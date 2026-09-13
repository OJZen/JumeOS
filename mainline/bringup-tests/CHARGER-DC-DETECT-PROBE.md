# R46H USB-DC / RK817 detection probe

This gate diagnoses one narrow mismatch: the R46H board has a dedicated
USB-DC input whose presence signal is wired to GPIO0_B3, while the current
mainline RK817 charger driver reports only the RK817 PMIC's internal plug
state. It does not change charger registers, charge current, charge voltage,
regulators, storage or filesystems.

## Source evidence

The tracked vendor DTB
`consoles/r46h/rk3326-r46h-linux.dtb` is 93,698 bytes with SHA-256
`ff42fbf07d9455b483f2e21eef074a7b2bcb13eb3ca2cba7c40b1193d6c79af8`.
Its previously preserved decompilation has SHA-256
`bbeb6c89dc67d6f89515fb93d0aa054e6aa1aa26483d08177aef5931ae750517`
and gives the charger both:

```dts
dc_det_gpio = <&gpio0 11 GPIO_ACTIVE_HIGH>;
extcon = <&u2phy>;
```

Offset 11 of `gpio0` is GPIO0_B3. Rockchip's pinned `develop-4.4` source at
commit
[`9ead5f3cbd6e0abd0ac70002205993c953c227ea`](https://github.com/rockchip-linux/kernel/tree/9ead5f3cbd6e0abd0ac70002205993c953c227ea)
contains `drivers/power/rk817_charger.c` with SHA-256
`d6ee5763f8e2063bc7dca24be4d35e480f3b6c1098e21f5dfaa5ecf59f70e2c4`.
That driver requests `dc_det_gpio` as an input, treats its declared active
level as `DC_TYPE_DC_CHARGER`, and reports it independently through `dc_in`.

The canonical Linux 6.12.99 tarball has SHA-256
`6a477222c132033381cda981eb0127f29fbcbba17e820283bc21290f8e408629`.
Its `drivers/power/supply/rk817_charger.c` has SHA-256
`eb06785415e3a49cbbbd472c79958ed06bef8cd62eb72c368ecfc691f6389b6b`.
It initializes `plugged_in` only from `RK817_SYS_STS.RK817_PLUG_IN_STS` and
then updates it through the RK817 plug-in/plug-out IRQs. Its DT binding permits
neither `dc-det-gpios` nor the old `dc_det_gpio`, so merely adding a property to
the board DTS would be rejected and ignored. A driver and binding change is
required if the board signal is confirmed.

## Accepted pre-probe observation

The 2026-08-15 serial capture
`mainline/out/r46h-serial-logs/v08-charger-diagnosis-20260815.bin` is 10,271
bytes with SHA-256
`8600e076cc676f3c4350c992bf6644287290cf567ead94e8ba54ff4bbc3e172a`.
On exact v0.8 it recorded:

- charger `online=0`, `voltage_avg=0`, `usb_type=Unknown [DCP]`;
- battery `status=Discharging`, `capacity=95`, `voltage_avg=4067190` and
  `current_avg=-65188`;
- both `rk817_plug_in` and `rk817_plug_out` IRQ counters at zero;
- a live charger DT node containing only the upstream monitored-battery and
  calibration properties, with `dc-det-gpios`, `dc_det_gpio` and `extcon`
  absent;
- ext4 error count zero and zero failed systemd units.

At this pre-probe stage the evidence proved the software mismatch but not the
live level or polarity of GPIO0_B3. The accepted result below closes that
question; this paragraph preserves the order in which the evidence was
obtained.

## Exact probe and safety boundary

Build `r46h-charger-observe.c` in the pinned ARM64 builder. The accepted source
SHA-256 is
`937428e1393da7e9ec2b984f0dc27e818b68f2d6b9c315fb7874382d9a698e04`;
the resulting 72,192-byte ARM64 binary SHA-256 is
`6368e7936c1e4f06626d96b9b1e4b0231568912a9c44205a95a0d19d77087ef3`.
Transfer it only to `/run/user/1000/r46h-charger-observe`; do not install it
into p2.

The probe:

- pins the exact v0.8 release, R46H model/compatible and current charger DT
  shape;
- opens the exact `/dev/gpiochip0` character device with `O_RDONLY`,
  `O_NOFOLLOW` and path/FD identity checks;
- refuses an already-owned GPIO0_B3 line;
- requests only `GPIO_V2_LINE_FLAG_INPUT`, applies no bias and samples the
  line five times over 80 ms;
- drives no GPIO output and performs no block, filesystem, PMIC-register,
  regulator or power-supply write;
- closes the line request before publishing its result.

Requesting an input line can transiently select GPIO input mode. It is
non-driving and mirrors the vendor driver's direction, but it is not a claim
of literally zero hardware configuration. The request disappears when the
process exits.

## Operator sequence

One disconnect/reconnect cycle is sufficient. Keep CH340 GND/TX/RX connected;
do not move the TF card or the external USB Host device.

1. With USB-DC power disconnected, capture ext4 errors, failed units, the
   relevant dmesg baseline and `/proc/interrupts`, then run:

   ```sh
   sudo /run/user/1000/r46h-charger-observe --expect-disconnected
   ```

2. Connect known-good USB-DC power, wait at least three seconds without
   touching the Host connector, then run:

   ```sh
   sudo /run/user/1000/r46h-charger-observe --expect-connected-mismatch
   ```

3. Capture the same health evidence again, remove the tmpfs probe and shut down
   normally if no further attended test follows.

The diagnostic passes only if the disconnected phase is stable low and the
connected phase is stable high while mainline remains `online=0`, input voltage
remains zero and battery status remains `Discharging`. That result proves the
board-level detection gap; it does not prove that charging current is safe or
that adding the GPIO alone will make charging work.

Only after both phases pass should a new kernel candidate add an optional,
canonical `dc-det-gpios` binding and use it as an additional online source.
That candidate must keep the PMIC IRQ path, configure no charge limits beyond
the existing reviewed values, and separately validate connect, disconnect,
current direction, voltage, dmesg, ext4 and shutdown behavior.

## Accepted 2026-08-15 result

Both phases passed on exact v0.8. With USB-DC connected, five samples were
stable high while the charger still reported `online=0`, `voltage_avg=0` and
the battery reported `Discharging`. After the operator removed only USB-DC,
five samples were stable low while those mainline attributes remained offline.
The RK817 plug-in and plug-out IRQ counters stayed at zero in both phases.

The bounded health checks ended with ext4 error count zero, no failed systemd
units and no new charger/GPIO/MMC/ext4 fault. The tmpfs probe was deleted. The
13,889-byte serial receipt is
`mainline/out/r46h-serial-logs/v08-charger-gpio-observe-20260815.bin`, SHA-256
`25c456133b764edda47a4df44bdb2fc051320d548b180cc5a7ab2f1c75541a01`.
After USB-DC removal, a normal shutdown reached read-only root, all filesystems
unmounted and `Powering off`; its 9,120-byte receipt is
`mainline/out/r46h-serial-logs/v08-charger-shutdown-20260815.bin`, SHA-256
`5a0a7f0286c284b73fa67048ea750415bc64e3f653d1fef47b02622112fc7896`.

This closes the board-signal hypothesis: active-high GPIO0_B3 accurately tracks
USB-DC, and the current upstream driver does not consume it. Do not repeat the
observation on v0.8. The next experiment is a single-variable kernel candidate
that adds the canonical optional GPIO binding and combines that input with the
existing PMIC plug state. Charging current, charge limits and unattended
charging remain unproved until that candidate is separately reviewed and
tested.
