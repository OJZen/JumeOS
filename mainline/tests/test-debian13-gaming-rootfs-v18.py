#!/usr/bin/env python3
"""Focused host gates for the R46H gaming p2 v0.18 policy image."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import stat
import subprocess
import sys
import unittest


REPO = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO / "mainline/scripts/build-debian13-gaming-rootfs-v18.py"
SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v18", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
WRAPPER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = WRAPPER
SPEC.loader.exec_module(WRAPPER)
BUILDER = WRAPPER.BASE
ROOT = REPO / "mainline/rootfs-debian13-gaming-v18"
IMAGE_TOOL = ROOT / "image-in-container.sh"


class Debian13GamingRootfsV18Tests(unittest.TestCase):
    def test_identity_is_exact_v17_successor(self) -> None:
        self.assertEqual(BUILDER.ARTIFACT_ID, "debian13-p2-gaming-v0.18")
        self.assertEqual(BUILDER.BASE_FS_UUID, "d3130017-46a4-4d56-9001-000000000017")
        self.assertEqual(BUILDER.FS_UUID, "d3130018-46a4-4d56-9001-000000000018")
        self.assertEqual(BUILDER.FS_LABEL, "R46H_GAMING_V18")
        self.assertEqual(
            BUILDER.BASE_IMAGE_SHA256,
            "efccaf9b1d6b48624427f96f0d995c0143cb50e3447f31506ef6553973538897",
        )
        self.assertEqual(BUILDER.SUCCESSOR_METHOD, "offline-ext4-repack-local-debs")
        self.assertTrue(BUILDER.CONTAINER_PRIVILEGED)

    def test_policy_inputs_are_exact(self) -> None:
        self.assertEqual(len(WRAPPER.PACKAGES), 6)
        self.assertEqual({package for package, *_rest in WRAPPER.PACKAGES}, {
            "libduktape207", "libpolkit-agent-1-0", "libpolkit-gobject-1-0",
            "polkitd", "sgml-base", "xml-core",
        })
        self.assertEqual(WRAPPER.RULE_SHA256, "842466c1aafc51d187abb1ec3204d7c34579d56149249947619c8967ecccc87e")
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["network_policy_actions"], "3")
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["network_policy_scope"], "ark-only")

    def test_generated_identity_chain_is_exact(self) -> None:
        base = {
            "r46h-es-de-ui.v17": b"u=d3130017-46a4-4d56-9001-000000000017\n",
            "r46h-screenshot.v17": (
                b"u=d3130017-46a4-4d56-9001-000000000017\n"
                b"h=2809199ce5020edd7a654b9ef8b72b58dca7568603f44769b7ace933a942c94d\n"
            ),
            "r46h-firstboot.v17": b"debian13-p2-gaming-v0.17\ndebian13-p2-gaming-v0.17\n",
            "r46h-rootfs-smoke.v17": b"d3130017-46a4-4d56-9001-000000000017\ndebian13-p2-gaming-v0.17\n",
            "es-de-receipt.v17": (
                b"2809199ce5020edd7a654b9ef8b72b58dca7568603f44769b7ace933a942c94d\n"
                b"offline-exclusive-systems-successor-p2-v0.17\n"
            ),
        }
        self.assertIn(b"d3130018", WRAPPER.replace_exact(base["r46h-es-de-ui.v17"], b"d3130017", b"d3130018", 1, "UUID"))
        with self.assertRaises(BUILDER.BuildError):
            WRAPPER.replace_exact(b"missing", b"old", b"new", 1, "guard")

    def test_composer_is_offline_and_block_device_bounded(self) -> None:
        script = IMAGE_TOOL.read_text(encoding="utf-8")
        for required in (
            "offline-ext4-repack-local-debs",
            "mke2fs -q -F -t ext4",
            'losetup --find --show "$SCRATCH"',
            "R46H_V18_PACKAGE_VERIFY_RESULT=pass",
            "R46H_V18_PRODUCT_VERIFY_RESULT=pass",
            "subject.user == \"ark\"",
        ):
            self.assertIn(required, script)
        for forbidden in ("/dev/disk", "saveenv", "curl ", "wget ", "apt-get update", "--net=host"):
            self.assertNotIn(forbidden, script)
        self.assertIn("'-f=${Package}\\t${Version}\\t${Architecture}\\n'", script)
        self.assertNotIn("'-f=${binary:Package}\\t${Version}\\t${Architecture}\\n'", script)
        framework = (REPO / "mainline/scripts/build-debian13-gaming-rootfs-v06.py").read_text(encoding="utf-8")
        self.assertIn("if CONTAINER_PRIVILEGED:", framework)
        self.assertIn('SUCCESSOR_METHOD = "offline-debugfs-bounded-overlay"', framework)

    def test_entry_points_and_docs_are_valid(self) -> None:
        self.assertEqual(subprocess.run(["/bin/bash", "-n", str(IMAGE_TOOL)]).returncode, 0)
        self.assertEqual(stat.S_IMODE(IMAGE_TOOL.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(BUILDER_PATH.stat().st_mode), 0o755)
        compile(BUILDER_PATH.read_text(encoding="utf-8"), str(BUILDER_PATH), "exec")
        text = " ".join((ROOT / "README.md").read_text(encoding="utf-8").split())
        for required in (
            "exact v0.17 successor", "hash-pinned local `.deb`", "never opens a host block device",
            "composed twice byte-for-byte", "Media write/readback and physical acceptance are separate",
        ):
            self.assertIn(required, text)


if __name__ == "__main__":
    unittest.main()
