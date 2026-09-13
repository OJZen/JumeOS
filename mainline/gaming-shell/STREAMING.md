# Moonlight management experiment

Revision 17, 2026-09-09. Remote handoff and v3 native HUD/A/V have short attended
proof. Long-session stability and application-list retrieval remain open. [Game Streaming](../../docs/GAME-STREAMING.md)
owns accepted streaming results and the next hardware gate.

The attended launcher adds `probe-r46h.sh --attended SHELL_SHA256 CLIENT_SHA256`.
Only while an operator is present, this permits 30 minutes per desktop process,
35 minutes per stream and 90 minutes for the outer cgroup. This leaves time to
observe 30 full streaming minutes before deliberately stopping the host.
Pairing remains limited to 60 seconds; the default short probes are unchanged.
The operator can leave each stream with L1 + R1; the agent stops the owned unit
for early recovery or when the operator leaves. The ten-second cgroup stop and
mixer/ES-DE restoration remain active.
The attended v2 `gpuslow` build prioritizes direct rendering even with
`DRM_FORCE_EGL=1`. The [v3 candidate](../gaming-moonlight/QT-CANDIDATE.md) removes
that preference; verify the actual renderer before comparing it.

## Attended result (2026-09-09)

The unchanged v0.17 card ran shell R17 with the v3 client and `DRM_FORCE_EGL=1`.
At 640×480/60 FPS/4 Mbps, the operator confirmed native performance text, normal
picture/audio, individual shoulder behavior and L1 + R1 return. The first stream
reported 59.25 rendered FPS and 11.91 ms average rendering time including V-sync.
Actual descriptors included Hantro `/dev/video1`, `/dev/media0` and DRM/Panfrost;
ALSA used stereo 48 kHz S32_LE, 1440/2880-frame period/buffer. The retained log
does not name the final renderer class. This short observation does not establish
all-content tearing/audio immunity or long-session stability.

Stopping the isolated Sunshine returned status 1 and a fresh desktop generation;
the operator accepted automatic return and its error message. Restarting the same
private server state allowed reconnection without pairing again, followed by a
normal status-0 return. Each restored UI accepted a fresh remote observation.
Application-list refresh returned no names twice despite successful known-name
streaming; this remains open. The host entry was prefilled, not a new add-host UI test.

All transient units restored ES-DE and the audio mux. CPU/backlight leases were
restored separately; services had zero restarts, ext4 errors stayed zero and ROMs
remained read-only. Logs were UART-hash-verified, temporary credentials/servers
removed and controlled poweroff confirmed. The later Wayland supplement has its
own record. Evidence: `mainline/out/.cache/r46h-acceptance.TiyDFF/session.json`
and `evidence/r17-device.tgz`. R17 keyboard/Y/START/wrapping and real dim/wake
observations belong to [Device settings](DEVICE.md); focus pacing remains open.

## Attended result (2026-09-08)

The unchanged v0.17 card cold-booted with the two-speed serial capture. The
operator confirmed Chinese input, pairing, Select exit from the stick tester,
invalid-app error return and successful reconnection after restoring the name.
Host loss exited the client with status 1; the operator accepted the return,
message and controls. Normal returns exited 0; the first took about three seconds.

| Requested preset | Rendered FPS | Median CPU, one-core scale | Operator observation |
| --- | --- | --- | --- |
| 640×480 / 60 / 4 Mbps | 58.85–59.29 | 37.2–38.2% | Initial audio normal/no pops; tearing; native HUD absent |
| 640×480 / 30 / 3 Mbps | 29.99–30.00 | 31.9–34.6% | Video more stable; occasional audio roughness |
| 1024×768 / 60 / 8 Mbps | 58.08 | 56.9% | Complex motion tears and audio stutters; ordinary scenes normal |

Hantro/media device use and matching stream dimensions were observed; the prior
reference-count warnings were absent. Native ALSA used 1440/2880-frame period/
buffer at 48 kHz. These are separate short samples, not a controlled same-content
comparison or end-to-end latency measurement. The EGL-variable repeat still had
no HUD; its reported reduced tearing does not establish a renderer change.
Thirty-minute acceptance is deferred until the display/audio issues are resolved.

