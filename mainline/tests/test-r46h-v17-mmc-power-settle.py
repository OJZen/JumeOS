#!/usr/bin/env python3
"""Focused host gates for the R46H v0.17 cold-MMC power-settle one-shot."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import unittest


REPO = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO / "mainline/scripts/build-r46h-v17-mmc-power-settle.py"
RUNBOOK = REPO / "mainline/bringup-tests/V17-MMC-POWER-SETTLE.md"


def load_builder():
    spec = importlib.util.spec_from_file_location("r46h_v17_mmc", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load v0.17 power-settle builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class R46HV17MMCPowerSettleTests(unittest.TestCase):
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

    def test_overlay_is_v016_plus_one_system_power_property(self) -> None:
        text = self.overlay_source.decode()
        self.assertEqual(text.count('target-path = "/mmc@ff370000";'), 1)
        self.assertEqual(text.count('post-power-on-delay-ms = <800>;'), 1)
        self.assertEqual(text.count('target-path = "/mmc@ff380000";'), 1)
        self.assertEqual(text.count('status = "disabled";'), 1)
        self.assertEqual(len(re.findall(r"fragment@[0-9]+", text)), 2)
        self.assertNotIn("max-frequency", text)
        self.assertNotIn("vmmc-supply", text)
        self.assertNotIn("vqmmc-supply", text)
        self.assertNotIn("card-detect-delay", text)

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
        receipt = self.builder.json.loads(files["RECEIPT.json"])
        self.assertEqual(receipt["post_power_on_delay_ms"], 800)

    def test_provenance_closure_includes_reused_helper(self) -> None:
        self.assertIn(self.builder.HELPER_RELATIVE, self.builder.SOURCE_PATHS)
        self.assertIn(self.builder.BUILDER_RELATIVE, self.builder.SOURCE_PATHS)
        self.assertEqual(len(self.builder.SOURCE_PATHS), 5)

    def test_runbook_keeps_evidence_and_rollback_boundaries(self) -> None:
        collapsed = " ".join(RUNBOOK.read_text(encoding="utf-8").split())
        for literal in (
            "ONE-SHOT PHYSICAL PASS / CLEANLY REMOVED",
            "800 ms",
            "default 10 ms",
            "post-power-on-delay-ms",
            "card-detect-delay",
            "drivers/mmc/core/host.c",
            "drivers/mmc/core/core.c",
            "exact v0.15 Image",
            "second card slot unavailable",
            "one bounded cold regression",
            "never use `saveenv`",
            "1500000",
            "I/TC: OP-TEE version",
            "115200",
            "Reset is rescue, not PASS",
            "p1 remains unchanged",
            "Host validation is not physical proof",
            "approximately 21 ms first gap",
            "821.662 ms",
            "896.044 ms",
            "1.717706 s",
            "eda7561a6acb378adb52f3c03255adadd67e5be2f1d03048fdd306e62ee40ba7",
        ):
            self.assertIn(literal, collapsed)
        self.assertNotIn("PHYSICAL PENDING", collapsed)


if __name__ == "__main__":
    unittest.main()
