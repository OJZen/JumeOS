#!/usr/bin/env python3
"""Focused host gates for the R46H gaming p2 v0.16 runtime fixes."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import stat
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET


REPO = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO / "mainline/scripts/build-debian13-gaming-rootfs-v16.py"
SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v16", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
WRAPPER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = WRAPPER
SPEC.loader.exec_module(WRAPPER)
BUILDER = WRAPPER.BASE
ROOT = REPO / "mainline/rootfs-debian13-gaming-v16"
IMAGE_TOOL = ROOT / "image-in-container.sh"


class Debian13GamingRootfsV16Tests(unittest.TestCase):
    def test_identity_is_exact_v15_successor(self) -> None:
        self.assertEqual(BUILDER.ARTIFACT_ID, "debian13-p2-gaming-v0.16")
        self.assertEqual(BUILDER.BASE_FS_UUID, "d3130015-46a4-4d56-9001-000000000015")
        self.assertEqual(BUILDER.FS_UUID, "d3130016-46a4-4d56-9001-000000000016")
        self.assertEqual(BUILDER.FS_LABEL, "R46H_GAMING_V16")
        self.assertEqual(BUILDER.BASE_IMAGE_SHA256, "a69c2dafeae76f37a6e582bfdf4887d5714b82a4cf5b3dc7a84e29f36be6e893")
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["consolidated_system_count"], "13")
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["consolidated_media_link_delta"], "0")

    def test_delta_is_only_two_fixes_and_one_hidden_menu(self) -> None:
        source = WRAPPER.REMOTE_INPUT_SOURCE.read_text(encoding="utf-8")
        screenshot = WRAPPER.SCREENSHOT_SOURCE.read_text(encoding="utf-8")
        self.assertIn("-DKEY_HOLD_MILLISECONDS=10", BUILDER_PATH.read_text(encoding="utf-8"))
        self.assertIn("#define KEY_HOLD_MILLISECONDS 100", source)
        self.assertIn("sleep_milliseconds(KEY_HOLD_MILLISECONDS)", source)
        for token in (
            "pgrep -u 1000 -f '^/usr/bin/retroarch( |$)'",
            "pgrep -u 1000 -f '^/opt/r46h/es-de/bin/es-de( |$)'",
            "${#retroarch_pids[@]} <= 1", "${#es_de_pids[@]} <= 1",
            "${#retroarch_pids[@]} + ${#es_de_pids[@]} >= 1",
        ):
            self.assertIn(token, screenshot)
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["remote_input_hold_ms"], "10")
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["dreamcast_menu"], "hidden-known-panfrost-fault")

    def test_dreamcast_fragment_removal_keeps_valid_systems(self) -> None:
        base = REPO / "mainline/out/.cache/r46h-v16-input-audit/es-de-systems.v15.xml"
        if not base.is_file():
            self.skipTest("exact v0.15 systems extraction is unavailable")
        data = WRAPPER.replace_exact(base.read_bytes(), WRAPPER.DREAMCAST_FRAGMENT.read_bytes(), b"", 1, "Dreamcast system")
        systems = ET.fromstring(data).findall("system")
        self.assertEqual(len(systems), 13)
        self.assertNotIn("dreamcast", {system.findtext("name") for system in systems})
        self.assertIn("gamegear", {system.findtext("name") for system in systems})
        self.assertEqual(len(data), WRAPPER.GENERATED_INPUTS[0][1])

    def test_image_overlay_is_bounded_and_networkless(self) -> None:
        script = IMAGE_TOOL.read_text(encoding="utf-8")
        for required in (
            "R46H_V16_PRODUCT_VERIFY_RESULT=pass", "remote_input_hold_ms=10",
            "screenshot_process_guard=anchored-command-line-one-plus-one",
            "dreamcast_menu=hidden-known-panfrost-fault",
            "path_is_absent /home/ark/.ssh/authorized_keys",
        ):
            self.assertIn(required, script)
        for retained in (
            "/usr/local/libexec/flycast_libretro.so",
            "/home/ark/ROMs/dreamcast",
            "/home/ark/ES-DE/gamelists/dreamcast/gamelist.xml",
        ):
            self.assertIn(retained, script)
        for forbidden in ("/dev/disk", "dd if=", "mkfs.ext", "mke2fs ", "curl ", "wget ", "saveenv"):
            self.assertNotIn(forbidden, script)

    def test_entry_points_and_host_boundary_are_valid(self) -> None:
        self.assertEqual(subprocess.run(["/bin/bash", "-n", str(IMAGE_TOOL)]).returncode, 0)
        self.assertEqual(stat.S_IMODE(IMAGE_TOOL.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(BUILDER_PATH.stat().st_mode), 0o755)
        compile(BUILDER_PATH.read_text(encoding="utf-8"), str(BUILDER_PATH), "exec")
        text = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
        for required in (
            "successor to exact p2 v0.15", "writes no block device", "10 ms",
            "ES-DE plus one RetroArch", "Dreamcast", "BOOT, p1 and p3 stay outside",
            "Media proof does not establish R46H behavior",
        ):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
