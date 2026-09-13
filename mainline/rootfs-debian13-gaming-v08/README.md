# R46H Debian 13 gaming p2 v0.8

Status: **HOST CANDIDATE / MEDIA + PHYSICAL OPEN**

This is the reproducible consolidation successor to exact p2 v0.7. It folds
the already accepted Ozone/FBNeo fallback, ES-DE 3.4.1/r51 visual profile,
ARGB8888 screenshot helper and fixed remote keyboard actions into one p2 image.
It does not modify BOOT, p1 or p3.

The builder is host-only and networkless. It starts from the exact accepted
10,716,877,312-byte v0.7 image and consumes five hash-pinned local artifacts:
the ES-DE runtime, migrated-media manifest, FBNeo core, DRM capture helper and
remote-input helper. All other product files are committed source blobs. Two
independent compositions must be byte-identical, followed by a third read-only
validation pass.

## Product boundary

- ES-DE remains the automatic frontend; Ozone remains the in-game fallback.
- Seven systems are advertised because only their cores are currently present.
- `/roms` remains a read-only p3 mount. The image contains only allowlisted
  links and no ROM data.
- The old live-install rollback stacks are omitted. Whole-p2 rollback is the
  retained prewrite clone owned by the Card Agent transaction.
- No operator public key, private key, host key, network profile, machine ID or
  target firstboot marker is embedded. Remote control requires the separate
  key-pairing step after the first boot.
- Component receipts are retained only where accepted runtime launchers require
  their exact compatibility identity; the consolidated receipt explicitly owns
  image provenance.

The filesystem UUID is `d3130008-46a4-4d56-9001-000000000008`, label
`R46H_GAMING_V08`, and the fixed p2 geometry is unchanged.

## Build and validate

Published hashes describe the source commit below. Current-checkout screenshot
identity drift is tracked in the [test index](../tests/README.md#current-review-gaps).

Docker Desktop and the five exact ignored inputs under `mainline/out/` must be
present. The build does not download anything or open a block device.

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v08.py validate-inputs
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v08.py build
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v08.py validate
```

The expected output is
`mainline/out/r46h-debian13-p2-gaming-v0.8/r46h-debian13-p2-gaming-v0.8.ext4`.
`HOST CANDIDATE` means only the retained artifact and host checks passed; it is
not permission to reuse an old disk path or claim an R46H boot result.

## Accepted host artifact

Clean source commit `d777b1661ed2bb1c45c7b51b4c44a488d785b1fc`
produced two byte-identical 10,716,877,312-byte images and passed a later
independent read-only validation. The published image SHA-256 is
`da8798c85864fc5ec3abc2cc940cbbbce737090f6281c19d92e301d95bf7247f`;
its `BUILD-INFO` SHA-256 is
`66d09d48aa26470b5c599e682916057ab5270a6c36fa5ea9577337eb3bef9587`.
This closes host composition only; no block device or R46H was accessed.

## Historical device contract

This intermediate image's separate media/physical gate remains open. Follow
[Project Context](../../docs/PROJECT-CONTEXT.md) for the current candidate and
next gate; do not deploy v0.8 just to close its historical checklist.
Its original acceptance scope was exact
v0.8 identity, read-only `/roms`, ES-DE motion, physical D-pad/A isolation from
remote input, one NES launch, Metal Slug, screenshot/input over strict SSH,
zero ext4/failed-unit errors and controlled poweroff. Keep p1 and p3 outside the
plan.

Only on exact p2 v0.8, stage an operator `.pub` file and the exact
[`pair-remote-key.sh`](pair-remote-key.sh) under `/run/r46h-pair-v0.8/`; run the
script with its SHA-256. The public key is deployment state, not image content.
