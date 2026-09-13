#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG
umask 077

readonly FEATURE_ID=r46h-remote-screen-v0.1
readonly EXPECTED_RELEASE=6.12.99-r46h-mainline-v0.15-gaming-product
readonly EXPECTED_ROOT_PARTUUID=c9f931c9-02
readonly EXPECTED_ROOT_UUID=d3130007-46a4-4d56-9001-000000000007
readonly PAYLOAD_DIR=/run/r46h-remote-screen-v0.1
readonly CAPTURE_SOURCE=$PAYLOAD_DIR/r46h-drm-capture
readonly HELPER_SOURCE=$PAYLOAD_DIR/r46h-screenshot
readonly GATEWAY_SOURCE=$PAYLOAD_DIR/r46h-screenshot-ssh
readonly SUDOERS_SOURCE=$PAYLOAD_DIR/r46h-remote-screen.sudoers
readonly ROLLBACK_SOURCE=$PAYLOAD_DIR/rollback.sh
readonly PUBLIC_KEY_SOURCE=$PAYLOAD_DIR/operator.pub
readonly CONFIG=/etc/r46h/retroarch.cfg
readonly RUNNER=/usr/local/sbin/r46h-game-ui
readonly CAPTURE=/usr/local/libexec/r46h-drm-capture
readonly HELPER=/usr/local/bin/r46h-screenshot
readonly GATEWAY=/usr/local/bin/r46h-screenshot-ssh
readonly SUDOERS=/etc/sudoers.d/r46h-remote-screen
readonly ROLLBACK=/usr/local/sbin/r46h-remote-screen-rollback
readonly AUTHORIZED_KEYS=/home/ark/.ssh/authorized_keys
readonly BASE_RECEIPT=/var/lib/r46h/gaming-mvp-v0.6-installed
readonly OZONE_RECEIPT=/var/lib/r46h/gaming-ozone-fbneo-v0.1-installed
readonly RECEIPT=/var/lib/r46h/remote-screen-v0.1-installed
readonly STATE_PARENT=/var/lib/r46h-remote-screen
readonly STATE_DIR=$STATE_PARENT/v0.1
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count
readonly SCREENSHOT_ROOT=/home/ark/.cache/r46h/screenshots
readonly BASE_RECEIPT_SHA256=82721e16a9b9a7c7927d0ca4d228dd3d850e3a39dca245177ec1f016b3b8d314
readonly OZONE_RECEIPT_SHA256=8acac2c8b8e4295c0235ad1fc7e396e341dcc4b1ba771a053355a98cf8fb73ec
readonly CONFIG_SHA256=0694b9f41220983bdf9d60789b97b2fe115f68474f22f4869a2764513bcf1835
readonly RUNNER_SHA256=b0a44a7184cef97e2b9597f0d84adacb66617073f9422ef719d98e3465cc77c8
readonly CAPTURE_SHA256=bb4c421029085cc182c369bb8b7c4a1431d0de2ddafb244d8c347dbbad127618
readonly HELPER_SHA256=728ad68187cc5647c695014c61ec86f48207ef05b46088463d427832ee3e40e4
readonly GATEWAY_SHA256=5932dd1eec9c510cf9f4a8c5f0425c7b4afa083c473d290e57c9775f15b6a638
readonly SUDOERS_SHA256=f366b8815b00f477521ef6d42e4dc2c94d3997e77940b66cacfc8548911e1ed6
readonly ROLLBACK_SHA256=3285d3b0c936ffb87f87de1a13fccc23be5fce8200f7891feaab34d7b4e7a686

auth_stage=""
capture_stage=""
gateway_stage=""
helper_stage=""
receipt_stage=""
rollback_stage=""
sudoers_stage=""
state_stage=""
capture_installed=0
gateway_installed=0
helper_installed=0
key_added=0
receipt_installed=0
rollback_installed=0
sudoers_installed=0
state_parent_created=0
state_published=0
ssh_dir_created=0
screenshot_root_created=0
capture_dir_created=0
export_dir_created=0
transaction_active=0

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  printf 'usage: sudo /bin/bash %s --installer-sha256 HEX --public-key-sha256 HEX\n' \
    "$PAYLOAD_DIR/install.sh"
}

