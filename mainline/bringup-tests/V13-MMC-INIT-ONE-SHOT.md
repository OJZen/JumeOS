# R46H v0.13 cold-MMC initialization one-shot

Status: **HOST BUILD PASS / PHYSICAL SAMPLE COMPLETE (ORIGINAL SIGNATURE INCONCLUSIVE) / TARGET CLEAN**

This is one bounded diagnostic for the intermittent first-attempt
`mmc0: error -84 whilst initialising SD card`. It must identify the failed
request when the signature reproduces. It is not a card stress test, a storage
qualification loop or a new persistent kernel.

## Source boundary

The accepted v0.10 build came from commit
`fd3a7dbcbad46ce9c437b2244f95cbec22f1f314`. From that source to the v0.12
host candidate, the R46H config changed only `LOCALVERSION`; the board DTS
changed only the RK817 `dc-det-gpios` input and charge-termination property.
Neither change touches the MMC node or the pre-root MMC path. The intervening
driver/binding change is confined to the modular RK817 charger.

v0.13 keeps that v0.10-equivalent MMC/DTS baseline and adds exactly patch
`0010-mmc-dw-log-request-errors.patch` to Linux 6.12.99. The patch changes only
`drivers/mmc/host/dw_mmc.c`. Successful requests remain silent. A failed
command records host, opcode, argument, raw command interrupt status and
errno; a failed data phase records the same request identity, raw data status
and errno. It does not change retry order, clock, maximum
frequency, bus timing, signal voltage, power sequencing or request completion.

The diagnostic uses an independent release identity:

```text
6.12.99-r46h-mainline-v0.13-mmc-init-observe
```

## Host build gate

Build only from a committed, clean source tree:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/tests/test-r46h-mmc-init-observe.py -v

mainline/scripts/build-kernel.sh \
  --build-id v0.13-mmc-init-observe \
  --root-spec PARTUUID=c9f931c9-02
```

The host gate passed from clean source commit
`87b3d0954644409f03469b0cfcd33567ec8757ac`. The official
`linux-6.12.99.tar.xz` SHA-256 is
`6a477222c132033381cda981eb0127f29fbcbba17e820283bc21290f8e408629`;
the committed mainline source snapshot SHA-256 is
`cdc888bc11cfaccdb00f04f384c12e4124726ca3f92d06a31e409dea3e9280ab`.
The 270-file source manifest independently matched every Git blob and has
SHA-256
`a6bf1ff0d99d7bf0f2a7147f85e1e94d4c55ef0d697bcc08683db11318419868`.
The full affected patch-series suite passed 69 tests and the deployment archive
suite passed another seven. The v0.13 patch itself passed
`checkpatch.pl --strict --no-tree` with zero errors and warnings.

Pinned build outputs are:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| raw `Image` | 41,570,816 | `cca1a3d958a2edc713f6dcfeebbac157224fdae44015b2b6356ac02db84b837f` |
| `rk3326-r46h.dtb` | 49,518 | `d1b035ee09ed0c44ccad62304f0c588d302c6055f634e65390850163cceba8ad` |
| kernel config | 302,008 | `8654e336ccd3a0f1e842bac96b51ef5cd41cfdd4f9707ecb54f5bbf5469ea493` |
| package tar | 33,262,229 | `9b8b6a011c0c965058cfe9a3b8e7a05f110097efafe1e725dc763d7a13c1bb2f` |

The package manifest and payload-manifest SHA-256 values are respectively
`a8637a8a7364f240c33aaa3b17773f5559cddb74bf351eab40a2a37e1b9c02a4`
and
`c762176c4f351498f93957d660664a3e4e23a6b2769d5c4ba4ad65966b1b2c93`;
the 1,276-module tree SHA-256 is
`8df4eb1e57722d15614a7f942b8752a76196c8333d6f7ad6ab3aa5f76e0d78c7`.
The built Image contains both exact `R46H_MMC_*_ERROR` format strings. Compared
with v0.12, the config differs only in `LOCALVERSION` and the DTB is
byte-identical; the source diagnostic delta is confined to the 12 added lines
in `drivers/mmc/host/dw_mmc.c`. This host proof does not become physical proof.

## Rollback-safe deployment contract

Clean builder commit `29132af4ed839837358ddad49d1e673fa38f396c`
produced the deterministic p2 payload:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/tests/test-v13-mmc-one-shot.py -v
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-v13-mmc-one-shot.py build
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-v13-mmc-one-shot.py validate
```

The only accepted transfer archive is
`mainline/out/r46h-v13-mmc-one-shot/r46h-v13-mmc-init-one-shot.tar.gz`,
14,792,602 bytes, SHA-256
`31da691b2831540ad01d196ed00536dfb51357144de10155a5dd115b619cf5f9`.
It contains deterministic 14,921,070-byte `IMAGE.GZ` with SHA-256
`3ba9ea56b01d3fd4b9f996f6d26604e35f9b968ed95b673179d68075af5440dd`,
the exact DTB above and a 1,387-byte U-Boot transcript with SHA-256
`39e148ba4933322cecf992f545b02d5e332b98950eb236ef6eb32e30cf08e23d`.
The archive, member set, root-only modes, raw decompressed Image, source blobs,
package provenance and generated scripts all passed post-publication
validation. The superseded pre-`rootflags=noload` archive was deleted.

