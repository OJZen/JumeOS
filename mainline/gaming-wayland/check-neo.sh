#!/bin/bash
# Real FBNeo/RetroArch in the isolated ARM64 GL compositor; original content is read-only.
set -Eeuo pipefail
[[ -f /.dockerenv && -d /wayland && -d /gaming-debs && -d /content/neogeo ]] || exit 2
mkdir -p /out/native-gl
dpkg -i /debs/*.deb /wayland-debs/weston_*.deb /wayland-debs/libqt6waylandclient6_*.deb \
  /gaming-debs/retroarch_*.deb /gaming-debs/retroarch-assets_*.deb /gaming-debs/libretro-core-info_*.deb \
  /gaming-debs/libjack-jackd2-0_*.deb /gaming-debs/libqt5*.deb /gaming-debs/libv4l-*.deb /gaming-debs/libv4lconvert*.deb \
  /gaming-debs/fonts-droid-fallback_*.deb /gaming-debs/fonts-noto-extra_*.deb /gaming-debs/fonts-roboto-unhinted_*.deb \
  /gaming-debs/libxcb-xinerama0_*.deb > /out/native-gl/setup.log 2>&1
[[ $(sha256sum /usr/local/libexec/fbneo_neogeo_libretro.so | cut -d ' ' -f 1) == 8bb17a551f3eeeb384ab00a5c5375d30eb63807afe5b6c1ba1d3f78220732bdb ]]
cmake -S /src -B /out/linux-build -DCMAKE_BUILD_TYPE=Release
cmake --build /out/linux-build -j 3
/out/linux-build/tools-check
g++ -fPIC -std=gnu++17 -O2 -Wall -Wextra -Werror /wayland/test-client.cpp -o /out/test-client $(pkg-config --cflags --libs Qt6Quick sdl2)
export XDG_RUNTIME_DIR=$(mktemp -d /run/r46h-neo-gl.XXXXXX)
export WAYLAND_DISPLAY=r46h-neo-test QT_QPA_PLATFORM=wayland QT_QUICK_BACKEND=software SDL_NO_SIGNAL_HANDLERS=1
export QT_PLUGIN_PATH=/out/qt-wayland/usr/lib/aarch64-linux-gnu/qt6/plugins LIBGL_ALWAYS_SOFTWARE=1
EGL_PLATFORM=surfaceless weston --backend=headless --renderer=gl --width=640 --height=480 --no-config --idle-time=0 \
  --shell=/out/handheld-shell.so --socket="$WAYLAND_DISPLAY" --log=/out/native-gl/weston.log > /out/native-gl/weston-stderr.log 2>&1 &
compositor=$!
cleanup() { kill "$compositor" 2>/dev/null || true; wait "$compositor" 2>/dev/null || true; rm -rf -- "$XDG_RUNTIME_DIR"; }
trap cleanup EXIT
for attempt in $(seq 1 50); do
  [[ ! -S $XDG_RUNTIME_DIR/$WAYLAND_DISPLAY ]] || break
  kill -0 "$compositor"; sleep .1
done
mknod /dev/uinput c 10 223
timeout 100 python3 -B /wayland/test-neo.py
