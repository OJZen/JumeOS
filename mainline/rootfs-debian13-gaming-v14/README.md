# R46H Debian 13 gaming p2 v0.14

Status: **HOST PASS / MEDIA + PHYSICAL OPEN**

This is the minimal Dreamcast successor to exact p2 v0.13. It adds the pinned
Flycast v2.6 AArch64 GLES2 libretro core, one ES-DE system, 14 audited
original-card entries and 28 existing media links. It uses Flycast's HLE BIOS;
no proprietary BIOS, old VMU/NVRAM state or ROM is packaged. BOOT, p1 and p3
remain outside the image and write plan.

## Host build

```sh
PYTHONDONTWRITEBYTECODE=1 mainline/gaming-flycast/generate-filtered-gamelist.py \
  --rom-root mainline/out/.cache/r46h-original-card-import-20260826/easyroms \
  --base-media mainline/out/r46h-gaming-ppsspp-content-v0.1/legacy-media-links.tsv \
  --output-root mainline/out/r46h-gaming-flycast-content-v0.1

PYTHONDONTWRITEBYTECODE=1 mainline/scripts/build-debian13-gaming-rootfs-v14.py validate-inputs
PYTHONDONTWRITEBYTECODE=1 mainline/scripts/build-debian13-gaming-rootfs-v14.py build
PYTHONDONTWRITEBYTECODE=1 mainline/scripts/build-debian13-gaming-rootfs-v14.py validate
```

The offline composer starts from exact p2 v0.13 and writes no block device. It
checks the core, 13-system configuration, 14-entry Dreamcast gamelist,
6,115-link media manifest, writable private Flycast state directory and direct
readbacks. Core options remain user-tunable after installation.

Two full builds from source commit
`64196d92cd33c3cc92475134557c33a912b36ba5` were byte-identical, and a
separate post-publish validation passed:

- image: `r46h-debian13-p2-gaming-v0.14.ext4`
- size: `10,716,877,312` bytes
- SHA-256: `34a52170a7b6d950abd677f7ff3f1c03f87449629047a536a44500efae8efffe`
- `BUILD-INFO` SHA-256: `6c3319cb983021d55e3f87490937ba3bc432d69f20b8abda47835c3a1d60d8fb`
- consolidated receipt SHA-256: `3143cf0856fe86cd20c9bf3cf2b8142261d3b2d8d052c65e7a0c2de518d0b49e`

Host startup ran every retained CDI/CHD for 120 software-EGL frames with HLE
BIOS and clean unload. It does not prove physical Mali output, LCD/audio,
controls, saving, pacing or gameplay.

## Historical device contract

Use [Project Context](../../docs/PROJECT-CONTEXT.md) for current deployment
selection. Later [Flycast gameplay](../gaming-flycast/README.md) failed on
Panfrost; do not repeat it without a new hypothesis. The original, unclosed
v0.14 acceptance scope was ES-DE discovery, one CDI and one CHD, Chinese text,
D-pad/sticks/buttons, audio, per-game VMU save plus warm reboot, frame pacing, remote input/screenshot,
rollback, read-only `/roms`, health and poweroff. Keep p1 and p3 outside the plan.
