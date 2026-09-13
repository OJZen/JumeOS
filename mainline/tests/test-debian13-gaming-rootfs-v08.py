#!/usr/bin/env python3
"""Focused host gates for the consolidated R46H gaming p2 v0.8."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


REPO = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO / "mainline/scripts/build-debian13-gaming-rootfs-v08.py"
SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v08", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
WRAPPER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = WRAPPER
SPEC.loader.exec_module(WRAPPER)
BUILDER = WRAPPER.BASE
ROOT = REPO / "mainline/rootfs-debian13-gaming-v08"
IMAGE_TOOL = ROOT / "image-in-container.sh"
PAIR_TOOL = ROOT / "pair-remote-key.sh"
README = ROOT / "README.md"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


class Debian13GamingRootfsV08Tests(unittest.TestCase):
    def test_identity_is_exact_v07_successor(self) -> None:
        self.assertEqual(BUILDER.ARTIFACT_ID, "debian13-p2-gaming-v0.8")
        self.assertEqual(BUILDER.OUTPUT_NAME, "r46h-debian13-p2-gaming-v0.8")
        self.assertEqual(BUILDER.IMAGE_SIZE, 10_716_877_312)
        self.assertEqual(BUILDER.BASE_FS_UUID, "d3130007-46a4-4d56-9001-000000000007")
        self.assertEqual(BUILDER.FS_UUID, "d3130008-46a4-4d56-9001-000000000008")
        self.assertEqual(BUILDER.FS_LABEL, "R46H_GAMING_V08")
        self.assertEqual(
            BUILDER.BASE_IMAGE_SHA256,
            "17530b491eaf7edd60cb0b499cc0c920af7399673bf9296f30c5753bc1ca7180",
        )

    def test_five_local_product_inputs_are_exact(self) -> None:
        self.assertEqual(len(WRAPPER.EXTRA_INPUTS), 5)
        for name, path, size, digest in WRAPPER.EXTRA_INPUTS:
            with self.subTest(name=name):
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(path.stat().st_size, size)
                self.assertEqual(sha256(path), digest)
        self.assertEqual(
            BUILDER.EXTRA_BUILD_INFO["remote_pairing"],
            "required-after-image-write",
        )

    def test_uuid_bound_runtime_transformations_are_pinned(self) -> None:
        old_uuid = b"d3130007-46a4-4d56-9001-000000000007"
        new_uuid = b"d3130008-46a4-4d56-9001-000000000008"
        old_runner_hash = BUILDER.EXTRA_BUILD_ENVIRONMENT["ES_DE_RUNNER_BASE_SHA256"]
        new_runner_hash = BUILDER.EXTRA_BUILD_ENVIRONMENT["ES_DE_RUNNER_SHA256"]
        runner = (REPO / "mainline/gaming-es-de/r46h-es-de-ui").read_bytes().replace(
            old_uuid, new_uuid
        )
        self.assertEqual(hashlib.sha256(runner).hexdigest(), new_runner_hash)
        screenshot = (REPO / "mainline/gaming-remote-screen/r46h-screenshot").read_bytes()
        screenshot = screenshot.replace(old_uuid, new_uuid).replace(
            old_runner_hash.encode(), new_runner_hash.encode()
        )
        self.assertEqual(
            hashlib.sha256(screenshot).hexdigest(),
            BUILDER.EXTRA_BUILD_ENVIRONMENT["SCREENSHOT_SHA256"],
        )

    def test_direct_product_omits_migration_rollback_and_credentials(self) -> None:
        script = IMAGE_TOOL.read_text(encoding="utf-8")
        for required in (
            "/opt/r46h/es-de",
            "/usr/local/libexec/fbneo_neogeo_libretro.so",
            "/usr/local/libexec/r46h-drm-capture",
            "/usr/local/libexec/r46h-remote-input",
            '"$PAYLOAD/files/r46h-input-bridge"',
            '"$PAYLOAD/files/r46h-gaming-input-ready"',
            "/usr/local/bin/r46h-screenshot-ssh",
            "/etc/sudoers.d/r46h-remote-screen",
            "media_count == 3417",
            "'home/ark/.config'",
            "[[ $relative == home/ark/* ]] && { uid=1000; gid=1000; }",
            "od -An -tx1 -j18 -N2",
            "neogeo_bios_sha256=d2d8ab5d5fc5ce41978e40c8db2984d8dd0a37e60c712e20961b80fdbb4c9936",
            "path_is_absent /home/ark/.ssh/authorized_keys",
            "migration_rollback_state=omitted-whole-p2-rollback",
        ):
            self.assertIn(required, script)
        self.assertNotIn("operator.pub", script)
        self.assertNotIn("PRIVATE KEY", script)

    def test_pairing_is_one_restricted_ed25519_key(self) -> None:
        script = PAIR_TOOL.read_text(encoding="utf-8")
        for required in (
            "EXPECTED_UUID=d3130008-46a4-4d56-9001-000000000008",
            "only one OpenSSH ED25519 public key is accepted",
            'restrict,command=\\"/usr/local/bin/r46h-screenshot-ssh\\"',
            "visudo -cf",
            "public_key_sha256=",
            "R46H_REMOTE_PAIR result=pass",
        ):
            self.assertIn(required, script)
        for forbidden in ("ssh-rsa", "no-strict-host-key", "PasswordAuthentication=yes"):
            self.assertNotIn(forbidden, script)

    def test_builder_remains_networkless_reproducible_and_host_only(self) -> None:
        base_source = (REPO / WRAPPER.BASE_BUILDER_RELATIVE).read_text(encoding="utf-8")
        wrapper_source = BUILDER_PATH.read_text(encoding="utf-8")
        self.assertIn('"--network",\n        "none"', base_source)
        self.assertIn("second p2 {VERSION_TEXT} composition is not byte-reproducible", base_source)
        self.assertNotIn("zip(SOURCE_PATHS, entries, strict=True)", base_source)
        self.assertNotIn("zip(sums, expected_names, strict=True)", base_source)
        self.assertEqual(BUILDER.ARTIFACT_STATUS, "host-only-no-media-operation-performed")
        self.assertNotIn("/dev/disk", wrapper_source)
        self.assertNotIn("subprocess.run", wrapper_source)
        self.assertIn("PRODUCT-INPUTS.sha256", BUILDER.REQUIRED_STAGE_FILES)
        self.assertIn("INDEPENDENT-PRODUCT-VERIFY.txt", BUILDER.REQUIRED_STAGE_FILES)

    def test_scripts_are_valid_and_have_no_media_write_or_network_path(self) -> None:
        for script in (IMAGE_TOOL, PAIR_TOOL):
            with self.subTest(script=script.name):
                self.assertEqual(
                    subprocess.run(["/bin/bash", "-n", str(script)], check=False).returncode,
                    0,
                )
        image_source = IMAGE_TOOL.read_text(encoding="utf-8")
        for forbidden in ("/dev/disk", "dd if=", "mkfs.ext", "mke2fs ", "curl ", "wget ", "apt-get"):
            self.assertNotIn(forbidden, image_source)
        self.assertNotRegex(image_source, r"(?m)^\s*saveenv\b")

    def test_readme_keeps_evidence_boundary_and_deferred_gate(self) -> None:
        normalized = " ".join(README.read_text(encoding="utf-8").split())
        for required in (
            "HOST CANDIDATE / MEDIA + PHYSICAL OPEN",
            "does not modify BOOT, p1 or p3",
            "No operator public key",
            "Two independent compositions must be byte-identical",
            "not permission to reuse an old disk path",
            "Keep p1 and p3 outside the plan",
            "public key is deployment state, not image content",
        ):
            self.assertIn(required, normalized)


if __name__ == "__main__":
    unittest.main()
