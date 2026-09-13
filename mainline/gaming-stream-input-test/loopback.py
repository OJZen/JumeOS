#!/usr/bin/env python3
"""Actual Sunshine/Moonlight loopback in a private container, with synthetic input."""
from array import array
import hashlib
import getpass
import importlib.util
import json
import math
import os
from pathlib import Path
import secrets
import signal
import socket
import subprocess
import sys
import time
import wave

assert Path('/.dockerenv').exists() and os.geteuid() == 0
assert len(sys.argv) in (3, 5)
stage, out = map(Path, sys.argv[1:3])
serving = len(sys.argv) == 5
if serving: assert sys.argv[3] == '--serve' and 10 <= int(sys.argv[4]) <= 1800
spec = importlib.util.spec_from_file_location('pad_fixture', '/project/mainline/gaming-wayland/test-input-router.py')
fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
os.umask(0o077)
state = stage / 'state'; state.mkdir()
for name in ('runtime', 'config', 'data', 'cache', 'host', 'client'):
    (state/name).mkdir()
common = {**os.environ, 'XDG_RUNTIME_DIR': str(state/'runtime'), 'XDG_CONFIG_HOME': str(state/'config'),
          'XDG_DATA_HOME': str(state/'data'), 'XDG_CACHE_HOME': str(state/'cache'),
          'QML_DISABLE_DISK_CACHE': '1', 'QT_DISABLE_SHADER_DISK_CACHE': '1', 'SDL_NO_SIGNAL_HANDLERS': '1',
          'QT_QPA_PLATFORM': 'xcb', 'DISPLAY': ':97'}
processes, logs, nodes = [], [], []
pad = None
seen, minimum, maximum = set(), [0]*6, [0]*6

def stop_signal(number, _frame): raise SystemExit(128+number)
signal.signal(signal.SIGINT, stop_signal); signal.signal(signal.SIGTERM, stop_signal)


def start(argv, name, env=None, **options):
    log = (state/(name+'.log')).open('wb'); logs.append(log)
    process = subprocess.Popen(list(map(str, argv)), env=env or common, start_new_session=True,
                               stdout=log, stderr=subprocess.STDOUT, **options)
    processes.append(process)
    return process


def wait_for(check, message, seconds=8):
    end = time.monotonic()+seconds
    while time.monotonic() < end:
        if check(): return
        time.sleep(.04)
    raise AssertionError(message)


def port_ready(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.1): return True
    except OSError: return False


def host_input():
    try: return json.loads((state/'host-input.json').read_text())
    except (FileNotFoundError, json.JSONDecodeError): return {}


def discover_controllers():
    for name in Path('/sys/devices/virtual/input').glob('input*/name'):
        if name.read_text().startswith('Sunshine X-Box One (virtual) pad'):
            events = list(name.parent.glob('event*/dev'))
            if events and not (Path('/dev/input')/events[0].parent.name).exists(): nodes.append(fixture.event_node(name.parent.name))


def safe_log(name):
    path = state/(name+'.log')
    if not path.exists(): return
    lines = []
    for line in path.read_text(errors='replace').splitlines():
        if any(word in line.lower() for word in ('pin', 'key', 'certificate', 'credential', 'password', 'http', 'salt', 'request')): continue
        lines.append(line[:2048])
    (out/(name+'.log')).write_text('\n'.join(lines[-400:])+'\n')


