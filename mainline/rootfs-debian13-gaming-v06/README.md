# R46H Debian 13 gaming p2 v0.6

Status: **HOST ARTIFACT + P2 MEDIA READBACK + PRODUCT PHYSICAL PASS /
DIAGNOSTIC PAYLOAD TARGET PASS / SUCCESSOR ARTIFACT OPEN**

This is the successor p2 composer. The historical v0.5 full-rootfs composer is
frozen; v0.6 starts from its exact accepted ext4 image and applies one bounded,
offline overlay.

The builder itself remains **host-only**: building or validating never touches
a block device, p1, p3, BOOT, U-Boot environment, network or target
credentials. The separate fixed-device p2 write/readback and current-card
physical evidence below passed only their stated boundaries.

## Frozen inputs and delta

The builder requires these exact inputs:

- p2 v0.5 image SHA-256
  `ee7d402c06a750081b4c588c5162cca44d0e07fa4b544d5a59bef7629722aeca`;
- published gaming payload v0.5 archive SHA-256
  `22bbbe33f6d96b170aebb886c1aa40e2596073e2609b2bdfa93eeb1b42377e17`;
- arm64 Debian builder image ID
  `sha256:bd09bf6db6f1fb8f882621e98d70f01f976fd8dfba1bc897766afebd64cf51b9`;
- fixed p2 geometry from `hl-r46h-v22-g92-v1`.

The overlay installs every versioned v0.5 gaming file, enables the hardware
volume service, replaces the v0.4 gaming receipt with v0.5, and updates only
the rootfs identity helpers to v0.6. It also installs
`/etc/udev/rules.d/90-alsa-restore.rules`. That same-basename `/etc` rule keeps
the package-owned `/usr/lib` file intact while applying upstream alsa-utils
commit `f90124c73edd050b24961197a4abcf17e53b41a8`, which restores the missing
`alsa_restore_std` label.

The filesystem keeps the exact partition length and zero tail, with UUID
`d3130006-46a4-4d56-9001-000000000006` and label `R46H_GAMING_V06`.

## Build and validate

