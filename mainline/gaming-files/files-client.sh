#!/bin/sh
set -eu
umask 077
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
[ "$(id -u)" != 0 ] || exit 2
[ "${QT_QPA_PLATFORM:-}" = wayland ] && [ -n "${WAYLAND_DISPLAY:-}" ] || exit 2
[ -d "${XDG_RUNTIME_DIR:-}" ] && [ ! -L "$XDG_RUNTIME_DIR" ] && [ "$(stat -c %u:%a "$XDG_RUNTIME_DIR")" = "$(id -u):700" ] || exit 2
export LD_LIBRARY_PATH="$base/usr/lib/aarch64-linux-gnu:$base/usr/lib/aarch64-linux-gnu/libproxy${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export QT_PLUGIN_PATH="$base/usr/lib/aarch64-linux-gnu/qt6/plugins"
unset QT_IM_MODULE QML_IMPORT_PATH QML2_IMPORT_PATH QT_QPA_EGLFS_INTEGRATION
unset XDG_CONFIG_HOME XDG_DATA_HOME XDG_CACHE_HOME R46H_SHELL_LOG R46H_DEVICE_CONTROLS
for argument in "$@"; do
    if [ "$argument" = --transfer ]; then
        exec "$base/usr/bin/jume-files" "$@"
    fi
done
# main reads the real user's XDG directory mapping, then sets private app paths.
# Debian Qt Multimedia uses PulseAudio; the accepted device otherwise uses ALSA.
# A private foreground server bridges one default PCM sink, with no mixer control,
# network listener, global service, saved volume or user Pulse configuration.
audio=$(mktemp -d "$XDG_RUNTIME_DIR/jume-files-audio.XXXXXX")
case "$audio" in *[!a-zA-Z0-9/_.-]*) rmdir "$audio";exit 2;; esac
export PULSE_RUNTIME_PATH="$audio" PULSE_STATE_PATH="$audio" PULSE_CONFIG_PATH="$audio"
export PULSE_SERVER="unix:$audio/native" PULSE_SINK=jume_files
server= child=
cleanup() {
    [ -z "$child" ] || kill "$child" 2>/dev/null || true
    [ -z "$child" ] || wait "$child" 2>/dev/null || true
    [ -z "$server" ] || kill "$server" 2>/dev/null || true
    [ -z "$server" ] || wait "$server" 2>/dev/null || true
    rm -rf -- "$audio"
}
trap cleanup EXIT
trap 'exit 143' TERM HUP
trap 'exit 130' INT
"$base/usr/bin/pulseaudio" --daemonize=no --exit-idle-time=-1 --use-pid-file=no --disable-shm=yes \
    --dl-search-path="$base/usr/lib/aarch64-linux-gnu/jume-audio" -n \
    --load="module-native-protocol-unix socket=$audio/native auth-anonymous=1 auth-cookie-enabled=0" \
    --load="module-alsa-sink device=default sink_name=jume_files" >/dev/null 2>&1 &
server=$!
for attempt in $(seq 1 40); do [ ! -S "$audio/native" ] || break; kill -0 "$server" 2>/dev/null || break; sleep .05; done
"$base/usr/bin/jume-files" "$@" &
child=$!
status=0
wait "$child" || status=$?
child=
exit "$status"
