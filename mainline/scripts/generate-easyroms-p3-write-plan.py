#!/usr/bin/env python3
"""Generate a p3-only Card Agent plan from the raw-verified recovery image."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile


ARTIFACT_ID = "r46h-easyroms-p3-recovery-v1"
IMAGE_NAME = "easyroms-p3-recovery-v1.img"
IMAGE_SIZE = 20_868_328_960
PROFILE_ID = "hl-r46h-v22-g92-31719424000-v1"
OPERATION_ID = "write-easyroms-p3-recovery-v1"
OPERATION_DESCRIPTION = (
    "Replace the complete corrupted EASYROMS p3 with the offline raw-verified image"
)
DEFAULT_OUTPUT = "mainline/out/r46h-p3-recovery-images/r46h-easyroms-p3-recovery-v1"
CONFIG_RELPATH = "mainline/p3-recovery/PAYLOAD-SOURCES.json"
FAT_LENGTH_SECTORS = 4_975
CLUSTER_HEAP_OFFSET_SECTORS = 8_192
CLUSTER_COUNT = 636_722
ROOT_DIRECTORY_CLUSTER = 6
VOLUME_GUID = "E1F5295C-4B12-A54A-ACB7-317194240001"
VOLUME_SERIAL = "52343648"
PINNED_BUILD_STATUS_SHA256: str | None = None
PINNED_SHA256SUMS_SHA256: str | None = None
PINNED_IMAGE_SHA256: str | None = None
PINNED_SOURCE_COMMIT: str | None = None
BUILDER_IMAGE = "arkos4clone/r46h-debian13-p2-mvp:v0.1"
BUILDER_IMAGE_ID = "sha256:bd09bf6db6f1fb8f882621e98d70f01f976fd8dfba1bc897766afebd64cf51b9"
DEVICE_RE = re.compile(r"^/dev/disk([1-9][0-9]*)$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_ARTIFACT_FILES = {
    "BUILD-STATUS.json",
    "CONTAINER-BUILD.log",
    "EXPECTED-FILES.json",
    "POST-NORMALIZE-FSCK.log",
    "RAW-VERIFY.json",
    "SHA256SUMS",
    "SOURCE-BINDINGS.json",
    IMAGE_NAME,
}
STATUS_KEYS = {
    "allocation_bitmap_exact",
    "artifact_id",
    "block_devices_opened",
    "builder_image",
    "builder_image_id",
    "cluster_size",
    "container_loop_devices_after",
    "deleted_entries",
    "directory_count",
    "expected_manifest_sha256",
    "file_count",
    "filesystem",
    "format_version",
    "image_name",
    "image_sha256",
    "image_size",
    "macos_fskit_used",
    "overlapping_clusters",
    "payload_config_sha256",
    "physical_devices_accessed",
    "post_normalize_fsck_read_only_passed",
    "profile_id",
    "raw_verification_sha256",
    "raw_verification_twice_passed",
    "sector_size",
    "source_date_epoch",
    "source_git_archive_sha256",
    "source_git_commit",
    "state",
    "volume_guid",
    "volume_label",
    "volume_serial",
}
EXPECTED_MANIFEST_KEYS = {
    "cluster_count",
    "cluster_heap_offset_sectors",
    "cluster_size",
    "directories",
    "fat_length_sectors",
    "fat_offset_sectors",
    "files",
    "format_version",
    "image_size",
    "root_directory_cluster",
    "sector_size",
    "volume_guid",
    "volume_label",
    "volume_serial",
}
BINDING_KEYS = {
    "action_policy",
    "build_id",
    "destination",
    "files",
    "manifest_sha256",
    "source_bundle",
    "source_git_commit",
    "stage_complete_sha256",
    "stage_sources_sha256",
}

COMPACT_VARIANT = {
    "artifact_id": "r46h-easyroms-p3-recovery-v1",
    "image_name": "easyroms-p3-recovery-v1.img",
    "image_size": 20_868_328_960,
    "profile_id": "hl-r46h-v22-g92-31719424000-v1",
    "operation_id": "write-easyroms-p3-recovery-v1",
    "operation_description": (
        "Replace the complete corrupted EASYROMS p3 with the offline raw-verified image"
    ),
    "default_output": "mainline/out/r46h-p3-recovery-images/r46h-easyroms-p3-recovery-v1",
    "config_relpath": "mainline/p3-recovery/PAYLOAD-SOURCES.json",
    "fat_length_sectors": 4_975,
    "cluster_heap_offset_sectors": 8_192,
    "cluster_count": 636_722,
    "root_directory_cluster": 6,
    "volume_guid": "E1F5295C-4B12-A54A-ACB7-317194240001",
    "volume_serial": "52343648",
    "pinned_build_status_sha256": None,
    "pinned_sha256sums_sha256": None,
    "pinned_image_sha256": None,
    "pinned_source_commit": None,
}

FAST_CARD_VARIANT = {
    "artifact_id": "r46h-easyroms-p3-62534975488-v1",
    "image_name": "easyroms-p3-62534975488-v1.img",
    "image_size": 51_683_880_448,
    "profile_id": "hl-r46h-v22-g92-62534975488-v1",
    "operation_id": "write-easyroms-p3-62534975488-v1",
    "operation_description": "Write the exact fast-card EASYROMS p3 release image",
    "default_output": (
        "mainline/out/r46h-p3-recovery-images/r46h-easyroms-p3-62534975488-v1"
    ),
    "config_relpath": "mainline/p3-recovery/PAYLOAD-SOURCES-62534975488.json",
    "fat_length_sectors": 12_321,
    "cluster_heap_offset_sectors": 16_384,
    "cluster_count": 1_577_010,
    "root_directory_cluster": 10,
    "volume_guid": "62534975-4880-4A4A-ACB7-625349754881",
    "volume_serial": "62534975",
    "pinned_build_status_sha256": (
        "05f706354bf46c9ad5237815f40d0b9155b8b103b6ab8ad9e3cfc1a81fe3ef08"
    ),
    "pinned_sha256sums_sha256": (
        "c2194050ac748fafedb46a6db2385d436b4320da5e6a10b21eee553f5c6123a7"
    ),
    "pinned_image_sha256": (
        "fe0ee7764f2e2e1f4b8451183f8cadc26e3a876847eb1bfa0569198438501fac"
    ),
    "pinned_source_commit": "6a996c3aed5c26519b6e35262e0bed5c034992c0",
}


class PlanError(RuntimeError):
    pass


def select_variant(name: str) -> None:
    global ARTIFACT_ID, IMAGE_NAME, IMAGE_SIZE, PROFILE_ID, OPERATION_ID
    global OPERATION_DESCRIPTION, DEFAULT_OUTPUT, CONFIG_RELPATH
    global FAT_LENGTH_SECTORS, CLUSTER_HEAP_OFFSET_SECTORS, CLUSTER_COUNT
    global ROOT_DIRECTORY_CLUSTER, VOLUME_GUID, VOLUME_SERIAL
    global PINNED_BUILD_STATUS_SHA256, PINNED_SHA256SUMS_SHA256
    global PINNED_IMAGE_SHA256, PINNED_SOURCE_COMMIT, EXPECTED_ARTIFACT_FILES
    variants = {
        "compact": COMPACT_VARIANT,
        "fast-card-62534975488": FAST_CARD_VARIANT,
    }
    try:
        variant = variants[name]
    except KeyError as exc:
        raise PlanError(f"unsupported p3 plan variant: {name}") from exc
    ARTIFACT_ID = variant["artifact_id"]
    IMAGE_NAME = variant["image_name"]
    IMAGE_SIZE = variant["image_size"]
    PROFILE_ID = variant["profile_id"]
    OPERATION_ID = variant["operation_id"]
    OPERATION_DESCRIPTION = variant["operation_description"]
    DEFAULT_OUTPUT = variant["default_output"]
    CONFIG_RELPATH = variant["config_relpath"]
    FAT_LENGTH_SECTORS = variant["fat_length_sectors"]
    CLUSTER_HEAP_OFFSET_SECTORS = variant["cluster_heap_offset_sectors"]
    CLUSTER_COUNT = variant["cluster_count"]
    ROOT_DIRECTORY_CLUSTER = variant["root_directory_cluster"]
    VOLUME_GUID = variant["volume_guid"]
    VOLUME_SERIAL = variant["volume_serial"]
    PINNED_BUILD_STATUS_SHA256 = variant["pinned_build_status_sha256"]
    PINNED_SHA256SUMS_SHA256 = variant["pinned_sha256sums_sha256"]
    PINNED_IMAGE_SHA256 = variant["pinned_image_sha256"]
    PINNED_SOURCE_COMMIT = variant["pinned_source_commit"]
    EXPECTED_ARTIFACT_FILES = {
        "BUILD-STATUS.json",
        "CONTAINER-BUILD.log",
        "EXPECTED-FILES.json",
        "POST-NORMALIZE-FSCK.log",
        "RAW-VERIFY.json",
        "SHA256SUMS",
        "SOURCE-BINDINGS.json",
        IMAGE_NAME,
    }


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise PlanError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def require_regular(path: Path, label: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise PlanError(f"missing {label}: {path}") from exc
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise PlanError(f"unsafe {label}: {path}")
    return metadata


def sha256_file(path: Path, expected_size: int | None = None) -> str:
    named = require_regular(path, path.name)
    if expected_size is not None and named.st_size != expected_size:
        raise PlanError(f"file size mismatch: {path.name}")
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
        if (named.st_dev, named.st_ino, named.st_size, named.st_mtime_ns, named.st_ctime_ns) != identity:
            raise PlanError(f"file changed before hashing: {path.name}")
        digest = hashlib.sha256()
        total = 0
        while True:
            block = os.read(descriptor, 4 * 1024 * 1024)
            if not block:
                break
            digest.update(block)
            total += len(block)
        after = os.fstat(descriptor)
        if total != opened.st_size or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) != identity:
            raise PlanError(f"file changed during hashing: {path.name}")
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def load_canonical_json(path: Path, label: str) -> dict[str, object]:
    require_regular(path, label)
    raw = path.read_bytes()
    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicate_pairs)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise PlanError(f"malformed {label}") from exc
    if not isinstance(value, dict) or raw != canonical_json(value):
        raise PlanError(f"noncanonical {label}")
    return value


def parse_sums(path: Path) -> dict[str, str]:
    require_regular(path, "SHA256SUMS")
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._+-]+)", line)
        if match is None:
            raise PlanError("malformed SHA256SUMS")
        digest, name = match.groups()
        if name in values:
            raise PlanError("duplicate SHA256SUMS entry")
        values[name] = digest
    if list(values) != sorted(values) or set(values) != EXPECTED_ARTIFACT_FILES - {"SHA256SUMS"}:
        raise PlanError("SHA256SUMS file set mismatch")
    return values


def load_artifact(repo_root: Path, artifact_dir: Path) -> tuple[Path, str]:
    out_root = (repo_root / "mainline/out").resolve(strict=True)
    if artifact_dir.is_symlink():
        raise PlanError("p3 recovery artifact is a symlink")
    resolved = artifact_dir.resolve(strict=True)
    if out_root not in resolved.parents:
        raise PlanError("p3 recovery artifact leaves mainline/out")
    metadata = resolved.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or {entry.name for entry in os.scandir(resolved)} != EXPECTED_ARTIFACT_FILES
    ):
        raise PlanError("p3 recovery artifact directory is unsafe or incomplete")
    sums = parse_sums(resolved / "SHA256SUMS")
    status = load_canonical_json(resolved / "BUILD-STATUS.json", "BUILD-STATUS.json")
    raw = load_canonical_json(resolved / "RAW-VERIFY.json", "RAW-VERIFY.json")
    expected = load_canonical_json(resolved / "EXPECTED-FILES.json", "EXPECTED-FILES.json")
    bindings = load_canonical_json(resolved / "SOURCE-BINDINGS.json", "SOURCE-BINDINGS.json")
    if set(status) != STATUS_KEYS:
        raise PlanError("BUILD-STATUS.json key set mismatch")
    image_sha = status.get("image_sha256")
    if (
        status.get("format_version") != 1
        or status.get("state") != "BUILD_COMPLETE"
        or status.get("artifact_id") != ARTIFACT_ID
        or status.get("profile_id") != PROFILE_ID
        or status.get("builder_image") != BUILDER_IMAGE
        or status.get("builder_image_id") != BUILDER_IMAGE_ID
        or status.get("image_name") != IMAGE_NAME
        or status.get("image_size") != IMAGE_SIZE
        or not isinstance(image_sha, str)
        or SHA_RE.fullmatch(image_sha) is None
        or status.get("filesystem") != "exfat"
        or status.get("sector_size") != 512
        or status.get("cluster_size") != 32768
        or status.get("source_date_epoch") != 1_785_369_600
        or status.get("directory_count") != 3
        or not isinstance(status.get("file_count"), int)
        or status["file_count"] <= 0
        or not isinstance(status.get("source_git_commit"), str)
        or re.fullmatch(r"[0-9a-f]{40}", status["source_git_commit"]) is None
        or any(
            not isinstance(status.get(key), str)
            or SHA_RE.fullmatch(status[key]) is None
            for key in (
                "expected_manifest_sha256",
                "payload_config_sha256",
                "raw_verification_sha256",
                "source_git_archive_sha256",
            )
        )
        or status.get("allocation_bitmap_exact") is not True
        or status.get("overlapping_clusters") != 0
        or status.get("deleted_entries") != 0
        or status.get("post_normalize_fsck_read_only_passed") is not True
        or status.get("raw_verification_twice_passed") is not True
        or status.get("container_loop_devices_after") != 0
        or status.get("block_devices_opened") != 0
        or status.get("physical_devices_accessed") != 0
        or status.get("macos_fskit_used") is not False
        or status.get("volume_guid") != VOLUME_GUID
        or status.get("volume_label") != "EASYROMS"
        or status.get("volume_serial") != VOLUME_SERIAL
    ):
        raise PlanError("p3 recovery BUILD-STATUS safety gates mismatch")
    head = subprocess_run_git(repo_root, ["rev-parse", "HEAD"]).strip()
    if PINNED_BUILD_STATUS_SHA256 is None:
        if head != status["source_git_commit"]:
            raise PlanError("p3 recovery artifact source commit is not the current HEAD")
    else:
        if (
            sha256_file(resolved / "BUILD-STATUS.json") != PINNED_BUILD_STATUS_SHA256
            or sha256_file(resolved / "SHA256SUMS") != PINNED_SHA256SUMS_SHA256
            or image_sha != PINNED_IMAGE_SHA256
            or status["source_git_commit"] != PINNED_SOURCE_COMMIT
        ):
            raise PlanError("pinned historical p3 artifact identity mismatch")
        subprocess_run_git(
            repo_root,
            ["merge-base", "--is-ancestor", str(PINNED_SOURCE_COMMIT), head],
        )
    if subprocess_run_git(repo_root, ["diff", "--quiet"], raw_result=True) != b"" or subprocess_run_git(
        repo_root, ["diff", "--cached", "--quiet"], raw_result=True
    ) != b"":
        raise PlanError("tracked worktree is not clean for p3 plan generation")
    if sha256_file(repo_root / CONFIG_RELPATH) != status["payload_config_sha256"]:
        raise PlanError("p3 payload configuration does not match the built artifact")
    try:
        config = json.loads((repo_root / CONFIG_RELPATH).read_bytes(), object_pairs_hook=reject_duplicate_pairs)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise PlanError("p3 payload configuration is malformed") from exc
    config_payloads = config.get("payloads") if isinstance(config, dict) else None
    if not isinstance(config_payloads, list) or len(config_payloads) != 3:
        raise PlanError("p3 payload configuration entry set mismatch")
    if (
        raw.get("result") != "pass"
        or raw.get("allocation_bitmap_exact") is not True
        or raw.get("overlapping_clusters") != 0
        or raw.get("deleted_entries") != 0
        or raw.get("volume_guid") != status["volume_guid"]
        or raw.get("volume_label") != status["volume_label"]
        or raw.get("volume_serial") != status["volume_serial"]
        or raw.get("expected_manifest_sha256") != status["expected_manifest_sha256"]
        or raw.get("timestamps_normalized_to_epoch") != status["source_date_epoch"]
        or len(raw.get("directories", [])) != status["directory_count"]
        or len(raw.get("files", [])) != status["file_count"]
    ):
        raise PlanError("p3 recovery RAW-VERIFY safety gates mismatch")
    expected_directories = expected.get("directories")
    expected_files = expected.get("files")
    if (
        set(expected) != EXPECTED_MANIFEST_KEYS
        or expected.get("format_version") != 1
        or expected.get("image_size") != IMAGE_SIZE
        or expected.get("sector_size") != 512
        or expected.get("cluster_size") != 32768
        or expected.get("fat_offset_sectors") != 2048
        or expected.get("fat_length_sectors") != FAT_LENGTH_SECTORS
        or expected.get("cluster_heap_offset_sectors") != CLUSTER_HEAP_OFFSET_SECTORS
        or expected.get("cluster_count") != CLUSTER_COUNT
        or expected.get("root_directory_cluster") != ROOT_DIRECTORY_CLUSTER
        or expected.get("volume_guid") != status["volume_guid"]
        or expected.get("volume_label") != status["volume_label"]
        or expected.get("volume_serial") != status["volume_serial"]
        or expected_directories != sorted(
            [
                "r46h-v0.10-adc-full-range",
                "r46h-v0.8-bootloader-handoff",
                "r46h-v0.9-adc-joystick-fix",
            ]
        )
        or not isinstance(expected_files, list)
        or len(expected_files) != status["file_count"]
    ):
        raise PlanError("p3 EXPECTED-FILES identity or geometry mismatch")
    expected_file_map = {
        item.get("path"): (item.get("size"), item.get("sha256"))
        for item in expected_files
        if isinstance(item, dict)
    }
    raw_file_map = {
        item.get("path"): (item.get("size"), item.get("sha256"))
        for item in raw.get("files", [])
        if isinstance(item, dict)
    }
    if len(expected_file_map) != len(expected_files) or raw_file_map != expected_file_map:
        raise PlanError("raw exFAT file tree is not bound to EXPECTED-FILES")
    payloads = bindings.get("payloads")
    expected_binding_identities = [
        ("r46h-v0.8-bootloader-handoff", "legacy-full", "v0.8-bootloader-handoff"),
        ("r46h-v0.9-adc-joystick-fix", "install-modules-only", "v0.9-adc-joystick-fix"),
        ("r46h-v0.10-adc-full-range", "install-modules-only", "v0.10-adc-full-range"),
    ]
    if bindings.get("format_version") != 1 or not isinstance(payloads, list) or len(payloads) != 3:
        raise PlanError("SOURCE-BINDINGS structure mismatch")
    actual_binding_identities = []
    bound_paths: set[str] = set()
    for payload, config_payload in zip(payloads, config_payloads):
        if (
            not isinstance(payload, dict)
            or set(payload) != BINDING_KEYS
            or not isinstance(payload.get("files"), list)
            or not isinstance(config_payload, dict)
        ):
            raise PlanError("SOURCE-BINDINGS payload entry mismatch")
        for key in BINDING_KEYS - {"files"}:
            if payload.get(key) != config_payload.get(key):
                raise PlanError(f"SOURCE-BINDINGS provenance mismatch: {key}")
        actual_binding_identities.append(
            (payload.get("destination"), payload.get("action_policy"), payload.get("build_id"))
        )
        destination = payload.get("destination")
        for item in payload["files"]:
            if not isinstance(item, dict) or set(item) != {"name", "size", "sha256"}:
                raise PlanError("SOURCE-BINDINGS file entry mismatch")
            path = f"{destination}/{item.get('name')}"
            if expected_file_map.get(path) != (item.get("size"), item.get("sha256")):
                raise PlanError("SOURCE-BINDINGS is not bound to EXPECTED-FILES")
            bound_paths.add(path)
    if actual_binding_identities != expected_binding_identities or bound_paths != set(expected_file_map):
        raise PlanError("SOURCE-BINDINGS identity or coverage mismatch")
    for name, expected in sums.items():
        actual = sha256_file(
            resolved / name,
            IMAGE_SIZE if name == IMAGE_NAME else None,
        )
        if actual != expected:
            raise PlanError(f"p3 recovery artifact checksum mismatch: {name}")
    if sums[IMAGE_NAME] != image_sha:
        raise PlanError("p3 recovery image binding mismatch")
    if sums["EXPECTED-FILES.json"] != status["expected_manifest_sha256"]:
        raise PlanError("expected-manifest receipt binding mismatch")
    if sums["RAW-VERIFY.json"] != status["raw_verification_sha256"]:
        raise PlanError("raw-verification receipt binding mismatch")
    return (resolved / IMAGE_NAME).resolve(strict=True), image_sha


def subprocess_run_git(
    repo_root: Path, arguments: list[str], *, raw_result: bool = False
) -> str | bytes:
    import subprocess

    result = subprocess.run(
        ["git", "-C", str(repo_root), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        if raw_result and arguments[-1] == "--quiet" and result.returncode == 1:
            return b"dirty"
        raise PlanError(f"Git command failed: {' '.join(arguments)}")
    return result.stdout if raw_result else result.stdout.decode("ascii", "strict")


def build_write_plan(
    device: str, image: Path, image_sha: str, target_sha256_before: str
) -> bytes:
    if DEVICE_RE.fullmatch(device) is None:
        raise PlanError("device must be an explicit nonzero whole macOS disk")
    if SHA_RE.fullmatch(image_sha) is None or SHA_RE.fullmatch(target_sha256_before) is None:
        raise PlanError("source or target SHA-256 is malformed")
    value = {
        "device": device,
        "format_version": 1,
        "operations": [
            {
                "description": OPERATION_DESCRIPTION,
                "id": OPERATION_ID,
                "partition": "easyroms",
                "source_path": str(image),
                "source_sha256": image_sha,
                "source_size": IMAGE_SIZE,
                "target_sha256_before": target_sha256_before,
            }
        ],
        "profile_id": PROFILE_ID,
    }
    return canonical_json(value)


def write_new(path: Path, data: bytes) -> None:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        offset = 0
        while offset < len(data):
            count = os.write(descriptor, data[offset:])
            if count <= 0:
                raise PlanError("short deploy-plan write")
            offset += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def create_plan(
    repo_root: Path,
    artifact_dir: Path,
    device: str,
    confirm_device: str,
    target_sha256_before: str,
    output_parent: Path | None,
) -> Path:
    if device != confirm_device:
        raise PlanError("device confirmation mismatch")
    image, image_sha = load_artifact(repo_root, artifact_dir)
    parent = output_parent or repo_root / "mainline/out/r46h-p3-recovery-deploy-plans"
    parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if parent.is_symlink():
        raise PlanError("deploy-plan output parent is a symlink")
    parent = parent.resolve(strict=True)
    out_root = (repo_root / "mainline/out").resolve(strict=True)
    metadata = parent.lstat()
    if (
        out_root not in parent.parents
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o077
    ):
        raise PlanError("deploy-plan output parent is unsafe")
    plan_dir = Path(tempfile.mkdtemp(prefix=".r46h-p3-plan.", dir=parent))
    plan_dir.chmod(0o700)
    try:
        plan = build_write_plan(device, image, image_sha, target_sha256_before)
        plan_sha = hashlib.sha256(plan).hexdigest()
        write_new(plan_dir / "write-plan.json", plan)
        write_new(plan_dir / "write-plan.sha256", f"{plan_sha}  write-plan.json\n".encode())
        write_new(
            plan_dir / "PLAN-INFO",
            (
                "format_version=1\n"
                "status=candidate-requires-card-agent-live-preflight\n"
                f"device={device}\n"
                f"profile_id={PROFILE_ID}\n"
                f"operation_id={OPERATION_ID}\n"
                f"source_image_sha256={image_sha}\n"
                f"target_sha256_before={target_sha256_before}\n"
                "physical_device_reads=0\n"
            ).encode(),
        )
    except BaseException:
        shutil.rmtree(plan_dir)
        raise
    print("PASS: p3-only Card Agent candidate plan generated.")
    print("PHYSICAL_DEVICE_READS=0")
    print("STATUS=candidate-requires-card-agent-live-preflight")
    print(f"PLAN_DIR={plan_dir}")
    print(f"WRITE_PLAN={plan_dir / 'write-plan.json'}")
    print(f"WRITE_PLAN_SHA256={plan_sha}")
    return plan_dir


def parse_args(repo_root: Path) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--variant",
        choices=("compact", "fast-card-62534975488"),
        default="compact",
    )
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--device", required=True)
    parser.add_argument("--confirm-device", required=True)
    parser.add_argument("--target-sha256-before", required=True)
    parser.add_argument("--output-parent", type=Path)
    return parser.parse_args()


def main() -> int:
    os.umask(0o077)
    try:
        repo_root = Path(__file__).resolve(strict=True).parents[2]
        args = parse_args(repo_root)
        select_variant(args.variant)
        create_plan(
            repo_root,
            args.artifact_dir or repo_root / DEFAULT_OUTPUT,
            args.device,
            args.confirm_device,
            args.target_sha256_before,
            args.output_parent,
        )
    except (PlanError, OSError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
