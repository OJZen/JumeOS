# R46H Debian 13 gaming product p2 v0.5

> Frozen accepted v0.5 composer. It pins the historical gaming payload v0.4
> and does not contain the 2026-08-29 GLES2, p3-ordering or hardware-volume
> deltas. Do not rewrite its hashes; a successor can consume the published
> gaming payload v0.5 generation owned by `GAMING-PRODUCT.md`. Current state is in
> [`PROJECT-CONTEXT.md`](../../docs/PROJECT-CONTEXT.md).

Historical accepted composition: **V0.5 MEDIA + FUNCTIONAL PASS WITH V0.17 PERSISTENT COLD PASS / FIRST VERSION ACCEPTED / INTEGRATED FULL-CARD ARTIFACT OPEN**

This builder produces a **HOST-ONLY** reproducible bottom-image candidate.
Running it does not authorize a TF-card write and does not prove target boot.
The current media and physical boundaries remain in the canonical R46H ledger
and `mainline/bringup-tests/GAMING-PRODUCT.md`.

V0.5 supersedes raw v0.4 as a distributable candidate. It integrates the exact
input-config correction from the accepted live v0.4 p2 while preserving the
three earlier product hotfixes and exact v0.10 kernel-module fallback. It does
not borrow physical proof from the live p2: v0.4 media and live behavior pass,
while the v0.5 build itself remains host-only evidence. Its later separately
authorized media write and initial attended target result are recorded below.
That original v0.15-DTB cold attempt failed and required one warm Reset; the
later exact v0.17 persistent BOOT state cold-booted this unchanged v0.5 p2 and
closed the fixed-profile first-version gate.

## Frozen composition

The image composes these exact offline inputs:

- Debian p2 v0.1 arm64 base image
  `sha256:bd09bf6db6f1fb8f882621e98d70f01f976fd8dfba1bc897766afebd64cf51b9`;
- accepted v0.8 fallback bundle
  `8c7282a07bdec52b753a8af27d15c6bbc8b71b34d017c3d78a2273fba6cfd09e`;
- accepted v0.10 fallback bundle
  `c4350520f7ad33ecf7b50f67c42985e2ce26c1c38d050ad50601c3538cebc780`;
- v0.15 gaming-product kernel bundle
  `748d81cc0e8b9bf353430db1f4ee358bf09dee1d32db85a855961368b58d3fad`;
- cumulative gaming v0.4 archive built from source commit `9cb978888b54`,
  `c192e6301b112e26436836e59fc8b9cf82af85851352d8db1a41bebb942e2c2e`.

The payload ID remains `r46h-gaming-mvp-v0.4`; its immutable generation is
identified by the source commit and archive hash above. The new p2 image gets a
v0.5 identity because its bytes differ from raw v0.4.

The four accepted live corrections are pinned independently inside that
archive:

- `r46h-storage-audit`:
  `08ed33dace8a94a6b129d72896c8e6a657b32d15c74d9ecf48df99a9f49ae95c`;
- `r46h-smoke-libretro.so`:
  `a6618fec16ab91fcfbc76497416c4542d1973862affb82f633ee70d600739085`;
- `r46h-game-ui`:
  `867664284d932cd23757b40d7108ed878d3ab8d16f5655956543444619e75ff3`.
- `retroarch.cfg`:
  `99a45beb148e58e40983773b4f5e26d9fb5d7e1bbbf6a7e714a5c352e43c0dba`.

The result contains exact v0.8, v0.10 and v0.15 module trees, the v0.15
Image/DTB and root-only p2 one-shot U-Boot commands, the permanent combined-input
service, RGUI with History and **Select+X**, the deterministic NES smoke ROM,
and the read-only storage audit. The U-Boot commands never write media, call
`saveenv` or change p1. An A2-labelled card remains usable as an ordinary
SD/UHS-I card; this image does not claim A2 command-queue acceleration or run a
storage write benchmark.

