#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG
umask 077

readonly EXPECTED_RELEASE=6.12.99-r46h-mainline-v0.15-gaming-product
readonly EXPECTED_ROOT_PARTUUID=c9f931c9-02
readonly EXPECTED_ROOT_UUID=d3130007-46a4-4d56-9001-000000000007
readonly OZONE_RECEIPT_SHA256=8acac2c8b8e4295c0235ad1fc7e396e341dcc4b1ba771a053355a98cf8fb73ec
readonly CONFIG_SHA256=0694b9f41220983bdf9d60789b97b2fe115f68474f22f4869a2764513bcf1835
readonly RUNNER_SHA256=b0a44a7184cef97e2b9597f0d84adacb66617073f9422ef719d98e3465cc77c8
readonly CAPTURE_SHA256=bb4c421029085cc182c369bb8b7c4a1431d0de2ddafb244d8c347dbbad127618
readonly HELPER_SHA256=728ad68187cc5647c695014c61ec86f48207ef05b46088463d427832ee3e40e4
readonly GATEWAY_SHA256=5932dd1eec9c510cf9f4a8c5f0425c7b4afa083c473d290e57c9775f15b6a638
readonly SUDOERS_SHA256=f366b8815b00f477521ef6d42e4dc2c94d3997e77940b66cacfc8548911e1ed6
readonly CONFIG=/etc/r46h/retroarch.cfg
readonly RUNNER=/usr/local/sbin/r46h-game-ui
readonly CAPTURE=/usr/local/libexec/r46h-drm-capture
readonly HELPER=/usr/local/bin/r46h-screenshot
readonly GATEWAY=/usr/local/bin/r46h-screenshot-ssh
readonly SUDOERS=/etc/sudoers.d/r46h-remote-screen
readonly OZONE_RECEIPT=/var/lib/r46h/gaming-ozone-fbneo-v0.1-installed
readonly AUTHORIZED_KEYS=/home/ark/.ssh/authorized_keys
readonly STATE_PARENT=/var/lib/r46h-remote-screen
readonly STATE_DIR=$STATE_PARENT/v0.1
readonly RECEIPT=/var/lib/r46h/remote-screen-v0.1-installed
readonly ROLLBACK=/usr/local/sbin/r46h-remote-screen-rollback
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count
readonly SCREENSHOT_ROOT=/home/ark/.cache/r46h/screenshots

auth_stage=""

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup_stage() {
  local status=$?
  trap - EXIT
  rm -f -- "$auth_stage"
  exit "$status"
}
trap cleanup_stage EXIT

remove_installed_key() {
  local authorized_line
  local key_line

  key_line=$(cat "$STATE_DIR/operator.pub")
  authorized_line="restrict,command=\"/usr/local/bin/r46h-screenshot-ssh\" $key_line"
  auth_stage=/home/ark/.ssh/.authorized_keys.remote-screen-rollback.$$
  [[ ! -e "$auth_stage" && ! -L "$auth_stage" ]] || die 'authorized_keys stage exists'
  awk -v target="$authorized_line" '$0 != target { print }' "$AUTHORIZED_KEYS" > "$auth_stage"
  chown ark:ark "$auth_stage"
  chmod 0600 "$auth_stage"
  if [[ -s "$auth_stage" ]]; then
    mv -f -- "$auth_stage" "$AUTHORIZED_KEYS"
  else
    rm -f -- "$auth_stage" "$AUTHORIZED_KEYS"
  fi
  auth_stage=""
}

