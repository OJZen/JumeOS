#!/usr/bin/env python3
"""Cross-platform build/cache driver for the R46H Rust card toolchain.

This module deliberately has no media-discovery or raw-device code. It owns
only Cargo process execution, private build directories, release publication,
and narrowly scoped cleanup beneath a validated cache root.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import plistlib
import re
import secrets
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, TextIO, Tuple


EX_USAGE = 64
EX_DATAERR = 65
EX_UNAVAILABLE = 69
EX_TEMPFAIL = 75
DEFAULT_LOCK_TIMEOUT_SECONDS = 60.0
KNOWN_CACHE_CHILDREN = frozenset({"cargo-home", "target", "work"})
CACHE_MARKER_NAME = ".r46h-card-cache-v1.json"
CACHE_MARKER_SCHEMA = "r46h-card-cache/v1"
SOURCE_MANIFEST_SCHEMA = "r46h-card-source-manifest/v1"
BUILD_RECEIPT_SCHEMA = "r46h-card-build-receipt/v1"
CURRENT_SCHEMA = "r46h-card-build-current/v1"
BUILD_ENVIRONMENT_SCHEMA = "r46h-card-build-env/v1"
MINIMUM_PYTHON = (3, 10)
GENERATION_PATTERN = re.compile(r"^build-[0-9a-f]{12}-[0-9a-f]{12}-[0-9a-f]{8}$")
BUILD_SOURCE_PATHS = (
    ".gitattributes",
    ".github/workflows/ci.yml",
    "mainline/README.md",
    "mainline/scripts/build-r46h-card-toolchain.sh",
    "mainline/scripts/clean-r46h-card-toolchain.sh",
    "mainline/scripts/r46h-card-toolchain-env.sh",
    "mainline/scripts/r46h_card_toolchain.py",
    "mainline/scripts/r46h_card_macos_readonly.py",
    "mainline/tests/test_r46h_card_toolchain_build.py",
    "mainline/tests/test_r46h_card_macos_readonly.py",
    "mainline/tools/r46h-card-toolchain",
)


class DriverError(RuntimeError):
    """Expected fail-closed driver error with a stable process exit code."""

    def __init__(self, message: str, exit_code: int = EX_DATAERR) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def require_supported_python(version: Sequence[int] = sys.version_info) -> None:
    if tuple(version[:2]) < MINIMUM_PYTHON:
        required = ".".join(str(component) for component in MINIMUM_PYTHON)
        actual = ".".join(str(component) for component in version[:2])
        raise DriverError(
            f"Python {required} or newer is required (running {actual})",
            EX_UNAVAILABLE,
        )


@dataclasses.dataclass(frozen=True)
class Layout:
    repo_root: Path
    workspace: Path
    out_root: Path
    release_dir: Path
    cache_root: Path

    @property
    def cargo_home(self) -> Path:
        return self.cache_root / "cargo-home"

    @property
    def target_dir(self) -> Path:
        return self.cache_root / "target"

    @property
    def work_root(self) -> Path:
        return self.cache_root / "work"

    @property
    def state_root(self) -> Path:
        return self.cache_root / "state"

    @property
    def lock_path(self) -> Path:
        return self.state_root / "operation.lock"

    @property
    def marker_path(self) -> Path:
        return self.cache_root / CACHE_MARKER_NAME


@dataclasses.dataclass(frozen=True)
class MacStorageIdentity:
    mount_point: Optional[Path]
    internal: Optional[bool]
    physical_id: Optional[str]


@dataclasses.dataclass(frozen=True)
class SourceSnapshot:
    root: Path
    commit: str
    tree: str
    manifest_path: Path
    manifest_sha256: str
    file_count: int
    driver_sha256: str
    cargo_lock_sha256: str


@dataclasses.dataclass(frozen=True)
class MountBoundary:
    device: int
    token: str


def _host_tag() -> str:
    system = {
        "darwin": "darwin",
        "linux": "linux",
        "win32": "windows",
    }.get(sys.platform, platform.system().lower())
    machine = platform.machine().lower() or "unknown"
    clean_system = re.sub(r"[^a-z0-9_.-]", "-", system)
    clean_machine = re.sub(r"[^a-z0-9_.-]", "-", machine)
    return f"{clean_system}-{clean_machine}"


def _repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_absolute(raw: str, label: str) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise DriverError(f"{label} must be an absolute path: {raw}")
    return candidate.resolve(strict=False)


def _absolute_lexical(raw: str, label: str) -> Path:
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise DriverError(f"{label} must be an absolute path: {raw}")
    return Path(os.path.abspath(os.path.normpath(str(candidate))))


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _is_link_or_reparse(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    return _metadata_is_link_or_reparse(metadata)


def _metadata_is_link_or_reparse(metadata: os.stat_result) -> bool:
    if stat.S_ISLNK(metadata.st_mode):
        return True
    attributes = getattr(metadata, "st_file_attributes", None)
    if os.name == "nt" and attributes is None:
        raise DriverError("cannot inspect Windows reparse-point attributes")
    if attributes is None:
        return False
    if not isinstance(attributes, int):
        raise DriverError("invalid Windows reparse-point attributes")
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _unlink_link_or_reparse(path: Path, metadata: Optional[os.stat_result] = None) -> None:
    metadata = metadata or path.lstat()
    if os.name == "nt" and stat.S_ISDIR(metadata.st_mode):
        path.rmdir()
    else:
        path.unlink()


def _parse_linux_mount_id(payload: str) -> str:
    values = []
    for line in payload.splitlines():
        if line.startswith("mnt_id:"):
            values.append(line.partition(":")[2].strip())
    if len(values) != 1 or not re.fullmatch(r"[1-9][0-9]*", values[0]):
        raise DriverError("cannot prove Linux mount identity from fdinfo")
    return values[0]


def _darwin_mount_token(descriptor: int) -> str:
    """Return fsid plus mount point from Darwin fstatfs(2)."""

    import ctypes  # pylint: disable=import-outside-toplevel

    class DarwinStatFs(ctypes.Structure):
        _fields_ = [
            ("f_bsize", ctypes.c_uint32),
            ("f_iosize", ctypes.c_int32),
            ("f_blocks", ctypes.c_uint64),
            ("f_bfree", ctypes.c_uint64),
            ("f_bavail", ctypes.c_uint64),
            ("f_files", ctypes.c_uint64),
            ("f_ffree", ctypes.c_uint64),
            ("f_fsid", ctypes.c_int32 * 2),
            ("f_owner", ctypes.c_uint32),
            ("f_type", ctypes.c_uint32),
            ("f_flags", ctypes.c_uint32),
            ("f_fssubtype", ctypes.c_uint32),
            ("f_fstypename", ctypes.c_char * 16),
            ("f_mntonname", ctypes.c_char * 1024),
            ("f_mntfromname", ctypes.c_char * 1024),
            ("f_flags_ext", ctypes.c_uint32),
            ("f_reserved", ctypes.c_uint32 * 7),
        ]

    libc = ctypes.CDLL(None, use_errno=True)
    fstatfs = libc.fstatfs
    fstatfs.argtypes = [ctypes.c_int, ctypes.POINTER(DarwinStatFs)]
    fstatfs.restype = ctypes.c_int
    value = DarwinStatFs()
    if fstatfs(descriptor, ctypes.byref(value)) != 0:
        error_number = ctypes.get_errno()
        raise DriverError(f"Darwin fstatfs failed with errno {error_number}")
    raw_mount = bytes(value.f_mntonname).split(b"\0", 1)[0]
    try:
        mount_point = raw_mount.decode("utf-8")
    except UnicodeError as error:
        raise DriverError("Darwin mount point is not UTF-8") from error
    if not mount_point.startswith("/") or "\0" in mount_point:
        raise DriverError("Darwin mount point is invalid")
    return f"darwin-fsid:{value.f_fsid[0]}:{value.f_fsid[1]}:mount:{mount_point}"


def _descriptor_mount_boundary(descriptor: int) -> MountBoundary:
    metadata = os.fstat(descriptor)
    if os.name == "nt":
        return MountBoundary(
            int(metadata.st_dev),
            f"windows-volume:{int(metadata.st_dev)}",
        )
    if sys.platform.startswith("linux"):
        fdinfo = Path(f"/proc/self/fdinfo/{descriptor}")
        try:
            mount_id = _parse_linux_mount_id(fdinfo.read_text(encoding="ascii"))
        except (OSError, UnicodeError) as error:
            raise DriverError("cannot read Linux mount identity from fdinfo") from error
        return MountBoundary(int(metadata.st_dev), f"linux-mnt-id:{mount_id}")
    if sys.platform == "darwin":
        return MountBoundary(int(metadata.st_dev), _darwin_mount_token(descriptor))
    try:
        fsid = os.fstatvfs(descriptor).f_fsid
    except (AttributeError, OSError) as error:
        raise DriverError("cannot prove POSIX filesystem identity") from error
    if not isinstance(fsid, int):
        raise DriverError("invalid POSIX filesystem identity")
    return MountBoundary(int(metadata.st_dev), f"posix-fsid:{fsid}")


def _mount_boundary(path: Path, *, directory: bool) -> MountBoundary:
    """Return a mount identity for one no-follow handle, or fail closed."""

    try:
        before = path.stat(follow_symlinks=False)
    except OSError as error:
        raise DriverError(f"cannot inspect mount boundary: {path}") from error
    if _metadata_is_link_or_reparse(before):
        raise DriverError(f"mount boundary is a link or reparse point: {path}")
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(before.st_mode):
        raise DriverError(f"mount boundary has an unexpected type: {path}")

    if os.name == "nt":
        return MountBoundary(int(before.st_dev), f"windows-volume:{int(before.st_dev)}")

    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    if directory:
        flags |= getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DriverError(f"cannot open mount boundary without following links: {path}") from error
    try:
        after = os.fstat(descriptor)
        if (
            (before.st_dev, before.st_ino, stat.S_IFMT(before.st_mode))
            != (after.st_dev, after.st_ino, stat.S_IFMT(after.st_mode))
            or not expected_type(after.st_mode)
        ):
            raise DriverError(f"mount boundary changed while opening: {path}")
        return _descriptor_mount_boundary(descriptor)
    finally:
        os.close(descriptor)


def _require_mount_boundary(
    path: Path,
    expected: MountBoundary,
    *,
    directory: bool,
    label: str,
) -> os.stat_result:
    metadata = path.stat(follow_symlinks=False)
    if _metadata_is_link_or_reparse(metadata):
        raise DriverError(f"{label} contains a link or reparse point: {path}")
    if metadata.st_dev != expected.device:
        raise DriverError(f"{label} crosses a filesystem: {path}")
    actual = _mount_boundary(path, directory=directory)
    if actual != expected:
        raise DriverError(f"{label} crosses a mount boundary: {path}")
    return metadata


def _reject_symlink_components(path: Path, label: str = "cache path") -> None:
    """Reject existing symlink components before creating a safety root."""

    current = Path(path.anchor)
    for part in path.parts[1:]:
        current = current / part
        try:
            if _is_link_or_reparse(current):
                raise DriverError(f"unsafe symlink in {label}: {current}")
        except OSError as error:
            raise DriverError(f"cannot inspect {label} {current}: {error}") from error


def make_layout(
    cache_root_override: Optional[str] = None,
    repo_root_override: Optional[Path] = None,
) -> Layout:
    repo_root = (repo_root_override or _repo_root_from_script()).resolve(strict=True)
    workspace = repo_root / "mainline" / "tools" / "r46h-card-toolchain"
    out_root = repo_root / "mainline" / "out"
    release_dir = out_root / "r46h-card-toolchain" / "bin" / _host_tag()
    default_cache = out_root / ".cache" / "r46h-card-toolchain"
    raw_cache = cache_root_override or os.environ.get("R46H_CARD_CACHE_ROOT")
    cache_candidate = (
        _absolute_lexical(raw_cache, "R46H_CARD_CACHE_ROOT")
        if raw_cache
        else default_cache
    )

    _reject_symlink_components(workspace)
    _reject_symlink_components(out_root)
    if not workspace.is_dir() or _is_link_or_reparse(workspace):
        raise DriverError(f"missing or unsafe Rust workspace: {workspace}")
    if out_root.exists() and (not out_root.is_dir() or _is_link_or_reparse(out_root)):
        raise DriverError(f"missing or unsafe release root: {out_root}")
    _reject_symlink_components(cache_candidate)
    cache_root = cache_candidate.resolve(strict=False)

    forbidden = {
        Path(cache_root.anchor).resolve(),
        repo_root,
        (repo_root / "mainline").resolve(),
        out_root.resolve(),
        (out_root / "r46h-card-toolchain" / "bin").resolve(strict=False),
    }
    if cache_root in forbidden:
        raise DriverError(f"unsafe cache root: {cache_root}")
    if _is_within(repo_root, cache_root):
        raise DriverError(f"cache root may not contain the repository: {cache_root}")
    if _is_within(release_dir, cache_root):
        raise DriverError(f"cache root may not contain release artifacts: {cache_root}")

    return Layout(
        repo_root=repo_root,
        workspace=workspace,
        out_root=out_root,
        release_dir=release_dir,
        cache_root=cache_root,
    )


def _nearest_existing(path: Path) -> Path:
    current = path
    while not current.exists():
        parent = current.parent
        if parent == current:
            raise DriverError(f"no existing ancestor for path: {path}")
        current = parent
    return current


def _mount_point(path: Path) -> Path:
    current = _nearest_existing(path).resolve(strict=True)
    current_device = current.stat().st_dev
    while current.parent != current:
        parent = current.parent
        if parent.stat().st_dev != current_device:
            break
        current = parent
    return current


def _whole_disk_identifier(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"(disk[0-9]+)(?:s[0-9]+)*", value)
    return match.group(1) if match is not None else None


def _macos_physical_storage_id(payload: Mapping[str, object]) -> Optional[str]:
    physical_stores = payload.get("APFSPhysicalStores")
    if physical_stores is not None:
        if not isinstance(physical_stores, list) or len(physical_stores) != 1:
            return None
        store = physical_stores[0]
        if not isinstance(store, dict):
            return None
        return _whole_disk_identifier(store.get("APFSPhysicalStore"))
    return _whole_disk_identifier(
        payload.get("ParentWholeDisk") or payload.get("DeviceIdentifier")
    )


def query_macos_storage_identity(
    path: Path,
    *,
    runner=subprocess.run,
) -> MacStorageIdentity:
    diskutil = Path("/usr/sbin/diskutil")
    fallback_mount = _mount_point(path)
    if not diskutil.is_file():
        return MacStorageIdentity(fallback_mount, None, None)

    try:
        result = runner(
            [str(diskutil), "info", "-plist", str(fallback_mount)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        payload = plistlib.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException, ValueError):
        return MacStorageIdentity(fallback_mount, None, None)
    if not isinstance(payload, dict):
        return MacStorageIdentity(fallback_mount, None, None)

    mount_raw = payload.get("MountPoint")
    mount = Path(mount_raw).resolve(strict=False) if isinstance(mount_raw, str) else fallback_mount
    internal_raw = payload.get("Internal")
    internal = internal_raw if isinstance(internal_raw, bool) else None
    physical_id = _macos_physical_storage_id(payload)
    return MacStorageIdentity(mount, internal, physical_id)


def _ci_system_storage_allowed(requested: bool) -> bool:
    if not requested:
        return False
    if os.environ.get("CI", "").lower() != "true":
        raise DriverError("system-storage override is restricted to an explicit CI environment")
    return True


def validate_storage(
    layout: Layout,
    platform_name: Optional[str] = None,
    *,
    allow_system_storage_for_ci: bool = False,
) -> None:
    """Keep cache and release publication on one non-system host volume."""

    platform_name = platform_name or sys.platform
    cache_ancestor = _nearest_existing(layout.cache_root)
    output_ancestor = _nearest_existing(layout.release_dir)
    if cache_ancestor.stat().st_dev != output_ancestor.stat().st_dev:
        raise DriverError(
            "R46H_CARD_CACHE_ROOT and mainline/out must be on the same filesystem "
            "for atomic release publication"
        )

    ci_override = _ci_system_storage_allowed(allow_system_storage_for_ci)
    if platform_name == "linux":
        if cache_ancestor.stat().st_dev == Path("/").stat().st_dev and not ci_override:
            raise DriverError(f"cache root is on the Linux root filesystem: {layout.cache_root}")
        return
    if platform_name in {"win32", "windows"}:
        system_drive = os.environ.get("SystemDrive", "C:") + "\\"
        try:
            on_system_drive = cache_ancestor.stat().st_dev == Path(system_drive).stat().st_dev
        except OSError as error:
            if not ci_override:
                raise DriverError("cannot prove cache isolation from Windows SystemDrive") from error
            return
        if on_system_drive and not ci_override:
            raise DriverError(f"cache root is on Windows SystemDrive: {layout.cache_root}")
        return
    if platform_name != "darwin":
        return

    identity = query_macos_storage_identity(layout.cache_root)
    mount = identity.mount_point
    if identity.internal is True:
        if ci_override:
            return
        detail = f" ({identity.physical_id})" if identity.physical_id else ""
        raise DriverError(f"cache root is on an internal macOS disk{detail}: {layout.cache_root}")
    if identity.internal is False:
        return

    volumes_root = Path("/Volumes")
    if mount is None or not _is_within(mount, volumes_root) or mount == volumes_root:
        if ci_override:
            return
        raise DriverError(
            "cannot prove that R46H_CARD_CACHE_ROOT is on a non-system macOS volume: "
            f"{layout.cache_root}"
        )


def _mkdir_private(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if _is_link_or_reparse(path) or not path.is_dir():
        raise DriverError(f"unsafe directory: {path}")
    try:
        path.chmod(0o700)
    except OSError as error:
        raise DriverError(f"cannot secure directory {path}: {error}") from error


def _cache_marker_payload(layout: Layout) -> Dict[str, object]:
    metadata = layout.cache_root.stat()
    return {
        "schema": CACHE_MARKER_SCHEMA,
        "cache_id": secrets.token_hex(16),
        "repo_root": str(layout.repo_root),
        "cache_root": str(layout.cache_root),
        "device": int(metadata.st_dev),
        "inode": int(metadata.st_ino),
    }


def _validate_cache_marker(layout: Layout) -> Dict[str, object]:
    marker = layout.marker_path
    if _is_link_or_reparse(marker) or not marker.is_file():
        raise DriverError(f"missing or unsafe cache ownership marker: {marker}")
    marker_metadata = marker.stat()
    cache_metadata = layout.cache_root.stat()
    if marker_metadata.st_nlink != 1:
        raise DriverError(f"cache ownership marker must have one link: {marker}")
    if hasattr(os, "geteuid"):
        effective_user = os.geteuid()
        if marker_metadata.st_uid != effective_user or cache_metadata.st_uid != effective_user:
            raise DriverError(f"cache root and marker must be owned by the current user: {marker}")
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DriverError(f"invalid cache ownership marker: {marker}") from error
    if not isinstance(payload, dict):
        raise DriverError(f"invalid cache ownership marker object: {marker}")

    expected = {
        "schema": CACHE_MARKER_SCHEMA,
        "repo_root": str(layout.repo_root),
        "cache_root": str(layout.cache_root),
        "device": int(cache_metadata.st_dev),
        "inode": int(cache_metadata.st_ino),
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise DriverError(f"cache ownership marker mismatch for {key}: {marker}")
    cache_id = payload.get("cache_id")
    if not isinstance(cache_id, str) or len(cache_id) != 32:
        raise DriverError(f"invalid cache ownership token: {marker}")
    try:
        bytes.fromhex(cache_id)
    except ValueError as error:
        raise DriverError(f"invalid cache ownership token: {marker}") from error
    return payload


def _prepare_cache_identity(layout: Layout) -> None:
    existed = layout.cache_root.exists()
    _mkdir_private(layout.cache_root)
    if layout.marker_path.exists() or _is_link_or_reparse(layout.marker_path):
        _validate_cache_marker(layout)
        return

    existing_names = {entry.name for entry in layout.cache_root.iterdir()}
    migratable = KNOWN_CACHE_CHILDREN | {"state"}
    is_default = layout.cache_root == (
        layout.out_root / ".cache" / "r46h-card-toolchain"
    ).resolve(strict=False)
    if existed and existing_names and (not is_default or not existing_names <= migratable):
        raise DriverError(
            "refusing to claim a nonempty cache root without an ownership marker: "
            f"{layout.cache_root}"
        )
    for name in existing_names:
        entry = layout.cache_root / name
        if _is_link_or_reparse(entry) or not entry.is_dir():
            raise DriverError(f"refusing unsafe legacy cache entry: {entry}")

    payload = _cache_marker_payload(layout)
    try:
        descriptor = os.open(
            layout.marker_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError:
        _validate_cache_marker(layout)
        return
    try:
        encoded = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
        written = 0
        while written < len(encoded):
            written += os.write(descriptor, encoded[written:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(layout.cache_root)
    _validate_cache_marker(layout)


def prepare_layout(layout: Layout) -> None:
    _prepare_cache_identity(layout)
    for path in (layout.cargo_home, layout.target_dir, layout.work_root, layout.state_root):
        _mkdir_private(path)
    _reject_symlink_components(layout.release_dir)
    layout.release_dir.mkdir(parents=True, exist_ok=True)
    if _is_link_or_reparse(layout.release_dir) or not layout.release_dir.is_dir():
        raise DriverError(f"unsafe release directory: {layout.release_dir}")


def _lock_file(file: TextIO, deadline: float) -> None:
    if os.name == "nt":
        import msvcrt  # pylint: disable=import-outside-toplevel

        file.seek(0)
        if file.read(1) == "":
            file.write("0")
            file.flush()
        while True:
            try:
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if time.monotonic() >= deadline:
                    raise DriverError("timed out waiting for the build/clean lock", EX_TEMPFAIL)
                time.sleep(0.1)
    else:
        import fcntl  # pylint: disable=import-outside-toplevel

        while True:
            try:
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise DriverError("timed out waiting for the build/clean lock", EX_TEMPFAIL)
                time.sleep(0.1)


def _unlock_file(file: TextIO) -> None:
    if os.name == "nt":
        import msvcrt  # pylint: disable=import-outside-toplevel

        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl  # pylint: disable=import-outside-toplevel

        fcntl.flock(file.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def operation_lock(layout: Layout, timeout_seconds: float) -> Iterator[None]:
    _mkdir_private(layout.state_root)
    deadline = time.monotonic() + timeout_seconds
    with layout.lock_path.open("a+", encoding="ascii") as lock_file:
        _lock_file(lock_file, deadline)
        try:
            # Detect replacement of the cache root or an ancestor between the
            # initial validation and lock acquisition.
            _validate_cache_marker(layout)
            yield
        finally:
            _unlock_file(lock_file)


def safe_remove_cache_child(layout: Layout, child_name: str) -> bool:
    _validate_cache_marker(layout)
    if child_name not in KNOWN_CACHE_CHILDREN:
        raise DriverError(f"refusing unknown cache child: {child_name}")
    target = layout.cache_root / child_name
    if target.parent.resolve(strict=False) != layout.cache_root:
        raise DriverError(f"cleanup escaped cache root: {target}")
    if not target.exists() and not _is_link_or_reparse(target):
        return False
    boundary = _mount_boundary(layout.cache_root, directory=True)
    if _is_link_or_reparse(target) or target.is_file():
        if not _is_link_or_reparse(target):
            _require_mount_boundary(
                target,
                boundary,
                directory=False,
                label="cache cleanup",
            )
        _unlink_link_or_reparse(target)
    elif target.is_dir():
        try:
            _remove_tree_on_device(target, boundary)
        except OSError as error:
            raise DriverError(
                "cache changed during cleanup; stop direct Cargo processes and retry: "
                f"{target}: {error}",
                EX_TEMPFAIL,
            ) from error
    else:
        raise DriverError(f"refusing unsupported cache entry: {target}")
    return True


def _remove_tree_on_device(root: Path, boundary: MountBoundary) -> None:
    """Remove one already-authorized tree without following links or mounts."""

    root_metadata = root.lstat()
    if _metadata_is_link_or_reparse(root_metadata):
        _unlink_link_or_reparse(root, root_metadata)
        return
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise DriverError(f"refusing cleanup of an unexpected entry: {root}")
    _require_mount_boundary(root, boundary, directory=True, label="cache cleanup")

    # A complete preflight ensures deletion never starts before every existing
    # descendant has proven to stay within the authorized mount.
    _validate_removable_cache_tree(root, boundary)
    if os.name != "nt":
        parent_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        parent_flags |= getattr(os, "O_DIRECTORY", 0)
        parent_flags |= getattr(os, "O_NOFOLLOW", 0)
        parent_descriptor = os.open(root.parent, parent_flags)
        try:
            _remove_tree_at(
                parent_descriptor,
                root.name,
                boundary,
                (root_metadata.st_dev, root_metadata.st_ino),
            )
        finally:
            os.close(parent_descriptor)
        return

    with os.scandir(root) as entries:
        for entry in entries:
            child = Path(entry.path)
            metadata = entry.stat(follow_symlinks=False)
            if _metadata_is_link_or_reparse(metadata):
                _unlink_link_or_reparse(child, metadata)
            elif stat.S_ISDIR(metadata.st_mode):
                _require_mount_boundary(
                    child,
                    boundary,
                    directory=True,
                    label="cache cleanup",
                )
                _remove_tree_on_device(child, boundary)
            elif stat.S_ISREG(metadata.st_mode):
                _require_mount_boundary(
                    child,
                    boundary,
                    directory=False,
                    label="cache cleanup",
                )
                child.unlink()
            else:
                raise DriverError(f"refusing unsupported cache entry: {child}")
    root.rmdir()


def _remove_tree_at(
    parent_descriptor: int,
    name: str,
    boundary: MountBoundary,
    expected_identity: Tuple[int, int],
) -> None:
    """Delete a POSIX directory relative to one pinned parent descriptor."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_descriptor)
    except OSError as error:
        raise DriverError(f"cache tree changed before deletion: {name}", EX_TEMPFAIL) from error
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or (metadata.st_dev, metadata.st_ino) != expected_identity
            or _descriptor_mount_boundary(descriptor) != boundary
        ):
            raise DriverError(f"cache cleanup crosses a mount boundary: {name}")
        with os.scandir(descriptor) as entries:
            children = sorted((entry.name for entry in entries), key=os.fsencode)
        for child_name in children:
            child_metadata = os.stat(
                child_name,
                dir_fd=descriptor,
                follow_symlinks=False,
            )
            if _metadata_is_link_or_reparse(child_metadata):
                os.unlink(child_name, dir_fd=descriptor)
            elif stat.S_ISDIR(child_metadata.st_mode):
                _remove_tree_at(
                    descriptor,
                    child_name,
                    boundary,
                    (child_metadata.st_dev, child_metadata.st_ino),
                )
            elif stat.S_ISREG(child_metadata.st_mode):
                file_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
                file_flags |= getattr(os, "O_NOFOLLOW", 0)
                file_descriptor = os.open(child_name, file_flags, dir_fd=descriptor)
                try:
                    opened = os.fstat(file_descriptor)
                    if (
                        not stat.S_ISREG(opened.st_mode)
                        or _descriptor_mount_boundary(file_descriptor) != boundary
                    ):
                        raise DriverError(
                            f"cache cleanup crosses a mount boundary: {child_name}"
                        )
                    if (opened.st_dev, opened.st_ino) != (
                        child_metadata.st_dev,
                        child_metadata.st_ino,
                    ):
                        raise DriverError(
                            f"cache entry changed before deletion: {child_name}",
                            EX_TEMPFAIL,
                        )
                finally:
                    os.close(file_descriptor)
                os.unlink(child_name, dir_fd=descriptor)
            else:
                raise DriverError(f"refusing unsupported cache entry: {child_name}")
    finally:
        os.close(descriptor)
    os.rmdir(name, dir_fd=parent_descriptor)


