#!/usr/bin/env python3
"""Safety and acceptance tests for the bounded R46H rumble probe."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "mainline/bringup-tests/r46h-rumble-probe.c"
RUNBOOK = REPO_ROOT / "mainline/bringup-tests/RUMBLE-PROBE.md"
BUILDER = "arkos4clone/r46h-kernel-builder:trixie-arm64"


class R46HRumbleProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.runbook = RUNBOOK.read_text(encoding="utf-8")

    def test_exact_device_identity_and_fd_binding(self) -> None:
        for value in (
            'strcmp(name, "pwm-vibrator")',
            "id.bustype != BUS_HOST",
            "id.vendor != 0U",
            "EVIOCGNAME",
            "EVIOCGID",
            "EVIOCGBIT(0",
            "EVIOCGBIT(EV_FF",
            "EVIOCGEFFECTS",
            "FF_RUMBLE",
            "O_NOFOLLOW",
            "path_stat.st_rdev != fd_stat.st_rdev",
            "path_stat.st_ino != fd_stat.st_ino",
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.source)
        self.assertIn("lstat(path, &path_stat)", self.source)
        self.assertIn("fstat(fd, &fd_stat)", self.source)

    def test_effect_is_fixed_short_and_moderate(self) -> None:
        self.assertIn("#define RUMBLE_DURATION_MS 750U", self.source)
        self.assertIn("#define RUMBLE_MAGNITUDE UINT16_C(0x8000)", self.source)
        self.assertIn("effect.type = FF_RUMBLE", self.source)
        self.assertIn("effect.id = -1", self.source)
        self.assertIn("effect.replay.length = RUMBLE_DURATION_MS", self.source)
        self.assertIn("effect.u.rumble.strong_magnitude = RUMBLE_MAGNITUDE", self.source)
        self.assertNotIn("FF_GAIN", self.source)
        self.assertIn("operator_observation=required", self.source)

    def test_cleanup_and_signal_paths_are_explicit(self) -> None:
        for value in (
            "sigaction(SIGINT",
            "sigaction(SIGTERM",
            "sigaction(SIGHUP",
            "write_event(fd, (uint16_t)effect.id, 0)",
            "ioctl(fd, EVIOCRMFF, effect.id)",
            "sleep_ms(50U)",
            'cleanup_failed ? "fail" : "pass"',
        ):
            with self.subTest(value=value):
                self.assertIn(value, self.source)
        self.assertLess(
            self.source.index("write_event(fd, (uint16_t)effect.id, 0)"),
            self.source.index("ioctl(fd, EVIOCRMFF, effect.id)"),
        )
        self.assertLess(
            self.source.index("ioctl(fd, EVIOCRMFF, effect.id)"),
            self.source.index("close(fd)"),
        )

    def test_mutation_scope_is_only_the_force_feedback_fd(self) -> None:
        forbidden = (
            r"\bopenat\s*\(",
            r"\bpwrite\w*\s*\(",
            r"\bfsync\s*\(",
            r"\bsystem\s*\(",
            r"\bmount\s*\(",
            r"\bmodprobe\b",
            r"EVIOCGRAB",
            r"O_CREAT",
            r"O_TRUNC",
        )
        for pattern in forbidden:
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, self.source))
        self.assertEqual(self.source.count("written = write(fd, &event"), 1)
        self.assertRegex(self.runbook, r"do not install it\s+into p2")

    def test_runbook_pins_accepted_source_binary_and_serial(self) -> None:
        source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
        self.assertEqual(
            source_hash,
            "c7490cc5f9f647383c25559d8a312d98e4edd9ad01c954ffc5d4038aa21e06f9",
        )
        self.assertEqual(self.runbook.count(source_hash), 1)
        for digest in (
            "99a01fb6996e785d0a0745f990ca3b07c1dc68a346d44790b745ae35f181e34b",
            "3321f0cb76f7aca236e70424a97b2cbe17217fbfd0c10d494959ac42d3c117ac",
        ):
            with self.subTest(digest=digest):
                self.assertIn(digest, self.runbook)
        self.assertRegex(self.runbook, r"explicitly felt by the\s+operator")
        self.assertIn("Do not repeat the direct hardware pulse", self.runbook)

    @unittest.skipUnless(
        os.environ.get("R46H_RUN_RUMBLE_PROBE_BUILD") == "1",
        "set R46H_RUN_RUMBLE_PROBE_BUILD=1 for the ARM64 Docker compile gate",
    )
    def test_arm64_probe_builds_with_warnings_as_errors(self) -> None:
        output = REPO_ROOT / "mainline/out/.cache/r46h-rumble-probe-test"
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
        try:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--user",
                    f"{os.getuid()}:{os.getgid()}",
                    "-v",
                    f"{SOURCE.parent}:/src:ro",
                    "-v",
                    f"{output}:/out",
                    "-w",
                    "/out",
                    "--entrypoint",
                    "/bin/bash",
                    BUILDER,
                    "-lc",
                    "gcc -std=c11 -O2 -Wall -Wextra -Werror "
                    "-o r46h-rumble-probe /src/r46h-rumble-probe.c",
                ],
                check=True,
            )
            self.assertTrue((output / "r46h-rumble-probe").is_file())
        finally:
            for child in output.iterdir():
                child.unlink()
            output.rmdir()


if __name__ == "__main__":
    unittest.main()
