#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(/usr/bin/dirname "$0")" && pwd -P)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd -P)
BIN_DIR="$REPO_ROOT/mainline/out/r46h-card-agent/bin"
CLIENT="$BIN_DIR/r46h-cardctl"
SUMS="$BIN_DIR/SHA256SUMS"

/bin/test -f "$CLIENT" || { echo "ERROR: build the agent first: mainline/scripts/build-r46h-card-agent.sh" >&2; exit 66; }
/bin/test -f "$SUMS" || { echo "ERROR: missing binary checksum manifest" >&2; exit 66; }
expected=$(/usr/bin/awk '$2 == "r46h-cardctl" { print $1 }' "$SUMS")
actual=$(/usr/bin/shasum -a 256 "$CLIENT")
actual=${actual%% *}
[[ "$expected" =~ ^[0-9a-f]{64}$ && "$actual" == "$expected" ]] || {
  echo "ERROR: client binary checksum mismatch" >&2
  exit 65
}

exec "$CLIENT" "$@"
