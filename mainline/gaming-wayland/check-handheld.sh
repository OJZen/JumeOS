#!/bin/bash
# Runs only inside the disposable, pinned ARM64 development container.
set -Eeuo pipefail
[[ -f /.dockerenv && -d /src/protocol && -d /out ]] || exit 2
renderer=${R46H_TEST_RENDERER:-pixman}
[[ $renderer == pixman || $renderer == gl ]] || exit 2
dpkg -i /debs/*.deb /wayland-debs/libqt6waylandclient6_*.deb /wayland-debs/weston_*.deb > /out/setup.log 2>&1
mkdir -p /out/build /out/images /out/qt-wayland
# Only client plugins are needed; do not install the unrelated Qt compositor.
dpkg-deb -x /wayland-debs/qt6-wayland_*.deb /out/qt-wayland
wayland-scanner client-header /src/protocol/weston-output-capture.xml /out/build/weston-output-capture-client-protocol.h
wayland-scanner private-code /src/protocol/weston-output-capture.xml /out/build/capture-protocol.c
gcc -fPIC -c /out/build/capture-protocol.c -o /out/build/capture-protocol.o $(pkg-config --cflags wayland-client)
g++ -shared -fPIC -std=gnu++17 -O2 -Wall -Wextra -Werror /src/handheld-shell.cpp -o /out/handheld-shell.so $(pkg-config --cflags --libs libweston-14 Qt6Core)
g++ -fPIC -std=gnu++17 -O2 -Wall -Wextra -Werror -I/out/build /src/capture.cpp /src/test-shell.cpp /out/build/capture-protocol.o -o /out/test-shell $(pkg-config --cflags --libs Qt6Gui Qt6Network wayland-client libdrm)
g++ -fPIC -std=gnu++17 -O2 -Wall -Wextra -Werror /src/test-client.cpp -o /out/test-client $(pkg-config --cflags --libs Qt6Quick sdl2)
export XDG_RUNTIME_DIR=$(mktemp -d /run/r46h-wm.XXXXXX)
export WAYLAND_DISPLAY=r46h-compositor-test
export QT_PLUGIN_PATH=/out/qt-wayland/usr/lib/aarch64-linux-gnu/qt6/plugins
export LD_LIBRARY_PATH=/out/qt-wayland/usr/lib/aarch64-linux-gnu
export LIBGL_ALWAYS_SOFTWARE=1 LP_NUM_THREADS=2 LANG=C.UTF-8
if [[ $renderer == pixman ]]; then export QT_QUICK_BACKEND=software; else unset QT_QUICK_BACKEND; fi
EGL_PLATFORM=surfaceless weston --backend=headless --renderer="$renderer" --width=640 --height=480 --idle-time=0 --no-config --socket=$WAYLAND_DISPLAY --shell=/out/handheld-shell.so --log=/out/weston.log > /out/weston-stderr.log 2>&1 &
weston_pid=$!
export R46H_TEST_WESTON_PID=$weston_pid
cleanup() {
    kill "$weston_pid" 2>/dev/null || true
    wait "$weston_pid" 2>/dev/null || true
    rm -rf -- "$XDG_RUNTIME_DIR"
}
trap cleanup EXIT
for attempt in $(seq 1 40); do
    [[ ! -S $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY ]] || break
    kill -0 "$weston_pid"
    sleep .1
done
QT_QPA_PLATFORM=wayland timeout 25 /out/test-shell /out/test-client /out/images
wait "$weston_pid"
! grep -E 'BUG:|assertion.*failed' /out/weston.log /out/weston-stderr.log
