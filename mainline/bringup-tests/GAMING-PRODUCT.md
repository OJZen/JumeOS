# R46H gaming product candidate

Status: **CURRENT-CARD V0.6 PRODUCT + RENDERER PAYLOAD PHYSICAL PASS /
REPRODUCIBLE FULL-CARD V0.5 RELEASE BASELINE PASS /
SUCCESSOR ARTIFACT + STATISTICAL RELIABILITY OPEN**

## Accepted live integration and current media state (2026-08-30)

The exact current card cold-booted v0.17 with the v0.15 kernel and exact p2
v0.6. `RequiresMountsFor=/roms` mounted imported p3 read-only before automatic
RGUI. Four analog axes, D-pad/buttons, hardware volume, speaker/headphones,
imported `1944.zip`, Select+X return, zero-restart services, clean SDR104 storage
and controlled poweroff passed. Exact physical evidence belongs to the
[v0.6 rootfs runbook](../rootfs-debian13-gaming-v06/README.md). `1943.zip`
instead reaches Nestopia's `Cpu: Jammed` path and is not a storage failure.

The initially accepted live v0.6 runtime selected `SDL_RENDER_DRIVER=opengles2`
for every mode and ran `r46h-volume-keys.service`. A bounded GLES2 game run had
far lower renderer load and no ALSA XRUN than the software path; the operator
reported much smoother audio with occasional minor stutter. The volume
listener uses the stable volume-key symlink, equal 16-step mixer changes and the
accepted 201
ceiling. Audible change and a clean warm autostart with zero restarts passed;
no UI overlay is implemented.

Clean payload source `5a3a3000bfd1` published the accepted v0.5 files. p2 source
`5b81d58039c0` consumed them, applied the upstream ALSA-rule correction and
produced deterministic v0.6 bytes. A p2-only write and two full readbacks then
matched that artifact while p1/p3 stayed outside the plan.

First-version release v0.2 generation
`build-ec2723116ec0-c67c533cfd32` independently bound that p2 to the unchanged
v0.17/v0.15 p1 and historical recovery components. Its asset manifest SHA-256
is `c67c533cfd32481fd42853afda882a067a9944467c4d1cb9edb643a023a69616`.
The release host build opened no block or physical device and did not
materialize a whole-card image. Its historical recovery p3 differs from the
current card, so v0.2 as a full release remains host-only even though its exact
p2 component now has media and product physical proof.

One direct diagnostic path then remained open: `/usr/local/sbin/r46h-game-ui smoke`
black-screened and was interrupted with status 130, while mixer restoration,
process cleanup and automatic frontend recovery passed. Its log recorded zero
content run time, so the observation cannot distinguish a persistent render
failure from an interrupted first frame. Earlier accepted custom-core runs used
the software renderer before the global GLES2 change and ran for 31--141
seconds. This makes renderer scope the smallest evidence-backed hypothesis.

Successor payload source v0.6 therefore uses the accepted software fallback
only for `smoke`; `menu` and `nes-smoke` retain GLES2. The runner emits its
selected renderer, passes it as a fixed argument and rejects any other value.
The strict v0.5-to-v0.6 installer verifies the exact previous receipt and three
old file hashes, confirms unchanged packages/fstab, requires an inactive
frontend and retains a root-only rollback state. It uses atomic renames to
replace only the runner, frontend condition and installed product document
before publishing the new receipt; it does not reinstall packages or rewrite
any other product file. These source changes pass focused host tests. The copy
embedded in the artifact records only that source-level boundary; post-build
acceptance is recorded below, and an accepted archive still does not prove
target behavior. Do not change normal game rendering or repeat the accepted
product batch.

Clean source commit `73cd84e30548d810f32c58dc21a7b2a8ef2a66cc`
published generation `build-73cd84e30548-4c03d9d621ac`. Its independently
validated 263,537,654-byte `r46h-gaming-mvp-v0.6.tar.gz` has SHA-256
`4c03d9d621ac362ce1fdc80628510d1f36e57e7d368eaa600b2f18af44bb31fa`.
Generation metadata hashes are:

- `BUILD-RECEIPT.json`:
  `d5ee90bd9b25eeb6dd7253e1adbe1d1f3f6f54fa3a91b4fbba50dc5e820810d4`;
- `SOURCE-MANIFEST.json`:
  `6987d5a51c9f513a81d37929a26279e6c099d325e7e7789f2a1969ae5bbfcd0a`;
- `SHA256SUMS`:
  `d9bae68f35741797a15994559b294b4b9bfcdf961ba6f3cee37c1a916e014b3f`;
- `BUILD-COMPLETE`:
  `e6dca62fe358bc9e3b98b11ee5d789a00dda8e21c7d2477aae8ecc487f84af65`.

An archive-manifest comparison against accepted payload v0.5 found differences
only in payload metadata, the runner, frontend condition, product document and
installer. Packages, cores, ROM, configuration, services, input, volume and
storage tools stayed byte-identical. This closed the host artifact gate before
the target transaction below.

## Accepted renderer payload target result (2026-08-30)

The fixed target matched the exact v0.15 kernel, p2 PARTUUID/UUID, v0.5 receipt,
three old file hashes, fstab, package state and zero ext4 errors. Wi-Fi and the
accepted public SSH key were restored over serial as live device state; strict
host-key checking stayed enabled. The explicitly approved secret bootstrap was
never printed or committed, and both host and target temporary copies were
removed after connection.

The 263,537,654-byte archive rehashed on target as
`4c03d9d621ac362ce1fdc80628510d1f36e57e7d368eaa600b2f18af44bb31fa`.
A direct extraction could not fit the 190,685,184 bytes then available on
`/run`; its partial tree was removed before the installer ran. The complete
263,686,815-byte payload instead validated in a root-only p2 staging directory
and was read-only bind-mounted at the installer's required `/run` path. The
strict transaction and its idempotent rerun passed. New receipt SHA-256 is
`82721e16a9b9a7c7927d0ca4d228dd3d850e3a39dca245177ec1f016b3b8d314`;
the root-only rollback manifest passed, and all transfer/extraction staging was
removed.

