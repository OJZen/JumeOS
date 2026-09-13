# R46H Debian 13 gaming p2 v0.10

Status: **HOST CANDIDATE / MEDIA + PHYSICAL OPEN**

This is the minimal CPS1 successor to exact p2 v0.9. It adds one ES-DE `cps1`
entry and read-only `/roms/cps1` mapping. The full FBNeo core, Arcade entry,
Neo-Geo fallback and remote-control stack remain byte-exact. BOOT, p1, p3,
packages, services and the existing 3,417 media links do not change.

All 48 original-card CPS1 ZIPs reached the pinned FBNeo startup marker with
exact RetroArch and null I/O. This is not target gameplay proof. CPS2/CPS3 stay
hidden as whole systems after 57/62 and 9/12; broad compatibility remains open.

## Host build

The networkless composer starts from exact p2 v0.9 and consumes its two exact
identity scripts. It writes no block device.

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v10.py validate-inputs
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v10.py build
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v10.py validate
```

Clean source commit `f166c5d9372cc11bbfd0a70f85ab53de27e3bebb` produced two
byte-identical 10,716,877,312-byte images, then passed a separate read-only
validation. The published image SHA-256 is
`71f0da96c972dca90dc1c40fff8ec36a46afb3ad0535fff1584a983575d77adf`;
its `BUILD-INFO` SHA-256 is
`bce3868fc2e20ebfd998952553979b464997a4716c24983e720a9b92491ef92d`.

## Historical device contract

Deployment selection belongs to [Project Context](../../docs/PROJECT-CONTEXT.md).
This intermediate image is retained for its build contract, not another pending
card write. Its unclosed device scope was exact
identity, ES-DE motion, Arcade and CPS1 visibility, `1941`, `1944`, one CPS1
game, Metal Slug fallback, screenshot/remote input, read-only `/roms`, health
and controlled poweroff. Keep p1 and p3 outside the plan.

Only exact p2 v0.10 can use this version's
[`pair-remote-key.sh`](pair-remote-key.sh). The public key remains deployment
state, not image content.
