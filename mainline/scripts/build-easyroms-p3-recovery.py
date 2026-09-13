#!/usr/bin/env python3
"""Build and raw-verify the full offline EASYROMS p3 recovery image."""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any


ARTIFACT_ID = "r46h-easyroms-p3-recovery-v1"
IMAGE_NAME = "easyroms-p3-recovery-v1.img"
EXPECTED_NAME = "EXPECTED-FILES.json"
PROFILE_ID = "hl-r46h-v22-g92-31719424000-v1"
IMAGE_SIZE = 20_868_328_960
SECTOR_SIZE = 512
CLUSTER_SIZE = 32_768
FAT_OFFSET_SECTORS = 2_048
FAT_LENGTH_SECTORS = 4_975
CLUSTER_HEAP_OFFSET_SECTORS = 8_192
CLUSTER_COUNT = 636_722
ROOT_DIRECTORY_CLUSTER = 6
VOLUME_LABEL = "EASYROMS"
VOLUME_GUID = "E1F5295C-4B12-A54A-ACB7-317194240001"
VOLUME_SERIAL = "52343648"
SOURCE_DATE_EPOCH = 1_785_369_600
BUILDER_IMAGE = "arkos4clone/r46h-debian13-p2-mvp:v0.1"
BUILDER_IMAGE_ID = "sha256:bd09bf6db6f1fb8f882621e98d70f01f976fd8dfba1bc897766afebd64cf51b9"
CONFIG_RELPATH = "mainline/p3-recovery/PAYLOAD-SOURCES.json"
CONTAINER_RELPATH = "mainline/p3-recovery/build-image-in-container.sh"
VERIFIER_RELPATH = "mainline/scripts/verify-exfat-image.py"
BUILDER_RELPATH = "mainline/scripts/build-easyroms-p3-recovery.py"
PLAN_RELPATH = "mainline/scripts/generate-easyroms-p3-write-plan.py"
TRACKED_INPUTS = {
    CONFIG_RELPATH: "100644",
    CONTAINER_RELPATH: "100755",
    VERIFIER_RELPATH: "100755",
    BUILDER_RELPATH: "100755",
    PLAN_RELPATH: "100755",
}

FAST_CARD_VARIANT = {
    "artifact_id": "r46h-easyroms-p3-62534975488-v1",
    "image_name": "easyroms-p3-62534975488-v1.img",
    "profile_id": "hl-r46h-v22-g92-62534975488-v1",
    "image_size": 51_683_880_448,
    "fat_length_sectors": 12_321,
    "cluster_heap_offset_sectors": 16_384,
    "cluster_count": 1_577_010,
    "root_directory_cluster": 10,
    "volume_guid": "62534975-4880-4A4A-ACB7-625349754881",
    "volume_serial": "62534975",
    "config_relpath": "mainline/p3-recovery/PAYLOAD-SOURCES-62534975488.json",
    "container_relpath": "mainline/p3-recovery/build-image-62534975488-in-container.sh",
}


def select_variant(name: str) -> None:
    global ARTIFACT_ID, IMAGE_NAME, PROFILE_ID, IMAGE_SIZE
    global FAT_LENGTH_SECTORS, CLUSTER_HEAP_OFFSET_SECTORS, CLUSTER_COUNT
    global ROOT_DIRECTORY_CLUSTER, VOLUME_GUID, VOLUME_SERIAL
    global CONFIG_RELPATH, CONTAINER_RELPATH, TRACKED_INPUTS
    if name == "compact":
        return
    if name != "fast-card-62534975488":
        raise BuildError(f"unsupported p3 build variant: {name}")
    ARTIFACT_ID = FAST_CARD_VARIANT["artifact_id"]
    IMAGE_NAME = FAST_CARD_VARIANT["image_name"]
    PROFILE_ID = FAST_CARD_VARIANT["profile_id"]
    IMAGE_SIZE = FAST_CARD_VARIANT["image_size"]
    FAT_LENGTH_SECTORS = FAST_CARD_VARIANT["fat_length_sectors"]
    CLUSTER_HEAP_OFFSET_SECTORS = FAST_CARD_VARIANT["cluster_heap_offset_sectors"]
    CLUSTER_COUNT = FAST_CARD_VARIANT["cluster_count"]
    ROOT_DIRECTORY_CLUSTER = FAST_CARD_VARIANT["root_directory_cluster"]
    VOLUME_GUID = FAST_CARD_VARIANT["volume_guid"]
    VOLUME_SERIAL = FAST_CARD_VARIANT["volume_serial"]
    CONFIG_RELPATH = FAST_CARD_VARIANT["config_relpath"]
    CONTAINER_RELPATH = FAST_CARD_VARIANT["container_relpath"]
    TRACKED_INPUTS = {
        CONFIG_RELPATH: "100644",
        CONTAINER_RELPATH: "100755",
        VERIFIER_RELPATH: "100755",
        BUILDER_RELPATH: "100755",
    }
