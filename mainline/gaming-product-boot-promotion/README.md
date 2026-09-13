# R46H v0.15 persistent BOOT promotion

This is the narrow target-side transaction that promotes the already accepted
gaming-product kernel while retaining complete, exact v0.10 and v0.8
kernel-plus-module fallbacks. Building or validating its payload is host-only
evidence. It does not authorize a p1 write, reboot, poweroff or U-Boot
environment change.

## Contract

The tool is bound to the current 62,534,975,488-byte fast card, root PARTUUID
`c9f931c9-02`, g92 prefix, the complete pre-promotion p1 digest, exact v0.8 and
v0.10 BOOT files, both R46H U-Boot DTBs, exact product Image/DTB staging and
all three accepted p2 hotfix receipts. The product v0.3 p2 contains v0.8 and
v0.15 module trees but omitted the previously accepted v0.10 module tree. The
payload therefore pins the exact historical 1,276-module bundle and restores
that missing fallback before it touches p1. Device names are rediscovered from
the PARTUUID aliases every run. Before any write, the target also rehashes all
1,290 files in each existing v0.8 and v0.15 module tree instead of promoting
their offline build proof into live-card proof.

The original Card Agent post-write audit correctly recorded raw p1 SHA-256
`e962cdb3f566476add93e51dc912e2656ff3ad38741fe75d97ce8c131ca12c6b`.
Before promotion, a read-only target audit found the current raw p1 SHA-256 is
`f50597d459a51bab509aae959267f77ade068d566751acb6cff888b012d3b4ed`,
while the 16 MiB prefix remains exact, the v0.10 module tree and promotion
state are absent, and `fsck.fat -n -v` is clean. The 168-file non-Spotlight
manifest at
`mainline/out/r46h-v15-boot-promotion/evidence/p1-nonspotlight-current-20260823.sha256`
has SHA-256
`b8e38b3c44666ffcd296b0be53b23caa3a976c09c04b23145015f368ca95c651`
and exactly matches the retained original p1 image after the accepted v0.10
file transformation. The audit found no non-Spotlight file-content divergence;
mutable Spotlight content and raw FAT metadata remain outside that manifest.
The transaction therefore still accepts only the complete current `f505...`
digest; it does not weaken the guard by accepting both raw images.

Two earlier archives are revoked without any p1 write or promotion state:
SHA-256 `123723ea28df1d2cd36656e9957a9a71cb42db908256a2e158bb7b637895ee9f`
failed read-only preflight because of a `set -u` local-variable expansion, and
SHA-256 `889524c7b31aa2cfc814f579995dc6dcf143e138fa2169d1637d9f927cf0d802`
retained the historical `e962...` raw baseline. Neither may authorize a
prepare or activation command.

Promotion has two explicit phases:

1. **prepare** first extracts and rehashes the v0.10 module bundle in a
   root-only p2 stage, atomically publishes its module directory and receipt,
   then adds the compressed v0.15 Image, DTB and versioned boot script to p1;
   the BOOT script is published last and active `boot.ini` stays exact v0.10;
2. **activate** replaces only active `boot.ini` after all three versioned files
   and both older kernel-plus-module fallback sets rehash exactly.

The p2 module tree is staged, rehashed, synced and atomically renamed on ext4;
each p1 file is staged, rehashed, synced, renamed and block-flushed. Exact p2
and p1 journals distinguish recoverable preparation and activation states.
Normal errors and terminal disconnects cannot leave an unreviewed switch:
signals are ignored after a write begins, an interrupted p2 extraction is
recoverable from the retained payload, and an activation error attempts an
immediate v0.10 rollback before unmounting.

Sudden power loss during the final FAT active-file rename cannot execute a
software rollback. The activation journal deliberately remains until the new
active file is rehashed and flushed, so a following serial boot can identify
whether v0.10 or v0.15 is active. If ordinary boot is unavailable, source the
retained exact `boot.ini.v0.10-adc-full-range` from U-Boot without `saveenv`,
then run the explicit rollback. Do not guess, delete journals manually or
power-cycle after a hard warning.

The only p2 kernel/runtime addition is the missing exact v0.10 module tree plus
its root-only receipt and retained recovery payload. The tool never replaces
or removes existing v0.8/v0.15 modules, never removes v0.8, v0.10 or v0.15
versioned BOOT files, never mounts p3 and never calls `saveenv`. It also never
reboots or powers off the board.

