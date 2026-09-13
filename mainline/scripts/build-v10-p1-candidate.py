#!/usr/bin/env python3
"""Build a full offline BOOT p1 image containing a one-shot v0.10 candidate."""

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
import tempfile
import types
from typing import Any


P1_SIZE = 117_440_512
PROFILE_ID = "hl-r46h-v22-g92-31719424000-v1"
BUILD_ID = "v0.10-adc-full-range"
RELEASE = "6.12.99-r46h-mainline-v0.10-adc-full-range"
ARTIFACT_ID = "r46h-v0.10-p1-one-shot"
SOURCE_DATE_EPOCH = 1_785_369_600
OUTPUT_IMAGE_NAME = "p1-v0.10-one-shot.img"
EXPECTED_BASE_IMAGE_SHA256 = "800e3c9a9196c62a2c46726db694866091cbc396b7e156109e24ce7ef5ef9907"
V10_IMAGE_NAME = "Image.mainline-v0.10-adc-full-range.gz"
V10_BOOT_NAME = "boot.ini.v0.10-adc-full-range"
V10_DTB_NAME = "rk3326-r46h-mainline-v0.10-adc-full-range.dtb"
V08_DTB_NAME = "rk3326-r46h-mainline-v0.8-bootloader-handoff.dtb"
MINIMUM_FREE_BYTES = 512 * 1024
DEVICE_PREFIX = "/dev/"
V08_DTB_SIZE = 49_481
V08_DTB_SHA256 = "7259bac7bdd063fbaed987a0d5d2bf7066e02beaacc4440849b93d5f048e3dbc"
GENERATOR_RELPATH = "mainline/scripts/generate-easyroms-bundle.py"
BUILDER_RELPATH = "mainline/scripts/build-v10-p1-candidate.py"
PROFILE_RELPATH = "mainline/deploy/profiles/hl-r46h-v22-g92-31719424000-v1.json"
BASELINE_RELPATH = "mainline/deploy/baselines/v0.8-bootloader-handoff.json"
BOOT_TEMPLATE_RELPATH = "mainline/deploy/templates/boot.ini.in"
BUNDLE_NAME = "r46h-easyroms-v0.10-adc-full-range"
PACKAGE_NAME = "r46h-mainline-test-v0.10-adc-full-range"
PACKAGE_TAR_NAME = f"{PACKAGE_NAME}.tar.gz"
MAX_BUNDLE_FILE_BYTES = 256 * 1024 * 1024

REMOVED_FILES: dict[str, tuple[int, str]] = {
    "Image.mainline-v0.9-adc-joystick-fix.gz": (
        14_921_320,
        "8cf19559f3c55b5bfa7e77d556ad64667070e2e5be0c9c3305b0fdffb0101de2",
    ),
    "boot.ini.v0.9-adc-joystick-fix": (
        1_419,
        "cc4d1f7347a93985dcba027908325611cd530bf3bc1929bb2fbdeac43f8e12ce",
    ),
}

PRESERVED_V08_ANCHORS: dict[str, tuple[int, str]] = {
    "boot.ini": (
        1_427,
        "cead3fbee0d5c42fddcd6f6d83839b82af791e1abf1dd0252d9850fb47dd33fb",
    ),
    "boot.ini.v0.8-bootloader-handoff": (
        1_427,
        "cead3fbee0d5c42fddcd6f6d83839b82af791e1abf1dd0252d9850fb47dd33fb",
    ),
    "Image.mainline-v0.8-bootloader-handoff.gz": (
        14_920_864,
        "d7c7796c097fbe692412fb63d19c1f97c4b21f55ae2c3b1e8df324a739f166fa",
    ),
    V08_DTB_NAME: (V08_DTB_SIZE, V08_DTB_SHA256),
}

SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")


