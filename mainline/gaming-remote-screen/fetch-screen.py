#!/usr/bin/env python3
"""Fetch one guarded gaming-frontend screenshot from the accepted R46H target."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import shlex
import stat
import struct
import subprocess
import sys
import tempfile
import zlib


REPO = Path(__file__).resolve().parents[2]
CACHE_ROOT = REPO / "mainline/out/.cache/r46h-remote-screen"
OUTPUT_ROOT = REPO / "mainline/out/r46h-screenshots"
SSH = "/usr/bin/ssh"
SSH_KEYGEN = "/usr/bin/ssh-keygen"
MAX_PNG_BYTES = 16 * 1024 * 1024
EXPECTED_WIDTH = 1024
EXPECTED_HEIGHT = 768
EXPECTED_ROW_BYTES = 1 + EXPECTED_WIDTH * 3
EXPECTED_RAW_BYTES = EXPECTED_ROW_BYTES * EXPECTED_HEIGHT
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"\x00\x00\x00\x00IEND\xaeB\x60\x82"
MARKER_RE = re.compile(
    r"^R46H_SCREENSHOT result=pass "
    r"name=(r46h-screen-[0-9]{8}T[0-9]{6}Z-[1-9][0-9]*\.png) "
    r"bytes=([1-9][0-9]*) sha256=([0-9a-f]{64})$"
)


class FetchError(RuntimeError):
    """A bounded validation, transport or cleanup failure."""


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Trigger the fixed R46H frontend screenshot helper over public-key SSH, "
            "verify the PNG, and publish it below mainline/out."
        )
    )
    result.add_argument("--host", required=True, help="current R46H IPv4 address")
    result.add_argument("--identity", required=True, type=Path, help="dedicated private key")
    result.add_argument(
        "--known-hosts",
        required=True,
        type=Path,
        help="one previously verified R46H ED25519 known_hosts entry",
    )
    result.add_argument("--port", type=int, default=22, help="SSH port (default: 22)")
    return result


def safe_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(PATH="/usr/bin:/bin:/usr/sbin:/sbin", LC_ALL="C", LANG="C")
    for name in ("SSH_ASKPASS", "SSH_ASKPASS_REQUIRE", "DISPLAY"):
        environment.pop(name, None)
    return environment


def validate_host(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise FetchError("--host must be one literal IPv4 address") from error
    if address.version != 4 or str(address) != value:
        raise FetchError("--host must be one canonical literal IPv4 address")
    return value


def validate_port(value: int) -> int:
    if value < 1 or value > 65535:
        raise FetchError("--port must be between 1 and 65535")
    return value


def local_regular_file(path: Path, label: str, private: bool) -> Path:
    candidate = path.expanduser().absolute()
    try:
        metadata = os.lstat(candidate)
    except OSError as error:
        raise FetchError(f"{label} is unavailable: {candidate}") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise FetchError(f"{label} must be a regular non-symlink file")
    if metadata.st_uid != os.getuid() or metadata.st_nlink != 1:
        raise FetchError(f"{label} must be user-owned with one link")
    if metadata.st_size <= 0:
        raise FetchError(f"{label} must not be empty")
    mode = stat.S_IMODE(metadata.st_mode)
    if private and mode & 0o077:
        raise FetchError(f"{label} must not grant group/world permissions")
    if not private and mode & 0o022:
        raise FetchError(f"{label} must not be group/world writable")
    return candidate


def validate_known_hosts(path: Path, host: str, port: int) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise FetchError("cannot read known_hosts as UTF-8") from error
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    expected_host = host if port == 22 else f"[{host}]:{port}"
    if len(lines) != 1:
        raise FetchError("known_hosts must contain exactly one non-comment entry")
    fields = lines[0].split()
    if len(fields) != 3 or fields[0] != expected_host or fields[1] != "ssh-ed25519":
        raise FetchError("known_hosts is not the exact R46H ED25519 host entry")
    result = checked_capture(
        [SSH_KEYGEN, "-F", expected_host, "-f", str(path)],
        "known_hosts address binding verification",
    )
    if "ssh-ed25519" not in result.stdout:
        raise FetchError("known_hosts address binding is missing")


def prepare_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    metadata = os.lstat(path)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise FetchError(f"unsafe output directory: {path}")


def checked_capture(arguments: list[str], label: str) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            arguments,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=safe_environment(),
        )
    except OSError as error:
        raise FetchError(f"cannot start {label}") from error
    if result.returncode != 0:
        detail = next(
            (line.strip() for line in reversed(result.stderr.splitlines()) if line.strip()),
            "no diagnostic",
        )
        raise FetchError(f"{label} failed ({result.returncode}): {detail[:300]}")
    return result


def checked_binary_to_file(arguments: list[str], destination: Path, label: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(destination, flags, 0o600)
    except OSError as error:
        raise FetchError(f"cannot create bounded output for {label}") from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            result = subprocess.run(
                arguments,
                check=False,
                stdout=stream,
                stderr=subprocess.PIPE,
                text=False,
                env=safe_environment(),
            )
    except OSError as error:
        destination.unlink(missing_ok=True)
        raise FetchError(f"cannot start {label}") from error
    if result.returncode != 0:
        destination.unlink(missing_ok=True)
        stderr = result.stderr.decode("utf-8", errors="replace")
        detail = next(
            (line.strip() for line in reversed(stderr.splitlines()) if line.strip()),
            "no diagnostic",
        )
        raise FetchError(f"{label} failed ({result.returncode}): {detail[:300]}")
    if destination.stat().st_size > MAX_PNG_BYTES:
        destination.unlink(missing_ok=True)
        raise FetchError(f"{label} exceeded the 16 MiB bound")


def ssh_options(identity: Path, known_hosts: Path, port: int) -> list[str]:
    return [
        "-F",
        "/dev/null",
        "-i",
        str(identity),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "PreferredAuthentications=publickey",
        "-o",
        "PasswordAuthentication=no",
        "-o",
        "KbdInteractiveAuthentication=no",
        "-o",
        "NumberOfPasswordPrompts=0",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        f"UserKnownHostsFile={known_hosts}",
        "-o",
        "HostKeyAlgorithms=ssh-ed25519",
        "-o",
        "UpdateHostKeys=no",
        "-o",
        "ClearAllForwardings=yes",
        "-o",
        "ConnectTimeout=10",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        "ServerAliveInterval=5",
        "-o",
        "ServerAliveCountMax=2",
        "-o",
        "LogLevel=ERROR",
        "-o",
        f"Port={port}",
    ]


def parse_marker(stdout: str) -> tuple[str, int, str]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise FetchError("target screenshot helper returned unexpected output")
    match = MARKER_RE.fullmatch(lines[0])
    if match is None:
        raise FetchError("target screenshot marker is invalid")
    name, bytes_text, digest = match.groups()
    byte_count = int(bytes_text)
    if byte_count < len(PNG_SIGNATURE) + len(PNG_IEND):
        raise FetchError("target screenshot is too short to be a complete PNG")
    if byte_count > MAX_PNG_BYTES:
        raise FetchError("target screenshot exceeds the 16 MiB bound")
    return name, byte_count, digest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def validate_png(path: Path, expected_bytes: int, expected_sha256: str) -> None:
    metadata = os.lstat(path)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
    ):
        raise FetchError("downloaded screenshot identity is unsafe")
    if metadata.st_size != expected_bytes:
        raise FetchError("downloaded screenshot size mismatch")
    if sha256_file(path) != expected_sha256:
        raise FetchError("downloaded screenshot SHA-256 mismatch")
    validate_png_structure(path.read_bytes())


def validate_png_structure(data: bytes, *, profile: str = "drm", width: int = EXPECTED_WIDTH,
                           height: int = EXPECTED_HEIGHT) -> None:
    if profile not in {"drm", "qt"} or not (0 < width <= 4096 and 0 < height <= 4096 and width * height <= 4194304):
        raise FetchError("unsupported screenshot profile or dimensions")
    if profile == "drm" and (width, height) != (EXPECTED_WIDTH, EXPECTED_HEIGHT):
        raise FetchError("DRM capture requires the fixed target dimensions")
    row_bytes = EXPECTED_ROW_BYTES
    raw_bytes = EXPECTED_RAW_BYTES
    if not data.startswith(PNG_SIGNATURE):
        raise FetchError("downloaded screenshot has no PNG signature")
    offset = len(PNG_SIGNATURE)
    chunk_index = 0
    idat_closed = False
    idat_parts: list[bytes] = []
    saw_idat = False
    saw_iend = False
    while offset < len(data):
        if len(data) - offset < 12:
            raise FetchError("downloaded screenshot has a truncated PNG chunk")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            raise FetchError("downloaded screenshot PNG chunk exceeds the file")
        payload = data[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", data[offset + 8 + length : chunk_end])[0]
        actual_crc = zlib.crc32(chunk_type + payload) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise FetchError("downloaded screenshot PNG chunk CRC mismatch")
        if chunk_index == 0:
            if chunk_type != b"IHDR" or length != 13:
                raise FetchError("downloaded screenshot has no valid first IHDR")
            header = struct.unpack(">IIBBBBB", payload)
            if profile == "drm" and header != (EXPECTED_WIDTH, EXPECTED_HEIGHT, 8, 2, 0, 0, 0):
                raise FetchError("downloaded screenshot IHDR does not match fixed RGB output")
            if profile == "qt":
                if header[:3] != (width, height, 8) or header[3] not in (2, 6) or header[4:] != (0, 0, 0):
                    raise FetchError("Qt capture requires bounded non-interlaced RGB/RGBA")
                row_bytes = 1 + width * (3 if header[3] == 2 else 4)
                raw_bytes = row_bytes * height
        elif chunk_type == b"IHDR":
            raise FetchError("downloaded screenshot contains a duplicate IHDR")
        if profile == "qt" and chunk_type not in (b"IHDR", b"IDAT", b"IEND") and not (chunk_type[0] & 32):
            raise FetchError("Qt capture has an unsupported critical chunk")
        if chunk_type == b"IDAT":
            if idat_closed:
                raise FetchError("downloaded screenshot has non-consecutive IDAT chunks")
            saw_idat = True
            idat_parts.append(payload)
        elif saw_idat:
            idat_closed = True
        if chunk_type == b"IEND":
            if length != 0 or chunk_end != len(data):
                raise FetchError("downloaded screenshot has an invalid PNG IEND")
            saw_iend = True
        offset = chunk_end
        chunk_index += 1
    if not saw_idat or not saw_iend or not data.endswith(PNG_IEND):
        raise FetchError("downloaded screenshot is not a complete PNG")
    compressed = b"".join(idat_parts)
    decoder = zlib.decompressobj()
    try:
        raw = decoder.decompress(compressed, raw_bytes + 1)
    except zlib.error as error:
        raise FetchError("downloaded screenshot IDAT stream is invalid") from error
    if (
        len(raw) != raw_bytes
        or not decoder.eof
        or decoder.unconsumed_tail
        or decoder.unused_data
    ):
        raise FetchError("downloaded screenshot RGB payload has an invalid size")
    filters = {0} if profile == "drm" else {0, 1, 2, 3, 4}
    if any(raw[offset] not in filters for offset in range(0, raw_bytes, row_bytes)):
        raise FetchError("downloaded screenshot uses an unexpected row filter")


def remote_cleanup_command(name: str, byte_count: int, digest: str) -> str:
    return " ".join(
        shlex.quote(word)
        for word in (
            "/usr/local/bin/r46h-screenshot",
            "--remove",
            name,
            str(byte_count),
            digest,
        )
    )


def remote_read_command(name: str, byte_count: int, digest: str) -> str:
    return " ".join(
        shlex.quote(word)
        for word in (
            "/usr/local/bin/r46h-screenshot",
            "--read",
            name,
            str(byte_count),
            digest,
        )
    )


def fetch(
    host: str,
    port: int,
    identity: Path,
    known_hosts: Path,
) -> tuple[Path, bool]:
    options = ssh_options(identity, known_hosts, port)
    captured = checked_capture(
        [SSH, *options, "-T", f"ark@{host}", "/usr/local/bin/r46h-screenshot"],
        "remote screenshot capture",
    )
    name, byte_count, digest = parse_marker(captured.stdout)
    final = OUTPUT_ROOT / name
    if final.exists() or final.is_symlink():
        raise FetchError(f"local screenshot already exists: {final}")

    prepare_directory(CACHE_ROOT)
    prepare_directory(OUTPUT_ROOT)
    with tempfile.TemporaryDirectory(prefix="fetch.", dir=CACHE_ROOT) as directory:
        temporary = Path(directory) / "screen.png"
        checked_binary_to_file(
            [
                SSH,
                *options,
                "-T",
                f"ark@{host}",
                remote_read_command(name, byte_count, digest),
            ],
            temporary,
            "screenshot download",
        )
        os.chmod(temporary, 0o600)
        validate_png(temporary, byte_count, digest)
        try:
            os.link(temporary, final)
        except FileExistsError as error:
            raise FetchError(f"local screenshot already exists: {final}") from error
        except OSError as error:
            raise FetchError(f"cannot publish local screenshot: {final}") from error
        temporary.unlink()
        try:
            validate_png(final, byte_count, digest)
        except (FetchError, OSError):
            final.unlink(missing_ok=True)
            raise

    cleanup_ok = True
    try:
        removed = checked_capture(
            [
                SSH,
                *options,
                "-T",
                f"ark@{host}",
                remote_cleanup_command(name, byte_count, digest),
            ],
            "remote screenshot cleanup",
        )
        expected = f"R46H_SCREENSHOT_REMOVE result=pass name={name}"
        if removed.stdout.strip() != expected:
            cleanup_ok = False
    except FetchError:
        cleanup_ok = False
    return final, cleanup_ok


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        host = validate_host(arguments.host)
        port = validate_port(arguments.port)
        identity = local_regular_file(arguments.identity, "private key", private=True)
        known_hosts = local_regular_file(
            arguments.known_hosts, "known_hosts", private=False
        )
        validate_known_hosts(known_hosts, host, port)
        screenshot, cleanup_ok = fetch(host, port, identity, known_hosts)
    except FetchError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"ERROR: local screenshot operation failed: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ERROR: interrupted", file=sys.stderr)
        return 130
    print(f"PASS: screenshot saved to {screenshot}")
    print(f"REMOTE_CLEANUP={'pass' if cleanup_ok else 'warning-pending-export-retained'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
