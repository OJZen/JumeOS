#!/bin/sh
set -eu
umask 077
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
[ "$(id -u)" != 0 ] || { echo 'Browser must run as the desktop user.' >&2; exit 2; }
[ "${QT_QPA_PLATFORM:-}" = wayland ] && [ -n "${WAYLAND_DISPLAY:-}" ] || { echo 'Browser requires the shared Wayland desktop.' >&2; exit 2; }
export LD_LIBRARY_PATH="$base/usr/lib/aarch64-linux-gnu:$base/usr/lib/aarch64-linux-gnu/libproxy${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export QT_PLUGIN_PATH="$base/usr/lib/aarch64-linux-gnu/qt6/plugins"
export QML_IMPORT_PATH="$base/usr/lib/aarch64-linux-gnu/qt6/qml"
export QTWEBENGINEPROCESS_PATH="$base/usr/lib/qt6/libexec/QtWebEngineProcess"
export QTWEBENGINE_RESOURCES_PATH="$base/usr/share/qt6/resources"
export QTWEBENGINE_LOCALES_PATH="$base/usr/share/qt6/translations/qtwebengine_locales"
export QSG_RHI_BACKEND=opengl
unset QT_QUICK_BACKEND QT_QPA_EGLFS_INTEGRATION LIBGL_ALWAYS_SOFTWARE
# The session owns Mesa/Panfrost selection. Preserve its GBM/EGL/DRI settings.
exec "$base/usr/bin/jume-browser" "$@"