Direct smoke announced `renderer=software`. The operator accepted its color
display, tone, D-pad/A behavior and independent left/right analog markers. The
run recorded 13 seconds of content before deliberate Ctrl-C, so its expected
terminal marker was status 130 rather than a zero exit; mixer restoration and
process cleanup both passed. Automatic RGUI then ran with an observed
`SDL_RENDER_DRIVER=opengles2`, zero restarts and a separate operator visual
pass.

p1 matched before and after as
`74dde6dd6c14324af0eb2d570b89096d6fb0414abc3293f648e40265b44a1db9`;
p3 stayed read-only. Failed units, ext4 errors, kernel storage-fault matches and
audio XRUN matches were zero, followed by `sync`. The board was deliberately
left running in RGUI. The mode-0600 serial capture is
`mainline/out/r46h-serial-logs/gaming-payload-v06-target-20260830T083200Z.bin`,
9,484 bytes, SHA-256
`133829cc11cd437140ef6b57c80623fcc572070041e72c8f663c8a268d52db11`.

This closes the live renderer hypothesis without promoting it into a new p2
artifact claim. The published p2 v0.6 and release v0.2 still embed payload v0.5;
the next host gate is a deterministic successor containing these accepted exact
bytes. Do not rewrite the current card merely to repeat this live overlay.

The first product candidate combines the shortest already accepted Debian
RetroArch path with the composite physical input result. It does not add
EmulationStation, broad ROM claims, a new audio route or a storage benchmark.

The required kernel is
`6.12.99-r46h-mainline-v0.15-gaming-product`. It applies only patches
`0001..0008` and enables built-in UINPUT. This preserves the physically
accepted v0.11 board behavior while excluding the host-only v0.12 charge
termination experiment and the spent v0.13 MMC logger.

At boot, `r46h-gaming-input.service` starts the exact bridge algorithm that
closed 16 identified game keys and four axes by composite physical evidence.
The service grabs only `gpio-keys` and `adc-joystick`; volume keys and the RK805
power key are separate devices. The frontend requires the bridge and waits for
exactly one `R46H Combined Gamepad` before starting RGUI. RetroArch selects the
combined Pad #1, keeps native analog binds, and uses **Select+X** as the menu
toggle so a running game can return to RGUI.
`r46h-gaming-frontend.service` carries the corresponding systemd dependency.

The runner retains the accepted HP mixer route (`mux=0`) and conservative
`201,201` game value (`-20.12 dB`). The smoke core's signed-16-bit peak is only
5,000, or 15.3% of full scale, below the 40% signal used with that same mixer
value in the completed physical route probe. The original product runner's
`20,20` raw value was about `-87.55 dB` and made its first normal-audio attempt
inaudible despite successful ALSA initialization. Correcting that scale error
does not exceed the already accepted playback boundary; no higher value or
unbounded retry is authorized.

The smoke core keeps the blinking upper marker for D-pad movement and inverts
the background while A is held. It also reads the native libretro analog axes:
the cyan lower-left marker follows the left stick and the magenta lower-right
marker follows the right stick. This makes the two analog paths independently
visible. The product configuration explicitly leaves all four D-pad axis binds
at `nul`; only buttons 10--13 drive the D-pad, so neither analog stick is also
translated into D-pad input.

`r46h-storage-audit` is read-only. It records the SD CID/CSD/SCR/SSR registers,
the active MMC timing/clock, queue scheduler and ext4 error count. The operator
reports that the medium is labelled A2, but this stack has no active SD command
queue path, so the tool always reports `a2_command_queue=not-available`. A2
media remains compatible as an ordinary SD/UHS-I card; the audit must not be
described as full A2 acceleration or used as a write-performance benchmark.

## Host artifact

Clean kernel/gaming source commit
`6e36b43ce1048a5924d3b64dde1c038d2ac87e4e` produced the v0.15 kernel bundle
with SHA-256
`748d81cc0e8b9bf353430db1f4ee358bf09dee1d32db85a855961368b58d3fad`
and the v0.4 gaming archive with SHA-256
`6f26b2188420216ed0cf7b6a6b079236bf76e77c6b803caad26c3405c66e0b0e`.
Clean p2 source commit `1e92783399ca58b5ffb608352efe085da74aa510`
then produced the exact 10,716,877,312-byte
`mainline/out/r46h-debian13-p2-gaming-v0.3/r46h-debian13-p2-gaming-v0.3.ext4`
with SHA-256
`09ec6bfc9a2f34a469e96adadc7e662e5b9474bdc3eb0a68011662939d97d52c`.

The 28-entry output checksum manifest, 422 package rows, committed source
closure, v0.8 fallback and v0.15 module trees, staged Image/DTB/one-shot
commands, both systemd services, RetroArch/Nestopia loads, six ext4 anchors and
offline `e2fsck` all passed.

## Accepted media deployment

After explicit operator authorization on 2026-08-23, Card Agent commit
`63106d770902acec12bf58ab91043278a49a56a9` used the device-bound plan from
commit `5527fb885704c0fab7f375835d7a1f9ffd5867c4` to replace only p2 on the
62,534,975,488-byte fast card. A retained full pre-write p2 clone independently
matched `2deb93bf074d985d5127600f72d16dbbe8272777a7b19986571d4f3ec8928aeb`.
The agent wrote 10,716,877,312 bytes, flushed them and read the complete p2 back
as `09ec6bfc9a2f34a469e96adadc7e662e5b9474bdc3eb0a68011662939d97d52c`.
Its immutable status is `WRITE_COMPLETE` with `safe_to_boot=yes`.

