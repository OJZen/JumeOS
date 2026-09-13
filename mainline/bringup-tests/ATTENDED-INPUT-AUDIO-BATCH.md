# R46H attended v0.5 input and headphone-localization batch

Status: **COMPLETED 2026-08-20 / INPUT INCOMPLETE (L3/R3 NOT
EXERCISED) / JACK LOCALIZED FAIL / CLEANLY REMOVED**

This was the single reviewed operator session for two changed hypotheses: one
v0.5 combined-input diagnostic trial and one simultaneous GPIO2_C6/evdev
headphone-detect localization cycle. If, and only if, the new localizer observed
both paths, the already reviewed headphone-output route could run once in the
same return boot.

This batch supersedes no result. The completed v0.3 input and old evdev-only
jack gates remain frozen in
[`ATTENDED-GAMING-RETRY.md`](ATTENDED-GAMING-RETRY.md) and must not be repeated.
The detailed acceptance contracts remain
[`GAMING-INPUT-BRIDGE.md`](GAMING-INPUT-BRIDGE.md),
[`AUDIO-JACK-LOCALIZATION.md`](AUDIO-JACK-LOCALIZATION.md) and
[`AUDIO-ROUTE-PROBE.md`](AUDIO-ROUTE-PROBE.md); this file fixes their execution
order and cleanup in one attended window.

The minimum is three cold boots: exact persistent v0.10 for inactive staging,
one exact v0.14 one-shot for input, then ordinary exact v0.10 for candidate
removal and audio. Each boot is also a passive cold-MMC observation. Do not add
a boot merely to reproduce or clear the intermittent initialization signature.
No TF-card rewrite, reset, persistent U-Boot environment change or new kernel
build is part of this batch.

Charging, History, speaker-only playback, direct rumble, USB writes, KMS,
suspend, F5 identification and broad ROM compatibility are excluded. Keep
USB-DC disconnected and the known working 3.5 mm headset removed before the
first power-on.

## Physical result: 2026-08-20

All three cold boots and both bounded gates were completed. Phase A booted
exact persistent `6.12.99-r46h-mainline-v0.10-adc-full-range`, retained the
accepted model/root/History identities and staged the two inactive candidates
with both exact PASS markers. This boot supplied the eighth captured occurrence
of the known 400 kHz `mmc0: error -84`; Linux automatically retried at 300 kHz,
reached SDR104 and retained zero ext4 errors and failed units. Staging cleanup
and controlled poweroff passed.

Phase B booted exact
`6.12.99-r46h-mainline-v0.14-gaming-input-bridge` from the one-shot without
`saveenv`. In the single trial, all 14 keys the operator actually exercised had
complete and identical source/write/virtual press and release counts. All four
axes passed source/write/virtual travel and centering, `SYN_DROPPED=0`, and the
operator saw the D-pad, A and left stick respond on the smoke screen. The exact
axis evidence was:

```text
ABS_X   source 108..1008 final 514; virtual 111..1007 final 513
ABS_Y   source  69..926  final 507; virtual  69..920  final 502
ABS_RX  source  61..839  final 506; virtual  64..839  final 509
ABS_RY  source  72..927  final 526; virtual  78..924  final 527
```

The command reported
`keys=14/16 axes=4/4 centered=4/4 failures=2` and machine FAIL because
`BTN_TRIGGER_HAPPY3`/`BTN_TRIGGER_HAPPY4` had zero source events. The operator
then explicitly reported that L3/R3 had been forgotten. Those two controls are
therefore **not exercised / still open**, not a new physical-source failure.
The v0.5 complete contract is not a PASS and its one permitted trial is spent;
do not rerun it unchanged. Post-trial cleanup, health and controlled poweroff
passed.

