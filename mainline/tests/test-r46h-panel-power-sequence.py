#!/usr/bin/env python3
"""Source, patch-series, and DTB tests for the R46H panel power sequence."""

from __future__ import annotations

import hashlib
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest


MAINLINE = pathlib.Path(__file__).resolve().parents[1]
PANEL = MAINLINE / "board" / "r46h" / "panel-r46h.c"
DTS = MAINLINE / "board" / "r46h" / "rk3326-r46h.dts"
PATCH_DIR = MAINLINE / "patches"
MANIFEST = MAINLINE / "manifest.env"
KERNEL_TARBALL = MAINLINE / ".cache" / "kernel" / "linux-6.12.99.tar.xz"
BUILDER_IMAGE = "arkos4clone/r46h-kernel-builder:trixie-arm64"
EXPECTED_SEQUENCE_SHA256 = (
    "b6d1e77241ae5d97168e7324c000c44459a56352cc09eff3d2e954bf2046d6dd"
)
PANEL_PATCH_NAMES = [
    "0001-arm64-dts-rockchip-add-R46H-mainline-bring-up.patch",
    "0002-drm-rockchip-use-r46h-dsi-lane-rate.patch",
    "0003-drm-panel-r46h-enable-backlight-rail-before-init.patch",
    "0004-drm-rockchip-use-r46h-dsi-host-timers.patch",
    "0005-drm-panel-r46h-preserve-bootloader-handoff.patch",
    "0007-arm64-dts-rockchip-use-r46h-adc-full-range.patch",
]
CHARGER_PATCH_NAME = "0008-power-supply-rk817-support-a-board-DC-input.patch"
CHARGE_TERM_PATCH_NAME = (
    "0009-arm64-dts-rockchip-use-rk817-150ma-charge-termination.patch"
)
MMC_OBSERVE_PATCH_NAME = "0010-mmc-dw-log-request-errors.patch"
ALL_PATCH_NAMES = [
    *PANEL_PATCH_NAMES[:5],
    "0006-input-joystick-adc-use-axis-code-for-inversion.patch",
    *PANEL_PATCH_NAMES[5:],
    CHARGER_PATCH_NAME,
    CHARGE_TERM_PATCH_NAME,
    MMC_OBSERVE_PATCH_NAME,
]
ACTIVE_PATCH_LAST_MATCH = re.search(
    r"^KERNEL_PATCH_LAST=([0-9]{4})$",
    MANIFEST.read_text(encoding="utf-8"),
    re.MULTILINE,
)
if ACTIVE_PATCH_LAST_MATCH is None:
    raise RuntimeError("manifest is missing KERNEL_PATCH_LAST")
