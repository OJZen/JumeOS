# R46H v0.17 persistent BOOT promotion

Status: **HOST ARTIFACT + TARGET TRANSACTION + PERSISTENT COLD PASS / FIRST FUNCTIONAL VERSION ACCEPTED / STATISTICAL RELIABILITY OPEN**

This is the narrow rollback-safe successor to the failed v0.16 persistent
gate. It promotes the exact v0.17 800 ms system-MMC power-settle DTB that
passed one serial-first cold one-shot on 2026-08-25. Host validation, target
publication and one separate persistent physical cold boot now each have
accepted evidence; they remain distinct evidence levels.

## Fixed candidate

The accepted one-shot archive is 12,517 bytes with SHA-256
`02b6da57c039c31a95143eab1b922c14c0ac4bc60621d02dab9d07f1796409a9`.
This promotion reuses its exact 49,561-byte DTB, SHA-256
`116942e7bc8691bbf6bf185dd3cbe306de2d33be8dad79a027249f9f5234b796`.
Relative to v0.16, the only functional DT change is
`/mmc@ff370000/post-power-on-delay-ms = <800>`; the secondary controller stays
disabled, aliases stay unchanged, and the exact v0.15 Image and accepted
module trees remain unchanged. The second card slot is therefore unavailable.

The accepted one-shot loaded the exact v0.15 Image and v0.17 DTB without Reset
or `saveenv`. Linux instantiated only `ff370000.mmc`, waited 821.662 ms from
card-detect to the 400 kHz marker and 896.044 ms from 400 kHz to 150 MHz,
enumerated p1/p2/p3, mounted the exact v0.5 root and reached multi-user with no
MMC error, timeout, stuck-busy, block-I/O or ext4 fault marker. This proves one
one-shot sample only, not persistent or statistical reliability.

## Fixed target baseline

The transaction keeps the v0.16 wrapper's device, geometry, prefix, product,
module-tree and fallback anchors. Dynamic device nodes are rediscovered from
the fixed PARTUUIDs every run. The current raw p1 baseline is
`7d3197852284c7feaf0034489310cbe4eb14cb73f79b4b94b733b1cac004a18e`.
It includes these exact inert predecessor files from the rolled-back v0.16
experiment:

- `rk3326-r46h-mainline-v0.16-disable-secondary.dtb`: 49,522 bytes, SHA-256
  `7831617d4003cdbb2733433781f80625cb94e7c9d619f2f90990223b8f8d7f81`;
- `boot.ini.v0.16-disable-secondary`: 1,449 bytes, SHA-256
  `edb33de5fef23b810deec13c05b6958a72eea3dbb74ce2b39b0f80cdb508aba3`.

The retained root-only v0.16 payload and rollback status on p2 may coexist with
the new versioned state. They are not an activation input and are not deleted.
p3, the pre-partition prefix, U-Boot environment, kernel Images and module
trees are never written by this wrapper.

## Transaction boundary

Prepare authenticates and retains the v0.17 payload on p2, then publishes only
these inert files to p1:

- `rk3326-r46h-mainline-v0.17-power-settle.dtb`;
- `boot.ini.v0.17-power-settle`.

Active `boot.ini` remains exact v0.15 during prepare. Activate atomically
selects the versioned v0.17 script, which still loads the exact existing v0.15
compressed Image. Rollback atomically restores exact v0.15 and leaves both the
v0.16 and v0.17 versioned pairs inert for audit. FAT staging, journals,
size/hash checks, flushes, retained status and partial-state recovery follow
the already tested v0.16 transaction model.

The wrapper fails closed unless p1 and p3 are unmounted, the frontend and
RetroArch are stopped, root/ext4/systemd health is clean, all baseline members
and product anchors rehash exact, and the dynamic media identity matches the
fixed profile. Standing user authority covers R46H device writes after this
identity check; it does not relax any fail-closed guard or authorize another
disk, geometry or profile.

## Host build

