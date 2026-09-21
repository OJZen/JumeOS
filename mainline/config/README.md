# R46H kernel configuration

`r46h.fragment` is merged on top of the arm64 `defconfig` from the exact
Linux `v6.12.99` release. The next product candidate is
`6.12.99-r46h-mainline-v0.19-zram-product`. It keeps the accepted v0.15
hardware configuration and adds the already device-tested modular zram/LZ4
configuration. `manifest.env` selects the
contiguous patch prefix through `0008`, so this release keeps the physically
accepted v0.8 display handoff, v0.10 ADC behavior and v0.11 GPIO-backed ONLINE
report, then adds the already proved built-in `INPUT_UINPUT` configuration.
It deliberately excludes the host-only v0.12 150 mA termination experiment
and the spent v0.13 MMC logging diagnostic. The later patch files remain in
the repository as historical experiment sources; they are not product build
inputs. See [`../bringup-tests/GAMING-INPUT-BRIDGE.md`](../bringup-tests/GAMING-INPUT-BRIDGE.md).

The fragment deliberately builds the MMC root path, UART2 console, Rockchip
VOP/DSI, provisional panel, Panfrost, thermal protection and the generic input
stack into the kernel.  The RK817 charger, Hantro decoder, exFAT and
`rtl8xxxu` stay modular: those devices either have uncertain calibration or
are easier to isolate during first hardware tests.

The in-tree `rtl8xxxu` USB ID table maps the observed `0bda:8179` adapter to
the RTL8188EU implementation without `CONFIG_RTL8XXXU_UNTESTED`.  The rootfs
must provide `rtlwifi/rtl8188eufw.bin`; the config does not embed firmware.

## 6.12 symbol mapping

- RK3326/PX30 has no separate user-visible SoC switch.  It is covered by
  `ARCH_ROCKCHIP` plus the PX30/RK3326 DT compatibles and platform drivers.
- RK817 exposes one upstream battery/charger switch, `CHARGER_RK817`; there is
  no `BATTERY_RK817` symbol in v6.12.99.  It remains a module because the
  current device's fuel-gauge calibration is not trustworthy yet.
- The generic stick path is `ROCKCHIP_SARADC` -> `IIO_MUX`/`MUX_GPIO` ->
  `JOYSTICK_ADC`; rumble is the separate `INPUT_PWM_VIBRA` input device.
  `INPUT_UINPUT=y` supplies only the generic virtual-input endpoint for the
  optional bridge and is built in so a one-shot kernel does not depend on a
  matching module installation before the bridge can be tested.
- `MMC_CQHCI=y` preserves the generic library selected by arm64 defconfig, but
  the RK3326 `dw_mmc-rockchip` host does not register CQE operations and
  `MMC_HSQ` remains disabled. An A2-labelled card therefore works through the
  accepted SD/UHS-I path without claiming active A2 command queue acceleration.
- Hantro uses a tristate core (`VIDEO_HANTRO=m`) and a Rockchip backend boolean
  (`VIDEO_HANTRO_ROCKCHIP=y`).
- `DRM_PANEL_R46H` is the only non-upstream symbol.  It is supplied by the
  R46H patch and intentionally fails validation against an unpatched tree.

## Reproduce the Kconfig check

The [performance/power plan](../../docs/PERFORMANCE-POWER.md#compressed-memory-and-disk-swap)
owns the 256 MiB LZ4 policy and its remaining persistent deployment gate.

Apply the R46H kernel patch first, because `CONFIG_DRM_PANEL_R46H` is a local
bring-up symbol and does not exist in pristine v6.12.99.  Then run from the
kernel source tree, with `REPO` and `BUILD` pointing at external-disk paths:

```bash
make O="$BUILD" ARCH=arm64 defconfig
scripts/kconfig/merge_config.sh -m -O "$BUILD" \
  "$BUILD/.config" "$REPO/mainline/config/r46h.fragment"
make O="$BUILD" ARCH=arm64 olddefconfig
"$REPO/mainline/config/validate-config.sh" "$BUILD/.config"
```

`validate-config.sh` checks every requested assignment and every explicit
disabled option after dependency resolution.  A missing symbol is a hard
failure rather than a warning.

This sequence was run in a case-sensitive Linux filesystem against tag
`v6.12.99` (commit `720e8bcaa674dfa40b989207d6cdb44b3aaa8db6`) after applying the R46H patch.
The product fragment currently contains 180 explicit requests. The canonical
build must prove that all survive `olddefconfig`; the same check on a pristine
tree is expected to fail at least on the not-yet-applied `DRM_PANEL_R46H`
symbol.
