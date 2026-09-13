#!/usr/bin/env python3
"""Focused host contracts for the R46H Flycast candidate."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "mainline/gaming-flycast"
ARTIFACT = REPO / "mainline/out/r46h-gaming-flycast-v0.1/r46h-flycast-libretro-v2.6.tar.gz"
ROMS = REPO / "mainline/out/.cache/r46h-original-card-import-20260826/easyroms"
BASE_MEDIA = REPO / "mainline/out/r46h-gaming-ppsspp-content-v0.1/legacy-media-links.tsv"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILDER = load_module("r46h_flycast_builder", ROOT / "build-core.py")
GENERATOR = load_module("r46h_flycast_gamelist", ROOT / "generate-filtered-gamelist.py")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FlycastCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lock = json.loads((ROOT / "source-lock.json").read_text(encoding="utf-8"))
        cls.audit = json.loads((ROOT / "content-audit.json").read_text(encoding="utf-8"))
        cls.builder_text = (ROOT / "build-core.py").read_text(encoding="utf-8")

    def test_exact_source_build_and_artifact_identity(self) -> None:
        self.assertEqual(self.lock["schema_version"], 1)
        self.assertEqual(self.lock["source"]["tag"], "v2.6")
        self.assertEqual(
            self.lock["source"]["commit"],
            "392a429e8b040b3e5bf6696cb4f984274fc44123",
        )
        self.assertEqual(
            self.lock["source"]["tree"],
            "712e00d5a9c99abc949bcce2bf02800492de869d",
        )
        self.assertEqual(
            self.lock["source"]["submodules"],
            {
                "core/deps/asio": "d3402006e84efb6114ff93e4f2b8508412ed80d5",
                "core/deps/libchdr": "5f82799f2c8cad1e9cd26d39a0f8d36369a5534b",
            },
        )
        self.assertIn("-DUSE_GLES2=ON", self.lock["build"]["cmake_options"])
        self.assertIn("-DUSE_VULKAN=OFF", self.lock["build"]["cmake_options"])
        self.assertEqual(self.lock["core"]["size"], 32_646_000)
        self.assertEqual(
            self.lock["core"]["sha256"],
            "1de0ebcad7de5906b2e03e3b7885254635399503969b5e1c8b21c8ef79c07eaf",
        )
        self.assertEqual(self.lock["artifact"]["size"], 4_115_189)
        self.assertEqual(
            self.lock["artifact"]["sha256"],
            "2e526c2533cf9e9ac79e210226c1a5e96990b9f6463317d747175604b8280861",
        )

    def test_build_reuses_pinned_builder_and_copies_mutable_source(self) -> None:
        recipe = REPO / self.lock["build"]["builder_recipe"]
        self.assertEqual(sha256(recipe), self.lock["build"]["builder_recipe_sha256"])
        self.assertIn("shutil.copytree(source, scratch", self.builder_text)
        self.assertIn('f"{scratch.resolve()}:/src"', self.builder_text)
        self.assertNotIn('f"{SOURCE_DIR.resolve()}:/src"', self.builder_text)

    def test_deterministic_archive_writer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "file").write_bytes(b"r46h\n")
            first, second = root / "first.tar.gz", root / "second.tar.gz"
            BUILDER.COMMON.write_deterministic_tar(source, first, 123456789)
            BUILDER.COMMON.write_deterministic_tar(source, second, 123456789)
            self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_locked_artifact_matches_when_present(self) -> None:
        if not ARTIFACT.exists():
            self.skipTest("generated Flycast bundle is unavailable")
        self.assertEqual(ARTIFACT.stat().st_size, self.lock["artifact"]["size"])
        self.assertEqual(sha256(ARTIFACT), self.lock["artifact"]["sha256"])

    def test_exact_fourteen_content_startup_boundary(self) -> None:
        self.assertEqual(self.audit["core_sha256"], self.lock["core"]["sha256"])
        self.assertEqual(self.audit["runtime"]["frames_per_content"], 120)
        self.assertEqual(self.audit["runtime"]["bios"], "HLE")
        self.assertEqual(len(self.audit["content"]), 14)
        self.assertEqual({entry["result"] for entry in self.audit["content"]}, {"pass"})
        self.assertEqual(
            {Path(entry["path"]).suffix.lower() for entry in self.audit["content"]},
            {".cdi", ".chd"},
        )
        self.assertEqual(
            sum(Path(entry["path"]).suffix.lower() == ".cdi" for entry in self.audit["content"]),
            7,
        )

    @unittest.skipUnless(ROMS.is_dir() and BASE_MEDIA.is_file(), "retained inputs unavailable")
    def test_filtered_gamelist_and_media_are_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            self.assertEqual(GENERATOR.generate(ROMS, BASE_MEDIA, output), (14, 28, 6115))
            gamelist = output / "gamelist.dreamcast.xml"
            media = output / "legacy-media-links.tsv"
            self.assertEqual(
                sha256(gamelist),
                "0099df582b7c4157dfed1ebe9ecf161efc8a3ab799630dc06977adafdffc7927",
            )
            self.assertEqual(
                sha256(media),
                "8b4820cf09a61fdc0fe96c638aad867c2af0013aa3a62187ef161dd54b0e86c1",
            )
            self.assertEqual(len(ET.parse(gamelist).getroot().findall("game")), 14)
            self.assertEqual(
                sum(line.startswith("dreamcast/") for line in media.read_text(encoding="utf-8").splitlines()),
                28,
            )

    def test_seed_is_hle_native_and_keeps_writable_state_off_roms(self) -> None:
        options = (ROOT / "core-options.cfg").read_text(encoding="utf-8")
        self.assertIn('reicast_hle_bios = "enabled"', options)
        self.assertIn('reicast_internal_resolution = "640x480"', options)
        self.assertIn('reicast_per_content_vmus = "VMU A1"', options)
        self.assertNotIn("/roms", options)

    def test_source_tree_contains_no_rom_bios_vmu_or_core(self) -> None:
        for pattern in ("*.cdi", "*.chd", "*.gdi", "dc_boot.bin", "dc_flash.bin", "*.vmu", "*.so"):
            self.assertEqual(list(ROOT.rglob(pattern)), [], pattern)


if __name__ == "__main__":
    unittest.main()
