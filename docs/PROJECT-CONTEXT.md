# R46H project context

> Current checkpoint: 2026-09-27 (physical). Handoff reviewed: 2026-10-23 (host/docs only).
> Read the [experiment ledger](../mainline/board/r46h/EXPERIMENT-STATUS.md) before hardware work.

## Scope

JumeOS targets the R46H with Linux 6.12, Debian 13, Panfrost, a Qt handheld
desktop, local gaming, streaming, and USB HID input. The
[roadmap](PRODUCT-ROADMAP.md) owns product gates; [Jume desktop requirements](DEVICE-SHELL.md) map the scope and code owners.

## Workspace handoff

- `main` is at `87242d2`, 15 commits ahead of local `origin/main`, with a dirty worktree; no remote refresh, commit, push or device contact in this handoff.
- Pending desktop work: `product-fallback.py`, `test-jume-fallback.py`, CI and linked runbooks/index.
  Streaming Switch-loopback/test-client, general docs and untracked `CLAUDE.md` also have edits; preserve them and stage only intended paths.
- 2026-10-12 cache cleanup reclaimed 3.54 GiB; receipt: `mainline/out/.cache/cache-cleanup-20261012.XdQ4wD/receipt.json`.
  Clean compiler/source caches were removed; modified FBNeo/ES-DE sources, recovery data, Qt SDK, Mono and r6/r8/r9 were retained.
  Reacquire build inputs when required; the prepared r9 fallback overlay needs no Qt rebuild or TF rewrite.
- r9's 2 artifacts + 29 evidence files rehashed successfully on 2026-10-18.
  Candidate and device evidence: [installed-session runbook](../mainline/gaming-wayland/PRODUCT.md).
  Ignored `mainline/out/` is local-only, not supplied by a clone; verify receipt-bound inputs before reuse.

## Current baseline

