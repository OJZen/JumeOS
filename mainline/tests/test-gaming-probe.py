#!/usr/bin/env python3
"""Execute the actual Bash guards/recovery with fake processes and service calls."""
from pathlib import Path
import os
import re
import subprocess
import tempfile
import shutil

repo = Path(__file__).resolve().parents[2]


def bash(code, **variables):
    return subprocess.run(["/bin/bash", "-c", "set -Eeuo pipefail\n" + code],
                          env={**os.environ, **variables}, text=True, capture_output=True, timeout=5)


for path in ("mainline/gaming-shell/probe-r46h.sh", "mainline/gaming-moonlight/run-stream.sh"):
    source = (repo / path).read_text()
    guard = re.search(r"process_status=0\n.*?exit 1; }\n", source, re.S).group()
    fake = '''pgrep() {
        [[ $1 == -u && $2 == 1000 && $3 == -f ]] || return 2
        [[ $PROCESS_ERROR == 0 ]] || return 2
        [[ $ARGV =~ $4 ]]
    }
'''
    for argv, expected in (("/usr/bin/es-de", 0), ("/usr/bin/retroarch -L ppsspp_libretro.so game.PBP", 1),
                           ("/run/r46h-moonlight-test/opt/r46h-moonlight-test/bin/moonlight stream host", 1),
                           ("/run/r46h-moonlight-qt-test/usr/bin/moonlight-qt stream host", 1),
                           ("/run/r46h-shell-probe/usr/bin/r46h-shell --fullscreen", 1)):
        result = bash(fake + guard + 'echo REACHED_START', ARGV=argv, PROCESS_ERROR="0")
        assert result.returncode == expected, (path, argv, result)
        assert ("REACHED_START" in result.stdout) == (expected == 0)
    assert bash(fake + guard, ARGV="/usr/bin/es-de", PROCESS_ERROR="1").returncode == 1

    restore = source[source.index("restore() {"):source.index("trap restore EXIT")]
    fake = '''systemctl() {
        if [[ $1 == show ]]; then printf '%s\\n' "$LOAD_STATE"; return; fi
        printf 'CALL %s\n' "$*"
        case "$1" in
          stop) return "$STOP_STATUS" ;;
          start) return "$START_STATUS" ;;
          is-active) return "$ACTIVE_STATUS" ;;
        esac
    }
    amixer() { echo MIXER_RESTORE; }
    unit=test.service
    mode=--run
    saved_mux=0
'''
    for stop, load, start, active, session, expected, resumes in (
        (0, "loaded", 0, 0, 0, 0, True), (0, "loaded", 0, 0, 124, 124, True),
        (0, "loaded", 0, 0, 143, 143, True), (1, "loaded", 0, 0, 0, 1, False),
        (1, "not-found", 0, 0, 0, 0, True), (0, "loaded", 1, 0, 0, 1, True),
        (0, "loaded", 0, 3, 0, 1, True)):
        result = bash(fake + restore + '\ntrap restore EXIT\nexit "$SESSION_STATUS"',
                      STOP_STATUS=str(stop), LOAD_STATE=load, START_STATUS=str(start),
                      ACTIVE_STATUS=str(active), SESSION_STATUS=str(session))
        assert result.returncode == expected, (path, result)
        assert ("CALL start r46h-gaming-frontend.service" in result.stdout) == resumes, result
    assert 'systemd-run --quiet --wait --pipe --collect --service-type=exec' in source
    assert '-p TimeoutStopSec=10 -p KillMode=control-group' in source
    assert '/usr/bin/setsid --wait /usr/bin/openvt' in source
    assert "trap 'exit 129' HUP" in source

source = (repo / "mainline/gaming-shell/probe-r46h.sh").read_text()
guard = source[source.index("if [[ $closure"):source.index("printf 'SHELL_PREFLIGHT")]
for closure, expected in (("libQt6Quick.so.6 => /bundle/libQt6Quick.so.6", 0), ("libQt6Quick.so.6 => not found", 1)):
    assert bash(guard, closure=closure, mode="--check").returncode == expected
