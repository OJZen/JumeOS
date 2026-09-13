#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG
umask 077

readonly FEATURE_ID=r46h-gaming-remote-input-v0.1
readonly EXPECTED_RELEASE=6.12.99-r46h-mainline-v0.15-gaming-product
readonly EXPECTED_ROOT_PARTUUID=c9f931c9-02
readonly EXPECTED_ROOT_UUID=d3130007-46a4-4d56-9001-000000000007
readonly PAYLOAD_DIR=/run/r46h-gaming-remote-input-v0.1
readonly INPUT=/usr/local/libexec/r46h-remote-input
readonly GATEWAY=/usr/local/bin/r46h-screenshot-ssh
readonly SUDOERS=/etc/sudoers.d/r46h-remote-screen
readonly ROLLBACK=/usr/local/sbin/r46h-remote-input-rollback
readonly RECEIPT=/var/lib/r46h/remote-input-v0.1-installed
readonly STATE_PARENT=/var/lib/r46h-remote-input
readonly STATE_DIR=$STATE_PARENT/v0.1
readonly REMOTE_SCREEN_RECEIPT=/var/lib/r46h/remote-screen-v0.1-installed
readonly REMOTE_SCREEN_ES_DE_RECEIPT=/var/lib/r46h/remote-screen-es-de-v0.1-installed
readonly CAPTURE=/usr/local/libexec/r46h-drm-capture
readonly SCREENSHOT=/usr/local/bin/r46h-screenshot
readonly ES_DE=/opt/r46h/es-de/bin/es-de
readonly ES_DE_RECEIPT=/var/lib/r46h/gaming-es-de-v0.1-installed
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count
readonly SCREENSHOT_LOCK=/run/user/1000/r46h-screenshot.lock

readonly REMOTE_SCREEN_RECEIPT_SHA256=28aae35ba2f35255ae628949b76f1bb1d271be887cd51a81f12d73c0bd771957
readonly REMOTE_SCREEN_ES_DE_RECEIPT_SHA256=caa07dbac59572217b8faca95ba5ddc8b7ea50a93b92e726f64916f809b8aa39
readonly CAPTURE_SHA256=77f22181289edd701001fd6570a49afbfde277417e3769a693d1dd335cad324e
readonly SCREENSHOT_SHA256=ce5b38185a92c5043b7ffd4d0a4248d91bc2a189812ed61b2ee68379469d3d04
readonly ES_DE_SHA256=9c6e50433b9bca5ac1c01030bc4d7b143f05c2cd27c52e6f5f765b0acf01be98
readonly OLD_GATEWAY_SHA256=5932dd1eec9c510cf9f4a8c5f0425c7b4afa083c473d290e57c9775f15b6a638
readonly OLD_SUDOERS_SHA256=f366b8815b00f477521ef6d42e4dc2c94d3997e77940b66cacfc8548911e1ed6
readonly INPUT_SHA256=9907972995127792b75f0cf9922c3d750e8a06437b3d4d026f4a1db614f0232c
readonly NEW_GATEWAY_SHA256=1b1ec52cec6d6e670d49789738d1a6c38d7f1b35c50bb24ba86ff1cd6203f9da
readonly NEW_SUDOERS_SHA256=2486b57b1312bea2477c4de629c2b5e60641f9016a3d3fb9c5be70e38b15e1fe
readonly ROLLBACK_SHA256=b4d10bbdc6789e3f09832a410dce422ea47bb2280ea5b56bcc522615710b6d24

input_stage=""
gateway_stage=""
sudoers_stage=""
rollback_stage=""
receipt_stage=""
state_stage=""
transaction_active=0

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
    [[ $(readlink "/proc/${es_de_pids[0]}/exe") == "$ES_DE" ]] || return 1
    printf '%s\n' "${es_de_pids[0]}"
  fi
}

