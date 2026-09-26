#!/bin/bash
# Bounded compositor probe with optional shared-desktop diagnostic profile.
set -Eeuo pipefail
umask 077
[[ ( ( $# == 2 || $# == 3 ) && ( $1 == --check || $1 == --run ) || $# == 5 && $1 == --remote ) && $2 =~ ^[0-9a-f]{64}$ ]] || {
  echo 'Usage: probe-r46h.sh --check|--run MANIFEST_SHA256 [handheld] | --remote MANIFEST_SHA256 PUBLIC_KEY_SHA256 DEVICE_IP HOST_IP' >&2; exit 2;
}
mode=$1
profile=${3:-windows}
[[ $mode != --remote ]] || profile=handheld
[[ $profile == windows || $profile == handheld ]] || exit 2
scope=/run/r46h-wayland-probe
[[ $EUID == 0 && $(uname -r) == 6.12.99-r46h-mainline-v0.15-gaming-product ]]
root_uuid=$(findmnt -rn -o UUID /)
case $root_uuid in
d3130017-46a4-4d56-9001-000000000017) rootfs=v0.17 ;;
d3130018-46a4-4d56-9001-000000000018) rootfs=v0.18 ;;
*) exit 1 ;;
esac
[[ $(cat /sys/class/block/mmcblk0/device/cid) == fe343253440000002000002d57019567 ]]
[[ $(cat /sys/class/block/mmcblk0/size) == 122138624 ]]
[[ $(findmnt -rn -o FSTYPE /run) == tmpfs && ,$(findmnt -rn -o OPTIONS /roms), == *,ro,* ]]
[[ -d $scope && ! -L $scope && $(stat -c %u:%g:%a "$scope") == 0:0:755 ]]
[[ $(sha256sum "$scope/SHA256SUMS" | cut -d ' ' -f 1) == "$2" ]]
(cd "$scope" && sha256sum --check --quiet SHA256SUMS)
[[ -z $(find "$scope/usr" -not -user root -print -quit) ]]
[[ -z $(find "$scope/usr" \( -type f -o -type d \) -perm /022 -print -quit) ]]
for file in session.sh clients.sh probe-r46h.sh; do
  [[ -f $scope/$file && ! -L $scope/$file && $(stat -c %u:%g:%a "$scope/$file") == 0:0:755 ]]
done
if [[ $mode == --remote ]]; then
  [[ $3 =~ ^[0-9a-f]{64}$ && -x /usr/sbin/sshd ]] || exit 2
  [[ -f $scope/remote-session.sh && ! -L $scope/remote-session.sh && $(stat -c %u:%g:%a "$scope/remote-session.sh") == 0:0:755 ]] || exit 1
  [[ -f $scope/remote-client.pub && ! -L $scope/remote-client.pub && $(stat -c %u:%g:%a:%h "$scope/remote-client.pub") == 0:0:644:1 && $(stat -c %s "$scope/remote-client.pub") -le 4096 ]] || exit 1
  [[ $(sha256sum "$scope/remote-client.pub" | cut -d ' ' -f 1) == "$3" ]] || exit 1
