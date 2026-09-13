#!/usr/bin/env python3
"""Focused host gates for the Game Gear R46H gaming p2 v0.15."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET


REPO = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO / "mainline/scripts/build-debian13-gaming-rootfs-v15.py"
SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v15", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
WRAPPER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = WRAPPER
SPEC.loader.exec_module(WRAPPER)
BUILDER = WRAPPER.BASE
ROOT = REPO / "mainline/rootfs-debian13-gaming-v15"
IMAGE_TOOL = ROOT / "image-in-container.sh"
GENESIS = REPO / "mainline/gaming-genesisplusgx"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Debian13GamingRootfsV15Tests(unittest.TestCase):
    def test_identity_is_exact_v14_successor(self) -> None:
        self.assertEqual(BUILDER.ARTIFACT_ID, "debian13-p2-gaming-v0.15")
        self.assertEqual(BUILDER.BASE_FS_UUID, "d3130014-46a4-4d56-9001-000000000014")
        self.assertEqual(BUILDER.FS_UUID, "d3130015-46a4-4d56-9001-000000000015")
        self.assertEqual(BUILDER.FS_LABEL, "R46H_GAMING_V15")
        self.assertEqual(BUILDER.BASE_IMAGE_SHA256, "34a52170a7b6d950abd677f7ff3f1c03f87449629047a536a44500efae8efffe")
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["consolidated_system_count"], "14")
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["consolidated_media_link_count"], "6220")
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["consolidated_media_link_delta"], "105")
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["genesisplusgx_host_load_samples"], "105")

    def test_nine_local_inputs_are_exact(self) -> None:
        self.assertEqual(
            [item[0] for item in WRAPPER.EXTRA_INPUTS],
            [
                "libretro-genesisplusgx_1.7.4+git20221128-2_arm64.deb",
                "gamelist.gamegear.xml",
                "legacy-media-links.tsv",
                "r46h-firstboot.v14",
                "r46h-es-de-ui.v14",
                "r46h-screenshot.v14",
                "r46h-rootfs-smoke.v14",
                "system-links.v14.tsv",
                "es-de-systems.v14.xml",
            ],
        )
        for name, path, size, digest in WRAPPER.EXTRA_INPUTS:
            with self.subTest(name=name):
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(path.stat().st_size, size)
                self.assertEqual(sha256(path), digest)

    def test_composite_systems_and_links_are_exact(self) -> None:
        inputs = {name: path for name, path, _size, _digest in WRAPPER.EXTRA_INPUTS}
        systems = inputs["es-de-systems.v14.xml"].read_bytes().replace(
            b"</systemList>\n", GENESIS.joinpath("es-system.gamegear.xml").read_bytes() + b"</systemList>\n"
        )
        links = inputs["system-links.v14.tsv"].read_bytes() + GENESIS.joinpath("system-link.gamegear.tsv").read_bytes()
        expected = BUILDER.EXTRA_BUILD_ENVIRONMENT
        self.assertEqual(hashlib.sha256(systems).hexdigest(), expected["ES_DE_SYSTEMS_SHA256"])
        self.assertEqual(hashlib.sha256(links).hexdigest(), expected["SYSTEM_LINKS_SHA256"])
        self.assertEqual(len(ET.fromstring(systems).findall("system")), 14)
        self.assertEqual(expected["CORE_OPTIONS_SHA256"], expected["BASE_CORE_OPTIONS_SHA256"])

    def test_generated_runtime_identities_are_reproducible(self) -> None:
        inputs = {name: path for name, path, _size, _digest in WRAPPER.EXTRA_INPUTS}
        env = BUILDER.EXTRA_BUILD_ENVIRONMENT
        command = [
            "awk",
            "-v", f"base_uuid={BUILDER.BASE_FS_UUID}",
            "-v", f"uuid={BUILDER.FS_UUID}",
            "-v", f"base_systems={env['BASE_ES_DE_SYSTEMS_SHA256']}",
            "-v", f"systems={env['ES_DE_SYSTEMS_SHA256']}",
            "-v", f"core_hash={env['GENESISPLUSGX_CORE_SHA256']}",
            "-f", str(GENESIS / "transform-es-de-runner.awk"),
            str(inputs["r46h-es-de-ui.v14"]),
        ]
        runner = subprocess.run(command, check=True, capture_output=True).stdout
        self.assertEqual(hashlib.sha256(runner).hexdigest(), env["ES_DE_RUNNER_SHA256"])
        screenshot = inputs["r46h-screenshot.v14"].read_bytes().replace(
            BUILDER.BASE_FS_UUID.encode(), BUILDER.FS_UUID.encode()
        ).replace(env["BASE_ES_DE_RUNNER_SHA256"].encode(), env["ES_DE_RUNNER_SHA256"].encode())
        firstboot = inputs["r46h-firstboot.v14"].read_bytes().replace(b"v0.14", b"v0.15")
        smoke = inputs["r46h-rootfs-smoke.v14"].read_bytes().replace(
            BUILDER.BASE_FS_UUID.encode(), BUILDER.FS_UUID.encode()
        ).replace(b"v0.14", b"v0.15")
        self.assertEqual(hashlib.sha256(screenshot).hexdigest(), env["SCREENSHOT_SHA256"])
        self.assertEqual(hashlib.sha256(firstboot).hexdigest(), BUILDER.FINAL_FIRSTBOOT_SHA256)
        self.assertEqual(hashlib.sha256(smoke).hexdigest(), BUILDER.FINAL_ROOTFS_SMOKE_SHA256)

    def test_media_manifest_is_exact_gamegear_successor(self) -> None:
        manifest = WRAPPER.EXTRA_INPUTS[2][1].read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(manifest), 6221)
        self.assertEqual(manifest, sorted(set(manifest)))
        self.assertEqual(sum(line.startswith("gamegear/") for line in manifest), 105)
        old = REPO / "mainline/out/r46h-gaming-flycast-content-v0.1/legacy-media-links.tsv"
        retained = [line for line in manifest if not line.startswith("gamegear/")]
        self.assertEqual(("\n".join(retained) + "\n").encode(), old.read_bytes())

    def test_image_overlay_is_bounded_and_networkless(self) -> None:
        script = IMAGE_TOOL.read_text(encoding="utf-8")
        for required in (
            "base already contains the Genesis Plus GX core",
            "/usr/local/libexec/genesis_plus_gx_libretro.so",
            "libvorbisfile.so.3.3.8",
            "R46H_V15_MEDIA_VERIFY_RESULT=pass",
            "R46H_V15_GENESISPLUSGX_VERIFY_RESULT=pass",
            "path_is_absent /home/ark/.ssh/authorized_keys",
            "R46H_V15_PRODUCT_VERIFY_RESULT=pass",
        ):
            self.assertIn(required, script)
        self.assertIn("INDEPENDENT-GENESISPLUSGX-VERIFY.txt", BUILDER.REQUIRED_STAGE_FILES)
        for forbidden in ("/dev/disk", "dd if=", "mkfs.ext", "mke2fs ", "curl ", "wget "):
            self.assertNotIn(forbidden, script)
        self.assertNotRegex(script, r"(?m)^\s*saveenv\b")

    def test_entry_points_and_host_boundary_are_valid(self) -> None:
        self.assertEqual(subprocess.run(["/bin/bash", "-n", str(IMAGE_TOOL)]).returncode, 0)
        self.assertEqual(stat.S_IMODE(IMAGE_TOOL.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(BUILDER_PATH.stat().st_mode), 0o755)
        compile(BUILDER_PATH.read_text(encoding="utf-8"), str(BUILDER_PATH), "exec")
        text = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
        for required in (
            "ATTENDED OPEN / DREAMCAST FAIL",
            "successor to exact p2 v0.14",
            "writes no block device",
            "105 audited",
            "BOOT, p1 and p3 stay outside",
            "safe_to_boot=yes",
            "No operator was present",
            "LCD motion, audible output, physical controls and save persistence remain open",
        ):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
