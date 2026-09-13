# R46H combined input bridge operations

This package is an inactive, removable userspace candidate for the independent
`6.12.99-r46h-mainline-v0.14-gaming-input-bridge` one-shot kernel. The
repository runbook `mainline/bringup-tests/GAMING-INPUT-BRIDGE.md` is the
authority for reviewed archive hashes and the complete attended-batch contract.
V0.5 keeps the exact v0.3 History paths, RetroArch config, source discovery and
event forwarding. It replaces the rejected v0.4 candidate, which could not
create its diagnostic file under `ProtectSystem=strict`. V0.5 uses one
systemd-managed root-only runtime directory and retains it only long enough for
the trial to compare events read from `gpio-keys` / `adc-joystick`, events
successfully written to uinput, and events captured from the combined virtual
device. Do not stage v0.4.

Stage both the v0.14 p2 one-shot and this bridge while exact persistent v0.10 is
running. Do not install this bridge from v0.14. The installer verifies the
accepted v0.10 gaming state, publishes a static inactive service and does not
write BOOT or the persistent U-Boot environment.

Boot v0.14 once with the one-shot `UBOOT-CMDS.txt`; never use `saveenv`. From an
attended TTY, run `/usr/local/sbin/r46h-input-bridge-trial`. The bounded trial
uses the installed hardware smoke core while a non-grabbing `evtest` reader
checks the virtual controller for all 16 identified game buttons, all four axes,
return to center and zero dropped events. The bridge writes only
`/run/r46h-input-bridge/diagnostics`; the trial validates and removes both that
file and its dedicated tmpfs directory after stopping the service. Key
localization requires exact press, release, repeat and final-value agreement
across all three stages. Axis localization requires sufficient source travel,
matching source/write counts and final values, and corresponding virtual travel,
extrema and final value. During its 60-second window:

1. start with every game button released and both sticks centered;
2. confirm D-pad, A and the left stick visibly affect the smoke screen;
3. press and release A, B, X, Y, L1, R1, L2, R2, Select, Start and each D-pad
   direction, then physically click the left stick cap for L3 and the right
   stick cap for R3;
4. move both sticks through every edge and corner, circle them, then release
   them centered;
5. do not press Power, Reset, volume controls or the unidentified inherited F5
   GPIO.

The trial ends automatically. Accept only its final
`R46H_INPUT_BRIDGE_TRIAL result=machine-pass` marker plus the required operator
screen observation. A failed control also receives one bounded localization:
`physical-source-missing`, `bridge-write-missing`, or
`virtual-delivery-or-capture-missing`. These labels locate an event-pipeline
stage; they do not by themselves diagnose a GPIO or RetroArch cause. A bridge
process failure is terminal; an actual uinput write failure is reported from the
diagnostic header as `bridge-write-missing` before cleanup. After an
ordinary return to exact v0.10, run the installed bridge remover first and the
one-shot remover second.
