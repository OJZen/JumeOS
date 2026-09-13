# Architecture and Native Backend Gates

## Layers

1. **Strict protocol model**: serde types reject unknown v2 fields. Profile,
   plan, device and evidence identities are distinct objects.
2. **Transaction engine**: verifies identity and baselines, pins sources,
   persists an append-only journal, writes, flushes, reads back, verifies,
   ejects, and only then marks the receipt safe.
3. **Platform backend**: owns discovery, exclusive claim, raw handles,
   physical-store ancestry, cache invalidation, synchronization and eject.
4. **Thin CLI**: parses inputs, computes exact byte hashes, reserves a new
   evidence directory before writing, creates the journal, invokes the engine
   and publishes a no-clobber final receipt.
5. **Build driver**: Python owns clean-commit source capture, cross-platform
   Cargo execution, external cache placement, per-build target isolation,
   immutable generation publication, `CURRENT` switching and narrow cleanup.

Shell is limited to five-line launchers. It must not implement transaction
state, parse device metadata, construct JSON, or supervise raw writes.

## Cross-Platform Backend Contract

Every native backend must provide equivalent guarantees through native APIs:

| Requirement | macOS | Linux | Windows |
| --- | --- | --- | --- |
| Stable identity | IOKit/Disk Arbitration registry identity | udev/sysfs major:minor plus serial | SetupAPI device instance and storage number |
| Exclusive claim | Disk Arbitration claim | O_EXCL plus mount namespace/udisks coordination | CreateFile sharing denied plus volume lock |
| No-follow source | open/fstat identity | openat2 or openat O_NOFOLLOW plus fstat | CreateFile reparse-point checks and file ID |
| Durable media flush | fsync plus DKIOCSYNCHRONIZECACHE | fsync plus BLKFLSBUF/cache contract | FlushFileBuffers plus storage property contract |
| Eject | DADiskEject while claimed | udisks/native block removal policy | CM request eject / storage eject IOCTL |
| Physical ancestry | IOMedia whole-disk parent | sysfs block ancestry | storage device number and bus ancestry |

Before a native backend is enabled it must pass real-device fault tests for:

- source replacement and same-inode mutation;
- target replacement or re-enumeration after claim;
- source, receipts, repository and system disk sharing target ancestry;
- baseline mismatch before the first target write;
- partial write at each operation and durable journal recovery;
- flush, readback and eject failures;
- Quick/Balanced interior corruption and Full whole-media coverage;
- receipt collision, parent replacement and crash during publication;
- signal, process termination and host power-loss recovery instructions.

Until those tests and a platform-specific security review pass, the backend
must remain unreachable and return `unsupported`.

### macOS 0.2 read-only milestone

The macOS read-only interface is intentionally separate from `MediaSession`.
It discovers only external removable/ejectable whole USB IOMedia objects,
cross-checks Disk Arbitration descriptions, binds the current attachment to
IORegistry identity plus `st_rdev`, unmounts without force, holds a Disk
Arbitration claim, opens the raw node read-only with no-follow, validates
`DKIOCGETBASE/BLOCKSIZE/BLOCKCOUNT`, and keeps that descriptor through the
profile audit. Partition geometry comes from each partition descriptor;
filesystem identity comes from bounded raw signatures; volume UUID comes from
Disk Arbitration; MBR boot/type bytes are profile-bound and PARTUUID is
derived from sector 0. The descriptor is
closed immediately before `DADiskEject`, while the claim remains active.

This milestone certifies the profile-bound layout fingerprint and its bounded
raw reads only. It does not hash partition contents in full, prove a complete
clone, or authenticate who performed the audit. It has no write method,
does not call `fsync` or `DKIOCSYNCHRONIZECACHE`, emits no `safe_to_boot`, and
does not satisfy any writable-backend gate above. The macOS operator launcher
validates the canonical immutable release against clean `HEAD`, then uses a
no-shell privileged bootstrap. That bootstrap drops to the invoking UID/GID to
open the ownership-disabled external inputs, accepts only the already-bound
hashes, and freezes them into a root-private stage. While privileged, evidence
is published only into a new root-owned `0700` child of sticky `/private/tmp`.
After the audit subprocess exits, sudo exposes only the bounded flat receipt;
the unprivileged parent verifies the external profile/tool/attachment bindings
and publishes a no-clobber archive on proven external storage after sudo has
exited. This proves that the tool owns no raw write capability; it does not
claim physical zero-write behavior because unmount/eject can flush metadata
already dirtied by macOS automount.

## Build Provenance Boundary

Strict builds use Git objects from one captured clean commit, not mutable
working-tree files. The source snapshot, Cargo target, and temporary files all
live in one external private work generation and are removed on success or
failure. A content-checked immutable release generation is complete before the
single `CURRENT` record is replaced, so readers cannot observe a binary from
one build with evidence from another. Release validation anchors the receipt
and all source-manifest records back to every raw blob in the current clean
`HEAD`, with Git replacement objects disabled and scoped LF normalization;
internally self-consistent rewritten evidence is insufficient. It also rejects
links/reparse points across the complete release ancestry.

Cache retention and cleanup use descriptor-derived mount identities in
addition to device numbers. Linux uses `/proc/self/fdinfo` `mnt_id`, Darwin
uses `fstatfs` filesystem and mount-point identity, and Windows rejects any
reparse point in each stable pre/post tree. POSIX deletion and download-cache
import pin source directories with `openat`/`O_NOFOLLOW` and recheck
descendants, so a same-filesystem bind mount is outside the authorized cleanup
boundary. Windows same-user concurrent reparse replacement is not certified
and remains an explicit native-backend gate.

`BUILD-RECEIPT.json` claims first-party source/output integrity, not a hermetic
or signed build. Rust stable, registry download storage and the system linker
remain outside the reproducibility closure. Windows parent-directory flush and
private DACL behavior are also uncertified. These limitations are recorded in
the receipt and must be closed before stronger release claims are made.

## Protocol Evolution

All four checked-in v1 profiles and their original SHA-256 digests remain
legacy evidence. V1 readers may inspect and archive them, but must ignore no
unknown field and must never infer missing execution fields.

In particular, old plans lacking `target_sha256_before` and old statuses using
either string or boolean `safe_to_boot` are not executable v2 input. Migration
is an explicit offline authoring task that produces a new profile/plan ID and
new review evidence. There is no automatic in-place upgrade.

## Journal and Receipt

The journal is append-only JSON Lines. Each complete line is a monotonically
numbered snapshot and is synced before the next destructive step. A truncated
last line after a crash is ignored only by a future recovery inspector; it
never authorizes continuation.

The final receipt binds:

- exact profile and plan byte digests;
- tool version and executable digest;
- complete discovered device identity;
- operation partition, offset, length, source digest and bytes written;
- full readback digest or each structured sample range;
- unchanged-range before/after evidence;
- terminal state and `safe_to_boot`.

Receipt publication is create-new and no-clobber. A production native agent
must strengthen this with a trusted directory handle and platform-native
no-replace rename before physical access is enabled.

The v0.2 simulator deliberately keeps a path-bound `EvidenceStore`. Windows
also lacks a certified parent-directory flush in this release. These are
explicit native-backend gates, not claims of power-loss-safe physical-media
evidence.
