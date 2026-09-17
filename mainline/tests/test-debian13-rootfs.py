#!/usr/bin/env python3
"""Static and unit tests for the R46H Debian 13 p2 MVP builder."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
import uuid


REPO_ROOT = Path(__file__).resolve().parents[2]
ROOTFS = REPO_ROOT / "mainline/rootfs-debian13"
BUILD_SCRIPT = REPO_ROOT / "mainline/scripts/build-debian13-rootfs.sh"
PACKAGER = REPO_ROOT / "mainline/scripts/package-debian13-rootfs.py"
PLAN_GENERATOR = REPO_ROOT / "mainline/scripts/generate-debian13-write-plan.py"
PROFILE = REPO_ROOT / "mainline/deploy/profiles/hl-r46h-v22-g92-v1.json"


def load_packager():
    spec = importlib.util.spec_from_file_location("package_debian13_rootfs", PACKAGER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Debian 13 packager")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_packager()


def load_plan_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_debian13_write_plan", PLAN_GENERATOR
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load Debian 13 plan generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PLAN_MODULE = load_plan_generator()


class Debian13RootfsTests(unittest.TestCase):
    def test_geometry_matches_card_profile(self) -> None:
        profile = json.loads(PROFILE.read_text(encoding="utf-8"))
        root = profile["card"]["root"]
        self.assertEqual(root["number"], 2)
        self.assertEqual(root["partuuid"], "c9f931c9-02")
        self.assertEqual(root["size"], MODULE.IMAGE_SIZE)
        self.assertEqual(
            MODULE.FS_BLOCK_SIZE * MODULE.FS_BLOCK_COUNT + MODULE.FS_TAIL_SIZE,
            MODULE.IMAGE_SIZE,
        )
        self.assertEqual(MODULE.FS_TAIL_SIZE, 512)

    def test_snapshot_and_base_are_pinned(self) -> None:
        dockerfile = (ROOTFS / "Dockerfile").read_text(encoding="utf-8")
        sources = (ROOTFS / "apt/debian.sources").read_text(encoding="utf-8")
        from_lines = [line.split() for line in dockerfile.splitlines() if line.startswith("FROM ")]
        self.assertEqual(len(from_lines), 2)
        self.assertTrue(all(parts[1] == MODULE.BASE_IMAGE for parts in from_lines))
        self.assertIn("20260713T000000Z", sources)
        self.assertIn("non-free-firmware", sources)
        self.assertNotIn("deb.debian.org", sources)
        self.assertIn('Acquire::Check-Valid-Until "false";', (ROOTFS / "apt/99snapshot").read_text())

    def test_required_and_forbidden_packages(self) -> None:
        packages: set[str] = set()
        for name in ("packages.base.txt", "packages.hardware.txt", "packages.graphics.txt"):
            lines = [
                line
                for line in (ROOTFS / name).read_text(encoding="utf-8").splitlines()
                if line
            ]
            self.assertEqual(lines, sorted(lines))
            self.assertFalse(packages.intersection(lines))
            packages.update(lines)
        required = {
            "firmware-realtek",
            "libgl1-mesa-dri",
            "libnss-systemd",
            "libpam-systemd",
            "linux-sysctl-defaults",
            "network-manager",
            "netbase",
            "openssh-server",
            "systemd-sysv",
            "systemd-timesyncd",
            "udev",
        }
        self.assertTrue(required.issubset(packages))
        self.assertFalse(any("mali" in package.lower() for package in packages))

    def test_boot_and_service_contract(self) -> None:
        fstab = (ROOTFS / "overlay/etc/fstab").read_text(encoding="utf-8")
        self.assertIn("PARTUUID=c9f931c9-02 / ext4", fstab)
        self.assertIn("PARTUUID=c9f931c9-01 /boot vfat noauto,ro", fstab)
        self.assertIn(
            "PARTUUID=c9f931c9-03 /roms exfat ro,noauto,nofail 0 0",
            fstab,
        )
        modules = [
            line
            for line in (ROOTFS / "overlay/etc/modules-load.d/r46h.conf").read_text().splitlines()
            if line
        ]
        self.assertEqual(modules, ["rtl8xxxu", "rk817_charger", "exfat"])
        dockerfile = (ROOTFS / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("serial-getty@ttyS2.service", dockerfile)
        self.assertIn("NetworkManager-wait-online.service", dockerfile)
        self.assertIn("systemd-firstboot.service", dockerfile)
        self.assertIn("alsa-restore.service", dockerfile)
        self.assertIn("/usr/share/zoneinfo/Asia/Shanghai", dockerfile)
        self.assertEqual(
            (ROOTFS / "overlay/etc/locale.conf").read_text(encoding="utf-8"),
            "LANG=C.UTF-8\n",
        )
        network_manager_dropin = (
            ROOTFS
            / "overlay/etc/systemd/system/NetworkManager.service.d/10-r46h-wifi-mac.conf"
        ).read_text(encoding="utf-8")
        self.assertIn("Requires=r46h-firstboot.service", network_manager_dropin)
        self.assertIn("Wants=r46h-wifi-mac.service", network_manager_dropin)
        self.assertIn(
            "After=r46h-firstboot.service r46h-wifi-mac.service",
            network_manager_dropin,
        )
        firstboot = (
            ROOTFS / "overlay/etc/systemd/system/r46h-firstboot.service"
        ).read_text(encoding="utf-8")
        self.assertIn("Before=sshd-keygen.service ssh.service", firstboot)
        self.assertIn(
            "rootfs-config/hostname",
            (ROOTFS / "build-ext4-in-container.sh").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "ln -s /run/NetworkManager/resolv.conf",
            (ROOTFS / "build-ext4-in-container.sh").read_text(encoding="utf-8"),
        )
        self.assertNotIn("rm -f /etc/resolv.conf", dockerfile)

    def test_security_and_graphics_contract(self) -> None:
        ssh = (ROOTFS / "overlay/etc/ssh/sshd_config.d/10-r46h-mvp.conf").read_text()
        self.assertIn("PermitRootLogin no", ssh)
        self.assertIn("PasswordAuthentication no", ssh)
        self.assertIn("AllowUsers ark", ssh)
        ssh_dropin = (
            ROOTFS / "overlay/etc/systemd/system/ssh.service.d/10-r46h-firstboot.conf"
        ).read_text(encoding="utf-8")
        self.assertIn("Requires=r46h-firstboot.service", ssh_dropin)
        self.assertIn("After=r46h-firstboot.service", ssh_dropin)
        smoke = (ROOTFS / "overlay/usr/local/sbin/r46h-rootfs-smoke").read_text()
        self.assertIn("MESA_LOADER_DRIVER_OVERRIDE=panfrost", smoke)
        self.assertIn("GPU_TIMEOUT_SECONDS=30", smoke)
        self.assertIn("/sys/fs/ext4/mmcblk0p2/errors_count", smoke)
        self.assertIn("dmesg_ring_wrapped", smoke)
        self.assertIn(
            "systemd-analyze --root=\"$ROOTFS\" verify --man=no",
            (ROOTFS / "build-ext4-in-container.sh").read_text(encoding="utf-8"),
        )
        self.assertIn(
            'rm -f -- "$ROOTFS/.dockerenv"',
            (ROOTFS / "build-ext4-in-container.sh").read_text(encoding="utf-8"),
        )
        self.assertIn("renderer=Mali-G31 (Panfrost)", smoke)
        self.assertIn("llvmpipe|softpipe|libMali", smoke)
        self.assertIn("source=usb-serial", smoke)
        self.assertIn('/sys/class/net/$wifi_iface/address', smoke)
        wifi_mac = (ROOTFS / "overlay/usr/libexec/r46h-wifi-mac").read_text()
        self.assertIn('"$path/idVendor"', wifi_mac)
        self.assertIn('"$path/idProduct"', wifi_mac)
        self.assertIn("no-matching-realtek-interface", wifi_mac)
        self.assertNotIn("/dev/dri/card0", smoke)
        self.assertNotIn("modetest", smoke)

    def test_write_plan_is_root_only(self) -> None:
        final_image = REPO_ROOT / "mainline/out" / MODULE.OUTPUT_NAME / MODULE.IMAGE_NAME
        raw = PLAN_MODULE.build_write_plan(
            "/dev/disk17", final_image, "a" * 64, "b" * 64
        )
        plan = json.loads(raw)
        self.assertEqual(
            set(plan), {"format_version", "profile_id", "device", "operations"}
        )
        self.assertEqual(plan["device"], "/dev/disk17")
        self.assertEqual(plan["profile_id"], "hl-r46h-v22-g92-v1")
        self.assertEqual(len(plan["operations"]), 1)
        operation = plan["operations"][0]
        self.assertEqual(
            set(operation),
            {
                "id",
                "description",
                "partition",
                "source_path",
                "source_size",
                "source_sha256",
                "target_sha256_before",
            },
        )
        self.assertEqual(operation["id"], "write-debian13-p2-mvp-v0.1")
        self.assertEqual(operation["partition"], "root")
        self.assertEqual(operation["source_size"], 10_716_877_312)
        self.assertEqual(operation["source_path"], str(final_image))
        self.assertEqual(operation["source_sha256"], "a" * 64)
        self.assertEqual(operation["target_sha256_before"], "b" * 64)
        for invalid_device in (
            "/dev/disk0",
            "/dev/disk04",
            "/dev/disk4s2",
            "/dev/rdisk4",
            "disk4",
        ):
            with self.subTest(device=invalid_device):
                with self.assertRaises(PLAN_MODULE.PlanError):
                    PLAN_MODULE.build_write_plan(
                        invalid_device, final_image, "a" * 64, "b" * 64
                    )
        with self.assertRaises(PLAN_MODULE.PlanError):
            PLAN_MODULE.build_write_plan(
                "/dev/disk17", final_image, "a" * 64, "not-a-sha256"
            )

    def test_write_plan_supports_gaming_v03_on_fast_card(self) -> None:
        artifact_id = "debian13-p2-gaming-v0.3"
        profile_id = "hl-r46h-v22-g92-62534975488-v1"
        final_image = (
            REPO_ROOT
            / "mainline/out/r46h-debian13-p2-gaming-v0.3"
            / "r46h-debian13-p2-gaming-v0.3.ext4"
        )
        raw = PLAN_MODULE.build_write_plan(
            "/dev/disk13",
            final_image,
            "c" * 64,
            "d" * 64,
            artifact_id=artifact_id,
            profile_id=profile_id,
        )
        plan = json.loads(raw)
        self.assertEqual(plan["profile_id"], profile_id)
        operation = plan["operations"][0]
        self.assertEqual(operation["id"], "write-debian13-p2-gaming-v0.3")
        self.assertEqual(operation["partition"], "root")
        self.assertEqual(operation["source_path"], str(final_image))
        self.assertEqual(operation["source_size"], 10_716_877_312)
        self.assertEqual(operation["source_sha256"], "c" * 64)
        self.assertEqual(operation["target_sha256_before"], "d" * 64)

        with self.assertRaises(PLAN_MODULE.PlanError):
            PLAN_MODULE.build_write_plan(
                "/dev/disk13",
                final_image,
                "c" * 64,
                "d" * 64,
                artifact_id="unknown",
                profile_id=profile_id,
            )
        with self.assertRaises(PLAN_MODULE.PlanError):
            PLAN_MODULE.build_write_plan(
                "/dev/disk13",
                final_image,
                "c" * 64,
                "d" * 64,
                artifact_id=artifact_id,
                profile_id="unknown",
            )
        with self.assertRaises(PLAN_MODULE.PlanError):
            PLAN_MODULE.build_write_plan(
                "/dev/disk13",
                final_image,
                "c" * 64,
                "d" * 64,
                artifact_id=artifact_id,
                profile_id="hl-r46h-v22-g92-v1",
            )

    def test_write_plan_supports_gaming_v04_on_fast_card(self) -> None:
        artifact_id = "debian13-p2-gaming-v0.4"
        profile_id = "hl-r46h-v22-g92-62534975488-v1"
        final_image = (
            REPO_ROOT
            / "mainline/out/r46h-debian13-p2-gaming-v0.4"
            / "r46h-debian13-p2-gaming-v0.4.ext4"
        )
        raw = PLAN_MODULE.build_write_plan(
            "/dev/disk14",
            final_image,
            "e" * 64,
            "f" * 64,
            artifact_id=artifact_id,
            profile_id=profile_id,
        )
        plan = json.loads(raw)
        self.assertEqual(plan["profile_id"], profile_id)
        operation = plan["operations"][0]
        self.assertEqual(operation["id"], "write-debian13-p2-gaming-v0.4")
        self.assertEqual(operation["partition"], "root")
        self.assertEqual(operation["source_path"], str(final_image))
        self.assertEqual(operation["source_size"], 10_716_877_312)
        self.assertEqual(operation["source_sha256"], "e" * 64)
        self.assertEqual(operation["target_sha256_before"], "f" * 64)

        with self.assertRaises(PLAN_MODULE.PlanError):
            PLAN_MODULE.build_write_plan(
                "/dev/disk14",
                final_image,
                "e" * 64,
                "f" * 64,
                artifact_id=artifact_id,
                profile_id="hl-r46h-v22-g92-v1",
            )

    def test_write_plan_supports_gaming_v05_on_fast_card(self) -> None:
        artifact_id = "debian13-p2-gaming-v0.5"
        profile_id = "hl-r46h-v22-g92-62534975488-v1"
        final_image = (
            REPO_ROOT
            / "mainline/out/r46h-debian13-p2-gaming-v0.5"
            / "r46h-debian13-p2-gaming-v0.5.ext4"
        )
        raw = PLAN_MODULE.build_write_plan(
            "/dev/disk15",
            final_image,
            "1" * 64,
            "2" * 64,
            artifact_id=artifact_id,
            profile_id=profile_id,
        )
        plan = json.loads(raw)
        self.assertEqual(plan["profile_id"], profile_id)
        operation = plan["operations"][0]
        self.assertEqual(operation["id"], "write-debian13-p2-gaming-v0.5")
        self.assertEqual(operation["partition"], "root")
        self.assertEqual(operation["source_path"], str(final_image))
        self.assertEqual(operation["source_size"], 10_716_877_312)
        self.assertEqual(operation["source_sha256"], "1" * 64)
        self.assertEqual(operation["target_sha256_before"], "2" * 64)

        with self.assertRaises(PLAN_MODULE.PlanError):
            PLAN_MODULE.build_write_plan(
                "/dev/disk15",
                final_image,
                "1" * 64,
                "2" * 64,
                artifact_id=artifact_id,
                profile_id="hl-r46h-v22-g92-v1",
            )

    def test_write_plan_supports_gaming_v06_on_fast_card(self) -> None:
        artifact_id = "debian13-p2-gaming-v0.6"
        profile_id = "hl-r46h-v22-g92-62534975488-v1"
        final_image = (
            REPO_ROOT
            / "mainline/out/r46h-debian13-p2-gaming-v0.6"
            / "r46h-debian13-p2-gaming-v0.6.ext4"
        )
        raw = PLAN_MODULE.build_write_plan(
            "/dev/disk16",
            final_image,
            "3" * 64,
            "4" * 64,
            artifact_id=artifact_id,
            profile_id=profile_id,
        )
        plan = json.loads(raw)
        self.assertEqual(plan["profile_id"], profile_id)
        operation = plan["operations"][0]
        self.assertEqual(operation["id"], "write-debian13-p2-gaming-v0.6")
        self.assertEqual(operation["partition"], "root")
        self.assertEqual(operation["source_path"], str(final_image))
        self.assertEqual(operation["source_size"], 10_716_877_312)
        self.assertEqual(operation["source_sha256"], "3" * 64)
        self.assertEqual(operation["target_sha256_before"], "4" * 64)

        with self.assertRaises(PLAN_MODULE.PlanError):
            PLAN_MODULE.build_write_plan(
                "/dev/disk16",
                final_image,
                "3" * 64,
                "4" * 64,
                artifact_id=artifact_id,
                profile_id="hl-r46h-v22-g92-v1",
            )

    def test_write_plan_supports_exact_gaming_artifacts_on_fast_card(self) -> None:
        profile_id = "hl-r46h-v22-g92-62534975488-v1"
        cases = (
            (
                "debian13-p2-gaming-v0.7",
                "17",
                "6",
                "22490e9bafcc0920a382f38d35e193ea033454de4af0a3e1dcda1eb28a84e7a7",
                "17530b491eaf7edd60cb0b499cc0c920af7399673bf9296f30c5753bc1ca7180",
            ),
            (
                "debian13-p2-gaming-v0.11",
                "18",
                "7",
                "f8a462c987a5cbcac2d1ae4c054c7844c55d74ea3889f3dd44d58dac8be2a3ab",
                "d84788c682c1f9e8c13c7fdcc1f0ebea25944aa2933b3633dde18a031b2aac60",
            ),
            (
                "debian13-p2-gaming-v0.12",
                "19",
                "8",
                "dcc7d0e526d9efe0f2bb58930cc008d672091c3b262fd3afa1694bb1a4a7fcf4",
                "af3235742a0324453a6193bc0c3ec0e149fffcf9f6c0c22dba4e2f2e082a9111",
            ),
            (
                "debian13-p2-gaming-v0.15",
                "20",
                "9",
                "f6533599f9c94997438170ac38e5a49eec9b13aa216cb20cde797cbf952968d0",
                "a69c2dafeae76f37a6e582bfdf4887d5714b82a4cf5b3dc7a84e29f36be6e893",
            ),
            (
                "debian13-p2-gaming-v0.16",
                "21",
                "a",
                "90a5c97848d1942b40981c975fbcbdcc93073b80bdc619ab8ebb7ab79035828a",
                "21cdfa3af3b96b6233decdc3ca4f8475c0eba946503045a4e86c21c50b8374c4",
            ),
            (
                "debian13-p2-gaming-v0.17",
                "22",
                "b",
                "45c7c732d36b8fb6ee5b33232ae69041e6159b285b667ab7eba2a81f34a9947e",
                "efccaf9b1d6b48624427f96f0d995c0143cb50e3447f31506ef6553973538897",
            ),
            (
                "debian13-p2-gaming-v0.18",
                "23",
                "c",
                "1ee96f46377d3fb579adae226b5eba8f86cde2bc3efe4b5920b256e20391fadd",
                "461d47535870568c854b1edf7016629a6fa66a60da81915c14449ac8700c4cae",
            ),
        )
        for artifact_id, disk, target_digit, build_sha, image_sha in cases:
            with self.subTest(artifact_id=artifact_id):
                spec = PLAN_MODULE.artifact_spec(artifact_id)
                self.assertEqual(spec["build_info_sha256"], build_sha)
                final_image = (
                    REPO_ROOT
                    / "mainline/out"
                    / spec["output_name"]
                    / spec["image_name"]
                ).resolve()
                canonical_image, canonical_sha = PLAN_MODULE.load_artifact(
                    REPO_ROOT, artifact_id
                )
                self.assertEqual(canonical_image, final_image)
                self.assertEqual(canonical_sha, image_sha)
                plan = json.loads(
                    PLAN_MODULE.build_write_plan(
                        f"/dev/disk{disk}",
                        canonical_image,
                        canonical_sha,
                        target_digit * 64,
                        artifact_id=artifact_id,
                        profile_id=profile_id,
                    )
                )
                operation = plan["operations"][0]
                self.assertEqual(operation["id"], f"write-{artifact_id}")
                self.assertEqual(operation["partition"], "root")
                self.assertEqual(operation["source_path"], str(final_image))
                self.assertEqual(operation["source_size"], 10_716_877_312)
                self.assertEqual(operation["source_sha256"], canonical_sha)
                self.assertEqual(
                    operation["target_sha256_before"], target_digit * 64
                )

                with self.assertRaises(PLAN_MODULE.PlanError):
                    PLAN_MODULE.build_write_plan(
                        f"/dev/disk{disk}",
                        canonical_image,
                        canonical_sha,
                        target_digit * 64,
                        artifact_id=artifact_id,
                        profile_id="hl-r46h-v22-g92-v1",
                    )

    def test_atomic_publish_is_no_replace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "source").mkdir()
            (root / "destination").mkdir()
            descriptor = __import__("os").open(root, __import__("os").O_RDONLY)
            try:
                with self.assertRaises(MODULE.PackageError):
                    MODULE.rename_noreplace(descriptor, "source", "destination")
            finally:
                __import__("os").close(descriptor)
            self.assertTrue((root / "source").is_dir())
            self.assertTrue((root / "destination").is_dir())

    def test_ext4_superblock_requires_full_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "superblock.img"
            superblock = bytearray(1024)
            struct.pack_into("<I", superblock, 0x04, MODULE.FS_BLOCK_COUNT)
            struct.pack_into("<I", superblock, 0x18, 2)
            struct.pack_into("<H", superblock, 0x38, 0xEF53)
            struct.pack_into("<H", superblock, 0x3A, 0x0001)
            superblock[0x68:0x78] = uuid.UUID(MODULE.FS_UUID).bytes
            superblock[0x78:0x88] = MODULE.FS_LABEL.encode("ascii").ljust(16, b"\0")
            image.write_bytes(b"\0" * 1024 + superblock)
            MODULE.require_ext4_superblock(image)

            struct.pack_into("<I", superblock, 0x04, MODULE.FS_BLOCK_COUNT - 1)
            image.write_bytes(b"\0" * 1024 + superblock)
            with self.assertRaises(MODULE.PackageError):
                MODULE.require_ext4_superblock(image)

    def test_build_script_pins_kernel_and_external_workspace(self) -> None:
        script = BUILD_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("8c7282a07bdec52b753a8af27d15c6bbc8b71b34d017c3d78a2273fba6cfd09e", script)
        self.assertIn("6.12.99-r46h-mainline-v0.8-bootloader-handoff", script)
        self.assertIn(
            "KERNEL_DIRECTORY=r46h-mainline-test-v0.8-bootloader-handoff",
            (ROOTFS / "build-ext4-in-container.sh").read_text(encoding="utf-8"),
        )
        self.assertIn("CACHE_ROOT=$OUTPUT_ROOT/.cache", script)
        self.assertIn('--iidfile "$runtime_iid_file"', script)
        self.assertIn('docker --context "$docker_context" create', script)
        self.assertIn('"$runtime_image_id"', script)
        self.assertIn(
            'PYTHONDONTWRITEBYTECODE=1 python3 "$SNAPSHOT_MAINLINE/tests/test-debian13-rootfs.py"',
            script,
        )
        self.assertIn("mainline/scripts/generate-debian13-write-plan.py", script)
        self.assertIn("build_inputs_git_dirty=false", script)
        self.assertIn("--network none", script)
        self.assertNotIn("/tmp/", script)


if __name__ == "__main__":
    unittest.main()
