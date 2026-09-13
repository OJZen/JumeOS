#!/usr/bin/env python3
"""Validate and atomically publish the R46H Debian 13 p2 MVP artifact."""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
from typing import Any
import uuid


OUTPUT_NAME = "r46h-debian13-p2-mvp-v0.1"
ARTIFACT_ID = "debian13-p2-mvp-v0.1"
IMAGE_NAME = "r46h-debian13-p2-mvp-v0.1.ext4"
IMAGE_SIZE = 10_716_877_312
FS_BLOCK_SIZE = 4096
FS_BLOCK_COUNT = 2_616_425
FS_TAIL_SIZE = 512
FS_UUID = "d3130001-46a4-4d56-9001-000000000001"
FS_LABEL = "R46H_DEB13"
KERNEL_RELEASE = "6.12.99-r46h-mainline-v0.8-bootloader-handoff"
KERNEL_BUNDLE_SHA256 = "8c7282a07bdec52b753a8af27d15c6bbc8b71b34d017c3d78a2273fba6cfd09e"
KERNEL_BUNDLE_NAME = "r46h-mainline-test-v0.8-bootloader-handoff.tar.gz"
BASE_IMAGE = "debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd"
APT_SNAPSHOT = "20260713T000000Z"
SOURCE_DATE_EPOCH = "1786060800"
PROFILE_ID = "hl-r46h-v22-g92-v1"
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
KEY_RE = re.compile(r"^[A-Za-z0-9_]+$")
STAGE_RE = re.compile(r"^\.r46h-debian13-p2-mvp-v0\.1\.tmp\.[A-Za-z0-9]+$")

REQUIRED_INPUTS = {
    "APT-INRELEASE-SHA256SUMS",
    "BUILD-INFO",
    "DEBUGFS-SMOKE.txt",
    "DUMPE2FS.txt",
    "E2FSCK.txt",
    "EXT4-VERIFIED.sha256",
    "KERNEL-BUNDLE-VERIFY.txt",
    "KERNEL-BUNDLE.sha256",
    "PACKAGES.tsv",
    "PROBE-FILE.txt",
    "PROBE-LDD.txt",
    "ROOTFS-FILES.sha256",
    "ROOTFS-TREE.tsv",
    "SOURCE-SHA256SUMS",
    "SSHD-EFFECTIVE.txt",
    "SYSTEMD-VERIFY.txt",
    IMAGE_NAME,
}


class PackageError(RuntimeError):
    pass


def reject_json_constant(value: str) -> None:
    raise PackageError(f"non-finite JSON value: {value}")


