#!/usr/bin/env python3
"""Exercise actual Wayland probe guards and recovery without a device."""
from pathlib import Path
import os
import re
import socket
import subprocess
import tempfile
import importlib.util
from unittest.mock import patch

repo = Path(__file__).resolve().parents[2]
source = (repo / 'mainline/gaming-wayland/probe-r46h.sh').read_text()
handheld = (repo / 'mainline/gaming-wayland/handheld-client.sh').read_text()



def bash(code, **env):
    return subprocess.run(['/bin/bash', '-c', 'set -Eeuo pipefail\n' + code],
                          env={**os.environ, **env}, text=True, capture_output=True, timeout=5)


identity = source[source.index('root_uuid='):source.index('[[ $(cat /sys/class/block/mmcblk0/device/cid)')]
for uuid, version in [('d3130017-46a4-4d56-9001-000000000017', 'v0.17'),
                      ('d3130018-46a4-4d56-9001-000000000018', 'v0.18')]:
    result = bash('findmnt() { echo "$ROOT_UUID"; }\n' + identity + '\nprintf "%s\\n" "$rootfs"', ROOT_UUID=uuid)
    assert result.returncode == 0 and result.stdout.strip() == version, result
assert bash('findmnt() { echo unknown; }\n' + identity).returncode != 0


with tempfile.TemporaryDirectory(prefix='handheld-client-', dir=repo / 'mainline/out/.cache') as directory:
    root = Path(directory); output = root / 'output'; output.mkdir()
    (root / 'handheld-client.sh').write_text(handheld); (root / 'handheld-client.sh').chmod(0o755)
    (root / 'shell-client.sh').write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CALL_RECORD"\n')
    (root / 'shell-client.sh').chmod(0o755)
    record = root / 'args'
    result = bash(f'CALL_RECORD={record} R46H_ROUTED_SOURCE=/dev/input/test R46H_SHARED_PORTS=1 {root}/handheld-client.sh ui {output}')
    assert result.returncode == 0 and '--applications' not in record.read_text().splitlines(), result
    browser = root / 'browser/browser-client.sh'
    browser.parent.mkdir(); browser.write_text('#!/bin/sh\nexit 0\n')
    for mode, diagnostic in [(0o644, True), (0o755, False)]:
        browser.chmod(mode)
        result = bash(f'CALL_RECORD={record} R46H_ROUTED_SOURCE=/dev/input/test R46H_SHARED_PORTS=0 {root}/handheld-client.sh ui {output}')
        assert result.returncode == 0, result
        assert ('--applications' in record.read_text().splitlines()) == diagnostic


# Execute the actual batched header/closure check without loading fixture ELFs.
elf_check = source[source.index('binaries=()'):source.index("printf 'WAYLAND_PREFLIGHT")]
with tempfile.TemporaryDirectory(prefix='elf-check-', dir=repo / 'mainline/out/.cache') as directory:
    root = Path(directory); payload = root / 'usr'; payload.mkdir(); record = root / 'calls'
    executable = payload / 'executable with spaces'; executable.write_bytes(b'\x7fELFfixture')
    library = payload / 'library.so'; library.write_bytes(b'\x7fELFfixture'); library.chmod(0o600)
    (payload / 'text').write_text('not an executable')
    (payload / 'nul-prefix').write_bytes(b'\0\x7fELF')
    (payload / 'short').write_bytes(b'\x7fEL')
    (payload / 'link').symlink_to(executable)
    fake_ldd = """ldd() {
        [[ $LD_LIBRARY_PATH == /private/ports:/private/libs:/private/libs/weston:/private/libs/libproxy && $LC_ALL == C ]] || return 2
        printf '%s\\0' "$@" > "$CALL_RECORD"
        printf '%s\\n' "$LDD_OUTPUT"
        return "$LDD_STATUS"
    }
    """
    for status, output, rejected in [(0, 'all resolved', False), (0, 'libmissing.so => not found', True), (1, 'invalid ELF', True)]:
        result = bash(fake_ldd + elf_check, scope=str(root), lib='/private/libs', portlib='/private/ports', CALL_RECORD=str(record), LDD_STATUS=str(status), LDD_OUTPUT=output)
        assert (result.returncode != 0) == rejected, result
        assert set(record.read_bytes().split(b'\0')[:-1]) == {os.fsencode(executable), os.fsencode(library)}
    executable.unlink(); library.unlink(); record.unlink()
    result = bash(fake_ldd + elf_check, scope=str(root), lib='/private/libs', portlib='/private/ports', CALL_RECORD=str(record), LDD_STATUS='0', LDD_OUTPUT='')
    assert result.returncode != 0 and not record.exists(), 'Empty ELF payload must fail before ldd'


