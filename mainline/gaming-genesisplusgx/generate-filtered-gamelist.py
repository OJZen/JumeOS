#!/usr/bin/env python3
"""Select audited Game Gear content and extend the ES-DE media manifest."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
AUDIT = ROOT / "content-audit.json"
MEDIA_GENERATOR_PATH = ROOT.parent / "gaming-es-de/generate-legacy-media-links.py"
SPEC = importlib.util.spec_from_file_location("r46h_es_de_media", MEDIA_GENERATOR_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load the ES-DE media generator")
MEDIA_GENERATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MEDIA_GENERATOR)
HEADER = "# destination-relative-to-downloaded_media\tsource-on-read-only-roms"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_relative(raw: str) -> PurePosixPath:
    value = raw.strip().replace("\\", "/")
    if value.startswith("./"):
        value = value[2:]
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"unsafe relative path: {raw!r}")
    return path


def require_file(path: Path, root: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"unsafe or missing {label}: {path}")
    resolved = path.resolve(strict=True)
    if root not in resolved.parents:
        raise ValueError(f"{label} escapes ROM root: {path}")
    cursor = path
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError(f"symlink in {label} path: {path}")
        cursor = cursor.parent
    return resolved


def write_tree(tree: ET.ElementTree, destination: Path) -> None:
    stage = destination.with_name(f".{destination.name}.tmp-{os.getpid()}")
    try:
        tree.write(stage, encoding="utf-8", xml_declaration=True)
        with stage.open("ab") as handle:
            handle.write(b"\n")
        os.chmod(stage, 0o644)
        os.replace(stage, destination)
    finally:
        stage.unlink(missing_ok=True)


def generate(rom_root: Path, base_media: Path, output_root: Path) -> tuple[int, int, int, int]:
    if rom_root.is_symlink() or not rom_root.is_dir():
        raise ValueError("ROM root must be a real directory")
    rom_root = rom_root.resolve(strict=True)
    gamegear_root = rom_root / "gamegear"
    if gamegear_root.is_symlink() or not gamegear_root.is_dir():
        raise ValueError("Game Gear root must be a real directory")

    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    expected: set[str] = set()
    for entry in audit["content"]:
        relative = safe_relative(entry["path"])
        if relative.parts[0] != "gamegear" or len(relative.parts) != 2:
            raise ValueError(f"invalid audited Game Gear path: {relative}")
        name = relative.parts[1]
        path = require_file(gamegear_root / name, rom_root, "Game Gear content")
        if path.suffix.lower() != ".zip" or entry["result"] != "pass":
            raise ValueError(f"unsupported audited Game Gear content: {name}")
        if path.stat().st_size != entry["size"] or sha256(path) != entry["sha256"]:
            raise ValueError(f"audited Game Gear content changed: {name}")
        if name in expected:
            raise ValueError(f"duplicate audited Game Gear content: {name}")
        expected.add(name)

    source_name = audit["original_gamelist"]["path"].split("/", 1)[1]
    source = require_file(gamegear_root / source_name, rom_root, "Game Gear gamelist")
    if source.stat().st_size != audit["original_gamelist"]["size"] or sha256(source) != audit["original_gamelist"]["sha256"]:
        raise ValueError("Game Gear gamelist changed")
    tree = ET.parse(source)
    root = tree.getroot()
    if root.tag != "gameList":
        raise ValueError("unexpected Game Gear gamelist root")
    retained: set[str] = set()
    for game in list(root.findall("game")):
        name = safe_relative(game.findtext("path") or "").as_posix()
        if name in retained:
            raise ValueError(f"duplicate Game Gear gamelist entry: {name}")
        if name in expected:
            retained.add(name)
        else:
            root.remove(game)
    if retained != expected:
        raise ValueError("Game Gear gamelist and audited content differ")

    if base_media.is_symlink() or not base_media.is_file():
        raise ValueError("base media manifest must be a real file")
    lines = base_media.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != HEADER or lines != sorted(set(lines)):
        raise ValueError("base media manifest is malformed")
    links = dict(line.split("\t", 1) for line in lines[1:])
    original_count = len(links)
    gamegear_links, missing = MEDIA_GENERATOR.generate(rom_root, ("gamegear",))
    for target, source_path in gamegear_links:
        previous = links.setdefault(target, source_path)
        if previous != source_path:
            raise ValueError(f"conflicting media destination: {target}")

    output_root.mkdir(parents=True, exist_ok=True)
    write_tree(tree, output_root / "gamelist.gamegear.xml")
    MEDIA_GENERATOR.write_manifest(output_root / "legacy-media-links.tsv", sorted(links.items()))
    return len(retained), len(links) - original_count, len(links), missing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom-root", type=Path, required=True)
    parser.add_argument("--base-media", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        games, media_delta, media_total, missing = generate(
            args.rom_root, args.base_media, args.output_root
        )
    except (KeyError, OSError, ET.ParseError, ValueError) as error:
        raise SystemExit(f"ERROR: {error}") from error
    print(
        f"R46H_GENESISPLUSGX_GAMELIST result=pass games={games} "
        f"media_delta={media_delta} media_total={media_total} missing={missing}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
