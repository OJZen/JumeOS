#!/usr/bin/env python3
"""Build and validate the immutable R46H v0.11 read-only USB one-shot payload."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tarfile
import uuid


REPO = Path(__file__).resolve().parents[2]
CACHE_ROOT = REPO / "mainline/out/.cache/r46h-v11-usb-one-shot-build"
RELEASE_ROOT = REPO / "mainline/out/r46h-v11-usb-one-shot"
PACKAGE_TAR = REPO / "mainline/out/r46h-mainline-test-v0.11-usb-dc-detect.tar.gz"
PACKAGE_NAME = "r46h-mainline-test-v0.11-usb-dc-detect"
PACKAGE_SIZE = 33_260_077
PACKAGE_SHA256 = "771c3149a44ab14fa2d1a3d24f1589677fbc85bed84074aebe6e43561292f2b7"
PACKAGE_SOURCE_COMMIT = "88a1e31a35c84091a15c3c326e97b79b948c5920"
PACKAGE_SOURCE_SNAPSHOT = (
    "cb2d6c1483636bffdec6d09280f574e3eb346db642f12263c5378806ff1c8a73"
)
PACKAGE_MODULE_TREE = (
    "2c7419db11fbf6aaa3b7317d72ca1b245c5abd65b2e731c3ca6e24d0ac436f3f"
)
BUILD_ID = "v0.11-usb-dc-detect"
KERNEL_RELEASE = "6.12.99-r46h-mainline-v0.11-usb-dc-detect"
IMAGE_SIZE = 41_570_816
IMAGE_SHA256 = "7add2ef8a1af128722a59733d38cd799070cae2d8f8de71cab13e6e2fe6d652d"
DTB_SIZE = 49_518
DTB_SHA256 = "4d6d4ebad3b98600b6e9a38df4ca82230335558497a9e15dd0e81ca60e304b61"
CHARGER_RELATIVE = (
    f"rootfs/lib/modules/{KERNEL_RELEASE}/kernel/drivers/power/supply/"
    "rk817_charger.ko"
)
CHARGER_SIZE = 27_024
CHARGER_SHA256 = "bf40b5a7c4ce96db45536b97cc2b5f7d94e9047aa822168cf534e7c5cc915416"
ROOT_SPEC = "PARTUUID=c9f931c9-02"
DOCKER_IMAGE = "arkos4clone/r46h-kernel-builder:trixie-arm64"
DOCKER_IMAGE_ID = (
    "sha256:b0589c0f936cb78c5ccb4b21b280cdbb4d7b90c52c93360c14777e8ce772dbf4"
)
SOURCE_DATE_EPOCH = "1785369600"
PAYLOAD_DIRECTORY = "R46HV11"
SOURCE_PATHS = (
    "mainline/scripts/build-v11-usb-one-shot.py",
    "mainline/scripts/stage-v11-usb-one-shot-macos.py",
    "mainline/scripts/generate-easyroms-bundle.py",
    "mainline/bringup-tests/r46h-v11-charger-observe.c",
    "mainline/bringup-tests/V11-USB-DC-ONE-SHOT.md",
    "mainline/tests/test-v11-usb-one-shot.py",
    "mainline/tests/test-v11-usb-stage-macos.py",
)
PAYLOAD_DATA_NAMES = (
    "BOOT.INI",
    "CHARGER.KO",
    "IMAGE.GZ",
    "OBSERVER",
    "R46H.DTB",
)
PAYLOAD_NAMES = {*PAYLOAD_DATA_NAMES, "PAYLOAD.json", "SHA256SUMS", "PAYLOAD.COMPLETE"}
GENERATION_NAMES = {
    PAYLOAD_DIRECTORY,
    "BUILD-RECEIPT.json",
    "SOURCE-MANIFEST.json",
    "SHA256SUMS",
    "BUILD-COMPLETE",
}


class BuildError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def require_real_directory(
    path: Path, expected_device: int | None = None
) -> os.stat_result:
    metadata = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or (expected_device is not None and metadata.st_dev != expected_device)
    ):
        raise BuildError(f"unsafe directory identity: {path}")
    return metadata


def require_regular_file(
    path: Path, expected_device: int | None = None
) -> os.stat_result:
    metadata = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or (expected_device is not None and metadata.st_dev != expected_device)
    ):
        raise BuildError(f"unsafe file identity: {path}")
    return metadata


def valid_generation_name(value: object) -> bool:
    if not isinstance(value, str):
        return False
    fields = value.split("-")
    return (
        len(fields) == 3
        and fields[0] == "build"
        and all(len(field) == 12 for field in fields[1:])
        and all(
            character in "0123456789abcdef"
            for field in fields[1:]
            for character in field
        )
    )


def git_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") and key not in {"BASH_ENV", "CDPATH", "ENV"}
    }
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_NO_REPLACE_OBJECTS": "1",
            "LC_ALL": "C",
        }
    )
    return environment


def git_bytes(arguments: list[str], repo: Path = REPO) -> bytes:
    result = subprocess.run(
        ["/usr/bin/git", "--no-replace-objects", "-C", str(repo), *arguments],
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


def require_clean_source() -> tuple[str, str, dict[str, bytes], bytes]:
    status = git_bytes(
        ["status", "--porcelain=v1", "--untracked-files=all", "--", *SOURCE_PATHS]
    )
    if status:
        raise BuildError("USB one-shot source scope is not committed and clean")
    commit = git_bytes(["rev-parse", "--verify", "HEAD^{commit}"]).decode().strip()
    tree = git_bytes(["rev-parse", "--verify", "HEAD^{tree}"]).decode().strip()
    blobs: dict[str, bytes] = {}
    entries: list[dict[str, object]] = []
    for relative in SOURCE_PATHS:
        live = REPO / relative
        metadata = live.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise BuildError(f"unsafe source identity: {relative}")
        tree_line = git_bytes(["ls-tree", "HEAD", "--", relative]).decode().strip()
        fields = tree_line.split(None, 3)
        if len(fields) != 4 or fields[1] != "blob" or fields[3] != relative:
            raise BuildError(f"source is not one committed blob: {relative}")
        payload = git_bytes(["cat-file", "blob", f"HEAD:{relative}"])
        if live.read_bytes() != payload:
            raise BuildError(f"live source differs from HEAD: {relative}")
        blobs[relative] = payload
        entries.append(
            {
                "git_mode": fields[0],
                "path": relative,
                "sha256": sha256_bytes(payload),
                "size": len(payload),
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
    return commit, tree, blobs, manifest


def load_package_validator(source_root: Path):
    path = source_root / "mainline/scripts/generate-easyroms-bundle.py"
    spec = importlib.util.spec_from_file_location("r46h_bundle_validator", path)
    if spec is None or spec.loader is None:
        raise BuildError("cannot load canonical package validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot_package(destination: Path) -> Path:
    metadata = PACKAGE_TAR.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size != PACKAGE_SIZE
    ):
        raise BuildError("canonical v0.11 package identity mismatch")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    source_fd = os.open(PACKAGE_TAR, flags)
    try:
        before = os.fstat(source_fd)
        if (before.st_dev, before.st_ino, before.st_size) != (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
        ):
            raise BuildError("canonical package changed while opening")
        output_fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
        digest = hashlib.sha256()
        total = 0
        try:
            while True:
                block = os.read(source_fd, 1024 * 1024)
                if not block:
                    break
                digest.update(block)
                total += len(block)
                view = memoryview(block)
                while view:
                    written = os.write(output_fd, view)
                    if written <= 0:
                        raise BuildError("short write while freezing canonical package")
                    view = view[written:]
            os.fsync(output_fd)
        finally:
            os.close(output_fd)
        after = os.fstat(source_fd)
        named = PACKAGE_TAR.lstat()
        if (
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            or (named.st_dev, named.st_ino, named.st_size)
            != (before.st_dev, before.st_ino, before.st_size)
            or total != PACKAGE_SIZE
            or digest.hexdigest() != PACKAGE_SHA256
        ):
            raise BuildError("canonical v0.11 package changed or has wrong SHA-256")
    finally:
        os.close(source_fd)
    return destination


def require_package(snapshot: Path, validator) -> tuple[dict[str, object], bytes]:
    package = validator.read_package(snapshot)
    manifest = package.get("manifest")
    if not isinstance(manifest, dict):
        raise BuildError("canonical package manifest is malformed")
    expected = {
        "tar_size": PACKAGE_SIZE,
        "tar_sha256": PACKAGE_SHA256,
        "package_name": PACKAGE_NAME,
        "build_id": BUILD_ID,
        "release": KERNEL_RELEASE,
        "module_count": 1276,
        "module_file_count": 1290,
        "module_tree_sha256": PACKAGE_MODULE_TREE,
        "source_git_commit": PACKAGE_SOURCE_COMMIT,
        "source_snapshot_sha256": PACKAGE_SOURCE_SNAPSHOT,
        "root_spec": ROOT_SPEC,
        "console": "ttyS2,115200n8",
    }
    for key, value in expected.items():
        if package.get(key) != value:
            raise BuildError(f"canonical package {key} mismatch")
    image = package.get("image")
    dtb = package.get("dtb")
    if (
        not isinstance(image, bytes)
        or len(image) != IMAGE_SIZE
        or sha256_bytes(image) != IMAGE_SHA256
        or not isinstance(dtb, bytes)
        or len(dtb) != DTB_SIZE
        or sha256_bytes(dtb) != DTB_SHA256
    ):
        raise BuildError("canonical package Image or DTB mismatch")

    member_name = f"{PACKAGE_NAME}/{CHARGER_RELATIVE}"
    with tarfile.open(snapshot, "r:gz") as archive:
        matches = [member for member in archive.getmembers() if member.name == member_name]
        if len(matches) != 1 or not matches[0].isfile() or matches[0].size != CHARGER_SIZE:
            raise BuildError("canonical package charger module member mismatch")
        stream = archive.extractfile(matches[0])
        if stream is None:
            raise BuildError("cannot read canonical charger module")
        charger = stream.read()
    if len(charger) != CHARGER_SIZE or sha256_bytes(charger) != CHARGER_SHA256:
        raise BuildError("canonical charger module SHA-256 mismatch")
    return package, charger


def write_source_snapshot(root: Path, blobs: dict[str, bytes]) -> Path:
    source = root / "source"
    source.mkdir(mode=0o700)
    for relative, payload in blobs.items():
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    return source


def require_source_snapshot(source: Path, blobs: dict[str, bytes]) -> None:
    for relative, expected in blobs.items():
        candidate = source / relative
        metadata = candidate.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or candidate.read_bytes() != expected
        ):
            raise BuildError(f"source snapshot changed: {relative}")


def run_host_tests(source: Path, package_snapshot: Path) -> None:
    package_copy = source / PACKAGE_TAR.relative_to(REPO)
    package_copy.parent.mkdir(parents=True, mode=0o700)
    os.link(package_snapshot, package_copy)
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"BASH_ENV", "CDPATH", "ENV", "PYTHONPATH", "PYTHONHOME"}
    }
    environment.update(
        {
            "LC_ALL": "C",
            "PYTHONDONTWRITEBYTECODE": "1",
            "R46H_RUN_V11_USB_INTEGRATION": "0",
        }
    )
    for relative in (
        "mainline/tests/test-v11-usb-one-shot.py",
        "mainline/tests/test-v11-usb-stage-macos.py",
    ):
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(source / relative), "-v"],
            check=False,
            cwd=source,
            env=environment,
        )
        if result.returncode != 0:
            raise BuildError(f"v0.11 USB host tests failed: {relative}")


def docker_image_identity() -> None:
    result = subprocess.run(
        ["docker", "image", "inspect", DOCKER_IMAGE, "--format", "{{.Id}}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0 or result.stdout.strip() != DOCKER_IMAGE_ID:
        raise BuildError("pinned ARM64 builder image is unavailable or changed")


def compile_observer(work: Path, source: Path) -> tuple[bytes, str, str]:
    output = work / "observer-output"
    output.mkdir(mode=0o700)
    command = (
        "set -euo pipefail; "
        "mkdir -p /output/a /output/b; "
        "for slot in a b; do "
        "cc -std=c11 -O2 -Wall -Wextra -Werror -D_FORTIFY_SOURCE=2 "
        "-fPIE -pie /source/mainline/bringup-tests/r46h-v11-charger-observe.c "
        "-o /output/$slot/OBSERVER; done; "
        "cmp /output/a/OBSERVER /output/b/OBSERVER; "
        "/output/a/OBSERVER --help; "
        "cc --version | head -1 > /output/CC-VERSION; "
        "ld --version | head -1 > /output/LD-VERSION"
    )
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--platform",
            "linux/arm64",
            "--entrypoint",
            "/bin/bash",
            "--env",
            f"SOURCE_DATE_EPOCH={SOURCE_DATE_EPOCH}",
            "--volume",
            f"{source}:/source:ro",
            "--volume",
            f"{output}:/output",
            DOCKER_IMAGE,
            "-lc",
            command,
        ],
        check=False,
    )
    if result.returncode != 0:
        raise BuildError("ARM64 observer compilation or reproducibility check failed")
    binary = (output / "a/OBSERVER").read_bytes()
    if (
        len(binary) < 64
        or binary[:4] != b"\x7fELF"
        or binary[4:6] != b"\x02\x01"
        or int.from_bytes(binary[18:20], "little") != 183
    ):
        raise BuildError("observer is not one little-endian AArch64 ELF binary")
    return (
        binary,
        (output / "CC-VERSION").read_text().strip(),
        (output / "LD-VERSION").read_text().strip(),
    )


def deterministic_gzip(payload: bytes) -> bytes:
    with io.BytesIO() as buffer:
        with gzip.GzipFile(
            filename="", mode="wb", compresslevel=9, fileobj=buffer, mtime=0
        ) as stream:
            stream.write(payload)
        result = buffer.getvalue()
    if result[:10] not in {
        b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\x03",
        b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff",
    }:
        raise BuildError("unexpected deterministic gzip header")
    return result


def render_boot_script(image_size: int, raw_size: int, dtb_size: int) -> bytes:
    text = f"""odroidgoa-uboot-config

