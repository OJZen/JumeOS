#!/usr/bin/env python3
"""Build and validate the immutable R46H v0.10 target installer release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
CACHE_PARENT = REPO / "mainline/out/.cache"
DEFAULT_CACHE = CACHE_PARENT / "r46h-v10-target-installer-build"
RELEASE_ROOT = REPO / "mainline/out/r46h-v10-target-installer"
DOCKER_IMAGE = "arkos4clone/r46h-kernel-builder:trixie-arm64"
DOCKER_IMAGE_ID = (
    "sha256:ead0163117edba9667137b8e65c560b11326ccb54002871d308fa340ddc1fc31"
)
RUST_PACKAGE_VERSION = "1.85.0+dfsg3-1"
BINARY_NAME = "r46h-v10-target-installer"
SOURCE_DATE_EPOCH = "1785369600"
MODULE_PACKAGE = REPO / "mainline/out/r46h-mainline-test-v0.10-adc-full-range.tar.gz"
MODULE_PACKAGE_SIZE = 33_258_814
MODULE_PACKAGE_SHA256 = (
    "c4350520f7ad33ecf7b50f67c42985e2ce26c1c38d050ad50601c3538cebc780"
)
SOURCE_PATHS = (
    "mainline/scripts/build-r46h-v10-target-installer.py",
    "mainline/tests/test-v10-target-installer-build.py",
    "mainline/tools/r46h-v10-target-installer/Cargo.lock",
    "mainline/tools/r46h-v10-target-installer/Cargo.toml",
    "mainline/tools/r46h-v10-target-installer/README.md",
    "mainline/tools/r46h-v10-target-installer/src/lib.rs",
    "mainline/tools/r46h-v10-target-installer/src/linux.rs",
    "mainline/tools/r46h-v10-target-installer/src/main.rs",
)
GENERATION_MEMBERS = {
    BINARY_NAME,
    "BUILD-RECEIPT.json",
    "SHA256SUMS",
    "SOURCE-MANIFEST.json",
}


class BuildError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def git_environment() -> dict[str, str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") and key not in {"CDPATH", "ENV", "BASH_ENV"}
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
        ["/usr/bin/git", "-C", str(repo), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=git_environment(),
    )
    if result.returncode != 0:
        raise BuildError(
            f"git {' '.join(arguments)} failed: {result.stderr.decode(errors='replace').strip()}"
        )
    return result.stdout


def require_clean_snapshot(
    repo: Path = REPO, source_paths: tuple[str, ...] = SOURCE_PATHS
) -> tuple[str, str, dict[str, bytes], bytes]:
    status = git_bytes(
        ["status", "--porcelain=v1", "--untracked-files=all", "--", *source_paths],
        repo,
    )
    if status:
        raise BuildError("installer source scope has staged, unstaged, or untracked changes")
    commit = git_bytes(["rev-parse", "HEAD"], repo).decode().strip()
    tree = git_bytes(["rev-parse", "HEAD^{tree}"], repo).decode().strip()
    captured: dict[str, bytes] = {}
    entries: list[dict[str, object]] = []
    for relative in source_paths:
        live = repo / relative
        metadata = live.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise BuildError(f"unsafe source file identity: {relative}")
        tree_line = git_bytes(["ls-tree", "HEAD", "--", relative], repo).decode().strip()
        fields = tree_line.split(None, 3)
        if len(fields) != 4 or fields[1] != "blob" or fields[3] != relative:
            raise BuildError(f"source path is not one committed blob: {relative}")
        blob = git_bytes(["cat-file", "blob", f"HEAD:{relative}"], repo)
        if live.read_bytes() != blob:
            raise BuildError(f"live source differs from HEAD blob: {relative}")
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


def safe_cache_root(raw: str | None) -> Path:
    path = Path(raw).expanduser() if raw else DEFAULT_CACHE
    if not path.is_absolute():
        raise BuildError("cache root must be absolute")
    path = path.resolve(strict=False)
    parent = CACHE_PARENT.resolve()
    try:
        path.relative_to(parent)
    except ValueError as error:
        raise BuildError(f"cache root must remain below {parent}") from error
    if path == parent:
        raise BuildError("cache root must be a dedicated child")
    return path


def verify_runtime_module_package(
    path: Path = MODULE_PACKAGE,
    expected_size: int = MODULE_PACKAGE_SIZE,
    expected_sha256: str = MODULE_PACKAGE_SHA256,
) -> dict[str, object]:
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size != expected_size
        or sha256_file(path) != expected_sha256
    ):
        raise BuildError("runtime v0.10 module package identity mismatch")
    return {
        "name": path.name,
        "sha256": expected_sha256,
        "size": expected_size,
    }


def write_snapshot(root: Path, captured: dict[str, bytes]) -> Path:
    source = root / "source"
    source.mkdir(mode=0o700)
    for relative, value in captured.items():
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
    return source


def seed_cargo_home(destination: Path) -> None:
    source = REPO / "mainline/out/.cache/r46h-card-toolchain/cargo-home"
    if not source.is_dir() or source.is_symlink():
        raise BuildError(f"missing safe offline Cargo cache: {source}")
    allowed = {".global-cache", ".package-cache", ".package-cache-mutate", "registry"}
    observed = {entry.name for entry in source.iterdir()}
    if observed != allowed or any(
        name.casefold() in {"config", "config.toml"} for name in observed
    ):
        raise BuildError(f"offline Cargo cache member set mismatch: {sorted(observed)}")
    device = source.stat().st_dev
    for path in [source, *source.rglob("*")]:
        metadata = path.lstat()
        if metadata.st_dev != device or not (
            stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)
        ):
            raise BuildError(f"unsafe offline Cargo cache entry: {path}")
    shutil.copytree(source, destination, symlinks=False)


def run_host_rust_gates(work: Path, source: Path) -> None:
    cargo = shutil.which("cargo")
    if not cargo:
        raise BuildError("host cargo is unavailable")
    environment = {
        "CARGO_HOME": str(work / "cargo-home"),
        "CARGO_INCREMENTAL": "0",
        "CARGO_NET_OFFLINE": "true",
        "CARGO_TARGET_DIR": str(work / "host-target"),
        "HOME": os.environ.get("HOME", "/var/empty"),
        "LC_ALL": "C",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "SOURCE_DATE_EPOCH": SOURCE_DATE_EPOCH,
    }
    manifest = "mainline/tools/r46h-v10-target-installer/Cargo.toml"
    commands = (
        [cargo, "test", "--manifest-path", manifest, "--locked", "--offline"],
        [
            cargo,
            "clippy",
            "--manifest-path",
            manifest,
            "--all-targets",
            "--locked",
            "--offline",
            "--",
            "-D",
            "warnings",
        ],
        [cargo, "fmt", "--manifest-path", manifest, "--", "--check"],
    )
    for command in commands:
        result = subprocess.run(command, cwd=source, env=environment, check=False)
        if result.returncode != 0:
            raise BuildError(f"host Rust gate failed with status {result.returncode}: {command[1]}")


def docker_image_identity() -> None:
    result = subprocess.run(
        [
            "/usr/local/bin/docker",
            "image",
            "inspect",
            DOCKER_IMAGE,
            "--format",
            "{{.Id}} {{.Architecture}} {{.Os}}",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    expected = f"{DOCKER_IMAGE_ID} arm64 linux"
    if result.returncode != 0 or result.stdout.strip() != expected:
        raise BuildError(
            f"Docker image identity mismatch: expected {expected!r}, got {result.stdout.strip()!r}"
        )


def run_container(work: Path, source: Path, module_package: Path) -> tuple[Path, bytes]:
    cargo_home = work / "cargo-home"
    test_cache = work / "test-cache"
    test_cache.mkdir(mode=0o700)
    for name in ("target-test", "target-a", "target-b"):
        (work / name).mkdir(mode=0o700)
    script = f"""set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  cargo={RUST_PACKAGE_VERSION} rustc={RUST_PACKAGE_VERSION}
