#!/usr/bin/env python3
"""Build and validate the immutable R46H v0.13 p2 one-shot payload."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import subprocess
import sys
import tarfile
import uuid


REPO = Path(__file__).resolve().parents[2]
CACHE_PARENT = REPO / "mainline/out/.cache"
CACHE_ROOT = CACHE_PARENT / "r46h-v13-mmc-one-shot-build"
RELEASE_ROOT = REPO / "mainline/out/r46h-v13-mmc-one-shot"
PACKAGE_TAR = REPO / "mainline/out/r46h-mainline-test-v0.13-mmc-init-observe.tar.gz"
PACKAGE_NAME = "r46h-mainline-test-v0.13-mmc-init-observe"
PACKAGE_SIZE = 33_262_229
PACKAGE_SHA256 = "9b8b6a011c0c965058cfe9a3b8e7a05f110097efafe1e725dc763d7a13c1bb2f"
PACKAGE_SOURCE_COMMIT = "87b3d0954644409f03469b0cfcd33567ec8757ac"
PACKAGE_SOURCE_SNAPSHOT = (
    "cdc888bc11cfaccdb00f04f384c12e4124726ca3f92d06a31e409dea3e9280ab"
)
PACKAGE_MODULE_TREE = (
    "8df4eb1e57722d15614a7f942b8752a76196c8333d6f7ad6ab3aa5f76e0d78c7"
)
BUILD_ID = "v0.13-mmc-init-observe"
KERNEL_RELEASE = "6.12.99-r46h-mainline-v0.13-mmc-init-observe"
RUNNING_RELEASE = "6.12.99-r46h-mainline-v0.10-adc-full-range"
ROOT_PARTUUID = "c9f931c9-02"
BOOT_PARTUUID = "c9f931c9-01"
IMAGE_SIZE = 41_570_816
IMAGE_SHA256 = "cca1a3d958a2edc713f6dcfeebbac157224fdae44015b2b6356ac02db84b837f"
DTB_SIZE = 49_518
DTB_SHA256 = "d1b035ee09ed0c44ccad62304f0c588d302c6055f634e65390850163cceba8ad"
PAYLOAD_ID = "r46h-v13-mmc-init-one-shot-v1"
PAYLOAD_DIRECTORY = "r46h-mmc-init-one-shot-v0.13"
TARGET_PARENT = "/var/lib/r46h-mmc-init-one-shot"
TARGET_DIRECTORY = f"{TARGET_PARENT}/{BUILD_ID}"
SOURCE_DATE_EPOCH = 1_785_369_600
ARCHIVE_NAME = "r46h-v13-mmc-init-one-shot.tar.gz"
SOURCE_PATHS = (
    "mainline/scripts/build-v13-mmc-one-shot.py",
    "mainline/tests/test-v13-mmc-one-shot.py",
)
PAYLOAD_DATA_NAMES = (
    "IMAGE.GZ",
    "PAYLOAD.json",
    "R46H.DTB",
    "RECEIPT",
    "UBOOT-CMDS.txt",
    "install.sh",
    "remove.sh",
)
PAYLOAD_NAMES = {*PAYLOAD_DATA_NAMES, "PAYLOAD.COMPLETE", "SHA256SUMS"}
RELEASE_NAMES = {
    ARCHIVE_NAME,
    f"{ARCHIVE_NAME}.sha256",
    "BUILD-RECEIPT.json",
    "SOURCE-MANIFEST.json",
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


def require_clean_source() -> tuple[str, str, bytes]:
    status = git_bytes(
        ["status", "--porcelain=v1", "--untracked-files=all", "--", *SOURCE_PATHS]
    )
    if status:
        raise BuildError("v0.13 one-shot source scope is not committed and clean")
    commit = git_bytes(["rev-parse", "--verify", "HEAD^{commit}"]).decode().strip()
    tree = git_bytes(["rev-parse", "--verify", "HEAD^{tree}"]).decode().strip()
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
    return commit, tree, manifest


def require_regular_file(path: Path, expected_size: int, expected_sha256: str) -> None:
    metadata = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size != expected_size
        or sha256_file(path) != expected_sha256
    ):
        raise BuildError(f"file identity mismatch: {path}")


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


def read_exact_member(archive: tarfile.TarFile, name: str) -> bytes:
    matches = [member for member in archive.getmembers() if member.name == name]
    if len(matches) != 1 or not matches[0].isfile():
        raise BuildError(f"package member identity mismatch: {name}")
    stream = archive.extractfile(matches[0])
    if stream is None:
        raise BuildError(f"cannot read package member: {name}")
    return stream.read()


def read_package(path: Path = PACKAGE_TAR) -> tuple[bytes, bytes]:
    require_regular_file(path, PACKAGE_SIZE, PACKAGE_SHA256)
    prefix = f"{PACKAGE_NAME}/"
    with tarfile.open(path, "r:gz") as archive:
        image = read_exact_member(archive, prefix + "boot/Image.mainline-test")
        dtb = read_exact_member(
            archive, prefix + "boot/rk3326-r46h-mainline-test.dtb"
        )
        manifest = read_exact_member(archive, prefix + "MANIFEST").decode()
    expected_manifest = {
        "build_id": BUILD_ID,
        "kernel_release": KERNEL_RELEASE,
        "module_tree_sha256": PACKAGE_MODULE_TREE,
        "root_spec": f"PARTUUID={ROOT_PARTUUID}",
        "source_git_commit": PACKAGE_SOURCE_COMMIT,
        "source_snapshot_sha256": PACKAGE_SOURCE_SNAPSHOT,
    }
    observed: dict[str, str] = {}
    for line in manifest.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key in observed:
            raise BuildError("canonical package MANIFEST is malformed")
        observed[key] = value
    for key, value in expected_manifest.items():
        if observed.get(key) != value:
            raise BuildError(f"canonical package MANIFEST {key} mismatch")
    if len(image) != IMAGE_SIZE or sha256_bytes(image) != IMAGE_SHA256:
        raise BuildError("canonical package Image mismatch")
    if len(dtb) != DTB_SIZE or sha256_bytes(dtb) != DTB_SHA256:
        raise BuildError("canonical package DTB mismatch")
    return image, dtb


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


def render_uboot_commands(compressed_size: int) -> bytes:
    path = TARGET_DIRECTORY
    return f"""# R46H {BUILD_ID} p2 one-shot; active p1 and environment remain unchanged.
