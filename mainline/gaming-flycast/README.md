# R46H Flycast component

Status: **HOST PASS / DEVICE GAMEPLAY FAIL**

This is the smallest Dreamcast addition for the accepted Debian 13 gaming
stack: Flycast v2.6 as an AArch64 GLES2 libretro core, one filtered ES-DE
system and the 14 Dreamcast images actually present on imported p3. ROMs stay
external and read-only.

The build uses exact upstream commit `392a429e8b040b3e5bf6696cb4f984274fc44123`
and initializes only the two submodules required by this Linux/libretro build.
It deliberately reuses the pinned PPSSPP Debian 13 builder instead of creating
a duplicate multi-gigabyte image.

```sh
PYTHONDONTWRITEBYTECODE=1 mainline/gaming-flycast/build-core.py build
PYTHONDONTWRITEBYTECODE=1 mainline/gaming-flycast/build-core.py validate

PYTHONDONTWRITEBYTECODE=1 mainline/gaming-flycast/generate-filtered-gamelist.py \
  --rom-root mainline/out/.cache/r46h-original-card-import-20260826/easyroms \
  --base-media mainline/out/r46h-gaming-ppsspp-content-v0.1/legacy-media-links.tsv \
  --output-root mainline/out/r46h-gaming-flycast-content-v0.1
```

The host audit loaded all seven CHD and seven CDI files through RetroArch 1.20,
selected the built-in HLE BIOS, created a writable fresh system/save tree, ran
120 software-EGL frames and unloaded cleanly. `content-audit.json` owns the
exact file identities and proof boundary.

No proprietary BIOS, original-card VMU/NVRAM state or ROM is committed or
packaged. The product seed keeps native 640x480 and exposes ordinary RetroArch
core options for device tuning.

## Device result

On exact p2 v0.15, `Capcom vs SNK 2 街霸对拳皇2.chd` reaches its VMU/start screen
at 640x480 with PCM running. Entering gameplay then continuously triggers
Panfrost `DATA_INVALID_FAULT`. The shipped per-strip path and a temporary
per-triangle path both fail. Forcing Mesa llvmpipe avoids the GPU fault but uses
about 300% CPU and leaves ALSA in XRUN, so it is not a playable fallback.

All experiments were reverted before a clean warm reboot. Keep Dreamcast hidden
from the first-version menu until a changed core or graphics-stack hypothesis
passes actual gameplay; do not repeat these three configurations unchanged.