remove_key_line() {
  local authorized_line
  local key_line
  local stage=/home/ark/.ssh/.authorized_keys.remote-screen-cleanup.$$

  [[ -f "$AUTHORIZED_KEYS" && ! -L "$AUTHORIZED_KEYS" ]] || return 1
  [[ "$(stat -c '%u:%g:%a:%h' "$AUTHORIZED_KEYS")" == 1000:1000:600:1 ]] || return 1
  key_line=$(cat "$PUBLIC_KEY_SOURCE") || return 1
  authorized_line="restrict,command=\"/usr/local/bin/r46h-screenshot-ssh\" $key_line"
  [[ "$(awk -v target="$authorized_line" '$0 == target { count++ } END { print count + 0 }' \
      "$AUTHORIZED_KEYS")" == 1 ]] || return 1
  rm -f -- "$stage"
  awk -v target="$authorized_line" '$0 != target { print }' "$AUTHORIZED_KEYS" > "$stage" || return 1
  chown ark:ark "$stage" || return 1
  chmod 0600 "$stage" || return 1
  if [[ -s "$stage" ]]; then
    mv -f -- "$stage" "$AUTHORIZED_KEYS" || return 1
  else
    rm -f -- "$stage" "$AUTHORIZED_KEYS" || return 1
  fi
}

remove_exact_file() {
  local path=$1
  local digest=$2
  local identity=$3

  [[ ! -e "$path" && ! -L "$path" ]] && return 0
  [[ -f "$path" && ! -L "$path" ]] || return 1
  [[ "$(stat -c '%u:%g:%a:%h' "$path")" == "$identity" ]] || return 1
  [[ "$(sha256sum "$path" | awk '{print $1}')" == "$digest" ]] || return 1
  rm -f -- "$path"
}

remove_state_directory() {
  local directory=$1

  [[ -d "$directory" && ! -L "$directory" ]] || return 1
  [[ "$(stat -c '%u:%g:%a' "$directory")" == 0:0:700 ]] || return 1
  [[ -z "$(find "$directory" -mindepth 1 -maxdepth 1 \
      ! -name key-added ! -name operator.pub ! -name rollback.sh -print -quit)" ]] || return 1
  rm -f -- "$directory/key-added" "$directory/operator.pub" "$directory/rollback.sh" || return 1
  rmdir -- "$directory"
}

