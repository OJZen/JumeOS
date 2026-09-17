#!/usr/bin/env python3
"""Isolated working directories for the identified original SDL2 GTA engines."""
import argparse
import configparser
import contextlib
import json
import os
from pathlib import Path
import platform
import selectors
import resource
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from manager import private_dir, digest, atomic_json

ORIGINAL_PROFILES = {
    'gta3': ('re3', 'd33f2446c4fc89f9a05c07e0dc0b60646c1115129db73cb00e33f5606feeedb0'),
    'gtavc': ('reVC', 'ab149ae9c2372ee7f5f4384fe8b2ffc37446fe0ccbf0a48722289fc5a803d5b9'),
}
SOURCE_PROFILES = {
    'gta3': ('re3', '6ebf8aedffa2a43bfeac93863917da33b13ae2ce0bff672d7a02018444bc12f4'),
    'gtavc': ('reVC', 'd19bbe5b90648e6ad0ae10b10f27fa256f84fd91381a38187ffd8c1e7814aa3c'),
}

DEVICE_VIDEO_MODE = (b'Width=1024\nHeight=768\n', b'Width=640\nHeight=480\n')

STARDEW = {
    'SVLoader.exe': '8fcf12a5ec69fbcc40cc02d484a8e6f9cad20c9e8c57c16b78c47ed28a7fef36',
    'gamedata/Stardew Valley.exe': '0cb091faf1c3ade402340641fc47bcf9a8f6e591a645f27a4c0db2fcdc966086',
    'gamedata/Stardew Valley.exe.config': '44d076bfb66070eb138c4472a9d9688e092c5478428b87c9c3ef3e9bc5a8fe48',
    'dlls/StardewPatches.dll': '68778b9a9835509146065def9af99df30c0f0689a745ff841ca0b39bf9965f3b',
    'dlls/MonoGame.Framework.dll': 'bb1b6f83e1441e45715a173a9c1946a57fbd351c9171877147446eb4f6cde36d',
    'libs/libret0.so': 'f2870c6afe1ae1eca88a9f721e1c1eeac697fa189ee3e7454e35495a1ebea3d9',
    'libs/liblwjgl_lz4.so': '7704111699a3491554eee629b5cdf14a36dc22915e2e6d18e6fd0ddca651ec6f',
}


def _device_libraries(script=Path(__file__)):
    root = script.resolve().parents[3]
    return ':'.join(str(root / path) for path in ('lib/r46h-ports', 'lib/aarch64-linux-gnu'))


def _packaged_engine_path(game, script=Path(__file__)):
    return script.resolve().parents[3] / 'lib/r46h-ports' / SOURCE_PROFILES[game][0]


def frontend_reached(log):
    return any(marker in log for marker in (b'GS_FRONTEND', b'LOAD frontend'))


def inspect(game, content):
    if game == 'stardew':
        source = content / 'ports/stardewvalley1615'
        for name, expected in STARDEW.items():
            file = source / name
            if not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(content.resolve()) or digest(file) != expected:
                raise ValueError('Stardew profile input differs: ' + name)
        if not (source / 'gamedata/Content').is_dir():
            raise ValueError('Stardew content is missing')
        return source, source / 'SVLoader.exe'
    name, expected = ORIGINAL_PROFILES[game]
    source = content / 'ports' / game
    executable = source / name
    if source.is_symlink() or not source.resolve().is_relative_to(content.resolve()):
        raise ValueError('Game directory escaped the original content root')
    if executable.is_symlink() or not executable.is_file() or digest(executable) != expected:
        raise ValueError('Original SDL2 engine hash differs from the inspected profile')
    names = {path.name.casefold(): path for path in source.iterdir()}
    for required in ('data', 'models', 'text', 'audio'):
        path = names.get(required)
        if not path or not path.is_dir() or path.is_symlink():
            raise ValueError('Missing original resource directory: ' + required)
    return source, executable


