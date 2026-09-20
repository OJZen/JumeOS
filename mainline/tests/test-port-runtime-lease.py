#!/usr/bin/env python3
"""Exercise the real lease script with private files and fake mount/service commands."""
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[2]
source = (repo / 'mainline/gaming-ports/runtime-lease.sh').read_text()
assert '107c61190ac1f8a60cd8a9ef94e7ae4e3f379bd9fca6efdadcb91e55fca55f83' in source
assert 'fe343253440000002000002d57019567' in source
with tempfile.TemporaryDirectory(prefix='port-lease-', dir=repo / 'mainline/out/.cache') as directory:
    root = Path(directory)
    scope = root / 'scope'; scope.mkdir(mode=0o755)
    wayland_scope = root / 'wayland'; wayland_scope.mkdir(mode=0o755)
    record = root / 'record'
    image = root / 'mono.squashfs'; image.write_bytes(b'fixture')
    cid = root / 'cid'; cid.write_text('fe343253440000002000002d57019567')
    size = root / 'size'; size.write_text('122138624')
    script = source.replace('/run/r46h-shell-probe', str(scope)).replace('/run/r46h-port-runtime', str(record))
    script = script.replace('/run/r46h-wayland-probe', str(wayland_scope))
    script = script.replace('/roms/tools/PortMaster/libs/mono-6.12.0.122-aarch64.squashfs', str(image))
    script = script.replace('/sys/class/block/mmcblk0/device/cid', str(cid)).replace('/sys/class/block/mmcblk0/size', str(size))
    script = script.replace('$EUID == 0', f'$EUID == {os.getuid()}').replace('== 0:700', f'== {os.getuid()}:700').replace('== 0:600', f'== {os.getuid()}:600').replace('== 0:755', f'== {os.getuid()}:755')
    script = script.replace('== 262057984', '== 7').replace('107c61190ac1f8a60cd8a9ef94e7ae4e3f379bd9fca6efdadcb91e55fca55f83', hashlib.sha256(b'fixture').hexdigest())
    prefix = r'''
uname() { echo 6.12.99-r46h-mainline-v0.15-gaming-product; }
stat() {
 python3 -c 'import os,stat,sys; s=os.lstat(sys.argv[2]); print(str(s.st_size) if sys.argv[1]=="%s" else str(s.st_uid)+":"+oct(stat.S_IMODE(s.st_mode))[2:])' "$2" "$3"
}
sha256sum() { shasum -a 256 "$@"; }
findmnt() {
 case "$*" in
  *'UUID /') echo "${ROOT_UUID:-d3130017-46a4-4d56-9001-000000000017}";;
  *'OPTIONS /roms') echo ro;;
  *'-o ID') [[ ${MOUNT_ID_ERROR:-0} != 1 ]] || return 1; cat "$FIXTURE/mounted";;
  *'-o OPTIONS') echo ro,nodev,nosuid;;
  *) return 1;;
 esac
}
mount() {
 [[ $1 == -t && $2 == squashfs && $3 == -o && $4 == loop,ro,nodev,nosuid ]] || return 1
 [[ ${MOUNT_ERROR:-0} != 1 ]] || return 1
 mkdir "$target/bin"; touch "$target/bin/mono"; chmod 755 "$target/bin/mono"
 echo 51 > "$FIXTURE/mounted"
}
umount() {
 [[ $1 == "$target" && -f $FIXTURE/mounted ]] || return 1
 rm "$target/bin/mono" "$FIXTURE/mounted"; rmdir "$target/bin"
}
'''
    def run(action, unit='r46h-shell-probe-42.service', **extra):
        return subprocess.run(['bash', '-c', prefix + script, 'lease', action, unit],
                              env={**os.environ, 'FIXTURE': str(root), **extra}, capture_output=True)
    result = run('--acquire'); assert result.returncode == 0, result.stderr
    assert (record / 'owner-unit').read_text().strip() == 'r46h-shell-probe-42.service'
    refused = run('--release', 'r46h-shell-probe-99.service')
    assert refused.returncode != 0, refused.stderr.decode()
    assert (root / 'mounted').exists()
    (root / 'mounted').write_text('52')
    assert run('--release').returncode != 0 and record.exists()
    (root / 'mounted').write_text('51')
    assert run('--release').returncode == 0 and not record.exists() and not (scope / 'mono').exists()
    v18 = 'd3130018-46a4-4d56-9001-000000000018'
    assert run('--acquire', ROOT_UUID=v18).returncode == 0
    assert run('--release', ROOT_UUID=v18).returncode == 0
    for failure in ({'MOUNT_ERROR': '1'}, {'MOUNT_ID_ERROR': '1'}):
        assert run('--acquire', **failure).returncode != 0
        assert not record.exists() and not (scope / 'mono').exists() and not (root / 'mounted').exists()
    assert run('--acquire', 'r46h-wayland-probe-43.service').returncode == 0
    assert (wayland_scope / 'mono/bin/mono').exists() and not (scope / 'mono').exists()
    assert run('--release').returncode != 0 and record.exists()
    assert run('--release', 'r46h-wayland-probe-43.service').returncode == 0
    assert not record.exists() and not (wayland_scope / 'mono').exists()
    cid.write_text('wrong card')
    assert run('--acquire').returncode != 0 and not record.exists()
print('PORT_RUNTIME_LEASE_PASS: fixed identity, owner-unit/mount-id refusal and acquisition-failure cleanup; no real mounts')
