# Consolidated gaming p2 first use and future acceptance

Status: **HOST REVIEW COMPLETE / BOARD AND MEDIA UNCHANGED**.

This document fixes the security and evidence boundary for a future physical
trial of `debian13-p2-gaming-v0.2`. It is not a device-bound deployment
procedure, a media write plan or permission to write a TF card.

## Decision

Keep the accepted v0.2 image generic and unchanged. Do not bake an operator SSH
key, Wi-Fi profile, password replacement or reused transaction receipt into the
canonical artifact.

The first physical boot must remain serial-first because all three of these
facts are unavailable beforehand:

1. first boot generates the device's unique SSH host keys;
2. the generic image has no Wi-Fi credential or trusted network path;
3. host and media evidence cannot prove the selected kernel, root identity,
   ext4 health or frontend behavior on the R46H.

Preinstalling only a public key would therefore not establish a safe SSH path.
Enabling SSH password login, committing a personal key, placing a Wi-Fi secret
on BOOT/EASYROMS or copying an existing device's SSH host keys are rejected.

## First-use credential contract

The generic image retains the existing `ark` password only for the physical
serial console and `sudo`; SSH password and root login remain disabled. After
the serial identity and health gate passes, a future first-use transaction may:

- change the initial `ark` password through a local, non-logged prompt;
- create one NetworkManager connection without printing or retaining its
  secret in a host or serial receipt;
- install one operator-selected public key as
  `/home/ark/.ssh/authorized_keys`, owned by `ark:ark` with directory mode
  `0700` and file mode `0600`;
- retain only the public-key SHA-256 and fingerprint in its root-owned receipt.

The key input must remain outside Git and be an exact root-owned regular file
bound by an operator-supplied SHA-256. Until a separately reviewed format
change exists, reuse the accepted ROM workflow's single, option-free RSA-3072
key validation. Never transfer, copy or log the private key.

This must be a standalone first-use transaction. Do not replay the old ROM
workflow installer: v0.2 already contains the accepted gaming and History
configuration, while its old target-side receipt and rollback state are
intentionally absent. The public-key carrier and NetworkManager input method
must be selected only after the exact deployment profile is authorized; no
Wi-Fi secret may be staged on FAT or exFAT media.

## Future physical acceptance contract

### 1. Authorization and media proof

- Obtain explicit authorization for one rediscovered, disposable TF-card
  identity and one fixed geometry/profile.
- Revalidate the clean-source v0.2 artifact, its exact image SHA-256
  `760b5c31ce74e25501aa1c3dfc37e2b52d398a5423cd7239ae906d668f67d753`
  and all retained manifests before producing a separate device-bound plan.
- Bind p1 to the accepted active v0.10 BOOT files plus the exact v0.8 fallback;
  do not infer that an older v0.8-only new-card procedure is sufficient.
- Require complete write/readback evidence for every changed media range,
  offline rootfs checking and a clean post-reinsert read-only audit. Host
  artifact proof remains distinct from this media proof.

### 2. Serial-first boot

- Open CH340 at 1500000 before cold power-on and switch to 115200 only after
  the visible `I/TC: OP-TEE version` marker. Do not use `saveenv`.
- Verify exact v0.10 boot, root PARTUUID `c9f931c9-02`, filesystem UUID
  `d3130002-46a4-4d56-9001-000000000002`, the v0.2 firstboot marker and
  consolidated receipt, both module trees, zero ext4 errors and no failed
  units.
- Confirm that first boot generated fresh SSH host keys and record only their
  public fingerprints over the independent serial channel.
- Bound the product check to automatic RGUI, the installed deterministic NES
  ROM, Nestopia loading, visible D-pad/A behavior and a clean health delta.

### 3. Credential handoff and SSH proof

- Run the standalone local first-use transaction only after the serial gate.
- Reboot normally and prove that firstboot did not rerun, Wi-Fi associated, and
  public-key-only SSH as unprivileged `ark` succeeds with strict host-key
  checking against the serial-observed fingerprint.
- Recheck the v0.10/rootfs identity, ext4 error counter and failed units over
  SSH, then `sync`, power off normally and confirm shutdown over serial.

Once this handoff passes, ordinary payload and ROM updates may use authenticated
Wi-Fi/p2 transactions. Serial remains required for cold-boot, rollback and
hardware evidence, but it no longer needs to stay attached for routine
post-boot work.

## Failure boundary

Any identity, hash, readback, firstboot, host-key, network, SSH or health
mismatch stops acceptance. Do not retry a destructive write automatically,
weaken SSH policy, reuse another device's receipt or promote a partial phase to
physical PASS. Preserve the exact failure evidence and keep the currently
accepted card as the rollback path.
