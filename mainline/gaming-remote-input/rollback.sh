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
readonly INPUT=/usr/local/libexec/r46h-remote-input
readonly GATEWAY=/usr/local/bin/r46h-screenshot-ssh
readonly SUDOERS=/etc/sudoers.d/r46h-remote-screen
readonly ROLLBACK=/usr/local/sbin/r46h-remote-input-rollback
readonly RECEIPT=/var/lib/r46h/remote-input-v0.1-installed
readonly STATE_PARENT=/var/lib/r46h-remote-input
readonly STATE_DIR=$STATE_PARENT/v0.1
readonly REMOTE_SCREEN_RECEIPT=/var/lib/r46h/remote-screen-v0.1-installed
readonly REMOTE_SCREEN_ES_DE_RECEIPT=/var/lib/r46h/remote-screen-es-de-v0.1-installed
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count
readonly SCREENSHOT_LOCK=/run/user/1000/r46h-screenshot.lock

readonly REMOTE_SCREEN_RECEIPT_SHA256=28aae35ba2f35255ae628949b76f1bb1d271be887cd51a81f12d73c0bd771957
readonly REMOTE_SCREEN_ES_DE_RECEIPT_SHA256=caa07dbac59572217b8faca95ba5ddc8b7ea50a93b92e726f64916f809b8aa39
readonly OLD_GATEWAY_SHA256=5932dd1eec9c510cf9f4a8c5f0425c7b4afa083c473d290e57c9775f15b6a638
readonly OLD_SUDOERS_SHA256=f366b8815b00f477521ef6d42e4dc2c94d3997e77940b66cacfc8548911e1ed6
readonly INPUT_SHA256=9907972995127792b75f0cf9922c3d750e8a06437b3d4d026f4a1db614f0232c
readonly NEW_GATEWAY_SHA256=1b1ec52cec6d6e670d49789738d1a6c38d7f1b35c50bb24ba86ff1cd6203f9da
readonly NEW_SUDOERS_SHA256=2486b57b1312bea2477c4de629c2b5e60641f9016a3d3fb9c5be70e38b15e1fe

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

require_file() {
  local path=$1 expected=$2 identity=$3
  [[ -f $path && ! -L $path ]] || die "file is missing or unsafe: $path"
  [[ $(sha256sum "$path" | awk '{print $1}') == "$expected" ]] || die "file identity mismatch: $path"
  [[ $(stat -c '%u:%g:%a:%h' "$path") == "$identity" ]] || die "unsafe file metadata: $path"
}

