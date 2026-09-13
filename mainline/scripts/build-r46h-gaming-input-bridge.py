#!/usr/bin/env python3
"""Build the rollback-safe R46H combined gaming input bridge candidate."""

from __future__ import annotations

import argparse
import gzip
import hashlib
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
from typing import Any


REPO = Path(__file__).resolve().parents[2]
CACHE_ROOT = REPO / "mainline/out/.cache/r46h-gaming-input-bridge-build"
RELEASE_ROOT = REPO / "mainline/out/r46h-gaming-input-bridge"
BASE_IMAGE = (
    "arkos4clone/r46h-debian13-p2-mvp:v0.1@"
    "sha256:bd09bf6db6f1fb8f882621e98d70f01f976fd8dfba1bc897766afebd64cf51b9"
)
BASE_IMAGE_ID = "sha256:bd09bf6db6f1fb8f882621e98d70f01f976fd8dfba1bc897766afebd64cf51b9"
PAYLOAD_ID = "r46h-gaming-input-bridge-v0.5"
ARCHIVE_NAME = f"{PAYLOAD_ID}.tar.gz"
TEST_RELEASE = "6.12.99-r46h-mainline-v0.14-gaming-input-bridge"
SOURCE_PATHS = (
    "mainline/gaming-input-bridge/Dockerfile",
    "mainline/gaming-input-bridge/OPERATIONS.md",
    "mainline/gaming-input-bridge/install.sh",
    "mainline/gaming-input-bridge/remove.sh",
    "mainline/gaming-input-bridge/r46h-input-bridge-wait",
    "mainline/gaming-input-bridge/r46h-input-bridge.c",
    "mainline/gaming-input-bridge/r46h-input-bridge.service",
    "mainline/gaming-input-bridge/retroarch.cfg",
    "mainline/gaming-input-bridge/trial.sh",
    "mainline/gaming-history-fix/retroarch.cfg",
    "mainline/gaming-mvp/r46h-game-ui",
    "mainline/scripts/build-r46h-gaming-input-bridge.py",
    "mainline/tests/test-r46h-gaming-input-bridge.py",
)
PAYLOAD_FILES = {
    "files/OPERATIONS.md",
    "files/r46h-game-ui-input-candidate",
    "files/r46h-input-bridge",
    "files/r46h-input-bridge-remove",
    "files/r46h-input-bridge-trial",
    "files/r46h-input-bridge-wait",
    "files/r46h-input-bridge.service",
    "files/retroarch.cfg",
}
PAYLOAD_TOP_LEVEL = {
    "PAYLOAD-INFO.json",
    "PAYLOAD.COMPLETE",
    "SHA256SUMS",
    "STATE-SHA256SUMS",
    "files",
    "install.sh",
}
GENERATION_FILES = {
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
        raise BuildError("gaming input bridge source scope must be committed and clean")
    commit = git_bytes(["rev-parse", "--verify", "HEAD^{commit}"]).decode().strip()
    tree = git_bytes(["rev-parse", "--verify", "HEAD^{tree}"]).decode().strip()
    captured: dict[str, bytes] = {}
    entries: list[dict[str, object]] = []
    for relative in SOURCE_PATHS:
        live = REPO / relative
        metadata = live.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise BuildError(f"unsafe source file: {relative}")
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
    return commit, tree, captured, manifest


def write_new(path: Path, payload: bytes, mode: int = 0o600) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def write_source_snapshot(root: Path, captured: dict[str, bytes]) -> Path:
    source = root / "source"
    source.mkdir(mode=0o700)
    for relative, payload in captured.items():
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        write_new(destination, payload)
    return source


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


def run(command: list[str], *, cwd: Path | None = None) -> None:
    result = subprocess.run(command, cwd=cwd, check=False)
    if result.returncode != 0:
        raise BuildError(f"command exited {result.returncode}: {' '.join(command)}")


def require_base_image(docker: str) -> None:
    result = subprocess.run(
        [
            docker,
            "--context",
            "desktop-linux",
            "image",
            "inspect",
            BASE_IMAGE,
            "--format",
            "{{.Id}} {{.Os}}/{{.Architecture}}",
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    expected = f"{BASE_IMAGE_ID} linux/arm64"
    if result.returncode != 0 or result.stdout.strip() != expected:
        raise BuildError(f"base image mismatch: expected {expected!r}")


def tree_manifest(root: Path, excluded: set[str]) -> bytes:
    lines: list[str] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise BuildError(f"unsafe manifest member: {path}")
        relative = path.relative_to(root).as_posix()
        if relative not in excluded:
            lines.append(f"{sha256_file(path)}  {relative}\n")
    return "".join(lines).encode()


def render_candidate_runner(base: bytes) -> bytes:
    old_release = b"readonly EXPECTED_RELEASE=6.12.99-r46h-mainline-v0.10-adc-full-range"
    new_release = f"readonly EXPECTED_RELEASE={TEST_RELEASE}".encode()
    old_config = b"readonly CONFIG=/etc/r46h/retroarch.cfg"
    new_config = b"readonly CONFIG=/etc/r46h/retroarch-input-candidate.cfg"
    old_result = b'"$([[ $status == 0 ]] && printf pass || printf fail)"'
    new_result = b'"$([[ $status == 0 || $status == 143 ]] && printf pass || printf fail)"'
    if (
        base.count(old_release) != 1
        or base.count(old_config) != 1
        or base.count(old_result) != 1
    ):
        raise BuildError("accepted gaming runner template identity mismatch")
    rendered = (
        base.replace(old_release, new_release)
        .replace(old_config, new_config)
        .replace(old_result, new_result)
    )
    if (
        rendered.count(new_release) != 1
        or rendered.count(new_config) != 1
        or rendered.count(new_result) != 1
    ):
        raise BuildError("candidate gaming runner rendering failed")
    return rendered


def create_payload(
    payload: Path, captured: dict[str, bytes], binary: bytes, commit: str
) -> None:
    files = payload / "files"
    files.mkdir(parents=True, mode=0o700)
    mappings = {
        "OPERATIONS.md": "mainline/gaming-input-bridge/OPERATIONS.md",
        "r46h-input-bridge-remove": "mainline/gaming-input-bridge/remove.sh",
        "r46h-input-bridge-trial": "mainline/gaming-input-bridge/trial.sh",
        "r46h-input-bridge-wait": "mainline/gaming-input-bridge/r46h-input-bridge-wait",
        "r46h-input-bridge.service": "mainline/gaming-input-bridge/r46h-input-bridge.service",
        "retroarch.cfg": "mainline/gaming-input-bridge/retroarch.cfg",
    }
    for name, relative in mappings.items():
        write_new(files / name, captured[relative])
    write_new(files / "r46h-input-bridge", binary)
    write_new(
        files / "r46h-game-ui-input-candidate",
        render_candidate_runner(captured["mainline/gaming-mvp/r46h-game-ui"]),
    )
    write_new(payload / "install.sh", captured["mainline/gaming-input-bridge/install.sh"])
    state_sums = tree_manifest(files, set())
    write_new(payload / "STATE-SHA256SUMS", state_sums)
    write_new(
        payload / "PAYLOAD-INFO.json",
        canonical_json(
            {
                "base_image": BASE_IMAGE,
                "base_image_id": BASE_IMAGE_ID,
                "format_version": 1,
                "install_from_release": "6.12.99-r46h-mainline-v0.10-adc-full-range",
                "payload_id": PAYLOAD_ID,
                "source_git_commit": commit,
                "test_release": TEST_RELEASE,
            }
        ),
    )
    sums = tree_manifest(payload, {"SHA256SUMS", "PAYLOAD.COMPLETE"})
    write_new(payload / "SHA256SUMS", sums)
    write_new(payload / "PAYLOAD.COMPLETE", f"sha256sums_sha256={sha256_bytes(sums)}\n".encode())
    for path in (payload / "install.sh", *files.iterdir()):
        if path.name in {
            "r46h-input-bridge",
            "r46h-game-ui-input-candidate",
            "r46h-input-bridge-remove",
            "r46h-input-bridge-trial",
            "r46h-input-bridge-wait",
        } or path.name == "install.sh":
            path.chmod(0o700)
        else:
            path.chmod(0o600)


def validate_payload(payload: Path) -> None:
    require_directory(payload, "payload")
    if {entry.name for entry in payload.iterdir()} != PAYLOAD_TOP_LEVEL:
        raise BuildError("payload top-level member set mismatch")
    actual_files = {
        path.relative_to(payload).as_posix()
        for path in (payload / "files").iterdir()
    }
    if actual_files != PAYLOAD_FILES:
        raise BuildError("payload file member set mismatch")
    for relative in PAYLOAD_FILES | {
        "PAYLOAD-INFO.json",
        "PAYLOAD.COMPLETE",
        "SHA256SUMS",
        "STATE-SHA256SUMS",
        "install.sh",
    }:
        require_regular(payload / relative, relative)
    sums = tree_manifest(payload, {"SHA256SUMS", "PAYLOAD.COMPLETE"})
    if (payload / "SHA256SUMS").read_bytes() != sums:
        raise BuildError("payload checksum manifest mismatch")
    if (payload / "PAYLOAD.COMPLETE").read_bytes() != (
        f"sha256sums_sha256={sha256_bytes(sums)}\n".encode()
    ):
        raise BuildError("payload completion marker mismatch")
    if (payload / "STATE-SHA256SUMS").read_bytes() != tree_manifest(
        payload / "files", set()
    ):
        raise BuildError("state checksum manifest mismatch")
    info = exact_json(payload / "PAYLOAD-INFO.json")
    if info.get("payload_id") != PAYLOAD_ID or info.get("test_release") != TEST_RELEASE:
        raise BuildError("payload metadata mismatch")
    if require_regular(payload / "files/r46h-input-bridge", "bridge").st_size < 10_000:
        raise BuildError("bridge binary is unexpectedly small")


def run_container_validation(docker: str, payload: Path, work: Path) -> None:
    command = r"""set -Eeuo pipefail
install -D -m 0755 /payload/files/r46h-input-bridge /usr/local/libexec/r46h-input-bridge
install -D -m 0755 /payload/files/r46h-input-bridge-wait /usr/local/libexec/r46h-input-bridge-wait
install -D -m 0644 /payload/files/r46h-input-bridge.service /etc/systemd/system/r46h-input-bridge.service
file /usr/local/libexec/r46h-input-bridge > /output/BRIDGE-FILE.txt
grep -Eq 'ELF 64-bit.*ARM aarch64' /output/BRIDGE-FILE.txt
test "$(/usr/local/libexec/r46h-input-bridge --version)" = r46h-gaming-input-bridge-v0.5
bash -n /payload/install.sh
bash -n /payload/files/r46h-input-bridge-remove
bash -n /payload/files/r46h-input-bridge-trial
bash -n /payload/files/r46h-input-bridge-wait
bash -n /payload/files/r46h-game-ui-input-candidate
systemd-analyze verify /etc/systemd/system/r46h-input-bridge.service
"""
    run(
        [
            docker,
            "--context",
            "desktop-linux",
            "run",
            "--rm",
            "--platform",
            "linux/arm64",
            "--network",
            "none",
            "--volume",
            f"{payload}:/payload:ro",
            "--volume",
            f"{work}:/output",
            "--entrypoint",
            "/bin/bash",
            BASE_IMAGE,
            "-lc",
            command,
        ]
    )


def deterministic_archive(payload: Path, destination: Path) -> None:
    with destination.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                paths = [payload, *sorted(payload.rglob("*"), key=lambda item: item.relative_to(payload).as_posix())]
                for path in paths:
                    relative = Path(PAYLOAD_ID) / path.relative_to(payload)
                    info = archive.gettarinfo(str(path), arcname=relative.as_posix())
                    info.uid = 0
                    info.gid = 0
                    info.uname = "root"
                    info.gname = "root"
                    info.mtime = 0
                    if info.isdir():
                        archive.addfile(info)
                    else:
                        with path.open("rb") as handle:
                            archive.addfile(info, handle)


def validate_archive(archive_path: Path) -> None:
    with tarfile.open(archive_path, "r:gz") as archive:
        names = archive.getnames()
        expected = [PAYLOAD_ID]
        expected.extend(
            f"{PAYLOAD_ID}/{path}"
            for path in sorted(PAYLOAD_TOP_LEVEL | PAYLOAD_FILES)
        )
        if sorted(names) != sorted(expected):
            raise BuildError("archive member set mismatch")
        for member in archive.getmembers():
            if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                raise BuildError(f"unsafe archive member: {member.name}")
            if member.uid != 0 or member.gid != 0 or member.mtime != 0:
                raise BuildError(f"non-deterministic archive metadata: {member.name}")


def run_extracted_archive_validation(docker: str, archive_path: Path) -> None:
    command = f"""set -Eeuo pipefail
tar -xzf /archive/{ARCHIVE_NAME} -C /run
test "$(stat -c '%u:%g:%a' /run/{PAYLOAD_ID})" = 0:0:700
test -x /run/{PAYLOAD_ID}/install.sh
/run/{PAYLOAD_ID}/install.sh --check-payload
"""
    run(
        [
            docker,
            "--context",
            "desktop-linux",
            "run",
            "--rm",
            "--platform",
            "linux/arm64",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/run:rw,exec,nosuid,nodev,mode=755",
            "--volume",
            f"{archive_path.parent}:/archive:ro",
            "--entrypoint",
            "/bin/bash",
            BASE_IMAGE,
            "-lc",
            command,
        ]
    )


def publish_generation(stage: Path, generation_name: str) -> Path:
    RELEASE_ROOT.mkdir(parents=True, exist_ok=True)
    builds = RELEASE_ROOT / "builds"
    builds.mkdir(exist_ok=True)
    destination = builds / generation_name
    if destination.exists() or destination.is_symlink():
        raise BuildError(f"generation already exists: {generation_name}")
    os.rename(stage, destination)
    pointer = RELEASE_ROOT / f".CURRENT.{os.getpid()}"
    write_new(pointer, f"{generation_name}\n".encode())
    os.replace(pointer, RELEASE_ROOT / "CURRENT")
    return destination


def validate_generation() -> Path:
    current_path = RELEASE_ROOT / "CURRENT"
    require_regular(current_path, "CURRENT")
    current = current_path.read_text(encoding="utf-8").strip()
    if GENERATION_RE.fullmatch(current) is None:
        raise BuildError("invalid CURRENT generation")
    generation = RELEASE_ROOT / "builds" / current
    require_directory(generation, "generation")
    if {entry.name for entry in generation.iterdir()} != GENERATION_FILES:
        raise BuildError("generation member set mismatch")
    for name in GENERATION_FILES:
        require_regular(generation / name, name)
    sums = tree_manifest(generation, {"SHA256SUMS", "BUILD-COMPLETE"})
    if (generation / "SHA256SUMS").read_bytes() != sums:
        raise BuildError("generation checksum manifest mismatch")
    if (generation / "BUILD-COMPLETE").read_bytes() != (
        f"sha256sums_sha256={sha256_bytes(sums)}\n".encode()
    ):
        raise BuildError("generation completion marker mismatch")
    receipt = exact_json(generation / "BUILD-RECEIPT.json")
    archive = generation / ARCHIVE_NAME
    if receipt.get("archive_sha256") != sha256_file(archive):
        raise BuildError("archive digest does not match receipt")
    validate_archive(archive)
    return generation


def command_build() -> Path:
    commit, tree, captured, source_manifest = capture_clean_source()
    docker = shutil.which("docker")
    if docker is None:
        raise BuildError("docker is unavailable")
    require_base_image(docker)
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="work.", dir=CACHE_ROOT))
    image_tag = f"arkos4clone/r46h-gaming-input-bridge-build:{commit[:12]}-{os.getpid()}"
    container = ""
    published = False
    stage = work / "generation"
    try:
        source = write_source_snapshot(work, captured)
        run(
            [
                docker,
                "--context",
                "desktop-linux",
                "build",
                "--platform",
                "linux/arm64",
                "--file",
                str(source / "mainline/gaming-input-bridge/Dockerfile"),
                "--tag",
                image_tag,
                str(source / "mainline"),
            ]
        )
        created = subprocess.run(
            [docker, "--context", "desktop-linux", "create", "--platform", "linux/arm64", image_tag],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if created.returncode != 0 or re.fullmatch(r"[0-9a-f]{64}\n?", created.stdout) is None:
            raise BuildError("cannot create bridge export container")
        container = created.stdout.strip()
        binary_path = work / "r46h-input-bridge"
        run([docker, "--context", "desktop-linux", "cp", f"{container}:/r46h-input-bridge", str(binary_path)])
        run([docker, "--context", "desktop-linux", "rm", container])
        container = ""
        payload = work / "payload"
        payload.mkdir(mode=0o700)
        create_payload(payload, captured, binary_path.read_bytes(), commit)
        validate_payload(payload)
        run_container_validation(docker, payload, work)
        stage.mkdir(mode=0o700)
        archive = stage / ARCHIVE_NAME
        deterministic_archive(payload, archive)
        validate_archive(archive)
        run_extracted_archive_validation(docker, archive)
        write_new(stage / "SOURCE-MANIFEST.json", source_manifest)
        archive_sha = sha256_file(archive)
        write_new(
            stage / "BUILD-RECEIPT.json",
            canonical_json(
                {
                    "archive_sha256": archive_sha,
                    "archive_size": archive.stat().st_size,
                    "base_image_id": BASE_IMAGE_ID,
                    "bridge_sha256": sha256_file(payload / "files/r46h-input-bridge"),
                    "bridge_size": (payload / "files/r46h-input-bridge").stat().st_size,
                    "format_version": 1,
                    "payload_id": PAYLOAD_ID,
                    "source_git_commit": commit,
                    "source_git_tree": tree,
                    "source_manifest_sha256": sha256_bytes(source_manifest),
                    "test_release": TEST_RELEASE,
                }
            ),
        )
        generation_sums = tree_manifest(stage, {"SHA256SUMS", "BUILD-COMPLETE"})
        write_new(stage / "SHA256SUMS", generation_sums)
        write_new(stage / "BUILD-COMPLETE", f"sha256sums_sha256={sha256_bytes(generation_sums)}\n".encode())
        generation_name = f"build-{commit[:12]}-{archive_sha[:12]}"
        destination = publish_generation(stage, generation_name)
        published = True
        validate_generation()
        print(f"PASS: gaming input bridge published at {destination}")
        print(f"ARCHIVE={destination / ARCHIVE_NAME}")
        print(f"ARCHIVE_SHA256={archive_sha}")
        return destination
    finally:
        if container:
            subprocess.run(
                [docker, "--context", "desktop-linux", "rm", "-f", container],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        subprocess.run(
            [docker, "--context", "desktop-linux", "image", "rm", "-f", image_tag],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
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
            print(f"PASS: gaming input bridge generation validated at {generation}")
    except (BuildError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
