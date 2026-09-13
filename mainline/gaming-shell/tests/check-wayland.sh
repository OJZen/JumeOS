#!/bin/sh
# Disposable host-only Wayland proof. No DRM device, seat, host input or network.
set -eu
[ "$#" -eq 2 ] || { echo 'Usage: check-wayland.sh BINARY EXTERNAL_OUTPUT' >&2; exit 2; }
binary=$1
output=$2
case "$binary:$output" in /*:/*) ;; *) exit 2 ;; esac
mkdir -p "$output"
export XDG_RUNTIME_DIR
XDG_RUNTIME_DIR=$(mktemp -d "$output/runtime.XXXXXX")
chmod 700 "$XDG_RUNTIME_DIR"
export TMPDIR="$output"
export QML_DISABLE_DISK_CACHE=1
export QT_SHADER_CACHE_PATH="$output/shader-cache"
export QT_QUICK_BACKEND=software
export QT_QPA_PLATFORM=wayland
export WAYLAND_DISPLAY=r46h-shell-probe
compositor=''
background=''
cleanup() {
    [ -z "$background" ] || kill "$background" 2>/dev/null || true
    [ -z "$background" ] || wait "$background" 2>/dev/null || true
    [ -z "$compositor" ] || kill "$compositor" 2>/dev/null || true
    [ -z "$compositor" ] || wait "$compositor" 2>/dev/null || true
    rm -rf -- "$XDG_RUNTIME_DIR"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Weston 14 (Debian 13). Headless deliberately does not test the GLES/DRM path.
weston --backend=headless-backend.so --renderer=pixman --width=1024 --height=768 \
    --socket="$WAYLAND_DISPLAY" --idle-time=0 --log="$output/weston.log" > "$output/weston-stderr.log" 2>&1 &
compositor=$!
for attempt in $(seq 1 100); do
    [ ! -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ] || break
    kill -0 "$compositor"
    sleep 0.1
done
[ -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]
"$binary" --state-dir "$output/background-state" --scene session --quit-after 20 > "$output/background.log" 2>&1 &
background=$!
"$binary" --state-dir "$output/foreground-state" --scene quick --capture "$output/quick-wayland.png" > "$output/foreground.log" 2>&1
kill -0 "$background"
printf 'WAYLAND_CLIENTS_PASS simultaneous_processes=2 renderer=software hardware_overlay=UNTESTED input_isolation=UNTESTED\n'