A separately reopened post-write read reproduced that p2 digest. The complete
p1 digest stayed
`e962cdb3f566476add93e51dc912e2656ff3ad38741fe75d97ce8c131ca12c6b`,
the raw 16 MiB prefix stayed
`3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3`,
all partitions were unmounted, the agent stopped and macOS ejected the card.
The detailed boundary is retained in
`mainline/out/r46h-card-agent-sessions/session-20260823T093132Z-57843-5e690885-8e12-4af3-bc70-49a63a7be679/POSTWRITE-AUDIT.json`.
Its SHA-256 is
`ddf39b2b81a112f510a5629ae4e959d723ac0cfda82f233d3628b8fe18c198c2`.

The later attended persistent-BOOT preflight made no p1 write. It revoked one
archive after a read-only `set -u` failure and a corrected archive after its
strict raw-p1 guard exposed that the historical post-write `e962...` digest
was no longer current. A second read-only audit found exact prefix SHA-256
`3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3`,
current raw p1 SHA-256
`f50597d459a51bab509aae959267f77ade068d566751acb6cff888b012d3b4ed`,
a clean FAT filesystem and absent promotion/module state. Its 168-file
non-Spotlight manifest exactly matches the retained original p1 plus the
accepted v0.10 transformation. The exact evidence and revoked archive hashes
are recorded in
[`../gaming-product-boot-promotion/README.md`](../gaming-product-boot-promotion/README.md);
the replacement package accepted only the current complete raw digest and
required separate explicit p1 authorization after a passing preflight.
Clean source commit `92f3ee1f350dbd9646a19e4d2ca3acff61582179`
then produced the 47,707,246-byte replacement archive with SHA-256
`d28efde390273d2674c91e7009fe99e9e365582962b972ec9859e5c1f47fbee2`;
all 12 original tests and deterministic generation validation passed. The target then
rehashed the exact archive, passed payload validation and returned read-only
`state=base`, `status=absent`, `v0.10_modules=absent` with exact current p1 and
prefix digests plus `write_started=false` before authorization. The completed
transaction, including both fail-closed recoveries, the separately authorized
legacy-inventory cleanup and the ordinary persistent boot, is recorded below
and in the promotion README.

## Accepted physical result

The single attended batch ran on 2026-08-23. CH340 capture opened at 1,500,000
before cold power-on, switched to 115,200 at the exact OP-TEE marker and sent
one autoboot interrupt. The reviewed p2 command file was rehashed before its
one-shot commands loaded the exact v0.15 Image and DTB; neither p1 nor the
persistent U-Boot environment changed, and `saveenv` was never used. This cold
boot selected SDR104 directly at 150 MHz without the intermittent 400/300 kHz
initialization error.

Three defects found inside the accepted physical boundary were corrected by
guarded p2 transactions rather than another media rewrite:

- commit `9f748dad513e545ee4af53eb7f2d7db257d22996` accepts the tab-separated
  fields emitted by the real MMC debugfs node. Installed storage-audit
  SHA-256 is
  `08ed33dace8a94a6b129d72896c8e6a657b32d15c74d9ecf48df99a9f49ae95c`;
  its root-only receipt SHA-256 is
  `d7f3b7cf5dda67e7799eabc13d385b880eaf3738a1bfa5fd5bcdd353e533450e`.
- commit `2c21c7ea389174263986a8ce5f3434f192145591` makes both native analog
  sticks independently visible. Its validated archive SHA-256 is
  `edfa12d8d23730960243781da89d34ac158afd8fe02255787a2681cb1785b426`;
  installed core SHA-256 is
  `a6618fec16ab91fcfbc76497416c4542d1973862affb82f633ee70d600739085`;
  receipt SHA-256 is
  `a28477802e06bcbe5628ea2721c75bf3acd2601aa9cba7800f618348a4e47928`.
- commit `e2c34896685aca46c191166840273965094f1839` replaces the inaudible raw
  mixer value `20,20` with the already physically bounded `201,201` value.
  Its validated archive SHA-256 is
  `d5187b78c9cc582006b15533536a28239df6f91b26d404377b8a8856a01597e5`;
  installed runner SHA-256 is
  `867664284d932cd23757b40d7108ed878d3ab8d16f5655956543444619e75ff3`;
  receipt SHA-256 is
  `7d1d6c86296dafc9a7f199476be4164eb505ce0d38291950ca4e46c5e611a17b`.

Each transaction first matched the original file hash, metadata and a clean
process boundary, retained its original and candidate under a root-only
directory, verified the replacement before an atomic rename and removed the
unprivileged transfer staging. The original v0.3 ext4 image does **not** contain
these fixes; the v0.4 host result below integrates them under a new reviewed
artifact identity without borrowing this live result as v0.4 physical proof.

The exact v0.15 release, Hantro/exFAT module vermagic, built-in Panfrost/RK817,
one active combined gamepad, zero ext4 errors and zero failed units passed.
The operator confirmed D-pad, A, both separately rendered sticks and Select+X.
The first audio attempt was inaudible at the rejected `20,20` setting; after
the bounded scale correction, the operator heard the normal RetroArch tone
through the built-in speaker, then through the fully inserted headset while
the speaker became silent. No higher-gain retry occurred. ALSA cleanup restored
`201,201`/HP and left no RetroArch process or temporary game session.

The fresh user History was initially empty. Starting the exact
`/roms/nes/r46h-nes-smoke.nes` once from the ROM browser loaded Nestopia and
passed D-pad/A; it created exactly one regular `ark:ark 0600` History item with
the exact path and core. The operator then reopened that item from History and
returned with Select+X. The final read-only storage audit passed SDR104 at
150 MHz with zero ext4 errors and correctly reported
`a2_command_queue=not-available`; p1 and p3 remained unmounted.