Transfer the accepted archive over the already proved authenticated Wi-Fi
path to `/var/tmp`, then run this exact root-owned p2 transaction from normal
v0.10. Replace only `HOST:PORT` with the current read-only host endpoint:

```bash
archive=/var/tmp/r46h-v13-mmc-init-one-shot.tar.gz
curl --fail --location --output "$archive" \
  http://HOST:PORT/r46h-v13-mmc-init-one-shot.tar.gz
printf '%s  %s\n' \
  31da691b2831540ad01d196ed00536dfb51357144de10155a5dd115b619cf5f9 \
  "$archive" | sha256sum -c -

sudo test ! -e /var/lib/r46h/.v13-mmc-one-shot-extract
sudo test ! -e /run/r46h-mmc-init-one-shot-v0.13
sudo install -d -o root -g root -m 0700 \
  /var/lib/r46h/.v13-mmc-one-shot-extract
sudo tar --no-same-owner -xzf "$archive" \
  -C /var/lib/r46h/.v13-mmc-one-shot-extract
sudo install -d -o root -g root -m 0700 \
  /run/r46h-mmc-init-one-shot-v0.13
sudo mount --bind \
  /var/lib/r46h/.v13-mmc-one-shot-extract/r46h-mmc-init-one-shot-v0.13 \
  /run/r46h-mmc-init-one-shot-v0.13
sudo /bin/bash /run/r46h-mmc-init-one-shot-v0.13/install.sh
sudo umount /run/r46h-mmc-init-one-shot-v0.13
sudo rmdir /run/r46h-mmc-init-one-shot-v0.13
sudo rm -f /var/lib/r46h/.v13-mmc-one-shot-extract/r46h-mmc-init-one-shot-v0.13/{IMAGE.GZ,PAYLOAD.COMPLETE,PAYLOAD.json,R46H.DTB,RECEIPT,SHA256SUMS,UBOOT-CMDS.txt,install.sh,remove.sh}
sudo rmdir \
  /var/lib/r46h/.v13-mmc-one-shot-extract/r46h-mmc-init-one-shot-v0.13 \
  /var/lib/r46h/.v13-mmc-one-shot-extract
rm -f "$archive"
```

The installer rejects the wrong running v0.10 identity, wrong root PARTUUID,
non-zero ext4 error count, failed systemd units, unexpected hashes or links,
pre-existing destination and any writable BOOT mount. It atomically publishes
only `/var/lib/r46h-mmc-init-one-shot/v0.13-mmc-init-observe`, calls `sync`,
and leaves p1 untouched. Rehash the installed transcript before poweroff:

```bash
sudo wc -c \
  /var/lib/r46h-mmc-init-one-shot/v0.13-mmc-init-observe/UBOOT-CMDS.txt
sudo sha256sum \
  /var/lib/r46h-mmc-init-one-shot/v0.13-mmc-init-observe/UBOOT-CMDS.txt
```

The generated U-Boot commands load both candidate files from the versioned p2
staging directory, verify the compressed Image, decompressed Image and DTB byte
sizes, and boot with
`rootwait ro rootflags=noload init=/bin/bash`. `rootflags=noload` prevents ext4
journal load/replay, but the physical sample confirmed that it does not prevent
ext4 orphan cleanup on a read-only mount. The commands do not read a candidate
from p1, write an environment variable persistently or alter the normal boot
script. The active p1 remains unchanged and the exact v0.10 boot remains the
fallback. `UBOOT-CMDS.txt` is a reviewable plain-text transcript, not a legacy
U-Boot script image; this board's g92 U-Boot rejects it with `Wrong image format
for "source" command`. Interrupt autoboot and enter only its verified commands
individually. You must never use `saveenv`.

## Single physical sample

This experiment requires an attended operator. Rediscover the CH340 device and
record whether USB-DC is absent or present. Open serial at **1500000** before
power-on; switch to **115200** only after the visible
`I/TC: OP-TEE version` marker. Interrupt U-Boot, load the staged one-shot and
capture the complete Linux initialization attempt.

At the rescue prompt, mount only procfs and sysfs; do not remount root or start
systemd:

```bash
mount -t proc proc /proc
mount -t sysfs sysfs /sys
uname -r
cat /proc/version
findmnt -rn -o SOURCE,FSTYPE,OPTIONS /
cat /sys/fs/ext4/mmcblk0p2/errors_count
dmesg | grep -E 'R46H_MMC_|mmc0:|mmcblk0|EXT4-fs|JBD2'
```

Required evidence is:

- exact v0.13 `/proc/version` identity and the expected read-only p2 root;
- the complete 400 kHz attempt and selected retry frequency, if any;
- every `R46H_MMC_CMD_ERROR` / `R46H_MMC_DATA_ERROR` line before the final
  generic core result;
- card identity, p1/p2/p3 enumeration and root mount;
- root ext4 error counter plus later MMC, EXT4 and JBD2 fault scan;
- confirmation that systemd failed-unit state is not applicable under the
  deliberate `init=/bin/bash` rescue boot.

If `-84` does not reproduce, record the run as an **inconclusive diagnostic
sample** and do not loop. If it reproduces but no diagnostic marker identifies
the request, stop and treat the instrumentation as insufficient. Keep the card
accepted only when the first attempt fails, a lower-frequency retry recovers,
all partitions appear and no later storage or ext4 fault follows.

Finish with `sync`, keep p2 read-only, invoke `/sbin/poweroff -f` and wait for
serial poweroff confirmation. Do not reboot merely to prove
fallback. During the next normal v0.10 use, verify the kernel identity and zero
failed units, then remove the versioned p2 staging directory with its guarded
helper:

```bash
sudo /bin/bash \
  /var/lib/r46h-mmc-init-one-shot/v0.13-mmc-init-observe/REMOVE.sh
