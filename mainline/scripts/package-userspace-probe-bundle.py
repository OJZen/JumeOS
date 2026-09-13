#!/usr/bin/env python3
"""Package the Debian 13 Mesa probe for the audited EASYROMS stager."""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import tempfile
from typing import Any


PROBE_ID = "debian13-mesa-v0.2"
PAYLOAD_NAME = "r46h-debian13-mesa-probe-v0.2"
BUNDLE_NAME = "r46h-easyroms-debian13-mesa-probe-v0.2"
IMAGE_NAME = "r46h-userspace-probe-debian13-mesa-v0.2.squashfs"
EXPECTED_PROFILE_SHA256 = "1c4f0d7116294085d59d5e60e08480c7ac715eddb4d839d0cbdaab605de8beb1"
EXPECTED_BASELINE_SHA256 = "065b06b94a44ef73290691cfb222f14184da6c5b2e594112a33997493f0bf8a9"
EXPECTED_STAGE_TEMPLATE_SHA256 = "332176302cae4ad317f816bcf69edcc08e944ab0414973988c7ab73ab18ec567"
LEGACY_PROBE_STAGE_TEMPLATE_SHA256 = (
    "c3dd6825668132c67dd31240b32510dbc0453af2faa2477f0a54a6b7b5bdee97"
)
PACKAGING_DISABLED_REASON = (
    "userspace probe v0.2 repackaging is frozen after the raw exFAT verification "
    "failure; see mainline/deploy/EXFAT-FSKIT-POSTMORTEM.md"
)
EXPECTED_INPUTS = {
    "BUILD-INFO",
    "LDD.txt",
    "PACKAGES.tsv",
    "PROBE-FILE.txt",
    "SQUASHFS-FILES.txt",
    "SQUASHFS-INFO.txt",
    "SOURCE-SHA256SUMS",
    "bootstrap-target.sh",
    IMAGE_NAME,
}
SHA_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")
FLAT_PATH_RE = re.compile(r"[A-Za-z0-9._+-]+")
RELATIVE_PATH_RE = re.compile(r"[A-Za-z0-9._+/-]+")


class BundleError(RuntimeError):
    pass


def derive_legacy_probe_stage_template(template: str) -> str:
    """Recover the exact pre-action-policy template frozen by probe v0.2."""
    action_policy_block = """allowed_actions=$(manifest_value allowed_actions)
case "$allowed_actions" in
  install-modules|install-modules,switch-boot) ;;
  *) fail "unsupported target action policy" ;;
esac
if [[ "$allowed_actions" == install-modules ]]; then
  [[ "$(manifest_value action_policy)" == install-modules-only &&
     "$(manifest_value target_boot_switch)" == disabled ]] ||
    fail "modules-only manifest policy mismatch"
  [[ ! -e "$SOURCE_ROOT/switch-boot.sh" && ! -L "$SOURCE_ROOT/switch-boot.sh" ]] ||
    fail "modules-only source unexpectedly contains switch-boot.sh"
else
  [[ "$(manifest_value action_policy)" == full &&
     "$(manifest_value target_boot_switch)" == switch-boot.sh ]] ||
    fail "full manifest policy mismatch"
fi
readonly allowed_actions
"""
    substitutions = (
        (action_policy_block, ""),
        (
            '  echo "One sudo authorization will be used only for audited raw reads and fixed ${roms_partition} payload writes."\n',
            '  echo "One sudo authorization will be used only for audited raw reads and fixed disk4s3 payload writes."\n',
        ),
        ('  "allowed_actions=${allowed_actions}" \\\n', ""),
    )
    legacy = template
    for current, historical in substitutions:
        if legacy.count(current) != 1:
            raise BundleError(
                "current stage template cannot be reduced to the frozen v0.2 contract"
            )
        legacy = legacy.replace(current, historical, 1)
    if sha_bytes(legacy.encode("utf-8")) != LEGACY_PROBE_STAGE_TEMPLATE_SHA256:
        raise BundleError("derived v0.2 stage template checksum mismatch")
    return legacy


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_regular(path: Path, label: str) -> os.stat_result:
    try:
        current = path.lstat()
    except FileNotFoundError as exc:
        raise BundleError(f"missing {label}: {path}") from exc
    if not stat.S_ISREG(current.st_mode):
        raise BundleError(f"{label} is not a regular file: {path}")
    return current


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BundleError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_json_constant(value: str) -> None:
    raise BundleError(f"non-finite JSON number: {value}")


