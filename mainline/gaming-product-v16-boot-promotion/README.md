# R46H v0.16 persistent BOOT promotion

Status: **HOST ARTIFACT PASS / PERSISTENT COLD GATE FAIL / EXACT V0.15 ROLLBACK PASS**

This is the narrow rollback-safe path from the accepted persistent v0.15
gaming kernel to the exact v0.16 secondary-MMC isolation DTB. Building and
validating the payload is host-only evidence. The separately authorized
2026-08-24 target transaction, failed cold gate and exact rollback are recorded
below; no U-Boot environment change was made.

## Fixed contract

The accepted one-shot archive is 12,466 bytes with SHA-256
`e9d04016f03e5619c64c3a8916b361c64857a6928cbf99f43392492c3d5276d1`.
This promotion reuses its exact 49,522-byte candidate DTB, SHA-256
`7831617d4003cdbb2733433781f80625cb94e7c9d619f2f90990223b8f8d7f81`.
The DTB changes only `/mmc@ff380000/status` from `okay` to `disabled`; system
`/mmc@ff370000`, aliases, the exact v0.15 Image and all three accepted module
trees remain unchanged. The first-version limitation is therefore explicit:
the second card slot is unavailable.

The target wrapper is bound to all of the following:

- whole-card size 62,534,975,488 bytes and 512-byte logical sectors;
- p1/p2/p3 PARTUUIDs `c9f931c9-01`, `c9f931c9-02` and `c9f931c9-03` plus their
  exact geometry;
- v0.5 root UUID `d3130005-46a4-4d56-9001-000000000005`, label
  `R46H_GAMING_V05` and accepted product receipts;
- current post-v0.5-media raw p1 SHA-256
  `042ad4ad08f39f60f1d57e393ab32ae148e2a946ab9996822ae161934f7a0825`
  and fixed 16 MiB prefix SHA-256
  `3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3`;
- exact v0.15/v0.10/v0.8 versioned BOOT files, both U-Boot DTBs and all three
  module trees.

The complete v0.5 p2 rewrite deliberately replaced the earlier live-p2 v0.15
promotion state. The wrapper therefore does not require or recreate that old
transaction receipt; it independently rehashes all three module trees and the
current p1 BOOT anchors instead.

Device names are rediscovered from PARTUUIDs every run. p1 and p3 must be
unmounted, the frontend must be stopped, RetroArch must be absent, ext4 and
systemd health must be clean, and the current storage log must be either clean
or the already accepted historical recovered sequence before a transaction.

## Changes and transaction boundary

Prepare retains the authenticated payload and intent receipt on p2, then adds
only these inert versioned files to p1:

- `rk3326-r46h-mainline-v0.16-disable-secondary.dtb`;
- `boot.ini.v0.16-disable-secondary`.

Active `boot.ini` stays exact v0.15 during prepare. Activate atomically replaces
only active `boot.ini` with the exact v0.16 script; it continues to load the
existing compressed v0.15 Image. Exact v0.15, v0.10 and v0.8 kernel-plus-module
fallbacks remain present. Rollback atomically restores exact v0.15 while
leaving the two inert candidate files for audit and a later reviewed retry.

Every FAT publication uses a root-only stage, exact size/hash verification,
`sync`, a rename and a flush of the freshly rediscovered p1 block device.
Prepare, activation and rollback journals classify every accepted partial
state. An activation error attempts exact v0.15 rollback before unmounting.
Sudden power loss can still interrupt a FAT rename; the journal deliberately
remains so the next serial-first recovery can distinguish the exact v0.15 and
v0.16 active states. Do not delete a journal manually or use `saveenv`.

The wrapper never writes p3, replaces a kernel or module tree, changes the raw
prefix, calls `saveenv`, reboots or powers off. Its only p2 writes are the
root-only retained payload and status receipt.

## Host build

