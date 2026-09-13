# R46H attended headphone-detect localization

Status: **PHYSICAL FAIL / NO GPIO2_C6 OR EVDEV TRANSITIONS / ROUTE SKIPPED /
CLEANLY REMOVED**

The 2026-08-19 replacement-headset run physically failed the existing evdev
transition gate: one complete plug insertion and removal produced no
`SW_HEADPHONE_INSERT` transition. This follow-up does not replace or repeat the
unchanged v0.1 gate. It adds one new observation: the raw level reported for
the already-requested active-low `gpio-86` / GPIO2_C6 line is sampled at the
same time as the exact RK817 headphone evdev device.

This is a bounded localization tool, not a fix. It can distinguish a raw GPIO
cycle that fails to reach evdev from a cycle that is absent at both layers. It
does not determine the final socket, board-trace, mux, pull, GPIO-controller or
ASoC cause by itself. It does not authorize headphone playback, automatic
speaker-muting claims, a DTS polarity change or another kernel build.

## Physical result: 2026-08-20

The exact 72,272-byte binary was transferred, rehashed and installed only in
root-owned `/run` on exact persistent v0.10 after complete input-candidate
removal. A first `sudo -n` command stopped at authentication before the binary
emitted a start marker, so no observation window or GPIO/evdev access began.
After authorization, the binary emitted exactly one start marker and the
operator fully inserted the known headset once, held it for about two seconds
and removed it once. The terminal result was:

```text
R46H_AUDIO_JACK_LOCALIZE id=r46h-audio-jack-localize-v0.1 result=fail reason=gpio-transitions-missing localization=gpio-mux-electrical-or-socket-path evdev_initial=0 evdev_insertions=0 evdev_removals=0 evdev_final=0 syn_dropped=0 gpio_initial_raw=1 gpio_insertions=0 gpio_removals=0 gpio_final_raw=1 samples=1452
R46H_AUDIO_JACK_LOCALIZE_COMMAND status=1
```

The raw active-low GPIO2_C6 debug line stayed high and the RK817 evdev switch
stayed logically removed throughout. This is physical FAIL localization at the
current GPIO selection/mux/electrical/socket boundary, not proof of one specific
hardware or software cause. The required stop rule skipped headphone playback
and speaker-muting observation. Do not repeat this unchanged localizer; inspect
the mux/pull, board trace and socket contact before defining another gate.

Both transferred audio files and both exact `/run` paths were removed. Final
v0.10 health, History identity, candidate absence, controlled unmount and
poweroff passed. The complete result and serial evidence are in
[`ATTENDED-INPUT-AUDIO-BATCH.md`](ATTENDED-INPUT-AUDIO-BATCH.md).

## Safety and contract

`r46h-audio-jack-localize.c` is pinned to exact persistent v0.10, the exact
`GameConsole R46H` model, one character device named `rk817_int Headphones`,
and the debugfs line containing `gpio-86`, `Headphone detection` and
`IRQ ACTIVE LOW`. It opens evdev and `/sys/kernel/debug/gpio` read-only. It
does not grab input, request a GPIO, change pinctrl, load a module, touch a
mixer, or play audio. It must not be run with `gpioget` or any other tool that
tries to request the already-owned line.

The probe must start and finish with the headset removed: evdev logical state
`0` and raw active-low GPIO state `high`. During its maximum 30-second window,
fully insert the known headset once, wait about two seconds, then remove it
once. It samples the debugfs line every 20 ms and allows 500 ms after a complete
raw cycle for the debounced evdev event to arrive. It neither mounts nor writes
persistent storage. No TF-card rewrite or kernel change is needed.

The result classes are deliberately narrow:

| Terminal reason | Meaning |
| --- | --- |
| `both-paths-observed` | Raw GPIO and evdev both saw one insert/remove cycle; this diagnostic passes. |
| `evdev-transitions-missing`, `localization=evdev-or-asoc-path` | Raw GPIO toggled low/high, but evdev did not report the same cycle. Investigate the GPIO-to-ASoC reporting path. |
| `gpio-transitions-missing`, `localization=gpio-mux-electrical-or-socket-path` | Neither layer saw a complete raw cycle. Investigate GPIO selection/mux/pull, board trace and socket contact before changing software. |
| `gpio-samples-inconsistent`, `localization=debug-gpio-path` | Evdev saw a cycle that the sampled debug view did not; do not draw a hardware conclusion. |

Any identity, state, framing, `SYN_DROPPED`, signal or final-removal failure is
also a FAIL. A result from this tool is localization evidence only.

## Reviewed artifact

The reviewed source SHA-256 is
`7eb0a8aa044822f9cf53f18bccec47441550a1a0c5e72782e2cb1625e2f44014`.
Build only in the external repository cache:

```bash
mkdir -p mainline/out/.cache/r46h-audio-jack-localize
docker run --rm --platform linux/arm64 \
  --user "$(id -u):$(id -g)" \
  -v "$PWD:/repo:ro" \
  -v "$PWD/mainline/out/.cache/r46h-audio-jack-localize:/work" \
  -w /work arkos4clone/r46h-kernel-builder:trixie-arm64 \
  /usr/bin/cc -std=c11 -O2 -Wall -Wextra -Werror \
  -o /work/r46h-audio-jack-localize \
  /repo/mainline/bringup-tests/r46h-audio-jack-localize.c
/usr/bin/shasum -a 256 \
  mainline/bringup-tests/r46h-audio-jack-localize.c \
  mainline/out/.cache/r46h-audio-jack-localize/r46h-audio-jack-localize
```

Independently require source SHA-256
`7eb0a8aa044822f9cf53f18bccec47441550a1a0c5e72782e2cb1625e2f44014`
and ARM64 binary SHA-256
`d88b5668384405cf52c3bf8d884ed2b881db50aef92e08406319fe23d64ad814`.
The host-built binary is 72,272 bytes. Its self-test passed in the pinned ARM64
builder container. This is host artifact proof only.

## Executed attended contract

The physical run transferred the exact binary through the accepted
authenticated Wi-Fi path, installed it only into root-owned tmpfs, rehashed it
and invoked it from an attended TTY using this frozen sequence:

```bash
sudo install -o root -g root -m 0700 \
  /dev/shm/r46h-audio-jack-localize.incoming \
  /run/r46h-audio-jack-localize
printf '%s  %s\n' \
  'd88b5668384405cf52c3bf8d884ed2b881db50aef92e08406319fe23d64ad814' \
  /run/r46h-audio-jack-localize | sudo sha256sum -c -
sudo /run/r46h-audio-jack-localize --observe
localize_status=$?
printf 'R46H_AUDIO_JACK_LOCALIZE_COMMAND status=%d\n' "$localize_status"
```

Only one actual insert/remove observation cycle ran. Both transfer and `/run`
copies were removed, ext4 and failed-unit health passed, and the board powered
off under serial. Because the result was not
`result=pass reason=both-paths-observed`, the separately reviewed route gate did
not run. The completed combined execution and cleanup order is
[`ATTENDED-INPUT-AUDIO-BATCH.md`](ATTENDED-INPUT-AUDIO-BATCH.md).
