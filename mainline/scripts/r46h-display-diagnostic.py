#!/usr/bin/env python3
"""Run one controlled display-path test on an explicitly supported R46H kernel.

The script is intentionally version-gated and has no boot-time integration.  It
stops (but never disables) the legacy display services, refuses to continue
while another userspace process owns a DRM/fbdev descriptor, records the DRM
state on stdout, then either writes one visible framebuffer pattern or requests
the DSI host's built-in video pattern generator for a bounded observation
window.  Framebuffer state and every software-visible temporary flag are
verified and restored; the DSI debugfs ABI does not expose hardware readback.

It does not modify BOOT, the module tree, systemd unit files, or the GPU render
node.  It keeps the original framebuffer snapshot in memory and restores that
snapshot, the active VT mode, and every service that was active before the run.
"""

from __future__ import print_function

import argparse
import array
import ctypes
import datetime
import errno
import fcntl
import hashlib
import os
import platform
import signal
import stat
import subprocess
import sys
import time


SUPPORTED_RELEASES = (
    "6.12.99-r46h-mainline-v0.4-dsi396",
    "6.12.99-r46h-mainline-v0.5-ldo7",
    "6.12.99-r46h-mainline-v0.6-ldo7",
    "6.12.99-r46h-mainline-v0.7-host-timers",
    "6.12.99-r46h-mainline-v0.8-bootloader-handoff",
)
FBIOGET_VSCREENINFO = 0x4600
FBIOGET_FSCREENINFO = 0x4602
FB_TYPE_PACKED_PIXELS = 0
FB_VISUAL_TRUECOLOR = 2
DISPLAY_UNITS = ("emulationstation.service", "mpv.service")
DISPLAY_PROCESS_NAMES = frozenset(
    ("emulationstation", "mpv", "mpv_sense", "plymouth", "plymouthd")
)
DISPLAY_DEVICE_PREFIXES = ("/dev/dri/",)
DISPLAY_DEVICE_PATHS = frozenset(("/dev/fb0",))
HOST_VPG_PATH = "/sys/kernel/debug/ff450000.dsi/vpg"
HOST_VPG_HORIZONTAL_PATH = "/sys/kernel/debug/ff450000.dsi/vpg_horizontal"
HOST_VPG_BER_PATH = "/sys/kernel/debug/ff450000.dsi/vpg_ber_pattern"
MIN_BATTERY_VOLTAGE_NOW_UV = 3600000
MIN_BATTERY_VOLTAGE_AVG_UV = 3700000
MAX_BATTERY_VOLTAGE_UV = 4500000
BATTERY_RECHECK_INTERVAL_SECONDS = 30
KDSETMODE = 0x4B3A
KDGETMODE = 0x4B3B
KD_TEXT = 0x00
KD_GRAPHICS = 0x01
SYSTEM_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
RECEIVED_SIGNALS = set()
CLEANUP_ACTIVE = False


class DiagnosticError(RuntimeError):
    pass


class FbBitfield(ctypes.Structure):
    _fields_ = [
        ("offset", ctypes.c_uint32),
        ("length", ctypes.c_uint32),
        ("msb_right", ctypes.c_uint32),
    ]


class FbVarScreeninfo(ctypes.Structure):
    _fields_ = [
        ("xres", ctypes.c_uint32),
        ("yres", ctypes.c_uint32),
        ("xres_virtual", ctypes.c_uint32),
        ("yres_virtual", ctypes.c_uint32),
        ("xoffset", ctypes.c_uint32),
        ("yoffset", ctypes.c_uint32),
        ("bits_per_pixel", ctypes.c_uint32),
        ("grayscale", ctypes.c_uint32),
        ("red", FbBitfield),
        ("green", FbBitfield),
        ("blue", FbBitfield),
        ("transp", FbBitfield),
        ("nonstd", ctypes.c_uint32),
        ("activate", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("width", ctypes.c_uint32),
        ("accel_flags", ctypes.c_uint32),
        ("pixclock", ctypes.c_uint32),
        ("left_margin", ctypes.c_uint32),
        ("right_margin", ctypes.c_uint32),
        ("upper_margin", ctypes.c_uint32),
        ("lower_margin", ctypes.c_uint32),
        ("hsync_len", ctypes.c_uint32),
        ("vsync_len", ctypes.c_uint32),
        ("sync", ctypes.c_uint32),
        ("vmode", ctypes.c_uint32),
        ("rotate", ctypes.c_uint32),
        ("colorspace", ctypes.c_uint32),
        ("reserved", ctypes.c_uint32 * 4),
    ]


class FbFixScreeninfo(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_char * 16),
        ("smem_start", ctypes.c_ulong),
        ("smem_len", ctypes.c_uint32),
        ("type", ctypes.c_uint32),
        ("type_aux", ctypes.c_uint32),
        ("visual", ctypes.c_uint32),
        ("xpanstep", ctypes.c_uint16),
        ("ypanstep", ctypes.c_uint16),
        ("ywrapstep", ctypes.c_uint16),
        ("line_length", ctypes.c_uint32),
        ("mmio_start", ctypes.c_ulong),
        ("mmio_len", ctypes.c_uint32),
        ("accel", ctypes.c_uint32),
        ("capabilities", ctypes.c_uint16),
        ("reserved", ctypes.c_uint16 * 2),
    ]


def fail(message):
    raise DiagnosticError(message)


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def read_text(path):
    return read_bytes(path).decode("utf-8", "replace").rstrip("\x00\n")


def utc_now():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def signal_list_text():
    return ",".join(str(item) for item in sorted(RECEIVED_SIGNALS.copy()))


def record_signal(signum, _frame):
    RECEIVED_SIGNALS.add(int(signum))


def raise_if_signal_received():
    if RECEIVED_SIGNALS and not CLEANUP_ACTIVE:
        fail("received signal(s) %s" % signal_list_text())


def interruptible_sleep(seconds):
    deadline = time.monotonic() + seconds
    while True:
        raise_if_signal_received()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(remaining, 0.25))


