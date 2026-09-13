#!/usr/bin/env python3
"""Regression gates for the bounded R46H USB-DC observation probe."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "mainline/bringup-tests/r46h-charger-observe.c"
RUNBOOK = REPO / "mainline/bringup-tests/CHARGER-DC-DETECT-PROBE.md"
CACHE = REPO / "mainline/out/.cache"
SOURCE_SHA256 = "937428e1393da7e9ec2b984f0dc27e818b68f2d6b9c315fb7874382d9a698e04"
BINARY_SHA256 = "6368e7936c1e4f06626d96b9b1e4b0231568912a9c44205a95a0d19d77087ef3"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ChargerObserveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")
        cls.runbook = RUNBOOK.read_text(encoding="utf-8")

    def test_exact_source_and_published_binary_are_pinned(self) -> None:
        self.assertEqual(sha256(SOURCE), SOURCE_SHA256)
        self.assertIn(SOURCE_SHA256, self.runbook)
        self.assertIn(BINARY_SHA256, self.runbook)
        self.assertIn("72,192-byte ARM64 binary", self.runbook)

    def test_probe_is_bound_to_exact_v08_target_and_vendor_line(self) -> None:
        for literal in (
            'EXPECTED_RELEASE "6.12.99-r46h-mainline-v0.8-bootloader-handoff"',
            'GPIO_CHIP_PATH "/dev/gpiochip0"',
            "DC_DETECT_OFFSET 11U",
            '"GameConsole R46H"',
            '"rockchip,rk3326-r46h-linux\\0rockchip,rk3326"',
            'CHARGER_DT_ROOT "/dc-det-gpios"',
            'CHARGER_DT_ROOT "/dc_det_gpio"',
            'CHARGER_DT_ROOT "/extcon"',
        ):
            self.assertIn(literal, self.source)

    def test_gpio_request_is_input_only_and_refuses_an_owned_line(self) -> None:
        self.assertIn("GPIO_V2_LINE_FLAG_USED", self.source)
        self.assertIn("errno = EBUSY", self.source)
        self.assertIn(
            "request.config.flags = GPIO_V2_LINE_FLAG_INPUT;", self.source
        )
        self.assertNotIn("GPIO_V2_LINE_FLAG_OUTPUT", self.source)
        self.assertNotIn("GPIO_V2_LINE_SET_VALUES_IOCTL", self.source)
        self.assertNotIn("GPIO_V2_LINE_SET_CONFIG_IOCTL", self.source)
        self.assertIn("GPIO_V2_LINE_GET_VALUES_IOCTL", self.source)
        self.assertIn("SAMPLE_COUNT 5U", self.source)
        self.assertIn("SAMPLE_INTERVAL_MS 20U", self.source)

    def test_paths_are_opened_read_only_and_bound_to_the_open_fd(self) -> None:
        self.assertIn("lstat(path, &path_stat)", self.source)
        self.assertIn("O_RDONLY | O_CLOEXEC | O_NOFOLLOW", self.source)
        self.assertIn("fstat(fd, &fd_stat)", self.source)
        self.assertIn("path_stat.st_ino != fd_stat.st_ino", self.source)
        self.assertIn("path_stat.st_rdev != fd_stat.st_rdev", self.source)
        for forbidden in (
            "O_WRONLY",
            "O_RDWR",
            "pwrite(",
            "write(",
            "GPIOHANDLE_SET_LINE_VALUES_IOCTL",
            "/dev/mem",
            "/dev/i2c",
            "mount(",
            "umount(",
            "system(",
        ):
            self.assertNotIn(forbidden, self.source)

    def test_both_phases_require_the_mainline_mismatch(self) -> None:
        self.assertIn("--expect-disconnected", self.source)
        self.assertIn("--expect-connected-mismatch", self.source)
        self.assertIn('"connected-mismatch" : "disconnected"', self.source)
        self.assertIn("expected_level =", self.source)
        self.assertIn("before.charger_online != 0", self.source)
        self.assertIn("before.charger_voltage_uv != 0", self.source)
        self.assertIn('strcmp(before.battery_status, "Discharging")', self.source)
        self.assertIn("critical_snapshot_equal(&before, &after)", self.source)

    def test_result_is_published_only_after_line_fd_cleanup(self) -> None:
        close_position = self.source.index("if (line_fd >= 0 && close(line_fd) < 0)")
        pass_position = self.source.index("R46H_CHARGER_OBSERVE result=pass")
        self.assertLess(close_position, pass_position)
        self.assertIn("drive_output=no persistent_change=no cleanup=pass", self.source)

    def test_runbook_pins_primary_sources_and_existing_live_evidence(self) -> None:
        for evidence in (
            "9ead5f3cbd6e0abd0ac70002205993c953c227ea",
            "d6ee5763f8e2063bc7dca24be4d35e480f3b6c1098e21f5dfaa5ecf59f70e2c4",
            "6a477222c132033381cda981eb0127f29fbcbba17e820283bc21290f8e408629",
            "eb06785415e3a49cbbbd472c79958ed06bef8cd62eb72c368ecfc691f6389b6b",
            "8600e076cc676f3c4350c992bf6644287290cf567ead94e8ba54ff4bbc3e172a",
            "dc_det_gpio = <&gpio0 11 GPIO_ACTIVE_HIGH>;",
            "One disconnect/reconnect cycle is sufficient",
            "does not prove that charging current is safe",
        ):
            self.assertIn(evidence, self.runbook)

    @unittest.skipUnless(
        os.environ.get("R46H_RUN_CHARGER_PROBE_BUILD") == "1",
        "set R46H_RUN_CHARGER_PROBE_BUILD=1 for the pinned ARM64 build gate",
    )
    def test_pinned_arm64_builder_reproduces_binary(self) -> None:
        docker = shutil.which("docker")
        self.assertIsNotNone(docker, "docker is required for the opt-in build gate")
        CACHE.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="r46h-charger-probe-test.", dir=CACHE
        ) as temporary:
            output = Path(temporary) / "r46h-charger-observe"
            subprocess.run(
                [
                    docker,
                    "run",
                    "--rm",
                    "--entrypoint",
                    "/bin/bash",
                    "-v",
                    f"{REPO}:/repo:ro",
                    "-v",
                    f"{temporary}:/out",
                    "arkos4clone/r46h-kernel-builder:trixie-arm64",
                    "-lc",
                    "cc -std=c11 -O2 -Wall -Wextra -Werror "
                    "-Wconversion -Wsign-conversion -Wshadow "
                    "/repo/mainline/bringup-tests/r46h-charger-observe.c "
                    "-o /out/r46h-charger-observe",
                ],
                check=True,
                cwd=REPO,
            )
            self.assertEqual(output.stat().st_size, 72192)
            self.assertEqual(sha256(output), BINARY_SHA256)


if __name__ == "__main__":
    unittest.main()
