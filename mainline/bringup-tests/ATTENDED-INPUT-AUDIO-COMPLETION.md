# R46H attended input/audio completion batch

Status: **PHYSICAL BATCH COMPLETE / INPUT COMPOSITE PASS / FACTORY CONTROL
V0.1 INFRASTRUCTURE FAIL / CLEANLY REMOVED**

This frozen runbook was executed once on 2026-08-21. It combined exactly two
changed contracts:

1. a 20-second L3/R3-only completion capture using the exact v0.5 bridge and
   exact v0.14 one-shot;
2. one raw GPIO2_C6 control under the retained factory `4.4.189` Image and DTB
   using a minimal in-memory initramfs.

It does not rerun the spent 16-key/four-axis/RetroArch trial or the failed
v0.10 jack localizer. It does not test headphone output, speaker muting,
charging, History, speaker-only playback, rumble, USB, KMS, suspend, F5 or
broad ROM compatibility. No TF-card rewrite, BOOT write, reset, normal factory
rootfs boot or persistent U-Boot environment change is authorized.

The detailed acceptance boundaries remain
[`GAMING-INPUT-BRIDGE.md`](GAMING-INPUT-BRIDGE.md) and
[`AUDIO-JACK-VENDOR-CONTROL.md`](AUDIO-JACK-VENDOR-CONTROL.md). This file fixes
their shared order, staging and final cleanup so all remaining manual actions
can be completed in one attended window.

The batch used four cold boots:

1. ordinary exact v0.10 for read-only factory-file proof and inactive staging;
2. one exact v0.14 boot for L3/R3 only;
3. one factory-kernel/minimal-initramfs boot for GPIO2_C6 only;
4. ordinary exact v0.10 for guarded removal, health and final poweroff.

Each is also a passive cold-MMC observation. Do not add or loop a boot merely
to reproduce the intermittent initialization signature.

## 2026-08-21 physical result

Host preflight passed both retained archive validators, all focused tests and
the four frozen hashes below. Phase A then booted exact persistent v0.10,
reproduced the known 400 kHz `mmc0: error -84`, recovered through the 300 kHz
retry to SDR104 and retained `errors_count=0` with no failed unit. The exact
current-media factory Image and DTB passed one read-only p1 mount/readback, p1
was unmounted again, and all four payloads were transferred through a newly
verified task-local SSH host-key file. Exact v0.14, v0.5 and vendor-control
staging passed; only the L3/R3 runner remained in the user cache before a
controlled poweroff.

Phase B booted exact v0.14 and the operator clicked/released L3 once followed
by R3 once. Both `BTN_TRIGGER_HAPPY3` and `BTN_TRIGGER_HAPPY4` reported exact
source/emitted/virtual agreement of one press, one release, zero other events
and released final state. `SYN_DROPPED=0`, `controls=2/2`,
`result=machine-pass`, `cleanup=pass` and command status zero all passed. This
targeted result combines with the exact 2026-08-20 v0.5 result to close the
controller contract: 16 identified keys, four axes with centered returns and
the required D-pad/A/left-stick screen observations passed by composite
evidence. It is not one simultaneous 16-key trial.

Phase C loaded and checksum-validated the exact factory Image, DTB and v0.1
ramdisk, then booted exact `4.4.189` with only the minimal initramfs. PID 1
reached its ready marker but immediately returned
`reason=initial-gpio-state-unreadable` with zero samples, command status 1 and
poweroff status 1. The observation-start marker never appeared, so the
operator was correctly not asked to insert the headset. This is a terminal
v0.1 diagnostic-infrastructure failure, not a GPIO, headset, socket or factory
stack result. Do not repeat the unchanged v0.1 control.

