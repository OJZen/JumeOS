#!/usr/bin/env python3
"""Focused contract and result checks for the attended R46H gaming retry."""

from __future__ import annotations

from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[2]
RUNBOOK = REPO / "mainline/bringup-tests/ATTENDED-GAMING-RETRY.md"


class AttendedGamingRetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = RUNBOOK.read_text(encoding="utf-8")
        cls.collapsed = " ".join(cls.text.split())

    def test_freezes_exact_four_host_inputs(self) -> None:
        for digest in (
            "b2193f28e1ae8cb625d34e9c191bda9eea48d079e28595d39eaddd5c9dbd3a68",
            "e59ff0a4b9d93a362155fbf66ecf8bd79f0d91e22e644919b4046d3d2187ae4f",
            "41dbe0e95ef6e6e2fe614c5acdcd18507714cc4cf94616b8745527bf39657d3e",
            "2bfa8d284d14d231a76d3660d7bd96a896a91147e8f53fc2e5e5dc3436bc508b",
        ):
            self.assertEqual(self.text.count(digest), 2, digest)
        self.assertIn("r46h-gaming-input-bridge-v0.3.tar.gz", self.text)
        self.assertNotIn("r46h-gaming-history-v0.2.tar.gz", self.text)

    def test_pins_current_history_state_before_staging(self) -> None:
        for token in (
            "697aa82bb42689cd841f16a8ce1ae9c6ac2bdc56ccd1b811136f8f5884e600e9",
            "9b800245202992cbdc063e5cabd071a6265fbb9133e89a8718d0952209d0f1aa",
            "1000:1000:700",
            "any old-config mismatch is a failure",
            "History v0.2 must remain intact",
        ):
            self.assertIn(token, self.text)

    def test_orders_input_cleanup_before_headphones(self) -> None:
        headings = (
            "## Phase A: exact v0.10 preflight and inactive staging",
            "## Phase B: one exact v0.14 input trial",
            "## Phase C: ordinary v0.10 return and candidate cleanup",
            "## Phase D: headphone detect and route",
            "## Final cleanup and state",
        )
        offsets = [self.text.index(heading) for heading in headings]
        self.assertEqual(offsets, sorted(offsets))
        self.assertIn("r46h-input-bridge-remove", self.text)
        self.assertIn("--headphones-inserted", self.text)

    def test_operator_actions_are_unambiguous_and_bounded(self) -> None:
        for token in (
            "only 60-second window",
            "left stick cap once for L3",
            "right stick cap once for R3",
            "Do not run a second trial",
            "insert the headset again",
            "silence from the built-in speaker",
            "Do not raise gain",
        ):
            self.assertIn(token, self.collapsed)

    def test_excludes_completed_or_independent_gates(self) -> None:
        self.assertIn("Charging", self.text)
        self.assertIn("were excluded", self.collapsed)
        self.assertIn("Do not transfer input bridge v0.1 or v0.2", self.text)
        self.assertIn("History result was a prerequisite, not a repeated gate", self.collapsed)
        self.assertNotIn("saveenv", self.text.split("Never use `saveenv`.", 1)[1])

    def test_records_failed_gates_and_clean_final_state(self) -> None:
        for token in (
            "COMPLETE / INPUT V0.3 FAIL / JACK DETECT FAIL / ROUTE SKIPPED",
            "R46H_INPUT_BRIDGE_COVERAGE keys=4/16 axes=4/4 centered=3/4 failures=13",
            "only the left stick respond on screen",
            "reason=required-transitions-missing initial=0 insertions=0 removals=0 final=0 syn_dropped=0",
            "headphone playback and automatic speaker-muting observations were skipped",
            "21a4f19b270ac0a6a1591bd823500bd8d65cfedac61e6e1bcb4a98b8947fb57b",
            "powered off with USB-DC disconnected and the headset removed",
        ):
            self.assertIn(token, self.collapsed)
        self.assertIn("Do not run a second trial", self.text)


if __name__ == "__main__":
    unittest.main()