Phase C returned normally to exact v0.10. The bridge remover and then the
one-shot remover emitted their exact PASS markers; candidate service, process,
virtual controller, state, runtime files, v0.14 payload and module tree were all
absent before audio. One attempted `sudo -n` invocation stopped at
authentication before the binary emitted a start marker, so it did not start
an observation window. After authorization, the localizer ran exactly once
while the operator performed one full insertion, about a two-second hold and
one removal. It returned:

```text
R46H_AUDIO_JACK_LOCALIZE id=r46h-audio-jack-localize-v0.1 result=fail reason=gpio-transitions-missing localization=gpio-mux-electrical-or-socket-path evdev_initial=0 evdev_insertions=0 evdev_removals=0 evdev_final=0 syn_dropped=0 gpio_initial_raw=1 gpio_insertions=0 gpio_removals=0 gpio_final_raw=1 samples=1452
R46H_AUDIO_JACK_LOCALIZE_COMMAND status=1
```

The conditional route probe was therefore correctly skipped. All target audio
and transfer staging was removed. Final exact v0.10 retained the accepted
History/config identities, zero ext4 errors, no failed units, no relevant new
kernel fault and no frontend/candidate process. Serial confirmed read-only p2,
complete unmount and `Powering off`; final physical state is board off, USB-DC
disconnected and headset removed.

Retained mode-`0600` serial evidence is:

- Phase A: `mainline/out/r46h-serial-logs/attended-input-audio-phase-a-20260820T141022Z.bin`,
  66,649 bytes, SHA-256
  `6135fafa6b1838ece8524841906c4418e5090fe41b17896873e88d893ef9911e`;
- Phase B: `mainline/out/r46h-serial-logs/attended-input-audio-v014-20260820T142017Z.bin`,
  76,786 bytes, SHA-256
  `cd062aa89dffbed3d0b390b8242fb70f6799331b5eb9e47f41d7510c28681d3f`;
- Phase C: `mainline/out/r46h-serial-logs/attended-input-audio-phase-c-20260820T143142Z.bin`,
  68,368 bytes, SHA-256
  `6b06e2c0de7991cf7a25192e2af3ba07bdc5b5ed12818fe57bd79d2ba84c7ac9`.

## Frozen host inputs

Use only these four retained files:

| Purpose | File | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| v0.14 p2 one-shot | `mainline/out/r46h-v14-gaming-input-one-shot/builds/build-ba00cebb7b19-b2193f28e1ae/r46h-v14-gaming-input-one-shot-v1.tar.gz` | 33,167,980 | `b2193f28e1ae8cb625d34e9c191bda9eea48d079e28595d39eaddd5c9dbd3a68` |
| combined input bridge v0.5 | `mainline/out/r46h-gaming-input-bridge/builds/build-624b267160d3-67090f7457f1/r46h-gaming-input-bridge-v0.5.tar.gz` | 24,665 | `67090f7457f19717e15f60e2d6c7bda83e6ae76322eaf97c5935b0f90ad94f14` |
| GPIO2_C6/evdev localizer | `mainline/out/.cache/r46h-audio-jack-localize/r46h-audio-jack-localize` | 72,272 | `d88b5668384405cf52c3bf8d884ed2b881db50aef92e08406319fe23d64ad814` |
| conditional headphone route v0.3 | `mainline/bringup-tests/r46h-audio-route-probe` | 10,961 | `2bfa8d284d14d231a76d3660d7bd96a896a91147e8f53fc2e5e5dc3436bc508b` |

The bridge archive comes from clean source commit
`624b267160d37cd46827f42d8c8b4d4c84ba275c`; its diagnostic runtime directory,
full key-event count comparisons and source/write/virtual axis comparisons are
the new hypothesis. Never transfer v0.1 through v0.4. The localizer binary is
the reviewed ARM64 build of source SHA-256
`7eb0a8aa044822f9cf53f18bccec47441550a1a0c5e72782e2cb1625e2f44014`.

