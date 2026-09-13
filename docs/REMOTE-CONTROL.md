# Agent control and UI testing

Status: **DIRECT-DISPLAY + R36 SHARED SSH/CONTROL DEVICE PASS / ATTENDED GATES OPEN**. This owns the
agent operation tool and its repeatable UI tests. The [desktop plan](DEVICE-SHELL.md)
owns display/input architecture. Existing [DRM capture](../mainline/gaming-remote-screen/README.md)
and [remote input](../mainline/gaming-remote-input/README.md) keep their own
accepted device contracts. Revision 11 adds a temporary Qt-only SSH session;
no persistent endpoint/key was installed on R46H. [Project Context](PROJECT-CONTEXT.md)
owns the next boot gate.

The [2026-09-09 session](../mainline/gaming-shell/STREAMING.md#attended-result-2026-09-09)
proved actual-device taps, verified Qt-window captures and fresh IPC generations
after normal, host-loss and reconnect returns. The [R35/R36 device check](../mainline/gaming-wayland/HANDHELD.md#r35r36-device-follow-up-2026-09-12)
adds persistent Neo save/load and PortMaster catalog proof through composed capture
and guarded actions. Physical L3+R3, LCD/audio and PC-stream input remain open.

## Run the local tool

The shell's `--control-dir ABSOLUTE_DIRECTORY` explicitly enables one private
Unix socket. Normal startup has no endpoint. Build using the shell runner, then
use isolated state and short socket paths on the external workspace:

```sh
mainline/gaming-shell/run.sh --check
TMPDIR="$PWD/mainline/out/.cache/r46h-shell/tmp" \
  mainline/out/.cache/r46h-shell/build/r46h-shell \
  --state-dir "$PWD/mainline/out/ctl-state" \
  --control-dir "$PWD/mainline/out/ctl" --quit-after 300
```

While that process runs, the host CLI can observe and save a verified window
capture. Run the operator's commands in an independent terminal; agents use
background processes, not the Codex bottom terminal.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B mainline/gaming-shell/control.py \
  --socket "$PWD/mainline/out/ctl/control.sock" \
  --output-dir "$PWD/mainline/out/ctl-traces" observe
```

For an action, copy `session`, `sequence` and `binary_sha256` from the preceding
observation. The placeholders below denote those exact values:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B mainline/gaming-shell/control.py \
  --socket "$PWD/mainline/out/ctl/control.sock" \
  --output-dir "$PWD/mainline/out/ctl-traces" --expect-binary BINARY_SHA256 \
  tap right --session SESSION_UUID --sequence SEQUENCE
```

`--no-image` skips capture and returns logical state immediately. Screenshot
requests allow 250 ms for the current short UI transitions without blocking
input. They capture one window; the API does not promise that independent
operator input or an ongoing animation was stationary. `--profile-ui` and the
control endpoint cannot run together: diagnostic captures are not performance
samples. No browser dashboard, continuous video or new host service is needed.
The `volume`/`brightness` state fields remain saved preview preferences.
Revision 15's `state.device` contains actual numeric readback and sample age;
`state.telemetry` contains process CPU/RSS/UI submissions and sampling status.
Unavailable device identity returns only `target: false, controls: false`.
No interface changes settings merely to obtain a measurement.

## Bounded metric recording

```sh
# Same transport/hash/output arguments as observe; select record instead:
python3 -B mainline/gaming-shell/control.py --socket /absolute/control.sock \
  --output-dir "$PWD/mainline/out/metric-record" record --seconds 30 --interval 2
```

The host tool issues read-only observations without screenshots and publishes
private JSON/CSV under external `mainline/out`. It accepts 2–300 seconds and
1–10-second intervals. Enable the HUD beforehand when process CPU/RSS/submissions
are needed; hidden HUD sampling stays off. Device health reads retain their own
two-second cadence. Values of -1 mean unavailable, and `sampleAgeMs` exposes age.
Only explicit numeric/boolean metrics enter exports, never UI text or profile names.

Transport loss or a changed process generation stops recording without retries
and saves completed samples as `partial`; no samples means a clear failure.
This is diagnostic polling, including transport overhead. Shared Wayland sessions
also export `gameActive`, `gameSubmissions`, median/P95/max submission intervals,
last-frame age and output-mode refresh from the [game producer](../mainline/gaming-wayland/HANDHELD.md#game-frame-metrics).
These count client buffers, not LCD presentations or GPU render duration.
The direct-display Moonlight handoff ends Qt and its recording; the shared session
keeps Qt alive. The [native streaming producer](../mainline/gaming-shell/STREAMING.md#native-statistics)
also exports `streamActive`, `streamAvailable` and its fixed numeric fields.
Unavailable or expired values are -1; rendering-call duration and network-audio
queue length do not establish GPU duration or speaker latency.

## Temporary R46H SSH session

Build with `mainline/gaming-shell/build-linux.sh`. The cache's `receipt.json`
binds the preview tar, stripped executable and frozen sources. Revision 11 is
also retained under `mainline/out/.cache/r46h-ui-remote-20260909/`. It needs no
Python on R46H, persistent service, home `authorized_keys` edit or TF rewrite.
For real settings, revision 14's [device lease](../mainline/gaming-shell/DEVICE.md)
adds `--remote-device` with the same key/address arguments. Normal `--remote`
keeps device writes disabled. Network switching may disconnect this transport.
Revision 15 also offers `--remote-streaming SHELL_SHA256 CLIENT_SHA256
PUBLIC_KEY_SHA256 DEVICE_IP MAC_IP` using the combined package. It retains the
SSH relay across [desktop/Moonlight handoff](../mainline/gaming-shell/STREAMING.md#direct-display-handoff),
with device-setting writes disabled. During a stream the Qt endpoint is absent;
after return, a fresh observation supplies the new generation and sequence.

1. Create a fresh client key in a new external session directory. Only its
   public half will reach R46H; never print or archive the private key:

   ```sh
   umask 077
   remote_work=$(mktemp -d "$PWD/mainline/out/.cache/r46h-ui-session.XXXXXX")
   ssh-keygen -q -t ed25519 -N '' -C r46h-ui-test -f "$remote_work/id_ed25519"
   shasum -a 256 "$remote_work/id_ed25519.pub"
   ```

2. Follow the [serial procedure](DEVELOPMENT.md#serial-and-physical-sessions).
   Rediscover UART and both IPv4 addresses; verify the fixed card, kernel, root
   UUID, read-only ROMs and service/health state. Require external supply and
   continue health monitoring: `online=1` alone does not prove net charging.
   Read battery voltage/thermal state and stop load on warnings or decline.
3. Transfer the receipt-bound preview tar and fresh public key using authenticated,
   bounded SFTP with a serial-verified host key. Match SHA-256 through UART before
   extraction/use. Do not expose the bundle/cache through an unauthenticated HTTP server.
   Stage only this payload in `/run/r46h-shell-probe`, owned `ark:0700`, with
   the key named `remote-client.pub`. Check free `/run` space first; after
   retaining prior evidence, remove only the previous task-owned staging.
4. Through the verified root serial session, start the guarded probe; placeholders
   below must be replaced by this session's verified hashes/addresses:

   ```sh
   /run/r46h-shell-probe/probe-r46h.sh --remote \
     SHELL_SHA256 PUBLIC_KEY_SHA256 DEVICE_IP MAC_IP \
     > /run/r46h-shell-probe/probe.log 2>&1 &
   ```

   Wait for the two public identity files to appear; read them over UART, not
   the untrusted network, using `cat /run/r46h-shell-probe/remote-identity` and
   `cat /run/r46h-shell-probe/remote-known-hosts`. Match the current boot ID and device/Mac addresses.
   Save the exact `[DEVICE_IP]:22222 ssh-ed25519 ...` line as
   `$remote_work/known_hosts`, mode 0600. Do not substitute `ssh-keyscan`,
   accept-new or a disabled host-key check.
5. On the Mac, observe the actual UI; the CLI requires the expected ELF hash:

   ```sh
   PYTHONDONTWRITEBYTECODE=1 python3 -B mainline/gaming-shell/control.py \
     --ssh-host DEVICE_IP --identity-file "$remote_work/id_ed25519" \
     --known-hosts "$remote_work/known_hosts" --expect-binary SHELL_SHA256 \
     --output-dir "$remote_work/captures" observe
   ```

   For a tap, keep these options and replace `observe` with
   `tap right --session SESSION_UUID --sequence SEQUENCE`, using the immediately
   preceding result. Inspect its PNG/state before choosing the next action.
6. The preview exits after 30 minutes; its outer cgroup has a 31-minute ceiling
   and restores ES-DE. To finish early, stop the exact `r46h-shell-probe-*.service`
   created by this run through serial. Check `SHELL_END` and actual frontend
   status, then retain public evidence and remove task-owned staging/keys. End
   unattended hardware with health, `sync` and serial-confirmed poweroff.

[remote-session.sh](../mainline/gaming-shell/remote-session.sh) starts a separate
`sshd` on the verified device IPv4/port 22222, restricted to user `ark` from this
Mac. Password/root login, TTY, forwarding and user rc are disabled. It uses the
device's existing host key and only the fresh test public key. `ForceCommand`
invokes the QCore-only relay; the sole accepted SSH command is `r46h-control`.
Neither shell arguments nor arbitrary files can be requested. The GUI and daemon
share the probe cgroup; temporary SSH config/socket directories are removed on
exit. The host uses `/usr/bin/ssh` with isolated config and strict explicit trust.
The relay has a 15-second lifetime and the host a 20-second response ceiling.

Plain `--remote` runs the desktop UI only; `--remote-streaming` preserves the relay
across direct-display handoffs. Use serial for deployment/recovery and retain ES-DE.

## Shared Wayland SSH candidate

The newer handheld package reuses that SSH helper and QCore relay. After the
usual manifest/device checks, stage `remote-client.pub` as a root-owned regular
file, mode 0644, with one link. Its SHA-256 must match the public key transferred
through the verified serial session. Start the bounded shared session with:

```sh
/run/r46h-wayland-probe/probe-r46h.sh --remote \
  MANIFEST_SHA256 PUBLIC_KEY_SHA256 DEVICE_IP HOST_IP
```

The shared payload root is `/run/r46h-wayland-probe`, owned `root:root`, mode
0755, unlike the older direct-display scope above. Use the current
[R36 artifact/run record](../mainline/gaming-wayland/HANDHELD.md#resume-and-rebuild),
not the historical R25 package. The default UI/game state is disposable.
Opt-in `R46H_SHELL_STATE_DIR=/home/ark/.local/share/r46h-preview` also enables the packaged
[native-port runtime lease](../mainline/gaming-ports/README.md#shared-target-session-candidate).
Read `remote-identity` and `remote-known-hosts` from `/run/r46h-wayland-probe`
over serial. The host CLI's `--expect-binary` still takes the shell ELF hash,
not the manifest hash. Existing SSH options now carry composed capture and the
bounded `game-input` operation as well as Qt actions. The desktop/IPC generation
remains alive across shared game/stream exits. The current native worker is bounded
to 120 seconds, the UI to 290 seconds and the outer cgroup to 360 seconds.
Have the host automation waiting before launching the preview. The separate
[85 C health monitor](../mainline/gaming-wayland/HANDHELD.md#r33-device-follow-up-2026-09-11)
must be recreated each run; that threshold is not embedded in the candidate or kernel.

The SSH relay uses its own temporary state directory. A detected SSH output-pipe
closure closes the local request, cancelling active input without waiting for its
lease to expire; the broker deadline remains the fallback for undetected network
loss. Private-entry refusal and session/binary/application/sequence checks are
unchanged. `check-remote.sh` tests the actual authenticated helper/relay in an
isolated container, with a headless seat substitute and a real SDL input consumer.
R32 passed the target temporary transport/seat path, HUD-independent frame
readiness and short matched samples. R35 passed outer runtime cleanup, normal
game return and persistent Neo save/load across warm reboot. R36 then displayed
the four local projects and 1,396 PortMaster catalog entries. Disconnect latency,
catalog mutations, native games and physical controls are separate gates.

R25 is frozen at `mainline/out/.cache/r46h-compositor-20260910/r25/receipt.json`,
source `eb31fad03030f8ffbe43ab2138393b19971e2c3d` on
`codex/r46h-shared-remote-r25-candidate`. The 33,648,662-byte archive expands to
92,868,724 regular-file bytes. Its packaged ELF passed the real SSH/game-input
flow and full manifest readback; the recorded disconnect released input in 89 ms
against a 1,000 ms lease. That is one host observation, not a target latency guarantee.

### Shared game readiness

`externalSession`, `sharedReady` and `gameInputAvailable` describe process/policy/
input readiness; they do not establish that a game has submitted its first frame.
The R31 run returned the previous page with a two-second process-only wait.
The shell now samples game submissions once per second while a game is active,
independent of HUD visibility. The client-side `wait-game-frame` command performs
only bounded no-image observations, pins the session and binary, and succeeds after
`state.telemetry.game.lastFrameAgeMs >= 0` with positive `submissions`:

```sh
python3 -B mainline/gaming-shell/control.py REMOTE_OPTIONS \
  --output-dir EXTERNAL_OUTPUT --no-image --expect-binary SHELL_SHA256 \
  wait-game-frame --seconds 25
```

The successful wait proves recent client buffer submissions, not the captured
content or LCD presentation. R32 passed that wait with the HUD hidden, then a
distinct composed Neo capture. Request and validate the PNG after every new launch.

Historical reference flow: `mainline/out/.cache/r46h-r31-device-20260911.CVD4cJ/frame-ready.py`;
its paired `evidence/frame-ready-result.json` is **INCOMPLETE** because 85 C aborted
exit confirmation. Earlier `automatic-result.json`/`resume-result.json` contain
failed timing attempts, not additional passes. These scripts contain old session
paths/addresses and the key was deleted: adapt the flow to a fresh session, do not
replay it directly. Read the per-step frames and authoritative `session.json`.

R31–R33 used a temporary chrooted SFTP service on device port 22221, restricted to
the verified Mac address and fresh key. Password/root login, TTY and forwarding
were disabled; only its `upload/` directory was writable. Keep transfer separate
from port 22222's restricted UI relay, remove the verified archive before the UI
starts, and stop both services/remove the fresh key during cleanup.

## Protocol and permissions

Each connection accepts one newline-terminated JSON request, at most 4096 bytes.
The response is one JSON object followed by EOF. Only one request is active;
a stalled peer is closed after three seconds. Busy/unauthorized peers are closed.
Malformed or oversized input is rejected; an oversized peer may receive a reset
before its error response. Request parameters and text values are never logged.

| Operation | Required fields beyond `version: 1`, `id`, `op`, `screenshot` |
| --- | --- |
| `observe` | None; reports this process generation and safe UI state |
| `tap` | Exact `session`, `binary_sha256`, `sequence` and one allowlisted `action` |
| `text` | The same identity/sequence fields plus `text`; only public game search or the explicitly enabled disposable input test |
| `game-input` | Shared-session identity fields plus `application`, `input_sequence`, `duration_ms`, `buttons`, `axes`; see the bounded input contract below |

Actions are `left`, `right`, `up`, `down`, `accept`, `back`, `quick`, `favorite`,
`home`, `previousTab`, `nextTab`, `erase` (Y), `submit` (START). Unknown fields/actions are refused. Sequence
checking rejects stale/replayed actions; the generation rejects commands for a
restarted process. There is no automatic action retry after transport failure:
observe again before deciding whether to repeat it. An accepted tap means the
application handled the action; inspect state for a blocked save or unchanged
selection. It is not a guarantee that a requested page transition succeeded.

The directory must be owner-only mode 0700, owned by the process user and not a
symlink. The socket is mode 0600; macOS `getpeereid` and Linux `SO_PEERCRED` also
check the peer UID. Existing socket paths are refused, never unlinked to take
over another process. Normal exit removes this process's socket. Following a
crash, verify the stopped process before removing its exact stale socket/directory.
The Qt process has no TCP listener, arbitrary shell, file-read request or QML evaluation.

The response names the executable hash, process generation, action sequence,
kernel and `qml-action` input backend. Capture metadata identifies `qt-window`,
logical/native dimensions, scale, orientation, monotonic time, length and SHA-256.
PNG bytes travel in the same response; there are no server-side export files.
The CLI verifies size/hash and the explicit bounded Qt RGB/RGBA PNG profile,
then publishes private PNG/JSON files atomically without overwriting existing
results. The existing DRM validator's default 1024×768 RGB/filter-0 contract
remains strict. A receipt maps the executable hash back to its frozen source.

Sensitive-entry captures return `sensitive_entry` without pixels. The optional
`--test-input-capture` flag permits only the labelled disposable input-test page,
including typed test text; never enter secrets there. Real editors and pairing
PINs stay blocked even when this flag is enabled. The remote preview enables
this test exception so the agent can inspect keyboard behavior. UI state omits
input contents, clipboard, credentials and raw error text. `remoteTextAllowed`
reports whether the narrow `text` operation is available. It replaces at most
80 characters, rejects control characters and does not submit the field. Host
editors, Wi-Fi passwords, PINs and other real editors refuse it; search-editor
captures remain blocked. Use `submit` separately to confirm a public search.
Missing/hidden/oversized windows are explicit capture
failures; no alternative screen is captured.

For a public search, keep the transport/output options and the latest expected
binary hash, then use `text --value=-测 --session SESSION_UUID --sequence SEQUENCE`.
This shares tap's freshness/replay protection. The server does not log request bodies, and response/evidence records omit
input contents; a committed public search can naturally appear on its
results page. The response's `operations` list advertises supported operations.

## Checks and remaining integration

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B mainline/tests/test-shell-control.py \
  --binary mainline/out/.cache/r46h-shell/build/r46h-shell \
  --evidence mainline/out/.cache/r46h-control-check
```

The check launches the actual application, exercises navigation, modal isolation,
settings focus, tester/input exit, HUD toggles, failed-save retention, stale
session/binary/sequence refusal, malformed/oversized requests and atomic capture.
It checks default endpoint absence and normal socket cleanup, and reports RSS
before/after repeated navigation without claiming a device memory budget.
Routine development uses the short default flow. Larger `--cycles` and paced
repeats are opt-in diagnostics, not required on every build.
With a configured application list, taps can launch only those entries. In an ordinary window session, the
endpoint reports the external-session state and ignores shell actions until the
child exits; it neither captures nor controls the child application.
The ARM64 builder runs it against the relocated stripped package, including a
cross-UID rejection test in its isolated Linux container. Container IPC uses
`/run`: macOS Docker shared volumes do not satisfy the private-socket checks.
Builds, state and retained evidence stay on the external volume.

`test-shell-ssh.py` runs one short flow against a prepared isolated SSH server
and actual ARM64 Qt process. It checks before/after PNGs, stale actions, wrong
host key, paths with spaces, command/forwarding refusal and, with `--keyboard`,
test-page typing/deletion/confirmation plus real-editor capture refusal.
The 2026-09-09 run passed; `ssh-final/summary.json` and captures in the revision
directory retain it. The isolated server used OpenSSH `1:10.0p1-7+deb13u4`;
target daemon/config compatibility still requires its own `sshd -t` and login.
Container Qt screenshots prove this application's output, not R46H LCD behavior.

Application actions prove Qt navigation, not remote kernel/SDL delivery or game input.
The shared-display candidate now returns `weston-output` captures using a fresh
public-frame fence, an expiring capture allowance and final scene/privacy checks.
The CLI validates that backend only when `sharedDisplay` is true. Private entry,
close-and-capture and cancellation while the compositor is paused pass host checks.
The shared session's [bounded game-input contract](../mainline/gaming-wayland/HANDHELD.md#bounded-remote-game-input)
now passes actual RPC/CLI → uinput → SDL host checks. It uses current application
and input-generation guards, a 10–1000 ms sample, automatic release and physical
takeover. It reports `routed-uinput` separately from Qt actions. R31's routed Ozone
input passed on R46H; the PC/Sunshine path remains a separate acceptance gate.

Copy `ACTIVE_APP` and `INPUT_SEQUENCE` from the same observation as the other
identity fields, then use a short explicit sample:

```sh
python3 -B mainline/gaming-shell/control.py --socket SOCKET --output-dir EXTERNAL_OUTPUT \
  --expect-binary BINARY_SHA256 game-input --session SESSION_UUID --sequence SEQUENCE \
  --application ACTIVE_APP --input-sequence INPUT_SEQUENCE --duration-ms 200 \
  --button a --left-x 0.5
```

Wayland capture must use the compositor's supported path and cover every active
plane. The old single-framebuffer reader and a Qt window capture do not establish
that. Do not expose unrestricted Weston debug interfaces as product control.
Actual LCD pacing, audible output and physical controls remain attended gates.

`test-portmaster-ui.py` also checks text refusal outside a supported editor and
in a host editor, stale text rejection, a literal leading-hyphen search, private
search capture refusal, and install-instruction modal isolation.
