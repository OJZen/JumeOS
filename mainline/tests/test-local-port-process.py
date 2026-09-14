#!/usr/bin/env python3
"""Real process/signal check in an isolated Linux container; no game compatibility claim."""
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

assert Path('/.dockerenv').exists()

if len(sys.argv) > 1:
    role, mode, directory = sys.argv[1:]
    state = Path(directory)
    if role == 'engine':
        def finish(signum, frame):
            if mode == 'shared-bound-slow': time.sleep(2)
            (state / 'saves/flushed').write_text('saved before shutdown')
            sys.exit(0)
        signal.signal(signal.SIGTERM, signal.SIG_IGN if mode == 'shared-ignore' else finish)
        (state / 'engine.json').write_text(json.dumps({'pid': os.getpid(), 'group': os.getpgrp()}))
        while True:
            time.sleep(.05)
    spec = importlib.util.spec_from_file_location('port', '/code/local_port.py')
    port = importlib.util.module_from_spec(spec); spec.loader.exec_module(port)
    @contextlib.contextmanager
    def prepared(*args, **kwargs):
        (state / 'saves').mkdir()
        (state / 'saves/existing').write_text('keep')
        with tempfile.TemporaryDirectory(dir=state) as work:
            yield {'program': sys.executable, 'arguments': [__file__, 'engine', mode, directory], 'directory': work}
        (state / 'cleaned').write_text('yes')
    port.prepared = prepared
    os.environ.update(WAYLAND_DISPLAY='fixture', SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT='0x5246/0x0049')
    seconds = 5 if mode == 'shared-bound-slow' else 30
    sys.exit(port.run_game('gta3', Path('/content'), state, seconds, host_test=True, shared_display=mode != 'direct'))

with tempfile.TemporaryDirectory(prefix='r46h-port-process-', dir='/run') as directory:
    for mode in ('direct', 'shared', 'shared-ignore', 'shared-bound-slow'):
        state = Path(directory) / mode; state.mkdir()
        worker = subprocess.Popen([sys.executable, '-B', __file__, 'worker', mode, str(state)],
                                  start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            end = time.monotonic() + 5
            while not (state / 'engine.json').exists() and time.monotonic() < end and worker.poll() is None:
                time.sleep(.02)
            engine = json.loads((state / 'engine.json').read_text())
            assert (engine['group'] == worker.pid) == (mode != 'direct')
            if mode == 'shared-bound-slow':
                output, _ = worker.communicate(timeout=10)
            else:
                start = time.monotonic()
                if mode == 'direct': worker.terminate()
                else: os.killpg(worker.pid, signal.SIGTERM)
                output, _ = worker.communicate(timeout=4)
            result = json.loads((state / 'host-result.json').read_text())
            if mode == 'shared-bound-slow':
                assert result['boundedStop'] and not result['requestedStop'] and not result['forcedKill'], result
            else:
                assert result['requestedStop'] and not result['boundedStop'], result
                assert result['forcedKill'] == (mode == 'shared-ignore'), result
            assert worker.returncode == (1 if mode == 'shared-ignore' else 0), output
            assert not Path('/proc/' + str(engine['pid'])).exists()
            assert (state / 'cleaned').exists() and (state / 'saves/existing').read_text() == 'keep'
            assert (state / 'saves/flushed').exists() == (mode != 'shared-ignore')
            if mode not in ('direct', 'shared-bound-slow'):
                assert time.monotonic() - start < 1.5
        finally:
            if worker.poll() is None:
                os.killpg(worker.pid, signal.SIGKILL); worker.wait(timeout=3)
print('PORT_PROCESS_PASS: inherited group, graceful save/cleanup, fast requested stop and slow bounded cleanup')
