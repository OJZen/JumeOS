#!/bin/bash
# Real original SDL2/Mono engines, isolated input and writable state; no original launchers.
set -Eeuo pipefail
[[ -f /.dockerenv && -d /code && -d /content/ports && -x /mono/bin/mono ]] || exit 2
mkdir -p /out/ports
dpkg -i /debs/*.deb /wayland-debs/weston_*.deb /wayland-debs/libqt6waylandclient6_*.deb > /out/ports/setup.log 2>&1
cmake -S /src -B /out/linux-build -DCMAKE_BUILD_TYPE=Release
cmake --build /out/linux-build -j 3
gcc -shared -fPIC -O2 -Wall -Wextra -Werror $(pkg-config --cflags sdl2) \
  /project/mainline/gaming-ports/gta-gl-profile.c -o /out/gta-gl-profile.so -ldl
timeout 20 python3 -B /tests/test-local-port-process.py > /out/ports/process-check.log 2>&1
export XDG_RUNTIME_DIR=$(mktemp -d /run/r46h-ports-gl.XXXXXX)
export WAYLAND_DISPLAY=r46h-ports-test QT_QPA_PLATFORM=wayland QT_QUICK_BACKEND=software SDL_NO_SIGNAL_HANDLERS=1
export QT_PLUGIN_PATH=/out/qt-wayland/usr/lib/aarch64-linux-gnu/qt6/plugins LIBGL_ALWAYS_SOFTWARE=1
export R46H_GTA_GL_PROFILE=/out/gta-gl-profile.so
EGL_PLATFORM=surfaceless weston --backend=headless --renderer=gl --width=640 --height=480 --no-config --idle-time=0 \
  --shell=/out/handheld-shell.so --socket="$WAYLAND_DISPLAY" --log=/out/ports/weston.log > /out/ports/weston-stderr.log 2>&1 &
compositor=$!
cleanup() { kill "$compositor" 2>/dev/null || true; wait "$compositor" 2>/dev/null || true; rm -rf -- "$XDG_RUNTIME_DIR"; }
trap cleanup EXIT
for attempt in $(seq 1 50); do
  [[ ! -S $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY ]] || break
  kill -0 "$compositor"; sleep .1
done
mknod /dev/uinput c 10 223
timeout 130 python3 -B /wayland/test-ports.py
