#!/usr/bin/env python3
"""Build or validate a pinned R46H FBNeo libretro core."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tarfile
from typing import NoReturn
import urllib.request


FEATURE_DIR = Path(__file__).resolve().parent
MAINLINE_DIR = FEATURE_DIR.parent
LOCK_PATH = FEATURE_DIR / "source-lock.json"
CACHE_DIR = MAINLINE_DIR / "out" / ".cache" / "r46h-ozone-fbneo" / "builder"
DEFAULT_OUTPUT = (
    MAINLINE_DIR
    / "out"
    / "r46h-gaming-ozone-fbneo-v0.1"
    / "fbneo_neogeo_libretro.so"
)


def die(message: str) -> NoReturn:
    raise SystemExit(f"ERROR: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_lock(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        lock = json.load(handle)
    if lock.get("schema_version") != 1:
        die("unsupported source lock schema")
    return lock


def run(command: list[str], *, capture: bool = False) -> str:
    completed = subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    return completed.stdout if capture else ""


def require_builder(lock: dict[str, object]) -> None:
    build = lock["build"]
    image = build["container_image"]
    actual = run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", image],
        capture=True,
    ).strip()
    if actual != build["container_image_id"]:
        die(f"builder image mismatch: {actual}")


def obtain_archive(lock: dict[str, object]) -> Path:
    source = lock["source"]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    archive = CACHE_DIR / source["archive_name"]
    if archive.exists():
        if not archive.is_file() or archive.is_symlink():
            die("unsafe cached source archive")
        if archive.stat().st_size != source["archive_size"] or sha256(archive) != source["archive_sha256"]:
            die("cached source archive mismatch")
        return archive

    stage = archive.with_name(f".{archive.name}.download-{os.getpid()}")
    try:
        with urllib.request.urlopen(source["archive_url"], timeout=120) as response:
            with stage.open("xb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
        if stage.stat().st_size != source["archive_size"] or sha256(stage) != source["archive_sha256"]:
            die("downloaded source archive mismatch")
        os.replace(stage, archive)
    finally:
        stage.unlink(missing_ok=True)
    return archive


def extractable_archive_members(
    members: list[tarfile.TarInfo],
) -> list[tarfile.TarInfo]:
    expanded_size = 0
    extractable: list[tarfile.TarInfo] = []
    for member in members:
        path = PurePosixPath(member.name)
        if path.is_absolute() or not path.parts or ".." in path.parts:
            die(f"unsafe source archive member: {member.name}")
        if member.issym() or member.islnk():
            continue
        if not (member.isdir() or member.isfile()):
            die(f"unsafe source archive member: {member.name}")
        expanded_size += member.size
        if expanded_size > 1_073_741_824:
            die("source archive expands beyond 1 GiB")
        extractable.append(member)
    return extractable


def extract_source(archive: Path) -> Path:
    extract_root = CACHE_DIR / "source"
    stage = CACHE_DIR / f".source-{os.getpid()}"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(mode=0o700)
    try:
        with tarfile.open(archive, "r:gz") as bundle:
            # Python 3.9 has no tarfile extraction filter API. FBNeo's links
            # are Xcode-only, so omit all links from this Linux source tree.
            members = extractable_archive_members(bundle.getmembers())
            bundle.extractall(stage, members=members)
        roots = [path for path in stage.iterdir() if path.is_dir()]
        if len(roots) != 1:
            die("source archive must contain one top-level directory")
        if extract_root.exists():
            shutil.rmtree(extract_root)
        os.replace(roots[0], extract_root)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return extract_root


def docker_prefix(lock: dict[str, object], mount: str) -> list[str]:
    build = lock["build"]
    return [
        "docker",
        "run",
        "--rm",
        "--platform",
        build["platform"],
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-v",
        mount,
        build["container_image"],
    ]


def inspect_artifact(path: Path, lock: dict[str, object]) -> None:
    artifact = lock["artifact"]
    if not path.is_file() or path.is_symlink():
        die(f"unsafe or missing artifact: {path}")
    if path.stat().st_size != artifact["size"]:
        die(f"artifact size mismatch: {path.stat().st_size}")
    actual_sha = sha256(path)
    if actual_sha != artifact["sha256"]:
        die(f"artifact SHA-256 mismatch: {actual_sha}")

    require_builder(lock)
    readelf = run(
        docker_prefix(lock, f"{path.parent.resolve()}:/artifact:ro")
        + [
            "aarch64-linux-gnu-readelf",
            "-hWs",
            f"/artifact/{path.name}",
        ],
        capture=True,
    )
    machine = re.search(r"^\s*Machine:\s*(.+)$", readelf, re.MULTILINE)
    if not machine or machine.group(1).strip() != artifact["machine"]:
        die("artifact ELF machine mismatch")
    for symbol in artifact["required_symbols"]:
        if not re.search(rf"\b{re.escape(symbol)}\b", readelf):
            die(f"artifact is missing symbol: {symbol}")

    dynamic = run(
        docker_prefix(lock, f"{path.parent.resolve()}:/artifact:ro")
        + [
            "aarch64-linux-gnu-readelf",
            "-d",
            f"/artifact/{path.name}",
        ],
        capture=True,
    )
    needed = re.findall(r"\(NEEDED\).*Shared library: \[(.+?)\]", dynamic)
    if needed != artifact["needed_libraries"]:
        die(f"artifact dependency mismatch: {needed}")


def build_core(lock: dict[str, object], output: Path) -> None:
    require_builder(lock)
    archive = obtain_archive(lock)
    source_root = extract_source(archive)
    source = lock["source"]
    build = lock["build"]
    command = [
        "docker",
        "run",
        "--rm",
        "--platform",
        build["platform"],
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-e",
        f"SOURCE_DATE_EPOCH={source['source_date_epoch']}",
        "-v",
        f"{source_root.resolve()}:/src",
        "-w",
        "/src",
        build["container_image"],
        "make",
        "-s",
        "-j5",
        "-C",
        build["make_directory"],
        *build["make_arguments"],
        f"GIT_VERSION={source['git_version']}",
        f"GIT_DATE={source['git_date']}",
    ]
    run(command)

    built = source_root / build["source_output"]
    if not built.is_file() or built.is_symlink():
        die("build did not produce the expected core")
    artifact_dir = CACHE_DIR / "artifact"
    artifact_dir.mkdir(mode=0o700, exist_ok=True)
    staged = artifact_dir / lock["artifact"]["name"]
    staged.unlink(missing_ok=True)
    shutil.copyfile(built, staged)
    run(
        docker_prefix(lock, f"{artifact_dir.resolve()}:/artifact")
        + [build["strip"], "--strip-unneeded", f"/artifact/{staged.name}"]
    )
    inspect_artifact(staged, lock)

    output.parent.mkdir(parents=True, exist_ok=True)
    publish = output.with_name(f".{output.name}.publish-{os.getpid()}")
    try:
        shutil.copyfile(staged, publish)
        os.chmod(publish, 0o644)
        os.replace(publish, output)
    finally:
        publish.unlink(missing_ok=True)
    print(
        f"R46H_FBNEO_BUILD result=pass sha256={sha256(output)} "
        f"size={output.stat().st_size} output={output}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "validate"))
    parser.add_argument("--lock", type=Path, default=LOCK_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    lock_path = args.lock.resolve()
    if lock_path != LOCK_PATH.resolve() and args.output == DEFAULT_OUTPUT:
        die("--output is required with an alternate --lock")
    lock = load_lock(lock_path)
    output = args.output.resolve()
    if args.action == "build":
        build_core(lock, output)
    else:
        inspect_artifact(output, lock)
        print(
            f"R46H_FBNEO_VALIDATE result=pass sha256={sha256(output)} "
            f"size={output.stat().st_size} output={output}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
