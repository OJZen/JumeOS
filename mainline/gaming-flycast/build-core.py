#!/usr/bin/env python3
"""Build or validate the pinned R46H Flycast libretro bundle."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
from typing import NoReturn


FEATURE_DIR = Path(__file__).resolve().parent
MAINLINE_DIR = FEATURE_DIR.parent
REPO = MAINLINE_DIR.parent
LOCK_PATH = FEATURE_DIR / "source-lock.json"
CACHE_DIR = MAINLINE_DIR / "out/.cache/r46h-flycast"
SOURCE_DIR = CACHE_DIR / "source-v2.6"
DEFAULT_OUTPUT = (
    MAINLINE_DIR
    / "out/r46h-gaming-flycast-v0.1/r46h-flycast-libretro-v2.6.tar.gz"
)
COMMON_PATH = MAINLINE_DIR / "gaming-ppsspp/build-core.py"
SPEC = importlib.util.spec_from_file_location("r46h_component_build_common", COMMON_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load shared component build helpers")
COMMON = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMMON)


def die(message: str) -> NoReturn:
    raise SystemExit(f"ERROR: {message}")


def run(command: list[str], *, capture: bool = False) -> str:
    return COMMON.run(command, capture=capture)


def load_lock() -> dict[str, object]:
    with LOCK_PATH.open("r", encoding="utf-8") as handle:
        lock = json.load(handle)
    if lock.get("schema_version") != 1:
        die("unsupported source lock schema")
    return lock


def build_builder(lock: dict[str, object]) -> None:
    build = lock["build"]
    recipe = REPO / build["builder_recipe"]
    if COMMON.sha256(recipe) != build["builder_recipe_sha256"]:
        die("shared builder recipe changed")
    common_lock = COMMON.load_lock()
    COMMON.build_builder(common_lock)
    require_builder(lock)


def require_builder(lock: dict[str, object]) -> None:
    build = lock["build"]
    actual = run(
        ["docker", "image", "inspect", "--format", "{{.Id}}", build["builder_image"]],
        capture=True,
    ).strip()
    if actual != build["builder_image_id"]:
        die(f"builder image mismatch: {actual}")


def validate_source(source: Path, lock: dict[str, object]) -> None:
    expected = lock["source"]
    if source.is_symlink() or not source.is_dir():
        die(f"unsafe or missing source checkout: {source}")
    checks = {
        "commit": run(["git", "-C", str(source), "rev-parse", "HEAD"], capture=True).strip(),
        "tree": run(
            ["git", "-C", str(source), "rev-parse", "HEAD^{tree}"], capture=True
        ).strip(),
        "tag": run(
            ["git", "-C", str(source), "describe", "--tags", "--exact-match", "HEAD"],
            capture=True,
        ).strip(),
    }
    for name, actual in checks.items():
        if actual != expected[name]:
            die(f"source {name} mismatch: {actual}")
    if run(
        ["git", "-C", str(source), "status", "--porcelain=v1", "--untracked-files=no"],
        capture=True,
    ).strip():
        die("source checkout has tracked changes")

    expected_modules = expected["submodules"]
    seen: set[str] = set()
    for line in run(
        ["git", "-C", str(source), "submodule", "status"], capture=True
    ).splitlines():
        fields = line[1:].split()
        if len(fields) < 2:
            die(f"malformed submodule status: {line}")
        path = fields[1]
        if path in expected_modules:
            if not line.startswith(" ") or fields[0] != expected_modules[path]:
                die(f"required submodule mismatch: {line}")
            if run(
                [
                    "git",
                    "-C",
                    str(source / path),
                    "status",
                    "--porcelain=v1",
                    "--untracked-files=no",
                ],
                capture=True,
            ).strip():
                die(f"required submodule is dirty: {path}")
            seen.add(path)
        elif not line.startswith("-"):
            die(f"unused submodule is initialized: {path}")
    if seen != set(expected_modules):
        die("required submodule set mismatch")


def obtain_source(lock: dict[str, object]) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not SOURCE_DIR.exists():
        source = lock["source"]
        stage = CACHE_DIR / f".source-{os.getpid()}"
        try:
            run(
                [
                    "git",
                    "clone",
                    "--branch",
                    source["tag"],
                    "--depth",
                    "1",
                    source["repository"],
                    str(stage),
                ]
            )
            run(
                [
                    "git",
                    "-C",
                    str(stage),
                    "submodule",
                    "update",
                    "--init",
                    "--depth",
                    "1",
                    *source["submodules"].keys(),
                ]
            )
            validate_source(stage, lock)
            os.replace(stage, SOURCE_DIR)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    validate_source(SOURCE_DIR, lock)
    return SOURCE_DIR


def expected_build_info(lock: dict[str, object]) -> bytes:
    values = {
        "component_id": "r46h-gaming-flycast-v0.1",
        "core_sha256": lock["core"]["sha256"],
        "core_size": str(lock["core"]["size"]),
        "source_commit": lock["source"]["commit"],
        "source_tree": lock["source"]["tree"],
        "upstream_version": lock["source"]["tag"],
    }
    return "".join(f"{key}={value}\n" for key, value in sorted(values.items())).encode()


def validate_artifact(path: Path, lock: dict[str, object]) -> None:
    expected = lock["artifact"]
    if path.is_symlink() or not path.is_file():
        die(f"unsafe or missing artifact: {path}")
    if expected["size"] is not None and path.stat().st_size != expected["size"]:
        die("artifact size mismatch")
    if expected["sha256"] is not None and COMMON.sha256(path) != expected["sha256"]:
        die("artifact SHA-256 mismatch")

    validation = CACHE_DIR / f"validation-{os.getpid()}"
    validation.mkdir(mode=0o700)
    try:
        with tarfile.open(path, "r:gz") as bundle:
            for member in bundle.getmembers():
                relative = PurePosixPath(member.name)
                if relative.is_absolute() or not relative.parts or ".." in relative.parts:
                    die(f"unsafe artifact member: {member.name}")
                target = validation.joinpath(*relative.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    source = bundle.extractfile(member)
                    if source is None:
                        die(f"cannot read artifact member: {member.name}")
                    with target.open("xb") as output:
                        shutil.copyfileobj(source, output)
                else:
                    die(f"unsupported artifact member: {member.name}")
        names = {member.name for member in validation.iterdir()}
        if names != {"BUILD-INFO", lock["license"]["name"], lock["core"]["name"]}:
            die("unexpected artifact member set")
        COMMON.inspect_core(validation / lock["core"]["name"], lock)
        license_path = validation / lock["license"]["name"]
        if (
            license_path.stat().st_size != lock["license"]["size"]
            or COMMON.sha256(license_path) != lock["license"]["sha256"]
        ):
            die("license identity mismatch")
        if (validation / "BUILD-INFO").read_bytes() != expected_build_info(lock):
            die("build information mismatch")
    finally:
        shutil.rmtree(validation, ignore_errors=True)


def build_core(lock: dict[str, object], output: Path) -> None:
    require_builder(lock)
    source = obtain_source(lock)
    scratch = CACHE_DIR / f"source-build-{os.getpid()}"
    build = CACHE_DIR / f"build-{os.getpid()}"
    package = CACHE_DIR / f"package-{os.getpid()}"
    try:
        shutil.copytree(source, scratch, symlinks=True)
        build.mkdir(mode=0o700)
        package.mkdir(mode=0o700)
        environment = (
            "-e", "HOME=/tmp",
            "-e", f"SOURCE_DATE_EPOCH={lock['source']['source_date_epoch']}",
            "-e", "GIT_CONFIG_COUNT=1",
            "-e", "GIT_CONFIG_KEY_0=safe.directory",
            "-e", "GIT_CONFIG_VALUE_0=/src",
        )
        mounts = (f"{scratch.resolve()}:/src", f"{build.resolve()}:/build")
        flags = [
            "-DCMAKE_C_FLAGS_RELEASE=-O2 -DNDEBUG -ffile-prefix-map=/src=.",
            "-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG -ffile-prefix-map=/src=.",
            "-DCMAKE_SHARED_LINKER_FLAGS=-Wl,--build-id=none",
        ]
        run(
            COMMON.docker_prefix(lock, *mounts, environment=environment)
            + ["cmake", "-S", "/src", "-B", "/build", *lock["build"]["cmake_options"], *flags]
        )
        run(
            COMMON.docker_prefix(lock, *mounts, environment=environment)
            + ["cmake", "--build", "/build", "--parallel", "5", "--target", "flycast_libretro"]
        )
        core = package / lock["core"]["name"]
        shutil.copyfile(build / lock["core"]["name"], core)
        os.chmod(core, 0o644)
        COMMON.inspect_core(core, lock)
        shutil.copyfile(source / lock["license"]["name"], package / lock["license"]["name"])
        os.chmod(package / lock["license"]["name"], 0o644)
        (package / "BUILD-INFO").write_bytes(expected_build_info(lock))
        os.chmod(package / "BUILD-INFO", 0o644)
        output.parent.mkdir(parents=True, exist_ok=True)
        COMMON.write_deterministic_tar(package, output, lock["source"]["source_date_epoch"])
        validate_artifact(output, lock)
        print(
            f"R46H_FLYCAST_BUILD result=pass size={output.stat().st_size} "
            f"sha256={COMMON.sha256(output)} output={output.resolve()}"
        )
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
        shutil.rmtree(build, ignore_errors=True)
        shutil.rmtree(package, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("builder", "build", "validate"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    lock = load_lock()
    try:
        if args.action == "builder":
            build_builder(lock)
        elif args.action == "build":
            build_core(lock, args.output)
        else:
            validate_artifact(args.output, lock)
            print(f"R46H_FLYCAST_VALIDATE result=pass output={args.output.resolve()}")
    except (OSError, subprocess.CalledProcessError, tarfile.TarError, ValueError) as error:
        die(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
