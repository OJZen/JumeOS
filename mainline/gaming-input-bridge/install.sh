#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG

readonly PAYLOAD_ID=r46h-gaming-input-bridge-v0.5
readonly EXPECTED_RUNNING_RELEASE=6.12.99-r46h-mainline-v0.10-adc-full-range
readonly EXPECTED_ROOT_PARTUUID=c9f931c9-02
readonly PAYLOAD_DIR=/run/r46h-gaming-input-bridge-v0.5
readonly STATE_PARENT=/var/lib/r46h-gaming-input-bridge
readonly STATE_DIR=/var/lib/r46h-gaming-input-bridge/v0.5
readonly RECEIPT=/var/lib/r46h/gaming-input-bridge-v0.5-installed
readonly BASE_GAMING_RECEIPT=/var/lib/r46h/gaming-mvp-v0.3-installed
readonly BASE_GAMING_RECEIPT_SHA256=08e0c35e924666b5fb946fadadad95218ed6d49d3e3eca3a8cee3f85d98700b4
readonly ROM_WORKFLOW_RECEIPT=/var/lib/r46h/rom-workflow-v0.1-installed
readonly ROM_WORKFLOW_RECEIPT_SHA256=d33a1e23c83e2bbcfbb05180aabad4428d99809096f1ca589ddf1be308d2ff27
readonly HISTORY_RECEIPT=/var/lib/r46h/gaming-history-v0.2-installed
readonly HISTORY_RECEIPT_SHA256=9b800245202992cbdc063e5cabd071a6265fbb9133e89a8718d0952209d0f1aa
readonly RETROARCH_STATE=/home/ark/.local/share/retroarch
readonly BASE_CONFIG=/etc/r46h/retroarch.cfg
readonly BASE_CONFIG_SHA256=697aa82bb42689cd841f16a8ce1ae9c6ac2bdc56ccd1b811136f8f5884e600e9
readonly BASE_RUNNER=/usr/local/sbin/r46h-game-ui
readonly BASE_RUNNER_SHA256=3d34e45ff35a6fa56e4b9d4fae3126dabdc60e1f6397d5419a25899b0f829708
readonly BRIDGE=/usr/local/libexec/r46h-input-bridge
readonly WAITER=/usr/local/libexec/r46h-input-bridge-wait
readonly RUNNER=/usr/local/sbin/r46h-game-ui-input-candidate
readonly TRIAL=/usr/local/sbin/r46h-input-bridge-trial
readonly REMOVE=/usr/local/sbin/r46h-input-bridge-remove
readonly UNIT=/etc/systemd/system/r46h-input-bridge.service
readonly CANDIDATE_CONFIG=/etc/r46h/retroarch-input-candidate.cfg
readonly DIAGNOSTICS_DIR=/run/r46h-input-bridge
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

state_stage=""
state_parent_created=0
receipt_stage=""
install_complete=0

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
  rmdir -- "$directory" 2>/dev/null || true
}

cleanup_install() {
  local status=$?

  trap - EXIT INT TERM HUP
  set +e
  [[ -z "$receipt_stage" ]] || rm -f -- "$receipt_stage"
  if (( install_complete == 0 )); then
    rm -f -- "$RECEIPT"
    systemctl stop r46h-input-bridge.service >/dev/null 2>&1 || true
    rm -f -- \
      "$BRIDGE" "$WAITER" "$RUNNER" "$TRIAL" "$REMOVE" "$UNIT" \
      "$CANDIDATE_CONFIG"
    systemctl daemon-reload >/dev/null 2>&1 || true
    if [[ -d "$STATE_DIR" && ! -L "$STATE_DIR" ]]; then
      remove_state_members "$STATE_DIR"
    elif [[ -n "$state_stage" && -d "$state_stage" && ! -L "$state_stage" ]]; then
      remove_state_members "$state_stage"
    fi
    if (( state_parent_created == 1 )); then
      rmdir -- "$STATE_PARENT" 2>/dev/null || true
    fi
  fi
  exit "$status"
}

