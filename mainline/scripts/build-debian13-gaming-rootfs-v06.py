#!/usr/bin/env python3
"""Build and validate the successor R46H Debian 13 gaming p2 v0.6 image."""

from __future__ import annotations

import argparse
import ctypes
import errno
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
OUTPUT_ROOT = REPO / "mainline/out"
CACHE_ROOT = OUTPUT_ROOT / ".cache/r46h-debian13-gaming-rootfs-v06"
OUTPUT_NAME = "r46h-debian13-p2-gaming-v0.6"
ARTIFACT_ID = "debian13-p2-gaming-v0.6"
IMAGE_NAME = f"{OUTPUT_NAME}.ext4"
OUTPUT_DIR = OUTPUT_ROOT / OUTPUT_NAME

IMAGE_SIZE = 10_716_877_312
FS_TAIL_SIZE = 512
BASE_FS_UUID = "d3130005-46a4-4d56-9001-000000000005"
BASE_FS_LABEL = "R46H_GAMING_V05"
FS_UUID = "d3130006-46a4-4d56-9001-000000000006"
FS_LABEL = "R46H_GAMING_V06"
SOURCE_DATE_EPOCH = "1787529600"
PROFILE_ID = "hl-r46h-v22-g92-v1"
KERNEL_RELEASE = "6.12.99-r46h-mainline-v0.15-gaming-product"

BASE_CONTAINER = (
    "arkos4clone/r46h-debian13-p2-mvp:v0.1@"
    "sha256:bd09bf6db6f1fb8f882621e98d70f01f976fd8dfba1bc897766afebd64cf51b9"
)
BASE_CONTAINER_ID = "sha256:bd09bf6db6f1fb8f882621e98d70f01f976fd8dfba1bc897766afebd64cf51b9"
BASE_IMAGE = (
    OUTPUT_ROOT
    / "r46h-debian13-p2-gaming-v0.5"
    / "r46h-debian13-p2-gaming-v0.5.ext4"
)
BASE_IMAGE_SHA256 = "ee7d402c06a750081b4c588c5162cca44d0e07fa4b544d5a59bef7629722aeca"
BASE_BUILD_INFO = OUTPUT_ROOT / "r46h-debian13-p2-gaming-v0.5/BUILD-INFO"
BASE_BUILD_INFO_SHA256 = "26e75ff265a6c53006859e6188fe04b2b149fd78839d1839844138ebe5ee1052"
BASE_CONSOLIDATED_RECEIPT_SHA256 = (
    "076dc3901e3b6f4bf7f875803aa643244083ce45e08b461a0057e50266aa09f5"
)
BASE_GAMING_RECEIPT_SHA256 = (
    "0a0675e82aa35fb22252de2d688fa280275e52634ef9a130c5e415ba2cc04666"
)

GAMING_PAYLOAD_ID = "r46h-gaming-mvp-v0.5"
GAMING_ARCHIVE_NAME = f"{GAMING_PAYLOAD_ID}.tar.gz"
GAMING_ARCHIVE = (
    OUTPUT_ROOT
    / "r46h-gaming-mvp-v0.5/builds/build-5a3a3000bfd1-22bbbe33f6d9"
    / GAMING_ARCHIVE_NAME
)
GAMING_ARCHIVE_SIZE = 263_536_270
GAMING_ARCHIVE_SHA256 = "22bbbe33f6d96b170aebb886c1aa40e2596073e2609b2bdfa93eeb1b42377e17"
GAMING_SOURCE_COMMIT = "5a3a3000bfd1b34669894776f61048037696b38e"
GAMING_PACKAGE_MANIFEST_SHA256 = (
    "c726b6cad27da02ab4f6215b35654319a143858b6bf6e1b641d7b720775ab8f7"
)
GAMING_PAYLOAD_SHA256SUMS_SHA256 = (
    "caf2ed188bfff6427483c4816e560cf1234dea9266d461d5faa0dfa0f27140ec"
)

ALSA_VENDOR_RULE_SHA256 = "78db137bced7b3e9ea57659d098f49ee8636e665bb856af929164cbf80b67880"
ALSA_OVERRIDE_RULE_SHA256 = "e17f53c8923c96e30d5d925f9d525235f2e2da8d084591e33993c2a05f0cb0e0"
BASE_FIRSTBOOT_SHA256 = "dd9bbbb0076de8cea73261ed278709fe2d7fd5451a5b32b5f401d6f9e051a708"
FINAL_FIRSTBOOT_SHA256 = "3c065d08ee2ee89d48fba0b4432662dd9d51e3e5d7a06212a854c758d55b504c"
BASE_ROOTFS_SMOKE_SHA256 = "2255b9d58e24408e5157c124d8828c84ff6f27f17133a407e8f8d33c26ac40a6"
FINAL_ROOTFS_SMOKE_SHA256 = "825e7a12667770f83d0e0ba79363a4d4b2ae6c5fab068aaa1eb4b5d7aa3034c7"

PROFILE = REPO / "mainline/deploy/profiles/hl-r46h-v22-g92-v1.json"
SOURCE_PATHS = (
    "mainline/rootfs-debian13-gaming-v06/README.md",
    "mainline/rootfs-debian13-gaming-v06/90-alsa-restore.rules",
    "mainline/rootfs-debian13-gaming-v06/image-in-container.sh",
    "mainline/scripts/build-debian13-gaming-rootfs-v06.py",
    "mainline/tests/test-debian13-gaming-rootfs-v06.py",
    "mainline/deploy/profiles/hl-r46h-v22-g92-v1.json",
)
VERSION_TEXT = "v0.6"
VERSION_TOKEN = "V06"
GAMING_PAYLOAD_VERSION_TEXT = "v0.5"
IMAGE_TOOL_RELATIVE = "mainline/rootfs-debian13-gaming-v06/image-in-container.sh"
BASE_IMAGE_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.5.ext4"
BASE_BUILD_INFO_RECEIPT_NAME = "r46h-debian13-p2-gaming-v0.5.BUILD-INFO"
DEBUGFS_EVIDENCE_NAME = "DEBUGFS-V06.txt"
INDEPENDENT_DEBUGFS_EVIDENCE_NAME = "INDEPENDENT-DEBUGFS-V06.txt"
ARTIFACT_STATUS = "host-only-not-authorized-for-media-write"
EXTRA_BUILD_ENVIRONMENT: dict[str, str] = {}
EXTRA_BUILD_INFO: dict[str, str] = {}
CONSOLIDATED_RECEIPT_EXTRA_MARKERS: tuple[str, ...] = ()

