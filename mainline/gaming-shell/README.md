# Jume Launcher

Version **0.1.0-dev**. The internal executable and control-protocol identifier
remain `r46h-shell` for compatibility.

**2026-09-20 TWO-LEVEL DEVICE PASS / ES-DE FALLBACK.** This is a desktop prototype,
not the installed frontend. Its [shared R35/R36 path](../gaming-wayland/HANDHELD.md#r35r36-device-follow-up-2026-09-12)
has composed-frame/remote-control proof; ordinary EGLFS previews have only a local panel. The [design and next gates](../../docs/DEVICE-SHELL.md)
own the product direction. ES-DE and shared input mappings remain the fallback. Device writes require
the explicit temporary lease. An explicit application list enables foreground process launch on
shared-window platforms; the default list exposes six real built-in tool routes. No host
settings or Sunshine service are installed by this preview.

R35's identified-device candidate showed actual Wi-Fi link quality,
battery percentage and charge/discharge state beside the clock. Host previews keep
their explicit preview label instead of inventing device values.
Settings now includes an About page with the launcher name, version and
`https://github.com/OJZen/JumeOS`.
The 2026-09-17 native build passed all three Qt test targets; reviewed 100% and
120% host captures are under `mainline/out/.cache/jume-launcher-about-20260917/`.
This is host-window evidence, not an R46H LCD result.

## Run on this Mac

```sh
mainline/gaming-shell/run.sh
mainline/gaming-shell/run.sh --check
```

[Application lists and launch](APPLICATIONS.md) owns `--applications`, stable
favorites, scrolling, child lifecycle and display restrictions. Normal exit and
failure restore the selected entry; returning waits for neutral controller input.
[Moonlight management](STREAMING.md) owns host editing, PIN pairing, stream
presets and the separate, bounded desktop-exit/stream/restart experiment.
Its attended record also tracks the current rendering, input-UX and backlight gaps.
The generic example application list is not activated automatically.

The runner builds with CMake and Qt 6.8.2 under
`mainline/out/.cache/r46h-shell/`. It uses the existing host SDL2 installation.
`R46H_QT_PREFIX` can point to another compatible SDK. No global Qt installation
is needed. The external SDK is a retained development dependency, not a release
bundle. Downloaded debug-symbol bundles were removed after verification;
release SDK tools/libraries remain available. Qt's shader/QML disk caches are disabled; build temporary files and
preview state stay beside the external build. On a restricted agent host,
Qt's CPU-feature detection and WindowServer access may need the agent's normal
reviewed execution permission. Do not disable CPU checks to bypass that failure.

Native SDK preparation used aqtinstall 3.3.0 and official Qt 6.8.2 macOS base
and declarative archives. Only the local download tool's cache/temp paths were
redirected to the external workspace (aqt's config key is `temp_path`). The SDK
was not installed in `/Applications` or the system package manager. The CMake
AGL workaround follows Qt's [upstream fix](https://github.com/qt/qtbase/commit/42b0903c34bd049729f85fcd6236e64f28898b34)
for the older SDK's obsolete link dependency on current macOS.

| Action | Keyboard | SDL controller, preview only |
| --- | --- | --- |
| Navigate / adjust | Arrows | D-pad / left stick |
| Confirm / back | Enter / Esc | A / B |
| Delete / confirm text | Backspace / Enter | Y / START |
| Favorite | X | X |
| Quick panel; leave controller test | Q | Select / Guide |
| Change page | `[` / `]` | L1 / R1 individually |
| Home | Home | Use panel's Home action |

Entering Settings shows only the category list, including entry by tabs,
shoulder buttons or pointer. Right/A asynchronously opens the selected category
as a second-level page; Left/B returns to the category list and unloads it after
saving pending values. Moving through categories does not construct detail rows
or refresh storage. Tool game lists follow the same rule; USB remains a deliberate
single-level page. For volume and brightness,
A/Enter starts adjustment, Up/Down increases/decreases, and A/Enter or B/Esc
finishes; Left also saves and returns to categories. Save failure retains the
editor and its pending value. Controller-test and text-entry modes keep their
own directional inputs; Select leaves the controller test, B leaves text entry.
Font size and idle timing open a choice list: Up/Down previews a selection,
A confirms, B cancels. Page shortcuts cannot escape an open choice list.

The [shared controls](controls/README.md) own typography, palette, spacing and
motion. Settings and Moonlight now share their row/switch/scrollbar styling and
independent moving focus frame. Page navigation, field editing and buttons use
the same primitives. Input stays live during transitions; reduced motion removes
spatial effects. The footer shows only current actions. Read-only rows remain
legible with no native activation, and scrollbars show additional content.

The controller opens without grabbing system input; only the active preview
window consumes its actions. The global controller bridge is not modified.
The session page is an explicitly labelled interaction placeholder. Opening the
panel prevents actions reaching that placeholder; it does not prove isolation
from RetroArch or Moonlight in another process.

The opt-in [agent control tool](../../docs/REMOTE-CONTROL.md) accepts bounded taps
and verified window captures over local IPC or temporary restricted SSH. It checks
peer UID, session, binary and sequence; normal startup has no endpoint. Revision
11 adds `probe-r46h.sh --remote` and passed actual SSH/ARM64-container UI tests.
No device endpoint/key was installed. Real editor/PIN captures remain blocked;
`--test-input-capture` allows only the labelled disposable keyboard test page.
Control captures and performance profiling remain separate runs.

On a host, volume and brightness are preview values. Favorites, those values, reduced
motion, font size, HUD visibility and idle dim timing are saved atomically to
`state/preview.json`. Versions 1/2 migrate to schema 3 on the next write; stable
application favorites are separate from the old demo indexes.
Save failure retains the
in-memory change, displays an error and blocks the attempted settings/panel or
window exit until retry succeeds. An unreadable/invalid existing file is never
overwritten. No Wi-Fi credentials or host-sensitive state are read or stored.
Revision 14 adds an explicit [temporary device-settings mode](DEVICE.md) for
real backlight/CPU readback and writes, power requests and saved Wi-Fi management.
Ordinary R46H previews read actual state but do not offer simulated device controls.

The [performance/power plan](../../docs/PERFORMANCE-POWER.md) owns settings
semantics and the next CPU, swap, real power and global-overlay gates. The HUD
uses real process CPU/RSS and UI submissions. The shared Wayland session adds
[game buffer submission metrics](../gaming-wayland/HANDHELD.md#game-frame-metrics);
its bounded remote wait does not require the HUD. These metrics do not establish
LCD refresh or GPU render time. Unsupported device
operations show unavailable; memory apply uses a separate guarded CLI.
Qt keyboard entry is bounded and marked sensitive to
disable Pinyin user-dictionary learning; text is cleared on exit.

## Linux virtual keyboard and tuning drafts

```sh
mainline/gaming-shell/build-keyboard.sh
mainline/gaming-shell/build-linux.sh
# Inside the extracted ARM64 experiment, on EGLFS or an offscreen test backend:
R46H_VIRTUAL_KEYBOARD=1 ./shell-client.sh --scene input
PYTHONDONTWRITEBYTECODE=1 python3 mainline/tests/test-shell-tuning.py
```

`build-keyboard.sh` pins Qt Virtual Keyboard 6.8.2 source and builds its English,
Pinyin and arrow-navigation modules in a disposable ARM64 container. Network
access is used only for dependency setup; compilation is offline. The container
is removed afterward. Its Docker storage and all archives/logs are external.
The runtime includes Qt/Pinyin license notices and a Chinese fallback font;
the corresponding Qt source archive remains alongside it. It is opt-in on
Linux; do not force the input-context plugin into a Wayland client before the
compositor input-method path is selected. No macOS virtual keyboard is bundled.

`tuning.py` outputs a read-only Linux CPU/memory snapshot. `--kernel-config`
accepts a retained config; `--root` allows an isolated fixture. For offline draft
validation use `--snapshot SNAPSHOT.json --validate PLAN.json`. CPU entries use
`{"policy":"policy0","preset":"custom","governor":"schedutil","min_khz":408000,"max_khz":816000}`;
those frequencies illustrate syntax, not an accepted R46H range. The outer object
is `{"schema":1,"cpu":[...]}`; optional `zram` contains `size_mib` and `algorithm`.
The command never changes frequencies, loads modules or enables/disables swap.
Disk-swap planning is explicitly refused pending identified-storage checks.
Unknown fields and frequency overrides attached to a non-custom preset are
rejected rather than silently discarded.
The current v0.17 device has no Python interpreter. Its first capability sample
used serial sysfs/proc reads and host-side validation; do not install Python or
rewrite the base just to run this diagnostic.

`r46h-cpufreq-default` is the user-approved product-policy candidate for the
nearest supported 1 GHz OPP. It keeps `schedutil`, lowers the CPU range from
600--1296 to 600--1008 MHz and leaves GPU devfreq unchanged. The adjacent oneshot
unit orders it before the frontend. Host tests plus current-v0.17 target
apply/readback, GTA/thermal use and warm-reboot persistence pass. It is not in the
frozen v0.18 image; integrate it only in the next p2 successor.

The performance HUD reuses the existing device sample to show current GPU MHz on
the thermal/status line. It adds no sampler and does not claim GPU utilization.
R64 target composition showed `GPU 200 MHz` matching the sampled 200000000 Hz.
A subsequent live minimum-frequency raise caused a Panfrost power-domain panic;
do not repeat it as a HUD test. Operator reset restored the default policy and
cleanup passed; the first capture remains valid machine evidence.

## Checks and evidence

`tests/check.cpp` runs the actual QML view through Qt Test and exercises the
actual SDL virtual-controller API. It checks directional navigation, focus
return, modal isolation, favorites, clamping, persistence, malformed state,
failed-save retry, ignored repeat confirmation, stick deadzone/repeat/release,
and absence of continuous idle repaint. It also checks telemetry lifecycle,
versioned preferences, settings/text focus and idle dimming. Revision 6 adds
permission-denied directory reads, connected-controller handover, and the real
Hide Keyboard action followed by reopening and typing. Permission denial runs
as an unprivileged user, including a separate ARM64 check. The packaged Linux
keyboard check also covers arrow input and Pinyin composition; exact counts
belong in the cache receipt.
Revision 11 adds Y deletion, START confirmation, same-row horizontal keyboard
wrap and handheld-only hints. The packaged keyboard test checks both wrapping
directions, Unicode deletion and confirmation; R17 attended delivery passed; see the device record.
Revision 12's [component contract](controls/README.md) adds native template controls,
shared page/focus motion, choice confirmation and 2,000-row virtualization checks.
It does not establish changed-candidate R46H pacing or device settings.
Revision 13 fixes native/accessibility activation of the wrong row, uses an
in-window Qt modal popup for keyboard isolation and pauses indeterminate progress
when a window hides/minimizes. The focused checks cover reopening/restoration,
scaled bounds and failed-save retry; results and hashes remain in the receipt.
Revision 14 adds device readback, backlight/CPU rollback, power confirmation and
saved Wi-Fi parser/argument checks. The [device contract](DEVICE.md) owns the
lease/memory CLI checks and their still-open target boundary.
Revision 15 adds application-list selection/manual fallback, actual mount
readback, numeric remote metrics and bounded recording. Its remote-streaming
supervisor test runs actual Qt through normal/error fake-worker returns and
checks fresh IPC generations. The shared choice regression now checks a nonzero
initial selection after model creation, including the focus outline position.
Revision 16 adds nearby Wi-Fi selection, masked password entry, optional saved
profiles and confirmed removal. `network-check` uses an isolated Linux D-Bus with
a fake NetworkManager; native UI checks cover privacy/cancel/confirmation. See
the [network contract](DEVICE.md#wi-fi-management) for scope and target gates.
Revision 7 adds left-first settings entry, interrupted focus movement, value
editing/left-return, contextual actions, 120% font layout and HUD avoidance of
active controls, actual switch clicks/state bindings, and interrupted page changes.
The current two-level navigation regression additionally covers unloaded detail
pages during rapid list movement and cancellation while asynchronous creation is in flight.
The same ARM64 package then passed 39 application actions on exact v0.18 with
binary SHA-256 `07758b8eda1a92fe59d58d9c4abad62c2b4c8114a26c378408c6ed01b7279fa4`.
Captured list/detail states cover Settings, Neo and PortMaster; the transient
session ended at status 0, restored ES-DE and left zero failed units/ext4 errors.
Evidence is under `mainline/out/.cache/r46h-two-level-device-20260920/evidence/`.
This is Qt/DRM machine evidence, not physical controls or LCD acceptance.
`test-shell-control.py` separately drives a real shell process, verifies before/
after PNGs, privacy refusals, stale-target rejection, socket cleanup and repeated
navigation. The Linux builder runs it against the relocated package and checks
cross-UID refusal; its temporary IPC uses the container's `/run` while artifacts
and state remain on external storage.
The packaged keyboard checks the accent color and reduced-motion
binding as well as input, Hide/reopen and Pinyin at the larger font size.
Since revision 4, it runs beside the package's `qt.conf`, excluding the SDK's fallback
QML imports. Removing `Qt.labs.folderlistmodel` makes this check fail; that module
and its library/license are now included in the full shell package.

`--scene home|library|settings|about|quick|session|performance|controller|power|input|neo|ports|usb --capture /absolute/path.png`
captures only this window and exits. The command requires a running window
system or a selected offscreen Qt backend. ARM64/software screenshots and
native Mac captures were reviewed. The Mac used Metal on Apple M4; these are
not LCD/Panfrost evidence.
Input-test captures also require `--test-input-capture`, even when empty;
real host editors and pairing PINs always remain private.
For repeatable navigation/100%/120% screenshots, create an external output
directory and set `R46H_UI_CAPTURE_DIR` when running `run.sh --check`.

The [current shared candidate](TOOLS.md#current-shared-candidate) links to R78's
frozen source, package and checks. R36 remains the accepted device proof for
status, Neo persistence and the catalog. Older `.cache/r46h-shell/receipt.json` and
closure logs describe their named historical revisions; they do not describe a
new build automatically. The device preflight still checks dynamic-library closure
before starting a candidate. The old Qt bundle's baseline
libraries/licenses are reused; the Moonlight executable is replaced by this
prototype and the optional keyboard/font runtime added. This is an experiment package, not a
new rootfs release or a two-build reproducibility claim.

The earlier prototype's isolated host Wayland check used Weston 14.0.2,
Qt Wayland 6.8.2 and Pixman:

```sh
# Inside a disposable Linux environment with Weston and Qt Wayland installed:
mainline/gaming-shell/tests/check-wayland.sh /absolute/r46h-shell /external/output
```

It runs two independent Qt clients and removes its compositor/socket on exit.
It has no DRM device, host input or network requirement. The retained result is
`WAYLAND_CLIENTS_PASS`; that historical test does not prove overlay stacking,
hardware decoding or global routing. R31's later result is linked above. It was not repeated for the expanded settings/
keyboard revision; the previous source snapshot and receipt remain named
evidence. The temporary container was removed afterward.

Revision 6 fixes the four findings from the 2026-09-08 review. An inaccessible
settings directory now locks saving rather than silently loading defaults;
restart after fixing access to re-read the preserved settings. Hiding the Qt
keyboard exits and clears the input page after the key callback completes.
Removing the active controller selects an already-connected eligible pad.
The Wayland builder records current container package versions separately from
retained target versions. These fixes require their own R46H repeat; the
performance/physical observations below belong to revision 5, retained as fallback.

## UI performance

The operator reported roughly 14 updates/s in the ordinary interface and below
10 in the keyboard. The HUD now labels its counter “界面更新 / 次/秒”: a static
interface does not repaint continuously, so this counter alone is not animation
FPS. The report was also reproduced with continuous automated activity.

On the same v0.17 cold boot, Qt 6.8.2 used OpenGL ES 3.1/Mesa 25.0.7 Panfrost,
1024×768 at 60 Hz, without MSAA. Each measured phase ran for about ten seconds:

| Continuous workload | Baseline submissions/s | Cached candidate submissions/s |
| --- | ---: | ---: |
| Alternating card scale animation | 19.7 | 58.9 |
| Same animation with HUD | 19.5 | 59.8 |
| Opening/closing quick panel | 18.0 | 59.4 |
| Alternating keyboard navigation | 20.3 | 60.0 |
| Same keyboard navigation with compact HUD | — | 60.1 |
| Two-level Settings category focus (v0.18, two runs) | 29.5–29.6 | 57.2–57.5 |
| Same Settings focus with HUD (v0.18, two runs) | 29.9 | 58.5–59.0 |

Cards' static artwork/text, the HUD, quick panel and keyboard key layout use
Qt's item layer cache. The input page hides the covered desktop; the window clear supplies its opaque
background. GPU buffer-upload waits were visible in diagnostic GL-call and
ioctl traces. Depth/render-loop/batch changes, removing card clipping, and
experimental buffer-update interception did not improve final throughput and
are not enabled. No Qt/Mesa library, CPU policy, kernel or installed frontend
was replaced. Cached layers trade some texture memory for less repeated work.

This measures submitted frames during synthetic activity, not physical display
latency or maximum rendering capacity. The operator found the intermediate
30/s keyboard candidate still visibly slow; it was not accepted. The final
keyboard layout cache is measured separately above; the operator confirmed
much smoother movement, subjectively above 40 FPS. That is not a locked-60
LCD/frame-pacing claim. The final input HUD was also observed around 58
updates/s during continuous navigation. Its diagnostic injects alternating directions every 16 ms;
normal held-controller repeat is 100 ms. Manual controls/visual acceptance and
long-run memory/power costs remain separate. Raw timing traces include waits
and are not pure GPU execution timings.

```sh
# Native preview (no packaged keyboard on macOS):
mainline/gaming-shell/run.sh --profile-ui
# Identified device, after the normal receipt-bound staging/preflight:
/run/r46h-shell-probe/probe-r46h.sh --profile BINARY_SHA256
# Optional detailed Qt timing; omitted by default to avoid per-frame logging:
QSG_RENDER_TIMING=1 /run/r46h-shell-probe/probe-r46h.sh --profile BINARY_SHA256
```

The revision 7 HUD is a horizontal panel above the main content, retaining its
CPU history. During text entry it becomes compact above the input field;
opening the quick panel moves it into the inactive left area. Metric definitions
and the toggle are unchanged. The two-level Settings category list is cached
independently of its moving outline. On v0.18 this reduced Qt's measured average
render time from 20.53 to 7.46 ms without HUD and 18.91 to 1.03 ms with HUD;
two repeat runs produced the table ranges above. Evidence is under
`mainline/out/.cache/r46h-profile-device-20260921/evidence/`; physical LCD motion
and handheld input latency remain open.

The keyboard adapter uses Qt 6.8.2's internal `keyboardLayoutLoader` cache,
default-style `navigationHighlightColor`, and `noAnimations` binding. The packaged
English/Pinyin test checks all three. Revalidate this small adapter when upgrading
Qt; the upstream keyboard layout and input implementation are unchanged.

The final device window captures of input/HUD and controller-test layout were
reviewed. Base/GPU/storage checks passed, all three frontend/input/volume
services had zero restarts, and each completed preview/capture restored ES-DE.
The operator did not separately report the revised tester's physical Select
exit; its source test and visible exit hint passed. Target staging and transfer
servers were removed, followed by sync and serial-confirmed controlled poweroff.

The profile now reports p50/p95/max frame-submission intervals as well as counts.
Intervals include intentional idle gaps between inputs: a 90 ms focus move at
a 100 ms input cadence is not continuous animation, and an average below 60 is
not itself proof of slow rendering. The bounded interval collection is enabled
only by `--profile-ui`; normal frames retain the existing cheap counter. LCD
presentation and end-to-end input latency still require device evidence.

The profile restores the original motion/HUD preferences and exits. The existing
transient-unit deadline and frontend recovery still apply. Qt diagnostics go to
`state/runtime.log` inside the staged package; preserve it before another run
replaces it. The session's `performance-20260907T135312Z/receipt.json` under the
external shell cache owns artifacts, comparisons, health and remaining gates.

## Prepare an attended device run

The 2026-09-07 revision 3 run passed exact v0.17/kernel/card identity, base and
storage smoke, package transfer SHA-256, preflight and EGLFS startup. The Qt
process held `card0` and Panfrost `renderD128` descriptors. A separate short
transient-unit test killed a TERM-resistant descendant and unloaded the unit.
The actual preview exited with `SHELL_END status=0 frontend_restore=0`; ES-DE
returned as a running process, all three frontend/input/volume services were
active with zero restarts, and post-run health stayed clean.

The 106 process samples cover 118.54 seconds. Excluding startup's first ten
seconds, one-core CPU median/p95 were 1.8%/2.7%; RSS peaked at 142.7 MiB.
Operator activity was not labelled, so these are not a navigation benchmark,
game FPS or frame-time measurements. The later attended run below owns LCD,
control, HUD and basic keyboard-input observations.
Global overlay and shared-display input isolation were not exercised.

Session evidence is under `mainline/out/.cache/r46h-shell/attended-20260907T125419Z/`;
its separate receipt owns hashes and boundaries. The host receipt still freezes
the build inputs; later result prose does not change the tested binary. Target
tmpfs staging and the host transfer server were removed, and serial confirmed
filesystem detach and `Powering off.`. BOOT/rootfs, CPU/swap policy and installed
services were not changed.

The attended `manual-20260907T131502Z` run connected after power-on, so it does
not provide another cold-boot trace. The operator accepted the LCD and visual
ES-DE return, but initially reported no controls. The package's SDL 2.33.0
enumerated the raw `gpio-keys` controller before `R46H Combined Gamepad`; Qt
opened the raw event node. The corrected device probe restricts SDL to the
bridge's VID/PID (`0x5246/0x0048`). A same-library diagnostic then enumerated only
the combined pad, Qt opened its node, and the operator accepted controls and
picture. The bridge and its mapping were not changed.

The same operator accepted HUD display, then found the keyboard unavailable.
An offscreen diagnostic on R46H identified missing `Qt.labs.folderlistmodel`.
Revision 4 fixes packaging and isolates its QML checks from the SDK. All previous
payload files are unchanged except the corrected probe; additions are `qt.conf`,
the QML module and its library/license. Target dependency checks and actual module
loading passed, and the operator confirmed text input. Pinyin interaction was
not separately confirmed on the device. The session receipt records exact scope,
observations and hashes; revision 3 remains named evidence, not the current package.

The operator also found the former controller-test exit hard to discover.
The current source makes Q/Select return directly to the settings sidebar;
A/B remain test inputs. This is separate from controller event delivery.
The operator also confirmed HUD closing and input exit via B or Hide Keyboard.
All five
bounded previews exited normally and restored the frontend process; post-run
base/GPU/storage checks passed with zero service restarts. The final tmpfs state
and transfer server were removed, and serial confirmed controlled poweroff.
The full session receipt is
`mainline/out/.cache/r46h-shell/manual-20260907T131502Z/receipt.json`.

`build-linux.sh` builds/tests in the pinned Moonlight ARM64 toolchain and packages
`r46h-shell-preview-arm64.tar.gz` using the hash-bound Qt baseline. It mounts
source read-only and uses external build/package staging with no network.

1. Rediscover serial and listen before cold power. Verify the accepted v0.17
   identity through the [device contract](../rootfs-debian13-gaming-v17/README.md#persistent-device-acceptance).
2. Transfer the receipt-bound tar to a task-owned `/run/r46h-shell-probe`; verify
   the transfer hash before extraction, then set the scope to `ark:0700`.
3. `probe-r46h.sh --check BINARY_SHA256` checks exact kernel/root UUID/card CID,
   card size, ROM read-only state, frontend services and binary/dependency identity.
4. With the operator ready, `--run BINARY_SHA256` pauses ES-DE, runs the preview
   via EGLFS/OpenGL on VT2 with a 300-second runtime limit and up to 10 seconds
   for forced cleanup, then restores the frontend. A disposable systemd unit
   contains the full process tree, including `setsid` descendants. No unit file
   or boot service is installed; sound controls and compositor remain untouched.
   This EGLFS probe enables the bundled virtual keyboard for the input page.
5. Capture LCD/input observations and process/GPU/frame-time evidence. Confirm
   ES-DE recovery, remove the owned tmpfs payload, run health checks, sync and
   power off with serial confirmation when unattended.

For temporary real settings, use the separate [device mode](DEVICE.md) after
preflight. Do not promote the preview based on host checks: the latest shared
machine result is limited, and physical controls, streaming, saves and endurance remain open.

The second review corrected ineffective negated Bash preflight checks, checks
argv rather than PPSSPP's renamed process label, and verifies frontend activity
after restart. `test-gaming-probe.py` exercises busy/check-error/missing-library
refusal and recovery failures with mock services. Transient-unit cleanup,
LCD recovery and corrected hardware input now have the device evidence above.

Keep the existing v0.17 TF rootfs for this test: the private userspace payload's
dependency closure matches it. Do not rewrite BOOT, p2 or p3 for a preview.
The [zram kernel candidate](DEVICE.md#memory-experiment-cli) is built separately;
its fallback/boot gate remains open and it is not a replacement base image.

## Tool applications

[Tools](TOOLS.md) owns the independent Neo, PortMaster and USB pages, safe save
handling and the bounded Neo handoff. New pages follow the [shared UI defaults](controls/README.md);
page-local geometry/typography overrides are no longer the default.

## Optional persistent preview state

`R46H_SHELL_STATE_DIR=/home/ark/.local/share/r46h-preview` opts an identified-device
probe into persistent preferences, tools/saves and Sunshine client state. The
probe admits only that fixed path and checks it as `ark` before pausing ES-DE.
The wrapper rejects noncanonical/symlink paths and requires an owned 0700 directory.
The same `--state-dir` is passed to GUI, native and streaming workers, so requests
and client identities cannot silently move to a different directory on handoff.
Runtime logs/control sockets remain in their existing temporary scope.

This is opt-in, not a boot-service installation. Do not put installed games or
long-term saves in the default `/run` state: that location is a limited memory
filesystem. Persistent client state contains private pairing material; do not
include it in Git, screenshots or public evidence, and do not remove it with the
temporary payload. Host wrapper checks cover both worker paths and restart reuse;
R35 proved Neo state across a warm reboot. Settings, pairing, port saves and upgrade
persistence remain gates.
