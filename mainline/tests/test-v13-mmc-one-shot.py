#!/usr/bin/env python3
"""Focused host tests for the R46H v0.13 p2 MMC one-shot payload."""

from __future__ import annotations

import gzip
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock


REPO = Path(__file__).resolve().parents[2]
BUILDER_PATH = REPO / "mainline/scripts/build-v13-mmc-one-shot.py"
RUNBOOK_PATH = REPO / "mainline/bringup-tests/V13-MMC-INIT-ONE-SHOT.md"


def load_builder():
    spec = importlib.util.spec_from_file_location("r46h_v13_one_shot", BUILDER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load v0.13 one-shot builder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class V13MmcOneShotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.builder = load_builder()
        cls.image, cls.dtb = cls.builder.read_package()
        cls.files = cls.builder.payload_files(cls.image, cls.dtb)

    def test_canonical_package_and_payload_identity(self) -> None:
        self.assertEqual(len(self.image), self.builder.IMAGE_SIZE)
        self.assertEqual(
            self.builder.sha256_bytes(self.image), self.builder.IMAGE_SHA256
        )
        self.assertEqual(len(self.dtb), self.builder.DTB_SIZE)
        self.assertEqual(self.files.keys(), self.builder.PAYLOAD_NAMES)
        self.assertEqual(gzip.decompress(self.files["IMAGE.GZ"]), self.image)

    def test_package_rejects_wrong_pinned_identity(self) -> None:
        cache = REPO / "mainline/out/.cache"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as temporary:
            changed = Path(temporary) / "changed.tar.gz"
            changed.write_bytes(b"not the canonical package")
            with self.assertRaises(self.builder.BuildError):
                with mock.patch.object(self.builder, "PACKAGE_SIZE", changed.stat().st_size):
                    self.builder.read_package(changed)

    def test_uboot_transcript_is_p2_only_and_size_guarded(self) -> None:
        text = self.files["UBOOT-CMDS.txt"].decode()
        self.assertIn("ext4load mmc 1:2", text)
        self.assertIn(self.builder.TARGET_DIRECTORY + "/IMAGE.GZ", text)
        self.assertIn(self.builder.TARGET_DIRECTORY + "/R46H.DTB", text)
        self.assertIn(f"-eq {len(self.files['IMAGE.GZ']):#x}", text)
        self.assertIn(f"-eq {self.builder.IMAGE_SIZE:#x}", text)
        self.assertIn(f"-eq {self.builder.DTB_SIZE:#x}", text)
        self.assertIn("rootwait ro rootflags=noload init=/bin/bash", text)
        self.assertNotIn("mmc 1:1", text)
        self.assertNotIn("fatload", text)
        self.assertNotIn("saveenv", text)
        self.assertNotIn("boot.ini", text)

    def test_install_and_remove_are_guarded(self) -> None:
        install = self.files["install.sh"].decode()
        remove = self.files["remove.sh"].decode()
        for text in (install, remove):
            self.assertIn(self.builder.RUNNING_RELEASE, text)
            self.assertIn(self.builder.ROOT_PARTUUID, text)
            self.assertIn(self.builder.BOOT_PARTUUID, text)
            self.assertIn("BOOT partition is mounted writable", text)
            self.assertIn("errors_count", text)
            self.assertNotIn("/boot/", text)
            self.assertNotIn("saveenv", text)
        self.assertIn("mv -T --no-clobber", install)
        self.assertIn("versioned target already exists", install)
        self.assertNotIn("rm -rf", install)
        self.assertIn("unexpected installed member set", remove)
        self.assertIn("rm -f --", remove)
        self.assertNotIn("rm -rf", remove)
        self.assertNotIn("systemctl reboot", remove)

    def test_archive_is_reproducible_exact_and_link_free(self) -> None:
        first = self.builder.deterministic_archive(self.files)
        second = self.builder.deterministic_archive(self.files)
        self.assertEqual(first, second)
        observed = self.builder.validate_archive_bytes(first)
        self.assertEqual(observed, self.files)
        with tarfile.open(fileobj=io.BytesIO(first), mode="r:gz") as archive:
            members = archive.getmembers()
        self.assertTrue(all(not member.issym() and not member.islnk() for member in members))
        self.assertEqual(
            {member.name for member in members},
            {self.builder.PAYLOAD_DIRECTORY}
            | {
                f"{self.builder.PAYLOAD_DIRECTORY}/{name}"
                for name in self.builder.PAYLOAD_NAMES
            },
        )

    def test_checksum_manifest_binds_exact_payload_data(self) -> None:
        expected = "".join(
            f"{self.builder.sha256_bytes(value)}  {name}\n"
            for name, value in sorted(self.files.items())
            if name not in {"PAYLOAD.COMPLETE", "SHA256SUMS"}
        ).encode()
        self.assertEqual(self.files["SHA256SUMS"], expected)
        self.assertEqual(
            self.files["PAYLOAD.COMPLETE"],
            f"sha256sums_sha256={self.builder.sha256_bytes(expected)}\n".encode(),
        )

    def test_runbook_preserves_one_sample_and_evidence_boundaries(self) -> None:
        text = RUNBOOK_PATH.read_text()
        collapsed = " ".join(text.split())
        self.assertIn("one bounded diagnostic", text)
        self.assertIn("do not loop", text)
        self.assertIn("inconclusive diagnostic sample", collapsed)
        self.assertIn("host proof does not become physical proof", collapsed)
        self.assertIn("p1 remains unchanged", text)
        self.assertIn("never use `saveenv`", text)


if __name__ == "__main__":
    unittest.main()
