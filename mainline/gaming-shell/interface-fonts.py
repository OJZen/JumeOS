#!/usr/bin/env python3
"""Fetch, install and verify the Jume UI font: Noto Sans SC Regular/Medium/Bold."""
import argparse
import hashlib
from pathlib import Path
import shutil
import urllib.request

# Region-specific Simplified Chinese subset from notofonts/noto-cjk tag Sans2.004.
# Sizes/blob hashes match the tag's git tree; SHA256 values were computed from those blobs.
SOURCE = 'https://raw.githubusercontent.com/notofonts/noto-cjk/Sans2.004/'
FONTS = {
    'NotoSansSC-Regular.otf': ('Sans/SubsetOTF/SC/', 8331336, 'faa6c9df652116dde789d351359f3d7e5d2285a2b2a1f04a2d7244df706d5ea9'),
    'NotoSansSC-Medium.otf': ('Sans/SubsetOTF/SC/', 8345436, '7633f5a016d4dd95e685a69633d818aabc4644c4b08e26bd35b1b30c45ed5dda'),
    'NotoSansSC-Bold.otf': ('Sans/SubsetOTF/SC/', 8543168, 'c6cb5a93abaa9edc8ee7463b7ebb7f42d618d40e6ed2f7a5371c97b0b64767c0'),
    'LICENSE': ('', 4301, '6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2'),
}
# Package layout; fonts.h loads the same directory relative to usr/bin.
FONT_DIR = 'usr/share/fonts/opentype/noto'
LICENSE_PATH = 'usr/share/doc/fonts-noto-sans-sc/LICENSE'


def valid(path, size, digest):
    return not path.is_symlink() and path.is_file() and path.stat().st_size == size \
        and hashlib.sha256(path.read_bytes()).hexdigest() == digest


def prepare(output, check):
    if not output.is_absolute() or output.is_symlink():
        raise SystemExit('Use an absolute external cache directory')
    output.mkdir(parents=True, exist_ok=True)
    for name, (prefix, size, digest) in FONTS.items():
        path = output / name
        if not path.exists() and not check:
            with urllib.request.urlopen(SOURCE + prefix + name, timeout=60) as response:
                data = response.read(size + 1)
            if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
                raise ValueError('Downloaded font digest mismatch: ' + name)
            temporary = path.with_suffix('.incoming'); temporary.write_bytes(data); temporary.replace(path)
        if not valid(path, size, digest):
            raise ValueError('Invalid interface font: ' + name)
    print('INTERFACE_FONTS_VERIFIED', len(FONTS))


def targets(stage):
    return {name: stage / (LICENSE_PATH if name == 'LICENSE' else f'{FONT_DIR}/{name}') for name in FONTS}


def install(source, stage):
    prepare(source, True)
    for name, target in targets(stage).items():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target); target.chmod(0o644)
    verify(stage)


def verify(stage):
    for name, target in targets(stage).items():
        _, size, digest = FONTS[name]
        if not valid(target, size, digest):
            raise ValueError('Packaged interface font missing or changed: ' + str(target.relative_to(stage)))
    print('PACKAGED_INTERFACE_FONTS_PASS: Noto Sans SC Regular, Medium, Bold and license')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    fetch = commands.add_parser('prepare', help='download or --check the external cache')
    fetch.add_argument('output', type=Path); fetch.add_argument('--check', action='store_true')
    copy = commands.add_parser('install', help='copy verified fonts into a package stage')
    copy.add_argument('source', type=Path); copy.add_argument('stage', type=Path)
    check = commands.add_parser('verify', help='package check: all three weights and the license')
    check.add_argument('stage', type=Path)
    args = parser.parse_args()
    if args.command == 'prepare': prepare(args.output, args.check)
    elif args.command == 'install': install(args.source, args.stage)
    else: verify(args.stage)
