# Temporary R46H settings

R79 Launcher/status/About and recovery: **HOST + DEVICE COMPOSED PASS / PHYSICAL LCD + PROMOTION OPEN**.
R35 status values remain **HOST + DEVICE READBACK PASS**; revision 17 device controls remain
**HOST + DEVICE SCOPE PASS / FOCUS PACING OPEN**.
The scene/auto-screen-off policy is **TARGET + ATTENDED WAKE PASS / POWER DRAW + STANDBY OPEN**.
The [project checkpoint](../../docs/PROJECT-CONTEXT.md) owns the next session;
the [performance/power plan](../../docs/PERFORMANCE-POWER.md) owns product scope.
The frozen package, source and checks live in
`mainline/out/.cache/r46h-hud-qos-20260909/receipt.json`; R16 and prior fallbacks remain retained.

## Readback and control boundary

`DeviceState` enables Linux reads only after checking the accepted kernel,
root UUID, card CID and geometry. It samples every two seconds: aggregate CPU,
CPU policies, available memory/swap, PSI, temperature, GPU frequency when
unambiguous, backlight, battery percentage/status, NetworkManager's cached active-AP signal
and voltage/supply. R35's desktop status area shows
Wi-Fi quality as 0–100% plus battery percentage and charging/discharging state.
Missing metrics stay unavailable. This small health sampler continues while the
HUD is hidden; the existing process/HUD sampler retains its visibility lifecycle.
Reported charging state is not proof of net charging or calibrated capacity.
The storage page reads capacity, filesystem and read-only state for `/`, `/roms`
and `/boot` on entry/refresh. An absent mount is unavailable rather than borrowing
its parent filesystem's capacity. These are read-only queries, not storage repair.
The remote response exports an explicit numeric metric allowlist with sample age;
it includes neither filesystem paths nor network/profile names.

Ordinary previews are read-only on R46H. Device brightness and idle dimming
require the explicit lease below; a black UI mask is only a host preview.
Volume uses the accepted physical keys, avoiding a second writer competing with
the installed volume service. No mixer policy changes here.

The top-center volume capsule listens to atomic updates of
`/var/lib/r46h-volume/level` through `QFileSystemWatcher`; it does not wait for
the two-second health sampler. It shows the safe 0–201 range as a percentage,
with a mute icon at zero, then hides 1.8 seconds after the last update. Repeated
presses at either limit renew the timeout without hiding/reopening the overlay.
Startup readback and unrelated temporary files are silent. The capsule does not
take focus or open the quick panel. Games/browser use the shared compositor's
overlay path; deploy the launcher and compositor together, not a launcher-only
replacement. ES-DE and standalone applications outside Jume are not covered.
2026-09-22 ARM64 host checks cover atomic replacement/recreation, invalid values,
timeout renewal, editor focus, 100%/120% font layout and Pixman/GL composed
clipping. Evidence: `mainline/out/.cache/r46h-volume-hud-20260922/`.
The paired binaries ran during the Transfer batch; physical volume-key/LCD and
in-game overlay acceptance remain open (not exercised by that batch).

With a lease, brightness writes the fixed backlight node and reads it back.
Idle dimming saves the current raw value, quarters it, and restores it on the
first wake action. CPU presets preserve the original limits; custom governor,
minimum and maximum use the sampled supported values. Writes preserve min ≤ max,
read back, and attempt rollback on failure. Failed rollback disables controls.
Manual CPU changes require external supply, known voltage/temperature and no low-voltage
or thermal warning. The backend warns near kernel protection limits; automatic
low-battery shutdown and calibrated battery percentage remain unimplemented.

