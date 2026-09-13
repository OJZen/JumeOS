#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(/usr/bin/dirname "$0")" && pwd -P)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd -P)
BIN_DIR="$REPO_ROOT/mainline/out/r46h-card-agent/bin"
AGENT="$BIN_DIR/r46h-card-agent"
SUMS="$BIN_DIR/SHA256SUMS"
DEFAULT_PROFILE_ID=hl-r46h-v22-g92-v1
PROFILE_ID=$DEFAULT_PROFILE_ID
LEGACY_PROFILE="$REPO_ROOT/mainline/deploy/profiles/hl-r46h-v22-g92-v1.json"
LEGACY_PROFILE_SHA256=1c4f0d7116294085d59d5e60e08480c7ac715eddb4d839d0cbdaab605de8beb1
NEW_CARD_PROFILE="$REPO_ROOT/mainline/deploy/profiles/hl-r46h-v22-g92-31719424000-v1.json"
NEW_CARD_PROFILE_SHA256=fc14a1f0fefbccc281e0b6887e78986cbaca0a9205ca2167ea338c41e9839a7b
RECOVERED_NEW_CARD_PROFILE="$REPO_ROOT/mainline/deploy/profiles/hl-r46h-v22-g92-31719424000-p3-recovery-v1.json"
RECOVERED_NEW_CARD_PROFILE_SHA256=13a44b40cc68bfd9d172e708c46c3d9758748ff6d6df394a10c5ab2b0358fc24
FAST_CARD_PROFILE="$REPO_ROOT/mainline/deploy/profiles/hl-r46h-v22-g92-62534975488-v1.json"
FAST_CARD_PROFILE_SHA256=2066603fad59102ccb9b39851962ef8224d1a45f8a672c097ad5b91d45f4e20b
OUTPUT_ROOT="$REPO_ROOT/mainline/out/r46h-card-agent-sessions"

MODE=audit
DEVICE=/dev/disk4
WRITE_PLAN=
WRITE_PLAN_SHA256=
NO_TUI=0

usage() {
  /bin/cat <<'EOF'
usage: mainline/scripts/start-r46h-card-agent.sh [OPTIONS]

  --device /dev/diskN        fixed target for this session (default: /dev/disk4)
  --profile-id ID            audited card profile (default: hl-r46h-v22-g92-v1)
  --no-tui                   line-oriented foreground log instead of terminal UI
  --deploy                   enable only a separately pinned write plan
  --write-plan ABSOLUTE_PATH required with --deploy
  --write-plan-sha256 HASH   required with --deploy
EOF
}

while (($#)); do
  case "$1" in
    --device)
      (($# >= 2)) || { usage >&2; exit 64; }
      DEVICE=$2
      shift 2
      ;;
    --profile-id)
      (($# >= 2)) || { usage >&2; exit 64; }
      PROFILE_ID=$2
      shift 2
      ;;
    --no-tui)
      NO_TUI=1
      shift
      ;;
    --deploy)
      MODE=deploy
      shift
      ;;
    --write-plan)
      (($# >= 2)) || { usage >&2; exit 64; }
      WRITE_PLAN=$2
      shift 2
      ;;
    --write-plan-sha256)
      (($# >= 2)) || { usage >&2; exit 64; }
      WRITE_PLAN_SHA256=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 64
      ;;
  esac
done

[[ "$DEVICE" =~ ^/dev/disk[1-9][0-9]*$ ]] || { echo "ERROR: unsafe device: $DEVICE" >&2; exit 64; }
case "$PROFILE_ID" in
  hl-r46h-v22-g92-v1)
    PROFILE=$LEGACY_PROFILE
    PROFILE_SHA256=$LEGACY_PROFILE_SHA256
    ;;
  hl-r46h-v22-g92-31719424000-v1)
    PROFILE=$NEW_CARD_PROFILE
    PROFILE_SHA256=$NEW_CARD_PROFILE_SHA256
    ;;
  hl-r46h-v22-g92-31719424000-p3-recovery-v1)
    PROFILE=$RECOVERED_NEW_CARD_PROFILE
    PROFILE_SHA256=$RECOVERED_NEW_CARD_PROFILE_SHA256
    ;;
  hl-r46h-v22-g92-62534975488-v1)
    PROFILE=$FAST_CARD_PROFILE
    PROFILE_SHA256=$FAST_CARD_PROFILE_SHA256
    ;;
  *)
    echo "ERROR: unsupported card profile ID: $PROFILE_ID" >&2
    exit 64
    ;;
esac
/bin/test -f "$AGENT" || { echo "ERROR: build the agent first: mainline/scripts/build-r46h-card-agent.sh" >&2; exit 66; }
/bin/test -f "$SUMS" || { echo "ERROR: missing binary checksum manifest" >&2; exit 66; }

