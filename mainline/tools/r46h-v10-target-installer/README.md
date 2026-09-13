# R46H v0.10 target-side one-shot installer

This small, versioned Linux/aarch64 program installs only the **inactive**
v0.10 Image, DTB and one-shot boot script from the rebuilt fast-card EASYROMS
partition into BOOT.  It never changes active `boot.ini`, the active v0.8
Image/DTB, the root filesystem, MBR, g92 prefix or U-Boot environment.

The tool exists to avoid another remove/write/reinsert cycle for the current
62.5 GB card.  It is not a generic updater.  Its production build pins the
exact fast-card geometry, prefix, PARTUUIDs, base p1 bytes, v0.8 anchors, v0.9
files being retired and v0.10 p3 payload bytes.

## State machine

- **base**: exact v0.8 active anchors plus the inert v0.9 candidate;
- **partial**: exact journal plus a permitted subset of old/new/staging files;
- **installed**: exact v0.8 active anchors plus the complete inert v0.10
  candidate and no journal or v0.9 candidate.

The canonical base is the full BOOT image with SHA-256
`5784db8171c096b9f6289bcb7914d5d7f05051a50434149080660544f1ab81f5`.
Its required top-level directories are exactly `consoles`,
`System Volume Information` and `.Spotlight-V100`; `.fseventsd` is not part of
this base.  Directory names and entry types are checked before the journal is
created, so historical macOS metadata must not be added to the contract merely
because it appeared on a different automounted volume.

The boot script is published last.  Every publication is file-fsynced,
filesystem-synced and no-replace renamed.  A power loss or `SIGKILL` after the
journal is durable leaves a recoverable partial state; it never selects v0.10
for ordinary boot.  `HUP`, `INT` and `TERM` cancel before the write commit and
are ignored after it so a terminal disconnect cannot interrupt the FAT update.

## Build

Commit the complete source scope first.  The builder refuses dirty or
untracked scoped files, copies Git `HEAD` blobs to a private external snapshot,
uses the pinned arm64 Debian image, runs host tests/Clippy/rustfmt plus Linux
tests and a Linux `-Dwarnings` check, performs two clean release builds and
publishes only if the AArch64 PIE binaries match byte-for-byte:

```sh
python3 mainline/scripts/build-r46h-v10-target-installer.py build
python3 mainline/scripts/build-r46h-v10-target-installer.py validate
```

Private build work and Cargo targets stay below `mainline/out/.cache` on the
external repository volume and are removed after success or failure.  The
small shared Cargo download cache is retained.  The immutable generation and
`CURRENT` pointer are under `mainline/out/r46h-v10-target-installer`.

## Target use

The binary must be transferred over the captured serial session, checked
against the immutable generation digest, installed as root-owned mode `0700`
at exactly `/run/r46h-v10-one-shot-installer`, and run from the v0.8 fallback.
`/run` is tmpfs, so neither tool nor transfer payload persists to p2.

Run `--preflight` first.  It performs the full identity/source/base checks but
does not mount BOOT writable:

```sh
/run/r46h-v10-one-shot-installer --preflight
```

Only an exact base-state PASS authorizes the explicit installation command:

```sh
/run/r46h-v10-one-shot-installer --install \
  --confirm install-v0.10-one-shot-keep-v0.8-active
```

If and only if a later run reports the exact recoverable journal state, use
the same confirmation with `--recover-partial`.  Never guess recovery, delete
the journal manually, replace active `boot.ini`, or run `saveenv`.

After an installed-state PASS, v0.10 is still inert.  At the verified U-Boot
prompt the already accepted v0.9 pattern is reused with the v0.10 script:

```text
mmc dev 1
load mmc 1:1 0x02000000 boot.ini.v0.10-adc-full-range
if itest ${filesize} -eq 0x580; then echo R46H_V10_SCRIPT_SIZE_PASS; else echo R46H_V10_SCRIPT_SIZE_FAIL; fi
source 0x02000000
```