class BuildError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def require_safe_output_parent(path: Path, out_root: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    named_metadata = path.stat(follow_symlinks=False)
    if path.is_symlink() or not stat.S_ISDIR(named_metadata.st_mode):
        raise BuildError("output parent must be a non-symlink directory")
    resolved = path.resolve(strict=True)
    root = out_root.resolve(strict=True)
    if resolved != root and root not in resolved.parents:
        raise BuildError("output parent must stay below mainline/out")
    metadata = resolved.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise BuildError("output parent must be user-owned and not group/world writable")
    return resolved


def validate_input_clone(path: Path, out_root: Path) -> tuple[Path, tuple[int, ...], str]:
    if str(path).startswith(DEVICE_PREFIX):
        raise BuildError("a block-device input is forbidden; supply a full p1 clone file")
    resolved = path.resolve(strict=True)
    root = out_root.resolve(strict=True)
    if root not in resolved.parents:
        raise BuildError("input p1 clone must stay below mainline/out")
    metadata = resolved.stat(follow_symlinks=False)
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise BuildError("input p1 clone must be a regular non-symlink file")
    if metadata.st_size != P1_SIZE:
        raise BuildError(f"input p1 clone must be exactly {P1_SIZE} bytes")
    return resolved, stable_identity(metadata), sha256_file(resolved)


def render_v10_boot(
    template: bytes,
    *,
    compressed_image_size: int,
    uncompressed_image_size: int,
    dtb_size: int,
) -> bytes:
    if min(compressed_image_size, uncompressed_image_size, dtb_size) <= 0:
        raise BuildError("boot artifact sizes must be positive")
    replacements = {
        b"@BUILD_ID@": BUILD_ID.encode(),
        b"@FALLBACK_BOOT_PATH@": b"boot.ini.v0.8-bootloader-handoff",
        b"@ROOT_SPEC@": b"PARTUUID=c9f931c9-02",
        b"@CONSOLE@": b"ttyS2,115200n8",
        b"@IMAGE_NAME@": V10_IMAGE_NAME.encode(),
        b"@IMAGE_COMPRESSED_SIZE_HEX@": hex(compressed_image_size).encode(),
        b"@IMAGE_UNCOMPRESSED_SIZE_HEX@": hex(uncompressed_image_size).encode(),
        b"@DTB_NAME@": V10_DTB_NAME.encode(),
        b"@DTB_SIZE_HEX@": hex(dtb_size).encode(),
    }
    result = template
    for needle, value in replacements.items():
        if result.count(needle) < 1:
            raise BuildError(f"boot template placeholder missing: {needle.decode()}")
        result = result.replace(needle, value)
    if re.search(rb"@[A-Z0-9_]+@", result):
        raise BuildError("boot template contains an unresolved placeholder")
    try:
        text = result.decode("ascii")
    except UnicodeDecodeError as exc:
        raise BuildError("rendered v0.10 boot candidate is not ASCII") from exc
    required_fragments = (
        f"root=PARTUUID=c9f931c9-02",
        "console=ttyS2,115200n8",
        V10_IMAGE_NAME,
        V10_DTB_NAME,
        "boot.ini.v0.8-bootloader-handoff",
        f"itest ${{filesize}} -eq {hex(compressed_image_size)}",
        f"itest ${{filesize}} -eq {hex(uncompressed_image_size)}",
        f"itest ${{filesize}} -eq {hex(dtb_size)}",
    )
    if any(fragment not in text for fragment in required_fragments):
        raise BuildError("rendered v0.10 boot candidate safety contract mismatch")
    if "saveenv" in text:
        raise BuildError("rendered v0.10 boot candidate must not persist U-Boot state")
    return result


def parse_kv_bytes(raw: bytes, label: str) -> dict[str, str]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BuildError(f"{label} is not UTF-8") from exc
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if not line or "=" not in line:
            raise BuildError(f"malformed {label}")
        key, value = line.split("=", 1)
        if re.fullmatch(r"[a-z][a-z0-9_]*", key) is None or not value or key in fields:
            raise BuildError(f"invalid {label} field set")
        fields[key] = value
    return fields


def parse_stage_sums(raw: bytes) -> dict[str, str]:
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise BuildError("STAGE-SOURCES.sha256 is not UTF-8") from exc
    result: dict[str, str] = {}
    for line_number, line in enumerate(lines, 1):
        match = re.fullmatch(r"([0-9a-f]{64})  payload/([A-Za-z0-9._+-]+)", line)
        if match is None:
            raise BuildError(f"STAGE-SOURCES.sha256:{line_number}: malformed line")
        digest, name = match.groups()
        if name in result:
            raise BuildError(f"duplicate staged payload checksum: {name}")
        result[name] = digest
    if not result:
        raise BuildError("STAGE-SOURCES.sha256 is empty")
    return result


def import_deploy_generator(repo_root: Path) -> Any:
    generator_path = repo_root / GENERATOR_RELPATH
    metadata = generator_path.stat(follow_symlinks=False)
    if generator_path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise BuildError("canonical EASYROMS generator has an unsafe file type")
    module = types.ModuleType("r46h_easyroms_generator_for_p1")
    module.__file__ = str(generator_path)
    module.__package__ = ""
    try:
        code = compile(generator_path.read_bytes(), str(generator_path), "exec")
        exec(code, module.__dict__)
    except (ImportError, OSError, SyntaxError) as exc:
        raise BuildError("cannot import the canonical EASYROMS generator") from exc
    return module


def require_running_builder_matches_head(repo_root: Path, deploy: Any, head: str) -> str:
    deploy.require_unmasked_index_entries(repo_root, (BUILDER_RELPATH,))
    expected = deploy.require_head_blob(repo_root, head, BUILDER_RELPATH, "100755")
    script_path = Path(__file__).resolve(strict=True)
    if script_path != repo_root / BUILDER_RELPATH:
        raise BuildError(f"builder must run from {BUILDER_RELPATH} in its source repository")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(script_path, flags)
    try:
        before = os.fstat(descriptor)
        named = script_path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(before.st_mode)
            or (named.st_dev, named.st_ino) != (before.st_dev, before.st_ino)
            or stat.S_IMODE(before.st_mode) != 0o755
            or before.st_nlink != 1
            or before.st_uid != os.geteuid()
        ):
            raise BuildError("running p1 builder has unsafe identity, owner, mode, or link count")
        identity = stable_identity(before)
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            actual = handle.read()
        if stable_identity(os.fstat(descriptor)) != identity:
            raise BuildError("running p1 builder changed during provenance validation")
        if actual != expected:
            raise BuildError("running p1 builder does not match its exact HEAD blob")
    finally:
        os.close(descriptor)
    return hashlib.sha256(expected).hexdigest()


