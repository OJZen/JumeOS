#!/usr/bin/env python3
"""Focused host gates for the R46H first-version release source set."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unittest


REPO = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO / "mainline/scripts/build-r46h-first-version-release.py"
SPEC = importlib.util.spec_from_file_location("r46h_first_version_release", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
BUILDER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = BUILDER
SPEC.loader.exec_module(BUILDER)
README = REPO / "mainline/first-version-release/README.md"


def file_identity(size: int, digest: str) -> dict[str, object]:
    return {"sha256": digest, "size": size}


def synthetic_p1() -> tuple[
    dict[str, dict[str, object]],
    dict[str, dict[str, object]],
    list[str],
    list[str],
]:
    before = {
        path: file_identity(size, digest)
        for path, (size, digest) in BUILDER.P1_PRESERVED_ANCHORS.items()
    }
    before["boot.ini"] = file_identity(
        *BUILDER.P1_PRESERVED_ANCHORS["boot.ini.v0.15-gaming-product"]
    )
    filler_count = BUILDER.P1_BASE_NON_SPOTLIGHT_FILE_COUNT - len(before)
    for index in range(filler_count):
        before[f"preserved/file-{index:03d}"] = file_identity(index, f"{index:064x}")
    before[".Spotlight-V100/index"] = file_identity(7, "f" * 64)
    after = dict(before)
    del after[".Spotlight-V100/index"]
    after["boot.ini"] = file_identity(BUILDER.V17_BOOT_SIZE, BUILDER.V17_BOOT_SHA256)
    after[BUILDER.V17_BOOT_NAME] = file_identity(
        BUILDER.V17_BOOT_SIZE, BUILDER.V17_BOOT_SHA256
    )
    after[BUILDER.V17_DTB_NAME] = file_identity(
        BUILDER.V17_DTB_SIZE, BUILDER.V17_DTB_SHA256
    )
    before_directories = [".Spotlight-V100", "preserved"]
    after_directories = ["preserved"]
    return before, after, before_directories, after_directories


class R46HFirstVersionReleaseTests(unittest.TestCase):
    def test_exact_geometry_is_contiguous_and_covers_card(self) -> None:
        self.assertEqual(BUILDER.P1_OFFSET, BUILDER.PREFIX_SIZE)
        self.assertEqual(BUILDER.P2_OFFSET, BUILDER.P1_OFFSET + BUILDER.P1_SIZE)
        self.assertEqual(BUILDER.P3_OFFSET, BUILDER.P2_OFFSET + BUILDER.P2_SIZE)
        self.assertEqual(BUILDER.WHOLE_SIZE, BUILDER.P3_OFFSET + BUILDER.P3_SIZE)
        self.assertEqual(BUILDER.WHOLE_SIZE % BUILDER.SECTOR_SIZE, 0)

    def test_exact_p1_diff_accepts_only_release_normalization(self) -> None:
        before, after, before_dirs, after_dirs = synthetic_p1()
        diff = BUILDER.validate_exact_p1_diff(before, after, before_dirs, after_dirs)
        self.assertEqual(diff["added"], sorted((BUILDER.V17_BOOT_NAME, BUILDER.V17_DTB_NAME)))
        self.assertEqual(diff["changed"], ["boot.ini"])
        self.assertEqual(diff["removed_spotlight_files"], 1)
        self.assertEqual(diff["preserved_non_spotlight_files"], 168)

    def test_p1_diff_rejects_extra_change_and_inert_v16(self) -> None:
        before, after, before_dirs, after_dirs = synthetic_p1()
        after["preserved/file-000"] = file_identity(1, "a" * 64)
        with self.assertRaises(BUILDER.BuildError):
            BUILDER.validate_exact_p1_diff(before, after, before_dirs, after_dirs)
        before, after, before_dirs, after_dirs = synthetic_p1()
        after["boot.ini.v0.16-disable-secondary"] = file_identity(1, "b" * 64)
        with self.assertRaises(BUILDER.BuildError):
            BUILDER.validate_exact_p1_diff(before, after, before_dirs, after_dirs)

    def test_asset_manifest_is_strict_and_host_only(self) -> None:
        manifest = BUILDER.render_asset_manifest(
            p1_sha256="1" * 64,
            source_commit="2" * 40,
            source_tree="3" * 40,
            source_manifest_sha256="4" * 64,
        )
        parsed = BUILDER.parse_asset_manifest(manifest)
        self.assertEqual(tuple(parsed), BUILDER.ASSET_MANIFEST_KEYS)
        self.assertEqual(parsed["evidence_level"], "host-artifact-only")
        self.assertEqual(parsed["media_write_performed"], "false")
        self.assertEqual(parsed["physical_devices_accessed"], "0")
        self.assertEqual(parsed["full_card_materialized"], "false")

    def test_pinned_prefix_mbr_matches_profile_geometry(self) -> None:
        prefix = REPO / BUILDER.PREFIX_RELATIVE
        self.assertEqual(BUILDER.sha256_file(prefix), BUILDER.PREFIX_SHA256)
        BUILDER.validate_mbr(prefix)
        profile = (REPO / BUILDER.PROFILE_RELATIVE).read_bytes()
        parsed = BUILDER.validate_profile(profile)
        self.assertEqual(parsed["card"]["whole_size"], BUILDER.WHOLE_SIZE)

    def test_fixed_macos_fsck_link_resolves_to_root_owned_tool(self) -> None:
        resolved = BUILDER.require_system_tool(
            BUILDER.FSCK_MSDOS,
            BUILDER.FSCK_MSDOS_TARGET,
            "fsck_msdos",
        )
        self.assertEqual(resolved, BUILDER.FSCK_MSDOS_TARGET)

    def test_v17_archive_is_safe_and_exact(self) -> None:
        archive = REPO / BUILDER.V17_ARCHIVE_RELATIVE
        boot, dtb = BUILDER.load_v17_payload(archive)
        self.assertEqual(hashlib.sha256(boot).hexdigest(), BUILDER.V17_BOOT_SHA256)
        self.assertEqual(hashlib.sha256(dtb).hexdigest(), BUILDER.V17_DTB_SHA256)
        self.assertNotIn(b"saveenv", boot)

    def test_upstream_receipts_pin_accepted_components(self) -> None:
        BUILDER.validate_upstream_receipts(
            (REPO / BUILDER.P1_AUDIT_RELATIVE).read_bytes(),
            (REPO / BUILDER.P2_BUILD_INFO_RELATIVE).read_bytes(),
            (REPO / BUILDER.P3_BUILD_STATUS_RELATIVE).read_bytes(),
            (REPO / BUILDER.V17_BUILD_RECEIPT_RELATIVE).read_bytes(),
            (REPO / BUILDER.PROFILE_RELATIVE).read_bytes(),
        )

    def test_source_closes_block_device_and_network_paths(self) -> None:
        source = BUILDER_PATH.read_text(encoding="utf-8")
        self.assertIn('"--network",\n        "none"', source)
        self.assertIn('str(path).startswith("/dev/")', source)
        self.assertIn('"block_devices_opened": 0', source)
        self.assertIn('"physical_devices_accessed": 0', source)
        self.assertIn('"media_write_performed": False', source)
        self.assertNotIn("saveenv_used=true", source)
        self.assertNotIn("open(\"/dev/disk", source)

    def test_publication_is_atomic_noreplace(self) -> None:
        source = BUILDER_PATH.read_text(encoding="utf-8")
        self.assertIn("renameatx_np", source)
        self.assertIn("0x00000004", source)
        self.assertNotIn("os.replace(stage", source)

    def test_readme_keeps_physical_and_a2_boundaries_explicit(self) -> None:
        text = README.read_text(encoding="utf-8")
        for marker in (
            "host-only",
            "62,534,975,488",
            ".Spotlight-V100",
            "v0.8, v0.10 and v0.15",
            "authorize or start",
            "compatible, but A2",
        ):
            self.assertIn(marker, text)

    def test_receipt_json_round_trip_is_canonical(self) -> None:
        payload = BUILDER.canonical_json({"z": 1, "a": [2, 3]})
        self.assertEqual(payload, b'{"a":[2,3],"z":1}\n')
        self.assertEqual(json.loads(payload), {"a": [2, 3], "z": 1})


if __name__ == "__main__":
    unittest.main()
