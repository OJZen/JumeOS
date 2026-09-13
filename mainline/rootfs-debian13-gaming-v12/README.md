# R46H Debian 13 gaming p2 v0.12

Status: **HOST CANDIDATE / MEDIA + PHYSICAL OPEN**

This is the filtered CPS successor to exact p2 v0.11. It keeps the accepted
frontend, cores, services and read-only p3 mount, then adds CPS2/CPS3 menus for
the 57/62 and 9/12 archives that passed the pinned FBNeo startup audit.

The original Chinese metadata stays intact. Eight exact incomplete archives
are marked hidden in p2-owned gamelists; the ROM files remain untouched on p3
so FBNeo parent/clone lookup still sees them. Existing nine gamelists remain
read-only links to p3. ES-DE is switched from legacy-location priority to its
p2 gamelist directory and does not show hidden games.

## Host build

Published hashes describe the source commit below. Current-checkout screenshot
identity drift is tracked in the [test index](../tests/README.md#current-review-gaps).

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/gaming-fbneo-full/generate-filtered-gamelists.py \
  --rom-root mainline/out/.cache/r46h-original-card-import-20260826/easyroms \
  --output-root mainline/out/r46h-gaming-fbneo-filter-v0.1

PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/gaming-es-de/generate-legacy-media-links.py \
  --rom-root mainline/out/.cache/r46h-original-card-import-20260826/easyroms \
  --output mainline/out/r46h-gaming-es-de-media-v0.2/legacy-media-links.tsv \
  --include-system arcade --include-system cps1 \
  --include-system cps2 --include-system cps3

PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v12.py validate-inputs
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v12.py build
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v12.py validate
```

The composer starts from exact p2 v0.11 and writes no block device. It verifies
all 6,082 media links, both filtered gamelists, all eleven system mappings and
the two ES-DE settings changes by reading them back from the image.

Clean source commit `b555a5319f94bd10765191a2dab907b728311556`
produced two byte-identical 10,716,877,312-byte images and passed a separate
read-only validation. The image SHA-256 is
`af3235742a0324453a6193bc0c3ec0e149fffcf9f6c0c22dba4e2f2e082a9111`;
its `BUILD-INFO` SHA-256 is
`dcc7d0e526d9efe0f2bb58930cc008d672091c3b262fd3afa1694bb1a4a7fcf4`.

## Historical device contract

Deployment selection belongs to [Project Context](../../docs/PROJECT-CONTEXT.md).
This intermediate image is retained for its build contract, not another pending
card write. Its unclosed device scope was identity, menu motion,
CPS2/CPS3 visibility and representative launches, existing systems, controls,
audio, remote input/screenshot, read-only `/roms`, health and poweroff. Keep p1
and p3 outside the plan.

Only for an explicitly selected v0.12 regression, independently hash the target
p2 and generate its session-scoped candidate:

```sh
python3 -B mainline/scripts/generate-debian13-write-plan.py \
  --device /dev/disk<diskN> \
  --artifact-id debian13-p2-gaming-v0.12 \
  --profile-id hl-r46h-v22-g92-62534975488-v1 \
  --target-sha256-before <target-p2-sha256>
```

The Card Agent must still perform live device/profile preflight. The plan never
authorizes a stale disk path or proves a media write.
