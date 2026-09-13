# R46H combined gaming input bridge

Status: **V0.1 PHYSICAL FAIL / V0.2 TARGET-INCOMPATIBLE / V0.3 PHYSICAL
FAIL / V0.4 REJECTED BEFORE STAGING / V0.5 COMPOSITE PHYSICAL PASS /
CLEANLY REMOVED**

The first userspace archive failed its second review before any device staging:
its payload-directory link-count guard rejected a correctly extracted Linux
directory, its bundled instructions had the wrong install order, and its trial
could not measure the right stick or the complete identified button set. That
archive is rejected. The corrected source and target-Linux regression gate are
implemented below. Its clean replacement passed that gate and is recorded here.
The replacement was then exercised once on the R46H and failed the complete
physical contract described below. It is no longer installed.

A v0.2 userspace correction addressed the observed RetroArch path without
changing the kernel or event bridge, but a later current-state review rejected
it before device staging. V0.3 carried the same input correction on top of the
accepted History v0.2 state. Its reviewed host artifact passed, but its only
physical trial failed a different complete-coverage boundary and it has been
cleanly removed.

V0.4 was also rejected before staging after a second review found that
`ProtectSystem=strict` made its top-level `/run` diagnostic path read-only and
that its per-stage acceptance could miss partial virtual-event loss. V0.5 keeps
the v0.3 RetroArch config, physical-device discovery, mapping and event
forwarding unchanged. It moves diagnostics into a systemd-managed writable
runtime directory, makes uinput write failure terminally visible, compares full
key event counts and compares source/virtual axis geometry. Its provenance-bound
archive passed build and independent validation, then ran once on the R46H.
Fourteen exercised keys, all four axes and all three required screen
observations passed, but the operator forgot L3/R3. The complete physical
contract was therefore incomplete rather than failed at those two sources. On
2026-08-21 the separate 20-second completion captured exact
source/write/virtual press/release agreement for both L3 and R3 with no dropped
event. Combined with the unchanged 2026-08-20 result, this closes the
controller contract by composite physical evidence. The candidate has been
cleanly removed and both one-shot contracts are spent.

This is an optional, rollback-safe follow-up to the accepted gaming MVP. It
combines the existing `gpio-keys` gamepad and four-axis `adc-joystick` into one
virtual evdev gamepad for RetroArch. It does not replace either physical input
driver, change ADC calibration, touch BOOT or claim physical success from host
tests.

The accepted v0.10 and current v0.13 configs have
`# CONFIG_INPUT_UINPUT is not set`, so the bridge cannot run on those kernels.
The independent candidate release is:

```text
6.12.99-r46h-mainline-v0.14-gaming-input-bridge
```

Relative to v0.13, v0.14 changes only `LOCALVERSION` and enables built-in
`CONFIG_INPUT_UINPUT=y`. Keeping it built in avoids a module-install dependency
during the later one-shot test. The candidate retains v0.13 MMC diagnostics and
the host-only v0.12 charger policy, but neither is an acceptance target for the
input test.

## Accepted host artifacts

The candidate source was committed as
`22be1f1381289cbd20c980591aefc1c32ca4a48d`. The clean kernel build produced:

- package size `33,270,314` and SHA-256
  `7bdf2aff75373c8482926131fc9f953030a05c66046cc147618c29e2ae939a62`;
- Image SHA-256
  `b02a2c4467a4c9ba1a0c1f3eac75ecd8d7fcb40c6e3d5d9d1d5d34e17a0ef10e`;
- DTB SHA-256
  `d1b035ee09ed0c44ccad62304f0c588d302c6055f634e65390850163cceba8ad`;
- config SHA-256
  `7318c868dd729749434b9e71f1f7f93efcb3dde4f1808fc58f2a2ff790b47808`;
- 1,276 `.ko` files, 1,290 module-tree files total, and module-tree SHA-256
  `adba2f4a0d116d8e077a3f44ba85d37cea758e7ab8d799d0da7d18702d30ebde`.

The final config diff against v0.13 contains exactly two assignments:
`LOCALVERSION` selects the independent v0.14 release and
`CONFIG_INPUT_UINPUT=y` replaces the disabled setting. The complete package
has 1,294 checksum-bound data files. This establishes source and host-artifact
identity only; it does not establish that v0.14 boots or that the bridge works
on the R46H.

