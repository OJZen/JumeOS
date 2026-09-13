#!/usr/bin/env python3
"""Focused host gates for the ES-DE media R46H gaming p2 v0.11."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import stat
import subprocess
import sys
import unittest


REPO = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO / "mainline/scripts/build-debian13-gaming-rootfs-v11.py"
SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v11", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
WRAPPER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = WRAPPER
SPEC.loader.exec_module(WRAPPER)
BUILDER = WRAPPER.BASE
ROOT = REPO / "mainline/rootfs-debian13-gaming-v11"
IMAGE_TOOL = ROOT / "image-in-container.sh"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Debian13GamingRootfsV11Tests(unittest.TestCase):
    def test_identity_is_exact_v10_successor(self) -> None:
        self.assertEqual(BUILDER.ARTIFACT_ID, "debian13-p2-gaming-v0.11")
        self.assertEqual(BUILDER.BASE_FS_UUID, "d3130010-46a4-4d56-9001-000000000010")
        self.assertEqual(BUILDER.FS_UUID, "d3130011-46a4-4d56-9001-000000000011")
        self.assertEqual(BUILDER.FS_LABEL, "R46H_GAMING_V11")
        self.assertEqual(
            BUILDER.BASE_IMAGE_SHA256,
            "71f0da96c972dca90dc1c40fff8ec36a46afb3ad0535fff1584a983575d77adf",
        )
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["consolidated_system_count"], "9")
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["consolidated_media_link_count"], "6008")
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["consolidated_media_link_delta"], "2591")
        self.assertEqual(
            BUILDER.EXTRA_BUILD_ENVIRONMENT["GAMING_PAYLOAD_ID"],
            "r46h-gaming-mvp-v0.6",
        )
        self.assertIsNotNone(
            BUILDER.STAGE_RE.fullmatch(
                ".r46h-debian13-p2-gaming-v0.11.tmp.native_name"
            )
        )

    def test_three_local_inputs_are_exact(self) -> None:
        self.assertEqual(len(WRAPPER.EXTRA_INPUTS), 3)
        self.assertEqual(
            [item[0] for item in WRAPPER.EXTRA_INPUTS],
            ["legacy-media-links.tsv", "r46h-firstboot.v10", "r46h-rootfs-smoke.v10"],
        )
        for name, path, size, digest in WRAPPER.EXTRA_INPUTS:
            with self.subTest(name=name):
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(path.stat().st_size, size)
                self.assertEqual(sha256(path), digest)

    def test_media_manifest_extends_the_exact_accepted_set(self) -> None:
        manifest = WRAPPER.EXTRA_INPUTS[0][1].read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            manifest[0],
            "# destination-relative-to-downloaded_media\tsource-on-read-only-roms",
        )
        self.assertEqual(len(manifest), 6009)
        self.assertEqual(manifest, sorted(set(manifest)))
        counts: dict[str, int] = {}
        for line in manifest[1:]:
            system = line.split("/", 1)[0]
            counts[system] = counts.get(system, 0) + 1
        self.assertEqual(counts["arcade"], 2543)
        self.assertEqual(counts["cps1"], 48)
        old = (REPO / "mainline/out/r46h-gaming-es-de-v0.1/legacy-media-links.tsv")
        retained = [
            line for line in manifest if not line.startswith(("arcade/", "cps1/"))
        ]
        self.assertEqual(("\n".join(retained) + "\n").encode(), old.read_bytes())

    def test_generated_runner_identity_is_reproducible(self) -> None:
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
        ).replace("systems=7", "systems=9")
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
        screenshot = (REPO / "mainline/gaming-remote-screen/r46h-screenshot").read_text()
        screenshot = screenshot.replace(
            "d3130007-46a4-4d56-9001-000000000007", BUILDER.FS_UUID
        ).replace(
            "5b9edd8705d26ac2b58285baee9d2025354a0343936b5360313e664edd5bafa1",
            BUILDER.EXTRA_BUILD_ENVIRONMENT["ES_DE_RUNNER_SHA256"],
        )
        self.assertEqual(
            hashlib.sha256(screenshot.encode()).hexdigest(),
            BUILDER.EXTRA_BUILD_ENVIRONMENT["SCREENSHOT_SHA256"],
        )

    def test_identity_script_transformations_are_exact(self) -> None:
        firstboot = WRAPPER.EXTRA_INPUTS[1][1].read_bytes().replace(b"v0.10", b"v0.11")
        smoke = WRAPPER.EXTRA_INPUTS[2][1].read_bytes().replace(
            BUILDER.BASE_FS_UUID.encode(), BUILDER.FS_UUID.encode()
        ).replace(b"v0.10", b"v0.11")
        self.assertEqual(hashlib.sha256(firstboot).hexdigest(), BUILDER.FINAL_FIRSTBOOT_SHA256)
        self.assertEqual(hashlib.sha256(smoke).hexdigest(), BUILDER.FINAL_ROOTFS_SMOKE_SHA256)

    def test_image_overlay_is_bounded_and_networkless(self) -> None:
        script = IMAGE_TOOL.read_text(encoding="utf-8")
        for required in (
            "base Arcade link target mismatch",
            "base CPS1 link target mismatch",
            "/usr/local/libexec/fbneo_libretro.so",
            "consolidated_system_count=9",
            "consolidated_media_link_count=6008",
            "consolidated_media_link_delta=2591",
            "media link readback differs from manifest",
            "R46H_V11_MEDIA_VERIFY_RESULT=pass",
            "path_is_absent /home/ark/.ssh/authorized_keys",
            "R46H_V11_PRODUCT_VERIFY_RESULT=pass",
        ):
            self.assertIn(required, script)
        self.assertIn("INDEPENDENT-MEDIA-VERIFY.txt", BUILDER.REQUIRED_STAGE_FILES)
        for forbidden in ("/dev/disk", "dd if=", "mkfs.ext", "mke2fs ", "curl ", "wget "):
            self.assertNotIn(forbidden, script)
        self.assertNotRegex(script, r"(?m)^\s*saveenv\b")

    def test_entry_points_are_valid_and_executable(self) -> None:
        self.assertEqual(
            subprocess.run(["/bin/bash", "-n", str(IMAGE_TOOL)]).returncode, 0
        )
        self.assertEqual(stat.S_IMODE(IMAGE_TOOL.stat().st_mode), 0o755)
        compile(BUILDER_PATH.read_text(encoding="utf-8"), str(BUILDER_PATH), "exec")

    def test_readme_keeps_host_media_physical_boundaries(self) -> None:
        text = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
        for required in (
            "MEDIA + PHYSICAL OPEN",
            "6,008 links",
            "2,543 Arcade links and 48 CPS1 images",
            "writes no block device",
            "Keep p1 and p3 outside the plan",
        ):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
