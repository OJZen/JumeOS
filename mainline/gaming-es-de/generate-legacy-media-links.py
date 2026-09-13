#!/usr/bin/env python3
"""Generate safe p2 symlink mappings for original-card ES media."""

from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import sys
import xml.etree.ElementTree as ET


SYSTEMS = ("nes", "famicom", "gb", "gbc", "gba", "nds", "neogeo")
MEDIA = {"image": "miximages", "marquee": "marquees", "video": "videos"}


def safe_relative(raw: str, *, allow_roms_prefix: bool = False) -> PurePosixPath:
    value = raw.strip().replace("\\", "/")
    if value.startswith("./"):
        value = value[2:]
    if allow_roms_prefix and value.startswith("/roms/"):
        value = value[len("/roms/") :]
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"unsafe relative path: {raw!r}")
    return path


def generate(
    rom_root: Path, systems: tuple[str, ...] = SYSTEMS
) -> tuple[list[tuple[str, str]], int]:
    if rom_root.is_symlink() or not rom_root.is_dir():
        raise ValueError("ROM root must be a real directory")
    root = rom_root.resolve(strict=True)
    links: dict[str, str] = {}
    missing = 0
    checked_systems: list[str] = []

    for raw_system in systems:
        system_path = safe_relative(raw_system)
        if len(system_path.parts) != 1:
            raise ValueError(f"unsafe system name: {raw_system!r}")
        system = system_path.parts[0]
        if system in checked_systems:
            raise ValueError(f"duplicate system name: {system}")
        checked_systems.append(system)

    for system in checked_systems:
        system_root = root / system
        gamelist = system_root / "gamelist.xml"
        if not gamelist.is_file() or gamelist.is_symlink():
            continue
        document = ET.parse(gamelist)
        if document.getroot().tag != "gameList":
            raise ValueError(f"unexpected gamelist root: {gamelist}")
        for game in document.getroot().findall("game"):
            path_text = game.findtext("path")
            if not path_text:
                continue
            rom_path = safe_relative(path_text, allow_roms_prefix=True)
            if rom_path.parts[0] == system:
                rom_path = PurePosixPath(*rom_path.parts[1:])
            if not rom_path.parts:
                raise ValueError(f"empty ROM path in {gamelist}")
            rom_stem = rom_path.with_suffix("")

            for xml_name, destination_kind in MEDIA.items():
                media_text = game.findtext(xml_name)
                if not media_text:
                    continue
                media_path = safe_relative(media_text, allow_roms_prefix=True)
                if media_path.parts[0] != system:
                    media_path = PurePosixPath(system) / media_path
                source = root.joinpath(*media_path.parts)
                cursor = source
                while cursor != root:
                    if cursor.is_symlink():
                        raise ValueError(f"unsafe media source: {source}")
                    cursor = cursor.parent
                try:
                    resolved = source.resolve(strict=True)
                except FileNotFoundError:
                    missing += 1
                    continue
                if not resolved.is_file() or root not in resolved.parents:
                    raise ValueError(f"unsafe media source: {source}")
                suffix = resolved.suffix.lower()
                if not suffix or any(character in suffix for character in "\t\n\r/"):
                    raise ValueError(f"unsafe media suffix: {resolved}")
                destination = PurePosixPath(system) / destination_kind / rom_stem.parent / (
                    rom_stem.name + suffix
                )
                destination_text = destination.as_posix()
                source_text = "/roms/" + media_path.as_posix()
                previous = links.setdefault(destination_text, source_text)
                if previous != source_text:
                    raise ValueError(f"conflicting media destination: {destination_text}")

    return sorted(links.items()), missing


def write_manifest(output: Path, links: list[tuple[str, str]]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    try:
        with stage.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write("# destination-relative-to-downloaded_media\tsource-on-read-only-roms\n")
            for destination, source in links:
                handle.write(f"{destination}\t{source}\n")
        os.chmod(stage, 0o644)
        os.replace(stage, output)
    finally:
        stage.unlink(missing_ok=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rom-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--include-system",
        action="append",
        default=[],
        help="append one successor system while preserving the v0.1 defaults",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    systems = SYSTEMS + tuple(args.include_system)
    try:
        links, missing = generate(args.rom_root, systems)
        write_manifest(args.output, links)
    except (OSError, ET.ParseError, ValueError) as error:
        raise SystemExit(f"ERROR: {error}") from error
    print(
        f"R46H_ES_DE_MEDIA result=pass systems={len(systems)} "
        f"links={len(links)} missing={missing} output={args.output.resolve()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
