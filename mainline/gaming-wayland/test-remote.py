#!/usr/bin/env python3
"""Actual SSH helper/relay, Qt/Weston and routed SDL input; root seat hardware is substituted."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time

assert Path('/.dockerenv').exists() and os.geteuid() == 0

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value

fixture = module('routing', Path(__file__).with_name('test-input-router.py'))
control = module('control', '/project/mainline/gaming-shell/control.py')
base = Path('/run/r46h-wayland-probe'); out = Path('/out/remote')

def wait_for(check, message, seconds=8):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check(): return
        time.sleep(.025)
    raise AssertionError(message)

with tempfile.TemporaryDirectory(prefix='r46h-ssh-', dir='/run') as directory:
    keys = Path(directory); identity = keys / 'identity'; known = keys / 'known_hosts'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(identity)], check=True)
    shutil.copyfile(str(identity) + '.pub', base / 'remote-client.pub'); (base / 'remote-client.pub').chmod(0o644)
    state = base / 'state/session.SSHTest'; state.mkdir(parents=True, mode=0o700); os.chown(state, 1000, 1000)
    # Only the hardware seat and diagnostic app selection are replaced in this fixture.
    (base / 'session.sh').write_text('#!/bin/bash\nset -Eeuo pipefail\n[[ $1 == seat && $3 == handheld ]]\nexec 7>/dev/uinput\nexec /usr/bin/setpriv --reuid=ark --regid=ark --init-groups -- "${0%/*}/session-real.sh" headless "$2" handheld\n')
    (base / 'session.sh').chmod(0o755)
    game_wrapper = state / 'game.sh'
    game_wrapper.write_text('#!/bin/sh\nexport LD_LIBRARY_PATH=' + str(base / 'usr/lib/aarch64-linux-gnu') + '\nexport QT_PLUGIN_PATH=' + str(base / 'usr/lib/aarch64-linux-gnu/qt6/plugins') + '\nexec ' + str(base / 'usr/bin/test-client') + ' game ' + str(state / 'game.json') + ' > ' + str(state / 'game.log') + ' 2>&1\n')
    game_wrapper.chmod(0o755)
    apps = {'version': 1, 'applications': [{'id': 'test.' + str(i), 'title': 'Test ' + str(i),
        'program': str(game_wrapper), 'arguments': []} for i in range(2)]}
    (state / 'applications.json').write_text(json.dumps(apps)); (state / 'applications.json').chmod(0o644)
    (base / 'handheld-client.sh').write_text('#!/bin/sh\nset -eu\nbase=${0%/*}\nexport R46H_SHELL_STATE_DIR="$2/ui-state"\nexec "$base/shell-client.sh" --fullscreen --scene input --quit-after 85 --applications "$2/applications.json" --control-dir "$2/control" --handheld-router "$base/usr/bin/input-router" --input-device "$R46H_ROUTED_SOURCE" --uinput-fd 7\n')
    (base / 'handheld-client.sh').chmod(0o755)
    pad = fixture.Pad(); os.chown(pad.path, 1000, 1000); pad.path.parent.chmod(0o755)
    log = (out / 'helper.log').open('w')
    helper = subprocess.Popen([str(base / 'remote-session.sh'), '127.0.0.1', '127.0.0.1', 'wayland', str(state)],
        env={**os.environ, 'R46H_ROUTED_SOURCE': str(pad.path)}, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    routed = None

    def exchange(request): return control.ssh_exchange('127.0.0.1', 22222, identity, known, request)

    def observe(action=None, capture=False):
        request = {'version': 1, 'id': 'shared-ssh', 'op': 'observe', 'screenshot': capture}
        if action:
            previous = observe(); request.update({k: previous[k] for k in ('session', 'sequence', 'binary_sha256')})
            request.update(op='tap', action=action)
        return exchange(request)

    def sample(milliseconds=700):
        previous = observe()
        return {'version': 1, 'id': 'ssh-input', 'op': 'game-input', 'screenshot': False,
            **{k: previous[k] for k in ('session', 'sequence', 'binary_sha256')},
            'application': previous['state']['activeApplication'], 'input_sequence': previous['state']['inputSequence'],
            'buttons': ['a'], 'axes': [.75, 0, 0, 0], 'duration_ms': milliseconds}

    def game():
        path = state / 'game.json'; return json.loads(path.read_text()) if path.exists() else {}

    try:
        wait_for(lambda: (state / 'control/control.sock').exists() or helper.poll() is not None, 'Shared SSH session did not start')
        assert helper.poll() is None
        shutil.copyfile(base / 'remote-known-hosts', known); known.chmod(0o600)
        wait_for(lambda: observe()['state']['sharedReady'], 'Shared SSH ownership not ready')
        private = observe(capture=True); assert private['capture']['status'] == 'sensitive_entry'
        observe('back'); observe('home'); session = observe()['session']
        paths = [p.parent for p in Path('/sys/devices/virtual/input').glob('input*/name') if p.read_text().strip() == 'R46H Routed Gamepad']
        assert len(paths) == 1; routed = fixture.event_node(paths[0].name); os.chown(routed, 1000, 1000)
        binary = hashlib.sha256((base / 'usr/bin/r46h-shell').read_bytes()).hexdigest()
        with (out / 'transport-check.log').open('w') as check_log:
            subprocess.run(['/usr/bin/python3', '-B', '/project/mainline/tests/test-shell-ssh.py', '--host', '127.0.0.1', '--port', '22222',
                '--identity', str(identity), '--known-hosts', str(known), '--binary', binary,
                '--evidence', '/project/mainline/out/remote/transport'], stdout=check_log, stderr=subprocess.STDOUT, check=True, timeout=35)
        observe('accept'); wait_for(lambda: 'buttons' in game() and observe()['state']['gameInputAvailable'], 'SSH could not launch the SDL game')
        request = sample(); replies = []; errors = []
        def send():
            try: replies.append(exchange(request))
            except Exception as error: errors.append(str(error))
        thread = threading.Thread(target=send); thread.start()
        wait_for(lambda: game()['buttons'][0] == 1 and game()['axes'][0] > 20000, 'SSH input did not reach SDL')
        thread.join(timeout=4); assert not thread.is_alive() and not errors and replies[0]['input_status'] == 'completed', errors
        wait_for(lambda: game()['buttons'][0] == 0 and abs(game()['axes'][0]) < 2, 'SSH input did not release')
        interrupted = subprocess.Popen(['/usr/bin/ssh', '-F', '/dev/null', '-T', '-p', '22222', '-i', str(identity),
            '-o', 'IdentityAgent=none', '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'UserKnownHostsFile=' + str(known), '-o', 'GlobalKnownHostsFile=/dev/null', '-o', 'ConnectTimeout=3',
            'ark@127.0.0.1', 'r46h-control'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        interrupted.stdin.write(json.dumps(sample(1000)).encode() + b'\n'); interrupted.stdin.close()
        wait_for(lambda: game()['buttons'][0] == 1, 'Interrupted SSH sample did not reach SDL')
        cancelled_at = time.monotonic(); interrupted.kill(); interrupted.wait(timeout=3)
        wait_for(lambda: game()['buttons'][0] == 0 and abs(game()['axes'][0]) < 2, 'SSH disconnect did not cancel the active sample', seconds=.6)
        (out / 'disconnect.json').write_text(json.dumps({'release_ms': round((time.monotonic() - cancelled_at) * 1000), 'lease_ms': 1000}) + '\n')
        interrupted.stdout.close(); interrupted.stderr.close()
        observe('quick'); frame = observe(capture=True); assert frame['state']['quickOpen'] and frame['capture']['source'] == 'weston-output'
        (out / 'game-panel.png').write_bytes(control.checked_image(copy.deepcopy(frame)))
        observe('back')
        (state / 'game.json.exit').write_text('0')
        wait_for(lambda: not observe()['state']['externalSession'] and observe()['session'] == session, 'SSH game return changed/lost the desktop')
        os.killpg(helper.pid, signal.SIGTERM); assert helper.wait(timeout=8) != 0
        assert not any(p.is_dir() for p in base.glob('remote-ssh.*')) and not (state / 'control').exists(), 'SSH temporary state survived'
        wait_for(lambda: not paths[0].exists(), 'Routed input survived SSH/session teardown')
        with socket.socket() as closed:
            closed.settimeout(.5); assert closed.connect_ex(('127.0.0.1', 22222)) != 0, 'Temporary SSH listener survived'
        (out / 'result.json').write_text(json.dumps({'status': 'SHARED_SSH_ROUTED_GAME_HOST_PASS', 'binary_sha256': binary,
            'checks': ['real production SSH helper and QCore relay', 'composed capture and private-entry refusal', 'real host-key/command/forwarding checks',
                       'SSH game launch and timed controller delivery/release', 'early release on SSH disconnect', 'panel and same-session return', 'temporary server cleanup'],
            'boundary': 'Isolated loopback SSH and synthetic controller; hardware seat and app manifest are substituted. No R46H network/seat/input acceptance.'}, indent=2) + '\n')
        print('SHARED_SSH_PASS: actual authenticated relay to composed desktop and bounded SDL game input')
    finally:
        if helper.poll() is None:
            os.killpg(helper.pid, signal.SIGTERM)
            try: helper.wait(timeout=8)
            except subprocess.TimeoutExpired: os.killpg(helper.pid, signal.SIGKILL); helper.wait(timeout=3)
        log.close()
        for name in ('remote-ssh.log', 'remote-session.log'):
            if (base / name).exists(): shutil.copyfile(base / name, out / name)
        for name in ('clients.log', 'weston.log', 'game.log'):
            if (state / name).exists(): shutil.copyfile(state / name, out / name)
        if routed: routed.unlink()
        pad.close()
