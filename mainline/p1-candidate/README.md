# R46H v0.9 offline BOOT candidate

`build-v09-p1-candidate.py` accepts a complete, regular-file clone of BOOT p1
and the completed **install-modules-only** v0.9 EASYROMS bundle.  It never opens
a block device and only mutates a private copy with `mtools` in the pinned
Debian snapshot builder.  The transaction removes the four retired v0.2
candidate files, keeps the active v0.8 boot path and every other file
byte-identical, and adds only the bundle's deterministic v0.9 gzip Image and a
versioned one-shot boot script.  The existing v0.8 DTB is reused only after the
bundle's v0.9 package DTB is proved byte-identical to that audited v0.8 DTB.

The builder intentionally contains no hash of a particular v0.9 build output.
Instead it validates the generated bundle's exact `STAGE-SOURCES.sha256`
coverage, `DEPLOY-MANIFEST`, action allowlist, canonical package tar, Image and
DTB relationships.  It then reuses the canonical EASYROMS parser to prove the
package's complete checksums and archive shape and to bind
`source_git_commit`/`source_snapshot_sha256` to the current clean `HEAD`.  The
running EASYROMS generator and P1 builder must both match their exact executable
blobs in that `HEAD`.  This avoids a provenance cycle: tooling can be committed
first, and the canonical package and bundle can then be rebuilt from that clean
commit without updating a tracked artifact hash.

Because the Docker/mtools pass is comparatively long, the complete bundle,
package, repository snapshot and running-builder proof is repeated immediately
before publication and must match the first proof byte-for-byte.  Publication
uses the canonical generator's cross-directory atomic no-replace rename plus
private/published inode checks.  If another process creates the requested
output name, the build fails closed and neither replaces nor removes the
competing path.

The input clone must be exactly 117,440,512 bytes and live below
`mainline/out`.  Temporary extraction and Docker build state stays below
`mainline/out/.cache`; a successful result is atomically published below
`mainline/out/r46h-v09-p1-candidates` by default.  The build receipt records the
complete before/after file manifests, the exact two-file addition/four-file
removal diff, both FAT check logs, free space, all pinned source hashes, and the
full candidate image SHA-256.

The default bundle path is
`mainline/out/r46h-easyroms-v0.9-adc-joystick-fix`.  To use an explicitly
reviewed bundle directory below `mainline/out`:

```sh
python3 mainline/scripts/build-v09-p1-candidate.py \
  --input-p1 /absolute/path/below/mainline/out/live-p1-clone.img \
  --bundle-dir /absolute/path/below/mainline/out/r46h-easyroms-v0.9-adc-joystick-fix
```

After reviewing that receipt, generate a session-bound Card Agent plan with:

```sh
python3 mainline/scripts/generate-v09-p1-write-plan.py \
  --candidate-dir /absolute/path/printed/by/the/builder \
  --device /dev/diskN \
  --confirm-device /dev/diskN
```

The plan contains one full-partition `boot` operation and is bound to profile
`hl-r46h-v22-g92-31719424000-v1`. Its required `target_sha256_before` is the
candidate receipt's full `base_image_sha256`, so the live p1 must still be the
exact image cloned for this build. The generator only validates the device path
as text; Card Agent claims the live card, hashes the pinned p1 FD in full, and
rejects a mismatch before publishing `WRITE_IN_PROGRESS` or writing any byte.

Start a fresh deploy session with the printed plan and hash:

```sh
mainline/scripts/start-r46h-card-agent.sh \
  --device /dev/diskN \
  --profile-id hl-r46h-v22-g92-31719424000-v1 \
  --deploy \
  --write-plan /absolute/path/from/WRITE_PLAN \
  --write-plan-sha256 64-lowercase-hex-from-WRITE_PLAN_SHA256
```

In a second terminal, prove the live profile, unmount the card, and capture a
full p1 pre-write hash. It must equal `base_image_sha256` in the candidate
`BUILD-STATUS.json`; the Agent independently enforces the same comparison on
its pinned target FD before executing the only operation:

```sh
mainline/scripts/r46h-cardctl.sh card-info
mainline/scripts/r46h-cardctl.sh unmount
mainline/scripts/r46h-cardctl.sh hash-raw boot
mainline/scripts/r46h-cardctl.sh --json execute-write write-v09-one-shot-boot-p1
mainline/scripts/r46h-cardctl.sh unmount
mainline/scripts/r46h-cardctl.sh hash-raw boot
```

The final p1 hash must equal the candidate image hash, and the response's
`details.write_status` file must contain both `state=WRITE_COMPLETE` and
`safe_to_boot=yes`.  The active v0.8 files are still verified from the
candidate build receipt; the added v0.9 boot script is for a UART-interrupted,
RAM-only U-Boot session and must never be persisted with `saveenv`.
