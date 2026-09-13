# R46H first-version release source set

This directory owns the host-only consolidation of the accepted fixed-card
first version. The source set combines exact v0.17 BOOT, exact gaming p2 v0.5,
the accepted g92 prefix and the accepted EASYROMS p3 without touching a block
device.

## Evidence boundary

- Physical proof belongs to the R46H ledger: one persistent serial-first cold
  boot passed exact v0.17 BOOT with the unchanged v0.15 Image and exact p2 v0.5.
- This builder proves only a reproducible host artifact. It opens no
  `/dev/disk*`, performs no media write and does not transfer physical evidence
  to a newly written card.
- The four output files are contiguous source ranges for the exact
  62,534,975,488-byte profile. A redundant monolithic 62.5 GB file is not
  materialized.

| Range | Offset | Size | Accepted input |
| --- | ---: | ---: | --- |
| g92 prefix | 0 | 16,777,216 | exact profile prefix |
| BOOT p1 | 16,777,216 | 117,440,512 | normalized v0.15 clone plus exact v0.17 |
| Debian p2 | 134,217,728 | 10,716,877,312 | gaming product v0.5 |
| EASYROMS p3 | 10,851,095,040 | 51,683,880,448 | accepted deterministic exFAT image |

The p1 transformation is deliberately narrow:

1. remove only `.Spotlight-V100` from the accepted raw p1 clone;
2. replace active `boot.ini` with exact `boot.ini.v0.17-power-settle`;
3. add that versioned boot script and its exact v0.17 DTB.

All other non-Spotlight files and directories must remain byte-exact. The
v0.8, v0.10 and v0.15 kernel/DTB/boot fallbacks are pinned. Clean release p1
does not add the inert v0.16 experiment files.

## Build and validate

The builder is provenance-bound and therefore runs only from committed, clean
source inputs. It rehashes every output component, runs FAT checks in the
pinned offline mtools image and publishes atomically below `mainline/out/`.

```sh
PYTHONDONTWRITEBYTECODE=1 \
  python3 mainline/scripts/build-r46h-first-version-release.py build

PYTHONDONTWRITEBYTECODE=1 \
  python3 mainline/scripts/build-r46h-first-version-release.py validate \
  mainline/out/r46h-first-version-release/builds/build-<commit>-<manifest>
```

The generation keeps the existing writer-facing component names:

- `00-prefix-g92-mbr.bin`
- `01-boot-p1.img`
- `02-debian13-root-p2.img`
- `03-easyroms-p3.img`

`ASSET-MANIFEST`, `SHA256SUMS`, `BUILD-COMPLETE`, upstream receipts and the p1
file-level normalization receipt bind the exact generation. A later media plan
must pin this generation's exact `ASSET-MANIFEST` hash, rediscover the device
identity and retain full write/readback receipts. Building the source set does
not authorize or start that destructive step.

An A2-rated TF card needs no different filesystem image. This source set is A2
compatible, but A2 rating and command-queue behavior are properties of the
physical card/controller and are not proven by host image bytes.

## Historical release convergence (completed 2026-08-26)

> This is a closed record of the release-card convergence, not an instruction
> for the current card. The current card later kept accepted p1/p2 and
> intentionally replaced p3 with the original card's EASYROMS content. Read the
> [current ledger](../board/r46h/EXPERIMENT-STATUS.md) and
> [p3 migration record](../../docs/P3-CONTENT-MIGRATION.md); do not replay the
> commands below against current media.

The completed audit did not infer raw partition equality from an earlier
functional boot: ext4 and exFAT runtime metadata can change even when
user-visible content is accepted. It audited all four complete ranges and
wrote each differing partition. The
2026-08-26 audit of the then-live card found p1 `aa3af4fb...`, p2
`6812d1bf...` and p3 `a55f1174...`; all three differed from this release, while
the g92 prefix remained exact. That card therefore required p1, p2 and p3
writes, not the previously assumed p1-only shortcut.

The completed transition did not use `provision-debian13-new-card-layout.sh`.
It started a Card Agent audit session with the dynamically rediscovered device
and exact `hl-r46h-v22-g92-62534975488-v1` profile. With all partitions
unmounted:

```sh
mainline/scripts/r46h-cardctl.sh card-info
mainline/scripts/r46h-cardctl.sh hash-raw prefix
mainline/scripts/r46h-cardctl.sh hash-raw boot
mainline/scripts/r46h-cardctl.sh clone boot first-version-p1-before.img
mainline/scripts/r46h-cardctl.sh stop
```

