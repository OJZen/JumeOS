#!/usr/bin/env python3
"""Prepare the four pinned sources for the 62,534,975,488-byte R46H card."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile


SOURCE_SET = "mainline/out/r46h-full-card-sources/r46h-card-31719424000-postrepair-20260812"
P3_ARTIFACT = "mainline/out/r46h-p3-recovery-images/r46h-easyroms-p3-62534975488-v1"
OUTPUT = "mainline/out/r46h-fast-card-62534975488-v1"
SOURCE_SET_COMPLETE_SHA256 = "f784209bcf6366da2c277207e48377b32840f3f92a2503838a3e56d148189dc2"
SOURCE_SET_SUMS_SHA256 = "446b966e4e3a214247569327b42cd7931d2c36ca89691e7ce9e68658c19097e4"
OLD_PREFIX_SHA256 = "97ede10075b3257c638a04b3044c9dda2d8dd9adc6f6fee3be7b004a31fb135e"
NEW_PREFIX_SHA256 = "3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3"
BOOT_SHA256 = "88c6d614984791b891e63068ea687dabe28eb80c905a2aa9c6dd34409b24f86d"
ROOT_SHA256 = "dba5ff14364aa32b2d5930a055182a7f49c2bea0e2a0eb8cc76d1097b37c4c3e"
PREFIX_SIZE = 16_777_216
BOOT_SIZE = 117_440_512
ROOT_SIZE = 10_716_877_312
P3_SIZE = 51_683_880_448
P3_SECTORS = 100_945_079
P3_IMAGE = "easyroms-p3-62534975488-v1.img"


class PrepareError(RuntimeError):
    pass


def digest(path: Path, expected_size: int | None = None) -> str:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise PrepareError(f"unsafe source: {path}")
    if expected_size is not None and metadata.st_size != expected_size:
        raise PrepareError(f"source size mismatch: {path}")
    value = hashlib.sha256()
    with path.open("rb", buffering=0) as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def clone(source: Path, destination: Path) -> None:
    result = subprocess.run(
        ["/bin/cp", "-c", str(source), str(destination)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise PrepareError(f"APFS clone failed: {result.stdout.decode(errors='replace')}")
    destination.chmod(0o600)


def write(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        offset = 0
        while offset < len(data):
            written = os.write(descriptor, data[offset:])
            if written <= 0:
                raise PrepareError(f"short output write: {path}")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def derive_prefix(raw: bytes) -> bytes:
    if len(raw) != PREFIX_SIZE or raw[490:494] != bytes.fromhex("b7ec6d02"):
        raise PrepareError("unexpected old MBR p3 length field")
    result = bytearray(raw)
    result[490:494] = P3_SECTORS.to_bytes(4, "little")
    if sum(a != b for a, b in zip(raw, result)) != 3:
        raise PrepareError("unexpected MBR p3 length delta")
    return bytes(result)


def publish_noreplace(source: Path, destination: Path) -> None:
    libc_name = ctypes.util.find_library("c")
    if libc_name is None:
        raise PrepareError("cannot resolve libc")
    libc = ctypes.CDLL(libc_name, use_errno=True)
    function = getattr(libc, "renameatx_np", None)
    if function is None:
        raise PrepareError("renameatx_np is unavailable")
    function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    source_parent = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY)
    destination_parent = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        before = source.lstat()
        if function(
            source_parent,
            os.fsencode(source.name),
            destination_parent,
            os.fsencode(destination.name),
            0x00000004,
        ) != 0:
            raise PrepareError(f"atomic asset publication failed: errno={ctypes.get_errno()}")
        after = destination.lstat()
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise PrepareError("published asset directory identity mismatch")
    finally:
        os.close(destination_parent)
        os.close(source_parent)


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    repo = Path(__file__).resolve(strict=True).parents[2]
    source = repo / SOURCE_SET
    p3_artifact = repo / P3_ARTIFACT
    output = (args.output or repo / OUTPUT).resolve(strict=False)
    out_root = (repo / "mainline/out").resolve(strict=True)
    if output == out_root or out_root not in output.parents or output.exists() or output.is_symlink():
        raise PrepareError("unsafe or existing output directory")
    if digest(source / "SOURCE-SET-COMPLETE") != SOURCE_SET_COMPLETE_SHA256:
        raise PrepareError("source-set completion marker mismatch")
    if digest(source / "SHA256SUMS") != SOURCE_SET_SUMS_SHA256:
        raise PrepareError("source-set checksum manifest mismatch")
    old_prefix = source / "00-prefix-g92-mbr.bin"
    boot = source / "01-boot-p1.img"
    root = source / "02-debian13-root-p2.img"
    if digest(old_prefix, PREFIX_SIZE) != OLD_PREFIX_SHA256:
        raise PrepareError("old prefix mismatch")
    if digest(boot, BOOT_SIZE) != BOOT_SHA256 or digest(root, ROOT_SIZE) != ROOT_SHA256:
        raise PrepareError("BOOT or root source mismatch")
    status_raw = (p3_artifact / "BUILD-STATUS.json").read_bytes()
    status = json.loads(status_raw)
    p3_sha = status.get("image_sha256")
    p3 = p3_artifact / P3_IMAGE
    if (
        status.get("state") != "BUILD_COMPLETE"
        or status.get("artifact_id") != "r46h-easyroms-p3-62534975488-v1"
        or status.get("profile_id") != "hl-r46h-v22-g92-62534975488-v1"
        or status.get("image_size") != P3_SIZE
        or status.get("volume_guid") != "62534975-4880-4A4A-ACB7-625349754881"
        or status.get("allocation_bitmap_exact") is not True
        or status.get("raw_verification_twice_passed") is not True
        or status.get("post_normalize_fsck_read_only_passed") is not True
        or status.get("physical_devices_accessed") != 0
        or status.get("block_devices_opened") != 0
        or not isinstance(p3_sha, str)
        or len(p3_sha) != 64
        or digest(p3, P3_SIZE) != p3_sha
    ):
        raise PrepareError("p3 artifact binding mismatch")

    stage = Path(tempfile.mkdtemp(prefix=".r46h-fast-card-assets.", dir=output.parent))
    stage.chmod(0o700)
    published = False
    try:
        prefix_bytes = derive_prefix(old_prefix.read_bytes())
        prefix_path = stage / "00-prefix-g92-mbr.bin"
        write(prefix_path, prefix_bytes)
        if digest(prefix_path, PREFIX_SIZE) != NEW_PREFIX_SHA256:
            raise PrepareError("new prefix mismatch")
        clone(boot, stage / "01-boot-p1.img")
        clone(root, stage / "02-debian13-root-p2.img")
        clone(p3, stage / "03-easyroms-p3.img")
        if digest(stage / "01-boot-p1.img", BOOT_SIZE) != BOOT_SHA256:
            raise PrepareError("cloned BOOT mismatch")
        if digest(stage / "02-debian13-root-p2.img", ROOT_SIZE) != ROOT_SHA256:
            raise PrepareError("cloned root mismatch")
        if digest(stage / "03-easyroms-p3.img", P3_SIZE) != p3_sha:
            raise PrepareError("cloned p3 mismatch")
        manifest = (
            "format_version 1\n"
            "whole_size 62534975488\n"
            f"prefix_sha256 {NEW_PREFIX_SHA256}\n"
            f"boot_sha256 {BOOT_SHA256}\n"
            f"root_sha256 {ROOT_SHA256}\n"
            f"easyroms_sha256 {p3_sha}\n"
            f"p3_build_status_sha256 {hashlib.sha256(status_raw).hexdigest()}\n"
            f"source_set_complete_sha256 {SOURCE_SET_COMPLETE_SHA256}\n"
            f"source_set_sums_sha256 {SOURCE_SET_SUMS_SHA256}\n"
        ).encode()
        write(stage / "ASSET-MANIFEST", manifest)
        publish_noreplace(stage, output)
        published = True
        print("PASS: exact 62,534,975,488-byte card source set prepared.")
        print(f"EASYROMS_SHA256={p3_sha}")
        print(f"ASSET_MANIFEST_SHA256={hashlib.sha256(manifest).hexdigest()}")
        print(f"OUTPUT_DIR={output}")
        return 0
    finally:
        if not published and stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PrepareError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
