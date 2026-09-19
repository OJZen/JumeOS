# R46H product roadmap

Updated 2026-09-20. This owns the feature backlog and completion criteria.
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
| U1 / P0 | Responsive desktop | Diagnose focus frame pacing, land the narrower HUD and check 100–120% fonts; measure real frame intervals under navigation/input, targeting 60 Hz without treating idle submissions as FPS |
| W1 / P1 | Fullscreen Wayland desktop | Remove diagnostic window decoration through the selected shell/fullscreen policy; run actual Moonlight and local games with correct Hantro/GL presentation and A/V |
| W2 / P1 | Global quick panel and input ownership | Explicit stacking; opening takes game input, closing sends neutral/release and restores it; crash/disconnect cannot leave held buttons or a lost display |
| R1 / P1 | Remote operation across games | Composed-output capture plus current surface/focus state; guarded actions, private-entry refusal and fresh-session checks; actual game input stays distinct from Qt actions |
| H1 / P1 | Complete performance display | Toggle CPU, available/total RAM, chip temperature, frequency/cooling, GPU and swap/zram metrics; attach real game/stream FPS/frame-time/drop/audio producers and measure overlay cost |
| P1 / P1 | PortMaster integration | [Local import first](../mainline/gaming-ports/README.md), then reuse HarbourMaster for catalog/install/update/remove/runtime management; progress/errors/cancellation and preservation of user data |
| P2 / P1 | Stardew Valley migration | Reuse original compatibility data and saves, validate Mono/loader/graphics/input and writable paths, then start/load/save/exit/relaunch; compare the newer experimental port separately |
| P3 / P1 | GTA III and Vice City migration | Reuse original classic assets, audit re3/reVC and libraries, adapt controls/audio/paths; verify gameplay, saving and desktop return per game |
| P4 / P2 | GTA San Andreas Chinese migration | Separate loader/library/data/translation audit for the found gtasa/libGTASA.so package; do not infer compatibility from GTA III/VC |
| I1 / early feasibility, then P2 | [USB gamepad mode](../mainline/gaming-usb-gamepad/README.md) | Prove an externally reachable peripheral/UDC path and safe VBUS roles first; then standard HID reports, neutral on exit/unplug, and restoration of normal USB/Wi-Fi operation |
| S1 / P1 | Network and basic settings | Wi-Fi authorization, password privacy, connect/disconnect/remember/forget and recovery; add Bluetooth/audio-output operations only after detecting actual capabilities |
| S2 / P1 | CPU and memory profiles | Retain accepted CPU controls; exercise guarded disk swap and zram apply/disable/reserve checks with a separate candidate-kernel boot before GUI writes |
| S3 / P1 | Power management | Retain real dim/wake and supervised reboot/poweroff; measure charging/battery reporting and low-voltage policy, then design bounded suspend/wake recovery |
| Q1 / P1→P2 | Product installation and endurance | Make Jume Launcher the persistent default after settings/pairing/saves, bounded logs/caches, repeated launches and sustained gameplay pass; remove ES-DE only after cold-boot, crash recovery and upgrade/rollback no longer depend on it |

## Current evidence by workstream — 2026-09-20

- **M1/M2:** v5 fixes the empty application-list path. Real pairing, listing,
  H.264/PCM, native stats and virtual controller roundtrip passed the isolated
  [Linux host check](../mainline/gaming-stream-input-test/README.md) on this Mac.
  Source input was synthetic; R46H LAN/physical input and shared Hantro streaming
  remain open. The earlier v3 attended A/V/exit/reconnect result stays valid.
- **G1/G2:** R35 retained R33's launch/exit proof, then wrote a persistent slot 0
  state, warm-rebooted and loaded the exact retained hash through Ozone; both save
  and load reached RetroArch's target log. Physical controls and longer gameplay
  remain open.
- **W1/W2/R1/H1:** R32 machine checks passed composed game/panel/HUD images,
  routed input refusal while the panel owns it, B returning input ownership,
  authenticated SSH, and normal/thermal recovery without the old teardown BUG.
  R33's external-stop cleanup passed on device with no manual runtime deletion.
  [The device record](../mainline/gaming-wayland/HANDHELD.md#r35r36-device-follow-up-2026-09-12)
  owns exact evidence and the 85 C limit. Physical L3+R3, LCD/audio, sustained
  performance, precise overlay cost and actual Moonlight remain open.
- **P1–P4:** resource/save management and HarbourMaster lifecycle have host checks.
  R74's accepted GTA III/Vice City engines pin the ring-upload and simple-shadow
  source build; Vice City's short intro passed picture, audio and controls, while
  open-world performance, broader play and saves remain open. Stardew's source,
  managed copy and backup remain hash-equal with overwrite refused, but both
  120-second profiles still stop before SDL/Wayland. GTA III broader physical play
  and Stardew shared-window save/load remain open. The
  separate SA Android-loader/direct-evdev findings do not establish a working port.
- **U1:** shared controls, headers, icons, font/spacing/motion rules and frame
  diagnostics are implemented; R35 displayed actual battery/charge/Wi-Fi status,
  and R32 adds the bounded HUD-independent first-frame
  wait. Use the [control contract](../mainline/gaming-shell/controls/README.md)
  for new tools. R32's three short samples per phase retained about 59.5–60.5 game
  submissions/s; this does not prove LCD 60 Hz or sustained performance.
- **I1:** the independent USB profile page and offline HID encoder/export exist.
  R41 confirmed the current device has Host-only DWC2 and no UDC/gadget/role entry.
  Output stays disabled pending connector routing evidence and a separate kernel/DT candidate.
- **S1/S2/S3/Q1:** the temporary ark-only Wi-Fi policy passed its exact three
  actions and denied unrelated permissions. Its byte-reproducible v0.18 successor
  passes host validation; media deployment, a new password and reboot persistence
  remain open. The isolated zram kernel passed one-shot apply/pressure/disable,
  but promotion waits for measurable game benefit. Bluetooth remains hardware
  blocked; suspend and product installation remain open.

## Delivery constraints

[Project Context](PROJECT-CONTEXT.md#immediate-next-work) owns the current order.
Keep Moonlight paused until the user resumes it; keep SA and every save generation
isolated. USB work still requires connector-routing evidence before a separate
recoverable kernel/DT candidate. Batch only changed-path attended checks, and do
not remove ES-DE before recovery and save-retention gates pass.

Sunshine stays a manually started test tool with isolated state and no host
service registration. Windows is optional if the Linux-on-Mac path cannot satisfy
LAN/input requirements. USB HID and Moonlight network input remain separate gates.
