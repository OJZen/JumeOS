#!/usr/bin/env python3
"""Host-side pure tests for r46h-display-diagnostic.py."""

import ctypes
import errno
import importlib.util
import io
import pathlib
import unittest
from unittest import mock


SCRIPT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "scripts"
    / "r46h-display-diagnostic.py"
)
SPEC = importlib.util.spec_from_file_location("r46h_display_diagnostic", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def xrgb8888_mode(width=8, height=2):
    var = MODULE.FbVarScreeninfo()
    var.xres = width
    var.yres = height
    var.xres_virtual = width
    var.yres_virtual = height
    var.bits_per_pixel = 32
    var.red.offset, var.red.length = 16, 8
    var.green.offset, var.green.length = 8, 8
    var.blue.offset, var.blue.length = 0, 8
    return var


class DisplayDiagnosticTests(unittest.TestCase):
    def test_supported_kernel_releases_are_an_exact_five_entry_allowlist(self):
        self.assertEqual(
            MODULE.SUPPORTED_RELEASES,
            (
                "6.12.99-r46h-mainline-v0.4-dsi396",
                "6.12.99-r46h-mainline-v0.5-ldo7",
                "6.12.99-r46h-mainline-v0.6-ldo7",
                "6.12.99-r46h-mainline-v0.7-host-timers",
                "6.12.99-r46h-mainline-v0.8-bootloader-handoff",
            ),
        )
        for supported_release in MODULE.SUPPORTED_RELEASES:
            self.assertTrue(MODULE.is_supported_release(supported_release))
        for near_match in (
            "6.12.99-r46h-mainline-v0.7-host-timers+",
            "6.12.99-r46h-mainline-v0.7-host-timers-dirty",
            "6.12.99-r46h-mainline-v0.7-host",
            "6.12.100-r46h-mainline-v0.7-host-timers",
            "6.12.99-r46h-mainline-v0.8-bootloader-handoff+",
            "6.12.99-r46h-mainline-v0.8-bootloader-handoff-dirty",
            "6.12.99-r46h-mainline-v0.8-bootloader",
            "6.12.100-r46h-mainline-v0.8-bootloader-handoff",
        ):
            self.assertFalse(MODULE.is_supported_release(near_match))

    def battery_voltage_fixture(self, entries, files):
        with mock.patch.object(
            MODULE.os, "listdir", return_value=entries
        ), mock.patch.object(
            MODULE.os.path, "isfile", side_effect=lambda path: path in files
        ), mock.patch.object(MODULE, "read_text", side_effect=lambda path: files[path]):
            return MODULE.read_battery_voltage("/power")

    def test_battery_voltage_prefers_voltage_now_and_records_source(self):
        files = {
            "/power/rk817-battery/type": "Battery",
            "/power/rk817-battery/voltage_now": "3987000",
            "/power/rk817-battery/voltage_avg": "3928030",
            "/power/usb/type": "USB",
        }
        self.assertEqual(
            self.battery_voltage_fixture(("usb", "rk817-battery"), files),
            (3987000, "/power/rk817-battery/voltage_now"),
        )

    def test_battery_voltage_falls_back_to_voltage_avg(self):
        files = {
            "/power/rk817-battery/type": "Battery",
            "/power/rk817-battery/voltage_avg": "3928030",
        }
        self.assertEqual(
            self.battery_voltage_fixture(("rk817-battery",), files),
            (3928030, "/power/rk817-battery/voltage_avg"),
        )

    def test_battery_voltage_rejects_multiple_battery_supplies(self):
        files = {
            "/power/battery-a/type": "Battery",
            "/power/battery-a/voltage_now": "3928030",
            "/power/battery-b/type": "Battery",
            "/power/battery-b/voltage_avg": "3928030",
        }
        with self.assertRaisesRegex(MODULE.DiagnosticError, "multiple type=Battery"):
            self.battery_voltage_fixture(("battery-b", "battery-a"), files)

    def test_battery_voltage_rejects_non_integer_preferred_value(self):
        files = {
            "/power/rk817-battery/type": "Battery",
            "/power/rk817-battery/voltage_now": "unknown",
            "/power/rk817-battery/voltage_avg": "3928030",
        }
        with self.assertRaisesRegex(
            MODULE.DiagnosticError,
            "not an integer.*voltage_now",
        ):
            self.battery_voltage_fixture(("rk817-battery",), files)

    def test_battery_voltage_rejects_missing_voltage_attributes(self):
        files = {
            "/power/rk817-battery/type": "Battery",
        }
        with self.assertRaisesRegex(
            MODULE.DiagnosticError,
            "missing voltage_now and voltage_avg",
        ):
            self.battery_voltage_fixture(("rk817-battery",), files)

    def test_voltage_avg_uses_extra_safety_margin(self):
        with mock.patch.object(
            MODULE,
            "read_battery_voltage",
            return_value=(3650000, "/power/battery/voltage_avg"),
        ):
            with self.assertRaisesRegex(MODULE.DiagnosticError, "minimum=3700000"):
                MODULE.require_safe_battery_voltage("test")

    def test_long_observation_rechecks_battery_every_thirty_seconds(self):
        self.assertEqual(
            MODULE.observation_checkpoints(120),
            [0.0, 2.0, 5.0, 30.0, 60.0, 90.0, 120.0],
        )

    def test_linux_arm64_fbdev_structure_sizes(self):
        self.assertEqual(ctypes.sizeof(MODULE.FbBitfield), 12)
        self.assertEqual(ctypes.sizeof(MODULE.FbVarScreeninfo), 160)
        self.assertEqual(ctypes.sizeof(MODULE.FbFixScreeninfo), 80)

    def test_xrgb8888_pixel_encoding(self):
        var = xrgb8888_mode()
        self.assertEqual(MODULE.encode_pixel(255, 0, 0, var), b"\x00\x00\xff\x00")
        self.assertEqual(MODULE.encode_pixel(0, 255, 0, var), b"\x00\xff\x00\x00")
        self.assertEqual(MODULE.encode_pixel(0, 0, 255, var), b"\xff\x00\x00\x00")
        self.assertEqual(MODULE.encode_pixel(255, 255, 255, var), b"\xff\xff\xff\x00")

    def test_rgb565_scaling_and_encoding(self):
        var = MODULE.FbVarScreeninfo()
        var.xres = 1
        var.yres = 1
        var.bits_per_pixel = 16
        var.red.offset, var.red.length = 11, 5
        var.green.offset, var.green.length = 5, 6
        var.blue.offset, var.blue.length = 0, 5
        self.assertEqual(MODULE.encode_pixel(255, 255, 255, var), b"\xff\xff")
        self.assertEqual(MODULE.encode_pixel(255, 0, 0, var), b"\x00\xf8")

    def test_eight_bar_order_and_width(self):
        var = xrgb8888_mode(width=8, height=1)
        row = MODULE.pattern_row("bars", 0, var)
        pixels = [row[index : index + 4] for index in range(0, len(row), 4)]
        self.assertEqual(
            pixels,
            [
                b"\xff\xff\xff\x00",
                b"\x00\xff\xff\x00",
                b"\xff\xff\x00\x00",
                b"\x00\xff\x00\x00",
                b"\xff\x00\xff\x00",
                b"\x00\x00\xff\x00",
                b"\xff\x00\x00\x00",
                b"\x00\x00\x00\x00",
            ],
        )

    def test_prepared_pattern_rows_are_reused_without_regeneration(self):
        var = xrgb8888_mode(width=8, height=3)
        with mock.patch.object(
            MODULE,
            "pattern_row",
            wraps=MODULE.pattern_row,
        ) as row_builder:
            rows = MODULE.prepare_pattern_rows("bars", var)
            expected_hash = MODULE.pattern_rows_hash(rows)
            self.assertEqual(len(rows), 3)
            self.assertEqual(row_builder.call_count, 3)
            self.assertEqual(MODULE.pattern_rows_hash(rows), expected_hash)
            self.assertEqual(row_builder.call_count, 3)

    def test_display_descriptor_target_filter(self):
        self.assertTrue(MODULE.is_display_target("/dev/fb0"))
        self.assertTrue(MODULE.is_display_target("/dev/dri/card0"))
        self.assertTrue(MODULE.is_display_target("/dev/dri/renderD128 (deleted)"))
        self.assertFalse(MODULE.is_display_target("/dev/ttyS2"))
        self.assertFalse(MODULE.is_display_target("/dev/fb1"))

    def test_pattern_failure_still_restores_full_snapshot(self):
        var = xrgb8888_mode(width=1, height=1)
        fix = MODULE.FbFixScreeninfo()
        fix.smem_len = 4
        fingerprint = ("stable",)
        expected_hash = MODULE.expected_pattern_hash("white", var)

        with mock.patch.object(
            MODULE,
            "open_framebuffer",
            return_value=(123, var, fix, fingerprint),
        ), mock.patch.object(
            MODULE,
            "read_exact_at",
            side_effect=(b"orig", b"orig"),
        ), mock.patch.object(
            MODULE,
            "verify_pattern",
            return_value=(expected_hash, "different", 0),
        ), mock.patch.object(
            MODULE, "write_pattern"
        ), mock.patch.object(
            MODULE, "write_all_at"
        ) as restore_write, mock.patch.object(
            MODULE, "sync_framebuffer"
        ), mock.patch.object(
            MODULE, "require_quiescent"
        ), mock.patch.object(
            MODULE, "require_safe_battery_voltage"
        ), mock.patch.object(
            MODULE, "drm_scanout_fingerprint"
        ), mock.patch.object(
            MODULE.time, "sleep"
        ), mock.patch.object(
            MODULE.os, "close"
        ), mock.patch("sys.stdout", new_callable=io.StringIO):
            with self.assertRaises(MODULE.DiagnosticError):
                MODULE.run_pattern("white", 5, {}, "scanout")

        restore_write.assert_called_once_with(123, b"orig", 0)

    def test_framebuffer_close_failure_cannot_skip_snapshot_restore(self):
        var = xrgb8888_mode(width=1, height=1)
        fix = MODULE.FbFixScreeninfo()
        fix.smem_len = 4
        fingerprint = ("stable",)

        with mock.patch.object(
            MODULE,
            "open_framebuffer",
            return_value=(123, var, fix, fingerprint),
        ), mock.patch.object(
            MODULE,
            "read_exact_at",
            side_effect=(b"orig", b"orig"),
        ), mock.patch.object(
            MODULE, "write_pattern"
        ), mock.patch.object(
            MODULE, "write_all_at"
        ) as restore_write, mock.patch.object(
            MODULE, "sync_framebuffer"
        ), mock.patch.object(
            MODULE.os,
            "close",
            side_effect=(OSError(errno.EIO, "injected close failure"), None),
        ), mock.patch("sys.stdout", new_callable=io.StringIO), mock.patch(
            "sys.stderr", new_callable=io.StringIO
        ):
            with self.assertRaises(OSError):
                MODULE.run_pattern("white", 5, {}, "scanout")

        restore_write.assert_called_once_with(123, b"orig", 0)

    def test_cli_requires_exactly_one_mode(self):
        self.assertEqual(MODULE.parse_args(["--pattern", "white"]).hold_seconds, 30)
        self.assertTrue(MODULE.parse_args(["--prepare-only"]).prepare_only)
        self.assertTrue(MODULE.parse_args(["--host-vpg"]).host_vpg)
        with mock.patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit):
                MODULE.parse_args([])
            with self.assertRaises(SystemExit):
                MODULE.parse_args(["--prepare-only", "--pattern", "white"])
            with self.assertRaises(SystemExit):
                MODULE.parse_args(["--prepare-only", "--host-vpg"])

    def test_host_vpg_failure_still_disables_generator(self):
        initial = (False, False, False)
        with mock.patch.object(
            MODULE.os.path, "isfile", return_value=True
        ), mock.patch.object(
            MODULE,
            "host_vpg_state",
            side_effect=(initial, (False, False, False), initial),
        ), mock.patch.object(
            MODULE,
            "write_debugfs_bool",
        ) as write_flag, mock.patch.object(
            MODULE,
            "interruptible_sleep",
        ), mock.patch.object(
            MODULE,
            "require_quiescent",
        ), mock.patch.object(
            MODULE,
            "require_safe_battery_voltage",
        ), mock.patch.object(
            MODULE,
            "drm_scanout_fingerprint",
        ), mock.patch("sys.stdout", new_callable=io.StringIO):
            with self.assertRaisesRegex(
                MODULE.DiagnosticError,
                "state changed",
            ):
                MODULE.run_host_vpg(5, {}, "scanout")

        self.assertEqual(
            write_flag.call_args_list,
            [
                mock.call(MODULE.HOST_VPG_PATH, True),
                mock.call(MODULE.HOST_VPG_PATH, False),
            ],
        )

    def test_host_vpg_restore_retries_once_after_write_failure(self):
        initial = (False, False, False)
        with mock.patch.object(
            MODULE,
            "write_debugfs_bool",
            side_effect=(OSError(errno.EIO, "injected restore failure"), None),
        ) as write_flag, mock.patch.object(
            MODULE,
            "host_vpg_state",
            return_value=initial,
        ), mock.patch("sys.stdout", new_callable=io.StringIO):
            MODULE.restore_host_vpg(initial)

        self.assertEqual(
            write_flag.call_args_list,
            [
                mock.call(MODULE.HOST_VPG_PATH, False),
                mock.call(MODULE.HOST_VPG_PATH, False),
            ],
        )

    def test_command_timeout_is_bounded_and_reported(self):
        timeout = MODULE.subprocess.TimeoutExpired(
            cmd=("systemctl", "stop", "mpv.service"),
            timeout=15,
            output=b"partial output",
        )
        with mock.patch.object(MODULE.subprocess, "run", side_effect=timeout):
            code, output = MODULE.run_command(
                ("systemctl", "stop", "mpv.service"),
                timeout_seconds=15,
            )
        self.assertEqual(code, 124)
        self.assertIn("timed out after 15s", output)
        self.assertIn("partial output", output)

    def test_signal_is_recorded_but_cannot_interrupt_cleanup(self):
        MODULE.RECEIVED_SIGNALS.clear()
        MODULE.CLEANUP_ACTIVE = True
        try:
            MODULE.record_signal(MODULE.signal.SIGTERM, None)
            MODULE.raise_if_signal_received()
            MODULE.CLEANUP_ACTIVE = False
            with self.assertRaises(MODULE.DiagnosticError):
                MODULE.raise_if_signal_received()
        finally:
            MODULE.CLEANUP_ACTIVE = False
            MODULE.RECEIVED_SIGNALS.clear()

    def test_vt_entry_failure_rolls_back_before_fd_is_lost(self):
        requests = []

        def fake_ioctl(_fd, request, argument=0, *_rest):
            requests.append(request)
            if requests == [MODULE.KDGETMODE]:
                argument[0] = MODULE.KD_TEXT
                return 0
            if requests == [
                MODULE.KDGETMODE,
                MODULE.KDSETMODE,
                MODULE.KDGETMODE,
            ]:
                raise OSError(errno.EIO, "injected verification failure")
            return 0

        with mock.patch.object(MODULE.os, "open", return_value=55), mock.patch.object(
            MODULE.os, "close"
        ) as close_fd, mock.patch.object(
            MODULE.fcntl, "ioctl", side_effect=fake_ioctl
        ), mock.patch("sys.stderr", new_callable=io.StringIO), mock.patch(
            "sys.stdout", new_callable=io.StringIO
        ):
            with self.assertRaises(OSError):
                MODULE.enter_graphics_vt()

        self.assertEqual(
            requests,
            [
                MODULE.KDGETMODE,
                MODULE.KDSETMODE,
                MODULE.KDGETMODE,
                MODULE.KDSETMODE,
            ],
        )
        close_fd.assert_called_once_with(55)


if __name__ == "__main__":
    unittest.main()
