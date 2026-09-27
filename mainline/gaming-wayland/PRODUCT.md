# Jume default-desktop candidate

Status: **ARM64 host + supervised installed-session device trial passed; default promotion open**.
This is the first Q1 step, not permission to remove ES-DE. The clean-source
candidate is from `0ca4f27`, under `mainline/out/.cache/jume-product-arm64-20260927-r6/`.
Its `receipt.json` records source, archive and evidence hashes; all were rechecked.
Qt checks (10 tools + 13 shell), desktop/tasks, PortMaster, packaged session/power
exits and full installer seal passed. Fresh-container SSH passed twice with the
same final ELF. macOS/Linux installation and memory-policy contracts pass too.
Host checks alone do not prove installed systemd, DRM/seatd or cold boot. Build record:
`mainline/out/.cache/jume-product-20260927.md`.
This artifact includes Files/Terminal/native ports, not Browser or Moonlight.
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
the sealed payload untouched. **Rebuild the sealed package before the next trial;
the retained r6 installer's first-start bug is not fixed inside that artifact.**

Launcher (with Files active), Weston and seatd were killed separately. Each
cleaned old children/leases and produced a new IPC generation and composed Home
frame without starting ES-DE. Full validation adds roughly 40 seconds per restart.
One desktop survived 460 seconds; GTA III survived 273 seconds, accepted two
routed B presses and produced an intro frame with positive recent submissions.
The explicit End Game action cleared its group and returned to the same desktop;
this was requested SIGTERM cleanup, not proof of engine exit 0 or save flushing.
Files capture privacy also passed. CPU-helper RuntimeMaxUSec is infinity;
actual two-hour endurance, crash-loop exhaustion and interrupted cleanup remain open.
Explicit rollback restored ES-DE/input/volume and CPU/backlight, with no failed
units or kernel errors. All 164 prior files remained present; the existing save
hash was unchanged. The inactive sealed release and root-private pre-trial backup
remain installed; task staging/SSH/guard/keys were removed. UART confirmed clean
poweroff. These are machine observations, not operator LCD/audio/save-load acceptance.
Evidence: `mainline/out/.cache/jume-product-device-20260927.hB4f8e/session.md`.

## Ownership and recovery

`jume-launcher.service` supervises the existing Wayland session and applications.
Launcher, Weston or seatd exit restarts the session, limited to three starts in
120 seconds. No crash recovery branch launches ES-DE. Serial login remains the
rescue route after restart exhaustion; explicit rollback restores ES-DE.

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
- Rollback removes the marker, stops/cleans Jume, disables its autostart and
  starts ES-DE. It never deletes a runtime, preference or save.
- First installation only: switching an existing selection to a different
  release is refused. Genuine version-to-version upgrade/rollback remains open.

## Next combined target gate

1. Rebuild/verify the corrected installer package before another trial. Optional Browser pairing needs
   the current guarded wrapper and a newly verified complete manifest; do not
   copy the old unguarded browser wrapper into an installed release.
2. Supervised trial: ready Home, settings/saves, input ownership, representative
   native/browser launches and rollback. Test beyond the old 120/290/360-second
   bounds and separately beyond the former two-hour CPU-helper limit.
3. Individual Launcher/Weston/seatd recovery and old-child/lease cleanup pass;
   prove bounded crash-loop stop and no ES-DE dependency after exhaustion.
   Test GUI power actions and interrupted prepare/cleanup on target.
4. After trial/save acceptance, enable and verify cold boot, Wi-Fi/settings/save
   retention and serial rollback. Then conduct endurance and a genuine upgrade cycle.
5. Inventory actual ES-DE systems/ROM entries against Jume before removal;
   fixed Neo/native entries are not a full ROM scanner. Keep unsupported routes.

Physical LCD/audio/controls, save retention and library coverage remain gates.
Heavy websites, zram and real suspend need not block the first desktop trial.