Phase D returned to exact persistent v0.10. Both guarded input removers passed;
the exact vendor ramdisk and retained runner were independently rehashed and
removed, and all 17 candidate, runtime, extraction and transfer paths were
absent. History/config identities, user state, p1-unmounted state,
`errors_count=0` and no-failed-unit health all passed. The documented metadata
check initially ran `stat` outside `sudo` and hit the expected mode-`0700`
parent-directory permission boundary; an explicit `sudo stat` proved the exact
`0:0:600:1` identity before removal. The corrected command is now frozen in
[`AUDIO-JACK-VENDOR-CONTROL.md`](AUDIO-JACK-VENDOR-CONTROL.md). Serial captured
the final read-only remount and `Powering off`; the board is off, USB-DC is
disconnected and the headset is removed.

| Phase | Serial evidence | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| A: exact v0.10 staging | `mainline/out/r46h-serial-logs/attended-input-audio-completion-phase-a-20260821T130833Z.bin` | 69,998 | `ee5cc40851eb2c6a7334465c1c0dc9d75a37a1b971e79391d5f249d02bf9ef2e` |
| B: exact v0.14 L3/R3 | `mainline/out/r46h-serial-logs/attended-input-audio-completion-v014-l3r3-20260821T131933Z.bin` | 63,349 | `d924b1ab2063eb8a10c2464d46cc78015fc74b301b06b0da6551f47d6f5c53a1` |
| C: factory v0.1 infrastructure failure | `mainline/out/r46h-serial-logs/attended-input-audio-completion-vendor-gpio-20260821T133011Z.bin` | 54,815 | `693ac6a84acf300cbd07b770f68e5a7bd7adac8152ec8d30a58759186cab2483` |
| D: exact v0.10 cleanup | `mainline/out/r46h-serial-logs/attended-input-audio-completion-cleanup-v010-20260821T133419Z.bin` | 66,562 | `cc4aa0f82370576b06082a54c170a914e755f17a25066f91f1ec5c9b276f60bf` |

## Frozen host inputs

Use only these four files:

| Purpose | File | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| v0.14 p2 one-shot | `mainline/out/r46h-v14-gaming-input-one-shot/builds/build-ba00cebb7b19-b2193f28e1ae/r46h-v14-gaming-input-one-shot-v1.tar.gz` | 33,167,980 | `b2193f28e1ae8cb625d34e9c191bda9eea48d079e28595d39eaddd5c9dbd3a68` |
| exact bridge v0.5 | `mainline/out/r46h-gaming-input-bridge/builds/build-624b267160d3-67090f7457f1/r46h-gaming-input-bridge-v0.5.tar.gz` | 24,665 | `67090f7457f19717e15f60e2d6c7bda83e6ae76322eaf97c5935b0f90ad94f14` |
| L3/R3 targeted runner | `mainline/bringup-tests/r46h-input-bridge-l3r3-complete` | 15,498 | `fbdca20ecf5eb758c064a88d4cc8410890ad552ba8820de85a0113847221c76f` |
| factory GPIO control ramdisk | `mainline/out/.cache/r46h-audio-jack-vendor-control/uInitrd` | 352,020 | `32f4f0ec8c5924cf31b3743a0f316950050caa38c3c4e41763a4eecd73650f1e` |

The two existing archives remain host-accepted artifacts and are reused only
under the new L3/R3-only contract. Never transfer bridge v0.1 through v0.4 or
the rejected v0.14 one-shot. The legacy-LZ4 ramdisk embeds only the reviewed
static source and empty pseudo-filesystem mountpoints; it is not the factory
`uInitrd` and does not start a persistent rootfs.

