# R46H v0.17 cold-MMC power settle

Status: **ONE-SHOT PHYSICAL PASS / CLEANLY REMOVED**

This is one changed system-card initialization hypothesis after persistent
v0.16 reproduced the recovered 400 kHz `-84` with Linux's secondary MMC host
disabled. It is not another game, input, audio, media-write or storage-stress
test.

## Why this candidate

The exact v0.15 DTB gives system `/mmc@ff370000` no
`post-power-on-delay-ms`, so Linux 6.12 uses its default 10 ms. In that kernel,
`drivers/mmc/core/host.c` parses the property into
`host->ios.power_delay_ms`; `drivers/mmc/core/core.c` applies it once after
card power and I/O signalling are selected but before the initial clock, then
once more after the initial clock is enabled. The binding defines it as the
stability delay for I/O signalling and card power, whether or not a separate
power-sequence node exists.

The similarly named `card-detect-delay` is not this initial-power control.
The DesignWare host uses it only when a card-detect interrupt schedules later
detection work. Raising the existing mainline value from 200 ms to the factory
DTB's 800 ms would therefore be a false initial-boot experiment.

The retained exact factory R46H DTB nevertheless supplies a useful bounded
board value: its system slot uses an 800 ms detection-settle window, and its
factory trace initializes the card cleanly after substantially more elapsed
time than mainline. V0.17 applies that same **800 ms** value to the standard
initial-power property. Relative to v0.16 this is the only new variable:

- system `/mmc@ff370000` gains `post-power-on-delay-ms = <800>`;
- secondary `/mmc@ff380000` remains disabled, preserving v0.16 isolation;
- system-card supplies, card-detect GPIO, UHS modes, maximum frequency, exact
  v0.15 Image and module tree remain unchanged.

The product limitation remains **second card slot unavailable** while this
candidate is active. One clean cold sample can reject or provisionally accept
this bounded candidate, but cannot prove statistical cold-boot reliability.

## Host artifact

The builder starts from the frozen v0.15 package and exact 49,518-byte DTB
SHA-256 `4d6d4ebad3b98600b6e9a38df4ca82230335558497a9e15dd0e81ca60e304b61`.
It compiles and applies the overlay twice inside the same pinned,
network-isolated builder used for v0.16. `fdtget` must prove:

- the base has both hosts enabled and no system-card power-delay property;
- the candidate keeps system `mmc0=okay` and aliases unchanged;
- the candidate has exactly `post-power-on-delay-ms=800` on system `mmc0`;
- the candidate has secondary `mmc1=disabled`.

The source closure deliberately includes the frozen v0.16 builder because
v0.17 reuses its exact base-package identity, Git checks and isolated DT tools.
Build only from committed clean inputs:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/tests/test-r46h-v17-mmc-power-settle.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-r46h-v17-mmc-power-settle.py build
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-r46h-v17-mmc-power-settle.py validate
```

Clean source commit `6b16dfc2d6e84d906ea7d2eeec436b3516672736`
produced the frozen host artifact. A second temporary release root then rebuilt
the complete archive from the same commit and matched it byte-for-byte before
that disposable copy was removed. The accepted host identities are:

- archive
  `mainline/out/r46h-v17-mmc-power-settle/r46h-v17-mmc-power-settle.tar.gz`:
  12,517 bytes, SHA-256
  `02b6da57c039c31a95143eab1b922c14c0ac4bc60621d02dab9d07f1796409a9`;
- candidate `R46H.DTB`: 49,561 bytes, SHA-256
  `116942e7bc8691bbf6bf185dd3cbe306de2d33be8dad79a027249f9f5234b796`;
- launcher `R46H-V17.SCR`: 1,004 bytes, SHA-256
  `fb51ba442d5972f9bb98b1b96f3fe1de67c806b34a2e2f3dc044fde63cdc6b81`;
- overlay DTBO: 357 bytes, SHA-256
  `7bc5f1406984ca9a9c2d2fe0226f7af35b5e1dfb78740e888f3fd0978840fcda`;
- build receipt: 740 bytes, SHA-256
  `171091ddacfb88cf3ade5f3f795ef5f2479e369f76b774cfcece08fda08e224e`;
- source manifest: 1,012 bytes, SHA-256
  `1ea883ffe2d0d9e749ed178e00a7b44f9f71ab13d436fa73a659be821efebeb3`.

Do not rebuild or replace this accepted artifact unchanged. **Host validation
is not physical proof.**

## Target boundary

The final payload will be staged only below
`/var/lib/r46h-mmc-power-settle/v0.17-800ms-single-host` on p2. Its U-Boot
script loads the already installed exact v0.15 Image plus the candidate DTB
from p2. **p1 remains unchanged**; p3 and BOOT stay unmounted; no partition,
U-Boot environment, persistent boot script, gaming payload or user
configuration is changed.

Rediscover and verify the target address, keep SSH host-key checking enabled,
and transfer the frozen archive to
`/var/tmp/r46h-v17-mmc-power-settle.tar.gz`. Then run this exact p2-only
transaction from one healthy normal v0.15/v0.5 logistics boot:

```bash
set -eu
archive=/var/tmp/r46h-v17-mmc-power-settle.tar.gz
stage=/var/lib/r46h/.v17-mmc-power-settle-stage
target_parent=/var/lib/r46h-mmc-power-settle
target=$target_parent/v0.17-800ms-single-host
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
  02b6da57c039c31a95143eab1b922c14c0ac4bc60621d02dab9d07f1796409a9 \
  "$archive" | sha256sum -c -
