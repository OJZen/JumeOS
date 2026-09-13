#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$('/usr/bin/dirname' "$0")" && pwd -P)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd -P)
SOURCE="$REPO_ROOT/mainline/tools/r46h-card-agent/Sources/R46HCardLayoutProvision/main.c"
OUTPUT_DIR="$REPO_ROOT/mainline/out/r46h-card-agent/bin"
OUTPUT="$OUTPUT_DIR/r46h-card-layout-provision"
SOURCE_RECEIPT_PATH="../../../tools/r46h-card-agent/Sources/R46HCardLayoutProvision/main.c"

[[ -f "$SOURCE" && ! -L "$SOURCE" ]] || { echo "ERROR: missing layout provision source" >&2; exit 66; }
/bin/mkdir -p "$OUTPUT_DIR"

temporary_dir=$(/usr/bin/mktemp -d "$OUTPUT_DIR/.r46h-card-layout-provision-build.XXXXXX")
temporary="$temporary_dir/r46h-card-layout-provision"
temporary_source="$temporary_dir/main.c"
cleanup() {
  /bin/rm -f -- "$temporary" "$temporary_source" 2>/dev/null || true
  /bin/rmdir -- "$temporary_dir" 2>/dev/null || true
}
trap cleanup EXIT

source_actual=$(/usr/bin/shasum -a 256 "$SOURCE")
source_actual=${source_actual%% *}
[[ "$source_actual" =~ ^[0-9a-f]{64}$ ]] || { echo "ERROR: invalid source SHA-256" >&2; exit 65; }
/bin/cp -p -- "$SOURCE" "$temporary_source"
/bin/chmod 0600 "$temporary_source"
snapshot_before=$(/usr/bin/shasum -a 256 "$temporary_source")
snapshot_before=${snapshot_before%% *}
[[ "$snapshot_before" == "$source_actual" ]] || { echo "ERROR: source snapshot mismatch" >&2; exit 65; }

/usr/bin/xcrun clang \
  -std=c11 -O2 -Wall -Wextra -Werror \
  -Wl,-reproducible \
  "$temporary_source" \
  -framework CoreFoundation \
  -framework DiskArbitration \
  -o "$temporary"
/bin/chmod 0755 "$temporary"

actual=$(/usr/bin/shasum -a 256 "$temporary")
actual=${actual%% *}
[[ "$actual" =~ ^[0-9a-f]{64}$ ]] || { echo "ERROR: invalid binary SHA-256" >&2; exit 65; }
snapshot_after=$(/usr/bin/shasum -a 256 "$temporary_source")
snapshot_after=${snapshot_after%% *}
source_after=$(/usr/bin/shasum -a 256 "$SOURCE")
source_after=${source_after%% *}
[[ "$snapshot_after" == "$source_actual" && "$source_after" == "$source_actual" ]] || {
  echo "ERROR: source changed while building" >&2
  exit 65
}

/bin/mv -f -- "$temporary" "$OUTPUT"
/bin/rm -f -- "$temporary_source"
/bin/rmdir -- "$temporary_dir"
trap - EXIT
printf '%s  %s\n%s  %s\n' \
  "$actual" "$('/usr/bin/basename' "$OUTPUT")" \
  "$source_actual" "$SOURCE_RECEIPT_PATH" \
  > "$OUTPUT_DIR/r46h-card-layout-provision.sha256"
printf 'PASS: built %s\nSHA256=%s\n' "$OUTPUT" "$actual"