After final module, hash, service and fault checks, `sync` plus controlled
poweroff remounted p2 read-only, unmounted all filesystems and reached
`systemd-shutdown: Powering off`; ten later seconds contained no serial bytes.
The cold-boot-through-History capture is
`mainline/out/r46h-serial-logs/gaming-product-v015-firstboot-20260823T095551Z.bin`,
92,162 bytes, SHA-256
`2de4a77b97b5720cb51041abf3042f57f1dd54f7f4e30cb709c1f3116952563f`.
The reattached postflight-through-poweroff capture is
`mainline/out/r46h-serial-logs/gaming-product-v015-postflight-20260823T110550Z.bin`,
21,236 bytes, SHA-256
`06b496e12bdd97caea0873cf2a600b684b466df8fb070af143a6f6a2bf1ff13f`.

## Accepted persistent BOOT result

After explicit p1 authorization, the promotion restored and receipted the
exact 1,276-module v0.10 fallback tree. Its first real flush exposed a missing
wrapper-to-helper device binding and stopped with active v0.10 unchanged;
source fix `faf84e8c0c5f45e4ea2bc9232ba3918511097da4` added the production
flush regression test. Recovery then stopped independently because p1 had only
693,760 free bytes. With separate operator authorization, the two unreferenced
13,096,968-byte legacy kernel inventory copies were preserved below the
root-only p2 promotion state, rehashed, and only then removed from p1. Backup
RECEIPT SHA-256 is
`620d3cee882fc8c1d107a8dd42ef11ead09e317de3228b34c05259b4bb4a8012`;
reclaim RESULT SHA-256 is
`02a00d3521e1b4b7fe4a0ab995f8265541242d0b7f8cd84aed6a240637c7bbe4`.
The root legacy `Image`, versioned v0.8/v0.10 files and active v0.10 remained
exact; free space rose to 26,888,704 bytes and read-only FAT checking passed.

Documented prepare recovery then produced raw p1 SHA-256
`daccd70b7c9f021eb8ae114e5b272ae404806e71892049675e5c4ed6119c0642`.
Activation changed only active `boot.ini`, retained exact v0.10 and v0.8
kernel-plus-module fallbacks, never called `saveenv`, and produced final p1
SHA-256
`e6ca320b5413a6fe224a8a9a89c3d4199d395237d3fc413ef93da50131e481c9`;
the 16 MiB prefix remained
`3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3`.
The prepare-through-activation serial capture is
`mainline/out/r46h-serial-logs/gaming-product-v015-persistent-promotion-20260823T123024Z.bin`,
141,737 bytes, SHA-256
`59233631562cd315270371ffba536f1fe2ea15bb080806a48663fa9489cd6457`.

The following serial-first ordinary cold boot used no autoboot interrupt and
loaded exact persistent v0.15, exact DTB and p2. It reached multi-user with the
input/frontend/Hantro/Wi-Fi services healthy. The boot also supplied the
independently tracked twelfth intermittent MMC recurrence: one 400 kHz
`error -84`, then ordered 300 kHz retry, SDR104 at 150 MHz, p1/p2/p3 discovery
and read-write p2 mount, with no later MMC/block/ext4 fault. The original
checksum-bound postflight correctly refused its broad fault marker but could
not distinguish this already tracked, fully recovered sequence. Commit
`6febc0b82ef2976f74d1b47e910bf6a49e638368` added an exact ordered classifier,
rejection tests for repeated/reordered/other errors and a one-transaction
completion path that mounts p1 read-only and changes only the p2 status state
line. All 16 tests passed. Its clean deterministic future package is 47,708,155
bytes with SHA-256
`023c4cff3f7b237cfb7abd1e6ce2634389f924380aec44b2e116ed6b68c293f0`;
that host artifact was not substituted for the retained target payload.

The guarded completion rehashed the retained payload, all three module trees,
active BOOT, final p1/prefix, product hotfixes and legacy backups, then published
the exact 13-line `state=complete` status with SHA-256
`1dec0439d0a781db1a07008db793796652df4a0f5b3be0231b7711d9e70f34aa`.
Zero ext4 errors, zero failed units, inactive frontend, absent RetroArch/session
state and unmounted p1/p3 passed independently. Temporary SSH authorization,
transfer files and root staging were removed. Controlled poweroff remounted p2
read-only, unmounted all filesystems and reached `Powering off`; twelve later
seconds contained no serial bytes. The ordinary-boot-through-completion capture
is
`mainline/out/r46h-serial-logs/gaming-product-v015-persistent-coldboot-20260823T143219Z.bin`,
72,630 bytes, SHA-256
`e8e77f40c1082e36f1a7684cc5f13dbaaa287b41ed5cbdefe3fe0a2c6ff573ad`.

This accepts the live hotfixed first-version NES/RGUI product with persistent
v0.15 and exact v0.10/v0.8 fallbacks. It does not turn the unmodified v0.3 raw
image into a final distributable or close the intermittent MMC item.

## Rebuilt bottom-image host result

Clean bottom-image source commit
`86c81340a123be6710722d7375c50c1a29a65ecc` fixed the cumulative gaming v0.4
archive built from commit `64d1393d75781694ab4b90a67ff2065ad10f9250`.
The archive is 263,525,002 bytes with SHA-256
`208d81c1a0302f3478ac67414bc5a3c2262aefeb9befec9f1182826cbc0ad81d`;
its build-commit physical/persistent product document and all payload checks
passed. Its three relevant installed-file identities exactly match the live
accepted values:

- storage audit:
  `08ed33dace8a94a6b129d72896c8e6a657b32d15c74d9ecf48df99a9f49ae95c`;
- dual-stick smoke core:
  `a6618fec16ab91fcfbc76497416c4542d1973862affb82f633ee70d600739085`;
- `201,201` game runner:
  `867664284d932cd23757b40d7108ed878d3ab8d16f5655956543444619e75ff3`.

