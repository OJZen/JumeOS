# R46H attended RK817 audio route probe

Status: **SPEAKER HP ROUTE PASS / HEADPHONE OUTPUT + MECHANICAL SPEAKER
CUT-OFF PASS / JACK DETECT FAILED / AUTOMATIC DAPM MUTING UNTESTED**

This gate tests one narrow hypothesis: the R46H speaker amplifier is fed from
the RK817 headphone DAC path rather than the RK817 Class-D path. It does not
change the DTB, kernel, root filesystem or TF-card contents.

The hypothesis comes from two independently checked sources:

- the R46H vendor DTB has `use-ext-amplifier` but no `spk-ctl-gpios` or
  `hp-ctl-gpios`;
- Rockchip's `develop-4.4` RK817 driver implements that boolean by powering the
  HP charge pump, HP op-amp and left/right DACs for its speaker path. Without
  the boolean it powers the internal Class-D/SPK DAC instead.

Linux 6.12.99 already exposes the equivalent choice as `Playback Mux` with
`HP` and `SPK` values. The earlier accepted negative test selected `SPK` twice
and heard nothing. Therefore the next test selects `HP` while keeping the
simple-card `Speaker` endpoint active. Copying the vendor-only property into
the mainline DTS would do nothing because the upstream driver does not parse
it.

Primary source references:

