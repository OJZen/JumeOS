#!/usr/bin/env python3
"""Verify an exFAT image from raw allocation metadata and file content."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import sys
import uuid


SHA_RE = re.compile(r"^[0-9a-f]{64}$")
PATH_RE = re.compile(r"^[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*$")
EXPECTED_MANIFEST_KEYS = {
    "format_version",
    "image_size",
    "volume_label",
    "volume_guid",
    "sector_size",
    "volume_serial",
    "cluster_size",
    "fat_offset_sectors",
    "fat_length_sectors",
    "cluster_heap_offset_sectors",
    "cluster_count",
    "root_directory_cluster",
    "directories",
    "files",
}
EXPECTED_FILE_KEYS = {"path", "size", "sha256"}
MAX_EXPECTED_MANIFEST_BYTES = 16 * 1024 * 1024


class VerifyError(RuntimeError):
    pass


@dataclass(frozen=True)
class Geometry:
    sector_size: int
    cluster_size: int
    volume_length_sectors: int
    fat_offset_sectors: int
    fat_length_sectors: int
    cluster_heap_offset_sectors: int
    cluster_count: int
    root_directory_cluster: int
    volume_serial: int
    volume_flags: int
    percent_in_use: int


@dataclass(frozen=True)
class ExpectedFile:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ExpectedManifest:
    image_size: int
    volume_label: str
    volume_guid: str
    volume_serial: str
    geometry: Geometry
    directories: tuple[str, ...]
    files: tuple[ExpectedFile, ...]


def require_regular(path: Path, label: str) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise VerifyError(f"missing {label}: {path}") from exc
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        raise VerifyError(f"unsafe {label}: {path}")
    return metadata


def stable_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def read_pinned_regular(path: Path, label: str, maximum_size: int) -> bytes:
    named = require_regular(path, label)
    if named.st_size <= 0 or named.st_size > maximum_size:
        raise VerifyError(f"unsafe {label} size: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if stable_identity(opened) != stable_identity(named):
            raise VerifyError(f"{label} changed before it was opened")
        output = bytearray()
        while len(output) < opened.st_size:
            block = os.read(descriptor, opened.st_size - len(output))
            if not block:
                raise VerifyError(f"short read from {label}")
            output.extend(block)
        if stable_identity(os.fstat(descriptor)) != stable_identity(opened):
            raise VerifyError(f"{label} changed while it was read")
        return bytes(output)
    finally:
        os.close(descriptor)


def reject_duplicate_json_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise VerifyError(f"duplicate expected-manifest key: {key}")
        result[key] = value
    return result


def load_expected(path: Path) -> tuple[ExpectedManifest, str]:
    raw = read_pinned_regular(
        path, "expected manifest", MAX_EXPECTED_MANIFEST_BYTES
    )
    digest = hashlib.sha256(raw).hexdigest()
    try:
        value = json.loads(raw, object_pairs_hook=reject_duplicate_json_pairs)
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise VerifyError("expected manifest is not canonical JSON") from exc
    if not isinstance(value, dict) or set(value) != EXPECTED_MANIFEST_KEYS:
        raise VerifyError("expected manifest contains unknown or missing keys")
    if raw != canonical_json(value):
        raise VerifyError("expected manifest is not canonical JSON")
    if value.get("format_version") != 1:
        raise VerifyError("unsupported expected manifest format")
    integers = (
        "image_size",
        "sector_size",
        "cluster_size",
        "fat_offset_sectors",
        "fat_length_sectors",
        "cluster_heap_offset_sectors",
        "cluster_count",
        "root_directory_cluster",
    )
    if any(not isinstance(value.get(key), int) or value[key] <= 0 for key in integers):
        raise VerifyError("expected manifest geometry is invalid")
    label = value.get("volume_label")
    guid = value.get("volume_guid")
    serial = value.get("volume_serial")
    if not isinstance(label, str) or not label or len(label) > 11:
        raise VerifyError("expected volume label is invalid")
    try:
        normalized_guid = str(uuid.UUID(str(guid))).upper()
    except (ValueError, AttributeError) as exc:
        raise VerifyError("expected volume GUID is invalid") from exc
    if guid != normalized_guid:
        raise VerifyError("expected volume GUID is not canonical uppercase text")
    if not isinstance(serial, str) or re.fullmatch(r"[0-9a-f]{8}", serial) is None:
        raise VerifyError("expected volume serial is not canonical lowercase hex")

    directories_raw = value.get("directories")
    files_raw = value.get("files")
    if not isinstance(directories_raw, list) or not isinstance(files_raw, list):
        raise VerifyError("expected file tree is malformed")
    if directories_raw != sorted(set(directories_raw)):
        raise VerifyError("expected directories are duplicated or unsorted")
    directories: list[str] = []
    for directory in directories_raw:
        if not isinstance(directory, str) or PATH_RE.fullmatch(directory) is None:
            raise VerifyError("expected directory path is unsafe")
        parent = directory.rpartition("/")[0]
        if parent and parent not in directories:
            raise VerifyError(f"expected directory parent is absent: {directory}")
        directories.append(directory)
    files: list[ExpectedFile] = []
    paths: set[str] = set(directories)
    for item in files_raw:
        if not isinstance(item, dict) or set(item) != EXPECTED_FILE_KEYS:
            raise VerifyError("expected file entry contains unknown or missing keys")
        file_path = item.get("path")
        file_size = item.get("size")
        file_sha = item.get("sha256")
        if (
            not isinstance(file_path, str)
            or PATH_RE.fullmatch(file_path) is None
            or not isinstance(file_size, int)
            or file_size < 0
            or not isinstance(file_sha, str)
            or SHA_RE.fullmatch(file_sha) is None
            or file_path in paths
        ):
            raise VerifyError("expected file identity is invalid or duplicated")
        parent = file_path.rpartition("/")[0]
        if parent not in directories:
            raise VerifyError(f"expected file parent is absent: {file_path}")
        paths.add(file_path)
        files.append(ExpectedFile(file_path, file_size, file_sha))
    if [item.path for item in files] != sorted(item.path for item in files):
        raise VerifyError("expected files are unsorted")

    geometry = Geometry(
        sector_size=value["sector_size"],
        cluster_size=value["cluster_size"],
        volume_length_sectors=value["image_size"] // value["sector_size"],
        fat_offset_sectors=value["fat_offset_sectors"],
        fat_length_sectors=value["fat_length_sectors"],
        cluster_heap_offset_sectors=value["cluster_heap_offset_sectors"],
        cluster_count=value["cluster_count"],
        root_directory_cluster=value["root_directory_cluster"],
        volume_serial=0,
        volume_flags=0,
        percent_in_use=0,
    )
    if value["image_size"] % value["sector_size"] != 0:
        raise VerifyError("expected image size is not sector aligned")
    if (
        value["sector_size"] not in {512, 1024, 2048, 4096}
        or value["cluster_size"] < value["sector_size"]
        or value["cluster_size"] % value["sector_size"] != 0
        or value["cluster_size"] & (value["cluster_size"] - 1)
        or value["fat_offset_sectors"] < 24
        or value["cluster_heap_offset_sectors"]
        <= value["fat_offset_sectors"] + value["fat_length_sectors"]
    ):
        raise VerifyError("expected exFAT geometry is not structurally valid")
    return (
        ExpectedManifest(
            image_size=value["image_size"],
            volume_label=label,
            volume_guid=normalized_guid,
            volume_serial=serial,
            geometry=geometry,
            directories=tuple(directories),
            files=tuple(files),
        ),
        digest,
    )


class ExfatVerifier:
    def __init__(self, descriptor: int, expected: ExpectedManifest) -> None:
        self.fd = descriptor
        self.expected = expected
        self.geometry = self._read_geometry()
        self.fat = self._read_exact(
            self.geometry.fat_offset_sectors * self.geometry.sector_size,
            self.geometry.fat_length_sectors * self.geometry.sector_size,
        )
        self.claims: dict[int, str] = {}
        self.actual_files: dict[str, tuple[int, str, tuple[int, ...]]] = {}
        self.actual_directories: set[str] = set()
        self.volume_label: str | None = None
        self.volume_guid: str | None = None
        self.bitmap: tuple[int, int] | None = None
        self.upcase: tuple[int, int, int] | None = None
        self.deleted_entries = 0
        self.fat_chained_clusters: set[int] = set()

    def _read_exact(self, offset: int, length: int) -> bytes:
        if offset < 0 or length < 0 or offset + length > self.expected.image_size:
            raise VerifyError("raw read exceeds the image")
        output = bytearray()
        while len(output) < length:
            block = os.pread(self.fd, length - len(output), offset + len(output))
            if not block:
                raise VerifyError("short raw image read")
            output.extend(block)
        return bytes(output)

    def _write_exact(self, offset: int, data: bytes) -> None:
        if offset < 0 or offset + len(data) > self.expected.image_size:
            raise VerifyError("raw write exceeds the image")
        written = 0
        while written < len(data):
            count = os.pwrite(self.fd, data[written:], offset + written)
            if count <= 0:
                raise VerifyError("short raw image write")
            written += count

    @staticmethod
    def _rotate_add16(checksum: int, value: int) -> int:
        return (((checksum & 1) << 15) | (checksum >> 1)) + value & 0xFFFF

    @staticmethod
    def _rotate_add32(checksum: int, value: int) -> int:
        return (((checksum & 1) << 31) | (checksum >> 1)) + value & 0xFFFFFFFF

    def _verify_boot_region(self, start_sector: int) -> bytes:
        sector_size = self.geometry.sector_size
        region = self._read_exact(start_sector * sector_size, 12 * sector_size)
        for sector_index in range(9):
            sector = region[
                sector_index * sector_size : (sector_index + 1) * sector_size
            ]
            if sector[-2:] != b"\x55\xaa":
                raise VerifyError("exFAT boot-region sector signature mismatch")
        if any(region[9 * sector_size : 11 * sector_size]):
            raise VerifyError("exFAT OEM-parameter or reserved boot sector is nonzero")
        checksum = 0
        for index, value in enumerate(region[: 11 * sector_size]):
            if index in {106, 107, 112}:
                continue
            checksum = self._rotate_add32(checksum, value)
        checksum_sector = region[11 * sector_size :]
        expected = struct.pack("<I", checksum) * (sector_size // 4)
        if checksum_sector != expected:
            raise VerifyError("exFAT boot-region checksum mismatch")
        return region

    def _read_geometry(self) -> Geometry:
        boot = self._read_exact(0, 512)
        if boot[3:11] != b"EXFAT   ":
            raise VerifyError("image does not contain an exFAT boot sector")
        sector_size = 1 << boot[108]
        cluster_size = sector_size * (1 << boot[109])
        number_of_fats = boot[110]
        revision = struct.unpack_from("<H", boot, 104)[0]
        geometry = Geometry(
            sector_size=sector_size,
            cluster_size=cluster_size,
            volume_length_sectors=struct.unpack_from("<Q", boot, 72)[0],
            fat_offset_sectors=struct.unpack_from("<I", boot, 80)[0],
            fat_length_sectors=struct.unpack_from("<I", boot, 84)[0],
            cluster_heap_offset_sectors=struct.unpack_from("<I", boot, 88)[0],
            cluster_count=struct.unpack_from("<I", boot, 92)[0],
            root_directory_cluster=struct.unpack_from("<I", boot, 96)[0],
            volume_serial=struct.unpack_from("<I", boot, 100)[0],
            volume_flags=struct.unpack_from("<H", boot, 106)[0],
            percent_in_use=boot[112],
        )
        expected = self.expected.geometry
        comparable = (
            geometry.sector_size,
            geometry.cluster_size,
            geometry.volume_length_sectors,
            geometry.fat_offset_sectors,
            geometry.fat_length_sectors,
            geometry.cluster_heap_offset_sectors,
            geometry.cluster_count,
            geometry.root_directory_cluster,
        )
        expected_values = (
            expected.sector_size,
            expected.cluster_size,
            expected.volume_length_sectors,
            expected.fat_offset_sectors,
            expected.fat_length_sectors,
            expected.cluster_heap_offset_sectors,
            expected.cluster_count,
            expected.root_directory_cluster,
        )
        if comparable != expected_values:
            raise VerifyError("exFAT geometry does not match the expected manifest")
        if revision != 0x0100 or number_of_fats != 1:
            raise VerifyError("unsupported exFAT revision or FAT count")
        if f"{geometry.volume_serial:08x}" != self.expected.volume_serial:
            raise VerifyError("exFAT volume serial does not match the expected manifest")
        if boot[0:3] != b"\xeb\x76\x90" or any(boot[11:64]):
            raise VerifyError("exFAT main boot-sector fixed fields mismatch")
        heap_end = (
            geometry.cluster_heap_offset_sectors * sector_size
            + geometry.cluster_count * cluster_size
        )
        if heap_end > self.expected.image_size:
            raise VerifyError("exFAT cluster heap exceeds the image")
        self.geometry = geometry
        main_boot = self._verify_boot_region(0)
        backup_boot = self._verify_boot_region(12)
        if main_boot != backup_boot:
            raise VerifyError("main and backup exFAT boot regions differ")
        reserved_start = 24 * sector_size
        reserved_length = geometry.fat_offset_sectors * sector_size - reserved_start
        if reserved_length and any(self._read_exact(reserved_start, reserved_length)):
            raise VerifyError("nonzero data exists in the pre-FAT reserved region")
        fat_end = (
            geometry.fat_offset_sectors + geometry.fat_length_sectors
        ) * sector_size
        heap_start = geometry.cluster_heap_offset_sectors * sector_size
        if heap_start > fat_end and any(self._read_exact(fat_end, heap_start - fat_end)):
            raise VerifyError("nonzero data exists between the FAT and cluster heap")
        return geometry

    def _fat_value(self, cluster: int) -> int:
        offset = cluster * 4
        if cluster < 0 or offset + 4 > len(self.fat):
            raise VerifyError("FAT cluster index is out of range")
        return struct.unpack_from("<I", self.fat, offset)[0]

    def _cluster_offset(self, cluster: int) -> int:
        if cluster < 2 or cluster > self.geometry.cluster_count + 1:
            raise VerifyError("cluster index is outside the heap")
        return (
            self.geometry.cluster_heap_offset_sectors * self.geometry.sector_size
            + (cluster - 2) * self.geometry.cluster_size
        )

    def _fat_chain(self, first: int, count: int | None = None) -> tuple[int, ...]:
        if first < 2 or first > self.geometry.cluster_count + 1:
            raise VerifyError("invalid first cluster")
        result: list[int] = []
        seen: set[int] = set()
        current = first
        limit = count if count is not None else self.geometry.cluster_count
        while True:
            if current in seen:
                raise VerifyError("FAT chain contains a loop")
            if current < 2 or current > self.geometry.cluster_count + 1:
                raise VerifyError("FAT chain leaves the cluster heap")
            seen.add(current)
            result.append(current)
            value = self._fat_value(current)
            if value == 0xFFFFFFFF:
                break
            if value in {0, 1, 0xFFFFFFF7} or value >= 0xFFFFFFF8:
                raise VerifyError("FAT chain contains an invalid terminator")
            current = value
            if len(result) >= limit and value != 0xFFFFFFFF:
                raise VerifyError("FAT chain is longer than expected")
        if count is not None and len(result) != count:
            raise VerifyError("FAT chain length does not match data length")
        self.fat_chained_clusters.update(result)
        return tuple(result)

    def _clusters_for_data(
        self, first: int, length: int, no_fat_chain: bool
    ) -> tuple[int, ...]:
        if length == 0:
            if first != 0:
                raise VerifyError("empty stream has a nonzero first cluster")
            return ()
        count = math.ceil(length / self.geometry.cluster_size)
        if no_fat_chain:
            last = first + count - 1
            if first < 2 or last > self.geometry.cluster_count + 1:
                raise VerifyError("contiguous stream exceeds the cluster heap")
            return tuple(range(first, last + 1))
        return self._fat_chain(first, count)

    def _claim(self, clusters: tuple[int, ...], owner: str) -> None:
        for cluster in clusters:
            previous = self.claims.get(cluster)
            if previous is not None:
                raise VerifyError(
                    f"cluster {cluster} is shared by {previous} and {owner}"
                )
            self.claims[cluster] = owner

    def _stream_bytes(self, clusters: tuple[int, ...], length: int) -> bytes:
        output = bytearray()
        remaining = length
        for cluster in clusters:
            take = min(remaining, self.geometry.cluster_size)
            output.extend(self._read_exact(self._cluster_offset(cluster), take))
            remaining -= take
            if remaining == 0:
                break
        if remaining != 0:
            raise VerifyError("cluster stream is shorter than its data length")
        return bytes(output)

    def _write_stream(self, clusters: tuple[int, ...], data: bytes) -> None:
        if len(data) != len(clusters) * self.geometry.cluster_size:
            raise VerifyError("directory rewrite size does not match its cluster chain")
        offset = 0
        for cluster in clusters:
            block = data[offset : offset + self.geometry.cluster_size]
            self._write_exact(self._cluster_offset(cluster), block)
            offset += len(block)

    def _hash_stream(self, clusters: tuple[int, ...], length: int) -> str:
        digest = hashlib.sha256()
        remaining = length
        for cluster in clusters:
            take = min(remaining, self.geometry.cluster_size)
            digest.update(self._read_exact(self._cluster_offset(cluster), take))
            remaining -= take
            if remaining == 0:
                break
        if remaining != 0:
            raise VerifyError("file stream is shorter than its data length")
        return digest.hexdigest()

    def _entry_set_checksum(self, entries: list[bytes]) -> int:
        checksum = 0
        for index, value in enumerate(b"".join(entries)):
            if index in {2, 3}:
                continue
            checksum = self._rotate_add16(checksum, value)
        return checksum

    @staticmethod
    def _fixed_exfat_timestamp(source_date_epoch: int) -> bytes:
        try:
            moment = datetime.fromtimestamp(source_date_epoch, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise VerifyError("timestamp-normalization epoch is invalid") from exc
        if not 1980 <= moment.year <= 2107 or moment.microsecond != 0:
            raise VerifyError("timestamp-normalization epoch is outside the exFAT range")
        fat_date = ((moment.year - 1980) << 9) | (moment.month << 5) | moment.day
        fat_time = (moment.hour << 11) | (moment.minute << 5) | (moment.second // 2)
        return struct.pack("<HH", fat_time, fat_date)

    def normalize_file_set_timestamps(self, source_date_epoch: int) -> int:
        """Normalize every file/directory primary entry in a regular image."""

        timestamp = self._fixed_exfat_timestamp(source_date_epoch)
        root_clusters = self._fat_chain(self.geometry.root_directory_cluster)
        pending: list[tuple[tuple[int, ...], str]] = [(root_clusters, "")]
        seen_directories: set[int] = set()
        normalized = 0
        while pending:
            clusters, parent = pending.pop()
            first_cluster = clusters[0]
            if first_cluster in seen_directories:
                raise VerifyError("directory graph contains a repeated cluster chain")
            seen_directories.add(first_cluster)
            data = bytearray(
                self._stream_bytes(
                    clusters, len(clusters) * self.geometry.cluster_size
                )
            )
            entries = [
                bytes(data[index : index + 32])
                for index in range(0, len(data), 32)
            ]
            index = 0
            changed = False
            while index < len(entries):
                entry = entries[index]
                entry_type = entry[0]
                if entry_type == 0:
                    break
                if not (entry_type & 0x80):
                    raise VerifyError("cannot normalize a directory with stale entries")
                if entry_type != 0x85:
                    index += 1
                    continue
                secondary_count = entry[1]
                if secondary_count < 2 or index + secondary_count >= len(entries):
                    raise VerifyError("file entry set exceeds its directory")
                group = entries[index : index + secondary_count + 1]
                if struct.unpack_from("<H", group[0], 2)[0] != self._entry_set_checksum(group):
                    raise VerifyError("cannot normalize a corrupt file entry set")
                stream_entries = [item for item in group[1:] if item[0] == 0xC0]
                if len(stream_entries) != 1:
                    raise VerifyError("cannot normalize an invalid stream entry set")
                stream = stream_entries[0]
                name_entries = [item for item in group[1:] if item[0] == 0xC1]
                name_length = stream[3]
                name_bytes = b"".join(item[2:32] for item in name_entries)
                try:
                    name = name_bytes[: name_length * 2].decode("utf-16le")
                except UnicodeDecodeError as exc:
                    raise VerifyError("cannot normalize an invalid UTF-16 file name") from exc
                path = f"{parent}/{name}" if parent else name
                if PATH_RE.fullmatch(path) is None:
                    raise VerifyError("cannot normalize an unsafe file path")

                primary = bytearray(group[0])
                primary[8:12] = timestamp
                primary[12:16] = timestamp
                primary[16:20] = timestamp
                primary[20:22] = b"\x00\x00"
                primary[22:25] = b"\x80\x80\x80"
                normalized_group = [bytes(primary), *group[1:]]
                checksum = self._entry_set_checksum(normalized_group)
                primary[2:4] = struct.pack("<H", checksum)
                normalized_group[0] = bytes(primary)
                for group_index, normalized_entry in enumerate(normalized_group):
                    entry_offset = (index + group_index) * 32
                    data[entry_offset : entry_offset + 32] = normalized_entry
                    entries[index + group_index] = normalized_entry
                changed = True
                normalized += 1

                attributes = struct.unpack_from("<H", primary, 4)[0]
                if attributes & 0x10:
                    flags = stream[1]
                    first = struct.unpack_from("<I", stream, 20)[0]
                    length = struct.unpack_from("<Q", stream, 24)[0]
                    child_clusters = self._clusters_for_data(
                        first, length, bool(flags & 0x02)
                    )
                    pending.append((child_clusters, path))
                index += secondary_count + 1
            if changed:
                self._write_stream(clusters, bytes(data))
        os.fsync(self.fd)
        return normalized

    def _parse_file_set(self, entries: list[bytes], parent: str) -> None:
        primary = entries[0]
        if primary[1] != len(entries) - 1:
            raise VerifyError("file entry secondary count mismatch")
        if struct.unpack_from("<H", primary, 2)[0] != self._entry_set_checksum(entries):
            raise VerifyError("file entry-set checksum mismatch")
        stream_entries = [entry for entry in entries[1:] if entry[0] == 0xC0]
        name_entries = [entry for entry in entries[1:] if entry[0] == 0xC1]
        if len(stream_entries) != 1 or len(name_entries) != len(entries) - 2:
            raise VerifyError("file entry-set secondary types are invalid")
        stream = stream_entries[0]
        flags = stream[1]
        if flags not in {0x01, 0x03}:
            raise VerifyError("unsupported stream allocation flags")
        name_length = stream[3]
        code_units = b"".join(entry[2:32] for entry in name_entries)
        try:
            decoded = code_units[: name_length * 2].decode("utf-16le")
        except UnicodeDecodeError as exc:
            raise VerifyError("file name is not valid UTF-16LE") from exc
        if any(code_units[name_length * 2 :]):
            raise VerifyError("file name entry has nonzero trailing characters")
        if not decoded or "/" in decoded or "\x00" in decoded:
            raise VerifyError("file name is unsafe")
        path = f"{parent}/{decoded}" if parent else decoded
        if PATH_RE.fullmatch(path) is None:
            raise VerifyError(f"file path is outside the supported contract: {path}")
        attributes = struct.unpack_from("<H", primary, 4)[0]
        valid_length = struct.unpack_from("<Q", stream, 8)[0]
        first_cluster = struct.unpack_from("<I", stream, 20)[0]
        data_length = struct.unpack_from("<Q", stream, 24)[0]
        if valid_length > data_length:
            raise VerifyError("valid data length exceeds stream data length")
        clusters = self._clusters_for_data(first_cluster, data_length, bool(flags & 0x02))
        if attributes & 0x10:
            if attributes != 0x10 or valid_length != data_length:
                raise VerifyError(f"directory stream metadata is noncanonical: {path}")
            if path in self.actual_directories or path in self.actual_files:
                raise VerifyError(f"duplicate directory: {path}")
            self._claim(clusters, f"directory:{path}")
            self.actual_directories.add(path)
            self._parse_directory(clusters, path)
        else:
            if attributes != 0x20:
                raise VerifyError(f"file attributes are noncanonical: {path}")
            if path in self.actual_files or path in self.actual_directories:
                raise VerifyError(f"duplicate file: {path}")
            if valid_length != data_length:
                raise VerifyError(f"file has unwritten valid-data tail: {path}")
            self._claim(clusters, f"file:{path}")
            self.actual_files[path] = (
                data_length,
                self._hash_stream(clusters, data_length),
                clusters,
            )

    def _parse_directory(self, clusters: tuple[int, ...], parent: str) -> None:
        data = self._stream_bytes(clusters, len(clusters) * self.geometry.cluster_size)
        entries = [data[index : index + 32] for index in range(0, len(data), 32)]
        index = 0
        ended = False
        while index < len(entries):
            entry = entries[index]
            entry_type = entry[0]
            if entry_type == 0:
                ended = True
                if any(any(item) for item in entries[index + 1 :]):
                    raise VerifyError("directory contains nonzero data after end marker")
                break
            if not (entry_type & 0x80):
                self.deleted_entries += 1
                raise VerifyError("directory contains a deleted/stale entry")
            if entry_type == 0x85:
                secondary_count = entry[1]
                if secondary_count < 2 or index + secondary_count >= len(entries):
                    raise VerifyError("file entry set exceeds its directory")
                group = entries[index : index + secondary_count + 1]
                self._parse_file_set(group, parent)
                index += secondary_count + 1
                continue
            if parent:
                raise VerifyError("system directory entry appears outside the root")
            if entry_type == 0x83:
                count = entry[1]
                if count > 11 or any(entry[24:32]):
                    raise VerifyError("volume-label entry is malformed")
                label = entry[2 : 2 + count * 2].decode("utf-16le")
                if self.volume_label is not None:
                    raise VerifyError("duplicate volume-label entry")
                self.volume_label = label
            elif entry_type == 0xA0:
                if entry[1] != 0 or struct.unpack_from("<H", entry, 2)[0] != self._entry_set_checksum([entry]):
                    raise VerifyError("volume-GUID entry checksum mismatch")
                if self.volume_guid is not None:
                    raise VerifyError("duplicate volume-GUID entry")
                self.volume_guid = str(uuid.UUID(bytes=entry[6:22])).upper()
            elif entry_type == 0x81:
                if self.bitmap is not None or entry[1] != 0:
                    raise VerifyError("allocation-bitmap entry is invalid or duplicated")
                first = struct.unpack_from("<I", entry, 20)[0]
                length = struct.unpack_from("<Q", entry, 24)[0]
                self.bitmap = (first, length)
            elif entry_type == 0x82:
                if self.upcase is not None:
                    raise VerifyError("duplicate up-case-table entry")
                checksum = struct.unpack_from("<I", entry, 4)[0]
                first = struct.unpack_from("<I", entry, 20)[0]
                length = struct.unpack_from("<Q", entry, 24)[0]
                self.upcase = (first, length, checksum)
            else:
                raise VerifyError(f"unsupported active directory entry type: 0x{entry_type:02x}")
            index += 1
        if not ended:
            raise VerifyError("directory lacks an end marker")

    def verify(self) -> dict[str, object]:
        root_clusters = self._fat_chain(self.geometry.root_directory_cluster)
        self._claim(root_clusters, "directory:/")
        self._parse_directory(root_clusters, "")
        if self.volume_label != self.expected.volume_label:
            raise VerifyError("volume label mismatch")
        if self.volume_guid != self.expected.volume_guid:
            raise VerifyError("volume GUID mismatch")
        if self.bitmap is None or self.upcase is None:
            raise VerifyError("mandatory exFAT system file is absent")
        if self._fat_value(0) != 0xFFFFFFF8 or self._fat_value(1) != 0xFFFFFFFF:
            raise VerifyError("exFAT FAT reserved entries are malformed")

        bitmap_first, bitmap_length = self.bitmap
        expected_bitmap_length = math.ceil(self.geometry.cluster_count / 8)
        if bitmap_length != expected_bitmap_length:
            raise VerifyError("allocation-bitmap length mismatch")
        bitmap_clusters = self._fat_chain(
            bitmap_first, math.ceil(bitmap_length / self.geometry.cluster_size)
        )
        self._claim(bitmap_clusters, "system:allocation-bitmap")
        bitmap_data = self._stream_bytes(bitmap_clusters, bitmap_length)
        trailing_bitmap_bits = self.geometry.cluster_count % 8
        if trailing_bitmap_bits and bitmap_data[-1] & ~((1 << trailing_bitmap_bits) - 1):
            raise VerifyError("allocation bitmap marks clusters beyond the heap")

        upcase_first, upcase_length, upcase_expected_checksum = self.upcase
        upcase_clusters = self._fat_chain(
            upcase_first, math.ceil(upcase_length / self.geometry.cluster_size)
        )
        self._claim(upcase_clusters, "system:up-case-table")
        upcase_data = self._stream_bytes(upcase_clusters, upcase_length)
        upcase_checksum = 0
        for value in upcase_data:
            upcase_checksum = self._rotate_add32(upcase_checksum, value)
        if upcase_checksum != upcase_expected_checksum:
            raise VerifyError("up-case-table checksum mismatch")

        allocated = {
            cluster
            for cluster in range(2, self.geometry.cluster_count + 2)
            if bitmap_data[(cluster - 2) // 8] & (1 << ((cluster - 2) % 8))
        }
        if allocated != set(self.claims):
            missing = sorted(set(self.claims) - allocated)[:8]
            unexplained = sorted(allocated - set(self.claims))[:8]
            raise VerifyError(
                f"allocation bitmap does not exactly match claimed clusters; "
                f"missing={missing} unexplained={unexplained}"
            )
        for cluster in range(2, self.geometry.cluster_count + 2):
            value = self._fat_value(cluster)
            if cluster not in self.fat_chained_clusters and value != 0:
                raise VerifyError(
                    f"cluster {cluster} has stale or unexplained FAT metadata"
                )
        used_fat_bytes = (self.geometry.cluster_count + 2) * 4
        if any(self.fat[used_fat_bytes:]):
            raise VerifyError("nonzero data exists in FAT padding entries")

        heap_end = (
            self.geometry.cluster_heap_offset_sectors * self.geometry.sector_size
            + self.geometry.cluster_count * self.geometry.cluster_size
        )
        tail_length = self.expected.image_size - heap_end
        if tail_length and any(self._read_exact(heap_end, tail_length)):
            raise VerifyError("nonzero data exists after the exFAT cluster heap")

        expected_directories = set(self.expected.directories)
        if self.actual_directories != expected_directories:
            raise VerifyError(
                "raw directory set mismatch; "
                f"missing={sorted(expected_directories - self.actual_directories)} "
                f"extra={sorted(self.actual_directories - expected_directories)}"
            )
        expected_files = {item.path: item for item in self.expected.files}
        if set(self.actual_files) != set(expected_files):
            raise VerifyError(
                "raw file set mismatch; "
                f"missing={sorted(set(expected_files) - set(self.actual_files))} "
                f"extra={sorted(set(self.actual_files) - set(expected_files))}"
            )
        report_files: list[dict[str, object]] = []
        for path in sorted(expected_files):
            expected = expected_files[path]
            size, digest, clusters = self.actual_files[path]
            if size != expected.size or digest != expected.sha256:
                raise VerifyError(
                    f"raw file content mismatch: {path}; size={size} sha256={digest}"
                )
            report_files.append(
                {
                    "path": path,
                    "size": size,
                    "sha256": digest,
                    "first_cluster": clusters[0] if clusters else 0,
                    "cluster_count": len(clusters),
                }
            )
        return {
            "format_version": 1,
            "result": "pass",
            "filesystem": "exfat",
            "volume_label": self.volume_label,
            "volume_guid": self.volume_guid,
            "volume_serial": f"{self.geometry.volume_serial:08x}",
            "sector_size": self.geometry.sector_size,
            "cluster_size": self.geometry.cluster_size,
            "fat_offset_sectors": self.geometry.fat_offset_sectors,
            "fat_length_sectors": self.geometry.fat_length_sectors,
            "cluster_heap_offset_sectors": self.geometry.cluster_heap_offset_sectors,
            "cluster_count": self.geometry.cluster_count,
            "root_directory_cluster": self.geometry.root_directory_cluster,
            "allocated_cluster_count": len(allocated),
            "claimed_cluster_count": len(self.claims),
            "allocation_bitmap_exact": True,
            "overlapping_clusters": 0,
            "deleted_entries": self.deleted_entries,
            "directories": sorted(self.actual_directories),
            "files": report_files,
        }


def verify_image(image: Path, expected_path: Path) -> tuple[dict[str, object], str]:
    expected, expected_sha = load_expected(expected_path)
    metadata = require_regular(image, "exFAT image")
    if metadata.st_size != expected.image_size:
        raise VerifyError("exFAT image size mismatch")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(image, flags)
    try:
        opened = os.fstat(descriptor)
        identity = stable_identity(opened)
        if (
            identity != stable_identity(metadata)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_size != expected.image_size
        ):
            raise VerifyError("opened exFAT image identity mismatch")
        report = ExfatVerifier(descriptor, expected).verify()
        after = os.fstat(descriptor)
        if identity != stable_identity(after):
            raise VerifyError("exFAT image changed during raw verification")
    finally:
        os.close(descriptor)
    return report, expected_sha


def normalize_image_timestamps(
    image: Path, expected_path: Path, source_date_epoch: int
) -> int:
    expected, _ = load_expected(expected_path)
    metadata = require_regular(image, "exFAT image")
    if metadata.st_size != expected.image_size:
        raise VerifyError("exFAT image size mismatch")
    flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(image, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            stable_identity(opened) != stable_identity(metadata)
            or not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_size != expected.image_size
        ):
            raise VerifyError("opened exFAT image identity mismatch")
        normalized = ExfatVerifier(descriptor, expected).normalize_file_set_timestamps(
            source_date_epoch
        )
        after = os.fstat(descriptor)
        if (
            (after.st_dev, after.st_ino, after.st_size)
            != (opened.st_dev, opened.st_ino, opened.st_size)
            or not stat.S_ISREG(after.st_mode)
            or after.st_nlink != 1
        ):
            raise VerifyError("exFAT image identity changed during normalization")
        return normalized
    finally:
        os.close(descriptor)


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_new_regular(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        offset = 0
        while offset < len(data):
            written = os.write(descriptor, data[offset:])
            if written <= 0:
                raise VerifyError("short write to raw-verification report")
            offset += written
        os.fsync(descriptor)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
            raise VerifyError("unsafe raw-verification report identity")
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--expected-manifest", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--normalize-source-date-epoch", type=int)
    args = parser.parse_args()
    try:
        normalized_entries: int | None = None
        if args.normalize_source_date_epoch is not None:
            normalized_entries = normalize_image_timestamps(
                args.image,
                args.expected_manifest,
                args.normalize_source_date_epoch,
            )
        report, expected_sha = verify_image(args.image, args.expected_manifest)
        report["expected_manifest_sha256"] = expected_sha
        if normalized_entries is not None:
            report["timestamps_normalized_to_epoch"] = args.normalize_source_date_epoch
            report["normalized_entry_count"] = normalized_entries
        output = canonical_json(report)
        if args.report is not None:
            write_new_regular(args.report, output)
        sys.stdout.buffer.write(output)
    except (VerifyError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
