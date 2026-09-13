# R46H Genesis Plus GX component

Status: **HOST + DEVICE FRAME/PCM + ATTENDED SAMPLES PASS / SAVES OPEN**

This adds only the Sega Game Gear content that exists on imported p3: the
Debian 13 arm64 Genesis Plus GX core, one ES-DE system, 105 audited ZIPs and
105 existing cover images. ROMs remain external and read-only.

The exact Debian package is locked in `package-lock.json`. Its upstream license
is non-commercial, so keep the included copyright file with the installed core
and do not treat this component as commercially redistributable.

```sh
curl -L -o mainline/out/.cache/r46h-genesisplusgx/libretro-genesisplusgx_1.7.4+git20221128-2_arm64.deb \
  'https://deb.debian.org/debian/pool/non-free/g/genesisplusgx/libretro-genesisplusgx_1.7.4%2Bgit20221128-2_arm64.deb'

PYTHONDONTWRITEBYTECODE=1 mainline/gaming-genesisplusgx/generate-filtered-gamelist.py \
  --rom-root mainline/out/.cache/r46h-original-card-import-20260826/easyroms \
  --base-media mainline/out/r46h-gaming-flycast-content-v0.1/legacy-media-links.tsv \
  --output-root mainline/out/r46h-gaming-genesisplusgx-content-v0.1
```

The host audit loaded all 105 ZIPs for 60 frames through RetroArch 1.20 and
unloaded cleanly without firmware. Two files switch to the core's 256x192
Master System-compatible geometry; the remaining 103 report native 160x144.
On exact p2 v0.15, `001.zip` ran for 748 seconds with a valid captured game
frame, PCM running and no service restart or kernel fault. Initial attended
v0.17 samples and the missing save-menu investigation now belong to the
[v0.17 device record](../rootfs-debian13-gaming-v17/README.md#persistent-device-evidence).
Save/reboot persistence and sustained pacing remain open.
