#!/usr/bin/env python3
"""Safety and behavior checks for the R46H jack localization probe."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "mainline/bringup-tests/r46h-audio-jack-localize.c"
RUNBOOK = REPO_ROOT / "mainline/bringup-tests/AUDIO-JACK-LOCALIZATION.md"
EXPECTED_SOURCE_SHA256 = (
    "7eb0a8aa044822f9cf53f18bccec47441550a1a0c5e72782e2cb1625e2f44014"
)
EXPECTED_BINARY_SHA256 = (
    "d88b5668384405cf52c3bf8d884ed2b881db50aef92e08406319fe23d64ad814"
)


class R46HAudioJackLocalizeTests(unittest.TestCase):
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

    def test_exact_target_evdev_and_gpio_identity_are_required(self) -> None:
        for value in (
            "r46h-audio-jack-localize-v0.1",
            "6.12.99-r46h-mainline-v0.10-adc-full-range",
            "GameConsole R46H",
            "rk817_int Headphones",
            'GPIO_DEBUG_PATH "/sys/kernel/debug/gpio"',
            'GPIO_LINE_NAME "Headphone detection"',
            'GPIO_NUMBER_TEXT "gpio-86"',
            'strstr(cursor, " IRQ ACTIVE LOW")',
            "major(before.st_rdev) != INPUT_MAJOR",
            "after.st_ino != before.st_ino",
            "after.st_rdev != before.st_rdev",
            "errno = ENOTUNIQ",
        ):
            self.assertIn(value, self.source)

    def test_probe_is_read_only_and_does_not_request_gpio(self) -> None:
        for forbidden in (
            "EVIOCGRAB",
            "O_RDWR",
            "O_WRONLY",
            "O_CREAT",
            "amixer",
            "speaker-test",
            "alsactl",
            "gpiod_",
            "GPIO_GET_LINEHANDLE_IOCTL",
            "/sys/class/gpio/export",
            "pinctrl-select",
            "system(",
            "fork(",
        ):
            self.assertNotIn(forbidden, self.source)
        self.assertIn("O_RDONLY | O_CLOEXEC | O_NOFOLLOW", self.source)
        self.assertIn("O_RDONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW", self.source)

    def test_observation_is_bounded_and_samples_both_paths(self) -> None:
        for value in (
            "OBSERVE_SECONDS 30",
            "GPIO_SAMPLE_MILLISECONDS 20",
            "EVDEV_SETTLE_MILLISECONDS 500",
            "SW_HEADPHONE_INSERT",
            "SYN_DROPPED",
            "query_gpio_raw()",
            "query_headphone_state(fd)",
            "headphones-must-start-removed",
            "headphones-not-removed",
            "operator-signal",
            "R46H_AUDIO_JACK_LOCALIZE id=%s result=%s",
        ):
            self.assertIn(value, self.source)

    def test_localization_classes_are_explicit_and_fail_closed(self) -> None:
        for value in (
            "both-paths-observed",
            "evdev-transitions-missing",
            "evdev-or-asoc-path",
            "gpio-samples-inconsistent",
            "debug-gpio-path",
            "gpio-transitions-missing",
            "gpio-mux-electrical-or-socket-path",
        ):
            self.assertIn(value, self.source)
        self.assertIn('*result = "fail";', self.source)
        self.assertEqual(self.source.count('*result = "pass";'), 1)

    def test_runbook_preserves_evidence_and_safety_boundaries(self) -> None:
        runbook = " ".join(self.runbook.split())
        for value in (
            "PHYSICAL FAIL / NO GPIO2_C6 OR EVDEV TRANSITIONS / ROUTE SKIPPED",
            "does not replace or repeat the unchanged v0.1 gate",
            "No TF-card rewrite or kernel change is needed",
            "must not be run with `gpioget`",
            "read-only",
            "one insert/remove cycle",
            "gpio-mux-electrical-or-socket-path",
            "evdev-or-asoc-path",
            "does not authorize headphone playback",
            "2026-08-19",
            "Physical result: 2026-08-20",
            "reason=gpio-transitions-missing",
            "Do not repeat this unchanged localizer",
        ):
            self.assertIn(value, runbook)

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
                prefix="r46h-audio-jack-localize-test.", dir=temporary_parent
            )
        else:
            directory_context = tempfile.TemporaryDirectory(
                prefix="r46h-audio-jack-localize-test."
            )
        with directory_context as directory:
            binary = Path(directory) / "r46h-audio-jack-localize"
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
            self.assertIn(
                "R46H_AUDIO_JACK_LOCALIZE_SELFTEST result=pass", selftest.stdout
            )
            help_run = subprocess.run(
                [str(binary), "--help"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertIn("does not request a GPIO", help_run.stdout)
            invalid = subprocess.run(
                [str(binary), "--unknown"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(invalid.returncode, 2)


if __name__ == "__main__":
    unittest.main()
