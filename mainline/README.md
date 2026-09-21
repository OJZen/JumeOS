# R46H mainline

This tree contains the active JumeOS platform work for the R46H. Read the
[project context](../docs/PROJECT-CONTEXT.md) and
[evidence ledger](board/r46h/EXPERIMENT-STATUS.md) before selecting a hardware
candidate.

## Source map

| Path | Purpose |
| --- | --- |
| [`board/r46h/`](board/r46h/) | Board DTS, notes, and physical evidence ledger |
| [`config/`](config/), [`patches/`](patches/) | Kernel configuration and patch series |
| [`rootfs-debian13/`](rootfs-debian13/) | Debian base system |
| [`rootfs-debian13-gaming-v18/`](rootfs-debian13-gaming-v18/) | Current gaming rootfs entry point |
| [`gaming-es-de/`](gaming-es-de/) | ES-DE runtime and frontend integration |
| [`gaming-shell/`](gaming-shell/) | Qt Quick handheld desktop |
| [`gaming-browser/`](gaming-browser/) | Optional Chromium-based handheld browser preview |
| [`gaming-wayland/`](gaming-wayland/) | Shared Wayland session and routed input |
| [`gaming-ports/`](gaming-ports/) | PortMaster and native game support |
| [`gaming-moonlight/`](gaming-moonlight/) | Moonlight client work |
| [`gaming-usb-gamepad/`](gaming-usb-gamepad/) | USB HID feasibility boundary |
| [`deploy/`](deploy/) | Fixed media profiles and guarded deployment inputs |
| [`scripts/`](scripts/) | Builders, verifiers, and deployment tools |
| [`tools/`](tools/) | Card Agent and next-generation card toolchain |
| [`tests/`](tests/) | Focused host regression checks |

The v0.18 rootfs builder imports the preceding versioned builders, so those
directories are source dependencies rather than archived releases. Generated
artifacts and device evidence live under ignored `out/` or `.cache/`.

## Common checks

Run the smallest check that owns the changed behavior, then:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B mainline/tests/test-project-docs.py
git diff --check
```

Build and hardware commands are documented by the nearest feature README.
