# R46H project context

> Current checkpoint: 2026-09-20. Read the
> [experiment ledger](../mainline/board/r46h/EXPERIMENT-STATUS.md) before
> hardware work; it owns physical evidence and limitations.

## Scope

JumeOS targets the R46H with Linux 6.12, Debian 13, Panfrost, a Qt handheld
desktop, local gaming, streaming, and future USB HID support. The
[roadmap](PRODUCT-ROADMAP.md) owns product gates.

## Current baseline

The device is **powered off** after ES-DE, services and default
600--1008/200--480 MHz policies were restored following the 2026-09-19 Vice City
SGSR1 experiment. Health checks and `sync` passed, and temporary target
access/staging was removed. R74 is the accepted and source-build-default GTA
candidate after attended picture/audio/control approval; R63 and R60 remain
rollbacks. Latest experiment evidence is under
`mainline/out/.cache/r46h-sgsr-r76-device-20260919.Ryx78e/`.

- Fixed card profile: `hl-r46h-v22-g92-62534975488-v1`.
- Current p2: [v0.17](../mainline/rootfs-debian13-gaming-v17/README.md).
- Kernel/modules: `6.12.99-r46h-mainline-v0.15-gaming-product`, selected by the
  v0.17 BOOT/power-settle DTB.
- Accepted fallbacks: attended p2 v0.7, automated p2 v0.15, and the p2 v0.5
  full-card recovery reference.
- Installed frontend: ES-DE 3.4.1/r51. Jume Launcher `0.1.0-dev` remains an
  experimental, non-default Qt candidate.

The card's p3 contains imported EASYROMS. Its full target checksum/readback was
skipped, so content equality remains unverified. See
[P3 Content Migration](P3-CONTENT-MIGRATION.md).

## Current feature evidence

- Jume Launcher has machine proof for status values, storage/settings,
  PortMaster and routed remote control. R56 aligns Wi-Fi, battery and clock; R64
  captured the HUD's `GPU 200 MHz` matching target state. Physical LCD remains open.
  The `0.1.0-dev` name/version/About page passes host Qt tests. The R78 full
  handheld package pins R74 and passes host checks; target deployment remains open.
- Repaired GTA III/Vice City accept the Switch-layout controls and no longer
  reproduce the bounded-exit crash. GTA-only `noafbc`, first-config 640x480 and
  private Mesa 26.2.2 passed target integration. The R60 batch reached captured
  cutscenes, clean 121-second exits and relaunches without storage/GPU faults.
  The attended Vice City run found only a small 816-to-1296 MHz pacing gain before
  the 85 C abort; disabling its frame limiter and an exact-size immediate-buffer
  candidate both regressed and were restored. R62 then measured roughly 700--800
  tiny immediate uploads/s consuming 15--20% wall time. R63 reused fixed-capacity
  upload regions and raised the same 816/300 MHz median from 18.67 to 20.52
  client commits/s, with clean bounded exit and no thermal/GPU fault; one isolated
  1.116-second maximum interval remains in that machine sample. A same-boot R63
  follow-up at CPU 600--1008 MHz ran two 121-second Vice City bounds and one
  121-second GTA III bound at exit 0. Vice City's matched 480/400/300 MHz GPU
  medians were 23.08/22.91/22.46 submissions/s, so a 37.5% GPU-clock reduction
  cost only 2.7%; raw GPU throughput is not the primary cutscene limit. A later
  45-second HUD sample at 1008/480 MHz averaged 23.26 submissions/s, peaked at
  82.307 C and exited 0 after 115.16 seconds. Removing swap wait then produced
  only a 6.6% same-boot gain. R69's frame profiler measured 40.06 ms/frame after
  warm-up: `CRenderer::PreRender` led at 13.37 ms (33.4%), `RenderScene` used
  8.79 ms and swap used 3.66 ms. R71/R72 narrowed that cost to the per-character
  real-time cutscene shadow map. R73 replaced it with the existing ordinary-ped
  shadow fallback: matched profiler medians fell from 40.72 to 27.37 ms/frame
  and `PreRender` from 13.73 to 0.46 ms. The uninstrumented R74 run then recorded
  nine complete intro samples at 28.93 submissions/s and 33.89 ms median interval,
  captured the composed scene, and exited 0. The operator then accepted its LCD
  motion, picture, audio and controls; later open-world play remained below 30 FPS.
  A full-frame 480x360-to-640x480 SGSR1 experiment was rejected: the upstream
  shader failed Mesa/Panfrost GLSL compilation, and the fixed-mode specialization
  exited -11 before the frontend. No SGSR product code was retained.
  [Ports](../mainline/gaming-ports/README.md) owns exact pacing and thermal data.
