#!/usr/bin/env python3
"""Focused guards for the private Mesa runtime integration."""

import importlib.util
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
ROOT = REPO / "mainline/gaming-mesa"
LOCK = json.loads((ROOT / "source-lock.json").read_text(encoding="utf-8"))
SPEC = importlib.util.spec_from_file_location("r46h_mesa_runtime", ROOT / "runtime.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

assert LOCK["schema"] == 1
assert LOCK["mesa"]["version"] == "26.2.2"
assert LOCK["runtime"]["sha256"] == "307c4ad9af58217a5f58ca936cf36984edff8efa43a857bd062e185b56a162f3"
assert set(LOCK["runtime"]["links"]) == {
    "lib/aarch64-linux-gnu/libEGL_mesa.so",
    "lib/aarch64-linux-gnu/libEGL_mesa.so.0",
    "lib/aarch64-linux-gnu/libgbm.so",
    "lib/aarch64-linux-gnu/libgbm.so.1",
}
assert MODULE.normalized("./lib/a.so") == "lib/a.so"
for rejected in ("/lib/a.so", "../lib/a.so", "lib/../a.so", "lib//a.so"):
    try:
        MODULE.normalized(rejected)
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe path accepted: " + rejected)

session = (REPO / "mainline/gaming-wayland/session.sh").read_text(encoding="utf-8")
builder = (REPO / "mainline/gaming-wayland/build-handheld.sh").read_text(encoding="utf-8")
packager = (REPO / "mainline/gaming-wayland/check-session.sh").read_text(encoding="utf-8")
assert 'GBM_BACKENDS_PATH="$lib/gbm"' in session
assert '__EGL_VENDOR_LIBRARY_FILENAMES="$base/usr/share/glvnd/egl_vendor.d/50_mesa.json"' in session
assert 'runtime.py" validate-runtime "$mesa"' in builder
assert '--tmpfs /run:rw,nosuid,nodev,exec,size=192m,mode=755' in builder
assert 'runtime.py install /mesa-runtime.tar.gz "$stage/usr"' in packager
assert 'mktemp -d /out/r46h-handheld-package.' in packager
assert "'mesa_runtime_revision': 60" in packager
assert "'status': 'HANDHELD_HOST_PASS_R46H_UNTESTED'" in packager

print("R46H_GAMING_MESA_TEST_PASS")
