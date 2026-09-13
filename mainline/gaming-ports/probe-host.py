#!/usr/bin/env python3
"""Bounded, init-reaped container probe for original local ports. No host services."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import uuid

IMAGE = 'cgutman/moonlight-packaging@sha256:f25a3e2ad90b85d1a4358e2d612ed311165cddd62aa194455a5dbed844d66d69'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game', choices=['gta3', 'gtavc', 'stardew'])
    parser.add_argument('--content-root', type=Path, required=True)
    parser.add_argument('--debs', type=Path, required=True)
    parser.add_argument('--mono', type=Path)
    parser.add_argument('--mono-compat', type=Path)
    parser.add_argument('--engine', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--exercise', action='store_true')
    parser.add_argument('--seconds', type=int, default=30)
    args = parser.parse_args()
    paths = [args.content_root, args.debs, args.output] + ([args.mono] if args.mono else []) + ([args.engine] if args.engine else [])
    if not 5 <= args.seconds <= 120 or any(not path.is_absolute() or path.is_symlink() for path in paths):
        parser.error('Use absolute non-symlink paths and a 5..120 second game bound')
    endpoint = subprocess.check_output(['docker', 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'], text=True).strip()
    if not endpoint.startswith('unix://'):
        parser.error('This probe requires an identified local Docker endpoint')
    args.output.mkdir(parents=True, exist_ok=True)
    name = 'r46h-port-' + uuid.uuid4().hex[:12]
    code = Path(__file__).resolve().parent
    command = ['docker', 'run', '--name', name, '--init', '--rm', '--network', 'none', '--memory', '1536m',
               '--cpus', '2', '--pids-limit', '256', '--security-opt', 'no-new-privileges', '--entrypoint', '/bin/bash',
               '-v', f'{code}:/code:ro', '-v', f'{args.content_root}:/content:ro',
               '-v', f'{args.debs}:/debs:ro', '-v', f'{args.output}:/out']
    if args.mono:
        command += ['-v', f'{args.mono}:/mono:ro']
    if args.mono_compat:
        command += ['-v', f'{args.mono_compat}:/mono-compat.so:ro']
    if args.engine:
        command += ['-v', f'{args.engine}:/engine:ro']
    command += [IMAGE, '-c', 'set -eu; dpkg -i /debs/*.deb > /out/setup.log 2>&1; '
                'g++ -fPIC -O2 /code/capture-x11.cpp -o /out/capture-x11 $(pkg-config --cflags --libs Qt6Gui); '
                'exec xvfb-run -a -s "-screen 0 1024x768x24" python3 -I -B /code/local_port.py "$@"',
                'probe', args.game, '--content-root', '/content', '--state', '/out/state', '--host-test', '--seconds', str(args.seconds), '--capture-tool', '/out/capture-x11']
    if args.mono:
        command += ['--mono', '/mono']
    if args.mono_compat:
        command += ['--mono-compat', '/mono-compat.so']
    if args.engine:
        command += ['--engine', '/engine']
    if args.exercise:
        command += ['--exercise']
    print(json.dumps({'event': 'started', 'container': name, 'output': str(args.output)}), flush=True)
    timed_out = False
    with (args.output / 'probe.log').open('wb') as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        try:
            status = process.wait(timeout=args.seconds + 90)
        except subprocess.TimeoutExpired:
            timed_out = True
            subprocess.run(['docker', 'stop', '--timeout', '5', name], stdout=log, stderr=log, timeout=15)
            status = process.wait(timeout=15)
        finally:
            if process.poll() is None:
                subprocess.run(['docker', 'kill', name], stdout=log, stderr=log, timeout=15)
                process.kill(); process.wait()
    result = {'game': args.game, 'container': name, 'image': IMAGE, 'exit': status, 'outerTimeout': timed_out,
              'boundary': 'isolated host container only; no device display/audio/input acceptance'}
    (args.output / 'probe.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    return 1 if timed_out or status else 0


if __name__ == '__main__':
    sys.exit(main())