@contextlib.contextmanager
def private_work_dir(layout: Layout, action: str) -> Iterator[Path]:
    _mkdir_private(layout.work_root)
    work = Path(tempfile.mkdtemp(prefix=f"{action}-{os.getpid()}-", dir=layout.work_root))
    work.chmod(0o700)
    try:
        yield work
    finally:
        if work.parent == layout.work_root and work.exists() and not _is_link_or_reparse(work):
            _remove_tree_on_device(
                work,
                _mount_boundary(layout.cache_root, directory=True),
            )


def _find_executable(name: str, toolchain_bin: Optional[Path]) -> Path:
    if toolchain_bin is not None:
        candidate = toolchain_bin / (f"{name}.exe" if os.name == "nt" else name)
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.absolute()
        raise DriverError(f"missing {name} in R46H_RUST_TOOLCHAIN_BIN: {candidate}", EX_UNAVAILABLE)
    found = shutil.which(name)
    if not found:
        raise DriverError(f"required Rust command is unavailable: {name}", EX_UNAVAILABLE)
    # Keep a rustup proxy path intact. Resolving its symlink to the rustup
    # executable would change argv[0] and stop it dispatching as cargo/rustc.
    return Path(found).absolute()


def resolve_rust_commands() -> Dict[str, Path]:
    raw_bin = os.environ.get("R46H_RUST_TOOLCHAIN_BIN")
    toolchain_bin = _resolve_absolute(raw_bin, "R46H_RUST_TOOLCHAIN_BIN") if raw_bin else None
    return {
        "cargo": _find_executable("cargo", toolchain_bin),
        "rustc": _find_executable("rustc", toolchain_bin),
    }


