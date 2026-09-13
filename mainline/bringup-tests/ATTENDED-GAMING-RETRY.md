# R46H attended input and headphone retry

Status: **COMPLETE / INPUT V0.3 FAIL / JACK DETECT FAIL / ROUTE SKIPPED / CLEANLY REMOVED**

This was the consolidated 2026-08-19 operator session. It contained exactly two
active gates: one v0.3 combined-input retry and the deferred headphone
detect/output pair. The already accepted History result was a prerequisite,
not a repeated gate. Charging, speaker-only playback, F5 identification, KMS,
suspend, USB writes and application rumble were excluded.

The batch needs three boots: cold exact v0.10 to stage inactive candidates, one
cold exact v0.14 one-shot for input, then ordinary exact v0.10 for candidate
removal and headphones. Each required cold boot is also a passive MMC sample;
do not add a boot merely to reproduce or clear the intermittent signature.

## Frozen host inputs

Use only these four retained files:

| Purpose | File | SHA-256 |
| --- | --- | --- |
| v0.14 p2 one-shot | `mainline/out/r46h-v14-gaming-input-one-shot/builds/build-ba00cebb7b19-b2193f28e1ae/r46h-v14-gaming-input-one-shot-v1.tar.gz` | `b2193f28e1ae8cb625d34e9c191bda9eea48d079e28595d39eaddd5c9dbd3a68` |
| combined input bridge v0.3 | `mainline/out/r46h-gaming-input-bridge/builds/build-c35da7b71f5f-e59ff0a4b9d9/r46h-gaming-input-bridge-v0.3.tar.gz` | `e59ff0a4b9d93a362155fbf66ecf8bd79f0d91e22e644919b4046d3d2187ae4f` |
| jack-detect binary | `mainline/out/.cache/r46h-audio-jack-probe/r46h-audio-jack-probe` | `41dbe0e95ef6e6e2fe614c5acdcd18507714cc4cf94616b8745527bf39657d3e` |
| headphone route v0.3 | `mainline/bringup-tests/r46h-audio-route-probe` | `2bfa8d284d14d231a76d3660d7bd96a896a91147e8f53fc2e5e5dc3436bc508b` |

Do not transfer input bridge v0.1 or v0.2. V0.1 physically failed; v0.2 pins
the pre-History config and is target-incompatible with the accepted current
state. No History archive is needed because History v0.2 is already installed
and physically accepted.

Before the device session, run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-r46h-gaming-input-bridge.py validate
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-v14-gaming-input-one-shot.py validate
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/tests/test-r46h-audio-jack-probe.py
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/tests/test-r46h-audio-route-probe.py
/usr/bin/shasum -a 256 \
  mainline/out/r46h-v14-gaming-input-one-shot/builds/build-ba00cebb7b19-b2193f28e1ae/r46h-v14-gaming-input-one-shot-v1.tar.gz \
  mainline/out/r46h-gaming-input-bridge/builds/build-c35da7b71f5f-e59ff0a4b9d9/r46h-gaming-input-bridge-v0.3.tar.gz \
  mainline/out/.cache/r46h-audio-jack-probe/r46h-audio-jack-probe \
  mainline/bringup-tests/r46h-audio-route-probe
