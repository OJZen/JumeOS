#!/bin/bash
set -Eeuo pipefail

PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG

readonly FEATURE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly REPO=$(cd -- "$FEATURE_DIR/../.." && pwd -P)
readonly OUTPUT=$REPO/mainline/out/r46h-remote-screen-es-de-v0.1
readonly REMOTE_SCREEN=$REPO/mainline/gaming-remote-screen
readonly CAPTURE=$REPO/mainline/out/r46h-gaming-remote-screen-v0.2/r46h-drm-capture

"$REMOTE_SCREEN/build-drm-capture.sh" validate
install -d -m 0755 "$OUTPUT"
expected=$'README.md\nSHA256SUMS\ninstall.sh\nr46h-drm-capture\nr46h-screenshot\nrollback.sh'
if [[ -n $(LC_ALL=C /bin/ls -1A "$OUTPUT" | sort | comm -23 - <(printf '%s\n' "$expected")) ]]; then
  printf 'ERROR: unexpected output member\n' >&2
  exit 1
fi
install -m 0644 "$FEATURE_DIR/README.md" "$OUTPUT/README.md"
install -m 0755 "$FEATURE_DIR/install.sh" "$OUTPUT/install.sh"
install -m 0755 "$CAPTURE" "$OUTPUT/r46h-drm-capture"
install -m 0755 "$REMOTE_SCREEN/r46h-screenshot" "$OUTPUT/r46h-screenshot"
install -m 0755 "$FEATURE_DIR/rollback.sh" "$OUTPUT/rollback.sh"
(cd "$OUTPUT" && sha256sum README.md install.sh r46h-drm-capture r46h-screenshot rollback.sh > SHA256SUMS)
printf 'R46H_REMOTE_SCREEN_ES_DE_PAYLOAD result=pass output=%s\n' "$OUTPUT"
