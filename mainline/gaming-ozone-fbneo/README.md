# R46H Ozone and FBNeo Metal Slug v0.1

Status: **HOST + TARGET + PHYSICAL PASS / MILD PACING OPEN**

This is a guarded p2-only successor to the accepted exact gaming p2 v0.7. It
replaces RGUI with Ozone, adds one pinned AArch64 FBNeo Neo-Geo core, and
publishes a one-entry `SNK - Neo Geo` playlist for the imported original-card
`mslug.zip`. Its separately owned
[remote-screen successor](../gaming-remote-screen/README.md) is not part of this
transaction and is already rebased on the exact accepted frontend files.

## Change boundary

- `retroarch.cfg` differs from the accepted file only by `menu_driver =
  "ozone"`, `video_driver = "gl"` and `content_directory = "/roms"`.
  The first target attempt proved that Debian RetroArch silently falls back to
  RGUI when Ozone is paired with the accepted SDL2 video driver. A bounded
  target probe then loaded Ozone's fonts, sidebar, themes and Neo-Geo icons via
  RetroArch's `gl` driver on the KMS/EGL Panfrost path.
- The playlist opens `/roms/neogeo/mslug.zip` directly with the versioned core;
  it does not scan or rewrite p3.
- `r46h-game-ui fbneo-mslug` is a direct diagnostic path. The normal service
  starts Ozone through RetroArch's OpenGL ES-on-KMS path; audio and input remain
  on the accepted product path.
- The exact per-core options select the bundled UniBIOS 3.3 in MVS mode. Exact
  target captures showed that the stock MVS BIOS emits the reported green
  garbage frames, while UniBIOS reaches its normal logo without them. The
  accepted 32-bit color path remains unchanged.
- The candidate volume-key service owns `/var/lib/r46h-volume/level`, writes a
  bounded `0..201` value atomically after every key press, and restores it at
  service start. The frontend runner no longer forces or restores volume; it
  continues to own only the speaker/headphone mux route.
- Install and rollback are bound to the exact p2 v0.7 UUID, v0.15 kernel,
  predecessor receipt/config/runner/volume service, read-only ROM mount,
  ROM/BIOS hashes, core-info file and Ozone assets.
- The transaction changes only its named p2 files. It does not write p1, p3,
  BOOT, U-Boot environment or packages.

The playlist format and Ozone asset layout follow the official
[Libretro playlist](https://docs.libretro.com/guides/roms-playlists-thumbnails/)
and [Ozone](https://docs.libretro.com/guides/ozone/) documentation.

## Pinned build and host evidence

`source-lock.json` is the single owner of the source archive, FBNeo commit/tree,
builder image, flags and output identity. The build intentionally selects
`SUBSET=neogeo`; passing the obsolete ARM32 `HAVE_NEON=1` flag on AArch64 is
forbidden.

The 2026-08-31 host gate passed:

- two clean extractions and the checked-in build entry produced byte-identical,
  stripped AArch64 cores;
- output is `9,007,520` bytes with SHA-256
  `8bb17a551f3eeeb384ab00a5c5375d30eb63807afe5b6c1ba1d3f78220732bdb`;
- exported libretro entry points and the five dynamic dependencies match the
  lock;
- all nine Metal Slug members, sizes and CRCs match the pinned FBNeo driver;
- exact Debian RetroArch 1.20 loaded the retained ROM and BIOS for five seconds
  with null I/O, reported `Metal Slug - Super Vehicle-001`, and logged no ROM,
  BIOS or core error.

These are host facts. On 2026-09-01 the guarded corrected install passed on the
exact current p2. Receipt/files, services, read-only ROM input and filesystem
health matched; target frames 120/180/210 showed clean UniBIOS output and frame
480 advanced normally. Saved levels 169 and 201 each restored across a controlled
service restart. The operator then accepted clean LCD startup and Metal Slug
gameplay. Hardware keys changed 201 to 169; after warm reboot the state file and
both RK817 mixer channels restored to 169, both services were active with zero
restarts, and ext4/failed-unit counts stayed zero. Mild pacing remains open.

Build and validate from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/gaming-ozone-fbneo/build-core.py build

PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/gaming-ozone-fbneo/build-core.py validate

R46H_TEST_TMPDIR=mainline/out/.cache/r46h-tests \
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/tests/test-r46h-gaming-ozone-fbneo.py
```

The ignored core output is
`mainline/out/r46h-gaming-ozone-fbneo-v0.1/fbneo_neogeo_libretro.so`.

## Guarded target install

Rediscover the live R46H identity each session. Stage exactly these ten
root-owned mode-0600 files under mode-0700
`/run/r46h-gaming-ozone-fbneo-v0.1`:

- `install.sh`
- `rollback.sh`
- `retroarch.cfg`
- `r46h-game-ui`
- `r46h-volume-keys`
- `r46h-volume-keys.service`
- `FinalBurn Neo (neogeo subset).opt`
- `fbneo_neogeo_libretro.so`
- `SNK - Neo Geo.lpl`
- `FBNEO-LICENSE.txt`

Then run the staged installer with its actual hash:

```sh
sudo /bin/bash /run/r46h-gaming-ozone-fbneo-v0.1/install.sh \
  --installer-sha256 INSTALLER_SHA256
```

The transaction records exact base files in root-only rollback state, stops
RetroArch and the volume listener, atomically publishes the named files, starts
the persistent volume service, then restores the frontend. Any failure restores
the exact accepted files; if automatic restore itself fails, services remain
stopped and rollback state is retained.

## Physical acceptance contract

The 2026-09-01 run accepted items 1, 2, 4, 5 and the health portion of 6. Item 3
remains a pacing-quality follow-up; do not repeat the accepted generic checks:

1. Ozone appears at boot and D-pad/A/B navigate it normally.
2. The `SNK - Neo Geo` sidebar opens directly to `Metal Slug`; launching it
   shows a clean UniBIOS boot without the prior green/garbage interval, then the
   game rather than a black screen or missing-ROM message.
3. Intro/gameplay video and speaker audio remain smooth for at least two
   minutes; Start, Select, D-pad and action buttons work.
4. `Select + X` returns to Ozone, and a second launch works without a frontend
   restart.
5. Change volume, restart once, and confirm the same audible level is restored.
6. Confirm exact p2 identity, read-only `/roms`, zero ext4 errors, zero failed
   units, unchanged frontend restart count, then `sync` and controlled poweroff.

If the playlist path is the only failure, test `sudo r46h-game-ui fbneo-mslug`
before changing the core. Record physical evidence in the R46H ledger only
after the corresponding observation.

## Rollback and licensing

```sh
sudo /usr/local/sbin/r46h-gaming-ozone-fbneo-rollback
```

Rollback restores the exact accepted p2 v0.7 RGUI config, runner and volume
service, then removes only this feature's core, options, playlist, volume state,
license, receipt and rollback state.

FBNeo has non-commercial and source/publication conditions. The exact upstream
license is retained as `FBNEO-LICENSE.txt` and installed beside the binary.
This feature does not distribute a ROM; the Metal Slug and Neo-Geo BIOS files
remain the user's imported original-card p3 content.
