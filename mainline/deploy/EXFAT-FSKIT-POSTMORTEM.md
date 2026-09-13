# 2026-08-11 EASYROMS exFAT raw-read incident

## Decision

Physical-card file staging through the generated macOS `stage-on-macos.sh` is
disabled.  Existing generated stagers and the v0.10 target trust receipt must
not be consumed.  Directory-backed integration fixtures remain enabled because
they do not address physical media.  The historical Debian Mesa probe v0.2
packager is also frozen: regenerating its old unguarded stager would bypass the
block, while changing it under the same v0.2 identity would violate its receipt
contract.

The revoked v0.10 receipt is:

```text
TARGET_TRUST_RECEIPT_SHA256=e46b2b0948d124e9e611520be5b0f66d45954dc5262fe0597f6e0bc1a98b3b8e
RECEIPT_DIR=mainline/out/r46h-v10-modules-only-card-receipts/.r46h-r46h-v0.10-adc-full-range-final.aPRW3T
```

Do not rename or delete that historical receipt.  Its retained bytes prove
what the old workflow accepted; this document revokes its authority.

Physical deployment may resume only after one of these paths has its own
reviewed implementation and tests:

1. construct a complete p3 image offline, verify every payload file from raw
   exFAT allocation metadata, and use Card Agent to perform one complete
   partition write plus complete readback; or
2. extend the physical stager with an independent raw-device parser/verifier
   which reconstructs every staged file from the on-media directory entries,
   FAT and data clusters after unmount, before publishing any trust receipt.

A filesystem-level hash, successful unmount/eject, or clean `fsck_exfat` result
is not sufficient.

The first path now has a source-level implementation candidate in
[`../p3-recovery/README.md`](../p3-recovery/README.md). It does not consume any
byte from the failed p3 and keeps macOS FSKit outside image construction. That
candidate is not itself a recovery receipt: resumption still requires a clean
HEAD build, complete raw artifact audit, Card Agent target-baseline match, full
p3 write and readback, independent post-write hashes, reinsertion and a fresh
raw clone verification. The second path has not been implemented, and all
file-level physical stagers remain blocked.

## Recovery completed on the replacement fast card

On 2026-08-14 the first recovery path completed for the exact
62,534,975,488-byte replacement card. A Linux-built 51,683,880,448-byte p3
image containing the retained v0.8, v0.9 and v0.10 payload trees was written as
one full partition, fully read back in the same write transaction, then passed
the post-reinsert quick immutable-payload audit. The accepted bounds and the
reason a normal iteration does not repeat a 125 GB full audit are documented
in [`FAST-CARD-62534975488.md`](FAST-CARD-62534975488.md).

This recovery validates the rebuilt fast-card p3 only. It does not restore
authority to the revoked receipt above and does not permit any generated
macOS file-level stager. Target-side consumers must still pin the rebuilt
payload bytes independently before use.

## What was observed

The canonical v0.10 compressed Image SHA-256 is:

```text
736549a919eee0342a2bae961a85b59337ad8de3c901c2e5f193aa15fdead954
```

macOS read the expected digest twice after reinsertion.  The R46H, however,
read the same stable wrong digest at both 50 MHz and 25 MHz:

```text
982fe2b483220ef4515f75f729714782f1997dca55124430fe3243d1c7f593f5
```

Only seven 32 KiB logical Image chunks differed: `411..414` and `425..427`.
Linux reported zero MMC error counters, p2 `errors_count=0`, no new failed
systemd unit and no storage-fault log.  Re-reading at a lower bus clock did not
change a byte, so the result is persistent media content rather than a transient
high-speed read error.

The v0.8 and v0.9 DTBs should both have had SHA-256:

```text
7259bac7bdd063fbaed987a0d5d2bf7066e02beaacc4440849b93d5f048e3dbc
```

Raw reconstruction instead produced:

```text
v0.8 DTB  86cdabbaccafdb470b69efb3645d6654154eae754bc2e0c3cb37488a36cdfad1
v0.9 DTB  d9e99384b745468b2d91921eb3ef2961145e0adc5f7fdec079c281c69d988db6
```

The card identity, g92 prefix, partition table, p1 and p2 remained separately
verified.  This incident invalidates p3 content and receipts derived from it;
it does not invalidate those independent p1/p2 proofs.

## Raw exFAT reconstruction

The audited p3 geometry was:

