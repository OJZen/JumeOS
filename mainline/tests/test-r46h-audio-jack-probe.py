#!/usr/bin/env python3
"""Safety and behavior checks for the bounded RK817 jack probe."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "mainline/bringup-tests/r46h-audio-jack-probe.c"
RUNBOOK = REPO_ROOT / "mainline/bringup-tests/AUDIO-JACK-PROBE.md"
EXPECTED_SOURCE_SHA256 = (
    "72e22b60ac007c37faacc8c7d2aacb7157126761b6d1e3e847027cf6d96abddc"
)
EXPECTED_BINARY_SHA256 = (
    "41dbe0e95ef6e6e2fe614c5acdcd18507714cc4cf94616b8745527bf39657d3e"
)


class R46HAudioJackProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.runbook = RUNBOOK.read_text(encoding="utf-8")

    def test_source_identity_and_runbook_pin(self) -> None:
        digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        self.assertEqual(digest, EXPECTED_SOURCE_SHA256)
        self.assertEqual(self.runbook.count(digest), 2)
        self.assertEqual(self.runbook.count(EXPECTED_BINARY_SHA256), 2)
        self.assertEqual(stat.S_IMODE(SOURCE.stat().st_mode), 0o644)

    def test_exact_target_and_unique_evdev_identity_are_required(self) -> None:
        for value in (
            "r46h-audio-jack-probe-v0.1",
            "6.12.99-r46h-mainline-v0.10-adc-full-range",
            "GameConsole R46H",
            "rk817_int Headphones",
            'opendir("/dev/input")',
            "major(before.st_rdev) != INPUT_MAJOR",
            "after.st_ino != before.st_ino",
            "after.st_rdev != before.st_rdev",
            "errno = ENOTUNIQ",
        ):
            self.assertIn(value, self.source)
        self.assertIn("O_RDONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW", self.source)

    def test_probe_has_no_input_grab_or_audio_mutation(self) -> None:
        for forbidden in (
            "EVIOCGRAB",
            "O_RDWR",
            "O_WRONLY",
            "amixer",
            "speaker-test",
            "alsactl",
            "modprobe",
            "/sys/class/sound",
        ):
            self.assertNotIn(forbidden, self.source)
        self.assertIn("EVIOCGNAME", self.source)
        self.assertIn("EVIOCGBIT", self.source)
        self.assertIn("EVIOCGSW", self.source)

    def test_transition_contract_is_fail_closed_and_bounded(self) -> None:
        for value in (
            "OBSERVE_SECONDS 30",
            "SW_HEADPHONE_INSERT",
            "headphones-must-start-removed",
            "required-transitions-missing",
            "headphones-not-removed",
            "switch-state-inconsistent",
            "SYN_DROPPED",
            "syn-dropped",
            "insert-remove-observed",
        ):
            self.assertIn(value, self.source)
        self.assertRegex(
            self.source,
            r"insertions >= 1 && observation\.removals >= 1 &&\s+"
            r"observation\.last_state == 0",
        )

    def test_signal_and_terminal_result_contract(self) -> None:
        for signal in ("SIGINT", "SIGTERM", "SIGHUP"):
            self.assertIn(f"sigaction({signal}", self.source)
        self.assertIn("status = 128 + stop_signal", self.source)
        self.assertEqual(self.source.count("R46H_AUDIO_JACK_PROBE id=%s result=%s"), 1)
        self.assertNotIn("fork(", self.source)
        self.assertNotIn("system(", self.source)

    def test_documentation_keeps_evidence_boundaries_narrow(self) -> None:
        for statement in (
            "does not play audio",
            "does not require a v0.11 kernel",
            "No TF-card rewrite is needed",
            "no `EVIOCGRAB`",
            "must start with the headphones removed",
            "no headphones were available",
            "not** evidence of a broken jack GPIO",
            "physical FAIL of the current jack-detect event contract",
            "insertions=0 removals=0 final=0 syn_dropped=0",
            "does not prove headphone output or automatic speaker muting",
            "does not extend the jack-detect boundary",
            "7ee9d17afa1cc17ceecfbb66da62cb2dc0643537948d544f39cfafecada8896f",
            "21a4f19b270ac0a6a1591bd823500bd8d65cfedac61e6e1bcb4a98b8947fb57b",
        ):
            self.assertIn(statement, self.runbook)
        self.assertRegex(
            self.runbook, r"does not prove headphone audio,\s+automatic speaker muting"
        )

    @unittest.skipUnless(
        sys.platform.startswith("linux") and shutil.which("cc") is not None,
        "Linux evdev headers and a native C compiler are required",
    )
    def test_linux_build_selftest_help_and_invalid_argument(self) -> None:
        requested_root = os.environ.get("R46H_TEST_TMPDIR")
        if requested_root:
            temporary_parent = Path(requested_root)
            temporary_parent.mkdir(parents=True, exist_ok=True)
            directory_context = tempfile.TemporaryDirectory(
                prefix="r46h-audio-jack-test.", dir=temporary_parent
            )
        else:
            directory_context = tempfile.TemporaryDirectory(
                prefix="r46h-audio-jack-test."
            )
        with directory_context as directory:
            binary = Path(directory) / "r46h-audio-jack-probe"
            subprocess.run(
                [
                    "cc",
                    "-std=c11",
                    "-O2",
                    "-Wall",
                    "-Wextra",
                    "-Werror",
                    "-o",
                    str(binary),
                    str(SOURCE),
                ],
                check=True,
            )
            selftest = subprocess.run(
                [str(binary), "--self-test"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertIn("R46H_AUDIO_JACK_SELFTEST result=pass", selftest.stdout)
            help_run = subprocess.run(
                [str(binary), "--help"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertIn("at most 30 seconds", help_run.stdout)
            invalid = subprocess.run(
                [str(binary), "--unknown"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(invalid.returncode, 2)


if __name__ == "__main__":
    unittest.main()