Commit the complete scoped inputs first. The builder refuses dirty or
untracked scoped paths, rehashes the frozen accepted one-shot archive, checks
the exact DT properties with the pinned offline toolchain, renders the narrow
v0.17 transaction from the reviewed v0.16 templates and publishes one
deterministic generation below `mainline/out/r46h-v17-boot-promotion/`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-r46h-v17-boot-promotion.py build
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-r46h-v17-boot-promotion.py validate
```

Disposable work stays below `mainline/out/.cache/` and is removed after the
generation is published.

Clean source commit `622cf60feab7e2f935c485316cd1cbc3f7be757c`
produced generation `build-622cf60feab7-c2eea1243359`. Its 29,463-byte
archive has SHA-256
`c2eea1243359c06bbb9463b114b37eb52b78f0d10e01960a69b72ecc30e2ce61`;
the 1,610-byte `BUILD-RECEIPT.json` has SHA-256
`c35b86b5eaec0941e46496adb2ef9ce2d246adbe577339229f0aee16d92903e1`,
and `SOURCE-MANIFEST.json` has SHA-256
`2427358e7eb6d52cd74fd0915d4bbc4df68288dca8e5fd6bb6fbee6819c012dc`.
Builder validation, a separately extracted `install.sh --check-payload`, exact
member ownership/mode checks and an isolated second full build all passed; the
two complete generations matched byte-for-byte. Focused v0.17 transaction
tests passed 9/9, the reused v0.16 framework passed 11/11 including validation
of its historical generation, and the v0.17 one-shot source gates passed 6/6.
The disposable extraction and second-build tree were removed.

The host result above alone does not prove a target write, active BOOT
selection or a physical R46H boot. The separate transaction evidence follows.

## Executed target transaction: 2026-08-25

The later logistics power-on was already running when the first reconnect
attempt began, so it is not cold-start evidence. After the operator restored
the UART crossover/common ground, CH340 re-enumerated and a fresh 115,200-baud
session reached the login prompt. Login proved exact running release
`6.12.99-r46h-mainline-v0.15-gaming-product`, exact p2 PARTUUID, writable ext4
with zero errors, no failed units and unmounted p1/p3. The frontend and
RetroArch were stopped normally. There was no target IPv4 address, so the exact
29,463-byte archive transferred over echo-disabled, 128-column paced serial.
Target SHA-256 reproduced
`c2eea1243359c06bbb9463b114b37eb52b78f0d10e01960a69b72ecc30e2ce61`,
and extracted `install.sh --check-payload` passed every member.

Initial read-only preflight passed as `state=base status=absent`, raw p1
`7d3197852284c7feaf0034489310cbe4eb14cb73f79b4b94b733b1cac004a18e`,
fixed prefix `3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3`
and `mmc_init=recovered-known-open`; no write had begun. Prepare retained the
root-only checksum-bound v0.17 payload/status on p2 and published only the two
inert v0.17 files while keeping active v0.15. It passed with p1 SHA-256
`da4c4607982c366ecba0e81b474b74722724de919c6a889367218507d3d17ab5`.
Retained read-only preflight then passed exact `prepared/prepared` with the
same p1 and prefix.

Activation atomically selected exact v0.17 and passed all fallback checks with
p1 SHA-256
`ad71f67bfb436cc480bb9a83db770f88cdcadc54612b322d9106befa0982929b`.
The retained `state=activated` status has SHA-256
`ffb379cf30fecfea1b3c18b20cc3685c0cd55841f21e49b6838e851d594d81b1`
and binds active boot SHA-256
`96300e2e74fa3ea00da28d81c80c7fa3e327bd4784af6ddc766817b36ad33778`,
candidate DTB SHA-256
`116942e7bc8691bbf6bf185dd3cbe306de2d33be8dad79a027249f9f5234b796`
and payload-manifest SHA-256
`ad08850e51b67cd317decd5ba0828c015c0624834e75d199d1ff627f3bdcf90b`.
No `saveenv` was used.

Final ext4 error count was zero, failed units were absent and p1/p3 were
unmounted. The task-created `/run` archive and extraction were removed while
the retained p2 recovery payload/status remained. `sync`, root read-only
remount, complete filesystem unmount and serial `Powering off.` passed. The
20,050-byte ignored capture is
`mainline/out/r46h-serial-logs/v17-persistent-logistics-rewire-20260825T134822Z.bin`,
SHA-256
`a9a0a7aedbdbb814d14157ac19395ce48a7f71e009d2ee74fae8e16e3c6196c1`.
The board is off with active v0.17 selected. This proves the target transaction
and rollback readiness, not a v0.17 boot.

## Completed persistent cold gate: 2026-08-25

Serial was open at 1,500,000 before power and switched to 115,200 only at the
visible OP-TEE marker. The operator used one ordinary cold power-on; autoboot
was not interrupted and Reset was not pressed. U-Boot loaded the exact
1,417-byte active v0.17 script, the existing 14,925,282-byte compressed v0.15
Image with 41,570,816-byte uncompressed size, and the exact 49,561-byte v0.17
DTB.

Linux reported exact release
`6.12.99-r46h-mainline-v0.15-gaming-product` and instantiated only
`ff370000/mmc0`. The measured interval from `Got CD GPIO` to the 400 kHz marker
was 819.113 ms; the following interval to 150 MHz was 902.528 ms. Tuning then
succeeded at phase 52, the card enumerated as SDR104 with p1/p2/p3, exact v0.5
p2 mounted as root and multi-user completed. The capture contains no MMC
error/timeout/stuck-busy, block-I/O or ext4 fault marker.

After a normal frontend stop, retained `install.sh --postflight` passed its
payload, fallback/module, media-identity, clean-log and storage-health gates.
It verified live big-endian `post-power-on-delay-ms` bytes `00 00 03 20`, one
MMC host, unavailable second card slot, SDR104 at 150 MHz, zero ext4 errors,
exact p1 SHA-256
`ad71f67bfb436cc480bb9a83db770f88cdcadc54612b322d9106befa0982929b`
and `saveenv_used=false`. The resulting retained `state=complete` status has
SHA-256
`3b4265849e446ee8566e47fbfb7d7ee4145bdd0d732caa7b5913684b4e4d3034`.
The audit cannot machine-verify the printed A2 label and found no SD command
queue interface; it does verify the accepted card's normal SDR104 operation.

Final checks again found zero ext4 errors, no failed units and unmounted p1/p3.
`sync`, root read-only remount, complete filesystem unmount and serial
`Powering off.` passed. The board is off. The 58,567-byte ignored capture is
`mainline/out/r46h-serial-logs/v17-persistent-coldboot-20260825T141047Z.bin`,
SHA-256
`c84dccd4bff90421c8a4741ebf5598b9ea7f86e619cb22212fefa6615ee97f70`.

This one persistent sample, together with the earlier separate one-shot,
qualifies the first functional version for this fixed card/profile. It does not
establish statistical cold-boot reliability or prove that secondary-host
isolation is independently necessary. Do not repeat either accepted v0.17
cold sample merely to increase the count, clear the retained rollback state or
use `saveenv`; exact v0.15 remains the recovery fallback for a real regression.