Commit the complete scoped inputs first. The builder refuses dirty or
untracked scoped paths, rehashes the frozen accepted one-shot archive, extracts
the candidate without filesystem extraction, validates its live-DT contract
with the pinned offline device-tree toolchain, checks all shell constants and
publishes one deterministic generation below
`mainline/out/r46h-v16-boot-promotion/`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-r46h-v16-boot-promotion.py build
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-r46h-v16-boot-promotion.py validate
```

Disposable build work stays below `mainline/out/.cache/` and is removed after
the generation is published. Host validation proves artifact identity and
transaction mechanics only; it is not media or physical R46H proof.

Clean source commit `e47adf35182ed5a163bb08296e08b7642c50b766`
produced generation `build-e47adf35182e-f02155890d82`. Its 29,094-byte archive
has SHA-256
`f02155890d825166a07f2e06d145d8bbb9841f73d3ea11f32c0841831f05313a`,
but it is now revoked. On 2026-08-24 that exact archive transferred over the
strict host-key-checked path and passed target payload validation. The
read-only preflight then failed closed with
`unexpected BOOT top-level entry: .fseventsd` before any p1 write. A separate
read-only inspection found `.fseventsd` as a directory with three regular
files, while the complete raw p1 still reproduced the pinned SHA-256
`042ad4ad08f39f60f1d57e393ab32ae148e2a946ab9996822ae161934f7a0825`.
The media therefore had not drifted: the transaction classifier omitted one
directory already present in its fixed baseline. The corrected source treats
`.fseventsd` as the twenty-ninth required base entry, preserves its contents
across prepare/activate/rollback fixtures and still rejects an unsafe type or
an unknown top-level entry. This generation remains revoked.

Clean corrected source commit
`408baa52f95d1c66c321ccc820a4481cb7ac2266` produced generation
`build-408baa52f95d-99d162b5d920`. Its 29,123-byte archive has SHA-256
`99d162b5d920f14108d9d7ff725f96f3e0e52d20dbd713fac46a4a53023ad042`;
the checksum-bound `BUILD-RECEIPT.json` has SHA-256
`e19021298ff0a5f86dbf5cace32392828bef90e4e0f4faf5669653836d896268`.
Build, separate validation and a separately extracted
`install.sh --check-payload` all passed. The revoked
`build-e47adf35182e-f02155890d82` directory was then removed rather than
retained as an ambiguous usable artifact.

The first 29,175-byte host generation from source commit `760a0aafff87`
produced archive SHA-256
`dfd01699adb7c053b32eede06d784c7187916ecde86d1811308fb407c43fd416`.
Second review revoked it before any transfer or target write: it pinned the
historical post-v0.15-promotion raw p1 digest instead of the current
post-v0.5-media digest, and it expected the old live-p2 promotion receipt that
the complete v0.5 p2 rewrite intentionally replaced. The wrapper would have
failed closed before writing, but this generation must not be used. Retain it
only as the recorded identity above: after the corrected replacement passed
independent validation, its superseded generation directory was deleted.

## Executed target result: 2026-08-24

The first ordinary v0.15 staging power-on repeated the already known dual-host
non-recovery and used one short Reset to reach the healthy staging system. That
was transaction logistics, not the separately contracted candidate sample.
The corrected archive then passed target payload validation and read-only
preflight as exact `state=base`, `status=absent`, raw p1 SHA-256
`042ad4ad08f39f60f1d57e393ab32ae148e2a946ab9996822ae161934f7a0825`
and fixed-prefix SHA-256
`3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3`.
Prepare published only the two inert versioned files and produced p1 SHA-256
`056b46df1bff0163bc097340ceb099606eee3b3f7e12e2655ec2c0cf343c4986`;
retained preflight passed, and activation selected exact v0.16 with p1 SHA-256
`d6ad4dd6b6716754227731203fdc7f871cb2a750fb6d52444a0688b45d70d252`.
All v0.15/v0.10/v0.8 fallbacks rehashed exact, `saveenv` was not used, and the
activation session ended with a controlled poweroff.

The one persistent serial-first cold power-on was ordinary: capture opened at
1,500,000 baud before power, switched to 115,200 at the visible OP-TEE marker,
and sent no autoboot interrupt or Reset. U-Boot loaded the 1,449-byte active
v0.16 script, existing 14,925,282-byte v0.15 Image and exact 49,522-byte v0.16
DTB. Linux probed only `ff370000/mmc0`; no Linux `ff380000`, `mmc_host mmc1`
or `mmc1:` marker occurred. The system card nevertheless emitted one
`mmc0: error -84` at 400 kHz, retried at 300 kHz, reached SDR104/150 MHz,
enumerated p1/p2/p3, mounted exact v0.5 p2 and reached multi-user.

This recovered boot violates the fixed no-MMC-error acceptance boundary.
Retained `install.sh --postflight` therefore failed closed with
`persistent v0.16 boot contains a forbidden storage marker` before publishing
`state=complete`; the retained status stayed `activated`. The exact rollback
then restored active v0.15 while leaving the two candidate files inert. It
produced p1 SHA-256
`7d3197852284c7feaf0034489310cbe4eb14cb73f79b4b94b733b1cac004a18e`,
and the final retained preflight passed as `state=prepared`,
`status=rollback-complete`, `mmc_init=recovered-known-open`, with the fixed
prefix unchanged.

The task-created transfer archive, checksum-matched temporary SSH key and
temporary Wi-Fi profile were removed. Final frontend/RetroArch, failed-unit,
ext4-error and p1/p3-mount checks were clean; `sync`, root read-only remount,
complete filesystem unmount and `Powering off.` passed. The root-only retained
payload and rollback status remain on p2 as required recovery evidence. The
three ignored mode-0600 serial captures are:

- preflight/prepare: 2,391,002 bytes, SHA-256
  `382d99df590592a43fc35bda2a69396c1eaabff0b2f54cade4b45ce295710bc9`,
  `mainline/out/r46h-serial-logs/v16-persistent-promotion-preflight-20260824T111641Z.bin`;
- activation/poweroff: 11,380 bytes, SHA-256
  `a001301b99ccc6baeea31758a7500f1214a12fd74bf232ed13c2f9439cdee932`,
  `mainline/out/r46h-serial-logs/v16-persistent-promotion-activation-20260824T124742Z.bin`;
- persistent cold gate/rollback/poweroff: 62,701 bytes, SHA-256
  `895a2ebaca0ec88f936d53142009716b80d99d72ee9214b2afdd1245d8b703b1`,
  `mainline/out/r46h-serial-logs/v16-persistent-coldboot-20260824T125155Z.bin`.

The clean one-shot remains valid evidence for that one sample, but it did not
reproduce under persistent qualification. Disabling the secondary controller
is therefore not sufficient to eliminate the recovered 400 kHz system-card
error and is not proved as the sole cause of the earlier non-recovery. Do not
repeat this unchanged candidate. Any successor must test a changed system-card
cold-power or initialization-timing hypothesis while retaining the same
fail-closed gate and exact v0.15 rollback.

## Reviewed target sequence

This sequence is retained as the executed transaction contract and recovery
reference. It ended in the rollback recorded above and must not be rerun
unchanged. A reviewed successor must still freeze its generation, rediscover
dynamic target and SSH identity, and record the applicable write authority.

1. Open cold serial at 1,500,000 baud before power. After the visible OP-TEE
   marker switch to 115,200, boot the unchanged v0.15 system and stop the
   frontend.
2. Transfer the exact archive with strict host-key checking into a new
   root-owned mode-0700 `/run/r46h-v16-boot-promotion-v0.1` payload. Rehash the
   archive before extraction and run `install.sh --check-payload`.
3. Run the read-only preflight. It may report only an exact clean initial state
   or one documented recoverable transaction state.
4. With the prepare authorization, run:

   ```sh
   /run/r46h-v16-boot-promotion-v0.1/install.sh \
     --prepare --confirm prepare-v0.16-keep-v0.15-active
   ```

   This must finish at `state=prepared active_v0.15=yes`.
5. Run preflight from the checksum-bound retained payload. With a separate
   activation authorization, run:

   ```sh
   /var/lib/r46h-boot-promotion/v0.16-disable-secondary/payload/install.sh \
     --activate --confirm activate-v0.16-keep-v0.15-v0.10-v0.8
   ```

   Do not warm reboot and do not treat activation as a physical pass.
6. After target health checks, `sync` and a controlled serial-confirmed
   poweroff, open serial at 1,500,000 before the one contracted cold power-on.
   The boot must be ordinary, with no autoboot interrupt or Reset.
7. Only after exact persistent v0.16, clean 400 kHz-to-150 MHz initialization,
   root mount and target health pass, run retained `install.sh --postflight`.
   Then clean temporary network/authentication state and perform a controlled
   poweroff.

Prepare recovery uses retained
`--recover-prepare --confirm recover-v0.16-versioned-files`. Activation
recovery uses retained
`--recover-activate --confirm recover-v0.16-active-switch`. Exact rollback is:

```sh
/var/lib/r46h-boot-promotion/v0.16-disable-secondary/payload/install.sh \
  --rollback --confirm rollback-active-to-v0.15
```

If serial or ordinary boot is unavailable, use the exact retained
`boot.ini.v0.15-gaming-product` only as a one-shot U-Boot fallback without
`saveenv`, then run the explicit rollback. A hard warning means do not reboot
or remove power until the classified recovery is reviewed.

## Acceptance boundary

Persistent completion requires one separately reviewed serial-first cold boot
that loads the exact v0.16 DTB and v0.15 Image, probes Linux `ff370000/mmc0`
only, moves once from 400 kHz to 150 MHz, enumerates p1/p2/p3, mounts exact v0.5
root and contains no MMC timeout/error, block-I/O or ext4 fault marker. It must
also rehash all fallbacks, pass the installed product storage audit and finish
with a controlled poweroff. One persistent sample still does not prove the
concurrent probe to be the sole root cause or establish statistical cold-boot
reliability.
