#!/usr/bin/env python3
"""Focused contracts for the ES-DE remote-screen overlay."""

from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import unittest


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "mainline/gaming-remote-screen-es-de"
REMOTE = REPO / "mainline/gaming-remote-screen"
OUTPUT = REPO / "mainline/out/r46h-remote-screen-es-de-v0.1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RemoteScreenEsDeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.capture = (REMOTE / "r46h-drm-capture.c").read_text(encoding="utf-8")
        cls.helper = (REMOTE / "r46h-screenshot").read_text(encoding="utf-8")
        cls.installer = (ROOT / "install.sh").read_text(encoding="utf-8")
        cls.rollback = (ROOT / "rollback.sh").read_text(encoding="utf-8")

    def test_capture_accepts_only_linear_xrgb_or_argb(self) -> None:
        self.assertIn("#define DRM_FORMAT_XRGB8888 0x34325258U", self.capture)
        self.assertIn("#define DRM_FORMAT_ARGB8888 0x34325241U", self.capture)
        self.assertIn("framebuffer->modifier != 0U", self.capture)
        self.assertIn("framebuffer->handles[1] != 0U", self.capture)

    def test_guard_supports_exact_ozone_or_es_de(self) -> None:
        runner_sha256 = sha256(REPO / "mainline/gaming-es-de/r46h-es-de-ui")
        for token in (
            "expected exactly one supported gaming frontend process",
            "pgrep -u 1000 -x retroarch",
            "pgrep -u 1000 -x es-de",
            "EXPECTED_CAPTURE_SHA256=77f22181289edd701001fd6570a49afbfde277417e3769a693d1dd335cad324e",
            f"EXPECTED_ES_DE_RUNNER_SHA256={runner_sha256}",
            "EXPECTED_ES_DE_SHA256=9c6e50433b9bca5ac1c01030bc4d7b143f05c2cd27c52e6f5f765b0acf01be98",
        ):
            self.assertIn(token, self.helper)
        self.assertIn(f"ES_DE_RUNNER_SHA256={runner_sha256}", self.installer)
        self.assertNotIn("TO_BE_LOCKED", self.helper)

    def test_overlay_is_two_file_p2_only_and_reversible(self) -> None:
        helper_sha256 = sha256(REMOTE / "r46h-screenshot")
        for text in (self.installer, self.rollback):
            for forbidden in ("/boot", "boot.ini", "/dev/disk", "mkfs", "saveenv"):
                self.assertNotIn(forbidden, text)
            for token in (
                "EXPECTED_ROOT_PARTUUID=c9f931c9-02",
                "EXPECTED_ROOT_UUID=d3130007-46a4-4d56-9001-000000000007",
                "BASE_RECEIPT_SHA256=28aae35ba2f35255ae628949b76f1bb1d271be887cd51a81f12d73c0bd771957",
                "OLD_CAPTURE_SHA256=bb4c421029085cc182c369bb8b7c4a1431d0de2ddafb244d8c347dbbad127618",
                "OLD_HELPER_SHA256=728ad68187cc5647c695014c61ec86f48207ef05b46088463d427832ee3e40e4",
                "NEW_CAPTURE_SHA256=77f22181289edd701001fd6570a49afbfde277417e3769a693d1dd335cad324e",
                f"NEW_HELPER_SHA256={helper_sha256}",
                "findmnt -rn -o OPTIONS /roms",
            ):
                self.assertIn(token, text)
            self.assertNotIn("systemctl stop r46h-gaming-frontend", text)
            self.assertNotIn("systemctl start r46h-gaming-frontend", text)
            self.assertNotIn("TO_BE_LOCKED", text)
        self.assertIn(f"ROLLBACK_SHA256={sha256(ROOT / 'rollback.sh')}", self.installer)
        self.assertIn('previous-capture" "$CAPTURE"', self.installer)
        self.assertIn('previous-helper" "$HELPER"', self.installer)
        self.assertIn('previous-capture" "$capture_stage"', self.rollback)
        self.assertIn('previous-helper" "$helper_stage"', self.rollback)

    def test_payload_manifest_and_scripts(self) -> None:
        for path in (
            ROOT / "install.sh",
            ROOT / "rollback.sh",
            ROOT / "build-payload.sh",
            REMOTE / "r46h-screenshot",
            REMOTE / "build-drm-capture.sh",
        ):
            subprocess.run(["bash", "-n", str(path)], check=True)
        if not OUTPUT.exists():
            self.skipTest("payload is not assembled")
        expected = {
            "README.md",
            "SHA256SUMS",
            "install.sh",
            "r46h-drm-capture",
            "r46h-screenshot",
            "rollback.sh",
        }
        self.assertEqual({path.name for path in OUTPUT.iterdir()}, expected)
        entries = {}
        for line in (OUTPUT / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            digest, name = line.split("  ", 1)
            entries[name] = digest
        self.assertEqual(set(entries), expected - {"SHA256SUMS"})
        for name, digest in entries.items():
            self.assertEqual(sha256(OUTPUT / name), digest)


if __name__ == "__main__":
    unittest.main()
