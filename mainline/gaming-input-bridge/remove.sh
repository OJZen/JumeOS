#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG

readonly EXPECTED_RELEASE=6.12.99-r46h-mainline-v0.10-adc-full-range
readonly EXPECTED_ROOT_PARTUUID=c9f931c9-02
readonly STATE_PARENT=/var/lib/r46h-gaming-input-bridge
readonly STATE_DIR=/var/lib/r46h-gaming-input-bridge/v0.5
readonly RECEIPT=/var/lib/r46h/gaming-input-bridge-v0.5-installed
readonly HISTORY_RECEIPT=/var/lib/r46h/gaming-history-v0.2-installed
readonly HISTORY_RECEIPT_SHA256=9b800245202992cbdc063e5cabd071a6265fbb9133e89a8718d0952209d0f1aa
readonly RETROARCH_STATE=/home/ark/.local/share/retroarch
readonly BASE_CONFIG=/etc/r46h/retroarch.cfg
readonly BASE_CONFIG_SHA256=697aa82bb42689cd841f16a8ce1ae9c6ac2bdc56ccd1b811136f8f5884e600e9
readonly BRIDGE=/usr/local/libexec/r46h-input-bridge
readonly WAITER=/usr/local/libexec/r46h-input-bridge-wait
readonly RUNNER=/usr/local/sbin/r46h-game-ui-input-candidate
readonly TRIAL=/usr/local/sbin/r46h-input-bridge-trial
readonly REMOVE=/usr/local/sbin/r46h-input-bridge-remove
readonly UNIT=/etc/systemd/system/r46h-input-bridge.service
readonly CANDIDATE_CONFIG=/etc/r46h/retroarch-input-candidate.cfg
readonly DIAGNOSTICS_DIR=/run/r46h-input-bridge
readonly DIAGNOSTICS=$DIAGNOSTICS_DIR/diagnostics
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count

state_tombstone=""
deletion_started=0

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

runtime_matches_or_absent() {
  local source=$1 destination=$2

  if [[ -e "$destination" || -L "$destination" ]]; then
    [[ -f "$destination" && ! -L "$destination" ]] || return 1
    cmp -s "$source" "$destination"
  fi
}

