#!/usr/bin/env python3
"""Compose and publish the offline R46H Debian 13 gaming product p2 v0.5 image."""

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
import uuid


REPO = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = REPO / "mainline/out"
CACHE_ROOT = OUTPUT_ROOT / ".cache/r46h-debian13-gaming-rootfs"
OUTPUT_NAME = "r46h-debian13-p2-gaming-v0.5"
ARTIFACT_ID = "debian13-p2-gaming-v0.5"
IMAGE_NAME = f"{OUTPUT_NAME}.ext4"
OUTPUT_DIR = OUTPUT_ROOT / OUTPUT_NAME

IMAGE_SIZE = 10_716_877_312
FS_BLOCK_SIZE = 4096
FS_BLOCK_COUNT = 2_616_425
FS_TAIL_SIZE = 512
FS_UUID = "d3130005-46a4-4d56-9001-000000000005"
FS_LABEL = "R46H_GAMING_V05"
PROFILE_ID = "hl-r46h-v22-g92-v1"
SOURCE_DATE_EPOCH = "1787529600"

BASE_IMAGE = (
    "arkos4clone/r46h-debian13-p2-mvp:v0.1@"
    "sha256:bd09bf6db6f1fb8f882621e98d70f01f976fd8dfba1bc897766afebd64cf51b9"
)
BASE_IMAGE_ID = "sha256:bd09bf6db6f1fb8f882621e98d70f01f976fd8dfba1bc897766afebd64cf51b9"
V08_FALLBACK_RELEASE = "6.12.99-r46h-mainline-v0.8-bootloader-handoff"
V08_FALLBACK_BUNDLE_NAME = "r46h-mainline-test-v0.8-bootloader-handoff.tar.gz"
V08_FALLBACK_BUNDLE_SIZE = 33_259_526
V08_FALLBACK_BUNDLE_SHA256 = "8c7282a07bdec52b753a8af27d15c6bbc8b71b34d017c3d78a2273fba6cfd09e"
V08_FALLBACK_MODULE_TREE_SHA256 = "2ec532a3d3c6833538bd4ffd284122afa30bea0945e832f57be481527986f210"
V08_FALLBACK_BUNDLE = OUTPUT_ROOT / V08_FALLBACK_BUNDLE_NAME
V10_FALLBACK_RELEASE = "6.12.99-r46h-mainline-v0.10-adc-full-range"
V10_FALLBACK_BUNDLE_NAME = "r46h-mainline-test-v0.10-adc-full-range.tar.gz"
V10_FALLBACK_BUNDLE_SIZE = 33_258_814
V10_FALLBACK_BUNDLE_SHA256 = "c4350520f7ad33ecf7b50f67c42985e2ce26c1c38d050ad50601c3538cebc780"
V10_FALLBACK_MODULE_TREE_SHA256 = "a70796c050de93c4c212180addf54a17efe7732d355db2b52d0bfcab6c56cc16"
V10_FALLBACK_BUNDLE = OUTPUT_ROOT / V10_FALLBACK_BUNDLE_NAME
KERNEL_RELEASE = "6.12.99-r46h-mainline-v0.15-gaming-product"
KERNEL_BUNDLE_NAME = "r46h-mainline-test-v0.15-gaming-product.tar.gz"
KERNEL_BUNDLE_SIZE = 33_268_548
KERNEL_BUNDLE_SHA256 = "748d81cc0e8b9bf353430db1f4ee358bf09dee1d32db85a855961368b58d3fad"
KERNEL_BUNDLE = OUTPUT_ROOT / KERNEL_BUNDLE_NAME
KERNEL_SOURCE_COMMIT = "6e36b43ce1048a5924d3b64dde1c038d2ac87e4e"
KERNEL_SOURCE_SNAPSHOT_SHA256 = "d86166716fc156d5e6e7b9a6aaa98f512aded75c4c156680aab353a1b43de997"
KERNEL_MODULE_TREE_SHA256 = "bd53fad3997ced39a15c69dbd70525106e891e5529dcef73bbbcfb699aafc291"
KERNEL_IMAGE_SIZE = 41_570_816
KERNEL_IMAGE_SHA256 = "956ab3d5a2e53afbfe964ae75850e8591b44c093b9779867b31149b7b591f68f"
KERNEL_DTB_SIZE = 49_518
KERNEL_DTB_SHA256 = "4d6d4ebad3b98600b6e9a38df4ca82230335558497a9e15dd0e81ca60e304b61"
PRODUCT_KERNEL_DIRECTORY = "/var/lib/r46h-gaming-product-kernel/v0.15-gaming-product"
PRODUCT_KERNEL_RELATIVE = PRODUCT_KERNEL_DIRECTORY.removeprefix("/")
PRODUCT_UBOOT_COMMANDS_SHA256 = "51bf7caf6e9a08f01e1007a0010841e539300d8776851630e9d7d2829589d717"

GAMING_PAYLOAD_ID = "r46h-gaming-mvp-v0.4"
GAMING_ARCHIVE_NAME = f"{GAMING_PAYLOAD_ID}.tar.gz"
GAMING_ARCHIVE_SIZE = 263_529_005
GAMING_ARCHIVE_SHA256 = "c192e6301b112e26436836e59fc8b9cf82af85851352d8db1a41bebb942e2c2e"
GAMING_ARCHIVE = (
    OUTPUT_ROOT
    / "r46h-gaming-mvp/builds/build-9cb978888b54-c192e6301b11"
    / GAMING_ARCHIVE_NAME
)
GAMING_SOURCE_COMMIT = "9cb978888b54ddc68dbaa600daf9cb38f006c047"
GAMING_PACKAGE_MANIFEST_SHA256 = "c726b6cad27da02ab4f6215b35654319a143858b6bf6e1b641d7b720775ab8f7"
GAMING_PAYLOAD_SHA256SUMS_SHA256 = "e9da64fdee61f157347528656122a9d64e3b1417fdee7642b5030952fff723b7"
GAMING_RECEIPT_SHA256 = "0a0675e82aa35fb22252de2d688fa280275e52634ef9a130c5e415ba2cc04666"
GAME_UI_SHA256 = "867664284d932cd23757b40d7108ed878d3ab8d16f5655956543444619e75ff3"
SMOKE_CORE_SHA256 = "a6618fec16ab91fcfbc76497416c4542d1973862affb82f633ee70d600739085"
STORAGE_AUDIT_SHA256 = "08ed33dace8a94a6b129d72896c8e6a657b32d15c74d9ecf48df99a9f49ae95c"
RETROARCH_CONFIG_SHA256 = "99a45beb148e58e40983773b4f5e26d9fb5d7e1bbbf6a7e714a5c352e43c0dba"
NES_SMOKE_SHA256 = "f4e911f38aade8353853127e5e45b91aef1333061bdf865ec1775236e72abb0c"
BASE_FIRSTBOOT_SHA256 = "c4f9ee2cbf3b70156e4c9cb84d5b71307ef756bbf86bd3a2a22a5bdb4a0b2fa5"
FINAL_FIRSTBOOT_SHA256 = "dd9bbbb0076de8cea73261ed278709fe2d7fd5451a5b32b5f401d6f9e051a708"
BASE_ROOTFS_SMOKE_SHA256 = "32e1eed3184a57a1f627d942afa61f0fb539103814c00754354bd51f9544736c"
FINAL_ROOTFS_SMOKE_SHA256 = "2255b9d58e24408e5157c124d8828c84ff6f27f17133a407e8f8d33c26ac40a6"