@contextlib.contextmanager
def prepared(game, content, state, host_test=False, mono=None, mono_compat=None, engine=None):
    if game == "stardew":
        with prepared_stardew(content, state, mono, mono_compat) as plan:
            yield plan
        return
    source, original = inspect(game, content)
    executable = original if host_test and engine is None else (engine if engine is not None else _packaged_engine_path(game))
    if executable != original and (not executable.is_absolute() or not executable.is_file() or executable.is_symlink() or digest(executable) != SOURCE_PROFILES[game][1]):
        raise ValueError('Source-built game engine differs from the packaged profile')
    private_dir(state)
    config = private_dir(state / 'config')
    saves = private_dir(state / 'saves')
    sessions = private_dir(state / 'sessions')
    cache = private_dir(state / 'cache')
    data = private_dir(state / 'data')
    name = original.name
    config_file = config / (name + '.ini')
    if config_file.is_symlink():
        raise ValueError('Managed game configuration is a symbolic link')
    if not config_file.exists():
        original = source / (name + '.ini')
        if original.is_symlink() or not original.is_file():
            raise ValueError('Missing original game configuration')
        fd, temporary = tempfile.mkstemp(prefix='.initial-', dir=config)
        try:
            with os.fdopen(fd, 'wb') as output, original.open('rb') as input_file:
                if host_test:
                    shutil.copyfileobj(input_file, output)
                else:
                    output.write(input_file.read().replace(*DEVICE_VIDEO_MODE, 1))
                output.flush()
                os.fsync(output.fileno())
            # Publish a complete first copy without replacing another session's config.
            os.link(temporary, config_file)
            directory_fd = os.open(config, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            os.unlink(temporary)
    with tempfile.TemporaryDirectory(prefix='game-', dir=sessions) as directory:
        working = Path(directory)
        # The host test mounts content read-only; the target supervisor must verify /roms is read-only.
        for resource in source.iterdir():
            if resource.name in ('userfiles', 'libs', name + '.ini', 'log.txt') or not resource.is_dir():
                continue
            if resource.is_symlink() or not resource.resolve().is_relative_to(content.resolve()):
                raise ValueError('Original resource contains an external link')
            (working / resource.name).symlink_to(resource, target_is_directory=True)
        (working / 'userfiles').symlink_to(saves, target_is_directory=True)
        mapping = os.environ.get('SDL_GAMECONTROLLERCONFIG', '').strip()
        (working / 'gamecontrollerdb.txt').write_text(mapping + ('\n' if mapping else ''))
        if host_test:
            # Host geometry stays in this disposable file; never save it as the device preference.
            settings = configparser.ConfigParser(interpolation=None, strict=False)
            settings.optionxform = str
            settings.read(config_file)
            if 'VideoMode' not in settings:
                settings['VideoMode'] = {}
            settings['VideoMode'].update({'Windowed': '1', 'Width': '1024', 'Height': '768'})
            with (working / (name + '.ini')).open('w') as output:
                settings.write(output, space_around_delimiters=False)
        else:
            (working / (name + '.ini')).symlink_to(config_file)
        yield {'program': str(executable), 'arguments': [], 'directory': str(working), 'saveDirectory': str(saves),
               'environment': {'PAN_MESA_DEBUG': 'noafbc', 'XDG_CONFIG_HOME': str(config), 'XDG_CACHE_HOME': str(cache), 'XDG_DATA_HOME': str(data)}}


@contextlib.contextmanager
def prepared_stardew(content, state, mono, mono_compat):
    source, loader = inspect('stardew', content)
    if mono is None or not mono.is_absolute():
        raise ValueError('An explicit private Mono runtime is required')
    executable = mono / 'bin/mono'
    if not executable.is_file() or not executable.resolve().is_relative_to(mono.resolve()) or digest(executable) != '8becea810fdd1c26f99347839d7a606a722bf811bcc9a754ba6ca7edd1c7e93b':
        raise ValueError('Mono executable is outside the private runtime')
    for folder in (state, state / 'saves', state / 'config', state / 'cache', state / 'data', state / 'sessions'):
        private_dir(folder)
    destination = state / 'config/StardewValley'
    if destination.exists() or destination.is_symlink():
        if not destination.is_symlink() or destination.resolve() != (state / 'saves').resolve():
            raise ValueError('Existing Stardew configuration must be inspected before migration')
    else:
        destination.symlink_to(state / 'saves', target_is_directory=True)
    with tempfile.TemporaryDirectory(prefix='game-', dir=state / 'sessions') as directory:
        working = Path(directory)
        for file in (source / 'gamedata').iterdir():
            if file.name.startswith('.'):
                continue
            if file.is_symlink() or not file.resolve().is_relative_to(content.resolve()):
                raise ValueError('Stardew resource escaped the content root')
            (working / file.name).symlink_to(file, target_is_directory=file.is_dir())
        if mono_compat and (not mono_compat.is_absolute() or not mono_compat.is_file() or mono_compat.is_symlink()):
            raise ValueError('Invalid private Mono compatibility library')
        yield {'program': str(executable), 'arguments': [str(loader), str(source / 'gamedata/Stardew Valley.exe'), str(working)],
               'directory': str(working), 'saveDirectory': str(state / 'saves'),
               'environment': {'SDL_NO_SIGNAL_HANDLERS': '0', **({'LD_PRELOAD': str(mono_compat)} if mono_compat else {}), 'MONO_PATH': str(source / 'dlls') + ':' + str(source),
                               'MONOGAME_PATCH': str(source / 'dlls/StardewPatches.dll'),
                               'LD_LIBRARY_PATH': str(source / 'libs'),
                               'XDG_CONFIG_HOME': str(state / 'config'), 'XDG_CACHE_HOME': str(state / 'cache'), 'XDG_DATA_HOME': str(state / 'data')}}


def run_game(game, content, state, seconds, mono=None, mono_compat=None, capture_tool=None, exercise=False, host_test=False, shared_display=False, engine=None):
    if host_test and (platform.machine() != 'aarch64' or not Path('/.dockerenv').exists()):
        raise ValueError('This command runs only inside the bounded AArch64 host-test container')
    if shared_display and (not os.environ.get('WAYLAND_DISPLAY') or os.environ.get('SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT') != '0x5246/0x0049' or exercise):
        raise ValueError('Shared ports require the routed controller and Wayland session; X11 input injection is unavailable')
    if not host_test:
        group = Path('/proc/self/cgroup').read_text()
        unit = r'/r46h-wayland-probe-[0-9]+\.service(?:\n|$)' if shared_display else r'/r46h-shell-probe-[0-9]+\.service(?:\n|$)'
        if os.geteuid() != 1000 or platform.release() != '6.12.99-r46h-mainline-v0.15-gaming-product' or not re.search(unit, group) or content != Path('/roms'):
            raise ValueError('Device execution requires the identified native preview supervisor')
        if Path('/sys/class/block/mmcblk0/device/cid').read_text().strip() != 'fe343253440000002000002d57019567':
            raise ValueError('Device media identity differs')
        mono = Path(__file__).resolve().parents[4] / 'mono'
        mono_compat = Path(__file__).resolve().parents[3] / 'lib/r46h-ports/libmono-compat.so'
    if not os.statvfs(content).f_flag & os.ST_RDONLY:
        raise ValueError('The original content mount must be read-only')
    started = time.monotonic()
    with prepared(game, content, state, host_test=host_test, mono=mono, mono_compat=mono_compat, engine=engine) as plan, contextlib.ExitStack() as cleanup:
        env = {**os.environ, 'SDL_VIDEODRIVER': 'x11', 'SDL_AUDIODRIVER': 'dummy', 'ALSOFT_DRIVERS': 'null',
               'LIBGL_ALWAYS_SOFTWARE': '1', 'SDL_NO_SIGNAL_HANDLERS': '1'}
        env.pop('LD_LIBRARY_PATH', None)  # Do not load the old card's GL dispatch libraries.
        env.pop('LD_PRELOAD', None)
        env.update(plan.get('environment', {}))
        if not host_test:
            env.update({'SDL_VIDEODRIVER': 'kmsdrm', 'SDL_AUDIODRIVER': 'alsa', 'ALSOFT_DRIVERS': 'alsa'})
            for key in ('LIBGL_ALWAYS_SOFTWARE', 'GALLIUM_DRIVER', 'MESA_GL_VERSION_OVERRIDE', 'MESA_GLES_VERSION_OVERRIDE', 'QT_IM_MODULE'):
                env.pop(key, None)
            libraries = _device_libraries()
            env['LD_LIBRARY_PATH'] = libraries + (':' + env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
        if shared_display:
            env['SDL_VIDEODRIVER'] = 'wayland'
        stop_requested = False
        def request_stop(signum, frame):
            nonlocal stop_requested
            stop_requested = True
        for signum in (signal.SIGTERM, signal.SIGINT):
            cleanup.callback(signal.signal, signum, signal.signal(signum, request_stop))
        proc = subprocess.Popen([plan['program'], *plan['arguments']], cwd=plan['directory'], env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=not shared_display)
        def send_signal(signum):
            # Shared children stay in Applications' group; never signal our own group recursively.
            with contextlib.suppress(ProcessLookupError):
                if shared_display:
                    proc.send_signal(signum)
                else:
                    os.killpg(proc.pid, signum)
        os.set_blocking(proc.stdout.fileno(), False)
        log = bytearray()
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        stop = False
        stop_started = None
        stop_grace = 5
        captured = False
        forced_kill = False
        input_sent = False
        input_attempted = False
        geometry = ""
        try:
            while True:
                for key, mask in selector.select(.1):
                    try:
                        data = os.read(key.fd, 65536)
                    except BlockingIOError:
                        continue
                    log.extend(data[:max(0, 262144 - len(log))])
                if proc.poll() is not None:
                    while True:
                        try:
                            data = os.read(proc.stdout.fileno(), 65536)
                        except BlockingIOError:
                            break
                        if not data:
                            break
                        log.extend(data[:max(0, 262144 - len(log))])
                    break
                elapsed = time.monotonic() - started
                if exercise and not input_attempted and elapsed >= 6:
                    input_attempted = True
                    windows = subprocess.run(['xdotool', 'search', '--onlyvisible', '--pid', str(proc.pid)], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3)
                    ids = windows.stdout.decode().splitlines()
                    if windows.returncode == 0 and len(ids) == 1:
                        geometry = subprocess.check_output(['xdotool', 'getwindowgeometry', '--shell', ids[0]], text=True, timeout=3)
                        if game == 'stardew':
                            subprocess.run(['xdotool', 'windowsize', ids[0], '1024', '768'], check=True, timeout=3)
                            subprocess.run(['xdotool', 'windowmove', ids[0], '0', '0'], check=True, timeout=3)
                        sent = subprocess.run(['xdotool', 'key', '--window', ids[0], 'Return'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
                        input_sent = sent.returncode == 0
                if capture_tool and not captured and elapsed >= seconds - 2:
                    captured = True
                    capture = subprocess.run([str(capture_tool), str(state / 'frame.png')], stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL, timeout=8)
                    captured = capture.returncode == 0
                    capture_tool = None
                if (elapsed >= seconds or stop_requested) and stop_started is None:
                    stop = elapsed >= seconds
                    stop_grace = 1 if shared_display and not stop else 5
                    stop_started = time.monotonic()
                    send_signal(signal.SIGTERM)
                elif stop_started is not None and time.monotonic() - stop_started >= stop_grace:
                    forced_kill = True
                    send_signal(signal.SIGKILL)
        finally:
            selector.close()
            proc.stdout.close()
            if proc.poll() is None:
                send_signal(signal.SIGKILL)
                proc.wait()
        (state / ('host-runtime.log' if host_test else 'runtime.log')).write_bytes(log)
        result = {'game': game, 'exit': proc.returncode, 'boundedStop': stop, 'requestedStop': stop_requested, 'sharedDisplay': shared_display, 'seconds': round(time.monotonic() - started, 2),
                  'engine_sha256': STARDEW['SVLoader.exe'] if game == 'stardew' else digest(Path(plan['program'])), 'sourceReadOnly': True,
                  'frontendReached': frontend_reached(log), 'x11ReturnSent': input_sent, 'initialWindowGeometry': geometry, 'captured': captured, 'forcedKill': forced_kill,
                  'deliberateSelfExit': game == 'stardew' and b'R46H_PORT_SELF_EXIT' in log and proc.returncode == -signal.SIGKILL and not forced_kill, 'peakRssKiB': resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
                  'renderer': next((line for line in log.decode(errors='replace').splitlines() if line.startswith('OpenGL version:')), ''),
                  'boundary': ('AArch64 container, ' + ('Wayland' if shared_display else 'X11') + '/software Mesa, null audio') if host_test else 'R46H bounded process only; LCD/audio/controls require observation'}
        atomic_json(state / ('host-result.json' if host_test else 'result.json'), result)
        print(json.dumps(result))
    return 0 if proc.returncode == 0 or result['deliberateSelfExit'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game', choices=[*ORIGINAL_PROFILES, 'stardew'])
    parser.add_argument('--mono', type=Path)
    parser.add_argument('--mono-compat', type=Path)
    parser.add_argument('--engine', type=Path)
    parser.add_argument('--capture-tool', type=Path)
    parser.add_argument('--exercise', action='store_true')
    parser.add_argument('--shared-display', action='store_true')
    parser.add_argument('--content-root', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--host-test', action='store_true')
    mode.add_argument('--device-run', action='store_true')
    parser.add_argument('--seconds', type=int, default=20)
    args = parser.parse_args()
    if args.device_run and (args.capture_tool or args.exercise or args.mono or args.mono_compat or args.engine):
        parser.error('Host diagnostic overrides are not accepted by the device runner')
    if args.engine and (not args.host_test or args.game == 'stardew'):
        parser.error('Only GTA host tests accept an explicit source-built engine')
    if not args.content_root.is_absolute() or not args.state.is_absolute() or not 5 <= args.seconds <= (2100 if args.device_run else 120):
        parser.error('Absolute paths and a 5..120 second bound are required')
    os.umask(0o077)
    if args.host_test or args.device_run:
        sys.exit(run_game(args.game, args.content_root, args.state, args.seconds, args.mono, args.mono_compat, args.capture_tool, args.exercise, args.host_test, args.shared_display, args.engine))
    source, executable = inspect(args.game, args.content_root)
    print(json.dumps({'game': args.game, 'status': 'PROFILE_INPUTS_MATCH', 'engine': str(executable)}))
