#!/usr/bin/env python3
"""One Qt action/observation over local IPC or restricted SSH; verified PNG and JSON."""
import argparse
import base64
import csv
import hashlib
import importlib.util
import ipaddress
import io
import json
import math
import os
import re
from pathlib import Path
import socket
import selectors
import stat
import subprocess
import sys
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parents[2]
MAX_RESPONSE = 16 * 1024 * 1024
spec = importlib.util.spec_from_file_location("r46h_png", REPO / "mainline/gaming-remote-screen/fetch-screen.py")
png_validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(png_validator)


class ControlError(RuntimeError):
    pass


def private_directory(path):
    path = Path(path).absolute()
    metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
        raise ControlError("directory must be user-owned, non-symlink and mode 0700")
    return path


def exchange(path, request):
    path = Path(path).absolute()
    private_directory(path.parent)
    metadata = path.lstat()
    if not stat.S_ISSOCK(metadata.st_mode) or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ControlError("socket must be user-owned and mode 0600")
    encoded = json.dumps(request, separators=(",", ":")).encode() + b"\n"
    if len(encoded) > 4096:
        raise ControlError("request exceeds limit")
    deadline = time.monotonic() + 5
    data = bytearray()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(5)
        client.connect(str(path))
        client.sendall(encoded)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ControlError("response deadline exceeded; observe before retrying an action")
            client.settimeout(remaining)
            chunk = client.recv(min(65536, MAX_RESPONSE + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_RESPONSE:
                raise ControlError("response exceeds limit")
    return validate_response(json.loads(data), request)


def validate_response(response, request):
    if not isinstance(response, dict) or response.get("id") != request["id"] or type(response.get("version")) is not int or response["version"] != 1:
        raise ControlError("response identity mismatch")
    if response.get("ok") is not True:
        raise ControlError("request rejected: " + str(response.get("error", "unknown"))[:64])
    if response.get("application") != "r46h-shell" or response.get("input_backend") != ("routed-uinput" if request['op'] == 'game-input' else "qml-action"):
        raise ControlError("unexpected application or input backend")
    if not isinstance(response.get("session"), str) or type(response.get("sequence")) is not int or not 0 <= response["sequence"] <= 9007199254740991:
        raise ControlError("invalid session metadata")
    if (str(uuid.UUID(response["session"])) != response["session"] or not isinstance(response.get("binary_sha256"), str)
            or not re.fullmatch("[0-9a-f]{64}", response["binary_sha256"])):
        raise ControlError("invalid application identity")
    if request["op"] in {"tap", "text", "game-input"} and (response["session"] != request["session"] or response["sequence"] != request["sequence"] + 1):
        raise ControlError("action result is from a different session or sequence")
    if request['op'] == 'game-input' and response.get('input_status') not in {'completed', 'cancelled', 'unavailable'}:
        raise ControlError('missing bounded game-input result')
    return response


def ssh_exchange(host, port, identity, known_hosts, request):
    host = str(ipaddress.IPv4Address(host))
    if not 1 <= port <= 65535:
        raise ControlError("invalid SSH port")
    for path in (identity, known_hosts):
        if '%' in str(path) or any(ord(c) < 32 or ord(c) == 127 for c in str(path)):
            raise ControlError("SSH paths must not contain expansion tokens or control characters")
        private_directory(path.parent)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ControlError("SSH identity and host-key record must be private regular files")
    encoded = json.dumps(request, separators=(",", ":")).encode() + b"\n"
    if len(encoded) > 4096:
        raise ControlError("request exceeds limit")
    host_file = '"' + str(known_hosts).replace('\\', '\\\\').replace('"', '\\"') + '"'
    command = ["/usr/bin/ssh", "-F", "/dev/null", "-T", "-p", str(port), "-i", str(identity),
               "-o", "IdentityAgent=none", "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
               "-o", "PreferredAuthentications=publickey",
               "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + host_file,
               "-o", "GlobalKnownHostsFile=/dev/null", "-o", "ClearAllForwardings=yes",
               "-o", "ConnectTimeout=3", "-o", "ConnectionAttempts=1",
               "ark@" + host, "r46h-control"]
    output, errors = bytearray(), bytearray()
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        process.stdin.write(encoded); process.stdin.close()
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, (output, MAX_RESPONSE))
            selector.register(process.stderr, selectors.EVENT_READ, (errors, 16384))
            deadline = time.monotonic() + 20
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ControlError("SSH deadline exceeded; observe before retrying an action")
                for key, _ in selector.select(remaining):
                    data = os.read(key.fd, 65536)
                    if not data:
                        selector.unregister(key.fileobj); continue
                    buffer, limit = key.data; buffer.extend(data)
                    if len(buffer) > limit:
                        raise ControlError("SSH response exceeds limit")
        status = process.wait(timeout=max(0.1, deadline-time.monotonic()))
        if status != 0:
            if output:
                rejected = json.loads(output)
                if isinstance(rejected, dict) and rejected.get("ok") is False:
                    validate_response(rejected, request)
            raise ControlError("SSH/relay failed; verify the paired host and observe before retrying")
        return validate_response(json.loads(output), request)
    finally:
        if process.poll() is None:
            process.kill(); process.wait()
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()


def checked_image(response):
    capture = response.get("capture", {})
    if not isinstance(capture, dict) or not isinstance(response.get("state"), dict):
        raise ControlError("invalid capture or state metadata")
    if capture.get("source") not in {"qt-window", "weston-output"} or (capture.get("source") == "weston-output" and response['state'].get('sharedDisplay') is not True):
        raise ControlError("unexpected capture backend")
    if capture.get("status") != "ok":
        if capture.get("status") not in {"not_requested", "sensitive_entry", "window_unavailable", "size_limit", "capture_failed"} or "png_base64" in capture:
            raise ControlError("invalid unavailable capture")
        return None
    state = response["state"]
    if state.get("sensitiveVisible") is True or (state.get("editing") and not (state.get("testInputVisible") is True and state.get("testInputCapture") is True)):
        raise ControlError("sensitive input capture must be unavailable")
    try:
        data = base64.b64decode(capture.pop("png_base64"), validate=True)
    except (KeyError, ValueError) as error:
        raise ControlError("invalid PNG encoding") from error
    if len(data) > 8 * 1024 * 1024 or len(data) != capture.get("bytes") or hashlib.sha256(data).hexdigest() != capture.get("sha256"):
        raise ControlError("PNG size or SHA-256 mismatch")
    width, height = capture.get("width"), capture.get("height")
    if type(width) is not int or type(height) is not int:
        raise ControlError("invalid PNG dimensions")
    logical_width, logical_height, scale = capture.get("logical_width"), capture.get("logical_height"), capture.get("scale")
    if (type(logical_width) is not int or type(logical_height) is not int or logical_width <= 0 or logical_height <= 0
            or type(scale) not in (int, float) or not math.isfinite(scale) or not 0 < scale <= 8
            or abs(width - logical_width * scale) > 1 or abs(height - logical_height * scale) > 1
            or capture.get("orientation") != 0 or type(capture.get("monotonic_ms")) is not int or capture["monotonic_ms"] < 0):
        raise ControlError("capture geometry or timestamp mismatch")
    png_validator.validate_png_structure(data, profile="qt", width=width, height=height)
    return data


def publish(directory, name, data):
    # Hard-link publication cannot replace an existing result, including a symlink.
    descriptor, temporary = tempfile.mkstemp(prefix=".incoming-", dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data); output.flush(); os.fsync(output.fileno())
        destination = directory / name
        os.link(temporary, destination)
        return destination
    finally:
        os.unlink(temporary)


def output_directory(directory):
    directory = Path(directory).resolve()
    if not directory.is_relative_to(REPO / "mainline/out"):
        raise ControlError("output must stay under the external project's mainline/out")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_directory(directory)
    return directory


def save_result(directory, response):
    directory = output_directory(directory)
    image = checked_image(response)
    stem = response["id"]
    # Names originate here, never from a server-provided export path.
    if str(uuid.UUID(stem)) != stem:
        raise ControlError("invalid result id")
    picture = None
    try:
        if image is not None:
            picture = publish(directory, stem + ".png", image)
            response["capture"]["path"] = str(picture)
        trace = publish(directory, stem + ".json", (json.dumps(response, ensure_ascii=False, indent=2) + "\n").encode())
    except Exception:
        if picture is not None:
            picture.unlink()
        raise
    return trace


DEVICE_METRICS = ("sampleAgeMs", "systemCpu", "MemTotal", "MemAvailable", "SwapTotal", "SwapFree",
                  "temperatureC", "gpuFrequencyHz", "voltageUv", "minimumVoltageUv", "online",
                  "brightnessRaw", "brightnessActual", "brightnessMax", "brightnessPercent",
                  "memoryPressurePercent", "zramSize", "zramOriginal", "zramCompressed", "zramMemory",
                  "scaling_cur_freq", "scaling_min_freq", "scaling_max_freq")
DEVICE_OPTIONAL_METRICS = ("socTemperatureC", "cpuCoolingState", "gpuCoolingState")


def record_values(response):
    state = response.get("state", {})
    if not isinstance(state, dict):
        raise ControlError("invalid diagnostic state")
    device, telemetry = state.get("device"), state.get("telemetry")
    if not isinstance(device, dict) or not isinstance(telemetry, dict):
        raise ControlError("this application does not expose diagnostic readback")
    result = {}
    for source, keys in [(telemetry, ("processCpu", "residentMiB", "uiSubmissions")),
                         (device, DEVICE_METRICS + tuple(k for k in DEVICE_OPTIONAL_METRICS if k in device) if device.get("target") is True else ())]:
        for key in keys:
            value = source.get(key)
            if type(value) not in (int, float) or not math.isfinite(value) or value < -1 or value > 1e15:
                raise ControlError("invalid diagnostic measurement")
            result[key] = value
    for source, key in [(telemetry, "active"), (device, "target"), (device, "controls")]:
        if type(source.get(key)) is not bool:
            raise ControlError("invalid diagnostic status")
        result[key] = source[key]
    if device["target"]:
        for key in ("lowVoltage", "hot"):
            if type(device.get(key)) is not bool:
                raise ControlError("invalid device health status")
            result[key] = device[key]
    game = telemetry.get("game", {})
    if game:
        if not isinstance(game, dict) or type(game.get("active")) is not bool:
            raise ControlError("invalid game frame status")
        result['gameActive'] = game['active']
        for key in ('submissions', 'intervalMedianMs', 'intervalP95Ms', 'intervalMaxMs', 'lastFrameAgeMs', 'outputRefreshHz'):
            value = game.get(key, -1)
            if type(value) not in (int, float) or not math.isfinite(value) or value < -1 or value > 1e15:
                raise ControlError("invalid game frame measurement")
            result['game' + key[0].upper() + key[1:]] = value
    stream = telemetry.get("stream", {})
    if stream:
        if not isinstance(stream, dict) or any(type(stream.get(key)) is not bool for key in ('active', 'available')):
            raise ControlError("invalid stream statistics status")
        result.update(streamActive=stream['active'], streamAvailable=stream['available'])
        for key in ('receivedFps', 'decodedFps', 'renderedFps', 'networkDropPercent', 'pacingDropPercent',
                    'decodeMs', 'queueMs', 'renderCallMs', 'rttMs', 'hostProcessingMs', 'audioNetworkQueueMs'):
            value = stream.get(key, -1)
            if type(value) not in (int, float) or not math.isfinite(value) or value < -1 or value > 1e6:
                raise ControlError("invalid stream statistic")
            result['stream' + key[0].upper() + key[1:]] = value
    return result


def wait_game_frame(send, seconds=25, expected_binary=None):
    """Wait for live game submissions without changing UI state or capturing frames."""
    if not 2 <= seconds <= 60:
        raise ControlError("game-frame wait needs 2–60 seconds")
    started = time.monotonic()
    session = binary = None
    while time.monotonic() - started < seconds:
        response = send({"version": 1, "id": str(uuid.uuid4()), "op": "observe", "screenshot": False})
        if (expected_binary and response.get("binary_sha256") != expected_binary) or (session and
                (response.get("session") != session or response.get("binary_sha256") != binary)):
            raise ControlError("game-frame target changed")
        session, binary = response.get("session"), response.get("binary_sha256")
        state = response.get("state")
        telemetry = state.get("telemetry") if isinstance(state, dict) else None
        game = telemetry.get("game") if isinstance(telemetry, dict) else None
        if (not isinstance(game, dict) or any(type(state.get(key)) is not bool for key in ("externalSession", "sharedReady"))
                or (game and type(game.get("active")) is not bool)):
            raise ControlError("invalid game-frame status")
        if not game:
            time.sleep(min(.3, max(0, seconds - (time.monotonic() - started))))
            continue
        values = [game.get("submissions", -1), game.get("lastFrameAgeMs", -1)]
        if any(type(value) not in (int, float) or not math.isfinite(value) or value < -1 for value in values):
            raise ControlError("invalid game-frame measurement")
        if state["externalSession"] and state["sharedReady"] and game["active"] and values[0] > 0 and values[1] >= 0:
            return response
        time.sleep(min(.3, max(0, seconds - (time.monotonic() - started))))
    raise ControlError("game frame did not become ready before deadline")


def record_samples(send, directory, seconds, interval=2, expected_binary=None):
    """Read-only, bounded sampling. Preserve partial evidence and never retry a lost session."""
    if not 2 <= seconds <= 300 or not 1 <= interval <= min(10, seconds):
        raise ControlError("record needs 2–300 seconds and a 1–10 second interval")
    samples, session, binary, failure = [], None, None, None
    started = time.monotonic()
    try:
        while time.monotonic() - started < seconds:
            request = {"version": 1, "id": str(uuid.uuid4()), "op": "observe", "screenshot": False}
            response = send(request)
            if (expected_binary and response["binary_sha256"] != expected_binary) or (session and
                    (response["session"] != session or response["binary_sha256"] != binary)):
                raise ControlError("recording target changed")
            capture = response.get("capture", {})
            if not isinstance(capture, dict) or capture.get("status") != "not_requested" or "png_base64" in capture:
                raise ControlError("recording must not contain screenshots")
            values = record_values(response)
            session, binary = response["session"], response["binary_sha256"]
            values["elapsedSeconds"] = round(time.monotonic()-started, 3)
            samples.append(values)
            remaining = seconds - (time.monotonic()-started)
            if remaining > 0:
                time.sleep(min(interval, remaining))
    except (ControlError, OSError, ValueError, subprocess.TimeoutExpired, KeyboardInterrupt) as error:
        if not samples:
            raise ControlError("recording ended before its first valid sample") from error
        failure = type(error).__name__
    directory = output_directory(directory)
    stem = "record-" + str(uuid.uuid4())
    result = {"version": 1, "status": "partial" if failure else "complete", "failure": failure,
              "session": session, "binary_sha256": binary, "intervalSeconds": interval,
              "boundary": "diagnostic polling; game submissions/intervals are client buffer commits, not LCD presentation or GPU render time",
              "samples": samples}
    trace = publish(directory, stem + ".json", (json.dumps(result, indent=2) + "\n").encode())
    fields = list(dict.fromkeys(key for sample in samples for key in sample))
    text = io.StringIO(); writer = csv.DictWriter(text, fieldnames=fields); writer.writeheader(); writer.writerows(samples)
    table = publish(directory, stem + ".csv", text.getvalue().encode())
    return {"status": result["status"], "samples": len(samples), "json": str(trace), "csv": str(table)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    transport = parser.add_mutually_exclusive_group(required=True)
    transport.add_argument("--socket", type=Path)
    transport.add_argument("--ssh-host", type=ipaddress.IPv4Address)
    parser.add_argument("--ssh-port", type=int, default=22222)
    parser.add_argument("--identity-file", type=Path)
    parser.add_argument("--known-hosts", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--no-image", action="store_true")
    parser.add_argument("--expect-binary", help="expected application SHA-256")
    commands = parser.add_subparsers(dest="op", required=True)
    commands.add_parser("observe")
    tap = commands.add_parser("tap")
    tap.add_argument("action")
    tap.add_argument("--session", required=True)
    tap.add_argument("--sequence", type=int, required=True)
    text = commands.add_parser("text", help="replace only a public game search or explicitly enabled disposable test field")
    text.add_argument("--value", required=True)
    text.add_argument("--session", required=True)
    text.add_argument("--sequence", type=int, required=True)
    game = commands.add_parser('game-input', help='hold one gamepad sample for 10–1000 ms, then release; requires a current game observation')
    game.add_argument('--session', required=True)
    game.add_argument('--sequence', type=int, required=True)
    game.add_argument('--application', required=True)
    game.add_argument('--input-sequence', type=int, required=True)
    game.add_argument('--duration-ms', type=int, default=100)
    game.add_argument('--button', action='append', choices=['a','b','x','y','l1','r1','l2','r2','select','start','up','down','left','right','l3','r3'], default=[])
    for axis in ['left-x', 'left-y', 'right-x', 'right-y']: game.add_argument('--' + axis, type=float, default=0.)
    recording = commands.add_parser("record", help="bounded read-only metrics, no screenshots or automatic UI changes")
    recording.add_argument("--seconds", type=int, default=30)
    recording.add_argument("--interval", type=int, default=2)
    waiting = commands.add_parser("wait-game-frame", help="bounded read-only wait for fresh game submissions")
    waiting.add_argument("--seconds", type=int, default=25)
    args = parser.parse_args()
    if args.ssh_host and not (args.identity_file and args.known_hosts and args.expect_binary):
        parser.error("SSH requires an explicit private identity, serial-verified known-hosts and expected binary hash")
    request = {"version": 1, "id": str(uuid.uuid4()), "op": args.op, "screenshot": not args.no_image}
    if args.op in {"tap", "text", "game-input"}:
        if not args.expect_binary:
            parser.error("mutating operations require --expect-binary from the preceding observation")
        request.update(session=args.session, sequence=args.sequence, binary_sha256=args.expect_binary)
        if args.op == 'game-input':
            axes = [args.left_x, args.left_y, args.right_x, args.right_y]
            if not 10 <= args.duration_ms <= 1000 or any(not math.isfinite(value) or not -1 <= value <= 1 for value in axes):
                parser.error('game input requires 10–1000 ms and axes between -1 and 1')
            request.update(application=args.application, input_sequence=args.input_sequence, duration_ms=args.duration_ms,
                           buttons=args.button, axes=axes)
        else:
            request["action" if args.op == "tap" else "text"] = args.action if args.op == "tap" else args.value
    try:
        args.output_dir = output_directory(args.output_dir)
        def send(request):
            return (ssh_exchange(args.ssh_host, args.ssh_port, args.identity_file.absolute(), args.known_hosts.absolute(), request)
                    if args.ssh_host else exchange(args.socket, request))
        if args.op == "record":
            result = record_samples(send, args.output_dir, args.seconds, args.interval, args.expect_binary)
            print(json.dumps(result)); return 0 if result["status"] == "complete" else 1
        if args.op == "wait-game-frame":
            response = wait_game_frame(send, args.seconds, args.expect_binary)
            trace = save_result(args.output_dir, response)
            print(json.dumps({"trace": str(trace), **response}, ensure_ascii=False)); return 0
        response = send(request)
        if args.expect_binary and response.get("binary_sha256") != args.expect_binary:
            raise ControlError("application binary mismatch")
        trace = save_result(args.output_dir, response)
        print(json.dumps({"trace": str(trace), **response}, ensure_ascii=False))
        if args.op == 'game-input' and response['input_status'] != 'completed': return 1
    except (ControlError, png_validator.FetchError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print("CONTROL_ERROR " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