The process retained the full p1 clone and required its printed SHA-256 to
match the preceding raw p1 hash. It generated a session-bound plan from that
clone; the canonical generation used for this convergence had
`ASSET-MANIFEST` SHA-256
`e1e8d9edb2f8d0a9fcb4c3a660547944adc0beabbb8d716b2db247b0e7ea588b`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 \
  mainline/scripts/generate-r46h-first-version-p1-write-plan.py \
  --release-dir mainline/out/r46h-first-version-release/builds/\
build-2e0d33a53f11-e1e8d9edb2f8 \
  --asset-manifest-sha256 \
e1e8d9edb2f8d0a9fcb4c3a660547944adc0beabbb8d716b2db247b0e7ea588b \
  --rollback-clone <ABSOLUTE-P1-CLONE-PATH> \
  --target-p1-sha256 <LIVE-P1-SHA256> \
  --device /dev/diskN --confirm-device /dev/diskN
```

The generator opened no device and wrote no media. It validated the release
manifest, completion receipt, component sizes and exact p1 source, then bound a
single full-p1 Card Agent operation to the retained live clone. The existing
partition-specific generators produced the p2 and p3 plans, each bound to its
independently audited live full-partition hash:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 \
  mainline/scripts/generate-debian13-write-plan.py \
  --device /dev/diskN \
  --artifact-id debian13-p2-gaming-v0.5 \
  --profile-id hl-r46h-v22-g92-62534975488-v1 \
  --target-sha256-before <LIVE-P2-SHA256>

PYTHONDONTWRITEBYTECODE=1 python3 \
  mainline/scripts/generate-easyroms-p3-write-plan.py \
  --variant fast-card-62534975488 \
  --device /dev/diskN --confirm-device /dev/diskN \
  --target-sha256-before <LIVE-P3-SHA256>
```

Each one-operation plan used a new deploy session and executed only
`write-first-version-release-boot-p1`, `write-debian13-p2-gaming-v0.5` and
`write-easyroms-p3-62534975488-v1` as required by that audit. It then
independently reopened and fully hashed all final ranges:

```sh
mainline/scripts/r46h-cardctl.sh hash-raw prefix
mainline/scripts/r46h-cardctl.sh hash-raw boot
mainline/scripts/r46h-cardctl.sh hash-raw root
mainline/scripts/r46h-cardctl.sh hash-raw easyroms
mainline/scripts/r46h-cardctl.sh fsck-exfat
mainline/scripts/r46h-cardctl.sh stop
```

The acceptance boundary required the four hashes to be respectively
`3fe2feb9...`, `c6f0d3a9...`, `ee7d402c...` and `fe0ee776...`, the write receipt
contains the exact p1 source/readback hash, exFAT remains clean, the agent is
stopped and macOS eject succeeds. A later serial-first cold boot remained the
separate physical gate; a differing final hash would have blocked that boot.

## Accepted media result: 2026-08-26

The existing accepted 62,534,975,488-byte card completed this convergence path.
`/dev/disk14` was its session-only macOS name; it is not reusable identity.
The exact profile, USB/removable identity, geometry, unmounted state and g92
prefix passed before every write. The retained full pre-write p1 clone is
`first-version-p1-before.img`, 117,440,512 bytes, SHA-256
`aa3af4fb3f715f547c783528789c6227c7da59d3cbf350bea0146b7669330a6e`,
under audit session
`session-20260826T122107Z-18846-23723c0b-0735-4152-9137-f84e5dd83d6d`.

Each differing partition used a separate one-operation plan and agent session:

| Partition | Pre-write SHA-256 | Plan SHA-256 | Session | Receipt / status SHA-256 |
| --- | --- | --- | --- | --- |
| p1 | `aa3af4fb...` | `36030a2a3cba90ded67b01fba380404420e4bead0060e5b678002739bf0bb572` | `session-20260826T122455Z-19182-6c46c094-35c0-40a4-a0e8-d088cbca6ac0` | `233e2044ca7c839bf7f3a98ad5d6908f1ceac9622e41e2cffef5850c5cc5a50c` / `ef33ac6e02641fcaa9ad8727f3ca306ca403924a17d727ba01917ad22119c01a` |
| p2 | `6812d1bf...` | `ed96310033535ee5768b698f61c628175dfd26746e0bf498d7cf8b65acffd073` | `session-20260826T124208Z-19701-04f49dff-74ea-4068-b5c7-4beeaf89f0e6` | `c4b677313582656070fe77f1aee834941ee7441536e857f0520535dfa81db591` / `4130ed8216865953f0fadedd411f02d475c1d051ba2debbaed77032eca16be06` |
| p3 | `a55f1174...` | `342a735820e8ca4f6df87864d67f939485b70fac9cea8a68a1f5019a052d90ae` | `session-20260826T130157Z-20528-e0f5a2f3-744f-471d-9370-0141bfe2f529` | `1c9603913bb2ac9064d95b8c1244948cfd65ca3e7a675104b825b44f5d7b2539` / `c25e091251cd765bd127d803f3d1258d41c65c00c1709ac2970fa1b7562d8e96` |

