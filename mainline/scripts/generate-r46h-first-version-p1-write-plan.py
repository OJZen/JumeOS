#!/usr/bin/env python3
"""Generate a manifest-bound p1 plan for the accepted R46H first version."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile


PROFILE_ID = "hl-r46h-v22-g92-62534975488-v1"
ARTIFACT_ID = "r46h-first-version-release-v0.1"
CURRENT_MANIFEST_SHA256 = (
    "e1e8d9edb2f8d0a9fcb4c3a660547944adc0beabbb8d716b2db247b0e7ea588b"
)
WHOLE_SIZE = 62_534_975_488
SECTOR_SIZE = 512
PREFIX_SIZE = 16_777_216
P1_OFFSET = 16_777_216
P1_SIZE = 117_440_512
P2_OFFSET = 134_217_728
P2_SIZE = 10_716_877_312
P3_OFFSET = 10_851_095_040
P3_SIZE = 51_683_880_448
PREFIX_NAME = "00-prefix-g92-mbr.bin"
P1_NAME = "01-boot-p1.img"
P2_NAME = "02-debian13-root-p2.img"
P3_NAME = "03-easyroms-p3.img"
OPERATION_ID = "write-first-version-release-boot-p1"
DEVICE_RE = re.compile(r"^/dev/disk([1-9][0-9]*)$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40}$")
SUM_LINE_RE = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9][A-Za-z0-9._/-]*)$")

MANIFEST_KEYS = (
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


class PlanError(RuntimeError):
    pass


@dataclass(frozen=True)
class ReleaseInputs:
    directory: Path
    manifest_sha256: str
    source_git_commit: str
    prefix_sha256: str
    p1_path: Path
    p1_sha256: str
    p2_sha256: str
    p3_sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_regular(path: Path, label: str, maximum_size: int | None = None) -> os.stat_result:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise PlanError(f"missing {label}: {path}") from exc
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise PlanError(f"unsafe {label}: {path}")
    if maximum_size is not None and metadata.st_size > maximum_size:
        raise PlanError(f"oversized {label}: {path}")
    return metadata


def require_directory_below(path: Path, root: Path, label: str) -> Path:
    root = root.resolve(strict=True)
    named = Path(os.path.abspath(path))
    try:
        resolved = named.resolve(strict=True)
    except OSError as exc:
        raise PlanError(f"missing {label}: {path}") from exc
    if resolved != root and root not in resolved.parents:
        raise PlanError(f"{label} must stay below {root}")
    current = named
    while current != root:
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise PlanError(f"missing {label} path component: {current}") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise PlanError(f"{label} path contains a symbolic link: {current}")
        parent = current.parent
        if parent == current:
            raise PlanError(f"{label} path does not descend from {root}")
        current = parent
    metadata = resolved.stat(follow_symlinks=False)
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) & 0o022:
        raise PlanError(f"unsafe {label}: {resolved}")
    return resolved


def parse_manifest(payload: bytes) -> dict[str, str]:
    try:
        text = payload.decode("utf-8")
    except UnicodeError as exc:
        raise PlanError("ASSET-MANIFEST is not UTF-8") from exc
    if not text.endswith("\n"):
        raise PlanError("ASSET-MANIFEST lacks a final newline")
    values: dict[str, str] = {}
    order: list[str] = []
    for line in text.splitlines():
        if not line or line != line.strip() or line.count(" ") != 1:
            raise PlanError("malformed ASSET-MANIFEST line")
        key, value = line.split(" ", 1)
        if not key or not value or key in values:
            raise PlanError("duplicate or empty ASSET-MANIFEST field")
        values[key] = value
        order.append(key)
    if tuple(order) != MANIFEST_KEYS:
        raise PlanError("ASSET-MANIFEST key order or set mismatch")
    return values


def parse_sums(payload: bytes) -> dict[str, str]:
    try:
        text = payload.decode("utf-8")
    except UnicodeError as exc:
        raise PlanError("SHA256SUMS is not UTF-8") from exc
    if not text.endswith("\n"):
        raise PlanError("SHA256SUMS lacks a final newline")
    values: dict[str, str] = {}
    for line in text.splitlines():
        match = SUM_LINE_RE.fullmatch(line)
        if match is None:
            raise PlanError("malformed SHA256SUMS line")
        digest, name = match.groups()
        if name.startswith("/") or ".." in Path(name).parts or name in values:
            raise PlanError("unsafe or duplicate SHA256SUMS path")
        values[name] = digest
    return values


def require_manifest_identity(values: dict[str, str]) -> None:
    expected = {
        "format_version": "2",
        "artifact_id": ARTIFACT_ID,
        "profile_id": PROFILE_ID,
        "whole_size": str(WHOLE_SIZE),
        "sector_size": str(SECTOR_SIZE),
        "prefix_name": PREFIX_NAME,
        "prefix_offset": "0",
        "prefix_size": str(PREFIX_SIZE),
        "boot_name": P1_NAME,
        "boot_offset": str(P1_OFFSET),
        "boot_size": str(P1_SIZE),
        "root_name": P2_NAME,
        "root_offset": str(P2_OFFSET),
        "root_size": str(P2_SIZE),
        "easyroms_name": P3_NAME,
        "easyroms_offset": str(P3_OFFSET),
        "easyroms_size": str(P3_SIZE),
        "p1_normalization": "remove-Spotlight-V100_replace-active-boot_add-v0.17",
        "evidence_level": "host-artifact-only",
        "second_card_slot": "unavailable",
        "a2_media": "compatible-not-class-proven",
        "full_card_materialized": "false",
        "media_write_performed": "false",
        "physical_devices_accessed": "0",
        "block_devices_opened": "0",
    }
    for key, value in expected.items():
        if values.get(key) != value:
            raise PlanError(f"ASSET-MANIFEST identity mismatch: {key}")
    for key in (
        "prefix_sha256",
        "boot_sha256",
        "root_sha256",
        "easyroms_sha256",
        "p1_base_sha256",
        "active_boot_sha256",
        "v17_dtb_sha256",
        "p1_prewrite_audit_sha256",
        "p2_build_info_sha256",
        "p3_build_status_sha256",
        "v17_build_receipt_sha256",
        "source_manifest_sha256",
    ):
        if SHA256_RE.fullmatch(values.get(key, "")) is None:
            raise PlanError(f"ASSET-MANIFEST malformed SHA-256: {key}")
    for key in ("source_git_commit", "source_git_tree"):
        if GIT_OBJECT_RE.fullmatch(values.get(key, "")) is None:
            raise PlanError(f"ASSET-MANIFEST malformed Git object: {key}")


def load_release(
    repo_root: Path, release_dir: Path, expected_manifest_sha256: str
) -> ReleaseInputs:
    if SHA256_RE.fullmatch(expected_manifest_sha256) is None:
        raise PlanError("expected ASSET-MANIFEST SHA-256 is malformed")
    if expected_manifest_sha256 != CURRENT_MANIFEST_SHA256:
        raise PlanError("ASSET-MANIFEST is not the accepted first-version generation")
    out_root = (repo_root / "mainline/out").resolve(strict=True)
    release = require_directory_below(release_dir, out_root, "release directory")

    manifest_path = release / "ASSET-MANIFEST"
    sums_path = release / "SHA256SUMS"
    complete_path = release / "BUILD-COMPLETE"
    receipt_path = release / "BUILD-RECEIPT.json"
    for path, label in (
        (manifest_path, "ASSET-MANIFEST"),
        (sums_path, "SHA256SUMS"),
        (complete_path, "BUILD-COMPLETE"),
        (receipt_path, "BUILD-RECEIPT.json"),
    ):
        require_regular(path, label, 1024 * 1024)

    manifest_payload = manifest_path.read_bytes()
    actual_manifest_sha256 = hashlib.sha256(manifest_payload).hexdigest()
    if actual_manifest_sha256 != expected_manifest_sha256:
        raise PlanError("ASSET-MANIFEST SHA-256 mismatch")
    values = parse_manifest(manifest_payload)
    require_manifest_identity(values)

    sums_payload = sums_path.read_bytes()
    sums = parse_sums(sums_payload)
    required_sum_bindings = {
        PREFIX_NAME: values["prefix_sha256"],
        P1_NAME: values["boot_sha256"],
        P2_NAME: values["root_sha256"],
        P3_NAME: values["easyroms_sha256"],
        "ASSET-MANIFEST": actual_manifest_sha256,
    }
    for name, digest in required_sum_bindings.items():
        if sums.get(name) != digest:
            raise PlanError(f"SHA256SUMS does not bind {name}")

    try:
        complete = json.loads(complete_path.read_bytes())
        receipt = json.loads(receipt_path.read_bytes())
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise PlanError("malformed release JSON receipt") from exc
    if (
        not isinstance(complete, dict)
        or set(complete)
        != {"asset_manifest_sha256", "format_version", "sha256sums_sha256", "state"}
        or complete.get("format_version") != 1
        or complete.get("state") != "BUILD_COMPLETE"
        or complete.get("asset_manifest_sha256") != actual_manifest_sha256
        or complete.get("sha256sums_sha256") != hashlib.sha256(sums_payload).hexdigest()
    ):
        raise PlanError("BUILD-COMPLETE contract mismatch")
    if (
        not isinstance(receipt, dict)
        or receipt.get("artifact_id") != ARTIFACT_ID
        or receipt.get("profile_id") != PROFILE_ID
        or receipt.get("asset_manifest_sha256") != actual_manifest_sha256
        or receipt.get("source_git_commit") != values["source_git_commit"]
        or receipt.get("physical_devices_accessed") != 0
        or receipt.get("block_devices_opened") != 0
        or receipt.get("media_write_performed") is not False
    ):
        raise PlanError("BUILD-RECEIPT safety contract mismatch")
    if sums.get("BUILD-RECEIPT.json") != sha256_file(receipt_path):
        raise PlanError("SHA256SUMS does not bind BUILD-RECEIPT.json")

    component_specs = (
        (PREFIX_NAME, PREFIX_SIZE, values["prefix_sha256"]),
        (P1_NAME, P1_SIZE, values["boot_sha256"]),
        (P2_NAME, P2_SIZE, values["root_sha256"]),
        (P3_NAME, P3_SIZE, values["easyroms_sha256"]),
    )
    for name, expected_size, _ in component_specs:
        metadata = require_regular(release / name, name)
        if metadata.st_size != expected_size:
            raise PlanError(f"release component size mismatch: {name}")
    p1_path = release / P1_NAME
    if sha256_file(p1_path) != values["boot_sha256"]:
        raise PlanError("release p1 SHA-256 mismatch")

    return ReleaseInputs(
        directory=release,
        manifest_sha256=actual_manifest_sha256,
        source_git_commit=values["source_git_commit"],
        prefix_sha256=values["prefix_sha256"],
        p1_path=p1_path,
        p1_sha256=values["boot_sha256"],
        p2_sha256=values["root_sha256"],
        p3_sha256=values["easyroms_sha256"],
    )


def load_rollback_clone(
    repo_root: Path, rollback_clone: Path, expected_sha256: str
) -> tuple[Path, str]:
    if SHA256_RE.fullmatch(expected_sha256) is None:
        raise PlanError("target p1 SHA-256 is malformed")
    out_root = (repo_root / "mainline/out").resolve(strict=True)
    named_sessions_root = repo_root / "mainline/out/r46h-card-agent-sessions"
    named_sessions_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    sessions_root = require_directory_below(
        named_sessions_root, out_root, "Card Agent session root"
    )
    require_directory_below(
        rollback_clone.parent, sessions_root, "rollback clone parent"
    )
    metadata = require_regular(rollback_clone, "p1 rollback clone")
    if metadata.st_size != P1_SIZE:
        raise PlanError("p1 rollback clone size mismatch")
    resolved = rollback_clone.resolve(strict=True)
    actual = sha256_file(resolved)
    if actual != expected_sha256:
        raise PlanError("p1 rollback clone SHA-256 mismatch")
    return resolved, actual


def build_write_plan(
    device: str,
    release: ReleaseInputs,
    target_p1_sha256: str,
) -> bytes:
    if DEVICE_RE.fullmatch(device) is None:
        raise PlanError("device must be an explicit whole macOS disk such as /dev/disk12")
    if SHA256_RE.fullmatch(target_p1_sha256) is None:
        raise PlanError("target p1 SHA-256 is malformed")
    if target_p1_sha256 == release.p1_sha256:
        raise PlanError("target p1 already matches the release; no write plan is needed")
    plan = {
        "format_version": 1,
        "profile_id": PROFILE_ID,
        "device": device,
        "operations": [
            {
                "id": OPERATION_ID,
                "description": "Write exact R46H first-version release BOOT p1 image",
                "partition": "boot",
                "source_path": str(release.p1_path),
                "source_size": P1_SIZE,
                "source_sha256": release.p1_sha256,
                "target_sha256_before": target_p1_sha256,
            }
        ],
    }
    return (json.dumps(plan, sort_keys=True, separators=(",", ":")) + "\n").encode()


def secure_output_parent(repo_root: Path, requested: Path | None) -> Path:
    out_root = (repo_root / "mainline/out").resolve(strict=True)
    named = requested or out_root / "r46h-first-version-release-deploy-plans"
    named = Path(os.path.abspath(named))
    if named != out_root and out_root not in named.parents:
        raise PlanError("deploy-plan output parent must stay below mainline/out")
    if requested is None:
        named.mkdir(parents=False, exist_ok=True, mode=0o700)
    elif not named.exists():
        raise PlanError("custom deploy-plan output parent must already exist")
    resolved = require_directory_below(named, out_root, "deploy-plan output parent")
    metadata = resolved.stat(follow_symlinks=False)
    if metadata.st_uid != os.getuid():
        raise PlanError("deploy-plan output parent is not owned by the invoking user")
    return resolved


def write_new(path: Path, payload: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)


def create_plan(
    repo_root: Path,
    release_dir: Path,
    manifest_sha256: str,
    rollback_clone: Path,
    target_p1_sha256: str,
    device: str,
    confirm_device: str,
    output_parent: Path | None = None,
) -> Path:
    if device != confirm_device:
        raise PlanError("device confirmation mismatch")
    release = load_release(repo_root, release_dir, manifest_sha256)
    rollback_path, rollback_sha256 = load_rollback_clone(
        repo_root, rollback_clone, target_p1_sha256
    )
    if rollback_sha256 == release.p1_sha256:
        raise PlanError("rollback clone already matches the release; no write is needed")
    plan_payload = build_write_plan(device, release, rollback_sha256)
    output = secure_output_parent(repo_root, output_parent)
    plan_dir = Path(
        tempfile.mkdtemp(prefix=".r46h-first-version-p1-plan.", dir=output)
    )
    plan_dir.chmod(0o700)
    try:
        plan_sha256 = hashlib.sha256(plan_payload).hexdigest()
        write_new(plan_dir / "write-plan.json", plan_payload)
        write_new(
            plan_dir / "write-plan.sha256",
            f"{plan_sha256}  write-plan.json\n".encode(),
        )
        info = (
            "format_version=1\n"
            "status=candidate-requires-card-agent-live-preflight\n"
            f"device={device}\n"
            f"profile_id={PROFILE_ID}\n"
            f"operation_id={OPERATION_ID}\n"
            f"release_dir={release.directory}\n"
            f"release_manifest_sha256={release.manifest_sha256}\n"
            f"release_source_git_commit={release.source_git_commit}\n"
            f"source_p1_sha256={release.p1_sha256}\n"
            f"target_p1_sha256_before={rollback_sha256}\n"
            f"rollback_clone_path={rollback_path}\n"
            f"rollback_clone_sha256={rollback_sha256}\n"
            f"expected_prefix_sha256={release.prefix_sha256}\n"
            f"expected_postwrite_p1_sha256={release.p1_sha256}\n"
            f"expected_postwrite_p2_sha256={release.p2_sha256}\n"
            f"expected_postwrite_p3_sha256={release.p3_sha256}\n"
            "postwrite_contract=full-hash-prefix-p1-p2-p3\n"
            "physical_device_reads=0\n"
            "media_writes=0\n"
        ).encode()
        write_new(plan_dir / "PLAN-INFO", info)
    except BaseException:
        shutil.rmtree(plan_dir)
        raise

    print("PASS: manifest-bound first-version p1 write plan generated.")
    print("PHYSICAL_DEVICE_READS=0")
    print("MEDIA_WRITES=0")
    print("STATUS=candidate-requires-card-agent-live-preflight")
    print(f"PLAN_DIR={plan_dir}")
    print(f"WRITE_PLAN={plan_dir / 'write-plan.json'}")
    print(f"WRITE_PLAN_SHA256={plan_sha256}")
    return plan_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-dir", required=True, type=Path)
    parser.add_argument("--asset-manifest-sha256", required=True)
    parser.add_argument("--rollback-clone", required=True, type=Path)
    parser.add_argument("--target-p1-sha256", required=True)
    parser.add_argument("--device", required=True)
    parser.add_argument("--confirm-device", required=True)
    parser.add_argument("--output-parent", type=Path)
    return parser.parse_args()


def main() -> int:
    try:
        repo_root = Path(__file__).resolve(strict=True).parents[2]
        args = parse_args()
        create_plan(
            repo_root,
            args.release_dir,
            args.asset_manifest_sha256,
            args.rollback_clone,
            args.target_p1_sha256,
            args.device,
            args.confirm_device,
            args.output_parent,
        )
    except (PlanError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
