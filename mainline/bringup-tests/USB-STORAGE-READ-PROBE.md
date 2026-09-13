# R46H external USB storage read gate

This attended gate closes one bounded external USB host-port path without
writing the test medium. It is intentionally separate from
`r46h-media-usb-preflight`: that earlier script only inventories the built-in
RTL8188EU and cannot prove an external connector, hotplug or data transfer.

The accepted device was an already populated, unmounted removable flash drive.
The gate did not mount it, run a filesystem checker, change authorization,
reset a USB device, or issue any block-device write. It read and hashed two
bounded raw ranges twice:

- the first 128 MiB;
- the last 16 MiB of the exact 125,829,120,000-byte device.

Repeated hashes prove stable reads of those ranges only. They are not a
whole-device digest, filesystem-consistency proof, write-path test, endurance
test or performance benchmark.

## Identity and safety contract

Before any raw read, require all of these:

- `lsusb` reports one external `048d:1234` device with serial
  `4756901203712257914`;
- sysfs binds that device to `1-1.2`, the removable SCSI disk to the same USB
  ancestry, and reports 480 Mbit/s High-Speed;
- the built-in `0bda:8179` RTL8188EU remains separately attached at `1-1.3`;
- `/dev/sda` is a block special file, removable, `TRAN=usb`, exactly
  125,829,120,000 bytes with 512-byte sectors;
- `/dev/sda` and its partition have no mount point and are absent from swaps;
- the root ext4 error counter and failed-unit count are both zero.

Stop if the device name, sysfs ancestry, serial, size, sector size or mount/swap
state differs. Never infer the target from `/dev/sda` alone: block names can
change after hotplug. Revalidate the same identity after the final read.

The accepted read commands used direct input and a hard deadline, with shell
`pipefail` enabled so a failed `dd` cannot be hidden by `sha256sum`:

```bash
sudo -n timeout -s TERM -k 2s 30s \
  dd if=/dev/sda bs=4M count=32 iflag=direct,fullblock status=none \
  | sha256sum
sudo -n timeout -s TERM -k 2s 30s \
  dd if=/dev/sda bs=4M skip=29996 count=4 iflag=direct,fullblock status=none \
  | sha256sum
```

Run each pipeline twice. PASS requires status 0 from all four pipelines,
matching hashes for both copies of each range, unchanged device identity and
geometry, no mount/swap appearance, an empty bounded dmesg delta, unchanged
zero ext4 errors and failed units, and complete deletion of `/run` health
scratch. Do not save raw USB contents on the target or host.

## Accepted 2026-08-15 result

The operator hotplugged a Chipsbank CBM2199 flash drive. Kernel evidence bound
it to DWC2 -> hub `1-1` -> external Port 2 (`1-1.2`) -> `usb-storage` ->
`/dev/sda`; the internal RTL8188EU remained on hub Port 3. The device stayed
unmounted and outside swap throughout.

The two 128 MiB reads both produced:

```text
8b8acf8c4c70f3c2b3d481c75423914083431e7e6ab79e13a99a4f5e7d22b73d
```

The two last-16-MiB reads both produced:

```text
dffab0dd410657cb30c7b2fd7f2586a4792e8472e58882b3532581f8111a646d
```

All four commands exited 0; total raw bytes read were 301,989,888. The bounded
dmesg delta was empty, USB fault count stayed zero, ext4 stayed `0 -> 0`, failed
units stayed `0 -> 0`, device size/sector/serial stayed identical, and target
tmpfs residue was zero.

The durable serial receipt is
`mainline/out/r46h-serial-logs/v08-external-usb-20260815.bin`, 10,403 bytes,
SHA-256
`ed7d91fdd2eb00761021d12718f137d33d2a9360affb2474405fd6b2c8f8f36f`.

This proves hotplug, power, enumeration and bounded stable raw reads through
the board's single external USB Host connector at USB 2.0 High-Speed. The other
physical connector is USB-DC, not a second USB Host connector, and must not be
treated as a storage-test target. USB writes, filesystem mounting, sustained
throughput and power under load remain open. The accepted read should not be
repeated without a USB-controller, DTS, connector, power or storage-device
change, or new I/O evidence.
