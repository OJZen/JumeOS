#!/usr/bin/env python3
"""Actual Qt desktop + input router + Weston + synthetic SDL game, container only."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import signal
import threading
import sys
import stat

spec = importlib.util.spec_from_file_location('routing_test', Path(__file__).with_name('test-input-router.py'))
fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
assert Path('/.dockerenv').exists()
os.umask(0o077)
out = Path('/out/desktop'); out.mkdir(exist_ok=True)


def wait_for(check, message, seconds=5):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if check(): return
        time.sleep(.03)
    raise AssertionError(message)


with tempfile.TemporaryDirectory(prefix='r46h-ui-', dir='/run') as directory:
    state = Path(directory)
    apps = state / 'applications.json'
    # The test game needs only the private client plugin, not the desktop's keyboard/runtime.
    wrapper = state / 'game.sh'
    wrapper.write_text('#!/bin/sh\nexport QT_PLUGIN_PATH=/out/qt-wayland/usr/lib/aarch64-linux-gnu/qt6/plugins\nexport LD_LIBRARY_PATH=/out/qt-wayland/usr/lib/aarch64-linux-gnu\nexec /out/test-client game ' + str(state / 'game-state.json') + '\n')
    wrapper.chmod(0o700)
    apps.write_text(json.dumps({'version': 1, 'applications': [{'id': 'test.game', 'title': '合成手柄测试', 'program': str(wrapper), 'arguments': []}]}))
    pad = fixture.Pad(); routed = None; stream_compositor = None
    logfile = (out / 'shell.log').open('w')
    delegated = os.open('/dev/uinput', os.O_WRONLY | os.O_CLOEXEC)
    # Remove only our container-created path: even root cannot silently fall back to opening it.
    os.rename('/dev/uinput', '/dev/uinput.hidden')
    try:
        shell = subprocess.Popen(['/out/linux-build/r46h-shell', '--state-dir', str(state / 'settings'), '--control-dir', str(state / 'control'),
            '--applications', str(apps), '--scene', 'input', '--handheld-router', '/out/input-router', '--input-device', str(pad.path),
            '--uinput-fd=' + str(delegated), '--fullscreen', '--quit-after', '90'], pass_fds=(delegated,), stdout=logfile, stderr=subprocess.STDOUT)
    finally:
        os.close(delegated)
    endpoint = state / 'control/control.sock'

    def observe(capture=False, action=None):
        request = {'version': 1, 'id': 'desktop', 'op': 'observe', 'screenshot': capture}
        if action:
            prior = observe()
            request.update({key: prior[key] for key in ('session', 'sequence', 'binary_sha256')})
            request.update(op='tap', action=action)
        return exchange(request)

    def exchange(request, expect_ok=True):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            channel.settimeout(3); channel.connect(str(endpoint)); channel.sendall(json.dumps(request).encode() + b'\n')
            raw = bytearray()
            while block := channel.recv(65536):
                raw += block
                assert len(raw) < 16 * 1024 * 1024
        response = json.loads(raw)
        if expect_ok: assert response['ok'], response
        return response

    def game_request(buttons=(), axes=(0., 0., 0., 0.), milliseconds=300, capture=False):
        prior = observe()
        return {'version': 1, 'id': 'game-input', 'op': 'game-input', 'screenshot': capture,
            **{key: prior[key] for key in ('session', 'sequence', 'binary_sha256')},
            'application': prior['state']['activeApplication'], 'input_sequence': prior['state']['inputSequence'],
            'buttons': list(buttons), 'axes': list(axes), 'duration_ms': milliseconds}

    def pending(request):
        replies, errors = [], []
        def run():
            try: replies.append(exchange(request))
            except Exception as error: errors.append(str(error))
        thread = threading.Thread(target=run); thread.start()
        return thread, replies, errors

    def completed(job, status):
        thread, replies, errors = job; thread.join(timeout=4)
        assert not thread.is_alive() and not errors and len(replies) == 1, errors
        response = replies[0]
        assert response['input_backend'] == 'routed-uinput' and response['input_status'] == status, response
        return response

    def ready():
        return observe()['state']['sharedReady']

    def press(index, duration=.04):
        pad.emit((1, fixture.KEYS[index], 1)); time.sleep(duration)
        pad.emit((1, fixture.KEYS[index], 0)); time.sleep(.07)

    def chord():
        pad.emit((1, fixture.KEYS[14], 1), (1, fixture.KEYS[15], 1)); time.sleep(.04)
        pad.emit((1, fixture.KEYS[14], 0), (1, fixture.KEYS[15], 0))

    def game():
        file = state / 'game-state.json'
        return json.loads(file.read_text()) if file.exists() else {}

    def uinput_handles(pid):
        handles = []
        for path in Path(f'/proc/{pid}/fd').iterdir():
            try: info = path.stat()
            except FileNotFoundError: continue
            if stat.S_ISCHR(info.st_mode) and info.st_rdev == os.makedev(10, 223): handles.append(path.name)
        return handles

    try:
        wait_for(lambda: endpoint.exists() or shell.poll() is not None, 'Qt did not publish control')
        assert shell.poll() is None, (out / 'shell.log').read_text()
        wait_for(ready, 'Shared desktop did not become ready')
        time.sleep(.15)
        response = observe(True)
        assert response['state']['sensitiveVisible'] and response['capture']['status'] == 'sensitive_entry'
        assert 'png_base64' not in response['capture']
        # Close a private view and request a capture in the SAME action, without a fixed settling sleep.
        response = observe(True, action='back')
        assert not response['state']['editing'] and response['capture']['status'] == 'ok', response['capture']
        (out / 'after-private-composed.png').write_bytes(base64.b64decode(response['capture']['png_base64']))
        observe(action='home')
        # No udev daemon in this container: create only our new broker's event node.
        paths = [p.parent for p in Path('/sys/devices/virtual/input').glob('input*/name') if p.read_text().strip() == 'R46H Routed Gamepad']
        assert len(paths) == 1
        routed = fixture.event_node(paths[0].name)
        response = observe(True); assert response['capture']['status'] == 'ok', response['capture']
        assert response['capture']['source'] == 'weston-output'
        (out / 'home.png').write_bytes(base64.b64decode(response['capture']['png_base64']))
        rate = state / 'game-state.json.fps'; rate.write_text('15')
        press(1)  # Physical East is the accepted A button.
        wait_for(lambda: observe()['state']['externalSession'] and ready(), 'Physical A did not launch game')
        wait_for(lambda: 'buttons' in game(), 'SDL did not discover routed controller')
        wait_for(lambda: (metrics := observe()['state']['telemetry']['game']).get('active') and
                 metrics.get('submissions', -1) > 0 and metrics.get('lastFrameAgeMs', -1) >= 0,
                 'Game-frame readiness depended on the hidden HUD')
        game_guid = game()['guid']
        assert not uinput_handles(shell.pid) and not uinput_handles(game()['pid']), 'Delegated uinput leaked outside router'
        wait_for(lambda: observe()['state']['gameInputAvailable'], 'Remote game input not available')
        request = game_request(['a', 'l2'], [.6, -.3, .5, -.5], capture=True)
        job = pending(request)
        wait_for(lambda: game()['buttons'][0] == 1 and game()['axes'][0] > 18000 and game()['axes'][4] > 30000, 'RPC did not reach the SDL game')
        response = completed(job, 'completed')
        assert response['sequence'] == request['sequence'] + 1 and response['capture']['status'] == 'ok'
        wait_for(lambda: game()['buttons'][0] == 0 and abs(game()['axes'][0]) < 2 and game()['axes'][4] == 0, 'Timed RPC input stuck')
        (out / 'remote-game-exchange.json').write_text(json.dumps({'request': request, 'response': response}, indent=2) + '\n')
        for change in [{'application': 'wrong.game'}, {'input_sequence': request['input_sequence']}, {'axes': [2, 0, 0, 0]}, {'buttons': ['l3', 'r3']}]:
            invalid = game_request(['a']); invalid.update(change)
            assert not exchange(invalid, False)['ok'], change
        pad.emit((1, fixture.KEYS[0], 1)); wait_for(lambda: game()['buttons'][1] == 1, 'Physical B missing')
        assert exchange(game_request(['a']))['input_status'] == 'unavailable'
        assert game()['buttons'][1] == 1
        pad.emit((1, fixture.KEYS[0], 0)); wait_for(lambda: game()['buttons'][1] == 0, 'Physical B stuck')
        job = pending(game_request(['a'], milliseconds=1000))
        wait_for(lambda: game()['buttons'][0] == 1, 'Takeover sample missing')
        pad.emit((1, fixture.KEYS[12], 1))
        completed(job, 'cancelled')
        wait_for(lambda: game()['buttons'][0] == 0 and game()['buttons'][13] == 1, 'Physical takeover did not preserve its own input')
        pad.emit((1, fixture.KEYS[12], 0)); wait_for(lambda: game()['buttons'][13] == 0, 'Physical direction stuck')
        request = game_request(['x'], milliseconds=1000)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
            channel.connect(str(endpoint)); channel.sendall(json.dumps(request).encode() + b'\n')
            wait_for(lambda: game()['buttons'][2] == 1, 'Disconnect sample missing')
        released = time.monotonic()
        wait_for(lambda: game()['buttons'][2] == 0, 'Client disconnect did not release input', seconds=.6)
        assert time.monotonic() - released < .6
        time.sleep(.05)
        # Exercise the real CLI and verifier against the same live endpoint.
        prior = observe()
        cli = subprocess.Popen([sys.executable, '-B', '/project/mainline/gaming-shell/control.py', '--socket', str(endpoint),
            '--output-dir', '/project/mainline/out/remote-cli', '--no-image', '--expect-binary', prior['binary_sha256'], 'game-input',
            '--session', prior['session'], '--sequence', str(prior['sequence']), '--application', prior['state']['activeApplication'],
            '--input-sequence', str(prior['state']['inputSequence']), '--button', 'b', '--right-y', '.8', '--duration-ms', '300'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        wait_for(lambda: game()['buttons'][1] == 1 and game()['axes'][3] > 25000, 'CLI sample did not reach SDL')
        stdout, stderr = cli.communicate(timeout=4)
        assert cli.returncode == 0 and json.loads(stdout)['input_status'] == 'completed', stderr
        wait_for(lambda: game()['buttons'][1] == 0 and abs(game()['axes'][3]) < 2, 'CLI sample did not release')
        job = pending(game_request(['a'], milliseconds=1000))
        wait_for(lambda: game()['buttons'][0] == 1, 'Panel cancellation sample missing')
        chord(); completed(job, 'cancelled')
        wait_for(lambda: observe()['state']['quickOpen'] and ready(), 'Panel did not acquire input after remote cancellation')
        wait_for(lambda: game()['buttons'][0] == 0, 'Remote input survived panel opening')
        press(0); wait_for(lambda: observe()['state']['gameInputAvailable'], 'Game input did not recover after panel close')
        print('REMOTE_GAME_INPUT_PASS: actual RPC/CLI to SDL, automatic release, stale/wrong-game refusal, physical priority and disconnect cancellation')
        # Exercise the actual inherited SDL mapping, not a test-only added mapping.
        for raw, mapped in [(0, 1), (1, 0), (2, 2), (3, 3), (8, 4), (9, 6), (10, 11), (11, 12), (12, 13), (13, 14), (14, 7), (15, 8)]:
            pad.emit((1, fixture.KEYS[raw], 1))
            wait_for(lambda: game()['buttons'][mapped] == 1, 'Missing SDL button ' + str(raw))
            pad.emit((1, fixture.KEYS[raw], 0))
            wait_for(lambda: game()['buttons'][mapped] == 0, 'Stuck SDL button ' + str(raw))
        for index in range(4):
            pad.emit((3, fixture.AXES[index], -24000))
            wait_for(lambda: game()['axes'][index] < -20000, 'Missing SDL axis ' + str(index))
            pad.emit((3, fixture.AXES[index], 0))
            wait_for(lambda: abs(game()['axes'][index]) < 2, 'Axis did not center ' + str(index))
        for raw, axis in [(6, 4), (7, 5)]:
            pad.emit((1, fixture.KEYS[raw], 1))
            wait_for(lambda: game()['axes'][axis] > 30000, 'Missing SDL trigger')
            pad.emit((1, fixture.KEYS[raw], 0))
            wait_for(lambda: game()['axes'][axis] == 0, 'Trigger did not release')
        pad.emit((3, 0, 24000), (1, fixture.KEYS[1], 1))
        wait_for(lambda: game()['axes'][0] > 20000 and game()['buttons'][0] == 1, 'Game input did not reach SDL')
        chord()
        wait_for(lambda: observe()['state']['quickOpen'] and ready(), 'Physical chord did not open real quick panel')
        wait_for(lambda: all(x == 0 for x in game()['buttons']) and abs(game()['axes'][0]) < 2, 'Game did not receive neutral on panel open')
        # Keep the original A/stick held across handoff. They must not move the panel.
        assert observe()['state']['quickIndex'] == 0
        pad.emit((3, 0, 0), (1, fixture.KEYS[1], 0)); time.sleep(.05)
        press(11); assert observe()['state']['quickIndex'] == 1
        assert all(x == 0 for x in game()['buttons'])
        response = observe(True); assert response['capture']['status'] == 'ok'
        (out / 'panel-composed.png').write_bytes(base64.b64decode(response['capture']['png_base64']))
        subprocess.run(['/out/test-client', '--check-panel', str(out / 'panel-composed.png')], check=True, timeout=3)
        press(11); press(11); assert observe()['state']['quickIndex'] == 3
        press(1); assert observe()['state']['monitor']
        press(0)  # B resumes the game without closing it.
        wait_for(lambda: not observe()['state']['quickOpen'] and ready(), 'B did not resume game')
        time.sleep(.25)
        response = observe(True); assert response['capture']['status'] == 'ok' and response['state']['monitorVisible']
        (out / 'game-hud-composed.png').write_bytes(base64.b64decode(response['capture']['png_base64']))
        # Drive real buffer submissions independently of the HUD's own repaints.
        def frame_metrics(): return observe()['state']['telemetry']['game']
        def policy_frames():
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as policy:
                policy.settimeout(2); policy.connect(os.environ['XDG_RUNTIME_DIR'] + '/r46h-wm.sock')
                policy.sendall(b'{"version":1,"op":"observe"}\n')
                return json.loads(policy.recv(65536))['frameStats']
        samples = []
        for fps in (60, 15, 0):
            rate.write_text(str(fps))
            wait_for(lambda: game()['requestedFps'] == fps, 'Test renderer did not accept cadence')
            time.sleep(2.1)  # Flush the previous HUD sampling window.
            client_before, policy_before = game(), policy_frames()
            time.sleep(2.1)
            client_after, policy_after = game(), policy_frames()
            rendered = client_after['renderedFrames'] - client_before['renderedFrames']
            committed = policy_after['bufferCommits'] - policy_before['bufferCommits']
            actual = rendered * 1000 / (client_after['sampledAtMs'] - client_before['sampledAtMs'])
            metrics = frame_metrics()
            # Software Qt/Weston need not reach the requested timer cadence.
            # Compare independent client frameSwapped and compositor counters.
            assert abs(rendered - committed) <= 3, (fps, rendered, committed)
            assert abs(metrics['submissions'] - actual) <= max(3, actual * .2), (fps, actual, metrics)
            if fps:
                assert rendered >= 10, 'Animated test client stopped rendering'
                assert metrics['intervalP95Ms'] >= metrics['intervalMedianMs'] > 0, metrics
            else:
                assert rendered == committed == metrics['submissions'] == 0, 'HUD repaints inflated the game counter'
                assert metrics['intervalMedianMs'] == metrics['intervalP95Ms'] == -1, 'Static game retained stale intervals'
            if fps == 15:
                frame = observe(True); (out / 'game-frame-hud.png').write_bytes(base64.b64decode(frame['capture']['png_base64']))
            samples.append({'requestedFps': fps, 'clientSubmissions': actual, 'clientFrames': rendered,
                            'compositorFrames': committed, **metrics})
        assert samples[0]['clientSubmissions'] > samples[1]['clientSubmissions'] * 1.3, samples
        assert observe()['state']['monitorVisible']
        (out / 'frame-metrics.json').write_text(json.dumps(samples, indent=2) + '\n')
        chord(); wait_for(lambda: observe()['state']['quickOpen'] and ready(), 'HUD control panel did not open')
        assert observe()['state']['quickIndex'] == 3
        press(1); press(0)
        time.sleep(1.1)
        assert not observe()['state']['monitorVisible'] and frame_metrics()['active'], 'Hidden HUD stopped game-frame readiness sampling'
        chord(); wait_for(lambda: observe()['state']['quickOpen'] and ready(), 'HUD control panel did not reopen')
        press(1); press(0)
        wait_for(lambda: frame_metrics().get('submissions') == 0, 'HUD toggle disturbed game-frame sampling')
        print('GAME_FRAME_METRICS_PASS: independent client/compositor frame counts, changing cadence, stale intervals and HUD-independent readiness sampling')
        pad.emit((1, fixture.KEYS[4], 1), (1, fixture.KEYS[5], 1))
        wait_for(lambda: game()['buttons'][9] == game()['buttons'][10] == 1, 'Shoulder chord was not forwarded')
        pad.emit((1, fixture.KEYS[4], 0), (1, fixture.KEYS[5], 0)); time.sleep(.04)
        chord(); wait_for(lambda: observe()['state']['quickOpen'] and ready(), 'Second chord did not reopen panel')
        for _ in range(5 - observe()['state']['quickIndex']): press(11)
        assert observe()['state']['quickIndex'] == 5
        press(1); assert observe()['state']['choicesOpen']
        press(1); assert not observe()['state']['choicesOpen'] and observe()['state']['externalSession'], 'Default cancellation stopped game'
        press(1); press(11); press(1)
        wait_for(lambda: not observe()['state']['externalSession'] and ready(), 'Confirmed game exit did not restore desktop')
        assert not frame_metrics().get('active', False), 'Game metrics survived game exit'
        rate.unlink()
        press(8); wait_for(lambda: observe()['state']['quickOpen'], 'Select no longer opens desktop panel')
        press(0); assert not observe()['state']['quickOpen']
        # Stop only this test's compositor after queuing a new capture. Kernel input
        # remains live, so opening a private editor must cancel the in-flight frame.
        observe(action='nextTab'); observe(action='nextTab')
        category = observe()['state']['settingsCategory']
        for _ in range(abs(9 - category)): observe(action='down' if category < 9 else 'up')
        observe(action='accept'); observe(action='down')
        assert observe()['state']['settingsCategory'] == 9 and observe()['state']['settingsIndex'] == 1
        time.sleep(.15); wait_for(ready, 'Settings not ready for privacy race')
        compositor = int(os.environ['R46H_TEST_WESTON_PID'])
        assert b'--shell=/out/handheld-shell.so' in Path(f'/proc/{compositor}/cmdline').read_bytes()
        pidfd = os.pidfd_open(compositor)
        before = (out / 'shell.log').read_text().count('HANDHELD_CAPTURE_BEGIN')
        result = []; errors = []
        def capture_pending():
            try: result.append(observe(True))
            except Exception as error: errors.append(str(error))
        thread = threading.Thread(target=capture_pending)
        try:
            signal.pidfd_send_signal(pidfd, signal.SIGSTOP)
            thread.start()
            wait_for(lambda: (out / 'shell.log').read_text().count('HANDHELD_CAPTURE_BEGIN') > before, 'Capture never entered its pending frame state')
            press(1)
            thread.join(timeout=2)
            assert not thread.is_alive() and not errors and len(result) == 1, errors
            assert result[0]['capture']['status'] == 'sensitive_entry' and 'png_base64' not in result[0]['capture'], result[0]['capture']
        finally:
            signal.pidfd_send_signal(pidfd, signal.SIGCONT); os.close(pidfd)
            if thread.is_alive(): thread.join(timeout=3)
        assert observe()['state']['sensitiveVisible']
        response = observe(True, action='back')
        assert response['capture']['status'] == 'ok' and not response['state']['sensitiveVisible'], response['capture']
        print('HANDHELD_CAPTURE_PRIVACY_PASS: private entry refusal, fresh public frame after close, in-flight cancellation while compositor stalled and recovery')
        observe(action='home'); press(1)
        wait_for(lambda: observe()['state']['externalSession'] and ready(), 'Recovery game launch failed')
        wait_for(lambda: Path('/proc/' + str(game().get('pid', 0))).exists(), 'Recovery game pid missing')
        game_pid = game()['pid']
        children = Path(f'/proc/{shell.pid}/task/{shell.pid}/children').read_text().split()
        routers = [int(pid) for pid in children if Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')[0] == b'/out/input-router']
        assert len(routers) == 1 and Path(f'/proc/{game_pid}/cmdline').read_bytes().split(b'\0')[0] == b'/out/test-client'
        router_fd = os.pidfd_open(routers[0])
        try: signal.pidfd_send_signal(router_fd, signal.SIGKILL)
        finally: os.close(router_fd)
        assert shell.wait(timeout=5) == 1
        assert not Path(f'/proc/{game_pid}').exists(), 'Game survived loss of the input router'
        wait_for(lambda: not paths[0].exists(), 'Routed device survived router death; inherited handle leaked')
        print('UINPUT_DELEGATION_PASS: hidden device path, no GUI/game handle leak, device destroyed after router loss')
        print('HANDHELD_FAILURE_PASS: router loss stops the game and returns a failure exit for supervisor recovery')
        receipt = {'status': 'REAL_QT_ROUTER_WESTON_SDL_HOST_PASS', 'game_guid': game_guid,
            'boundary': 'Synthetic Linux VM with composed capture, private-entry cancellation and router-loss cleanup; no physical panel/audio/Panfrost proof'}
        (out / 'result.json').write_text(json.dumps(receipt, indent=2) + '\n')
        (out / 'game-state.json').write_text(json.dumps(game(), indent=2) + '\n')
        print('HANDHELD_DESKTOP_PASS: physical-style buttons through uinput to real Qt, SDL gameplay, L3+R3 panel, neutral isolation, resume, confirmation/cancel and desktop recovery')
        routed.unlink(); routed = None
        (state / 'game-state.json').unlink()
        # Run the actual built-in management page and existing stream worker with
        # a fake transport endpoint that opens the same real Wayland/SDL client.
        stream = state / 'settings/streaming'; stream.mkdir(exist_ok=True, mode=0o700)
        host = {'id': 'cf29d1af-ea71-4dbf-81fc-9d95498387e7', 'name': 'Fixture', 'address': '127.0.0.1',
            'application': 'Game; literal', 'preset': 0, 'overlay': True, 'paired': True}
        (stream / 'hosts.json').write_text(json.dumps({'version': 1, 'selected': host['id'], 'hosts': [host]}))
        fake = state / 'moonlight-fixture'
        stats = {'version': 1, 'receivedFps': 60, 'decodedFps': 60, 'renderedFps': 59,
                 'networkDropPercent': 0.1, 'pacingDropPercent': 0.2, 'decodeMs': 2, 'queueMs': 4,
                 'renderCallMs': 3, 'rttMs': 8, 'hostProcessingMs': 5, 'audioNetworkQueueMs': 10}
        fake.write_text('#!/usr/bin/python3\nimport json,os,pathlib,sys,time\n'
            'assert sys.argv[1] == "stream"\n'
            'assert os.environ.get("R46H_STREAM_STATS") == "1"\n'
            'pathlib.Path(' + repr(str(state / 'stream-argv.json')) + ').write_text(json.dumps({"argv":sys.argv[1:],"env":{key:os.environ.get(key) for key in '
            '["QT_QPA_PLATFORM","SDL_VIDEODRIVER","SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT","XDG_CONFIG_HOME","XDG_DATA_HOME"]}}))\n'
            'print("FPS 60",flush=True)\nprint("https://fixture/?credential=private-marker",flush=True)\n'
            'sys.stdout.write("R46H_ST");sys.stdout.flush();time.sleep(.02)\n'
            'print(' + repr('ATS ' + json.dumps(stats)) + ',flush=True)\n'
            'print(' + repr('R46H_STATS ' + json.dumps({**stats, 'renderedFps': 99})) + ',file=sys.stderr,flush=True)\n'
            'print(' + repr('R46H_STATS ' + json.dumps({**stats, 'address': 'private-marker'})) + ',flush=True)\n'
            'os.execv("/out/test-client",["/out/test-client","game",' + repr(str(state / 'game-state.json')) + '])\n')
        fake.chmod(0o700)
        # A controller claim lasts for its compositor session. Give this second
        # desktop a fresh private compositor instead of bypassing that ownership.
        runtime = state / 'stream-runtime'; runtime.mkdir(mode=0o700)
        os.environ.update(XDG_RUNTIME_DIR=str(runtime), WAYLAND_DISPLAY='r46h-stream-test')
        stream_compositor = subprocess.Popen(['weston', '--backend=headless', '--renderer=pixman', '--width=640', '--height=480',
            '--idle-time=0', '--no-config', '--socket=r46h-stream-test', '--shell=/out/handheld-shell.so',
            '--log=/out/desktop-stream-weston.log'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        wait_for(lambda: (runtime / 'r46h-stream-test').exists(), 'Streaming compositor did not start')
        delegated = os.open('/dev/uinput.hidden', os.O_WRONLY | os.O_CLOEXEC)
        try:
            shell = subprocess.Popen(['/out/linux-build/r46h-shell', '--state-dir', str(state / 'settings'), '--control-dir', str(state / 'control'),
                '--scene', 'home', '--handheld-router', '/out/input-router', '--input-device', str(pad.path), '--uinput-fd', str(delegated),
                '--moonlight-client', str(fake), '--moonlight-sha256', hashlib.sha256(fake.read_bytes()).hexdigest(),
                '--fullscreen', '--quit-after', '90'], pass_fds=(delegated,), stdout=logfile, stderr=subprocess.STDOUT)
        finally: os.close(delegated)
        wait_for(lambda: endpoint.exists() or shell.poll() is not None, 'Shared streaming UI did not start')
        assert shell.poll() is None, (out / 'shell.log').read_text()
        wait_for(ready, 'Shared streaming UI did not become ready')
        paths = [p.parent for p in Path('/sys/devices/virtual/input').glob('input*/name') if p.read_text().strip() == 'R46H Routed Gamepad']
        assert len(paths) == 1; routed = fixture.event_node(paths[0].name)
        initial = observe(); assert initial['state']['selectedApplication'] == 'builtin.moonlight'
        observe(action='accept'); assert observe()['state']['streamingOpen'], 'Foreground owner hid the built-in tool cards'
        observe(action='accept')  # Host details.
        for code in (0, 7):
            observe(action='accept')
            wait_for(lambda: observe()['state']['externalSession'] and ready(), 'Streaming did not take shared foreground ownership')
            wait_for(lambda: 'buttons' in game(), 'Stream worker did not start the Wayland/SDL child')
            wait_for(lambda: observe()['state']['telemetry']['stream'].get('renderedFps') == 59,
                     'Validated native statistics did not pass through the worker pipe')
            assert observe()['session'] == initial['session'] and observe()['state']['activeApplication'] == 'builtin.moonlight'
            assert not (stream / 'request.json').exists(), 'Shared worker did not consume the request'
            request_data = json.loads((state / 'stream-argv.json').read_text())
            assert request_data['argv'][:3] == ['stream', '127.0.0.1', 'Game; literal']
            assert request_data['env']['QT_QPA_PLATFORM'] == request_data['env']['SDL_VIDEODRIVER'] == 'wayland'
            assert request_data['env']['SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT'] == '0x5246/0x0049'
            assert request_data['env']['XDG_CONFIG_HOME'] == str(stream / 'client/config')
            assert request_data['env']['XDG_DATA_HOME'] == str(stream / 'client/data')
            job = pending(game_request(['a'], milliseconds=300))
            wait_for(lambda: game()['buttons'][0] == 1, 'Remote input did not reach the stream child')
            completed(job, 'completed')
            chord(); wait_for(lambda: observe()['state']['quickOpen'] and ready(), 'Stream panel did not open')
            time.sleep(.3)  # Retain the settled panel, not an intentional entry-animation frame.
            frame = observe(True); assert frame['capture']['status'] == 'ok'
            assert frame['state']['gameOverlay'], 'Stream panel lost its external-session context'
            (out / 'stream-panel-state.json').write_text(json.dumps(frame['state'], indent=2) + '\n')
            (out / 'stream-panel.png').write_bytes(base64.b64decode(frame['capture']['png_base64']))
            if code == 0:
                assert frame['state']['telemetry']['stream']['audioNetworkQueueMs'] == 10
                (out / 'stream-stats-panel.png').write_bytes(base64.b64decode(frame['capture']['png_base64']))
            else:
                wait_for(lambda: not observe()['state']['telemetry']['stream']['available'], 'Silent statistics did not expire')
                assert 'renderedFps' not in observe()['state']['telemetry']['stream']
            observe(action='back'); wait_for(lambda: not observe()['state']['quickOpen'] and ready(), 'Stream panel did not resume')
            ending = state / 'game-state.json.exit'; ending.write_text(str(code))
            wait_for(lambda: not observe()['state']['externalSession'] and ready(), 'Shared stream exit did not restore management')
            assert observe()['session'] == initial['session'] and observe()['state']['streamingOpen']
            assert json.loads((stream / 'result.json').read_text())['exit'] == code
            assert not observe()['state']['telemetry']['stream']['active'], 'Exited stream retained statistics'
            text = (stream / 'stream.log').read_text(); assert 'FPS 60' in text and 'private-marker' not in text
            assert 'R46H_STATS' not in text, 'Raw diagnostic messages entered persistent logs'
            ending.unlink(); (state / 'game-state.json').unlink()
        # An explicit panel stop uses the same group cleanup as ordinary games.
        observe(action='accept')
        wait_for(lambda: observe()['state']['externalSession'] and ready() and 'buttons' in game(), 'Stream relaunch failed')
        stopped_pid = game()['pid']; chord(); wait_for(lambda: observe()['state']['quickOpen'] and ready(), 'Stop panel missing')
        for _ in range(5 - observe()['state']['quickIndex']): observe(action='down')
        observe(action='accept'); observe(action='down'); observe(action='accept')
        wait_for(lambda: not observe()['state']['externalSession'] and ready(), 'Panel stop left stream running')
        assert not Path(f'/proc/{stopped_pid}').exists()
        assert json.loads((stream / 'result.json').read_text())['exit'] == 0, 'Explicit stop retained a stale failure result'
        (out / 'shared-stream-result.json').write_text(json.dumps({'status': 'SHARED_STREAM_MANAGEMENT_WORKER_HOST_PASS',
            'checks': ['built-in cards retained', 'same live desktop/IPC', 'literal stream argv and private client state',
                'routed SDL input and global panel', 'normal/error return, reconnect and explicit group stop', 'filtered logs',
                'numeric statistics pipe, stderr refusal, stale and exit clearing'],
            'boundary': 'Real Qt/Wayland/SDL and existing stream worker with fake Moonlight transport; no actual A/V, Sunshine or R46H proof'}, indent=2) + '\n')
        print('SHARED_STREAM_WORKER_PASS: management to foreground worker, routed input/panel, same desktop return, reconnect and explicit stop')
    finally:
        if shell.poll() is None:
            shell.terminate()
            try: shell.wait(timeout=5)
            except subprocess.TimeoutExpired: shell.kill(); shell.wait(timeout=3)
        logfile.close()
        if stream_compositor:
            stream_compositor.terminate(); stream_compositor.wait(timeout=3)
        if routed: routed.unlink()
        pad.close()
        os.rename('/dev/uinput.hidden', '/dev/uinput')
