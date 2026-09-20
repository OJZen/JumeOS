# Independent tool applications

Status 2026-09-20: **R45 STARDEW DIRECT TARGET PASS / R77 SHARED HOST PACKAGE PASS / TARGET OPEN**.
The normal home/library has separate Neo, PortMaster and USB entries. Each uses
[shared UI defaults](controls/README.md), its own route and the existing controller,
modal, keyboard and remote-control paths. No persistent launcher was replaced.

## Pages and state

| Application | Available host work | Device gate |
| --- | --- | --- |
| Neo | Fixed Metal Slug resource/hash check, display options, private saves/backup, direct/shared adapters | R35 slot 0 save survived reboot and loaded; physical controls and longer gameplay remain open |
| PortMaster | Original-game resources/saves plus catalog, search, install/update/rollback/uninstall and verified dependency runtimes | R74 GTA and R45 direct Stardew automation pass; shared Stardew plus attended gameplay/saves remain open |
| USB gamepad | AB/XY swap, right-Y inversion, 0–30% deadzone chooser, private config/descriptor export | External peripheral routing/UDC must be proven; the output switch stays disabled |

`--scene neo|ports|usb` opens a tool directly. `--content-root /absolute/path`
changes the read-only inspection root (default `/roms`) for disposable host
fixtures. It cannot enable native gameplay. Tool settings live in private
`STATE/tools/settings.json`; malformed files are preserved, and failed saves
retain the draft and block leaving. The parent owns one bounded worker for
inspection/hashing/copying. No legacy launcher is executed and no original game
asset, original save, host service or USB role is modified.

Port saves are copied to `STATE/tools/ports/ID/saves`; existing destinations are
never overwritten. Neo uses `mslug/saves/battery` and `mslug/saves/states`, so
its backup includes both native and quick states. Existing generic RetroArch
saves are not silently imported. Backups are unique directories under
`STATE/tools/backups`. Copying rejects symlinks and stops at 2,048 files/64 MiB;
file size, mtime and SHA-256 are checked before atomic directory promotion.
Stardew may create `startup_preferences` before an import. If that is the only
managed file, import atomically adds the original `Saves` directory beside it;
any other existing entry still refuses the copy without overwrite.
Hidden placeholders and copy receipts are not game saves. Normal navigation or
window close waits for an active copy/export; forced termination may leave a
bounded `.incoming-*` partial copy, never replacing an existing save. Inspect
that partial directory before cleanup/retry.

USB export writes only `STATE/tools/usb-profile.json`: four mapping settings,
a 14-byte report contract, descriptor and neutral example. It does not open
`/dev/hidg*`, bind a UDC or change VBUS. [USB feasibility](../gaming-usb-gamepad/README.md)
owns the hardware decision. [Ports](../gaming-ports/README.md) owns original-data
provenance and runtime requirements.

## Neo direct-display candidate