options = source[source.index("unit=r46h-shell"):source.index("restore() {")]
for mode, seconds, deadline, extra in (("--run", 290, 300, []), ("--profile", 110, 120, ["--profile-ui"])):
    result = bash(options + '\n printf "%s\\n" "${args[@]}" "$deadline"', mode=mode, scope="/owned")
    assert result.returncode == 0
    assert result.stdout.splitlines() == ["--fullscreen", "--quit-after", str(seconds), *extra, str(deadline)]
for setting in ("", "0", "1"):
    result = bash(options + '\n declare -p render_env', mode="--profile", scope="/owned", QSG_RENDER_TIMING=setting)
    assert result.returncode == 0
    assert ('"QSG_RENDER_TIMING=1"' in result.stdout) == (setting == "1")
    result = bash(options + '\n declare -p render_env', mode="--attended", scope="/owned", client_hash="a"*64, DRM_FORCE_EGL=setting)
    assert result.returncode == 0 and ('DRM_FORCE_EGL=1' in result.stdout) == (setting == "1")
result = bash(options + '\n printf "%s\\n" "$entry" "${args[@]}" "$deadline"', mode="--streaming", scope="/owned", client_hash="a"*64)
assert result.returncode == 0 and result.stdout.splitlines() == ["/owned/desktop-session.sh", "a"*64, "900"]
result = bash(options + '\n printf "%s\\n" "$entry" "${args[@]}" "$deadline"', mode="--attended", scope="/owned", client_hash="a"*64)
assert result.returncode == 0 and result.stdout.splitlines() == ["/owned/desktop-session.sh", "a"*64, "--attended", "5400"]
result = bash(options + '\n printf "%s\\n" "$entry" "${args[@]}" "$deadline"', mode="--attended-ports", scope="/owned")
assert result.returncode == 0 and result.stdout.splitlines() == ["/owned/desktop-session.sh", "ports", "--attended", "5400"]
result = bash(options + '\n printf "%s\\n" "$entry" "${args[@]}" "$deadline"', mode="--remote", scope="/owned", listen_ip="192.0.2.2", peer_ip="192.0.2.1")
assert result.returncode == 0 and result.stdout.splitlines() == ["/owned/remote-session.sh", "192.0.2.2", "192.0.2.1", "1860"]
result = bash(options + '\n printf "%s\\n" "$entry" "${args[@]}" "$deadline" "${render_env[@]}"', mode="--remote-streaming", scope="/owned", listen_ip="192.0.2.2", peer_ip="192.0.2.1", client_hash="a"*64)
assert result.returncode == 0 and result.stdout.splitlines() == ["/owned/remote-session.sh", "192.0.2.2", "192.0.2.1", "a"*64, "1860", "R46H_DEVICE_CONTROLS=0"]
for mode in ("--device", "--remote-device"):
    result = bash(options + '\n declare -p render_env unit_properties', mode=mode, scope="/owned", listen_ip="192.0.2.2", peer_ip="192.0.2.1")
    assert result.returncode == 0 and 'R46H_DEVICE_CONTROLS=1' in result.stdout
    assert 'ExecStartPre=/bin/bash /owned/device-lease.sh --acquire' in result.stdout
    assert 'ExecStopPost=/bin/bash /owned/device-lease.sh --restore' in result.stdout

