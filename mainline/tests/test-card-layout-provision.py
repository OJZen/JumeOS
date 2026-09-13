#!/usr/bin/env python3
import os
from pathlib import Path
import hashlib
import json
import re
import signal
import struct
import subprocess
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[2]
C_PATH = ROOT / "mainline/tools/r46h-card-agent/Sources/R46HCardLayoutProvision/main.c"
WRAPPER_PATH = ROOT / "mainline/scripts/provision-debian13-new-card-layout.sh"
AUDIT_PATH = ROOT / "mainline/scripts/audit-debian13-new-card-after-reinsert.sh"
PROBE_PATH = ROOT / "mainline/scripts/probe-debian13-new-card-snapshots.sh"
BUILD_PATH = ROOT / "mainline/scripts/build-r46h-card-layout-provision.sh"
C_SOURCE = C_PATH.read_text(encoding="utf-8")
WRAPPER = WRAPPER_PATH.read_text(encoding="utf-8")
AUDIT = AUDIT_PATH.read_text(encoding="utf-8")
PROBE = PROBE_PATH.read_text(encoding="utf-8")
BUILD = BUILD_PATH.read_text(encoding="utf-8")


def shell_function(source: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}\n",
        source,
    )
    if match is None:
        raise AssertionError(f"missing shell function: {name}")
    return match.group(0)


def embedded_root_audit_prelude(source: str) -> str:
    marker = "ROOT_AUDIT='\n"
    start = source.index(marker) + len(marker)
    end = source.index('[[ "${SUDO_UID:-}"', start)
    return source[start:end]


