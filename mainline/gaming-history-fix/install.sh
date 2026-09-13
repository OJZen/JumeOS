#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG

readonly FIX_ID=r46h-gaming-history-v0.2
readonly EXPECTED_RELEASE=6.12.99-r46h-mainline-v0.10-adc-full-range
readonly EXPECTED_ROOT_PARTUUID=c9f931c9-02
readonly PAYLOAD_DIR=/run/r46h-gaming-history-v0.2
readonly CONFIG_SOURCE="$PAYLOAD_DIR/retroarch.cfg"
readonly ROLLBACK_SOURCE="$PAYLOAD_DIR/rollback.sh"
readonly CONFIG=/etc/r46h/retroarch.cfg
readonly BASE_CONFIG_SHA256=621fdf049cd05e6aa02c62b5c42ed37a768ce9342af14c4563cfd4466d80d078
readonly CONFIG_SHA256=697aa82bb42689cd841f16a8ce1ae9c6ac2bdc56ccd1b811136f8f5884e600e9
readonly ROLLBACK_SHA256=fb88d6f8d093527fb6b56730e6082cb088de97d8024ec1dac5f5b724acbc5819
readonly BASE_GAMING_RECEIPT=/var/lib/r46h/gaming-mvp-v0.3-installed
readonly BASE_GAMING_RECEIPT_SHA256=08e0c35e924666b5fb946fadadad95218ed6d49d3e3eca3a8cee3f85d98700b4
readonly ROM_WORKFLOW_RECEIPT=/var/lib/r46h/rom-workflow-v0.1-installed
readonly ROM_WORKFLOW_RECEIPT_SHA256=d33a1e23c83e2bbcfbb05180aabad4428d99809096f1ca589ddf1be308d2ff27
readonly STATE_PARENT=/var/lib/r46h-gaming-history
readonly STATE_DIR=/var/lib/r46h-gaming-history/v0.2
readonly RECEIPT=/var/lib/r46h/gaming-history-v0.2-installed
readonly ROLLBACK=/usr/local/sbin/r46h-gaming-history-rollback
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count
readonly RETROARCH_STATE=/home/ark/.local/share/retroarch
readonly BASE_RETROARCH_STATE_IDENTITY=0:0:755
readonly CANDIDATE_RETROARCH_STATE_IDENTITY=1000:1000:700

state_stage=""
config_stage=""
receipt_stage=""
state_parent_created=0
state_published=0
config_replaced=0
retroarch_state_normalized=0

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  printf 'usage: sudo /bin/bash %s --installer-sha256 HEX\n' "$PAYLOAD_DIR/install.sh"
}

remove_state() {
  local directory=$1

  rm -f -- "$directory/base-retroarch.cfg" "$directory/rollback.sh"
  rmdir -- "$directory" 2>/dev/null || true
}

cleanup_install() {
  local status=$?

  trap - EXIT INT TERM HUP
  set +e
  rm -f -- "$config_stage" "$receipt_stage" "$RECEIPT" "$ROLLBACK"
  if (( config_replaced == 1 && state_published == 1 )) &&
     [[ -f "$STATE_DIR/base-retroarch.cfg" && ! -L "$STATE_DIR/base-retroarch.cfg" ]]; then
    install -o root -g root -m 0644 "$STATE_DIR/base-retroarch.cfg" "$CONFIG.restore.$$" &&
      mv -f -- "$CONFIG.restore.$$" "$CONFIG"
  fi
  rm -f -- "$CONFIG.restore.$$"
  if (( state_published == 1 )) && [[ -d "$STATE_DIR" && ! -L "$STATE_DIR" ]]; then
    remove_state "$STATE_DIR"
  elif [[ -n "$state_stage" && -d "$state_stage" && ! -L "$state_stage" ]]; then
    remove_state "$state_stage"
  fi
  if (( state_parent_created == 1 )); then
    rmdir -- "$STATE_PARENT" 2>/dev/null || true
  fi
  if (( retroarch_state_normalized == 1 )); then
    chmod 0755 "$RETROARCH_STATE" || status=1
    chown 0:0 "$RETROARCH_STATE" || status=1
    [[ "$(stat -c '%u:%g:%a' "$RETROARCH_STATE" 2>/dev/null)" == \
      "$BASE_RETROARCH_STATE_IDENTITY" ]] || status=1
  fi
  exit "$status"
}