guard = re.search(r'status=0\n.*?exit 1; }\n', source, re.S).group()
fake = '''pgrep() {
    [[ $1 == -f ]] || return 2
    [[ $PROCESS_ERROR == 0 ]] || return 2
    [[ $ARGV =~ $2 ]]
}
'''
for argv, expected in [('/usr/bin/es-de', 0), ('/usr/bin/retroarch -L ppsspp_libretro.so', 1),
                       ('/run/test/usr/bin/moonlight-qt stream host', 1),
                       ('/run/test/usr/bin/r46h-shell --fullscreen', 1),
                       ('/run/test/usr/bin/input-router /dev/input/event1 7 120', 1),
                       ('/run/test/usr/bin/weston --backend=drm', 1),
                       ('/usr/sbin/seatd -u ark', 1), ('/roms/ports/gta3/re3', 1),
                       ('/roms/ports/gtavc/reVC', 1), ('/run/test/mono/bin/mono-sgen game.exe', 1)]:
    assert bash(fake + guard, ARGV=argv, PROCESS_ERROR='0').returncode == expected
assert bash(fake + guard, ARGV='/usr/bin/es-de', PROCESS_ERROR='1').returncode == 1
entry = source[source.index('entry=('):source.index('unit_properties=()')]
for mode, expected in [('--run', ['/owned/session.sh', 'seat', '/owned/state/session.ABC', 'handheld']),
                       ('--remote', ['/owned/remote-session.sh', '192.0.2.2', '192.0.2.1', 'wayland', '/owned/state/session.ABC'])]:
    response = bash('set -- --remote hash key 192.0.2.2 192.0.2.1\n' + entry + '\nprintf "%s\\n" "${entry[@]}"',
                    scope='/owned', output='/owned/state/session.ABC', profile='handheld', mode=mode)
    assert response.returncode == 0 and response.stdout.splitlines() == expected, response

cache = repo / 'mainline/.cache'
cache.mkdir(exist_ok=True)
state_guard = source[source.index('ports_mode=0'):source.index('for service in r46h-gaming-input')]
for profile, persistent, installed, busy, user_status, expected in [
    ('handheld', '', False, False, 0, 0),
    ('windows', '/home/ark/.local/share/r46h-preview', False, False, 0, 2),
    ('handheld', '/arbitrary', True, False, 0, 2),
    ('handheld', '/home/ark/.local/share/r46h-preview', False, False, 0, 0),
    ('handheld', '/home/ark/.local/share/r46h-preview', True, False, 0, 0),
    ('handheld', '/home/ark/.local/share/r46h-preview', True, True, 0, 1),
    ('handheld', '/home/ark/.local/share/r46h-preview', True, False, 1, 1),
]:
    with tempfile.TemporaryDirectory(prefix='state.', dir=cache) as directory:
        folder = Path(directory)
        if installed:
            (folder / 'usr/share/r46h/ports').mkdir(parents=True)
            (folder / 'usr/share/r46h/ports/local_port.py').touch()
            (folder / 'runtime-lease.sh').touch()
            (folder / 'session-leases.sh').touch()
        if busy: (folder / 'lease').mkdir()
        code = state_guard.replace('/usr/bin/setpriv', 'setpriv').replace('/run/r46h-port-runtime', str(folder / 'lease'))
        response = bash('setpriv() { return "$USER_STATUS"; }; stat() { echo 0:0:755; }\n' + code + '\necho MODE=$ports_mode',
                        profile=profile, scope=str(folder), R46H_SHELL_STATE_DIR=persistent, USER_STATUS=str(user_status))
        assert response.returncode == expected, (profile, persistent, installed, busy, user_status, response)
        if expected == 0:
            assert response.stdout.strip() == ('MODE=1' if installed else 'MODE=0'), response
