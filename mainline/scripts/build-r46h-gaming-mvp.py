#!/usr/bin/env python3
"""Build the offline Debian-native RetroArch gaming product layer."""

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
from typing import Any


REPO = Path(__file__).resolve().parents[2]
CACHE_ROOT = REPO / "mainline/out/.cache/r46h-gaming-mvp-build"
RELEASE_ROOT = REPO / "mainline/out/r46h-gaming-mvp-v0.6"
BASE_IMAGE = (
    "arkos4clone/r46h-debian13-p2-mvp:v0.1@"
    "sha256:bd09bf6db6f1fb8f882621e98d70f01f976fd8dfba1bc897766afebd64cf51b9"
)
BASE_IMAGE_ID = "sha256:bd09bf6db6f1fb8f882621e98d70f01f976fd8dfba1bc897766afebd64cf51b9"
PAYLOAD_ID = "r46h-gaming-mvp-v0.6"
ARCHIVE_NAME = f"{PAYLOAD_ID}.tar.gz"
FSTAB_SHA256 = "390d3e67cfaa42aa2781b06c0bb167cae961034d22563584c58ae57e0d5cada5"
SOURCE_PATHS = (
    "mainline/gaming-mvp/Dockerfile",
    "mainline/gaming-input-bridge/r46h-input-bridge.c",
    "mainline/gaming-mvp/build-r46h-nes-smoke.py",
    "mainline/gaming-mvp/install.sh",
    "mainline/gaming-mvp/packages.txt",
    "mainline/gaming-mvp/r46h-game-ui",
    "mainline/gaming-mvp/r46h-gaming-frontend-condition",
    "mainline/gaming-mvp/r46h-gaming-frontend.service",
    "mainline/gaming-mvp/r46h-gaming-input-ready",
    "mainline/gaming-mvp/r46h-gaming-input.service",
    "mainline/gaming-mvp/r46h-volume-keys",
    "mainline/gaming-mvp/r46h-volume-keys.service",
    "mainline/gaming-mvp/r46h-smoke-core.c",
    "mainline/gaming-mvp/r46h-storage-audit",
    "mainline/gaming-mvp/retroarch.cfg",
    "mainline/rootfs-debian13/overlay/etc/fstab",
    "mainline/bringup-tests/GAMING-PRODUCT.md",
    "mainline/scripts/build-r46h-gaming-mvp.py",
    "mainline/tests/test-r46h-gaming-mvp.py",
)
PAYLOAD_TOP_LEVEL = {
    "PACKAGES.tsv",
    "PAYLOAD-INFO.json",
    "PAYLOAD.COMPLETE",
    "SHA256SUMS",
    "debs",
    "files",
    "install.sh",
}
PAYLOAD_FILES = {
    "files/GAMING-PRODUCT.md",
    "files/fstab",
    "files/r46h-game-ui",
    "files/r46h-gaming-frontend-condition",
    "files/r46h-gaming-frontend.service",
    "files/r46h-gaming-input-ready",
    "files/r46h-gaming-input.service",
    "files/r46h-volume-keys",
    "files/r46h-volume-keys.service",
    "files/r46h-input-bridge",
    "files/r46h-nes-smoke.nes",
    "files/r46h-smoke-libretro.so",
    "files/r46h-storage-audit",
    "files/retroarch.cfg",
}
GENERATION_FILES = {
    ARCHIVE_NAME,
    "BUILD-COMPLETE",
    "BUILD-RECEIPT.json",
    "SHA256SUMS",
    "SOURCE-MANIFEST.json",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
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
        raise BuildError("gaming MVP source scope must be committed and clean")
    commit = git_bytes(["rev-parse", "--verify", "HEAD^{commit}"]).decode().strip()
    tree = git_bytes(["rev-parse", "--verify", "HEAD^{tree}"]).decode().strip()
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise BuildError("invalid source commit")
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


def write_source_snapshot(root: Path, captured: dict[str, bytes]) -> Path:
    snapshot = root / "source"
    snapshot.mkdir(mode=0o700)
    for relative, payload in captured.items():
        destination = snapshot / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
    return snapshot


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


def docker_command() -> str:
    command = shutil.which("docker")
    if not command:
        raise BuildError("docker is unavailable")
    return command


def require_base_image(docker: str) -> None:
    result = subprocess.run(
        [docker, "--context", "desktop-linux", "image", "inspect", BASE_IMAGE, "--format", "{{.Id}} {{.Os}}/{{.Architecture}}"],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    expected = f"{BASE_IMAGE_ID} linux/arm64"
    if result.returncode != 0 or result.stdout.strip() != expected:
        raise BuildError(f"base image mismatch: expected {expected!r}")


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, check=False, text=True)
    if result.returncode != 0:
        raise BuildError(f"command exited {result.returncode}: {' '.join(command)}")
    return result


def payload_manifest(root: Path, excluded: set[str]) -> bytes:
    lines: list[str] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        metadata = path.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise BuildError(f"unsafe payload member: {path}")
        relative = path.relative_to(root).as_posix()
        if relative not in excluded:
            lines.append(f"{sha256_file(path)}  {relative}\n")
    return "".join(lines).encode()


def validate_payload_tree(payload: Path, required_packages: set[str]) -> dict[str, str]:
    require_directory(payload, "payload")
    if {entry.name for entry in payload.iterdir()} != PAYLOAD_TOP_LEVEL:
        raise BuildError("payload top-level member set mismatch")
    for relative in PAYLOAD_FILES | {"install.sh", "PACKAGES.tsv", "PAYLOAD-INFO.json", "SHA256SUMS", "PAYLOAD.COMPLETE"}:
        require_regular(payload / relative, relative)
    require_directory(payload / "debs", "Debian package directory")
    debs = sorted((payload / "debs").glob("*.deb"))
    if len(debs) < 20 or {entry for entry in (payload / "debs").iterdir()} != set(debs):
        raise BuildError("unexpected Debian package set")
    for deb in debs:
        require_regular(deb, "Debian package")
    packages: dict[str, str] = {}
    for line in (payload / "PACKAGES.tsv").read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) != 2 or not fields[0] or not fields[1] or fields[0] in packages:
            raise BuildError("invalid package version manifest")
        packages[fields[0]] = fields[1]
    if set(packages) != required_packages:
        raise BuildError("package version manifest does not cover the requested package set")
    info = exact_json(payload / "PAYLOAD-INFO.json")
    if info.get("format_version") != 1 or info.get("payload_id") != PAYLOAD_ID:
        raise BuildError("payload identity mismatch")
    if sha256_file(payload / "files/fstab") != FSTAB_SHA256:
        raise BuildError("payload fstab identity mismatch")
    sums = payload_manifest(payload, {"SHA256SUMS", "PAYLOAD.COMPLETE"})
    if (payload / "SHA256SUMS").read_bytes() != sums:
        raise BuildError("payload checksum manifest mismatch")
    expected_complete = f"sha256sums_sha256={sha256_bytes(sums)}\n".encode()
    if (payload / "PAYLOAD.COMPLETE").read_bytes() != expected_complete:
        raise BuildError("payload completion marker mismatch")
    core = payload / "files/r46h-smoke-libretro.so"
    if require_regular(core, "smoke core").st_size < 8_000:
        raise BuildError("smoke core is unexpectedly small")
    bridge = payload / "files/r46h-input-bridge"
    if require_regular(bridge, "input bridge").st_size < 20_000:
        raise BuildError("input bridge is unexpectedly small")
    rom = payload / "files/r46h-nes-smoke.nes"
    rom_bytes = rom.read_bytes()
    if len(rom_bytes) != 24_592 or rom_bytes[:16] != b"NES\x1a\x01\x01" + b"\x00" * 10:
        raise BuildError("NES smoke ROM identity mismatch")
    return packages


