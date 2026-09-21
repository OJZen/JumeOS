#!/usr/bin/env python3
"""Exercise the opt-in endpoint of the actual shell process; no device or SSH."""
import argparse
import copy
import importlib.util
import json
import math
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("control", REPO / "mainline/gaming-shell/control.py")
control = importlib.util.module_from_spec(spec); spec.loader.exec_module(control)


def request(op="observe", **fields):
    return {"version": 1, "id": str(uuid.uuid4()), "op": op, "screenshot": False, **fields}


def raw(path, data):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(5); client.connect(str(path)); client.sendall(data)
        result = bytearray()
        while chunk := client.recv(65536):
            result.extend(chunk)
            assert len(result) <= control.MAX_RESPONSE
        return json.loads(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--cycles", type=int, default=3)
    parser.add_argument("--action-delay-ms", type=int, default=0, help="paced repetition; 100 matches held-controller repeat")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--ipc-root", type=Path, help="local Unix-socket filesystem; containers use /run")
    args = parser.parse_args()
    binary = args.binary.resolve(); assert binary.is_file()
    assert 1 <= args.cycles <= 2000
    assert 0 <= args.action_delay_ms <= 1000 and args.cycles * 7 * args.action_delay_ms <= 900000
    cache = REPO / "mainline/out/.cache"; cache.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "SDL_NO_SIGNAL_HANDLERS": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    trace = []
    with tempfile.TemporaryDirectory(prefix="ctl.", dir=cache) as temporary, \
            tempfile.TemporaryDirectory(prefix="ctl-ipc.", dir=args.ipc_root or cache) as ipc_temporary:
        root = Path(temporary)
        ipc_root = Path(ipc_temporary)
        environment["TMPDIR"] = str(root)
        processes = []
        peer_uid_verified = False
        def start(name, state=None, enabled=True, seconds=120, extra=()):
            ipc = ipc_root / name
            argv = [str(binary), "--state-dir", str(state or root / (name + "-state")), "--quit-after", str(seconds)]
            if enabled: argv.extend(["--control-dir", str(ipc)])
            with (root / (name + ".log")).open("wb") as log:
                process = subprocess.Popen([*argv, *extra], stdout=log, stderr=subprocess.STDOUT, env=environment)
            processes.append(process)
            if enabled:
                end = time.monotonic() + 10
                while True:
                    try:
                        metadata = (ipc / "control.sock").lstat()
                        if stat.S_ISSOCK(metadata.st_mode) and stat.S_IMODE(metadata.st_mode) == 0o600 and metadata.st_uid == os.getuid(): break
                    except FileNotFoundError: pass
                    assert process.poll() is None, (name, (root / (name + ".log")).read_text())
                    assert time.monotonic() < end, "endpoint startup timeout"
                    time.sleep(0.02)
            return process, ipc / "control.sock"
        try:
            process, path = start("live", seconds=60 + math.ceil(args.cycles * 7 * (args.action_delay_ms / 1000 + 0.02)))
            latest = control.exchange(path, request(screenshot=True))
            assert latest["state"]["page"] == 0
            assert latest["state"]["device"] == {"target": False, "controls": False}
            assert latest["state"]["telemetry"]["active"] is False
            assert control.checked_image(copy.deepcopy(latest))
            # Exercise the actual headless stdio relay used by the forced SSH command.
            relay_request = request(screenshot=True)
            relay = subprocess.run([str(binary), "--control-call", "--control-dir", str(path.parent)],
                                   input=json.dumps(relay_request).encode()+b"\n", capture_output=True, timeout=8,
                                   env={**environment, "SSH_ORIGINAL_COMMAND": "r46h-control"})
            assert relay.returncode == 0, relay.stderr
            relayed = control.validate_response(json.loads(relay.stdout), relay_request)
            assert control.checked_image(copy.deepcopy(relayed))
            forbidden = root / 'relay-must-not-create'
            rejected = subprocess.run([str(binary), "--control-call", "--control-dir", str(path.parent)],
                                      input=json.dumps(request()).encode()+b"\n", capture_output=True, timeout=4,
                                      env={**environment, "SSH_ORIGINAL_COMMAND": "touch " + str(forbidden)})
            assert rejected.returncode == 2 and not forbidden.exists()
            rejected = subprocess.run([str(binary), "--control-call", "--control-dir", str(path.parent)],
                                      input=b"x"*4097+b"\n", capture_output=True, timeout=4,
                                      env={**environment, "SSH_ORIGINAL_COMMAND": "r46h-control"})
            assert rejected.returncode == 1 and json.loads(rejected.stdout)["error"] == "invalid_request"
            initial = latest["capture"]["sha256"]
            if args.evidence:
                control.save_result(args.evidence, copy.deepcopy(latest))
            def tap(action, screenshot=False):
                nonlocal latest
                sent = request("tap", action=action, session=latest["session"], sequence=latest["sequence"],
                               binary_sha256=latest["binary_sha256"], screenshot=screenshot)
                latest = control.exchange(path, sent)
                result = copy.deepcopy(latest)
                if args.evidence and screenshot: control.save_result(args.evidence, result)
                else: control.checked_image(result)
                trace.append({"request": sent, "result": result})
                return latest["state"]
            def wait_state(name, value=True):
                nonlocal latest
                deadline = time.monotonic() + 5
                while True:
                    latest = control.exchange(path, request())
                    if latest["state"][name] == value: return latest["state"]
                    assert time.monotonic() < deadline, f"timeout waiting for {name}={value}"
                    time.sleep(.02)
            assert tap("right", True)["selected"] == 1
            assert latest["capture"]["sha256"] != initial
            prior = copy.deepcopy(latest)
            for bad, reason in [({"session": "expired"}, "stale_session"), ({"sequence": -1}, "stale_sequence"),
                                ({"binary_sha256": "0" * 64}, "wrong_binary"), ({"action": "shell"}, "unsupported_action")]:
                sent = request("tap", action="right", session=latest["session"], sequence=latest["sequence"], binary_sha256=latest["binary_sha256"])
                sent.update(bad)
                result = raw(path, json.dumps(sent).encode() + b"\n")
                assert result["ok"] is False and result["error"] == reason
            observed = control.exchange(path, request())
            assert observed["sequence"] == prior["sequence"] and observed["state"]["selected"] == 1
            assert raw(path, b"{bad}\n")["error"] == "invalid_request"
            try:
                assert raw(path, b"x" * 4097 + b"\n")["error"] == "request_too_large"
            except ConnectionResetError:
                pass  # Linux can reset an oversized peer with unread bytes; no action is accepted.
            assert raw(path, json.dumps(request(op="hold")).encode() + b"\n")["error"] == "unsupported_operation"
            if os.geteuid() == 0 and all(p.stat().st_mode & 1 for p in ipc_root.parents):
                # In the isolated Linux builder, bypass file modes to exercise peer-UID rejection itself.
                ipc_root.chmod(0o755); path.parent.chmod(0o755); path.chmod(0o666)
                try:
                    peer = subprocess.run(["runuser", "-u", "nobody", "--", sys.executable, "-c",
                        "import socket,sys; s=socket.socket(socket.AF_UNIX); s.settimeout(4); s.connect(sys.argv[1]);\n"
                        "try:\n s.sendall(b'{}\\n'); data=s.recv(1)\nexcept (ConnectionResetError,BrokenPipeError):\n data=b''\n"
                        "sys.exit(1 if data else 0)", str(path)], timeout=6, capture_output=True)
                    assert peer.returncode == 0, peer.stderr
                    peer_uid_verified = True
                finally:
                    path.chmod(0o600); path.parent.chmod(0o700); ipc_root.chmod(0o700)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as dropped:
                dropped.connect(str(path)); dropped.sendall(b"{")
            time.sleep(0.03)
            assert control.exchange(path, request())["sequence"] == prior["sequence"]
            assert tap("accept")["toolRoute"] == "neo"
            assert tap("quick")["quickOpen"]
            prior_row = latest["state"]["toolRow"]
            assert tap("right")["toolRow"] == prior_row
            tap("back"); assert not tap("back")["toolOpen"]
            tap("nextTab"); assert tap("nextTab")["settingsSidebar"]
            assert not tap("right")["settingsSidebar"]
            wait_state("settingsDetailReady")
            assert tap("left")["settingsSidebar"]
            for _ in range(8): tap("down")
            tap("right"); wait_state("settingsDetailReady"); assert tap("accept", True)["choicesOpen"]
            assert tap("down")["fontPercent"] == 100
            assert tap("nextTab")["page"] == 2  # A choice owns input until confirm/cancel.
            assert not tap("back")["choicesOpen"]
            tap("accept"); tap("down"); assert tap("accept", True)["fontPercent"] == 110
            tap("down"); assert tap("accept", True)["editing"]
            assert latest["capture"]["status"] == "sensitive_entry" and "png_base64" not in latest["capture"]
            assert set(latest["state"]).isdisjoint({"text", "input", "clipboard", "notice", "error"})
            assert not tap("back", True)["editing"]
            assert control.checked_image(copy.deepcopy(latest))
            tap("left")
            for _ in range(6): tap("up")
            assert tap("right")["testingController"]
            assert tap("left")["testingController"]
            assert not tap("quick")["testingController"]
            tap("home"); tap("quick")
            for _ in range(3): tap("down")
            assert tap("accept")["monitor"]
            recorded = subprocess.run([sys.executable, "-B", str(REPO / "mainline/gaming-shell/control.py"),
                "--socket", str(path), "--output-dir", str(root / "metrics"), "--expect-binary", latest["binary_sha256"],
                "record", "--seconds", "2", "--interval", "1"], capture_output=True, text=True, env=environment, timeout=8)
            assert recorded.returncode == 0, recorded.stderr
            recording = json.loads(recorded.stdout)
            assert recording["status"] == "complete" and recording["samples"] >= 1
            values = json.loads(Path(recording["json"]).read_text())["samples"]
            assert all(v["active"] and not v["target"] for v in values)
            assert not tap("accept")["monitor"]
            tap("back")
            # Actual CLI verifies and publishes a capture without overwriting another result.
            before_invalid_output = control.exchange(path, request())
            bad_output = subprocess.run([sys.executable, '-B', str(REPO / 'mainline/gaming-shell/control.py'), '--socket', str(path),
                '--output-dir', str(REPO), '--expect-binary', before_invalid_output['binary_sha256'], 'tap', 'right',
                '--session', before_invalid_output['session'], '--sequence', str(before_invalid_output['sequence'])],
                capture_output=True, text=True, env=environment, timeout=8)
            assert bad_output.returncode == 1 and 'output must stay' in bad_output.stderr
            assert control.exchange(path, request())['sequence'] == before_invalid_output['sequence'], 'Invalid output path dispatched a mutation'
            output = root / "exports"
            cli = subprocess.run([sys.executable, "-B", str(REPO / "mainline/gaming-shell/control.py"), "--socket", str(path),
                                  "--output-dir", str(output), "observe"], capture_output=True, text=True, env=environment, timeout=8)
            assert cli.returncode == 0, cli.stderr
            published = json.loads(cli.stdout)
            assert Path(published["capture"]["path"]).is_file() and Path(published["trace"]).is_file()
            preview, preview_socket = start("ime", seconds=30, extra=("--scene", "input", "--test-input-capture"))
            preview_state = control.exchange(preview_socket, request(screenshot=True))
            assert preview_state['state']['testInputVisible'] and control.checked_image(copy.deepcopy(preview_state))
            for action in ('back','home','accept','favorite'):
                preview_state = control.exchange(preview_socket, request('tap',action=action,
                    session=preview_state['session'], sequence=preview_state['sequence'], binary_sha256=preview_state['binary_sha256'], screenshot=True))
            assert preview_state['state']['editing'] and preview_state['state']['sensitiveVisible']
            assert not preview_state['state']['testInputVisible'] and preview_state['capture']['status']=='sensitive_entry'
            assert control.checked_image(copy.deepcopy(preview_state)) is None
            preview.terminate(); preview.wait(timeout=5)
            corrupt = copy.deepcopy(latest); corrupt["capture"] = {"source":"qt-window", "status":"ok", "png_base64":"AA==", "bytes":1, "sha256":"0"*64}
            try: control.checked_image(corrupt); raise AssertionError("accepted bad hash")
            except control.ControlError: pass
            mislabeled = copy.deepcopy(latest)
            mislabeled['capture'] = {'source': 'weston-output', 'status': 'not_requested'}
            mislabeled['state']['sharedDisplay'] = False
            try: control.checked_image(mislabeled); raise AssertionError('accepted composed capture outside shared display')
            except control.ControlError: pass
            mislabeled['state']['sharedDisplay'] = True
            assert control.checked_image(mislabeled) is None
            # A live endpoint cannot be replaced, and normal startup creates none.
            duplicate = subprocess.run([str(binary), "--state-dir", str(root / "duplicate-state"), "--control-dir", str(path.parent)],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment, timeout=8)
            assert duplicate.returncode == 2 and path.exists()
            for directory, extras in [(root / "unsafe", []), (root / "profile", ["--profile-ui"])]:
                if not extras: directory.mkdir(mode=0o755)
                refused = subprocess.run([str(binary), "--state-dir", str(root / "refusal-state"), "--control-dir", str(directory), *extras],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=environment, timeout=8)
                assert refused.returncode == 2 and not (directory / "control.sock").exists()
            normal, unused = start("disabled", enabled=False, seconds=1)
            assert normal.wait(timeout=8) == 0 and not unused.parent.exists()
            clean, clean_path = start("clean", seconds=2)
            assert clean.wait(timeout=8) == 0 and not clean_path.exists()
            # Failed save must still preserve the actual application's current editor.
            blocked = root / "blocked"; blocked.write_text("preserve")
            failed, failed_path = start("failed", state=blocked)
            state = control.exchange(failed_path, request())
            for action in ["nextTab", "nextTab", "right"]:
                state = control.exchange(failed_path, request("tap", action=action, session=state["session"], sequence=state["sequence"], binary_sha256=state["binary_sha256"]))
            deadline = time.monotonic() + 5
            while not state["state"]["settingsDetailReady"]:
                assert time.monotonic() < deadline, "settings detail timeout"
                state = control.exchange(failed_path, request())
                time.sleep(.02)
            for action in ["accept", "up", "left"]:
                state = control.exchange(failed_path, request("tap", action=action, session=state["session"], sequence=state["sequence"], binary_sha256=state["binary_sha256"]))
            assert state["state"]["save_error"] and state["state"]["settingsAdjusting"] and not state["state"]["settingsSidebar"]
            assert blocked.read_text() == "preserve"
            failed.terminate(); failed.wait(timeout=5)
            # Short repeat sample: report RSS, without claiming a device memory budget.
            def rss(): return int(subprocess.check_output(["ps", "-o", "rss=", "-p", str(process.pid)], text=True).strip())
            rss_start = rss()
            repeat_start = time.monotonic()
            samples = [{"cycle":0, "rss_kib":rss_start}]
            for cycle in range(args.cycles):
                for action in ["home", "nextTab", "nextTab", "right", "left", "quick", "back"]:
                    tap(action)
                    if args.action_delay_ms: time.sleep(args.action_delay_ms / 1000)
                if (cycle + 1) % 100 == 0: samples.append({"cycle":cycle + 1, "rss_kib":rss()})
            time.sleep(1)
            summary = {"status":"SHELL_CONTROL_PASS", "cycles":args.cycles, "actions":len(trace), "rss_start_kib":rss_start,
                       "action_delay_ms":args.action_delay_ms,
                       "rss_end_kib":rss(), "repeat_elapsed_seconds":round(time.monotonic()-repeat_start,2), "rss_samples":samples,
                       "peer_uid_rejection": "passed" if peer_uid_verified else "not_run_without_isolated_root",
                       "binary_sha256":latest["binary_sha256"], "boundary":"host Qt application actions; no kernel input or hardware proof"}
            if args.evidence:
                args.evidence.mkdir(mode=0o700, parents=True, exist_ok=True)
                (args.evidence / "control-trace.jsonl").write_text("".join(json.dumps(line, ensure_ascii=False) + "\n" for line in trace))
                frame = control.exchange(path, request(screenshot=True)); control.save_result(args.evidence, frame)
                (args.evidence / "control-result.json").write_text(json.dumps(summary, indent=2) + "\n")
            print(json.dumps(summary))
        finally:
            for process in processes:
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
