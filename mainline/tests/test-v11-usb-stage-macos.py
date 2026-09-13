#!/usr/bin/env python3
"""Host tests for exact v0.11 USB staging on macOS."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
STAGER_PATH = REPO / "mainline/scripts/stage-v11-usb-one-shot-macos.py"


def load_stager():
    spec = importlib.util.spec_from_file_location("v11_usb_stager", STAGER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


STAGER = load_stager()


def valid_plists(device: str, volume: Path):
    identifier = device.removeprefix("/dev/")
    whole = {
        "BusProtocol": "USB",
        "Content": "FDisk_partition_scheme",
        "DeviceBlockSize": 512,
        "DeviceIdentifier": identifier,
        "DeviceNode": device,
        "DeviceTreePath": "IODeviceTree:/test/usb-port@02110000",
        "Ejectable": True,
        "Internal": False,
        "IOKitSize": STAGER.EXPECTED_WHOLE_SIZE,
        "ParentWholeDisk": identifier,
        "Removable": True,
        "Size": STAGER.EXPECTED_WHOLE_SIZE,
        "VirtualOrPhysical": "Physical",
        "WholeDisk": True,
        "Writable": True,
        "WritableMedia": True,
    }
    partition = {
        "BusProtocol": "USB",
        "Content": "DOS_FAT_32",
        "DeviceBlockSize": 512,
        "DeviceIdentifier": f"{identifier}s1",
        "DeviceNode": f"/dev/{identifier}s1",
        "Ejectable": True,
        "FilesystemType": "msdos",
        "Internal": False,
        "IOKitSize": STAGER.EXPECTED_WHOLE_SIZE - STAGER.EXPECTED_PARTITION_OFFSET,
        "MountPoint": str(volume),
        "ParentWholeDisk": identifier,
        "PartitionMapPartition": True,
        "PartitionMapPartitionOffset": STAGER.EXPECTED_PARTITION_OFFSET,
        "Removable": True,
        "Size": STAGER.EXPECTED_WHOLE_SIZE - STAGER.EXPECTED_PARTITION_OFFSET,
        "TotalSize": 62_898_143_232,
        "VolumeName": STAGER.EXPECTED_VOLUME_NAME,
        "VolumeSize": 62_898_143_232,
        "VolumeUUID": "1C2F8BA6-3185-3369-89FE-AC0C2612A01E",
        "WholeDisk": False,
        "Writable": True,
        "WritableMedia": True,
        "WritableVolume": True,
    }
    usb = {
        "IORegistryEntryChildren": [
            {
                "idVendor": STAGER.EXPECTED_USB_VENDOR,
                "idProduct": STAGER.EXPECTED_USB_PRODUCT,
                "kUSBSerialNumberString": STAGER.EXPECTED_USB_SERIAL,
                "locationID": 0x02110000,
            }
        ]
    }
    return whole, partition, usb


class V11UsbStageTests(unittest.TestCase):
    def test_identity_parser_accepts_only_the_exact_drive(self) -> None:
        cache = REPO / "mainline/out/.cache"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            volume = Path(temporary)
            whole, partition, usb = valid_plists("/dev/disk12", volume)
            with mock.patch.object(STAGER.os.path, "ismount", return_value=True):
                identity = STAGER.parse_identity(
                    whole, partition, usb, "/dev/disk12", volume
                )
        self.assertEqual(identity.usb_serial, STAGER.EXPECTED_USB_SERIAL)
        self.assertEqual(identity.whole_size, STAGER.EXPECTED_WHOLE_SIZE)
        self.assertEqual(identity.usb_vendor, 0x346D)

    def test_identity_parser_rejects_every_critical_mismatch(self) -> None:
        cache = REPO / "mainline/out/.cache"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            volume = Path(temporary)
            with mock.patch.object(STAGER.os.path, "ismount", return_value=True):
                for target, key, value in (
                    ("whole", "Size", 1),
                    ("whole", "Internal", True),
                    ("partition", "Content", "Apple_APFS"),
                    ("partition", "VolumeName", "OTHER"),
                    ("partition", "VolumeUUID", "not-a-uuid"),
                    ("usb", "kUSBSerialNumberString", "wrong"),
                ):
                    whole, partition, usb = valid_plists("/dev/disk12", volume)
                    if target == "whole":
                        whole[key] = value
                    elif target == "partition":
                        partition[key] = value
                    else:
                        usb["IORegistryEntryChildren"][0][key] = value
                    with self.subTest(target=target, key=key):
                        with self.assertRaises(STAGER.StageError):
                            STAGER.parse_identity(
                                whole, partition, usb, "/dev/disk12", volume
                            )

    def test_protected_devices_are_rejected_before_usb_matching(self) -> None:
        whole, _, usb = valid_plists("/dev/disk12", Path("/Volumes/R46HUSB"))
        for device in sorted(STAGER.REJECTED_WHOLE_DEVICES):
            identifier = device.removeprefix("/dev/")
            protected = dict(whole)
            protected.update(
                {
                    "DeviceIdentifier": identifier,
                    "DeviceNode": device,
                    "ParentWholeDisk": identifier,
                }
            )
            with self.subTest(device=device):
                with self.assertRaisesRegex(STAGER.StageError, "protected"):
                    STAGER.parse_hardware(protected, usb, device)

    def test_copy_is_no_clobber_and_full_readback(self) -> None:
        cache = REPO / "mainline/out/.cache"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            root = Path(temporary)
            source = root / "source"
            volume = root / "volume"
            source.mkdir()
            volume.mkdir()
            for name in STAGER.PAYLOAD_NAMES:
                (source / name).write_bytes((name + "\n").encode())
            expected = STAGER.require_flat_payload(source)
            self.assertEqual(STAGER.copy_and_verify_payload(source, volume), expected)
            before = STAGER.require_flat_payload(
                volume / STAGER.PAYLOAD_DIRECTORY
            )
            self.assertEqual(STAGER.copy_and_verify_payload(source, volume), expected)
            self.assertEqual(
                STAGER.require_flat_payload(volume / STAGER.PAYLOAD_DIRECTORY),
                before,
            )

    def test_exact_appledouble_is_removed_during_idempotent_recovery(self) -> None:
        cache = REPO / "mainline/out/.cache"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            root = Path(temporary)
            source = root / "source"
            volume = root / "volume"
            destination = volume / STAGER.PAYLOAD_DIRECTORY
            source.mkdir()
            destination.mkdir(parents=True)
            for name in STAGER.PAYLOAD_NAMES:
                contents = (name + "\n").encode()
                (source / name).write_bytes(contents)
                (destination / name).write_bytes(contents)
                (destination / f"._{name}").write_bytes(b"AppleDouble")
            (volume / f"._{STAGER.PAYLOAD_DIRECTORY}").write_bytes(b"metadata")
            expected = STAGER.require_flat_payload(source)
            self.assertEqual(
                STAGER.copy_and_verify_payload(source, volume), expected
            )
            self.assertEqual(
                {entry.name for entry in destination.iterdir()},
                STAGER.PAYLOAD_NAMES,
            )
            self.assertFalse((volume / f"._{STAGER.PAYLOAD_DIRECTORY}").exists())

    def test_recovery_refuses_unknown_or_mismatched_existing_members(self) -> None:
        cache = REPO / "mainline/out/.cache"
        cache.mkdir(parents=True, exist_ok=True)
        for failure in ("unknown", "mismatch"):
            with self.subTest(failure=failure):
                with tempfile.TemporaryDirectory(dir=cache) as temporary:
                    root = Path(temporary)
                    source = root / "source"
                    volume = root / "volume"
                    destination = volume / STAGER.PAYLOAD_DIRECTORY
                    source.mkdir()
                    destination.mkdir(parents=True)
                    for name in STAGER.PAYLOAD_NAMES:
                        (source / name).write_bytes((name + "\n").encode())
                    if failure == "unknown":
                        (destination / "unexpected").write_bytes(b"do not remove")
                    else:
                        (destination / "BOOT.INI").write_bytes(b"wrong")
                    with self.assertRaises(STAGER.StageError):
                        STAGER.copy_and_verify_payload(source, volume)
                    if failure == "unknown":
                        self.assertEqual(
                            (destination / "unexpected").read_bytes(),
                            b"do not remove",
                        )
                    else:
                        self.assertEqual(
                            (destination / "BOOT.INI").read_bytes(), b"wrong"
                        )

    def test_source_and_destination_links_are_rejected(self) -> None:
        cache = REPO / "mainline/out/.cache"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            for name in STAGER.PAYLOAD_NAMES:
                (source / name).write_bytes(b"fixture")
            (source / "OBSERVER").unlink()
            (source / "OBSERVER").symlink_to("BOOT.INI")
            with self.assertRaises(STAGER.StageError):
                STAGER.require_flat_payload(source)

    def test_prepare_uses_one_exact_destructive_command(self) -> None:
        hardware = STAGER.HardwareIdentity(
            device="/dev/disk12",
            whole_size=STAGER.EXPECTED_WHOLE_SIZE,
            location_id=0x02110000,
            usb_vendor=STAGER.EXPECTED_USB_VENDOR,
            usb_product=STAGER.EXPECTED_USB_PRODUCT,
            usb_serial=STAGER.EXPECTED_USB_SERIAL,
        )
        identity = STAGER.UsbIdentity(
            device=hardware.device,
            partition="/dev/disk12s1",
            whole_size=hardware.whole_size,
            partition_size=STAGER.EXPECTED_WHOLE_SIZE
            - STAGER.EXPECTED_PARTITION_OFFSET,
            volume_size=62_898_143_232,
            volume_uuid="1C2F8BA6-3185-3369-89FE-AC0C2612A01E",
            volume_name=STAGER.EXPECTED_VOLUME_NAME,
            mount_point=f"/Volumes/{STAGER.EXPECTED_VOLUME_NAME}",
            location_id=hardware.location_id,
            usb_vendor=hardware.usb_vendor,
            usb_product=hardware.usb_product,
            usb_serial=hardware.usb_serial,
        )
        with (
            mock.patch.object(STAGER, "query_hardware", return_value=hardware),
            mock.patch.object(STAGER, "query_identity", return_value=identity),
            mock.patch.object(STAGER, "run_bytes", return_value=b"") as runner,
            mock.patch("builtins.print"),
        ):
            STAGER.command_prepare("/dev/disk12", "/dev/disk12")
        runner.assert_called_once_with(
            [
                "/usr/sbin/diskutil",
                "eraseDisk",
                "FAT32",
                STAGER.EXPECTED_VOLUME_NAME,
                "MBRFormat",
                "/dev/disk12",
            ]
        )

    def test_prepare_confirmation_mismatch_does_not_inspect_or_erase(self) -> None:
        with (
            mock.patch.object(STAGER, "query_hardware") as query,
            mock.patch.object(STAGER, "run_bytes") as runner,
        ):
            with self.assertRaisesRegex(STAGER.StageError, "confirmation"):
                STAGER.command_prepare("/dev/disk12", "/dev/disk13")
        query.assert_not_called()
        runner.assert_not_called()

    def test_stager_has_one_format_path_and_no_recursive_replace(self) -> None:
        source = STAGER_PATH.read_text()
        self.assertEqual(source.count('"eraseDisk"'), 1)
        for forbidden in (
            "partitionDisk",
            "newfs_",
            "shutil.copytree",
            "os.replace(",
            "rm -rf",
        ):
            self.assertNotIn(forbidden, source)
        self.assertIn("os.O_EXCL", source)
        self.assertIn("diskutil\", \"eject", source)


if __name__ == "__main__":
    unittest.main()
