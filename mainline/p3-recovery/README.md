# EASYROMS p3 full-image recovery

This directory implements the only currently authorized engineering path for
recovering the corrupted EASYROMS partition described in
[`../deploy/EXFAT-FSKIT-POSTMORTEM.md`](../deploy/EXFAT-FSKIT-POSTMORTEM.md).
It does **not** re-enable any generated `stage-on-macos.sh`: physical file-level
staging through macOS FSKit remains blocked.

## Scope and inputs

The compact recovery image is exactly `20,868,328,960` bytes and targets only
p3 of profile `hl-r46h-v22-g92-31719424000-v1`. The same builder and plan
generator also support the exact `51,683,880,448`-byte p3 of profile
`hl-r46h-v22-g92-62534975488-v1` through variant
`fast-card-62534975488`. Both are built from the same three retained host-side
canonical payloads, pinned by `PAYLOAD-SOURCES.json` or the corresponding
`PAYLOAD-SOURCES-62534975488.json`:

- `r46h-v0.8-bootloader-handoff` (historical full-policy anchor only);
- `r46h-v0.9-adc-joystick-fix` (install-modules-only);
- `r46h-v0.10-adc-full-range` (install-modules-only).

No byte is recovered from the corrupted physical p3. No external target trust
receipt, completion secret, macOS metadata directory, or prior failed receipt is
put into the image. Payload scripts on p3 remain data until a separately trusted
target-side receipt authorizes a particular action.

The profile above is the pre-recovery target identity. Linux `mkfs.exfat -U`
stores the GUID so that macOS `diskutil` reports the recovered volume as
`5C29F5E1-124B-4AA5-ACB7-317194240001`. Fresh post-recovery Card Agent audits
therefore use the separate exact identity
`hl-r46h-v22-g92-31719424000-p3-recovery-v1`; this is not a relaxed UUID check.

The build uses a pinned arm64 Linux container, exfatprogs 1.2.9 and the Linux
exFAT driver. The container has no network. It receives only a regular sparse
image and frozen payload files under `/work`; it receives no macOS block-device
path. macOS FSKit is never mounted or invoked during image construction.

## Deterministic filesystem and raw proof

The filesystem contract is fixed:

```text
label=EASYROMS
volume_guid=E1F5295C-4B12-A54A-ACB7-317194240001
volume_serial=52343648
sector_size=512
cluster_size=32768
fat_offset_sectors=2048
fat_length_sectors=4975
cluster_heap_offset_sectors=8192
cluster_count=636722
root_directory_cluster=6
source_date_epoch=1785369600
```

The fast-card variant keeps the same sector and cluster sizes, label and fixed
epoch, but pins FAT length `12321`, cluster heap offset `16384`, cluster count
`1577010`, root cluster `10`, GUID
`62534975-4880-4A4A-ACB7-625349754881` and serial `62534975`.

After Linux has copied and unmounted the files, the raw verifier normalizes all
file/directory entry timestamps to the fixed epoch and recomputes each entry-set
checksum. It then reconstructs every directory and file directly from the boot
regions, FAT, allocation bitmap and cluster heap. PASS requires all of these:

- main/backup boot regions and their checksums match;
- geometry, GUID, label and serial match the expected manifest;
- directory entry-set checksums pass and no deleted/stale entry exists;
- FAT chains have no loop, overlap, unexplained/stale FAT entry or invalid end;
- the allocation bitmap equals the exact set of system, directory and file
  clusters claimed by the reconstructed tree;
- the directory set, file set, every size and every raw file SHA-256 match the
  frozen host inputs;
- exfatprogs read-only fsck passes after timestamp normalization;
- a second raw verification and a second complete image hash see unchanged
  bytes, and no loop device remains attached.

