#!/usr/bin/env python3
"""Build and validate the host-only R46H first-version release source set."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
from typing import Any


REPO = Path(__file__).resolve().parents[2]
MAINLINE = REPO / "mainline"
OUT_ROOT = MAINLINE / "out"
CACHE_ROOT = OUT_ROOT / ".cache/r46h-first-version-release"
RELEASE_ROOT = OUT_ROOT / "r46h-first-version-release/builds"

ARTIFACT_ID = "r46h-first-version-release-v0.1"
PROFILE_ID = "hl-r46h-v22-g92-62534975488-v1"
SOURCE_DATE_EPOCH = 1_787_616_000
SECTOR_SIZE = 512
WHOLE_SIZE = 62_534_975_488

PREFIX_NAME = "00-prefix-g92-mbr.bin"
P1_NAME = "01-boot-p1.img"
P2_NAME = "02-debian13-root-p2.img"
P3_NAME = "03-easyroms-p3.img"

PREFIX_SIZE = 16_777_216
PREFIX_SHA256 = "3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3"
P1_SIZE = 117_440_512
P1_BASE_SHA256 = "78d238eb6da8562f8d30ee2fcbea376c0abd24f0b335fa2b3c950eec5826d171"
P2_SIZE = 10_716_877_312
P2_SHA256 = "ee7d402c06a750081b4c588c5162cca44d0e07fa4b544d5a59bef7629722aeca"
P3_SIZE = 51_683_880_448
P3_SHA256 = "fe0ee7764f2e2e1f4b8451183f8cadc26e3a876847eb1bfa0569198438501fac"

P1_OFFSET = PREFIX_SIZE
P2_OFFSET = P1_OFFSET + P1_SIZE
P3_OFFSET = P2_OFFSET + P2_SIZE

P1_BASE_RELATIVE = (
    "mainline/out/r46h-card-agent-sessions/"
    "session-20260824T025608Z-4440-215c307f-a2aa-4ed4-b421-56d10d495f4f/"
    "p1-v015-reinsert-20260824.img"
)
P1_AUDIT_RELATIVE = (
    "mainline/out/r46h-card-agent-sessions/"
    "session-20260824T025608Z-4440-215c307f-a2aa-4ed4-b421-56d10d495f4f/"
    "PREWRITE-AUDIT.json"
)
P1_AUDIT_SHA256 = "43233526fef56711a781a604f7c0c04bc24013971099f1ac28c7116216d6169f"
PREFIX_RELATIVE = "mainline/out/r46h-fast-card-62534975488-v1/00-prefix-g92-mbr.bin"
P2_RELATIVE = (
    "mainline/out/r46h-debian13-p2-gaming-v0.5/"
    "r46h-debian13-p2-gaming-v0.5.ext4"
)
P2_LABEL = "v0.5 p2"
P2_BUILD_INFO_RELATIVE = "mainline/out/r46h-debian13-p2-gaming-v0.5/BUILD-INFO"
P2_BUILD_INFO_SHA256 = "26e75ff265a6c53006859e6188fe04b2b149fd78839d1839844138ebe5ee1052"
EXPECTED_P2_BUILD_INFO = {
    "artifact_id": "debian13-p2-gaming-v0.5",
    "image_size": str(P2_SIZE),
    "image_sha256": P2_SHA256,
    "filesystem_uuid": "d3130005-46a4-4d56-9001-000000000005",
    "filesystem_label": "R46H_GAMING_V05",
    "root_partuuid": "c9f931c9-02",
    "kernel_release": "6.12.99-r46h-mainline-v0.15-gaming-product",
    "retroarch_config_sha256": (
        "99a45beb148e58e40983773b4f5e26d9fb5d7e1bbbf6a7e714a5c352e43c0dba"
    ),
    "source_git_commit": "44c1b0293061d03805c204c3b383ebb8ca8cc017",
    "build_inputs_git_dirty": "false",
}
P3_RELATIVE = "mainline/out/r46h-fast-card-62534975488-v1/03-easyroms-p3.img"
P3_BUILD_STATUS_RELATIVE = (
    "mainline/out/r46h-p3-recovery-images/"
    "r46h-easyroms-p3-62534975488-v1/BUILD-STATUS.json"
)
P3_BUILD_STATUS_SHA256 = "05f706354bf46c9ad5237815f40d0b9155b8b103b6ab8ad9e3cfc1a81fe3ef08"
V17_GENERATION_RELATIVE = (
    "mainline/out/r46h-v17-boot-promotion/builds/"
    "build-622cf60feab7-c2eea1243359"
)
V17_ARCHIVE_RELATIVE = (
    f"{V17_GENERATION_RELATIVE}/r46h-v17-boot-promotion-v0.1.tar.gz"
)
V17_ARCHIVE_SIZE = 29_463
V17_ARCHIVE_SHA256 = "c2eea1243359c06bbb9463b114b37eb52b78f0d10e01960a69b72ecc30e2ce61"
V17_BUILD_RECEIPT_RELATIVE = f"{V17_GENERATION_RELATIVE}/BUILD-RECEIPT.json"
V17_BUILD_RECEIPT_SHA256 = "c35b86b5eaec0941e46496adb2ef9ce2d246adbe577339229f0aee16d92903e1"

V17_ROOT = "r46h-v17-boot-promotion-v0.1"
V17_BOOT_NAME = "boot.ini.v0.17-power-settle"
V17_BOOT_SIZE = 1_417
V17_BOOT_SHA256 = "96300e2e74fa3ea00da28d81c80c7fa3e327bd4784af6ddc766817b36ad33778"
V17_DTB_NAME = "rk3326-r46h-mainline-v0.17-power-settle.dtb"
V17_DTB_SIZE = 49_561
V17_DTB_SHA256 = "116942e7bc8691bbf6bf185dd3cbe306de2d33be8dad79a027249f9f5234b796"
V17_ARCHIVE_MEMBERS = {
    V17_ROOT,
    f"{V17_ROOT}/PAYLOAD-INFO.json",
    f"{V17_ROOT}/PAYLOAD.COMPLETE",
    f"{V17_ROOT}/SHA256SUMS",
    f"{V17_ROOT}/fallback-modules.sh",
    f"{V17_ROOT}/files",
    f"{V17_ROOT}/files/{V17_BOOT_NAME}",
    f"{V17_ROOT}/files/{V17_DTB_NAME}",
    f"{V17_ROOT}/install.sh",
    f"{V17_ROOT}/storage-health.sh",
    f"{V17_ROOT}/transaction.sh",
}

PROFILE_RELATIVE = "mainline/deploy/profiles/hl-r46h-v22-g92-62534975488-v1.json"
DOCKERFILE_RELATIVE = "mainline/p1-candidate/Dockerfile"
DOCKERFILE_SHA256 = "529800294bedb9acd5a42681dc15879e00351c00c786abab016e78da12a3cb5d"
DOCKER_CONTEXT = "desktop-linux"
DOCKER_IMAGE = "arkos4clone/r46h-p1-builder:trixie-arm64"
DOCKER_IMAGE_ID = "sha256:fdadd0c517a338a4a776d3588307472d00ec5ed7904f0aec215fb60b05d0dbb0"
FSCK_MSDOS = Path("/sbin/fsck_msdos")
FSCK_MSDOS_TARGET = Path(
    "/System/Library/Filesystems/msdos.fs/Contents/Resources/fsck_msdos"
)

README_RELATIVE = "mainline/first-version-release/README.md"
BUILDER_RELATIVE = "mainline/scripts/build-r46h-first-version-release.py"
TEST_RELATIVE = "mainline/tests/test-r46h-first-version-release.py"
V17_BOOT_SOURCE_RELATIVE = (
    "mainline/gaming-product-v17-boot-promotion/boot.ini.v0.17-power-settle"
)
SOURCE_PATHS = (
    README_RELATIVE,
    BUILDER_RELATIVE,
    TEST_RELATIVE,
    PROFILE_RELATIVE,
    DOCKERFILE_RELATIVE,
    V17_BOOT_SOURCE_RELATIVE,
)

P1_PRESERVED_ANCHORS: dict[str, tuple[int, str]] = {
    "boot.ini.v0.8-bootloader-handoff": (
        1_427,
        "cead3fbee0d5c42fddcd6f6d83839b82af791e1abf1dd0252d9850fb47dd33fb",
    ),
    "Image.mainline-v0.8-bootloader-handoff.gz": (
        14_920_864,
        "d7c7796c097fbe692412fb63d19c1f97c4b21f55ae2c3b1e8df324a739f166fa",
    ),
    "rk3326-r46h-mainline-v0.8-bootloader-handoff.dtb": (
        49_481,
        "7259bac7bdd063fbaed987a0d5d2bf7066e02beaacc4440849b93d5f048e3dbc",
    ),
    "boot.ini.v0.10-adc-full-range": (
        1_408,
        "915039bf17dea6aa2ba42701195510c346c70c8c81117151e7d153073fa1ceab",
    ),
    "Image.mainline-v0.10-adc-full-range.gz": (
        14_921_256,
        "736549a919eee0342a2bae961a85b59337ad8de3c901c2e5f193aa15fdead954",
    ),
    "rk3326-r46h-mainline-v0.10-adc-full-range.dtb": (
        49_481,
        "04868feae2678cbee5073f93250dafb0219e560b0f1131526ac89930a8791cee",
    ),
    "boot.ini.v0.15-gaming-product": (
        1_403,
        "f41ab69f17cd22fb22446e390c46325d4e536cf8dee1bd9ab85682297dca1ac8",
    ),
    "Image.mainline-v0.15-gaming-product.gz": (
        14_925_282,
        "9a4f58ed03aab19d5472c5ff41f99383dee90c653dadebcee360f2323dc653bf",
    ),
    "rk3326-r46h-mainline-v0.15-gaming-product.dtb": (
        49_518,
        "4d6d4ebad3b98600b6e9a38df4ca82230335558497a9e15dd0e81ca60e304b61",
    ),
}
P1_BASE_NON_SPOTLIGHT_FILE_COUNT = 169
MINIMUM_P1_FREE_BYTES = 1024 * 1024

ASSET_MANIFEST_KEYS = (
    "format_version",
    "artifact_id",
    "profile_id",
    "whole_size",
    "sector_size",
    "prefix_name",
    "prefix_offset",
    "prefix_size",
    "prefix_sha256",
    "boot_name",
    "boot_offset",
    "boot_size",
    "boot_sha256",
    "root_name",
    "root_offset",
    "root_size",
    "root_sha256",
    "easyroms_name",
    "easyroms_offset",
    "easyroms_size",
    "easyroms_sha256",
    "p1_base_sha256",
    "p1_normalization",
    "active_boot_sha256",
    "v17_dtb_sha256",
    "p1_prewrite_audit_sha256",
    "p2_build_info_sha256",
    "p3_build_status_sha256",
    "v17_build_receipt_sha256",
    "source_git_commit",
    "source_git_tree",
    "source_manifest_sha256",
    "evidence_level",
    "second_card_slot",
    "a2_media",
    "full_card_materialized",
    "media_write_performed",
    "physical_devices_accessed",
    "block_devices_opened",
)

EXPECTED_GENERATION_FILES = {
    PREFIX_NAME,
    P1_NAME,
    P2_NAME,
    P3_NAME,
    "ASSET-MANIFEST",
    "BUILD-COMPLETE",
    "BUILD-RECEIPT.json",
    "SHA256SUMS",
    "SOURCE-MANIFEST.json",
    "p1-receipt/7zz-after.txt",
    "p1-receipt/7zz-before.txt",
    "p1-receipt/DIFF.json",
    "p1-receipt/DIRECTORIES-AFTER.json",
    "p1-receipt/DIRECTORIES-BEFORE.json",
    "p1-receipt/FILES-AFTER.json",
    "p1-receipt/FILES-BEFORE.json",
    "p1-receipt/fsck.fat.txt",
    "p1-receipt/fsck_msdos.txt",
    "p1-receipt/mdir.txt",
    "p1-receipt/mtools.txt",
    "upstream/p1-PREWRITE-AUDIT.json",
    "upstream/p2-BUILD-INFO",
    "upstream/p3-BUILD-STATUS.json",
    "upstream/profile.json",
    "upstream/v17-BUILD-RECEIPT.json",
}
EXPECTED_GENERATION_DIRECTORIES = {"p1-receipt", "upstream"}
SAFE_OUTPUT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
SHA256_RE = re.compile(r"[0-9a-f]{64}")


class BuildError(RuntimeError):
    pass


@dataclass(frozen=True)
class InputFile:
    path: Path
    size: int
    sha256: str
    identity: tuple[int, ...]


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def stable_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def require_regular(path: Path, label: str, expected_size: int | None = None) -> os.stat_result:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise BuildError(f"unsafe {label}: {path}")
    if expected_size is not None and metadata.st_size != expected_size:
        raise BuildError(f"{label} size mismatch: {metadata.st_size}")
    return metadata


def require_directory(path: Path, label: str) -> os.stat_result:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise BuildError(f"unsafe {label}: {path}")
    return metadata


def require_system_tool(path: Path, target: Path, label: str) -> Path:
    named = path.lstat()
    if not stat.S_ISLNK(named.st_mode) or Path(os.readlink(path)) != target:
        raise BuildError(f"unexpected fixed {label} link")
    resolved = path.resolve(strict=True)
    if resolved != target:
        raise BuildError(f"unexpected fixed {label} target")
    metadata = resolved.lstat()
    mode = stat.S_IMODE(metadata.st_mode)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or mode & 0o022
        or not mode & 0o111
    ):
        raise BuildError(f"unsafe fixed {label} target")
    return resolved


def write_new(path: Path, payload: bytes, mode: int = 0o400) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        mode,
    )
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise BuildError(f"short write: {path}")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    path.chmod(mode)


def git_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") and key not in {"BASH_ENV", "CDPATH", "ENV"}
    }
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_NO_REPLACE_OBJECTS": "1",
            "LC_ALL": "C",
        }
    )
    return environment


def git_bytes(arguments: list[str]) -> bytes:
    result = subprocess.run(
        ["/usr/bin/git", "--no-replace-objects", "-C", str(REPO), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=git_environment(),
    )
    if result.returncode != 0:
        detail = result.stderr.decode(errors="replace").strip()
        raise BuildError(f"git {' '.join(arguments)} failed: {detail}")
    return result.stdout


def capture_clean_source() -> tuple[str, str, bytes, dict[str, bytes]]:
    status = git_bytes(
        ["status", "--porcelain=v1", "--untracked-files=all", "--", *SOURCE_PATHS]
    )
    if status:
        raise BuildError("first-version release source scope is not committed and clean")
    commit = git_bytes(["rev-parse", "--verify", "HEAD^{commit}"]).decode().strip()
    tree = git_bytes(["rev-parse", "--verify", "HEAD^{tree}"]).decode().strip()
    captured: dict[str, bytes] = {}
    entries: list[dict[str, object]] = []
    for relative in SOURCE_PATHS:
        live = REPO / relative
        require_regular(live, f"source {relative}")
        listing = git_bytes(["ls-tree", commit, "--", relative]).decode().strip()
        fields = listing.split(None, 3)
        blob = git_bytes(["cat-file", "blob", f"{commit}:{relative}"])
        if (
            len(fields) != 4
            or fields[1] != "blob"
            or fields[3] != relative
            or live.read_bytes() != blob
        ):
            raise BuildError(f"source is not one unchanged committed blob: {relative}")
        captured[relative] = blob
        entries.append(
            {
                "git_mode": fields[0],
                "path": relative,
                "sha256": sha256_bytes(blob),
                "size": len(blob),
            }
        )
    manifest = canonical_json(
        {
            "file_count": len(entries),
            "files": entries,
            "format_version": 1,
            "git_commit": commit,
            "git_tree": tree,
        }
    )
    return commit, tree, manifest, captured


def validate_source_manifest(payload: bytes) -> dict[str, Any]:
    try:
        parsed = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError("invalid source manifest JSON") from exc
    if not isinstance(parsed, dict) or parsed.get("format_version") != 1:
        raise BuildError("source manifest structure mismatch")
    commit = parsed.get("git_commit")
    tree = parsed.get("git_tree")
    files = parsed.get("files")
    if (
        not isinstance(commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", commit) is None
        or not isinstance(tree, str)
        or re.fullmatch(r"[0-9a-f]{40}", tree) is None
        or not isinstance(files, list)
        or parsed.get("file_count") != len(files)
    ):
        raise BuildError("source manifest identity mismatch")
    if git_bytes(["rev-parse", "--verify", f"{commit}^{{tree}}"]).decode().strip() != tree:
        raise BuildError("source manifest Git tree mismatch")
    observed_paths: list[str] = []
    for entry in files:
        if not isinstance(entry, dict):
            raise BuildError("invalid source manifest entry")
        relative = entry.get("path")
        if not isinstance(relative, str) or relative not in SOURCE_PATHS:
            raise BuildError("source manifest path mismatch")
        blob = git_bytes(["cat-file", "blob", f"{commit}:{relative}"])
        listing = git_bytes(["ls-tree", commit, "--", relative]).decode().strip()
        fields = listing.split(None, 3)
        expected = {
            "git_mode": fields[0] if len(fields) == 4 else "",
            "path": relative,
            "sha256": sha256_bytes(blob),
            "size": len(blob),
        }
        if entry != expected:
            raise BuildError(f"source manifest entry mismatch: {relative}")
        observed_paths.append(relative)
    if tuple(observed_paths) != SOURCE_PATHS:
        raise BuildError("source manifest path order or set mismatch")
    return parsed


def require_out_parent(path: Path) -> Path:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    path.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise BuildError("output parent must not be a symlink")
    resolved = path.resolve(strict=True)
    out = OUT_ROOT.resolve(strict=True)
    if resolved == out or out not in resolved.parents:
        raise BuildError("output parent must stay below mainline/out")
    metadata = require_directory(resolved, "output parent")
    if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o022:
        raise BuildError("output parent must be user-owned and not group/world writable")
    return resolved


def require_out_input(relative: str, size: int, digest: str, label: str) -> InputFile:
    named = REPO / relative
    metadata = require_regular(named, label, size)
    path = named.resolve(strict=True)
    out = OUT_ROOT.resolve(strict=True)
    if out not in path.parents or str(path).startswith("/dev/"):
        raise BuildError(f"{label} must be a retained regular file below mainline/out")
    if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o022:
        raise BuildError(f"unsafe ownership or mode for {label}")
    actual = sha256_file(path)
    if actual != digest:
        raise BuildError(f"{label} SHA-256 mismatch")
    return InputFile(path, size, digest, stable_identity(metadata))


def require_out_input_without_hash(relative: str, size: int, label: str) -> InputFile:
    named = REPO / relative
    metadata = require_regular(named, label, size)
    path = named.resolve(strict=True)
    out = OUT_ROOT.resolve(strict=True)
    if out not in path.parents or str(path).startswith("/dev/"):
        raise BuildError(f"{label} must be a retained regular file below mainline/out")
    if metadata.st_uid != os.geteuid() or stat.S_IMODE(metadata.st_mode) & 0o022:
        raise BuildError(f"unsafe ownership or mode for {label}")
    return InputFile(path, size, "", stable_identity(metadata))


def require_out_receipt(relative: str, digest: str, label: str) -> InputFile:
    named = REPO / relative
    metadata = require_regular(named, label)
    return require_out_input(relative, metadata.st_size, digest, label)


def recheck_identity(source: InputFile, label: str) -> None:
    if stable_identity(require_regular(source.path, label, source.size)) != source.identity:
        raise BuildError(f"{label} changed while building")


def parse_kv(payload: bytes, separator: str, label: str) -> dict[str, str]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise BuildError(f"{label} is not UTF-8") from exc
    result: dict[str, str] = {}
    for line in lines:
        if not line or separator not in line:
            raise BuildError(f"malformed {label}")
        key, value = line.split(separator, 1)
        if re.fullmatch(r"[a-z][a-z0-9_]*", key) is None or not value or key in result:
            raise BuildError(f"invalid {label} field")
        result[key] = value
    return result


def validate_profile(payload: bytes) -> dict[str, Any]:
    try:
        profile = json.loads(payload)
        card = profile["card"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise BuildError("invalid card profile") from exc
    expected = {
        "whole_size": WHOLE_SIZE,
        "sector_size": SECTOR_SIZE,
        "g92_prefix_size": PREFIX_SIZE,
        "g92_prefix_sha256": PREFIX_SHA256,
    }
    if profile.get("format_version") != 1 or profile.get("profile_id") != PROFILE_ID:
        raise BuildError("card profile identity mismatch")
    if any(card.get(key) != value for key, value in expected.items()):
        raise BuildError("card profile top-level geometry mismatch")
    partitions = (
        (card.get("boot"), 1, P1_OFFSET, P1_SIZE),
        (card.get("root"), 2, P2_OFFSET, P2_SIZE),
        (card.get("easyroms"), 3, P3_OFFSET, P3_SIZE),
    )
    for value, number, offset, size in partitions:
        if not isinstance(value, dict) or (
            value.get("number"), value.get("offset"), value.get("size")
        ) != (number, offset, size):
            raise BuildError(f"card profile p{number} geometry mismatch")
    if P3_OFFSET + P3_SIZE != WHOLE_SIZE:
        raise BuildError("release geometry does not cover the exact card")
    return profile


def validate_upstream_receipts(
    p1_audit: bytes,
    p2_info: bytes,
    p3_status_raw: bytes,
    v17_receipt_raw: bytes,
    profile_raw: bytes,
) -> None:
    if sha256_bytes(p1_audit) != P1_AUDIT_SHA256:
        raise BuildError("p1 audit receipt mismatch")
    if sha256_bytes(p2_info) != P2_BUILD_INFO_SHA256:
        raise BuildError("p2 build receipt mismatch")
    if sha256_bytes(p3_status_raw) != P3_BUILD_STATUS_SHA256:
        raise BuildError("p3 build receipt mismatch")
    if sha256_bytes(v17_receipt_raw) != V17_BUILD_RECEIPT_SHA256:
        raise BuildError("v0.17 build receipt mismatch")
    validate_profile(profile_raw)

    try:
        audit = json.loads(p1_audit)
        p3 = json.loads(p3_status_raw)
        v17 = json.loads(v17_receipt_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError("invalid upstream JSON receipt") from exc
    p2 = parse_kv(p2_info, "=", "p2 BUILD-INFO")
    if (
        audit.get("state") != "AUDIT_COMPLETE"
        or audit.get("profile_id") != PROFILE_ID
        or audit.get("p1_clone_size") != P1_SIZE
        or audit.get("p1_clone_sha256") != P1_BASE_SHA256
        or audit.get("p1_fsck_msdos_n") != "clean"
        or audit.get("p1_non_spotlight_manifest", {}).get("result") != "pass"
        or audit.get("p1_non_spotlight_manifest", {}).get("current_files")
        != P1_BASE_NON_SPOTLIGHT_FILE_COUNT
    ):
        raise BuildError("p1 audit contract mismatch")
    if any(p2.get(key) != value for key, value in EXPECTED_P2_BUILD_INFO.items()):
        raise BuildError("p2 BUILD-INFO contract mismatch")
    if (
        p3.get("state") != "BUILD_COMPLETE"
        or p3.get("artifact_id") != "r46h-easyroms-p3-62534975488-v1"
        or p3.get("profile_id") != PROFILE_ID
        or p3.get("image_size") != P3_SIZE
        or p3.get("image_sha256") != P3_SHA256
        or p3.get("allocation_bitmap_exact") is not True
        or p3.get("raw_verification_twice_passed") is not True
        or p3.get("post_normalize_fsck_read_only_passed") is not True
        or p3.get("physical_devices_accessed") != 0
        or p3.get("block_devices_opened") != 0
    ):
        raise BuildError("p3 BUILD-STATUS contract mismatch")
    if (
        v17.get("archive_size") != V17_ARCHIVE_SIZE
        or v17.get("archive_sha256") != V17_ARCHIVE_SHA256
        or v17.get("candidate_dtb_size") != V17_DTB_SIZE
        or v17.get("candidate_dtb_sha256") != V17_DTB_SHA256
        or v17.get("source_git_commit")
        != "622cf60feab7e2f935c485316cd1cbc3f7be757c"
        or v17.get("second_card_slot") != "unavailable"
    ):
        raise BuildError("v0.17 BUILD-RECEIPT contract mismatch")


def load_v17_payload(archive_path: Path) -> tuple[bytes, bytes]:
    require_regular(archive_path, "v0.17 promotion archive", V17_ARCHIVE_SIZE)
    if sha256_file(archive_path) != V17_ARCHIVE_SHA256:
        raise BuildError("v0.17 promotion archive SHA-256 mismatch")
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)) or set(names) != V17_ARCHIVE_MEMBERS:
            raise BuildError("v0.17 promotion archive member set mismatch")
        directories = {V17_ROOT, f"{V17_ROOT}/files"}
        contents: dict[str, bytes] = {}
        for member in members:
            if member.name in directories:
                if not member.isdir():
                    raise BuildError("v0.17 archive directory type mismatch")
                continue
            if not member.isfile() or member.issym() or member.islnk():
                raise BuildError("unsafe v0.17 archive member type")
            stream = archive.extractfile(member)
            if stream is None:
                raise BuildError("cannot read v0.17 archive member")
            contents[member.name.removeprefix(f"{V17_ROOT}/")] = stream.read()
    sums_raw = contents["SHA256SUMS"]
    sums: dict[str, str] = {}
    for line in sums_raw.decode("utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9./_-]+)", line)
        if match is None or match.group(2) in sums:
            raise BuildError("v0.17 payload checksum manifest is malformed")
        sums[match.group(2)] = match.group(1)
    expected_names = set(contents) - {"SHA256SUMS", "PAYLOAD.COMPLETE"}
    if set(sums) != expected_names:
        raise BuildError("v0.17 payload checksum file set mismatch")
    for name, digest in sums.items():
        if sha256_bytes(contents[name]) != digest:
            raise BuildError(f"v0.17 payload checksum mismatch: {name}")
    complete = contents["PAYLOAD.COMPLETE"].decode("ascii")
    if complete != f"sha256sums_sha256={sha256_bytes(sums_raw)}\n":
        raise BuildError("v0.17 payload completion marker mismatch")
    boot = contents[f"files/{V17_BOOT_NAME}"]
    dtb = contents[f"files/{V17_DTB_NAME}"]
    if len(boot) != V17_BOOT_SIZE or sha256_bytes(boot) != V17_BOOT_SHA256:
        raise BuildError("v0.17 boot payload identity mismatch")
    if len(dtb) != V17_DTB_SIZE or sha256_bytes(dtb) != V17_DTB_SHA256:
        raise BuildError("v0.17 DTB payload identity mismatch")
    if b"saveenv" in boot:
        raise BuildError("v0.17 boot payload must not use saveenv")
    return boot, dtb


def run_checked(
    command: list[str],
    *,
    cwd: Path | None = None,
    log: Path | None = None,
) -> str:
    environment = {**os.environ, "LC_ALL": "C", "LANG": "C", "TZ": "UTC"}
    result = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if log is not None:
        write_new(log, result.stdout.encode("utf-8"))
    if result.returncode != 0:
        raise BuildError(
            f"command failed ({result.returncode}): {' '.join(command[:4])}"
        )
    return result.stdout


def clone_file(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise BuildError(f"clone destination already exists: {destination}")
    run_checked(["/bin/cp", "-c", str(source), str(destination)])
    metadata = require_regular(destination, "APFS clone")
    if metadata.st_size != source.stat().st_size:
        raise BuildError("APFS clone size mismatch")
    destination.chmod(0o400)


def find_7zip() -> str:
    seven_zip = shutil.which("7zz") or shutil.which("7z")
    if seven_zip is None:
        raise BuildError("7zz is required for offline FAT validation")
    return seven_zip


def extract_fat(image: Path, destination: Path, log: Path) -> None:
    destination.mkdir(mode=0o700)
    work = image.parent.parent
    relative_image = image.relative_to(work)
    relative_destination = destination.relative_to(work)
    run_checked(
        [
            find_7zip(),
            "x",
            "-y",
            "-bb1",
            f"-o{relative_destination}",
            str(relative_image),
        ],
        cwd=work,
        log=log,
    )


def validate_fat_path(relative: str) -> None:
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise BuildError(f"unsafe FAT path: {relative}")
    for part in path.parts:
        if part.startswith("._") or part == "__MACOSX" or "\x00" in part:
            raise BuildError(f"AppleDouble or unsafe FAT path: {relative}")


def scan_tree(root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    files: dict[str, dict[str, Any]] = {}
    directories: list[str] = []
    folded: dict[str, str] = {}
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirnames.sort()
        filenames.sort()
        for name in dirnames:
            path = current_path / name
            metadata = path.lstat()
            if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
                raise BuildError(f"unsafe extracted FAT directory: {path}")
            relative = path.relative_to(root).as_posix()
            validate_fat_path(relative)
            directories.append(relative)
        for name in filenames:
            path = current_path / name
            metadata = path.lstat()
            if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
                raise BuildError(f"unsafe extracted FAT file: {path}")
            relative = path.relative_to(root).as_posix()
            validate_fat_path(relative)
            key = relative.casefold()
            if key in folded:
                raise BuildError(f"case-colliding FAT paths: {folded[key]} and {relative}")
            folded[key] = relative
            files[relative] = {
                "sha256": sha256_file(path),
                "size": metadata.st_size,
            }
    directories.sort()
    return files, directories


def identity(size: int, digest: str) -> dict[str, Any]:
    return {"sha256": digest, "size": size}


def validate_exact_p1_diff(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    before_directories: list[str],
    after_directories: list[str],
) -> dict[str, Any]:
    spotlight = lambda path: path == ".Spotlight-V100" or path.startswith(
        ".Spotlight-V100/"
    )
    spotlight_files = sorted(path for path in before if spotlight(path))
    spotlight_directories = sorted(path for path in before_directories if spotlight(path))
    if not spotlight_files or ".Spotlight-V100" not in spotlight_directories:
        raise BuildError("p1 baseline Spotlight tree is missing")
    if any(
        path == ".fseventsd" or path.startswith(".fseventsd/")
        for path in (*before, *before_directories)
    ):
        raise BuildError("unmodelled p1 .fseventsd baseline")
    if sum(not spotlight(path) for path in before) != P1_BASE_NON_SPOTLIGHT_FILE_COUNT:
        raise BuildError("p1 baseline non-Spotlight file count mismatch")
    for path, (size, digest) in P1_PRESERVED_ANCHORS.items():
        if before.get(path) != identity(size, digest):
            raise BuildError(f"p1 fallback baseline mismatch: {path}")
        if after.get(path) != identity(size, digest):
            raise BuildError(f"p1 fallback changed: {path}")
    if before.get("boot.ini") != identity(*P1_PRESERVED_ANCHORS["boot.ini.v0.15-gaming-product"]):
        raise BuildError("p1 active boot is not exact v0.15")

    before_paths = set(before)
    after_paths = set(after)
    removed = sorted(before_paths - after_paths)
    added = sorted(after_paths - before_paths)
    changed = sorted(
        path for path in before_paths & after_paths if before[path] != after[path]
    )
    if removed != spotlight_files:
        raise BuildError("p1 removed file set exceeds Spotlight normalization")
    if added != sorted((V17_BOOT_NAME, V17_DTB_NAME)):
        raise BuildError(f"unexpected p1 added file set: {added}")
    if changed != ["boot.ini"]:
        raise BuildError(f"unexpected p1 changed file set: {changed}")
    if after.get("boot.ini") != identity(V17_BOOT_SIZE, V17_BOOT_SHA256):
        raise BuildError("p1 active boot is not exact v0.17")
    if after.get(V17_BOOT_NAME) != identity(V17_BOOT_SIZE, V17_BOOT_SHA256):
        raise BuildError("p1 versioned v0.17 boot mismatch")
    if after.get(V17_DTB_NAME) != identity(V17_DTB_SIZE, V17_DTB_SHA256):
        raise BuildError("p1 v0.17 DTB mismatch")
    if any("v0.16-disable-secondary" in path for path in after):
        raise BuildError("clean release p1 unexpectedly contains inert v0.16 files")
    expected_directories = sorted(
        path for path in before_directories if path not in spotlight_directories
    )
    if after_directories != expected_directories:
        raise BuildError("p1 directory changes exceed Spotlight normalization")
    if any(spotlight(path) for path in after) or any(
        path.startswith("._") or "/._" in path for path in after
    ):
        raise BuildError("p1 contains forbidden host metadata after normalization")
    return {
        "added": added,
        "changed": changed,
        "preserved_non_spotlight_files": P1_BASE_NON_SPOTLIGHT_FILE_COUNT - 1,
        "removed_spotlight_directories": len(spotlight_directories),
        "removed_spotlight_files": len(spotlight_files),
    }


def docker_command() -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise BuildError("Docker is required for direct-image mtools")
    return docker


def require_toolchain() -> dict[str, str]:
    docker = docker_command()
    context = run_checked([docker, "context", "show"]).strip()
    if context != DOCKER_CONTEXT:
        raise BuildError("unexpected Docker context")
    image = run_checked(
        [docker, "--context", DOCKER_CONTEXT, "image", "inspect", DOCKER_IMAGE_ID, "--format", "{{.Id}} {{.Architecture}}"]
    ).strip()
    if image != f"{DOCKER_IMAGE_ID} arm64":
        raise BuildError("p1 builder image identity or architecture mismatch")
    client = run_checked(
        [docker, "--context", DOCKER_CONTEXT, "version", "--format", "{{.Client.Version}}"]
    ).strip()
    server = run_checked(
        [docker, "--context", DOCKER_CONTEXT, "info", "--format", "{{.ServerVersion}}"]
    ).strip()
    seven_output = run_checked([find_7zip(), "i"])
    version = next(
        (line.strip() for line in seven_output.splitlines() if line.strip().startswith("7-Zip")),
        "unknown",
    )
    return {
        "docker_client_version": client,
        "docker_image_id": DOCKER_IMAGE_ID,
        "docker_server_version": server,
        "seven_zip_version": version,
    }


def mutate_p1(work: Path, toolchain: dict[str, str]) -> None:
    del toolchain
    docker = docker_command()
    script = f"""set -euo pipefail
