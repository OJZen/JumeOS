#!/usr/bin/env python3
"""Safe macOS launcher for the R46H profile-bound read-only card audit.

The long-lived implementation is Rust.  This launcher owns only the narrow
privilege transition which cannot safely start from an ownership-disabled
external workspace: validate the canonical release against clean HEAD, freeze
the exact binary and profile into a root-private /private/tmp stage, execute
the read-only audit, and publish the flat receipt to an external archive only
after sudo has exited.

No shell is involved.  The privileged bootstrap is supplied as an immutable
``python3 -c`` argument, opens external inputs while running with the invoking
user's effective IDs, and accepts them only when their bytes match the hashes
validated before sudo.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import dataclasses
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import signal
import stat
import subprocess
import sys
import time
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

sys.dont_write_bytecode = True


EX_USAGE = 64
EX_DATAERR = 65
EX_UNAVAILABLE = 69
EX_SOFTWARE = 70
MAX_PROFILE_BYTES = 1024 * 1024
MAX_BINARY_BYTES = 128 * 1024 * 1024
MAX_RECEIPT_FILE_BYTES = 1024 * 1024
PROFILE_RELATIVE_PATH = PurePosixPath(
    "mainline/tools/r46h-card-toolchain/examples/profiles/"
    "hl-r46h-v22-g92-62534975488-v2.json"
)
DRIVER_RELATIVE_PATH = PurePosixPath("mainline/scripts/r46h_card_toolchain.py")
HANDOFF_SCHEMA = "r46h-card-macos-readonly-handoff/v1"
HANDOFF_PREFIX = "R46H_CARD_HANDOFF_V1"
LOWER_SHA256 = re.compile(r"^[0-9a-f]{64}$")
AUDIT_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
LAYOUT_ID = re.compile(r"^r46h-profile-bound-layout-v1:[0-9a-f]{64}$")
RECEIPT_KEYS = {
    "format_version",
    "audit_id",
    "profile_id",
    "profile_sha256",
    "tool_version",
    "tool_sha256",
    "hardware_target",
    "layout_id",
    "candidate",
    "partition_scheme",
    "prefix_size",
    "prefix_sha256",
    "mbr_disk_signature",
    "partitions",
    "media_access",
    "ejected",
}
PARTITION_KEYS = {
    "role",
    "number",
    "offset",
    "size",
    "mbr_bootable",
    "mbr_type_code",
    "filesystem",
    "identifiers",
}
DISCOVERY_KEYS = {
    "platform",
    "attachment_id",
    "physical_store_id",
    "display_path",
    "transport",
    "size",
    "sector_size",
    "whole",
    "internal",
    "removable",
    "ejectable",
    "writable",
    "system_disk",
}


class LauncherError(RuntimeError):
    """Expected fail-closed launcher error with a stable exit status."""

    def __init__(self, message: str, exit_code: int = EX_DATAERR) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclasses.dataclass(frozen=True)
class ReleaseBindings:
    repo_root: Path
    generation: Path
    git_commit: str
    binary: Path
    binary_sha256: str
    binary_size: int
    tool_version: str
    profile: Path
    profile_sha256: str
    profile_size: int
    profile_payload: Mapping[str, Any]


@dataclasses.dataclass(frozen=True)
class PrivilegedResult:
    returncode: int
    evidence_name: str
    status: str
    files: Mapping[str, bytes]


@dataclasses.dataclass(frozen=True)
class ArchiveRootHandle:
    path: Path
    descriptor: int
    device: int
    inode: int
    physical_id: str


def _repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_build_driver(repo_root: Path) -> Any:
    driver_path = repo_root / Path(DRIVER_RELATIVE_PATH.as_posix())
    specification = importlib.util.spec_from_file_location(
        "r46h_card_toolchain_release_driver", driver_path
    )
    if specification is None or specification.loader is None:
        raise LauncherError(f"cannot load canonical build driver: {driver_path}")
    module = importlib.util.module_from_spec(specification)
    # dataclasses resolves postponed annotations through sys.modules while the
    # module executes.  Keep this private name registered for the process.
    sys.modules[specification.name] = module
    try:
        specification.loader.exec_module(module)
    except (OSError, ImportError, SyntaxError) as error:
        raise LauncherError(f"cannot load canonical build driver: {error}") from error
    version_gate = getattr(module, "require_supported_python", None)
    if not callable(version_gate):
        raise LauncherError("canonical build driver has no Python version gate")
    try:
        version_gate()
    except Exception as error:
        exit_code = getattr(error, "exit_code", EX_UNAVAILABLE)
        if not isinstance(exit_code, int):
            exit_code = EX_UNAVAILABLE
        raise LauncherError(
            f"canonical build driver is unavailable: {error}", exit_code
        ) from error
    return module


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _read_regular_file(path: Path, maximum: Optional[int] = None) -> bytes:
    try:
        before = os.stat(path, follow_symlinks=False)
    except OSError as error:
        raise LauncherError(f"missing or unsafe regular file: {path}") from error
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_nlink != 1
    ):
        raise LauncherError(f"missing or unsafe regular file: {path}")
    if maximum is not None and before.st_size > maximum:
        raise LauncherError(f"file exceeds the audited size bound: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino, opened.st_size)
            != (before.st_dev, before.st_ino, before.st_size)
        ):
            raise LauncherError(f"file identity changed while opening: {path}")
        chunks = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise LauncherError(f"short read from regular file: {path}")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise LauncherError(f"file grew while reading: {path}")
        after = os.fstat(descriptor)
        if (
            after.st_size != opened.st_size
            or after.st_mtime_ns != opened.st_mtime_ns
            or after.st_ctime_ns != opened.st_ctime_ns
        ):
            raise LauncherError(f"file changed while reading: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _strict_json_object(payload: bytes, label: str) -> Dict[str, Any]:
    def reject_duplicate_pairs(pairs: Sequence[Tuple[str, Any]]) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        decoded = payload.decode("utf-8")
        value = json.loads(decoded, object_pairs_hook=reject_duplicate_pairs)
    except (UnicodeError, ValueError, json.JSONDecodeError) as error:
        raise LauncherError(f"invalid {label} JSON") from error
    if not isinstance(value, dict):
        raise LauncherError(f"invalid {label} JSON object")
    return value


def _manifest_record(manifest: Mapping[str, Any], relative: PurePosixPath) -> Mapping[str, Any]:
    records = manifest.get("files")
    if not isinstance(records, list):
        raise LauncherError("release source manifest has no file records")
    selected = [
        record
        for record in records
        if isinstance(record, dict) and record.get("path") == relative.as_posix()
    ]
    if len(selected) != 1:
        raise LauncherError(f"release source manifest does not pin {relative}")
    record = selected[0]
    if set(record) != {"path", "size", "sha256"}:
        raise LauncherError(f"invalid source-manifest record for {relative}")
    if (
        not isinstance(record.get("size"), int)
        or isinstance(record.get("size"), bool)
        or record["size"] < 0
        or not isinstance(record.get("sha256"), str)
        or not LOWER_SHA256.fullmatch(record["sha256"])
    ):
        raise LauncherError(f"invalid source-manifest binding for {relative}")
    return record


def collect_release_bindings(
    repo_root: Path, cache_root: Optional[str] = None
) -> ReleaseBindings:
    """Validate CURRENT against clean HEAD and collect immutable audit inputs."""

    repo_root = repo_root.resolve(strict=True)
    driver = _load_build_driver(repo_root)
    try:
        layout = driver.make_layout(cache_root, repo_root_override=repo_root)
        generation = driver.validate_release_generation(layout)
    except Exception as error:
        if error.__class__.__name__ == "DriverError":
            raise LauncherError(f"canonical release validation failed: {error}") from error
        raise

    binary = generation / "r46h-card"
    build_receipt = _strict_json_object(
        _read_regular_file(generation / "BUILD-RECEIPT.json", MAX_PROFILE_BYTES),
        "release build receipt",
    )
    manifest = _strict_json_object(
        _read_regular_file(generation / "SOURCE-MANIFEST.json", MAX_PROFILE_BYTES),
        "release source manifest",
    )
    artifact = build_receipt.get("artifact")
    source = build_receipt.get("source")
    if not isinstance(artifact, dict) or not isinstance(source, dict):
        raise LauncherError("canonical release receipt is missing bindings")
    binary_payload = _read_regular_file(binary, MAX_BINARY_BYTES)
    binary_sha256 = _sha256_bytes(binary_payload)
    if (
        artifact.get("path") != "r46h-card"
        or artifact.get("sha256") != binary_sha256
        or artifact.get("size") != len(binary_payload)
    ):
        raise LauncherError("canonical binary disagrees with its release receipt")
    git_commit = source.get("git_commit")
    if not isinstance(git_commit, str) or not re.fullmatch(r"[0-9a-f]{40,64}", git_commit):
        raise LauncherError("canonical release has an invalid Git commit binding")

    profile = repo_root / Path(PROFILE_RELATIVE_PATH.as_posix())
    profile_payload_bytes = _read_regular_file(profile, MAX_PROFILE_BYTES)
    profile_record = _manifest_record(manifest, PROFILE_RELATIVE_PATH)
    profile_sha256 = _sha256_bytes(profile_payload_bytes)
    if (
        profile_record["sha256"] != profile_sha256
        or profile_record["size"] != len(profile_payload_bytes)
    ):
        raise LauncherError("canonical profile disagrees with clean-HEAD source evidence")
    profile_payload = _strict_json_object(profile_payload_bytes, "canonical profile")
    if profile_payload.get("format_version") != 2:
        raise LauncherError("canonical read-only profile is not format_version 2")

    try:
        version = subprocess.run(
            [str(binary), "version"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C", "LANG": "C"},
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise LauncherError("canonical release binary failed its version probe") from error
    match = re.fullmatch(rb"r46h-card ([0-9]+\.[0-9]+\.[0-9]+)\n", version.stdout)
    if match is None:
        raise LauncherError("canonical release returned an invalid version string")
    try:
        readonly_schema = subprocess.run(
            [str(binary), "schema-check-readonly", "--profile", str(profile)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C", "LANG": "C"},
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise LauncherError("canonical macOS read-only profile preflight failed") from error
    expected_schema = (
        "R46H_CARD_READONLY_SCHEMA result=pass format_version=2 "
        f"profile_sha256={profile_sha256}\n"
    ).encode("ascii")
    if readonly_schema.stdout != expected_schema or readonly_schema.stderr:
        raise LauncherError("canonical macOS read-only profile preflight was not exact")

    return ReleaseBindings(
        repo_root=repo_root,
        generation=generation,
        git_commit=git_commit,
        binary=binary,
        binary_sha256=binary_sha256,
        binary_size=len(binary_payload),
        tool_version=match.group(1).decode("ascii"),
        profile=profile,
        profile_sha256=profile_sha256,
        profile_size=len(profile_payload_bytes),
        profile_payload=profile_payload,
    )


def parse_discovery(payload: bytes) -> Sequence[Mapping[str, Any]]:
    candidates = []
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeError as error:
        raise LauncherError("discover output is not UTF-8") from error
    for line in lines:
        if not line:
            continue
        try:
            candidate = json.loads(line)
        except json.JSONDecodeError as error:
            raise LauncherError("discover output contains invalid JSON") from error
        if not isinstance(candidate, dict) or set(candidate) != DISCOVERY_KEYS:
            raise LauncherError("discover output candidate key set mismatch")
        if (
            candidate.get("platform") != "macos"
            or not isinstance(candidate.get("attachment_id"), str)
            or not candidate["attachment_id"]
            or len(candidate["attachment_id"].encode("utf-8")) > 512
            or candidate.get("transport", "").lower() != "usb"
            or candidate.get("whole") is not True
            or candidate.get("internal") is not False
            or candidate.get("removable") is not True
            or candidate.get("ejectable") is not True
            or candidate.get("system_disk") is not False
            or not isinstance(candidate.get("size"), int)
            or isinstance(candidate.get("size"), bool)
            or not isinstance(candidate.get("sector_size"), int)
            or isinstance(candidate.get("sector_size"), bool)
        ):
            raise LauncherError("discover output contains an ineligible candidate")
        candidates.append(candidate)
    identifiers = [candidate["attachment_id"] for candidate in candidates]
    if len(set(identifiers)) != len(identifiers):
        raise LauncherError("discover output contains duplicate attachment IDs")
    return candidates


def discover_candidates(bindings: ReleaseBindings) -> Sequence[Mapping[str, Any]]:
    try:
        result = subprocess.run(
            [str(bindings.binary), "discover"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C", "LANG": "C"},
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise LauncherError("canonical release discovery failed", EX_UNAVAILABLE) from error
    return parse_discovery(result.stdout)


def select_candidate(
    candidates: Sequence[Mapping[str, Any]],
    attachment_id: str,
    profile: Mapping[str, Any],
) -> Mapping[str, Any]:
    selected = [candidate for candidate in candidates if candidate["attachment_id"] == attachment_id]
    if len(selected) != 1:
        raise LauncherError(
            f"explicit attachment ID matched {len(selected)} eligible candidates"
        )
    candidate = selected[0]
    if (
        candidate.get("size") != profile.get("whole_size")
        or candidate.get("sector_size") != profile.get("sector_size")
    ):
        raise LauncherError("selected candidate geometry does not match the canonical profile")
    return candidate


def _validate_audit_id(value: str) -> str:
    if not AUDIT_ID.fullmatch(value):
        raise LauncherError("audit ID must match [a-z0-9][a-z0-9._-]{0,63}", EX_USAGE)
    return value


def _default_audit_id() -> str:
    return f"r46h-macos-ro-{secrets.token_hex(10)}"


def _reject_linked_ancestry(path: Path, label: str) -> None:
    current = Path(path.anchor)
    for component in path.parts[1:]:
        current = current / component
        try:
            metadata = os.stat(current, follow_symlinks=False)
        except FileNotFoundError:
            continue
        except OSError as error:
            raise LauncherError(f"cannot inspect {label}: {current}") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise LauncherError(f"linked component in {label}: {current}")


def prepare_external_archive_root(
    path: Path,
    driver: Any,
    *,
    platform_name: Optional[str] = None,
    forbidden_physical_id: Optional[str] = None,
) -> Path:
    if not path.is_absolute():
        raise LauncherError("archive root must be an absolute path", EX_USAGE)
    path = Path(os.path.abspath(os.path.normpath(str(path))))
    _reject_linked_ancestry(path, "archive root")
    try:
        metadata = os.stat(path, follow_symlinks=False)
    except FileNotFoundError as error:
        raise LauncherError(
            "archive root must already exist on external storage; the launcher will not "
            f"create path components: {path}",
            EX_USAGE,
        ) from error
    if not stat.S_ISDIR(metadata.st_mode):
        raise LauncherError(f"archive root is not a real directory: {path}")
    effective_platform = platform_name or sys.platform
    if effective_platform == "darwin":
        identity = driver.query_macos_storage_identity(path)
        if identity.internal is not False or not identity.physical_id:
            raise LauncherError(
                f"cannot prove that the receipt archive is on external macOS storage: {path}"
            )
        if identity.physical_id == forbidden_physical_id:
            raise LauncherError("receipt archive may not reside on the selected target card")
    _reject_linked_ancestry(path, "archive root")
    if effective_platform == "darwin":
        identity = driver.query_macos_storage_identity(path)
        if identity.internal is not False or not identity.physical_id:
            raise LauncherError(
                f"cannot prove that the receipt archive is on external macOS storage: {path}"
            )
        if identity.physical_id == forbidden_physical_id:
            raise LauncherError("receipt archive may not reside on the selected target card")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise LauncherError("archive root identity changed while opening")
    finally:
        os.close(descriptor)
    return path


def open_external_archive_root(
    path: Path, driver: Any, *, forbidden_physical_id: str
) -> ArchiveRootHandle:
    prepared = prepare_external_archive_root(
        path, driver, forbidden_physical_id=forbidden_physical_id
    )
    identity = driver.query_macos_storage_identity(prepared)
    if identity.internal is not False or not identity.physical_id:
        raise LauncherError("external archive identity became unprovable while opening")
    if identity.physical_id == forbidden_physical_id:
        raise LauncherError("receipt archive may not reside on the selected target card")
    descriptor = _open_directory(prepared)
    try:
        metadata = os.fstat(descriptor)
        current = os.stat(prepared, follow_symlinks=False)
        if (metadata.st_dev, metadata.st_ino) != (current.st_dev, current.st_ino):
            raise LauncherError("external archive root changed while opening")
        return ArchiveRootHandle(
            prepared,
            descriptor,
            metadata.st_dev,
            metadata.st_ino,
            identity.physical_id,
        )
    except Exception:
        os.close(descriptor)
        raise


def revalidate_external_archive_root(handle: ArchiveRootHandle, driver: Any) -> None:
    try:
        current = os.stat(handle.path, follow_symlinks=False)
    except OSError as error:
        raise LauncherError("external archive root disappeared during the audit") from error
    opened = os.fstat(handle.descriptor)
    identity = driver.query_macos_storage_identity(handle.path)
    if (
        stat.S_ISLNK(current.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != (handle.device, handle.inode)
        or (opened.st_dev, opened.st_ino) != (handle.device, handle.inode)
        or identity.internal is not False
        or identity.physical_id != handle.physical_id
    ):
        raise LauncherError("external archive root identity changed during the audit")


def candidate_whole_disk_id(candidate: Mapping[str, Any]) -> str:
    display_path = candidate.get("display_path")
    if not isinstance(display_path, str):
        raise LauncherError("selected candidate has no physical display path")
    match = re.fullmatch(r"/dev/r?(disk[0-9]+)", display_path)
    if match is None:
        raise LauncherError("selected candidate does not expose a whole-disk BSD path")
    return match.group(1)


def require_archive_target_separation(
    handle: ArchiveRootHandle, candidate: Mapping[str, Any]
) -> None:
    if candidate_whole_disk_id(candidate) == handle.physical_id:
        raise LauncherError("receipt archive may not reside on the selected target card")


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def _json_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _layout_hash_text(hasher: Any, value: str) -> None:
    encoded = value.encode("utf-8")
    if len(encoded) > 0xFFFFFFFF:
        raise LauncherError("layout identity text exceeds the protocol bound")
    hasher.update(len(encoded).to_bytes(4, "big"))
    hasher.update(encoded)


def recompute_layout_id(receipt: Mapping[str, Any]) -> str:
    candidate = receipt["candidate"]
    partitions = receipt["partitions"]
    hasher = hashlib.sha256()
    hasher.update(b"r46h-profile-bound-layout-v1\0")
    _layout_hash_text(hasher, receipt["profile_id"])
    _layout_hash_text(hasher, receipt["profile_sha256"])
    _layout_hash_text(hasher, receipt["hardware_target"])
    hasher.update(candidate["size"].to_bytes(8, "big"))
    hasher.update(candidate["sector_size"].to_bytes(4, "big"))
    hasher.update(receipt["partition_scheme"].encode("ascii"))
    hasher.update(receipt["prefix_size"].to_bytes(8, "big"))
    _layout_hash_text(hasher, receipt["prefix_sha256"])
    hasher.update(receipt["mbr_disk_signature"].to_bytes(4, "big"))
    hasher.update(len(partitions).to_bytes(4, "big"))
    for partition in partitions:
        hasher.update(partition["number"].to_bytes(4, "big"))
        hasher.update(partition["offset"].to_bytes(8, "big"))
        hasher.update(partition["size"].to_bytes(8, "big"))
        hasher.update(bytes([int(partition["mbr_bootable"])]))
        hasher.update(bytes([partition["mbr_type_code"]]))
        _layout_hash_text(hasher, partition["role"])
        _layout_hash_text(hasher, partition["filesystem"] or "")
        identifiers = partition["identifiers"]
        hasher.update(len(identifiers).to_bytes(4, "big"))
        for key in sorted(identifiers):
            _layout_hash_text(hasher, key)
            _layout_hash_text(hasher, identifiers[key])
    return "r46h-profile-bound-layout-v1:" + hasher.hexdigest()


def validate_completed_receipt(
    files: Mapping[str, bytes],
    bindings: ReleaseBindings,
    expected_candidate: Mapping[str, Any],
    audit_id: str,
) -> Mapping[str, Any]:
    if set(files) != {"READONLY-AUDIT.json", "AUDIT-COMPLETE"}:
        raise LauncherError("completed handoff does not contain the exact flat receipt set")
    receipt_bytes = files["READONLY-AUDIT.json"]
    digest = _sha256_bytes(receipt_bytes)
    if files["AUDIT-COMPLETE"] != f"receipt_sha256={digest}\n".encode("ascii"):
        raise LauncherError("AUDIT-COMPLETE does not bind the handed-off receipt")
    receipt = _strict_json_object(receipt_bytes, "read-only audit receipt")
    profile = bindings.profile_payload
    candidate = receipt.get("candidate")
    attachment_id = expected_candidate.get("attachment_id")
    partitions = receipt.get("partitions")
    expected_partitions = profile.get("partitions")
    if (
        set(receipt) != RECEIPT_KEYS
        or receipt.get("format_version") != 1
        or receipt.get("audit_id") != audit_id
        or receipt.get("profile_id") != profile.get("profile_id")
        or receipt.get("profile_sha256") != bindings.profile_sha256
        or receipt.get("tool_version") != bindings.tool_version
        or receipt.get("tool_sha256") != bindings.binary_sha256
        or receipt.get("hardware_target") != profile.get("target")
        or not isinstance(receipt.get("layout_id"), str)
        or not LAYOUT_ID.fullmatch(receipt["layout_id"])
        or receipt.get("partition_scheme") != profile.get("partition_scheme")
        or receipt.get("prefix_size") != profile.get("prefix", {}).get("size")
        or receipt.get("prefix_sha256") != profile.get("prefix", {}).get("sha256")
        or not _json_integer(receipt.get("mbr_disk_signature"))
        or not 0 < receipt["mbr_disk_signature"] <= 0xFFFFFFFF
        or receipt.get("media_access") != "read_only"
        or receipt.get("ejected") is not True
        or not isinstance(candidate, dict)
        or set(candidate) != DISCOVERY_KEYS
        or candidate != expected_candidate
        or candidate.get("attachment_id") != attachment_id
        or candidate.get("transport", "").lower() != "usb"
        or candidate.get("size") != profile.get("whole_size")
        or candidate.get("sector_size") != profile.get("sector_size")
        or candidate.get("whole") is not True
        or candidate.get("internal") is not False
        or candidate.get("removable") is not True
        or candidate.get("ejectable") is not True
        or candidate.get("system_disk") is not False
        or not isinstance(partitions, list)
        or not isinstance(expected_partitions, list)
        or len(partitions) != len(expected_partitions)
    ):
        raise LauncherError("read-only receipt disagrees with pinned audit bindings")
    expected_by_number = {
        partition.get("number"): partition
        for partition in expected_partitions
        if isinstance(partition, dict)
    }
    if len(expected_by_number) != len(expected_partitions):
        raise LauncherError("canonical profile has invalid partition records")
    seen = set()
    previous_number = 0
    for partition in partitions:
        if not isinstance(partition, dict) or set(partition) != PARTITION_KEYS:
            raise LauncherError("read-only receipt has an invalid partition record")
        number = partition.get("number")
        expected = expected_by_number.get(number)
        if (
            expected is None
            or number in seen
            or not _json_integer(number)
            or number <= previous_number
            or not _json_integer(partition.get("offset"))
            or not _json_integer(partition.get("size"))
            or not isinstance(partition.get("mbr_bootable"), bool)
            or not _json_integer(partition.get("mbr_type_code"))
            or not 0 < partition["mbr_type_code"] <= 255
            or not isinstance(partition.get("identifiers"), dict)
            or partition.get("role") != expected.get("role")
            or partition.get("offset") != expected.get("offset")
            or partition.get("size") != expected.get("size")
            or partition.get("mbr_bootable")
            != expected.get("mbr", {}).get("bootable")
            or partition.get("mbr_type_code")
            != expected.get("mbr", {}).get("type_code")
            or partition.get("filesystem") != expected.get("filesystem")
            or partition.get("identifiers", {}) != expected.get("identifiers", {})
        ):
            raise LauncherError("read-only receipt partition disagrees with the profile")
        partuuid = partition["identifiers"].get("partuuid")
        if partuuid is not None:
            derived = f"{receipt['mbr_disk_signature']:08x}-{number:02d}"
            if partuuid != derived:
                raise LauncherError(
                    "read-only receipt PARTUUID is not derived from its MBR signature"
                )
        seen.add(number)
        previous_number = number
    if receipt["layout_id"] != recompute_layout_id(receipt):
        raise LauncherError("read-only receipt layout identity is invalid")
    return receipt


def _open_directory(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    return os.open(path, flags)


def _write_new_at(directory: int, name: str, payload: bytes, mode: int = 0o600) -> None:
    if not name or "/" in name or name in {".", ".."}:
        raise LauncherError("invalid flat archive member name")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(name, flags, mode, dir_fd=directory)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise LauncherError(f"short archive write: {name}")
            view = view[written:]
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_handoff_archive(
    archive_root: Path,
    files: Mapping[str, bytes],
    status: str,
    bindings: ReleaseBindings,
    attachment_id: str,
    audit_id: str,
    *,
    _root_descriptor: Optional[int] = None,
) -> Path:
    if status not in {"complete", "failed"}:
        raise LauncherError("invalid handoff status")
    suffix = "" if status == "complete" else "-failed"
    directory_name = f"r46h-readonly-{audit_id}{suffix}"
    root_descriptor = (
        os.dup(_root_descriptor)
        if _root_descriptor is not None
        else _open_directory(archive_root)
    )
    created = False
    try:
        os.mkdir(directory_name, 0o700, dir_fd=root_descriptor)
        created = True
        os.fsync(root_descriptor)
        archive_descriptor = os.open(
            directory_name,
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=root_descriptor,
        )
        try:
            ordered_files = sorted(
                (name for name in files if name != "AUDIT-COMPLETE"),
                key=lambda item: item.encode("utf-8"),
            )
            if "AUDIT-COMPLETE" in files:
                ordered_files.append("AUDIT-COMPLETE")
            for name in ordered_files:
                _write_new_at(archive_descriptor, name, files[name])
            manifest = {
                "schema": HANDOFF_SCHEMA,
                "status": status,
                "audit_id": audit_id,
                "attachment_id": attachment_id,
                "git_commit": bindings.git_commit,
                "release_generation": bindings.generation.name,
                "profile": {
                    "path": PROFILE_RELATIVE_PATH.as_posix(),
                    "sha256": bindings.profile_sha256,
                    "size": bindings.profile_size,
                },
                "tool": {
                    "version": bindings.tool_version,
                    "sha256": bindings.binary_sha256,
                    "size": bindings.binary_size,
                },
                "files": {
                    name: {"sha256": _sha256_bytes(payload), "size": len(payload)}
                    for name, payload in sorted(files.items())
                },
            }
            manifest_bytes = _canonical_json(manifest)
            _write_new_at(archive_descriptor, "HANDOFF.json", manifest_bytes)
            os.fsync(archive_descriptor)
            complete = (
                f"handoff_sha256={_sha256_bytes(manifest_bytes)}\n"
                f"status={status}\n"
            ).encode("ascii")
            _write_new_at(archive_descriptor, "HANDOFF-COMPLETE", complete)
            os.fsync(archive_descriptor)
        finally:
            os.close(archive_descriptor)
        os.fsync(root_descriptor)
    except FileExistsError as error:
        raise LauncherError(f"archive directory already exists: {archive_root / directory_name}") from error
    except Exception:
        if created:
            # A partial directory is evidence of an interrupted handoff.  It is
            # intentionally preserved, lacks HANDOFF-COMPLETE, and is never
            # mistaken for a completed archive.
            pass
        raise
    finally:
        os.close(root_descriptor)
    return archive_root / directory_name


def validate_and_publish_privileged_result(
    archive_handle: ArchiveRootHandle,
    driver: Any,
    result: PrivilegedResult,
    bindings: ReleaseBindings,
    selected_candidate: Mapping[str, Any],
    attachment_id: str,
    audit_id: str,
) -> Path:
    """Validate and archive a handoff while preserving recoverable evidence."""
    try:
        revalidate_external_archive_root(archive_handle, driver)
        if result.status == "complete":
            validate_completed_receipt(
                result.files, bindings, selected_candidate, audit_id
            )
        return publish_handoff_archive(
            archive_handle.path,
            result.files,
            result.status,
            bindings,
            attachment_id,
            audit_id,
            _root_descriptor=archive_handle.descriptor,
        )
    except BaseException:
        print(
            "WARNING: recovery evidence remains at "
            f"/private/tmp/{result.evidence_name}",
            file=sys.stderr,
        )
        raise


def parse_handoff_line(line: bytes, token: str) -> PrivilegedResult:
    prefix = f"{HANDOFF_PREFIX}:{token}:".encode("ascii")
    if not line.startswith(prefix):
        raise LauncherError("invalid privileged handoff prefix")
    try:
        raw = base64.b64decode(line[len(prefix) :].strip(), validate=True)
        envelope = json.loads(raw.decode("utf-8"))
    except (ValueError, binascii.Error, UnicodeError, json.JSONDecodeError) as error:
        raise LauncherError("invalid privileged handoff envelope") from error
    if not isinstance(envelope, dict) or set(envelope) != {
        "schema",
        "status",
        "returncode",
        "evidence_name",
        "files",
    }:
        raise LauncherError("privileged handoff envelope key set mismatch")
    if envelope.get("schema") != HANDOFF_SCHEMA or envelope.get("status") not in {
        "complete",
        "failed",
    }:
        raise LauncherError("privileged handoff envelope schema mismatch")
    returncode = envelope.get("returncode")
    evidence_name = envelope.get("evidence_name")
    encoded_files = envelope.get("files")
    if (
        not isinstance(returncode, int)
        or isinstance(returncode, bool)
        or returncode < 0
        or returncode > 255
        or not isinstance(evidence_name, str)
        or not re.fullmatch(r"\.r46h-card-readonly-audit\.[0-9a-f]{32}", evidence_name)
        or not isinstance(encoded_files, dict)
        or not encoded_files
    ):
        raise LauncherError("privileged handoff envelope fields are invalid")
    files: Dict[str, bytes] = {}
    for name, encoded in encoded_files.items():
        if (
            name not in {"READONLY-AUDIT.json", "AUDIT-COMPLETE", "AUDIT-FAILED"}
            or not isinstance(encoded, str)
        ):
            raise LauncherError("privileged handoff contains an unexpected file")
        try:
            payload = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as error:
            raise LauncherError("privileged handoff file is not valid base64") from error
        if len(payload) > MAX_RECEIPT_FILE_BYTES:
            raise LauncherError("privileged handoff file exceeds its size bound")
        files[name] = payload
    status = envelope["status"]
    if (status == "complete") != (returncode == 0):
        raise LauncherError("privileged handoff status disagrees with the audit exit status")
    return PrivilegedResult(returncode, evidence_name, status, files)


# This bootstrap is intentionally self-contained and passed as an argv value to
# root's system Python.  It never executes a mutable script as root and never
# invokes a shell.  Keep dependencies to the Python standard library.
PRIVILEGED_BOOTSTRAP = r'''
import base64, hashlib, json, os, signal, stat, subprocess, sys

MAX_FILE = 1024 * 1024
PREFIX = "R46H_CARD_HANDOFF_V1"
SCHEMA = "r46h-card-macos-readonly-handoff/v1"

def fail(message, code=70):
    print("ERROR: privileged read-only bootstrap: " + message.replace("\n", "_"), file=sys.stderr)
    return code

def regular_source(path, expected_size):
    flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
             | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_CLOEXEC", 0))
    descriptor = os.open(path, flags)
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_size != expected_size:
        os.close(descriptor)
        raise RuntimeError("source is not the expected regular file")
    return descriptor

def copy_pinned(source, directory, name, expected_size, expected_digest, mode):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    destination = os.open(name, flags, mode, dir_fd=directory)
    digest = hashlib.sha256()
    total = 0
    try:
        while True:
            chunk = os.read(source, 1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > expected_size:
                raise RuntimeError("source grew while freezing")
            digest.update(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(destination, view)
                if written <= 0:
                    raise RuntimeError("short stage write")
                view = view[written:]
        if total != expected_size or digest.hexdigest() != expected_digest:
            raise RuntimeError("source bytes do not match the pre-sudo binding")
        os.fchmod(destination, mode)
        os.fsync(destination)
    finally:
        os.close(destination)

def exact_files(path, returncode):
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory = os.open(path, flags)
    try:
        metadata = os.fstat(directory)
        if metadata.st_uid != 0 or metadata.st_gid != 0 or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise RuntimeError("evidence directory lost its root-private identity")
        names = set(os.listdir(directory))
        success = {"READONLY-AUDIT.json", "AUDIT-COMPLETE"}
        allowed_failure = {"READONLY-AUDIT.json", "AUDIT-COMPLETE", "AUDIT-FAILED"}
        if returncode == 0 and names != success:
            raise RuntimeError("successful audit has an incomplete flat receipt")
        if returncode != 0 and (not names or not names.issubset(allowed_failure)):
            raise RuntimeError("failed audit has an unsafe evidence member set")
        payloads = {}
        descriptors = []
        for name in sorted(names):
            descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory)
            try:
                member = os.fstat(descriptor)
                if (not stat.S_ISREG(member.st_mode) or member.st_uid != 0 or member.st_gid != 0
                        or member.st_nlink != 1 or member.st_mode & 0o022 or member.st_size > MAX_FILE):
                    raise RuntimeError("unsafe evidence member")
                chunks = []
                remaining = member.st_size
                while remaining:
                    chunk = os.read(descriptor, min(1024 * 1024, remaining))
                    if not chunk:
                        raise RuntimeError("short evidence read")
                    chunks.append(chunk)
                    remaining -= len(chunk)
                if os.read(descriptor, 1):
                    raise RuntimeError("evidence member grew while reading")
                payloads[name] = b"".join(chunks)
                descriptors.append(descriptor)
                descriptor = None
            finally:
                if descriptor is not None:
                    os.close(descriptor)
        if returncode == 0:
            receipt = payloads["READONLY-AUDIT.json"]
            marker = ("receipt_sha256=" + hashlib.sha256(receipt).hexdigest() + "\n").encode("ascii")
            if payloads["AUDIT-COMPLETE"] != marker:
                raise RuntimeError("root receipt marker does not bind the receipt")
        for descriptor in descriptors:
            os.fchown(descriptor, CALLER_UID, CALLER_GID)
            os.close(descriptor)
        descriptors = []
        os.fchown(directory, CALLER_UID, CALLER_GID)
        return payloads
    finally:
        for descriptor in locals().get("descriptors", []):
            try: os.close(descriptor)
            except OSError: pass
        os.close(directory)

def cleanup_stage(path, directory):
    if directory is not None:
        try:
            for name in ("profile.json", "r46h-card"):
                try:
                    os.unlink(name, dir_fd=directory)
                except FileNotFoundError:
                    pass
            os.fsync(directory)
        finally:
            os.close(directory)
    try:
        os.rmdir(path)
    except FileNotFoundError:
        pass

def main():
    global CALLER_UID, CALLER_GID
    if len(sys.argv) != 13 or os.geteuid() != 0:
        return fail("invalid root invocation", 64)
    (uid_raw, gid_raw, binary_source, binary_size_raw, binary_digest,
     profile_source, profile_size_raw, profile_digest, evidence_name,
     attachment_id, audit_id, token) = sys.argv[1:]
    try:
        CALLER_UID, CALLER_GID = int(uid_raw), int(gid_raw)
        binary_size, profile_size = int(binary_size_raw), int(profile_size_raw)
    except ValueError:
        return fail("invalid numeric binding", 64)
    if (CALLER_UID <= 0 or CALLER_GID < 0 or os.environ.get("SUDO_UID") != uid_raw
            or os.environ.get("SUDO_GID") != gid_raw):
        return fail("sudo caller identity mismatch", 64)
    evidence_token = evidence_name.removeprefix(".r46h-card-readonly-audit.")
    hex_digits = "0123456789abcdef"
    if (len(evidence_token) != 32 or any(character not in hex_digits for character in evidence_token)
            or len(token) != 32 or any(character not in hex_digits for character in token)):
        return fail("invalid private path binding", 64)
    tmp = "/private/tmp"
    tmp_metadata = os.lstat(tmp)
    if (not stat.S_ISDIR(tmp_metadata.st_mode) or stat.S_ISLNK(tmp_metadata.st_mode)
            or tmp_metadata.st_uid != 0 or tmp_metadata.st_gid != 0
            or stat.S_IMODE(tmp_metadata.st_mode) != 0o1777):
        return fail("/private/tmp is not root-owned sticky 1777")
    stage = tmp + "/.r46h-card-readonly-stage." + token
    evidence = tmp + "/" + evidence_name
    os.umask(0o077)
    stage_fd = None
    source_fds = []
    child = None
    forwarded = []
    old_handlers = {}
    def forward(signum, _frame):
        forwarded.append(signum)
        if child is not None and child.poll() is None:
            try:
                child.send_signal(signum)
            except ProcessLookupError:
                pass
    for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        old_handlers[signum] = signal.signal(signum, forward)
    try:
        if forwarded:
            raise InterruptedError("interrupted before root-private staging")
        os.mkdir(stage, 0o700)
        stage_fd = os.open(stage, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
        stage_metadata = os.fstat(stage_fd)
        if stage_metadata.st_uid != 0 or stage_metadata.st_gid != 0 or stat.S_IMODE(stage_metadata.st_mode) != 0o700:
            raise RuntimeError("stage is not root-private")

        os.setgroups([CALLER_GID])
        os.setegid(CALLER_GID)
        os.seteuid(CALLER_UID)
        try:
            source_fds.append(regular_source(binary_source, binary_size))
            source_fds.append(regular_source(profile_source, profile_size))
        finally:
            os.seteuid(0)
            os.setegid(0)
            os.setgroups([])
        copy_pinned(source_fds[0], stage_fd, "r46h-card", binary_size, binary_digest, 0o700)
        copy_pinned(source_fds[1], stage_fd, "profile.json", profile_size, profile_digest, 0o600)
        for descriptor in source_fds:
            os.close(descriptor)
        source_fds = []
        os.fsync(stage_fd)
        if forwarded:
            raise InterruptedError("interrupted during root-private staging")
        command = [stage + "/r46h-card", "audit-readonly", "--profile", stage + "/profile.json",
                   "--attachment-id", attachment_id, "--evidence-dir", evidence, "--audit-id", audit_id]
        environment = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": "/var/root",
                       "TMPDIR": "/private/tmp", "LC_ALL": "C", "LANG": "C"}
        child = subprocess.Popen(command, env=environment)
        if forwarded and child.poll() is None:
            child.send_signal(forwarded[-1])
        returncode = child.wait()
        if returncode < 0:
            returncode = 128 - returncode
        if forwarded:
            raise InterruptedError("interrupted before privileged receipt handoff")
        active_stage_fd = stage_fd
        stage_fd = None
        cleanup_stage(stage, active_stage_fd)
        payloads = exact_files(evidence, returncode)
        if forwarded:
            raise InterruptedError("interrupted during privileged receipt handoff")
        status = "complete" if returncode == 0 else "failed"
        envelope = {"schema": SCHEMA, "status": status, "returncode": returncode,
                    "evidence_name": evidence_name,
                    "files": {name: base64.b64encode(payload).decode("ascii")
                              for name, payload in payloads.items()}}
        encoded = base64.b64encode(json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode("ascii")).decode("ascii")
        print(PREFIX + ":" + token + ":" + encoded, flush=True)
        return returncode
    except BaseException as error:
        if child is not None and child.poll() is None:
            try:
                child.terminate()
                child.wait(timeout=50)
            except BaseException:
                try:
                    child.kill()
                except BaseException:
                    pass
                try:
                    child.wait(timeout=5)
                except BaseException:
                    pass
        return fail(str(error))
    finally:
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
        for descriptor in source_fds:
            try: os.close(descriptor)
            except OSError: pass
        try: cleanup_stage(stage, stage_fd)
        except BaseException as error: print("WARNING: root-private stage cleanup failed: " + str(error), file=sys.stderr)

raise SystemExit(main())
'''


def privileged_command(
    bindings: ReleaseBindings,
    attachment_id: str,
    audit_id: str,
    evidence_name: str,
    token: str,
    uid: int,
    gid: int,
) -> Sequence[str]:
    if sys.platform != "darwin":
        raise LauncherError("physical read-only audit is enabled only on macOS", EX_UNAVAILABLE)
    required = [Path("/usr/bin/caffeinate"), Path("/usr/bin/sudo"), Path("/usr/bin/python3")]
    for executable in required:
        if not executable.is_file():
            raise LauncherError(f"required system executable is missing: {executable}")
    return [
        "/usr/bin/caffeinate",
        "-im",
        "/usr/bin/sudo",
        "-n",
        "--",
        "/usr/bin/python3",
        "-I",
        "-B",
        "-c",
        PRIVILEGED_BOOTSTRAP,
        str(uid),
        str(gid),
        str(bindings.binary),
        str(bindings.binary_size),
        bindings.binary_sha256,
        str(bindings.profile),
        str(bindings.profile_size),
        bindings.profile_sha256,
        evidence_name,
        attachment_id,
        audit_id,
        token,
    ]


def authorize_sudo(
    *,
    _command: Sequence[str] = ("/usr/bin/sudo", "-v"),
    _timeout_seconds: float = 120.0,
) -> None:
    """Prime sudo in the inherited foreground process group before isolation."""

    process: Optional[subprocess.Popen[bytes]] = None
    forwarded: list[Tuple[int, float]] = []
    old_handlers: Dict[int, Any] = {}

    def forward(signum: int, _frame: object) -> None:
        forwarded.append((signum, time.monotonic()))
        if process is not None and process.poll() is None:
            try:
                process.send_signal(signum)
            except ProcessLookupError:
                pass

    started_at = time.monotonic()
    terminate_sent_at: Optional[float] = None
    kill_sent_at: Optional[float] = None
    try:
        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            old_handlers[signum] = signal.signal(signum, forward)
        process = subprocess.Popen(list(_command))
        if forwarded and process.poll() is None:
            process.send_signal(forwarded[-1][0])
        while True:
            try:
                returncode = process.wait(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                now = time.monotonic()
                if forwarded and now - forwarded[0][1] >= 10 and kill_sent_at is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    kill_sent_at = now
                elif (
                    not forwarded
                    and now - started_at >= _timeout_seconds
                    and terminate_sent_at is None
                ):
                    try:
                        process.terminate()
                    except ProcessLookupError:
                        pass
                    terminate_sent_at = now
                elif (
                    terminate_sent_at is not None
                    and now - terminate_sent_at >= 5
                    and kill_sent_at is None
                ):
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass
                    kill_sent_at = now
                elif kill_sent_at is not None and now - kill_sent_at >= 5:
                    raise LauncherError(
                        "administrator authorization child did not terminate after SIGKILL",
                        EX_SOFTWARE,
                    )
    except OSError as error:
        raise LauncherError("administrator authorization failed", EX_UNAVAILABLE) from error
    finally:
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)
    if forwarded:
        raise LauncherError(
            "administrator authorization was interrupted",
            128 + forwarded[0][0],
        )
    if returncode != 0:
        raise LauncherError(
            f"administrator authorization failed with exit status {returncode}",
            returncode if 0 < returncode <= 255 else EX_UNAVAILABLE,
        )


def run_privileged(command: Sequence[str], token: str, evidence_name: str) -> PrivilegedResult:
    process: Optional[subprocess.Popen[bytes]] = None
    forwarded: list[Tuple[int, float]] = []
    old_handlers: Dict[int, Any] = {}

    def forward(signum: int, _frame: object) -> None:
        forwarded.append((signum, time.monotonic()))
        if process is not None and process.poll() is None:
            try:
                os.killpg(process.pid, signum)
            except (ProcessLookupError, PermissionError):
                pass

    try:
        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            old_handlers[signum] = signal.signal(signum, forward)
        # A new process group lets the parent target the complete
        # caffeinate/sudo/bootstrap chain without creating a new session.
        # Keeping the session preserves sudo's controlling terminal.
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, preexec_fn=os.setpgrp
        )
        if forwarded and process.poll() is None:
            os.killpg(process.pid, forwarded[-1][0])
        kill_sent_at: Optional[float] = None
        while True:
            try:
                output, _ = process.communicate(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                now = time.monotonic()
                if forwarded and kill_sent_at is None and now - forwarded[0][1] >= 130:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
                    kill_sent_at = now
                elif kill_sent_at is not None and now - kill_sent_at >= 5:
                    raise LauncherError(
                        "privileged process tree did not terminate after SIGKILL; "
                        f"recovery evidence may remain at /private/tmp/{evidence_name}",
                        EX_SOFTWARE,
                    )
        returncode = process.returncode
        if returncode is None:
            raise LauncherError("privileged process exited without a status")
    finally:
        for signum, handler in old_handlers.items():
            signal.signal(signum, handler)

    if forwarded:
        raise LauncherError(
            "privileged read-only audit was interrupted; recovery evidence may remain at "
            f"/private/tmp/{evidence_name}",
            128 + forwarded[0][0],
        )

    handoff_lines = []
    prefix = f"{HANDOFF_PREFIX}:{token}:".encode("ascii")
    for line in output.splitlines(keepends=True):
        if line.startswith(prefix):
            handoff_lines.append(line)
        else:
            sys.stdout.buffer.write(line)
    sys.stdout.buffer.flush()
    if len(handoff_lines) != 1:
        raise LauncherError(
            f"privileged audit exited {returncode} without one valid handoff; "
            f"recovery evidence may remain at /private/tmp/{evidence_name}",
            returncode or EX_SOFTWARE,
        )
    result = parse_handoff_line(handoff_lines[0], token)
    if result.evidence_name != evidence_name or result.returncode != returncode:
        raise LauncherError("privileged handoff disagrees with the sudo process status")
    return result


def cleanup_temporary_evidence(
    evidence_name: str,
    files: Mapping[str, bytes],
    *,
    _parent: Path = Path("/private/tmp"),
) -> bool:
    if not re.fullmatch(r"\.r46h-card-readonly-audit\.[0-9a-f]{32}", evidence_name):
        return False
    path = _parent / evidence_name
    try:
        metadata = os.stat(path, follow_symlinks=False)
    except FileNotFoundError:
        return True
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        return False
    descriptor = _open_directory(path)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            return False
        if set(os.listdir(descriptor)) != set(files):
            return False
        for name, expected in files.items():
            member = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=descriptor,
            )
            try:
                member_metadata = os.fstat(member)
                if (
                    not stat.S_ISREG(member_metadata.st_mode)
                    or member_metadata.st_uid != os.geteuid()
                    or member_metadata.st_nlink != 1
                ):
                    return False
                chunks = []
                remaining = member_metadata.st_size
                while remaining:
                    chunk = os.read(member, min(1024 * 1024, remaining))
                    if not chunk:
                        return False
                    chunks.append(chunk)
                    remaining -= len(chunk)
                if os.read(member, 1) or b"".join(chunks) != expected:
                    return False
            finally:
                os.close(member)
        for name in files:
            os.unlink(name, dir_fd=descriptor)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.rmdir(path)
    return True


def _print_candidates(candidates: Sequence[Mapping[str, Any]]) -> None:
    for candidate in candidates:
        print(json.dumps(candidate, sort_keys=True, separators=(",", ":")))


def make_parser(repo_root: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--attachment-id",
        help="exact attachment_id printed by --list; never inferred by size alone",
    )
    parser.add_argument("--list", action="store_true", help="list eligible candidates and exit")
    parser.add_argument("--audit-id", help="lowercase receipt identifier; random by default")
    parser.add_argument(
        "--archive-root",
        type=Path,
        default=repo_root / "mainline" / "out" / "r46h-card-readonly-audits",
        help="absolute directory on proven external macOS storage",
    )
    parser.add_argument(
        "--cache-root",
        help="optional absolute external build-cache root used only for release validation",
    )
    return parser


def run(argv: Optional[Sequence[str]] = None, *, repo_root: Optional[Path] = None) -> int:
    if sys.platform != "darwin":
        raise LauncherError("this launcher is enabled only on macOS", EX_UNAVAILABLE)
    if os.geteuid() == 0:
        raise LauncherError("run the launcher as the invoking user, never directly as root")
    selected_repo = (repo_root or _repo_root_from_script()).resolve(strict=True)
    arguments = make_parser(selected_repo).parse_args(argv)
    if not arguments.list and not arguments.attachment_id:
        raise LauncherError("--attachment-id is required unless --list is used", EX_USAGE)

    bindings = collect_release_bindings(selected_repo, arguments.cache_root)
    candidates = discover_candidates(bindings)
    if arguments.list:
        if arguments.attachment_id or arguments.audit_id:
            raise LauncherError("--list cannot be combined with audit selection", EX_USAGE)
        _print_candidates(candidates)
        return 0
    attachment_id = arguments.attachment_id
    assert isinstance(attachment_id, str)
    selected_candidate = select_candidate(
        candidates, attachment_id, bindings.profile_payload
    )
    audit_id = _validate_audit_id(arguments.audit_id or _default_audit_id())
    driver = _load_build_driver(selected_repo)
    target_physical_id = candidate_whole_disk_id(selected_candidate)
    archive_handle = open_external_archive_root(
        arguments.archive_root,
        driver,
        forbidden_physical_id=target_physical_id,
    )
    try:
        require_archive_target_separation(archive_handle, selected_candidate)
        token = secrets.token_hex(16)
        evidence_name = f".r46h-card-readonly-audit.{secrets.token_hex(16)}"
        command = privileged_command(
            bindings,
            attachment_id,
            audit_id,
            evidence_name,
            token,
            os.geteuid(),
            os.getegid(),
        )
        print(
            "R46H macOS profile-bound read-only audit\n"
            f"commit={bindings.git_commit} generation={bindings.generation.name}\n"
            f"profile_sha256={bindings.profile_sha256}\n"
            f"tool_sha256={bindings.binary_sha256}\n"
            f"attachment_id={attachment_id}\n"
            "No native write capability is present. One sudo authorization claims, reads, and "
            "ejects the exact selected attachment. Unmount/eject may flush metadata already "
            "dirtied by macOS automount."
        )
        # sudo -v remains in this foreground process group so it can read one
        # administrator password.  The audited chain itself is non-interactive
        # and can then be isolated into a group that this parent can terminate.
        authorize_sudo()
        result = run_privileged(command, token, evidence_name)
        archive = validate_and_publish_privileged_result(
            archive_handle,
            driver,
            result,
            bindings,
            selected_candidate,
            attachment_id,
            audit_id,
        )
    finally:
        os.close(archive_handle.descriptor)
    cleaned = cleanup_temporary_evidence(result.evidence_name, result.files)
    if not cleaned:
        print(
            f"WARNING: validated temporary evidence was archived but not removed: "
            f"/private/tmp/{result.evidence_name}",
            file=sys.stderr,
        )
    if result.status != "complete":
        raise LauncherError(
            f"read-only audit failed; flat failure evidence archived at {archive}",
            result.returncode or 1,
        )
    print(f"PASS: read-only receipt verified and archived after sudo exit: {archive}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        return run(argv)
    except LauncherError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return error.exit_code
    except subprocess.CalledProcessError as error:
        print(f"ERROR: command failed with exit status {error.returncode}", file=sys.stderr)
        return error.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())
