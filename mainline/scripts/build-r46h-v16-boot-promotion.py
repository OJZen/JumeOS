#!/usr/bin/env python3
"""Build and validate the rollback-safe R46H v0.16 BOOT promotion payload."""

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
MAINLINE = REPO / "mainline"
VERSION_LABEL = "v0.16"
PROMOTION_RELATIVE = "mainline/gaming-product-v16-boot-promotion"
README_RELATIVE = f"{PROMOTION_RELATIVE}/README.md"
BOOT_RELATIVE = f"{PROMOTION_RELATIVE}/boot.ini.v0.16-disable-secondary"
INSTALL_RELATIVE = f"{PROMOTION_RELATIVE}/install.sh"
TRANSACTION_RELATIVE = f"{PROMOTION_RELATIVE}/transaction.sh"
BUILDER_RELATIVE = "mainline/scripts/build-r46h-v16-boot-promotion.py"
TEST_RELATIVE = "mainline/tests/test-r46h-v16-boot-promotion.py"
ONE_SHOT_RUNBOOK_RELATIVE = "mainline/bringup-tests/V16-MMC-COLD-ISOLATION.md"
ONE_SHOT_TEST_RELATIVE = "mainline/tests/test-r46h-v16-mmc-cold-isolation.py"
PROMOTION = REPO / PROMOTION_RELATIVE
CACHE_ROOT = MAINLINE / "out/.cache/r46h-v16-boot-promotion"
RELEASE_ROOT = MAINLINE / "out/r46h-v16-boot-promotion"
PAYLOAD_ID = "r46h-v16-boot-promotion-v0.1"
ARCHIVE_NAME = f"{PAYLOAD_ID}.tar.gz"
SOURCE_DATE_EPOCH = 1_785_369_600

FROZEN_CANDIDATE = (
    MAINLINE
    / "out/r46h-v16-mmc-cold-isolation"
    / "r46h-v16-mmc-cold-isolation.tar.gz"
)
FROZEN_CANDIDATE_SIZE = 12_466
FROZEN_CANDIDATE_SHA256 = (
    "e9d04016f03e5619c64c3a8916b361c64857a6928cbf99f43392492c3d5276d1"
)
FROZEN_CANDIDATE_ROOT = "v0.16-disable-secondary"
CANDIDATE_MEMBER = f"{FROZEN_CANDIDATE_ROOT}/R46H.DTB"
FROZEN_CANDIDATE_FILES = (
    "LAUNCH.txt",
    "R46H-V16.SCR",
    "R46H.DTB",
    "RECEIPT.json",
    "SHA256SUMS",
    "UBOOT-CMDS.txt",
    "r46h-v16-mmc-cold-isolation.dtbo",
)
CANDIDATE_DTB_NAME = "rk3326-r46h-mainline-v0.16-disable-secondary.dtb"
CANDIDATE_DTB_SIZE = 49_522
CANDIDATE_DTB_SHA256 = (
    "7831617d4003cdbb2733433781f80625cb94e7c9d619f2f90990223b8f8d7f81"
)
BOOT_NAME = "boot.ini.v0.16-disable-secondary"
BOOT_SIZE = 1_449
BOOT_SHA256 = (
    "edb33de5fef23b810deec13c05b6958a72eea3dbb74ce2b39b0f80cdb508aba3"
)
CANDIDATE_VARIABLE_PREFIX = "R46H_V16"
CANDIDATE_DTB_EXTRA_CHECKS = ""
BASE_P1_SHA256 = (
    "042ad4ad08f39f60f1d57e393ab32ae148e2a946ab9996822ae161934f7a0825"
)
PREFIX_SHA256 = (
    "3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3"
)
FALLBACK_HELPER_RELATIVE = (
    "mainline/gaming-product-boot-promotion/fallback-modules.sh"
)
FALLBACK_HELPER_SIZE = 14_055
FALLBACK_HELPER_SHA256 = (
    "f7b3fd534ec90ca420568dc20299b90a9ff66782145631cc7b272a59500f341e"
)
STORAGE_HELPER_RELATIVE = "mainline/gaming-product-boot-promotion/storage-health.sh"
STORAGE_HELPER_SIZE = 2_439
STORAGE_HELPER_SHA256 = (
    "c0e3cb1b69e5b4773f999c62e448cf44a645fe824bc4b8732eef33d8acbf842c"
)
V05_ROOTFS_ROOT = MAINLINE / "out/r46h-debian13-p2-gaming-v0.5"
V05_ROOTFS_FILES = V05_ROOTFS_ROOT / "ROOTFS-FILES.sha256"
V05_ROOTFS_FILES_SIZE = 2_571_386
V05_ROOTFS_FILES_SHA256 = (
    "1ad54bc7afa6f4e16b21a726663f630bd02769c4a5ab50d0b7c40ef36f718d83"
)
V05_ROOTFS_TREE = V05_ROOTFS_ROOT / "ROOTFS-TREE.tsv"
V05_ROOTFS_TREE_SIZE = 1_798_571
V05_ROOTFS_TREE_SHA256 = (
    "72abe4699628a4a93c1f2324c58dadc5209c7244b94fb03e4e7bdb529b705380"
)
MODULE_TREE_SHA256 = {
    "6.12.99-r46h-mainline-v0.8-bootloader-handoff": (
        "2ec532a3d3c6833538bd4ffd284122afa30bea0945e832f57be481527986f210"
    ),
    "6.12.99-r46h-mainline-v0.10-adc-full-range": (
        "a70796c050de93c4c212180addf54a17efe7732d355db2b52d0bfcab6c56cc16"
    ),
    "6.12.99-r46h-mainline-v0.15-gaming-product": (
        "bd53fad3997ced39a15c69dbd70525106e891e5529dcef73bbbcfb699aafc291"
    ),
}

