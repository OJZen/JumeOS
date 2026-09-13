#!/usr/bin/env python3
"""Create and verify the canonical R46H Git source snapshot on one open FD."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tarfile
import threading
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


TRUSTED_GIT = Path("/usr/bin/git")
SAFE_EXEC_PATH = "/usr/bin:/bin"
MAX_GIT_DIAGNOSTIC_BYTES = 64 * 1024
MAINLINE_PATH = "mainline"
BUILD_SCRIPT_RELPATH = "mainline/scripts/build-kernel.sh"
HELPER_RELPATH = "mainline/scripts/r46h-source-snapshot.py"
SNAPSHOT_NAME_RE = re.compile(r"^r46h-build-input\.[A-Za-z0-9]+$")
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
INITIAL_IDENTITY_RE = re.compile(
    r"^(?P<dev>[0-9]+):(?P<ino>[0-9]+):(?P<mode>[0-7]{3,4}):"
    r"(?P<nlink>[0-9]+):(?P<uid>[0-9]+):(?P<size>[0-9]+)$"
)
GIT_CONFIG_OVERRIDES = (
    "core.fsmonitor=false",
    "core.untrackedCache=false",
    "core.hooksPath=/dev/null",
    "core.attributesFile=/dev/null",
    "tar.umask=0002",
)
MANIFEST_FIELDS = (
    "KERNEL_VERSION",
    "KERNEL_TARBALL",
    "KERNEL_URL",
    "KERNEL_MIRROR_URL",
    "KERNEL_SHA256",
    "KERNEL_LOCALVERSION",
    "KERNEL_PATCH_LAST",
    "BUILDER_IMAGE",
    "BUILD_VOLUME_PREFIX",
)


class SnapshotError(RuntimeError):
    pass


def clean_git_environment() -> Dict[str, str]:
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


def require_trusted_git() -> None:
    try:
        metadata = os.stat(TRUSTED_GIT, follow_symlinks=False)
    except OSError as exc:
        raise SnapshotError(f"trusted Git is unavailable: {TRUSTED_GIT}: {exc}") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or TRUSTED_GIT.is_symlink()
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) & 0o022
        or not os.access(TRUSTED_GIT, os.X_OK)
    ):
        raise SnapshotError(f"trusted Git has unsafe identity or mode: {TRUSTED_GIT}")


def git_command(repo_root: Path, args: Sequence[str]) -> List[str]:
    require_trusted_git()
    command = [str(TRUSTED_GIT), "--no-replace-objects"]
    for override in GIT_CONFIG_OVERRIDES:
        command.extend(("-c", override))
    command.extend(("-C", str(repo_root)))
    command.extend(args)
    return command


def run_git(
    repo_root: Path,
    args: Sequence[str],
    label: str,
    *,
    input_data: Optional[bytes] = None,
) -> bytes:
    result = subprocess.run(
        git_command(repo_root, args),
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=clean_git_environment(),
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise SnapshotError(f"cannot {label}: {detail or 'Git exited nonzero'}")
    return result.stdout


def decode_one_line(raw: bytes, label: str) -> str:
    if b"\0" in raw:
        raise SnapshotError(f"{label} is malformed")
    try:
        text = raw.decode("utf-8", "strict").rstrip("\n")
    except UnicodeDecodeError as exc:
        raise SnapshotError(f"{label} is not UTF-8") from exc
    if not text or "\n" in text:
        raise SnapshotError(f"{label} is malformed")
    return text


def require_repository_root(repo_root: Path) -> None:
    top_level = decode_one_line(
        run_git(repo_root, ("rev-parse", "--show-toplevel"), "locate repository"),
        "repository root",
    )
    if Path(top_level).resolve(strict=True) != repo_root:
        raise SnapshotError("source helper is not operating on the requested repository root")


def require_archive_repository_state(repo_root: Path) -> None:
    config = run_git(
        repo_root,
        ("config", "--null", "--includes", "--name-only", "--list"),
        "inspect archive-affecting Git configuration",
    )
    for raw_name in config.split(b"\0"):
        if not raw_name:
            continue
        try:
            name = raw_name.decode("utf-8", "strict").lower()
        except UnicodeDecodeError as exc:
            raise SnapshotError("repository Git configuration is not canonical text") from exc
        if name.startswith("tar.") and name != "tar.umask":
            raise SnapshotError(
                f"repository archive-affecting Git configuration is forbidden: {name}"
            )

    attributes_path = Path(
        decode_one_line(
            run_git(
                repo_root,
                ("rev-parse", "--path-format=absolute", "--git-path", "info/attributes"),
                "locate repository-local attributes",
            ),
            "repository-local attributes path",
        )
    )
    if not attributes_path.is_absolute():
        raise SnapshotError("repository-local attributes path is not absolute")
    try:
        os.lstat(attributes_path)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise SnapshotError(f"cannot inspect repository-local attributes: {exc}") from exc
    raise SnapshotError(
        f"repository-local info/attributes is forbidden for canonical archives: {attributes_path}"
    )


def resolve_head(repo_root: Path) -> str:
    head = decode_one_line(
        run_git(
            repo_root,
            ("rev-parse", "--verify", "HEAD^{commit}"),
            "resolve source HEAD",
        ),
        "source HEAD",
    )
    if SHA1_RE.fullmatch(head) is None:
        raise SnapshotError("source HEAD is not a full SHA-1 commit ID")
    return head


def parse_tree(
    repo_root: Path, head: str
) -> Tuple[bytes, Dict[str, Tuple[str, str, str]], Tuple[str, ...]]:
    raw = run_git(
        repo_root,
        ("ls-tree", "-r", "-t", "-z", "--full-tree", head, "--", MAINLINE_PATH),
        "inspect committed mainline tree",
    )
    entries: Dict[str, Tuple[str, str, str]] = {}
    for record in (item for item in raw.split(b"\0") if item):
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_type, object_id = metadata.decode("ascii", "strict").split()
            path = raw_path.decode("utf-8", "strict")
        except (UnicodeDecodeError, ValueError) as exc:
            raise SnapshotError("cannot parse committed mainline tree") from exc
        if path in entries:
            raise SnapshotError(f"duplicate committed mainline path: {path}")
        if object_type == "tree":
            if mode != "040000":
                raise SnapshotError(f"unsafe committed directory mode: {mode} {path}")
        elif object_type == "blob":
            if mode not in {"100644", "100755"}:
                raise SnapshotError(f"unsafe committed file mode or link: {mode} {path}")
        else:
            raise SnapshotError(
                f"unsupported committed object type in mainline: {mode} {object_type} {path}"
            )
        if SHA1_RE.fullmatch(object_id) is None:
            raise SnapshotError(f"invalid committed object ID: {path}")
        entries[path] = (mode, object_type, object_id)
    if MAINLINE_PATH not in entries or entries[MAINLINE_PATH][1] != "tree":
        raise SnapshotError("committed mainline tree is missing")
    paths = tuple(sorted(entries))
    return raw, entries, paths


def require_index_matches_head(
    repo_root: Path, entries: Dict[str, Tuple[str, str, str]]
) -> Tuple[bytes, bytes]:
    expected_blobs = {
        path: (mode, object_id)
        for path, (mode, object_type, object_id) in entries.items()
        if object_type == "blob"
    }
    stage_raw = run_git(
        repo_root,
        ("ls-files", "--stage", "-z", "--", MAINLINE_PATH),
        "inspect mainline index entries",
    )
    staged: Dict[str, Tuple[str, str]] = {}
    for record in (item for item in stage_raw.split(b"\0") if item):
        try:
            metadata, raw_path = record.split(b"\t", 1)
            mode, object_id, stage = metadata.decode("ascii", "strict").split()
            path = raw_path.decode("utf-8", "strict")
        except (UnicodeDecodeError, ValueError) as exc:
            raise SnapshotError("cannot parse mainline index entries") from exc
        if stage != "0" or path in staged:
            raise SnapshotError(f"mainline index has an unmerged or duplicate entry: {path}")
        staged[path] = (mode, object_id)
    if staged != expected_blobs:
        raise SnapshotError("mainline index entries do not exactly match HEAD")

    flags_raw = run_git(
        repo_root,
        ("ls-files", "-v", "-z", "--", MAINLINE_PATH),
        "inspect mainline index flags",
    )
    flagged_paths = set()
    for record in (item for item in flags_raw.split(b"\0") if item):
        if len(record) < 3 or record[1:2] != b" ":
            raise SnapshotError("cannot parse mainline index flags")
        try:
            tag = record[:1].decode("ascii", "strict")
            path = record[2:].decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise SnapshotError("mainline index flags are not canonical text") from exc
        if path in flagged_paths:
            raise SnapshotError(f"duplicate mainline index flag entry: {path}")
        flagged_paths.add(path)
        if tag != "H":
            raise SnapshotError(
                f"mainline uses assume-unchanged, skip-worktree, or unsafe index state: {path}"
            )
    if flagged_paths != set(expected_blobs):
        raise SnapshotError("mainline index flag set does not exactly match HEAD")
    return stage_raw, flags_raw


def require_clean_mainline(repo_root: Path) -> None:
    status = run_git(
        repo_root,
        (
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--ignore-submodules=none",
            "--",
            MAINLINE_PATH,
        ),
        "inspect mainline worktree",
    )
    if status:
        lines = status.decode("utf-8", "replace").splitlines()
        raise SnapshotError(f"mainline worktree must be completely clean: {lines[:8]}")


def require_safe_export_attributes(
    repo_root: Path, head: str, paths: Iterable[str]
) -> bytes:
    ordered_paths = tuple(paths)
    stdin = b"\0".join(path.encode("utf-8") for path in ordered_paths) + b"\0"
    raw = run_git(
        repo_root,
        (
            "check-attr",
            f"--source={head}",
            "--stdin",
            "-z",
            "export-ignore",
            "export-subst",
        ),
        "inspect committed archive attributes",
        input_data=stdin,
    )
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) != len(ordered_paths) * 2 * 3:
        raise SnapshotError("committed archive attribute output is incomplete")
    expected = set(ordered_paths)
    seen = set()
    for offset in range(0, len(fields), 3):
        try:
            path = fields[offset].decode("utf-8", "strict")
            attribute = fields[offset + 1].decode("ascii", "strict")
            value = fields[offset + 2].decode("utf-8", "strict")
        except UnicodeDecodeError as exc:
            raise SnapshotError("committed archive attributes are not canonical text") from exc
        key = (path, attribute)
        if path not in expected or attribute not in {"export-ignore", "export-subst"}:
            raise SnapshotError("committed archive attribute output is malformed")
        if key in seen:
            raise SnapshotError(f"duplicate committed archive attribute: {path} {attribute}")
        seen.add(key)
        if value not in {"unspecified", "unset"}:
            raise SnapshotError(
                f"committed {attribute} is forbidden for canonical archives: {path}={value}"
            )
    return raw


def stable_file_state(metadata: os.stat_result) -> Tuple[int, ...]:
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


def require_running_file_matches_head(
    repo_root: Path,
    head: str,
    relative: str,
    named_path: Path,
    entries: Dict[str, Tuple[str, str, str]],
) -> None:
    expected = entries.get(relative)
    if expected is None or expected[0:2] != ("100755", "blob"):
        raise SnapshotError(f"committed executable is not a 100755 blob: {relative}")
    expected_bytes = run_git(
        repo_root,
        ("cat-file", "blob", f"{head}:{relative}"),
        f"read committed executable {relative}",
    )
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(named_path, flags)
    except OSError as exc:
        raise SnapshotError(f"cannot open running executable {relative}: {exc}") from exc
    try:
        before = os.fstat(descriptor)
        named = os.stat(named_path, follow_symlinks=False)
        before_state = stable_file_state(before)
        if (
            not stat.S_ISREG(before.st_mode)
            or (named.st_dev, named.st_ino) != (before.st_dev, before.st_ino)
            or stat.S_IMODE(before.st_mode) != 0o755
            or before.st_nlink != 1
            or before.st_uid != os.geteuid()
        ):
            raise SnapshotError(
                f"running executable has unsafe mode, owner, link count, or identity: {relative}"
            )
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            actual_bytes = handle.read()
        after = os.fstat(descriptor)
        if stable_file_state(after) != before_state:
            raise SnapshotError(f"running executable changed during provenance check: {relative}")
        if actual_bytes != expected_bytes:
            raise SnapshotError(f"running executable bytes do not match HEAD: {relative}")
    finally:
        os.close(descriptor)


def require_repository_binding(
    repo_root: Path,
    running_script: Path,
    helper_path: Path,
    *,
    expected_head: Optional[str] = None,
    expected_fingerprint: Optional[str] = None,
) -> Tuple[str, str, Dict[str, Tuple[str, str, str]]]:
    require_repository_root(repo_root)
    require_archive_repository_state(repo_root)
    head = resolve_head(repo_root)
    if expected_head is not None and head != expected_head:
        raise SnapshotError("source HEAD changed while creating the canonical archive")
    tree_raw, entries, paths = parse_tree(repo_root, head)
    stage_raw, flags_raw = require_index_matches_head(repo_root, entries)
    require_clean_mainline(repo_root)
    attributes_raw = require_safe_export_attributes(repo_root, head, paths)

    expected_script = repo_root / BUILD_SCRIPT_RELPATH
    expected_helper = repo_root / HELPER_RELPATH
    if running_script.absolute() != expected_script or helper_path.absolute() != expected_helper:
        raise SnapshotError("source provenance executables are not at their fixed repository paths")
    require_running_file_matches_head(
        repo_root, head, BUILD_SCRIPT_RELPATH, running_script, entries
    )
    require_running_file_matches_head(repo_root, head, HELPER_RELPATH, helper_path, entries)

    fingerprint = hashlib.sha256(
        b"tree\0"
        + tree_raw
        + b"index\0"
        + stage_raw
        + b"flags\0"
        + flags_raw
        + b"attributes\0"
        + attributes_raw
    ).hexdigest()
    if expected_fingerprint is not None and fingerprint != expected_fingerprint:
        raise SnapshotError("HEAD, index, or archive attributes changed during snapshot creation")
    return head, fingerprint, entries


def snapshot_fd_state(fd: int) -> Tuple[int, ...]:
    try:
        metadata = os.fstat(fd)
    except OSError as exc:
        raise SnapshotError(f"cannot inspect snapshot FD {fd}: {exc}") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.geteuid():
        raise SnapshotError("snapshot FD is not a regular file owned by the current user")
    return stable_file_state(metadata)


def initial_file_identity(metadata: os.stat_result) -> Tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        stat.S_IMODE(metadata.st_mode),
        metadata.st_nlink,
        metadata.st_uid,
        metadata.st_size,
    )


def encode_initial_identity(identity: Tuple[int, ...]) -> str:
    dev, inode, mode, nlink, uid, size = identity
    return f"{dev}:{inode}:{mode:o}:{nlink}:{uid}:{size}"


def decode_initial_identity(value: str) -> Tuple[int, ...]:
    match = INITIAL_IDENTITY_RE.fullmatch(value)
    if match is None:
        raise SnapshotError("mktemp identity token is malformed")
    return (
        int(match.group("dev"), 10),
        int(match.group("ino"), 10),
        int(match.group("mode"), 8),
        int(match.group("nlink"), 10),
        int(match.group("uid"), 10),
        int(match.group("size"), 10),
    )


def unlink_owned_snapshot(
    fd: int,
    snapshot_path: Path,
    cache_dir: Path,
    initial_identity: str,
    *,
    require_initial_state: bool = False,
) -> None:
    cache_dir = cache_dir.resolve(strict=True)
    if snapshot_path.parent.resolve(strict=True) != cache_dir:
        raise SnapshotError("snapshot temporary path is outside the fixed cache directory")
    if SNAPSHOT_NAME_RE.fullmatch(snapshot_path.name) is None:
        raise SnapshotError("snapshot temporary name is outside the owned pattern")
    expected_identity = decode_initial_identity(initial_identity)
    fd_metadata = os.fstat(fd)
    fd_identity = initial_file_identity(fd_metadata)
    if (
        not stat.S_ISREG(fd_metadata.st_mode)
        or fd_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(fd_metadata.st_mode) not in {0o400, 0o600}
        or fd_metadata.st_nlink not in {0, 1}
    ):
        raise SnapshotError("snapshot temporary FD has unsafe initial identity or mode")
    if (fd_identity[0], fd_identity[1], fd_identity[4]) != (
        expected_identity[0],
        expected_identity[1],
        expected_identity[4],
    ):
        raise SnapshotError("snapshot FD was replaced after mktemp")
    if require_initial_state and fd_identity != expected_identity:
        raise SnapshotError("snapshot FD no longer has the exact mktemp identity")
    if require_initial_state and expected_identity[2:] != (
        0o600,
        1,
        os.geteuid(),
        0,
    ):
        raise SnapshotError("new snapshot mktemp identity is not an empty mode-0600 file")

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    directory_fd = os.open(cache_dir, flags)
    try:
        try:
            named = os.stat(snapshot_path.name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            if os.fstat(fd).st_nlink == 0:
                return
            raise SnapshotError("owned snapshot name disappeared before it could be unlinked")
        named_identity = initial_file_identity(named)
        if (
            not stat.S_ISREG(named.st_mode)
            or named_identity != expected_identity
            or fd_identity != expected_identity
        ):
            raise SnapshotError("snapshot name was replaced; refusing path-based cleanup")
        os.unlink(snapshot_path.name, dir_fd=directory_fd)
    finally:
        os.close(directory_fd)
    if os.fstat(fd).st_nlink != 0:
        raise SnapshotError("snapshot inode retained an unexpected link after unlink")


def rewind_fd(fd: int) -> None:
    os.lseek(fd, 0, os.SEEK_SET)


def hash_fd(fd: int) -> str:
    rewind_fd(fd)
    digest = hashlib.sha256()
    while True:
        block = os.read(fd, 1024 * 1024)
        if not block:
            break
        digest.update(block)
    rewind_fd(fd)
    return digest.hexdigest()


def archive_to_fd(repo_root: Path, head: str, fd: int) -> None:
    os.ftruncate(fd, 0)
    rewind_fd(fd)
    process = subprocess.Popen(
        git_command(
            repo_root,
            (
                "archive",
                "--no-worktree-attributes",
                "--format=tar",
                head,
                "--",
                MAINLINE_PATH,
            ),
        ),
        stdout=fd,
        stderr=subprocess.PIPE,
        env=clean_git_environment(),
    )
    assert process.stderr is not None
    diagnostic = bytearray()
    truncated = threading.Event()
    drain_error: List[BaseException] = []

    def drain_stderr() -> None:
        try:
            for block in iter(lambda: process.stderr.read(64 * 1024), b""):
                remaining = MAX_GIT_DIAGNOSTIC_BYTES - len(diagnostic)
                if remaining > 0:
                    diagnostic.extend(block[:remaining])
                if len(block) > remaining:
                    truncated.set()
        except BaseException as exc:  # surfaced in the caller below
            drain_error.append(exc)

    drain_thread = threading.Thread(target=drain_stderr, daemon=True)
    drain_thread.start()
    returncode = process.wait()
    drain_thread.join()
    process.stderr.close()
    if drain_error:
        os.ftruncate(fd, 0)
        rewind_fd(fd)
        raise SnapshotError(f"cannot drain Git archive diagnostics: {drain_error[0]}")
    if returncode != 0:
        detail = bytes(diagnostic).decode("utf-8", "replace").strip()
        if truncated.is_set():
            detail = f"{detail}\n[diagnostics truncated]" if detail else "[diagnostics truncated]"
        os.ftruncate(fd, 0)
        rewind_fd(fd)
        raise SnapshotError(
            f"cannot create committed mainline archive: {detail or f'Git exited {returncode}'}"
        )
    os.fsync(fd)
    if os.fstat(fd).st_size <= 0:
        raise SnapshotError("committed mainline archive is empty")
    rewind_fd(fd)


def require_archive_commit(repo_root: Path, head: str, fd: int) -> None:
    rewind_fd(fd)
    result = subprocess.run(
        git_command(repo_root, ("get-tar-commit-id",)),
        stdin=fd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=clean_git_environment(),
    )
    rewind_fd(fd)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise SnapshotError(f"cannot read Git archive commit ID: {detail}")
    archive_head = decode_one_line(result.stdout, "Git archive commit ID")
    if archive_head != head:
        raise SnapshotError("Git archive commit ID does not match fixed source HEAD")


def git_blob_id(payload: bytes) -> str:
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def validate_archive(
    fd: int, entries: Dict[str, Tuple[str, str, str]]
) -> Dict[str, str]:
    rewind_fd(fd)
    duplicate = os.dup(fd)
    manifest_bytes: Optional[bytes] = None
    seen = set()
    try:
        with os.fdopen(duplicate, "rb") as handle:
            with tarfile.open(fileobj=handle, mode="r:") as archive:
                for member in archive:
                    path = member.name.rstrip("/")
                    if path in seen:
                        raise SnapshotError(f"duplicate Git archive member: {path}")
                    seen.add(path)
                    expected = entries.get(path)
                    if expected is None:
                        raise SnapshotError(f"unexpected Git archive member: {path}")
                    mode, object_type, object_id = expected
                    if object_type == "tree":
                        if not member.isdir() or member.mode != 0o775:
                            raise SnapshotError(
                                f"Git archive directory type or mode mismatch: {path}"
                            )
                        continue
                    archive_mode = 0o664 if mode == "100644" else 0o775
                    if not member.isreg() or member.mode != archive_mode:
                        raise SnapshotError(f"Git archive file type or mode mismatch: {path}")
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise SnapshotError(f"cannot read Git archive member: {path}")
                    payload = stream.read()
                    if len(payload) != member.size or git_blob_id(payload) != object_id:
                        raise SnapshotError(f"Git archive bytes do not match HEAD blob: {path}")
                    if path == "mainline/manifest.env":
                        manifest_bytes = payload
    except (OSError, tarfile.TarError) as exc:
        raise SnapshotError(f"cannot validate Git archive: {exc}") from exc
    finally:
        rewind_fd(fd)
    if seen != set(entries):
        missing = sorted(set(entries) - seen)
        raise SnapshotError(f"Git archive member set is incomplete: {missing[:8]}")
    if manifest_bytes is None:
        raise SnapshotError("Git archive is missing mainline/manifest.env")
    return parse_manifest(manifest_bytes)


def parse_manifest(payload: bytes) -> Dict[str, str]:
    if b"\0" in payload or b"\r" in payload:
        raise SnapshotError("manifest.env contains NUL or carriage-return bytes")
    if not payload.endswith(b"\n") or b"\n\n" in payload:
        raise SnapshotError("manifest.env does not use canonical non-empty LF lines")
    try:
        text = payload.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise SnapshotError("manifest.env is not UTF-8") from exc
    values: Dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line or "=" not in line:
            raise SnapshotError(f"manifest.env:{line_number}: malformed field")
        name, value = line.split("=", 1)
        if name in values or not value:
            raise SnapshotError(f"manifest.env:{line_number}: duplicate or empty field")
        values[name] = value
    missing = [name for name in MANIFEST_FIELDS if name not in values]
    if missing:
        raise SnapshotError(f"manifest.env is missing required fields: {missing}")
    return {name: values[name] for name in MANIFEST_FIELDS}


def encode_state(state: Tuple[int, ...]) -> str:
    return ":".join(str(item) for item in state)


def decode_state(value: str) -> Tuple[int, ...]:
    if re.fullmatch(r"[0-9]+(?::[0-9]+){8}", value) is None:
        raise SnapshotError("snapshot state token is malformed")
    return tuple(int(item, 10) for item in value.split(":"))


def create_snapshot(
    repo_root: Path,
    running_script: Path,
    helper_path: Path,
    snapshot_path: Path,
    fd: int,
    initial_identity: str,
) -> Dict[str, str]:
    unlink_owned_snapshot(
        fd,
        snapshot_path,
        repo_root / "mainline/.cache",
        initial_identity,
        require_initial_state=True,
    )
    head, fingerprint, entries = require_repository_binding(
        repo_root, running_script, helper_path
    )
    archive_to_fd(repo_root, head, fd)
    snapshot_sha256 = hash_fd(fd)
    require_archive_commit(repo_root, head, fd)
    manifest = validate_archive(fd, entries)
    require_repository_binding(
        repo_root,
        running_script,
        helper_path,
        expected_head=head,
        expected_fingerprint=fingerprint,
    )
    os.fchmod(fd, 0o400)
    os.fsync(fd)
    state = snapshot_fd_state(fd)
    if state[3] != 0 or stat.S_IMODE(state[2]) != 0o400:
        raise SnapshotError("canonical snapshot FD is not anonymous and read-only by mode")
    if hash_fd(fd) != snapshot_sha256 or snapshot_fd_state(fd) != state:
        raise SnapshotError("canonical snapshot changed during final verification")
    receipt = {
        "format_version": "1",
        "source_git_commit": head,
        "source_snapshot_sha256": snapshot_sha256,
        "snapshot_state": encode_state(state),
    }
    receipt.update(manifest)
    return receipt


def verify_snapshot(fd: int, expected_state: str, expected_sha256: str) -> None:
    try:
        state = decode_state(expected_state)
        if SHA256_RE.fullmatch(expected_sha256) is None:
            raise SnapshotError("expected snapshot SHA256 is malformed")
        if snapshot_fd_state(fd) != state:
            raise SnapshotError("snapshot FD identity or metadata changed")
        if hash_fd(fd) != expected_sha256:
            raise SnapshotError("snapshot FD bytes changed")
        if snapshot_fd_state(fd) != state:
            raise SnapshotError("snapshot FD changed while being verified")
    finally:
        rewind_fd(fd)


def print_receipt(receipt: Dict[str, str]) -> None:
    order = (
        "format_version",
        "source_git_commit",
        "source_snapshot_sha256",
        "snapshot_state",
        *MANIFEST_FIELDS,
    )
    for name in order:
        value = receipt[name]
        if "\n" in value or "\r" in value or not value:
            raise SnapshotError(f"unsafe receipt value: {name}")
        print(f"{name}={value}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create")
    create.add_argument("--repo-root", required=True)
    create.add_argument("--running-script", required=True)
    create.add_argument("--snapshot-path", required=True)
    create.add_argument("--fd", required=True, type=int)
    create.add_argument("--initial-identity", required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--fd", required=True, type=int)
    verify.add_argument("--state", required=True)
    verify.add_argument("--sha256", required=True)

    cleanup = subparsers.add_parser("unlink-owned")
    cleanup.add_argument("--repo-root", required=True)
    cleanup.add_argument("--snapshot-path", required=True)
    cleanup.add_argument("--fd", required=True, type=int)
    cleanup.add_argument("--initial-identity", required=True)

    identity = subparsers.add_parser("fd-identity")
    identity.add_argument("--fd", required=True, type=int)
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "create":
            repo_root = Path(args.repo_root).resolve(strict=True)
            running_script = Path(args.running_script).absolute()
            helper_path = Path(__file__).absolute()
            receipt = create_snapshot(
                repo_root,
                running_script,
                helper_path,
                Path(args.snapshot_path).absolute(),
                args.fd,
                args.initial_identity,
            )
            print_receipt(receipt)
        elif args.command == "verify":
            verify_snapshot(args.fd, args.state, args.sha256)
        elif args.command == "unlink-owned":
            repo_root = Path(args.repo_root).resolve(strict=True)
            unlink_owned_snapshot(
                args.fd,
                Path(args.snapshot_path).absolute(),
                repo_root / "mainline/.cache",
                args.initial_identity,
            )
        elif args.command == "fd-identity":
            print(encode_initial_identity(initial_file_identity(os.fstat(args.fd))))
        else:  # argparse enforces the command set
            raise SnapshotError("unsupported command")
    except (OSError, SnapshotError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