The accepted corrected userspace source was captured from clean commit
`83456088025dd8305e6f10b93047c77c9ea3517b`, tree
`60f81c78f2e02de506e3e16b8f1e048f8d79468f`. Generation
`build-83456088025d-e0c1cc1c9c28` contains a 19,508-byte archive with SHA-256
`e0c1cc1c9c28149d6892b8ab9c85fa421ba7b2566404b0882c34e055c6f831c2`;
its 67,400-byte AArch64 bridge binary has SHA-256
`fc162a43b4fe2a28b3aa3451eb52bb05604a8b26934a4651665256c432e39c0f`.
The builder extracted the actual archive inside the pinned AArch64 Linux image,
directly executed `install.sh --check-payload` from an executable `/run` tmpfs
and passed the exact member, metadata and checksum checks. The installer remains
static and inactive.

The rejected first userspace generation was
`build-22be1f138128-04e1418ff076`, archive SHA-256
`04e1418ff0763f473e93bc5bc152600d4da5c73ff49239a28ba7e2bfb85cf129`.
Do not transfer or install it.

The corrected p2 one-shot source was committed separately as
`ba00cebb7b19464c5ea9cdebaa59302d742ec169`. Generation
`build-ba00cebb7b19-b2193f28e1ae` contains the exact Image, DTB and matching
module tree. Its 33,167,980-byte archive has SHA-256
`b2193f28e1ae8cb625d34e9c191bda9eea48d079e28595d39eaddd5c9dbd3a68`.
The installer publishes only a new versioned module directory and an inactive
p2 boot payload. It rejects a writable BOOT partition and never changes p1 or
the persistent U-Boot environment. The guarded remover runs only after an
ordinary return to exact v0.10.

The superseded one-shot generation `build-0a8e49080ab7-3b548dc178ab`, archive
SHA-256 `3b548dc178abd1fd30384b0a6dd28f90e62a217646d361e37f8c923d8ad16087`,
was rejected by the first 2026-08-18 Phase A target preflight. Its 1,290 files
and hashes were correct, but the extracted module tree had 395 directories
while the installer required 396. The installer stopped before any persistent
publication; exact staging cleanup, v0.10 health and controlled poweroff passed.
The corrected builder validates that the canonical module tree, generated tar,
installer and payload metadata all use the same 395-directory count. Do not
transfer the superseded archive.