def require_bundle_directory(path: Path, out_root: Path) -> tuple[Path, Path, dict[str, tuple[int, ...]]]:
    if path.is_symlink():
        raise BuildError("EASYROMS bundle must be a non-symlink directory")
    resolved = path.resolve(strict=True)
    root = out_root.resolve(strict=True)
    if root not in resolved.parents:
        raise BuildError("EASYROMS bundle must stay below mainline/out")
    metadata = resolved.stat(follow_symlinks=False)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise BuildError("EASYROMS bundle directory is unsafe")
    root_entries = {entry.name: entry for entry in os.scandir(resolved)}
    if set(root_entries) != {"payload", "STAGE-SOURCES.sha256", "stage-on-macos.sh"}:
        raise BuildError("EASYROMS bundle root contains an unexpected entry set")
    payload = resolved / "payload"
    payload_metadata = payload.stat(follow_symlinks=False)
    if payload.is_symlink() or not stat.S_ISDIR(payload_metadata.st_mode):
        raise BuildError("EASYROMS payload directory is unsafe")
    states = {
        ".bundle": stable_identity(metadata),
        ".payload": stable_identity(payload_metadata),
    }
    return resolved, payload, states


def deterministic_gzip(data: bytes) -> bytes:
    with io.BytesIO() as buffer:
        with gzip.GzipFile(filename="", mode="wb", compresslevel=9, fileobj=buffer, mtime=0) as output:
            output.write(data)
        return buffer.getvalue()


