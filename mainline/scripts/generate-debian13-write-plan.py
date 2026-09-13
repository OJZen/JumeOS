#!/usr/bin/env python3
"""Generate a device-path-bound candidate plan for a later live card preflight."""

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


IMAGE_SIZE = 10_716_877_312
DEFAULT_ARTIFACT_ID = "debian13-p2-mvp-v0.1"
DEFAULT_PROFILE_ID = "hl-r46h-v22-g92-v1"
FAST_CARD_PROFILE_ID = "hl-r46h-v22-g92-62534975488-v1"
FAST_CARD_ONLY_ARTIFACTS = frozenset(
    {
        "debian13-p2-gaming-v0.3",
        "debian13-p2-gaming-v0.4",
        "debian13-p2-gaming-v0.5",
        "debian13-p2-gaming-v0.6",
        "debian13-p2-gaming-v0.7",
        "debian13-p2-gaming-v0.11",
        "debian13-p2-gaming-v0.12",
        "debian13-p2-gaming-v0.15",
        "debian13-p2-gaming-v0.16",
        "debian13-p2-gaming-v0.17",
    }
)
ARTIFACTS = {
    DEFAULT_ARTIFACT_ID: {
        "output_name": "r46h-debian13-p2-mvp-v0.1",
        "image_name": "r46h-debian13-p2-mvp-v0.1.ext4",
        "operation_id": "write-debian13-p2-mvp-v0.1",
        "description": "Write R46H Debian 13 p2 MVP v0.1 root filesystem",
    },
    "debian13-p2-gaming-v0.3": {
        "output_name": "r46h-debian13-p2-gaming-v0.3",
        "image_name": "r46h-debian13-p2-gaming-v0.3.ext4",
        "operation_id": "write-debian13-p2-gaming-v0.3",
        "description": "Write R46H Debian 13 gaming product p2 v0.3 root filesystem",
    },
    "debian13-p2-gaming-v0.4": {
        "output_name": "r46h-debian13-p2-gaming-v0.4",
        "image_name": "r46h-debian13-p2-gaming-v0.4.ext4",
        "operation_id": "write-debian13-p2-gaming-v0.4",
        "description": "Write R46H Debian 13 gaming product p2 v0.4 root filesystem",
    },
    "debian13-p2-gaming-v0.5": {
        "output_name": "r46h-debian13-p2-gaming-v0.5",
        "image_name": "r46h-debian13-p2-gaming-v0.5.ext4",
        "operation_id": "write-debian13-p2-gaming-v0.5",
        "description": "Write R46H Debian 13 gaming product p2 v0.5 root filesystem",
    },
    "debian13-p2-gaming-v0.6": {
        "output_name": "r46h-debian13-p2-gaming-v0.6",
        "image_name": "r46h-debian13-p2-gaming-v0.6.ext4",
        "operation_id": "write-debian13-p2-gaming-v0.6",
        "description": "Write R46H Debian 13 gaming product p2 v0.6 root filesystem",
    },
    "debian13-p2-gaming-v0.7": {
        "output_name": "r46h-debian13-p2-gaming-v0.7",
        "image_name": "r46h-debian13-p2-gaming-v0.7.ext4",
        "image_sha256": "17530b491eaf7edd60cb0b499cc0c920af7399673bf9296f30c5753bc1ca7180",
        "build_info_sha256": "22490e9bafcc0920a382f38d35e193ea033454de4af0a3e1dcda1eb28a84e7a7",
        "operation_id": "write-debian13-p2-gaming-v0.7",
        "description": "Write R46H Debian 13 gaming product p2 v0.7 root filesystem",
    },
    "debian13-p2-gaming-v0.11": {
        "output_name": "r46h-debian13-p2-gaming-v0.11",
        "image_name": "r46h-debian13-p2-gaming-v0.11.ext4",
        "image_sha256": "d84788c682c1f9e8c13c7fdcc1f0ebea25944aa2933b3633dde18a031b2aac60",
        "build_info_sha256": "f8a462c987a5cbcac2d1ae4c054c7844c55d74ea3889f3dd44d58dac8be2a3ab",
        "operation_id": "write-debian13-p2-gaming-v0.11",
        "description": "Write R46H Debian 13 gaming product p2 v0.11 root filesystem",
    },
    "debian13-p2-gaming-v0.12": {
        "output_name": "r46h-debian13-p2-gaming-v0.12",
        "image_name": "r46h-debian13-p2-gaming-v0.12.ext4",
        "image_sha256": "af3235742a0324453a6193bc0c3ec0e149fffcf9f6c0c22dba4e2f2e082a9111",
        "build_info_sha256": "dcc7d0e526d9efe0f2bb58930cc008d672091c3b262fd3afa1694bb1a4a7fcf4",
        "operation_id": "write-debian13-p2-gaming-v0.12",
        "description": "Write R46H Debian 13 gaming product p2 v0.12 root filesystem",
    },
    "debian13-p2-gaming-v0.15": {
        "output_name": "r46h-debian13-p2-gaming-v0.15",
        "image_name": "r46h-debian13-p2-gaming-v0.15.ext4",
        "image_sha256": "a69c2dafeae76f37a6e582bfdf4887d5714b82a4cf5b3dc7a84e29f36be6e893",
        "build_info_sha256": "f6533599f9c94997438170ac38e5a49eec9b13aa216cb20cde797cbf952968d0",
        "operation_id": "write-debian13-p2-gaming-v0.15",
        "description": "Write R46H Debian 13 gaming product p2 v0.15 root filesystem",
    },
    "debian13-p2-gaming-v0.16": {
        "output_name": "r46h-debian13-p2-gaming-v0.16",
        "image_name": "r46h-debian13-p2-gaming-v0.16.ext4",
        "image_sha256": "21cdfa3af3b96b6233decdc3ca4f8475c0eba946503045a4e86c21c50b8374c4",
        "build_info_sha256": "90a5c97848d1942b40981c975fbcbdcc93073b80bdc619ab8ebb7ab79035828a",
        "operation_id": "write-debian13-p2-gaming-v0.16",
        "description": "Write R46H Debian 13 gaming product p2 v0.16 root filesystem",
    },
    "debian13-p2-gaming-v0.17": {
        "output_name": "r46h-debian13-p2-gaming-v0.17",
        "image_name": "r46h-debian13-p2-gaming-v0.17.ext4",
        "image_sha256": "efccaf9b1d6b48624427f96f0d995c0143cb50e3447f31506ef6553973538897",
        "build_info_sha256": "45c7c732d36b8fb6ee5b33232ae69041e6159b285b667ab7eba2a81f34a9947e",
        "operation_id": "write-debian13-p2-gaming-v0.17",
        "description": "Write R46H Debian 13 gaming product p2 v0.17 root filesystem",
    },
}
PROFILE_IDS = frozenset(
    {
        "hl-r46h-v22-g92-v1",
        "hl-r46h-v22-g92-31719424000-v1",
        "hl-r46h-v22-g92-31719424000-p3-recovery-v1",
        "hl-r46h-v22-g92-62534975488-v1",
    }
)
# Backward-compatible aliases for the original MVP callers and tests.
OUTPUT_NAME = ARTIFACTS[DEFAULT_ARTIFACT_ID]["output_name"]
ARTIFACT_ID = DEFAULT_ARTIFACT_ID
IMAGE_NAME = ARTIFACTS[DEFAULT_ARTIFACT_ID]["image_name"]
PROFILE_ID = DEFAULT_PROFILE_ID
OPERATION_ID = ARTIFACTS[DEFAULT_ARTIFACT_ID]["operation_id"]
DEVICE_RE = re.compile(r"^/dev/disk([1-9][0-9]*)$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class PlanError(RuntimeError):
    pass


def require_regular(path: Path, label: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise PlanError(f"missing {label}: {path}") from exc
    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink() or metadata.st_nlink != 1:
        raise PlanError(f"unsafe {label}: {path}")
    return metadata


def parse_build_info(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or "=" not in line:
            raise PlanError("malformed BUILD-INFO")
        key, value = line.split("=", 1)
        if not key or not value or key in values:
            raise PlanError("invalid BUILD-INFO field set")
        values[key] = value
    return values


def artifact_spec(artifact_id: str) -> dict[str, str]:
    try:
        return ARTIFACTS[artifact_id]
    except KeyError as exc:
        raise PlanError(f"unsupported artifact ID: {artifact_id}") from exc


def load_artifact(
    repo_root: Path, artifact_id: str = DEFAULT_ARTIFACT_ID
) -> tuple[Path, str]:
    spec = artifact_spec(artifact_id)
    output_name = spec["output_name"]
    image_name = spec["image_name"]
    artifact_dir = repo_root / "mainline/out" / output_name
    if not artifact_dir.is_dir() or artifact_dir.is_symlink():
        raise PlanError(f"canonical artifact is missing: {artifact_dir}")
    image = artifact_dir / image_name
    metadata = require_regular(image, "canonical p2 image")
    if metadata.st_size != IMAGE_SIZE:
        raise PlanError("canonical p2 image size mismatch")

    build_info_path = artifact_dir / "BUILD-INFO"
    sums_path = artifact_dir / "SHA256SUMS"
    require_regular(build_info_path, "BUILD-INFO")
    require_regular(sums_path, "SHA256SUMS")
    expected_build_info_sha = spec.get("build_info_sha256")
    if expected_build_info_sha and (
        hashlib.sha256(build_info_path.read_bytes()).hexdigest()
        != expected_build_info_sha
    ):
        raise PlanError("canonical BUILD-INFO pinned digest mismatch")
    build_info = parse_build_info(build_info_path)
    image_sha = build_info.get("image_sha256", "")
    expected_image_sha = spec.get("image_sha256")
    if (
        build_info.get("artifact_id") != artifact_id
        or build_info.get("image_name") != image_name
        or build_info.get("image_size") != str(IMAGE_SIZE)
        or SHA_RE.fullmatch(image_sha) is None
        or (expected_image_sha is not None and image_sha != expected_image_sha)
    ):
        raise PlanError("canonical BUILD-INFO identity mismatch")

    expected_line = f"{image_sha}  {image_name}"
    sum_lines = sums_path.read_text(encoding="utf-8").splitlines()
    if sum_lines.count(expected_line) != 1:
        raise PlanError("canonical SHA256SUMS does not bind the p2 image")
    return image.resolve(strict=True), image_sha


def build_write_plan(
    device: str,
    image: Path,
    image_sha256: str,
    target_sha256_before: str,
    *,
    artifact_id: str = DEFAULT_ARTIFACT_ID,
    profile_id: str = DEFAULT_PROFILE_ID,
) -> bytes:
    spec = artifact_spec(artifact_id)
    if DEVICE_RE.fullmatch(device) is None:
        raise PlanError("device must be an explicit whole macOS disk such as /dev/disk4")
    if profile_id not in PROFILE_IDS:
        raise PlanError(f"unsupported card profile ID: {profile_id}")
    if artifact_id in FAST_CARD_ONLY_ARTIFACTS and profile_id != FAST_CARD_PROFILE_ID:
        raise PlanError(
            f"artifact {artifact_id} requires card profile {FAST_CARD_PROFILE_ID}"
        )
    if SHA_RE.fullmatch(image_sha256) is None:
        raise PlanError("source image SHA-256 is malformed")
    if SHA_RE.fullmatch(target_sha256_before) is None:
        raise PlanError("target pre-write SHA-256 is malformed")
    plan = {
        "format_version": 1,
        "profile_id": profile_id,
        "device": device,
        "operations": [
            {
                "id": spec["operation_id"],
                "description": spec["description"],
                "partition": "root",
                "source_path": str(image),
                "source_size": IMAGE_SIZE,
                "source_sha256": image_sha256,
                "target_sha256_before": target_sha256_before,
            }
        ],
    }
    return (json.dumps(plan, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def create_plan(
    repo_root: Path,
    device: str,
    target_sha256_before: str,
    artifact_id: str = DEFAULT_ARTIFACT_ID,
    profile_id: str = DEFAULT_PROFILE_ID,
) -> Path:
    spec = artifact_spec(artifact_id)
    image, image_sha = load_artifact(repo_root, artifact_id)
    output_parent = repo_root / "mainline/out/r46h-debian13-deploy-plans"
    if not output_parent.exists():
        output_parent.mkdir(mode=0o700)
    parent_stat = output_parent.lstat()
    if (
        output_parent.is_symlink()
        or not stat.S_ISDIR(parent_stat.st_mode)
        or parent_stat.st_uid != os.getuid()
        or stat.S_IMODE(parent_stat.st_mode) & 0o077
    ):
        raise PlanError("unsafe deploy-plan output parent")

    plan_dir = Path(tempfile.mkdtemp(prefix=".r46h-debian13-plan.", dir=output_parent))
    plan_dir.chmod(0o700)
    try:
        plan_bytes = build_write_plan(
            device,
            image,
            image_sha,
            target_sha256_before,
            artifact_id=artifact_id,
            profile_id=profile_id,
        )
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
            f"profile_id={profile_id}\n"
            f"artifact_id={artifact_id}\n"
            f"operation_id={spec['operation_id']}\n"
            f"source_image_sha256={image_sha}\n"
            f"target_sha256_before={target_sha256_before}\n",
            encoding="utf-8",
        )
        (plan_dir / "PLAN-INFO").chmod(0o600)
    except BaseException:
        shutil.rmtree(plan_dir)
        raise

    print("PASS: session-scoped Card Agent write plan generated.")
    print("STATUS=candidate-requires-card-agent-live-preflight")
    print(f"PLAN_DIR={plan_dir}")
    print(f"WRITE_PLAN={plan_dir / 'write-plan.json'}")
    print(f"WRITE_PLAN_SHA256={plan_sha}")
    return plan_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", required=True)
    parser.add_argument(
        "--artifact-id",
        choices=tuple(ARTIFACTS),
        default=DEFAULT_ARTIFACT_ID,
    )
    parser.add_argument(
        "--profile-id",
        choices=tuple(sorted(PROFILE_IDS)),
        default=DEFAULT_PROFILE_ID,
    )
    parser.add_argument(
        "--target-sha256-before",
        required=True,
        help="independently audited full target-partition SHA-256",
    )
    return parser.parse_args()


def main() -> int:
    try:
        repo_root = Path(__file__).resolve(strict=True).parents[2]
        args = parse_args()
        create_plan(
            repo_root,
            args.device,
            args.target_sha256_before,
            args.artifact_id,
            args.profile_id,
        )
    except (PlanError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
