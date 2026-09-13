#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG

readonly EXPECTED_RELEASE=6.12.99-r46h-mainline-v0.14-gaming-input-bridge
readonly EXPECTED_ROOT_PARTUUID=c9f931c9-02
readonly EXPECTED_NAME='R46H Combined Gamepad'
readonly STATE_DIR=/var/lib/r46h-gaming-input-bridge/v0.5
readonly RECEIPT=/var/lib/r46h/gaming-input-bridge-v0.5-installed
readonly SERVICE=r46h-input-bridge.service
readonly RUNNER=/usr/local/sbin/r46h-game-ui-input-candidate
readonly WAITER=/usr/local/libexec/r46h-input-bridge-wait
readonly CANDIDATE_CONFIG=/etc/r46h/retroarch-input-candidate.cfg
readonly DIAGNOSTICS_DIR=/run/r46h-input-bridge
readonly DIAGNOSTICS=$DIAGNOSTICS_DIR/diagnostics
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count
readonly INPUT_WINDOW_SECONDS=60

readonly REQUIRED_KEYS=(
  BTN_DPAD_UP BTN_DPAD_DOWN BTN_DPAD_LEFT BTN_DPAD_RIGHT
  BTN_EAST BTN_SOUTH BTN_WEST BTN_NORTH
  BTN_TL BTN_TR BTN_TL2 BTN_TR2 BTN_SELECT BTN_START
  BTN_TRIGGER_HAPPY3 BTN_TRIGGER_HAPPY4
)
readonly REQUIRED_CAPABILITY_KEYS=("${REQUIRED_KEYS[@]}" BTN_TRIGGER_HAPPY5)
readonly REQUIRED_AXES=(ABS_X ABS_Y ABS_RX ABS_RY)

