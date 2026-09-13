#!/usr/bin/env python3
"""Build and validate the R46H v0.17 cold-MMC power-settle one-shot."""

from __future__ import annotations

import argparse
import gzip
import importlib.util
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
RELEASE_ROOT = MAINLINE / "out/r46h-v17-mmc-power-settle"
HELPER_RELATIVE = "mainline/scripts/build-r46h-v16-mmc-cold-isolation.py"
HELPER_PATH = REPO / HELPER_RELATIVE
OVERLAY_RELATIVE = "mainline/board/r46h/rk3326-r46h-v17-mmc-power-settle.dtso"
OVERLAY = REPO / OVERLAY_RELATIVE
TEST_RELATIVE = "mainline/tests/test-r46h-v17-mmc-power-settle.py"
RUNBOOK_RELATIVE = "mainline/bringup-tests/V17-MMC-POWER-SETTLE.md"
BUILDER_RELATIVE = "mainline/scripts/build-r46h-v17-mmc-power-settle.py"
SOURCE_PATHS = (
    BUILDER_RELATIVE,
    OVERLAY_RELATIVE,
    TEST_RELATIVE,
    RUNBOOK_RELATIVE,
    HELPER_RELATIVE,
)
POWER_SETTLE_MS = 800
ROOT_PARTUUID = "c9f931c9-02"
PAYLOAD_DIRECTORY = "v0.17-800ms-single-host"
TARGET_PARENT = "/var/lib/r46h-mmc-power-settle"
TARGET_DIRECTORY = f"{TARGET_PARENT}/{PAYLOAD_DIRECTORY}"
ARCHIVE_NAME = "r46h-v17-mmc-power-settle.tar.gz"
PAYLOAD_NAMES = {
    "LAUNCH.txt",
    "R46H-V17.SCR",
    "R46H.DTB",
    "RECEIPT.json",
    "SHA256SUMS",
    "UBOOT-CMDS.txt",
    "r46h-v17-mmc-power-settle.dtbo",
}
RELEASE_NAMES = {
    ARCHIVE_NAME,
    f"{ARCHIVE_NAME}.sha256",
    "BUILD-RECEIPT.json",
    "SOURCE-MANIFEST.json",
}


def helper_git_bytes(arguments: list[str]) -> bytes:
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
    result = subprocess.run(
        ["/usr/bin/git", "--no-replace-objects", "-C", str(REPO), *arguments],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=environment,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(arguments)} failed before helper load: "
            f"{result.stderr.decode(errors='replace').strip()}"
        )
    return result.stdout


