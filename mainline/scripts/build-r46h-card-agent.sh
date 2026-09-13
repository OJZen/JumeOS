#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(/usr/bin/dirname "$0")" && pwd -P)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd -P)
PACKAGE_ROOT="$REPO_ROOT/mainline/tools/r46h-card-agent"
OUT_ROOT="$REPO_ROOT/mainline/out"
SCRATCH_ROOT="$OUT_ROOT/.swift-build/r46h-card-agent"
MODULE_CACHE="$OUT_ROOT/.swift-module-cache"
DESTINATION="$OUT_ROOT/r46h-card-agent/bin"

/bin/mkdir -p "$OUT_ROOT" "$SCRATCH_ROOT" "$MODULE_CACHE" "$DESTINATION"
/bin/chmod 0755 "$OUT_ROOT" "$DESTINATION"

export CLANG_MODULE_CACHE_PATH="$MODULE_CACHE"
export SWIFTPM_MODULECACHE_OVERRIDE="$MODULE_CACHE"
export TMPDIR="$OUT_ROOT/.tmp-r46h-card-agent"
/bin/mkdir -p "$TMPDIR"
cleanup() {
  /bin/rm -rf "$TMPDIR"
  /bin/rm -f "$DESTINATION/r46h-card-agent.new" "$DESTINATION/r46h-cardctl.new" "$DESTINATION/SHA256SUMS.new"
}
trap cleanup EXIT HUP INT TERM

/usr/bin/swift build \
  --disable-sandbox \
  --jobs 1 \
  --configuration release \
  --package-path "$PACKAGE_ROOT" \
  --scratch-path "$SCRATCH_ROOT"

BIN_PATH=$(/usr/bin/swift build \
  --disable-sandbox \
  --configuration release \
  --package-path "$PACKAGE_ROOT" \
  --scratch-path "$SCRATCH_ROOT" \
  --show-bin-path)

for NAME in r46h-card-agent r46h-cardctl; do
  /bin/test -f "$BIN_PATH/$NAME"
  /usr/bin/install -m 0755 "$BIN_PATH/$NAME" "$DESTINATION/$NAME.new"
  /bin/mv -f "$DESTINATION/$NAME.new" "$DESTINATION/$NAME"
done

(
  cd -- "$DESTINATION"
  /usr/bin/shasum -a 256 r46h-card-agent r46h-cardctl > SHA256SUMS.new
  /bin/mv -f SHA256SUMS.new SHA256SUMS
)

cleanup
trap - EXIT HUP INT TERM
echo "PASS: release binaries built and pinned at $DESTINATION"
/bin/cat "$DESTINATION/SHA256SUMS"
