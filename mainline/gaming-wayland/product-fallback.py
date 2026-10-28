#!/usr/bin/env python3
"""Optional r9 service overlay: failed Jume -> ES-DE for this boot only."""
import fcntl
import hashlib
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import sys

ROOT = Path('/var/lib/jume-launcher')
R9 = 'b50da7bbd0dca358c7a4b7199735a1ff4548648b6659e0afc8654833762de33c'
INSTALLER_SHA256 = '8702148559762f6a8aae5948d5d7afa8e0d15738ad901caf26924eb44fcdaa30'
HELPER = ROOT / 'esde-fallback.py'
SERVICE = Path('/etc/systemd/system/jume-esde-fallback.service')
DROPIN = Path('/etc/systemd/system/jume-launcher.service.d/60-esde-fallback.conf')
BOOT_OVERRIDE = Path('/run/systemd/system/r46h-gaming-frontend.service.d/90-jume-fallback.conf')
SERVICE_DATA = b'''[Unit]
Description=Return to ES-DE after Jume failure
After=jume-launcher.service

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -B /var/lib/jume-launcher/esde-fallback.py --recover
TimeoutStartSec=180
UMask=0077
'''
DROPIN_DATA = b'''[Unit]
OnFailure=jume-esde-fallback.service
Conflicts=r46h-gaming-frontend.service

[Service]
Restart=no
'''
BOOT_DATA = b'[Unit]\nConditionPathExists=\n'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_installer():
    # Pin the trusted recovery code before importing it; a broken payload must
    # not prevent cleanup verification, nor supply different privileged code.
    path = ROOT / 'releases' / R9 / 'product-install.py'
    meta = path.lstat()
    require(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1 and 0 < meta.st_size <= 65536,
            'Invalid r9 recovery script type/size')
    for parent in (path, *path.parents):
        meta = parent.lstat()
        require(meta.st_uid == 0 and not meta.st_mode & 0o022 and not stat.S_ISLNK(meta.st_mode),
                'Unsealed r9 recovery path')
    require(hashlib.sha256(path.read_bytes()).hexdigest() == INSTALLER_SHA256, 'r9 installer differs')
    spec = importlib.util.spec_from_file_location('jume_installed_product', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def owned_file(product, path, data):
    for parent in path.parents:
        if os.path.lexists(parent):
            product.sealed(parent)
    if os.path.lexists(path):
        product.sealed(path)
        meta = path.lstat()
        require(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1
                and meta.st_size == len(data) and path.read_bytes() == data,
                'Existing fallback configuration differs; retained')


def check_integration(product):
    release = ROOT / 'releases' / R9
    current = ROOT / 'current'
    require(current.is_symlink() and current.lstat().st_uid == os.geteuid()
            and current.resolve() == release, 'Select the sealed r9 release first')
    for path, data in ((product.UNIT, (release / 'jume-launcher.service').read_bytes()),
                       (product.DROPIN, product.DROPIN_CONTENT)):
        owned_file(product, path, data)
        require(path.is_file(), 'Missing r9 service integration')
    # Clearing the boot condition must never discard an unrelated safety guard.
    text = subprocess.check_output(['systemctl', 'cat', 'r46h-gaming-frontend.service'], text=True, timeout=10)
    conditions = [line.strip() for line in text.splitlines()
                  if line.strip().startswith(('Condition', 'Assert'))]
    expected = ['ConditionPathExists=!/var/lib/jume-launcher/enabled']
    if BOOT_OVERRIDE.exists():
        expected.append('ConditionPathExists=')
    require(conditions == expected, 'Unexpected ES-DE conditions; refusing to replace them')


def perform(action, product):
    check_integration(product)
    require(product.unit_value('ActiveState') in ('inactive', 'failed'), 'Stop Jume before changing recovery')
    product.clean_runtime()
    files = ((HELPER, Path(__file__).read_bytes()), (SERVICE, SERVICE_DATA), (DROPIN, DROPIN_DATA))
    for path, data in (*files, (BOOT_OVERRIDE, BOOT_DATA)):
        owned_file(product, path, data)
    if action == '--recover':
        require(product.unit_value('ActiveState') == 'failed', 'No failed Jume session to recover')
        require(all(path.is_file() for path, _ in files), 'Incomplete fallback installation')
        BOOT_OVERRIDE.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        product.durable_write(BOOT_OVERRIDE, BOOT_DATA)
        product.systemctl('daemon-reload')
        product.systemctl('start', 'r46h-gaming-frontend.service')
        product.systemctl('is-active', '--quiet', 'r46h-gaming-frontend.service')
        print('JUME_ESDE_FALLBACK_STARTED current boot only; next boot still selects Jume')
        return
    require(product.unit_value('UnitFileState') == 'disabled' and not os.path.lexists(ROOT / 'enabled')
            and not os.path.lexists(product.TRIAL), 'Run r9 --rollback before installing/removing the overlay')
    product.systemctl('is-active', '--quiet', 'r46h-gaming-frontend.service')
    product.systemctl('is-enabled', '--quiet', 'r46h-gaming-frontend.service')
    if action == '--install':
        product.verify(ROOT / 'releases' / R9, R9)
        for path, data in files:
            path.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            product.durable_write(path, data)
    else:
        # Remove the trigger first; only byte-matching, task-owned files go away.
        for path in (DROPIN, SERVICE, HELPER, BOOT_OVERRIDE):
            if path.exists():
                path.unlink()
                product.sync_directory(path.parent)
    product.systemctl('daemon-reload')
    print('JUME_ESDE_FALLBACK_' + ('INSTALLED' if action == '--install' else 'REMOVED') +
          ' ES-DE remains default; no user state changed')


def main(argv):
    require(len(argv) == 1 and argv[0] in ('--install', '--recover', '--remove'),
            'Use --install, --recover or --remove')
    product = load_installer()
    product.target()
    fd = os.open(ROOT / 'operation.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        meta = os.fstat(fd)
        require(stat.S_ISREG(meta.st_mode) and meta.st_nlink == 1 and meta.st_uid == os.geteuid()
                and not meta.st_mode & 0o077, 'Unsafe operation lock')
        # A crash can race --trial/--enable; the recovery service bounds this wait.
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if argv[0] == '--recover' else fcntl.LOCK_NB))
        perform(argv[0], product)
    finally:
        os.close(fd)


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        sys.exit(f'JUME_ESDE_FALLBACK_REFUSED {error}')
