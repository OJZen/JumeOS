# R46H experiment status ledger

> Current checkpoint: 2026-09-20. This is the authoritative index of accepted
> physical evidence and open hardware gates. Exact commands, hashes and raw
> receipts stay in the linked owning runbooks.

## How to read this ledger

**PASS** is accepted only for its stated boundary; **FAIL** needs a new hypothesis,
**REVOKED** cannot authorize later work, and **OPEN** has not passed. Host, media,
machine and operator evidence remain distinct.

## Current accepted first version and next gate

The last fully read-back full-card release is `build-2e0d33a53f11-e1e8d9edb2f8`
for `hl-r46h-v22-g92-62534975488-v1`: v0.17 BOOT/power settle selects the exact
v0.15 Image/modules and Debian 13 gaming p2 v0.5. Cold boot and identity passed.

The current card's EASYROMS p3 import passed write, eject and physical use; its
full target checksum/readback was skipped, so equality remains unverified; see
[P3 Content Migration](../../../docs/P3-CONTENT-MIGRATION.md).

Fallbacks are p2 v0.7 attended and v0.15 automated; v0.17 passed readbacks/cold/warm infra.
Exact p2 v0.18 passes fixed-profile write/full readback, cold identity, policy
scope and full base smoke; new Wi-Fi activation/reboot persistence, LCD, USB,
Moonlight and PSP remain open.

## Capability ledger

- **Full-card first version v0.1 — HOST + MEDIA + PHYSICAL PASS.** Current p2/p3 later changed.
- **Original-card EASYROMS — P3 WRITE/PHYSICAL PASS; READBACK UNVERIFIED.** Checksums were skipped.
- **Cold MMC — V0.17 ONE-SHOT + TWO PERSISTENT PASS / RELIABILITY OPEN.**
  Three SDR104/150 MHz samples had no MMC/ext4 fault; v0.16 reproduced the fault
  and was rolled back. Do not loop unchanged boots.
- **Debian 13 gaming p2 v0.7 — HOST + P2 MEDIA + PHYSICAL PASS.** Readbacks and cold product passed.
- **Debian 13 gaming p2 v0.15 — HOST + P2 MEDIA + DEVICE AUTOMATION PASS /
  ATTENDED OPEN / DREAMCAST FAIL.** Build/readback, game automation, reboot and health passed.
- **Debian 13 gaming p2 v0.16 — HOST + P2 MEDIA + DEVICE INFRA PASS / PRODUCT
  FAIL.** ES-DE merged bundled Dreamcast and loaded 14 systems instead of 13.
- **Debian 13 gaming p2 v0.17 exclusive systems — HOST + P2 MEDIA + DEVICE
  INFRA + STICK SMOKE PASS / SAVE MENU FAIL / PSP DEFERRED.** Identity, 13 systems,
  controls, captures and health passed; custom cores lack Ozone save discovery.
- **Persistent v0.15 BOOT — PASS.** Fallbacks and U-Boot environment stay unchanged; never use `saveenv`.
- **Panel handoff — FIRST BOOT PASS / FULL INIT + KMS OPEN.** Full DCS/KMS remains open.
- **Panfrost — BASE PROBE PASS / FLYCAST GAMEPLAY FAIL.** Flycast faults; llvmpipe XRUNs at ~300% CPU.
- **Combined gaming input — COMPOSITE PHYSICAL + V0.17 STICK PASS.** Sixteen keys and four axes passed.
- **Inherited F5/GPIO2_A4 — PARTIAL / DT-HARDWARE MISMATCH.** Require schematic or continuity evidence.
- **Debian-native gaming MVP — PASS.** `1944.zip` passed; `1943.zip` jammed. Broad compatibility is open.
- **Ozone + FBNeo/Metal Slug — HOST + TARGET + PHYSICAL PASS / MILD PACING OPEN.**
  Guarded install, clean UniBIOS frames and advancing frame 480 passed; the
  operator accepted clean LCD startup and gameplay. Mild pacing artifacts remain.
