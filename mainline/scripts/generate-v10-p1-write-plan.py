#!/usr/bin/env python3
"""Generate a device-path-bound Card Agent plan for the audited v0.10 p1 image."""

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


P1_SIZE = 117_440_512
PROFILE_ID = "hl-r46h-v22-g92-31719424000-v1"
ARTIFACT_ID = "r46h-v0.10-p1-one-shot"
BUILD_ID = "v0.10-adc-full-range"
RELEASE = "6.12.99-r46h-mainline-v0.10-adc-full-range"
IMAGE_NAME = "p1-v0.10-one-shot.img"
EXPECTED_BASE_IMAGE_SHA256 = "800e3c9a9196c62a2c46726db694866091cbc396b7e156109e24ce7ef5ef9907"
OPERATION_ID = "write-v10-one-shot-boot-p1"
DEVICE_RE = re.compile(r"^/dev/disk([1-9][0-9]*)$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
STATUS_KEYS = {
    "format_version",
    "state",
    "artifact_id",
    "profile_id",
    "build_id",
    "kernel_release",
    "image_name",
    "image_size",
    "image_sha256",
    "base_image_sha256",
    "active_boot_ini_unchanged",
    "v08_dtb_reused",
    "added_files",
    "removed_files",
    "changed_preexisting_files",
    "free_bytes",
    "fsck_fat_read_only_passed",
    "block_devices_opened",
}


class PlanError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def regular_file(path: Path, label: str) -> os.stat_result:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as exc:
        raise PlanError(f"missing {label}: {path}") from exc
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise PlanError(f"unsafe {label}: {path}")
    return metadata


def load_candidate(repo_root: Path, candidate_dir: Path) -> tuple[Path, str, str]:
    out_root = (repo_root / "mainline/out").resolve(strict=True)
    resolved = candidate_dir.resolve(strict=True)
    if out_root not in resolved.parents:
        raise PlanError("candidate directory must stay below mainline/out")
    metadata = candidate_dir.stat(follow_symlinks=False)
    if (
        candidate_dir.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise PlanError("candidate directory is unsafe")

    status_path = resolved / "BUILD-STATUS.json"
    sums_path = resolved / "SHA256SUMS"
    image = resolved / IMAGE_NAME
    regular_file(status_path, "BUILD-STATUS.json")
    regular_file(sums_path, "SHA256SUMS")
    image_metadata = regular_file(image, "full p1 candidate image")
    if image_metadata.st_size != P1_SIZE:
        raise PlanError("full p1 candidate image size mismatch")

    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise PlanError("malformed BUILD-STATUS.json") from exc
    if not isinstance(status, dict) or set(status) != STATUS_KEYS:
        raise PlanError("BUILD-STATUS.json contains unknown or missing keys")
    image_sha = status.get("image_sha256")
    base_sha = status.get("base_image_sha256")
    expected_added = [
        "Image.mainline-v0.10-adc-full-range.gz",
        "boot.ini.v0.10-adc-full-range",
        "rk3326-r46h-mainline-v0.10-adc-full-range.dtb",
    ]
    expected_removed = [
        "Image.mainline-v0.9-adc-joystick-fix.gz",
        "boot.ini.v0.9-adc-joystick-fix",
    ]
    if (
        status.get("format_version") != 1
        or status.get("state") != "BUILD_COMPLETE"
        or status.get("artifact_id") != ARTIFACT_ID
        or status.get("profile_id") != PROFILE_ID
        or status.get("build_id") != BUILD_ID
        or status.get("kernel_release") != RELEASE
        or status.get("image_name") != IMAGE_NAME
        or status.get("image_size") != P1_SIZE
        or not isinstance(image_sha, str)
        or SHA_RE.fullmatch(image_sha) is None
        or not isinstance(base_sha, str)
        or base_sha != EXPECTED_BASE_IMAGE_SHA256
        or status.get("active_boot_ini_unchanged") is not True
        or status.get("v08_dtb_reused") is not False
        or status.get("added_files") != expected_added
        or status.get("removed_files") != expected_removed
        or status.get("changed_preexisting_files") != []
        or not isinstance(status.get("free_bytes"), int)
        or status["free_bytes"] < 512 * 1024
        or status.get("fsck_fat_read_only_passed") is not True
        or status.get("block_devices_opened") != 0
    ):
        raise PlanError("candidate BUILD-STATUS identity or safety gates mismatch")
    expected_line = f"{image_sha}  {IMAGE_NAME}"
    sum_lines = sums_path.read_text(encoding="utf-8").splitlines()
    if sum_lines.count(expected_line) != 1:
        raise PlanError("SHA256SUMS does not uniquely bind the candidate image")
    if sha256_file(image) != image_sha:
        raise PlanError("full p1 candidate image SHA-256 mismatch")
    return image, image_sha, base_sha


def build_write_plan(
    device: str, image: Path, image_sha256: str, target_sha256_before: str
) -> bytes:
    if DEVICE_RE.fullmatch(device) is None:
        raise PlanError("device must be an explicit whole macOS disk such as /dev/disk12")
    if device == "/dev/disk6":
        raise PlanError("refusing the known 1 TB workspace disk")
    if SHA_RE.fullmatch(image_sha256) is None:
        raise PlanError("source image SHA-256 is malformed")
    if SHA_RE.fullmatch(target_sha256_before) is None:
        raise PlanError("target pre-write SHA-256 is malformed")
    if target_sha256_before != EXPECTED_BASE_IMAGE_SHA256:
        raise PlanError("target pre-write SHA-256 is not the deployed v0.9 p1 baseline")
    plan = {
        "format_version": 1,
        "profile_id": PROFILE_ID,
        "device": device,
        "operations": [
            {
                "id": OPERATION_ID,
                "description": "Write full R46H v0.10 one-shot BOOT p1 candidate image",
                "partition": "boot",
                "source_path": str(image),
                "source_size": P1_SIZE,
                "source_sha256": image_sha256,
                "target_sha256_before": target_sha256_before,
            }
        ],
    }
    return (json.dumps(plan, sort_keys=True, separators=(",", ":")) + "\n").encode()


def create_plan(
    repo_root: Path,
    candidate_dir: Path,
    device: str,
    confirm_device: str,
    output_parent: Path | None = None,
) -> Path:
    if device != confirm_device:
        raise PlanError("device confirmation mismatch")
    image, image_sha, base_sha = load_candidate(repo_root, candidate_dir)
    output_parent = output_parent or repo_root / "mainline/out/r46h-v10-p1-deploy-plans"
    output_parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    named_output_parent = output_parent
    named_parent_metadata = named_output_parent.stat(follow_symlinks=False)
    if named_output_parent.is_symlink() or not stat.S_ISDIR(named_parent_metadata.st_mode):
        raise PlanError("unsafe deploy-plan output parent")
    output_parent = named_output_parent.resolve(strict=True)
    out_root = (repo_root / "mainline/out").resolve(strict=True)
    if output_parent != out_root and out_root not in output_parent.parents:
        raise PlanError("plan output parent must stay below mainline/out")
    parent_metadata = output_parent.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.getuid()
        or stat.S_IMODE(parent_metadata.st_mode) & 0o022
    ):
        raise PlanError("unsafe deploy-plan output parent")

    plan_dir = Path(tempfile.mkdtemp(prefix=".r46h-v10-p1-plan.", dir=output_parent))
    plan_dir.chmod(0o700)
    try:
        plan_bytes = build_write_plan(device, image, image_sha, base_sha)
        plan_path = plan_dir / "write-plan.json"
        plan_path.write_bytes(plan_bytes)
        plan_path.chmod(0o600)
        plan_sha = hashlib.sha256(plan_bytes).hexdigest()
        (plan_dir / "write-plan.sha256").write_text(
            f"{plan_sha}  write-plan.json\n", encoding="utf-8"
        )
        (plan_dir / "write-plan.sha256").chmod(0o600)
        (plan_dir / "PLAN-INFO").write_text(
            "format_version=1\n"
            "status=candidate-requires-card-agent-live-preflight\n"
            f"device={device}\n"
            f"profile_id={PROFILE_ID}\n"
            f"operation_id={OPERATION_ID}\n"
            f"source_image_sha256={image_sha}\n"
            f"target_sha256_before={base_sha}\n"
            "physical_device_reads=0\n",
            encoding="utf-8",
        )
        (plan_dir / "PLAN-INFO").chmod(0o600)
    except BaseException:
        shutil.rmtree(plan_dir)
        raise

    print("PASS: session-scoped Card Agent p1-only write plan generated.")
    print("PHYSICAL_DEVICE_READS=0")
    print("STATUS=candidate-requires-card-agent-live-preflight")
    print(f"PLAN_DIR={plan_dir}")
    print(f"WRITE_PLAN={plan_dir / 'write-plan.json'}")
    print(f"WRITE_PLAN_SHA256={plan_sha}")
    return plan_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", required=True, type=Path)
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
            args.candidate_dir,
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