verify_installed() {
  require_file "$INPUT" "$INPUT_SHA256" 0:0:755:1
  require_file "$GATEWAY" "$NEW_GATEWAY_SHA256" 0:0:755:1
  require_file "$SUDOERS" "$NEW_SUDOERS_SHA256" 0:0:440:1
  require_file "$ROLLBACK" "$ROLLBACK_SHA256" 0:0:700:1
  [[ -f $RECEIPT && ! -L $RECEIPT && $(stat -c '%u:%g:%a:%h' "$RECEIPT") == 0:0:600:1 ]] || \
    die 'remote-input receipt is unsafe'
  for line in \
    "feature_id=$FEATURE_ID" \
    "remote_screen_receipt_sha256=$REMOTE_SCREEN_RECEIPT_SHA256" \
    "remote_screen_es_de_receipt_sha256=$REMOTE_SCREEN_ES_DE_RECEIPT_SHA256" \
    "input_sha256=$INPUT_SHA256" \
    "gateway_sha256=$NEW_GATEWAY_SHA256" \
    "sudoers_sha256=$NEW_SUDOERS_SHA256" \
    "rollback_sha256=$ROLLBACK_SHA256"; do
    grep -Fqx "$line" "$RECEIPT" || die "receipt mismatch: ${line%%=*}"
  done
  [[ -d $STATE_DIR && ! -L $STATE_DIR && $(stat -c '%u:%g:%a' "$STATE_DIR") == 0:0:700 ]] || \
    die 'rollback state is unsafe'
  state_members=$(find "$STATE_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
  [[ $state_members == $'previous-gateway\nprevious-sudoers\nrollback.sh' ]] || die 'unexpected rollback state members'
  require_file "$STATE_DIR/previous-gateway" "$OLD_GATEWAY_SHA256" 0:0:400:1
  require_file "$STATE_DIR/previous-sudoers" "$OLD_SUDOERS_SHA256" 0:0:400:1
  [[ -f $STATE_DIR/rollback.sh && ! -L $STATE_DIR/rollback.sh && \
     $(stat -c '%u:%g:%a:%h' "$STATE_DIR/rollback.sh") == 0:0:500:1 ]] || die 'saved rollback is unsafe'
  cmp -s "$STATE_DIR/rollback.sh" "$ROLLBACK" || die 'saved rollback changed'
  /usr/sbin/visudo -cf "$SUDOERS" >/dev/null || die 'installed sudo policy is invalid'
  [[ $($INPUT --version) == "$FEATURE_ID" ]] || die 'input version mismatch'
  "$INPUT" --self-test || die 'input self-test failed'
}

cleanup() {
  local status=$? restore_ok=1
  trap - EXIT INT TERM HUP
  set +e
  rm -f -- "$input_stage" "$gateway_stage" "$sudoers_stage" "$rollback_stage" "$receipt_stage"
  if (( transaction_active == 1 )); then
    if [[ -d $STATE_DIR && ! -L $STATE_DIR ]]; then
      install -o root -g root -m 0755 "$STATE_DIR/previous-gateway" "$GATEWAY" || restore_ok=0
      install -o root -g root -m 0440 "$STATE_DIR/previous-sudoers" "$SUDOERS" || restore_ok=0
    else
      restore_ok=0
    fi
    rm -f -- "$INPUT"
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
[[ -d $PAYLOAD_DIR && ! -L $PAYLOAD_DIR && $(stat -c '%u:%g:%a' "$PAYLOAD_DIR") == 0:0:700 ]] || \
  die 'unsafe payload directory identity'
payload_members=$(find "$PAYLOAD_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
[[ $payload_members == $'README.md\nSHA256SUMS\ninstall.sh\nr46h-remote-input\nr46h-remote-input.sudoers\nr46h-screenshot-ssh\nrollback.sh' ]] || \
  die 'unexpected payload member set'
while IFS= read -r -d '' path; do
  [[ -f $path && ! -L $path && $(stat -c '%u:%g:%a:%h' "$path") == 0:0:600:1 ]] || \
    die "unsafe payload member: $path"
done < <(find "$PAYLOAD_DIR" -mindepth 1 -maxdepth 1 -print0)
require_file "$PAYLOAD_DIR/install.sh" "$installer_sha256" 0:0:600:1
require_file "$PAYLOAD_DIR/r46h-remote-input" "$INPUT_SHA256" 0:0:600:1
require_file "$PAYLOAD_DIR/r46h-screenshot-ssh" "$NEW_GATEWAY_SHA256" 0:0:600:1
require_file "$PAYLOAD_DIR/r46h-remote-input.sudoers" "$NEW_SUDOERS_SHA256" 0:0:600:1
require_file "$PAYLOAD_DIR/rollback.sh" "$ROLLBACK_SHA256" 0:0:600:1

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
require_file "$CAPTURE" "$CAPTURE_SHA256" 0:0:755:1
require_file "$SCREENSHOT" "$SCREENSHOT_SHA256" 0:0:755:1
require_file "$ES_DE" "$ES_DE_SHA256" 0:0:755:1
[[ -f $ES_DE_RECEIPT && ! -L $ES_DE_RECEIPT ]] || die 'ES-DE receipt is unsafe'
grep -Fqx 'feature_id=r46h-gaming-es-de-v0.1' "$ES_DE_RECEIPT" || die 'ES-DE receipt mismatch'

if [[ -e $RECEIPT || -L $RECEIPT ]]; then
  verify_installed
  printf 'R46H_REMOTE_INPUT_INSTALL result=pass status=already-installed\n'
  exit 0
fi
require_file "$GATEWAY" "$OLD_GATEWAY_SHA256" 0:0:755:1
require_file "$SUDOERS" "$OLD_SUDOERS_SHA256" 0:0:440:1
for path in "$INPUT" "$ROLLBACK" "$STATE_DIR"; do
  [[ ! -e $path && ! -L $path ]] || die "feature path already exists: $path"
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
install -o root -g root -m 0400 "$GATEWAY" "$state_stage/previous-gateway"
install -o root -g root -m 0400 "$SUDOERS" "$state_stage/previous-sudoers"
install -o root -g root -m 0500 "$PAYLOAD_DIR/rollback.sh" "$state_stage/rollback.sh"
mv -T -- "$state_stage" "$STATE_DIR"
state_stage=""
transaction_active=1

input_stage=/usr/local/libexec/.r46h-remote-input.$$
gateway_stage=/usr/local/bin/.r46h-screenshot-ssh.remote-input.$$
sudoers_stage=/etc/sudoers.d/.r46h-remote-screen.remote-input.$$
rollback_stage=/usr/local/sbin/.r46h-remote-input-rollback.$$
install -o root -g root -m 0755 "$PAYLOAD_DIR/r46h-remote-input" "$input_stage"
install -o root -g root -m 0755 "$PAYLOAD_DIR/r46h-screenshot-ssh" "$gateway_stage"
install -o root -g root -m 0440 "$PAYLOAD_DIR/r46h-remote-input.sudoers" "$sudoers_stage"
install -o root -g root -m 0700 "$PAYLOAD_DIR/rollback.sh" "$rollback_stage"
/usr/sbin/visudo -cf "$sudoers_stage" >/dev/null || die 'staged sudo policy is invalid'
mv -T -- "$input_stage" "$INPUT"; input_stage=""
mv -f -- "$sudoers_stage" "$SUDOERS"; sudoers_stage=""
mv -f -- "$gateway_stage" "$GATEWAY"; gateway_stage=""
mv -T -- "$rollback_stage" "$ROLLBACK"; rollback_stage=""

receipt_stage=/var/lib/r46h/.remote-input-v0.1-installed.$$
printf 'feature_id=%s\nremote_screen_receipt_sha256=%s\nremote_screen_es_de_receipt_sha256=%s\ninput_sha256=%s\ngateway_sha256=%s\nsudoers_sha256=%s\nrollback_sha256=%s\ninstaller_sha256=%s\n' \
  "$FEATURE_ID" "$REMOTE_SCREEN_RECEIPT_SHA256" "$REMOTE_SCREEN_ES_DE_RECEIPT_SHA256" \
  "$INPUT_SHA256" "$NEW_GATEWAY_SHA256" "$NEW_SUDOERS_SHA256" "$ROLLBACK_SHA256" \
  "$installer_sha256" > "$receipt_stage"
chmod 0600 "$receipt_stage"
mv -T -- "$receipt_stage" "$RECEIPT"; receipt_stage=""

verify_installed
[[ $(active_frontend_pid) == "$frontend_pid" ]] || die 'frontend changed during install'
[[ $(systemctl show -p NRestarts --value r46h-gaming-frontend.service) == "$frontend_restarts" ]] || \
  die 'frontend restarted during install'
[[ $(cat "$EXT4_ERRORS") == 0 && -z $(systemctl --failed --no-legend --plain) ]] || \
  die 'target health changed during install'
sync

transaction_active=0
trap - EXIT INT TERM HUP
printf 'R46H_REMOTE_INPUT_INSTALL result=pass frontend_untouched=yes actions=16\n'