DOCKER_CONTEXT = "desktop-linux"
DOCKER_IMAGE = "arkos4clone/r46h-kernel-builder:trixie-arm64"
DOCKER_IMAGE_ID = (
    "sha256:3686fd20408cf746c1171e9345fd6c842a71f87e589f691b2455435b3bdd141a"
)
DOCKER_CLI = Path("/Applications/Docker.app/Contents/Resources/bin/docker")

SOURCE_PATHS = (
    ONE_SHOT_RUNBOOK_RELATIVE,
    README_RELATIVE,
    BOOT_RELATIVE,
    INSTALL_RELATIVE,
    TRANSACTION_RELATIVE,
    FALLBACK_HELPER_RELATIVE,
    STORAGE_HELPER_RELATIVE,
    BUILDER_RELATIVE,
    TEST_RELATIVE,
    ONE_SHOT_TEST_RELATIVE,
)
PAYLOAD_MEMBERS = {
    "PAYLOAD-INFO.json",
    "PAYLOAD.COMPLETE",
    "SHA256SUMS",
    "fallback-modules.sh",
    "files",
    f"files/{BOOT_NAME}",
    f"files/{CANDIDATE_DTB_NAME}",
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
GENERATION_RE = re.compile(r"build-[0-9a-f]{12}-[0-9a-f]{12}")


class BuildError(RuntimeError):
    pass


def render_payload_source(relative: str, payload: bytes) -> bytes:
    """Return the exact payload member derived from one committed source blob."""

    return payload


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


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


def require_regular(path: Path, label: str) -> os.stat_result:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise BuildError(f"unsafe {label}: {path}")
    return metadata


def require_directory(path: Path, label: str) -> os.stat_result:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise BuildError(f"unsafe {label}: {path}")
    return metadata


def write_new(path: Path, payload: bytes, mode: int = 0o400) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)
    path.chmod(mode)


def capture_clean_source() -> tuple[str, str, dict[str, bytes], bytes]:
    status = git_bytes(
        ["status", "--porcelain=v1", "--untracked-files=all", "--", *SOURCE_PATHS]
    )
    if status:
        raise BuildError(
            f"{VERSION_LABEL} BOOT promotion source scope is not committed and clean"
        )
    commit = git_bytes(["rev-parse", "--verify", "HEAD^{commit}"]).decode().strip()
    tree = git_bytes(["rev-parse", "--verify", "HEAD^{tree}"]).decode().strip()
    captured: dict[str, bytes] = {}
    entries: list[dict[str, object]] = []
    for relative in SOURCE_PATHS:
        live = REPO / relative
        require_regular(live, f"source {relative}")
        listing = git_bytes(["ls-tree", "HEAD", "--", relative]).decode().strip()
        fields = listing.split(None, 3)
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
    source_manifest = canonical_json(
        {
            "file_count": len(entries),
            "files": entries,
            "format_version": 1,
            "git_commit": commit,
            "git_tree": tree,
        }
    )
    return commit, tree, captured, source_manifest