PAYLOAD_TOP_LEVEL = {
    "PACKAGES.tsv",
    "PAYLOAD-INFO.json",
    "PAYLOAD.COMPLETE",
    "SHA256SUMS",
    "debs",
    "files",
    "install.sh",
}
PAYLOAD_FILES = {
    "files/GAMING-PRODUCT.md",
    "files/fstab",
    "files/r46h-game-ui",
    "files/r46h-gaming-frontend-condition",
    "files/r46h-gaming-frontend.service",
    "files/r46h-gaming-input-ready",
    "files/r46h-gaming-input.service",
    "files/r46h-input-bridge",
    "files/r46h-nes-smoke.nes",
    "files/r46h-smoke-libretro.so",
    "files/r46h-storage-audit",
    "files/r46h-volume-keys",
    "files/r46h-volume-keys.service",
    "files/retroarch.cfg",
}
APPLY_EVIDENCE = {
    "APPLY-DEBUGFS.txt",
    "CONSOLIDATED-RECEIPT",
    DEBUGFS_EVIDENCE_NAME,
    "DUMPE2FS.txt",
    "E2FSCK-REPAIR.txt",
    "E2FSCK.txt",
    "EXT4-VERIFIED.sha256",
    "GAMING-PAYLOAD-VERIFY.txt",
    "GAMING-RECEIPT",
    "NORMALIZE-SUPER.txt",
    "SYSTEMD-VERIFY.txt",
    "TUNE2FS.txt",
    "UDEV-VERIFY.txt",
}
INDEPENDENT_EVIDENCE = {
    DEBUGFS_EVIDENCE_NAME: INDEPENDENT_DEBUGFS_EVIDENCE_NAME,
    "E2FSCK.txt": "INDEPENDENT-E2FSCK.txt",
    "EXT4-VERIFIED.sha256": "INDEPENDENT-EXT4-VERIFIED.sha256",
    "SYSTEMD-VERIFY.txt": "INDEPENDENT-SYSTEMD-VERIFY.txt",
    "UDEV-VERIFY.txt": "INDEPENDENT-UDEV-VERIFY.txt",
}
REQUIRED_STAGE_FILES = (
    APPLY_EVIDENCE
    | set(INDEPENDENT_EVIDENCE.values())
    | {
        "BUILD-COMPLETE",
        "BUILD-INFO",
        "CONTAINER-APPLY.txt",
        "INDEPENDENT-VERIFY.txt",
        "INPUT-ARTIFACTS.sha256",
        "REPRODUCE.txt",
        "SHA256SUMS",
        "SOURCE-MANIFEST.json",
        IMAGE_NAME,
    }
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
STAGE_RE = re.compile(r"^\.r46h-debian13-p2-gaming-v0\.6\.tmp\.[A-Za-z0-9]+$")


class BuildError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as handle:
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def exact_json(path: Path) -> dict[str, Any]:
    def reject_duplicates(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise BuildError(f"duplicate JSON key in {path.name}: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            path.read_bytes(),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda constant: (_ for _ in ()).throw(
                BuildError(f"non-finite JSON value in {path.name}: {constant}")
            ),
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BuildError(f"cannot parse {path.name}") from error
    if not isinstance(value, dict):
        raise BuildError(f"{path.name} is not one object")
    return value


def require_regular(path: Path, label: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise BuildError(f"missing {label}: {path}") from error
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise BuildError(f"unsafe {label}: {path}")
    return metadata


def require_directory(path: Path, label: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise BuildError(f"missing {label}: {path}") from error
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise BuildError(f"unsafe {label}: {path}")
    return metadata


def write_new(path: Path, payload: bytes, mode: int = 0o644) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def git_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") and key not in {"BASH_ENV", "CDPATH", "ENV"}
    }
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
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
        raise BuildError(
            f"git {' '.join(arguments)} failed: "
            f"{result.stderr.decode(errors='replace').strip()}"
        )
    return result.stdout


def capture_clean_source() -> tuple[str, str, dict[str, tuple[bytes, int]], bytes]:
    status = git_bytes(
        ["status", "--porcelain=v1", "--untracked-files=all", "--", *SOURCE_PATHS]
    )
    if status:
        raise BuildError(f"p2 {VERSION_TEXT} source scope must be committed and clean")
    commit = git_bytes(["rev-parse", "--verify", "HEAD^{commit}"]).decode().strip()
    tree = git_bytes(["rev-parse", "--verify", "HEAD^{tree}"]).decode().strip()
    captured: dict[str, tuple[bytes, int]] = {}
    entries: list[dict[str, object]] = []
    for relative in SOURCE_PATHS:
        live = REPO / relative
        metadata = require_regular(live, f"source file {relative}")
        tree_line = git_bytes(["ls-tree", "HEAD", "--", relative]).decode().strip()
        fields = tree_line.split(None, 3)
        if len(fields) != 4 or fields[1] != "blob" or fields[3] != relative:
            raise BuildError(f"source is not one committed blob: {relative}")
        git_mode = fields[0]
        if git_mode not in {"100644", "100755"}:
            raise BuildError(f"unsupported Git mode for source: {relative}")
        mode = 0o755 if git_mode == "100755" else 0o644
        payload = git_bytes(["cat-file", "blob", f"HEAD:{relative}"])
        if stat.S_IMODE(metadata.st_mode) != mode or live.read_bytes() != payload:
            raise BuildError(f"live source differs from HEAD: {relative}")
        captured[relative] = (payload, mode)
        entries.append(
            {
                "git_mode": git_mode,
                "path": relative,
                "sha256": sha256_bytes(payload),
                "size": len(payload),
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
    return commit, tree, captured, manifest


def capture_manifest_source(
    manifest_bytes: bytes,
) -> tuple[str, str, dict[str, tuple[bytes, int]]]:
    try:
        manifest = json.loads(manifest_bytes)
    except json.JSONDecodeError as error:
        raise BuildError("invalid retained source manifest") from error
    if not isinstance(manifest, dict) or canonical_json(manifest) != manifest_bytes:
        raise BuildError("retained source manifest is not canonical")
    commit = manifest.get("git_commit")
    tree = manifest.get("git_tree")
    entries = manifest.get("files")
    if (
        not isinstance(commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", commit) is None
        or not isinstance(tree, str)
        or re.fullmatch(r"[0-9a-f]{40}", tree) is None
        or git_bytes(["rev-parse", "--verify", f"{commit}^{{tree}}"])
        .decode()
        .strip()
        != tree
        or not isinstance(entries, list)
        or manifest.get("format_version") != 1
        or manifest.get("file_count") != len(SOURCE_PATHS)
        or len(entries) != len(SOURCE_PATHS)
    ):
        raise BuildError("retained source manifest identity mismatch")
    captured: dict[str, tuple[bytes, int]] = {}
    for expected_path, entry in zip(SOURCE_PATHS, entries):
        if not isinstance(entry, dict) or entry.get("path") != expected_path:
            raise BuildError("retained source manifest ordering mismatch")
        git_mode = entry.get("git_mode")
        if git_mode not in {"100644", "100755"}:
            raise BuildError(f"invalid retained source mode: {expected_path}")
        tree_line = git_bytes(["ls-tree", commit, "--", expected_path]).decode().strip()
        fields = tree_line.split(None, 3)
        if len(fields) != 4 or fields[0] != git_mode or fields[3] != expected_path:
            raise BuildError(f"retained source is not one blob: {expected_path}")
        payload = git_bytes(["cat-file", "blob", f"{commit}:{expected_path}"])
        if entry.get("size") != len(payload) or entry.get("sha256") != sha256_bytes(payload):
            raise BuildError(f"retained source digest mismatch: {expected_path}")
        captured[expected_path] = (payload, 0o755 if git_mode == "100755" else 0o644)
    return commit, tree, captured


def write_source_snapshot(root: Path, captured: dict[str, tuple[bytes, int]]) -> Path:
    snapshot = root / "source"
    snapshot.mkdir(mode=0o700)
    for relative, (payload, mode) in captured.items():
        destination = snapshot / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        write_new(destination, payload, mode)
    return snapshot


def safe_extract_payload(archive_path: Path, destination: Path) -> Path:
    destination.mkdir(mode=0o700)
    seen: set[str] = set()
    directory_modes: list[tuple[Path, int]] = []
    total_size = 0
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        if not members:
            raise BuildError("gaming archive is empty")
        for member in members:
            pure = PurePosixPath(member.name)
            canonical_name = pure.as_posix() + ("/" if member.isdir() else "")
            if (
                pure.is_absolute()
                or not pure.parts
                or pure.parts[0] != GAMING_PAYLOAD_ID
                or any(part in {"", ".", ".."} for part in pure.parts)
                or member.name not in {pure.as_posix(), canonical_name}
                or member.name in seen
                or member.uid != 0
                or member.gid != 0
                or not (member.isdir() or member.isreg())
            ):
                raise BuildError(f"unsafe gaming archive member: {member.name}")
            seen.add(member.name)
            target = destination.joinpath(*pure.parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                directory_modes.append((target, member.mode & 0o777))
                continue
            total_size += member.size
            if total_size > 1_073_741_824:
                raise BuildError("gaming archive expands beyond the fixed 1 GiB limit")
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = archive.extractfile(member)
            if extracted is None:
                raise BuildError(f"cannot read gaming archive member: {member.name}")
            descriptor = os.open(
                target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, member.mode & 0o777
            )
            with extracted, os.fdopen(descriptor, "wb") as output:
                shutil.copyfileobj(extracted, output, length=1024 * 1024)
    for directory, mode in reversed(directory_modes):
        directory.chmod(mode)
    payload = destination / GAMING_PAYLOAD_ID
    require_directory(payload, "extracted gaming payload")
    return payload


def payload_manifest(root: Path, excluded: set[str]) -> bytes:
    lines: list[str] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise BuildError(f"unsafe payload member: {path}")
        relative = path.relative_to(root).as_posix()
        if relative not in excluded:
            lines.append(f"{sha256_file(path)}  {relative}\n")
    return "".join(lines).encode()


def validate_payload(payload: Path) -> None:
    if {entry.name for entry in payload.iterdir()} != PAYLOAD_TOP_LEVEL:
        raise BuildError("gaming payload top-level member set mismatch")
    for relative in PAYLOAD_FILES | {
        "PACKAGES.tsv",
        "PAYLOAD-INFO.json",
        "PAYLOAD.COMPLETE",
        "SHA256SUMS",
        "install.sh",
    }:
        require_regular(payload / relative, relative)
    deb_directory = payload / "debs"
    require_directory(deb_directory, "gaming Debian package directory")
    debs = sorted(deb_directory.glob("*.deb"))
    if len(debs) < 20 or {entry for entry in deb_directory.iterdir()} != set(debs):
        raise BuildError("unexpected gaming Debian package set")
    if sha256_file(payload / "PACKAGES.tsv") != GAMING_PACKAGE_MANIFEST_SHA256:
        raise BuildError("gaming package manifest digest mismatch")
    expected_info = {
        "base_image": BASE_CONTAINER,
        "base_image_id": BASE_CONTAINER_ID,
        "format_version": 1,
        "install_from_release": KERNEL_RELEASE,
        "package_count": 6,
        "payload_id": GAMING_PAYLOAD_ID,
        "source_git_commit": GAMING_SOURCE_COMMIT,
        "target_release": KERNEL_RELEASE,
    }
    if exact_json(payload / "PAYLOAD-INFO.json") != expected_info:
        raise BuildError("gaming payload identity mismatch")
    sums = payload_manifest(payload, {"SHA256SUMS", "PAYLOAD.COMPLETE"})
    if (
        (payload / "SHA256SUMS").read_bytes() != sums
        or sha256_bytes(sums) != GAMING_PAYLOAD_SHA256SUMS_SHA256
        or (payload / "PAYLOAD.COMPLETE").read_bytes()
        != f"sha256sums_sha256={GAMING_PAYLOAD_SHA256SUMS_SHA256}\n".encode()
    ):
        raise BuildError("gaming payload checksum identity mismatch")


def load_profile() -> None:
    profile = exact_json(PROFILE)
    if profile.get("format_version") != 1 or profile.get("profile_id") != PROFILE_ID:
        raise BuildError("card profile identity mismatch")
    card = profile.get("card")
    root = card.get("root") if isinstance(card, dict) else None
    if root != {
        "number": 2,
        "offset": 134_217_728,
        "size": IMAGE_SIZE,
        "partuuid": "c9f931c9-02",
    }:
        raise BuildError("card profile p2 geometry mismatch")


def docker_command() -> str:
    command = shutil.which("docker")
    if not command:
        raise BuildError("docker is unavailable")
    return command


def require_base_container(docker: str) -> None:
    result = subprocess.run(
        [
            docker,
            "--context",
            "desktop-linux",
            "image",
            "inspect",
            BASE_CONTAINER,
            "--format",
            "{{.Id}} {{.Os}}/{{.Architecture}}",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    expected = f"{BASE_CONTAINER_ID} linux/arm64"
    if result.returncode != 0 or result.stdout.strip() != expected:
        raise BuildError(f"base container mismatch: expected {expected!r}")


def validate_inputs(docker: str, extraction_root: Path) -> Path:
    load_profile()
    base_metadata = require_regular(BASE_IMAGE, "accepted predecessor p2 image")
    if base_metadata.st_size != IMAGE_SIZE or sha256_file(BASE_IMAGE) != BASE_IMAGE_SHA256:
        raise BuildError("accepted predecessor p2 image identity mismatch")
    require_regular(BASE_BUILD_INFO, "accepted predecessor p2 build info")
    if sha256_file(BASE_BUILD_INFO) != BASE_BUILD_INFO_SHA256:
        raise BuildError("accepted predecessor p2 build info mismatch")
    archive_metadata = require_regular(
        GAMING_ARCHIVE, f"gaming {GAMING_PAYLOAD_VERSION_TEXT} archive"
    )
    if (
        archive_metadata.st_size != GAMING_ARCHIVE_SIZE
        or sha256_file(GAMING_ARCHIVE) != GAMING_ARCHIVE_SHA256
    ):
        raise BuildError(
            f"gaming {GAMING_PAYLOAD_VERSION_TEXT} archive identity mismatch"
        )
    require_base_container(docker)
    payload = safe_extract_payload(GAMING_ARCHIVE, extraction_root)
    validate_payload(payload)
    return payload


def docker_versions(docker: str) -> tuple[str, str]:
    values: list[str] = []
    for side in ("Client", "Server"):
        result = subprocess.run(
            [
                docker,
                "--context",
                "desktop-linux",
                "version",
                "--format",
                f"{{{{.{side}.Version}}}}",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        value = result.stdout.strip()
        if result.returncode != 0 or re.fullmatch(r"[0-9A-Za-z._+-]+", value) is None:
            raise BuildError(f"cannot query Docker {side.lower()} version")
        values.append(value)
    return values[0], values[1]


def build_environment(source_commit: str, source_tree: str, manifest_sha256: str) -> dict[str, str]:
    environment = {
        "ALSA_OVERRIDE_RULE_SHA256": ALSA_OVERRIDE_RULE_SHA256,
        "ALSA_VENDOR_RULE_SHA256": ALSA_VENDOR_RULE_SHA256,
        "ARTIFACT_ID": ARTIFACT_ID,
        "BASE_CONSOLIDATED_RECEIPT_SHA256": BASE_CONSOLIDATED_RECEIPT_SHA256,
        "BASE_CONTAINER_ID": BASE_CONTAINER_ID,
        "BASE_FIRSTBOOT_SHA256": BASE_FIRSTBOOT_SHA256,
        "BASE_FS_LABEL": BASE_FS_LABEL,
        "BASE_FS_UUID": BASE_FS_UUID,
        "BASE_GAMING_RECEIPT_SHA256": BASE_GAMING_RECEIPT_SHA256,
        "BASE_IMAGE_SHA256": BASE_IMAGE_SHA256,
        "BASE_ROOTFS_SMOKE_SHA256": BASE_ROOTFS_SMOKE_SHA256,
        "FINAL_FIRSTBOOT_SHA256": FINAL_FIRSTBOOT_SHA256,
        "FINAL_ROOTFS_SMOKE_SHA256": FINAL_ROOTFS_SMOKE_SHA256,
        "FS_LABEL": FS_LABEL,
        "FS_TAIL_SIZE": str(FS_TAIL_SIZE),
        "FS_UUID": FS_UUID,
        "GAMING_ARCHIVE_SHA256": GAMING_ARCHIVE_SHA256,
        "GAMING_PACKAGE_MANIFEST_SHA256": GAMING_PACKAGE_MANIFEST_SHA256,
        "GAMING_PAYLOAD_SHA256SUMS_SHA256": GAMING_PAYLOAD_SHA256SUMS_SHA256,
        "GAMING_SOURCE_COMMIT": GAMING_SOURCE_COMMIT,
        "IMAGE_NAME": IMAGE_NAME,
        "IMAGE_SIZE": str(IMAGE_SIZE),
        "KERNEL_RELEASE": KERNEL_RELEASE,
        "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH,
        "SOURCE_GIT_COMMIT": source_commit,
        "SOURCE_GIT_TREE": source_tree,
        "SOURCE_MANIFEST_SHA256": manifest_sha256,
    }
    duplicate_keys = set(environment) & set(EXTRA_BUILD_ENVIRONMENT)
    if duplicate_keys:
        raise BuildError(f"duplicate build environment keys: {sorted(duplicate_keys)}")
    environment.update(EXTRA_BUILD_ENVIRONMENT)
    return environment


def run_image_tool(
    docker: str,
    action: str,
    image_directory: Path,
    source: Path,
    payload: Path,
    work: Path,
    evidence: Path,
    environment: dict[str, str],
    *,
    writable_image: bool,
) -> str:
    work.mkdir(mode=0o700)
    evidence.mkdir(mode=0o700)
    arguments = [
        docker,
        "--context",
        "desktop-linux",
        "run",
        "--rm",
        "--platform",
        "linux/arm64",
        "--network",
        "none",
        "--mount",
        f"type=bind,source={source},target=/source,readonly",
        "--mount",
        f"type=bind,source={payload},target=/payload,readonly",
        "--mount",
        (
            f"type=bind,source={image_directory},target=/output"
            + ("" if writable_image else ",readonly")
        ),
        "--mount",
        f"type=bind,source={work},target=/work",
        "--mount",
        f"type=bind,source={evidence},target=/evidence",
    ]
    for key, value in environment.items():
        arguments.extend(("--env", f"{key}={value}"))
    arguments.extend(
        (
            BASE_CONTAINER,
            f"/source/{IMAGE_TOOL_RELATIVE}",
            action,
        )
    )
    result = subprocess.run(
        arguments,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        raise BuildError(f"container image {action} failed with status {result.returncode}")
    expected = f"PASS: R46H Debian 13 gaming p2 {VERSION_TEXT} image {action} completed."
    if expected not in result.stdout:
        raise BuildError(f"container image {action} success marker missing")
    return result.stdout


def clone_base_image(destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise BuildError(f"clone destination already exists: {destination}")
    result = subprocess.run(
        ["/bin/cp", "-c", str(BASE_IMAGE), str(destination)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise BuildError(f"APFS clone failed: {result.stderr.strip()}")
    metadata = require_regular(destination, f"private p2 {VERSION_TEXT} clone")
    if metadata.st_size != IMAGE_SIZE:
        raise BuildError(f"private p2 {VERSION_TEXT} clone length mismatch")


def parse_build_info(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.count("=") != 1:
            raise BuildError("invalid BUILD-INFO syntax")
        key, value = line.split("=", 1)
        if not key or not value or key in values:
            raise BuildError("invalid BUILD-INFO field")
        values[key] = value
    return values


def require_ext4_superblock(image: Path) -> None:
    with image.open("rb", buffering=0) as handle:
        handle.seek(1024 + 56)
        if handle.read(2) != struct.pack("<H", 0xEF53):
            raise BuildError(f"p2 {VERSION_TEXT} image lacks the ext4 superblock magic")
        handle.seek(-FS_TAIL_SIZE, os.SEEK_END)
        if handle.read(FS_TAIL_SIZE) != b"\0" * FS_TAIL_SIZE:
            raise BuildError(f"p2 {VERSION_TEXT} image tail is not zero-filled")


def write_build_metadata(
    stage: Path,
    source_commit: str,
    source_tree: str,
    source_manifest: bytes,
    image_sha256: str,
    docker_client: str,
    docker_server: str,
) -> None:
    values = {
        "artifact_id": ARTIFACT_ID,
        "artifact_status": ARTIFACT_STATUS,
        "base_build_info_sha256": BASE_BUILD_INFO_SHA256,
        "base_container": BASE_CONTAINER,
        "base_container_id": BASE_CONTAINER_ID,
        "base_image_sha256": BASE_IMAGE_SHA256,
        "build_inputs_git_dirty": "false",
        "docker_client_version": docker_client,
        "docker_context": "desktop-linux",
        "docker_server_version": docker_server,
        "filesystem_label": FS_LABEL,
        "filesystem_uuid": FS_UUID,
        "gaming_archive_sha256": GAMING_ARCHIVE_SHA256,
        "gaming_package_manifest_sha256": GAMING_PACKAGE_MANIFEST_SHA256,
        "gaming_payload_id": GAMING_PAYLOAD_ID,
        "gaming_payload_sha256sums_sha256": GAMING_PAYLOAD_SHA256SUMS_SHA256,
        "gaming_source_commit": GAMING_SOURCE_COMMIT,
        "image_name": IMAGE_NAME,
        "image_sha256": image_sha256,
        "image_size": str(IMAGE_SIZE),
        "kernel_release": KERNEL_RELEASE,
        "profile_id": PROFILE_ID,
        "root_partuuid": "c9f931c9-02",
        "source_date_epoch": SOURCE_DATE_EPOCH,
        "source_git_commit": source_commit,
        "source_git_tree": source_tree,
        "source_manifest_sha256": sha256_bytes(source_manifest),
        "source_snapshot_method": "exact-committed-blobs",
        "successor_method": "offline-debugfs-bounded-overlay",
        "udev_vendor_rule_sha256": ALSA_VENDOR_RULE_SHA256,
        "udev_override_rule_sha256": ALSA_OVERRIDE_RULE_SHA256,
    }
    duplicate_keys = set(values) & set(EXTRA_BUILD_INFO)
    if duplicate_keys:
        raise BuildError(f"duplicate BUILD-INFO keys: {sorted(duplicate_keys)}")
    values.update(EXTRA_BUILD_INFO)
    write_new(
        stage / "BUILD-INFO",
        "".join(f"{key}={value}\n" for key, value in values.items()).encode(),
    )
    write_new(stage / "SOURCE-MANIFEST.json", source_manifest)
    write_new(
        stage / "INPUT-ARTIFACTS.sha256",
        (
            f"{BASE_IMAGE_SHA256}  {BASE_IMAGE_RECEIPT_NAME}\n"
            f"{BASE_BUILD_INFO_SHA256}  {BASE_BUILD_INFO_RECEIPT_NAME}\n"
            f"{GAMING_ARCHIVE_SHA256}  {GAMING_ARCHIVE_NAME}\n"
        ).encode(),
    )
    write_new(
        stage / "BUILD-COMPLETE",
        (
            f"artifact_id={ARTIFACT_ID}\n"
            f"image_sha256={image_sha256}\n"
            f"source_git_commit={source_commit}\n"
        ).encode(),
    )


def validate_stage(stage: Path, expected_source_commit: str | None = None) -> str:
    require_directory(stage, f"p2 {VERSION_TEXT} artifact directory")
    names = {entry.name for entry in stage.iterdir()}
    if names != REQUIRED_STAGE_FILES:
        raise BuildError(f"unexpected artifact file set: {sorted(names ^ REQUIRED_STAGE_FILES)}")
    for name in names:
        require_regular(stage / name, name)
    image = stage / IMAGE_NAME
    if image.stat().st_size != IMAGE_SIZE:
        raise BuildError(f"p2 {VERSION_TEXT} image size mismatch")
    require_ext4_superblock(image)
    image_sha256 = sha256_file(image)
    expected_image_receipt = f"{image_sha256}  {IMAGE_NAME}\n"
    for name in ("EXT4-VERIFIED.sha256", "INDEPENDENT-EXT4-VERIFIED.sha256"):
        if (stage / name).read_text(encoding="utf-8") != expected_image_receipt:
            raise BuildError(f"image verification receipt mismatch: {name}")

    build_info = parse_build_info(stage / "BUILD-INFO")
    expected = {
        "artifact_id": ARTIFACT_ID,
        "artifact_status": ARTIFACT_STATUS,
        "base_build_info_sha256": BASE_BUILD_INFO_SHA256,
        "base_container": BASE_CONTAINER,
        "base_container_id": BASE_CONTAINER_ID,
        "base_image_sha256": BASE_IMAGE_SHA256,
        "build_inputs_git_dirty": "false",
        "docker_context": "desktop-linux",
        "filesystem_label": FS_LABEL,
        "filesystem_uuid": FS_UUID,
        "gaming_archive_sha256": GAMING_ARCHIVE_SHA256,
        "gaming_package_manifest_sha256": GAMING_PACKAGE_MANIFEST_SHA256,
        "gaming_payload_id": GAMING_PAYLOAD_ID,
        "gaming_payload_sha256sums_sha256": GAMING_PAYLOAD_SHA256SUMS_SHA256,
        "gaming_source_commit": GAMING_SOURCE_COMMIT,
        "image_name": IMAGE_NAME,
        "image_sha256": image_sha256,
        "image_size": str(IMAGE_SIZE),
        "kernel_release": KERNEL_RELEASE,
        "profile_id": PROFILE_ID,
        "root_partuuid": "c9f931c9-02",
        "source_date_epoch": SOURCE_DATE_EPOCH,
        "source_snapshot_method": "exact-committed-blobs",
        "successor_method": "offline-debugfs-bounded-overlay",
        "udev_vendor_rule_sha256": ALSA_VENDOR_RULE_SHA256,
        "udev_override_rule_sha256": ALSA_OVERRIDE_RULE_SHA256,
    }
    duplicate_keys = set(expected) & set(EXTRA_BUILD_INFO)
    if duplicate_keys:
        raise BuildError(f"duplicate BUILD-INFO keys: {sorted(duplicate_keys)}")
    expected.update(EXTRA_BUILD_INFO)
    for key, value in expected.items():
        if build_info.get(key) != value:
            raise BuildError(f"BUILD-INFO mismatch for {key}")
    for key in ("source_git_commit", "source_git_tree"):
        if re.fullmatch(r"[0-9a-f]{40}", build_info.get(key, "")) is None:
            raise BuildError(f"invalid BUILD-INFO Git identity: {key}")
    if expected_source_commit and build_info["source_git_commit"] != expected_source_commit:
        raise BuildError("BUILD-INFO source commit mismatch")
    source_manifest = (stage / "SOURCE-MANIFEST.json").read_bytes()
    if build_info.get("source_manifest_sha256") != sha256_bytes(source_manifest):
        raise BuildError("source manifest digest mismatch")
    captured_commit, captured_tree, _ = capture_manifest_source(source_manifest)
    if (
        captured_commit != build_info["source_git_commit"]
        or captured_tree != build_info["source_git_tree"]
    ):
        raise BuildError("source manifest Git identity mismatch")
    for key in ("docker_client_version", "docker_server_version"):
        if re.fullmatch(r"[0-9A-Za-z._+-]+", build_info.get(key, "")) is None:
            raise BuildError(f"invalid BUILD-INFO Docker identity: {key}")

    expected_inputs = (
        f"{BASE_IMAGE_SHA256}  {BASE_IMAGE_RECEIPT_NAME}\n"
        f"{BASE_BUILD_INFO_SHA256}  {BASE_BUILD_INFO_RECEIPT_NAME}\n"
        f"{GAMING_ARCHIVE_SHA256}  {GAMING_ARCHIVE_NAME}\n"
    )
    if (stage / "INPUT-ARTIFACTS.sha256").read_text(encoding="utf-8") != expected_inputs:
        raise BuildError("input artifact receipt mismatch")
    markers = {
        DEBUGFS_EVIDENCE_NAME: f"R46H_{VERSION_TOKEN}_IMAGE_VERIFY_RESULT=pass",
        "E2FSCK.txt": f"R46H_{VERSION_TOKEN}_E2FSCK_RESULT=pass",
        INDEPENDENT_DEBUGFS_EVIDENCE_NAME: (
            f"R46H_{VERSION_TOKEN}_IMAGE_VERIFY_RESULT=pass"
        ),
        "INDEPENDENT-E2FSCK.txt": f"R46H_{VERSION_TOKEN}_E2FSCK_RESULT=pass",
        "INDEPENDENT-SYSTEMD-VERIFY.txt": (
            f"R46H_{VERSION_TOKEN}_SYSTEMD_VERIFY_RESULT=pass"
        ),
        "INDEPENDENT-UDEV-VERIFY.txt": (
            f"R46H_{VERSION_TOKEN}_UDEV_VERIFY_RESULT=pass"
        ),
        "INDEPENDENT-VERIFY.txt": (
            f"PASS: R46H Debian 13 gaming p2 {VERSION_TEXT} image verify completed."
        ),
        "REPRODUCE.txt": f"R46H_{VERSION_TOKEN}_REPRODUCE_RESULT=pass",
        "SYSTEMD-VERIFY.txt": f"R46H_{VERSION_TOKEN}_SYSTEMD_VERIFY_RESULT=pass",
        "UDEV-VERIFY.txt": f"R46H_{VERSION_TOKEN}_UDEV_VERIFY_RESULT=pass",
    }
    for name, marker in markers.items():
        if marker not in (stage / name).read_text(encoding="utf-8", errors="replace"):
            raise BuildError(f"retained verification marker missing: {name}")
    reproduce = (stage / "REPRODUCE.txt").read_text(encoding="utf-8")
    if reproduce.count(f"image_sha256={image_sha256}\n") != 2:
        raise BuildError("reproducibility receipt does not contain two matching images")

    receipt = (stage / "CONSOLIDATED-RECEIPT").read_text(encoding="utf-8")
    for line in (
        f"artifact_id={ARTIFACT_ID}",
        f"source_git_commit={build_info['source_git_commit']}",
        f"successor_base_image_sha256={BASE_IMAGE_SHA256}",
        f"gaming_archive_sha256={GAMING_ARCHIVE_SHA256}",
        f"alsa_vendor_rule_sha256={ALSA_VENDOR_RULE_SHA256}",
        f"alsa_override_rule_sha256={ALSA_OVERRIDE_RULE_SHA256}",
        f"filesystem_uuid={FS_UUID}",
        f"filesystem_label={FS_LABEL}",
        "personal_authorized_keys=absent",
        "diagnostic_input_bridge=absent",
        *CONSOLIDATED_RECEIPT_EXTRA_MARKERS,
    ):
        if f"{line}\n" not in receipt:
            raise BuildError(f"consolidated receipt marker missing: {line}")
    gaming_receipt = (stage / "GAMING-RECEIPT").read_text(encoding="utf-8")
    if gaming_receipt != (
        f"payload_id={GAMING_PAYLOAD_ID}\n"
        f"target_release={KERNEL_RELEASE}\n"
        f"package_manifest_sha256={GAMING_PACKAGE_MANIFEST_SHA256}\n"
        f"payload_sha256sums_sha256={GAMING_PAYLOAD_SHA256SUMS_SHA256}\n"
    ):
        raise BuildError(f"gaming {GAMING_PAYLOAD_VERSION_TEXT} receipt mismatch")
    build_complete = (stage / "BUILD-COMPLETE").read_text(encoding="utf-8")
    if build_complete != (
        f"artifact_id={ARTIFACT_ID}\n"
        f"image_sha256={image_sha256}\n"
        f"source_git_commit={build_info['source_git_commit']}\n"
    ):
        raise BuildError("build completion marker mismatch")

    sums = (stage / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    expected_names = sorted(REQUIRED_STAGE_FILES - {"SHA256SUMS"})
    if len(sums) != len(expected_names):
        raise BuildError("artifact checksum manifest length mismatch")
    for line, name in zip(sums, expected_names):
        match = re.fullmatch(rf"([0-9a-f]{{64}})  {re.escape(name)}", line)
        if match is None or match.group(1) != sha256_file(stage / name):
            raise BuildError(f"artifact checksum mismatch: {name}")
    return image_sha256


def move_apply_evidence(evidence: Path, stage: Path) -> None:
    names = {entry.name for entry in evidence.iterdir()}
    if names != APPLY_EVIDENCE:
        raise BuildError(f"unexpected apply evidence set: {sorted(names ^ APPLY_EVIDENCE)}")
    for name in sorted(names):
        source = evidence / name
        require_regular(source, f"apply evidence {name}")
        os.replace(source, stage / name)


def retain_independent_evidence(evidence: Path, stage: Path) -> None:
    for source_name, destination_name in INDEPENDENT_EVIDENCE.items():
        source = evidence / source_name
        require_regular(source, f"independent evidence {source_name}")
        shutil.copyfile(source, stage / destination_name)


def rename_noreplace(parent_fd: int, source_name: str, destination_name: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    destination = os.fsencode(destination_name)
    if hasattr(libc, "renameatx_np"):
        call = libc.renameatx_np
        call.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        call.restype = ctypes.c_int
        result = call(parent_fd, source, parent_fd, destination, 0x00000004)
    elif hasattr(libc, "renameat2"):
        call = libc.renameat2
        call.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        call.restype = ctypes.c_int
        result = call(parent_fd, source, parent_fd, destination, 1)
    else:
        raise BuildError("platform lacks atomic no-replace rename support")
    if result != 0:
        error = ctypes.get_errno()
        if error in {errno.EEXIST, errno.ENOTEMPTY}:
            raise BuildError(f"output already exists: {destination_name}")
        raise OSError(error, os.strerror(error))


def publish(stage: Path) -> None:
    if stage.parent != OUTPUT_ROOT or STAGE_RE.fullmatch(stage.name) is None:
        raise BuildError(f"unsafe p2 {VERSION_TEXT} staging directory")
    if OUTPUT_DIR.exists() or OUTPUT_DIR.is_symlink():
        raise BuildError(f"output already exists: {OUTPUT_DIR}")
    output_fd = os.open(OUTPUT_ROOT, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        rename_noreplace(output_fd, stage.name, OUTPUT_NAME)
    finally:
        os.close(output_fd)
    if stage.exists() or not OUTPUT_DIR.is_dir():
        raise BuildError("published output is not the validated staging directory")


def command_validate_inputs() -> None:
    docker = docker_command()
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="preflight.", dir=CACHE_ROOT))
    try:
        validate_inputs(docker, work / "payload-extract")
        print(
            f"PASS: exact predecessor base, gaming {GAMING_PAYLOAD_VERSION_TEXT} payload, "
            "container and p2 geometry validated."
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)


def command_build() -> Path:
    if OUTPUT_DIR.exists() or OUTPUT_DIR.is_symlink():
        raise BuildError(f"output already exists: {OUTPUT_DIR}")
    if shutil.disk_usage(OUTPUT_ROOT).free < 12 * 1024**3:
        raise BuildError("less than 12 GiB is available in the external workspace")
    source_commit, source_tree, captured, source_manifest = capture_clean_source()
    source_manifest_sha256 = sha256_bytes(source_manifest)
    docker = docker_command()
    docker_client, docker_server = docker_versions(docker)
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="work.", dir=CACHE_ROOT))
    stage = Path(tempfile.mkdtemp(prefix=f".{OUTPUT_NAME}.tmp.", dir=OUTPUT_ROOT))
    stage.chmod(0o700)
    published = False
    try:
        source = write_source_snapshot(work, captured)
        payload = validate_inputs(docker, work / "payload-extract")
        environment = build_environment(source_commit, source_tree, source_manifest_sha256)
        clone_base_image(stage / IMAGE_NAME)
        apply_output = run_image_tool(
            docker,
            "apply",
            stage,
            source,
            payload,
            work / "apply-work",
            work / "apply-evidence",
            environment,
            writable_image=True,
        )
        write_new(stage / "CONTAINER-APPLY.txt", apply_output.encode())
        move_apply_evidence(work / "apply-evidence", stage)
        image_sha256 = sha256_file(stage / IMAGE_NAME)
        if (stage / "EXT4-VERIFIED.sha256").read_text(encoding="utf-8") != (
            f"{image_sha256}  {IMAGE_NAME}\n"
        ):
            raise BuildError("container and host image digests differ")

        reproduce_directory = work / "reproduce-image"
        reproduce_directory.mkdir(mode=0o700)
        clone_base_image(reproduce_directory / IMAGE_NAME)
        run_image_tool(
            docker,
            "apply",
            reproduce_directory,
            source,
            payload,
            work / "reproduce-work",
            work / "reproduce-evidence",
            environment,
            writable_image=True,
        )
        reproduce_sha256 = sha256_file(reproduce_directory / IMAGE_NAME)
        if reproduce_sha256 != image_sha256:
            raise BuildError(
                f"second p2 {VERSION_TEXT} composition is not byte-reproducible"
            )
        write_new(
            stage / "REPRODUCE.txt",
            (
                f"first_image_sha256={image_sha256}\n"
                f"second_image_sha256={reproduce_sha256}\n"
                f"R46H_{VERSION_TOKEN}_REPRODUCE_RESULT=pass\n"
            ).encode(),
        )

        independent_output = run_image_tool(
            docker,
            "verify",
            stage,
            source,
            payload,
            work / "independent-work",
            work / "independent-evidence",
            environment,
            writable_image=False,
        )
        write_new(stage / "INDEPENDENT-VERIFY.txt", independent_output.encode())
        retain_independent_evidence(work / "independent-evidence", stage)
        write_build_metadata(
            stage,
            source_commit,
            source_tree,
            source_manifest,
            image_sha256,
            docker_client,
            docker_server,
        )
        digest_lines = []
        for name in sorted(REQUIRED_STAGE_FILES - {"SHA256SUMS"}):
            require_regular(stage / name, name)
            digest_lines.append(f"{sha256_file(stage / name)}  {name}\n")
        write_new(stage / "SHA256SUMS", "".join(digest_lines).encode())
        validate_stage(stage, source_commit)
        if git_bytes(["rev-parse", "--verify", "HEAD^{commit}"]).decode().strip() != source_commit:
            raise BuildError(f"HEAD changed during p2 {VERSION_TEXT} build")
        if git_bytes(
            ["status", "--porcelain=v1", "--untracked-files=all", "--", *SOURCE_PATHS]
        ):
            raise BuildError(f"p2 {VERSION_TEXT} source scope changed during build")
        publish(stage)
        published = True
        print(f"PASS: successor Debian 13 gaming product p2 {VERSION_TEXT} host artifact published.")
        print(f"STATUS={ARTIFACT_STATUS}")
        print(f"OUTPUT_DIR={OUTPUT_DIR}")
        print(f"IMAGE_SHA256={image_sha256}")
        return OUTPUT_DIR
    finally:
        if not published and stage.exists() and stage.parent == OUTPUT_ROOT:
            shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)


def command_validate() -> None:
    image_sha256 = validate_stage(OUTPUT_DIR)
    build_info = parse_build_info(OUTPUT_DIR / "BUILD-INFO")
    manifest = (OUTPUT_DIR / "SOURCE-MANIFEST.json").read_bytes()
    source_commit, source_tree, captured = capture_manifest_source(manifest)
    docker = docker_command()
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="validate.", dir=CACHE_ROOT))
    try:
        source = write_source_snapshot(work, captured)
        payload = validate_inputs(docker, work / "payload-extract")
        environment = build_environment(
            source_commit, source_tree, build_info["source_manifest_sha256"]
        )
        run_image_tool(
            docker,
            "verify",
            OUTPUT_DIR,
            source,
            payload,
            work / "verify-work",
            work / "verify-evidence",
            environment,
            writable_image=False,
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(
        f"PASS: successor Debian 13 gaming product p2 {VERSION_TEXT} artifact "
        "independently validated."
    )
    print(f"IMAGE_SHA256={image_sha256}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "validate-inputs", "validate"))
    return parser.parse_args()


def main() -> int:
    try:
        action = parse_args().action
        if action == "build":
            command_build()
        elif action == "validate-inputs":
            command_validate_inputs()
        else:
            command_validate()
    except (BuildError, OSError, tarfile.TarError, UnicodeDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
