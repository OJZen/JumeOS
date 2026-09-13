#!/usr/bin/env python3
"""One real Qt/HarbourMaster IPC flow with a disposable installed package and offline catalog."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid
import zipfile

repo = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('control', repo / 'mainline/gaming-shell/control.py')
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--binary', type=Path, required=True)
parser.add_argument('--runtime', type=Path, required=True)
parser.add_argument('--evidence', type=Path, required=True)
parser.add_argument('--ipc-root', type=Path)
parser.add_argument('--packaged', action='store_true')
args = parser.parse_args()
output = control.output_directory(args.evidence)
backend = (args.binary.resolve().parent / '../share/r46h/ports/manager.py').resolve() if args.packaged else repo / 'mainline/gaming-ports/manager.py'
backend_options = [] if args.packaged else ['--portmaster-backend', str(backend), '--portmaster-runtime', str(args.runtime.resolve())]

with tempfile.TemporaryDirectory(prefix='catalog-ui-', dir=repo / 'mainline/out/.cache') as directory, tempfile.TemporaryDirectory(prefix='pc.', dir=args.ipc_root or repo / 'mainline/.cache') as ipc:
    root = Path(directory)
    state = root / 'state'
    content = root / 'roms'
    content.mkdir()
    entry = {'version': 4, 'name': 'fixture.zip', 'items': ['Fixture.sh', 'fixture/'],
             'attr': {'title': '-测试游戏', 'desc': '用于目录和卸载检查的临时样本。', 'inst': '测试安装说明。\n原存档不会被覆盖。', 'runtime': [], 'reqs': [], 'arch': ['aarch64'], 'rtr': True}}
    archive = root / 'fixture.zip'
    with zipfile.ZipFile(archive, 'w') as package:
        package.writestr('Fixture.sh', '#!/bin/sh\nexit 99\n')
        package.writestr('fixture/port.json', json.dumps(entry))
        package.writestr('fixture/game', 'not executed')
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software', 'SDL_NO_SIGNAL_HANDLERS': '1'}
    with (output / 'setup.log').open('wb') as log:
        subprocess.run([sys.executable, '-B', str(backend), '--runtime', str(args.runtime.resolve()), '--state', str(state), 'install', '--id', 'fixture.zip', '--archive', str(archive)], env=env, stdout=log, stderr=log, check=True)
    base = state / 'tools/portmaster'
    source = base / 'registry/PortMaster/config/020_portmaster.source.json'
    cfg = json.loads(source.read_text())
    md5 = hashlib.md5(archive.read_bytes()).hexdigest()
    entry['source'] = {'name': 'fixture.zip', 'size': archive.stat().st_size, 'md5': md5, 'url': 'https://example.invalid/fixture.zip'}
    cfg['data'] = {'ports': ['fixture.zip'], 'utils': [], 'info': {'fixture.zip': entry}, 'data': {'fixture.zip': entry['source']}}
    source.write_text(json.dumps(cfg))
    save = state / 'tools/ports/fixture/saves/progress'
    save.parent.mkdir(parents=True)
    save.write_text('must survive uninstall')
    (state / 'preview.json').write_text(json.dumps({'version': 3, 'volume': 55, 'brightness': 70, 'reducedMotion': False, 'favorites': [], 'monitor': False, 'fontPercent': 120, 'dimSeconds': 0, 'applicationFavorites': []}))
    sock = Path(ipc) / 'control.sock'
    if args.packaged:
        # A packaged tool must work on v0.17 without a system Python executable.
        assert (args.binary.resolve().parent / 'python3.13').is_file()
        env['PATH'] = '/nonexistent'
    with (output / 'runtime.log').open('wb') as log:
        process = subprocess.Popen([str(args.binary.resolve()), '--state-dir', str(state), '--content-root', str(content), '--scene', 'ports',
                                    *backend_options, '--control-dir', ipc, '--quit-after', '35'],
                                   env=env, stdout=log, stderr=log)
        completed = False
        try:
            deadline = time.monotonic() + 15
            while not sock.exists():
                assert process.poll() is None and time.monotonic() < deadline, 'missing Qt endpoint'
                time.sleep(.05)
            current = None
            def ask(op='observe', **values):
                global current
                current = control.exchange(sock, dict(version=1, id=str(uuid.uuid4()), op=op, **{'screenshot': False, **values}))
                return current
            def wait():
                deadline = time.monotonic() + 15
                while ask()['state']['toolBusy']:
                    assert time.monotonic() < deadline, 'backend did not finish'
                    time.sleep(.05)
                return current['state']
            def tap(action):
                ask()
                return ask('tap', action=action, session=current['session'], sequence=current['sequence'], binary_sha256=current['binary_sha256'])['state']
            wait()
            assert tap('favorite')['portCatalogOpen']
            wait()
            before = ask()
            try:
                ask('text', text='not allowed', session=before['session'], sequence=before['sequence'], binary_sha256=before['binary_sha256'])
            except control.ControlError as error:
                assert 'field_unavailable' in str(error)
            else:
                raise AssertionError('Text accepted outside a supported editor')
            assert ask()['sequence'] == before['sequence']
            assert not current['state']['toolSaveError']
            control.save_result(output, ask(screenshot=True))
            tap('accept')
            assert not wait()['portCatalogSidebar']
            control.save_result(output, ask(screenshot=True))
            for _ in range(4): tap('down')
            tap('accept'); assert ask()['state']['choicesOpen']
            tap('home'); assert ask()['state']['choicesOpen']
            tap('back')
            for _ in range(4): tap('up')
            tap('accept')
            assert current['state']['choicesOpen']
            tap('home'); tap('nextTab')
            assert ask()['state']['choicesOpen'] and current['state']['portCatalogOpen']
            tap('back')  # Do not download from the synthetic URL.
            tap('back')  # Sidebar.
            assert tap('favorite')['editing']
            assert ask()['state']['sensitiveVisible'] and current['state']['remoteTextAllowed']
            before = ask()
            try:
                ask('text', text='wrong sequence', session=before['session'], sequence=before['sequence'] - 1, binary_sha256=before['binary_sha256'])
            except control.ControlError as error:
                assert 'stale_sequence' in str(error)
            else:
                raise AssertionError('Stale text request accepted')
            before = ask()
            ask('text', text='-测', session=before['session'], sequence=before['sequence'], binary_sha256=before['binary_sha256'])
            assert ask(screenshot=True)['capture']['status'] == 'sensitive_entry'
            tap('submit'); wait()
            assert current['state']['portCatalogTotal'] == 1
            tap('erase'); wait()  # Installed filter.
            tap('accept'); wait()
            tap('down'); tap('down'); tap('accept')
            assert ask()['state']['choicesOpen']
            tap('down'); tap('accept'); wait()
            assert not json.loads((base / 'installed.json').read_text())['packages']
            assert save.read_text() == 'must survive uninstall'
            assert ask()['state']['portCatalogSidebar']
            assert not tap('back')['portCatalogOpen']
            tap('back'); tap('home'); tap('accept'); tap('favorite')  # Moonlight add-host editor is not writable via text IPC.
            assert ask()['state']['editing'] and not current['state']['remoteTextAllowed']
            before = ask()
            try:
                ask('text', text='127.0.0.1', session=before['session'], sequence=before['sequence'], binary_sha256=before['binary_sha256'])
            except control.ControlError as error:
                assert 'field_unavailable' in str(error)
            else:
                raise AssertionError('Private host editor accepted remote text')
            tap('back'); tap('back')
            completed = True
        finally:
            if completed:
                process.wait(timeout=40)
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
    assert process.returncode == 0 and not sock.exists()
    text = (output / 'runtime.log').read_text(errors='replace')
    assert not any(message in text for message in ['ReferenceError:', 'TypeError:', 'is not a type', 'failed to load']), text[-4000:]
    print('PORTMASTER_UI_PASS: real backend, catalog/details/filter, confirmation isolation, search privacy, uninstall/save preservation and clean return')
