#!/usr/bin/env python3
"""Upload one operator-owned ROM to the accepted R46H workflow safely."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import tempfile
import uuid


EXPECTED_RELEASE = "6.12.99-r46h-mainline-v0.10-adc-full-range"
EXPECTED_HOST_KEY_FINGERPRINT = (
    "SHA256:6C7YclGZi6qYujswYZD7yKb2SaWNsGA2bxeN3xTGjps"
)
MAX_ROM_BYTES = 4 * 1024 * 1024 * 1024
SYSTEM_BY_SUFFIX = {
    ".nes": "nes",
    ".gb": "gb",
    ".gbc": "gb",
    ".gba": "gba",
    ".nds": "nds",
}
REPO = Path(__file__).resolve().parents[2]
CACHE_ROOT = REPO / "mainline/out/.cache"
SSH = "/usr/bin/ssh"
SCP = "/usr/bin/scp"
SSH_KEYGEN = "/usr/bin/ssh-keygen"
SSH_KEYSCAN = "/usr/bin/ssh-keyscan"


class UploadError(RuntimeError):
    """A bounded validation or transfer failure."""


PRECHECK_SCRIPT = r"""
set -Eeuo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
export PATH LC_ALL
readonly directory=$1
readonly final=$2
readonly candidate=$3
readonly expected_release=$4
case "$directory" in
  /roms/nes|/roms/gb|/roms/gba|/roms/nds) ;;
  *) printf 'invalid ROM directory\n' >&2; exit 1 ;;
esac
[[ "$(dirname -- "$final")" == "$directory" ]] || exit 1
[[ "$(basename -- "$final")" != .* ]] || exit 1
case "$candidate" in
  "$directory"/.r46h-upload-*) ;;
  *) printf 'invalid upload candidate\n' >&2; exit 1 ;;
esac
[[ "$(uname -r)" == "$expected_release" ]] || exit 1
[[ "$(id -u):$(id -g)" == 1000:1000 ]] || exit 1
[[ -d "$directory" && ! -L "$directory" ]] || exit 1
[[ "$(stat -c '%u:%g:%a' "$directory")" == 1000:1000:755 ]] || exit 1
[[ ! -e "$final" && ! -L "$final" ]] || {
  printf 'destination already exists\n' >&2
  exit 1
}
[[ ! -e "$candidate" && ! -L "$candidate" ]] || exit 1
[[ "$(cat /sys/fs/ext4/mmcblk0p2/errors_count)" == 0 ]] || exit 1
failed_units=$(systemctl --failed --no-legend --plain) || exit 1
[[ -z "$failed_units" ]] || exit 1
printf 'R46H_ROM_UPLOAD_PREFLIGHT result=pass\n'
""".strip()


PUBLISH_SCRIPT = r"""
set -Eeuo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
export PATH LC_ALL
readonly directory=$1
readonly final=$2
readonly candidate=$3
readonly expected_sha256=$4
readonly expected_size=$5
readonly expected_release=$6
readonly system=$7
rollback=0
on_exit() {
  status=$?
  trap - EXIT
  if (( status != 0 && rollback == 1 )); then
    rm -f -- "$final" || true
  fi
  exit "$status"
}
trap on_exit EXIT
case "$directory" in
  /roms/nes|/roms/gb|/roms/gba|/roms/nds) ;;
  *) exit 1 ;;
esac
[[ "$directory" == "/roms/$system" ]] || exit 1
[[ "$(dirname -- "$final")" == "$directory" ]] || exit 1
[[ "$(basename -- "$final")" != .* ]] || exit 1
case "$candidate" in
  "$directory"/.r46h-upload-*) ;;
  *) exit 1 ;;