```text
sector_size=512
cluster_size=32768
fat_offset_sectors=2048
fat_length_sectors=4975
cluster_heap_offset_sectors=8192
cluster_count=636722
root_directory_cluster=6
```

The v0.10 Image directory entry had `NoFatChain=0`, first cluster `3142` and
length `14921256`.  Walking its FAT chain and reading raw clusters exposed two
places where the chain skipped over clusters currently named by older DTB
entries, while those DTB clusters contained the missing Image chunks:

| Raw allocation evidence | Content found |
| --- | --- |
| `1607 -> 1608 -> 1609 -> 1610 -> 1613 -> 1614 -> 1615 -> 1616` | Image chunks `407..410`, then `413..414`; `1615..1616` were stale/non-Image data |
| v0.8 DTB contiguous clusters `1611..1612` | Image chunks `411..412`, not the DTB |
| `3133 -> 3134 -> 3135 -> 3138 -> 3139 -> 3140` | Image chunks `422..424`, then `427`; `3139..3140` were stale/non-Image data |
| v0.9 DTB contiguous clusters `3136..3137` | Image chunks `425..426`, not the DTB |

This mapping accounts for the seven mismatching Linux chunks exactly.  The
filesystem's allocation structures are internally plausible, but the bytes
owned by named files are wrong.

Both Apple's read-only `fsck_exfat` and exfatprogs 1.2.9 accepted the structure.
The independent exfatprogs result was:

```text
/work/easyroms.img: clean. directories 20, files 148
```

That is expected: structural checkers cannot know the intended SHA-256 of an
Image or DTB when directory entries, FAT and bitmap are mutually consistent.

## Causality boundary

The failing stage ran on macOS 26.5.2 using Apple's FSKit exFAT extension.  The
system log showed 512-byte sectors, 128 KiB device read/write sizes, several
mount/unmount cycles, and no logged disk I/O error.  These facts identify the
observed path, not a single proven cause.  The defect could be in FSKit, the
reader/card, or their interaction.

A virtual CRawDiskImage reproduction used the same copy/sync/rename ordering.
It produced a fragmented Image, including a gap over the v0.9 DTB allocation,
but its offline raw reconstruction still matched the canonical digest.  That
negative reproduction rejects the stronger claim that the sequence always
corrupts exFAT.

## Preserved evidence

The Card Agent audit session is:

```text
mainline/out/r46h-card-agent-sessions/session-20260811T122258Z-88006-5ddea02c-d830-4dee-9754-a6341659eed0
```

Key retained files and SHA-256 digests:

```text
47dee69038ef861db972255121a4acf2f19319bc6dfe42d97a864b124eee9645  events.jsonl
6671eec508be361c81b4f77b508dc9e3f6e7b9b7c9f5dc42fb05999b4eb839ac  fsck-exfat-read-only.log
7a93cb9f8c15b8da08fbbc1ed91659eb8273bb86f69310176a0e4ccf68475d04  fsck-exfatprogs-1.2.9-read-only.log
33afe6e0efa3176a4e9ec170701909db8482ac29b804eafc1e4d5cd01b1c6476  v10-fat-window-2048-2079.bin
495f29d4216748d833af776babd62b56bea1fc4b98e084b90ba404886cc15d41  v10-metadata-first-6m.bin
7537680aa914f6813ec3a94f4bbc79ce0d7ad25009d38e09c29b1e07b41db501  v10-metadata-6m-8m.bin
e3c93ce68a8d6a006c50ea148b89316606a6b8a8f80fc2dfc78f0563c0b7bfa6  v08-dtb-raw-clusters.bin
dee53695da02e1bfcff7a573546e9f5445702f237f23a5f7c27f2897b7c7fcfd  v09-dtb-raw-clusters.bin
b89f3dfb8dfdde32d5351cb61eae1fef336a998fdb1f8c9e3b1c86257dda15a2  v10-corruption-window-a.bin
7cccb47f40e5c65381b90635cc2f3161e2f4c1d33ad8d75eea1389ad699b046d  v10-corruption-window-b.bin
```

The serial evidence is:

```text
211d708daa9db871a1e021942b0933ab48ed3132098c12d32cdca663daa38ad6  mainline/out/r46h-serial-logs/v10-sd-highspeed-oneshot-20260811T0725Z.log
```

At audit completion, all `/dev/disk12` partitions were unmounted, the Card
Agent was stopped, and no physical-card write or filesystem repair had been
performed during diagnosis.
