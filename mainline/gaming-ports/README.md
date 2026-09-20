# Original ports and PortMaster integration

Status 2026-09-19: **R74 VICE CITY SHORT ATTENDED PASS / BROADER PLAY OPEN**.
The [roadmap](../../docs/PRODUCT-ROADMAP.md) owns ordering. The guarded profile
executed the fixed-hash GTA III engine, never the original launcher script; original
game data stayed read-only and the managed save directory stayed empty.

## Original-card data

The retained source is `mainline/out/.cache/r46h-original-card-import-20260826/easyroms`.
A read-only SHA-256 inventory of every regular file in the four game directories,
plus launchers, Mono runtime and Metal Slug ROM/BIOS is in
`mainline/out/.cache/r46h-ports-source-20260910/inventory.json`.
It proves this source snapshot, not vendor authenticity/version or target equality.

| Original directory under ports/ | Files / MiB | Relevant inputs |
| --- | --- | --- |
| stardewvalley1615 | 3631 / 570.3 | Managed Stardew Valley.exe, SVLoader.exe, patches, gamedata/Content and savedata/Saves |
| gta3 | 439 / 439.3 | AArch64 re3/re3_gl, classic game data, configuration; userfiles currently empty |
| gtavc | 2384 / 2678.1 | AArch64 reVC/reVC_gl, classic game data, Chinese/mod files and an existing userfiles save |
| gtasa_zh | 458 / 2551.8 | AArch64 gtasa and libGTASA.so, assets, translation/archive files and loose save files |

The Mono squashfs exists under `tools/PortMaster/libs/`. The Metal Slug ROM and
Neo Geo BIOS hashes match the [accepted FBNeo inputs](../gaming-ozone-fbneo/README.md).
These directories were within the earlier [p3 import](../../docs/P3-CONTENT-MIGRATION.md)
scope, but full target readback was skipped. Verify the matching target paths
before copying; avoid a second full copy of roughly 6 GiB when assets are already there.
Original save files must survive import, failed launch, update and removal.

The Stardew metadata names stardewvalley/StardewValley.sh while the original
folder/launcher are named with 1615; its saved status says Broken. This is a
metadata/path discrepancy, not proof that the game itself fails. Metadata inspection now reports assembly `1.6.15.24356` and `.NETFramework 4 Client`;
this identifies the local compatibility assembly, not vendor authenticity.

## Upstream findings