- Stardew's source, managed copy and backup hashes match and overwrite is refused.
  R45's direct-display run crossed the SDL/GBM crash and stayed active for its
  full 120-second bound. Later shared-Wayland runs at two clock profiles stayed
  before window creation with no game submissions. R78 retains the exact accepted
  Mono/Mesa isolation shim; shared-window diagnosis, save/load and physical
  picture/audio/control evidence remain open.
- ES-DE's transient 33 ms idle pacing roughly halved settled CPU use and reduced
  temperature while retaining immediate input. The original executable remains
  installed; persistent promotion and physical patched LCD motion are open.
- A temporary ark-only three-action polkit rule passed scan, profile create/delete
  and saved-profile reconnect. The exact six-package/rule successor is now the
  byte-reproducible, independently validated v0.18 host artifact. Media deployment,
  new-password activation and reboot persistence remain. Bluetooth is blocked by
  absent controller/firmware and BlueZ.
- The isolated v0.18 zram kernel passed one-shot boot and 256 MiB LZ4 apply,
  pressure, disable and unload. Normal v0.15/media were restored; promotion waits
  for measurable real-game benefit.
- The CPU default keeps dynamic `schedutil` scaling but caps policy0 at the
  hardware's nearest 1 GHz OPP, 600--1008 MHz. Target apply/readback, game/thermal
  and warm-reboot persistence passed on the current v0.17 device. GPU devfreq and
  the frozen v0.18 image remain unchanged; next-image integration is open.
- Moonlight v5 passes a Linux-host H.264/PCM/controller loopback. R46H-to-LAN
  streaming is deferred by the user and remains open.
- The current image exposes DWC2 as host-only with no UDC, gadget, or role
  switch. USB HID needs hardware-route evidence and a separate recoverable
  kernel/DT candidate.

Exact observations and limitations remain in the
[ledger](../mainline/board/r46h/EXPERIMENT-STATUS.md) and the owning feature
runbooks.

## Immediate next work

1. Deploy exact p2 v0.18 through a fixed-profile write/readback, then verify cold
   identity, new-password activation, unrelated-action denial and reboot persistence.
2. Deploy R78 Jume Launcher `0.1.0-dev`; in the same guarded session confirm the
   retained R45 Stardew direct path and capture the shared-Wayland stall state.
   Make Launcher persistent only after cold-boot, settings, game-return and
   recovery gates pass; retain ES-DE rollback.
3. Continue R74 broader gameplay/save proof and profile the below-30-FPS
   open-world phase only when a new software hypothesis exists. Keep R63/R60
   available; do not repeat SGSR1 or a live GPU minimum-frequency raise unchanged.
4. Deferred: Bluetooth hardware, zram promotion/benefit, Moonlight, USB HID and
   other hardware-gated work until requested or its evidence changes.

## Working rules

- Branch `main` tracks `git@github.com:OJZen/JumeOS.git`.
- Keep generated artifacts and named evidence under ignored `mainline/out/` or
  `mainline/.cache/` on the external volume.
- Run only the focused test that owns a change; do not replay accepted hardware
  tests without a relevant implementation change.
- Keep host, media, machine, and operator proof separate.
- End unattended device work with health checks, `sync`, controlled poweroff,
  and serial confirmation. Never commit credentials.