active_frontend_pid() {
  local -a es_de_pids retroarch_pids
  mapfile -t retroarch_pids < <(pgrep -u 1000 -x retroarch || true)
  mapfile -t es_de_pids < <(pgrep -u 1000 -x es-de || true)
  (( ${#retroarch_pids[@]} + ${#es_de_pids[@]} == 1 )) || return 1
  if (( ${#retroarch_pids[@]} == 1 )); then
    [[ $(readlink "/proc/${retroarch_pids[0]}/exe") == /usr/bin/retroarch ]] || return 1
    printf '%s\n' "${retroarch_pids[0]}"
  else
    [[ $(readlink "/proc/${es_de_pids[0]}/exe") == /opt/r46h/es-de/bin/es-de ]] || return 1
    printf '%s\n' "${es_de_pids[0]}"
  fi
}

[[ $# == 0 ]] || die 'this rollback accepts no arguments'
(( EUID == 0 )) || die 'root is required'
[[ ${BASH_SOURCE[0]} == "$ROLLBACK" ]] || die 'run the installed rollback helper'
[[ $(uname -r) == "$EXPECTED_RELEASE" ]] || die 'unexpected running kernel'
[[ $(findmnt -rn -o PARTUUID /) == "$EXPECTED_ROOT_PARTUUID" ]] || die 'unexpected root partition'
[[ $(findmnt -rn -o UUID /) == "$EXPECTED_ROOT_UUID" ]] || die 'unexpected root filesystem'
[[ ,$(findmnt -rn -o OPTIONS /), == *,rw,* ]] || die 'p2 is not writable'
[[ ,$(findmnt -rn -o OPTIONS /roms), == *,ro,* ]] || die '/roms is not read-only'
[[ $(cat "$EXT4_ERRORS") == 0 && -z $(systemctl --failed --no-legend --plain) ]] || die 'target is unhealthy'
[[ ! -e $SCREENSHOT_LOCK && ! -L $SCREENSHOT_LOCK ]] || die 'a screenshot operation is active'
[[ -z $(pgrep -f '^/usr/local/libexec/r46h-remote-input (up|down|left|right|a|b|x|y|select|start|l1|r1|l2|r2|l3|r3)$' || true) ]] || \
  die 'a remote input operation is active'
[[ $(systemctl is-active r46h-gaming-frontend.service || true) == active ]] || die 'frontend is not active'
frontend_pid=$(active_frontend_pid) || die 'expected one supported frontend process'
frontend_restarts=$(systemctl show -p NRestarts --value r46h-gaming-frontend.service)

require_file "$REMOTE_SCREEN_RECEIPT" "$REMOTE_SCREEN_RECEIPT_SHA256" 0:0:600:1
require_file "$REMOTE_SCREEN_ES_DE_RECEIPT" "$REMOTE_SCREEN_ES_DE_RECEIPT_SHA256" 0:0:600:1
require_file "$INPUT" "$INPUT_SHA256" 0:0:755:1
require_file "$GATEWAY" "$NEW_GATEWAY_SHA256" 0:0:755:1
require_file "$SUDOERS" "$NEW_SUDOERS_SHA256" 0:0:440:1
require_file "$ROLLBACK" "$(sha256sum "$ROLLBACK" | awk '{print $1}')" 0:0:700:1
[[ -f $RECEIPT && ! -L $RECEIPT && $(stat -c '%u:%g:%a:%h' "$RECEIPT") == 0:0:600:1 ]] || \
  die 'remote-input receipt is unsafe'
grep -Fqx 'feature_id=r46h-gaming-remote-input-v0.1' "$RECEIPT" || die 'receipt identity mismatch'
grep -Fqx "input_sha256=$INPUT_SHA256" "$RECEIPT" || die 'input receipt mismatch'
grep -Fqx "gateway_sha256=$NEW_GATEWAY_SHA256" "$RECEIPT" || die 'gateway receipt mismatch'
grep -Fqx "sudoers_sha256=$NEW_SUDOERS_SHA256" "$RECEIPT" || die 'sudoers receipt mismatch'
grep -Fqx "rollback_sha256=$(sha256sum "$ROLLBACK" | awk '{print $1}')" "$RECEIPT" || die 'rollback receipt mismatch'

[[ -d $STATE_DIR && ! -L $STATE_DIR && $(stat -c '%u:%g:%a' "$STATE_DIR") == 0:0:700 ]] || \
  die 'rollback state is unsafe'
state_members=$(find "$STATE_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
[[ $state_members == $'previous-gateway\nprevious-sudoers\nrollback.sh' ]] || die 'unexpected rollback state members'
require_file "$STATE_DIR/previous-gateway" "$OLD_GATEWAY_SHA256" 0:0:400:1
require_file "$STATE_DIR/previous-sudoers" "$OLD_SUDOERS_SHA256" 0:0:400:1
[[ -f $STATE_DIR/rollback.sh && ! -L $STATE_DIR/rollback.sh && \
   $(stat -c '%u:%g:%a:%h' "$STATE_DIR/rollback.sh") == 0:0:500:1 ]] || die 'rollback state helper is unsafe'
cmp -s "$STATE_DIR/rollback.sh" "$ROLLBACK" || die 'rollback state helper changed'

gateway_stage=/usr/local/bin/.r46h-screenshot-ssh.remote-input-restore.$$
sudoers_stage=/etc/sudoers.d/.r46h-remote-screen.remote-input-restore.$$
trap 'rm -f -- "$gateway_stage" "$sudoers_stage"' EXIT
install -o root -g root -m 0755 "$STATE_DIR/previous-gateway" "$gateway_stage"
install -o root -g root -m 0440 "$STATE_DIR/previous-sudoers" "$sudoers_stage"
/usr/sbin/visudo -cf "$sudoers_stage" >/dev/null || die 'saved sudo policy is invalid'
mv -f -- "$gateway_stage" "$GATEWAY"; gateway_stage=""
mv -f -- "$sudoers_stage" "$SUDOERS"; sudoers_stage=""
require_file "$GATEWAY" "$OLD_GATEWAY_SHA256" 0:0:755:1
require_file "$SUDOERS" "$OLD_SUDOERS_SHA256" 0:0:440:1
rm -f -- "$INPUT" "$RECEIPT"
find "$STATE_DIR" -depth -delete
rmdir -- "$STATE_PARENT"
rm -f -- "$ROLLBACK"
if [[ -e /run/r46h-remote-input.lock || -L /run/r46h-remote-input.lock ]]; then
  [[ -f /run/r46h-remote-input.lock && ! -L /run/r46h-remote-input.lock && \
     $(stat -c '%u:%g:%a:%h' /run/r46h-remote-input.lock) == 0:0:600:1 ]] || \
    die 'remote-input lock is unsafe'
  rm -f -- /run/r46h-remote-input.lock
fi
[[ $(active_frontend_pid) == "$frontend_pid" ]] || die 'frontend changed during rollback'
[[ $(systemctl show -p NRestarts --value r46h-gaming-frontend.service) == "$frontend_restarts" ]] || \
  die 'frontend restarted during rollback'
[[ $(cat "$EXT4_ERRORS") == 0 && -z $(systemctl --failed --no-legend --plain) ]] || \
  die 'target health changed during rollback'
sync
trap - EXIT
printf 'R46H_REMOTE_INPUT_ROLLBACK result=pass frontend_untouched=yes remote_screen=restored\n'
