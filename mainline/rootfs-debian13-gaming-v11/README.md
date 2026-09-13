# R46H Debian 13 gaming p2 v0.11

Status: **HOST CANDIDATE / MEDIA + PHYSICAL OPEN**

This is the media-only successor to exact p2 v0.10. It keeps the same nine
ES-DE systems, cores, theme, services and read-only p3 ROM mappings, and adds
the original-card media already named by the Arcade and CPS1 gamelists.

The exact generated manifest has 6,008 links: the accepted 3,417 links plus
2,543 Arcade links and 48 CPS1 images. Missing source files remain normal ES-DE
fallbacks; no guessed paths, ROMs or media bytes enter p2.

## Host build

Published hashes describe the source commit below. Current-checkout screenshot
identity drift is tracked in the [test index](../tests/README.md#current-review-gaps).

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/gaming-es-de/generate-legacy-media-links.py \
  --rom-root mainline/out/.cache/r46h-original-card-import-20260826/easyroms \
  --output mainline/out/r46h-gaming-es-de-media-v0.1/legacy-media-links.tsv \
  --include-system arcade --include-system cps1

PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v11.py validate-inputs
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v11.py build
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v11.py validate
```

The composer starts from exact p2 v0.10, checks the pinned manifest, adds only
the Arcade/CPS1 link delta and reads the complete 6,008-link tree back from the
image. It writes no block device.

Clean source commit `1b1da13a374d342ca5d8f643242c00fc6f58f159`
produced two byte-identical 10,716,877,312-byte images and passed a separate
read-only validation. The image SHA-256 is
`d84788c682c1f9e8c13c7fdcc1f0ebea25944aa2933b3633dde18a031b2aac60`;
its `BUILD-INFO` SHA-256 is
`f8a462c987a5cbcac2d1ae4c054c7844c55d74ea3889f3dd44d58dac8be2a3ab`.

## Historical device contract

Deployment selection belongs to [Project Context](../../docs/PROJECT-CONTEXT.md).
This intermediate image is retained for its build contract, not another pending
card write. Its unclosed device scope was exact identity, ES-DE motion,
Arcade/CPS1 artwork and fallback, representative games, remote input/screenshot,
read-only `/roms`, health and controlled poweroff. Keep p1 and p3 outside the
plan. The old instruction to pair with the v0.10 helper was invalid: its UUID
guard rejects v0.11. An exact-version pairing helper is required for SSH.

Only for an explicitly selected v0.11 regression, independently hash the target
p2 and generate its session-scoped candidate:

```sh
python3 -B mainline/scripts/generate-debian13-write-plan.py \
  --device /dev/disk<diskN> \
  --artifact-id debian13-p2-gaming-v0.11 \
  --profile-id hl-r46h-v22-g92-62534975488-v1 \
  --target-sha256-before <target-p2-sha256>
```

The Card Agent must still perform live device/profile preflight. Generating the
plan does not authorize a stale disk path or prove a media write.
