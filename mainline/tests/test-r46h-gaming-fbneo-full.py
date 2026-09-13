#!/usr/bin/env python3
"""Focused host gates for the full R46H FBNeo core."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
import xml.etree.ElementTree as ET


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "mainline/gaming-fbneo-full"
BUILDER = REPO / "mainline/gaming-ozone-fbneo/build-core.py"
GAMELIST_GENERATOR = ROOT / "generate-filtered-gamelists.py"
GENERATED_CORE = REPO / "mainline/out/r46h-gaming-fbneo-full-v0.1/fbneo_libretro.so"
ROMS = REPO / "mainline/out/.cache/r46h-original-card-import-20260826/easyroms"

SPEC = importlib.util.spec_from_file_location("r46h_fbneo_builder", BUILDER)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load FBNeo builder")
BUILDER_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER_MODULE)

GAMELIST_SPEC = importlib.util.spec_from_file_location(
    "r46h_fbneo_gamelist_generator", GAMELIST_GENERATOR
)
if GAMELIST_SPEC is None or GAMELIST_SPEC.loader is None:
    raise RuntimeError("cannot load FBNeo gamelist generator")
GAMELIST_MODULE = importlib.util.module_from_spec(GAMELIST_SPEC)
GAMELIST_SPEC.loader.exec_module(GAMELIST_MODULE)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FullFBNeoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lock = json.loads((ROOT / "source-lock.json").read_text(encoding="utf-8"))
        cls.audit = json.loads((ROOT / "content-audit.json").read_text(encoding="utf-8"))

    def test_exact_source_build_and_artifact_identity(self) -> None:
        self.assertEqual(self.lock["schema_version"], 1)
        self.assertEqual(
            self.lock["source"]["commit"],
            "26f11fa9e43227a04953e20e8c7e4bf322cd53cb",
        )
        self.assertEqual(
            self.lock["source"]["tree"],
            "b39288c23cadb273a1f02a558687ce5cc6952241",
        )
        self.assertEqual(self.lock["build"]["make_arguments"], ["REGEN_HEADERS=1"])
        self.assertEqual(
            self.lock["build"]["container_image_id"],
            "sha256:3686fd20408cf746c1171e9345fd6c842a71f87e589f691b2455435b3bdd141a",
        )
        self.assertEqual(self.lock["artifact"]["name"], "fbneo_libretro.so")
        self.assertEqual(self.lock["artifact"]["size"], 79683320)
        self.assertEqual(
            self.lock["artifact"]["sha256"],
            "d63bc891a85599949b99748aa5dcd79aed86c29dc859739a9bfe4e1361c02956",
        )

    def test_alternate_lock_cannot_overwrite_subset_default(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(BUILDER), "validate", "--lock", str(ROOT / "source-lock.json")],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("--output is required with an alternate --lock", completed.stderr)

    def test_python39_archive_guard_rejects_traversal(self) -> None:
        member = tarfile.TarInfo("../escape")
        with self.assertRaisesRegex(SystemExit, "unsafe source archive member"):
            BUILDER_MODULE.extractable_archive_members([member])

    def test_python39_archive_guard_omits_links(self) -> None:
        member = tarfile.TarInfo("source/link")
        member.type = tarfile.SYMTYPE
        member.linkname = "../../escape"
        self.assertEqual(BUILDER_MODULE.extractable_archive_members([member]), [])

    def test_generated_core_matches_lock_when_present(self) -> None:
        if not GENERATED_CORE.exists():
            self.skipTest("generated full FBNeo core is unavailable")
        self.assertEqual(GENERATED_CORE.stat().st_size, self.lock["artifact"]["size"])
        self.assertEqual(sha256(GENERATED_CORE), self.lock["artifact"]["sha256"])
        self.assertEqual(GENERATED_CORE.read_bytes()[:4], b"\x7fELF")

    def test_es_de_system_fragments_are_bounded(self) -> None:
        for name in ("arcade", "cps1"):
            with self.subTest(name=name):
                system = ET.parse(ROOT / f"es-system.{name}.xml").getroot()
                self.assertEqual(system.tag, "system")
                self.assertEqual(system.findtext("name"), name)
                self.assertEqual(system.findtext("path"), f"%ROMPATH%/{name}")
                self.assertIn(
                    "/usr/local/libexec/fbneo_libretro.so",
                    system.findtext("command", ""),
                )
                self.assertEqual(
                    (ROOT / f"system-link.{name}.tsv").read_text(encoding="utf-8"),
                    f"{name}\t/roms/{name}\n",
                )

        fragment = ET.fromstring(
            "<systemList>"
            + (ROOT / "es-systems.cps23.xml").read_text(encoding="utf-8")
            + "</systemList>"
        )
        self.assertEqual([node.findtext("name") for node in fragment], ["cps2", "cps3"])
        for node in fragment:
            name = node.findtext("name")
            self.assertEqual(node.findtext("path"), f"%ROMPATH%/{name}")
            self.assertIn("/usr/local/libexec/fbneo_libretro.so", node.findtext("command", ""))
        self.assertEqual(
            (ROOT / "system-links.cps23.tsv").read_text(encoding="utf-8"),
            "cps2\t/roms/cps2\ncps3\t/roms/cps3\n",
        )

    def test_full_directory_audit_is_exact(self) -> None:
        self.assertEqual(self.audit["schema_version"], 1)
        self.assertEqual(self.audit["core_sha256"], self.lock["artifact"]["sha256"])
        expected = {"cps1": (48, 48, 0), "cps2": (62, 57, 5), "cps3": (12, 9, 3)}
        for name, (archives, loaded, failed) in expected.items():
            entry = self.audit["directories"][name]
            with self.subTest(name=name):
                self.assertEqual(entry["archives"], archives)
                self.assertEqual(entry["loaded"], loaded)
                self.assertEqual(len(entry["failed"]), failed)

    @unittest.skipUnless(ROMS.is_dir(), "retained original-card ROM fixture is unavailable")
    def test_full_directory_fixture_manifests_are_exact(self) -> None:
        for name, entry in self.audit["directories"].items():
            lines = []
            for path in sorted((ROMS / name).glob("*.zip")):
                lines.append(f"{sha256(path)}  {path.relative_to(ROMS).as_posix()}\n")
                if path.name in entry["failed"]:
                    self.assertEqual(sha256(path), entry["failed"][path.name])
            manifest = "".join(lines).encode()
            with self.subTest(name=name):
                self.assertEqual(len(lines), entry["archives"])
                self.assertEqual(
                    hashlib.sha256(manifest).hexdigest(),
                    entry["fixture_manifest_sha256"],
                )

    @unittest.skipUnless(ROMS.is_dir(), "retained original-card ROM fixture is unavailable")
    def test_filtered_gamelists_hide_only_failed_sets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            results = GAMELIST_MODULE.generate(ROMS, Path(temporary))
            self.assertEqual(
                results,
                [
                    (
                        "cps2",
                        62,
                        5,
                        "a9d78da1e7e780e4a7f73ecd302b79efd381b15fc1a05d23f824ccd27a3daed8",
                    ),
                    (
                        "cps3",
                        12,
                        3,
                        "9b7bad4b8f955a56cdf405c087222772824358f6a83d58f572fd36152830d45e",
                    ),
                ],
            )
            for system, games, _hidden, _sha in results:
                root = ET.parse(Path(temporary) / f"gamelist.{system}.xml").getroot()
                entries = {GAMELIST_MODULE.game_filename(game): game for game in root}
                self.assertEqual(len(entries), games)
                self.assertEqual(
                    {name for name, game in entries.items() if game.findtext("hidden") == "true"},
                    set(self.audit["directories"][system]["failed"]),
                )

    @unittest.skipUnless(ROMS.is_dir(), "retained original-card ROM fixture is unavailable")
    def test_exact_representative_content_boundaries(self) -> None:
        expected = {
            "arcade/1941.zip": "8e562cacceea51597e1e05eb5af4abdd75c880ce1b171b0f61180b673d2f52cc",
            "arcade/1944.zip": "9186f400aa9cfcdf2720c16bf9801da0e782c5ca6e4bfcdac70c3dc30bbe508d",
            "arcade/avsp.zip": "a730bfe75175ce6f12e19a9e7b6e246a37386e173967d38d41a473ff915de6e3",
            "arcade/bublbobl.zip": "8c5a428bb15204c0fcd71665461e2cddc6d620599e05c4868e463aeaa6702e48",
            "arcade/ddonpach.zip": "362815809c70e8f1956d1ea3ce9d2da62b7cacb056f62be59e211bbb77f2c8a0",
            "arcade/ddtod.zip": "c2d3180ec85d64a8ffce9f2dbcae374f9c02e57d32eb6dddf02911b95c674e2c",
            "arcade/dino.zip": "3d3ca06e7966f1889f5a7066e2b01f23854787e1b3d9b47fdca48661909692b7",
            "arcade/mvsc.zip": "4fa282121abe3d593caa9fe79ae9934b30e754026b6c9e3a2f14cabe9eb3b55c",
            "arcade/sf2.zip": "a1fd7b047d2fc8a54f12050dce9474a6503d63ab111178ca28a2532a9496dddf",
            "arcade/tmnt.zip": "a9594936dd4014c46b259999cc819cce8de32afb5fb6fe4a2611d5e7027b38bf",
            "arcade/xmen.zip": "bcf803883289689831483cf6a3ab2c6b6ac00ca148f1e13411987f1690a8f332",
            "cps3/sfiii3.zip": "8b9a0002654f289e37f58c3e26bb4111fde105e75a0834c80fa2e660f4b116d8",
            "cps3/redearth.zip": "26beb691702dc9b31303a9bc021dfe4421a064b4a15bf7a421c37459717856f4",
            "cps3/jojo.zip": "4edb64dd5c3c0a1503a9ad9077ddb8a8a04a378f5f92bb615172a2fa7194f396",
            "arcade/progear.zip": "17ccd8dc6daa73b4d1765d24a140ec740c559faa58bc1c3e346d92d72cc231e0",
            "cps2/1944.zip": "c654a6b850d594c6c22913b8d884123f7f4c9dce31e7de1ee98c7cf703b90818",
        }
        for relative, digest in expected.items():
            with self.subTest(relative=relative):
                self.assertEqual(sha256(ROMS / relative), digest)

    def test_source_tree_contains_no_rom_or_core(self) -> None:
        self.assertEqual(list(ROOT.rglob("*.zip")), [])
        self.assertEqual(list(ROOT.rglob("*.so")), [])


if __name__ == "__main__":
    unittest.main()
