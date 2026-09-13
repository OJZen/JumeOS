# R46H shared-display preparation

Status: **R36 STATUS/NEO PERSISTENCE/PORTMASTER CATALOG DEVICE PASS / STREAMING DEFERRED**. This experiment adds Weston
14.0.2 and Qt Wayland 6.8.2 to the shell revision 9 bundle. Its optional local
control endpoint and application list stay disabled in this display probe. It is not an
installed compositor, replacement desktop or finished global overlay. The
[desktop plan](../../docs/DEVICE-SHELL.md) owns the integration gates; the
[agent-control plan](../../docs/REMOTE-CONTROL.md) owns remote operation and UI tests.

## Prepare on the host

```sh
mainline/gaming-wayland/build-runtime.sh
PYTHONDONTWRITEBYTECODE=1 python3 -B mainline/tests/test-wayland-probe.py
```

All outputs go to `mainline/out/.cache/r46h-wayland/`. A disposable ARM64
container installs pinned Weston/Qt Wayland/seatd packages, then disconnects its
network before packaging and testing. The input shell payload is hash-pinned
and remains unchanged. This is a separately named experiment archive, not a
rootfs release or two-build reproducibility claim. `receipt.json` owns input,
source, archive and manifest hashes; `evidence/` contains the runtime results.

The bundle includes the DRM and headless backends, GLES renderer, desktop shell,
Qt Wayland client plugins and missing supplementary libraries with licenses.
System graphics libraries are retained as dependencies. The inherited Qt
closure and base graphics package recipe identify expected target providers;
current container versions are queried from dpkg during each audit. Target
`--check` must still resolve every ELF dependency. No driver is replaced to
make that check pass. The builder rejects unreviewed Qt/libc/Mesa replacements.

The host check hides installed Weston module directories/helpers and Qt Wayland
platform plugins. Two independent Qt clients run using the relocated package;
the foreground captures its own window while the background remains alive.
It tests Pixman/software only, not Panfrost, composed-output capture, stacking
policy or input isolation. Module paths and shell-client paths are explicit;
Weston does not depend on files installed in `/usr` by this experiment.

