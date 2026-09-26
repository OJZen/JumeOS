# Mainline tests

Run the smallest test that owns the changed behavior. Generated packages and
large local fixtures remain below ignored `mainline/out/`; they are not source
or current hardware evidence.

`test-project-docs.py` guards the mandatory onboarding documents, all source
Markdown links, checkpoint synchronization, frozen-history banners, the
rootfs/bring-up indexes and selected readability budgets. AGENTS.md links to
the state owners instead of carrying a checkpoint. Run it whenever an entry
document, status owner or runbook index changes.

## Current review gaps

The 2026-09-05 host review found five existing failures: two in the standalone
[ES-DE screen overlay](../gaming-remote-screen-es-de/README.md), plus the
screenshot identity checks in `test-debian13-gaming-rootfs-v08.py`,
`test-debian13-gaming-rootfs-v11.py` and `test-debian13-gaming-rootfs-v12.py`.
The latter tests transform the current screenshot source but compare it with
historical pinned hashes; the anchored process-guard change altered those
bytes. Preserve the pins and use version-bound inputs if these historical
paths need repair. These failures do not revalidate or revoke already
published images. P2 v0.16/v0.17 host checks pass separately; v0.18 owns its
new package/repack path.

Those checks do not establish that each ES-DE core is discoverable through
RetroArch's configured core directory. The
[v0.17 device check](../rootfs-debian13-gaming-v17/README.md#persistent-device-evidence)
found missing save-state entries despite installed save-capable metadata.

The R16 Mac run could not activate its native test window in
`keyboardNavigationAndModalIsolation`, including a focused retry. The same
keyboard flow passed with Qt offscreen; other native checks and the ARM64 suite
passed. Keep this window-system limitation separate from a clean native full-run
claim and from R46H input proof; the R16 receipt retains both results.

## Test ownership

`shell-check backgroundTasksAndClose`, `gaming-wayland/test-input-policy.cpp`,
`test-input-router.py` and `test-tasks.py` own the [task manager](../gaming-shell/APPLICATIONS.md):
four-process lifecycle/input isolation, local thumbnails, physical synthetic Select
shortcuts, cooperative window-close refusal/acceptance and forced cleanup. Real
Wayland/evdev host fixtures do not establish R46H physical controls or memory stability.

`gaming-files/build.sh` compiles ARM64 Files/Text, runs disposable file/editor/
USB D-Bus and GUI fixtures, and checks the packaged runtime with real synthetic
PCM. `shell-check filesEntriesAndPrivacy` owns launcher routing/capture privacy.
These [host checks](../gaming-files/README.md) do not prove physical USB or A/V.
`gaming-files/test-transfer.py` adds real HTTP with synthetic Wi-Fi status, upload/
download integrity, pairing, path/origin guards, loss/EOF cleanup and limits;
`files-check transferQrAndLifecycle` decodes QR and checks the native controller.
The [Transfer runbook](../gaming-files/TRANSFER.md) separates passed target Wi-Fi
checks from remaining phone QR, physical controls and USB acceptance.

`test-gaming-probe.py` executes the shell/Embedded-stream launchers' actual Bash
preflight and recovery blocks with mocked processes/services: busy clients,
PPSSPP argv, check errors, missing libraries, cleanup failure and inactive
frontend. It also checks the attended Ports duration/worker route. It does not
prove target systemd lifecycle or LCD restoration. The Ports guard additionally
creates its private runtime log directory on a fresh `/run` and refuses a link.

`test-wayland-probe.py` checks the shared-display launcher's busy/error guard,
transient-unit failure, exact leftover seat-socket cleanup and frontend recovery
using host mocks. Its provider check queries current container versions while retaining target
version references. The bundle builder separately runs the actual Weston/Qt
headless pair with installed module/plugin directories hidden. Neither check
proves R46H DRM, global overlay policy or gamepad isolation.

The same probe test leaves a real Unix socket under the exact session `runtime.*`
directory and verifies the outer stop path removes it before frontend recovery.

The newer [handheld policy checks](../gaming-wayland/HANDHELD.md) use real
Weston composed pixels and separate synthetic uinput/evdev devices. The latter
exercises grabs, neutral handoffs, L3/R3 chords, queue overflow and disconnect
cleanup inside a disposable Linux container. A separate actual Qt/Weston/SDL run
exercises mapped game input, global quick controls, neutral ownership, resident
HUD and cancel/confirm/return. It also checks composed private-entry cancellation
and bounded RPC/CLI game input, including physical takeover and connection loss.
The packaged session also runs as an unprivileged user, checking delegated-handle
isolation, compositor-loss cleanup and the original two-window profile.
They also require game-frame readiness while the HUD is hidden. Physical
gamepad/global-panel behavior and the PC stream remain open.

`gaming-wayland/check-neo.sh` adds real RetroArch/FBNeo under headless software
GL: read-only Metal Slug inputs, routed shortcuts, nontrivial save/load frame
comparison and same-session return/relaunch. The [Neo host runbook](../gaming-wayland/HANDHELD.md#real-neo-host-check)
owns its inputs and limits; this does not exercise the target-only native worker.

`gaming-wayland/check-ports.sh` uses the hash-pinned source-built GTA III/VC and
Mono/Stardew engines in the shared desktop. `test-local-port-process.py` separately
verifies real signal/group cleanup, fast requested stops and a slow self-bound flush
with synthetic children in a disposable Linux container. Neither check proves
target gameplay or durable native saves.
`test-mono-compat.py` keeps unrelated lookup unchanged while checking provider-local
ELF resolution for Mesa GLX/EGL/GBM and Panfrost DRI names.

`gaming-wayland/check-remote.sh` checks the packaged SSH helper and QCore relay
against the shared desktop and a real SDL consumer. It covers strict trust,
composed capture, timed input, early disconnect release and listener/state cleanup.
The container substitutes the hardware seat and diagnostic application list;
the actual R46H network/seat path remains open.

`test-moonlight-qt-client.py` checks the isolated
[Qt candidate wrapper](../gaming-moonlight/QT-CANDIDATE.md), including private
state directories, paths with spaces, argument forwarding and exit status.
It runs a fake executable and does not establish Qt or hardware compatibility.

`test-moonlight-qt-patch.py SOURCE OUTPUT [--fixture ANNEX_B_H264]` runs inside
the pinned ARM64 Qt builder documented in the same runbook. It compiles the
actual patched SPS/quit predicates and buffer writer, and executes the QML
handlers in QJSEngine. It checks CLI error/normal exit and preserves the GUI
path. An optional artificial stream produces old/preserved SPS outputs for
offline decode comparison. This does not prove SDL input delivery or R46H A/V.

`test-easyroms-deploy-fixture.sh` and
`test-userspace-probe-deploy-fixture.sh` use the exact local fixture at
`mainline/out/test-fixtures/legacy-v08-deploy`. Its seven-file closure is pinned
by [`fixtures/legacy-v08-deploy.sha256`](fixtures/legacy-v08-deploy.sha256).
The BOOT files came from the old v0.3 stage backup and the raw prefix/layout
files from the old v0.4 stage receipt. They are test inputs only and must not
authorize media writes or describe the current R46H state.

`test-r46h-gaming-remote-screen.py` owns the host contract for guarded
screenshot support: exact accepted Ozone/FBNeo predecessor hashes, pinned hardened
AArch64 KMS reader, no-argument sudo boundary, no frontend replacement,
rollback, strict SSH transport and publish-before-cleanup behavior. It does not
itself prove that an installed product frame matches the physical LCD or gameplay.

`test-r46h-gaming-remote-screen-es-de.py` owns the historical two-file overlay
contract. Its two known failures and the standalone rebuild boundary are in the
[overlay runbook](../gaming-remote-screen-es-de/README.md). Do not update only
the test expectations or lower the installer hash guard to make it pass.

`test-r46h-gaming-remote-input.py` owns the fixed ES-DE keyboard map, one-shot
uinput lifetime, forced-command/sudo allowlists, pinned AArch64 build and exact
p2-only rollback contract. It does not prove that ES-DE consumed an action.

`test-r46h-gaming-ozone-fbneo.py` owns the host contract for the Ozone switch,
required `gl` video-driver delta, single-entry Neo-Geo playlist, pinned
reproducible FBNeo subset, retained Metal Slug ROM identity, deterministic
UniBIOS core options, persistent bounded volume state and exact p2-only
install/rollback contract. Host load and target null-I/O frame capture do not
prove LCD output, physical navigation, audio, frame pacing or controls.

`test-r46h-gaming-fbneo-full.py` owns the alternate-lock guard, pinned full
FBNeo AArch64 artifact, full CPS startup audit and retained content identities.
It does not turn known incomplete ROM sets into passes or prove gameplay or
R46H behavior.

`test-r46h-gaming-ppsspp.py` owns the pinned PPSSPP source/submodule closure,
reproducible AArch64 core/assets bundle and exact six-file null-I/O startup
audit. It does not prove GLES, LCD, audio, controls, pacing or PSP gameplay.

`test-r46h-gaming-flycast.py` owns the pinned Flycast source/submodule closure,
reproducible AArch64 GLES2 core and exact 14-file software-EGL/HLE startup audit.
It does not prove Mali/LCD output, audio, controls, saving, pacing or gameplay.

`test-r46h-gaming-es-de.py` owns the ES-DE source/runtime lock, target ABI
closure, seven-system/core allowlist, read-only p3 metadata/media mapping,
KMS/input/audio launcher, p2-only install/Ozone rollback and the reversible
visual-profile overlay. It does not prove ES-DE display, controller GUID, game
launch or performance on R46H.

`test-debian13-gaming-rootfs-v08.py` owns the host-only consolidation contract:
exact v0.7 predecessor and five product inputs, v0.8 UUID-bound launchers,
direct ES-DE/FBNeo/screenshot/input content, no embedded operator key or ROM,
separate restricted-key pairing and reproducible networkless composition. It
does not prove a media write, boot, LCD motion or physical controls.

`test-debian13-gaming-rootfs-v09.py` owns the minimal full-FBNeo successor:
exact v0.8 predecessor and inputs, one added Arcade system, UUID-bound identity,
restricted-key pairing and a networkless bounded overlay. It does not prove a
media write, boot, Arcade compatibility or physical behavior.

`test-debian13-gaming-rootfs-v10.py` owns the CPS1-only successor: exact v0.9
predecessor and identity inputs, one audited system/link, unchanged full core,
UUID-bound launchers and networkless composition. It does not prove media or
physical gameplay.

`test-debian13-gaming-rootfs-v11.py` owns the media-only successor: exact v0.10
predecessor, pinned Arcade/CPS1 manifest and full 6,008-link image readback. It
does not prove the imported p3 contents, a media write or physical display.

`test-debian13-gaming-rootfs-v12.py` owns the filtered CPS successor: exact
v0.11 predecessor, eight hidden audit failures, two settings changes and full
6,082-link readback. It does not prove a media write or physical gameplay.

`test-debian13-gaming-rootfs-v13.py` owns the PPSSPP successor: exact v0.12
predecessor, pinned core/assets, one six-entry PSP system and full 6,087-link
readback. It does not prove a media write, GLES, audio, controls or gameplay.

`test-debian13-gaming-rootfs-v14.py` owns the Flycast successor: exact v0.13
predecessor, pinned core, one 14-entry Dreamcast system, private writable state
and full 6,115-link readback. It does not prove a media write or R46H behavior.

`test-debian13-gaming-rootfs-v15.py` owns the Game Gear successor;
`test-debian13-gaming-rootfs-v16.py` owns the 10 ms input and anchored capture
overlay; `test-debian13-gaming-rootfs-v17.py` owns exclusive custom systems and
retained runtime identity; `test-debian13-gaming-rootfs-v18.py` owns the exact
polkit packages, ark-only rule and external-scratch ext4 repack. These are host
checks; actual ES-DE system loading, transport, media and operator observations
remain separate gates.

## Qt desktop preview

[The shell check](../gaming-shell/README.md#checks-and-evidence) builds/runs the
actual QML view and SDL virtual controller through Qt Test. Native Mac and ARM64
host checks cover navigation, modal isolation, atomic preview state and failure
recovery. The separate Weston/Pixman check proves concurrent Wayland clients,
not R46H acceleration, actual game overlay stacking or global input isolation.
The expanded check also covers telemetry stop/reset, old-state migration,
settings/input focus, idle dimming and the optional Qt keyboard's navigation
and Chinese composition. `test-shell-tuning.py` checks read-only fixtures and
CPU/zram draft rejection; it performs no sysfs or swap writes.

`test-shell-control.py --binary ABSOLUTE_SHELL_PATH` drives the actual opt-in
local endpoint. It covers safe-state observations, verified Qt PNGs, one-shot
actions, stale session/binary/sequence rejection, input privacy, failed saves and
normal socket cleanup. `--cycles` adds repeated navigation with RSS observations;
`--evidence` retains traces/captures under external `mainline/out`. This proves
application actions, not SDL/kernel input or device display behavior. The ARM64
builder also runs it against the relocated package with a cross-UID refusal check.
`test-shell-record.py` additionally checks the bounded, stable-target
`wait-game-frame` predicate used before a composed game capture.

`test-shell-ssh.py --host IP --port PORT --identity PRIVATE_KEY --known-hosts FILE
--binary ELF_SHA256 --evidence DIRECTORY [--keyboard]` runs one short flow against
a prepared isolated key-only server and actual Qt app. It covers PNG/action
roundtrips, stale actions, wrong host keys, paths with spaces, arbitrary-command
and forwarding refusal. The keyboard option covers the explicit test-page capture
exception, typing/Y/START and capture refusal in real editors. The
[remote runbook](../../docs/REMOTE-CONTROL.md) owns temporary R46H deployment;
container success does not prove target SSH, kernel input or LCD output.

`test-shell-applications.py --binary ABSOLUTE_SHELL_PATH` is a short new-feature
flow: configured scrolling, stable favorites, literal argv, foreground launch,
normal return and failure recovery. Routine builds use brief control checks;
large repeated UI loops are explicit diagnostics only.

`shell-check standardControlsAndChoices` uses `tests/ControlsGallery.qml` and a
real 2,000-row table model to verify native control behavior, font scaling,
viewport-limited delegates, idle redraw and choice/save-failure semantics.
`streamingNavigation` covers the same choice control in Moonlight. See the
[control contract](../gaming-shell/controls/README.md) for APIs and captures;
the real-process control test also verifies popup isolation through the agent API.

`nativeRowActivationUsesItsOwnTarget`, `choiceKeyboardFocusStaysModal` and
`progressAnimationFollowsWindowVisibility` guard the second-review failures:
wrong-row accessibility/native clicks, keyboard escape to background controls,
and animation while hidden. They include outside-click dismissal, same-window
popup/scaled bounds, failed-save retry and hide/minimize/restore behavior.

`deviceSettingsReadbackAndGuards` uses a constructor-only proc/sysfs fixture for
real state parsing, CPU ranges/governors, low-voltage/temperature refusal,
brightness dim/restore, failed-write rollback and power-dialog exits. It also
checks the top-right battery/charge text and normalized Wi-Fi link quality.
`savedNetworkProfilesAndLiteralArguments` runs a fake nmcli process to check
escaped profile names, known UUIDs, literal up/down arguments and read-only refusal.
`test-device-lease.py` executes the actual recovery/power-exit shell blocks against
owned files and mocked services; `test-memory-control.py` covers sizes, memory
reserve and ownership refusal. No host check changes sysfs, NetworkManager,
power state or swap. See the [device gate](../gaming-shell/DEVICE.md).

`streamingApplicationListAndFallback` covers bounded upstream-style list parsing,
literal names, cancellation, host-cache invalidation, shared choices and manual
editing. Mount readback tests refuse a missing mount instead of reporting its
parent volume. `test-shell-record.py` checks numeric-only JSON/CSV, private output,
bounds and retained partial samples after a disconnect or process restart.
The real-process control check also records a short sample through actual IPC.

`test-shell-handoff.py --binary ABSOLUTE_SHELL_PATH --evidence EXTERNAL_DIRECTORY`
runs the actual Qt desktop/supervisor around a fake stream. It covers normal/error
return, three distinct IPC generations, stale-action refusal and literal argv.
The Linux builder runs it against the relocated package. It does not exercise
real Sunshine, SSH continuity, DRM, audio or the physical exit chord.

`network-check` validates scan parsing/password boundaries and runs the real Qt
D-Bus adapter against a private test daemon and fake NetworkManager. It covers
message types, volatile/disk options, open/PSK settings, initial and signalled
activation, permission denial, changed APs and deadline handling. Native systems
without dbus-daemon skip that wire test; the ARM64 builder runs it. No actual
network, saved password, system bus or host NetworkManager is touched.
`test-shell-network-policy.py` pins the exact target-tested polkit rule and its
three ark-only NetworkManager actions. The v0.18 rootfs test owns host image
integration; media and reboot/new-password behavior remain separate.
`wifiChooserPasswordPrivacyAndForget` checks the shared chooser, password masking,
capture-refusal state, cancellation/clear, remember switch and confirmed UUID
removal. Actual device permissions, DHCP, reconnect and persisted secrets remain
in the [combined acceptance route](../gaming-shell/DEVICE.md#combined-acceptance-route).

### Independent tools and application discovery

`test-shell-tools.py --binary ABSOLUTE_BINARY --evidence EXTERNAL_DIRECTORY`
drives Neo/PortMaster/USB through real local IPC, uses disposable save fixtures,
checks non-overwrite/backup/export/save failure/modal routes and captures 100/120%
fonts. `gaming-shell/tests/tools-check.cpp` covers asynchronous inspection and
HID encoding. `test-gaming-probe.py` includes the bounded native supervisor.
`test-moonlight-list.py SOURCE_CPP EXTERNAL_DIRECTORY` compiles and
executes the actual list callback with bounded fake HTTP data. The old callback
fails on empty cached data; the patched callback passes. Real R46H gameplay,
USB enumeration and Sunshine application/input delivery remain separate gates.

`test-portmaster-manager.py --runtime PRIVATE_RUNTIME` uses the real pinned
HarbourMaster with disposable archives: install/update/rollback, traversal/link
rejection, failures before and after index publication, corrupt/link cache repair,
cancel/failure recovery, verified runtime reuse and non-destructive
uninstall. `test-portmaster-ui.py --binary SHELL --runtime PRIVATE_RUNTIME
--evidence EXTERNAL_DIRECTORY` checks actual Qt/worker interaction, 120% layout,
search, instructions and confirmation isolation. `--packaged` requires the
relocated package's default helper locations. Private search text is never copied
into response records; host/PIN/password editors reject the new text operation.