def run_command(argv, timeout_seconds=5):
    raise_if_signal_received()
    try:
        completed = subprocess.run(
            argv,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            check=False,
            timeout=timeout_seconds,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as error:
        output = error.output or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", "replace")
        message = "command timed out after %ss: %s" % (
            timeout_seconds,
            " ".join(argv),
        )
        if output:
            message += "\n" + output.rstrip()
        raise_if_signal_received()
        return 124, message
    except OSError as error:
        if error.errno == errno.ENOENT:
            return 127, "command not found: %s" % argv[0]
        raise
    raise_if_signal_received()
    return completed.returncode, completed.stdout.rstrip()


def close_fd_safely(fd, label):
    try:
        os.close(fd)
    except BaseException as error:
        print("FD_CLOSE_FAIL label=%s error=%s" % (label, error), file=sys.stderr)
        return error
    return None


def read_battery_voltage(power_root="/sys/class/power_supply"):
    try:
        supply_names = sorted(os.listdir(power_root))
    except OSError as error:
        fail("cannot enumerate power supplies: %s" % error)

    battery_supplies = []
    for name in supply_names:
        supply = os.path.join(power_root, name)
        type_path = os.path.join(supply, "type")
        if not os.path.isfile(type_path):
            continue
        try:
            supply_type = read_text(type_path)
        except OSError as error:
            fail("cannot read power supply type %s: %s" % (type_path, error))
        if supply_type == "Battery":
            battery_supplies.append(supply)

    if not battery_supplies:
        fail("battery voltage is unavailable: no type=Battery supply")
    if len(battery_supplies) != 1:
        fail(
            "battery voltage is ambiguous: multiple type=Battery supplies: %s"
            % ",".join(battery_supplies)
        )

    battery_supply = battery_supplies[0]
    voltage_path = None
    for attribute in ("voltage_now", "voltage_avg"):
        candidate = os.path.join(battery_supply, attribute)
        if os.path.isfile(candidate):
            voltage_path = candidate
            break
    if voltage_path is None:
        fail(
            "battery voltage is unavailable for %s: missing voltage_now and voltage_avg"
            % battery_supply
        )

    try:
        raw_voltage = read_text(voltage_path)
    except OSError as error:
        fail("cannot read battery voltage %s: %s" % (voltage_path, error))
    if not raw_voltage or any(character not in "0123456789" for character in raw_voltage):
        fail("battery voltage is not an integer: source=%s" % voltage_path)
    return int(raw_voltage), voltage_path


def require_safe_battery_voltage(stage):
    battery_voltage, battery_voltage_source = read_battery_voltage()
    minimum = (
        MIN_BATTERY_VOLTAGE_AVG_UV
        if battery_voltage_source.endswith("/voltage_avg")
        else MIN_BATTERY_VOLTAGE_NOW_UV
    )
    if battery_voltage < minimum or battery_voltage > MAX_BATTERY_VOLTAGE_UV:
        fail(
            "battery voltage is outside the safe diagnostic range: "
            "stage=%s value=%d minimum=%d maximum=%d source=%s"
            % (
                stage,
                battery_voltage,
                minimum,
                MAX_BATTERY_VOLTAGE_UV,
                battery_voltage_source,
            )
        )
    print(
        "BATTERY_CHECK stage=%s voltage_uv=%d minimum_uv=%d source=%s"
        % (stage, battery_voltage, minimum, battery_voltage_source)
    )
    return battery_voltage, battery_voltage_source


def observation_checkpoints(hold_seconds):
    checkpoints = {0.0, 2.0, 5.0, float(hold_seconds)}
    checkpoint = BATTERY_RECHECK_INTERVAL_SECONDS
    while checkpoint < hold_seconds:
        checkpoints.add(float(checkpoint))
        checkpoint += BATTERY_RECHECK_INTERVAL_SECONDS
    return sorted(checkpoints)


def is_supported_release(release):
    return release in SUPPORTED_RELEASES


def validate_target():
    os.environ["PATH"] = SYSTEM_PATH
    if os.geteuid() != 0:
        fail("must run as root")
    script_path = os.path.realpath(sys.argv[0])
    if script_path != "/run/r46h-display-diagnostic.py":
        fail("script must be installed at /run/r46h-display-diagnostic.py")
    script_stat = os.stat(script_path)
    if script_stat.st_uid != 0 or stat.S_IMODE(script_stat.st_mode) != 0o700:
        fail("/run diagnostic must be root-owned mode 0700")
    current_release = platform.release()
    if not is_supported_release(current_release):
        fail(
            "refusing kernel release %r; expected exactly one of: %s"
            % (current_release, ", ".join(repr(value) for value in SUPPORTED_RELEASES))
        )
    model = read_text("/proc/device-tree/model")
    if "R46H" not in model.upper():
        fail("refusing non-R46H model %r" % model)
    fb_stat = os.stat("/dev/fb0")
    if not stat.S_ISCHR(fb_stat.st_mode):
        fail("/dev/fb0 is not a character device")
    if read_text("/sys/class/drm/card0-DSI-1/status") != "connected":
        fail("DSI-1 is not connected")
    if read_text("/sys/class/drm/card0-DSI-1/enabled") != "enabled":
        fail("DSI-1 is not enabled")
    if read_text("/sys/class/graphics/fb0/name") != "rockchipdrmfb":
        fail("fb0 is not rockchipdrmfb")
    for required_debugfs in (
        "/sys/kernel/debug/dri/0/clients",
        "/sys/kernel/debug/dri/0/framebuffer",
        "/sys/kernel/debug/dri/0/state",
    ):
        if not os.path.isfile(required_debugfs):
            fail("required DRM debugfs file is unavailable: %s" % required_debugfs)

    battery_voltage, battery_voltage_source = require_safe_battery_voltage("target")
    print("TARGET model=%s" % model)
    print("TARGET release=%s" % platform.release())
    print("TARGET cmdline=%s" % read_text("/proc/cmdline"))
    print("TARGET battery_voltage_uv=%d" % battery_voltage)
    print("TARGET battery_voltage_source=%s" % battery_voltage_source)


def unit_properties(unit):
    properties = (
        "LoadState",
        "ActiveState",
        "SubState",
        "MainPID",
        "ControlGroup",
        "KillMode",
        "Restart",
        "NRestarts",
    )
    argv = ["systemctl", "show", unit]
    for name in properties:
        argv.extend(("--property", name))
    code, output = run_command(tuple(argv))
    values = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name] = value
    if code != 0 or not values:
        fail("cannot inspect systemd unit %s: rc=%d output=%s" % (unit, code, output))
    for name in properties:
        values.setdefault(name, "unavailable")
    return values


def print_unit_properties(stage, unit, properties):
    print(
        "SERVICE stage=%s unit=%s load=%s active=%s sub=%s main_pid=%s "
        "cgroup=%s kill_mode=%s restart=%s nrestarts=%s"
        % (
            stage,
            unit,
            properties["LoadState"],
            properties["ActiveState"],
            properties["SubState"],
            properties["MainPID"],
            properties["ControlGroup"],
            properties["KillMode"],
            properties["Restart"],
            properties["NRestarts"],
        )
    )


