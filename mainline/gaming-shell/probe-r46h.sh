#!/bin/bash
# Prepared attended probe, not an installer. Stage the receipt-bound tar first.
set -Eeuo pipefail
[[ ( $# == 2 && ( $1 == --check || $1 == --run || $1 == --profile || $1 == --device || $1 == --native || $1 == --ports || $1 == --attended-ports ) || $# == 3 && ( $1 == --streaming || $1 == --attended ) || $# == 5 && ( $1 == --remote || $1 == --remote-device || $1 == --remote-native || $1 == --remote-ports ) || $# == 6 && $1 == --remote-streaming ) && $2 =~ ^[0-9a-f]{64}$ ]] || {
  echo 'Usage: probe-r46h.sh --check|--run|--profile|--device|--native|--ports|--attended-ports SHELL_SHA256 | --streaming|--attended SHELL_SHA256 CLIENT_SHA256 | --remote|--remote-device|--remote-native|--remote-ports SHELL_SHA256 PUBLIC_KEY_SHA256 DEVICE_IP MAC_IP | --remote-streaming SHELL_SHA256 CLIENT_SHA256 PUBLIC_KEY_SHA256 DEVICE_IP MAC_IP' >&2; exit 2;
}
mode=$1
expected=$2
client_hash=${3:-}
listen_ip=${4:-}
peer_ip=${5:-}
public_key_hash=${3:-}
if [[ $mode == --remote-streaming ]]; then public_key_hash=$4;listen_ip=$5;peer_ip=$6;fi
saved_mux=
device_mode=0
[[ $mode != --device && $mode != --remote-device ]] || device_mode=1
scope=/run/r46h-shell-probe
[[ $EUID == 0 && $(uname -r) == 6.12.99-r46h-mainline-v0.15-gaming-product ]]
[[ $(findmnt -rn -o UUID /) == d3130017-46a4-4d56-9001-000000000017 ]]
[[ $(cat /sys/class/block/mmcblk0/device/cid) == fe343253440000002000002d57019567 ]]
[[ $(cat /sys/class/block/mmcblk0/size) == 122138624 ]]
[[ ,$(findmnt -rn -o OPTIONS /roms), == *,ro,* ]]
[[ -d $scope && ! -L $scope && ( $(stat -c %U:%a "$scope") == ark:700 || $(stat -c %U:%a "$scope") == root:755 ) ]]
[[ -x $scope/usr/bin/r46h-shell && -x $scope/shell-client.sh ]]
[[ $(sha256sum "$scope/usr/bin/r46h-shell" | cut -d ' ' -f 1) == "$expected" ]]
for service in r46h-gaming-input r46h-volume-keys r46h-gaming-frontend; do
  systemctl is-active --quiet "$service.service"
done
process_status=0
# Match argv: PPSSPP renames RetroArch's comm to Main. Negation is not an errexit guard.
pgrep -u 1000 -f '(^|/)(retroarch|moonlight(-qt)?|r46h-shell|re3|reVC|mono(-sgen)?)([[:space:]]|$)' >/dev/null || process_status=$?
[[ $process_status == 1 ]] || { echo 'Refusing probe: game/client active or process check failed.' >&2; exit 1; }
mapping=$(sed -n '/^readonly CONTROLLER_MAPPING=/p' /usr/local/sbin/r46h-es-de-ui | cut -d "'" -f 2)
[[ $mapping == 06004e84465200004800000001000000,* ]]
[[ -c /dev/dri/card0 && -c /dev/dri/renderD128 ]]
closure=$(LD_LIBRARY_PATH="$scope/usr/lib/aarch64-linux-gnu:$scope/usr/lib/aarch64-linux-gnu/libproxy" ldd "$scope/usr/bin/r46h-shell")
if [[ $closure == *'not found'* ]]; then
  echo 'Refusing probe: runtime dependency missing.' >&2; exit 1
fi
if [[ $mode == --streaming || $mode == --attended || $mode == --remote-streaming ]]; then
  [[ $client_hash =~ ^[0-9a-f]{64}$ && -x $scope/usr/bin/moonlight-qt && -x $scope/desktop-session.sh ]] || exit 1
  [[ $(sha256sum "$scope/usr/bin/moonlight-qt" | cut -d ' ' -f 1) == "$client_hash" ]] || exit 1
  client_closure=$(LD_LIBRARY_PATH="$scope/usr/lib/aarch64-linux-gnu:$scope/usr/lib/aarch64-linux-gnu/libproxy" ldd "$scope/usr/bin/moonlight-qt") || exit 1
  [[ $client_closure != *'not found'* ]] || exit 1
  saved_mux=$(amixer -c 0 cget numid=5 | awk -F= '/: values=/{print $2}')
  [[ $saved_mux =~ ^[0-9]+$ ]] || exit 1
fi
if [[ $mode == --native || $mode == --remote-native || $mode == --ports || $mode == --attended-ports || $mode == --remote-ports ]]; then
  [[ -x $scope/desktop-session.sh && -x /usr/bin/retroarch && -f /etc/r46h/retroarch.cfg ]] || exit 1
  saved_mux=$(amixer -c 0 cget numid=5 | awk -F= '/: values=/{print $2}')
  [[ $saved_mux =~ ^[0-9]+$ ]] || exit 1
fi
if [[ $mode == --remote || $mode == --remote-device || $mode == --remote-streaming || $mode == --remote-native || $mode == --remote-ports ]]; then
  [[ $public_key_hash =~ ^[0-9a-f]{64}$ && -x $scope/remote-session.sh && -f $scope/remote-client.pub && ! -L $scope/remote-client.pub ]]
  (( $(stat -c %s "$scope/remote-client.pub") <= 1024 ))
  [[ $(sha256sum "$scope/remote-client.pub" | cut -d ' ' -f 1) == "$public_key_hash" ]]
  [[ -x /usr/sbin/sshd ]]
  [[ $(cat /sys/class/power_supply/rk817-charger/online) == 1 ]] || { echo 'Remote preview requires external power.' >&2; exit 1; }
  remote_listeners=$(ss -H -ltn 'sport = :22222') || exit 1
  [[ -z $remote_listeners ]] || { echo 'Remote control port is already occupied.' >&2; exit 1; }
fi
if (( ${device_mode:-0} )); then
  [[ -x $scope/device-lease.sh && ! -L $scope/device-lease.sh && ! -e /run/r46h-device-lease && ! -L /run/r46h-device-lease ]]
  [[ ! -L $scope/state && ( ! -e $scope/state || $(stat -c %U:%a "$scope/state") == ark:700 ) ]]
  [[ -z $(find "$scope" -path "$scope/state" -prune -o -type f -links +1 -print -quit) ]]
  [[ $(cat /sys/class/power_supply/rk817-charger/online) == 1 ]] || { echo 'Device controls require external power.' >&2; exit 1; }
  # Code used by root ExecStartPre/ExecStopPost must be protected from the GUI user.
  find "$scope" -path "$scope/state" -prune -o -exec chown -h root:root {} +
  find "$scope" -path "$scope/state" -prune -o ! -type l -exec chmod go-w {} +
  chmod 755 "$scope"
  install -d -o ark -g ark -m 700 "$scope/state"
fi
if [[ -n ${R46H_SHELL_STATE_DIR:-} ]]; then
  [[ $R46H_SHELL_STATE_DIR == /home/ark/.local/share/r46h-preview ]] || { echo 'Unrecognized persistent preview state path.' >&2; exit 2; }
  runuser -u ark -- env R46H_SHELL_STATE_DIR="$R46H_SHELL_STATE_DIR" "$scope/shell-client.sh" --check-state || exit 1
fi
if [[ $mode == --ports || $mode == --attended-ports || $mode == --remote-ports ]]; then
  [[ ${R46H_SHELL_STATE_DIR:-} == /home/ark/.local/share/r46h-preview && -x $scope/runtime-lease.sh ]] || exit 2
  [[ ! -e /run/r46h-port-runtime && ! -L /run/r46h-port-runtime && ! -e $scope/mono && ! -L $scope/mono ]] || exit 2
  [[ ! -L $scope/state && ( ! -e $scope/state || $(stat -c %U:%a "$scope/state") == ark:700 ) ]] || exit 2
  linked_files=$(find "$scope" -path "$scope/state" -prune -o -type f -links +1 -print -quit) || exit 1
  [[ -z $linked_files ]] || exit 2
  find "$scope" -path "$scope/state" -prune -o -exec chown -h root:root {} +
  find "$scope" -path "$scope/state" -prune -o ! -type l -exec chmod go-w {} +
  chmod 755 "$scope"
  install -d -o ark -g ark -m 700 "$scope/state"
fi
printf 'SHELL_PREFLIGHT PASS kernel=v0.15 rootfs=v0.17 scope=tmpfs binary=%s\n' "$expected"
[[ $mode != --check ]] || exit 0
unit=r46h-shell-probe-$$.service
args=(--fullscreen --quit-after 290)
deadline=300
if [[ $mode == --profile ]]; then
  args=(--fullscreen --quit-after 110 --profile-ui)
  deadline=120
fi
entry="$scope/shell-client.sh"
if [[ $mode == --ports || $mode == --attended-ports ]]; then
  entry="$scope/desktop-session.sh"; args=(ports); deadline=900
  if [[ $mode == --attended-ports ]]; then args+=(--attended); deadline=5400; fi
fi
if [[ $mode == --native ]]; then entry="$scope/desktop-session.sh"; args=(native); deadline=900; fi
if [[ $mode == --streaming || $mode == --attended ]]; then
  entry="$scope/desktop-session.sh"
  args=("$client_hash")
  deadline=900
  if [[ $mode == --attended ]]; then args+=(--attended); deadline=5400; fi
fi
if [[ $mode == --remote || $mode == --remote-device || $mode == --remote-streaming || $mode == --remote-native || $mode == --remote-ports ]]; then
  entry="$scope/remote-session.sh"
  args=("$listen_ip" "$peer_ip")
  [[ $mode != --remote-streaming ]] || args+=("$client_hash")
  [[ $mode != --remote-native ]] || args+=(native)
  [[ $mode != --remote-ports ]] || args+=(ports)
  deadline=1860
fi
render_env=(R46H_DEVICE_CONTROLS=0)
unit_properties=()
if [[ $mode == --device || $mode == --remote-device ]]; then
  render_env=(R46H_DEVICE_CONTROLS=1)
  unit_properties=(-p "ExecStartPre=/bin/bash $scope/device-lease.sh --acquire $unit" -p "ExecStopPost=/bin/bash $scope/device-lease.sh --restore $unit")
fi
if [[ -n ${R46H_SHELL_STATE_DIR:-} ]]; then
  render_env+=(R46H_SHELL_STATE_DIR="$R46H_SHELL_STATE_DIR")
fi
if [[ $mode == --ports || $mode == --attended-ports || $mode == --remote-ports ]]; then
  unit_properties=(-p "ExecStartPre=/bin/bash $scope/runtime-lease.sh --acquire $unit" -p "ExecStopPost=/bin/bash $scope/runtime-lease.sh --release $unit")
fi
# Qt enables this diagnostic by presence, including a value of "0".
[[ ${QSG_RENDER_TIMING:-} != 1 ]] || render_env+=(QSG_RENDER_TIMING=1)
[[ ${DRM_FORCE_EGL:-} != 1 ]] || render_env+=(DRM_FORCE_EGL=1)
restore() {
  result=$?
  trap - EXIT
  set +e
  # A cgroup also contains descendants that setsid moved out of timeout's group.
  if ! systemctl stop "$unit" 2>/dev/null; then
    [[ $(systemctl show -p LoadState --value "$unit") == not-found ]] || {
      echo 'SHELL_END failed to stop preview; frontend left stopped.' >&2; exit 1;
    }
  fi
  if [[ $mode == --ports || $mode == --attended-ports || $mode == --remote-ports ]]; then
    /bin/bash "$scope/runtime-lease.sh" --release "$unit" || { echo 'SHELL_END runtime_restore=failed; frontend left stopped.' >&2; exit 1; }
  fi
  mux_status=0
  if [[ -n $saved_mux ]]; then amixer -q -c 0 cset numid=5 "$saved_mux"; mux_status=$?; fi
  if (( ${device_mode:-0} )); then
    /bin/bash "$scope/device-lease.sh" --restore "$unit" || { echo 'SHELL_END device_restore=failed; frontend left stopped.' >&2; exit 1; }
    if (( result == 77 || result == 78 )); then
      operation=poweroff
      (( result != 78 )) || operation=reboot
      sync
      if systemctl --no-block "$operation"; then
        printf 'SHELL_END power_request=%s device_restore=0\n' "$operation"
        exit 0
      fi
      result=1
    fi
  fi
  systemctl start r46h-gaming-frontend.service
  restored=$?
  if (( restored == 0 )); then
    systemctl is-active --quiet r46h-gaming-frontend.service
    restored=$?
  fi
  printf 'SHELL_END status=%s frontend_restore=%s mux_restore=%s\n' "$result" "$restored" "$mux_status"
  (( restored == 0 && mux_status == 0 )) || exit 1
  exit "$result"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
systemctl stop r46h-gaming-frontend.service
if [[ -n $saved_mux ]]; then amixer -q -c 0 cset numid=5 0; fi
printf 'SHELL_BEGIN display=eglfs input=local-preview keyboard=qt timeout=%ss global_overlay=UNTESTED\n' "$deadline"
runner=(/usr/sbin/runuser -u ark --)
[[ $mode != --remote && $mode != --remote-device && $mode != --remote-streaming && $mode != --remote-native && $mode != --remote-ports ]] || runner=()
systemd-run --quiet --wait --pipe --collect --service-type=exec --unit="$unit" \
  -p RuntimeMaxSec="$deadline" -p TimeoutStopSec=10 -p KillMode=control-group "${unit_properties[@]}" \
  /usr/bin/setsid --wait /usr/bin/openvt -e -c 2 -s -f -- \
  "${runner[@]}" /usr/bin/env \
  XDG_RUNTIME_DIR=/run/user/1000 QT_QPA_PLATFORM=eglfs QT_QPA_EGLFS_INTEGRATION=eglfs_kms \
  QSG_RHI_BACKEND=opengl R46H_VIRTUAL_KEYBOARD=1 SDL_GAMECONTROLLERCONFIG="$mapping" \
  SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT=0x5246/0x0048 SDL_NO_SIGNAL_HANDLERS=1 R46H_SHELL_LOG=1 \
  "${render_env[@]}" \
  "$entry" "${args[@]}"