try:
    for display in ((97,) if serving else (97, 98)):
        start(['Xvfb', ':'+str(display), '-screen', '0', '640x480x24', '-nolisten', 'tcp'], 'xvfb-'+str(display))
        wait_for(lambda: Path('/tmp/.X11-unix/X'+str(display)).exists(), 'Private X display did not start')
    pulse_socket = state/'runtime/pulse-native'
    pulse = state/'pulse.pa'
    pulse.write_text(f'load-module module-native-protocol-unix socket={pulse_socket} auth-anonymous=1\n'
                     'load-module module-null-sink sink_name=r46h-loop channels=2 rate=48000\nset-default-sink r46h-loop\n')
    common['PULSE_SERVER'] = 'unix:'+str(pulse_socket)
    start(['pulseaudio', '--daemonize=no', '--exit-idle-time=-1', '--disallow-exit', '-n', '-F', pulse], 'pulse')
    wait_for(pulse_socket.exists, 'Private PulseAudio server did not start')
    tone = state/'tone.wav'
    with wave.open(str(tone), 'wb') as audio:
        audio.setnchannels(2); audio.setsampwidth(2); audio.setframerate(48000)
        values = array('h')
        for i in range(48000*12):
            value = round(1800*math.sin(2*math.pi*440*i/48000)*min(1, i/960))
            values.extend((value, value))
        audio.writeframes(values.tobytes())
    host_env = {**common, 'QT_QUICK_BACKEND': 'software', 'SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS': '1',
                'SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT': '0x045e/0x02ea', 'SDL_JOYSTICK_DISABLE_UDEV': '1'}
    # This container has no udev daemon; let SDL watch the real event nodes we create.
    Path('/dev/input').mkdir(exist_ok=True)
    (state/'host-input.json.fps').write_text('60')
    start([stage/'test-client', 'server', state/'host-input.json'], 'host-view', host_env)
    wait_for(lambda: host_input().get('renderedFrames', 0)>0, 'Host test window did not render')
    assert host_input().get('controllers') == 0, 'Host test must start without a local source controller'
    apps = state/'host/apps.json'; apps.write_text(json.dumps({'env': {}, 'apps': [{'name': 'Loopback', 'cmd': ''}]}))
    config = state/'host/sunshine.conf'
    config.write_text('\n'.join(['capture = x11', 'encoder = software', 'sw_preset = ultrafast', 'gamepad = xone',
        'keyboard = disabled', 'mouse = disabled', 'audio_sink = r46h-loop', 'upnp = disabled', 'flags = 0',
        'min_log_level = info', 'sunshine_name = R46H Loopback', 'address_family = ipv4',
        f'file_apps = {apps}', f'file_state = {state}/host/state.json', f'credentials_file = {state}/host/credentials.json',
        f'pkey = {state}/host/key.pem', f'cert = {state}/host/cert.pem', f'log_path = {state}/sunshine-file.log'])+'\n')
    sunshine = start([stage/'sunshine/usr/bin/sunshine', config], 'sunshine', stdin=subprocess.PIPE)
    wait_for(lambda: port_ready(47989) or sunshine.poll() is not None, 'Sunshine did not expose its private endpoint', 15)
    assert sunshine.poll() is None, 'Sunshine exited during startup'
    if serving:
        start(['/bin/sh', '-c', 'while paplay --device=r46h-loop "$1"; do :; done', 'r46h-tone', tone], 'tone-loop')
        print('HOST_READY app=Loopback input=Sunshine-Xbox-One display=private-Xvfb audio=private-null-sink', flush=True)
        print('When Moonlight pairs, enter its PIN here; input is hidden. Ctrl+C stops this temporary host.', flush=True)
        end = time.monotonic()+int(sys.argv[4]); prompts = 0; next_prompt_check = 0
        while time.monotonic()<end:
            assert sunshine.poll() is None, 'Sunshine exited'
            discover_controllers()
            info = host_input()
            if 'axes' in info:
                seen.update(i for i, value in enumerate(info['buttons']) if value)
                minimum = [min(a,b) for a,b in zip(minimum,info['axes'])]
                maximum = [max(a,b) for a,b in zip(maximum,info['axes'])]
            if time.monotonic() >= next_prompt_check:
                next_prompt_check = time.monotonic()+.5
                count = (state/'sunshine.log').read_text(errors='replace').count('Please insert pin:')
                if count > prompts:
                    assert sys.stdin.isatty(), 'Pairing requires an interactive Terminal with hidden input'
                    pin = getpass.getpass('Moonlight pairing PIN: ')
                    while len(pin)!=4 or not pin.isascii() or not pin.isdigit(): pin=getpass.getpass('Enter four digits: ')
                    sunshine.stdin.write((pin+'\n').encode()); sunshine.stdin.flush(); del pin
                    prompts = count
            time.sleep(.04)
        print('HOST_END deadline reached', flush=True)
        raise SystemExit(0)
    runtime = stage/'client'
    client_env = {**common, 'DISPLAY': ':98', 'XDG_CONFIG_HOME': str(state/'client/config'),
        'XDG_DATA_HOME': str(state/'client/data'), 'XDG_CACHE_HOME': str(state/'client/cache'),
        'LD_LIBRARY_PATH': str(runtime/'usr/lib/aarch64-linux-gnu')+':'+str(runtime/'usr/lib/aarch64-linux-gnu/libproxy'),
        'QT_PLUGIN_PATH': str(runtime/'usr/lib/aarch64-linux-gnu/qt6/plugins'), 'SDL_VIDEODRIVER': 'x11',
        'SDL_AUDIODRIVER': 'disk', 'SDL_DISKAUDIOFILE': str(state/'decoded.pcm'),
        'SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS': '1', 'SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT': '0x5246/0x0048',
        'SDL_GAMECONTROLLERCONFIG': '06004e84465200004800000001000000,R46H Combined Gamepad,a:b1,b:b0,x:b2,y:b3,back:b8,start:b9,leftshoulder:b4,rightshoulder:b5,lefttrigger:b6,righttrigger:b7,leftstick:b14,rightstick:b15,leftx:a0,lefty:a1,rightx:a2,righty:a3,dpup:b10,dpdown:b11,dpleft:b12,dpright:b13,platform:Linux,'}
    moonlight = runtime/'usr/bin/moonlight-qt'
    pin = f'{secrets.randbelow(10000):04d}'
    pairing = subprocess.Popen([str(moonlight), 'pair', '127.0.0.1', '--pin', pin],
        env={**client_env, 'QT_QPA_PLATFORM': 'offscreen', 'SDL_VIDEODRIVER': 'dummy'},
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    processes.append(pairing); sunshine.stdin.write((pin+'\n').encode()); sunshine.stdin.flush(); del pin
    assert pairing.wait(timeout=20) == 0, 'Real Sunshine pairing failed'
    listed = subprocess.run([str(moonlight), 'list', '127.0.0.1'], env={**client_env, 'QT_QPA_PLATFORM': 'offscreen', 'SDL_VIDEODRIVER': 'dummy'},
                            capture_output=True, timeout=20)
    assert listed.returncode == 0 and b'Loopback' in listed.stdout, 'Fresh application-list query failed'
    (out/'applications.json').write_text(json.dumps({'freshListContainsLoopback': True})+'\n')
    pad = fixture.Pad()
    assert host_input().get('controllers') == 0, 'Host program read the local input source directly'
    error = (state/'moonlight.log').open('wb'); logs.append(error)
    client = subprocess.Popen([str(moonlight), 'stream', '127.0.0.1', 'Loopback', '--resolution', '640x480', '--fps', '30',
        '--bitrate', '3000', '--video-codec', 'H.264', '--video-decoder', 'software', '--display-mode', 'fullscreen',
        '--audio-config', 'stereo', '--no-quit-after', '--no-game-optimization', '--no-hdr', '--no-yuv444'],
        env={**client_env, 'R46H_STREAM_STATS': '1'}, stdout=subprocess.PIPE, stderr=error, start_new_session=True)
    processes.append(client); os.set_blocking(client.stdout.fileno(), False)
    stats, pending = [], bytearray()

    def progress():
        global pending
        discover_controllers()
        try: data = os.read(client.stdout.fileno(), 8192)
        except BlockingIOError: data = b''
        pending += data
        assert len(pending) <= 65536
        while b'\n' in pending:
            line, _, pending = pending.partition(b'\n')
            if line.startswith(b'R46H_STATS '): stats.append(json.loads(line[11:]))
        assert client.poll() is None, 'Native Moonlight client exited'

    def received():
        progress()
        return bool(stats and stats[-1].get('renderedFps', 0)>0 and 'buttons' in host_input())

    wait_for(received, 'Real stream or Sunshine virtual controller did not become ready', 20)
    start(['paplay', '--device=r46h-loop', tone], 'tone')
    image_env = {**common, 'DISPLAY': ':98'}
    subprocess.run([str(stage/'capture-x11'), str(out/'client-neutral.png'), 'green'], env=image_env, check=True, timeout=5)
    states = []
    for raw, button in ((1, 0), (0, 1), (2, 2), (3, 3), (4, 9), (5, 10), (8, 4), (9, 6),
                        (10, 11), (11, 12), (12, 13), (13, 14), (14, 7), (15, 8)):
        pad.emit((1, fixture.KEYS[raw], 1))
        wait_for(lambda: (progress() is None) and host_input()['buttons'][button] == 1, 'Button did not traverse the real stream')
        states.append({'sourceButton': raw, 'hostButton': button, 'value': host_input()['buttons'][button]})
        if raw == 1:
            time.sleep(.2)
            subprocess.run([str(stage/'capture-x11'), str(out/'client-button-a.png'), 'blue'], env=image_env, check=True, timeout=5)
        pad.emit((1, fixture.KEYS[raw], 0))
        wait_for(lambda: (progress() is None) and host_input()['buttons'][button] == 0, 'Remote button stuck after release')
    for raw, axis in ((6, 4), (7, 5)):
        for pressed, value in ((1, 32767), (0, 0)):
            pad.emit((1, fixture.KEYS[raw], pressed))
            wait_for(lambda: (progress() is None) and abs(host_input()['axes'][axis]-value)<1500, 'Trigger did not traverse the real stream')
            states.append({'trigger': axis, 'source': pressed, 'host': host_input()['axes'][axis]})
    for axis_index, code in enumerate(fixture.AXES):
        for value in (-24000, 24000, 0):
            pad.emit((3, code, value))
            wait_for(lambda: (progress() is None) and abs(host_input()['axes'][axis_index]-value)<1500, 'Remote axis range/direction mismatch')
            states.append({'axis': axis_index, 'source': value, 'host': host_input()['axes'][axis_index]})
    deadline = time.monotonic()+4
    while time.monotonic()<deadline: progress(); time.sleep(.04)
    assert len(stats)>=3 and all(s['renderedFps']>0 for s in stats[-3:])
    # Existing native L1+R1 exit, after individual shoulder transmission above.
    pad.emit((1, fixture.KEYS[4], 1), (1, fixture.KEYS[5], 1))
    assert client.wait(timeout=8)==0, 'Native shoulder exit did not complete'
    raw = (state/'decoded.pcm').read_bytes(); samples=array('f'); samples.frombytes(raw[:len(raw)//4*4])
    assert len(samples)>96000 and all(math.isfinite(v) and abs(v)<2 for v in samples), 'Decoded PCM invalid'
    mono=samples[::2]; chunks=[mono[i:i+48000] for i in range(0,len(mono)-48000,48000)]
    loud=max(chunks,key=lambda c:sum(v*v for v in c)); rms=math.sqrt(sum(v*v for v in loud)/len(loud))
    crossing=sum(a<0<=b for a,b in zip(loud,loud[1:])); assert rms>.005 and abs(crossing-440)<30, (rms,crossing)
    with wave.open(str(out/'decoded-tone.wav'),'wb') as audio:
        audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(48000)
        audio.writeframes(array('h',(round(max(-1,min(1,v))*32767) for v in loud)).tobytes())
    report={'status':'REAL_LOOPBACK_HOST_PASS','sunshineVersion':'2026.516.143833','client':'v5',
        'input':states,'videoStatistics':stats,'audio':{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'rms':rms,'positiveCrossingsPerSecond':crossing},
        'boundary':'Real encrypted pairing, stream, software decode, virtual gamepad and captured PCM in one private Linux container. Synthetic source input; no physical R46H, Mac gamepad emulation, hardware decoder, audible output or LCD acceptance.'}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print('REAL_LOOPBACK_PASS: actual list/video/PCM/controller roundtrip and native L1+R1 exit')
finally:
    for process in reversed(processes):
        if process.poll() is None:
            os.killpg(process.pid,signal.SIGTERM)
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired: os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=3)
    for log in logs: log.close()
    if pad: pad.close()
    for node in nodes: node.unlink(missing_ok=True)
    (out/'last-host-input.json').write_text(json.dumps(host_input(),indent=2)+'\n')
    if serving:
        (out/'host-observation.json').write_text(json.dumps({'observedButtons':sorted(seen),'axisMinimum':minimum,'axisMaximum':maximum,
            'boundary':'Samples from the Sunshine virtual controller only; physical origin and LCD/audio need separate observation.'},indent=2)+'\n')
    if 'stats' in globals():
        (out/'last-statistics.json').write_text(json.dumps(stats,indent=2)+'\n')
        (out/'stream-diagnostic.json').write_text(json.dumps({'pendingBytes':len(pending),'hostNodes':[str(p) for p in nodes]},indent=2)+'\n')
    for name in ('sunshine','moonlight','pulse','host-view','xvfb-97','xvfb-98'): safe_log(name)