- **ES-DE successor — HOST + POWER-BACKED TRANSIENT TARGET + GAME PHYSICAL PASS /
  PERSISTENT PROMOTION + PATCHED LCD MOTION OPEN.**
  NES/Metal Slug and 60 FPS original-art capture passed. Transient idle pacing cut
  CPU 51.16% to 25.08% and GPU 82.45 C to 72.34 C while preserving immediate input;
  a power-backed repeat held 23.57% CPU and changed the DRM frame after input.
  Exact restoration passed; promotion, physical patched motion, CJK and startup remain open.
- **Remote screen — V0.16/V0.17 ANCHORED GUARD DEVICE PASS.** ES-DE-only,
  ES-DE-plus-Game Gear and PPSSPP-after-`comm=Main` captures passed; pairing is
  still required after a new image write.
- **Remote input — V0.16/V0.17 10 MS DEVICE PASS.** Self-test and exact
  screenshot-verified right/left single-step roundtrip passed; v0.15 uses 100 ms.
- **[Jume Launcher](../../gaming-shell/DEVICE.md) — R79 DEVICE/RECOVERY PASS / PHYSICAL + PROMOTION OPEN.**
  R79 passed exact archive/1,741-file target readback and preflight. Composed Home
  and About captures show the aligned Wi-Fi/battery/clock row, live charge state,
  version and project URL. Normal expiry and forced input-router failure restored
  ES-DE and all transient leases. Physical LCD/readability, L3+R3 and persistent
  replacement remain open.
- **CPU 600--1008 MHz default — HOST + TARGET + WARM-REBOOT PASS / IMAGE OPEN.**
  Dynamic `schedutil` and both GTA engines passed; reset recovered a live GPU-min panic. Do not repeat it.
- **Wayland/ports — R74 SHORT ATTENDED + R79 TRANSIENT MACHINE PASS / BROADER PLAY OPEN.**
  R48 fixed D-pad Down; 640x480, first-config and [private Mesa](../../gaming-mesa/README.md)
  passed. R60's Vice City LCD/audio/controls passed at 816/300 MHz. R62 found
  15--20% wall time in tiny uploads; R63 raised the same-clock median 18.67→20.52/s.
  At 1008 MHz CPU, matched 480/400/300 MHz GPU medians were 23.08/22.91/22.46/s;
  a later R63 run averaged 23.26/s, and R66's no-wait gain was only 6.6%.
  R69 put 13.37 of 40.06 ms/frame in `PreRender`; R72 isolated 11.8--16.1 ms in
  cutscene shadows, and R73 cut median total frame time from 40.72 to 27.37 ms. R74 captured
  the intro, recorded nine complete samples at 28.93/s and 33.89 ms median interval,
  exited 0 after 121.06 seconds and peaked at 80.384 C. R75 accepted picture/motion,
  audio and controls; open-world play stayed below 30 FPS, and saves remain open.
  R79 then routed two B presses into each accepted engine, captured distinct GTA III
  and Vice City startup animations, sampled roughly 25--30 compositor submissions/s
  below 81 C and returned to Jume Launcher with clean lease/service restoration.
  Neo launch/menu/exit also passed. The offline PortMaster catalog was empty, so
  live package lifecycle, broader GTA play/save and Stardew remain open.
  A 480x360 SGSR1 candidate failed Mesa compilation, then its fixed-mode variant
  exited -11 before the frontend. R63/R60 remain rollbacks.
- **GLES2 frontend — V0.7 PRODUCT PHYSICAL PASS / MINOR STUTTER OPEN.**
  No ALSA XRUN; much smoother than software rendering, with occasional minor stutter.
- **Hardware volume keys — PHYSICAL + REBOOT PERSISTENCE PASS / OVERLAY OPEN.**
  Stable evdev input adjusts equal RK817 channels in steps of 16 up to 201.
  Exact 169/201 restart tests and a key-generated 169 across warm reboot passed.
- **RetroArch History — PASS.** The user-owned path persisted and reopened the
  exact smoke ROM once; scraping, metadata and arbitrary content remain open.
- **Speaker — ACCEPTED HP-FED ROUTE PASS / GAIN, MUTE AND POPS OPEN.**
  Bounded tone/normal content were audible at accepted gain. Post-poweroff hiss
  stopped when unplugged; faint streaming pops have unknown cause. Avoid louder tests.
- **Headphones — STEREO + MECHANICAL SPEAKER CUT-OFF PASS.** Left/silence/right
  passed and insertion silenced the speaker. Automatic reporting/DAPM remains open.
