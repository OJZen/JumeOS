#!/bin/bash
# Temporary p2 v0.17 test launcher; staging and pairing must already exist.
set -Eeuo pipefail
client=embedded
if [[ ${1:-} == --qt ]]; then client=qt; shift; fi
if [[ $client == qt ]]; then
  [[ $# == 2 && $2 =~ ^[0-9a-f]{64}$ ]] || { echo 'Usage: run-stream.sh --qt HOST BINARY_SHA256' >&2; exit 2; }
  expected_binary=$2
else
  [[ $# == 1 ]] || { echo 'Usage: run-stream.sh HOST' >&2; exit 2; }
fi
[[ -n $1 && $1 != -* ]] || exit 2
server=$1
scope=/run/r46h-moonlight-test
if [[ $client == qt ]]; then scope=/run/r46h-moonlight-qt-test; fi
[[ $EUID == 0 ]]
root_uuid=$(findmnt -rn -o UUID /)
[[ $root_uuid == d3130017-46a4-4d56-9001-000000000017 || $root_uuid == d3130018-46a4-4d56-9001-000000000018 ]]
[[ $(uname -r) == 6.12.99-r46h-mainline-v0.15-gaming-product ]]
[[ $(cat /sys/class/block/mmcblk0/device/cid) == fe343253440000002000002d57019567 ]]
[[ $(stat -c %U:%a "$scope") == ark:700 ]]
if [[ $client == qt ]]; then
  [[ -x $scope/qt-client.sh && -x $scope/usr/bin/moonlight-qt ]] || exit 1
  [[ -f "$scope/state/config/Moonlight Game Streaming Project/Moonlight.conf" ]] || exit 1
  [[ $(sha256sum "$scope/usr/bin/moonlight-qt" | cut -d ' ' -f 1) == "$expected_binary" ]] || exit 1
  closure=$(LD_LIBRARY_PATH="$scope/usr/lib/aarch64-linux-gnu:$scope/usr/lib/aarch64-linux-gnu/libproxy" ldd "$scope/usr/bin/moonlight-qt") || exit 1
  [[ $closure != *'not found'* && $closure != *'not a dynamic executable'* ]] || exit 1
else
  [[ -x $scope/opt/r46h-moonlight-test/bin/moonlight && -d $scope/keys ]] || exit 1
fi
process_status=0
# Match argv: PPSSPP renames RetroArch's comm to Main. Negation is not an errexit guard.
pgrep -u 1000 -f '(^|/)(retroarch|moonlight(-qt)?|r46h-shell)([[:space:]]|$)' >/dev/null || process_status=$?
[[ $process_status == 1 ]] || { echo 'Refusing probe: game/client active or process check failed.' >&2; exit 1; }
systemctl is-active --quiet r46h-gaming-frontend.service
mapping=$(sed -n '/^readonly CONTROLLER_MAPPING=/p' /usr/local/sbin/r46h-es-de-ui | cut -d "'" -f 2)
[[ $mapping == 06004e84465200004800000001000000,* ]]
saved_mux=$(amixer -c 0 cget numid=5 | awk -F= '/: values=/{print $2}')
[[ $saved_mux =~ ^[0-9]+$ ]]
unit=r46h-stream-probe-$$.service
restore() {
  result=$?
  trap - EXIT
  set +e
  if ! systemctl stop "$unit" 2>/dev/null; then
    [[ $(systemctl show -p LoadState --value "$unit") == not-found ]] || {
      echo 'STREAM_END failed to stop client; frontend left stopped.' >&2; exit 1;
    }
  fi
  amixer -q -c 0 cset numid=5 "$saved_mux"
  mux_status=$?
  systemctl start r46h-gaming-frontend.service
  frontend_status=$?
  if (( frontend_status == 0 )); then
    systemctl is-active --quiet r46h-gaming-frontend.service
    frontend_status=$?
  fi
  printf 'STREAM_END status=%s mux_restore=%s frontend_restore=%s\n' "$result" "$mux_status" "$frontend_status"
  if (( mux_status || frontend_status )); then exit 1; fi
  exit "$result"
}
trap restore EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
systemctl stop r46h-gaming-frontend.service
amixer -q -c 0 cset numid=5 0
# Both clients share the same identity, busy guard, mixer and cgroup recovery.
if [[ $client == qt ]]; then
  deadline=120
  client_env=(QT_QPA_PLATFORM=eglfs QT_QPA_EGLFS_INTEGRATION=eglfs_kms
    SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT=0x5246/0x0048)
  client_log="$scope/client-qt.log"
  command=("$scope/qt-client.sh" stream "$server" 'R46H Desktop Test'
    --resolution 640x480 --fps 60 --bitrate 4000 --video-codec H.264
    --video-decoder hardware --audio-config stereo --performance-overlay
    --no-game-optimization --no-hdr --no-yuv444 --no-quit-after)
  printf 'STREAM_BEGIN client=qt codec=h264 width=640 height=480 fps=60 bitrate=4000 decoder=hardware audio=native hud=native exit=L1+R1 limit=120s\n'
else
  deadline=300
  client_env=(LD_LIBRARY_PATH="$scope/opt/r46h-moonlight-test/lib" SDL_RENDER_DRIVER=opengles2 SDL_AUDIO_SAMPLES=1024)
  client_log="$scope/client-hud.log"
  command=(/usr/bin/stdbuf -oL -eL "$scope/opt/r46h-moonlight-test/bin/moonlight" stream
    -platform sdl -codec h264 -width 640 -height 480 -fps 60 -bitrate 4000
    -nosops -app 'R46H Desktop Test' -keydir "$scope/keys"
    -mapping "$scope/opt/r46h-moonlight-test/share/moonlight/gamecontrollerdb.txt"
    -verbose "$server")
  printf 'STREAM_BEGIN client=embedded codec=h264 width=640 height=480 fps=60 bitrate=4000 decoder=software audio_samples=1024 hud=fps-cpu exit=L1+R1 limit=300s\n'
fi
systemd-run --quiet --wait --pipe --collect --service-type=exec --unit="$unit" \
  -p RuntimeMaxSec="$deadline" -p TimeoutStopSec=10 -p KillMode=control-group \
  /usr/bin/setsid --wait /usr/bin/openvt -e -c 2 -s -f -- \
  /usr/sbin/runuser -u ark -- /usr/bin/env \
  XDG_RUNTIME_DIR=/run/user/1000 SDL_VIDEODRIVER=kmsdrm SDL_AUDIODRIVER=alsa \
  SDL_GAMECONTROLLERCONFIG="$mapping" "${client_env[@]}" \
  /bin/sh -c 'log=$1; shift; exec "$@" > "$log" 2>&1' sh "$client_log" "${command[@]}"