class CardLayoutProvisionTests(unittest.TestCase):
    def test_audit_receipt_boundary_dynamic_fixture(self) -> None:
        if os.environ.get("R46H_RUN_RECEIPT_BOUNDARY_INTEGRATION") != "1":
            self.skipTest("root receipt-boundary integration is opt-in")
        if os.geteuid() != 0:
            self.skipTest("root receipt-boundary integration requires container root")
        script = r"""
set -euo pipefail
fixture=$(mktemp -d /tmp/r46h-audit-receipt-boundary.XXXXXX)
cleanup() { rm -rf -- "$fixture"; }
trap cleanup EXIT
chmod 0711 "$fixture"

old_parent="$fixture/user-parent"
safe_parent="$fixture/root-sticky"
mkdir -m 0700 "$old_parent"
chown 12345:12345 "$old_parent"
mkdir -m 0700 "$old_parent/root-child"
chown 0:0 "$old_parent/root-child"
setpriv --reuid=12345 --regid=12345 --clear-groups \
  mv "$old_parent/root-child" "$old_parent/replaced-by-user"
test -d "$old_parent/replaced-by-user"

mkdir -m 1777 "$safe_parent"
chown 0:0 "$safe_parent"
mkdir -m 0700 "$safe_parent/root-child"
chown 0:0 "$safe_parent/root-child"
if setpriv --reuid=12345 --regid=12345 --clear-groups \
  mv "$safe_parent/root-child" "$safe_parent/replaced-by-user" 2>/dev/null; then
  exit 1
fi
printf evidence > "$safe_parent/root-child/leaf"
chmod 0600 "$safe_parent/root-child/leaf"
chown 12345:12345 "$safe_parent/root-child/leaf"
if setpriv --reuid=12345 --regid=12345 --clear-groups \
  cat "$safe_parent/root-child/leaf" >/dev/null 2>&1; then
  exit 1
fi
chown 12345:12345 "$safe_parent/root-child"
test "$(setpriv --reuid=12345 --regid=12345 --clear-groups \
  cat "$safe_parent/root-child/leaf")" = evidence
"""
        result = subprocess.run(
            ["/bin/bash", "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_wrapper_pins_compact_and_fast_card_geometry(self) -> None:
        required = (
            "WHOLE_SIZE=31719424000",
            "PREFIX_SIZE=16777216",
            "BOOT_OFFSET=16777216",
            "BOOT_SIZE=117440512",
            "ROOT_OFFSET=134217728",
            "ROOT_SIZE=10716877312",
            "EASYROMS_OFFSET=10851095040",
            "EASYROMS_SIZE=20868328960",
            "EASYROMS_DATA_SIZE=4358144",
            "EASYROMS_ZERO_SIZE=16777216",
            "WHOLE_SIZE=62534975488",
            "factory-exfat-16m",
            "factory-fat32-1m",
            "CURRENT_P1_OFFSET=1048576",
            "CURRENT_P1_SIZE=62533926912",
            "CURRENT_P1_CONTENT=Windows_FAT_32",
            "CURRENT_P1_OFFSET=16777216",
            "CURRENT_P1_SIZE=62518198272",
            "CURRENT_P1_CONTENT=Windows_NTFS",
            "EASYROMS_SIZE=51683880448",
            "EASYROMS_DATA_SIZE=$EASYROMS_SIZE",
            "EASYROMS_ZERO_SIZE=0",
            "EXPECTED_P3_SECTORS=100945079",
            '[[ "$DEVICE" != /dev/disk6 ]]',
            "PartitionMapPartitionOffset",
            '[[ ! -e "${device}s2" && ! -e "${device}s3" && ! -e "${device}s4" ]]',
        )
        for marker in required:
            self.assertIn(marker, WRAPPER)

    def test_fast_card_requires_an_exact_target_before_layout(self) -> None:
        common = (
            str(WRAPPER_PATH),
            "--device",
            "/dev/disk99",
            "--confirm-device",
            "/dev/disk99",
            "--layout",
            "fast-card-62534975488",
            "--asset-manifest-sha256",
            "1" * 64,
        )
        for extra in ((), ("--target-before-layout", "unknown")):
            result = subprocess.run(
                ("/bin/bash", *common, *extra),
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 64, result.stderr)
            self.assertIn(
                "fast-card layout requires an exact target-before layout",
                result.stderr,
            )

    def test_wrapper_pins_every_source_hash(self) -> None:
        for digest in (
            "97ede10075b3257c638a04b3044c9dda2d8dd9adc6f6fee3be7b004a31fb135e",
            "b701da77349d3514c65fcfe992434a648ca8678b661c47cb4d6bd997e103f017",
            "6a4254a8e66c110405cf068317da5922bb5ddfe2a02535d1a381fe1303876c96",
            "9e3e27c0859ba273e44a6709a3b62d8f4968dc12e061df019f137202672cf6bb",
            "3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3",
            "88c6d614984791b891e63068ea687dabe28eb80c905a2aa9c6dd34409b24f86d",
            "dba5ff14364aa32b2d5930a055182a7f49c2bea0e2a0eb8cc76d1097b37c4c3e",
        ):
            self.assertIn(digest, WRAPPER)
        self.assertIn('EASYROMS_DATA_SHA256=$(/usr/bin/awk', WRAPPER)
        self.assertIn("fast-card layout requires a pinned asset manifest", WRAPPER)

    def test_fast_card_uses_full_p3_source_without_zeroing_shortcut(self) -> None:
        zero_parser = C_SOURCE[
            C_SOURCE.index("static uint64_t parse_u64_or_zero") : C_SOURCE.index(
                "static int is_lower_hex_sha256"
            )
        ]
        self.assertIn('if (strcmp(value, "0") == 0)', zero_parser)
        self.assertIn("return parse_u64(value, label);", zero_parser)
        self.assertEqual(C_SOURCE.count("parse_u64_or_zero("), 2)
        self.assertIn(
            'parse_u64_or_zero(\n        argv[19], "EASYROMS zero size"',
            C_SOURCE,
        )
        self.assertIn("easyroms_zero_size == 0", C_SOURCE)
        self.assertIn("easyroms.hash_size == easyroms.expected_size", C_SOURCE)
        self.assertIn("if (easyroms_zero_size > 0)", C_SOURCE)
        self.assertIn("if (easyroms_zero_size > easyroms.hash_size)", C_SOURCE)
        self.assertIn("EASYROMS_DATA_SIZE=$EASYROMS_SIZE", WRAPPER)
        self.assertIn("EASYROMS_ZERO_SIZE=0", WRAPPER)
        self.assertIn('if [[ "$EASYROMS_DATA_SIZE" == "$EASYROMS_SIZE" ]]', WRAPPER)
        self.assertIn("p3_sha256=($easyroms_sha|not-verified)", AUDIT)
        self.assertIn('strcmp(easyroms_sha, "-")', C_SOURCE)
        self.assertIn('strcpy(easyroms_actual, "not-verified")', C_SOURCE)

    def test_fast_card_quick_audit_is_bounded_and_honest(self) -> None:
        self.assertIn("--audit-level full|quick", AUDIT)
        self.assertIn('[[ "$AUDIT_LEVEL" == full || "$AUDIT_LEVEL" == quick ]]', AUDIT)
        self.assertIn("RAW_BYTES_READ=12199690592", AUDIT)
        self.assertIn("RAW_BYTES_READ=125992697856", AUDIT)
        self.assertIn("EASYROMS_HEAD_SIZE=268435456", AUDIT)
        self.assertIn(
            "EASYROMS_HEAD_SHA256=d7923cfdb8b9b287a1946548699a9933234c50e89b51ac95f584f7f6ac90340e",
            AUDIT,
        )
        self.assertIn(
            "EASYROMS_QUICK_IMMUTABLE_SHA256=1b761a61e89c46c49ab78c1634c25d22112c26f990c13daedf73791ca47aba7a",
            AUDIT,
        )
        self.assertIn("p3_full_verified", AUDIT)
        self.assertIn("p3_allocated_window_verified", AUDIT)
        self.assertIn("p3_immutable_payload_verified", AUDIT)
        self.assertIn("prior_full_write_verified", AUDIT)
        self.assertIn("raw_bytes_read", AUDIT)
        self.assertIn("AUDIT_LEVEL=%s", AUDIT)
        self.assertIn("P3_FULL_VERIFIED=%s", AUDIT)
        self.assertIn("audit_level=%s p3_full_verified=%s", C_SOURCE)
        self.assertIn('"raw_bytes_read=%llu card_state=ejected', C_SOURCE)
        self.assertIn("root_size * (audit_is_quick ? 1 : 2)", C_SOURCE)
        self.assertIn("(audit_is_full ? easyroms_size * 2 : 0)", C_SOURCE)
        self.assertIn('(audit_is_quick || audit_is_compact_head)', C_SOURCE)
        self.assertIn('strcmp(easyroms_sha, "-")', C_SOURCE)
        self.assertIn("require_expected_hash(\n            target,\n            easyroms_offset", C_SOURCE)
        self.assertIn("require_quick_immutable_hash(", C_SOURCE)
        self.assertIn("#define QUICK_EXFAT_FAT_PREFIX_SIZE 17840ULL", C_SOURCE)
        self.assertNotEqual(17840 % 512, 0)
        self.assertIn("uint32_t block_size,\n    const struct hash_segment *segments", C_SOURCE)
        self.assertIn(
            "uint64_t aligned_offset = absolute_offset - (absolute_offset % block_size)",
            C_SOURCE,
        )
        self.assertIn("size_t aligned_request = leading + desired", C_SOURCE)
        self.assertIn("buffer,\n                aligned_request,\n                (off_t)aligned_offset", C_SOURCE)
        self.assertIn(
            "CC_SHA256_Update(&context, buffer + leading, (CC_LONG)desired)",
            C_SOURCE,
        )
        self.assertIn("short aligned read while hashing segments", C_SOURCE)
        self.assertIn("p3_quick_immutable_sha256=%s", C_SOURCE)
        self.assertIn("R46H_MEDIA_AUDIT stage=%s range=easyroms-immutable", C_SOURCE)

    def test_fast_card_quick_allocation_proof_covers_the_window(self) -> None:
        artifact = ROOT / "mainline/out/r46h-p3-recovery-images/r46h-easyroms-p3-62534975488-v1"
        raw_path = artifact / "RAW-VERIFY.json"
        status_path = artifact / "BUILD-STATUS.json"
        if not raw_path.exists() or not status_path.exists():
            self.skipTest("canonical fast-card p3 evidence is absent")
        raw_bytes = raw_path.read_bytes()
        status = json.loads(status_path.read_bytes())
        raw = json.loads(raw_bytes)
        self.assertEqual(
            hashlib.sha256(raw_bytes).hexdigest(),
            "560de14babd243bbb981dca5b5a697660c895200be5f633a67d33d66ee398915",
        )
        self.assertEqual(status["raw_verification_sha256"], hashlib.sha256(raw_bytes).hexdigest())
        self.assertTrue(raw["allocation_bitmap_exact"])
        self.assertEqual(raw["allocated_cluster_count"], raw["claimed_cluster_count"])
        self.assertEqual(raw["overlapping_clusters"], 0)
        self.assertEqual(raw["deleted_entries"], 0)
        image = ROOT / "mainline/out/r46h-fast-card-62534975488-v1/03-easyroms-p3.img"
        if not image.exists():
            self.skipTest("canonical fast-card p3 source image is absent")
        with image.open("rb", buffering=0) as handle:
            boot = handle.read(512)
            sector_size = 1 << boot[108]
            cluster_size = sector_size << boot[109]
            cluster_heap = struct.unpack_from("<I", boot, 88)[0] * sector_size
            root_cluster = struct.unpack_from("<I", boot, 96)[0]
            handle.seek(cluster_heap + (root_cluster - 2) * cluster_size)
            root = handle.read(cluster_size)
            bitmap_entries = [
                root[index : index + 32]
                for index in range(0, len(root), 32)
                if root[index] == 0x81
            ]
            self.assertEqual(len(bitmap_entries), 1)
            bitmap_first = struct.unpack_from("<I", bitmap_entries[0], 20)[0]
            bitmap_length = struct.unpack_from("<Q", bitmap_entries[0], 24)[0]
            handle.seek(cluster_heap + (bitmap_first - 2) * cluster_size)
            bitmap = handle.read(bitmap_length)
        allocated = [
            index + 2
            for index in range(raw["cluster_count"])
            if bitmap[index // 8] & (1 << (index % 8))
        ]
        self.assertEqual(len(allocated), 4458)
        self.assertEqual(max(allocated), 4459)
        last_byte = cluster_heap + (max(allocated) - 1) * cluster_size
        self.assertLessEqual(last_byte, 268435456)

        immutable_ranges = (
            (0, 12288),
            (1048576, 17840),
            (8650752, 512),
            (8683520, 145784832),
        )
        immutable = hashlib.sha256()
        with image.open("rb", buffering=0) as handle:
            for offset, length in immutable_ranges:
                handle.seek(offset)
                remaining = length
                while remaining:
                    chunk = handle.read(min(remaining, 1024 * 1024))
                    self.assertTrue(chunk)
                    immutable.update(chunk)
                    remaining -= len(chunk)
        self.assertEqual(
            immutable.hexdigest(),
            "1b761a61e89c46c49ab78c1634c25d22112c26f990c13daedf73791ca47aba7a",
        )
        self.assertIn("QUICK_EXFAT_BOOT_SIZE 12288ULL", C_SOURCE)
        self.assertIn("QUICK_EXFAT_FAT_PREFIX_SIZE 17840ULL", C_SOURCE)
        self.assertIn("QUICK_EXFAT_ROOT_PREFIX_SIZE 512ULL", C_SOURCE)
        self.assertIn("QUICK_EXFAT_PAYLOAD_SIZE 145784832ULL", C_SOURCE)
        self.assertIn("QUICK_EASYROMS_SIZE 51683880448ULL", C_SOURCE)
        self.assertIn("QUICK_EASYROMS_HEAD_SIZE 268435456ULL", C_SOURCE)
        self.assertIn("easyroms_size != QUICK_EASYROMS_SIZE", C_SOURCE)
        self.assertIn("easyroms_head_size != QUICK_EASYROMS_HEAD_SIZE", C_SOURCE)

    def test_fast_card_quick_requires_all_prior_write_and_allocation_proofs(self) -> None:
        quick_body = shell_function(AUDIT, "validate_fast_quick_proof")
        for marker in (
            "p3_build_status_sha256",
            "raw_verification_sha256",
            "allocation_bitmap_exact",
            "allocated_cluster_count",
            "claimed_cluster_count",
            "overlapping_clusters",
            "deleted_entries",
            "R46H_LAYOUT readback=prefix",
            "R46H_LAYOUT readback=boot",
            "R46H_LAYOUT readback=root",
            "R46H_LAYOUT readback=easyroms-metadata",
            "R46H_LAYOUT result=pass state=MEDIA_WRITE_COMPLETE",
            "quick audit evidence changed during validation",
        ):
            self.assertIn(marker, quick_body)
        self.assertIn('require_regular_user_file "$ASSET_DIR/03-easyroms-p3.img" 600', quick_body)
        self.assertIn('/bin/dd if="$ASSET_DIR/03-easyroms-p3.img"', quick_body)
        self.assertIn('[[ "$actual_head_sha" == "$EASYROMS_HEAD_SHA256" ]]', quick_body)
        self.assertIn('fast_p3_immutable_sha256 "$ASSET_DIR/03-easyroms-p3.img"', quick_body)
        self.assertIn(
            '[[ "$actual_immutable_sha" == "$EASYROMS_QUICK_IMMUTABLE_SHA256" ]]',
            quick_body,
        )
        self.assertLess(
            AUDIT.index("validate_fast_quick_proof\n"),
            AUDIT.index('[[ -f "$TOOL"'),
        )
        self.assertLess(
            AUDIT.index('[[ -f "$TOOL"'),
            AUDIT.index('/usr/bin/sudo -- /bin/bash -c "$ROOT_AUDIT"'),
        )

    def test_quick_skips_only_the_redundant_full_root_and_p3_repeats(self) -> None:
        audit_body = C_SOURCE[
            C_SOURCE.index("static int run_media_audit") : C_SOURCE.index(
                "static void usage", C_SOURCE.index("static int run_media_audit")
            )
        ]
        self.assertIn('if (!audit_is_quick) {\n        require_expected_hash(\n            target, root_offset', audit_body)
        self.assertIn('if (verify_full_easyroms) {', audit_body)
        for required in (
            'target, root_offset, root_size, root_sha, "root", root_actual',
            'target, 0, prefix_size, prefix_sha, "prefix-repeat", repeated',
            'target, boot_offset, boot_size, boot_actual, "boot-repeat", repeated',
            '"easyroms-head-repeat"',
            "run_filesystem_probe(",
            "verify_raw_identity(target, device_path, &target_before);",
            "eject_claimed_disk(device_path);",
        ):
            self.assertIn(required, audit_body)

    def test_build_keeps_a_valid_reproducible_macho_uuid(self) -> None:
        self.assertIn("-Wl,-reproducible", BUILD)
        self.assertNotIn("-no_uuid", BUILD)
        self.assertIn('temporary="$temporary_dir/r46h-card-layout-provision"', BUILD)
        self.assertIn('temporary_source="$temporary_dir/main.c"', BUILD)
        self.assertIn('"$temporary_source" \\', BUILD)
        self.assertIn('[[ "$snapshot_after" == "$source_actual"', BUILD)
        self.assertIn('"$source_after" == "$source_actual"', BUILD)
        self.assertIn("SOURCE_RECEIPT_PATH=", BUILD)
        self.assertIn('"$source_actual" "$SOURCE_RECEIPT_PATH"', BUILD)
        for entrypoint in (WRAPPER, AUDIT):
            self.assertIn("TOOL_SOURCE_RECEIPT_PATH=", entrypoint)
            self.assertIn(
                'actual_tool_source=$(/usr/bin/shasum -a 256 "$TOOL_SOURCE")',
                entrypoint,
            )

    def test_disk_claim_and_signal_transition_precede_writes(self) -> None:
        self.assertLess(
            C_SOURCE.rindex("claim_whole_disk(device_path);"),
            C_SOURCE.rindex("open(device_path, O_RDWR | O_NOFOLLOW)"),
        )
        self.assertIn("DADiskIsClaimed(claimed_disk)", C_SOURCE)
        self.assertIn("deny_claim_release", C_SOURCE)
        provision_body = C_SOURCE[C_SOURCE.index("int main(int argc") :]
        self.assertEqual(
            provision_body.count("require_no_target_mounts(expected_identifier);"),
            2,
        )
        self.assertLess(
            provision_body.index("require_no_target_mounts(expected_identifier);"),
            provision_body.index("stage=write-started"),
        )
        self.assertGreater(
            provision_body.rindex("require_no_target_mounts(expected_identifier);"),
            provision_body.index("verify_target_hash(target, &easyroms"),
        )
        self.assertLess(
            provision_body.rindex("require_no_target_mounts(expected_identifier);"),
            provision_body.rindex("eject_claimed_disk(device_path);"),
        )
        self.assertNotIn('release_disk_claim();\n    close(prefix.descriptor);', provision_body)
        self.assertIn("card_state=ejected next=reinsert-and-audit", provision_body)
        self.assertNotIn('/usr/sbin/diskutil eject "$device"', WRAPPER)
        self.assertIn('[[ ! -e "$device" && ! -e "$raw_device" ]]', WRAPPER)
        self.assertLess(
            C_SOURCE.index("signal(SIGPIPE, SIG_IGN)"),
            C_SOURCE.index("stage=write-started"),
        )
        self.assertIn('fail_data("stopped at write-phase transition")', C_SOURCE)
        self.assertIn('fail_data("operation interrupted")', C_SOURCE)

    def test_mbr_is_the_last_write_after_two_durability_barriers(self) -> None:
        boot = C_SOURCE.index("write_source(&boot, target, boot_offset);")
        root = C_SOURCE.index("write_source(&root, target, root_offset);")
        clear = C_SOURCE.index("zero_range(target, easyroms_offset, easyroms_zero_size);")
        easyroms = C_SOURCE.index("write_source(&easyroms, target, easyroms_offset);")
        payload_sync = C_SOURCE.index(
            'synchronize_target(target, "partition-payloads-before-prefix");'
        )
        prefix_tail = C_SOURCE.index('"prefix-tail"', payload_sync)
        prefix_sync = C_SOURCE.index(
            'synchronize_target(target, "prefix-tail-before-mbr");'
        )
        mbr = C_SOURCE.index(
            'write_source_range(&prefix, target, 0, 0, 512, "mbr-sector-last");'
        )
        final_sync = C_SOURCE.index('synchronize_target(target, "mbr-commit");')
        readback = C_SOURCE.index("verify_target_hash(target, &prefix, 0);")
        self.assertLess(boot, root)
        self.assertLess(root, clear)
        self.assertLess(clear, easyroms)
        self.assertLess(easyroms, payload_sync)
        self.assertLess(payload_sync, prefix_tail)
        self.assertLess(prefix_tail, prefix_sync)
        self.assertLess(prefix_sync, mbr)
        self.assertLess(mbr, final_sync)
        self.assertLess(final_sync, readback)
        main_body = C_SOURCE[C_SOURCE.index("int main(int argc") :]
        self.assertEqual(
            len(re.findall(r"(?m)^\s+synchronize_target\(", main_body)),
            3,
        )

    def test_full_readback_and_source_recheck_are_fail_closed(self) -> None:
        self.assertIn("verify_target_hash(target, &prefix, 0);", C_SOURCE)
        self.assertIn("verify_target_hash(target, &boot, boot_offset);", C_SOURCE)
        self.assertIn("verify_target_hash(target, &root, root_offset);", C_SOURCE)
        self.assertIn("verify_target_hash(target, &easyroms, easyroms_offset);", C_SOURCE)
        self.assertIn("verify_zero_range(", C_SOURCE)
        self.assertIn("verify_source_unchanged(&prefix);", C_SOURCE)
        self.assertIn("verify_source_unchanged(&root);", C_SOURCE)
        self.assertIn("verify_raw_identity(target, device_path, &target_before);", C_SOURCE)

    def test_audit_keeps_one_claimed_read_only_fd_through_probe_and_eject(self) -> None:
        self.assertNotIn('strcmp(argv[1], "snapshot") == 0', C_SOURCE)
        self.assertIn('strcmp(argv[1], "audit") == 0', C_SOURCE)
        self.assertEqual(
            C_SOURCE.count("open(device_path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC)"),
            1,
        )
        self.assertIn("R46H_MEDIA_AUDIT result=pass", C_SOURCE)
        self.assertIn("create_snapshot(", C_SOURCE)
        self.assertIn("run_filesystem_probe(", C_SOURCE)
        self.assertIn("require_no_target_mounts(expected_identifier);", C_SOURCE)
        self.assertIn('"boot-repeat"', C_SOURCE)
        self.assertIn('"root-repeat"', C_SOURCE)
        self.assertIn('"prefix-repeat"', C_SOURCE)
        self.assertIn('"easyroms-head-repeat"', C_SOURCE)
        audit_body = C_SOURCE[
            C_SOURCE.index("static int run_media_audit") : C_SOURCE.index(
                "static void usage", C_SOURCE.index("static int run_media_audit")
            )
        ]
        claim = audit_body.index("claim_whole_disk(device_path);")
        raw_open = audit_body.index("open(device_path, O_RDONLY")
        probe = audit_body.index("run_filesystem_probe(")
        root_repeat = audit_body.index('"root-repeat"')
        identity = audit_body.index("verify_raw_identity(")
        eject = audit_body.index("eject_claimed_disk(device_path);")
        marker = audit_body.index('"R46H_MEDIA_AUDIT result=pass')
        self.assertLess(claim, raw_open)
        self.assertLess(raw_open, probe)
        self.assertLess(probe, root_repeat)
        self.assertLess(root_repeat, identity)
        self.assertLess(identity, eject)
        self.assertLess(eject, marker)
        self.assertNotIn("DKIOCSYNCHRONIZECACHE", audit_body)

        eject_start = C_SOURCE.index("static void eject_claimed_disk")
        eject_body = C_SOURCE[
            eject_start : C_SOURCE.index("static void fail_errno", eject_start)
        ]
        self.assertNotIn("DADiskUnclaim", eject_body)
        self.assertLess(
            eject_body.index("DADiskIsClaimed"), eject_body.index("DADiskEject")
        )
        self.assertEqual(C_SOURCE.count("DADiskUnclaim("), 1)

    def test_privileged_parent_supervises_worker_without_pipeline(self) -> None:
        self.assertNotIn("| /usr/bin/tee", WRAPPER)
        self.assertNotIn("PIPESTATUS", WRAPPER)
        self.assertIn('> "$receipt_dir/layout-provision.log" 2>&1 &', WRAPPER)
        self.assertIn("wait_for_worker()", WRAPPER)
        self.assertIn("forward_worker_signal()", WRAPPER)
        self.assertIn('trap "" INT TERM HUP', WRAPPER)
        self.assertIn("worker_marker_count=", WRAPPER)
        self.assertLess(
            WRAPPER.index("worker_marker_count="),
            WRAPPER.index('[[ ! -e "$device" && ! -e "$raw_device" ]]'),
        )
        self.assertNotIn('/usr/sbin/fdisk "$device"', WRAPPER[WRAPPER.index("worker_marker_count=") :])
        self.assertNotIn("/usr/bin/sync", WRAPPER)

    def test_supervisor_wait_loop_is_shared_and_signal_safe_on_bash_3(self) -> None:
        self.assertEqual(
            shell_function(WRAPPER, "forward_worker_signal"),
            shell_function(AUDIT, "forward_worker_signal"),
        )
        self.assertEqual(
            shell_function(WRAPPER, "wait_for_worker"),
            shell_function(AUDIT, "wait_for_worker"),
        )

        cache = ROOT / "mainline/out/.cache"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="r46h-supervisor-test.", dir=cache) as temp:
            temp_path = Path(temp)
            fake_worker = temp_path / "fake-worker.sh"
            fake_worker.write_text(
                """#!/bin/bash
set -u
mode=$1
event=$2
case "$mode" in
  prewrite)
    trap 'exit 86' INT TERM HUP
    printf 'prewrite\\n' > "$event"
    while :; do /bin/sleep 1; done
    ;;
  write)
    trap '' INT TERM HUP PIPE
    printf 'write\\n' > "$event"
    /bin/sleep 2
    printf 'worker-pass\\n'
    ;;
  *) exit 64 ;;
esac
""",
                encoding="utf-8",
            )
            fake_worker.chmod(0o700)
            harness = temp_path / "harness.sh"
            harness.write_text(
                "#!/bin/bash\n"
                "set -u\n"
                "worker_pid=\nworker_result=127\npending_signal=\n"
                + shell_function(WRAPPER, "forward_worker_signal")
                + shell_function(WRAPPER, "wait_for_worker")
                + """
worker=$1
mode=$2
event=$3
pid_file=$4
result_file=$5
log_file=$6
trap 'forward_worker_signal INT' INT
trap 'forward_worker_signal TERM' TERM
trap 'forward_worker_signal HUP' HUP
"$worker" "$mode" "$event" > "$log_file" 2>&1 &
worker_pid=$!
printf '%s\\n' "$worker_pid" > "$pid_file"
if [[ -n "$pending_signal" ]]; then
  /bin/kill "-$pending_signal" "$worker_pid" 2>/dev/null || true
fi
set +e
wait_for_worker
status=$worker_result
set -e
printf '%s\\n' "$status" > "$result_file"
exit "$status"
""",
                encoding="utf-8",
            )
            harness.chmod(0o700)

            for mode, expected, minimum_elapsed in (
                ("prewrite", 86, 0.0),
                ("write", 0, 1.5),
            ):
                with self.subTest(mode=mode):
                    event = temp_path / f"{mode}.event"
                    pid_file = temp_path / f"{mode}.pid"
                    result = temp_path / f"{mode}.result"
                    log = temp_path / f"{mode}.log"
                    started = time.monotonic()
                    process = subprocess.Popen(
                        [
                            "/bin/bash",
                            str(harness),
                            str(fake_worker),
                            mode,
                            str(event),
                            str(pid_file),
                            str(result),
                            str(log),
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline:
                        if event.exists() and pid_file.exists():
                            break
                        time.sleep(0.02)
                    self.assertTrue(event.exists())
                    child_pid = int(pid_file.read_text(encoding="utf-8").strip())
                    os.kill(process.pid, signal.SIGTERM)
                    _, stderr = process.communicate(timeout=8)
                    elapsed = time.monotonic() - started
                    self.assertEqual(process.returncode, expected, stderr)
                    self.assertEqual(
                        int(result.read_text(encoding="utf-8").strip()),
                        expected,
                    )
                    self.assertGreaterEqual(elapsed, minimum_elapsed)
                    with self.assertRaises(ProcessLookupError):
                        os.kill(child_pid, 0)
                    if mode == "write":
                        self.assertEqual(log.read_text(encoding="utf-8"), "worker-pass\n")

    def test_post_reinsert_audit_is_pinned_read_only_and_ejects(self) -> None:
        self.assertIn("$staged_tool\" audit", AUDIT)
        self.assertNotIn("$staged_tool\" snapshot", AUDIT)
        root_audit = AUDIT[AUDIT.index("ROOT_AUDIT='") :]
        self.assertNotIn("/bin/dd if=", root_audit)
        self.assertNotIn("/sbin/fsck_msdos", AUDIT)
        self.assertNotIn("/sbin/fsck_exfat", AUDIT)
        self.assertNotIn("mount readOnly", AUDIT)
        self.assertNotIn('/usr/sbin/diskutil eject "$device"', AUDIT)
        self.assertIn("filesystem-snapshot-probe.sh", AUDIT)
        self.assertIn("boot-snapshot.img", AUDIT)
        self.assertIn("easyroms-snapshot.img", AUDIT)
        self.assertIn("E1F5295C-4B12-A54A-ACB7-317194240001", AUDIT)
        self.assertIn("75495362-8048-4A4A-ACB7-625349754881", AUDIT)
        self.assertIn("easyroms-repeat", C_SOURCE)
        self.assertIn("three-payloads", PROBE)
        self.assertIn("r46h-v0.10-adc-full-range", PROBE)
        self.assertIn('"card_state\\":\\"ejected', AUDIT)
        self.assertNotIn("/usr/bin/sync", AUDIT)

        self.assertIn("/sbin/fsck_msdos -n", PROBE)
        self.assertIn("/sbin/fsck_exfat -n", PROBE)
        self.assertNotIn("fsck_msdos -y", PROBE)
        self.assertNotIn("fsck_exfat -y", PROBE)
        self.assertEqual(PROBE.count("-readonly -nomount"), 1)
        self.assertIn("diskimage-class=CRawDiskImage", PROBE)
        self.assertEqual(PROBE.count("-o rdonly,noowners,nobrowse"), 2)
        self.assertIn("BOOT-ANCHORS.sha256", PROBE)
        self.assertIn('find "$easyroms_mount"', PROBE)
        self.assertIn('unexpected EASYROMS metadata entry type', PROBE)
        self.assertIn('[[ -d "$entry" && ! -L "$entry" ]]', PROBE)
        self.assertIn("WritableVolume", PROBE)
        self.assertNotIn("/dev/r${expected_identifier}s1", PROBE)

    def test_post_reinsert_root_worker_receives_p3_sector_count(self) -> None:
        prelude = embedded_root_audit_prelude(AUDIT)
        self.assertIn('[[ "$#" -eq 36 ]]', prelude)
        self.assertIn('expected_uid=${26}', prelude)
        self.assertIn('expected_gid=${27}', prelude)
        self.assertIn('expected_p3_sectors=${28}', prelude)
        self.assertIn('audit_level=${29}', prelude)
        self.assertIn('easyroms_head_sha=${30}', prelude)
        self.assertIn('quick_immutable_sha=${36}', prelude)
        command = prelude + 'printf "%s:%s:%s:%s:%s:%s\\n" "$expected_uid" "$expected_gid" "$expected_p3_sectors" "$audit_level" "$easyroms_head_sha" "$quick_immutable_sha"\n'
        arguments = [f"argument-{index}" for index in range(1, 26)] + [
            "501",
            "20",
            "100945079",
            "quick",
            "d7923cfdb8b9b287a1946548699a9933234c50e89b51ac95f584f7f6ac90340e",
            "12199690592",
            "e3b11a96fff037db123316762ef79ee14fb687d4ecccc3244fc0fc8281f50285",
            "46b3797082d450a5fcf3132e3740a28fc1a6318f5592bc5502090344d9eccfda",
            "05f706354bf46c9ad5237815f40d0b9155b8b103b6ab8ad9e3cfc1a81fe3ef08",
            "560de14babd243bbb981dca5b5a697660c895200be5f633a67d33d66ee398915",
            "1b761a61e89c46c49ab78c1634c25d22112c26f990c13daedf73791ca47aba7a",
        ]
        result = subprocess.run(
            ["/bin/bash", "-c", command, "r46h-audit-argument-test", *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout,
            "501:20:100945079:quick:d7923cfdb8b9b287a1946548699a9933234c50e89b51ac95f584f7f6ac90340e:1b761a61e89c46c49ab78c1634c25d22112c26f990c13daedf73791ca47aba7a\n",
        )
        self.assertIn('"$expected_uid" "$expected_gid" "$EXPECTED_P3_SECTORS" \\', AUDIT)

        missing = subprocess.run(
            [
                "/bin/bash",
                "-c",
                command,
                "r46h-audit-argument-test",
                *arguments[:-1],
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertNotEqual(missing.returncode, 0)

    def test_audit_completion_marker_is_published_last(self) -> None:
        status_move = AUDIT.index('/bin/mv -f -- "$final_status_tmp" "$status_file"')
        status_sync = AUDIT.index("/bin/sync", status_move)
        marker_move = AUDIT.index(
            '/bin/mv -f -- "$marker_tmp" "$receipt_dir/AUDIT-COMPLETE"'
        )
        complete = AUDIT.index("audit_complete=1", marker_move)
        self.assertLess(status_move, status_sync)
        self.assertLess(status_sync, marker_move)
        self.assertLess(marker_move, complete)
        self.assertNotIn("/bin/sync", AUDIT[marker_move:complete])
        handoff = AUDIT.index("if ! finalize_receipt_ownership", complete)
        self.assertLess(complete, handoff)
        self.assertNotIn("chown -R", AUDIT)
        finalizer = shell_function(AUDIT, "finalize_receipt_ownership")
        self.assertLess(
            finalizer.index('change_owner "$expected_uid:$expected_gid" "$item"'),
            finalizer.index('change_owner "$expected_uid:$expected_gid" "$receipt_dir"'),
        )
        self.assertTrue(
            finalizer.rstrip().endswith(
                'change_owner "$expected_uid:$expected_gid" "$receipt_dir"\n}'
            )
        )
        self.assertNotRegex(AUDIT, r"local label=.*\$\{label\}")
        self.assertNotRegex(AUDIT, r"local mount_point=.*\$mount_point")

    def test_audit_receipt_is_root_private_until_final_handoff(self) -> None:
        self.assertIn("readonly ROOT_RECEIPT_PARENT=/private/tmp", AUDIT)
        self.assertNotIn('/bin/mkdir -p "$RECEIPT_PARENT"', AUDIT)
        self.assertNotIn('mktemp -d "$RECEIPT_PARENT/', AUDIT)
        self.assertIn(
            'receipt_dir=$(/usr/bin/mktemp -d "$receipt_parent/.r46h-new-card-postwrite.XXXXXX")',
            AUDIT,
        )
        parent_gate = shell_function(AUDIT, "root_receipt_parent_is_safe")
        for marker in (
            '"$receipt_parent" == "$ROOT_RECEIPT_PARENT"',
            '! -L "$receipt_parent" && -k "$receipt_parent"',
            '"$uid" == 0 && "$gid" == 0',
            "Owners:[[:space:]]+Enabled$",
            '"$physical" != "${device#/dev/}"',
        ):
            self.assertIn(marker, parent_gate)
        self.assertIn(
            '[[ "${SUDO_UID:-}" == "$expected_uid" && "${SUDO_GID:-}" == "$expected_gid"',
            AUDIT,
        )

    def test_audit_cleanup_never_touches_the_device(self) -> None:
        cleanup = shell_function(AUDIT, "cleanup")
        for forbidden in (
            "diskutil",
            "hdiutil",
            "unmount",
            "umount",
            "eject",
            "fdisk",
            '"$raw_device"',
        ):
            self.assertNotIn(forbidden, cleanup)
        self.assertLess(
            AUDIT.index('/usr/bin/grep -Eq "\\[ +21193545 - +${expected_p3_sectors}\\]" "$receipt_dir/fdisk.txt"'),
            AUDIT.index('/usr/sbin/diskutil unmountDisk "$device" > "$receipt_dir/unmount-before.txt"'),
        )

    def test_cleanup_preserves_failure_status_on_bash_3(self) -> None:
        for label, source in (
            ("provision", WRAPPER),
            ("audit", AUDIT),
            ("probe", PROBE),
        ):
            with self.subTest(label=label):
                cleanup = shell_function(source, "cleanup")
                match = re.match(
                    r"cleanup\(\) \{\n  local (status|task_status)=\$\?\n",
                    cleanup,
                )
                self.assertIsNotNone(match)
                status_name = match.group(1)
                harness = f"""#!/bin/bash
set -u
cleanup() {{
  local {status_name}=$?
  trap - EXIT
  exit "${{{status_name}}}"
}}
trap cleanup EXIT
false
"""
                result = subprocess.run(
                    ["/bin/bash", "-c", harness],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 1, result.stderr)

        self.assertIn(
            'if [[ "$audit_complete" -ne 1 && "$status" -eq 0 ]]; then\n'
            "    status=1\n"
            "  fi",
            shell_function(AUDIT, "cleanup"),
        )
        nounset = subprocess.run(
            [
                "/bin/bash",
                "-c",
                "set -euo pipefail; audit_complete=0; cleanup(){ local status=$?; "
                "trap - EXIT; set +e; "
                'if [[ "$audit_complete" -ne 1 && "$status" -eq 0 ]]; then '
                "status=1; fi; exit \"$status\"; }; "
                "trap cleanup EXIT; echo \"$missing\"",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(nounset.returncode, 1, nounset.stderr)

        self.assertNotIn('[[ "$audit_status" -eq 0 ]]', AUDIT)
        self.assertIn(
            'if [[ "$audit_status" -ne 0 ]]; then\n  exit "$audit_status"\nfi',
            AUDIT,
        )
        self.assertIn('trap "exit 143" TERM\ntrap "exit 129" HUP', PROBE)
        for expected_status in (65, 129, 130, 143):
            with self.subTest(worker_status=expected_status):
                result = subprocess.run(
                    [
                        "/bin/bash",
                        "-c",
                        'audit_status=$1; if [[ "$audit_status" -ne 0 ]]; then '
                        'exit "$audit_status"; fi',
                        "r46h-audit-status-test",
                        str(expected_status),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, expected_status, result.stderr)

    def test_layout_stage_never_claims_boot_safety(self) -> None:
        self.assertNotIn("safe_to_boot=yes", WRAPPER)
        self.assertNotIn("safe_to_boot=yes", C_SOURCE)
        self.assertIn(
            "safe_to_boot=no \"\n           \"card_state=ejected next=reinsert-and-audit",
            C_SOURCE,
        )
        self.assertIn('\\"safe_to_boot\\":false', WRAPPER)

    def test_scripts_are_bash_3_syntax_clean(self) -> None:
        for path in (WRAPPER_PATH, AUDIT_PATH, PROBE_PATH, BUILD_PATH):
            result = subprocess.run(
                ["/bin/bash", "-n", str(path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
