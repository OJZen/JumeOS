#!/usr/bin/env python3
"""Focused host gates for the ES-DE media R46H gaming p2 v0.12."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import stat
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET


REPO = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO / "mainline/scripts/build-debian13-gaming-rootfs-v12.py"
SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v12", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
WRAPPER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = WRAPPER
SPEC.loader.exec_module(WRAPPER)
BUILDER = WRAPPER.BASE
ROOT = REPO / "mainline/rootfs-debian13-gaming-v12"
IMAGE_TOOL = ROOT / "image-in-container.sh"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Debian13GamingRootfsV12Tests(unittest.TestCase):
    def test_identity_is_exact_v11_successor(self) -> None:
        self.assertEqual(BUILDER.ARTIFACT_ID, "debian13-p2-gaming-v0.12")
        self.assertEqual(BUILDER.BASE_FS_UUID, "d3130011-46a4-4d56-9001-000000000011")
        self.assertEqual(BUILDER.FS_UUID, "d3130012-46a4-4d56-9001-000000000012")
        self.assertEqual(BUILDER.FS_LABEL, "R46H_GAMING_V12")
        self.assertEqual(
            BUILDER.BASE_IMAGE_SHA256,
            "d84788c682c1f9e8c13c7fdcc1f0ebea25944aa2933b3633dde18a031b2aac60",
        )
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["consolidated_system_count"], "11")
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["consolidated_media_link_count"], "6082")
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["consolidated_media_link_delta"], "74")
        self.assertEqual(
            BUILDER.EXTRA_BUILD_ENVIRONMENT["GAMING_PAYLOAD_ID"],
            "r46h-gaming-mvp-v0.6",
        )
        self.assertIsNotNone(
            BUILDER.STAGE_RE.fullmatch(
                ".r46h-debian13-p2-gaming-v0.12.tmp.native_name"
            )
        )

    def test_six_local_inputs_are_exact(self) -> None:
        self.assertEqual(len(WRAPPER.EXTRA_INPUTS), 6)
        self.assertEqual(
            [item[0] for item in WRAPPER.EXTRA_INPUTS],
            [
                "legacy-media-links.tsv",
                "gamelist.cps2.xml",
                "gamelist.cps3.xml",
                "es_settings.v11.xml",
                "r46h-firstboot.v11",
                "r46h-rootfs-smoke.v11",
            ],
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
        self.assertEqual(len(manifest), 6083)
        self.assertEqual(manifest, sorted(set(manifest)))
        counts: dict[str, int] = {}
        for line in manifest[1:]:
            system = line.split("/", 1)[0]
            counts[system] = counts.get(system, 0) + 1
        self.assertEqual(counts["arcade"], 2543)
        self.assertEqual(counts["cps1"], 48)
        self.assertEqual(counts["cps2"], 62)
        self.assertEqual(counts["cps3"], 12)
        old = REPO / "mainline/out/r46h-gaming-es-de-media-v0.1/legacy-media-links.tsv"
        retained = [
            line for line in manifest if not line.startswith(("cps2/", "cps3/"))
        ]
        self.assertEqual(("\n".join(retained) + "\n").encode(), old.read_bytes())

    def test_filtered_gamelists_and_settings_are_exact(self) -> None:
        for index, system, hidden in ((1, "cps2", 5), (2, "cps3", 3)):
            root = ET.parse(WRAPPER.EXTRA_INPUTS[index][1]).getroot()
            self.assertEqual(len(root.findall("game")), 62 if system == "cps2" else 12)
            self.assertEqual(
                sum(game.findtext("hidden") == "true" for game in root.findall("game")),
                hidden,
            )
        settings = WRAPPER.EXTRA_INPUTS[3][1].read_text(encoding="utf-8")
        settings = settings.replace(
            '<bool name="LegacyGamelistFileLocation" value="true" />',
            '<bool name="LegacyGamelistFileLocation" value="false" />',
        ).replace(
            '<bool name="NavigationSounds" value="false" />\n',
            '<bool name="NavigationSounds" value="false" />\n'
            '<bool name="ShowHiddenGames" value="false" />\n',
        )
        self.assertEqual(
            hashlib.sha256(settings.encode()).hexdigest(),
            BUILDER.EXTRA_BUILD_ENVIRONMENT["SETTINGS_SHA256"],
        )

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
        ).replace("systems=7", "systems=11")
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
        firstboot = WRAPPER.EXTRA_INPUTS[4][1].read_bytes().replace(b"v0.11", b"v0.12")
        smoke = WRAPPER.EXTRA_INPUTS[5][1].read_bytes().replace(
            BUILDER.BASE_FS_UUID.encode(), BUILDER.FS_UUID.encode()
        ).replace(b"v0.11", b"v0.12")
        self.assertEqual(hashlib.sha256(firstboot).hexdigest(), BUILDER.FINAL_FIRSTBOOT_SHA256)
        self.assertEqual(hashlib.sha256(smoke).hexdigest(), BUILDER.FINAL_ROOTFS_SMOKE_SHA256)

    def test_image_overlay_is_bounded_and_networkless(self) -> None:
        script = IMAGE_TOOL.read_text(encoding="utf-8")
        for required in (
            "base Arcade link target mismatch",
            "base CPS1 link target mismatch",
            "base already contains CPS2 system link",
            "gamelist link target mismatch",
            "/usr/local/libexec/fbneo_libretro.so",
            "consolidated_system_count=11",
            "consolidated_media_link_count=6082",
            "consolidated_media_link_delta=74",
            "filtered_cps_failure_count=8",
            "media link readback differs from manifest",
            "R46H_V12_MEDIA_VERIFY_RESULT=pass",
            "path_is_absent /home/ark/.ssh/authorized_keys",
            "R46H_V12_PRODUCT_VERIFY_RESULT=pass",
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
            "57/62 and 9/12 archives",
            "Eight exact incomplete archives",
            "all 6,082 media links",
            "af3235742a0324453a6193bc0c3ec0e149fffcf9f6c0c22dba4e2f2e082a9111",
            "writes no block device",
            "Keep p1 and p3 outside the plan",
            "--artifact-id debian13-p2-gaming-v0.12",
        ):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