def build_environment(
    layout: Layout,
    work: Path,
    rustc: Optional[Path] = None,
    target_dir: Optional[Path] = None,
    cargo_home: Optional[Path] = None,
) -> Dict[str, str]:
    """Return the narrow deterministic environment used by strict builds."""

    for name in ("config", "config.toml"):
        cargo_config = layout.cargo_home / name
        if cargo_config.exists() or _is_link_or_reparse(cargo_config):
            raise DriverError(f"Cargo config in the shared home is not allowed: {cargo_config}")

    blocked_prefixes = (
        "CARGO_",
        "RUST",
        "RUSTDOC",
        "GIT_",
        "DYLD_",
        "LD_",
    )
    blocked_names = {
        "AR",
        "CC",
        "CFLAGS",
        "CPPFLAGS",
        "CXX",
        "CXXFLAGS",
        "LDFLAGS",
        "MAKEFLAGS",
        "SOURCE_DATE_EPOCH",
    }
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in blocked_names
        and not any(key.startswith(prefix) for prefix in blocked_prefixes)
    }
    environment.update(
        {
            "CARGO_HOME": str(cargo_home or layout.cargo_home),
            "CARGO_TARGET_DIR": str(target_dir or layout.target_dir),
            "CARGO_INCREMENTAL": "0",
            "CARGO_NET_OFFLINE": "true",
            "TMPDIR": str(work),
            "TMP": str(work),
            "TEMP": str(work),
            "RUSTUP_AUTO_INSTALL": "0",
            "R46H_CARD_CACHE_ROOT": str(layout.cache_root),
        }
    )
    if rustc is not None:
        environment["RUSTC"] = str(rustc)
    return environment


