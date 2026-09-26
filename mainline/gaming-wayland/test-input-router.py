#!/usr/bin/env python3
"""Real uinput routing in an isolated Linux container; never opens host inputs."""
import fcntl
import os
from pathlib import Path
import select
import signal
import socket
import stat
import struct
import subprocess
import sys
import time

assert Path('/.dockerenv').exists() and sys.platform == 'linux'
KEYS = [304, 305, 307, 308, 310, 311, 312, 313, 314, 315, 544, 545, 546, 547, 706, 707, 708]
AXES = [0, 1, 3, 4]
EVENT = struct.Struct('llHHi')
PACKET = struct.Struct('<IIQIII4i32sI')
assert PACKET.size == 80


def ioctl_code(direction, kind, number, size=0):
    return direction << 30 | size << 16 | ord(kind) << 8 | number


class Pad:
    def __init__(self, product=0x0048):
        self.fd = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
        self.path = None
        for kind in (1, 3):
            fcntl.ioctl(self.fd, ioctl_code(1, 'U', 100, 4), kind)
        for key in KEYS:
            fcntl.ioctl(self.fd, ioctl_code(1, 'U', 101, 4), key)
        for axis in AXES:
            fcntl.ioctl(self.fd, ioctl_code(1, 'U', 103, 4), axis)
            fcntl.ioctl(self.fd, ioctl_code(1, 'U', 4, 28), struct.pack('H2x6i', axis, 0, -32768, 32767, 0, 128, 0))
        fcntl.ioctl(self.fd, ioctl_code(1, 'U', 3, 92), struct.pack('4H80sI', 6, 0x5246, product, 1, b'R46H Combined Gamepad', 0))
        fcntl.ioctl(self.fd, ioctl_code(0, 'U', 1))
        name = bytearray(32)
        fcntl.ioctl(self.fd, ioctl_code(2, 'U', 44, len(name)), name)
        self.path = event_node(name.split(b'\0')[0].decode())

    def emit(self, *events):
        data = b''.join(EVENT.pack(0, 0, *event) for event in (*events, (0, 0, 0)))
        assert os.write(self.fd, data) == len(data)

    def close(self):
        fcntl.ioctl(self.fd, ioctl_code(0, 'U', 2))
        os.close(self.fd)
        if self.path:
            self.path.unlink()


def event_node(sysname):
    assert sysname.startswith('input') and sysname[5:].isdigit()
    base = Path('/sys/devices/virtual/input') / sysname
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        nodes = list(base.glob('event*/dev'))
        if len(nodes) == 1:
            major, minor = map(int, nodes[0].read_text().split(':'))
            assert major == 13
            Path('/dev/input').mkdir(exist_ok=True)
            path = Path('/dev/input') / nodes[0].parent.name
            os.mknod(path, stat.S_IFCHR | 0o600, os.makedev(major, minor))
            return path
        time.sleep(.01)
    raise AssertionError('Synthetic input did not appear')


def delegated_slots(path='/dev/uinput'):
    handles=[os.open(path,os.O_WRONLY|os.O_CLOEXEC) for _ in range(4)]
    assert handles==list(range(handles[0],handles[0]+4)),handles
    return handles

def routed_devices(slot=0):
    return [p.parent for p in Path('/sys/devices/virtual/input').glob('input*/name')
            if p.read_text().strip()=='R46H Routed Gamepad' and
            (p.parent/'id/product').read_text().strip()==f'{0x49+slot:04x}']

def drain(fd):
    events = []
    while True:
        try:
            raw = os.read(fd, EVENT.size * 256)
        except BlockingIOError:
            return events
        assert raw and len(raw) % EVENT.size == 0
        events.extend(EVENT.unpack_from(raw, offset)[2:] for offset in range(0, len(raw), EVENT.size))


