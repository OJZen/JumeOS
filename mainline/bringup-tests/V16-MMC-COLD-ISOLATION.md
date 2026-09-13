# R46H v0.16 cold-MMC secondary-host isolation

Status: **ONE-SHOT PHYSICAL PASS / PERSISTENT COLD GATE FAIL / EXACT V0.15 ROLLBACK PASS**

This is one changed hypothesis after the v0.5 product cold boot failed to
mount root.  It is not another game, input, audio, media-write or storage
stress test.

## Why this candidate

The failed v0.5 cold attempt and every retained recovered recurrence start
`ff370000` (`mmc0`, the system TF card) and `ff380000` (`mmc1`) concurrently.
Both hosts reference the same `vcc_sd` and `vccio_sd` regulators.  The failed
attempt reached `-84` at 400 kHz, `-110` at 300 kHz and stuck-busy timeouts at
200/100 kHz; after that, `mmc1` continuously cycled the same four discovery
frequencies.  Other long captures independently show the secondary host
cycling while the regulator framework restricts its shared I/O-voltage
requests.

The factory 4.4 control has the same two controllers and rails, but its serial
trace completes the system card's transition to 150 MHz before starting the
secondary controller.  The current first-version product uses only the system
card; no accepted gate depends on `mmc1`.  The narrow candidate therefore
changes only `/mmc@ff380000/status` from `okay` to `disabled`.  System `mmc0`,
SDR104/150 MHz, the exact v0.15 Image and module tree remain unchanged.  The
explicit product limitation is **second card slot unavailable**.

The retained non-recovery evidence is
`mainline/out/r46h-serial-logs/gaming-product-v05-firstboot-20260824T063956Z.bin`:
620,192 bytes, SHA-256
`015e571c0f0f4a5ebe967a9543d5b68d58cf1e39ea4c6608c5371ec79d7b522f`.
Do not scan unrelated historical logs or repeat the failed boot to regenerate
this evidence.

## Host artifact

The builder starts from the frozen v0.15 package and its exact 49,518-byte DTB
SHA-256 `4d6d4ebad3b98600b6e9a38df4ca82230335558497a9e15dd0e81ca60e304b61`.
It compiles one target-path overlay and applies it twice inside the pinned,
network-isolated kernel builder.  Both DTBO and candidate DTB must reproduce
byte-for-byte.  `fdtget` then proves system `mmc0` remains enabled, secondary
`mmc1` is disabled and both aliases remain unchanged.

Clean source commit `48173de13e16d39a4202bd736d4e833d6d949542`
produced and independently validated the frozen host artifact.  Validation
rehashes the exact v0.15 base package, recompiles the overlay twice, reproduces
the packaged candidate by reapplying its DTBO, checks the DT aliases/statuses
with `fdtget`, and validates the deterministic U-Boot script and archive.

The accepted host identities are:

- archive
  `mainline/out/r46h-v16-mmc-cold-isolation/r46h-v16-mmc-cold-isolation.tar.gz`:
  12,466 bytes, SHA-256
  `e9d04016f03e5619c64c3a8916b361c64857a6928cbf99f43392492c3d5276d1`;
- candidate `R46H.DTB`: 49,522 bytes, SHA-256
  `7831617d4003cdbb2733433781f80625cb94e7c9d619f2f90990223b8f8d7f81`;
- launcher `R46H-V16.SCR`: 1,002 bytes, SHA-256
  `dce8be98480dd955fda974b4379445251f12e70ce283d020d7422bb5052c7745`;
- reused p2 v0.15 `IMAGE`: 41,570,816 bytes, SHA-256
  `956ab3d5a2e53afbfe964ae75850e8591b44c093b9779867b31149b7b591f68f`.

