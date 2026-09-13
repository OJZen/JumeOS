# Architecture

This document describes stable structure and design boundaries. For the live
checkpoint, read [Project Context](PROJECT-CONTEXT.md); for physical evidence,
read the [R46H ledger](../mainline/board/r46h/EXPERIMENT-STATUS.md).

## Repository scope

JumeOS keeps its R46H source under `mainline/`. The system uses Debian-native
RetroArch 1.20 and libretro cores beneath a replaceable p2-local frontend
service.

## Technology stack

| Layer | Current choice |
| --- | --- |
| SoC/board | ARM64 Rockchip RK3326, fixed R46H/g92 hardware profile |
| Boot | Vendor U-Boot 2017.09; FAT p1 `boot.ini`, Image, initrd and DTB |
| Kernel | Linux 6.12.99 with R46H DTS/config/patch set |
| Graphics | DRM panel pipeline, Mesa/Panfrost |
| Base OS | Debian 13 (trixie), systemd, NetworkManager, OpenSSH |
| Audio/input | ALSA/RK817, evdev/udev, permanent combined-input service |
| Frontend | p2-local ES-DE launcher; RetroArch/Ozone supplies the in-game menu and retained fallback |
| Gaming | RetroArch 1.20, Debian-native/pinned libretro cores, read-only EASYROMS on p3 |
| Remote operations | Strict host-key SSH, bounded KMS screenshots and fixed one-shot frontend input; serial remains boot/recovery authority |
| Implementation | Kernel C/DTS; C probes/helpers; Python builders, verifiers and tests; thin Bash entry points |
| Media tooling | Swift Card Agent for guarded macOS operations; Rust/Python next-generation toolchain |
| Build isolation | Docker/container builders with disposable data on the external workspace |

## Boot and storage flow

```text
ROM/DDR -> BL31/OP-TEE -> U-Boot -> p1 boot.ini
                                  -> Image + initrd + R46H DTB
                                  -> p2 Debian 13 rootfs/systemd
                                  -> p2 frontend service
                                  -> RetroArch/libretro
                                  -> intended: p3 EASYROMS mounted at /roms
```

The diagram states the product boundary, not current physical evidence. Whether
p3 is mounted and accepted now belongs to Project Context and the ledger.

The serial rate is part of this chain: early ROM/DDR/BL31 output is 1,500,000
baud; U-Boot and Linux use 115,200 baud after the visible OP-TEE handoff marker.

Partition responsibilities for the fixed profile:

- Prefix: immutable bootloader-area bytes governed by the release profile.
- p1 (FAT/BOOT): versioned kernel, DTB, initrd and `boot.ini` selection.
- p2 (ext4): Debian rootfs, modules, services, RetroArch configuration and
  operational receipts.
- p3 (exFAT/EASYROMS): user content plus required recovery files. It is data,
  not a place for active kernel or rootfs updates.

Ordinary product updates should use SSH/Wi-Fi and mutate only the narrow p2
payload. BOOT changes use versioned inactive files plus explicit promotion and
rollback. Full-card or partition writes are exceptional, identity-bound media
operations.

## Mainline component map

| Path | Responsibility |
| --- | --- |
| `board/r46h/` | Board DTS and authoritative experiment ledger; rationale is in [R46H board notes](R46H-BOARD.md) |
| `config/`, `patches/`, `manifest.env` | Kernel configuration and pinned source/patch identity |
| `scripts/` | Reproducible builders, verifiers, deployment plans and thin launchers |
| `rootfs-debian13*/` | Base and gaming rootfs construction/integration |
| `gaming-*/` | Versioned gaming MVP, input, History, ROM and promotion payloads |
| `bringup-tests/` | Hardware probes and feature-local executable runbooks |
| `deploy/` | Fixed profiles, plans and deployment templates |
| `tools/` | Card Agent, card toolchain and target-side utilities |
| `tests/` | Static contracts, deterministic builders and regression checks |
| `out/`, `.cache/` | Generated artifacts, named evidence and disposable workspace; not source authority |

See [mainline/README.md](../mainline/README.md) for the short entry-point index.

## Design boundaries

### Custom shell candidate

The [Device Shell design](DEVICE-SHELL.md) separates Qt Quick UI, existing
system services and the shared Wayland display. `mainline/gaming-shell/` supplies
the Qt UI; `mainline/gaming-wayland/` owns compositor policy, capture and routed
input. R33 has game/panel, automatic cleanup and disposable Neo save/load machine
proof. The candidate is not the current boot frontend. Preserve ES-DE/direct-DRM
fallbacks until product recovery, physical controls, streaming and
sustained-performance gates pass.

### Evidence boundary

Host artifact, media and physical-board results are separate states. Builders
emit deterministic inputs and receipts; media tools bind an exact device and
geometry; only an observed R46H run can close a hardware row in the ledger.

### Configuration boundary

Keep active configuration explicit and versioned. One-shot boot tests may
change the in-memory U-Boot command but never persist it with `saveenv`.
Promotion payloads retain rollback paths and do not silently replace unrelated
partitions.

### Service boundary

Product behavior belongs in small systemd-managed services or root-owned
configuration with receipts. Diagnostic probes stay bounded and removable; a
successful probe is not automatically a production service.

### Content boundary

ROM/content migration is independent from emulator ABI migration. p3 can carry
original user content, while the Debian-native stack supplies compatible cores
and frontend behavior. A launch result proves only the exact core/content path
that was exercised.

### Documentation boundary

Project-wide state and design live under `docs/`. Feature runbooks stay beside
their owning code when tests consume them as executable contracts. The ledger
is the sole exception for physical status because it is board-owned evidence.
