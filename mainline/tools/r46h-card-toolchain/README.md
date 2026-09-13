# R46H Card Toolchain

This directory is the version-2 foundation for replacing the growing set of
host-side card scripts with one reviewed transaction engine.

The build driver requires Python 3.10 or newer.

## Current Release Boundary

Version `0.2.0` adds a deliberately narrow macOS read-only certification path:

- the Rust core validates strict v2 profiles and plans, pins source file
  handles, journals every state transition, writes through a regular-file
  simulator, performs readback, and publishes a structured receipt;
- `inspect-legacy` reads v1 JSON as opaque evidence and never converts it into
  an executable plan;
- macOS can discover eligible whole USB media through IOKit/Disk Arbitration,
  unmount and claim one exact attachment, open one `O_RDONLY|O_NOFOLLOW` raw
  descriptor, verify the profile-bound prefix/MBR/partition geometry,
  filesystem signatures and identifiers, and eject while the claim is held;
- this read-only command has no write-capable trait or descriptor, emits no
  `safe_to_boot`, and cannot mint a destructive authorization;
- native writes and all Linux/Windows physical-media access remain
  `unsupported`. The regular-file simulator remains the only write path.
- Windows is compile- and simulator-compatible. Parent-directory
  flush semantics are not certified there, so no power-loss durability claim is
  made for Windows evidence publication.

The existing audited Swift Card Agent and versioned deployment scripts remain
the canonical physical-media path until each native backend completes the
certification gates in [ARCHITECTURE.md](ARCHITECTURE.md).

## Build

All transient files default to the external repository volume:

```sh
mainline/scripts/build-r46h-card-toolchain.sh
```

`R46H_CARD_CACHE_ROOT` may override the cache, but it must be absolute. On
macOS the driver rejects a cache proven to reside on an internal disk. The
strict build requires a clean tracked toolchain source scope, captures that
commit into a private snapshot, uses a per-build target, and forces every gate
offline. Unrelated historical evidence elsewhere in the repository is not
deleted and does not block the build.

Publication uses an immutable generation selected by one atomic `CURRENT`
record under a platform-specific directory:

```text
mainline/out/r46h-card-toolchain/bin/<os>-<arch>/CURRENT
mainline/out/r46h-card-toolchain/bin/<os>-<arch>/builds/<generation>/
  r46h-card[.exe]
  BUILD-RECEIPT.json
  SOURCE-MANIFEST.json
  SHA256SUMS
```

Consumers read `CURRENT` once, verify its `sha256sums_sha256`, and then use
only that immutable generation. `validate-release` additionally requires the
tracked build scope to be clean at the current `HEAD`, rejects links anywhere
in the release ancestry, and recomputes every source-manifest record from that
commit's raw Git blobs with replacement objects disabled. The scoped
`.gitattributes` rules keep those inputs LF-normalized on Windows. Advancing
`HEAD` intentionally invalidates an older
`CURRENT` until a new generation is built. The receipt proves first-party
source/output integrity and records `hermetic=false`: the installed Rust stable
toolchain, shared Cargo archive/index cache, system linker, and publisher
identity are not claimed to be reproducible or authenticated. Windows
publication is logically atomic, but parent-directory durability remains
uncertified.

The build is locked and offline by default. `--online` only fetches packages
already pinned by `Cargo.lock`; it does not update the lock file.

Linux and macOS can use the thin POSIX launcher above. Windows uses the same
Python driver directly from PowerShell:

```powershell
python mainline/scripts/r46h_card_toolchain.py build
python mainline/scripts/r46h_card_toolchain.py env --format powershell
python mainline/scripts/r46h_card_toolchain.py clean
```

On every platform, set `R46H_CARD_CACHE_ROOT` to an absolute path on the
intended external volume when the repository itself is not already there.
Linux rejects the root filesystem and Windows rejects `SystemDrive` by
default. Hosted CI may use the explicit `--allow-system-storage-for-ci` flag
only when `CI=true`; that exception is written into the build receipt.

Use the narrow cleanup after verification:

```sh
mainline/scripts/clean-r46h-card-toolchain.sh
```

This removes only the legacy shared `target` and private work directories. New
strict builds keep their target in the automatically removed private work
generation and copy only Cargo archives/index metadata into the reusable
cache; dependency source extraction remains private. Add `--all` to also
remove that cache. Release files are never removed.
Direct Cargo commands do not participate in the driver's build/clean lock;
stop them before cleanup. If a cache tree changes during deletion, cleanup
fails closed with a temporary-error status and must be retried after the writer
has stopped. Cleanup and cache import bind every opened entry to the cache
mount: Linux uses the descriptor's `mnt_id`, macOS uses `fstatfs` filesystem
and mount-point identity, and Windows rejects reparse points in each stable
pre/post tree. POSIX descriptor-relative traversal also rejects concurrent
nested bind replacement. Windows same-user concurrent junction replacement is
not certified in v0.2 and remains a writable-native-backend enable gate.

## Commands

