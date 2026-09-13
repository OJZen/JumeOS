#!/usr/bin/env python3
"""Regression tests for the R46H ADC inversion and full-range fixes."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
DRIVER_PATCH = (
    REPO_ROOT
    / "mainline/patches/0006-input-joystick-adc-use-axis-code-for-inversion.patch"
)
RANGE_PATCH = (
    REPO_ROOT
    / "mainline/patches/0007-arm64-dts-rockchip-use-r46h-adc-full-range.patch"
)
CHARGER_PATCH = (
    REPO_ROOT
    / "mainline/patches/0008-power-supply-rk817-support-a-board-DC-input.patch"
)
POLICY_PATCH = (
    REPO_ROOT
    / "mainline/patches/0009-arm64-dts-rockchip-use-rk817-150ma-charge-termination.patch"
)
MMC_OBSERVE_PATCH = (
    REPO_ROOT
    / "mainline/patches/0010-mmc-dw-log-request-errors.patch"
)
DTS = REPO_ROOT / "mainline/board/r46h/rk3326-r46h.dts"
BUILDER = REPO_ROOT / "mainline/scripts/build-in-container.sh"
BUILD_ENTRYPOINT = REPO_ROOT / "mainline/scripts/build-kernel.sh"
MANIFEST = REPO_ROOT / "mainline/manifest.env"
CONFIG = REPO_ROOT / "mainline/config/r46h.fragment"
BUILD_ID = "v0.15-gaming-product"
KERNEL_RELEASE = f"6.12.99-r46h-mainline-{BUILD_ID}"


class R46HAdcJoystickInversionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.driver_patch = DRIVER_PATCH.read_text(encoding="utf-8")
        cls.range_patch = RANGE_PATCH.read_text(encoding="utf-8")
        cls.dts = DTS.read_text(encoding="utf-8")
        cls.builder = BUILDER.read_text(encoding="utf-8")
        cls.build_entrypoint = BUILD_ENTRYPOINT.read_text(encoding="utf-8")
        cls.manifest = MANIFEST.read_text(encoding="utf-8")
        cls.config = CONFIG.read_text(encoding="utf-8")

    def test_patch_changes_only_the_adc_joystick_driver(self) -> None:
        targets = re.findall(
            r"^diff --git a/(\S+) b/(\S+)$", self.driver_patch, re.M
        )
        self.assertEqual(
            targets,
            [("drivers/input/joystick/adc-joystick.c",) * 2],
        )
        self.assertIn(
            "1 file changed, 2 insertions(+), 2 deletions(-)", self.driver_patch
        )

    def test_both_inversion_paths_use_the_event_code(self) -> None:
        self.assertEqual(
            self.driver_patch.count(
                "+\t\t\tval = adc_joystick_invert(input, joy->axes[i].code, val);"
            ),
            1,
        )
        self.assertEqual(
            self.driver_patch.count(
                "+\t\t\tval = adc_joystick_invert(joy->input, "
                "joy->axes[i].code, val);"
            ),
            1,
        )
        self.assertIn(
            "-\t\t\tval = adc_joystick_invert(input, i, val);",
            self.driver_patch,
        )
        self.assertIn(
            "-\t\t\tval = adc_joystick_invert(joy->input, i, val);",
            self.driver_patch,
        )

    def test_range_patch_changes_only_the_r46h_dts(self) -> None:
        parsed = subprocess.run(
            ["git", "apply", "--numstat", str(RANGE_PATCH)],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            parsed.stdout,
            "7\t7\tarch/arm64/boot/dts/rockchip/rk3326-r46h.dts\n",
        )
        targets = re.findall(
            r"^diff --git a/(\S+) b/(\S+)$", self.range_patch, re.M
        )
        self.assertEqual(
            targets,
            [("arch/arm64/boot/dts/rockchip/rk3326-r46h.dts",) * 2],
        )
        self.assertEqual(self.range_patch.count("-\t\t\tabs-range = <800 180>;"), 2)
        self.assertEqual(self.range_patch.count("-\t\t\tabs-range = <180 800>;"), 2)
        self.assertEqual(self.range_patch.count("+\t\t\tabs-range = <1023 0>;"), 2)
        self.assertEqual(self.range_patch.count("+\t\t\tabs-range = <0 1023>;"), 2)

    def test_r46h_layout_exercises_the_channel_code_mismatch(self) -> None:
        axis = re.search(r"axis@2 \{(?P<body>.*?)\n\t\t\};", self.dts, re.S)
        self.assertIsNotNone(axis)
        body = axis.group("body")
        self.assertIn("reg = <2>;", body)
        self.assertIn("abs-range = <1023 0>;", body)
        self.assertIn("linux,code = <ABS_Y>;", body)

        raw_center = 517
        configured_min, configured_max = 0, 1023
        old_value = -raw_center  # Channel index 2 incorrectly selects unset ABS_Z.
        new_value = configured_min + configured_max - raw_center
        self.assertLess(old_value, configured_min)
        self.assertGreaterEqual(new_value, configured_min)
        self.assertLessEqual(new_value, configured_max)

    def test_all_axes_use_the_full_ten_bit_domain(self) -> None:
        expected = {
            "0": ("1023 0", "ABS_X"),
            "1": ("0 1023", "ABS_RX"),
            "2": ("1023 0", "ABS_Y"),
            "3": ("0 1023", "ABS_RY"),
        }
        axes = re.findall(r"axis@(\d+) \{(.*?)\n\t\t\};", self.dts, re.S)
        self.assertEqual(len(axes), 4)
        for index, body in axes:
            axis_range, code = expected[index]
            self.assertIn(f"abs-range = <{axis_range}>;", body)
            self.assertIn(f"linux,code = <{code}>;", body)
            self.assertIn("abs-flat = <10>;", body)
            self.assertIn("abs-fuzz = <10>;", body)

        for low, high in ((82, 946), (31, 874), (51, 891), (70, 927)):
            self.assertGreaterEqual(low, 0)
            self.assertLessEqual(high, 1023)

    def test_builder_applies_the_manifest_selected_prefix_in_lexical_order(self) -> None:
        self.assertIn('patches=("$MAINLINE_DIR"/patches/*.patch)', self.builder)
        self.assertIn('[[ "$selected_patch_last" == "$KERNEL_PATCH_LAST" ]]', self.builder)
        self.assertIn(
            'patch --directory "$SOURCE_DIR" --strip=1 --forward < "$patch_file"',
            self.builder,
        )
        self.assertEqual(
            re.findall(r"^KERNEL_PATCH_LAST=(.+)$", self.manifest, re.M),
            ["0008"],
        )
        patch_names = sorted(path.name for path in DRIVER_PATCH.parent.glob("*.patch"))
        self.assertEqual(
            patch_names[-5:],
            [
                DRIVER_PATCH.name,
                RANGE_PATCH.name,
                CHARGER_PATCH.name,
                POLICY_PATCH.name,
                MMC_OBSERVE_PATCH.name,
            ],
        )

    def test_current_candidate_identity_is_consistent(self) -> None:
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
            re.findall(r'^BUILD_ID="(.+)"$', self.build_entrypoint, re.M),
            [BUILD_ID],
        )
        self.assertEqual(self.build_entrypoint.count(f"默认 {BUILD_ID}"), 1)
        self.assertEqual(
            KERNEL_RELEASE,
            "6.12.99-r46h-mainline-v0.15-gaming-product",
        )


if __name__ == "__main__":
    unittest.main()