[[ $# == 2 && $1 == --installer-sha256 ]] || { usage >&2; exit 2; }
installer_sha256=$2
[[ "$installer_sha256" =~ ^[0-9a-f]{64}$ ]] || die 'invalid installer SHA-256'
(( EUID == 0 )) || die 'root is required'
[[ "${BASH_SOURCE[0]}" == "$PAYLOAD_DIR/install.sh" ]] || die "stage payload at $PAYLOAD_DIR"
[[ -d "$PAYLOAD_DIR" && ! -L "$PAYLOAD_DIR" ]] || die 'unsafe payload directory'
[[ "$(stat -c '%u:%g:%a' "$PAYLOAD_DIR")" == 0:0:700 ]] || die 'unsafe payload directory identity'
payload_members=$(find "$PAYLOAD_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
[[ "$payload_members" == $'install.sh\nretroarch.cfg\nrollback.sh' ]] || die 'unexpected payload member set'
for path in "${BASH_SOURCE[0]}" "$CONFIG_SOURCE" "$ROLLBACK_SOURCE"; do
  [[ -f "$path" && ! -L "$path" ]] || die "unsafe payload member: $path"
  [[ "$(stat -c '%u:%g:%a:%h' "$path")" == 0:0:600:1 ]] || die "unsafe payload member identity: $path"
done
[[ "$(sha256sum "${BASH_SOURCE[0]}" | awk '{print $1}')" == "$installer_sha256" ]] || die 'installer SHA-256 mismatch'
[[ "$(sha256sum "$CONFIG_SOURCE" | awk '{print $1}')" == "$CONFIG_SHA256" ]] || die 'config SHA-256 mismatch'
[[ "$(sha256sum "$ROLLBACK_SOURCE" | awk '{print $1}')" == "$ROLLBACK_SHA256" ]] || die 'rollback SHA-256 mismatch'

[[ "$(uname -r)" == "$EXPECTED_RELEASE" ]] || die 'unexpected running kernel'
[[ "$(findmnt -rn -o PARTUUID /)" == "$EXPECTED_ROOT_PARTUUID" ]] || die 'unexpected root partition'
[[ "$(findmnt -rn -o FSTYPE /)" == ext4 ]] || die 'root is not ext4'
[[ ",$(findmnt -rn -o OPTIONS /)," == *,rw,* ]] || die 'root is not writable'
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem already reports errors'
[[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd has failed units'
[[ -f "$BASE_GAMING_RECEIPT" && ! -L "$BASE_GAMING_RECEIPT" ]] || die 'gaming receipt is missing'
[[ "$(sha256sum "$BASE_GAMING_RECEIPT" | awk '{print $1}')" == "$BASE_GAMING_RECEIPT_SHA256" ]] || die 'gaming receipt mismatch'
[[ -f "$ROM_WORKFLOW_RECEIPT" && ! -L "$ROM_WORKFLOW_RECEIPT" ]] || die 'ROM workflow receipt is missing'
[[ "$(sha256sum "$ROM_WORKFLOW_RECEIPT" | awk '{print $1}')" == "$ROM_WORKFLOW_RECEIPT_SHA256" ]] || die 'ROM workflow receipt mismatch'
[[ -f "$CONFIG" && ! -L "$CONFIG" ]] || die 'base RetroArch config is missing'
[[ "$(stat -c '%u:%g:%a:%h' "$CONFIG")" == 0:0:644:1 ]] || die 'unsafe base RetroArch config identity'
[[ "$(sha256sum "$CONFIG" | awk '{print $1}')" == "$BASE_CONFIG_SHA256" ]] || die 'base RetroArch config mismatch'
[[ ! -e "$STATE_DIR" && ! -L "$STATE_DIR" ]] || die 'history state already exists'
[[ ! -e "$RECEIPT" && ! -L "$RECEIPT" ]] || die 'history receipt already exists'
[[ ! -e "$ROLLBACK" && ! -L "$ROLLBACK" ]] || die 'history rollback already exists'
for directory in /home/ark/.local /home/ark/.local/share "$RETROARCH_STATE"; do
  [[ ! -L "$directory" ]] || die "symbolic-link directory is forbidden: $directory"
done
[[ -d "$RETROARCH_STATE" ]] || die 'RetroArch user state directory is missing'
[[ "$(stat -c '%u:%g:%a' "$RETROARCH_STATE")" == "$BASE_RETROARCH_STATE_IDENTITY" ]] || \
  die 'unexpected base RetroArch state identity'

systemctl stop r46h-gaming-frontend.service
[[ "$(systemctl is-active r46h-gaming-frontend.service || true)" == inactive ]] || die 'frontend did not stop'
[[ -z "$(pgrep -x retroarch || true)" ]] || die 'RetroArch process survived service stop'

trap cleanup_install EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

retroarch_state_normalized=1
chown 1000:1000 "$RETROARCH_STATE"
chmod 0700 "$RETROARCH_STATE"
[[ "$(stat -c '%u:%g:%a' "$RETROARCH_STATE")" == "$CANDIDATE_RETROARCH_STATE_IDENTITY" ]] || \
  die 'RetroArch state normalization failed'

if [[ -e "$STATE_PARENT" || -L "$STATE_PARENT" ]]; then
  [[ -d "$STATE_PARENT" && ! -L "$STATE_PARENT" ]] || die 'unsafe history state parent'
  [[ "$(stat -c '%u:%g:%a' "$STATE_PARENT")" == 0:0:700 ]] || die 'unsafe history state parent identity'
else
  install -d -o root -g root -m 0700 "$STATE_PARENT"
  state_parent_created=1
fi
state_stage=$STATE_PARENT/.stage-v0.2.$$
[[ ! -e "$state_stage" && ! -L "$state_stage" ]] || die 'history state stage already exists'
install -d -o root -g root -m 0700 "$state_stage"
install -o root -g root -m 0400 "$CONFIG" "$state_stage/base-retroarch.cfg"
install -o root -g root -m 0500 "$ROLLBACK_SOURCE" "$state_stage/rollback.sh"
[[ "$(sha256sum "$state_stage/base-retroarch.cfg" | awk '{print $1}')" == "$BASE_CONFIG_SHA256" ]] || die 'base config state mismatch'
[[ "$(sha256sum "$state_stage/rollback.sh" | awk '{print $1}')" == "$ROLLBACK_SHA256" ]] || die 'rollback state mismatch'
mv -T --no-clobber -- "$state_stage" "$STATE_DIR"
state_stage=""
state_published=1

config_stage=/etc/r46h/.retroarch.cfg.history-v0.2.$$
[[ ! -e "$config_stage" && ! -L "$config_stage" ]] || die 'config stage already exists'
install -o root -g root -m 0644 "$CONFIG_SOURCE" "$config_stage"
mv -f -- "$config_stage" "$CONFIG"
config_stage=""
config_replaced=1
install -o root -g root -m 0700 "$STATE_DIR/rollback.sh" "$ROLLBACK"

receipt_stage=/var/lib/r46h/.gaming-history-v0.2-installed.$$
[[ ! -e "$receipt_stage" && ! -L "$receipt_stage" ]] || die 'receipt stage already exists'
printf 'fix_id=%s\nbase_config_sha256=%s\nconfig_sha256=%s\nrollback_sha256=%s\ninstaller_sha256=%s\nbase_retroarch_state_identity=%s\nretroarch_state_identity=%s\n' \
  "$FIX_ID" "$BASE_CONFIG_SHA256" "$CONFIG_SHA256" "$ROLLBACK_SHA256" \
  "$installer_sha256" "$BASE_RETROARCH_STATE_IDENTITY" \
  "$CANDIDATE_RETROARCH_STATE_IDENTITY" > "$receipt_stage"
chmod 0600 "$receipt_stage"
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem reported an error during install'
sync
ln "$receipt_stage" "$RECEIPT"
rm -f -- "$receipt_stage"
receipt_stage=""
sync
trap '' INT TERM HUP
trap - EXIT INT TERM HUP

printf 'PASS: R46H RetroArch history-directory fix installed; frontend remains stopped.\n'
printf 'NEXT=start-frontend-launch-one-rom-stop-and-verify-user-history\n'