# R46H {BUILD_ID} read-only USB one-shot.
# The active TF boot.ini and U-Boot environment remain unchanged.
setenv bootargs \"root={ROOT_SPEC} rootwait ro init=/bin/bash net.ifnames=0 console=ttyS2,115200n8 earlycon loglevel=7 ignore_loglevel plymouth.enable=0 clk_ignore_unused pd_ignore_unused\"

setenv loadaddr \"0x02000000\"
setenv dtb_loadaddr \"0x01f00000\"
setenv kernel_comp_addr \"0x10000000\"

if fatload usb 0:1 ${{kernel_comp_addr}} {PAYLOAD_DIRECTORY}/IMAGE.GZ; then
  if itest ${{filesize}} -eq {image_size:#x}; then
    if unzip ${{kernel_comp_addr}} ${{loadaddr}} 0x03000000; then
      if itest ${{filesize}} -eq {raw_size:#x}; then
        if fatload usb 0:1 ${{dtb_loadaddr}} {PAYLOAD_DIRECTORY}/R46H.DTB; then
          if itest ${{filesize}} -eq {dtb_size:#x}; then
            booti ${{loadaddr}} - ${{dtb_loadaddr}}
          else
            echo \"R46H {BUILD_ID}: DTB size mismatch\"
          fi
        else
          echo \"R46H {BUILD_ID}: DTB load failed\"
        fi
      else
        echo \"R46H {BUILD_ID}: decompressed Image size mismatch\"
      fi
    else
      echo \"R46H {BUILD_ID}: Image unzip failed\"
    fi
  else
    echo \"R46H {BUILD_ID}: compressed Image size mismatch\"
  fi
else
  echo \"R46H {BUILD_ID}: compressed Image load failed\"
fi
"""
    return text.encode()


def write_new(path: Path, payload: bytes, mode: int = 0o644) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def tree_manifest(root: Path, excluded: set[str]) -> bytes:
    lines: list[str] = []
    for candidate in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        metadata = candidate.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or candidate.is_symlink()
        ):
            raise BuildError(f"unsafe manifest member: {candidate.relative_to(root)}")
        relative = candidate.relative_to(root).as_posix()
        if relative in excluded:
            continue
        lines.append(f"{sha256_file(candidate)}  {relative}\n")
    return "".join(lines).encode()


def build_generation(
    stage: Path,
    commit: str,
    tree: str,
    source_manifest: bytes,
    package: dict[str, object],
    charger: bytes,
    observer: bytes,
    cc_version: str,
    ld_version: str,
) -> str:
    payload_root = stage / PAYLOAD_DIRECTORY
    payload_root.mkdir(mode=0o755)
    image = package["image"]
    dtb = package["dtb"]
    assert isinstance(image, bytes) and isinstance(dtb, bytes)
    compressed = deterministic_gzip(image)
    boot = render_boot_script(len(compressed), len(image), len(dtb))
    payload_data = {
        "BOOT.INI": boot,
        "CHARGER.KO": charger,
        "IMAGE.GZ": compressed,
        "OBSERVER": observer,
        "R46H.DTB": dtb,
    }
    for name, value in payload_data.items():
        write_new(payload_root / name, value, 0o755 if name == "OBSERVER" else 0o644)
    payload_manifest = {
        "boot_source": "usb-fat32-read-only",
        "build_id": BUILD_ID,
        "files": {
            name: {"sha256": sha256_bytes(value), "size": len(value)}
            for name, value in sorted(payload_data.items())
        },
        "format_version": 1,
        "kernel_release": KERNEL_RELEASE,
        "package": {
            "sha256": PACKAGE_SHA256,
            "size": PACKAGE_SIZE,
            "source_git_commit": PACKAGE_SOURCE_COMMIT,
            "source_snapshot_sha256": PACKAGE_SOURCE_SNAPSHOT,
        },
        "payload_id": "r46h-v11-usb-one-shot-v1",
        "root_spec": ROOT_SPEC,
        "safety": {
            "active_boot_changed": False,
            "saveenv_used": False,
            "tf_card_write": False,
        },
    }
    write_new(payload_root / "PAYLOAD.json", canonical_json(payload_manifest))
    payload_sums = tree_manifest(payload_root, {"SHA256SUMS", "PAYLOAD.COMPLETE"})
    write_new(payload_root / "SHA256SUMS", payload_sums)
    write_new(
        payload_root / "PAYLOAD.COMPLETE",
        f"sha256sums_sha256={sha256_bytes(payload_sums)}\n".encode(),
    )

    write_new(stage / "SOURCE-MANIFEST.json", source_manifest)
    receipt = {
        "artifact": {
            "observer_sha256": sha256_bytes(observer),
            "payload_manifest_sha256": sha256_file(payload_root / "PAYLOAD.json"),
            "payload_sha256sums_sha256": sha256_bytes(payload_sums),
        },
        "build": {
            "cc": cc_version,
            "docker_image": DOCKER_IMAGE,
            "docker_image_id": DOCKER_IMAGE_ID,
            "ld": ld_version,
            "reproducible_observer_builds": 2,
            "source_date_epoch": int(SOURCE_DATE_EPOCH),
        },
        "format_version": 1,
        "package": {
            "sha256": PACKAGE_SHA256,
            "size": PACKAGE_SIZE,
            "source_git_commit": PACKAGE_SOURCE_COMMIT,
            "source_snapshot_sha256": PACKAGE_SOURCE_SNAPSHOT,
        },
        "source": {
            "file_count": len(SOURCE_PATHS),
            "git_commit": commit,
            "git_tree": tree,
            "manifest_sha256": sha256_bytes(source_manifest),
        },
    }
    write_new(stage / "BUILD-RECEIPT.json", canonical_json(receipt))
    generation_sums = tree_manifest(stage, {"SHA256SUMS", "BUILD-COMPLETE"})
    write_new(stage / "SHA256SUMS", generation_sums)
    write_new(
        stage / "BUILD-COMPLETE",
        f"sha256sums_sha256={sha256_bytes(generation_sums)}\n".encode(),
    )
    stage_fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(stage_fd)
    finally:
        os.close(stage_fd)
    return f"build-{commit[:12]}-{sha256_bytes(payload_sums)[:12]}"


def exact_json(path: Path) -> dict[str, object]:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise BuildError(f"duplicate JSON key in {path.name}: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(path.read_bytes(), object_pairs_hook=reject_duplicates)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BuildError(f"cannot parse {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise BuildError(f"{path.name} is not one JSON object")
    return value


def validate_sums(root: Path, sums_name: str, excluded: set[str]) -> str:
    sums = root / sums_name
    if not sums.is_file() or sums.is_symlink():
        raise BuildError(f"missing safe {sums_name}")
    expected = tree_manifest(root, excluded)
    if sums.read_bytes() != expected:
        raise BuildError(f"{sums_name} does not bind the exact file set")
    return sha256_bytes(expected)


def validate_generation(
    generation: Path,
    expected_commit: str | None,
    staged_generation_name: str | None = None,
) -> None:
    generation_metadata = generation.lstat()
    if not stat.S_ISDIR(generation_metadata.st_mode) or generation.is_symlink():
        raise BuildError("release generation is not one real directory")
    members = {entry.name: entry for entry in generation.iterdir()}
    names = set(members)
    if names != GENERATION_NAMES:
        raise BuildError(f"release generation member set mismatch: {sorted(names)}")
    payload = generation / PAYLOAD_DIRECTORY
    for name, candidate in members.items():
        metadata = candidate.lstat()
        expected_directory = name == PAYLOAD_DIRECTORY
        if (
            candidate.is_symlink()
            or metadata.st_dev != generation_metadata.st_dev
            or (expected_directory and not stat.S_ISDIR(metadata.st_mode))
            or (not expected_directory and not stat.S_ISREG(metadata.st_mode))
            or (not expected_directory and metadata.st_nlink != 1)
        ):
            raise BuildError(f"unsafe release member: {name}")
    payload_metadata = payload.lstat()
    payload_members = {entry.name: entry for entry in payload.iterdir()}
    payload_names = set(payload_members)
    if payload_names != PAYLOAD_NAMES:
        raise BuildError(f"USB payload member set mismatch: {sorted(payload_names)}")
    for name, candidate in payload_members.items():
        metadata = candidate.lstat()
        if (
            candidate.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_dev != payload_metadata.st_dev
        ):
            raise BuildError(f"unsafe USB payload member: {name}")
    payload_sum = validate_sums(payload, "SHA256SUMS", {"SHA256SUMS", "PAYLOAD.COMPLETE"})
    if (payload / "PAYLOAD.COMPLETE").read_text() != f"sha256sums_sha256={payload_sum}\n":
        raise BuildError("USB payload completion marker mismatch")
    generation_sum = validate_sums(
        generation, "SHA256SUMS", {"SHA256SUMS", "BUILD-COMPLETE"}
    )
    if (generation / "BUILD-COMPLETE").read_text() != (
        f"sha256sums_sha256={generation_sum}\n"
    ):
        raise BuildError("release completion marker mismatch")
    source_path = generation / "SOURCE-MANIFEST.json"
    receipt_path = generation / "BUILD-RECEIPT.json"
    source = exact_json(source_path)
    receipt = exact_json(receipt_path)
    payload_manifest = exact_json(payload / "PAYLOAD.json")
    if set(source) != {"file_count", "files", "format_version", "git_commit", "git_tree"}:
        raise BuildError("source manifest key set mismatch")
    commit = source.get("git_commit")
    if expected_commit is not None and commit != expected_commit:
        raise BuildError("release source commit does not match current clean source")
    if not isinstance(commit, str):
        raise BuildError("release source commit is malformed")
    observed_tree = git_bytes(["rev-parse", f"{commit}^{{tree}}"]).decode().strip()
    if source.get("git_tree") != observed_tree:
        raise BuildError("source manifest Git tree mismatch")
    entries = source.get("files")
    if (
        source.get("format_version") != 1
        or source.get("file_count") != len(SOURCE_PATHS)
        or not isinstance(entries, list)
        or len(entries) != len(SOURCE_PATHS)
    ):
        raise BuildError("source manifest shape mismatch")
    for relative, entry in zip(SOURCE_PATHS, entries, strict=True):
        if not isinstance(entry, dict) or set(entry) != {"git_mode", "path", "sha256", "size"}:
            raise BuildError("source manifest entry shape mismatch")
        tree_line = git_bytes(["ls-tree", commit, "--", relative]).decode().strip()
        fields = tree_line.split(None, 3)
        blob = git_bytes(["cat-file", "blob", f"{commit}:{relative}"])
        if (
            len(fields) != 4
            or fields[1] != "blob"
            or fields[3] != relative
            or entry
            != {
                "git_mode": fields[0],
                "path": relative,
                "sha256": sha256_bytes(blob),
                "size": len(blob),
            }
        ):
            raise BuildError(f"source manifest Git blob mismatch: {relative}")
    if set(receipt) != {"artifact", "build", "format_version", "package", "source"}:
        raise BuildError("build receipt key set mismatch")
    if receipt.get("source") != {
        "file_count": len(SOURCE_PATHS),
        "git_commit": commit,
        "git_tree": source.get("git_tree"),
        "manifest_sha256": sha256_file(source_path),
    }:
        raise BuildError("release source receipt mismatch")
    if receipt.get("format_version") != 1 or receipt.get("package") != {
        "sha256": PACKAGE_SHA256,
        "size": PACKAGE_SIZE,
        "source_git_commit": PACKAGE_SOURCE_COMMIT,
        "source_snapshot_sha256": PACKAGE_SOURCE_SNAPSHOT,
    }:
        raise BuildError("build receipt package provenance mismatch")
    build = receipt.get("build")
    artifact = receipt.get("artifact")
    if (
        not isinstance(build, dict)
        or set(build)
        != {
            "cc",
            "docker_image",
            "docker_image_id",
            "ld",
            "reproducible_observer_builds",
            "source_date_epoch",
        }
        or build.get("docker_image") != DOCKER_IMAGE
        or build.get("docker_image_id") != DOCKER_IMAGE_ID
        or build.get("reproducible_observer_builds") != 2
        or build.get("source_date_epoch") != int(SOURCE_DATE_EPOCH)
        or not isinstance(build.get("cc"), str)
        or not isinstance(build.get("ld"), str)
        or not isinstance(artifact, dict)
        or set(artifact)
        != {"observer_sha256", "payload_manifest_sha256", "payload_sha256sums_sha256"}
    ):
        raise BuildError("build receipt artifact/toolchain shape mismatch")
    if set(payload_manifest) != {
        "boot_source",
        "build_id",
        "files",
        "format_version",
        "kernel_release",
        "package",
        "payload_id",
        "root_spec",
        "safety",
    }:
        raise BuildError("USB payload manifest key set mismatch")
    if payload_manifest.get("package") != {
        "sha256": PACKAGE_SHA256,
        "size": PACKAGE_SIZE,
        "source_git_commit": PACKAGE_SOURCE_COMMIT,
        "source_snapshot_sha256": PACKAGE_SOURCE_SNAPSHOT,
    }:
        raise BuildError("USB payload package provenance mismatch")
    if (
        payload_manifest.get("boot_source") != "usb-fat32-read-only"
        or payload_manifest.get("build_id") != BUILD_ID
        or payload_manifest.get("format_version") != 1
        or payload_manifest.get("kernel_release") != KERNEL_RELEASE
        or payload_manifest.get("payload_id") != "r46h-v11-usb-one-shot-v1"
        or payload_manifest.get("root_spec") != ROOT_SPEC
        or payload_manifest.get("safety")
        != {"active_boot_changed": False, "saveenv_used": False, "tf_card_write": False}
    ):
        raise BuildError("USB payload semantic contract mismatch")
    files = payload_manifest.get("files")
    actual_files = {
        name: {
            "sha256": sha256_file(payload / name),
            "size": (payload / name).stat().st_size,
        }
        for name in PAYLOAD_DATA_NAMES
    }
    if files != actual_files:
        raise BuildError("USB payload file manifest mismatch")
    compressed = (payload / "IMAGE.GZ").read_bytes()
    try:
        image = gzip.decompress(compressed)
    except (OSError, EOFError) as exc:
        raise BuildError(f"USB Image gzip is invalid: {exc}") from exc
    if len(image) != IMAGE_SIZE or sha256_bytes(image) != IMAGE_SHA256:
        raise BuildError("USB Image bytes mismatch")
    if (
        (payload / "R46H.DTB").stat().st_size != DTB_SIZE
        or sha256_file(payload / "R46H.DTB") != DTB_SHA256
        or (payload / "CHARGER.KO").stat().st_size != CHARGER_SIZE
        or sha256_file(payload / "CHARGER.KO") != CHARGER_SHA256
        or (payload / "BOOT.INI").read_bytes()
        != render_boot_script(len(compressed), len(image), DTB_SIZE)
    ):
        raise BuildError("USB boot/DTB/charger contract mismatch")
    observer = (payload / "OBSERVER").read_bytes()
    if (
        len(observer) < 64
        or observer[:4] != b"\x7fELF"
        or observer[4:6] != b"\x02\x01"
        or int.from_bytes(observer[18:20], "little") != 183
        or artifact.get("observer_sha256") != sha256_bytes(observer)
        or artifact.get("payload_manifest_sha256")
        != sha256_file(payload / "PAYLOAD.json")
        or artifact.get("payload_sha256sums_sha256") != payload_sum
    ):
        raise BuildError("USB observer or artifact receipt mismatch")
    expected_name = f"build-{commit[:12]}-{payload_sum[:12]}"
    observed_name = (
        generation.name if staged_generation_name is None else staged_generation_name
    )
    if observed_name != expected_name:
        raise BuildError("release generation name mismatch")


def publish(stage: Path, generation_name: str, validator) -> Path:
    RELEASE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o755)
    release_metadata = require_real_directory(RELEASE_ROOT)
    builds = RELEASE_ROOT / "builds"
    builds.mkdir(mode=0o755, exist_ok=True)
    require_real_directory(builds, release_metadata.st_dev)
    destination = builds / generation_name
    if destination.exists() or destination.is_symlink():
        raise BuildError("immutable USB generation already exists")
    source_fd = os.open(stage.parent, os.O_RDONLY | os.O_DIRECTORY)
    destination_fd = os.open(builds, os.O_RDONLY | os.O_DIRECTORY)
    try:
        validator.rename_noreplace_at(
            source_fd, stage.name, destination_fd, generation_name
        )
    finally:
        os.close(destination_fd)
        os.close(source_fd)
    current = canonical_json(
        {
            "format_version": 1,
            "generation": generation_name,
            "sha256sums_sha256": sha256_file(destination / "SHA256SUMS"),
        }
    )
    temporary = RELEASE_ROOT / f".CURRENT.{uuid.uuid4().hex}"
    write_new(temporary, current)
    os.replace(temporary, RELEASE_ROOT / "CURRENT")
    directory_fd = os.open(RELEASE_ROOT, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return destination


def command_build() -> None:
    commit, tree, blobs, source_manifest = require_clean_source()
    docker_image_identity()
    CACHE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    require_real_directory(CACHE_ROOT, REPO.lstat().st_dev)
    work = CACHE_ROOT / f"work-{uuid.uuid4().hex}"
    work.mkdir(mode=0o700)
    stage: Path | None = None
    try:
        source = write_source_snapshot(work, blobs)
        validator = load_package_validator(source)
        package_snapshot = snapshot_package(work / "package.tar.gz")
        run_host_tests(source, package_snapshot)
        require_source_snapshot(source, blobs)
        package, charger = require_package(package_snapshot, validator)
        observer, cc_version, ld_version = compile_observer(work, source)
        stage = work / f"stage-{uuid.uuid4().hex}"
        stage.mkdir(mode=0o700)
        generation_name = build_generation(
            stage,
            commit,
            tree,
            source_manifest,
            package,
            charger,
            observer,
            cc_version,
            ld_version,
        )
        validate_generation(stage, commit, generation_name)
        generation = publish(stage, generation_name, validator)
        stage = None
        validate_generation(generation, commit)
        print(f"PASS: immutable v0.11 USB one-shot published at {generation}")
        print(f"PAYLOAD_DIR={generation / PAYLOAD_DIRECTORY}")
        print(f"PAYLOAD_SHA256SUMS={sha256_file(generation / PAYLOAD_DIRECTORY / 'SHA256SUMS')}")
        print(f"BOOT_SCRIPT_SIZE={(generation / PAYLOAD_DIRECTORY / 'BOOT.INI').stat().st_size}")
        print(f"OBSERVER_SHA256={sha256_file(generation / PAYLOAD_DIRECTORY / 'OBSERVER')}")
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage)
        if work.exists():
            shutil.rmtree(work)
        if CACHE_ROOT.exists() and not any(CACHE_ROOT.iterdir()):
            CACHE_ROOT.rmdir()


def command_validate() -> None:
    commit, _, _, _ = require_clean_source()
    release_metadata = require_real_directory(RELEASE_ROOT)
    require_real_directory(RELEASE_ROOT / "builds", release_metadata.st_dev)
    current_path = RELEASE_ROOT / "CURRENT"
    require_regular_file(current_path, release_metadata.st_dev)
    current = exact_json(current_path)
    if set(current) != {"format_version", "generation", "sha256sums_sha256"}:
        raise BuildError("CURRENT key set mismatch")
    generation_name = current.get("generation")
    if not valid_generation_name(generation_name):
        raise BuildError("CURRENT generation name is malformed")
    generation = RELEASE_ROOT / "builds" / generation_name
    validate_generation(generation, commit)
    if current.get("sha256sums_sha256") != sha256_file(generation / "SHA256SUMS"):
        raise BuildError("CURRENT SHA256SUMS binding mismatch")
    print(f"PASS: v0.11 USB one-shot validated at {generation}")
    print(f"PAYLOAD_DIR={generation / PAYLOAD_DIRECTORY}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build")
    subparsers.add_parser("validate")
    return result


def main() -> int:
    try:
        if sys.version_info < (3, 10):
            raise BuildError("Python 3.10 or newer is required")
        arguments = parser().parse_args()
        if arguments.command == "build":
            command_build()
        else:
            command_validate()
        return 0
    except (BuildError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 65


if __name__ == "__main__":
    raise SystemExit(main())
