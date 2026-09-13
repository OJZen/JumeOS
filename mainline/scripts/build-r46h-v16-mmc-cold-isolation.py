#!/usr/bin/env python3
"""Build and validate the R46H v0.16 cold-MMC DTB one-shot."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import tempfile


REPO = Path(__file__).resolve().parents[2]
MAINLINE = REPO / "mainline"
CACHE_PARENT = MAINLINE / "out/.cache"
RELEASE_ROOT = MAINLINE / "out/r46h-v16-mmc-cold-isolation"
BASE_PACKAGE = MAINLINE / "out/r46h-mainline-test-v0.15-gaming-product.tar.gz"
BASE_PACKAGE_SIZE = 33_268_548
BASE_PACKAGE_SHA256 = (
    "748d81cc0e8b9bf353430db1f4ee358bf09dee1d32db85a855961368b58d3fad"
)
BASE_PACKAGE_ROOT = "r46h-mainline-test-v0.15-gaming-product"
BASE_DTB_MEMBER = f"{BASE_PACKAGE_ROOT}/boot/rk3326-r46h-mainline-test.dtb"
BASE_DTB_SIZE = 49_518
BASE_DTB_SHA256 = (
    "4d6d4ebad3b98600b6e9a38df4ca82230335558497a9e15dd0e81ca60e304b61"
)
BASE_IMAGE_PATH = "/var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/IMAGE"
BASE_IMAGE_SIZE = 41_570_816
BASE_IMAGE_SHA256 = (
    "956ab3d5a2e53afbfe964ae75850e8591b44c093b9779867b31149b7b591f68f"
)
OVERLAY_RELATIVE = "mainline/board/r46h/rk3326-r46h-v16-mmc-cold-isolation.dtso"
OVERLAY = REPO / OVERLAY_RELATIVE
TEST_RELATIVE = "mainline/tests/test-r46h-v16-mmc-cold-isolation.py"
RUNBOOK_RELATIVE = "mainline/bringup-tests/V16-MMC-COLD-ISOLATION.md"
BUILDER_RELATIVE = "mainline/scripts/build-r46h-v16-mmc-cold-isolation.py"
SOURCE_PATHS = (BUILDER_RELATIVE, OVERLAY_RELATIVE, TEST_RELATIVE, RUNBOOK_RELATIVE)
DOCKER_CONTEXT = "desktop-linux"
DOCKER_IMAGE = "arkos4clone/r46h-kernel-builder:trixie-arm64"
DOCKER_IMAGE_ID = (
    "sha256:3686fd20408cf746c1171e9345fd6c842a71f87e589f691b2455435b3bdd141a"
)
DOCKER_CLI = Path("/Applications/Docker.app/Contents/Resources/bin/docker")
SOURCE_DATE_EPOCH = 1_785_369_600
ROOT_PARTUUID = "c9f931c9-02"
PAYLOAD_DIRECTORY = "v0.16-disable-secondary"
TARGET_PARENT = "/var/lib/r46h-mmc-cold-isolation"
TARGET_DIRECTORY = f"{TARGET_PARENT}/{PAYLOAD_DIRECTORY}"
ARCHIVE_NAME = "r46h-v16-mmc-cold-isolation.tar.gz"
PAYLOAD_NAMES = {
    "LAUNCH.txt",
    "R46H-V16.SCR",
    "R46H.DTB",
    "RECEIPT.json",
    "SHA256SUMS",
    "UBOOT-CMDS.txt",
    "r46h-v16-mmc-cold-isolation.dtbo",
}
RELEASE_NAMES = {
    ARCHIVE_NAME,
    f"{ARCHIVE_NAME}.sha256",
    "BUILD-RECEIPT.json",
    "SOURCE-MANIFEST.json",
}


class BuildError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
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


def require_clean_source() -> tuple[str, str, bytes]:
    status = git_bytes(
        ["status", "--porcelain=v1", "--untracked-files=all", "--", *SOURCE_PATHS]
    )
    if status:
        raise BuildError("v0.16 cold-MMC source scope is not committed and clean")
    commit = git_bytes(["rev-parse", "--verify", "HEAD^{commit}"]).decode().strip()
    tree = git_bytes(["rev-parse", "--verify", "HEAD^{tree}"]).decode().strip()
    entries: list[dict[str, object]] = []
    for relative in SOURCE_PATHS:
        live = REPO / relative
        metadata = live.lstat()
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise BuildError(f"unsafe source identity: {relative}")
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
        entries.append(
            {
                "git_mode": fields[0],
                "path": relative,
                "sha256": sha256_bytes(blob),
                "size": len(blob),
            }
        )
    return commit, tree, canonical_json(
        {
            "file_count": len(entries),
            "files": entries,
            "format_version": 1,
            "git_commit": commit,
            "git_tree": tree,
        }
    )


def require_regular(path: Path, size: int | None = None, digest: str | None = None) -> None:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise BuildError(f"unsafe regular file: {path}")
    if size is not None and metadata.st_size != size:
        raise BuildError(f"file size mismatch: {path}")
    if digest is not None and sha256_file(path) != digest:
        raise BuildError(f"file SHA-256 mismatch: {path}")


def read_base_dtb() -> bytes:
    metadata = BASE_PACKAGE.lstat()
    if (
        BASE_PACKAGE.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_size != BASE_PACKAGE_SIZE
    ):
        raise BuildError("unsafe base package identity")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(BASE_PACKAGE, flags)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
        ):
            raise BuildError("base package changed while opening")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            digest = hashlib.sha256()
            while block := handle.read(1024 * 1024):
                digest.update(block)
            if digest.hexdigest() != BASE_PACKAGE_SHA256:
                raise BuildError("base package SHA-256 mismatch")
            handle.seek(0)
            with tarfile.open(fileobj=handle, mode="r:gz") as archive:
                matches = [
                    member
                    for member in archive.getmembers()
                    if member.name == BASE_DTB_MEMBER
                ]
                if len(matches) != 1 or not matches[0].isfile():
                    raise BuildError("base package DTB member mismatch")
                stream = archive.extractfile(matches[0])
                if stream is None:
                    raise BuildError("cannot read base package DTB")
                payload = stream.read()
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ):
            raise BuildError("base package changed while reading")
    finally:
        os.close(descriptor)
    if len(payload) != BASE_DTB_SIZE or sha256_bytes(payload) != BASE_DTB_SHA256:
        raise BuildError("base v0.15 DTB identity mismatch")
    return payload


def docker_output(arguments: list[str]) -> str:
    result = subprocess.run(
        [str(DOCKER_CLI), *arguments], check=False, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise BuildError(result.stderr.strip() or "Docker command failed")
    return result.stdout.strip()


def require_toolchain() -> dict[str, str]:
    metadata = DOCKER_CLI.lstat()
    mode = stat.S_IMODE(metadata.st_mode)
    if (
        DOCKER_CLI.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid not in {0, os.geteuid()}
        or mode & 0o022
        or not mode & 0o111
    ):
        raise BuildError("unsafe fixed Docker CLI")
    if docker_output(["context", "show"]) != DOCKER_CONTEXT:
        raise BuildError("unexpected Docker context")
    server = docker_output(["info", "--format", "{{.ServerVersion}}"])
    client = docker_output(["version", "--format", "{{.Client.Version}}"])
    image_id = docker_output(["image", "inspect", "--format", "{{.Id}}", DOCKER_IMAGE])
    if image_id != DOCKER_IMAGE_ID:
        raise BuildError("builder image identity mismatch")
    return {"docker_client_version": client, "docker_server_version": server}


def docker_run(work: Path, script: str) -> None:
    result = subprocess.run(
        [
            str(DOCKER_CLI),
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--mount",
            f"type=bind,source={work},target=/work",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=16m",
            "--env",
            f"SOURCE_DATE_EPOCH={SOURCE_DATE_EPOCH}",
            DOCKER_IMAGE_ID,
            "/bin/sh",
            "-ceu",
            script,
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    if result.returncode != 0:
        raise BuildError(f"isolated DT tool failed:\n{result.stdout}")


def compile_candidate(base_dtb: bytes, overlay: bytes) -> tuple[bytes, bytes]:
    CACHE_PARENT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="r46h-v16-mmc-cold-isolation.", dir=CACHE_PARENT
    ) as temporary:
        work = Path(temporary)
        (work / "base.dtb").write_bytes(base_dtb)
        (work / "candidate.dtso").write_bytes(overlay)
        docker_run(
            work,
            """
