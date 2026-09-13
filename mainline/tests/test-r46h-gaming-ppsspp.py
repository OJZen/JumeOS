#!/usr/bin/env python3
"""Focused host contracts for the R46H PPSSPP candidate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "mainline/gaming-ppsspp"
ARTIFACT = REPO / "mainline/out/r46h-gaming-ppsspp-v0.1/r46h-ppsspp-libretro-v1.20.4.tar.gz"
ROMS = REPO / "mainline/out/.cache/r46h-original-card-import-20260826/easyroms"
CONTENT_OUTPUT = REPO / "mainline/out/r46h-gaming-ppsspp-content-v0.1"
BASE_MEDIA = REPO / "mainline/out/r46h-gaming-es-de-media-v0.2/legacy-media-links.tsv"

SPEC = importlib.util.spec_from_file_location("r46h_ppsspp_builder", ROOT / "build-core.py")
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load PPSSPP builder")
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)

GENERATOR_SPEC = importlib.util.spec_from_file_location(
    "r46h_ppsspp_gamelist", ROOT / "generate-filtered-gamelist.py"
)
if GENERATOR_SPEC is None or GENERATOR_SPEC.loader is None:
    raise RuntimeError("cannot load PPSSPP gamelist generator")
GENERATOR = importlib.util.module_from_spec(GENERATOR_SPEC)
GENERATOR_SPEC.loader.exec_module(GENERATOR)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PPSSPPCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lock = json.loads((ROOT / "source-lock.json").read_text(encoding="utf-8"))
        cls.audit = json.loads((ROOT / "content-audit.json").read_text(encoding="utf-8"))
        cls.dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        cls.builder_text = (ROOT / "build-core.py").read_text(encoding="utf-8")

    def test_exact_source_build_and_artifact_identity(self) -> None:
        self.assertEqual(self.lock["schema_version"], 1)
        self.assertEqual(self.lock["source"]["tag"], "v1.20.4")
        self.assertEqual(
            self.lock["source"]["commit"],
            "fa50bb1976065c4f8b1b47af227d367fe9771555",
        )
        self.assertEqual(
            self.lock["source"]["tree"],
            "d76acd887f4202ab78bf87cc926c8c9b17e0728c",
        )
        self.assertEqual(len(self.lock["source"]["submodules"]), 29)
        self.assertIn("-DARM_NO_VULKAN=ON", self.lock["build"]["cmake_options"])
        self.assertIn("-DUSING_GLES2=ON", self.lock["build"]["cmake_options"])
        self.assertEqual(self.lock["core"]["size"], 17840344)
        self.assertEqual(
            self.lock["core"]["sha256"],
            "f39819580dc5a867bd8674eef37b13c2eef328824b1aabe7ed4dc98af61bf3a7",
        )
        self.assertEqual(self.lock["artifact"]["size"], 19260809)
        self.assertEqual(
            self.lock["artifact"]["sha256"],
            "8940315762f7abb91624d009f13cddafdb1ab644e41f8e4bf3be70a5a875bc04",
        )

    def test_builder_is_pinned_read_only_and_orders_docker_options(self) -> None:
        self.assertIn("@sha256:bd09bf6d", self.dockerfile)
        for package in (
            "build-essential=12.12",
            "cmake=3.31.6-2",
            "git=1:2.47.3-0+deb13u1",
            "retroarch=1.20.0+dfsg-2+b1",
        ):
            self.assertIn(package, self.dockerfile)
        self.assertNotIn("curl", self.dockerfile)
        self.assertNotIn("wget", self.dockerfile)
        self.assertIn(":/src:ro", self.builder_text)
        command = BUILDER.docker_prefix(
            self.lock,
            "/tmp/source:/src:ro",
            environment=("-e", "HOME=/tmp"),
        )
        self.assertLess(command.index("HOME=/tmp"), command.index(self.lock["build"]["builder_image"]))

    def test_deterministic_archive_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "file").write_bytes(b"r46h\n")
            first, second = root / "first.tar.gz", root / "second.tar.gz"
            BUILDER.write_deterministic_tar(source, first, 123456789)
            BUILDER.write_deterministic_tar(source, second, 123456789)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_locked_artifact_matches_when_present(self) -> None:
        if not ARTIFACT.exists():
            self.skipTest("generated PPSSPP bundle is unavailable")
        self.assertEqual(ARTIFACT.stat().st_size, self.lock["artifact"]["size"])
        self.assertEqual(sha256(ARTIFACT), self.lock["artifact"]["sha256"])

    def test_exact_six_content_startup_boundary(self) -> None:
        self.assertEqual(self.audit["core_sha256"], self.lock["core"]["sha256"])
        self.assertEqual(self.audit["original_gamelist"], {
            "path": "psp/gamelist.xml.old",
            "entries": 27,
            "present": 6,
            "missing": 21,
        })
        self.assertEqual(len(self.audit["content"]), 6)
        self.assertEqual({entry["result"] for entry in self.audit["content"]}, {"pass"})

    @unittest.skipUnless(ROMS.is_dir() and BASE_MEDIA.is_file(), "retained inputs unavailable")
    def test_filtered_gamelist_and_media_are_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            self.assertEqual(GENERATOR.generate(ROMS, BASE_MEDIA, output), (6, 5, 6087))
            gamelist = output / "gamelist.psp.xml"
            media = output / "legacy-media-links.tsv"
            self.assertEqual(sha256(gamelist), "c2f722c494fa623f9b31b7c9a4eab1fa0aca9409262fa82d2631dbc728ed5288")
            self.assertEqual(sha256(media), "5e2e35d671a57c93faefe5715a541b5cda3ffc273458f99e7c35adbb2fa7ecf8")
            self.assertEqual(len(ET.parse(gamelist).getroot().findall("game")), 6)
            self.assertEqual(
                sum(line.startswith("psp/") for line in media.read_text(encoding="utf-8").splitlines()),
                5,
            )

    @unittest.skipUnless(ROMS.is_dir(), "retained original-card ROM fixture is unavailable")
    def test_retained_content_matches_audit(self) -> None:
        for entry in self.audit["content"]:
            path = ROMS / entry["path"]
            with self.subTest(path=entry["path"]):
                self.assertEqual(path.stat().st_size, entry["size"])
                self.assertEqual(sha256(path), entry["sha256"])

    def test_source_tree_contains_no_rom_core_or_font_dump(self) -> None:
        self.assertEqual(list(ROOT.rglob("*.iso")), [])
        self.assertEqual(list(ROOT.rglob("*.cso")), [])
        self.assertEqual(list(ROOT.rglob("*.pbp")), [])
        self.assertEqual(list(ROOT.rglob("*.so")), [])
        self.assertEqual(list(ROOT.rglob("*.pgf")), [])


if __name__ == "__main__":
    unittest.main()