def _validate_download_cache_tree(root: Path, boundary: MountBoundary) -> None:
    try:
        root_metadata = root.stat(follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        _metadata_is_link_or_reparse(root_metadata)
        or not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_dev != boundary.device
    ):
        raise DriverError(f"unsafe Cargo download cache: {root}")
    _require_mount_boundary(root, boundary, directory=True, label="Cargo download cache")
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in [*directory_names, *file_names]:
            path = parent / name
            metadata = path.stat(follow_symlinks=False)
            if _metadata_is_link_or_reparse(metadata):
                raise DriverError(f"Cargo download cache contains a link: {path}")
            if stat.S_ISDIR(metadata.st_mode):
                _require_mount_boundary(
                    path,
                    boundary,
                    directory=True,
                    label="Cargo download cache",
                )
            elif stat.S_ISREG(metadata.st_mode):
                _require_mount_boundary(
                    path,
                    boundary,
                    directory=False,
                    label="Cargo download cache",
                )
            else:
                raise DriverError(f"Cargo download cache contains a special entry: {path}")


def _validate_removable_cache_tree(root: Path, boundary: MountBoundary) -> None:
    """Preflight a disposable tree without following links or mutating it."""

    metadata = root.stat(follow_symlinks=False)
    if _metadata_is_link_or_reparse(metadata):
        return
    if stat.S_ISREG(metadata.st_mode):
        _require_mount_boundary(
            root,
            boundary,
            directory=False,
            label="Cargo cache residue",
        )
        return
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_dev != boundary.device:
        raise DriverError(f"unsafe removable Cargo cache entry: {root}")
    _require_mount_boundary(root, boundary, directory=True, label="Cargo cache residue")
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in [*directory_names, *file_names]:
            path = parent / name
            child_metadata = path.stat(follow_symlinks=False)
            if _metadata_is_link_or_reparse(child_metadata):
                continue
            if stat.S_ISDIR(child_metadata.st_mode):
                _require_mount_boundary(
                    path,
                    boundary,
                    directory=True,
                    label="Cargo cache residue",
                )
            elif stat.S_ISREG(child_metadata.st_mode):
                _require_mount_boundary(
                    path,
                    boundary,
                    directory=False,
                    label="Cargo cache residue",
                )
            else:
                raise DriverError(f"Cargo cache residue contains a special entry: {path}")


def _copy_download_cache_tree(
    source: Path,
    destination: Path,
    boundary: MountBoundary,
) -> None:
    """Copy an already-scoped cache tree through no-follow source handles."""

    if os.name == "nt":
        _validate_download_cache_tree(source, boundary)
        shutil.copytree(source, destination, symlinks=False)
        _validate_download_cache_tree(source, boundary)
        return

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(source, flags)
    try:
        if _descriptor_mount_boundary(descriptor) != boundary:
            raise DriverError(f"Cargo download cache crosses a mount boundary: {source}")
        destination.mkdir(mode=0o700)
        _copy_download_cache_from_fd(descriptor, destination, boundary)
    finally:
        os.close(descriptor)


def _copy_download_cache_from_fd(
    source_descriptor: int,
    destination: Path,
    boundary: MountBoundary,
) -> None:
    before = os.fstat(source_descriptor)
    if (
        not stat.S_ISDIR(before.st_mode)
        or _descriptor_mount_boundary(source_descriptor) != boundary
    ):
        raise DriverError("Cargo download cache directory changed during copy")
    with os.scandir(source_descriptor) as entries:
        names = sorted((entry.name for entry in entries), key=os.fsencode)
    seen_casefold: set[str] = set()
    for name in names:
        if name in {"", ".", ".."} or "/" in name or "\0" in name:
            raise DriverError("Cargo download cache contains an unsafe name")
        if name.casefold() in seen_casefold:
            raise DriverError("Cargo download cache contains a case-colliding name")
        seen_casefold.add(name.casefold())
        metadata = os.stat(name, dir_fd=source_descriptor, follow_symlinks=False)
        if _metadata_is_link_or_reparse(metadata):
            raise DriverError(f"Cargo download cache contains a link: {name}")
        if stat.S_ISDIR(metadata.st_mode):
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_DIRECTORY", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            child_descriptor = os.open(name, flags, dir_fd=source_descriptor)
            try:
                opened = os.fstat(child_descriptor)
                if (
                    (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
                    or _descriptor_mount_boundary(child_descriptor) != boundary
                ):
                    raise DriverError(f"Cargo download cache directory changed: {name}")
                child_destination = destination / name
                child_destination.mkdir(mode=0o700)
                _copy_download_cache_from_fd(
                    child_descriptor,
                    child_destination,
                    boundary,
                )
            finally:
                os.close(child_descriptor)
        elif stat.S_ISREG(metadata.st_mode):
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            source_file = os.open(name, flags, dir_fd=source_descriptor)
            try:
                opened = os.fstat(source_file)
                if (
                    (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
                    or _descriptor_mount_boundary(source_file) != boundary
                ):
                    raise DriverError(f"Cargo download cache file changed: {name}")
                destination_file = os.open(
                    destination / name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                try:
                    while chunk := os.read(source_file, 1024 * 1024):
                        written = 0
                        while written < len(chunk):
                            count = os.write(destination_file, chunk[written:])
                            if count <= 0:
                                raise DriverError("short write while copying Cargo cache")
                            written += count
                    os.fsync(destination_file)
                finally:
                    os.close(destination_file)
                after = os.fstat(source_file)
                if (
                    opened.st_size,
                    opened.st_mtime_ns,
                    opened.st_ctime_ns,
                ) != (
                    after.st_size,
                    after.st_mtime_ns,
                    after.st_ctime_ns,
                ):
                    raise DriverError(f"Cargo download cache file changed during copy: {name}")
            finally:
                os.close(source_file)
        else:
            raise DriverError(f"Cargo download cache contains a special entry: {name}")
    after = os.fstat(source_descriptor)
    if (
        before.st_dev,
        before.st_ino,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise DriverError("Cargo download cache directory changed during copy")
    _fsync_directory(destination)


def prepare_private_cargo_home(layout: Layout, work: Path) -> Path:
    private_home = work / "cargo-home"
    private_home.mkdir(mode=0o700)
    boundary = _mount_boundary(layout.cache_root, directory=True)
    relative_roots = (
        Path("registry") / "cache",
        Path("registry") / "index",
    )
    for relative in relative_roots:
        source = layout.cargo_home / relative
        if not source.exists():
            continue
        _validate_download_cache_tree(source, boundary)
        destination = private_home / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        _copy_download_cache_tree(source, destination, boundary)
    return private_home


def prune_shared_cargo_home(layout: Layout) -> None:
    """Retain only Cargo registry archives/index metadata in the shared cache."""

    _validate_cache_marker(layout)
    cargo_home = layout.cargo_home
    boundary = _mount_boundary(layout.cache_root, directory=True)
    device = boundary.device
    cargo_home_metadata = cargo_home.stat(follow_symlinks=False)
    if (
        _metadata_is_link_or_reparse(cargo_home_metadata)
        or not stat.S_ISDIR(cargo_home_metadata.st_mode)
        or cargo_home_metadata.st_dev != device
    ):
        raise DriverError(f"unsafe shared Cargo home: {cargo_home}")
    removals: List[Path] = []
    for entry in list(cargo_home.iterdir()):
        folded_name = entry.name.casefold()
        if folded_name in {"config", "config.toml"}:
            raise DriverError(f"Cargo config in the shared home is not allowed: {entry}")
        if folded_name == "registry" and entry.name != "registry":
            raise DriverError(f"noncanonical shared Cargo registry name: {entry}")
        if entry.name != "registry":
            _validate_removable_cache_tree(entry, boundary)
            removals.append(entry)
            continue
        registry_metadata = entry.stat(follow_symlinks=False)
        if (
            _metadata_is_link_or_reparse(registry_metadata)
            or not stat.S_ISDIR(registry_metadata.st_mode)
            or registry_metadata.st_dev != device
        ):
            raise DriverError(f"unsafe shared Cargo registry: {entry}")
        retained_names = {
            "cache": "cache",
            "index": "index",
            "cachedir.tag": "CACHEDIR.TAG",
        }
        for registry_entry in list(entry.iterdir()):
            canonical_name = retained_names.get(registry_entry.name.casefold())
            if canonical_name is not None and registry_entry.name != canonical_name:
                raise DriverError(f"noncanonical retained Cargo cache name: {registry_entry}")
            if registry_entry.name in {"cache", "index", "CACHEDIR.TAG"}:
                metadata = registry_entry.stat(follow_symlinks=False)
                expected_type = (
                    stat.S_ISREG(metadata.st_mode)
                    if registry_entry.name == "CACHEDIR.TAG"
                    else stat.S_ISDIR(metadata.st_mode)
                )
                if (
                    _metadata_is_link_or_reparse(metadata)
                    or not expected_type
                    or metadata.st_dev != device
                ):
                    raise DriverError(f"unsafe retained Cargo cache entry: {registry_entry}")
                if registry_entry.name != "CACHEDIR.TAG":
                    _validate_download_cache_tree(registry_entry, boundary)
                continue
            _validate_removable_cache_tree(registry_entry, boundary)
            removals.append(registry_entry)

    # Mutate only after the complete shared tree has passed validation. Paths
    # are fixed from the preflight snapshot, so a newly appearing Cargo config
    # is never swept up as generic state.
    for removal in removals:
        metadata = removal.stat(follow_symlinks=False)
        if _metadata_is_link_or_reparse(metadata) or stat.S_ISREG(metadata.st_mode):
            _unlink_link_or_reparse(removal, metadata)
        elif stat.S_ISDIR(metadata.st_mode):
            _remove_tree_on_device(removal, boundary)
        else:
            raise DriverError(f"Cargo cache changed after preflight: {removal}")


def _run(command: Sequence[str], environment: Mapping[str, str], cwd: Path) -> None:
    subprocess.run(list(command), cwd=cwd, env=dict(environment), check=True)


def _run_output(
    command: Sequence[str], environment: Mapping[str, str], cwd: Path
) -> str:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        env=dict(environment),
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.rstrip("\n")


def _sha256_file(path: Path) -> str:
    state = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1024 * 1024):
            state.update(chunk)
    return state.hexdigest()


def _canonical_json(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _write_new_file(path: Path, payload: bytes, mode: int) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        written = 0
        while written < len(payload):
            count = os.write(descriptor, payload[written:])
            if count <= 0:
                raise DriverError(f"short write while creating {path}")
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _git_environment() -> Dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") and key not in {"CDPATH", "GLOBIGNORE"}
    }
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "NUL" if os.name == "nt" else "/dev/null",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "LC_ALL": "C",
        }
    )
    return environment


def _git_result(layout: Layout, arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(layout.repo_root), *arguments],
        env=_git_environment(),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _git_output(layout: Layout, arguments: Sequence[str]) -> str:
    result = _git_result(layout, arguments)
    if result.returncode != 0:
        detail = result.stderr.strip() or "git command failed"
        raise DriverError(detail)
    return result.stdout.rstrip("\n")


def _git_bytes(layout: Layout, arguments: Sequence[str]) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(layout.repo_root), *arguments],
        env=_git_environment(),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip() or "git command failed"
        raise DriverError(detail)
    return result.stdout