def load_json(path: Path, label: str) -> tuple[dict[str, Any], str]:
    require_regular(path, label)
    data = path.read_bytes()
    try:
        value = json.loads(
            data,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BundleError(f"invalid {label}: {path}") from exc
    if not isinstance(value, dict):
        raise BundleError(f"{label} must be a JSON object")
    return value, sha_bytes(data)


def require_map(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise BundleError(f"{key} must be an object")
    return value


def require_list(parent: dict[str, Any], key: str) -> list[Any]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise BundleError(f"{key} must be an array")
    return value


def require_int(parent: dict[str, Any], key: str, *, minimum: int = 0) -> int:
    value = parent.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise BundleError(f"{key} must be an integer >= {minimum}")
    return value


def require_string(
    parent: dict[str, Any], key: str, pattern: re.Pattern[str] | None = None
) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        raise BundleError(f"{key} must be a non-empty single-line string")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise BundleError(f"unsafe {key}: {value}")
    return value


def require_sha(parent: dict[str, Any], key: str) -> str:
    return require_string(parent, key, SHA_RE)


def parse_key_values(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line or "=" not in line:
            raise BundleError(f"invalid BUILD-INFO line {line_number}")
        key, value = line.split("=", 1)
        if not IDENTIFIER_RE.fullmatch(key) or not value or key in result:
            raise BundleError(f"invalid BUILD-INFO key at line {line_number}")
        result[key] = value
    return result


def manifest_bytes(fields: list[tuple[str, Any]]) -> bytes:
    seen: set[str] = set()
    lines: list[str] = []
    for key, raw_value in fields:
        value = str(raw_value)
        if key in seen or not IDENTIFIER_RE.fullmatch(key):
            raise BundleError(f"invalid or duplicate manifest key: {key}")
        if not value or "\n" in value or "\r" in value:
            raise BundleError(f"invalid manifest value for {key}")
        seen.add(key)
        lines.append(f"{key}={value}\n")
    return "".join(lines).encode("utf-8")


def validate_relative_path(value: str, label: str, *, flat: bool = False) -> str:
    pattern = FLAT_PATH_RE if flat else RELATIVE_PATH_RE
    if pattern.fullmatch(value) is None or value.startswith("/") or ".." in value.split("/"):
        raise BundleError(f"unsafe {label}: {value}")
    return value


def rename_noreplace(parent_fd: int, source_name: str, destination_name: str) -> None:
    for name in (source_name, destination_name):
        if not FLAT_PATH_RE.fullmatch(name):
            raise BundleError(f"unsafe publication name: {name}")
    libc = ctypes.CDLL(None, use_errno=True)
    source = os.fsencode(source_name)
    destination = os.fsencode(destination_name)
    if hasattr(libc, "renameatx_np"):
        rename_call = libc.renameatx_np
        rename_call.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename_call.restype = ctypes.c_int
        result = rename_call(parent_fd, source, parent_fd, destination, 0x00000004)
    elif hasattr(libc, "renameat2"):
        rename_call = libc.renameat2
        rename_call.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename_call.restype = ctypes.c_int
        result = rename_call(parent_fd, source, parent_fd, destination, 0x00000001)
    else:
        raise BundleError("platform lacks atomic no-replace rename support")
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise BundleError(f"bundle output appeared during publication: {destination_name}")
    raise OSError(error_number, os.strerror(error_number), destination_name)


def validate_profile_and_baseline(
    profile: dict[str, Any], baseline: dict[str, Any]
) -> None:
    if require_int(profile, "format_version") != 1:
        raise BundleError("unsupported card profile version")
    if require_int(baseline, "format_version") != 1:
        raise BundleError("unsupported current baseline version")
    require_string(profile, "profile_id", IDENTIFIER_RE)
    if require_string(profile, "target", IDENTIFIER_RE) != "HL-R46H-V22":
        raise BundleError("unexpected target")
    require_string(baseline, "baseline_id", IDENTIFIER_RE)
    require_string(baseline, "release", IDENTIFIER_RE)
    require_string(baseline, "payload_name", IDENTIFIER_RE)
    require_string(baseline, "source_git_commit", COMMIT_RE)

    card = require_map(profile, "card")
    boot = require_map(card, "boot")
    root = require_map(card, "root")
    easyroms = require_map(card, "easyroms")
    whole_size = require_int(card, "whole_size", minimum=1)
    sector_size = require_int(card, "sector_size", minimum=1)
    boot_offset = require_int(boot, "offset", minimum=1)
    boot_size = require_int(boot, "size", minimum=1)
    root_offset = require_int(root, "offset", minimum=1)
    root_size = require_int(root, "size", minimum=1)
    roms_offset = require_int(easyroms, "offset", minimum=1)
    roms_size = require_int(easyroms, "size", minimum=1)
    if sector_size != 512:
        raise BundleError("unexpected card sector size")
    if not (boot_offset + boot_size <= root_offset and root_offset + root_size <= roms_offset):
        raise BundleError("card partitions overlap or are out of order")
    if roms_offset + roms_size > whole_size:
        raise BundleError("EASYROMS exceeds the card size")
    if require_int(card, "g92_prefix_size", minimum=1) != boot_offset:
        raise BundleError("g92 prefix size does not end at BOOT")
    require_sha(card, "g92_prefix_sha256")
    for partition in (boot, root, easyroms):
        require_int(partition, "number", minimum=1)
    require_string(boot, "volume_uuid", IDENTIFIER_RE)
    require_string(root, "partuuid", IDENTIFIER_RE)
    require_string(easyroms, "volume_uuid", IDENTIFIER_RE)

    current_boot = require_map(baseline, "boot")
    for key in ("active_path", "candidate_path", "image_path", "dtb_path"):
        validate_relative_path(require_string(current_boot, key), f"current {key}", flat=True)
    for prefix in ("candidate", "image", "dtb"):
        require_int(current_boot, f"{prefix}_size", minimum=1)
        require_sha(current_boot, f"{prefix}_sha256")
    anchors = require_list(baseline, "payload_anchors")
    if not anchors:
        raise BundleError("current payload anchors are empty")
    seen_anchors: set[str] = set()
    for anchor in anchors:
        if not isinstance(anchor, dict):
            raise BundleError("current payload anchor must be an object")
        path = validate_relative_path(
            require_string(anchor, "path"), "current payload anchor", flat=True
        )
        if path in seen_anchors:
            raise BundleError(f"duplicate current payload anchor: {path}")
        seen_anchors.add(path)
        require_int(anchor, "size", minimum=1)
        require_sha(anchor, "sha256")

    fallback = require_map(profile, "fallback")
    for key in ("boot_path", "boot_test_path", "image_path", "dtb_path"):
        validate_relative_path(require_string(fallback, key), f"fallback {key}", flat=True)
    for prefix in ("boot", "image", "dtb"):
        require_int(fallback, f"{prefix}_size", minimum=1)
        require_sha(fallback, f"{prefix}_sha256")
    uboot = require_map(profile, "uboot")
    for key in ("root_dtb_path", "console_dtb_path"):
        validate_relative_path(require_string(uboot, key), f"U-Boot {key}")
    require_int(uboot, "dtb_size", minimum=1)
    require_sha(uboot, "dtb_sha256")


def copy_input_files(input_dir: Path, payload_dir: Path) -> None:
    actual = {entry.name for entry in input_dir.iterdir()}
    if actual != EXPECTED_INPUTS:
        missing = sorted(EXPECTED_INPUTS - actual)
        extra = sorted(actual - EXPECTED_INPUTS)
        raise BundleError(f"probe input set mismatch; missing={missing}, extra={extra}")
    for name in sorted(EXPECTED_INPUTS):
        source = input_dir / name
        require_regular(source, f"probe input {name}")
        destination = payload_dir / name
        shutil.copyfile(source, destination, follow_symlinks=False)
        destination.chmod(0o755 if name == "bootstrap-target.sh" else 0o644)


def build_bundle(args: argparse.Namespace) -> Path:
    input_dir = Path(args.input_dir)
    try:
        input_stat = input_dir.lstat()
    except FileNotFoundError as exc:
        raise BundleError("missing probe input directory") from exc
    if not stat.S_ISDIR(input_stat.st_mode):
        raise BundleError("unsafe probe input directory")
    input_dir = input_dir.resolve(strict=True)
    output_root = Path(args.output_root)
    if output_root.is_symlink():
        raise BundleError("output root must not be a symlink")
    output_root.mkdir(parents=True, exist_ok=True)
    output_root = output_root.resolve(strict=True)
    if output_root == Path(output_root.anchor):
        raise BundleError("unsafe output root")
    final_dir = output_root / BUNDLE_NAME
    if final_dir.exists() or final_dir.is_symlink():
        raise BundleError(f"bundle output already exists: {final_dir}")

    profile, profile_sha = load_json(Path(args.card_profile), "card profile")
    baseline, baseline_sha = load_json(Path(args.current_baseline), "current baseline")
    if profile_sha != EXPECTED_PROFILE_SHA256:
        raise BundleError("card profile does not match the audited identity")
    if baseline_sha != EXPECTED_BASELINE_SHA256:
        raise BundleError("current baseline does not match the audited v0.8 identity")
    validate_profile_and_baseline(profile, baseline)
    template_path = Path(args.stage_template)
    require_regular(template_path, "stage template")
    template_sha = sha_file(template_path)
    if template_sha != EXPECTED_STAGE_TEMPLATE_SHA256:
        raise BundleError("stage template does not match the audited implementation")
    template = template_path.read_text(encoding="utf-8")
    if template.count("@STAGE_SOURCES_SHA256@") != 1:
        raise BundleError("stage template token count is not exactly one")

    build_info = parse_key_values(input_dir / "BUILD-INFO")
    release = require_string(baseline, "release", IDENTIFIER_RE)
    if build_info.get("probe_id") != PROBE_ID:
        raise BundleError("BUILD-INFO probe ID mismatch")
    if build_info.get("architecture") != "arm64":
        raise BundleError("BUILD-INFO architecture mismatch")
    if build_info.get("kernel_contract") != release:
        raise BundleError("BUILD-INFO kernel contract mismatch")
    source_commit = build_info.get("source_git_commit", "")
    if COMMIT_RE.fullmatch(source_commit) is None:
        raise BundleError("BUILD-INFO source commit is invalid")
    if build_info.get("source_git_dirty") != "false":
        raise BundleError("canonical probe bundle requires clean probe sources")
    if build_info.get("source_snapshot_method") != "git-archive-exact-commit":
        raise BundleError("canonical probe bundle requires an immutable Git snapshot")
    source_archive_sha = build_info.get("source_archive_sha256", "")
    if SHA_RE.fullmatch(source_archive_sha) is None:
        raise BundleError("BUILD-INFO source archive SHA-256 is invalid")

    image_path = input_dir / IMAGE_NAME
    require_regular(image_path, "probe SquashFS")
    image_size = image_path.stat().st_size
    if image_size <= 0:
        raise BundleError("probe SquashFS is empty")
    image_sha = sha_file(image_path)
    bootstrap = (input_dir / "bootstrap-target.sh").read_text(encoding="utf-8")
    if "@IMAGE_SHA256@" in bootstrap:
        raise BundleError("bootstrap still contains the image checksum token")
    checksum_line = f"readonly EXPECTED_IMAGE_SHA256={image_sha}"
    if bootstrap.splitlines().count(checksum_line) != 1:
        raise BundleError("bootstrap does not contain the exact image checksum")
    kernel_line = f"readonly EXPECTED_KERNEL={release}"
    if bootstrap.splitlines().count(kernel_line) != 1:
        raise BundleError("bootstrap kernel contract mismatch")
    bootstrap_identities = (
        ("PROBE_ID", PROBE_ID),
        ("PAYLOAD_NAME", PAYLOAD_NAME),
        ("IMAGE_NAME", IMAGE_NAME),
    )
    for key, value in bootstrap_identities:
        identity_line = f"readonly {key}={value}"
        if bootstrap.splitlines().count(identity_line) != 1:
            raise BundleError(f"bootstrap {key} identity mismatch")
    required_bootstrap_markers = (
        "--external-receipt",
        "--external-receipt-sha256",
        "expected_receipt_keys=",
        "FINAL-RECEIPT-COMMITMENT",
        "completion_secret_sha256",
        "stage-source-list-checksum-mismatch",
        "staged-payload-entry-set-mismatch",
        "bootstrap-checksum-mismatch",
    )
    for marker in required_bootstrap_markers:
        if marker not in bootstrap:
            raise BundleError(f"bootstrap lacks external receipt trust marker: {marker}")

    # v0.2 is a frozen, already-receipted historical artifact.  Re-deriving its
    # pre-incident stager would bypass the production guard in the current
    # template, while silently changing it under the same v0.2 identity would
    # violate the receipt contract.  A future deployable probe needs a new ID
    # and a raw-media-verified publication path.
    raise BundleError(PACKAGING_DISABLED_REASON)

    epoch = args.source_date_epoch
    if epoch < 0 or epoch > 4_102_444_800:
        raise BundleError("unsafe source date epoch")
    created = dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    output_root_fd = os.open(
        output_root,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    stage_dir = Path(tempfile.mkdtemp(prefix=f".{BUNDLE_NAME}.tmp.", dir=output_root))
    published = False
    try:
        stage_dir.chmod(0o700)
        payload_dir = stage_dir / "payload"
        payload_dir.mkdir(mode=0o700)
        copy_input_files(input_dir, payload_dir)

        target = require_string(profile, "target", IDENTIFIER_RE)
        owner = manifest_bytes(
            [
                ("format_version", 1),
                ("status", "owned"),
                ("purpose", f"{PAYLOAD_NAME}-exclusive-card-stage"),
                ("target", target),
                ("source_git_commit", source_commit),
                ("kernel_release", release),
                ("probe_id", PROBE_ID),
                ("payload", PAYLOAD_NAME),
                ("image_sha256", image_sha),
            ]
        )
        complete = manifest_bytes(
            [
                ("format_version", 1),
                ("status", "complete"),
                ("probe_id", PROBE_ID),
                ("image_sha256", image_sha),
            ]
        )
        (payload_dir / ".r46h-stage-owner").write_bytes(owner)
        (payload_dir / "STAGE-COMPLETE").write_bytes(complete)
        (payload_dir / ".r46h-stage-owner").chmod(0o644)
        (payload_dir / "STAGE-COMPLETE").chmod(0o644)

        card = require_map(profile, "card")
        card_boot = require_map(card, "boot")
        card_root = require_map(card, "root")
        card_roms = require_map(card, "easyroms")
        uboot = require_map(profile, "uboot")
        fallback = require_map(profile, "fallback")
        current_boot = require_map(baseline, "boot")
        anchors = require_list(baseline, "payload_anchors")
        bootstrap_path = payload_dir / "bootstrap-target.sh"
        fields: list[tuple[str, Any]] = [
            ("format_version", 1),
            ("target", target),
            ("purpose", "debian13-mesa-panfrost-render-node-probe"),
            ("created_utc", created),
            ("source_git_commit", source_commit),
            ("build_id", PROBE_ID),
            ("kernel_release", release),
            ("payload_name", PAYLOAD_NAME),
            ("stage_template_sha256", LEGACY_PROBE_STAGE_TEMPLATE_SHA256),
            ("probe_id", PROBE_ID),
            ("probe_image", IMAGE_NAME),
            ("probe_image_size", image_size),
            ("probe_image_sha256", image_sha),
            ("stage_owner_size", len(owner)),
            ("stage_owner_sha256", sha_bytes(owner)),
            ("stage_complete_size", len(complete)),
            ("stage_complete_sha256", sha_bytes(complete)),
            ("target_bootstrap", "bootstrap-target.sh"),
            ("target_bootstrap_size", bootstrap_path.stat().st_size),
            ("target_bootstrap_sha256", sha_file(bootstrap_path)),
            ("card_profile_id", require_string(profile, "profile_id", IDENTIFIER_RE)),
            ("card_profile_sha256", profile_sha),
            ("current_baseline_id", require_string(baseline, "baseline_id", IDENTIFIER_RE)),
            ("current_baseline_sha256", baseline_sha),
            ("current_release", release),
            ("current_payload_name", require_string(baseline, "payload_name", IDENTIFIER_RE)),
            ("current_active_path", require_string(current_boot, "active_path")),
            ("current_candidate_path", require_string(current_boot, "candidate_path")),
            ("current_candidate_size", require_int(current_boot, "candidate_size", minimum=1)),
            ("current_candidate_sha256", require_sha(current_boot, "candidate_sha256")),
            ("current_image_path", require_string(current_boot, "image_path")),
            ("current_image_size", require_int(current_boot, "image_size", minimum=1)),
            ("current_image_sha256", require_sha(current_boot, "image_sha256")),
            ("current_dtb_path", require_string(current_boot, "dtb_path")),
            ("current_dtb_size", require_int(current_boot, "dtb_size", minimum=1)),
            ("current_dtb_sha256", require_sha(current_boot, "dtb_sha256")),
            ("current_anchor_count", len(anchors)),
        ]
        for index, anchor in enumerate(anchors, 1):
            assert isinstance(anchor, dict)
            fields.extend(
                [
                    (f"current_anchor_{index}_path", require_string(anchor, "path")),
                    (f"current_anchor_{index}_size", require_int(anchor, "size", minimum=1)),
                    (f"current_anchor_{index}_sha256", require_sha(anchor, "sha256")),
                ]
            )
        fields.extend(
            [
                ("fallback_boot_path", require_string(fallback, "boot_path")),
                ("fallback_boot_test_path", require_string(fallback, "boot_test_path")),
                ("fallback_boot_size", require_int(fallback, "boot_size", minimum=1)),
                ("fallback_boot_sha256", require_sha(fallback, "boot_sha256")),
                ("fallback_image_path", require_string(fallback, "image_path")),
                ("fallback_image_size", require_int(fallback, "image_size", minimum=1)),
                ("fallback_image_sha256", require_sha(fallback, "image_sha256")),
                ("fallback_dtb_path", require_string(fallback, "dtb_path")),
                ("fallback_dtb_size", require_int(fallback, "dtb_size", minimum=1)),
                ("fallback_dtb_sha256", require_sha(fallback, "dtb_sha256")),
                ("uboot_root_dtb_path", require_string(uboot, "root_dtb_path")),
                ("uboot_console_dtb_path", require_string(uboot, "console_dtb_path")),
                ("uboot_dtb_size", require_int(uboot, "dtb_size", minimum=1)),
                ("uboot_dtb_sha256", require_sha(uboot, "dtb_sha256")),
                ("card_whole_size", require_int(card, "whole_size", minimum=1)),
                ("card_sector_size", require_int(card, "sector_size", minimum=1)),
                ("card_boot_number", require_int(card_boot, "number", minimum=1)),
                ("card_boot_offset", require_int(card_boot, "offset", minimum=1)),
                ("card_boot_size", require_int(card_boot, "size", minimum=1)),
                ("card_boot_uuid", require_string(card_boot, "volume_uuid")),
                ("card_root_number", require_int(card_root, "number", minimum=1)),
                ("card_root_offset", require_int(card_root, "offset", minimum=1)),
                ("card_root_size", require_int(card_root, "size", minimum=1)),
                ("card_easyroms_number", require_int(card_roms, "number", minimum=1)),
                ("card_easyroms_offset", require_int(card_roms, "offset", minimum=1)),
                ("card_easyroms_size", require_int(card_roms, "size", minimum=1)),
                ("card_easyroms_uuid", require_string(card_roms, "volume_uuid")),
                ("card_g92_prefix_size", require_int(card, "g92_prefix_size", minimum=1)),
                ("card_g92_prefix_sha256", require_sha(card, "g92_prefix_sha256")),
            ]
        )
        deploy_manifest = manifest_bytes(fields)
        (payload_dir / "DEPLOY-MANIFEST").write_bytes(deploy_manifest)
        (payload_dir / "DEPLOY-MANIFEST").chmod(0o644)

        payload_names = sorted(entry.name for entry in payload_dir.iterdir())
        if len(payload_names) < 9 or len(payload_names) != len(set(payload_names)):
            raise BundleError("generated payload file set is invalid")
        required_trust_files = {"DEPLOY-MANIFEST", "STAGE-COMPLETE", "bootstrap-target.sh"}
        if not required_trust_files.issubset(payload_names):
            raise BundleError("generated payload misses a trust anchor")
        source_lines: list[str] = []
        for name in payload_names:
            if FLAT_PATH_RE.fullmatch(name) is None:
                raise BundleError(f"unsafe generated payload name: {name}")
            path = payload_dir / name
            require_regular(path, f"generated payload {name}")
            source_lines.append(f"{sha_file(path)}  payload/{name}\n")
        source_list = "".join(source_lines).encode("utf-8")
        (stage_dir / "STAGE-SOURCES.sha256").write_bytes(source_list)
        (stage_dir / "STAGE-SOURCES.sha256").chmod(0o644)

        complete_hash = sha_file(payload_dir / "STAGE-COMPLETE")
        if complete_hash != dict(fields)["stage_complete_sha256"]:
            raise BundleError("manifest gate hash does not match STAGE-COMPLETE")
        bootstrap_hash = sha_file(bootstrap_path)
        if bootstrap_hash != dict(fields)["target_bootstrap_sha256"]:
            raise BundleError("manifest bootstrap hash does not match bootstrap-target.sh")
        if f"{complete_hash}  payload/STAGE-COMPLETE\n" not in source_lines:
            raise BundleError("STAGE-COMPLETE is absent from the source list")
        if f"{bootstrap_hash}  payload/bootstrap-target.sh\n" not in source_lines:
            raise BundleError("bootstrap-target.sh is absent from the source list")

        source_sha = sha_bytes(source_list)
        stage_script = template.replace("@STAGE_SOURCES_SHA256@", source_sha)
        if re.search(r"@[A-Z0-9_]+@", stage_script):
            raise BundleError("stage script still contains an unresolved token")
        (stage_dir / "stage-on-macos.sh").write_text(stage_script, encoding="utf-8")
        (stage_dir / "stage-on-macos.sh").chmod(0o755)
        payload_dir.chmod(0o755)
        stage_dir.chmod(0o755)

        rename_noreplace(output_root_fd, stage_dir.name, final_dir.name)
        published = True
    finally:
        if not published and stage_dir.exists():
            shutil.rmtree(stage_dir)
        os.close(output_root_fd)

    print("PASS: Debian 13 Mesa probe EASYROMS bundle created.")
    print(f"OUTPUT_DIR={final_dir}")
    print(f"STAGE_SOURCES_SHA256={source_sha}")
    print(f"IMAGE_SHA256={image_sha}")
    return final_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--card-profile", required=True)
    parser.add_argument("--current-baseline", required=True)
    parser.add_argument("--stage-template", required=True)
    parser.add_argument("--source-date-epoch", required=True, type=int)
    return parser.parse_args()


def main() -> int:
    try:
        build_bundle(parse_args())
    except (BundleError, OSError) as exc:
        print(f"error: {exc}", file=os.sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
