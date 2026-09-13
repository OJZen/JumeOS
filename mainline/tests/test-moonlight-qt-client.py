#!/usr/bin/env python3
"""Check the portable Qt wrapper without running Moonlight or creating keys."""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

repo = Path(__file__).resolve().parents[2]
cache = repo / "mainline/out/.cache"
cache.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="moonlight-qt-env-", dir=cache) as temporary:
    root = Path(temporary) / "package with spaces"
    binary = root / "usr/bin/moonlight-qt"
    binary.parent.mkdir(parents=True)
    binary.write_text('''#!/bin/sh
printf '%s\n' "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME" \
    "$LD_LIBRARY_PATH" "$QT_PLUGIN_PATH" "$QML_IMPORT_PATH" \
    "$XDG_RUNTIME_DIR" "$@"
exit 7
''')
    binary.chmod(0o755)
    wrapper = root / "qt-client.sh"
    shutil.copyfile(repo / "mainline/gaming-moonlight/qt-client.sh", wrapper)
    env = {"PATH": os.defpath, "XDG_RUNTIME_DIR": "/run/user/1000"}
    result = subprocess.run(
        ["/bin/sh", str(wrapper), "stream", "host with spaces", "game"],
        env=env, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 7, result.stderr
    lib = root / "usr/lib/aarch64-linux-gnu"
    assert result.stdout.splitlines() == [
        str(root / "state/config"), str(root / "state/cache"),
        str(root / "state/data"), f"{lib}:{lib}/libproxy",
        str(lib / "qt6/plugins"), str(lib / "qt6/qml"),
        "/run/user/1000", "stream", "host with spaces", "game",
    ]
    for directory in (root / "state").rglob("*"):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o700
result = subprocess.run([sys.executable, "-B", str(repo / "mainline/gaming-moonlight/sunshine-pin.py"), "/unused"],
                        stdin=subprocess.DEVNULL, capture_output=True, timeout=5)
assert result.returncode == 2 and not result.stderr  # Refuse echoed/non-terminal PIN input before reading state.
print("Moonlight Qt wrapper/private state and Sunshine hidden-PIN boundary PASS")