AXIS_AWK='
/^[[:space:]]*Event code [0-9]+ \(/ {
  wanted_header = index($0, "(" wanted ")") > 0
  next
}
wanted_header && /^[[:space:]]*Min[[:space:]]/ {
  advertised_min = $NF
  have_min = 1
  next
}
wanted_header && /^[[:space:]]*Value[[:space:]]/ {
  initial = $NF
  have_initial = 1
  next
}
wanted_header && /^[[:space:]]*Max[[:space:]]/ {
  advertised_max = $NF
  have_max = 1
  next
}
index($0, "Event: time") && index($0, "(" wanted ")") {
  value = $NF
  if (value !~ /^-?[0-9]+$/) next
  if (count == 0 || value < observed_min) observed_min = value
  if (count == 0 || value > observed_max) observed_max = value
  last = value
  count++
}
END {
  if (!have_min || !have_max || !have_initial || count == 0) exit 1
  printf "%d %d %d %d %d %d %d\n", \
    advertised_min, advertised_max, initial, observed_min, observed_max, last, count
}'
readonly AXIS_AWK

KEY_AWK='
index($0, "Event: time") && index($0, "(" wanted ")") {
  value = $NF
  if (value !~ /^-?[0-9]+$/) next
  if (value == 1) {
    presses++
  } else if (value == 0) {
    releases++
  } else {
    other++
  }
  last = value
  have_last = 1
}
END {
  if (!have_last) last = -1
  printf "%d %d %d %d\n", presses, releases, other, last
}'
readonly KEY_AWK

SYN_AWK='
index($0, "Event: time") && index($0, "SYN_DROPPED") { count++ }
END { print count + 0 }
'
readonly SYN_AWK

BRIDGE_HEADER_AWK='
$1 == "R46H_INPUT_BRIDGE_DIAGNOSTIC" && $2 == "kind=header" {
  matches++
  for (field_index = 3; field_index <= NF; field_index++) {
    split($field_index, field, "=")
    value[field[1]] = field[2]
  }
}
END {
  if (matches != 1) exit 1
  if (value["version"] == "" ||
      value["bridge_status"] !~ /^(pass|fail)$/ ||
      value["uinput_write_failures"] !~ /^[0-9]+$/ ||
      value["failed_type"] !~ /^-?[0-9]+$/ ||
      value["failed_code"] !~ /^-?[0-9]+$/ ||
      value["failed_value"] !~ /^-?[0-9]+$/) exit 1
  printf "%s %s %s %s %s %s\n", value["version"],
    value["bridge_status"], value["uinput_write_failures"],
    value["failed_type"], value["failed_code"], value["failed_value"]
}'
readonly BRIDGE_HEADER_AWK

BRIDGE_KEY_AWK='
$1 == "R46H_INPUT_BRIDGE_DIAGNOSTIC" && $2 == "kind=key" && $3 == "code=" wanted {
  matches++
  for (field_index = 4; field_index <= NF; field_index++) {
    split($field_index, field, "=")
    value[field[1]] = field[2]
  }
}
END {
  if (matches != 1) exit 1
  required[1] = "source_presses"
  required[2] = "source_releases"
  required[3] = "source_other"
  required[4] = "source_last"
  required[5] = "emitted_presses"
  required[6] = "emitted_releases"
  required[7] = "emitted_other"
  required[8] = "emitted_last"
  for (field_index = 1; field_index <= 8; field_index++) {
    if (value[required[field_index]] !~ /^-?[0-9]+$/) exit 1
  }
  printf "%s %s %s %s %s %s %s %s\n", \
    value["source_presses"], value["source_releases"], \
    value["source_other"], value["source_last"], \
    value["emitted_presses"], value["emitted_releases"], \
    value["emitted_other"], value["emitted_last"]
}'
readonly BRIDGE_KEY_AWK

BRIDGE_AXIS_AWK='
$1 == "R46H_INPUT_BRIDGE_DIAGNOSTIC" && $2 == "kind=axis" && $3 == "code=" wanted {
  matches++
  for (field_index = 4; field_index <= NF; field_index++) {
    split($field_index, field, "=")
    value[field[1]] = field[2]
  }
}
END {
  if (matches != 1) exit 1
  required[1] = "source_samples"
  required[2] = "source_min"
  required[3] = "source_max"
  required[4] = "source_last"
  required[5] = "emitted_samples"
  required[6] = "emitted_last"
  for (field_index = 1; field_index <= 6; field_index++) {
    if (value[required[field_index]] !~ /^-?[0-9]+$/) exit 1
  }
  printf "%s %s %s %s %s %s\n", value["source_samples"], \
    value["source_min"], value["source_max"], value["source_last"], \
    value["emitted_samples"], value["emitted_last"]
}'
readonly BRIDGE_AXIS_AWK

BRIDGE_SYN_AWK='
$1 == "R46H_INPUT_BRIDGE_DIAGNOSTIC" && $2 == "kind=syn" {
  matches++
  for (field_index = 3; field_index <= NF; field_index++) {
    split($field_index, field, "=")
    value[field[1]] = field[2]
  }
}
END {
  if (matches != 1 || value["source_reports"] !~ /^[0-9]+$/ ||
      value["emitted_reports"] !~ /^[0-9]+$/) exit 1
  printf "%s %s\n", value["source_reports"], value["emitted_reports"]
}'
readonly BRIDGE_SYN_AWK

runtime_dir=""
runtime_id=""
event_log=""
capture_pid=""
runner_pid=""

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

combined_device_count() {
  local count=0 name_path

  for name_path in /sys/class/input/event*/device/name; do
    [[ -f "$name_path" ]] || continue
    [[ "$(<"$name_path")" == "$EXPECTED_NAME" ]] || continue
    count=$((count + 1))
  done
  printf '%d\n' "$count"
}

safe_remove_runtime() {
  [[ -n "$runtime_dir" && "$runtime_dir" == /run/r46h-input-bridge-trial.* &&
     -d "$runtime_dir" && ! -L "$runtime_dir" ]] || return 1
  [[ "$(stat -c '%u:%g:%a:%d:%i' "$runtime_dir")" == "0:0:700:$runtime_id" ]] || return 1
  [[ -z "$event_log" || "$event_log" == "$runtime_dir/events.txt" ]] || return 1
  [[ -z "$event_log" ]] || rm -f -- "$event_log"
  rmdir -- "$runtime_dir"
}

safe_remove_diagnostics() {
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

report_bridge_runtime_failure() {
  local bridge_version bridge_status write_failures failed_type failed_code failed_value

  [[ -f "$DIAGNOSTICS" && ! -L "$DIAGNOSTICS" ]] || return 0
  [[ "$(stat -c '%u:%g:%a:%h' "$DIAGNOSTICS")" == 0:0:600:1 ]] || return 0
  if ! read -r bridge_version bridge_status write_failures failed_type failed_code failed_value \
      < <(awk "$BRIDGE_HEADER_AWK" "$DIAGNOSTICS"); then
    return 0
  fi
  if [[ "$bridge_status" == fail || "$write_failures" != 0 ]]; then
    printf 'R46H_INPUT_BRIDGE_RUNTIME result=fail localization=%s version=%s uinput_write_failures=%s failed_type=%s failed_code=%s failed_value=%s\n' \
      "$([[ "$write_failures" == 0 ]] && printf bridge-runtime-failed || printf bridge-write-missing)" \
      "$bridge_version" "$write_failures" "$failed_type" "$failed_code" "$failed_value"
  fi
}

cleanup() {
  local status=$? active_state="" attempt

  trap - EXIT INT TERM HUP
  set +e
  trap '' INT TERM HUP
  if [[ "$capture_pid" =~ ^[1-9][0-9]*$ ]]; then
    kill -TERM -- "$capture_pid" 2>/dev/null || true
    wait "$capture_pid" 2>/dev/null || true
    capture_pid=""
  fi
  if [[ "$runner_pid" =~ ^[1-9][0-9]*$ ]]; then
    kill -TERM -- "$runner_pid" 2>/dev/null || true
    wait "$runner_pid" 2>/dev/null || true
    runner_pid=""
  fi
  systemctl stop "$SERVICE" >/dev/null 2>&1 || true
  active_state=$(systemctl is-active "$SERVICE" 2>/dev/null || true)
  [[ "$active_state" == inactive ]] || status=1
  pgrep -f '^/usr/local/libexec/r46h-input-bridge --diagnostics$' >/dev/null && status=1
  pgrep -x retroarch >/dev/null && status=1
  for ((attempt=0; attempt<30; attempt++)); do
    [[ "$(combined_device_count)" == 0 ]] && break
    /usr/bin/sleep 0.1
  done
  [[ "$(combined_device_count)" == 0 ]] || status=1
  report_bridge_runtime_failure
  safe_remove_diagnostics || status=1
  if [[ -n "$runtime_dir" ]]; then
    safe_remove_runtime || status=1
  fi
  [[ "$(cat "$EXT4_ERRORS")" == 0 ]] || status=1
  [[ -z "$(systemctl --failed --no-legend --plain)" ]] || status=1
  printf 'R46H_INPUT_BRIDGE_TRIAL result=%s status=%d cleanup=%s operator_screen_observation=required\n' \
    "$([[ $status == 0 ]] && printf machine-pass || printf fail)" "$status" \
    "$([[ $status == 0 ]] && printf pass || printf check-required)"
  exit "$status"
}

[[ $# == 0 ]] || die 'this trial accepts no arguments'
(( EUID == 0 )) || die 'root is required'
[[ -t 0 && -t 1 && -t 2 ]] || die 'an attended TTY is required'
[[ "$(uname -r)" == "$EXPECTED_RELEASE" ]] || die 'boot the exact v0.14 one-shot'
[[ "$(findmnt -rn -o PARTUUID /)" == "$EXPECTED_ROOT_PARTUUID" ]] || die 'unexpected root partition'
[[ "$(findmnt -rn -o FSTYPE /)" == ext4 ]] || die 'root is not ext4'
[[ ",$(findmnt -rn -o OPTIONS /)," == *,rw,* ]] || die 'root is not writable'
[[ "$(findmnt -rn -T /run -o FSTYPE)" == tmpfs ]] || die '/run is not tmpfs'
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem already reports errors'
[[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd has failed units'
[[ -d "/lib/modules/$EXPECTED_RELEASE" ]] || die 'matching v0.14 modules are not installed'
[[ -f "$RECEIPT" && ! -L "$RECEIPT" ]] || die 'candidate receipt is missing'
[[ "$(stat -c '%u:%g:%a:%h' "$RECEIPT")" == 0:0:600:1 ]] || die 'unsafe candidate receipt'
[[ -x "$RUNNER" && ! -L "$RUNNER" ]] || die 'candidate runner is missing'
[[ -x "$WAITER" && ! -L "$WAITER" ]] || die 'candidate waiter is missing'
[[ -r "$CANDIDATE_CONFIG" && ! -L "$CANDIDATE_CONFIG" ]] || die 'candidate config is missing'
[[ -r "$STATE_DIR/SHA256SUMS" && ! -L "$STATE_DIR/SHA256SUMS" ]] || die 'installed manifest is missing'
[[ ! -e "$DIAGNOSTICS_DIR" && ! -L "$DIAGNOSTICS_DIR" ]] || \
  die 'stale bridge diagnostics directory exists'
for command_path in /usr/bin/awk /usr/bin/evtest /usr/bin/mktemp /usr/bin/pgrep \
  /usr/bin/sleep /usr/bin/stdbuf; do
  [[ -x "$command_path" ]] || die "required command is missing: $command_path"
done

cd "$STATE_DIR"
sha256sum -c SHA256SUMS
cmp -s r46h-input-bridge /usr/local/libexec/r46h-input-bridge || die 'runtime bridge mismatch'
cmp -s r46h-input-bridge-wait "$WAITER" || die 'runtime waiter mismatch'
cmp -s r46h-game-ui-input-candidate "$RUNNER" || die 'runtime runner mismatch'
cmp -s r46h-input-bridge-trial /usr/local/sbin/r46h-input-bridge-trial || die 'runtime trial mismatch'
cmp -s r46h-input-bridge-remove /usr/local/sbin/r46h-input-bridge-remove || die 'runtime remover mismatch'
cmp -s retroarch.cfg "$CANDIDATE_CONFIG" || die 'runtime config mismatch'
cmp -s r46h-input-bridge.service /etc/systemd/system/r46h-input-bridge.service || die 'runtime unit mismatch'

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

systemctl stop r46h-gaming-frontend.service
[[ -z "$(pgrep -x retroarch || true)" ]] || die 'RetroArch process survived frontend stop'
systemctl start "$SERVICE"
systemctl is-active --quiet "$SERVICE" || die 'input bridge did not become active'
virtual_node=$("$WAITER" --print-node)
[[ "$virtual_node" =~ ^/dev/input/event[0-9]+$ ]] || die 'waiter returned an unsafe virtual node'

runtime_dir=$(/usr/bin/mktemp -d /run/r46h-input-bridge-trial.XXXXXX)
chmod 0700 "$runtime_dir"
runtime_id=$(stat -c '%d:%i' "$runtime_dir")
event_log=$runtime_dir/events.txt
install -o root -g root -m 0600 /dev/null "$event_log"

/usr/bin/stdbuf -oL -eL /usr/bin/evtest "$virtual_node" > "$event_log" 2>&1 &
capture_pid=$!
capture_ready=0
for ((attempt=0; attempt<30; attempt++)); do
  kill -0 "$capture_pid" 2>/dev/null || die 'virtual event capture exited before the operator window'
  if grep -Fq 'Testing ...' "$event_log"; then
    capture_ready=1
    break
  fi
  /usr/bin/sleep 0.1
done
(( capture_ready == 1 )) || die 'virtual event capture did not become ready'

"$RUNNER" smoke &
runner_pid=$!
runner_ready=0
for ((attempt=0; attempt<100; attempt++)); do
  kill -0 "$runner_pid" 2>/dev/null || die 'candidate runner exited before the operator window'
  if pgrep -x retroarch >/dev/null; then
    runner_ready=1
    break
  fi
  /usr/bin/sleep 0.1
done
(( runner_ready == 1 )) || die 'candidate RetroArch did not become ready'

printf 'R46H_INPUT_BRIDGE_TRIAL phase=operator-window seconds=%d controls=16-buttons,4-axes screen=dpad,a,left-stick auto-exit=yes\n' \
  "$INPUT_WINDOW_SECONDS"
printf '%s\n' \
  'ACTION: verify D-pad, A, and left-stick movement on screen.' \
  'ACTION: press/release A B X Y L1 R1 L2 R2 Select Start and every D-pad direction.' \
  'ACTION: click the left stick cap (L3), then click the right stick cap (R3).' \
  'ACTION: move both sticks through edges/corners, circle them, and release centered.'
/usr/bin/sleep "$INPUT_WINDOW_SECONDS"
kill -0 "$capture_pid" 2>/dev/null || die 'virtual event capture exited during the operator window'
kill -0 "$runner_pid" 2>/dev/null || die 'candidate runner exited during the operator window'

kill -TERM -- "$capture_pid"
set +e
wait "$capture_pid"
capture_status=$?
set -e
capture_pid=""
[[ "$capture_status" == 0 || "$capture_status" == 143 ]] || die "virtual event capture failed: $capture_status"

kill -TERM -- "$runner_pid"
set +e
wait "$runner_pid"
runner_status=$?
set -e
runner_pid=""
[[ "$runner_status" == 0 || "$runner_status" == 143 ]] || die "candidate runner failed: $runner_status"

systemctl stop "$SERVICE"
[[ "$(systemctl is-active "$SERVICE" 2>/dev/null || true)" == inactive ]] || \
  die 'input bridge did not stop cleanly'
[[ -z "$(pgrep -f '^/usr/local/libexec/r46h-input-bridge --diagnostics$' || true)" ]] || \
  die 'input bridge process survived explicit stop'
[[ -f "$DIAGNOSTICS" && ! -L "$DIAGNOSTICS" ]] || die 'bridge diagnostics are missing'
[[ "$(stat -c '%u:%g:%a:%h' "$DIAGNOSTICS")" == 0:0:600:1 ]] || \
  die 'unsafe bridge diagnostics identity'
[[ "$(wc -l < "$DIAGNOSTICS" | tr -d '[:space:]')" == 23 ]] || \
  die 'bridge diagnostics line count mismatch'
if ! read -r bridge_version bridge_status write_failures failed_type failed_code failed_value \
    < <(awk "$BRIDGE_HEADER_AWK" "$DIAGNOSTICS"); then
  die 'bridge diagnostics header is unparseable'
fi
[[ "$bridge_version" == r46h-gaming-input-bridge-v0.5 && "$bridge_status" == pass &&
   "$write_failures" == 0 && "$failed_type" == -1 && "$failed_code" == -1 &&
   "$failed_value" == -1 ]] || die 'bridge diagnostics header reports a runtime failure'
if ! read -r source_syn_reports emitted_syn_reports \
    < <(awk "$BRIDGE_SYN_AWK" "$DIAGNOSTICS"); then
  die 'bridge diagnostics SYN summary is unparseable'
fi
(( source_syn_reports >= 1 && emitted_syn_reports == source_syn_reports )) || \
  die 'bridge diagnostics SYN summary mismatch'

failures=0
grep -Fqx "Input device name: \"$EXPECTED_NAME\"" "$event_log" || {
  printf 'R46H_INPUT_BRIDGE_DEVICE result=fail reason=name-mismatch\n'
  failures=$((failures + 1))
}
for code in "${REQUIRED_CAPABILITY_KEYS[@]}" "${REQUIRED_AXES[@]}"; do
  if ! grep -Fq "($code)" "$event_log"; then
    printf 'R46H_INPUT_BRIDGE_CAPABILITY code=%s result=fail\n' "$code"
    failures=$((failures + 1))
  fi
done

syn_dropped=$(awk "$SYN_AWK" "$event_log")
if [[ "$syn_dropped" == 0 ]]; then
  printf 'R46H_INPUT_BRIDGE_SYN_DROPPED result=pass count=0\n'
else
  printf 'R46H_INPUT_BRIDGE_SYN_DROPPED result=fail count=%s\n' "$syn_dropped"
  failures=$((failures + 1))
fi

key_count=0
for key in "${REQUIRED_KEYS[@]}"; do
  if ! read -r source_presses source_releases source_other source_last \
      emitted_presses emitted_releases emitted_other emitted_last \
      < <(awk -v wanted="$key" "$BRIDGE_KEY_AWK" "$DIAGNOSTICS"); then
    printf 'R46H_INPUT_BRIDGE_PATH code=%s result=fail reason=diagnostic-unparseable\n' "$key"
    failures=$((failures + 1))
    continue
  fi
  read -r presses releases other last < <(awk -v wanted="$key" "$KEY_AWK" "$event_log")
  source_result=fail
  emitted_result=fail
  virtual_result=fail
  if (( source_presses >= 1 && source_releases >= 1 && source_last == 0 )); then
    source_result=pass
  fi
  if (( emitted_presses == source_presses &&
        emitted_releases == source_releases && emitted_other == source_other &&
        emitted_last == source_last )); then
    emitted_result=pass
  fi
  if (( presses == emitted_presses && releases == emitted_releases &&
        other == emitted_other && last == emitted_last )); then
    virtual_result=pass
  fi
  if [[ "$source_result" == pass && "$emitted_result" == pass &&
        "$virtual_result" == pass ]]; then
    localization=none
    key_count=$((key_count + 1))
    key_result=pass
  elif [[ "$source_result" == fail ]]; then
    localization=physical-source-missing
    key_result=fail
  elif [[ "$emitted_result" == fail ]]; then
    localization=bridge-write-missing
    key_result=fail
  else
    localization=virtual-delivery-or-capture-missing
    key_result=fail
  fi
  if [[ "$key_result" == fail ]]; then
    failures=$((failures + 1))
  fi
  printf 'R46H_INPUT_BRIDGE_KEY code=%s result=%s presses=%d releases=%d other=%d last=%d\n' \
    "$key" "$key_result" "$presses" "$releases" "$other" "$last"
  printf 'R46H_INPUT_BRIDGE_PATH code=%s source=%s emitted=%s virtual=%s localization=%s source_presses=%d source_releases=%d source_other=%d source_last=%d emitted_presses=%d emitted_releases=%d emitted_other=%d emitted_last=%d virtual_presses=%d virtual_releases=%d virtual_other=%d virtual_last=%d\n' \
    "$key" "$source_result" "$emitted_result" "$virtual_result" "$localization" \
    "$source_presses" "$source_releases" "$source_other" "$source_last" \
    "$emitted_presses" "$emitted_releases" "$emitted_other" "$emitted_last" \
    "$presses" "$releases" "$other" "$last"
done

axis_count=0
centered_count=0
for axis in "${REQUIRED_AXES[@]}"; do
  axis_result=pass
  if ! read -r source_samples source_min source_max source_last emitted_samples emitted_last \
      < <(awk -v wanted="$axis" "$BRIDGE_AXIS_AWK" "$DIAGNOSTICS"); then
    printf 'R46H_INPUT_BRIDGE_AXIS_PATH code=%s result=fail reason=diagnostic-unparseable\n' "$axis"
    failures=$((failures + 1))
    continue
  fi
  if ! read -r advertised_min advertised_max initial_value observed_min observed_max last_value sample_count \
      < <(awk -v wanted="$axis" "$AXIS_AWK" "$event_log"); then
    printf 'R46H_INPUT_BRIDGE_AXIS code=%s result=fail reason=unparseable\n' "$axis"
    failures=$((failures + 1))
    continue
  fi
  advertised_span=$((advertised_max - advertised_min))
  source_span=$((source_max - source_min))
  observed_span=$((observed_max - observed_min))
  source_min_delta=$((observed_min - source_min))
  (( source_min_delta < 0 )) && source_min_delta=$((-source_min_delta))
  source_max_delta=$((observed_max - source_max))
  (( source_max_delta < 0 )) && source_max_delta=$((-source_max_delta))
  source_last_delta=$((last_value - source_last))
  (( source_last_delta < 0 )) && source_last_delta=$((-source_last_delta))
  axis_path_result=fail
  if (( advertised_span <= 0 )); then
    axis_localization=diagnostic-inconsistent
  elif (( source_samples <= 0 || source_min < advertised_min ||
          source_max > advertised_max || source_last < advertised_min ||
          source_last > advertised_max || source_span * 100 < advertised_span * 70 )); then
    axis_path_result=fail
    axis_localization=physical-source-missing
  elif (( emitted_samples != source_samples || emitted_last != source_last )); then
    axis_path_result=fail
    axis_localization=bridge-write-missing
  elif (( sample_count <= 0 || observed_min < advertised_min ||
          observed_max > advertised_max || last_value < advertised_min ||
          last_value > advertised_max || observed_span * 100 < advertised_span * 70 ||
          source_min_delta * 100 > advertised_span * 20 ||
          source_max_delta * 100 > advertised_span * 20 ||
          source_last_delta * 100 > advertised_span * 10 )); then
    axis_path_result=fail
    axis_localization=virtual-delivery-or-capture-missing
  else
    axis_path_result=pass
    axis_localization=none
  fi
  if [[ "$axis_path_result" == fail ]]; then
    failures=$((failures + 1))
  fi
  printf 'R46H_INPUT_BRIDGE_AXIS_PATH code=%s result=%s localization=%s source_samples=%d source_min=%d source_max=%d source_last=%d emitted_samples=%d emitted_last=%d virtual_samples=%d virtual_min=%d virtual_max=%d virtual_last=%d\n' \
    "$axis" "$axis_path_result" "$axis_localization" "$source_samples" \
    "$source_min" "$source_max" "$source_last" "$emitted_samples" \
    "$emitted_last" "$sample_count" "$observed_min" "$observed_max" "$last_value"
  center_twice=$((advertised_min + advertised_max))
  initial_twice=$((initial_value * 2))
  center_delta=$((initial_twice - center_twice))
  (( center_delta < 0 )) && center_delta=$((-center_delta))
  return_delta=$((last_value - initial_value))
  (( return_delta < 0 )) && return_delta=$((-return_delta))
  if (( advertised_span <= 0 || sample_count <= 0 ||
        initial_value < advertised_min || initial_value > advertised_max ||
        observed_min < advertised_min || observed_max > advertised_max ||
        last_value < advertised_min || last_value > advertised_max ||
        observed_span * 100 < advertised_span * 70 ||
        (observed_min - advertised_min) * 100 > advertised_span * 20 ||
        (advertised_max - observed_max) * 100 > advertised_span * 20 )); then
    axis_result=fail
  else
    axis_count=$((axis_count + 1))
  fi
  if (( advertised_span > 0 &&
        center_delta * 100 <= advertised_span * 70 &&
        return_delta * 100 <= advertised_span * 10 )); then
    centered_count=$((centered_count + 1))
  else
    axis_result=fail
  fi
  printf 'R46H_INPUT_BRIDGE_AXIS code=%s result=%s advertised_min=%d advertised_max=%d initial=%d observed_min=%d observed_max=%d last=%d samples=%d\n' \
    "$axis" "$axis_result" "$advertised_min" "$advertised_max" \
    "$initial_value" "$observed_min" "$observed_max" "$last_value" "$sample_count"
  if [[ "$axis_result" == fail ]]; then
    failures=$((failures + 1))
  fi
done

printf 'R46H_INPUT_BRIDGE_COVERAGE keys=%d/%d axes=%d/%d centered=%d/%d failures=%d\n' \
  "$key_count" "${#REQUIRED_KEYS[@]}" "$axis_count" "${#REQUIRED_AXES[@]}" \
  "$centered_count" "${#REQUIRED_AXES[@]}" "$failures"
(( failures == 0 )) || die 'virtual combined-controller acceptance was incomplete'
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem reported an error during trial'
[[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd reported a failed unit during trial'
exit 0