ACTIVE_PATCH_LAST = ACTIVE_PATCH_LAST_MATCH.group(1)


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    open_brace = source.index("{", start)
    depth = 0
    for index in range(open_brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated function: {signature}")


def command_stream(source: str) -> bytes:
    block = re.search(
        r"static const struct r46h_panel_command "
        r"r46h_panel_init_commands\[\] = \{(.*?)\n\};",
        source,
        re.DOTALL,
    )
    if block is None:
        raise AssertionError("missing panel command table")
    commands = [
        tuple(int(value, 16) for value in match)
        for match in re.findall(
            r"\{ 0x([0-9a-f]{2}), 0x([0-9a-f]{2}) \}", block.group(1)
        )
    ]
    if len(commands) != 167:
        raise AssertionError(f"expected 167 panel commands, found {len(commands)}")

    sequence = b"".join(
        bytes((0x15, 0x00, 0x02, command, value))
        for command, value in commands
    )
    sequence += bytes((0x05, 0xC8, 0x01, 0x11))
    sequence += bytes((0x05, 0x14, 0x01, 0x29))
    return sequence


def git_blob_oid(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


class PanelPowerSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.panel = PANEL.read_text(encoding="utf-8")
        cls.dts = DTS.read_text(encoding="utf-8")

    def test_downstream_843_byte_sequence_is_unchanged(self) -> None:
        sequence = command_stream(self.panel)
        self.assertEqual(len(sequence), 843)
        self.assertEqual(hashlib.sha256(sequence).hexdigest(), EXPECTED_SEQUENCE_SHA256)

    def test_dsi_parameters_are_unchanged(self) -> None:
        probe = function_body(self.panel, "static int r46h_panel_probe")
        self.assertEqual(probe.count("dsi->lanes = 4;"), 1)
        self.assertEqual(probe.count("dsi->format = MIPI_DSI_FMT_RGB888;"), 1)
        flags = re.search(
            r"dsi->mode_flags = (.*?);\n\s*dev_info", probe, re.DOTALL
        )
        self.assertIsNotNone(flags)
        self.assertEqual(
            re.sub(r"\s+", " ", flags.group(1)).strip(),
            "MIPI_DSI_MODE_VIDEO | MIPI_DSI_MODE_VIDEO_BURST | "
            "MIPI_DSI_MODE_NO_EOT_PACKET | MIPI_DSI_MODE_LPM",
        )

    def test_supply_array_indices_preserve_reverse_disable_order(self) -> None:
        supply_enum = re.search(
            r"enum r46h_panel_supply \{(.*?)\n\};", self.panel, re.DOTALL
        )
        self.assertIsNotNone(supply_enum)
        entries = [
            entry.strip()
            for entry in supply_enum.group(1).split(",")
            if entry.strip()
        ]
        self.assertEqual(
            entries,
            [
                "R46H_PANEL_SUPPLY_POWER",
                "R46H_PANEL_SUPPLY_BACKLIGHT",
                "R46H_PANEL_NUM_SUPPLIES",
            ],
        )
        self.assertEqual(
            self.panel.count(
                "struct regulator_bulk_data "
                "supplies[R46H_PANEL_NUM_SUPPLIES];"
            ),
            1,
        )

    def test_required_supplies_and_prepare_order(self) -> None:
        probe = function_body(self.panel, "static int r46h_panel_probe")
        self.assertIn(
            'ctx->supplies[R46H_PANEL_SUPPLY_POWER].supply = "power";', probe
        )
        self.assertIn(
            'ctx->supplies[R46H_PANEL_SUPPLY_BACKLIGHT].supply = "backlight";',
            probe,
        )
        self.assertIn("devm_regulator_bulk_get", probe)
        self.assertNotIn("devm_regulator_bulk_get_optional", probe)

        prepare = function_body(self.panel, "static int r46h_panel_prepare")
        power_binding = prepare.index(
            "ctx->supplies[R46H_PANEL_SUPPLY_POWER].consumer;"
        )
        backlight_binding = prepare.index(
            "ctx->supplies[R46H_PANEL_SUPPLY_BACKLIGHT].consumer;"
        )
        power_enable = prepare.index("ret = regulator_enable(power);")
        backlight_enable = prepare.index("ret = regulator_enable(backlight);")
        normal_guard = prepare.index(
            "if (ctx->supply_enabled[R46H_PANEL_SUPPLY_BACKLIGHT] ||"
        )
        reset_direction = prepare.index(
            "ret = r46h_panel_assert_reset(ctx);", normal_guard
        )
        reset = prepare.index("gpiod_set_value_cansleep", backlight_enable)
        dcs = prepare.index("r46h_panel_write_init_sequence")
        self.assertLess(backlight_binding, power_binding)
        self.assertLess(power_binding, power_enable)
        self.assertLess(reset_direction, power_enable)
        self.assertLess(power_enable, backlight_enable)
        self.assertLess(backlight_enable, reset)
        self.assertLess(reset, dcs)

        normal_path = prepare[
            power_enable : prepare.index("ctx->initialized = true;", power_enable)
        ]
        ordered = [
            "ret = regulator_enable(power);",
            "ctx->supply_enabled[R46H_PANEL_SUPPLY_POWER] = true;",
            "ret = regulator_enable(backlight);",
            "ctx->supply_enabled[R46H_PANEL_SUPPLY_BACKLIGHT] = true;",
            "msleep(20);",
            "gpiod_set_value_cansleep(ctx->reset_gpio, 1);",
            "msleep(150);",
            "gpiod_set_value_cansleep(ctx->reset_gpio, 0);",
            "msleep(20);",
            "ret = r46h_panel_write_init_sequence(ctx);",
            "ret = mipi_dsi_dcs_exit_sleep_mode(ctx->dsi);",
            "msleep(200);",
            "ret = mipi_dsi_dcs_set_display_on(ctx->dsi);",
            "msleep(20);",
        ]
        cursor = 0
        for token in ordered:
            cursor = normal_path.index(token, cursor) + len(token)
        self.assertEqual(
            re.findall(r"(?:m|u)sleep(?:_range)?\([^;]+\);", normal_path),
            [
                "msleep(20);",
                "msleep(150);",
                "msleep(20);",
                "msleep(200);",
                "msleep(20);",
            ],
        )

    def test_reverse_cleanup_tracks_each_owned_ref_and_stops_on_error(self) -> None:
        cleanup = function_body(
            self.panel, "static int r46h_panel_disable_supplies"
        )
        backlight_guard = cleanup.index(
            "ctx->supply_enabled[R46H_PANEL_SUPPLY_BACKLIGHT]"
        )
        backlight_disable = cleanup.index("regulator_disable(backlight);")
        backlight_clear = cleanup.index(
            "ctx->supply_enabled[R46H_PANEL_SUPPLY_BACKLIGHT] = false;"
        )
        power_guard = cleanup.index(
            "ctx->supply_enabled[R46H_PANEL_SUPPLY_POWER]", backlight_clear
        )
        power_disable = cleanup.index("regulator_disable(power);")
        power_clear = cleanup.index(
            "ctx->supply_enabled[R46H_PANEL_SUPPLY_POWER] = false;"
        )
        self.assertLess(backlight_guard, backlight_disable)
        self.assertLess(backlight_disable, backlight_clear)
        self.assertLess(backlight_clear, power_guard)
        self.assertLess(power_guard, power_disable)
        self.assertLess(power_disable, power_clear)
        self.assertIn("return ret;", cleanup[backlight_disable:backlight_clear])
        self.assertIn("return ret;", cleanup[power_disable:power_clear])
        self.assertNotIn("regulator_bulk_disable", cleanup)

    def test_prepare_clears_residual_refs_before_new_enables(self) -> None:
        prepare = function_body(self.panel, "static int r46h_panel_prepare")
        residual_guard = prepare.index(
            "ctx->supply_enabled[R46H_PANEL_SUPPLY_BACKLIGHT] ||"
        )
        residual_cleanup = prepare.index(
            "r46h_panel_disable_supplies(ctx);", residual_guard
        )
        power_enable = prepare.index("regulator_enable(power);")
        power_owned = prepare.index(
            "ctx->supply_enabled[R46H_PANEL_SUPPLY_POWER] = true;"
        )
        backlight_enable = prepare.index("regulator_enable(backlight);")
        backlight_owned = prepare.index(
            "ctx->supply_enabled[R46H_PANEL_SUPPLY_BACKLIGHT] = true;"
        )
        self.assertLess(residual_guard, residual_cleanup)
        self.assertLess(residual_cleanup, power_enable)
        self.assertIn("return ret;", prepare[residual_cleanup:power_enable])
        self.assertLess(power_enable, power_owned)
        self.assertLess(power_owned, backlight_enable)
        self.assertLess(backlight_enable, backlight_owned)

    def test_failure_cleanup_preserves_original_error(self) -> None:
        prepare = function_body(self.panel, "static int r46h_panel_prepare")
        cleanup = prepare[prepare.index("disable_supplies:") :]
        self.assertIn("cleanup_ret = r46h_panel_disable_supplies(ctx);", cleanup)
        self.assertIn("ret, cleanup_ret", cleanup)
        self.assertIn("return ret;", cleanup)
        self.assertNotIn("regulator_enable", cleanup)

    def test_enable_rejects_an_uninitialized_panel(self) -> None:
        enable = function_body(self.panel, "static int r46h_panel_enable")
        initialized_guard = enable.index("if (!ctx->initialized)")
        failure = enable.index("return -EIO;")
        delay = enable.index("msleep(120);")
        self.assertLess(initialized_guard, failure)
        self.assertLess(failure, delay)
        self.assertEqual(re.findall(r"msleep\([^;]+\);", enable), ["msleep(120);"])

        disable = function_body(
            self.panel, "static int r46h_panel_disable(struct drm_panel *panel)"
        )
        self.assertEqual(re.findall(r"msleep\([^;]+\);", disable), ["msleep(50);"])

    def test_unprepare_preserves_residual_refs_without_sticking_drm_state(self) -> None:
        unprepare = function_body(self.panel, "static int r46h_panel_unprepare")
        initialized_guard = unprepare.index("if (ctx->initialized)")
        display_off = unprepare.index("mipi_dsi_dcs_set_display_off")
        initialized_clear = unprepare.index("ctx->initialized = false;")
        reset = unprepare.index("r46h_panel_assert_reset(ctx)")
        disable = unprepare.index("r46h_panel_disable_supplies(ctx)")
        self.assertLess(initialized_guard, display_off)
        self.assertLess(display_off, initialized_clear)
        self.assertLess(initialized_clear, reset)
        self.assertLess(reset, disable)
        self.assertIn("return 0;", unprepare)
        self.assertNotIn("return disable_ret;", unprepare)
        self.assertIn("DRM clears panel->prepared", unprepare)
        self.assertIn("next prepare", unprepare)
        self.assertEqual(
            re.findall(r"(?:m|u)sleep(?:_range)?\([^;]+\);", unprepare),
            [
                "msleep(20);",
                "usleep_range(10000, 15000);",
                "msleep(20);",
            ],
        )

        prepare = function_body(self.panel, "static int r46h_panel_prepare")
        display_on = prepare.index("mipi_dsi_dcs_set_display_on")
        initialized_set = prepare.index("ctx->initialized = true;", display_on)
        self.assertLess(display_on, initialized_set)

    def test_remove_releases_failed_prepare_residual_refs(self) -> None:
        remove = function_body(self.panel, "static void r46h_panel_remove")
        unprepared_guard = remove.index("if (!ctx->panel.prepared &&")
        residual_guard = remove.index(
            "ctx->supply_enabled[R46H_PANEL_SUPPLY_BACKLIGHT] ||"
        )
        reset = remove.index("r46h_panel_assert_reset(ctx)", residual_guard)
        cleanup = remove.index("r46h_panel_disable_supplies(ctx)", reset)
        detach = remove.index("mipi_dsi_detach(dsi)")
        panel_remove = remove.index("drm_panel_remove(&ctx->panel);")
        self.assertLess(unprepared_guard, residual_guard)
        self.assertLess(residual_guard, reset)
        self.assertLess(reset, cleanup)
        self.assertLess(cleanup, detach)
        self.assertLess(detach, panel_remove)
        self.assertNotIn("drm_panel_disable", remove)
        self.assertNotIn("drm_panel_unprepare", remove)
        self.assertIn("failed to release residual panel supplies", remove)

    def test_panel_dts_names_both_required_rails(self) -> None:
        panel_node = re.search(r"&internal_display \{(.*?)\n\};", self.dts, re.DOTALL)
        self.assertIsNotNone(panel_node)
        body = panel_node.group(1)
        self.assertEqual(body.count("backlight-supply = <&vcc_bl>;"), 1)
        self.assertEqual(body.count("power-supply = <&vcc_lcd>;"), 1)


class PatchSeriesAndDtbTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not KERNEL_TARBALL.is_file():
            raise unittest.SkipTest(f"missing cached kernel tarball: {KERNEL_TARBALL}")
        cache = MAINLINE / ".cache"
        cache.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="r46h-panel-power-test.", dir=cache
        )
        cls.root = pathlib.Path(cls.temporary.name)
        cls.source = cls.root / "linux-6.12.99"
        members = [
            "linux-6.12.99/arch/arm64/boot/dts/rockchip",
            "linux-6.12.99/include/dt-bindings",
            "linux-6.12.99/include/uapi/linux/input-event-codes.h",
            "linux-6.12.99/drivers/gpu/drm/panel/Kconfig",
            "linux-6.12.99/drivers/gpu/drm/panel/Makefile",
            "linux-6.12.99/drivers/gpu/drm/rockchip/dw-mipi-dsi-rockchip.c",
            "linux-6.12.99/drivers/phy/rockchip/phy-rockchip-inno-dsidphy.c",
            "linux-6.12.99/drivers/input/joystick/adc-joystick.c",
            "linux-6.12.99/drivers/power/supply/rk817_charger.c",
            "linux-6.12.99/drivers/mmc/host/dw_mmc.c",
            "linux-6.12.99/Documentation/devicetree/bindings/mfd/rockchip,rk817.yaml",
        ]
        subprocess.run(
            ["tar", "-xJf", str(KERNEL_TARBALL), "-C", str(cls.root), *members],
            check=True,
        )
        cls.patches = [PATCH_DIR / name for name in ALL_PATCH_NAMES]
        cls.after_0003 = None
        cls.after_active = None
        for patch in cls.patches:
            with patch.open("rb") as patch_input:
                subprocess.run(
                    ["patch", "--directory", str(cls.source), "--strip=1", "--forward"],
                    stdin=patch_input,
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                )
            if patch.name == PANEL_PATCH_NAMES[2]:
                cls.after_0003 = {
                    "dts": (
                        cls.source
                        / "arch/arm64/boot/dts/rockchip/rk3326-r46h.dts"
                    ).read_bytes(),
                    "panel": (
                        cls.source / "drivers/gpu/drm/panel/panel-r46h.c"
                    ).read_bytes(),
                }
            if patch.name.startswith(f"{ACTIVE_PATCH_LAST}-"):
                cls.after_active = {
                    "dts": (
                        cls.source
                        / "arch/arm64/boot/dts/rockchip/rk3326-r46h.dts"
                    ).read_bytes(),
                    "panel": (
                        cls.source / "drivers/gpu/drm/panel/panel-r46h.c"
                    ).read_bytes(),
                }

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def test_0003_changes_only_panel_and_dts(self) -> None:
        patch = PATCH_DIR / "0003-drm-panel-r46h-enable-backlight-rail-before-init.patch"
        changed = re.findall(
            r"^diff --git a/(\S+) b/(\S+)$",
            patch.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        self.assertEqual(
            changed,
            [
                (
                    "arch/arm64/boot/dts/rockchip/rk3326-r46h.dts",
                    "arch/arm64/boot/dts/rockchip/rk3326-r46h.dts",
                ),
                (
                    "drivers/gpu/drm/panel/panel-r46h.c",
                    "drivers/gpu/drm/panel/panel-r46h.c",
                ),
            ],
        )

    def test_0003_postimage_oids_match_reviewable_sources(self) -> None:
        self.assertIsNotNone(self.after_0003)
        patch = (
            PATCH_DIR / "0003-drm-panel-r46h-enable-backlight-rail-before-init.patch"
        ).read_text(encoding="utf-8")
        index_lines = re.findall(r"^index [0-9a-f]+\.\.([0-9a-f]+) 100644$", patch, re.MULTILINE)
        self.assertEqual(
            index_lines,
            [
                git_blob_oid(self.after_0003["dts"])[:7],
                git_blob_oid(self.after_0003["panel"])[:7],
            ],
        )

    def test_active_patch_series_matches_reviewable_sources(self) -> None:
        self.assertEqual(
            [path.name for path in sorted(PATCH_DIR.glob("*.patch"))],
            ALL_PATCH_NAMES,
        )
        self.assertIsNotNone(self.after_active)
        self.assertEqual(self.after_active["panel"], PANEL.read_bytes())
        self.assertEqual(self.after_active["dts"], DTS.read_bytes())

    def test_compiled_dtb_resolves_panel_supplies_to_ldo8_then_ldo7(self) -> None:
        if shutil.which("docker") is None:
            self.skipTest("Docker is unavailable")
        image = subprocess.run(
            ["docker", "image", "inspect", BUILDER_IMAGE],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if image.returncode != 0:
            self.skipTest(f"builder image is unavailable: {BUILDER_IMAGE}")

        script = r"""
set -eu
src=/work/linux-6.12.99
cpp -nostdinc -I "$src/include" -I "$src/arch/arm64/boot/dts" \
  -undef -D__DTS__ -x assembler-with-cpp \
  "$src/arch/arm64/boot/dts/rockchip/rk3326-r46h.dts" \
  > /work/rk3326-r46h.preprocessed.dts
dtc -q -I dts -O dtb -o /work/rk3326-r46h.dtb \
  /work/rk3326-r46h.preprocessed.dts
panel=/dsi@ff450000/panel@0
regulators=/i2c@ff180000/pmic@20/regulators
test "$(fdtget -t x /work/rk3326-r46h.dtb "$panel" power-supply)" = \
     "$(fdtget -t x /work/rk3326-r46h.dtb "$regulators/LDO_REG8" phandle)"
test "$(fdtget -t x /work/rk3326-r46h.dtb "$panel" backlight-supply)" = \
     "$(fdtget -t x /work/rk3326-r46h.dtb "$regulators/LDO_REG7" phandle)"
"""
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--platform",
                "linux/arm64",
                "--mount",
                f"type=bind,src={self.root},dst=/work",
                BUILDER_IMAGE,
                "sh",
                "-c",
                script,
            ],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