```

Update the experiment ledger only after the physical evidence is complete.

## Accepted physical sample (2026-08-17)

The attended run rediscovered CH340 as `/dev/cu.usbserial-3140`, kept USB-DC
absent, opened serial at 1500000 before power and switched to 115200 only at the
OP-TEE marker. The target first staged the exact accepted archive over the
strict host-key-checked Wi-Fi path. Every installed payload hash and mode
matched, p1 remained unmounted, ext4 `errors_count` and the failed-unit count
were zero, and all transfer/extraction residue was removed before poweroff.

That staging boot itself produced another instance of the original v0.10
signature: 400 kHz `mmc0: error -84`, automatic 300 kHz retry, SDR104/150 MHz,
successful tuning at phase 46 and complete p1/p2/p3 enumeration. Its 59,863-byte
serial log is
`mainline/out/r46h-serial-logs/v010-v13-staging-20260817.bin`, SHA-256
`3020aee389e57246f9b500fe3990ac8dc476cf588c53e6ca2eee1225307fa571`.

For the bounded v0.13 cold sample, U-Boot independently loaded the installed
1,387-byte transcript and verified its expected `0x56b` size. Direct `source`
returned the documented format error without starting a kernel or changing
storage. Entering the same reviewed commands individually then passed all three
size gates: compressed Image `0xe3ad6e`, raw Image `0x27a5200` and DTB `0xc16e`.
The exact `6.12.99-r46h-mainline-v0.13-mmc-init-observe` kernel booted.

This v0.13 sample did **not** reproduce the original 400 kHz generic
`mmc0: error -84 whilst initialising SD card` followed by a 300 kHz retry, so it
is inconclusive for the failing request behind that intermittent signature. It
did prove that the instrumentation works and separately localized `-84` during
SDR104 tuning to opcode 19 (`CMD19`, argument zero) at 150 MHz. Observed raw
status pairs included data `0x88` with command `0x46`, and later data `0x8088`
with command `0x44`; intervening CMD19 attempts also reported `-5` and `-110`.
Tuning then succeeded at phase 69, the card enumerated as SDR104 with p1/p2/p3,
and p2 mounted `ro,relatime,norecovery`.

The rescue check reported ext4 `errors_count=0` and no later MMC, EXT4 or JBD2
fault. It also logged `orphan cleanup on readonly fs`, establishing the
`noload` limitation above. Systemd was deliberately not started. `sync` and
`/sbin/poweroff -f` reached serial `Powering off.` The 33,284-byte capture is
`mainline/out/r46h-serial-logs/v013-mmc-init-one-shot-20260817.bin`, SHA-256
`d87a70c05032881dbf9997952ac1a514b9d6b2519f27cc5020da062fcc227ad4`.

One following ordinary cold boot used unchanged p1 and exact v0.10, reached
multi-user with ext4 `errors_count=0` and no failed unit, and did not reproduce
the original generic initialization error. The guarded removal helper returned
`PASS`, the versioned p2 staging path was absent afterward, and controlled
systemd poweroff remounted p2 read-only, unmounted every filesystem and reached
`systemd-shutdown: Powering off`; five later seconds were silent. That
56,696-byte capture is
`mainline/out/r46h-serial-logs/v010-fallback-remove-20260817.bin`, SHA-256
`fac63f60e9f71a5f6cc0c504bf2e078a16794bbe3cea0a3bc9ab4b887177ccdc`.

Do not loop this sample. The original cold-initialization issue remains open,
but the card remains accepted because every captured recurrence has recovered
before root mount and no post-initialization storage or filesystem fault has
followed. Reuse this diagnostic only alongside a separately required cold boot
or after a new hypothesis changes the evidence contract.
