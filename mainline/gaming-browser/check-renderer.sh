#!/bin/bash
# Container-only offline smoke test, with a real unprivileged Chromium sandbox.
set -Eeuo pipefail
[[ -f /.dockerenv && -f /out/jume-browser-arm64.tar.gz ]] || exit 2
stage=$(mktemp -d /out/renderer.XXXXXX)
runtime=$(mktemp -d /run/jume-browser.XXXXXX)
weston_pid= xvfb_pid=
cleanup() {
    [[ ! -f $runtime/weston.log ]] || cp "$runtime/weston.log" /out/renderer-weston.log
    [[ ! -f $runtime/xvfb.log ]] || cp "$runtime/xvfb.log" /out/renderer-xvfb.log
    if [[ -n $weston_pid ]]; then kill "$weston_pid" 2>/dev/null || true; wait "$weston_pid" 2>/dev/null || true; fi
    if [[ -n $xvfb_pid ]]; then kill "$xvfb_pid" 2>/dev/null || true; wait "$xvfb_pid" 2>/dev/null || true; fi
    rm -rf -- "$stage" "$runtime"
}
trap cleanup EXIT
tar -xzf /out/jume-browser-arm64.tar.gz -C "$stage"
[[ $(stat -c %a "$stage") == 755 ]] # Archive must be traversable by the desktop user.
mkdir -m 700 "$stage/state"
chown nobody:nogroup "$stage/state" "$runtime"
export XDG_RUNTIME_DIR="$runtime" WAYLAND_DISPLAY=jume-browser-check LANG=C.UTF-8 XDG_CACHE_HOME="$runtime/cache"
# Weston headless has no seat: it cannot activate a client's IME. Nested X11
# gives this offline fixture a real Wayland keyboard seat, not a mocked focus.
runuser -u nobody -- Xvfb -displayfd 3 -screen 0 1024x768x24 -nolisten tcp 3>"$runtime/display" >"$runtime/xvfb.log" 2>&1 &
xvfb_pid=$!
for attempt in {1..60}; do [[ ! -s $runtime/display ]] || break; kill -0 "$xvfb_pid"; sleep .1; done
export DISPLAY=":$(cat "$runtime/display")"
runuser -u nobody -- env EGL_PLATFORM=x11 LIBGL_ALWAYS_SOFTWARE=1 LP_NUM_THREADS=2 \
    weston --backend=x11 --renderer=gl --width=1024 --height=768 --idle-time=0 \
    --no-config --shell=kiosk-shell.so --socket="$WAYLAND_DISPLAY" --log="$runtime/weston.log" &
weston_pid=$!
for attempt in {1..60}; do [[ ! -S $runtime/$WAYLAND_DISPLAY ]] || break; kill -0 "$weston_pid"; sleep .1; done
timeout 8 xdotool search --sync --onlyvisible --class 'weston' windowfocus
set +e
runuser -u nobody -- env QT_QPA_PLATFORM=wayland \
    LD_LIBRARY_PATH="$stage/usr/lib/aarch64-linux-gnu:$stage/usr/lib/aarch64-linux-gnu/libproxy" \
    QT_PLUGIN_PATH="$stage/usr/lib/aarch64-linux-gnu/qt6/plugins" \
    QML_IMPORT_PATH="$stage/usr/lib/aarch64-linux-gnu/qt6/qml" \
    QTWEBENGINEPROCESS_PATH="$stage/usr/lib/qt6/libexec/QtWebEngineProcess" \
    QTWEBENGINE_RESOURCES_PATH="$stage/usr/share/qt6/resources" \
    QTWEBENGINE_LOCALES_PATH="$stage/usr/share/qt6/translations/qtwebengine_locales" \
    LIBGL_ALWAYS_SOFTWARE=1 LP_NUM_THREADS=2 \
    timeout 75 "$stage/browser-client.sh" --state-dir "$stage/state" --self-test > /out/renderer-check.log 2>&1
result=$?
set -e
[[ ! -f $stage/state/smoke.png ]] || cp "$stage/state/smoke.png" /out/smoke.png
cp "$runtime/weston.log" /out/renderer-weston.log
cat /out/renderer-check.log
exit "$result"
