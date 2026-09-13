#!/usr/bin/env python3
"""Host checks for read-only capabilities and CPU/zram draft validation."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("tuning", Path(__file__).resolve().parents[1] / "gaming-shell/tuning.py")
tuning = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tuning)


class TuningCheck(unittest.TestCase):
    def test_probe_and_drafts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            files = {"proc/meminfo": "MemTotal: 1000000 kB\nMemAvailable: 500000 kB\n",
                     "config": "CONFIG_SWAP=y\n# CONFIG_ZRAM is not set\n# CONFIG_ZSWAP is not set\n"}
            policy = {"cpuinfo_min_freq": "408000", "cpuinfo_max_freq": "1296000",
                      "scaling_min_freq": "408000", "scaling_max_freq": "1296000",
                      "scaling_governor": "schedutil", "scaling_available_governors": "schedutil performance",
                      "scaling_available_frequencies": "408000 816000 1296000"}
            for name, value in policy.items():
                files["sys/devices/system/cpu/cpufreq/policy0/" + name] = value
            for name, value in files.items():
                path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(value)
            before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
            caps = tuning.probe(root, root / "config")
            self.assertEqual(caps["kernel_config"]["CONFIG_ZRAM"], "n")
            for preset in ("default", "balanced", "performance"):
                draft = tuning.validate(caps, {"schema": 1, "cpu": [{"policy": "policy0", "preset": preset}]})
                self.assertEqual(draft["cpu"][0]["max_khz"], 1296000)
            for low, high, governor in ((1296000, 408000, "schedutil"), (408000, 2000000, "schedutil"),
                                         (500000, 816000, "schedutil"), (408000, 816000, "missing"), (True, 816000, "schedutil")):
                with self.assertRaises(ValueError):
                    tuning.cpu_draft(caps["cpu"][0], "custom", low, high, governor)
            with self.assertRaises(ValueError): tuning.cpu_draft(caps["cpu"][0], "powersave")
            self.assertEqual(tuning.cpu_draft(caps["cpu"][0], "custom", 408000, 816000, "schedutil")["max_khz"], 816000)
            zram = {"schema": 1, "zram": {"size_mib": 512, "algorithm": "lz4"}}
            with self.assertRaises(ValueError): tuning.validate(caps, zram)
            caps["zram"] = [{"algorithms": ["lz4", "zstd"]}]
            caps["kernel_config"]["CONFIG_ZRAM"] = "m"
            self.assertEqual(tuning.validate(caps, zram)["zram"]["size_mib"], 512)
            for size, algorithm in ((-1, "lz4"), (99999, "lz4"), (True, "lz4"), (512, "missing")):
                with self.assertRaises(ValueError): tuning.validate(caps, {"schema": 1, "zram": {"size_mib": size, "algorithm": algorithm}})
            with self.assertRaises(ValueError): tuning.validate(caps, {"schema": 1, "disk_swap": {"size_mib": 1024}})
            for invalid in ([], {"schema": True}, {"schema": 1, "cpu": {}},
                            {"schema": 1, "cpu": [{"policy": "policy0", "preset": "balanced", "min_khz": 816000}]},
                            {"schema": 1, "cpu": [{"policy": "policy0", "preset": "balanced", "max_mhz": 816}]},
                            {"schema": 1, "zram": []}, {"schema": 1, "zram": {"size_mib": 0, "writeback": True}}):
                with self.assertRaises(ValueError): tuning.validate(caps, invalid)
            with self.assertRaises(ValueError): tuning.validate([], {"schema": 1})
            self.assertEqual(before, {p: p.read_bytes() for p in root.rglob("*") if p.is_file()})
            self.assertEqual(tuning.probe(root / "missing")["cpu"], [])


if __name__ == "__main__":
    unittest.main()
