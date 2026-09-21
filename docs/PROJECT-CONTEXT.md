# R46H project context

> Current checkpoint: 2026-09-21. Read the
> [experiment ledger](../mainline/board/r46h/EXPERIMENT-STATUS.md) before
> hardware work; it owns physical evidence and limitations.

## Scope

JumeOS targets the R46H with Linux 6.12, Debian 13, Panfrost, a Qt handheld
desktop, local gaming, streaming, and future USB HID support. The
[roadmap](PRODUCT-ROADMAP.md) owns product gates.

## Current baseline

The device is **off after browser memory testing and clean shutdown** with exact p2 v0.18. Fixed-profile write/readback,
cold identity, service health, exact policy/package hashes, permission scope and
the full base smoke pass. A reset after an unconfirmed serial staging attempt
also recovered cleanly with zero ext4/kernel faults. R79 then passed exact
archive and 1,741-file manifest readback, v0.18 preflight, transient Launcher,
game lifecycle and forced-child recovery without replacing ES-DE. R74 is the
accepted and source-build-default GTA
candidate after attended picture/audio/control approval; R63 and R60 remain
rollbacks. Latest base-image evidence is under `mainline/out/.cache/r46h-v018-device-20260920.FoS3wK/`;
latest launcher evidence is under `mainline/out/.cache/r46h-profile-device-20260921/evidence/`.

- Fixed card profile: `hl-r46h-v22-g92-62534975488-v1`.
- Current card p2: [v0.18](../mainline/rootfs-debian13-gaming-v18/README.md)
  (cold base pass; network persistence and product acceptance open).
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
  captured the HUD's `GPU 200 MHz` matching target state. R79 composed Home and
  About captures show the aligned status row, live battery/charge state,
  `0.1.0-dev` and the project URL on v0.18. Repeated normal expiry and a forced
  input-router failure restored all services and removed transient leases.
  The 2026-09-20 two-level candidate passed 39 target actions: focus motion left
  Settings, Neo and PortMaster details unloaded; open/return and in-flight
  PortMaster cancellation passed. On v0.18, caching the category list separately
  raised two Settings focus runs from about 29.5 to 57.2--57.5 submissions/s;
  HUD runs rose from 29.9 to 58.5--59.0, with p50 near 16.7 ms.
  ES-DE/services recovered with zero failed units or kernel/ext4/OOM errors; physical LCD/readability, L3+R3 and persistent promotion remain open.
- Repaired GTA III/Vice City accept the Switch-layout controls and no longer
  reproduce the bounded-exit crash. GTA-only `noafbc`, first-config 640x480 and
  private Mesa 26.2.2 passed target integration. The R60 batch reached captured
  cutscenes, clean 121-second exits and relaunches without storage/GPU faults.
  R62/R63 isolated tiny-buffer upload cost; fixed-capacity reuse improved pacing.
  Matched 480/400/300 MHz GPU samples then differed by only 2.7%, ruling out raw
  GPU throughput as the primary cutscene limit. R69/R72 traced the remaining
  bottleneck to per-character cutscene shadow maps. R73's ordinary-ped shadow
  fallback cut profiler medians from 40.72 to 27.37 ms/frame and `PreRender` from
  13.73 to 0.46 ms. The uninstrumented R74 run then recorded
  nine complete intro samples at 28.93 submissions/s and 33.89 ms median interval,
  captured the composed scene, and exited 0. The operator then accepted its LCD
  motion, picture, audio and controls; later open-world play remained below 30 FPS.
  A full-frame 480x360-to-640x480 SGSR1 experiment was rejected: the upstream
  shader failed Mesa/Panfrost GLSL compilation, and the fixed-mode specialization
  exited -11 before the frontend. No SGSR product code was retained.
  R79 repeated both accepted engines through Jume Launcher: two routed B presses
  reached distinct GTA III and Vice City startup-animation captures, 20-second
  samples stayed near 25--30 compositor submissions/s, mostly at 480 MHz GPU and below
  81 C, and both returned cleanly. This is machine/composed evidence, not broader
  play, saves, physical LCD, audio or controls.
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
  byte-reproducible, independently validated v0.18 artifact. Media/cold base and
  exact policy permission checks pass. Correcting the saved profile's truncated
  SSID enabled activation/transfer and the next cold boot autoconnected; launcher-created
  profile activation/persistence remain open. The exact board has no onboard Bluetooth controller, and
  the corresponding launcher category has been removed.
