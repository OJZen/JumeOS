#!/usr/bin/env python3
"""Generate a deterministic, fail-closed R46H EASYROMS deployment bundle."""

from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import errno
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import stat
import subprocess
import tarfile
import threading
from typing import Any
import zlib


IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
RELEASE_RE = re.compile(r"^6\.12\.99-r46h-mainline-[A-Za-z0-9._-]+$")
PURPOSE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_REL_RE = re.compile(r"^[A-Za-z0-9._+/-]+$")
TOKEN_RE = re.compile(r"@[A-Z][A-Z0-9_]*@")
MODULE_SUFFIXES = (".ko", ".ko.gz", ".ko.xz", ".ko.zst")
GENERATOR_RELPATH = "mainline/scripts/generate-easyroms-bundle.py"
TEMPLATE_RELPATHS = (
    "mainline/deploy/templates/boot.ini.in",
    "mainline/deploy/templates/bootstrap-target.sh.in",
    "mainline/deploy/templates/install-modules.sh.in",
    "mainline/deploy/templates/stage-easyroms-macos.sh.in",
    "mainline/deploy/templates/switch-boot.sh.in",
    "mainline/deploy/templates/target-common.sh.in",
)
EXPECTED_ROOT_SPEC = "PARTUUID=c9f931c9-02"
EXPECTED_CONSOLE = "ttyS2,115200n8"
EXPECTED_DTB_COMPATIBLE = "rockchip,rk3326-r46h-linux"
MAX_COMPRESSED_PACKAGE_BYTES = 256 * 1024 * 1024
MAX_RAW_TAR_BYTES = 512 * 1024 * 1024
MAX_PACKAGE_MEMBERS = 20_000
MAX_RAW_TAR_HEADERS = 40_000
MAX_SINGLE_MEMBER_BYTES = 256 * 1024 * 1024
MAX_TOTAL_MEMBER_BYTES = 384 * 1024 * 1024
MAX_PACKAGE_PATH_BYTES = 4096
MAX_PACKAGE_PATH_COMPONENTS = 256
MAX_PACKAGE_DIRECTORY_DEPTH = 128
MAX_EXTRACTION_INODES = 100_000
MAX_PROFILE_ANCHORS = 128
MAX_GIT_DIAGNOSTIC_BYTES = 64 * 1024
TAR_BLOCK_SIZE = 512
MAX_SAFE_SHELL_INTEGER = (1 << 63) - 1
MAX_SOURCE_DATE_EPOCH = 253402300799
TRUSTED_GIT = Path("/usr/bin/git")
SAFE_EXEC_PATH = "/usr/bin:/bin"
GIT_CONFIG_OVERRIDES = (
    "core.fsmonitor=false",
    "core.untrackedCache=false",
    "core.hooksPath=/dev/null",
    "core.attributesFile=/dev/null",
    "tar.umask=0002",
)
AUDITED_CARD_GEOMETRIES = {
    "hl-r46h-v22-g92-v1": {
        "whole_size": 31914983424,
        "sector_size": 512,
        "partition_scheme": "FDisk_partition_scheme",
        "boot": {
            "number": 1,
            "offset": 16777216,
            "size": 117440512,
            "volume_uuid": "575BC58C-96FA-3E4F-958B-7A30D5210C3D",
        },
        "root": {
            "number": 2,
            "offset": 134217728,
            "size": 10716877312,
            "partuuid": "c9f931c9-02",
        },
        "easyroms": {
            "number": 3,
            "offset": 10851095040,
            "size": 21063888384,
            "volume_uuid": "2D584C38-94B7-38C2-B369-6A7A82C72CC2",
        },
        "g92_prefix_size": 16777216,
        "g92_prefix_sha256": "91a1f0d5f84e9589843ebf1eb0889669a5da64632fd258ef872f890b446a998b",
    },
    "hl-r46h-v22-g92-31719424000-v1": {
        "whole_size": 31719424000,
        "sector_size": 512,
        "partition_scheme": "FDisk_partition_scheme",
        "boot": {
            "number": 1,
            "offset": 16777216,
            "size": 117440512,
            "volume_uuid": "575BC58C-96FA-3E4F-958B-7A30D5210C3D",
        },
        "root": {
            "number": 2,
            "offset": 134217728,
            "size": 10716877312,
            "partuuid": "c9f931c9-02",
        },
        "easyroms": {
            "number": 3,
            "offset": 10851095040,
            "size": 20868328960,
            "volume_uuid": "E1F5295C-4B12-A54A-ACB7-317194240001",
        },
        "g92_prefix_size": 16777216,
        "g92_prefix_sha256": "97ede10075b3257c638a04b3044c9dda2d8dd9adc6f6fee3be7b004a31fb135e",
    },
}
AUDITED_UBOOT_IDENTITY = {
    "root_dtb_path": "arkos4clone-uboot.dtb",
    "console_dtb_path": "consoles/r46h/arkos4clone-uboot.dtb",
    "dtb_size": 59991,
    "dtb_sha256": "dd892bbd8dd1e5c51f7b3be2390faab4355e6932aef6a48b030b2591a7b0bf4c",
}
AUDITED_FALLBACK_IDENTITY = {
    "release": "6.12.99-r46h-mainline-v0.2",
    "boot_path": "boot.ini.v0.2-known-good",
    "boot_test_path": "boot.ini.test",
    "boot_size": 1327,
    "boot_sha256": "921f439aa602bb8bc84ffe39cdb00a9ffd03dab1bed1d8960d2e30fdff4703cc",
    "image_path": "Image.mainline-test.gz",
    "image_size": 14919642,
    "image_sha256": "fb8b8d39262e087af5a9efa73c4cb8f5f7d0559f9d2b0d30acc4dd9156140abb",
    "dtb_path": "rk3326-r46h-mainline-test.dtb",
    "dtb_size": 49448,
    "dtb_sha256": "074bb3121fafe5df96872628ab22db03ffd63adf53c990e779e5a0e2f54b7a2b",
    "module_count": 1276,
    "module_file_count": 1290,
    "module_tree_sha256_allowed": [
        "82b2e768c292a07d8c2901765d87dafa352f5dab4f86667d53c4086185017b60",
        "a8c889a65a24cf6c953524b932ca6f6af94b59108e5185cada626b7832e0c2a8",
    ],
}


class BundleError(RuntimeError):
    pass


def stat_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def stable_file_state(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def regular_file(path: Path, label: str) -> Path:
    if not path.is_file() or path.is_symlink():
        raise BundleError(f"{label} must be a regular non-symlink file: {path}")
    return path.resolve(strict=True)


def reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number {value}")


def reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key}")
        result[key] = value
    return result


def require_finite_json_numbers(value: Any) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite JSON number")
    if isinstance(value, dict):
        for nested in value.values():
            require_finite_json_numbers(nested)
    elif isinstance(value, list):
        for nested in value:
            require_finite_json_numbers(nested)


def load_json_bytes(raw: bytes, label: str) -> tuple[dict[str, Any], str]:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=reject_duplicate_json_keys,
            parse_constant=reject_json_constant,
        )
        require_finite_json_numbers(value)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise BundleError(f"invalid {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise BundleError(f"{label} must contain one JSON object")
    return value, sha_bytes(raw)


def load_json(path: Path, label: str) -> tuple[dict[str, Any], str]:
    path = regular_file(path, label)
    return load_json_bytes(path.read_bytes(), label)


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


def require_string(parent: dict[str, Any], key: str, pattern: re.Pattern[str] | None = None) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value:
        raise BundleError(f"{key} must be a non-empty string")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise BundleError(f"unsafe {key}: {value}")
    return value


def require_int(
    parent: dict[str, Any],
    key: str,
    minimum: int = 1,
    maximum: int = MAX_SAFE_SHELL_INTEGER,
) -> int:
    value = parent.get(key)
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < minimum
        or value > maximum
    ):
        raise BundleError(f"{key} must be an integer in [{minimum}, {maximum}]")
    return value


def require_sha(parent: dict[str, Any], key: str) -> str:
    return require_string(parent, key, SHA_RE)


def require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise BundleError(f"{label} fields mismatch; missing={missing}, extra={extra}")


def safe_relative(value: str, label: str, *, basename_only: bool = False) -> str:
    if SAFE_REL_RE.fullmatch(value) is None or value.startswith("/") or "//" in value:
        raise BundleError(f"unsafe {label}: {value}")
    parts = PurePosixPath(value).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise BundleError(f"unsafe {label}: {value}")
    if basename_only and len(parts) != 1:
        raise BundleError(f"{label} must be a basename: {value}")
    return value


def clean_git_environment() -> dict[str, str]:
    return {
        "PATH": SAFE_EXEC_PATH,
        "LC_ALL": "C",
        "LANG": "C",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_OPTIONAL_LOCKS": "0",
    }


def git_command(repo_root: Path, args: list[str]) -> list[str]:
    try:
        git_state = TRUSTED_GIT.stat(follow_symlinks=False)
    except OSError as exc:
        raise BundleError(f"trusted Git executable is unavailable: {TRUSTED_GIT}: {exc}") from exc
    if (
        not stat.S_ISREG(git_state.st_mode)
        or TRUSTED_GIT.is_symlink()
        or git_state.st_uid != 0
        or stat.S_IMODE(git_state.st_mode) & 0o022
        or not os.access(TRUSTED_GIT, os.X_OK)
    ):
        raise BundleError(f"trusted Git executable has unsafe identity or mode: {TRUSTED_GIT}")
    command = [str(TRUSTED_GIT)]
    for override in GIT_CONFIG_OVERRIDES:
        command.extend(("-c", override))
    command.extend(("-C", str(repo_root), *args))
    return command


