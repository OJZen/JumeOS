#!/bin/sh
# Place beside the extracted official package's usr/ tree; state stays private.
set -eu
umask 077
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
export XDG_CONFIG_HOME="$base/state/config"
export XDG_CACHE_HOME="$base/state/cache"
export XDG_DATA_HOME="$base/state/data"
mkdir -p "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME" "$XDG_DATA_HOME"
export LD_LIBRARY_PATH="$base/usr/lib/aarch64-linux-gnu:$base/usr/lib/aarch64-linux-gnu/libproxy"
export QT_PLUGIN_PATH="$base/usr/lib/aarch64-linux-gnu/qt6/plugins"
export QML_IMPORT_PATH="$base/usr/lib/aarch64-linux-gnu/qt6/qml"
exec "$base/usr/bin/moonlight-qt" "$@"