def require_modules_only_bundle(repo_root: Path, bundle_dir: Path) -> dict[str, Any]:
    out_root = repo_root / "mainline/out"
    bundle, payload, states = require_bundle_directory(bundle_dir, out_root)
    sums_path = bundle / "STAGE-SOURCES.sha256"
    stage_script = bundle / "stage-on-macos.sh"
    for path, label in ((sums_path, "STAGE-SOURCES.sha256"), (stage_script, "stage-on-macos.sh")):
        metadata = path.stat(follow_symlinks=False)
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise BuildError(f"unsafe bundle {label}")
        states[f"root/{path.name}"] = stable_identity(metadata)
    sums_raw = sums_path.read_bytes()
    sums = parse_stage_sums(sums_raw)
    payload_entries = {entry.name: entry for entry in os.scandir(payload)}
    if set(payload_entries) != set(sums):
        raise BuildError("STAGE-SOURCES.sha256 does not cover the exact payload file set")

    payload_bytes: dict[str, bytes] = {}
    for name, expected_digest in sorted(sums.items()):
        path = payload / name
        metadata = path.stat(follow_symlinks=False)
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise BuildError(f"unsafe staged payload file: {name}")
        if metadata.st_size <= 0 or metadata.st_size > MAX_BUNDLE_FILE_BYTES:
            raise BuildError(f"staged payload file size is unsafe: {name}")
        data = path.read_bytes()
        if len(data) != metadata.st_size or hashlib.sha256(data).hexdigest() != expected_digest:
            raise BuildError(f"staged payload checksum mismatch: {name}")
        states[f"payload/{name}"] = stable_identity(metadata)
        payload_bytes[name] = data

    manifest = parse_kv_bytes(payload_bytes.get("DEPLOY-MANIFEST", b""), "DEPLOY-MANIFEST")
    required_manifest = {
        "format_version": "3",
        "target": "HL-R46H-V22",
        "build_id": BUILD_ID,
        "kernel_release": RELEASE,
        "action_policy": "install-modules-only",
        "allowed_actions": "install-modules",
        "package_name": PACKAGE_NAME,
        "payload_name": f"r46h-{BUILD_ID}",
        "canonical_tar": PACKAGE_TAR_NAME,
        "boot_image": V10_IMAGE_NAME,
        "boot_dtb": V10_DTB_NAME,
        "boot_candidate": V10_BOOT_NAME,
        "target_boot_switch": "disabled",
        "card_profile_id": PROFILE_ID,
        "current_baseline_id": "v0.8-bootloader-handoff",
        "current_release": "6.12.99-r46h-mainline-v0.8-bootloader-handoff",
        "current_active_path": "boot.ini",
        "current_candidate_path": "boot.ini.v0.8-bootloader-handoff",
        "current_image_path": "Image.mainline-v0.8-bootloader-handoff.gz",
        "current_dtb_path": V08_DTB_NAME,
    }
    for key, value in required_manifest.items():
        if manifest.get(key) != value:
            raise BuildError(f"modules-only DEPLOY-MANIFEST mismatch: {key}")
    required_names = {
        ".r46h-stage-owner",
        "DEPLOY-MANIFEST",
        "STAGE-COMPLETE",
        V10_IMAGE_NAME,
        V10_BOOT_NAME,
        V10_DTB_NAME,
        PACKAGE_TAR_NAME,
        "bootstrap-target.sh",
        "install-modules.sh",
        "target-common.sh",
    }
    if set(payload_bytes) != required_names or "switch-boot.sh" in payload_bytes:
        raise BuildError("modules-only bundle payload file set mismatch")

    deploy = import_deploy_generator(repo_root)
    package_path = payload / PACKAGE_TAR_NAME
    try:
        package = deploy.read_package(package_path)
        binding = deploy.establish_repository_binding(
            package,
            repo_root / PROFILE_RELPATH,
            repo_root / BASELINE_RELPATH,
        )
        card, card_sha = deploy.load_json_bytes(binding["blobs"][PROFILE_RELPATH], "card profile")
        baseline, baseline_sha = deploy.load_json_bytes(
            binding["blobs"][BASELINE_RELPATH], "current baseline"
        )
        deploy.validate_profiles(card, baseline)
    except deploy.BundleError as exc:
        raise BuildError(f"canonical bundle provenance validation failed: {exc}") from exc
    builder_sha = require_running_builder_matches_head(repo_root, deploy, binding["head"])

    if (
        package["build_id"] != BUILD_ID
        or package["release"] != RELEASE
        or package["package_name"] != PACKAGE_NAME
        or package["root_spec"] != "PARTUUID=c9f931c9-02"
        or package["console"] != "ttyS2,115200n8"
    ):
        raise BuildError("canonical package identity does not match the v0.10 p1 contract")
    if (
        manifest.get("source_git_commit") != package["source_git_commit"]
        or manifest.get("source_snapshot_sha256") != package["source_snapshot_sha256"]
        or manifest.get("source_git_commit") != binding["head"]
        or manifest.get("source_snapshot_sha256") != binding["snapshot_sha256"]
    ):
        raise BuildError("bundle source provenance does not match canonical package and HEAD")
    if (
        manifest.get("card_profile_sha256") != card_sha
        or manifest.get("current_baseline_sha256") != baseline_sha
    ):
        raise BuildError("bundle profile provenance mismatch")

    def require_manifest_file(name_key: str, size_key: str, sha_key: str) -> bytes:
        name = manifest.get(name_key, "")
        if name not in payload_bytes:
            raise BuildError(f"manifest payload name is missing: {name_key}")
        data = payload_bytes[name]
        if manifest.get(size_key) != str(len(data)) or manifest.get(sha_key) != hashlib.sha256(data).hexdigest():
            raise BuildError(f"manifest payload identity mismatch: {name_key}")
        return data

    canonical_tar = require_manifest_file("canonical_tar", "canonical_tar_size", "canonical_tar_sha256")
    if len(canonical_tar) != package["tar_size"] or hashlib.sha256(canonical_tar).hexdigest() != package["tar_sha256"]:
        raise BuildError("bundle canonical package identity mismatch")
    compressed_image = require_manifest_file("boot_image", "boot_image_size", "boot_image_sha256")
    if compressed_image != deterministic_gzip(package["image"]):
        raise BuildError("bundle boot Image is not the canonical deterministic gzip of the package Image")
    bundle_dtb = require_manifest_file("boot_dtb", "boot_dtb_size", "boot_dtb_sha256")
    if bundle_dtb != package["dtb"]:
        raise BuildError("bundle DTB does not match the canonical package DTB")
    if not bundle_dtb or hashlib.sha256(bundle_dtb).hexdigest() == V08_DTB_SHA256:
        raise BuildError("v0.10 package DTB does not carry a distinct candidate device tree")
    if (
        manifest.get("image_uncompressed_size") != str(len(package["image"]))
        or manifest.get("image_uncompressed_sha256") != hashlib.sha256(package["image"]).hexdigest()
    ):
        raise BuildError("bundle uncompressed Image identity mismatch")

    template = binding["blobs"].get(BOOT_TEMPLATE_RELPATH)
    if not isinstance(template, bytes):
        raise BuildError("repository binding lacks the committed boot template")

    # Re-read every staged byte and recheck directory/file identities after the
    # package and repository validation, closing same-UID replacement races.
    if parse_stage_sums(sums_path.read_bytes()) != sums:
        raise BuildError("STAGE-SOURCES.sha256 changed during provenance validation")
    if {entry.name for entry in os.scandir(payload)} != set(payload_bytes):
        raise BuildError("bundle payload entry set changed during provenance validation")
    for key, identity in states.items():
        if key == ".bundle":
            current = bundle.stat(follow_symlinks=False)
        elif key == ".payload":
            current = payload.stat(follow_symlinks=False)
        elif key.startswith("root/"):
            current = (bundle / key.removeprefix("root/")).stat(follow_symlinks=False)
        else:
            current = (payload / key.removeprefix("payload/")).stat(follow_symlinks=False)
        if stable_identity(current) != identity:
            raise BuildError(f"bundle source identity changed during validation: {key}")
    for name, expected in sums.items():
        if sha256_file(payload / name) != expected:
            raise BuildError(f"bundle payload changed during validation: {name}")
    try:
        deploy.recheck_repository_binding(binding)
    except deploy.BundleError as exc:
        raise BuildError(f"repository provenance changed during bundle validation: {exc}") from exc
    if require_running_builder_matches_head(repo_root, deploy, binding["head"]) != builder_sha:
        raise BuildError("running p1 builder identity changed during bundle validation")

    return {
        "deploy_helper": deploy,
        "bundle_path": bundle,
        "bundle_manifest_sha256": hashlib.sha256(payload_bytes["DEPLOY-MANIFEST"]).hexdigest(),
        "stage_sources_sha256": hashlib.sha256(sums_raw).hexdigest(),
        "source_git_commit": package["source_git_commit"],
        "source_snapshot_sha256": package["source_snapshot_sha256"],
        "canonical_tar_size": package["tar_size"],
        "canonical_tar_sha256": package["tar_sha256"],
        "canonical_image_size": len(package["image"]),
        "canonical_image_sha256": hashlib.sha256(package["image"]).hexdigest(),
        "compressed_image": compressed_image,
        "dtb": bundle_dtb,
        "dtb_size": len(bundle_dtb),
        "dtb_sha256": hashlib.sha256(bundle_dtb).hexdigest(),
        "boot_template": template,
        "builder_head_blob_sha256": builder_sha,
    }