```

Have one known working 3.5 mm headset available before power-on. Keep USB-DC
disconnected. Rediscover the CH340 device; never reuse an old serial path.

## Common stop conditions

Stop the current gate for wrong kernel/root/config identity, lost serial, a new
ext4 error, failed unit, new relevant kernel fault, surviving candidate process,
stuck input, abnormal temperature or unexpected power behavior. Do not reset or
immediately repeat. Use controlled poweroff when responsive, return normally to
exact v0.10 and run only the applicable guarded cleanup.

An input failure does not automatically skip headphones. Continue only after
ordinary v0.10, both candidate removers and clean health are re-established.
A jack-detect failure always skips headphone playback.

## Executed result: 2026-08-19

Phase A booted exact v0.10, verified the accepted History config, receipt and
user-state identities, rehashed all four frozen inputs, and staged both input
candidates inactive. The known intermittent cold-MMC signature recurred once
at 400 kHz, recovered through the automatic 300 kHz retry, reached SDR104 and
had no later storage or ext4 fault. Both installers emitted their required
inactive PASS markers. The 56,409-byte serial log is
`mainline/out/r46h-serial-logs/attended-gaming-retry-phase-a-20260819T114332Z.bin`,
SHA-256 `4db87fcd98a860bbc7ca296d97ff8df3be620547669d94537e79877b39cc405f`.

Phase B booted exact v0.14 once and ran exactly one trial. It reported
`SYN_DROPPED=0`, 4/16 keys, 4/4 axes with travel and 3/4 centered axes. The
only covered keys were `BTN_TL`, `BTN_TR`, `BTN_TL2` and `BTN_TR2`; all D-pad
directions, A/B/X/Y, Select, Start, L3 and R3 were missing. `ABS_RY` ended at
914 and failed the centering gate. The operator confirmed completing all
requested actions and saw only the left stick respond on screen; D-pad and A
did not respond. The exact terminal markers were:

```text
R46H_INPUT_BRIDGE_COVERAGE keys=4/16 axes=4/4 centered=3/4 failures=13
R46H_INPUT_BRIDGE_TRIAL result=fail status=1 cleanup=check-required
```

This is **V0.3 PHYSICAL FAIL**, not a partial pass, and the unchanged trial was
not repeated. Post-trial checks found no surviving bridge, virtual gamepad or
failed unit and retained `errors_count=0`. The 57,833-byte serial log is
`mainline/out/r46h-serial-logs/attended-gaming-retry-v014-20260819T115332Z.bin`,
SHA-256 `36f026a5ba8cf8904e6dd06e0bee26c3523019f4d85ed34c526fbad760e78828`.

Phase C returned normally to exact v0.10. The bridge remover first failed
closed without mutation because RetroArch was still active. After the base
frontend was stopped and its process absence confirmed, the bridge remover and
then the v0.14 one-shot remover emitted their exact PASS markers. Candidate
state, runtime files, virtual gamepad and v0.14 modules were absent; the
accepted History identities remained exact.

Phase D used the exact rehashed jack probe with the replacement headset removed
at start. During its only 30-second window the operator fully inserted the plug,
waited and removed it. The event device remained coherent but reported no
switch transition:

```text
R46H_AUDIO_JACK_PROBE id=r46h-audio-jack-probe-v0.1 result=fail reason=required-transitions-missing initial=0 insertions=0 removals=0 final=0 syn_dropped=0
```

This is **JACK-DETECT PHYSICAL FAIL** for the current exact v0.10 path. Per the
predeclared stop rule, headphone playback and automatic speaker-muting
observations were skipped, so both remain untested rather than failed. No
second detect attempt was made.

Final cleanup removed both `/run` tools, all four transferred artifacts, the
temporary staging helper and the transfer directory. Exact v0.10, p2,
History, zero ext4 errors, zero failed units and complete candidate absence all
rechecked. This return boot reached SDR104 directly without the old `-84`;
that non-reproduction does not close the intermittent issue. The system then
remounted p2 read-only, unmounted all filesystems and reached `Powering off`.
The 53,906-byte serial log is
`mainline/out/r46h-serial-logs/attended-gaming-retry-v010-return-20260819T120012Z.bin`,
SHA-256 `21a4f19b270ac0a6a1591bd823500bd8d65cfedac61e6e1bcb4a98b8947fb57b`.
Final physical state is powered off with USB-DC disconnected and the headset
removed.

## Phase A: exact v0.10 preflight and inactive staging

1. Open cold serial at 1,500,000 8N1 with no flow control before applying power.
   Switch to 115,200 only after the visible `I/TC: OP-TEE version` marker.
2. Let persistent BOOT start exact
   `6.12.99-r46h-mainline-v0.10-adc-full-range`. Require p2 PARTUUID
   `c9f931c9-02`, writable ext4, `errors_count=0`, no failed units and stable
   Wi-Fi. Also require:

```text
/etc/r46h/retroarch.cfg sha256 = 697aa82bb42689cd841f16a8ce1ae9c6ac2bdc56ccd1b811136f8f5884e600e9
/var/lib/r46h/gaming-history-v0.2-installed sha256 = 9b800245202992cbdc063e5cabd071a6265fbb9133e89a8718d0952209d0f1aa
/home/ark/.local/share/retroarch identity = 1000:1000:700
```

3. As unprivileged `ark`, create mode `0700`
   `/home/ark/.cache/r46h-attended-gaming-v2` and transfer the four frozen files
   using the accepted strict-host-key SSH workflow. Use these exact names:

```text
r46h-v14-gaming-input-one-shot-v1.tar.gz
r46h-gaming-input-bridge-v0.3.tar.gz
r46h-audio-jack-probe
r46h-audio-route-probe-v0.3
```

4. Rehash all four on target before extraction:

```bash
cd /home/ark/.cache/r46h-attended-gaming-v2
printf '%s  %s\n' \
  'b2193f28e1ae8cb625d34e9c191bda9eea48d079e28595d39eaddd5c9dbd3a68' r46h-v14-gaming-input-one-shot-v1.tar.gz \
  'e59ff0a4b9d93a362155fbf66ecf8bd79f0d91e22e644919b4046d3d2187ae4f' r46h-gaming-input-bridge-v0.3.tar.gz \
  '41dbe0e95ef6e6e2fe614c5acdcd18507714cc4cf94616b8745527bf39657d3e' r46h-audio-jack-probe \
  '2bfa8d284d14d231a76d3660d7bd96a896a91147e8f53fc2e5e5dc3436bc508b' r46h-audio-route-probe-v0.3 |
  sha256sum -c -
