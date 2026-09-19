# R46H project context

> Current checkpoint: 2026-09-17. Read the
> [experiment ledger](../mainline/board/r46h/EXPERIMENT-STATUS.md) before
> hardware work; it owns physical evidence and limitations.

## Scope

JumeOS targets the R46H with Linux 6.12, Debian 13, Panfrost, a Qt handheld
desktop, local gaming, streaming, and future USB HID support. The
[roadmap](PRODUCT-ROADMAP.md) owns product gates.

## Current baseline

The device was last left **powered off** after the 2026-09-17 attended R60
Vice City performance batch. Exact v0.17/R60 identity, service restoration,
temporary-access cleanup, `sync` and controlled shutdown passed. The operator
accepted Vice City intro LCD motion, audio and controls at temporary 816/300 MHz;
broader gameplay, saves and GTA III physical acceptance remain open. Exact evidence
is `mainline/out/.cache/r46h-attended-cooling-20260917.vlknbF/session.json`.

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
  PortMaster and routed remote control. R56 aligns Wi-Fi, battery, clock and the
  clipped game HUD in composed output; physical LCD confirmation remains open.
  The `0.1.0-dev` name/version/About page passes host Qt tests and awaits target deployment.
- Repaired GTA III/Vice City accept the Switch-layout controls and no longer
  reproduce the bounded-exit crash. GTA-only `noafbc`, first-config 640x480 and
  private Mesa 26.2.2 passed target integration. The R60 batch reached captured
  cutscenes, clean 121-second exits and relaunches without storage/GPU faults.
  The attended Vice City run found only a small 816-to-1296 MHz pacing gain before
  the 85 C abort; disabling its frame limiter and an exact-size immediate-buffer
  candidate both regressed and were restored. Profiling instead points to repeated
  Panfrost buffer wait/map churn as the next software investigation;
  [ports](../mainline/gaming-ports/README.md) owns exact pacing and thermal data.
- Stardew's source, managed copy and backup hashes match and overwrite is refused.
  Its 120-second runs still remain before SDL/Wayland at both tested clock profiles;
  shared-window save selection/load and all attended gameplay evidence stay open.
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
2. Before another GTA buffer change, run the host-built, behavior-preserving
   immediate-upload profiler at 816/300 MHz; use its per-second call/byte/CPU-time
   data to decide whether a ring upload is justified. Then batch remaining attended
   gameplay/save observations; keep Stardew's shared-window/save-load gate separate.
3. Deferred: Bluetooth hardware, zram promotion/benefit, Moonlight, USB HID and
   dynamic frequency policy until requested or their hardware gates change.

## Working rules

- Branch `main` tracks `git@github.com:OJZen/JumeOS.git`.
- Keep generated artifacts and named evidence under ignored `mainline/out/` or
  `mainline/.cache/` on the external volume.
- Run only the focused test that owns a change; do not replay accepted hardware
  tests without a relevant implementation change.
- Keep host, media, machine, and operator proof separate.
- End unattended device work with health checks, `sync`, controlled poweroff,
  and serial confirmation. Never commit credentials.
