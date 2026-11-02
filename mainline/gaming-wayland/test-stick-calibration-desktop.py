#!/usr/bin/env python3
"""Real Qt calibration workflow and persisted broker application; synthetic pad only."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

assert Path('/.dockerenv').exists()
spec = importlib.util.spec_from_file_location('routing', Path(__file__).with_name('test-input-router.py'))
routing = importlib.util.module_from_spec(spec); spec.loader.exec_module(routing)
out = Path('/out/calibration-desktop'); out.mkdir(exist_ok=True)


def wait_for(check, message, seconds=6):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check(): return
        time.sleep(.03)
    raise AssertionError(message)


with tempfile.TemporaryDirectory(prefix='stick-calibration-', dir='/run') as directory:
    state = Path(directory); pad = routing.Pad(); shell = restart_compositor = None
    settings = state / 'settings'; settings.mkdir(mode=0o700)
    saved = settings / 'stick-calibration.json'
    saved.write_text(json.dumps({'version': 1, 'enabled': True, 'axes': [[-30000, 1000, 30000]] * 4}))
    endpoint = None
    generation = 0
    log = (out / 'shell.log').open('w')

    def observe(action=None):
        request = {'version': 1, 'id': 'calibration', 'op': 'observe', 'screenshot': False}
        if action:
            prior = observe()
            request.update({key: prior[key] for key in ('session', 'sequence', 'binary_sha256')})
            request.update(op='tap', action=action)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            channel.settimeout(3); channel.connect(str(endpoint))
            channel.sendall(json.dumps(request).encode() + b'\n')
            data = bytearray()
            while block := channel.recv(65536):
                data += block
                assert len(data) < 1048576
        reply = json.loads(data); assert reply['ok'], reply
        return reply

    def start(scene):
        global endpoint, generation, shell
        generation += 1
        control = state / ('control-' + str(generation)); endpoint = control / 'control.sock'
        handles = routing.delegated_slots()
        try:
            shell = subprocess.Popen(['/out/linux-build/r46h-shell', '--state-dir', str(settings),
                '--control-dir', str(control), '--scene', scene, '--fullscreen', '--quit-after', '45',
                '--handheld-router', '/out/input-router', '--input-device', str(pad.path), '--uinput-fd=' + str(handles[0])],
                pass_fds=handles, stdout=log, stderr=subprocess.STDOUT)
        finally:
            for fd in handles: os.close(fd)
        wait_for(lambda: endpoint.exists() or shell.poll() is not None, 'No Qt control endpoint')
        assert shell.poll() is None, (out / 'shell.log').read_text()
        wait_for(lambda: observe()['state']['sharedReady'], 'Desktop input handshake failed')
        return shell

    try:
        shell = start('settings')
        for _ in range(3): observe('down')
        observe('right')
        wait_for(lambda: observe()['state']['settingsDetailReady'], 'Controller settings missing')
        observe('down'); observe('down'); observe('accept')
        time.sleep(.7); observe('accept')
        lows = [-24000, -27000, -21000, -25000]; highs = [28000, 22000, 26000, 23000]
        pad.emit(*((3, axis, value - 1) for axis, value in zip(routing.AXES, lows))); time.sleep(.08)
        pad.emit(*((3, axis, value) for axis, value in zip(routing.AXES, highs))); time.sleep(.08)
        observe('accept')
        pad.emit(*((3, axis, 0) for axis in routing.AXES)); time.sleep(.08)
        observe('accept')
        expected = {'version': 1, 'enabled': True, 'axes': [[low, 0, high] for low, high in zip(lows, highs)]}
        wait_for(lambda: json.loads(saved.read_text()) == expected, 'Raw calibration was not saved through the UI')
        wait_for(lambda: observe()['state']['sharedReady'], 'Saved calibration was not acknowledged')
        assert observe()['state']['settingsIndex'] == 2
        pad.emit((3, 1, 16000))
        wait_for(lambda: observe()['state']['settingsIndex'] == 3, 'New calibration did not apply live')
        pad.emit((3, 1, 0)); time.sleep(.08)
        shell.terminate(); shell.wait(timeout=5); shell = None
        # Installed session restart replaces the compositor as well as the UI.
        runtime = state / 'restart-runtime'; runtime.mkdir(mode=0o700)
        os.environ.update(XDG_RUNTIME_DIR=str(runtime), WAYLAND_DISPLAY='calibration-restart')
        restart_compositor = subprocess.Popen(['weston', '--backend=headless', '--renderer=pixman',
            '--width=1024', '--height=768', '--idle-time=0', '--no-config', '--socket=calibration-restart',
            '--shell=/out/handheld-shell.so', '--log=' + str(out / 'restart-weston.log')],
            env={**os.environ, 'EGL_PLATFORM': 'surfaceless'}, stdout=log, stderr=subprocess.STDOUT)
        wait_for(lambda: (runtime / 'calibration-restart').exists(), 'Replacement compositor not ready')
        shell = start('home')
        before = observe()['state']['homeIndex']
        # 16000 is below the uncalibrated 55% UI threshold, above the calibrated threshold.
        pad.emit((3, 0, 16000))
        wait_for(lambda: observe()['state']['homeIndex'] == before + 1, 'Saved calibration did not reach the restarted broker')
        pad.emit((3, 0, 0))
        assert not any(error in (out / 'shell.log').read_text() for error in ('No such method', 'TypeError', 'ReferenceError'))
        result = {'status': 'STICK_CALIBRATION_DESKTOP_HOST_PASS', 'profile': expected,
                  'checks': ['raw capture while previously calibrated', 'UI save', 'live IPC acknowledgment', 'restart persistence and corrected navigation'],
                  'boundary': 'Qt/Wayland and synthetic uinput, not a physical R46H calibration'}
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(result['status'])
    finally:
        if shell and shell.poll() is None:
            shell.terminate()
            try: shell.wait(timeout=5)
            except subprocess.TimeoutExpired: shell.kill(); shell.wait(timeout=3)
        if restart_compositor:
            restart_compositor.terminate(); restart_compositor.wait(timeout=3)
        pad.close(); log.close()