def capture_display_units():
    snapshots = {}
    for unit in DISPLAY_UNITS:
        properties = unit_properties(unit)
        print_unit_properties("initial", unit, properties)
        if properties["LoadState"] == "not-found":
            fail("required display unit is missing: %s" % unit)
        if properties["ActiveState"] in ("activating", "deactivating", "reloading"):
            fail("display unit is transitioning: %s" % unit)
        snapshots[unit] = properties
    return snapshots


def stop_display_units(snapshots):
    for unit in DISPLAY_UNITS:
        before = snapshots[unit]
        if before["ActiveState"] != "active":
            print("SERVICE_STOP unit=%s action=skip initial=%s" % (unit, before["ActiveState"]))
            continue
        code, output = run_command(("systemctl", "stop", unit), timeout_seconds=15)
        if output:
            for line in output.splitlines():
                print("SERVICE_OUTPUT unit=%s %s" % (unit, line))
        after = unit_properties(unit)
        print_unit_properties("stopped", unit, after)
        if code != 0 or after["ActiveState"] not in ("inactive", "failed"):
            fail("failed to stop %s cleanly" % unit)


def restore_display_units(snapshots):
    errors = []
    if not snapshots:
        return errors
    for unit in DISPLAY_UNITS:
        before = snapshots.get(unit)
        if before is None or before["ActiveState"] != "active":
            continue
        try:
            code, output = run_command(
                ("systemctl", "start", unit),
                timeout_seconds=15,
            )
            if output:
                for line in output.splitlines():
                    print("SERVICE_RESTORE_OUTPUT unit=%s %s" % (unit, line))
            after = unit_properties(unit)
            print_unit_properties("restored", unit, after)
            if code != 0 or after["ActiveState"] != "active":
                errors.append("service did not return active: %s" % unit)
        except BaseException as error:
            errors.append("failed to restore %s: %s" % (unit, error))
            continue
    return errors


def proc_start_time(pid):
    # The comm field may contain spaces and parentheses.  Everything after its
    # final ')' starts at stat field 3; starttime is field 22.
    raw = read_text("/proc/%d/stat" % pid)
    close = raw.rfind(")")
    if close < 0:
        fail("cannot parse /proc/%d/stat" % pid)
    suffix = raw[close + 2 :].split()
    if len(suffix) < 20:
        fail("short /proc/%d/stat" % pid)
    return suffix[19]


def process_identity(pid):
    try:
        cmdline_raw = read_bytes("/proc/%d/cmdline" % pid)
        cmdline = [
            item.decode("utf-8", "replace")
            for item in cmdline_raw.split(b"\x00")
            if item
        ]
        argv0 = cmdline[0] if cmdline else ""
        comm = read_text("/proc/%d/comm" % pid)
        start_time = proc_start_time(pid)
    except (OSError, DiagnosticError):
        return None
    return {
        "pid": pid,
        "argv0": argv0,
        "argument_basenames": frozenset(os.path.basename(item) for item in cmdline),
        "comm": comm,
        "start_time": start_time,
    }


def display_processes():
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        identity = process_identity(int(entry))
        if identity is None:
            continue
        if (
            identity["argument_basenames"].intersection(DISPLAY_PROCESS_NAMES)
            or identity["comm"] in DISPLAY_PROCESS_NAMES
        ):
            found.append(identity)
    return sorted(found, key=lambda item: item["pid"])


def require_no_legacy_processes(stage):
    remaining = display_processes()
    for item in remaining:
        print(
            "LEGACY_PROCESS stage=%s pid=%d start=%s comm=%s argv0=%s"
            % (stage, item["pid"], item["start_time"], item["comm"], item["argv0"])
        )
    if remaining:
        details = ", ".join(
            "%d:%s" % (item["pid"], item["comm"]) for item in remaining
        )
        fail("legacy display processes remain at stage %s: %s" % (stage, details))
    print("LEGACY_PROCESSES stage=%s count=0" % stage)


def is_display_target(target):
    clean = target[:-10] if target.endswith(" (deleted)") else target
    return clean in DISPLAY_DEVICE_PATHS or clean.startswith(DISPLAY_DEVICE_PREFIXES)


def display_device_nodes():
    nodes = ["/dev/fb0"]
    dri_root = "/dev/dri"
    if os.path.isdir(dri_root):
        nodes.extend(os.path.join(dri_root, name) for name in sorted(os.listdir(dri_root)))
    devices = {}
    for node in nodes:
        try:
            node_stat = os.stat(node)
        except OSError:
            continue
        if not stat.S_ISCHR(node_stat.st_mode):
            continue
        devices.setdefault(node_stat.st_rdev, []).append(node)
    if os.stat("/dev/fb0").st_rdev not in devices:
        fail("cannot resolve fb0 device identity")
    return devices


def display_device_holders(exclude_pid=None):
    holders = []
    seen = set()
    display_devices = display_device_nodes()
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid == exclude_pid:
            continue
        identity = process_identity(pid)
        if identity is None:
            continue
        for kind in ("fd", "map_files"):
            proc_dir = "/proc/%d/%s" % (pid, kind)
            try:
                entries = os.listdir(proc_dir)
            except OSError:
                continue
            for descriptor in entries:
                proc_path = os.path.join(proc_dir, descriptor)
                try:
                    target = os.readlink(proc_path)
                    target_stat = os.stat(proc_path)
                except OSError:
                    continue
                matches_device = (
                    stat.S_ISCHR(target_stat.st_mode)
                    and target_stat.st_rdev in display_devices
                )
                if not matches_device and not is_display_target(target):
                    continue
                key = (pid, kind, descriptor, target)
                if key in seen:
                    continue
                seen.add(key)
                holders.append(
                    {
                        "pid": pid,
                        "start_time": identity["start_time"],
                        "comm": identity["comm"],
                        "kind": kind,
                        "descriptor": descriptor,
                        "target": target,
                    }
                )

        maps_path = "/proc/%d/maps" % pid
        try:
            maps_lines = read_text(maps_path).splitlines()
        except OSError:
            maps_lines = []
        for line_number, line in enumerate(maps_lines, 1):
            fields = line.split(None, 5)
            if len(fields) < 6 or not is_display_target(fields[5]):
                continue
            key = (pid, "maps", str(line_number), fields[5])
            if key in seen:
                continue
            seen.add(key)
            holders.append(
                {
                    "pid": pid,
                    "start_time": identity["start_time"],
                    "comm": identity["comm"],
                    "kind": "maps",
                    "descriptor": str(line_number),
                    "target": fields[5],
                }
            )
    return sorted(
        holders,
        key=lambda item: (item["pid"], item["kind"], item["descriptor"]),
    )