Before opening serial, validate and rehash the retained inputs without
rebuilding them:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-r46h-gaming-input-bridge.py validate
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-v14-gaming-input-one-shot.py validate
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/tests/test-r46h-audio-jack-localize.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/tests/test-r46h-audio-route-probe.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/tests/test-r46h-attended-input-audio-batch.py -v
/usr/bin/shasum -a 256 \
  mainline/out/r46h-v14-gaming-input-one-shot/builds/build-ba00cebb7b19-b2193f28e1ae/r46h-v14-gaming-input-one-shot-v1.tar.gz \
  mainline/out/r46h-gaming-input-bridge/builds/build-624b267160d3-67090f7457f1/r46h-gaming-input-bridge-v0.5.tar.gz \
  mainline/out/.cache/r46h-audio-jack-localize/r46h-audio-jack-localize \
  mainline/bringup-tests/r46h-audio-route-probe
```

Require the four hashes above and a clean tracked worktree. Rediscover the
current CH340 serial device and target Wi-Fi address; never reuse an old device
path, attachment identity or IP address.

## Common stop and continuation rules

Stop the current gate for a wrong kernel/model/root/config identity, lost
serial, new ext4 error, failed unit, new relevant kernel fault, surviving
candidate process, stuck input, abnormal temperature or unexpected power
behavior. Do not press Reset and do not immediately repeat a failed gate. Use a
controlled poweroff whenever the system is responsive.

The v0.5 trial runs at most once even if it fails. An input failure does not
automatically cancel audio: continue only after an ordinary exact v0.10 return,
both installed candidate removers, complete candidate absence and clean health.
The localizer also receives exactly one insert/remove cycle. Any localizer
result other than `result=pass reason=both-paths-observed`, or a nonzero command
status, skips headphone playback. Never fall back to the unchanged
`r46h-audio-jack-probe`.

## Phase A: exact v0.10 preflight and inactive staging

1. With the board off, open cold serial at 1,500,000 baud, 8N1 and no flow
   control before applying power. Switch to 115,200 only after the visible
   `I/TC: OP-TEE version` marker.
2. Let active BOOT start exact
   `6.12.99-r46h-mainline-v0.10-adc-full-range`. Require the exact
   `GameConsole R46H` model, p2 root PARTUUID `c9f931c9-02`, writable ext4,
   `errors_count=0`, no failed units and stable Wi-Fi. Also require:

```text
/etc/r46h/retroarch.cfg sha256 = 697aa82bb42689cd841f16a8ce1ae9c6ac2bdc56ccd1b811136f8f5884e600e9
/var/lib/r46h/gaming-history-v0.2-installed sha256 = 9b800245202992cbdc063e5cabd071a6265fbb9133e89a8718d0952209d0f1aa
/home/ark/.local/share/retroarch identity = 1000:1000:700
```

3. As unprivileged `ark`, require that
   `/home/ark/.cache/r46h-attended-input-audio-v1` does not already exist, then
   create it with `install -d -m 0700`. Transfer the four frozen files using the
   accepted strict-host-key Wi-Fi workflow and these exact target names:

```text
r46h-v14-gaming-input-one-shot-v1.tar.gz
r46h-gaming-input-bridge-v0.5.tar.gz
r46h-audio-jack-localize
r46h-audio-route-probe-v0.3
```

4. Rehash all four incoming files on target before any extraction:

```bash
cd /home/ark/.cache/r46h-attended-input-audio-v1
printf '%s  %s\n' \
  'b2193f28e1ae8cb625d34e9c191bda9eea48d079e28595d39eaddd5c9dbd3a68' r46h-v14-gaming-input-one-shot-v1.tar.gz \
  '67090f7457f19717e15f60e2d6c7bda83e6ae76322eaf97c5935b0f90ad94f14' r46h-gaming-input-bridge-v0.5.tar.gz \
  'd88b5668384405cf52c3bf8d884ed2b881db50aef92e08406319fe23d64ad814' r46h-audio-jack-localize \
  '2bfa8d284d14d231a76d3660d7bd96a896a91147e8f53fc2e5e5dc3436bc508b' r46h-audio-route-probe-v0.3 |
  sha256sum -c -
