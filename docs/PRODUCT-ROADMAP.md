# R46H product roadmap

Updated 2026-09-26. This owns the feature backlog and completion criteria.
[Project Context](PROJECT-CONTEXT.md) owns the immediate order and current device
state; the [ledger](../mainline/board/r46h/EXPERIMENT-STATUS.md) owns physical proof.
P0 closes the first usable gameplay flows. P1 builds the product around them.
P2 depends on additional runtime or hardware evidence. No row implies acceptance.

| ID / priority | Deliverable | Completion gate |
| --- | --- | --- |
| M1 / P0 | Moonlight real stream and input | R46H controls the [host test page](../mainline/gaming-stream-input-test/README.md) through Moonlight/Sunshine; both sticks, buttons and triggers reach the host, and its visible response streams back |
| M2 / P0 | Reliable host/application management | Fix empty application-list results, preserve manual entry, validate errors/cancellation and reconnect; persist pairing/host/preset state across ordinary restarts without repeated PIN entry |
| G1 / P0 | Metal Slug in the custom desktop | Reuse accepted FBNeo/ROM/BIOS; home/library card launches gameplay, coin/start/actions work, exit/crash returns correctly and a second launch succeeds |
| G2 / P0 | Common game lifecycle and saves | Literal validated argv, per-game runtime/environment, one foreground owner, isolated writable saves/config/logs, native and supported quick-save/load checks, recovery without lost saves |
| U1 / P0 | Responsive desktop | Diagnose focus frame pacing, land the narrower HUD and check 90–130% fonts in light and night themes; measure real frame intervals under navigation/input, targeting 60 Hz without treating idle submissions as FPS |
| W1 / P1 | Fullscreen Wayland desktop | Remove diagnostic window decoration through the selected shell/fullscreen policy; run actual Moonlight and local games with correct Hantro/GL presentation and A/V |
| W2 / P1 | Global quick panel and input ownership | Explicit stacking; opening takes game input, closing sends neutral/release and restores it; crash/disconnect cannot leave held buttons or a lost display |
| R1 / P1 | Remote operation across games | Composed-output capture plus current surface/focus state; guarded actions, private-entry refusal and fresh-session checks; actual game input stays distinct from Qt actions |
| H1 / P1 | Complete performance display | Toggle CPU, available/total RAM, chip temperature, frequency/cooling, GPU and swap/zram metrics; attach real game/stream FPS/frame-time/drop/audio producers and measure overlay cost |
| P1 / P1 | PortMaster integration | [Local import first](../mainline/gaming-ports/README.md), then reuse HarbourMaster for catalog/install/update/remove/runtime management; progress/errors/cancellation and preservation of user data |
| P2 / P1 | Stardew Valley migration | Reuse original compatibility data and saves, validate Mono/loader/graphics/input and writable paths, then start/load/save/exit/relaunch; compare the newer experimental port separately |
| P3 / P1 | GTA III and Vice City migration | Reuse original classic assets, audit re3/reVC and libraries, adapt controls/audio/paths; verify gameplay, saving and desktop return per game |
| P4 / P2 | GTA San Andreas Chinese migration | Separate loader/library/data/translation audit for the found gtasa/libGTASA.so package; do not infer compatibility from GTA III/VC |
| I1 / early feasibility, then P2 | [USB gamepad mode](../mainline/gaming-usb-gamepad/README.md) | Prove an externally reachable peripheral/UDC path and safe VBUS roles first; then standard HID reports, neutral on exit/unplug, and restoration of normal USB/Wi-Fi operation |
| S1 / P1 | Network and basic settings | Wi-Fi authorization, password privacy, connect/disconnect/remember/forget and recovery; add audio-output operations only after detecting actual capabilities |
| S2 / P1 | CPU and memory profiles | Retain accepted CPU controls; ship the fixed 256 MiB LZ4 zram policy only after the product artifact and rollback-safe persistent boot pass; keep disk swap manual |
| S3 / P1 | Power management | Retain real dim/wake and supervised reboot/poweroff; measure charging/battery reporting and low-voltage policy, then design bounded suspend/wake recovery |
| B1 / P1 | [Jume Browser](../mainline/gaming-browser/README.md) | Dual-stick scrolling/cursor, B/Y/A/X, tabs/address/IME; maintained Chromium security baseline, sandbox, Panfrost composition/WebGL and separately measured video decode; memory/thermal and foreground recovery on device |
| F1 / P1 | [Files, previews and Text](../mainline/gaming-files/README.md) | Responsive large directories; copy/cut/paste/delete, ZIP, partitions/USB; safe cancellation, preserved originals, supported previews and editing on device |
| F2 / P1 | [Wi-Fi Transfer](../mainline/gaming-files/TRANSFER.md) | Phone QR/link upload/download, bounded long transfers, background retention and disconnect revocation without data loss |
| T1 / P1 | [Background tasks](../mainline/gaming-shell/APPLICATIONS.md) | Fast previews and isolated input; resume, normal close and physical long-hold kill; retained game/save/transfer/audio state |
| Q1 / P1→P2 | Product installation and endurance | Make Jume Launcher the persistent default after settings/pairing/saves, bounded logs/caches, repeated launches and sustained gameplay pass; remove ES-DE only after cold-boot, crash recovery and upgrade/rollback no longer depend on it |

## Evidence owners

Use [current feature evidence](PROJECT-CONTEXT.md#current-feature-evidence) and
the [physical ledger](../mainline/board/r46h/EXPERIMENT-STATUS.md), not a second
dated snapshot here. The [combined route](../mainline/gaming-shell/DEVICE.md#combined-acceptance-route)
separates automated preparation from the remaining operator observations and
does not repeat accepted media, sequential USB, wake or task-entry checks.
Browser isolation has bounded target OOM/recovery proof; zram has target refusal checks.
Both remain source candidates, without persistent product promotion.

## Delivery constraints

[Project Context](PROJECT-CONTEXT.md#immediate-next-work) owns the current order.
Keep Moonlight paused until the user resumes it; keep SA and every save generation
isolated. USB work still requires connector-routing evidence before a separate
recoverable kernel/DT candidate. Batch only changed-path attended checks, and do
not remove ES-DE before recovery and save-retention gates pass.

Sunshine stays a manually started test tool with isolated state and no host
service registration. Windows is optional if the Linux-on-Mac path cannot satisfy
LAN/input requirements. USB HID and Moonlight network input remain separate gates.
