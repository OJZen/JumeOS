# Jume default-desktop candidate

Status: **source/host candidate only; not installed or accepted on R46H**.
This is the first Q1 step, not permission to remove ES-DE. ARM64 packaging and
target systemd/boot proof remain open. Docker is used only temporarily for builds.

Host checks: installation/recovery fixtures pass on macOS and Linux/Python 3.13;
adjacent lease/probe guards pass. Linux checks use the packaged worker path,
independent of checkout depth, and nonrecursive filesystem-stat mocks;
macOS Qt 6.8.2 `tools-check` rebuilt and passed 10 checks including actual Qt
cgroup-pattern matching. This is not a Linux/ARM64 product build. Receipt:
`mainline/out/.cache/jume-product-20260927.md`.
The builder verifies the complete payload with the installer's seal checks.
Remote tests use an anonymous Linux disk volume, removed with the container:
the payload exceeds the 192 MiB `/run` tmpfs, and macOS binds do not retain test UIDs.
Build caches, final artifacts and evidence stay on the external workspace.

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

1. Build the paired ARM64 payload when Linux resources are available; keep the
   host's Docker low-memory restriction. Host contracts alone cannot deploy this.
2. Supervised trial: ready Home, settings/saves, input ownership, representative
   native/browser launches and rollback. Test beyond the old 120/290/360-second
   bounds and separately beyond the former two-hour CPU-helper limit.
3. Kill Launcher, Weston and seatd separately; prove fresh-session recovery,
   old-child/lease cleanup, bounded crash-loop stop and no ES-DE dependency.
   Test GUI power actions and interrupted prepare/cleanup on target.
4. After trial/save acceptance, enable and verify cold boot, Wi-Fi/settings/save
   retention and serial rollback. Then conduct endurance and a genuine upgrade cycle.
5. Inventory actual ES-DE systems/ROM entries against Jume before removal;
   fixed Neo/native entries are not a full ROM scanner. Keep unsupported routes.

Physical LCD/audio/controls, save retention and library coverage remain gates.
Heavy websites, zram and real suspend need not block the first desktop trial.
