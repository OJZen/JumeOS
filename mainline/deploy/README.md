# R46H EASYROMS deployment bundles

This directory defines the fail-closed deployment format for HL-R46H-V22
mainline-kernel tests. It does not build a Debian root filesystem and it does
not replace the audited bootloader.

## Inputs and trust boundary

`generate-easyroms-bundle.py` requires three immutable inputs:

- a canonical `r46h-mainline-test-<build-id>.tar.gz` produced by the package
  workflow;
- exactly one of the two audited profiles: `profiles/hl-r46h-v22-g92-v1.json`
  for the original 31,914,983,424-byte g92 card, or
  `profiles/hl-r46h-v22-g92-31719424000-v1.json` for the provisioned
  31,719,424,000-byte Debian 13 card. Each pins the complete partition geometry,
  UUIDs, g92 prefix, U-Boot DTBs, and the v0.2 known-good fallback identity;
- one `baselines/*.json` file describing the currently selected mainline
  kernel and the existing EASYROMS payload anchors.

The generator rejects malformed source identity fields, recomputes the
module-tree hash from the package `SHA256SUMS`, validates the complete
card/profile schema, accepts only the exact profile-ID/geometry pairs above,
and rejects release, payload, and BOOT-path collisions.
Output is deterministic for identical inputs and `SOURCE_DATE_EPOCH`.

Repository provenance checks reject persistent Git configuration pollution,
repository-local archive attributes, index masking, ordinary path replacement,
and accidental concurrent edits. They do **not** defend against a malicious
process already running as the same macOS UID that changes private `.git`
metadata only during the `git archive` subprocess window and restores it before
the post-check, or that actively races the generator's private output names.
Eliminating that threat requires an isolated build account, object store, and
output namespace; this workflow does not claim to do so.

Example for a build that advances from the hardware-booted v0.7 baseline:

```sh
python3 -B mainline/scripts/generate-easyroms-bundle.py \
  --package-tar mainline/out/r46h-mainline-test-<build-id>.tar.gz \
  --card-profile mainline/deploy/profiles/hl-r46h-v22-g92-v1.json \
  --current-baseline mainline/deploy/baselines/v0.7-host-timers.json \
  --purpose <lowercase-purpose> \
  --source-date-epoch <unix-epoch> \
  --output-dir mainline/out
```

The result contains a directory and a byte-reproducible `.tar.gz`. The
directory is the directly consumable form.

For the provisioned Debian 13 card, first complete the one-time bounded seed in
[`NEW-CARD-V08-SEED.md`](NEW-CARD-V08-SEED.md). Then generate the v0.9 payload
as an **install-modules-only** bundle:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B mainline/scripts/generate-easyroms-bundle.py \
  --package-tar mainline/out/r46h-mainline-test-v0.9-adc-joystick-fix.tar.gz \
  --card-profile mainline/deploy/profiles/hl-r46h-v22-g92-31719424000-v1.json \
  --current-baseline mainline/deploy/baselines/v0.8-bootloader-handoff.json \
  --purpose adc-joystick-fix-modules \
  --action-policy install-modules-only \
  --source-date-epoch 1785369600 \
  --output-dir mainline/out