That clean closure produced
`mainline/out/r46h-debian13-p2-gaming-v0.4/r46h-debian13-p2-gaming-v0.4.ext4`,
exactly 10,716,877,312 bytes with SHA-256
`aa83ab8d080226018df9016a9eeee5ad3a14c13ef6ffe05128ab86566dde4e69`.
The complete rootfs file and tree manifests have SHA-256
`c99693cd9bfb3cfabcf37abc45d5eb4bde365cba28784622d5f147711fd01a46`
and
`72abe4699628a4a93c1f2324c58dadc5209c7244b94fb03e4e7bdb529b705380`.
Exact v0.8, v0.10 and v0.15 module trees, 422 package rows, 29 retained output
hashes, systemd, RetroArch/Nestopia, clean ext4 geometry and offline `e2fsck`
passed. An independent post-publish validation reopened all retained evidence
and reproduced the image digest.

This build result was **HOST-ONLY PASS** when published. No v0.3 physical
observation is borrowed as v0.4 proof. The later media and live-target results
are recorded below; neither changes this artifact's original host-only evidence
level or adds commit `98ec4d0` to the raw image.
EmulationStation, arbitrary ROMs, automatic jack reporting, full A2 command
queue behavior, suspend/resume and long-duration thermal operation remain
outside this result.

## V0.4 media and focused regression contract

Status: **MEDIA WRITE + DUAL FULL READBACK + LIVE PHYSICAL PASS / RAW IMAGE CONFIG SUPERSEDED**.

The authorized media transaction is complete and does not itself prove target
boot. The board remained serial-confirmed off, and the TF card was rediscovered
as one explicit whole macOS disk. The only eligible profile was
`hl-r46h-v22-g92-62534975488-v1`: 62,534,975,488 bytes, 512-byte sectors, the
fixed three-partition geometry and prefix SHA-256
`3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3`.
On 2026-08-24 an audit-mode Card Agent session fixed that insertion as
`/dev/disk6`, proved the profile and prefix, and unmounted all three partitions.
Its complete current-p2 clone and independent reopened raw hash both produced
`7d4feea24f12aec1d383d648748dd8af42464c870f24d175650efb8474bb449e`.
The retained rollback clone is 10,716,877,312 bytes. At audit completion no
write had started.

The same session failed closed when raw p1 produced
`78d238eb6da8562f8d30ee2fcbea376c0abd24f0b335fa2b3c950eec5826d171`
instead of the historical target-side final digest
`e6ca320b5413a6fe224a8a9a89c3d4199d395237d3fc413ef93da50131e481c9`.
A retained p1 clone passed `/sbin/fsck_msdos -n`; all 169 expected
non-Spotlight files matched the transformed persistent-v0.15 manifest, with
169 current files and missing, extra and changed counts all zero. The active
v0.15 and exact v0.10/v0.8 BOOT payloads all matched their accepted hashes.
Mutable Spotlight content and raw FAT metadata are outside that file manifest,
so the historical target-side digest remains valid evidence while `78d238...`
is the accepted raw pre-write baseline for this reinserted card.

The stopped audit session, exact events, p1 evidence and p2 rollback clone are
retained under
`mainline/out/r46h-card-agent-sessions/session-20260824T025608Z-4440-215c307f-a2aa-4ed4-b421-56d10d495f4f/`.
The operator then explicitly authorized the newly rediscovered `/dev/disk6`,
that profile, the p2-only scope and complete p2 state loss. A separate deploy
session reproduced the fixed profile, prefix, current raw p1 and current raw p2
with all partitions unmounted before mutation.

This was a complete p2 replacement, not a state-preserving update. It removed
the live Wi-Fi profile, generated SSH host keys, operator password change,
History/save state and prior root-only transaction/backup state. The generic
image returns to the documented initial serial credential, generates fresh SSH
host keys and contains no personal public key or network secret. The complete
pre-write clone remains the ignored, local and unshared rollback copy and is
not deleted merely because the new image later boots.

After that authorization, clean source commit
`c221638ff8d6d5f10c1581cbc37190177c849408` generated the exact plan:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/generate-debian13-write-plan.py \
  --device /dev/disk6 \
  --profile-id hl-r46h-v22-g92-62534975488-v1 \
  --artifact-id debian13-p2-gaming-v0.4 \
  --target-sha256-before 7d4feea24f12aec1d383d648748dd8af42464c870f24d175650efb8474bb449e
