# Jume Browser

Chromium-based handheld browser using Qt WebEngine and Jume Launcher's Qt
controls, virtual keyboard and foreground manager. **Optional development
preview**, not an accepted system browser. No default-desktop or service change.

## Interface and controls

Chrome-style tabs and address/search bar stay visible above the page. Up to three
tabs, back/forward/reload, zoom, GPU diagnostics, About and Exit are available. Inactive
pages freeze only when Chromium recommends it; form state is not deliberately
discarded. HTTP cache is capped at 32 MiB. Cookies/profile storage are private and
persistent; there is no password sync or session-tab restore. Blank tabs are local.

Chromium's compositor tile budget is set to 128 MiB for shared-memory R46H graphics
using its native `--force-gpu-mem-available-mb` switch. This is **not** a total
browser/GPU-memory limit: JavaScript, decoded resources and other allocations
remain separate. Hardware acceleration and the renderer sandbox stay enabled.
See the [Chromium implementation](https://github.com/chromium/chromium/blob/134.0.6998.208/third_party/blink/renderer/platform/widget/compositing/layer_tree_settings.cc)
and [Qt lifecycle guidance](https://doc.qt.io/qt-6.10/qml-qtwebengine-webengineview.html#recommendedState-prop).

| Physical control | Browsing | Virtual keyboard |
| --- | --- | --- |
| Left stick | Scroll under cursor, including nested areas | Navigate keys |
| Right stick | Move visible cursor | No pointer input |
| B (south) | Left click; hold to drag/select | Select key |
| Y (west) | Back | Dismiss |
| A (east) | Forward | No navigation |
| X (north) | Reload | Backspace |
| Start | Focus/select address bar | Submit |
| Select | Show keyboard for focused editor | Dismiss |
| L1 / R1 | Previous / next tab | No tab switching |
| D-pad | — | Navigate keys |
| L3 + R3 | Existing launcher quick panel | Existing launcher quick panel |

Positions follow the accepted routed-pad mapping, not Xbox labels. Focus loss
releases clicks and requires neutral before resuming. The 18% dead zone and
quadratic response reduce drift. `--pointer-speed` (240–1400 px/s) and
`--scroll-speed` (200–1800 px/s) retain hardware calibration. No global mouse
injection, `/dev/uinput` access or compositor policy change is added.

## Build and integration

Run `mainline/gaming-browser/build.sh`. It uses the pinned ARM64 SDK and retained
shell Qt bundle, installs Debian WebEngine dependencies in a disposable container,
then builds offline. Checksums, dependency receipts, source snapshot and optional
`jume-browser-arm64.tar.gz` go to ignored `mainline/out/.cache/jume-browser/` on the
external disk. No host package installation or Chromium source build is needed.
WebEngine is pinned to Debian trixie-backports `6.10.2+dfsg-3~bpo13+1`; the
launcher and base Qt remain 6.8.2. A missing pinned package fails the build rather
than silently selecting another engine. Only the disposable builder enables
backports, never the host or R46H system.

Both browser About and Launcher Settings → About show WebEngine, Chromium and
the Chromium security-patch baseline separately. Browser values come from the
loaded library; packaging queries that same executable with `--engine-versions`
to generate `engine-versions.json` for the launcher, without loading WebEngine
into the launcher process. Missing runtime/metadata shows unknown, not a guessed
version. Upgrade binaries and their generated metadata together.

For a **transient** shared-desktop candidate, extract this archive into
`browser/` beside the candidate's `usr/`, not over its Qt libraries. Rebuild the
launcher integration too. Its new card checks the fixed wrapper, reports missing
runtime and uses the existing foreground manager/routed pad. The launcher supplies
private `state/browser`, owns the child process group and restores the desktop
on exit. Keep the accepted shared bundle as fallback. Never overwrite browser
state when upgrading/rolling back binaries. The shared client selects built-in
cards when the browser wrapper exists, even without a native-ports lease.
Packaging requires a traversable archive root and explicitly includes XComposite,
XDamage and Xtst; availability in the builder is not target dependency proof.

## Graphics and security gates

Qt Quick uses OpenGL; the wrapper retains the session's Mesa/Panfrost EGL/GBM/DRI
selection and uses Wayland. Qt WebEngine negotiates Chromium's interoperable GPU
backend. No GPU-blocklist override, forced Vulkan, single-process mode, disabled
GPU sandbox or certificate bypass is shipped. Follow
[Qt's graphics guidance](https://doc.qt.io/qt-6.8/qtwebengine-features.html#hardware-acceleration),
then inspect `chrome://gpu` on the exact device. Configured OpenGL is not proof of
accelerated composition/WebGL, and neither proves Hantro video decode. Check
`chrome://media-internals` with a known clip before claiming video offload.

The preview rejects root and inherited sandbox/debug overrides. Kernel namespaces
and seccomp must work; failure is a blocker, not permission to add `--no-sandbox`.
URLs are limited to HTTP(S), blank and three diagnostic pages. Local files,
external protocols and URL-embedded credentials are rejected. Certificates fail
closed. Downloads, uploads and website device permissions are explicitly
unavailable pending safe confirmation UIs. Remote composed capture is refused
throughout browsing, including the keyboard and quick panel.

**Security gate remains open:** the upgraded engine reports WebEngine **6.10.2**,
Chromium **134.0.6998.208**, security patches through **144.0.7559.96**, replacing
6.8.2 / Chromium 122 / patches through 132. These are the actual library's values,
consistent with [Qt's version record](https://wiki.qt.io/QtWebEngine/ChromiumVersions).
Backported security fixes do not add all newer Chromium features. This available
[Debian backport](https://packages.debian.org/trixie-backports/qt6-webengine-dev)
still trails upstream; it is not a claim of current security coverage. Keep this
preview to controlled pages, not sensitive accounts. Review security advisories
and a current maintained engine before ordinary Internet use or promotion;
host sandbox proof alone does not close target sandbox or GPU gates.

## Verification

2026-09-21: ARM64 build and `browser-check` passed (4 QtTest results). Launcher
entry/privacy, foreground lifecycle and routed-input checks passed (6 results).
The relocated runtime passed offline Wayland rendering, native B click/left-stick
scroll, address and page-field IME, tabs and renderer sandbox. Evidence is in
`mainline/out/.cache/jume-browser/`; those host checks alone make no GPU claim.
The 6.10.2 upgrade repeats those checks through the actual launch wrapper, verifies
About versions and Y dismissal, and passes six launcher QtTest results including
About's absent/present metadata. A relocated launcher capture also reads the
actual packaged metadata. `RESULTS.md` owns exact artifact hashes and logs.

`browser-check` covers actions, click release, repeat suppression, dead zone,
bounded time steps, wheel delivery, keyboard remapping and URL policy. Launcher
`shell-check browserEntryAndPrivacy` checks runtime gating and capture privacy;
existing foreground-lifecycle/routed-input checks cover shared ownership.

`check-renderer.sh` runs the relocated bundle under unprivileged Weston in an
ARM64 container with `weston`, `xvfb` and `xdotool` installed. Xvfb supplies Weston's
keyboard seat; the browser still uses Wayland. Give this test container
`--security-opt seccomp=unconfined` so Chromium can create its own namespaces;
the renderer must still report `NoNewPrivs=1` and `Seccomp=2`. An offline,
off-the-record fixture checks actual Chromium rendering/click/scroll, keyboard,
tabs and sandbox. The fixture retries its idempotent native click until Chromium's
first hit-test frame is ready; all checks remain watchdog-bounded.
Host software Mesa is **not R46H GPU proof**.

2026-09-21 transient v0.18 device checks passed: Qt OpenGL and WebGL 2 used
Mali-G31 MC1/Panfrost (Mesa 26.2.2); blue-pixel readback matched with no GL error.
Offline click/scroll, address/page IME, tabs, About and renderer sandbox passed.
Normal launch, cancel/confirm exit, relaunch and private-capture blocking passed;
bounded expiry restored ES-DE and services with no matching kernel/storage/OOM
faults. Renderer checks await asynchronous results under a watchdog instead of
assuming host timing. These synthetic inputs do not prove physical controls.
The component-verified overlay is not a full latest-archive target readback.
Exact scope and receipts: `mainline/out/.cache/r46h-browser-device-20260921/RESULTS.md`.

Subsequent attended mi.com product-page navigation is **FAIL**. The page initially
responded, then stalled during operation. First run: compositor ownership/privacy
validation ended the session at 22:07, with no matched OOM record; its exact cause
remains open. Protocol-only rejection diagnostics preserve all security checks.
Second run at 22:18:53: kernel global OOM killed Chromium renderer PID 5355;
systemd's `DefaultOOMPolicy=stop` then stopped the shared desktop unit. Peak cgroup
memory was 799.2 MiB, system RAM 933 MiB, and no swap was active. ES-DE recovered.
No health abort or normal expiry. This confirms memory exhaustion for the second
exit, not the first policy rejection or a memory leak. Browser OOM isolation and
swap/zram validation remain necessary before repeating heavy-page operator acceptance.
Evidence: `mainline/out/.cache/r46h-browser-attended-20260921/`.

Follow-up memory experiment: an identical offline layered/scrolling fixture with
the default tile budget reached 118.5 MiB available RAM and was stopped early by
the **test harness** (128 MiB threshold), before OOM. A 64 MiB tile budget finished
but reported missing-tile warnings, so was rejected. The selected 128 MiB budget
finished all 120 scroll steps with no such warnings, minimum sampled available
RAM 298.6 MiB and peak temperature 83.846 C. This is one bounded synthetic
comparison, not a mi.com reproduction, whole-browser memory cap or smoothness
acceptance. Following Qt's recommendation down to automatic background discard
passed on the host but failed the device's edited-form retention check; that
change was withdrawn and the original freeze-only policy retained.
The selected freeze-only/128 MiB build passed target native input/IME/tabs/About,
Panfrost WebGL 2 blue-pixel readback and renderer sandbox again. ES-DE/services
recovered with no new matched kernel faults; device was cleanly powered off.
No swap, clocks or kernel were changed. Exact candidate, failed
attempts and checks: `mainline/out/.cache/r46h-browser-memory-20260921/RESULTS.md`.

Next device batch: physical stick precision, long-page scrolling and L3+R3 while
dragging/typing; controlled video decode, sustained memory/thermals, forced-crash
recovery and persistent cookies. Human acceptance covers LCD smoothness,
readability and audio. Keep the accepted desktop and security gate unchanged.