UI follow-up: revision 12 adds expandable choices and a shared focus/page motion
system with settings; hardware smoothness remains untested. Revision 11
implements device-only hints, Y deletion, START confirmation and horizontal
keyboard wrapping within a row; these changes have host checks only.
That sample's brightness slider and dim mask did not control real backlight.
The later R17 [device session](DEVICE.md) accepted guarded backlight/CPU writes;
direct-display streaming leaves them disabled. The shared Wayland candidate now
offers the [explicit device lease](DEVICE.md#shared-wayland-settings-candidate).

Kernel low-voltage warnings prompted a pause. External supply was then detected
and average battery voltage recovered above the reported minimum; the driver
still said `Not charging`, so net charging was not established. The final SoC
sample was about 80°C. Core services had zero restarts, ext4 errors stayed zero,
and ROMs stayed read-only. Public evidence was UART-hash-verified before cleanup;
serial confirmed filesystem detach and poweroff. Owned servers and private test
state were removed. No TF image, global mapping or host service was installed.

Evidence owner: `mainline/out/.cache/r46h-attended-20260908/session.json`,
`performance.json`, both `device-*-evidence.tgz` files and serial traces.
The separate [Wayland result](../gaming-wayland/README.md#device-result-2026-09-08)
does not establish Moonlight under a compositor.

## Interface and state

The default home Moonlight card opens host management; `--scene streaming`
opens it directly. X adds an IPv4 address or DNS name. A enters the selected
host, Up/Down selects a setting, and Left/B returns to the host list.
The shared keyboard edits host name, address and Sunshine application name;
Enter/Done/START saves, Y deletes, B or hiding the keyboard cancels. Invalid input or failed
writes keep the editor open. IPv6 and automatic LAN discovery are not implemented.

The application row now opens the shared chooser. Select **Refresh application
list** to run the hash-checked client's non-verbose `list HOST`; successful
readback reopens the choices. Names are session-only, at most 256 entries/32 KiB,
and clear when switching/removing a host or changing its address. Selection saves
the literal name through the existing atomic state path. **Manual name entry**
remains available for unavailable/unpaired hosts. A 45-second supervisor deadline
and B cancellation bound list retrieval; stderr and raw protocol output are
discarded. This uses the frozen upstream CLI implementation, not a second pairing
or certificate store. Host fake-client parsing, cancellation, failure and UI checks
pass; the actual Sunshine application list still needs the device session.

The three H.264 hardware-decoder presets are 640×480/60/4 Mbps (default),
640×480/30/3 Mbps and 1024×768/60/8 Mbps. The switch controls Moonlight's own
performance overlay. Other settings retain native stereo audio and disable
HDR/YUV444/game optimization and automatic host-app termination.
A opens the shared choice list for quality; Up/Down previews, A confirms and B
cancels. Highlighting alone does not change the preset; failed saves keep the
choice open. The [control contract](controls/README.md) owns common interaction
and motion. Detail rows now scroll with a shared indicator at large font sizes.

`streaming/hosts.json` under `--state-dir` stores version 1, a selected UUID and
at most 32 records: `id`, `name`, `address`, `application`, `preset`, `overlay`,
`paired`. Writes are atomic and owner-only; invalid/unreadable state and symlinks
are refused. A failed deletion retains the visible host. Online status is a
bounded HTTP `serverinfo` reachability check, not authenticated pairing proof.
The saved paired flag is only a UI hint; the client verifies the actual identity.

Pairing runs the exact hash-checked [Qt client](../gaming-moonlight/QT-CANDIDATE.md)
offscreen, with a 60-second deadline and B cancellation. The random four-digit
PIN exists only in memory/UI. Pair output is discarded; PIN/text-entry captures
are refused. Client identity remains in private `streaming/client/` for reconnect.
Do not archive that directory, PINs or host credentials. The experiment's tmpfs state
survives desktop restarts, not device poweroff; persistent installation is deferred.

## Direct display handoff

[desktop-session.sh](desktop-session.sh) runs one UI at a time. Start writes a
validated owner-only request and exits the UI with status 75. Only after the GUI
has exited does a QCoreApplication worker consume that request once and run
Moonlight with the fixed binary/hash and presets. It uses EGLFS/KMSDRM and ALSA;
the desktop restarts after normal exit, connection failure or the 120-second
stream limit. Status 2 stops on local validation/record failure. Returning waits
for neutral controller input. No GUI remains holding DRM during the stream.

The worker keeps only a bounded, filtered decoder/performance log and exit
record. Raw protocol output is never written. The outer probe owns all processes
in one transient cgroup, with a 900-second experiment limit and ten-second stop
limit; it restores the audio mux and ES-DE. Generic EGLFS application launching
remains blocked. This handoff provides no cross-process quick panel/global HUD;
that still needs the [shared-display gate](../../docs/DEVICE-SHELL.md#display-and-input-decision).

Revision 15's `--remote-streaming` probe wraps this supervisor in the existing
temporary SSH session. The relay stays up while the GUI releases DRM; its UI
socket is unavailable during the stream. Each restored desktop creates a fresh
IPC generation. A Start tap may lose its reply because the GUI exits: never
retry it automatically. After return, observe the new generation before sending
another action. Actual host Qt tests pass for normal/error worker return, fresh
generation and stale-action refusal. A fake worker cannot prove R46H DRM recovery.
This mode retains the short 120-second stream limit and a 31-minute outer unit;
long attended streaming still uses the separate `--attended` mode.

## Shared display candidate

With `--handheld-router` on Wayland, the built-in management page launches the
same request-consuming worker through the foreground application manager. The
desktop, remote endpoint and UI generation stay alive. The worker inherits the
private Qt runtime, explicitly selects Wayland for Qt/SDL, removes direct-DRM
overrides and receives only the routed controller mapping. Pairing/list operations
keep their existing offscreen/dummy environment and private client directory.
The existing 120-second stream ceiling and filtered log still apply.

### Native statistics

With the opt-in [v5 client](../gaming-moonlight/QT-CANDIDATE.md#current-revision),
the shared worker enables `R46H_STREAM_STATS=1`. A separate stdout pipe carries
only the bounded numeric `streamstats.h` schema; stderr cannot supply metrics.
The worker validates and re-encodes messages before the desktop receives them.
Both producers use nonblocking writes and tolerate a closed consumer. Other
applications keep stdout discarded. No raw diagnostic message enters stream.log
and no periodic statistics file is written to the TF card.

The desktop exposes `telemetry.stream` with `active`/`available`, native video
rates, network/pacing drops and timing fields. Valid samples expire after 2.5
seconds of silence and are cleared on exit/reconnect. The global HUD shows native
rendered FPS, decode time, RTT, drops and queue times; the existing recorder exports
all fields with a `stream` prefix. The native source's one-second counter/report
continues during the stream when the HUD is hidden; hiding the HUD still suppresses
its rendering and ordinary process sampling. Actual overhead needs target measurement.

`renderCallMs` includes time spent inside the renderer call, not GPU execution or
LCD scanout. `audioNetworkQueueMs` measures pending compressed audio before client
decoding, not ALSA/device buffering, underruns or speaker latency. Missing values
remain -1. These distinctions also apply to recorded values.

Host checks cover the actual native formatter, full/closed pipe handling, split
messages, unknown/string-field refusal, stderr isolation, expiration and desktop
return. The Qt/Wayland integration uses a fake transport with controlled values;
actual Sunshine/Hantro/audio statistics remain an attended-device gate.

R28 is frozen at `mainline/out/.cache/r46h-compositor-20260910/r28/receipt.json`,
source `a3f03889ffc4b2030dd5ecea6ae53d9f38e706f1` on
`codex/r46h-stream-stats-r28-candidate`, with the v5 client. Its 33,666,920-byte
archive expands to 92,940,749 regular-file bytes; full archive/manifest readback
and matching client/desktop protocol hashes passed. The complete packaged session,
power-exit, input/privacy and authenticated SSH checks also passed. This retains
R27/v4 and the accepted R17/v3 device fallback; no TF or device change occurred.

L3 + R3 opens the resident panel; B resumes. The panel receives navigation before
the hidden management page. Native client exit/error restores that page; explicit
Stop uses the common group cleanup. Reconnection uses the same private client
state. The desktop records explicit Stop as a completed session even if the
worker was terminated before writing its result; a later UI restart cannot show
an older connection failure. Host checks run the actual GUI, worker and Wayland/SDL child with a fake
transport: literal arguments, routed input, capture/privacy, normal/error return,
reconnect, Stop and same IPC generation pass. Actual Moonlight/Hantro/A/V and
gamepad delivery to Sunshine remain device gates. R21 is the frozen diagnostic
package; subsequent streaming packaging is owned by [the shared runbook](../gaming-wayland/HANDHELD.md).

## Build and attended run

```sh
sh mainline/gaming-shell/build-linux.sh
sh mainline/gaming-shell/build-streaming.sh /absolute/moonlight-qt-arm64 SHA256
```

The combined public tar is `mainline/out/.cache/r46h-shell/r46h-streaming-desktop-arm64.tar.gz`.
Revision receipts freeze source, shell/client hashes, dependencies and tests.
Do not infer a target hash from an older preview receipt.

After rediscovering serial/network and verifying the unchanged v0.17 identity,
transfer/hash-check the tar into task-owned `/run/r46h-shell-probe`, extract and
restore the directory to `ark:0700`. Run `probe-r46h.sh --check SHELL_SHA256`,
then `probe-r46h.sh --streaming SHELL_SHA256 CLIENT_SHA256`.
For agent-operated management, follow the [remote session procedure](../../docs/REMOTE-CONTROL.md#temporary-r46h-ssh-session)
and use `--remote-streaming SHELL_SHA256 CLIENT_SHA256 PUBLIC_KEY_SHA256 DEVICE_IP MAC_IP`.
No rootfs/TF rewrite or boot service is required. Keep the current Mac's patched
Sunshine manually started with fresh isolated state and UPnP disabled.

On the Mac, [sunshine-pin.py](../gaming-moonlight/sunshine-pin.py) accepts the
test's private directory, containing newly generated `operator.json` credentials
and `server.crt`. Use real Terminal for its hidden PIN prompt; `--check` verifies
local authentication without a PIN. It connects only to localhost, trusts that
test certificate, disables proxies and never prints credentials or responses.
Both files must be owner-only. Do not point it at unrelated existing credentials.

Confirm host editing, pairing, start, Hantro/HUD, LCD colors/audio, single
shoulders, L1 + R1 return and reconnect. Observe the return delay. Capture only
public decoder/health evidence; finish with service/storage/PCM health, cleanup,
sync and controlled serial-confirmed poweroff. Current Mac A/V acceptance does
not establish virtual-gamepad delivery to a supported game host.

Focused checks live in `shell-check` (`streamingProfilesAndWorker`,
`streamingNavigation`) and `mainline/tests/test-gaming-probe.py`. They cover
state validation/save failure, UI edit/profile navigation, safe logs and
supervisor normal/failure/timeout sequencing; they do not prove device DRM handoff.
