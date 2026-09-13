#!/usr/bin/env python3
"""Build or validate the pinned R46H PPSSPP libretro bundle."""

from __future__ import annotations

import argparse
import gzip
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


FEATURE_DIR = Path(__file__).resolve().parent
MAINLINE_DIR = FEATURE_DIR.parent
LOCK_PATH = FEATURE_DIR / "source-lock.json"
CACHE_DIR = MAINLINE_DIR / "out/.cache/r46h-ppsspp/builder"
SOURCE_DIR = CACHE_DIR / "source-v1.20.4"
DEFAULT_OUTPUT = (
    MAINLINE_DIR
    / "out/r46h-gaming-ppsspp-v0.1/r46h-ppsspp-libretro-v1.20.4.tar.gz"
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


def build_builder(lock: dict[str, object]) -> None:
    require_base(lock)
    build = lock["build"]
    run(
        [
            "docker",
            "build",
            "--platform",
            build["platform"],
            "--build-arg",
            f"BASE_IMAGE={build['base_image']}",
            "--tag",
            build["builder_image"],
            str(FEATURE_DIR),
        ]
    )


def require_builder(lock: dict[str, object]) -> None:
    image = lock["build"]["builder_image"]
    try:
        run(["docker", "image", "inspect", image], capture=True)
    except subprocess.CalledProcessError as error:
        die(f"builder image is missing; run the builder command: {error.output}")


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
        [
            "git",
            "-C",
            str(source),
            "status",
            "--porcelain=v1",
            "--untracked-files=no",
        ],
        capture=True,
    ).strip():
        die("source checkout has tracked changes")

    actual_submodules: dict[str, str] = {}
    for line in run(
        ["git", "-C", str(source), "submodule", "status", "--recursive"],
        capture=True,
    ).splitlines():
        if not line.startswith(" "):
            die(f"submodule is not at its recorded commit: {line}")
        fields = line[1:].split()
        if len(fields) < 2 or fields[1] in actual_submodules:
            die(f"malformed submodule status: {line}")
        actual_submodules[fields[1]] = fields[0]
    if actual_submodules != expected["submodules"]:
        die("recursive submodule set or identity mismatch")


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
                    "--recurse-submodules",
                    "--shallow-submodules",
                    source["repository"],
                    str(stage),
                ]
            )
            validate_source(stage, lock)
            os.replace(stage, SOURCE_DIR)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    validate_source(SOURCE_DIR, lock)
    return SOURCE_DIR


def docker_prefix(
    lock: dict[str, object], *mounts: str, environment: tuple[str, ...] = ()
) -> list[str]:
    command = [
        "docker",
        "run",
        "--rm",
        "--platform",
        lock["build"]["platform"],
        "--user",
        f"{os.getuid()}:{os.getgid()}",
    ]
    for mount in mounts:
        command.extend(("-v", mount))
    command.extend(environment)
    command.append(lock["build"]["builder_image"])
    return command


def inspect_core(path: Path, lock: dict[str, object]) -> None:
    expected = lock["core"]
    if path.is_symlink() or not path.is_file():
        die(f"unsafe or missing core: {path}")
    if path.stat().st_size != expected["size"] or sha256(path) != expected["sha256"]:
        die("core size or SHA-256 mismatch")
    require_builder(lock)
    mount = f"{path.parent.resolve()}:/artifact:ro"
    readelf = run(
        docker_prefix(lock, mount)
        + ["readelf", "-hWs", f"/artifact/{path.name}"],
        capture=True,
    )
    machine = re.search(r"^\s*Machine:\s*(.+)$", readelf, re.MULTILINE)
    if not machine or machine.group(1).strip() != expected["machine"]:
        die("core ELF machine mismatch")
    for symbol in expected["required_symbols"]:
        if not re.search(rf"\b{re.escape(symbol)}\b", readelf):
            die(f"core is missing symbol: {symbol}")
    dynamic = run(
        docker_prefix(lock, mount)
        + ["readelf", "-d", f"/artifact/{path.name}"],
        capture=True,
    )
    needed = re.findall(r"\(NEEDED\).*Shared library: \[(.+?)\]", dynamic)
    if needed != expected["needed_libraries"]:
        die(f"core dependency mismatch: {needed}")


