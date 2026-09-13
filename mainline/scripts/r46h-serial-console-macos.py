#!/usr/bin/env python3
"""Capture the R46H two-speed serial console on macOS without pyserial."""

from __future__ import annotations

import argparse
import fcntl
import os
import select
import signal
import struct
import sys
import termios
import tty
from pathlib import Path
from typing import Sequence


# _IOW('T', 2, speed_t). macOS speed_t is an unsigned long (8 bytes on the
# supported 64-bit hosts), so the ioctl payload and size bits are both 8 bytes.
IOSSIOSPEED = 0x80085402
EXIT_BYTE = b"\x1d"  # Ctrl-]
AUTOBOOT_INTERRUPT_BYTE = b"\x03"  # Ctrl-C
UBOOT_AUTOBOOT_TRIGGER = b"Hit key to stop autoboot('CTRL+C'):"
CAPTURE_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


class CaptureSignal(Exception):
    def __init__(self, signum: int) -> None:
        super().__init__(f"received signal {signum}")
        self.signum = signum


class TriggerMatcher:
    """Find one byte string even when it is split across serial reads."""

    def __init__(self, trigger: bytes) -> None:
        if not trigger:
            raise ValueError("trigger must not be empty")
        self._trigger = trigger
        self._tail = b""

    def feed(self, data: bytes) -> bool:
        combined = self._tail + data
        matched = self._trigger in combined
        tail_length = len(self._trigger) - 1
        self._tail = combined[-tail_length:] if tail_length else b""
        return matched


class CaptureTriggerState:
    """Order the one-shot baud switch before the one-shot U-Boot interrupt."""

    def __init__(self, switch_trigger: bytes | None, interrupt_autoboot: bool) -> None:
        self._switch_matcher = (
            TriggerMatcher(switch_trigger) if switch_trigger is not None else None
        )
        self._autoboot_matcher = (
            TriggerMatcher(UBOOT_AUTOBOOT_TRIGGER) if interrupt_autoboot else None
        )
        self.switched = False
        self.autoboot_interrupt_sent = False

    def feed(self, data: bytes) -> tuple[bool, bool]:
        """Return (switch_now, interrupt_now) for one serial read.

        Bytes from the read that triggers the baud switch were received at the
        old rate. They are deliberately never fed to the U-Boot matcher.
        """

        if (
            self._switch_matcher is not None
            and not self.switched
            and self._switch_matcher.feed(data)
        ):
            self.switched = True
            return True, False
        if (
            self._autoboot_matcher is not None
            and self.switched
            and not self.autoboot_interrupt_sent
            and self._autoboot_matcher.feed(data)
        ):
            self.autoboot_interrupt_sent = True
            return False, True
        return False, False


def split_at_exit_byte(data: bytes) -> tuple[bytes, bool]:
    """Return bytes to transmit and whether Ctrl-] requested local exit."""

    index = data.find(EXIT_BYTE)
    if index < 0:
        return data, False
    return data[:index], True


def positive_baud(value: str) -> int:
    try:
        baud = int(value, 10)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a decimal integer") from exc
    if baud <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    if baud > (1 << (8 * struct.calcsize("@L"))) - 1:
        raise argparse.ArgumentTypeError("does not fit macOS speed_t")
    return baud


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture an R46H serial console on macOS, optionally switching "
            "from the early-boot baud rate to the U-Boot/Linux baud rate "
            "after an exact byte trigger."
        ),
        epilog=(
            "Interactive mode sends keyboard input to the device; press "
            "Ctrl-] to exit locally. The log parent directory must already "
            "exist and an existing log is never overwritten. The optional "
            "autoboot interrupt is sent only after the configured baud switch "
            "and the exact U-Boot prompt is observed."
        ),
    )
    parser.add_argument(
        "device",
        help="macOS callout device, for example /dev/cu.usbserial-3140",
    )
    parser.add_argument(
        "baud",
        type=positive_baud,
        help="initial baud rate, normally 1500000 for R46H early boot",
    )
    parser.add_argument(
        "log",
        type=Path,
        help="new binary log path; its parent directory must already exist",
    )
    parser.add_argument(
        "--switch-trigger",
        metavar="TEXT",
        help="exact UTF-8 text whose first occurrence triggers a baud switch",
    )
    parser.add_argument(
        "--switch-baud",
        metavar="BAUD",
        type=positive_baud,
        help="new baud rate; required together with --switch-trigger",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="forward terminal input to the serial port; Ctrl-] exits locally",
    )
    parser.add_argument(
        "--interrupt-autoboot",
        action="store_true",
        help=(
            "after switching baud, send one Ctrl-C when the exact verified "
            "g92 U-Boot autoboot prompt is observed; requires --interactive"
        ),
    )
    return parser


