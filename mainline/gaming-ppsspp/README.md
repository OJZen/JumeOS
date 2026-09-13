# R46H PPSSPP libretro candidate

Status: **HOST + P2 + DEVICE GAMEPLAY FRAME/PCM PASS / PSP-SPECIFIC FOLLOW-UP DEFERRED**

This directory owns the smallest PSP runtime addition after p2 v0.12. It pins
PPSSPP v1.20.4 and produces one AArch64 libretro bundle; it does not modify the
current card, BOOT, p1, p2, p3 or imported ROMs.

## Build

```sh
PYTHONDONTWRITEBYTECODE=1 mainline/gaming-ppsspp/build-core.py build
PYTHONDONTWRITEBYTECODE=1 mainline/gaming-ppsspp/build-core.py validate
```

`source-lock.json` owns the exact upstream tag, commit, tree, 29 recursive
submodule commits, build options, core ABI, asset manifest and final archive.
The Dockerfile pins the accepted Debian 13 base plus package versions. Source is
mounted read-only. Two clean builds produced the same 19,260,809-byte archive:
`8940315762f7abb91624d009f13cddafdb1ab644e41f8e4bf3be70a5a875bc04`.

The archive contains the stripped 17,840,344-byte core with SHA-256
`f39819580dc5a867bd8674eef37b13c2eef328824b1aabe7ed4dc98af61bf3a7`
and exactly 189 git-tracked upstream assets under `PPSSPP/`. This follows the
[libretro PPSSPP setup contract](https://github.com/libretro/docs/blob/master/docs/library/ppsspp.md).
No proprietary PSP font is imported; visual Chinese glyph coverage remains an
attended check.

## Content boundary

Exact Debian RetroArch 1.20, null video/audio/input and the software backend
loaded all six retained PSP files through kernel initialization and graphics
startup. `content-audit.json` owns their sizes, hashes, IDs and the proof
boundary. The old 27-entry gamelist references only six files now present, so
the p2 integration must publish a filtered gamelist rather than 21 dead entries.

The device profile will use OpenGL/GLES at native 480x272, JIT defaults and p2
save/state storage. It must set a deterministic RetroArch system directory so
the version-matched `PPSSPP/` assets are found. Rewind stays disabled because
the core does not support it.

## Remaining gate

Exact p2 v0.15 launched the loose `我的世界PSP.PBP` through ES-DE. It ran for 639
seconds with a valid Chinese menu frame, PCM running, clean service state and no
kernel fault. PPSSPP changes the process `comm` to `Main`, exposing a bug in the
installed screenshot guard. P2 v0.16+ carries the versioned anchored guard;
current regression and attended checks belong to the
[v0.17 device record](../rootfs-debian13-gaming-v17/README.md#persistent-device-evidence).
Initial attended gameplay and the subsequent passing dual-stick RetroArch smoke
are recorded there. The user deferred PSP-specific investigation for streaming;
ISO behavior, game-specific controls, saves and sustained pacing remain open.
