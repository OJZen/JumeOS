#!/usr/bin/env python3
"""Regression gates for the R46H RK817 termination-current conversion."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest


REPO = Path(__file__).resolve().parents[2]
BASE_PATCH = REPO / "mainline/patches/0001-arm64-dts-rockchip-add-R46H-mainline-bring-up.patch"
POLICY_PATCH = REPO / "mainline/patches/0009-arm64-dts-rockchip-use-rk817-150ma-charge-termination.patch"
DTS = REPO / "mainline/board/r46h/rk3326-r46h.dts"
MANIFEST = REPO / "mainline/manifest.env"
CONFIG = REPO / "mainline/config/r46h.fragment"
BUILD = REPO / "mainline/scripts/build-kernel.sh"
CONTAINER_BUILD = REPO / "mainline/scripts/build-in-container.sh"
RUNBOOK = REPO / "mainline/bringup-tests/V12-CHARGE-TERM-POLICY.md"
LEDGER = REPO / "mainline/board/r46h/EXPERIMENT-STATUS.md"
BUILD_ID = "v0.19-zram-product"


def downstream_analog_selection_ma(configured_ma: int) -> int:
    if configured_ma < 200:
        return 150
    if configured_ma < 300:
        return 200
    if configured_ma < 400:
        return 300
    return 400


def upstream_selection_ma(configured_ua: int) -> int:
    configured_ma = configured_ua // 1000
    if configured_ma < 150 or configured_ma > 400:
        return 200
    register = (configured_ma - 100) // 100
    return (150, 200, 300, 400)[register]


class R46HChargeTermPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.base_patch = BASE_PATCH.read_text(encoding="utf-8")
        cls.policy_patch = POLICY_PATCH.read_text(encoding="utf-8")
        cls.dts = DTS.read_text(encoding="utf-8")
        cls.manifest = MANIFEST.read_text(encoding="utf-8")
        cls.config = CONFIG.read_text(encoding="utf-8")
        cls.build = BUILD.read_text(encoding="utf-8")
        cls.container_build = CONTAINER_BUILD.read_text(encoding="utf-8")
        cls.runbook = RUNBOOK.read_text(encoding="utf-8")
        cls.ledger = LEDGER.read_text(encoding="utf-8")

    def test_patch_changes_only_one_r46h_dts_value(self) -> None:
        parsed = subprocess.run(
            ["git", "apply", "--numstat", str(POLICY_PATCH)],
            cwd=REPO,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            parsed.stdout,
            "1\t1\tarch/arm64/boot/dts/rockchip/rk3326-r46h.dts\n",
        )
        targets = re.findall(
            r"^diff --git a/(\S+) b/(\S+)$", self.policy_patch, re.M
        )
        self.assertEqual(
            targets,
            [("arch/arm64/boot/dts/rockchip/rk3326-r46h.dts",) * 2],
        )
        self.assertEqual(
            self.policy_patch.count("-\t\tcharge-term-current-microamp = <52000>;"),
            1,
        )
        self.assertEqual(
            self.policy_patch.count("+\t\tcharge-term-current-microamp = <150000>;"),
            1,
        )

    def test_experimental_patch_is_retained_but_product_dts_excludes_it(self) -> None:
        self.assertEqual(
            self.base_patch.count("+\t\tcharge-term-current-microamp = <52000>;"),
            1,
        )
        self.assertEqual(
            self.dts.count("\t\tcharge-term-current-microamp = <52000>;"),
            1,
        )
        self.assertNotIn("charge-term-current-microamp = <150000>;", self.dts)
        self.assertEqual(
            re.findall(r"^KERNEL_PATCH_LAST=(.+)$", self.manifest, re.M),
            ["0008"],
        )
        self.assertIn(
            '[[ "$selected_patch_last" == "$KERNEL_PATCH_LAST" ]]',
            self.container_build,
        )

    def test_effective_vendor_register_selection_is_preserved(self) -> None:
        vendor_configured_ma = 0x34
        self.assertEqual(vendor_configured_ma, 52)
        self.assertEqual(downstream_analog_selection_ma(vendor_configured_ma), 150)
        self.assertEqual(upstream_selection_ma(52000), 200)
        self.assertEqual(upstream_selection_ma(150000), 150)

    def test_candidate_identity_is_exact_and_unique(self) -> None:
        localversion = f"-r46h-mainline-{BUILD_ID}"
        self.assertEqual(
            re.findall(r"^KERNEL_LOCALVERSION=(.+)$", self.manifest, re.M),
            [localversion],
        )
        self.assertEqual(
            re.findall(r'^CONFIG_LOCALVERSION="(.+)"$', self.config, re.M),
            [localversion],
        )
        self.assertEqual(
            re.findall(r'^BUILD_ID="(.+)"$', self.build, re.M), [BUILD_ID]
        )
        self.assertEqual(self.build.count(f"默认 {BUILD_ID}"), 1)

    def test_runbook_pins_sources_and_bounds_physical_charging_claim(self) -> None:
        for literal in (
            "9ead5f3cbd6e0abd0ac70002205993c953c227ea",
            "d6ee5763f8e2063bc7dca24be4d35e480f3b6c1098e21f5dfaa5ecf59f70e2c4",
            "6a477222c132033381cda981eb0127f29fbcbba17e820283bc21290f8e408629",
            "eb06785415e3a49cbbbd472c79958ed06bef8cd62eb72c368ecfc691f6389b6b",
            "chrg_term_mode = <0x00>;",
            "chrg_finish_cur = <0x34>;",
            "PASS (short attended actual charging on v0.10)",
            "f8d068698b158847104ee4bef7b5c3c191c6db296b1b19d57b79d6e9dee56fd9",
            "`+252152..+255764` uA",
            "`-702276..-702792` uA",
            "does not validate",
            "unattended safety",
        ):
            self.assertIn(literal, self.runbook)

    def test_host_artifact_evidence_is_pinned_without_hardware_claims(self) -> None:
        for literal in (
            "9054fc849fc4845a4b5511d8edbf94e969328367",
            "40a1301ebcb2a4f0dbf977ee2bd90d2771d6d1f1a7129d08684d19edf8fa81eb",
            "d974e397ab0ddedaf46309fde2aa0bdf9eb1775b50431ad85f913a652c614f52",
            "6a0a4c4a82919c6461307e644db37b2569a349120d8f2c4933b0e7d1a341608f",
            "d1b035ee09ed0c44ccad62304f0c588d302c6055f634e65390850163cceba8ad",
            "PASS (host only)",
        ):
            self.assertIn(literal, self.runbook)
        collapsed_ledger = " ".join(self.ledger.split())
        self.assertIn("V0.12 charge termination", collapsed_ledger)
        self.assertIn("PASS (HOST ONLY)", collapsed_ledger)
        self.assertNotIn("HOST BUILD OPEN", self.ledger)


if __name__ == "__main__":
    unittest.main()
