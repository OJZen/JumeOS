#!/usr/bin/env python3
"""One real application-list/launch/return flow; no repetition or device access."""
import argparse
import importlib.util
import json
import os
import stat
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("control", REPO / "mainline/gaming-shell/control.py")
control = importlib.util.module_from_spec(spec); spec.loader.exec_module(control)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--ipc-root", type=Path)
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args(); cache = REPO / "mainline/out/.cache"
    with tempfile.TemporaryDirectory(prefix="apps.", dir=cache) as temporary, \
            tempfile.TemporaryDirectory(prefix="apps-ipc.", dir=args.ipc_root or cache) as sockets:
        root = Path(temporary); state = root / "state"; ipc = Path(sockets) / "a"
        helper = root / "foreground app.sh"; record = root / "arguments.txt"
        helper.write_text('#!/bin/sh\nout=$1; shift; printf "%s\\n" "$@" > "$out"\nsleep 1\n')
        helper.chmod(0o700)
        entries = [{"id":f"app-{i}", "title":f"应用 {i}", "description":"前台应用", "program":str(helper),
                    "arguments":[str(record), f"app-{i}", "literal $(not-a-command)"]} for i in range(8)]
        entries.append({"id":"failure", "title":"启动失败恢复", "program":"/bin/sh", "arguments":["-c", "exit 7"]})
        config = root / "applications.json"; config.write_text(json.dumps({"version":1,"applications":entries}))
        env = {**os.environ, "TMPDIR":str(root), "SDL_NO_SIGNAL_HANDLERS":"1", "PYTHONDONTWRITEBYTECODE":"1"}
        runtime_log = root / "runtime.log"
        with runtime_log.open("wb") as log:
            process = subprocess.Popen([str(args.binary.resolve()), "--state-dir", str(state), "--applications", str(config),
                                        "--control-dir", str(ipc), "--quit-after", "30"], stdout=log, stderr=subprocess.STDOUT, env=env)
        try:
            def wait_endpoint():
                deadline = time.monotonic() + 8
                while True:
                    try:
                        metadata = (ipc / "control.sock").lstat()
                        if stat.S_ISSOCK(metadata.st_mode) and stat.S_IMODE(metadata.st_mode) == 0o600 and metadata.st_uid == os.getuid(): return
                    except FileNotFoundError: pass
                    assert process.poll() is None, runtime_log.read_text()
                    assert time.monotonic() < deadline
                    time.sleep(0.02)
            wait_endpoint()
            def request(op="observe", **values):
                return {"version":1,"id":str(uuid.uuid4()),"op":op,"screenshot":False, **values}
            latest = control.exchange(ipc / "control.sock", request())
            def tap(action):
                nonlocal latest
                latest = control.exchange(ipc / "control.sock", request("tap", action=action, session=latest["session"],
                    binary_sha256=latest["binary_sha256"], sequence=latest["sequence"]))
                return latest["state"]
            def observe(image=False):
                nonlocal latest
                latest = control.exchange(ipc / "control.sock", request(screenshot=image)); return latest
            tap("nextTab"); tap("down"); tap("down"); assert tap("right")["selected"] == 7
            tap("favorite")
            assert latest["state"]["selectedFavorite"] and latest["state"]["selectedApplication"] == "app-7"
            saved = json.loads((state / "preview.json").read_text())
            assert saved["version"] == 4 and saved["screenOffSeconds"] == 300 and saved["applicationFavorites"] == ["app-7"]
            if args.evidence: control.save_result(args.evidence, observe(True))
            assert tap("accept")["externalSession"]
            # The parent ignores controls while another application owns the session.
            assert tap("nextTab")["page"] == 1
            hidden = observe(True); assert hidden["state"]["externalSession"] and hidden["capture"]["status"] == "window_unavailable"
            deadline = time.monotonic() + 4
            while observe()["state"]["externalSession"]:
                assert time.monotonic() < deadline; time.sleep(0.1)
            assert latest["state"]["selected"] == 7 and latest["state"]["applicationExitCode"] == 0
            assert record.read_text() == "app-7\nliteral $(not-a-command)\n"
            frame = observe(True); assert frame["capture"]["status"] == "ok"
            if args.evidence: control.save_result(args.evidence, frame)
            tap("right"); assert latest["state"]["selected"] == 8
            tap("accept"); deadline = time.monotonic() + 4
            while observe()["state"]["externalSession"]:
                assert time.monotonic() < deadline; time.sleep(0.1)
            assert latest["state"]["applicationError"] and latest["state"]["applicationExitCode"] == 7
            assert observe(True)["capture"]["status"] == "ok"
            process.terminate(); process.wait(timeout=5)
            config.write_text(json.dumps({"version":1,"applications":list(reversed(entries))}))
            ipc = Path(sockets) / "b"
            runtime_log = root / "reordered.log"
            with runtime_log.open("wb") as log:
                process = subprocess.Popen([str(args.binary.resolve()), "--state-dir", str(state), "--applications", str(config),
                    "--control-dir", str(ipc), "--quit-after", "15"], stdout=log, stderr=subprocess.STDOUT, env=env)
            wait_endpoint()
            observe(); assert tap("right")["selectedApplication"] == "app-7"
            assert latest["state"]["selectedFavorite"]
            result = {"status":"APPLICATION_FLOW_PASS", "binary_sha256":latest["binary_sha256"],
                      "checks":["nine-entry scrolling", "favorite after reorder/restart", "literal argv", "launch and return", "parent input isolation", "failure recovery"],
                      "boundary":"owned host foreground process; no R46H display or full process-tree proof"}
            if args.evidence:
                (args.evidence / "application-result.json").write_text(json.dumps(result, indent=2) + "\n")
            print(json.dumps(result))
        finally:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
