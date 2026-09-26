#!/usr/bin/python3
"""Root-owned, temporary CPU control for the exact R46H device lease."""
import json
import os
from pathlib import Path
import pwd
import re
import socket
import stat
import struct
import subprocess
import sys
import time


LEASE = Path('/run/r46h-device-lease')
SOCKET = Path('/run/r46h-cpu-control/control.sock')
CPU = Path('sys/devices/system/cpu/cpufreq/policy0')
NODES = ('scaling_min_freq', 'scaling_max_freq', 'scaling_governor')
CAPS = {'desktop': 816000, 'game': 1008000, 'off': 600000}


class Rejected(Exception):
    pass


def read(root, path):
    return (root / path).read_text().strip()


def integer(root, path):
    value = read(root, path)
    if not value.isascii() or not value.isdecimal():
        raise Rejected('readback_unavailable')
    return int(value)


def health(root, manual):
    online = integer(root, Path('sys/class/power_supply/rk817-charger/online'))
    voltage_path = Path('sys/class/power_supply/rk817-battery/voltage_avg')
    try:
        voltage = integer(root, voltage_path)
    except (OSError, Rejected):
        voltage = integer(root, Path('sys/class/power_supply/rk817-battery/voltage_now'))
    minimum = integer(root, Path('sys/class/power_supply/rk817-battery/voltage_min_design'))
    if online not in (0, 1) or (manual and online != 1) or minimum <= 0 or voltage <= minimum:
        raise Rejected('unsafe_supply')
    temperatures = []
    for zone in (root / 'sys/class/thermal').glob('thermal_zone*'):
        try:
            value = integer(root, zone.relative_to(root) / 'temp')
            if value > 200000:
                continue
            temperatures.append(value)
            for trip in zone.glob('trip_point_*_type'):
                if trip.read_text().strip() in ('hot', 'critical'):
                    limit = integer(root, trip.relative_to(root).with_name(trip.name.replace('_type', '_temp')))
                    if limit > 5000 and value >= limit - 5000:
                        raise Rejected('thermal_limit')
        except OSError:
            raise Rejected('temperature_unavailable') from None
    if not temperatures:
        raise Rejected('temperature_unavailable')