```text
r46h-card schema-check --profile /absolute/profile-v2.json --plan /absolute/plan-v2.json
r46h-card schema-check-readonly --profile /absolute/profile-v2.json
r46h-card inspect-legacy --input /absolute/legacy-v1.json
r46h-card simulate --profile ... --plan ... --input-root ... --media ... \
  --evidence-dir /absolute/new-evidence-directory \
  --transaction-id exact-lowercase-id
r46h-card discover
r46h-card audit-readonly --profile /absolute/profile-v2.json \
  --attachment-id macos-iomedia-v1:... \
  --evidence-dir /private/tmp/.r46h-card-readonly-audit.UNIQUE \
  --audit-id exact-lowercase-id
r46h-card verify-readonly-receipt --profile /absolute/profile-v2.json \
  --receipt /absolute/READONLY-AUDIT.json \
  --complete /absolute/AUDIT-COMPLETE --tool-version 0.2.0 \
  --tool-sha256 64-lowercase-hex
```

The supported macOS operator entry is the non-root Python launcher, not a
direct `sudo r46h-card` invocation:

```sh
python3 mainline/scripts/r46h_card_macos_readonly.py --list
python3 mainline/scripts/r46h_card_macos_readonly.py \
  --attachment-id 'macos-iomedia-v1:EXACT-DISCOVERED-ID' \
  --archive-root /Volumes/EXTERNAL/EXISTING-r46h-readonly-receipts
```

Before requesting sudo it validates the immutable `CURRENT` generation and
every source record against clean `HEAD`, binds the canonical profile and
binary hashes, and requires an explicit attachment ID. A no-shell bootstrap
then drops to the invoking user to open the external inputs, copies only bytes
matching those bindings into a root-private `/private/tmp` stage, and executes
the staged binary. After the audit subprocess has exited, sudo hands off only
the bounded flat receipt. The unprivileged launcher rechecks its profile/tool/
attachment bindings, publishes it without clobbering to proven external
storage, and removes the exact temporary evidence when unchanged.
The archive root must already exist: the launcher pins its directory handle
and never creates pathname components. It creates only one receipt child via
that proven handle.

"Read-only" describes this tool's descriptor and API surface, not an absolute
electrical no-write guarantee: unmount/eject may flush filesystem metadata
that macOS automount had already dirtied before the tool claimed the card.

On macOS, `discover` prints one strict JSON object for each eligible whole USB
candidate. It does not claim a stable layout identity or hardware target.
`audit-readonly` binds those only after exact profile verification and a
successful eject. On macOS the new evidence directory must be a direct child
of root-owned sticky `/private/tmp`; it must not exist and its physical store
must differ from the target. The small completed receipt can be copied to the
external evidence archive only after the privileged process exits. Linux and
Windows `discover` remain fail-closed.

`ReadOnlyAuditReceipt::validate()` checks internal receipt integrity;
`verify-readonly-receipt` additionally binds it to the raw profile bytes,
expected tool version/digest and `AUDIT-COMPLETE`. The layout identity includes
the profile ID, raw profile digest, hardware target, media geometry, prefix
digest, exact MBR boot/type bytes, partition geometry, filesystems and
identifiers. It excludes attachment/path identity so the same layout remains
recognizable after a reader change or reinsertion. It hashes the bounded prefix
and metadata observations only; it is not a digest of BOOT, root, or EASYROMS
partition contents and cannot prove a full clone. The SHA completion markers
are unsigned consistency checks, not proof that a specific tool performed the
audit. A handoff archive is complete only when `HANDOFF-COMPLETE` is present;
an inner `AUDIT-COMPLETE` alone does not prove archive publication completed.

The checked-in JSON Schemas are structural authoring aids. They intentionally
do not duplicate every cross-field, platform, and media-identity rule. The
CLI's `schema-check` and `schema-check-readonly` commands are the authoritative
semantic validators; passing a JSON Schema alone neither authorizes execution
nor grants a write capability.

The simulator rejects disposable plans;
those require a non-serializable capability issued by a claimed native backend.
The evidence directory must not exist: it is reserved before the first write
and contains `journal.jsonl`, `receipt.json`, and `RECEIPT-COMPLETE`.
The simulator's evidence store is path-bound. A future writable native backend
additionally requires a trusted directory handle and platform-certified
directory flush before physical-media support can be enabled.

## Write Verification Semantics

- `quick`: first and last 4 MiB of every written partition, or the whole
  partition when smaller.
- `balanced`: first and last 1 MiB plus eight deterministic interior samples
  derived from the plan digest.
- `full`: complete readback of every written partition, while attestations
  must cover every remaining byte of the medium exactly once.

All modes verify the actual byte stream consumed during the write against the
declared source SHA-256. `safe_to_boot` becomes true only after verification
and successful eject.

## Tests

```sh
PYTHONDONTWRITEBYTECODE=1 python3 mainline/tests/test_r46h_card_toolchain_build.py
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 mainline/tests/test_r46h_card_macos_readonly.py
mainline/scripts/build-r46h-card-toolchain.sh
```

The build command runs Rust tests, Clippy with warnings denied, rustfmt check,
and the release build before publication. The build-driver tests run on macOS,
Linux, and Windows. The launcher suite and launcher build gate run only on
macOS because they exercise macOS privilege, filesystem, and process contracts.