```

The two profiles are not interchangeable even though p1 and p2 have the same
offsets, sizes and identities: whole-card size, p3 size/UUID, and prefix SHA-256
are card-specific trust anchors. A modules-only manifest and its external
receipt authorize exactly `install-modules`; `switch-boot.sh` is absent and a
`switch-boot` request is rejected before any target mutation. After the module
receipt succeeds, build the separate full-p1 one-shot candidate described in
[`../p1-candidate/README.md`](../p1-candidate/README.md). The active v0.8
`boot.ini` remains unchanged, so a normal reset still returns to v0.8.

The one-shot p1 layout retires the space-consuming v0.2 BOOT fallback files.
Consequently an `install-modules-only` stager verifies the active v0.8 files,
the versioned v0.8 candidate/Image/DTB, both U-Boot DTBs, the complete p1 raw
hash before and after staging, and all current EASYROMS anchors, but it does not
require the unused v0.2 BOOT files to exist. A full
`install-modules,switch-boot` bundle still requires and verifies every v0.2
fallback file before any write. The executable action-policy fixture covers
both sides of this distinction: modules-only succeeds without the retired
files, while full policy fails before mutation when they are absent.

## Deployment order

> **Physical EASYROMS file-level staging is permanently blocked.** The
> 2026-08-11 v0.10 audit proved that macOS could return the expected file hash
> while raw exFAT allocation contained overwritten Image and DTB clusters. The
> source template now rejects production staging before card access; already generated
> `stage-on-macos.sh` files predate that guard and must not be run.  The steps
> below remain historical workflow documentation, not present authorization to
> write a physical card.  See
> [`EXFAT-FSKIT-POSTMORTEM.md`](EXFAT-FSKIT-POSTMORTEM.md) for the evidence,
> revoked receipt and safe resumption criteria.
>
> The full-partition implementation candidate is documented in
> [`../p3-recovery/README.md`](../p3-recovery/README.md). It constructs p3
> offline with Linux exFAT, reconstructs every intended file from raw metadata,
> and permits only a Card Agent full-p3 write/readback plan. That full-partition
> path has since completed on the 62.5 GB fast card: the complete
> write/readback and post-reinsert quick immutable-payload audit passed. This
> does not rehabilitate either historical file stager or the revoked receipt.
> A build receipt alone is not permission to boot: future physical recovery
> still requires a live target
> baseline, `WRITE_COMPLETE`/`safe_to_boot=yes`, independent post-write hashes,
> reinsertion and a fresh raw clone verification. The blocked file stagers below
> remain historical and must not be used.

1. On macOS, stage the payload to EASYROMS only. Use a receipt directory on a
   different physical disk from the TF card:

   ```sh
   bash mainline/out/r46h-easyroms-<build-id>/stage-on-macos.sh \
     --device /dev/diskN \
     --confirm-device /dev/diskN \
     --receipt-parent /Volumes/Ju/r46h-receipts
   ```

   The script verifies the exact card/profile, current BOOT files, current
   payload anchors, partition geometry, and g92 prefix. All working receipts
   stay in a private `/private/tmp` directory. The p1/g92/fdisk baseline is
   captured before anything is written below `--receipt-parent`. The script
   mounts only p3 for card writes, proves p1/partition-table/prefix stability,
   publishes `STAGE-COMPLETE` last, safely ejects the card, and only then
   copies a final receipt to the independent receipt disk.

   A random completion secret is generated at staging time. Only its SHA-256
   commitment is put on the card; the secret is revealed solely inside the
   post-eject `TARGET-TRUST-RECEIPT`. Therefore a card left after `SIGKILL`,
   power loss, or a failed final proof cannot be consumed from card markers
   alone. Preserve these three Mac-side values as literal trust anchors:

   ```sh
   RECEIPT_DIR=<RECEIPT_DIR printed by stage-on-macos.sh>
   RECEIPT_SHA256=$(awk '{print $1}' "$RECEIPT_DIR/TARGET-TRUST-RECEIPT.sha256")
   BOOTSTRAP_SHA256=$(sed -n 's/^bootstrap_target_sha256=//p' \
     "$RECEIPT_DIR/TARGET-TRUST-RECEIPT")
   printf 'receipt=%s\nbootstrap=%s\n' "$RECEIPT_SHA256" "$BOOTSTRAP_SHA256"
   ```

2. The audited g92 card has already completed a full p2 clone, offline repair
   of the clone, clean `e2fsck`, p2-only writeback, and a byte-for-byte full
   read verification. Do not repeat that full-card workflow before every test.
   For each later deployment, require the live ext4 `errors_count` to be zero
   and reject mmcblk0p2 EXT4/JBD2 error, warning, corruption, or abort records
   in the kernel log. If that online gate fails, stop and return to an offline
   read-only `e2fsck -fn` audit before any repair. Preserve or refresh a complete
   p2 recovery image before writing when the existing verified recovery image
   no longer matches the card or the read-only audit reports new structural
   damage. A merely mountable rootfs is not sufficient, but neither a passing
   gate nor a lone unchecked-state recurrence on this byte-verified card
   requires another redundant 10.7 GB clone/writeback cycle.

   The later `mounting unchecked fs` block has been resolved. A verified AArch64
   vendor `uInitrd`, v0.4, and `break=premount` were booted non-persistently with
   p2 unmounted. The first read-only check found only one deleted-inode/bitmap
   residue; the conservative repair was followed by two clean checks. Continuing
   that same boot produced `errors_count=0` and no EXT4/JBD2 warning or error.
   Do not repeat that rescue while the online gate remains clean. The subsequent
   v0.5 bootstrap failed closed before module or BOOT writes because Linux exFAT
   omitted root-default `uid=0,gid=0` from its displayed mount options. v0.6
   fixed that control-plane parser, was installed and selected, and then booted
   cleanly to the existing rootfs. Its BOOT files and EASYROMS payload formed
   the checked v0.6-to-v0.7 migration baseline; the withdrawn v0.5 receipt
   remains unusable. Canonical v0.7 was subsequently built from one clean Git
   HEAD, staged, installed, selected and cold-booted with clean root/BOOT gates.
   Its downstream host transition tuple and 396 MHz DPHY matched in hardware,
   but the panel still failed to show a stable image. v0.8 subsequently used a
   newly reviewed v0.7 baseline and a new release/payload/receipt; it did not
   reuse the historical v0.6 baseline or v0.7 completion markers.

   The completed `v0.8-bootloader-handoff` release tested only the first
   bootloader-to-kernel panel handoff. Probe leaves reset as-is and acquires
   balanced regulator references; when reset plus both regulator framework
   enable latches and voltage selectors match the expected U-Boot software
   state, the first prepare preserves that state and skips one reset/DCS replay.
   Otherwise it falls back to the existing full initialization. These checks
   are not analog rail-voltage measurements. This is not a complete DRM
   `loader_protect` implementation and does not claim continuous bootloader
   framebuffer, VOP/DSI clock, plane or logo preservation. The next
   `v0.9-adc-joystick-fix` candidate keeps that display baseline and adds only
   the ADC joystick inversion fix; it requires a new payload/receipt and
   matching v0.9 modules rather than modifying the accepted v0.8 identity.

   Boot the unchanged current kernel. Never run `install-modules.sh`,
   `switch-boot.sh`, or `bootstrap-target.sh` directly from `/roms`: p3 is
   normally mounted as `uid=1002,gid=1002,fmask=0000,dmask=0000`, so those
   paths are not a root trust boundary. First make and verify root-owned
   copies, replacing both angle-bracket values below with the **literal values
   printed on the Mac**:

   ```sh
   sudo install -d -o root -g root -m 0700 /run/r46h-deploy
   sudo install -o root -g root -m 0700 \
     /roms/r46h-<build-id>/bootstrap-target.sh \
     /run/r46h-deploy/bootstrap-target.sh
   printf '%s  %s\n' '<BOOTSTRAP_SHA256-FROM-MAC>' \
     /run/r46h-deploy/bootstrap-target.sh | sudo sha256sum -c -
   ```

   ArkOS mounts `/run` with `noexec`. Invoke the verified copy through the
   fixed `/bin/bash` path shown below; the script still proves its
   `BASH_SOURCE` real path, root ownership, `0700` mode, and external SHA-256.
   The private exFAT mount may omit `uid=0,gid=0` from `findmnt`: Linux exFAT
   deliberately suppresses global-root defaults. Deployment accepts only that
   omission or one explicit zero value, rejects every non-root or duplicate
   mapping, keeps exact `0077` masks, and independently proves `0:0:700` with
   `stat`.

   With SSH, copy the small final receipt as data and then make it root-owned:

   ```sh
   scp "$RECEIPT_DIR/TARGET-TRUST-RECEIPT" ark@<r46h-ip>:/tmp/
   ssh ark@<r46h-ip>
   sudo install -o root -g root -m 0600 /tmp/TARGET-TRUST-RECEIPT \
     /run/r46h-deploy/TARGET-TRUST-RECEIPT
   rm -f /tmp/TARGET-TRUST-RECEIPT
   ```

   Without Wi-Fi, encode it on the Mac:

   ```sh
   base64 < "$RECEIPT_DIR/TARGET-TRUST-RECEIPT"
   ```

   Then paste that Base64 text into the serial shell between the delimiters:

   ```sh
   sudo /bin/sh -c 'umask 077; base64 -d > /run/r46h-deploy/TARGET-TRUST-RECEIPT' <<'R46H_RECEIPT_B64'
   <PASTE-BASE64-FROM-MAC-HERE>
   R46H_RECEIPT_B64
   sudo chown root:root /run/r46h-deploy/TARGET-TRUST-RECEIPT
   sudo chmod 0600 /run/r46h-deploy/TARGET-TRUST-RECEIPT
   ```

   In either case, verify the receipt using the other literal Mac value:

   ```sh
   printf '%s  %s\n' '<RECEIPT_SHA256-FROM-MAC>' \
     /run/r46h-deploy/TARGET-TRUST-RECEIPT | sudo sha256sum -c -
   ```

3. Install modules only through the verified bootstrap:

   ```sh
   sudo /bin/bash /run/r46h-deploy/bootstrap-target.sh \
     --external-receipt /run/r46h-deploy/TARGET-TRUST-RECEIPT \
     --external-receipt-sha256 '<RECEIPT_SHA256-FROM-MAC>' \
     --action install-modules
   ```

   Before issuing any remount, the externally hash-anchored bootstrap runs a
   minimal ext4 `errors_count` and kernel-log preflight. This ordering matters:
   even a read-write to read-only remount may flush pre-existing exFAT metadata.
   Only after that preflight does the bootstrap record the independent initial
   read/write policies of `/roms` and its `/roms/tools` bind at
   `/opt/system/Tools`, then freeze both entry points read-only. It copies the
   complete payload into a root-owned `0700` directory and verifies the
   external receipt, random-secret commitment, exact source-list hash, exact
   file set, and every file hash. While p3 is still read-only it runs the
   complete trusted rootfs health gate again, so a potentially metadata-writing
   exFAT read-write mount cannot precede a valid health check. It performs normal (never lazy/forced)
   unmounts of Tools and `/roms`, fresh-mounts `/dev/mmcblk0p3` at a private
   `/run` path with `uid=0,gid=0,fmask=0077,dmask=0077`, and proves that this is
   p3's only reachable mount. The target scripts and all read-only inputs run
   only from the trusted copy; card writes are limited to fixed receipt and
   old-BOOT-backup paths on that private mount. Cleanup restores `/roms` with
   the audited ArkOS `uid=1002,gid=1002,fmask=0000,dmask=0000` semantics and
   restores each public mount's independently recorded initial `ro` or `rw`
   policy. The only extra payload entries tolerated are the fixed, size-bounded
   interrupted-receipt marker for the requested action; that trusted action
   removes the marker after repeating the health gate. Unknown entries and the
   other action's marker remain fatal. If any freeze, normal
   unmount, fresh mount, uniqueness proof, or restoration fails, deployment
   stops closed and preserves the trusted recovery directory.

4. **Full-policy bundles only:** after the module receipt succeeds, switch BOOT
   through the same bootstrap and the same literal receipt hash:

   ```sh
   sudo /bin/bash /run/r46h-deploy/bootstrap-target.sh \
     --external-receipt /run/r46h-deploy/TARGET-TRUST-RECEIPT \
     --external-receipt-sha256 '<RECEIPT_SHA256-FROM-MAC>' \
     --action switch-boot
   ```

   The switch first selects and verifies the v0.2 known-good fallback, retires
   the previous versioned BOOT files into its existing EASYROMS payload, then
   publishes the new versioned files and finally updates active `boot.ini`.
   The v0.2 BOOT files, U-Boot DTBs, and v0.2 module tree remain immutable.
   From immediately before that final active-file replacement until a complete
   switch receipt is verified, ordinary errors plus `INT`, `TERM`, and `HUP`
   arm a best-effort return to the verified v0.2 `boot.ini`; a failed rollback
   proof is reported as a hard warning not to reboot. `SIGKILL` and sudden power
   loss cannot run shell cleanup, so `BOOT-SWITCHED` remains the completion gate.

   Do not run this step for the Debian 13 new-card v0.9 modules-only bundle. Its
   receipt cannot authorize the action and no switch script exists. That flow
   uses the independently reviewed full-p1 candidate and a RAM-only U-Boot
   one-shot command sequence; it never replaces active v0.8 `boot.ini`.

Neither target action reboots or powers off the device. Review receipts and
reboot manually. DDR/Boot1/BL31 output uses 1500000 baud; switch to 115200 near
the exact `I/TC: OP-TEE version` line. U-Boot, the Linux console, and login all
remain at 115200 baud.

## Tests are not hardware evidence

Run the deterministic generator suite and directory-backed migration fixture:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B mainline/tests/test-generate-easyroms-bundle.py
docker run --rm --entrypoint /bin/bash \
  -e R46H_RUN_ACTION_POLICY_INTEGRATION=1 \
  -v "$PWD:/repo" arkos4clone/r46h-kernel-builder:trixie-arm64 \
  -lc 'cd /repo && PYTHONDONTWRITEBYTECODE=1 python3 mainline/tests/test-easyroms-action-policies.py -v'
bash mainline/tests/test-easyroms-deploy-fixture.sh
```

The fixture runs inside the existing arm64 builder container without passing
through any block device. It uses artifacts corresponding to the separately
hardware-booted v0.7 baseline and requires a canonical v0.8 package from the
same clean Git HEAD as the generator; a missing input is always a hard failure
and there is no skip or provenance-bypass mode.
It proves the fake v0.7 to v0.8 stage/install/switch path, attack rejection,
recovery, and ordering, but it is not evidence of a real card write, boot,
panel output, Panfrost rendering, peripherals, or Debian 13.
The action-policy fixture additionally executes both the modules-only and
default full host/target paths without exposing a physical block device. It
proves successful module publication, pre-mutation switch rejection with an
unchanged target tree, and preservation of the historical full workflow.
