# R46H experiment status ledger

> Current checkpoint: 2026-09-19. This is the authoritative index of accepted
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

Fallbacks are p2 v0.7 attended and v0.15 automated; current v0.17 passed readbacks,
cold/warm infra and stick smoke. LCD, USB, Moonlight and PSP remain open.
The v0.18 local-network-policy successor is host-only; media and physical gates are open.

## Capability ledger

- **Full-card first-version release v0.1 — HOST + MEDIA + PHYSICAL PASS.** Its
  v0.17/v0.15 and p2 v0.5 cold-booted; current p2/p3 later changed.
- **Original-card EASYROMS — P3 WRITE/PHYSICAL PASS; READBACK UNVERIFIED.**
  Write/sync/eject, read-only mounts, frontend and one game passed; checksums were skipped.
- **Cold MMC — V0.17 ONE-SHOT + TWO PERSISTENT PASS / RELIABILITY OPEN.**
  Three SDR104/150 MHz samples had no MMC/ext4 fault; v0.16 reproduced the fault
  and was rolled back. Do not loop unchanged boots.
- **Debian 13 gaming p2 v0.7 — HOST + P2 MEDIA + PHYSICAL PASS.** Exact payload
  v0.6, two readbacks, cold boot, product sample, health and poweroff passed.
- **Debian 13 gaming p2 v0.15 — HOST + P2 MEDIA + DEVICE AUTOMATION PASS /
  ATTENDED OPEN / DREAMCAST FAIL.** Build/readback, boot, `/roms`, automated game
  samples, reboot, health and poweroff passed; operator evidence stayed open.
- **Debian 13 gaming p2 v0.16 — HOST + P2 MEDIA + DEVICE INFRA PASS / PRODUCT
  FAIL.** Infra passed, but ES-DE merged bundled Dreamcast and loaded 14 systems
  instead of the intended 13.
- **Debian 13 gaming p2 v0.17 exclusive systems — HOST + P2 MEDIA + DEVICE
  INFRA + STICK SMOKE PASS / SAVE MENU FAIL / PSP DEFERRED.** Build/readback,
  cold/warm identity, 13 systems, input/captures, health and poweroff passed.
  Ozone save entries are absent because custom cores sit outside discovery;
  both sticks passed direction/centering without a mapping change.
- **Persistent v0.15 BOOT — PASS.** Versioned promotion kept v0.10/v0.8
  fallbacks and U-Boot environment unchanged. Roll back only for a regression;
  never use `saveenv`.
- **Panel handoff — FIRST BOOT PASS / FULL INIT + KMS OPEN.** V0.8 preserved the
  bootloader display; full DCS reset/init and general KMS page flips remain open.
- **Panfrost — BASE PROBE PASS / FLYCAST GAMEPLAY FAIL.** Exact 64x64 FBO/readback
  gates pass. Flycast `Capcom vs SNK 2` continuously faults in gameplay with
  per-strip or per-triangle sorting; llvmpipe instead XRUNs at about 300% CPU.
- **Combined gaming input — COMPOSITE PHYSICAL + V0.17 STICK SMOKE PASS.** V0.14
  closed 16 keys and four axes; v0.17's unchanged product path passed attended
  dual-stick direction/centering checks. Spent diagnostic batches remain removed.
- **Inherited F5/GPIO2_A4 — PARTIAL / DT-HARDWARE MISMATCH.** The advertised
  line stayed idle-high and no key was identified. Require schematic or
  continuity evidence before documenting a key or deleting the node.
- **Debian-native gaming MVP — PASS.** RetroArch/RGUI, Nestopia and the custom
  smoke core passed. Imported `1944.zip` passed controls, audio and RGUI return;
  `1943.zip` jammed in Nestopia. Broad ROM/core compatibility is open.
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
- **Jume Launcher (Qt shell) — R17 CONTROLS + R35 STATUS VALUES DEVICE PASS / R56 GEOMETRY COMPOSED PASS.**
  Remote taps/captures, CPU restore, keyboard, HUD, dim/wake, battery/charge/Wi-Fi passed;
  R56 aligned the status row in a device-composed capture; physical LCD remains open.
  Reboot/poweroff passed. [Device settings](../../gaming-shell/DEVICE.md) owns scope.
- **Wayland/ports — R60 VICE CITY INTRO PHYSICAL PASS / R63 MACHINE CANDIDATE / BROADER PLAY OPEN.**
  R48 fixed D-pad Down; 640x480, first-config and [private Mesa](../../gaming-mesa/README.md)
  passed. R60 reached GTA III/VC cutscenes and clean exits/relaunches without faults;
  the operator accepted Vice City LCD motion, audio and controls at 816/300 MHz.
  Stock clocks gave little benefit; frame-limiter-off and exact buffer sizing regressed.
  R62 attributed 15--20% wall time to about 700--800 tiny uploads/s. R63's upload
  ring raised the same-clock median from 18.67 to 20.52 client commits/s and passed
  capture, bounded exit, cleanup and poweroff. One 1.116-second maximum interval and
  attended LCD/audio/control reacceptance remain; R60 stays the fallback. GTA III
  physical play, broader saves/gameplay and Stardew save-load remain open.
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
- **Local Wi-Fi control — TEMPORARY POLICY DEVICE + V0.18 HOST PASS / MEDIA + NEW PASSWORD OPEN.**
  The ark-only three-action rule passed scan, profile create/delete and saved
  reconnect; unrelated permissions stayed denied. Exact packages/rule now pass
  byte-reproducible host composition and independent validation. Fixed-profile
  deployment, new-password activation and reboot persistence remain open.
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
- **A2 media — READ-ONLY COMPATIBILITY PASS / COMMAND QUEUE OPEN.** Accepted p2
  works on the tested card; CQE and comparative performance remain open.
- **Second card slot — UNAVAILABLE.** V0.17 disables it; dual-card needs isolation.
- **Suspend/resume — OPEN / HIGH RISK.** Historical deep-suspend attempts did
  not establish reliable resume. Design bounded wake/recovery before retesting.
- **Old macOS exFAT staging receipt — REVOKED.** Use the Linux image path and exFAT postmortem.

## Evidence owners

- Boot/media: [release](../../first-version-release/README.md),
  [power settle](../../bringup-tests/V17-MMC-POWER-SETTLE.md),
  [promotion](../../gaming-product-boot-promotion/README.md), [p3](../../../docs/P3-CONTENT-MIGRATION.md).
- Product: [rootfs](../../rootfs-debian13-gaming-v17/README.md),
  [MVP](../../bringup-tests/GAMING-MVP.md), [input/audio](../../bringup-tests/ATTENDED-INPUT-AUDIO-COMPLETION.md).
- Hardware: [audio](../../bringup-tests/AUDIO-ROUTE-PROBE.md),
  [charging](../../bringup-tests/V12-CHARGE-TERM-POLICY.md),
  [Hantro](../../bringup-tests/HANTRO-CODEC-DECODE-PROBE.md), [USB](../../bringup-tests/USB-STORAGE-READ-PROBE.md).
