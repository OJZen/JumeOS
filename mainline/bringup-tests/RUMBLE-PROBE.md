# R46H bounded rumble probe

`r46h-rumble-probe.c` is an attended physical-output gate for the separate
mainline `pwm-vibrator` input device. It does not touch the ADC joystick or
button event nodes. It uploads one standard Linux `FF_RUMBLE` effect at fixed
50% magnitude for 750 ms, starts it once, waits for its bounded replay window,
then explicitly stops and removes the effect before closing the event FD.

This probe is not a silent automated PASS. A successful process proves the
evdev/force-feedback control path and cleanup, but the final hardware result
also requires a person holding the R46H to report a felt vibration. Keep the
device in hand while running it. Do not increase the magnitude or duration to
compensate for a missing physical response; investigate the PWM, motor and
power path instead.

The probe fails closed unless the provided non-symlink character device and
its opened FD retain the same inode and `st_rdev`, and report all of these:

- input name `pwm-vibrator`;
- `BUS_HOST` with the exact zero vendor/product/version identity observed on
  this platform device;
- `EV_FF` and `FF_RUMBLE` capabilities;
- at least one force-feedback effect slot.

It installs handlers for `HUP`, `INT` and `TERM`. Every path after a successful
start attempts a stop event, a short stop-settle interval, `EVIOCRMFF` and FD
close. The kernel replay length is also bounded, and closing the FD invokes the
driver's stop path. An outer timeout remains mandatory.

## Build and ephemeral transfer

The accepted source SHA-256 is
`c7490cc5f9f647383c25559d8a312d98e4edd9ad01c954ffc5d4038aa21e06f9`.
The accepted ARM64 binary was built with warnings as errors inside the existing
external-cache builder:

```bash
cache="$PWD/mainline/out/.cache/r46h-rumble-probe-build"
mkdir -p "$cache"
docker run --rm --user 501:20 \
  -v "$PWD/mainline/bringup-tests:/src:ro" \
  -v "$cache:/out" -w /out --entrypoint /bin/bash \
  arkos4clone/r46h-kernel-builder:trixie-arm64 \
  -lc 'gcc -std=c11 -O2 -Wall -Wextra -Werror \
    -o r46h-rumble-probe /src/r46h-rumble-probe.c'
```

Its SHA-256 is
`99a01fb6996e785d0a0745f990ca3b07c1dc68a346d44790b745ae35f181e34b`.
Transfer and re-hash only that binary under `/run/user/1000`; do not install it
into p2. Discover the unique event node from `/sys/class/input/event*/device/name`
instead of assuming that it will always remain `event0`.

With the operator holding the device, retain dmesg, ext4 error-count and failed
unit baselines, then run exactly one bounded process:

```bash
timeout -s TERM -k 1s 5s \
  /run/user/1000/r46h-rumble-probe /dev/input/event0
status=$?
printf 'R46H_RUMBLE_COMMAND_EXIT status=%d\n' "$status"
```

PASS requires all of the following:

- exact `R46H_RUMBLE_IDENTITY` and `R46H_RUMBLE_STARTED` markers;
- one final `R46H_RUMBLE result=pass ... cleanup=pass` and exit status 0;
- an empty bounded dmesg delta, unchanged zero ext4 error counter and zero
  failed units;
- an explicit operator statement that the vibration was felt;
- deletion of the transferred binary and health scratch from target tmpfs.

## Accepted 2026-08-15 result

The accepted binary ran twice on
`6.12.99-r46h-mainline-v0.8-bootloader-handoff`. Both runs reported 16 effect
slots, uploaded effect ID 0, ran the fixed 750 ms / 32,768-magnitude effect,
exited 0 and completed cleanup. The second repeat was explicitly felt by the
operator. Both bounded dmesg deltas were empty; ext4 stayed `0 -> 0`; failed
units stayed `0 -> 0`; final target-tmpfs residue was zero.

The durable serial receipt is
`mainline/out/r46h-serial-logs/v08-rumble-20260815.bin`, 8,733 bytes, SHA-256
`3321f0cb76f7aca236e70424a97b2cbe17217fbfd0c10d494959ac42d3c117ac`.

This closes direct physical motor actuation through mainline `pwm-vibrator`.
It does not prove game/emulator force-feedback routing, magnitude linearity,
long-duration thermal behavior, suspend interaction or any direction control.
Do not repeat the direct hardware pulse without a driver, DTS, motor/power or
userspace-routing change.