dpkg-query -W -f='${{Package}} ${{Version}}\\n' | LC_ALL=C sort > /work/RUST-PACKAGES
cd /repo
export CARGO_HOME=/cargo-home CARGO_NET_OFFLINE=true CARGO_INCREMENTAL=0
export SOURCE_DATE_EPOCH={SOURCE_DATE_EPOCH}
export CARGO_TARGET_DIR=/work/target-test
export R46H_V10_MODULE_PACKAGE=/runtime/r46h-v0.10-modules.tar.gz
cargo test --manifest-path mainline/tools/r46h-v10-target-installer/Cargo.toml --locked --offline
RUSTFLAGS=-Dwarnings cargo check --manifest-path mainline/tools/r46h-v10-target-installer/Cargo.toml --all-targets --locked --offline
for target in target-a target-b; do
  CARGO_TARGET_DIR=/work/$target RUSTFLAGS='-C debuginfo=0 -C strip=symbols -Dwarnings' \
    cargo build --manifest-path mainline/tools/r46h-v10-target-installer/Cargo.toml --release --locked --offline
done
"""
    command = [
        "/usr/local/bin/docker",
        "run",
        "--rm",
        "--entrypoint",
        "/bin/bash",
        "-v",
        f"{source}:/repo:ro",
        "-v",
        f"{work}:/work",
        "-v",
        f"{cargo_home}:/cargo-home",
        "-v",
        f"{test_cache}:/repo/mainline/out/.cache/r46h-v10-target-installer/tests",
        "-v",
        f"{module_package}:/runtime/r46h-v0.10-modules.tar.gz:ro",
        DOCKER_IMAGE,
        "-lc",
        script,
    ]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise BuildError(f"Linux/aarch64 container build failed with status {result.returncode}")
    first = work / f"target-a/release/{BINARY_NAME}"
    second = work / f"target-b/release/{BINARY_NAME}"
    first_bytes = first.read_bytes()
    if first_bytes != second.read_bytes():
        raise BuildError("two clean release builds are not byte-for-byte reproducible")
    verify_aarch64_elf(first_bytes)
    packages = (work / "RUST-PACKAGES").read_bytes()
    return first, packages


def verify_aarch64_elf(value: bytes) -> None:
    if (
        len(value) < 64
        or value[:6] != b"\x7fELF\x02\x01"
        or int.from_bytes(value[16:18], "little") != 3
        or int.from_bytes(value[18:20], "little") != 183
    ):
        raise BuildError("release is not one little-endian AArch64 PIE ELF binary")


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_generation(
    work: Path,
    binary: Path,
    manifest: bytes,
    commit: str,
    tree: str,
    packages: bytes,
    runtime_input: dict[str, object],
) -> Path:
    binary_bytes = binary.read_bytes()
    binary_sha = sha256_bytes(binary_bytes)
    manifest_sha = sha256_bytes(manifest)
    receipt = canonical_json(
        {
            "artifact": {
                "name": BINARY_NAME,
                "sha256": binary_sha,
                "size": len(binary_bytes),
            },
            "build": {
                "built_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "docker_image": DOCKER_IMAGE,
                "docker_image_id": DOCKER_IMAGE_ID,
                "reproducible_builds": 2,
                "rust_packages": packages.decode().splitlines(),
                "source_date_epoch": int(SOURCE_DATE_EPOCH),
            },
            "format_version": 1,
            "runtime_input": runtime_input,
            "source": {
                "file_count": len(SOURCE_PATHS),
                "git_commit": commit,
                "git_tree": tree,
                "manifest_sha256": manifest_sha,
            },
        }
    )
    members = {
        BINARY_NAME: binary_bytes,
        "BUILD-RECEIPT.json": receipt,
        "SOURCE-MANIFEST.json": manifest,
    }
    sums = "".join(
        f"{sha256_bytes(value)}  {name}\n" for name, value in sorted(members.items())
    ).encode()
    members["SHA256SUMS"] = sums
    generation_name = f"build-{commit[:12]}-{binary_sha[:12]}"
    stage = work / generation_name
    stage.mkdir(mode=0o700)
    for name, value in members.items():
        mode = 0o755 if name == BINARY_NAME else 0o644
        descriptor = os.open(stage / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
    fsync_directory(stage)
    RELEASE_ROOT.mkdir(parents=True, exist_ok=True, mode=0o755)
    builds = RELEASE_ROOT / "builds"
    builds.mkdir(exist_ok=True, mode=0o755)
    generation = builds / generation_name
    if generation.exists():
        validate_generation(generation, commit)
        shutil.rmtree(stage)
    else:
        os.rename(stage, generation)
        fsync_directory(builds)
    current_value = canonical_json(
        {
            "format_version": 1,
            "generation": generation_name,
            "sha256sums_sha256": sha256_bytes(sums),
        }
    )
    temporary = RELEASE_ROOT / f".CURRENT.{uuid.uuid4().hex}"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(current_value)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, RELEASE_ROOT / "CURRENT")
    fsync_directory(RELEASE_ROOT)
    validate_generation(generation, commit)
    return generation


def load_exact_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        raise BuildError(f"invalid JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise BuildError(f"JSON root is not an object: {path}")
    return value


def validate_generation(
    generation: Path, expected_commit: str | None = None, repo: Path = REPO
) -> None:
    metadata = generation.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or generation.is_symlink():
        raise BuildError("release generation is not one direct directory")
    names = {entry.name for entry in generation.iterdir()}
    if names != GENERATION_MEMBERS:
        raise BuildError(f"release member set mismatch: {sorted(names)}")
    for name in names:
        metadata = (generation / name).lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise BuildError(f"unsafe release member identity: {name}")
    sums = (generation / "SHA256SUMS").read_text().splitlines()
    expected_lines = [
        f"{sha256_file(generation / name)}  {name}"
        for name in sorted(GENERATION_MEMBERS - {"SHA256SUMS"})
    ]
    if sums != expected_lines:
        raise BuildError("SHA256SUMS does not bind the exact release members")
    binary = (generation / BINARY_NAME).read_bytes()
    verify_aarch64_elf(binary)
    receipt = load_exact_json(generation / "BUILD-RECEIPT.json")
    manifest_bytes = (generation / "SOURCE-MANIFEST.json").read_bytes()
    manifest = load_exact_json(generation / "SOURCE-MANIFEST.json")
    if set(receipt) != {
        "artifact",
        "build",
        "format_version",
        "runtime_input",
        "source",
    } or set(
        manifest
    ) != {"file_count", "files", "format_version", "git_commit", "git_tree"}:
        raise BuildError("release receipt or source manifest key set mismatch")
    if receipt.get("format_version") != 1 or manifest.get("format_version") != 1:
        raise BuildError("release format version mismatch")
    source = receipt.get("source")
    artifact = receipt.get("artifact")
    build = receipt.get("build")
    runtime_input = receipt.get("runtime_input")
    if (
        not isinstance(source, dict)
        or not isinstance(artifact, dict)
        or not isinstance(build, dict)
        or not isinstance(runtime_input, dict)
        or set(source) != {"file_count", "git_commit", "git_tree", "manifest_sha256"}
        or set(artifact) != {"name", "sha256", "size"}
        or set(build)
        != {
            "built_utc",
            "docker_image",
            "docker_image_id",
            "reproducible_builds",
            "rust_packages",
            "source_date_epoch",
        }
        or set(runtime_input) != {"name", "sha256", "size"}
    ):
        raise BuildError("receipt source/artifact is malformed")
    commit = manifest.get("git_commit")
    if expected_commit is not None and commit != expected_commit:
        raise BuildError("release commit does not match current clean source commit")
    observed_tree = git_bytes(["rev-parse", f"{commit}^{{tree}}"], repo).decode().strip()
    if manifest.get("git_tree") != observed_tree:
        raise BuildError("source manifest Git tree mismatch")
    if (
        source.get("git_commit") != commit
        or source.get("git_tree") != manifest.get("git_tree")
        or source.get("file_count") != manifest.get("file_count")
        or source.get("manifest_sha256") != sha256_bytes(manifest_bytes)
        or artifact.get("name") != BINARY_NAME
        or artifact.get("size") != len(binary)
        or artifact.get("sha256") != sha256_bytes(binary)
        or build.get("docker_image") != DOCKER_IMAGE
        or build.get("docker_image_id") != DOCKER_IMAGE_ID
        or build.get("reproducible_builds") != 2
        or build.get("source_date_epoch") != int(SOURCE_DATE_EPOCH)
        or not isinstance(build.get("rust_packages"), list)
        or runtime_input
        != {
            "name": MODULE_PACKAGE.name,
            "sha256": MODULE_PACKAGE_SHA256,
            "size": MODULE_PACKAGE_SIZE,
        }
    ):
        raise BuildError("release receipt closure mismatch")
    if generation.name != f"build-{str(commit)[:12]}-{sha256_bytes(binary)[:12]}":
        raise BuildError("release generation name mismatch")
    entries = manifest.get("files")
    if not isinstance(entries, list) or len(entries) != len(SOURCE_PATHS):
        raise BuildError("source manifest file list mismatch")
    if [entry.get("path") for entry in entries if isinstance(entry, dict)] != list(
        SOURCE_PATHS
    ):
        raise BuildError("source manifest path order/scope mismatch")
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"git_mode", "path", "sha256", "size"}:
            raise BuildError("malformed source manifest entry")
        path = entry["path"]
        tree_line = git_bytes(["ls-tree", str(commit), "--", str(path)], repo).decode().strip()
        fields = tree_line.split(None, 3)
        if (
            len(fields) != 4
            or fields[1] != "blob"
            or fields[3] != path
            or entry.get("git_mode") != fields[0]
        ):
            raise BuildError(f"source manifest Git mode/path mismatch: {path}")
        blob = git_bytes(["cat-file", "blob", f"{commit}:{path}"], repo)
        if entry.get("size") != len(blob) or entry.get("sha256") != sha256_bytes(blob):
            raise BuildError(f"source manifest Git blob mismatch: {path}")


def command_build(cache_root: Path) -> None:
    commit, tree, captured, manifest = require_clean_snapshot()
    runtime_input = verify_runtime_module_package()
    docker_image_identity()
    work_parent = cache_root / "work"
    work_parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    work = work_parent / f"build-{uuid.uuid4().hex}"
    work.mkdir(mode=0o700)
    try:
        source = write_snapshot(work, captured)
        test_environment = os.environ.copy()
        test_environment["PYTHONDONTWRITEBYTECODE"] = "1"
        test_result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(source / "mainline/tests/test-v10-target-installer-build.py"),
                "-v",
            ],
            cwd=source,
            env=test_environment,
            check=False,
        )
        if test_result.returncode != 0:
            raise BuildError("snapshot build-driver tests failed")
        for relative, expected in captured.items():
            if (source / relative).read_bytes() != expected:
                raise BuildError(f"snapshot source changed during host gates: {relative}")
        seed_cargo_home(work / "cargo-home")
        run_host_rust_gates(work, source)
        (source / "mainline/out/.cache/r46h-v10-target-installer/tests").mkdir(
            parents=True, exist_ok=True, mode=0o700
        )
        binary, packages = run_container(work, source, MODULE_PACKAGE)
        generation = publish_generation(
            work, binary, manifest, commit, tree, packages, runtime_input
        )
        print(f"PASS: immutable v0.10 target installer release published at {generation}")
        print(f"BINARY_SHA256={sha256_file(generation / BINARY_NAME)}")
    finally:
        if work.exists():
            shutil.rmtree(work)
        if work_parent.exists() and not any(work_parent.iterdir()):
            work_parent.rmdir()


def command_validate() -> None:
    commit, _, _, _ = require_clean_snapshot()
    current = load_exact_json(RELEASE_ROOT / "CURRENT")
    if set(current) != {"format_version", "generation", "sha256sums_sha256"}:
        raise BuildError("CURRENT key set mismatch")
    generation_name = current.get("generation")
    if not isinstance(generation_name, str) or not generation_name.startswith("build-"):
        raise BuildError("CURRENT generation name is malformed")
    generation = RELEASE_ROOT / "builds" / generation_name
    validate_generation(generation, commit)
    if current.get("sha256sums_sha256") != sha256_file(generation / "SHA256SUMS"):
        raise BuildError("CURRENT checksum root mismatch")
    print(f"PASS: v0.10 target installer release validated at {generation}")


def command_clean(cache_root: Path) -> None:
    work = cache_root / "work"
    if work.exists():
        if work.is_symlink() or not work.is_dir():
            raise BuildError("refusing unsafe build work path")
        shutil.rmtree(work)
    print("PASS: disposable v0.10 target-installer build work removed")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "validate", "clean"))
    parser.add_argument("--cache-root")
    return parser.parse_args()


def main() -> int:
    try:
        arguments = parse_arguments()
        cache_root = safe_cache_root(arguments.cache_root)
        if arguments.command == "build":
            command_build(cache_root)
        elif arguments.command == "validate":
            command_validate()
        else:
            command_clean(cache_root)
        return 0
    except (BuildError, OSError, KeyError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 65


if __name__ == "__main__":
    raise SystemExit(main())