def git_files(repository: Path, *pathspec: str) -> list[str]:
    output = subprocess.run(
        ["git", "-C", str(repository), "ls-files", "-s", "-z", "--", *pathspec],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    paths = []
    for record in output.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode = metadata.split(b" ", 1)[0]
        path = raw_path.decode("utf-8")
        if mode == b"160000" and path == "assets/debugger":
            continue
        if mode not in (b"100644", b"100755"):
            die(f"unsupported tracked asset: {mode.decode()} {path}")
        paths.append(path)
    return paths


def copy_assets(source: Path, destination: Path) -> bytes:
    files = [(source / path, path.removeprefix("assets/")) for path in git_files(source, "assets")]
    debugger = source / "assets/debugger"
    files.extend((debugger / path, f"debugger/{path}") for path in git_files(debugger))
    files.sort(key=lambda item: item[1])
    lines = []
    for source_path, relative in files:
        posix = PurePosixPath(relative)
        if posix.is_absolute() or ".." in posix.parts:
            die(f"unsafe asset path: {relative}")
        if source_path.is_symlink() or not source_path.is_file():
            die(f"unsafe or missing asset: {source_path}")
        target = destination.joinpath(*posix.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target)
        os.chmod(target, 0o644)
        lines.append(f"{sha256(target)}  {relative}\n")
    return "".join(lines).encode()


def write_deterministic_tar(source: Path, destination: Path, mtime: int) -> None:
    stage = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
    try:
        with stage.open("xb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as bundle:
                    for path in sorted(source.rglob("*"), key=lambda item: item.relative_to(source).as_posix()):
                        relative = path.relative_to(source).as_posix()
                        info = tarfile.TarInfo(relative)
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        info.mtime = mtime
                        if path.is_dir() and not path.is_symlink():
                            info.type = tarfile.DIRTYPE
                            info.mode = 0o755
                            bundle.addfile(info)
                        elif path.is_file() and not path.is_symlink():
                            info.mode = 0o644
                            info.size = path.stat().st_size
                            with path.open("rb") as handle:
                                bundle.addfile(info, handle)
                        else:
                            die(f"unsupported bundle member: {path}")
        os.chmod(stage, 0o644)
        os.replace(stage, destination)
    finally:
        stage.unlink(missing_ok=True)


def validate_artifact(path: Path, lock: dict[str, object]) -> None:
    expected = lock["artifact"]
    if path.is_symlink() or not path.is_file():
        die(f"unsafe or missing artifact: {path}")
    if expected["size"] is not None and path.stat().st_size != expected["size"]:
        die(f"artifact size mismatch: {path.stat().st_size}")
    if expected["sha256"] is not None and sha256(path) != expected["sha256"]:
        die(f"artifact SHA-256 mismatch: {sha256(path)}")

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
        if {path.name for path in validation.iterdir()} != {
            "ASSETS.sha256",
            "BUILD-INFO",
            "LICENSE.TXT",
            "PPSSPP",
            lock["core"]["name"],
        }:
            die("unexpected artifact top-level member set")
        core = validation / lock["core"]["name"]
        inspect_core(core, lock)
        manifest = (validation / "ASSETS.sha256").read_bytes()
        if lock["assets"]["manifest_sha256"] is not None and hashlib.sha256(manifest).hexdigest() != lock["assets"]["manifest_sha256"]:
            die("asset manifest SHA-256 mismatch")
        lines = manifest.decode("utf-8").splitlines()
        if len(lines) != lock["assets"]["file_count"]:
            die("asset count mismatch")
        for line in lines:
            digest, relative = line.split("  ", 1)
            asset = validation / "PPSSPP" / relative
            if asset.is_symlink() or not asset.is_file() or sha256(asset) != digest:
                die(f"asset identity mismatch: {relative}")
    finally:
        shutil.rmtree(validation, ignore_errors=True)


def build_core(lock: dict[str, object], output: Path) -> None:
    build_builder(lock)
    source = obtain_source(lock)
    build_dir = CACHE_DIR / f"build-{os.getpid()}"
    package_dir = CACHE_DIR / f"package-{os.getpid()}"
    for path in (build_dir, package_dir):
        path.mkdir(mode=0o700)
    try:
        environment = [
            "-e", "HOME=/tmp",
            "-e", f"SOURCE_DATE_EPOCH={lock['source']['source_date_epoch']}",
            "-e", "GIT_CONFIG_COUNT=1",
            "-e", "GIT_CONFIG_KEY_0=safe.directory",
            "-e", "GIT_CONFIG_VALUE_0=/src",
        ]
        mounts = (f"{source.resolve()}:/src:ro", f"{build_dir.resolve()}:/build")
        flags = [
            "-DCMAKE_C_FLAGS_RELEASE=-O2 -DNDEBUG -ffile-prefix-map=/src=.",
            "-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG -ffile-prefix-map=/src=.",
            "-DCMAKE_SHARED_LINKER_FLAGS=-Wl,--build-id=none",
        ]
        run(
            docker_prefix(lock, *mounts, environment=tuple(environment))
            + ["cmake", "-S", "/src", "-B", "/build", *lock["build"]["cmake_options"], *flags]
        )
        run(
            docker_prefix(lock, *mounts, environment=tuple(environment))
            + ["cmake", "--build", "/build", "--parallel", "5", "--target", "ppsspp_libretro"]
        )
        built = build_dir / "lib/ppsspp_libretro.so"
        core = package_dir / lock["core"]["name"]
        shutil.copyfile(built, core)
        run(
            docker_prefix(lock, f"{package_dir.resolve()}:/package")
            + ["strip", "--strip-unneeded", f"/package/{core.name}"]
        )
        os.chmod(core, 0o644)
        inspect_core(core, lock)

        asset_manifest = copy_assets(source, package_dir / lock["assets"]["directory"])
        (package_dir / "ASSETS.sha256").write_bytes(asset_manifest)
        shutil.copyfile(source / "LICENSE.TXT", package_dir / "LICENSE.TXT")
        info = {
            "assets_file_count": str(len(asset_manifest.splitlines())),
            "assets_manifest_sha256": hashlib.sha256(asset_manifest).hexdigest(),
            "component_id": "r46h-gaming-ppsspp-v0.1",
            "core_sha256": sha256(core),
            "core_size": str(core.stat().st_size),
            "source_commit": lock["source"]["commit"],
            "source_tree": lock["source"]["tree"],
            "upstream_version": lock["source"]["tag"],
        }
        (package_dir / "BUILD-INFO").write_text(
            "".join(f"{key}={value}\n" for key, value in sorted(info.items())),
            encoding="utf-8",
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        write_deterministic_tar(package_dir, output, lock["source"]["source_date_epoch"])
        validate_artifact(output, lock)
        print(
            f"R46H_PPSSPP_BUILD result=pass size={output.stat().st_size} "
            f"sha256={sha256(output)} assets_sha256={info['assets_manifest_sha256']} "
            f"output={output.resolve()}"
        )
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)
        shutil.rmtree(package_dir, ignore_errors=True)


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
            print(f"R46H_PPSSPP_VALIDATE result=pass output={args.output.resolve()}")
    except (OSError, subprocess.CalledProcessError, tarfile.TarError, ValueError) as error:
        die(str(error))
    return 0


if __name__ == "__main__":
    sys.exit(main())
