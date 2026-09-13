# Examples

`profile-v2.json` is a schema fixture for a 4096-byte all-zero simulated
medium. It is not a hardware profile and cannot be used by a native backend.

`profiles/hl-r46h-v22-g92-62534975488-v2.json` is the strict-v2, read-only
identity fixture for the exact 62,534,975,488-byte R46H fast-card layout. It is
a strict-v2 layout mapping derived from
`mainline/deploy/profiles/hl-r46h-v22-g92-62534975488-v1.json`. Retained v1
identity fields map `FDisk_partition_scheme` to `mbr` and move volume UUID/
PARTUUID values under each partition's `identifiers` object. Strict v2 also
records independently audited MBR boot/type bytes and normalized `fat32`,
`ext4`, and `exfat` filesystem names. Legacy fallback policy is absent.
The resulting layout ID covers the 16 MiB prefix (which can contain bootloader
bytes), MBR, geometry, filesystem signatures, and identifiers. It does not
hash any partition in full, so it is not a whole-card content or clone digest.

The hardware fixture authorizes comparison only. It is not a write plan, does
not grant a destructive capability, and must not be used to infer one. The
native macOS backend remains responsible for independently discovering the
whole-device identity before a read-only audit.

A write plan must bind `target_stable_id` to the canonical absolute simulator
file path, so no checked-in plan can be portable. Generate test plans in a
private directory under `mainline/out/.cache` and delete them after the test.