def run_git(repo_root: Path, args: list[str], label: str) -> bytes:
    result = subprocess.run(
        git_command(repo_root, args),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=clean_git_environment(),
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise BundleError(f"cannot {label}: {detail or f'git exited {result.returncode}'}")
    return result.stdout


def require_canonical_archive_repository_state(repo_root: Path) -> None:
    local_config = run_git(
        repo_root,
        ["config", "--null", "--includes", "--name-only", "--list"],
        "inspect repository-local archive configuration",
    )
    for raw_name in local_config.split(b"\0"):
        if not raw_name:
            continue
        try:
            name = raw_name.decode("utf-8", "strict").lower()
        except UnicodeDecodeError as exc:
            raise BundleError("repository-local Git configuration is not canonical text") from exc
        if name.startswith("tar.") and name != "tar.umask":
            raise BundleError(
                f"repository-local archive-affecting Git configuration is forbidden: {name}"
            )

    attributes_raw = run_git(
        repo_root,
        ["rev-parse", "--path-format=absolute", "--git-path", "info/attributes"],
        "locate repository-local archive attributes",
    )
    if b"\0" in attributes_raw:
        raise BundleError("repository-local archive attributes path is malformed")
    try:
        attributes_text = attributes_raw.decode("utf-8", "strict").rstrip("\n")
    except UnicodeDecodeError as exc:
        raise BundleError("repository-local archive attributes path is not UTF-8") from exc
    if not attributes_text or "\n" in attributes_text:
        raise BundleError("repository-local archive attributes path is malformed")
    attributes_path = Path(attributes_text)
    if not attributes_path.is_absolute():
        raise BundleError("repository-local archive attributes path is not absolute")
    try:
        os.lstat(attributes_path)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise BundleError(
            f"cannot inspect repository-local archive attributes: {exc}"
        ) from exc
    raise BundleError(
        f"repository-local info/attributes is forbidden for canonical archives: {attributes_path}"
    )


def git_archive_sha256(repo_root: Path, head: str) -> str:
    # Persistent repository-local inputs are rejected before and after archive.
    # A malicious process with the same UID can still race Git's own metadata
    # reads; defending against that requires an isolated object store, not a
    # worktree-side generator check.
    require_canonical_archive_repository_state(repo_root)
    with subprocess.Popen(
        git_command(
            repo_root,
            ["archive", "--format=tar", head, "--", "mainline"],
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=clean_git_environment(),
    ) as process:
        assert process.stdout is not None
        assert process.stderr is not None
        diagnostic = bytearray()
        diagnostic_truncated = threading.Event()
        drain_errors: list[BaseException] = []

        def drain_stderr() -> None:
            try:
                for block in iter(lambda: process.stderr.read(64 * 1024), b""):
                    remaining = MAX_GIT_DIAGNOSTIC_BYTES - len(diagnostic)
                    if remaining > 0:
                        diagnostic.extend(block[:remaining])
                    if len(block) > remaining:
                        diagnostic_truncated.set()
            except BaseException as exc:  # surfaced in the calling thread below
                drain_errors.append(exc)

        drain_thread = threading.Thread(
            target=drain_stderr,
            name="r46h-git-archive-stderr",
            daemon=True,
        )
        drain_thread.start()
        digest = hashlib.sha256()
        try:
            for block in iter(lambda: process.stdout.read(1024 * 1024), b""):
                digest.update(block)
            returncode = process.wait()
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait()
            drain_thread.join()
        if drain_errors:
            raise BundleError(f"cannot read Git archive diagnostics: {drain_errors[0]}")
    if returncode != 0:
        detail = bytes(diagnostic).decode("utf-8", "replace").strip()
        if diagnostic_truncated.is_set():
            detail = f"{detail}\n[diagnostics truncated]" if detail else "[diagnostics truncated]"
        raise BundleError(
            f"cannot archive committed mainline source: {detail or f'git exited {returncode}'}"
        )
    require_canonical_archive_repository_state(repo_root)
    return digest.hexdigest()


def require_clean_mainline(repo_root: Path) -> None:
    status = run_git(
        repo_root,
        ["status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none", "--", "mainline"],
        "inspect mainline worktree",
    )
    if status:
        lines = status.decode("utf-8", "replace").splitlines()
        raise BundleError(f"mainline worktree must be completely clean: {lines[:8]}")


def require_head_blob(
    repo_root: Path, head: str, relative: str, expected_mode: str
) -> bytes:
    if safe_relative(relative, "tracked source path") != relative:
        raise BundleError(f"unsafe tracked source path: {relative}")
    listing = run_git(
        repo_root,
        ["ls-tree", "-z", head, "--", relative],
        f"resolve committed source {relative}",
    )
    expected_suffix = b"\t" + relative.encode("utf-8") + b"\0"
    if not listing.endswith(expected_suffix) or listing.count(b"\0") != 1:
        raise BundleError(f"committed source is not one exact HEAD entry: {relative}")
    metadata = listing[: -len(expected_suffix)].decode("ascii", "strict").split()
    if len(metadata) != 3 or metadata[0] != expected_mode or metadata[1] != "blob":
        actual = metadata[:2] if len(metadata) >= 2 else metadata
        raise BundleError(
            f"committed source mode/type mismatch for {relative}; "
            f"expected={expected_mode} blob, actual={actual}"
        )
    return run_git(
        repo_root,
        ["cat-file", "blob", f"{head}:{relative}"],
        f"read committed source {relative}",
    )


def require_unmasked_index_entries(repo_root: Path, relative_paths: tuple[str, ...]) -> None:
    listing = run_git(
        repo_root,
        ["ls-files", "-v", "-z", "--", "mainline"],
        "inspect mainline index flags",
    )
    entries = [entry for entry in listing.split(b"\0") if entry]
    expected = set(relative_paths)
    actual: set[str] = set()
    for entry in entries:
        if len(entry) < 3 or entry[1:2] != b" ":
            raise BundleError("cannot parse committed input index flags")
        try:
            path = entry[2:].decode("utf-8", "strict")
            tag = entry[:1].decode("ascii", "strict")
        except UnicodeDecodeError as exc:
            raise BundleError("committed input index flags are not canonical text") from exc
        if path in actual:
            raise BundleError(f"duplicate committed input index entry: {path}")
        actual.add(path)
        if tag != "H":
            raise BundleError(
                f"committed input uses assume-unchanged, skip-worktree, or another unsafe index state: {path}"
            )
    if not actual or not expected.issubset(actual):
        raise BundleError("committed source index entry set is incomplete")


def require_running_generator_matches_head(script_path: Path, expected_blob: bytes) -> None:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(script_path, flags)
    except OSError as exc:
        raise BundleError(f"cannot open running generator for provenance check: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        named = script_path.stat(follow_symlinks=False)
        before_identity = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_nlink,
            before.st_uid,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        if (
            not stat.S_ISREG(before.st_mode)
            or (named.st_dev, named.st_ino) != (before.st_dev, before.st_ino)
            or stat.S_IMODE(before.st_mode) != 0o755
            or before.st_nlink != 1
            or before.st_uid != os.geteuid()
        ):
            raise BundleError("running generator has unsafe mode, owner, link count, or identity")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            running_bytes = handle.read()
        after = os.fstat(descriptor)
        after_identity = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_nlink,
            after.st_uid,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if after_identity != before_identity:
            raise BundleError("running generator changed while checking provenance")
        if running_bytes != expected_blob:
            raise BundleError("running generator bytes do not match its exact HEAD blob")
    finally:
        os.close(descriptor)


def resolve_deploy_input(path: Path, deploy_dir: Path, repo_root: Path, label: str) -> str:
    resolved = regular_file(path, label)
    try:
        resolved.relative_to(deploy_dir)
    except ValueError as exc:
        raise BundleError(f"{label} must be inside mainline/deploy: {resolved}") from exc
    relative = resolved.relative_to(repo_root).as_posix()
    safe_relative(relative, f"{label} repository path")
    return relative


def establish_repository_binding(
    package: dict[str, Any], card_path: Path, baseline_path: Path
) -> dict[str, Any]:
    script_path = Path(__file__).resolve(strict=True)
    candidate_repo = script_path.parents[2]
    top_level = run_git(candidate_repo, ["rev-parse", "--show-toplevel"], "locate source repository")
    repo_root = Path(top_level.decode("utf-8", "strict").strip()).resolve(strict=True)
    expected_script = repo_root / GENERATOR_RELPATH
    if script_path != expected_script:
        raise BundleError(
            f"generator must run from {GENERATOR_RELPATH} in its source repository"
        )
    deploy_dir = repo_root / "mainline/deploy"
    card_relative = resolve_deploy_input(card_path, deploy_dir, repo_root, "card profile")
    baseline_relative = resolve_deploy_input(
        baseline_path, deploy_dir, repo_root, "current baseline"
    )

    require_clean_mainline(repo_root)
    head = run_git(repo_root, ["rev-parse", "--verify", "HEAD"], "resolve source HEAD")
    head_text = head.decode("ascii", "strict").strip()
    if re.fullmatch(r"[0-9a-f]{40}", head_text) is None:
        raise BundleError("source HEAD is not a full SHA-1 commit ID")
    if package["source_git_commit"] != head_text:
        raise BundleError("canonical package source commit does not match source HEAD")

    tracked_modes = {
        GENERATOR_RELPATH: "100755",
        card_relative: "100644",
        baseline_relative: "100644",
        **{relative: "100644" for relative in TEMPLATE_RELPATHS},
    }
    require_unmasked_index_entries(repo_root, tuple(tracked_modes))
    blobs = {
        relative: require_head_blob(repo_root, head_text, relative, mode)
        for relative, mode in tracked_modes.items()
    }
    require_running_generator_matches_head(script_path, blobs[GENERATOR_RELPATH])
    snapshot = git_archive_sha256(repo_root, head_text)
    if package["source_snapshot_sha256"] != snapshot:
        raise BundleError("canonical package source snapshot does not match git archive of HEAD mainline")
    require_clean_mainline(repo_root)
    if run_git(repo_root, ["rev-parse", "--verify", "HEAD"], "recheck source HEAD").strip() != head.strip():
        raise BundleError("source HEAD changed while establishing provenance")
    return {
        "repo_root": repo_root,
        "head": head_text,
        "snapshot_sha256": snapshot,
        "card_relative": card_relative,
        "baseline_relative": baseline_relative,
        "tracked_paths": tuple(tracked_modes),
        "blobs": blobs,
    }


def recheck_repository_binding(binding: dict[str, Any]) -> None:
    repo_root = binding["repo_root"]
    if not isinstance(repo_root, Path):
        raise BundleError("invalid internal repository binding")
    tracked_paths = binding.get("tracked_paths")
    if (
        not isinstance(tracked_paths, tuple)
        or not tracked_paths
        or any(not isinstance(path, str) for path in tracked_paths)
    ):
        raise BundleError("invalid internal tracked-path binding")
    require_clean_mainline(repo_root)
    require_unmasked_index_entries(repo_root, tracked_paths)
    head = run_git(repo_root, ["rev-parse", "--verify", "HEAD"], "recheck source HEAD")
    if head.decode("ascii", "strict").strip() != binding["head"]:
        raise BundleError("source HEAD changed before bundle publication")
    snapshot = git_archive_sha256(repo_root, binding["head"])
    if snapshot != binding["snapshot_sha256"]:
        raise BundleError("committed mainline source changed before bundle publication")


def parse_kv(data: bytes, label: str) -> dict[str, str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BundleError(f"{label} is not UTF-8") from exc
    result: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line or "=" not in line:
            raise BundleError(f"{label}:{line_number}: malformed field")
        key, value = line.split("=", 1)
        if re.fullmatch(r"[a-z][a-z0-9_]*", key) is None or not value:
            raise BundleError(f"{label}:{line_number}: unsafe field")
        if key in result:
            raise BundleError(f"{label}: duplicate field {key}")
        result[key] = value
    return result


def parse_canonical_octal(field: bytes, digits: int, label: str) -> int:
    if len(field) != digits + 1 or field[-1:] != b"\0":
        raise BundleError(f"non-canonical tar {label} field")
    numeric = field[:digits]
    if not numeric or any(byte < ord("0") or byte > ord("7") for byte in numeric):
        raise BundleError(f"non-canonical tar {label} field")
    return int(numeric, 8)


def parse_tar_cstring(field: bytes, label: str) -> bytes:
    try:
        end = field.index(0)
    except ValueError as exc:
        raise BundleError(f"non-canonical tar {label} field") from exc
    if any(field[end + 1 :]):
        raise BundleError(f"non-canonical tar {label} padding")
    return field[:end]


def verify_tar_header_checksum(header: bytes) -> None:
    checksum_field = header[148:156]
    if re.fullmatch(rb"[0-7]{6}\0 ", checksum_field) is None:
        raise BundleError("non-canonical tar checksum field")
    stored = int(checksum_field[:6], 8)
    calculated = sum(header[:148]) + (8 * ord(" ")) + sum(header[156:])
    if stored != calculated:
        raise BundleError("tar header checksum mismatch")


def write_bounded_raw_block(raw_file: Any, data: bytes, total: int) -> int:
    total += len(data)
    if total > MAX_RAW_TAR_BYTES:
        raise BundleError("canonical package exceeds raw tar byte budget")
    raw_file.write(data)
    return total


def open_package_source(
    package_tar: Path,
) -> tuple[Path, int, tuple[int, ...]]:
    lexical_path = Path(os.path.abspath(os.fspath(package_tar)))
    try:
        candidate = os.stat(lexical_path, follow_symlinks=False)
    except OSError as exc:
        raise BundleError(f"cannot inspect canonical package source: {exc}") from exc
    if not stat.S_ISREG(candidate.st_mode):
        raise BundleError(
            "canonical package source must be one stable regular non-symlink file"
        )
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        descriptor = os.open(lexical_path, flags)
    except OSError as exc:
        raise BundleError(f"cannot safely open canonical package source: {exc}") from exc
    try:
        opened = os.fstat(descriptor)
        try:
            named = os.stat(lexical_path, follow_symlinks=False)
        except OSError as exc:
            raise BundleError(
                f"canonical package source path changed while opening: {exc}"
            ) from exc
        opened_state = stable_file_state(opened)
        if (
            not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or stable_file_state(named) != opened_state
        ):
            raise BundleError(
                "canonical package source must be one stable regular non-symlink file"
            )
        if opened.st_size <= 0 or opened.st_size > MAX_COMPRESSED_PACKAGE_BYTES:
            raise BundleError("canonical package exceeds compressed byte budget")
        return lexical_path, descriptor, opened_state
    except Exception:
        os.close(descriptor)
        raise


def verify_package_source(
    package_tar: Path, descriptor: int, expected_state: tuple[int, ...]
) -> None:
    opened = os.fstat(descriptor)
    try:
        named = os.stat(package_tar, follow_symlinks=False)
    except OSError as exc:
        raise BundleError(f"canonical package source path changed while being read: {exc}") from exc
    if (
        not stat.S_ISREG(opened.st_mode)
        or not stat.S_ISREG(named.st_mode)
        or stable_file_state(opened) != expected_state
        or stable_file_state(named) != expected_state
    ):
        raise BundleError("canonical package source identity changed while being read")


def decompress_package_to_temp(
    package_fd: int, compressed_size: int
) -> tuple[Any, int, int, str]:
    if compressed_size > MAX_COMPRESSED_PACKAGE_BYTES:
        raise BundleError("canonical package exceeds compressed byte budget")
    os.lseek(package_fd, 0, os.SEEK_SET)
    with os.fdopen(package_fd, "rb", closefd=False) as source:
        gzip_header = source.read(10)
        if (
            len(gzip_header) != 10
            or gzip_header[:3] != b"\x1f\x8b\x08"
            or gzip_header[3] != 0
            or gzip_header[4:8] != b"\0\0\0\0"
            or gzip_header[8] != 2
            or gzip_header[9] != 3
        ):
            raise BundleError("canonical package has non-canonical gzip header")
        source.seek(0)
        raw_file = io.BytesIO()
        decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
        compressed_digest = hashlib.sha256()
        compressed_bytes_read = 0
        total = 0
        reached_eof = False
        try:
            while True:
                compressed = source.read(1024 * 1024)
                if not compressed:
                    break
                compressed_digest.update(compressed)
                compressed_bytes_read += len(compressed)
                if compressed_bytes_read > MAX_COMPRESSED_PACKAGE_BYTES:
                    raise BundleError("canonical package exceeds compressed byte budget")
                if reached_eof:
                    raise BundleError("canonical package contains trailing or concatenated gzip data")
                pending = compressed
                while pending:
                    try:
                        output = decompressor.decompress(pending, 1024 * 1024)
                    except zlib.error as exc:
                        raise BundleError(f"cannot decompress canonical package: {exc}") from exc
                    total = write_bounded_raw_block(raw_file, output, total)
                    pending = decompressor.unconsumed_tail
                    if decompressor.eof:
                        if decompressor.unused_data or pending:
                            raise BundleError(
                                "canonical package contains trailing or concatenated gzip data"
                            )
                        reached_eof = True
                        break
            if not reached_eof:
                raise BundleError("canonical package gzip stream is truncated")
            try:
                tail = decompressor.flush()
            except zlib.error as exc:
                raise BundleError(f"cannot finish canonical package decompression: {exc}") from exc
            total = write_bounded_raw_block(raw_file, tail, total)
            if total == 0 or total % TAR_BLOCK_SIZE:
                raise BundleError("canonical package raw tar size is invalid")
            if compressed_bytes_read != compressed_size:
                raise BundleError("canonical package size changed while being read")
            raw_file.seek(0)
            return raw_file, total, compressed_size, compressed_digest.hexdigest()
        except Exception:
            raw_file.close()
            raise


def validate_raw_tar(package_fd: int, compressed_size: int) -> dict[str, Any]:
    raw_file, raw_size, compressed_size, compressed_sha256 = decompress_package_to_temp(
        package_fd, compressed_size
    )
    entries: list[tuple[str, bytes, int, int]] = []
    header_count = 0
    member_bytes = 0
    pending_long_name: bytes | None = None
    try:
        while raw_file.tell() < raw_size:
            header = raw_file.read(TAR_BLOCK_SIZE)
            if len(header) != TAR_BLOCK_SIZE:
                raise BundleError("canonical package has a partial tar header")
            if not any(header):
                if pending_long_name is not None:
                    raise BundleError("orphan GNU longname before tar end marker")
                second = raw_file.read(TAR_BLOCK_SIZE)
                if len(second) != TAR_BLOCK_SIZE or any(second):
                    raise BundleError("canonical package lacks two tar end marker blocks")
                while True:
                    trailing = raw_file.read(1024 * 1024)
                    if not trailing:
                        break
                    if any(trailing):
                        raise BundleError("canonical package contains data after tar end marker")
                break

            header_count += 1
            if header_count > MAX_RAW_TAR_HEADERS:
                raise BundleError("canonical package exceeds raw tar header budget")
            verify_tar_header_checksum(header)
            if header[257:265] != b"ustar  \0":
                raise BundleError("canonical package is not GNU tar format")
            if (
                any(header[157:257])
                or any(header[265:345])
                or any(header[345:500])
                or any(header[500:512])
            ):
                raise BundleError("canonical package tar header contains hidden metadata")
            entry_type = header[156:157]
            if entry_type in {
                tarfile.GNUTYPE_LONGLINK,
                tarfile.XHDTYPE,
                tarfile.XGLTYPE,
                tarfile.GNUTYPE_SPARSE,
            }:
                raise BundleError("canonical package contains forbidden hidden tar extension")
            if entry_type not in {
                tarfile.REGTYPE,
                tarfile.DIRTYPE,
                tarfile.GNUTYPE_LONGNAME,
            }:
                raise BundleError("canonical package contains a non-canonical raw member type")
            size = parse_canonical_octal(header[124:136], 11, "size")
            if size > MAX_SINGLE_MEMBER_BYTES:
                raise BundleError("canonical package exceeds single-member byte budget")
            if entry_type == tarfile.GNUTYPE_LONGNAME and not (
                102 <= size <= MAX_PACKAGE_PATH_BYTES + 1
            ):
                raise BundleError("GNU longname record is not canonical or necessary")
            data_blocks = ((size + TAR_BLOCK_SIZE - 1) // TAR_BLOCK_SIZE) * TAR_BLOCK_SIZE
            data = raw_file.read(data_blocks)
            if len(data) != data_blocks:
                raise BundleError("canonical package member data is truncated")
            if any(data[size:]):
                raise BundleError("canonical package member padding is nonzero")

            if entry_type == tarfile.GNUTYPE_LONGNAME:
                if pending_long_name is not None:
                    raise BundleError("stacked GNU longname records are not canonical")
                long_name_bytes = data[: max(0, size - 1)]
                try:
                    long_name_text = long_name_bytes.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise BundleError(
                        "canonical package member name is not UTF-8"
                    ) from exc
                long_name_parts = PurePosixPath(long_name_text).parts
                if len(long_name_parts) > MAX_PACKAGE_PATH_COMPONENTS:
                    raise BundleError(
                        "canonical package member path exceeds component budget"
                    )
                if max(0, len(long_name_parts) - 1) > MAX_PACKAGE_DIRECTORY_DEPTH:
                    raise BundleError(
                        "canonical package member path exceeds directory-depth budget"
                    )
                if (
                    parse_tar_cstring(header[:100], "longname name") != b"././@LongLink"
                    or parse_canonical_octal(header[100:108], 7, "longname mode") != 0o644
                    or parse_canonical_octal(header[108:116], 7, "longname uid") != 0
                    or parse_canonical_octal(header[116:124], 7, "longname gid") != 0
                    or parse_canonical_octal(header[136:148], 11, "longname mtime") != 0
                    or not data[:size].endswith(b"\0")
                    or b"\0" in data[: size - 1]
                ):
                    raise BundleError("GNU longname record is not canonical or necessary")
                pending_long_name = data[: size - 1]
                continue

            expected_mode = 0o755 if entry_type == tarfile.DIRTYPE else 0o644
            mode = parse_canonical_octal(header[100:108], 7, "mode")
            uid = parse_canonical_octal(header[108:116], 7, "uid")
            gid = parse_canonical_octal(header[116:124], 7, "gid")
            mtime = parse_canonical_octal(header[136:148], 11, "mtime")
            if mode != expected_mode or uid != 0 or gid != 0:
                raise BundleError("canonical package raw member metadata mismatch")
            if entry_type == tarfile.DIRTYPE and size != 0:
                raise BundleError("canonical package directory has nonzero size")
            member_bytes += size
            if member_bytes > MAX_TOTAL_MEMBER_BYTES:
                raise BundleError("canonical package exceeds total member byte budget")

            raw_name_field = header[:100]
            if pending_long_name is not None:
                if raw_name_field != pending_long_name[:100]:
                    raise BundleError("GNU longname does not match its following header")
                raw_name = pending_long_name
                pending_long_name = None
            else:
                raw_name = (
                    parse_tar_cstring(raw_name_field, "name")
                    if b"\0" in raw_name_field
                    else raw_name_field
                )
            if entry_type == tarfile.DIRTYPE:
                if not raw_name.endswith(b"/"):
                    raise BundleError("canonical package directory name lacks trailing slash")
                raw_name = raw_name[:-1]
            elif raw_name.endswith(b"/"):
                raise BundleError("canonical package file name has trailing slash")
            try:
                logical_name = raw_name.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise BundleError("canonical package member name is not UTF-8") from exc
            if len(raw_name) > MAX_PACKAGE_PATH_BYTES:
                raise BundleError("canonical package member path exceeds budget")
            path_parts = PurePosixPath(logical_name).parts
            if len(path_parts) > MAX_PACKAGE_PATH_COMPONENTS:
                raise BundleError("canonical package member path exceeds component budget")
            if max(0, len(path_parts) - 1) > MAX_PACKAGE_DIRECTORY_DEPTH:
                raise BundleError("canonical package member path exceeds directory-depth budget")
            entries.append((logical_name, entry_type, size, mtime))
            if len(entries) > MAX_PACKAGE_MEMBERS:
                raise BundleError("canonical package exceeds member-count budget")
        else:
            raise BundleError("canonical package lacks tar end marker")
        if not entries:
            raise BundleError("canonical package has no logical members")
        mtimes = {entry[3] for entry in entries}
        if len(mtimes) != 1:
            raise BundleError("canonical package logical member mtimes are inconsistent")
        raw_file.seek(0)
        return {
            "entries": entries,
            "mtime": next(iter(mtimes)),
            "raw_size": raw_size,
            "member_bytes": member_bytes,
            "compressed_size": compressed_size,
            "compressed_sha256": compressed_sha256,
            "file": raw_file,
        }
    except Exception:
        raw_file.close()
        raise


def _read_package_from_open_source(
    package_tar: Path, package_fd: int, source_state: tuple[int, ...]
) -> dict[str, Any]:
    raw_tar = validate_raw_tar(package_fd, source_state[6])
    try:
        archive = tarfile.open(fileobj=raw_tar["file"], mode="r:")
    except (tarfile.TarError, ValueError, OSError) as exc:
        raw_tar["file"].close()
        raise BundleError(f"cannot open canonical package: {exc}") from exc
    with raw_tar["file"], archive:
        try:
            members = archive.getmembers()
        except (tarfile.TarError, ValueError, OSError) as exc:
            raise BundleError(f"cannot read canonical package: {exc}") from exc
        if not members:
            raise BundleError("canonical package is empty")
        if archive.pax_headers:
            raise BundleError("package contains non-canonical global PAX metadata")
        logical_entries = [
            (member.name, member.type, member.size, int(member.mtime))
            for member in members
        ]
        if logical_entries != raw_tar["entries"]:
            raise BundleError("raw and logical tar member views do not match exactly")
        roots: set[str] = set()
        member_names: set[str] = set()
        regular_members: dict[str, tarfile.TarInfo] = {}
        directory_members: set[str] = set()
        ordered_names: list[str] = []
        for member in members:
            path = PurePosixPath(member.name)
            canonical_name = path.as_posix()
            if (
                path.is_absolute()
                or not path.parts
                or member.name != canonical_name
                or SAFE_REL_RE.fullmatch(member.name) is None
                or any(part in {"", ".", ".."} for part in path.parts)
            ):
                raise BundleError(f"non-canonical package path: {member.name}")
            if member.name in member_names:
                raise BundleError(f"duplicate package member: {member.name}")
            member_names.add(member.name)
            ordered_names.append(member.name)
            roots.add(path.parts[0])
            if member.pax_headers or member.sparse is not None:
                raise BundleError(f"package contains PAX or sparse metadata: {member.name}")
            if member.uid != 0 or member.gid != 0 or member.uname != "" or member.gname != "":
                raise BundleError(f"package member ownership is not canonical: {member.name}")
            if member.type == tarfile.DIRTYPE:
                if member.mode != 0o755 or member.size != 0 or member.linkname:
                    raise BundleError(f"package directory metadata is not canonical: {member.name}")
                directory_members.add(member.name)
                continue
            if member.type != tarfile.REGTYPE:
                raise BundleError(f"package member type is not canonical: {member.name}")
            if member.mode != 0o644 or member.linkname:
                raise BundleError(f"package file metadata is not canonical: {member.name}")
            regular_members[member.name] = member
        if len(roots) != 1:
            raise BundleError("package must contain exactly one top-level directory")
        package_name = next(iter(roots))
        if IDENTIFIER_RE.fullmatch(package_name) is None:
            raise BundleError("package top-level directory is unsafe")
        expected_directories = {package_name}
        for name in regular_members:
            parent = PurePosixPath(name).parent
            while parent.as_posix() != ".":
                expected_directories.add(parent.as_posix())
                parent = parent.parent
        if directory_members != expected_directories:
            missing = sorted(expected_directories - directory_members)
            extra = sorted(directory_members - expected_directories)
            raise BundleError(
                f"package directory set is not canonical; missing={missing}, extra={extra}"
            )
        children: dict[str, list[str]] = {}
        for name in member_names - {package_name}:
            parent = PurePosixPath(name).parent.as_posix()
            children.setdefault(parent, []).append(name)
        expected_order = [package_name]
        pending_children = list(
            reversed(
                sorted(
                    children.get(package_name, []),
                    key=lambda item: PurePosixPath(item).name,
                )
            )
        )
        while pending_children:
            child = pending_children.pop()
            expected_order.append(child)
            if child in directory_members:
                nested = sorted(
                    children.get(child, []),
                    key=lambda item: PurePosixPath(item).name,
                )
                pending_children.extend(reversed(nested))
        if ordered_names != expected_order:
            raise BundleError("package members are not in canonical tree order")
        manifest_name = f"{package_name}/MANIFEST"
        sums_name = f"{package_name}/SHA256SUMS"
        if manifest_name not in regular_members or sums_name not in regular_members:
            raise BundleError("package lacks MANIFEST or SHA256SUMS")

        def member_bytes(name: str) -> bytes:
            member = regular_members.get(name)
            if member is None:
                raise BundleError(f"missing package member: {name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise BundleError(f"cannot read package member: {name}")
            try:
                with stream:
                    return stream.read()
            except (tarfile.TarError, OSError) as exc:
                raise BundleError(f"cannot read package member: {name}: {exc}") from exc

        manifest = parse_kv(member_bytes(manifest_name), "package MANIFEST")
        require_exact_keys(
            manifest,
            {
                "format_version",
                "target",
                "soc",
                "purpose",
                "build_id",
                "kernel_release",
                "kernel_baseline",
                "dtb_compatible",
                "root_spec",
                "console",
                "initramfs",
                "module_count",
                "module_tree_sha256",
                "source_git_commit",
                "source_snapshot_sha256",
                "created_utc",
                "image_file",
                "dtb_file",
                "boot_script",
                "modules_path",
            },
            "package MANIFEST",
        )
        if manifest.get("format_version") != "2" or manifest.get("target") != "r46h":
            raise BundleError("unsupported package manifest")
        if manifest.get("soc") != "rk3326" or manifest.get("kernel_baseline") != "6.12.99":
            raise BundleError("unsupported package SoC or kernel baseline")
        if manifest.get("purpose") != "mainline-bring-up-test-only":
            raise BundleError("unsupported package purpose")
        created_utc = manifest.get("created_utc", "")
        try:
            created_timestamp = int(
                dt.datetime.strptime(created_utc, "%Y-%m-%dT%H:%M:%SZ")
                .replace(tzinfo=dt.timezone.utc)
                .timestamp()
            )
        except (ValueError, OverflowError) as exc:
            raise BundleError("invalid package created_utc") from exc
        if created_timestamp != raw_tar["mtime"]:
            raise BundleError("package member mtime does not match MANIFEST created_utc")
        build_id = manifest.get("build_id", "")
        release = manifest.get("kernel_release", "")
        if IDENTIFIER_RE.fullmatch(build_id) is None or RELEASE_RE.fullmatch(release) is None:
            raise BundleError("unsafe package build ID or kernel release")
        if package_name != f"r46h-mainline-test-{build_id}":
            raise BundleError("package root does not match build ID")
        if release != f"6.12.99-r46h-mainline-{build_id}":
            raise BundleError("package kernel release does not match build ID")
        if manifest.get("initramfs") != "absent":
            raise BundleError("EASYROMS generator currently requires initramfs=absent")
        image_rel = safe_relative(manifest.get("image_file", ""), "image_file")
        dtb_rel = safe_relative(manifest.get("dtb_file", ""), "dtb_file")
        boot_script_rel = safe_relative(manifest.get("boot_script", ""), "boot_script")
        module_rel = safe_relative(manifest.get("modules_path", ""), "modules_path")
        if image_rel != "boot/Image.mainline-test" or dtb_rel != "boot/rk3326-r46h-mainline-test.dtb":
            raise BundleError("package boot artifact paths are unsupported")
        if boot_script_rel != "boot/boot.ini.test":
            raise BundleError("package boot script path is unsupported")
        expected_module_rel = f"rootfs/lib/modules/{release}"
        if module_rel != expected_module_rel:
            raise BundleError("package modules path does not match kernel release")

        try:
            sums_text = member_bytes(sums_name).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BundleError("package SHA256SUMS is not UTF-8") from exc
        expected_sums: dict[str, str] = {}
        for line_number, line in enumerate(sums_text.splitlines(), 1):
            match = re.fullmatch(r"([0-9a-f]{64})  ([A-Za-z0-9._+@/-]+)", line)
            if match is None:
                raise BundleError(f"SHA256SUMS:{line_number}: malformed line")
            digest, rel = match.groups()
            safe_relative(rel, "checksum path")
            if rel in expected_sums:
                raise BundleError(f"duplicate checksum path: {rel}")
            expected_sums[rel] = digest
        actual_rel = {
            name[len(package_name) + 1 :]
            for name in regular_members
            if name != sums_name
        }
        required_files = {"MANIFEST", image_rel, dtb_rel, boot_script_rel}
        missing_files = sorted(required_files - actual_rel)
        if missing_files:
            raise BundleError(f"package lacks required payload files: {missing_files}")
        if set(expected_sums) != actual_rel:
            raise BundleError("SHA256SUMS does not cover the exact package file set")
        for rel, expected in expected_sums.items():
            if sha_bytes(member_bytes(f"{package_name}/{rel}")) != expected:
                raise BundleError(f"package checksum mismatch: {rel}")

        allowed_fixed_files = {"MANIFEST", image_rel, dtb_rel, boot_script_rel}
        unexpected_files = sorted(
            rel
            for rel in actual_rel
            if rel not in allowed_fixed_files and not rel.startswith(f"{module_rel}/")
        )
        if unexpected_files:
            raise BundleError(f"package contains unsupported payload files: {unexpected_files}")
        allowed_fixed_dirs = {
            "",
            "boot",
            "rootfs",
            "rootfs/lib",
            "rootfs/lib/modules",
            module_rel,
        }
        for member in members:
            if not member.isdir():
                continue
            normalized = member.name.rstrip("/")
            relative = normalized[len(package_name) :].lstrip("/")
            if relative not in allowed_fixed_dirs and not relative.startswith(f"{module_rel}/"):
                raise BundleError(f"package contains unsupported directory: {relative}")

        image_data = member_bytes(f"{package_name}/{image_rel}")
        dtb_data = member_bytes(f"{package_name}/{dtb_rel}")
        module_rel_files = sorted(
            rel for rel in expected_sums if rel.startswith(f"{module_rel}/")
        )
        if not module_rel_files:
            raise BundleError("package module tree is empty")
        module_count = sum(rel.endswith(MODULE_SUFFIXES) for rel in module_rel_files)
        if str(module_count) != manifest.get("module_count"):
            raise BundleError("package module count mismatch")
        tree_sha = manifest.get("module_tree_sha256", "")
        if SHA_RE.fullmatch(tree_sha) is None:
            raise BundleError("invalid module tree hash")
        module_tree_manifest = "".join(
            f"{expected_sums[rel]}  {rel}\n" for rel in module_rel_files
        ).encode("utf-8")
        if sha_bytes(module_tree_manifest) != tree_sha:
            raise BundleError("package module tree hash mismatch")
        commit = manifest.get("source_git_commit", "")
        if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
            raise BundleError("invalid package source commit")
        source_snapshot = manifest.get("source_snapshot_sha256", "")
        if SHA_RE.fullmatch(source_snapshot) is None:
            raise BundleError("invalid package source snapshot hash")
        root_spec = manifest.get("root_spec", "")
        console = manifest.get("console", "")
        if re.fullmatch(r"[A-Za-z0-9_./:=+-]+", root_spec) is None:
            raise BundleError("unsafe package root_spec")
        if re.fullmatch(r"[A-Za-z0-9_,.-]+", console) is None:
            raise BundleError("unsafe package console")
        implied_paths: set[str] = {package_name}
        extraction_bytes = 0
        for member in members:
            normalized = member.name.rstrip("/")
            parts = PurePosixPath(normalized).parts
            for index in range(1, len(parts) + 1):
                implied_paths.add(PurePosixPath(*parts[:index]).as_posix())
            if member.isfile():
                extraction_bytes += member.size
        if len(implied_paths) > MAX_EXTRACTION_INODES:
            raise BundleError("canonical package exceeds extraction inode budget")
        result = {
            "tar_path": package_tar,
            "tar_size": raw_tar["compressed_size"],
            "tar_sha256": raw_tar["compressed_sha256"],
            "raw_tar_size": raw_tar["raw_size"],
            "package_name": package_name,
            "manifest": manifest,
            "build_id": build_id,
            "release": release,
            "image": image_data,
            "dtb": dtb_data,
            "module_count": module_count,
            "module_file_count": len(module_rel_files),
            "module_tree_sha256": tree_sha,
            "source_git_commit": commit,
            "source_snapshot_sha256": source_snapshot,
            "extraction_bytes": extraction_bytes,
            "extraction_inodes": len(implied_paths),
            "root_spec": root_spec,
            "console": console,
        }
        return result


def read_package(package_tar: Path) -> dict[str, Any]:
    package_tar, package_fd, source_state = open_package_source(package_tar)
    try:
        result = _read_package_from_open_source(
            package_tar, package_fd, source_state
        )
        verify_package_source(package_tar, package_fd, source_state)
        result["tar_source_state"] = source_state
        return result
    finally:
        os.close(package_fd)


def validate_profiles(card: dict[str, Any], baseline: dict[str, Any]) -> None:
    require_exact_keys(
        card,
        {"format_version", "profile_id", "target", "card", "uboot", "fallback"},
        "card profile",
    )
    require_exact_keys(
        baseline,
        {
            "format_version",
            "baseline_id",
            "release",
            "payload_name",
            "source_git_commit",
            "boot",
            "payload_anchors",
        },
        "current baseline",
    )
    if card.get("format_version") != 1 or baseline.get("format_version") != 1:
        raise BundleError("unsupported profile format")
    profile_id = require_string(card, "profile_id", IDENTIFIER_RE)
    if profile_id not in AUDITED_CARD_GEOMETRIES:
        raise BundleError("unsupported card profile ID")
    if require_string(card, "target") != "HL-R46H-V22":
        raise BundleError("unsupported target")
    baseline_id = require_string(baseline, "baseline_id", IDENTIFIER_RE)
    baseline_release = require_string(baseline, "release", RELEASE_RE)
    if baseline_release != f"6.12.99-r46h-mainline-{baseline_id}":
        raise BundleError("baseline release does not match baseline ID")
    if re.fullmatch(r"[0-9a-f]{40}", require_string(baseline, "source_git_commit")) is None:
        raise BundleError("invalid baseline source commit")
    payload = require_string(baseline, "payload_name")
    if payload != f"r46h-{baseline_id}":
        raise BundleError("unsafe current payload name")
    boot = require_map(baseline, "boot")
    require_exact_keys(
        boot,
        {
            "active_path",
            "candidate_path",
            "candidate_size",
            "candidate_sha256",
            "image_path",
            "image_size",
            "image_sha256",
            "dtb_path",
            "dtb_size",
            "dtb_sha256",
        },
        "baseline boot",
    )
    for key in ("active_path", "candidate_path", "image_path", "dtb_path"):
        safe_relative(require_string(boot, key), f"baseline {key}", basename_only=True)
    for key in ("candidate_size", "image_size", "dtb_size"):
        require_int(boot, key)
    for key in ("candidate_sha256", "image_sha256", "dtb_sha256"):
        require_sha(boot, key)
    anchors = require_list(baseline, "payload_anchors")
    if not anchors:
        raise BundleError("baseline must contain at least one payload anchor")
    if len(anchors) > MAX_PROFILE_ANCHORS:
        raise BundleError("baseline payload anchor count exceeds safe limit")
    seen: set[str] = set()
    for anchor in anchors:
        if not isinstance(anchor, dict):
            raise BundleError("payload anchor must be an object")
        require_exact_keys(anchor, {"path", "size", "sha256"}, "payload anchor")
        path = safe_relative(require_string(anchor, "path"), "payload anchor", basename_only=True)
        if path in seen:
            raise BundleError(f"duplicate payload anchor: {path}")
        seen.add(path)
        require_int(anchor, "size")
        require_sha(anchor, "sha256")

    card_map = require_map(card, "card")
    require_exact_keys(
        card_map,
        {
            "whole_size",
            "sector_size",
            "partition_scheme",
            "boot",
            "root",
            "easyroms",
            "g92_prefix_size",
            "g92_prefix_sha256",
        },
        "card geometry",
    )
    if require_string(card_map, "partition_scheme") != "FDisk_partition_scheme":
        raise BundleError("unsupported partition scheme")
    for key in ("whole_size", "sector_size", "g92_prefix_size"):
        require_int(card_map, key)
    require_sha(card_map, "g92_prefix_sha256")
    partition_maps: dict[str, dict[str, Any]] = {}
    for part in ("boot", "root", "easyroms"):
        part_map = require_map(card_map, part)
        partition_maps[part] = part_map
        expected_fields = {"number", "offset", "size"}
        expected_fields.add("partuuid" if part == "root" else "volume_uuid")
        require_exact_keys(part_map, expected_fields, f"{part} partition")
        for key in ("number", "offset", "size"):
            require_int(part_map, key)
    if [partition_maps[name]["number"] for name in ("boot", "root", "easyroms")] != [1, 2, 3]:
        raise BundleError("partition numbers must be exactly 1, 2, 3")
    sector_size = require_int(card_map, "sector_size")
    if sector_size not in {512, 4096}:
        raise BundleError("unsupported logical sector size")
    boot_part = partition_maps["boot"]
    root_part = partition_maps["root"]
    roms_part = partition_maps["easyroms"]
    geometry_values = [
        require_int(card_map, "whole_size"),
        require_int(card_map, "g92_prefix_size"),
        *(require_int(partition_maps[name], key) for name in ("boot", "root", "easyroms") for key in ("offset", "size")),
    ]
    if any(value % sector_size for value in geometry_values):
        raise BundleError("card geometry is not sector-aligned")
    if require_int(card_map, "g92_prefix_size") != require_int(boot_part, "offset"):
        raise BundleError("g92 prefix size must equal BOOT offset")
    if require_int(root_part, "offset") != require_int(boot_part, "offset") + require_int(boot_part, "size"):
        raise BundleError("BOOT and root partitions are not contiguous")
    if require_int(roms_part, "offset") != require_int(root_part, "offset") + require_int(root_part, "size"):
        raise BundleError("root and EASYROMS partitions are not contiguous")
    if require_int(card_map, "whole_size") != require_int(roms_part, "offset") + require_int(roms_part, "size"):
        raise BundleError("EASYROMS does not end at the audited card size")
    uuid_re = re.compile(r"^[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}$")
    for name in ("boot", "easyroms"):
        require_string(partition_maps[name], "volume_uuid", uuid_re)
    partuuid = require_string(root_part, "partuuid")
    if re.fullmatch(r"[0-9a-f]{8}-02", partuuid) is None:
        raise BundleError("invalid root PARTUUID")
    if card_map != AUDITED_CARD_GEOMETRIES[profile_id]:
        raise BundleError("card geometry does not exactly match the audited R46H card")

    uboot = require_map(card, "uboot")
    require_exact_keys(
        uboot,
        {"root_dtb_path", "console_dtb_path", "dtb_size", "dtb_sha256"},
        "U-Boot identity",
    )
    safe_relative(require_string(uboot, "root_dtb_path"), "U-Boot root DTB")
    safe_relative(require_string(uboot, "console_dtb_path"), "U-Boot console DTB")
    require_int(uboot, "dtb_size")
    require_sha(uboot, "dtb_sha256")
    if uboot != AUDITED_UBOOT_IDENTITY:
        raise BundleError("U-Boot identity does not exactly match the audited R46H profile")
    fallback = require_map(card, "fallback")
    require_exact_keys(
        fallback,
        {
            "release",
            "boot_path",
            "boot_test_path",
            "boot_size",
            "boot_sha256",
            "image_path",
            "image_size",
            "image_sha256",
            "dtb_path",
            "dtb_size",
            "dtb_sha256",
            "module_count",
            "module_file_count",
            "module_tree_sha256_allowed",
        },
        "fallback identity",
    )
    require_string(fallback, "release", RELEASE_RE)
    for key in ("boot_path", "boot_test_path", "image_path", "dtb_path"):
        safe_relative(require_string(fallback, key), f"fallback {key}", basename_only=True)
    for key in ("boot_size", "image_size", "dtb_size", "module_count", "module_file_count"):
        require_int(fallback, key)
    for key in ("boot_sha256", "image_sha256", "dtb_sha256"):
        require_sha(fallback, key)
    hashes = require_list(fallback, "module_tree_sha256_allowed")
    if not hashes or any(not isinstance(value, str) or SHA_RE.fullmatch(value) is None for value in hashes):
        raise BundleError("fallback module tree allowlist is invalid")
    if fallback != AUDITED_FALLBACK_IDENTITY:
        raise BundleError("fallback identity does not exactly match the audited v0.2 state")


def render_template_bytes(data: bytes, label: str, values: dict[str, str]) -> bytes:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BundleError(f"template is not UTF-8: {label}") from exc
    required = set(TOKEN_RE.findall(text))
    expected = {f"@{key}@" for key in values}
    unknown_values = expected - required
    if unknown_values:
        raise BundleError(f"unused template values for {label}: {sorted(unknown_values)}")
    for token in required:
        key = token[1:-1]
        if key not in values:
            raise BundleError(f"missing template value {token} for {label}")
        text = text.replace(token, values[key])
    if TOKEN_RE.search(text):
        raise BundleError(f"unresolved template token in {label}")
    return text.encode("utf-8")


def validate_deployment_relationships(
    package: dict[str, Any],
    card: dict[str, Any],
    baseline: dict[str, Any],
    *,
    image_name: str,
    dtb_name: str,
    boot_name: str,
    boot_data: bytes,
) -> None:
    fallback = require_map(card, "fallback")
    uboot = require_map(card, "uboot")
    current_boot = require_map(baseline, "boot")
    root_profile = require_map(require_map(card, "card"), "root")
    expected_root_spec = f"PARTUUID={require_string(root_profile, 'partuuid')}"
    if expected_root_spec != EXPECTED_ROOT_SPEC:
        raise BundleError("card profile root PARTUUID is not the audited R46H value")
    if package["root_spec"] != expected_root_spec:
        raise BundleError("package root_spec does not match the audited root PARTUUID")
    if package["console"] != EXPECTED_CONSOLE:
        raise BundleError("package console must be exactly ttyS2,115200n8")
    if package["manifest"].get("dtb_compatible") != EXPECTED_DTB_COMPATIBLE:
        raise BundleError("package DTB compatible is not the audited R46H compatible")
    if package["source_git_commit"] == require_string(baseline, "source_git_commit"):
        raise BundleError("new package source commit must differ from the current baseline commit")
    releases = {
        package["release"],
        require_string(baseline, "release", RELEASE_RE),
        require_string(fallback, "release", RELEASE_RE),
    }
    if len(releases) != 3:
        raise BundleError("new, current, and fallback releases must be distinct")
    if f"r46h-{package['build_id']}" == require_string(baseline, "payload_name"):
        raise BundleError("new and current payload names must be distinct")

    managed_paths = [
        require_string(current_boot, "active_path"),
        require_string(current_boot, "candidate_path"),
        require_string(current_boot, "image_path"),
        require_string(current_boot, "dtb_path"),
        require_string(fallback, "boot_path"),
        require_string(fallback, "boot_test_path"),
        require_string(fallback, "image_path"),
        require_string(fallback, "dtb_path"),
        require_string(uboot, "root_dtb_path"),
        require_string(uboot, "console_dtb_path"),
        image_name,
        dtb_name,
        boot_name,
    ]
    if len(set(managed_paths)) != len(managed_paths):
        raise BundleError("managed BOOT paths collide")

    boot_states = {
        (require_int(current_boot, "candidate_size"), require_sha(current_boot, "candidate_sha256")),
        (require_int(fallback, "boot_size"), require_sha(fallback, "boot_sha256")),
        (len(boot_data), sha_bytes(boot_data)),
    }
    if len(boot_states) != 3:
        raise BundleError("current, fallback, and new boot states must be distinct")


def open_directory_at(parent_fd: int, name: str, label: str) -> int:
    require_plain_basename(name, label)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(name, flags, dir_fd=parent_fd)
    try:
        opened = os.fstat(descriptor)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(named.st_mode)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise BundleError(f"{label} identity changed while opening")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def create_private_directory_at(parent_fd: int) -> tuple[str, int, tuple[int, int]]:
    # The random 192-bit name, 0700 mode, descriptor binding, and empty check
    # reject accidental or ordinary replacement. A malicious process already
    # running as the same UID can still race the mkdir-to-open namespace window;
    # such a process is outside this generator's trust boundary.
    for _attempt in range(128):
        name = f".easyroms-bundle.{secrets.token_hex(24)}"
        try:
            os.mkdir(name, 0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        try:
            created = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except Exception as exc:
            raise BundleError(
                f"cannot bind new private publication directory; retained path: {name}: {exc}"
            ) from exc
        if not stat.S_ISDIR(created.st_mode):
            raise BundleError(
                f"new private publication path is not a directory; retained path: {name}"
            )
        created_identity = stat_identity(created)
        try:
            descriptor = open_directory_at(
                parent_fd, name, "private publication directory"
            )
        except Exception as exc:
            raise BundleError(
                f"cannot open new private publication directory; retained path: {name}: {exc}"
            ) from exc
        try:
            opened_identity = fd_identity(descriptor, "directory")
            opened = os.fstat(descriptor)
            if (
                opened_identity != created_identity
                or stat.S_IMODE(opened.st_mode) != 0o700
                or opened.st_uid != os.geteuid()
                or os.listdir(descriptor)
            ):
                raise BundleError(
                    "private publication directory changed or was not empty after creation; "
                    "path was preserved"
                )
        except Exception as exc:
            os.close(descriptor)
            raise BundleError(
                f"cannot prove new private publication directory; retained path: {name}: {exc}"
            ) from exc
        return name, descriptor, opened_identity
    raise BundleError("cannot allocate a unique private publication directory")


def create_directory_at(
    parent_fd: int, name: str, label: str, mode: int = 0o755
) -> tuple[int, tuple[int, int]]:
    require_plain_basename(name, label)
    os.mkdir(name, mode, dir_fd=parent_fd)
    descriptor = open_directory_at(parent_fd, name, label)
    try:
        os.fchmod(descriptor, mode)
        return descriptor, fd_identity(descriptor, "directory")
    except Exception:
        os.close(descriptor)
        raise


def create_file_at(parent_fd: int, name: str, mode: int) -> int:
    require_plain_basename(name, "generated file name")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(name, flags, mode, dir_fd=parent_fd)
    try:
        os.fchmod(descriptor, mode)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise BundleError(f"generated output is not a regular file: {name}")
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def write_bytes_at(parent_fd: int, name: str, data: bytes, mode: int = 0o644) -> None:
    descriptor = create_file_at(parent_fd, name, mode)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def copy_verified_file_at(
    source_path: Path,
    parent_fd: int,
    name: str,
    expected_size: int,
    expected_sha256: str,
    expected_source_state: tuple[int, ...],
) -> None:
    try:
        candidate = os.stat(source_path, follow_symlinks=False)
    except OSError as exc:
        raise BundleError(
            f"canonical package source identity changed before copying: {exc}"
        ) from exc
    if (
        not stat.S_ISREG(candidate.st_mode)
        or stable_file_state(candidate) != expected_source_state
    ):
        raise BundleError("canonical package source identity changed before copying")
    try:
        source_fd = os.open(
            source_path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
        )
    except OSError as exc:
        raise BundleError(f"cannot safely reopen canonical package source: {exc}") from exc
    destination_fd: int | None = None
    try:
        try:
            verify_package_source(source_path, source_fd, expected_source_state)
        except BundleError as exc:
            raise BundleError(
                "canonical package source identity changed before copying"
            ) from exc
        os.lseek(source_fd, 0, os.SEEK_SET)
        destination_fd = create_file_at(parent_fd, name, 0o644)
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(source_fd, "rb", closefd=False) as source, os.fdopen(
            destination_fd, "wb", closefd=False
        ) as destination:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                size += len(block)
                if size > MAX_COMPRESSED_PACKAGE_BYTES:
                    raise BundleError("canonical package exceeds compressed byte budget while copying")
                digest.update(block)
                destination.write(block)
        if size != expected_size or digest.hexdigest() != expected_sha256:
            raise BundleError("canonical package changed while being copied")
        try:
            verify_package_source(source_path, source_fd, expected_source_state)
        except BundleError as exc:
            raise BundleError(
                "canonical package source identity changed while being copied"
            ) from exc
    finally:
        os.close(source_fd)
        if destination_fd is not None:
            os.close(destination_fd)


def sha_file_at(parent_fd: int, name: str) -> str:
    require_plain_basename(name, "generated digest source")
    descriptor = os.open(
        name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=parent_fd
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise BundleError(f"generated digest source is not regular: {name}")
        digest = hashlib.sha256()
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def manifest_bytes(fields: list[tuple[str, Any]]) -> bytes:
    seen: set[str] = set()
    lines: list[str] = []
    for key, raw in fields:
        if key in seen or re.fullmatch(r"[a-z][a-z0-9_]*", key) is None:
            raise BundleError(f"invalid or duplicate generated manifest key: {key}")
        seen.add(key)
        value = str(raw)
        if not value or "\n" in value or "\r" in value:
            raise BundleError(f"unsafe generated manifest value for {key}")
        lines.append(f"{key}={value}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def deterministic_archive_at(
    source_fd: int,
    source_name: str,
    archive_parent_fd: int,
    archive_name: str,
    epoch: int,
) -> tuple[int, tuple[int, int]]:
    require_plain_basename(source_name, "archive source name")
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as archive:
        root_info = tarfile.TarInfo(source_name)
        root_info.uid = root_info.gid = 0
        root_info.uname = root_info.gname = ""
        root_info.mtime = epoch
        root_info.type = tarfile.DIRTYPE
        root_info.mode = 0o755
        root_info.size = 0
        archive.addfile(root_info)

        def append_directory(directory_fd: int, relative: PurePosixPath) -> None:
            for name in sorted(os.listdir(directory_fd)):
                require_plain_basename(name, "generated archive entry")
                entry_relative = relative / name
                archive_path = f"{source_name}/{entry_relative.as_posix()}"
                named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                if stat.S_ISDIR(named.st_mode):
                    child_fd = open_directory_at(
                        directory_fd, name, "generated archive directory"
                    )
                    try:
                        info = tarfile.TarInfo(archive_path)
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        info.mtime = epoch
                        info.type = tarfile.DIRTYPE
                        info.mode = 0o755
                        info.size = 0
                        archive.addfile(info)
                        append_directory(child_fd, entry_relative)
                    finally:
                        os.close(child_fd)
                    continue
                if not stat.S_ISREG(named.st_mode):
                    raise BundleError(f"unsafe generated bundle entry: {archive_path}")
                file_fd = os.open(
                    name,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_fd,
                )
                try:
                    opened = os.fstat(file_fd)
                    if (
                        not stat.S_ISREG(opened.st_mode)
                        or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
                    ):
                        raise BundleError(
                            f"generated archive file identity changed: {archive_path}"
                        )
                    mode = stat.S_IMODE(opened.st_mode)
                    if mode not in {0o644, 0o755}:
                        raise BundleError(
                            f"generated archive file mode is unsafe: {archive_path}"
                        )
                    info = tarfile.TarInfo(archive_path)
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = epoch
                    info.type = tarfile.REGTYPE
                    info.mode = mode
                    info.size = opened.st_size
                    with os.fdopen(file_fd, "rb", closefd=False) as handle:
                        archive.addfile(info, handle)
                    after = os.fstat(file_fd)
                    if (
                        after.st_size != opened.st_size
                        or after.st_mtime_ns != opened.st_mtime_ns
                        or after.st_ctime_ns != opened.st_ctime_ns
                    ):
                        raise BundleError(
                            f"generated archive file changed while being read: {archive_path}"
                        )
                finally:
                    os.close(file_fd)

        append_directory(source_fd, PurePosixPath())

    archive_fd = create_file_at(archive_parent_fd, archive_name, 0o644)
    try:
        with os.fdopen(archive_fd, "wb", closefd=False) as output:
            with gzip.GzipFile(
                filename="", mode="wb", compresslevel=9, fileobj=output, mtime=0
            ) as compressed:
                compressed.write(raw.getvalue())
        return archive_fd, fd_identity(archive_fd, "file")
    except Exception:
        os.close(archive_fd)
        raise


def require_plain_basename(name: str, label: str) -> bytes:
    if not name or name in {".", ".."} or "/" in name or "\0" in name:
        raise BundleError(f"unsafe {label}: {name}")
    return os.fsencode(name)


def rename_noreplace_at(
    source_dir_fd: int,
    source_name: str,
    destination_dir_fd: int,
    destination_name: str,
) -> None:
    source = require_plain_basename(source_name, "publication source name")
    destination = require_plain_basename(destination_name, "publication destination name")
    libc = ctypes.CDLL(None, use_errno=True)
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
        result = rename_call(
            source_dir_fd,
            source,
            destination_dir_fd,
            destination,
            0x00000004,  # RENAME_EXCL
        )
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
        result = rename_call(
            source_dir_fd,
            source,
            destination_dir_fd,
            destination,
            0x00000001,  # RENAME_NOREPLACE
        )
    else:
        raise BundleError("platform lacks atomic no-replace rename support")
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(
            error_number,
            "publication destination already exists",
            destination_name,
        )
    raise OSError(error_number, os.strerror(error_number), destination_name)


def open_verified_directory(path: Path, label: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        opened = os.fstat(fd)
        named = path.stat(follow_symlinks=False)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(named.st_mode)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
        ):
            raise BundleError(f"{label} identity changed while opening")
        return fd
    except Exception:
        os.close(fd)
        raise


def fd_identity(fd: int, expected_kind: str) -> tuple[int, int]:
    current = os.fstat(fd)
    if expected_kind == "directory":
        valid = stat.S_ISDIR(current.st_mode)
    elif expected_kind == "file":
        valid = stat.S_ISREG(current.st_mode)
    else:
        raise BundleError("invalid internal publication kind")
    if not valid:
        raise BundleError(f"publication source is not a {expected_kind}")
    return current.st_dev, current.st_ino


def verify_published_identity(
    parent_fd: int,
    name: str,
    expected_identity: tuple[int, int],
    expected_kind: str,
) -> None:
    current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if expected_kind == "directory":
        valid = stat.S_ISDIR(current.st_mode)
    else:
        valid = stat.S_ISREG(current.st_mode)
    if not valid or (current.st_dev, current.st_ino) != expected_identity:
        raise BundleError(
            f"published {expected_kind} identity changed; refusing path-based cleanup"
        )


def verify_private_source_identity(
    parent_fd: int,
    name: str,
    expected_identity: tuple[int, int],
    expected_kind: str,
) -> None:
    current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if expected_kind == "directory":
        valid = stat.S_ISDIR(current.st_mode)
    elif expected_kind == "file":
        valid = stat.S_ISREG(current.st_mode)
    else:
        raise BundleError("invalid private publication source kind")
    if not valid or (current.st_dev, current.st_ino) != expected_identity:
        raise BundleError(f"private {expected_kind} source identity changed before publication")


def verify_directory_path_identity(
    path: Path, expected_identity: tuple[int, int], label: str
) -> None:
    current = path.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != expected_identity
    ):
        raise BundleError(f"{label} path identity changed")


def build_bundle(args: argparse.Namespace) -> tuple[Path, Path]:
    package = read_package(Path(args.package_tar))
    binding = establish_repository_binding(
        package, Path(args.card_profile), Path(args.current_baseline)
    )
    blobs = binding["blobs"]
    card, card_sha = load_json_bytes(blobs[binding["card_relative"]], "card profile")
    baseline, baseline_sha = load_json_bytes(
        blobs[binding["baseline_relative"]], "current baseline"
    )
    validate_profiles(card, baseline)
    purpose = args.purpose
    if PURPOSE_RE.fullmatch(purpose) is None:
        raise BundleError(f"unsafe purpose: {purpose}")
    if package["release"] == baseline["release"]:
        raise BundleError("new and current kernel releases must differ")
    # Direct library callers used by the race fixtures predate the CLI option;
    # preserving their historical default keeps the API fail-closed and stable.
    action_policy = getattr(args, "action_policy", "full")
    if action_policy == "full":
        allowed_actions = "install-modules,switch-boot"
        boot_switch_name = "switch-boot.sh"
    elif action_policy == "install-modules-only":
        allowed_actions = "install-modules"
        boot_switch_name = "disabled"
    else:
        raise BundleError("unsupported target action policy")
    card_root_profile = require_map(require_map(card, "card"), "root")
    if package["extraction_bytes"] + 64 * 1024 * 1024 >= require_int(card_root_profile, "size"):
        raise BundleError("package extraction projection cannot fit the audited root partition")
    epoch = args.source_date_epoch
    if epoch < 0 or epoch > MAX_SOURCE_DATE_EPOCH:
        raise BundleError(
            f"SOURCE_DATE_EPOCH must be in [0, {MAX_SOURCE_DATE_EPOCH}]"
        )
    created = dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    output_parent = Path(args.output_dir)
    if str(output_parent).strip() in {"", "/"}:
        raise BundleError("unsafe output directory")
    output_parent.mkdir(parents=True, exist_ok=True)
    output_parent = output_parent.resolve(strict=True)
    if output_parent == Path(output_parent.anchor):
        raise BundleError("unsafe resolved output directory")
    build_id = package["build_id"]
    bundle_name = f"r46h-easyroms-{build_id}"
    final_archive_name = f"{bundle_name}.tar.gz"
    final_dir = output_parent / bundle_name
    final_tar = output_parent / final_archive_name
    if final_dir.exists() or final_dir.is_symlink() or final_tar.exists() or final_tar.is_symlink():
        raise BundleError("bundle output already exists")

    output_parent_fd = open_verified_directory(output_parent, "bundle output directory")
    output_parent_identity = fd_identity(output_parent_fd, "directory")
    stage_name: str | None = None
    stage_fd: int | None = None
    stage_identity: tuple[int, int] | None = None
    payload_fd: int | None = None
    archive_temp_name: str | None = None
    archive_fd: int | None = None
    published_dir = False
    published_tar = False
    try:
        template_data = {
            PurePosixPath(relative).name: blobs[relative]
            for relative in TEMPLATE_RELPATHS
        }
        stage_name, stage_fd, stage_identity = create_private_directory_at(
            output_parent_fd
        )
        payload_fd, _payload_identity = create_directory_at(
            stage_fd, "payload", "private bundle payload"
        )

        image_name = f"Image.mainline-{build_id}.gz"
        dtb_name = f"rk3326-r46h-mainline-{build_id}.dtb"
        boot_name = f"boot.ini.{build_id}"
        tar_name = f"{package['package_name']}.tar.gz"
        with io.BytesIO() as buffer:
            with gzip.GzipFile(filename="", mode="wb", compresslevel=9, fileobj=buffer, mtime=0) as compressed:
                compressed.write(package["image"])
            compressed_image = buffer.getvalue()
        write_bytes_at(payload_fd, image_name, compressed_image)
        write_bytes_at(payload_fd, dtb_name, package["dtb"])
        copy_verified_file_at(
            package["tar_path"],
            payload_fd,
            tar_name,
            package["tar_size"],
            package["tar_sha256"],
            package["tar_source_state"],
        )

        card_map = require_map(card, "card")
        card_boot = require_map(card_map, "boot")
        card_root = require_map(card_map, "root")
        card_roms = require_map(card_map, "easyroms")
        uboot = require_map(card, "uboot")
        fallback = require_map(card, "fallback")
        current_boot = require_map(baseline, "boot")
        anchors = require_list(baseline, "payload_anchors")

        boot_data = render_template_bytes(
            template_data["boot.ini.in"],
            "boot.ini.in",
            {
                "BUILD_ID": build_id,
                "FALLBACK_BOOT_PATH": require_string(fallback, "boot_path"),
                "ROOT_SPEC": package["root_spec"],
                "CONSOLE": package["console"],
                "IMAGE_NAME": image_name,
                "IMAGE_COMPRESSED_SIZE_HEX": hex(len(compressed_image)),
                "IMAGE_UNCOMPRESSED_SIZE_HEX": hex(len(package["image"])),
                "DTB_NAME": dtb_name,
                "DTB_SIZE_HEX": hex(len(package["dtb"])),
            },
        )
        write_bytes_at(payload_fd, boot_name, boot_data)
        validate_deployment_relationships(
            package,
            card,
            baseline,
            image_name=image_name,
            dtb_name=dtb_name,
            boot_name=boot_name,
            boot_data=boot_data,
        )

        common_data = template_data["target-common.sh.in"]
        write_bytes_at(payload_fd, "target-common.sh", common_data, 0o755)
        bootstrap_data = render_template_bytes(
            template_data["bootstrap-target.sh.in"], "bootstrap-target.sh.in", {}
        )
        write_bytes_at(payload_fd, "bootstrap-target.sh", bootstrap_data, 0o755)
        owner = manifest_bytes(
            [
                ("format_version", 1),
                ("status", "owned"),
                ("purpose", f"r46h-{build_id}-exclusive-card-stage"),
                ("target", require_string(card, "target")),
                ("source_git_commit", package["source_git_commit"]),
                ("source_snapshot_sha256", package["source_snapshot_sha256"]),
                ("kernel_release", package["release"]),
                ("payload", f"r46h-{build_id}"),
                ("package_sha256", package["tar_sha256"]),
            ]
        )
        complete = manifest_bytes(
            [
                ("format_version", 1),
                ("status", "complete"),
                ("purpose", f"r46h-{build_id}-macos-stage"),
                ("target", require_string(card, "target")),
                ("source_git_commit", package["source_git_commit"]),
                ("source_snapshot_sha256", package["source_snapshot_sha256"]),
                ("kernel_release", package["release"]),
                ("payload", f"r46h-{build_id}"),
                ("active_boot_ini", f"unchanged-{require_string(baseline, 'baseline_id', IDENTIFIER_RE)}"),
                ("bootloader_prefix", "unchanged-g92"),
                ("boot_partition", "unchanged-raw-sha256"),
                ("root_partition", "not-mounted"),
                ("package_sha256", package["tar_sha256"]),
            ]
        )
        write_bytes_at(payload_fd, ".r46h-stage-owner", owner)
        write_bytes_at(payload_fd, "STAGE-COMPLETE", complete)

        fields: list[tuple[str, Any]] = [
            ("format_version", 3),
            ("target", require_string(card, "target")),
            ("purpose", purpose),
            ("created_utc", created),
            ("source_git_commit", package["source_git_commit"]),
            ("source_snapshot_sha256", package["source_snapshot_sha256"]),
            ("build_id", build_id),
            ("kernel_release", package["release"]),
            ("action_policy", action_policy),
            ("allowed_actions", allowed_actions),
            ("package_name", package["package_name"]),
            ("payload_name", f"r46h-{build_id}"),
            ("canonical_tar", tar_name),
            ("canonical_tar_size", package["tar_size"]),
            ("canonical_tar_sha256", package["tar_sha256"]),
            ("extraction_bytes", package["extraction_bytes"]),
            ("extraction_inodes", package["extraction_inodes"]),
            ("image_uncompressed_size", len(package["image"])),
            ("image_uncompressed_sha256", sha_bytes(package["image"])),
            ("boot_image", image_name),
            ("boot_image_size", len(compressed_image)),
            ("boot_image_sha256", sha_bytes(compressed_image)),
            ("boot_dtb", dtb_name),
            ("boot_dtb_size", len(package["dtb"])),
            ("boot_dtb_sha256", sha_bytes(package["dtb"])),
            ("boot_candidate", boot_name),
            ("boot_candidate_size", len(boot_data)),
            ("boot_candidate_sha256", sha_bytes(boot_data)),
            ("module_tree_sha256", package["module_tree_sha256"]),
            ("module_count", package["module_count"]),
            ("module_tree_file_count", package["module_file_count"]),
            ("stage_owner_size", len(owner)),
            ("stage_owner_sha256", sha_bytes(owner)),
            ("stage_complete_size", len(complete)),
            ("stage_complete_sha256", sha_bytes(complete)),
            ("target_common", "target-common.sh"),
            ("target_common_size", len(common_data)),
            ("target_common_sha256", sha_bytes(common_data)),
            ("target_bootstrap", "bootstrap-target.sh"),
            ("target_bootstrap_size", len(bootstrap_data)),
            ("target_bootstrap_sha256", sha_bytes(bootstrap_data)),
            ("target_module_installer", "install-modules.sh"),
            ("target_boot_switch", boot_switch_name),
            ("card_profile_id", require_string(card, "profile_id", IDENTIFIER_RE)),
            ("card_profile_sha256", card_sha),
            ("current_baseline_id", require_string(baseline, "baseline_id", IDENTIFIER_RE)),
            ("current_baseline_sha256", baseline_sha),
            ("current_release", require_string(baseline, "release", RELEASE_RE)),
            ("current_payload_name", require_string(baseline, "payload_name")),
            ("current_active_path", require_string(current_boot, "active_path")),
            ("current_candidate_path", require_string(current_boot, "candidate_path")),
            ("current_candidate_size", require_int(current_boot, "candidate_size")),
            ("current_candidate_sha256", require_sha(current_boot, "candidate_sha256")),
            ("current_image_path", require_string(current_boot, "image_path")),
            ("current_image_size", require_int(current_boot, "image_size")),
            ("current_image_sha256", require_sha(current_boot, "image_sha256")),
            ("current_dtb_path", require_string(current_boot, "dtb_path")),
            ("current_dtb_size", require_int(current_boot, "dtb_size")),
            ("current_dtb_sha256", require_sha(current_boot, "dtb_sha256")),
            ("current_anchor_count", len(anchors)),
        ]
        for index, anchor in enumerate(anchors, 1):
            assert isinstance(anchor, dict)
            fields.extend(
                [
                    (f"current_anchor_{index}_path", require_string(anchor, "path")),
                    (f"current_anchor_{index}_size", require_int(anchor, "size")),
                    (f"current_anchor_{index}_sha256", require_sha(anchor, "sha256")),
                ]
            )
        fields.extend(
            [
                ("fallback_release", require_string(fallback, "release", RELEASE_RE)),
                ("fallback_boot_path", require_string(fallback, "boot_path")),
                ("fallback_boot_test_path", require_string(fallback, "boot_test_path")),
                ("fallback_boot_size", require_int(fallback, "boot_size")),
                ("fallback_boot_sha256", require_sha(fallback, "boot_sha256")),
                ("fallback_image_path", require_string(fallback, "image_path")),
                ("fallback_image_size", require_int(fallback, "image_size")),
                ("fallback_image_sha256", require_sha(fallback, "image_sha256")),
                ("fallback_dtb_path", require_string(fallback, "dtb_path")),
                ("fallback_dtb_size", require_int(fallback, "dtb_size")),
                ("fallback_dtb_sha256", require_sha(fallback, "dtb_sha256")),
                ("fallback_module_count", require_int(fallback, "module_count")),
                ("fallback_module_file_count", require_int(fallback, "module_file_count")),
                ("fallback_module_tree_sha256_allowed", ",".join(require_list(fallback, "module_tree_sha256_allowed"))),
                ("uboot_root_dtb_path", require_string(uboot, "root_dtb_path")),
                ("uboot_console_dtb_path", require_string(uboot, "console_dtb_path")),
                ("uboot_dtb_size", require_int(uboot, "dtb_size")),
                ("uboot_dtb_sha256", require_sha(uboot, "dtb_sha256")),
                ("card_whole_size", require_int(card_map, "whole_size")),
                ("card_sector_size", require_int(card_map, "sector_size")),
                ("card_boot_number", require_int(card_boot, "number")),
                ("card_boot_offset", require_int(card_boot, "offset")),
                ("card_boot_size", require_int(card_boot, "size")),
                ("card_boot_uuid", require_string(card_boot, "volume_uuid")),
                ("card_root_number", require_int(card_root, "number")),
                ("card_root_offset", require_int(card_root, "offset")),
                ("card_root_size", require_int(card_root, "size")),
                ("card_root_partuuid", require_string(card_root, "partuuid")),
                ("card_easyroms_number", require_int(card_roms, "number")),
                ("card_easyroms_offset", require_int(card_roms, "offset")),
                ("card_easyroms_size", require_int(card_roms, "size")),
                ("card_easyroms_uuid", require_string(card_roms, "volume_uuid")),
                ("card_g92_prefix_size", require_int(card_map, "g92_prefix_size")),
                ("card_g92_prefix_sha256", require_sha(card_map, "g92_prefix_sha256")),
            ]
        )
        deploy_manifest = manifest_bytes(fields)
        write_bytes_at(payload_fd, "DEPLOY-MANIFEST", deploy_manifest)
        manifest_sha = sha_bytes(deploy_manifest)
        rendered_targets = [("install-modules.sh.in", "install-modules.sh")]
        if action_policy == "full":
            rendered_targets.append(("switch-boot.sh.in", "switch-boot.sh"))
        for template_name, output_name in rendered_targets:
            rendered = render_template_bytes(
                template_data[template_name],
                template_name,
                {"DEPLOY_MANIFEST_SHA256": manifest_sha},
            )
            write_bytes_at(payload_fd, output_name, rendered, 0o755)

        payload_files = sorted(os.listdir(payload_fd))
        for name in payload_files:
            current = os.stat(name, dir_fd=payload_fd, follow_symlinks=False)
            if not stat.S_ISREG(current.st_mode):
                raise BundleError(f"generated payload entry is not regular: {name}")
        source_lines = [
            f"{sha_file_at(payload_fd, name)}  payload/{name}\n"
            for name in payload_files
        ]
        source_list = "".join(source_lines).encode("utf-8")
        write_bytes_at(stage_fd, "STAGE-SOURCES.sha256", source_list)
        stage_script = render_template_bytes(
            template_data["stage-easyroms-macos.sh.in"],
            "stage-easyroms-macos.sh.in",
            {"STAGE_SOURCES_SHA256": sha_bytes(source_list)},
        )
        write_bytes_at(stage_fd, "stage-on-macos.sh", stage_script, 0o755)

        archive_temp_name = f".easyroms-archive.{secrets.token_hex(24)}.tar.gz"
        archive_fd, archive_identity = deterministic_archive_at(
            stage_fd,
            bundle_name,
            output_parent_fd,
            archive_temp_name,
            epoch,
        )
        verify_private_source_identity(
            output_parent_fd, stage_name, stage_identity, "directory"
        )
        verify_private_source_identity(
            output_parent_fd, archive_temp_name, archive_identity, "file"
        )
        recheck_repository_binding(binding)
        verify_directory_path_identity(
            output_parent, output_parent_identity, "bundle output directory"
        )
        verify_private_source_identity(
            output_parent_fd, stage_name, stage_identity, "directory"
        )
        try:
            rename_noreplace_at(
                output_parent_fd, stage_name, output_parent_fd, bundle_name
            )
        except FileExistsError as exc:
            raise BundleError("bundle directory appeared during atomic publication") from exc
        published_dir = True
        os.fchmod(stage_fd, 0o755)
        if stat.S_IMODE(os.fstat(stage_fd).st_mode) != 0o755:
            raise BundleError("published bundle directory mode could not be finalized")
        verify_published_identity(
            output_parent_fd, bundle_name, stage_identity, "directory"
        )
        verify_private_source_identity(
            output_parent_fd, archive_temp_name, archive_identity, "file"
        )
        try:
            rename_noreplace_at(
                output_parent_fd,
                archive_temp_name,
                output_parent_fd,
                final_archive_name,
            )
        except FileExistsError as exc:
            raise BundleError(
                "bundle archive appeared during atomic publication; "
                "owned directory was retained without path-based cleanup"
            ) from exc
        published_tar = True
        verify_published_identity(
            output_parent_fd, final_archive_name, archive_identity, "file"
        )
        recheck_repository_binding(binding)
        verify_published_identity(
            output_parent_fd, bundle_name, stage_identity, "directory"
        )
        verify_published_identity(
            output_parent_fd, final_archive_name, archive_identity, "file"
        )
        verify_directory_path_identity(
            output_parent, output_parent_identity, "bundle output directory"
        )
        return final_dir, final_tar
    except Exception as exc:
        if published_dir or published_tar:
            retained = [
                bundle_name if published_dir else stage_name,
                final_archive_name if published_tar else archive_temp_name,
            ]
            raise BundleError(
                f"bundle publication did not complete ({exc}); already published owned "
                "paths and private failure evidence were retained without path deletion: "
                f"{[name for name in retained if name is not None]}"
            ) from exc
        retained = [
            name
            for name in (stage_name, archive_temp_name)
            if name is not None
        ]
        if retained:
            raise BundleError(
                f"{exc}; private failure evidence was retained without path deletion: "
                f"{retained}"
            ) from exc
        raise
    finally:
        for fd in (archive_fd, payload_fd, stage_fd):
            if fd is not None:
                os.close(fd)
        os.close(output_parent_fd)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package-tar", required=True)
    parser.add_argument("--card-profile", required=True)
    parser.add_argument("--current-baseline", required=True)
    parser.add_argument("--purpose", required=True)
    parser.add_argument(
        "--action-policy",
        choices=("full", "install-modules-only"),
        default="full",
        help="target action allowlist; default preserves the historical two-action workflow",
    )
    parser.add_argument("--source-date-epoch", required=True, type=int)
    parser.add_argument("--output-dir", required=True)
    return parser.parse_args()


def main() -> int:
    try:
        final_dir, final_tar = build_bundle(parse_args())
    except (BundleError, OSError) as exc:
        print(f"error: {exc}", file=os.sys.stderr)
        return 1
    print(f"bundle: {final_dir}")
    print(f"archive: {final_tar}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