with tempfile.TemporaryDirectory(prefix="shell-wrapper-", dir=repo / "mainline/out/.cache") as temporary:
    root = Path(temporary)
    binary = root / "usr/bin/r46h-shell"; binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\necho RUNTIME_DIAGNOSTIC >&2\nexit 7\n"); binary.chmod(0o755)
    wrapper = root / "shell-client.sh"
    shutil.copyfile(repo / "mainline/gaming-shell/shell-client.sh", wrapper)
    result = subprocess.run(["sh", str(wrapper)], env={**os.environ, "R46H_SHELL_LOG": "1"}, capture_output=True)
    assert result.returncode == 7 and not result.stdout and not result.stderr
    assert (root / "state/runtime.log").read_text() == "RUNTIME_DIAGNOSTIC\n"
    persistent = root / "persistent data"
    args_file = root / "args"
    binary.write_text('#!/bin/sh\nprintf "%s\\n" "$@" "$XDG_CONFIG_HOME" > "$R46H_ARGS_FILE"\n')
    env = {**os.environ, "R46H_SHELL_STATE_DIR": str(persistent), "R46H_ARGS_FILE": str(args_file)}
    result = subprocess.run(["sh", str(wrapper), "--native-worker"], env=env, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert args_file.read_text().splitlines() == ["--state-dir", str(persistent), "--native-worker", str(persistent / "config")]
    args_file.unlink()
    result = subprocess.run(["sh", str(wrapper), "--check-state"], env=env, capture_output=True)
    assert result.returncode == 0 and not args_file.exists()
    marker = persistent / "keep"; marker.write_text("saved progress")
    result = subprocess.run(["sh", str(wrapper), "--stream-worker"], env=env, capture_output=True)
    assert result.returncode == 0 and marker.read_text() == "saved progress"
    linked = root / "linked"; linked.symlink_to(persistent, target_is_directory=True)
    args_file.unlink()
    result = subprocess.run(["sh", str(wrapper)], env={**env, "R46H_SHELL_STATE_DIR": str(linked / "outside")}, capture_output=True)
    assert result.returncode == 2 and not (persistent / "outside").exists() and not args_file.exists()
stream = (repo / "mainline/gaming-moonlight/run-stream.sh").read_text()
options = stream[stream.index("# Both clients share"):stream.index("\nsystemd-run")]
for client, deadline, decoder in (("embedded", "300", "software"), ("qt", "120", "hardware")):
    result = bash(options + '\n[[ $deadline == "$EXPECTED" ]]\nprintf "%s\\n" "${command[@]}" "${client_env[@]}"',
                  client=client, server="host with spaces;$(never-run)", scope="/owned scope", EXPECTED=deadline)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert f"decoder={decoder}" in lines[0] and "host with spaces;$(never-run)" in lines[1:]
    if client == "qt":
        assert "--video-decoder" in lines and "hardware" in lines and "SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT=0x5246/0x0048" in lines
        assert not any("SDL_AUDIO_SAMPLES" in line for line in lines)
    else:
        assert "SDL_AUDIO_SAMPLES=1024" in lines
payload = stream[stream.index('if [[ $client == qt ]]; then\n  [[ -x'):stream.index("process_status=0")]
with tempfile.TemporaryDirectory(prefix="stream-payload-", dir=repo / "mainline/out/.cache") as temporary:
    root = Path(temporary); (root / "usr/bin").mkdir(parents=True)
    for name in ("qt-client.sh", "usr/bin/moonlight-qt"):
        f = root / name; f.write_text("fixture"); f.chmod(0o755)
    config = root / "state/config/Moonlight Game Streaming Project/Moonlight.conf"
    config.parent.mkdir(parents=True); config.write_text("fixture")
    fake = 'sha256sum() { echo "$ACTUAL file"; }\nldd() { echo "$CLOSURE"; return "$LDD_STATUS"; }\n'
    for actual, closure, status, expected in (("a"*64, "library found", "0", 0), ("b"*64, "library found", "0", 1),
                                               ("a"*64, "library => not found", "0", 1), ("a"*64, "check failed", "2", 1)):
        result = bash(fake + payload, client="qt", scope=str(root), expected_binary="a"*64,
                      ACTUAL=actual, CLOSURE=closure, LDD_STATUS=status)
        assert result.returncode == expected, (actual, closure, status, expected, result)
with tempfile.TemporaryDirectory(prefix="desktop-handoff-", dir=repo / "mainline/out/.cache") as temporary:
    root = Path(temporary); (root / "usr/bin").mkdir(parents=True)
    shutil.copyfile(repo / "mainline/gaming-shell/desktop-session.sh", root / "desktop-session.sh")
    client = root / "usr/bin/moonlight-qt"; client.touch(); client.chmod(0o700)
    wrapper = root / "shell-client.sh"
    wrapper.write_text('''#!/bin/sh
set -eu
if [ "$1" = --stream-worker ]; then
  test "$R46H_SHELL_LOG" = 0
  test "$SDL_VIDEODRIVER" = kmsdrm && test "$SDL_AUDIODRIVER" = alsa
  if [ "$ATTENDED" = 1 ]; then test "$6" = --attended; else test "$#" = 5; fi
  echo worker >> "$TRACE"
  exit "$WORKER_STATUS"
fi
if [ "$ATTENDED" = 1 ] || [ "$REMOTE" = 1 ]; then test "$5" = 1800; else test "$5" = 290; fi
if [ "$REMOTE" = 1 ]; then test "${11}" = --control-dir && test "${12}" = "$CONTROL" && test "${13}" = --test-input-capture; fi
echo gui >> "$TRACE"
if [ ! -e "$TRACE.started" ]; then touch "$TRACE.started"; exit 75; fi
exit 0
'''); wrapper.chmod(0o700)
    control = root / 'control with spaces'; control.mkdir(mode=0o700)
    for attended, remote in ((False,False), (True,False), (False,True)):
        for worker_status, expected in ((0, 0), (1, 0), (124, 0), (2, 2)):
            trace = root / f"trace-{attended}-{remote}-{worker_status}"
            options = ["--attended"] if attended else ["--remote", str(control)] if remote else []
            result = subprocess.run(["sh", str(root / "desktop-session.sh"), "a" * 64, *options],
                                    env={**os.environ, "TRACE": str(trace), "WORKER_STATUS": str(worker_status), "ATTENDED": str(int(attended)), "REMOTE": str(int(remote)), "CONTROL":str(control)}, capture_output=True, timeout=5)
            assert result.returncode == expected, result.stderr
            assert trace.read_text().splitlines() == (["gui", "worker"] if expected == 2 else ["gui", "worker", "gui"])
with tempfile.TemporaryDirectory(prefix="native-handoff-", dir=repo / "mainline/out/.cache") as temporary:
    root = Path(temporary)
    shutil.copyfile(repo / "mainline/gaming-shell/desktop-session.sh", root / "desktop-session.sh")
    wrapper = root / "shell-client.sh"
    wrapper.write_text('''#!/bin/sh
set -eu
if [ "$1" = --native-worker ]; then
  test "$R46H_SHELL_LOG" = 0
  if [ "$ATTENDED" = 1 ]; then test "$2" = --attended; else test "$#" = 1; fi
  echo worker >> "$TRACE"; exit "$WORKER_STATUS"
fi
test "$2" = --scene && test "$3" = "${SCENE:-neo}" && test "$6" = --native-handoff
if [ "$ATTENDED" = 1 ] || [ "$REMOTE" = 1 ]; then test "$5" = 1800; else test "$5" = 290; fi
if [ "${7:-}" = --resume-native ]; then shift 7; else shift 6; fi
if [ "$REMOTE" = 1 ]; then test "$1" = --control-dir && test "$2" = "$CONTROL" && test "$3" = --test-input-capture; fi
echo gui >> "$TRACE"
if [ ! -e "$TRACE.started" ]; then touch "$TRACE.started"; exit 79; fi
exit 0
'''); wrapper.chmod(0o700)
    control = root / "control with spaces"; control.mkdir(mode=0o700)
    for native_mode in ("native", "ports"):
        for attended, remote in ((False, False), (True, False), (False, True)):
            for worker_status, expected in ((0, 0), (1, 0), (124, 0), (2, 2)):
                trace = root / f"{native_mode}-{attended}-{remote}-{worker_status}"
                options = ["--attended"] if attended else ["--remote", str(control)] if remote else []
                result = subprocess.run(["sh", str(root / "desktop-session.sh"), native_mode, *options], env={**os.environ,
                    "SCENE": "ports" if native_mode == "ports" else "neo", "TRACE": str(trace), "WORKER_STATUS": str(worker_status), "ATTENDED": str(int(attended)), "REMOTE": str(int(remote)), "CONTROL": str(control)}, capture_output=True, timeout=5)
                assert result.returncode == expected, result.stderr
                assert trace.read_text().splitlines() == (["gui", "worker"] if expected == 2 else ["gui", "worker", "gui"])

print("GAMING_PROBE_CHECK PASS: client hashes/dependencies, busy/error guards, desktop handoff and cgroup/frontend recovery (host mocks)")