Revalidate the retained generations without rebuilding:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-r46h-gaming-input-bridge.py validate
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/scripts/build-v14-gaming-input-one-shot.py validate
```

The reviewed archives are below ignored `mainline/out/`; do not build or select
a new copy during the physical batch.

## V0.2 remediation and rejection

The v0.1 event capture proved that the combined virtual device forwarded all
four axes with broad travel and returned them to center. Inspection of the
pinned RetroArch 1.20.0 source then found that its analog-to-D-pad preparation
indexes the manual bind table by selected joypad index. Player 1 selects Pad #1
on this image, while its manual bindings live in the player-port #0 table. The
automatic mode therefore did not publish the left-stick axes to the smoke
core's D-pad queries, matching the physical observation.

V0.2 keeps Pad #1 and all four native analog bindings, adds explicit player-1
D-pad axis bindings (`-1`, `+1`, `-0`, `+0`), and disables the ineffective
automatic analog-to-D-pad mode. It also gives the operator explicit L3/R3 stick
cap instructions. The bridge forwarding code, v0.14 kernel and one-shot archive
are unchanged. Because the payload contents changed, all userspace state,
receipt, binary version and archive identities advance from v0.1 to v0.2.

The clean v0.2 source commit is
`97b12b79c3b73b5eb99892e7abc12f5b8dd98691`, tree
`4abf531a442b0df135a5a0d799aa8035e3541c03`. Generation
`build-97b12b79c3b7-f34b0b228bef` contains the 19,905-byte
`r46h-gaming-input-bridge-v0.2.tar.gz` with SHA-256
`f34b0b228bef2ae7bb32832f976d654ba97f3ddd2ee43be98a9bfb08be76e060`.
Its 67,400-byte AArch64 bridge binary has SHA-256
`5088bffe53e2ddd9c1f0f3e5f229a9640b20cde191368df6374798b89e56b366`.
The builder and a separate validation pass checked the generation manifest,
deterministic archive, exact payload members and metadata, then extracted the
actual archive in the pinned AArch64 Linux image and passed
`install.sh --check-payload`.

This establishes only that the v0.2 archive was reproducibly built; it does not
claim that the left stick or L3/R3 pass on the R46H.

V0.2 is rejected for the current device state. History v0.2 was installed after
the v0.1 bridge removal, so the accepted active config is now
SHA-256 `697aa82bb42689cd841f16a8ce1ae9c6ac2bdc56ccd1b811136f8f5884e600e9`
rather than the old `621fdf049cd05e6aa02c62b5c42ed37a768ce9342af14c4563cfd4466d80d078`.
The v0.2 bridge installer pins the old hash and would stop before publication;
its candidate config also omitted the five History directory keys. Do not
transfer or stage archive SHA-256
`f34b0b228bef2ae7bb32832f976d654ba97f3ddd2ee43be98a9bfb08be76e060`.

## V0.3 current-state correction

V0.3 advances every userspace payload, state, receipt, binary and archive
identity. Its installer and guarded remover pin the exact seven-line History
v0.2 receipt SHA-256
`9b800245202992cbdc063e5cabd071a6265fbb9133e89a8718d0952209d0f1aa`,
the `ark:ark 0700` RetroArch state root and the accepted History config hash.
The candidate config now differs from the History config only in the reviewed
combined-controller input contract. V0.14 kernel and one-shot contents remain
unchanged.

The missing v0.1 L3/R3 capture does not justify a GPIO or DT change. Earlier
direct physical evidence in
`mainline/out/r46h-serial-logs/v09-one-shot-20260810T230435Z.log` recorded
`BTN_TRIGGER_HAPPY3` and `BTN_TRIGGER_HAPPY4` with three presses, three releases
and a released final state each. That 89,070-byte log has SHA-256
`aec087f408d394ba992030813bf415eacfed3b6ae526dc7e7dad2d70c273d72e`.
V0.3 therefore keeps the input source path and makes the operator explicitly
click the left and right stick caps.

The clean v0.3 source commit is
`c35da7b71f5f6069815d33418d4073d9f80b71b0`, tree
`ec0140c669b403a5ce4b1752dfa264eddf9b156d`. Generation
`build-c35da7b71f5f-e59ff0a4b9d9` contains the 20,253-byte
`r46h-gaming-input-bridge-v0.3.tar.gz` with SHA-256
`e59ff0a4b9d93a362155fbf66ecf8bd79f0d91e22e644919b4046d3d2187ae4f`.
Its 67,400-byte AArch64 bridge binary has SHA-256
`35058bd8b446be58ed936cf35b22ab7f09578d3b6d8919e82636c4ad501ba2f3`;
the source manifest SHA-256 is
`31a20e8350195118c06a06c3b6c9ec0e09f282a1597a905969ceb6bc567f30a9`.
The builder and an independent validation pass checked the manifest,
deterministic archive, exact payload members and metadata, then extracted the
actual archive in the pinned AArch64 Linux image and passed
`install.sh --check-payload`. This is host artifact proof only.

## V0.1 physical result: 2026-08-18

Exact `6.12.99-r46h-mainline-v0.14-gaming-input-bridge` booted from the reviewed
one-shot on p2 with its matching module tree. The single bounded trial reported
`SYN_DROPPED=0`, 14/16 keys, 4/4 axes and 4/4 centered axes. The only missing
keys were `BTN_TRIGGER_HAPPY3` and `BTN_TRIGGER_HAPPY4`, intended as L3/R3;
both had zero presses and releases. Axis evidence was:

```text
ABS_X   140..1018  final 513
ABS_Y    68..940   final 509
ABS_RX   59..882   final 506
ABS_RY   66..926   final 524
```

The operator confirmed visible D-pad and A response on the smoke screen, but
the left stick had no visible response. Other buttons had no screen-observation
requirement. The exact trial result was therefore FAIL, not a partial PASS.

The bridge stopped without a surviving process, virtual gamepad or RetroArch
process. Ext4 errors, failed units and new relevant kernel errors remained zero.
After controlled poweroff, ordinary persistent v0.10 booted; the guarded bridge
remover and then the v0.14 one-shot remover both emitted their exact PASS
markers. Final v0.10 health and controlled poweroff passed.
The frozen v0.1 outcome remains **PHYSICAL FAIL / CLEANLY REMOVED**.

The next run therefore excluded unchanged v0.1 and target-incompatible v0.2,
and used only the reviewed v0.3 archive with explicit L3/R3 instructions and
exact v0.10 fallback. Its result follows; none of these three archives now
authorizes another unchanged trial.

## V0.3 physical result: 2026-08-19

The exact reviewed v0.3 archive accepted the installed History v0.2 receipt,
config and user-state identity, then remained inactive until one exact v0.14
one-shot boot. The only 60-second trial reported:

```text
R46H_INPUT_BRIDGE_COVERAGE keys=4/16 axes=4/4 centered=3/4 failures=13
R46H_INPUT_BRIDGE_TRIAL result=fail status=1 cleanup=check-required
```

`SYN_DROPPED` remained zero. Only `BTN_TL`, `BTN_TR`, `BTN_TL2` and `BTN_TR2`
completed press/release coverage. All D-pad directions, A/B/X/Y, Select, Start,
L3 and R3 were missing from the virtual-pad capture. All four axes recorded
travel, but `ABS_RY` ended at 914 and failed the centering boundary. The
operator confirmed performing all requested actions, including both stick-cap
clicks and both sticks, and observed only the left stick respond on the smoke
screen; D-pad and A did not respond.

This differs from v0.1: the direct left-stick mapping now produced the intended
visible response, but most physical keys did not reach the combined virtual
device in this trial. That observation does not localize the cause to GPIO,
the event-source discovery path or forwarding logic; diagnose those paths from
host/source evidence before creating a new candidate. Do not repeat unchanged
v0.3.

The trial left no bridge process, virtual gamepad or failed unit and retained
zero ext4 errors. After controlled poweroff, ordinary exact v0.10 booted. The
base frontend was stopped, the guarded bridge and one-shot removers both passed,
and all candidate state, runtime files and v0.14 modules were absent. History
v0.2 remained byte-exact and final v0.10 health plus controlled poweroff passed.
The 57,833-byte one-shot serial log is
`mainline/out/r46h-serial-logs/attended-gaming-retry-v014-20260819T115332Z.bin`,
SHA-256 `36f026a5ba8cf8904e6dd06e0bee26c3523019f4d85ed34c526fbad760e78828`.
The detailed three-boot result and final cleanup evidence are in
[`ATTENDED-GAMING-RETRY.md`](ATTENDED-GAMING-RETRY.md).

## V0.4 diagnostic candidate and pre-staging rejection

A direct Git comparison of the v0.1 and v0.3 bridge C sources found no event
discovery or forwarding change; apart from the version string, the bridge code
was identical. V0.3's RetroArch correction explains why the left stick became
visible, but it cannot explain why twelve previously observable game keys were
absent from that trial's virtual capture. Changing GPIO definitions from that
evidence would therefore be speculative.

V0.4 attempted to add observability at the existing userspace seam. For all 17
advertised game keys and four axes, the bridge counts events read from `gpio-keys` or
`adc-joystick` and events successfully written to uinput. On the trial's normal
service stop it writes exactly 23 machine lines to the root-owned
`/run/r46h-input-bridge-diagnostics` file. The trial validates that file,
compares each required control against the non-grabbing virtual `evtest`
capture, emits one of `physical-source-missing`, `bridge-write-missing` or
`virtual-delivery-or-capture-missing`, then removes both tmpfs logs. The service
does not restart on failure, so a diagnostic error cannot silently start a
second uncontrolled trial.

The candidate does not change v0.14, ADC calibration, the input mapping or the
forwarding whitelist. It was designed to remain inactive after staging and use
the same guarded v0.10 removal boundary.

The clean source commit is
`0ffbc170aec02363dd916b6fc53698e00789a5da`, tree
`7da13770ef1f82dcd928904194b17c01414c5e74`. Generation
`build-0ffbc170aec0-e0656d83fc09` contains the 23,450-byte
`r46h-gaming-input-bridge-v0.4.tar.gz` with SHA-256
`e0656d83fc09f4c4ef5a4763c0e839ec7c30fb74eece72567245475006f1bf3b`.
Its 67,480-byte AArch64 bridge binary has SHA-256
`bbb527bc9f44cd054387f8c1d7af6ab14a2c0b7c48c7171769483851c199d2b0`;
the source manifest SHA-256 is
`9a031f35435b32881d544e4c0bfe64f06fce3140bfd5e0db0e0ade7e90bbe461`.
The builder and a separate validation pass checked the generation and source
manifests, deterministic archive, exact members and metadata, then extracted
the actual archive in the pinned AArch64 Linux image and passed
`install.sh --check-payload`.

An independent v0.3/v0.4 payload comparison also found byte-identical
RetroArch config SHA-256
`e3092c469aa50b980b952f139c134ea5a6e9ec42646b29ef594fef4bc88a5545`,
candidate runner SHA-256
`8f7f9a87576d2d670ce485959e897c68260995bf093317a672ea48a6e64c7012`
and waiter SHA-256
`fa949b24a76e4341649ba9c3485cadaa8ec5c871a0ea9776cd8885c797f894ae`.
That host artifact proof did not cover the service mount namespace. Target
systemd 257 applies `ProtectSystem=strict` before `ExecStart`, leaving the
top-level `/run` path read-only to the bridge. Because the unit did not declare
a writable runtime directory, its exclusive diagnostic-file creation would fail
with `EROFS` before either physical input was grabbed. The trial also rejected a
failed header before classifying the recorded write boundary, accepted any one
complete virtual key cycle instead of the full source count, and required only
one virtual axis sample for path localization. Partial virtual loss could
therefore be labelled `localization=none`.

V0.4 is **REJECTED BEFORE STAGING**. Do not transfer or stage the v0.4 archive
SHA-256 `e0656d83fc09f4c4ef5a4763c0e839ec7c30fb74eece72567245475006f1bf3b`.

## V0.5 corrected diagnostic candidate

V0.5 fixes only those review defects. The static service now declares
`RuntimeDirectory=r46h-input-bridge`, mode `0700`, and
`RuntimeDirectoryPreserve=yes`. Systemd creates that one writable exception
under `ProtectSystem=strict`; the bridge writes the root-owned mode-`0600`
`/run/r46h-input-bridge/diagnostics`, and the trial or guarded remover deletes
only the exact validated file and empty directory.

The 23-line format now records uinput write-failure count and the first failed
type/code/value in its header. Cleanup reports a failed header even when the
service exits before the normal comparison stage. Each key passes localization
only when press, release, repeat/other and final-value counts agree exactly from
source through successful uinput writes to the virtual capture. Each axis now
requires at least 70 percent source travel, exact source/write sample count and
final value, and corresponding virtual range, extrema and final value; one
virtual sample can no longer yield `localization=none`. SYN source/write report
counts must also agree.

The mapping, forwarding whitelist, v0.14 kernel, RetroArch config and physical
operator actions are unchanged. Focused parser, lifecycle and shell regressions
cover the new contract.

The clean source commit is
`624b267160d37cd46827f42d8c8b4d4c84ba275c`, tree
`934d72bb5a402dbe7a7b0fbaa79fb7a38867a0a2`. Generation
`build-624b267160d3-67090f7457f1` contains the 24,665-byte
`r46h-gaming-input-bridge-v0.5.tar.gz` with SHA-256
`67090f7457f19717e15f60e2d6c7bda83e6ae76322eaf97c5935b0f90ad94f14`.
Its 67,480-byte AArch64 bridge binary has SHA-256
`c8d2c9a1e0f875ad727bf37ae73ccbd76cfd4f7dd4c2ac538b906169ae91ee4e`;
the 13-file source manifest has SHA-256
`7d75676bc95b72081689daa0921110d42bbc4eefd5376f542e5018e657bdcada`.

The builder and an independent validation pass checked generation checksums,
deterministic archive structure, exact payload members and metadata, then
extracted the actual archive into an executable `/run` tmpfs in the pinned
AArch64 Linux image and passed `install.sh --check-payload`. A separate
source-manifest audit matched every size, mode and SHA-256 to the 13 exact Git
blobs and the recorded commit tree. Strict ARM64 compilation and GCC analyzer
completed. An isolated target-systemd-257 run then exercised the unit's exact
runtime-directory settings under `ProtectSystem=strict`: the writer succeeded,
the directory and file were `root:root` modes `0700` and `0600`, and the file
remained after service exit for trial-side parsing. This is host artifact proof
only, not a physical PASS.

The v0.5 archive retains the v0.3/v0.4 RetroArch config, candidate runner and
waiter SHA-256 values `e3092c469aa50b980b952f139c134ea5a6e9ec42646b29ef594fef4bc88a5545`,
`8f7f9a87576d2d670ce485959e897c68260995bf093317a672ea48a6e64c7012`
and `fa949b24a76e4341649ba9c3485cadaa8ec5c871a0ea9776cd8885c797f894ae`.

## V0.5 physical result: 2026-08-20

The reviewed v0.5 archive accepted exact persistent v0.10 and History v0.2,
then remained static and inactive until one exact v0.14 one-shot boot. The only
60-second trial reported:

```text
R46H_INPUT_BRIDGE_SYN_DROPPED result=pass count=0
R46H_INPUT_BRIDGE_COVERAGE keys=14/16 axes=4/4 centered=4/4 failures=2
R46H_INPUT_BRIDGE_TRIAL result=fail status=1 cleanup=check-required
```

Every exercised D-pad, face, shoulder/trigger, Select and Start key had exact
source/write/virtual press and release count agreement. All four axes passed
the new source/write/virtual geometry contract and returned centered:

```text
ABS_X   source 108..1008 final 514; virtual 111..1007 final 513
ABS_Y   source  69..926  final 507; virtual  69..920  final 502
ABS_RX  source  61..839  final 506; virtual  64..839  final 509
ABS_RY  source  72..927  final 526; virtual  78..924  final 527
```

The operator also saw D-pad, A and left-stick response on the smoke screen.
The only zero-source keys were `BTN_TRIGGER_HAPPY3` and
`BTN_TRIGGER_HAPPY4`. After the window, the operator explicitly reported that
both L3/R3 stick-cap clicks had been forgotten. The tool's
`localization=physical-source-missing` markers therefore record absent stimulus
in this run; they do not overturn earlier direct evidence that those physical
sources can emit events. V0.5 is **PHYSICAL INCOMPLETE**, not a complete PASS
and not a new L3/R3 hardware FAIL. Its at-most-once contract forbids an
unchanged retry. The separately reviewed targeted contract below subsequently
completed those two controls without repeating the full trial.

The trial left no bridge process, virtual gamepad, RetroArch process or runtime
directory. After controlled poweroff, ordinary exact v0.10 returned. The
guarded bridge and one-shot removers both passed; all candidate state and v0.14
modules were absent, History remained byte-exact, and final health plus
controlled poweroff passed. The detailed three-boot result and serial hashes
are in [`ATTENDED-INPUT-AUDIO-BATCH.md`](ATTENDED-INPUT-AUDIO-BATCH.md).

## Targeted L3/R3 completion v0.1

Status: **PHYSICAL PASS / COMPOSITE V0.5 CONTROLLER CONTRACT CLOSED /
CLEANLY REMOVED**

The incomplete v0.5 trial does not authorize another unchanged full trial.
The separately reviewed
[`r46h-input-bridge-l3r3-complete`](r46h-input-bridge-l3r3-complete) runner
changes the acceptance contract while reusing the exact v0.5 bridge only as an
instrument. It starts the same static service under exact v0.14, captures the
same combined virtual device, but asks for and accepts only L3 and R3. It does
not start RetroArch, retest the other 14 keys, move either stick through its
axis range or require another screen observation.

The runner SHA-256 is
`fbdca20ecf5eb758c064a88d4cc8410890ad552ba8820de85a0113847221c76f`.
It is a mode-`0755` tracked Bash file and must be installed as root-owned mode
`0700`, one regular link, at exact tmpfs path
`/run/r46h-input-bridge-l3r3-complete`. It pins exact v0.14, p2 PARTUUID,
v0.5 receipt/state/service hashes, a clean ext4/systemd preflight and an
attended TTY. Its only operator window is 20 seconds:

1. start with both stick caps released;
2. click and release the left stick cap once for L3;
3. click and release the right stick cap once for R3;
4. leave both released; no screen observation is required.

The runner stops the base frontend, starts the v0.5 bridge service, captures
the unique `R46H Combined Gamepad` without grabbing it and stops both capture
and bridge automatically. For `BTN_TRIGGER_HAPPY3` and
`BTN_TRIGGER_HAPPY4`, PASS requires at least one source press and release, a
released final value, exact source-to-uinput press/release/repeat/final count
agreement, exact uinput-to-virtual agreement and zero `SYN_DROPPED`. The
23-line v0.5 diagnostic header must also report no runtime or uinput write
failure. Cleanup must leave no bridge process, virtual controller, RetroArch
process, event file, diagnostic directory, ext4 error or failed unit.

The only accepted terminal boundary is:

```text
R46H_INPUT_BRIDGE_L3R3_COVERAGE controls=2/2
R46H_INPUT_BRIDGE_L3R3 id=r46h-input-bridge-l3r3-complete-v0.1 result=machine-pass status=0 controls=2/2 cleanup=pass operator_screen_observation=not-required
```

Any `physical-source-missing`, `bridge-write-missing` or
`virtual-delivery-or-capture-missing` localization is a terminal result for
this one targeted window, not permission to repeat it. A targeted PASS can be
combined only with the exact 2026-08-20 v0.5 evidence: 14 exercised keys, four
source/write/virtual axes, four centered returns, zero dropped events and the
D-pad/A/left-stick screen observations. That would close the v0.5 controller
contract by composite evidence; it must not be described as one simultaneous
16-key trial.

The only targeted run on 2026-08-21 produced exactly that PASS. Both controls
had one source press and release, one emitted press and release, one virtual
press and release, zero other events and released final state:

```text
R46H_INPUT_BRIDGE_L3R3_SYN_DROPPED result=pass count=0
R46H_INPUT_BRIDGE_L3R3_COVERAGE controls=2/2
R46H_INPUT_BRIDGE_L3R3 id=r46h-input-bridge-l3r3-complete-v0.1 result=machine-pass status=0 controls=2/2 cleanup=pass operator_screen_observation=not-required
R46H_INPUT_BRIDGE_L3R3_COMMAND status=0
```

Exact v0.14 identity, p2 health and cleanup passed before controlled poweroff.
The exact v0.10 return then removed both candidates and all task staging while
preserving History/config and clean health. The 63,349-byte serial receipt is
`mainline/out/r46h-serial-logs/attended-input-audio-completion-v014-l3r3-20260821T131933Z.bin`,
SHA-256 `d924b1ab2063eb8a10c2464d46cc78015fc74b301b06b0da6551f47d6f5c53a1`.
This closes all 16 identified keys only when composed with the exact v0.5
14-key/four-axis/three-screen evidence; it is not a simultaneous 16-key run.

Before the physical batch, validate the syntax and pinned host contract:

```bash
/bin/bash -n mainline/bringup-tests/r46h-input-bridge-l3r3-complete
PYTHONDONTWRITEBYTECODE=1 python3 -B \
  mainline/tests/test-r46h-input-bridge-l3r3-complete.py -v
