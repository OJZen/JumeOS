#!/usr/bin/env python3
"""Focused host gates for the R46H gaming p2 v0.17 ES-DE fix."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import stat
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET


REPO = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO / "mainline/scripts/build-debian13-gaming-rootfs-v17.py"
SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v17", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
WRAPPER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = WRAPPER
SPEC.loader.exec_module(WRAPPER)
BUILDER = WRAPPER.BASE
ROOT = REPO / "mainline/rootfs-debian13-gaming-v17"
IMAGE_TOOL = ROOT / "image-in-container.sh"


class Debian13GamingRootfsV17Tests(unittest.TestCase):
    def test_identity_is_exact_v16_successor(self) -> None:
        self.assertEqual(BUILDER.ARTIFACT_ID, "debian13-p2-gaming-v0.17")
        self.assertEqual(BUILDER.BASE_FS_UUID, "d3130016-46a4-4d56-9001-000000000016")
        self.assertEqual(BUILDER.FS_UUID, "d3130017-46a4-4d56-9001-000000000017")
        self.assertEqual(BUILDER.FS_LABEL, "R46H_GAMING_V17")
        self.assertEqual(
            BUILDER.BASE_IMAGE_SHA256,
            "21cdfa3af3b96b6233decdc3ca4f8475c0eba946503045a4e86c21c50b8374c4",
        )
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["es_de_systems_scope"], "exclusive-custom")
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["product_input_count"], "6")
        self.assertEqual(
            BUILDER.EXTRA_BUILD_ENVIRONMENT["REMOTE_INPUT_SHA256"],
            BUILDER.EXTRA_BUILD_ENVIRONMENT["BASE_REMOTE_INPUT_SHA256"],
        )

    def test_custom_systems_are_exclusive_and_valid(self) -> None:
        source = BUILDER_PATH.read_text(encoding="utf-8")
        self.assertIn("<loadExclusive/>", source)
        self.assertNotIn("r46h-remote-input-10ms", {name for name, _size, _digest in WRAPPER.GENERATED_INPUTS})

        base = (b'<?xml version="1.0"?>\n<!-- retained comment -->\n<systemList>\n'
                b'<system><name>gamegear</name></system>\n</systemList>\n')
        data = WRAPPER.replace_exact(
            base,
            b'<?xml version="1.0"?>\n',
            b'<?xml version="1.0"?>\n<loadExclusive/>\n',
            1,
            "exclusive custom systems marker",
        )
        lines = data.splitlines()
        self.assertEqual(lines[1], b"<loadExclusive/>")
        self.assertLess(lines.index(b"<loadExclusive/>"), lines.index(b"<systemList>"))
        systems = ET.fromstring(data[data.index(b"<systemList>"):]).findall("system")
        self.assertEqual([system.findtext("name") for system in systems], ["gamegear"])

        extracted = REPO / "mainline/out/.cache/r46h-v17-design/base/systems"
        if extracted.is_file():
            generated = WRAPPER.replace_exact(
                extracted.read_bytes(),
                b'<?xml version="1.0"?>\n',
                b'<?xml version="1.0"?>\n<loadExclusive/>\n',
                1,
                "exclusive custom systems marker",
            )
            self.assertEqual(len(generated), WRAPPER.GENERATED_INPUTS[0][1])
            self.assertEqual(BUILDER.sha256_bytes(generated), WRAPPER.GENERATED_INPUTS[0][2])

    def test_image_overlay_is_bounded_and_networkless(self) -> None:
        script = IMAGE_TOOL.read_text(encoding="utf-8")
        for required in (
            "R46H_V17_PRODUCT_VERIFY_RESULT=pass",
            "successor_base_artifact_id=debian13-p2-gaming-v0.16",
            "es_de_systems_scope=exclusive-custom",
            '"$REMOTE_INPUT:$REMOTE_INPUT_SHA256"',
            "path_is_absent /home/ark/.ssh/authorized_keys",
        ):
            self.assertIn(required, script)
        self.assertNotIn('emit_replace "$INPUTS/r46h-remote-input-10ms"', script)
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
            "successor to exact p2 v0.16",
            "writes no block device",
            "root-level `<loadExclusive/>`",
            "retained byte-exactly",
            "BOOT, p1 and p3 stay outside",
            "Media proof does not establish R46H behavior",
        ):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