expected_binary=$(/usr/bin/awk '$2 == "r46h-card-agent" { print $1 }' "$SUMS")
actual_binary=$(/usr/bin/shasum -a 256 "$AGENT")
actual_binary=${actual_binary%% *}
[[ "$expected_binary" =~ ^[0-9a-f]{64}$ && "$actual_binary" == "$expected_binary" ]] || {
  echo "ERROR: agent binary checksum mismatch" >&2
  exit 65
}
binary_size=$(/usr/bin/stat -f '%z' "$AGENT")
[[ "$binary_size" =~ ^[1-9][0-9]*$ && "$binary_size" -le 134217728 ]] || {
  echo "ERROR: unsafe agent binary size" >&2
  exit 65
}
actual_profile=$(/usr/bin/shasum -a 256 "$PROFILE")
actual_profile=${actual_profile%% *}
[[ "$actual_profile" == "$PROFILE_SHA256" ]] || { echo "ERROR: card profile checksum mismatch" >&2; exit 65; }

if [[ "$MODE" == deploy ]]; then
  [[ "$WRITE_PLAN" == /* && "$WRITE_PLAN_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
    echo "ERROR: deploy mode requires an absolute --write-plan and lowercase SHA-256" >&2
    exit 64
  }
else
  [[ -z "$WRITE_PLAN" && -z "$WRITE_PLAN_SHA256" ]] || {
    echo "ERROR: write-plan options require --deploy" >&2
    exit 64
  }
fi

/bin/mkdir -p "$OUTPUT_ROOT"
/bin/chmod 0755 "$OUTPUT_ROOT"

echo "R46H Card Agent foreground session"
echo "mode=$MODE device=$DEVICE profile=$PROFILE_ID"
echo "One administrator authorization starts the fixed-command broker."
echo "Keep this window open; press Ctrl+C or run r46h-cardctl stop to close it safely."

AGENT_ARGUMENTS=(
  serve
  --mode "$MODE"
  --device "$DEVICE"
  --profile "$PROFILE"
  --profile-sha256 "$PROFILE_SHA256"
  --output-root "$OUTPUT_ROOT"
  --input-root "$REPO_ROOT"
)
if [[ "$MODE" == deploy ]]; then
  AGENT_ARGUMENTS+=(--write-plan "$WRITE_PLAN" --write-plan-sha256 "$WRITE_PLAN_SHA256")
fi
if [[ "$NO_TUI" -eq 1 ]]; then
  AGENT_ARGUMENTS+=(--no-tui)
fi

# shellcheck disable=SC2016  # Expanded only by the privileged child shell.
ROOT_BOOTSTRAP='
set -euo pipefail
source_binary=$1
expected_sha256=$2
expected_size=$3
expected_uid=$4
shift 4

[[ "$expected_sha256" =~ ^[0-9a-f]{64}$ ]]
[[ "$expected_size" =~ ^[1-9][0-9]*$ && "$expected_size" -le 134217728 ]]
[[ "${SUDO_UID:-}" == "$expected_uid" && "$expected_uid" =~ ^[1-9][0-9]*$ ]]

umask 077
stage_directory=$(/usr/bin/mktemp -d /private/tmp/r46h-card-agent-root.XXXXXX)
staged_agent="$stage_directory/r46h-card-agent"
cleanup_stage() {
  /bin/rm -f "$staged_agent" 2>/dev/null || true
  /bin/rmdir "$stage_directory" 2>/dev/null || true
}
trap cleanup_stage EXIT

/usr/bin/install -m 0700 "$source_binary" "$staged_agent"
staged_identity=$(/usr/bin/stat -f "%u:%Lp:%z" "$staged_agent")
[[ "$staged_identity" == "0:700:$expected_size" ]]
staged_sha256=$(/usr/bin/shasum -a 256 "$staged_agent")
staged_sha256=${staged_sha256%% *}
[[ "$staged_sha256" == "$expected_sha256" ]] || {
  echo "ERROR: root-staged agent checksum mismatch" >&2
  exit 65
}

"$staged_agent" "$@" &
agent_pid=$!

forward_stop() {
  /bin/kill -INT "$agent_pid" 2>/dev/null || true
}
trap forward_stop HUP INT TERM

agent_status=0
set +e
while /bin/kill -0 "$agent_pid" 2>/dev/null; do
  wait "$agent_pid"
  agent_status=$?
done
wait "$agent_pid" 2>/dev/null
final_status=$?
if [[ $final_status -eq 127 ]]; then
  final_status=$agent_status
fi
exit "$final_status"
'

exec /usr/bin/sudo -- /bin/bash -c "$ROOT_BOOTSTRAP" r46h-card-agent-root-bootstrap \
  "$AGENT" "$expected_binary" "$binary_size" "$(/usr/bin/id -u)" \
  "${AGENT_ARGUMENTS[@]}"
