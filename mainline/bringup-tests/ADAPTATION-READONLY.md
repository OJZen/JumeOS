# R46H Debian 13 read-only adaptation audit

> Retained v0.2 execution contract for the exact v0.8/Debian p2 MVP. It remains
> testable reference material, not the current boot gate. Check
> [Project Context](../../docs/PROJECT-CONTEXT.md) and the
> [ledger](../board/r46h/EXPERIMENT-STATUS.md) before target use.

The audit is separate from the rootfs image so diagnostic changes do not require
rewriting the 10.7 GB p2 image. It performs non-mutating enumeration before any
active Panfrost workload.

## Scope

| Group | Required evidence | Explicitly excluded |
| --- | --- | --- |
| Storage | exact root, p1/p3 unmounted, ext4 counter, MMC layout | repair or mounting p1/p3 |
| DRM | Rockchip/Panfrost nodes, DSI/mode/fb geometry, query-only `modetest` | modeset, page flip or framebuffer write |
| Input | expected devices, key/ABS capabilities and udev data | event grab, calibration or rumble |
| Audio | RK817 playback/capture/mixer enumeration | mixer change, playback or recording |
| Power | RK817 battery/charger attributes and plausible voltage | charge control or trusted capacity |
| Thermal/performance | sysfs limits, stock CPU/GPU OPPs and bounded current values | governor, voltage or stress changes |
| Media | Hantro nodes, encoder/decoder identity and modules | streaming or format validation |
| USB/Wi-Fi | RTL8188EU identity, stable MAC, driver and query state | scan, association or rfkill change |
| Modules/post-audit | exact vermagic, loaded state, unchanged ext4/fault state | module load/unload |

Temporary files and the lock live only under verified `/run` tmpfs. Query
ioctls are used by DRM, ALSA and netlink tools, so the accurate claim is
non-mutating enumeration, not that every device opens with `O_RDONLY`.
Checks execute serially to keep failures attributable.

## Exact historical precondition

Do not use this audit to decide whether newly written media is safe. For the
retained v0.8 contract, the Card Agent status had to be
`WRITE_COMPLETE`/`safe_to_boot=yes`, a separately reopened p2 hash had to
match, p1 had to remain unchanged, and BOOT anchors had to select v0.8. UART then
had to show the 1,500,000-to-115,200 handoff, exact kernel, Debian login and the
expected first-boot marker.

These identities describe the historical fixture only. They do not authorize a
write or describe the current card.

## Transfer and run

On the host, confirm the committed script and create one compressed base64 line:

```bash
/usr/bin/shasum -a 256 mainline/bringup-tests/r46h-adaptation-readonly
/usr/bin/gzip -9 -c mainline/bringup-tests/r46h-adaptation-readonly \
  | /usr/bin/base64 | /usr/bin/tr -d '\n'
```

At the target, disable interactive history before pasting the payload:

```bash
unset HISTFILE
set +o history
umask 077
set -o pipefail
printf '%s' '<single-line-base64>' | base64 -d | gzip -d \
  > /dev/shm/r46h-adaptation-readonly.incoming
```

Install the exact file in root-owned tmpfs and run it:

```bash
sudo install -o root -g root -m 0700 \
  /dev/shm/r46h-adaptation-readonly.incoming \
  /run/r46h-adaptation-readonly
printf '%s  %s\n' '2ff45792f9029f6f89ff544b9293e5780aba932544fbf13aef77e6d0adcc6bc9' \
  /run/r46h-adaptation-readonly | sudo sha256sum -c -
sudo /bin/bash /run/r46h-adaptation-readonly --readonly
audit_status=$?
printf 'R46H_ADAPT_COMMAND_EXIT status=%d\n' "$audit_status"
test "$audit_status" -eq 0
```

## Acceptance

The final two markers must be:

```text
R46H_ADAPT_AUDIT id=r46h-adaptation-readonly-v0.2 mode=readonly result=pass failures=0 skips=<n> skip_names=<allowed-set> cleanup=pass reason=checks-complete worker_timeout=160s output_timeout=15s
R46H_ADAPT_COMMAND_EXIT status=0
```

`skip_names` must be exactly `none`, `audio:capture-enumeration`,
`modules:exfat-loaded`, or both in that order. Any other skip, failed check,
timeout, changed ext4 counter, wrapped dmesg ring, fault marker or incomplete
cleanup fails the audit.

Only after this exact audit passed did the historical sequence run the active
Panfrost baseline:

```bash
sudo /usr/local/sbin/r46h-rootfs-smoke --base
```

The serial logger is the durable receipt. The target copy is ephemeral and
shell history stays disabled, so do not install the script to p2 merely to
preserve it. Active display, input, audio, Wi-Fi, media, USB and gaming gates
remain separate runbooks indexed by [README.md](README.md).