def load_helper():
    metadata = HELPER_PATH.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise RuntimeError("unsafe frozen v0.16 DTB helper identity")
    descriptor = os.open(HELPER_PATH, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
        ):
            raise RuntimeError("frozen v0.16 DTB helper changed while opening")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            live = handle.read()
        after = os.fstat(descriptor)
        if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != (
            opened.st_dev,
            opened.st_ino,
            opened.st_size,
            opened.st_mtime_ns,
        ):
            raise RuntimeError("frozen v0.16 DTB helper changed while reading")
    finally:
        os.close(descriptor)
    listing = helper_git_bytes(["ls-tree", "HEAD", "--", HELPER_RELATIVE])
    fields = listing.decode().strip().split(None, 3)
    committed = helper_git_bytes(["cat-file", "blob", f"HEAD:{HELPER_RELATIVE}"])
    if (
        len(fields) != 4
        or fields[1] != "blob"
        or fields[3] != HELPER_RELATIVE
        or live != committed
    ):
        raise RuntimeError("frozen v0.16 DTB helper is not one unchanged HEAD blob")
    spec = importlib.util.spec_from_file_location("r46h_v16_mmc_helper", HELPER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen v0.16 DTB helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HELPER = load_helper()
BuildError = HELPER.BuildError
BASE_PACKAGE = HELPER.BASE_PACKAGE
BASE_PACKAGE_SIZE = HELPER.BASE_PACKAGE_SIZE
BASE_PACKAGE_SHA256 = HELPER.BASE_PACKAGE_SHA256
BASE_DTB_SIZE = HELPER.BASE_DTB_SIZE
BASE_DTB_SHA256 = HELPER.BASE_DTB_SHA256
BASE_IMAGE_PATH = HELPER.BASE_IMAGE_PATH
BASE_IMAGE_SIZE = HELPER.BASE_IMAGE_SIZE
BASE_IMAGE_SHA256 = HELPER.BASE_IMAGE_SHA256
DOCKER_CONTEXT = HELPER.DOCKER_CONTEXT
DOCKER_IMAGE_ID = HELPER.DOCKER_IMAGE_ID
SOURCE_DATE_EPOCH = HELPER.SOURCE_DATE_EPOCH


sha256_bytes = HELPER.sha256_bytes
sha256_file = HELPER.sha256_file
canonical_json = HELPER.canonical_json
git_bytes = HELPER.git_bytes
require_regular = HELPER.require_regular
read_base_dtb = HELPER.read_base_dtb
require_toolchain = HELPER.require_toolchain
docker_run = HELPER.docker_run


def require_clean_source() -> tuple[str, str, bytes]:
    status = git_bytes(
        ["status", "--porcelain=v1", "--untracked-files=all", "--", *SOURCE_PATHS]
    )
    if status:
        raise BuildError("v0.17 power-settle source scope is not committed and clean")
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


def compile_candidate(base_dtb: bytes, overlay: bytes) -> tuple[bytes, bytes]:
    CACHE_PARENT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="r46h-v17-mmc-power-settle.", dir=CACHE_PARENT
    ) as temporary:
        work = Path(temporary)
        (work / "base.dtb").write_bytes(base_dtb)
        (work / "candidate.dtso").write_bytes(overlay)
        docker_run(
            work,
            f"""
umask 077
dtc -q -@ -I dts -O dtb -o /work/first.dtbo /work/candidate.dtso
fdtoverlay -i /work/base.dtb -o /work/first.dtb /work/first.dtbo
dtc -q -@ -I dts -O dtb -o /work/second.dtbo /work/candidate.dtso
fdtoverlay -i /work/base.dtb -o /work/second.dtb /work/second.dtbo
test "$(fdtget -t s /work/base.dtb /mmc@ff370000 status)" = okay
test "$(fdtget -t s /work/base.dtb /mmc@ff380000 status)" = okay
! fdtget -t u /work/base.dtb /mmc@ff370000 post-power-on-delay-ms
test "$(fdtget -t s /work/first.dtb /mmc@ff370000 status)" = okay
test "$(fdtget -t u /work/first.dtb /mmc@ff370000 post-power-on-delay-ms)" = {POWER_SETTLE_MS}
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
        prefix="r46h-v17-overlay-verify.", dir=CACHE_PARENT
    ) as temporary:
        work = Path(temporary)
        (work / "base.dtb").write_bytes(base_dtb)
        (work / "candidate.dtbo").write_bytes(overlay_binary)
        docker_run(
            work,
            f"""
umask 077
fdtoverlay -i /work/base.dtb -o /work/candidate.dtb /work/candidate.dtbo
test "$(fdtget -t s /work/candidate.dtb /mmc@ff370000 status)" = okay
test "$(fdtget -t u /work/candidate.dtb /mmc@ff370000 post-power-on-delay-ms)" = {POWER_SETTLE_MS}
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
    return f"""# R46H v0.17 power-settle one-shot; p1 and U-Boot environment remain unchanged.
setenv loadaddr 0x02000000
setenv dtb_loadaddr 0x01f00000
setenv bootargs \"{bootargs}\"
if ext4load mmc 1:2 ${{loadaddr}} {BASE_IMAGE_PATH}; then
  if itest ${{filesize}} -eq {BASE_IMAGE_SIZE:#x}; then
    if ext4load mmc 1:2 ${{dtb_loadaddr}} {TARGET_DIRECTORY}/R46H.DTB; then
      if itest ${{filesize}} -eq {candidate_size:#x}; then
        booti ${{loadaddr}} - ${{dtb_loadaddr}}
      else
        echo \"R46H v0.17: candidate DTB size mismatch\"
      fi
    else
      echo \"R46H v0.17: candidate DTB load failed\"
    fi
  else
    echo \"R46H v0.17: base Image size mismatch\"
  fi
else
  echo \"R46H v0.17: base Image load failed\"
fi
""".encode()


def make_script_image(commands: bytes) -> bytes:
    CACHE_PARENT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="r46h-v17-mkimage.", dir=CACHE_PARENT
    ) as temporary:
        work = Path(temporary)
        (work / "commands.txt").write_bytes(commands)
        docker_run(
            work,
            """
umask 077
mkimage -A arm64 -O linux -T script -C none -a 0 -e 0 \
  -n 'R46H v0.17 MMC power settle' \
  -d /work/commands.txt /work/first.scr >/dev/null
mkimage -A arm64 -O linux -T script -C none -a 0 -e 0 \
  -n 'R46H v0.17 MMC power settle' \
  -d /work/commands.txt /work/second.scr >/dev/null
cmp /work/first.scr /work/second.scr
""",
        )
        return (work / "first.scr").read_bytes()


