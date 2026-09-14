# R46H project context

> Current checkpoint: 2026-09-14. Read the
> [experiment ledger](../mainline/board/r46h/EXPERIMENT-STATUS.md) before
> hardware work; it owns physical evidence and limitations.

## Scope

JumeOS targets the R46H with Linux 6.12, Debian 13, Panfrost, a Qt handheld
desktop, local gaming, streaming, and future USB HID support. The
[roadmap](PRODUCT-ROADMAP.md) owns product gates.

## Current baseline

The device is **off** after the R56 status/GTA diagnostic. Serial confirmed
sync, filesystem unmount, loop/MD/DM detach and `Powering off.` Temporary target
staging, the one-time key and the host serial bridge were removed.

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
- R48's repaired source-built GTA III and Vice City use Panfrost OpenGL ES 3.1.
  The operator accepted both intro starts and GTA III D-pad Down after the
  no-`O_NOATIME` and 10% deadzone repair, but reported abnormally slow motion.
- R43/R44 still failed in SDL/GBM because their wrappers missed the real loader.
  R45 preloads the exact Debian Gallium provider with local symbol scope. Its
  exact 1,630-file package ran Stardew for the full 120.6-second bound, returned
  cleanly and kept the original saves read-only. LCD, audio, physical controls,
  gameplay, save/load and relaunch remain operator-open.
- R47 imported the retained Stardew save through the product worker, preserved
  equal source/copy hashes and refused a second overwrite. Stardew then ran its
  120-second machine bound; no operator display/audio/gameplay result was given.
- R51 reuses the shared compositor's existing performance HUD, capture and
  bounded gamepad RPC. Its 1,726 files and preflight passed on target. A composed
  GTA III menu measured 25.6 game submissions/s (36.3 ms median, 43.6 ms P95)
  at the temporary 1008/400 MHz caps, and one remote Down sample completed.
  The first run reached the 85 C guard; both runs restored ES-DE and all leases.
  Displayed LCD FPS, GTA gameplay/audio/saves/relaunch and shared Vice City remain open.
- R54 replaces the GTA development profile with upstream `MASTER`/`FINAL`.
  Its 1,727 files and preflight passed on target. At the same 1008/400 MHz caps,
  GTA III averaged 26.84 submissions/s with the resident HUD and 30.43/s with
  it hidden; the full-screen transparent HUD is a material compositor cost.
  The hottest GPU sample was 83.846 C. All runs exited without a forced kill,
  but remote confirm did not leave the main menu, so intro/crash proof stays open.
- R56 retains R55's clipped game HUD and aligns the top-right Wi-Fi, battery and
  clock with shared icon boxes, gaps, caption size and centerline. Its complete
  1,727-file readback and preflight passed on R46H. A Weston capture shows the
  status row aligned and the HUD confined to the top-right over a real GTA III
  intro frame; physical LCD confirmation remains open.
- GTA III intro pacing stayed abnormally low with the HUD hidden: seven samples
  averaged 5.57 submissions/s (median 5.00), with 121.24--226.62 ms median frame
  intervals at the same 1008/400 MHz caps. The HUD-on recorder covered only three
  samples from a different intro phase, so it is not a matched comparison. The
  observed disappearance at 121.17 seconds was the diagnostic bound's forced kill,
  not a reproduced natural crash. That run alone could not separate Panfrost
  runtime faults from its forced cleanup; R57 resolves that boundary below.
- R57 keeps the one-second shared user-stop deadline but gives a diagnostic's
  self-triggered bound the existing five-second cleanup grace. On R46H, two GTA III
  bounds ended in 120.97/121.05 seconds with exit 0 and no forced kill, proving the
  lifecycle fix. Panfrost `DATA_INVALID_FAULT` events occurred while the game was
  still active, however, so they are a runtime fault rather than a forced-cleanup
  artifact.
- A similar roughly 59-second intro window averaged 5.59 submissions/s at
  1024x768 and 12.32/s at a temporary 640x480. The lower resolution also reached
  active thermal cooling from a hot start and did not prevent two Panfrost faults;
  it is evidence for a rendering-cost bottleneck, not an accepted default. The
  original configuration was hash-restored before poweroff.
- Moonlight v5 passes a Linux-host H.264/PCM/controller loopback. R46H-to-LAN
  streaming is deferred by the user and remains open.
- The current image exposes DWC2 as host-only with no UDC, gadget, or role
  switch. USB HID needs hardware-route evidence and a separate recoverable
  kernel/DT candidate.

Exact observations and limitations remain in the
[ledger](../mainline/board/r46h/EXPERIMENT-STATUS.md) and the owning feature
runbooks.

## Immediate next work

1. Isolate the GTA/Panfrost runtime fault with one bounded hypothesis; do not treat
   the now-proven graceful exit as a graphics fix.
2. Recheck the 640x480 performance candidate from a cooled start and obtain physical
   LCD quality acceptance before choosing a product default.
3. Measure natural intro/gameplay/exit behavior, then recheck shared Vice City.
4. Finish Stardew display/audio/gameplay/save/relaunch acceptance when attended.
5. Keep Moonlight paused until requested; keep USB HID as a separate hardware-route gate.

## Working rules

- Branch `main` tracks `git@github.com:OJZen/JumeOS.git`.
- Keep generated artifacts and named evidence under ignored `mainline/out/` or
  `mainline/.cache/` on the external volume.
- Run only the focused test that owns a change; do not replay accepted hardware
  tests without a relevant implementation change.
- Keep host, media, machine, and operator proof separate.
- End unattended device work with health checks, `sync`, controlled poweroff,
  and serial confirmation. Never commit credentials.
