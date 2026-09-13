# R46H attended RK817 headphone-detect probe

Status: **JACK-DETECT PHYSICAL FAIL ON EXACT V0.10 / PHYSICAL OUTPUT LATER
PASSED SEPARATELY / AUTOMATIC DAPM MUTING UNTESTED**

This gate tests one narrow hardware contract: the RK817 jack-detect input must
report one headphone insertion followed by one removal. It does not play audio,
change a mixer, grab an input device, or write the TF card. A PASS therefore
does not prove headphone audio, automatic speaker muting, microphone support or
production volume.

The accepted speaker experiment does not require a v0.11 kernel. Linux 6.12.99
already routes `SPKO`, `HPOL` and `HPOR` through the same `Playback Mux`, whose
default value is `HP`, while the simple-card already declares `Speaker`,
`Headphones` and an active-low headphone-detect GPIO. The faint accepted tone
confirmed the shared HP-fed external-amplifier path. Adding the downstream-only
`use-ext-amplifier` property to the mainline DTS would have no effect because
the upstream RK817 driver does not parse it. No TF-card rewrite is needed for
this detection test.

Primary source references:

- [Rockchip BSP RK817 codec driver](https://github.com/rockchip-linux/kernel/blob/develop-4.4/sound/soc/codecs/rk817_codec.c)
- [Linux 6.12.99 RK817 codec driver](https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/tree/sound/soc/codecs/rk817_codec.c?h=v6.12.99)

## Safety and acceptance

`r46h-audio-jack-probe.c` is pinned to exact v0.10 and the exact
`GameConsole R46H` model. At runtime it requires root and an attended TTY,
discovers exactly one character device named `rk817_int Headphones`, pins its
inode and `st_rdev` with one `O_RDONLY|O_NONBLOCK|O_NOFOLLOW` descriptor, and
checks `EV_SW` plus `SW_HEADPHONE_INSERT`. It issues only evdev query ioctls;
there is no `EVIOCGRAB` and no audio-control operation.

The probe must start with the headphones removed. Within the 30-second maximum,
insert the plug fully once and then remove it once. A complete cycle returns
early. PASS requires the initial and final states to be removed, at least one
real transition in each direction, a final ioctl state consistent with the
event stream, and zero `SYN_DROPPED` events. Catchable termination signals fail
the gate with their conventional `128 + signal` status.

The reviewed source SHA-256 is
`72e22b60ac007c37faacc8c7d2aacb7157126761b6d1e3e847027cf6d96abddc`.
Build it only in the external repository cache; this keeps disposable output
off the Mac's internal disk:

```bash
mkdir -p mainline/out/.cache/r46h-audio-jack-probe
docker run --rm --platform linux/arm64 \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/repo:ro" \
  -v "$PWD/mainline/out/.cache/r46h-audio-jack-probe:/work" \
  -w /work arkos4clone/r46h-kernel-builder:trixie-arm64 \
  /usr/bin/cc -std=c11 -O2 -Wall -Wextra -Werror \
  -o /work/r46h-audio-jack-probe \
  /repo/mainline/bringup-tests/r46h-audio-jack-probe.c
/usr/bin/shasum -a 256 \
  mainline/bringup-tests/r46h-audio-jack-probe.c \
  mainline/out/.cache/r46h-audio-jack-probe/r46h-audio-jack-probe
```

Before target execution, independently compare the first digest with
`72e22b60ac007c37faacc8c7d2aacb7157126761b6d1e3e847027cf6d96abddc` and
compare the second digest with the reviewed ARM64 binary SHA-256
`41dbe0e95ef6e6e2fe614c5acdcd18507714cc4cf94616b8745527bf39657d3e`.
Transfer that exact binary with shell history disabled, then install it only
into root-owned tmpfs:

```bash
sudo install -o root -g root -m 0700 \
  /dev/shm/r46h-audio-jack-probe.incoming \
  /run/r46h-audio-jack-probe
printf '%s  %s\n' \
  '41dbe0e95ef6e6e2fe614c5acdcd18507714cc4cf94616b8745527bf39657d3e' \
  /run/r46h-audio-jack-probe | sudo sha256sum -c -
sudo /run/r46h-audio-jack-probe --observe
probe_status=$?
printf 'R46H_AUDIO_JACK_COMMAND status=%d\n' "$probe_status"
```

The accepted terminal result is:

```text
R46H_AUDIO_JACK_PROBE id=r46h-audio-jack-probe-v0.1 result=pass reason=insert-remove-observed initial=0 insertions=1 removals=1 final=0 syn_dropped=0
R46H_AUDIO_JACK_COMMAND status=0
```

Counts greater than one are acceptable if the connector bounces, provided the
final state is removed and `syn_dropped=0`. Any other terminal marker or exit
status is a failure. Remove both temporary copies before normal poweroff.

## 2026-08-15 inconclusive hardware run

The reviewed ARM64 binary, its self-test and its evdev discovery/preflight all
passed on exact v0.10. Two bounded observation windows reported the removed
state and no transition; the first ended with
`reason=required-transitions-missing initial=0 insertions=0 removals=0 final=0`
and the second was stopped by the operator with the same initial state. The
GPIO debug view was idle-high, which is consistent with the declared
active-low input while no plug is inserted.

The operator subsequently clarified that no headphones were available during
these observations. This is therefore **not** evidence of a broken jack GPIO,
wrong polarity or DTS defect: the required physical stimulus never occurred.
Keep headphone detection, headphone output and automatic speaker muting
deferred. Re-run the gate only when a known working headphone plug is
available; do not change the DTS or build another kernel from this result.

The same serial session repeated the already accepted HP-fed speaker route at
the bounded settings. All machine checks passed and the operator heard sound
from the device with no headphones attached. This reconfirms the physical
speaker only and does not extend the jack-detect boundary.

The ignored serial evidence is
`mainline/out/r46h-serial-logs/v010-audio-jack-20260815.bin` (80,736 bytes,
SHA-256 `7ee9d17afa1cc17ceecfbb66da62cb2dc0643537948d544f39cfafecada8896f`).
It also records `ext4_errors=0`, removal of all temporary probe files, clean
filesystem unmounts and the final `Powering off` marker.

## 2026-08-19 physical failure with replacement headset

The same reviewed binary was rehashed and run once on exact v0.10 after both
v0.14 input candidates had been cleanly removed. The replacement headset was
removed at start. During the only 30-second window the operator fully inserted
the plug, waited approximately two seconds and fully removed it. The exact
terminal result was:

```text
R46H_AUDIO_JACK_PROBE id=r46h-audio-jack-probe-v0.1 result=fail reason=required-transitions-missing initial=0 insertions=0 removals=0 final=0 syn_dropped=0
```

This is a **physical FAIL of the current jack-detect event contract**, unlike
the 2026-08-15 run whose physical stimulus was absent. It proves that the
existing `rk817_int Headphones` evdev path did not report the required switch
transition during this bounded insert/remove cycle. It does not by itself
localize the cause to the socket, GPIO mux/polarity, DTS or codec driver, and it
does not prove headphone output or automatic speaker muting.

The predeclared stop rule was followed: the v0.3 headphone playback mode was
not run, the probe was not repeated, all tmpfs and transfer files were removed,
and exact v0.10 retained zero ext4 errors and failed units. The final
53,906-byte serial log is
`mainline/out/r46h-serial-logs/attended-gaming-retry-v010-return-20260819T120012Z.bin`,
SHA-256 `21a4f19b270ac0a6a1591bd823500bd8d65cfedac61e6e1bcb4a98b8947fb57b`;
it covers exact v0.10, cleanup, read-only remount, complete unmount and
`Powering off`. Do not repeat the unchanged detect gate without a new
diagnostic hypothesis. The reviewed host-only follow-up is now the simultaneous
read-only evdev/GPIO2_C6 sampler in
[`AUDIO-JACK-LOCALIZATION.md`](AUDIO-JACK-LOCALIZATION.md). It ran once on
2026-08-20 and also failed: evdev stayed removed and raw active-low GPIO2_C6
stayed high throughout the complete cycle. Do not repeat either unchanged
probe.

A source review then confirmed that factory and mainline select the same
active-low GPIO2_C6 and that the factory alternate PDM node is disabled. Factory
v0.1 later failed before observation; changed v0.2 then ran once and also saw no
raw transition. Neither result repaired jack reporting. On 2026-08-23 the
changed mechanical v0.4 route gate deliberately bypassed the failed detect
prerequisite without resampling it. Physical headphone output and effective
mechanical speaker cut-off passed, while automatic DAPM muting remained
untested. The exact independent boundary is in
[`AUDIO-ROUTE-PROBE.md`](AUDIO-ROUTE-PROBE.md). Do not repeat any completed
detect, localization, factory-control or v0.4 route gate unchanged.