def parse_cli_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    has_trigger = args.switch_trigger is not None
    has_switch_baud = args.switch_baud is not None
    if has_trigger != has_switch_baud:
        parser.error("--switch-trigger and --switch-baud must be provided together")
    if has_trigger and args.switch_trigger == "":
        parser.error("--switch-trigger must not be empty")
    if args.interrupt_autoboot and not has_trigger:
        parser.error("--interrupt-autoboot requires a configured baud switch")
    if args.interrupt_autoboot and not args.interactive:
        parser.error("--interrupt-autoboot requires --interactive")
    return args


def pack_macos_speed(baud: int) -> bytes:
    payload = struct.pack("@L", baud)
    if len(payload) != 8:
        raise RuntimeError("IOSSIOSPEED requires a 64-bit macOS speed_t")
    return payload


def configure_serial(fd: int, baud: int, *, flush_input: bool) -> None:
    attrs = termios.tcgetattr(fd)
    attrs[0] = 0
    attrs[1] = 0
    attrs[2] &= ~(
        termios.CSIZE
        | termios.PARENB
        | termios.CSTOPB
        | getattr(termios, "CRTSCTS", 0)
    )
    attrs[2] |= termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[3] = 0

    # 115200 is a native macOS termios speed. For non-standard rates such as
    # 1500000, establish a valid termios baseline and then use IOSSIOSPEED.
    standard_baud = {115200: termios.B115200}.get(baud)
    attrs[4] = standard_baud if standard_baud is not None else termios.B9600
    attrs[5] = standard_baud if standard_baud is not None else termios.B9600
    attrs[6][termios.VMIN] = 1
    attrs[6][termios.VTIME] = 0

    custom_speed = standard_baud is None
    try:
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    except termios.error:
        # Some USB serial drivers reject even a nominally standard rate via
        # tcsetattr. Fall back to the same IOSSIOSPEED path used for 1500000.
        if standard_baud is None:
            raise
        attrs[4] = termios.B9600
        attrs[5] = termios.B9600
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        custom_speed = True

    if custom_speed:
        fcntl.ioctl(fd, IOSSIOSPEED, pack_macos_speed(baud))
    if flush_input:
        termios.tcflush(fd, termios.TCIFLUSH)

    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)


def claim_exclusive_serial(fd: int) -> None:
    request = getattr(termios, "TIOCEXCL", None)
    if request is None:
        raise RuntimeError("macOS termios does not expose TIOCEXCL")
    fcntl.ioctl(fd, request)


def write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        try:
            written = os.write(fd, view)
        except BlockingIOError:
            select.select([], [fd], [])
            continue
        if written <= 0:
            raise OSError("write returned no progress")
        view = view[written:]


def open_private_log(log_path: Path):
    """Atomically reserve a new 0600 log before touching the serial device."""

    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    log_fd = os.open(log_path, flags, 0o600)
    try:
        return os.fdopen(log_fd, "wb", buffering=0)
    except BaseException:
        os.close(log_fd)
        try:
            log_path.unlink()
        except OSError:
            pass
        raise


def clean_capture_exit(
    switch_requested: bool,
    switch_observed: bool,
    interrupt_requested: bool = False,
    interrupt_sent: bool = False,
) -> int:
    switch_state = "yes" if switch_observed else "not-requested"
    if switch_requested and not switch_observed:
        switch_state = "no"
    interrupt_state = "yes" if interrupt_sent else "not-requested"
    if interrupt_requested and not interrupt_sent:
        interrupt_state = "no"
    print(
        f"capture summary: switch_observed={switch_state}",
        file=sys.stderr,
        flush=True,
    )
    print(
        f"capture summary: autoboot_interrupt_sent={interrupt_state}",
        file=sys.stderr,
        flush=True,
    )
    if switch_requested and not switch_observed:
        print(
            "capture ended before the requested baud-switch trigger was observed",
            file=sys.stderr,
            flush=True,
        )
        return 2
    if interrupt_requested and not interrupt_sent:
        print(
            "capture ended before the verified U-Boot autoboot prompt was observed",
            file=sys.stderr,
            flush=True,
        )
        return 3
    return 0