The transient power candidate adds automatic `schedutil` scene caps:
desktop 816, foreground app 1008 and screen-off 600 MHz, always bounded by the
original session maximum. Battery operation is permitted for these downward
caps only when voltage, supply and temperature are known and safe; manual CPU
tuning retains its AC gate in a root-owned helper. CPU sysfs nodes remain
root-owned and readable by ark, but writable only by root; the temporary socket accepts only fixed scenes or validated AC
manual requests. A failed scene change disables automatic mode and reports an error.
The leased backlight can be set to zero and restores
the pre-dim value on the first wake input. The automatic timeout defaults to
five minutes, is configurable/off, and is inhibited while a foreground app,
text entry, simulated session or controller test is active. It does not suspend
the kernel or stop background transfers. The 2026-09-23 temporary v0.18 device
run read back desktop/off caps (816/600 MHz), a helper-requested game cap
(1008 MHz), and backlight 80 -> 0 -> 80 for both immediate and one-minute
automatic screen-off. The first routed Down only woke the screen; Settings
focus stayed on the same row. Ark could read CPU frequency but its direct
sysfs write was denied. The initial root:0600 CPU lease blocked the launcher
read and was corrected to root:0644 before these checks. Stopping the transient
unit restored the original 600--1296 MHz range, backlight and permissions;
ES-DE/input/volume services resumed with no failed units or kernel errors. The
staged runtime was removed and UART confirmed clean poweroff. Evidence:
`mainline/out/.cache/r46h-power-device-20260923.1DqmS3/`.
On 2026-09-26 the operator accepted one-minute physical screen-off, immediate
first-Down wake and unchanged Settings focus on both AC and battery. Volume+
woke the screen; both volume keys showed an unclipped top-center HUD with timed
dismissal. Battery samples confirmed online=0, backlight 80 -> 0 -> 80 and caps
816 -> 600 -> 816 MHz; a manual CPU request was rejected as `unsafe_supply`.
Charging was reconnected and first-stage exit restored all leases and services.
Evidence: `mainline/out/.cache/r46h-attended-20260926.3Iyp3b/session.md`.
These short battery samples do not prove calibrated power savings, sustained
residency or long standby. Kernel suspend stays disabled; shared-app acceptance
and persistent integration remain separate gates.

The 2026-09-09 R16 device run proved remote navigation/captures, storage readback,
performance governor and a 1200 MHz custom upper limit. The operator confirmed
real backlight adjustment. Restoring the upper limit exposed deferred CPUFreq QoS:
the immediate read stayed at 1200000, then read 1296000 after 50 ms. R17 allows
up to 100 ms for bound readback; lease cleanup also waits briefly. Thermal limits
remain enforced. The R17 remote session exposes the new metrics. The operator accepted Y/START
and same-row keyboard wrapping; the HUD is visible but needs a narrower layout.
R17 subsequently passed GUI 1296 → 1200 → 1296 MHz with serial readback.
The lease restored original values and root-only write permissions before ES-DE
recovery. The operator accepted 30-second real dimming and first-key wake without
selection movement. Temporary state was removed and UART confirmed poweroff.
The subsequent 510 → 360 px hardware HUD width adjustment is host-checked only.

The 2026-09-12 R35 device run matched the status display to NetworkManager's
cached signal and battery sysfs percentage/status. This proves the shown values
for that session, not Wi-Fi connection management or calibrated battery policy.
R56 gives both status icons one 18 px box and shared centerline, uses theme gaps,
and matches the clock to caption text. Its R46H Weston capture shows the Wi-Fi,
battery and clock row aligned in composed output. This does not independently
prove the physical LCD or revalidate the R35 status-value sources.
R79 repeated that row on p2 v0.18 with live `97%` discharge state and captured the
About page's `Jume Launcher`, `0.1.0-dev` and project URL. Normal expiry and forced
input-router failure both restored ES-DE and removed transient leases. This is
composed/machine evidence; physical readability, L3+R3 and promotion remain open.

The hardware HUD now shows available/total RAM, `soc-thermal` chip temperature,
current/effective upper CPU frequency and CPU/GPU cooling-device activity. Missing
sensors remain unknown. These are shared chip/kernel readings, not per-core
thermometers; low frequency alone does not prove thermal throttling.

## Bounded run and recovery