umask 077
dtc -q -@ -I dts -O dtb -o /work/first.dtbo /work/candidate.dtso
fdtoverlay -i /work/base.dtb -o /work/first.dtb /work/first.dtbo
dtc -q -@ -I dts -O dtb -o /work/second.dtbo /work/candidate.dtso
fdtoverlay -i /work/base.dtb -o /work/second.dtb /work/second.dtbo
test "$(fdtget -t s /work/base.dtb /mmc@ff370000 status)" = okay
test "$(fdtget -t s /work/base.dtb /mmc@ff380000 status)" = okay
test "$(fdtget -t s /work/first.dtb /mmc@ff370000 status)" = okay
test "$(fdtget -t s /work/first.dtb /mmc@ff380000 status)" = disabled
test "$(fdtget -t s /work/first.dtb /aliases mmc0)" = /mmc@ff370000
test "$(fdtget -t s /work/first.dtb /aliases mmc1)" = /mmc@ff380000
cmp /work/first.dtbo /work/second.dtbo
cmp /work/first.dtb /work/second.dtb
""",
        )
        return (work / "first.dtb").read_bytes(), (work / "first.dtbo").read_bytes()


def apply_overlay_binary(base_dtb: bytes, overlay_binary: bytes) -> bytes:
    CACHE_PARENT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="r46h-v16-overlay-verify.", dir=CACHE_PARENT
    ) as temporary:
        work = Path(temporary)
        (work / "base.dtb").write_bytes(base_dtb)
        (work / "candidate.dtbo").write_bytes(overlay_binary)
        docker_run(
            work,
            """
