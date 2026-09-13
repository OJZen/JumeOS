#!/usr/bin/env python3
"""Static and host-side behavior tests for the attended RK817 route probe."""

from __future__ import annotations

from pathlib import Path
import hashlib
import re
import stat
import subprocess
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "mainline/bringup-tests/r46h-audio-route-probe"
RUNBOOK = REPO_ROOT / "mainline/bringup-tests/AUDIO-ROUTE-PROBE.md"


class R46HAudioRouteProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SCRIPT.read_text(encoding="utf-8")
        cls.runbook = RUNBOOK.read_text(encoding="utf-8")

    def test_syntax_help_arguments_and_permissions(self) -> None:
        subprocess.run(["/bin/bash", "-n", str(SCRIPT)], check=True)
        help_run = subprocess.run(
            ["/bin/bash", str(SCRIPT), "--help"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        help_text = " ".join(help_run.stdout.split())
        self.assertIn("--hp-external-amp", help_text)
        self.assertIn("--headphones-mechanical", help_text)
        self.assertIn("operator must state where the tone was heard", help_text)
        invalid = subprocess.run(
            ["/bin/bash", str(SCRIPT), "--unknown"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertEqual(invalid.returncode, 2)
        markers = [
            line
            for line in invalid.stdout.splitlines()
            if line.startswith("R46H_AUDIO_ROUTE_PROBE ")
        ]
        self.assertEqual(len(markers), 1)
        self.assertIn("result=fail", markers[0])
        self.assertEqual(stat.S_IMODE(SCRIPT.stat().st_mode), 0o755)

    def test_runbook_pins_script_and_observation_boundary(self) -> None:
        digest = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
        self.assertEqual(
            digest,
            "db7fce6727e70fef11f6fc25530024db3ee8a132a7a00183d698b2577710077a",
        )
        self.assertEqual(self.runbook.count(digest), 2)
        self.assertEqual(
            self.runbook.count(
                "2bfa8d284d14d231a76d3660d7bd96a896a91147e8f53fc2e5e5dc3436bc508b"
            ),
            2,
        )
        self.assertEqual(
            self.runbook.count(
                "1af064e3d20f12f86127d385a613b6eb99e4e800c5ea401f564aeaa4cae10a97"
            ),
            2,
        )
        self.assertIn("result=observation-required", self.runbook)
        self.assertRegex(self.runbook, r"never prove audible\s+output")
        self.assertIn("do not invent an enable GPIO", self.runbook)
        self.assertIn(
            "HEADPHONE OUTPUT + MECHANICAL SPEAKER\nCUT-OFF PASS", self.runbook
        )
        self.assertIn(
            "The 2026-08-19 replacement-headset session did not execute this mode",
            self.runbook,
        )
        self.assertRegex(
            self.runbook,
            r"At that gate, headphone output and\s+automatic speaker muting "
            r"remained \*\*UNTESTED\*\*",
        )
        self.assertIn("2026-08-23 under exact persistent v0.10", self.runbook)
        self.assertIn(
            "ececb7460ce08bf07cec5d329627b193338237d092146eb216ee515bd8420083",
            self.runbook,
        )
        self.assertRegex(
            self.runbook,
            r"audible in the fully inserted headset while the built-in speaker was silent",
        )
        self.assertIn("does not repair the failed jack-detect path", self.runbook)

    def test_exact_release_media_and_runtime_identity_are_pinned(self) -> None:
        for value in (
            "r46h-audio-route-probe-v0.4",
            "6.12.99-r46h-mainline-v0.10-adc-full-range",
            "/dev/mmcblk0p2",
            "c9f931c9-02",
            "d3130001-46a4-4d56-9001-000000000001",
            "GameConsole R46H",
            "/run/r46h-audio-route-probe",
        ):
            self.assertIn(value, self.source)
        self.assertIn("0:700:1", self.source)
        self.assertIn("findmnt -rn -T /run -o FSTYPE", self.source)
        self.assertIn("mktemp -d /run/r46h-audio-route-probe.XXXXXX", self.source)

    def test_probe_reproduces_downstream_hp_dac_route_without_kernel_write(self) -> None:
        self.assertIn("TEST_MUX=0", self.source)
        self.assertIn("TEST_ROUTE=HP", self.source)
        self.assertIn('cset "numid=$MUX_CONTROL" "$TEST_MUX"', self.source)
        self.assertIn("Speaker: On", self.source)
        self.assertIn("Headphones: Off", self.source)
        self.assertNotIn("Speaker: Off", self.source)
        self.assertNotIn("Headphones: On", self.source)
        self.assertNotIn("--headphones-inserted", self.source)
        self.assertIn("--headphones-mechanical", self.source)
        self.assertIn("operator-mechanical-headphone-audio-and-speaker-silence-required", self.source)
        self.assertIn("operator-audibility-required", self.source)
        self.assertIn("it does not repeat jack detection", self.source)
        self.assertIn("result=%s", self.source)
        self.assertNotIn("of_property", self.source)
        self.assertNotIn("/proc/device-tree/codec", self.source)
        for forbidden in (
            r"\bmodprobe\b",
            r"\bmount\b",
            r"\bumount\b",
            r"\b(?:i2cset|devmem|memtool)\b",
            r"/sys/[A-Za-z0-9_./-]+\s*(?:>|>>)",
        ):
            self.assertIsNone(re.search(forbidden, self.source))

    def test_playback_is_bounded_and_low_level(self) -> None:
        self.assertIn("TEST_VOLUME=201,201", self.source)
        self.assertIn("TEST_SCALE=40", self.source)
        self.assertIn("test_seconds=4", self.source)
        self.assertIn("test_seconds=2", self.source)
        self.assertIn("setsid timeout -s TERM -k 2s", self.source)
        self.assertIn("speaker-test -D hw:0,0 -c 2 -t sine", self.source)
        self.assertIn('[[ "$probe_status" == 124 ]]', self.source)
        self.assertIn("headset-fully-inserted-earpieces-away-from-ears", self.source)
        self.assertIn("R46H-HEADPHONE-READY", self.source)
        self.assertLess(
            self.source.index("R46H_AUDIO_ROUTE_READY mode=headphones-mechanical"),
            self.source.index(
                'amixer -q -c 0 cset "numid=$VOLUME_CONTROL" "$TEST_VOLUME"'
            ),
        )
        self.assertNotIn("GPIO2_C6", self.source)
        self.assertNotIn("audio-jack", self.source)

    def test_original_mixer_state_is_restored_on_all_exits(self) -> None:
        self.assertIn("trap cleanup EXIT", self.source)
        self.assertIn("restore_state", self.source)
        self.assertIn('cset "numid=$VOLUME_CONTROL" "$saved_volume"', self.source)
        self.assertIn('cset "numid=$MUX_CONTROL" "$saved_mux"', self.source)
        self.assertIn("R46H_AUDIO_ROUTE_RESTORE", self.source)
        self.assertLess(
            self.source.index("restore_state()"),
            self.source.index("R46H_AUDIO_ROUTE_OBSERVATION phase=start"),
        )

    def test_post_checks_and_terminal_semantics_are_fail_closed(self) -> None:
        for value in (
            "ext4-errors-before",
            "ext4-errors-after",
            "failed-units-before",
            "failed-units-after",
            "dmesg-prefix",
            "dmesg-new-faults",
            "observation-required",
            "frontend-inactive",
            "retroarch-inactive",
        ):
            self.assertIn(value, self.source)
        self.assertIn("completed=1", self.source)
        self.assertIn("cleanup_status", self.source)
        self.assertNotIn("safe_to_boot", self.source.lower())


if __name__ == "__main__":
    unittest.main()
