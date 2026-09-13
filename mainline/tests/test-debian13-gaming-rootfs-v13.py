#!/usr/bin/env python3
"""Focused host gates for the PPSSPP R46H gaming p2 v0.13."""

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
BUILDER_PATH = REPO / "mainline/scripts/build-debian13-gaming-rootfs-v13.py"
SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v13", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
WRAPPER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = WRAPPER
SPEC.loader.exec_module(WRAPPER)
BUILDER = WRAPPER.BASE
ROOT = REPO / "mainline/rootfs-debian13-gaming-v13"
IMAGE_TOOL = ROOT / "image-in-container.sh"
PPSSPP = REPO / "mainline/gaming-ppsspp"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Debian13GamingRootfsV13Tests(unittest.TestCase):
    def test_identity_is_exact_v12_successor(self) -> None:
        self.assertEqual(BUILDER.ARTIFACT_ID, "debian13-p2-gaming-v0.13")
        self.assertEqual(BUILDER.BASE_FS_UUID, "d3130012-46a4-4d56-9001-000000000012")
        self.assertEqual(BUILDER.FS_UUID, "d3130013-46a4-4d56-9001-000000000013")
        self.assertEqual(BUILDER.FS_LABEL, "R46H_GAMING_V13")
        self.assertEqual(
            BUILDER.BASE_IMAGE_SHA256,
            "af3235742a0324453a6193bc0c3ec0e149fffcf9f6c0c22dba4e2f2e082a9111",
        )
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["consolidated_system_count"], "12")
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["consolidated_media_link_count"], "6087")
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["consolidated_media_link_delta"], "5")
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["ppsspp_host_load_samples"], "6")
        self.assertEqual(
            BUILDER.EXTRA_BUILD_ENVIRONMENT["ES_DE_RECEIPT_SHA256"],
            "75267ae9b44d4c40b15a3485fd220501cfa10aa005626ebe31709b17c9379099",
        )

    def test_eleven_local_inputs_are_exact(self) -> None:
        self.assertEqual(
            [item[0] for item in WRAPPER.EXTRA_INPUTS],
            [
                "r46h-ppsspp-libretro-v1.20.4.tar.gz",
                "gamelist.psp.xml",
                "legacy-media-links.tsv",
                "core-options.v12.cfg",
                "r46h-firstboot.v12",
                "es-de-retroarch.v12.cfg",
                "r46h-es-de-ui.v12",
                "r46h-screenshot.v12",
                "r46h-rootfs-smoke.v12",
                "system-links.v12.tsv",
                "es-de-systems.v12.xml",
            ],
        )
        for name, path, size, digest in WRAPPER.EXTRA_INPUTS:
            with self.subTest(name=name):
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(path.stat().st_size, size)
                self.assertEqual(sha256(path), digest)

    def test_composite_configs_are_exact(self) -> None:
        inputs = {name: path for name, path, _size, _digest in WRAPPER.EXTRA_INPUTS}
        systems = inputs["es-de-systems.v12.xml"].read_bytes().replace(
            b"</systemList>\n", (PPSSPP / "es-system.psp.xml").read_bytes() + b"</systemList>\n"
        )
        links = inputs["system-links.v12.tsv"].read_bytes() + (
            PPSSPP / "system-link.psp.tsv"
        ).read_bytes()
        append = inputs["es-de-retroarch.v12.cfg"].read_bytes() + (
            b'system_directory = "/usr/share/r46h/libretro-system"\n'
        )
        options = inputs["core-options.v12.cfg"].read_bytes() + (
            PPSSPP / "core-options.cfg"
        ).read_bytes()
        expected = BUILDER.EXTRA_BUILD_ENVIRONMENT
        self.assertEqual(hashlib.sha256(systems).hexdigest(), expected["ES_DE_SYSTEMS_SHA256"])
        self.assertEqual(hashlib.sha256(links).hexdigest(), expected["SYSTEM_LINKS_SHA256"])
        self.assertEqual(hashlib.sha256(append).hexdigest(), expected["RETROARCH_APPEND_SHA256"])
        self.assertEqual(hashlib.sha256(options).hexdigest(), expected["CORE_OPTIONS_SHA256"])
        self.assertEqual(len(ET.fromstring(systems).findall("system")), 12)
        self.assertEqual(len(ET.parse(inputs["gamelist.psp.xml"]).getroot().findall("game")), 6)

    def test_generated_runtime_identities_are_reproducible(self) -> None:
        inputs = {name: path for name, path, _size, _digest in WRAPPER.EXTRA_INPUTS}
        env = BUILDER.EXTRA_BUILD_ENVIRONMENT
        command = [
            "awk",
            "-v", f"base_uuid={BUILDER.BASE_FS_UUID}",
            "-v", f"uuid={BUILDER.FS_UUID}",
            "-v", f"base_systems={env['BASE_ES_DE_SYSTEMS_SHA256']}",
            "-v", f"systems={env['ES_DE_SYSTEMS_SHA256']}",
            "-v", f"base_append={env['BASE_RETROARCH_APPEND_SHA256']}",
            "-v", f"append={env['RETROARCH_APPEND_SHA256']}",
            "-v", f"fbneo_hash={env['FBNEO_FULL_CORE_SHA256']}",
            "-v", f"core_hash={env['PPSSPP_CORE_SHA256']}",
            "-v", f"assets_hash={env['PPSSPP_ASSETS_MANIFEST_SHA256']}",
            "-f", str(PPSSPP / "transform-es-de-runner.awk"),
            str(inputs["r46h-es-de-ui.v12"]),
        ]
        runner = subprocess.run(command, check=True, capture_output=True).stdout
        self.assertEqual(hashlib.sha256(runner).hexdigest(), env["ES_DE_RUNNER_SHA256"])
        screenshot = inputs["r46h-screenshot.v12"].read_bytes().replace(
            BUILDER.BASE_FS_UUID.encode(), BUILDER.FS_UUID.encode()
        ).replace(env["BASE_ES_DE_RUNNER_SHA256"].encode(), env["ES_DE_RUNNER_SHA256"].encode())
        firstboot = inputs["r46h-firstboot.v12"].read_bytes().replace(b"v0.12", b"v0.13")
        smoke = inputs["r46h-rootfs-smoke.v12"].read_bytes().replace(
            BUILDER.BASE_FS_UUID.encode(), BUILDER.FS_UUID.encode()
        ).replace(b"v0.12", b"v0.13")
        self.assertEqual(hashlib.sha256(screenshot).hexdigest(), env["SCREENSHOT_SHA256"])
        self.assertEqual(hashlib.sha256(firstboot).hexdigest(), BUILDER.FINAL_FIRSTBOOT_SHA256)
        self.assertEqual(hashlib.sha256(smoke).hexdigest(), BUILDER.FINAL_ROOTFS_SMOKE_SHA256)

    def test_media_manifest_is_the_exact_five_link_successor(self) -> None:
        manifest = WRAPPER.EXTRA_INPUTS[2][1].read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(manifest), 6088)
        self.assertEqual(manifest, sorted(set(manifest)))
        self.assertEqual(sum(line.startswith("psp/") for line in manifest), 5)
        old = REPO / "mainline/out/r46h-gaming-es-de-media-v0.2/legacy-media-links.tsv"
        retained = [line for line in manifest if not line.startswith("psp/")]
        self.assertEqual(("\n".join(retained) + "\n").encode(), old.read_bytes())

    def test_image_overlay_is_bounded_and_networkless(self) -> None:
        script = IMAGE_TOOL.read_text(encoding="utf-8")
        for required in (
            "base already contains the PPSSPP core",
            "/usr/local/libexec/ppsspp_libretro.so",
            "readonly PPSSPP_ASSETS=$PPSSPP_SYSTEM/PPSSPP",
            "PPSSPP asset count changed",
            "consolidated_system_count=12",
            "consolidated_media_link_count=6087",
            "ppsspp_host_load_samples=6",
            "R46H_V13_MEDIA_VERIFY_RESULT=pass",
            "R46H_V13_PPSSPP_VERIFY_RESULT=pass",
            "path_is_absent /home/ark/.ssh/authorized_keys",
            "R46H_V13_PRODUCT_VERIFY_RESULT=pass",
        ):
            self.assertIn(required, script)
        for evidence in (
            "INDEPENDENT-MEDIA-VERIFY.txt",
            "INDEPENDENT-PPSSPP-VERIFY.txt",
        ):
            self.assertIn(evidence, BUILDER.REQUIRED_STAGE_FILES)
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
            "HOST PASS / MEDIA + PHYSICAL OPEN",
            "starts from exact p2 v0.12",
            "writes no block device",
            "six retained ISO/CSO/PBP files",
            "5eac9494cadd106aece559169f984bcf1565b3a2aa48383f73eabdfe4d473098",
            "Keep p1 and p3 outside the plan",
        ):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
