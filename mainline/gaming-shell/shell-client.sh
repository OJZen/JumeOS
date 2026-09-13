#!/bin/sh
set -eu
umask 077
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
state_dir=${R46H_SHELL_STATE_DIR:-"$base/state"}
case "$state_dir" in /*) ;; *) echo 'Shell state directory must be absolute.' >&2; exit 2;; esac
case "$state_dir" in *'//'*|*/./*|*/../*|*/.|*/..|/*/) exit 2;; esac
state_parent=$state_dir
while [ "$state_parent" != / ]; do
    [ ! -L "$state_parent" ] || exit 2
    state_parent=${state_parent%/*}
    [ -n "$state_parent" ] || state_parent=/
done
mkdir -p "$state_dir"
[ "$(CDPATH= cd -- "$state_dir" && pwd -P)" = "$state_dir" ] || { echo 'Shell state directory must be canonical.' >&2; exit 2; }
if [ "$(uname -s)" = Darwin ]; then state_owner=$(stat -f '%u:%Lp' "$state_dir"); else state_owner=$(stat -c '%u:%a' "$state_dir"); fi
[ "$state_owner" = "$(id -u):700" ] || { echo 'Shell state directory must be owned by this user and mode 0700.' >&2; exit 2; }
export XDG_CONFIG_HOME="$state_dir/config"
export XDG_CACHE_HOME="$state_dir/cache"
export XDG_DATA_HOME="$state_dir/data"
export QML_DISABLE_DISK_CACHE=1
export QT_DISABLE_SHADER_DISK_CACHE=1
export LD_LIBRARY_PATH="$base/usr/lib/aarch64-linux-gnu:$base/usr/lib/aarch64-linux-gnu/libproxy"
export QT_PLUGIN_PATH="$base/usr/lib/aarch64-linux-gnu/qt6/plugins"
export QML_IMPORT_PATH="$base/usr/lib/aarch64-linux-gnu/qt6/qml"
for state_child in "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME"; do [ ! -L "$state_child" ] || exit 2; done
mkdir -p "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME"
if [ "${1:-}" = --check-state ]; then [ "$#" -eq 1 ] || exit 2; exit 0; fi
if [ "${R46H_SHELL_LOG:-0}" = 1 ]; then
    mkdir -p "$base/state"
    exec > "$base/state/runtime.log" 2>&1
fi
exec "$base/usr/bin/r46h-shell" --state-dir "$state_dir" "$@"
