#!/usr/bin/env python3
"""Opt-in R46H userspace trial/default switch. Never extracts archives or deletes releases/saves."""
import hashlib
import fcntl
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys

ROOT = Path('/var/lib/jume-launcher')
UNIT = Path('/etc/systemd/system/jume-launcher.service')
DROPIN = Path('/etc/systemd/system/r46h-gaming-frontend.service.d/50-jume.conf')
TRIAL = Path('/run/jume-launcher-trial')
DROPIN_CONTENT = b'[Unit]\nConditionPathExists=!/var/lib/jume-launcher/enabled\n'
REQUIRED = {'product-install.py', 'product-session.sh', 'jume-launcher.service',
            'session.sh', 'session-leases.sh', 'probe-r46h.sh', 'browser-cgroup.sh',
            'device-lease.sh', 'cpu-control.py', 'runtime-lease.sh', 'handheld-client.sh',
            'shell-client.sh', 'usr/bin/r46h-shell', 'usr/bin/input-router'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def sealed(path, owner=0):
    meta = path.lstat()
    require(meta.st_uid == owner and not meta.st_mode & 0o022, f'Unsealed path: {path}')
    require(not stat.S_ISLNK(meta.st_mode), f'Symlink parent: {path}')


def verify(root, expected, owner=0):
    require(re.fullmatch('[0-9a-f]{64}', expected), 'Invalid manifest hash')
    for parent in (root, *root.parents):
        sealed(parent, owner if parent == root else 0)
    manifest = root / 'SHA256SUMS'
    meta = manifest.lstat()
    require(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1 and meta.st_uid == owner
            and not meta.st_mode & 0o6022 and 0 < meta.st_size <= 4 * 1024 * 1024,
            'Unsafe or oversized manifest')
    require(digest(manifest) == expected, 'Manifest mismatch')
    entries = {}
    for line in manifest.read_text().splitlines():
        require(len(line) > 66 and re.fullmatch('[0-9a-f]{64}  .+', line), 'Invalid manifest line')
        name = line[66:]
        path = PurePosixPath(name)
        require(not path.is_absolute() and str(path) == name and '..' not in path.parts
                and not any(ord(c) < 32 for c in name) and name not in entries, 'Unsafe/duplicate manifest path')
        entries[name] = line[:64]
    require(REQUIRED <= entries.keys(), 'Incomplete installed-session payload')
    actual = set()
    for path in root.rglob('*'):
        meta = path.lstat()
        require(meta.st_uid == owner, f'Foreign owner: {path}')
        if path.is_symlink():
            require(not os.path.isabs(os.readlink(path)) and path.resolve(strict=True).is_relative_to(root),
                    f'External runtime link: {path}')
        elif path.is_dir():
            require(not meta.st_mode & 0o022, f'Writable runtime directory: {path}')
        else:
            require(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1 and not meta.st_mode & 0o6022,
                    f'Unsafe runtime file: {path}')
            name = path.relative_to(root).as_posix()
            if name == 'SHA256SUMS':
                continue
            require(name in entries and digest(path) == entries[name], f'Unverified file: {name}')
            actual.add(name)
    require(actual == entries.keys(), 'Missing files or symlink masquerading as manifest file')


def durable_write(path, data):
    temporary = path.with_name(path.name + '.incoming')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def systemctl(*args):
    return subprocess.run(['systemctl', *args], check=True, timeout=150)


def unit_value(name):
    return subprocess.check_output(['systemctl', 'show', '--value', '--property=' + name,
                                    'jume-launcher.service'], text=True, timeout=150).strip()


def clean_runtime():
    for name in ('/run/r46h-wayland-probe', '/run/r46h-device-lease', '/run/r46h-cpu-control',
                 '/run/r46h-port-runtime', '/run/seatd.sock', '/run/jume-launcher/mount-id',
                 '/run/jume-launcher/scope-created', '/run/jume-launcher/seatd-socket-identity',
                 '/run/jume-launcher/session'):
        require(not os.path.lexists(name), f'Cleanup incomplete; refusing transition: {name}')


def stopped_cleanly():
    systemctl('stop', 'jume-launcher.service')
    clean_runtime()


def target():
    require(os.geteuid() == 0 and os.uname().release == '6.12.99-r46h-mainline-v0.15-gaming-product', 'Wrong device/kernel')
    require(Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() == 'fe343253440000002000002d57019567'
            and Path('/sys/class/block/mmcblk0/size').read_text().strip() == '122138624', 'Wrong card')
    uuid = subprocess.check_output(['findmnt', '-rn', '-o', 'UUID', '/'], text=True).strip()
    require(uuid == 'd3130018-46a4-4d56-9001-000000000018', 'Only accepted p2 v0.18 is supported')
    for parent in (ROOT, ROOT.parent, ROOT / 'releases'):
        sealed(parent)


def main(argv):
    require(len(argv) in (1, 2, 3), 'Use --verify HASH, --install HASH, --select FROM TO, --trial, --enable or --rollback')
    action = argv[0]
    require(action in ('--verify', '--install', '--select', '--trial', '--enable', '--rollback'), 'Unknown action')
    require(len(argv) == (3 if action == '--select' else 2 if action in ('--verify', '--install') else 1), 'Wrong arguments')
    target()
    if action == '--verify':
        # ExecStartPre verifies while --trial is waiting for systemctl start.
        return perform(argv)
    fd = os.open(ROOT / 'operation.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        meta = os.fstat(fd)
        require(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1 and meta.st_uid == os.geteuid()
                and not meta.st_mode & 0o077, 'Unsafe operation lock')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return perform(argv)
    finally:
        os.close(fd)


def perform(argv):
    action = argv[0]
    if action in ('--verify', '--install'):
        expected = argv[1]
        require(re.fullmatch('[0-9a-f]{64}', expected), 'Invalid manifest hash')
        release = ROOT / 'releases' / expected
        verify(release, expected)
        if action == '--verify':
            print('JUME_RELEASE_VERIFIED artifact only; target runtime unproven')
            return
        # First promotion only: do not silently replace an existing version or unit.
        current = ROOT / 'current'
        require(not os.path.lexists(current) or current.is_symlink() and current.resolve() == release,
                'Another release is selected; use --rollback then --select FROM TO')
        systemctl('is-enabled', '--quiet', 'r46h-gaming-frontend.service')
        for path, data in ((UNIT, (release / 'jume-launcher.service').read_bytes()), (DROPIN, DROPIN_CONTENT)):
            for parent in path.parents:
                if parent.exists():
                    sealed(parent)
            require(not os.path.lexists(path) or not path.is_symlink() and path.read_bytes() == data,
                    f'Existing integration differs: {path}')
        if not os.path.lexists(current):
            current.symlink_to(release)
            sync_directory(ROOT)
        for path, data in ((UNIT, (release / 'jume-launcher.service').read_bytes()), (DROPIN, DROPIN_CONTENT)):
            path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            durable_write(path, data)
        systemctl('daemon-reload')
        print('JUME_INSTALLED_INACTIVE ES-DE remains boot default; no user state moved')
        return
    current = ROOT / 'current'
    require(current.is_symlink() and current.resolve().parent == ROOT / 'releases', 'No selected release')
    require(current.lstat().st_uid == 0, 'Foreign selection')
    if action == '--select':
        before, after = argv[1:]
        require(all(re.fullmatch('[0-9a-f]{64}', value) for value in (before, after)) and before != after,
                'Use distinct manifest hashes for FROM and TO')
        old, new = (ROOT / 'releases' / value for value in (before, after))
        require(current.resolve() in (old, new), 'Selection changed; inspect current before retrying')
        require(not os.path.lexists(ROOT / 'enabled') and not os.path.lexists(TRIAL), 'Run --rollback first')
        require(unit_value('ActiveState') == 'inactive' and unit_value('UnitFileState') == 'disabled',
                'Launcher must be inactive and disabled')
        systemctl('is-enabled', '--quiet', 'r46h-gaming-frontend.service')
        systemctl('is-active', '--quiet', 'r46h-gaming-frontend.service')
        clean_runtime()
        verify(old, before)
        verify(new, after)
        service = (old / 'jume-launcher.service').read_bytes()
        # ponytail: same-unit inactive switching only; service/schema migrations need a separate transaction.
        require((new / 'jume-launcher.service').read_bytes() == service, 'Service migration is not supported')
        for path, data in ((UNIT, service), (DROPIN, DROPIN_CONTENT)):
            for parent in (path, *path.parents):
                sealed(parent)
            require(path.is_file() and path.stat().st_size == len(data) and path.read_bytes() == data,
                    f'Existing integration differs: {path}')
        temporary = ROOT / 'current.incoming'
        if os.path.lexists(temporary):
            require(temporary.is_symlink() and temporary.lstat().st_uid == 0 and os.readlink(temporary) == str(new),
                    'Foreign pending selection; retained for inspection')
        else:
            temporary.symlink_to(new)
        # Retain a matching pending link on failure. Retry FROM TO even if rename
        # succeeded but fsync failed; current is always one complete old/new link.
        os.replace(temporary, current)
        sync_directory(ROOT)
        print(f'JUME_RELEASE_SELECTED from={before} to={after} inactive; ES-DE remains default')
        return
    if action == '--rollback':
        # Safe on reboot even if later cleanup fails. Do not start a second compositor.
        (ROOT / 'enabled').unlink(missing_ok=True)
        TRIAL.unlink(missing_ok=True)
        sync_directory(ROOT)
        stopped_cleanly()
        systemctl('disable', 'jume-launcher.service')
        systemctl('start', 'r46h-gaming-frontend.service')
        print('JUME_ROLLBACK_ESDE saves and installed release retained')
        return
    if action == '--trial':
        require(not (ROOT / 'enabled').exists(), 'Already promoted')
        systemctl('is-active', '--quiet', 'r46h-gaming-frontend.service')
        durable_write(TRIAL, b'trial\n')
        systemctl('stop', 'r46h-gaming-frontend.service')
        try:
            # A fresh inactive unit may be unloaded; reset-failed then fails on systemd 257.
            if unit_value('ActiveState') == 'failed':
                systemctl('reset-failed', 'jume-launcher.service')
            systemctl('start', 'jume-launcher.service')
            systemctl('is-active', '--quiet', 'jume-launcher.service')
        except subprocess.SubprocessError:
            TRIAL.unlink(missing_ok=True)
            stopped_cleanly()
            systemctl('start', 'r46h-gaming-frontend.service')
            raise
        print('JUME_TRIAL_STARTED next cold boot still selects ES-DE; readiness requires acceptance')
        return
    systemctl('is-active', '--quiet', 'jume-launcher.service')
    require(TRIAL.is_file() and not TRIAL.is_symlink() and TRIAL.stat().st_uid == 0, 'Run and accept a trial first')
    systemctl('enable', 'jume-launcher.service')
    durable_write(ROOT / 'enabled', b'jume\n')
    TRIAL.unlink()
    print('JUME_DEFAULT_SELECTED cold boot and independent recovery are still acceptance gates')


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        sys.exit(f'JUME_INSTALL_REFUSED {error}')