restore = source[source.index('restore() {'):source.index('trap restore EXIT')]
service = '''systemctl() {
    if [[ $1 == show ]]; then echo "$LOAD_STATE"; return; fi
    echo "CALL $*"
    case $1 in stop) return "$STOP_STATUS";; start) return "$START_STATUS";; is-active) return "$ACTIVE_STATUS";; --no-block) return "${POWER_STATUS:-0}";; esac
}
stat() {
    if [[ $1 == -c && $2 == %u:%g:%a ]]; then command stat -f '%u:%g:%Lp' "$3"; else echo "$SOCKET_ID"; fi
}
unit=r46h-wayland-probe-123.service
output=test-output
ports_mode=${PORTS_MODE:-0}
device_mode=${DEVICE_MODE:-0}
sync() { echo SYNC; }
'''
for socket_state, stop, load, start, active, result, expected, resumed in [
    ('absent', 0, 'loaded', 0, 0, 0, 0, True),
    ('owned', 0, 'loaded', 0, 0, 0, 0, True),
    ('changed', 0, 'loaded', 0, 0, 0, 1, False),
    ('owned', 1, 'loaded', 0, 0, 0, 1, False),
    ('absent', 1, 'not-found', 0, 0, 0, 0, True),
    ('absent', 0, 'loaded', 1, 0, 0, 1, True),
    ('absent', 0, 'loaded', 0, 3, 0, 1, True),
    ('owned', 0, 'loaded', 0, 0, 143, 143, True),
]:
    with tempfile.TemporaryDirectory(prefix='w.', dir=cache) as tmp:
        folder = Path(tmp)
        path = folder / 's'
        (folder / 'seatd-socket-identity').write_text('1:2\n')
        with socket.socket(socket.AF_UNIX) as sock:
            if socket_state != 'absent':
                sock.bind(str(path))
            code = restore.replace('/run/seatd.sock', str(path))
            response = bash(service + code + '\ntrap restore EXIT\nexit "$SESSION_STATUS"',
                            scope=str(folder), SOCKET_ID='2:3' if socket_state == 'changed' else '1:2',
                            STOP_STATUS=str(stop), LOAD_STATE=load, START_STATUS=str(start),
                            ACTIVE_STATUS=str(active), SESSION_STATUS=str(result))
            assert response.returncode == expected, response
            assert ('CALL start r46h-gaming-frontend.service' in response.stdout) == resumed, response
            if socket_state == 'changed':
                assert path.exists(), 'Must retain an unrelated socket'
            if socket_state == 'owned' and resumed:
                assert not path.exists(), 'Must clean a leftover owned socket'
with tempfile.TemporaryDirectory(prefix='r.', dir=cache) as directory:
    folder = Path(directory); output = folder
    runtime = output / 'runtime.r'; runtime.mkdir(mode=0o700)
    with socket.socket(socket.AF_UNIX) as sock: sock.bind(str(runtime / 's'))
    code = restore.replace('/run/seatd.sock', str(folder / 'absent'))
    identity = f'''id() {{ [[ $1 == -u ]] && echo {os.getuid()} || echo {os.getgid()}; }}\n'''
    response = bash(service + identity + 'output="$OUTPUT"\n' + code + '\ntrap restore EXIT\nexit 0',
                    scope=str(folder), OUTPUT=str(output), STOP_STATUS='0', LOAD_STATE='loaded',
                    START_STATUS='0', ACTIVE_STATUS='0', SOCKET_ID='unused')
    assert response.returncode == 0 and not runtime.exists(), response
for status in (0, 1):
    with tempfile.TemporaryDirectory(prefix='ports.', dir=cache) as directory:
        folder = Path(directory)
        (folder / 'session-leases.sh').write_text('echo "LEASE $*"\nexit ' + str(status) + '\n')
        code = restore.replace('/run/seatd.sock', str(folder / 'absent'))
        response = bash(service + code + '\ntrap restore EXIT\nexit 0', scope=str(folder), PORTS_MODE='1',
                        STOP_STATUS='0', LOAD_STATE='loaded', START_STATUS='0', ACTIVE_STATUS='0')
        assert response.returncode == status, response
        assert 'LEASE --restore r46h-wayland-probe-123.service 1 0' in response.stdout, response
        assert ('CALL start r46h-gaming-frontend.service' in response.stdout) == (status == 0), response

