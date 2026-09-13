#!/usr/bin/env python3
"""Actual Qt/IPC desktop restart around a fake stream; no hardware, SSH or real video."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
import uuid

repo = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("control", repo / "mainline/gaming-shell/control.py")
control = importlib.util.module_from_spec(spec); spec.loader.exec_module(control)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--binary", type=Path, required=True)
parser.add_argument("--ipc-root", type=Path)
parser.add_argument("--evidence", type=Path, required=True)
args = parser.parse_args()
binary = args.binary.resolve(); assert binary.is_file()
evidence = control.output_directory(args.evidence)
with tempfile.TemporaryDirectory(prefix="handoff-", dir=repo / "mainline/out/.cache") as temporary, \
        tempfile.TemporaryDirectory(prefix="hof.", dir=args.ipc_root or repo / "mainline/out/.cache") as ipc:
    root = Path(temporary); endpoint = Path(ipc) / "ui"; endpoint.mkdir(mode=0o700)
    path = endpoint / "control.sock"
    (root / "usr/bin").mkdir(parents=True)
    (root / "state/streaming").mkdir(parents=True, mode=0o700)
    host_id = str(uuid.uuid4())
    hosts = {"version": 1, "selected": host_id, "hosts": [{"id": host_id, "name": "Fixture",
             "address": "127.0.0.1", "application": "Game; literal", "preset": 0, "overlay": True, "paired": False}]}
    state = root / "state/streaming/hosts.json"; state.write_text(json.dumps(hosts)); state.chmod(0o600)
    client = root / "usr/bin/moonlight-qt"
    client.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$FIXTURE/arguments"\nexit "$(cat "$FIXTURE/exit")"\n')
    client.chmod(0o700); digest = hashlib.sha256(client.read_bytes()).hexdigest()
    shutil.copyfile(repo / "mainline/gaming-shell/desktop-session.sh", root / "desktop-session.sh")
    wrapper = root / "shell-client.sh"
    wrapper.write_text('#!/bin/sh\nexec ' + shlex.quote(str(binary)) + ' --state-dir ' + shlex.quote(str(root / "state")) + ' "$@"\n')
    wrapper.chmod(0o700)
    environment = {**os.environ, "FIXTURE": str(root), "TMPDIR": str(root), "PYTHONDONTWRITEBYTECODE": "1"}
    log = (evidence / "handoff.log").open("w")
    process = subprocess.Popen(["sh", str(root / "desktop-session.sh"), digest, "--remote", str(endpoint)],
                               env=environment, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)

    def observe():
        return control.exchange(path, {"version": 1, "id": str(uuid.uuid4()), "op": "observe", "screenshot": False})

    def wait_for_session(previous=None):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            assert process.poll() is None, "supervisor exited"
            try:
                result = observe()
                if result["session"] != previous:
                    return result
            except (control.ControlError, OSError, ValueError):
                pass
            time.sleep(.05)
        raise AssertionError("new desktop session did not appear")

    def tap(current, action):
        return control.exchange(path, {"version": 1, "id": str(uuid.uuid4()), "op": "tap", "screenshot": False,
            "session": current["session"], "sequence": current["sequence"], "binary_sha256": current["binary_sha256"], "action": action})

    try:
        current = wait_for_session()
        sessions = [current["session"]]
        for exit_code in (0, 7):
            (root / "exit").write_text(str(exit_code))
            assert current["state"]["streamingOpen"]
            current = tap(current, "accept")  # Details select Start.
            old = current
            try:
                tap(current, "accept")  # Exit 75 may close IPC before its reply; never repeat this action.
            except (control.ControlError, OSError, ValueError):
                pass
            current = wait_for_session(old["session"]); sessions.append(current["session"])
            assert current["sequence"] == 0 and current["binary_sha256"] == old["binary_sha256"]
            result = json.loads((root / "state/streaming/result.json").read_text())
            assert result["exit"] == exit_code
            assert (root / "arguments").read_text().splitlines()[:3] == ["stream", "127.0.0.1", "Game; literal"]
            assert not (root / "state/streaming/request.json").exists()
            try:
                tap(old, "down")
            except control.ControlError:
                pass
            else:
                raise AssertionError("stale desktop action accepted")
            assert observe()["sequence"] == 0
        result = {"status": "SHELL_HANDOFF_PASS", "binary_sha256": current["binary_sha256"], "sessions": len(set(sessions)),
                  "checks": ["normal and failed worker return", "new IPC generation", "stale action refused", "literal argv", "request consumed once"],
                  "boundary": "actual host Qt and supervisor, fake stream; no device DRM, real Moonlight, SSH or audio proof"}
        (evidence / "handoff-result.json").write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result))
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait()
        log.close()