The official [compatibility port](https://github.com/PortsMaster/PortMaster-New/blob/main/ports/stardewvalley/port.json)
requires the Steam/GOG compatibility data and Mono 6.12.0.122 AArch64. Prefer this
route for the found data. The separate [mainline port](https://github.com/PortsMaster/PortMaster-New/blob/main/ports/stardewvalleymainline/port.json)
requires regular Windows Steam data and is marked experimental; its loader/mod
and memory behavior need a separate comparison, not a blind replacement.
[Stardew's compatibility guide](https://www.stardewvalley.net/compatibility/).

The checked default PortMaster-New ports tree contains both Stardew variants but
no gta3/gtavc/gtasa entries. The local GTA manifests identify classic PC assets for
III/VC and include an additional-source record. Do not assume a current default
catalog download exists; preserve the found packages while checking provenance,
engine/library closure and available upstream maintenance. SA is a separate package.

[HarbourMaster](https://portmaster.games/harbourmaster.html) already owns catalog,
install/remove and runtime management. Reuse that backend behind a small Qt
adapter after one local game works. PortMaster's [repository policy](https://github.com/PortsMaster/PortMaster-New)
keeps port-specific libraries separate from OS libraries; retain that boundary.
Do not put commercial assets, private pairing data or user saves in Git.

## Runtime audit and management

The separate [Qt tool page](../gaming-shell/TOOLS.md) keeps the four original games
and their save-copy/backup operations. The current working tree also adds a real
HarbourMaster catalog, search/installed filter, package install/update/rollback/
uninstall and dependency runtimes. These additions are packaged in the host-checked R19 candidate. Installed catalog packages do not execute their legacy launch scripts;
actual game launching still requires an adapted profile.

Read-only ELF inspection is retained in
`mainline/out/.cache/r46h-ports-source-20260910/elf-dependencies.json`:

| Binary | Required runtime boundary |
| --- | --- |
| re3 / reVC | SDL2, OpenAL, libOpenGL, mpg123; maximum referenced GLIBC 2.29 / GLIBCXX 3.4.22 |
| re3_gl / reVC_gl | GLFW and X11 in addition to audio/C++ libraries; not an assumed EGLFS path |
| gtasa | SDL2, OpenAL, EGL/GLESv2, zlib and libbsd; custom Android loader and direct evdev input |
| libGTASA.so | Android-named libraries including libandroid, liblog, OpenSLES and libSCAnd; requires the package's compatibility loader |

No original script was run. Match these dependencies on the R46H first;
do not replace Mesa/Panfrost with vendor libraries or assume an existing filename
proves a working dependency closure. The original Mono archive was subsequently extracted only inside an isolated
container: it reports Mono 6.12.0.122, arm64. It was not installed on the device. Original GTASA loose saves and Vice City userfiles are included in
the managed-copy path; source SHA inventory remains unchanged.

The 2026-09-11 SA follow-up is retained in
`mainline/out/.cache/r46h-ports-source-20260910/gtasa-audit/receipt.json` with focused
ELF/disassembly evidence. All 458 original files still match the earlier inventory.
The loader and Android libraries are ELF64/AArch64; the Linux loader's highest
referenced GLIBC version is 2.29. Its `sdl_gamepad_sample` actually calls `evdev_poll`
and reads the wrapper's button/axis state. `patch_game` opens input event nodes
and attempts EVIOCGRAB. SDL controller mappings/ignore lists therefore do not
establish this game's input isolation or layout. A future adapter must restrict
visible inputs to the routed controller and verify the loader's own button table.

The translation archive differs from its original backup in `Text/japanese.gxt`
and two Japanese font files; all three match the current `assets/` files. This
proves patch placement, not the selected language or rendered Chinese. The loader's
configuration, loose saves, `savegames/`, auxiliary state and logs need private
writable paths; retain originals. Existing `gtasa.log`/`log.txt` are original-card
history, not current R46H runtime proof. The legacy launcher also writes governors,
forces graphics settings and invokes distro helpers; it was not executed.

The exact upstream source/revision for this binary remains unidentified. A
[related patch author's report](https://github.com/erfan2255/gtasa-portmaster-dpad)
also describes direct evdev, but does not identify this binary. The separate
[Switch wrapper](https://github.com/NaGaa95/gtasa_nx/blob/main/README.md) expects
2.11.311 `libGame.so`; it is not an established replacement for the found package.
SA launch stays disabled until loader, writable paths and routed-input adaptation
have their own bounded runtime checks.

## Private HarbourMaster backend

`backend-lock.json` pins upstream commit `0009bb08d33252d9e0b1813c3c481a3017fc7a01`
and the required Python wheels by SHA-256. The adapter reuses upstream catalog,
package inspection/installation and runtime download APIs. It suppresses bulk
image downloads, distro hooks, global permission changes and original-ROM scans.
Requests uses a private session with `trust_env=False`: host `.netrc`, proxy
credentials and environment authentication are not consulted. The backend also
binds `HOME` to its private state before importing HarbourMaster, so upstream
platform probes cannot read the launching account's home. Python 3.10+ is required.
R31 bundles Debian's [Python 3.13 interpreter and standard library](https://packages.debian.org/trixie/python3.13-minimal),
pinned in `prepare-native.py` with official package-index sizes/SHA-256. They
live at `usr/bin/python3.13` and `usr/lib/python3.13`, without a system install.
Both catalog and native-port workers use this interpreter with `-I -B`; a missing
packaged interpreter fails closed. Unpackaged development retains system Python.
`test-port-python.py` verifies imports, TLS validation and paths inside the bundle;
the packaged catalog check removes system Python from PATH. Target preflight also
imports the required extensions as `ark`. R36's direct refresh and Qt catalog passed
on R46H; native-port launch remains a separate gate.

Installation distinguishes an unpublished index failure from a failure to sync
its directory after replacement. The latter reports uncertain durable storage
and retains the published generation, its runtimes and the prior version; it
must not delete files referenced by the visible index. A verified runtime download
replaces a corrupt cached file or link; intact verified caches are reused.

```sh
python3 -B mainline/gaming-ports/prepare-backend.py "$PWD/mainline/out/.cache/r46h-portmaster"
python3 -B mainline/gaming-ports/manager.py \
  --runtime "$PWD/mainline/out/.cache/r46h-portmaster/runtime" \
  --state "$PWD/mainline/out/.cache/r46h-portmaster-test" refresh
```

The Qt builder accepts `R46H_PORTMASTER_BUNDLE` for a separately named prepared
archive; the neighboring SHA receipt and source lock must match. The packaged
adapter/runtime live under `usr/share/r46h/`. Native development can point
`--portmaster-backend` and `--portmaster-runtime` at those private files.

In the local PortMaster page, X opens the catalog. In the catalog, X searches,
Y switches installed/all, START refreshes and L1/R1 page through 50 entries.
A opens details; install/update, rollback and uninstall use the shared confirmation
popup with Cancel selected first. B cancels work or returns. Installation
instructions use a scrollable, plain-text popup. Metadata compatibility is a
filter against the known target profile, not proof that a game runs.

Downloads and extraction use fresh transactions, with 512 MiB compressed,
2 GiB expanded, 50,000-file and 64 MiB free-space reserve limits. Traversal,
links/device entries and duplicate paths are rejected. Only after successful
installation/runtime checks does an atomic index select the new generation;
one previous version remains available. Saves stay outside package generations.
Runtime downloads are verified again after the upstream result, reused by content
hash and removed when neither current nor previous packages reference them.
Only the fixed official catalog is loaded; self-updating PortMaster, themes and
arbitrary custom repositories are outside this adapter.

The live official catalog returned 1,396 entries; Wordle SDL downloaded and
installed successfully in a disposable host state. Its launcher was never run.
R36 also refreshed the same 1,396 records on R46H and displayed them with the four
local projects; no target package mutation or launcher execution occurred.
`test-portmaster-manager.py` covers updates/rollback, bad ZIPs, cancellation,
failed index writes, failed/mismatched runtime downloads, reuse/cleanup and save
preservation. `test-portmaster-ui.py` drives the actual Qt/backend pair, including
120% fonts, modal isolation, installed filtering, instructions and private-editor
refusal. Evidence is under `mainline/out/.cache/r46h-ports-backend-20260910/`.

The frozen R19 package/source/receipt are in that evidence directory; the newer
R20 native-launch package/source/receipt are separately retained in its `r20/`
subdirectory. R20 also includes the v4 Moonlight combined package; it has no
device acceptance. The
assembled backend archive is byte-identical across two cached repacks; this does
not claim a reproducible Qt ELF build. Temporary Mono extraction is retained at
`mono-audit/runtime` only for ongoing Stardew adapter work; remove it after the
adapter's replacement runtime/test evidence is verified.

## Stardew adapter input

`mono-audit/metadata/` contains metadata-only inspection of the local assembly
and `SVLoader.exe` IL. The loader accepts `<assembly> [appBasePath] [-- appArgs...]`,
sets its working directory/AppDomain base to that optional path, and redirects
XNA assembly names to MonoGame. The original `gamedata` already lacks the obsolete
System/MonoGame duplicates removed by the legacy script. The adapter uses a
private working directory and existing `MONO_PATH`/patch inputs without moving
or deleting original DLLs. It reaches the title/menu and writes `startup_preferences` through
that private save path. Original files remain read-only. The original Mono exports
LLVM 6 symbols which collide with Mesa 25/LLVM 19 when graphics providers load;
the private `mono-compat.c` shim deep-binds Mesa GLX/EGL/GBM and `*_dri.so`
provider groups. Baseline native crash and corrected host-menu evidence are
retained. No system graphics library was replaced.

The game's own `GameRunner` exit handler calls `Process.Kill` after notifying game
instances. The shim reports that deliberate self-exit separately from a supervisor
kill; the host check observed the marker, no forced kill and private settings
readback. `test-mono-compat.py` additionally checks real ELF symbol resolution,
unrelated-library behavior, and intentional versus external SIGKILL. This does not
prove a farm save/load cycle or physical speaker/controller behavior.

The dedicated host Xvfb had no window manager and left the initial SDL window at
1280×720. The host harness records that geometry, resizes only that test window to
1024×768 and captures the complete menu. This is a test-environment correction,
not a guessed permanent game setting. `probe-host.py` uses init and an outer
container deadline; putting `xvfb-run` at PID 1 previously stalled its startup handshake.

## GTA SDL2 profile preparation

`local_port.py` verifies the exact original re3/reVC engines and uses a disposable
working directory with read-only resource links, managed configuration and a
separate `userfiles` save directory. The referenced SDL2 source implements that
relative save location; source references and engine hashes remain in the host
record. The old GL dispatch libraries and Windows launchers are not loaded.

Both original engines reached `GS_FRONTEND`, initialized OpenGL ES 3.2 on Mesa
25.0.7 software rendering and exited 0 on the 20-second bounded stop in an
AArch64 container. The missing SDL2 dynamic library was supplied by Debian's
2.32.4 runtime; the builder's static SDK alone was insufficient. This proves
frontend startup and controlled exit, not gameplay, physical input/audio,
Panfrost performance or save/load. Original content was mounted read-only.
The helper's `--host-test` requires that isolated container/read-only mount;
its prepared-directory function is now connected to the guarded ports supervisor.
R36's first target launch exposed one missing inherited path: the private process
found the port audio libraries but not the package's existing `libOpenGL.so.0`.
R37 explicitly admits both verified package-library directories. The target then
reached SDL context creation but stopped at `gladLoadGLLoader`: its profile loop
treated a Wayland window as proof that an unavailable desktop GL context worked.
R38's process-local adapter loaded, but SDL did not read back the pending profile
before context creation. R39 records the application's `SDL_GL_SetAttribute`
request directly and rejects only core-profile window attempts. It again passed
the actual-engine AArch64 host check on software GLES 3.2, but the R46H target's
Panfrost GLES 3.1 path still ended at the same `gladLoadGLLoader` error before a
fresh frame. This narrows the blocker to the engine/target GL capability boundary;
do not add another profile shim or repeat the shared session without a new hypothesis.
The initial managed INI copy is published only after a flushed complete write,
without replacing an existing copy. This later working-tree fix has an interrupted
copy/retry check; it is newer than the frozen R20 package.

## Migration gates

1. Inspect executable architecture, ELF dependencies, loader/data versions and
   required runtimes without executing the original scripts. Keep hashed originals.
2. Build a per-game launcher using the current combined controller and accepted
   audio route. The old scripts change HOME, chmod device nodes globally, restart
   oga_events, kill all gptokeyb processes, change governors or delete/move data.
   Those actions do not belong in the new launcher.
3. Keep assets read-only and allocate separate writable saves/config/logs. Only
   games that require resource patching get a working copy; back up existing saves
   before import. Old uppercase paths and Windows-only mods need explicit review.
4. Validate dependency loading and a bounded start/exit/restart on the selected
   display path. Add a desktop/library entry with stable ID, cover and last-played
   state. Uninstall removes managed code without silently removing user data.
5. Attended gates per title: Chinese/text, sticks/buttons, picture/audio, save/load
   and returning to the desktop. Metadata discovery and host parsing do not prove playability.

Metal Slug is the first local game integration: reuse the accepted core/options
and data, but use a current lifecycle wrapper. Do not replay the historical
p2-v0.7-bound Ozone installer on the current p2-v0.17 card. Save-state menu/core-info
issues remain separately tracked until verified with this core.

## Shared-display host integration

`local_port.py --host-test --shared-display` uses Wayland and keeps the engine in
the desktop's foreground process group. It requires the routed-controller identity
and refuses the X11-only input helper. TERM/INT request a bounded graceful stop,
then finalize logs and remove the disposable working directory. Shared children
get a one-second inner grace period before the desktop's 1.5-second group ceiling;
direct-display children retain their separate process group and five-second grace.
This is process cleanup, not a promise that a game saves progress automatically.

`gaming-wayland/check-ports.sh` runs the hash-pinned source-built re3/reVC and
Mono/Stardew engines with the Qt desktop, headless Mesa GL and read-only original assets.
`mainline/out/.cache/r46h-compositor-20260910/ports/` holds the captured frontends,
routed-only input descriptors, global panels and completion records. GTA III/VC
menus move from Start Game to Options; Stardew's title screen accepts controller
input and selects Load. All three return to the same desktop session and remove
their working directories. Stardew still uses the identified deliberate self-exit
marker; no forced-timeout success is inferred.

The check exposed an input gap hidden by the old synthetic game: SDL rejects
background controller events by default. The common launcher now sets that hint
for routed sessions, and the test game no longer supplies its own workaround.
Broker ownership/neutral gating still controls delivery. These results establish
host menu input and lifecycle only; gameplay, real audio, saves and target timing
remain open. The target session candidate below supplies persistent state and
the guarded Mono lease; its physical mount/launch/retention gate remains open.

## Shared target session candidate

For the newer complete handheld package, opt into the same fixed persistent
directory already used by the direct-display preview:

```sh
R46H_SHELL_STATE_DIR=/home/ark/.local/share/r46h-preview \
  /run/r46h-wayland-probe/probe-r46h.sh --check MANIFEST_SHA256 handheld
R46H_SHELL_STATE_DIR=/home/ark/.local/share/r46h-preview \
  /run/r46h-wayland-probe/probe-r46h.sh --run MANIFEST_SHA256 handheld
```

Use the exact new manifest after the existing identity/space/serial preparation.
Other persistent paths and ordinary two-window mode are refused. The private
directory is checked as `ark`; `/run` session output remains disposable. When
the package includes the native port helper, the supervisor acquires Mono before
starting the compositor and supplies `R46H_SHARED_PORTS=1`. Without that capability
or persistent storage, the shared UI leaves port launch disabled.

The same fixed-image lease accepts the shell or Wayland unit and selects that
unit's fixed staging directory. Unit and mount-ID checks prevent releasing
another session's mount. Cgroup stop precedes release and ES-DE recovery; failed
release keeps the frontend stopped. The native worker retains device/UID/cgroup,
read-only original content and hash checks, then passes the shared profile to
the existing Python runner. Completion refreshes the port page's save counts.

`install-runtime.sh` assembles the common PortMaster backend, native helper,
private audio libraries and Mono shim for both package builders. It runs only
inside the isolated SDK staging area. No game assets or Mono image are embedded;
the original verified Mono image is mounted read-only on the target. Packaged
unprivileged session checks cover the explicit state location surviving compositor
failure. Fake-mount checks cover both unit families and release refusal; actual
mounting, persistent gameplay saves and power-cycle retention remain unverified.

Use the current [R78 shared candidate](../gaming-wayland/HANDHELD.md#resume-and-rebuild).
It retains private Python for the v0.17 base, binds HarbourMaster's HOME to
private state and pins the accepted native-game runtimes. R36's direct refresh
and 1,396-entry Qt catalog passed on R46H;
package mutation, gameplay and save/load remain open. R39 is a retained diagnostic,
not a promoted shared candidate: GTA III's guarded runtime path ran on-device but
failed at the target GL loader before gameplay. The C++
Neo worker's result does not validate those paths. R29 and earlier archives
remain historical evidence, not the next deployment recommendation.

R24 is frozen at `mainline/out/.cache/r46h-compositor-20260910/r24/receipt.json`,
source `091b796cb28c6d046cf0bd3076e667847e78fe1c` on
`codex/r46h-shared-ports-r24-candidate`. Its 33,647,407-byte archive expands to
92,864,150 regular-file bytes. Full readback, packaged unprivileged sessions,
explicit state retention, the common backend/shim checks and all three frozen-source
Wayland frontend checks passed. Device mounting, native worker and gameplay remain open.

## Native ports session candidate

The shell's `--ports` / `--remote-ports` probe modes open the local PortMaster page
with native handoff enabled. They require the opt-in persistent state directory;
GTA III, Vice City and Stardew start through fixed hash-bound profiles. The UI exits
before KMS use and a fresh process restores the correct tool/game selection after
normal, failed or bounded exit. San Andreas remains disabled pending adaptation.

R40 freezes this existing direct path at
`mainline/out/.cache/r46h-direct-gta-20260913/r40/receipt.json`, using the same
R39 source and target libraries. Its ARM64 package tests, direct supervisor recovery
check and independent 1,629-file host/target readbacks passed. The fixed R46H then
ran GTA III through `--remote-ports`; it exited -11 after 1.46 seconds at the same
`gladLoadGLLoader` boundary as shared Wayland, before `GS_FRONTEND` or a game frame.
The direct-path hypothesis is rejected. Evidence is
`mainline/out/.cache/r46h-r40-direct-device-20260913.mAey9k/session.json`; do not
add another shim or rerun this binary.

R41 reused those exact 1,629 verified files for the two independent targets in one
device session. Stardew's fixed Mono squashfs mounted read-only and execution reached
`StardewValley.Program.Main`, but Mono's native stack failed through
`SDL_CreateWindow` and `gbm_create_device` after 10.44 seconds (supervisor exit -6).
Vice City's fixed reVC failed after 1.12 seconds at the same librw
`gladLoadGLLoader` source line as GTA III (exit -11). Neither reached a game frame.
The UI recovered after each failure; source saves remained 3/1 files and both managed
save trees remained empty. Evidence is
`mainline/out/.cache/r46h-r40-ports-batch-device-20260913.XEe7qy/session.json`.

`runtime-lease.sh` mounts only the hash-verified original gzip Mono squashfs read-only
at the temporary payload's `mono` directory. Root-only records bind it to the
current unit and mount ID; release refuses another unit or a replaced mount. The
supervisor stops the entire process group before release and frontend restoration.
R41 passed actual read-only squashfs acquisition, guarded release and loop detach on
the accepted kernel; this proves lifecycle only, not Stardew graphics or gameplay.
`prepare-native.py` supplies only pinned Debian OpenAL/mpg123 libraries in a private
port library directory; it does not replace Mesa, libc or the system SDL2.

## R42 source-built GTA candidate

R42 retires the fixed original GTA executables from execution while retaining their
hashes as source-card identity checks. `prepare-gta-source.py` pins re3
`ead2747`, reVC `b9f0b23`, shared librw `81c9426` and two Debian ARM64 build-header
packages. `librw-context-fallback.patch` creates and loads GL inside the existing
profile loop, so a failed context/GLAD attempt releases its window and advances to
the next GLES profile. `build-gta-source.sh INPUT_CACHE NEW_OUTPUT` runs offline,
uses `LIBRW_FORCE_GLES`, and produced byte-identical re3/reVC pairs in independent
builds. The old `LD_PRELOAD` GTA profile shim is no longer packaged.

The package source is `e6c830904cd4087b440fa68b108cf2771de5cd2d`; the verified
fresh-download/path follow-up is `3b12c775d0b83f9d0da931afa6612d9f0653cf86`.
Receipt-bound output is `mainline/out/.cache/r46h-source-gta-20260913/r42/`. Its source-built GTA III
and Vice City each reached a captured real menu, accepted one host input and exited
at 20 seconds on ARM64 software GLES 3.2 with original assets read-only. The full
1,630-file shell package and lifecycle checks passed.

The same candidate adds `libgbm.so.1` to Stardew's existing Mono/Mesa deep-binding
set because R41's direct KMSDRM stack entered GBM without the earlier GLX/EGL marker.
The focused ELF collision test passed, but the R42 target run rejected the diagnosis:
Stardew still crashed after 10.46 seconds through `SDL_CreateWindow` and
`gbm_create_device`. Do not repeat it without a new source-level hypothesis.

The fixed R46H repeated all 1,630 package hashes. Source GTA III/re3 and Vice
City/reVC then used Panfrost OpenGL ES 3.1, reached `GS_FRONTEND`, ran for their
full 120-second bounds and returned to fresh PortMaster UIs. Original content
and source saves stayed read-only; source saves remained 3/0/1 files and all
managed save trees remained empty. The logs warn that `gamecontrollerdb.txt` is
absent, but the fixed SDL mapping has not yet had its attended check. Gameplay,
LCD motion, audible output, physical controls, save/exit/relaunch and a fresh
game-frame capture remain open. Evidence is
`mainline/out/.cache/r46h-r42-ports-device-20260913.GdcAbV/session.json`.

Post-R42 ELF inspection found 9,534 LLVM 6.1 symbols in the 2022 Mono executable's
dynamic exports while Debian 13 Mesa loads LLVM 19. R42 logged no GBM isolation
marker before the crash, so wrapping `libgbm.so.1` did not reach the actual provider
load. The minimal follow-up also matches `*_dri.so`; its ARM64 collision fixture now
covers GLX, EGL, GBM and Panfrost DRI.

## R43 Stardew DRI candidate

R43 freezes that single hypothesis from clean JumeOS source
`9ddb045d0eaa780e7258a6c0f83410a2b97e69c4`. The exact package is
`mainline/out/.cache/r46h-stardew-dri-20260913/r43/r46h-shell-preview-arm64.tar.gz`,
38,143,655 bytes, SHA-256
`fd123d671f5af9a2ed653cc301cd59e6f3c7f38bfca826afd8192bdf26d9a70a`.
Its 1,630 regular files rehashed after independent extraction. The packaged
`libmono-compat.so` has SHA-256
`ca7713e44936c791b4daf350f16d0ebd6272a881dd7035484c247fa459f5a018`
and passed the ARM64 GLX/EGL/GBM/Panfrost DRI collision fixture from the frozen
archive. Two package builds produced that same shim and file set; only the Qt
`r46h-shell` binary differed, so the complete shell build is not byte-reproducible
and only the exact archive above is the candidate. The adjacent receipt, source
archive and file manifest own the full host boundary.

The fixed R46H repeated all 1,630 hashes, but R43 still crashed through the same
`SDL_CreateWindow` / `gbm_create_device` path after 10.31 seconds and emitted no
scope marker. Target inspection then showed `panfrost_dri.so` is only a symlink
to the small `libdril_dri.so`; the real LLVM 19 consumer is
`libgallium-25.0.7-2+deb13u1.so`. Matching that basename in R44 still emitted no
marker and failed after 10.48 seconds because `libgbm` called glibc's loader
without passing through the preload wrapper. Both hypotheses are retired.

## R45 Stardew Gallium preload

R45 directly preloads the fixed Debian 13 Gallium provider with
`RTLD_DEEPBIND` during shim initialization. The focused ARM64 fixture covers
that constructor path. A target differential probe used the fully read-back R43
package with only the shim replaced by SHA-256
`28164fe9af77f8b02e6f7caef18e48c5de146ac5351fb28a1d63fb60f140354e`.
Stardew stayed alive past the old crash, mapped the shim, Gallium 25, LLVM 19 and
GBM, then completed the 120.7-second bound with deliberate self-exit and no
forced kill. Three provider-scope markers were retained, source saves stayed at
three files on read-only `/roms`, one startup file appeared only in the managed
save tree, and the tools UI recovered. The 85 C guard peaked at 68.846 C.

The clean package from source `d45ede16f3be21cbf2f15e79d7bbbcd750440b22`
is `mainline/out/.cache/r46h-stardew-gallium-20260913/r45/r46h-shell-preview-arm64.tar.gz`,
38,143,915 bytes, SHA-256
`0ff856a9df1cf0b86c5b7393b3c75750a04da014cfe13488638be66164591f08`.
The target repeated all 1,630 hashes and the same result for 120.6 seconds. ES-DE,
1296/480 MHz limits, services and mounts recovered; failed units, temporary
listeners and matched kernel errors were zero. Sync, unmount, loop detach and
poweroff were serial-confirmed. The adjacent receipt and
`mainline/out/.cache/r46h-r43-device-20260913.YmFUAM/session.json` own the full
boundary.

Target automation accepts the loader fix. LCD motion, audio, physical controls,
gameplay and save/reload remain operator-open.

## R46/R47 attended ports preparation

The existing native worker already supports a 35-minute operator-present bound.
`probe-r46h.sh --attended-ports SHELL_SHA256` now exposes it through the same
fixed identity, read-only ROM, Mono lease, cgroup, mixer and ES-DE recovery
guards; the outer session remains limited to 90 minutes.

Stardew's first successful start created only `startup_preferences` in its
managed save directory. Import now accepts that exact initialized state (or an
empty directory), publishes the original `Saves` subtree without replacing the
preference, and refuses every other existing entry. The ARM64 C++ fixture and a
read-only run against the retained two-file farm save passed; a second import was
refused and source/copy hashes remained equal. The exact package from source
`882ea1d298db0c6eeb1fa45356d3596ed87df78a` is
`mainline/out/.cache/r46h-attended-ports-20260913/r46/r46h-shell-preview-arm64.tar.gz`,
38,146,119 bytes, SHA-256
`c5e30a853d7aba1a60ee6c0604abbeb3af66dd0314bbf89a856f8a192f7b2305`.
Its 1,630 regular files rehashed after independent extraction; only the Shell
and probe differ from R45. The adjacent receipt owns the host boundary.

A clean target repeated all R46 hashes, then exposed a probe-only defect before
the UI: root-protected fresh `/run` staging lacked the private `state/` log
directory. After explicit `ark:0700` preparation, the 1,800-second attended UI
bound returned status 0 and recovered ES-DE, but received no operator input.
R47 fixes that shared Ports guard at source `da0b2febfd0f8d8c7ccf8b2cec70be6d8ad34f66`:
it refuses a linked or wrongly owned state and creates the absent directory
before launch. Its exact package is
`mainline/out/.cache/r46h-attended-ports-20260913/r47/r46h-shell-preview-arm64.tar.gz`,
38,146,124 bytes, SHA-256
`6db8ded1f6814252b6f8ba645ca832d0169826c4f76ad6b6a477827adda0e287`.
All 1,630 files rehashed on target; `--check` left state absent, `--ports`
created `ark:0700` state, completed the 290-second UI bound and restored the
frontend/mixer. Original save hashes and the sole managed `startup_preferences`
file were unchanged. Both capped UI runs peaked at 67.692 C without a thermal
abort; frequency limits, services and storage recovered, temporary scope/key
were removed, and serial confirmed controlled poweroff. The adjacent R47 receipt
and `mainline/out/.cache/r46h-r46-attended-device-20260913.Z7skfu/session.json`
own exact evidence. Device import, LCD/audio/physical controls, gameplay,
save/exit/relaunch and GTA attended checks remain open.

## R48 GTA media and D-pad repair candidate

The R47 attended GTA III run reached `GS_INIT_PLAYING_GAME`, then asserted in
`CdStreamAddImage`. Target `strace` proved that the case-correct
`./models/gta3.img` exists but its `O_NOATIME` open fails with `EPERM` for the
unprivileged game user on the read-only exFAT content mount. The same run's
operator reported that D-pad Down required many presses. A non-grabbing evdev
sample then showed the combined pad's idle `ABS_Y` around 501--506 against a
511.5 centre while the imported GTA configuration selected zero stick deadzone;
re3 treats that small upward drift and D-pad Down as conflicting directions.

`r46h-gta-runtime.patch` removes the optional `O_NOATIME` optimization and keeps
a 10% minimum configurable deadzone in both pinned GTA engines. It does not
change the global controller mapping or original content. Clean source
`825cdda7816599814f50fb838f9a708e873737e0` produced re3 SHA-256
`f4865b71ac0a2a9dac10e4cd98a4ba1be5e43bfee94f3d8f9542bf9637e4253e`
and reVC SHA-256
`233d8b574b666208c31872429fa766bdaa6cb30d930b3739cd0311bf541e1156`;
their build receipt records runtime patch SHA-256
`1a9a8ca56459d87936d0df8274031e2e9d803a9aa584d554e3e70d1efe10d92b`.
The hash-bound isolated workspace check passed. R48's exact 1,630-file target
package is `mainline/out/.cache/r46h-gta-runtime-20260913/r48/`, archive SHA-256
`175f6cb38a7b6783264b6a61020a198bfc59df7cf864686be3cfcf908a523cc6`.
GTA III held the case-correct `gta3.img`, completed its 121-second bound without
a forced kill, and the operator accepted D-pad Down plus the intro. Vice City
also reached its intro. Both were reported abnormally slow; save/load, audio,
gameplay, normal exit and relaunch remain open.

R51 then packaged the same engines into the existing shared Wayland compositor,
performance HUD, capture and bounded gamepad endpoint. Source
`75c1800d636b138635c589016b7f99e181760ec1` produced the 1,726-file archive
SHA-256 `d7a1561f93f4c64d3e4825a0c265a624feda7b13fd6447a99d86905088f5d202`;
host and target readback plus target preflight passed. The composed GTA III menu
reported 25.6 game submissions/s, 36.3 ms median and 43.6 ms P95 intervals at
temporary 1008/400 MHz caps. A strict remote Down request completed for
`native.gta3`. The first short run reached the 85 C guard; the second was stopped
after input at 84.615 C. Services, mounts and leases recovered, original save
hashes stayed unchanged and both managed GTA save directories stayed empty.
The device then restored 1296/480 MHz maxima and serial-confirmed poweroff.
Exact evidence is `mainline/out/.cache/r46h-r47-attended-device-20260913.oxUqYw/session.json`.
This measures compositor submissions, not displayed LCD FPS; shared Vice City
and Moonlight were not run.

## R52 production build candidate

The pinned re3/reVC sources state that released PC builds define `MASTER`, which
also selects `FINAL`. `CMAKE_BUILD_TYPE=Release` only supplied compiler
optimization and `NDEBUG`; the R48 binaries still contain `Show Timebars`, frame
timer and Debug Menu strings. Those development paths run per-frame bookkeeping
even when their overlay is hidden.

`build-gta-source.sh` now supplies `MASTER` to both pinned engines and rejects an
artifact retaining the two diagnostic markers. Clean source
`b2d82f707025473ebf47b59c09f9317e10c9d5cc` produced re3 SHA-256
`6ebf8aedffa2a43bfeac93863917da33b13ae2ce0bff672d7a02018444bc12f4`
and reVC SHA-256
`d19bbe5b90648e6ad0ae10b10f27fa256f84fd91381a38187ffd8c1e7814aa3c`.
Both hashes pass readback, and the former diagnostic markers are absent. The
stripped binaries are 204,016 and 271,152 bytes smaller than R48. This does not
change the 30 FPS limit, graphics settings, input, save layout or source game
data. The new binaries each completed a 12-second ARM64 Wayland/software GLES
3.2 process bound without a forced kill. `MASTER` removes the old `GS_FRONTEND`
trace but retains `LOAD frontend`; the launcher now recognizes both markers.
The R54 shared check then loaded the exact R52 hashes, captured both main menus,
moved Down from Start Game to Options, overlaid the global panel and returned to
the same desktop without a forced kill. Evidence is
`mainline/out/.cache/r46h-gta-host-r52-20260914/` and
`mainline/out/.cache/r46h-gta-composed-r54-20260914/`. The frozen R54 package is
`mainline/out/.cache/r46h-gta-shared-20260914/r54/`: source commit
`8923172a3f50cfc37ccce5d8bcee503c6f1b6598`, manifest SHA-256
`9409118571dda4794b0de22c5d82dcd9894049b024710447b659a3f8aaf940d1`
and archive SHA-256
`1b6627947d0ecdf0853d8b48dca21f15f40e8f5e58ea99bee5ed5f83209f7d92`.
Its 1,727-file independent readback passed and it contains no Moonlight client.

The same 1,727 files and preflight passed on the exact R46H. Under temporary
1008/400 MHz caps, two 30-second GTA III menu phases averaged 26.84 game
submissions/s with the full-screen HUD and 30.43/s with it hidden; median interval
samples improved from 35.84 to 31.85 ms. A second HUD-off sample averaged 30.64/s.
All engine bounds exited 0 without a forced kill, the hottest GPU sample was
83.846 C under the 85 C guard, `/roms` stayed read-only and managed GTA saves
stayed empty. Two bounded remote A inputs completed but identical captures stayed
on the main menu, so the reported intro slowdown/crash remains untested. State,
1296/480 MHz limits and the HUD preference were restored before serial-confirmed
poweroff. Exact evidence is
`mainline/out/.cache/r46h-r54-device-20260914.goly7P/session.json`. These are
buffer submissions, not displayed LCD FPS.

R56 source `c5514be42c346f008c8fadf0982668c1d2ad3cf9` retains R55's clipped
HUD and aligns the status row. Its 1,727-file archive SHA-256 is
`d21881d20f26b3a5e5208880211ff1c0304a88fe6881f82b4bf482c738eab762`;
target readback and preflight passed. Device-composed captures show the Wi-Fi,
battery and clock aligned and the HUD confined to the top-right over a real GTA
III intro frame. This is not physical LCD acceptance.

At the same 1008/400 MHz caps, seven 20-second HUD-hidden intro samples averaged
5.57 submissions/s (median 5.00), with 121.24--226.62 ms median and
200.33--268.40 ms P95 intervals. Three HUD-on samples covered a different intro
phase and do not support a matched comparison; the slowdown therefore persists
without the HUD, but its incremental cost in the intro is unresolved. The game
disappeared at 121.17 seconds with `boundedStop=true` and `forcedKill=true`: the
diagnostic bound explains this exit and no natural crash was reproduced. Panfrost
faults coincided with forced session/game cleanup, so that run alone could not
assign a driver cause. R57 later separates the boundary below. Original content and
the GTA configuration stayed unchanged, managed saves stayed empty, limits/state/
services recovered, and serial confirmed poweroff. Exact evidence is
`mainline/out/.cache/r46h-r56-device-20260914.L7Smy5/session.json`; Vice City and
Moonlight were not run.

R57 changes only the shared launcher's self-triggered bound: it now keeps the
existing five-second direct cleanup grace, while an external shared stop retains
its one-second deadline. The process fixture proves a two-second flush completes
without `SIGKILL` and an ignored requested stop is still killed promptly. The real
ARM64 Wayland ports check then passed GTA III, Vice City and Stardew frontend,
routed-input, panel and same-desktop recovery with unchanged engine hashes. Host
evidence is `mainline/out/.cache/r46h-gta-grace-r57-host-20260914.HOhs2f/ports/`.
Clean source `30c1813422acd14078f40a9e9893f4f46f8dbf08` produced the no-Moonlight
package at `mainline/out/.cache/r46h-gta-shared-20260914/r57/`: archive SHA-256
`f0c9e735c8cf52db1d646aa3a94228a24fd798dcb569257db4a2e585ff535693`,
manifest SHA-256
`c2e222e2d0f9a16772d1190c0256ca7e0786078b62b4aaefc1ea33a2ad5f3234`
and shell SHA-256
`c90d918c90e62b1bfd180fdb6eba985bbf508fa3adcef809288726a98a79b7b4`.
All 1,727 files passed independent readback. This does not prove that the R46H
intro exits gracefully or eliminate the Panfrost faults by itself.

The R46H run closes the lifecycle part of that gate: 1024x768 and temporary
640x480 GTA III instances reached 120.97/121.05 seconds, exited 0 and reported no
forced kill. A similar roughly 59-second HUD-on intro window improved from 5.59
to 12.32 submissions/s at 640x480, with median interval samples improving from
161.88 to 76.98 ms. The candidate still reached 85.384 C from a hot start and
activated CPU/GPU cooling, so it is not a final quality/performance decision.
More importantly, one native-resolution and two lower-resolution Panfrost
`DATA_INVALID_FAULT` events occurred while the game stayed active and continued
submitting buffers. They are not explained by forced teardown. The original
configuration was hash-restored before clean serial poweroff. Exact evidence is
`mainline/out/.cache/r46h-r57-device-20260914.vAbRL9/session.json`; no Moonlight,
Vice City, physical LCD/audio/control/save or relaunch result is claimed.

R58 isolates one driver hypothesis without changing the system stack: only the
GTA III/Vice City launch plan sets `PAN_MESA_DEBUG=noafbc`; Stardew and other
applications are unchanged. Mesa 25.0.7's Panfrost option disables AFBC for that
process. The focused plan check and complete ARM64 desktop/session/remote build
passed. Clean source `b5e63c1cbebe00526ca134952977f9954a8e768f` produced the
no-Moonlight package at `mainline/out/.cache/r46h-gta-shared-20260914/r58/`.
Its 1,727 files passed independent readback; archive SHA-256 is
`218e227b9853e3ff046c0afc727c37cee973b2ef04b3b4482f5477d6642bfb76`
and manifest SHA-256 is
`c3ddc421b11350d1fe67b21ff4cf988dd4438eccad0e0efa479ab326e4969099`.

On the exact R46H at temporary 1008/400 MHz caps, a fresh composed menu frame
measured 30.20 submissions/s, then a real intro frame fell to 3.21/s. The first
session requested a clean stop at 60.68 seconds; a cooled second GTA III run
reached its 120.38-second bound.
Both exited 0 without a forced kill. Its recorder retained 27 game-active samples
through 94.95 seconds, averaging 29.51 submissions/s with 33.11 ms median and
37.82 ms P95 interval samples. No matching composed capture identifies that
faster window's visual phase, so it cannot replace the slow-intro observation.
The whole cold boot logged zero Panfrost `DATA_INVALID`/GPU faults and zero ext4
errors. Recorded temperature stayed at 70.0--78.846 C with cooling states zero. Config,
saves, services and 1296/480 MHz limits were unchanged or restored; staging/key
cleanup and serial poweroff passed. Exact evidence is
`mainline/out/.cache/r46h-r58-device-20260914.nA6gGX/session.json`. This is a
two-run fault-suppression candidate result, not a completed fix or physical LCD
FPS proof. Vice City, audio, physical controls, saves and relaunch remain open;
Moonlight was not run.

A same-boot R58 follow-up then supplied the missing phase match and Vice City
machine pass. Bounded remote South/B presses opened New Game and started both
intros. At 1008/400 MHz, GTA III's menu/cutscene measured 28.66/3.17 submissions/s
(313.48 ms intro P95), while Vice City's measured 27.70/4.17/s (247.58 ms P95).
Their 120.82/121.17-second bounded runs exited 0 without forced kills; a second
49.81-second GTA III run was cleanly requested to stop by the outer preview bound.
The whole boot again logged zero Panfrost data/GPU faults and ext4 errors. One
earlier preview ended on a routed-controller disconnect before any game result,
so it is retained as an infrastructure interruption, not a crash. Cleanup and
serial poweroff passed. Exact evidence is
`mainline/out/.cache/r46h-r58-matched-device-20260915.QUE1fH/session.json`.
This confirms the intro pacing defect independently of R58's fault suppression;
physical buttons, LCD motion, audio, gameplay, saves and relaunch remain open.

A host-only audit then traced the exact pinned re3/reVC and librw sources used by
R58. Both engines are Release/`MASTER` builds with `SQUEEZE_PERFORMANCE`; their
runtime seeds disable VSync, multisampling, the new renderer and vehicle pipeline,
and GTA III also disables trails. The normal GL frame path has no explicit
`glFinish` or framebuffer readback, and `CStreaming::Update` schedules ordinary
world reads asynchronously. The matched frame histories nevertheless retain one
4.41-second GTA III gap and one 8.96-second Vice City gap around New Game, followed
by sustained 3--4/s cutscene submissions. This separates a transition hiatus from
the continuing render cost but does not prove which subsystem owns either delay.
Because R57 already showed strong resolution sensitivity, the next discriminating
test is a cooled R58/no-AFBC 1024x768/640x480 A/B with transition and settled
cutscene windows recorded separately. No source patch or product-default change is
justified by this static audit.

## R59 first-config resolution candidate

A cooled R58 follow-up supplied the missing resolution control without changing
either accepted engine. At 640x480 and temporary 1008/400 MHz caps, Vice City's
transition samples averaged 15.36 submissions/s and a later intro capture reported
19.67/s; GTA III's first ten seconds averaged 19.86/s and a later car frame reported
10.75/s. GTA III then touched the external 85 C abort, so this was not retained as
the thermal candidate. At temporary 816/300 MHz caps, 20-second GTA III/Vice City
intro windows averaged 15.24/14.46 submissions/s, peaked at 76.538/77.692 C and
never entered CPU/GPU cooling. Both engine bounds ended at 121.03/121.01 seconds,
exit 0, with no forced kill. A 512x384 request was unsupported and exited 0 before
the frontend. Exact evidence is
`mainline/out/.cache/r46h-r59-resolution-device-20260915.0uJai5/`.

This supports the smallest product change: a first target-managed GTA config
copies an exact 1024x768 source preference as 640x480. Host tests keep their
1024x768 disposable window, existing managed preferences are not rewritten and
the accepted engine/no-AFBC paths remain unchanged. The temporary frequency caps
are evidence controls, not a new persistent or per-game policy. Physical LCD
quality, audio, controls, gameplay, saves and relaunch remain open.

Clean source `944b753208d7073527ebf27b0309e5038c1b4941` produced the R59
no-Moonlight package at `mainline/out/.cache/r46h-gta-shared-20260915/r59/`.
Its 1,727 files passed independent verification; archive SHA-256 is
`b6b02e33439d8472a4a0854faefdf1f910c083c9bbf6cce5c23efbed0ce8de23`,
manifest SHA-256 is
`172e7c9cf41816dd6f250b1dca1239bb94a5db79f54ea4a53391ae89da68cbeb`
and shell SHA-256 is
`650b4d9ee97f46d9fc89a3f5dc2859841587745bff99e2afcf36b4062a97adfc`.
On the exact R46H, package readback/preflight passed and a fresh state generated
GTA III config SHA-256
`9caf644193bc42844112a86cfc8ed0bce11a721e0693efb23542528744020d29`
at 640x480. The unchanged engine reached a real game frame and exited 0 without a
forced kill. The original preview state, 1296/480 MHz limits and ES-DE were restored;
staging/access were removed and the device stayed on. Exact evidence is the R59
directory above and
`mainline/out/.cache/r46h-r59-resolution-device-20260915.0uJai5/session.json`.

## R60 private Mesa runtime candidate

A same-boot 816/300 MHz A/B kept the accepted engines, 640x480 configuration,
no-AFBC setting and HUD policy fixed. With Debian Mesa 25.0.7, the active GTA III
window averaged 11.00 submissions/s and Vice City averaged 14.67/s. A private
Mesa 26.2.2 EGL/GBM/Gallium closure raised them to 14.36/s and 17.15/s,
respectively. Candidate runs exited 0 below 81 C with zero cooling state and no
new Panfrost fault; the original-Mesa GTA III control added one
`DATA_INVALID_FAULT`. A preceding Gallium-only frontend run segfaulted without a
GPU fault, so that partial ABI replacement is rejected.

The retained integration packages the complete closure only inside the shared
Wayland session. It does not overwrite Debian libraries or affect ES-DE. These
rates are compositor submissions rather than physical LCD FPS.

Clean source `495c35232176f0c6ca39a93fd6ab4ac1f02e70bd` produced the formal
1,741-file no-Moonlight R60 package. Archive, manifest and private Mesa SHA-256
values are `0a0861bb2d4713f79cf198a50f8fed9cf37b9a174a7c3df9fb510fc90aaf20b3`,
`ebb732de7ee71d830f2603667eabb421f969fc01b9df0cf03197814822bf8168` and
`307c4ad9af58217a5f58ca936cf36984edff8efa43a857bd062e185b56a162f3`.
Full host checks and exact-target preflight passed. Weston, the shell and re3
mapped the private Mesa files; GTA III reported `OpenGL ES 3.1 Mesa 26.2.2`,
rendered a captured intro and reached its 121.15-second bound at exit 0 without
a forced kill or new GPU fault. The system Mesa hash, services and stock clocks
were restored; access/staging were removed and the device stayed on. Evidence is
`mainline/out/.cache/r46h-r60-formal-device-20260915/session.json`. At that
checkpoint, LCD motion, audio, physical controls, gameplay, saves and relaunch
were open.

A power-backed R60 batch on 2026-09-16 revalidated the exact archive and target
preflight. At temporary 816/300 MHz caps, two completed remote South/B samples
started fresh GTA III and Vice City cutscenes. Their composed captures reported
20.32/19.03 submissions/s; later 20-second windows had 10.31/16.73 median
submissions/s in their observed phases and peaked at 76.923/76.153 C without a
cooling state. Both 120.97/121.15-second bounds exited 0 without a forced kill.
Fresh sessions relaunched both games; a 28.56-second Vice City relaunch stopped
on request without a forced kill. The boot logged zero ext4/Panfrost/GPU faults,
and stock clocks, services, access and runtime state were restored before
serial-confirmed poweroff. Exact evidence is
`mainline/out/.cache/r46h-unattended-20260916/session.json`. This closes the
machine relaunch gate only; physical LCD motion, audio, controls, gameplay and
saves remain open.

A same-day follow-up exercised the guarded Stardew save path: the original two
save files, managed copy and timestamped backup kept identical SHA-256 values,
and a second import was refused without overwriting either tree. `/roms` stayed
read-only. Temporarily removing and restoring the managed `Saves` directory did
not change launch behavior. At both 816/300 MHz and stock 1296/480 MHz, Mono
remained before SDL/Wayland initialization for the full 120-second bound, with
no game window or buffer submission; lower GTA caps only made that wait longer.
In the same boot Vice City completed another 120.40-second run at exit 0; eleven
valid samples averaged 58.26 submissions/s, peaked at 77.307 C and never entered
a cooling state. Evidence is under
`mainline/out/.cache/r46h-unattended-20260916-2/`. The copy/backup and mixed-run
gates are closed; Stardew save selection/load and shared-window readiness remain
open.

An attended 2026-09-17 R60 Vice City batch then supplied the first physical
intro acceptance: the operator reported normal LCD motion, audio and controls at
temporary 816/300 MHz. Its 25 game samples averaged 18.24 submissions/s with an
18.67/s median, 52.55 ms median interval and 66.538 C maximum. A 1008/400 MHz
sample reached a 20.87/s median, while stock 1296/480 MHz reached the external
85 C abort at only 19.52/s median. The rates are client buffer commits, not LCD
FPS, but the weak scaling and physical observation reject clocks as the primary
remaining pacing limit.

Two single-variable software candidates were rejected. Disabling Vice City's
frame limiter reduced the 816/300 MHz median to 17.24/s and the original config
was restored. A 15-second `strace -c -f` of accepted R60 recorded 65,277 syscalls:
57.96% of syscall time in `ppoll`, 21.68% in `ioctl`, 9.68% in `mmap` and 7.85%
in `munmap`; render-thread detail repeatedly showed Panfrost BO waits and
immediate-buffer map/unmap activity. R61 therefore sized librw immediate buffers
to each draw, but its phase-matched first 64.5 seconds regressed from R60's
18.97/s median to 17.60/s. Commit `354ab53` was reverted by `dce8dad`; R60 remains
the accepted fallback. Investigate persistent/ring-buffer reuse or batching only
with engine-side phase timing. Evidence is
`mainline/out/.cache/r46h-attended-cooling-20260917.vlknbF/session.json`.

This run did not accept GTA III physical play, broader Vice City gameplay, saves
or relaunch. Stock clocks, services, configuration and ES-DE were restored before
cleanup and controlled poweroff.

The R36-R39 target record is
`mainline/out/.cache/r46h-r36-gta3-device-20260912.KssIkj/session.json`. All four
manifests and fixed identities passed. The final run peaked at 78.461 C under the
85 C guard, returned to ES-DE, restored 1296/480 MHz maxima, left failed units empty
and powered off through serial. R40 then reproduced the same loader failure under
direct KMSDRM; R41 added the matching Vice City failure and independent Stardew
SDL/GBM crash. R42 retires the old GTA binaries and closes target frontend
readiness; attended gameplay is next.

`test-port-runtime-lease.py` exercises identity/ownership/mount-ID checks and failed
acquisition cleanup with fake mounts. `test-local-port.py` checks actual retained
inputs and isolated writable paths without launching games. These and the native
supervisor tests cannot substitute for actual LCD/audio/input/save acceptance.

Set `R46H_GTA_IMMEDIATE_PROFILE=1 R46H_GTA_IMMEDIATE_RING=0` for the
behavior-preserving profiler. Its R62
Vice City target run retained Mesa 26.2.2 and the 816/300 MHz caps, exited 0 at
121.04 seconds, and produced 103 valid one-second intervals. Tiny uploads used a
weighted 18.44% of wall time overall and 15.40% in the last 37 intervals despite
only 0.44 MB/s median bandwidth; the latter window had 793 calls/s median. This
identifies per-call synchronization overhead rather than upload bandwidth.

Set `R46H_GTA_IMMEDIATE_RING=1` for the R63 candidate. It appends 2D/3D vertex and
index uploads inside the existing fixed-capacity buffers, orphaning only when a
buffer wraps; profiling and ring modes are mutually exclusive. Its ARM64 re3/reVC
SHA-256 values are
`575fe67064b8250dfbb06645a7046b30677ebbc5515838bda551f4fec37df6b7` and
`dc36256b6e51b65e7f615fe6ab4a18f4f74bd5e99dff78c2118467d0ab922883`;
the patch SHA-256 is
`cbed003ac36ffd75788653c61c1d6a754d30c8258504689304bd2d8929acbfdb`.
At 816/300 MHz, 16 active Vice City samples reached a 20.52/s median and 45.23 ms
median interval, improving R60's 18.67/s and 52.55 ms by 9.9% and 13.9%. The
120.88-second run exited 0 without cooling or GPU faults, but one isolated interval
reached 1.116 seconds. With both options unset, rebuilt engines remain byte-identical
to R60 and contain neither optional receipt. R60 remains the rollback. Exact
R62/R63 evidence is in
`mainline/out/.cache/r46h-gta-profile-device-20260919.aakor9/session.json` and
`mainline/out/.cache/r46h-gta-ring-device-20260919.axyBwv/session.json`.

A later default-policy R63 reacceptance run remotely delivered the two B presses,
captured the Vice City intro with `GPU 480 MHz` in the HUD and recorded 14 samples
over 45 seconds. Submission rate ranged from 19.34 to 26.60/s (23.26/s mean),
frame-interval median averaged 40.32 ms, CPU/GPU stayed at 1008/480 MHz and the
temperature peaked at 82.307 C without reaching the 85 C guard. The engine exited
0 after 115.16 seconds, with no forced kill, low voltage or current-boot fault;
services, policies, `sync` and temporary-access cleanup passed. This run was
machine proof only. Evidence is in
`mainline/out/.cache/r46h-r63-physical-20260919.jo53TV/session.json`.

R70 then repeated the exact R63/default-policy intro path for the operator. The
operator reported no issue with the requested LCD motion/picture, audible output
and physical-control observation. Nine 30-second machine samples averaged 23.13
submissions/s and 41.26 ms median intervals; the thermal guard peaked at 82.692 C
without firing. The preview exited 0, health and `sync` passed, services/policies
were restored, temporary access/staging was removed and the device remained on.
This accepts the short R63 intro path; broader gameplay, saves and GTA III physical
play remain open. Evidence is in
`mainline/out/.cache/r46h-r63-acceptance-20260919.m1uKjv/session.json`.

Set `R46H_GTA_SWAP_NOWAIT=1` only for the isolated swap-wait experiment. It
keeps the engine's 30 FPS frame limiter but forces SDL GL swap interval zero,
separating that limiter from compositor/VSync waiting. Combine it with the R63
ring candidate for the target A/B; it is not a product default. The R66 target
run averaged 24.17 submissions/s versus 22.67/s for its same-boot control, a
6.6% gain that leaves the cutscene below 30 FPS. Swap waiting is secondary.

Set `R46H_GTA_FRAME_PROFILE=1` for the Vice City phase profiler. It records
one-second averages for game processing, render phases and swap to stderr and
can be combined with the R63 ring candidate. It is not a product default. R69
excluded the first ten startup/menu windows and retained 48 windows containing
1,222 frames. The weighted mean was 40.06 ms/frame: `CRenderer::PreRender`
13.37 ms (33.4%), `RenderScene` 8.79 ms (21.9%), swap 3.66 ms (9.1%) and game
processing 3.07 ms (7.7%). Its matched display sample averaged 24.25
submissions/s at 1008/480 MHz, the engine exited 0 on request, and temperature
peaked at 83.076 C. The primary remaining bottleneck is CPU-side entity
preparation in `CRenderer::PreRender`; split or optimize that path before more
clock work. A direct unsynchronized-map candidate was rejected after an early
`SIGSEGV` and was removed. Exact evidence is in
`mainline/out/.cache/r46h-vblank-r65-device-20260919.LIMH3N/session.json`.
R71 then attributed the low-rate intro phase to the object bucket: roughly
13--17 ms/frame came from 6--11 object calls while the other entity buckets
stayed below about 0.2 ms/frame. R72 identified the exact cause: four or five
real-time cutscene-shadow updates cost 11.8--16.1 ms/frame and their registration
another 1.6--2.1 ms, while animation cost only 0.16--0.25 ms. Set
`R46H_GTA_SIMPLE_CUTSCENE_SHADOWS=1` for the isolated fallback-shadow candidate;
it retains the engine's ordinary ped shadow but skips the per-character offscreen
shadow map. In matched profiler builds, R73 reduced median `PreRender` from
13.73 to 0.46 ms/frame and median total frame time from 40.72 to 27.37 ms;
the expensive update fell to zero while the fallback registration used only
0.01 ms. Its longer run reached the external 85 C guard, then restored cleanly.
The uninstrumented R74 product candidate captured the same intro at a 28.93/s
median and 33.89 ms median interval across nine complete samples, peaked at
80.384 C, and exited its 121.06-second bound at status 0 without a forced kill.
The following R75 operator check found no LCD motion, picture, audio or control
problem and accepts R74 for that short path. Later open-world play did not hold
30 FPS; broader play and saves remain open. R74's ring upload and simple cutscene
shadows are now the default source build and packaged-runtime hash contract;
set both feature variables to `0` only to reproduce the R60 rollback. R63 and R60
remain rollbacks. Exact
R71 evidence is in
`mainline/out/.cache/r46h-prerender-r71-device-20260919.ATo8aL/`.
Exact R72 evidence is in
`mainline/out/.cache/r46h-cutscene-r72-device-20260919.OL5FJ2/`.
Exact R73/R74 evidence is in
`mainline/out/.cache/r46h-simple-shadow-r73-device-20260919.dlSzrS/` and
`mainline/out/.cache/r46h-simple-shadow-r74-device-20260919.jH33JR/`.

R79 revalidated the accepted R74 engines through the transient Jume Launcher on
p2 v0.18. A rejected logical-A attempt left byte-identical GTA III menu captures;
two logical-B samples then produced distinct startup-animation captures for GTA III
and Vice City. GTA III's ten samples across 20 seconds ranged 25.03--29.85 submissions/s
with 33.94--36.14 ms median intervals and 79.23 C maximum. After one transition
sample, Vice City held 29.35--30.33 submissions/s with 33.80--34.03 ms medians and
80.384 C maximum. Both sampled mostly at 480 MHz GPU, exited through the shared panel
and returned to Launcher with clean lease/service restoration. These are composed
startup samples, not physical LCD FPS, audio, controls, broader play or save proof.
Evidence is under `mainline/out/.cache/r46h-v018-device-20260920.FoS3wK/`.

The later SGSR1 experiment rendered Vice City into a 480x360 offscreen target
and attempted a full-frame upscale to the existing 640x480 output. The shader
from upstream commit `d926f074bcb9d714e179f1ce0fcb9ee2eeb5074e` did not compile
under Mesa 26.2.2/Panfrost because its gather component was not a constant
expression. The apparent working fallback was not SGSR and did not improve the
matched intro rate. Specializing the fixed mode removed that diagnostic, but
reVC exited -11 after 6.14 seconds before reaching the frontend. The candidate
is rejected, its product code was removed, and unchanged reruns are not useful.
Evidence is under
`mainline/out/.cache/r46h-sgsr-r76-device-20260919.Ryx78e/`.