mmc dev 1
setenv loadaddr 0x02000000
setenv dtb_loadaddr 0x01f00000
setenv kernel_comp_addr 0x10000000
setenv bootargs \"root=PARTUUID={ROOT_PARTUUID} rootwait ro rootflags=noload init=/bin/bash net.ifnames=0 console=ttyS2,115200n8 earlycon loglevel=7 ignore_loglevel plymouth.enable=0 clk_ignore_unused pd_ignore_unused\"
if ext4load mmc 1:2 ${{kernel_comp_addr}} {path}/IMAGE.GZ; then
  if itest ${{filesize}} -eq {compressed_size:#x}; then
    if unzip ${{kernel_comp_addr}} ${{loadaddr}} 0x03000000; then
      if itest ${{filesize}} -eq {IMAGE_SIZE:#x}; then
        if ext4load mmc 1:2 ${{dtb_loadaddr}} {path}/R46H.DTB; then
          if itest ${{filesize}} -eq {DTB_SIZE:#x}; then
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
""".encode()


def render_install_script(hashes: dict[str, str]) -> bytes:
    template = r'''#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG

readonly PAYLOAD_ID=@PAYLOAD_ID@
readonly EXPECTED_RELEASE=@RUNNING_RELEASE@
readonly ROOT_PARTUUID=@ROOT_PARTUUID@
readonly BOOT_PARTUUID=@BOOT_PARTUUID@
readonly PAYLOAD_DIR=/run/@PAYLOAD_DIRECTORY@
readonly TARGET_PARENT=@TARGET_PARENT@
readonly TARGET_DIR=@TARGET_DIRECTORY@
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

boot_partition_must_not_be_writable() {
  local partuuid options
  while read -r partuuid options; do
    if [[ "$partuuid" == "$BOOT_PARTUUID" && ",$options," == *,rw,* ]]; then
      die 'BOOT partition is mounted writable'
    fi
  done < <(findmnt -rn -o PARTUUID,OPTIONS)
}

cleanup_stage() {
  if [[ -n "${stage:-}" && -d "$stage" && ! -L "$stage" ]]; then
    rm -f -- "$stage/IMAGE.GZ" "$stage/R46H.DTB" "$stage/RECEIPT" \
      "$stage/REMOVE.sh" "$stage/UBOOT-CMDS.txt"
    rmdir -- "$stage" 2>/dev/null || true
  fi
}

(( EUID == 0 )) || die 'root is required'
[[ $# == 0 ]] || die 'this installer accepts no arguments'
[[ "${BASH_SOURCE[0]}" == "$PAYLOAD_DIR/install.sh" ]] || die "bind payload at $PAYLOAD_DIR"
[[ -d "$PAYLOAD_DIR" && ! -L "$PAYLOAD_DIR" ]] || die 'unsafe payload directory'
[[ "$(stat -c '%u:%g:%a' "$PAYLOAD_DIR")" == 0:0:700 ]] || die 'unsafe payload ownership or mode'
payload_members=$(find "$PAYLOAD_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort)
[[ "$payload_members" == $'IMAGE.GZ\nPAYLOAD.COMPLETE\nPAYLOAD.json\nR46H.DTB\nRECEIPT\nSHA256SUMS\nUBOOT-CMDS.txt\ninstall.sh\nremove.sh' ]] || die 'unexpected payload member set'
for member in IMAGE.GZ PAYLOAD.COMPLETE PAYLOAD.json R46H.DTB RECEIPT SHA256SUMS UBOOT-CMDS.txt install.sh remove.sh; do
  candidate=$PAYLOAD_DIR/$member
  [[ -f "$candidate" && ! -L "$candidate" ]] || die "unsafe payload member: $member"
  [[ "$(stat -c '%u:%g:%h' "$candidate")" == 0:0:1 ]] || die "unsafe payload member identity: $member"
done
[[ "$(stat -c '%a' "$PAYLOAD_DIR/install.sh")" == 700 ]] || die 'unsafe installer mode'
[[ "$(stat -c '%a' "$PAYLOAD_DIR/remove.sh")" == 700 ]] || die 'unsafe remover mode'

cd "$PAYLOAD_DIR"
sha256sum -c SHA256SUMS
[[ "$(<PAYLOAD.COMPLETE)" == "sha256sums_sha256=$(sha256sum SHA256SUMS | awk '{print $1}')" ]] || die 'payload completion marker mismatch'
[[ "$(sha256sum IMAGE.GZ | awk '{print $1}')" == @IMAGE_GZ_SHA256@ ]] || die 'compressed Image mismatch'
[[ "$(sha256sum R46H.DTB | awk '{print $1}')" == @DTB_SHA256@ ]] || die 'DTB mismatch'
[[ "$(sha256sum UBOOT-CMDS.txt | awk '{print $1}')" == @UBOOT_SHA256@ ]] || die 'U-Boot transcript mismatch'
[[ "$(sha256sum RECEIPT | awk '{print $1}')" == @RECEIPT_SHA256@ ]] || die 'receipt mismatch'
[[ "$(sha256sum remove.sh | awk '{print $1}')" == @REMOVE_SHA256@ ]] || die 'remover mismatch'

[[ "$(uname -r)" == "$EXPECTED_RELEASE" ]] || die 'install from the persistent v0.10 boot'
[[ "$(findmnt -rn -o PARTUUID /)" == "$ROOT_PARTUUID" ]] || die 'unexpected root partition'
[[ "$(findmnt -rn -o FSTYPE /)" == ext4 ]] || die 'root is not ext4'
[[ ",$(findmnt -rn -o OPTIONS /)," == *,rw,* ]] || die 'root is not writable'
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem already reports errors'
[[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd has failed units'
boot_partition_must_not_be_writable

if [[ -e "$TARGET_PARENT" || -L "$TARGET_PARENT" ]]; then
  [[ -d "$TARGET_PARENT" && ! -L "$TARGET_PARENT" ]] || die 'unsafe target parent'
else
  install -d -o root -g root -m 0700 "$TARGET_PARENT"
fi
[[ "$(stat -c '%u:%g:%a' "$TARGET_PARENT")" == 0:0:700 ]] || die 'unsafe target parent ownership or mode'
[[ ! -e "$TARGET_DIR" && ! -L "$TARGET_DIR" ]] || die 'versioned target already exists'
stage=$TARGET_PARENT/.stage-@BUILD_ID@.$$
[[ ! -e "$stage" && ! -L "$stage" ]] || die 'target stage already exists'
install -d -o root -g root -m 0700 "$stage"
trap cleanup_stage EXIT
install -o root -g root -m 0600 IMAGE.GZ "$stage/IMAGE.GZ"
install -o root -g root -m 0600 R46H.DTB "$stage/R46H.DTB"
install -o root -g root -m 0600 RECEIPT "$stage/RECEIPT"
install -o root -g root -m 0700 remove.sh "$stage/REMOVE.sh"
install -o root -g root -m 0600 UBOOT-CMDS.txt "$stage/UBOOT-CMDS.txt"
[[ "$(sha256sum "$stage/IMAGE.GZ" | awk '{print $1}')" == @IMAGE_GZ_SHA256@ ]] || die 'staged Image mismatch'
[[ "$(sha256sum "$stage/R46H.DTB" | awk '{print $1}')" == @DTB_SHA256@ ]] || die 'staged DTB mismatch'
[[ "$(sha256sum "$stage/UBOOT-CMDS.txt" | awk '{print $1}')" == @UBOOT_SHA256@ ]] || die 'staged U-Boot transcript mismatch'
[[ "$(sha256sum "$stage/RECEIPT" | awk '{print $1}')" == @RECEIPT_SHA256@ ]] || die 'staged receipt mismatch'
[[ "$(sha256sum "$stage/REMOVE.sh" | awk '{print $1}')" == @REMOVE_SHA256@ ]] || die 'staged remover mismatch'
boot_partition_must_not_be_writable
mv -T --no-clobber -- "$stage" "$TARGET_DIR"
stage=
sync
trap - EXIT

printf 'PASS: %s staged at %s; active BOOT was not modified.\n' "$PAYLOAD_ID" "$TARGET_DIR"
printf 'NEXT=poweroff-then-use-UBOOT-CMDS.txt-for-one-attended-cold-boot\n'
'''
    replacements = {
        "@PAYLOAD_ID@": PAYLOAD_ID,
        "@RUNNING_RELEASE@": RUNNING_RELEASE,
        "@ROOT_PARTUUID@": ROOT_PARTUUID,
        "@BOOT_PARTUUID@": BOOT_PARTUUID,
        "@PAYLOAD_DIRECTORY@": PAYLOAD_DIRECTORY,
        "@TARGET_PARENT@": TARGET_PARENT,
        "@TARGET_DIRECTORY@": TARGET_DIRECTORY,
        "@BUILD_ID@": BUILD_ID,
        "@IMAGE_GZ_SHA256@": hashes["IMAGE.GZ"],
        "@DTB_SHA256@": hashes["R46H.DTB"],
        "@UBOOT_SHA256@": hashes["UBOOT-CMDS.txt"],
        "@RECEIPT_SHA256@": hashes["RECEIPT"],
        "@REMOVE_SHA256@": hashes["remove.sh"],
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    if "@" in template:
        raise BuildError("unresolved install-script template token")
    return template.encode()


def render_remove_script(hashes: dict[str, str]) -> bytes:
    template = r'''#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG

readonly EXPECTED_RELEASE=@RUNNING_RELEASE@
readonly ROOT_PARTUUID=@ROOT_PARTUUID@
readonly BOOT_PARTUUID=@BOOT_PARTUUID@
readonly TARGET_PARENT=@TARGET_PARENT@
readonly TARGET_DIR=@TARGET_DIRECTORY@
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

boot_partition_must_not_be_writable() {
  local partuuid options
  while read -r partuuid options; do
    if [[ "$partuuid" == "$BOOT_PARTUUID" && ",$options," == *,rw,* ]]; then
      die 'BOOT partition is mounted writable'
    fi
  done < <(findmnt -rn -o PARTUUID,OPTIONS)
}

(( EUID == 0 )) || die 'root is required'
[[ $# == 0 ]] || die 'this remover accepts no arguments'
[[ "${BASH_SOURCE[0]}" == "$TARGET_DIR/REMOVE.sh" ]] || die 'run the installed guarded remover'
[[ "$(uname -r)" == "$EXPECTED_RELEASE" ]] || die 'remove only from the persistent v0.10 boot'
[[ "$(findmnt -rn -o PARTUUID /)" == "$ROOT_PARTUUID" ]] || die 'unexpected root partition'
[[ "$(findmnt -rn -o FSTYPE /)" == ext4 ]] || die 'root is not ext4'
[[ ",$(findmnt -rn -o OPTIONS /)," == *,rw,* ]] || die 'root is not writable'
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem reports errors'
boot_partition_must_not_be_writable
[[ -d "$TARGET_PARENT" && ! -L "$TARGET_PARENT" ]] || die 'unsafe target parent'
[[ "$(stat -c '%u:%g:%a' "$TARGET_PARENT")" == 0:0:700 ]] || die 'unsafe target parent ownership or mode'
[[ -d "$TARGET_DIR" && ! -L "$TARGET_DIR" ]] || die 'versioned target is missing or unsafe'
members=$(find "$TARGET_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort)
[[ "$members" == $'IMAGE.GZ\nR46H.DTB\nRECEIPT\nREMOVE.sh\nUBOOT-CMDS.txt' ]] || die 'unexpected installed member set'
for member in IMAGE.GZ R46H.DTB RECEIPT REMOVE.sh UBOOT-CMDS.txt; do
  candidate=$TARGET_DIR/$member
  [[ -f "$candidate" && ! -L "$candidate" ]] || die "unsafe installed member: $member"
  [[ "$(stat -c '%u:%g:%h' "$candidate")" == 0:0:1 ]] || die "unsafe installed identity: $member"
done
[[ "$(sha256sum "$TARGET_DIR/IMAGE.GZ" | awk '{print $1}')" == @IMAGE_GZ_SHA256@ ]] || die 'installed Image mismatch'
[[ "$(sha256sum "$TARGET_DIR/R46H.DTB" | awk '{print $1}')" == @DTB_SHA256@ ]] || die 'installed DTB mismatch'
[[ "$(sha256sum "$TARGET_DIR/UBOOT-CMDS.txt" | awk '{print $1}')" == @UBOOT_SHA256@ ]] || die 'installed U-Boot transcript mismatch'
[[ "$(sha256sum "$TARGET_DIR/RECEIPT" | awk '{print $1}')" == @RECEIPT_SHA256@ ]] || die 'installed receipt mismatch'

tombstone=$TARGET_PARENT/.remove-@BUILD_ID@.$$
[[ ! -e "$tombstone" && ! -L "$tombstone" ]] || die 'removal tombstone already exists'
mv -T --no-clobber -- "$TARGET_DIR" "$tombstone"
cd /
rm -f -- "$tombstone/IMAGE.GZ" "$tombstone/R46H.DTB" "$tombstone/RECEIPT" \
  "$tombstone/REMOVE.sh" "$tombstone/UBOOT-CMDS.txt"
rmdir -- "$tombstone"
sync
printf 'PASS: removed exact v0.13 MMC one-shot staging; active BOOT was not modified.\n'
'''
    replacements = {
        "@RUNNING_RELEASE@": RUNNING_RELEASE,
        "@ROOT_PARTUUID@": ROOT_PARTUUID,
        "@BOOT_PARTUUID@": BOOT_PARTUUID,
        "@TARGET_PARENT@": TARGET_PARENT,
        "@TARGET_DIRECTORY@": TARGET_DIRECTORY,
        "@BUILD_ID@": BUILD_ID,
        "@IMAGE_GZ_SHA256@": hashes["IMAGE.GZ"],
        "@DTB_SHA256@": hashes["R46H.DTB"],
        "@UBOOT_SHA256@": hashes["UBOOT-CMDS.txt"],
        "@RECEIPT_SHA256@": hashes["RECEIPT"],
    }
    for key, value in replacements.items():
        template = template.replace(key, value)
    if "@" in template:
        raise BuildError("unresolved remove-script template token")
    return template.encode()


def payload_files(image: bytes, dtb: bytes) -> dict[str, bytes]:
    compressed = deterministic_gzip(image)
    commands = render_uboot_commands(len(compressed))
    receipt = (
        f"payload_id={PAYLOAD_ID}\n"
        f"build_id={BUILD_ID}\n"
        f"kernel_release={KERNEL_RELEASE}\n"
        f"package_sha256={PACKAGE_SHA256}\n"
        f"image_sha256={IMAGE_SHA256}\n"
        f"dtb_sha256={DTB_SHA256}\n"
    ).encode()
    files: dict[str, bytes] = {
        "IMAGE.GZ": compressed,
        "R46H.DTB": dtb,
        "RECEIPT": receipt,
        "UBOOT-CMDS.txt": commands,
    }
    hashes = {name: sha256_bytes(value) for name, value in files.items()}
    remover = render_remove_script(hashes)
    files["remove.sh"] = remover
    hashes["remove.sh"] = sha256_bytes(remover)
    files["install.sh"] = render_install_script(hashes)
    files["PAYLOAD.json"] = canonical_json(
        {
            "boot_source": "mmc1-p2-ext4-one-shot",
            "build_id": BUILD_ID,
            "files": {
                name: {"sha256": sha256_bytes(value), "size": len(value)}
                for name, value in sorted(files.items())
            },
            "format_version": 1,
            "kernel_release": KERNEL_RELEASE,
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
                "persistent_environment_changed": False,
                "target_partition": "p2",
            },
        }
    )
    sums = "".join(
        f"{sha256_bytes(value)}  {name}\n"
        for name, value in sorted(files.items())
    ).encode()
    files["SHA256SUMS"] = sums
    files["PAYLOAD.COMPLETE"] = (
        f"sha256sums_sha256={sha256_bytes(sums)}\n".encode()
    )
    if set(files) != PAYLOAD_NAMES:
        raise BuildError("internal payload member set mismatch")
    return files


def deterministic_archive(files: dict[str, bytes]) -> bytes:
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        directory = tarfile.TarInfo(PAYLOAD_DIRECTORY + "/")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o700
        directory.uid = directory.gid = 0
        directory.uname = directory.gname = "root"
        directory.mtime = SOURCE_DATE_EPOCH
        archive.addfile(directory)
        for name, payload in sorted(files.items()):
            member = tarfile.TarInfo(f"{PAYLOAD_DIRECTORY}/{name}")
            member.mode = 0o700 if name in {"install.sh", "remove.sh"} else 0o600
            member.uid = member.gid = 0
            member.uname = member.gname = "root"
            member.mtime = SOURCE_DATE_EPOCH
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
    with io.BytesIO() as compressed:
        with gzip.GzipFile(
            filename="", mode="wb", compresslevel=9, fileobj=compressed, mtime=0
        ) as stream:
            stream.write(tar_buffer.getvalue())
        return compressed.getvalue()


def validate_archive_bytes(archive_bytes: bytes) -> dict[str, bytes]:
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        members = archive.getmembers()
        expected_names = {PAYLOAD_DIRECTORY} | {
            f"{PAYLOAD_DIRECTORY}/{name}" for name in PAYLOAD_NAMES
        }
        observed_names = {member.name for member in members}
        if len(members) != len(observed_names) or observed_names != expected_names:
            raise BuildError("one-shot archive member set mismatch")
        result: dict[str, bytes] = {}
        for member in members:
            pure = PurePosixPath(member.name)
            if pure.is_absolute() or ".." in pure.parts or member.issym() or member.islnk():
                raise BuildError(f"unsafe one-shot archive member: {member.name}")
            if member.name == PAYLOAD_DIRECTORY:
                if not member.isdir() or member.mode != 0o700:
                    raise BuildError("one-shot archive directory identity mismatch")
                continue
            if not member.isfile():
                raise BuildError(f"non-file one-shot archive member: {member.name}")
            short_name = pure.name
            expected_mode = 0o700 if short_name in {"install.sh", "remove.sh"} else 0o600
            if member.uid != 0 or member.gid != 0 or member.mode != expected_mode:
                raise BuildError(f"one-shot archive metadata mismatch: {member.name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise BuildError(f"cannot read one-shot archive member: {member.name}")
            result[short_name] = stream.read()
    if set(result) != PAYLOAD_NAMES:
        raise BuildError("one-shot payload member set mismatch")
    sums = "".join(
        f"{sha256_bytes(value)}  {name}\n"
        for name, value in sorted(result.items())
        if name not in {"PAYLOAD.COMPLETE", "SHA256SUMS"}
    ).encode()
    if result["SHA256SUMS"] != sums:
        raise BuildError("one-shot payload SHA256SUMS mismatch")
    if result["PAYLOAD.COMPLETE"] != (
        f"sha256sums_sha256={sha256_bytes(sums)}\n".encode()
    ):
        raise BuildError("one-shot payload completion marker mismatch")
    try:
        raw_image = gzip.decompress(result["IMAGE.GZ"])
    except (OSError, EOFError) as exc:
        raise BuildError(f"one-shot compressed Image is invalid: {exc}") from exc
    if len(raw_image) != IMAGE_SIZE or sha256_bytes(raw_image) != IMAGE_SHA256:
        raise BuildError("one-shot raw Image mismatch")
    if len(result["R46H.DTB"]) != DTB_SIZE or sha256_bytes(result["R46H.DTB"]) != DTB_SHA256:
        raise BuildError("one-shot DTB mismatch")
    return result


def write_new(path: Path, payload: bytes, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


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


def validate_source_manifest(source: dict[str, object]) -> None:
    if set(source) != {"file_count", "files", "format_version", "git_commit", "git_tree"}:
        raise BuildError("v0.13 one-shot source manifest key set mismatch")
    if source.get("format_version") != 1 or source.get("file_count") != len(SOURCE_PATHS):
        raise BuildError("v0.13 one-shot source manifest shape mismatch")
    commit = source.get("git_commit")
    tree = source.get("git_tree")
    if not isinstance(commit, str) or len(commit) != 40 or not isinstance(tree, str):
        raise BuildError("v0.13 one-shot source Git identity is malformed")
    observed_tree = git_bytes(["rev-parse", "--verify", f"{commit}^{{tree}}"]).decode().strip()
    if observed_tree != tree:
        raise BuildError("v0.13 one-shot source Git tree mismatch")
    entries = source.get("files")
    if not isinstance(entries, list) or len(entries) != len(SOURCE_PATHS):
        raise BuildError("v0.13 one-shot source manifest entries are malformed")
    for relative, entry in zip(SOURCE_PATHS, entries, strict=True):
        if not isinstance(entry, dict):
            raise BuildError(f"v0.13 one-shot source entry is malformed: {relative}")
        tree_line = git_bytes(["ls-tree", commit, "--", relative]).decode().strip()
        fields = tree_line.split(None, 3)
        blob = git_bytes(["cat-file", "blob", f"{commit}:{relative}"])
        expected = {
            "git_mode": fields[0] if len(fields) == 4 else "",
            "path": relative,
            "sha256": sha256_bytes(blob),
            "size": len(blob),
        }
        if (
            len(fields) != 4
            or fields[1] != "blob"
            or fields[3] != relative
            or entry != expected
            or (REPO / relative).read_bytes() != blob
        ):
            raise BuildError(f"v0.13 one-shot source blob mismatch: {relative}")


def validate_release(root: Path = RELEASE_ROOT) -> None:
    require_real_directory(root)
    members = {entry.name: entry for entry in root.iterdir()}
    if set(members) != RELEASE_NAMES:
        raise BuildError("v0.13 one-shot release member set mismatch")
    for name, candidate in members.items():
        item = candidate.lstat()
        if candidate.is_symlink() or not stat.S_ISREG(item.st_mode) or item.st_nlink != 1:
            raise BuildError(f"unsafe v0.13 one-shot release member: {name}")
    archive_path = root / ARCHIVE_NAME
    archive = archive_path.read_bytes()
    payload = validate_archive_bytes(archive)
    archive_hash = sha256_bytes(archive)
    sidecar = f"{archive_hash}  {ARCHIVE_NAME}\n".encode()
    if (root / f"{ARCHIVE_NAME}.sha256").read_bytes() != sidecar:
        raise BuildError("v0.13 one-shot archive sidecar mismatch")
    source = exact_json(root / "SOURCE-MANIFEST.json")
    receipt = exact_json(root / "BUILD-RECEIPT.json")
    validate_source_manifest(source)
    if receipt != {
        "archive": {
            "name": ARCHIVE_NAME,
            "sha256": archive_hash,
            "size": len(archive),
        },
        "format_version": 1,
        "package": {
            "sha256": PACKAGE_SHA256,
            "size": PACKAGE_SIZE,
            "source_git_commit": PACKAGE_SOURCE_COMMIT,
            "source_snapshot_sha256": PACKAGE_SOURCE_SNAPSHOT,
        },
        "payload": {
            "compressed_image_sha256": sha256_bytes(payload["IMAGE.GZ"]),
            "payload_sha256sums_sha256": sha256_bytes(payload["SHA256SUMS"]),
        },
        "source": {
            "git_commit": source.get("git_commit"),
            "git_tree": source.get("git_tree"),
            "manifest_sha256": sha256_file(root / "SOURCE-MANIFEST.json"),
        },
    }:
        raise BuildError("v0.13 one-shot build receipt mismatch")


def command_build() -> None:
    commit, tree, source_manifest = require_clean_source()
    image, dtb = read_package()
    files = payload_files(image, dtb)
    archive = deterministic_archive(files)
    if deterministic_archive(files) != archive:
        raise BuildError("v0.13 one-shot archive is not reproducible")
    payload = validate_archive_bytes(archive)
    cache_parent = require_real_directory(CACHE_PARENT)
    CACHE_ROOT.mkdir(exist_ok=True, mode=0o700)
    cache_root = require_real_directory(CACHE_ROOT, cache_parent.st_dev)
    work = CACHE_ROOT / f"work-{uuid.uuid4().hex}"
    work.mkdir(mode=0o700)
    require_real_directory(work, cache_root.st_dev)
    stage = work / "release"
    stage.mkdir(mode=0o700)
    try:
        archive_hash = sha256_bytes(archive)
        write_new(stage / ARCHIVE_NAME, archive)
        write_new(
            stage / f"{ARCHIVE_NAME}.sha256",
            f"{archive_hash}  {ARCHIVE_NAME}\n".encode(),
        )
        write_new(stage / "SOURCE-MANIFEST.json", source_manifest)
        receipt = {
            "archive": {
                "name": ARCHIVE_NAME,
                "sha256": archive_hash,
                "size": len(archive),
            },
            "format_version": 1,
            "package": {
                "sha256": PACKAGE_SHA256,
                "size": PACKAGE_SIZE,
                "source_git_commit": PACKAGE_SOURCE_COMMIT,
                "source_snapshot_sha256": PACKAGE_SOURCE_SNAPSHOT,
            },
            "payload": {
                "compressed_image_sha256": sha256_bytes(payload["IMAGE.GZ"]),
                "payload_sha256sums_sha256": sha256_bytes(payload["SHA256SUMS"]),
            },
            "source": {
                "git_commit": commit,
                "git_tree": tree,
                "manifest_sha256": sha256_bytes(source_manifest),
            },
        }
        write_new(stage / "BUILD-RECEIPT.json", canonical_json(receipt))
        validate_release(stage)
        if RELEASE_ROOT.exists() or RELEASE_ROOT.is_symlink():
            raise BuildError("v0.13 one-shot release already exists")
        os.rename(stage, RELEASE_ROOT)
        validate_release()
        print(f"PASS: immutable v0.13 MMC one-shot published at {RELEASE_ROOT}")
        print(f"ARCHIVE={RELEASE_ROOT / ARCHIVE_NAME}")
        print(f"ARCHIVE_SIZE={len(archive)}")
        print(f"ARCHIVE_SHA256={archive_hash}")
        print(f"IMAGE_GZ_SIZE={len(payload['IMAGE.GZ'])}")
        print(f"IMAGE_GZ_SHA256={sha256_bytes(payload['IMAGE.GZ'])}")
        print(f"UBOOT_CMDS_SIZE={len(payload['UBOOT-CMDS.txt'])}")
    finally:
        if work.exists():
            shutil.rmtree(work)
        if CACHE_ROOT.exists() and not any(CACHE_ROOT.iterdir()):
            CACHE_ROOT.rmdir()


def command_validate() -> None:
    validate_release()
    receipt = exact_json(RELEASE_ROOT / "BUILD-RECEIPT.json")
    print(f"PASS: v0.13 MMC one-shot validated at {RELEASE_ROOT}")
    print(f"ARCHIVE_SHA256={receipt['archive']['sha256']}")


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
    except (BuildError, OSError, ValueError, tarfile.TarError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 65


if __name__ == "__main__":
    raise SystemExit(main())
