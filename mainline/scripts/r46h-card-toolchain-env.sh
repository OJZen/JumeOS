#!/bin/sh
set -eu

# Print shell exports for direct Cargo work:
#   eval "$(mainline/scripts/r46h-card-toolchain-env.sh)"
SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)
PYTHON=${R46H_PYTHON:-python3}

exec "$PYTHON" "$SCRIPT_DIR/r46h_card_toolchain.py" env --format sh "$@"