CONFIG_KEYS = {
    "artifact_id",
    "builder_image",
    "builder_image_id",
    "cluster_count",
    "cluster_heap_offset_sectors",
    "cluster_size",
    "fat_length_sectors",
    "fat_offset_sectors",
    "format_version",
    "image_name",
    "image_size",
    "payloads",
    "profile_id",
    "root_directory_cluster",
    "sector_size",
    "source_date_epoch",
    "volume_guid",
    "volume_label",
    "volume_serial",
}
PAYLOAD_KEYS = {
    "action_policy",
    "build_id",
    "destination",
    "manifest_sha256",
    "source_bundle",
    "source_git_commit",
    "stage_complete_sha256",
    "stage_sources_sha256",
}
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
NAME_RE = re.compile(r"^[A-Za-z0-9._+-]+$")
MAX_PAYLOAD_FILE_SIZE = 512 * 1024 * 1024
MAX_TEXT_SIZE = 4 * 1024 * 1024


class BuildError(RuntimeError):
    pass


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


def require_regular(path: Path, label: str, *, owner: int | None = None) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise BuildError(f"missing {label}: {path}") from exc
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or (owner is not None and metadata.st_uid != owner)
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise BuildError(f"unsafe {label}: {path}")
    return metadata


def read_pinned(path: Path, label: str, maximum_size: int) -> tuple[bytes, tuple[int, ...]]:
    named = require_regular(path, label, owner=os.getuid())
    if named.st_size <= 0 or named.st_size > maximum_size:
        raise BuildError(f"unsafe {label} size: {path}")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        identity = stable_identity(opened)
        if identity != stable_identity(named):
            raise BuildError(f"{label} changed before open")
        output = bytearray()
        while len(output) < opened.st_size:
            block = os.read(descriptor, min(1024 * 1024, opened.st_size - len(output)))
            if not block:
                raise BuildError(f"short read from {label}")
            output.extend(block)
        if stable_identity(os.fstat(descriptor)) != identity:
            raise BuildError(f"{label} changed during read")
        return bytes(output), identity
    finally:
        os.close(descriptor)


