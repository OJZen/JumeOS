#!/usr/bin/env python3
"""Static contract and result checks for the R46H input/audio batch."""

from __future__ import annotations

from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[2]
RUNBOOK = REPO / "mainline/bringup-tests/ATTENDED-INPUT-AUDIO-BATCH.md"
LEDGER = REPO / "mainline/board/r46h/EXPERIMENT-STATUS.md"


class AttendedInputAudioBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = RUNBOOK.read_text(encoding="utf-8")
        cls.collapsed = " ".join(cls.text.split())
        cls.ledger = LEDGER.read_text(encoding="utf-8")

    def test_freezes_only_the_four_reviewed_inputs(self) -> None:
        expected_counts = {
            "b2193f28e1ae8cb625d34e9c191bda9eea48d079e28595d39eaddd5c9dbd3a68": 2,
            "67090f7457f19717e15f60e2d6c7bda83e6ae76322eaf97c5935b0f90ad94f14": 2,
            "d88b5668384405cf52c3bf8d884ed2b881db50aef92e08406319fe23d64ad814": 3,
            "2bfa8d284d14d231a76d3660d7bd96a896a91147e8f53fc2e5e5dc3436bc508b": 3,
        }
        for digest, count in expected_counts.items():
            self.assertEqual(self.text.count(digest), count, digest)
        for size in ("33,167,980", "24,665", "72,272", "10,961"):
            self.assertIn(size, self.text)
        self.assertIn("Never transfer v0.1 through v0.4", self.text)

    def test_orders_three_boots_and_cleanup_before_audio(self) -> None:
        headings = (
            "## Phase A: exact v0.10 preflight and inactive staging",
            "## Phase B: one exact v0.14 input trial",
            "## Phase C: ordinary v0.10 return, cleanup and audio",
            "## Final cleanup and state",
        )
        offsets = [self.text.index(heading) for heading in headings]
        self.assertEqual(offsets, sorted(offsets))
        phase_c = self.text.index(headings[2])
        remover = self.text.index("r46h-input-bridge-remove", phase_c)
        localizer = self.text.index("r46h-audio-jack-localize --observe", phase_c)
        self.assertLess(remover, localizer)
        self.assertIn("minimum is three cold boots", self.text)
        self.assertIn("Do not start audio before these checks pass", self.text)
        self.assertIn(
            "PASS: exact inactive gaming input bridge candidate removed;",
            self.text,
        )
        self.assertIn("PASS: exact v0.14 one-shot staging removed;", self.text)

    def test_staging_commands_preserve_exact_installer_paths(self) -> None:
        for phrase in (
            "sudo test ! -e /run/r46h-v14-gaming-input-one-shot-v1",
            "sudo test ! -e /run/r46h-gaming-input-bridge-v0.5",
            "-C /run",
            "sudo /run/r46h-v14-gaming-input-one-shot-v1/install.sh",
            "sudo /run/r46h-gaming-input-bridge-v0.5/install.sh",
            "find /run/r46h-v14-gaming-input-one-shot-v1 -xdev -depth -delete",
            "find /run/r46h-gaming-input-bridge-v0.5 -xdev -depth -delete",
            "Require all four paths to be absent",
        ):
            self.assertIn(phrase, self.text)
        self.assertNotIn("--strip-components", self.text)

    def test_input_trial_is_one_shot_and_keeps_full_operator_contract(self) -> None:
        for phrase in (
            "only 60-second window",
            "at most once even if it fails",
            "visibly confirm D-pad, A and the left stick",
            "left stick cap once for L3",
            "right stick cap once for R3",
            "move both sticks through every edge and corner",
            "R46H_INPUT_BRIDGE_TRIAL result=machine-pass",
            "A localization marker is evidence, not permission for another trial",
        ):
            self.assertIn(phrase, self.collapsed)

    def test_audio_localization_is_new_bounded_gate_and_route_is_conditional(self) -> None:
        for phrase in (
            "exactly one insert/remove cycle",
            "Never fall back to the unchanged `r46h-audio-jack-probe`",
            "result=pass reason=both-paths-observed",
            "Any localizer result other than",
            "--headphones-inserted",
            "440 Hz tone in the headphones",
            "no sound from the built-in speaker",
            "Do not raise gain",
        ):
            self.assertIn(phrase, self.collapsed)
        self.assertNotIn("sudo /run/r46h-audio-jack-probe", self.text)
        self.assertIn("sudo test ! -e /run/r46h-audio-jack-localize", self.text)
        self.assertIn("sudo test ! -e /run/r46h-audio-route-probe", self.text)

    def test_hardware_safety_and_scope_are_explicit(self) -> None:
        for phrase in (
            "USB-DC disconnected",
            "1,500,000 baud",
            "I/TC: OP-TEE version",
            "never use `saveenv`",
            "Do not press Reset",
            "No TF-card rewrite",
            "Charging, History, speaker-only playback",
            "controlled poweroff",
            "Do not add a boot",
        ):
            self.assertIn(phrase, self.collapsed)

    def test_cleanup_is_exact_and_final_state_is_closed(self) -> None:
        for phrase in (
            "Remove only the exact task-created tmpfs tools",
            "Remove the transfer directory only if it is empty",
            "Do not delete unrelated cache entries",
            "complete v0.5/v0.14 and audio staging absence",
            "Final physical state is board off",
        ):
            self.assertIn(phrase, self.text)
        self.assertNotIn("rm -rf /home/ark", self.text)
        self.assertNotIn("rm -rf /run", self.text)

    def test_physical_ledger_links_this_contract(self) -> None:
        link = "ATTENDED-INPUT-AUDIO-BATCH.md"
        self.assertIn(link, self.ledger)

    def test_completed_result_preserves_exact_boundaries_and_evidence(self) -> None:
        for phrase in (
            "COMPLETED 2026-08-20",
            "INPUT INCOMPLETE (L3/R3 NOT EXERCISED)",
            "keys=14/16 axes=4/4 centered=4/4 failures=2",
            "not a new physical-source failure",
            "result=fail reason=gpio-transitions-missing",
            "localization=gpio-mux-electrical-or-socket-path",
            "conditional route probe was therefore correctly skipped",
            "final physical state is board off",
            "6135fafa6b1838ece8524841906c4418e5090fe41b17896873e88d893ef9911e",
            "cd062aa89dffbed3d0b390b8242fb70f6799331b5eb9e47f41d7510c28681d3f",
            "6b06e2c0de7991cf7a25192e2af3ba07bdc5b5ed12818fe57bd79d2ba84c7ac9",
        ):
            self.assertIn(phrase, self.collapsed)


if __name__ == "__main__":
    unittest.main()