[[ $# == 0 ]] || die 'this rollback accepts no arguments'
(( EUID == 0 )) || die 'root is required'
[[ "${BASH_SOURCE[0]}" == "$ROLLBACK" ]] || die 'run the installed rollback helper'
[[ "$(uname -r)" == "$EXPECTED_RELEASE" ]] || die 'unexpected running kernel'
[[ "$(findmnt -rn -o PARTUUID /)" == "$EXPECTED_ROOT_PARTUUID" ]] || die 'unexpected root partition'
[[ "$(findmnt -rn -o UUID /)" == "$EXPECTED_ROOT_UUID" ]] || die 'unexpected p2 image UUID'
[[ "$(findmnt -rn -o FSTYPE /)" == ext4 ]] || die 'root is not ext4'
[[ ",$(findmnt -rn -o OPTIONS /)," == *,rw,* ]] || die 'root is not writable'
[[ ",$(findmnt -rn -o OPTIONS /roms)," == *,ro,* ]] || die '/roms is not read-only'
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem already reports errors'
[[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd has failed units'

for specification in \
  "$CONFIG:$CONFIG_SHA256:0:0:644" \
  "$RUNNER:$RUNNER_SHA256:0:0:755" \
  "$CAPTURE:$CAPTURE_SHA256:0:0:755" \
  "$HELPER:$HELPER_SHA256:0:0:755" \
  "$GATEWAY:$GATEWAY_SHA256:0:0:755" \
  "$SUDOERS:$SUDOERS_SHA256:0:0:440"; do
  IFS=: read -r path digest owner group mode <<< "$specification"
  [[ -f "$path" && ! -L "$path" ]] || die "installed file is unsafe: $path"
  [[ "$(stat -c '%u:%g:%a:%h' "$path")" == "$owner:$group:$mode:1" ]] || \
    die "installed file identity changed: $path"
  [[ "$(sha256sum "$path" | awk '{print $1}')" == "$digest" ]] || \
    die "installed file content changed: $path"
done
/usr/sbin/visudo -cf "$SUDOERS" >/dev/null || die 'installed sudo policy is invalid'

[[ -f "$OZONE_RECEIPT" && ! -L "$OZONE_RECEIPT" ]] || die 'Ozone receipt is missing'
[[ "$(stat -c '%u:%g:%a:%h' "$OZONE_RECEIPT")" == 0:0:600:1 ]] || \
  die 'Ozone receipt identity is unsafe'
[[ "$(sha256sum "$OZONE_RECEIPT" | awk '{print $1}')" == "$OZONE_RECEIPT_SHA256" ]] || \
  die 'Ozone receipt changed'
[[ -f "$RECEIPT" && ! -L "$RECEIPT" ]] || die 'remote-screen receipt is missing'
[[ "$(stat -c '%u:%g:%a:%h' "$RECEIPT")" == 0:0:600:1 ]] || die 'receipt identity is unsafe'
[[ "$(wc -l < "$RECEIPT" | tr -d '[:space:]')" == 10 ]] || die 'receipt line count mismatch'
grep -Fqx 'feature_id=r46h-remote-screen-v0.1' "$RECEIPT" || die 'receipt identity mismatch'
grep -Fqx "ozone_receipt_sha256=$OZONE_RECEIPT_SHA256" "$RECEIPT" || die 'Ozone receipt mismatch'
grep -Fqx "capture_sha256=$CAPTURE_SHA256" "$RECEIPT" || die 'capture receipt mismatch'
grep -Fqx "helper_sha256=$HELPER_SHA256" "$RECEIPT" || die 'helper receipt mismatch'
grep -Fqx "gateway_sha256=$GATEWAY_SHA256" "$RECEIPT" || die 'gateway receipt mismatch'
grep -Fqx "sudoers_sha256=$SUDOERS_SHA256" "$RECEIPT" || die 'sudoers receipt mismatch'
grep -Eq '^rollback_sha256=[0-9a-f]{64}$' "$RECEIPT" || die 'rollback receipt mismatch'
grep -Eq '^installer_sha256=[0-9a-f]{64}$' "$RECEIPT" || die 'installer receipt mismatch'
grep -Eq '^public_key_sha256=[0-9a-f]{64}$' "$RECEIPT" || die 'public-key receipt mismatch'
grep -Eq '^key_added=(yes|no)$' "$RECEIPT" || die 'key-added receipt mismatch'

[[ -d "$STATE_PARENT" && ! -L "$STATE_PARENT" ]] || die 'rollback state parent is missing'
[[ "$(stat -c '%u:%g:%a' "$STATE_PARENT")" == 0:0:700 ]] || die 'state parent is unsafe'
[[ -d "$STATE_DIR" && ! -L "$STATE_DIR" ]] || die 'rollback state is missing'
[[ "$(stat -c '%u:%g:%a' "$STATE_DIR")" == 0:0:700 ]] || die 'rollback state is unsafe'
state_members=$(find "$STATE_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
[[ "$state_members" == $'key-added\noperator.pub\nrollback.sh' ]] || die 'unexpected rollback state members'
for path in "$STATE_DIR/key-added" "$STATE_DIR/operator.pub" "$STATE_DIR/rollback.sh"; do
  [[ -f "$path" && ! -L "$path" ]] || die "unsafe rollback state member: $path"
  [[ "$(stat -c '%u:%g:%h' "$path")" == 0:0:1 ]] || die "unsafe state links: $path"
done
[[ "$(stat -c '%a' "$STATE_DIR/key-added")" == 400 ]] || die 'key-added state mode mismatch'
[[ "$(stat -c '%a' "$STATE_DIR/operator.pub")" == 400 ]] || die 'public-key state mode mismatch'
[[ "$(stat -c '%a' "$STATE_DIR/rollback.sh")" == 500 ]] || die 'rollback state mode mismatch'
cmp -s "$STATE_DIR/rollback.sh" "$ROLLBACK" || die 'installed rollback differs from state'
rollback_sha256=$(sha256sum "$ROLLBACK" | awk '{print $1}')
grep -Fqx "rollback_sha256=$rollback_sha256" "$RECEIPT" || die 'rollback state receipt mismatch'
public_key_sha256=$(sha256sum "$STATE_DIR/operator.pub" | awk '{print $1}')
grep -Fqx "public_key_sha256=$public_key_sha256" "$RECEIPT" || die 'public-key state receipt mismatch'
key_added=$(cat "$STATE_DIR/key-added")
[[ "$key_added" == yes || "$key_added" == no ]] || die 'invalid key-added state'
grep -Fqx "key_added=$key_added" "$RECEIPT" || die 'key-added state receipt mismatch'

[[ -f "$AUTHORIZED_KEYS" && ! -L "$AUTHORIZED_KEYS" ]] || die 'authorized_keys is missing'
[[ "$(stat -c '%u:%g:%a:%h' "$AUTHORIZED_KEYS")" == 1000:1000:600:1 ]] || \
  die 'authorized_keys identity is unsafe'
key_line=$(cat "$STATE_DIR/operator.pub")
key_blob=$(awk '{print $2}' "$STATE_DIR/operator.pub")
authorized_line="restrict,command=\"/usr/local/bin/r46h-screenshot-ssh\" $key_line"
key_count=$(awk -v target="$authorized_line" '$0 == target { count++ } END { print count + 0 }' "$AUTHORIZED_KEYS")
blob_count=$(awk -v blob="$key_blob" \
  '{ for (field=1; field<NF; field++) if ($field == "ssh-ed25519" && $(field+1) == blob) count++ } END { print count + 0 }' \
  "$AUTHORIZED_KEYS")
[[ "$key_count" == 1 && "$blob_count" == 1 ]] || die 'installed screenshot key changed'

[[ "$(systemctl is-active r46h-gaming-frontend.service || true)" == active ]] || \
  die 'gaming frontend is not active'
mapfile -t retroarch_pids < <(pgrep -u 1000 -x retroarch || true)
(( ${#retroarch_pids[@]} == 1 )) || die 'expected exactly one ark RetroArch process'
retroarch_pid=${retroarch_pids[0]}
[[ "$(readlink "/proc/$retroarch_pid/exe")" == /usr/bin/retroarch ]] || die 'unexpected RetroArch executable'
frontend_restarts=$(systemctl show -p NRestarts --value r46h-gaming-frontend.service)
[[ "$frontend_restarts" == 0 ]] || die 'gaming frontend already restarted'
[[ -z "$(/usr/bin/ss -H -lun sport = :55355)" ]] || die 'RetroArch UDP command listener is active'

if [[ "$key_added" == yes ]]; then
  remove_installed_key
fi
rm -f -- "$SUDOERS" "$CAPTURE" "$HELPER" "$GATEWAY" "$RECEIPT"
rm -f -- "$STATE_DIR/key-added" "$STATE_DIR/operator.pub" "$STATE_DIR/rollback.sh"
rmdir -- "$STATE_DIR"
rmdir -- "$STATE_PARENT"
rmdir -- "$SCREENSHOT_ROOT/capture" "$SCREENSHOT_ROOT/exports" "$SCREENSHOT_ROOT" 2>/dev/null || true
sync

[[ "$(sha256sum "$CONFIG" | awk '{print $1}')" == "$CONFIG_SHA256" ]] || die 'Ozone config changed'
[[ "$(sha256sum "$RUNNER" | awk '{print $1}')" == "$RUNNER_SHA256" ]] || die 'Ozone launcher changed'
[[ "$(systemctl is-active r46h-gaming-frontend.service || true)" == active ]] || die 'frontend stopped during rollback'
[[ "$(pgrep -u 1000 -x retroarch)" == "$retroarch_pid" ]] || die 'RetroArch changed during rollback'
[[ "$(systemctl show -p NRestarts --value r46h-gaming-frontend.service)" == "$frontend_restarts" ]] || \
  die 'frontend restarted during rollback'
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem reported an error during rollback'
[[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd has failed units after rollback'

rm -f -- "$ROLLBACK"
sync
trap - EXIT
printf 'PASS: R46H remote-screen v0.1 rolled back; Ozone config and frontend remained untouched.\n'
