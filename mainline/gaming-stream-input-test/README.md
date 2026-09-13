# Real streaming controller test

Status: **LINUX PROTOCOL LOOPBACK PASS / R46H INPUT ACCEPTANCE OPEN**.
The user accepts this milestone: R46H buttons/sticks → Moonlight → Sunshine's
virtual gamepad → a host test program → the response streamed back to the LCD.

## Temporary Linux host on the current Mac

`run-linux-host.sh` runs the pinned Sunshine ARM64 package in the existing Docker
VM, without installing a Mac service or input driver. It captures only a private
640×480 Xvfb test window and a quiet 440 Hz tone from a private PulseAudio sink.
The test window changes from green to blue with A; the left stick moves a white
square. Every observed button and the ranges of all six axes are recorded.
This exercises Linux virtual input, not native macOS gamepad emulation.

Run in an **independent macOS Terminal**, with a freshly identified Mac IPv4
address on the handheld's LAN:

```sh
bash mainline/gaming-stream-input-test/run-linux-host.sh CURRENT_MAC_IPV4 900
```

The address must be assigned locally. The launcher publishes only Sunshine's
stream/pairing ports on that address, not its web administration port. Select
application `Loopback` on R46H, initially at 640×480 / 30 FPS / 3 Mbps. When
pairing is requested, enter the handheld PIN at the hidden Terminal prompt.
Noninteractive pairing is refused. No PIN, keys or certificates enter retained
logs. Each launch has fresh pairing state; timeout or Ctrl+C removes it and the
container. Duration is 10–1800 seconds; the default is 900. Cleanup records input
observations even on interruption. Pair again after restarting this disposable host.

The retained prerequisites live under external `mainline/out/.cache/`:

- `r46h-stream-loopback/`: Sunshine `v2026.516.143833` ARM64 Debian package,
  `sunshine-source.json`, dependency debs and `dependency-sha256.txt`.
- `r46h-ports-backend-20260910/game-debs/`: the existing native test dependencies.
- `r46h-compositor-20260910/r28/`: hash-checked desktop/client runtime.

The scripts pin the SDK image, Sunshine package and R28 archive, verify package
and runtime manifests, and fail if the required closure is missing. Extra
packages are installed only inside the disposable container; service startup is
suppressed. Every launch creates a separate `host.*` evidence directory in the
external cache. Keep its observation JSON; empty input is not an acceptance pass.

## Automated protocol check

`check-loopback.sh` is the container-only runner; no arguments select its bounded
self-test, `--serve SECONDS` selects the temporary host. Mount this tool directory,
`gaming-wayland` and `gaming-ports` under `/project/mainline/`, writable results at
`/out`, the prerequisite directory at `/fixtures` with
`R46H_LOOPBACK_FIXTURES=/fixtures`, native test debs at `/existing-debs`, and R28's
archive at `/candidate.tar.gz`. Use the same pinned SDK and two device cgroup
rules as `run-linux-host.sh`; the self-test can use `--network none`.

The self-test pairs the actual v5 Moonlight client, fetches the actual application
list, streams H.264, checks native video statistics and decodes the known tone.
A synthetic R46H source sends 14 buttons, two triggers and four signed axes;
Sunshine's separate Xbox controller must receive each press, release and center.
The host test explicitly ignores the synthetic source. Client-side green/blue
captures prove the response returned through video. Individual shoulders remain
usable; L1 + R1 exits the native client.

The retained `r46h-stream-loopback/verified/` result passes these checks. A separate
`server-smoke.json` proves the published HTTP endpoint from Mac loopback and
15-second automatic cleanup. The receipt records exact source and evidence.
Neither check proves LAN traversal, R46H hardware decoding, physical controls,
LCD presentation, audible output, or native Mac gamepad support.

The container lacks udev, so its test process uses SDL's evdev directory watcher;
PCM capture keeps SDL's sample-derived timing. These are test-environment choices,
not changes to R46H input or audio policy. See the upstream
[Linux joystick backend](https://raw.githubusercontent.com/libsdl-org/SDL/SDL2/src/joystick/linux/SDL_sysjoystick.c)
and [disk audio backend](https://raw.githubusercontent.com/libsdl-org/SDL/SDL2/src/audio/disk/SDL_diskaudio.c).

## Attended procedure

1. Start the chosen temporary host, pair and connect. Move both sticks through
   all directions and back to center; press buttons and triggers separately.
   Check A/color and left-stick motion on the handheld, then inspect the numeric
   host record for the other controls. A host-side injected fixture is not physical proof.
2. Test L1 and R1 separately, then L1 + R1 to exit. Confirm return and reconnect.
   With the shared desktop, separately check L3 + R3 opens the global panel,
   suppresses game input and resumes with neutral controls.
3. Record operator LCD/audio observations separately from button/axis samples;
   stop the temporary host and perform the target runbook's health/poweroff steps.

## Windows fallback page

`index.html` remains a single local Edge/Chrome page for a Windows Sunshine host.
Verify host/driver access before setup and keep Sunshine manually started. It
shows raw controls, uses left stick/D-pad for a square, right stick for a cursor,
and A for color; disconnect clears input and device selection resets its record.
It has no dependencies or network requests. Use a trusted localhost context if
browser Gamepad API permissions require it. Browser/Windows acceptance is open.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B mainline/gaming-stream-input-test/check.py
```

That check covers pure movement and Node DOM/canvas fixtures, not browser rendering
or streaming. Neither program establishes commercial-game compatibility, rumble
or end-to-end latency.
