#!/bin/bash
set -Eeuo pipefail

PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG

readonly FEATURE_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly REPO=$(cd -- "$FEATURE_DIR/../.." && pwd -P)
readonly OUTPUT=$REPO/mainline/out/r46h-gaming-es-de-visual-v0.1
readonly THEME=$REPO/mainline/gaming-es-de/r46h-theme.xml

install -d -m 0755 "$OUTPUT"
expected=$'README.md\nSHA256SUMS\ninstall.sh\nr46h-theme.xml\nrollback.sh'
if [[ -n $(LC_ALL=C /bin/ls -1A "$OUTPUT" | sort | comm -23 - <(printf '%s\n' "$expected")) ]]; then
  printf 'ERROR: unexpected output member\n' >&2
  exit 1
fi
install -m 0644 "$FEATURE_DIR/README.md" "$OUTPUT/README.md"
install -m 0755 "$FEATURE_DIR/install.sh" "$OUTPUT/install.sh"
install -m 0644 "$THEME" "$OUTPUT/r46h-theme.xml"
install -m 0755 "$FEATURE_DIR/rollback.sh" "$OUTPUT/rollback.sh"
(cd "$OUTPUT" && sha256sum README.md install.sh r46h-theme.xml rollback.sh > SHA256SUMS)
printf 'R46H_ES_DE_VISUAL_PAYLOAD result=pass output=%s\n' "$OUTPUT"
