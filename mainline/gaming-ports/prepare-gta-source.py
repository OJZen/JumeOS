#!/usr/bin/env python3
"""Fetch the exact GTA/librw sources and ARM64 build headers."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

INPUTS = {
    're3-ead2747.tar.gz': ('https://codeload.github.com/nosro1/re3/tar.gz/ead2747eadbbdbf0e134eea6679364153dd6c4b8', 10105086, '3b9be667eb7fd9d63ddc9fb1e4a3d868c829b71120d9d870e084cac4f82518fa'),
    'revc-b9f0b23.tar.gz': ('https://codeload.github.com/nosro1/re3/tar.gz/b9f0b23466ab4db76615cc2c761df9013a838184', 9184072, '9ed831bc2942eacf68117df3d6407ca3dc79f2544badf933307b68883824f126'),
    'librw-81c9426.tar.gz': ('https://codeload.github.com/nosro1/librw/tar.gz/81c9426cdde73717b04ae4dfc0f6c255f74a3a8a', 2111720, 'a94faf62cdeed5ef62cc39ff9bb290e0201a8892c205373806376ed788975afe'),
    'libopenal-dev_1%3a1.24.2-1_arm64.deb': ('https://deb.debian.org/debian/pool/main/o/openal-soft/libopenal-dev_1.24.2-1_arm64.deb', 37364, '340b18bce0891f86ef6a5a6b83dc94f3a9570898160b4701174457884948cb63'),
    'libmpg123-dev_1.32.10-1+deb13u1_arm64.deb': ('https://deb.debian.org/debian/pool/main/m/mpg123/libmpg123-dev_1.32.10-1+deb13u1_arm64.deb', 61880, '17a9fce20ce124f47aa38f1c92217e7f2aeaf7629c773b615c17866015aa02b3'),
}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if not args.output.is_absolute() or args.output.is_symlink():
        parser.error('Use an absolute external cache directory')
    args.output.mkdir(parents=True, exist_ok=True)
    for name, (url, size, expected) in INPUTS.items():
        path = args.output / name
        if not path.exists() and not args.check:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = response.read(size + 1)
            if len(data) != size or hashlib.sha256(data).hexdigest() != expected:
                raise ValueError('GTA source input digest mismatch: ' + name)
            incoming = path.with_name(path.name + '.incoming')
            incoming.write_bytes(data)
            incoming.replace(path)
        if path.is_symlink() or not path.is_file() or path.stat().st_size != size or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Invalid GTA source input: ' + name)
    print(json.dumps({'status': 'GTA_SOURCE_INPUTS_VERIFIED', 'inputs': list(INPUTS)}))