def drm_user_clients():
    clients = []
    debug_root = "/sys/kernel/debug/dri"
    for entry in sorted(os.listdir(debug_root)):
        if not entry.isdigit():
            continue
        path = os.path.join(debug_root, entry, "clients")
        if not os.path.isfile(path):
            continue
        lines = [line.strip() for line in read_text(path).splitlines() if line.strip()]
        for line in lines:
            if line.startswith("command"):
                continue
            clients.append((entry, line))
    return clients


def require_no_display_holders(stage, exclude_pid=None):
    holders = display_device_holders(exclude_pid=exclude_pid)
    for item in holders:
        print(
            "DISPLAY_HOLDER stage=%s pid=%d start=%s comm=%s kind=%s "
            "descriptor=%s target=%s"
            % (
                stage,
                item["pid"],
                item["start_time"],
                item["comm"],
                item["kind"],
                item["descriptor"],
                item["target"],
            )
        )
    if holders:
        fail("userspace display descriptors remain at stage %s" % stage)
    print("DISPLAY_HOLDERS stage=%s count=0" % stage)


def require_no_drm_clients(stage):
    clients = drm_user_clients()
    for card, line in clients:
        print("DRM_CLIENT stage=%s card=%s value=%s" % (stage, card, line))
    if clients:
        fail("userspace DRM clients remain at stage %s" % stage)
    print("DRM_CLIENTS stage=%s count=0" % stage)


def require_fuser_clear(stage):
    devices = sorted(
        node for nodes in display_device_nodes().values() for node in nodes
    )
    code, output = run_command(tuple(["fuser", "-v"] + devices))
    print("FUSER stage=%s rc=%d" % (stage, code))
    if output:
        for line in output.splitlines():
            print("FUSER_OUTPUT stage=%s %s" % (stage, line))
    if code == 0:
        fail("fuser reports a display device holder at stage %s" % stage)
    if code != 1:
        fail("fuser failed unexpectedly at stage %s" % stage)


def drm_scanout_fingerprint(stage, expected=None):
    state = read_text("/sys/kernel/debug/dri/0/state")
    framebuffer = read_text("/sys/kernel/debug/dri/0/framebuffer")
    required_state = (
        "allocated by = [fbcon]",
        "format=XR24 little-endian (0x34325258)",
        "size=1024x768",
        "pitch[0]=4096",
        "offset[0]=0",
        "crtc-pos=1024x768+0+0",
        "enable=1",
        "active=1",
        "connector_mask=1",
        "connector[",
        ": DSI-1",
        "crtc=crtc-0",
    )
    for marker in required_state:
        if marker not in state:
            fail("DRM scanout is missing %r at stage %s" % (marker, stage))
    if state.count("allocated by = [fbcon]") != 1:
        fail("expected exactly one fbcon scanout at stage %s" % stage)
    if state.count("\n\tcrtc=(null)\n\tfb=0") != 2:
        fail("secondary planes are not both unbound at stage %s" % stage)
    if framebuffer.count("framebuffer[") != 1:
        fail("expected exactly one DRM framebuffer at stage %s" % stage)
    for marker in (
        "allocated by = [fbcon]",
        "format=XR24 little-endian (0x34325258)",
        "size=1024x768",
        "pitch[0]=4096",
        "offset[0]=0",
    ):
        if marker not in framebuffer:
            fail("DRM framebuffer is missing %r at stage %s" % (marker, stage))
    digest = hashlib.sha256(
        state.encode("utf-8") + b"\x00" + framebuffer.encode("utf-8")
    ).hexdigest()
    print("DRM_SCANOUT stage=%s sha256=%s" % (stage, digest))
    if expected is not None and digest != expected:
        fail("DRM scanout state changed at stage %s" % stage)
    return digest


def require_quiescent(stage, service_snapshots, samples=3, interval=0.5):
    restart_values = None
    for sample in range(1, samples + 1):
        sample_stage = "%s_%d" % (stage, sample)
        require_no_legacy_processes(sample_stage)
        require_no_display_holders(sample_stage)
        require_no_drm_clients(sample_stage)
        require_fuser_clear(sample_stage)
        current_restarts = []
        for unit in DISPLAY_UNITS:
            properties = unit_properties(unit)
            print_unit_properties(sample_stage, unit, properties)
            if service_snapshots[unit]["ActiveState"] == "active":
                if properties["ActiveState"] not in ("inactive", "failed"):
                    fail("stopped service changed state during quiescence: %s" % unit)
            elif properties["ActiveState"] != service_snapshots[unit]["ActiveState"]:
                fail("initially inactive service changed state: %s" % unit)
            current_restarts.append((unit, properties["NRestarts"]))
        if restart_values is not None and current_restarts != restart_values:
            fail("service restart counters changed during quiescence")
        restart_values = current_restarts
        print("QUIESCENT stage=%s sample=%d pass=yes" % (stage, sample))
        if sample != samples:
            interruptible_sleep(interval)


def enter_graphics_vt():
    tty_fd = os.open("/dev/tty0", os.O_RDWR | os.O_CLOEXEC)
    mode = array.array("i", [0])
    original = None
    restore_needed = False
    try:
        fcntl.ioctl(tty_fd, KDGETMODE, mode, True)
        if mode[0] not in (KD_TEXT, KD_GRAPHICS):
            fail("unexpected active VT mode %d" % mode[0])
        original = mode[0]
        if original != KD_GRAPHICS:
            restore_needed = True
            fcntl.ioctl(tty_fd, KDSETMODE, KD_GRAPHICS)
        verify = array.array("i", [0])
        fcntl.ioctl(tty_fd, KDGETMODE, verify, True)
        if verify[0] != KD_GRAPHICS:
            fail("failed to enter KD_GRAPHICS")
        print("VT_MODE original=%d current=%d" % (original, verify[0]))
        return tty_fd, original
    except BaseException as primary_error:
        if restore_needed and original is not None:
            try:
                fcntl.ioctl(tty_fd, KDSETMODE, original)
                print("VT_ROLLBACK_AFTER_ENTRY_FAILURE restored=%d" % original)
            except OSError as restore_error:
                print(
                    "VT_ROLLBACK_AFTER_ENTRY_FAILURE failed=%s primary=%s"
                    % (restore_error, primary_error),
                    file=sys.stderr,
                )
        close_fd_safely(tty_fd, "vt-entry-rollback")
        raise