cleanup_install() {
  local status=$?
  local cleanup_ok=1

  trap - EXIT INT TERM HUP
  set +e
  trap '' INT TERM HUP
  rm -f -- "$auth_stage" "$capture_stage" "$gateway_stage" "$helper_stage" \
    "$receipt_stage" "$rollback_stage" "$sudoers_stage"
  if (( transaction_active == 1 )); then
    if (( key_added == 1 )); then
      remove_key_line || cleanup_ok=0
    fi
    if (( sudoers_installed == 1 )); then
      remove_exact_file "$SUDOERS" "$SUDOERS_SHA256" 0:0:440:1 || cleanup_ok=0
    fi
    if (( capture_installed == 1 )); then
      remove_exact_file "$CAPTURE" "$CAPTURE_SHA256" 0:0:755:1 || cleanup_ok=0
    fi
    if (( helper_installed == 1 )); then
      remove_exact_file "$HELPER" "$HELPER_SHA256" 0:0:755:1 || cleanup_ok=0
    fi
    if (( gateway_installed == 1 )); then
      remove_exact_file "$GATEWAY" "$GATEWAY_SHA256" 0:0:755:1 || cleanup_ok=0
    fi
    if (( rollback_installed == 1 )); then
      remove_exact_file "$ROLLBACK" "$ROLLBACK_SHA256" 0:0:700:1 || cleanup_ok=0
    fi
    if (( receipt_installed == 1 )); then
      if [[ -f "$RECEIPT" && ! -L "$RECEIPT" &&
            "$(stat -c '%u:%g:%a:%h' "$RECEIPT")" == 0:0:600:1 ]] &&
           grep -Fqx "feature_id=$FEATURE_ID" "$RECEIPT"; then
        rm -f -- "$RECEIPT" || cleanup_ok=0
      else
        cleanup_ok=0
      fi
    fi
  fi
  if (( cleanup_ok == 1 )); then
    if (( state_published == 1 )); then
      remove_state_directory "$STATE_DIR" || cleanup_ok=0
    elif [[ -n "$state_stage" && -d "$state_stage" && ! -L "$state_stage" ]]; then
      remove_state_directory "$state_stage" || cleanup_ok=0
    fi
  fi
  if (( cleanup_ok == 1 )); then
    (( export_dir_created == 0 )) || rmdir -- "$SCREENSHOT_ROOT/exports" 2>/dev/null || true
    (( capture_dir_created == 0 )) || rmdir -- "$SCREENSHOT_ROOT/capture" 2>/dev/null || true
    (( screenshot_root_created == 0 )) || rmdir -- "$SCREENSHOT_ROOT" 2>/dev/null || true
    (( ssh_dir_created == 0 )) || rmdir -- /home/ark/.ssh 2>/dev/null || true
    (( state_parent_created == 0 )) || rmdir -- "$STATE_PARENT" 2>/dev/null || true
  else
    printf 'ERROR: rollback state retained at %s\n' "$STATE_DIR" >&2
    status=1
  fi
  exit "$status"
}

