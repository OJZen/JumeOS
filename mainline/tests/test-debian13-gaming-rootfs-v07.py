#!/usr/bin/env python3
"""Focused host gates for the R46H Debian gaming p2 v0.7 successor."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


REPO = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO / "mainline/scripts/build-debian13-gaming-rootfs-v07.py"
SPEC = importlib.util.spec_from_file_location("debian13_gaming_rootfs_v07", BUILDER_PATH)
assert SPEC is not None and SPEC.loader is not None
WRAPPER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = WRAPPER
SPEC.loader.exec_module(WRAPPER)
BUILDER = WRAPPER.BASE
ROOT = REPO / "mainline/rootfs-debian13-gaming-v07"
IMAGE_TOOL = ROOT / "image-in-container.sh"
README = ROOT / "README.md"


class Debian13GamingRootfsV07Tests(unittest.TestCase):
    def test_identity_is_an_exact_v06_successor(self) -> None:
        self.assertEqual(BUILDER.ARTIFACT_ID, "debian13-p2-gaming-v0.7")
        self.assertEqual(BUILDER.OUTPUT_NAME, "r46h-debian13-p2-gaming-v0.7")
        self.assertEqual(BUILDER.IMAGE_SIZE, 10_716_877_312)
        self.assertEqual(BUILDER.BASE_FS_UUID, "d3130006-46a4-4d56-9001-000000000006")
        self.assertEqual(BUILDER.FS_UUID, "d3130007-46a4-4d56-9001-000000000007")
        self.assertEqual(BUILDER.FS_LABEL, "R46H_GAMING_V07")
        self.assertEqual(BUILDER.SOURCE_DATE_EPOCH, "1788048000")
        self.assertEqual(
            BUILDER.BASE_IMAGE_SHA256,
            "4ac3a525264fcab7efda804c147f8e77604cbee82847d504de7e359258ca4bee",
        )

    def test_renderer_payload_identity_is_exact(self) -> None:
        self.assertEqual(BUILDER.GAMING_PAYLOAD_ID, "r46h-gaming-mvp-v0.6")
        self.assertEqual(BUILDER.GAMING_ARCHIVE_SIZE, 263_537_654)
        self.assertEqual(
            BUILDER.GAMING_ARCHIVE_SHA256,
            "4c03d9d621ac362ce1fdc80628510d1f36e57e7d368eaa600b2f18af44bb31fa",
        )
        self.assertEqual(
            BUILDER.GAMING_PAYLOAD_SHA256SUMS_SHA256,
            "d1d9a713b0b70e7bb7834c90a12147039280c72fa00360562eaf754c20035619",
        )
        self.assertEqual(
            BUILDER.EXTRA_BUILD_ENVIRONMENT["FINAL_RUNNER_SHA256"],
            "27d2f987545a3ab20610806923372b41530d41e5e3fc0384614211088d71135c",
        )

    def test_overlay_is_exactly_three_payload_files_plus_identity_state(self) -> None:
        script = IMAGE_TOOL.read_text(encoding="utf-8")
        changed_block = script.split("readonly -a CHANGED_FILES=(", 1)[1].split(")", 1)[0]
        self.assertEqual(changed_block.count("files/"), 3)
        for destination in (
            "/usr/local/sbin/r46h-game-ui",
            "/usr/local/libexec/r46h-gaming-frontend-condition",
            "/usr/share/doc/r46h-gaming-mvp/GAMING-PRODUCT.md",
        ):
            self.assertIn(destination, changed_block)
        self.assertIn('for entry in "${UNCHANGED_FILES[@]}"', script)
        self.assertIn("v0.6 payload unexpectedly changes", script)
        self.assertIn("successor_method=offline-debugfs-bounded-overlay", script)

    def test_rollback_state_matches_the_accepted_live_installer(self) -> None:
        script = IMAGE_TOOL.read_text(encoding="utf-8")
        for marker in (
            "/var/lib/r46h/gaming-mvp-v0.6-rollback",
            "gaming-mvp-v0.5-installed",
            "upgrade_id=r46h-gaming-mvp-v0.6",
            "previous_receipt_sha256=%s",
            "sha256sum GAMING-PRODUCT.md gaming-mvp-v0.5-installed r46h-game-ui",
            "0040700",
            "ROLLBACK-STATE.sha256",
            "rollback manifest verification failed",
        ):
            self.assertIn(marker, script)
        self.assertEqual(
            BUILDER.EXTRA_BUILD_ENVIRONMENT["ROLLBACK_MANIFEST_SHA256"],
            "cab1619dd8bfbcc022a5b33daea49020b24c197cfda793831c6afaed90f1bdbf",
        )
        self.assertEqual(BUILDER.EXTRA_BUILD_INFO["gaming_overlay_file_count"], "3")

    def test_runtime_identity_transformations_are_exact(self) -> None:
        script = IMAGE_TOOL.read_text(encoding="utf-8")
        self.assertIn("s/debian13-p2-gaming-v0\\.6/debian13-p2-gaming-v0.7/g", script)
        self.assertIn('s/$BASE_FS_UUID/$FS_UUID/g', script)
        self.assertEqual(
            BUILDER.FINAL_FIRSTBOOT_SHA256,
            "3e4ea0389887c508e4bbcdbae2e07c19018d2777c55256bbbfa596255ffda72d",
        )
        self.assertEqual(
            BUILDER.FINAL_ROOTFS_SMOKE_SHA256,
            "b5d04865dcff63c6e8221d7d5ee2261000459f906bbdca2231b98cc1c2bb51cb",
        )

    def test_builder_is_networkless_host_only_and_reproducible(self) -> None:
        base_source = (REPO / WRAPPER.BASE_BUILDER_RELATIVE).read_text(encoding="utf-8")
        wrapper_source = BUILDER_PATH.read_text(encoding="utf-8")
        self.assertIn('"--network",\n        "none"', base_source)
        self.assertIn('run_image_tool(\n            docker,\n            "apply"', base_source)
        self.assertIn("second p2 {VERSION_TEXT} composition is not byte-reproducible", base_source)
        self.assertIn('run_image_tool(\n            docker,\n            "verify"', base_source)
        self.assertEqual(BUILDER.ARTIFACT_STATUS, "host-only-no-media-operation-performed")
        self.assertNotIn("subprocess.run", wrapper_source)
        self.assertNotIn("/dev/disk", wrapper_source)

    def test_source_scope_and_evidence_are_versioned(self) -> None:
        self.assertEqual(
            BUILDER.SOURCE_PATHS,
            (
                WRAPPER.README_RELATIVE,
                WRAPPER.IMAGE_TOOL_RELATIVE,
                WRAPPER.BUILDER_RELATIVE,
                WRAPPER.TEST_RELATIVE,
                WRAPPER.BASE_BUILDER_RELATIVE,
                "mainline/deploy/profiles/hl-r46h-v22-g92-v1.json",
            ),
        )
        self.assertIn("DEBUGFS-V07.txt", BUILDER.APPLY_EVIDENCE)
        self.assertIn("ROLLBACK-STATE.sha256", BUILDER.APPLY_EVIDENCE)
        self.assertIn("INDEPENDENT-DEBUGFS-V07.txt", BUILDER.REQUIRED_STAGE_FILES)
        self.assertRegex(
            ".r46h-debian13-p2-gaming-v0.7.tmp.A1", BUILDER.STAGE_RE
        )

    def test_image_tool_is_syntax_valid_and_has_no_media_or_network_path(self) -> None:
        self.assertEqual(
            subprocess.run(["/bin/bash", "-n", str(IMAGE_TOOL)], check=False).returncode,
            0,
        )
        script = IMAGE_TOOL.read_text(encoding="utf-8")
        for forbidden in (
            "/dev/disk",
            "dd if=",
            "mkfs.ext",
            "mke2fs ",
            "curl ",
            "wget ",
            "apt-get",
        ):
            self.assertNotIn(forbidden, script)
        self.assertNotRegex(script, r"(?m)^\s*saveenv\b")

    def test_readme_keeps_evidence_and_current_card_boundaries(self) -> None:
        normalized = " ".join(README.read_text(encoding="utf-8").split())
        for marker in (
            "HOST + P2 MEDIA + PHYSICAL PASS",
            "replaces exactly three payload-owned files",
            "byte-identical to the v0.6 base image",
            "host-only-no-media-operation-performed",
            "never opens a block device",
            "POSTWRITE-AUDIT.json",
            "p2-v07-cold-product-20260830T125652Z.bin",
            "d2a8078bddc522ef0ebb593c5c10202223da04b140f936471cd37120d6064ce4",
            "p1 and p3 must stay outside that plan",
            "current imported p3 is not the historical recovery p3",
            "Target acceptance of the input payload does not itself prove",
            "candidate-requires-card-agent-live-preflight",
            "--artifact-id debian13-p2-gaming-v0.7",
        ):
            self.assertIn(marker, normalized)


if __name__ == "__main__":
    unittest.main()