remove_runtime_diagnostics() {
  local members

  [[ -e "$DIAGNOSTICS_DIR" || -L "$DIAGNOSTICS_DIR" ]] || return 0
  [[ -d "$DIAGNOSTICS_DIR" && ! -L "$DIAGNOSTICS_DIR" ]] || return 1
  [[ "$(stat -c '%u:%g:%a' "$DIAGNOSTICS_DIR")" == 0:0:700 ]] || return 1
  members=$(find "$DIAGNOSTICS_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort)
  [[ -z "$members" || "$members" == diagnostics ]] || return 1
  if [[ -e "$DIAGNOSTICS" || -L "$DIAGNOSTICS" ]]; then
    [[ -f "$DIAGNOSTICS" && ! -L "$DIAGNOSTICS" ]] || return 1
    [[ "$(stat -c '%u:%g:%a:%h' "$DIAGNOSTICS")" == 0:0:600:1 ]] || return 1
    rm -f -- "$DIAGNOSTICS"
  fi
  rmdir -- "$DIAGNOSTICS_DIR"
}

remove_state_members() {
  local directory=$1

  rm -f -- \
    "$directory/OPERATIONS.md" \
    "$directory/SHA256SUMS" \
    "$directory/r46h-game-ui-input-candidate" \
    "$directory/r46h-input-bridge" \
    "$directory/r46h-input-bridge-remove" \
    "$directory/r46h-input-bridge-trial" \
    "$directory/r46h-input-bridge-wait" \
    "$directory/r46h-input-bridge.service" \
    "$directory/retroarch.cfg"
  rmdir -- "$directory"
}

restore_on_failure() {
  local status=$?

  trap - EXIT INT TERM HUP
  set +e
  if (( deletion_started == 0 )) &&
     [[ -n "$state_tombstone" && -d "$state_tombstone" && ! -L "$state_tombstone" ]]; then
    if [[ ! -e "$STATE_DIR" && ! -L "$STATE_DIR" ]]; then
      mv -T --no-clobber -- "$state_tombstone" "$STATE_DIR" || \
        printf 'ERROR: guarded rollback could not restore %s\n' "$STATE_DIR" >&2
    else
      printf 'ERROR: guarded rollback found both state and tombstone under %s\n' \
        "$STATE_PARENT" >&2
    fi
  elif (( deletion_started == 1 )); then
    printf 'ERROR: removal stopped after exact state deletion began; inspect %s before retrying\n' \
      "$STATE_PARENT" >&2
  fi
  exit "$status"
}

[[ $# == 0 ]] || die 'this remover accepts no arguments'
(( EUID == 0 )) || die 'root is required'
[[ "${BASH_SOURCE[0]}" == "$REMOVE" ]] || die 'run the installed guarded remover'
[[ "$(uname -r)" == "$EXPECTED_RELEASE" ]] || die 'remove from exact persistent v0.10'
[[ "$(findmnt -rn -T /run -o FSTYPE)" == tmpfs ]] || die '/run is not tmpfs'
[[ "$(findmnt -rn -o PARTUUID /)" == "$EXPECTED_ROOT_PARTUUID" ]] || die 'unexpected root partition'
[[ "$(findmnt -rn -o FSTYPE /)" == ext4 ]] || die 'root is not ext4'
[[ ",$(findmnt -rn -o OPTIONS /)," == *,rw,* ]] || die 'root is not writable'
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem already reports errors'
[[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd has failed units'
[[ -f "$HISTORY_RECEIPT" && ! -L "$HISTORY_RECEIPT" ]] || die 'history receipt is missing'
[[ "$(stat -c '%u:%g:%a:%h' "$HISTORY_RECEIPT")" == 0:0:600:1 ]] || die 'unsafe history receipt'
[[ "$(sha256sum "$HISTORY_RECEIPT" | awk '{print $1}')" == "$HISTORY_RECEIPT_SHA256" ]] || die 'history receipt mismatch'
[[ -d "$RETROARCH_STATE" && ! -L "$RETROARCH_STATE" ]] || die 'RetroArch user state is missing'
[[ "$(stat -c '%u:%g:%a' "$RETROARCH_STATE")" == 1000:1000:700 ]] || die 'RetroArch user state identity mismatch'
[[ -f "$BASE_CONFIG" && ! -L "$BASE_CONFIG" ]] || die 'base RetroArch config is missing'
[[ "$(sha256sum "$BASE_CONFIG" | awk '{print $1}')" == "$BASE_CONFIG_SHA256" ]] || die 'base RetroArch config changed'
[[ -f "$RECEIPT" && ! -L "$RECEIPT" ]] || die 'candidate receipt is missing'
[[ "$(stat -c '%u:%g:%a:%h' "$RECEIPT")" == 0:0:600:1 ]] || die 'unsafe candidate receipt'
[[ "$(wc -l < "$RECEIPT" | tr -d '[:space:]')" == 5 ]] || die 'candidate receipt line count mismatch'
grep -Fqx 'payload_id=r46h-gaming-input-bridge-v0.5' "$RECEIPT" || die 'candidate receipt mismatch'
grep -Fqx 'install_release=6.12.99-r46h-mainline-v0.10-adc-full-range' "$RECEIPT" || die 'candidate install release mismatch'
grep -Fqx 'test_release=6.12.99-r46h-mainline-v0.14-gaming-input-bridge' "$RECEIPT" || die 'candidate test release mismatch'
grep -Fqx "base_config_sha256=$BASE_CONFIG_SHA256" "$RECEIPT" || die 'candidate base config receipt mismatch'
[[ -d "$STATE_PARENT" && ! -L "$STATE_PARENT" ]] || die 'candidate state parent is missing'
[[ "$(stat -c '%u:%g:%a' "$STATE_PARENT")" == 0:0:700 ]] || die 'unsafe candidate state parent'
[[ -d "$STATE_DIR" && ! -L "$STATE_DIR" ]] || die 'candidate state is missing'
[[ "$(stat -c '%u:%g:%a' "$STATE_DIR")" == 0:0:700 ]] || die 'unsafe candidate state'
state_members=$(find "$STATE_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort)
[[ "$state_members" == $'OPERATIONS.md\nSHA256SUMS\nr46h-game-ui-input-candidate\nr46h-input-bridge\nr46h-input-bridge-remove\nr46h-input-bridge-trial\nr46h-input-bridge-wait\nr46h-input-bridge.service\nretroarch.cfg' ]] || die 'unexpected candidate state member set'
[[ -z "$(find "$STATE_DIR" -xdev -type l -print -quit)" ]] || die 'candidate state contains a symbolic link'
[[ -z "$(find "$STATE_DIR" -xdev ! -type d ! -type f -print -quit)" ]] || die 'candidate state contains a special file'
[[ -z "$(find "$STATE_DIR" -xdev -type f ! -links 1 -print -quit)" ]] || die 'candidate state contains a hard-linked file'
(cd "$STATE_DIR" && sha256sum -c SHA256SUMS)
grep -Fqx "state_sha256sums_sha256=$(sha256sum "$STATE_DIR/SHA256SUMS" | awk '{print $1}')" \
  "$RECEIPT" || die 'candidate state receipt mismatch'
runtime_matches_or_absent "$STATE_DIR/r46h-input-bridge" "$BRIDGE" || die 'runtime bridge mismatch'
runtime_matches_or_absent "$STATE_DIR/r46h-input-bridge-wait" "$WAITER" || die 'runtime waiter mismatch'
runtime_matches_or_absent "$STATE_DIR/r46h-game-ui-input-candidate" "$RUNNER" || die 'runtime runner mismatch'
runtime_matches_or_absent "$STATE_DIR/r46h-input-bridge-trial" "$TRIAL" || die 'runtime trial mismatch'
runtime_matches_or_absent "$STATE_DIR/r46h-input-bridge-remove" "$REMOVE" || die 'runtime remover mismatch'
runtime_matches_or_absent "$STATE_DIR/r46h-input-bridge.service" "$UNIT" || die 'runtime unit mismatch'
runtime_matches_or_absent "$STATE_DIR/retroarch.cfg" "$CANDIDATE_CONFIG" || die 'runtime config mismatch'

systemctl stop r46h-input-bridge.service >/dev/null 2>&1 || true
active_state=$(systemctl is-active r46h-input-bridge.service 2>/dev/null || true)
[[ "$active_state" != active && "$active_state" != activating && "$active_state" != deactivating ]] || \
  die 'candidate service did not stop'
[[ -z "$(pgrep -f '^/usr/local/libexec/r46h-input-bridge --diagnostics$' || true)" ]] || die 'bridge process survived service stop'
[[ -z "$(pgrep -x retroarch || true)" ]] || die 'RetroArch is still active'
remove_runtime_diagnostics || die 'unsafe bridge diagnostics directory'

state_tombstone=$STATE_PARENT/.remove-v0.5.$$
[[ ! -e "$state_tombstone" && ! -L "$state_tombstone" ]] || die 'candidate state tombstone already exists'
trap restore_on_failure EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

mv -T --no-clobber -- "$STATE_DIR" "$state_tombstone"
rm -f -- "$UNIT" "$CANDIDATE_CONFIG" "$BRIDGE" "$WAITER" "$RUNNER" "$TRIAL"
systemctl daemon-reload
[[ -z "$(pgrep -f '^/usr/local/libexec/r46h-input-bridge --diagnostics$' || true)" ]] || die 'bridge process reappeared during removal'
deletion_started=1
remove_state_members "$state_tombstone"
rm -f -- "$RECEIPT"
rmdir -- "$STATE_PARENT" 2>/dev/null || true
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem reported an error during removal'
sync
rm -f -- "$REMOVE"
sync
trap '' INT TERM HUP
trap - EXIT INT TERM HUP

printf 'PASS: exact inactive gaming input bridge candidate removed; base frontend and BOOT were unchanged.\n'