def run_container_validation(docker: str, payload: Path, work: Path) -> None:
    command = r"""set -Eeuo pipefail
mapfile -d '' debs < <(find /payload/debs -maxdepth 1 -type f -name '*.deb' -print0 | sort -z)
(( ${#debs[@]} > 0 ))
mkdir -m 0700 /tmp/empty-apt
mkdir -m 0700 /tmp/empty-apt/sources.list.d
: > /tmp/empty-apt/sources.list
apt-get \
  -o Dir::Etc::sourcelist=/tmp/empty-apt/sources.list \
  -o Dir::Etc::sourceparts=/tmp/empty-apt/sources.list.d \
  install -y --no-install-recommends "${debs[@]}" >/tmp/install.log
while IFS=$'\t' read -r package version; do
  [[ "$(dpkg-query -W -f='${db:Status-Abbrev}\t${Version}' "$package")" == $'ii \t'"$version" ]]
done < /payload/PACKAGES.tsv
install -D -m 0755 /payload/files/r46h-game-ui /usr/local/sbin/r46h-game-ui
install -D -m 0755 /payload/files/r46h-gaming-frontend-condition \
  /usr/local/libexec/r46h-gaming-frontend-condition
install -D -m 0755 /payload/files/r46h-input-bridge \
  /usr/local/libexec/r46h-input-bridge
install -D -m 0755 /payload/files/r46h-gaming-input-ready \
  /usr/local/libexec/r46h-gaming-input-ready
install -D -m 0755 /payload/files/r46h-volume-keys \
  /usr/local/libexec/r46h-volume-keys
install -D -m 0755 /payload/files/r46h-storage-audit \
  /usr/local/sbin/r46h-storage-audit
install -D -m 0644 /payload/files/r46h-gaming-frontend.service \
  /etc/systemd/system/r46h-gaming-frontend.service
install -D -m 0644 /payload/files/r46h-gaming-input.service \
  /etc/systemd/system/r46h-gaming-input.service
install -D -m 0644 /payload/files/r46h-volume-keys.service \
  /etc/systemd/system/r46h-volume-keys.service
install -D -m 0644 /payload/files/GAMING-PRODUCT.md \
  /usr/share/doc/r46h-gaming-mvp/GAMING-PRODUCT.md
systemd-analyze verify /etc/systemd/system/r46h-gaming-input.service \
  /etc/systemd/system/r46h-volume-keys.service \
  /etc/systemd/system/r46h-gaming-frontend.service
test "$(/usr/local/libexec/r46h-input-bridge --version)" = \
  r46h-gaming-input-bridge-v0.5
retroarch --features > /output/RETROARCH-FEATURES.txt
for feature in 'KMS             - Video context driver: yes' 'OpenGLES        - Video driver: yes' 'EGL             - Video context driver: yes' 'ALSA            - Audio driver: yes' 'UDEV            - UDEV/EVDEV input driver: yes'; do
  grep -Fq "$feature" /output/RETROARCH-FEATURES.txt
done
file /payload/files/r46h-smoke-libretro.so > /output/SMOKE-CORE-FILE.txt
grep -Eq 'ELF 64-bit.*ARM aarch64' /output/SMOKE-CORE-FILE.txt
ldd /usr/bin/retroarch > /output/RETROARCH-LDD.txt
! grep -Eiq 'not found|libMali' /output/RETROARCH-LDD.txt
printf '%s\n' 'video_driver = "null"' 'audio_driver = "null"' 'input_driver = "null"' > /tmp/null.cfg
set +e
timeout -s TERM -k 1 3 retroarch --verbose --config /tmp/null.cfg -L /payload/files/r46h-smoke-libretro.so > /output/SMOKE-CORE-LOAD.txt 2>&1
status=$?
set -e
[[ "$status" == 124 ]]
grep -Fq 'R46H Hardware Smoke' /output/SMOKE-CORE-LOAD.txt
set +e
timeout -s TERM -k 1 3 retroarch --verbose --config /tmp/null.cfg \
  -L /usr/lib/aarch64-linux-gnu/libretro/nestopia_libretro.so \
  /payload/files/r46h-nes-smoke.nes > /output/NESTOPIA-ROM-LOAD.txt 2>&1
status=$?
set -e
[[ "$status" == 124 ]]
grep -Fq 'Nestopia' /output/NESTOPIA-ROM-LOAD.txt
! grep -Fq '[ERROR] [Content]' /output/NESTOPIA-ROM-LOAD.txt
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
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                for path in [payload, *sorted(payload.rglob("*"), key=lambda item: item.relative_to(payload).as_posix())]:
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


def write_new(path: Path, payload: bytes, mode: int = 0o644) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def publish_generation(stage: Path, generation: str) -> Path:
    builds = RELEASE_ROOT / "builds"
    RELEASE_ROOT.mkdir(parents=True, exist_ok=True)
    builds.mkdir(exist_ok=True)
    destination = builds / generation
    if destination.exists() or destination.is_symlink():
        raise BuildError(f"generation already exists: {generation}")
    os.rename(stage, destination)
    pointer = RELEASE_ROOT / f".CURRENT.{os.getpid()}"
    write_new(pointer, f"{generation}\n".encode())
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
    sums = payload_manifest(generation, {"SHA256SUMS", "BUILD-COMPLETE"})
    if (generation / "SHA256SUMS").read_bytes() != sums:
        raise BuildError("generation checksum manifest mismatch")
    expected_complete = f"sha256sums_sha256={sha256_bytes(sums)}\n".encode()
    if (generation / "BUILD-COMPLETE").read_bytes() != expected_complete:
        raise BuildError("generation completion marker mismatch")
    receipt = exact_json(generation / "BUILD-RECEIPT.json")
    archive = generation / ARCHIVE_NAME
    if receipt.get("archive_sha256") != sha256_file(archive):
        raise BuildError("archive digest does not match build receipt")
    return generation


def command_build() -> Path:
    commit, tree, captured, source_manifest = capture_clean_source()
    required_packages = {
        line
        for line in captured["mainline/gaming-mvp/packages.txt"]
        .decode("utf-8")
        .splitlines()
        if line
    }
    docker = docker_command()
    require_base_image(docker)
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="work.", dir=CACHE_ROOT))
    container = ""
    image_tag = f"arkos4clone/r46h-gaming-mvp-build:{commit[:12]}-{os.getpid()}"
    published = False
    stage = work / "generation"
    try:
        source = write_source_snapshot(work, captured)
        payload = work / "payload"
        payload.mkdir(mode=0o700)
        run(
            [
                docker,
                "--context",
                "desktop-linux",
                "build",
                "--platform",
                "linux/arm64",
                "--file",
                str(source / "mainline/gaming-mvp/Dockerfile"),
                "--tag",
                image_tag,
                str(source / "mainline"),
            ]
        )
        create = subprocess.run(
            [docker, "--context", "desktop-linux", "create", "--platform", "linux/arm64", image_tag],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if create.returncode != 0 or re.fullmatch(r"[0-9a-f]{64}\n?", create.stdout) is None:
            raise BuildError("cannot create payload export container")
        container = create.stdout.strip()
        run([docker, "--context", "desktop-linux", "cp", f"{container}:/payload/.", str(payload)])
        run([docker, "--context", "desktop-linux", "rm", container])
        container = ""
        write_new(
            payload / "files/GAMING-PRODUCT.md",
            captured["mainline/bringup-tests/GAMING-PRODUCT.md"],
        )
        run(
            [
                sys.executable,
                "-B",
                str(source / "mainline/gaming-mvp/build-r46h-nes-smoke.py"),
                str(payload / "files/r46h-nes-smoke.nes"),
            ]
        )

        package_lines = (payload / "PACKAGES.tsv").read_text(encoding="utf-8").splitlines()
        write_new(
            payload / "PAYLOAD-INFO.json",
            canonical_json(
                {
                    "base_image": BASE_IMAGE,
                    "base_image_id": BASE_IMAGE_ID,
                    "format_version": 1,
                    "install_from_release": "6.12.99-r46h-mainline-v0.15-gaming-product",
                    "package_count": len(package_lines),
                    "payload_id": PAYLOAD_ID,
                    "source_git_commit": commit,
                    "target_release": "6.12.99-r46h-mainline-v0.15-gaming-product",
                }
            ),
        )
        sums = payload_manifest(payload, {"SHA256SUMS", "PAYLOAD.COMPLETE"})
        write_new(payload / "SHA256SUMS", sums)
        write_new(payload / "PAYLOAD.COMPLETE", f"sha256sums_sha256={sha256_bytes(sums)}\n".encode())
        validate_payload_tree(payload, required_packages)
        run_container_validation(docker, payload, work)

        stage.mkdir(mode=0o700)
        archive = stage / ARCHIVE_NAME
        deterministic_archive(payload, archive)
        write_new(stage / "SOURCE-MANIFEST.json", source_manifest)
        archive_sha = sha256_file(archive)
        write_new(
            stage / "BUILD-RECEIPT.json",
            canonical_json(
                {
                    "archive_sha256": archive_sha,
                    "archive_size": archive.stat().st_size,
                    "base_image_id": BASE_IMAGE_ID,
                    "format_version": 1,
                    "payload_id": PAYLOAD_ID,
                    "source_git_commit": commit,
                    "source_git_tree": tree,
                    "source_manifest_sha256": sha256_bytes(source_manifest),
                }
            ),
        )
        generation_sums = payload_manifest(stage, {"SHA256SUMS", "BUILD-COMPLETE"})
        write_new(stage / "SHA256SUMS", generation_sums)
        write_new(stage / "BUILD-COMPLETE", f"sha256sums_sha256={sha256_bytes(generation_sums)}\n".encode())
        generation_name = f"build-{commit[:12]}-{archive_sha[:12]}"
        destination = publish_generation(stage, generation_name)
        published = True
        validate_generation()
        print(f"PASS: gaming MVP payload published at {destination}")
        print(f"ARCHIVE={destination / ARCHIVE_NAME}")
        print(f"ARCHIVE_SHA256={archive_sha}")
        return destination
    finally:
        if container:
            subprocess.run([docker, "--context", "desktop-linux", "rm", "-f", container], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run([docker, "--context", "desktop-linux", "image", "rm", "-f", image_tag], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not published and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "validate"))
    return parser.parse_args()


def main() -> int:
    try:
        args = parse_args()
        if args.action == "build":
            command_build()
        else:
            generation = validate_generation()
            print(f"PASS: gaming MVP generation validated at {generation}")
    except (BuildError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
