#!/bin/sh
set -eu
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
workspace=$(CDPATH= cd -- "$source_dir/../.." && pwd -P)
output="$workspace/mainline/out/.cache/r46h-shell"
export TMPDIR="$output/tmp"
export QML_DISABLE_DISK_CACHE=1
export QT_DISABLE_SHADER_DISK_CACHE=1
export QT_SHADER_CACHE_PATH="$output/shader-cache"
export CLANG_MODULE_CACHE_PATH="$output/clang-cache"
mkdir -p "$TMPDIR"
if [ "$(uname -s)" = Darwin ]; then
    qt_prefix=${R46H_QT_PREFIX:-"$output/qt/6.8.2/macos"}
else
    qt_prefix=${R46H_QT_PREFIX:-/usr}
fi
cmake -S "$source_dir" -B "$output/build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$qt_prefix"
cmake --build "$output/build" -j 4
if [ "${1:-}" = --check ]; then
    shift
    exec "$output/build/shell-check" "$@"
fi
exec "$output/build/r46h-shell" --state-dir "$output/state" "$@"