device_guard = source[source.index('device_mode='):source.index('for service in r46h-gaming-input')]
for mode, profile, online, installed, busy, expected in [
    ('0', 'windows', '0', False, False, 0), ('yes', 'handheld', '1', True, False, 2),
    ('1', 'windows', '1', True, False, 1), ('1', 'handheld', '0', True, False, 1),
    ('1', 'handheld', '1', False, False, 1), ('1', 'handheld', '1', True, True, 1),
    ('1', 'handheld', '1', True, False, 0),
]:
    with tempfile.TemporaryDirectory(prefix='device.', dir=cache) as directory:
        folder = Path(directory)
        if installed:
            (folder / 'device-lease.sh').touch(); (folder / 'session-leases.sh').touch()
        if busy: (folder / 'lease').mkdir()
        code = device_guard.replace('/run/r46h-device-lease', str(folder / 'lease'))
        result = bash('cat() { echo "$ONLINE"; }; stat() { echo 0:0:755; }\n' + code,
                      R46H_DEVICE_CONTROLS=mode, profile=profile, ONLINE=online, scope=str(folder), ports_mode='0')
        assert result.returncode == expected, (mode, profile, online, installed, busy, result)

# Use the actual lease-hook command body with task-owned scripts; no sysfs writes.
hook = (repo / 'mainline/gaming-wayland/session-leases.sh').read_text()
argument_guard = hook[:hook.index('base=')].replace('$EUID', '$TEST_UID')
for operation, unit, ports, device, uid, expected in [
    ('--acquire', 'r46h-wayland-probe-123.service', '1', '1', '0', 0),
    ('--restore', 'r46h-wayland-probe-123.service', '0', '1', '0', 0),
    ('--restore', 'unrelated.service', '1', '1', '0', 2),
    ('--restore', 'r46h-wayland-probe-123.service', '2', '1', '0', 2),
    ('--restore', 'r46h-wayland-probe-123.service', '1', '1', '1000', 2),
]:
    result = bash('set -- "$OP" "$UNIT" "$PORTS" "$DEVICE"\n' + argument_guard,
                  OP=operation, UNIT=unit, PORTS=ports, DEVICE=device, TEST_UID=uid)
    assert result.returncode == expected, result
commands = hook[hook.index('operation=$1'):]
with tempfile.TemporaryDirectory(prefix='leases.', dir=cache) as directory:
    folder = Path(directory)
    (folder / 'runtime-lease.sh').write_text('echo "PORT $*"\nexit "$PORT_STATUS"\n')
    (folder / 'device-lease.sh').write_text('echo "DEVICE $*"\nexit "$DEVICE_STATUS"\n')
    for operation in ('--acquire', '--restore'):
        for port_status, device_status in ((0, 0), (1, 0), (0, 1), (1, 1)):
            result = bash('set -- "$OP" r46h-wayland-probe-123.service 1 1\n' + commands,
                          base=str(folder), OP=operation, PORT_STATUS=str(port_status), DEVICE_STATUS=str(device_status))
            assert result.returncode == bool(port_status or device_status), result
            if operation == '--restore':
                assert result.stdout.splitlines() == ['PORT --release r46h-wayland-probe-123.service', 'DEVICE --restore r46h-wayland-probe-123.service'], result
            else:
                assert result.stdout.splitlines() == ['DEVICE --acquire r46h-wayland-probe-123.service'] + ([] if device_status else ['PORT --acquire r46h-wayland-probe-123.service']), result

for status, device, lease_status, power_status in [(77, 1, 0, 0), (78, 1, 0, 0), (77, 0, 0, 0),
                                                 (0, 1, 0, 0), (77, 1, 1, 0), (77, 1, 0, 1)]:
    with tempfile.TemporaryDirectory(prefix='power.', dir=cache) as directory:
        folder = Path(directory)
        (folder / 'session-leases.sh').write_text('echo "LEASE $*"\nexit ' + str(lease_status) + '\n')
        code = restore.replace('/run/seatd.sock', str(folder / 'absent'))
        result = bash(service + code + '\ntrap restore EXIT\nexit "$SESSION_STATUS"', scope=str(folder),
                      PORTS_MODE='1', DEVICE_MODE=str(device), SESSION_STATUS=str(status), POWER_STATUS=str(power_status),
                      STOP_STATUS='0', LOAD_STATE='loaded', START_STATUS='0', ACTIVE_STATUS='0')
        power = device and status in (77, 78) and not lease_status
        assert ('CALL --no-block' in result.stdout) == bool(power), result
        assert ('CALL start r46h-gaming-frontend.service' in result.stdout) == (not lease_status and (not power or bool(power_status))), result
        if power:
            assert result.stdout.index('LEASE --restore') < result.stdout.index('SYNC') < result.stdout.index('CALL --no-block'), result
        assert result.returncode == (1 if lease_status or power_status else 0 if power else status), result