def sha256_pinned(path: Path, label: str, expected_size: int | None = None) -> tuple[str, tuple[int, ...]]:
    named = require_regular(path, label, owner=os.getuid())
    if expected_size is not None and named.st_size != expected_size:
        raise BuildError(f"{label} size mismatch")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        identity = stable_identity(opened)
        if identity != stable_identity(named):
            raise BuildError(f"{label} changed before hashing")
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(descriptor, 4 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
            total += len(block)
        if total != opened.st_size or stable_identity(os.fstat(descriptor)) != identity:
            raise BuildError(f"{label} changed during hashing")
        return digest.hexdigest(), identity
    finally:
        os.close(descriptor)


def write_new(path: Path, data: bytes, mode: int = 0o600) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        mode,
    )
    try:
        offset = 0
        while offset < len(data):
            written = os.write(descriptor, data[offset:])
            if written <= 0:
                raise BuildError(f"short write: {path.name}")
            offset += written
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise BuildError(f"unsafe output identity: {path.name}")
    finally:
        os.close(descriptor)


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise BuildError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_config(path: Path) -> tuple[dict[str, Any], str]:
    raw, _ = read_pinned(path, "p3 payload-source configuration", MAX_TEXT_SIZE)
    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicate_pairs)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise BuildError("malformed p3 payload-source configuration") from exc
    if not isinstance(value, dict) or set(value) != CONFIG_KEYS:
        raise BuildError("p3 payload-source configuration key set mismatch")
    expected = {
        "artifact_id": ARTIFACT_ID,
        "builder_image": BUILDER_IMAGE,
        "builder_image_id": BUILDER_IMAGE_ID,
        "cluster_count": CLUSTER_COUNT,
        "cluster_heap_offset_sectors": CLUSTER_HEAP_OFFSET_SECTORS,
        "cluster_size": CLUSTER_SIZE,
        "fat_length_sectors": FAT_LENGTH_SECTORS,
        "fat_offset_sectors": FAT_OFFSET_SECTORS,
        "format_version": 1,
        "image_name": IMAGE_NAME,
        "image_size": IMAGE_SIZE,
        "profile_id": PROFILE_ID,
        "root_directory_cluster": ROOT_DIRECTORY_CLUSTER,
        "sector_size": SECTOR_SIZE,
        "source_date_epoch": SOURCE_DATE_EPOCH,
        "volume_guid": VOLUME_GUID,
        "volume_label": VOLUME_LABEL,
        "volume_serial": VOLUME_SERIAL,
    }
    for key, expected_value in expected.items():
        if value.get(key) != expected_value:
            raise BuildError(f"p3 payload-source configuration mismatch: {key}")
    payloads = value.get("payloads")
    if not isinstance(payloads, list) or len(payloads) != 3:
        raise BuildError("p3 payload-source configuration must contain three payloads")
    destinations: list[str] = []
    for item in payloads:
        if not isinstance(item, dict) or set(item) != PAYLOAD_KEYS:
            raise BuildError("p3 payload-source entry key set mismatch")
        if any(not isinstance(item.get(key), str) or not item[key] for key in PAYLOAD_KEYS):
            raise BuildError("p3 payload-source entry contains a non-string value")
        if (
            NAME_RE.fullmatch(item["destination"]) is None
            or NAME_RE.fullmatch(item["build_id"]) is None
            or item["action_policy"] not in {"legacy-full", "install-modules-only"}
            or not item["source_bundle"].startswith("mainline/out/")
            or ".." in Path(item["source_bundle"]).parts
            or re.fullmatch(r"[0-9a-f]{40}", item["source_git_commit"]) is None
            or any(
                SHA_RE.fullmatch(item[key]) is None
                for key in (
                    "manifest_sha256",
                    "stage_complete_sha256",
                    "stage_sources_sha256",
                )
            )
        ):
            raise BuildError("p3 payload-source entry identity is malformed")
        destinations.append(item["destination"])
    if destinations != [
        "r46h-v0.8-bootloader-handoff",
        "r46h-v0.9-adc-joystick-fix",
        "r46h-v0.10-adc-full-range",
    ]:
        raise BuildError("p3 payload destination order or identity mismatch")
    return value, hashlib.sha256(raw).hexdigest()


def run(command: list[str], *, timeout: int = 1800) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise BuildError(f"command timed out: {' '.join(command[:3])}") from exc


def require_git_inputs(repo_root: Path) -> tuple[str, str, dict[str, str]]:
    for command, label in (
        (["git", "-C", str(repo_root), "diff", "--quiet"], "unstaged"),
        (["git", "-C", str(repo_root), "diff", "--cached", "--quiet"], "staged"),
    ):
        if run(command, timeout=60).returncode != 0:
            raise BuildError(f"tracked worktree contains {label} changes")
    head_result = run(["git", "-C", str(repo_root), "rev-parse", "HEAD"], timeout=60)
    head = head_result.stdout.decode("ascii", "strict").strip()
    if head_result.returncode != 0 or re.fullmatch(r"[0-9a-f]{40}", head) is None:
        raise BuildError("cannot resolve source Git commit")
    hashes: dict[str, str] = {}
    for relative, expected_mode in TRACKED_INPUTS.items():
        live_path = repo_root / relative
        live, _ = read_pinned(live_path, f"tracked build input {relative}", MAX_TEXT_SIZE)
        blob = run(["git", "-C", str(repo_root), "show", f"{head}:{relative}"], timeout=60)
        if blob.returncode != 0 or blob.stdout != live:
            raise BuildError(f"tracked build input does not match HEAD: {relative}")
        tree = run(["git", "-C", str(repo_root), "ls-tree", head, "--", relative], timeout=60)
        text = tree.stdout.decode("utf-8", "strict").strip()
        if tree.returncode != 0 or not text.startswith(f"{expected_mode} blob ") or not text.endswith(f"\t{relative}"):
            raise BuildError(f"tracked build-input mode mismatch: {relative}")
        hashes[relative] = hashlib.sha256(live).hexdigest()
    archive = run(["git", "-C", str(repo_root), "archive", "--format=tar", head], timeout=300)
    if archive.returncode != 0:
        raise BuildError("cannot compute canonical Git archive")
    return head, hashlib.sha256(archive.stdout).hexdigest(), hashes