- The isolated v0.18 zram kernel passed one-shot boot and 256 MiB LZ4 apply,
  pressure, disable and unload. The requested v0.19 product source now carries
  the same module configuration and an exact-kernel 256 MiB LZ4 startup service.
  Normal v0.15/media remain the accepted fallback; build and persistent proof are open.
- The CPU default keeps dynamic `schedutil` scaling but caps policy0 at the
  hardware's nearest 1 GHz OPP, 600--1008 MHz. Target apply/readback, game/thermal
  and warm-reboot persistence passed on the current v0.17 device. GPU devfreq and
  the frozen v0.18 image remain unchanged; next-image integration is open.
- Moonlight v5 passes a Linux-host H.264/PCM/controller loopback. R46H-to-LAN
  streaming is deferred by the user and remains open.
- The current image exposes DWC2 as host-only with no UDC, gadget, or role
  switch. USB HID needs hardware-route evidence and a separate recoverable
  kernel/DT candidate.
- [Jume Browser](../mainline/gaming-browser/README.md) is an optional Chromium/
  Qt WebEngine preview with dual-stick control, tabs/address/IME and launcher
  lifecycle/privacy integration. WebEngine 6.10.2 retains base Qt 6.8.2; both About
  pages show engine/security versions. Host/target input, IME, Panfrost WebGL 2,
  sandbox, About, exit/relaunch and capture privacy pass. Attended mi.com failed:
  first policy rejection unexplained; second global OOM killed renderer/shared unit.
  A 128 MiB tile budget passed offline pressure and target regression. Background
  discard failed form-retention testing and was withdrawn. Heavy-site/OOM isolation remain open.

Exact observations remain in the [ledger](../mainline/board/r46h/EXPERIMENT-STATUS.md) and feature runbooks.

## Immediate next work

1. Continue the [combined acceptance route](../mainline/gaming-shell/DEVICE.md#combined-acceptance-route)
   with operator LCD/readability/L3+R3 checks, retained Metal Slug state and R74
   GTA broader play/save/relaunch. Automated transient launch, exit and recovery
   already pass; do not replay them unchanged.
2. Prove launcher-created Wi-Fi profile activation/persistence;
   run live PortMaster install/update/remove
   while preserving user data. Offline refresh currently returns zero entries.
3. Keep R45 direct Stardew as fallback. Revisit the shared-Wayland stall only
   with a new source-level hypothesis; the unchanged R78/R79 Mono/Mesa path has
   already failed before window creation at two clock profiles.
4. Make Jume Launcher persistent and remove ES-DE only after the remaining
   operator, network/package and save gates pass.
5. Profile R74's below-30-FPS open-world phase only when a new software hypothesis
   exists. Keep R63/R60 available; do not repeat SGSR1 or a live GPU minimum-frequency
   raise unchanged.
6. Build the v0.19 zram product artifact and prepare a rollback-safe persistent
   successor using the accepted v0.17 DTB; physical deployment remains a separate gate.
7. Isolate browser OOM recovery and validate a bounded swap/zram candidate
   before further heavy-page acceptance; keep the accepted desktop. Upgrade its
   security baseline before ordinary Internet use.
8. Deferred: Moonlight, USB HID and other hardware-gated work until requested or
   its evidence changes.

## Working rules

- Branch `main` tracks `git@github.com:OJZen/JumeOS.git`.
- Keep generated artifacts and named evidence under ignored `mainline/out/` or
  `mainline/.cache/` on the external volume.
- Run only the focused test that owns a change; do not replay accepted hardware
  tests without a relevant implementation change.
- Keep host, media, machine, and operator proof separate.
- End unattended device work with health checks, `sync`, controlled poweroff,
  and serial confirmation. Never commit credentials.
