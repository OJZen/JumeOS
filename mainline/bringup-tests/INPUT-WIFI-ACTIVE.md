# R46H input and Wi-Fi active gates

`r46h-input-wifi-active` contains two deliberately separate, bounded gates for
the canonical Debian 13 p2 image and
`6.12.99-r46h-mainline-v0.8-bootloader-handoff` kernel. Run only one mode at a
time and do not run display, audio, Hantro, suspend, rumble or USB tests during
the same window.

Both modes fail closed unless the process is root on an interactive TTY, the
script is a root-owned, single-link, mode-0700 regular file at its fixed `/run`
path, `/run` is root-owned tmpfs, and the board, root filesystem, kernel,
firstboot marker, ext4 counter and failed-unit state all match the canonical
target. Evidence and the exclusive lock exist only under `/run`. A passing run
removes them before the one final `R46H_INPUT_WIFI_ACTIVE` marker; if verified
cleanup cannot complete, the run preserves the evidence and reports
`cleanup=fail`. `INT`, `TERM` and `HUP` are forwarded to the bounded worker
process group and result in failure.

## Transfer and pin

On the Mac, verify and encode the reviewed script. The checked-in v0.1 script
hash is pinned below; stop if the local file differs.

```bash
reviewed='ad050bd768e7b3ec6f112037330b00ebe24a2a71249d014ad132af9b58bdd993'
actual=$(/usr/bin/shasum -a 256 mainline/bringup-tests/r46h-input-wifi-active)
actual=${actual%% *}
test "$actual" = "$reviewed"
/usr/bin/gzip -9 -c mainline/bringup-tests/r46h-input-wifi-active \
  | /usr/bin/base64 | /usr/bin/tr -d '\n'
```

On the target, disable shell history before pasting the single base64 line:

```bash
unset HISTFILE
set +o history
umask 077
printf '%s' '<single-line-base64>' | base64 -d | gzip -d \
  > /dev/shm/r46h-input-wifi-active.incoming
expected='ad050bd768e7b3ec6f112037330b00ebe24a2a71249d014ad132af9b58bdd993'
printf '%s  %s\n' "$expected" /dev/shm/r46h-input-wifi-active.incoming \
  | sha256sum -c -
sudo install -o root -g root -m 0700 \
  /dev/shm/r46h-input-wifi-active.incoming /run/r46h-input-wifi-active
printf '%s  %s\n' "$expected" /run/r46h-input-wifi-active \
  | sudo sha256sum -c -
```

The target copy is intentionally ephemeral. Do not install it into the root
filesystem merely to preserve a receipt; the UART log is the durable evidence.

## Passive Wi-Fi scan

```bash
sudo /bin/bash /run/r46h-input-wifi-active --wifi-scan
status=$?
printf 'R46H_ACTIVE_COMMAND mode=wifi-scan status=%d\n' "$status"
test "$status" -eq 0
```

This mode accepts only the boot service's `source=usb-serial` stable-MAC
receipt, confirms the live Realtek `0bda:8179`/`rtl8xxxu` identity and runs the
exact bounded operation `iw dev <interface> scan passive`. It never accepts
credentials, associates, changes link/rfkill state or invokes NetworkManager
configuration. The interface must be unassociated before the scan and remain
unassociated afterward. A successful command with zero BSS entries is still a
failed gate. Association, DHCP, reconnect and throughput remain later,
separate tests.

## Input capture

Have an operator ready before starting. During the 60-second window:

1. Start with every button released and both sticks physically centered.
2. Press and release every D-pad, face, shoulder, trigger, stick-click,
   Select, Start, F5 and volume control exactly as labelled on the unit.
3. Move each stick to all four edges/corners, make a full circle, then release
   it and leave it centered.
4. Do not press Power or Reset.

```bash
sudo /bin/bash /run/r46h-input-wifi-active --input-capture
status=$?
printf 'R46H_ACTIVE_COMMAND mode=input-capture status=%d\n' "$status"
test "$status" -eq 0
```

Devices are found by the exact kernel names `adc-joystick`, `gpio-keys` and
`gpio-keys-vol`; event numbers are never assumed and `evtest --grab` is never
used. Passing requires press and release observations for all 19 expected key
codes, every key released at the end, at least 70 percent of each advertised
axis range with both endpoints approached, all four axes returned to the
starting neutral value within 10 percent of the advertised range (with the
starting value itself inside the central 70-percent band), and zero
`SYN_DROPPED` events. Missing operator actions are a normal, auditable failure
and must not be relabelled as kernel success.

For either mode, accept only a final marker with `result=pass`, `failures=0`,
`cleanup=pass`, `reason=checks-complete`, followed by a zero command status.
Any timeout, signal, ext4 change, new relevant kernel fault, failed systemd unit
or incomplete cleanup invalidates the run.
