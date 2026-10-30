# Jume boot image

An optional r11 overlay covers the tty1 login screen while the sealed desktop
performs its approximately 45-second verification/preparation. It renders the
existing Jume mark, UI palette and Noto Sans SC text “正在准备桌面，请稍候”. This
is a static waiting image, not a measured percentage and not a startup-speed fix.
The initial bootloader/kernel interval is outside its scope; serial diagnostics
remain available. It does not alter BOOT, the sealed release or ES-DE recovery.

## Files and lifecycle

- `BootSplash.qml` is the artwork source, using the existing UI theme.
- `boot-splash.bgra.gz` is its 1024×768, 32-bit BGRA framebuffer raster.
- `boot-splash.py` reuses the exact framebuffer mode/write helpers from
  `../scripts/r46h-display-diagnostic.py`, copied beside it at installation.
- `70-jume-boot-splash-getty.conf` delays tty1 agetty while the splash owns it.
- `jume-boot-splash.service` is pulled by `70-boot-splash.conf`. It is optional
  (`Wants`, not `Requires`) and runs only when Jume is the configured default.

The root-owned files live under `/var/lib/jume-launcher/boot-splash/`, with the
unit under `/etc/systemd/system/` and drop-ins under `jume-launcher.service.d/`
and `getty@tty1.service.d/`. The serial getty is unchanged.
The helper authenticates the current r11 recovery helper/installer and fixed
card/kernel/rootfs before display access. It accepts only the verified
rockchipdrmfb 1024×768 XR24 layout. It refuses an existing graphics owner and
skips an already active desktop on tty2.

On tty1 it records ownership in the private systemd RuntimeDirectory, enters
KD_GRAPHICS with VT_PROCESS, writes and reads back the exact raster, then signals READY.
VT_PROCESS acknowledges openvt's release signal without blocking the VT change;
KD_GRAPHICS with VT_AUTO would instead hold the switch until timeout. The ABI is
the [Linux 6.12 VT interface](https://raw.githubusercontent.com/torvalds/linux/v6.12/include/uapi/linux/vt.h). Only
then may the desktop preparation proceed. When the frontend switches to tty2,
it restores tty1 without changing the active VT, then queues tty1 agetty again.
The ownership-marker condition prevents agetty's TTYReset from erasing the image
after READY; Before=getty alone was insufficient and failed operator review.
SIGTERM/errors/145-second
expiry restore the console; ExecStopPost also restores a matching receipt after
a forced exit. The unit has a 5-second startup bound and 150-second runtime bound.
A splash failure does not block Jume or change its existing ES-DE fallback.

## Build and validation

Render `BootSplash.qml` through the existing Qt 6.8.2 host SDK using software
rendering at 1024×768, with the verified Regular/Medium/Bold Noto Sans SC fonts.
The task evidence contains the exact `render.qml` wrapper and inspected PNG.
Convert with the installed ImageMagick `magick input.png -depth 8 BGRA:output.bgra`;
require exactly 3145728 bytes, then gzip with `mtime=0`. The waiting image uses
Theme's light palette; no Qt process or font renderer runs during device boot.

Run `PYTHONDONTWRITEBYTECODE=1 python3 -B mainline/tests/test-jume-boot-splash.py`
and `mainline/tests/test-r46h-display-diagnostic.py`. They cover fixed-format
image bounds, avoiding a running frontend, readback mismatch/write failure,
bounded wait, VT handoff and foreign-receipt refusal. These are host checks.

Before deployment, reopen serial and identify the actual R46H; verify the full
six-file archive hash and regular-file allowlist. Install root-owned files,
refusing an existing foreign directory/unit/drop-in; run `systemd-analyze --man=no verify` (the minimal image omits manual pages)
and reload. Keep the current Jume/ES-DE selection unchanged. Test skip on the
running desktop, then one supervised boot with UART, framebuffer readback and
operator observation. Keep an independent bounded poweroff backstop while testing.

Removal: stop `jume-boot-splash.service` first and verify tty1 restoration; remove
only the byte-matching launcher/getty drop-ins, unit and three installed payload
files, then daemon-reload. Do not disable Jume or delete the ES-DE fallback.
Before changing the pinned r11 recovery helper/release, remove or revalidate this
overlay too; its hashes deliberately reject an unreviewed successor.

## Device evidence

Evidence: `mainline/out/.cache/jume-boot-splash-20261030.mHWHqc/`.

The first five-file candidate wrote/read back the image but failed operator
review: agetty reset tty1 about two seconds later and displayed its login prompt.
That candidate is rejected as visual proof. Delaying agetty made the image visible,
confirmed by the operator and a separate 63.65-second read of KD_GRAPHICS, all
3145728 image bytes and the active fbcon DRM plane. That second candidate exposed
a separate handoff bug: KD_GRAPHICS with VT_AUTO blocked openvt until the
145-second safety timeout. It is rejected for startup latency/terminal flash.

The final VT_PROCESS helper acknowledges the release request. On the final boot,
the image appeared at 13.414 s, acknowledged handoff at 60.535 s, switched to tty2
and restored tty1 at 60.571 s, and restored tty1 agetty at 61.973 s. Jume started
without fallback; the extended timeout wait is gone. Exact hashes, health/state
retention and the operator's final appearance response belong in session.md and
final-receipt.json. No extra Qt, kernel or sealed-release build was needed.

At the user's request, this batch stops here and is committed without another
visual iteration. The operator accepted the visible splash and eventual Home;
final flash-free handoff is **not** accepted. tty2 still contains seatd/Weston
startup text; journal redirection was not deployed and is not included here.
Follow that specific issue when resumed, preserving the installed exit/power
semantics. Task staging/timer were removed, all 177 state files matched, health
and failed-unit/kernel checks passed, and UART confirmed final clean poweroff
at about 22:43 CST. Serial is closed; Jume default and ES-DE recovery remain.