def require_clean_source_scope(layout: Layout) -> Tuple[str, str]:
    """Pin a clean tracked source scope while ignoring unrelated old evidence."""

    commit = _git_output(layout, ["rev-parse", "--verify", "HEAD^{commit}"])
    tree = _git_output(layout, ["rev-parse", "--verify", f"{commit}^{{tree}}"])
    for value, label in ((commit, "commit"), (tree, "tree")):
        if not re.fullmatch(r"[0-9a-f]{40,64}", value):
            raise DriverError(f"invalid Git {label} identity: {value}")

    for arguments, label in (
        (["diff", "--quiet", "--", *BUILD_SOURCE_PATHS], "unstaged"),
        (["diff", "--cached", "--quiet", "--", *BUILD_SOURCE_PATHS], "staged"),
    ):
        result = _git_result(layout, arguments)
        if result.returncode == 1:
            raise DriverError(f"build source scope has {label} changes")
        if result.returncode != 0:
            raise DriverError(result.stderr.strip() or f"cannot inspect {label} changes")

    untracked = _git_output(
        layout,
        ["ls-files", "--others", "--exclude-standard", "--", *BUILD_SOURCE_PATHS],
    )
    if untracked:
        raise DriverError(f"build source scope has untracked files: {untracked.splitlines()[0]}")

    driver_relative = "mainline/scripts/r46h_card_toolchain.py"
    head_driver = _git_bytes(layout, ["show", f"{commit}:{driver_relative}"])
    live_driver = (layout.repo_root / driver_relative).read_bytes()
    if hashlib.sha256(head_driver).digest() != hashlib.sha256(live_driver).digest():
        raise DriverError("running build driver does not match the captured commit")
    return commit, tree


def _safe_archive_member(name: str) -> PurePosixPath:
    if not name or name.startswith("/") or "\\" in name:
        raise DriverError(f"unsafe source archive path: {name}")
    path = PurePosixPath(name.rstrip("/"))
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise DriverError(f"unsafe source archive path: {name}")
    return path


def _snapshot_file_mode(archive_mode: int, platform_name: Optional[str] = None) -> int:
    """Return a private snapshot mode without creating Windows read-only files."""

    executable = bool(archive_mode & 0o111)
    if (platform_name or os.name) == "nt":
        return 0o755 if executable else 0o644
    return 0o555 if executable else 0o444


