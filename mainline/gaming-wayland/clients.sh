#!/bin/sh
set -eu
[ "$#" -eq 2 ] && { [ "$1" = headless ] || [ "$1" = drm ]; } || exit 2
mode=$1
output=$2
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
exec > "$output/clients.log" 2>&1
background=''
cleanup() {
    [ -z "$background" ] || kill "$background" 2>/dev/null || true
    [ -z "$background" ] || wait "$background" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
if [ "$mode" = headless ]; then background_seconds=8; else background_seconds=300; fi
XDG_CONFIG_HOME="$output/background-config" XDG_DATA_HOME="$output/background-data" \
    "$base/usr/bin/r46h-shell" --state-dir "$output/background-state" --scene session \
    --quit-after "$background_seconds" > "$output/background.log" 2>&1 &
background=$!
if [ "$mode" = headless ]; then
    set -- --capture "$output/quick-wayland.png"
else
    set -- --quit-after 290
fi
XDG_CONFIG_HOME="$output/foreground-config" XDG_DATA_HOME="$output/foreground-data" \
    "$base/usr/bin/r46h-shell" --state-dir "$output/foreground-state" --scene quick \
    "$@" > "$output/foreground.log" 2>&1
kill -0 "$background"
# Let Qt destroy its surfaces before stopping the compositor; the trap handles failures.
wait "$background"
background=''
printf 'WAYLAND_CLIENTS_PASS simultaneous_processes=2 backend=%s input_isolation=UNTESTED\n' "$mode"
