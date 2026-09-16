# R46H ES-DE frontend candidate

This directory owns the first ES-DE replacement candidate for the accepted
v0.17/v0.15 + exact p2 v0.7 + imported p3 card. It is a p2-only successor to
the accepted Ozone/FBNeo feature; it does not change BOOT, p1 or p3.

## Status and scope

Status: **HOST + POWER-BACKED TRANSIENT TARGET + REPRESENTATIVE GAME PHYSICAL
PASS / PERSISTENT PROMOTION + VISUAL PROFILE LCD MOTION OPEN.** The guarded
install, exact runtime identity, 7-system discovery,
3,417 media links, corrected controller GUID, strict-SSH screenshots, exact
Ozone rollback/reinstall and zero-error health pass on the current card. An
unattended DRM probe measured the unmodified bundled theme at 15.0 FPS. The
[visual profile](../gaming-es-de-visual/README.md) keeps its original system art
and variants, selects its native OLED palette and bounds the expensive carousel;
the settled system view measures 60 FPS. A target A/B of the locked idle-pacing
patch cut settled no-video CPU from 51.16% to 25.08% and GPU temperature from
82.45 C to 72.34 C; a remote input restored full-rate rendering immediately.
The patched archive and embedded executable hashes reproduce on host. A later
power-backed transient bind held the patched service to 23.57% CPU over 60
seconds; strict DRM captures before and after remote Right changed from SHA-256
`d569468527351804efaa8ca3b42c88035089414c368b837ebf2c3debd02a3c13` to
`a5feae1e074b220d31ed8c9cea39b350a7cf61ef48bbe101c6d6e1f89743773a`.
The installed executable, service and temporary access were restored exactly and
final health passed. Persistent promotion and physical patched LCD motion remain open.

Version 0.1 exposes only content backed by cores already present on the accepted
p2:

| ES-DE directories | Runtime | Current evidence |
| --- | --- | --- |
| `nes`, `famicom` | Debian Nestopia | ES-DE controls, picture, audio and return passed |
| `gb`, `gbc` | Debian Gambatte | Host contract only |
| `gba` | Debian mGBA | Host contract only |
| `nds` | Debian DeSmuME | Experimental; performance pending |
| `neogeo` | Accepted pinned FBNeo subset | ES-DE gameplay passed; brief green startup open |

Unsupported p3 directories are deliberately absent from `/home/ark/ROMs`, so
ES-DE cannot advertise a system without an installed emulator. Later host-only
successors add full FBNeo Arcade/CPS, [PPSSPP/PSP](../gaming-ppsspp/README.md)
and [Flycast/Dreamcast](../gaming-flycast/README.md); none extends the accepted
physical baseline until its p2 write and attended checks pass. SNES/SFC, Mega
Drive/Genesis and PSX remain the next unimplemented core wave.

## Design contract

- ES-DE 3.4.1/r51 is pinned by tag, commit, tree, source size and SHA-256.
- A product allowlist uses root-level `<loadExclusive/>`. Without it, ES-DE
  complements the custom file with bundled systems, so deleting one custom
  entry does not hide the bundled definition.
- It is built natively for AArch64 with GLES, `DEINIT_ON_LAUNCH`, no updater and
  no hardware video decoding. The install prefix is `/opt/r46h/es-de`.
- After one second without input, the no-video main loop sleeps 33 ms after each
  swap. Input and video playback keep the original full-rate path.
- The runtime library closure is compared with the exact accepted p2 package
  set. Mesa/DRM, glibc and libraries already owned by RetroArch stay on p2.
- `/roms` remains read-only. `/home/ark/ROMs` contains only bounded symlinks;
  saves, states, ES-DE settings and metadata stay on p2.
- RetroArch runs launched by ES-DE use a dedicated mutable core-options file;
  they cannot rewrite the byte-locked Ozone/FBNeo options baseline.
- Original-card `gamelist.xml` files are read in legacy mode and never rewritten.
  A host-generated manifest maps compatible original images, marquees and videos
  to p2 symlinks; missing media is reported and skipped.
