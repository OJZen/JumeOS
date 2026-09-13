#!/usr/bin/env python3
"""Read CPU/memory capabilities and validate drafts. Never writes system settings."""
import argparse
import gzip
import json
from pathlib import Path


def read(path):
    try:
        return path.read_text().strip()
    except (OSError, UnicodeError):
        return ""


def number(value):
    return int(value) if value.isdecimal() else None


def probe(root, config=None):
    policies = []
    for directory in sorted((root / "sys/devices/system/cpu/cpufreq").glob("policy[0-9]*")):
        values = {name: read(directory / name) for name in (
            "scaling_driver", "scaling_governor", "scaling_available_governors",
            "scaling_available_frequencies", "scaling_min_freq", "scaling_max_freq",
            "cpuinfo_min_freq", "cpuinfo_max_freq", "scaling_cur_freq")}
        policies.append({"policy": directory.name, "driver": values["scaling_driver"],
                         "governor": values["scaling_governor"],
                         "governors": values["scaling_available_governors"].split(),
                         "frequencies_khz": [int(v) for v in values["scaling_available_frequencies"].split() if v.isdecimal()],
                         **{name: number(values[name]) for name in values if name.endswith("freq")}})
    config_text = read(config) if config else ""
    if not config and (root / "proc/config.gz").exists():
        try:
            with gzip.open(root / "proc/config.gz", "rt") as stream:
                config_text = stream.read(2 * 1024 * 1024)
        except (OSError, UnicodeError):
            pass
    config_values = dict(line.split("=", 1) for line in config_text.splitlines() if line.startswith("CONFIG_") and "=" in line)
    disabled = {line.split()[1] for line in config_text.splitlines() if line.startswith("# CONFIG_") and line.endswith(" is not set")}
    mem = {}
    for line in read(root / "proc/meminfo").splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2] == "kB":
            mem[fields[0].rstrip(":")] = number(fields[1])
    zram = []
    for path in sorted((root / "sys/block").glob("zram[0-9]*")):
        zram.append({"device": path.name,
                     "algorithms": read(path / "comp_algorithm").replace("[", "").replace("]", "").split(),
                     "disksize_bytes": number(read(path / "disksize")),
                     "mm_stat": read(path / "mm_stat")})
    return {"schema": 1, "scope": "read-only snapshot; not device identity or an apply receipt",
            "kernel": read(root / "proc/sys/kernel/osrelease"), "cpu": policies,
            "memory_kib": mem, "active_swaps": read(root / "proc/swaps"), "zram": zram,
            "kernel_config": {name: config_values.get(name, "n" if name in disabled else "unknown")
                              for name in ("CONFIG_SWAP", "CONFIG_ZRAM", "CONFIG_ZSWAP")}}


def cpu_draft(policy, preset, low=None, high=None, governor=None):
    """Presets preserve the sampled frequency limits; custom values use kHz."""
    if preset not in {"default", "balanced", "powersave", "performance", "custom"}:
        raise ValueError("unknown CPU preset")
    if preset != "custom":
        governor = {"default": policy["governor"], "balanced": "schedutil",
                    "powersave": "powersave", "performance": "performance"}[preset]
        low, high = policy["scaling_min_freq"], policy["scaling_max_freq"]
    minimum, maximum = policy["cpuinfo_min_freq"], policy["cpuinfo_max_freq"]
    if any(type(v) is not int for v in (low, high, minimum, maximum)) or not 0 < minimum <= low <= high <= maximum:
        raise ValueError("frequency limits unavailable, reversed, or outside hardware bounds")
    if governor not in policy["governors"]:
        raise ValueError("governor is not currently available; no implicit module loading")
    table = policy["frequencies_khz"]
    if table and (low not in table or high not in table):
        raise ValueError("custom limits must use the device's available frequencies")
    return {"policy": policy["policy"], "governor": governor, "min_khz": low, "max_khz": high}


def validate(snapshot, plan):
    if not isinstance(snapshot, dict) or not isinstance(plan, dict):
        raise ValueError("snapshot and plan must be objects")
    if type(snapshot.get("schema")) is not int or type(plan.get("schema")) is not int or snapshot["schema"] != 1 or plan["schema"] != 1:
        raise ValueError("unsupported schema")
    result = {"status": "VALID_DRAFT_NOT_APPLIED", "cpu": []}
    policies = {p["policy"]: p for p in snapshot["cpu"]}
    seen = set()
    if not isinstance(plan.get("cpu", []), list):
        raise ValueError("CPU plan must be a list")
    for entry in plan.get("cpu", []):
        if not isinstance(entry, dict) or set(entry) - {"policy", "preset", "min_khz", "max_khz", "governor"}:
            raise ValueError("unknown CPU configuration field or invalid entry")
        if entry.get("preset") != "custom" and set(entry) & {"min_khz", "max_khz", "governor"}:
            raise ValueError("frequency/governor overrides require the custom preset")
        name = entry["policy"]
        if name in seen or name not in policies:
            raise ValueError("duplicate or unavailable CPU policy")
        seen.add(name)
        result["cpu"].append(cpu_draft(policies[name], entry["preset"], entry.get("min_khz"), entry.get("max_khz"), entry.get("governor")))
    if "zram" in plan:
        entry = plan["zram"]
        if not isinstance(entry, dict) or set(entry) - {"size_mib", "algorithm"}:
            raise ValueError("unknown zram configuration field or invalid entry")
        size = entry["size_mib"]
        if type(size) is not int or size < 0:
            raise ValueError("zram size must be a non-negative integer MiB")
        ram = snapshot["memory_kib"].get("MemTotal")
        if size:
            if snapshot["kernel_config"]["CONFIG_SWAP"] != "y" or snapshot["kernel_config"]["CONFIG_ZRAM"] == "n" or not snapshot["zram"]:
                raise ValueError("swap/zram runtime capability has not been established")
            if type(ram) is not int or size * 1024 > ram * 2:
                raise ValueError("preview policy limits logical zram size to 2x verified RAM")
            if entry["algorithm"] not in snapshot["zram"][0]["algorithms"]:
                raise ValueError("compression algorithm is not available")
        result["zram"] = entry
    # Disk swap needs an identified writable filesystem and an owned file first.
    # Do not turn a host draft into a swapoff/truncate operation.
    if "disk_swap" in plan:
        raise ValueError("disk swap apply planning awaits identified target storage and space checks")
    if set(plan) - {"schema", "cpu", "zram"}:
        raise ValueError("unknown configuration field")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/"), help="Linux root or a test fixture")
    parser.add_argument("--kernel-config", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--validate", type=Path, metavar="PLAN_JSON")
    args = parser.parse_args()
    try:
        snapshot = json.loads(args.snapshot.read_text()) if args.snapshot else probe(args.root, args.kernel_config)
        result = validate(snapshot, json.loads(args.validate.read_text())) if args.validate else snapshot
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.exit(2, f"Invalid or unavailable tuning data: {error}\n")


if __name__ == "__main__":
    main()
