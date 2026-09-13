#!/usr/bin/env python3
"""Host contract checks for the targeted R46H L3/R3 completion runner."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import textwrap
import unittest


REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "mainline/bringup-tests/r46h-input-bridge-l3r3-complete"
RUNBOOK = REPO / "mainline/bringup-tests/GAMING-INPUT-BRIDGE.md"
BATCH = REPO / "mainline/bringup-tests/ATTENDED-INPUT-AUDIO-COMPLETION.md"
EXPECTED_SHA256 = "fbdca20ecf5eb758c064a88d4cc8410890ad552ba8820de85a0113847221c76f"


class R46HInputBridgeL3R3CompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = RUNNER.read_text(encoding="utf-8")
        cls.runbook = RUNBOOK.read_text(encoding="utf-8")
        cls.batch = BATCH.read_text(encoding="utf-8")

    def test_source_identity_mode_and_document_pins(self) -> None:
        self.assertEqual(hashlib.sha256(RUNNER.read_bytes()).hexdigest(), EXPECTED_SHA256)
        self.assertEqual(stat.S_IMODE(RUNNER.stat().st_mode), 0o755)
        self.assertEqual(self.runbook.count(EXPECTED_SHA256), 2)
        self.assertEqual(self.batch.count(EXPECTED_SHA256), 2)

    def test_runner_is_exactly_targeted_to_l3_and_r3(self) -> None:
        match = re.search(r"^readonly TARGET_KEYS=\(([^\n]+)\)$", self.runner, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(
            match.group(1).split(),  # type: ignore[union-attr]
            ["BTN_TRIGGER_HAPPY3", "BTN_TRIGGER_HAPPY4"],
        )
        self.assertEqual(self.runner.count("BTN_TRIGGER_HAPPY3"), 1)
        self.assertEqual(self.runner.count("BTN_TRIGGER_HAPPY4"), 1)
        for forbidden in (
            "ABS_X",
            "ABS_Y",
            "ABS_RX",
            "ABS_RY",
            "REQUIRED_AXES",
            "r46h-game-ui-input-candidate",
            '"$RUNNER" smoke',
            "INPUT_WINDOW_SECONDS=60",
        ):
            self.assertNotIn(forbidden, self.runner)
        self.assertIn("INPUT_WINDOW_SECONDS=20", self.runner)
        self.assertIn("operator_screen_observation=not-required", self.runner)

    def test_exact_runtime_and_installed_v05_identity_are_required(self) -> None:
        for token in (
            "6.12.99-r46h-mainline-v0.14-gaming-input-bridge",
            "EXPECTED_ROOT_PARTUUID=c9f931c9-02",
            "EXPECTED_SELF=/run/r46h-input-bridge-l3r3-complete",
            "STATE_DIR=/var/lib/r46h-gaming-input-bridge/v0.5",
            "gaming-input-bridge-v0.5-installed",
            "r46h-gaming-input-bridge-v0.5",
            '[[ -t 0 && -t 1 && -t 2 ]]',
            "stat -c '%u:%g:%a:%h' \"$EXPECTED_SELF\"",
            '[[ "$(findmnt -rn -T /run -o FSTYPE)" == tmpfs ]]',
            '[[ "$(cat "$EXT4_ERRORS")" == 0 ]]',
            '[[ -z "$(systemctl --failed --no-legend --plain)" ]]',
            'sha256sum -c SHA256SUMS',
            'cmp -s r46h-input-bridge /usr/local/libexec/r46h-input-bridge',
        ):
            self.assertIn(token, self.runner)

    def test_lifecycle_uses_exact_service_and_virtual_capture(self) -> None:
        for token in (
            'systemctl stop "$FRONTEND_SERVICE"',
            'systemctl start "$SERVICE"',
            'systemctl is-active --quiet "$SERVICE"',
            '"$WAITER" --print-node',
            '/usr/bin/evtest "$virtual_node"',
            'systemctl stop "$SERVICE"',
            "bridge diagnostics line count mismatch",
            "source_syn_reports >= 1 && emitted_syn_reports == source_syn_reports",
            "virtual capture reported SYN_DROPPED",
            "R46H_INPUT_BRIDGE_L3R3_COVERAGE controls=%d/%d",
            "result=%s status=%d controls=%s cleanup=%s",
        ):
            self.assertIn(token, self.runner)
        self.assertNotIn("systemctl enable", self.runner)
        self.assertNotIn("systemctl start \"$FRONTEND_SERVICE\"", self.runner)

    def test_three_stage_key_counts_fail_closed(self) -> None:
        for token in (
            "source_presses >= 1 && source_releases >= 1 && source_last == 0",
            "emitted_presses == source_presses",
            "emitted_releases == source_releases",
            "emitted_other == source_other",
            "emitted_last == source_last",
            "virtual_presses == emitted_presses",
            "virtual_releases == emitted_releases",
            "virtual_other == emitted_other",
            "virtual_last == emitted_last",
            "physical-source-missing",
            "bridge-write-missing",
            "virtual-delivery-or-capture-missing",
            "key_count == ${#TARGET_KEYS[@]}",
        ):
            self.assertIn(token, self.runner)

    def test_cleanup_is_exact_and_health_checked(self) -> None:
        for token in (
            "trap cleanup EXIT",
            "safe_remove_runtime",
            "safe_remove_diagnostics",
            "rm -f -- \"$event_log\"",
            "rm -f -- \"$DIAGNOSTICS\"",
            "rmdir -- \"$runtime_dir\"",
            "rmdir -- \"$DIAGNOSTICS_DIR\"",
            "combined_device_count",
            "pgrep -x retroarch",
            "operator_screen_observation=not-required",
        ):
            self.assertIn(token, self.runner)
        for forbidden in ("rm -rf", "saveenv", "reboot", "poweroff"):
            self.assertNotIn(forbidden, self.runner)

    def test_shell_syntax_and_documented_evidence_boundary(self) -> None:
        subprocess.run(["/bin/bash", "-n", str(RUNNER)], check=True)
        collapsed = " ".join((self.runbook + " " + self.batch).split())
        for phrase in (
            "changes the acceptance contract",
            "does not start RetroArch",
            "only L3 and R3",
            "click and release the left stick cap once",
            "click and release the right stick cap once",
            "composite evidence",
            "must not be described as one simultaneous 16-key trial",
            "one targeted window",
            "Do not retry",
        ):
            self.assertIn(phrase, collapsed)

    def _extract_awk_program(self, variable: str) -> str:
        match = re.search(
            rf"(?ms)^{variable}='\n(.*?)'\nreadonly {variable}$", self.runner
        )
        self.assertIsNotNone(match)
        return match.group(1)  # type: ignore[union-attr]

    def test_parsers_accept_exact_l3r3_fixture(self) -> None:
        events = textwrap.dedent(
            '''\
            Input device name: "R46H Combined Gamepad"
            Event: time 1.0, type 1 (EV_KEY), code 706 (BTN_TRIGGER_HAPPY3), value 1
            Event: time 1.1, type 1 (EV_KEY), code 706 (BTN_TRIGGER_HAPPY3), value 0
            Event: time 2.0, type 1 (EV_KEY), code 707 (BTN_TRIGGER_HAPPY4), value 1
            Event: time 2.1, type 1 (EV_KEY), code 707 (BTN_TRIGGER_HAPPY4), value 0
            '''
        )
        diagnostics = textwrap.dedent(
            """\
            R46H_INPUT_BRIDGE_DIAGNOSTIC kind=header version=r46h-gaming-input-bridge-v0.5 bridge_status=pass uinput_write_failures=0 failed_type=-1 failed_code=-1 failed_value=-1
            R46H_INPUT_BRIDGE_DIAGNOSTIC kind=key code=BTN_TRIGGER_HAPPY3 source_presses=1 source_releases=1 source_other=0 source_last=0 emitted_presses=1 emitted_releases=1 emitted_other=0 emitted_last=0
            R46H_INPUT_BRIDGE_DIAGNOSTIC kind=key code=BTN_TRIGGER_HAPPY4 source_presses=1 source_releases=1 source_other=0 source_last=0 emitted_presses=1 emitted_releases=1 emitted_other=0 emitted_last=0
            R46H_INPUT_BRIDGE_DIAGNOSTIC kind=syn source_reports=7 emitted_reports=7
            """
        )
        with tempfile.TemporaryDirectory() as directory:
            event_path = Path(directory) / "events.txt"
            diagnostic_path = Path(directory) / "diagnostics.txt"
            event_path.write_text(events, encoding="utf-8")
            diagnostic_path.write_text(diagnostics, encoding="utf-8")
            happy3 = subprocess.run(
                [
                    "awk",
                    "-v",
                    "wanted=BTN_TRIGGER_HAPPY3",
                    self._extract_awk_program("KEY_AWK"),
                    str(event_path),
                ],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
            bridge_happy4 = subprocess.run(
                [
                    "awk",
                    "-v",
                    "wanted=BTN_TRIGGER_HAPPY4",
                    self._extract_awk_program("BRIDGE_KEY_AWK"),
                    str(diagnostic_path),
                ],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
            header = subprocess.run(
                ["awk", self._extract_awk_program("BRIDGE_HEADER_AWK"), str(diagnostic_path)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
            syn = subprocess.run(
                ["awk", self._extract_awk_program("BRIDGE_SYN_AWK"), str(diagnostic_path)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
        self.assertEqual(happy3.stdout.strip(), "1 1 0 0")
        self.assertEqual(bridge_happy4.stdout.strip(), "1 1 0 0 1 1 0 0")
        self.assertEqual(
            header.stdout.strip(), "r46h-gaming-input-bridge-v0.5 pass 0 -1 -1 -1"
        )
        self.assertEqual(syn.stdout.strip(), "7 7")


if __name__ == "__main__":
    unittest.main()
