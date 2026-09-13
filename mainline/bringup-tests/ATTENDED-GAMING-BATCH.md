# R46H consolidated attended gaming batch

Status: **PHYSICAL COMPLETE / INPUT FAIL / HEADPHONE DEFERRED / HISTORY PASS**

This is the retained execution record for the 2026-08-18 R46H operator session.
Detailed acceptance contracts remain in the linked subsystem runbooks; this
document owns their order, shared staging, stop conditions and final cleanup.

The batch contained five separately delimited gates:

1. passive cold-MMC serial capture during already required boots;
2. exact v0.14 combined button/ADC input bridge;
3. RK817 headphone insert/remove detection;
4. conditional headphone output plus automatic speaker muting;
5. persistent RetroArch history placement on exact v0.10.

Charging is intentionally excluded. Application-level rumble is also excluded:
RetroArch 1.20's udev joypad backend sends force feedback to the selected pad's
own evdev descriptor, while the current combined virtual gamepad advertises no
`EV_FF`; see the upstream
[`udev_joypad.c`](https://raw.githubusercontent.com/libretro/RetroArch/v1.20.0/input/drivers_joypad/udev_joypad.c).
The already accepted direct `pwm-vibrator` pulse must not be repeated as a
substitute for missing application routing.

No TF-card base-image rewrite is needed. All mutations use authenticated Wi-Fi
transfer and guarded p2 transactions. Do not press Reset, write p1, mount BOOT
writable or use `saveenv`.

## Frozen host inputs

Use only these retained files:

| Purpose | File | SHA-256 |
| --- | --- | --- |
| v0.14 p2 one-shot | `mainline/out/r46h-v14-gaming-input-one-shot/builds/build-ba00cebb7b19-b2193f28e1ae/r46h-v14-gaming-input-one-shot-v1.tar.gz` | `b2193f28e1ae8cb625d34e9c191bda9eea48d079e28595d39eaddd5c9dbd3a68` |
| combined input bridge | `mainline/out/r46h-gaming-input-bridge/builds/build-83456088025d-e0c1cc1c9c28/r46h-gaming-input-bridge-v0.1.tar.gz` | `e0c1cc1c9c28149d6892b8ab9c85fa421ba7b2566404b0882c34e055c6f831c2` |
| jack-detect binary | `mainline/out/.cache/r46h-audio-jack-probe/r46h-audio-jack-probe` | `41dbe0e95ef6e6e2fe614c5acdcd18507714cc4cf94616b8745527bf39657d3e` |
| headphone route v0.3 | `mainline/bringup-tests/r46h-audio-route-probe` | `2bfa8d284d14d231a76d3660d7bd96a896a91147e8f53fc2e5e5dc3436bc508b` |
| history fix v0.2 | `mainline/out/r46h-gaming-history-fix/builds/build-878a33e-ea4d53659c25/r46h-gaming-history-v0.2.tar.gz` | `ea4d53659c25389efbc1c692da43aaf99699f5c5f42aee6b150799d0c4c7ea62` |

The first Phase A attempt on 2026-08-18 rejected the superseded one-shot
generation `build-0a8e49080ab7-3b548dc178ab`: all 1,290 module hashes passed,
but the extracted tree had 395 directories while its installer required 396.
The installer stopped before publishing a module or candidate-state path. The
exact transfer and tmpfs staging were removed, v0.10 health and configuration
hash passed, and serial confirmed a controlled poweroff. Do not use archive
SHA-256 `3b548dc178abd1fd30384b0a6dd28f90e62a217646d361e37f8c923d8ad16087`.
The replacement above binds the canonical tree, archive members, generated
installer and payload metadata to the same 395-directory count.

The first Phase E history attempt rejected superseded generation
`build-892f649-1724089c04e6`. Its root-only staging made the unprivileged shell
unable to expand the documented `*`; after using explicit member paths, the
installer rejected its incorrect assumption that the RetroArch state root was
already owned by `ark`. The accepted v0.10 target has exact identity
`root:root 0755` there. Both stops preceded config, receipt, helper or state
publication; the original config SHA-256 remained exact. Do not use archive
SHA-256 `1724089c04e60fff9fac31c12df8889adbcc0b6575a95374637d31882f6a671a`.

The corrected history archive was generated twice from clean commit
`878a33e9e5b37a8e8f20ef0317b2b6a363612698` with deterministic tar plus
`gzip -n`; both copies had the same digest. Its extracted file identities are:

```text
066f2dd962cd6f34943e619c9dfa69a628c0e6680f61307d334aaab9ec64c49d  install.sh
fb88d6f8d093527fb6b56730e6082cb088de97d8024ec1dac5f5b724acbc5819  rollback.sh
697aa82bb42689cd841f16a8ce1ae9c6ac2bdc56ccd1b811136f8f5884e600e9  retroarch.cfg
```

## Completed result: 2026-08-18

- The three required cold boots did not reproduce the old 400/300 kHz `-84`
  signature. Two cleanly fell back to 50 MHz after skipping the voltage switch;
  the ordinary v0.10 return reached SDR104. This passive non-reproduction does
  not close the intermittent MMC issue.
- Exact v0.14 booted once. Its only input trial reported `SYN_DROPPED=0`, 14/16
  keys, 4/4 axes and 4/4 centered axes. L3/R3 emitted no events; the operator
  saw D-pad and A screen response but no left-stick response. The input gate
  therefore failed. The bridge and v0.14 one-shot state were later removed by
  their guarded helpers on exact v0.10.
- Both headphone gates were skipped because the available 3.5 mm headset was
  known broken. No headphone result was inferred.
- Corrected history v0.2 installed on exact v0.10. The user playlist contained
  the exact smoke-ROM path once, and the operator reopened it from RGUI History.
  The config, seven-line receipt and rollback helper remain installed.
- Final checks found exact v0.10, no candidate process/service/module tree, no
  RetroArch process, zero ext4 errors, no failed units and no new relevant
  kernel error. Transfer and `/run` staging were removed. Serial captured a
  controlled poweroff; USB-DC was disconnected.

Do not repeat the unchanged v0.14 candidate. A later attended session may run
the deferred headphone gates and a changed input candidate only after a new
host-reviewed hypothesis exists.

Before the device session, revalidate the two large retained generations and
all five transfer inputs. Do not rebuild or select a newer output:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-r46h-gaming-input-bridge.py validate
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-v14-gaming-input-one-shot.py validate
/usr/bin/shasum -a 256 \
  mainline/out/r46h-v14-gaming-input-one-shot/builds/build-ba00cebb7b19-b2193f28e1ae/r46h-v14-gaming-input-one-shot-v1.tar.gz \
  mainline/out/r46h-gaming-input-bridge/builds/build-83456088025d-e0c1cc1c9c28/r46h-gaming-input-bridge-v0.1.tar.gz \
  mainline/out/.cache/r46h-audio-jack-probe/r46h-audio-jack-probe \
  mainline/bringup-tests/r46h-audio-route-probe \
  mainline/out/r46h-gaming-history-fix/builds/build-878a33e-ea4d53659c25/r46h-gaming-history-v0.2.tar.gz
```

Have a known working 3.5 mm headset available. If none is available, mark both
headphone gates skipped before power-on; do not improvise a stimulus.

## Common stop conditions

Stop the current gate on a wrong kernel/root identity, lost serial visibility,
new ext4 error, failed unit, new relevant kernel fault, surviving candidate
process, stuck input, abnormal temperature or unexpected power behavior. Do not
reset or immediately repeat. Use controlled poweroff when the system remains
responsive, return through ordinary exact v0.10, then run only the guarded
cleanup that is still applicable.

One gate's failure does not turn another gate into a PASS. Continue to a later
gate only if exact v0.10 health and serial control have been re-established.

## Phase A: cold v0.10 and inactive staging

1. Keep USB-DC disconnected. Rediscover the CH340 device. Open capture at
   1,500,000 baud before applying power and change to 115,200 only after the
   visible `I/TC: OP-TEE version` marker.
2. Let persistent BOOT start exact
   `6.12.99-r46h-mainline-v0.10-adc-full-range`. Verify p2 PARTUUID
   `c9f931c9-02`, writable ext4, `errors_count=0`, no failed units and stable
   Wi-Fi. Preserve the raw cold-boot log; do not classify MMC from a filtered
   terminal view.
3. As unprivileged `ark`, create mode `0700`
   `/home/ark/.cache/r46h-attended-gaming-v1` and transfer the five frozen host
   inputs there using the already accepted strict-host-key SSH workflow. Name
   them exactly as in the digest block below.
4. On serial, verify all five before any extraction:

```bash
cd /home/ark/.cache/r46h-attended-gaming-v1
printf '%s  %s\n' \
  'b2193f28e1ae8cb625d34e9c191bda9eea48d079e28595d39eaddd5c9dbd3a68' r46h-v14-gaming-input-one-shot-v1.tar.gz \
  'e0c1cc1c9c28149d6892b8ab9c85fa421ba7b2566404b0882c34e055c6f831c2' r46h-gaming-input-bridge-v0.1.tar.gz \
  '41dbe0e95ef6e6e2fe614c5acdcd18507714cc4cf94616b8745527bf39657d3e' r46h-audio-jack-probe \
  '2bfa8d284d14d231a76d3660d7bd96a896a91147e8f53fc2e5e5dc3436bc508b' r46h-audio-route-probe-v0.3 \
  'ea4d53659c25389efbc1c692da43aaf99699f5c5f42aee6b150799d0c4c7ea62' r46h-gaming-history-v0.2.tar.gz |
  sha256sum -c -
```

5. Extract the one-shot archive and bridge archive as root into `/run`. Run the
   one-shot installer first, then the bridge installer. Both must report their
   inactive PASS markers. Follow
   [`GAMING-INPUT-BRIDGE.md`](GAMING-INPUT-BRIDGE.md) and the bundled
   `OPERATIONS.md`; do not alter their extracted content or install order.
6. Remove only the two verified `/run` extraction directories, run `sync`, and
   power off cleanly. Keep the five rehashed transfer files on p2 until final
   cleanup.

## Phase B: one exact v0.14 input trial

1. Reopen cold serial at 1,500,000 before power, switch at the OP-TEE marker,
   interrupt autoboot once, and enter the exact commands from
   `/var/lib/r46h-gaming-input-one-shot/v0.14-gaming-input-bridge/UBOOT-CMDS.txt`.
   Never use `saveenv`. This required boot is also the passive cold-MMC sample;
   do not loop it if the old `-84` signature does or does not appear.
2. After exact `6.12.99-r46h-mainline-v0.14-gaming-input-bridge` reaches
   multi-user, run `/usr/local/sbin/r46h-input-bridge-trial` from the attended
   TTY with every game button released and both sticks centered.
3. During its only 60-second window, confirm D-pad, A and left-stick response on
   the smoke screen. Exercise A/B/X/Y, L1/R1, L2/R2, Select, Start, L3/R3, all
   four D-pad directions and every edge/corner of both sticks; circle both
   sticks and release centered. Do not press Power, Reset, volume keys or F5.
4. Require the exact machine PASS and the screen observations defined in
   [`GAMING-INPUT-BRIDGE.md`](GAMING-INPUT-BRIDGE.md). Then check health, `sync`
   and power off. Do not run a second trial to improve coverage.

## Phase C: exact v0.10 return and candidate cleanup

1. Power on normally and let unchanged persistent BOOT return to exact v0.10.
   Verify root, ext4 and failed-unit health before deletion.
2. Remove the bridge first:

```bash
sudo /usr/local/sbin/r46h-input-bridge-remove
```

3. Remove the v0.14 one-shot/module state second:

```bash
sudo /var/lib/r46h-gaming-input-one-shot/v0.14-gaming-input-bridge/REMOVE.sh
```

4. Require both PASS markers, absence of the candidate service/process/module
   tree and the original config SHA-256
   `621fdf049cd05e6aa02c62b5c42ed37a768ce9342af14c4563cfd4466d80d078`.
   Only then continue.

## Phase D: headphone gates on v0.10

Result: **DEFERRED**. The known available headset was broken, so both gates were
skipped without installing or running the audio tools.

Stop the gaming frontend and require no RetroArch process. Install the rehashed
jack binary and v0.3 route script from the p2 transfer directory into their
fixed root-owned tmpfs paths:

```bash
sudo install -o root -g root -m 0700 \
  /home/ark/.cache/r46h-attended-gaming-v1/r46h-audio-jack-probe \
  /run/r46h-audio-jack-probe
sudo install -o root -g root -m 0700 \
  /home/ark/.cache/r46h-attended-gaming-v1/r46h-audio-route-probe-v0.3 \
  /run/r46h-audio-route-probe
```

With the headset removed, run the 30-second insert/remove detector exactly as
documented in [`AUDIO-JACK-PROBE.md`](AUDIO-JACK-PROBE.md). Insert fully once,
then remove once. If it does not PASS, skip the route probe.

Only after detector PASS, insert the headset again and leave it inserted while
running:

```bash
sudo /run/r46h-audio-route-probe --headphones-inserted
```

Machine PASS requires `Speaker: Off`, `Headphones: On`, bounded playback,
restored mixer and clean health. Physical PASS additionally requires the
operator to hear the tone in the headset and hear nothing from the built-in
speaker. Remove the headset after the probe. Never increase gain or rerun the
completed speaker-only mode.

## Phase E: history fix and UI persistence

This phase must be after both candidate removers because they pin the old
configuration hash. Extract the rehashed history archive, normalize its exact
root-owned tmpfs metadata, and run the installer with its reviewed self hash:

```bash
cd /run
sudo test ! -e /run/r46h-gaming-history-v0.2
sudo tar -xzf \
  /home/ark/.cache/r46h-attended-gaming-v1/r46h-gaming-history-v0.2.tar.gz
sudo chown -R root:root /run/r46h-gaming-history-v0.2
sudo chmod 0700 /run/r46h-gaming-history-v0.2
sudo chmod 0600 \
  /run/r46h-gaming-history-v0.2/install.sh \
  /run/r46h-gaming-history-v0.2/rollback.sh \
  /run/r46h-gaming-history-v0.2/retroarch.cfg
sudo /bin/bash /run/r46h-gaming-history-v0.2/install.sh \
  --installer-sha256 066f2dd962cd6f34943e619c9dfa69a628c0e6680f61307d334aaab9ec64c49d
```

Start the frontend, launch `/roms/nes/r46h-nes-smoke.nes` once with Nestopia,
then stop the service from serial. Run the machine checks in
[`../gaming-history-fix/README.md`](../gaming-history-fix/README.md). Start the
frontend once more and have the operator open the same ROM from RGUI History;
stop it cleanly afterward. If either machine or UI acceptance fails, run the
installed rollback helper before continuing.

## Final cleanup and final state

Remove only the two `/run` audio tools, the history extraction directory and
the five exact user-owned transfer files. Remove the transfer directory only if
empty. Do not delete unrelated cache or historical `.tmp-r46h-*` trees.

```bash
sudo rm -f /run/r46h-audio-jack-probe /run/r46h-audio-route-probe
sudo rm -f \
  /run/r46h-gaming-history-v0.2/install.sh \
  /run/r46h-gaming-history-v0.2/rollback.sh \
  /run/r46h-gaming-history-v0.2/retroarch.cfg
sudo rmdir /run/r46h-gaming-history-v0.2
rm -f \
  /home/ark/.cache/r46h-attended-gaming-v1/r46h-v14-gaming-input-one-shot-v1.tar.gz \
  /home/ark/.cache/r46h-attended-gaming-v1/r46h-gaming-input-bridge-v0.1.tar.gz \
  /home/ark/.cache/r46h-attended-gaming-v1/r46h-audio-jack-probe \
  /home/ark/.cache/r46h-attended-gaming-v1/r46h-audio-route-probe-v0.3 \
  /home/ark/.cache/r46h-attended-gaming-v1/r46h-gaming-history-v0.2.tar.gz
rmdir /home/ark/.cache/r46h-attended-gaming-v1
```

Require exact v0.10, no candidate service/process/module tree, no RetroArch
process, `errors_count=0`, no failed unit and no new relevant dmesg fault. Run
`sync`, perform controlled poweroff, and retain the serial `Powering off`
marker. The final accepted state is powered off, USB-DC disconnected, exact
v0.10 persistent BOOT, no v0.14 staging and the history fix present only if its
own physical gate passed.
