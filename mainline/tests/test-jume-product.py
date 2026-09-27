#!/usr/bin/env python3
"""Installed-session contracts and transaction fixtures; no systemd/device proof."""
import contextlib
import fcntl
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

repo = Path(__file__).resolve().parents[2]
code = repo / 'mainline/gaming-wayland'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


install = load('product_install', code / 'product-install.py')
port = load('product_local_port', repo / 'mainline/gaming-ports/local_port.py')


def refuses(call):
    try:
        call()
    except (ValueError, OSError, subprocess.SubprocessError):
        return
    raise AssertionError('Unsafe operation accepted')


with tempfile.TemporaryDirectory(prefix='jume-product-', dir=repo / 'mainline/out/.cache') as temporary:
    root = Path(temporary)
    payload = root / 'payload'
    payload.mkdir(mode=0o755)
    for name in install.REQUIRED:
        path = payload / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(name + '\n')
        path.chmod(0o644)
    manifest = ''.join(f'{install.digest(payload/name)}  {name}\n' for name in sorted(install.REQUIRED))
    (payload / 'SHA256SUMS').write_text(manifest)
    expected = hashlib.sha256(manifest.encode()).hexdigest()
    sealed = install.sealed

    # The host fixture is user-owned; real CLI always uses root ownership, including parents.
    with patch.object(install, 'sealed', side_effect=lambda path, owner=0: sealed(path, os.getuid()) if path == payload else None):
        verify = lambda: install.verify(payload, expected, os.getuid())
        verify()
        unexpected = payload / 'unlisted'
        unexpected.write_text('not covered')
        refuses(verify)
        unexpected.unlink()
        file = payload / 'product-session.sh'
        original = file.read_bytes()
        file.write_text('tampered')
        refuses(verify)
        file.write_bytes(original)
        file.chmod(0o666)
        refuses(verify)
        file.chmod(0o644)
        file.unlink()
        file.symlink_to('/bin/sh')
        refuses(verify)
        file.unlink()
        file.write_bytes(original)
        link = payload / 'external'
        link.symlink_to('../payload/product-session.sh')
        verify()  # Contained, verified target; no external references.
        link.unlink()
        link.symlink_to('../../outside')
        refuses(verify)
        link.unlink()
        (payload / 'SHA256SUMS').write_text(manifest + manifest.splitlines()[0] + '\n')
        duplicate = install.digest(payload / 'SHA256SUMS')
        refuses(lambda: install.verify(payload, duplicate, os.getuid()))
        (payload / 'SHA256SUMS').write_text(manifest)
        manifest_path = payload / 'SHA256SUMS'
        manifest_path.unlink()
        os.mkfifo(manifest_path)
        with patch.object(install, 'digest', side_effect=AssertionError('Unsafe manifest must not be opened')):
            refuses(verify)
        manifest_path.unlink()
        manifest_path.write_text(manifest)
        manifest_path.chmod(0o666)
        refuses(verify)
        manifest_path.chmod(0o644)
        with manifest_path.open('wb') as stream:
            stream.truncate(4 * 1024 * 1024 + 1)
        with patch.object(install, 'digest', side_effect=AssertionError('Oversized manifest must not be read')):
            refuses(verify)
        manifest_path.write_text(manifest)

    selected = root / 'selection'
    selected.write_bytes(b'old')
    with patch.object(install.os, 'replace', side_effect=OSError('interrupted publication')):
        refuses(lambda: install.durable_write(selected, b'new'))
    assert selected.read_bytes() == b'old' and not (root / 'selection.incoming').exists()

    # Exercise the real stop hook against owned fixtures, never a host mount/service.
    hook = (code / 'product-session.sh').read_text()
    for case in ('foreign', 'owned', 'changed-mount', 'lease-failed'):
        folder = root / case
        scope = folder / 'scope'
        runtime = folder / 'runtime'
        scope.mkdir(parents=True)
        runtime.mkdir()
        if case != 'foreign':
            (runtime / 'scope-created').touch()
            (runtime / 'mount-id').write_text('123\n')
            (scope / 'session-leases.sh').write_text('echo LEASE_RESTORE\nexit ' + ('1' if case == 'lease-failed' else '0') + '\n')
        source = hook.replace('$EUID', '${TEST_UID}').replace('/run/r46h-wayland-probe', str(scope)) \
            .replace('/run/jume-launcher', str(runtime)).replace('/run/seatd.sock', str(folder / 'socket'))
        prelude = '''readlink() { echo /var/lib/jume-launcher/releases/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; }
stat() { echo 0:0:755; }
findmnt() { echo "$MOUNT_ID"; }
umount() { echo UNMOUNT; rm -- "$1/session-leases.sh"; }
systemctl() { echo "SYSTEMCTL $*"; }
sync() { echo SYNC; }
'''
        result = subprocess.run(['bash', '-c', prelude + source, 'fixture', '--restore'],
                                env={**os.environ, 'TEST_UID': '0', 'MOUNT_ID': '456' if case == 'changed-mount' else '123'},
                                capture_output=True, text=True, timeout=5)
        assert (result.returncode == 0) == (case in ('foreign', 'owned')), result
        assert ('UNMOUNT' in result.stdout) == (case == 'owned'), result
        assert scope.exists() == (case != 'owned'), result
        if case in ('changed-mount', 'lease-failed'):
            assert (runtime / 'mount-id').exists(), 'Failed cleanup must retain its receipt'

    product = root / 'product'
    release = product / 'releases' / expected
    release.mkdir(parents=True)
    (release / 'jume-launcher.service').write_bytes((code / 'jume-launcher.service').read_bytes())
    unit = root / 'system/jume-launcher.service'
    dropin = root / 'system/esde.d/50-jume.conf'
    trial = root / 'trial'
    calls = []
    def systemctl(*args):
        calls.append(args)
    with patch.multiple(install, ROOT=product, UNIT=unit, DROPIN=dropin, TRIAL=trial), \
         patch.object(install, 'target'), patch.object(install, 'sealed'), patch.object(install, 'verify'), \
         patch.object(install, 'systemctl', side_effect=systemctl), \
         patch.object(install.subprocess, 'check_output', return_value='inactive\n') as service_state:
        install.main(['--install', expected])
        # A concurrent mutation fails promptly; the service's read-only verification
        # remains available while --trial holds the lock across systemctl start.
        with (product / 'operation.lock').open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            before = list(calls)
            refuses(lambda: install.main(['--rollback']))
            install.main(['--verify', expected])
            assert calls == before
        # Closing a failed contender must not unlink/recreate the live lock inode.
        inode = (product / 'operation.lock').stat().st_ino
        install.main(['--install', expected])
        assert (product / 'operation.lock').stat().st_ino == inode
        assert (product / 'current').resolve() == release
        assert not (product / 'enabled').exists() and not trial.exists()
        assert not any(call[0] in ('enable', 'disable', 'stop', 'start') for call in calls)
        unit.write_text('foreign integration')
        refuses(lambda: install.main(['--install', expected]))
        assert unit.read_text() == 'foreign integration'
        unit.write_bytes((code / 'jume-launcher.service').read_bytes())
        # Simulate the root-owned selection/marker when testing on a non-root Mac.
        def root_marker(path):
            # Python 3.13 Path.lstat delegates to Path.stat (patched below).
            meta = os.lstat(path)
            if path in (product / 'current', trial):
                values = list(meta)
                values[4] = 0
                return os.stat_result(values)
            return meta
        original_stat = Path.stat
        def marker_stat(path, **kwargs):
            return root_marker(path) if path == trial else original_stat(path, **kwargs)
        with patch.object(Path, 'lstat', root_marker), patch.object(Path, 'stat', marker_stat):
            install.main(['--trial'])
            assert trial.exists() and not (product / 'enabled').exists()
            assert ('stop', 'r46h-gaming-frontend.service') in calls
            assert ('reset-failed', 'jume-launcher.service') not in calls
            trial.unlink()
            service_state.return_value = 'failed\n'
            install.main(['--trial'])
            assert ('reset-failed', 'jume-launcher.service') in calls
            trial.unlink()
            calls.clear()
            service_state.side_effect = subprocess.CalledProcessError(1, ['systemctl', 'show'])
            with patch.object(install.os.path, 'lexists', return_value=False):
                try:
                    install.main(['--trial'])
                except subprocess.CalledProcessError:
                    pass
                else:
                    raise AssertionError('State lookup failure must abort the trial')
            assert not trial.exists()
            assert calls == [('is-active', '--quiet', 'r46h-gaming-frontend.service'),
                             ('stop', 'r46h-gaming-frontend.service'), ('stop', 'jume-launcher.service'),
                             ('start', 'r46h-gaming-frontend.service')]
            service_state.side_effect = None
            install.main(['--trial'])
            install.main(['--enable'])
            assert (product / 'enabled').read_bytes() == b'jume\n' and not trial.exists()
            calls.clear()
            with patch.object(install.os.path, 'lexists', return_value=False):
                install.main(['--rollback'])
            assert not (product / 'enabled').exists()
            assert calls == [('stop', 'jume-launcher.service'), ('disable', 'jume-launcher.service'),
                             ('start', 'r46h-gaming-frontend.service')]
            assert release.exists() and (product / 'current').is_symlink()
            calls.clear()
            with patch.object(install.os.path, 'lexists', return_value=True):
                refuses(lambda: install.main(['--rollback']))
            assert calls == [('stop', 'jume-launcher.service')], 'Do not resume ES-DE after failed cleanup'

    # Run the actual port event loop: product has no diagnostic timeout but exits normally.
    @contextlib.contextmanager
    def prepared(*args, **kwargs):
        yield {'program': '/bin/sh', 'arguments': ['-c', 'sleep 0.05; exit 0'], 'directory': str(root)}
    real_read = Path.read_text
    for index, (group, seconds, accepted) in enumerate([
        ('0::/system.slice/jume-launcher.service/desktop\n', 0, True),
        ('0::/system.slice/r46h-wayland-probe-42.service/desktop\n', 5, True),
        ('0::/system.slice/r46h-wayland-probe-42.service\n', 5, True),
        ('0::/system.slice/r46h-wayland-probe-42.service/desktop\n', 0, False),
        ('0::/system.slice/jume-launcher.service/browser\n', 5, False),
        ('0::/user.slice/system.slice/jume-launcher.service/desktop\n', 0, False),
    ]):
        def read(path, *args, **kwargs):
            if str(path) == '/proc/self/cgroup': return group
            if str(path) == '/sys/class/block/mmcblk0/device/cid': return 'fe343253440000002000002d57019567'
            return real_read(path, *args, **kwargs)
        state = root / f'game-state-{index}'
        state.mkdir(exist_ok=True)
        with patch.object(Path, 'read_text', read), patch.object(port.os, 'geteuid', return_value=1000), \
             patch.object(port, '__file__', str(root / 'runtime/usr/share/r46h/ports/local_port.py')), \
             patch.object(port.platform, 'release', return_value='6.12.99-r46h-mainline-v0.15-gaming-product'), \
             patch.object(port.os, 'statvfs', return_value=SimpleNamespace(f_flag=os.ST_RDONLY)), \
             patch.object(port, 'prepared', prepared), patch.object(port, '_device_libraries', return_value='/unused'), \
             patch.dict(os.environ, WAYLAND_DISPLAY='fixture', SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT='0x5246/0x0049'):
            run = lambda: port.run_game('gta3', Path('/roms'), state, seconds, shared_display=True)
            if accepted: assert run() == 0
            else: refuses(run)

    # The C++ worker must accept exactly the same shared membership paths.
    tools = (repo / 'mainline/gaming-shell/tools.cpp').read_text()
    pattern = re.search(r'\? "(\^0::.*)"', tools).group(1).replace('\\\\', '\\')
    for path, accepted in [('r46h-wayland-probe-42.service', True),
                           ('r46h-wayland-probe-42.service/desktop', True),
                           ('jume-launcher.service/desktop', True),
                           ('jume-launcher.service/browser', False),
                           ('other.service/desktop', False)]:
        assert bool(re.fullmatch(pattern, '0::/system.slice/' + path + '\n')) == accepted

unit = (code / 'jume-launcher.service').read_text()
for contract in ('Restart=always', 'StartLimitBurst=3', 'KillMode=control-group', 'DelegateSubgroup=desktop',
                 'OOMPolicy=continue', 'ExecStopPost=', 'RestartPreventExitStatus=77 78',
                 'RuntimeDirectoryPreserve=yes', 'ConditionPathExists=|/run/jume-launcher-trial'):
    assert contract in unit
assert 'RuntimeMaxSec' not in unit
session = (code / 'session.sh').read_text()
assert 'wait -n -p completed "$client" "$pid"' in session and '[ "$completed" != "$pid" ] || exit 1' in session
product = (code / 'product-session.sh').read_text()
assert 'systemctl start r46h-gaming-frontend' not in product
assert product.index('--restore "$unit" 1 1') < product.index('umount "$scope"') < product.index('systemctl --no-block')
for path in ('product-session.sh', 'session.sh', 'handheld-client.sh', 'session-leases.sh'):
    subprocess.run(['bash', '-n', str(code / path)], check=True)
print('JUME_PRODUCT_HOST_PASS: seal, trial/default/rollback, native membership and lifetime; systemd/ARM64/boot untested')
