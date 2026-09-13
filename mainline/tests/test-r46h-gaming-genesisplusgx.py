#!/usr/bin/env python3
"""Focused host contracts for the R46H Genesis Plus GX candidate."""

from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
import xml.etree.ElementTree as ET


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "mainline/gaming-genesisplusgx"
CACHE = REPO / "mainline/out/.cache/r46h-genesisplusgx"
ROMS = REPO / "mainline/out/.cache/r46h-original-card-import-20260826/easyroms"
BASE_MEDIA = REPO / "mainline/out/r46h-gaming-flycast-content-v0.1/legacy-media-links.tsv"
OUTPUT = REPO / "mainline/out/r46h-gaming-genesisplusgx-content-v0.1"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


GENERATOR = load_module("r46h_genesisplusgx_gamelist", ROOT / "generate-filtered-gamelist.py")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class GenesisPlusGxCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lock = json.loads((ROOT / "package-lock.json").read_text(encoding="utf-8"))
        cls.audit = json.loads((ROOT / "content-audit.json").read_text(encoding="utf-8"))

    def test_exact_debian_package_core_and_license(self) -> None:
        package = CACHE / self.lock["package"]["name"]
        core = CACHE / "extracted" / self.lock["core"]["package_path"]
        copyright_file = CACHE / "extracted" / self.lock["copyright"]["package_path"]
        for path, record in (
            (package, self.lock["package"]),
            (core, self.lock["core"]),
            (copyright_file, self.lock["copyright"]),
        ):
            self.assertTrue(path.is_file())
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.stat().st_size, record["size"])
            self.assertEqual(sha256(path), record["sha256"])
        self.assertEqual(self.lock["source"]["version"], "1.7.4+git20221128-2")
        self.assertEqual(self.lock["source"]["architecture"], "arm64")
        self.assertEqual(self.lock["source"]["section"], "non-free/games")
        self.assertFalse(self.lock["license"]["commercial_redistribution"])
        self.assertEqual(self.lock["runtime"]["mandatory_gamegear_firmware"], [])

    def test_all_imported_gamegear_content_passed_exact_host_startup(self) -> None:
        content = self.audit["content"]
        self.assertEqual(len(content), 105)
        self.assertEqual([item["path"] for item in content], [f"gamegear/{i:03}.zip" for i in range(1, 106)])
        self.assertEqual({item["result"] for item in content}, {"pass"})
        self.assertEqual(sum(item["size"] for item in content), 21_796_066)
        self.assertEqual(Counter(item["geometry"] for item in content), {"160x144": 103, "256x192": 2})
        self.assertEqual(self.audit["runtime"]["frames_per_content"], 60)
        self.assertEqual(self.audit["runtime"]["mandatory_firmware"], [])

    def test_original_gamelist_identity_and_generated_successor(self) -> None:
        source = ROMS / self.audit["original_gamelist"]["path"]
        self.assertEqual(source.stat().st_size, self.audit["original_gamelist"]["size"])
        self.assertEqual(sha256(source), self.audit["original_gamelist"]["sha256"])
        with tempfile.TemporaryDirectory() as temporary:
            result = GENERATOR.generate(ROMS, BASE_MEDIA, Path(temporary))
            self.assertEqual(result, (105, 105, 6220, 105))
            for name in ("gamelist.gamegear.xml", "legacy-media-links.tsv"):
                self.assertEqual((Path(temporary) / name).read_bytes(), (OUTPUT / name).read_bytes())

    def test_gamelist_and_media_are_bounded_to_the_audited_set(self) -> None:
        root = ET.parse(OUTPUT / "gamelist.gamegear.xml").getroot()
        paths = [(game.findtext("path") or "").removeprefix("./") for game in root.findall("game")]
        self.assertEqual(set(paths), {f"{i:03}.zip" for i in range(1, 106)})
        self.assertEqual(len(paths), 105)
        lines = (OUTPUT / "legacy-media-links.tsv").read_text(encoding="utf-8").splitlines()
        gamegear = [line for line in lines if line.startswith("gamegear/")]
        self.assertEqual(len(lines), 6221)
        self.assertEqual(len(gamegear), 105)
        self.assertTrue(all("/miximages/" in line and line.endswith(".jpg") for line in gamegear))
        self.assertEqual(lines, sorted(set(lines)))

    def test_es_de_system_and_link_are_minimal(self) -> None:
        fragment = (ROOT / "es-system.gamegear.xml").read_text(encoding="utf-8")
        system = ET.fromstring(f"<systemList>{fragment}</systemList>").find("system")
        assert system is not None
        self.assertEqual(system.findtext("name"), "gamegear")
        self.assertEqual(system.findtext("path"), "%ROMPATH%/gamegear")
        self.assertIn("genesis_plus_gx_libretro.so", system.findtext("command") or "")
        self.assertEqual((ROOT / "system-link.gamegear.tsv").read_text(), "gamegear\t/roms/gamegear\n")
        script = ROOT / "generate-filtered-gamelist.py"
        self.assertEqual(stat.S_IMODE(script.stat().st_mode), 0o755)
        compile(script.read_text(encoding="utf-8"), str(script), "exec")


if __name__ == "__main__":
    unittest.main()