def render_launch(script_size: int) -> bytes:
    return (
        f"ext4load mmc 1:2 0x0b000000 {TARGET_DIRECTORY}/R46H-V17.SCR\n"
        f"if itest ${{filesize}} -eq {script_size:#x}; then source 0x0b000000; fi\n"
    ).encode()


def payload_files(
    candidate: bytes, overlay_binary: bytes, source_commit: str
) -> dict[str, bytes]:
    commands = render_uboot_commands(len(candidate))
    script = make_script_image(commands)
    files = {
        "LAUNCH.txt": render_launch(len(script)),
        "R46H-V17.SCR": script,
        "R46H.DTB": candidate,
        "RECEIPT.json": canonical_json(
            {
                "base_dtb_sha256": BASE_DTB_SHA256,
                "base_image_path": BASE_IMAGE_PATH,
                "base_image_sha256": BASE_IMAGE_SHA256,
                "candidate": PAYLOAD_DIRECTORY,
                "candidate_dtb_sha256": sha256_bytes(candidate),
                "disabled_node": "/mmc@ff380000",
                "format_version": 1,
                "kernel_release": "6.12.99-r46h-mainline-v0.15-gaming-product",
                "post_power_on_delay_ms": POWER_SETTLE_MS,
                "source_git_commit": source_commit,
                "system_node": "/mmc@ff370000",
            }
        ),
        "UBOOT-CMDS.txt": commands,
        "r46h-v17-mmc-power-settle.dtbo": overlay_binary,
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
        if len(members) != len(expected) or {member.name for member in members} != expected:
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
    entries = parsed_source.get("files")
    if (
        parsed_source.get("file_count") != len(SOURCE_PATHS)
        or not isinstance(entries, list)
        or not all(isinstance(entry, dict) for entry in entries)
        or [entry.get("path") for entry in entries] != list(SOURCE_PATHS)
    ):
        raise BuildError("release source closure mismatch")
    source_commit = receipt["source_git_commit"]
    source_tree = git_bytes(["rev-parse", "--verify", f"{source_commit}^{{tree}}"])
    if source_tree.decode().strip() != receipt["source_git_tree"]:
        raise BuildError("release source commit tree mismatch")
    for entry in entries:
        relative = entry["path"]
        listing = git_bytes(["ls-tree", source_commit, "--", relative]).decode().strip()
        fields = listing.split(None, 3)
        blob = git_bytes(["cat-file", "blob", f"{source_commit}:{relative}"])
        if (
            len(fields) != 4
            or fields[1] != "blob"
            or fields[3] != relative
            or entry.get("git_mode") != fields[0]
            or entry.get("size") != len(blob)
            or entry.get("sha256") != sha256_bytes(blob)
        ):
            raise BuildError(f"release source blob mismatch: {relative}")
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
    payload_receipt = json.loads(files["RECEIPT.json"])
    expected_payload_receipt = {
        "base_dtb_sha256": BASE_DTB_SHA256,
        "base_image_path": BASE_IMAGE_PATH,
        "base_image_sha256": BASE_IMAGE_SHA256,
        "candidate": PAYLOAD_DIRECTORY,
        "candidate_dtb_sha256": receipt["candidate_dtb_sha256"],
        "disabled_node": "/mmc@ff380000",
        "format_version": 1,
        "kernel_release": "6.12.99-r46h-mainline-v0.15-gaming-product",
        "post_power_on_delay_ms": POWER_SETTLE_MS,
        "source_git_commit": receipt["source_git_commit"],
        "system_node": "/mmc@ff370000",
    }
    for key, value in expected_payload_receipt.items():
        if payload_receipt.get(key) != value:
            raise BuildError(f"payload receipt {key} mismatch")
    require_toolchain()
    rebuilt = apply_overlay_binary(
        read_base_dtb(), files["r46h-v17-mmc-power-settle.dtbo"]
    )
    if rebuilt != files["R46H.DTB"]:
        raise BuildError("release overlay does not reproduce candidate DTB")
    return receipt


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
    stage = Path(tempfile.mkdtemp(prefix="r46h-v17-release.", dir=CACHE_PARENT))
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "validate"))
    arguments = parser.parse_args()
    try:
        if arguments.command == "build":
            destination = build()
            print(f"PASS: v0.17 power-settle candidate published at {destination}")
        else:
            receipt = validate_release(RELEASE_ROOT)
            print(
                "PASS: v0.17 power-settle candidate validated "
                f"sha256={receipt['archive_sha256']}"
            )
    except (BuildError, OSError, tarfile.TarError, json.JSONDecodeError) as error:
        print(f"error: {error}", file=os.sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
