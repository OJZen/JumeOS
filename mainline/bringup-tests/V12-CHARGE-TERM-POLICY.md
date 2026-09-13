# R46H v0.12 RK817 charge-termination policy

This candidate fixes one device-tree conversion error while preserving the
effective downstream RK817 register selection. It does not prove that the
battery charges, that its current and temperature are safe, or that unattended
charging is acceptable.

## Fixed source evidence

The vendor R46H DTB is 93,698 bytes with SHA-256
`ff42fbf07d9455b483f2e21eef074a7b2bcb13eb3ca2cba7c40b1193d6c79af8`.
Its preserved decompilation has SHA-256
`bbeb6c89dc67d6f89515fb93d0aa054e6aa1aa26483d08177aef5931ae750517`
and contains:

```dts
charger {
	chrg_term_mode = <0x00>;
	chrg_finish_cur = <0x34>;
};
```

`0x34` is decimal 52. Rockchip's fixed `develop-4.4` source commit
`9ead5f3cbd6e0abd0ac70002205993c953c227ea` has
`drivers/power/rk817_charger.c` SHA-256
`d6ee5763f8e2063bc7dca24be4d35e480f3b6c1098e21f5dfaa5ecf59f70e2c4`.
For analog mode 0, that driver maps every value below 200 mA to
`CHRG_TERM_150MA`. The vendor value 52 therefore selects the 150 mA hardware
setting; it does not describe a supported 52 mA hardware step.

The canonical Linux 6.12.99 tarball has SHA-256
`6a477222c132033381cda981eb0127f29fbcbba17e820283bc21290f8e408629`.
Its `drivers/power/supply/rk817_charger.c` has SHA-256
`eb06785415e3a49cbbbd472c79958ed06bef8cd62eb72c368ecfc691f6389b6b`.
The upstream driver accepts analog termination values from 150 through 400 mA
and documents the four hardware choices as 150, 200, 300 and 400 mA. The old
mainline DTS value `52000` microamps becomes 52 mA, is rejected, and falls back
to 200 mA. That fallback was observed on v0.11 as:

```text
rk817-charger ...: Invalid charge termination 52000, keeping default
```

## Candidate boundary

Patch `0009-arm64-dts-rockchip-use-rk817-150ma-charge-termination.patch`
changes only the R46H battery property's value from 52000 to 150000 microamps.
The resulting upstream analog selector is 0, exactly matching the vendor
driver's effective `CHRG_TERM_150MA` selection. Charge voltage remains 4.2 V,
maximum charge current remains 2 A, and patch 0008's GPIO-backed ONLINE logic
is unchanged.

The release identity is
`6.12.99-r46h-mainline-v0.12-charge-term-150ma`.

## Host artifact result

The clean source commit
`9054fc849fc4845a4b5511d8edbf94e969328367` produced the canonical host
artifacts on 2026-08-15. The independently checked evidence is:

- 238 `SOURCE-SHA256SUMS` entries match the corresponding Git blobs;
- the canonical Git source snapshot SHA-256 is
  `40a1301ebcb2a4f0dbf977ee2bd90d2771d6d1f1a7129d08684d19edf8fa81eb`;
- all 1,294 package payload hashes pass, including 1,276 modules;
- the package tar SHA-256 is
  `d974e397ab0ddedaf46309fde2aa0bdf9eb1775b50431ad85f913a652c614f52`;
- the module-tree SHA-256 is
  `6a0a4c4a82919c6461307e644db37b2569a349120d8f2c4933b0e7d1a341608f`;
- the R46H DTB SHA-256 is
  `d1b035ee09ed0c44ccad62304f0c588d302c6055f634e65390850163cceba8ad`.

Relative to v0.11, the final config changes only `CONFIG_LOCALVERSION`, while
`Module.symvers`, `System.map`, the 1,290-file module set and all 14 non-`.ko`
module metadata files are byte-identical. After removing `.modinfo` and GNU
build-ID notes, 1,275 modules are byte-identical. The remaining `msm.ko` has
only the expected kernel-release text on its normalized printable-string
surface. Decompiling both DTBs yields one property change: the battery
termination current changes from 52,000 to 150,000 microamps.

This is a **PASS (host only)**. It proves the source, package and intended DTB
delta; it does not prove actual charging or make the candidate safe for an
unattended charging experiment.

## 2026-08-17 attended input-current result

An inline USB meter became available after the host-only v0.12 build. The first
bounded run deliberately used the unchanged active
`6.12.99-r46h-mainline-v0.10-adc-full-range` installation; it tested whether
the existing physical path supplies net current to the battery, not whether the
unbooted v0.12 candidate terminates at 150 mA.

With the board powered off, USB-DC held 5.00 V and fell from 0.63 to 0.61 A,
the charge LED was lit, the operator reported normal case temperature and the
pre-power serial console remained silent. After normal boot, RetroArch was
stopped to keep the login-page load stable. The observed differential was:

| Phase | Inline USB result | Five RK817 `current_avg` samples | Battery voltage |
| --- | --- | --- | --- |
| connected | 4.98 V / 0.85 A | `+252152..+255764` uA | `4.050930..4.051770` V |
| disconnected | 0 A | `-702276..-702792` uA | `3.932910..3.938580` V |
| reconnected | 4.98 V / 0.91 A | `+287756..+291540` uA | `4.041990..4.045070` V |

The connected-to-disconnected battery-current difference is approximately
0.95--0.99 A at about 4 V, or 3.8--4.0 W. That is consistent with the measured
4.2--4.5 W USB input after conversion loss. The sign reversal, voltage response,
charge LED and input meter together prove actual net battery charging during
this short attended run; the input meter alone would not have proved it.

The old v0.10 driver continued to report `online=0`, charger voltage 0 and
`Not charging`, exactly the board-detect defect already fixed and separately
proved on v0.11. Its live DT also retained `charge_term_current=52000`, and boot
logged the expected fallback to the driver's default. Capacity changed from 97
to 96 percent despite positive current, so this uncalibrated estimate was not an
acceptance criterion. The run found zero failed units, a clean ext4 state and no
post-initialization MMC/ext4 fault. Controlled shutdown remounted root read-only,
unmounted all filesystems and reached `Powering off`; powered-off USB input then
returned to 5.00 V / 0.58 A before USB-DC was removed.

The raw serial evidence is
`mainline/out/r46h-serial-logs/v010-charger-input-meter-20260817.bin`, 63,828
bytes, SHA-256
`f8d068698b158847104ee4bef7b5c3c191c6db296b1b19d57b79d6e9dee56fd9`.
It also captured an independent cold-MMC initialization recurrence, tracked by
the fast-card runbook rather than promoted into this charger result.

This is **PASS (short attended actual charging on v0.10)**. It does not validate
v0.12's 150 mA termination selection on hardware, charge completion, a full
cycle, meter calibration, calibrated battery temperature, long-duration or
unattended safety. Do not boot v0.12 merely to repeat this direction gate. A
future v0.12 experiment must specifically target termination/completion, remain
attended and set reviewed voltage, current, time and temperature stop limits.