Docker Desktop must be running. Inputs and committed source are read-only;
private clones, payload extraction and validation work stay under
`mainline/out/.cache/` and are removed when the command exits.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v06.py validate-inputs
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v06.py build
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v06.py validate
```

`build` requires the listed source scope to be committed and clean. Before
atomic publication it composes two independent private clones and requires
identical final SHA-256 values, then reopens the first image read-only for a
third verification pass. Retained evidence covers ext4 cleanliness and
geometry, exact payload bytes and modes, systemd unit syntax, volume enablement,
receipt boundaries and udev rule precedence.

`validate` rechecks every retained artifact checksum and repeats the read-only
container verification from the exact committed source snapshot. Neither
command authorizes media work.

## Accepted host artifact

Clean source commit `5b81d58039c0df65b339850665f7ff6c2746a5c8`
produced two byte-identical compositions and passed the independent read-only
validation. The published 10,716,877,312-byte image is
`mainline/out/r46h-debian13-p2-gaming-v0.6/r46h-debian13-p2-gaming-v0.6.ext4`
with SHA-256
`4ac3a525264fcab7efda804c147f8e77604cbee82847d504de7e359258ca4bee`.
`BUILD-INFO` has SHA-256
`a7219d27d78be4b6b6f34b5dae72cf6e5d259c5aacf5a35a878b6cce0572c463`.

This proves deterministic host composition and retained artifact integrity. No
block device was opened by the build, and no R46H evidence transfers from v0.5.

## Accepted media deployment

On 2026-08-30 the card was rediscovered as the exact 62,534,975,488-byte fixed
profile. The mode-0600 p2-only plan had SHA-256
`b8ec9371a0e3cb5bb66cd5dca80ca635372cf38855aed4ecc6a650ecdf3049f9`.
The full pre-write p2 rollback clone `p2-prewrite-v06-20260830.ext4` is
10,716,877,312 bytes with SHA-256
`36c12c618995e426cbe54aebf9e246e1f5b41a00a15dc6fe4e022c31c4d6c42e`.
It remains in audit session
`session-20260830T051623Z-35309-7bab6288-00a1-42c8-ae1c-eb3c50da1b18`.

The Card Agent wrote exactly 10,716,877,312 bytes to p2, flushed the device and
read the complete partition back as the source SHA-256
`4ac3a525264fcab7efda804c147f8e77604cbee82847d504de7e359258ca4bee`.
A separate raw reopen and second complete p2 hash matched. Final state is
`WRITE_COMPLETE` with `safe_to_boot=yes`. The complete p1 hash matched before
and after as
`74dde6dd6c14324af0eb2d570b89096d6fb0414abc3293f648e40265b44a1db9`;
the prefix stayed
`3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3`.
p3 stayed unmounted and outside the plan.

The deploy receipt SHA-256 is
`5e82eb50b6d0807a7cb65fc7d9abda94fbd6f32d96aeb55ebce58265bf30cea3`;
the immutable write-status SHA-256 is
`65cc679e74e8cb24646d8758a326b7c34fad154b562aeaafba7fdae00c756574`.
The retained deploy session is
`session-20260830T052517Z-35757-fb842c97-1725-45b6-b65e-02f967b357a2`.
After a final independent audit, macOS safely ejected the card. The session's
`/dev/disk4` name is evidence only and must never be reused as identity.

## Accepted physical regression

On 2026-08-30 a mode-0600 CH340 capture started at 1,500,000 baud before cold
power-on and switched to 115,200 at the exact OP-TEE marker. Ordinary autoboot
loaded `Image.mainline-v0.15-gaming-product.gz` and
`rk3326-r46h-mainline-v0.17-power-settle.dtb`; no interrupt or U-Boot state
change was used. Linux reported the exact v0.15 kernel, p2 UUID
`d3130006-46a4-4d56-9001-000000000006` and
`release=debian13-p2-gaming-v0.6`.

The cold sample reached SDR104/150 MHz without MMC, block or ext4 faults. p3
mounted read-only at `/roms` before automatic RGUI. Firstboot, input, volume,
frontend and SSH services were active with successful results and zero
restarts; failed units were empty. The storage audit passed with zero ext4
errors and correctly retained `a2_command_queue=not-available`.

The combined gamepad produced all four D-pad directions, representative game
buttons and these observed analog ranges: X 122--999, Y 46--911, RX 62--890 and
RY 79--914. Hardware volume events changed equal RK817 channels and the final
mixer was deliberately restored to `201,201`. The operator played imported
`/roms/nes/1944.zip` for one minute without anomaly, accepted speaker and
headphone playback plus speaker cut-off on insertion, and returned to RGUI with
Select+X. No ALSA XRUN/underrun, service crash or leftover input monitor was
present.

Final health checks passed, then `sync` and controlled poweroff unmounted
`/roms`, remounted p2 read-only, unmounted every filesystem and reached
`systemd-shutdown[1]: Powering off.` This regression rewrote neither p1 nor p3.
The capture is
`mainline/out/r46h-serial-logs/gaming-product-v06-firstboot-20260830T055033Z.bin`,
95,853 bytes, SHA-256
`a8957222ae7c1359b455c0ea3faf1330477b1219ca55123beb5bc905c77214a6`.

## Accepted diagnostic payload update

The same batch found one isolated failure: direct
`sudo /usr/local/sbin/r46h-game-ui smoke` invocation showed a black screen.
RetroArch initialized video/audio but recorded zero content run time; the
operator interrupted it and the helper closed with
`R46H_GAME_UI result=fail status=130 mixer_restored=yes process_cleanup=pass`.
Automatic frontend recovery restored RGUI, and the normal imported-game path
then passed. This is a **diagnostic helper failure**, not a failure of the
product path.

Source inspection found that the earlier successful custom-core path used the
software renderer before the accepted product runner changed every mode to
GLES2. The successor gaming payload now keeps GLES2 for normal menu/NES use and
uses software only for direct `smoke`. Its clean host build, independent
validation and exact provenance are owned by
[Gaming Product](../bringup-tests/GAMING-PRODUCT.md). Its guarded Wi-Fi update
then passed exact preflight, install, rollback and idempotence checks. Direct
software smoke passed operator display/audio/control observation, and normal
RGUI returned on GLES2. The deliberate test interrupt produced status 130 with
mixer/process cleanup passing. p1 was unchanged, p3 stayed read-only and health
checks were clean.

This live update does not change the published p2 image. The next host gate is
a deterministic successor p2/release artifact embedding the accepted payload;
representative-system coverage, intermittent-stutter profiling and the skipped
p3 checksum/readback remain separate follow-up work.