LATE_REVALIDATION_KEYS = (
    "bundle_path",
    "bundle_manifest_sha256",
    "stage_sources_sha256",
    "source_git_commit",
    "source_snapshot_sha256",
    "canonical_tar_size",
    "canonical_tar_sha256",
    "canonical_image_size",
    "canonical_image_sha256",
    "compressed_image",
    "dtb",
    "dtb_size",
    "dtb_sha256",
    "boot_template",
    "builder_head_blob_sha256",
)


def revalidate_canonical_sources(
    repo_root: Path, bundle_dir: Path, initial: dict[str, Any]
) -> dict[str, Any]:
    current = require_modules_only_bundle(repo_root, bundle_dir)
    drifted = [key for key in LATE_REVALIDATION_KEYS if current.get(key) != initial.get(key)]
    if drifted:
        raise BuildError(f"canonical v0.10 sources drifted during p1 build: {drifted}")
    return current


def publish_candidate_noreplace(
    stage: Path,
    output_parent: Path,
    output_name: str,
    deploy: Any,
    expected_output_parent_identity: tuple[int, int],
) -> Path:
    if SAFE_NAME_RE.fullmatch(output_name) is None:
        raise BuildError("unsafe candidate publication name")
    source_parent = stage.parent
    source_name = stage.name
    source_parent_fd: int | None = None
    output_parent_fd: int | None = None
    stage_fd: int | None = None
    published = False
    try:
        source_parent_fd = deploy.open_verified_directory(
            source_parent, "p1 private publication parent"
        )
        output_parent_fd = deploy.open_verified_directory(
            output_parent, "p1 candidate output directory"
        )
        output_parent_identity = deploy.fd_identity(output_parent_fd, "directory")
        if output_parent_identity != expected_output_parent_identity:
            raise BuildError("p1 candidate output directory changed during build")
        stage_fd = deploy.open_verified_directory(stage, "p1 private candidate directory")
        stage_identity = deploy.fd_identity(stage_fd, "directory")
        deploy.verify_private_source_identity(
            source_parent_fd, source_name, stage_identity, "directory"
        )
        deploy.verify_directory_path_identity(
            output_parent, output_parent_identity, "p1 candidate output directory"
        )
        try:
            deploy.rename_noreplace_at(
                source_parent_fd,
                source_name,
                output_parent_fd,
                output_name,
            )
        except FileExistsError as exc:
            raise BuildError(
                "candidate output appeared during atomic no-replace publication"
            ) from exc
        published = True
        deploy.verify_published_identity(
            output_parent_fd, output_name, stage_identity, "directory"
        )
        deploy.verify_directory_path_identity(
            output_parent, output_parent_identity, "p1 candidate output directory"
        )
        return output_parent / output_name
    except BuildError:
        raise
    except deploy.BundleError as exc:
        suffix = " after publication; owned output retained" if published else ""
        raise BuildError(f"atomic candidate publication failed{suffix}: {exc}") from exc
    finally:
        for descriptor in (stage_fd, output_parent_fd, source_parent_fd):
            if descriptor is not None:
                os.close(descriptor)


def run_checked(command: list[str], log: Path | None = None) -> str:
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    if log is not None:
        log.write_text(result.stdout, encoding="utf-8")
    if result.returncode != 0:
        raise BuildError(f"command failed ({result.returncode}): {' '.join(command[:3])}")
    return result.stdout


def extract_fat(image: Path, destination: Path, log: Path) -> None:
    seven_zip = shutil.which("7zz") or shutil.which("7z")
    if seven_zip is None:
        raise BuildError("7zz is required for exact offline file-manifest validation")
    destination.mkdir(mode=0o700)
    run_checked([seven_zip, "x", "-y", "-bb1", f"-o{destination}", str(image)], log)