Use the [normal staging/preflight](README.md#prepare-an-attended-device-run)
and the receipt's shell executable hash, then choose one mode:

```sh
/run/r46h-shell-probe/probe-r46h.sh --device SHELL_SHA256
# Or the same fresh public key, serial-verified host key and addresses as --remote:
/run/r46h-shell-probe/probe-r46h.sh --remote-device SHELL_SHA256 PUBLIC_KEY_SHA256 DEVICE_IP MAC_IP
```

These are placeholders, not known device addresses. Follow the
[remote transport procedure](../../docs/REMOTE-CONTROL.md#temporary-r46h-ssh-session).
The remote mode requires external supply; local device controls can run on
battery for the guarded automatic policy. Both require the exact accepted identity. The probe
seals executable files as root-owned, leaves only private state writable by ark,
and grants ark access only to the fixed backlight node through `device-lease.sh`.
The root-only CPU helper checks each requested operation and is stopped before
lease restoration; the launcher and other `ark` processes cannot write CPU sysfs directly.
An existing lease is refused. Values, ownership and permissions are recorded in
root-only `/run/r46h-device-lease`, bound to the current boot. The newer helper also
records its transient unit; automatic acquire/restore passes that unit and refuses
another session's lease. The one-argument restore remains an explicit root recovery
command, including for retained older receipts.

The transient unit's `ExecStopPost` restores values and permissions even after
GUI/probe failure. The outer probe checks restoration again before restarting
ES-DE. A failed restore retains its receipt and leaves the frontend stopped:
inspect serial, correct the failure, then rerun `device-lease.sh --restore`.
Do not delete a failed lease. Reboot also ends the sysfs permission lease.

The local mode lasts 290 seconds inside a 300-second unit; remote mode has the
existing 30/31-minute limits. GUI power dialogs default to Cancel. Confirming
saves preferences and returns 77 (poweroff) or 78 (reboot); only the outer
device-mode supervisor restores the lease, syncs, then requests the system action.
An ordinary preview cannot power off the host. R17 transient-unit value/permission
restoration passed on device. In the later 2026-09-09 power-menu session, the
operator confirmed default Cancel and a GUI-triggered reboot back to ES-DE.
After reboot, remote UI actions confirmed default Cancel for poweroff, then
selected poweroff. Both paths logged successful lease restoration before the
system action; UART confirmed final filesystem detach and poweroff. Final LCD/
indicator state was not separately observed. Suspend and low-battery policy remain
open. Evidence: `mainline/out/.cache/r46h-power-attended.cpxchdlb/session.json`.
Its temporary SSH transfer accepted only the fresh test key and Mac address;
transfer/reboot caches, listeners and private test state were removed.

## Shared Wayland settings candidate

The [handheld supervisor](../gaming-wayland/HANDHELD.md) accepts the same explicit
`R46H_DEVICE_CONTROLS=1` opt-in for its `handheld` profile. Use it for both preflight
and execution, with the frozen package manifest hash:

```sh
R46H_DEVICE_CONTROLS=1 /run/r46h-wayland-probe/probe-r46h.sh --check MANIFEST_SHA256 handheld
R46H_DEVICE_CONTROLS=1 /run/r46h-wayland-probe/probe-r46h.sh --run MANIFEST_SHA256 handheld
# The same environment also applies to the documented --remote form.
```

The existing identity/file/lease guards are required; manual CPU tuning and
remote-shell probes still require external power. Omit the
opt-in for read-only settings. The existing persistent-state option can enable
native ports simultaneously. One `session-leases.sh` hook acquires device and port
leases; restoration attempts both even if one fails. Only successful cleanup and
seat-socket recovery permit ES-DE return or a GUI-requested power action. The GUI
retains its brightness, dim/wake, CPU and Cancel-first power controls; application
children do not inherit its device-control environment flag.

Host fixtures passed ownership, both restoration attempts, power gating and existing
CPU/backlight checks. Packaged wrappers passed the GUI's 77/78 exit-code
path without powering off the host. Shared R46H sysfs/cgroup and physical use still
need acceptance; R17's existing physical result does not cover this new supervisor.

R27 is frozen at `mainline/out/.cache/r46h-compositor-20260910/r27/receipt.json`,
source `7cb57078264e13a3e292e0e0c2a54e6312d18ea1` on
`codex/r46h-shared-device-r27-candidate`. Its 33,661,896-byte archive expands to
92,940,685 regular-file bytes; complete manifest/archive readback passed. The
combined build also passed shared desktop/input/frame checks, unprivileged sessions,
Moonlight management and authenticated SSH control. The unchanged TF base and
accepted R17 remain the physical fallback; no R27 device operation has occurred.

## Wi-Fi management

`NetworkState` asynchronously lists saved profiles and scans nearby networks with
nmcli. It never requests saved secrets. Scan output is bounded to 64 KiB/256 APs,
validates UTF-8, fields and identifiers, and groups matching SSID/security/interface
entries by strongest signal. Hidden/non-text SSIDs, WEP, enterprise and WPA3/mixed
setup are outside this first entry flow; existing saved profiles remain usable.

Select **Add Wi-Fi**, choose a visible open or WPA/WPA2-personal network, then
enter its password when required. The password field masks text, disables
prediction/automatic capitalization, and uses Latin input. B cancels and clears
the field. Confirmation sends a local D-Bus request, then clears the field;
the production bus address is fixed to `/run/dbus/system_bus_socket`.
passwords never become process arguments, application files, captures or numeric
exports. Printable ASCII passphrases of 8–63 characters and 64-digit hexadecimal
PSKs are accepted. No claim is made that Qt erases every temporary memory copy.

Before activation the adapter rereads the selected AP's raw SSID, BSSID, mode and
security flags. It rejects changed/unsupported identity instead of changing the
connection target. It then uses
[AddAndActivateConnection2](https://networkmanager.dev/docs/api/latest/gdbus-org.freedesktop.NetworkManager.html#gdbus-method-org-freedesktop-NetworkManager.AddAndActivateConnection2)
and tracks the active connection's state; accepting a request is not connection
success. The overall deadline is 40 seconds, with five-second individual bus calls.
Timeout reports an unknown outcome and does not retry. Closing the UI does not
undo a request already sent to NetworkManager; refresh through UI/serial afterward.

**Remember new network** defaults off: the new profile is volatile, has no
autoconnect, and NetworkManager removes it when disconnected. Enabling the switch
explicitly requests a disk profile and autoconnect, including NetworkManager's
normal secret storage. New connections create profiles, not edits to old ones.
A failed remembered connection can leave a saved profile; remove it through
**Forget network** if unwanted. Forgetting confirms the selected UUID before
deleting it and may disconnect an active connection. Existing-profile activation
also uses UUID; disconnect requires exactly one active Wi-Fi.

The adapter uses the bundled Qt DBus library. Host checks use an isolated bus and
fake NetworkManager, including real message serialization, state signals, denial,
timeout and changed-AP refusal. The deployed v0.17 image omits `polkitd`, so ark's direct
NetworkManager control is denied even though root reconnect, autoconnect and DHCP
already pass. A temporary target test installed Debian's polkit packages and an
ark-only rule for exactly `network-control`, `settings.modify.system` and
`wifi.scan`. Ark then rescanned, created/deleted an isolated profile, disconnected
and reactivated the saved profile, retained its address and reached the gateway;
all unrelated NetworkManager permissions stayed denied. The exact packages and
`49-r46h-network.rules` are now integrated in the byte-reproducible
[v0.18 host artifact](../rootfs-debian13-gaming-v18/README.md), without broadening
the rule. It is not deployed; media proof, new-password AddAndActivateConnection2
and reboot persistence still require acceptance.
The [test index](../tests/README.md#current-review-gaps) records the Mac window-
activation limitation separately from the passing offscreen/ARM64 checks.

Switching/disconnecting Wi-Fi can cut the remote session. Keep serial available
and perform that step after navigation/capture checks; reconnect through the
physical UI or serial. Never disable SSH host-key verification to recover.

The exact board has no onboard Bluetooth controller: boot reports `BT=0`, rfkill
exposes only Wi-Fi, `/sys/class/bluetooth` is empty, USB has no controller and the
board DTS has no Bluetooth node. The launcher therefore exposes no Bluetooth
category or pairing placeholder.

## Memory control

`memory-control.sh` is the single guarded implementation for the product zram
service and operator experiments. The UI reports memory state. `--check` only
reads; other modes require root, exact device/storage identity and no active
game/stream. Disk-swap changes additionally require external power.

```sh
/run/r46h-shell-probe/memory-control.sh --check
/run/r46h-shell-probe/memory-control.sh --disk 256
/run/r46h-shell-probe/memory-control.sh --disk-off
/run/r46h-shell-probe/memory-control.sh --zram 256 lz4
/run/r46h-shell-probe/memory-control.sh --zram-off
```

Sizes are 64–2048 MiB and at most twice RAM. Disk swap uses only the owned ext4
file `/var/lib/r46h-memory/swapfile`, keeps 512 MiB disk reserve and checks its
inode/size/permissions before reuse or deletion. Resize requires explicit off.
zram uses only an inactive, uninitialized zram0 and available LZ4/Zstd; its owner
record is bound to the boot/device generation. Swapoff requires available RAM
above used swap plus max(128 MiB, RAM/8); failure retains the active configuration.
Disk priority is 10, zram 100. There is no fstab or automatic disk swap.
`r46h-zram.service` enables exactly 256 MiB LZ4 only on the exact v0.19 product
kernel and treats an already-owned matching device as success. It has no automatic
stop path because shutdown-time swapoff can fail under pressure. Disk-off removes
the owned file; temporary settings must be disabled and checked before cleanup.

The isolated `codex/r46h-zram-candidate-v1` commit `2b89c5d` built
`6.12.99-r46h-mainline-v0.18-zram-candidate`; its source/config/metadata and verified
archive remain in `mainline/out/.cache/r46h-unattended-20260909/zram-candidate/`.
It adds modular zram and LZ4/Zstd, without writeback or zswap. A one-shot serial
boot used its Image/modules with the accepted v0.17 DTB and unchanged U-Boot
environment. A guarded 256 MiB LZ4 device reached 43.5 MiB swap use under bounded
650 MiB zero plus 32 MiB random pressure, then `--zram-off` reset its size and the
module unloaded. The run peaked at 72.083 C and logged no OOM, ext4, data-invalid
or GPU fault. Normal v0.15 boot, services and boot-file hashes were restored and
candidate target files were removed. The same bounded configuration now lives
in the v0.19 product source; its build, persistent activation and real-game
benefit remain open. **Use only its Image/modules with the
accepted v0.17 DTB and existing boot fallback.** The generic archive's boot.ini
and DTB are not the accepted card configuration; do not rewrite the TF base. This
Qt adapter intentionally still accepts only the accepted kernel.

## Combined acceptance route

Keep the device off during host preparation. One attended batch can cover the
following sequence; most navigation, capture and readback is agent-operated.
The batch starts with the exact [p2 v0.18](../rootfs-debian13-gaming-v18/README.md)
media write, so the TF card must be available before power-on. Rediscover media,
serial and host-key identity first; keep external supply connected. Freeze the
[R79 handheld package](../gaming-wayland/HANDHELD.md#resume-and-rebuild) and
[R45 direct Stardew fallback](../gaming-ports/README.md#r45-stardew-gallium-preload),
with p2 v0.17 and ES-DE ready for recovery.

| Route | Agent checks | Operator observations |
| --- | --- | --- |
| v0.18 media and cold identity | Fixed-profile p2 write/readback, cold identity, exact package/rule hashes, service health and unrelated-action denial | Card handling and normal boot observation |
| R79 transient desktop baseline | Target manifest/preflight, Home/About/status and clean/forced recovery pass; finish 100%/120% fonts, settings/storage and physical L3+R3 | LCD layout/motion, readability and physical shortcut feel |
| PortMaster lifecycle | Offline refresh recovery passes with zero entries; finish live refresh plus install/update/remove one bounded test port and prove retained user data | Confirm progress/error readability if requested |
| Local lifecycle and retained state | Metal Slug launch/menu/exit and GTA III/Vice City startup/exit pass by remote control; finish retained slot load, broader GTA play and save/relaunch hashes | Picture, audio and physical controls; confirm expected loaded state |
| Stardew direct then shared | R45 start/load/save/exit/relaunch with source/backup hashes preserved; revisit R79 shared state only with a new source hypothesis | Direct-path picture, audio, controls and loaded farm; report whether a changed shared path creates a window |
| Network, reboot and recovery | Forced-child recovery, repeated transient expiry and ES-DE fallback pass; finish Wi-Fi create/reconnect/forget, warm-reboot persistence and bounded log/cache growth | Enter secrets only on the handheld and confirm expected network choice |

Run each changed path once; repeat only after a relevant failure/fix. A denied
permission, thermal/voltage warning or missing capability remains an explicit
open item, not an excuse to bypass the guard. Cool between game bounds and stop
at the existing 85 C external abort. Moonlight, zram-kernel promotion, USB HID
and suspend/resume are intentionally outside this batch: each is deferred or
lacks a changed hypothesis.
Keep machine receipts separate from the operator's LCD/audio observations.
End with restored settings, health checks, sync and serial-confirmed poweroff.