Last observed device state: **serial-confirmed clean poweroff on 2026-09-27**, unchanged p2 v0.18,
inactive r9 selected, sealed r6/r8/private backups retained, ES-DE default and all 167 prior files unchanged.
The [r9 recovery and GUI reboot record](../mainline/gaming-wayland/PRODUCT.md#packaged-r9-recovery-and-gui-reboot--2026-09-27)
owns the latest result; historical host build notes' "next boot" steps are not the current plan.

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
  PortMaster and routed remote control. Home/About captures show aligned Wi-Fi,
  battery/charge, clock, `0.1.0-dev` and project URL; GPU HUD matches target state.
  R79 passed archive/1,741-file readback, preflight, transient lifecycle and forced-child recovery.
  Two-level pages passed 39 actions, unloaded focus navigation and in-flight cancellation.
  Cached categories raised Settings from ~29.5 to 57.2--57.5 submissions/s and HUD
  from 29.9 to 58.5--59.0, p50 ~16.7 ms; exact samples remain in the ledger.
  ES-DE/services recovered with zero failed units or kernel/ext4/OOM errors; physical LCD/readability, L3+R3 and persistent promotion remain open.
  The [top-center volume capsule](../mainline/gaming-shell/DEVICE.md) passes ARM64 UI/event and Pixman/GL clipping checks;
  paired binaries ran during Transfer testing; attended screen-wake/HUD passed on 2026-09-26; in-game acceptance remains open.
- Repaired GTA III/Vice City accept the Switch-layout controls and no longer
  reproduce the bounded-exit crash. GTA-only `noafbc`, first-config 640x480 and
  private Mesa 26.2.2 passed target integration. The R60 batch reached captured
  cutscenes, clean 121-second exits and relaunches without storage/GPU faults.
  R62/R63 isolated tiny-buffer upload cost; fixed-capacity reuse improved pacing.
  Matched GPU-clock samples ruled out raw GPU throughput as the primary cutscene limit.
  R69/R72 isolated per-character shadow maps; R73's ordinary-ped fallback cut
  profiler medians from 40.72 to 27.37 ms/frame. The uninstrumented R74 recorded
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
  Host guards and target active-app/missing-module refusals pass; normal v0.15/media remain the accepted fallback. Build and persistent proof are open.
- The requested CPU default is dynamic `schedutil` at 600--1008 MHz; earlier
  target/game/thermal and v0.17 warm-reboot checks passed. The current frozen p2
  v0.18 restores 600--1296 MHz outside Jume's transient scene policy, confirmed
  on 2026-09-27. Default-cap image integration remains open; GPU devfreq is unchanged; kernel suspend stays disabled.
- Moonlight v5 passes the Linux-host H.264/PCM/controller loopback with [Switch Pro emulation](../mainline/gaming-stream-input-test/README.md#automated-protocol-check).
  The 2026-10-18 configuration change and rerun are host-only; R46H-to-LAN streaming remains deferred and open.
- [USB keyboard/mouse and Terminal](../mainline/gaming-wayland/PERIPHERALS.md) passed sequential attended keyboard typing/editing/Ctrl+C/D/reconnect and mouse cursor/move/click/scroll/reconnect. Simultaneous hub use and browser/game-specific focus remain open.
  DWC2 is host-only; USB **gadget** mode still needs hardware-route evidence and a recoverable kernel/DT candidate.
- [Jume Files/Text](../mainline/gaming-files/README.md) passes target launch/privacy/exit and nine ARM64 offscreen functional cases. [Transfer](../mainline/gaming-files/TRANSFER.md) passes real Wi-Fi 16 MiB hash roundtrip, cancellation, readonly ROMs and disconnect revocation. Phone QR, physical controls/USB/A/V and promotion remain open; [file layout](FILESYSTEM-LAYOUT.md) preserves legacy data.
- [Background tasks](../mainline/gaming-shell/APPLICATIONS.md) passed corrected target close/kill/two-app checks and attended faster entry/preview, resume and normal close. Physical long-hold kill and real game/transfer retention remain open. ES-DE remains default.
- [Jume Browser](../mainline/gaming-browser/README.md) is an optional Chromium/
  Qt WebEngine preview with dual-stick control, tabs/address/IME and launcher
  lifecycle/privacy integration. WebEngine 6.10.2 retains base Qt 6.8.2; both About
  pages show engine/security versions. Host/target input, IME, Panfrost WebGL 2,
  sandbox, About, exit/relaunch and capture privacy pass. Attended mi.com failed:
  first policy rejection unexplained; second global OOM killed renderer/shared unit.
  A 128 MiB tile budget passed offline pressure and target regression. Background
  discard failed form-retention testing and was withdrawn. The browser-only cgroup passes target limit/child-kill, paired smoke and actual browser OOM/relaunch with the same launcher surviving; heavy-site/security/promotion remain open.

## Immediate next work

1. [Q1: Jume default with ES-DE crash recovery](../mainline/gaming-wayland/PRODUCT.md#optional-r9-es-de-fallback-overlay) is prepared and host-tested, not deployed; the user deferred device connection. Review the pending patch, then resume item 4 when connected.
   Use the [combined acceptance route](../mainline/gaming-shell/DEVICE.md#combined-acceptance-route) for remaining long-hold kill,
   game/save/transfer retention, Files/QR, LCD/audio and L3+R3 observations.
   Media, sequential USB, wake/HUD and task entry/resume/close already pass; do not replay them unchanged.
2. Prove launcher-created Wi-Fi profile activation/persistence and genuine newer-version
   PortMaster updates/game saves. Target live catalog, isolated install/same-release
   replacement/rollback/uninstall and synthetic-save preservation passed; no game was run.
3. Keep R45 direct Stardew as fallback. Revisit the shared-Wayland stall only
   with a new source-level hypothesis; the unchanged R78/R79 Mono/Mesa path has
   already failed before window creation at two clock profiles.
4. Continue [installed r9](../mainline/gaming-wayland/PRODUCT.md): packaged failed-state rollback, release cycling, cleanup-receipt refusal/recovery, GUI warm reboot and 167-file retention pass. Two-hour endurance, GUI poweroff, actual interrupted lease cleanup and cold default boot remain open; receipt mismatch is not interruption proof.
   ES-DE stays the recovery frontend. L1 library coverage and Q2 full removal/endurance are separate from Q1 default-boot delivery; see the [desktop handoff](DEVICE-SHELL.md).
5. Profile R74's below-30-FPS open-world phase only when a new software hypothesis
   exists. Keep R63/R60 available; do not repeat SGSR1 or a live GPU minimum-frequency
   raise unchanged.
6. Build v0.19 from clean committed inputs when Linux build resources are available;
   use the guarded zram installer, accepted v0.17 DTB and existing boot fallback.
   Use Docker only for temporary memory-limited builds; v0.19 still has no product artifact or persistent proof.
7. Retain the [paired browser memory boundary](../mainline/gaming-browser/README.md#browser-memory-boundary--source-candidate)
   for subsequent heavy-page trials; target memcg and actual browser recovery now pass.
   Do not equate induced group OOM recovery with mi.com performance or global-OOM immunity.
   Upgrade the security baseline before ordinary Internet use; no newer package was listed in the pinned Debian channel.
8. Deferred: Moonlight, USB gadget and other hardware-gated work until requested or its evidence changes.

## Working rules

- Branch `main` tracks `git@github.com:OJZen/JumeOS.git`.
- Keep generated artifacts and named evidence under ignored `mainline/out/` or
  `mainline/.cache/` on the external volume.
- Run only the focused test that owns a change; do not replay accepted hardware
  tests without a relevant implementation change.
- Keep host, media, machine, and operator proof separate.
- End unattended device work with health checks, `sync`, controlled poweroff and serial confirmation. Never commit credentials.