def restore_vt(tty_fd, original):
    errors = []
    if tty_fd is None:
        return errors
    try:
        fcntl.ioctl(tty_fd, KDSETMODE, original)
        verify = array.array("i", [0])
        fcntl.ioctl(tty_fd, KDGETMODE, verify, True)
        print("VT_RESTORE expected=%d current=%d" % (original, verify[0]))
        if verify[0] != original:
            errors.append("active VT mode was not restored")
    except OSError as error:
        errors.append("failed to restore active VT: %s" % error)
    finally:
        close_error = close_fd_safely(tty_fd, "vt-restore")
        if close_error is not None:
            errors.append("failed to close active VT descriptor: %s" % close_error)
    return errors


def dump_file(label, path):
    print("BEGIN_%s path=%s" % (label, path))
    try:
        content = read_text(path)
    except OSError as error:
        print("UNAVAILABLE errno=%s message=%s" % (error.errno, error))
    else:
        print(content)
    print("END_%s" % label)


def dump_runtime_state(stage):
    print("STATE stage=%s timestamp=%s" % (stage, utc_now()))
    for path in (
        "/sys/class/drm/card0-DSI-1/status",
        "/sys/class/drm/card0-DSI-1/enabled",
        "/sys/class/drm/card0-DSI-1/modes",
    ):
        if os.path.exists(path):
            print("SYSFS path=%s value=%s" % (path, read_text(path).replace("\n", ",")))

    for root in ("/sys/class/backlight", "/sys/class/power_supply"):
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            device = os.path.join(root, name)
            fields = (
                ("brightness", "actual_brightness", "max_brightness", "bl_power")
                if root.endswith("backlight")
                else ("online", "status", "capacity", "voltage_now", "voltage_avg")
            )
            for field in fields:
                path = os.path.join(device, field)
                if os.path.isfile(path):
                    try:
                        value = read_text(path)
                    except OSError as error:
                        value = "ERROR:%s" % error.errno
                    print("SYSFS path=%s value=%s" % (path, value))

    for card in ("0", "1"):
        for leaf in ("clients", "framebuffer", "state"):
            path = "/sys/kernel/debug/dri/%s/%s" % (card, leaf)
            if os.path.exists(path):
                dump_file("DRI_%s_%s_%s" % (card, leaf.upper(), stage.upper()), path)

    code, output = run_command(("dmesg",))
    print("BEGIN_DSI_MARKERS stage=%s dmesg_rc=%d" % (stage, code))
    for line in output.splitlines():
        if "R46H_DSI_" in line or "R46H_DPHY_" in line:
            print(line)
    print("END_DSI_MARKERS stage=%s" % stage)


def kernel_log_snapshot():
    code, output = run_command(("dmesg",))
    if code != 0:
        fail("cannot read kernel log: rc=%d" % code)
    return output


def require_no_new_display_faults(baseline):
    current = kernel_log_snapshot()
    if not current.startswith(baseline):
        fail("kernel log no longer has the pre-test snapshot as a prefix")
    appended = current[len(baseline) :].lstrip("\n")
    print("BEGIN_NEW_KERNEL_LOG")
    if appended:
        print(appended)
    print("END_NEW_KERNEL_LOG")
    subsystem_words = ("drm", "dsi", "vop", "mipi", "panfrost", "gpu", "display")
    failure_words = (
        "fault",
        "error",
        "failed",
        "timeout",
        "underflow",
        "overflow",
        "hang",
    )
    bad_lines = []
    for line in appended.splitlines():
        lowered = line.lower()
        if "low voltage" in lowered or "suspend" in lowered:
            bad_lines.append(line)
            continue
        if any(word in lowered for word in subsystem_words) and any(
            word in lowered for word in failure_words
        ):
            bad_lines.append(line)
    for line in bad_lines:
        print("NEW_DISPLAY_FAULT %s" % line)
    if bad_lines:
        fail("new display/GPU/power fault appeared in the kernel log")
    print("NEW_DISPLAY_FAULTS count=0")


def ioctl_struct(fd, request, structure_type):
    size = ctypes.sizeof(structure_type)
    buffer = bytearray(size)
    fcntl.ioctl(fd, request, buffer, True)
    return structure_type.from_buffer_copy(buffer)


def fb_mode(fd):
    if ctypes.sizeof(FbVarScreeninfo) != 160:
        fail("unexpected fb_var_screeninfo size %d" % ctypes.sizeof(FbVarScreeninfo))
    if ctypes.sizeof(ctypes.c_ulong) != 8:
        fail("expected a 64-bit userspace")
    if ctypes.sizeof(FbFixScreeninfo) != 80:
        fail("unexpected fb_fix_screeninfo size %d" % ctypes.sizeof(FbFixScreeninfo))

    var = ioctl_struct(fd, FBIOGET_VSCREENINFO, FbVarScreeninfo)
    fix = ioctl_struct(fd, FBIOGET_FSCREENINFO, FbFixScreeninfo)
    if fix.type != FB_TYPE_PACKED_PIXELS:
        fail("unsupported framebuffer type %d" % fix.type)
    if fix.visual != FB_VISUAL_TRUECOLOR:
        fail("unsupported framebuffer visual %d" % fix.visual)
    if var.grayscale != 0 or var.nonstd != 0:
        fail("refusing grayscale/non-standard framebuffer")
    if var.bits_per_pixel not in (16, 24, 32):
        fail("unsupported bits_per_pixel %d" % var.bits_per_pixel)
    if var.xres == 0 or var.yres == 0:
        fail("zero visible resolution")
    if (var.xres, var.yres, var.bits_per_pixel) != (1024, 768, 32):
        fail(
            "unexpected R46H framebuffer mode %dx%dx%d"
            % (var.xres, var.yres, var.bits_per_pixel)
        )
    if (
        var.xres_virtual,
        var.yres_virtual,
        var.xoffset,
        var.yoffset,
    ) != (1024, 768, 0, 0):
        fail("unexpected R46H virtual geometry or viewport offset")
    if var.xres_virtual < var.xoffset + var.xres:
        fail("visible x range exceeds virtual framebuffer")
    if var.yres_virtual < var.yoffset + var.yres:
        fail("visible y range exceeds virtual framebuffer")

    bytes_per_pixel = var.bits_per_pixel // 8
    row_bytes = var.xres * bytes_per_pixel
    if fix.line_length < (var.xoffset * bytes_per_pixel) + row_bytes:
        fail("line_length is shorter than the visible row")
    active_end = (
        (var.yoffset + var.yres - 1) * fix.line_length
        + (var.xoffset * bytes_per_pixel)
        + row_bytes
    )
    if active_end > fix.smem_len:
        fail("visible framebuffer exceeds smem_len")
    if fix.line_length != 4096 or fix.smem_len != 3145728:
        fail("unexpected R46H stride or framebuffer allocation size")

    for label, field in (
        ("red", var.red),
        ("green", var.green),
        ("blue", var.blue),
        ("transp", var.transp),
    ):
        if field.msb_right != 0:
            fail("unsupported msb_right for %s" % label)
        if field.offset + field.length > var.bits_per_pixel:
            fail("%s bitfield exceeds pixel width" % label)
    if not var.red.length or not var.green.length or not var.blue.length:
        fail("missing RGB bitfields")
    if (
        bitfield_fingerprint(var.red),
        bitfield_fingerprint(var.green),
        bitfield_fingerprint(var.blue),
        bitfield_fingerprint(var.transp),
    ) != ((16, 8, 0), (8, 8, 0), (0, 8, 0), (0, 0, 0)):
        fail("fbdev bitfields do not match DRM XR24")

    identifier = bytes(fix.id).split(b"\x00", 1)[0].decode("ascii", "replace")
    print(
        "FB_MODE id=%s visible=%dx%d virtual=%dx%d offset=%d,%d bpp=%d "
        "stride=%d smem_len=%d visual=%d"
        % (
            identifier,
            var.xres,
            var.yres,
            var.xres_virtual,
            var.yres_virtual,
            var.xoffset,
            var.yoffset,
            var.bits_per_pixel,
            fix.line_length,
            fix.smem_len,
            fix.visual,
        )
    )
    print(
        "FB_FIELDS red=%d:%d green=%d:%d blue=%d:%d transp=%d:%d"
        % (
            var.red.offset,
            var.red.length,
            var.green.offset,
            var.green.length,
            var.blue.offset,
            var.blue.length,
            var.transp.offset,
            var.transp.length,
        )
    )
    return var, fix


