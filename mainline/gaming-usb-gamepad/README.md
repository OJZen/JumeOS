# R46H USB gamepad feasibility

Status 2026-09-13: **CONFIGURATION HOST IMPLEMENTED / CURRENT TARGET HOST-ONLY / PERIPHERAL ROUTE UNPROVEN**.
This is separate from sending controller events through Moonlight over the network.
No kernel, device tree, USB role or VBUS configuration has been changed.

## What is known

The [accepted USB probe](../bringup-tests/USB-STORAGE-READ-PROBE.md) found the
external connector at DWC2 → internal hub → Port 2, with RTL8188EU Wi-Fi on Port 3.
The other connector is documented as USB-DC power/detection, not a second Host.
Neither fact proves an accessible peripheral data connection on this board.

R41 confirmed the current v0.17/v0.15 target at runtime without changing USB state:
`/sys/class/udc`, configfs `usb_gadget/` and `/sys/class/usb_role` were empty;
the live DT reported `usb@ff300000/dr_mode=host`; the kernel exposed only
`CONFIG_USB_DWC2_HOST=y`; and `lsusb -t` showed DWC2 → hub → RTL8188EU Wi-Fi.
Evidence is
`mainline/out/.cache/r46h-r40-ports-batch-device-20260913.XEe7qy/session.json`.
This closes software-only gadget testing on the current image, not the board-routing question.

The current [kernel fragment](../config/r46h.fragment) selects USB_DWC2_HOST and
disables PERIPHERAL/DUAL_ROLE; the [device tree](../board/r46h/rk3326-r46h.dts)
sets usb20_otg to host. The regulator named otg_switch is not evidence of a USB
data-line mux. Do not infer routing from that name or from SoC capabilities.

Linux [configfs gadgets](https://docs.kernel.org/usb/gadget_configfs.html) require
a USB Device Controller and binding to it. A [HID gadget](https://docs.kernel.org/6.5/usb/gadget_hid.html)
can expose gamepad reports through /dev/hidgX. Enabling those options alone does
not prove that a PC can reach this device through an external connector.

## Offline configuration

The independent [Qt USB page](../gaming-shell/TOOLS.md) saves mapping preferences
and exports a test profile while actual output remains disabled. The shared
encoder in `gaming-shell/usbgamepad.cpp` prepares report ID 1 with 16 buttons,
D-pad hat (neutral 8), four signed 16-bit axes and two unsigned 8-bit triggers.
The 14-byte layout uses little-endian fields, normalized deadzone rescaling and
neutral output for conflicting D-pad directions. Host checks cover extremes,
swaps, inversion, neutral and malformed/non-finite input. This is descriptor/report
preparation, not PC recognition or kernel gadget support.

## Ordered gates

1. Next, trace D+/D−, ID and VBUS roles using original board evidence and, if needed,
   an attended electrical/connector check. A downstream hub port is not proof of
   an upstream device route. Establish a safe data connection before any role test.
2. If wiring permits it, prepare a separate DWC2 device/dual-role + configfs/HID
   candidate with the accepted boot fallback. Use UART because changing this
   shared controller may disconnect the internal Wi-Fi/hub. Observe actual UDC
   binding and PC enumeration before implementing the full mode.
3. First software scope: standard USB HID gamepad, buttons, D-pad, two sticks and
   triggers. Feed the existing normalized controller state; validate report ranges,
   combinations and neutral/release on startup, exit and disconnect.
4. Add an explicit settings mode and exit path. Prevent simultaneous unintended
   local-game and USB input; restore the normal Host/hub/Wi-Fi state on exit/failure.
5. Verify host recognition, every physical control, unplug/replug and restoration.
   XInput-specific compatibility, rumble/output reports and composite USB networking
   are later extensions, not promises of the initial generic HID implementation.

If there is no usable peripheral route, stop the software-only approach and
record that hardware boundary. Do not silently assume a different connector,
board modification or extra controller exists. USB/normal/Wi-Fi restoration and
VBUS behavior must be part of acceptance, not just descriptor enumeration.