The clean image does not bake any operator SSH public key, Wi-Fi credential,
private material, host key or historical transaction rollback state, and it
does not install the old diagnostic input bridge. Ordinary updates to the
accepted live product remain authenticated Wi-Fi/p2 transactions.

## Build and validate

Inputs must exist at their pinned paths, Docker Desktop's arm64 base image must
match exactly, and the builder source scope must be committed and clean.
Disposable extraction, rootfs export and Docker-volume work stay below the
external workspace and are removed on exit:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs.py validate-inputs
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs.py build
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-debian13-gaming-rootfs.py validate
```

## Accepted host build

Clean source commit `44c1b0293061d03805c204c3b383ebb8ca8cc017`
produced
`mainline/out/r46h-debian13-p2-gaming-v0.5/r46h-debian13-p2-gaming-v0.5.ext4`.
The file is exactly `10,716,877,312` bytes with SHA-256
`ee7d402c06a750081b4c588c5162cca44d0e07fa4b544d5a59bef7629722aeca`,
filesystem UUID `d3130005-46a4-4d56-9001-000000000005` and label
`R46H_GAMING_V05`. Independent post-publish validation reopened all 29 retained
outputs, reproduced the image digest and passed the clean offline `e2fsck`.
The output checksum manifest has SHA-256
`e844e13b1ea458adda6cad447f6f73b8a017ca983998870df404cc4464cde0e7`;
the complete rootfs file manifest has SHA-256
`1ad54bc7afa6f4e16b21a726663f630bd02769c4a5ab50d0b7c40ef36f718d83`.

Retained evidence covers committed source closure, all four frozen input
hashes, three exact module trees, the four accepted live identities, product
Image/DTB/U-Boot staging, 422 offline package rows, systemd,
RetroArch/Nestopia, complete rootfs manifests, ext4 geometry and offline
`e2fsck`. This is an accepted **HOST-ONLY PASS**. It is not media readback or
physical R46H evidence, and the accepted live v0.4 card was not touched by the
build.

The guarded plan generator accepts v0.5 only for the fixed
`hl-r46h-v22-g92-62534975488-v1` profile and requires an independently audited
complete current-p2 SHA-256. A generated plan is still only a candidate: it
does not authorize a write. The historical v0.4 plan was bound to a different
source and target state and must not be reused for v0.5. Follow the current
registered-plan and authorization boundary in
[`../bringup-tests/GAMING-PRODUCT.md`](../bringup-tests/GAMING-PRODUCT.md);
never substitute the historical v0.3 target hash or a same-session
"read whatever is present, then authorize it" value.

## Accepted media write

On 2026-08-24 a new audit rediscovered the card as `/dev/disk6` with exact
profile `hl-r46h-v22-g92-62534975488-v1`, fixed 62,534,975,488-byte geometry
and prefix SHA-256
`3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3`.
The complete live-v0.4 p2 independently hashed as
`c7dee8dac10f41593beb9327b8145d8e2b329ab8b0ca619d8b9b00c09a226b3a`;
a retained 10,716,877,312-byte rollback clone reproduced that digest.

Clean plan-generator commit `5f49de24d546cfd2af4e93a8ab1571c292e08fc6`
then produced mode-0600 p2-only plan SHA-256
`17bd631ecc04c598b1216d478f580c108af4636701f58d43d3f9e54be8355535`.
After explicit fixed-device and complete-p2-state-loss authorization, Card
Agent revalidated the profile and target, staged and rehashed source
`ee7d402c...`, wrote only p2, synchronized the medium and completed a full
readback. Both its readback and a separate reopened full-p2 hash equal
`ee7d402c06a750081b4c588c5162cca44d0e07fa4b544d5a59bef7629722aeca`.
Raw p1 stayed exact at
`042ad4ad08f39f60f1d57e393ab32ae148e2a946ab9996822ae161934f7a0825`;
the prefix stayed exact, p3 was outside the plan and remained unmounted.
`WRITE_COMPLETE`, `safe_to_boot=yes`, agent shutdown and macOS eject passed.

At media completion this was **MEDIA PASS / PHYSICAL OPEN**. The write must not
repeat. The initial target result and later v0.17 companion-BOOT acceptance
below supersede that open physical boundary without changing the media proof.

## Initial attended target result

The 2026-08-24 serial-first cold attempt loaded exact persistent v0.15 but
failed before mounting root: `mmc0` progressed from `-84` at 400 kHz to `-110`
at 300 kHz and stuck-busy `-110` at 200/100 kHz. One short warm Reset then
reached SDR104/150 MHz directly and mounted exact UUID
`d3130005-46a4-4d56-9001-000000000005` with label `R46H_GAMING_V05`.

The recovered session rehashed the corrected config and all accepted runtime
files, plus all 1,290 files in each exact v0.8, v0.10 and v0.15 module tree.
Five services, one combined controller, the read-only A2-compatible storage
audit, zero failed units and zero ext4 errors passed. The operator confirmed
independent D-pad/left-stick markers and a short Nestopia D-pad/A/Select+X
regression. Cleanup, `sync`, read-only root remount, complete unmount and
controlled poweroff passed. Evidence is the 620,192-byte serial capture
`mainline/out/r46h-serial-logs/gaming-product-v05-firstboot-20260824T063956Z.bin`,
SHA-256
`015e571c0f0f4a5ebe967a9543d5b68d58cf1e39ea4c6608c5371ec79d7b522f`.

At that point the deployed composition was **MEDIA + WARM FUNCTIONAL PASS /
ORIGINAL V0.15 COLD GATE FAIL**. Do not repeat the write or accepted functional
checks. The Reset was only a rescue and is not cold-boot acceptance.

## Later v0.17 persistent cold acceptance

The v0.5 p2 bytes and physical evidence above did not change. The separately
reviewed v0.17 BOOT promotion retained the exact v0.15 Image/modules and added
only the accepted 800 ms system-card power-settle DTB while disabling the
secondary MMC host. Its host artifact, p1 transaction, recovery anchors and
exact hashes are canonical in
[`../gaming-product-v17-boot-promotion/README.md`](../gaming-product-v17-boot-promotion/README.md).

On 2026-08-25 one separate persistent serial-first cold boot loaded exact
v0.17/v0.15 without Reset or autoboot interruption. Linux instantiated only
`ff370000/mmc0`, measured 819.113 ms then 902.528 ms through 400 kHz to
SDR104/150 MHz, enumerated p1/p2/p3, mounted this exact v0.5 root and reached
multi-user without an MMC, block-I/O or ext4 fault marker. Strict retained
postflight passed live DT bytes `00 00 03 20`, fallback/module hashes, clean
boot state, product storage health, zero ext4 errors and no failed units. It
published `state=complete` status SHA-256
`3b4265849e446ee8566e47fbfb7d7ee4145bdd0d732caa7b5913684b4e4d3034`
with p1 SHA-256
`ad71f67bfb436cc480bb9a83db770f88cdcadc54612b322d9106befa0982929b`
and `saveenv_used=false`; final controlled poweroff passed. The 58,567-byte
capture has SHA-256
`c84dccd4bff90421c8a4741ebf5598b9ea7f86e619cb22212fefa6615ee97f70`.

The exact v0.5 p2 plus exact v0.17 BOOT state therefore qualifies the fixed
card/profile as the first functional version. This does not transfer physical
proof into the host-only p2 build, establish statistical cold reliability or
transfer proof to a newly written card. Clean source `2e0d33a53f11` separately
produced the integrated four-range host source set
`build-2e0d33a53f11-e1e8d9edb2f8`; see
[`../first-version-release/README.md`](../first-version-release/README.md).
The second card slot is unavailable in this profile; do not repeat accepted
functional or cold gates merely to raise the sample count.