```

5. Require both exact extraction paths to be absent. The archives already
   contain their required top-level directories, so extract each with `/run`
   itself as the destination and invoke each installer by its absolute path:

```bash
sudo test ! -e /run/r46h-v14-gaming-input-one-shot-v1
sudo test ! -e /run/r46h-gaming-input-bridge-v0.5
sudo tar -xzf \
  /home/ark/.cache/r46h-attended-input-audio-v1/r46h-v14-gaming-input-one-shot-v1.tar.gz \
  -C /run
sudo /run/r46h-v14-gaming-input-one-shot-v1/install.sh
sudo tar -xzf \
  /home/ark/.cache/r46h-attended-input-audio-v1/r46h-gaming-input-bridge-v0.5.tar.gz \
  -C /run
sudo /run/r46h-gaming-input-bridge-v0.5/install.sh
```

   Require, in this order:

```text
PASS: inactive r46h-v14-gaming-input-one-shot-v1 staged on p2; active BOOT and environment are unchanged.
PASS: inactive R46H gaming input bridge candidate staged; active frontend and BOOT are unchanged.
```

6. Require the one-shot and bridge service to remain inactive. Remove only the
   two validated `/run` extraction trees and the two now-unneeded input archive
   copies:

```bash
sudo find /run/r46h-v14-gaming-input-one-shot-v1 -xdev -depth -delete
sudo find /run/r46h-gaming-input-bridge-v0.5 -xdev -depth -delete
rm -f \
  /home/ark/.cache/r46h-attended-input-audio-v1/r46h-v14-gaming-input-one-shot-v1.tar.gz \
  /home/ark/.cache/r46h-attended-input-audio-v1/r46h-gaming-input-bridge-v0.5.tar.gz
```

   Require all four paths to be absent. Retain the two rehashed audio incoming
   files for Phase C. Run `sync`, perform a controlled poweroff and retain the
   serial poweroff marker.

If bridge staging fails after the one-shot was installed, run the installed
one-shot guarded remover while still on exact v0.10, verify complete absence,
remove only this batch's incoming files and stop the batch.

## Phase B: one exact v0.14 input trial

1. Reopen cold serial at 1,500,000 before power and switch after the OP-TEE
   marker. Interrupt autoboot once and enter the exact installed
   `UBOOT-CMDS.txt`; never use `saveenv`.
2. Require exact
   `6.12.99-r46h-mainline-v0.14-gaming-input-bridge`, p2 root, matching module
   directory, `CONFIG_INPUT_UINPUT=y`, zero ext4 errors, no failed units and no
   unexpected active process. Begin with every game button released and both
   sticks centered, then run from the attended TTY:

```bash
sudo /usr/local/sbin/r46h-input-bridge-trial
```

3. During its only 60-second window:
   - visibly confirm D-pad, A and the left stick affect the NES smoke screen;
   - press/release A, B, X, Y, L1, R1, L2, R2, Select, Start and all four
     D-pad directions;
   - physically click the left stick cap once for L3 and the right stick cap
     once for R3;
   - move both sticks through every edge and corner, circle them, then release
     them centered;
   - do not press Power, Reset, either volume control or the unidentified F5
     GPIO.
4. Let the command exit automatically and preserve its complete terminal
   markers. Accept machine state only with
   `R46H_INPUT_BRIDGE_TRIAL result=machine-pass`; physical PASS additionally
   needs the three screen observations. A localization marker is evidence, not
   permission for another trial. Require no remaining bridge, virtual pad or
   RetroArch process, recheck health, run `sync` and power off cleanly.

## Phase C: ordinary v0.10 return, cleanup and audio

1. Cold boot normally into unchanged exact v0.10 and recheck the Phase A
   kernel/model/root, History and health identities. Stop the gaming frontend
   and require no RetroArch process before candidate removal.
2. Run the bridge remover first and the v0.14 one-shot remover second:

```bash
sudo /usr/local/sbin/r46h-input-bridge-remove
sudo /var/lib/r46h-gaming-input-one-shot/v0.14-gaming-input-bridge/REMOVE.sh
```

   Require, in order:

```text
PASS: exact inactive gaming input bridge candidate removed; base frontend and BOOT were unchanged.
PASS: exact v0.14 one-shot staging removed; active BOOT and v0.10 modules were unchanged.
```

   Then require complete absence of the
   bridge service/process/virtual pad/state/receipt/runtime directory, v0.14 p2
   target and v0.14 module tree. The accepted History state must remain exact.
   Do not start audio before these checks pass.
3. With the headset still removed, install only the rehashed localizer into
   root-owned tmpfs, rehash that installed copy and run it once:

```bash
sudo test ! -e /run/r46h-audio-jack-localize
sudo install -o root -g root -m 0700 \
  /home/ark/.cache/r46h-attended-input-audio-v1/r46h-audio-jack-localize \
  /run/r46h-audio-jack-localize