def parse_stage_sums(raw: bytes) -> dict[str, str]:
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise BuildError("STAGE-SOURCES.sha256 is not UTF-8") from exc
    values: dict[str, str] = {}
    for line_number, line in enumerate(lines, 1):
        match = re.fullmatch(r"([0-9a-f]{64})  payload/([A-Za-z0-9._+-]+)", line)
        if match is None:
            raise BuildError(f"malformed STAGE-SOURCES.sha256 line {line_number}")
        digest, name = match.groups()
        if name in values:
            raise BuildError(f"duplicate staged payload file: {name}")
        values[name] = digest
    if list(values) != sorted(values) or not values:
        raise BuildError("STAGE-SOURCES.sha256 is empty or unsorted")
    return values


def parse_manifest(raw: bytes) -> dict[str, str]:
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise BuildError("DEPLOY-MANIFEST is not UTF-8") from exc
    values: dict[str, str] = {}
    for line in lines:
        if not line or "=" not in line:
            raise BuildError("DEPLOY-MANIFEST contains a malformed line")
        key, value = line.split("=", 1)
        if re.fullmatch(r"[a-z][a-z0-9_]*", key) is None or not value or key in values:
            raise BuildError("DEPLOY-MANIFEST contains an invalid field")
        values[key] = value
    return values


def safe_source_bundle(repo_root: Path, relative: str) -> tuple[Path, Path]:
    out_root = (repo_root / "mainline/out").resolve(strict=True)
    named = repo_root / relative
    if named.is_symlink():
        raise BuildError("payload source bundle is a symlink")
    bundle = named.resolve(strict=True)
    if out_root not in bundle.parents:
        raise BuildError("payload source bundle leaves mainline/out")
    metadata = bundle.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise BuildError("payload source bundle directory is unsafe")
    entries = {entry.name for entry in os.scandir(bundle)}
    if entries != {"payload", "STAGE-SOURCES.sha256", "stage-on-macos.sh"}:
        raise BuildError("payload source bundle root entry set mismatch")
    payload = bundle / "payload"
    payload_metadata = payload.lstat()
    if payload.is_symlink() or not stat.S_ISDIR(payload_metadata.st_mode):
        raise BuildError("payload source directory is unsafe")
    return bundle, payload


