#!/usr/bin/env python3
"""Focused host checks for the R46H 600--1008 MHz dynamic default."""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "mainline/gaming-shell/r46h-cpufreq-default"
UNIT = REPO / "mainline/gaming-shell/r46h-cpufreq-default.service"


class CpuFrequencyDefaultTests(unittest.TestCase):
    def fixture(self, directory: str, frequencies: str = "600000 816000 1008000 1200000 1296000") -> Path:
        policy = Path(directory) / "sys/devices/system/cpu/cpufreq/policy0"
        policy.mkdir(parents=True)
        values = {
            "scaling_available_frequencies": frequencies,
            "scaling_available_governors": "ondemand performance schedutil",
            "scaling_min_freq": "1200000",
            "scaling_max_freq": "1296000",
            "scaling_governor": "performance",
            "cpuinfo_min_freq": "600000",
            "cpuinfo_max_freq": "1296000",
        }
        for name, value in values.items():
            (policy / name).write_text(value + "\n", encoding="ascii")
        return policy

    def run_script(self, root: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SCRIPT)], env={**os.environ, "R46H_CPUFREQ_TEST_ROOT": root},
            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )

    def test_applies_supported_dynamic_range(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            policy = self.fixture(root)
            result = self.run_script(root)
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual((policy / "scaling_min_freq").read_text().strip(), "600000")
            self.assertEqual((policy / "scaling_max_freq").read_text().strip(), "1008000")
            self.assertEqual((policy / "scaling_governor").read_text().strip(), "schedutil")
            self.assertIn("result=pass governor=schedutil min_khz=600000 max_khz=1008000", result.stdout)

    def test_rejects_an_unavailable_target_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            policy = self.fixture(root, "600000 816000 1200000 1296000")
            result = self.run_script(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((policy / "scaling_max_freq").read_text().strip(), "1296000")
            self.assertEqual((policy / "scaling_governor").read_text().strip(), "performance")

    def test_unit_orders_the_policy_before_the_frontend(self) -> None:
        text = UNIT.read_text(encoding="utf-8")
        self.assertIn("Before=r46h-gaming-frontend.service", text)
        self.assertIn("ExecStart=/usr/local/libexec/r46h-cpufreq-default", text)
        self.assertIn("WantedBy=multi-user.target", text)


if __name__ == "__main__":
    unittest.main()