`0x580` is 1,408 bytes, the rendered script installed by this tool.  Do not
run `source` unless the size marker passes.  There is no `saveenv`; an ordinary
reset continues to read the unchanged v0.8 `boot.ini`.

The first v0.10 hardware run is accepted only for the explicitly documented
kernel/input/Panfrost gates.  It does not require repeating the completed v0.9
range experiment, framebuffer colour bars, louder speaker playback or a full
125 GB media audit.

## Matching v0.10 modules on the fast card

The first one-shot boot proved that the v0.10 kernel and built-in ADC fix boot,
but also proved that `/lib/modules/6.12.99-r46h-mainline-v0.10-adc-full-range`
was absent.  The same immutable binary therefore has a second, independent
module-only state machine.  It is deliberately bound to all of the following:

- the running v0.8 fallback release and healthy `mmcblk0p2` root filesystem;
- the exact 62,534,975,488-byte fast-card layout, g92 prefix and installed BOOT
  hash `ef62200b...fc88`;
- the exact read-only p3 archive (size 33,258,814, SHA-256
  `c4350520...bc780`);
- the unchanged v0.8 module tree and the expected 1,276-module v0.10 tree.

`--modules-preflight` copies the archive only into private `/run` tmpfs, hashes
it, checks both BOOT and the existing v0.8 modules, and reports `ready`,
`partial`, `receipt-recovery`, or `installed`.  It makes no persistent change:

```sh
/run/r46h-v10-one-shot-installer --modules-preflight
```

Only an exact `ready` PASS authorizes installation:

```sh
/run/r46h-v10-one-shot-installer --install-modules \
  --confirm install-v0.10-modules-from-fast-card
```

The archive is mounted from p3 read-only, frozen to `/run`, then p3 is
unmounted before extraction.  The complete tree is extracted into a fixed
root-owned staging directory below `/lib/modules`, fully hashed, synced and
published with `RENAME_NOREPLACE`; the v0.8 tree is rehashed before and after.
The persistent completion receipt is published last at
`/var/lib/r46h/v0.10-modules-installed`.  BOOT and EASYROMS are never opened
writable in this mode.

A power loss can leave the fixed staging directory or receipt stage.  In that
case ordinary v0.8 boot remains usable and the next preflight reports
`partial`.  Do not remove the stage manually; after inspecting the failure,
run the explicit recovery form with the same confirmation token:

```sh
/run/r46h-v10-one-shot-installer --recover-modules \
  --confirm install-v0.10-modules-from-fast-card
```

This path does **not** consume the revoked small-card TARGET-TRUST receipt or
the old geometry fields in the inert v0.10 p3 bundle.  Only the exact archive
bytes are treated as input, under the fast-card checks compiled into this
binary.

## Accepted 2026-08-15 hardware result

The committed installer generation from `5f4f7e7` passed module preflight and
then published the exact module tree SHA-256
`a70796c050de93c4c212180addf54a17efe7732d355db2b52d0bfcab6c56cc16`.
The persistent receipt SHA-256 is
`5e05ab382231a18f44701772c9a9c4b0df504d863b9b9739696d17207203afae`.
The v0.8 module tree and installed p1 hash remained exact before and after.

The following one-shot boot loaded matching `rtl8xxxu`, `rk817_charger` and
`hantro_vpu` vermagic, enumerated RK817 audio, registered the Hantro encoder and
decoder nodes, passed the derived v0.10 Panfrost base gate, found 10 BSSes in a
passive unassociated scan, and ended with zero failed units, zero ext4 errors
and zero bounded kernel-fault matches. An ordinary reboot selected v0.8 with
both module trees and the completion receipt still present, after which the
device powered off cleanly.

This closes module installation and v0.10 boot/enumeration. It does not close
full ADC travel, audible speaker output, Wi-Fi association/throughput or the
Hantro codec data path. Do not rerun this installer to investigate those
independent items.
