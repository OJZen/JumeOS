# R46H Debian 13 gaming p2 v0.9

Status: **HOST CANDIDATE / MEDIA + PHYSICAL OPEN**

This is the minimal full-FBNeo successor to reproducible p2 v0.8. It adds the
pinned 79,683,320-byte AArch64 core and one ES-DE `arcade` entry. The accepted
Neo-Geo subset remains installed as the Metal Slug/Ozone fallback. BOOT, p1,
p3, packages, services and the existing 3,417 media links do not change.

The original-card arcade directory has 11 exact null-I/O load passes spanning
Capcom, Cave, Konami and Taito. `progear.zip` is a known incomplete parent set,
so broad content compatibility remains open. CPS1/CPS2/CPS3 directories are
not separately advertised yet.

## Host build

The networkless composer starts from the exact p2 v0.8 image and consumes the
exact full core plus the two exact v0.8 identity scripts. It writes no block
device.

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v09.py validate-inputs
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v09.py build
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v09.py validate
```

Clean source commit `5430ecf456b7ed2201915cc650b6d0aa33f2e89e` produced two
byte-identical 10,716,877,312-byte images, then passed a separate read-only
validation. The published image SHA-256 is
`9b5bf248c39121ad2cfde2d719648469442e9c89f194cfcfca3674336b2e0ea5`;
its `BUILD-INFO` SHA-256 is
`8062fbe076cfb4cf1b7cace9f5586fe69d79867706579842636649e182473285`.

## Historical device contract

Deployment selection belongs to [Project Context](../../docs/PROJECT-CONTEXT.md).
This intermediate image is retained for its build contract, not another pending
card write. Its unclosed device scope was exact
identity, ES-DE motion, Arcade visibility, `1941`, `1944` and one non-Capcom
game, Metal Slug fallback, screenshot/remote input, read-only `/roms`, health
and controlled poweroff. Keep p1 and p3 outside the plan.

Only exact p2 v0.9 can use this version's
[`pair-remote-key.sh`](pair-remote-key.sh). The public key remains deployment
state, not image content.