def copy_pinned(source: Path, destination: Path, expected_digest: str) -> dict[str, object]:
    named = require_regular(source, f"payload source {source.name}", owner=os.getuid())
    if named.st_size <= 0 or named.st_size > MAX_PAYLOAD_FILE_SIZE:
        raise BuildError(f"payload source size is unsafe: {source.name}")
    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    destination_fd = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        opened = os.fstat(source_fd)
        identity = stable_identity(opened)
        if identity != stable_identity(named):
            raise BuildError(f"payload source changed before open: {source.name}")
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(source_fd, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            total += len(block)
            offset = 0
            while offset < len(block):
                written = os.write(destination_fd, block[offset:])
                if written <= 0:
                    raise BuildError(f"short frozen payload write: {source.name}")
                offset += written
        os.fsync(destination_fd)
        if total != opened.st_size or stable_identity(os.fstat(source_fd)) != identity:
            raise BuildError(f"payload source changed during freeze: {source.name}")
        actual = digest.hexdigest()
        if actual != expected_digest:
            raise BuildError(f"payload source checksum mismatch: {source.name}")
        frozen = os.fstat(destination_fd)
        if not stat.S_ISREG(frozen.st_mode) or frozen.st_nlink != 1 or frozen.st_size != total:
            raise BuildError(f"frozen payload identity mismatch: {source.name}")
        return {"name": source.name, "size": total, "sha256": actual}
    finally:
        os.close(destination_fd)
        os.close(source_fd)


def validate_manifest_policy(spec: dict[str, str], manifest: dict[str, str], names: set[str]) -> None:
    if (
        manifest.get("format_version") != "3"
        or manifest.get("target") != "HL-R46H-V22"
        or manifest.get("build_id") != spec["build_id"]
        or manifest.get("payload_name") != spec["destination"]
        or manifest.get("source_git_commit") != spec["source_git_commit"]
    ):
        raise BuildError(f"payload DEPLOY-MANIFEST identity mismatch: {spec['destination']}")
    if spec["action_policy"] == "install-modules-only":
        if (
            manifest.get("action_policy") != "install-modules-only"
            or manifest.get("allowed_actions") != "install-modules"
            or manifest.get("target_boot_switch") != "disabled"
            or "switch-boot.sh" in names
        ):
            raise BuildError(f"modules-only policy mismatch: {spec['destination']}")
    elif "switch-boot.sh" not in names or manifest.get("target_boot_switch") != "switch-boot.sh":
        raise BuildError("legacy v0.8 payload no longer contains its historical switch anchor")


def freeze_payload(
    repo_root: Path, spec: dict[str, str], destination_root: Path
) -> dict[str, object]:
    bundle, payload = safe_source_bundle(repo_root, spec["source_bundle"])
    sums_raw, _ = read_pinned(bundle / "STAGE-SOURCES.sha256", "STAGE-SOURCES.sha256", MAX_TEXT_SIZE)
    if hashlib.sha256(sums_raw).hexdigest() != spec["stage_sources_sha256"]:
        raise BuildError(f"source-list checksum mismatch: {spec['destination']}")
    sums = parse_stage_sums(sums_raw)
    names = {entry.name for entry in os.scandir(payload)}
    if names != set(sums):
        raise BuildError(f"payload file set mismatch: {spec['destination']}")
    manifest_raw, _ = read_pinned(payload / "DEPLOY-MANIFEST", "DEPLOY-MANIFEST", MAX_TEXT_SIZE)
    complete_raw, _ = read_pinned(payload / "STAGE-COMPLETE", "STAGE-COMPLETE", MAX_TEXT_SIZE)
    if hashlib.sha256(manifest_raw).hexdigest() != spec["manifest_sha256"]:
        raise BuildError(f"DEPLOY-MANIFEST checksum mismatch: {spec['destination']}")
    if hashlib.sha256(complete_raw).hexdigest() != spec["stage_complete_sha256"]:
        raise BuildError(f"STAGE-COMPLETE checksum mismatch: {spec['destination']}")
    validate_manifest_policy(spec, parse_manifest(manifest_raw), names)
    destination = destination_root / spec["destination"]
    destination.mkdir(mode=0o700)
    files = [
        copy_pinned(payload / name, destination / name, digest)
        for name, digest in sums.items()
    ]
    return {
        "action_policy": spec["action_policy"],
        "build_id": spec["build_id"],
        "destination": spec["destination"],
        "source_bundle": spec["source_bundle"],
        "source_git_commit": spec["source_git_commit"],
        "stage_sources_sha256": spec["stage_sources_sha256"],
        "manifest_sha256": spec["manifest_sha256"],
        "stage_complete_sha256": spec["stage_complete_sha256"],
        "files": files,
    }


def revalidate_live_payload(repo_root: Path, spec: dict[str, str], binding: dict[str, object]) -> None:
    bundle, payload = safe_source_bundle(repo_root, spec["source_bundle"])
    sums_raw, _ = read_pinned(bundle / "STAGE-SOURCES.sha256", "STAGE-SOURCES.sha256", MAX_TEXT_SIZE)
    if hashlib.sha256(sums_raw).hexdigest() != spec["stage_sources_sha256"]:
        raise BuildError(f"live source list drifted: {spec['destination']}")
    sums = parse_stage_sums(sums_raw)
    if {entry.name for entry in os.scandir(payload)} != set(sums):
        raise BuildError(f"live payload file set drifted: {spec['destination']}")
    expected_files = {item["name"]: item for item in binding["files"]}  # type: ignore[index]
    if set(expected_files) != set(sums):
        raise BuildError("frozen payload binding is internally inconsistent")
    for name, digest in sums.items():
        actual, identity = sha256_pinned(payload / name, f"live payload {name}")
        if actual != digest or expected_files[name] != {
            "name": name,
            "size": identity[6],
            "sha256": digest,
        }:
            raise BuildError(f"live payload drifted after build: {spec['destination']}/{name}")


def require_docker() -> str:
    docker = shutil.which("docker")
    if docker is None:
        raise BuildError("Docker is required for the offline exFAT build")
    inspection = run(
        [docker, "image", "inspect", BUILDER_IMAGE, "--format", "{{.Id}} {{.Architecture}} {{.Os}}"],
        timeout=60,
    )
    expected = f"{BUILDER_IMAGE_ID} arm64 linux"
    if inspection.returncode != 0 or inspection.stdout.decode("utf-8", "strict").strip() != expected:
        raise BuildError("pinned p3 builder image identity mismatch")
    return docker


def expected_manifest(bindings: list[dict[str, object]]) -> dict[str, object]:
    directories = sorted(str(binding["destination"]) for binding in bindings)
    files: list[dict[str, object]] = []
    for binding in bindings:
        destination = str(binding["destination"])
        for item in binding["files"]:  # type: ignore[union-attr]
            files.append(
                {
                    "path": f"{destination}/{item['name']}",
                    "size": item["size"],
                    "sha256": item["sha256"],
                }
            )
    files.sort(key=lambda item: str(item["path"]))
    return {
        "cluster_count": CLUSTER_COUNT,
        "cluster_heap_offset_sectors": CLUSTER_HEAP_OFFSET_SECTORS,
        "cluster_size": CLUSTER_SIZE,
        "directories": directories,
        "fat_length_sectors": FAT_LENGTH_SECTORS,
        "fat_offset_sectors": FAT_OFFSET_SECTORS,
        "files": files,
        "format_version": 1,
        "image_size": IMAGE_SIZE,
        "root_directory_cluster": ROOT_DIRECTORY_CLUSTER,
        "sector_size": SECTOR_SIZE,
        "volume_guid": VOLUME_GUID,
        "volume_label": VOLUME_LABEL,
        "volume_serial": VOLUME_SERIAL,
    }


def run_logged(command: list[str], log: Path, *, timeout: int = 1800) -> bytes:
    result = run(command, timeout=timeout)
    write_new(log, result.stdout)
    if result.returncode != 0:
        raise BuildError(f"command failed ({result.returncode}): {' '.join(command[:3])}")
    return result.stdout


def rename_noreplace(parent: Path, source: str, destination: str) -> None:
    if NAME_RE.fullmatch(source) is None or NAME_RE.fullmatch(destination) is None:
        raise BuildError("unsafe atomic publication name")
    descriptor = os.open(parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        before = os.fstat(descriptor)
        source_metadata = os.stat(source, dir_fd=descriptor, follow_symlinks=False)
        if not stat.S_ISDIR(source_metadata.st_mode):
            raise BuildError("private publication source is not a directory")
        libc_name = ctypes.util.find_library("c")
        if libc_name is None:
            raise BuildError("cannot resolve libc for no-replace publication")
        libc = ctypes.CDLL(libc_name, use_errno=True)
        function = getattr(libc, "renameatx_np", None)
        if function is None:
            raise BuildError("renameatx_np is unavailable on this host")
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        function.restype = ctypes.c_int
        if function(descriptor, os.fsencode(source), descriptor, os.fsencode(destination), 0x00000004) != 0:
            error_number = ctypes.get_errno()
            if error_number == 17:
                raise BuildError("p3 recovery output already exists")
            raise BuildError(f"atomic no-replace publication failed: errno={error_number}")
        published = os.stat(destination, dir_fd=descriptor, follow_symlinks=False)
        after = os.fstat(descriptor)
        if (
            (published.st_dev, published.st_ino) != (source_metadata.st_dev, source_metadata.st_ino)
            or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
        ):
            raise BuildError("atomic publication identity mismatch")
    finally:
        os.close(descriptor)


def require_output_parent(repo_root: Path, requested: Path | None) -> Path:
    out_root = (repo_root / "mainline/out").resolve(strict=True)
    parent = requested or repo_root / "mainline/out/r46h-p3-recovery-images"
    parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if parent.is_symlink():
        raise BuildError("p3 output parent is a symlink")
    resolved = parent.resolve(strict=True)
    if resolved != out_root and out_root not in resolved.parents:
        raise BuildError("p3 output parent leaves mainline/out")
    metadata = resolved.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise BuildError("p3 output parent is unsafe")
    return resolved


def build(repo_root: Path, output_parent: Path | None) -> Path:
    head, archive_sha, tracked_hashes = require_git_inputs(repo_root)
    config, config_sha = load_config(repo_root / CONFIG_RELPATH)
    docker = require_docker()
    parent = require_output_parent(repo_root, output_parent)
    final = parent / ARTIFACT_ID
    if final.exists() or final.is_symlink():
        raise BuildError(f"p3 recovery output already exists: {final}")
    stage = Path(tempfile.mkdtemp(prefix=".r46h-p3-recovery.", dir=parent))
    stage.chmod(0o700)
    published = False
    try:
        source_root = stage / "source"
        source_root.mkdir(mode=0o700)
        bindings = [freeze_payload(repo_root, spec, source_root) for spec in config["payloads"]]
        source_bindings = {
            "format_version": 1,
            "payloads": bindings,
        }
        write_new(stage / "SOURCE-BINDINGS.json", canonical_json(source_bindings))
        expected = expected_manifest(bindings)
        write_new(stage / EXPECTED_NAME, canonical_json(expected))

        container_source = repo_root / CONTAINER_RELPATH
        container_bytes, _ = read_pinned(container_source, "container build script", MAX_TEXT_SIZE)
        write_new(stage / "build-image-in-container.sh", container_bytes, 0o700)
        image = stage / IMAGE_NAME
        descriptor = os.open(
            image,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            os.ftruncate(descriptor, IMAGE_SIZE)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

        container_log = stage / "CONTAINER-BUILD.log"
        output = run_logged(
            [
                docker,
                "run",
                "--rm",
                "--network",
                "none",
                "--privileged",
                "--mount",
                f"type=bind,src={stage},dst=/work",
                "--entrypoint",
                "/bin/bash",
                BUILDER_IMAGE_ID,
                "/work/build-image-in-container.sh",
            ],
            container_log,
        )
        marker = (
            f"R46H_P3_CONTAINER_BUILD result=pass image_size={IMAGE_SIZE} "
            f"volume_guid={VOLUME_GUID}\n"
        ).encode()
        if output.count(marker) != 1:
            raise BuildError("container build lacks its unique PASS marker")

        loop_check = run(
            [
                docker,
                "run",
                "--rm",
                "--network",
                "none",
                "--privileged",
                "--mount",
                f"type=bind,src={stage},dst=/work",
                BUILDER_IMAGE_ID,
                "losetup",
                "-j",
                f"/work/{IMAGE_NAME}",
            ],
            timeout=120,
        )
        if loop_check.returncode != 0 or loop_check.stdout.strip():
            raise BuildError("container loop device remained attached after build")

        raw_report = stage / "RAW-VERIFY.json"
        normalize = run(
            [
                sys.executable,
                "-B",
                str(repo_root / VERIFIER_RELPATH),
                "--image",
                str(image),
                "--expected-manifest",
                str(stage / EXPECTED_NAME),
                "--normalize-source-date-epoch",
                str(SOURCE_DATE_EPOCH),
                "--report",
                str(raw_report),
            ]
        )
        if normalize.returncode != 0:
            raise BuildError(f"raw exFAT normalization/verification failed: {normalize.stdout.decode(errors='replace')}")
        try:
            raw_value = json.loads(raw_report.read_bytes())
        except (json.JSONDecodeError, OSError) as exc:
            raise BuildError("raw verification report is malformed") from exc
        expected_file_count = sum(len(binding["files"]) for binding in bindings)  # type: ignore[arg-type]
        if (
            raw_value.get("result") != "pass"
            or raw_value.get("allocation_bitmap_exact") is not True
            or raw_value.get("overlapping_clusters") != 0
            or raw_value.get("deleted_entries") != 0
            or raw_value.get("volume_serial") != VOLUME_SERIAL
            or raw_value.get("timestamps_normalized_to_epoch") != SOURCE_DATE_EPOCH
            or raw_value.get("normalized_entry_count") != expected_file_count + len(bindings)
            or len(raw_value.get("files", [])) != expected_file_count
        ):
            raise BuildError("raw verification report safety gates mismatch")

        fsck_log = stage / "POST-NORMALIZE-FSCK.log"
        run_logged(
            [
                docker,
                "run",
                "--rm",
                "--network",
                "none",
                "--mount",
                f"type=bind,src={stage},dst=/work,readonly",
                BUILDER_IMAGE_ID,
                "fsck.exfat",
                "-n",
                "-v",
                f"/work/{IMAGE_NAME}",
            ],
            fsck_log,
            timeout=600,
        )

        image_sha, image_identity = sha256_pinned(image, "complete p3 recovery image", IMAGE_SIZE)
        second = run(
            [
                sys.executable,
                "-B",
                str(repo_root / VERIFIER_RELPATH),
                "--image",
                str(image),
                "--expected-manifest",
                str(stage / EXPECTED_NAME),
            ]
        )
        if second.returncode != 0:
            raise BuildError("second read-only raw exFAT verification failed")
        image_sha_after, image_identity_after = sha256_pinned(
            image, "complete p3 recovery image", IMAGE_SIZE
        )
        if image_sha_after != image_sha or image_identity_after != image_identity:
            raise BuildError("p3 recovery image changed during final verification")

        for spec, binding in zip(config["payloads"], bindings):
            revalidate_live_payload(repo_root, spec, binding)
            frozen = source_root / str(binding["destination"])
            for item in binding["files"]:  # type: ignore[union-attr]
                digest, _ = sha256_pinned(frozen / item["name"], "frozen payload")
                if digest != item["sha256"]:
                    raise BuildError("frozen payload changed during image build")
        head_after, archive_after, tracked_after = require_git_inputs(repo_root)
        if (head_after, archive_after, tracked_after) != (head, archive_sha, tracked_hashes):
            raise BuildError("tracked source provenance changed during image build")

        shutil.rmtree(source_root)
        (stage / "build-image-in-container.sh").unlink()
        expected_sha = hashlib.sha256((stage / EXPECTED_NAME).read_bytes()).hexdigest()
        raw_sha = hashlib.sha256(raw_report.read_bytes()).hexdigest()
        status = {
            "allocation_bitmap_exact": True,
            "artifact_id": ARTIFACT_ID,
            "block_devices_opened": 0,
            "builder_image": BUILDER_IMAGE,
            "builder_image_id": BUILDER_IMAGE_ID,
            "cluster_size": CLUSTER_SIZE,
            "container_loop_devices_after": 0,
            "deleted_entries": 0,
            "directory_count": len(bindings),
            "expected_manifest_sha256": expected_sha,
            "file_count": expected_file_count,
            "filesystem": "exfat",
            "format_version": 1,
            "image_name": IMAGE_NAME,
            "image_sha256": image_sha,
            "image_size": IMAGE_SIZE,
            "macos_fskit_used": False,
            "overlapping_clusters": 0,
            "payload_config_sha256": config_sha,
            "physical_devices_accessed": 0,
            "post_normalize_fsck_read_only_passed": True,
            "profile_id": PROFILE_ID,
            "raw_verification_sha256": raw_sha,
            "raw_verification_twice_passed": True,
            "sector_size": SECTOR_SIZE,
            "source_date_epoch": SOURCE_DATE_EPOCH,
            "source_git_archive_sha256": archive_sha,
            "source_git_commit": head,
            "state": "BUILD_COMPLETE",
            "volume_guid": VOLUME_GUID,
            "volume_label": VOLUME_LABEL,
            "volume_serial": VOLUME_SERIAL,
        }
        write_new(stage / "BUILD-STATUS.json", canonical_json(status))
        evidence_names = sorted(
            name
            for name in (
                IMAGE_NAME,
                EXPECTED_NAME,
                "RAW-VERIFY.json",
                "SOURCE-BINDINGS.json",
                "CONTAINER-BUILD.log",
                "POST-NORMALIZE-FSCK.log",
                "BUILD-STATUS.json",
            )
        )
        sum_lines: list[str] = []
        for name in evidence_names:
            digest, _ = sha256_pinned(stage / name, f"published evidence {name}")
            sum_lines.append(f"{digest}  {name}\n")
        write_new(stage / "SHA256SUMS", "".join(sum_lines).encode())
        fsync_directory(stage)
        rename_noreplace(parent, stage.name, ARTIFACT_ID)
        published = True
        result = parent / ARTIFACT_ID
        print("PASS: full offline EASYROMS p3 recovery image built and raw-verified.")
        print("PHYSICAL_DEVICES_ACCESSED=0")
        print("MACOS_FSKIT_USED=no")
        print(f"IMAGE_SHA256={image_sha}")
        print(f"OUTPUT_DIR={result}")
        return result
    finally:
        if not published and stage.exists() and not stage.is_symlink():
            shutil.rmtree(stage)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-parent", type=Path)
    parser.add_argument(
        "--variant",
        choices=("compact", "fast-card-62534975488"),
        default="compact",
    )
    return parser.parse_args()


def main() -> int:
    os.umask(0o077)
    try:
        repo_root = Path(__file__).resolve(strict=True).parents[2]
        arguments = parse_args()
        select_variant(arguments.variant)
        build(repo_root, arguments.output_parent)
    except (BuildError, OSError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