PROFILE = REPO / "mainline/deploy/profiles/hl-r46h-v22-g92-v1.json"
SOURCE_PATHS = (
    "mainline/rootfs-debian13-gaming/build-ext4-in-container.sh",
    "mainline/rootfs-debian13-gaming/compose-in-container.sh",
    "mainline/rootfs-debian13-gaming/README.md",
    "mainline/rootfs-debian13-gaming/UBOOT-CMDS.product",
    "mainline/scripts/build-debian13-gaming-rootfs.py",
    "mainline/tests/test-debian13-gaming-rootfs.py",
    "mainline/deploy/profiles/hl-r46h-v22-g92-v1.json",
)

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
    "files/r46h-game-ui",
    "files/r46h-gaming-frontend-condition",
    "files/r46h-gaming-frontend.service",
    "files/r46h-gaming-input-ready",
    "files/r46h-gaming-input.service",
    "files/r46h-input-bridge",
    "files/r46h-nes-smoke.nes",
    "files/r46h-smoke-libretro.so",
    "files/r46h-storage-audit",
    "files/retroarch.cfg",
}
REQUIRED_STAGE_FILES = {
    "APT-INRELEASE-SHA256SUMS",
    "BUILD-INFO",
    "COMPOSE-VERIFY.txt",
    "CONSOLIDATED-RECEIPT",
    "DEBUGFS-GAMING.txt",
    "DUMPE2FS.txt",
    "E2FSCK.txt",
    "EXT4-VERIFIED.sha256",
    "V08-KERNEL-BUNDLE-VERIFY.txt",
    "V10-KERNEL-BUNDLE-VERIFY.txt",
    "GAMING-PAYLOAD-VERIFY.txt",
    "GAMING-RECEIPT",
    "GAMING-SYSTEMD-VERIFY.txt",
    "INPUT-ARTIFACTS.sha256",
    "KERNEL-BUNDLE-VERIFY.txt",
    "NESTOPIA-ROM-LOAD.txt",
    "PACKAGES.tsv",
    "PRODUCT-KERNEL-FILES.sha256",
    "RETROARCH-FEATURES.txt",
    "RETROARCH-LDD.txt",
    "ROOTFS-FILES.sha256",
    "ROOTFS-TREE.tsv",
    "SHA256SUMS",
    "SMOKE-CORE-FILE.txt",
    "SMOKE-CORE-LOAD.txt",
    "SOURCE-MANIFEST.json",
    "SOURCE-SHA256SUMS",
    "SSHD-EFFECTIVE.txt",
    "SYSTEMD-VERIFY.txt",
    IMAGE_NAME,
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
STAGE_RE = re.compile(r"^\.r46h-debian13-p2-gaming-v0\.5\.tmp\.[A-Za-z0-9]+$")


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
        raise BuildError("consolidated rootfs source scope must be committed and clean")
    commit = git_bytes(["rev-parse", "--verify", "HEAD^{commit}"]).decode().strip()
    tree = git_bytes(["rev-parse", "--verify", "HEAD^{tree}"]).decode().strip()
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise BuildError("invalid source commit")

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
        if stat.S_IMODE(metadata.st_mode) != mode:
            raise BuildError(f"live source mode differs from Git: {relative}")
        payload = git_bytes(["cat-file", "blob", f"HEAD:{relative}"])
        if live.read_bytes() != payload:
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
            ):
                raise BuildError(f"unsafe gaming archive path: {member.name}")
            seen.add(member.name)
            if member.uid != 0 or member.gid != 0:
                raise BuildError(f"unexpected gaming archive owner: {member.name}")
            if not (member.isdir() or member.isreg()):
                raise BuildError(f"unsupported gaming archive member: {member.name}")
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
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, member.mode & 0o777)
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
    require_directory(payload, "gaming payload")
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
    for deb in debs:
        require_regular(deb, "gaming Debian package")

    if sha256_file(payload / "PACKAGES.tsv") != GAMING_PACKAGE_MANIFEST_SHA256:
        raise BuildError("gaming package manifest digest mismatch")
    packages: dict[str, str] = {}
    for line in (payload / "PACKAGES.tsv").read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 2 or not all(fields) or fields[0] in packages:
            raise BuildError("invalid gaming package manifest")
        packages[fields[0]] = fields[1]
    if set(packages) != {
        "kbd",
        "libretro-desmume",
        "libretro-gambatte",
        "libretro-mgba",
        "libretro-nestopia",
        "retroarch",
    }:
        raise BuildError("gaming package manifest has an unexpected package set")

    expected_info = {
        "base_image": BASE_IMAGE,
        "base_image_id": BASE_IMAGE_ID,
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
    if (payload / "SHA256SUMS").read_bytes() != sums:
        raise BuildError("gaming payload checksum manifest mismatch")
    if sha256_bytes(sums) != GAMING_PAYLOAD_SHA256SUMS_SHA256:
        raise BuildError("gaming payload checksum identity mismatch")
    if (payload / "PAYLOAD.COMPLETE").read_bytes() != (
        f"sha256sums_sha256={GAMING_PAYLOAD_SHA256SUMS_SHA256}\n".encode()
    ):
        raise BuildError("gaming payload completion marker mismatch")
    if sha256_file(payload / "files/r46h-nes-smoke.nes") != NES_SMOKE_SHA256:
        raise BuildError("gaming NES smoke ROM mismatch")
    if sha256_file(payload / "files/retroarch.cfg") != RETROARCH_CONFIG_SHA256:
        raise BuildError("gaming RetroArch configuration mismatch")
    accepted_hotfixes = {
        "files/r46h-game-ui": GAME_UI_SHA256,
        "files/r46h-smoke-libretro.so": SMOKE_CORE_SHA256,
        "files/r46h-storage-audit": STORAGE_AUDIT_SHA256,
    }
    for relative, expected_sha256 in accepted_hotfixes.items():
        if sha256_file(payload / relative) != expected_sha256:
            raise BuildError(f"accepted gaming hotfix mismatch: {relative}")
    bridge = payload / "files/r46h-input-bridge"
    if require_regular(bridge, "product input bridge").st_size < 20_000:
        raise BuildError("product input bridge is unexpectedly small")


def load_profile() -> None:
    require_regular(PROFILE, "card profile")
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


def require_base_image(docker: str) -> None:
    result = subprocess.run(
        [
            docker,
            "--context",
            "desktop-linux",
            "image",
            "inspect",
            BASE_IMAGE,
            "--format",
            "{{.Id}} {{.Os}}/{{.Architecture}}",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    expected = f"{BASE_IMAGE_ID} linux/arm64"
    if result.returncode != 0 or result.stdout.strip() != expected:
        raise BuildError(f"base image mismatch: expected {expected!r}")


def validate_frozen_inputs(docker: str, extraction_root: Path) -> Path:
    load_profile()
    v08_metadata = require_regular(V08_FALLBACK_BUNDLE, "v0.8 fallback kernel bundle")
    if (
        v08_metadata.st_size != V08_FALLBACK_BUNDLE_SIZE
        or sha256_file(V08_FALLBACK_BUNDLE) != V08_FALLBACK_BUNDLE_SHA256
    ):
        raise BuildError("v0.8 fallback kernel bundle identity mismatch")
    v10_metadata = require_regular(V10_FALLBACK_BUNDLE, "v0.10 fallback kernel bundle")
    if (
        v10_metadata.st_size != V10_FALLBACK_BUNDLE_SIZE
        or sha256_file(V10_FALLBACK_BUNDLE) != V10_FALLBACK_BUNDLE_SHA256
    ):
        raise BuildError("v0.10 fallback kernel bundle identity mismatch")
    kernel_metadata = require_regular(KERNEL_BUNDLE, "v0.15 product kernel bundle")
    if (
        kernel_metadata.st_size != KERNEL_BUNDLE_SIZE
        or sha256_file(KERNEL_BUNDLE) != KERNEL_BUNDLE_SHA256
    ):
        raise BuildError("v0.15 product kernel bundle identity mismatch")
    gaming_metadata = require_regular(GAMING_ARCHIVE, "gaming v0.4 archive")
    if (
        gaming_metadata.st_size != GAMING_ARCHIVE_SIZE
        or sha256_file(GAMING_ARCHIVE) != GAMING_ARCHIVE_SHA256
    ):
        raise BuildError("gaming v0.4 archive identity mismatch")
    require_base_image(docker)
    payload = safe_extract_payload(GAMING_ARCHIVE, extraction_root)
    validate_payload(payload)
    return payload


def run_checked(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, check=False, text=True)
    if result.returncode != 0:
        raise BuildError(f"command exited {result.returncode}: {' '.join(command)}")
    return result


def run_captured(command: list[str], evidence: Path) -> None:
    result = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    write_new(evidence, result.stdout.encode("utf-8", errors="replace"))
    if result.stdout:
        print(result.stdout, end="")
    if result.returncode != 0:
        raise BuildError(f"command exited {result.returncode}: {' '.join(command)}")


def env_arguments(values: dict[str, str]) -> list[str]:
    arguments: list[str] = []
    for key, value in values.items():
        arguments.extend(("--env", f"{key}={value}"))
    return arguments


def build_environment(source_commit: str) -> dict[str, str]:
    return {
        "ARTIFACT_ID": ARTIFACT_ID,
        "BASE_IMAGE_ID": BASE_IMAGE_ID,
        "SOURCE_GIT_COMMIT": source_commit,
        "V08_FALLBACK_BUNDLE_SHA256": V08_FALLBACK_BUNDLE_SHA256,
        "V08_FALLBACK_MODULE_TREE_SHA256": V08_FALLBACK_MODULE_TREE_SHA256,
        "V10_FALLBACK_BUNDLE_SHA256": V10_FALLBACK_BUNDLE_SHA256,
        "V10_FALLBACK_MODULE_TREE_SHA256": V10_FALLBACK_MODULE_TREE_SHA256,
        "KERNEL_RELEASE": KERNEL_RELEASE,
        "KERNEL_BUNDLE_SHA256": KERNEL_BUNDLE_SHA256,
        "KERNEL_SOURCE_COMMIT": KERNEL_SOURCE_COMMIT,
        "KERNEL_SOURCE_SNAPSHOT_SHA256": KERNEL_SOURCE_SNAPSHOT_SHA256,
        "KERNEL_MODULE_TREE_SHA256": KERNEL_MODULE_TREE_SHA256,
        "KERNEL_IMAGE_SIZE": str(KERNEL_IMAGE_SIZE),
        "KERNEL_IMAGE_SHA256": KERNEL_IMAGE_SHA256,
        "KERNEL_DTB_SIZE": str(KERNEL_DTB_SIZE),
        "KERNEL_DTB_SHA256": KERNEL_DTB_SHA256,
        "PRODUCT_KERNEL_DIRECTORY": PRODUCT_KERNEL_DIRECTORY,
        "PRODUCT_UBOOT_COMMANDS_SHA256": PRODUCT_UBOOT_COMMANDS_SHA256,
        "GAMING_ARCHIVE_SHA256": GAMING_ARCHIVE_SHA256,
        "GAMING_PACKAGE_MANIFEST_SHA256": GAMING_PACKAGE_MANIFEST_SHA256,
        "GAMING_PAYLOAD_SHA256SUMS_SHA256": GAMING_PAYLOAD_SHA256SUMS_SHA256,
        "GAMING_RECEIPT_SHA256": GAMING_RECEIPT_SHA256,
        "GAME_UI_SHA256": GAME_UI_SHA256,
        "SMOKE_CORE_SHA256": SMOKE_CORE_SHA256,
        "STORAGE_AUDIT_SHA256": STORAGE_AUDIT_SHA256,
        "RETROARCH_CONFIG_SHA256": RETROARCH_CONFIG_SHA256,
        "NES_SMOKE_SHA256": NES_SMOKE_SHA256,
        "BASE_FIRSTBOOT_SHA256": BASE_FIRSTBOOT_SHA256,
        "FINAL_FIRSTBOOT_SHA256": FINAL_FIRSTBOOT_SHA256,
        "BASE_ROOTFS_SMOKE_SHA256": BASE_ROOTFS_SMOKE_SHA256,
        "FINAL_ROOTFS_SMOKE_SHA256": FINAL_ROOTFS_SMOKE_SHA256,
        "FS_UUID": FS_UUID,
    }


def compose_rootfs(
    docker: str,
    source: Path,
    payload: Path,
    work: Path,
    stage: Path,
    source_commit: str,
) -> Path:
    rootfs_tar = work / "rootfs.tar"
    create_command = [
        docker,
        "--context",
        "desktop-linux",
        "create",
        "--platform",
        "linux/arm64",
        "--network",
        "none",
        "--mount",
        f"type=bind,source={source},target=/run/r46h-build-source,readonly",
        "--mount",
        f"type=bind,source={payload},target=/run/r46h-gaming-payload,readonly",
        *env_arguments(build_environment(source_commit)),
        "--entrypoint",
        "/bin/bash",
        BASE_IMAGE,
        "/run/r46h-build-source/mainline/rootfs-debian13-gaming/compose-in-container.sh",
    ]
    created = subprocess.run(
        create_command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if created.returncode != 0 or re.fullmatch(r"[0-9a-f]{64}\n?", created.stdout) is None:
        raise BuildError(f"cannot create composition container: {created.stderr.strip()}")
    container = created.stdout.strip()
    try:
        run_captured(
            [docker, "--context", "desktop-linux", "start", "--attach", container],
            stage / "COMPOSE-VERIFY.txt",
        )
        run_checked(
            [
                docker,
                "--context",
                "desktop-linux",
                "export",
                "--output",
                str(rootfs_tar),
                container,
            ]
        )
    finally:
        subprocess.run(
            [docker, "--context", "desktop-linux", "rm", "-f", container],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    require_regular(rootfs_tar, "composed rootfs export")
    return rootfs_tar


def assemble_ext4(
    docker: str,
    source: Path,
    rootfs_tar: Path,
    work: Path,
    stage: Path,
    source_commit: str,
) -> None:
    input_directory = work / "input"
    input_directory.mkdir(mode=0o700)
    shutil.copyfile(rootfs_tar, input_directory / "rootfs.tar")
    shutil.copyfile(
        V08_FALLBACK_BUNDLE,
        input_directory / V08_FALLBACK_BUNDLE_NAME,
    )
    shutil.copyfile(V10_FALLBACK_BUNDLE, input_directory / V10_FALLBACK_BUNDLE_NAME)
    shutil.copyfile(KERNEL_BUNDLE, input_directory / KERNEL_BUNDLE_NAME)
    (input_directory / "rootfs.tar").chmod(0o400)
    (input_directory / V08_FALLBACK_BUNDLE_NAME).chmod(0o400)
    (input_directory / V10_FALLBACK_BUNDLE_NAME).chmod(0o400)
    (input_directory / KERNEL_BUNDLE_NAME).chmod(0o400)
    if (
        sha256_file(input_directory / V08_FALLBACK_BUNDLE_NAME)
        != V08_FALLBACK_BUNDLE_SHA256
    ):
        raise BuildError("private v0.8 fallback kernel bundle copy mismatch")
    if (
        sha256_file(input_directory / V10_FALLBACK_BUNDLE_NAME)
        != V10_FALLBACK_BUNDLE_SHA256
    ):
        raise BuildError("private v0.10 fallback kernel bundle copy mismatch")
    if sha256_file(input_directory / KERNEL_BUNDLE_NAME) != KERNEL_BUNDLE_SHA256:
        raise BuildError("private kernel bundle copy mismatch")

    volume = f"arkos4clone-r46h-gaming-v05-{source_commit[:12]}-{os.getpid()}"
    run_checked([docker, "--context", "desktop-linux", "volume", "create", volume])
    environment = {
        **build_environment(source_commit),
        "IMAGE_NAME": IMAGE_NAME,
        "PARTITION_SIZE": str(IMAGE_SIZE),
        "FS_BLOCK_SIZE": str(FS_BLOCK_SIZE),
        "FS_BLOCK_COUNT": str(FS_BLOCK_COUNT),
        "FS_TAIL_SIZE": str(FS_TAIL_SIZE),
        "FS_LABEL": FS_LABEL,
        "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH,
    }
    try:
        run_captured(
            [
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
                f"type=bind,source={input_directory},target=/input,readonly",
                "--mount",
                f"type=volume,source={volume},target=/work",
                "--mount",
                f"type=bind,source={stage},target=/output",
                *env_arguments(environment),
                "--entrypoint",
                "/bin/bash",
                BASE_IMAGE,
                "/source/mainline/rootfs-debian13-gaming/build-ext4-in-container.sh",
            ],
            stage / "ASSEMBLE-VERIFY.txt",
        )
    finally:
        subprocess.run(
            [docker, "--context", "desktop-linux", "volume", "rm", "-f", volume],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    # The final PASS is useful while running but is redundant with the retained
    # offline evidence and would otherwise expand the canonical file set.
    (stage / "ASSEMBLE-VERIFY.txt").unlink()


def require_ext4_superblock(path: Path) -> None:
    with path.open("rb", buffering=0) as handle:
        handle.seek(1024)
        superblock = handle.read(1024)
    if len(superblock) != 1024:
        raise BuildError("truncated ext4 superblock")
    blocks_lo = struct.unpack_from("<I", superblock, 0x04)[0]
    log_block_size = struct.unpack_from("<I", superblock, 0x18)[0]
    magic = struct.unpack_from("<H", superblock, 0x38)[0]
    state = struct.unpack_from("<H", superblock, 0x3A)[0]
    blocks_hi = struct.unpack_from("<I", superblock, 0x150)[0]
    block_count = blocks_lo | (blocks_hi << 32)
    block_size = 1024 << log_block_size if log_block_size < 32 else 0
    filesystem_uuid = str(uuid.UUID(bytes=superblock[0x68:0x78]))
    label = superblock[0x78:0x88].split(b"\0", 1)[0].decode("ascii")
    if magic != 0xEF53 or state != 0x0001:
        raise BuildError("ext4 superblock is invalid or unclean")
    if block_count != FS_BLOCK_COUNT or block_size != FS_BLOCK_SIZE:
        raise BuildError("ext4 superblock geometry mismatch")
    if filesystem_uuid != FS_UUID or label != FS_LABEL:
        raise BuildError("ext4 superblock identity mismatch")


def parse_build_info(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line or "=" not in line:
            raise BuildError(f"invalid BUILD-INFO line {line_number}")
        key, value = line.split("=", 1)
        if re.fullmatch(r"[A-Za-z0-9_]+", key) is None or not value or key in values:
            raise BuildError(f"invalid BUILD-INFO key on line {line_number}")
        values[key] = value
    return values


def write_build_metadata(
    stage: Path,
    source_commit: str,
    source_tree: str,
    source_manifest: bytes,
    image_sha256: str,
    docker_client: str,
    docker_server: str,
) -> None:
    write_new(stage / "SOURCE-MANIFEST.json", source_manifest)
    source_sums = []
    manifest = json.loads(source_manifest)
    for entry in manifest["files"]:
        source_sums.append(f"{entry['sha256']}  {entry['path']}\n")
    write_new(stage / "SOURCE-SHA256SUMS", "".join(source_sums).encode())
    write_new(
        stage / "INPUT-ARTIFACTS.sha256",
        (
            f"{V08_FALLBACK_BUNDLE_SHA256}  {V08_FALLBACK_BUNDLE_NAME}\n"
            f"{V10_FALLBACK_BUNDLE_SHA256}  {V10_FALLBACK_BUNDLE_NAME}\n"
            f"{KERNEL_BUNDLE_SHA256}  {KERNEL_BUNDLE_NAME}\n"
            f"{GAMING_ARCHIVE_SHA256}  {GAMING_ARCHIVE_NAME}\n"
        ).encode(),
    )
    values = {
        "artifact_id": ARTIFACT_ID,
        "artifact_status": "host-only-not-authorized-for-media-write",
        "distribution": "Debian GNU/Linux 13 (trixie)",
        "architecture": "arm64",
        "image_name": IMAGE_NAME,
        "image_size": str(IMAGE_SIZE),
        "image_sha256": image_sha256,
        "filesystem": "ext4",
        "filesystem_block_size": str(FS_BLOCK_SIZE),
        "filesystem_block_count": str(FS_BLOCK_COUNT),
        "filesystem_tail_zero_bytes": str(FS_TAIL_SIZE),
        "filesystem_uuid": FS_UUID,
        "filesystem_label": FS_LABEL,
        "root_partuuid": "c9f931c9-02",
        "base_image": BASE_IMAGE,
        "base_image_id": BASE_IMAGE_ID,
        "v08_fallback_release": V08_FALLBACK_RELEASE,
        "v08_fallback_bundle_sha256": V08_FALLBACK_BUNDLE_SHA256,
        "v08_fallback_module_tree_sha256": V08_FALLBACK_MODULE_TREE_SHA256,
        "v10_fallback_release": V10_FALLBACK_RELEASE,
        "v10_fallback_bundle_sha256": V10_FALLBACK_BUNDLE_SHA256,
        "v10_fallback_module_tree_sha256": V10_FALLBACK_MODULE_TREE_SHA256,
        "kernel_release": KERNEL_RELEASE,
        "kernel_bundle_sha256": KERNEL_BUNDLE_SHA256,
        "kernel_source_commit": KERNEL_SOURCE_COMMIT,
        "kernel_source_snapshot_sha256": KERNEL_SOURCE_SNAPSHOT_SHA256,
        "kernel_module_tree_sha256": KERNEL_MODULE_TREE_SHA256,
        "kernel_image_size": str(KERNEL_IMAGE_SIZE),
        "kernel_image_sha256": KERNEL_IMAGE_SHA256,
        "kernel_dtb_size": str(KERNEL_DTB_SIZE),
        "kernel_dtb_sha256": KERNEL_DTB_SHA256,
        "product_kernel_directory": PRODUCT_KERNEL_DIRECTORY,
        "product_uboot_commands_sha256": PRODUCT_UBOOT_COMMANDS_SHA256,
        "product_kernel_boot_mode": "p2-one-shot-no-saveenv",
        "gaming_payload_id": GAMING_PAYLOAD_ID,
        "gaming_source_commit": GAMING_SOURCE_COMMIT,
        "gaming_archive_sha256": GAMING_ARCHIVE_SHA256,
        "gaming_package_manifest_sha256": GAMING_PACKAGE_MANIFEST_SHA256,
        "gaming_payload_sha256sums_sha256": GAMING_PAYLOAD_SHA256SUMS_SHA256,
        "game_ui_sha256": GAME_UI_SHA256,
        "smoke_core_sha256": SMOKE_CORE_SHA256,
        "storage_audit_sha256": STORAGE_AUDIT_SHA256,
        "retroarch_config_sha256": RETROARCH_CONFIG_SHA256,
        "nes_smoke_sha256": NES_SMOKE_SHA256,
        "personal_authorized_keys": "absent",
        "diagnostic_input_bridge": "absent",
        "product_input_bridge": "r46h-gaming-input-bridge-v0.5",
        "source_git_commit": source_commit,
        "source_git_tree": source_tree,
        "source_manifest_sha256": sha256_bytes(source_manifest),
        "build_inputs_git_dirty": "false",
        "source_snapshot_method": "exact-committed-blobs",
        "source_date_epoch": SOURCE_DATE_EPOCH,
        "docker_context": "desktop-linux",
        "docker_client_version": docker_client,
        "docker_server_version": docker_server,
    }
    write_new(
        stage / "BUILD-INFO",
        "".join(f"{key}={value}\n" for key, value in values.items()).encode(),
    )


def validate_stage(stage: Path, expected_source_commit: str | None = None) -> str:
    require_directory(stage, "artifact directory")
    names = {entry.name for entry in stage.iterdir()}
    if names != REQUIRED_STAGE_FILES:
        raise BuildError(f"unexpected artifact file set: {sorted(names ^ REQUIRED_STAGE_FILES)}")
    for name in names:
        require_regular(stage / name, name)

    image = stage / IMAGE_NAME
    if image.stat().st_size != IMAGE_SIZE:
        raise BuildError("consolidated ext4 image size mismatch")
    require_ext4_superblock(image)
    with image.open("rb", buffering=0) as handle:
        handle.seek(-FS_TAIL_SIZE, os.SEEK_END)
        if handle.read(FS_TAIL_SIZE) != b"\0" * FS_TAIL_SIZE:
            raise BuildError("consolidated ext4 tail is not zero-filled")
    image_sha256 = sha256_file(image)
    if (stage / "EXT4-VERIFIED.sha256").read_text(encoding="utf-8") != (
        f"{image_sha256}  {IMAGE_NAME}\n"
    ):
        raise BuildError("post-verification image digest mismatch")

    build_info = parse_build_info(stage / "BUILD-INFO")
    expected = {
        "artifact_id": ARTIFACT_ID,
        "artifact_status": "host-only-not-authorized-for-media-write",
        "image_name": IMAGE_NAME,
        "image_size": str(IMAGE_SIZE),
        "image_sha256": image_sha256,
        "filesystem_uuid": FS_UUID,
        "filesystem_label": FS_LABEL,
        "root_partuuid": "c9f931c9-02",
        "base_image": BASE_IMAGE,
        "base_image_id": BASE_IMAGE_ID,
        "v08_fallback_release": V08_FALLBACK_RELEASE,
        "v08_fallback_bundle_sha256": V08_FALLBACK_BUNDLE_SHA256,
        "v08_fallback_module_tree_sha256": V08_FALLBACK_MODULE_TREE_SHA256,
        "v10_fallback_release": V10_FALLBACK_RELEASE,
        "v10_fallback_bundle_sha256": V10_FALLBACK_BUNDLE_SHA256,
        "v10_fallback_module_tree_sha256": V10_FALLBACK_MODULE_TREE_SHA256,
        "kernel_release": KERNEL_RELEASE,
        "kernel_bundle_sha256": KERNEL_BUNDLE_SHA256,
        "kernel_source_commit": KERNEL_SOURCE_COMMIT,
        "kernel_source_snapshot_sha256": KERNEL_SOURCE_SNAPSHOT_SHA256,
        "kernel_module_tree_sha256": KERNEL_MODULE_TREE_SHA256,
        "kernel_image_size": str(KERNEL_IMAGE_SIZE),
        "kernel_image_sha256": KERNEL_IMAGE_SHA256,
        "kernel_dtb_size": str(KERNEL_DTB_SIZE),
        "kernel_dtb_sha256": KERNEL_DTB_SHA256,
        "product_kernel_directory": PRODUCT_KERNEL_DIRECTORY,
        "product_uboot_commands_sha256": PRODUCT_UBOOT_COMMANDS_SHA256,
        "product_kernel_boot_mode": "p2-one-shot-no-saveenv",
        "gaming_payload_id": GAMING_PAYLOAD_ID,
        "gaming_source_commit": GAMING_SOURCE_COMMIT,
        "gaming_archive_sha256": GAMING_ARCHIVE_SHA256,
        "gaming_package_manifest_sha256": GAMING_PACKAGE_MANIFEST_SHA256,
        "gaming_payload_sha256sums_sha256": GAMING_PAYLOAD_SHA256SUMS_SHA256,
        "game_ui_sha256": GAME_UI_SHA256,
        "smoke_core_sha256": SMOKE_CORE_SHA256,
        "storage_audit_sha256": STORAGE_AUDIT_SHA256,
        "retroarch_config_sha256": RETROARCH_CONFIG_SHA256,
        "nes_smoke_sha256": NES_SMOKE_SHA256,
        "personal_authorized_keys": "absent",
        "diagnostic_input_bridge": "absent",
        "product_input_bridge": "r46h-gaming-input-bridge-v0.5",
        "build_inputs_git_dirty": "false",
        "source_snapshot_method": "exact-committed-blobs",
        "source_date_epoch": SOURCE_DATE_EPOCH,
        "docker_context": "desktop-linux",
    }
    for key, value in expected.items():
        if build_info.get(key) != value:
            raise BuildError(f"BUILD-INFO mismatch for {key}")
    if expected_source_commit and build_info.get("source_git_commit") != expected_source_commit:
        raise BuildError("BUILD-INFO source commit mismatch")
    for key in ("source_git_commit", "source_git_tree"):
        if re.fullmatch(r"[0-9a-f]{40}", build_info.get(key, "")) is None:
            raise BuildError(f"invalid BUILD-INFO Git identity: {key}")
    if SHA256_RE.fullmatch(build_info.get("source_manifest_sha256", "")) is None:
        raise BuildError("invalid BUILD-INFO source manifest digest")
    if build_info["source_manifest_sha256"] != sha256_file(stage / "SOURCE-MANIFEST.json"):
        raise BuildError("source manifest digest mismatch")

    required_markers = {
        "COMPOSE-VERIFY.txt": "R46H_GAMING_COMPOSE result=pass",
        "E2FSCK.txt": "R46H_E2FSCK_RESULT=pass",
        "SYSTEMD-VERIFY.txt": "R46H_SYSTEMD_VERIFY_RESULT=pass",
        "NESTOPIA-ROM-LOAD.txt": "Nestopia",
        "SMOKE-CORE-LOAD.txt": "R46H Hardware Smoke",
        "SMOKE-CORE-FILE.txt": "ARM aarch64",
        "RETROARCH-FEATURES.txt": "ALSA            - Audio driver: yes",
    }
    for name, marker in required_markers.items():
        if marker not in (stage / name).read_text(encoding="utf-8", errors="replace"):
            raise BuildError(f"missing retained build marker in {name}")
    for name in (
        "V08-KERNEL-BUNDLE-VERIFY.txt",
        "V10-KERNEL-BUNDLE-VERIFY.txt",
        "KERNEL-BUNDLE-VERIFY.txt",
    ):
        verification = (stage / name).read_text(encoding="utf-8", errors="replace")
        if not verification or "FAILED" in verification:
            raise BuildError(f"kernel bundle checksum evidence reports failure: {name}")
    if (stage / "DEBUGFS-GAMING.txt").read_text(
        encoding="utf-8", errors="replace"
    ).count("Type: regular") != 6:
        raise BuildError("debugfs gaming anchor count mismatch")
    if "FAILED" in (stage / "GAMING-PAYLOAD-VERIFY.txt").read_text(
        encoding="utf-8", errors="replace"
    ):
        raise BuildError("gaming payload checksum evidence reports failure")
    if "not found" in (stage / "RETROARCH-LDD.txt").read_text(
        encoding="utf-8", errors="replace"
    ):
        raise BuildError("RetroArch dependency evidence reports a missing library")

    input_artifacts = (stage / "INPUT-ARTIFACTS.sha256").read_text(encoding="utf-8")
    if input_artifacts != (
        f"{V08_FALLBACK_BUNDLE_SHA256}  {V08_FALLBACK_BUNDLE_NAME}\n"
        f"{V10_FALLBACK_BUNDLE_SHA256}  {V10_FALLBACK_BUNDLE_NAME}\n"
        f"{KERNEL_BUNDLE_SHA256}  {KERNEL_BUNDLE_NAME}\n"
        f"{GAMING_ARCHIVE_SHA256}  {GAMING_ARCHIVE_NAME}\n"
    ):
        raise BuildError("input artifact receipt mismatch")
    product_kernel_files = (stage / "PRODUCT-KERNEL-FILES.sha256").read_text(
        encoding="utf-8"
    )
    if product_kernel_files != (
        f"{KERNEL_IMAGE_SHA256}  {PRODUCT_KERNEL_RELATIVE}/IMAGE\n"
        f"{KERNEL_DTB_SHA256}  {PRODUCT_KERNEL_RELATIVE}/R46H.DTB\n"
        f"{PRODUCT_UBOOT_COMMANDS_SHA256}  {PRODUCT_KERNEL_RELATIVE}/UBOOT-CMDS.txt\n"
    ):
        raise BuildError("product kernel staging receipt mismatch")
    if sha256_file(stage / "GAMING-RECEIPT") != GAMING_RECEIPT_SHA256:
        raise BuildError("retained gaming receipt mismatch")
    consolidated_receipt = (stage / "CONSOLIDATED-RECEIPT").read_text(encoding="utf-8")
    for line in (
        f"artifact_id={ARTIFACT_ID}",
        f"v08_fallback_bundle_sha256={V08_FALLBACK_BUNDLE_SHA256}",
        f"v08_fallback_module_tree_sha256={V08_FALLBACK_MODULE_TREE_SHA256}",
        f"v10_fallback_bundle_sha256={V10_FALLBACK_BUNDLE_SHA256}",
        f"v10_fallback_module_tree_sha256={V10_FALLBACK_MODULE_TREE_SHA256}",
        f"kernel_release={KERNEL_RELEASE}",
        f"kernel_image_sha256={KERNEL_IMAGE_SHA256}",
        f"kernel_dtb_sha256={KERNEL_DTB_SHA256}",
        f"product_kernel_directory={PRODUCT_KERNEL_DIRECTORY}",
        f"game_ui_sha256={GAME_UI_SHA256}",
        f"smoke_core_sha256={SMOKE_CORE_SHA256}",
        f"storage_audit_sha256={STORAGE_AUDIT_SHA256}",
        f"retroarch_config_sha256={RETROARCH_CONFIG_SHA256}",
        "personal_authorized_keys=absent",
        "diagnostic_input_bridge=absent",
        "product_input_bridge=r46h-gaming-input-bridge-v0.5",
    ):
        if f"{line}\n" not in consolidated_receipt:
            raise BuildError("consolidated receipt boundary mismatch")
    if expected_source_commit and f"source_git_commit={expected_source_commit}\n" not in consolidated_receipt:
        raise BuildError("consolidated receipt source commit mismatch")

    packages = (stage / "PACKAGES.tsv").read_text(encoding="utf-8")
    for package in (
        "firmware-realtek",
        "libgl1-mesa-dri",
        "libretro-desmume",
        "libretro-gambatte",
        "libretro-mgba",
        "libretro-nestopia",
        "openssh-server",
        "retroarch",
        "systemd-sysv",
    ):
        if re.search(rf"^{re.escape(package)}(?:\t|:)", packages, re.MULTILINE) is None:
            raise BuildError(f"required consolidated package absent: {package}")
    if "libMali" in packages:
        raise BuildError("forbidden libMali package evidence")

    rootfs_files = (stage / "ROOTFS-FILES.sha256").read_text(
        encoding="utf-8", errors="surrogateescape"
    )
    for path in (
        "./etc/r46h/retroarch.cfg",
        "./etc/systemd/system/r46h-gaming-input.service",
        "./roms/nes/r46h-nes-smoke.nes",
        "./usr/local/libexec/r46h-input-bridge",
        "./usr/local/sbin/r46h-storage-audit",
        "./usr/share/r46h-build/CONSOLIDATED-RECEIPT",
        "./var/lib/r46h/gaming-mvp-v0.4-installed",
        f"./{PRODUCT_KERNEL_RELATIVE}/IMAGE",
        f"./{PRODUCT_KERNEL_RELATIVE}/R46H.DTB",
        f"./{PRODUCT_KERNEL_RELATIVE}/UBOOT-CMDS.txt",
    ):
        if f"  {path}\n" not in rootfs_files:
            raise BuildError(f"rootfs file evidence is missing {path}")
    for digest, path in (
        (GAME_UI_SHA256, "./usr/local/sbin/r46h-game-ui"),
        (SMOKE_CORE_SHA256, "./usr/local/libexec/r46h-smoke-libretro.so"),
        (STORAGE_AUDIT_SHA256, "./usr/local/sbin/r46h-storage-audit"),
    ):
        if f"{digest}  {path}\n" not in rootfs_files:
            raise BuildError(f"accepted gaming hotfix evidence mismatch: {path}")
    rootfs_tree = (stage / "ROOTFS-TREE.tsv").read_text(
        encoding="utf-8", errors="surrogateescape"
    )
    for release in (V08_FALLBACK_RELEASE, V10_FALLBACK_RELEASE, KERNEL_RELEASE):
        if f"\t./usr/lib/modules/{release}\t\n" not in rootfs_tree:
            raise BuildError(f"rootfs module tree evidence is missing {release}")
    for forbidden in (
        "./home/ark/.ssh/authorized_keys",
        "./var/lib/r46h/rom-workflow-v0.1-installed",
        "./var/lib/r46h/gaming-history-v0.2-installed",
        "r46h-gaming-input-bridge",
    ):
        if forbidden in rootfs_tree:
            raise BuildError(f"forbidden consolidated rootfs state: {forbidden}")

    sums = (stage / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    expected_names = sorted(REQUIRED_STAGE_FILES - {"SHA256SUMS"})
    if len(sums) != len(expected_names):
        raise BuildError("artifact checksum manifest length mismatch")
    for line, name in zip(sums, expected_names, strict=True):
        match = re.fullmatch(rf"([0-9a-f]{{64}})  {re.escape(name)}", line)
        if match is None:
            raise BuildError("artifact checksum manifest ordering or syntax mismatch")
        actual = image_sha256 if name == IMAGE_NAME else sha256_file(stage / name)
        if match.group(1) != actual:
            raise BuildError(f"artifact checksum mismatch: {name}")
    return image_sha256


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
        raise BuildError("unsafe consolidated rootfs staging directory")
    if OUTPUT_DIR.exists() or OUTPUT_DIR.is_symlink():
        raise BuildError(f"output already exists: {OUTPUT_DIR}")
    output_fd = os.open(OUTPUT_ROOT, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        rename_noreplace(output_fd, stage.name, OUTPUT_NAME)
    finally:
        os.close(output_fd)
    if stage.exists() or not OUTPUT_DIR.is_dir():
        raise BuildError("published output is not the validated staging directory")


def docker_versions(docker: str) -> tuple[str, str]:
    client = subprocess.run(
        [docker, "--context", "desktop-linux", "version", "--format", "{{.Client.Version}}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    server = subprocess.run(
        [docker, "--context", "desktop-linux", "version", "--format", "{{.Server.Version}}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if client.returncode != 0 or server.returncode != 0:
        raise BuildError("cannot query Docker versions")
    values = client.stdout.strip(), server.stdout.strip()
    if not all(re.fullmatch(r"[0-9A-Za-z._+-]+", value) for value in values):
        raise BuildError("invalid Docker version identity")
    return values


def command_build() -> Path:
    if OUTPUT_DIR.exists() or OUTPUT_DIR.is_symlink():
        raise BuildError(f"output already exists: {OUTPUT_DIR}")
    if shutil.disk_usage(OUTPUT_ROOT).free < 15 * 1024**3:
        raise BuildError("less than 15 GiB is available in the external workspace")
    source_commit, source_tree, captured, source_manifest = capture_clean_source()
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
        payload = validate_frozen_inputs(docker, work / "payload-extract")
        if (
            sha256_file(
                source / "mainline/rootfs-debian13-gaming/UBOOT-CMDS.product"
            )
            != PRODUCT_UBOOT_COMMANDS_SHA256
        ):
            raise BuildError("committed product U-Boot command identity mismatch")
        rootfs_tar = compose_rootfs(docker, source, payload, work, stage, source_commit)
        assemble_ext4(docker, source, rootfs_tar, work, stage, source_commit)

        image = stage / IMAGE_NAME
        require_regular(image, "consolidated ext4 image")
        if image.stat().st_size != IMAGE_SIZE:
            raise BuildError("consolidated image length mismatch")
        image_sha256 = sha256_file(image)
        if (stage / "EXT4-VERIFIED.sha256").read_text(encoding="utf-8") != (
            f"{image_sha256}  {IMAGE_NAME}\n"
        ):
            raise BuildError("host image digest differs from container verification")
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
            path = stage / name
            require_regular(path, name)
            digest = image_sha256 if name == IMAGE_NAME else sha256_file(path)
            digest_lines.append(f"{digest}  {name}\n")
        write_new(stage / "SHA256SUMS", "".join(digest_lines).encode())
        validate_stage(stage, source_commit)
        if git_bytes(["rev-parse", "--verify", "HEAD^{commit}"]).decode().strip() != source_commit:
            raise BuildError("HEAD changed during consolidated rootfs build")
        if git_bytes(
            ["status", "--porcelain=v1", "--untracked-files=all", "--", *SOURCE_PATHS]
        ):
            raise BuildError("consolidated rootfs source scope changed during build")
        publish(stage)
        published = True
        print("PASS: consolidated Debian 13 gaming product p2 v0.5 host artifact published.")
        print("STATUS=host-only-not-authorized-for-media-write")
        print(f"OUTPUT_DIR={OUTPUT_DIR}")
        print(f"IMAGE_SHA256={image_sha256}")
        return OUTPUT_DIR
    finally:
        if not published and stage.exists() and stage.parent == OUTPUT_ROOT:
            shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)


def command_validate_inputs() -> None:
    docker = docker_command()
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="preflight.", dir=CACHE_ROOT))
    try:
        validate_frozen_inputs(docker, work / "payload-extract")
        print(
            "PASS: frozen v0.8/v0.10 fallbacks, v0.15 product kernel, cumulative "
            "gaming v0.4 payload, base image and p2 geometry validated."
        )
    finally:
        shutil.rmtree(work, ignore_errors=True)


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
            image_sha256 = validate_stage(OUTPUT_DIR)
            print("PASS: consolidated Debian 13 gaming product p2 v0.5 artifact validated.")
            print(f"IMAGE_SHA256={image_sha256}")
    except (BuildError, OSError, tarfile.TarError, UnicodeDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
