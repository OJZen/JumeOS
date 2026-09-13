#!/usr/bin/env python3
"""Fetch pinned Debian audio libraries and the private Python interpreter."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

PACKAGES = {
    'libopenal1.deb': ('openal-soft/libopenal1_1.24.2-1_arm64.deb', 577344, '2431891da0bce880529768817087a7789000f07d24e201f13ff07a1ace9b40b5'),
    'libmpg123.deb': ('mpg123/libmpg123-0t64_1.32.10-1+deb13u1_arm64.deb', 143208, 'd284df39ff3b64f1cdf274352613c52534c55eed82c3a2ff0fc7ba154acd7bf0'),
    'python3.13-minimal.deb': ('python3.13/python3.13-minimal_3.13.5-2+deb13u3_arm64.deb', 2002540, 'd64a87f3dc9b3b52567cda12096312767b19f8f3995d4051f79a2435d3d994de'),
    'libpython3.13-minimal.deb': ('python3.13/libpython3.13-minimal_3.13.5-2+deb13u3_arm64.deb', 856300, 'c5210fcdcbf293d7ccdb1a0ebb33fad11c87d027af89e6f5bb8cd62ed001defe'),
    'libpython3.13-stdlib.deb': ('python3.13/libpython3.13-stdlib_3.13.5-2+deb13u3_arm64.deb', 1892732, '88f3f041436676c627672955f39269abff8168196546fc65130aa31165c03981'),
}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if not args.output.is_absolute() or args.output.is_symlink():
        parser.error('Use an absolute external cache directory')
    args.output.mkdir(parents=True, exist_ok=True)
    for name, (relative, size, expected) in PACKAGES.items():
        path = args.output / name
        if not path.exists() and not args.check:
            source_name = relative.split('/')[0]
            url = 'https://deb.debian.org/debian/pool/main/' + source_name[0] + '/' + relative
            with urllib.request.urlopen(url, timeout=30) as response:
                data = response.read(size + 1)
            if len(data) != size or hashlib.sha256(data).hexdigest() != expected:
                raise ValueError('Native package digest mismatch: ' + name)
            temporary = path.with_suffix('.incoming')
            temporary.write_bytes(data)
            temporary.replace(path)
        if path.is_symlink() or path.stat().st_size != size or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Invalid native library package: ' + name)
    print(json.dumps({'status': 'PORT_NATIVE_LIBRARIES_VERIFIED', 'packages': list(PACKAGES)}))