```

The 569-byte mode-0600 plan has SHA-256
`f66191f53d4040022bba99d02708301044c78d218c1984491a6563bde2d3e347`
and contains only `write-debian13-p2-gaming-v0.4`. The separate deploy session
reproduced old p2 `7d4feea2...`, exact source image
`aa83ab8d080226018df9016a9eeee5ad3a14c13ef6ffe05128ab86566dde4e69`,
and executed that one operation. Its complete internal readback and a later
independently reopened complete p2 hash both equal the source. It published
`WRITE_COMPLETE` and `safe_to_boot=yes`.

Raw p1 remained byte-exact at
`78d238eb6da8562f8d30ee2fcbea376c0abd24f0b335fa2b3c950eec5826d171`;
the prefix remained byte-exact at
`3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3`.
p3 was never mounted or written, all partitions were unmounted, the agent
stopped and macOS ejected the card. The detailed ignored result is
`mainline/out/r46h-card-agent-sessions/session-20260824T031826Z-13325-d7d1fdbc-a2dc-4f14-95b0-db486fb3030d/POSTWRITE-AUDIT.json`,
SHA-256
`a72335a5ad800f088f0090d07871bcc403427f1e9b49f5da0122fb7328743bcf`.
At that point, the result accepted media write/readback only; the later target
gate below supplied the separate live physical evidence.

The one allowed cold boot is serial-first at 1,500,000 baud, switching to
115,200 only after the visible OP-TEE marker. It uses the already persistent
v0.15 BOOT path without an autoboot interrupt or `saveenv`. Machine checks are
limited to exact v0.15, root PARTUUID `c9f931c9-02`, filesystem UUID
`d3130004-46a4-4d56-9001-000000000004`, firstboot marker
`release=debian13-p2-gaming-v0.4`, the consolidated receipt, all three module
trees, the three accepted hotfix hashes, one combined gamepad, clean service
state, zero ext4 errors and either clean MMC initialization or the already
bounded single recovered intermittent sequence.

The attended screen/audio observations are one combined regression, not a
repeat of the earlier diagnostic batches: automatic RGUI; the installed smoke
ROM at `/roms/nes/r46h-nes-smoke.nes` opened with Nestopia; D-pad, A and both
independently rendered sticks; **Select+X** back to RGUI; normal speaker audio
followed by fully inserted headset audio with mechanical speaker cut-off. The
custom smoke-core portion must also prove that the left stick moves only its
cyan marker and does not move the D-pad marker. Run
the installed read-only storage audit once and require SDR104/150 MHz, zero
ext4 errors and
`a2_command_queue=not-available`. Do not test higher gain, jack GPIO/events,
input diagnostics, storage writes, command-queue acceleration or another BOOT
promotion. Finish with exact hash/service/fault checks, remove only test-created
runtime state, `sync`, controlled poweroff and serial confirmation.

The first 2026-08-24 v0.4 target run passed the exact boot/root/receipt/module
and hotfix hashes, one combined gamepad, service health, zero ext4 errors and
the read-only SDR104/150 MHz storage audit. Its first cold initialization had
the accepted single `-84`/300 kHz recovery sequence and no later MMC, block or
ext4 fault; a second required boot initialized cleanly. The operator confirmed
the custom core's D-pad, A, both analog markers, normal speaker audio and
Select+X, plus an additional bounded headset check at the accepted `201,201`
mixer value and scale 40: left-only, silence, right-only, with the built-in
speaker silent throughout.

That run also found one product-config regression: the explicit numeric D-pad
axis binds made the left stick move both its cyan marker and the D-pad marker,
even though `input_player1_analog_dpad_mode` was already zero. Commit
`98ec4d02fbcbd8b11e33e488d4c0811db1b9b67a` sets all four D-pad axis binds to
`nul` while retaining the four native analog-stick binds. Its focused 15-test
gaming-MVP suite and 23 rootfs/gaming-rootfs tests passed before target work.

After explicit authorization, the one-time p2 installer matched its own
SHA-256 `d5b97ab7955eeed99ad86eac7da895bc418e624c0f080813665dabfdd98b8bf3`,
exact persistent v0.15, root PARTUUID `c9f931c9-02`, the v0.4 receipt, clean
health, inactive frontend, unmounted p1/p3 and original config SHA-256
`d75edaf499adf15e2476dcd0a49b9ebe573c2003cb24ea0387d440582c37b595`.
It atomically installed exact candidate
`99a45beb148e58e40983773b4f5e26d9fb5d7e1bbbf6a7e714a5c352e43c0dba`
as root-owned mode 0644 `/etc/r46h/retroarch.cfg`. Root-only state at
`/var/lib/r46h-gaming-input-separation/v0.1` retains the old and candidate
files plus metadata; receipt
`/var/lib/r46h/gaming-input-separation-v0.1-installed` has SHA-256
`77c302dde8a2f12c9bafc40ea572ef941c8452b87e7a8fc348c56dcdbac3a351`.
The installer reported `result=pass`, `frontend=inactive`, `p1=unmounted`,
`p3=unmounted` and `ext4_errors=0`. Transfer and installer files under `/run`
were then removed; p1, p3 and BOOT were not changed.

For the post-install observation, an audio-disabled tmpfs derivative was bound
temporarily over the config. The operator confirmed that D-pad moved only the
upper marker and the left stick moved only the cyan marker. Serial stopped the
core, the bind and derivative were removed, and the persistent config rehashed
exact. Automatic RGUI then launched `/roms/nes/r46h-nes-smoke.nes` with
Nestopia; D-pad, A and Select+X all passed. Final state had no RetroArch process,
an inactive frontend, zero ext4 errors, zero failed units and p1/p3 unmounted.
`sync` completed and serial captured p2 remounted read-only, all filesystems
unmounted and `Powering off.`

The 209,306-byte capture is
`mainline/out/r46h-serial-logs/gaming-product-v04-firstboot-20260824T034030Z.bin`,
SHA-256
`cc762b0f8525efdf0d4c9ce53a1f463a08fde1ab173e44ca6ab98d56881128c0`.
This accepts the current live p2. The raw v0.4 image `aa83ab8d...` predates
commit `98ec4d0` and must not be distributed as if it contains the correction;
the v0.5 host result below integrates that commit. Do not repeat this completed
physical gate or rewrite the working card merely to reproduce it.

## Rebuilt v0.5 bottom-image host result

Clean builder source commit
`44c1b0293061d03805c204c3b383ebb8ca8cc017` pinned the cumulative gaming
v0.4 payload generation built from accepted-results commit
`9cb978888b54ddc68dbaa600daf9cb38f006c047`. That 263,529,005-byte payload has
SHA-256
`c192e6301b112e26436836e59fc8b9cf82af85851352d8db1a41bebb942e2c2e`;
its immutable payload ID remains `r46h-gaming-mvp-v0.4`, while the containing
bottom image receives the v0.5 identity because its bytes differ from raw
v0.4. The payload pins all three earlier accepted live hotfixes plus corrected
`retroarch.cfg` SHA-256
`99a45beb148e58e40983773b4f5e26d9fb5d7e1bbbf6a7e714a5c352e43c0dba`.

That clean closure produced
`mainline/out/r46h-debian13-p2-gaming-v0.5/r46h-debian13-p2-gaming-v0.5.ext4`,
exactly 10,716,877,312 bytes with SHA-256
`ee7d402c06a750081b4c588c5162cca44d0e07fa4b544d5a59bef7629722aeca`.
Its ext4 UUID is `d3130005-46a4-4d56-9001-000000000005`, label is
`R46H_GAMING_V05`, and offline `e2fsck` reports a clean filesystem. The
29-entry output checksum manifest has SHA-256
`e844e13b1ea458adda6cad447f6f73b8a017ca983998870df404cc4464cde0e7`;
all entries rehashed successfully during an independent post-publish
validation. The complete rootfs file manifest has SHA-256
`1ad54bc7afa6f4e16b21a726663f630bd02769c4a5ab50d0b7c40ef36f718d83`.
Exact v0.8, v0.10 and v0.15 module trees, 422 package rows, product
Image/DTB/root-only one-shot commands, systemd, RetroArch/Nestopia, absent
personal authorization and diagnostic bridge, ext4 geometry and source closure
all passed.

This build result is **HOST-ONLY PASS**. It closes the reproducible raw-v0.4
config gap without borrowing the live-v0.4 result. The later media result below
is separate and still does not prove a target boot.

## V0.5 accepted media result

On 2026-08-24 the card was newly rediscovered as `/dev/disk6`, exact profile
`hl-r46h-v22-g92-62534975488-v1`, with all three partitions unmounted and fixed
prefix SHA-256
`3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3`.
The complete current p2 independently hashed as
`c7dee8dac10f41593beb9327b8145d8e2b329ab8b0ca619d8b9b00c09a226b3a`.
The audit retained a full 10,716,877,312-byte rollback clone and an independent
host rehash reproduced that exact digest. Its ignored `PREWRITE-AUDIT.json`
has SHA-256
`5451573a5d4278ef68e1c62d79e3f3be5d2768545d39e141e36acafa8bd5ca3a`.

Clean source commit `5f49de24d546cfd2af4e93a8ab1571c292e08fc6` added only
the fixed-profile v0.5 artifact identity and its focused test. The generated
mode-0600 p2-only plan has SHA-256
`17bd631ecc04c598b1216d478f580c108af4636701f58d43d3f9e54be8355535`
and binds source `ee7d402c...` to target `c7dee8da...`. After the operator
explicitly authorized that fixed device, plan and complete current-p2 state
loss, Card Agent revalidated the profile, target and root-only source staging,
passed its no-write cache synchronization preflight, then wrote only p2.

The complete in-transaction readback and a separately reopened full-p2 hash
both equal source SHA-256
`ee7d402c06a750081b4c588c5162cca44d0e07fa4b544d5a59bef7629722aeca`.
Raw p1 remained byte-exact at
`042ad4ad08f39f60f1d57e393ab32ae148e2a946ab9996822ae161934f7a0825`;
the 16 MiB prefix remained exact, while p3 was outside the plan and stayed
unmounted. `WRITE_COMPLETE`, `safe_to_boot=yes`, all-unmounted final state,
agent stop and macOS eject passed. The ignored `POSTWRITE-AUDIT.json` has
SHA-256
`5b17889b629fc621b8238087b129490f72bf594f17edf7059679ab6852d5c8f7`.

At media completion this was **MEDIA PASS / PHYSICAL OPEN**. Do not repeat the
write or reuse the spent plan. The separately recorded target result below now
supersedes only that open physical boundary; it does not change the accepted
media evidence.

## V0.5 attended target result

The one allowed serial-first cold target attempt ran on 2026-08-24. Capture
opened at 1,500,000 before power-on, switched to 115,200 at the OP-TEE marker,
and did not interrupt ordinary U-Boot autoboot. U-Boot loaded exact persistent
`6.12.99-r46h-mainline-v0.15-gaming-product` and the expected root PARTUUID,
but Linux did not mount p2. `mmc0` reported `-84` at 400 kHz, `-110` at
300 kHz, then stuck-busy `-110` failures at 200 and 100 kHz and remained at
`Waiting for root device PARTUUID=c9f931c9-02`. This is not the previously
bounded single `-84` followed by a successful 300 kHz recovery. It is the first
captured non-recovery in the tracked set. The cold gate therefore **FAILS**.

One operator short Reset was then used as a warm rescue, not as a replacement
cold qualification. The unchanged persistent boot reached SDR104/150 MHz
directly, enumerated p1/p2/p3 and mounted exact v0.5 p2 UUID
`d3130005-46a4-4d56-9001-000000000005`, label `R46H_GAMING_V05`. Exact kernel,
firstboot release, clean-source receipt, config `99a45beb...`, the three
accepted runtime hotfixes, NES ROM and gaming receipt `0a0675e8...` all
matched. Independent target rehashes covered 1,290 files in each module tree:
v0.8 `2ec532a3...`, v0.10 `a70796c0...` and v0.15 `bd53fad3...`.

All five checked services were active and enabled, exactly one
`R46H Combined Gamepad` used bridge v0.5, failed units and ext4 errors were
zero, and the installed read-only storage audit passed SDR104/150 MHz with
`a2_command_queue=not-available`. The operator then confirmed that D-pad moved
only the blinking upper marker and the left stick moved only the cyan
lower-left marker. A short exact Nestopia regression passed D-pad movement, A
blue/black background switching and **Select+X** return to RGUI. Audio was not
repeated. The two bounded UI helpers were deliberately interrupted only after
the observations; both restored the mixer and reported process cleanup pass.

Final checks found no RetroArch process or helper runtime directory, exact
config and receipt hashes, p1/p3 unmounted, zero warm-boot MMC fault lines, zero
ext4 errors and zero failed units. `sync` passed, p2 remounted read-only, every
filesystem unmounted and serial reached `Powering off.` The 620,192-byte
capture is
`mainline/out/r46h-serial-logs/gaming-product-v05-firstboot-20260824T063956Z.bin`,
SHA-256
`015e571c0f0f4a5ebe967a9543d5b68d58cf1e39ea4c6608c5371ec79d7b522f`.

This initial result accepts **v0.5 media and warm-boot product functionality**,
but did not accept v0.5 as a cold-bootable first-version release. Do not repeat
the media, module, input or Nestopia gates unchanged. Retain rollback clone
`c7dee8da...`. A Reset workaround must not be silently promoted to release
success; the later changed-candidate evidence is recorded separately below.

## V0.16 one-shot cold result

Clean commit `48173de13e16d39a4202bd736d4e833d6d949542` froze one
candidate that changes only secondary `/mmc@ff380000/status` to `disabled`.
The exact v0.15 Image/modules, system `mmc0` and SDR104/150 MHz remain
unchanged.  Its ordinary staging boot supplied the thirteenth recovered
dual-host recurrence, then the single attended candidate cold boot passed
without Reset: Linux probed only `ff370000/mmc0`, moved once from 400 kHz
directly to 150 MHz with no initialization error or timeout, enumerated all
three partitions, mounted exact v0.5 p2 and reached multi-user.

Exact modules and live-DT statuses matched.  The installed read-only product
audit passed SDR104/150 MHz, zero ext4 errors and
`a2_command_queue=not-available`; final MMC/block/ext4 fault matches, failed
units and p1/p3 mounts were zero.  The exact one-shot payload and all
test-created transfer/authentication state were removed before `sync` and
serial-confirmed controlled poweroff.  The detailed 87,023-byte capture,
SHA-256 `54c081d0ea2ed2dd4345de2e85e348a9c78e1e0fc0357f7df216b7e326adcba5`,
and the out-of-scope legacy read-only helper limitation are recorded only in
[`V16-MMC-COLD-ISOLATION.md`](V16-MMC-COLD-ISOLATION.md).

This accepts one physical mitigation sample, not general cold reliability or
proof that concurrent probing is the sole cause. The first persistent archive
from source `e47adf35182e...` was revoked when target preflight exposed an
unmodelled baseline `.fseventsd` directory before any write. Corrected clean
source `408baa52f95d1c66c321ccc820a4481cb7ac2266` produced independently
validated generation `build-408baa52f95d-99d162b5d920`: 29,123 bytes,
SHA-256
`99d162b5d920f14108d9d7ff725f96f3e0e52d20dbd713fac46a4a53023ad042`.
It binds the current post-v0.5 raw p1 and full-p2 baseline while preserving
exact v0.15/v0.10/v0.8 fallbacks.

Corrected target preflight, prepare and activation passed, but the separately
contracted persistent cold boot did not meet its clean-only gate. Exact v0.16
disabled Linux `ff380000` and reached exact v0.5 multi-user without Reset, yet
system `mmc0` still emitted one 400 kHz `-84`, recovered at 300 kHz and reached
SDR104/150 MHz. Postflight failed closed before completion. Exact rollback and
retained preflight then passed as active v0.15, inert v0.16 files,
`status=rollback-complete`, raw p1 `7d319785...`, unchanged prefix and no
`saveenv`. Cleanup, final health and controlled poweroff passed. At that point
v0.5 remained non-releaseable for cold boot and active BOOT again used the
earlier dual-host v0.15 DTB. Disabling the secondary controller was not
sufficient to eliminate the recovered system-card error. Do not repeat either
v0.16 sample or any completed functional or media gate; the changed successor
is recorded below.

## V0.17 persistent cold acceptance

Clean source `6b16dfc2d6e8` first changed only the system-card
`post-power-on-delay-ms` from 10 to 800 ms while retaining the v0.16
secondary-host isolation and exact v0.15 Image/modules. Its one p2 one-shot
cold sample passed without an MMC fault. Clean source `622cf60feab7` then
produced the independently reproduced rollback-safe persistent generation
`build-622cf60feab7-c2eea1243359`. Target preflight, prepare, activation,
fallback checks, cleanup and first controlled poweroff passed without
`saveenv`; exact recovery state remains on p2. The canonical transaction and
hash boundary is
[`../gaming-product-v17-boot-promotion/README.md`](../gaming-product-v17-boot-promotion/README.md).

One separate 2026-08-25 serial-first persistent cold boot loaded exact
v0.17/v0.15 without Reset or autoboot interruption. Linux instantiated only
`ff370000/mmc0`, measured 819.113 ms then 902.528 ms through 400 kHz to
SDR104/150 MHz, enumerated p1/p2/p3, mounted exact v0.5 and reached multi-user
without an MMC, block-I/O or ext4 fault marker. Strict retained postflight
verified live DT bytes `00 00 03 20`, exact fallbacks/modules, clean boot state,
product storage health, zero ext4 errors and no failed units. It published
`state=complete` status SHA-256
`3b4265849e446ee8566e47fbfb7d7ee4145bdd0d732caa7b5913684b4e4d3034`
with final p1 SHA-256
`ad71f67bfb436cc480bb9a83db770f88cdcadc54612b322d9106befa0982929b`
and `saveenv_used=false`. Final controlled poweroff passed; the 58,567-byte
capture has SHA-256
`c84dccd4bff90421c8a4741ebf5598b9ea7f86e619cb22212fefa6615ee97f70`.

The exact v0.5 p2 plus exact v0.17 BOOT state is the accepted first functional
version for this fixed card/profile. This does not establish statistical
cold-boot reliability or prove secondary isolation independently necessary.
Clean source `2e0d33a53f11` later closed the integrated host-source gap with
four-range generation `build-2e0d33a53f11-e1e8d9edb2f8`; its exact boundary
is in [`../first-version-release/README.md`](../first-version-release/README.md).
That generation has not been written to a new card. The second card slot is
unavailable. Do not repeat accepted cold or functional gates merely to raise
the sample count.
