#!/usr/bin/env python3
"""Regression gates for the R46H board-level USB-DC detection candidate."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest


REPO = Path(__file__).resolve().parents[2]
PATCH = REPO / "mainline/patches/0008-power-supply-rk817-support-a-board-DC-input.patch"
DTS = REPO / "mainline/board/r46h/rk3326-r46h.dts"
BINDING = "Documentation/devicetree/bindings/mfd/rockchip,rk817.yaml"
DRIVER = "drivers/power/supply/rk817_charger.c"
MANIFEST = REPO / "mainline/manifest.env"
CONFIG = REPO / "mainline/config/r46h.fragment"
BUILD = REPO / "mainline/scripts/build-kernel.sh"
BOARD_NOTES = REPO / "docs/R46H-BOARD.md"
PROBE_RUNBOOK = REPO / "mainline/bringup-tests/CHARGER-DC-DETECT-PROBE.md"
BUILD_ID = "v0.19-zram-product"
RELEASE = f"6.12.99-r46h-mainline-{BUILD_ID}"


class R46HChargerDcDetectTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.patch = PATCH.read_text(encoding="utf-8")
        cls.dts = DTS.read_text(encoding="utf-8")
        cls.manifest = MANIFEST.read_text(encoding="utf-8")
        cls.config = CONFIG.read_text(encoding="utf-8")
        cls.build = BUILD.read_text(encoding="utf-8")
        cls.board_notes = BOARD_NOTES.read_text(encoding="utf-8")
        cls.runbook = PROBE_RUNBOOK.read_text(encoding="utf-8")

    def test_patch_scope_and_numstat_are_exact(self) -> None:
        parsed = subprocess.run(
            ["git", "apply", "--numstat", str(PATCH)],
            cwd=REPO,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            parsed.stdout,
            "7\t0\tDocumentation/devicetree/bindings/mfd/rockchip,rk817.yaml\n"
            "1\t0\tarch/arm64/boot/dts/rockchip/rk3326-r46h.dts\n"
            "97\t4\tdrivers/power/supply/rk817_charger.c\n",
        )
        targets = re.findall(r"^diff --git a/(\S+) b/(\S+)$", self.patch, re.M)
        self.assertEqual(
            targets,
            [(BINDING, BINDING),
             ("arch/arm64/boot/dts/rockchip/rk3326-r46h.dts",) * 2,
             (DRIVER, DRIVER)],
        )

    def test_binding_is_optional_and_board_line_is_exact(self) -> None:
        binding_change = self.patch.split(f"diff --git a/{BINDING}", 1)[1]
        binding_change = binding_change.split("diff --git ", 1)[0]
        self.assertIn("+      dc-det-gpios:", binding_change)
        self.assertIn("+        maxItems: 1", binding_change)
        self.assertNotRegex(binding_change, re.compile(r"^\+\s+required:", re.M))
        expected = "dc-det-gpios = <&gpio0 RK_PB3 GPIO_ACTIVE_HIGH>;"
        self.assertEqual(self.dts.count(expected), 1)
        self.assertEqual(self.patch.count(f"+\t{expected}"), 1)

    def test_gpio_is_input_only_and_uses_the_child_fwnode(self) -> None:
        for literal in (
            'of_property_present(node, "dc-det-gpios")',
            '"dc-det", 0, GPIOD_IN, "rk817-dc-det"',
            "gpiod_to_irq(charger->dc_det_gpio)",
            "IRQF_TRIGGER_RISING |",
            "IRQF_TRIGGER_FALLING |",
            "IRQF_ONESHOT",
            "gpiod_get_value_cansleep(charger->dc_det_gpio)",
        ):
            self.assertIn(literal, self.patch)
        for forbidden in ("GPIOD_OUT", "gpiod_set_value", "gpiod_direction_output"):
            self.assertNotIn(forbidden, self.patch)

    def test_online_is_the_or_of_pmic_and_board_state(self) -> None:
        self.assertIn("READ_ONCE(charger->plugged_in) ||", self.patch)
        self.assertIn("READ_ONCE(charger->dc_plugged_in);", self.patch)
        self.assertEqual(
            self.patch.count("WRITE_ONCE(charger->plugged_in,"),
            3,
        )
        self.assertIn("WRITE_ONCE(charger->dc_plugged_in, plugged_in);", self.patch)
        self.assertIn("power_supply_changed(charger->chg_ps);", self.patch)
        self.assertIn("power_supply_changed(charger->bat_ps);", self.patch)

    def test_initialization_occurs_after_battery_init_and_before_pmic_irqs(self) -> None:
        probe_hunk = self.patch.split(
            "@@ -1166,6 +1246,10 @@ static int rk817_charger_probe", 1
        )[1]
        put_info = probe_hunk.index(
            "power_supply_put_battery_info(charger->bat_ps, bat_info);"
        )
        dc_init = probe_hunk.index("ret = rk817_dc_det_init(charger, node);")
        plugin_irq = probe_hunk.index("plugin_irq = platform_get_irq(pdev, 0);")
        self.assertLess(put_info, dc_init)
        self.assertLess(dc_init, plugin_irq)
        self.assertIn("rk817_update_dc_det(charger, false);", self.patch)
        self.assertIn("rk817_update_dc_det(charger, true);", self.patch)

    def test_patch_does_not_program_charger_limits_or_enable_state(self) -> None:
        driver_change = self.patch.split(f"diff --git a/{DRIVER}", 1)[1]
        added = "\n".join(
            line[1:]
            for line in driver_change.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        for forbidden in (
            "regmap_write(",
            "regmap_update_bits(",
            "RK817_CHRG",
            "RK817_PMIC_CHRG",
            "RK817_USB_CTRL",
            "RK817_BAT_CTRL",
        ):
            self.assertNotIn(forbidden, added)

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
        self.assertEqual(RELEASE, "6.12.99-r46h-mainline-v0.19-zram-product")
        self.assertEqual(
            re.findall(r"^KERNEL_PATCH_LAST=(.+)$", self.manifest, re.M),
            ["0008"],
        )

    def test_documentation_preserves_the_evidence_boundary(self) -> None:
        for literal in (
            "GPIO0_B3",
            "active-high",
            "online=0",
            "does not prove that charging current is safe",
        ):
            self.assertIn(literal, self.runbook)
        normalized_board_notes = re.sub(r"\s+", " ", self.board_notes)
        for literal in (
            "v0.11 single-variable candidate",
            "does not change charge voltage, current, enable state or input limits",
            "cannot prove battery current direction or safe charging",
            "Patch `0009` is retained as the host-only v0.12",
            "deliberately excluded by the current product manifest",
        ):
            self.assertIn(literal, normalized_board_notes)


if __name__ == "__main__":
    unittest.main()
