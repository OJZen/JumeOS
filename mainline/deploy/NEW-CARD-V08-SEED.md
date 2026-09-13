# Debian 13 new-card v0.8 baseline seed

The Debian 13 card has a different whole-media size and EASYROMS UUID from the
historical g92 test card. Its initially blank EASYROMS partition therefore does
not contain the v0.8 anchors required to generate and stage a normal v0.9
bundle. `seed-v08-baseline-on-debian13-new-card.sh` performs that one bounded
bridge operation.

The seed is deliberately **not** a target deployment authorization:

- it writes only `r46h-v0.8-bootloader-handoff` on p3;
- that directory contains exactly the 11 files covered by the canonical v0.8
  `STAGE-SOURCES.sha256`, with `STAGE-COMPLETE` published last;
- the included target scripts and `STAGE-COMPLETE` are baseline anchors only;
- no `TARGET-TRUST-RECEIPT`, completion secret, or
  `FINAL-RECEIPT-COMMITMENT` is generated;
- **never execute** `bootstrap-target.sh`, `install-modules.sh`, or
  `switch-boot.sh` from this seeded v0.8 directory.

The script accepts only the audited 31,719,424,000-byte card identity, rejects
the known 1 TB workspace disk, and requires p3 to contain no user data. Standard
macOS metadata directories may remain. It freezes and revalidates the canonical
source, mounts only p3 for writes, removes only byte-proven AppleDouble
sidecars, and verifies the exact destination set. Before and after both body
and completion-gate publication it proves the g92 prefix, fdisk output, full
BOOT raw hash, and bounded first/last root samples unchanged. This seed run does
not recalculate the full 10.7 GB p2 hash. It instead requires the exact prior
post-reinsert audit whose status SHA-256 is
`ce59319faafe2a84ee8efe7640ab0bfffa471510a41889fb3f517597964963e2` and
whose complete p2 SHA-256 is
`6a4254a8e66c110405cf068317da5922bb5ddfe2a02535d1a381fe1303876c96`.
The two bounded samples only prove that p2 did not drift during this seed
transaction. Root is never mounted. A successful run safely ejects the card and
publishes an invoking-user-owned `0700` receipt on a different physical disk.
The default receipt parent is the system sticky directory `/private/tmp`.
This is intentional: the root worker creates its random `0700` receipt directly
under the root-owned sticky parent. The invoking user cannot replace that
root-owned directory while privileged source snapshots are present.
`/Volumes/Ju` is mounted `noowners` and therefore cannot prove a root-only trust
boundary; production `--receipt-parent` consequently accepts only
`/private/tmp`. Source files and the prior audit remain user-owned external
evidence. The root worker reads them through a dropped-UID reader into its
private snapshot and validates only the frozen copy. On a macOS `noowners`
external volume, those input paths are accepted only after `diskutil`
independently reports `Owners: Disabled`; mode, link count, content hash and
physical-disk separation remain mandatory.

Run from the repository root while the audited card is inserted:

```sh
mainline/scripts/seed-v08-baseline-on-debian13-new-card.sh \
  --device /dev/diskN \
  --confirm-device /dev/diskN \
  --prior-audit-dir /Volumes/Ju/Projects/github/arkos4clone/mainline/out/r46h-new-card-postwrite-audits/.r46h-new-card-postwrite.VVNMVg \
  --prior-audit-status-sha256 ce59319faafe2a84ee8efe7640ab0bfffa471510a41889fb3f517597964963e2
```

The repository and `/private/tmp` must resolve to backing disks different from
the target card. For Apple Silicon internal storage, `diskutil` may omit the
human-readable `Virtual` field; that case is accepted only when the resolved
whole disk is simultaneously internal, fixed, solid-state and uses the Apple
Fabric protocol. Disk images, external virtual devices and incomplete
identities remain rejected. Before either success or an ordinary failure
receipt is handed to the invoking user, the private `.work` snapshot must be
deleted and the top-level receipt directory is chowned last. If `.work` removal
fails, the receipt remains root-owned, returns status 74 and must be inspected
and removed with administrator authority; it is never `COMPLETE`. On success,
retain the printed `RECEIPT_DIR`; as the invoking user, copy that specific small
receipt to the external evidence directory, verify its complete relative-path
and SHA-256 manifest, atomically publish the external copy, then remove only
that specific internal receipt. Never remove `/private/tmp` itself.

The receipt proves only that baseline anchors were seeded. The next step is to
generate and stage a v0.9 bundle using the Debian 13 new-card profile and the
repository v0.8 baseline. Only the new v0.9 stage receipt may authorize the
v0.9 module installation.

The directory-backed test does not pass a block device to its container:

```sh
bash mainline/tests/test-new-card-v08-seed.sh
```

It checks exact-file publication, AppleDouble cleanup, blank-card rejection,
source-tamper rejection, completion-gate invalidation, receipt boundaries, and
the absence of every target-execution authorization. It is not hardware or
real-media-write evidence.
