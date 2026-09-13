# Original-card p3 content migration

> Operation record: 2026-08-26–29. This owns the exact content/media boundary.
> Physical R46H use passed; full target readback remains unverified.

## Goal

Move the original card's EASYROMS content onto only p3 of the accepted fixed
R46H card while preserving p1/BOOT, p2/Debian and the required target recovery
files. This migrates content, not legacy emulator binaries or their vendor ABI.

## Fixed target

- Profile: `hl-r46h-v22-g92-62534975488-v1`.
- Whole-device size: 62,534,975,488 bytes.
- Authorized mutation: exact p3 only.
- p1, p2, prefix and U-Boot environment were outside the write scope.

Device names are deliberately omitted because `/dev/diskN` is attachment
specific and must be rediscovered.

## Host image result

- Source card copied read-only: 39,612 files, 42,175,236,685 bytes.
- Preserved target recovery files: 31.
- Container-built exFAT image size: 51,683,880,448 bytes, exactly matching the
  target p3 geometry.
- Read-only `fsck.exfat -n`: clean.
- Image inventory: 3,815 directories and 39,643 files.
- Free space: about 7.85 GiB.

The Linux-container image path was chosen because earlier macOS file-level
exFAT staging produced unreliable metadata/mount behavior. See the
[exFAT postmortem](../mainline/deploy/EXFAT-FSKIT-POSTMORTEM.md).

## Media result

After rediscovering and matching the fixed card/profile and exact partition
geometry, a single visible persistent privileged session:

1. opened the exact p3 raw target;
2. wrote exactly 51,683,880,448 bytes;
3. completed `sync`;
4. ejected the whole device.

Final marker:

```text
R46H_P3_DIRECT result=pass checksums=skipped p1=untouched p2=untouched p3=replaced
```

“p1/p2 untouched” means the operation did not open them for writing; it is not
a new post-operation hash of those partitions.

At the user's direction, full target checksum/readback was skipped. Therefore:

- target p3 content equality is unverified;
- the first-version release p3 hash no longer describes the current card;
- write/sync/eject alone was not physical proof; the separate result follows.

## Physical acceptance result

The exact current card passed the bounded physical gate on 2026-08-29:

1. v0.17 BOOT selected the exact v0.15 kernel/modules and Debian gaming p2 v0.5.
2. p3 mounted read-only at `/roms`; `RequiresMountsFor=/roms` reproduced the
   mount-before-frontend order on warm boot despite the `noauto` fstab policy.
3. Imported directories were visible. `1944.zip` launched with accepted
   controls, audio and Select+X return to RGUI.
4. Services, MMC/block/ext4 health and the read-only mount passed.

`1943.zip` separately reached Nestopia's `Cpu: Jammed` path with repeating
audio. Treat that exact ROM/core combination as failed; it does not revoke the
p3 mount/use result. This gate proves current-card use, not content byte
equality or broad ROM/core compatibility.

## Retention and cleanup

Inventory `mainline/out/.cache/r46h-original-card-import-20260826/` before any
cleanup. Because target readback was skipped, retain the exact image/copy if it
is the only recovery source. Once a separate recovery source is confirmed,
remove redundant staging but keep the named operation and physical receipts.