The parser follows the on-disk structures in the
[Microsoft exFAT specification](https://learn.microsoft.com/en-us/windows/win32/fileio/exfat-specification).
It is deliberately stricter than a generic repair utility because this image is
newly constructed and has an exact expected file manifest.

## Build

The builder requires a clean tracked `HEAD`; the builder, verifier, container
script, plan generator and payload configuration must each match their exact
committed blob and mode. Disposable work stays below external `mainline/out/`.

```bash
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-easyroms-p3-recovery.py

# Exact 62,534,975,488-byte card profile:
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/build-easyroms-p3-recovery.py \
  --variant fast-card-62534975488
```

The canonical output is:

```text
mainline/out/r46h-p3-recovery-images/r46h-easyroms-p3-recovery-v1/
```

The fast-card output is
`mainline/out/r46h-p3-recovery-images/r46h-easyroms-p3-62534975488-v1/`.
Its accepted historical generation is additionally pinned in the plan
generator by exact `BUILD-STATUS.json`, `SHA256SUMS`, image SHA-256 and source
commit. This permits reuse after later clean commits without weakening the
artifact identity check; the pinned source commit must remain an ancestor of
the current clean `HEAD`.

`BUILD-STATUS.json` is build evidence, not physical-card evidence. Before a
write plan is created, verify all artifact files and rerun the read-only raw
parser:

```bash
cd mainline/out/r46h-p3-recovery-images/r46h-easyroms-p3-recovery-v1
/usr/bin/shasum -a 256 -c SHA256SUMS
cd /Volumes/Ju/Projects/github/arkos4clone
/usr/bin/python3 -B mainline/scripts/verify-exfat-image.py \
  --image mainline/out/r46h-p3-recovery-images/r46h-easyroms-p3-recovery-v1/easyroms-p3-recovery-v1.img \
  --expected-manifest mainline/out/r46h-p3-recovery-images/r46h-easyroms-p3-recovery-v1/EXPECTED-FILES.json
```

Both commands read the complete logical image. A sparse host file consuming
less physical space is expected; Card Agent still stages, writes and reads all
`20,868,328,960` logical bytes.

## Session-bound physical write

Do not generate a plan while the card is absent. After reinsertion, derive the
actual `/dev/diskN` again; examples below use `/dev/disk12` only as a placeholder.

First start an **audit** Card Agent with the exact smaller-card profile:

```bash
mainline/scripts/start-r46h-card-agent.sh \
  --device /dev/disk12 \
  --profile-id hl-r46h-v22-g92-31719424000-v1
```

In a second terminal, require exact `card-info`, unmount all partitions, and
capture complete pre-write hashes of prefix, p1, p2 and p3:

```bash
mainline/scripts/r46h-cardctl.sh card-info
mainline/scripts/r46h-cardctl.sh unmount
mainline/scripts/r46h-cardctl.sh --json hash-raw prefix
mainline/scripts/r46h-cardctl.sh --json hash-raw boot
mainline/scripts/r46h-cardctl.sh --json hash-raw root
mainline/scripts/r46h-cardctl.sh --json hash-raw easyroms
mainline/scripts/r46h-cardctl.sh stop
```

Copy the lowercase 64-hex digest from that session's complete `easyroms` hash
into `--target-sha256-before`. The generator performs no device read:

```bash
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/scripts/generate-easyroms-p3-write-plan.py \
  --device /dev/disk12 \
  --confirm-device /dev/disk12 \
  --target-sha256-before 64-lowercase-hex-from-the-live-audit
```

For the exact 62,534,975,488-byte profile, add
`--variant fast-card-62534975488`, start Card Agent with profile
`hl-r46h-v22-g92-62534975488-v1`, and execute operation
`write-easyroms-p3-62534975488-v1`. Device names are session-dynamic; the plan
and Card Agent must use the freshly rediscovered same whole-disk path.

Start a new **deploy** agent using the absolute plan path and printed plan hash:

```bash
mainline/scripts/start-r46h-card-agent.sh \
  --device /dev/disk12 \
  --profile-id hl-r46h-v22-g92-31719424000-v1 \
  --deploy \
  --write-plan /absolute/path/to/write-plan.json \
  --write-plan-sha256 64-lowercase-plan-hash
```

In the second terminal, recheck `card-info`, unmount and execute the single
allowed operation:

```bash
mainline/scripts/r46h-cardctl.sh card-info
mainline/scripts/r46h-cardctl.sh unmount
mainline/scripts/r46h-cardctl.sh --json execute-write write-easyroms-p3-recovery-v1
```

The agent hashes the pinned target p3 before `WRITE_IN_PROGRESS`; a mismatch
fails before any target byte is written. It stages and hashes the entire source,
performs a raw-device cache-sync preflight, writes only p3, syncs media, reads
the entire p3 back through the same pinned target FD and verifies the g92 prefix
before publishing `WRITE_COMPLETE` with `safe_to_boot=yes`.

Do not stop at that receipt. While the same card is still present, independently
repeat complete prefix/p1/p2/p3 hashes. Prefix, p1 and p2 must equal their audit
values; p3 must equal the canonical image SHA-256. Also require the response's
`write_status` file to contain `state=WRITE_COMPLETE` and `safe_to_boot=yes`.
Only then unmount, stop the agent, safely eject and reinsert. Start a fresh audit
session using the post-recovery identity, unmount, repeat the full p3 hash and
create a new full clone with
`mainline/scripts/r46h-cardctl.sh clone easyroms easyroms-postreinsert.img`.
The clone path printed by Card Agent must be exactly `20,868,328,960` bytes and
have the canonical image SHA-256; run the same raw verifier against that clone
and the artifact's `EXPECTED-FILES.json` before booting the R46H.

```bash
mainline/scripts/start-r46h-card-agent.sh \
  --device /dev/disk12 \
  --profile-id hl-r46h-v22-g92-31719424000-p3-recovery-v1
```

Any disconnect, I/O error, hash drift, missing status file or incomplete readback
leaves the card unsafe to boot. Never fall back to file-level macOS staging or
filesystem-level hashes to waive a failed raw gate.
