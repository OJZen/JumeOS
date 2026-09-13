#!/usr/bin/env python3
"""Focused host tests for the R46H v0.14 gaming-input one-shot payload."""

from __future__ import annotations

import gzip
import importlib.util
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO / "mainline/scripts/build-v14-gaming-input-one-shot.py"
RUNBOOK_PATH = REPO / "mainline/bringup-tests/GAMING-INPUT-BRIDGE.md"


def load_builder():
    spec = importlib.util.spec_from_file_location("r46h_v14_one_shot", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load v0.14 one-shot builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class V14GamingInputOneShotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load_builder()
        cls.image, cls.dtb, cls.modules = cls.builder.read_package()
        captured = {
            relative: (REPO / relative).read_bytes()
            for relative in cls.builder.SOURCE_PATHS
            if relative.endswith(".in")
        }
        cls.files = cls.builder.payload_files(
            cls.image, cls.dtb, cls.modules, captured
        )
        cls.archive = cls.builder.deterministic_archive(cls.files)

    def test_canonical_package_identity_and_module_boundary(self) -> None:
        self.assertEqual(len(self.image), self.builder.IMAGE_SIZE)
        self.assertEqual(
            self.builder.sha256_bytes(self.image), self.builder.IMAGE_SHA256
        )
        self.assertEqual(len(self.dtb), self.builder.DTB_SIZE)
        self.assertEqual(len(self.modules), self.builder.MODULE_FILE_COUNT)
        self.assertEqual(
            self.builder.relative_directory_count(self.modules),
            self.builder.MODULE_DIRECTORY_COUNT,
        )
        self.assertEqual(
            sum(name.endswith(".ko") for name in self.modules), 1_276
        )

    def test_package_rejects_wrong_pinned_identity(self) -> None:
        cache = REPO / "mainline/out/.cache"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            changed = Path(temporary) / "changed.tar.gz"
            changed.write_bytes(b"not the canonical package")
            with self.assertRaises(self.builder.BuildError):
                with mock.patch.object(
                    self.builder, "PACKAGE_SIZE", changed.stat().st_size
                ):
                    self.builder.read_package(changed)

    def test_source_manifest_validator_rejects_unrelated_shape(self) -> None:
        with self.assertRaises(self.builder.BuildError):
            self.builder.validate_source_manifest({"format_version": 1})

    def test_payload_binds_exact_module_tree_and_state(self) -> None:
        prefix = f"modules/{self.builder.CANDIDATE_RELEASE}/"
        payload_modules = {
            name[len(prefix) :]: value
            for name, value in self.files.items()
            if name.startswith(prefix)
        }
        self.assertEqual(payload_modules, self.modules)
        self.assertEqual(
            self.files["MODULE-SHA256SUMS"],
            self.builder.module_checksum_manifest(self.modules),
        )
        state = self.builder.parse_checksum_manifest(
            self.files["STATE-SHA256SUMS"]
        )
        self.assertEqual(
            set(state),
            {
                "IMAGE.GZ",
                "MODULE-SHA256SUMS",
                "R46H.DTB",
                "RECEIPT",
                "REMOVE.sh",
                "UBOOT-CMDS.txt",
            },
        )
        self.assertEqual(state["REMOVE.sh"], self.builder.sha256_bytes(self.files["remove.sh"]))

    def test_uboot_transcript_is_p2_only_size_guarded_and_nonpersistent(self) -> None:
        text = self.files["UBOOT-CMDS.txt"].decode()
        self.assertIn("ext4load mmc 1:2", text)
        self.assertIn(self.builder.TARGET_DIRECTORY + "/IMAGE.GZ", text)
        self.assertIn(self.builder.TARGET_DIRECTORY + "/R46H.DTB", text)
        self.assertIn(f"-eq {len(self.files['IMAGE.GZ']):#x}", text)
        self.assertIn(f"-eq {self.builder.IMAGE_SIZE:#x}", text)
        self.assertIn(f"-eq {self.builder.DTB_SIZE:#x}", text)
        self.assertIn("rootwait rw fsck.repair=yes", text)
        self.assertNotIn("mmc 1:1", text)
        self.assertNotIn("fatload", text)
        self.assertNotIn("saveenv", text)
        self.assertNotIn("boot.ini", text)

    def test_install_and_remove_are_syntax_checked_and_guarded(self) -> None:
        install = self.files["install.sh"].decode()
        remove = self.files["remove.sh"].decode()
        for text in (install, remove):
            result = subprocess.run(
                ["/bin/bash", "-n"],
                input=text,
                text=True,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(self.builder.RUNNING_RELEASE, text)
            self.assertIn(self.builder.ROOT_PARTUUID, text)
            self.assertIn(self.builder.BOOT_PARTUUID, text)
            self.assertIn("BOOT partition is mounted writable", text)
            self.assertIn("errors_count", text)
            self.assertNotIn("saveenv", text)
            self.assertNotIn("/boot/", text)
            self.assertNotIn("rm -rf", text)
        self.assertIn("mv -T --no-clobber", install)
        self.assertIn("delete_owned_stage", install)
        self.assertIn("stat -c '%d:%i'", install)
        self.assertIn("target_parent_created", install)
        self.assertIn("candidate module tree already exists", install)
        self.assertIn("insufficient p2 space for guarded staging", install)
        self.assertIn("sha256sum -c --quiet SHA256SUMS", install)
        self.assertIn("active BOOT and environment are unchanged", install)
        self.assertIn("input bridge service is still active", remove)
        self.assertIn("module_tombstone", remove)
        self.assertIn("unexpected installed target member set", remove)

    def test_archive_is_exact_link_free_and_reproducible(self) -> None:
        observed = self.builder.validate_archive_bytes(self.archive)
        self.assertEqual(observed, self.files)
        second = self.builder.deterministic_archive(self.files)
        self.assertEqual(second, self.archive)
        with tarfile.open(fileobj=io.BytesIO(self.archive), mode="r:gz") as archive:
            members = archive.getmembers()
        self.assertTrue(
            all(not member.issym() and not member.islnk() for member in members)
        )
        self.assertTrue(all(member.uid == 0 and member.gid == 0 for member in members))
        self.assertTrue(all(member.mtime == 0 for member in members))
        self.assertEqual(gzip.decompress(self.files["IMAGE.GZ"]), self.image)

        module_root = (
            f"{self.builder.PAYLOAD_DIRECTORY}/modules/"
            f"{self.builder.CANDIDATE_RELEASE}"
        )
        module_directory_count = sum(
            member.isdir()
            and (
                member.name.rstrip("/") == module_root
                or member.name.startswith(module_root + "/")
            )
            for member in members
        )
        self.assertEqual(
            module_directory_count, self.builder.MODULE_DIRECTORY_COUNT
        )
        self.assertIn(
            f"readonly MODULE_DIRECTORY_COUNT={module_directory_count}",
            self.files["install.sh"].decode(),
        )

    def test_runbook_records_physical_failure_and_keeps_evidence_levels_separate(self) -> None:
        text = RUNBOOK_PATH.read_text()
        collapsed = " ".join(text.split())
        self.assertIn("V0.1 physical result: 2026-08-18", text)
        self.assertIn("PHYSICAL FAIL / CLEANLY REMOVED", collapsed)
        self.assertIn("no longer authorizes", collapsed)
        self.assertIn("retry of an unchanged older candidate", collapsed)
        self.assertIn("active BOOT", text)
        self.assertIn("does not", text)
        self.assertIn("physical success", text)


if __name__ == "__main__":
    unittest.main()
