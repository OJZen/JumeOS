#!/usr/bin/env python3
"""Build the immutable R46H v0.14 p2 gaming-input one-shot payload."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
from typing import Any


REPO = Path(__file__).resolve().parents[2]
CACHE_ROOT = REPO / "mainline/out/.cache/r46h-v14-gaming-input-one-shot-build"
RELEASE_ROOT = REPO / "mainline/out/r46h-v14-gaming-input-one-shot"
PACKAGE_TAR = REPO / "mainline/out/r46h-mainline-test-v0.14-gaming-input-bridge.tar.gz"
PACKAGE_NAME = "r46h-mainline-test-v0.14-gaming-input-bridge"
PACKAGE_SIZE = 33_270_314
PACKAGE_SHA256 = "7bdf2aff75373c8482926131fc9f953030a05c66046cc147618c29e2ae939a62"
PACKAGE_SOURCE_COMMIT = "22be1f1381289cbd20c980591aefc1c32ca4a48d"
PACKAGE_SOURCE_SNAPSHOT = "724834ce2e0f6c7204ae43c91bee72422d8dd0880115c65634f60603f33c352e"
PACKAGE_MODULE_TREE = "adba2f4a0d116d8e077a3f44ba85d37cea758e7ab8d799d0da7d18702d30ebde"
BUILD_ID = "v0.14-gaming-input-bridge"
CANDIDATE_RELEASE = "6.12.99-r46h-mainline-v0.14-gaming-input-bridge"
RUNNING_RELEASE = "6.12.99-r46h-mainline-v0.10-adc-full-range"
ROOT_PARTUUID = "c9f931c9-02"
BOOT_PARTUUID = "c9f931c9-01"
IMAGE_SIZE = 41_570_816
IMAGE_SHA256 = "b02a2c4467a4c9ba1a0c1f3eac75ecd8d7fcb40c6e3d5d9d1d5d34e17a0ef10e"
DTB_SIZE = 49_518
DTB_SHA256 = "d1b035ee09ed0c44ccad62304f0c588d302c6055f634e65390850163cceba8ad"
MODULE_FILE_COUNT = 1_290
MODULE_DIRECTORY_COUNT = 395
PACKAGE_FILE_COUNT = 1_295
PACKAGE_DIRECTORY_COUNT = 400
SOURCE_DATE_EPOCH = 1_785_369_600
PAYLOAD_ID = "r46h-v14-gaming-input-one-shot-v1"
PAYLOAD_DIRECTORY = PAYLOAD_ID
TARGET_PARENT = "/var/lib/r46h-gaming-input-one-shot"
TARGET_DIRECTORY = f"{TARGET_PARENT}/{BUILD_ID}"
ARCHIVE_NAME = f"{PAYLOAD_ID}.tar.gz"
SOURCE_PATHS = (
    "mainline/gaming-input-one-shot/install.sh.in",
    "mainline/gaming-input-one-shot/remove.sh.in",
    "mainline/scripts/build-v14-gaming-input-one-shot.py",
    "mainline/tests/test-v14-gaming-input-one-shot.py",
)
TOP_DATA_NAMES = {
    "IMAGE.GZ",
    "MODULE-SHA256SUMS",
    "PAYLOAD-INFO.json",
    "R46H.DTB",
    "RECEIPT",
    "STATE-SHA256SUMS",
    "UBOOT-CMDS.txt",
    "install.sh",
    "remove.sh",
}
RELEASE_NAMES = {
    ARCHIVE_NAME,
    "BUILD-COMPLETE",
    "BUILD-RECEIPT.json",
    "SHA256SUMS",
    "SOURCE-MANIFEST.json",
}
GENERATION_RE = re.compile(r"^build-[0-9a-f]{12}-[0-9a-f]{12}$")


class BuildError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb", buffering=0) as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def git_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") and key not in {"BASH_ENV", "CDPATH", "ENV"}
    }
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "LC_ALL": "C",
        }
    )
    return environment


def git_bytes(arguments: list[str]) -> bytes:
    result = subprocess.run(
        ["/usr/bin/git", "--no-replace-objects", "-C", str(REPO), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=git_environment(),
    )
    if result.returncode != 0:
        raise BuildError(
            f"git {' '.join(arguments)} failed: "
            f"{result.stderr.decode(errors='replace').strip()}"
        )
    return result.stdout


def capture_clean_source() -> tuple[str, str, dict[str, bytes], bytes]:
    status = git_bytes(
        ["status", "--porcelain=v1", "--untracked-files=all", "--", *SOURCE_PATHS]
    )
    if status:
        raise BuildError("v0.14 one-shot source scope must be committed and clean")
    commit = git_bytes(["rev-parse", "--verify", "HEAD^{commit}"]).decode().strip()
    tree = git_bytes(["rev-parse", "--verify", "HEAD^{tree}"]).decode().strip()
    captured: dict[str, bytes] = {}
    entries: list[dict[str, object]] = []
    for relative in SOURCE_PATHS:
        live = REPO / relative
        metadata = live.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise BuildError(f"unsafe source identity: {relative}")
        tree_line = git_bytes(["ls-tree", "HEAD", "--", relative]).decode().strip()
        fields = tree_line.split(None, 3)
        blob = git_bytes(["cat-file", "blob", f"HEAD:{relative}"])
        if (
            len(fields) != 4
            or fields[1] != "blob"
            or fields[3] != relative
            or live.read_bytes() != blob
        ):
            raise BuildError(f"source is not one unchanged committed blob: {relative}")
        captured[relative] = blob
        entries.append(
            {
                "git_mode": fields[0],
                "path": relative,
                "sha256": sha256_bytes(blob),
                "size": len(blob),
            }
        )
    manifest = canonical_json(
        {
            "file_count": len(entries),
            "files": entries,
            "format_version": 1,
            "git_commit": commit,
            "git_tree": tree,
        }
    )
    return commit, tree, captured, manifest


def require_regular(path: Path, label: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise BuildError(f"missing {label}: {path}") from error
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise BuildError(f"unsafe {label}: {path}")
    return metadata


def require_directory(path: Path, label: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as error:
        raise BuildError(f"missing {label}: {path}") from error
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise BuildError(f"unsafe {label}: {path}")
    return metadata


def parse_checksum_manifest(value: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        lines = value.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise BuildError("checksum manifest is not ASCII") from error
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([^\n]+)", line)
        if match is None:
            raise BuildError("checksum manifest is malformed")
        digest, name = match.groups()
        pure = PurePosixPath(name)
        if pure.is_absolute() or ".." in pure.parts or name in result:
            raise BuildError(f"unsafe checksum path: {name}")
        result[name] = digest
    return result


def parse_key_values(value: bytes) -> dict[str, str]:
    try:
        lines = value.decode("ascii").splitlines()
    except UnicodeDecodeError as error:
        raise BuildError("package manifest is not ASCII") from error
    result: dict[str, str] = {}
    for line in lines:
        key, separator, item = line.partition("=")
        if not separator or not key or key in result:
            raise BuildError("package manifest is malformed")
        result[key] = item
    return result


def read_package(path: Path = PACKAGE_TAR) -> tuple[bytes, bytes, dict[str, bytes]]:
    metadata = require_regular(path, "canonical v0.14 package")
    if metadata.st_size != PACKAGE_SIZE or sha256_file(path) != PACKAGE_SHA256:
        raise BuildError("canonical v0.14 package identity mismatch")
    prefix = PACKAGE_NAME + "/"
    files: dict[str, bytes] = {}
    directory_count = 0
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)):
            raise BuildError("canonical package has duplicate members")
        for member in members:
            pure = PurePosixPath(member.name)
            if member.name == PACKAGE_NAME:
                if (
                    not member.isdir()
                    or member.uid != 0
                    or member.gid != 0
                    or member.mtime != SOURCE_DATE_EPOCH
                ):
                    raise BuildError("canonical package root identity mismatch")
                directory_count += 1
                continue
            if (
                pure.is_absolute()
                or ".." in pure.parts
                or not member.name.startswith(prefix)
                or member.uid != 0
                or member.gid != 0
                or member.mtime != SOURCE_DATE_EPOCH
                or member.issym()
                or member.islnk()
            ):
                raise BuildError(f"unsafe canonical package member: {member.name}")
            relative = member.name[len(prefix) :]
            if member.isdir():
                directory_count += 1
                continue
            if not member.isfile() or not relative:
                raise BuildError(f"unexpected canonical package member: {member.name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise BuildError(f"cannot read canonical package member: {member.name}")
            files[relative] = stream.read()
    if len(files) != PACKAGE_FILE_COUNT or directory_count != PACKAGE_DIRECTORY_COUNT:
        raise BuildError("canonical package file or directory count mismatch")
    sums = parse_checksum_manifest(files["SHA256SUMS"])
    data_names = set(files) - {"SHA256SUMS"}
    if set(sums) != data_names:
        raise BuildError("canonical package checksum member set mismatch")
    for name, digest in sums.items():
        if sha256_bytes(files[name]) != digest:
            raise BuildError(f"canonical package checksum mismatch: {name}")
    manifest = parse_key_values(files["MANIFEST"])
    expected_manifest = {
        "build_id": BUILD_ID,
        "kernel_release": CANDIDATE_RELEASE,
        "module_count": "1276",
        "module_tree_sha256": PACKAGE_MODULE_TREE,
        "root_spec": f"PARTUUID={ROOT_PARTUUID}",
        "source_git_commit": PACKAGE_SOURCE_COMMIT,
        "source_snapshot_sha256": PACKAGE_SOURCE_SNAPSHOT,
    }
    for key, value in expected_manifest.items():
        if manifest.get(key) != value:
            raise BuildError(f"canonical package manifest mismatch: {key}")
    image = files["boot/Image.mainline-test"]
    dtb = files["boot/rk3326-r46h-mainline-test.dtb"]
    if len(image) != IMAGE_SIZE or sha256_bytes(image) != IMAGE_SHA256:
        raise BuildError("canonical package Image mismatch")
    if len(dtb) != DTB_SIZE or sha256_bytes(dtb) != DTB_SHA256:
        raise BuildError("canonical package DTB mismatch")
    module_prefix = f"rootfs/lib/modules/{CANDIDATE_RELEASE}/"
    modules = {
        name[len(module_prefix) :]: value
        for name, value in files.items()
        if name.startswith(module_prefix)
    }
    if (
        len(modules) != MODULE_FILE_COUNT
        or relative_directory_count(modules) != MODULE_DIRECTORY_COUNT
        or sum(name.endswith(".ko") for name in modules) != 1_276
        or any(not name for name in modules)
    ):
        raise BuildError("canonical package module tree mismatch")
    return image, dtb, modules


def deterministic_gzip(payload: bytes) -> bytes:
    with io.BytesIO() as buffer:
        with gzip.GzipFile(
            filename="", mode="wb", compresslevel=9, fileobj=buffer, mtime=0
        ) as stream:
            stream.write(payload)
        return buffer.getvalue()


def render_uboot_commands(compressed_size: int) -> bytes:
    return f'''# R46H {BUILD_ID} p2 one-shot; p1 and persistent environment stay unchanged.
mmc dev 1
setenv loadaddr 0x02000000
setenv dtb_loadaddr 0x01f00000
setenv kernel_comp_addr 0x10000000
setenv bootargs "root=PARTUUID={ROOT_PARTUUID} rootwait rw fsck.repair=yes net.ifnames=0 console=ttyS2,115200n8 earlycon loglevel=7 ignore_loglevel plymouth.enable=0 clk_ignore_unused pd_ignore_unused"
if ext4load mmc 1:2 ${{kernel_comp_addr}} {TARGET_DIRECTORY}/IMAGE.GZ; then
  if itest ${{filesize}} -eq {compressed_size:#x}; then
    if unzip ${{kernel_comp_addr}} ${{loadaddr}} 0x03000000; then
      if itest ${{filesize}} -eq {IMAGE_SIZE:#x}; then
        if ext4load mmc 1:2 ${{dtb_loadaddr}} {TARGET_DIRECTORY}/R46H.DTB; then
          if itest ${{filesize}} -eq {DTB_SIZE:#x}; then
            booti ${{loadaddr}} - ${{dtb_loadaddr}}
          else
            echo "R46H {BUILD_ID}: DTB size mismatch"
          fi
        else
          echo "R46H {BUILD_ID}: DTB load failed"
        fi
      else
        echo "R46H {BUILD_ID}: decompressed Image size mismatch"
      fi
    else
      echo "R46H {BUILD_ID}: Image unzip failed"
    fi
  else
    echo "R46H {BUILD_ID}: compressed Image size mismatch"
  fi
else
  echo "R46H {BUILD_ID}: compressed Image load failed"
fi
'''.encode()


def render_template(value: bytes) -> bytes:
    try:
        text = value.decode("ascii")
    except UnicodeDecodeError as error:
        raise BuildError("shell template is not ASCII") from error
    replacements = {
        "@PAYLOAD_ID@": PAYLOAD_ID,
        "@RUNNING_RELEASE@": RUNNING_RELEASE,
        "@CANDIDATE_RELEASE@": CANDIDATE_RELEASE,
        "@ROOT_PARTUUID@": ROOT_PARTUUID,
        "@BOOT_PARTUUID@": BOOT_PARTUUID,
        "@PAYLOAD_DIRECTORY@": PAYLOAD_DIRECTORY,
        "@TARGET_PARENT@": TARGET_PARENT,
        "@TARGET_DIRECTORY@": TARGET_DIRECTORY,
        "@MODULE_FILE_COUNT@": str(MODULE_FILE_COUNT),
        "@MODULE_DIRECTORY_COUNT@": str(MODULE_DIRECTORY_COUNT),
    }
    for token, replacement in replacements.items():
        text = text.replace(token, replacement)
    if re.search(r"@[A-Z0-9_]+@", text):
        raise BuildError("unresolved shell-template token")
    return text.encode()


def module_checksum_manifest(modules: dict[str, bytes]) -> bytes:
    return "".join(
        f"{sha256_bytes(value)}  {name}\n" for name, value in sorted(modules.items())
    ).encode()


def relative_directory_count(files: dict[str, bytes]) -> int:
    directories = {PurePosixPath(".")}
    for name in files:
        parent = PurePosixPath(name).parent
        while parent != PurePosixPath("."):
            directories.add(parent)
            parent = parent.parent
    return len(directories)


def payload_files(
    image: bytes, dtb: bytes, modules: dict[str, bytes], captured: dict[str, bytes]
) -> dict[str, bytes]:
    compressed = deterministic_gzip(image)
    commands = render_uboot_commands(len(compressed))
    module_sums = module_checksum_manifest(modules)
    receipt = (
        f"payload_id={PAYLOAD_ID}\n"
        f"build_id={BUILD_ID}\n"
        f"kernel_release={CANDIDATE_RELEASE}\n"
        f"package_sha256={PACKAGE_SHA256}\n"
        f"module_tree_sha256={PACKAGE_MODULE_TREE}\n"
        f"image_sha256={IMAGE_SHA256}\n"
        f"dtb_sha256={DTB_SHA256}\n"
    ).encode()
    install_template = captured["mainline/gaming-input-one-shot/install.sh.in"]
    remove_template = captured["mainline/gaming-input-one-shot/remove.sh.in"]
    files: dict[str, bytes] = {
        "IMAGE.GZ": compressed,
        "MODULE-SHA256SUMS": module_sums,
        "R46H.DTB": dtb,
        "RECEIPT": receipt,
        "UBOOT-CMDS.txt": commands,
        "install.sh": render_template(install_template),
        "remove.sh": render_template(remove_template),
    }
    state_names = {
        "IMAGE.GZ",
        "MODULE-SHA256SUMS",
        "R46H.DTB",
        "RECEIPT",
        "UBOOT-CMDS.txt",
        "remove.sh",
    }
    files["STATE-SHA256SUMS"] = "".join(
        f"{sha256_bytes(files[name])}  {'REMOVE.sh' if name == 'remove.sh' else name}\n"
        for name in sorted(state_names)
    ).encode()
    files["PAYLOAD-INFO.json"] = canonical_json(
        {
            "boot_source": "mmc1-p2-ext4-one-shot",
            "build_id": BUILD_ID,
            "candidate_release": CANDIDATE_RELEASE,
            "format_version": 1,
            "module_directory_count": MODULE_DIRECTORY_COUNT,
            "module_file_count": MODULE_FILE_COUNT,
            "package": {
                "sha256": PACKAGE_SHA256,
                "size": PACKAGE_SIZE,
                "source_git_commit": PACKAGE_SOURCE_COMMIT,
                "source_snapshot_sha256": PACKAGE_SOURCE_SNAPSHOT,
            },
            "payload_id": PAYLOAD_ID,
            "root_spec": f"PARTUUID={ROOT_PARTUUID}",
            "safety": {
                "active_boot_changed": False,
                "existing_module_tree_changed": False,
                "persistent_environment_changed": False,
                "target_partition": "p2",
            },
        }
    )
    for name, value in modules.items():
        files[f"modules/{CANDIDATE_RELEASE}/{name}"] = value
    if set(files).intersection({"SHA256SUMS", "PAYLOAD.COMPLETE"}):
        raise BuildError("internal payload member collision")
    sums = "".join(
        f"{sha256_bytes(value)}  {name}\n" for name, value in sorted(files.items())
    ).encode()
    files["SHA256SUMS"] = sums
    files["PAYLOAD.COMPLETE"] = f"sha256sums_sha256={sha256_bytes(sums)}\n".encode()
    if not TOP_DATA_NAMES.issubset(files):
        raise BuildError("internal top-level payload member mismatch")
    return files


def payload_directories(files: dict[str, bytes]) -> list[str]:
    directories: set[str] = set()
    for name in files:
        pure = PurePosixPath(name)
        if pure.is_absolute() or ".." in pure.parts:
            raise BuildError(f"unsafe payload path: {name}")
        parent = pure.parent
        while parent != PurePosixPath("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    return sorted(directories, key=lambda name: (name.count("/"), name))


def deterministic_archive(files: dict[str, bytes]) -> bytes:
    with io.BytesIO() as tar_buffer:
        with tarfile.open(
            fileobj=tar_buffer, mode="w", format=tarfile.USTAR_FORMAT
        ) as archive:
            root = tarfile.TarInfo(PAYLOAD_DIRECTORY + "/")
            root.type = tarfile.DIRTYPE
            root.mode = 0o700
            root.uid = root.gid = 0
            root.uname = root.gname = "root"
            root.mtime = 0
            archive.addfile(root)
            for name in payload_directories(files):
                member = tarfile.TarInfo(f"{PAYLOAD_DIRECTORY}/{name}/")
                member.type = tarfile.DIRTYPE
                member.mode = 0o755
                member.uid = member.gid = 0
                member.uname = member.gname = "root"
                member.mtime = 0
                archive.addfile(member)
            for name, value in sorted(files.items()):
                member = tarfile.TarInfo(f"{PAYLOAD_DIRECTORY}/{name}")
                member.mode = 0o700 if name in {"install.sh", "remove.sh"} else 0o600
                member.uid = member.gid = 0
                member.uname = member.gname = "root"
                member.mtime = 0
                member.size = len(value)
                archive.addfile(member, io.BytesIO(value))
        raw_tar = tar_buffer.getvalue()
    with io.BytesIO() as output:
        with gzip.GzipFile(
            filename="", mode="wb", compresslevel=9, fileobj=output, mtime=0
        ) as stream:
            stream.write(raw_tar)
        return output.getvalue()


def validate_archive_bytes(archive_bytes: bytes) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    directories: set[str] = set()
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        members = archive.getmembers()
        names = [member.name for member in members]
        if len(names) != len(set(names)):
            raise BuildError("one-shot archive has duplicate members")
        for member in members:
            if (
                member.uid != 0
                or member.gid != 0
                or member.mtime != 0
                or member.issym()
                or member.islnk()
            ):
                raise BuildError(f"unsafe one-shot archive member: {member.name}")
            if member.name == PAYLOAD_DIRECTORY:
                if not member.isdir() or member.mode != 0o700:
                    raise BuildError("one-shot archive root identity mismatch")
                continue
            prefix = PAYLOAD_DIRECTORY + "/"
            if not member.name.startswith(prefix):
                raise BuildError(f"one-shot archive member escaped root: {member.name}")
            relative = member.name[len(prefix) :]
            if member.isdir():
                if member.mode != 0o755:
                    raise BuildError(f"one-shot directory mode mismatch: {relative}")
                directories.add(relative)
                continue
            expected_mode = 0o700 if relative in {"install.sh", "remove.sh"} else 0o600
            if not member.isfile() or member.mode != expected_mode:
                raise BuildError(f"one-shot file identity mismatch: {relative}")
            stream = archive.extractfile(member)
            if stream is None:
                raise BuildError(f"cannot read one-shot archive member: {relative}")
            files[relative] = stream.read()
    if directories != set(payload_directories(files)):
        raise BuildError("one-shot archive directory set mismatch")
    sums = parse_checksum_manifest(files["SHA256SUMS"])
    data_names = set(files) - {"SHA256SUMS", "PAYLOAD.COMPLETE"}
    if set(sums) != data_names:
        raise BuildError("one-shot checksum member set mismatch")
    for name, digest in sums.items():
        if sha256_bytes(files[name]) != digest:
            raise BuildError(f"one-shot checksum mismatch: {name}")
    expected_complete = f"sha256sums_sha256={sha256_bytes(files['SHA256SUMS'])}\n".encode()
    if files["PAYLOAD.COMPLETE"] != expected_complete:
        raise BuildError("one-shot completion marker mismatch")
    try:
        raw_image = gzip.decompress(files["IMAGE.GZ"])
    except (OSError, EOFError) as error:
        raise BuildError("one-shot compressed Image is invalid") from error
    if len(raw_image) != IMAGE_SIZE or sha256_bytes(raw_image) != IMAGE_SHA256:
        raise BuildError("one-shot raw Image mismatch")
    module_prefix = f"modules/{CANDIDATE_RELEASE}/"
    modules = {
        name[len(module_prefix) :]: value
        for name, value in files.items()
        if name.startswith(module_prefix)
    }
    if (
        len(modules) != MODULE_FILE_COUNT
        or relative_directory_count(modules) != MODULE_DIRECTORY_COUNT
    ):
        raise BuildError("one-shot module tree count mismatch")
    if files["MODULE-SHA256SUMS"] != module_checksum_manifest(modules):
        raise BuildError("one-shot module checksum manifest mismatch")
    expected_count_line = f"readonly MODULE_DIRECTORY_COUNT={MODULE_DIRECTORY_COUNT}"
    try:
        install_lines = files["install.sh"].decode("ascii").splitlines()
        payload_info = json.loads(files["PAYLOAD-INFO.json"])
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BuildError("one-shot generated metadata is invalid") from error
    if install_lines.count(expected_count_line) != 1:
        raise BuildError("one-shot installer module directory count mismatch")
    if payload_info.get("module_directory_count") != MODULE_DIRECTORY_COUNT:
        raise BuildError("one-shot payload module directory count mismatch")
    return files


def write_new(path: Path, payload: bytes, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def exact_json(path: Path) -> dict[str, Any]:
    def reject_duplicates(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise BuildError(f"duplicate key in {path.name}: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(path.read_bytes(), object_pairs_hook=reject_duplicates)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BuildError(f"cannot parse {path.name}") from error
    if not isinstance(value, dict):
        raise BuildError(f"{path.name} is not one object")
    return value


def validate_source_manifest(source: dict[str, Any]) -> None:
    if set(source) != {"file_count", "files", "format_version", "git_commit", "git_tree"}:
        raise BuildError("v0.14 one-shot source manifest key set mismatch")
    files = source.get("files")
    commit = source.get("git_commit")
    tree = source.get("git_tree")
    if (
        source.get("format_version") != 1
        or source.get("file_count") != len(SOURCE_PATHS)
        or not isinstance(files, list)
        or len(files) != len(SOURCE_PATHS)
        or not isinstance(commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", commit) is None
        or not isinstance(tree, str)
        or re.fullmatch(r"[0-9a-f]{40}", tree) is None
    ):
        raise BuildError("v0.14 one-shot source manifest identity mismatch")
    observed_tree = git_bytes(["rev-parse", "--verify", f"{commit}^{{tree}}"]).decode().strip()
    if observed_tree != tree:
        raise BuildError("v0.14 one-shot source Git tree mismatch")
    for expected_path, entry in zip(SOURCE_PATHS, files, strict=True):
        if not isinstance(entry, dict) or set(entry) != {
            "git_mode",
            "path",
            "sha256",
            "size",
        }:
            raise BuildError("v0.14 one-shot source file entry mismatch")
        blob = git_bytes(["cat-file", "blob", f"{commit}:{expected_path}"])
        tree_line = git_bytes(["ls-tree", commit, "--", expected_path]).decode().strip()
        fields = tree_line.split(None, 3)
        if (
            len(fields) != 4
            or fields[1] != "blob"
            or fields[3] != expected_path
            or entry.get("git_mode") != fields[0]
            or entry.get("path") != expected_path
            or entry.get("sha256") != sha256_bytes(blob)
            or entry.get("size") != len(blob)
        ):
            raise BuildError(f"v0.14 one-shot source blob mismatch: {expected_path}")


def release_checksum_manifest(root: Path) -> bytes:
    return "".join(
        f"{sha256_file(root / name)}  {name}\n"
        for name in sorted(RELEASE_NAMES - {"SHA256SUMS", "BUILD-COMPLETE"})
    ).encode()


def validate_generation() -> Path:
    current = RELEASE_ROOT / "CURRENT"
    require_regular(current, "CURRENT")
    generation_name = current.read_text(encoding="ascii").strip()
    if GENERATION_RE.fullmatch(generation_name) is None:
        raise BuildError("invalid v0.14 one-shot CURRENT")
    generation = RELEASE_ROOT / "builds" / generation_name
    require_directory(generation, "v0.14 one-shot generation")
    if {entry.name for entry in generation.iterdir()} != RELEASE_NAMES:
        raise BuildError("v0.14 one-shot generation member set mismatch")
    for name in RELEASE_NAMES:
        require_regular(generation / name, name)
    sums = release_checksum_manifest(generation)
    if (generation / "SHA256SUMS").read_bytes() != sums:
        raise BuildError("v0.14 one-shot generation checksum mismatch")
    complete = f"sha256sums_sha256={sha256_bytes(sums)}\n".encode()
    if (generation / "BUILD-COMPLETE").read_bytes() != complete:
        raise BuildError("v0.14 one-shot generation completion mismatch")
    archive_path = generation / ARCHIVE_NAME
    archive_bytes = archive_path.read_bytes()
    validate_archive_bytes(archive_bytes)
    receipt = exact_json(generation / "BUILD-RECEIPT.json")
    source = exact_json(generation / "SOURCE-MANIFEST.json")
    validate_source_manifest(source)
    if receipt != {
        "archive_sha256": sha256_bytes(archive_bytes),
        "archive_size": len(archive_bytes),
        "candidate_release": CANDIDATE_RELEASE,
        "format_version": 1,
        "package_sha256": PACKAGE_SHA256,
        "payload_id": PAYLOAD_ID,
        "source_git_commit": source.get("git_commit"),
        "source_git_tree": source.get("git_tree"),
        "source_manifest_sha256": sha256_file(generation / "SOURCE-MANIFEST.json"),
    }:
        raise BuildError("v0.14 one-shot build receipt mismatch")
    return generation


def publish_generation(stage: Path, generation_name: str) -> Path:
    RELEASE_ROOT.mkdir(parents=True, exist_ok=True)
    builds = RELEASE_ROOT / "builds"
    builds.mkdir(exist_ok=True)
    destination = builds / generation_name
    if destination.exists() or destination.is_symlink():
        raise BuildError(f"v0.14 one-shot generation already exists: {generation_name}")
    os.rename(stage, destination)
    pointer = RELEASE_ROOT / f".CURRENT.{os.getpid()}"
    write_new(pointer, f"{generation_name}\n".encode(), 0o644)
    os.replace(pointer, RELEASE_ROOT / "CURRENT")
    return destination


def command_build() -> Path:
    commit, tree, captured, source_manifest = capture_clean_source()
    image, dtb, modules = read_package()
    files = payload_files(image, dtb, modules, captured)
    archive = deterministic_archive(files)
    if deterministic_archive(files) != archive:
        raise BuildError("v0.14 one-shot archive is not reproducible")
    payload = validate_archive_bytes(archive)
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="work.", dir=CACHE_ROOT))
    stage = work / "generation"
    published = False
    try:
        stage.mkdir(mode=0o700)
        write_new(stage / ARCHIVE_NAME, archive)
        write_new(stage / "SOURCE-MANIFEST.json", source_manifest)
        archive_sha = sha256_bytes(archive)
        write_new(
            stage / "BUILD-RECEIPT.json",
            canonical_json(
                {
                    "archive_sha256": archive_sha,
                    "archive_size": len(archive),
                    "candidate_release": CANDIDATE_RELEASE,
                    "format_version": 1,
                    "package_sha256": PACKAGE_SHA256,
                    "payload_id": PAYLOAD_ID,
                    "source_git_commit": commit,
                    "source_git_tree": tree,
                    "source_manifest_sha256": sha256_bytes(source_manifest),
                }
            ),
        )
        sums = release_checksum_manifest(stage)
        write_new(stage / "SHA256SUMS", sums)
        write_new(
            stage / "BUILD-COMPLETE",
            f"sha256sums_sha256={sha256_bytes(sums)}\n".encode(),
        )
        generation_name = f"build-{commit[:12]}-{archive_sha[:12]}"
        destination = publish_generation(stage, generation_name)
        published = True
        validate_generation()
        print(f"PASS: v0.14 gaming-input one-shot published at {destination}")
        print(f"ARCHIVE={destination / ARCHIVE_NAME}")
        print(f"ARCHIVE_SIZE={len(archive)}")
        print(f"ARCHIVE_SHA256={archive_sha}")
        print(f"IMAGE_GZ_SIZE={len(payload['IMAGE.GZ'])}")
        print(f"MODULE_FILE_COUNT={MODULE_FILE_COUNT}")
        return destination
    finally:
        if not published and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)
        if CACHE_ROOT.exists() and not any(CACHE_ROOT.iterdir()):
            CACHE_ROOT.rmdir()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "validate"))
    return parser.parse_args()


def main() -> int:
    try:
        arguments = parse_args()
        if arguments.action == "build":
            command_build()
        else:
            generation = validate_generation()
            print(f"PASS: v0.14 gaming-input one-shot validated at {generation}")
    except (BuildError, OSError, ValueError, tarfile.TarError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 65
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