def scan_tree(root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    files: dict[str, dict[str, Any]] = {}
    directories: list[str] = []
    casefolded: dict[str, str] = {}
    for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        dirnames.sort()
        filenames.sort()
        for name in dirnames:
            candidate = current_path / name
            metadata = candidate.lstat()
            if not stat.S_ISDIR(metadata.st_mode) or candidate.is_symlink():
                raise BuildError(f"unsafe extracted directory entry: {candidate}")
            relative = candidate.relative_to(root).as_posix()
            validate_fat_path(relative)
            directories.append(relative)
        for name in filenames:
            candidate = current_path / name
            metadata = candidate.lstat()
            if not stat.S_ISREG(metadata.st_mode) or candidate.is_symlink():
                raise BuildError(f"unsafe extracted file entry: {candidate}")
            relative = candidate.relative_to(root).as_posix()
            validate_fat_path(relative)
            folded = relative.casefold()
            if folded in casefolded:
                raise BuildError(f"case-colliding FAT paths: {casefolded[folded]} and {relative}")
            casefolded[folded] = relative
            files[relative] = {"size": metadata.st_size, "sha256": sha256_file(candidate)}
    directories.sort()
    return files, directories


def validate_fat_path(relative: str) -> None:
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise BuildError(f"unsafe FAT path: {relative}")
    for component in path.parts:
        if component.startswith("._") or component == "__MACOSX" or "\x00" in component:
            raise BuildError(f"AppleDouble or unsafe FAT path is forbidden: {relative}")


def require_file_identity(
    manifest: dict[str, dict[str, Any]], expected: dict[str, tuple[int, str]], label: str
) -> None:
    for path, (size, digest) in expected.items():
        if manifest.get(path) != {"size": size, "sha256": digest}:
            raise BuildError(f"{label} identity mismatch: {path}")


def validate_exact_diff(
    before: dict[str, dict[str, Any]],
    after: dict[str, dict[str, Any]],
    before_directories: list[str],
    after_directories: list[str],
    added_files: dict[str, tuple[int, str]],
) -> dict[str, list[str]]:
    before_paths = set(before)
    after_paths = set(after)
    removed = sorted(before_paths - after_paths)
    added = sorted(after_paths - before_paths)
    changed = sorted(path for path in before_paths & after_paths if before[path] != after[path])
    if removed != sorted(REMOVED_FILES):
        raise BuildError(f"unexpected removed file set: {removed}")
    if added != sorted(added_files):
        raise BuildError(f"unexpected added file set: {added}")
    if changed:
        raise BuildError(f"pre-existing BOOT files changed unexpectedly: {changed}")
    if before_directories != after_directories:
        raise BuildError("BOOT directory set changed unexpectedly")
    require_file_identity(after, added_files, "added v0.10 file")
    require_file_identity(after, PRESERVED_V08_ANCHORS, "preserved v0.8 anchor")
    return {"added": added, "removed": removed, "changed": changed}


def ensure_builder_image(repo_root: Path, cache_root: Path, build_log: Path) -> tuple[str, str]:
    docker = shutil.which("docker")
    if docker is None:
        raise BuildError("Docker is required for direct-image mtools and fsck.fat")
    dockerfile = repo_root / "mainline/p1-candidate/Dockerfile"
    dockerfile_hash = sha256_file(dockerfile)
    iid_file = cache_root / "builder-image.iid"
    iid_file.unlink(missing_ok=True)
    command = [
        docker,
        "build",
        "--platform",
        "linux/arm64",
        "--iidfile",
        str(iid_file),
        "--tag",
        "arkos4clone/r46h-p1-builder:trixie-arm64",
        "--file",
        str(dockerfile),
        str(repo_root / "mainline"),
    ]
    run_checked(command, build_log)
    image_id = iid_file.read_text(encoding="utf-8").strip()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image_id) is None:
        raise BuildError("Docker did not return a pinned builder image ID")
    inspection = run_checked(
        [docker, "image", "inspect", image_id, "--format", "{{.Id}} {{.Architecture}}"]
    ).strip()
    if inspection != f"{image_id} arm64":
        raise BuildError("p1 builder image identity or architecture mismatch")
    return image_id, dockerfile_hash


def mutate_candidate_with_mtools(stage: Path, image_id: str, log: Path) -> None:
    docker = shutil.which("docker")
    assert docker is not None
    script = """set -euo pipefail
image=/work/candidate.img
mdel -i "$image" ::/Image.mainline-v0.9-adc-joystick-fix.gz
mdel -i "$image" ::/boot.ini.v0.9-adc-joystick-fix
mcopy -o -m -i "$image" /work/v10-image.gz ::/Image.mainline-v0.10-adc-full-range.gz
mcopy -o -m -i "$image" /work/v10-boot.ini ::/boot.ini.v0.10-adc-full-range
mcopy -o -m -i "$image" /work/v10.dtb ::/rk3326-r46h-mainline-v0.10-adc-full-range.dtb
fsck.fat -n -v "$image" > /work/fsck.fat.txt
mdir -i "$image" -/ ::/ > /work/mdir.txt
"""
    command = [
        docker,
        "run",
        "--rm",
        "--platform",
        "linux/arm64",
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=16m",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--volume",
        f"{stage}:/work:rw",
        "--entrypoint",
        "/bin/bash",
        image_id,
        "-c",
        script,
    ]
    run_checked(command, log)


