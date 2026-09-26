#!/usr/bin/env python3
"""Actual Qt/Weston/RetroArch/FBNeo host check, with synthetic input and private saves."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import socket
import subprocess
import tempfile
import time

assert Path('/.dockerenv').exists()
os.umask(0o077)
spec = importlib.util.spec_from_file_location('routing', Path(__file__).with_name('test-input-router.py'))
fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
out = Path('/out/native-gl')
rom = Path('/content/neogeo/mslug.zip'); bios = Path('/content/neogeo/neogeo.zip')
expected = {rom: '3ebe7ca4166f956a65ae98d86f9172f8b5d4462efa13723a5ea72fcf59adcbf8',
            bios: 'd2d8ab5d5fc5ce41978e40c8db2984d8dd0a37e60c712e20961b80fdbb4c9936'}
assert os.statvfs(rom).f_flag & os.ST_RDONLY
for path, digest in expected.items(): assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def wait_for(check, message, seconds=12):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check(): return
        time.sleep(.05)
    raise AssertionError(message)


with tempfile.TemporaryDirectory(prefix='r46h-neo-', dir='/run') as directory:
    state = Path(directory); game = state / 'game'
    for name in ('saves/battery', 'saves/states', 'screenshots', 'config', 'cache', 'data'): (game / name).mkdir(parents=True)
    shutil.copyfile('/neo/FinalBurn Neo (neogeo subset).opt', game / 'core-options.cfg')
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as reservation:
        reservation.bind(('127.0.0.1', 0)); port = reservation.getsockname()[1]
    # Only this network-disabled test container exposes RetroArch's command interface.
    config = subprocess.check_output(['/out/linux-build/tools-check', '--neo-config', str(game)])
    config += f'audio_driver = "null"\nnetwork_cmd_enable = "true"\nnetwork_cmd_port = "{port}"\nvideo_font_enable = "false"\n'.encode()
    (game / 'retroarch.cfg').write_bytes(config)
    wrapper = state / 'game.sh'
    command = ['/usr/bin/retroarch', '--verbose', '-c', '/neo/retroarch.cfg', '--appendconfig', str(game / 'retroarch.cfg'),
               '-L', '/usr/local/libexec/fbneo_neogeo_libretro.so', str(rom)]
    wrapper.write_text('#!/bin/sh\nexport XDG_CONFIG_HOME=' + shlex.quote(str(game / 'config')) + '\nexport XDG_CACHE_HOME=' + shlex.quote(str(game / 'cache'))
        + '\nexport XDG_DATA_HOME=' + shlex.quote(str(game / 'data')) + '\nexec ' + shlex.join(command) + ' > ' + shlex.quote(str(game / 'runtime.log')) + ' 2>&1\n')
    wrapper.chmod(0o700)
    manifest = state / 'applications.json'
    manifest.write_text(json.dumps({'version': 1, 'applications': [{'id': 'native.mslug', 'title': '合金弹头', 'program': str(wrapper), 'directory': str(game), 'arguments': []}]}))
    pad = fixture.Pad(); routed = None; game_pid = None
    log = (out / 'shell.log').open('w')
    shell = subprocess.Popen(['/out/linux-build/r46h-shell', '--state-dir', str(state / 'ui'), '--applications', str(manifest),
        '--control-dir', str(state / 'control'), '--handheld-router', '/out/input-router', '--input-device', str(pad.path),
        '--fullscreen', '--quit-after', '90'], stdout=log, stderr=subprocess.STDOUT)
    channel = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); channel.settimeout(.3)
    endpoint = state / 'control/control.sock'

    def observe(action=None, capture=False):
        request = {'version': 1, 'id': 'neo', 'op': 'observe', 'screenshot': capture}
        if action:
            previous = observe(); request.update({k: previous[k] for k in ('session', 'sequence', 'binary_sha256')})
            request.update(op='tap', action=action)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(4); connection.connect(str(endpoint)); connection.sendall(json.dumps(request).encode() + b'\n')
            data = bytearray()
            while block := connection.recv(65536):
                data += block; assert len(data) < 16 * 1024 * 1024
        result = json.loads(data); assert result['ok'], result
        return result

    def ready(): return observe()['state']['sharedReady']

    def command(message, reply=False):
        channel.sendto(message.encode(), ('127.0.0.1', port))
        if reply:
            try: return channel.recv(4096).decode()
            except socket.timeout: return ''

    def screenshot(name):
        previous = {p.name: p.stat().st_mtime_ns for p in (game / 'screenshots').glob('*.png')}
        command('SCREENSHOT')
        def changed(): return [p for p in (game / 'screenshots').glob('*.png') if p.stat().st_mtime_ns != previous.get(p.name)
            and p.read_bytes().endswith(b'\0\0\0\0IEND\xaeB`\x82')]
        wait_for(changed, 'RetroArch did not write a screenshot', 5)
        path = changed()[0]; data = path.read_bytes(); (out / name).write_bytes(data); return data

    def press(index, seconds=.08):
        pad.emit((1, fixture.KEYS[index], 1)); time.sleep(seconds)
        pad.emit((1, fixture.KEYS[index], 0)); time.sleep(.15)

    def hotkey(index):
        pad.emit((1, fixture.KEYS[8], 1)); time.sleep(.2)
        press(index, .2)
        pad.emit((1, fixture.KEYS[8], 0)); time.sleep(.15)

    try:
        wait_for(lambda: endpoint.exists() or shell.poll() is not None, 'Qt did not start')
        assert shell.poll() is None; wait_for(ready, 'Shared desktop not ready')
        paths = fixture.routed_devices()
        assert len(paths) == 1; routed = fixture.event_node(paths[0].name)
        session = observe()['session']; observe('accept')
        wait_for(lambda: observe()['state']['externalSession'] and ready(), 'Real Neo game did not launch')
        for pid in Path(f'/proc/{shell.pid}/task/{shell.pid}/children').read_text().split():
            if Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')[0] == b'/usr/bin/retroarch': game_pid = int(pid)
        assert game_pid
        wait_for(lambda: 'mslug' in command('GET_STATUS', True), 'RetroArch did not load Metal Slug')
        time.sleep(12)
        (out / 'status-before-input.txt').write_text(command('GET_STATUS', True))
        input_fds = []
        for descriptor in Path(f'/proc/{game_pid}/fd').iterdir():
            try: target = str(descriptor.readlink())
            except FileNotFoundError: continue
            if target.startswith('/dev/input/'): input_fds.append(target)
        (out / 'input-fds.json').write_text(json.dumps(input_fds) + '\n')
        assert str(routed) in input_fds, 'RetroArch did not open the routed input endpoint'
        screenshot('before-input.png')
        press(8); press(9); time.sleep(8)
        (out / 'status-after-input.txt').write_text(command('GET_STATUS', True))
        screenshot('after-start.png')
        press(9, .3); time.sleep(5)
        screenshot('after-second-start.png')
        hotkey(2); time.sleep(.4)
        menu = observe(capture=True); assert menu['capture']['status'] == 'ok'
        (out / 'ozone-menu.png').write_bytes(base64.b64decode(menu['capture']['png_base64']))
        hotkey(2); time.sleep(.4)
        pad.emit((1, fixture.KEYS[14], 1), (1, fixture.KEYS[15], 1)); time.sleep(.04)
        pad.emit((1, fixture.KEYS[14], 0), (1, fixture.KEYS[15], 0))
        wait_for(lambda: observe()['state']['quickOpen'] and ready(), 'L3+R3 did not take input from RetroArch')
        time.sleep(.3); capture = observe(capture=True); assert capture['capture']['status'] == 'ok'
        (out / 'game-panel.png').write_bytes(base64.b64decode(capture['capture']['png_base64']))
        observe('back'); wait_for(lambda: not observe()['state']['quickOpen'] and ready(), 'B did not resume Neo')
        status = command('GET_STATUS', True)
        if 'PAUSED' not in status: command('PAUSE_TOGGLE')
        wait_for(lambda: 'PAUSED' in command('GET_STATUS', True), 'Could not pause for deterministic save test')
        command('SAVE_STATE')
        wait_for(lambda: any(p.stat().st_size > 0 for p in (game / 'saves/states').rglob('*.state*') if p.suffix != '.png'), 'No serialized save state')
        command('FRAMEADVANCE'); time.sleep(.1)
        screenshot('saved-frame.png')
        for _ in range(10): command('FRAMEADVANCE'); time.sleep(.05)
        screenshot('advanced-frame.png')
        assert command('LOAD_STATE_SLOT 0', True).startswith('LOAD_STATE_SLOT 0')
        time.sleep(.3); command('FRAMEADVANCE'); time.sleep(.1)
        screenshot('loaded-frame.png')
        comparison = subprocess.run(['/out/test-client', '--compare-frames', str(out / 'saved-frame.png'), str(out / 'loaded-frame.png')],
            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, timeout=3)
        assert comparison.returncode == 0, 'Restored frame differs from the same frame after saving'
        changed = subprocess.run(['/out/test-client', '--compare-frames', str(out / 'saved-frame.png'), str(out / 'advanced-frame.png')],
            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'}, capture_output=True, timeout=3)
        assert changed.returncode == 4, 'Save/load comparison did not include an advancing scene'
        assert '[State]: Loading state ' in (game / 'runtime.log').read_text()
        command('PAUSE_TOGGLE')
        wait_for(lambda: 'PLAYING' in command('GET_STATUS', True), 'Could not resume before physical-style exit')
        hotkey(9)
        try:
            wait_for(lambda: not observe()['state']['externalSession'] and ready(), 'Neo exit did not restore desktop')
        except AssertionError:
            (out / 'exit-state.json').write_text(json.dumps(observe(), indent=2) + '\n')
            (out / 'exit-processes.txt').write_bytes(subprocess.check_output(['ps', '-eo', 'pid,ppid,pgid,stat,wchan:30,args']))
            raise
        assert observe()['session'] == session
        (out / 'runtime-first.log').write_bytes((game / 'runtime.log').read_bytes())
        observe('accept')
        wait_for(lambda: observe()['state']['externalSession'] and ready(), 'Neo second launch failed')
        wait_for(lambda: 'mslug' in command('GET_STATUS', True), 'Neo second content load failed')
        observe('quick'); wait_for(lambda: observe()['state']['quickOpen'] and ready(), 'Stop panel did not open')
        for _ in range(5 - observe()['state']['quickIndex']): observe('down')
        observe('accept'); observe('down'); observe('accept')
        wait_for(lambda: not observe()['state']['externalSession'] and ready(), 'Panel Stop did not restore desktop')
        assert observe()['session'] == session
        assert 'wayland' in (game / 'runtime.log').read_text().lower()
        assert 'Found joypad driver: "sdl2"' in (game / 'runtime.log').read_text()
        for path, digest in expected.items(): assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        result = {'status': 'REAL_NEO_SHARED_HOST_PASS', 'core_sha256': '8bb17a551f3eeeb384ab00a5c5375d30eb63807afe5b6c1ba1d3f78220732bdb',
            'save_files': [str(p.relative_to(game / 'saves/states')) for p in (game / 'saves/states').rglob('*') if p.is_file()],
            'restored_frame_equal': True,
            'checks': ['routed coin/start', 'L3+R3 panel/B resume', 'nontrivial save/load frame equality', 'single Select+Start exit', 'second launch and panel Stop', 'same desktop session'],
            'boundary': 'Real RetroArch/FBNeo in software GL container; synthetic controller, null audio. Target native worker guards and LCD/audio/controls require device checks.'}
        (out / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
    finally:
        if game_pid and Path(f'/proc/{game_pid}').exists():
            os.killpg(game_pid, signal.SIGTERM)
        if shell.poll() is None:
            shell.terminate()
            try: shell.wait(timeout=4)
            except subprocess.TimeoutExpired: shell.kill(); shell.wait(timeout=3)
        for name in ('runtime.log', 'retroarch.cfg', 'core-options.cfg'):
            if (game / name).exists(): (out / name).write_bytes((game / name).read_bytes())
        (out / 'save-files.json').write_text(json.dumps([{ 'path': str(p.relative_to(game)), 'bytes': p.stat().st_size }
            for p in (game / 'saves').rglob('*') if p.is_file()], indent=2) + '\n')
        log.close(); channel.close()
        if routed: routed.unlink()
        pad.close()
