# R46H v0.11 USB-DC one-shot gate

This is the rollback-safe hardware gate for
`6.12.99-r46h-mainline-v0.11-usb-dc-detect`. It deliberately avoids another
TF-card write or remove/reinsert cycle. U-Boot reads an exact Image and DTB
from a separate FAT32 USB drive, boots the existing root partition read-only
into an `init=/bin/bash` rescue shell, and Linux loads only the matching
`rk817_charger.ko` into memory. A later ordinary reset still selects the
unchanged v0.8 `boot.ini` on the TF card.

The gate proves only the optional GPIO-backed `POWER_SUPPLY_PROP_ONLINE`
contract and bounded system health. It does not enable or tune charging, prove
the direction or magnitude of battery current, validate charge limits, or
authorize unattended charging.

## Immutable host input

Build only from a committed clean source scope:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-v11-usb-one-shot.py build
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-v11-usb-one-shot.py validate
```

The builder consumes only the canonical v0.11 package tar with SHA-256
`771c3149a44ab14fa2d1a3d24f1589677fbc85bed84074aebe6e43561292f2b7`.
It independently validates the complete package, freezes the exact Image,
DTB and no-dependency charger module, compiles the observer twice in the
pinned ARM64 builder, and publishes an immutable generation under
`mainline/out/r46h-v11-usb-one-shot/builds/`. `CURRENT` selects one generation;
copy only that generation's `R46HV11` directory.

The accepted disposable transport is the USB `346d:5678` device with serial
`8447981125795107445` and exact whole size 62,914,560,000 bytes. Its preparation
is destructive and is authorized only because the operator explicitly marked
this exact drive disposable. The macOS stager revalidates size, USB
VID/PID/serial, external/removable/physical flags and device confirmation before
formatting it as one MBR/FAT32 volume named `R46HUSB`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/stage-v11-usb-one-shot-macos.py prepare \
  --device /dev/disk12 --confirm-device /dev/disk12
```

After a clean immutable generation exists, the same tool performs a no-clobber
copy, full per-file readback, repeated device identity check and safe eject:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/stage-v11-usb-one-shot-macos.py stage \
  --device /dev/disk12 --confirm-device /dev/disk12 \
  --volume /Volumes/R46HUSB