Before opening serial, validate without rebuilding the two retained archives,
run the focused tests and independently rehash all four inputs:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-r46h-gaming-input-bridge.py validate
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-v14-gaming-input-one-shot.py validate
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/tests/test-r46h-input-bridge-l3r3-complete.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/tests/test-r46h-audio-jack-vendor-control.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/tests/test-r46h-attended-input-audio-completion.py -v
/usr/bin/shasum -a 256 \
  mainline/out/r46h-v14-gaming-input-one-shot/builds/build-ba00cebb7b19-b2193f28e1ae/r46h-v14-gaming-input-one-shot-v1.tar.gz \
  mainline/out/r46h-gaming-input-bridge/builds/build-624b267160d3-67090f7457f1/r46h-gaming-input-bridge-v0.5.tar.gz \
  mainline/bringup-tests/r46h-input-bridge-l3r3-complete \
  mainline/out/.cache/r46h-audio-jack-vendor-control/uInitrd
```

Require the four hashes above and a clean tracked worktree. Rediscover the
current CH340 device and target Wi-Fi address; never reuse an old serial path,
attachment identity or IP address.

## Common stop rules

Start with the board off, USB-DC disconnected and the headset removed. For
every cold boot, open serial at 1,500,000 baud before applying power and switch
to 115,200 only after the visible `I/TC: OP-TEE version` marker. Do not press
Reset. Never use `saveenv`.

Stop the current phase for a wrong kernel/model/root/config identity, lost
serial, new ext4 error, failed unit, new relevant kernel fault, surviving
candidate process, stuck input, abnormal temperature or unexpected power
behavior. A failed bounded gate is evidence, not permission for an immediate
retry. Use controlled poweroff whenever normal Linux is responsive.

The input result does not cancel the independent factory control, provided the
input phase cleaned up and powered off normally. The factory result never
authorizes headphone playback in this batch.

## Phase A: exact v0.10 readback and inactive staging

1. Cold boot normally into exact
   `6.12.99-r46h-mainline-v0.10-adc-full-range`. Require exact model
   `GameConsole R46H`, p2 PARTUUID `c9f931c9-02`, writable ext4,
   `errors_count=0`, no failed units, stable Wi-Fi, accepted History/config
   hashes and no surviving v0.5/v0.14/audio staging.
2. Require p1 to be unmounted everywhere. Mount it once, read-only, under a
   fresh root-owned tmpfs directory; verify current-media identity and unmount:

```bash
sudo test -z "$(findmnt -rn -S /dev/mmcblk0p1)"
sudo test ! -e /run/r46h-vendor-p1-readback
sudo install -d -o root -g root -m 0700 /run/r46h-vendor-p1-readback
sudo mount -t vfat -o ro,nosuid,nodev,noexec \
  /dev/mmcblk0p1 /run/r46h-vendor-p1-readback
sudo test "$(findmnt -rn -T /run/r46h-vendor-p1-readback -o PARTUUID)" = c9f931c9-01
sudo test "$(findmnt -rn -T /run/r46h-vendor-p1-readback -o FSTYPE)" = vfat
sudo sh -c 'case ",$(findmnt -rn -T /run/r46h-vendor-p1-readback -o OPTIONS)," in *,ro,*) exit 0;; *) exit 1;; esac'
printf '%s  %s\n' \
  'eda795942083d198d7223dcf3f65e19c05c4c7bfc754935e4f84d3a0cc15bbfd' \
    /run/r46h-vendor-p1-readback/Image \
  'ff42fbf07d9455b483f2e21eef074a7b2bcb13eb3ca2cba7c40b1193d6c79af8' \
    /run/r46h-vendor-p1-readback/rk3326-r46h-linux.dtb |
  sudo sha256sum -c -