verify_installed() {
  local authorized_line
  local blob_count
  local key_blob
  local key_count
  local key_line
  local key_added_value
  local state_members

  for specification in \
    "$CAPTURE:$CAPTURE_SHA256:0:0:755" \
    "$HELPER:$HELPER_SHA256:0:0:755" \
    "$GATEWAY:$GATEWAY_SHA256:0:0:755" \
    "$SUDOERS:$SUDOERS_SHA256:0:0:440" \
    "$ROLLBACK:$ROLLBACK_SHA256:0:0:700"; do
    IFS=: read -r path digest owner group mode <<< "$specification"
    [[ -f "$path" && ! -L "$path" ]] || die "installed file is unsafe: $path"
    [[ "$(stat -c '%u:%g:%a:%h' "$path")" == "$owner:$group:$mode:1" ]] || \
      die "installed file identity changed: $path"
    [[ "$(sha256sum "$path" | awk '{print $1}')" == "$digest" ]] || \
      die "installed file content changed: $path"
  done
  /usr/sbin/visudo -cf "$SUDOERS" >/dev/null || die 'installed sudo policy is invalid'
  [[ -f "$RECEIPT" && ! -L "$RECEIPT" ]] || die 'installed receipt is unsafe'
  [[ "$(stat -c '%u:%g:%a:%h' "$RECEIPT")" == 0:0:600:1 ]] || die 'receipt identity is unsafe'
  [[ "$(wc -l < "$RECEIPT" | tr -d '[:space:]')" == 10 ]] || die 'receipt line count mismatch'
  grep -Fqx "feature_id=$FEATURE_ID" "$RECEIPT" || die 'installed receipt mismatch'
  grep -Fqx "ozone_receipt_sha256=$OZONE_RECEIPT_SHA256" "$RECEIPT" || die 'Ozone receipt mismatch'
  grep -Fqx "capture_sha256=$CAPTURE_SHA256" "$RECEIPT" || die 'capture receipt mismatch'
  grep -Fqx "helper_sha256=$HELPER_SHA256" "$RECEIPT" || die 'helper receipt mismatch'
  grep -Fqx "gateway_sha256=$GATEWAY_SHA256" "$RECEIPT" || die 'gateway receipt mismatch'
  grep -Fqx "sudoers_sha256=$SUDOERS_SHA256" "$RECEIPT" || die 'sudoers receipt mismatch'
  grep -Fqx "rollback_sha256=$ROLLBACK_SHA256" "$RECEIPT" || die 'rollback receipt mismatch'
  grep -Fqx "installer_sha256=$installer_sha256" "$RECEIPT" || die 'installer receipt mismatch'
  grep -Fqx "public_key_sha256=$public_key_sha256" "$RECEIPT" || die 'public-key receipt mismatch'
  key_added_value=$(sed -n 's/^key_added=//p' "$RECEIPT")
  [[ "$key_added_value" == yes || "$key_added_value" == no ]] || die 'key-added receipt mismatch'
  [[ -d "$STATE_DIR" && ! -L "$STATE_DIR" ]] || die 'installed rollback state is missing'
  [[ "$(stat -c '%u:%g:%a' "$STATE_DIR")" == 0:0:700 ]] || die 'rollback state is unsafe'
  state_members=$(find "$STATE_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
  [[ "$state_members" == $'key-added\noperator.pub\nrollback.sh' ]] || die 'unexpected state members'
  for path in "$STATE_DIR/key-added" "$STATE_DIR/operator.pub" "$STATE_DIR/rollback.sh"; do
    [[ -f "$path" && ! -L "$path" ]] || die "unsafe state member: $path"
    [[ "$(stat -c '%u:%g:%h' "$path")" == 0:0:1 ]] || die "unsafe state links: $path"
  done
  [[ "$(stat -c '%a' "$STATE_DIR/key-added")" == 400 ]] || die 'key-added state mode mismatch'
  [[ "$(stat -c '%a' "$STATE_DIR/operator.pub")" == 400 ]] || die 'public-key state mode mismatch'
  [[ "$(stat -c '%a' "$STATE_DIR/rollback.sh")" == 500 ]] || die 'rollback state mode mismatch'
  [[ "$(cat "$STATE_DIR/key-added")" == "$key_added_value" ]] || die 'key-added state differs'
  [[ "$(sha256sum "$STATE_DIR/operator.pub" | awk '{print $1}')" == "$public_key_sha256" ]] || \
    die 'state public key differs'
  cmp -s "$STATE_DIR/rollback.sh" "$ROLLBACK" || die 'state rollback differs'
  [[ -f "$AUTHORIZED_KEYS" && ! -L "$AUTHORIZED_KEYS" ]] || die 'authorized_keys is missing'
  [[ "$(stat -c '%u:%g:%a:%h' "$AUTHORIZED_KEYS")" == 1000:1000:600:1 ]] || \
    die 'authorized_keys identity is unsafe'
  key_line=$(cat "$PUBLIC_KEY_SOURCE")
  key_blob=$(awk '{print $2}' "$PUBLIC_KEY_SOURCE")
  authorized_line="restrict,command=\"/usr/local/bin/r46h-screenshot-ssh\" $key_line"
  key_count=$(awk -v target="$authorized_line" '$0 == target { count++ } END { print count + 0 }' \
    "$AUTHORIZED_KEYS")
  blob_count=$(awk -v blob="$key_blob" \
    '{ for (field=1; field<NF; field++) if ($field == "ssh-ed25519" && $(field+1) == blob) count++ } END { print count + 0 }' \
    "$AUTHORIZED_KEYS")
  [[ "$key_count" == 1 && "$blob_count" == 1 ]] || die 'installed screenshot key changed'
}

[[ $# == 4 ]] || { usage >&2; exit 2; }
installer_sha256=""
public_key_sha256=""
while (( $# > 0 )); do
  case $1 in
    --installer-sha256) installer_sha256=$2 ;;
    --public-key-sha256) public_key_sha256=$2 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift 2
done
[[ "$installer_sha256" =~ ^[0-9a-f]{64}$ ]] || die 'invalid installer SHA-256'
[[ "$public_key_sha256" =~ ^[0-9a-f]{64}$ ]] || die 'invalid public-key SHA-256'
(( EUID == 0 )) || die 'root is required'
[[ "${BASH_SOURCE[0]}" == "$PAYLOAD_DIR/install.sh" ]] || die "stage payload at $PAYLOAD_DIR"
[[ -d "$PAYLOAD_DIR" && ! -L "$PAYLOAD_DIR" ]] || die 'unsafe payload directory'
[[ "$(stat -c '%u:%g:%a' "$PAYLOAD_DIR")" == 0:0:700 ]] || die 'unsafe payload directory identity'
payload_members=$(find "$PAYLOAD_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
[[ "$payload_members" == $'install.sh\noperator.pub\nr46h-drm-capture\nr46h-remote-screen.sudoers\nr46h-screenshot\nr46h-screenshot-ssh\nrollback.sh' ]] || \
  die 'unexpected payload member set'
while IFS= read -r path; do
  [[ -f "$path" && ! -L "$path" ]] || die "unsafe payload member: $path"
  [[ "$(stat -c '%u:%g:%a:%h' "$path")" == 0:0:600:1 ]] || \
    die "unsafe payload member identity: $path"
done < <(find "$PAYLOAD_DIR" -mindepth 1 -maxdepth 1 -type f -print)
[[ "$(sha256sum "${BASH_SOURCE[0]}" | awk '{print $1}')" == "$installer_sha256" ]] || \
  die 'installer SHA-256 mismatch'
[[ "$(sha256sum "$PUBLIC_KEY_SOURCE" | awk '{print $1}')" == "$public_key_sha256" ]] || \
  die 'public-key SHA-256 mismatch'
for specification in \
  "$CAPTURE_SOURCE:$CAPTURE_SHA256" \
  "$HELPER_SOURCE:$HELPER_SHA256" \
  "$GATEWAY_SOURCE:$GATEWAY_SHA256" \
  "$SUDOERS_SOURCE:$SUDOERS_SHA256" \
  "$ROLLBACK_SOURCE:$ROLLBACK_SHA256"; do
  IFS=: read -r path digest <<< "$specification"
  [[ "$(sha256sum "$path" | awk '{print $1}')" == "$digest" ]] || die "payload hash mismatch: $path"
done
/usr/sbin/visudo -cf "$SUDOERS_SOURCE" >/dev/null || die 'candidate sudo policy is invalid'
key_fields=$(awk 'NR == 1 && NF == 3 && $1 == "ssh-ed25519" && $3 == "r46h-remote-screen-v0.1" { print NF } END { if (NR != 1) exit 1 }' \
  "$PUBLIC_KEY_SOURCE")
[[ "$key_fields" == 3 ]] || die 'operator.pub is not the dedicated ED25519 public key'
key_fingerprint=$(ssh-keygen -lf "$PUBLIC_KEY_SOURCE" -E sha256 | \
  awk 'NF >= 4 && $1 == 256 && $2 ~ /^SHA256:/ && $4 == "(ED25519)" { print $2 }')
[[ "$key_fingerprint" =~ ^SHA256:[A-Za-z0-9+/]+$ ]] || die 'invalid ED25519 public key'

[[ "$(uname -r)" == "$EXPECTED_RELEASE" ]] || die 'unexpected running kernel'
[[ "$(findmnt -rn -o PARTUUID /)" == "$EXPECTED_ROOT_PARTUUID" ]] || die 'unexpected root partition'
[[ "$(findmnt -rn -o UUID /)" == "$EXPECTED_ROOT_UUID" ]] || die 'unexpected p2 image UUID'
[[ "$(findmnt -rn -o FSTYPE /)" == ext4 ]] || die 'root is not ext4'
[[ ",$(findmnt -rn -o OPTIONS /)," == *,rw,* ]] || die 'root is not writable'
[[ ",$(findmnt -rn -o OPTIONS /roms)," == *,ro,* ]] || die '/roms is not read-only'
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem already reports errors'
[[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd has failed units'
for specification in \
  "$BASE_RECEIPT:$BASE_RECEIPT_SHA256:0:0:600" \
  "$OZONE_RECEIPT:$OZONE_RECEIPT_SHA256:0:0:600" \
  "$CONFIG:$CONFIG_SHA256:0:0:644" \
  "$RUNNER:$RUNNER_SHA256:0:0:755"; do
  IFS=: read -r path digest owner group mode <<< "$specification"
  [[ -f "$path" && ! -L "$path" ]] || die "accepted predecessor file is unsafe: $path"
  [[ "$(stat -c '%u:%g:%a:%h' "$path")" == "$owner:$group:$mode:1" ]] || \
    die "accepted predecessor identity changed: $path"
  [[ "$(sha256sum "$path" | awk '{print $1}')" == "$digest" ]] || \
    die "accepted predecessor content changed: $path"
done
[[ "$(id -u ark):$(id -g ark)" == 1000:1000 ]] || die 'unexpected ark identity'
[[ -d /home/ark && ! -L /home/ark && "$(stat -c '%u:%g' /home/ark)" == 1000:1000 ]] || \
  die 'ark home is unsafe'
for directory in /usr/local/libexec /usr/local/bin /usr/local/sbin /etc/sudoers.d /var/lib/r46h; do
  [[ -d "$directory" && ! -L "$directory" ]] || die "unsafe install directory: $directory"
  [[ "$(stat -c '%u:%g' "$directory")" == 0:0 ]] || die "unexpected install directory owner: $directory"
done
[[ "$(systemctl is-active r46h-gaming-frontend.service || true)" == active ]] || \
  die 'gaming frontend is not active'
mapfile -t retroarch_pids < <(pgrep -u 1000 -x retroarch || true)
(( ${#retroarch_pids[@]} == 1 )) || die 'expected exactly one ark RetroArch process'
retroarch_pid=${retroarch_pids[0]}
[[ "$(readlink "/proc/$retroarch_pid/exe")" == /usr/bin/retroarch ]] || die 'unexpected RetroArch executable'
frontend_restarts=$(systemctl show -p NRestarts --value r46h-gaming-frontend.service)
[[ "$frontend_restarts" == 0 ]] || die 'gaming frontend already restarted'
[[ -z "$(/usr/bin/ss -H -lun sport = :55355)" ]] || die 'RetroArch UDP command listener is active'

if [[ -e "$RECEIPT" || -L "$RECEIPT" ]]; then
  verify_installed
  printf 'PASS: R46H remote-screen v0.1 is already installed.\n'
  exit 0
fi
for path in "$CAPTURE" "$HELPER" "$GATEWAY" "$SUDOERS" "$ROLLBACK" "$STATE_DIR"; do
  [[ ! -e "$path" && ! -L "$path" ]] || die "feature path already exists: $path"
done
if [[ -e "$STATE_PARENT" || -L "$STATE_PARENT" ]]; then
  [[ -d "$STATE_PARENT" && ! -L "$STATE_PARENT" ]] || die 'state parent is unsafe'
  [[ "$(stat -c '%u:%g:%a' "$STATE_PARENT")" == 0:0:700 ]] || die 'state parent identity is unsafe'
  [[ -z "$(find "$STATE_PARENT" -mindepth 1 -maxdepth 1 -print -quit)" ]] || \
    die 'state parent is not empty'
fi
for directory in /home/ark/.ssh /home/ark/.cache /home/ark/.cache/r46h "$SCREENSHOT_ROOT" \
  "$SCREENSHOT_ROOT/capture" "$SCREENSHOT_ROOT/exports"; do
  [[ ! -L "$directory" ]] || die "symbolic-link directory is forbidden: $directory"
  if [[ -e "$directory" ]]; then
    [[ -d "$directory" && "$(stat -c '%u:%g:%a' "$directory")" == 1000:1000:700 ]] || \
      die "existing ark directory is unsafe: $directory"
  fi
done
if [[ -e "$AUTHORIZED_KEYS" || -L "$AUTHORIZED_KEYS" ]]; then
  [[ -f "$AUTHORIZED_KEYS" && ! -L "$AUTHORIZED_KEYS" ]] || die 'authorized_keys is unsafe'
  [[ "$(stat -c '%u:%g:%a:%h' "$AUTHORIZED_KEYS")" == 1000:1000:600:1 ]] || \
    die 'authorized_keys identity is unsafe'
  [[ "$(stat -c '%s' "$AUTHORIZED_KEYS")" -le 65536 ]] || die 'authorized_keys is unexpectedly large'
fi

trap cleanup_install EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
transaction_active=1

if [[ ! -d "$STATE_PARENT" ]]; then
  install -d -o root -g root -m 0700 "$STATE_PARENT"
  state_parent_created=1
fi
state_stage=$STATE_PARENT/.stage-v0.1.$$
[[ ! -e "$state_stage" && ! -L "$state_stage" ]] || die 'rollback state stage exists'
install -d -o root -g root -m 0700 "$state_stage"
install -o root -g root -m 0400 "$PUBLIC_KEY_SOURCE" "$state_stage/operator.pub"
install -o root -g root -m 0500 "$ROLLBACK_SOURCE" "$state_stage/rollback.sh"
printf 'pending\n' > "$state_stage/key-added"
chmod 0400 "$state_stage/key-added"
mv -T --no-clobber -- "$state_stage" "$STATE_DIR"
state_stage=""
state_published=1

if [[ ! -d /home/ark/.ssh ]]; then
  install -d -o ark -g ark -m 0700 /home/ark/.ssh
  ssh_dir_created=1
fi
for directory in /home/ark/.cache /home/ark/.cache/r46h; do
  [[ -d "$directory" ]] || die "required Ozone cache directory is absent: $directory"
done
if [[ ! -d "$SCREENSHOT_ROOT" ]]; then
  install -d -o ark -g ark -m 0700 "$SCREENSHOT_ROOT"
  screenshot_root_created=1
fi
if [[ ! -d "$SCREENSHOT_ROOT/capture" ]]; then
  install -d -o ark -g ark -m 0700 "$SCREENSHOT_ROOT/capture"
  capture_dir_created=1
fi
if [[ ! -d "$SCREENSHOT_ROOT/exports" ]]; then
  install -d -o ark -g ark -m 0700 "$SCREENSHOT_ROOT/exports"
  export_dir_created=1
fi

capture_stage=/usr/local/libexec/.r46h-drm-capture.$$
helper_stage=/usr/local/bin/.r46h-screenshot.$$
gateway_stage=/usr/local/bin/.r46h-screenshot-ssh.$$
sudoers_stage=/etc/sudoers.d/.r46h-remote-screen.$$
rollback_stage=/usr/local/sbin/.r46h-remote-screen-rollback.$$
install -o root -g root -m 0755 "$CAPTURE_SOURCE" "$capture_stage"
install -o root -g root -m 0755 "$HELPER_SOURCE" "$helper_stage"
install -o root -g root -m 0755 "$GATEWAY_SOURCE" "$gateway_stage"
install -o root -g root -m 0440 "$SUDOERS_SOURCE" "$sudoers_stage"
install -o root -g root -m 0700 "$ROLLBACK_SOURCE" "$rollback_stage"
/usr/sbin/visudo -cf "$sudoers_stage" >/dev/null || die 'staged sudo policy is invalid'
mv -T --no-clobber -- "$capture_stage" "$CAPTURE"
capture_stage=""
capture_installed=1
mv -T --no-clobber -- "$helper_stage" "$HELPER"
helper_stage=""
helper_installed=1
mv -T --no-clobber -- "$gateway_stage" "$GATEWAY"
gateway_stage=""
gateway_installed=1
mv -T --no-clobber -- "$sudoers_stage" "$SUDOERS"
sudoers_stage=""
sudoers_installed=1
mv -T --no-clobber -- "$rollback_stage" "$ROLLBACK"
rollback_stage=""
rollback_installed=1

key_line=$(cat "$PUBLIC_KEY_SOURCE")
key_blob=$(awk '{print $2}' "$PUBLIC_KEY_SOURCE")
authorized_line="restrict,command=\"/usr/local/bin/r46h-screenshot-ssh\" $key_line"
if [[ -f "$AUTHORIZED_KEYS" ]]; then
  key_count=$(awk -v target="$authorized_line" '$0 == target { count++ } END { print count + 0 }' \
    "$AUTHORIZED_KEYS")
  blob_count=$(awk -v blob="$key_blob" \
    '{ for (field=1; field<NF; field++) if ($field == "ssh-ed25519" && $(field+1) == blob) count++ } END { print count + 0 }' \
    "$AUTHORIZED_KEYS")
else
  key_count=0
  blob_count=0
fi
[[ "$key_count" == 0 || "$key_count" == 1 ]] || die 'dedicated public key is duplicated'
[[ "$blob_count" == "$key_count" ]] || die 'dedicated public key already has broader authorization'
if [[ "$key_count" == 0 ]]; then
  auth_stage=/home/ark/.ssh/.authorized_keys.remote-screen.$$
  [[ ! -e "$auth_stage" && ! -L "$auth_stage" ]] || die 'authorized_keys stage exists'
  if [[ -f "$AUTHORIZED_KEYS" ]]; then
    install -o ark -g ark -m 0600 "$AUTHORIZED_KEYS" "$auth_stage"
    if [[ -s "$auth_stage" ]] && \
       [[ "$(tail -c 1 "$auth_stage" | od -An -tu1 | tr -d '[:space:]')" != 10 ]]; then
      printf '\n' >> "$auth_stage"
    fi
  else
    install -o ark -g ark -m 0600 /dev/null "$auth_stage"
  fi
  printf '%s\n' "$authorized_line" >> "$auth_stage"
  mv -f -- "$auth_stage" "$AUTHORIZED_KEYS"
  auth_stage=""
  key_added=1
fi
key_added_value=$([[ $key_added == 1 ]] && printf yes || printf no)
printf '%s\n' "$key_added_value" > "$STATE_DIR/.key-added.$$.tmp"
chmod 0400 "$STATE_DIR/.key-added.$$.tmp"
mv -f -- "$STATE_DIR/.key-added.$$.tmp" "$STATE_DIR/key-added"

receipt_stage=/var/lib/r46h/.remote-screen-v0.1-installed.$$
printf 'feature_id=%s\nozone_receipt_sha256=%s\ncapture_sha256=%s\nhelper_sha256=%s\ngateway_sha256=%s\nsudoers_sha256=%s\nrollback_sha256=%s\ninstaller_sha256=%s\npublic_key_sha256=%s\nkey_added=%s\n' \
  "$FEATURE_ID" "$OZONE_RECEIPT_SHA256" "$CAPTURE_SHA256" "$HELPER_SHA256" \
  "$GATEWAY_SHA256" "$SUDOERS_SHA256" "$ROLLBACK_SHA256" "$installer_sha256" \
  "$public_key_sha256" "$key_added_value" > "$receipt_stage"
chmod 0600 "$receipt_stage"
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem reported an error during install'
sync
ln -- "$receipt_stage" "$RECEIPT"
rm -f -- "$receipt_stage"
receipt_stage=""
receipt_installed=1
sync

verify_installed
[[ "$(systemctl is-active r46h-gaming-frontend.service || true)" == active ]] || \
  die 'frontend stopped during install'
[[ "$(pgrep -u 1000 -x retroarch)" == "$retroarch_pid" ]] || die 'RetroArch changed during install'
[[ "$(systemctl show -p NRestarts --value r46h-gaming-frontend.service)" == "$frontend_restarts" ]] || \
  die 'frontend restarted during install'
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem reported an error after install'
[[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd has failed units after install'
[[ -z "$(/usr/bin/ss -H -lun sport = :55355)" ]] || die 'RetroArch UDP command listener is active'

transaction_active=0
trap - EXIT INT TERM HUP
printf 'PASS: R46H remote-screen v0.1 installed; frontend_untouched=active key_added=%s.\n' \
  "$key_added_value"
printf 'PUBLIC_KEY_FINGERPRINT=%s\n' "$key_fingerprint"
printf 'NEXT=run-r46h-screenshot-over-strict-host-key-SSH\n'
