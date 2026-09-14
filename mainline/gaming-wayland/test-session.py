#!/usr/bin/env python3
"""Run the real session/client scripts as nobody using only synthetic Linux input."""
import base64
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import pwd
import signal
import socket
import subprocess
import sys
import tempfile
import time

assert Path('/.dockerenv').exists() and os.geteuid() == 0
spec = importlib.util.spec_from_file_location('routing', Path(__file__).with_name('test-input-router.py'))
fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
base = Path(sys.argv[1]).resolve()
stream_mode = len(sys.argv) == 3 and sys.argv[2] == '--stream-ui'
out = Path('/out/stream-session' if stream_mode else '/out/session'); out.mkdir(exist_ok=True)
user = pwd.getpwnam('nobody')


def wait_for(check, message, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check(): return
        time.sleep(.04)
    raise AssertionError(message)


with tempfile.TemporaryDirectory(prefix='r46h-session-', dir='/run') as directory:
    state = Path(directory); os.chown(state, user.pw_uid, user.pw_gid)
    environment = {**os.environ, 'R46H_SHELL_STATE_DIR': ''}
    persistent = state / 'persistent'
    if stream_mode:
        persistent.mkdir(mode=0o700); os.chown(persistent, user.pw_uid, user.pw_gid)
        environment['R46H_SHELL_STATE_DIR'] = str(persistent)
    pad = fixture.Pad(); os.chown(pad.path, user.pw_uid, user.pw_gid)
    # A preceding root-only check can leave its synthetic /dev/input directory 0700.
    pad.path.parent.chmod(0o755)
    fd = os.open('/dev/uinput', os.O_WRONLY | os.O_CLOEXEC)
    delegated = fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 7); os.close(fd)
    assert delegated == 7
    os.rename('/dev/uinput', '/dev/uinput.hidden')
    log = (out / 'session.log').open('w')
    process = subprocess.Popen([str(base / 'session.sh'), 'headless', str(state), 'handheld'],
        env={**environment, 'R46H_ROUTED_SOURCE': str(pad.path)}, user=user.pw_uid, group=user.pw_gid,
        extra_groups=[], pass_fds=(7,), start_new_session=True, stdout=log, stderr=subprocess.STDOUT)
    os.close(7)
    routed = None
    endpoint = state / 'control/control.sock'

    def request(action=None, capture=False):
        command = {'version': 1, 'id': 'session', 'op': 'observe', 'screenshot': capture}
        if action:
            previous = request()
            command.update({key: previous[key] for key in ('session', 'sequence', 'binary_sha256')})
            command.update(op='tap', action=action)
        # The real private endpoint requires the client's UID to match the GUI.
        os.seteuid(user.pw_uid)
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                connection.settimeout(4); connection.connect(str(endpoint))
                connection.sendall(json.dumps(command).encode() + b'\n')
                response = bytearray()
                while block := connection.recv(65536):
                    response += block
                    assert len(response) < 16 * 1024 * 1024
        finally: os.seteuid(0)
        result = json.loads(response); assert result['ok'], result
        return result

    def ready(): return request()['state']['sharedReady']

    def uinput_handles(pid):
        # The test container alone grants SYS_PTRACE to inspect the other UID.
        result = []
        for path in Path(f'/proc/{pid}/fd').iterdir():
            try: target = path.readlink()
            except FileNotFoundError: continue
            if str(target) == '/dev/uinput.hidden': result.append(path.name)
        return result

    def children(pid): return Path(f'/proc/{pid}/task/{pid}/children').read_text().split()

    try:
        wait_for(lambda: endpoint.exists() or process.poll() is not None, 'Session did not start')
        assert process.poll() is None, (out / 'session.log').read_text()
        wait_for(ready, 'Unprivileged desktop did not become ready')
        peers = children(process.pid)
        weston = next(int(pid) for pid in peers if Path(f'/proc/{pid}/comm').read_text().strip() == 'weston')
        gui = next(int(pid) for pid in peers if Path(f'/proc/{pid}/comm').read_text().strip() == 'r46h-shell')
        assert not uinput_handles(process.pid) and not uinput_handles(weston) and not uinput_handles(gui)
        routers = children(gui); assert len(routers) == 1 and len(uinput_handles(routers[0])) == 1
        paths = [p.parent for p in Path('/sys/devices/virtual/input').glob('input*/name') if p.read_text().strip() == 'R46H Routed Gamepad']
        assert len(paths) == 1
        routed = fixture.event_node(paths[0].name); os.chown(routed, user.pw_uid, user.pw_gid)
        game = None
        if stream_mode:
            assert request()['state']['streamingOpen'] and request()['state']['selectedApplication'] == 'builtin.moonlight'
            request('accept'); wait_for(lambda: request()['state']['editing'], 'Add-host editor did not open')
            wait_for(lambda: request()['state']['keyboardReady'], 'Packaged Wayland keyboard module did not load')
            response = request(capture=True); assert response['capture']['status'] == 'sensitive_entry'
            assert 'png_base64' not in response['capture']
            request('back'); wait_for(lambda: not request()['state']['editing'], 'Private editor did not close')
            request('back'); assert not request()['state']['streamingOpen']
            request('favorite')
            response = request(capture=True); assert response['capture']['status'] == 'ok'
            (out / 'home.png').write_bytes(base64.b64decode(response['capture']['png_base64']))
            assert 'unavailable' not in (state / 'clients.log').read_text().lower()
        else:
            request('accept')
            wait_for(lambda: request()['state']['externalSession'] and ready(), 'Diagnostic child did not launch')
            time.sleep(.5)
            game = next(int(pid) for pid in children(gui) if pid != routers[0])
            assert not uinput_handles(game)
            pad.emit((1, fixture.KEYS[14], 1), (1, fixture.KEYS[15], 1)); time.sleep(.05)
            pad.emit((1, fixture.KEYS[14], 0), (1, fixture.KEYS[15], 0))
            wait_for(lambda: request()['state']['quickOpen'] and ready(), 'L3+R3 did not open panel')
            response = request(capture=True); assert response['capture']['status'] == 'ok'
            (out / 'panel.png').write_bytes(base64.b64decode(response['capture']['png_base64']))
            request('back'); wait_for(lambda: not request()['state']['quickOpen'] and ready(), 'B did not resume child')
        # Compositor loss must fail the GUI and unwind this actual shell-script stack.
        os.kill(weston, signal.SIGTERM)
        assert process.wait(timeout=8) != 0
        wait_for(lambda: not paths[0].exists(), 'Routed endpoint survived session teardown')
        wait_for(lambda: not Path(f'/proc/{gui}').exists() and (game is None or not Path(f'/proc/{game}').exists()),
                 'GUI or game survived session teardown')
        assert not list(state.glob('runtime.*')), 'Private runtime survived cleanup'
        if stream_mode:
            assert (persistent / 'preview.json').is_file() and not (state / 'ui-state').exists(), 'Explicit state was ignored or removed'
        receipt = {'status': 'UNPRIVILEGED_STREAM_UI_HOST_PASS' if stream_mode else 'UNPRIVILEGED_SESSION_HOST_PASS', 'uid': user.pw_uid,
            'checks': ['delegated uinput without device path', 'no parent/compositor/GUI/game handle leak',
                *(['built-in management and private editor, public capture after close', 'explicit state survives compositor failure'] if stream_mode else ['separate diagnostic app', 'L3+R3 panel and B resume']), 'compositor loss cleanup'],
            'boundary': 'Headless container only; root seatd, target cgroup and physical DRM/input remain untested'}
        (out / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(receipt['status'] + ': real launcher, delegated input, privacy or panel/resume, compositor-loss cleanup')
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=3)
        for name in ('clients.log', 'weston.log', 'weston-stderr.log'):
            if (state / name).exists(): (out / name).write_bytes((state / name).read_bytes())
        log.close()
        if routed: routed.unlink()
        pad.close(); os.rename('/dev/uinput.hidden', '/dev/uinput')

