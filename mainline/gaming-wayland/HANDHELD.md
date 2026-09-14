# Handheld compositor policy

Status 2026-09-14: **R56 CLIPPED HUD + STATUS BAR HOST PASS / R54 GTA HUD-OFF MENU DEVICE PASS / R56 DEVICE + INTRO OPEN / STREAMING DEFERRED**.
This is a separately named candidate over the retained Weston 14.0.2 backend;
it does not replace the device's accepted desktop-shell probe or ES-DE.

`handheld-shell.cpp` uses libweston desktop surfaces to request fullscreen sizes,
keeps unassigned views hidden, and places the registered game below the UI layer.
The controller first claims its own UI process (or its child), then selects an
owned foreground process. Descendant surfaces follow that game's role. Only the
claiming process may change game/panel/overlay/privacy state; commands carry a session
and sequence and reject stale state. The local socket is owner-only inside the
private runtime directory; there is no TCP service or arbitrary command execution.

`capture.cpp` uses Weston's version-locked output-capture protocol to obtain the
actual composed framebuffer through bounded shared memory. It accepts only bounded
32-bit formats and has a poll deadline. Capture authorization admits only the
registered UI/controller process, and defaults to private until explicitly allowed.
An allowance expires after 2.5 seconds and UI-surface removal revokes it. The XML
retains its upstream copyright/license. Framebuffer capture can temporarily disable
hardware planes; it is diagnostic, not a performance recording path.

`check-handheld.sh` compiles and runs only in the isolated ARM64 container. Its two
real Qt clients supply a green game surface and a transparent UI with a yellow
panel. Checks assert actual pixels before/after panel changes, fullscreen geometry,
privacy refusal, wrong-controller/stale-request refusal and UI restoration after
game exit. Evidence: `mainline/out/.cache/r46h-compositor-20260910/`. The source
reference is Debian Weston's 14.0.2 tarball verified against its published SHA-256.

The policy and synthetic-game checks use Pixman/headless; the Neo check below
uses headless software GL. Tests use container-private `/run` for
Unix sockets; Docker's shared host volume is only for code and evidence. Client-only
Qt Wayland plugins are extracted separately instead of installing Qt's compositor.

Ordinary Wayland keyboard focus does not isolate applications reading evdev.
The actual desktop integration below now uses the input broker. Actual
Moonlight/Hantro and physical shortcut acceptance remain separate R46H gates; the limited
Panfrost/capture result below does not authorize replacing the default launcher.

The selected in-game panel shortcut is **L3 + R3**, confirmed by the user on
2026-09-10. Keep Moonlight's existing L1 + R1 exit.

## Unattended device result 2026-09-11

The unchanged v0.17 card cold-booted the v0.15 kernel. UART verified its fixed
CID/root UUID, then authenticated temporary SFTP transferred the hash-checked
payload into `/run`; `/roms` stayed read-only. No installed launcher was replaced.
R30 source is `47f968e7256dd46893f3640900c5b959a482e590`; artifact identity and
the two-file delta readback live in
`mainline/out/.cache/r46h-compositor-20260910/r30/receipt.json`.
R30 replaces R29's per-file subprocess preflight with Bash header reads and one
dependency query; runtime binaries are unchanged. Both resolved the target ELF
closure, but an R29 repeat hit the 80 C guard during preflight.

Evidence root: `mainline/out/.cache/r46h-r29-device-20260911.2GMPfL/`.
`session.json`, raw `serial.log`, paired PNG/JSON records and the UART-hash-verified
`evidence/r30-evidence.tgz` retain the exact boundaries:

- First R30 session: actual DRM/Panfrost Qt navigation, Neo resource check,
  target native-worker launch and a composed Metal Slug title frame passed.
  `control/05e45430-4774-44e6-b1dc-a94d00a21b97.png` under `evidence/` owns that
  frame. The bounded session ended with `status=0 frontend_restore=0`;
  health samples reached 76.923 C without triggering the guard.
- Repeat: the input RPC reported a completed Select+X lease, but both returned
  PNGs showed the old Moonlight page despite active Neo state. Thus game-input
  effect and fresh capture **did not pass**; API success is insufficient.
  Near panel opening, temperature reached 82.307 C at the three-second sample;
  the 80 C guard stopped the session (`status=143 frontend_restore=0`).
  Diagnose display/capture freshness and load before repeating this flow.
  Weston also logged `finalizing a layer with views still on it` during abort;
  cleanup needs review even though its processes and seat socket disappeared.
- `python3` is absent on this rootfs. PortMaster/native-port Python workflows
  need a verified runtime before their target gate; no runtime was installed.
- Final checks: ext4 errors 0, no failed units or matched MMC/GPU/OOM faults,
  input/volume/frontend restart counts 0. Both temporary listeners and test
  trees were removed, the host test private key deleted, then `sync` and serial
  `Powering off.` at uptime 2868.377044 confirmed controlled shutdown.

Panel isolation, physical L3+R3, fresh repeated captures, Neo save/load,
Moonlight under this compositor, LCD motion and audible output remain open.
The automatic script's partial step labels prove transport/state only; its
review annotation explicitly rejects the stale PNGs as game-effect evidence.

