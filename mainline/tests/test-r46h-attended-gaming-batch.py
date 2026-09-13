#!/usr/bin/env python3
"""Static checks for the consolidated R46H attended gaming batch."""

from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[2]
RUNBOOK = REPO / "mainline/bringup-tests/ATTENDED-GAMING-BATCH.md"


class AttendedGamingBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runbook = RUNBOOK.read_text(encoding="utf-8")

    def test_frozen_artifact_identities_are_complete(self) -> None:
        for digest in (
            "b2193f28e1ae8cb625d34e9c191bda9eea48d079e28595d39eaddd5c9dbd3a68",
            "e0c1cc1c9c28149d6892b8ab9c85fa421ba7b2566404b0882c34e055c6f831c2",
            "41dbe0e95ef6e6e2fe614c5acdcd18507714cc4cf94616b8745527bf39657d3e",
            "2bfa8d284d14d231a76d3660d7bd96a896a91147e8f53fc2e5e5dc3436bc508b",
            "ea4d53659c25389efbc1c692da43aaf99699f5c5f42aee6b150799d0c4c7ea62",
            "066f2dd962cd6f34943e619c9dfa69a628c0e6680f61307d334aaab9ec64c49d",
            "fb88d6f8d093527fb6b56730e6082cb088de97d8024ec1dac5f5b724acbc5819",
            "697aa82bb42689cd841f16a8ce1ae9c6ac2bdc56ccd1b811136f8f5884e600e9",
        ):
            self.assertIn(digest, self.runbook)

    def test_order_keeps_old_config_until_candidate_cleanup(self) -> None:
        phases = [
            "Phase A: cold v0.10 and inactive staging",
            "Phase B: one exact v0.14 input trial",
            "Phase C: exact v0.10 return and candidate cleanup",
            "Phase D: headphone gates on v0.10",
            "Phase E: history fix and UI persistence",
            "Final cleanup and final state",
        ]
        offsets = [self.runbook.index(phase) for phase in phases]
        self.assertEqual(offsets, sorted(offsets))
        self.assertLess(
            self.runbook.index("r46h-input-bridge-remove"),
            self.runbook.index("history archive, normalize"),
        )

    def test_hardware_safety_and_evidence_boundaries_are_explicit(self) -> None:
        for phrase in (
            "USB-DC disconnected",
            "1,500,000 baud",
            "I/TC: OP-TEE version",
            "Never use `saveenv`",
            "Do not press Reset",
            "No TF-card base-image rewrite is needed",
            "do not loop it",
            "known working 3.5 mm headset",
            "skip the route probe",
            "controlled poweroff",
            "Charging is intentionally excluded",
            "Application-level rumble is also excluded",
        ):
            self.assertIn(phrase, self.runbook)

    def test_final_cleanup_is_bounded(self) -> None:
        for phrase in (
            "Remove only the two `/run` audio tools",
            "five exact user-owned transfer files",
            "Remove the transfer directory only",
            "Do not delete unrelated cache",
            "no v0.14 staging",
        ):
            self.assertIn(phrase, self.runbook)
        self.assertNotIn("rm -rf /home/ark", self.runbook)
        self.assertNotIn("rm -rf /run/r46h-gaming-history-v0.2", self.runbook)

    def test_history_staging_does_not_expand_inside_root_only_directory(self) -> None:
        self.assertNotIn("/run/r46h-gaming-history-v0.2/*", self.runbook)
        for name in ("install.sh", "rollback.sh", "retroarch.cfg"):
            self.assertIn(f"/run/r46h-gaming-history-v0.2/{name}", self.runbook)

    def test_completed_results_and_history_control_are_explicit(self) -> None:
        for phrase in (
            "PHYSICAL COMPLETE / INPUT FAIL / HEADPHONE DEFERRED / HISTORY PASS",
            "14/16",
            "4/4 axes",
            "L3/R3 emitted no events",
            "no left-stick response",
            "Do not repeat the unchanged v0.14 candidate",
            "stop the service from serial",
            "reopened it from RGUI History",
            "controlled poweroff",
        ):
            self.assertIn(phrase, self.runbook)
        self.assertNotIn("return to RGUI", self.runbook)


if __name__ == "__main__":
    unittest.main()
