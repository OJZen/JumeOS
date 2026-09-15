#!/usr/bin/env python3
"""Build or validate the pinned, p2-local R46H ES-DE runtime bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from typing import NoReturn
import urllib.request


FEATURE_DIR = Path(__file__).resolve().parent
MAINLINE_DIR = FEATURE_DIR.parent
LOCK_PATH = FEATURE_DIR / "source-lock.json"
CACHE_DIR = MAINLINE_DIR / "out/.cache/r46h-es-de/builder"
DEFAULT_OUTPUT_DIR = MAINLINE_DIR / "out/r46h-gaming-es-de-v0.1"
MEDIA_MANIFEST = MAINLINE_DIR / "out/.cache/r46h-es-de/legacy-media-links.tsv"
PAYLOAD_FILES = (
    (FEATURE_DIR / "README.md", "README.md", 0o644),
    (FEATURE_DIR / "es-de-retroarch.cfg", "es-de-retroarch.cfg", 0o644),
    (FEATURE_DIR / "es_settings.xml", "es_settings.xml", 0o644),
    (FEATURE_DIR / "es_systems.xml", "es_systems.xml", 0o644),
    (FEATURE_DIR / "install.sh", "install.sh", 0o755),
    (MEDIA_MANIFEST, "legacy-media-links.tsv", 0o644),
    (FEATURE_DIR / "r46h-es-de-ui", "r46h-es-de-ui", 0o755),
    (FEATURE_DIR / "r46h-gaming-frontend.service", "r46h-gaming-frontend.service", 0o644),
    (FEATURE_DIR / "r46h-theme.xml", "r46h-theme.xml", 0o644),
    (FEATURE_DIR / "rollback.sh", "rollback.sh", 0o755),
    (FEATURE_DIR / "system-links.tsv", "system-links.tsv", 0o644),
)


def die(message: str) -> NoReturn:
    raise SystemExit(f"ERROR: {message}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], *, capture: bool = False) -> str:
    completed = subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    return completed.stdout if capture else ""


def load_lock() -> dict[str, object]:
    with LOCK_PATH.open("r", encoding="utf-8") as handle:
        lock = json.load(handle)
    if lock.get("schema_version") != 1:
        die("unsupported source lock schema")
    return lock


def require_base(lock: dict[str, object]) -> None:
    build = lock["build"]
    actual = run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", build["base_image"]],
        capture=True,
    ).strip()
    if actual != build["base_image_id"]:
        die(f"base image mismatch: {actual}")


def obtain_archive(lock: dict[str, object]) -> Path:
    source = lock["source"]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    archive = CACHE_DIR / source["archive_name"]
    if archive.exists():
        if archive.is_symlink() or not archive.is_file():
            die("unsafe cached source archive")
        if archive.stat().st_size != source["archive_size"] or sha256(archive) != source["archive_sha256"]:
            die("cached source archive mismatch")
        return archive

    stage = archive.with_name(f".{archive.name}.download-{os.getpid()}")
    try:
        with urllib.request.urlopen(source["archive_url"], timeout=180) as response:
            with stage.open("xb") as handle:
                shutil.copyfileobj(response, handle, length=1024 * 1024)
        if stage.stat().st_size != source["archive_size"] or sha256(stage) != source["archive_sha256"]:
            die("downloaded source archive mismatch")
        os.replace(stage, archive)
    finally:
        stage.unlink(missing_ok=True)
    return archive


def validate_members(artifact: Path) -> None:
    roots: set[str] = set()
    with tarfile.open(artifact, "r:gz") as bundle:
        for member in bundle.getmembers():
            path = Path(member.name)
            if path.is_absolute() or ".." in path.parts:
                die(f"unsafe artifact member: {member.name}")
            roots.add(path.parts[0] if path.parts else "")
            if member.isdev() or member.issym() or member.islnk():
                die(f"unsupported artifact member type: {member.name}")
    if roots != {"opt"}:
        die(f"unexpected artifact roots: {sorted(roots)}")


def require_aarch64_elf(path: Path) -> None:
    with path.open("rb") as handle:
        header = handle.read(20)
    if (
        len(header) != 20
        or header[:4] != b"\x7fELF"
        or header[4] != 2
        or header[5] != 1
        or int.from_bytes(header[18:20], "little") != 183
    ):
        die(f"not an AArch64 ELF64 executable: {path}")


def inspect_artifact(artifact: Path, lock: dict[str, object]) -> None:
    expected = lock["artifact"]
    if artifact.is_symlink() or not artifact.is_file():
        die(f"unsafe or missing artifact: {artifact}")
    actual_size = artifact.stat().st_size
    actual_sha = sha256(artifact)
    if expected["size"] is not None and actual_size != expected["size"]:
        die(f"artifact size mismatch: {actual_size}")
    if expected["sha256"] is not None and actual_sha != expected["sha256"]:
        die(f"artifact SHA-256 mismatch: {actual_sha}")
    validate_members(artifact)

    validation = CACHE_DIR / "validation"
    if validation.exists():
        shutil.rmtree(validation)
    validation.mkdir(mode=0o700)
    try:
        # validate_members() rejects links, devices, absolute paths and traversal
        # before extraction. Python 3.9 has no tarfile extraction filter API.
        with tarfile.open(artifact, "r:gz") as bundle:
            bundle.extractall(validation)
        prefix = validation / "opt/r46h/es-de"
        for required in (
            prefix / "bin/es-de",
            prefix / "bin/es-pdf-convert",
            prefix / "share/es-de/resources",
            prefix / "share/es-de/themes/linear-es-de",
            prefix / "share/r46h/RUNTIME-LIBRARIES.tsv",
            prefix / "share/r46h/BUILD-INFO",
            prefix / "share/r46h/VERSION",
        ):
            if not required.exists() or required.is_symlink():
                die(f"runtime bundle member is missing or unsafe: {required.relative_to(validation)}")
        require_aarch64_elf(prefix / "bin/es-de")
        output = (prefix / "share/r46h/VERSION").read_text(encoding="utf-8").strip()
        if output != expected["version_output"]:
            die(f"unexpected ES-DE version output: {output}")
    finally:
        shutil.rmtree(validation, ignore_errors=True)


def publish_file(source: Path, destination: Path, mode: int) -> None:
    if source.is_symlink() or not source.is_file():
        die(f"unsafe or missing payload source: {source}")
    stage = destination.with_name(f".{destination.name}.publish-{os.getpid()}")
    try:
        shutil.copyfile(source, stage)
        os.chmod(stage, mode)
        os.replace(stage, destination)
    finally:
        stage.unlink(missing_ok=True)


def assemble_payload(lock: dict[str, object], output_dir: Path) -> Path:
    artifact = output_dir / lock["artifact"]["name"]
    inspect_artifact(artifact, lock)
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = {artifact.name, "SHA256SUMS"}
    expected.update(name for _, name, _ in PAYLOAD_FILES)
    extras = sorted(path.name for path in output_dir.iterdir() if path.name not in expected)
    if extras:
        die(f"unexpected files in payload output: {extras}")
    for source, name, mode in PAYLOAD_FILES:
        publish_file(source, output_dir / name, mode)

    manifest = output_dir / "SHA256SUMS"
    stage = manifest.with_name(f".{manifest.name}.publish-{os.getpid()}")
    try:
        with stage.open("x", encoding="utf-8", newline="\n") as handle:
            for name in sorted(expected - {manifest.name}):
                path = output_dir / name
                handle.write(f"{sha256(path)}  {name}\n")
        os.chmod(stage, 0o644)
        os.replace(stage, manifest)
    finally:
        stage.unlink(missing_ok=True)
    return artifact


def build_runtime(lock: dict[str, object], output_dir: Path) -> Path:
    require_base(lock)
    archive = obtain_archive(lock)
    context = CACHE_DIR / f"context-{os.getpid()}"
    export = CACHE_DIR / f"export-{os.getpid()}"
    for path in (context, export):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(mode=0o700)
    try:
        shutil.copyfile(FEATURE_DIR / "Dockerfile", context / "Dockerfile")
        shutil.copyfile(FEATURE_DIR / "collect-runtime.sh", context / "collect-runtime.sh")
        patch = FEATURE_DIR / lock["build"]["patch"]["name"]
        if sha256(patch) != lock["build"]["patch"]["sha256"]:
            die("idle frame pacing patch mismatch")
        shutil.copyfile(patch, context / patch.name)
        shutil.copyfile(archive, context / archive.name)
        run(
            [
                "docker",
                "build",
                "--platform",
                lock["build"]["platform"],
                "--target",
                "export",
                "--build-arg",
                f"BASE_IMAGE={lock['build']['base_image']}",
                "--build-arg",
                f"SOURCE_DATE_EPOCH={lock['source']['source_date_epoch']}",
                "--output",
                f"type=local,dest={export}",
                str(context),
            ]
        )
        built = export / lock["artifact"]["name"]
        inspect_artifact(built, lock)
        output_dir.mkdir(parents=True, exist_ok=True)
        output = output_dir / built.name
        stage = output.with_name(f".{output.name}.publish-{os.getpid()}")
        shutil.copyfile(built, stage)
        os.chmod(stage, 0o644)
        os.replace(stage, output)
        return output
    finally:
        shutil.rmtree(context, ignore_errors=True)
        shutil.rmtree(export, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "payload", "validate"))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--artifact", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    lock = load_lock()
    if args.action == "build":
        artifact = build_runtime(lock, args.output_dir.resolve())
    elif args.action == "payload":
        artifact = assemble_payload(lock, args.output_dir.resolve())
    else:
        artifact = (args.artifact or args.output_dir / lock["artifact"]["name"]).resolve()
        inspect_artifact(artifact, lock)
    print(
        f"R46H_ES_DE_RUNTIME result=pass action={args.action} "
        f"sha256={sha256(artifact)} size={artifact.stat().st_size} artifact={artifact}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