printf '%s  %s\n' \
  956ab3d5a2e53afbfe964ae75850e8591b44c093b9779867b31149b7b591f68f \
  /var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/IMAGE \
  | sudo sha256sum -c -

sudo install -d -o root -g root -m 0700 "$target_parent" "$stage"
sudo tar --no-same-owner -xzf "$archive" -C "$stage"
payload=$stage/v0.17-800ms-single-host
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
mode `0400`. A mismatch stops the experiment; do not partially repair it or
copy anything to p1. Remove any task-created temporary SSH/Wi-Fi state, run
`sync`, perform a controlled poweroff and confirm it on serial. The normal
staging boot is logistics, not v0.17 acceptance; use at most one short Reset
only if the already known root-mount failure recurs.

At U-Boot enter exactly the two packaged, size-guarded lines below. They load
only p2 and must never use `saveenv`, `mmc write`, or a p1 path:

```text
ext4load mmc 1:2 0x0b000000 /var/lib/r46h-mmc-power-settle/v0.17-800ms-single-host/R46H-V17.SCR
if itest ${filesize} -eq 0x3ec; then source 0x0b000000; fi
```

After either candidate success or one Reset rescue, rehash and remove only the
disposable payload before final health checks:

```bash
set -eu
target=/var/lib/r46h-mmc-power-settle/v0.17-800ms-single-host
p1=$(readlink -f /dev/disk/by-partuuid/c9f931c9-01)
p2=$(readlink -f /dev/disk/by-partuuid/c9f931c9-02)
p3=$(readlink -f /dev/disk/by-partuuid/c9f931c9-03)
root_name=$(basename "$p2")
test "$(findmnt -rn -o PARTUUID /)" = c9f931c9-02
test -b "$p1" && test -b "$p2" && test -b "$p3"
sudo sh -c 'cd "$1" && sha256sum -c SHA256SUMS' sh "$target"
sudo rm -f -- \
  "$target/LAUNCH.txt" \
  "$target/R46H-V17.SCR" \
  "$target/R46H.DTB" \
  "$target/RECEIPT.json" \
  "$target/SHA256SUMS" \
  "$target/UBOOT-CMDS.txt" \
  "$target/r46h-v17-mmc-power-settle.dtbo"
sudo rmdir "$target"
sudo rmdir /var/lib/r46h-mmc-power-settle
test "$(cat "/sys/fs/ext4/$root_name/errors_count")" = 0
test -z "$(systemctl --failed --no-legend --plain)"
! findmnt -rn -S "$p1" >/dev/null
! findmnt -rn -S "$p3" >/dev/null
sync
```

## One bounded cold regression

This stage requires an attended operator. Rediscover the serial device for
that session. Open serial at **1500000** before cold power-on and switch to
**115200** only after the visible `I/TC: OP-TEE version` marker. Interrupt
U-Boot once and enter only the two packaged launcher lines.

Acceptance requires all of the following in one bounded cold regression:

- the exact candidate DTB and exact v0.15 Image load from their p2 paths;
- Linux probes `ff370000` as `mmc0` and never probes `ff380000`;
- live DT reports `post-power-on-delay-ms=800`, `mmc0=okay` and
  `mmc1=disabled` with aliases unchanged;
- serial timestamps show the first 800 ms wait between `Got CD GPIO` and the
  first 400 kHz bus-speed line, then the second wait after that line and before
  the next card bus transition; together they replace the v0.16 baseline's
  approximately 21 ms first gap with about 1.7 seconds before 150 MHz;
