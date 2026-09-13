#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG
umask 077

readonly FEATURE_ID=r46h-remote-screen-es-de-v0.1
readonly EXPECTED_RELEASE=6.12.99-r46h-mainline-v0.15-gaming-product
readonly EXPECTED_ROOT_PARTUUID=c9f931c9-02
readonly EXPECTED_ROOT_UUID=d3130007-46a4-4d56-9001-000000000007
readonly PAYLOAD_DIR=/run/r46h-remote-screen-es-de-v0.1
readonly CAPTURE=/usr/local/libexec/r46h-drm-capture
readonly HELPER=/usr/local/bin/r46h-screenshot
readonly GATEWAY=/usr/local/bin/r46h-screenshot-ssh
readonly SUDOERS=/etc/sudoers.d/r46h-remote-screen
readonly BASE_ROLLBACK=/usr/local/sbin/r46h-remote-screen-rollback
readonly ROLLBACK=/usr/local/sbin/r46h-remote-screen-es-de-rollback
readonly BASE_RECEIPT=/var/lib/r46h/remote-screen-v0.1-installed
readonly ES_DE_RECEIPT=/var/lib/r46h/gaming-es-de-v0.1-installed
readonly RECEIPT=/var/lib/r46h/remote-screen-es-de-v0.1-installed
readonly STATE_PARENT=/var/lib/r46h-remote-screen-es-de
readonly STATE_DIR=$STATE_PARENT/v0.1
readonly ES_DE=/opt/r46h/es-de/bin/es-de
readonly ES_DE_RUNNER=/usr/local/sbin/r46h-es-de-ui
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count
readonly LOCK_DIR=/run/user/1000/r46h-screenshot.lock

readonly BASE_RECEIPT_SHA256=28aae35ba2f35255ae628949b76f1bb1d271be887cd51a81f12d73c0bd771957
readonly OLD_CAPTURE_SHA256=bb4c421029085cc182c369bb8b7c4a1431d0de2ddafb244d8c347dbbad127618
readonly OLD_HELPER_SHA256=728ad68187cc5647c695014c61ec86f48207ef05b46088463d427832ee3e40e4
readonly GATEWAY_SHA256=5932dd1eec9c510cf9f4a8c5f0425c7b4afa083c473d290e57c9775f15b6a638
readonly SUDOERS_SHA256=f366b8815b00f477521ef6d42e4dc2c94d3997e77940b66cacfc8548911e1ed6
readonly BASE_ROLLBACK_SHA256=3285d3b0c936ffb87f87de1a13fccc23be5fce8200f7891feaab34d7b4e7a686
readonly NEW_CAPTURE_SHA256=77f22181289edd701001fd6570a49afbfde277417e3769a693d1dd335cad324e
readonly NEW_HELPER_SHA256=ce5b38185a92c5043b7ffd4d0a4248d91bc2a189812ed61b2ee68379469d3d04
readonly ROLLBACK_SHA256=6b25c6315802e69064dd72692a55df74cbd01dba8a57161dbbbf71ea0d5d9f8c
readonly ES_DE_SHA256=9c6e50433b9bca5ac1c01030bc4d7b143f05c2cd27c52e6f5f765b0acf01be98
readonly ES_DE_RUNNER_SHA256=5b9edd8705d26ac2b58285baee9d2025354a0343936b5360313e664edd5bafa1

capture_stage=""
helper_stage=""
receipt_stage=""
rollback_stage=""
state_stage=""
transaction_active=0

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

