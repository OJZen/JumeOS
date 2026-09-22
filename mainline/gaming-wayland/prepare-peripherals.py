#!/usr/bin/env python3
"""Fetch/hash-check the small Debian Foot + USB pointer cursor runtime."""
import argparse
import hashlib
from pathlib import Path
import urllib.request

# Versions and digests from Debian's signed trixie package index.
PACKAGES = {
    'foot_1.21.0-2_arm64.deb': ('f/foot', 283912, '73603c2339f0a344f0c3f0a6586246219d15bb49665a28c8a09ce7cc5264f7cc'),
    'libfcft4t64_3.3.1-1_arm64.deb': ('f/fcft', 58128, '6b8024711d73411b4766ab42c715584e548372f67fb90c8e53a017cd72272e8f'),
    'libutf8proc3_2.9.0-1+b2_arm64.deb': ('u/utf8proc', 60960, 'bc3890f70b603cbcc0c13df9edea5110bc50904569acb7652aa425ed3038d0a0'),
    'ncurses-term_6.5+20250216-2_all.deb': ('n/ncurses', 517504, 'bd6104ab13bd008b4bd5aaf8740fd9f5168ca5199a72fe1c3e984fe49286fbb6'),
    'dmz-cursor-theme_0.4.5.2_all.deb': ('d/dmz-cursor-theme', 191584, '4dbbd42fdc3ec30be725b6994b0b428e69c575e01811f051851df679da3b6dfe'),
    'fonts-dejavu-mono_2.37-8_all.deb': ('f/fonts-dejavu', 488808, '3003e98a5debfdeadc7040a7f715fe9fe6fb67f68deacf6049b54e30f07fc014'),
}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if not args.output.is_absolute() or args.output.is_symlink():
        parser.error('Use an absolute external cache directory')
    args.output.mkdir(parents=True, exist_ok=True)
    for name, (pool, size, digest) in PACKAGES.items():
        path = args.output / name
        if not path.exists() and not args.check:
            with urllib.request.urlopen(f'https://deb.debian.org/debian/pool/main/{pool}/{name}', timeout=30) as response:
                data = response.read(size + 1)
            if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
                raise ValueError('Downloaded package digest mismatch: ' + name)
            temporary = path.with_suffix('.incoming'); temporary.write_bytes(data); temporary.replace(path)
        if path.is_symlink() or not path.is_file() or path.stat().st_size != size or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Invalid peripheral package: ' + name)
    print('PERIPHERAL_PACKAGES_VERIFIED', len(PACKAGES))
