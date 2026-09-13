#!/usr/bin/env python3
"""Pure-logic tests for r46h-serial-console-macos.py; no device is opened."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import pathlib
import sys
import unittest
from unittest import mock


SCRIPT = pathlib.Path(__file__).parents[1] / "scripts" / "r46h-serial-console-macos.py"
SPEC = importlib.util.spec_from_file_location("r46h_serial_console_macos", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
serial_console = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(serial_console)


class TriggerMatcherTests(unittest.TestCase):
    def test_finds_trigger_split_across_chunks(self) -> None:
        matcher = serial_console.TriggerMatcher(b"I/TC: OP-TEE version")
        self.assertFalse(matcher.feed(b"noise\nI/TC: OP-"))
        self.assertTrue(matcher.feed(b"TEE version: 3.x\n"))

    def test_finds_trigger_within_one_chunk(self) -> None:
        matcher = serial_console.TriggerMatcher(b"OP-TEE")
        self.assertTrue(matcher.feed(b"before OP-TEE after"))

    def test_does_not_join_bytes_older_than_possible_prefix(self) -> None:
        matcher = serial_console.TriggerMatcher(b"abcdef")
        self.assertFalse(matcher.feed(b"abcxxxx"))
        self.assertFalse(matcher.feed(b"def"))

    def test_rejects_empty_trigger(self) -> None:
        with self.assertRaises(ValueError):
            serial_console.TriggerMatcher(b"")


class CaptureTriggerStateTests(unittest.TestCase):
    def make_state(self) -> object:
        return serial_console.CaptureTriggerState(b"OP-TEE", True)

    def test_never_interrupts_before_switch(self) -> None:
        state = self.make_state()
        self.assertEqual(
            state.feed(serial_console.UBOOT_AUTOBOOT_TRIGGER),
            (False, False),
        )
        self.assertFalse(state.autoboot_interrupt_sent)

    def test_switch_chunk_is_not_fed_to_autoboot_matcher(self) -> None:
        state = self.make_state()
        data = b"OP-TEE" + serial_console.UBOOT_AUTOBOOT_TRIGGER
        self.assertEqual(state.feed(data), (True, False))
        self.assertTrue(state.switched)
        self.assertFalse(state.autoboot_interrupt_sent)

    def test_prompt_can_span_reads_after_switch(self) -> None:
        state = self.make_state()
        self.assertEqual(state.feed(b"OP-TEE"), (True, False))
        split = len(serial_console.UBOOT_AUTOBOOT_TRIGGER) // 2
        self.assertEqual(
            state.feed(serial_console.UBOOT_AUTOBOOT_TRIGGER[:split]),
            (False, False),
        )
        self.assertEqual(
            state.feed(serial_console.UBOOT_AUTOBOOT_TRIGGER[split:]),
            (False, True),
        )

    def test_interrupt_is_emitted_only_once(self) -> None:
        state = self.make_state()
        self.assertEqual(state.feed(b"OP-TEE"), (True, False))
        self.assertEqual(
            state.feed(serial_console.UBOOT_AUTOBOOT_TRIGGER),
            (False, True),
        )
        self.assertEqual(
            state.feed(serial_console.UBOOT_AUTOBOOT_TRIGGER),
            (False, False),
        )


class ArgumentTests(unittest.TestCase):
    def parse_error(self, argv: list[str]) -> int:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as caught:
                serial_console.parse_cli_args(argv)
        return caught.exception.code

    def test_accepts_paired_switch_options(self) -> None:
        args = serial_console.parse_cli_args(
            [
                "/dev/cu.example",
                "1500000",
                "/tmp/new.log",
                "--switch-trigger",
                "I/TC: OP-TEE version",
                "--switch-baud",
                "115200",
                "--interactive",
            ]
        )
        self.assertEqual(args.baud, 1_500_000)
        self.assertEqual(args.switch_baud, 115_200)
        self.assertTrue(args.interactive)

    def test_accepts_explicit_autoboot_interrupt_with_interactive_switch(self) -> None:
        args = serial_console.parse_cli_args(
            [
                "/dev/cu.example",
                "1500000",
                "/tmp/new.log",
                "--switch-trigger",
                "I/TC: OP-TEE version",
                "--switch-baud",
                "115200",
                "--interactive",
                "--interrupt-autoboot",
            ]
        )
        self.assertTrue(args.interrupt_autoboot)

    def test_rejects_trigger_without_switch_baud(self) -> None:
        self.assertEqual(
            self.parse_error(
                [
                    "/dev/cu.example",
                    "1500000",
                    "/tmp/new.log",
                    "--switch-trigger",
                    "OP-TEE",
                ]
            ),
            2,
        )

    def test_rejects_switch_baud_without_trigger(self) -> None:
        self.assertEqual(
            self.parse_error(
                [
                    "/dev/cu.example",
                    "1500000",
                    "/tmp/new.log",
                    "--switch-baud",
                    "115200",
                ]
            ),
            2,
        )

    def test_rejects_non_positive_baud(self) -> None:
        self.assertEqual(
            self.parse_error(["/dev/cu.example", "0", "/tmp/new.log"]),
            2,
        )

    def test_rejects_autoboot_interrupt_without_switch(self) -> None:
        self.assertEqual(
            self.parse_error(
                [
                    "/dev/cu.example",
                    "1500000",
                    "/tmp/new.log",
                    "--interactive",
                    "--interrupt-autoboot",
                ]
            ),
            2,
        )

    def test_rejects_autoboot_interrupt_without_interactive_mode(self) -> None:
        self.assertEqual(
            self.parse_error(
                [
                    "/dev/cu.example",
                    "1500000",
                    "/tmp/new.log",
                    "--switch-trigger",
                    "I/TC: OP-TEE version",
                    "--switch-baud",
                    "115200",
                    "--interrupt-autoboot",
                ]
            ),
            2,
        )


class InteractiveTests(unittest.TestCase):
    def test_ctrl_right_bracket_is_local_exit_and_not_transmitted(self) -> None:
        payload, should_exit = serial_console.split_at_exit_byte(b"help\r\x1dignored")
        self.assertEqual(payload, b"help\r")
        self.assertTrue(should_exit)

    def test_regular_input_is_transmitted_unchanged(self) -> None:
        payload, should_exit = serial_console.split_at_exit_byte(b"boot\r")
        self.assertEqual(payload, b"boot\r")
        self.assertFalse(should_exit)

    def test_requested_switch_must_be_observed_for_clean_exit(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            status = serial_console.clean_capture_exit(True, False)
        self.assertEqual(status, 2)
        self.assertIn("switch_observed=no", stderr.getvalue())
        self.assertIn("autoboot_interrupt_sent=not-requested", stderr.getvalue())

    def test_clean_exit_reports_observed_or_not_requested_switch(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(serial_console.clean_capture_exit(True, True), 0)
            self.assertEqual(serial_console.clean_capture_exit(False, False), 0)
        self.assertIn("switch_observed=yes", stderr.getvalue())
        self.assertIn("switch_observed=not-requested", stderr.getvalue())

    def test_requested_autoboot_interrupt_must_be_sent_for_clean_exit(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            status = serial_console.clean_capture_exit(True, True, True, False)
        self.assertEqual(status, 3)
        self.assertIn("switch_observed=yes", stderr.getvalue())
        self.assertIn("autoboot_interrupt_sent=no", stderr.getvalue())

    def test_clean_exit_reports_sent_autoboot_interrupt(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            status = serial_console.clean_capture_exit(True, True, True, True)
        self.assertEqual(status, 0)
        self.assertIn("autoboot_interrupt_sent=yes", stderr.getvalue())

    def test_verified_uboot_autoboot_prompt_is_exact(self) -> None:
        self.assertEqual(
            serial_console.UBOOT_AUTOBOOT_TRIGGER,
            b"Hit key to stop autoboot('CTRL+C'):",
        )
        self.assertEqual(serial_console.AUTOBOOT_INTERRUPT_BYTE, b"\x03")


class MacOSIoctlTests(unittest.TestCase):
    def test_iossiospeed_uses_64_bit_speed_payload(self) -> None:
        self.assertEqual(serial_console.IOSSIOSPEED, 0x80085402)
        self.assertEqual(len(serial_console.pack_macos_speed(1_500_000)), 8)

    def test_serial_device_is_claimed_exclusive(self) -> None:
        with mock.patch.object(serial_console.fcntl, "ioctl") as ioctl:
            serial_console.claim_exclusive_serial(42)
        ioctl.assert_called_once_with(42, serial_console.termios.TIOCEXCL)


class CaptureOrderingTests(unittest.TestCase):
    def test_existing_log_is_rejected_before_serial_device_is_opened(self) -> None:
        args = serial_console.parse_cli_args(
            ["/dev/cu.example", "1500000", "/logs/existing.log"]
        )
        with mock.patch.object(sys, "platform", "darwin"), mock.patch.object(
            pathlib.Path,
            "is_dir",
            return_value=True,
        ), mock.patch.object(
            serial_console.os,
            "open",
            side_effect=FileExistsError("existing log"),
        ) as open_fd, mock.patch.object(
            serial_console,
            "configure_serial",
        ) as configure:
            with self.assertRaises(FileExistsError):
                serial_console.capture(args)

        self.assertEqual(open_fd.call_count, 1)
        self.assertEqual(open_fd.call_args.args[0], pathlib.Path("/logs/existing.log"))
        self.assertTrue(open_fd.call_args.args[1] & serial_console.os.O_EXCL)
        self.assertEqual(open_fd.call_args.args[2], 0o600)
        configure.assert_not_called()

    def test_keyboard_interrupt_is_not_reported_as_success(self) -> None:
        with mock.patch.object(
            serial_console,
            "parse_cli_args",
            return_value=mock.sentinel.args,
        ), mock.patch.object(
            serial_console,
            "capture",
            side_effect=KeyboardInterrupt,
        ), contextlib.redirect_stderr(io.StringIO()) as stderr:
            status = serial_console.main([])

        self.assertEqual(status, 130)
        self.assertIn("SIGINT", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