```

macOS may materialize `._*` AppleDouble sidecars on FAT32 even when the stager
copies only file data. The stager accepts and removes only sidecars whose names
correspond to the exact payload members. A retry may resume only when every
already-present payload file has the expected size and SHA-256; an unknown or
different member remains a hard failure and is never overwritten or deleted.

Do not replace an existing `R46HV11` directory or use the TF card's EASYROMS
filesystem as substitute transport. A different USB drive requires a new,
reviewed identity contract; never weaken the exact-device constants at runtime.

## One-shot boot boundary

The audited g92 prefix contains U-Boot's `usb`, `fatload`, `unzip`, `booti` and
`source` commands. Actual USB boot remains a hardware gate: at the 115200-baud
U-Boot prompt, first enumerate the drive and load only the checked script:

```text
usb start
fatload usb 0:1 0x02000000 R46HV11/BOOT.INI
```

Compare `${filesize}` with the exact `BOOT_SCRIPT_SIZE` printed by the immutable
builder. Run `source 0x02000000` only after that size matches. The script checks
the compressed Image, decompressed Image and DTB sizes before `booti`. It never
runs `saveenv`, changes the active TF `boot.ini`, or writes any TF partition.
Any load/size/unzip failure must stop at the prompt; reset normally to return to
v0.8. The one-shot command line contains `rootwait ro init=/bin/bash`; it does
not contain `rw`, filesystem repair, or a normal userspace boot that could
remount p2 read-write.

## Linux observation

Accept only the exact v0.11 release in the read-only rescue shell with root
still mounted `ro` from `PARTUUID=c9f931c9-02`. Do not start systemd or remount
root. Mount only procfs, sysfs and a fresh tmpfs on `/run`; devtmpfs is built in.
The v0.11 module tree is intentionally not installed for this narrow gate.
Identify the same USB drive by USB serial plus block ancestry, require
`/dev/sda1` to be unmounted and outside swap, then mount it read-only on
`/run/r46h-v11-usb` with `nosuid,nodev,noexec`. Verify
`R46HV11/SHA256SUMS` and `PAYLOAD.COMPLETE` before using any member.

Load only `CHARGER.KO` after its exact SHA-256
`bf40b5a7c4ce96db45536b97cc2b5f7d94e9047aa822168cf534e7c5cc915416`
and 27,024-byte size match. Copy `OBSERVER` into root-owned `/run`, unmount the
USB drive, verify the copied observer digest, and run it in this attended order:

1. USB-DC disconnected: `--expect-disconnected` must report five stable
   `online=0` samples.
2. Connect USB-DC once: `--expect-connected` must report five stable `online=1`
   samples and a larger `rk817_dc_det` IRQ count.
3. Disconnect USB-DC once: `--expect-disconnected` must return to stable
   `online=0` and the IRQ count must increase again.

The observer also proves that GPIO0_B3 is owned by consumer `rk817-dc-det` and
that the live DT contains the exact active-high property. It only reads GPIO
line metadata and power-supply attributes; it never requests the line, drives
an output, or writes a persistent file.

Capture the root mount flags, root ext4 `errors_count`, bounded dmesg and the two
PMIC plug IRQ counters before module load and after the final disconnected
sample. There is intentionally no systemd failed-unit gate because systemd is
never started. PASS requires root to stay read-only, no new
MMC/ext4/GPIO/charger/IOMMU/kernel fault, unchanged zero ext4 errors, and no
persistent target write. Record battery status/current/voltage exactly as
observed, but do not make them acceptance criteria. Remove tmpfs copies, run
`sync` only as a conservative device barrier, and power off directly from the
rescue shell with `/sbin/poweroff -f`; confirm the serial power-down marker
before removing power.

## Hardware result (2026-08-15)

The GPIO-backed ONLINE contract passed on hardware using immutable generation
`build-0691be4b1c6d-db1449d74288`. The captured serial log is external evidence:

- path: `/Volumes/Ju/r46h-serial-logs/v11-usb-dc-20260815-215628.log`
- size: 43,541 bytes
- SHA-256: `28cf45861aefa732b664eaeaa4a13df8dad7fdadc2c44d93005035d85d338067`

U-Boot enumerated one USB storage device, read the checked `BOOT.INI` as exactly
1,308 bytes (`filesize=0x51c`), and booted the exact
`6.12.99-r46h-mainline-v0.11-usb-dc-detect` kernel. Linux matched USB
`346d:5678`, serial `8447981125795107445`, and mounted its payload FAT32
partition read-only. All six checksums, the checksum-file digest, both copied
tmpfs artifacts and their sizes matched before the USB partition was unmounted.

The attended observations were:

| Physical phase | `ONLINE` | `rk817_dc_det` IRQ total | Result |
| --- | ---: | ---: | --- |
| initially connected | 1 | 0 | pass |
| disconnected | 0 | 1 | pass |
| reconnected | 1 | 15 | pass |
| finally disconnected | 0 | 16 | pass |

Each phase comprised five stable samples. GPIO0_B3 was owned by
`rk817-dc-det`; the exact release, target model and active-high DT property all
passed. Root remained `ext4 ro,relatime`, the ext4 error counter remained
`0 -> 0`, and the post-module dmesg delta contained only:

```text
rk817-charger ...: Invalid charge termination 52000, keeping default
```

The rescue shell removed its tmpfs copies, emitted the qualified
`result=online-contract-pass` marker and reached `Powering off.`. This closes
only the GPIO-backed ONLINE detection gap. It does not prove charging:
`charger_voltage_uv` stayed 0, `usb_type` was `Unknown [DCP]`, and battery state
varied between `Discharging` and `Not charging` with small instantaneous current
samples.

Two persistence/configuration qualifications remain explicit:

1. Root mounted read-only, but boot logged `orphan cleanup on readonly fs`.
   Therefore this run does not prove that no TF metadata write occurred. A
   stricter future persistence run must begin from an offline-clean filesystem
   and suppress ext4 recovery during the one-shot mount.
2. DTS currently supplies `charge-term-current-microamp = <52000>`, which this
   driver rejects and replaces with its default. Correcting and separately
   validating that charging policy is outside the ONLINE-only v0.11 change.

The observer's `persistent-write=no` field describes the observer process only;
it must not be promoted into a whole-boot persistence claim.
