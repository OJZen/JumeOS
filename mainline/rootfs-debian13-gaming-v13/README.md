# R46H Debian 13 gaming p2 v0.13

Status: **HOST PASS / MEDIA + PHYSICAL OPEN**

This is the minimal PSP successor to exact p2 v0.12. It adds the pinned PPSSPP
v1.20.4 AArch64 libretro core, its 189 version-matched upstream assets, one
ES-DE system, six audited original-card entries and five existing cover images.
It does not modify ROMs, BOOT, p1 or p3.

## Host build

```sh
PYTHONDONTWRITEBYTECODE=1 mainline/gaming-ppsspp/generate-filtered-gamelist.py \
  --rom-root mainline/out/.cache/r46h-original-card-import-20260826/easyroms \
  --base-media mainline/out/r46h-gaming-es-de-media-v0.2/legacy-media-links.tsv \
  --output-root mainline/out/r46h-gaming-ppsspp-content-v0.1

PYTHONDONTWRITEBYTECODE=1 mainline/scripts/build-debian13-gaming-rootfs-v13.py validate-inputs
PYTHONDONTWRITEBYTECODE=1 mainline/scripts/build-debian13-gaming-rootfs-v13.py build
PYTHONDONTWRITEBYTECODE=1 mainline/scripts/build-debian13-gaming-rootfs-v13.py validate
```

The composer starts from exact p2 v0.12 and writes no block device. It checks
the core, every asset, the 12-system configuration, six-entry PSP gamelist,
6,087-link media manifest, native 480x272 OpenGL seed and all direct readbacks.
The generated core-options file remains user-tunable after installation.

Two clean full builds from source commit `bbda42e2b7644a4c42ea5b6e8865350fc7bf93e7`
were byte-identical, and a separate post-publish validation passed:

- image: `r46h-debian13-p2-gaming-v0.13.ext4`
- size: `10,716,877,312` bytes
- SHA-256: `5eac9494cadd106aece559169f984bcf1565b3a2aa48383f73eabdfe4d473098`
- `BUILD-INFO` SHA-256: `a863ca3b95ec034116306d447745d000c09aaee7ed8a5825619f4f957e998b1a`
- consolidated receipt SHA-256: `b2f6477d1c8eb2c73cf558320ccd35d426c1ebf64c580e57416b93d76a1908be`

Host startup proved all six retained ISO/CSO/PBP files reach PSP kernel and
graphics initialization with null I/O. It does not prove physical GLES output,
Chinese glyphs, audio, controls, saving, pacing or gameplay.

## Historical device contract

Use [Project Context](../../docs/PROJECT-CONTEXT.md) for the current candidate
and attended gate; do not deploy this intermediate image just for its old
checklist. Its unclosed scope was ES-DE discovery, one ISO and the loose PBP,
Chinese text, D-pad/sticks/buttons, audio, save plus warm reboot, frame pacing, remote
input/screenshot, rollback, read-only `/roms`, health and poweroff. Keep p1 and
p3 outside the plan.