After the normal package/identity preparation in the [device runbook](README.md#prepare-an-attended-device-run),
the bounded probe accepts:

```sh
/run/r46h-shell-probe/probe-r46h.sh --native SHELL_SHA256
/run/r46h-shell-probe/probe-r46h.sh --remote-native SHELL_SHA256 PUBLIC_KEY_SHA256 DEVICE_IP MAC_IP
```

Use freshly verified device addresses and the existing strict SSH setup; these
are not installation commands. The shell requires `--native-handoff`, the exact
R46H target and `/roms` before writing a fixed Metal Slug request and exiting 79.
The supervisor starts a QCore worker only after the Qt window has released DRM.
The worker rechecks the accepted ROM/BIOS/core hashes and trusted RetroArch/config/
metadata, appends the private save/display settings, and runs literal argv.
Both adapters require UID 1000, the matching preview cgroup and read-only `/roms`.
The accepted per-core options are copied once into the private game directory;
new options, saves and screenshots stay there. Automatic overrides/remaps and
history/runtime writes are disabled. A single Select+Start exits; the private
config explicitly disables RetroArch's default double-quit requirement.
It sets `/usr/local/libexec` as the core directory to include the accepted FBNeo
core; R35 used this path for persistent save/load, without physical-control proof.
Normal/error/timeout return starts a fresh Neo page/session; invalid input aborts.
The existing outer cgroup, audio mux restoration, deadline and ES-DE recovery
remain authoritative. Wayland/global overlays remain a separate display gate.

## Neo shared-display adapter

The newer working source uses the existing `Applications` foreground manager
inside the [handheld compositor](../gaming-wayland/HANDHELD.md). It launches the
same guarded worker with `--shared-native`; the desktop and IPC session remain
alive. RetroArch uses Wayland/EGL and SDL2's normalized routed controller buttons,
including trigger axes. L3+R3 opens the global panel and B returns input to the
game. Completion records the result and refreshes Neo save/resource information.
Shared port launch additionally requires the supervisor's mounted-runtime capability
and persistent state. R20/R22 archives predate this source and remain unchanged.

The shared probe defaults to disposable state under `/run`. Its explicit persistent
state option is documented in the [shared ports contract](../gaming-ports/README.md#shared-target-session-candidate);
R35 proved Neo retention across warm reboot; each other data class remains separate.

The native game ceiling is 120 seconds in remote/unattended mode. The supervisor's
explicit `--attended` option permits 35 minutes, but no longer target probe is
implicitly enabled. Never replay the historical p2-v0.7 installer on v0.17.

## Current shared candidate

Use [R36](../gaming-wayland/HANDHELD.md#resume-and-rebuild) for the next shared
session. It retains the status area, guarded cleanup and Neo lifecycle, fixes the
PortMaster backend's inherited home, and passed persistent Neo reboot-load plus
the 1,396-entry target catalog. The
[R35/R36 device record](../gaming-wayland/HANDHELD.md#r35r36-device-follow-up-2026-09-12)
owns exact evidence and thermal limits. Physical controls, catalog mutations and
native-port acceptance remain open; the
[R36-R39 GTA record](../gaming-wayland/HANDHELD.md#r36-r39-gta-iii-device-follow-up-2026-09-12)
owns the failed target launch. Use the
maintained wait after every launch and do not replay discarded session keys.

## R40 direct GTA III device comparison

`mainline/out/.cache/r46h-direct-gta-20260913/r40/receipt.json` freezes the direct
package at source `286fcdfcf7643c43f19b1272beefd136e09cc08f`. ARM64 shell/network/tools,
packaged keyboard/control/application/handoff/PortMaster checks, direct-supervisor
recovery and an independent 1,629-file readback passed. It adds no new display path:
`--remote-ports` still releases EGLFS/DRM before the native KMSDRM worker starts.

The fixed R46H repeated all 1,629 hashes, mounted/released the guarded runtime and
ran GTA III under that direct worker. The engine exited -11 after 1.46 seconds at
`gladLoadGLLoader`, matching R39's shared failure before `GS_FRONTEND`. Managed
saves stayed empty, the 85 C guard peaked at 64.583 C, frequency limits and ES-DE
recovered, failed units/kernel-fault matches were zero, and serial poweroff passed.
Exact evidence is `mainline/out/.cache/r46h-r40-direct-device-20260913.mAey9k/session.json`.
Do not rerun this engine without a source-proven GLES 3.1 loader rebuild.

## R41 ports and USB device batch

R41 reused the exact R40 package and passed the 1,629-file target readback. The
guarded direct session then mounted the original Mono squashfs read-only: Stardew
reached its managed program entry but crashed in `SDL_CreateWindow` / GBM after
10.44 seconds. Vice City's fixed reVC failed after 1.12 seconds at the same
`gladLoadGLLoader` source line as GTA III. Both returned to a fresh tool UI, all
original/managed save counts were preserved, the runtime lease released, ES-DE and
frequency limits recovered, and serial poweroff passed. The same boot's read-only
USB inventory was Host-only with no UDC/gadget/role entry. Exact evidence is
`mainline/out/.cache/r46h-r40-ports-batch-device-20260913.XEe7qy/session.json`.

## R42 source and device candidate

R42 packages reproducibly built re3/reVC from exact upstream commits and removes the
GTA profile shim. librw now creates the context and loads GLAD inside its existing
GLES fallback loop; Stardew's Mono shim also isolates direct GBM loading. Both GTA
engines rendered captured real menus and exited cleanly in isolated ARM64 host runs.
The full 1,630-file package passed the existing shell, keyboard, PortMaster, remote,
handoff, native-supervisor and lease checks. Receipt:
`mainline/out/.cache/r46h-source-gta-20260913/r42/receipt.json`.

The fixed R46H repeated all 1,630 hashes. Source-built GTA III and Vice City used
Panfrost OpenGL ES 3.1, reached `GS_FRONTEND`, ran for 120.45/120.55 seconds and
returned to fresh PortMaster UIs. Their original assets stayed read-only and all
managed save trees stayed empty. This proves target process/frontend readiness,
not operator gameplay, LCD, audio, controls, saves or relaunch. Stardew still
crashed after 10.46 seconds in `SDL_CreateWindow` / `gbm_create_device`, so the
GBM deep-binding change is rejected. The batch peaked at 67.307 C, restored ES-DE
and frequency limits, left zero failed units/kernel-fault matches/listeners, and
powered off through serial. Cold boot was not captured because serial attached
after power-on. Exact evidence is
`mainline/out/.cache/r46h-r42-ports-device-20260913.GdcAbV/session.json`.

The post-R42 follow-up confirms why GBM-only isolation was inert: the 2022 Mono
exposes 9,534 LLVM 6.1 dynamic symbols while target Mesa loads LLVM 19, and no GBM
shim marker appeared before the crash. The minimal next patch also deep-binds the
actual `*_dri.so` provider; its ARM64 Panfrost collision check passes. It remains
host evidence until a clean package and target run exist.

## Retained R20 host candidate

`mainline/out/.cache/r46h-ports-backend-20260910/r20/receipt.json` and `SHA256SUMS`
own the frozen native-ports shell, Moonlight v4 combination and source at
`11c9cdd48ffee2b041d8ec5e6cff86c5de5a1db8`. ARM64 package checks passed, including
the native supervisor and Mono lease guards. The [ports runbook](../gaming-ports/README.md)
owns the three original-game profiles and their host frontend evidence.
These archives remain historical comparisons; the current shared candidate is
linked above. Runtime mounting, gameplay/save-load and persistence remain open.

## Retained host candidates

`mainline/out/.cache/r46h-ports-backend-20260910/receipt.json` and `SHA256SUMS`
own the R19 source and packages at clean experimental commit
`dfd6036b1e0623e85d1c470d03d8dcbe78dad690`. The relocated ARM64 package passed
its actual PortMaster Python/UI flow, public-search text/privacy checks, keyboard,
remote control and application/stream lifecycle tests. The backend runtime adds
about 0.55 MiB compressed. [Ports](../gaming-ports/README.md) owns its contracts.

The optional persistent state path in the [shell runbook](README.md#optional-persistent-preview-state)
is needed before installing packages or keeping new game progress on the target;
leave that private data in place when retiring `/run` staging. Target power-cycle
persistence and actual port launch remain untested. R18 and the R17/v3 device
fallbacks stay retained.

The retained experimental source is `a1956ce753ef305da8b18420aa38d75ac23302da`
(`codex/r46h-tools-r18-candidate`); later commits supersede its source snapshot.
`mainline/out/.cache/r46h-tools-20260910/receipt.json` and `SHA256SUMS` own the
frozen source, ARM64 shell, combined Moonlight v4 package, checks and screenshots.
They remain a tools-only comparison point. No TF rewrite, permanent installation
or service registration occurred.

The [current context](../../docs/PROJECT-CONTEXT.md#immediate-next-gate) owns
the next device batch and selected streaming host. Port runtime and USB connector
checks remain separate; disabled USB output is expected until hardware routing
is established. Keep R17/v3 fallbacks and end bounded device runs with normal poweroff.

## Host checks

`tools-check` exercises dirty-save retry, in-flight route inspection, safe copy
and HID report encoding. `test-shell-tools.py --binary ABSOLUTE_BINARY --evidence
ABSOLUTE_EXTERNAL_DIRECTORY` drives actual IPC: independent routes, favorites,
copy/refusal/backup, export, failed-save recovery, modal isolation and 100/120%
font screenshots. `test-gaming-probe.py` checks native and stream supervisor
normal/error/timeout/invalid-request cleanup. The Linux builder runs the relocated
package, existing application/stream lifecycle and packaged keyboard checks.
No host check proves physical controls, audio, port playability or USB enumeration.

`--ports` / `--remote-ports` add a persistent-data native ports session;
`--attended-ports` reuses the same direct path with a 35-minute per-game ceiling
inside the existing 90-minute outer guard. Port modes provision the private
`state/` log directory before root-protecting fresh `/run` staging; a link or
wrong existing owner is refused. The
[ports runbook](../gaming-ports/README.md#native-ports-session-candidate) owns
Mono mounting, private libraries, exit reporting and pending physical gates.
