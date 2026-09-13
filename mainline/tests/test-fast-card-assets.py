#!/usr/bin/env python3
import hashlib
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "mainline/scripts/prepare-r46h-fast-card-assets.py"
RUNBOOK = ROOT / "mainline/deploy/FAST-CARD-62534975488.md"
STATUS = ROOT / "mainline/board/r46h/EXPERIMENT-STATUS.md"
MODULE = types.ModuleType("r46h_fast_card_assets_test")
MODULE.__file__ = str(PATH)
sys.modules[MODULE.__name__] = MODULE
exec(compile(PATH.read_bytes(), str(PATH), "exec"), MODULE.__dict__)


class FastCardAssetsTests(unittest.TestCase):
    def test_exact_geometry_covers_the_card(self) -> None:
        self.assertEqual(MODULE.P3_SIZE, 62_534_975_488 - 10_851_095_040)
        self.assertEqual(MODULE.P3_SECTORS, MODULE.P3_SIZE // 512)

    def test_mbr_derivation_changes_only_the_p3_length_field(self) -> None:
        raw = bytearray(MODULE.PREFIX_SIZE)
        raw[490:494] = bytes.fromhex("b7ec6d02")
        result = MODULE.derive_prefix(bytes(raw))
        self.assertEqual(result[490:494], bytes.fromhex("b74c0406"))
        self.assertEqual(sum(a != b for a, b in zip(raw, result)), 3)
        raw[490] ^= 1
        with self.assertRaises(MODULE.PrepareError):
            MODULE.derive_prefix(bytes(raw))

    def test_pinned_real_prefix_produces_expected_digest(self) -> None:
        source = ROOT / MODULE.SOURCE_SET / "00-prefix-g92-mbr.bin"
        if not source.exists():
            self.skipTest("retained full-card source set is absent")
        result = MODULE.derive_prefix(source.read_bytes())
        self.assertEqual(hashlib.sha256(result).hexdigest(), MODULE.NEW_PREFIX_SHA256)

    def test_publication_is_noreplace(self) -> None:
        source = PATH.read_text(encoding="utf-8")
        self.assertIn("renameatx_np", source)
        self.assertIn("0x00000004", source)
        self.assertNotIn("os.rename(stage, output)", source)

    def test_cold_mmc_history_and_v17_boundary_are_pinned(self) -> None:
        runbook = RUNBOOK.read_text(encoding="utf-8")
        status = STATUS.read_text(encoding="utf-8")
        collapsed_status = " ".join(status.split())
        for digest in (
            "1e72aa804007158edc56d991cbfc6f10d256fcaa48469b1ac1bb10244daf4f04",
            "f895e594b80fe8a1aca4675981d4e99f2a46e33386162297efb1040afa5b77d2",
            "abc6db1042817e5dd4198cd28a9aa6339157c4319801669965b190b7f484fbd5",
        ):
            self.assertIn(digest, runbook)
        for literal in (
            "fast-card-firstboot-20260814T120439Z.bin",
            "v010-audio-jack-20260815.bin",
            "hantro-reference-20260816.bin",
            "v010-rgui-rom-launch-20260817.bin",
            "v010-charger-input-meter-20260817.bin",
            "f8d068698b158847104ee4bef7b5c3c191c6db296b1b19d57b79d6e9dee56fd9",
            "Do not run another blind cold-boot loop",
        ):
            self.assertIn(literal, runbook)
        self.assertIn("Cold MMC initialization", collapsed_status)
        self.assertIn(
            "V0.17 ONE-SHOT + TWO PERSISTENT CLEAN PASS / "
            "STATISTICAL RELIABILITY OPEN",
            collapsed_status,
        )
        self.assertIn("three cold samples reached SDR104/150 MHz", collapsed_status)
        self.assertIn("v0.16 persistent isolation alone reproduced", collapsed_status)
        self.assertIn(
            "Do not loop boots or call the issue statistically solved",
            collapsed_status,
        )
        self.assertIn("v0.17 BOOT/power settle selects the exact", status)
        self.assertNotIn("Cold MMC initialization — PASS.", collapsed_status)


if __name__ == "__main__":
    unittest.main()