def write(root, name, value):
    path = root / CPU / name
    fd = os.open(path, os.O_WRONLY | os.O_TRUNC | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        data = f'{value}\n'.encode()
        if os.write(fd, data) != len(data):
            raise Rejected('short_write')
    finally:
        os.close(fd)
    deadline = time.monotonic() + (0.1 if name in NODES[:2] else 0)
    while read(root, CPU / name) != str(value):
        if time.monotonic() >= deadline:
            raise Rejected('readback_failed')
        time.sleep(0.002)


def write_profile(root, governor, minimum, maximum):
    current_min = integer(root, CPU / 'scaling_min_freq')
    order = (('scaling_min_freq', minimum), ('scaling_max_freq', maximum)) if maximum < current_min else (
        ('scaling_max_freq', maximum), ('scaling_min_freq', minimum))
    for name, value in order:
        write(root, name, value)
    write(root, 'scaling_governor', governor)


def apply(request, root=Path('/'), lease=LEASE):
    """Validate every privileged operation independently of the launcher."""
    if type(request) is not dict:
        return {'ok': False, 'error': 'invalid_request'}
    operation = request.get('op')
    if (operation == 'scene' and set(request) == {'op', 'scene'}
            and type(request['scene']) is str and request['scene'] in CAPS):
        manual = False
    elif operation == 'manual' and set(request) == {'op', 'governor', 'minimum', 'maximum'}:
        manual = True
    else:
        return {'ok': False, 'error': 'invalid_request'}
    try:
        health(root, manual)
        original_min = integer(lease, Path('1.value'))
        original_max = integer(lease, Path('2.value'))
        original_governor = read(lease, Path('3.value'))
        available = {int(value) for value in read(root, CPU / 'scaling_available_frequencies').split() if value.isdecimal()}
        governors = read(root, CPU / 'scaling_available_governors').split()
        previous = (read(root, CPU / 'scaling_governor'), integer(root, CPU / 'scaling_min_freq'),
                    integer(root, CPU / 'scaling_max_freq'))
        if manual:
            governor = request['governor']
            minimum, maximum = request['minimum'], request['maximum']
            if (type(governor) is not str or type(minimum) is not int or type(maximum) is not int
                    or governor not in governors or minimum < integer(root, CPU / 'cpuinfo_min_freq')
                    or maximum > integer(root, CPU / 'cpuinfo_max_freq')):
                raise Rejected('unsupported_cpu_policy')
        else:
            if original_governor != 'schedutil' or previous[0] != 'schedutil':
                raise Rejected('unsupported_cpu_policy')
            governor, minimum, maximum = 'schedutil', original_min, min(original_max, CAPS[request['scene']])
        if minimum not in available or maximum not in available or minimum > maximum:
            raise Rejected('unsupported_cpu_policy')
        try:
            write_profile(root, governor, minimum, maximum)
        except (OSError, Rejected):
            try:
                write_profile(root, *previous)
            except (OSError, Rejected):
                return {'ok': False, 'error': 'rollback_failed'}
            return {'ok': False, 'error': 'write_failed'}
        return {'ok': True}
    except (OSError, ValueError, Rejected) as error:
        return {'ok': False, 'error': str(error) if isinstance(error, Rejected) else 'readback_unavailable'}


def serve(unit):
    if os.geteuid() != 0 or not re.fullmatch(r'r46h-(?:shell|wayland)-probe-[0-9]+\.service', unit):
        raise Rejected('invalid_owner')
    if (os.uname().release != '6.12.99-r46h-mainline-v0.15-gaming-product'
            or read(Path('/'), Path('sys/class/block/mmcblk0/device/cid')) != 'fe343253440000002000002d57019567'
            or read(Path('/'), Path('sys/class/block/mmcblk0/size')) != '122138624'
            or subprocess.check_output(['/usr/bin/findmnt', '-rn', '-o', 'UUID', '/'], text=True).strip()
            not in ('d3130017-46a4-4d56-9001-000000000017', 'd3130018-46a4-4d56-9001-000000000018')
            or read(LEASE, Path('unit')) != unit
            or read(LEASE, Path('boot')) != read(Path('/'), Path('proc/sys/kernel/random/boot_id'))
            or not (LEASE / 'ready').is_file()):
        raise Rejected('device_identity')
    folder = SOCKET.parent
    ark_gid = pwd.getpwnam('ark').pw_gid
    meta = folder.lstat()
    if not stat.S_ISDIR(meta.st_mode) or meta.st_uid != 0 or meta.st_gid != ark_gid or stat.S_IMODE(meta.st_mode) != 0o750:
        raise Rejected('socket_directory')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(SOCKET))
        os.chown(SOCKET, 0, ark_gid)
        os.chmod(SOCKET, 0o660)
        server.listen(4)
        while True:
            connection, _ = server.accept()
            with connection:
                connection.settimeout(1)
                pid, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                if pid <= 1 or uid != 1000:
                    continue
                try:
                    data = b''
                    while len(data) <= 256 and not data.endswith(b'\n'):
                        chunk = connection.recv(257 - len(data))
                        if not chunk:
                            break
                        data += chunk
                    if len(data) > 256 or not data.endswith(b'\n'):
                        reply = {'ok': False, 'error': 'invalid_request'}
                    else:
                        try:
                            reply = apply(json.loads(data))
                        except (ValueError, UnicodeError):
                            reply = {'ok': False, 'error': 'invalid_request'}
                    connection.sendall(json.dumps(reply, separators=(',', ':')).encode() + b'\n')
                except OSError:
                    continue


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(2)
    try:
        serve(sys.argv[1])
    except (OSError, subprocess.SubprocessError, Rejected):
        sys.exit(1)
