#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG

readonly EXPECTED_RELEASE=6.12.99-r46h-mainline-v0.10-adc-full-range
readonly EXPECTED_ROOT_PARTUUID=c9f931c9-02
readonly CONFIG=/etc/r46h/retroarch.cfg
readonly BASE_CONFIG_SHA256=621fdf049cd05e6aa02c62b5c42ed37a768ce9342af14c4563cfd4466d80d078
readonly CONFIG_SHA256=697aa82bb42689cd841f16a8ce1ae9c6ac2bdc56ccd1b811136f8f5884e600e9
readonly STATE_PARENT=/var/lib/r46h-gaming-history
readonly STATE_DIR=/var/lib/r46h-gaming-history/v0.2
readonly RECEIPT=/var/lib/r46h/gaming-history-v0.2-installed
readonly ROLLBACK=/usr/local/sbin/r46h-gaming-history-rollback
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count
readonly RETROARCH_STATE=/home/ark/.local/share/retroarch
readonly BASE_RETROARCH_STATE_IDENTITY=0:0:755
readonly CANDIDATE_RETROARCH_STATE_IDENTITY=1000:1000:700
readonly ROLLBACK_INTERMEDIATE_STATE_IDENTITY=1000:1000:755

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ $# == 0 ]] || die 'this rollback accepts no arguments'
(( EUID == 0 )) || die 'root is required'
[[ "${BASH_SOURCE[0]}" == "$ROLLBACK" ]] || die 'run the installed rollback helper'
[[ "$(uname -r)" == "$EXPECTED_RELEASE" ]] || die 'rollback from exact persistent v0.10'
[[ "$(findmnt -rn -o PARTUUID /)" == "$EXPECTED_ROOT_PARTUUID" ]] || die 'unexpected root partition'
[[ "$(findmnt -rn -o FSTYPE /)" == ext4 ]] || die 'root is not ext4'
[[ ",$(findmnt -rn -o OPTIONS /)," == *,rw,* ]] || die 'root is not writable'
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem already reports errors'
[[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd has failed units'
[[ -f "$CONFIG" && ! -L "$CONFIG" ]] || die 'RetroArch config is missing'
current_config_sha256=$(sha256sum "$CONFIG" | awk '{print $1}')
[[ "$current_config_sha256" == "$CONFIG_SHA256" || "$current_config_sha256" == "$BASE_CONFIG_SHA256" ]] || die 'RetroArch config mismatch'
[[ -f "$RECEIPT" && ! -L "$RECEIPT" ]] || die 'history receipt is missing'
[[ "$(stat -c '%u:%g:%a:%h' "$RECEIPT")" == 0:0:600:1 ]] || die 'unsafe history receipt'
[[ "$(wc -l < "$RECEIPT" | tr -d '[:space:]')" == 7 ]] || die 'history receipt line count mismatch'
grep -Fqx 'fix_id=r46h-gaming-history-v0.2' "$RECEIPT" || die 'history receipt mismatch'
grep -Fqx "base_config_sha256=$BASE_CONFIG_SHA256" "$RECEIPT" || die 'base config receipt mismatch'
grep -Fqx "config_sha256=$CONFIG_SHA256" "$RECEIPT" || die 'config receipt mismatch'
grep -Eq '^installer_sha256=[0-9a-f]{64}$' "$RECEIPT" || die 'installer receipt mismatch'
grep -Fqx "base_retroarch_state_identity=$BASE_RETROARCH_STATE_IDENTITY" "$RECEIPT" || \
  die 'base RetroArch state receipt mismatch'
grep -Fqx "retroarch_state_identity=$CANDIDATE_RETROARCH_STATE_IDENTITY" "$RECEIPT" || \
  die 'RetroArch state receipt mismatch'
for directory in /home/ark/.local /home/ark/.local/share "$RETROARCH_STATE"; do
  [[ ! -L "$directory" ]] || die "symbolic-link directory is forbidden: $directory"
done
[[ -d "$RETROARCH_STATE" ]] || die 'RetroArch user state directory is missing'
retroarch_state_identity=$(stat -c '%u:%g:%a' "$RETROARCH_STATE")
[[ "$retroarch_state_identity" == "$CANDIDATE_RETROARCH_STATE_IDENTITY" ||
   "$retroarch_state_identity" == "$ROLLBACK_INTERMEDIATE_STATE_IDENTITY" ||
   "$retroarch_state_identity" == "$BASE_RETROARCH_STATE_IDENTITY" ]] || \
  die 'unexpected RetroArch state identity'
[[ -d "$STATE_PARENT" && ! -L "$STATE_PARENT" ]] || die 'history state parent is missing'
[[ "$(stat -c '%u:%g:%a' "$STATE_PARENT")" == 0:0:700 ]] || die 'unsafe history state parent'
[[ -d "$STATE_DIR" && ! -L "$STATE_DIR" ]] || die 'history state is missing'
[[ "$(stat -c '%u:%g:%a' "$STATE_DIR")" == 0:0:700 ]] || die 'unsafe history state'
state_members=$(find "$STATE_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
[[ "$state_members" == $'base-retroarch.cfg\nrollback.sh' ]] || die 'unexpected history state member set'
for path in "$STATE_DIR/base-retroarch.cfg" "$STATE_DIR/rollback.sh" "$ROLLBACK"; do
  [[ -f "$path" && ! -L "$path" ]] || die "unsafe history state member: $path"
  [[ "$(stat -c '%h' "$path")" == 1 ]] || die "hard-linked history state member: $path"
done
[[ "$(stat -c '%u:%g:%a' "$STATE_DIR/base-retroarch.cfg")" == 0:0:400 ]] || die 'unsafe base config state identity'
[[ "$(stat -c '%u:%g:%a' "$STATE_DIR/rollback.sh")" == 0:0:500 ]] || die 'unsafe rollback state identity'
[[ "$(stat -c '%u:%g:%a' "$ROLLBACK")" == 0:0:700 ]] || die 'unsafe installed rollback identity'
[[ "$(sha256sum "$STATE_DIR/base-retroarch.cfg" | awk '{print $1}')" == "$BASE_CONFIG_SHA256" ]] || die 'base config state mismatch'
rollback_sha256=$(sha256sum "$STATE_DIR/rollback.sh" | awk '{print $1}')
grep -Fqx "rollback_sha256=$rollback_sha256" "$RECEIPT" || die 'rollback receipt mismatch'
cmp -s "$STATE_DIR/rollback.sh" "$ROLLBACK" || die 'installed rollback mismatch'

systemctl stop r46h-gaming-frontend.service
[[ "$(systemctl is-active r46h-gaming-frontend.service || true)" == inactive ]] || die 'frontend did not stop'
[[ -z "$(pgrep -x retroarch || true)" ]] || die 'RetroArch process survived service stop'

if [[ "$current_config_sha256" == "$CONFIG_SHA256" ]]; then
  config_stage=/etc/r46h/.retroarch.cfg.history-rollback.$$
  trap 'rm -f -- "$config_stage"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
  install -o root -g root -m 0644 "$STATE_DIR/base-retroarch.cfg" "$config_stage"
  mv -f -- "$config_stage" "$CONFIG"
  config_stage=""
  trap - EXIT INT TERM HUP
fi
[[ "$(sha256sum "$CONFIG" | awk '{print $1}')" == "$BASE_CONFIG_SHA256" ]] || die 'base config restore failed'

chmod 0755 "$RETROARCH_STATE"
chown 0:0 "$RETROARCH_STATE"
[[ "$(stat -c '%u:%g:%a' "$RETROARCH_STATE")" == "$BASE_RETROARCH_STATE_IDENTITY" ]] || \
  die 'base RetroArch state identity restore failed'

rm -f -- "$RECEIPT"
rm -f -- "$STATE_DIR/base-retroarch.cfg" "$STATE_DIR/rollback.sh"
rmdir -- "$STATE_DIR"
rmdir -- "$STATE_PARENT" 2>/dev/null || true
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem reported an error during rollback'
sync
rm -f -- "$ROLLBACK"
sync

printf 'PASS: R46H RetroArch history-directory fix rolled back to exact v0.1 config.\n'
