# Jume default-desktop candidate

Status: **r11 default cold/warm boot and ES-DE failure recovery PASS for observed paths**.
The [default activation](#r11-default-activation--2026-10-30) adds recovery proof to the
[r11 desktop soak](#r11-two-hour-desktop-soak--2026-10-29). One operator-confirmed cold start now passes; gameplay remains open. Keep ES-DE.
The original r9 clean-source candidate is from `5126d40`, under `mainline/out/.cache/jume-product-arm64-20260927-r9/`.
Its `receipt.json` records source, archive and evidence hashes; all were rechecked.
Qt checks (10 tools + 13 shell), desktop/tasks, PortMaster, packaged session/power
exits and full installer seal passed. Fresh-container SSH passed with the final
ELF. The installer's selection/retry/refusal contracts pass macOS and ARM64 Linux.
All 2,954 archive members were compared with r8: only installer, manifest and
Launcher differ; that host comparison alone proves neither byte-reproducibility nor device acceptance.
Build record: `mainline/out/.cache/jume-product-arm64-20260927-r9/session.md`.
This artifact includes Files/Terminal/native ports, not Browser or Moonlight.
The r9 installer exactly matches the separately device-tested rollback correction below.
Sealed r8 lacks that correction; r9 is installed and machine-tested below.
The builder verifies the complete payload with the installer's seal checks.
Remote tests use an anonymous Linux disk volume, removed with the container:
the payload exceeds the 192 MiB `/run` tmpfs, and macOS binds do not retain test UIDs.
Build caches, final artifacts and evidence stay on the external workspace.
Compilation/session and SSH checks run in separate, equally memory-limited
containers; previous input fixtures and build memory do not carry into SSH tests.

## Installed trial — 2026-09-27

The frozen r6 payload passed verified installation and a UART/85 C-guarded trial
on v0.18. First startup exposed systemd 257 rejecting `reset-failed` for a fresh
unloaded unit. The installer now queries ActiveState and resets only failed units;
inactive, failed and query-error recovery paths have focused host coverage.
On-device execution used a separately hash-verified corrected installer, leaving
the sealed payload untouched. The corrected installer is included in r7/r8;
the retained r6 installer's first-start bug is not fixed inside that artifact.

Launcher (with Files active), Weston and seatd were killed separately. Each
cleaned old children/leases and produced a new IPC generation and composed Home
frame without starting ES-DE. Full validation adds roughly 40 seconds per restart.
One desktop survived 460 seconds; GTA III survived 273 seconds, accepted two
routed B presses and produced an intro frame with positive recent submissions.
The explicit End Game action cleared its group and returned to the same desktop;
this was requested SIGTERM cleanup, not proof of engine exit 0 or save flushing.
Files capture privacy also passed. CPU-helper RuntimeMaxUSec is infinity;
actual two-hour endurance and interrupted lease cleanup remain open; startup-failure limiting is covered below.
Explicit rollback restored ES-DE/input/volume and CPU/backlight, with no failed
units or kernel errors. All 164 prior files remained present; the existing save
hash was unchanged. The inactive sealed release and root-private pre-trial backup
remain installed; task staging/SSH/guard/keys were removed. UART confirmed clean
poweroff. These are machine observations, not operator LCD/audio/save-load acceptance.
Evidence: `mainline/out/.cache/jume-product-device-20260927.hB4f8e/session.md`.

## Release cycling and failed-state recovery — 2026-09-27

r8 was transferred over UART-pinned Wi-Fi SSH, hash-checked, synced and fully
seal-verified. Inactive r6-to-r8 selection, r8 trial/Home/library navigation,
explicit ES-DE rollback, reverse selection and r6 trial/Home all passed.
Each Launcher ELF/session matched the expected version. Live switching was
refused; old children/binds/leases were removed. All 167 existing state files,
including the existing save/backup, remained byte-identical.

On r6 with the identical installed unit, a main-process kill followed by three
verified prepare-process failures triggered `Start request repeated too quickly`.
The journal proves limiting; the fixture's expected `Result=start-limit-hit`
was wrong for this systemd 257 run, which retained `Result=signal`. ES-DE started
only on explicit rescue. That rescue exposed a real bug: `stop` leaves a failed
unit failed, so subsequent selection refuses it. The corrected installer resets
failed state only after verified cleanup. A separately hash-verified script
passed recovery to inactive and another bidirectional selection on device;
sealed r6/r8 were not modified. Host checks cover failed/inactive/query-error paths.

Final state: inactive r6 selected, r8 and private backups retained, ES-DE default,
no failed units/kernel errors. Task staging/SSH/guard/keys were removed and UART
confirmed clean poweroff. No physical LCD/audio/save-load or sudden-power-loss claim.
Evidence: `mainline/out/.cache/jume-r8-device-20260927.aMhPCy/session.md`.

## Packaged r9 recovery and GUI reboot — 2026-09-27

r9 transfer/full seal, trial Home and exact Launcher identity passed. Three
verified prepare failures reached the restart limit; the packaged installer
recovered the failed unit to inactive/disabled and restored ES-DE. Subsequent
r9-to-r6-to-r9 selection passed without a separate repair script.

With real device/CPU/Mono leases held, a reversible owned mount-receipt mismatch
made rollback refuse cleanup and keep ES-DE stopped. Restoring the exact receipt
and running the sealed cleanup hook recovered normally. This proves fail-closed
receipt handling, not interruption of the cleanup hook or sudden power loss.

The Settings reboot confirmation triggered a real warm reboot, with UART filesystem
detachment and a new boot ID. ES-DE/input/volume and Wi-Fi returned automatically;
Jume stayed inactive/disabled with r9 selected. All 167 prior files, including the
existing save/backup, remained identical. No failed units or kernel errors.
GUI poweroff, two-hour endurance and operator/save-load acceptance remain open.

Final state: r9 selected inactive, r6/r8 and private backups retained, ES-DE default.
117 guard samples peaked at CPU 76.923 C/GPU 76.538 C; no abort. Task staging,
SSH/guard/keys were removed; UART confirmed final clean poweroff.
Evidence: `mainline/out/.cache/jume-r9-device-20260927.uudLqJ/session.md`.

## Jume UI v1 trials (r10/r11) — 2026-10-28

r10 (`169783b`, manifest `7dcbe3c6…`) and r11 (`38643e9`, manifest `c049d069…`, archive
`4764be53…`) were built from clean worktrees with the full host gate, then staged over a
temporary key/IP-restricted SFTP port with a UART-pinned host key, verified, selected from r9 and
trialled. Captured Home, quick panel, options, power menu and tools show the v1 UI; the session held
the `handle-power-key` inhibitor and the operator confirmed the power key (short off, wake, hold
menu). r11 fixed the clipped row rings seen on r10. Rollback restored ES-DE with no failed units or
kernel errors; staging/keys were removed and UART confirmed clean poweroff. Final state: inactive r11
selected, r6/r8/r9/r10 and `pre-r10-IM577S` backup retained, ES-DE default. Not accepted: games,
saves, LCD readability, Select chords on hardware, endurance or default promotion.
Evidence: `mainline/out/.cache/jume-r10-device-20261028.IM577S/`.

## R11 two-hour desktop soak — 2026-10-29

Status: **PASS_DESKTOP_ONLY / UART-CONFIRMED POWEROFF**. The sealed r11 trial on p2 v0.18
ran **7203.1 seconds** from **00:03:49.986 CST**, with the same service/GUI PID and IPC
generation, 680 health samples, 114 Home/Right/Left cycles and inspected start/end composed frames.
No game was launched, setting edited, default promoted or r9-only fallback overlay applied.

During the soak, CPU/GPU peaked at **66.153/67.307 C**, available RAM stayed above
**602644 KiB (588.5 MiB)** and GUI RSS peaked at **192684 KiB (188.2 MiB)**.
AC stayed present, voltage >=4.015600 V, and the storage/Panfrost/OOM scan found zero faults.
All 177 files in the aggregate state snapshot matched before/after the run, before rollback;
this is byte-retention evidence, not gameplay/save-load or a post-poweroff readback.

The device-owned finish hook rolled back to ES-DE with zero failed units. Its post-cleanup
CPU/GPU sample was 71.666/69.615 C, separate from the soak peaks. It synced, exported a
179761-byte archive (SHA256 `0a8908a4b10ce918975b08090cb1a0ecafbdaa21b2e09801906b22bf86d31acd`)
and requested poweroff. UART at about **02:04 CST** confirmed `/roms` unmount, root read-only,
all filesystems/loops detached and `Powering off`; the emergency timer was not needed.

Archive bytes/hash, fixed member allowlist, all health extrema, state hashes and original guard
source were independently checked on the host. Serial capture is closed; heartbeat `r46h` was
deleted. No SSH service/key was installed. Upload staging was removed; bounded named target
evidence remains at `/var/lib/jume-soak-0czawbe0` for later deliberate cleanup, with a verified
host copy at `mainline/out/.cache/jume-r11-soak-20261028.0czawbe0/` (`receipt.json`, `target-evidence/`).
Final selection is inactive/disabled r11 with ES-DE boot default; retained releases/backups remain.
This closes only desktop/light-navigation endurance. Gameplay, saves, physical LCD/audio/controls,
GUI poweroff, interrupted cleanup, default cold boot and crash fallback still need their own proof.

## R11 default activation — 2026-10-30

Status: **DEFAULT WARM BOOT + AUTOMATIC FAILURE RECOVERY MACHINE PASS / COLD OPEN**.
On the freshly identified v0.18/card, the requested default is now r11 Jume, with
ES-DE retained for this boot after a failed startup or session crash. The next
boot retries Jume. The sealed r11 archive and complete installed release passed
hash/seal checks; only the separate fallback overlay's r9 pin changed to r11.
Its installer, unit and session hooks are byte-identical to the reviewed sources.
Installed helper SHA256: `ad6ff7e57c46caaec7fbbe722ceb146496fa5b5bf5d5c25238292b4bc6c8cec2`.

Ready Home/IPC and `--enable` passed. Killing the identified Launcher GUI caused
exit 137, verified lease cleanup and automatic ES-DE start with no Jume restart.
A task-owned `/run` override forcing `ExecStartPre=/bin/false` independently
produced the same recovery; the exact override was removed before reboot.
Both paths preserved the persistent Jume default marker and ran a single frontend.

Warm reboot produced a new verified boot ID and automatically entered Jume Home;
ES-DE stayed inactive, and no trial marker or runtime fallback override survived.
The composed Home frame and IPC were inspected; full seal/preflight took about
44 seconds from the service start request. Normal stop cleaned all session
resources without invoking fallback, while Jume remained enabled for next boot.
The same 177 state files matched before, after reboot and after normal stop.
No failed units or detected kernel/storage/Panfrost/OOM faults remained in that boot.

The eight-file export was size/SHA-256 checked and extracted by fixed regular-file
allowlist. Evidence and exact receipts: `mainline/out/.cache/jume-r11-default-20261030.1pm7oq/`.
Task uploads, temporary failure configuration, target staging and poweroff timer
were removed. Existing releases/backups and prior named soak evidence remain.
After sync, UART confirmed `/roms` unmount, root read-only, device detachment and
`Powering off` at about **21:45 CST**; serial capture is closed. The device is off,
with **r11 enabled/default and the ES-DE fallback installed**. No commit/push.

This does not prove cold power-on, Weston-only loss with this overlay, interrupted
cleanup, GUI power actions, hung-process recovery, games/save-load or new physical
LCD/audio/control acceptance. No game or additional endurance run was started.

## User cold start and boot image — 2026-10-30

The user powered on again and initially saw the Linux login screen. Read-only
serial inspection found r11 already active/enabled with zero restarts; neither
ES-DE nor recovery had run. The user then confirmed Jume Home, with no agent
start/restart command. This closes one attended cold-start sample. Systemd
reported 60.946 seconds; Jume preparation/start occupied 45.251 seconds of it.
Evidence: `mainline/out/.cache/jume-r11-cold-start-20261030.gwXAXZ/`.

At the user's request, the separate [boot image](BOOT-SPLASH.md) now covers this
waiting interval. It preserves sealed release verification and the ES-DE fallback.
The owning runbook records its exact payload, boot handoff and UART-confirmed
cleanup. The user accepted the image; final terminal-flash verification was
deferred when the user requested wrap-up and commit. Startup latency is unchanged; this is not a percentage
progress meter or bootloader/kernel splash.

## Ownership and recovery

`jume-launcher.service` supervises the existing Wayland session and applications.
Without the [ES-DE fallback overlay](#optional-r11-es-de-fallback-overlay), Launcher,
Weston or seatd exit restarts the session, limited to three starts in 120 seconds
in sealed r9/r11. Serial login then remains the rescue route after restart
exhaustion; explicit rollback restores ES-DE. The installed overlay instead
returns to ES-DE on the first detected failure after verified cleanup.

Installed desktop/game/CPU-helper lifetimes have no diagnostic timer. Only exact
`jume-launcher.service/desktop` membership permits unlimited native gameplay;
bounded probes retain their timers. Both native guards now accept the browser
candidate's `/desktop` subgroup but reject `/browser` and unrelated/user slices.
This needs a **new Launcher ELF**, not just new scripts. Other input/save guards
remain enabled. Existing user state is not renamed or migrated.

After systemd kills all session children, `ExecStopPost` restores CPU/backlight
and the identified Mono mount. Failed cleanup retains its root-owned receipt
and refuses ES-DE restart. Power requests 77/78 run only after cleanup.
Installed session logs use the rate-limited journal, not files beside the bundle.

## Stage and activate

Build the paired handheld payload from clean committed source. Packaging includes
the service and product scripts; do not combine them with an old Launcher ELF.
Keep the kernel/rootfs unchanged; Browser and Files are optional verified bundles.

After authenticating and hashing the complete host artifact, stage over verified
Wi-Fi SSH into a new `/var/lib/jume-launcher/releases/<SHA256-of-SHA256SUMS>/`.
The installer does not unpack arbitrary archives. Seal all parents and runtime
files root-owned, not group/world writable, with release mode 0755. The manifest
covers every regular file; relative symlinks must resolve inside the release.
Extra files, devices, hardlinks and set-ID files fail. Exclude logs, credentials,
sockets and user state. The exact v0.15 kernel/p2 v0.18/card identity is required.
Manifest type/ownership and a 4 MiB size bound are checked before reading it.
Mutating installer operations hold one nonblocking filesystem lock; a concurrent
switch/rollback is refused. Read-only service verification does not take that
lock, avoiding a deadlock while the trial waits for startup.

The runtime bind stays `/run/r46h-wayland-probe`, preserving existing fixed paths.
Root-only Mono mounting is temporary. Session output is under
`/run/jume-launcher/session`; persistent state stays at
`/home/ark/.local/share/r46h-preview` without moving settings or saves.

Run as root with the reviewed release hash in place of `HASH`:

```sh
python3 /var/lib/jume-launcher/releases/HASH/product-install.py --install HASH
python3 /var/lib/jume-launcher/current/product-install.py --trial
# Only after independent trial acceptance:
python3 /var/lib/jume-launcher/current/product-install.py --enable
# Rescue, retaining all releases and user state:
python3 /var/lib/jume-launcher/current/product-install.py --rollback
```

- Install verifies the full manifest, refuses foreign units/selections, and
  installs an inactive service. ES-DE remains enabled.
- Trial starts Jume without changing the next cold-boot default. It is not
  timed: supervise the first trial with UART and an external health/time bound.
  Failed startup returns to ES-DE only after verified cleanup.
- Enable first enables Jume, then durably publishes its default marker. ES-DE's
  drop-in skips it only when that marker exists; a pre-marker interruption
  leaves the old frontend selected on reboot.
- Rollback removes the marker, stops/cleans Jume, resets failed state, disables its autostart and
  starts ES-DE. It never deletes a runtime, preference or save.
- Install is first-install only; it never replaces a different selection.

## Inactive version selection

r8/r9 support `--select FROM TO`; use r9 for corrected failed-state rollback.
r6/r7's bundled installers do not support selection.
Stage and `sync` the complete successor first. Invoke its reviewed installer by the fixed release
path, including when switching back (the older installer lacks this command):

```sh
python3 /var/lib/jume-launcher/releases/NEW/product-install.py --rollback
python3 /var/lib/jume-launcher/releases/NEW/product-install.py --select OLD NEW
python3 /var/lib/jume-launcher/current/product-install.py --trial
# Return to the prior release after stopping the new trial:
python3 /var/lib/jume-launcher/releases/NEW/product-install.py --rollback
python3 /var/lib/jume-launcher/releases/NEW/product-install.py --select NEW OLD
```

Replace OLD/NEW with the respective manifest hashes. Selection requires Jume
inactive and disabled, ES-DE active/enabled, no default/trial marker and no
session/lease/cleanup receipts. Both complete seals, identical service definitions
and unchanged sealed installed integration are required. Only `current` is
atomically replaced and its parent synced; services, releases and user state
are untouched. Service/schema migrations and online updates are not supported.
After an interruption, retry the same FROM/TO: either complete release remains
selected. A matching owned pending link can be reused; foreign pending paths
are retained and refused, never deleted. Inspect identity before retrying.
Host fixtures cover both interruption sides, reverse selection and refusal gates.
Same-service r6/r8 device cycling and unchanged user files pass; actual power-loss
recovery remains open and is not established by host filesystem mocks.

## Optional r11 ES-DE fallback overlay

**2026-10-30: r11 adaptation.** The requested policy is Jume at boot, then ES-DE
after a failed startup or session crash, with Jume selected again on the next
boot. The r11 archive/manifest and unchanged installer/service hooks were checked
before replacing the old r9 pin. This is an opt-in configuration, not full
game-library, save/load or endurance acceptance. See the [activation result](#r11-default-activation--2026-10-30).

[`product-fallback.py`](product-fallback.py) installs a separate helper/service
and a Jume drop-in. It pins the installed r11 manifest and recovery-script hash,
reuses its target, lock, file-seal and cleanup checks, and never edits its sealed
release or user state. `Restart=no` and `OnFailure=` replace the three Jume
restart attempts with one ES-DE handoff. The service runs after Jume's original
`ExecStopPost` cleanup; any retained lease/mount/socket refuses recovery. A mutual
exclusion prevents both frontends from running together.

After verified cleanup, the helper adds only a `/run/systemd/system/` override
to clear ES-DE's known Jume-default condition, reloads systemd and starts ES-DE.
The persistent Jume enable marker is unchanged; `/run` clears at reboot. Foreign
conditions/configuration are refused rather than overwritten. Jume's failed state
and journal remain available for diagnosis. Ordinary stop and GUI reboot/poweroff
do not invoke `OnFailure`; a hung process or successful exit is not a detected crash.
This ordering follows the upstream [OnFailure](https://www.freedesktop.org/software/systemd/man/latest/systemd.unit.html#OnFailure=)
and [ExecStopPost](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html#ExecStopPost=) contracts.

Deploy only after rediscovering the exact v0.18 device and opening serial. Transfer
the reviewed script to a root-owned staging path, compare its host/target SHA-256,
and run as root. `STAGED_SCRIPT` below is that verified path, not a bundled release file:

```sh
python3 -B /var/lib/jume-launcher/current/product-install.py --rollback
python3 -B "$STAGED_SCRIPT" --install
python3 -B /var/lib/jume-launcher/current/product-install.py --trial
# Observe ready Home, then apply the user's requested boot default:
python3 -B /var/lib/jume-launcher/current/product-install.py --enable
```

Installation alone does not promote Jume. It requires inactive/disabled r11,
active/enabled ES-DE and a complete r11 seal. Matching completed files allow an
idempotent retry. Foreign files or interrupted `.incoming` writes are retained
and refused; inspect them before retrying. This is not power-loss recovery proof.
Before selecting another release, remove the optional [boot image](BOOT-SPLASH.md) if installed,
then explicitly roll back and remove this recovery overlay:

```sh
python3 -B /var/lib/jume-launcher/current/product-install.py --rollback
python3 -B /var/lib/jume-launcher/esde-fallback.py --remove
```

`test-jume-fallback.py` exercises current-boot recovery, unchanged default/save
bytes, cleanup/foreign-config/active-session/lock refusal, install retry, removal
and ES-DE start errors. It uses fake systemd calls, not a live service manager.
Ready Home, failed startup, Launcher loss, default warm boot and normal stop
and one attended cold start now pass on r11. Weston loss with this overlay,
held-lease recovery and GUI power actions remain separate device gates. Preserve the installed
overlay and recovery evidence; GUI/input/save/gameplay-endurance gates stay open.

## Next combined target gate

1. Use the [r11 fallback overlay](#optional-r11-es-de-fallback-overlay) for Q1.
   Keep installed r11 and retained releases; packaged failed-state rollback and
   bidirectional selection pass. Receipt-mismatch cleanup refusal/recovery passes;
   actual interrupted lease cleanup remains open. Use the fixed-path r11 controller.
   Optional Browser pairing needs its guarded wrapper and a new complete seal.
2. Broader Q2 acceptance: settings/saves, input ownership and representative native/browser
   launches/rollback under sustained load. The r11 desktop/light-navigation two-hour run above
   passes; do not repeat it unchanged or count it as gameplay endurance. Longer game tests need
   guards and transport lifetimes covering the full run, not the old 45-minute guard.
3. Individual Launcher/Weston/seatd recovery and old-child/lease cleanup pass;
   fast prepare-failure limiting and explicit rescue now pass on r6's identical unit.
   GUI warm reboot passes; test GUI poweroff and interrupted cleanup on target.
4. Q1 default activation, one attended cold start and automatic ES-DE return pass;
   retain the fallback and observe broader reliability separately. Wi-Fi/settings/save retention and gameplay
   endurance remain Q2 gates; schema/service migrations remain unsupported.
5. L1: inventory actual ES-DE systems/ROM entries against Jume before Q2 removal;
   fixed Neo/native entries are not a full ROM scanner. Keep unsupported routes.

Physical LCD/audio/controls, save retention and library coverage remain gates.
Heavy websites, zram and real suspend need not block the first desktop trial.