R31 addresses two confirmed gaps: compositor teardown now unlinks
live desktop views before finalizing layers, and the bundle includes the
[private Python interpreter](../gaming-ports/README.md#private-harbourmaster-backend).
The live-surface SIGTERM check failed on the old compositor and passes after the
fix. `R46H_TEST_RENDERER=gl` now exercises both Qt and Weston with OpenGL in
`check-handheld.sh` and `check-desktop.sh`; software rendering remains the default.
Both basic and threaded GL desktop/input/privacy/recovery checks passed, but did not reproduce
R30's stale pixels or temperature rise. These remain device-only open findings;
do not claim either fixed by the teardown change. Host evidence lives under
`mainline/out/.cache/r46h-shared-repair-20260911/`.
The frozen source is `cdb1b3e863f928e7f82338ce5d361748ebb665de` on
`codex/r46h-shared-repair-r31`; the combined candidate, receipt and independent
manifest readback are in `mainline/out/.cache/r46h-compositor-20260910/r31/`.
The package is 40,227,813 bytes compressed, 115,666,343 regular-file bytes expanded.
Account for both transfer and extracted copies in `/run`; remove the verified
transfer archive before launching. Packaged catalog checks with no system Python
on PATH, unprivileged sessions, power-result forwarding and authenticated SSH
control passed. The temporary R31 device result follows; it is not installed.

## R31 device follow-up 2026-09-11

Evidence: `mainline/out/.cache/r46h-r31-device-20260911.CVD4cJ/`, including
`session.json`, `serial.log`, checked PNG/JSON pairs and the UART-hash-verified
`evidence/r31-evidence.tgz`. Same fixed v0.17/v0.15 profile; cold boot, external
power, payload readback and private Python extension imports as `ark` passed.

The first run captured a pre-launch page two seconds after process/input readiness;
a later capture showed Metal Slug. Its native worker reached the 120-second limit,
and the preview subsequently expired normally (`status=0 frontend_restore=0`).
This shows that process readiness alone does not establish a mapped game frame.
The second run waited for recent compositor game frames and positive submissions
before capturing; its fresh game frame and subsequent checks passed:

- Routed Select+X opened Ozone; the composed PNG shows its Save States entry.
  Save/load itself was not exercised.
- The global panel and resident HUD composed over Ozone. Remote game input was
  refused while the panel owned input; B closed it and restored game ownership.
  These are RPC-driven checks, not physical L3+R3 acceptance or resumed gameplay.
- Snapshot game submissions were about 47–57/s before the global panel and
  37/s with it open. Capture and control traffic were active; this does not
  establish steady gameplay/LCD FPS or isolate the overlay's cost.
- First-run maximum was 75.769 C. The second reached 85.000 C and triggered the
  configured guard during exit confirmation. It restored ES-DE with
  `status=143 frontend_restore=0`; Cancel/confirmed exit remain unverified.
- Neither session logged the previous layer-finalization BUG. No test clients
  or seat socket remained; ext4 errors and service restart counts stayed zero,
  with no failed units or matched MMC/GPU/OOM faults. Temporary services/files
  and the host test private key were removed, then serial confirmed controlled
  poweroff at uptime 1033.463468.

Use recent game-frame metrics as the automation readiness gate, then validate
the captured content; preserve early-frame failures instead of accepting RPC
success alone. Profile frame/control/overlay load under short bounded sessions
before completing exit, saves, physical controls and streaming gates.
Record client/compositor/game CPU, frame metrics and thermal samples together:
the user set the unattended test abort to **85 C** on 2026-09-11. Stop the
temporary session when either SoC/GPU sample is `>= 85000` millidegrees C.
This changes the external test monitor's threshold, not kernel thermal trips.
The 80 C aborts above remain historical evidence. Keep short sessions until
the R30 fault is understood.

## R32 device follow-up 2026-09-11

R32 source `1c04ca9f5cb5b25173fb6a202c88cf4fc3d65322` moves the
readiness predicate into maintained code and keeps the one-second game sample
active when the HUD is hidden. Its package and 1,726-file independent readback
are in `mainline/out/.cache/r46h-compositor-20260910/r32/`; device evidence is
`mainline/out/.cache/r46h-r32-device-20260911.nWSGPW/`.

The same fixed v0.17/v0.15 identity cold-booted. Authenticated transfer, full
target manifest, private Python preflight and fresh composed Neo content passed.
The maintained wait succeeded before enabling the HUD. Three short samples per
phase reported median game submissions of 60.519/s HUD-off, 59.856/s with capture
traffic, 60.166/s HUD-on and 59.917/s with the panel open. HUD-on UI CPU was 8.585%
of one core and panel-open 24.072%. Maximum temperature was 80.384 C; the external
85 C guard did not fire. These 102 seconds do not prove LCD FPS, sustained load or
the cause of earlier heating.

External stop returned `status=0 frontend_restore=0`, restored all three product
services and left no processes or global seat socket. Two unlistened socket paths
remained in the session's `runtime.*` directory because the cgroup stop killed the
inner shell before its EXIT cleanup completed. The exact directory was removed,
then kernel-fault/failed-unit counts were zero, `/roms` remained read-only and UART
confirmed poweroff at uptime 1317.049034. No save/load, physical control, LCD or
audio observation was made.

R33 source `8f43660eef230ebb0267490be155c88ac65493fc` on
`codex/r46h-stop-cleanup-r33-candidate` adds a fail-closed outer cleanup for the
single exact `ark:0700` runtime directory. Its full ARM64 checks and 1,726-file
readback pass under `mainline/out/.cache/r46h-compositor-20260910/r33/`.

## R33 device follow-up 2026-09-11

Evidence is `mainline/out/.cache/r46h-r33-device-20260911.7qFngw/`; its
`session.json` owns the exact hashes, captures, discarded attempts and limits.
The fixed v0.17/v0.15 target cold-booted, the R33 archive and 1,726-file target
manifest passed, and the private Python preflight completed as `ark`.

The first minimal session proved the R33 change: external `systemctl stop`
returned `WAYLAND_END status=0 frontend_restore=0`, removed the sole exact
`runtime.*` directory without manual deletion, left no related process or global
seat socket, and restored frontend/input/volume. Later normal expiry, external
stop and thermal-abort paths repeated the same automatic cleanup.

Remote device automation then launched Neo, passed the maintained first-frame
wait, proved the exit dialog defaults to Cancel, confirmed Stop returns to the
same shared desktop, relaunched Neo and opened the real Ozone Quick Menu. A final
disposable run selected slot 0 Save State and Load State; RetroArch's target log
records both operations at 415,184 serialized bytes and the compressed state was
2,222 bytes. Select+Start returned with native result 0.

One earlier stock-frequency save-menu attempt reached 85.769 C and the external
85 C guard terminated it cleanly. After cooldown, save/load ran with temporary
1008 MHz CPU and 400 MHz GPU maxima; that session peaked at 78.461 C. The original
1296 MHz / 480 MHz maxima were restored before final health. Failed units and
kernel-fault matches were zero, `/roms` stayed read-only, target staging/listeners
and the fresh private key were removed, and serial confirmed `Powering off.` at
uptime 3811.373113. This is composed-frame/remote-control evidence: physical
controls, LCD motion, audible output, sustained thermals and reboot save retention
remain open.

## R35/R36 device follow-up 2026-09-12

Evidence is `mainline/out/.cache/r46h-r34-device-20260912.70eo6d/`; `session.json`
owns exact identities, hashes, captures, discarded attempts and limits. R35 showed
NetworkManager's actual cached signal plus battery percentage and charge state.
Its Neo slot 0 state was written under the explicit persistent directory, retained
the exact SHA-256 across a warm reboot and then produced both RetroArch's Load State
log and the visible loaded notification. The first automated load landed in Rewind
and is rejected because no load log existed.

R35's PortMaster refresh exposed a privileged-launcher leak: HarbourMaster inherited
`HOME=/root` and refused `/root/.var/...`. R36 binds HOME to its private `ark` state
before import. The focused manager suite, full ARM64 build and independent 1,726-file
readback passed; direct target refresh then returned 1,396 entries. The Qt UI showed
those entries and the four original local projects. No install/update/remove, Mono
mount or game launch was attempted.

One stock-frequency PortMaster UI attempt hit 85.769 C and the external guard ended
it safely. The accepted work used temporary 1008 MHz CPU / 400 MHz GPU caps, restored
to 1296/480 before final health. Services were active with zero restarts, `/roms`
was read-only, failed units and matched kernel faults were zero, temporary target
state and the fresh private key were removed, and serial confirmed poweroff at
uptime 2491.318084. The persistent Neo state and PortMaster registry remain by design.

## R36-R39 GTA III device follow-up 2026-09-12

Evidence is `mainline/out/.cache/r46h-r36-gta3-device-20260912.KssIkj/`;
`session.json` owns exact identities, candidates, artifact/evidence hashes and
cleanup. R36 first proved the guarded fixed-hash GTA III handoff but exited 127
because `libOpenGL.so.0` was packaged outside the inherited library path. R37's
single shared-runner fix admitted both verified bundle directories; dependency
loading then passed, but the engine exited -11 at `gladLoadGLLoader` before a frame.

R38 and R39 tested the engine's existing desktop-GL-to-GLES fallback without
replacing Mesa or system SDL. R39 records the requested SDL profile and rejects
only core-profile window attempts. The actual retained GTA III/VC engines still
reach their frontends on the AArch64 host with software GLES 3.2, but R38 and R39
both retained the target failure on Mali-G31 Panfrost GLES 3.1. The loader error is
hard-coded for both profile paths, so the run does not prove which GLES symbol is
missing. Another profile shim is not justified; the next bounded hypothesis is the
same engine under the retained direct KMSDRM supervisor, or a source-proven librw/GL
loader rebuild matched to target GLES 3.1.

The R39 target run kept `/roms` read-only, created no GTA save and returned to the
composed desktop with an explicit launch error. Its guard sampled at most 78.461 C;
1296 MHz CPU and 480 MHz GPU maxima were restored. Frontend/input/volume services
were active, failed units were empty, transfer/UI/staging trees and the fresh key
were removed, and serial confirmed full filesystem detach and `Powering off.` at
uptime 3448.012302. This is a negative compatibility result, not gameplay, LCD,
audio, physical-control, save or relaunch proof.

## Resume and rebuild

R51 reuses the existing composed game layer, resident performance panel,
frame-submission telemetry, capture authorization and routed remote gamepad for
the repaired source-built GTA engines. `build-handheld.sh` now verifies and
mounts the same explicit hash-bound GTA engine directory used by the direct
package; the receipt records both engine hashes. This adds no second overlay or
remote protocol. R49 passed its 1,726-file target readback but its preflight
omitted the already packaged private port library from the diagnostic `ldd`
search path. R50 fixed that preflight and passed it on target, but its no-Moonlight
fallback hid the built-in PortMaster page behind the diagnostic controller.
R51 keeps that fallback only for sessions without shared ports; it adds no game,
overlay or remote protocol. Source `75c1800d636b138635c589016b7f99e181760ec1`
produced archive SHA-256
`d7a1561f93f4c64d3e4825a0c265a624feda7b13fd6447a99d86905088f5d202`
with manifest SHA-256
`fe1f4b8c0662581307f75cfd470958549fff963b684014f3ad67df44282e7178`.
All 1,726 files rehashed on host and target, and target preflight passed.

The R46H composed capture showed the GTA III menu beneath the resident HUD at
25.596 game submissions/s, 36.281 ms median and 43.572 ms P95 intervals under
temporary 1008/400 MHz caps. The maintained fresh-frame gate separately measured
26.572/s. A strict `game-input` Down sample completed for `native.gta3`; completion
proves the bounded routed sample, not the game's response. The first run reached
the external 85 C limit and stopped; a cooled second run was stopped immediately
after input at 84.615 C. Both restored the three product services, device/port
leases and seat state. Original save hashes were unchanged and managed GTA saves
remained empty. After restoring 1296/480 MHz limits, serial confirmed filesystem
unmount, loop detach and `Powering off.` at uptime 35646.117430.

Exact device evidence is
`mainline/out/.cache/r46h-r47-attended-device-20260913.oxUqYw/session.json`.
The capture measures compositor submissions, not displayed LCD FPS. GTA gameplay,
audio, save/relaunch, shared Vice City and Moonlight remain open or deferred.

R54 source `8923172a3f50cfc37ccce5d8bcee503c6f1b6598` switches both GTA engines to
upstream `MASTER`/`FINAL`. Its target manifest and preflight passed. At identical
1008/400 MHz caps, the GTA III menu averaged 26.84 submissions/s with the
full-screen transparent HUD and 30.43/s hidden; interval medians improved from
35.84 to 31.85 ms. A second HUD-off sample averaged 30.64/s. GPU temperature
peaked at 83.846 C without crossing the 85 C guard. All engine bounds exited 0,
but two completed remote A requests left identical main-menu captures, so no intro
or crash result is inferred. Exact evidence is
`mainline/out/.cache/r46h-r54-device-20260914.goly7P/session.json`.

R55 uses Weston's existing view mask to limit the transparent UI surface to the
resident HUD's fixed top-right canvas region while a game owns the display. The
full UI mask returns when the quick panel opens, and compositors without the mask
capability retain the previous full-surface behavior. Pixman, software GL and the
real Qt/router/SDL desktop checks passed, including composed HUD and panel pixels.
Evidence is `mainline/out/.cache/r46h-hud-mask-r55-host-20260914/`. This is host
proof only; the R46H pacing, colors, controls and thermal gate remain open.

R56's no-Moonlight candidate is
`mainline/out/.cache/r46h-gta-shared-20260914/r56/`, source
`c5514be42c346f008c8fadf0982668c1d2ad3cf9`. It retains R55's HUD mask and
aligns the status icons, labels and clock. Mac and ARM64 Qt fixture captures
passed. Its 1,727 regular files passed
independent readback; archive SHA-256 is
`d21881d20f26b3a5e5208880211ff1c0304a88fe6881f82b4bf482c738eab762` and
manifest SHA-256 is
`22cfc859f0b268524122cb456a01ffc9979207632b38bb9f0c3207e5e4d346df`.
Target readback/preflight and composed status/HUD capture passed. Its HUD-hidden
GTA III intro averaged 5.57 submissions/s; the 121.17-second disappearance was a
forced diagnostic bound, not a reproduced crash. Exact target evidence is
`mainline/out/.cache/r46h-r56-device-20260914.L7Smy5/session.json`.

R57 preserves the fast requested-stop path but gives a self-triggered bound five
seconds for cleanup. Its slow-flush Linux process fixture and real ARM64 Wayland
ports check pass. Clean source `30c1813422acd14078f40a9e9893f4f46f8dbf08`
produced `mainline/out/.cache/r46h-gta-shared-20260914/r57/`; its 1,727 files
passed independent readback with archive SHA-256
`f0c9e735c8cf52db1d646aa3a94228a24fd798dcb569257db4a2e585ff535693`
and manifest SHA-256
`c2e222e2d0f9a16772d1190c0256ca7e0786078b62b4aaefc1ea33a2ad5f3234`.

On R46H, the 1024x768 and temporary 640x480 GTA III runs reached their
120.97/121.05-second diagnostic bounds, exited 0 and reported `forcedKill=false`.
The lifecycle fix therefore passes. One 1024x768 and two 640x480 Panfrost
`DATA_INVALID_FAULT` events happened before those exits while game submissions
continued, disproving the earlier teardown-only hypothesis. In similar roughly
59-second HUD-on intro windows, 1024x768 averaged 5.59 submissions/s with a
161.88 ms median interval sample; 640x480 averaged 12.32/s with 76.98 ms. The
second run began hot and reached 85.384 C with CPU/GPU cooling active, so this is
not a clean thermal comparison or an accepted display default. The exact managed
configuration hash was restored; services, leases and temporary authorization
were clean before serial-confirmed poweroff. Exact evidence is
`mainline/out/.cache/r46h-r57-device-20260914.vAbRL9/session.json`. Moonlight and
Vice City were not run; LCD motion, audio, physical controls, saves and relaunch
remain open.

R36 remains the accepted Moonlight/status comparison. The current target-tested
no-Moonlight GTA candidate is `mainline/out/.cache/r46h-gta-shared-20260914/r56/`;
its receipt owns source, shell, engine, archive and manifest hashes. Use its shell
hash for SSH `--expect-binary` and manifest hash for the target probe. The R56
device `session.json` above owns physical results and limitations.

The retained GTA diagnostic is `mainline/out/.cache/r46h-compositor-20260910/r39/`,
source `286fcdfcf7643c43f19b1272beefd136e09cc08f` on
`codex/r46h-gta-gles-r39-candidate`. Its 1,727-file independent readback passed;
archive, manifest and shell hashes are in its receipt. R39 is not the next general
deployment recommendation because its target GTA gate failed.

The R36 build worktree and redundant staging were removed. Reuse the independent
source branch from [Project Context](../../docs/PROJECT-CONTEXT.md#workspace-handoff)
or freeze a new clean source snapshot. Do not build by resetting the dirty main
checkout. A sparse checkout of `AGENTS.md`, `docs/` and `mainline/` avoids unrelated
legacy CRLF blobs; do not normalize legacy files just to satisfy the builder.
Keep any temporary `GIT_INDEX_FILE` confined to snapshot creation, not worktree commands.

The original workspace's external `mainline/out/.cache/` retains the builder inputs:

- `r46h-ports-backend-20260910/prepared/portmaster-backend.tar.gz` and its adjacent
  `runtime.sha256`: set `R46H_PORTMASTER_BUNDLE` to this path; the builder default
  `r46h-portmaster/` is not the prepared cache in this workspace.
- `r46h-ports-native/`: `R46H_PORT_NATIVE_CACHE`, verified by `prepare-native.py`;
  includes pinned private Python and native audio-library debs.
- `r46h-moonlight-qt/revision-v5/moonlight-qt-v5`: use its hash from the R36 receipt.
- Retained `r46h-wayland/`, `r46h-shell/linux-build/` and compositor font/plugin/
  `ssh-debs/` caches: keep them; they are inputs, not stale session staging.

Run `build-handheld.sh EXISTING_MAINLINE_CACHE NEW_EMPTY_OUTPUT MOONLIGHT_BINARY
SHA256` from the clean snapshot with those overrides. Increment the candidate
revision in `check-session.sh` before freezing changed payloads; never overwrite
or relabel R36. The builder checks actual desktop, packaged catalog/private Python,
unprivileged sessions, power-result propagation and authenticated remote control.
`check-handheld.sh` adds live-surface SIGTERM cleanup; `check-desktop.sh` accepts
`R46H_TEST_RENDERER=gl`, and `QSG_RENDER_LOOP=threaded` matches the target render loop.
Their dependencies/mounts are in the scripts and the build wrapper. Host GL uses
llvmpipe, not Panfrost. Retain the named evidence, then remove only new disposable staging.

## Input routing candidate

`input-router.cpp` grabs only the name/VID/PID/version-checked **R46H Combined
Gamepad**, then creates **R46H Routed Gamepad** (product 0x0049) with the same
17 button capabilities and four axes/calibration. The unidentified HAPPY5 capability
is retained without assigning it a new action. The accepted bridge is unchanged.
Games read the routed endpoint; the UI receives normalized samples over an inherited
parent-owned Unix `SOCK_SEQPACKET` connection. `input-route.h` owns the fixed local
packet contract (version 2); GUI and router must come from the same candidate.
There is no listening socket or network input service in the router itself.

The controller selects UI/game ownership with a strictly increasing sequence.
Each change sends neutral game/UI state and waits for physical neutral. A matched
L3 + R3 chord releases game controls immediately and requests a panel transition;
delivery stays paused until the controller acknowledges ownership. Only stick
clicks wait for the configurable 40–300 ms chord window (120 ms test default).
Standalone short clicks retain both edges; late overlap remains ordinary clicks.
The physical feel of that window still needs operator acceptance. L1/R1 passthrough
is unchanged. Input overruns resynchronize behind the neutral gate; source/channel
loss or invalid commands release the grab and destroy the virtual endpoint.

`check-input-router.sh` runs in the same pinned ARM64 SDK as the compositor check,
with `--init --network none --device-cgroup-rule 'c 10:223 rwm'` and
`--device-cgroup-rule 'c 13:* rwm'`. Mount this directory read-only at `/src` and a
named external evidence directory at `/out`; run `timeout 60 bash /src/check-input-router.sh`.
The test creates only synthetic input nodes in its container. Policy checks and
real kernel tests cover both click orders, short clicks, unchanged shoulder keys,
held-input gates, EVIOCGRAB isolation, axis metadata, actual SYN_DROPPED recovery,
stale/wrong-device refusal and disconnect cleanup. Evidence is
`mainline/out/.cache/r46h-compositor-20260910/input-router-check.log`.

## Actual Qt desktop integration

`gaming-shell/handheld.cpp` connects the actual desktop to both the private Weston
policy and its child input router. Enable only in the separate Wayland session with
`--handheld-router ABSOLUTE_EXECUTABLE --input-device VERIFIED_MERGED_EVDEV`.
The shell rejects simultaneous direct-display handoff modes. Existing EGLFS/native
and SDL input paths remain the default; the accepted merged bridge is unchanged.
Router executable, socket directory/owner/mode and inherited channel are checked.
After bounded startup, policy/input IO uses Qt notifications with deadlines and
bounded stale-state refresh. Failed ownership stops the foreground application
and closes the preview for supervisor recovery.

The window requests an alpha channel before creation and keeps its ordinary
content hidden during gameplay. The existing quick controls open over that surface;
L3 + R3 and B toggle/resume with broker ownership acknowledgements. A separate
overlay flag keeps the performance HUD visible while the game owns input. Ending
the game uses the shared choice popup, initially on Cancel. Application exit closes
that confirmation and restores the desktop. The application launcher supplies the
observed routed GUID/mapping and selects only product 0x0049 for SDL games.

`check-desktop.sh` uses the same isolated SDK/device rules as the kernel check.
Mount the shell at `/src`, this directory at `/wayland` and `/gaming-wayland`, the
existing Linux build cache at `/out/linux-build`, dependencies at `/debs` and
`/wayland-debs`, and named evidence at `/out`. It uses the retained shell package's
Chinese font under `/out/share/fonts/` and the client plugins prepared by
`check-handheld.sh`. Run it with an outer 240-second deadline. Live game observations
stay in private `/run`; only final evidence is copied to the external volume.
The CLI integration also mounts the shell and screen-fetch tool at their normal
`/project/mainline/` paths, with `/project/mainline/out` mapped to the external
desktop evidence directory. The CLI's output-location guard remains enabled.

The real Qt/Weston/SDL test passes four axes, mapped buttons/triggers, physical-style
A launch, L3 + R3 neutralization, blocked background input, B resume, a resident HUD,
shoulder passthrough, default cancellation and confirmed exit/desktop return.
Actual composed PNGs show the game behind the shared controls and Chinese text;
a QImage check verifies game pixels beside the opaque panel. The evidence lives in
`mainline/out/.cache/r46h-compositor-20260910/desktop/` and `desktop-check.log`.

The outer probe also removes one exact `ark:0700` per-session `runtime.*`
directory after stopping its transient cgroup. This closes the external-stop race
where the inner shell can be killed before its EXIT trap unlinks stale Unix socket
paths. Multiple, linked or differently owned runtime paths fail closed before the
frontend restarts; the host recovery check creates a real socket for this case.

## Composed capture and recovery

The shared session's endpoint reports `weston-output`; ordinary previews retain
`qt-window`. A capture first rejects sensitive entry, then waits for a fresh Qt
sync/swap and an asynchronous `wl_display_sync` on [Qt's own Wayland connection](https://doc.qt.io/qt-6.8/qnativeinterface-qwaylandapplication.html).
This confirms the public surface reached Weston before briefly granting capture.
When the acknowledged policy hides the UI behind a game, only the same-connection
fence is needed. Pixel capture runs on a bounded worker; permission is revoked
before returning the image. Entry/exit and ownership changes invalidate the pending
result, including a private editor opened while a frame is waiting. No private
result is encoded, published or retained. The frame wait never blocks the Qt loop.

The actual desktop test covers initial private-entry refusal, immediate close-plus-
capture, deterministic cancellation with the compositor paused, recovery, and
router loss during a game. The last stops the game and returns failure to its
supervisor. Qt process-group cleanup also covers a main launcher exiting before a
TERM-ignoring ordinary child. Source/artifact hashes and results remain in the
named evidence directory; these are host checks, not device acceptance.

The session scripts now support the optional `handheld` profile beside the accepted
two-window `windows` default. Target preflight finds exactly one named merged pad,
checks `ark` can read it and verifies uinput's character-device identity. The root
seat wrapper opens uinput once and drops to `ark` with `setpriv`; it closes its copy
immediately. The compositor never inherits it. The GUI seals the descriptor before
Qt initialization, passes it only to the router, then closes its own copy. No udev
rule, global device mode or service is installed. Wrong-device/read-only descriptors
are refused; the existing target cgroup and ES-DE recovery wrapper remain in use.

`handheld-client.sh` defaults to a private diagnostic application list: one separate
copy of the controller-test UI. A shared ports session instead exposes the existing
built-in PortMaster page without requiring a packaged Moonlight client. Settings
are read-only unless the root supervisor
grants the [explicit device lease](../gaming-shell/DEVICE.md#shared-wayland-settings-candidate).
The game child never inherits that control flag. `check-session.sh` runs these
actual scripts as `nobody`, with `/dev/uinput` hidden after delegation. It verifies
no handle in the session/compositor/GUI/game, L3+R3/B handoff, and cleanup after
compositor loss. The retained two-window profile is also checked. The container
uses `--cap-add SYS_PTRACE` only so the test can inspect another UID's descriptors;
this is not a target permission requirement.

The shared supervisor's optional device mode reuses the accepted backlight/CPU
adapter and Cancel-first power dialogs. A single transient-unit hook coordinates
device and port leases, attempting every restore before reporting failure. The
outer probe verifies cleanup before ES-DE or power actions. This follows
[systemd's startup-failure cleanup contract](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html#ExecStopPost=).
R31 tested the basic seat/cgroup/recovery path; target use of these optional
device/Mono leases remains unverified.

`build-handheld.sh EXISTING_MAINLINE_CACHE NEW_CANDIDATE_OUTPUT [MOONLIGHT_BINARY SHA256]` freezes a separately
named archive from a clean source snapshot. Both paths must be on the external
workspace and output must be empty. It builds/tests in the pinned SDK, reuses the
hash-bound Weston runtime, strips the three new binaries, and records manifest,
source archive, payload and evidence hashes. This never overwrites R20 or the
accepted Wayland archive. The device command adds `handheld` after the manifest hash
to both `probe-r46h.sh --check` and `--run`; the established scope, identity, health,
space and serial procedure remains in [the display runbook](README.md#first-device-gate).

The newer builder also uses the shared [port runtime assembly](../gaming-ports/README.md#shared-target-session-candidate).
Prepare the existing PortMaster bundle and native-library cache first; optional
`R46H_PORTMASTER_BUNDLE` and `R46H_PORT_NATIVE_CACHE` select their verified external
locations. The target's explicit persistent-state path enables the Mono lease
and shared native-port capability. Omit it for the disposable diagnostic session.
The [current candidate](#resume-and-rebuild) owns the next combined archive;
the [ports contract](../gaming-ports/README.md#shared-target-session-candidate)
owns native-port/persistence gates. R24 is a retained historical comparison.

The newer [shared SSH entry](../../docs/REMOTE-CONTROL.md#shared-wayland-ssh-candidate)
reuses the existing restricted relay for composed captures and bounded game input.
The builder runs `check-remote.sh` against the packaged executable. Its test-only
`ssh-debs/` cache under the compositor evidence directory contains OpenSSH server/
client and iproute2 dependencies downloaded with APT's download-only mode in the
pinned SDK. Testing uses a private loopback server in a network-disabled container;
no host keys, accounts or service configuration are changed on the Mac.
The [transport contract](../../docs/REMOTE-CONTROL.md#shared-wayland-ssh-candidate)
owns the shared SSH procedure; R25 is its retained host baseline, superseded by R31.

R21 is frozen at `mainline/out/.cache/r46h-compositor-20260910/r21/receipt.json`,
source `5acdd9041bdff7944b62b1eb7a9fd43de2ade09e` on
`codex/r46h-shared-r21-candidate`. Full Qt/router/remote/capture checks, the packaged
unprivileged diagnostic session and the original two-window profile passed. The
archive is 27,691,074 bytes (79,193,494 regular-file bytes expanded); full manifest
and archive readback passed. Recheck free `/run` space before staging. No device or
media write has been performed for this candidate.

The newer source adds [shared Moonlight management](../gaming-shell/STREAMING.md#shared-display-candidate).
Supplying the optional hash-bound client produces a separate streaming candidate:
`MOONLIGHT_SHA256` explicitly selects the built-in management page and embedded
keyboard instead of the diagnostic application list. The actual private client
must pass offline `--help`; the packaged UI is checked as an unprivileged user,
including keyboard-module readiness and private-entry capture refusal. Pairing and
real stream data are not included in the package. The remote safe-state flag
`keyboardReady` reports module readiness only, without exposing editor contents.

R22 is frozen at `mainline/out/.cache/r46h-compositor-20260910/r22/receipt.json`,
source `856def66467decaff94128752f61d28bd2e6c651` on
`codex/r46h-shared-stream-r22-candidate`. It includes the retained v4 client.
The 32,117,951-byte archive expands to 88,744,237 regular-file bytes; complete
archive/manifest/evidence readback passed. Packaged management, keyboard readiness,
private-entry refusal and offline client startup pass as an unprivileged session.
The fake-transport stream flow preserves one desktop/IPC generation across normal
exit, error, reconnect and explicit Stop. Real Sunshine/Hantro/A/V/input still
require the device gate. R21 remains the smaller diagnostic comparison package.

The current device follow-up above supersedes these host-only milestones.
Remaining gates are thermal/performance cost, normal exit/saves, physical controls
and streaming. A process group does not contain a deliberately detached service;
limited machine proof does not establish broad game compatibility or 60 FPS.

## Game frame metrics

The compositor counts new buffer attachments in its existing desktop-surface
commit callback. It measures the largest mapped, parentless game window (newest
on equal size); child-only video surfaces are outside this first producer's scope.
`frameStats` reports a window ID, cumulative count, monotonic sample time, last
buffer age and median/P95/max of the last 120 submission intervals. Intervals
become unavailable after two seconds without a buffer. Output-mode Hz is metadata.
No output-frame listener is installed: Weston DRM uses those listeners to disable
direct scanout. Per-commit bookkeeping uses a fixed ring and no allocation.

The desktop reads this data once per second while a game is active and its window
is visible. HUD visibility changes only the overlay; minimized or closed-game
sampling stops. Count deltas use actual elapsed time and reset when the window
changes. Failed optional samples clear values and retry without stopping the game.
Input/privacy transitions take precedence.
The HUD labels the rate as game submissions; the existing recorder exports the
same numeric values without screenshots. This does not measure displayed frames,
GPU render duration, simulation updates, video drops or audio latency.

`control.py wait-game-frame` reuses these samples and the R31 predicate: stable
session/binary, active shared game, nonnegative last-frame age and positive
submissions. It is bounded to 2–60 seconds and never captures or changes UI state.
The caller must validate the following composed PNG against pre-launch references.

`check-desktop.sh` first verifies readiness with the HUD hidden, then compares
independent client `frameSwapped` and compositor counts at two requested timer
rates and at rest. The software renderer need not
reach the requested rate. The check covers HUD-only repaints, stale intervals,
sampling off/on and game exit. Evidence lives in `desktop/frame-metrics.json`
and `desktop/game-frame-hud.png` under the named candidate output. R55 additionally
checks that the game remains visible outside the masked HUD and opening the panel
restores the full UI surface. Physical accuracy and R55 overlay cost on R46H remain open.

R26 is frozen at `mainline/out/.cache/r46h-compositor-20260910/r26/receipt.json`,
source `e4ed1ba3b115ce43805eb12306efac04b838dddd` on
`codex/r46h-game-metrics-r26-candidate`. The 33,661,193-byte archive expands to
92,934,308 regular-file bytes; full archive/manifest readback passed. Desktop
frame/input/privacy, packaged unprivileged sessions and authenticated SSH checks
passed. The first combined build stopped after the logged two-window pass without
a diagnostic; retrying the session/package/SSH phases with identical source passed.
The receipt retains that failed attempt; its cause remains unconfirmed. This is
host proof only. R25 and the accepted device fallback remain retained.

## Real Neo host check

The working source after R22 adds the [guarded Neo adapter](../gaming-shell/TOOLS.md#neo-shared-display-adapter).
`check-neo.sh` runs the retained RetroArch 1.20.0 and hash-bound FBNeo/Metal Slug
under the same compositor with headless Mesa GL. Its original ROM/BIOS mount is
read-only; config, core options, saves and screenshots live in private `/run`.
Frozen evidence is `mainline/out/.cache/r46h-compositor-20260910/r23/native-gl/`.

The actual routed SDL controller supplies coin/start and reaches the game's
teaching screen. The composed Ozone image shows the Save States entry. The test
saves, advances to a different frame, loads the state and compares restored pixels.
L3+R3/B, one Select+Start exit, second launch and confirmed panel Stop pass while
preserving the desktop session. The private config disables RetroArch's
[default double-quit requirement](https://github.com/libretro/RetroArch/blob/v1.20.0/config.def.h#L958).

This test uses the explicit application-list launcher and production Neo config;
it does not bypass or exercise the target-only worker identity guard. Its temporary
RetroArch UDP commands exist only inside a network-disabled container. Audio is
disabled; full gameplay, physical menu/save controls, LCD motion, sound and
persistent saves remain target gates. The limited native-worker device result
is recorded above. R20/R22 are unchanged.

R23 is frozen at `mainline/out/.cache/r46h-compositor-20260910/r23/receipt.json`,
source `7c001613318a1488f5c58e6dec193e6416a56a22` on
`codex/r46h-shared-neo-r23-candidate`. The 32,123,310-byte archive expands to
88,744,237 regular-file bytes. Archive/manifest readback, packaged unprivileged
sessions, shared-stream regression and the frozen-source Neo check passed.

## Bounded remote game input

The existing private control endpoint advertises `game-input` only in a handheld
session. Each request supplies the usual session/binary/UI sequence plus the current
`state.activeApplication` and `state.inputSequence`. The latter changes with input
ownership and tool commands; a stale value or wrong application is refused.
`state.gameInputAvailable` reports the permitted UI/game context, while the broker
also rechecks physical neutral at the moment of injection.

One request holds up to 16 named buttons and four normalized axes (-1..1) for
10–1000 ms, defaulting to 100 ms in the CLI. The broker owns the monotonic deadline;
it sends neutral tool state on expiry, then resumes the physical sample. Physical
buttons or sticks leaving the established neutral gate cancel the sample. Opening
the panel, input resynchronization, client disconnect or ownership loss also cancel
it. Cancellation preserves physical input. Simultaneous L3 + R3 is reserved;
use the existing `tap quick` UI action for the panel. L1 + R1 remains available to
the game/Moonlight. No unbounded press, text injection or arbitrary device write
is exposed.

The result reports `input_backend: routed-uinput` and `input_status` as `completed`,
`cancelled` or `unavailable`. Completed means the broker applied and released the
sample, not that the game accepted a particular action. The CLI exits nonzero for
the latter two statuses; re-observe before another mutation. An optional composed
capture follows release. Existing `tap`/`text` retain their Qt-action semantics.
The CLI validates its external output directory before sending any operation.

The kernel check covers normalized ranges, timing, physical takeover, a second
lease refusal, cancellation/mode changes and disconnect. The actual desktop check
drives the SDL game through both RPC and the real CLI, verifies buttons/axes and
release, wrong-game/stale-generation refusal, physical takeover and panel/client
cancellation. `desktop/remote-game-exchange.json` retains a real request/result;
the regular CLI validator also checks its returned composed PNG. No physical R46H
or PC-stream input acceptance is inferred from this synthetic-device test.