def reject_duplicate_keys(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise PackageError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_regular(path: Path, label: str) -> os.stat_result:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise PackageError(f"missing {label}: {path}") from exc
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink() or metadata.st_nlink != 1:
        raise PackageError(f"unsafe {label}: {path}")
    return metadata


def require_ext4_superblock(path: Path) -> None:
    with path.open("rb", buffering=0) as handle:
        handle.seek(1024)
        superblock = handle.read(1024)
    if len(superblock) != 1024:
        raise PackageError("truncated ext4 superblock")

    blocks_lo = struct.unpack_from("<I", superblock, 0x04)[0]
    log_block_size = struct.unpack_from("<I", superblock, 0x18)[0]
    magic = struct.unpack_from("<H", superblock, 0x38)[0]
    state = struct.unpack_from("<H", superblock, 0x3A)[0]
    blocks_hi = struct.unpack_from("<I", superblock, 0x150)[0]
    block_count = blocks_lo | (blocks_hi << 32)
    block_size = 1024 << log_block_size if log_block_size < 32 else 0
    filesystem_uuid = str(uuid.UUID(bytes=superblock[0x68:0x78]))
    try:
        volume_label = superblock[0x78:0x88].split(b"\0", 1)[0].decode("ascii")
    except UnicodeDecodeError as exc:
        raise PackageError("invalid ext4 volume label encoding") from exc

    if magic != 0xEF53:
        raise PackageError("ext4 superblock magic mismatch")
    if block_count != FS_BLOCK_COUNT or block_size != FS_BLOCK_SIZE:
        raise PackageError("ext4 superblock geometry mismatch")
    if state != 0x0001:
        raise PackageError("ext4 filesystem is not marked clean")
    if filesystem_uuid != FS_UUID or volume_label != FS_LABEL:
        raise PackageError("ext4 superblock identity mismatch")


def parse_build_info(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line or "=" not in line:
            raise PackageError(f"invalid BUILD-INFO line {line_number}")
        key, value = line.split("=", 1)
        if KEY_RE.fullmatch(key) is None or not value or key in values:
            raise PackageError(f"invalid BUILD-INFO key on line {line_number}")
        values[key] = value
    return values


def require_exact_build_info(values: dict[str, str]) -> str:
    expected = {
        "artifact_id": ARTIFACT_ID,
        "distribution": "Debian GNU/Linux 13 (trixie)",
        "architecture": "arm64",
        "image_name": IMAGE_NAME,
        "image_size": str(IMAGE_SIZE),
        "filesystem": "ext4",
        "filesystem_block_size": str(FS_BLOCK_SIZE),
        "filesystem_block_count": str(FS_BLOCK_COUNT),
        "filesystem_tail_zero_bytes": str(FS_TAIL_SIZE),
        "filesystem_uuid": FS_UUID,
        "filesystem_label": FS_LABEL,
        "root_partuuid": "c9f931c9-02",
        "kernel_release": KERNEL_RELEASE,
        "kernel_bundle_sha256": KERNEL_BUNDLE_SHA256,
        "build_inputs_git_dirty": "false",
        "source_snapshot_method": "git-archive-exact-commit",
        "base_image": BASE_IMAGE,
        "apt_snapshot": APT_SNAPSHOT,
        "source_date_epoch": SOURCE_DATE_EPOCH,
    }
    dynamic_keys = {
        "image_sha256",
        "runtime_image_id",
        "source_git_commit",
        "source_archive_sha256",
        "docker_context",
        "docker_client_version",
        "docker_server_version",
    }
    if set(values) != set(expected) | dynamic_keys:
        raise PackageError("BUILD-INFO key set mismatch")
    for key, expected_value in expected.items():
        if values.get(key) != expected_value:
            raise PackageError(f"BUILD-INFO mismatch for {key}")
    for key in (
        "image_sha256",
        "source_archive_sha256",
    ):
        if SHA_RE.fullmatch(values.get(key, "")) is None:
            raise PackageError(f"invalid BUILD-INFO hash: {key}")
    if re.fullmatch(r"[0-9a-f]{40}", values.get("source_git_commit", "")) is None:
        raise PackageError("invalid source Git commit")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", values.get("runtime_image_id", "")) is None:
        raise PackageError("invalid runtime image ID")
    if re.fullmatch(r"[A-Za-z0-9._-]+", values.get("docker_context", "")) is None:
        raise PackageError("invalid Docker context")
    for key in ("docker_client_version", "docker_server_version"):
        if re.fullmatch(r"[0-9A-Za-z._+-]+", values.get(key, "")) is None:
            raise PackageError(f"invalid Docker version: {key}")
    return values["image_sha256"]


def require_build_evidence(stage_dir: Path) -> None:
    expected_bundle = f"{KERNEL_BUNDLE_SHA256}  {KERNEL_BUNDLE_NAME}\n"
    if (stage_dir / "KERNEL-BUNDLE.sha256").read_text(encoding="utf-8") != expected_bundle:
        raise PackageError("kernel bundle identity evidence mismatch")

    dumpe2fs = (stage_dir / "DUMPE2FS.txt").read_text(encoding="utf-8", errors="replace")
    required_ext4 = {
        f"Filesystem UUID:          {FS_UUID}",
        f"Filesystem volume name:   {FS_LABEL}",
        f"Block count:              {FS_BLOCK_COUNT}",
        f"Block size:               {FS_BLOCK_SIZE}",
        "Filesystem state:         clean",
    }
    if not all(line in dumpe2fs for line in required_ext4):
        raise PackageError("ext4 geometry evidence mismatch")
    if "R46H_E2FSCK_RESULT=pass" not in (
        stage_dir / "E2FSCK.txt"
    ).read_text(encoding="utf-8", errors="replace").splitlines():
        raise PackageError("offline e2fsck evidence is not a PASS")
    if "R46H_SYSTEMD_VERIFY_RESULT=pass" not in (
        stage_dir / "SYSTEMD-VERIFY.txt"
    ).read_text(encoding="utf-8", errors="replace").splitlines():
        raise PackageError("systemd verification evidence is not a PASS")

    inrelease_lines = (
        stage_dir / "APT-INRELEASE-SHA256SUMS"
    ).read_text(encoding="utf-8").splitlines()
    if len(inrelease_lines) != 3:
        raise PackageError("unexpected APT InRelease evidence count")
    inrelease_paths: set[str] = set()
    for line in inrelease_lines:
        match = re.fullmatch(r"[0-9a-f]{64}  (/var/lib/apt/lists/\S+_InRelease)", line)
        if match is None or match.group(1) in inrelease_paths:
            raise PackageError("invalid APT InRelease checksum evidence")
        inrelease_paths.add(match.group(1))

    probe_file = (stage_dir / "PROBE-FILE.txt").read_text(encoding="utf-8", errors="replace")
    probe_ldd = (stage_dir / "PROBE-LDD.txt").read_text(encoding="utf-8", errors="replace")
    if "ELF 64-bit" not in probe_file or "ARM aarch64" not in probe_file:
        raise PackageError("GPU probe architecture evidence mismatch")
    if re.search(r"not found|libMali", probe_ldd, re.IGNORECASE):
        raise PackageError("GPU probe dependency evidence mismatch")

    sshd_effective = set(
        (stage_dir / "SSHD-EFFECTIVE.txt").read_text(encoding="utf-8").splitlines()
    )
    required_sshd = {
        "permitrootlogin no",
        "passwordauthentication no",
        "kbdinteractiveauthentication no",
        "x11forwarding no",
        "allowusers ark",
    }
    if not required_sshd.issubset(sshd_effective):
        raise PackageError("effective OpenSSH policy evidence mismatch")

    rootfs_tree = (stage_dir / "ROOTFS-TREE.tsv").read_text(
        encoding="utf-8", errors="surrogateescape"
    )
    if "\t./.dockerenv\t" in rootfs_tree or "\t./run/.containerenv\t" in rootfs_tree:
        raise PackageError("container runtime marker leaked into hardware rootfs")


def load_profile(path: Path) -> None:
    require_regular(path, "card profile")
    try:
        profile = json.loads(
            path.read_bytes(),
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PackageError("invalid card profile") from exc
    if not isinstance(profile, dict) or profile.get("format_version") != 1:
        raise PackageError("unsupported card profile")
    if profile.get("profile_id") != PROFILE_ID:
        raise PackageError("card profile identity mismatch")
    card = profile.get("card")
    if not isinstance(card, dict):
        raise PackageError("card profile is missing card geometry")
    root = card.get("root")
    if not isinstance(root, dict):
        raise PackageError("card profile is missing root geometry")
    expected_root = {
        "number": 2,
        "offset": 134_217_728,
        "size": IMAGE_SIZE,
        "partuuid": "c9f931c9-02",
    }
    if root != expected_root:
        raise PackageError("card profile root geometry mismatch")


def rename_noreplace(parent_fd: int, source_name: str, destination_name: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    destination = os.fsencode(destination_name)
    if hasattr(libc, "renameatx_np"):
        call = libc.renameatx_np
        call.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        call.restype = ctypes.c_int
        result = call(parent_fd, source, parent_fd, destination, 0x00000004)
    elif hasattr(libc, "renameat2"):
        call = libc.renameat2
        call.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        call.restype = ctypes.c_int
        result = call(parent_fd, source, parent_fd, destination, 1)
    else:
        raise PackageError("platform lacks atomic no-replace rename support")
    if result != 0:
        error = ctypes.get_errno()
        if error in {errno.EEXIST, errno.ENOTEMPTY}:
            raise PackageError(f"output already exists: {destination_name}")
        raise OSError(error, os.strerror(error))


def validate_and_publish(args: argparse.Namespace) -> Path:
    repo_root = Path(args.repo_root).resolve(strict=True)
    output_root = Path(args.output_root).resolve(strict=True)
    stage_dir = Path(args.stage_dir).resolve(strict=True)
    profile_path = Path(args.card_profile).resolve(strict=True)
    if output_root != repo_root / "mainline/out":
        raise PackageError("output root is outside the fixed repository location")
    if stage_dir.parent != output_root or STAGE_RE.fullmatch(stage_dir.name) is None:
        raise PackageError("unsafe staging directory")
    if stage_dir.is_symlink() or not stage_dir.is_dir():
        raise PackageError("staging directory is not a real directory")
    final_dir = output_root / OUTPUT_NAME
    if final_dir.exists() or final_dir.is_symlink():
        raise PackageError(f"output already exists: {final_dir}")

    names = {entry.name for entry in stage_dir.iterdir()}
    if names != REQUIRED_INPUTS:
        raise PackageError(f"unexpected staging file set: {sorted(names ^ REQUIRED_INPUTS)}")
    for name in sorted(names):
        require_regular(stage_dir / name, name)

    load_profile(profile_path)
    build_info = parse_build_info(stage_dir / "BUILD-INFO")
    expected_image_sha = require_exact_build_info(build_info)
    require_build_evidence(stage_dir)
    image = stage_dir / IMAGE_NAME
    metadata = require_regular(image, "ext4 image")
    if metadata.st_size != IMAGE_SIZE:
        raise PackageError("ext4 image size mismatch")
    require_ext4_superblock(image)
    with image.open("rb", buffering=0) as handle:
        handle.seek(-FS_TAIL_SIZE, os.SEEK_END)
        if handle.read(FS_TAIL_SIZE) != b"\0" * FS_TAIL_SIZE:
            raise PackageError("p2 tail is not zero-filled")
    actual_image_sha = sha_file(image)
    if actual_image_sha != expected_image_sha:
        raise PackageError("ext4 image SHA-256 mismatch")
    if (stage_dir / "EXT4-VERIFIED.sha256").read_text(encoding="utf-8") != (
        f"{actual_image_sha}  {IMAGE_NAME}\n"
    ):
        raise PackageError("post-verification ext4 hash evidence mismatch")

    packages = (stage_dir / "PACKAGES.tsv").read_text(encoding="utf-8")
    for package in (
        "firmware-realtek",
        "libgl1-mesa-dri",
        "libnss-systemd",
        "libpam-systemd",
        "linux-sysctl-defaults",
        "netbase",
        "openssh-server",
        "systemd-sysv",
        "systemd-timesyncd",
    ):
        if re.search(rf"^{re.escape(package)}(?:\t|:)", packages, re.MULTILINE) is None:
            raise PackageError(f"required package absent: {package}")
    if "libMali" in packages:
        raise PackageError("forbidden libMali package evidence")
    if "Type: regular" not in (stage_dir / "DEBUGFS-SMOKE.txt").read_text(
        encoding="utf-8", errors="replace"
    ):
        raise PackageError("debugfs did not prove the smoke tool")

    digest_lines: list[str] = []
    for entry in sorted(stage_dir.iterdir(), key=lambda item: item.name):
        require_regular(entry, f"published input {entry.name}")
        digest = actual_image_sha if entry.name == IMAGE_NAME else sha_file(entry)
        digest_lines.append(f"{digest}  {entry.name}\n")
    (stage_dir / "SHA256SUMS").write_text("".join(digest_lines), encoding="utf-8")
    (stage_dir / "SHA256SUMS").chmod(0o644)
    names = {entry.name for entry in stage_dir.iterdir()}
    if names != REQUIRED_INPUTS | {"SHA256SUMS"}:
        raise PackageError("final artifact file set mismatch")

    output_fd = os.open(output_root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        rename_noreplace(output_fd, stage_dir.name, final_dir.name)
    finally:
        os.close(output_fd)

    if stage_dir.exists() or not final_dir.is_dir() or (final_dir / IMAGE_NAME).stat().st_ino != metadata.st_ino:
        raise PackageError("published directory is not the validated staging object")
    print("PASS: Debian 13 p2 MVP artifact validated and atomically published.")
    print(f"OUTPUT_DIR={final_dir}")
    print(f"IMAGE_SHA256={actual_image_sha}")
    return final_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage-dir", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--card-profile", required=True)
    return parser.parse_args()


def main() -> int:
    try:
        validate_and_publish(parse_args())
    except (PackageError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
