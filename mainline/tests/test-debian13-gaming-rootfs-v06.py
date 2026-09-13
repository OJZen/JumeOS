#!/usr/bin/env python3
"""Focused host tests for the successor R46H Debian gaming p2 v0.6 builder."""

from __future__ import annotations

import hashlib
import importlib.util
import io
from pathlib import Path
import stat
import sys
import tarfile
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO / "mainline/scripts/build-debian13-gaming-rootfs-v06.py"
ROOT = REPO / "mainline/rootfs-debian13-gaming-v06"
README = ROOT / "README.md"
IMAGE_TOOL = ROOT / "image-in-container.sh"
RULE = ROOT / "90-alsa-restore.rules"

SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v06", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BUILDER
SPEC.loader.exec_module(BUILDER)


class Debian13GamingRootfsV06Tests(unittest.TestCase):
    def test_identity_and_inputs_are_exact_successors(self) -> None:
        self.assertEqual(BUILDER.ARTIFACT_ID, "debian13-p2-gaming-v0.6")
        self.assertEqual(BUILDER.OUTPUT_NAME, "r46h-debian13-p2-gaming-v0.6")
        self.assertEqual(BUILDER.VERSION_TEXT, "v0.6")
        self.assertEqual(BUILDER.GAMING_PAYLOAD_VERSION_TEXT, "v0.5")
        self.assertEqual(BUILDER.EXTRA_BUILD_ENVIRONMENT, {})
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO, {})
        self.assertEqual(BUILDER.IMAGE_SIZE, 10_716_877_312)
        self.assertEqual(BUILDER.FS_TAIL_SIZE, 512)
        self.assertEqual(BUILDER.BASE_FS_UUID, "d3130005-46a4-4d56-9001-000000000005")
        self.assertEqual(BUILDER.FS_UUID, "d3130006-46a4-4d56-9001-000000000006")
        self.assertEqual(
            BUILDER.BASE_IMAGE_SHA256,
            "ee7d402c06a750081b4c588c5162cca44d0e07fa4b544d5a59bef7629722aeca",
        )
        self.assertEqual(
            BUILDER.GAMING_ARCHIVE_SHA256,
            "22bbbe33f6d96b170aebb886c1aa40e2596073e2609b2bdfa93eeb1b42377e17",
        )
        self.assertEqual(BUILDER.GAMING_PAYLOAD_ID, "r46h-gaming-mvp-v0.5")
        self.assertEqual(BUILDER.KERNEL_RELEASE, "6.12.99-r46h-mainline-v0.15-gaming-product")

    def test_alsa_override_is_the_one_line_upstream_fix(self) -> None:
        text = RULE.read_text(encoding="utf-8")
        self.assertEqual(hashlib.sha256(RULE.read_bytes()).hexdigest(), BUILDER.ALSA_OVERRIDE_RULE_SHA256)
        self.assertEqual(text.count('LABEL="alsa_restore_go"'), 1)
        self.assertEqual(text.count('LABEL="alsa_restore_std"'), 1)
        self.assertEqual(text.count('GOTO="alsa_restore_std"'), 2)
        self.assertIn("f90124c73edd050b24961197a4abcf17e53b41a8", README.read_text())

    def test_overlay_is_bounded_and_preserves_package_file(self) -> None:
        script = IMAGE_TOOL.read_text(encoding="utf-8")
        for marker in (
            "r46h-volume-keys.service",
            "gaming-mvp-v0.5-installed",
            "rm %s\\n' \"$OLD_RECEIPT\"",
            "successor_method=offline-debugfs-bounded-overlay",
            "alsa_override_upstream_commit=f90124c73edd050b24961197a4abcf17e53b41a8",
            "udevadm verify --root=",
            "systemd-analyze verify --man=no",
            "e2fsck -f -n",
            "tune2fs -U",
            "Fast link dest:",
        ):
            self.assertIn(marker, script)
        self.assertIn("dump_image_file \"$VENDOR_RULE\"", script)
        self.assertNotIn("rm $VENDOR_RULE", script)
        self.assertNotIn("rm \"$VENDOR_RULE\"", script)
        for forbidden in ("/dev/disk", "dd if=", "mke2fs ", "mkfs.ext", "curl ", "wget "):
            self.assertNotIn(forbidden, script)
        self.assertNotRegex(script, r"(?m)^\s*saveenv\b")

    def test_every_installer_product_file_has_a_fixed_destination(self) -> None:
        script = IMAGE_TOOL.read_text(encoding="utf-8")
        for relative in BUILDER.PAYLOAD_FILES:
            self.assertIn(relative, script)
        self.assertIn("/etc/fstab|0100644|existing", script)
        self.assertIn("/usr/local/libexec/r46h-volume-keys|0100755|new", script)
        self.assertIn("/etc/systemd/system/r46h-volume-keys.service|0100644|new", script)

    def test_builder_is_networkless_host_only_and_reproducible(self) -> None:
        source = BUILDER_PATH.read_text(encoding="utf-8")
        self.assertIn('"--network",\n        "none"', source)
        self.assertIn('"host-only-not-authorized-for-media-write"', source)
        self.assertIn('run_image_tool(\n            docker,\n            "apply"', source)
        self.assertIn(
            'f"second p2 {VERSION_TEXT} composition is not byte-reproducible"',
            source,
        )
        self.assertIn('run_image_tool(\n            docker,\n            "verify"', source)
        self.assertIn('["/bin/cp", "-c"', source)
        self.assertNotIn("generate-debian13-write-plan", source)
        self.assertNotIn("execute-write", source)
        self.assertNotIn('open("/dev/', source)

    def test_source_scope_and_external_cleanup_are_explicit(self) -> None:
        source = BUILDER_PATH.read_text(encoding="utf-8")
        for relative in BUILDER.SOURCE_PATHS:
            self.assertIn(f'"{relative}"', source)
        self.assertIn('OUTPUT_ROOT / ".cache/r46h-debian13-gaming-rootfs-v06"', source)
        self.assertIn(
            'f"p2 {VERSION_TEXT} source scope must be committed and clean"', source
        )
        self.assertIn("shutil.rmtree(work, ignore_errors=True)", source)
        self.assertIn("renameatx_np", source)
        self.assertIn("0x00000004", source)

    def test_runtime_identity_transformations_are_exact(self) -> None:
        script = IMAGE_TOOL.read_text(encoding="utf-8")
        self.assertIn("s/debian13-p2-gaming-v0\\.5/debian13-p2-gaming-v0.6/g", script)
        self.assertIn('s/$BASE_FS_UUID/$FS_UUID/g', script)
        self.assertEqual(
            BUILDER.FINAL_FIRSTBOOT_SHA256,
            "3c065d08ee2ee89d48fba0b4432662dd9d51e3e5d7a06212a854c758d55b504c",
        )
        self.assertEqual(
            BUILDER.FINAL_ROOTFS_SMOKE_SHA256,
            "825e7a12667770f83d0e0ba79363a4d4b2ae6c5fab068aaa1eb4b5d7aa3034c7",
        )

    def test_safe_payload_extraction_accepts_regular_root_owned_members(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "payload.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                directory = tarfile.TarInfo(BUILDER.GAMING_PAYLOAD_ID)
                directory.type = tarfile.DIRTYPE
                directory.mode = 0o700
                directory.uid = directory.gid = 0
                archive.addfile(directory)
                member = tarfile.TarInfo(f"{BUILDER.GAMING_PAYLOAD_ID}/file")
                payload = b"payload\n"
                member.size = len(payload)
                member.mode = 0o600
                member.uid = member.gid = 0
                archive.addfile(member, io.BytesIO(payload))
            extracted = BUILDER.safe_extract_payload(archive_path, root / "extracted")
            self.assertEqual((extracted / "file").read_bytes(), payload)
            self.assertEqual(stat.S_IMODE((extracted / "file").stat().st_mode), 0o600)

    def test_safe_payload_extraction_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "payload.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                member = tarfile.TarInfo(f"{BUILDER.GAMING_PAYLOAD_ID}/../escape")
                payload = b"escape\n"
                member.size = len(payload)
                member.mode = 0o600
                member.uid = member.gid = 0
                archive.addfile(member, io.BytesIO(payload))
            with self.assertRaisesRegex(BUILDER.BuildError, "unsafe gaming archive member"):
                BUILDER.safe_extract_payload(archive_path, root / "extracted")
            self.assertFalse((root / "escape").exists())

    def test_ext4_guard_requires_magic_and_zero_tail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "image.ext4"
            payload = bytearray(2048)
            payload[1024 + 56 : 1024 + 58] = b"\x53\xef"
            image.write_bytes(payload)
            BUILDER.require_ext4_superblock(image)
            payload[-1] = 1
            image.write_bytes(payload)
            with self.assertRaisesRegex(BUILDER.BuildError, "tail is not zero-filled"):
                BUILDER.require_ext4_superblock(image)

    def test_readme_keeps_evidence_and_partition_boundaries_explicit(self) -> None:
        text = README.read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        for marker in (
            "HOST ARTIFACT + P2 MEDIA READBACK + PRODUCT PHYSICAL PASS / DIAGNOSTIC PAYLOAD TARGET PASS / SUCCESSOR ARTIFACT OPEN",
            "host-only",
            "two independent private clones",
            "same-basename `/etc` rule",
            "p2-only",
            "This regression rewrote neither p1 nor p3",
            "b8ec9371a0e3cb5bb66cd5dca80ca635372cf38855aed4ecc6a650ecdf3049f9",
            "36c12c618995e426cbe54aebf9e246e1f5b41a00a15dc6fe4e022c31c4d6c42e",
            "4ac3a525264fcab7efda804c147f8e77604cbee82847d504de7e359258ca4bee",
            "WRITE_COMPLETE",
            "safe_to_boot=yes",
            "p3 stayed unmounted and outside the plan",
            "session-20260830T051623Z-35309-7bab6288-00a1-42c8-ae1c-eb3c50da1b18",
            "gaming-product-v06-firstboot-20260830T055033Z.bin",
            "95,853 bytes",
            "a8957222ae7c1359b455c0ea3faf1330477b1219ca55123beb5bc905c77214a6",
            "SDR104/150 MHz",
            "/roms/nes/1944.zip",
            "systemd-shutdown[1]: Powering off.",
            "R46H_GAME_UI result=fail status=130 mixer_restored=yes process_cleanup=pass",
            "diagnostic helper failure",
            "guarded Wi-Fi update",
            "p1 was unchanged, p3 stayed read-only",
            "successor p2/release artifact",
        ):
            self.assertIn(marker, normalized)
        self.assertIn("never touches a block device, p1, p3", normalized)
        self.assertIn("`/dev/disk4` name is evidence only", normalized)


if __name__ == "__main__":
    unittest.main()