def docker_output(arguments: list[str]) -> str:
    result = subprocess.run(
        [str(DOCKER_CLI), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if result.returncode != 0:
        raise BuildError(result.stderr.strip() or "Docker command failed")
    return result.stdout.strip()


def require_toolchain() -> dict[str, str]:
    metadata = require_regular(DOCKER_CLI, "fixed Docker CLI")
    mode = stat.S_IMODE(metadata.st_mode)
    if metadata.st_uid not in {0, os.geteuid()} or mode & 0o022 or not mode & 0o111:
        raise BuildError("unsafe fixed Docker CLI ownership or mode")
    if docker_output(["context", "show"]) != DOCKER_CONTEXT:
        raise BuildError("unexpected Docker context")
    client = docker_output(["version", "--format", "{{.Client.Version}}"])
    server = docker_output(["info", "--format", "{{.ServerVersion}}"])
    image = docker_output(["image", "inspect", "--format", "{{.Id}}", DOCKER_IMAGE])
    if image != DOCKER_IMAGE_ID:
        raise BuildError("builder image identity mismatch")
    return {"docker_client_version": client, "docker_server_version": server}


def docker_verify_candidate(candidate: bytes) -> None:
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dtb.", dir=CACHE_ROOT) as temporary:
        work = Path(temporary)
        (work / "candidate.dtb").write_bytes(candidate)
        result = subprocess.run(
            [
                str(DOCKER_CLI),
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--mount",
                f"type=bind,source={work},target=/work,readonly",
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=8m",
                DOCKER_IMAGE_ID,
                "/bin/sh",
                "-ceu",
                f"""
test "$(fdtget -t s /work/candidate.dtb /mmc@ff370000 status)" = okay
test "$(fdtget -t s /work/candidate.dtb /mmc@ff380000 status)" = disabled
test "$(fdtget -t s /work/candidate.dtb /aliases mmc0)" = /mmc@ff370000
test "$(fdtget -t s /work/candidate.dtb /aliases mmc1)" = /mmc@ff380000
{CANDIDATE_DTB_EXTRA_CHECKS}
""",
            ],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        if result.returncode != 0:
            raise BuildError(f"candidate DTB contract failed:\n{result.stdout}")


def read_frozen_candidate() -> bytes:
    metadata = require_regular(
        FROZEN_CANDIDATE, f"frozen {VERSION_LABEL} candidate archive"
    )
    if (
        metadata.st_size != FROZEN_CANDIDATE_SIZE
        or sha256_file(FROZEN_CANDIDATE) != FROZEN_CANDIDATE_SHA256
    ):
        raise BuildError(f"frozen {VERSION_LABEL} candidate archive identity mismatch")
    expected = {
        FROZEN_CANDIDATE_ROOT,
        *{
            f"{FROZEN_CANDIDATE_ROOT}/{name}"
            for name in FROZEN_CANDIDATE_FILES
        },
    }
    with tarfile.open(FROZEN_CANDIDATE, "r:gz") as archive:
        members = archive.getmembers()
        names = [member.name.rstrip("/") for member in members]
        if len(names) != len(set(names)) or set(names) != expected:
            raise BuildError("frozen candidate archive member set mismatch")
        for member in members:
            if member.issym() or member.islnk() or member.uid != 0 or member.gid != 0:
                raise BuildError("unsafe frozen candidate archive member")
            if member.name.rstrip("/") == FROZEN_CANDIDATE_ROOT:
                if not member.isdir() or stat.S_IMODE(member.mode) != 0o700:
                    raise BuildError("unsafe frozen candidate root")
            elif not member.isfile() or stat.S_IMODE(member.mode) != 0o400:
                raise BuildError("unsafe frozen candidate file")
        stream = archive.extractfile(CANDIDATE_MEMBER)
        if stream is None:
            raise BuildError("cannot read frozen candidate DTB")
        candidate = stream.read()
    if len(candidate) != CANDIDATE_DTB_SIZE or sha256_bytes(candidate) != CANDIDATE_DTB_SHA256:
        raise BuildError("frozen candidate DTB identity mismatch")
    return candidate


def verify_v05_rootfs_contract() -> dict[str, object]:
    for path, size, expected_hash, label in (
        (
            V05_ROOTFS_FILES,
            V05_ROOTFS_FILES_SIZE,
            V05_ROOTFS_FILES_SHA256,
            "v0.5 rootfs file manifest",
        ),
        (
            V05_ROOTFS_TREE,
            V05_ROOTFS_TREE_SIZE,
            V05_ROOTFS_TREE_SHA256,
            "v0.5 rootfs tree manifest",
        ),
    ):
        metadata = require_regular(path, label)
        if metadata.st_size != size or sha256_file(path) != expected_hash:
            raise BuildError(f"{label} identity mismatch")

    tree_rows: dict[str, list[str]] = {}
    module_counts = {
        release: {"dirs": 0, "files": 0, "modules": 0}
        for release in MODULE_TREE_SHA256
    }
    for line in V05_ROOTFS_TREE.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 6:
            raise BuildError("v0.5 rootfs tree row shape mismatch")
        path = fields[4]
        if path.startswith("./var/lib/r46h-boot-promotion"):
            raise BuildError("v0.5 rootfs unexpectedly retains old BOOT promotion state")
        if path in tree_rows:
            raise BuildError(f"duplicate v0.5 rootfs tree path: {path}")
        tree_rows[path] = fields
        prefix = "./usr/lib/modules/"
        if not path.startswith(prefix):
            continue
        remainder = path.removeprefix(prefix)
        release = remainder.split("/", 1)[0]
        if release not in module_counts:
            raise BuildError(f"unexpected v0.5 module release: {release}")
        if fields[3] == "d":
            module_counts[release]["dirs"] += 1
        elif fields[3] == "f":
            module_counts[release]["files"] += 1
            if path.endswith(".ko"):
                module_counts[release]["modules"] += 1
        else:
            raise BuildError(f"unexpected v0.5 module entry type: {path}")
    expected_modes = {
        "./var/lib/r46h/gaming-mvp-v0.4-installed": "600",
        "./etc/r46h/retroarch.cfg": "644",
        "./usr/local/sbin/r46h-storage-audit": "755",
        "./var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/IMAGE": "400",
        "./var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/R46H.DTB": "400",
        "./var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/RECEIPT": "400",
    }
    for path, mode in expected_modes.items():
        fields = tree_rows.get(path)
        if fields is None or fields[:4] != [mode, "0", "0", "f"]:
            raise BuildError(f"v0.5 rootfs identity mismatch: {path}")
    if any(
        counts != {"dirs": 395, "files": 1290, "modules": 1276}
        for counts in module_counts.values()
    ):
        raise BuildError("v0.5 module tree counts mismatch")

    file_hashes: dict[str, str] = {}
    module_entries: dict[str, list[tuple[str, str]]] = {
        release: [] for release in MODULE_TREE_SHA256
    }
    for line in V05_ROOTFS_FILES.read_text(encoding="utf-8").splitlines():
        digest_value, separator, path = line.partition("  ")
        if not separator or re.fullmatch(r"[0-9a-f]{64}", digest_value) is None:
            raise BuildError("v0.5 rootfs checksum row shape mismatch")
        if path.startswith("./var/lib/r46h-boot-promotion"):
            raise BuildError("v0.5 checksums unexpectedly retain old BOOT promotion state")
        if path in file_hashes:
            raise BuildError(f"duplicate v0.5 rootfs checksum path: {path}")
        file_hashes[path] = digest_value
        prefix = "./usr/lib/modules/"
        if not path.startswith(prefix):
            continue
        remainder = path.removeprefix(prefix)
        release, separator, relative = remainder.partition("/")
        if release not in module_entries or not separator or not relative:
            raise BuildError(f"unexpected v0.5 module checksum path: {path}")
        module_entries[release].append((relative, digest_value))
    expected_hashes = {
        "./var/lib/r46h/gaming-mvp-v0.4-installed": (
            "0a0675e82aa35fb22252de2d688fa280275e52634ef9a130c5e415ba2cc04666"
        ),
        "./etc/r46h/retroarch.cfg": (
            "99a45beb148e58e40983773b4f5e26d9fb5d7e1bbbf6a7e714a5c352e43c0dba"
        ),
        "./usr/local/sbin/r46h-storage-audit": (
            "08ed33dace8a94a6b129d72896c8e6a657b32d15c74d9ecf48df99a9f49ae95c"
        ),
        "./var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/IMAGE": (
            "956ab3d5a2e53afbfe964ae75850e8591b44c093b9779867b31149b7b591f68f"
        ),
        "./var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/R46H.DTB": (
            "4d6d4ebad3b98600b6e9a38df4ca82230335558497a9e15dd0e81ca60e304b61"
        ),
        "./var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/RECEIPT": (
            "a90b359f2275bdc732b5814bf9d1dc328844532a1e3c2a4d23577068978fffbd"
        ),
    }
    for path, expected_hash in expected_hashes.items():
        if file_hashes.get(path) != expected_hash:
            raise BuildError(f"v0.5 rootfs checksum mismatch: {path}")
    observed_module_hashes: dict[str, str] = {}
    for release, entries in module_entries.items():
        if len(entries) != 1290 or len({relative for relative, _ in entries}) != 1290:
            raise BuildError(f"v0.5 module checksum count mismatch: {release}")
        canonical = b"".join(
            f"{digest_value}  rootfs/lib/modules/{release}/{relative}\n".encode()
            for relative, digest_value in sorted(entries)
        )
        observed_module_hashes[release] = sha256_bytes(canonical)
    if observed_module_hashes != MODULE_TREE_SHA256:
        raise BuildError("v0.5 module tree digest mismatch")
    return {
        "rootfs_files_sha256": V05_ROOTFS_FILES_SHA256,
        "rootfs_tree_sha256": V05_ROOTFS_TREE_SHA256,
        "module_trees": observed_module_hashes,
        "old_v15_promotion_state": "absent-after-full-p2-rewrite",
    }


def check_script_constants(captured: dict[str, bytes], candidate: bytes) -> None:
    boot = captured[BOOT_RELATIVE]
    if len(boot) != BOOT_SIZE or sha256_bytes(boot) != BOOT_SHA256:
        raise BuildError(f"tracked {VERSION_LABEL} boot script identity mismatch")
    if len(candidate) != CANDIDATE_DTB_SIZE or sha256_bytes(candidate) != CANDIDATE_DTB_SHA256:
        raise BuildError("candidate DTB identity mismatch")
    fallback = captured[FALLBACK_HELPER_RELATIVE]
    storage = captured[STORAGE_HELPER_RELATIVE]
    if len(fallback) != FALLBACK_HELPER_SIZE or sha256_bytes(fallback) != FALLBACK_HELPER_SHA256:
        raise BuildError("fallback helper identity mismatch")
    if len(storage) != STORAGE_HELPER_SIZE or sha256_bytes(storage) != STORAGE_HELPER_SHA256:
        raise BuildError("storage helper identity mismatch")
    transaction = render_payload_source(
        TRANSACTION_RELATIVE, captured[TRANSACTION_RELATIVE]
    ).decode()
    installer = render_payload_source(INSTALL_RELATIVE, captured[INSTALL_RELATIVE]).decode()
    for marker in (
        f"readonly {CANDIDATE_VARIABLE_PREFIX}_DTB_SIZE={CANDIDATE_DTB_SIZE}",
        f"readonly {CANDIDATE_VARIABLE_PREFIX}_DTB_SHA256={CANDIDATE_DTB_SHA256}",
        f"readonly {CANDIDATE_VARIABLE_PREFIX}_BOOT_SIZE={BOOT_SIZE}",
        f"readonly {CANDIDATE_VARIABLE_PREFIX}_BOOT_SHA256={BOOT_SHA256}",
    ):
        if marker not in transaction:
            raise BuildError(f"transaction constant mismatch: {marker}")
    for marker in (
        f"readonly EXPECTED_BASE_P1_SHA256={BASE_P1_SHA256}",
        f"readonly EXPECTED_PREFIX_SHA256={PREFIX_SHA256}",
        "readonly EXPECTED_RUNNING_RELEASE=6.12.99-r46h-mainline-v0.15-gaming-product",
        "readonly EXPECTED_ROOT_UUID=d3130005-46a4-4d56-9001-000000000005",
    ):
        if marker not in installer:
            raise BuildError(f"installer constant mismatch: {marker}")
    for relative in (
        INSTALL_RELATIVE,
        TRANSACTION_RELATIVE,
        FALLBACK_HELPER_RELATIVE,
        STORAGE_HELPER_RELATIVE,
    ):
        syntax = subprocess.run(
            ["/bin/bash", "-n"],
            input=render_payload_source(relative, captured[relative]),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if syntax.returncode != 0:
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
    candidate: bytes,
    commit: str,
    tree: str,
) -> None:
    root.mkdir(mode=0o700)
    (root / "files").mkdir(mode=0o700)
    write_new(
        root / "install.sh",
        render_payload_source(INSTALL_RELATIVE, captured[INSTALL_RELATIVE]),
        0o500,
    )
    write_new(
        root / "transaction.sh",
        render_payload_source(TRANSACTION_RELATIVE, captured[TRANSACTION_RELATIVE]),
    )
    write_new(root / "fallback-modules.sh", captured[FALLBACK_HELPER_RELATIVE])
    write_new(root / "storage-health.sh", captured[STORAGE_HELPER_RELATIVE])
    write_new(
        root / f"files/{BOOT_NAME}",
        captured[BOOT_RELATIVE],
    )
    write_new(root / f"files/{CANDIDATE_DTB_NAME}", candidate)
    write_new(
        root / "PAYLOAD-INFO.json",
        canonical_json(
            {
                "base_p1_sha256": BASE_P1_SHA256,
                "candidate_dtb_sha256": CANDIDATE_DTB_SHA256,
                "candidate_dtb_size": CANDIDATE_DTB_SIZE,
                "format_version": 1,
                "frozen_candidate_archive_sha256": FROZEN_CANDIDATE_SHA256,
                "payload_id": PAYLOAD_ID,
                "p2_baseline": "gaming-v0.5-full-rewrite",
                "prefix_sha256": PREFIX_SHA256,
                "second_card_slot": "unavailable",
                "source_git_commit": commit,
                "source_git_tree": tree,
                "target_boot_sha256": BOOT_SHA256,
                "target_release": "6.12.99-r46h-mainline-v0.15-gaming-product",
                "writes_p1_when_confirmed": True,
                "writes_uboot_environment": False,
            }
        ),
    )
    sums = file_manifest(root, {"SHA256SUMS", "PAYLOAD.COMPLETE"})
    write_new(root / "SHA256SUMS", sums)
    write_new(
        root / "PAYLOAD.COMPLETE",
        f"sha256sums_sha256={sha256_bytes(sums)}\n".encode(),
    )
    observed = {path.relative_to(root).as_posix() for path in root.rglob("*")}
    if observed != PAYLOAD_MEMBERS:
        raise BuildError(f"payload member mismatch: {sorted(observed)}")


def deterministic_archive(payload: Path) -> bytes:
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        entries = [
            payload,
            *sorted(payload.rglob("*"), key=lambda path: path.relative_to(payload).as_posix()),
        ]
        for path in entries:
            relative = (
                Path(PAYLOAD_ID)
                if path == payload
                else Path(PAYLOAD_ID) / path.relative_to(payload)
            )
            metadata = path.lstat()
            info = tarfile.TarInfo(relative.as_posix())
            info.uid = info.gid = 0
            info.uname = info.gname = "root"
            info.mtime = SOURCE_DATE_EPOCH
            if stat.S_ISDIR(metadata.st_mode):
                info.type = tarfile.DIRTYPE
                info.mode = 0o700
                archive.addfile(info)
            elif stat.S_ISREG(metadata.st_mode):
                info.type = tarfile.REGTYPE
                info.mode = stat.S_IMODE(metadata.st_mode)
                info.size = metadata.st_size
                with path.open("rb") as handle:
                    archive.addfile(info, handle)
            else:
                raise BuildError(f"unsafe payload entry: {path}")
    compressed = io.BytesIO()
    with gzip.GzipFile(
        filename="",
        mode="wb",
        compresslevel=9,
        mtime=SOURCE_DATE_EPOCH,
        fileobj=compressed,
    ) as output:
        output.write(tar_buffer.getvalue())
    return compressed.getvalue()


def validate_archive(payload: bytes) -> dict[str, bytes]:
    expected = {PAYLOAD_ID, *{f"{PAYLOAD_ID}/{name}" for name in PAYLOAD_MEMBERS}}
    observed: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        members = archive.getmembers()
        names = [member.name.rstrip("/") for member in members]
        if len(names) != len(set(names)) or set(names) != expected:
            raise BuildError("promotion archive member set mismatch")
        for member in members:
            name = member.name.rstrip("/")
            relative = name.removeprefix(f"{PAYLOAD_ID}/")
            if member.issym() or member.islnk() or member.uid != 0 or member.gid != 0:
                raise BuildError(f"unsafe promotion archive member: {name}")
            if name in {PAYLOAD_ID, f"{PAYLOAD_ID}/files"}:
                if not member.isdir() or stat.S_IMODE(member.mode) != 0o700:
                    raise BuildError(f"unsafe promotion archive directory: {name}")
                continue
            expected_mode = 0o500 if relative == "install.sh" else 0o400
            if not member.isfile() or stat.S_IMODE(member.mode) != expected_mode:
                raise BuildError(f"unsafe promotion archive file: {name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise BuildError(f"cannot read promotion archive member: {name}")
            observed[relative] = stream.read()
    manifest = observed["SHA256SUMS"].decode().splitlines()
    expected_manifest = [
        f"{sha256_bytes(value)}  {name}"
        for name, value in sorted(observed.items())
        if name not in {"SHA256SUMS", "PAYLOAD.COMPLETE"}
    ]
    if manifest != expected_manifest:
        raise BuildError("payload checksum manifest mismatch")
    completion = f"sha256sums_sha256={sha256_bytes(observed['SHA256SUMS'])}\n".encode()
    if observed["PAYLOAD.COMPLETE"] != completion:
        raise BuildError("payload completion marker mismatch")
    if (
        len(observed[f"files/{CANDIDATE_DTB_NAME}"]) != CANDIDATE_DTB_SIZE
        or sha256_bytes(observed[f"files/{CANDIDATE_DTB_NAME}"]) != CANDIDATE_DTB_SHA256
        or len(observed[f"files/{BOOT_NAME}"]) != BOOT_SIZE
        or sha256_bytes(observed[f"files/{BOOT_NAME}"]) != BOOT_SHA256
    ):
        raise BuildError("payload BOOT artifact identity mismatch")
    if (
        len(observed["fallback-modules.sh"]) != FALLBACK_HELPER_SIZE
        or sha256_bytes(observed["fallback-modules.sh"]) != FALLBACK_HELPER_SHA256
        or len(observed["storage-health.sh"]) != STORAGE_HELPER_SIZE
        or sha256_bytes(observed["storage-health.sh"]) != STORAGE_HELPER_SHA256
    ):
        raise BuildError("payload reused-helper identity mismatch")
    transaction = observed["transaction.sh"].decode()
    installer = observed["install.sh"].decode()
    for marker in (
        f"readonly {CANDIDATE_VARIABLE_PREFIX}_DTB_SIZE={CANDIDATE_DTB_SIZE}",
        f"readonly {CANDIDATE_VARIABLE_PREFIX}_DTB_SHA256={CANDIDATE_DTB_SHA256}",
        f"readonly {CANDIDATE_VARIABLE_PREFIX}_BOOT_SIZE={BOOT_SIZE}",
        f"readonly {CANDIDATE_VARIABLE_PREFIX}_BOOT_SHA256={BOOT_SHA256}",
    ):
        if marker not in transaction:
            raise BuildError(f"payload transaction constant mismatch: {marker}")
    for marker in (
        f"readonly EXPECTED_BASE_P1_SHA256={BASE_P1_SHA256}",
        f"readonly EXPECTED_PREFIX_SHA256={PREFIX_SHA256}",
    ):
        if marker not in installer:
            raise BuildError(f"payload installer constant mismatch: {marker}")
    for name in ("install.sh", "transaction.sh", "fallback-modules.sh", "storage-health.sh"):
        syntax = subprocess.run(
            ["/bin/bash", "-n"],
            input=observed[name],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if syntax.returncode != 0:
            raise BuildError(f"payload bash syntax failed: {name}")
    return observed


def publish_generation(stage: Path, generation_name: str) -> Path:
    builds = RELEASE_ROOT / "builds"
    builds.mkdir(parents=True, exist_ok=True)
    destination = builds / generation_name
    if destination.exists() or destination.is_symlink():
        raise BuildError(f"generation already exists: {generation_name}")
    os.rename(stage, destination)
    pointer = RELEASE_ROOT / f".CURRENT.{os.getpid()}"
    write_new(pointer, f"{generation_name}\n".encode())
    os.replace(pointer, RELEASE_ROOT / "CURRENT")
    return destination


def exact_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise BuildError(f"not one JSON object: {path}")
    return value


def validate_generation() -> Path:
    current_path = RELEASE_ROOT / "CURRENT"
    current_metadata = require_regular(current_path, "CURRENT pointer")
    if stat.S_IMODE(current_metadata.st_mode) != 0o400:
        raise BuildError("CURRENT pointer mode mismatch")
    current = current_path.read_text(encoding="utf-8").strip()
    if GENERATION_RE.fullmatch(current) is None:
        raise BuildError("invalid CURRENT generation")
    generation = RELEASE_ROOT / "builds" / current
    generation_metadata = require_directory(generation, "generation")
    if stat.S_IMODE(generation_metadata.st_mode) != 0o700:
        raise BuildError("generation mode mismatch")
    if {entry.name for entry in generation.iterdir()} != GENERATION_MEMBERS:
        raise BuildError("generation member set mismatch")
    for member in generation.iterdir():
        metadata = require_regular(member, f"generation member {member.name}")
        if stat.S_IMODE(metadata.st_mode) != 0o400:
            raise BuildError(f"generation member mode mismatch: {member.name}")
    sums = file_manifest(generation, {"SHA256SUMS", "BUILD-COMPLETE"})
    if (generation / "SHA256SUMS").read_bytes() != sums:
        raise BuildError("generation checksum manifest mismatch")
    expected_complete = f"sha256sums_sha256={sha256_bytes(sums)}\n".encode()
    if (generation / "BUILD-COMPLETE").read_bytes() != expected_complete:
        raise BuildError("generation completion marker mismatch")
    receipt = exact_json(generation / "BUILD-RECEIPT.json")
    required = {
        "base_p1_sha256": BASE_P1_SHA256,
        "builder_image_id": DOCKER_IMAGE_ID,
        "candidate_dtb_sha256": CANDIDATE_DTB_SHA256,
        "candidate_dtb_size": CANDIDATE_DTB_SIZE,
        "docker_context": DOCKER_CONTEXT,
        "format_version": 1,
        "frozen_candidate_archive_sha256": FROZEN_CANDIDATE_SHA256,
        "payload_id": PAYLOAD_ID,
        "prefix_sha256": PREFIX_SHA256,
        "second_card_slot": "unavailable",
    }
    for key, value in required.items():
        if receipt.get(key) != value:
            raise BuildError(f"build receipt mismatch: {key}")
    for key, pattern in (
        ("archive_sha256", r"[0-9a-f]{64}"),
        ("source_git_commit", r"[0-9a-f]{40}"),
        ("source_git_tree", r"[0-9a-f]{40}"),
        ("source_manifest_sha256", r"[0-9a-f]{64}"),
    ):
        value = receipt.get(key)
        if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
            raise BuildError(f"build receipt identity mismatch: {key}")
    if not isinstance(receipt.get("archive_size"), int) or receipt["archive_size"] < 1:
        raise BuildError("build receipt archive size mismatch")
    source_manifest = (generation / "SOURCE-MANIFEST.json").read_bytes()
    if sha256_bytes(source_manifest) != receipt.get("source_manifest_sha256"):
        raise BuildError("source manifest digest mismatch")
    parsed_source = json.loads(source_manifest)
    if not isinstance(parsed_source, dict):
        raise BuildError("source manifest is not one object")
    if (
        parsed_source.get("git_commit") != receipt.get("source_git_commit")
        or parsed_source.get("git_tree") != receipt.get("source_git_tree")
    ):
        raise BuildError("source manifest Git identity mismatch")
    entries = parsed_source.get("files")
    if (
        parsed_source.get("format_version") != 1
        or parsed_source.get("file_count") != len(SOURCE_PATHS)
        or not isinstance(entries, list)
        or len(entries) != len(SOURCE_PATHS)
    ):
        raise BuildError("source manifest structure mismatch")
    source_entries = {
        entry.get("path"): entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    if set(source_entries) != set(SOURCE_PATHS):
        raise BuildError("source manifest path set mismatch")
    for relative, entry in source_entries.items():
        if (
            entry.get("git_mode") not in {"100644", "100755"}
            or not isinstance(entry.get("size"), int)
            or entry["size"] < 1
            or not isinstance(entry.get("sha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is None
        ):
            raise BuildError(f"source manifest entry mismatch: {relative}")
    archive = (generation / ARCHIVE_NAME).read_bytes()
    if len(archive) != receipt.get("archive_size") or sha256_bytes(archive) != receipt.get(
        "archive_sha256"
    ):
        raise BuildError("promotion archive receipt mismatch")
    files = validate_archive(archive)
    payload_source_map = {
        "install.sh": INSTALL_RELATIVE,
        "transaction.sh": TRANSACTION_RELATIVE,
        "fallback-modules.sh": FALLBACK_HELPER_RELATIVE,
        "storage-health.sh": STORAGE_HELPER_RELATIVE,
        f"files/{BOOT_NAME}": BOOT_RELATIVE,
    }
    for payload_name, source_name in payload_source_map.items():
        source = source_entries[source_name]
        source_blob = git_bytes(
            ["cat-file", "blob", f"{receipt['source_git_commit']}:{source_name}"]
        )
        if (
            len(source_blob) != source["size"]
            or sha256_bytes(source_blob) != source["sha256"]
        ):
            raise BuildError(f"Git/source manifest mismatch: {source_name}")
        expected_payload = render_payload_source(source_name, source_blob)
        if files[payload_name] != expected_payload:
            raise BuildError(f"payload/source render mismatch: {payload_name}")
    payload_info = json.loads(files["PAYLOAD-INFO.json"])
    expected_info = {
        "base_p1_sha256": BASE_P1_SHA256,
        "candidate_dtb_sha256": CANDIDATE_DTB_SHA256,
        "candidate_dtb_size": CANDIDATE_DTB_SIZE,
        "format_version": 1,
        "frozen_candidate_archive_sha256": FROZEN_CANDIDATE_SHA256,
        "payload_id": PAYLOAD_ID,
        "p2_baseline": "gaming-v0.5-full-rewrite",
        "prefix_sha256": PREFIX_SHA256,
        "second_card_slot": "unavailable",
        "source_git_commit": receipt["source_git_commit"],
        "source_git_tree": receipt["source_git_tree"],
        "target_boot_sha256": BOOT_SHA256,
        "target_release": "6.12.99-r46h-mainline-v0.15-gaming-product",
        "writes_p1_when_confirmed": True,
        "writes_uboot_environment": False,
    }
    if payload_info != expected_info:
        raise BuildError("payload info mismatch")
    candidate = files[f"files/{CANDIDATE_DTB_NAME}"]
    if receipt.get("v05_rootfs_contract") != verify_v05_rootfs_contract():
        raise BuildError("v0.5 rootfs contract receipt mismatch")
    require_toolchain()
    docker_verify_candidate(candidate)
    return generation


def command_build() -> Path:
    commit, tree, captured, source_manifest = capture_clean_source()
    toolchain = require_toolchain()
    candidate = read_frozen_candidate()
    docker_verify_candidate(candidate)
    check_script_constants(captured, candidate)
    v05_rootfs_contract = verify_v05_rootfs_contract()
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="work.", dir=CACHE_ROOT))
    stage = work / "generation"
    published = False
    try:
        payload_root = work / "payload"
        create_payload(payload_root, captured, candidate, commit, tree)
        archive = deterministic_archive(payload_root)
        if archive != deterministic_archive(payload_root):
            raise BuildError("promotion archive is not deterministic")
        validate_archive(archive)
        stage.mkdir(mode=0o700)
        write_new(stage / ARCHIVE_NAME, archive)
        write_new(stage / "SOURCE-MANIFEST.json", source_manifest)
        receipt = canonical_json(
            {
                "archive_sha256": sha256_bytes(archive),
                "archive_size": len(archive),
                "base_p1_sha256": BASE_P1_SHA256,
                "builder_image_id": DOCKER_IMAGE_ID,
                "candidate_dtb_sha256": CANDIDATE_DTB_SHA256,
                "candidate_dtb_size": CANDIDATE_DTB_SIZE,
                "docker_context": DOCKER_CONTEXT,
                "format_version": 1,
                "frozen_candidate_archive_sha256": FROZEN_CANDIDATE_SHA256,
                "payload_id": PAYLOAD_ID,
                "prefix_sha256": PREFIX_SHA256,
                "second_card_slot": "unavailable",
                "source_git_commit": commit,
                "source_git_tree": tree,
                "source_manifest_sha256": sha256_bytes(source_manifest),
                "v05_rootfs_contract": v05_rootfs_contract,
                **toolchain,
            }
        )
        write_new(stage / "BUILD-RECEIPT.json", receipt)
        sums = file_manifest(stage, {"SHA256SUMS", "BUILD-COMPLETE"})
        write_new(stage / "SHA256SUMS", sums)
        write_new(
            stage / "BUILD-COMPLETE",
            f"sha256sums_sha256={sha256_bytes(sums)}\n".encode(),
        )
        generation_name = f"build-{commit[:12]}-{sha256_bytes(archive)[:12]}"
        destination = publish_generation(stage, generation_name)
        published = True
        validate_generation()
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
            generation = command_build()
            receipt = exact_json(generation / "BUILD-RECEIPT.json")
            print(f"PASS: {VERSION_LABEL} BOOT promotion payload published at {generation}")
            print(f"ARCHIVE={generation / ARCHIVE_NAME}")
            print(f"ARCHIVE_SHA256={receipt['archive_sha256']}")
        else:
            generation = validate_generation()
            receipt = exact_json(generation / "BUILD-RECEIPT.json")
            print(
                f"PASS: {VERSION_LABEL} BOOT promotion generation validated at {generation}"
            )
            print(f"ARCHIVE_SHA256={receipt['archive_sha256']}")
    except (BuildError, OSError, tarfile.TarError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
