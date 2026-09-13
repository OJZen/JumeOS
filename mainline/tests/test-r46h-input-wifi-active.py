#!/usr/bin/env python3
"""Safety and parser tests for the R46H input/Wi-Fi active gates."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import textwrap
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "mainline/bringup-tests/r46h-input-wifi-active"
README = REPO_ROOT / "mainline/bringup-tests/INPUT-WIFI-ACTIVE.md"


class R46HInputWifiActiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SCRIPT.read_text(encoding="utf-8")
        cls.readme = README.read_text(encoding="utf-8")

    def test_shell_syntax_help_modes_and_permissions(self) -> None:
        subprocess.run(["/bin/bash", "-n", str(SCRIPT)], check=True)
        help_run = subprocess.run(
            ["/bin/bash", str(SCRIPT), "--help"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertIn("--wifi-scan", help_run.stdout)
        self.assertIn("--input-capture", help_run.stdout)
        self.assertIn("without credentials or saved configuration", help_run.stdout)
        self.assertEqual(stat.S_IMODE(SCRIPT.stat().st_mode), 0o755)
        invalid = subprocess.run(
            ["/bin/bash", str(SCRIPT), "--wifi-scan", "--input-capture"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(invalid.returncode, 2)

    def test_active_mode_without_root_tty_fails_with_one_terminal_marker(self) -> None:
        run = subprocess.run(
            ["/bin/bash", str(SCRIPT), "--wifi-scan"],
            text=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(run.returncode, 1)
        markers = [
            line
            for line in run.stdout.splitlines()
            if line.startswith("R46H_INPUT_WIFI_ACTIVE ")
        ]
        self.assertEqual(len(markers), 1)
        self.assertIn("mode=wifi-scan result=fail", markers[0])
        self.assertRegex(markers[0], r"reason=(?:not-root|interactive-tty-required)")
        self.assertEqual(run.stdout.splitlines()[-1], markers[0])

    def test_target_and_script_identity_are_fail_closed(self) -> None:
        for value in (
            "r46h-input-wifi-active-v0.1",
            "6.12.99-r46h-mainline-v0.8-bootloader-handoff",
            "/dev/mmcblk0p2",
            "c9f931c9-02",
            "d3130001-46a4-4d56-9001-000000000001",
            "release=debian13-p2-mvp-v0.1",
            "00E04C8188FF",
            "00:e0:4c:81:88:ff",
            "GameConsole R46H",
        ):
            self.assertIn(value, self.source)
        self.assertIn("[[ -t 0 && -t 1 && -t 2 ]]", self.source)
        self.assertIn("interactive-tty-required", self.source)
        self.assertIn("${BASH_SOURCE[0]}\" == \"$REQUIRED_SCRIPT_PATH", self.source)
        self.assertIn("0:700:1", self.source)
        self.assertIn("0:600:1", self.source)
        self.assertIn("failed-units-before", self.source)
        self.assertIn("failed-units-after", self.source)

    def test_all_runtime_writes_are_bounded_to_run_tmpfs(self) -> None:
        self.assertIn("findmnt -rn -T /run -o FSTYPE", self.source)
        self.assertIn("== tmpfs", self.source)
        self.assertIn("mktemp -d /run/r46h-input-wifi-active.XXXXXX", self.source)
        self.assertIn("/run/r46h-input-wifi-active.lock", self.source)
        self.assertIn('rm -rf -- "$path"', self.source)
        self.assertNotRegex(
            self.source,
            r"(?m)(?:>|>>|\btee\b)[^\n]*(?:/etc|/boot|/roms|/var|/sys|/proc)/",
        )
        self.assertNotIn("/run/lock/", self.source)

    def test_wifi_is_passive_scan_only(self) -> None:
        self.assertIn('iw dev "$wifi_iface" scan passive', self.source)
        self.assertIn('"$WIFI_SCAN_TIMEOUT_SECONDS"', self.source)
        self.assertIn("source=usb-serial", self.source)
        self.assertIn("0bda", self.source)
        self.assertIn("8179", self.source)
        self.assertIn("rtl8xxxu", self.source)
        self.assertIn("bss-observed", self.source)
        self.assertIn('$2 ~ /^[0-9A-Fa-f][0-9A-Fa-f]:/', self.source)
        self.assertIn("link-state-unchanged", self.source)
        self.assertIn("link-state-before", self.source)
        self.assertIn("link-state-after", self.source)
        self.assertIn("initially-unassociated", self.source)
        self.assertIn("association-unchanged", self.source)
        self.assertIn("Not connected.", self.source)
        forbidden = (
            r"\biw\b[^\n]*\bconnect\b",
            r"\biwconfig\b",
            r"\bwpa_(?:cli|supplicant)\b",
            r"\bnmcli\b",
            r"\bip\s+link\s+set\b",
            r"\brfkill\s+(?:block|unblock|toggle)\b",
            r"\bmodprobe\b",
            r"/etc/NetworkManager/system-connections",
        )
        for pattern in forbidden:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, self.source))

    def test_input_discovery_capture_and_acceptance_contract(self) -> None:
        for name in ("adc-joystick", "gpio-keys", "gpio-keys-vol"):
            self.assertIn(name, self.source)
        self.assertIn("/sys/class/input/event*/device/name", self.source)
        self.assertNotRegex(self.source, r"/dev/input/event[0-9]+")
        self.assertNotIn("--grab", self.source)
        self.assertIn("INPUT_WINDOW_SECONDS=60", self.source)
        self.assertIn("observed_span * 100 < advertised_span * 70", self.source)
        self.assertIn("initial_value < advertised_min", self.source)
        self.assertIn("observed_min < advertised_min", self.source)
        self.assertIn("observed_max > advertised_max", self.source)
        self.assertIn("last_value > advertised_max", self.source)
        self.assertIn("center_delta * 100 <= advertised_span * 70", self.source)
        self.assertIn("return_delta * 100 <= advertised_span * 10", self.source)
        self.assertIn("SYN_DROPPED", self.source)
        self.assertIn('index($0, "Event: time") && index($0, "SYN_DROPPED")', self.source)
        self.assertIn("presses >= 1 && releases >= 1 && last == 0", self.source)
        for code in (
            "BTN_DPAD_UP",
            "BTN_DPAD_DOWN",
            "BTN_DPAD_LEFT",
            "BTN_DPAD_RIGHT",
            "BTN_EAST",
            "BTN_SOUTH",
            "BTN_WEST",
            "BTN_NORTH",
            "BTN_TRIGGER_HAPPY3",
            "BTN_TRIGGER_HAPPY4",
            "BTN_TRIGGER_HAPPY5",
            "BTN_TL",
            "BTN_TR",
            "BTN_SELECT",
            "BTN_TR2",
            "BTN_TL2",
            "BTN_START",
            "KEY_VOLUMEDOWN",
            "KEY_VOLUMEUP",
            "ABS_X",
            "ABS_Y",
            "ABS_RX",
            "ABS_RY",
        ):
            self.assertIn(code, self.source)
        self.assertNotIn("rk805 pwrkey", self.source)

    def _extract_awk_program(self, variable: str) -> str:
        match = re.search(
            rf"(?ms)^{variable}='\n(.*?)'\nreadonly {variable}$", self.source
        )
        self.assertIsNotNone(match)
        return match.group(1)  # type: ignore[union-attr]

    def test_exact_axis_parser_with_signed_range_fixture(self) -> None:
        fixture = textwrap.dedent(
            """\
            Event type 3 (EV_ABS)
              Event code 1 (ABS_Y)
                Value   -518
                Min     -620
                Max        0
            Event: time 1.0, type 3 (EV_ABS), code 1 (ABS_Y), value -600
            Event: time 1.1, type 3 (EV_ABS), code 1 (ABS_Y), value -20
            Event: time 1.2, type 3 (EV_ABS), code 1 (ABS_Y), value -310
            """
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "joystick.txt"
            path.write_text(fixture, encoding="utf-8")
            run = subprocess.run(
                ["awk", "-v", "wanted=ABS_Y", self._extract_awk_program("AXIS_AWK"), str(path)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
        self.assertEqual(run.stdout.strip(), "-620 0 -518 -600 -20 -310 3")

    def test_exact_key_parser_counts_press_release_and_final_state(self) -> None:
        fixture = textwrap.dedent(
            """\
            Event: time 1.0, type 1 (EV_KEY), code 304 (BTN_SOUTH), value 1
            Event: time 1.1, type 1 (EV_KEY), code 304 (BTN_SOUTH), value 2
            Event: time 1.2, type 1 (EV_KEY), code 304 (BTN_SOUTH), value 0
            Event: time 1.3, type 1 (EV_KEY), code 305 (BTN_EAST), value 1
            """
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "keys.txt"
            path.write_text(fixture, encoding="utf-8")
            south = subprocess.run(
                ["awk", "-v", "wanted=BTN_SOUTH", self._extract_awk_program("KEY_AWK"), str(path)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
            east = subprocess.run(
                ["awk", "-v", "wanted=BTN_EAST", self._extract_awk_program("KEY_AWK"), str(path)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
        self.assertEqual(south.stdout.strip(), "1 1 0")
        self.assertEqual(east.stdout.strip(), "1 0 1")

    def test_exact_syn_parser_ignores_capability_and_counts_event(self) -> None:
        fixture = textwrap.dedent(
            """\
            Event code 3 (SYN_DROPPED)
            Event: time 1.0, -------------- SYN_REPORT ------------
            Event: time 1.1, -------------- SYN_DROPPED ------------
            """
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "events.txt"
            path.write_text(fixture, encoding="utf-8")
            run = subprocess.run(
                ["awk", self._extract_awk_program("SYN_AWK"), str(path)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            )
        self.assertEqual(run.stdout.strip(), "1")

    def test_timeout_signal_cleanup_and_single_terminal_contract(self) -> None:
        self.assertIn('setsid timeout -s TERM -k 5 "$worker_timeout"', self.source)
        self.assertIn("forward_signal()", self.source)
        self.assertIn("signal_status=130", self.source)
        self.assertIn("signal_status=143", self.source)
        self.assertIn("signal_status=129", self.source)
        self.assertIn("case $signal_status in", self.source)
        self.assertIn('safe_remove_lock "$lock_inode"', self.source)
        self.assertIn('safe_remove_session "$session_dir" "$session_inode"', self.source)
        self.assertEqual(
            self.source.count("R46H_INPUT_WIFI_ACTIVE id=%s mode=%s result=%s"), 1
        )
        self.assertIn("worker-marker-count", self.source)
        self.assertIn("worker-status-mismatch", self.source)
        self.assertIn("worker-process-leak", self.source)
        self.assertIn("supervisor_session_is_empty", self.source)
        self.assertIn("cleanup-failed", self.source)
        self.assertIn("dmesg-ring-prefix", self.source)
        self.assertIn("dmesg-new-faults", self.source)
        self.assertIn("dmesg-delta-capture", self.source)
        self.assertIn("ext4-errors-after", self.source)

    def test_runbook_preserves_evidence_boundaries(self) -> None:
        normalized_readme = re.sub(r"\s+", " ", self.readme)
        for phrase in (
            "Run only one mode at a time",
            "Passive Wi-Fi scan",
            "never accepts credentials",
            "Do not press Power or Reset",
            "zero `SYN_DROPPED`",
            "Missing operator actions are a normal, auditable failure",
            "UART log is the durable evidence",
            "result=pass",
            "cleanup=pass",
        ):
            self.assertIn(phrase, normalized_readme)
        script_hash = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
        self.assertEqual(
            self.readme.count(script_hash),
            2,
            "runbook must pin the reviewed host and target hashes",
        )


if __name__ == "__main__":
    unittest.main()
