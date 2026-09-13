#!/usr/bin/env python3
"""Generate CPS2/CPS3 gamelists that hide exact failed FBNeo sets."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
AUDIT = ROOT / "content-audit.json"
SYSTEMS = ("cps2", "cps3")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_directory(path: Path, label: str) -> Path:
    if path.is_symlink() or not path.is_dir():
        raise ValueError(f"{label} must be a real directory")
    return path.resolve(strict=True)


def archive_manifest(system_root: Path, rom_root: Path) -> tuple[set[str], str]:
    archives = sorted(system_root.glob("*.zip"))
    lines = []
    for archive in archives:
        if archive.is_symlink() or not archive.is_file():
            raise ValueError(f"unsafe ROM archive: {archive}")
        lines.append(f"{sha256(archive)}  {archive.relative_to(rom_root).as_posix()}\n")
    return {archive.name for archive in archives}, hashlib.sha256(
        "".join(lines).encode()
    ).hexdigest()


def game_filename(game: ET.Element) -> str:
    raw = (game.findtext("path") or "").strip().replace("\\", "/")
    if raw.startswith("./"):
        raw = raw[2:]
    path = PurePosixPath(raw)
    if len(path.parts) != 1 or path.suffix.lower() != ".zip":
        raise ValueError(f"unsafe gamelist path: {raw!r}")
    return path.name


def filtered_tree(
    gamelist: Path, archive_names: set[str], failed: dict[str, str]
) -> ET.ElementTree:
    if gamelist.is_symlink() or not gamelist.is_file():
        raise ValueError(f"unsafe source gamelist: {gamelist}")
    tree = ET.parse(gamelist)
    root = tree.getroot()
    if root.tag != "gameList":
        raise ValueError(f"unexpected gamelist root: {gamelist}")
    games: dict[str, ET.Element] = {}
    for game in root.findall("game"):
        name = game_filename(game)
        if name in games:
            raise ValueError(f"duplicate gamelist entry: {name}")
        if game.find("hidden") is not None:
            raise ValueError(f"source gamelist already hides: {name}")
        games[name] = game
    if set(games) != archive_names or not set(failed) <= archive_names:
        raise ValueError("gamelist, audit and ROM archive sets differ")
    for name in sorted(failed):
        ET.SubElement(games[name], "hidden").text = "true"
    ET.indent(tree, space="  ")
    return tree


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


def generate(rom_root: Path, output_root: Path) -> list[tuple[str, int, int, str]]:
    rom_root = require_directory(rom_root, "ROM root")
    if output_root.exists():
        output_root = require_directory(output_root, "output root")
    else:
        output_root.mkdir(parents=True, mode=0o755)
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    results = []
    for system in SYSTEMS:
        entry = audit["directories"][system]
        system_root = require_directory(rom_root / system, f"{system} root")
        archives, manifest_sha = archive_manifest(system_root, rom_root)
        failed = entry["failed"]
        if (
            len(archives) != entry["archives"]
            or len(archives) - len(failed) != entry["loaded"]
            or manifest_sha != entry["fixture_manifest_sha256"]
        ):
            raise ValueError(f"{system} fixture no longer matches its startup audit")
        for name, digest in failed.items():
            if sha256(system_root / name) != digest:
                raise ValueError(f"{system} failed archive identity mismatch: {name}")
        destination = output_root / f"gamelist.{system}.xml"
        write_tree(
            filtered_tree(system_root / "gamelist.xml", archives, failed), destination
        )
        results.append((system, len(archives), len(failed), sha256(destination)))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        results = generate(args.rom_root, args.output_root)
    except (KeyError, OSError, ET.ParseError, ValueError) as error:
        raise SystemExit(f"ERROR: {error}") from error
    for system, games, hidden, digest in results:
        print(
            f"R46H_FBNEO_GAMELIST result=pass system={system} games={games} "
            f"hidden={hidden} sha256={digest}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