def parse_free_bytes(mdir_log: Path) -> int:
    text = mdir_log.read_text(encoding="utf-8", errors="replace")
    matches = re.findall(r"([0-9][0-9 ,.]*[0-9]|[0-9]) bytes free", text)
    if not matches:
        raise BuildError("mtools did not report BOOT free space")
    digits = re.sub(r"[^0-9]", "", matches[-1])
    free = int(digits)
    if free < MINIMUM_FREE_BYTES:
        raise BuildError(f"candidate BOOT free space is too small: {free}")
    return free


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def build_candidate(
    repo_root: Path,
    input_path: Path,
    output_parent: Path,
    output_name: str,
    bundle_dir: Path | None = None,
) -> Path:
    if SAFE_NAME_RE.fullmatch(output_name) is None:
        raise BuildError("unsafe candidate output name")
    out_root = repo_root / "mainline/out"
    cache_root = require_safe_output_parent(out_root / ".cache", out_root)
    output_parent = require_safe_output_parent(output_parent, out_root)
    output_parent_metadata = output_parent.stat(follow_symlinks=False)
    output_parent_identity = (
        output_parent_metadata.st_dev,
        output_parent_metadata.st_ino,
    )
    final_dir = output_parent / output_name
    if final_dir.exists() or final_dir.is_symlink():
        raise BuildError(f"candidate output already exists: {final_dir}")

    source, source_identity, source_hash = validate_input_clone(input_path, out_root)
    if source_hash != EXPECTED_BASE_IMAGE_SHA256:
        raise BuildError("input p1 clone does not match the deployed v0.9 one-shot baseline")
    bundle_dir = bundle_dir or out_root / BUNDLE_NAME
    canonical = require_modules_only_bundle(repo_root, bundle_dir)
    compressed_image = canonical["compressed_image"]
    if not isinstance(compressed_image, bytes):
        raise BuildError("invalid internal compressed Image state")
    candidate_dtb = canonical["dtb"]
    if not isinstance(candidate_dtb, bytes):
        raise BuildError("invalid internal candidate DTB state")
    boot_data = render_v10_boot(
        canonical["boot_template"],
        compressed_image_size=len(compressed_image),
        uncompressed_image_size=canonical["canonical_image_size"],
        dtb_size=canonical["dtb_size"],
    )
    added_files = {
        V10_IMAGE_NAME: (len(compressed_image), hashlib.sha256(compressed_image).hexdigest()),
        V10_BOOT_NAME: (len(boot_data), hashlib.sha256(boot_data).hexdigest()),
        V10_DTB_NAME: (len(candidate_dtb), hashlib.sha256(candidate_dtb).hexdigest()),
    }
    source_state = {
        "input_p1": {"path": str(source), "size": P1_SIZE, "sha256": source_hash},
        "modules_only_bundle": {
            "path": str(canonical["bundle_path"]),
            "deploy_manifest_sha256": canonical["bundle_manifest_sha256"],
            "stage_sources_sha256": canonical["stage_sources_sha256"],
        },
        "canonical_package": {
            "size": canonical["canonical_tar_size"],
            "sha256": canonical["canonical_tar_sha256"],
            "source_git_commit": canonical["source_git_commit"],
            "source_snapshot_sha256": canonical["source_snapshot_sha256"],
        },
        "canonical_image": {
            "size": canonical["canonical_image_size"],
            "sha256": canonical["canonical_image_sha256"],
        },
        "canonical_dtb": {
            "size": canonical["dtb_size"],
            "sha256": canonical["dtb_sha256"],
            "candidate_path": V10_DTB_NAME,
        },
        "p1_builder": {
            "head_blob_sha256": canonical["builder_head_blob_sha256"],
        },
        "boot_template": {
            "repository_path": BOOT_TEMPLATE_RELPATH,
            "size": len(canonical["boot_template"]),
            "sha256": hashlib.sha256(canonical["boot_template"]).hexdigest(),
        },
    }

    with tempfile.TemporaryDirectory(prefix=".r46h-v10-p1-build.", dir=cache_root) as temporary:
        work = Path(temporary)
        work.chmod(0o700)
        stage = work / "publication"
        stage.mkdir(mode=0o700)
        receipt = stage / "receipt"
        receipt.mkdir(mode=0o700)
        candidate = work / "candidate.img"
        shutil.copyfile(source, candidate)
        candidate.chmod(0o600)
        if sha256_file(candidate) != source_hash:
            raise BuildError("private p1 copy does not match the input clone")

        before_tree = work / "before-tree"
        extract_fat(candidate, before_tree, receipt / "7zz-before.txt")
        before, before_directories = scan_tree(before_tree)
        require_file_identity(before, REMOVED_FILES, "retired v0.9 candidate file")
        require_file_identity(before, PRESERVED_V08_ANCHORS, "required v0.8 anchor")
        for new_path in added_files:
            if new_path in before:
                raise BuildError(f"v0.10 destination already exists in input clone: {new_path}")

        gzip_path = work / "v10-image.gz"
        gzip_path.write_bytes(compressed_image)
        gzip_path.chmod(0o600)
        os.utime(gzip_path, (SOURCE_DATE_EPOCH, SOURCE_DATE_EPOCH), follow_symlinks=False)
        boot_path = work / "v10-boot.ini"
        boot_path.write_bytes(boot_data)
        boot_path.chmod(0o600)
        os.utime(boot_path, (SOURCE_DATE_EPOCH, SOURCE_DATE_EPOCH), follow_symlinks=False)
        dtb_path = work / "v10.dtb"
        dtb_path.write_bytes(candidate_dtb)
        dtb_path.chmod(0o600)
        os.utime(dtb_path, (SOURCE_DATE_EPOCH, SOURCE_DATE_EPOCH), follow_symlinks=False)

        image_id, dockerfile_hash = ensure_builder_image(
            repo_root, work, receipt / "docker-build.txt"
        )
        mutate_candidate_with_mtools(work, image_id, receipt / "mtools-mutation.txt")
        shutil.copyfile(work / "fsck.fat.txt", receipt / "fsck.fat.txt")
        shutil.copyfile(work / "mdir.txt", receipt / "mdir.txt")
        free_bytes = parse_free_bytes(receipt / "mdir.txt")

        if sys.platform == "darwin" and Path("/sbin/fsck_msdos").is_file():
            run_checked(
                ["/sbin/fsck_msdos", "-n", str(candidate)],
                receipt / "fsck_msdos.txt",
            )

        after_tree = work / "after-tree"
        extract_fat(candidate, after_tree, receipt / "7zz-after.txt")
        after, after_directories = scan_tree(after_tree)
        diff = validate_exact_diff(
            before,
            after,
            before_directories,
            after_directories,
            added_files,
        )

        current_source = source.stat(follow_symlinks=False)
        if stable_identity(current_source) != source_identity or sha256_file(source) != source_hash:
            raise BuildError("input p1 clone changed while building the candidate")
        candidate_hash = sha256_file(candidate)

        write_json(receipt / "FILES-BEFORE.json", before)
        write_json(receipt / "FILES-AFTER.json", after)
        write_json(receipt / "DIRECTORIES-BEFORE.json", before_directories)
        write_json(receipt / "DIRECTORIES-AFTER.json", after_directories)
        write_json(receipt / "DIFF.json", diff)
        source_state["builder"] = {
            "docker_image_id": image_id,
            "dockerfile_sha256": dockerfile_hash,
            "network_during_mutation": "none",
            "block_devices_opened": 0,
        }
        write_json(receipt / "SOURCE-INFO.json", source_state)
        (receipt / V10_IMAGE_NAME).write_bytes(gzip_path.read_bytes())
        (receipt / V10_BOOT_NAME).write_bytes(boot_data)
        (receipt / V10_DTB_NAME).write_bytes(candidate_dtb)
        for path in (
            receipt / V10_IMAGE_NAME,
            receipt / V10_BOOT_NAME,
            receipt / V10_DTB_NAME,
        ):
            path.chmod(0o600)

        published_image = stage / OUTPUT_IMAGE_NAME
        shutil.copyfile(candidate, published_image)
        published_image.chmod(0o600)
        if sha256_file(published_image) != candidate_hash:
            raise BuildError("published candidate copy SHA-256 mismatch")
        status = {
            "format_version": 1,
            "state": "BUILD_COMPLETE",
            "artifact_id": ARTIFACT_ID,
            "profile_id": PROFILE_ID,
            "build_id": BUILD_ID,
            "kernel_release": RELEASE,
            "image_name": OUTPUT_IMAGE_NAME,
            "image_size": P1_SIZE,
            "image_sha256": candidate_hash,
            "base_image_sha256": source_hash,
            "active_boot_ini_unchanged": True,
            "v08_dtb_reused": False,
            "added_files": sorted(added_files),
            "removed_files": sorted(REMOVED_FILES),
            "changed_preexisting_files": [],
            "free_bytes": free_bytes,
            "fsck_fat_read_only_passed": True,
            "block_devices_opened": 0,
        }
        write_json(stage / "BUILD-STATUS.json", status)
        (stage / "SHA256SUMS").write_text(
            f"{candidate_hash}  {OUTPUT_IMAGE_NAME}\n"
            f"{added_files[V10_IMAGE_NAME][1]}  receipt/{V10_IMAGE_NAME}\n"
            f"{added_files[V10_BOOT_NAME][1]}  receipt/{V10_BOOT_NAME}\n"
            f"{added_files[V10_DTB_NAME][1]}  receipt/{V10_DTB_NAME}\n",
            encoding="utf-8",
        )
        (stage / "SHA256SUMS").chmod(0o600)
        late_canonical = revalidate_canonical_sources(repo_root, bundle_dir, canonical)
        current_source = source.stat(follow_symlinks=False)
        if stable_identity(current_source) != source_identity or sha256_file(source) != source_hash:
            raise BuildError("input p1 clone changed before candidate publication")
        published = publish_candidate_noreplace(
            stage,
            output_parent,
            output_name,
            late_canonical["deploy_helper"],
            output_parent_identity,
        )
        if published != final_dir:
            raise BuildError("internal candidate publication path mismatch")

    print("PASS: offline full-p1 v0.10 one-shot candidate built.")
    print("PHYSICAL_BLOCK_DEVICES_OPENED=0")
    print("ACTIVE_BOOT_INI=unchanged-v0.8")
    print("CANDIDATE_DTB=separate-v0.10")
    print(f"CANDIDATE_DIR={final_dir}")
    print(f"P1_IMAGE={final_dir / OUTPUT_IMAGE_NAME}")
    print(f"P1_IMAGE_SHA256={candidate_hash}")
    print(f"FREE_BYTES={free_bytes}")
    return final_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-p1", required=True, type=Path)
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        help=(
            "clean-HEAD install-modules-only EASYROMS bundle; defaults to "
            "mainline/out/r46h-easyroms-v0.10-adc-full-range"
        ),
    )
    parser.add_argument("--output-parent", type=Path)
    parser.add_argument("--output-name", default=ARTIFACT_ID)
    return parser.parse_args()


def main() -> int:
    try:
        repo_root = Path(__file__).resolve(strict=True).parents[2]
        args = parse_args()
        output_parent = args.output_parent or repo_root / "mainline/out/r46h-v10-p1-candidates"
        build_candidate(
            repo_root,
            args.input_p1,
            output_parent,
            args.output_name,
            args.bundle_dir,
        )
    except (BuildError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
