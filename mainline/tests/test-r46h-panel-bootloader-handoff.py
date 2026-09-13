#!/usr/bin/env python3
"""Fail-closed source and patch tests for the R46H panel handoff."""

from __future__ import annotations

import hashlib
import pathlib
import re
import subprocess
import tempfile
import unittest


MAINLINE = pathlib.Path(__file__).resolve().parents[1]
PANEL = MAINLINE / "board" / "r46h" / "panel-r46h.c"
DTS = MAINLINE / "board" / "r46h" / "rk3326-r46h.dts"
PATCH_DIR = MAINLINE / "patches"
KERNEL_TARBALL = MAINLINE / ".cache" / "kernel" / "linux-6.12.99.tar.xz"
KERNEL_TARBALL_SHA256 = (
    "6a477222c132033381cda981eb0127f29fbcbba17e820283bc21290f8e408629"
)
EXPECTED_SEQUENCE_SHA256 = (
    "b6d1e77241ae5d97168e7324c000c44459a56352cc09eff3d2e954bf2046d6dd"
)
PATCH_NAMES = [
    "0001-arm64-dts-rockchip-add-R46H-mainline-bring-up.patch",
    "0002-drm-rockchip-use-r46h-dsi-lane-rate.patch",
    "0003-drm-panel-r46h-enable-backlight-rail-before-init.patch",
    "0004-drm-rockchip-use-r46h-dsi-host-timers.patch",
    "0005-drm-panel-r46h-preserve-bootloader-handoff.patch",
    "0006-input-joystick-adc-use-axis-code-for-inversion.patch",
    "0007-arm64-dts-rockchip-use-r46h-adc-full-range.patch",
    "0008-power-supply-rk817-support-a-board-DC-input.patch",
    "0009-arm64-dts-rockchip-use-rk817-150ma-charge-termination.patch",
    "0010-mmc-dw-log-request-errors.patch",
]

KERNEL_PANEL = pathlib.Path("drivers/gpu/drm/panel/panel-r46h.c")
KERNEL_DTS = pathlib.Path(
    "arch/arm64/boot/dts/rockchip/rk3326-r46h.dts"
)
GENERIC_DSI = pathlib.Path("drivers/gpu/drm/bridge/synopsys/dw-mipi-dsi.c")
ROCKCHIP_DSI = pathlib.Path(
    "drivers/gpu/drm/rockchip/dw-mipi-dsi-rockchip.c"
)
DPHY = pathlib.Path("drivers/phy/rockchip/phy-rockchip-inno-dsidphy.c")


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


def command_stream(source: str) -> tuple[int, bytes]:
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
    sequence = b"".join(
        bytes((0x15, 0x00, 0x02, command, value))
        for command, value in commands
    )
    sequence += bytes((0x05, 0xC8, 0x01, 0x11))
    sequence += bytes((0x05, 0x14, 0x01, 0x29))
    return len(commands), sequence


