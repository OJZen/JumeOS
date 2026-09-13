#!/usr/bin/env python3
"""Tests for the offline EASYROMS p3 recovery image and raw verifier."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import types
import unittest


REPO = Path(__file__).resolve().parents[2]
OUT_CACHE = REPO / "mainline/out/.cache"
VERIFIER_PATH = REPO / "mainline/scripts/verify-exfat-image.py"
BUILDER_PATH = REPO / "mainline/scripts/build-easyroms-p3-recovery.py"
PLAN_PATH = REPO / "mainline/scripts/generate-easyroms-p3-write-plan.py"
CONFIG_PATH = REPO / "mainline/p3-recovery/PAYLOAD-SOURCES.json"
CONTAINER_SCRIPT = REPO / "mainline/p3-recovery/build-image-in-container.sh"
FAST_CONFIG_PATH = REPO / "mainline/p3-recovery/PAYLOAD-SOURCES-62534975488.json"
FAST_CONTAINER_SCRIPT = REPO / "mainline/p3-recovery/build-image-62534975488-in-container.sh"
DOCKER_IMAGE = "arkos4clone/r46h-debian13-p2-mvp:v0.1"
GUID = "E1F5295C-4B12-A54A-ACB7-317194240001"
SERIAL = "52343648"
SOURCE_DATE_EPOCH = 1_785_369_600


def load_module(path: Path, name: str) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    sys.modules[name] = module
    exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
    return module


VERIFY = load_module(VERIFIER_PATH, "r46h_exfat_raw_verifier_test")
BUILD = load_module(BUILDER_PATH, "r46h_p3_recovery_builder_test")
PLAN = load_module(PLAN_PATH, "r46h_p3_recovery_plan_test")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class ManifestAndBuilderTests(unittest.TestCase):
    def test_payload_configuration_is_exact(self) -> None:
        value, digest = BUILD.load_config(CONFIG_PATH)
        self.assertEqual(value["artifact_id"], BUILD.ARTIFACT_ID)
        self.assertEqual(value["image_size"], 20_868_328_960)
        self.assertEqual(value["volume_serial"], SERIAL)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertEqual(
            [item["destination"] for item in value["payloads"]],
            [
                "r46h-v0.8-bootloader-handoff",
                "r46h-v0.9-adc-joystick-fix",
                "r46h-v0.10-adc-full-range",
            ],
        )

    def test_fast_card_variant_has_exact_geometry_and_does_not_drift_compact_defaults(self) -> None:
        compact = (
            BUILD.ARTIFACT_ID,
            BUILD.IMAGE_NAME,
            BUILD.PROFILE_ID,
            BUILD.IMAGE_SIZE,
            BUILD.VOLUME_GUID,
        )
        BUILD.select_variant("fast-card-62534975488")
        try:
            value, digest = BUILD.load_config(FAST_CONFIG_PATH)
            self.assertEqual(value["artifact_id"], "r46h-easyroms-p3-62534975488-v1")
            self.assertEqual(value["image_size"], 51_683_880_448)
            self.assertEqual(value["fat_length_sectors"], 12_321)
            self.assertEqual(value["cluster_heap_offset_sectors"], 16_384)
            self.assertEqual(value["cluster_count"], 1_577_010)
            self.assertEqual(value["root_directory_cluster"], 10)
            self.assertEqual(value["volume_guid"], "62534975-4880-4A4A-ACB7-625349754881")
            self.assertRegex(digest, r"^[0-9a-f]{64}$")
            script = FAST_CONTAINER_SCRIPT.read_text(encoding="utf-8")
            self.assertIn("readonly IMAGE_SIZE=51683880448", script)
            self.assertNotIn("/dev/disk", script)
        finally:
            (
                BUILD.ARTIFACT_ID,
                BUILD.IMAGE_NAME,
                BUILD.PROFILE_ID,
                BUILD.IMAGE_SIZE,
                BUILD.VOLUME_GUID,
            ) = compact
            BUILD.FAT_LENGTH_SECTORS = 4_975
            BUILD.CLUSTER_HEAP_OFFSET_SECTORS = 8_192
            BUILD.CLUSTER_COUNT = 636_722
            BUILD.ROOT_DIRECTORY_CLUSTER = 6
            BUILD.VOLUME_SERIAL = SERIAL
            BUILD.CONFIG_RELPATH = "mainline/p3-recovery/PAYLOAD-SOURCES.json"
            BUILD.CONTAINER_RELPATH = "mainline/p3-recovery/build-image-in-container.sh"
            BUILD.TRACKED_INPUTS = {
                BUILD.CONFIG_RELPATH: "100644",
                BUILD.CONTAINER_RELPATH: "100755",
                BUILD.VERIFIER_RELPATH: "100755",
                BUILD.BUILDER_RELPATH: "100755",
                BUILD.PLAN_RELPATH: "100755",
            }

    def test_expected_manifest_is_sorted_and_exact(self) -> None:
        bindings = [
            {
                "destination": "z",
                "files": [{"name": "b", "size": 2, "sha256": "b" * 64}],
            },
            {
                "destination": "a",
                "files": [{"name": "c", "size": 3, "sha256": "c" * 64}],
            },
        ]
        value = BUILD.expected_manifest(bindings)
        self.assertEqual(value["directories"], ["a", "z"])
        self.assertEqual([item["path"] for item in value["files"]], ["a/c", "z/b"])
        self.assertEqual(value["volume_guid"], GUID)
        self.assertEqual(value["volume_serial"], SERIAL)

    def test_manifest_parser_rejects_duplicates_and_noncanonical_json(self) -> None:
        OUT_CACHE.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".r46h-p3-test.", dir=OUT_CACHE) as raw:
            root = Path(raw)
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"format_version":1,"format_version":1}\n', encoding="utf-8")
            with self.assertRaises(VERIFY.VerifyError):
                VERIFY.load_expected(duplicate)
            noncanonical = root / "noncanonical.json"
            noncanonical.write_text("{}\n\n", encoding="utf-8")
            with self.assertRaises(VERIFY.VerifyError):
                VERIFY.load_expected(noncanonical)

    def test_cluster_claims_are_fail_closed(self) -> None:
        verifier = object.__new__(VERIFY.ExfatVerifier)
        verifier.claims = {}
        verifier._claim((4, 5), "first")
        with self.assertRaisesRegex(VERIFY.VerifyError, "shared"):
            verifier._claim((5, 6), "second")

    def test_timestamp_normalization_is_fixed_utc(self) -> None:
        # 2026-07-30 00:00:00 UTC => time=0, date=0x5cfe.
        self.assertEqual(
            VERIFY.ExfatVerifier._fixed_exfat_timestamp(SOURCE_DATE_EPOCH),
            b"\x00\x00\xfe\x5c",
        )

    def test_atomic_publication_is_no_replace_and_inode_preserving(self) -> None:
        OUT_CACHE.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".r46h-p3-publish.", dir=OUT_CACHE) as raw:
            root = Path(raw)
            source = root / ".stage"
            source.mkdir()
            identity = source.stat().st_ino
            BUILD.rename_noreplace(root, source.name, "published")
            self.assertFalse(source.exists())
            self.assertEqual((root / "published").stat().st_ino, identity)
            competitor = root / "competitor"
            competitor.mkdir()
            another = root / ".another"
            another.mkdir()
            with self.assertRaisesRegex(BUILD.BuildError, "already exists"):
                BUILD.rename_noreplace(root, another.name, competitor.name)
            self.assertTrue(another.is_dir())
            self.assertTrue(competitor.is_dir())

    def test_container_builder_pins_serial_and_never_mentions_disk_nodes(self) -> None:
        source = CONTAINER_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("tune.exfat -I \"$VOLUME_SERIAL\" \"$IMAGE\"", source)
        self.assertIn("--find --show \"$IMAGE\"", source)
        self.assertNotRegex(source, r"/dev/(?:sd|disk|mmcblk|nvme)")

    def test_write_plan_is_easyroms_only_and_binds_target_baseline(self) -> None:
        plan = json.loads(
            PLAN.build_write_plan(
                "/dev/disk6",
                Path("/absolute/recovery.img"),
                "a" * 64,
                "b" * 64,
            )
        )
        self.assertEqual(set(plan), {"device", "format_version", "operations", "profile_id"})
        self.assertEqual(len(plan["operations"]), 1)
        operation = plan["operations"][0]
        self.assertEqual(operation["partition"], "easyroms")
        self.assertEqual(operation["source_size"], 20_868_328_960)
        self.assertEqual(operation["target_sha256_before"], "b" * 64)
        for invalid in ("/dev/disk0", "/dev/rdisk12", "/dev/disk", "disk12"):
            with self.subTest(invalid=invalid), self.assertRaises(PLAN.PlanError):
                PLAN.build_write_plan(invalid, Path("/x"), "a" * 64, "b" * 64)

    def test_fast_card_write_plan_uses_exact_variant(self) -> None:
        PLAN.select_variant("fast-card-62534975488")
        try:
            plan = json.loads(
                PLAN.build_write_plan(
                    "/dev/disk14",
                    Path("/absolute/easyroms-p3-62534975488-v1.img"),
                    "f" * 64,
                    "a" * 64,
                )
            )
            operation = plan["operations"][0]
            self.assertEqual(plan["profile_id"], "hl-r46h-v22-g92-62534975488-v1")
            self.assertEqual(operation["id"], "write-easyroms-p3-62534975488-v1")
            self.assertEqual(operation["partition"], "easyroms")
            self.assertEqual(operation["source_size"], 51_683_880_448)
            self.assertEqual(PLAN.FAT_LENGTH_SECTORS, 12_321)
            self.assertEqual(PLAN.CLUSTER_HEAP_OFFSET_SECTORS, 16_384)
            self.assertEqual(PLAN.CLUSTER_COUNT, 1_577_010)
            self.assertEqual(PLAN.ROOT_DIRECTORY_CLUSTER, 10)
            self.assertEqual(PLAN.VOLUME_GUID, "62534975-4880-4A4A-ACB7-625349754881")
            self.assertIn("easyroms-p3-62534975488-v1.img", PLAN.EXPECTED_ARTIFACT_FILES)
            self.assertEqual(
                PLAN.PINNED_IMAGE_SHA256,
                "fe0ee7764f2e2e1f4b8451183f8cadc26e3a876847eb1bfa0569198438501fac",
            )
        finally:
            PLAN.select_variant("compact")
        self.assertEqual(PLAN.IMAGE_SIZE, 20_868_328_960)
        self.assertEqual(PLAN.OPERATION_ID, "write-easyroms-p3-recovery-v1")

    def test_artifact_loader_checks_all_raw_safety_receipts(self) -> None:
        OUT_CACHE.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".r46h-p3-artifact.", dir=OUT_CACHE) as raw:
            root = Path(raw)
            original_size = PLAN.IMAGE_SIZE
            original_git = PLAN.subprocess_run_git
            PLAN.IMAGE_SIZE = 1024 * 1024
            try:
                head = subprocess.run(
                    ["git", "-C", str(REPO), "rev-parse", "HEAD"],
                    stdout=subprocess.PIPE,
                    check=True,
                    text=True,
                ).stdout.strip()

                def clean_git_fixture(
                    _repo_root: Path, arguments: list[str], *, raw_result: bool = False
                ) -> str | bytes:
                    if arguments == ["rev-parse", "HEAD"]:
                        return head
                    if arguments in (["diff", "--quiet"], ["diff", "--cached", "--quiet"]):
                        return b"" if raw_result else ""
                    raise AssertionError(arguments)

                PLAN.subprocess_run_git = clean_git_fixture
                image = root / PLAN.IMAGE_NAME
                with image.open("wb") as handle:
                    handle.truncate(PLAN.IMAGE_SIZE)
                image_sha = sha256(image)
                expected = root / "EXPECTED-FILES.json"
                expected_value = {
                    "cluster_count": 636722,
                    "cluster_heap_offset_sectors": 8192,
                    "cluster_size": 32768,
                    "directories": sorted(
                        [
                            "r46h-v0.8-bootloader-handoff",
                            "r46h-v0.9-adc-joystick-fix",
                            "r46h-v0.10-adc-full-range",
                        ]
                    ),
                    "files": [
                        {
                            "path": "r46h-v0.8-bootloader-handoff/f",
                            "sha256": "9" * 64,
                            "size": 1,
                        }
                    ],
                    "format_version": 1,
                    "fat_length_sectors": 4975,
                    "fat_offset_sectors": 2048,
                    "image_size": PLAN.IMAGE_SIZE,
                    "root_directory_cluster": 6,
                    "sector_size": 512,
                    "volume_guid": GUID,
                    "volume_label": "EASYROMS",
                    "volume_serial": SERIAL,
                }
                expected.write_bytes(PLAN.canonical_json(expected_value))
                source_bindings = root / "SOURCE-BINDINGS.json"
                config_payloads = json.loads(CONFIG_PATH.read_bytes())["payloads"]
                binding_payloads = []
                for index, config_payload in enumerate(config_payloads):
                    binding_payloads.append(
                        {
                            **{
                                key: config_payload[key]
                                for key in PLAN.BINDING_KEYS - {"files"}
                            },
                            "files": (
                                [{"name": "f", "sha256": "9" * 64, "size": 1}]
                                if index == 0
                                else []
                            ),
                        }
                    )
                source_bindings.write_bytes(
                    PLAN.canonical_json(
                        {
                            "format_version": 1,
                            "payloads": binding_payloads,
                        }
                    )
                )
                container_log = root / "CONTAINER-BUILD.log"
                container_log.write_bytes(b"pass\n")
                fsck_log = root / "POST-NORMALIZE-FSCK.log"
                fsck_log.write_bytes(b"clean\n")
                raw_report_value = {
                    "allocation_bitmap_exact": True,
                    "deleted_entries": 0,
                    "directories": expected_value["directories"],
                    "expected_manifest_sha256": sha256(expected),
                    "files": [
                        {
                            "path": "r46h-v0.8-bootloader-handoff/f",
                            "sha256": "9" * 64,
                            "size": 1,
                        }
                    ],
                    "overlapping_clusters": 0,
                    "result": "pass",
                    "timestamps_normalized_to_epoch": SOURCE_DATE_EPOCH,
                    "volume_guid": GUID,
                    "volume_label": "EASYROMS",
                    "volume_serial": SERIAL,
                }
                raw_report = root / "RAW-VERIFY.json"
                raw_report.write_bytes(PLAN.canonical_json(raw_report_value))
                status = {
                    "allocation_bitmap_exact": True,
                    "artifact_id": PLAN.ARTIFACT_ID,
                    "block_devices_opened": 0,
                    "builder_image": DOCKER_IMAGE,
                    "builder_image_id": PLAN.BUILDER_IMAGE_ID,
                    "cluster_size": 32768,
                    "container_loop_devices_after": 0,
                    "deleted_entries": 0,
                    "directory_count": 3,
                    "expected_manifest_sha256": sha256(expected),
                    "file_count": 1,
                    "filesystem": "exfat",
                    "format_version": 1,
                    "image_name": PLAN.IMAGE_NAME,
                    "image_sha256": image_sha,
                    "image_size": PLAN.IMAGE_SIZE,
                    "macos_fskit_used": False,
                    "overlapping_clusters": 0,
                    "payload_config_sha256": sha256(CONFIG_PATH),
                    "physical_devices_accessed": 0,
                    "post_normalize_fsck_read_only_passed": True,
                    "profile_id": PLAN.PROFILE_ID,
                    "raw_verification_sha256": sha256(raw_report),
                    "raw_verification_twice_passed": True,
                    "sector_size": 512,
                    "source_date_epoch": SOURCE_DATE_EPOCH,
                    "source_git_archive_sha256": "f" * 64,
                    "source_git_commit": head,
                    "state": "BUILD_COMPLETE",
                    "volume_guid": GUID,
                    "volume_label": "EASYROMS",
                    "volume_serial": SERIAL,
                }
                status_path = root / "BUILD-STATUS.json"
                status_path.write_bytes(PLAN.canonical_json(status))
                evidence = sorted(PLAN.EXPECTED_ARTIFACT_FILES - {"SHA256SUMS"})
                (root / "SHA256SUMS").write_text(
                    "".join(f"{sha256(root / name)}  {name}\n" for name in evidence),
                    encoding="utf-8",
                )
                loaded, loaded_sha = PLAN.load_artifact(REPO, root)
                self.assertEqual(loaded, image.resolve())
                self.assertEqual(loaded_sha, image_sha)
                raw_report_value["allocation_bitmap_exact"] = False
                raw_report.write_bytes(PLAN.canonical_json(raw_report_value))
                with self.assertRaisesRegex(PLAN.PlanError, "RAW-VERIFY"):
                    PLAN.load_artifact(REPO, root)
            finally:
                PLAN.IMAGE_SIZE = original_size
                PLAN.subprocess_run_git = original_git


@unittest.skipUnless(
    os.environ.get("R46H_RUN_P3_SOURCE_INTEGRATION") == "1",
    "set R46H_RUN_P3_SOURCE_INTEGRATION=1 for retained-payload freeze integration",
)
class RetainedPayloadIntegrationTests(unittest.TestCase):
    def test_all_three_pinned_payloads_freeze_and_revalidate(self) -> None:
        value, _ = BUILD.load_config(CONFIG_PATH)
        OUT_CACHE.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".r46h-p3-source.", dir=OUT_CACHE) as raw:
            root = Path(raw)
            bindings = [BUILD.freeze_payload(REPO, spec, root) for spec in value["payloads"]]
            self.assertEqual([item["destination"] for item in bindings], [
                "r46h-v0.8-bootloader-handoff",
                "r46h-v0.9-adc-joystick-fix",
                "r46h-v0.10-adc-full-range",
            ])
            self.assertEqual(sum(len(item["files"]) for item in bindings), 31)
            for spec, binding in zip(value["payloads"], bindings):
                BUILD.revalidate_live_payload(REPO, spec, binding)


@unittest.skipUnless(
    os.environ.get("R46H_RUN_P3_RECOVERY_INTEGRATION") == "1",
    "set R46H_RUN_P3_RECOVERY_INTEGRATION=1 for privileged Docker integration",
)
class RawExfatIntegrationTests(unittest.TestCase):
    image_size = 64 * 1024 * 1024

    def setUp(self) -> None:
        OUT_CACHE.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix=".r46h-p3-raw.", dir=OUT_CACHE)
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _build_image(self, name: str) -> Path:
        image = self.root / name
        descriptor = os.open(image, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.ftruncate(descriptor, self.image_size)
        finally:
            os.close(descriptor)
        script = r'''set -Eeuo pipefail
image=/work/''' + name + r'''
mkfs.exfat -q -L EASYROMS -U ''' + GUID + r''' -s 512 -c 32K -b 1M "$image"
tune.exfat -I 0x52343648 "$image"
loop=$(losetup --find --show "$image")
mounted=0
cleanup() {
  set +e
  if [ "$mounted" = 1 ]; then umount /mnt/p; fi
  losetup -d "$loop" >/dev/null 2>&1 || true
}
trap cleanup EXIT
mkdir -p /mnt/p
mount -t exfat -o rw,nosuid,nodev,noexec "$loop" /mnt/p
mounted=1
mkdir /mnt/p/alpha
cp /source/PAYLOAD-SOURCES.json /mnt/p/alpha/PAYLOAD-SOURCES.json
cp /source/build-image-in-container.sh /mnt/p/alpha/build-image-in-container.sh
sync -f /mnt/p
umount /mnt/p
mounted=0
losetup -d "$loop"
trap - EXIT
fsck.exfat -n "$image"
'''
        command = [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--privileged",
            "--mount",
            f"type=bind,src={self.root},dst=/work",
            "--mount",
            f"type=bind,src={CONTAINER_SCRIPT.parent},dst=/source,readonly",
            DOCKER_IMAGE,
            "/bin/bash",
            "-c",
            script,
        ]
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        self.assertEqual(result.returncode, 0, result.stdout.decode(errors="replace"))
        return image

    @staticmethod
    def _geometry(image: Path) -> dict[str, int]:
        with image.open("rb") as handle:
            boot = handle.read(512)
        sector = 1 << boot[108]
        return {
            "sector_size": sector,
            "cluster_size": sector * (1 << boot[109]),
            "fat_offset_sectors": struct.unpack_from("<I", boot, 80)[0],
            "fat_length_sectors": struct.unpack_from("<I", boot, 84)[0],
            "cluster_heap_offset_sectors": struct.unpack_from("<I", boot, 88)[0],
            "cluster_count": struct.unpack_from("<I", boot, 92)[0],
            "root_directory_cluster": struct.unpack_from("<I", boot, 96)[0],
        }

    def _manifest(self, image: Path) -> Path:
        value = {
            **self._geometry(image),
            "directories": ["alpha"],
            "files": [
                {
                    "path": "alpha/PAYLOAD-SOURCES.json",
                    "size": CONFIG_PATH.stat().st_size,
                    "sha256": sha256(CONFIG_PATH),
                },
                {
                    "path": "alpha/build-image-in-container.sh",
                    "size": CONTAINER_SCRIPT.stat().st_size,
                    "sha256": sha256(CONTAINER_SCRIPT),
                },
            ],
            "format_version": 1,
            "image_size": self.image_size,
            "volume_guid": GUID,
            "volume_label": "EASYROMS",
            "volume_serial": SERIAL,
        }
        path = self.root / "EXPECTED.json"
        path.write_bytes(VERIFY.canonical_json(value))
        return path

    @staticmethod
    def _clone(source: Path, destination: Path) -> None:
        shutil.copyfile(source, destination)
        destination.chmod(0o600)

    def test_raw_verifier_accepts_clean_image_and_rejects_three_corruptions(self) -> None:
        image = self._build_image("clean.img")
        manifest = self._manifest(image)
        normalized = VERIFY.normalize_image_timestamps(image, manifest, SOURCE_DATE_EPOCH)
        self.assertEqual(normalized, 3)
        report, _ = VERIFY.verify_image(image, manifest)
        self.assertTrue(report["allocation_bitmap_exact"])
        self.assertEqual(report["overlapping_clusters"], 0)
        self.assertEqual(report["deleted_entries"], 0)

        geometry = self._geometry(image)
        cluster_heap = geometry["cluster_heap_offset_sectors"] * geometry["sector_size"]
        cluster_size = geometry["cluster_size"]

        data_corrupt = self.root / "data-corrupt.img"
        self._clone(image, data_corrupt)
        first_cluster = report["files"][0]["first_cluster"]
        descriptor = os.open(data_corrupt, os.O_RDWR)
        try:
            os.pwrite(
                descriptor,
                b"\x00",
                cluster_heap + (first_cluster - 2) * cluster_size,
            )
        finally:
            os.close(descriptor)
        with self.assertRaisesRegex(VERIFY.VerifyError, "raw file content mismatch"):
            VERIFY.verify_image(data_corrupt, manifest)

        root_offset = cluster_heap + (geometry["root_directory_cluster"] - 2) * cluster_size
        with image.open("rb") as handle:
            handle.seek(root_offset)
            root_data = handle.read(cluster_size)
        primary_offset = next(
            index for index in range(0, len(root_data), 32) if root_data[index] == 0x85
        )
        directory_corrupt = self.root / "directory-corrupt.img"
        self._clone(image, directory_corrupt)
        descriptor = os.open(directory_corrupt, os.O_RDWR)
        try:
            os.pwrite(descriptor, b"\x00\x00", root_offset + primary_offset + 2)
        finally:
            os.close(descriptor)
        with self.assertRaisesRegex(VERIFY.VerifyError, "checksum mismatch"):
            VERIFY.verify_image(directory_corrupt, manifest)

        bitmap_corrupt = self.root / "bitmap-corrupt.img"
        self._clone(image, bitmap_corrupt)
        verifier_expected, _ = VERIFY.load_expected(manifest)
        descriptor = os.open(image, os.O_RDONLY)
        try:
            verifier = VERIFY.ExfatVerifier(descriptor, verifier_expected)
            verifier.verify()
            bitmap_first = verifier.bitmap[0]
        finally:
            os.close(descriptor)
        descriptor = os.open(bitmap_corrupt, os.O_RDWR)
        try:
            os.pwrite(
                descriptor,
                b"\x00",
                cluster_heap + (bitmap_first - 2) * cluster_size,
            )
        finally:
            os.close(descriptor)
        with self.assertRaisesRegex(VERIFY.VerifyError, "allocation bitmap"):
            VERIFY.verify_image(bitmap_corrupt, manifest)


if __name__ == "__main__":
    unittest.main()
