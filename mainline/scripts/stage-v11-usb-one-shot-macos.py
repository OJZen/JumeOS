#!/usr/bin/env python3
"""Stage the immutable R46H v0.11 one-shot onto one exact FAT32 USB drive."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import subprocess
import sys
import time
import uuid


REPO = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO / "mainline/scripts/build-v11-usb-one-shot.py"
EXPECTED_WHOLE_SIZE = 62_914_560_000
EXPECTED_PARTITION_OFFSET = 1_048_576
EXPECTED_VOLUME_NAME = "R46HUSB"
EXPECTED_USB_VENDOR = 0x346D
EXPECTED_USB_PRODUCT = 0x5678
EXPECTED_USB_SERIAL = "8447981125795107445"
REJECTED_WHOLE_DEVICES = {"/dev/disk0", "/dev/disk6"}
PAYLOAD_DIRECTORY = "R46HV11"
PAYLOAD_NAMES = {
    "BOOT.INI",
    "CHARGER.KO",
    "IMAGE.GZ",
    "OBSERVER",
    "PAYLOAD.COMPLETE",
    "PAYLOAD.json",
    "R46H.DTB",
    "SHA256SUMS",
}


class StageError(RuntimeError):
    pass


@dataclass(frozen=True)
class UsbIdentity:
    device: str
    partition: str
    whole_size: int
    partition_size: int
    volume_size: int
    volume_uuid: str
    volume_name: str
    mount_point: str
    location_id: int
    usb_vendor: int
    usb_product: int
    usb_serial: str


@dataclass(frozen=True)
class HardwareIdentity:
    device: str
    whole_size: int
    location_id: int
    usb_vendor: int
    usb_product: int
    usb_serial: str


def load_builder():
    spec = importlib.util.spec_from_file_location("v11_usb_builder", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise StageError("cannot load the pinned v0.11 USB builder")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def run_bytes(command: list[str]) -> bytes:
    result = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise StageError(
            f"command failed ({result.returncode}): {' '.join(command)}: "
            f"{result.stderr.decode(errors='replace').strip()}"
        )
    return result.stdout


def require_plist(command: list[str]) -> object:
    try:
        return plistlib.loads(run_bytes(command))
    except plistlib.InvalidFileException as exc:
        raise StageError(f"invalid plist from {' '.join(command)}") from exc


def walk_usb_nodes(value: object):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_usb_nodes(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_usb_nodes(child)


def parse_hardware(
    whole: object, usb_tree: object, device: str
) -> HardwareIdentity:
    if not isinstance(whole, dict):
        raise StageError("whole-disk identity is not a dictionary")
    if device in REJECTED_WHOLE_DEVICES:
        raise StageError("refusing protected system or workspace disk")
    if not re.fullmatch(r"/dev/disk[1-9][0-9]*", device):
        raise StageError("device must be one explicit whole /dev/diskN")
    identifier = device.removeprefix("/dev/")
    whole_expected = {
        "BusProtocol": "USB",
        "Content": "FDisk_partition_scheme",
        "DeviceBlockSize": 512,
        "DeviceIdentifier": identifier,
        "DeviceNode": device,
        "Ejectable": True,
        "Internal": False,
        "IOKitSize": EXPECTED_WHOLE_SIZE,
        "ParentWholeDisk": identifier,
        "Removable": True,
        "Size": EXPECTED_WHOLE_SIZE,
        "VirtualOrPhysical": "Physical",
        "WholeDisk": True,
        "Writable": True,
        "WritableMedia": True,
    }
    for key, expected in whole_expected.items():
        if whole.get(key) != expected:
            raise StageError(f"whole-disk identity mismatch: {key}")
    device_tree_path = whole.get("DeviceTreePath")
    if not isinstance(device_tree_path, str):
        raise StageError("whole disk has no device-tree path")
    location_match = re.search(r"@([0-9A-Fa-f]{8})$", device_tree_path)
    if location_match is None:
        raise StageError("cannot derive USB location from whole disk")
    location_id = int(location_match.group(1), 16)
    matches = [
        node
        for node in walk_usb_nodes(usb_tree)
        if node.get("idVendor") == EXPECTED_USB_VENDOR
        and node.get("idProduct") == EXPECTED_USB_PRODUCT
        and node.get("kUSBSerialNumberString") == EXPECTED_USB_SERIAL
        and node.get("locationID") == location_id
    ]
    if len(matches) != 1:
        raise StageError("exact USB VID/PID/serial/location match is not unique")
    return HardwareIdentity(
        device=device,
        whole_size=EXPECTED_WHOLE_SIZE,
        location_id=location_id,
        usb_vendor=EXPECTED_USB_VENDOR,
        usb_product=EXPECTED_USB_PRODUCT,
        usb_serial=EXPECTED_USB_SERIAL,
    )


def parse_identity(
    whole: object,
    partition: object,
    usb_tree: object,
    device: str,
    volume: Path,
) -> UsbIdentity:
    hardware = parse_hardware(whole, usb_tree, device)
    if not isinstance(partition, dict):
        raise StageError("partition identity is not a dictionary")
    identifier = device.removeprefix("/dev/")
    partition_identifier = f"{identifier}s1"
    partition_expected = {
        "BusProtocol": "USB",
        "DeviceBlockSize": 512,
        "DeviceIdentifier": partition_identifier,
        "DeviceNode": f"/dev/{partition_identifier}",
        "Ejectable": True,
        "FilesystemType": "msdos",
        "Internal": False,
        "ParentWholeDisk": identifier,
        "PartitionMapPartition": True,
        "PartitionMapPartitionOffset": EXPECTED_PARTITION_OFFSET,
        "Removable": True,
        "VolumeName": EXPECTED_VOLUME_NAME,
        "WholeDisk": False,
        "Writable": True,
        "WritableMedia": True,
        "WritableVolume": True,
    }
    for key, expected in partition_expected.items():
        if partition.get(key) != expected:
            raise StageError(f"partition identity mismatch: {key}")
    if partition.get("Content") not in {"DOS_FAT_32", "Windows_FAT_32"}:
        raise StageError("partition is not FAT32")
    partition_size = partition.get("IOKitSize")
    total_size = partition.get("TotalSize")
    volume_size = partition.get("VolumeSize")
    volume_uuid = partition.get("VolumeUUID")
    if (
        not isinstance(partition_size, int)
        or partition_size != EXPECTED_WHOLE_SIZE - EXPECTED_PARTITION_OFFSET
        or not isinstance(total_size, int)
        or not isinstance(volume_size, int)
        or total_size != volume_size
        or total_size < 62_000_000_000
        or total_size > partition_size
        or not isinstance(volume_uuid, str)
        or re.fullmatch(
            r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}",
            volume_uuid,
        )
        is None
    ):
        raise StageError("FAT32 partition geometry or UUID mismatch")
    mount_point = partition.get("MountPoint")
    if not isinstance(mount_point, str) or Path(mount_point) != volume:
        raise StageError("partition mount point mismatch")
    metadata = volume.lstat()
    if (
        volume.is_symlink()
        or not stat.S_ISDIR(metadata.st_mode)
        or not os.path.ismount(volume)
        or volume.resolve() != volume
    ):
        raise StageError("unsafe USB volume mount path")
    return UsbIdentity(
        device=device,
        partition=f"/dev/{partition_identifier}",
        whole_size=EXPECTED_WHOLE_SIZE,
        partition_size=partition_size,
        volume_size=volume_size,
        volume_uuid=volume_uuid,
        volume_name=EXPECTED_VOLUME_NAME,
        mount_point=str(volume),
        location_id=hardware.location_id,
        usb_vendor=EXPECTED_USB_VENDOR,
        usb_product=EXPECTED_USB_PRODUCT,
        usb_serial=EXPECTED_USB_SERIAL,
    )


def query_identity(device: str, volume: Path) -> UsbIdentity:
    identifier = device.removeprefix("/dev/")
    return parse_identity(
        require_plist(["/usr/sbin/diskutil", "info", "-plist", device]),
        require_plist(
            ["/usr/sbin/diskutil", "info", "-plist", f"/dev/{identifier}s1"]
        ),
        require_plist(["/usr/sbin/ioreg", "-a", "-l", "-p", "IOUSB"]),
        device,
        volume,
    )


def query_hardware(device: str) -> HardwareIdentity:
    return parse_hardware(
        require_plist(["/usr/sbin/diskutil", "info", "-plist", device]),
        require_plist(["/usr/sbin/ioreg", "-a", "-l", "-p", "IOUSB"]),
        device,
    )


def require_flat_payload(source: Path) -> dict[str, dict[str, object]]:
    metadata = source.lstat()
    if source.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        raise StageError("unsafe source payload directory")
    members = {entry.name: entry for entry in source.iterdir()}
    if set(members) != PAYLOAD_NAMES:
        raise StageError("source payload member set mismatch")
    result: dict[str, dict[str, object]] = {}
    for name, candidate in sorted(members.items()):
        item = candidate.lstat()
        if (
            candidate.is_symlink()
            or not stat.S_ISREG(item.st_mode)
            or item.st_nlink != 1
            or item.st_dev != metadata.st_dev
        ):
            raise StageError(f"unsafe source payload member: {name}")
        result[name] = {"sha256": sha256_file(candidate), "size": item.st_size}
    return result


def copy_one(source: Path, destination: Path) -> None:
    source_fd = os.open(source, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    destination_fd = -1
    try:
        before = os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise StageError(f"unsafe source while copying: {source.name}")
        destination_fd = os.open(
            destination,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        copied = 0
        while block := os.read(source_fd, 1024 * 1024):
            view = memoryview(block)
            while view:
                written = os.write(destination_fd, view)
                if written <= 0:
                    raise StageError(f"short write while copying: {source.name}")
                copied += written
                view = view[written:]
        os.fsync(destination_fd)
        after = os.fstat(source_fd)
        if (
            copied != before.st_size
            or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        ):
            raise StageError(f"source changed while copying: {source.name}")
    finally:
        if destination_fd >= 0:
            os.close(destination_fd)
        os.close(source_fd)


def require_regular_on_device(candidate: Path, device: int, label: str) -> os.stat_result:
    metadata = candidate.lstat()
    if (
        candidate.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_dev != device
    ):
        raise StageError(f"unsafe {label}: {candidate.name}")
    return metadata


def remove_appledouble(directory: Path, names: set[str], device: int) -> None:
    present: list[Path] = []
    for name in sorted(names):
        candidate = directory / name
        try:
            require_regular_on_device(candidate, device, "AppleDouble member")
        except FileNotFoundError:
            continue
        present.append(candidate)
    for candidate in present:
        candidate.unlink()


def copy_and_verify_payload(
    source: Path, volume: Path
) -> dict[str, dict[str, object]]:
    expected = require_flat_payload(source)
    destination = volume / PAYLOAD_DIRECTORY
    try:
        os.mkdir(destination, 0o700)
    except FileExistsError:
        pass
    directory_identity = destination.lstat()
    volume_identity = volume.lstat()
    if (
        destination.is_symlink()
        or not stat.S_ISDIR(directory_identity.st_mode)
        or directory_identity.st_dev != volume_identity.st_dev
    ):
        raise StageError("new USB payload path is not a directory")

    appledouble_names = {f"._{name}" for name in PAYLOAD_NAMES}
    members = {entry.name: entry for entry in destination.iterdir()}
    unknown = set(members) - PAYLOAD_NAMES - appledouble_names
    if unknown:
        raise StageError("USB payload directory contains unknown members")
    for name in sorted(set(members) & PAYLOAD_NAMES):
        candidate = members[name]
        metadata = require_regular_on_device(
            candidate, directory_identity.st_dev, "existing payload member"
        )
        if (
            metadata.st_size != expected[name]["size"]
            or sha256_file(candidate) != expected[name]["sha256"]
        ):
            raise StageError(f"existing USB payload member differs: {name}")
    for name in sorted(set(members) & appledouble_names):
        require_regular_on_device(
            members[name], directory_identity.st_dev, "AppleDouble member"
        )

    for name in sorted(expected):
        if name not in members:
            copy_one(source / name, destination / name)
    remove_appledouble(destination, appledouble_names, directory_identity.st_dev)
    directory_fd = os.open(destination, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    observed = require_flat_payload(destination)
    after = destination.lstat()
    if (
        observed != expected
        or (after.st_dev, after.st_ino)
        != (directory_identity.st_dev, directory_identity.st_ino)
    ):
        raise StageError("USB payload readback mismatch")
    remove_appledouble(
        volume,
        {f"._{PAYLOAD_DIRECTORY}"},
        volume_identity.st_dev,
    )
    volume_fd = os.open(volume, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(volume_fd)
    finally:
        os.close(volume_fd)
    return expected


def eject(device: str) -> None:
    run_bytes(["/usr/sbin/diskutil", "eject", device])
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        raw_device = Path(f"/dev/r{device.removeprefix('/dev/')}")
        if not Path(device).exists() and not raw_device.exists():
            return
        time.sleep(0.1)
    raise StageError("USB device nodes remain after eject")


def publish_receipt(
    builder,
    generation: Path,
    identity: UsbIdentity,
    files: dict[str, dict[str, object]],
) -> Path:
    receipt_root = builder.RELEASE_ROOT / "usb-stages"
    receipt_root.mkdir(mode=0o700, exist_ok=True)
    receipt = {
        "ejected": True,
        "files": files,
        "format_version": 1,
        "generation": generation.name,
        "identity": asdict(identity),
        "payload_sha256sums_sha256": sha256_file(
            generation / PAYLOAD_DIRECTORY / "SHA256SUMS"
        ),
        "source_git_commit": builder.git_bytes(
            ["rev-parse", "--verify", "HEAD^{commit}"]
        ).decode().strip(),
        "status": "pass",
    }
    destination = receipt_root / (
        f"stage-{generation.name}-{uuid.uuid4().hex}.json"
    )
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(canonical_json(receipt))
        handle.flush()
        os.fsync(handle.fileno())
    directory_fd = os.open(receipt_root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
    return destination


def command_stage(device: str, confirm_device: str, volume: Path) -> None:
    if device != confirm_device:
        raise StageError("device confirmation mismatch")
    builder = load_builder()
    commit, _, _, _ = builder.require_clean_source()
    current = builder.exact_json(builder.RELEASE_ROOT / "CURRENT")
    generation_name = current.get("generation")
    if not builder.valid_generation_name(generation_name):
        raise StageError("current USB generation name is malformed")
    generation = builder.RELEASE_ROOT / "builds" / generation_name
    builder.validate_generation(generation, commit)
    source = generation / PAYLOAD_DIRECTORY
    source_files = require_flat_payload(source)
    before = query_identity(device, volume)
    copied = copy_and_verify_payload(source, volume)
    if copied != source_files:
        raise StageError("USB payload source changed during staging")
    after = query_identity(device, volume)
    if after != before:
        raise StageError("USB identity changed during staging")
    eject(device)
    receipt = publish_receipt(builder, generation, after, copied)
    print("PASS: exact v0.11 one-shot payload copied, read back, and ejected")
    print(f"GENERATION={generation.name}")
    print(f"USB_SERIAL={after.usb_serial}")
    print(f"RECEIPT={receipt}")


def command_prepare(device: str, confirm_device: str) -> None:
    if device != confirm_device:
        raise StageError("device confirmation mismatch")
    before = query_hardware(device)
    run_bytes(
        [
            "/usr/sbin/diskutil",
            "eraseDisk",
            "FAT32",
            EXPECTED_VOLUME_NAME,
            "MBRFormat",
            device,
        ]
    )
    volume = Path(f"/Volumes/{EXPECTED_VOLUME_NAME}")
    after = query_identity(device, volume)
    if (
        after.device != before.device
        or after.whole_size != before.whole_size
        or after.location_id != before.location_id
        or after.usb_vendor != before.usb_vendor
        or after.usb_product != before.usb_product
        or after.usb_serial != before.usb_serial
    ):
        raise StageError("USB hardware identity changed during format")
    print("PASS: exact disposable USB drive formatted as one FAT32 partition")
    print(f"DEVICE={device}")
    print(f"VOLUME={volume}")
    print(f"VOLUME_UUID={after.volume_uuid}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--device", required=True)
    prepare.add_argument("--confirm-device", required=True)
    stage = subparsers.add_parser("stage")
    stage.add_argument("--device", required=True)
    stage.add_argument("--confirm-device", required=True)
    stage.add_argument("--volume", type=Path, required=True)
    return result


def main() -> int:
    try:
        if sys.platform != "darwin":
            raise StageError("this staging tool requires macOS")
        if sys.version_info < (3, 10):
            raise StageError("Python 3.10 or newer is required")
        arguments = parser().parse_args()
        if arguments.command == "prepare":
            command_prepare(arguments.device, arguments.confirm_device)
        else:
            command_stage(arguments.device, arguments.confirm_device, arguments.volume)
        return 0
    except (StageError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 65


if __name__ == "__main__":
    raise SystemExit(main())
