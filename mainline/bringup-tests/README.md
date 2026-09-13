# R46H bring-up tests

This directory contains bounded probes and executable feature contracts. It is
an index, not a current result summary. Read
[Project Context](../../docs/PROJECT-CONTEXT.md) and the
[experiment ledger](../board/r46h/EXPERIMENT-STATUS.md) before selecting a
physical action.

Run only the contract that owns the changed hypothesis. Historical versions and
completed attended batches remain available for regression/source provenance;
their presence is not permission to repeat them.

## Foundation and product

- [ADAPTATION-READONLY.md](ADAPTATION-READONLY.md) — retained exact v0.8/Debian
  p2 non-mutating audit contract.
- [GAMING-MVP.md](GAMING-MVP.md) — Debian-native RetroArch/libretro path.
- [GAMING-PRODUCT.md](GAMING-PRODUCT.md) — accepted first-version gaming
  product contract.
- [GAMING-INPUT-BRIDGE.md](GAMING-INPUT-BRIDGE.md) — combined-controller
  development and removal boundary.

## Boot, MMC and power

- [V11-USB-DC-ONE-SHOT.md](V11-USB-DC-ONE-SHOT.md) — exact ONLINE candidate.
- [V12-CHARGE-TERM-POLICY.md](V12-CHARGE-TERM-POLICY.md) — host-only RK817
  termination policy.
- [V13-MMC-INIT-ONE-SHOT.md](V13-MMC-INIT-ONE-SHOT.md) — bounded MMC
  observation.
- [V16-MMC-COLD-ISOLATION.md](V16-MMC-COLD-ISOLATION.md) — rejected persistent
  isolation experiment and rollback.
- [V17-MMC-POWER-SETTLE.md](V17-MMC-POWER-SETTLE.md) — accepted first-version
  power-settle gate.
- [CHARGER-DC-DETECT-PROBE.md](CHARGER-DC-DETECT-PROBE.md) — historical
  GPIO0_B3 localization.

## Input, network and gaming batches

- [INPUT-WIFI-ACTIVE.md](INPUT-WIFI-ACTIVE.md) — bounded input and Wi-Fi active
  gates.
- [ATTENDED-GAMING-BATCH.md](ATTENDED-GAMING-BATCH.md) and
  [ATTENDED-GAMING-RETRY.md](ATTENDED-GAMING-RETRY.md) — completed historical
  attended product batches.
- [ATTENDED-INPUT-AUDIO-BATCH.md](ATTENDED-INPUT-AUDIO-BATCH.md) and
  [ATTENDED-INPUT-AUDIO-COMPLETION.md](ATTENDED-INPUT-AUDIO-COMPLETION.md) —
  completed input/audio batches retained for exact evidence.

## Audio

- [AUDIO-ROUTE-PROBE.md](AUDIO-ROUTE-PROBE.md) — bounded speaker/headphone
  route and mechanical cut-off.
- [AUDIO-JACK-PROBE.md](AUDIO-JACK-PROBE.md) — event-only jack gate.
- [AUDIO-JACK-LOCALIZATION.md](AUDIO-JACK-LOCALIZATION.md) — simultaneous
  evdev/GPIO localization.
- [AUDIO-JACK-VENDOR-CONTROL.md](AUDIO-JACK-VENDOR-CONTROL.md) — retained
  factory-kernel comparison.

## Media, USB and rumble

- [MEDIA-USB-PREFLIGHT.md](MEDIA-USB-PREFLIGHT.md) — query-only readiness
  contract.
- [USB-STORAGE-READ-PROBE.md](USB-STORAGE-READ-PROBE.md) — accepted single
  external USB Host bounded-read contract; USB-DC is not a second Host.
- [RUMBLE-PROBE.md](RUMBLE-PROBE.md) — bounded direct motor actuation.
- [HANTRO-JPEG-PROBE.md](HANTRO-JPEG-PROBE.md),
  [HANTRO-MPEG2-DECODE-PROBE.md](HANTRO-MPEG2-DECODE-PROBE.md) and
  [HANTRO-CODEC-DECODE-PROBE.md](HANTRO-CODEC-DECODE-PROBE.md) — exact media
  codec probes.

## Execution rules

- Freeze exact kernel/rootfs/payload identity and expected result markers.
- Keep target-side tools in verified tmpfs unless a product installer owns
  persistent state.
- Run hardware probes serially; parallel host development must not become
  concurrent access to one board.
- Define operator actions, abort conditions, cleanup and final power state
  before starting.
- Never promote a probe result to a product service without a separate design
  and acceptance contract.
- Record accepted physical results only in the ledger. Exact commands and
  hashes stay in the owning runbook.