cleanup() {
  local status=$? restore_ok=1
  trap - EXIT INT TERM HUP
  set +e
  rm -f -- "$capture_stage" "$helper_stage" "$receipt_stage" "$rollback_stage"
  if (( transaction_active == 1 )); then
    if [[ -d $STATE_DIR && ! -L $STATE_DIR ]]; then
      install -o root -g root -m 0755 "$STATE_DIR/previous-capture" "$CAPTURE" || restore_ok=0
      install -o root -g root -m 0755 "$STATE_DIR/previous-helper" "$HELPER" || restore_ok=0
    else
      restore_ok=0
    fi
    if (( restore_ok == 1 )); then
      rm -f -- "$RECEIPT" "$ROLLBACK" || status=1
      find "$STATE_DIR" -depth -delete || status=1
      rmdir -- "$STATE_PARENT" 2>/dev/null || status=1
    else
      printf 'ERROR: automatic restore incomplete; keep %s\n' "$STATE_DIR" >&2
      status=1
    fi
  fi
  if [[ -n $state_stage && -d $state_stage && ! -L $state_stage ]]; then
    find "$state_stage" -depth -delete || status=1
  fi
  (( transaction_active == 1 )) || rmdir -- "$STATE_PARENT" 2>/dev/null || true
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

[[ $# == 2 && $1 == --installer-sha256 ]] || die 'usage: install.sh --installer-sha256 HEX'
installer_sha256=$2
[[ $installer_sha256 =~ ^[0-9a-f]{64}$ ]] || die 'invalid installer SHA-256'
(( EUID == 0 )) || die 'root is required'
[[ ${BASH_SOURCE[0]} == "$PAYLOAD_DIR/install.sh" ]] || die 'run the staged installer'
[[ -d $PAYLOAD_DIR && ! -L $PAYLOAD_DIR ]] || die 'unsafe payload directory'
[[ $(stat -c '%u:%g:%a' "$PAYLOAD_DIR") == 0:0:700 ]] || die 'unsafe payload directory identity'
payload_members=$(find "$PAYLOAD_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
[[ $payload_members == $'README.md\nSHA256SUMS\ninstall.sh\nr46h-drm-capture\nr46h-screenshot\nrollback.sh' ]] || \
  die 'unexpected payload member set'
while IFS= read -r -d '' path; do
  [[ -f $path && ! -L $path && $(stat -c '%u:%g:%a:%h' "$path") == 0:0:600:1 ]] || \
    die "unsafe payload member: $path"
done < <(find "$PAYLOAD_DIR" -mindepth 1 -maxdepth 1 -print0)
hash_is "$PAYLOAD_DIR/install.sh" "$installer_sha256" || die 'installer hash mismatch'
require_file "$PAYLOAD_DIR/r46h-drm-capture" "$NEW_CAPTURE_SHA256" 0:0:600:1
require_file "$PAYLOAD_DIR/r46h-screenshot" "$NEW_HELPER_SHA256" 0:0:600:1
require_file "$PAYLOAD_DIR/rollback.sh" "$ROLLBACK_SHA256" 0:0:600:1

[[ $(uname -r) == "$EXPECTED_RELEASE" ]] || die 'unexpected running kernel'
[[ $(findmnt -rn -o PARTUUID /) == "$EXPECTED_ROOT_PARTUUID" ]] || die 'unexpected root partition'
[[ $(findmnt -rn -o UUID /) == "$EXPECTED_ROOT_UUID" ]] || die 'unexpected root filesystem'
[[ ,$(findmnt -rn -o OPTIONS /), == *,rw,* ]] || die 'p2 is not writable'
[[ ,$(findmnt -rn -o OPTIONS /roms), == *,ro,* ]] || die '/roms is not read-only'
[[ $(cat "$EXT4_ERRORS") == 0 ]] || die 'p2 already reports ext4 errors'
[[ -z $(systemctl --failed --no-legend --plain) ]] || die 'systemd has failed units'
[[ ! -e $LOCK_DIR && ! -L $LOCK_DIR ]] || die 'a screenshot operation is active'

require_file "$BASE_RECEIPT" "$BASE_RECEIPT_SHA256" 0:0:600:1
require_file "$CAPTURE" "$OLD_CAPTURE_SHA256" 0:0:755:1
require_file "$HELPER" "$OLD_HELPER_SHA256" 0:0:755:1
require_file "$GATEWAY" "$GATEWAY_SHA256" 0:0:755:1
require_file "$SUDOERS" "$SUDOERS_SHA256" 0:0:440:1
require_file "$BASE_ROLLBACK" "$BASE_ROLLBACK_SHA256" 0:0:700:1
require_file "$ES_DE" "$ES_DE_SHA256" 0:0:755:1
require_file "$ES_DE_RUNNER" "$ES_DE_RUNNER_SHA256" 0:0:755:1
[[ -f $ES_DE_RECEIPT && ! -L $ES_DE_RECEIPT && $(stat -c '%u:%g:%a:%h' "$ES_DE_RECEIPT") == 0:0:600:1 ]] || \
  die 'ES-DE receipt is unsafe'
grep -Fqx 'feature_id=r46h-gaming-es-de-v0.1' "$ES_DE_RECEIPT" || die 'ES-DE receipt mismatch'
grep -Fqx "es_de_sha256=$ES_DE_SHA256" "$ES_DE_RECEIPT" || die 'ES-DE binary receipt mismatch'
grep -Fqx "runner_sha256=$ES_DE_RUNNER_SHA256" "$ES_DE_RECEIPT" || die 'ES-DE runner receipt mismatch'
[[ $(systemctl is-active r46h-gaming-frontend.service || true) == active ]] || die 'frontend is not active'
mapfile -t es_pids < <(pgrep -u 1000 -x es-de || true)
(( ${#es_pids[@]} == 1 )) || die 'expected one ES-DE process'
frontend_pid=${es_pids[0]}
[[ $(readlink "/proc/$frontend_pid/exe") == "$ES_DE" ]] || die 'unexpected ES-DE process'
frontend_restarts=$(systemctl show -p NRestarts --value r46h-gaming-frontend.service)
[[ $frontend_restarts == 0 ]] || die 'frontend already restarted'

for path in "$RECEIPT" "$STATE_DIR" "$ROLLBACK"; do
  [[ ! -e $path && ! -L $path ]] || die "overlay path already exists: $path"
done
if [[ -e $STATE_PARENT || -L $STATE_PARENT ]]; then
  [[ -d $STATE_PARENT && ! -L $STATE_PARENT && $(stat -c '%u:%g:%a' "$STATE_PARENT") == 0:0:700 ]] || \
    die 'unsafe state parent'
  [[ -z $(find "$STATE_PARENT" -mindepth 1 -maxdepth 1 -print -quit) ]] || die 'state parent is not empty'
else
  install -d -o root -g root -m 0700 "$STATE_PARENT"
fi
state_stage=$STATE_PARENT/.v0.1-stage.$$
install -d -o root -g root -m 0700 "$state_stage"
install -o root -g root -m 0400 "$CAPTURE" "$state_stage/previous-capture"
install -o root -g root -m 0400 "$HELPER" "$state_stage/previous-helper"
install -o root -g root -m 0500 "$PAYLOAD_DIR/rollback.sh" "$state_stage/rollback.sh"
mv -T -- "$state_stage" "$STATE_DIR"
state_stage=""
transaction_active=1

capture_stage=/usr/local/libexec/.r46h-drm-capture.es-de.$$
helper_stage=/usr/local/bin/.r46h-screenshot.es-de.$$
rollback_stage=/usr/local/sbin/.r46h-remote-screen-es-de-rollback.$$
install -o root -g root -m 0755 "$PAYLOAD_DIR/r46h-drm-capture" "$capture_stage"
install -o root -g root -m 0755 "$PAYLOAD_DIR/r46h-screenshot" "$helper_stage"
install -o root -g root -m 0700 "$PAYLOAD_DIR/rollback.sh" "$rollback_stage"
mv -f -- "$capture_stage" "$CAPTURE"; capture_stage=""
mv -f -- "$helper_stage" "$HELPER"; helper_stage=""
mv -T -- "$rollback_stage" "$ROLLBACK"; rollback_stage=""

receipt_stage=/var/lib/r46h/.remote-screen-es-de-v0.1-installed.$$
printf 'feature_id=%s\nbase_receipt_sha256=%s\nold_capture_sha256=%s\nold_helper_sha256=%s\nnew_capture_sha256=%s\nnew_helper_sha256=%s\nrollback_sha256=%s\nes_de_sha256=%s\nes_de_runner_sha256=%s\ninstaller_sha256=%s\n' \
  "$FEATURE_ID" "$BASE_RECEIPT_SHA256" "$OLD_CAPTURE_SHA256" "$OLD_HELPER_SHA256" \
  "$NEW_CAPTURE_SHA256" "$NEW_HELPER_SHA256" "$ROLLBACK_SHA256" "$ES_DE_SHA256" \
  "$ES_DE_RUNNER_SHA256" "$installer_sha256" > "$receipt_stage"
chmod 0600 "$receipt_stage"
mv -T -- "$receipt_stage" "$RECEIPT"; receipt_stage=""

require_file "$CAPTURE" "$NEW_CAPTURE_SHA256" 0:0:755:1
require_file "$HELPER" "$NEW_HELPER_SHA256" 0:0:755:1
require_file "$ROLLBACK" "$ROLLBACK_SHA256" 0:0:700:1
[[ $(pgrep -u 1000 -x es-de) == "$frontend_pid" ]] || die 'frontend changed during update'
[[ $(systemctl show -p NRestarts --value r46h-gaming-frontend.service) == "$frontend_restarts" ]] || \
  die 'frontend restarted during update'
[[ $(cat "$EXT4_ERRORS") == 0 && -z $(systemctl --failed --no-legend --plain) ]] || \
  die 'target health changed during update'
sync

transaction_active=0
trap - EXIT INT TERM HUP
printf 'R46H_REMOTE_SCREEN_ES_DE_INSTALL result=pass frontend_untouched=es-de rollback=%s\n' "$ROLLBACK"
