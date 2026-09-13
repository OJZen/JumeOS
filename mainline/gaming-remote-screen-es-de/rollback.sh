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
readonly CAPTURE=/usr/local/libexec/r46h-drm-capture
readonly HELPER=/usr/local/bin/r46h-screenshot
readonly ROLLBACK=/usr/local/sbin/r46h-remote-screen-es-de-rollback
readonly BASE_RECEIPT=/var/lib/r46h/remote-screen-v0.1-installed
readonly RECEIPT=/var/lib/r46h/remote-screen-es-de-v0.1-installed
readonly STATE_PARENT=/var/lib/r46h-remote-screen-es-de
readonly STATE_DIR=$STATE_PARENT/v0.1
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count
readonly LOCK_DIR=/run/user/1000/r46h-screenshot.lock
readonly BASE_RECEIPT_SHA256=28aae35ba2f35255ae628949b76f1bb1d271be887cd51a81f12d73c0bd771957
readonly OLD_CAPTURE_SHA256=bb4c421029085cc182c369bb8b7c4a1431d0de2ddafb244d8c347dbbad127618
readonly OLD_HELPER_SHA256=728ad68187cc5647c695014c61ec86f48207ef05b46088463d427832ee3e40e4
readonly NEW_CAPTURE_SHA256=77f22181289edd701001fd6570a49afbfde277417e3769a693d1dd335cad324e
readonly NEW_HELPER_SHA256=ce5b38185a92c5043b7ffd4d0a4248d91bc2a189812ed61b2ee68379469d3d04

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

hash_is() {
  local path=$1 expected=$2
  [[ -f $path && ! -L $path && $(sha256sum "$path" | awk '{print $1}') == "$expected" ]]
}

require_file() {
  local path=$1 expected=$2 identity=$3
  hash_is "$path" "$expected" || die "file identity mismatch: $path"
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
[[ ! -e $LOCK_DIR && ! -L $LOCK_DIR ]] || die 'a screenshot operation is active'
[[ $(systemctl is-active r46h-gaming-frontend.service || true) == active ]] || die 'frontend is not active'
frontend_pid=$(active_frontend_pid) || die 'expected one supported frontend process'
frontend_restarts=$(systemctl show -p NRestarts --value r46h-gaming-frontend.service)

require_file "$BASE_RECEIPT" "$BASE_RECEIPT_SHA256" 0:0:600:1
require_file "$CAPTURE" "$NEW_CAPTURE_SHA256" 0:0:755:1
require_file "$HELPER" "$NEW_HELPER_SHA256" 0:0:755:1
[[ -f $RECEIPT && ! -L $RECEIPT && $(stat -c '%u:%g:%a:%h' "$RECEIPT") == 0:0:600:1 ]] || \
  die 'overlay receipt is unsafe'
grep -Fqx 'feature_id=r46h-remote-screen-es-de-v0.1' "$RECEIPT" || die 'overlay receipt mismatch'
grep -Fqx "base_receipt_sha256=$BASE_RECEIPT_SHA256" "$RECEIPT" || die 'base receipt mismatch'
grep -Fqx "new_capture_sha256=$NEW_CAPTURE_SHA256" "$RECEIPT" || die 'capture receipt mismatch'
grep -Fqx "new_helper_sha256=$NEW_HELPER_SHA256" "$RECEIPT" || die 'helper receipt mismatch'
rollback_sha256=$(sha256sum "$ROLLBACK" | awk '{print $1}')
grep -Fqx "rollback_sha256=$rollback_sha256" "$RECEIPT" || die 'rollback receipt mismatch'

[[ -d $STATE_DIR && ! -L $STATE_DIR && $(stat -c '%u:%g:%a' "$STATE_DIR") == 0:0:700 ]] || \
  die 'rollback state is unsafe'
state_members=$(find "$STATE_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
[[ $state_members == $'previous-capture\nprevious-helper\nrollback.sh' ]] || die 'unexpected rollback state members'
require_file "$STATE_DIR/previous-capture" "$OLD_CAPTURE_SHA256" 0:0:400:1
require_file "$STATE_DIR/previous-helper" "$OLD_HELPER_SHA256" 0:0:400:1
[[ -f $STATE_DIR/rollback.sh && ! -L $STATE_DIR/rollback.sh && \
   $(stat -c '%u:%g:%a:%h' "$STATE_DIR/rollback.sh") == 0:0:500:1 ]] || die 'rollback state helper is unsafe'
cmp -s "$STATE_DIR/rollback.sh" "$ROLLBACK" || die 'rollback state helper changed'

capture_stage=/usr/local/libexec/.r46h-drm-capture.restore.$$
helper_stage=/usr/local/bin/.r46h-screenshot.restore.$$
trap 'rm -f -- "$capture_stage" "$helper_stage"' EXIT
install -o root -g root -m 0755 "$STATE_DIR/previous-capture" "$capture_stage"
install -o root -g root -m 0755 "$STATE_DIR/previous-helper" "$helper_stage"
mv -f -- "$capture_stage" "$CAPTURE"; capture_stage=""
mv -f -- "$helper_stage" "$HELPER"; helper_stage=""
require_file "$CAPTURE" "$OLD_CAPTURE_SHA256" 0:0:755:1
require_file "$HELPER" "$OLD_HELPER_SHA256" 0:0:755:1
rm -f -- "$RECEIPT"
find "$STATE_DIR" -depth -delete
rmdir -- "$STATE_PARENT"
rm -f -- "$ROLLBACK"
[[ $(active_frontend_pid) == "$frontend_pid" ]] || die 'frontend changed during rollback'
[[ $(systemctl show -p NRestarts --value r46h-gaming-frontend.service) == "$frontend_restarts" ]] || \
  die 'frontend restarted during rollback'
[[ $(cat "$EXT4_ERRORS") == 0 && -z $(systemctl --failed --no-legend --plain) ]] || \
  die 'target health changed during rollback'
sync
trap - EXIT
printf 'R46H_REMOTE_SCREEN_ES_DE_ROLLBACK result=pass frontend_untouched=yes base=v0.1\n'