Session cleanup explicitly terminates clients and the compositor. The probe
sets `SDL_NO_SIGNAL_HANDLERS=1` for its clients: otherwise SDL converts SIGTERM
into an SDL_QUIT event that this Qt controller-only loop does not consume.
That caused the initial host cleanup timeout and is covered by the real runtime
check. The experiment does not change the accepted shell launcher.
[SDL signal hint](https://wiki.libsdl.org/SDL2/SDL_HINT_NO_SIGNAL_HANDLERS)

## First device gate

Keep the current TF base and ES-DE fallback. On an identified boot:

1. Listen on serial before power and follow the current
   [v0.17 contract](../rootfs-debian13-gaming-v17/README.md#persistent-device-acceptance).
   Record pre-run base/storage health and service restart counters.
2. Verify the experiment tar hash before extracting into exactly
   `/run/r46h-wayland-probe`. The scope must be root-owned mode 0755; its code and
   `usr/` files must stay root-owned and not group/world writable. Staging and
   the versioned input hashes must match the host receipt.
   For retained bundles, seal `usr/` regular files/directories with `chmod go-w`
   after extraction; inherited Qt license permissions otherwise fail the guard.
   Check available `/run` space first. On this card its 187 MiB limit cannot hold
   both runtime bundles plus staging; retire the stopped previous bundle only
   after its evidence has been copied and verified.
3. Run `probe-r46h.sh --check MANIFEST_SHA256` from that scope. It checks the
   fixed kernel, root UUID, card CID/size, read-only ROMs, active services,
   manifest contents, dependencies and absence of game/compositor/seatd users.
   ELF headers are read with Bash builtins and passed together to `ldd`,
   preserving full dependency coverage without thousands of per-file shell forks.
   The R30 preflight-only candidate retains R29's runtime binaries and PortMaster
   fixes; its source/payload delta is recorded in
   `mainline/out/.cache/r46h-compositor-20260910/r30/receipt.json`.
4. With the observed baseline healthy, `--run MANIFEST_SHA256` pauses ES-DE and
   starts a transient process group on VT2. A temporary root seatd supplies seat
   access; Weston and both Qt clients run as `ark`. The accepted combined-pad
   mapping and VID/PID filter are reused without changing the bridge.
5. Inspect `state/session.*/weston.log` and both client logs for actual GLES/
   Panfrost, output geometry and errors. Check LCD/colors and active-client
   controls. The current attended script keeps the foreground for 290 seconds and background
   for 300 seconds. The entire cgroup has a 360-second runtime limit plus a 10-second stop deadline.
6. Confirm `WAYLAND_END ... frontend_restore=0`, compare post-run health and
   restart counts, save evidence, remove exact staging and finish with sync,
   controlled poweroff and serial confirmation when unattended.

seatd 0.9.1 uses `/run/seatd.sock`. The probe refuses an existing socket/daemon;
this is the one temporary path outside its staging directory. Cleanup removes
only the recorded socket inode after stopping the whole cgroup. If the unit
cannot stop or that socket's identity changes, it leaves ES-DE stopped and
reports the failure for serial recovery instead of competing for display access.
No system service, udev rule, input mapping or boot configuration is installed.

The 2026-09-09 operator missed the retained 45-second probe. The separately
frozen `mainline/out/.cache/r46h-wayland-attended-20260909/receipt.json` changes
only the client/supervisor deadlines above; all runtime binaries are unchanged.
Its guard/recovery test passed. The original 45-second archive remains retained.

## Device result (2026-09-09)

The original 45-second repeat passed DRM/Panfrost, two-client lifetime and ES-DE
restoration, but the operator requested another run. The duration-only package
above then kept the foreground available for 290 seconds. The operator confirmed
panel navigation, B closing and card movement. Standard Weston window borders
were visible as expected; this is an ordinary-window experiment, not the final
fullscreen desktop or a product global panel.

The agent stopped the owned unit after that confirmation. The wrapper restored
ES-DE with status 0 and removed the recorded seat socket. Health showed zero ext4
errors and zero input/volume/frontend restarts, with ROMs read-only. The operator also confirmed visible ES-DE recovery. Staging and the transfer
server were removed; sync, filesystem detach and poweroff were confirmed over
serial. The complete record is in
`mainline/out/.cache/r46h-acceptance.TiyDFF/session.json`; the matching public
archive is `evidence/wayland-long-device.tgz`. The last reboot was captured at
115200 after operator power-on; it is not another complete two-speed cold trace.
Actual Moonlight/Hantro under Wayland, global stacking, gamepad isolation and
composed-output remote control remain separate untested gates.

## Device result (2026-09-08)

The first probe passed on unchanged v0.17: Weston used DRM, OpenGL ES 3.1/Mesa
25.0.7 and Mali-G31/Panfrost, with two simultaneous Qt clients. The wrapper ended
0 and restored ES-DE; the owned seat socket was removed. The operator saw desktop
window styling but did not operate it. Detailed LCD, controls and visible recovery
therefore remain unconfirmed; actual Moonlight and global input isolation were not tested.

The initial extraction filled `/run` while the previous bundle was retained;
after verified evidence export, both the old bundle and partial extraction were
removed and staging succeeded. Seven inherited Qt license entries also needed
group-write removal; content hashes were unchanged. The builder now seals modes
and reads the frozen revision-9 base rather than the changing shell output path.
Its focused host guard/permission checks passed; a rebuilt Wayland archive has
not been claimed. Public device logs and the poweroff trace are retained in
`mainline/out/.cache/r46h-attended-20260908/` with UART SHA-256 readback.

The first probe uses two ordinary desktop-shell windows and disables the
application's optional keyboard. It does not establish a product overlay or
Wayland input-method ownership. Follow-up must select stacking/overlay policy,
then run actual Moonlight with Hantro and compare overlay hidden/visible frame
pacing, colors and A/V. Keep global gamepad handoff/release and crash recovery as
separate gates; ordinary window focus cannot isolate games reading evdev.
[Weston seat/backend model](https://wayland.pages.freedesktop.org/weston/toc/running-weston.html)

The newer [handheld policy and composed-capture candidate](HANDHELD.md) has
headless composition and actual Qt/router/SDL checks, plus an optional shared-session
profile tested as an unprivileged user. R36's target follow-up proves actual status,
persistent Neo reboot-load and PortMaster catalog browsing; the accepted two-window
archive remains unchanged. R39's later GTA III diagnostic failed at the target GL
loader before a frame; [HANDHELD.md](HANDHELD.md) owns that negative result.
