# R46H Debian 13 gaming p2 v0.7

Status: **HOST + P2 MEDIA + PHYSICAL PASS**

This is the narrow successor to the accepted p2 v0.6 image. It freezes the
exact renderer payload v0.6 that already passed its guarded live-target update,
without rebuilding Debian or changing BOOT, kernel, packages, cores, RetroArch
configuration, ALSA policy, systemd services or p3 storage policy.

The builder is host-only. It never opens a block device, uses the network or
touches p1, p3, BOOT, U-Boot state, target credentials or the running R46H.
Target acceptance of the input payload does not itself prove this composed
image. The later media and physical gates separately prove the published image;
they do not change the builder boundary.

## Frozen inputs and bounded delta

The builder requires these exact inputs:

- accepted 10,716,877,312-byte p2 v0.6 image SHA-256
  `4ac3a525264fcab7efda804c147f8e77604cbee82847d504de7e359258ca4bee`;
- its `BUILD-INFO` SHA-256
  `a7219d27d78be4b6b6f34b5dae72cf6e5d259c5aacf5a35a878b6cce0572c463`;
- accepted renderer payload archive v0.6 SHA-256
  `4c03d9d621ac362ce1fdc80628510d1f36e57e7d368eaa600b2f18af44bb31fa`;
- pinned arm64 builder image ID
  `sha256:bd09bf6db6f1fb8f882621e98d70f01f976fd8dfba1bc897766afebd64cf51b9`;
- fixed p2 geometry from `hl-r46h-v22-g92-v1`.

The overlay replaces exactly three payload-owned files: `r46h-game-ui`, the
frontend condition and `GAMING-PRODUCT.md`. Every other payload file must be
byte-identical to the v0.6 base image or composition fails. It adds the v0.6
receipt and the same root-only mode-0700 rollback state used by the accepted
live installer while retaining the exact v0.5 receipt. The rollback manifest
SHA-256 is
`cab1619dd8bfbcc022a5b33daea49020b24c197cfda793831c6afaed90f1bdbf`.

Only rootfs identity helpers and the consolidated receipt advance to v0.7.
The ext4 length and zero tail remain fixed; its new UUID is
`d3130007-46a4-4d56-9001-000000000007` and label is `R46H_GAMING_V07`.

## Build and validate

Docker Desktop must be running. Large private clones and extracted payloads
stay under `mainline/out/.cache/` and are removed on exit.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v07.py validate-inputs
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v07.py build
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs-v07.py validate
```

`build` requires the complete source scope to be committed and clean. It
composes two independent APFS clones and requires byte-identical results before
atomic no-clobber publication, then performs a third read-only container pass.
Validation covers the exact predecessor, payload manifest, three-file delta,
unchanged payload files, rollback contents and modes, both receipts, ext4
cleanliness/geometry, systemd syntax, ALSA rule precedence and absence of
personal SSH authorization or target firstboot state.

## Accepted host artifact

Clean source commit `b1acacae77a95f6e3799fd1593fee1567cc5abc6` produced two
byte-identical compositions and passed both the build-time and later independent
read-only validation. The published 10,716,877,312-byte image is
`mainline/out/r46h-debian13-p2-gaming-v0.7/r46h-debian13-p2-gaming-v0.7.ext4`
with SHA-256
`17530b491eaf7edd60cb0b499cc0c920af7399673bf9296f30c5753bc1ca7180`.
Its `BUILD-INFO` SHA-256 is
`22490e9bafcc0920a382f38d35e193ea033454de4af0a3e1dcda1eb28a84e7a7`.

The retained receipt reports
`artifact_status=host-only-no-media-operation-performed`, an exact three-file
payload overlay, the v0.6 receipt and rollback manifest, and zero transfer of
target-local firstboot or SSH state. This closes only deterministic host
composition and retained-artifact integrity.

## Media pass and physical boundary

On 2026-08-30 live Card Agent preflight rediscovered the fixed-profile card as
that session's `/dev/disk12`; the path is not reusable authority. Audit session
`session-20260830T110057Z-74267-d1b9556d-5ead-4f66-b76b-c9efb6c0cd0e`
retained the exact 10,716,877,312-byte p2 rollback clone. Its copy hash, an
independent file hash and a second raw-card hash all matched
`ebf8b076b0d86b8179eece391bb8f5329d18622d89f04a00fe20f69d7461c8ed`.

Pinned plan SHA-256
`5591ee332cf59b88604ad29c2509faf8f9efef5fa8665429888bfdda0259a5c4`
opened only p2. Deploy session
`session-20260830T111016Z-74750-80739232-55ca-4e3a-b947-b528669c5608`
wrote the exact published image; its built-in full readback and a separate raw
hash both matched `17530b491eaf7edd60cb0b499cc0c920af7399673bf9296f30c5753bc1ca7180`.
p1 matched before/after at
`ac4f7a81cef83ab3582841b37d45b5677329f8ed0f6d686a699b6ff4d743f503`;
p3 stayed unmounted and outside the plan. The session ended with `sync`, agent
shutdown and confirmed eject. Retained `PREWRITE-AUDIT.json`,
`POSTWRITE-AUDIT.json`, immutable write status and receipt own the exact proof.

Serial-first capture
`mainline/out/r46h-serial-logs/p2-v07-cold-product-20260830T125652Z.bin`
is 63,338 bytes with SHA-256
`d2a8078bddc522ef0ebb593c5c10202223da04b140f936471cd37120d6064ce4`.
The listener switched from 1,500,000 to 115,200 at OP-TEE without reset or
autoboot interruption. v0.17 loaded exact v0.15, p2 mounted with exact v0.7
UUID, MMC reached SDR104/150 MHz, p3 mounted read-only at `/roms`, Panfrost and
automatic GLES2 RGUI started, and service restarts, ext4 errors and failed units
were zero before and after the product sample. The operator ran
`/roms/nes/1944.zip` for about one minute and accepted picture, controls,
speaker audio and Select+X return. Shutdown unmounted `/roms`, remounted root
read-only, unmounted every filesystem and printed `Powering off.`

The paired physical receipt is
`p2-v07-cold-product-20260830T125652Z-receipt.json`, SHA-256
`bc107439cb9a81a88463d19e2ddd49bdca0137e65c078e206e7079dbfdc58bcb`.
Headphones and volume keys were not repeated because their bytes were unchanged
and prior physical gates remain accepted. Broad ROM compatibility, the skipped
p3 checksum/readback, minor intermittent stutter and the known `1943.zip` jam
remain open.

For an intentional media repeat, rediscover and independently hash the live
target, then generate a new session-scoped candidate. p1 and p3 must stay
outside that plan; current imported p3 is not the historical recovery p3:

```sh
python3 -B mainline/scripts/generate-debian13-write-plan.py \
  --device /dev/disk<diskN> \
  --artifact-id debian13-p2-gaming-v0.7 \
  --profile-id hl-r46h-v22-g92-62534975488-v1 \
  --target-sha256-before <target-p2-sha256>
```

Its status remains `candidate-requires-card-agent-live-preflight`; generation
alone neither authorizes a stale device path nor proves another write.

Do not repeat this accepted media/physical batch without a relevant change.
