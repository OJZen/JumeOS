#!/usr/bin/env python3
"""Container-only real X11 seat -> Wayland keyboard/mouse -> terminal PTY check."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time

assert Path('/.dockerenv').exists() and os.getuid() != 0
out = Path('/out/peripherals')
children = []


def wait_for(check, message):
    until = time.monotonic() + 8
    while time.monotonic() < until:
        if check():
            return
        time.sleep(.05)
    raise AssertionError(message)


def start(name, args, env):
    with (out / (name + '.log')).open('w') as log:
        child = subprocess.Popen(args, env=env, stdout=log, stderr=subprocess.STDOUT)
    children.append(child)
    return child


# Docker Desktop's bind mount does not preserve guest UID ownership; socket
# authentication needs a genuinely user-owned directory in the container.
with tempfile.TemporaryDirectory(prefix='jume-seat-') as temp:
    root = Path(temp)
    env = dict(os.environ, XDG_RUNTIME_DIR=temp, WAYLAND_DISPLAY='peripheral-check',
               QT_QPA_PLATFORM='wayland', QT_QUICK_BACKEND='software', LANG='C.UTF-8', HOME=temp)
    try:
        # No host X display, USB devices or network. This seat belongs only to Xvfb.
        with (root / 'display').open('w') as display:
            xvfb = subprocess.Popen(['Xvfb', '-displayfd', str(display.fileno()), '-screen', '0', '640x480x24', '-nolisten', 'tcp'],
                                    pass_fds=(display.fileno(),), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        children.append(xvfb)
        wait_for(lambda: (root / 'display').read_text().strip(), 'X display')
        env['DISPLAY'] = ':' + (root / 'display').read_text().strip()
        start('weston', ['weston', '--backend=x11', '--renderer=pixman', '--width=640', '--height=480',
              '--no-config', '--idle-time=0', '--shell=/out/handheld-shell.so', '--socket=peripheral-check'], env)
        endpoint = root / 'r46h-wm.sock'
        wait_for(endpoint.exists, 'compositor socket')

        def call(request):
            with socket.socket(socket.AF_UNIX) as channel:
                channel.settimeout(3); channel.connect(str(endpoint))
                channel.sendall(json.dumps(dict(version=1, **request)).encode() + b'\n')
                raw = bytearray()
                while part := channel.recv(65536):
                    raw += part
                    assert len(raw) < 65536
            response = json.loads(raw)
            assert response['ok'], response
            return response

        def policy(op, **fields):
            state = call({'op': 'observe'})
            return call(dict(op=op, session=state['session'], sequence=state['sequence'], **fields))

        ui = start('ui', ['/out/test-client', 'ui'], dict(env, R46H_TEST_PASS_THROUGH='1'))
        call({'op': 'hello', 'uiPid': ui.pid})
        # Deliberately pass a private Qt variable: the shell adapter must remove it.
        terminal = start('terminal', ['/out/terminal-runtime/usr/bin/foot', '--config=/dev/null', '--fullscreen',
                         '--font=monospace:size=10', '--term=xterm-256color', '/out/terminal-runtime/terminal-shell.sh'],
                         dict(env, QT_PLUGIN_PATH='/private-test-sdk',
                              LD_LIBRARY_PATH='/out/terminal-runtime/usr/lib/aarch64-linux-gnu',
                              FONTCONFIG_FILE='/out/terminal-runtime/terminal-fonts.conf',
                              XCURSOR_PATH='/out/terminal-runtime/usr/share/icons', XCURSOR_THEME='DMZ-White'))
        policy('game', pid=terminal.pid)
        wait_for(lambda: sum(s['mapped'] for s in call({'op': 'observe'})['surfaces']) == 2, 'two mapped clients')
        subprocess.run(['xdotool', 'search', '--sync', '--onlyvisible', '--class', 'weston', 'windowfocus'], env=env, check=True, timeout=8)

        def key(*keys):
            subprocess.run(['xdotool', 'key', '--clearmodifiers', *keys], env=env, check=True, timeout=3)

        def type_command(command):
            subprocess.run(['xdotool', 'type', '--clearmodifiers', '--delay', '2', command], env=env, check=True, timeout=8)
            key('Return')

        type_command(f'printf "%s %s %s" "$(id -u)" "${{QT_PLUGIN_PATH-unset}}" "$(test -t 0 && echo pty)" > {root}/keyboard')
        wait_for(lambda: (root / 'keyboard').exists(), 'real keyboard reached Bash')
        assert (root / 'keyboard').read_text() == f'{os.getuid()} unset pty'
        # Ctrl+C must reach the shell, not a launcher shortcut.
        type_command('sleep 30'); time.sleep(.2); key('ctrl+c')
        type_command(f'printf interrupted > {root}/interrupt')
        wait_for(lambda: (root / 'interrupt').exists(), 'Ctrl+C interrupted foreground command')
        # Request terminal mouse reports beneath the visible right-hand UI overlay.
        policy('overlay', active=True)
        type_command(f"printf '\\033[?1000h'; IFS= read -r -n 6 reply; printf %s \"$reply\" | od -An -t x1 > {root}/mouse; printf '\\033[?1000l'")
        time.sleep(.3)
        subprocess.run(['xdotool', 'mousemove', '600', '25', 'click', '1'], env=env, check=True, timeout=3)
        wait_for(lambda: (root / 'mouse').exists(), 'mouse passed through visible HUD')
        assert (root / 'mouse').read_text().strip().startswith('1b 5b 4d'), (root / 'mouse').read_text()
        time.sleep(.2); key('ctrl+c')  # Discard the synthetic button-release report left after read's six bytes.
        type_command('exit 0'); terminal.wait(timeout=5); assert terminal.returncode == 0, terminal.returncode
        policy('game', pid=0)
        assert ui.poll() is None
        (out / 'result.json').write_text(json.dumps({'keyboard': 'PASS', 'ctrl_c': 'PASS', 'terminal_pty': 'PASS',
            'nonroot_clean_environment': 'PASS', 'mouse_through_overlay': 'PASS', 'exit': 'PASS',
            'physical_usb_hotplug': 'UNTESTED'}, indent=2) + '\n')
    finally:
        for child in reversed(children):
            if child.poll() is None:
                child.send_signal(signal.SIGTERM)
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill(); child.wait(timeout=3)
