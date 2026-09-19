# Performance, settings and power

This owns the incremental feature plan for the [Qt shell](DEVICE-SHELL.md).
The [shell runbook](../mainline/gaming-shell/README.md) owns host commands and
evidence. R17 passed temporary CPU/backlight changes and supervised power actions;
the [device record](../mainline/gaming-shell/DEVICE.md) owns that scope. Persistent
settings installation and zram promotion remain open; the isolated zram boot and
guarded apply/disable gate now pass.

## First host version

The quick panel toggles a local performance HUD. It measures this process's
CPU time (one core = 100%), resident memory and Qt frame submissions each
second. It retains at most 60 CPU samples in memory. Turning it off, minimizing
the window or dimming the preview stops sampling and clears old samples.
The submission rate includes HUD repaints and can approach zero on a static
page; it is not game FPS, LCD refresh rate or GPU render time. A horizontal panel
above the content retains the history graph. It becomes compact during text entry
or quick-panel use and stays clear of the active field, keys and controls.
The [remote recorder](REMOTE-CONTROL.md#bounded-metric-recording) now exports
bounded numeric JSON/CSV, retaining partial samples after transport/session loss.
It neither captures frames nor turns sampling on automatically.
The shared Wayland HUD also shows actual game buffer submissions and recent
submission intervals. Its [producer contract](../mainline/gaming-wayland/HANDHELD.md#game-frame-metrics)
distinguishes these from LCD presentation, GPU duration and video/audio drops.
R31 displayed these values over Neo/Ozone on the device. Its game/panel snapshots
included capture and control traffic, so they do not isolate normal overlay cost.
The [device record](../mainline/gaming-wayland/HANDHELD.md#r31-device-follow-up-2026-09-11)
owns the values, thermal abort and remaining gates.
The [native streaming adapter](../mainline/gaming-shell/STREAMING.md#native-statistics)
adds Moonlight's own video rates, drop counters and queue/timing data. Host checks
cover the protocol and UI path; actual stream values and overlay cost remain open.

Settings provide categories for network/Wi-Fi, Bluetooth, controller testing,
sound, display, storage, system information, battery/power, font/input, CPU
frequency and memory/swap. Real host reads are labelled as the current runtime
or preview volume. On identified R46H, the [device adapter](../mainline/gaming-shell/DEVICE.md)
reads actual state; ordinary previews disable writes. An explicit temporary lease
enables backlight/CPU changes and supervised power requests. Volume remains on
the accepted physical keys. Host sliders still affect only preview values.
Font size, reduced motion and the HUD affect the UI. The dual-stick page shows actual SDL
axes, triggers and buttons without recalibration. In test mode controls are
observed; Select returns directly to the settings sidebar (Q on a PC). A/B remain test
inputs while that page is active.
Settings enter through the category list; the footer explains the current mode
and value-adjustment controls. The [shell navigation contract](../mainline/gaming-shell/README.md#run-on-this-mac)
owns exact keys and save-failure behavior. Unavailable rows remain readable and
visually distinct from working controls.
Font size and idle timing now use the [shared choice list](../mainline/gaming-shell/controls/README.md):
preview with Up/Down, confirm with A, cancel with B. CPU choices and saved Wi-Fi
reuse the same control. A minimal target polkit candidate passed saved-profile
control and reconnect, but new-password entry and image integration remain open.
Bluetooth pairing is blocked by absent controller/firmware and BlueZ.

Idle dimming offers off/30/60/120 seconds. The host preview uses a visual mask;
the leased target adapter changes actual backlight and restores its saved value.
Interaction wakes it, and an initial wake key does not activate a card.
The simulated session, text entry and controller tester inhibit dimming.
R17 passed actual brightness/dim/wake and restore, attended GUI reboot and
agent-tested GUI poweroff; [Device settings](../mainline/gaming-shell/DEVICE.md)
owns evidence. Suspend, low-battery policy and broader power limits remain open.

The optional Linux Qt Virtual Keyboard uses one application `InputPanel`,
English and simplified-Chinese layouts, and Qt's built-in arrow navigation.
SDL directions/A send local navigation key events to the focused input field;
Y deletes and START confirms, while B/Select cancels. Horizontal keyboard moves
wrap within their current row. Packaged Qt checks and R17 attended input acceptance
passed; the device record owns the exact result. The test field is limited to 128 characters and cleared
on exit. macOS uses the existing input method/physical keyboard. Shared Wayland
input-method ownership is a later compositor task. Qt documents the module as
commercial/GPLv3; its license files and corresponding source archive are kept
with the experiment. [Integration](https://doc.qt.io/qt-6.8/qtvirtualkeyboard-deployment-guide.html),
[navigation build option](https://doc.qt.io/qt-6.8/qtvirtualkeyboard-build.html),
[module and license](https://doc.qt.io/qt-6.8/qtvirtualkeyboard-index.html).

## CPU presets and custom limits

The retained v0.15 build config enables CPUFreq/DT and default schedutil;
performance, userspace and ondemand are built in, powersave/conservative modular.
The 2026-09-07 serial sample exposed policy0 at 600/816/1008/1200/1296 MHz,
using schedutil with 600–1296 MHz limits. Available governors were ondemand,
userspace, performance and schedutil; powersave was absent. No policy was changed.
The sample had no active swap. Python was absent, so host-side validation used
serial sysfs/proc reads; three preset drafts passed and powersave was rejected.
Read each `policy*` afresh before offering or applying values. Session evidence
is linked from the [shell runbook](../mainline/gaming-shell/README.md#prepare-an-attended-device-run).

The host draft checker supports restoring the sampled original governor/limits,
balanced (schedutil), powersave and performance. Presets preserve the sampled
frequency limits. Custom limits must be integers in kHz, ordered, within the
hardware range and, when exported, selected from the available-frequency table.
An unavailable governor is rejected, not silently substituted or loaded.
Revision 14 implements these rules with fixed-path writes, readback, rollback and
original-state restoration at the end of a temporary probe. No voltage changes,
overclocking or per-game profiles are offered. R17 passed GUI
1296 → 1200 → 1296 MHz limits with serial readback and restoration.
[Linux CPUFreq policy interface](https://docs.kernel.org/admin-guide/pm/cpufreq.html).

The user-approved persistent default selects the nearest supported 1 GHz OPP:
`schedutil` with a 600--1008 MHz CPU range. It leaves GPU devfreq and thermal
protection unchanged. Host fixtures cover supported-OPP validation, write order
and readback. The current v0.17 device passed dynamic residency, GTA/thermal use
and a warm reboot with the oneshot enabled; the frozen v0.18 image is unchanged,
so the next p2 integration remains open.

## Compressed memory and disk swap

The retained v0.15 config has `CONFIG_SWAP=y`, **ZRAM and ZSWAP disabled**.
An optional [zram candidate fragment](../mainline/config/r46h-zram-candidate.fragment)
selects a modular zram device, LZ4 and Zstd, initially LZ4, without disk writeback
or zswap. A clean isolated branch now builds the v0.18 candidate Image/modules;
its package hashes passed. The accepted main-branch kernel fragment is unchanged.
The [candidate contract](../mainline/gaming-shell/DEVICE.md#memory-experiment-cli)
owns source/provenance and the passing one-shot boot/module gate. Retain the v0.17 DTB.

zram stores compressed pages in RAM. A disk swap file consumes storage and I/O;
zswap is a compressed cache in front of backing swap, not a synonym for zram.
The implementation treats zram and disk swap independently,
with disk swap off by default and no automatic zswap-on-zram layering.
[zram](https://docs.kernel.org/admin-guide/blockdev/zram.html),
[zswap](https://docs.kernel.org/admin-guide/mm/zswap.html).

The host draft checker still performs no writes. The guarded memory CLI
checks device/storage identity, file ownership, available-space reserve, algorithms
and sizes before apply. Active-file resize is refused; disable checks the RAM
needed to reclaim used swap. On the isolated kernel, 256 MiB LZ4 zram reached
43.5 MiB swap use under bounded pressure, then disabled, reset and unloaded
cleanly. The accepted v0.15 boot and unchanged media files were restored. GUI or
startup activation waits for measurable real-workload benefit; memory/swap/pressure
readout is implemented.

## Next implementation order

1. R54 measured the GTA III menu under identical 1008 MHz CPU / 400 MHz GPU
   caps: 26.84 game submissions/s with the full-screen transparent HUD and
   30.43/s with it hidden. R56's native view mask now confines the HUD to the
   top-right on R46H, but seven HUD-hidden intro samples averaged only 5.57/s
   with 121.24--226.62 ms median intervals. Its three HUD-on samples came from a
   different intro phase and are not a matched comparison. R57 keeps fast requested
   stops but gives a self-triggered bound five seconds for renderer cleanup. Two
   R46H GTA III bounds then exited 0 without a forced kill. Similar roughly
   59-second HUD-on intro windows averaged 5.59 submissions/s at 1024x768 and
   12.32/s at a temporary 640x480. The lower-resolution run started hot, reached
   85.384 C with CPU/GPU cooling active and still produced two Panfrost runtime
   faults, so it is not yet a product default. With R58's GTA-only no-AFBC setting,
   the first two-run boot and a later mixed-game boot logged zero Panfrost data/GPU
   faults. The later run matched the visual phases: at 1008/400 MHz GTA III fell
   from 28.66 submissions/s in its menu to 3.17/s in the car cutscene, and Vice City
   fell from 27.70/s to 4.17/s in its intro. P95 intervals reached 313.48/247.58 ms
   without thermal cooling. This confirms a phase-specific rendering stall, not a
   menu-wide cap or a fault-driven exit. A host audit of the exact Release/`MASTER`
   sources found no explicit readback or `glFinish` in the normal frame path;
   ordinary streaming is asynchronous and the optional renderer paths are off.
   The captures instead retain distinct 4.41/8.96-second transition gaps followed
   by sustained 3--4/s intro submissions. Run one cooled, same-build
   1024x768/640x480 A/B with transition and settled-cutscene windows separated;
   keep `noafbc` as the fault fallback and retain the HUD-independent sampler.
   The user-set external abort remains 85 C, not a kernel thermal-trip change.
   A cooled R58 follow-up completed that A/B. At 640x480 with temporary 1008/400
   MHz caps, Vice City reached 14.53--19.67/s and GTA III reached 10.75--23.00/s
   in observed intro phases; the latter touched the 85 C abort. Reducing only the
   temporary caps to 816/300 MHz kept GTA III/Vice City 20-second intro windows
   at 15.24/14.46/s averages, 76.538/77.692 C maxima and zero cooling state. Both
   121-second bounds exited 0 without forced kills. A 512x384 request was not a
   supported video mode. The implementation therefore seeds 640x480 only for a
   first managed GTA config and preserves later preferences; no speculative engine
   patch or per-game frequency framework was added. Physical LCD quality and a
   product frequency policy remain separate gates. R59's 1,727-file host package
   and exact target preflight passed; a fresh target state generated the expected
   640x480 GTA III config and reached game submissions before a clean exit.
   A same-boot 816/300 MHz driver A/B then isolated a software-side gain. A private
   Mesa 26.2.2 EGL/GBM/Gallium closure raised GTA III from 11.00 to 14.36 and
   Vice City from 14.67 to 17.15 submissions/s at 640x480. Both candidate runs
   exited 0 below 81 C without cooling or a new Panfrost fault; the original-Mesa
   GTA III control added one `DATA_INVALID_FAULT`. A Gallium-only trial failed at
   the frontend ABI boundary, so R60 packages the complete private closure and
   leaves Debian's system Mesa unchanged. Clean source `495c35232176f0c6ca39a93fd6ab4ac1f02e70bd`
   produced the 1,741-file R60 package; host checks, target preflight and actual
   Mesa 26 process maps passed. GTA III reached a captured intro and its 121.15-second
   bound at exit 0 without a new fault. A later attended Vice City batch compared
   816/300, 1008/400 and 1296/480 MHz: the stock maximum reached the 85 C guard while
   its median submission rate was only 19.52/s versus 18.67/s at 816/300. Disabling
   the frame limiter reduced the median to 17.24/s. Profiling found render-thread
   Panfrost BO waits and repeated immediate-buffer map/unmap activity, but sizing
   each allocation to the current draw also regressed to 17.60/s and was reverted.
   R63's fixed-capacity upload reuse now passes the machine gate. A same-boot
   follow-up held CPU at dynamic 600--1008 MHz and compared Vice City at GPU
   480/400/300 MHz: matched 30-second medians were 23.08/22.91/22.46 submissions/s.
   Cutting GPU clock 37.5% cost only 2.7%, and the governor sometimes dropped to
   200 MHz during the cutscene, so raw GPU throughput is not the primary limit.
   GTA III also completed its 121-second R63 bound at exit 0. Investigate the
   phase-specific driver/engine submission path; keep R60 until attended R63
   reacceptance and avoid unsupported GPU OPPs.
   The two-second health sampler warns near voltage/thermal limits and blocks
   unsafe CPU adjustment. Automatic low-battery shutdown, calibrated percentage,
   charge completion and suspend/resume remain open; supply alone is not net
   charging.
2. Package `polkitd` and the proven three-action ark-only NetworkManager rule in a
   future image, then verify new-password AddAndActivateConnection2 and reboot
   persistence. The installed hardware-key service already owns RK817 volume;
   add no second writer unless the product explicitly needs a slider. Bluetooth
   waits for controller/firmware evidence before BlueZ or pairing work.
3. The isolated zram boot, bounded pressure and apply/disable gate pass. Promote
   no startup or GUI policy until a real game demonstrates a measurable benefit.
4. The HUD now reads system CPU, available RAM, temperature and current GPU MHz;
   settings show policies, swap/zram, GPU frequency and PSI where available.
   R32 measured HUD-on UI CPU near 8.6% of one core and panel-open near 24.1%
   during the short run. Actual streaming, GPU time and audio-device metrics
   remain separate producer/acceptance work.

The R32 global HUD shares compositor ownership and routed input with games.
Keep its machine proof separate from attended LCD/audio/physical-control evidence.
