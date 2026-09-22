#!/bin/bash
set -Eeuo pipefail
[[ -f /.dockerenv && -d /wayland && -d /out ]] || exit 2
renderer=${R46H_TEST_RENDERER:-pixman}
[[ $renderer == pixman || $renderer == gl ]] || exit 2
[[ -f /out/share/fonts/truetype/droid/DroidSansFallbackFull.ttf ]] || { echo 'Prepare the retained shell bundle font in /out/share first.' >&2; exit 2; }
dpkg -i /debs/*.deb /wayland-debs/libqt6waylandclient6_*.deb /wayland-debs/weston_*.deb > /out/desktop-setup.log 2>&1
cmake -S /src -B /out/linux-build -DCMAKE_BUILD_TYPE=Release
cmake --build /out/linux-build -j 3
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software /out/linux-build/shell-check virtualControllerEvents virtualControllerHandover routedControllerEvents applicationManifestAndForegroundLifecycle streamingProfilesAndWorker streamingNavigation terminalEntryKeyboardMouseAndPrivacy browserEntryAndPrivacy filesEntriesAndPrivacy volumeHudAndAtomicUpdates
g++ -std=c++17 -Wall -Wextra -Werror -O2 /wayland/input-router.cpp -o /out/input-router
g++ -shared -fPIC -std=gnu++17 -O2 -Wall -Wextra -Werror /wayland/handheld-shell.cpp -o /out/handheld-shell.so $(pkg-config --cflags --libs libweston-14 Qt6Core)
g++ -fPIC -std=gnu++17 -O2 -Wall -Wextra -Werror /wayland/test-client.cpp -o /out/test-client $(pkg-config --cflags --libs Qt6Quick sdl2)
export XDG_RUNTIME_DIR=$(mktemp -d /run/r46h-desktop.XXXXXX)
export WAYLAND_DISPLAY=r46h-desktop-test QT_QPA_PLATFORM=wayland SDL_NO_SIGNAL_HANDLERS=1
export LIBGL_ALWAYS_SOFTWARE=1 LP_NUM_THREADS=2 LANG=C.UTF-8
if [[ $renderer == pixman ]]; then export QT_QUICK_BACKEND=software; else unset QT_QUICK_BACKEND; fi
export QT_PLUGIN_PATH=/out/qt-wayland/usr/lib/aarch64-linux-gnu/qt6/plugins
export LD_LIBRARY_PATH=/out/qt-wayland/usr/lib/aarch64-linux-gnu
EGL_PLATFORM=surfaceless weston --backend=headless --renderer="$renderer" --width=640 --height=480 --idle-time=0 --no-config --socket=$WAYLAND_DISPLAY --shell=/out/handheld-shell.so --log=/out/desktop-weston.log > /out/desktop-weston-stderr.log 2>&1 &
weston_pid=$!
export R46H_TEST_WESTON_PID=$weston_pid R46H_SHELL_LOG=1
cleanup() { kill "$weston_pid" 2>/dev/null || true; wait "$weston_pid" 2>/dev/null || true; rm -rf -- "$XDG_RUNTIME_DIR"; }
trap cleanup EXIT
for attempt in $(seq 1 40); do
    [[ ! -S $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY ]] || break
    kill -0 "$weston_pid"; sleep .1
done
mknod /dev/uinput c 10 223
timeout 70 python3 -B /wayland/test-desktop.py