validate_payload() {
  local payload_members expected_members

  [[ -d "$PAYLOAD_DIR" && ! -L "$PAYLOAD_DIR" ]] || die 'unsafe payload directory'
  [[ "$(stat -c '%u:%g:%a' "$PAYLOAD_DIR")" == 0:0:700 ]] || die 'unsafe payload directory identity'
  payload_members=$(find "$PAYLOAD_DIR" -mindepth 1 -maxdepth 2 -printf '%P\n' | LC_ALL=C sort)
  expected_members=$'PAYLOAD-INFO.json\nPAYLOAD.COMPLETE\nSHA256SUMS\nSTATE-SHA256SUMS\nfiles\nfiles/OPERATIONS.md\nfiles/r46h-game-ui-input-candidate\nfiles/r46h-input-bridge\nfiles/r46h-input-bridge-remove\nfiles/r46h-input-bridge-trial\nfiles/r46h-input-bridge-wait\nfiles/r46h-input-bridge.service\nfiles/retroarch.cfg\ninstall.sh'
  [[ "$payload_members" == "$expected_members" ]] || die 'unexpected payload member set'
  [[ -z "$(find "$PAYLOAD_DIR" -xdev -type l -print -quit)" ]] || die 'payload contains a symbolic link'
  [[ -z "$(find "$PAYLOAD_DIR" -xdev ! -type d ! -type f -print -quit)" ]] || die 'payload contains a special file'
  [[ -z "$(find "$PAYLOAD_DIR" -xdev -type f ! -links 1 -print -quit)" ]] || die 'payload contains a hard-linked file'
  cd "$PAYLOAD_DIR"
  sha256sum -c SHA256SUMS
  [[ "$(<PAYLOAD.COMPLETE)" == "sha256sums_sha256=$(sha256sum SHA256SUMS | awk '{print $1}')" ]] || die 'payload completion marker mismatch'
}

