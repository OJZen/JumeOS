#!/usr/bin/env python3
"""Static execution-contract checks for the R46H completion batch."""

from __future__ import annotations

from pathlib import Path
import unittest


REPO = Path(__file__).resolve().parents[2]
RUNBOOK = REPO / "mainline/bringup-tests/ATTENDED-INPUT-AUDIO-COMPLETION.md"
LEDGER = REPO / "mainline/board/r46h/EXPERIMENT-STATUS.md"


class AttendedInputAudioCompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = RUNBOOK.read_text(encoding="utf-8")
        cls.collapsed = " ".join(cls.text.split())
        cls.ledger = LEDGER.read_text(encoding="utf-8")

    def test_freezes_exactly_four_host_inputs(self) -> None:
        expected_counts = {
            "b2193f28e1ae8cb625d34e9c191bda9eea48d079e28595d39eaddd5c9dbd3a68": 2,
            "67090f7457f19717e15f60e2d6c7bda83e6ae76322eaf97c5935b0f90ad94f14": 2,
            "fbdca20ecf5eb758c064a88d4cc8410890ad552ba8820de85a0113847221c76f": 2,
            "32f4f0ec8c5924cf31b3743a0f316950050caa38c3c4e41763a4eecd73650f1e": 2,
        }
        for digest, count in expected_counts.items():
            self.assertEqual(self.text.count(digest), count, digest)
        for size in ("33,167,980", "24,665", "15,498", "352,020"):
            self.assertIn(size, self.text)
        self.assertIn("Never transfer bridge v0.1 through v0.4", self.text)

    def test_orders_exactly_four_cold_boot_phases(self) -> None:
        headings = (
            "## Phase A: exact v0.10 readback and inactive staging",
            "## Phase B: exact v0.14 L3/R3 completion",
            "## Phase C: factory `4.4.189` GPIO2_C6 control",
            "## Phase D: ordinary v0.10 removal and final state",
        )
        offsets = [self.text.index(heading) for heading in headings]
        self.assertEqual(offsets, sorted(offsets))
        self.assertIn("The batch used four cold boots", self.text)
        self.assertEqual(self.text.count("## Phase "), 4)

    def test_phase_a_proves_current_p1_and_stages_inactive_payloads(self) -> None:
        for phrase in (
            "mount -t vfat -o ro,nosuid,nodev,noexec",
            "c9f931c9-01",
            "current-media identity",
            "sudo umount /run/r46h-vendor-p1-readback",
            "sudo rmdir /run/r46h-vendor-p1-readback",
            "sudo test ! -e /run/r46h-v14-gaming-input-one-shot-v1",
            "sudo test ! -e /run/r46h-gaming-input-bridge-v0.5",
            "sudo /run/r46h-v14-gaming-input-one-shot-v1/install.sh",
            "sudo /run/r46h-gaming-input-bridge-v0.5/install.sh",
            "/var/lib/r46h/audio-jack-vendor-control-v0.1/uInitrd",
            "Retain only the targeted",
            "both candidates inactive",
        ):
            self.assertIn(phrase, self.text)
        self.assertNotIn("--strip-components", self.text)

    def test_phase_b_is_targeted_and_does_not_repeat_full_trial(self) -> None:
        for phrase in (
            "only 20-second window",
            "click/release the left stick cap once",
            "click/release the right stick cap once",
            "controls=2/2",
            "result=machine-pass",
            "cleanup=pass",
            "Other buttons, stick-axis travel and screen behavior are not requested",
            "Do not retry",
        ):
            self.assertIn(phrase, self.collapsed)
        self.assertNotIn("r46h-input-bridge-trial", self.text)
        self.assertNotIn("move both sticks", self.text)
        self.assertNotIn("60-second", self.text)

    def test_factory_control_is_one_shot_read_only_and_no_playback(self) -> None:
        for phrase in (
            "one factory-kernel/minimal-initramfs boot",
            "retained factory `4.4.189` Image and DTB",
            "loads the already rehashed factory Image and DTB from p1",
            "validates all three sizes and the ramdisk checksum",
            "neither mounts nor writes a filesystem",
            "fully insert the known headset once",
            "hold about two seconds",
            "PID 1 powers off",
            "contains no headphone playback or speaker-muting observation",
        ):
            self.assertIn(phrase, self.collapsed)
        self.assertNotIn("r46h-audio-jack-localize", self.text)
        self.assertNotIn("r46h-audio-route-probe", self.text)
        self.assertNotIn("speaker-test", self.text)

    def test_hardware_safety_is_explicit(self) -> None:
        for phrase in (
            "USB-DC disconnected",
            "1,500,000 baud",
            "I/TC: OP-TEE version",
            "Do not press Reset",
            "Never use `saveenv`",
            "No TF-card rewrite",
            "controlled poweroff",
            "Do not add or loop a boot",
            "wrong kernel/model/root/config identity",
        ):
            self.assertIn(phrase, self.collapsed)

    def test_phase_d_cleanup_order_and_final_state_are_closed(self) -> None:
        phase_d = self.text.index("## Phase D:")
        bridge_remove = self.text.index("r46h-input-bridge-remove", phase_d)
        one_shot_remove = self.text.index("/REMOVE.sh", bridge_remove)
        vendor_remove = self.text.index("Exact cleanup on the next v0.10 boot", one_shot_remove)
        cache_remove = self.text.index("rmdir /home/ark/.cache/r46h-input-audio-completion-v1", vendor_remove)
        self.assertLess(bridge_remove, one_shot_remove)
        self.assertLess(one_shot_remove, vendor_remove)
        self.assertLess(vendor_remove, cache_remove)
        for phrase in (
            "complete input/v0.14/vendor-control/transfer staging absence",
            "Do not delete any unrelated cache entry",
            "Final physical state is board off",
            "Only after all cleanup and evidence checks pass",
        ):
            self.assertIn(phrase, self.text)
        self.assertNotIn("rm -rf", self.text)

    def test_physical_ledger_links_this_contract(self) -> None:
        link = "ATTENDED-INPUT-AUDIO-COMPLETION.md"
        self.assertIn(link, self.ledger)

    def test_physical_result_is_exact_and_bounded(self) -> None:
        for phrase in (
            "PHYSICAL BATCH COMPLETE",
            "INPUT COMPOSITE PASS",
            "FACTORY CONTROL V0.1 INFRASTRUCTURE FAIL",
            "controls=2/2",
            "not one simultaneous 16-key trial",
            "reason=initial-gpio-state-unreadable",
            "operator was correctly not asked to insert the headset",
            "all 17 candidate, runtime, extraction and transfer paths were absent",
            "board is off, USB-DC is disconnected and the headset is removed",
        ):
            self.assertIn(phrase, self.collapsed)
        evidence = {
            "attended-input-audio-completion-phase-a-20260821T130833Z.bin": (
                "69,998",
                "ee5cc40851eb2c6a7334465c1c0dc9d75a37a1b971e79391d5f249d02bf9ef2e",
            ),
            "attended-input-audio-completion-v014-l3r3-20260821T131933Z.bin": (
                "63,349",
                "d924b1ab2063eb8a10c2464d46cc78015fc74b301b06b0da6551f47d6f5c53a1",
            ),
            "attended-input-audio-completion-vendor-gpio-20260821T133011Z.bin": (
                "54,815",
                "693ac6a84acf300cbd07b770f68e5a7bd7adac8152ec8d30a58759186cab2483",
            ),
            "attended-input-audio-completion-cleanup-v010-20260821T133419Z.bin": (
                "66,562",
                "cc4aa0f82370576b06082a54c170a914e755f17a25066f91f1ec5c9b276f60bf",
            ),
        }
        for name, (size, digest) in evidence.items():
            self.assertIn(name, self.text)
            self.assertIn(size, self.text)
            self.assertIn(digest, self.text)
        collapsed_ledger = " ".join(self.ledger.split())
        self.assertIn("COMPOSITE PHYSICAL PASS / CLEANLY REMOVED", collapsed_ledger)
        self.assertIn(
            "FACTORY CONTROL V0.1 INFRASTRUCTURE FAIL", collapsed_ledger
        )


if __name__ == "__main__":
    unittest.main()
