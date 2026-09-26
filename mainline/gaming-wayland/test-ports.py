#!/usr/bin/env python3
"""Source-built GTA and original Mono ports through the shared desktop; no device claim."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

assert Path('/.dockerenv').exists()
os.umask(0o077)

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value

fixture = module('routing', Path(__file__).with_name('test-input-router.py'))
control = module('control', '/project/mainline/gaming-shell/control.py')
out = Path('/out/ports')

def wait_for(check, message, seconds=8):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if check(): return
        time.sleep(.05)
    raise AssertionError(message)

with tempfile.TemporaryDirectory(prefix='r46h-ports-', dir='/run') as directory:
    state = Path(directory); apps = []
    engines = {'gta3': '/gta-source/re3', 'gtavc': '/gta-source/reVC'}
    for game in ('gta3', 'gtavc', 'stardew'):
        arguments = ['-I', '-B', '/code/local_port.py', game, '--host-test', '--shared-display', '--content-root', '/content',
                     '--state', str(state / game), '--seconds', '70', '--mono', '/mono', '--mono-compat', '/mono-compat.so']
        if game in engines: arguments += ['--engine', engines[game]]
        apps.append({'id': 'ports.' + game, 'title': game, 'program': '/usr/bin/python3',
            'arguments': arguments})
    manifest = state / 'applications.json'; manifest.write_text(json.dumps({'version': 1, 'applications': apps}))
    pad = fixture.Pad(); routed = None
    log = (out / 'shell.log').open('w')
    shell = subprocess.Popen(['/out/linux-build/r46h-shell', '--state-dir', str(state / 'ui'), '--applications', str(manifest),
        '--control-dir', str(state / 'control'), '--handheld-router', '/out/input-router', '--input-device', str(pad.path),
        '--fullscreen', '--quit-after', '120'], stdout=log, stderr=subprocess.STDOUT)
    endpoint = state / 'control/control.sock'

    def observe(action=None, capture=False):
        request = {'version': 1, 'id': 'ports', 'op': 'observe', 'screenshot': capture}
        if action:
            previous = observe()
            request.update({k: previous[k] for k in ('session', 'sequence', 'binary_sha256')})
            request.update(op='tap', action=action)
        return control.exchange(endpoint, request)

    def ready(): return observe()['state']['sharedReady']

    def capture(path):
        result = observe(capture=True)
        assert result['capture']['status'] == 'ok', result['capture']
        data = control.checked_image(result)
        path.write_bytes(data)

    def children(pid):
        path = Path(f'/proc/{pid}/task/{pid}/children')
        return [int(child) for child in path.read_text().split()] if path.exists() else []

    try:
        wait_for(lambda: endpoint.exists() or shell.poll() is not None, 'Desktop did not start')
        assert shell.poll() is None; wait_for(ready, 'Desktop ownership not ready')
        paths = fixture.routed_devices()
        assert len(paths) == 1; routed = fixture.event_node(paths[0].name)
        session = observe()['session']; results = []
        for index, game in enumerate(('gta3', 'gtavc', 'stardew')):
            evidence = out / game; evidence.mkdir(exist_ok=True)
            if index: observe('right')
            observe('accept')
            wait_for(lambda: observe()['state']['externalSession'] and ready(), game + ' did not launch')
            worker = next(pid for pid in children(shell.pid) if Path(f'/proc/{pid}/cmdline').read_bytes().startswith(b'/usr/bin/python3\0'))
            wait_for(lambda: children(worker) or not observe()['state']['externalSession'], game + ' engine did not start')
            assert children(worker), game + ' preparation failed'
            engine = children(worker)[0]
            assert os.getpgid(engine) == worker, 'Engine escaped foreground process group'
            time.sleep(14 if game == 'stardew' else 9)
            assert observe()['state']['externalSession'], game + ' exited before the frontend check'
            fds = []
            for descriptor in Path(f'/proc/{engine}/fd').iterdir():
                try: target = str(descriptor.readlink())
                except FileNotFoundError: continue
                if target.startswith('/dev/input/'): fds.append(target)
            (evidence / 'input-fds.json').write_text(json.dumps(fds) + '\n')
            assert str(routed) in fds and str(pad.path) not in fds, game + ' did not use only routed input'
            if game == 'stardew':
                pad.emit((1, fixture.KEYS[1], 1)); time.sleep(.2)
                pad.emit((1, fixture.KEYS[1], 0)); time.sleep(2)
            capture(evidence / 'before-input.png')
            pad.emit((1, fixture.KEYS[11], 1)); time.sleep(.2)
            pad.emit((1, fixture.KEYS[11], 0)); time.sleep(.3)
            capture(evidence / 'after-down.png')
            pad.emit((1, fixture.KEYS[14], 1), (1, fixture.KEYS[15], 1)); time.sleep(.04)
            pad.emit((1, fixture.KEYS[14], 0), (1, fixture.KEYS[15], 0))
            wait_for(lambda: observe()['state']['quickOpen'] and ready(), 'Global panel did not take input')
            time.sleep(.3); capture(evidence / 'panel.png')
            observe('back'); wait_for(lambda: not observe()['state']['quickOpen'] and ready(), 'B did not resume game')
            observe('quick'); wait_for(ready, 'Stop panel did not settle')
            for _ in range(5 - observe()['state']['quickIndex']): observe('down')
            observe('accept'); observe('down'); observe('accept')
            wait_for(lambda: not observe()['state']['externalSession'] and ready(), game + ' stop did not restore desktop')
            assert not Path(f'/proc/{engine}').exists() and observe()['session'] == session
            result = json.loads((state / game / 'host-result.json').read_text())
            assert result['sharedDisplay'] and result['requestedStop'] and not result['forcedKill'], result
            assert not list((state / game / 'sessions').iterdir()), 'Disposable game directory survived'
            results.append(result)
        (out / 'result.json').write_text(json.dumps({'status': 'SHARED_PORT_FRONTENDS_HOST_PASS', 'games': results,
            'boundary': 'Hash-pinned source-built GTA and retained Mono/Stardew, Wayland/software GL, synthetic routed inputs and silent audio. No target gameplay or save/load acceptance.'}, indent=2) + '\n')
        print('SHARED_PORTS_PASS: three real engines, routed input endpoints, global panel and same desktop recovery')
    finally:
        if shell.poll() is None:
            shell.terminate()
            try: shell.wait(timeout=5)
            except subprocess.TimeoutExpired: shell.kill(); shell.wait(timeout=3)
        for game in ('gta3', 'gtavc', 'stardew'):
            target = out / game; target.mkdir(exist_ok=True)
            for name in ('host-runtime.log', 'host-result.json'):
                source = state / game / name
                if source.exists(): shutil.copyfile(source, target / name)
        log.close()
        if routed: routed.unlink()
        pad.close()