/usr/bin/shasum -a 256 \
  mainline/bringup-tests/r46h-input-bridge-l3r3-complete
```

During exact v0.14, install only the already rehashed incoming copy to tmpfs,
rehash it again, execute it once, preserve the complete terminal output, then
remove only that tmpfs copy:

```bash
sudo test ! -e /run/r46h-input-bridge-l3r3-complete
sudo install -o root -g root -m 0700 \
  /home/ark/.cache/r46h-input-audio-completion-v1/r46h-input-bridge-l3r3-complete \
  /run/r46h-input-bridge-l3r3-complete
printf '%s  %s\n' \
  'fbdca20ecf5eb758c064a88d4cc8410890ad552ba8820de85a0113847221c76f' \
  /run/r46h-input-bridge-l3r3-complete | sudo sha256sum -c -
sudo /run/r46h-input-bridge-l3r3-complete
l3r3_status=$?
printf 'R46H_INPUT_BRIDGE_L3R3_COMMAND status=%d\n' "$l3r3_status"
sudo rm -f /run/r46h-input-bridge-l3r3-complete
```

Require command status zero as well as the terminal PASS. Health-check and
power off; do not restart the frontend because the next ordinary exact v0.10
boot performs guarded candidate removal. The full four-boot order is
[`ATTENDED-INPUT-AUDIO-COMPLETION.md`](ATTENDED-INPUT-AUDIO-COMPLETION.md).

## Reviewed physical contract

The following preserves the safety boundary used by the completed single v0.5
trial. It no longer authorizes another v0.5 run or a retry of an unchanged older
candidate:

Device staging was an attended-batch mutation, not a host-only proof.

1. Rediscover the CH340 identity. For a cold power-on, capture at 1,500,000
   baud before applying power and switch to 115,200 only after the visible
   `I/TC: OP-TEE version` marker.
2. Let active BOOT start exact persistent v0.10. Confirm the root PARTUUID,
   writable ext4, zero ext4 error count, no failed units and stable Wi-Fi.
3. Transfer and rehash the exact bridge and p2 one-shot archives over Wi-Fi.
   Extract each as root into its exact `/run/<payload-id>` directory, run the
   one-shot installer and then the bridge installer, and remove only the
   verified transfer/extraction staging. Both candidates must remain inactive;
   p1 and active BOOT must be byte-unchanged.
4. Run `sync` and a controlled poweroff. Reopen cold serial as in step 1,
   interrupt autoboot once and use the exact `UBOOT-CMDS.txt` from the accepted
   one-shot archive. Never use `saveenv`.
5. After exact v0.14 reaches multi-user, verify the kernel, p2 root, matching
   module directory, ext4 error count and failed-unit preflight. Start with all
   game buttons released and both sticks centered, then run
   `/usr/local/sbin/r46h-input-bridge-trial` from an attended TTY.
6. During its single 60-second window, visibly confirm D-pad, A and the left
   stick affect the hardware smoke screen. Press and release A/B/X/Y, L1/R1,
   L2/R2, Select, Start, L3/R3 and all four D-pad directions. Move both sticks
   through every edge and corner, circle them, then release them centered. Do
   not press Power, Reset, either volume control or the unidentified F5 GPIO.
7. Let the trial exit automatically. Its non-grabbing virtual-device capture
   must report the exact `R46H Combined Gamepad`, all 16 identified game keys
   with complete source/write/virtual count agreement, at least 70 percent of
   every source and virtual advertised axis range, matching source/write final
   values, corresponding source/virtual extrema, all axes returned within 10
   percent of their starting neutral values and zero `SYN_DROPPED` events.
   Cleanup must leave no virtual device, RetroArch or bridge process. Check
   ext4, failed units and new kernel fault matches, then `sync` and power off.
8. Perform one ordinary v0.10 boot, remove the bridge candidate first and the
   v0.14 one-shot/module staging second with their installed guarded removers,
   recheck health, and power off. Do not leave a host-only candidate active.

Machine PASS requires the exact kernel/root/module identities, complete virtual
key/axis coverage, a clean bridge start/stop, no stuck input, no new ext4 error
and no failed unit or relevant kernel fault. Physical PASS additionally requires
the operator to observe the smoke-screen D-pad/A/left-stick response, which also
proves the configured Pad #1 RetroArch path because both physical sources are
grabbed during the trial. A wrong release, serial loss, filesystem error,
persistent process, abnormal temperature or unexpected power behavior ends the
batch and returns to the unchanged ordinary v0.10 boot; it is not a prompt to
reset or repeat the trial.

Charging, headphone, KMS and suspend observations remain outside this input
gate. [`ATTENDED-GAMING-BATCH.md`](ATTENDED-GAMING-BATCH.md) records the
completed cross-gate session: headphone work was deferred and history passed.
The completed v0.3 retry and headphone gates are recorded in
[`ATTENDED-GAMING-RETRY.md`](ATTENDED-GAMING-RETRY.md); no v0.1 through v0.5
archive authorizes an unchanged rerun. The only prepared next use is the
L3/R3-only runner above, within
[`ATTENDED-INPUT-AUDIO-COMPLETION.md`](ATTENDED-INPUT-AUDIO-COMPLETION.md).
The completed full-trial execution order with the independent headphone
localizer remains frozen in
[`ATTENDED-INPUT-AUDIO-BATCH.md`](ATTENDED-INPUT-AUDIO-BATCH.md).