- **Jack detection — FAIL / FACTORY V0.1 INFRA FAIL / V0.2 NO-TRANSITION.**
  Mainline and exact factory v0.2 saw no evdev/raw GPIO2_C6 transition. Do not repeat
  unchanged; electrical/socket localization remains open and damage is unproven.
- **Wi-Fi / streaming — V0.17 PICTURE/AUDIO + 60 FPS SAMPLE PASS / SSH UNPAIRED.**
  Patched Sunshine removed alternating frame gaps; L1 + R1 exits, with transient black before ES-DE recovery.
  [Streaming](../../../docs/GAME-STREAMING.md): low-delay A/V pass; Qt ~60 FPS Hantro sample; product/gamepad open.
- **Local Wi-Fi control — TEMPORARY POLICY DEVICE + V0.18 HOST + P2 MEDIA + COLD BASE PASS / PERSISTENCE OPEN.**
  The ark-only three-action rule passed scan, profile create/delete and saved
  reconnect; unrelated permissions stayed denied. Exact packages/rule pass
  reproducible host validation, fixed-profile p2 write/full readback, cold
  identity, exact target hashes and intended/denied permission checks. New-profile
  activation and reboot persistence remain open.
- **Bluetooth — HARDWARE BLOCKED.** Boot reports `BT=0`; rfkill/sysfs/USB expose
  no controller and BlueZ is absent. Require controller/firmware before pairing.
- **Zram — ONE-SHOT KERNEL + APPLY/DISABLE DEVICE PASS / PROMOTION OPEN.** The
  v0.18 candidate used 43.5 MiB of 256 MiB LZ4 swap under bounded pressure, then
  reset/unloaded cleanly. Normal v0.15/media were restored; benefit remains open.
- **Hantro media — QT V3 SHORT HUD/A/V/RETURN PASS / LONG SESSION OPEN.**
  Default-preset native HUD, picture/audio, shoulders, host-loss return and reconnect
  were accepted; 59.25 rendered FPS reported. Application-list retrieval failed to
  return names. [Streaming](../../gaming-shell/STREAMING.md) owns exact scope.
- **External USB — SINGLE HOST BOUNDED-READ PASS / CURRENT HID GADGET PATH FAIL.**
  A known disk's bounded hashes matched. R41 found DWC2 Host, `dr_mode=host` and no
  UDC/gadget/role entry; wiring evidence plus a recoverable kernel/DT candidate are required.
- **Rumble — DIRECT MOTOR PASS / APP ROUTING OPEN.** Two bounded `FF_RUMBLE`
  pulses were felt. Emulator routing, magnitude and suspend interaction are open.
- **Charger ONLINE + net charging — SHORT ATTENDED PASS / LIMITS OPEN.** GPIO
  ONLINE and meter/current direction proved short-run net charging. Do not
  repeat unchanged; limits remain open. V0.12 RK817 150 mA is host-only/unbooted.
- **A2 media — READ-ONLY PASS / CQE OPEN.** Tested p2 works; comparative performance remains open.
- **Second card slot — UNAVAILABLE.** V0.17 disables it; dual-card needs isolation.
- **Suspend/resume — OPEN / HIGH RISK.** Require bounded wake/recovery before retesting.
- **Old macOS exFAT staging receipt — REVOKED.** Use the Linux image path and exFAT postmortem.

## Evidence owners

- Boot/media: [release](../../first-version-release/README.md),
  [power settle](../../bringup-tests/V17-MMC-POWER-SETTLE.md),
  [promotion](../../gaming-product-boot-promotion/README.md), [p3](../../../docs/P3-CONTENT-MIGRATION.md).
- Product: [rootfs](../../rootfs-debian13-gaming-v17/README.md), [MVP](../../bringup-tests/GAMING-MVP.md),
  [input/audio](../../bringup-tests/ATTENDED-INPUT-AUDIO-COMPLETION.md).
- Hardware: [audio](../../bringup-tests/AUDIO-ROUTE-PROBE.md),
  [charging](../../bringup-tests/V12-CHARGE-TERM-POLICY.md),
  [Hantro](../../bringup-tests/HANTRO-CODEC-DECODE-PROBE.md), [USB](../../bringup-tests/USB-STORAGE-READ-PROBE.md).
