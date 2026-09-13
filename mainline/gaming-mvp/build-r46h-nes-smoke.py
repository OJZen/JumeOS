#!/usr/bin/env python3
"""Build the deterministic, original R46H NES emulator smoke ROM."""

from __future__ import annotations

import argparse
from pathlib import Path
import stat


ORIGIN = 0xC000
PRG_SIZE = 16 * 1024
CHR_SIZE = 8 * 1024


class Assembler:
    def __init__(self) -> None:
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.fixups: list[tuple[str, int, str]] = []

    @property
    def pc(self) -> int:
        return ORIGIN + len(self.code)

    def label(self, name: str) -> None:
        if name in self.labels:
            raise ValueError(f"duplicate label: {name}")
        self.labels[name] = self.pc

    def emit(self, *values: int) -> None:
        if any(value < 0 or value > 0xFF for value in values):
            raise ValueError("byte outside range")
        self.code.extend(values)

    def absolute(self, opcode: int, label: str) -> None:
        self.emit(opcode, 0, 0)
        self.fixups.append(("absolute", len(self.code) - 2, label))

    def branch(self, opcode: int, label: str) -> None:
        self.emit(opcode, 0)
        self.fixups.append(("relative", len(self.code) - 1, label))

    def finish(self) -> bytes:
        for kind, position, label in self.fixups:
            if label not in self.labels:
                raise ValueError(f"missing label: {label}")
            target = self.labels[label]
            if kind == "absolute":
                self.code[position] = target & 0xFF
                self.code[position + 1] = target >> 8
            else:
                next_pc = ORIGIN + position + 1
                delta = target - next_pc
                if delta < -128 or delta > 127:
                    raise ValueError(f"branch outside range: {label}")
                self.code[position] = delta & 0xFF
        return bytes(self.code)


