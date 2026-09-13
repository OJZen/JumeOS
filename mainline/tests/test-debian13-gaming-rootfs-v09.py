#!/usr/bin/env python3
"""Focused host gates for the full-FBNeo R46H gaming p2 v0.9."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import stat
import subprocess
import sys
import unittest


REPO = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO / "mainline/scripts/build-debian13-gaming-rootfs-v09.py"
SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v09", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
WRAPPER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = WRAPPER
SPEC.loader.exec_module(WRAPPER)
BUILDER = WRAPPER.BASE
ROOT = REPO / "mainline/rootfs-debian13-gaming-v09"
IMAGE_TOOL = ROOT / "image-in-container.sh"
PAIR_TOOL = ROOT / "pair-remote-key.sh"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Debian13GamingRootfsV09Tests(unittest.TestCase):
    def test_identity_is_exact_v08_successor(self) -> None:
        self.assertEqual(BUILDER.ARTIFACT_ID, "debian13-p2-gaming-v0.9")
        self.assertEqual(BUILDER.BASE_FS_UUID, "d3130008-46a4-4d56-9001-000000000008")
        self.assertEqual(BUILDER.FS_UUID, "d3130009-46a4-4d56-9001-000000000009")
        self.assertEqual(BUILDER.FS_LABEL, "R46H_GAMING_V09")
        self.assertEqual(
            BUILDER.BASE_IMAGE_SHA256,
            "da8798c85864fc5ec3abc2cc940cbbbce737090f6281c19d92e301d95bf7247f",
        )
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["consolidated_system_count"], "8")
        self.assertEqual(
            BUILDER.EXTRA_BUILD_ENVIRONMENT["GAMING_PAYLOAD_ID"],
            "r46h-gaming-mvp-v0.6",
        )
        self.assertIsNotNone(
            BUILDER.STAGE_RE.fullmatch(
                ".r46h-debian13-p2-gaming-v0.9.tmp.native_name"
            )
        )

    def test_three_local_inputs_are_exact(self) -> None:
        self.assertEqual(len(WRAPPER.EXTRA_INPUTS), 3)
        for name, path, size, digest in WRAPPER.EXTRA_INPUTS:
            with self.subTest(name=name):
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(path.stat().st_size, size)
                self.assertEqual(sha256(path), digest)

    def test_generated_system_and_runner_identities_are_reproducible(self) -> None:
        feature = REPO / "mainline/gaming-fbneo-full"
        base_systems = (REPO / "mainline/gaming-es-de/es_systems.xml").read_text()
        fragment = (feature / "es-system.arcade.xml").read_text()
        systems = base_systems.removesuffix("</systemList>\n") + fragment + "</systemList>\n"
        self.assertEqual(
            hashlib.sha256(systems.encode()).hexdigest(),
            BUILDER.EXTRA_BUILD_ENVIRONMENT["ES_DE_SYSTEMS_SHA256"],
        )
        links = (
            REPO / "mainline/gaming-es-de/system-links.tsv"
        ).read_bytes() + (feature / "system-link.arcade.tsv").read_bytes()
        self.assertEqual(
            hashlib.sha256(links).hexdigest(),
            BUILDER.EXTRA_BUILD_ENVIRONMENT["SYSTEM_LINKS_SHA256"],
        )

        runner = (REPO / "mainline/gaming-es-de/r46h-es-de-ui").read_text()
        runner = runner.replace(
            "  /usr/local/libexec/fbneo_neogeo_libretro.so; do",
            "  /usr/local/libexec/fbneo_neogeo_libretro.so \\\n"
            "  /usr/local/libexec/fbneo_libretro.so; do",
        ).replace(
            "d3130007-46a4-4d56-9001-000000000007", BUILDER.FS_UUID
        ).replace(
            "1f451723d4ce1062157eb0e041ff4c098c5adea98c61e87ddf3cb784dfe630f0",
            BUILDER.EXTRA_BUILD_ENVIRONMENT["ES_DE_SYSTEMS_SHA256"],
        ).replace("systems=7", "systems=8")
        full_constants = (
            "readonly FBNEO_FULL_CORE=/usr/local/libexec/fbneo_libretro.so\n"
            "readonly FBNEO_FULL_CORE_SHA256="
            f"{BUILDER.EXTRA_BUILD_ENVIRONMENT['FBNEO_FULL_CORE_SHA256']}\n"
        )
        runner = runner.replace(
            "readonly FBNEO_CORE_SHA256=8bb17a551f3eeeb384ab00a5c5375d30eb63807afe5b6c1ba1d3f78220732bdb\n",
            "readonly FBNEO_CORE_SHA256=8bb17a551f3eeeb384ab00a5c5375d30eb63807afe5b6c1ba1d3f78220732bdb\n"
            + full_constants,
        ).replace(
            '  "$FBNEO_CORE:$FBNEO_CORE_SHA256" \\\n',
            '  "$FBNEO_CORE:$FBNEO_CORE_SHA256" \\\n'
            '  "$FBNEO_FULL_CORE:$FBNEO_FULL_CORE_SHA256" \\\n',
        )
        self.assertEqual(
            hashlib.sha256(runner.encode()).hexdigest(),
            BUILDER.EXTRA_BUILD_ENVIRONMENT["ES_DE_RUNNER_SHA256"],
        )

    def test_identity_script_transformations_are_exact(self) -> None:
        firstboot = WRAPPER.EXTRA_INPUTS[1][1].read_bytes().replace(b"v0.8", b"v0.9")
        smoke = WRAPPER.EXTRA_INPUTS[2][1].read_bytes().replace(
            BUILDER.BASE_FS_UUID.encode(), BUILDER.FS_UUID.encode()
        ).replace(b"v0.8", b"v0.9")
        self.assertEqual(hashlib.sha256(firstboot).hexdigest(), BUILDER.FINAL_FIRSTBOOT_SHA256)
        self.assertEqual(hashlib.sha256(smoke).hexdigest(), BUILDER.FINAL_ROOTFS_SMOKE_SHA256)

    def test_image_overlay_is_bounded_and_networkless(self) -> None:
        script = IMAGE_TOOL.read_text(encoding="utf-8")
        for required in (
            "base already contains full FBNeo core",
            "base already exposes Arcade",
            "/usr/local/libexec/fbneo_libretro.so",
            "arcade_host_load_samples=11",
            "consolidated_system_count=8",
            "path_is_absent /home/ark/.ssh/authorized_keys",
            "R46H_V09_PRODUCT_VERIFY_RESULT=pass",
        ):
            self.assertIn(required, script)
        for forbidden in ("/dev/disk", "dd if=", "mkfs.ext", "mke2fs ", "curl ", "wget "):
            self.assertNotIn(forbidden, script)
        self.assertNotRegex(script, r"(?m)^\s*saveenv\b")

    def test_pairing_remains_one_restricted_key(self) -> None:
        script = PAIR_TOOL.read_text(encoding="utf-8")
        for required in (
            "EXPECTED_UUID=d3130009-46a4-4d56-9001-000000000009",
            "only one OpenSSH ED25519 public key is accepted",
            'restrict,command=\\"/usr/local/bin/r46h-screenshot-ssh\\"',
            "R46H_REMOTE_PAIR result=pass",
        ):
            self.assertIn(required, script)

    def test_entry_points_are_valid_and_executable(self) -> None:
        for path in (IMAGE_TOOL, PAIR_TOOL):
            self.assertEqual(subprocess.run(["/bin/bash", "-n", str(path)]).returncode, 0)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755)
        compile(BUILDER_PATH.read_text(encoding="utf-8"), str(BUILDER_PATH), "exec")

    def test_readme_keeps_host_media_physical_boundaries(self) -> None:
        text = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
        for required in (
            "HOST CANDIDATE / MEDIA + PHYSICAL OPEN",
            "9b5bf248c39121ad2cfde2d719648469442e9c89f194cfcfca3674336b2e0ea5",
            "writes no block device",
            "broad content compatibility remains open",
            "Keep p1 and p3 outside the plan",
            "public key remains deployment state, not image content",
        ):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