- the system card moves from 400 kHz to SDR104/150 MHz, exposes p1/p2/p3 and
  mounts exact v0.5 p2 with no initialization error, timeout or stuck-busy
  line;
- exact kernel/modules, read-only storage health, ext4 error counter and
  failed-unit count pass;
- no game, input, audio, full-media or A2 stress gate is repeated.

If root does not mount, one short Reset may rescue the unchanged persistent
v0.15 path. **Reset is rescue, not PASS.** Do not loop the candidate. After
either candidate success or rescue, rehash and remove only the seven-file p2
payload, remove its two empty directories, clean temporary SSH/Wi-Fi/transfer
state, `sync`, and end with controlled poweroff plus serial confirmation.

## Physical result

**ONE-SHOT PHYSICAL PASS (2026-08-25) / CLEANLY REMOVED.** This accepts one
bounded changed-candidate cold sample. It does not prove statistical cold-boot
reliability or authorize persistent integration without a separate
rollback-safe contract.

The ordinary logistics boot loaded exact persistent v0.15 and exact v0.5 p2,
reached `multi-user.target`, and had zero ext4 errors and failed units. No saved
Wi-Fi profile or target IPv4 address existed, so the frozen 12,517-byte archive
was sent through the already captured serial console with terminal echo
disabled and canonical-safe line wrapping. One initial unwrapped attempt
failed decoder validation after 3,071 bytes; that task-created partial file was
measured and removed before the formal transaction or target directory existed.
The replacement transfer independently reproduced archive SHA-256
`02b6da57c039c31a95143eab1b922c14c0ac4bc60621d02dab9d07f1796409a9`.
The exact transaction then rehashed the archive and v0.15 Image, published
seven `root:root` files with directory mode `0700` and file mode `0400`, left
p1/p3 unmounted, removed all transfer temporaries, synced and powered off
cleanly. Its logistics capture is
`mainline/out/r46h-serial-logs/v17-power-settle-staging-20260825T113642Z.bin`,
59,725 bytes, SHA-256
`2219929ff35432337f56a1b32387fccf5c2922f59d6cbc94dd9cad959ed57f8d`.

For the separate cold gate, the listener switched from 1500000 to 115200 only
at the exact OP-TEE marker and automatically interrupted the verified g92
autoboot prompt. U-Boot read the guarded launcher as exactly 1,004 bytes
(`0x3ec`), then loaded the exact 41,570,816-byte v0.15 Image and exact
49,561-byte candidate DTB from p2. No Reset was used. Linux instantiated only
`ff370000.mmc`; live DT reported big-endian `00 00 03 20` (800 ms),
`mmc0=okay`, `mmc1=disabled`, and unchanged aliases.

The trace corrects one pre-run marker interpretation. The DesignWare 400 kHz
bus-speed line is emitted between the two core waits, not after both:

- `Got CD GPIO` at 2.173040 to 400 kHz at 2.994702 was **821.662 ms**;
- 400 kHz to 150 MHz at 3.890746 was **896.044 ms**, consistent with the
  second 800 ms wait plus card negotiation;
- `Got CD GPIO` to 150 MHz therefore totalled **1.717706 s**.

The card then tuned successfully at phase 53, exposed the exact 58.2 GiB
p1/p2/p3 layout, mounted exact p2 PARTUUID `c9f931c9-02` and UUID
`d3130005-46a4-4d56-9001-000000000005`, and reached multi-user with no MMC
error, timeout or stuck-busy line. Exact v0.15 kernel release, its matching
module directory, zero ext4 errors, zero failed units and unmounted p1/p3
passed. The payload rehashed before its
seven files and two directories were removed; transfer/cleanup temporaries were
also absent. Final `sync`, read-only remount, complete filesystem unmount and
`Powering off.` were serial-confirmed. The cold capture is
`mainline/out/r46h-serial-logs/v17-power-settle-cold-20260825T114520Z.bin`,
59,812 bytes, SHA-256
`eda7561a6acb378adb52f3c03255adadd67e5be2f1d03048fdd306e62ee40ba7`.

p1, p3, BOOT and the U-Boot environment were never changed. The board is off,
the v0.17 p2 candidate is absent, and the next ordinary boot still selects the
persistent dual-host v0.15 DTB. Do not repeat this one-shot unchanged. The next
cold-MMC step is a separately built, rollback-safe persistent integration of
the exact accepted v0.17 DTB followed by one clean-only cold gate.