```

5. Extract the one-shot and v0.3 bridge as root under `/run`. Run the one-shot
   installer first, then the bridge installer. Require both inactive PASS
   markers. The bridge preflight must accept the exact installed History state;
   any old-config mismatch is a failure, not a reason to roll History back.
6. Remove only the two verified `/run` extraction trees, run `sync` and power
   off cleanly. Retain the four target transfer files until final cleanup.

## Phase B: one exact v0.14 input trial

1. Reopen cold serial at 1,500,000 before power, switch at the OP-TEE marker,
   interrupt autoboot once and enter the exact installed `UBOOT-CMDS.txt`.
   Never use `saveenv`.
2. Require exact `6.12.99-r46h-mainline-v0.14-gaming-input-bridge`, p2 root,
   matching modules, zero ext4 errors and no failed units. Start with every game
   button released and both sticks centered, then run:

```bash
sudo /usr/local/sbin/r46h-input-bridge-trial
```

3. During its only 60-second window:
   - visibly confirm D-pad, A and left-stick movement on the smoke screen;
   - press/release A, B, X, Y, L1, R1, L2, R2, Select, Start and each D-pad;
   - physically click the left stick cap once for L3 and the right stick cap
     once for R3;
   - move both sticks through edges/corners, circle them and release centered;
   - do not press Power, Reset, volume controls or F5.
4. Require the machine PASS and operator observations in
   [`GAMING-INPUT-BRIDGE.md`](GAMING-INPUT-BRIDGE.md). Do not run a second trial.
   Check health, `sync` and power off.

## Phase C: ordinary v0.10 return and candidate cleanup

1. Boot normally into unchanged exact v0.10 and verify health plus the accepted
   History config/receipt/state identities from Phase A.
2. Run the installed bridge remover first, then the one-shot remover:

```bash
sudo /usr/local/sbin/r46h-input-bridge-remove
sudo /var/lib/r46h-gaming-input-one-shot/v0.14-gaming-input-bridge/REMOVE.sh
```

3. Require both PASS markers and absence of the bridge process, virtual pad,
   candidate unit/state and v0.14 module tree. History v0.2 must remain intact.

## Phase D: headphone detect and route

Stop the gaming frontend and require no RetroArch process. Install the two
rehashed tools only into root-owned tmpfs:

```bash
sudo install -o root -g root -m 0700 \
  /home/ark/.cache/r46h-attended-gaming-v2/r46h-audio-jack-probe \
  /run/r46h-audio-jack-probe
sudo install -o root -g root -m 0700 \
  /home/ark/.cache/r46h-attended-gaming-v2/r46h-audio-route-probe-v0.3 \
  /run/r46h-audio-route-probe
```

With the headset removed, run the exact 30-second gate in
[`AUDIO-JACK-PROBE.md`](AUDIO-JACK-PROBE.md). Insert it fully once, then remove
it once. Require its insert/remove PASS and zero `SYN_DROPPED`.

Only after detector PASS, insert the headset again, leave it inserted and run:

```bash
sudo /run/r46h-audio-route-probe --headphones-inserted
```

Require the machine marker in
[`AUDIO-ROUTE-PROBE.md`](AUDIO-ROUTE-PROBE.md). Physical PASS additionally
requires the 440 Hz tone in the headset and silence from the built-in speaker.
Remove the headset after the probe. Do not raise gain or repeat speaker mode.

## Final cleanup and state

Remove only the two `/run` audio tools and four exact transfer files, then the
transfer directory if empty:

```bash
sudo rm -f /run/r46h-audio-jack-probe /run/r46h-audio-route-probe
rm -f \
  /home/ark/.cache/r46h-attended-gaming-v2/r46h-v14-gaming-input-one-shot-v1.tar.gz \
  /home/ark/.cache/r46h-attended-gaming-v2/r46h-gaming-input-bridge-v0.3.tar.gz \
  /home/ark/.cache/r46h-attended-gaming-v2/r46h-audio-jack-probe \
  /home/ark/.cache/r46h-attended-gaming-v2/r46h-audio-route-probe-v0.3
rmdir /home/ark/.cache/r46h-attended-gaming-v2
```

Require exact v0.10, accepted History config/receipt/state, no candidate
service/process/module tree, no RetroArch process, `errors_count=0`, no failed
units and no new relevant kernel fault. Run `sync`, perform controlled poweroff
and retain the serial `Powering off` marker. Final state is powered off with
USB-DC disconnected, History v0.2 still installed and no v0.14 staging.
