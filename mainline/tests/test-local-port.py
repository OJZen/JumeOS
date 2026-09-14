#!/usr/bin/env python3
"""Check working-directory isolation with real retained profile inputs, without running games."""
import argparse
import importlib.util
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

repo = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('local_port', repo / 'mainline/gaming-ports/local_port.py')
port = importlib.util.module_from_spec(spec); spec.loader.exec_module(port)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--content-root', type=Path, required=True)
parser.add_argument('--mono', type=Path, required=True)
args = parser.parse_args()
os.umask(0o077)
assert port._device_libraries(Path('/payload/usr/share/r46h/ports/local_port.py')) == \
    '/payload/usr/lib/r46h-ports:/payload/usr/lib/aarch64-linux-gnu'
assert port._packaged_engine_path('gta3', Path('/payload/usr/share/r46h/ports/local_port.py')) == \
    Path('/payload/usr/lib/r46h-ports/re3')
assert port.frontend_reached(b'GS_FRONTEND')
assert port.frontend_reached(b'LOAD frontend2')
assert not port.frontend_reached(b'OpenGL version only')
with tempfile.TemporaryDirectory(prefix='local-port-', dir=repo / 'mainline/out/.cache') as directory:
    root = Path(directory)
    for game in ('gta3', 'gtavc'):
        state = root / game
        with port.prepared(game, args.content_root, state, host_test=True) as plan:
            work = Path(plan['directory'])
            assert plan['environment']['PAN_MESA_DEBUG'] == 'noafbc'
            assert (work / 'userfiles').resolve() == (state / 'saves').resolve()
            assert (work / 'data').is_symlink()
            config = state / 'config' / (Path(plan['program']).name + '.ini')
            original = config.read_bytes()
            (work / config.name).write_text('host geometry only')
            assert config.read_bytes() == original
        assert not work.exists()
    # An interrupted first copy must not leave a partial config that looks initialized.
    failed = root / 'failed-copy'
    with patch.object(port.shutil, 'copyfileobj', side_effect=OSError('disk full')):
        try:
            with port.prepared('gta3', args.content_root, failed, host_test=True):
                raise AssertionError('Copy unexpectedly completed')
        except OSError:
            pass
    assert not list((failed / 'config').iterdir())
    with port.prepared('gta3', args.content_root, failed, host_test=True) as plan:
        assert (failed / 'config/re3.ini').read_bytes() == (args.content_root / 'ports/gta3/re3.ini').read_bytes()
    state = root / 'stardew'
    with port.prepared('stardew', args.content_root, state, mono=args.mono) as plan:
        work = Path(plan['directory'])
        assert (state / 'config/StardewValley').resolve() == state / 'saves'
        assert (work / 'Content').is_symlink()
        assert plan['arguments'][2] == str(work)
        assert 'PAN_MESA_DEBUG' not in plan['environment']
        assert plan['environment']['XDG_CONFIG_HOME'] == str(state / 'config')
    assert not work.exists()
    for game in ('gta3', 'stardew'):
        try:
            port.run_game(game, args.content_root, root / 'refused', 5, host_test=False)
        except (ValueError, FileNotFoundError):
            pass
        else:
            raise AssertionError('Host crossed the physical device guard')
print('LOCAL_PORT_PREPARATION_PASS: identified inputs, separate saves/configs, disposable workspaces and device rejection')