sudo umount /run/r46h-vendor-p1-readback
sudo rmdir /run/r46h-vendor-p1-readback
```

   Require p1 to be unmounted again. A mismatch ends this batch; do not copy
   replacement files onto BOOT.
3. As unprivileged `ark`, require
   `/home/ark/.cache/r46h-input-audio-completion-v1` to be absent, create it
   mode `0700`, and transfer the four frozen files through the accepted strict
   host-key Wi-Fi workflow with these exact names:

```text
r46h-v14-gaming-input-one-shot-v1.tar.gz
r46h-gaming-input-bridge-v0.5.tar.gz
r46h-input-bridge-l3r3-complete
uInitrd
```

4. Rehash every incoming file before extraction or installation:

```bash
cd /home/ark/.cache/r46h-input-audio-completion-v1
printf '%s  %s\n' \
  'b2193f28e1ae8cb625d34e9c191bda9eea48d079e28595d39eaddd5c9dbd3a68' r46h-v14-gaming-input-one-shot-v1.tar.gz \
  '67090f7457f19717e15f60e2d6c7bda83e6ae76322eaf97c5935b0f90ad94f14' r46h-gaming-input-bridge-v0.5.tar.gz \
  'fbdca20ecf5eb758c064a88d4cc8410890ad552ba8820de85a0113847221c76f' r46h-input-bridge-l3r3-complete \
  '32f4f0ec8c5924cf31b3743a0f316950050caa38c3c4e41763a4eecd73650f1e' uInitrd |
  sha256sum -c -
```

5. Stage the exact v0.14 and v0.5 archives exactly as their accepted
   installers require; the archives already contain their top-level
   directories:

```bash
sudo test ! -e /run/r46h-v14-gaming-input-one-shot-v1
sudo test ! -e /run/r46h-gaming-input-bridge-v0.5
sudo tar -xzf r46h-v14-gaming-input-one-shot-v1.tar.gz -C /run
sudo /run/r46h-v14-gaming-input-one-shot-v1/install.sh
sudo tar -xzf r46h-gaming-input-bridge-v0.5.tar.gz -C /run
sudo /run/r46h-gaming-input-bridge-v0.5/install.sh
```

   Require, in order:

```text
PASS: inactive r46h-v14-gaming-input-one-shot-v1 staged on p2; active BOOT and environment are unchanged.
PASS: inactive R46H gaming input bridge candidate staged; active frontend and BOOT are unchanged.
```

6. Stage the exact factory-control ramdisk using the commands in
   `Inactive p2 staging from exact v0.10` in
   [`AUDIO-JACK-VENDOR-CONTROL.md`](AUDIO-JACK-VENDOR-CONTROL.md). Require only
   `/var/lib/r46h/audio-jack-vendor-control-v0.1/uInitrd`, root ownership,
   directory mode `0700`, file mode `0600`, one link and the exact hash.
7. Remove only the two validated `/run` extraction trees, the two archive
   copies and the now-published incoming ramdisk. Retain only the targeted
   runner in the user cache for Phase B:

```bash
sudo find /run/r46h-v14-gaming-input-one-shot-v1 -xdev -depth -delete
sudo find /run/r46h-gaming-input-bridge-v0.5 -xdev -depth -delete
rm -f \
  r46h-v14-gaming-input-one-shot-v1.tar.gz \
  r46h-gaming-input-bridge-v0.5.tar.gz \
  uInitrd