def scale_channel(value, length):
    if value < 0 or value > 255:
        fail("channel value outside 0..255")
    if length == 0:
        return 0
    maximum = (1 << length) - 1
    return (value * maximum + 127) // 255


def encode_pixel(red, green, blue, var):
    value = 0
    value |= scale_channel(red, var.red.length) << var.red.offset
    value |= scale_channel(green, var.green.length) << var.green.offset
    value |= scale_channel(blue, var.blue.length) << var.blue.offset
    if var.transp.length:
        value |= ((1 << var.transp.length) - 1) << var.transp.offset
    return value.to_bytes(var.bits_per_pixel // 8, byteorder="little")


def pattern_row(pattern, y, var):
    white = (255, 255, 255)
    black = (0, 0, 0)
    if pattern == "white":
        return encode_pixel(*white, var=var) * var.xres
    if pattern == "black":
        return encode_pixel(*black, var=var) * var.xres
    if pattern == "bars":
        colors = (
            white,
            (255, 255, 0),
            (0, 255, 255),
            (0, 255, 0),
            (255, 0, 255),
            (255, 0, 0),
            (0, 0, 255),
            black,
        )
        pixels = []
        for x in range(var.xres):
            color = colors[min(len(colors) - 1, (x * len(colors)) // var.xres)]
            pixels.append(encode_pixel(*color, var=var))
        return b"".join(pixels)
    if pattern == "checker":
        pixels = []
        for x in range(var.xres):
            color = white if ((x // 32) + (y // 32)) % 2 == 0 else black
            pixels.append(encode_pixel(*color, var=var))
        return b"".join(pixels)
    fail("unknown pattern %r" % pattern)


def write_all_at(fd, data, offset):
    os.lseek(fd, offset, os.SEEK_SET)
    view = memoryview(data)
    written = 0
    while written < len(data):
        count = os.write(fd, view[written:])
        if count <= 0:
            fail("short framebuffer write at offset %d" % (offset + written))
        written += count


def read_exact_at(fd, length, offset):
    os.lseek(fd, offset, os.SEEK_SET)
    chunks = []
    remaining = length
    while remaining:
        chunk = os.read(fd, remaining)
        if not chunk:
            fail("short framebuffer read at offset %d" % (offset + length - remaining))
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def visible_row_offset(y, var, fix):
    return (
        (var.yoffset + y) * fix.line_length
        + var.xoffset * (var.bits_per_pixel // 8)
    )


def prepare_pattern_rows(pattern, var):
    rows = []
    for y in range(var.yres):
        raise_if_signal_received()
        rows.append(pattern_row(pattern, y, var))
    return tuple(rows)


def pattern_rows_hash(rows):
    digest = hashlib.sha256()
    for row in rows:
        digest.update(row)
    return digest.hexdigest()


def expected_pattern_hash(pattern, var):
    return pattern_rows_hash(prepare_pattern_rows(pattern, var))


def bitfield_fingerprint(field):
    return (field.offset, field.length, field.msb_right)


def framebuffer_fingerprint(fd, var, fix):
    fd_stat = os.fstat(fd)
    return (
        fd_stat.st_rdev,
        var.xres,
        var.yres,
        var.xres_virtual,
        var.yres_virtual,
        var.xoffset,
        var.yoffset,
        var.bits_per_pixel,
        var.grayscale,
        bitfield_fingerprint(var.red),
        bitfield_fingerprint(var.green),
        bitfield_fingerprint(var.blue),
        bitfield_fingerprint(var.transp),
        var.nonstd,
        bytes(fix.id),
        fix.smem_start,
        fix.smem_len,
        fix.type,
        fix.visual,
        fix.line_length,
    )


def open_framebuffer(expected_fingerprint=None):
    fd = os.open("/dev/fb0", os.O_RDWR | os.O_CLOEXEC)
    try:
        var, fix = fb_mode(fd)
        fingerprint = framebuffer_fingerprint(fd, var, fix)
        if expected_fingerprint is not None and fingerprint != expected_fingerprint:
            fail("framebuffer identity or mode changed during the diagnostic")
        return fd, var, fix, fingerprint
    except BaseException:
        close_fd_safely(fd, "framebuffer-open-failure")
        raise


def sync_framebuffer(fd):
    try:
        os.fsync(fd)
    except OSError as error:
        if error.errno not in (errno.EINVAL, errno.ENOTTY):
            raise


def write_pattern(fd, rows, var, fix):
    if len(rows) != var.yres:
        fail("prepared pattern row count does not match framebuffer height")
    for y, row in enumerate(rows):
        raise_if_signal_received()
        write_all_at(fd, row, visible_row_offset(y, var, fix))
    sync_framebuffer(fd)


def verify_pattern(fd, rows, var, fix):
    if len(rows) != var.yres:
        fail("prepared pattern row count does not match framebuffer height")
    expected_digest = hashlib.sha256()
    actual_digest = hashlib.sha256()
    first_mismatch = None
    for y, expected in enumerate(rows):
        raise_if_signal_received()
        actual = read_exact_at(fd, len(expected), visible_row_offset(y, var, fix))
        expected_digest.update(expected)
        actual_digest.update(actual)
        if first_mismatch is None and actual != expected:
            first_mismatch = y
    return expected_digest.hexdigest(), actual_digest.hexdigest(), first_mismatch


def run_pattern(pattern, hold_seconds, service_snapshots, scanout_fingerprint):
    fd = None
    original = None
    original_hash = None
    fingerprint = None
    restored = False
    try:
        fd, var, fix, fingerprint = open_framebuffer()
        original = read_exact_at(fd, fix.smem_len, 0)
        original_hash = hashlib.sha256(original).hexdigest()
        print(
            "FB_SNAPSHOT bytes=%d sha256=%s storage=memory"
            % (len(original), original_hash)
        )
        prepared_rows = prepare_pattern_rows(pattern, var)
        prepared_bytes = sum(len(row) for row in prepared_rows)
        expected_hash = pattern_rows_hash(prepared_rows)
        print(
            "PATTERN_WRITE name=%s bytes=%d storage=memory expected_sha256=%s"
            % (pattern, prepared_bytes, expected_hash)
        )
        write_pattern(fd, prepared_rows, var, fix)
        closing_fd = fd
        fd = None
        close_error = close_fd_safely(closing_fd, "framebuffer-after-write")
        if close_error is not None:
            raise close_error

        started = time.monotonic()
        checkpoints = observation_checkpoints(hold_seconds)
        print("PATTERN_VISIBLE hold_seconds=%d" % hold_seconds)
        for checkpoint in checkpoints:
            remaining = started + checkpoint - time.monotonic()
            if remaining > 0:
                interruptible_sleep(remaining)
            require_safe_battery_voltage("pattern_%.2f" % checkpoint)
            fd, current_var, current_fix, _ = open_framebuffer(fingerprint)
            expected, actual, mismatch = verify_pattern(
                fd, prepared_rows, current_var, current_fix
            )
            closing_fd = fd
            fd = None
            close_error = close_fd_safely(
                closing_fd,
                "framebuffer-readback-%.2f" % checkpoint,
            )
            if close_error is not None:
                raise close_error
            match = mismatch is None and expected == actual == expected_hash
            print(
                "PATTERN_READBACK checkpoint=%.2f elapsed=%.2f "
                "expected_sha256=%s actual_sha256=%s match=%s "
                "first_mismatch_row=%s"
                % (
                    checkpoint,
                    time.monotonic() - started,
                    expected,
                    actual,
                    "yes" if match else "no",
                    "none" if mismatch is None else mismatch,
                )
            )
            if not match:
                fail("framebuffer contents changed during controlled readback")
            require_quiescent(
                "pattern_%.2f" % checkpoint,
                service_snapshots,
                samples=1,
                interval=0,
            )
            drm_scanout_fingerprint(
                "pattern_%.2f" % checkpoint,
                expected=scanout_fingerprint,
            )
    finally:
        active_error = sys.exc_info()[1]
        deferred_close_error = None
        if fd is not None:
            closing_fd = fd
            fd = None
            deferred_close_error = close_fd_safely(
                closing_fd,
                "framebuffer-pattern-finally",
            )
        if original is not None and fingerprint is not None:
            restore_fd = None
            restore_close_error = None
            try:
                restore_fd, _, restore_fix, _ = open_framebuffer(fingerprint)
                if len(original) != restore_fix.smem_len:
                    fail("framebuffer size changed before restore")
                write_all_at(restore_fd, original, 0)
                sync_framebuffer(restore_fd)
                restored_bytes = read_exact_at(restore_fd, len(original), 0)
                restored_hash = hashlib.sha256(restored_bytes).hexdigest()
                restored = restored_hash == original_hash
                print(
                    "FB_RESTORE expected_sha256=%s actual_sha256=%s match=%s"
                    % (original_hash, restored_hash, "yes" if restored else "no")
                )
            finally:
                if restore_fd is not None:
                    closing_fd = restore_fd
                    restore_fd = None
                    restore_close_error = close_fd_safely(
                        closing_fd,
                        "framebuffer-restore",
                    )
            if not restored:
                fail("original framebuffer snapshot was not restored")
            if restore_close_error is not None:
                raise restore_close_error
        if deferred_close_error is not None and active_error is None:
            raise deferred_close_error


def read_debugfs_bool(path):
    value = read_text(path)
    if value not in ("0", "1"):
        fail("debugfs boolean has unexpected value: %s=%r" % (path, value))
    return value == "1"


def write_debugfs_bool(path, enabled):
    with open(path, "w") as debugfs_file:
        debugfs_file.write("1\n" if enabled else "0\n")
        debugfs_file.flush()
    actual = read_debugfs_bool(path)
    if actual != enabled:
        fail(
            "debugfs boolean write did not take effect: %s expected=%d actual=%d"
            % (path, int(enabled), int(actual))
        )


def host_vpg_state():
    return (
        read_debugfs_bool(HOST_VPG_PATH),
        read_debugfs_bool(HOST_VPG_HORIZONTAL_PATH),
        read_debugfs_bool(HOST_VPG_BER_PATH),
    )


def restore_host_vpg(initial_state, attempts=2):
    errors = []
    for attempt in range(1, attempts + 1):
        try:
            write_debugfs_bool(HOST_VPG_PATH, False)
            restored_state = host_vpg_state()
            print(
                "HOST_VPG_RESTORE attempt=%d software_flags=%d,%d,%d match=%s"
                % (
                    attempt,
                    int(restored_state[0]),
                    int(restored_state[1]),
                    int(restored_state[2]),
                    "yes" if restored_state == initial_state else "no",
                )
            )
            if restored_state == initial_state:
                return
            errors.append("attempt %d state=%r" % (attempt, restored_state))
        except BaseException as error:
            errors.append("attempt %d error=%s" % (attempt, error))
    fail(
        "DSI host VPG software flags were not restored after %d attempts: %s"
        % (attempts, "; ".join(errors))
    )


def run_host_vpg(hold_seconds, service_snapshots, scanout_fingerprint):
    for path in (HOST_VPG_PATH, HOST_VPG_HORIZONTAL_PATH, HOST_VPG_BER_PATH):
        if not os.path.isfile(path):
            fail("required DSI host VPG debugfs file is unavailable: %s" % path)

    initial_state = host_vpg_state()
    print(
        "HOST_VPG_INITIAL software_flags=%d,%d,%d hardware_readback=unavailable"
        % tuple(int(value) for value in initial_state)
    )
    if initial_state != (False, False, False):
        fail("DSI host VPG was not fully disabled before the diagnostic")

    enable_attempted = False
    try:
        enable_attempted = True
        write_debugfs_bool(HOST_VPG_PATH, True)
        print(
            "HOST_VPG_REQUEST pattern=color-bars software_flags=1,0,0 hold_seconds=%d"
            % hold_seconds
        )
        started = time.monotonic()
        checkpoints = observation_checkpoints(hold_seconds)
        for checkpoint in checkpoints:
            remaining = started + checkpoint - time.monotonic()
            if remaining > 0:
                interruptible_sleep(remaining)
            require_safe_battery_voltage("host_vpg_%.2f" % checkpoint)
            state = host_vpg_state()
            if state != (True, False, False):
                fail("DSI host VPG state changed during the diagnostic: %r" % (state,))
            print(
                "HOST_VPG_CHECK checkpoint=%.2f elapsed=%.2f "
                "software_flags=1,0,0 hardware_readback=unavailable"
                % (checkpoint, time.monotonic() - started)
            )
            require_quiescent(
                "host_vpg_%.2f" % checkpoint,
                service_snapshots,
                samples=1,
                interval=0,
            )
            drm_scanout_fingerprint(
                "host_vpg_%.2f" % checkpoint,
                expected=scanout_fingerprint,
            )
    finally:
        if enable_attempted:
            restore_host_vpg(initial_state)


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Controlled R46H framebuffer diagnostic"
    )
    parser.add_argument(
        "--pattern",
        choices=("white", "bars", "checker", "black"),
        help="visible pattern to show temporarily on fb0",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="stop legacy display userspace and capture state without writing fb0",
    )
    parser.add_argument(
        "--host-vpg",
        action="store_true",
        help="temporarily enable the DSI host built-in color-bar generator",
    )
    parser.add_argument(
        "--hold-seconds",
        type=int,
        default=30,
        help="observation window before automatic restore (5..300; default 30)",
    )
    args = parser.parse_args(argv)
    selected_modes = sum(
        (int(args.prepare_only), int(args.pattern is not None), int(args.host_vpg))
    )
    if selected_modes != 1:
        parser.error("choose exactly one of --prepare-only, --pattern, or --host-vpg")
    if args.hold_seconds < 5 or args.hold_seconds > 300:
        parser.error("--hold-seconds must be between 5 and 300")
    return args


def main(argv=None):
    global CLEANUP_ACTIVE

    args = parse_args(sys.argv[1:] if argv is None else argv)
    print("R46H_DISPLAY_DIAG_BEGIN timestamp=%s" % utc_now())
    validate_target()
    service_snapshots = None
    tty_fd = None
    original_vt_mode = None
    primary_error = None
    cleanup_errors = []
    cleanup_signals = frozenset((signal.SIGINT, signal.SIGTERM, signal.SIGHUP))
    RECEIVED_SIGNALS.clear()
    CLEANUP_ACTIVE = False
    original_handlers = {
        handled_signal: signal.getsignal(handled_signal)
        for handled_signal in cleanup_signals
    }
    for handled_signal in cleanup_signals:
        signal.signal(handled_signal, record_signal)

    try:
        kernel_log_before = kernel_log_snapshot()
        dump_runtime_state("before_stop")
        service_snapshots = capture_display_units()
        stop_display_units(service_snapshots)
        tty_fd, original_vt_mode = enter_graphics_vt()
        require_quiescent("clean", service_snapshots)
        dump_runtime_state("clean")
        clean_scanout = drm_scanout_fingerprint("clean")

        if args.pattern is not None:
            run_pattern(
                args.pattern,
                args.hold_seconds,
                service_snapshots,
                clean_scanout,
            )
        elif args.host_vpg:
            run_host_vpg(
                args.hold_seconds,
                service_snapshots,
                clean_scanout,
            )

        if args.pattern is not None or args.host_vpg:
            require_quiescent("after_test", service_snapshots)
            drm_scanout_fingerprint("after_test", expected=clean_scanout)
            dump_runtime_state("after_test")
            require_quiescent("final", service_snapshots)
            drm_scanout_fingerprint("final", expected=clean_scanout)
            require_no_new_display_faults(kernel_log_before)
    except BaseException as error:
        primary_error = error
    finally:
        CLEANUP_ACTIVE = True
        try:
            cleanup_errors.extend(restore_vt(tty_fd, original_vt_mode))
        except BaseException as error:
            cleanup_errors.append("unexpected VT cleanup failure: %s" % error)
        try:
            cleanup_errors.extend(restore_display_units(service_snapshots))
        except BaseException as error:
            cleanup_errors.append("unexpected service cleanup failure: %s" % error)
        for handled_signal, original in original_handlers.items():
            signal.signal(handled_signal, original)
        CLEANUP_ACTIVE = False

    if RECEIVED_SIGNALS and primary_error is None:
        primary_error = DiagnosticError(
            "received signal(s) %s" % signal_list_text()
        )

    for cleanup_error in cleanup_errors:
        print(
            "R46H_DISPLAY_DIAG_CLEANUP_FAIL error=%s" % cleanup_error,
            file=sys.stderr,
        )
    if primary_error is not None:
        raise primary_error
    if cleanup_errors:
        fail("one or more cleanup operations failed")
    if args.prepare_only:
        print("R46H_DISPLAY_DIAG_PASS mode=prepare-only cleanup=restored")
    elif args.host_vpg:
        print("R46H_DISPLAY_DIAG_PASS mode=host-vpg cleanup=restored")
    else:
        print(
            "R46H_DISPLAY_DIAG_PASS pattern=%s cleanup=restored" % args.pattern
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (DiagnosticError, OSError, KeyboardInterrupt) as error:
        print("R46H_DISPLAY_DIAG_FAIL error=%s" % error, file=sys.stderr)
        sys.exit(1)