umask 077
fdtoverlay -i /work/base.dtb -o /work/candidate.dtb /work/candidate.dtbo
test "$(fdtget -t s /work/candidate.dtb /mmc@ff370000 status)" = okay
test "$(fdtget -t s /work/candidate.dtb /mmc@ff380000 status)" = disabled
test "$(fdtget -t s /work/candidate.dtb /aliases mmc0)" = /mmc@ff370000
test "$(fdtget -t s /work/candidate.dtb /aliases mmc1)" = /mmc@ff380000
""",
        )
        return (work / "candidate.dtb").read_bytes()


def render_uboot_commands(candidate_size: int) -> bytes:
    bootargs = (
        f"root=PARTUUID={ROOT_PARTUUID} rootwait rw fsck.repair=yes "
        "net.ifnames=0 console=ttyS2,115200n8 earlycon loglevel=7 "
        "ignore_loglevel plymouth.enable=0 clk_ignore_unused pd_ignore_unused"
    )
    return f"""# R46H v0.16 cold-MMC one-shot; p1 and U-Boot environment remain unchanged.
setenv loadaddr 0x02000000
setenv dtb_loadaddr 0x01f00000
setenv bootargs \"{bootargs}\"
if ext4load mmc 1:2 ${{loadaddr}} {BASE_IMAGE_PATH}; then
  if itest ${{filesize}} -eq {BASE_IMAGE_SIZE:#x}; then
    if ext4load mmc 1:2 ${{dtb_loadaddr}} {TARGET_DIRECTORY}/R46H.DTB; then
      if itest ${{filesize}} -eq {candidate_size:#x}; then
        booti ${{loadaddr}} - ${{dtb_loadaddr}}
      else
        echo \"R46H v0.16: candidate DTB size mismatch\"
      fi
    else
      echo \"R46H v0.16: candidate DTB load failed\"
    fi
  else
    echo \"R46H v0.16: base Image size mismatch\"
  fi
else
  echo \"R46H v0.16: base Image load failed\"
fi
""".encode()


def make_script_image(commands: bytes) -> bytes:
    CACHE_PARENT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="r46h-v16-mkimage.", dir=CACHE_PARENT
    ) as temporary:
        work = Path(temporary)
        (work / "commands.txt").write_bytes(commands)
        docker_run(
            work,
            """
umask 077
mkimage -A arm64 -O linux -T script -C none -a 0 -e 0 \
  -n 'R46H v0.16 MMC cold isolation' \
  -d /work/commands.txt /work/first.scr >/dev/null
mkimage -A arm64 -O linux -T script -C none -a 0 -e 0 \
  -n 'R46H v0.16 MMC cold isolation' \
  -d /work/commands.txt /work/second.scr >/dev/null
cmp /work/first.scr /work/second.scr
""",
        )
        return (work / "first.scr").read_bytes()


def render_launch(script_size: int) -> bytes:
    return (
        f"ext4load mmc 1:2 0x0b000000 {TARGET_DIRECTORY}/R46H-V16.SCR\n"
        f"if itest ${{filesize}} -eq {script_size:#x}; then source 0x0b000000; fi\n"
    ).encode()


def payload_files(
    candidate: bytes, overlay_binary: bytes, source_commit: str
) -> dict[str, bytes]:
    commands = render_uboot_commands(len(candidate))
    script = make_script_image(commands)
    files = {
        "LAUNCH.txt": render_launch(len(script)),
        "R46H-V16.SCR": script,
        "R46H.DTB": candidate,
        "RECEIPT.json": canonical_json(
            {
                "base_dtb_sha256": BASE_DTB_SHA256,
                "base_image_path": BASE_IMAGE_PATH,
                "base_image_sha256": BASE_IMAGE_SHA256,
                "candidate": "v0.16-disable-secondary",
                "candidate_dtb_sha256": sha256_bytes(candidate),
                "disabled_node": "/mmc@ff380000",
                "format_version": 1,
                "kernel_release": "6.12.99-r46h-mainline-v0.15-gaming-product",
                "source_git_commit": source_commit,
                "system_node": "/mmc@ff370000",
            }
        ),
        "UBOOT-CMDS.txt": commands,
        "r46h-v16-mmc-cold-isolation.dtbo": overlay_binary,
    }
    files["SHA256SUMS"] = "".join(
        f"{sha256_bytes(value)}  {name}\n" for name, value in sorted(files.items())
    ).encode()
    if set(files) != PAYLOAD_NAMES:
        raise BuildError("internal payload member mismatch")
    return files


def deterministic_archive(files: dict[str, bytes]) -> bytes:
    with io.BytesIO() as raw:
        with gzip.GzipFile(filename="", mode="wb", mtime=0, fileobj=raw) as compressed:
            with tarfile.open(
                fileobj=compressed, mode="w", format=tarfile.USTAR_FORMAT
            ) as archive:
                directory = tarfile.TarInfo(PAYLOAD_DIRECTORY)
                directory.type = tarfile.DIRTYPE
                directory.mode = 0o700
                directory.uid = directory.gid = 0
                directory.uname = directory.gname = "root"
                directory.mtime = SOURCE_DATE_EPOCH
                archive.addfile(directory)
                for name, value in sorted(files.items()):
                    info = tarfile.TarInfo(f"{PAYLOAD_DIRECTORY}/{name}")
                    info.size = len(value)
                    info.mode = 0o400
                    info.uid = info.gid = 0
                    info.uname = info.gname = "root"
                    info.mtime = SOURCE_DATE_EPOCH
                    archive.addfile(info, io.BytesIO(value))
        return raw.getvalue()


def validate_archive(archive_bytes: bytes) -> dict[str, bytes]:
    observed: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        members = archive.getmembers()
        expected = {PAYLOAD_DIRECTORY} | {
            f"{PAYLOAD_DIRECTORY}/{name}" for name in PAYLOAD_NAMES
        }
        if {member.name for member in members} != expected:
            raise BuildError("archive member set mismatch")
        for member in members:
            if member.issym() or member.islnk() or member.uid != 0 or member.gid != 0:
                raise BuildError("unsafe archive member")
            if member.name == PAYLOAD_DIRECTORY:
                if not member.isdir() or stat.S_IMODE(member.mode) != 0o700:
                    raise BuildError("unsafe archive directory")
                continue
            if not member.isfile() or stat.S_IMODE(member.mode) != 0o400:
                raise BuildError("unsafe archive file")
            stream = archive.extractfile(member)
            if stream is None:
                raise BuildError("cannot read archive member")
            observed[member.name.removeprefix(f"{PAYLOAD_DIRECTORY}/")] = stream.read()
    checksum_lines = observed["SHA256SUMS"].decode().splitlines()
    expected_lines = [
        f"{sha256_bytes(value)}  {name}"
        for name, value in sorted(observed.items())
        if name != "SHA256SUMS"
    ]
    if checksum_lines != expected_lines:
        raise BuildError("payload checksum manifest mismatch")
    return observed


def build() -> Path:
    if RELEASE_ROOT.exists() or RELEASE_ROOT.is_symlink():
        raise BuildError(f"release output already exists: {RELEASE_ROOT}")
    source_commit, source_tree, source_manifest = require_clean_source()
    docker_versions = require_toolchain()
    base = read_base_dtb()
    candidate, overlay_binary = compile_candidate(base, OVERLAY.read_bytes())
    files = payload_files(candidate, overlay_binary, source_commit)
    archive = deterministic_archive(files)
    if archive != deterministic_archive(files):
        raise BuildError("archive is not deterministic")
    validate_archive(archive)
    receipt = canonical_json(
        {
            "archive_sha256": sha256_bytes(archive),
            "archive_size": len(archive),
            "base_package_sha256": BASE_PACKAGE_SHA256,
            "builder_image_id": DOCKER_IMAGE_ID,
            "candidate_dtb_sha256": sha256_bytes(candidate),
            "candidate_dtb_size": len(candidate),
            "docker_context": DOCKER_CONTEXT,
            "format_version": 1,
            "source_git_commit": source_commit,
            "source_git_tree": source_tree,
            "source_manifest_sha256": sha256_bytes(source_manifest),
            **docker_versions,
        }
    )
    CACHE_PARENT.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="r46h-v16-release.", dir=CACHE_PARENT))
    try:
        (stage / ARCHIVE_NAME).write_bytes(archive)
        (stage / f"{ARCHIVE_NAME}.sha256").write_text(
            f"{sha256_bytes(archive)}  {ARCHIVE_NAME}\n", encoding="ascii"
        )
        (stage / "BUILD-RECEIPT.json").write_bytes(receipt)
        (stage / "SOURCE-MANIFEST.json").write_bytes(source_manifest)
        for path in stage.iterdir():
            path.chmod(0o400)
        os.replace(stage, RELEASE_ROOT)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    validate_release(RELEASE_ROOT)
    return RELEASE_ROOT


def validate_release(root: Path) -> dict[str, object]:
    metadata = root.lstat()
    if root.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise BuildError("unsafe release directory")
    if {path.name for path in root.iterdir()} != RELEASE_NAMES:
        raise BuildError("release member set mismatch")
    for path in root.iterdir():
        require_regular(path)
    receipt = json.loads((root / "BUILD-RECEIPT.json").read_bytes())
    required_receipt = {
        "base_package_sha256": BASE_PACKAGE_SHA256,
        "builder_image_id": DOCKER_IMAGE_ID,
        "docker_context": DOCKER_CONTEXT,
        "format_version": 1,
    }
    for key, value in required_receipt.items():
        if receipt.get(key) != value:
            raise BuildError(f"release receipt {key} mismatch")
    source_manifest = (root / "SOURCE-MANIFEST.json").read_bytes()
    if sha256_bytes(source_manifest) != receipt.get("source_manifest_sha256"):
        raise BuildError("release source manifest mismatch")
    parsed_source = json.loads(source_manifest)
    if (
        parsed_source.get("git_commit") != receipt.get("source_git_commit")
        or parsed_source.get("git_tree") != receipt.get("source_git_tree")
    ):
        raise BuildError("release source identity mismatch")
    archive = (root / ARCHIVE_NAME).read_bytes()
    if (
        len(archive) != receipt["archive_size"]
        or sha256_bytes(archive) != receipt["archive_sha256"]
    ):
        raise BuildError("release archive identity mismatch")
    if (root / f"{ARCHIVE_NAME}.sha256").read_text(encoding="ascii") != (
        f"{receipt['archive_sha256']}  {ARCHIVE_NAME}\n"
    ):
        raise BuildError("release archive sidecar mismatch")
    files = validate_archive(archive)
    if (
        len(files["R46H.DTB"]) != receipt["candidate_dtb_size"]
        or sha256_bytes(files["R46H.DTB"]) != receipt["candidate_dtb_sha256"]
    ):
        raise BuildError("release candidate DTB mismatch")
    require_toolchain()
    rebuilt = apply_overlay_binary(
        read_base_dtb(), files["r46h-v16-mmc-cold-isolation.dtbo"]
    )
    if rebuilt != files["R46H.DTB"]:
        raise BuildError("release overlay does not reproduce candidate DTB")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "validate"))
    arguments = parser.parse_args()
    try:
        if arguments.command == "build":
            destination = build()
            print(f"PASS: v0.16 cold-MMC candidate published at {destination}")
        else:
            receipt = validate_release(RELEASE_ROOT)
            print(
                "PASS: v0.16 cold-MMC candidate validated "
                f"sha256={receipt['archive_sha256']}"
            )
    except (BuildError, OSError, tarfile.TarError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=os.sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
