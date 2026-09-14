# R46H experiment status ledger

> Current checkpoint: 2026-09-14. This is the authoritative index of accepted
> physical evidence and open hardware gates. Exact commands, hashes and raw
> receipts stay in the linked owning runbooks.

## How to read this ledger

- **PASS**: evidence exists for the stated boundary; repeat only after a relevant change or reviewed regression.
- **FAIL**: the tested path failed; do not repeat without a new hypothesis or implementation.
- **REVOKED**: old evidence cannot authorize later work.
- **OPEN**: the stated acceptance contract has not passed.

Host artifact, media write/readback and physical R46H evidence are distinct; each row names its level.
Operator audio/display/control observations are not implied by a machine exit code.

## Current accepted first version and next gate

The last fully read-back full-card release is `build-2e0d33a53f11-e1e8d9edb2f8`
for `hl-r46h-v22-g92-62534975488-v1`: v0.17 BOOT/power settle selects the exact
v0.15 Image/modules and Debian 13 gaming p2 v0.5. Cold boot and identity passed.

The current card's EASYROMS p3 import passed write, eject and physical use; its
full target checksum/readback was skipped, so equality remains unverified; see
[P3 Content Migration](../../../docs/P3-CONTENT-MIGRATION.md).

P2 v0.7 is the last fully attended fallback; p2 v0.15 is the last accepted
automated device fallback. The current card's exact p2 v0.17 passed its p2-only
write, two full readbacks, cold/warm infrastructure and attended dual-stick smoke.
R47-R54 passed Stardew import/bound, R48 GTA intro starts/D-pad Down and the R54
GTA III menu at the 30 FPS limit with HUD hidden. R54 intro/crash, USB, Moonlight and PSP remain open.

## Capability ledger

- **Full-card first-version release v0.1 — HOST + MEDIA + PHYSICAL PASS.** Its
  v0.17/v0.15 and p2 v0.5 cold-booted cleanly. Current p2/p3 later changed;
  blank-card provisioning and statistical reliability remain open.
- **Original-card EASYROMS — P3 WRITE/PHYSICAL PASS; READBACK UNVERIFIED.**
  Exact-size exFAT read-only fsck, p3 write/sync/eject, cold/warm read-only mount,
  frontend and one game passed. Checksums were skipped; retain a recovery path.
- **Cold MMC — V0.17 ONE-SHOT + TWO PERSISTENT PASS / RELIABILITY OPEN.**
  Three SDR104/150 MHz cold samples retained exact v0.15 bytes without MMC/ext4
  faults. v0.16 persistent isolation reproduced the fault and was rolled back.
  Do not loop unchanged boots or claim statistical reliability.
- **Debian 13 gaming p2 v0.7 — HOST + P2 MEDIA + PHYSICAL PASS.** Exact payload
  v0.6 is embedded. Two readbacks, serial cold boot,
  product sample, zero-error health and controlled poweroff passed.
- **Debian 13 gaming p2 v0.15 — HOST + P2 MEDIA + DEVICE AUTOMATION PASS /
  ATTENDED OPEN / DREAMCAST FAIL.** Builds/readbacks, cold boot, SDR104/150 MHz,
  read-only `/roms`, ES-DE, Game Gear/PSP/CPS capture/PCM, warm reboot, health
  and poweroff passed. LCD, audible output, controls and saves were not observed.
- **Debian 13 gaming p2 v0.16 — HOST + P2 MEDIA + DEVICE INFRA PASS / PRODUCT
  FAIL.** Two builds/readbacks, cold boot, base smoke, storage, 10 ms input,
  guarded captures, health and poweroff passed. ES-DE merged bundled Dreamcast,
  loaded 14 systems and failed the intended 13-system menu contract.
- **Debian 13 gaming p2 v0.17 exclusive systems — HOST + P2 MEDIA + DEVICE
  INFRA + STICK SMOKE PASS / SAVE MENU FAIL / PSP DEFERRED.** Builds/readbacks, cold/warm
  identity, base/storage checks, actual 13-system loading, exact input roundtrip,
  ES-DE/Game Gear/PSP frames, health and poweroff passed. Two Game Gear samples
  had no operator-reported issue. Ozone save entries are absent; custom cores
  sit outside RetroArch's discovery path. Both sticks passed attended RetroArch
  direction/centering checks; no mapping changed. PSP-specific follow-up is deferred.
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
- **ES-DE successor — HOST + TARGET + GAME PHYSICAL PASS / VISUAL LCD MOTION OPEN.**
  NES/Metal Slug and the 60 FPS original-art view pass capture and health checks.
  Per-frame generic/minimal paths are 21.7/3.3 ms; one bad batch caused 12 recovered
  watchdogs, then corrected/live runs added none. No-fill stays 60 FPS; CJK/startup/LCD remain open.
- **Remote screen — V0.16/V0.17 ANCHORED GUARD DEVICE PASS.** ES-DE-only,
  ES-DE-plus-Game Gear and PPSSPP-after-`comm=Main` captures passed; pairing is
  still required after a new image write.
- **Remote input — V0.16/V0.17 10 MS DEVICE PASS.** Self-test and exact
  screenshot-verified right/left single-step roundtrip passed; v0.15 uses 100 ms.
- **Qt shell — R17 CONTROLS + R35 STATUS BAR DEVICE PASS / FOCUS PACING OPEN.**
  Remote taps/captures, CPU restore, keyboard, HUD, dim/wake, battery/charge/Wi-Fi passed;
  reboot/poweroff passed. [Device settings](../../gaming-shell/DEVICE.md) owns scope; Wi-Fi/swap/suspend remain open.
- **Wayland/ports — R54 GTA HUD-OFF MENU DEVICE PASS / HUD-ON PACING FAIL / INTRO OPEN.**
  R48 fixed D-pad Down; R51 measured 25.6 submissions/s and reached 85 C. At
  1008/400 MHz R54 averaged 26.84/s with HUD, 30.43/s hidden and peaked at 83.846 C.
  It restored all state and powered off; LCD FPS, intro/crash, gameplay/audio/saves,
  shared VC and Moonlight remain open.
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

- Release/media/boot: [release](../../first-version-release/README.md),
  [v0.17 power settle](../../bringup-tests/V17-MMC-POWER-SETTLE.md),
  [v0.15 promotion](../../gaming-product-boot-promotion/README.md) and
  [p3 migration](../../../docs/P3-CONTENT-MIGRATION.md).
- Product/rootfs: [product](../../bringup-tests/GAMING-PRODUCT.md),
  [v0.7](../../rootfs-debian13-gaming-v07/README.md), [v0.15](../../rootfs-debian13-gaming-v15/README.md),
  [v0.16](../../rootfs-debian13-gaming-v16/README.md), [v0.17](../../rootfs-debian13-gaming-v17/README.md),
  and [MVP](../../bringup-tests/GAMING-MVP.md).
- Attended/power/media: [input/audio](../../bringup-tests/ATTENDED-INPUT-AUDIO-COMPLETION.md),
  [audio route](../../bringup-tests/AUDIO-ROUTE-PROBE.md), [charging](../../bringup-tests/V12-CHARGE-TERM-POLICY.md),
  [fast card](../../deploy/FAST-CARD-62534975488.md), [Hantro](../../bringup-tests/HANTRO-CODEC-DECODE-PROBE.md),
  [USB](../../bringup-tests/USB-STORAGE-READ-PROBE.md) and [rumble](../../bringup-tests/RUMBLE-PROBE.md).