All three statuses are exact `WRITE_COMPLETE` with `safe_to_boot=yes`. Their
transaction readbacks matched the release sources. A later independent reopened
full-media audit produced exact prefix
`3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3`,
p1 `c6f0d3a9dee4856922fa31cefab1cfae74c0e41364d05cfe36041dacb81ee6bb`,
p2 `ee7d402c06a750081b4c588c5162cca44d0e07fa4b544d5a59bef7629722aeca`
and p3
`fe0ee7764f2e2e1f4b8451183f8cadc26e3a876847eb1bfa0569198438501fac`.
The final read-only exFAT check passed; its log SHA-256 is
`a0bf582faac84c1c31a7db1cbf704d9049960e744aecd9363ca111b293b0eb42`.
The agent stopped, macOS ejected the whole disk and the device node disappeared.

This is **MEDIA PASS for this existing card**. By itself it does not prove a
physical R46H boot, blank/new-card provisioning, statistical cold reliability
or the card's A2 command-queue behavior. Do not rewrite or repeat the complete
hashes absent a disconnect, unsafe removal, I/O evidence or new release bytes.
The separate physical gate is recorded below.

## Accepted physical result: 2026-08-26

The converged existing card completed one ordinary serial-first cold boot.
`/dev/cu.usbserial-3140` was the session-only CH340 name. The listener was open
at 1,500,000 baud before power, observed the visible OP-TEE marker, switched to
115,200 baud and reported `switch_observed=yes`; no Reset, autoboot interrupt
or `saveenv` was used.

U-Boot loaded `Image.mainline-v0.15-gaming-product.gz` and
`rk3326-r46h-mainline-v0.17-power-settle.dtb`. Linux reported exact release
`6.12.99-r46h-mainline-v0.15-gaming-product`, exact model `GameConsole R46H`,
live 800 ms system-card power settle, only `mmc0`, disabled `ff380000`, SDR104
at 150 MHz and p1/p2/p3 enumeration. The intervals from card detect to 400 kHz
and from 400 kHz to 150 MHz were respectively 820.385 ms and 900.663 ms. Exact
v0.5 UUID `d3130005-46a4-4d56-9001-000000000005`, label
`R46H_GAMING_V05` and PARTUUID `c9f931c9-02` mounted as root and reached
multi-user without an MMC, block-I/O or ext4 fault marker.

Read-only target checks reproduced the exact prefix and p1 raw SHA-256 values
`3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3`
and `c6f0d3a9dee4856922fa31cefab1cfae74c0e41364d05cfe36041dacb81ee6bb`.
The three module-tree hashes, product kernel files, product/config receipts,
RetroArch config, frontend, smoke core, storage audit and NES ROM all matched
their release anchors. Five required services were active, one combined
gamepad appeared, p1/p3 remained unmounted and the storage audit passed SDR104
at 150 MHz with zero ext4 errors. It still reports the printed A2 label as not
machine-verifiable and exposes no A2 command-queue interface.

After the frontend stopped normally, the final gate reported no RetroArch
process or session directory, zero failed units, zero ext4 errors, unmounted
p1/p3, no storage-fault marker and successful `sync`. Systemd remounted root
read-only, unmounted all filesystems and printed `Powering off.`. The ignored
70,032-byte capture is
`mainline/out/r46h-serial-logs/first-version-release-coldboot-20260826T140329Z.bin`,
SHA-256
`086134e45172bd98a5322d067e0fa5a346d77df03233b47ae546d8ba2ba1a7a8`.

This closes the existing-card physical gate for the integrated first version.
It does not prove blank/new-card provisioning, statistical cold reliability,
A2 command-queue acceleration or availability of the disabled second card
slot. The already accepted input, NES and audio gates were deliberately not
repeated.
