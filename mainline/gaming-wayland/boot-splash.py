#!/usr/bin/env python3
"""Optional r11 boot image on tty1; release it when a frontend switches to tty2."""
import array
import fcntl
import gzip
import hashlib
import importlib.util
import os
from pathlib import Path
import signal
import socket
import stat
import struct
import sys
import time

BASE = Path(__file__).resolve().parent
ASSET = BASE / 'boot-splash.bgra.gz'
MARKER = Path('/run/jume-boot-splash/tty1-owned')
BYTES = 1024 * 768 * 4
STOP = False
VT_GETMODE, VT_SETMODE, VT_RELDISP = 0x5601, 0x5602, 0x5605
VT_AUTO = bytes(8)


def vt_signal(tty, signum):
    # KD_GRAPHICS + VT_AUTO blocks openvt; acknowledge its release request.
    fcntl.ioctl(tty, VT_RELDISP, 1 if signum == signal.SIGUSR1 else 2)
    if signum == signal.SIGUSR1:
        print('JUME_BOOT_SPLASH_RELEASE_REQUEST', flush=True)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(path, expected):
    require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'Helper hash mismatch')
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def helpers():
    fallback = load(Path('/var/lib/jume-launcher/esde-fallback.py'),
                    'ad6ff7e57c46caaec7fbbe722ceb146496fa5b5bf5d5c25238292b4bc6c8cec2')
    product = fallback.load_installer()
    product.target()
    require((fallback.ROOT / 'current').resolve() == fallback.ROOT / 'releases' / fallback.R11,
            'Wrong selected release')
    for path in (BASE, *BASE.parents, ASSET, BASE / 'r46h-display-diagnostic.py'):
        product.sealed(path)
    return load(BASE / 'r46h-display-diagnostic.py',
                '2d256521c895cb1ef84e59ac8b6b9436f98d2a7b596953e58af319aa6e80f55a')


def active_tty():
    return Path('/sys/class/tty/tty0/active').read_text().strip()


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def ready():
    address = os.environ.get('NOTIFY_SOCKET')
    if address:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect('\0' + address[1:] if address.startswith('@') else address)
            sock.sendall(b'READY=1')


def picture():
    require(ASSET.stat().st_size < 128 * 1024, 'Oversized boot image')
    with gzip.open(ASSET, 'rb') as stream:
        data = stream.read(BYTES + 1)
    require(len(data) == BYTES, 'Wrong boot image size')
    return data


def restore(fb):
    if not os.path.lexists(MARKER):
        return
    meta = MARKER.lstat()
    require(stat.S_ISREG(meta.st_mode) and meta.st_uid == os.geteuid()
            and meta.st_nlink == 1 and not meta.st_mode & 0o077
            and meta.st_size <= 64 and MARKER.read_text() == boot_id(), 'Foreign VT receipt')
    fd = os.open('/dev/tty1', os.O_RDWR | os.O_NOCTTY | os.O_CLOEXEC)
    try:
        # Always address tty1 explicitly: tty0 may already refer to the desktop VT.
        fcntl.ioctl(fd, VT_SETMODE, VT_AUTO)
        fcntl.ioctl(fd, fb.KDSETMODE, fb.KD_TEXT)
    finally:
        os.close(fd)
    MARKER.unlink()
    print('JUME_BOOT_SPLASH_RESTORED tty1', flush=True)


def show(fb):
    if active_tty() != 'tty1':
        ready()
        print('JUME_BOOT_SPLASH_SKIPPED active frontend', flush=True)
        return
    require(Path('/sys/class/graphics/fb0/name').read_text().strip() == 'rockchipdrmfb', 'Wrong framebuffer')
    data = picture()
    tty = os.open('/dev/tty1', os.O_RDWR | os.O_NOCTTY | os.O_CLOEXEC)
    try:
        mode = array.array('i', [0])
        fcntl.ioctl(tty, fb.KDGETMODE, mode, True)
        require(mode[0] == fb.KD_TEXT, 'tty1 already has a graphics owner')
        switching = bytearray(8)
        fcntl.ioctl(tty, VT_GETMODE, switching, True)
        require(switching[0] == 0, 'tty1 already has a VT controller')
        with MARKER.open('x') as receipt:
            os.chmod(MARKER, 0o600)
            receipt.write(boot_id())
        handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGUSR1, signal.SIGUSR2)}
        try:
            for sig in handlers:
                signal.signal(sig, lambda signum, _frame: vt_signal(tty, signum))
            fcntl.ioctl(tty, VT_SETMODE, struct.pack('=BBhhh', 1, 0, signal.SIGUSR1, signal.SIGUSR2, 0))
            fcntl.ioctl(tty, fb.KDSETMODE, fb.KD_GRAPHICS)
            fd = os.open('/dev/fb0', os.O_RDWR | os.O_CLOEXEC)
            try:
                require(stat.S_ISCHR(os.fstat(fd).st_mode), 'Framebuffer is not a device')
                fb.fb_mode(fd)  # Existing fixed geometry, stride and XR24 validation.
                fb.write_all_at(fd, data, 0)
                require(fb.read_exact_at(fd, BYTES, 0) == data, 'Boot image readback differs')
            finally:
                os.close(fd)
            print('JUME_BOOT_SPLASH_VISIBLE sha256=' + hashlib.sha256(data).hexdigest(), flush=True)
            ready()
            deadline = time.monotonic() + 145
            while not STOP and active_tty() == 'tty1' and time.monotonic() < deadline:
                time.sleep(0.1)
            print('JUME_BOOT_SPLASH_END active=' + active_tty(), flush=True)
        finally:
            try:
                restore(fb)
            finally:
                for sig, handler in handlers.items():
                    signal.signal(sig, handler)
    finally:
        os.close(tty)


def stop(_signum, _frame):
    global STOP
    STOP = True


if __name__ == '__main__':
    try:
        require(sys.argv[1:] in ([], ['--restore']), 'Use no arguments or --restore')
        for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            signal.signal(signum, stop)
        fb = helpers()
        restore(fb) if sys.argv[1:] else show(fb)
    except (OSError, ValueError, RuntimeError) as error:
        sys.exit('JUME_BOOT_SPLASH_REFUSED ' + str(error))
