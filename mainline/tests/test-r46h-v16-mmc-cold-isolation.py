#!/usr/bin/env python3
"""Focused host gates for the R46H v0.16 cold-MMC DTB one-shot."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import unittest


REPO = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO / "mainline/scripts/build-r46h-v16-mmc-cold-isolation.py"
RUNBOOK = REPO / "mainline/bringup-tests/V16-MMC-COLD-ISOLATION.md"


def load_builder():
    spec = importlib.util.spec_from_file_location("r46h_v16_mmc", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load v0.16 cold-MMC builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class R46HV16MMCColdIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load_builder()
        cls.base = cls.builder.read_base_dtb()
        cls.overlay_source = cls.builder.OVERLAY.read_bytes()
        cls.builder.require_toolchain()
        cls.candidate, cls.overlay_binary = cls.builder.compile_candidate(
            cls.base, cls.overlay_source
        )
        cls.commands = cls.builder.render_uboot_commands(len(cls.candidate))

    def test_overlay_is_one_exact_secondary_host_change(self) -> None:
        text = self.overlay_source.decode()
        self.assertEqual(text.count('target-path = "/mmc@ff380000";'), 1)
        self.assertEqual(text.count('status = "disabled";'), 1)
        self.assertNotIn("ff370000", text)
        self.assertNotIn("max-frequency", text)
        self.assertNotIn("vmmc-supply", text)
        self.assertEqual(len(re.findall(r"fragment@[0-9]+", text)), 1)

    def test_candidate_is_deterministic_and_not_the_base(self) -> None:
        again, overlay_again = self.builder.compile_candidate(
            self.base, self.overlay_source
        )
        self.assertEqual(self.candidate, again)
        self.assertEqual(self.overlay_binary, overlay_again)
        self.assertEqual(
            self.builder.apply_overlay_binary(self.base, self.overlay_binary),
            self.candidate,
        )
        self.assertNotEqual(self.candidate, self.base)
        self.assertEqual(
            self.builder.sha256_bytes(self.base), self.builder.BASE_DTB_SHA256
        )

    def test_uboot_one_shot_reuses_exact_v015_image_and_p2_only(self) -> None:
        text = self.commands.decode()
        self.assertIn(self.builder.BASE_IMAGE_PATH, text)
        self.assertIn(self.builder.TARGET_DIRECTORY + "/R46H.DTB", text)
        self.assertIn(f"-eq {self.builder.BASE_IMAGE_SIZE:#x}", text)
        self.assertIn(f"-eq {len(self.candidate):#x}", text)
        self.assertIn(f"root=PARTUUID={self.builder.ROOT_PARTUUID}", text)
        self.assertIn("ext4load mmc 1:2", text)
        self.assertNotIn("mmc 1:1", text)
        self.assertNotIn("fatload", text)
        self.assertNotIn("saveenv", text)
        self.assertNotIn("mmc write", text)

    def test_script_image_and_archive_are_deterministic(self) -> None:
        first_script = self.builder.make_script_image(self.commands)
        second_script = self.builder.make_script_image(self.commands)
        self.assertEqual(first_script, second_script)
        files = self.builder.payload_files(
            self.candidate, self.overlay_binary, "0" * 40
        )
        first = self.builder.deterministic_archive(files)
        second = self.builder.deterministic_archive(files)
        self.assertEqual(first, second)
        self.assertEqual(self.builder.validate_archive(first), files)
        launch = files["LAUNCH.txt"].decode()
        self.assertEqual(launch.count("ext4load mmc 1:2"), 1)
        self.assertIn("source 0x0b000000", launch)
        self.assertNotIn("saveenv", launch)

    def test_runbook_keeps_evidence_and_rollback_boundaries(self) -> None:
        collapsed = " ".join(RUNBOOK.read_text(encoding="utf-8").split())
        for literal in (
            "ONE-SHOT PHYSICAL PASS",
            "PERSISTENT COLD GATE FAIL",
            "EXACT V0.15 ROLLBACK PASS",
            "second card slot unavailable",
            "one bounded cold regression",
            "status=rollback-complete",
            "never use `saveenv`",
            "1500000",
            "I/TC: OP-TEE version",
            "115200",
            "Reset is rescue, not PASS",
            "Do not repeat either unchanged sample",
            "gaming-product-v16-boot-promotion/README.md",
            "before any p1 write",
            "twenty-ninth required base entry",
            "does not prove that concurrent probing is the sole root cause",
            "54c081d0ea2ed2dd4345de2e85e348a9c78e1e0fc0357f7df216b7e326adcba5",
            "99d162b5d920f14108d9d7ff725f96f3e0e52d20dbd713fac46a4a53023ad042",
            "895a2ebaca0ec88f936d53142009716b80d99d72ee9214b2afdd1245d8b703b1",
            "Disabling the secondary controller is not sufficient",
        ):
            self.assertIn(literal, collapsed)


if __name__ == "__main__":
    unittest.main()
