# R46H Debian 13 gaming p2 v0.16

Status: **HOST + P2 MEDIA + DEVICE INFRASTRUCTURE PASS / ES-DE SCOPE FAIL**

This is the narrow runtime-fix successor to exact p2 v0.15. It changes only
the remote key hold from 100 ms to the target-proven 10 ms, lets the guarded
screenshot helper recognize ES-DE plus one RetroArch child by anchored command
line, and attempts to hide the known-failing Dreamcast entry from ES-DE. The
Flycast core, Dreamcast ROM mapping, gamelist and media remain installed for
later diagnosis.

All emulator cores, ROM links, media, settings, services and the accepted
no-redundant-fill ES-DE profile otherwise stay byte-exact. BOOT, p1 and p3 stay
outside the image and write plan.

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v16.py validate-inputs
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v16.py build
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v16.py validate
```

The offline composer writes no block device. It starts from the exact published
v0.15 image, compiles the 10 ms helper with the pinned AArch64 builder, checks
that it is byte-identical to the device-tested candidate, and replaces only
eight bounded p2 files plus the filesystem UUID/label. No network is used.

Two builds from source commit
`42346b61dcf7837cc46b49d4bd6f3da4f5d7802b` were byte-identical, followed by
a separate post-publish validation:

- image SHA-256: `21cdfa3af3b96b6233decdc3ca4f8475c0eba946503045a4e86c21c50b8374c4`
- `BUILD-INFO` SHA-256: `90a5c97848d1942b40981c975fbcbdcc93073b80bdc619ab8ebb7ab79035828a`
- consolidated receipt SHA-256: `38dba41fdec1846b7476e29c045381040749e75a4c341d60e3e068578fcfa88f`

## P2 media pass

On 2026-09-05, audit session
`session-20260905T054433Z-7116-da4eccf5-2dad-45f7-b56c-2fe45f837812`
fixed that insertion as `/dev/disk12`. Its complete 10,716,877,312-byte
pre-write p2 clone `p2-v0.15-before-v0.16-20260905.ext4`, the host clone rehash
and a separate raw p2 read all matched at
`60d26bc9db04725ebd91e725b23ef655c26d72ea546093213643910d3d8a7347`.

Pinned plan SHA-256
`290abaf1498c52cd70f92f59eab6d9ca4afeaa51c97700eabe05e142b4dc9f43`
opened only p2. Deploy session
`session-20260905T055042Z-35690-4af55e12-7996-495e-88f0-606d728fb586`
wrote the published image. Its transaction readback and a separate reopened raw
p2 hash both equal the source SHA-256. `WRITE_COMPLETE` and `safe_to_boot=yes`
passed; the retained write receipt SHA-256 is
`28017f4195c3e95c00acb175d0d6246324b6568e293505f61d3dc61f42b8cf18`.

BOOT matched before/after at
`07873e6b9af82a69f9f98ae125b6f45898abc2e4ee7202ddc8d67a3b23d513c1`.
Its active v0.17 script, exact v0.15 Image and v0.17 DTB anchors passed before
the write. The fixed prefix remained exact, p3 stayed unmounted and outside the
plan, and macOS confirmed eject.

## Physical result

On 2026-09-05, exact p2 v0.16 cold-booted with the expected identity and passed
base smoke, SDR104/150 MHz, read-only `/roms`, clean health, guarded ES-DE and
Game Gear screenshots, and an exact right/left 10 ms menu roundtrip. The normal
ES-DE-plus-RetroArch process topology also passed the screenshot guard.

The product gate failed: ES-DE loaded 14 systems and exposed Dreamcast. Its
custom file is complementary by default, so removing Dreamcast from that file
did not suppress the bundled definition. A temporary root-level
`<loadExclusive/>` candidate then loaded only the 13 custom systems, hid
Dreamcast and passed ES-DE, Game Gear and PPSSPP (`comm=Main`) captures. The
candidate binds were removed, exact v0.16 restored, health remained clean and
the device powered off normally.

[P2 v0.17](../rootfs-debian13-gaming-v17/README.md) owns the persistent fix.
Media proof does not establish R46H behavior. LCD motion, audible output,
physical controls and save persistence remain attended gates.
