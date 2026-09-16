# R46H private Mesa runtime

Status 2026-09-16: **MESA 26.2.2 GTA III/VC PERFORMANCE + BATCHED TARGET PASS / ATTENDED OPEN**.

This feature pins the Panfrost/softpipe Mesa 26.2.2 EGL, GBM and Gallium ABI
closure used only by the shared Wayland game session. It does not replace Debian
packages or the normal ES-DE graphics stack. `source-lock.json` owns the upstream
archive, build configuration and every runtime member; `runtime.py` refuses a
different archive or an overwrite during assembly.

The source was built in the pinned ARM64 SDK with the recorded Meson options and
external LLVM 19 development inputs. The normalized runtime is expected at
`mainline/out/.cache/r46h-mesa-26.2.2/r60/mesa-26.2.2-r46h-runtime.tar.gz`.
Validate it directly or let `gaming-wayland/build-handheld.sh` validate and add it:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B mainline/gaming-mesa/runtime.py \
  validate-runtime mainline/out/.cache/r46h-mesa-26.2.2/r60/mesa-26.2.2-r46h-runtime.tar.gz
```

The tested 816/300 MHz same-boot intro windows improved from 11.00 to 14.36
submissions/s in GTA III and from 14.67 to 17.15/s in Vice City. Both candidate
runs exited 0 below 81 C without cooling-state throttling or a new Panfrost fault;
the original Mesa GTA III comparison added one `DATA_INVALID_FAULT`. These are
compositor submissions, not proof of LCD motion, audible output, gameplay or saves.
A preceding Gallium-only frontend trial segfaulted without a GPU fault, so it is
rejected; the complete private ABI closure is the smallest supported deployment.

Clean source `495c35232176f0c6ca39a93fd6ab4ac1f02e70bd` produced the formal
1,741-file package with archive SHA-256
`0a0861bb2d4713f79cf198a50f8fed9cf37b9a174a7c3df9fb510fc90aaf20b3`.
Host checks and exact R46H preflight passed. Weston, the shell and GTA III mapped
the private files; GTA III reported Mesa 26.2.2, rendered a captured intro and
exited 0 at its 121.15-second bound without a forced kill or new GPU fault. The
system Mesa, services and stock clocks were restored and temporary access was
removed. Exact evidence is
`mainline/out/.cache/r46h-r60-formal-device-20260915/session.json`. At that
checkpoint, physical LCD motion, audio, controls, gameplay, saves and relaunch
were open.

A later power-backed batch revalidated the exact archive and target preflight,
then drove GTA III and Vice City through two remote South/B samples into captured
640x480 cutscenes at temporary 816/300 MHz caps. The captures reported
20.32 submissions/s with 43.19 ms median/54.18 ms P95 intervals for GTA III and
19.03/s with 50.15/61.78 ms for Vice City. Their 120.97/121.15-second bounds
exited 0 without a forced kill. Fresh sessions relaunched both games; Vice City's
second run stopped on request at 28.56 seconds without a forced kill. No cooling
state or ext4/Panfrost/GPU fault appeared, and stock clocks, ES-DE and temporary
access/runtime state were restored before serial-confirmed poweroff. Evidence is
`mainline/out/.cache/r46h-unattended-20260916/session.json`. These are composed
frame and remote-input results, not physical LCD/audio/control/gameplay/save proof.