- [Rockchip BSP RK817 codec driver](https://github.com/rockchip-linux/kernel/blob/develop-4.4/sound/soc/codecs/rk817_codec.c)
- [Linux 6.12.99 RK817 codec driver](https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/tree/sound/soc/codecs/rk817_codec.c?h=v6.12.99)

## Safety and interpretation

`r46h-audio-route-probe` is pinned to exact v0.10 and must run from the
root-owned tmpfs path `/run/r46h-audio-route-probe`. It saves the current
Master Playback Volume and Playback Mux values, selects HP with value `0`, and
uses a 440 Hz stereo tone at scale 40 with the preserved system playback value
`201,201`. The completed speaker mode is bounded to four seconds; the completed
mechanical-headphone mode is bounded to two seconds. Both controls are restored
on success, failure or a catchable signal.

The helper also checks the exact board/kernel/root identity, failed units,
ext4 error counter, dmesg continuity, new storage/audio faults and the two DAPM
endpoint states required by the selected mode. All evidence is temporary under
`/run` and is removed before the terminal marker.

This is attended evidence. Exit zero and
`result=observation-required cleanup=pass` prove only that the bounded PCM job,
state restoration and health checks succeeded. They never prove audible
output. The operator must separately state whether the tone was heard. Stop
after this one attempt; do not increase volume or repeat SPK mode merely to
obtain a different answer.

The first conservative HP-path attempt used scale 20 and ALSA value `190,190`;
its machine checks passed but the operator heard nothing. The reviewed v0.2
helper made one final volume-control comparison using the pre-existing
`201,201` mixer value and the same scale 40 already used by an earlier bounded
SPK-path attempt. Every machine gate passed and the operator heard a faint,
identifiable 440 Hz `bu~~` tone. This proves the physical speaker's HP-fed
external-amplifier route, but not normal gain or headphone switching. Do not
raise either value or repeat this completed comparison.

A later bounded repeat in the headphone-detect session also passed every
machine check and was audible. The operator then clarified that no headphones
were attached or available, so that repeat only reconfirms the speaker result;
it is not a headphone-output or switching test. A later replacement-headset
session is recorded below.

The accepted speaker-only v0.2 script SHA-256 was
`1af064e3d20f12f86127d385a613b6eb99e4e800c5ea401f564aeaa4cae10a97`.
After transferring it through the serial session with history disabled:

```bash
sudo install -o root -g root -m 0700 \
  /dev/shm/r46h-audio-route-probe.incoming \
  /run/r46h-audio-route-probe
printf '%s  %s\n' \
  '1af064e3d20f12f86127d385a613b6eb99e4e800c5ea401f564aeaa4cae10a97' \
  /run/r46h-audio-route-probe | sudo sha256sum -c -
sudo /run/r46h-audio-route-probe --hp-external-amp
probe_status=$?
printf 'R46H_AUDIO_ROUTE_COMMAND status=%d\n' "$probe_status"
```

The only accepted machine result before the human observation is:

```text
R46H_AUDIO_ROUTE_PROBE id=r46h-audio-route-probe-v0.2 route=HP result=observation-required failures=0 cleanup=pass reason=operator-audibility-required frequency=440 scale=40 volume=201,201 seconds=4
R46H_AUDIO_ROUTE_COMMAND status=0
```

The accepted result is audible. A second source-level review then confirmed
that the current upstream machine/codec graph already models the relevant
shared path: `SPKO`, `HPOL` and `HPOR` all select the same `Playback Mux`, whose
default value is `HP`, and simple-card already declares both `Speaker` and
`Headphones`. No v0.11 kernel or DTS change is justified by this experiment.
The next step is the separate read-only headphone-detect gate in
[`AUDIO-JACK-PROBE.md`](AUDIO-JACK-PROBE.md); do not invent an enable GPIO.
The vendor DTB exposes none, and the successful route experiment did not need
one.

## Retired detect-gated headphone-output mode (v0.3)

The 2026-08-19 replacement-headset session did not execute this mode. Its
required read-only jack gate reported
`reason=required-transitions-missing initial=0 insertions=0 removals=0 final=0 syn_dropped=0`
after the attended insert/remove cycle. The batch therefore
skipped playback exactly as required. At that gate, headphone output and
automatic speaker muting remained **UNTESTED**, not failed; the jack-detect path
was the failed prerequisite. The later exact-factory control also left the
shared raw GPIO high throughout its one insertion/removal cycle. The v0.3 mode
is therefore retired and is not present in v0.4; do not run it even if an old
copy remains.

The v0.3 source keeps the completed speaker mode and adds one separate
`--headphones-inserted` gate. Run it only after the read-only jack probe has
observed a complete insert/remove cycle. Stop the gaming frontend, insert the
known working headphones fully, leave them inserted for the entire four-second
probe, and do not run the completed speaker mode again.

The new mode uses the same already accepted HP mux, `201,201` mixer value,
scale 40 and four-second bound. During active PCM it requires DAPM `Speaker:
Off` and `Headphones: On`; it also requires RetroArch to be inactive, restores
both mixer controls and retains the same health checks. This machine gate does
not prove audible routing. The operator must separately report both sound in
the headphones and silence from the built-in speaker.

The reviewed v0.3 script SHA-256 is
`2bfa8d284d14d231a76d3660d7bd96a896a91147e8f53fc2e5e5dc3436bc508b`.
Transfer it into root-owned tmpfs and run only the new mode:

```bash
sudo install -o root -g root -m 0700 \
  /dev/shm/r46h-audio-route-probe-v0.3.incoming \
  /run/r46h-audio-route-probe
printf '%s  %s\n' \
  '2bfa8d284d14d231a76d3660d7bd96a896a91147e8f53fc2e5e5dc3436bc508b' \
  /run/r46h-audio-route-probe | sudo sha256sum -c -
sudo /run/r46h-audio-route-probe --headphones-inserted
probe_status=$?
printf 'R46H_HEADPHONE_ROUTE_COMMAND status=%d\n' "$probe_status"
```

The only accepted machine result before the two human observations is:

```text
R46H_AUDIO_ROUTE_PROBE id=r46h-audio-route-probe-v0.3 route=HP result=observation-required failures=0 cleanup=pass reason=operator-headphone-audio-and-speaker-silence-required frequency=440 scale=40 volume=201,201 seconds=4
R46H_HEADPHONE_ROUTE_COMMAND status=0
```

Any jack-detect failure skips this mode. Any unexpected DAPM state, audible
speaker output, missing headphone output, cleanup failure or health regression
is a failed/inconclusive headphone route result, not a reason to increase gain
or edit the DTS during the batch.

## Completed mechanical socket/output mode (v0.4)

The changed hypothesis is now below the failed software-detect boundary: a
fully inserted 3.5 mm plug may mechanically transfer the already accepted HP
analog signal to the headset and cut the HP-fed external speaker even while
mainline DAPM remains `Speaker: On` and `Headphones: Off`. This mode does not
run the jack event probe, sample GPIO2_C6, expect a transition or claim that
automatic DAPM muting works.

The v0.4 mode reuses the physically audible `201,201`/scale-40 speaker baseline
but shortens playback from four seconds to two. Keep both earpieces away from
the ears for the entire test; listen only at a safe distance. The script
requires the literal `R46H-HEADPHONE-READY` confirmation before changing the
mixer. Do not wear the headset, increase either level or repeat the attempt if
the result is quiet or ambiguous.

The reviewed v0.4 script SHA-256 is
`db7fce6727e70fef11f6fc25530024db3ee8a132a7a00183d698b2577710077a`.
On exact persistent v0.10, stop the frontend, fully insert the known headset,
leave it inserted and install only that exact script in root-owned tmpfs:

```bash
sudo systemctl stop r46h-gaming-frontend.service
test "$(systemctl is-active r46h-gaming-frontend.service || true)" = inactive
sudo install -o root -g root -m 0700 \
  /dev/shm/r46h-audio-route-probe-v0.4.incoming \
  /run/r46h-audio-route-probe
printf '%s  %s\n' \
  'db7fce6727e70fef11f6fc25530024db3ee8a132a7a00183d698b2577710077a' \
  /run/r46h-audio-route-probe | sudo sha256sum -c -
sudo /run/r46h-audio-route-probe --headphones-mechanical
probe_status=$?
printf 'R46H_HEADPHONE_MECHANICAL_COMMAND status=%d\n' "$probe_status"
```

After the ready marker, keep the headset out of the ears, type the exact token
once and observe two independent facts: whether the 440 Hz tone comes from the
headset and whether the built-in speaker remains audible. Before interpreting
either observation, require exactly:

```text
R46H_AUDIO_ROUTE_PROBE id=r46h-audio-route-probe-v0.4 route=HP mode=headphones-mechanical result=observation-required failures=0 cleanup=pass reason=operator-mechanical-headphone-audio-and-speaker-silence-required frequency=440 scale=40 volume=201,201 seconds=2
R46H_HEADPHONE_MECHANICAL_COMMAND status=0
```

Classify the two human observations without combining them:

| Headset tone | Built-in speaker | Accepted interpretation |
| --- | --- | --- |
| heard | silent | Physical headphone output and effective mechanical speaker cut-off PASS; jack detect remains failed and automatic DAPM muting remains untested |
| heard | heard | Physical headphone output PASS; mechanical speaker cut-off FAIL |
| not heard | heard | Mechanical headphone transfer/output FAIL at the accepted audible speaker setting |
| not heard or uncertain | silent or uncertain | Inconclusive; do not raise gain or repeat in the same batch |

The only physical run completed on 2026-08-23 under exact persistent v0.10.
The machine marker and command status matched the accepted pair above with
`failures=0 cleanup=pass`. The operator separately reported that the tone was
audible in the fully inserted headset while the built-in speaker was silent.
This accepts physical headphone output and effective mechanical speaker
cut-off. Because the deliberately unchanged DAPM state remained `Speaker: On`
and `Headphones: Off`, this result does not repair the failed jack-detect path
or prove automatic DAPM muting.

The run removed both target copies, retained zero ext4 errors and failed units,
preserved the accepted History config and receipt, left p1/p3 unmounted, then
remounted p2 read-only and powered off normally. Its required cold boot also
repeated the known 400/300 kHz initialization `mmc0: error -84`, recovered to
SDR104 and produced no later storage fault. The ignored 68,621-byte serial log
is `mainline/out/r46h-serial-logs/headphone-mechanical-v04-20260823T070248Z.bin`,
SHA-256
`ececb7460ce08bf07cec5d329627b193338237d092146eb216ee515bd8420083`.

This gate is complete and must not repeat unchanged. Any future audio work must
target a different boundary, such as automatic jack reporting/DAPM routing or
microphone capture; do not increase the accepted playback level.