def capture_source_snapshot(
    layout: Layout, work: Path, commit: str, tree: str
) -> SourceSnapshot:
    """Create and validate a private source snapshot from the captured commit."""

    import tarfile  # pylint: disable=import-outside-toplevel

    archive = work / "source.tar"
    with archive.open("xb") as output:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(layout.repo_root),
                "archive",
                "--format=tar",
                commit,
                "--",
                *BUILD_SOURCE_PATHS,
            ],
            env=_git_environment(),
            check=False,
            stdout=output,
            stderr=subprocess.PIPE,
        )
        output.flush()
        os.fsync(output.fileno())
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise DriverError(detail or "cannot create source archive")

    snapshot_root = work / "source"
    snapshot_root.mkdir(mode=0o700)
    seen_paths: set[str] = set()
    seen_casefold: set[str] = set()
    total_size = 0
    with tarfile.open(archive, mode="r:") as source:
        members = source.getmembers()
        for member in members:
            relative = _safe_archive_member(member.name)
            relative_text = relative.as_posix()
            folded = relative_text.casefold()
            if relative_text in seen_paths or folded in seen_casefold:
                raise DriverError(f"duplicate or case-colliding source path: {relative_text}")
            seen_paths.add(relative_text)
            seen_casefold.add(folded)
            destination = snapshot_root.joinpath(*relative.parts)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=False)
                continue
            if not member.isfile():
                raise DriverError(f"source snapshot contains a non-regular entry: {relative_text}")
            total_size += member.size
            if member.size > 128 * 1024 * 1024 or total_size > 512 * 1024 * 1024:
                raise DriverError("source snapshot exceeds the fixed size limit")
            destination.parent.mkdir(parents=True, exist_ok=True)
            extracted = source.extractfile(member)
            if extracted is None:
                raise DriverError(f"cannot read source archive member: {relative_text}")
            descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            try:
                while chunk := extracted.read(1024 * 1024):
                    view = memoryview(chunk)
                    while view:
                        count = os.write(descriptor, view)
                        if count <= 0:
                            raise DriverError(f"short source extraction write: {relative_text}")
                        view = view[count:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            # Windows chmod maps missing write bits to FILE_ATTRIBUTE_READONLY,
            # which would make the private snapshot impossible to remove.
            destination.chmod(_snapshot_file_mode(member.mode))

    records: List[Dict[str, object]] = []
    for path in sorted(snapshot_root.rglob("*"), key=lambda item: item.as_posix().encode("utf-8")):
        if path.is_dir() and not _is_link_or_reparse(path):
            continue
        if _is_link_or_reparse(path) or not path.is_file():
            raise DriverError(f"unsafe extracted source entry: {path}")
        relative = path.relative_to(snapshot_root).as_posix()
        records.append(
            {
                "path": relative,
                "size": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    if not records:
        raise DriverError("captured source snapshot is empty")
    manifest_path = work / "SOURCE-MANIFEST.json"
    manifest = {
        "schema": SOURCE_MANIFEST_SCHEMA,
        "git_commit": commit,
        "git_tree": tree,
        "scope": list(BUILD_SOURCE_PATHS),
        "files": records,
    }
    _write_new_file(manifest_path, _canonical_json(manifest), 0o600)
    driver_path = snapshot_root / "mainline" / "scripts" / "r46h_card_toolchain.py"
    cargo_lock = snapshot_root / "mainline" / "tools" / "r46h-card-toolchain" / "Cargo.lock"
    archive.unlink()
    return SourceSnapshot(
        root=snapshot_root,
        commit=commit,
        tree=tree,
        manifest_path=manifest_path,
        manifest_sha256=_sha256_file(manifest_path),
        file_count=len(records),
        driver_sha256=_sha256_file(driver_path),
        cargo_lock_sha256=_sha256_file(cargo_lock),
    )


def validate_source_snapshot(source: SourceSnapshot) -> None:
    try:
        manifest = json.loads(source.manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DriverError("cannot re-read the source snapshot manifest") from error
    if manifest.get("schema") != SOURCE_MANIFEST_SCHEMA:
        raise DriverError("source snapshot manifest schema mismatch")
    records = manifest.get("files")
    if not isinstance(records, list):
        raise DriverError("source snapshot manifest file list is invalid")
    expected: Dict[str, Tuple[int, str]] = {}
    for record in records:
        if not isinstance(record, dict):
            raise DriverError("source snapshot manifest record is invalid")
        path = record.get("path")
        size = record.get("size")
        digest = record.get("sha256")
        if (
            not isinstance(path, str)
            or not isinstance(size, int)
            or not isinstance(digest, str)
            or path in expected
        ):
            raise DriverError("source snapshot manifest record is malformed")
        expected[path] = (size, digest)
    actual: Dict[str, Tuple[int, str]] = {}
    for path in source.root.rglob("*"):
        if path.is_dir() and not _is_link_or_reparse(path):
            continue
        if _is_link_or_reparse(path) or not path.is_file():
            raise DriverError(f"source snapshot gained an unsafe entry: {path}")
        relative = path.relative_to(source.root).as_posix()
        actual[relative] = (path.stat().st_size, _sha256_file(path))
    if actual != expected:
        raise DriverError("source snapshot changed during build gates")


def _fsync_file(path: Path) -> None:
    with path.open("rb") as file:
        os.fsync(file.fileno())


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _copy_regular_file(source: Path, destination: Path, mode: int) -> Tuple[str, int]:
    before = source.stat(follow_symlinks=False)
    if _metadata_is_link_or_reparse(before) or not stat.S_ISREG(before.st_mode):
        raise DriverError(f"release input is not a regular file: {source}")
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    source_fd = os.open(source, os.O_RDONLY | nofollow)
    destination_fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    digest = hashlib.sha256()
    size = 0
    try:
        opened = os.fstat(source_fd)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            before.st_dev,
            before.st_ino,
            before.st_size,
        ):
            raise DriverError(f"release input changed before copy: {source}")
        while chunk := os.read(source_fd, 1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
            view = memoryview(chunk)
            while view:
                count = os.write(destination_fd, view)
                if count <= 0:
                    raise DriverError(f"short release copy write: {destination}")
                view = view[count:]
        if size != opened.st_size:
            raise DriverError(f"release input changed during copy: {source}")
        os.fsync(destination_fd)
    finally:
        os.close(source_fd)
        os.close(destination_fd)
    return digest.hexdigest(), size


def _directory_durability_claim() -> str:
    return "uncertified" if os.name == "nt" else "fsync-directory"


def _publication_receipt(
    layout: Layout,
    source: SourceSnapshot,
    executable_name: str,
    executable_sha256: str,
    executable_size: int,
    commands: Mapping[str, Path],
    environment: Mapping[str, str],
    gates: Sequence[Mapping[str, object]],
    storage_policy: str,
) -> Dict[str, object]:
    rustc_version = _run_output(
        [str(commands["rustc"]), "--version", "--verbose"],
        environment,
        layout.repo_root,
    )
    cargo_version = _run_output(
        [str(commands["cargo"]), "--version", "--verbose"],
        environment,
        layout.repo_root,
    )
    return {
        "schema": BUILD_RECEIPT_SCHEMA,
        "status": "complete",
        "claim_scope": "first-party-source-and-output-integrity",
        "hermetic": False,
        "source": {
            "git_commit": source.commit,
            "git_tree": source.tree,
            "scope": list(BUILD_SOURCE_PATHS),
            "scope_clean_observed": True,
            "file_count": source.file_count,
            "driver_sha256": source.driver_sha256,
            "cargo_lock_sha256": source.cargo_lock_sha256,
            "snapshot_manifest_sha256": source.manifest_sha256,
        },
        "dependencies": {
            "mode": "cargo-lock-and-cargo-checksums",
            "network_during_gates": "offline",
            "shared_download_cache": "archives-and-index-only",
        },
        "toolchain": {
            "cargo_version_verbose": cargo_version,
            "rustc_version_verbose": rustc_version,
            "python_version": sys.version.splitlines()[0],
            "host": _host_tag(),
            "linker": "system-not-pinned",
        },
        "environment": {
            "profile": BUILD_ENVIRONMENT_SCHEMA,
            "cargo_incremental": False,
            "network_during_gates": "offline",
        },
        "storage": {
            "cache_device": int(layout.cache_root.stat().st_dev),
            "release_device": int(layout.release_dir.stat().st_dev),
            "same_filesystem": layout.cache_root.stat().st_dev
            == layout.release_dir.stat().st_dev,
            "non_system_policy": storage_policy,
        },
        "gates": list(gates),
        "artifact": {
            "path": executable_name,
            "size": executable_size,
            "sha256": executable_sha256,
        },
        "publication": {
            "strategy": "immutable-generation-plus-current/v1",
            "logical_atomicity": True,
            "directory_durability": _directory_durability_claim(),
        },
        "cleanup": {
            "source_snapshot_removed_before_publication": True,
            "private_target_removed_before_publication": True,
            "private_work_policy": "removed-before-success-return",
            "shared_download_cache_retained": "archives-and-index-only",
        },
        "limitations": [
            "no publisher signature",
            "floating installed Rust stable toolchain",
            "system linker not pinned",
            "same-user hostile path replacement not certified",
        ],
    }


def _require_release_directory(
    path: Path,
    label: str,
    expected_device: Optional[int] = None,
) -> os.stat_result:
    try:
        metadata = path.stat(follow_symlinks=False)
    except OSError as error:
        raise DriverError(f"missing or unsafe {label}: {path}") from error
    if _metadata_is_link_or_reparse(metadata) or not stat.S_ISDIR(metadata.st_mode):
        raise DriverError(f"missing or unsafe {label}: {path}")
    if expected_device is not None and metadata.st_dev != expected_device:
        raise DriverError(f"{label} crosses the release filesystem: {path}")
    return metadata


def _require_release_ancestry(layout: Layout) -> os.stat_result:
    """Require every repository-owned release directory to be real and co-located."""

    _reject_symlink_components(layout.release_dir, "release path")
    release_device: Optional[int] = None
    directories = (
        (layout.out_root, "release root"),
        (layout.out_root / "r46h-card-toolchain", "release toolchain directory"),
        (layout.release_dir.parent, "release binary directory"),
        (layout.release_dir, "release directory"),
    )
    metadata: Optional[os.stat_result] = None
    for directory, label in directories:
        metadata = _require_release_directory(directory, label, release_device)
        if release_device is None:
            release_device = metadata.st_dev
    if metadata is None:
        raise DriverError("release ancestry is empty")
    return metadata


def _lower_hex(value: object, lengths: Sequence[int]) -> bool:
    return isinstance(value, str) and len(value) in lengths and bool(
        re.fullmatch(r"[0-9a-f]+", value)
    )


def _validate_source_manifest(path: Path) -> Dict[str, object]:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DriverError("invalid release source manifest") from error
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema",
        "git_commit",
        "git_tree",
        "scope",
        "files",
    }:
        raise DriverError("release source manifest key set mismatch")
    if manifest.get("schema") != SOURCE_MANIFEST_SCHEMA:
        raise DriverError("release source manifest schema mismatch")
    if not _lower_hex(manifest.get("git_commit"), (40, 64)) or not _lower_hex(
        manifest.get("git_tree"), (40, 64)
    ):
        raise DriverError("release source manifest Git identity mismatch")
    if manifest.get("scope") != list(BUILD_SOURCE_PATHS):
        raise DriverError("release source manifest scope mismatch")
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise DriverError("release source manifest file list mismatch")
    seen: set[str] = set()
    seen_casefold: set[str] = set()
    ordered_paths: List[str] = []
    for record in files:
        if not isinstance(record, dict) or set(record) != {"path", "size", "sha256"}:
            raise DriverError("release source manifest record mismatch")
        relative = record.get("path")
        size = record.get("size")
        digest = record.get("sha256")
        if not isinstance(relative, str):
            raise DriverError("release source manifest path mismatch")
        parsed = PurePosixPath(relative)
        if (
            parsed.is_absolute()
            or relative != parsed.as_posix()
            or "\\" in relative
            or any(part in {"", ".", ".."} for part in parsed.parts)
        ):
            raise DriverError("release source manifest path mismatch")
        if relative in seen or relative.casefold() in seen_casefold:
            raise DriverError("release source manifest duplicate path")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise DriverError("release source manifest size mismatch")
        if not _lower_hex(digest, (64,)):
            raise DriverError("release source manifest digest mismatch")
        seen.add(relative)
        seen_casefold.add(relative.casefold())
        ordered_paths.append(relative)
    if ordered_paths != sorted(ordered_paths, key=lambda item: item.encode("utf-8")):
        raise DriverError("release source manifest order mismatch")
    return manifest


def _validate_manifest_against_current_git(
    layout: Layout, manifest: Mapping[str, object]
) -> None:
    """Bind every manifest record to the current clean HEAD and its raw blobs."""

    commit, tree = require_clean_source_scope(layout)
    if manifest.get("git_commit") != commit or manifest.get("git_tree") != tree:
        raise DriverError("release source does not match the current clean HEAD")

    raw_tree = _git_bytes(
        layout,
        [
            "ls-tree",
            "-r",
            "-z",
            "--full-tree",
            commit,
            "--",
            *BUILD_SOURCE_PATHS,
        ],
    )
    git_records: Dict[str, Tuple[int, str]] = {}
    seen_casefold: set[str] = set()
    for raw_record in raw_tree.split(b"\0"):
        if not raw_record:
            continue
        try:
            header, raw_path = raw_record.split(b"\t", 1)
            mode, kind, object_id = header.decode("ascii").split(" ")
            relative = raw_path.decode("utf-8")
        except (UnicodeError, ValueError) as error:
            raise DriverError("invalid Git source tree record") from error
        parsed = PurePosixPath(relative)
        if (
            mode not in {"100644", "100755"}
            or kind != "blob"
            or not re.fullmatch(r"[0-9a-f]{40,64}", object_id)
            or parsed.is_absolute()
            or relative != parsed.as_posix()
            or "\\" in relative
            or any(part in {"", ".", ".."} for part in parsed.parts)
            or relative in git_records
            or relative.casefold() in seen_casefold
        ):
            raise DriverError(f"unsafe or duplicate Git source tree record: {relative}")
        blob = _git_bytes(layout, ["cat-file", "blob", object_id])
        git_records[relative] = (len(blob), hashlib.sha256(blob).hexdigest())
        seen_casefold.add(relative.casefold())

    manifest_records = {
        record["path"]: (record["size"], record["sha256"])
        for record in manifest["files"]  # type: ignore[index]
        if isinstance(record, dict)
    }
    if manifest_records != git_records:
        raise DriverError("release source records do not match the current Git tree")


def _validate_generation_directory(
    layout: Layout,
    generation: Path,
    executable_name: str,
    expected_device: Optional[int] = None,
) -> str:
    generation_metadata = _require_release_directory(
        generation,
        "release generation",
        expected_device,
    )
    generation_device = generation_metadata.st_dev
    expected = {"BUILD-RECEIPT.json", "SHA256SUMS", "SOURCE-MANIFEST.json", executable_name}
    actual = {entry.name for entry in generation.iterdir()}
    if actual != expected:
        raise DriverError(f"release generation file set mismatch: {generation}")
    for name in expected:
        path = generation / name
        metadata = path.stat(follow_symlinks=False)
        if (
            _metadata_is_link_or_reparse(metadata)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_dev != generation_device
            or metadata.st_nlink != 1
        ):
            raise DriverError(f"unsafe release generation member: {path}")
    sums = (generation / "SHA256SUMS").read_text(encoding="ascii").splitlines()
    expected_names = sorted(expected - {"SHA256SUMS"}, key=lambda item: item.encode("utf-8"))
    if len(sums) != len(expected_names):
        raise DriverError("release checksum member count mismatch")
    for line, name in zip(sums, expected_names):
        expected_line = f"{_sha256_file(generation / name)}  {name}"
        if line != expected_line:
            raise DriverError(f"release checksum mismatch: {name}")
    try:
        receipt = json.loads(
            (generation / "BUILD-RECEIPT.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DriverError("invalid release build receipt") from error
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema") != BUILD_RECEIPT_SCHEMA
        or receipt.get("status") != "complete"
        or receipt.get("claim_scope") != "first-party-source-and-output-integrity"
        or receipt.get("hermetic") is not False
    ):
        raise DriverError("invalid release build receipt")
    artifact = receipt.get("artifact")
    binary = generation / executable_name
    if (
        not isinstance(artifact, dict)
        or set(artifact) != {"path", "sha256", "size"}
        or artifact.get("path") != executable_name
        or not _lower_hex(artifact.get("sha256"), (64,))
        or not isinstance(artifact.get("size"), int)
        or isinstance(artifact.get("size"), bool)
        or artifact.get("size") != binary.stat().st_size
    ):
        raise DriverError("release receipt artifact mismatch")
    if artifact.get("sha256") != _sha256_file(binary):
        raise DriverError("release receipt binary digest mismatch")

    manifest_path = generation / "SOURCE-MANIFEST.json"
    manifest = _validate_source_manifest(manifest_path)
    source = receipt.get("source")
    expected_source_keys = {
        "cargo_lock_sha256",
        "driver_sha256",
        "file_count",
        "git_commit",
        "git_tree",
        "scope",
        "scope_clean_observed",
        "snapshot_manifest_sha256",
    }
    if not isinstance(source, dict) or set(source) != expected_source_keys:
        raise DriverError("release receipt source key set mismatch")
    if (
        not _lower_hex(source.get("git_commit"), (40, 64))
        or not _lower_hex(source.get("git_tree"), (40, 64))
        or not _lower_hex(source.get("snapshot_manifest_sha256"), (64,))
        or not _lower_hex(source.get("driver_sha256"), (64,))
        or not _lower_hex(source.get("cargo_lock_sha256"), (64,))
        or not isinstance(source.get("file_count"), int)
        or isinstance(source.get("file_count"), bool)
        or not isinstance(source.get("scope"), list)
        or source.get("git_commit") != manifest.get("git_commit")
        or source.get("git_tree") != manifest.get("git_tree")
        or source.get("scope") != manifest.get("scope")
        or source.get("scope_clean_observed") is not True
        or source.get("file_count") != len(manifest["files"])
        or source.get("snapshot_manifest_sha256") != _sha256_file(manifest_path)
    ):
        raise DriverError("release receipt source identity mismatch")
    records = {
        record["path"]: record
        for record in manifest["files"]
        if isinstance(record, dict) and isinstance(record.get("path"), str)
    }
    driver_record = records.get("mainline/scripts/r46h_card_toolchain.py")
    lock_record = records.get("mainline/tools/r46h-card-toolchain/Cargo.lock")
    if (
        driver_record is None
        or lock_record is None
        or source.get("driver_sha256") != driver_record.get("sha256")
        or source.get("cargo_lock_sha256") != lock_record.get("sha256")
    ):
        raise DriverError("release receipt source digest mismatch")
    _validate_manifest_against_current_git(layout, manifest)
    commit = source["git_commit"]
    artifact_digest = artifact["sha256"]
    if not generation.name.startswith(f"build-{commit[:12]}-{artifact_digest[:12]}-"):
        raise DriverError("release generation identity mismatch")
    return _sha256_file(generation / "SHA256SUMS")


def validate_release_generation(layout: Layout) -> Path:
    release_metadata = _require_release_ancestry(layout)
    release_device = release_metadata.st_dev
    builds = layout.release_dir / "builds"
    _require_release_directory(builds, "release builds directory", release_device)
    current_path = layout.release_dir / "CURRENT"
    try:
        metadata = current_path.stat(follow_symlinks=False)
    except OSError as error:
        raise DriverError(f"missing or unsafe CURRENT: {current_path}") from error
    if (
        _metadata_is_link_or_reparse(metadata)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_dev != release_device
        or metadata.st_nlink != 1
    ):
        raise DriverError(f"missing or unsafe CURRENT: {current_path}")
    try:
        current = json.loads(current_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DriverError(f"invalid CURRENT: {current_path}") from error
    if set(current) != {"schema", "generation", "sha256sums_sha256"}:
        raise DriverError("CURRENT key set mismatch")
    generation_name = current.get("generation")
    if current.get("schema") != CURRENT_SCHEMA or not isinstance(generation_name, str):
        raise DriverError("CURRENT schema mismatch")
    if not GENERATION_PATTERN.fullmatch(generation_name):
        raise DriverError("CURRENT generation name is invalid")
    if not _lower_hex(current.get("sha256sums_sha256"), (64,)):
        raise DriverError("CURRENT checksum root is invalid")
    generation = builds / generation_name
    executable_name = "r46h-card.exe" if os.name == "nt" else "r46h-card"
    actual_sums = _validate_generation_directory(
        layout,
        generation,
        executable_name,
        release_device,
    )
    if current.get("sha256sums_sha256") != actual_sums:
        raise DriverError("CURRENT checksum root mismatch")
    return generation


def publish_release_generation(
    layout: Layout,
    work: Path,
    built: Path,
    source: SourceSnapshot,
    commands: Mapping[str, Path],
    environment: Mapping[str, str],
    gates: Sequence[Mapping[str, object]],
    storage_policy: str = "proven-non-system",
) -> Tuple[Path, str]:
    executable_name = "r46h-card.exe" if os.name == "nt" else "r46h-card"
    if not built.is_file() or _is_link_or_reparse(built):
        raise DriverError(f"release binary is missing or unsafe: {built}")

    stage = work / "release-generation"
    stage.mkdir(mode=0o700)
    digest, binary_size = _copy_regular_file(
        built, stage / executable_name, 0o755 if os.name != "nt" else 0o600
    )
    shutil.copyfile(source.manifest_path, stage / "SOURCE-MANIFEST.json")
    (stage / "SOURCE-MANIFEST.json").chmod(0o644)
    _fsync_file(stage / "SOURCE-MANIFEST.json")
    receipt = _publication_receipt(
        layout,
        source,
        executable_name,
        digest,
        binary_size,
        commands,
        environment,
        gates,
        storage_policy,
    )
    _write_new_file(stage / "BUILD-RECEIPT.json", _canonical_json(receipt), 0o644)
    checksum_names = sorted(
        {"BUILD-RECEIPT.json", "SOURCE-MANIFEST.json", executable_name},
        key=lambda item: item.encode("utf-8"),
    )
    sums = "".join(f"{_sha256_file(stage / name)}  {name}\n" for name in checksum_names)
    _write_new_file(stage / "SHA256SUMS", sums.encode("ascii"), 0o644)
    _fsync_directory(stage)

    _require_release_ancestry(layout)
    builds = layout.release_dir / "builds"
    builds.mkdir(mode=0o700, exist_ok=True)
    release_device = layout.release_dir.stat(follow_symlinks=False).st_dev
    _require_release_directory(builds, "release builds directory", release_device)
    generation_name = (
        f"build-{source.commit[:12]}-{digest[:12]}-{secrets.token_hex(4)}"
    )
    generation = builds / generation_name
    os.rename(stage, generation)
    _fsync_directory(builds)
    sums_sha256 = _validate_generation_directory(
        layout,
        generation,
        executable_name,
        release_device,
    )

    current = {
        "schema": CURRENT_SCHEMA,
        "generation": generation_name,
        "sha256sums_sha256": sums_sha256,
    }
    current_temp = layout.release_dir / f".CURRENT.{secrets.token_hex(8)}.tmp"
    _write_new_file(current_temp, _canonical_json(current), 0o644)
    try:
        os.replace(current_temp, layout.release_dir / "CURRENT")
    except OSError:
        if current_temp.is_file() and not _is_link_or_reparse(current_temp):
            current_temp.unlink()
        current_generation = None
        try:
            current_generation = validate_release_generation(layout)
        except (DriverError, OSError):
            pass
        if current_generation != generation and generation.is_dir():
            _remove_tree_on_device(
                generation,
                _mount_boundary(layout.release_dir, directory=True),
            )
        raise
    _fsync_directory(layout.release_dir)
    if validate_release_generation(layout) != generation:
        raise DriverError("published CURRENT does not resolve to the new generation")

    # CURRENT is the sole reader entry point. Once it is durable, old immutable
    # generations and the pre-generation flat v0.1 output are disposable.
    for entry in list(builds.iterdir()):
        if entry == generation:
            continue
        if (
            entry.is_dir()
            and not _is_link_or_reparse(entry)
            and GENERATION_PATTERN.fullmatch(entry.name)
        ):
            _remove_tree_on_device(
                entry,
                _mount_boundary(layout.release_dir, directory=True),
            )
    legacy_root = layout.release_dir.parent
    for name in (executable_name, "SHA256SUMS"):
        legacy = legacy_root / name
        if legacy.is_file() and not _is_link_or_reparse(legacy):
            legacy.unlink()
    return generation, digest


def _lock_timeout(raw: Optional[float]) -> float:
    if raw is not None:
        value = raw
    else:
        try:
            value = float(os.environ.get("R46H_CARD_LOCK_TIMEOUT", DEFAULT_LOCK_TIMEOUT_SECONDS))
        except ValueError as error:
            raise DriverError("R46H_CARD_LOCK_TIMEOUT must be numeric", EX_USAGE) from error
    if value < 0.0 or value > 3600.0:
        raise DriverError("lock timeout must be between 0 and 3600 seconds", EX_USAGE)
    return value


def _should_run_macos_launcher_tests() -> bool:
    return sys.platform == "darwin"


def command_build(args: argparse.Namespace) -> int:
    layout = make_layout(args.cache_root)
    validate_storage(
        layout, allow_system_storage_for_ci=args.allow_system_storage_for_ci
    )
    prepare_layout(layout)
    commands = resolve_rust_commands()
    cargo = str(commands["cargo"])

    with operation_lock(layout, _lock_timeout(args.lock_timeout)):
        # There can be no live peer work directory while this exclusive lock is held.
        safe_remove_cache_child(layout, "work")
        with private_work_dir(layout, "build") as work:
            commit, tree = require_clean_source_scope(layout)
            source = capture_source_snapshot(layout, work, commit, tree)
            workspace = source.root / "mainline" / "tools" / "r46h-card-toolchain"
            manifest = str(workspace / "Cargo.toml")
            private_target = work / "target"
            private_target.mkdir(mode=0o700)
            private_cargo_home = work / "cargo-home"
            environment = build_environment(
                layout,
                work,
                commands["rustc"],
                target_dir=private_target,
                cargo_home=private_cargo_home,
            )
            prune_shared_cargo_home(layout)
            if prepare_private_cargo_home(layout, work) != private_cargo_home:
                raise DriverError("private Cargo home path changed unexpectedly")
            environment["R46H_CARD_TEST_SCRATCH_ROOT"] = str(work / "driver-tests")
            if args.online:
                environment["CARGO_NET_OFFLINE"] = "false"
                _run(
                    [cargo, "fetch", "--locked", "--manifest-path", manifest],
                    environment,
                    workspace,
                )
                # Preserve only fetched archives/index metadata. Compiled
                # outputs and extracted dependency sources remain private.
                for relative in (
                    Path("registry") / "cache",
                    Path("registry") / "index",
                ):
                    fetched = private_cargo_home / relative
                    shared = layout.cargo_home / relative
                    if fetched.exists() or _is_link_or_reparse(fetched):
                        _validate_download_cache_tree(
                            fetched,
                            _mount_boundary(layout.cache_root, directory=True),
                        )
                        if shared.exists() or _is_link_or_reparse(shared):
                            _remove_tree_on_device(
                                shared,
                                _mount_boundary(layout.cache_root, directory=True),
                            )
                        shared.parent.mkdir(parents=True, exist_ok=True)
                        _copy_download_cache_tree(
                            fetched,
                            shared,
                            _mount_boundary(layout.cache_root, directory=True),
                        )
                prune_shared_cargo_home(layout)
                environment["CARGO_NET_OFFLINE"] = "true"
            common = ["--locked", "--manifest-path", manifest]
            gates: List[Mapping[str, object]] = []

            def run_gate(name: str, command: Sequence[str]) -> None:
                _run(command, environment, workspace)
                gates.append({"name": name, "argv": list(command), "exit_code": 0})

            python_test = source.root / "mainline" / "tests" / "test_r46h_card_toolchain_build.py"
            macos_launcher_test = (
                source.root / "mainline" / "tests" / "test_r46h_card_macos_readonly.py"
            )
            run_gate(
                "python-driver-tests",
                [sys.executable, "-I", "-B", str(python_test)],
            )
            if _should_run_macos_launcher_tests():
                run_gate(
                    "python-macos-launcher-tests",
                    [sys.executable, "-I", "-B", str(macos_launcher_test)],
                )
            run_gate(
                "format",
                [cargo, "fmt", "--all", "--manifest-path", manifest, "--", "--check"],
            )
            run_gate(
                "test",
                [cargo, "test", *common, "--workspace"],
            )
            run_gate(
                "clippy",
                [cargo, "clippy"]
                + common
                + ["--workspace", "--all-targets", "--", "-D", "warnings"],
            )
            run_gate(
                "release-build",
                [cargo, "build"]
                + common
                + ["--release", "--package", "r46h-card"],
            )
            # The live scope must still resolve to the captured source before
            # publication. Builds always used the private immutable snapshot.
            if require_clean_source_scope(layout) != (commit, tree):
                raise DriverError("source scope changed during the build")
            validate_source_snapshot(source)
            executable_name = "r46h-card.exe" if os.name == "nt" else "r46h-card"
            built = private_target / "release" / executable_name
            artifact_stage = work / "artifact-stage"
            artifact_stage.mkdir(mode=0o700)
            staged_binary = artifact_stage / executable_name
            _copy_regular_file(
                built,
                staged_binary,
                0o755 if os.name != "nt" else 0o600,
            )
            snapshot_root = source.root
            cache_boundary = _mount_boundary(layout.cache_root, directory=True)
            _remove_tree_on_device(snapshot_root, cache_boundary)
            _remove_tree_on_device(private_target, cache_boundary)
            if snapshot_root.exists() or private_target.exists():
                raise DriverError("private source or target cleanup did not complete")
            generation, digest = publish_release_generation(
                layout,
                work,
                staged_binary,
                source,
                commands,
                environment,
                gates,
                storage_policy=(
                    "explicit-ci-system-storage-override"
                    if args.allow_system_storage_for_ci
                    else "proven-non-system"
                ),
            )

    print(f"PASS: cross-platform toolchain built at {generation}")
    print(f"CURRENT={layout.release_dir / 'CURRENT'}")
    print(f"SHA256={digest}")
    return 0


def command_clean(args: argparse.Namespace) -> int:
    layout = make_layout(args.cache_root)
    validate_storage(
        layout, allow_system_storage_for_ci=args.allow_system_storage_for_ci
    )
    _prepare_cache_identity(layout)
    _mkdir_private(layout.state_root)
    selected = ["target", "work"]
    if args.all:
        selected.append("cargo-home")

    removed: List[str] = []
    with operation_lock(layout, _lock_timeout(args.lock_timeout)):
        for child_name in selected:
            if safe_remove_cache_child(layout, child_name):
                removed.append(child_name)

    detail = ", ".join(removed) if removed else "nothing to remove"
    print(f"PASS: cleaned card-toolchain cache ({detail})")
    return 0


def command_validate_release(args: argparse.Namespace) -> int:
    layout = make_layout(args.cache_root)
    generation = validate_release_generation(layout)
    print(f"PASS: release generation verified: {generation}")
    return 0


def _shell_assignments(environment: Mapping[str, str]) -> str:
    names = (
        "R46H_CARD_CACHE_ROOT",
        "CARGO_HOME",
        "CARGO_TARGET_DIR",
        "TMPDIR",
        "TMP",
        "TEMP",
        "CARGO_NET_OFFLINE",
        "RUSTUP_AUTO_INSTALL",
    )
    return "\n".join(f"export {name}={shlex.quote(environment[name])}" for name in names)


def _powershell_assignments(environment: Mapping[str, str]) -> str:
    names = (
        "R46H_CARD_CACHE_ROOT",
        "CARGO_HOME",
        "CARGO_TARGET_DIR",
        "TMPDIR",
        "TMP",
        "TEMP",
        "CARGO_NET_OFFLINE",
        "RUSTUP_AUTO_INSTALL",
    )
    lines = []
    for name in names:
        escaped = environment[name].replace("'", "''")
        lines.append(f"$env:{name} = '{escaped}'")
    return "\n".join(lines)


def command_env(args: argparse.Namespace) -> int:
    layout = make_layout(args.cache_root)
    validate_storage(layout)
    prepare_layout(layout)
    environment = build_environment(layout, layout.work_root)
    environment["R46H_CARD_CACHE_ROOT"] = str(layout.cache_root)
    selected = {
        name: environment[name]
        for name in (
            "R46H_CARD_CACHE_ROOT",
            "CARGO_HOME",
            "CARGO_TARGET_DIR",
            "TMPDIR",
            "TMP",
            "TEMP",
            "CARGO_NET_OFFLINE",
            "RUSTUP_AUTO_INSTALL",
        )
    }
    if args.format == "json":
        print(json.dumps(selected, sort_keys=True))
    elif args.format == "powershell":
        print(_powershell_assignments(selected))
    else:
        print(_shell_assignments(selected))
    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="test, lint, build, and publish the Rust CLI")
    build.add_argument(
        "--cache-root",
        help="absolute build/cache root (default: R46H_CARD_CACHE_ROOT or mainline/out/.cache)",
    )
    build.add_argument(
        "--allow-system-storage-for-ci",
        action="store_true",
        help="CI=true only: record and allow a system-volume build cache",
    )
    build.add_argument("--lock-timeout", type=float)
    build.add_argument(
        "--online",
        action="store_true",
        help="fetch dependencies pinned by Cargo.lock into the external cache",
    )
    build.set_defaults(handler=command_build)

    clean = subparsers.add_parser("clean", help="remove only named disposable cache children")
    clean.add_argument(
        "--cache-root",
        help="absolute build/cache root (default: R46H_CARD_CACHE_ROOT or mainline/out/.cache)",
    )
    clean.add_argument("--all", action="store_true", help="also remove the Cargo dependency cache")
    clean.add_argument("--lock-timeout", type=float)
    clean.add_argument(
        "--allow-system-storage-for-ci",
        action="store_true",
        help="CI=true only: allow cleanup in the explicitly recorded system-volume cache",
    )
    clean.set_defaults(handler=command_clean)

    validate = subparsers.add_parser(
        "validate-release", help="verify CURRENT and its immutable release generation"
    )
    validate.add_argument(
        "--cache-root",
        help="accepted for layout compatibility; release remains under mainline/out",
    )
    validate.set_defaults(handler=command_validate_release)

    env = subparsers.add_parser("env", help="print environment for direct Cargo commands")
    env.add_argument(
        "--cache-root",
        help="absolute build/cache root (default: R46H_CARD_CACHE_ROOT or mainline/out/.cache)",
    )
    env.add_argument("--format", choices=("sh", "powershell", "json"), default="json")
    env.set_defaults(handler=command_env)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        require_supported_python()
        parser = make_parser()
        args = parser.parse_args(argv)
        return int(args.handler(args))
    except DriverError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return error.exit_code
    except subprocess.CalledProcessError as error:
        print(f"ERROR: command failed with exit status {error.returncode}", file=sys.stderr)
        return error.returncode or 1


def _terminate(signum: int, _frame: object) -> None:
    raise SystemExit(128 + signum)


if __name__ == "__main__":
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _terminate)
    sys.exit(main())
