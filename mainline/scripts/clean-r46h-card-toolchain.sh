#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)
PYTHON=${R46H_PYTHON:-python3}

exec "$PYTHON" "$SCRIPT_DIR/r46h_card_toolchain.py" clean "$@"