def receive(channel, kind, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if select.select([channel], [], [], max(0, deadline - time.monotonic()))[0]:
            raw = channel.recv(512)
            assert len(raw) == PACKET.size, raw
            packet = PACKET.unpack(raw)
            assert packet[0] == 3
            if packet[1] == kind:
                return packet
    raise AssertionError('Missing broker packet: ' + str(kind))


def command(channel, sequence, mode, slot=0):
    channel.sendall(PACKET.pack(3, 1, sequence, mode, 0, 0, 0, 0, 0, 0, b'', slot))


def inject(channel, sequence, keys, axes=(0, 0, 0, 0), milliseconds=100, slot=0):
    channel.sendall(PACKET.pack(3, 6, sequence, 1, milliseconds, keys, *axes, b'', slot))


def cancel(channel, sequence):
    channel.sendall(PACKET.pack(3, 7, sequence, 1, 0, 0, 0, 0, 0, 0, b'', 0))


def run(executable):
    pad = Pad()
    controller, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    proc = None; sink = observer = -1; routed = None
    try:
        observer = os.open(pad.path, os.O_RDONLY | os.O_NONBLOCK)
        proc = subprocess.Popen([executable, str(pad.path), str(child.fileno()), '120'], pass_fds=[child.fileno()])
        child.close()
        ready = receive(controller, 2)
        routed = event_node(ready[10].split(b'\0')[0].decode())
        sink = os.open(routed, os.O_RDONLY | os.O_NONBLOCK)
        # Actual axis metadata survives cloning.
        data = bytearray(24)
        fcntl.ioctl(sink, ioctl_code(2, 'E', 0x40, 24), data)
        assert struct.unpack('6i', data)[1:5] == (-32768, 32767, 0, 128)
        command(controller, 1, 1); receive(controller, 5)
        pad.emit((1, KEYS[0], 1), (3, 0, 20000)); time.sleep(.05)
        assert {(1, KEYS[0], 1), (3, 0, 20000)} <= set(drain(sink))
        assert not drain(observer), 'Grab leaked input to a pre-existing game reader'
        # Chord consumes both clicks and immediately releases held game controls.
        pad.emit((1, KEYS[14], 1)); time.sleep(.03)
        assert not drain(sink)
        pad.emit((1, KEYS[15], 1))
        request = receive(controller, 4)
        assert request[4] & 2
        events = drain(sink)
        assert (1, KEYS[0], 0) in events and (3, 0, 0) in events
        assert not any(code in KEYS[14:16] for kind, code, value in events if kind == 1)
        command(controller, 2, 0); ack = receive(controller, 5)
        assert ack[4] & 1, 'Held input bypassed the new owner gate'
        pad.emit((1, KEYS[0], 0), (3, 0, 0), (1, KEYS[14], 0), (1, KEYS[15], 0)); time.sleep(.03)
        pad.emit((1, KEYS[10], 1))
        sample = receive(controller, 3)
        assert sample[5] == 1 << 10 and not drain(sink)
        command(controller, 3, 1); assert receive(controller, 5)[4] & 1
        pad.emit((1, KEYS[0], 1)); time.sleep(.03)
        assert not drain(sink), 'Game resumed while a UI control was still held'
        pad.emit((1, KEYS[10], 0), (1, KEYS[0], 0)); time.sleep(.03)
        # A standalone short L3 is delayed but both edges survive.
        pad.emit((1, KEYS[14], 1)); time.sleep(.02)
        pad.emit((1, KEYS[14], 0)); time.sleep(.04)
        edges = [e for e in drain(sink) if e[0] == 1]
        assert edges == [(1, KEYS[14], 1), (1, KEYS[14], 0)], edges
        # Late overlap is two ordinary stick clicks, not an accidental panel chord.
        pad.emit((1, KEYS[14], 1)); time.sleep(.17)
        assert (1, KEYS[14], 1) in drain(sink)
        pad.emit((1, KEYS[15], 1)); time.sleep(.03)
        assert (1, KEYS[15], 1) in drain(sink)
        pad.emit((1, KEYS[14], 0), (1, KEYS[15], 0)); time.sleep(.03)
        drain(sink)
        # Moonlight's shoulder chord is forwarded untouched.
        pad.emit((1, KEYS[4], 1), (1, KEYS[5], 1)); time.sleep(.03)
        assert {(1, KEYS[4], 1), (1, KEYS[5], 1)} <= set(drain(sink))
        pad.emit((1, KEYS[4], 0), (1, KEYS[5], 0)); time.sleep(.03)
        drain(sink)
        # The broker, not the client, owns the short remote hold deadline.
        inject(controller, 4, 1 << 1, (20000, -20000, 32767, -32767), 80)
        time.sleep(.025)
        events = drain(sink)
        assert (1, KEYS[1], 1) in events and (3, 3, 32767) in events and (3, 4, -32768) in events
        done = receive(controller, 8); assert done[2] == 4 and not done[4] & 4
        events = drain(sink); assert (1, KEYS[1], 0) in events and (3, 0, 0) in events
        inject(controller, 5, 1, milliseconds=1001); assert receive(controller, 9)[2] == 5
        inject(controller, 6, (1 << 14) | (1 << 15)); assert receive(controller, 9)[2] == 6
        command(controller, 7, 0); receive(controller, 5)
        inject(controller, 8, 1); assert receive(controller, 9)[2] == 8
        command(controller, 9, 1); receive(controller, 5)
        pad.emit((1, KEYS[0], 1)); time.sleep(.03); drain(sink)
        inject(controller, 10, 1 << 1); assert receive(controller, 9)[2] == 10
        pad.emit((1, KEYS[0], 0)); time.sleep(.03); drain(sink)
        inject(controller, 11, 1 << 1, milliseconds=500); time.sleep(.03)
        assert (1, KEYS[1], 1) in drain(sink)
        pad.emit((1, KEYS[12], 1))
        done = receive(controller, 8); assert done[2] == 11 and done[4] & 4
        time.sleep(.02); events = drain(sink)
        assert (1, KEYS[1], 0) in events and (1, KEYS[12], 1) in events
        pad.emit((1, KEYS[12], 0)); time.sleep(.03); drain(sink)
        inject(controller, 12, 1 << 5, milliseconds=500); time.sleep(.03); drain(sink)
        cancel(controller, 13)
        done = receive(controller, 8); assert done[2] == 12 and done[4] & 4
        assert (1, KEYS[5], 0) in drain(sink)
        inject(controller, 14, 1 << 1, milliseconds=500); time.sleep(.03); drain(sink)
        command(controller, 15, 0)
        done = receive(controller, 8); assert done[2] == 14 and done[4] & 4
        receive(controller, 5); command(controller, 16, 1); receive(controller, 5)
        drain(sink)
        inject(controller, 17, 1 << 1, milliseconds=100)
        inject(controller, 18, 1 << 3)
        assert receive(controller, 9)[2] == 18
        done = receive(controller, 8); assert done[2] == 17 and not done[4] & 4
        drain(sink)
        command(controller, 19, 0); cancel(controller, 20)
        assert receive(controller, 5)[2] == 19, 'A mode ack must retain its own generation when a cancel is queued after it'
        command(controller, 21, 1); receive(controller, 5)
        print('REMOTE_INPUT_KERNEL_PASS: deadline/release, normalized axes, reserved/invalid/UI/busy refusal, physical takeover, explicit cancellation and mode handoff')
        # Force a real evdev queue overrun. Recovered held state stays gated.
        proc.send_signal(signal.SIGSTOP)
        time.sleep(.03)
        for index in range(1001):
            pad.emit((1, KEYS[0], int(index % 2 == 0)))
        proc.send_signal(signal.SIGCONT)
        time.sleep(.08)
        assert not any(e == (1, KEYS[0], 1) for e in drain(sink)), 'SYN_DROPPED replayed a held press'
        pad.emit((1, KEYS[0], 0)); time.sleep(.03)
        pad.emit((1, KEYS[0], 1)); time.sleep(.03)
        assert (1, KEYS[0], 1) in drain(sink)
        pad.emit((1, KEYS[0], 0)); time.sleep(.03)
        drain(sink)
        # Invalid ownership sequence fails closed; destruction releases the grab.
        other_path=event_node(routed_devices(1)[0].name)
        other=os.open(other_path,os.O_RDONLY|os.O_NONBLOCK)
        try:
            command(controller,22,1,1);ack=receive(controller,5);assert ack[-1]==1
            pad.emit((1,KEYS[0],1));time.sleep(.03)
            assert (1,KEYS[0],1) in drain(other) and not drain(sink)
            pad.emit((1,KEYS[0],0));time.sleep(.03);drain(other)
            command(controller,23,1);receive(controller,5)
            pad.emit((1,KEYS[0],1));time.sleep(.03)
            assert (1,KEYS[0],1) in drain(sink) and not drain(other)
            pad.emit((1,KEYS[0],0));time.sleep(.03);drain(sink)
        finally:
            os.close(other);other_path.unlink()
        for seq,key,kind,hold in ((24,3,10,0),(25,2,12,0),(26,9,11,.05),(27,9,13,2.1)):
            pad.emit((1,KEYS[8],1),(1,KEYS[key],1))
            if key==9:
                time.sleep(hold)
                if kind==11:pad.emit((1,KEYS[8],0),(1,KEYS[key],0))
            assert receive(controller,kind)[1]==kind
            assert not any(e[0]==1 and e[1] in (KEYS[8],KEYS[key]) and e[2]==1 for e in drain(sink))
            pad.emit((1,KEYS[8],0),(1,KEYS[key],0));command(controller,seq,1);receive(controller,5);time.sleep(.03)
        print('TASK_INPUT_PASS: isolated slots, Select shortcuts, short release and 2-second forced exit')
        command(controller, 3, 0)
        assert proc.wait(timeout=3) == 1
        pad.emit((1, KEYS[0], 1)); time.sleep(.03)
        assert (1, KEYS[0], 1) in drain(observer)
        print('INPUT_ROUTER_KERNEL_PASS: EVIOCGRAB, real game/UI separation, neutral handoff, chord/standalone clicks, axis metadata, shoulder passthrough, SYN_DROPPED, stale refusal and cleanup')
    finally:
        controller.close(); child.close()
        if proc and proc.poll() is None:
            proc.send_signal(signal.SIGCONT)
            proc.terminate(); proc.wait(timeout=3)
        if sink >= 0: os.close(sink)
        if observer >= 0: os.close(observer)
        if routed: routed.unlink()
        pad.close()
    # Identity guard must refuse an unrelated controller before taking its input.
    pad = Pad(0x1234); controller, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
    try:
        result = subprocess.run([executable, str(pad.path), str(child.fileno()), '120'], pass_fds=[child.fileno()], timeout=3)
        assert result.returncode == 1
    finally:
        child.close(); controller.close(); pad.close()
    print('INPUT_ROUTER_IDENTITY_PASS')

    for path, flags in [('/dev/null', os.O_WRONLY), ('/dev/uinput', os.O_RDONLY)]:
        pad = Pad(); controller, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        invalid = os.open(path, flags)
        try:
            result = subprocess.run([executable, str(pad.path), str(child.fileno()), '120', str(invalid)],
                pass_fds=(child.fileno(), invalid), timeout=3, capture_output=True)
            assert result.returncode == 1 and b'invalid inherited uinput handle' in result.stderr
        finally:
            os.close(invalid); child.close(); controller.close(); pad.close()
    print('INPUT_ROUTER_FD_GUARD_PASS: wrong device and read-only delegated handles rejected')

    for failure in ('controller', 'source'):
        pad = Pad(); controller, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        proc = subprocess.Popen([executable, str(pad.path), str(child.fileno()), '120'], pass_fds=[child.fileno()])
        child.close()
        routed_name = None
        try:
            ready = receive(controller, 2)
            routed_name = ready[10].split(b'\0')[0].decode()
            command(controller, 1, 1); receive(controller, 5)
            inject(controller, 2, 1 << 1, milliseconds=1000); time.sleep(.03)
            if failure == 'controller': controller.close()
            else: pad.close(); pad = None
            assert proc.wait(timeout=3) == 1
            assert not (Path('/sys/devices/virtual/input') / routed_name).exists(), 'Virtual device leaked after ' + failure
        finally:
            controller.close()
            if proc.poll() is None: proc.terminate(); proc.wait(timeout=3)
            if pad: pad.close()
    print('INPUT_ROUTER_DISCONNECT_PASS: lost controller and lost source destroy the routed device')


if __name__ == '__main__':
    run(sys.argv[1])