## Host build

Commit the complete source scope first. The builder refuses dirty or untracked
scoped inputs, rehashes the accepted v0.15 kernel bundle, independently
reproduces the exact `gzip -n -9` Image, verifies every member and the canonical
tree digest of the v0.10 fallback bundle, and publishes one deterministic
control archive below `mainline/out/r46h-v15-boot-promotion/`:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-r46h-v15-boot-promotion.py build
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-r46h-v15-boot-promotion.py validate
```

Build work is removed from `mainline/out/.cache/` after completion. The payload
contains the checked scripts, versioned boot script, exact deterministic
compressed Image and DTB, and the exact v0.10 fallback module bundle. The
target independently rehashes the root-only raw product Image/DTB already on
p2 before accepting those packaged BOOT files. The current p2 has more than
8 GiB free; target preflight still requires the bundle's extraction projection
plus a 64 MiB margin and 256 free inodes.

Clean source commit `92f3ee1f350dbd9646a19e4d2ca3acff61582179`
produced the 47,707,246-byte archive used by the physical transaction, with SHA-256
`d28efde390273d2674c91e7009fe99e9e365582962b972ec9859e5c1f47fbee2`.
All 12 original transaction tests, source capture, member checks and deterministic
generation validation passed. On 2026-08-23 the target independently rehashed
that exact archive, passed its payload self-check and returned
`result=pass mode=preflight state=base status=absent v0.10_modules=absent`
with exact p1/prefix digests and `write_started=false`. This is physical
preflight evidence and did not replace the operator's explicit p1 authorization.

The physical recovery exposed the missing production flush-device binding;
fix commit `faf84e8c0c5f45e4ea2bc9232ba3918511097da4` added the real flush
branch test. Final postflight hardening commit
`6febc0b82ef2976f74d1b47e910bf6a49e638368` added the exact recovered-MMC
classifier and guarded status completion. All 16 tests passed. From clean
inputs it produced a separately validated 47,708,155-byte future archive with
SHA-256
`023c4cff3f7b237cfb7abd1e6ce2634389f924380aec44b2e116ed6b68c293f0`.
That later host artifact was not substituted for the checksum-bound payload
retained by the completed physical transaction.

## Accepted target transaction

The attended transaction is complete; do not rerun prepare, activation or
postflight. After the authorized and recoverable cleanup described below,
prepare recovery passed at raw p1 SHA-256
`daccd70b7c9f021eb8ae114e5b272ae404806e71892049675e5c4ed6119c0642`.
Activation retained exact v0.10 and v0.8 kernel-plus-module fallbacks, changed
only active `boot.ini`, and produced final raw p1 SHA-256
`e6ca320b5413a6fe224a8a9a89c3d4199d395237d3fc413ef93da50131e481c9`.
The raw 16 MiB prefix stayed
`3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3`;
the U-Boot environment stayed unchanged and `saveenv_used=false`.

The next serial-first ordinary cold boot used no autoboot interrupt, loaded
exact v0.15 and reached multi-user. The guarded completion rehashed the final
p1/prefix, active BOOT, retained payload, all three module trees, product
hotfixes and legacy backups. It then published exact 13-line `state=complete`
status SHA-256
`1dec0439d0a781db1a07008db793796652df4a0f5b3be0231b7711d9e70f34aa`.
Independent final checks found zero ext4 errors, zero failed units, no
RetroArch/session state and no p1/p3 mount. Temporary authentication and
staging were removed before controlled poweroff. Root remounted read-only, all
filesystems unmounted and `systemd-shutdown: Powering off` appeared; twelve
later seconds contained no serial bytes. The prepare-through-activation capture
is
`mainline/out/r46h-serial-logs/gaming-product-v015-persistent-promotion-20260823T123024Z.bin`,
141,737 bytes, SHA-256
`59233631562cd315270371ffba536f1fe2ea15bb080806a48663fa9489cd6457`.
The ordinary-boot-through-completion capture is
`mainline/out/r46h-serial-logs/gaming-product-v015-persistent-coldboot-20260823T143219Z.bin`,
72,630 bytes, SHA-256
`e8e77f40c1082e36f1a7684cc5f13dbaaa287b41ed5cbdefe3fe0a2c6ff573ad`.

The postflight storage gate accepts either a log with no storage-fault marker
or the one already tracked intermittent cold-MMC recovery sequence: one exact
400 kHz `error -84`, then ordered 300 kHz retry, 150 MHz SDR104 enumeration,
`mmcblk0` p1/p2/p3 discovery and read-write p2 mount. That exception is valid
only when it is the sole fault-regex line in the complete current `dmesg`;
repetition, reordering, a missing recovery marker or any later MMC, block-I/O
or ext4 error still fails closed. Accepting the recovered boot does not close
the intermittent cold-MMC ledger item.

The completed 2026-08-23 transaction retains an older checksum-bound payload
whose original postflight rejected even that exact recovered sequence. It was
not edited or replaced. For that transaction only, the committed
`complete-recovered-mmc-postflight.sh` and `storage-health.sh` were staged
together in a root-owned mode-0700 directory and independently rehashed before
the exact completion command was run:

```sh
sudo /run/r46h-v15-recovered-postflight-v0.1/complete-recovered-mmc-postflight.sh \
  --confirm complete-v0.15-recovered-mmc-open