image=/work/stage/{P1_NAME}
mdeltree -i \"$image\" ::/.Spotlight-V100
mdel -i \"$image\" ::/boot.ini
mcopy -o -m -i \"$image\" /work/v17-boot.ini ::/boot.ini
mcopy -o -m -i \"$image\" /work/v17-boot.ini ::/{V17_BOOT_NAME}
mcopy -o -m -i \"$image\" /work/v17.dtb ::/{V17_DTB_NAME}
fsck.fat -n -v \"$image\" > /work/stage/p1-receipt/fsck.fat.txt
mdir -i \"$image\" -/ ::/ > /work/stage/p1-receipt/mdir.txt
"""
    command = [
        docker,
        "--context",
        DOCKER_CONTEXT,
        "run",
        "--rm",
        "--platform",
        "linux/arm64",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=16m",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--volume",
        f"{work}:/work:rw",
        "--entrypoint",
        "/bin/bash",
        DOCKER_IMAGE_ID,
        "-c",
        script,
    ]
    run_checked(command, log=work / "stage/p1-receipt/mtools.txt")


def parse_free_bytes(path: Path) -> int:
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"([0-9][0-9 ,.]*[0-9]|[0-9]) bytes free", text)
    if not matches:
        raise BuildError("mtools did not report p1 free space")
    free = int(re.sub(r"[^0-9]", "", matches[-1]))
    if free < MINIMUM_P1_FREE_BYTES:
        raise BuildError(f"p1 free space is too small: {free}")
    return free


def validate_mbr(path: Path) -> None:
    with path.open("rb") as handle:
        mbr = handle.read(512)
    if len(mbr) != 512 or mbr[510:512] != b"\x55\xaa":
        raise BuildError("g92 prefix MBR signature mismatch")
    expected = (
        (0x0B, P1_OFFSET // SECTOR_SIZE, P1_SIZE // SECTOR_SIZE),
        (0x83, P2_OFFSET // SECTOR_SIZE, P2_SIZE // SECTOR_SIZE),
        (0x07, P3_OFFSET // SECTOR_SIZE, P3_SIZE // SECTOR_SIZE),
        (0x00, 0, 0),
    )
    for index, values in enumerate(expected):
        entry = 446 + index * 16
        status_byte = mbr[entry]
        partition_type = mbr[entry + 4]
        start, sectors = struct.unpack_from("<II", mbr, entry + 8)
        if status_byte != 0 or (partition_type, start, sectors) != values:
            raise BuildError(f"g92 prefix MBR p{index + 1} geometry mismatch")


def render_asset_manifest(
    *,
    p1_sha256: str,
    source_commit: str,
    source_tree: str,
    source_manifest_sha256: str,
) -> bytes:
    if SHA256_RE.fullmatch(p1_sha256) is None:
        raise BuildError("invalid p1 release SHA-256")
    values = {
        "format_version": "2",
        "artifact_id": ARTIFACT_ID,
        "profile_id": PROFILE_ID,
        "whole_size": str(WHOLE_SIZE),
        "sector_size": str(SECTOR_SIZE),
        "prefix_name": PREFIX_NAME,
        "prefix_offset": "0",
        "prefix_size": str(PREFIX_SIZE),
        "prefix_sha256": PREFIX_SHA256,
        "boot_name": P1_NAME,
        "boot_offset": str(P1_OFFSET),
        "boot_size": str(P1_SIZE),
        "boot_sha256": p1_sha256,
        "root_name": P2_NAME,
        "root_offset": str(P2_OFFSET),
        "root_size": str(P2_SIZE),
        "root_sha256": P2_SHA256,
        "easyroms_name": P3_NAME,
        "easyroms_offset": str(P3_OFFSET),
        "easyroms_size": str(P3_SIZE),
        "easyroms_sha256": P3_SHA256,
        "p1_base_sha256": P1_BASE_SHA256,
        "p1_normalization": "remove-Spotlight-V100_replace-active-boot_add-v0.17",
        "active_boot_sha256": V17_BOOT_SHA256,
        "v17_dtb_sha256": V17_DTB_SHA256,
        "p1_prewrite_audit_sha256": P1_AUDIT_SHA256,
        "p2_build_info_sha256": P2_BUILD_INFO_SHA256,
        "p3_build_status_sha256": P3_BUILD_STATUS_SHA256,
        "v17_build_receipt_sha256": V17_BUILD_RECEIPT_SHA256,
        "source_git_commit": source_commit,
        "source_git_tree": source_tree,
        "source_manifest_sha256": source_manifest_sha256,
        "evidence_level": "host-artifact-only",
        "second_card_slot": "unavailable",
        "a2_media": "compatible-not-class-proven",
        "full_card_materialized": "false",
        "media_write_performed": "false",
        "physical_devices_accessed": "0",
        "block_devices_opened": "0",
    }
    if tuple(values) != ASSET_MANIFEST_KEYS:
        raise BuildError("internal ASSET-MANIFEST key order mismatch")
    return "".join(f"{key} {values[key]}\n" for key in ASSET_MANIFEST_KEYS).encode()


def parse_asset_manifest(payload: bytes) -> dict[str, str]:
    values = parse_kv(payload, " ", "ASSET-MANIFEST")
    if tuple(values) != ASSET_MANIFEST_KEYS:
        raise BuildError("ASSET-MANIFEST key order or set mismatch")
    return values


def generation_tree(root: Path) -> tuple[set[str], set[str]]:
    files: set[str] = set()
    directories: set[str] = set()
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirnames.sort()
        filenames.sort()
        for name in dirnames:
            path = current_path / name
            require_directory(path, "generation directory")
            directories.add(path.relative_to(root).as_posix())
        for name in filenames:
            path = current_path / name
            require_regular(path, "generation file")
            files.add(path.relative_to(root).as_posix())
    return files, directories


def render_sha256sums(root: Path, component_hashes: dict[str, str]) -> bytes:
    files, directories = generation_tree(root)
    if directories != EXPECTED_GENERATION_DIRECTORIES:
        raise BuildError("generation directory set mismatch before checksums")
    expected = EXPECTED_GENERATION_FILES - {"SHA256SUMS", "BUILD-COMPLETE"}
    if files != expected:
        raise BuildError(f"generation file set mismatch before checksums: {sorted(files ^ expected)}")
    lines: list[str] = []
    for relative in sorted(files):
        digest = component_hashes.get(relative) or sha256_file(root / relative)
        lines.append(f"{digest}  {relative}\n")
    return "".join(lines).encode()


def parse_sha256sums(payload: bytes) -> dict[str, str]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise BuildError("SHA256SUMS is not UTF-8") from exc
    result: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._/-]+)", line)
        if match is None or match.group(2) in result:
            raise BuildError("malformed generation SHA256SUMS")
        result[match.group(2)] = match.group(1)
    return result


def publish_noreplace(source: Path, destination: Path) -> None:
    libc_name = ctypes.util.find_library("c")
    if libc_name is None:
        raise BuildError("cannot resolve libc for atomic publication")
    libc = ctypes.CDLL(libc_name, use_errno=True)
    rename = getattr(libc, "renameatx_np", None)
    if rename is None:
        raise BuildError("renameatx_np is unavailable")
    rename.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    rename.restype = ctypes.c_int
    source_parent = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY)
    destination_parent = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        before = source.lstat()
        if rename(
            source_parent,
            os.fsencode(source.name),
            destination_parent,
            os.fsencode(destination.name),
            0x00000004,
        ) != 0:
            raise BuildError(f"atomic publication failed: errno={ctypes.get_errno()}")
        after = destination.lstat()
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise BuildError("published generation identity mismatch")
    finally:
        os.close(destination_parent)
        os.close(source_parent)


def build_release(output_parent: Path, output_name: str | None) -> Path:
    os.umask(0o077)
    source_commit, source_tree, source_manifest, captured = capture_clean_source()
    source_manifest_sha = sha256_bytes(source_manifest)
    toolchain = require_toolchain()
    profile_raw = captured[PROFILE_RELATIVE]
    if sha256_bytes(captured[DOCKERFILE_RELATIVE]) != DOCKERFILE_SHA256:
        raise BuildError("committed p1 Dockerfile mismatch")

    p1_base = require_out_input(P1_BASE_RELATIVE, P1_SIZE, P1_BASE_SHA256, "base p1")
    prefix = require_out_input(PREFIX_RELATIVE, PREFIX_SIZE, PREFIX_SHA256, "g92 prefix")
    p2 = require_out_input_without_hash(P2_RELATIVE, P2_SIZE, P2_LABEL)
    p3 = require_out_input_without_hash(P3_RELATIVE, P3_SIZE, "accepted p3")
    v17_archive = require_out_input(
        V17_ARCHIVE_RELATIVE,
        V17_ARCHIVE_SIZE,
        V17_ARCHIVE_SHA256,
        "v0.17 promotion archive",
    )
    small_sources = {
        "upstream/p1-PREWRITE-AUDIT.json": require_out_receipt(
            P1_AUDIT_RELATIVE,
            P1_AUDIT_SHA256,
            "p1 audit",
        ),
        "upstream/p2-BUILD-INFO": require_out_receipt(
            P2_BUILD_INFO_RELATIVE,
            P2_BUILD_INFO_SHA256,
            "p2 BUILD-INFO",
        ),
        "upstream/p3-BUILD-STATUS.json": require_out_receipt(
            P3_BUILD_STATUS_RELATIVE,
            P3_BUILD_STATUS_SHA256,
            "p3 BUILD-STATUS",
        ),
        "upstream/v17-BUILD-RECEIPT.json": require_out_receipt(
            V17_BUILD_RECEIPT_RELATIVE,
            V17_BUILD_RECEIPT_SHA256,
            "v0.17 BUILD-RECEIPT",
        ),
    }
    validate_upstream_receipts(
        small_sources["upstream/p1-PREWRITE-AUDIT.json"].path.read_bytes(),
        small_sources["upstream/p2-BUILD-INFO"].path.read_bytes(),
        small_sources["upstream/p3-BUILD-STATUS.json"].path.read_bytes(),
        small_sources["upstream/v17-BUILD-RECEIPT.json"].path.read_bytes(),
        profile_raw,
    )
    boot, dtb = load_v17_payload(v17_archive.path)
    if captured[V17_BOOT_SOURCE_RELATIVE] != boot:
        raise BuildError("committed v0.17 boot source differs from accepted archive")
    validate_mbr(prefix.path)

    output_parent = require_out_parent(output_parent)
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    require_out_parent(CACHE_ROOT)
    with tempfile.TemporaryDirectory(prefix=".build.", dir=CACHE_ROOT) as temporary:
        work = Path(temporary)
        work.chmod(0o700)
        stage = work / "stage"
        stage.mkdir(mode=0o700)
        receipt = stage / "p1-receipt"
        receipt.mkdir(mode=0o700)
        upstream = stage / "upstream"
        upstream.mkdir(mode=0o700)

        candidate = stage / P1_NAME
        clone_file(p1_base.path, candidate)
        before_tree = work / "before-tree"
        extract_fat(candidate, before_tree, receipt / "7zz-before.txt")
        before, before_directories = scan_tree(before_tree)

        boot_path = work / "v17-boot.ini"
        write_new(boot_path, boot, 0o600)
        os.utime(boot_path, (SOURCE_DATE_EPOCH, SOURCE_DATE_EPOCH), follow_symlinks=False)
        dtb_path = work / "v17.dtb"
        write_new(dtb_path, dtb, 0o600)
        os.utime(dtb_path, (SOURCE_DATE_EPOCH, SOURCE_DATE_EPOCH), follow_symlinks=False)
        candidate.chmod(0o600)
        mutate_p1(work, toolchain)
        candidate.chmod(0o400)
        free_bytes = parse_free_bytes(receipt / "mdir.txt")
        fsck_msdos = require_system_tool(
            FSCK_MSDOS, FSCK_MSDOS_TARGET, "fsck_msdos"
        )
        run_checked(
            [str(fsck_msdos), "-n", P1_NAME],
            cwd=stage,
            log=receipt / "fsck_msdos.txt",
        )

        after_tree = work / "after-tree"
        extract_fat(candidate, after_tree, receipt / "7zz-after.txt")
        after, after_directories = scan_tree(after_tree)
        diff = validate_exact_p1_diff(
            before,
            after,
            before_directories,
            after_directories,
        )
        write_new(receipt / "FILES-BEFORE.json", canonical_json(before))
        write_new(receipt / "FILES-AFTER.json", canonical_json(after))
        write_new(
            receipt / "DIRECTORIES-BEFORE.json", canonical_json(before_directories)
        )
        write_new(
            receipt / "DIRECTORIES-AFTER.json", canonical_json(after_directories)
        )
        write_new(receipt / "DIFF.json", canonical_json(diff))

        p1_sha = sha256_file(candidate)
        clone_file(prefix.path, stage / PREFIX_NAME)
        clone_file(p2.path, stage / P2_NAME)
        clone_file(p3.path, stage / P3_NAME)
        component_hashes = {
            PREFIX_NAME: sha256_file(stage / PREFIX_NAME),
            P1_NAME: p1_sha,
            P2_NAME: sha256_file(stage / P2_NAME),
            P3_NAME: sha256_file(stage / P3_NAME),
        }
        expected_components = {
            PREFIX_NAME: PREFIX_SHA256,
            P2_NAME: P2_SHA256,
            P3_NAME: P3_SHA256,
        }
        for name, expected in expected_components.items():
            if component_hashes[name] != expected:
                raise BuildError(f"release component SHA-256 mismatch: {name}")
        validate_mbr(stage / PREFIX_NAME)

        for destination, source in small_sources.items():
            write_new(stage / destination, source.path.read_bytes())
        write_new(upstream / "profile.json", profile_raw)
        write_new(stage / "SOURCE-MANIFEST.json", source_manifest)
        asset_manifest = render_asset_manifest(
            p1_sha256=p1_sha,
            source_commit=source_commit,
            source_tree=source_tree,
            source_manifest_sha256=source_manifest_sha,
        )
        write_new(stage / "ASSET-MANIFEST", asset_manifest)
        receipt_payload = canonical_json(
            {
                "apfs_clone_count": 4,
                "artifact_id": ARTIFACT_ID,
                "asset_manifest_sha256": sha256_bytes(asset_manifest),
                "block_devices_opened": 0,
                "docker_context": DOCKER_CONTEXT,
                "format_version": 1,
                "full_card_materialized": False,
                "media_write_performed": False,
                "network_during_p1_mutation": "none",
                "p1": {
                    "base_sha256": P1_BASE_SHA256,
                    "free_bytes": free_bytes,
                    "image_sha256": p1_sha,
                    "normalization": diff,
                },
                "physical_devices_accessed": 0,
                "profile_id": PROFILE_ID,
                "source_date_epoch": SOURCE_DATE_EPOCH,
                "source_git_commit": source_commit,
                "source_git_tree": source_tree,
                "source_manifest_sha256": source_manifest_sha,
                "toolchain": toolchain,
            }
        )
        write_new(stage / "BUILD-RECEIPT.json", receipt_payload)
        sums = render_sha256sums(stage, component_hashes)
        write_new(stage / "SHA256SUMS", sums)
        complete = canonical_json(
            {
                "asset_manifest_sha256": sha256_bytes(asset_manifest),
                "format_version": 1,
                "sha256sums_sha256": sha256_bytes(sums),
                "state": "BUILD_COMPLETE",
            }
        )
        write_new(stage / "BUILD-COMPLETE", complete)

        for source in (p1_base, prefix, p2, p3, v17_archive, *small_sources.values()):
            recheck_identity(source, source.path.name)
        source_commit_after = git_bytes(["rev-parse", "--verify", "HEAD^{commit}"]).decode().strip()
        status_after = git_bytes(
            ["status", "--porcelain=v1", "--untracked-files=all", "--", *SOURCE_PATHS]
        )
        if source_commit_after != source_commit or status_after:
            raise BuildError("release source changed while building")

        generation = output_name or (
            f"build-{source_commit[:12]}-{sha256_bytes(asset_manifest)[:12]}"
        )
        if SAFE_OUTPUT_NAME.fullmatch(generation) is None:
            raise BuildError("unsafe release generation name")
        destination = output_parent / generation
        if destination.exists() or destination.is_symlink():
            raise BuildError(f"release generation already exists: {destination}")
        publish_noreplace(stage, destination)

    print("PASS: host-only R46H first-version release source set built.")
    print("PHYSICAL_DEVICES_ACCESSED=0")
    print("BLOCK_DEVICES_OPENED=0")
    print("MEDIA_WRITE_PERFORMED=false")
    print("FULL_CARD_MATERIALIZED=false")
    print(f"P1_SHA256={p1_sha}")
    print(f"ASSET_MANIFEST_SHA256={sha256_bytes(asset_manifest)}")
    print(f"RELEASE_DIR={destination}")
    return destination


def validate_generation(generation: Path) -> None:
    os.umask(0o077)
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    require_out_parent(CACHE_ROOT)
    resolved = generation.resolve(strict=True)
    out = OUT_ROOT.resolve(strict=True)
    if out not in resolved.parents:
        raise BuildError("release generation must stay below mainline/out")
    require_directory(resolved, "release generation")
    files, directories = generation_tree(resolved)
    if files != EXPECTED_GENERATION_FILES or directories != EXPECTED_GENERATION_DIRECTORIES:
        raise BuildError("release generation file or directory set mismatch")

    sums_raw = (resolved / "SHA256SUMS").read_bytes()
    sums = parse_sha256sums(sums_raw)
    expected_sums = EXPECTED_GENERATION_FILES - {"SHA256SUMS", "BUILD-COMPLETE"}
    if set(sums) != expected_sums or list(sums) != sorted(sums):
        raise BuildError("generation SHA256SUMS path set or order mismatch")
    for relative, expected in sums.items():
        actual = sha256_file(resolved / relative)
        if actual != expected:
            raise BuildError(f"generation checksum mismatch: {relative}")

    try:
        complete = json.loads((resolved / "BUILD-COMPLETE").read_bytes())
        receipt = json.loads((resolved / "BUILD-RECEIPT.json").read_bytes())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError("invalid release completion or receipt JSON") from exc
    asset_raw = (resolved / "ASSET-MANIFEST").read_bytes()
    asset = parse_asset_manifest(asset_raw)
    source_raw = (resolved / "SOURCE-MANIFEST.json").read_bytes()
    source = validate_source_manifest(source_raw)
    expected_complete = {
        "asset_manifest_sha256": sha256_bytes(asset_raw),
        "format_version": 1,
        "sha256sums_sha256": sha256_bytes(sums_raw),
        "state": "BUILD_COMPLETE",
    }
    if complete != expected_complete:
        raise BuildError("release completion marker mismatch")
    if (
        asset.get("format_version") != "2"
        or asset.get("artifact_id") != ARTIFACT_ID
        or asset.get("profile_id") != PROFILE_ID
        or asset.get("whole_size") != str(WHOLE_SIZE)
        or asset.get("sector_size") != str(SECTOR_SIZE)
        or asset.get("source_git_commit") != source.get("git_commit")
        or asset.get("source_git_tree") != source.get("git_tree")
        or asset.get("source_manifest_sha256") != sha256_bytes(source_raw)
        or asset.get("evidence_level") != "host-artifact-only"
        or asset.get("media_write_performed") != "false"
        or asset.get("physical_devices_accessed") != "0"
        or asset.get("block_devices_opened") != "0"
        or asset.get("full_card_materialized") != "false"
        or asset.get("second_card_slot") != "unavailable"
        or asset.get("a2_media") != "compatible-not-class-proven"
    ):
        raise BuildError("release ASSET-MANIFEST contract mismatch")
    expected_assets = {
        PREFIX_NAME: (PREFIX_SIZE, PREFIX_SHA256, "prefix_size", "prefix_sha256"),
        P1_NAME: (P1_SIZE, asset["boot_sha256"], "boot_size", "boot_sha256"),
        P2_NAME: (P2_SIZE, P2_SHA256, "root_size", "root_sha256"),
        P3_NAME: (P3_SIZE, P3_SHA256, "easyroms_size", "easyroms_sha256"),
    }
    for name, (size, digest, size_key, digest_key) in expected_assets.items():
        if (
            (resolved / name).stat().st_size != size
            or sums.get(name) != digest
            or asset.get(size_key) != str(size)
            or asset.get(digest_key) != digest
        ):
            raise BuildError(f"release component contract mismatch: {name}")
    if (
        asset.get("prefix_name") != PREFIX_NAME
        or asset.get("boot_name") != P1_NAME
        or asset.get("root_name") != P2_NAME
        or asset.get("easyroms_name") != P3_NAME
        or asset.get("prefix_offset") != "0"
        or asset.get("boot_offset") != str(P1_OFFSET)
        or asset.get("root_offset") != str(P2_OFFSET)
        or asset.get("easyroms_offset") != str(P3_OFFSET)
        or asset.get("p1_base_sha256") != P1_BASE_SHA256
        or asset.get("p1_normalization")
        != "remove-Spotlight-V100_replace-active-boot_add-v0.17"
        or asset.get("active_boot_sha256") != V17_BOOT_SHA256
        or asset.get("v17_dtb_sha256") != V17_DTB_SHA256
        or asset.get("p1_prewrite_audit_sha256") != P1_AUDIT_SHA256
        or asset.get("p2_build_info_sha256") != P2_BUILD_INFO_SHA256
        or asset.get("p3_build_status_sha256") != P3_BUILD_STATUS_SHA256
        or asset.get("v17_build_receipt_sha256") != V17_BUILD_RECEIPT_SHA256
    ):
        raise BuildError("release geometry or upstream identity mismatch")
    validate_mbr(resolved / PREFIX_NAME)
    validate_upstream_receipts(
        (resolved / "upstream/p1-PREWRITE-AUDIT.json").read_bytes(),
        (resolved / "upstream/p2-BUILD-INFO").read_bytes(),
        (resolved / "upstream/p3-BUILD-STATUS.json").read_bytes(),
        (resolved / "upstream/v17-BUILD-RECEIPT.json").read_bytes(),
        (resolved / "upstream/profile.json").read_bytes(),
    )

    before = json.loads((resolved / "p1-receipt/FILES-BEFORE.json").read_bytes())
    after_receipt = json.loads((resolved / "p1-receipt/FILES-AFTER.json").read_bytes())
    before_directories = json.loads(
        (resolved / "p1-receipt/DIRECTORIES-BEFORE.json").read_bytes()
    )
    after_directories_receipt = json.loads(
        (resolved / "p1-receipt/DIRECTORIES-AFTER.json").read_bytes()
    )
    expected_diff = validate_exact_p1_diff(
        before,
        after_receipt,
        before_directories,
        after_directories_receipt,
    )
    if json.loads((resolved / "p1-receipt/DIFF.json").read_bytes()) != expected_diff:
        raise BuildError("p1 normalization receipt mismatch")
    toolchain = require_toolchain()
    del toolchain
    with tempfile.TemporaryDirectory(prefix=".validate.", dir=CACHE_ROOT) as temporary:
        work = Path(temporary)
        work.chmod(0o700)
        stage = work / "stage"
        stage.mkdir(mode=0o700)
        clone_file(resolved / P1_NAME, stage / P1_NAME)
        extracted = work / "after-tree"
        extract_fat(stage / P1_NAME, extracted, work / "7zz-after.txt")
        actual_after, actual_directories = scan_tree(extracted)
        if actual_after != after_receipt or actual_directories != after_directories_receipt:
            raise BuildError("live p1 file manifest differs from retained receipt")
        fsck_msdos = require_system_tool(
            FSCK_MSDOS, FSCK_MSDOS_TARGET, "fsck_msdos"
        )
        run_checked(
            [str(fsck_msdos), "-n", P1_NAME],
            cwd=stage,
            log=work / "fsck_msdos.txt",
        )
        docker = docker_command()
        run_checked(
            [
                docker,
                "--context",
                DOCKER_CONTEXT,
                "run",
                "--rm",
                "--platform",
                "linux/arm64",
                "--network",
                "none",
                "--read-only",
                "--volume",
                f"{work}:/work:ro",
                "--entrypoint",
                "/bin/bash",
                DOCKER_IMAGE_ID,
                "-c",
                f"fsck.fat -n -v /work/stage/{P1_NAME}",
            ],
            log=work / "fsck.fat.txt",
        )

    expected_receipt = {
        "artifact_id": ARTIFACT_ID,
        "asset_manifest_sha256": sha256_bytes(asset_raw),
        "block_devices_opened": 0,
        "docker_context": DOCKER_CONTEXT,
        "format_version": 1,
        "full_card_materialized": False,
        "media_write_performed": False,
        "network_during_p1_mutation": "none",
        "physical_devices_accessed": 0,
        "profile_id": PROFILE_ID,
        "source_date_epoch": SOURCE_DATE_EPOCH,
        "source_git_commit": source["git_commit"],
        "source_git_tree": source["git_tree"],
        "source_manifest_sha256": sha256_bytes(source_raw),
    }
    for key, value in expected_receipt.items():
        if receipt.get(key) != value:
            raise BuildError(f"BUILD-RECEIPT mismatch: {key}")
    if receipt.get("apfs_clone_count") != 4:
        raise BuildError("BUILD-RECEIPT APFS clone count mismatch")
    p1_receipt = receipt.get("p1")
    retained_free_bytes = parse_free_bytes(resolved / "p1-receipt/mdir.txt")
    if (
        not isinstance(p1_receipt, dict)
        or p1_receipt.get("base_sha256") != P1_BASE_SHA256
        or p1_receipt.get("image_sha256") != asset["boot_sha256"]
        or p1_receipt.get("normalization") != expected_diff
        or not isinstance(p1_receipt.get("free_bytes"), int)
        or p1_receipt["free_bytes"] != retained_free_bytes
    ):
        raise BuildError("BUILD-RECEIPT p1 contract mismatch")
    receipt_toolchain = receipt.get("toolchain")
    if (
        not isinstance(receipt_toolchain, dict)
        or receipt_toolchain.get("docker_image_id") != DOCKER_IMAGE_ID
    ):
        raise BuildError("BUILD-RECEIPT toolchain mismatch")

    print("PASS: R46H first-version release source set validated.")
    print("PHYSICAL_DEVICES_ACCESSED=0")
    print("BLOCK_DEVICES_OPENED=0")
    print("MEDIA_WRITE_PERFORMED=false")
    print(f"P1_SHA256={asset['boot_sha256']}")
    print(f"ASSET_MANIFEST_SHA256={sha256_bytes(asset_raw)}")
    print(f"RELEASE_DIR={resolved}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="build one host-only release generation")
    build.add_argument("--output-parent", type=Path, default=RELEASE_ROOT)
    build.add_argument("--output-name")
    validate = subparsers.add_parser("validate", help="independently validate a generation")
    validate.add_argument("generation", type=Path)
    return parser.parse_args()


def main() -> int:
    try:
        arguments = parse_args()
        if arguments.command == "build":
            build_release(arguments.output_parent, arguments.output_name)
        else:
            validate_generation(arguments.generation)
    except (BuildError, OSError, ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