def capture(args: argparse.Namespace) -> int:
    if sys.platform != "darwin":
        raise RuntimeError("this tool requires macOS IOSSIOSPEED support")
    if args.interactive and not sys.stdin.isatty():
        raise RuntimeError("--interactive requires a terminal on standard input")

    log_path = args.log.expanduser()
    if not log_path.parent.is_dir():
        raise RuntimeError(f"log parent directory does not exist: {log_path.parent}")

    stdin_fd: int | None = None
    stdin_attrs: list[object] | None = None
    serial_fd: int | None = None
    capture_ready = False
    log_file = open_private_log(log_path)
    try:
        with log_file:
            serial_fd = os.open(
                args.device,
                os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK,
            )
            claim_exclusive_serial(serial_fd)
            configure_serial(serial_fd, args.baud, flush_input=True)
            capture_ready = True
            trigger_state = CaptureTriggerState(
                args.switch_trigger.encode("utf-8")
                if args.switch_trigger is not None
                else None,
                args.interrupt_autoboot,
            )

            print(
                f"ready device={args.device} baud={args.baud} log={log_path}",
                file=sys.stderr,
                flush=True,
            )
            if args.interactive:
                print("interactive mode: press Ctrl-] to exit", file=sys.stderr, flush=True)
                stdin_fd = sys.stdin.fileno()
                stdin_attrs = termios.tcgetattr(stdin_fd)
                tty.setraw(stdin_fd)

            while True:
                readers = [serial_fd]
                if stdin_fd is not None:
                    readers.append(stdin_fd)
                readable, _, _ = select.select(readers, [], [])

                if serial_fd in readable:
                    data = os.read(serial_fd, 4096)
                    if not data:
                        raise RuntimeError("serial device disconnected")
                    switch_now, interrupt_now = trigger_state.feed(data)
                    if switch_now:
                        configure_serial(serial_fd, args.switch_baud, flush_input=False)
                        print(
                            f"\nswitched baud={args.switch_baud} "
                            f"after trigger={args.switch_trigger!r}",
                            file=sys.stderr,
                            flush=True,
                        )
                    if interrupt_now:
                        write_all(serial_fd, AUTOBOOT_INTERRUPT_BYTE)
                        print(
                            "\nsent Ctrl-C after verified U-Boot autoboot prompt",
                            file=sys.stderr,
                            flush=True,
                        )
                    # Time-sensitive serial actions must precede external-disk
                    # logging and terminal output.
                    log_file.write(data)
                    write_all(sys.stdout.fileno(), data)

                if stdin_fd is not None and stdin_fd in readable:
                    outgoing = os.read(stdin_fd, 4096)
                    if not outgoing:
                        return clean_capture_exit(
                            args.switch_trigger is not None,
                            trigger_state.switched,
                            args.interrupt_autoboot,
                            trigger_state.autoboot_interrupt_sent,
                        )
                    payload, should_exit = split_at_exit_byte(outgoing)
                    if payload:
                        write_all(serial_fd, payload)
                    if should_exit:
                        return clean_capture_exit(
                            args.switch_trigger is not None,
                            trigger_state.switched,
                            args.interrupt_autoboot,
                            trigger_state.autoboot_interrupt_sent,
                        )
    finally:
        try:
            if stdin_fd is not None and stdin_attrs is not None:
                termios.tcsetattr(stdin_fd, termios.TCSANOW, stdin_attrs)
        finally:
            if serial_fd is not None:
                os.close(serial_fd)
            if not capture_ready:
                try:
                    log_path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as error:
                    print(
                        f"warning: cannot remove unused log reservation "
                        f"{log_path}: {error}",
                        file=sys.stderr,
                    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_cli_args(argv)
    original_handlers = {
        handled_signal: signal.getsignal(handled_signal)
        for handled_signal in CAPTURE_SIGNALS
    }

    def raise_signal(signum: int, _frame: object) -> None:
        # Ignore a second termination signal while capture() restores the tty.
        for handled_signal in CAPTURE_SIGNALS:
            signal.signal(handled_signal, signal.SIG_IGN)
        raise CaptureSignal(signum)

    for handled_signal in CAPTURE_SIGNALS:
        signal.signal(handled_signal, raise_signal)
    try:
        return capture(args)
    except KeyboardInterrupt:
        print("capture interrupted: signal=SIGINT", file=sys.stderr)
        return 130
    except CaptureSignal as exc:
        print(f"capture interrupted: signal={exc.signum}", file=sys.stderr)
        return 128 + exc.signum
    except (OSError, RuntimeError, termios.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        for handled_signal, original_handler in original_handlers.items():
            signal.signal(handled_signal, original_handler)


if __name__ == "__main__":
    raise SystemExit(main())