esac
[[ "$(uname -r)" == "$expected_release" ]] || exit 1
[[ "$(id -u):$(id -g)" == 1000:1000 ]] || exit 1
[[ -d "$directory" && ! -L "$directory" ]] || exit 1
[[ "$(stat -c '%u:%g:%a' "$directory")" == 1000:1000:755 ]] || exit 1
[[ ! -e "$final" && ! -L "$final" ]] || exit 1
[[ -f "$candidate" && ! -L "$candidate" ]] || exit 1
chmod 0600 "$candidate"
[[ "$(stat -c '%u:%g:%a:%h' "$candidate")" == 1000:1000:600:1 ]] || exit 1
[[ "$(stat -c '%s' "$candidate")" == "$expected_size" ]] || exit 1
[[ "$(sha256sum "$candidate" | awk '{print $1}')" == "$expected_sha256" ]] || exit 1
chmod 0644 "$candidate"
sync -f "$candidate"
[[ "$(cat /sys/fs/ext4/mmcblk0p2/errors_count)" == 0 ]] || exit 1
failed_units=$(systemctl --failed --no-legend --plain) || exit 1
[[ -z "$failed_units" ]] || exit 1
ln -- "$candidate" "$final"
rollback=1
rm -f -- "$candidate"
[[ ! -e "$candidate" && ! -L "$candidate" ]] || exit 1
[[ -f "$final" && ! -L "$final" ]] || exit 1
[[ "$(stat -c '%u:%g:%a:%h:%s' "$final")" == \
   "1000:1000:644:1:$expected_size" ]] || exit 1
[[ "$(sha256sum "$final" | awk '{print $1}')" == "$expected_sha256" ]] || exit 1
sync -f "$final"
[[ "$(cat /sys/fs/ext4/mmcblk0p2/errors_count)" == 0 ]] || exit 1
failed_units=$(systemctl --failed --no-legend --plain) || exit 1
[[ -z "$failed_units" ]] || exit 1
printf 'R46H_ROM_UPLOAD result=pass system=%s bytes=%s sha256=%s\n' \
  "$system" "$expected_size" "$expected_sha256"
rollback=0
trap - EXIT
""".strip()


CLEANUP_SCRIPT = r"""
set -Eeuo pipefail
PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
export PATH LC_ALL
readonly directory=$1
readonly candidate=$2
case "$directory" in
  /roms/nes|/roms/gb|/roms/gba|/roms/nds) ;;
  *) exit 1 ;;
esac
case "$candidate" in
  "$directory"/.r46h-upload-*) ;;
  *) exit 1 ;;
esac
if [[ -e "$candidate" || -L "$candidate" ]]; then
  [[ ! -d "$candidate" ]] || exit 1
  rm -f -- "$candidate"