```

That completion path required the exact activated p1/prefix/status hashes,
ordinary v0.15 runtime, all three module trees, retained payload, product
hotfixes, root-only legacy-kernel backups and the exact recovered MMC sequence.
It mounted p1 read-only and changed only the p2 status receipt's third line from
`state=activated` to `state=complete`. It never wrote p1, controlled power or
called `saveenv`. Do not rerun it from the completed state.

## Recovery history and retained rollback

The 2026-08-23 physical transaction exposed that source commit `92f3ee1`
did not bind the wrapper's already verified `BOOT_DEVICE` to the transaction
helper's production flush variable. It stopped fail-closed at exact
`state=prepare-partial status=prepare-intent v0.10_modules=complete` before
activation. Its checksum-bound retained payload was not edited or replaced;
the freshly reverified PARTUUID `c9f931c9-01` alias was supplied explicitly to
every remaining write command. The source fix binds this variable automatically
for later payloads.

Fix commit `faf84e8c0c5f45e4ea2bc9232ba3918511097da4` passed all 13
tests, including a production-mode `sync` and `blockdev --flushbufs` binding
check. Physical recovery reached the next independent fail-closed gate: only
693,760 bytes were free while the three missing target files plus the fixed
512 KiB margin required 15,500,491 bytes. The partial p1 hash and active v0.10
remained unchanged.

A read-only inventory found two legacy setup-selection copies outside every
active or accepted fallback path:

- `consoles/kernel/original/Image`, 13,096,968 bytes, SHA-256
  `ae08557630a4bae7e8df5fa39c0651b1ef4380233989aca4450827c3018ea65f`;
- `consoles/kernel/arkos4clone_fix/Image`, 13,096,968 bytes, SHA-256
  `eda795942083d198d7223dcf3f65e19c05c4c7bfc754935e4f84d3a0cc15bbfd`.

The root `Image` remained present and exactly matched the latter copy; active
v0.10 named its exact versioned compressed Image. With separate authorization,
both inventory files were first preserved under root-only p2 state. Backup
RECEIPT SHA-256 is
`620d3cee882fc8c1d107a8dd42ef11ead09e317de3228b34c05259b4bb4a8012`
and reclaim RESULT SHA-256 is
`02a00d3521e1b4b7fe4a0ab995f8265541242d0b7f8cd84aed6a240637c7bbe4`.
Only then were the two p1 copies removed. Free space rose to 26,888,704 bytes;
raw p1 became
`2f505fc5664dc6d8cbcfc4119bda340cad1c7477a925046df36f25a16c7f887d`,
the prefix stayed exact and `fsck.fat -n -v` returned 0. Prepare recovery and
activation subsequently passed as recorded above. Do not rerun either command
from `state=complete`.

The exact v0.10 rollback remains available only for a real persistent-v0.15
regression. Because the retained physical payload predates the binding fix,
rediscover and reverify the device and fixed geometry first, then provide the
verified alias explicitly:

```sh
sudo env R46H_BOOT_DEVICE=/dev/disk/by-partuuid/c9f931c9-01 \
  /var/lib/r46h-boot-promotion/v0.15-gaming-product/payload/install.sh \
  --rollback --confirm rollback-active-to-v0.10
```

Rollback must still pass exact runtime, media, module, payload and storage
health gates. Its target is v0.10 because that accepted kernel and newly
restored exact module tree are the immediate fallback; v0.8 remains the second
independent fallback. Never use rollback as a routine retest and never call
`saveenv`.