```

   Require both candidates inactive, the base frontend still active, p1
   unmounted and only the exact targeted runner left in this task's cache.
   Run `sync`, perform controlled poweroff and retain the serial poweroff
   marker.

If a later installer fails, use only an already installed guarded remover while
still on exact v0.10. Verify complete absence of every successfully published
piece before ending the phase; never continue with partial staging.

## Phase B: exact v0.14 L3/R3 completion

1. Cold-open serial as above, interrupt autoboot once and enter the exact
   installed v0.14 `UBOOT-CMDS.txt` commands individually. Never use `saveenv`.
2. Require exact
   `6.12.99-r46h-mainline-v0.14-gaming-input-bridge`, p2 root, matching module
   tree, `CONFIG_INPUT_UINPUT=y`, zero ext4 errors, no failed units, exact v0.5
   inactive state and no combined controller. Begin with both stick caps
   released.
3. Install, rehash and invoke the targeted tmpfs runner exactly as documented
   under `Targeted L3/R3 completion v0.1` in
   [`GAMING-INPUT-BRIDGE.md`](GAMING-INPUT-BRIDGE.md).
4. During the only 20-second window, click/release the left stick cap once,
   then click/release the right stick cap once. Leave both released. Do not
   press Reset, Power, volume controls or F5. Other buttons, stick-axis travel
   and screen behavior are not requested.
5. Preserve the complete two path lines, coverage, cleanup and command-status
   markers. Accept only `controls=2/2`, `result=machine-pass`, `cleanup=pass`
   and command status zero. Remove only the exact `/run` runner even after a
   terminal failure, require no bridge/RetroArch/virtual device/runtime
   residue, recheck health, run `sync` and power off cleanly. Do not retry.

## Phase C: factory `4.4.189` GPIO2_C6 control

1. Keep the headset removed. Cold-open serial and switch baud at the OP-TEE
   marker as above. Interrupt autoboot once.
2. Enter only the exact nested U-Boot block in `One factory-kernel boot` in
   [`AUDIO-JACK-VENDOR-CONTROL.md`](AUDIO-JACK-VENDOR-CONTROL.md). It loads the
   already rehashed factory Image and DTB from p1 plus the exact minimal
   ramdisk from p2, validates all three sizes and the ramdisk checksum, then
   boots with `rdinit=/init`. It neither mounts nor writes a filesystem.
3. If any load, size or `iminfo` branch fails, stop at the U-Boot prompt and
   remove power; no filesystem has been mounted and no environment was saved.
   Record an infrastructure failure and do not improvise another boot command.
4. After the exact init and observation-start markers, fully insert the known
   headset once, hold about two seconds, remove it once and leave it removed.
   Do not press any game or system button. The window ends automatically after
   a complete cycle or 30 seconds and PID 1 powers off.
5. Preserve the exact terminal result, command status, pseudo-filesystem
   cleanup and poweroff markers. Either conclusive result is useful and must
   not be repeated unchanged:
   - a factory raw cycle narrows the next work to a mainline-specific path;
   - factory raw-high throughout keeps the shared electrical/socket/plug or
     common pin-state boundary open.

This phase contains no headphone playback or speaker-muting observation.

## Phase D: ordinary v0.10 removal and final state

1. Cold boot normally into exact persistent v0.10. Recheck model, root,
   History/config, zero ext4 errors, no failed units and stable health. Stop
   the base frontend and require no RetroArch process.
2. Run the exact bridge remover first and v0.14 one-shot remover second:

```bash
sudo /usr/local/sbin/r46h-input-bridge-remove
sudo /var/lib/r46h-gaming-input-one-shot/v0.14-gaming-input-bridge/REMOVE.sh
```

   Require both exact PASS markers and complete absence of the service,
   process, virtual controller, v0.5 state/receipt/runtime, v0.14 p2 payload and
   v0.14 module tree.
3. Rehash and remove only the factory-control ramdisk/file directory using
   `Exact cleanup on the next v0.10 boot` in
   [`AUDIO-JACK-VENDOR-CONTROL.md`](AUDIO-JACK-VENDOR-CONTROL.md).
4. Remove only the retained user-owned runner, then remove its cache directory
   only if empty:

```bash
rm -f \
  /home/ark/.cache/r46h-input-audio-completion-v1/r46h-input-bridge-l3r3-complete
rmdir /home/ark/.cache/r46h-input-audio-completion-v1
```

5. Require exact persistent v0.10, accepted History identities, p1 unmounted,
   complete input/v0.14/vendor-control/transfer staging absence, no RetroArch
   process, `errors_count=0`, no failed units and no new relevant MMC/ext4/
   input/audio/kernel fault. Do not delete any unrelated cache entry.
6. Run `sync`, perform a controlled poweroff and retain serial through
   `Powering off`. Final physical state is board off, USB-DC disconnected and
   the headset removed. Only after all cleanup and evidence checks pass may the
   authoritative ledger change physical status.
