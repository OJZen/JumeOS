#!/usr/bin/env python3
"""Focused host tests for the consolidated R46H Debian gaming rootfs builder."""

from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import struct
import tarfile
import tempfile
import unittest
import uuid


REPO = Path(__file__).resolve().parents[2]
BUILDER = REPO / "mainline/scripts/build-debian13-gaming-rootfs.py"
ROOT = REPO / "mainline/rootfs-debian13-gaming"
README = ROOT / "README.md"


def load_builder():
    spec = importlib.util.spec_from_file_location("build_debian13_gaming_rootfs", BUILDER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load consolidated gaming rootfs builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_builder()


class Debian13GamingRootfsTests(unittest.TestCase):
    def test_identity_geometry_and_frozen_inputs_are_distinct_from_v01(self) -> None:
        self.assertEqual(MODULE.ARTIFACT_ID, "debian13-p2-gaming-v0.5")
        self.assertEqual(MODULE.OUTPUT_NAME, "r46h-debian13-p2-gaming-v0.5")
        self.assertEqual(MODULE.IMAGE_SIZE, 10_716_877_312)
        self.assertEqual(
            MODULE.FS_BLOCK_SIZE * MODULE.FS_BLOCK_COUNT + MODULE.FS_TAIL_SIZE,
            MODULE.IMAGE_SIZE,
        )
        self.assertEqual(MODULE.FS_UUID, "d3130005-46a4-4d56-9001-000000000005")
        self.assertNotEqual(MODULE.FS_UUID, "d3130001-46a4-4d56-9001-000000000001")
        self.assertEqual(MODULE.KERNEL_RELEASE, "6.12.99-r46h-mainline-v0.15-gaming-product")
        self.assertEqual(
            MODULE.V08_FALLBACK_BUNDLE_SHA256,
            "8c7282a07bdec52b753a8af27d15c6bbc8b71b34d017c3d78a2273fba6cfd09e",
        )
        self.assertEqual(
            MODULE.V10_FALLBACK_BUNDLE_SHA256,
            "c4350520f7ad33ecf7b50f67c42985e2ce26c1c38d050ad50601c3538cebc780",
        )
        self.assertEqual(
            MODULE.V10_FALLBACK_MODULE_TREE_SHA256,
            "a70796c050de93c4c212180addf54a17efe7732d355db2b52d0bfcab6c56cc16",
        )
        self.assertEqual(
            MODULE.KERNEL_BUNDLE_SHA256,
            "748d81cc0e8b9bf353430db1f4ee358bf09dee1d32db85a855961368b58d3fad",
        )
        self.assertEqual(
            MODULE.GAMING_ARCHIVE_SHA256,
            "c192e6301b112e26436836e59fc8b9cf82af85851352d8db1a41bebb942e2c2e",
        )
        self.assertEqual(
            MODULE.GAME_UI_SHA256,
            "867664284d932cd23757b40d7108ed878d3ab8d16f5655956543444619e75ff3",
        )
        self.assertEqual(
            MODULE.SMOKE_CORE_SHA256,
            "a6618fec16ab91fcfbc76497416c4542d1973862affb82f633ee70d600739085",
        )
        self.assertEqual(
            MODULE.STORAGE_AUDIT_SHA256,
            "08ed33dace8a94a6b129d72896c8e6a657b32d15c74d9ecf48df99a9f49ae95c",
        )
        self.assertEqual(
            MODULE.RETROARCH_CONFIG_SHA256,
            "99a45beb148e58e40983773b4f5e26d9fb5d7e1bbbf6a7e714a5c352e43c0dba",
        )
        self.assertEqual(MODULE.KERNEL_IMAGE_SIZE, 41_570_816)
        self.assertEqual(MODULE.KERNEL_DTB_SIZE, 49_518)
        profile = json.loads(MODULE.PROFILE.read_text(encoding="utf-8"))
        self.assertEqual(profile["card"]["root"]["size"], MODULE.IMAGE_SIZE)
        self.assertEqual(profile["card"]["root"]["partuuid"], "c9f931c9-02")

    def test_composer_bakes_accepted_product_state_only(self) -> None:
        script = (ROOT / "compose-in-container.sh").read_text(encoding="utf-8")
        for required in (
            "--no-install-recommends",
            "gaming-mvp-v0.4-installed",
            '"$PAYLOAD/files/retroarch.cfg"',
            "/roms/nes/r46h-nes-smoke.nes",
            "update-alternatives --set regulatory.db",
            "/lib/firmware/regulatory.db-upstream",
            "personal_authorized_keys=absent",
            "diagnostic_input_bridge=absent",
            "product_input_bridge=r46h-gaming-input-bridge-v0.5",
            "systemctl enable r46h-gaming-input.service",
            "systemctl enable r46h-gaming-frontend.service",
            "input_enable_hotkey_btn",
            "input_menu_toggle_btn",
            "policy-rc.d",
            "Nestopia",
            "accepted game UI hotfix mismatch",
            "accepted smoke core hotfix mismatch",
            "accepted storage audit hotfix mismatch",
        ):
            self.assertIn(required, script)
        self.assertIn("[[ ! -e /home/ark/.ssh/authorized_keys", script)
        self.assertNotIn("id_rsa.pub", script)
        self.assertNotIn("public_key_fingerprint", script)
        self.assertIn("readonly PAYLOAD=/run/r46h-gaming-payload", script)
        self.assertNotIn("readonly PAYLOAD=/payload", script)
        self.assertNotIn("gaming-history-fix/retroarch.cfg", script)
        self.assertNotIn("gaming-history-v0.2-installed\" >", script)
        for forbidden in ("curl ", "wget ", "dd if=", "mkfs"):
            self.assertNotIn(forbidden, script)

    def test_ext4_assembler_keeps_fallback_and_adds_exact_product_kernel(self) -> None:
        script = (ROOT / "build-ext4-in-container.sh").read_text(encoding="utf-8")
        self.assertIn(MODULE.V08_FALLBACK_RELEASE, script)
        self.assertIn(MODULE.V10_FALLBACK_RELEASE, script)
        self.assertIn("V08_FALLBACK_BUNDLE", script)
        self.assertIn("V10_FALLBACK_BUNDLE", script)
        self.assertIn('cp -a -- "$V08_FALLBACK_ROOT/rootfs/lib/modules/$V08_FALLBACK_RELEASE"', script)
        self.assertIn('cp -a -- "$V10_FALLBACK_ROOT/rootfs/lib/modules/$V10_FALLBACK_RELEASE"', script)
        self.assertIn("test -f \"$ROOTFS/lib/modules/$V08_FALLBACK_RELEASE/modules.dep\"", script)
        self.assertIn("test -f \"$ROOTFS/lib/modules/$V10_FALLBACK_RELEASE/modules.dep\"", script)
        self.assertIn('cp -a -- "$KERNEL_ROOT/rootfs/lib/modules/$KERNEL_RELEASE"', script)
        self.assertIn("build_id=v0.15-gaming-product", script)
        self.assertIn("PRODUCT-KERNEL-FILES.sha256", script)
        self.assertIn('"$ROOTFS/$product_kernel_rel/IMAGE"', script)
        self.assertIn('"$ROOTFS/$product_kernel_rel/R46H.DTB"', script)
        self.assertIn('"$ROOTFS/$product_kernel_rel/UBOOT-CMDS.txt"', script)
        self.assertNotIn('rm -rf -- "$ROOTFS/lib/modules"', script)
        self.assertIn("systemd-analyze --root=\"$ROOTFS\" verify --man=no", script)
        self.assertIn("r46h-gaming-input.service", script)
        self.assertIn("r46h-gaming-frontend.service", script)
        self.assertIn("e2fsck -f -n", script)
        self.assertIn("find \"$ROOTFS\" -xdev -exec touch -h", script)
        self.assertIn("DEBUGFS-GAMING.txt", script)

    def test_base_runtime_helpers_transform_to_exact_v05_identity(self) -> None:
        base_firstboot = (
            REPO / "mainline/rootfs-debian13/overlay/usr/libexec/r46h-firstboot"
        ).read_text(encoding="utf-8")
        final_firstboot = base_firstboot.replace(
            "debian13-p2-mvp-v0.1", "debian13-p2-gaming-v0.5"
        ).encode()
        self.assertEqual(MODULE.sha256_bytes(final_firstboot), MODULE.FINAL_FIRSTBOOT_SHA256)

        base_smoke = (
            REPO
            / "mainline/rootfs-debian13/overlay/usr/local/sbin/r46h-rootfs-smoke"
        ).read_text(encoding="utf-8")
        final_smoke = (
            base_smoke.replace(MODULE.V08_FALLBACK_RELEASE, MODULE.KERNEL_RELEASE)
            .replace("d3130001-46a4-4d56-9001-000000000001", MODULE.FS_UUID)
            .replace("debian13-p2-mvp-v0.1", "debian13-p2-gaming-v0.5")
            .encode()
        )
        self.assertEqual(MODULE.sha256_bytes(final_smoke), MODULE.FINAL_ROOTFS_SMOKE_SHA256)

    def test_source_scope_and_external_cleanup_are_explicit(self) -> None:
        script = BUILDER.read_text(encoding="utf-8")
        for relative in MODULE.SOURCE_PATHS:
            self.assertIn(f'"{relative}"', script)
        self.assertIn('OUTPUT_ROOT / ".cache/r46h-debian13-gaming-rootfs"', script)
        self.assertIn("shutil.rmtree(work, ignore_errors=True)", script)
        self.assertIn('"--network",\n        "none"', script)
        self.assertIn("source scope must be committed and clean", script)
        self.assertIn("host-only-not-authorized-for-media-write", script)
        self.assertNotIn("generate-debian13-write-plan", script)
        self.assertNotIn("execute-write", script)

    def test_product_uboot_commands_are_exact_one_shot_only(self) -> None:
        path = ROOT / "UBOOT-CMDS.product"
        commands = path.read_text(encoding="ascii")
        self.assertEqual(MODULE.sha256_file(path), MODULE.PRODUCT_UBOOT_COMMANDS_SHA256)
        self.assertIn(MODULE.PRODUCT_KERNEL_DIRECTORY + "/IMAGE", commands)
        self.assertIn(MODULE.PRODUCT_KERNEL_DIRECTORY + "/R46H.DTB", commands)
        self.assertIn("0x27a5200", commands)
        self.assertIn("0xc16e", commands)
        self.assertIn("booti ${loadaddr} - ${dtb_loadaddr}", commands)
        self.assertNotIn("saveenv", commands)
        self.assertNotIn("mmc write", commands)

    def test_safe_payload_extraction_accepts_regular_root_owned_members(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "payload.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                directory = tarfile.TarInfo(MODULE.GAMING_PAYLOAD_ID)
                directory.type = tarfile.DIRTYPE
                directory.mode = 0o700
                directory.uid = directory.gid = 0
                archive.addfile(directory)
                member = tarfile.TarInfo(f"{MODULE.GAMING_PAYLOAD_ID}/file")
                payload = b"payload\n"
                member.size = len(payload)
                member.mode = 0o600
                member.uid = member.gid = 0
                archive.addfile(member, io.BytesIO(payload))
            extracted = MODULE.safe_extract_payload(archive_path, root / "extracted")
            self.assertEqual((extracted / "file").read_bytes(), b"payload\n")
            self.assertEqual(stat.S_IMODE((extracted / "file").stat().st_mode), 0o600)

    def test_safe_payload_extraction_rejects_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive_path = root / "payload.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                member = tarfile.TarInfo(f"{MODULE.GAMING_PAYLOAD_ID}/../escape")
                payload = b"escape\n"
                member.size = len(payload)
                member.mode = 0o600
                member.uid = member.gid = 0
                archive.addfile(member, io.BytesIO(payload))
            with self.assertRaisesRegex(MODULE.BuildError, "unsafe gaming archive path"):
                MODULE.safe_extract_payload(archive_path, root / "extracted")
            self.assertFalse((root / "escape").exists())

    def test_ext4_superblock_requires_new_full_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "superblock.img"
            superblock = bytearray(1024)
            struct.pack_into("<I", superblock, 0x04, MODULE.FS_BLOCK_COUNT)
            struct.pack_into("<I", superblock, 0x18, 2)
            struct.pack_into("<H", superblock, 0x38, 0xEF53)
            struct.pack_into("<H", superblock, 0x3A, 0x0001)
            superblock[0x68:0x78] = uuid.UUID(MODULE.FS_UUID).bytes
            superblock[0x78:0x88] = MODULE.FS_LABEL.encode().ljust(16, b"\0")
            image.write_bytes(b"\0" * 1024 + superblock)
            MODULE.require_ext4_superblock(image)
            superblock[0x68:0x78] = uuid.UUID(
                "d3130001-46a4-4d56-9001-000000000001"
            ).bytes
            image.write_bytes(b"\0" * 1024 + superblock)
            with self.assertRaisesRegex(MODULE.BuildError, "identity mismatch"):
                MODULE.require_ext4_superblock(image)

    def test_atomic_publish_is_no_replace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "source").mkdir()
            (root / "destination").mkdir()
            descriptor = os.open(root, os.O_RDONLY)
            try:
                with self.assertRaises(MODULE.BuildError):
                    MODULE.rename_noreplace(descriptor, "source", "destination")
            finally:
                os.close(descriptor)
            self.assertTrue((root / "source").is_dir())
            self.assertTrue((root / "destination").is_dir())

    def test_runbook_states_evidence_and_deployment_boundaries(self) -> None:
        text = README.read_text(encoding="utf-8")
        normalized = " ".join(text.split())
        for phrase in (
            "HOST-ONLY",
            "does not authorize a TF-card write",
            "p2 v0.5",
            "v0.15",
            "cumulative gaming v0.4",
            "v0.10",
            "four accepted live corrections",
            "Select+X",
            "A2",
            "does not bake any operator SSH public key",
            "does not install the old diagnostic input bridge",
            "p2 one-shot",
            "Wi-Fi/p2 transaction",
            "10,716,877,312",
            "V0.5 MEDIA + FUNCTIONAL PASS WITH V0.17 PERSISTENT COLD PASS",
            "ORIGINAL V0.15 COLD GATE FAIL",
            "FIRST VERSION ACCEPTED",
            "INTEGRATED FULL-CARD ARTIFACT OPEN",
            "015e571c0f0f4a5ebe967a9543d5b68d58cf1e39ea4c6608c5371ec79d7b522f",
            "3b4265849e446ee8566e47fbfb7d7ee4145bdd0d732caa7b5913684b4e4d3034",
            "c84dccd4bff90421c8a4741ebf5598b9ea7f86e619cb22212fefa6615ee97f70",
        ):
            self.assertIn(phrase, normalized)
        self.assertNotIn("safe to boot", text.lower())

    def test_scripts_are_executable_and_parse(self) -> None:
        for path in (
            BUILDER,
            ROOT / "compose-in-container.sh",
            ROOT / "build-ext4-in-container.sh",
        ):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE((ROOT / "UBOOT-CMDS.product").stat().st_mode), 0o644)


if __name__ == "__main__":
    unittest.main()