printf '%s  %s\n' \
  'd88b5668384405cf52c3bf8d884ed2b881db50aef92e08406319fe23d64ad814' \
  /run/r46h-audio-jack-localize | sudo sha256sum -c -
sudo /run/r46h-audio-jack-localize --observe
localize_status=$?
printf 'R46H_AUDIO_JACK_LOCALIZE_COMMAND status=%d\n' "$localize_status"
```

   During the only 30-second window, fully insert the known headset once, wait
   about two seconds, then remove it once. Leave it removed when the localizer
   exits. Preserve the terminal result and localization class.
4. Proceed only if the exact result is
   `result=pass reason=both-paths-observed` and command status is zero. Install
   the exact route probe into `/run`, insert the headset again, leave it fully
   inserted and run:

```bash
sudo test ! -e /run/r46h-audio-route-probe
sudo install -o root -g root -m 0700 \
  /home/ark/.cache/r46h-attended-input-audio-v1/r46h-audio-route-probe-v0.3 \
  /run/r46h-audio-route-probe
printf '%s  %s\n' \
  '2bfa8d284d14d231a76d3660d7bd96a896a91147e8f53fc2e5e5dc3436bc508b' \
  /run/r46h-audio-route-probe | sudo sha256sum -c -
sudo /run/r46h-audio-route-probe --headphones-inserted
route_status=$?
printf 'R46H_HEADPHONE_ROUTE_COMMAND status=%d\n' "$route_status"
```

   Machine PASS requires the exact v0.3 observation-required marker, command
   status zero, clean restoration and health. Physical PASS additionally
   requires the operator to hear the bounded 440 Hz tone in the headphones and
   hear no sound from the built-in speaker. Remove the headset after the probe.
   Do not raise gain, repeat speaker-only mode or retry a failed route.

## Final cleanup and state

Remove only the exact task-created tmpfs tools and two user-owned audio incoming
files. Remove the transfer directory only if it is empty:

```bash
sudo rm -f /run/r46h-audio-jack-localize /run/r46h-audio-route-probe
rm -f \
  /home/ark/.cache/r46h-attended-input-audio-v1/r46h-audio-jack-localize \
  /home/ark/.cache/r46h-attended-input-audio-v1/r46h-audio-route-probe-v0.3
rmdir /home/ark/.cache/r46h-attended-input-audio-v1
```

Do not delete unrelated cache entries. Require exact persistent v0.10, accepted
History identities, complete v0.5/v0.14 and audio staging absence, no RetroArch
process, `errors_count=0`, no failed units and no new relevant kernel fault.
Run `sync`, perform a controlled poweroff and retain serial through
`Powering off`. Final physical state is board off, USB-DC disconnected and the
headset removed.
