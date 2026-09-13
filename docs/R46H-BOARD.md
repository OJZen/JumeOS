# R46H board notes

This document retains stable board-source rationale and unresolved hardware
assumptions. It is not a result ledger. For current physical evidence, read
[EXPERIMENT-STATUS.md](../mainline/board/r46h/EXPERIMENT-STATUS.md).

## Source basis

- Current board sources target released Linux `v6.12.99`.
- `mainline/board/r46h/rk3326-r46h.dts` and the provisional panel driver are
  the reviewable outputs of the product series through patch `0008`.
- Patch `0009` is retained as the host-only v0.12 termination-policy
  experiment and is deliberately excluded by the current product manifest.
- Board model, GPIO assignments, regulators, display timing and panel bytes
  came from the running R46H FDT and downstream Linux 4.4 DTS/driver.
- The top-level compatible preserves the string observed on the physical
  device. `gameconsole,r46h-panel` remains a local provisional compatible,
  not an upstream-ready hardware identity.
- CPU/GPU use upstream PX30/RK3326 OPP tables. The mainline path does not import
  ArkOS overclock or voltage overlays.

## Display

The panel driver decodes the complete downstream 843-byte sequence into 167 DCS
short writes, sleep-exit delay and display-on delay. The duplicated downstream
write is intentionally preserved. Mainline keeps the downstream no-EoT
semantics and the matched 396 Mbps/lane host/PHY rate.

Changing panel rails, DSI timers and replaying the full sequence did not produce
a stable Linux-initialized image. The accepted v0.8 solution preserves the
incoming reset/regulator selector state and skips only the first reset/DCS
replay. Later prepares fall back to full initialization.

This proves a usable bootloader-to-Linux fbcon handoff, not complete
`loader_protect`, a general KMS/page-flip path or reliable full panel
reinitialization. Keep the provisional driver isolated to the exact R46H
compatible.

## Input

The ADC mux follows upstream ODROID-Go3 wiring because its select/enable GPIOs
match the downstream R46H description. v0.9 fixed inverted-axis handling; v0.10
advertises the conservative complete unsigned 10-bit SARADC range
`0..1023`. Physical full-travel evidence accepted that range.

The inherited active-low GPIO2_A4 node advertises
`BTN_TRIGGER_HAPPY5`/“F5”, but the tested R46H has no identified matching
physical key and the line remained idle-high. Keep this as a fail-closed
DT/hardware mismatch until a schematic or continuity test justifies documenting
the key or deleting the node.

The permanent product input bridge combines the accepted physical sources for
RetroArch. Diagnostic one-shot bridges are not product services and should not
be reinstalled.

## Power and charging

The v0.11 single-variable candidate adds the observed active-high GPIO0_B3
USB-DC input to RK817 ONLINE reporting. It does not change charge voltage,
current, enable state or input limits. Host artifacts cannot prove battery
current direction or safe charging; the later bounded physical run separately
proved ONLINE transitions and short-run net charging.

The v0.12 source maps the vendor driver's effective 150 mA termination choice
to the upstream `150000`-microamp property. This remains host-only policy
evidence. Charge completion, calibrated temperature and unattended/long-term
safety remain open.

Battery OCV/capacity data came from downstream sources and has not been
calibrated for trustworthy percentage reporting.

## Audio

The accepted built-in speaker path uses the RK817 HP playback mux feeding the
external amplifier; the direct SPK/Class-D experiments were silent. Stereo
headphone playback and mechanical speaker cut-off passed.

Mainline and factory kernels both observed no transition on the inherited
active-low GPIO2_C6 jack-detect path during bounded insertion tests. DAPM stays
deliberately configured without automatic jack routing. Do not infer socket
damage, and do not repeat the unchanged GPIO/event experiments without a new
electrical or schematic hypothesis.

## Storage, USB and other board limits

- The two removable-card controllers share RK817 SD power rails. v0.17 disables
  the second controller and adds the accepted system-card power-settle delay;
  the second slot is unavailable in the current profile.
- The board exposes one external USB Host connector. USB-DC is power/detection,
  not another Host port.
- The status LED is exposed as a simple red GPIO LED; a red/blue policy is
  deferred.
- Direct `pwm-vibrator` actuation passed, but emulator/game rumble routing is
  still separate product work.

## Open hardware risks

1. Panel controller/glass identity and full reset/DCS initialization.
2. Statistical cold-MMC reliability and the independent need for secondary-host
   isolation.
3. Second-card simultaneous rail/voltage behavior.
4. Automatic headphone jack reporting/DAPM routing.
5. Calibrated battery percentage, termination completion and long-duration
   charge/thermal behavior.
6. Suspend/resume.

Exact accepted boundaries and “do not repeat” rules belong only in the
[experiment ledger](../mainline/board/r46h/EXPERIMENT-STATUS.md).
