# R46H media and USB query preflight

`r46h-media-usb-preflight` is a bounded, query-only gate for the canonical
Debian 13 p2 image and the
`6.12.99-r46h-mainline-v0.8-bootloader-handoff` kernel. It does not stream,
encode, decode, hotplug, mount, write a device, load a module or change USB
authorization.

The media check discovers the two V4L2 nodes by their exact Hantro sysfs names
and discovers `/dev/media*` character devices through `/sys/dev/char`. This is
necessary on the R46H kernel, which exposes `/dev/media0` without a
`/sys/class/media` directory. The USB check records inventories at the start
and end and requires both the device list and mount table snapshots to match.

## Transfer and pin

On the Mac, stop if the reviewed hash does not match:

```bash
reviewed='144bfcc158a04946156cba86b4e407ce9f68b8b42c1976c9d1d06c4ede16f898'
actual=$(/usr/bin/shasum -a 256 mainline/bringup-tests/r46h-media-usb-preflight)
actual=${actual%% *}
test "$actual" = "$reviewed"
/usr/bin/gzip -9 -c mainline/bringup-tests/r46h-media-usb-preflight \
  | /usr/bin/base64 | /usr/bin/tr -d '\n'
```

On the target, disable shell history, verify the decoded file, and install it
only into root-owned `/run`:

```bash
unset HISTFILE
set +o history
umask 077
printf '%s' '<single-line-base64>' | base64 -d | gzip -d \
  > /dev/shm/r46h-media-usb-preflight.incoming
expected='144bfcc158a04946156cba86b4e407ce9f68b8b42c1976c9d1d06c4ede16f898'
printf '%s  %s\n' "$expected" /dev/shm/r46h-media-usb-preflight.incoming \
  | sha256sum -c -
sudo install -o root -g root -m 0700 \
  /dev/shm/r46h-media-usb-preflight.incoming /run/r46h-media-usb-preflight
printf '%s  %s\n' "$expected" /run/r46h-media-usb-preflight \
  | sudo sha256sum -c -
```

Run the preflight and retain the nonzero skip status instead of hiding it:

```bash
sudo /bin/bash /run/r46h-media-usb-preflight --query-only
status=$?
printf 'R46H_MEDIA_USB_COMMAND_EXIT status=%d\n' "$status"
```

The current Debian 13 v0.1 image does not contain `v4l2-ctl`, FFmpeg or
GStreamer. Its expected honest result is therefore:

```text
R46H_MEDIA_USB_GATE id=r46h-media-usb-preflight-v0.1 mode=query-only result=skip media=SKIP_TOOLING usb=PASS post=PASS cleanup=pass reason=media-tooling-unavailable worker_status=0
R46H_MEDIA_USB_COMMAND_EXIT status=77
```

`media=SKIP_TOOLING` means the Hantro encoder, decoder and media nodes were
identified but no codec capability or data path was validated. `usb=PASS`
means only that the sysfs/`lsusb` inventory, built-in Realtek identity and
mount baseline were stable. It is not evidence that the external USB Host
connector supplies power, handles hotplug, or transfers data. Those require a
separate operator-present gate with a known USB device and end-to-end hashes.

This paragraph describes the historical query-only run. The later
single-frame Hantro JPEG encoder data-path gate passed on 2026-08-15 and is
documented in [`HANTRO-JPEG-PROBE.md`](HANTRO-JPEG-PROBE.md). Decoder and
sustained-streaming coverage remain open. A later attended gate also proved
hotplug and repeated bounded raw reads through the board's single external USB
Host connector; see
[`USB-STORAGE-READ-PROBE.md`](USB-STORAGE-READ-PROBE.md). The query-only result
itself remains inventory evidence and must not be relabelled.

Any `result=fail`, unexpected zero status for a skip, ext4 change, failed
systemd unit, dmesg fault, process leak or incomplete cleanup invalidates the
run. The target copy is ephemeral and disappears at shutdown.