The source build commands were:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/tests/test-r46h-v16-mmc-cold-isolation.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-r46h-v16-mmc-cold-isolation.py build
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-r46h-v16-mmc-cold-isolation.py validate
```

Do not rebuild this candidate unchanged: the exact artifact above is the
accepted host evidence.  Host validation alone is neither p2 staging proof nor
physical boot proof; those separate results are recorded below.

## Target boundary

The payload is staged only below
`/var/lib/r46h-mmc-cold-isolation/v0.16-disable-secondary` on p2.  Its script
loads the already installed exact v0.15 Image and the candidate DTB from p2.
p1 remains unchanged; p3 and BOOT stay unmounted; no partition layout, U-Boot
environment, persistent boot script, game payload or user configuration is
changed.  Do not improvise a p1 copy or make this candidate persistent.

Transfer the frozen archive over the already accepted authenticated Wi-Fi path
to `/var/tmp/r46h-v16-mmc-cold-isolation.tar.gz`.  Rediscover and verify the
current target address; keep SSH host-key checking enabled.  Then run the exact
p2-only transaction below from a healthy normal v0.15/v0.5 boot.  That required
staging power-on is logistics, not another cold acceptance sample: open serial
at the required cold-start rate, do not interrupt normal U-Boot, and use at
most one short Reset only if the already known root-mount failure recurs.

```bash
set -eu
archive=/var/tmp/r46h-v16-mmc-cold-isolation.tar.gz
stage=/var/lib/r46h/.v16-mmc-cold-isolation-stage
target_parent=/var/lib/r46h-mmc-cold-isolation
target=$target_parent/v0.16-disable-secondary
p1=$(readlink -f /dev/disk/by-partuuid/c9f931c9-01)
p2=$(readlink -f /dev/disk/by-partuuid/c9f931c9-02)
p3=$(readlink -f /dev/disk/by-partuuid/c9f931c9-03)
root_name=$(basename "$p2")

test "$(uname -r)" = 6.12.99-r46h-mainline-v0.15-gaming-product
test "$(findmnt -rn -o PARTUUID /)" = c9f931c9-02
test -b "$p1" && test -b "$p2" && test -b "$p3"
test "$(cat "/sys/fs/ext4/$root_name/errors_count")" = 0
test -z "$(systemctl --failed --no-legend --plain)"
! findmnt -rn -S "$p1" >/dev/null
! findmnt -rn -S "$p3" >/dev/null
sudo test ! -e "$stage"
sudo test ! -e "$target_parent"
printf '%s  %s\n' \
  e9d04016f03e5619c64c3a8916b361c64857a6928cbf99f43392492c3d5276d1 \
  "$archive" | sha256sum -c -
printf '%s  %s\n' \
  956ab3d5a2e53afbfe964ae75850e8591b44c093b9779867b31149b7b591f68f \
  /var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/IMAGE \
  | sudo sha256sum -c -

sudo install -d -o root -g root -m 0700 "$target_parent" "$stage"
sudo tar --no-same-owner -xzf "$archive" -C "$stage"
payload=$stage/v0.16-disable-secondary
sudo test "$(sudo find "$payload" -mindepth 1 -maxdepth 1 -type f | wc -l)" -eq 7
sudo test -z "$(sudo find "$payload" -mindepth 1 -maxdepth 1 ! -type f -print)"
sudo chown -R root:root "$payload"
sudo chmod 0700 "$payload"
sudo find "$payload" -mindepth 1 -maxdepth 1 -type f -exec chmod 0400 {} +
sudo sh -c 'cd "$1" && sha256sum -c SHA256SUMS' sh "$payload"
sudo mv -T --no-clobber "$payload" "$target"
sudo test ! -e "$payload"
sudo sh -c 'cd "$1" && sha256sum -c SHA256SUMS' sh "$target"
sudo rmdir "$stage"
rm -f "$archive"
sync
! findmnt -rn -S "$p1" >/dev/null
! findmnt -rn -S "$p3" >/dev/null
```

The seven files must remain root-owned, with directory mode `0700` and file
mode `0400`.  A mismatch stops the experiment; do not partially repair or copy
anything to p1.  After the staging checks pass, run `sync`, use a controlled
poweroff and confirm it on serial.  Leave the exact payload in place for the
single attended cold start; do not turn that staging boot into another
functional regression.

At the U-Boot prompt, enter exactly these two reviewed, size-guarded lines and
never use `saveenv`:

```text
ext4load mmc 1:2 0x0b000000 /var/lib/r46h-mmc-cold-isolation/v0.16-disable-secondary/R46H-V16.SCR
if itest ${filesize} -eq 0x3ea; then source 0x0b000000; fi
```

After either an accepted candidate boot or one Reset rescue, rehash and remove
only this disposable p2 payload before the final controlled poweroff:

```bash
set -eu
target=/var/lib/r46h-mmc-cold-isolation/v0.16-disable-secondary
p1=$(readlink -f /dev/disk/by-partuuid/c9f931c9-01)
p2=$(readlink -f /dev/disk/by-partuuid/c9f931c9-02)
p3=$(readlink -f /dev/disk/by-partuuid/c9f931c9-03)
root_name=$(basename "$p2")
test "$(findmnt -rn -o PARTUUID /)" = c9f931c9-02
test -b "$p1" && test -b "$p2" && test -b "$p3"
sudo sh -c 'cd "$1" && sha256sum -c SHA256SUMS' sh "$target"
sudo rm -f -- \
  "$target/LAUNCH.txt" \
  "$target/R46H-V16.SCR" \
  "$target/R46H.DTB" \
  "$target/RECEIPT.json" \
  "$target/SHA256SUMS" \
  "$target/UBOOT-CMDS.txt" \
  "$target/r46h-v16-mmc-cold-isolation.dtbo"