fi
""".strip()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Verify and atomically upload one NES/GB/GBC/GBA/NDS ROM to the "
            "accepted R46H ark account. Existing destination files are never replaced."
        )
    )
    result.add_argument("--host", required=True, help="current serial-verified R46H IPv4 address")
    result.add_argument(
        "--identity",
        required=True,
        type=Path,
        help="private key matching the installed ark public key",
    )
    result.add_argument("--port", type=int, default=22, help="SSH port (default: 22)")
    result.add_argument("rom", type=Path, help="one local .nes/.gb/.gbc/.gba/.nds ROM")
    return result


def safe_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        PATH="/usr/bin:/bin:/usr/sbin:/sbin",
        LC_ALL="C",
        LANG="C",
    )
    environment.pop("SSH_ASKPASS", None)
    environment.pop("SSH_ASKPASS_REQUIRE", None)
    return environment


def validate_host(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise UploadError("--host must be one literal IPv4 address") from error
    if address.version != 4 or str(address) != value:
        raise UploadError("--host must be one canonical literal IPv4 address")
    return value


def validate_port(value: int) -> int:
    if value < 1 or value > 65535:
        raise UploadError("--port must be between 1 and 65535")
    return value


def local_regular_file(path: Path, label: str, private: bool) -> tuple[Path, os.stat_result]:
    candidate = path.expanduser().absolute()
    try:
        metadata = os.lstat(candidate)
    except OSError as error:
        raise UploadError(f"{label} is unavailable: {candidate}") from error
    if not stat.S_ISREG(metadata.st_mode):
        raise UploadError(f"{label} must be a regular non-symlink file")
    if metadata.st_uid != os.getuid() or metadata.st_nlink != 1:
        raise UploadError(f"{label} must be user-owned with one link")
    if metadata.st_size <= 0:
        raise UploadError(f"{label} must not be empty")
    if private and stat.S_IMODE(metadata.st_mode) & 0o077:
        raise UploadError(f"{label} must not grant group/world permissions")
    return candidate, metadata


def validate_rom_name(path: Path) -> tuple[str, str]:
    name = path.name
    if name in ("", ".", "..") or name.startswith("."):
        raise UploadError("ROM filename must be visible and non-empty")
    if len(name.encode("utf-8")) > 240:
        raise UploadError("ROM filename is longer than 240 UTF-8 bytes")
    if any(ord(character) < 32 or ord(character) == 127 for character in name):
        raise UploadError("ROM filename contains a control character")
    try:
        system = SYSTEM_BY_SUFFIX[path.suffix.lower()]
    except KeyError as error:
        raise UploadError("ROM extension must be .nes, .gb, .gbc, .gba or .nds") from error
    return name, system


def hash_open_file(path: Path) -> tuple[str, os.stat_result]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise UploadError(f"cannot open ROM safely: {path}") from error
    digest = hashlib.sha256()
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise UploadError("ROM changed identity while opening")
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest(), metadata


def validate_rom(path: Path) -> tuple[Path, str, str, str, os.stat_result]:
    candidate, before = local_regular_file(path, "ROM", private=False)
    name, system = validate_rom_name(candidate)
    if before.st_size > MAX_ROM_BYTES:
        raise UploadError("ROM exceeds the 4 GiB transfer bound")
    digest, opened = hash_open_file(candidate)
    if (before.st_dev, before.st_ino, before.st_size) != (
        opened.st_dev,
        opened.st_ino,
        opened.st_size,
    ):
        raise UploadError("ROM changed identity during local hashing")
    return candidate, name, system, digest, opened


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
        raise UploadError(f"cannot start {label}") from error
    if result.returncode != 0:
        detail = next(
            (line.strip() for line in reversed(result.stderr.splitlines()) if line.strip()),
            "no diagnostic",
        )
        raise UploadError(f"{label} failed ({result.returncode}): {detail[:300]}")
    return result


def prepare_cache_root() -> None:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    metadata = os.lstat(CACHE_ROOT)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise UploadError(f"unsafe cache directory: {CACHE_ROOT}")


def scan_pinned_host_key(host: str, port: int, known_hosts: Path) -> None:
    arguments = [SSH_KEYSCAN, "-T", "5", "-t", "ed25519"]
    lookup = host
    if port != 22:
        arguments.extend(("-p", str(port)))
        lookup = f"[{host}]:{port}"
    arguments.append(host)
    result = checked_capture(arguments, "ED25519 host-key scan")
    lines = [line for line in result.stdout.splitlines() if line and not line.startswith("#")]
    if len(lines) != 1:
        raise UploadError("host-key scan did not return exactly one ED25519 key")
    fields = lines[0].split()
    if len(fields) != 3 or fields[1] != "ssh-ed25519":
        raise UploadError("host-key scan returned an unexpected key format")
    descriptor = os.open(known_hosts, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(lines[0] + "\n")
    fingerprint = checked_capture(
        [SSH_KEYGEN, "-lf", str(known_hosts), "-E", "sha256"],
        "host-key fingerprint verification",
    )
    fingerprint_lines = [line for line in fingerprint.stdout.splitlines() if line.strip()]
    if len(fingerprint_lines) != 1:
        raise UploadError("temporary known_hosts contains more than one key")
    fingerprint_fields = fingerprint_lines[0].split()
    if (
        len(fingerprint_fields) < 4
        or fingerprint_fields[1] != EXPECTED_HOST_KEY_FINGERPRINT
        or fingerprint_fields[-1] != "(ED25519)"
    ):
        raise UploadError("R46H ED25519 host-key fingerprint mismatch")
    checked_capture(
        [SSH_KEYGEN, "-F", lookup, "-f", str(known_hosts)],
        "host-key address binding verification",
    )


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
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=4",
        "-o",
        "LogLevel=ERROR",
        "-o",
        f"Port={port}",
    ]


def remote_command(script: str, arguments: list[str]) -> str:
    words = ["/bin/bash", "-c", script, "--", *arguments]
    return " ".join(shlex.quote(word) for word in words)


def run_remote(
    host: str,
    options: list[str],
    script: str,
    arguments: list[str],
    label: str,
) -> subprocess.CompletedProcess[str]:
    return checked_capture(
        [SSH, *options, "-T", f"ark@{host}", remote_command(script, arguments)],
        label,
    )


def cleanup_candidate(host: str, options: list[str], directory: str, candidate: str) -> bool:
    try:
        run_remote(
            host,
            options,
            CLEANUP_SCRIPT,
            [directory, candidate],
            "remote temporary-file cleanup",
        )
    except UploadError:
        return False
    return True


def upload(
    host: str,
    port: int,
    identity: Path,
    rom: Path,
    name: str,
    system: str,
    digest: str,
    metadata: os.stat_result,
    known_hosts: Path,
) -> None:
    options = ssh_options(identity, known_hosts, port)
    directory = f"/roms/{system}"
    final = f"{directory}/{name}"
    candidate = f"{directory}/.r46h-upload-{uuid.uuid4().hex}"
    preflight = run_remote(
        host,
        options,
        PRECHECK_SCRIPT,
        [directory, final, candidate, EXPECTED_RELEASE],
        "remote preflight",
    )
    if "R46H_ROM_UPLOAD_PREFLIGHT result=pass" not in preflight.stdout.splitlines():
        raise UploadError("remote preflight marker is missing")

    cleanup_needed = True
    try:
        try:
            copied = subprocess.run(
                [SCP, *options, str(rom), f"ark@{host}:{candidate}"],
                check=False,
                env=safe_environment(),
            )
        except OSError as error:
            raise UploadError("cannot start scp") from error
        if copied.returncode != 0:
            raise UploadError(f"scp failed ({copied.returncode})")

        after_digest, after = hash_open_file(rom)
        if (
            after_digest != digest
            or (after.st_dev, after.st_ino, after.st_size)
            != (metadata.st_dev, metadata.st_ino, metadata.st_size)
        ):
            raise UploadError("ROM changed during upload")

        marker = (
            f"R46H_ROM_UPLOAD result=pass system={system} "
            f"bytes={metadata.st_size} sha256={digest}"
        )
        published = run_remote(
            host,
            options,
            PUBLISH_SCRIPT,
            [
                directory,
                final,
                candidate,
                digest,
                str(metadata.st_size),
                EXPECTED_RELEASE,
                system,
            ],
            "remote hash verification and atomic publish",
        )
        if marker not in published.stdout.splitlines():
            raise UploadError("remote publish marker is missing")
        cleanup_needed = False
    finally:
        if cleanup_needed and not cleanup_candidate(host, options, directory, candidate):
            print(
                f"WARNING: verify and remove only this remote temporary file: {candidate}",
                file=sys.stderr,
            )

    print(f"PASS: {rom} -> ark@{host}:{final}")
    print(f"SHA256={digest}")
    print(f"BYTES={metadata.st_size}")


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        host = validate_host(arguments.host)
        port = validate_port(arguments.port)
        identity, _ = local_regular_file(arguments.identity, "private key", private=True)
        rom, name, system, digest, metadata = validate_rom(arguments.rom)
        prepare_cache_root()
        with tempfile.TemporaryDirectory(prefix="r46h-rom-upload.", dir=CACHE_ROOT) as directory:
            known_hosts = Path(directory) / "known_hosts"
            scan_pinned_host_key(host, port, known_hosts)
            upload(
                host,
                port,
                identity,
                rom,
                name,
                system,
                digest,
                metadata,
                known_hosts,
            )
    except UploadError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("ERROR: interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