if not stream_mode:
    # Exercise the real unprivileged session/client wrappers, substituting only
    # the final GUI executable with its documented power-request exit codes.
    launcher = base / 'shell-client.sh'
    original = launcher.read_bytes()
    power_results = []
    try:
        for code in (77, 78):
            launcher.write_text('#!/bin/sh\nprintf "DEVICE_FLAG=%s\\n" "${R46H_DEVICE_CONTROLS:-unset}"\nexit ' + str(code) + '\n')
            with tempfile.TemporaryDirectory(prefix='r46h-power-exit-', dir='/run') as directory:
                state = Path(directory); os.chown(state, user.pw_uid, user.pw_gid)
                pad = fixture.Pad(); os.chown(pad.path, user.pw_uid, user.pw_gid)
                fd = os.open('/dev/uinput', os.O_WRONLY | os.O_CLOEXEC)
                delegated = fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, 7); os.close(fd)
                assert delegated == 7
                process = subprocess.Popen([str(base / 'session.sh'), 'headless', str(state), 'handheld'],
                    env={**os.environ, 'R46H_ROUTED_SOURCE': str(pad.path), 'R46H_DEVICE_CONTROLS': '1'},
                    user=user.pw_uid, group=user.pw_gid, extra_groups=[], pass_fds=(7,),
                    start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                os.close(7)
                try:
                    stdout, _ = process.communicate(timeout=10)
                    assert process.returncode == code, (code, process.returncode, stdout)
                    assert (state / 'clients.log').read_text().strip() == 'DEVICE_FLAG=1'
                    assert not list(state.glob('runtime.*')), 'Power request left its compositor runtime'
                    power_results.append({'guiExitCode': code, 'sessionExitCode': process.returncode})
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=3)
                    pad.close()
    finally:
        launcher.write_bytes(original)
    (out / 'power-exits.json').write_text(json.dumps(power_results, indent=2) + '\n')
    print('SHARED_POWER_EXIT_PASS: actual session wrappers preserve device mode and GUI 77/78; no system power action')
