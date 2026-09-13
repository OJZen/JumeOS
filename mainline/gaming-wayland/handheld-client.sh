#!/bin/sh
# One diagnostic launcher and a separate controller-test process; no installed service.
set -eu
[ "$#" -eq 2 ] || exit 2
role=$1
output=$2
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
case "$base:$output" in *[[:space:]\;=\"\\]*) exit 2;; esac
case "$output" in /*) ;; *) exit 2;; esac
unset R46H_SHELL_LOG
case "${R46H_DEVICE_CONTROLS:-0}" in 0|1) ;; *) exit 2;; esac
if [ "$role" = game ]; then
    unset R46H_DEVICE_CONTROLS
    export R46H_SHELL_STATE_DIR="$output/game-state"
    exec "$base/shell-client.sh" --scene controller --fullscreen --quit-after 240
fi
[ "$role" = ui ] || exit 2
if [ -f "$base/MOONLIGHT_SHA256" ]; then
    client_hash=$(cat "$base/MOONLIGHT_SHA256")
    [ "${#client_hash}" = 64 ] && [ "$(sha256sum "$base/usr/bin/moonlight-qt" | cut -d ' ' -f 1)" = "$client_hash" ]
    export R46H_VIRTUAL_KEYBOARD=1
    set -- --scene streaming --moonlight-client "$base/usr/bin/moonlight-qt" --moonlight-sha256 "$client_hash"
else
cat > "$output/applications.json" <<JSON
{"version":1,"applications":[{"id":"diagnostic.controller","title":"独立摇杆测试","program":"$base/handheld-client.sh","arguments":["game","$output"]}]}
JSON
    set -- --applications "$output/applications.json"
fi
export R46H_SHELL_STATE_DIR="${R46H_SHELL_STATE_DIR:-$output/ui-state}"
exec "$base/shell-client.sh" --fullscreen --quit-after 290 \
    "$@" --control-dir "$output/control" \
    --handheld-router "$base/usr/bin/input-router" --input-device "$R46H_ROUTED_SOURCE" --uinput-fd 7