hooks = source[source.index('unit_properties=()'):source.index('restore() {')]
for ports, device in ((0, 0), (1, 0), (0, 1), (1, 1)):
    result = bash(hooks + '\nif (( ports_mode || device_mode )); then printf "%s\\n" "${unit_properties[@]}"; fi', scope='/owned',
                  unit='r46h-wayland-probe-123.service', ports_mode=str(ports), device_mode=str(device))
    assert result.returncode == 0, result
    if ports or device:
        assert result.stdout.splitlines() == ['-p', f'ExecStartPre=/bin/bash /owned/session-leases.sh --acquire r46h-wayland-probe-123.service {ports} {device}',
                                             '-p', f'ExecStopPost=/bin/bash /owned/session-leases.sh --restore r46h-wayland-probe-123.service {ports} {device}'], result

assert '-p RuntimeMaxSec=360 -p TimeoutStopSec=10 -p KillMode=control-group' in source
assert "trap 'exit 129' HUP" in source
assert 'sha256sum --check --quiet SHA256SUMS' in source
session = repo / 'mainline/gaming-wayland/session.sh'
login_environment = session.read_text().split('session_user=', 1)[1].split('umask 077', 1)[0]
login_environment = 'session_user=' + login_environment
for inherited in ('unset', '/root'):
    prefix = 'unset HOME USER LOGNAME\n' if inherited == 'unset' else 'export HOME=/root USER=root LOGNAME=root\n'
    account = 'id() { case "$1" in -u) echo 1000;; -un) echo ark;; *) return 1;; esac; }\n'
    for home in ('/home/ark', '/home/user space', '', 'relative'):
        result = bash(prefix + account + 'getent() { printf "ark:x:1000:1000::%s:/bin/bash\\n" "$ACCOUNT_HOME"; }\n' +
                      login_environment + '\nprintf "%s\\n" "$HOME" "$USER" "$LOGNAME" "$R46H_DEVICE_CONTROLS"',
                      ACCOUNT_HOME=home, R46H_DEVICE_CONTROLS='1')
        assert (result.returncode == 0) == home.startswith('/'), result
        if result.returncode == 0: assert result.stdout.splitlines() == [home, 'ark', 'ark', '1'], result
for mode, output in [('invalid', '/unused'), ('headless', str(cache / 'not allowed'))]:
    result = subprocess.run(['/bin/sh', str(session), mode, output], capture_output=True, timeout=5)
    assert result.returncode == 2
assert subprocess.run(['/bin/sh', str(session), 'headless', '/unused', 'invalid'],
                      capture_output=True, timeout=5).returncode == 2
spec = importlib.util.spec_from_file_location('wayland_bundle', repo / 'mainline/gaming-wayland/build-in-container.py')
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)
with tempfile.TemporaryDirectory(prefix='seal.', dir=cache) as tmp:
    root = Path(tmp); payload = root / 'payload'; payload.mkdir()
    licenses = payload / 'LICENSES'; licenses.mkdir(); licenses.chmod(0o775)
    license_file = licenses / 'license.txt'; license_file.write_text('retained'); license_file.chmod(0o664)
    outside = root / 'outside'; outside.write_text('untouched'); outside.chmod(0o664)
    (payload / 'link').symlink_to(outside)
    bundle.seal_payload(payload)
    assert licenses.stat().st_mode & 0o777 == 0o755
    assert license_file.stat().st_mode & 0o777 == 0o644 and license_file.read_text() == 'retained'
    assert outside.stat().st_mode & 0o777 == 0o664
reference = {'package': 'libcap2', 'container_version': 'old', 'target_version': 'retained-target'}
with patch.object(bundle, 'capture', return_value='current-container\n') as query:
    record = bundle.provider_record(reference)
    query.assert_called_once_with('dpkg-query', '-W', '-f=${Version}', 'libcap2')
assert record == {**reference, 'container_version': 'current-container'}
assert reference['container_version'] == 'old'
with patch.object(bundle, 'capture', side_effect=subprocess.CalledProcessError(1, 'dpkg-query')):
    try:
        bundle.provider_record(reference)
    except subprocess.CalledProcessError:
        pass
    else:
        raise AssertionError('Missing live package metadata must fail closed')
print('WAYLAND_PROBE_CHECK PASS: guards/recovery and fresh package provenance (host mocks)')