sudo rmdir "$target"
sudo rmdir /var/lib/r46h-mmc-cold-isolation
test "$(cat "/sys/fs/ext4/$root_name/errors_count")" = 0
test -z "$(systemctl --failed --no-legend --plain)"
! findmnt -rn -S "$p1" >/dev/null
! findmnt -rn -S "$p3" >/dev/null
sync
```

## One bounded cold regression

This requires an attended operator.  Rediscover the serial device for this
session.  For a real cold start, open it at **1500000** before power and switch
to **115200** only after the visible `I/TC: OP-TEE version` marker.  Interrupt
U-Boot and enter only the two reviewed launcher lines.

Acceptance requires all of the following in one bounded cold regression:

- exact candidate DTB was loaded from the versioned p2 path;
- Linux probes `ff370000` as `mmc0` and never probes `ff380000`;
- the system card enumerates, exposes p1/p2/p3 and mounts exact p2 without any
  400/300/200/100 kHz initialization error;
- it reaches multi-user on exact v0.15 with the existing matching modules;
- read-only storage audit, ext4 error counter and failed-unit count stay clean;
- no game, input, audio or media-write gate is repeated.

If root does not mount, one short Reset may rescue the unchanged persistent
v0.15 path.  **Reset is rescue, not PASS.**  Do not loop the candidate.  End a
successful run only after the exact payload cleanup above, `sync`, controlled
poweroff and serial confirmation.  If rescue is needed, perform that same
cleanup from the rescued normal boot before controlled poweroff.

## Physical result

The exact contract ran once on 2026-08-24 and **PASSed** without Reset.  The
ordinary persistent-v0.15 staging boot was logistics rather than candidate
acceptance.  It reproduced one bounded 400 kHz `-84`, recovered at 300 kHz,
reached SDR104/150 MHz and mounted exact v0.5 p2.  The archive and installed
v0.15 Image rehashed exact before the seven-file payload was published twice
with the required ownership and modes.  The temporary Wi-Fi profile, temporary
SSH key, transfer archive and staging directory were removed; the retained
candidate rehashed exact before controlled poweroff.  Its 65,651-byte capture
is
`mainline/out/r46h-serial-logs/v16-staging-boot-20260824T092131Z.bin`,
SHA-256
`261b17606b19500c7f00aefbd84f2ca54280555af554a8c1ff63d0ae207b93ad`.
This is the thirteenth retained recovered occurrence for the unchanged
dual-host mainline DT, not a candidate fault.

For the candidate cold boot, capture opened at 1,500,000 before power-on and
switched to 115,200 only after the OP-TEE marker.  One autoboot interrupt and
the two frozen commands loaded exactly one 1,002-byte script, one
41,570,816-byte v0.15 Image and the 49,522-byte candidate DTB.  Linux then:

- probed only `ff370000` as `mmc0`; no Linux `ff380000`, `mmc_host mmc1` or
  `mmc1:` line occurred;
- moved `mmc0` once from 400 kHz directly to 150 MHz, with no initialization
  error, command timeout or stuck-busy line;
- enumerated p1/p2/p3, mounted exact p2 and reached multi-user on exact v0.15;
- matched the four checked module vermagic values and the live DT statuses
  `mmc0=okay`, `mmc1=disabled`, with both aliases unchanged;
- passed the exact installed product storage audit at SDR104/150 MHz with zero
  ext4 errors and `a2_command_queue=not-available`.

One obsolete generic v0.8 adaptation helper was also invoked once in read-only
mode.  It returned seven expected identity mismatches against current
v0.15/v0.5: kernel, firstboot marker, root UUID and four module vermagic checks.
Its actual storage checks, before/after ext4 counters, full-boot fault scan and
cleanup all passed.  That out-of-scope helper result is not candidate evidence;
the helper and its transfer file were removed.  The required product audit was
the exact 2,757-byte installed tool with SHA-256
`08ed33dace8a94a6b129d72896c8e6a657b32d15c74d9ecf48df99a9f49ae95c`,
and it passed once as recorded above.

The candidate payload rehashed exact after all checks, then only its seven
files and two directories were removed.  Final MMC/block/ext4 fault matches,
ext4 errors, failed units and p1/p3 mounts were all zero.  `sync`, root
read-only remount, complete filesystem unmount and `Powering off.` passed.  The
87,023-byte candidate capture is
`mainline/out/r46h-serial-logs/v16-disable-secondary-cold-20260824T093615Z.bin`,
SHA-256
`54c081d0ea2ed2dd4345de2e85e348a9c78e1e0fc0357f7df216b7e326adcba5`.

This accepts the exact v0.16 isolation candidate for one bounded physical
sample.  It does not prove that concurrent probing is the sole root cause or
establish statistical cold-boot reliability.  The later persistent gate below
did not reproduce its clean initialization and was rolled back, so active BOOT
again uses the earlier v0.15 dual-host DTB. The two versioned v0.16 files remain
inert for audit. Enabling this mitigation deliberately makes the second card
slot unavailable. Do not repeat either unchanged sample.

The rollback-safe persistent integration source now lives in
[`../gaming-product-v16-boot-promotion/README.md`](../gaming-product-v16-boot-promotion/README.md).
The first integration generation from clean source
`e47adf35182ed5a163bb08296e08b7642c50b766` was revoked after target preflight
found the fixed baseline's unmodelled `.fseventsd` directory before any p1
write. Complete raw p1 still reproduced `042ad4ad...`; this was a fail-closed
classifier omission, not media drift. Commit
`408baa52f95d1c66c321ccc820a4481cb7ac2266` added `.fseventsd` as the
twenty-ninth required base entry while preserving unsafe-type and unknown-entry
rejection. It produced independently validated generation
`build-408baa52f95d-99d162b5d920`: 29,123 bytes, SHA-256
`99d162b5d920f14108d9d7ff725f96f3e0e52d20dbd713fac46a4a53023ad042`,
with receipt SHA-256
`e19021298ff0a5f86dbf5cace32392828bef90e4e0f4faf5669653836d896268`.

Corrected target preflight, prepare, retained preflight and activation all
passed. The activation selected exact v0.16, retained exact v0.15/v0.10/v0.8
fallbacks and produced p1 SHA-256
`d6ad4dd6b6716754227731203fdc7f871cb2a750fb6d52444a0688b45d70d252`;
`saveenv` was not used. The separately contracted serial-first cold power-on
then loaded the 1,449-byte v0.16 script, existing 14,925,282-byte v0.15 Image
and exact 49,522-byte candidate DTB without an autoboot interrupt or Reset.
Linux probed only `ff370000/mmc0`, but the system card emitted one `-84` at
400 kHz before its 300 kHz retry, SDR104/150 MHz enumeration, exact v0.5 root
mount and multi-user. No Linux secondary-controller, later block-I/O or ext4
fault occurred.

The fixed clean-only postflight correctly rejected that recovered sequence
with `persistent v0.16 boot contains a forbidden storage marker` and did not
publish completion. Exact rollback restored active v0.15 and retained the two
candidate files inert. Final preflight passed as `state=prepared`,
`status=rollback-complete`, `mmc_init=recovered-known-open`, raw p1 SHA-256
`7d3197852284c7feaf0034489310cbe4eb14cb73f79b4b94b733b1cac004a18e`
and unchanged prefix
`3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3`.
Temporary transfer, SSH and Wi-Fi state were removed; failed-unit, ext4-error
and p1/p3-mount counts were zero before `sync` and serial-confirmed
`Powering off.`

The persistent cold/rollback capture is 62,701 bytes, SHA-256
`895a2ebaca0ec88f936d53142009716b80d99d72ee9214b2afdd1245d8b703b1`,
at
`mainline/out/r46h-serial-logs/v16-persistent-coldboot-20260824T125155Z.bin`.
Transaction and activation capture identities are kept in the linked promotion
runbook. This proves the wrapper's fail-closed rollback path, not persistent
cold acceptance. Disabling the secondary controller is not sufficient to
eliminate the recovered system-card initialization error. The next cold test
must use a changed system-card power/initialization-timing hypothesis; no game,
input, audio or media rewrite is needed.