- Frontend navigation/video audio is initially disabled to avoid competing with
  emulator audio. The accepted RK817 mixer selection is restored on every exit.
- The bundled `linear-es-de` theme is replaced during guarded staging by the
  fixed `r46h-theme.xml`: its original console art and game-list variants remain,
  while the system carousel is bounded to three animated items. The native OLED
  palette avoids the fill-rate-heavy tiled background; no new assets are added.
- The guarded KMS screenshot feature remains independent. Its bounded
  [ES-DE compatibility overlay](../gaming-remote-screen-es-de/README.md) adds
  linear ARGB8888 and exact ES-DE process support without restarting either
  frontend.
- `Select + X` still opens Ozone inside a game. `Select + Start` exits RetroArch
  and returns to ES-DE.

The original ArkOS theme is not copied: legacy EmulationStation theme formats
are not an ES-DE compatibility contract. Version 0.1 uses the optimized bundled
`linear-es-de` profile, Chinese UI, a 128 MiB texture budget and no screensaver.
ES-DE's built-in GPU statistics remain available for attended diagnosis; there
is no resident FPS logger.

## Host build

Large sources, Docker contexts and extracted files stay below
`mainline/out/.cache/r46h-es-de/`.

```bash
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/gaming-es-de/build-runtime.py build

PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/gaming-es-de/generate-legacy-media-links.py \
  --rom-root mainline/out/.cache/r46h-original-card-import-20260826/easyroms \
  --output mainline/out/.cache/r46h-es-de/legacy-media-links.tsv

PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/gaming-es-de/build-runtime.py payload
```

`source-lock.json` owns source, patch, build and runtime identity. The build runs
`ES-DE --version` after recreating the accepted p2 package state;
`build-runtime.py validate` rechecks the locked archive, resources, recorded
version and AArch64 ELF identity without requiring target libraries on the host.

## Guarded target transaction

The payload is staged only at `/run/r46h-gaming-es-de-v0.1`. Its
installer verifies the exact kernel, p2 identity, read-only p3, accepted Ozone
receipt/config/launcher, every payload file and the current frontend process.
It stops Ozone only after the runtime and rollback state are ready.

On success it replaces only the frontend unit and adds:

- `/opt/r46h/es-de/`;
- `/etc/r46h/es-de-systems.xml` and `/etc/r46h/es-de-retroarch.cfg`;
- `/usr/local/sbin/r46h-es-de-{ui,rollback}`;
- p2-owned application data and symlinks under `/home/ark`;
- `/var/lib/r46h-gaming-es-de/v0.1` and one receipt.

The installed rollback helper restores the byte-exact Ozone unit, verifies and
removes the exact runtime and feature links, then restarts Ozone. User-mutated
`/home/ark/ES-DE` settings/logs are intentionally preserved; p1, p3, the
accepted RetroArch config/core, volume service and base remote-screen feature
are outside both transactions. Roll back the ES-DE screenshot overlay before
rolling this frontend back to Ozone.

## First physical gate

Do not update the experiment ledger before all corresponding observations pass:

1. guarded install reports one ES-DE process, zero ext4 errors and no failed
   units;
2. screenshot shows the 1024x768 OLED visual profile; the original-art system
   carousel measures about 60 FPS and its LCD motion is accepted once by the
   operator;
3. D-pad, A/B, both sticks, Start/Select and shoulder navigation behave once;
4. launch one NES title and Metal Slug, verify picture/audio, `Select + X`, then
   `Select + Start` return without a frontend restart;
5. inspect at least one migrated image and one missing-media fallback;
6. warm reboot preserves ES-DE settings and hardware volume;
7. rollback restores exact Ozone, then reinstall idempotence is evaluated;
8. finish with health checks, `sync` and controlled poweroff.

GB/GBC/GBA and especially NDS remain system-specific compatibility work even
after the frontend gate passes. A menu appearing is not emulator proof.
