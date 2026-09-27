#!/usr/bin/env python3
"""Host contract/negative checks. Not proof of Linux cgroup enforcement."""
import os
from pathlib import Path
import subprocess
import tempfile

repo = Path(__file__).resolve().parents[2]
guard = repo / 'mainline/gaming-wayland/browser-cgroup.sh'
source = guard.read_text()
subprocess.run(['bash', '-n', str(guard)], check=True)
functions = source[source.index('session_parent()'):source.index('[[ $(findmnt')]

def bash(code, **env):
    return subprocess.run(['bash', '-c', 'set -Eeuo pipefail\n' + functions + code],
                          env={**os.environ, **env}, capture_output=True, text=True, timeout=5)

for value, valid in [('/system.slice/r46h-wayland-probe-123.service/desktop', True),
                     ('/system.slice/jume-launcher.service/desktop', True),
                     ('/system.slice/jume-launcher.service/browser', False),
                     ('/system.slice/r46h-wayland-probe-123.service/browser', False),
                     ('/system.slice/other.service/desktop', False), ('/', False),
                     ('/system.slice/r46h-wayland-probe-../desktop', False),
                     ('/system.slice/r46h-wayland-probe-123.service/desktop\n/escape', False)]:
    result = bash('session_parent "$VALUE"', VALUE=value)
    assert (result.returncode == 0) == valid, (value, result)
    if valid:
        assert result.stdout.strip() == '/sys/fs/cgroup' + value.removesuffix('/desktop')

with tempfile.TemporaryDirectory(prefix='browser-memory-', dir=repo/'mainline/out/.cache') as directory:
    group = Path(directory)
    limits = {'memory.max': '402653184', 'memory.swap.max': '134217728', 'memory.oom.group': '1'}
    for name, value in limits.items(): (group/name).write_text(value+'\n')
    assert bash('verify_limits "$GROUP"', GROUP=directory).returncode == 0
    for name, value in limits.items():
        for wrong in ('max', '', '0', '999999999'):
            (group/name).write_text(wrong+'\n')
            assert bash('verify_limits "$GROUP"', GROUP=directory).returncode != 0, name
        (group/name).unlink()
        assert bash('verify_limits "$GROUP"', GROUP=directory).returncode != 0, name
        (group/name).write_text(value+'\n')

probe = (repo/'mainline/gaming-wayland/probe-r46h.sh').read_text()
session = (repo/'mainline/gaming-wayland/session.sh').read_text()
client = (repo/'mainline/gaming-browser/browser-client.sh').read_text()
assert 'Delegate=memory -p DelegateSubgroup=desktop -p OOMPolicy=continue' in probe
assert "grep -Fq 'JUME_BROWSER_MEMORY_GUARD'" in probe
assert session.index('browser-cgroup.sh" --prepare') < session.index('"$base/usr/sbin/seatd"')
assert 'unset JUME_BROWSER_MEMORY_GUARD' in session
assert 'Browser memory guard missing.' in client and '--run "$base/usr/bin/jume-browser" "$@"' in client
assert 'browser-cgroup.sh' in (repo/'mainline/gaming-wayland/check-session.sh').read_text()
assert "'browser-cgroup.sh'" in (repo/'mainline/gaming-wayland/build-in-container.py').read_text()
assert 'chown ark:ark "$parent/cgroup.procs" "$group/cgroup.procs"' in source
assert '! -w $parent/desktop/cgroup.procs' in source and '! -w $parent/cgroup.subtree_control' in source
assert 'membership-readback' in source and 'browser-still-active' in source
assert source.index('membership-readback') < source.index('exec "$@"')
assert 'available >= 262144' in source
print('BROWSER_CGROUP_HOST_PASS: exact session, limit rejection, fail-closed launch and package wiring; no kernel/OOM exercised here')