(( EUID == 0 )) || die 'root is required'
[[ $# == 0 || ( $# == 1 && ${1:-} == --check-payload ) ]] || die 'usage: install.sh [--check-payload]'
[[ "${BASH_SOURCE[0]}" == "$PAYLOAD_DIR/install.sh" ]] || die "stage payload at $PAYLOAD_DIR"
validate_payload
if [[ ${1:-} == --check-payload ]]; then
  printf 'PASS: exact R46H gaming input bridge payload structure and checksums validated.\n'
  exit 0
fi
[[ "$(findmnt -rn -T /run -o FSTYPE)" == tmpfs ]] || die '/run is not tmpfs'
[[ "$(uname -r)" == "$EXPECTED_RUNNING_RELEASE" ]] || die 'stage from exact persistent v0.10'
[[ "$(findmnt -rn -o PARTUUID /)" == "$EXPECTED_ROOT_PARTUUID" ]] || die 'unexpected root partition'
[[ "$(findmnt -rn -o FSTYPE /)" == ext4 ]] || die 'root is not ext4'
[[ ",$(findmnt -rn -o OPTIONS /)," == *,rw,* ]] || die 'root is not writable'
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem already reports errors'
[[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd has failed units'
[[ -f "$BASE_GAMING_RECEIPT" && ! -L "$BASE_GAMING_RECEIPT" ]] || die 'gaming receipt is missing'
[[ "$(sha256sum "$BASE_GAMING_RECEIPT" | awk '{print $1}')" == "$BASE_GAMING_RECEIPT_SHA256" ]] || die 'gaming receipt mismatch'
[[ -f "$ROM_WORKFLOW_RECEIPT" && ! -L "$ROM_WORKFLOW_RECEIPT" ]] || die 'ROM workflow receipt is missing'
[[ "$(sha256sum "$ROM_WORKFLOW_RECEIPT" | awk '{print $1}')" == "$ROM_WORKFLOW_RECEIPT_SHA256" ]] || die 'ROM workflow receipt mismatch'
[[ -f "$HISTORY_RECEIPT" && ! -L "$HISTORY_RECEIPT" ]] || die 'history receipt is missing'
[[ "$(stat -c '%u:%g:%a:%h' "$HISTORY_RECEIPT")" == 0:0:600:1 ]] || die 'unsafe history receipt'
[[ "$(sha256sum "$HISTORY_RECEIPT" | awk '{print $1}')" == "$HISTORY_RECEIPT_SHA256" ]] || die 'history receipt mismatch'
[[ -d "$RETROARCH_STATE" && ! -L "$RETROARCH_STATE" ]] || die 'RetroArch user state is missing'
[[ "$(stat -c '%u:%g:%a' "$RETROARCH_STATE")" == 1000:1000:700 ]] || die 'RetroArch user state identity mismatch'
[[ -f "$BASE_CONFIG" && ! -L "$BASE_CONFIG" ]] || die 'base RetroArch config is missing'
[[ "$(sha256sum "$BASE_CONFIG" | awk '{print $1}')" == "$BASE_CONFIG_SHA256" ]] || die 'base RetroArch config mismatch'
[[ -f "$BASE_RUNNER" && ! -L "$BASE_RUNNER" ]] || die 'base gaming runner is missing'
[[ "$(sha256sum "$BASE_RUNNER" | awk '{print $1}')" == "$BASE_RUNNER_SHA256" ]] || die 'base gaming runner mismatch'
[[ ! -e "$STATE_DIR" && ! -L "$STATE_DIR" ]] || die 'candidate state already exists'
[[ ! -e "$RECEIPT" && ! -L "$RECEIPT" ]] || die 'candidate receipt already exists'
[[ ! -e "$DIAGNOSTICS_DIR" && ! -L "$DIAGNOSTICS_DIR" ]] || \
  die 'stale bridge diagnostics directory exists'
for destination in "$BRIDGE" "$WAITER" "$RUNNER" "$TRIAL" "$REMOVE" "$UNIT" "$CANDIDATE_CONFIG"; do
  [[ ! -e "$destination" && ! -L "$destination" ]] || die "candidate destination already exists: $destination"
done
trap cleanup_install EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

if [[ -e "$STATE_PARENT" || -L "$STATE_PARENT" ]]; then
  [[ -d "$STATE_PARENT" && ! -L "$STATE_PARENT" ]] || die 'unsafe candidate state parent'
  [[ "$(stat -c '%u:%g:%a' "$STATE_PARENT")" == 0:0:700 ]] || die 'unsafe candidate state parent identity'
else
  state_parent_created=1
  install -d -o root -g root -m 0700 "$STATE_PARENT"
fi
state_stage=$STATE_PARENT/.stage-v0.5.$$
[[ ! -e "$state_stage" && ! -L "$state_stage" ]] || die 'candidate state stage already exists'
install -d -o root -g root -m 0700 "$state_stage"
install -o root -g root -m 0500 files/r46h-input-bridge "$state_stage/r46h-input-bridge"
install -o root -g root -m 0500 files/r46h-input-bridge-wait "$state_stage/r46h-input-bridge-wait"
install -o root -g root -m 0500 files/r46h-game-ui-input-candidate "$state_stage/r46h-game-ui-input-candidate"
install -o root -g root -m 0500 files/r46h-input-bridge-trial "$state_stage/r46h-input-bridge-trial"
install -o root -g root -m 0500 files/r46h-input-bridge-remove "$state_stage/r46h-input-bridge-remove"
install -o root -g root -m 0400 files/r46h-input-bridge.service "$state_stage/r46h-input-bridge.service"
install -o root -g root -m 0400 files/retroarch.cfg "$state_stage/retroarch.cfg"
install -o root -g root -m 0400 files/OPERATIONS.md "$state_stage/OPERATIONS.md"
install -o root -g root -m 0400 STATE-SHA256SUMS "$state_stage/SHA256SUMS"
(cd "$state_stage" && sha256sum -c SHA256SUMS)
mv -T --no-clobber -- "$state_stage" "$STATE_DIR"
state_stage=""

install -o root -g root -m 0755 "$STATE_DIR/r46h-input-bridge" "$BRIDGE"
install -o root -g root -m 0755 "$STATE_DIR/r46h-input-bridge-wait" "$WAITER"
install -o root -g root -m 0755 "$STATE_DIR/r46h-game-ui-input-candidate" "$RUNNER"
install -o root -g root -m 0700 "$STATE_DIR/r46h-input-bridge-trial" "$TRIAL"
install -o root -g root -m 0700 "$STATE_DIR/r46h-input-bridge-remove" "$REMOVE"
install -o root -g root -m 0644 "$STATE_DIR/r46h-input-bridge.service" "$UNIT"
install -o root -g root -m 0644 "$STATE_DIR/retroarch.cfg" "$CANDIDATE_CONFIG"

systemctl daemon-reload
[[ "$(systemctl is-enabled r46h-input-bridge.service || true)" == static ]] || die 'candidate unit is not static'
[[ "$(systemctl is-active r46h-input-bridge.service || true)" == inactive ]] || die 'candidate unit unexpectedly active'

receipt_stage=/var/lib/r46h/.gaming-input-bridge-v0.5-installed.$$
printf 'payload_id=%s\ninstall_release=%s\ntest_release=%s\nbase_config_sha256=%s\nstate_sha256sums_sha256=%s\n' \
  "$PAYLOAD_ID" "$EXPECTED_RUNNING_RELEASE" \
  6.12.99-r46h-mainline-v0.14-gaming-input-bridge "$BASE_CONFIG_SHA256" \
  "$(sha256sum "$STATE_DIR/SHA256SUMS" | awk '{print $1}')" > "$receipt_stage"
chmod 0600 "$receipt_stage"
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem reported an error during staging'
sync
mv -f "$receipt_stage" "$RECEIPT"
receipt_stage=""
sync
trap '' INT TERM HUP
install_complete=1
trap - EXIT INT TERM HUP

printf 'PASS: inactive R46H gaming input bridge candidate staged; active frontend and BOOT are unchanged.\n'
printf 'NEXT=boot-exact-v0.14-one-shot-then-run-%s\n' "$TRIAL"