def git_blob_oid(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def file_sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def apply_patch(source: pathlib.Path, patch: pathlib.Path) -> None:
    with patch.open("rb") as patch_input:
        subprocess.run(
            ["patch", "--directory", str(source), "--strip=1", "--forward"],
            stdin=patch_input,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )


def assert_tokens_in_order(
    case: unittest.TestCase, source: str, tokens: list[str]
) -> None:
    cursor = 0
    for token in tokens:
        position = source.find(token, cursor)
        case.assertNotEqual(position, -1, f"missing ordered token: {token}")
        cursor = position + len(token)


class PanelHandoffSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.panel = PANEL.read_text(encoding="utf-8")

    def test_vendor_command_stream_remains_167_writes_and_843_bytes(self) -> None:
        command_count, sequence = command_stream(self.panel)
        self.assertEqual(command_count, 167)
        self.assertEqual(len(sequence), 843)
        self.assertEqual(hashlib.sha256(sequence).hexdigest(), EXPECTED_SEQUENCE_SHA256)

        writer = function_body(
            self.panel, "static int r46h_panel_write_init_sequence"
        )
        self.assertEqual(writer.count("mipi_dsi_dcs_write("), 1)
        self.assertEqual(writer.count("ARRAY_SIZE(r46h_panel_init_commands)"), 1)

    def test_probe_requests_reset_without_driving_it(self) -> None:
        probe = function_body(self.panel, "static int r46h_panel_probe")
        self.assertEqual(
            probe.count(
                'devm_gpiod_get(dev, "reset", GPIOD_ASIS)'
            ),
            1,
        )
        self.assertNotIn("GPIOD_OUT_HIGH", probe)
        assert_tokens_in_order(
            self,
            probe,
            [
                "drm_panel_of_backlight(&ctx->panel)",
                "r46h_panel_arm_bootloader_handoff(ctx)",
                "drm_panel_add(&ctx->panel)",
                "mipi_dsi_attach(dsi)",
            ],
        )

    def test_handoff_gate_requires_raw_high_output_and_both_live_rails(self) -> None:
        self.assertEqual(
            self.panel.count("#define R46H_PANEL_POWER_UV\t\t2800000"), 1
        )
        self.assertEqual(
            self.panel.count("#define R46H_PANEL_BACKLIGHT_UV\t3300000"), 1
        )
        read = function_body(
            self.panel, "r46h_panel_read_handoff_state"
        )
        for expression in (
            "gpiod_get_direction(ctx->reset_gpio)",
            "gpiod_get_raw_value_cansleep(ctx->reset_gpio)",
            "regulator_is_enabled(power)",
            "regulator_is_enabled(backlight)",
            "regulator_get_voltage(power)",
            "regulator_get_voltage(backlight)",
        ):
            self.assertEqual(read.count(expression), 1)

        ready = function_body(
            self.panel, "r46h_panel_handoff_state_ready"
        )
        compact = re.sub(r"\s+", " ", ready)
        for condition in (
            "state->reset_direction == 0",
            "state->reset_raw == 1",
            "state->power_enabled > 0",
            "state->backlight_enabled > 0",
            "state->power_uv == R46H_PANEL_POWER_UV",
            "state->backlight_uv == R46H_PANEL_BACKLIGHT_UV",
        ):
            self.assertEqual(compact.count(condition), 1)
        self.assertNotIn("gpiod_get_value", read)

    def test_adoption_is_revalidated_after_both_consumer_refs(self) -> None:
        arm = function_body(
            self.panel, "static int r46h_panel_arm_bootloader_handoff"
        )
        reads = [
            match.start()
            for match in re.finditer(
                re.escape("r46h_panel_read_handoff_state(ctx, &state);"), arm
            )
        ]
        ready_checks = [
            match.start()
            for match in re.finditer(
                re.escape("r46h_panel_handoff_state_ready(&state)"), arm
            )
        ]
        self.assertEqual(
            len(reads), 2, "handoff state must be read before and after ref adoption"
        )
        self.assertEqual(
            len(ready_checks), 2, "both handoff state reads must be validated"
        )
        power_enable = arm.index("ret = regulator_enable(power);")
        power_owned = arm.index(
            "ctx->supply_enabled[R46H_PANEL_SUPPLY_POWER] = true;"
        )
        backlight_enable = arm.index("ret = regulator_enable(backlight);")
        backlight_owned = arm.index(
            "ctx->supply_enabled[R46H_PANEL_SUPPLY_BACKLIGHT] = true;"
        )
        pending = arm.index("ctx->handoff_pending = true;")
        self.assertLess(reads[0], ready_checks[0])
        self.assertLess(ready_checks[0], power_enable)
        self.assertLess(power_enable, power_owned)
        self.assertLess(power_owned, backlight_enable)
        self.assertLess(backlight_enable, backlight_owned)
        self.assertLess(backlight_owned, reads[1])
        self.assertLess(reads[1], ready_checks[1])
        self.assertLess(ready_checks[1], pending)

    def test_partial_adoption_rolls_back_in_reverse_order(self) -> None:
        arm = function_body(
            self.panel, "static int r46h_panel_arm_bootloader_handoff"
        )
        power_enable = arm.index("ret = regulator_enable(power);")
        backlight_enable = arm.index("ret = regulator_enable(backlight);")
        rollback = arm.index("r46h_panel_disable_supplies(ctx);", backlight_enable)
        reset = arm.rfind("r46h_panel_assert_reset(ctx);", backlight_enable, rollback)
        self.assertGreater(reset, backlight_enable)
        self.assertLess(reset, rollback)

        cleanup = function_body(
            self.panel, "static int r46h_panel_disable_supplies"
        )
        assert_tokens_in_order(
            self,
            cleanup,
            [
                "if (ctx->supply_enabled[R46H_PANEL_SUPPLY_BACKLIGHT])",
                "regulator_disable(backlight);",
                "ctx->supply_enabled[R46H_PANEL_SUPPLY_BACKLIGHT] = false;",
                "if (ctx->supply_enabled[R46H_PANEL_SUPPLY_POWER])",
                "regulator_disable(power);",
                "ctx->supply_enabled[R46H_PANEL_SUPPLY_POWER] = false;",
            ],
        )
        self.assertLess(power_enable, backlight_enable)
        self.assertNotIn("regulator_bulk_disable", arm)
        self.assertNotIn("regulator_bulk_disable", cleanup)

    def test_post_adoption_drift_asserts_and_releases_before_fallback(self) -> None:
        arm = function_body(
            self.panel, "static int r46h_panel_arm_bootloader_handoff"
        )
        checks = [
            match.start()
            for match in re.finditer(
                re.escape("if (!r46h_panel_handoff_state_ready(&state))"), arm
            )
        ]
        self.assertEqual(len(checks), 2)
        drift = arm[checks[1] : arm.index("ctx->handoff_pending = true;")]
        assert_tokens_in_order(
            self,
            drift,
            [
                "stage=probe decision=fallback reason=state-drift",
                "r46h_panel_assert_reset(ctx);",
                "r46h_panel_disable_supplies(ctx);",
                "msleep(20);",
                "return 0;",
            ],
        )
        self.assertNotIn("ctx->handoff_pending = true;", drift)

    def test_every_fallback_asserts_reset_direction_before_cleanup(self) -> None:
        helper = function_body(self.panel, "static int r46h_panel_assert_reset")
        self.assertEqual(
            helper.count("gpiod_direction_output(ctx->reset_gpio, 1)"), 1
        )
        self.assertNotIn("gpiod_set_value", helper)

        arm = function_body(
            self.panel, "static int r46h_panel_arm_bootloader_handoff"
        )
        initial_reject = arm[
            arm.index("if (!r46h_panel_handoff_state_ready(&state))") :
            arm.index("ret = regulator_enable(power);")
        ]
        self.assertIn("return r46h_panel_assert_reset(ctx);", initial_reject)

        prepare = function_body(self.panel, "static int r46h_panel_prepare")
        drift = prepare[
            prepare.index("action=fallback-full-init") :
            prepare.index(
                "if (ctx->supply_enabled[R46H_PANEL_SUPPLY_BACKLIGHT] ||"
            )
        ]
        assert_tokens_in_order(
            self,
            drift,
            [
                "r46h_panel_assert_reset(ctx);",
                "r46h_panel_disable_supplies(ctx);",
                "msleep(20);",
            ],
        )

    def test_first_prepare_preserves_state_without_reset_dcs_or_rail_cycle(self) -> None:
        prepare = function_body(self.panel, "static int r46h_panel_prepare")
        handoff_start = prepare.index("if (ctx->handoff_pending)")
        normal_start = prepare.index(
            "if (ctx->supply_enabled[R46H_PANEL_SUPPLY_BACKLIGHT] ||",
            handoff_start,
        )
        handoff = prepare[handoff_start:normal_start]
        preserve_start = handoff.index(
            "if (r46h_panel_handoff_state_ready(&state))"
        )
        preserve_end = handoff.index("return 0;", preserve_start) + len("return 0;")
        preserve = handoff[preserve_start:preserve_end]
        assert_tokens_in_order(
            self,
            preserve,
            [
                "ctx->handoff_active = true;",
                "ctx->initialized = true;",
                "stage=prepare action=preserve",
                "return 0;",
            ],
        )
        for forbidden in (
            "regulator_enable",
            "regulator_disable",
            "gpiod_",
            "r46h_panel_assert_reset",
            "r46h_panel_write_init_sequence",
            "mipi_dsi_dcs_",
            "msleep",
        ):
            self.assertNotIn(forbidden, preserve)

        normal = prepare[normal_start:]
        assert_tokens_in_order(
            self,
            normal,
            [
                "r46h_panel_assert_reset(ctx)",
                "regulator_enable(power)",
                "regulator_enable(backlight)",
                "gpiod_set_value_cansleep(ctx->reset_gpio, 1)",
                "gpiod_set_value_cansleep(ctx->reset_gpio, 0)",
                "r46h_panel_write_init_sequence(ctx)",
                "mipi_dsi_dcs_exit_sleep_mode(ctx->dsi)",
                "mipi_dsi_dcs_set_display_on(ctx->dsi)",
                "ctx->initialized = true;",
            ],
        )

    def test_first_enable_consumes_handoff_then_normal_delay_remains(self) -> None:
        enable = function_body(self.panel, "static int r46h_panel_enable")
        handoff_start = enable.index("if (ctx->handoff_active)")
        handoff_end = enable.index("return 0;", handoff_start) + len("return 0;")
        handoff = enable[handoff_start:handoff_end]
        assert_tokens_in_order(
            self,
            handoff,
            [
                "ctx->handoff_active = false;",
                "stage=enable action=consume-first-enable",
                "return 0;",
            ],
        )
        self.assertNotIn("msleep", handoff)
        self.assertEqual(enable.count("msleep(120);"), 1)
        self.assertGreater(enable.index("msleep(120);"), handoff_end)

    def test_unprepare_consumes_handoff_and_restores_full_future_init(self) -> None:
        unprepare = function_body(self.panel, "static int r46h_panel_unprepare")
        assert_tokens_in_order(
            self,
            unprepare,
            [
                "mipi_dsi_dcs_set_display_off(ctx->dsi)",
                "mipi_dsi_dcs_enter_sleep_mode(ctx->dsi)",
                "r46h_panel_assert_reset(ctx)",
                "r46h_panel_disable_supplies(ctx)",
                "ctx->handoff_pending = false;",
                "ctx->handoff_active = false;",
                "ctx->handoff_used = false;",
                "stage=unprepare next=full-init",
            ],
        )
        self.assertNotIn("ctx->handoff_pending = true;", unprepare)

        prepare = function_body(self.panel, "static int r46h_panel_prepare")
        self.assertEqual(prepare.count("if (ctx->handoff_pending)"), 1)
        self.assertEqual(prepare.count("r46h_panel_write_init_sequence(ctx)"), 1)

    def test_attach_failure_asserts_reset_and_releases_owned_refs(self) -> None:
        probe = function_body(self.panel, "static int r46h_panel_probe")
        attach = probe.index("ret = mipi_dsi_attach(dsi);")
        failure = probe.index("if (ret) {", attach)
        tail = probe[failure:]
        assert_tokens_in_order(
            self,
            tail,
            [
                "ctx->handoff_pending = false;",
                "r46h_panel_assert_reset(ctx);",
                "r46h_panel_disable_supplies(ctx);",
                "drm_panel_remove(&ctx->panel);",
                "return dev_err_probe(dev, ret",
            ],
        )
        self.assertIn("failed to rollback panel after attach error", tail)

    def test_markers_make_adopt_fallback_use_and_retirement_auditable(self) -> None:
        for marker in (
            "R46H_PANEL_HANDOFF stage=probe decision=fallback reason=state ",
            "R46H_PANEL_HANDOFF stage=probe decision=fallback reason=state-drift",
            "R46H_PANEL_HANDOFF stage=probe decision=adopt",
            "R46H_PANEL_HANDOFF stage=prepare action=preserve",
            "R46H_PANEL_HANDOFF stage=prepare action=fallback-full-init",
            "R46H_PANEL_HANDOFF stage=enable action=consume-first-enable",
            "R46H_PANEL_HANDOFF stage=unprepare next=full-init",
        ):
            self.assertEqual(self.panel.count(marker), 1, marker)
        self.assertNotIn("ctx->panel.prepared =", self.panel)
        self.assertNotIn("ctx->panel.enabled =", self.panel)


class PanelHandoffPatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not KERNEL_TARBALL.is_file():
            raise unittest.SkipTest(f"missing cached kernel tarball: {KERNEL_TARBALL}")
        if file_sha256(KERNEL_TARBALL) != KERNEL_TARBALL_SHA256:
            raise AssertionError(f"kernel tarball SHA-256 mismatch: {KERNEL_TARBALL}")

        cache = MAINLINE / ".cache"
        cache.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(
            prefix="r46h-panel-handoff-test.", dir=cache
        )
        cls.root = pathlib.Path(cls.temporary.name)
        cls.source = cls.root / "linux-6.12.99"
        members = [
            "linux-6.12.99/arch/arm64/boot/dts/rockchip",
            "linux-6.12.99/include/dt-bindings",
            "linux-6.12.99/include/uapi/linux/input-event-codes.h",
            "linux-6.12.99/drivers/gpu/drm/bridge/synopsys/dw-mipi-dsi.c",
            "linux-6.12.99/drivers/gpu/drm/panel/Kconfig",
            "linux-6.12.99/drivers/gpu/drm/panel/Makefile",
            "linux-6.12.99/drivers/gpu/drm/rockchip/dw-mipi-dsi-rockchip.c",
            "linux-6.12.99/drivers/phy/rockchip/phy-rockchip-inno-dsidphy.c",
        ]
        subprocess.run(
            ["tar", "-xJf", str(KERNEL_TARBALL), "-C", str(cls.root), *members],
            check=True,
        )
        for name in PATCH_NAMES[:4]:
            apply_patch(cls.source, PATCH_DIR / name)

        cls.after_0004 = {
            path: (cls.source / path).read_bytes()
            for path in (KERNEL_PANEL, KERNEL_DTS, GENERIC_DSI, ROCKCHIP_DSI, DPHY)
        }
        cls.patch_0005 = PATCH_DIR / PATCH_NAMES[4]
        cls.applied_0005 = cls.patch_0005.is_file()
        if cls.applied_0005:
            apply_patch(cls.source, cls.patch_0005)

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def require_0005(self) -> None:
        self.assertTrue(
            self.applied_0005,
            f"missing handoff patch: {self.patch_0005}",
        )

    def test_patch_series_is_exact(self) -> None:
        self.assertEqual(
            [path.name for path in sorted(PATCH_DIR.glob("*.patch"))],
            PATCH_NAMES,
        )

    def test_0005_changes_only_panel_driver(self) -> None:
        self.require_0005()
        changed = re.findall(
            r"^diff --git a/(\S+) b/(\S+)$",
            self.patch_0005.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
        self.assertEqual(changed, [(str(KERNEL_PANEL), str(KERNEL_PANEL))])

    def test_0005_postimage_matches_review_source(self) -> None:
        self.require_0005()
        patch = self.patch_0005.read_text(encoding="utf-8")
        match = re.search(
            rf"^diff --git a/{re.escape(str(KERNEL_PANEL))} .*?"
            r"^index [0-9a-f]+\.\.([0-9a-f]+) 100644$",
            patch,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(match)
        replayed = (self.source / KERNEL_PANEL).read_bytes()
        self.assertEqual(match.group(1), git_blob_oid(replayed)[:7])
        self.assertEqual(replayed, PANEL.read_bytes())

    def test_0005_leaves_dts_dsi_core_glue_and_dphy_byte_identical(self) -> None:
        self.require_0005()
        self.assertNotEqual(
            (self.source / KERNEL_PANEL).read_bytes(),
            self.after_0004[KERNEL_PANEL],
        )
        for path in (KERNEL_DTS, GENERIC_DSI, ROCKCHIP_DSI, DPHY):
            self.assertEqual(
                (self.source / path).read_bytes(), self.after_0004[path], path
            )


if __name__ == "__main__":
    unittest.main()
