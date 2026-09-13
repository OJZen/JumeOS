#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
PROMOTION = REPO / "mainline/gaming-product-boot-promotion"
TRANSACTION = PROMOTION / "transaction.sh"
INSTALLER = PROMOTION / "install.sh"
FALLBACK_HELPER = PROMOTION / "fallback-modules.sh"
STORAGE_HELPER = PROMOTION / "storage-health.sh"
RECOVERED_POSTFLIGHT = PROMOTION / "complete-recovered-mmc-postflight.sh"
BOOT = PROMOTION / "boot.ini.v0.15-gaming-product"
BUILDER_PATH = REPO / "mainline/scripts/build-r46h-v15-boot-promotion.py"

SPEC = importlib.util.spec_from_file_location("r46h_v15_boot_builder", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


class PromotionFixture:
    BASE_NAMES = {
        ".Spotlight-V100",
        ".console",
        "Image",
        "Image.mainline-v0.10-adc-full-range.gz",
        "Image.mainline-v0.8-bootloader-handoff.gz",
        "System Volume Information",
        "USE_DTB_SELECT_TO_SELECT_DEVICE",
        "arkos4clone-uboot.dtb",
        "boot.ini",
        "boot.ini.v0.10-adc-full-range",
        "boot.ini.v0.8-bootloader-handoff",
        "boot.ini.vendor",
        "boot.log",
        "clone_log.txt",
        "consoles",
        "dtb_selector_linux32",
        "dtb_selector_macos",
        "dtb_selector_win32.exe",
        "error.log",
        "firstboot.sh",
        "logo.bmp",
        "rk3326-r46h-linux.dtb",
        "rk3326-r46h-mainline-v0.10-adc-full-range.dtb",
        "rk3326-r46h-mainline-v0.8-bootloader-handoff.dtb",
        "uInitrd",
    }

    def __init__(self, parent: Path) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="fixture.", dir=parent))
        self.boot = self.root / "boot"
        self.source = self.root / "source"
        self.boot.mkdir()
        self.source.mkdir()
        self.bytes = {
            "R46H_V08_BOOT": b"fixture-v08-boot\n",
            "R46H_V08_IMAGE": b"fixture-v08-image\n",
            "R46H_V08_DTB": b"fixture-v08-dtb\n",
            "R46H_V10_BOOT": b"fixture-v10-boot\n",
            "R46H_V10_IMAGE": b"fixture-v10-image\n",
            "R46H_V10_DTB": b"fixture-v10-dtb\n",
            "R46H_UBOOT_DTB": b"fixture-uboot-dtb\n",
            "R46H_V15_BOOT": b"fixture-v15-boot\n",
            "R46H_V15_IMAGE": b"fixture-v15-image\n",
            "R46H_V15_DTB": b"fixture-v15-dtb\n",
        }
        directories = {"consoles", "System Volume Information", ".Spotlight-V100"}
        for name in sorted(self.BASE_NAMES):
            path = self.boot / name
            if name in directories:
                path.mkdir()
            else:
                path.write_bytes(f"legacy:{name}\n".encode())
        (self.boot / "consoles/r46h").mkdir()
        mapping = {
            "boot.ini.v0.8-bootloader-handoff": "R46H_V08_BOOT",
            "Image.mainline-v0.8-bootloader-handoff.gz": "R46H_V08_IMAGE",
            "rk3326-r46h-mainline-v0.8-bootloader-handoff.dtb": "R46H_V08_DTB",
            "boot.ini.v0.10-adc-full-range": "R46H_V10_BOOT",
            "Image.mainline-v0.10-adc-full-range.gz": "R46H_V10_IMAGE",
            "rk3326-r46h-mainline-v0.10-adc-full-range.dtb": "R46H_V10_DTB",
            "boot.ini": "R46H_V10_BOOT",
            "arkos4clone-uboot.dtb": "R46H_UBOOT_DTB",
        }
        for name, key in mapping.items():
            (self.boot / name).write_bytes(self.bytes[key])
        (self.boot / "consoles/r46h/arkos4clone-uboot.dtb").write_bytes(
            self.bytes["R46H_UBOOT_DTB"]
        )
        for name, key in (
            ("Image.mainline-v0.15-gaming-product.gz", "R46H_V15_IMAGE"),
            ("rk3326-r46h-mainline-v0.15-gaming-product.dtb", "R46H_V15_DTB"),
            ("boot.ini.v0.15-gaming-product", "R46H_V15_BOOT"),
        ):
            (self.source / name).write_bytes(self.bytes[key])
        self.transaction = self.root / "transaction.sh"
        self.transaction.write_text(self._render_transaction(), encoding="utf-8")

    def _render_transaction(self) -> str:
        text = TRANSACTION.read_text(encoding="utf-8")
        replacements: dict[str, str | int] = {}
        for prefix, key in (
            ("R46H_V08_BOOT", "R46H_V08_BOOT"),
            ("R46H_V08_IMAGE", "R46H_V08_IMAGE"),
            ("R46H_V08_DTB", "R46H_V08_DTB"),
            ("R46H_V10_BOOT", "R46H_V10_BOOT"),
            ("R46H_V10_IMAGE", "R46H_V10_IMAGE"),
            ("R46H_V10_DTB", "R46H_V10_DTB"),
            ("R46H_UBOOT_DTB", "R46H_UBOOT_DTB"),
            ("R46H_V15_BOOT", "R46H_V15_BOOT"),
            ("R46H_V15_IMAGE", "R46H_V15_IMAGE"),
            ("R46H_V15_DTB", "R46H_V15_DTB"),
        ):
            replacements[f"{prefix}_SIZE"] = len(self.bytes[key])
            replacements[f"{prefix}_SHA256"] = digest(self.bytes[key])
        replacements["R46H_MINIMUM_FREE_BYTES"] = 0
        for name, value in replacements.items():
            text, count = re.subn(
                rf"^readonly {re.escape(name)}=.*$",
                f"readonly {name}={value}",
                text,
                count=1,
                flags=re.MULTILINE,
            )
            if count != 1:
                raise AssertionError(f"cannot render fixture constant {name}")
        return text

    def run(self, commands: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        script = f"""
set -Eeuo pipefail
export R46H_TRANSACTION_TEST_MODE=1
source {self.transaction!s}
boot={self.boot!s}
source_dir={self.source!s}
{commands}
"""
        result = subprocess.run(
            ["/bin/bash"],
            input=script,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            cwd=REPO,
        )
        if result.returncode != expected:
            raise AssertionError(
                f"fixture command returned {result.returncode}, expected {expected}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        return result

    def close(self) -> None:
        shutil.rmtree(self.root)


class R46HV15BootPromotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cache = REPO / "mainline/out/.cache/r46h-v15-boot-promotion-tests"
        cls.cache.mkdir(parents=True, exist_ok=True)

    def setUp(self) -> None:
        self.fixture = PromotionFixture(self.cache)

    def tearDown(self) -> None:
        self.fixture.close()

    def test_boot_script_has_exact_size_hash_and_guards(self) -> None:
        payload = BOOT.read_bytes()
        self.assertEqual(len(payload), BUILDER.BOOT_SIZE)
        self.assertEqual(digest(payload), BUILDER.BOOT_SHA256)
        text = payload.decode("utf-8")
        self.assertIn("Image.mainline-v0.15-gaming-product.gz", text)
        self.assertIn("rk3326-r46h-mainline-v0.15-gaming-product.dtb", text)
        self.assertIn("0xe3bde2", text)
        self.assertIn("0x27a5200", text)
        self.assertIn("0xc16e", text)
        self.assertNotIn("saveenv", text)

    def test_happy_prepare_activate_and_rollback(self) -> None:
        self.fixture.run(
            """
[[ "$(r46h_tx_detect_state "$boot")" == base ]]
r46h_tx_prepare "$boot" "$source_dir" 0
[[ "$(r46h_tx_detect_state "$boot")" == prepared ]]
cmp -s "$boot/boot.ini" "$boot/boot.ini.v0.10-adc-full-range"
r46h_tx_activate "$boot" 0
[[ "$(r46h_tx_detect_state "$boot")" == activated ]]
cmp -s "$boot/boot.ini" "$boot/boot.ini.v0.15-gaming-product"
r46h_tx_rollback "$boot"
[[ "$(r46h_tx_detect_state "$boot")" == prepared ]]
cmp -s "$boot/boot.ini" "$boot/boot.ini.v0.10-adc-full-range"
cmp -s "$boot/boot.ini.v0.8-bootloader-handoff" <(printf 'fixture-v08-boot\n')
"""
        )

    def test_prepare_faults_keep_v10_active_and_recover(self) -> None:
        fixtures = [self.fixture]
        try:
            for index, fault in enumerate(("after-image", "after-dtb", "after-boot")):
                fixture = self.fixture if index == 0 else PromotionFixture(self.cache)
                if index != 0:
                    fixtures.append(fixture)
                with self.subTest(fault=fault):
                    fixture.run(
                        f"""
export R46H_TRANSACTION_FAULT={fault}
if r46h_tx_prepare "$boot" "$source_dir" 0; then exit 91; fi
[[ "$(r46h_tx_detect_state "$boot")" == prepare-partial ]]
cmp -s "$boot/boot.ini" "$boot/boot.ini.v0.10-adc-full-range"
unset R46H_TRANSACTION_FAULT
r46h_tx_prepare "$boot" "$source_dir" 1
[[ "$(r46h_tx_detect_state "$boot")" == prepared ]]
"""
                    )
        finally:
            for fixture in fixtures[1:]:
                fixture.close()

    def test_activation_fault_is_explicitly_recoverable_or_rollbackable(self) -> None:
        self.fixture.run(
            """
r46h_tx_prepare "$boot" "$source_dir" 0
export R46H_TRANSACTION_FAULT=after-active
if r46h_tx_activate "$boot" 0; then exit 92; fi
[[ "$(r46h_tx_detect_state "$boot")" == activate-partial-v15 ]]
unset R46H_TRANSACTION_FAULT
r46h_tx_rollback "$boot"
[[ "$(r46h_tx_detect_state "$boot")" == prepared ]]
r46h_tx_activate "$boot" 0
[[ "$(r46h_tx_detect_state "$boot")" == activated ]]
"""
        )

    def test_explicit_rollback_fault_keeps_a_recoverable_journal(self) -> None:
        self.fixture.run(
            """
r46h_tx_prepare "$boot" "$source_dir" 0
r46h_tx_activate "$boot" 0
export R46H_TRANSACTION_FAULT=after-rollback-active
if r46h_tx_rollback "$boot"; then exit 93; fi
[[ "$(r46h_tx_detect_state "$boot")" == rollback-partial-v10 ]]
unset R46H_TRANSACTION_FAULT
r46h_tx_rollback "$boot"
[[ "$(r46h_tx_detect_state "$boot")" == prepared ]]
"""
        )

    def test_tampered_anchor_extra_entry_and_symlink_fail_closed(self) -> None:
        variants = []
        for mutation in ("anchor", "extra", "symlink"):
            clone = self.fixture.root.parent / f"{self.fixture.root.name}-{mutation}"
            shutil.copytree(self.fixture.root, clone)
            variants.append(clone)
            boot = clone / "boot"
            if mutation == "anchor":
                (boot / "boot.ini.v0.8-bootloader-handoff").write_bytes(b"tampered\n")
            elif mutation == "extra":
                (boot / "unexpected.bin").write_bytes(b"unexpected\n")
            else:
                target = boot / "boot.ini.v0.10-adc-full-range"
                target.unlink()
                target.symlink_to("boot.ini")
            result = subprocess.run(
                ["/bin/bash", "-c", f"export R46H_TRANSACTION_TEST_MODE=1; source {clone / 'transaction.sh'}; r46h_tx_detect_state {boot}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0, mutation)
        for clone in variants:
            shutil.rmtree(clone)

    def test_installer_pins_dynamic_identity_and_never_controls_power(self) -> None:
        text = INSTALLER.read_text(encoding="utf-8")
        self.assertIn("/dev/disk/by-partuuid/$EXPECTED_BOOT_PARTUUID", text)
        self.assertIn("R46H_BOOT_DEVICE=$BOOT_DEVICE", text)
        self.assertIn("EXPECTED_BASE_P1_SHA256=f50597d4", text)
        self.assertNotIn(
            "e962cdb3f566476add93e51dc912e2656ff3ad38741fe75d97ce8c131ca12c6b",
            text,
        )
        self.assertIn("EXPECTED_PREFIX_SHA256=3fe2feb9", text)
        self.assertIn("--prepare --confirm", text)
        self.assertIn("--activate --confirm", text)
        self.assertIn("--rollback --confirm", text)
        self.assertIn("verify_hotfixed_product", text)
        self.assertIn("r46h_mod_ensure", text)
        for line in text.splitlines():
            stripped = line.strip()
            self.assertFalse(re.match(r"^(sudo +)?(reboot|poweroff)( |$)", stripped))
            self.assertFalse(re.match(r"^saveenv( |$)", stripped))

    def _classify_storage_log(self, lines: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/bash", "-c", f"set -Eeuo pipefail; source {STORAGE_HELPER}; r46h_storage_health_from_log"],
            input="\n".join(lines) + ("\n" if lines else ""),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            cwd=REPO,
        )

    @staticmethod
    def _recovered_mmc_log() -> list[str]:
        return [
            "[    2.158025] mmc_host mmc0: Bus speed (slot 0) = 400000Hz (slot req 400000Hz, actual 400000HZ div = 0)",
            "[    2.241198] mmc0: error -84 whilst initialising SD card",
            "[    2.266816] mmc_host mmc0: Bus speed (slot 0) = 300000Hz (slot req 300000Hz, actual 300000HZ div = 0)",
            "[    2.435818] mmc_host mmc0: Bus speed (slot 0) = 150000000Hz (slot req 150000000Hz, actual 150000000HZ div = 0)",
            "[    3.192122] mmc0: new ultra high speed SDR104 SDXC card at address 0001",
            "[    3.201570] mmcblk0: mmc0:0001 SD 58.2 GiB",
            "[    3.210055]  mmcblk0: p1 p2 p3",
            "[    3.542582] EXT4-fs (mmcblk0p2): mounted filesystem d3130003-46a4-4d56-9001-000000000003 r/w with ordered data mode. Quota mode: none.",
            "[    7.291433] EXT4-fs (mmcblk0p2): re-mounted d3130003-46a4-4d56-9001-000000000003.",
        ]

    def test_storage_health_accepts_only_the_exact_recovered_mmc_sequence(self) -> None:
        clean = self._classify_storage_log(["[ 1.0] mmc0: new card", "[ 2.0] root ready"])
        self.assertEqual(clean.returncode, 0, clean.stderr)
        self.assertEqual(clean.stdout.strip(), "clean")

        recovered = self._classify_storage_log(self._recovered_mmc_log())
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        self.assertEqual(recovered.stdout.strip(), "recovered-known-open")

    def test_storage_health_rejects_reordered_repeated_and_other_faults(self) -> None:
        base = self._recovered_mmc_log()
        variants = {
            "reordered": [base[0], base[2], base[1], *base[3:]],
            "repeated": [*base[:2], base[1], *base[2:]],
            "different-init-error": [
                *base[:1],
                "[ 2.2] mmc0: error -110 whilst initialising SD card",
                *base[2:],
            ],
            "missing-partitions": [*base[:6], *base[7:]],
            "later-ext4-error": [*base, "[ 9.0] EXT4-fs error (device mmcblk0p2): injected"],
            "later-mmc-timeout": [*base, "[ 9.0] mmc0: timeout waiting for hardware interrupt"],
        }
        for name, lines in variants.items():
            with self.subTest(name=name):
                result = self._classify_storage_log(lines)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout.strip(), "fault")

    def test_recovered_postflight_changes_only_the_status_state_line(self) -> None:
        def render(state: str) -> list[str]:
            result = subprocess.run(
                [
                    "/bin/bash",
                    "-c",
                    f"set -Eeuo pipefail; source {RECOVERED_POSTFLIGHT}; r46h_expected_status {state}",
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                cwd=REPO,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            return result.stdout.splitlines()

        activated = render("activated")
        complete = render("complete")
        self.assertEqual(len(activated), 13)
        self.assertEqual(len(complete), 13)
        self.assertEqual(
            [index for index, pair in enumerate(zip(activated, complete)) if pair[0] != pair[1]],
            [2],
        )
        self.assertEqual(activated[2], "state=activated")
        self.assertEqual(complete[2], "state=complete")
        text = RECOVERED_POSTFLIGHT.read_text(encoding="utf-8")
        self.assertIn("mount -t vfat -o ro,nosuid,nodev,noexec", text)
        self.assertIn("mmc_init=recovered-known-open", text)
        self.assertNotIn("mount -t vfat -o rw", text)
        for line in text.splitlines():
            stripped = line.strip()
            self.assertFalse(re.match(r"^(sudo +)?(reboot|poweroff)( |$)", stripped))
            self.assertFalse(re.match(r"^saveenv( |$)", stripped))

    def test_production_flush_uses_the_installer_bound_boot_device(self) -> None:
        trace = self.fixture.root / "blockdev.trace"
        result = subprocess.run(
            ["/bin/bash"],
            input=(
                "set -Eeuo pipefail\n"
                f"source {TRANSACTION}\n"
                "sync() { :; }\n"
                f"blockdev() {{ printf '%s\\n' \"$*\" > {trace}; }}\n"
                "BOOT_DEVICE=/dev/disk/by-partuuid/r46h-test-boot\n"
                "R46H_BOOT_DEVICE=$BOOT_DEVICE\n"
                "r46h_tx_flush\n"
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            cwd=REPO,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            trace.read_text(encoding="utf-8"),
            "--flushbufs /dev/disk/by-partuuid/r46h-test-boot\n",
        )

    def test_set_u_target_helpers_do_not_expand_unbound_locals(self) -> None:
        installer = INSTALLER.read_text(encoding="utf-8")
        match = re.search(
            r"verify_partition_geometry\(\) \{.*?^\}",
            installer,
            flags=re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match)
        sys_class = self.fixture.root / "sys/class/block"
        partition = sys_class / "mmcblk0p1"
        partition.mkdir(parents=True)
        (partition / "start").write_text("32768\n", encoding="utf-8")
        (partition / "size").write_text("229376\n", encoding="utf-8")
        geometry_function = match.group(0).replace("/sys/class/block", str(sys_class))
        geometry = subprocess.run(
            ["/bin/bash"],
            input=(
                "set -Eeuo pipefail\n"
                "die() { printf 'ERROR: %s\\n' \"$*\" >&2; exit 1; }\n"
                f"{geometry_function}\n"
                "verify_partition_geometry /dev/mmcblk0p1 32768 229376\n"
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            cwd=REPO,
        )
        self.assertEqual(geometry.returncode, 0, geometry.stderr)

        state = self.fixture.root / "module-state"
        state.mkdir()
        receipt = subprocess.run(
            ["/bin/bash"],
            input=(
                "set -Eeuo pipefail\n"
                f"source {FALLBACK_HELPER}\n"
                f"state_dir={state}\n"
                "r46h_mod_receipt_bytes > \"$state_dir/$R46H_V10_RECEIPT_NAME\"\n"
                "stat() { printf '0:0:600:1\\n'; }\n"
                "r46h_mod_verify_receipt \"$state_dir\"\n"
                "r46h_mod_publish_receipt \"$state_dir\"\n"
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            cwd=REPO,
        )
        self.assertEqual(receipt.returncode, 0, receipt.stderr)

    def test_builder_constants_match_pinned_kernel_bundle(self) -> None:
        captured = {
            "mainline/gaming-product-boot-promotion/complete-recovered-mmc-postflight.sh": RECOVERED_POSTFLIGHT.read_bytes(),
            "mainline/gaming-product-boot-promotion/fallback-modules.sh": FALLBACK_HELPER.read_bytes(),
            "mainline/gaming-product-boot-promotion/transaction.sh": TRANSACTION.read_bytes(),
            "mainline/gaming-product-boot-promotion/install.sh": INSTALLER.read_bytes(),
            "mainline/gaming-product-boot-promotion/storage-health.sh": STORAGE_HELPER.read_bytes(),
            "mainline/gaming-product-boot-promotion/boot.ini.v0.15-gaming-product": BOOT.read_bytes(),
        }
        BUILDER.check_script_constants(captured)
        work = Path(tempfile.mkdtemp(prefix="kernel.", dir=self.cache))
        try:
            result = BUILDER.verify_kernel_bundle(work)
            self.assertEqual(result["compressed_image_sha256"], BUILDER.COMPRESSED_IMAGE_SHA256)
            self.assertEqual(result["dtb_sha256"], BUILDER.KERNEL_DTB_SHA256)
            self.assertEqual(
                result["module_tree_sha256"], BUILDER.KERNEL_MODULE_TREE_SHA256
            )
            fallback = BUILDER.verify_fallback_bundle()
            self.assertEqual(
                fallback["module_tree_sha256"], BUILDER.FALLBACK_MODULE_TREE_SHA256
            )
            self.assertEqual(fallback["module_count"], 1276)
            rootfs = BUILDER.verify_product_rootfs_module_contract()
            self.assertEqual(
                rootfs["module_trees"][BUILDER.SECONDARY_FALLBACK_RELEASE],
                BUILDER.SECONDARY_FALLBACK_MODULE_TREE_SHA256,
            )
            self.assertEqual(
                rootfs["module_trees"]["6.12.99-r46h-mainline-v0.15-gaming-product"],
                BUILDER.KERNEL_MODULE_TREE_SHA256,
            )
        finally:
            shutil.rmtree(work)

    def test_product_p2_gap_is_closed_by_atomic_fallback_module_transaction(self) -> None:
        rootfs_tree = (
            REPO
            / "mainline/out/r46h-debian13-p2-gaming-v0.3/ROOTFS-TREE.tsv"
        ).read_text(encoding="utf-8")
        releases = {
            line.split("\t")[4].split("/")[4]
            for line in rootfs_tree.splitlines()
            if len(line.split("\t")) >= 5
            and line.split("\t")[4].startswith("./usr/lib/modules/")
            and len(line.split("\t")[4].split("/")) == 5
        }
        self.assertEqual(
            releases,
            {
                "6.12.99-r46h-mainline-v0.8-bootloader-handoff",
                "6.12.99-r46h-mainline-v0.15-gaming-product",
            },
        )
        helper = FALLBACK_HELPER.read_text(encoding="utf-8")
        self.assertIn(f"R46H_V10_RELEASE={BUILDER.FALLBACK_RELEASE}", helper)
        self.assertIn("r46h_mod_verify_tree", helper)
        self.assertIn("r46h_mod_verify_existing_fallbacks", helper)
        self.assertIn(BUILDER.SECONDARY_FALLBACK_MODULE_TREE_SHA256, helper)
        self.assertIn(BUILDER.KERNEL_MODULE_TREE_SHA256, helper)
        self.assertIn('mv -T -- "$staged_modules"', helper)
        self.assertIn("r46h_mod_publish_receipt", helper)
        self.assertNotIn("boot.ini", helper)

    def test_shell_module_tree_hash_matches_all_three_pinned_releases(self) -> None:
        trees = {
            "6.12.99-r46h-mainline-v0.8-bootloader-handoff": (
                REPO
                / "mainline/out/r46h-mainline-test-v0.8-bootloader-handoff/rootfs/lib/modules/6.12.99-r46h-mainline-v0.8-bootloader-handoff",
                BUILDER.SECONDARY_FALLBACK_MODULE_TREE_SHA256,
            ),
            BUILDER.FALLBACK_RELEASE: (
                REPO
                / f"mainline/out/r46h-mainline-test-v0.10-adc-full-range/rootfs/lib/modules/{BUILDER.FALLBACK_RELEASE}",
                BUILDER.FALLBACK_MODULE_TREE_SHA256,
            ),
            "6.12.99-r46h-mainline-v0.15-gaming-product": (
                REPO
                / "mainline/out/r46h-mainline-test-v0.15-gaming-product/rootfs/lib/modules/6.12.99-r46h-mainline-v0.15-gaming-product",
                BUILDER.KERNEL_MODULE_TREE_SHA256,
            ),
        }
        for release, (tree, expected) in trees.items():
            with self.subTest(release=release):
                result = subprocess.run(
                    ["/bin/bash"],
                    input=(
                        "set -Eeuo pipefail\n"
                        f"source {FALLBACK_HELPER}\n"
                        f"r46h_mod_tree_hash {tree} {release}\n"
                    ),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    cwd=REPO,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected)

    def test_control_archive_is_deterministic_and_contains_exact_boot_artifacts(self) -> None:
        captured = {
            "mainline/gaming-product-boot-promotion/complete-recovered-mmc-postflight.sh": RECOVERED_POSTFLIGHT.read_bytes(),
            "mainline/gaming-product-boot-promotion/fallback-modules.sh": FALLBACK_HELPER.read_bytes(),
            "mainline/gaming-product-boot-promotion/transaction.sh": TRANSACTION.read_bytes(),
            "mainline/gaming-product-boot-promotion/install.sh": INSTALLER.read_bytes(),
            "mainline/gaming-product-boot-promotion/storage-health.sh": STORAGE_HELPER.read_bytes(),
            "mainline/gaming-product-boot-promotion/boot.ini.v0.15-gaming-product": BOOT.read_bytes(),
        }
        work = Path(tempfile.mkdtemp(prefix="archive.", dir=self.cache))
        try:
            kernel = BUILDER.verify_kernel_bundle(work)
            fallback = BUILDER.verify_fallback_bundle()
            payload = work / "payload"
            BUILDER.create_payload(
                payload, captured, "a" * 40, "b" * 40, kernel, fallback, work
            )
            check = subprocess.run(
                [str(payload / "install.sh"), "--check-payload"],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(check.returncode, 0, check.stderr)
            self.assertIn("payload structure and checksums validated", check.stdout)
            first = work / "first.tar.gz"
            second = work / "second.tar.gz"
            BUILDER.deterministic_archive(payload, first)
            BUILDER.deterministic_archive(payload, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            BUILDER.validate_archive(first)
            self.assertGreater(first.stat().st_size, 45_000_000)
            self.assertLess(first.stat().st_size, 52_000_000)
        finally:
            shutil.rmtree(work)


if __name__ == "__main__":
    unittest.main()
