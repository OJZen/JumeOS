# Jume Launcher

Status: **R36 STATUS/NEO PERSISTENCE/PORTMASTER CATALOG DEVICE PASS; STREAMING DEFERRED**.
The operator selected a custom Switch-inspired desktop, settings and a
Steam Deck-like quick panel. The first device sample is in the shell runbook;
[Project Context](PROJECT-CONTEXT.md) still owns the active hardware checkpoint.
[The shell runbook](../mainline/gaming-shell/README.md) owns commands and checks.

## Selected direction

Use Qt 6 Quick/QML for the interface and small C++ components for state and
controller events. Keep one visual system for cards, settings and quick controls.
The [shared Qt controls](../mainline/gaming-shell/controls/README.md) own primitive
styling, navigation and motion; feature pages reuse them and own their data/actions.
Use the physical 1024×768 aspect ratio, explicit focus, short transitions and
bounded cover sizes. Reuse existing launch, network, audio and input services
through narrow device adapters. The opt-in [temporary settings mode](../mainline/gaming-shell/DEVICE.md)
adds guarded backlight/CPU writes and power requests; ordinary previews remain
read-only on R46H. Its [application list](../mainline/gaming-shell/APPLICATIONS.md)
now launches foreground commands on shared-window platforms. The separate
[Moonlight supervisor](../mainline/gaming-shell/STREAMING.md) exits the desktop
before a direct-display stream, then restarts it. Generic EGLFS launch remains
blocked; the separate Moonlight handoff passed the attended 2026-09-08 session.
Use one accent for active focus, quieter backgrounds for the current page or
category, and context-specific button hints for a controller-first interface.
Logical input must respond immediately; short visual transitions may follow it
and must respect reduced motion. Keep large text, unavailable controls and HUD
placement legible at 100% and 120% font size. Cache stable content; avoid adding
blur or animated page layout to achieve depth.

The host prototype includes home/library/settings, favorite persistence,
keyboard and SDL controller navigation, an interactive session placeholder and
a modal quick panel. The product-facing name is **Jume Launcher**; the internal
`r46h-shell` binary and control-protocol identifier stay stable while existing
deployment and evidence tooling depend on them. Version `0.1.0-dev` and the
project URL are visible under **Settings → About**. Its
[performance, settings and power plan](PERFORMANCE-POWER.md)
owns the local HUD, device-setting categories, keyboard, CPU presets and swap/
compression work. Placeholder content is identified in the UI. The retained
EGLFS preview's panel is local to its process. R36's shared Wayland path separately
composes it over a native game with explicit input ownership and proved guarded
cleanup, persistent Neo reboot-load and PortMaster catalog browsing. Preferences use
atomic writes and failed-save retention; broader product persistence is still a gate.

## Display and input decision

Current ES-DE and Moonlight experiments use direct KMS/DRM output. Qt EGLFS
supports a single fullscreen GL window per screen, without an inter-process
window manager. The proposed product overlay therefore needs a shared display
owner; opening another EGLFS application cannot supply that ownership.
[Qt embedded Linux](https://doc.qt.io/qt-6.8/embedded-linux.html)

The current candidate uses Weston 14 with the project-owned
[handheld shell and input router](../mainline/gaming-wayland/HANDHELD.md).
The retained two-window probe established DRM/Panfrost and attended panel/card
controls. R35 additionally proved actual battery/charge/Wi-Fi status and persistent
Neo slot 0 save/load across warm reboot; R36 showed 1,396 PortMaster entries.
Actual streaming, physical L3+R3, native ports, endurance and performance under load remain
open; ES-DE stays the installed frontend. [Remote Control](REMOTE-CONTROL.md) separates Qt actions,
routed game input and the actual game-frame readiness gate. A generic Qt
always-on-top flag does not replace compositor policy or input ownership.
[Weston runtime](https://wayland.pages.freedesktop.org/weston/toc/running-weston.html)

Moonlight's video renderer is independent of its QML menus. Moving the client
from KMSDRM to Wayland changes its presentation path; hardware frame import,
colors, frame pacing and A/V timing must be rechecked. Retain the accepted
Embedded stream and ES-DE recovery path until that succeeds.

The permanent evdev/uinput bridge currently forwards controls continuously.
Window focus does not stop a game reading its gamepad directly. A product menu
uses the candidate's broker for explicit routing, release/neutral events and
failure recovery; the accepted merged mapping is unchanged. Select opens the
desktop preview panel. The selected in-game shortcut is L3 + R3; its physical
acceptance remains open even though RPC panel ownership passed. L1 + R1 remains
the streaming exit chord.

## Gates

| Gate | Scope and acceptance |
| --- | --- |
| Host UI | Native Mac and ARM64 build; keyboard/controller events; persistence/failure recovery; visual review at 4:3; no idle repaint loop |
| Direct device preview | Receipt-bound tmpfs payload; Panfrost rendering, actual controls, readable LCD, CPU/RSS/frame times, clean frontend return |
| Shared display | Actual Moonlight plus a separate surface on R46H; retain Hantro use, correct colors and A/V; measure overlay hidden/visible costs |
| System integration | Real app launch/exit, supported settings operations, global input isolation, crash recovery and persistent state |
| Product acceptance | Attended gameplay and repeated menu/launch/exit cycles; only then select a replacement frontend |

## ES-DE removal gate

Jume Launcher may become the default frontend after its persistent image install,
cold boot, repeated launch/exit/crash recovery, input ownership and save-retention
gates pass. Keep ES-DE as a recovery entry during that transition. Remove it only
after an endurance and upgrade/rollback cycle proves that Jume Launcher can recover
without ES-DE, plus attended LCD, audio, physical-control and gameplay acceptance.

Use the temporary remote tool to automate Qt navigation and window captures
after its device gate passes. Keep attended LCD/audio/physical-input results
separate; screenshots and software Wayland frames cannot close those gates.

Use the shell's bounded `--profile-ui` comparison to separate static update
counts from continuous animation and keyboard-navigation throughput. The
[runbook](../mainline/gaming-shell/README.md#ui-performance) owns device results.
Compare the same game/stream
with the panel hidden and visible. Target 60 Hz interaction, but set no claimed
R46H CPU/memory/latency budget before measurement. Prefer opacity/transform
animations, lazy views and event-driven work; avoid live full-screen blur.
[Qt Quick performance](https://doc.qt.io/qt-6.8/qtquick-performance.html)

The new [independent tools](../mainline/gaming-shell/TOOLS.md) use the
[shared defaults and UI contract](../mainline/gaming-shell/controls/README.md).
Neo launch/save, PortMaster game runtimes and USB output retain separate device gates.