fi
if [[ $profile == handheld ]]; then
  for file in handheld-client.sh shell-client.sh; do
    [[ -f $scope/$file && ! -L $scope/$file && $(stat -c %u:%g:%a "$scope/$file") == 0:0:755 ]]
  done
  if [[ -e $scope/MOONLIGHT_SHA256 || -L $scope/MOONLIGHT_SHA256 ]]; then
    [[ -f $scope/MOONLIGHT_SHA256 && ! -L $scope/MOONLIGHT_SHA256 && $(stat -c %u:%g:%a "$scope/MOONLIGHT_SHA256") == 0:0:644 ]]
    [[ $(cat "$scope/MOONLIGHT_SHA256") =~ ^[0-9a-f]{64}$ && -x $scope/usr/bin/moonlight-qt ]]
    [[ $(sha256sum "$scope/usr/bin/moonlight-qt" | cut -d ' ' -f 1) == "$(cat "$scope/MOONLIGHT_SHA256")" ]]
  fi
  [[ -x /usr/bin/setpriv && -x $scope/usr/bin/input-router && -f $scope/usr/lib/aarch64-linux-gnu/weston/handheld-shell.so ]]
  [[ -c /dev/uinput && ! -L /dev/uinput && $(stat -c '%t:%T' /dev/uinput) == a:df ]]
  inputs=()
  for name in /sys/class/input/event*/device/name; do
    [[ $(cat "$name") != 'R46H Combined Gamepad' ]] || inputs+=("/dev/input/$(basename "$(dirname "$(dirname "$name")")")")
  done
  [[ ${#inputs[@]} == 1 && -c ${inputs[0]} && ! -L ${inputs[0]} ]]
  /usr/bin/setpriv --reuid=ark --regid=ark --init-groups -- /usr/bin/test -r "${inputs[0]}"
  export R46H_ROUTED_SOURCE=${inputs[0]}
fi
ports_mode=0
if [[ -n ${R46H_SHELL_STATE_DIR:-} ]]; then
  [[ $profile == handheld && $R46H_SHELL_STATE_DIR == /home/ark/.local/share/r46h-preview ]] || exit 2
  /usr/bin/setpriv --reuid=ark --regid=ark --init-groups -- /usr/bin/env R46H_SHELL_STATE_DIR="$R46H_SHELL_STATE_DIR" "$scope/shell-client.sh" --check-state || exit 1
  if [[ -f $scope/usr/share/r46h/ports/local_port.py ]]; then
    [[ -f $scope/runtime-lease.sh && ! -L $scope/runtime-lease.sh && $(stat -c %u:%g:%a "$scope/runtime-lease.sh") == 0:0:755 ]] || exit 1
    [[ ! -e /run/r46h-port-runtime && ! -L /run/r46h-port-runtime && ! -e $scope/mono && ! -L $scope/mono ]] || exit 1
    ports_mode=1
  fi
fi
device_mode=${R46H_DEVICE_CONTROLS:-0}
[[ $device_mode == 0 || $device_mode == 1 ]] || exit 2
if (( device_mode )); then
  [[ $profile == handheld && -f $scope/device-lease.sh && ! -L $scope/device-lease.sh && $(stat -c %u:%g:%a "$scope/device-lease.sh") == 0:0:755
     && -f $scope/cpu-control.py && ! -L $scope/cpu-control.py && $(stat -c %u:%g:%a "$scope/cpu-control.py") == 0:0:755 ]] || exit 1
  [[ ! -e /run/r46h-device-lease && ! -L /run/r46h-device-lease && ! -e /run/r46h-cpu-control && ! -L /run/r46h-cpu-control ]] || exit 1
fi
if (( device_mode || ports_mode )); then
  [[ -f $scope/session-leases.sh && ! -L $scope/session-leases.sh && $(stat -c %u:%g:%a "$scope/session-leases.sh") == 0:0:755 ]] || exit 1
fi
for service in r46h-gaming-input r46h-volume-keys r46h-gaming-frontend; do
  systemctl is-active --quiet "$service.service"
done
status=0
pgrep -f '(^|/)(retroarch|moonlight(-qt)?|r46h-shell|input-router|weston|seatd|re3|reVC|mono(-sgen)?)([[:space:]]|$)' >/dev/null || status=$?
[[ $status == 1 ]] || { echo 'Refusing probe: client/compositor active or process check failed.' >&2; exit 1; }
[[ ! -e /run/seatd.sock && ! -L /run/seatd.sock ]]
[[ -c /dev/dri/card0 && -c /dev/dri/renderD128 ]]
lib="$scope/usr/lib/aarch64-linux-gnu"
portlib="$scope/usr/lib/r46h-ports"
# Inspect headers with Bash builtins; keep one ldd call for the complete closure.
binaries=()
while IFS= read -r -d '' binary; do
  signature=
  IFS= LC_ALL=C read -r -n 4 -d '' signature < "$binary" || true
  [[ $signature != $'\177ELF' ]] || binaries+=("$binary")
done < <(find "$scope/usr" -type f -print0)
[[ ${#binaries[@]} -gt 0 ]]
closure=$(LC_ALL=C LD_LIBRARY_PATH="$portlib:$lib:$lib/weston:$lib/libproxy" ldd "${binaries[@]}")
[[ $closure != *'not found'* ]] || { printf '%s\n' "$closure" >&2; exit 1; }
if [[ -f $scope/usr/share/r46h/ports/manager.py ]]; then
  /usr/bin/setpriv --reuid=ark --regid=ark --init-groups -- /usr/bin/env -u LD_LIBRARY_PATH -u PYTHONHOME -u PYTHONPATH \
    "$scope/usr/bin/python3.13" -I -B -c 'import bz2, ctypes, lzma, sqlite3, ssl, urllib.request, zipfile'
fi
printf 'WAYLAND_PREFLIGHT PASS kernel=v0.15 rootfs=%s device_runtime=UNTESTED\n' "$rootfs"
[[ $mode != --check ]] || exit 0
exec 9> "$scope/probe.lock"
flock -n 9
rm -f -- "$scope/seatd-socket-identity"
install -d -o root -g root -m 755 "$scope/state"
output=$(mktemp -d "$scope/state/session.XXXXXX")
chown ark:ark "$output"
unit=r46h-wayland-probe-$$.service
entry=("$scope/session.sh" seat "$output" "$profile")
[[ $mode != --remote ]] || entry=("$scope/remote-session.sh" "$4" "$5" wayland "$output")
unit_properties=()
if (( ports_mode || device_mode )); then
  unit_properties=(-p "ExecStartPre=/bin/bash $scope/session-leases.sh --acquire $unit $ports_mode $device_mode"
                   -p "ExecStopPost=/bin/bash $scope/session-leases.sh --restore $unit $ports_mode $device_mode")
fi
restore() {
  result=$?
  trap - EXIT
  set +e
  if ! systemctl stop "$unit" 2>/dev/null; then
    [[ $(systemctl show -p LoadState --value "$unit") == not-found ]] || {
      echo 'WAYLAND_END cgroup stop failed; frontend left stopped.' >&2; exit 1;
    }
  fi
  shopt -s nullglob
  runtimes=("$output"/runtime.*)
  shopt -u nullglob
  if (( ${#runtimes[@]} > 1 )); then
    echo 'WAYLAND_END runtime cleanup refused; frontend left stopped.' >&2; exit 1
  elif (( ${#runtimes[@]} == 1 )); then
    runtime=${runtimes[0]}
    [[ -d $runtime && ! -L $runtime && $(stat -c '%u:%g:%a' "$runtime") == "$(id -u ark):$(id -g ark):700" ]] || {
      echo 'WAYLAND_END runtime cleanup refused; frontend left stopped.' >&2; exit 1;
    }
    rm -rf -- "$runtime" || { echo 'WAYLAND_END runtime cleanup failed; frontend left stopped.' >&2; exit 1; }
  fi
  if (( ports_mode || device_mode )); then
    /bin/bash "$scope/session-leases.sh" --restore "$unit" "$ports_mode" "$device_mode" || { echo 'WAYLAND_END lease restore failed; frontend left stopped.' >&2; exit 1; }
  fi
  if [[ -e /run/seatd.sock || -L /run/seatd.sock ]]; then
    if [[ -S /run/seatd.sock && ! -L /run/seatd.sock && -f $scope/seatd-socket-identity &&
          $(stat -c '%d:%i' /run/seatd.sock) == "$(cat "$scope/seatd-socket-identity")" ]]; then
      rm -- /run/seatd.sock || exit 1
    else
      echo 'WAYLAND_END seat socket identity changed; frontend left stopped.' >&2; exit 1
    fi
  fi
  if (( device_mode && (result == 77 || result == 78) )); then
    operation=poweroff
    (( result != 78 )) || operation=reboot
    sync
    if systemctl --no-block "$operation"; then
      printf 'WAYLAND_END power_request=%s lease_restore=0 evidence=%s\n' "$operation" "$output"
      exit 0
    fi
    result=1
  fi
  systemctl start r46h-gaming-frontend.service
  restored=$?
  if (( restored == 0 )); then
    systemctl is-active --quiet r46h-gaming-frontend.service
    restored=$?
  fi
  printf 'WAYLAND_END status=%s frontend_restore=%s evidence=%s\n' "$result" "$restored" "$output"
  (( restored == 0 )) || exit 1
  exit "$result"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
systemctl stop r46h-gaming-frontend.service
systemd-run --quiet --wait --pipe --collect --service-type=exec --unit="$unit" \
  -p RuntimeMaxSec=360 -p TimeoutStopSec=10 -p KillMode=control-group \
  "${unit_properties[@]}" \
  /usr/bin/setsid --wait /usr/bin/openvt -e -c 2 -s -f -- \
  /usr/bin/env R46H_ROUTED_SOURCE="${R46H_ROUTED_SOURCE:-}" R46H_SHELL_STATE_DIR="${R46H_SHELL_STATE_DIR:-}" \
    R46H_SHARED_PORTS="$ports_mode" R46H_DEVICE_CONTROLS="$device_mode" "${entry[@]}"