def build_program() -> tuple[bytes, dict[str, int]]:
    a = Assembler()
    a.label("reset")
    a.emit(0x78, 0xD8)  # SEI; CLD
    a.emit(0xA2, 0x40, 0x8E, 0x17, 0x40)  # disable APU frame IRQ
    a.emit(0xA2, 0xFF, 0x9A, 0xE8)  # stack=$ff, X=0
    a.emit(0x8E, 0x00, 0x20, 0x8E, 0x01, 0x20, 0x8E, 0x10, 0x40)

    for label in ("vblank_one", "vblank_two"):
        a.label(label)
        a.emit(0x2C, 0x02, 0x20)  # BIT $2002
        a.branch(0x10, label)  # BPL

    a.emit(0xA9, 0x00, 0xA2, 0x00)  # LDA #0; LDX #0
    a.label("clear_ram")
    a.emit(0x95, 0x00)
    for page in range(1, 8):
        a.emit(0x9D, 0x00, page)
    a.emit(0xE8)
    a.branch(0xD0, "clear_ram")

    a.emit(0xAD, 0x02, 0x20, 0xA9, 0x3F, 0x8D, 0x06, 0x20)
    a.emit(0xA9, 0x00, 0x8D, 0x06, 0x20, 0xA2, 0x00)
    a.label("palette_loop")
    a.absolute(0xBD, "palette")  # LDA palette,X
    a.emit(0x8D, 0x07, 0x20, 0xE8, 0xE0, 0x20)
    a.branch(0xD0, "palette_loop")

    a.emit(0xAD, 0x02, 0x20, 0xA9, 0x20, 0x8D, 0x06, 0x20)
    a.emit(0xA9, 0x00, 0x8D, 0x06, 0x20)
    a.emit(0xA0, 0x03, 0xA9, 0x01, 0xA2, 0x00)
    a.label("name_page")
    a.emit(0x8D, 0x07, 0x20, 0xE8)
    a.branch(0xD0, "name_page")
    a.emit(0x88)
    a.branch(0xD0, "name_page")
    a.emit(0xA2, 0x00)
    a.label("name_tail")
    a.emit(0x8D, 0x07, 0x20, 0xE8, 0xE0, 0xC0)
    a.branch(0xD0, "name_tail")
    a.emit(0xA9, 0x00, 0xA2, 0x00)
    a.label("attribute_loop")
    a.emit(0x8D, 0x07, 0x20, 0xE8, 0xE0, 0x40)
    a.branch(0xD0, "attribute_loop")

    # Sprite 0 is a movable square. All other sprites are hidden below screen.
    for value, address in ((0x70, 0x0200), (0x02, 0x0201), (0x00, 0x0202), (0x78, 0x0203)):
        a.emit(0xA9, value, 0x8D, address & 0xFF, address >> 8)
    a.emit(0xA9, 0xFF, 0xA2, 0x04)
    a.label("hide_sprites")
    a.emit(0x9D, 0x00, 0x02, 0xE8, 0xE8, 0xE8, 0xE8)
    a.branch(0xD0, "hide_sprites")

    a.emit(0xA9, 0x00, 0x8D, 0x05, 0x20, 0x8D, 0x05, 0x20)
    a.emit(0xA9, 0x80, 0x8D, 0x00, 0x20)
    a.emit(0xA9, 0x1E, 0x8D, 0x01, 0x20)
    a.label("forever")
    a.absolute(0x4C, "forever")

    a.label("nmi")
    a.emit(0x48, 0x8A, 0x48, 0x98, 0x48)  # save A/X/Y
    a.emit(0xA9, 0x01, 0x8D, 0x16, 0x40)
    a.emit(0xA9, 0x00, 0x8D, 0x16, 0x40)

    # A toggles a palette colour on each new press.
    a.emit(0xAD, 0x16, 0x40, 0x29, 0x01)
    a.branch(0xF0, "a_released")
    a.emit(0xA5, 0x01)
    a.branch(0xD0, "a_done")
    a.emit(0xA9, 0x01, 0x85, 0x01, 0xA5, 0x00, 0x49, 0x01, 0x85, 0x00, 0xAA)
    a.emit(0xAD, 0x02, 0x20, 0xA9, 0x3F, 0x8D, 0x06, 0x20)
    a.emit(0xA9, 0x01, 0x8D, 0x06, 0x20)
    a.absolute(0xBD, "toggle_colors")
    a.emit(0x8D, 0x07, 0x20)
    a.absolute(0x4C, "a_done")
    a.label("a_released")
    a.emit(0x85, 0x01)
    a.label("a_done")

    # Discard B, Select and Start, then move on D-pad presses.
    a.emit(0xAD, 0x16, 0x40, 0xAD, 0x16, 0x40, 0xAD, 0x16, 0x40)
    for label, opcode, address in (
        ("up_done", 0xCE, 0x0200),
        ("down_done", 0xEE, 0x0200),
        ("left_done", 0xCE, 0x0203),
        ("right_done", 0xEE, 0x0203),
    ):
        a.emit(0xAD, 0x16, 0x40, 0x29, 0x01)
        a.branch(0xF0, label)
        a.emit(opcode, address & 0xFF, address >> 8)
        a.label(label)

    a.emit(0xA9, 0x00, 0x8D, 0x03, 0x20)
    a.emit(0xA9, 0x02, 0x8D, 0x14, 0x40)
    a.emit(0xA9, 0x00, 0x8D, 0x05, 0x20, 0x8D, 0x05, 0x20)
    a.emit(0x68, 0xA8, 0x68, 0xAA, 0x68, 0x40)  # restore Y/X/A; RTI

    a.label("irq")
    a.emit(0x40)
    a.label("palette")
    a.emit(
        0x0F, 0x21, 0x11, 0x30, 0x0F, 0x16, 0x27, 0x30,
        0x0F, 0x06, 0x17, 0x28, 0x0F, 0x09, 0x19, 0x29,
        0x0F, 0x30, 0x27, 0x16, 0x0F, 0x30, 0x21, 0x11,
        0x0F, 0x30, 0x28, 0x18, 0x0F, 0x30, 0x2A, 0x1A,
    )
    a.label("toggle_colors")
    a.emit(0x21, 0x16)
    return a.finish(), a.labels


def build_rom() -> bytes:
    program, labels = build_program()
    if len(program) >= PRG_SIZE - 6:
        raise ValueError("program is too large")
    prg = bytearray(PRG_SIZE)
    prg[: len(program)] = program
    for offset, name in ((0x3FFA, "nmi"), (0x3FFC, "reset"), (0x3FFE, "irq")):
        address = labels[name]
        prg[offset] = address & 0xFF
        prg[offset + 1] = address >> 8

    chr_rom = bytearray(CHR_SIZE)
    chr_rom[16:24] = bytes((0xAA, 0x55) * 4)  # tile 1 checkerboard
    chr_rom[24:32] = b"\x00" * 8
    chr_rom[32:40] = b"\xff" * 8  # tile 2 solid sprite square
    chr_rom[40:48] = b"\x00" * 8
    header = b"NES\x1a" + bytes((1, 1, 0, 0)) + b"\x00" * 8
    return header + prg + chr_rom


def write_new(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = path.open("xb")
    except FileExistsError as error:
        raise ValueError(f"output already exists: {path}") from error
    with descriptor:
        descriptor.write(data)
        descriptor.flush()
    path.chmod(0o644)
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise ValueError("unsafe published ROM")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    write_new(args.output, build_rom())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
