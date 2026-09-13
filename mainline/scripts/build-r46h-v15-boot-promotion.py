#!/usr/bin/env python3
"""Build the provenance-bound R46H v0.15 BOOT promotion control payload."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile


REPO = Path(__file__).resolve().parents[2]
CACHE_ROOT = REPO / "mainline/out/.cache/r46h-v15-boot-promotion-build"
RELEASE_ROOT = REPO / "mainline/out/r46h-v15-boot-promotion"
PAYLOAD_ID = "r46h-v15-boot-promotion-v0.1"
ARCHIVE_NAME = f"{PAYLOAD_ID}.tar.gz"
SOURCE_DATE_EPOCH = 1_785_369_600
KERNEL_BUNDLE = REPO / "mainline/out/r46h-mainline-test-v0.15-gaming-product.tar.gz"
KERNEL_BUNDLE_SIZE = 33_268_548
KERNEL_BUNDLE_SHA256 = (
    "748d81cc0e8b9bf353430db1f4ee358bf09dee1d32db85a855961368b58d3fad"
)
KERNEL_ROOT = "r46h-mainline-test-v0.15-gaming-product"
KERNEL_IMAGE_MEMBER = f"{KERNEL_ROOT}/boot/Image.mainline-test"
KERNEL_DTB_MEMBER = f"{KERNEL_ROOT}/boot/rk3326-r46h-mainline-test.dtb"
KERNEL_MANIFEST_MEMBER = f"{KERNEL_ROOT}/MANIFEST"
KERNEL_IMAGE_SIZE = 41_570_816
KERNEL_IMAGE_SHA256 = (
    "956ab3d5a2e53afbfe964ae75850e8591b44c093b9779867b31149b7b591f68f"
)
KERNEL_DTB_SIZE = 49_518
KERNEL_DTB_SHA256 = (
    "4d6d4ebad3b98600b6e9a38df4ca82230335558497a9e15dd0e81ca60e304b61"
)
KERNEL_MODULE_TREE_SHA256 = (
    "bd53fad3997ced39a15c69dbd70525106e891e5529dcef73bbbcfb699aafc291"
)
COMPRESSED_IMAGE_SIZE = 14_925_282
COMPRESSED_IMAGE_SHA256 = (
    "9a4f58ed03aab19d5472c5ff41f99383dee90c653dadebcee360f2323dc653bf"
)
BOOT_SIZE = 1_403
BOOT_SHA256 = "f41ab69f17cd22fb22446e390c46325d4e536cf8dee1bd9ab85682297dca1ac8"
FALLBACK_BUNDLE = REPO / "mainline/out/r46h-mainline-test-v0.10-adc-full-range.tar.gz"
FALLBACK_BUNDLE_SIZE = 33_258_814
FALLBACK_BUNDLE_SHA256 = (
    "c4350520f7ad33ecf7b50f67c42985e2ce26c1c38d050ad50601c3538cebc780"
)
FALLBACK_PACKAGE_ROOT = "r46h-mainline-test-v0.10-adc-full-range"
FALLBACK_RELEASE = "6.12.99-r46h-mainline-v0.10-adc-full-range"
FALLBACK_MANIFEST_MEMBER = f"{FALLBACK_PACKAGE_ROOT}/MANIFEST"
FALLBACK_SUMS_MEMBER = f"{FALLBACK_PACKAGE_ROOT}/SHA256SUMS"
FALLBACK_MODULE_PREFIX = f"{FALLBACK_PACKAGE_ROOT}/rootfs/lib/modules/{FALLBACK_RELEASE}"
FALLBACK_MODULE_TREE_SHA256 = (
    "a70796c050de93c4c212180addf54a17efe7732d355db2b52d0bfcab6c56cc16"
)
FALLBACK_MODULE_COUNT = 1_276
FALLBACK_MODULE_FILE_COUNT = 1_290
FALLBACK_MODULE_DIR_COUNT = 395
FALLBACK_ARCHIVE_MEMBER_COUNT = 1_695
SECONDARY_FALLBACK_RELEASE = "6.12.99-r46h-mainline-v0.8-bootloader-handoff"
SECONDARY_FALLBACK_MODULE_TREE_SHA256 = (
    "2ec532a3d3c6833538bd4ffd284122afa30bea0945e832f57be481527986f210"
)
PRODUCT_ROOTFS_FILES = REPO / "mainline/out/r46h-debian13-p2-gaming-v0.3/ROOTFS-FILES.sha256"
PRODUCT_ROOTFS_FILES_SIZE = 2_352_005
PRODUCT_ROOTFS_FILES_SHA256 = (
    "cd4394311012f89c55a3321f93602c45a183b3c89b0ad29536aa44c99f9cbb22"
)
PRODUCT_ROOTFS_TREE = REPO / "mainline/out/r46h-debian13-p2-gaming-v0.3/ROOTFS-TREE.tsv"
PRODUCT_ROOTFS_TREE_SIZE = 1_610_315
PRODUCT_ROOTFS_TREE_SHA256 = (
    "4665f7f810007b5db2a5816a984ee6c6739d6c3c2dd0654af59b6e655b292158"
)
BASE_P1_SHA256 = "f50597d459a51bab509aae959267f77ade068d566751acb6cff888b012d3b4ed"
PREFIX_SHA256 = "3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3"
SOURCE_PATHS = (
    "docs/PROJECT-CONTEXT.md",
    "mainline/board/r46h/EXPERIMENT-STATUS.md",
    "mainline/bringup-tests/GAMING-PRODUCT.md",
    "mainline/gaming-product-boot-promotion/README.md",
    "mainline/gaming-product-boot-promotion/boot.ini.v0.15-gaming-product",
    "mainline/gaming-product-boot-promotion/complete-recovered-mmc-postflight.sh",
    "mainline/gaming-product-boot-promotion/fallback-modules.sh",
    "mainline/gaming-product-boot-promotion/install.sh",
    "mainline/gaming-product-boot-promotion/storage-health.sh",
    "mainline/gaming-product-boot-promotion/transaction.sh",
    "mainline/scripts/build-r46h-v15-boot-promotion.py",
    "mainline/tests/test-r46h-v15-boot-promotion.py",
)
PAYLOAD_MEMBERS = {
    "PAYLOAD-INFO.json",
    "PAYLOAD.COMPLETE",
    "SHA256SUMS",
    "fallback-modules.sh",
    "files",
    "files/Image.mainline-v0.15-gaming-product.gz",
    "files/boot.ini.v0.15-gaming-product",
    "files/r46h-mainline-test-v0.10-adc-full-range.tar.gz",
    "files/rk3326-r46h-mainline-v0.15-gaming-product.dtb",
    "install.sh",
    "storage-health.sh",
    "transaction.sh",
}
GENERATION_MEMBERS = {
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
        while block := handle.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_new(path: Path, payload: bytes, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


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
        raise BuildError("BOOT promotion source scope must be committed and clean")
    commit = git_bytes(["rev-parse", "--verify", "HEAD^{commit}"]).decode().strip()
    tree = git_bytes(["rev-parse", "--verify", "HEAD^{tree}"]).decode().strip()
    captured: dict[str, bytes] = {}
    entries: list[dict[str, object]] = []
    for relative in SOURCE_PATHS:
        live = REPO / relative
        metadata = require_regular(live, relative)
        tree_line = git_bytes(["ls-tree", "HEAD", "--", relative]).decode().strip()
        fields = tree_line.split(None, 3)
        if len(fields) != 4 or fields[1] != "blob" or fields[3] != relative:
            raise BuildError(f"source is not one committed blob: {relative}")
        payload = git_bytes(["cat-file", "blob", f"HEAD:{relative}"])
        if live.read_bytes() != payload:
            raise BuildError(f"live source differs from HEAD: {relative}")
        captured[relative] = payload
        entries.append(
            {
                "git_mode": fields[0],
                "path": relative,
                "sha256": sha256_bytes(payload),
                "size": metadata.st_size,
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


def verify_kernel_bundle(work: Path) -> dict[str, object]:
    metadata = require_regular(KERNEL_BUNDLE, "v0.15 kernel bundle")
    if metadata.st_size != KERNEL_BUNDLE_SIZE or sha256_file(KERNEL_BUNDLE) != KERNEL_BUNDLE_SHA256:
        raise BuildError("v0.15 kernel bundle identity mismatch")
    extracted_image = work / "Image"
    extracted_dtb = work / "R46H.DTB"
    with tarfile.open(KERNEL_BUNDLE, "r:gz") as archive:
        for name, size, expected_hash in (
            (KERNEL_IMAGE_MEMBER, KERNEL_IMAGE_SIZE, KERNEL_IMAGE_SHA256),
            (KERNEL_DTB_MEMBER, KERNEL_DTB_SIZE, KERNEL_DTB_SHA256),
            (KERNEL_MANIFEST_MEMBER, None, None),
        ):
            member = archive.getmember(name)
            if not member.isreg() or member.size != (size if size is not None else member.size):
                raise BuildError(f"unsafe or mismatched kernel bundle member: {name}")
            reader = archive.extractfile(member)
            if reader is None:
                raise BuildError(f"cannot read kernel bundle member: {name}")
            payload = reader.read()
            if len(payload) != member.size or (
                expected_hash is not None and sha256_bytes(payload) != expected_hash
            ):
                raise BuildError(f"kernel bundle member hash mismatch: {name}")
            if name == KERNEL_IMAGE_MEMBER:
                write_new(extracted_image, payload)
            elif name == KERNEL_DTB_MEMBER:
                write_new(extracted_dtb, payload)
            elif name == KERNEL_MANIFEST_MEMBER:
                manifest = payload.decode("utf-8")
                for line in (
                    "build_id=v0.15-gaming-product",
                    "kernel_release=6.12.99-r46h-mainline-v0.15-gaming-product",
                    f"module_tree_sha256={KERNEL_MODULE_TREE_SHA256}",
                    "root_spec=PARTUUID=c9f931c9-02",
                ):
                    if line not in manifest.splitlines():
                        raise BuildError(f"kernel manifest lacks {line}")
    compressed = work / "Image.gz"
    gzip_command = shutil.which("gzip")
    if not gzip_command:
        raise BuildError("gzip is unavailable")
    with compressed.open("xb") as output:
        result = subprocess.run(
            [gzip_command, "-n", "-9", "-c", str(extracted_image)],
            check=False,
            stdout=output,
            stderr=subprocess.PIPE,
        )
    if result.returncode != 0:
        raise BuildError(f"deterministic Image compression failed: {result.stderr.decode().strip()}")
    if compressed.stat().st_size != COMPRESSED_IMAGE_SIZE or sha256_file(compressed) != COMPRESSED_IMAGE_SHA256:
        raise BuildError("deterministic compressed Image identity mismatch")
    return {
        "bundle_sha256": KERNEL_BUNDLE_SHA256,
        "bundle_size": KERNEL_BUNDLE_SIZE,
        "compressed_image_sha256": COMPRESSED_IMAGE_SHA256,
        "compressed_image_size": COMPRESSED_IMAGE_SIZE,
        "dtb_sha256": KERNEL_DTB_SHA256,
        "dtb_size": KERNEL_DTB_SIZE,
        "image_sha256": KERNEL_IMAGE_SHA256,
        "image_size": KERNEL_IMAGE_SIZE,
        "module_tree_sha256": KERNEL_MODULE_TREE_SHA256,
    }


def verify_fallback_bundle() -> dict[str, object]:
    metadata = require_regular(FALLBACK_BUNDLE, "v0.10 fallback module bundle")
    if (
        metadata.st_size != FALLBACK_BUNDLE_SIZE
        or sha256_file(FALLBACK_BUNDLE) != FALLBACK_BUNDLE_SHA256
    ):
        raise BuildError("v0.10 fallback module bundle identity mismatch")
    with tarfile.open(FALLBACK_BUNDLE, "r:gz") as archive:
        members = archive.getmembers()
        if len(members) != FALLBACK_ARCHIVE_MEMBER_COUNT:
            raise BuildError("v0.10 fallback archive member count mismatch")
        if any(not (member.isdir() or member.isreg()) for member in members):
            raise BuildError("v0.10 fallback archive contains a link or special member")
        names = [member.name.rstrip("/") for member in members]
        if len(names) != len(set(names)) or any(
            not name
            or name.startswith("/")
            or name == ".."
            or "/../" in name
            or name.startswith("../")
            for name in names
        ):
            raise BuildError("v0.10 fallback archive has an unsafe or duplicate path")
        module_files = sorted(
            member.name
            for member in members
            if member.isreg() and member.name.startswith(f"{FALLBACK_MODULE_PREFIX}/")
        )
        module_dirs = [
            member.name
            for member in members
            if member.isdir()
            and (
                member.name.rstrip("/") == FALLBACK_MODULE_PREFIX
                or member.name.startswith(f"{FALLBACK_MODULE_PREFIX}/")
            )
        ]
        if (
            len(module_files) != FALLBACK_MODULE_FILE_COUNT
            or sum(name.endswith(".ko") for name in module_files) != FALLBACK_MODULE_COUNT
            or len(module_dirs) != FALLBACK_MODULE_DIR_COUNT
        ):
            raise BuildError("v0.10 fallback module tree count mismatch")
        manifest_reader = archive.extractfile(archive.getmember(FALLBACK_MANIFEST_MEMBER))
        sums_reader = archive.extractfile(archive.getmember(FALLBACK_SUMS_MEMBER))
        if manifest_reader is None or sums_reader is None:
            raise BuildError("cannot read v0.10 fallback metadata")
        manifest = manifest_reader.read().decode("utf-8")
        for line in (
            f"kernel_release={FALLBACK_RELEASE}",
            f"module_count={FALLBACK_MODULE_COUNT}",
            f"module_tree_sha256={FALLBACK_MODULE_TREE_SHA256}",
        ):
            if line not in manifest.splitlines():
                raise BuildError(f"v0.10 fallback manifest lacks {line}")
        sums = sums_reader.read().splitlines()
        expected: dict[str, str] = {}
        module_manifest_lines: list[bytes] = []
        module_relative_prefix = f"rootfs/lib/modules/{FALLBACK_RELEASE}/"
        for line in sums:
            fields = line.split(b"  ", 1)
            if len(fields) != 2:
                raise BuildError("malformed v0.10 fallback SHA256SUMS")
            expected_hash = fields[0].decode("ascii")
            relative = fields[1].decode("utf-8")
            if not re.fullmatch(r"[0-9a-f]{64}", expected_hash) or relative in expected:
                raise BuildError("unsafe or duplicate v0.10 fallback checksum entry")
            expected[relative] = expected_hash
            if relative.startswith(module_relative_prefix):
                module_manifest_lines.append(line + b"\n")
        regular_relative = {
            member.name.removeprefix(f"{FALLBACK_PACKAGE_ROOT}/")
            for member in members
            if member.isreg() and member.name != FALLBACK_SUMS_MEMBER
        }
        if set(expected) != regular_relative:
            raise BuildError("v0.10 fallback checksum member set mismatch")
        if (
            len(module_manifest_lines) != FALLBACK_MODULE_FILE_COUNT
            or sha256_bytes(b"".join(module_manifest_lines))
            != FALLBACK_MODULE_TREE_SHA256
        ):
            raise BuildError("v0.10 fallback module manifest digest mismatch")
        for relative, expected_hash in expected.items():
            member = archive.getmember(f"{FALLBACK_PACKAGE_ROOT}/{relative}")
            reader = archive.extractfile(member)
            if reader is None or sha256_bytes(reader.read()) != expected_hash:
                raise BuildError(f"v0.10 fallback member hash mismatch: {relative}")
    return {
        "bundle_sha256": FALLBACK_BUNDLE_SHA256,
        "bundle_size": FALLBACK_BUNDLE_SIZE,
        "module_count": FALLBACK_MODULE_COUNT,
        "module_file_count": FALLBACK_MODULE_FILE_COUNT,
        "module_tree_sha256": FALLBACK_MODULE_TREE_SHA256,
        "release": FALLBACK_RELEASE,
    }


def verify_product_rootfs_module_contract() -> dict[str, object]:
    for path, size, expected_hash, label in (
        (
            PRODUCT_ROOTFS_FILES,
            PRODUCT_ROOTFS_FILES_SIZE,
            PRODUCT_ROOTFS_FILES_SHA256,
            "product rootfs file manifest",
        ),
        (
            PRODUCT_ROOTFS_TREE,
            PRODUCT_ROOTFS_TREE_SIZE,
            PRODUCT_ROOTFS_TREE_SHA256,
            "product rootfs tree manifest",
        ),
    ):
        metadata = require_regular(path, label)
        if metadata.st_size != size or sha256_file(path) != expected_hash:
            raise BuildError(f"{label} identity mismatch")
    expected_trees = {
        SECONDARY_FALLBACK_RELEASE: SECONDARY_FALLBACK_MODULE_TREE_SHA256,
        "6.12.99-r46h-mainline-v0.15-gaming-product": KERNEL_MODULE_TREE_SHA256,
    }
    observed_counts: dict[str, dict[str, int]] = {}
    for line in PRODUCT_ROOTFS_TREE.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 6 or not fields[4].startswith("./usr/lib/modules/"):
            continue
        remainder = fields[4].removeprefix("./usr/lib/modules/")
        release = remainder.split("/", 1)[0]
        counts = observed_counts.setdefault(release, {"dirs": 0, "files": 0})
        if fields[1:3] != ["0", "0"]:
            raise BuildError(f"product module ownership mismatch: {fields[4]}")
        if fields[3] == "d" and fields[0] == "755":
            counts["dirs"] += 1
        elif fields[3] == "f" and fields[0] == "644":
            counts["files"] += 1
        else:
            raise BuildError(f"product module type or mode mismatch: {fields[4]}")
    if set(observed_counts) != set(expected_trees) or any(
        counts != {"dirs": 395, "files": 1290}
        for counts in observed_counts.values()
    ):
        raise BuildError("product rootfs module release or count mismatch")
    manifests: dict[str, list[tuple[str, str]]] = {
        release: [] for release in expected_trees
    }
    for line in PRODUCT_ROOTFS_FILES.read_text(encoding="utf-8").splitlines():
        fields = line.split("  ", 1)
        if len(fields) != 2 or not fields[1].startswith("./usr/lib/modules/"):
            continue
        digest_value, path = fields
        remainder = path.removeprefix("./usr/lib/modules/")
        release, separator, relative = remainder.partition("/")
        if release not in manifests or not separator or not relative:
            raise BuildError(f"unexpected product module checksum path: {path}")
        manifests[release].append((relative, digest_value))
    observed_hashes: dict[str, str] = {}
    for release, entries in manifests.items():
        if len(entries) != 1290 or len({relative for relative, _ in entries}) != 1290:
            raise BuildError(f"product module checksum count mismatch: {release}")
        canonical = b"".join(
            f"{digest_value}  rootfs/lib/modules/{release}/{relative}\n".encode()
            for relative, digest_value in sorted(entries)
        )
        observed_hashes[release] = sha256_bytes(canonical)
    if observed_hashes != expected_trees:
        raise BuildError("product rootfs module tree digest mismatch")
    return {
        "rootfs_files_sha256": PRODUCT_ROOTFS_FILES_SHA256,
        "rootfs_tree_sha256": PRODUCT_ROOTFS_TREE_SHA256,
        "module_trees": observed_hashes,
    }


def check_script_constants(captured: dict[str, bytes]) -> None:
    transaction = captured[
        "mainline/gaming-product-boot-promotion/transaction.sh"
    ].decode("utf-8")
    installer = captured[
        "mainline/gaming-product-boot-promotion/install.sh"
    ].decode("utf-8")
    fallback = captured[
        "mainline/gaming-product-boot-promotion/fallback-modules.sh"
    ].decode("utf-8")
    boot = captured[
        "mainline/gaming-product-boot-promotion/boot.ini.v0.15-gaming-product"
    ]
    if len(boot) != BOOT_SIZE or sha256_bytes(boot) != BOOT_SHA256:
        raise BuildError("tracked v0.15 boot script identity mismatch")
    required_transaction = (
        f"readonly R46H_V15_IMAGE_SIZE={COMPRESSED_IMAGE_SIZE}",
        f"readonly R46H_V15_IMAGE_SHA256={COMPRESSED_IMAGE_SHA256}",
        f"readonly R46H_V15_DTB_SIZE={KERNEL_DTB_SIZE}",
        f"readonly R46H_V15_DTB_SHA256={KERNEL_DTB_SHA256}",
        f"readonly R46H_V15_BOOT_SIZE={BOOT_SIZE}",
        f"readonly R46H_V15_BOOT_SHA256={BOOT_SHA256}",
    )
    required_installer = (
        f"readonly EXPECTED_BASE_P1_SHA256={BASE_P1_SHA256}",
        f"readonly EXPECTED_PREFIX_SHA256={PREFIX_SHA256}",
        f"readonly EXPECTED_PRODUCT_IMAGE_SIZE={KERNEL_IMAGE_SIZE}",
        f"readonly EXPECTED_PRODUCT_IMAGE_SHA256={KERNEL_IMAGE_SHA256}",
        f"readonly EXPECTED_PRODUCT_DTB_SHA256={KERNEL_DTB_SHA256}",
        f"readonly SECONDARY_FALLBACK_RUNNING_RELEASE={SECONDARY_FALLBACK_RELEASE}",
    )
    required_fallback = (
        f"readonly R46H_V10_RELEASE={FALLBACK_RELEASE}",
        f"readonly R46H_V10_BUNDLE_SIZE={FALLBACK_BUNDLE_SIZE}",
        f"readonly R46H_V10_BUNDLE_SHA256={FALLBACK_BUNDLE_SHA256}",
        f"readonly R46H_V10_MODULE_TREE_SHA256={FALLBACK_MODULE_TREE_SHA256}",
        f"readonly R46H_V10_MODULE_COUNT={FALLBACK_MODULE_COUNT}",
        f"readonly R46H_V10_MODULE_FILE_COUNT={FALLBACK_MODULE_FILE_COUNT}",
        f"readonly R46H_V10_MODULE_DIR_COUNT={FALLBACK_MODULE_DIR_COUNT}",
        f"readonly R46H_V08_RELEASE={SECONDARY_FALLBACK_RELEASE}",
        f"readonly R46H_V08_MODULE_TREE_SHA256={SECONDARY_FALLBACK_MODULE_TREE_SHA256}",
        "readonly R46H_V15_RELEASE=6.12.99-r46h-mainline-v0.15-gaming-product",
        f"readonly R46H_V15_MODULE_TREE_SHA256={KERNEL_MODULE_TREE_SHA256}",
    )
    for marker in required_transaction:
        if marker not in transaction:
            raise BuildError(f"script constant mismatch: {marker}")
    for marker in required_installer:
        if marker not in installer:
            raise BuildError(f"script constant mismatch: {marker}")
    for marker in required_fallback:
        if marker not in fallback:
            raise BuildError(f"script constant mismatch: {marker}")
    for relative in (
        "mainline/gaming-product-boot-promotion/fallback-modules.sh",
        "mainline/gaming-product-boot-promotion/install.sh",
        "mainline/gaming-product-boot-promotion/storage-health.sh",
        "mainline/gaming-product-boot-promotion/transaction.sh",
        "mainline/gaming-product-boot-promotion/complete-recovered-mmc-postflight.sh",
    ):
        result = subprocess.run(
            ["/bin/bash", "-n"],
            input=captured[relative],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if result.returncode != 0:
            raise BuildError(f"bash syntax failed: {relative}")


def file_manifest(root: Path, excluded: set[str]) -> bytes:
    lines = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        if not path.is_file() or path.name in excluded:
            continue
        relative = path.relative_to(root).as_posix()
        lines.append(f"{sha256_file(path)}  {relative}\n")
    return "".join(lines).encode()


def create_payload(
    root: Path,
    captured: dict[str, bytes],
    commit: str,
    tree: str,
    kernel: dict[str, object],
    fallback: dict[str, object],
    artifact_root: Path,
) -> None:
    root.mkdir(mode=0o700)
    (root / "files").mkdir(mode=0o700)
    write_new(root / "install.sh", captured["mainline/gaming-product-boot-promotion/install.sh"], 0o500)
    write_new(
        root / "transaction.sh",
        captured["mainline/gaming-product-boot-promotion/transaction.sh"],
        0o400,
    )
    write_new(
        root / "fallback-modules.sh",
        captured["mainline/gaming-product-boot-promotion/fallback-modules.sh"],
        0o400,
    )
    write_new(
        root / "storage-health.sh",
        captured["mainline/gaming-product-boot-promotion/storage-health.sh"],
        0o400,
    )
    write_new(
        root / "files/boot.ini.v0.15-gaming-product",
        captured["mainline/gaming-product-boot-promotion/boot.ini.v0.15-gaming-product"],
        0o400,
    )
    image = artifact_root / "Image.gz"
    dtb = artifact_root / "R46H.DTB"
    if image.stat().st_size != COMPRESSED_IMAGE_SIZE or sha256_file(image) != COMPRESSED_IMAGE_SHA256:
        raise BuildError("payload compressed Image input mismatch")
    if dtb.stat().st_size != KERNEL_DTB_SIZE or sha256_file(dtb) != KERNEL_DTB_SHA256:
        raise BuildError("payload DTB input mismatch")
    write_new(
        root / "files/Image.mainline-v0.15-gaming-product.gz",
        image.read_bytes(),
        0o400,
    )
    write_new(
        root / "files/rk3326-r46h-mainline-v0.15-gaming-product.dtb",
        dtb.read_bytes(),
        0o400,
    )
    if (
        FALLBACK_BUNDLE.stat().st_size != FALLBACK_BUNDLE_SIZE
        or sha256_file(FALLBACK_BUNDLE) != FALLBACK_BUNDLE_SHA256
    ):
        raise BuildError("payload fallback bundle input mismatch")
    write_new(
        root / f"files/{FALLBACK_BUNDLE.name}",
        FALLBACK_BUNDLE.read_bytes(),
        0o400,
    )
    write_new(
        root / "PAYLOAD-INFO.json",
        canonical_json(
            {
                "base_p1_sha256": BASE_P1_SHA256,
                "boot_script_sha256": BOOT_SHA256,
                "boot_script_size": BOOT_SIZE,
                "format_version": 1,
                "fallback": fallback,
                "kernel": kernel,
                "payload_id": PAYLOAD_ID,
                "prefix_sha256": PREFIX_SHA256,
                "source_git_commit": commit,
                "source_git_tree": tree,
                "secondary_fallback": {
                    "module_tree_sha256": SECONDARY_FALLBACK_MODULE_TREE_SHA256,
                    "release": SECONDARY_FALLBACK_RELEASE,
                },
                "target_release": "6.12.99-r46h-mainline-v0.15-gaming-product",
                "writes_p1_when_confirmed": True,
                "writes_uboot_environment": False,
            }
        ),
        0o400,
    )
    sums = file_manifest(root, {"SHA256SUMS", "PAYLOAD.COMPLETE"})
    write_new(root / "SHA256SUMS", sums, 0o400)
    write_new(
        root / "PAYLOAD.COMPLETE",
        f"sha256sums_sha256={sha256_bytes(sums)}\n".encode(),
        0o400,
    )
    observed = {path.relative_to(root).as_posix() for path in root.rglob("*")}
    if observed != PAYLOAD_MEMBERS:
        raise BuildError(f"payload member mismatch: {sorted(observed)}")


def deterministic_archive(payload: Path, destination: Path) -> None:
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        entries = [payload, *sorted(payload.rglob("*"), key=lambda path: path.relative_to(payload).as_posix())]
        for path in entries:
            relative = Path(PAYLOAD_ID) if path == payload else Path(PAYLOAD_ID) / path.relative_to(payload)
            metadata = path.lstat()
            info = tarfile.TarInfo(relative.as_posix())
            info.uid = 0
            info.gid = 0
            info.uname = "root"
            info.gname = "root"
            info.mtime = SOURCE_DATE_EPOCH
            if stat.S_ISDIR(metadata.st_mode):
                info.type = tarfile.DIRTYPE
                info.mode = 0o700
                archive.addfile(info)
            elif stat.S_ISREG(metadata.st_mode):
                info.type = tarfile.REGTYPE
                info.size = metadata.st_size
                info.mode = stat.S_IMODE(metadata.st_mode)
                with path.open("rb") as handle:
                    archive.addfile(info, handle)
            else:
                raise BuildError(f"unsafe payload entry: {path}")
    with destination.open("xb") as output:
        with gzip.GzipFile(filename="", mode="wb", compresslevel=9, mtime=SOURCE_DATE_EPOCH, fileobj=output) as compressed:
            compressed.write(tar_buffer.getvalue())


def validate_archive(path: Path) -> None:
    require_regular(path, "promotion archive")
    expected = {PAYLOAD_ID, *{f"{PAYLOAD_ID}/{name}" for name in PAYLOAD_MEMBERS}}
    with tarfile.open(path, "r:gz") as archive:
        observed = {member.name.rstrip("/") for member in archive.getmembers()}
        if observed != expected:
            raise BuildError("promotion archive member set mismatch")
        for member in archive.getmembers():
            if not (member.isdir() or member.isreg()) or member.uid != 0 or member.gid != 0:
                raise BuildError(f"unsafe promotion archive member: {member.name}")


def publish_generation(stage: Path, generation: str) -> Path:
    builds = RELEASE_ROOT / "builds"
    builds.mkdir(parents=True, exist_ok=True)
    destination = builds / generation
    if destination.exists() or destination.is_symlink():
        raise BuildError(f"generation already exists: {generation}")
    os.rename(stage, destination)
    RELEASE_ROOT.mkdir(parents=True, exist_ok=True)
    pointer = RELEASE_ROOT / f".CURRENT.{os.getpid()}"
    write_new(pointer, f"{generation}\n".encode())
    os.replace(pointer, RELEASE_ROOT / "CURRENT")
    return destination


def exact_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise BuildError(f"not one JSON object: {path.name}")
    return value


def validate_generation() -> Path:
    current_path = RELEASE_ROOT / "CURRENT"
    require_regular(current_path, "CURRENT")
    current = current_path.read_text(encoding="utf-8").strip()
    if GENERATION_RE.fullmatch(current) is None:
        raise BuildError("invalid CURRENT generation")
    generation = RELEASE_ROOT / "builds" / current
    require_directory(generation, "generation")
    if {entry.name for entry in generation.iterdir()} != GENERATION_MEMBERS:
        raise BuildError("generation member set mismatch")
    sums = file_manifest(generation, {"SHA256SUMS", "BUILD-COMPLETE"})
    if (generation / "SHA256SUMS").read_bytes() != sums:
        raise BuildError("generation checksum manifest mismatch")
    expected_complete = f"sha256sums_sha256={sha256_bytes(sums)}\n".encode()
    if (generation / "BUILD-COMPLETE").read_bytes() != expected_complete:
        raise BuildError("generation completion marker mismatch")
    archive = generation / ARCHIVE_NAME
    receipt = exact_json(generation / "BUILD-RECEIPT.json")
    if receipt.get("archive_sha256") != sha256_file(archive):
        raise BuildError("archive digest does not match build receipt")
    validate_archive(archive)
    return generation


def command_build() -> Path:
    commit, tree, captured, source_manifest = capture_clean_source()
    check_script_constants(captured)
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="work.", dir=CACHE_ROOT))
    stage = work / "generation"
    published = False
    try:
        kernel = verify_kernel_bundle(work)
        fallback = verify_fallback_bundle()
        product_rootfs = verify_product_rootfs_module_contract()
        payload = work / "payload"
        create_payload(payload, captured, commit, tree, kernel, fallback, work)
        stage.mkdir(mode=0o700)
        archive = stage / ARCHIVE_NAME
        deterministic_archive(payload, archive)
        validate_archive(archive)
        archive_sha = sha256_file(archive)
        write_new(stage / "SOURCE-MANIFEST.json", source_manifest)
        write_new(
            stage / "BUILD-RECEIPT.json",
            canonical_json(
                {
                    "archive_sha256": archive_sha,
                    "archive_size": archive.stat().st_size,
                    "base_p1_sha256": BASE_P1_SHA256,
                    "format_version": 1,
                    "fallback_bundle_sha256": FALLBACK_BUNDLE_SHA256,
                    "kernel_bundle_sha256": KERNEL_BUNDLE_SHA256,
                    "payload_id": PAYLOAD_ID,
                    "prefix_sha256": PREFIX_SHA256,
                    "product_rootfs_module_contract": product_rootfs,
                    "source_git_commit": commit,
                    "source_git_tree": tree,
                    "source_manifest_sha256": sha256_bytes(source_manifest),
                }
            ),
        )
        generation_sums = file_manifest(stage, {"SHA256SUMS", "BUILD-COMPLETE"})
        write_new(stage / "SHA256SUMS", generation_sums)
        write_new(
            stage / "BUILD-COMPLETE",
            f"sha256sums_sha256={sha256_bytes(generation_sums)}\n".encode(),
        )
        generation_name = f"build-{commit[:12]}-{archive_sha[:12]}"
        destination = publish_generation(stage, generation_name)
        published = True
        validate_generation()
        print(f"PASS: v0.15 BOOT promotion payload published at {destination}")
        print(f"ARCHIVE={destination / ARCHIVE_NAME}")
        print(f"ARCHIVE_SHA256={archive_sha}")
        return destination
    finally:
        if not published and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "validate"))
    return parser.parse_args()


def main() -> int:
    try:
        arguments = parse_args()
        if arguments.action == "build":
            command_build()
        else:
            generation = validate_generation()
            print(f"PASS: v0.15 BOOT promotion generation validated at {generation}")
    except (BuildError, OSError, tarfile.TarError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
