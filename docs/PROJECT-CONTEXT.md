# R46H project context

> Current checkpoint: 2026-09-13. Read the
> [experiment ledger](../mainline/board/r46h/EXPERIMENT-STATUS.md) before
> hardware work; it owns physical evidence and limitations.

## Scope

JumeOS targets the R46H with Linux 6.12, Debian 13, Panfrost, a Qt handheld
desktop, local gaming, streaming, and future USB HID support. The
[roadmap](PRODUCT-ROADMAP.md) owns product gates.

## Current baseline

The device is **on at ES-DE** after the R45 differential Stardew probe. The
fixed kernel, card CID, root UUID and read-only ROM mount were reconfirmed from
a cold-boot serial capture. Temporary package staging remains only for the
immediate clean-package follow-up.

- Fixed card profile: `hl-r46h-v22-g92-62534975488-v1`.
- Current p2: [v0.17](../mainline/rootfs-debian13-gaming-v17/README.md).
- Kernel/modules: `6.12.99-r46h-mainline-v0.15-gaming-product`, selected by the
  v0.17 BOOT/power-settle DTB.
- Accepted fallbacks: attended p2 v0.7, automated p2 v0.15, and the p2 v0.5
  full-card recovery reference.
- Installed frontend: ES-DE 3.4.1/r51. The Qt shell remains an experimental,
  non-default candidate.

The card's p3 contains imported EASYROMS. Its full target checksum/readback was
skipped, so content equality remains unverified. See
[P3 Content Migration](P3-CONTENT-MIGRATION.md).

## Current feature evidence

- The Qt candidate has machine proof for battery percentage, charging state,
  Wi-Fi signal, temperature, frequency, Neo Geo state persistence, and the
  PortMaster catalog. Physical UI controls, LCD motion, and sustained thermal
  acceptance remain open.
- R42 source-built GTA III and Vice City used Panfrost OpenGL ES 3.1, reached
  their target frontends, ran for 120 seconds, and returned to the tools UI.
  Gameplay, display, audio, controls, saves, and relaunch are not yet accepted.
- R43 repeated all 1,630 hashes but still failed in SDL/GBM after 10.31 seconds;
  neither its DRI match nor R44's Gallium-name match reached the real loader.
  R45 instead preloads the exact Debian Gallium provider with local symbol
  scope. Its differential probe ran Stardew for the full 120.7-second bound,
  returned cleanly and kept the original saves read-only. A clean full-package
  repeat is still required before promotion.
- Moonlight v5 passes a Linux-host H.264/PCM/controller loopback. R46H-to-LAN
  streaming is deferred by the user and remains open.
- The current image exposes DWC2 as host-only with no UDC, gadget, or role
  switch. USB HID needs hardware-route evidence and a separate recoverable
  kernel/DT candidate.

Exact observations and limitations remain in the
[ledger](../mainline/board/r46h/EXPERIMENT-STATUS.md) and the owning feature
runbooks.

## Immediate next work

1. Build and repeat R45 as an exact clean-source package, then remove its temporary target state.
2. Run attended GTA III/Vice City gameplay, audio, controls, save, exit, and relaunch checks.
3. Keep Moonlight paused until requested.
4. Investigate a physically reachable USB peripheral route before writing gadget code.
5. Batch remaining physical L3/R3, LCD, audio, and stream-control observations.

## Working rules

- Branch `main` tracks `git@github.com:OJZen/JumeOS.git`.
- Keep generated artifacts and named evidence under ignored `mainline/out/` or
  `mainline/.cache/` on the external volume.
- Run only the focused test that owns a change; do not replay accepted hardware
  tests without a relevant implementation change.
- Keep host, media, machine, and operator proof separate.
- End unattended device work with health checks, `sync`, controlled poweroff,
  and serial confirmation. Never commit credentials.
