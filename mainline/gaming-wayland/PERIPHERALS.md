# USB keyboard, mouse and Jume Terminal

2026-09-22: **ARM64 HOST INPUT/PTY PASS; PHYSICAL USB HOTPLUG OPEN**.
This is USB **host** input, not the deferred USB gamepad gadget feature. The
kernel fragment already enables USB HID/evdev and the accepted port has bounded
USB storage evidence. No kernel, DT, USB role or device permissions are changed.

## Behavior

- Connect a USB keyboard/mouse or receiver to the data/OTG port using the
  appropriate adapter; a hub can provide both devices. Hardware enumeration,
  hub power and reconnect behavior still need one attended R46H check.
- Weston/libinput owns hotplug, layout and native pointer input. New/restored
  seat capabilities reapply focus to the foreground application. No extra evdev
  grab or competing USB input daemon is installed.
- Launcher: arrows/Enter/Escape, existing shortcuts, pointer clicks and scrolling.
  Ctrl/Alt/Meta combinations are not mistaken for unmodified launcher shortcuts.
  Read-only HUDs pass pointer events through; the quick panel takes input only
  when explicitly opened. In-game key bindings remain the game's responsibility.
- Browser: native pointer/scroll/text entry; moving the mouse hides the software
  stick cursor. A fresh stick/button action restores it from the last position.
  Ctrl+L/T/W, Ctrl+R/F5 and Alt+Left/Right provide common browser shortcuts.
- **终端 / Jume Terminal** appears in the full application grid. Foot 1.21.0 runs
  an interactive login Bash in the desktop user's home, never as root. `exit`
  or Ctrl+D returns to Jume; Ctrl+C interrupts a foreground command.
  Mouse selection, scrolling, Ctrl+Shift+C/V, colors and bracketed paste use
  Foot's existing implementation. There is no new terminal emulator or shell parser.
- L3+R3 still opens the launcher panel. Terminal and browser contents remain
  sensitive even behind that panel: remote screenshots/input injection are refused.
  Terminal output is not copied into launcher logs; Bash's normal user history
  still applies. Commands have the ordinary desktop user's filesystem permissions.

## Packaging and checks

`prepare-peripherals.py ABSOLUTE_CACHE [--check]` fetches or verifies exact
Debian package sizes/SHA-256. `build-handheld.sh` uses the external cache
`r46h-peripherals/`, then assembles offline with `install-peripherals.sh`.
Only Foot, its extra libraries, terminfo, DMZ-White cursors, an explicit monospace
font and licenses are added. No Foot server or systemd service is installed.
The existing runtime supplies the rest of the ELF closure; target preflight
must resolve it. The terminal clears the launcher's private Qt/Mesa/font settings
before starting Bash, while preserving the real home and Wayland session.

Focused checks: `shell-check terminalEntryKeyboardMouseAndPrivacy`,
`browser-check physicalMouseAndStickHandover`, and `test-peripherals.py`.
The latter runs only as a non-root user in an isolated ARM64 SDK with Xvfb,
Weston X11, `xdotool`, the compiled `test-client`/`handheld-shell.so` and assembled
`/out/terminal-runtime`. It exercises real Wayland keyboard/mouse delivery to
a PTY, Ctrl+C, pointer pass-through under a visible HUD and clean terminal exit.
Neither synthetic input nor nested X11 proves physical USB enumeration/hotplug.
Evidence: `mainline/out/.cache/r46h-peripherals-20260922/RESULTS.md`.
The terminal currently expects a physical keyboard; a controller keyboard and
Chinese IME for Foot are not implemented by this compositor.

Deploy a matching launcher/compositor/runtime candidate, not one executable.
Keep ES-DE available. One attended batch should cover insertion before/after
startup, unplug/replug, pointer visibility/scroll, text and Ctrl shortcuts,
terminal commands/exit, game/panel focus and the volume HUD.
