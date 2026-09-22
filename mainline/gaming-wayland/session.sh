#!/bin/sh
# Unprivileged compositor session. Device supervision belongs to probe-r46h.sh.
set -eu
[ "$#" -ge 2 ] && [ "$#" -le 3 ] && { [ "$1" = headless ] || [ "$1" = drm ] || [ "$1" = seat ]; } || exit 2
mode=$1
output=$2
profile=${3:-windows}
case "$profile" in windows|handheld) ;; *) exit 2;; esac
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
if [ "$mode" = seat ]; then
    [ "$(id -u)" = 0 ] && [ "$base" = /run/r46h-wayland-probe ] || exit 1
    [ ! -e /run/seatd.sock ] && [ ! -L /run/seatd.sock ] || exit 1
    "$base/usr/sbin/seatd" -u ark -g ark > "$base/seatd.log" 2>&1 &
    seat=$!
    trap 'kill "$seat" 2>/dev/null || true; wait "$seat" 2>/dev/null || true' EXIT
    trap 'exit 143' TERM HUP
    trap 'exit 130' INT
    for attempt in $(seq 1 100); do
        [ ! -S /run/seatd.sock ] || break
        kill -0 "$seat"
        sleep 0.1
    done
    [ -S /run/seatd.sock ]
    stat -c '%d:%i' /run/seatd.sock > "$base/seatd-socket-identity"
    if [ "$profile" = handheld ]; then
        [ -c /dev/uinput ] && [ ! -L /dev/uinput ] && [ "$(stat -c '%t:%T' /dev/uinput)" = a:df ]
        # Delegate one open handle, never global device permissions. No parent copy
        # may survive: uinput destroys the virtual device on its last close.
        exec 7>/dev/uinput
        /usr/bin/setpriv --reuid=ark --regid=ark --init-groups -- "$0" drm "$output" handheld &
        client=$!
        exec 7>&-
        wait "$client"
    else
        /usr/sbin/runuser -u ark -- "$0" drm "$output"
    fi
    exit
fi
case "$base:$output" in *[[:space:]\;=]*) echo 'Paths must not contain whitespace, semicolon or equals.' >&2; exit 2;; esac
case "$output" in /*) ;; *) exit 2;; esac
umask 077
mkdir -p "$output"
export XDG_RUNTIME_DIR
XDG_RUNTIME_DIR=$(mktemp -d "$output/runtime.XXXXXX")
export XDG_CONFIG_HOME="$output/config" XDG_CACHE_HOME="$output/cache" XDG_DATA_HOME="$output/data"
export TMPDIR="$output" QML_DISABLE_DISK_CACHE=1 QT_DISABLE_SHADER_DISK_CACHE=1
export QT_QPA_PLATFORM=wayland R46H_VIRTUAL_KEYBOARD=0 SDL_NO_SIGNAL_HANDLERS=1
unset QT_IM_MODULE QT_QPA_EGLFS_INTEGRATION
lib="$base/usr/lib/aarch64-linux-gnu"
export LD_LIBRARY_PATH="$lib:$lib/weston:$lib/libproxy"
export GBM_BACKENDS_PATH="$lib/gbm" GBM_BACKEND=dri
export __EGL_VENDOR_LIBRARY_FILENAMES="$base/usr/share/glvnd/egl_vendor.d/50_mesa.json"
export WAYLAND_DISPLAY=r46h-wayland-probe
export WESTON_DATA_DIR="$base/usr/share/weston"
export XCURSOR_PATH="$base/usr/share/icons:/usr/share/icons" XCURSOR_THEME=DMZ-White XCURSOR_SIZE=24
WESTON_MODULE_MAP=''
for module in "$lib"/libweston-14/*.so "$lib"/weston/*.so*; do
    WESTON_MODULE_MAP="$WESTON_MODULE_MAP$(basename "$module")=$module;"
done
export WESTON_MODULE_MAP
shell=desktop-shell.so
if [ "$profile" = handheld ]; then
    [ -n "${R46H_ROUTED_SOURCE:-}" ] && [ -c "$R46H_ROUTED_SOURCE" ] && [ -r "$R46H_ROUTED_SOURCE" ]
    [ -c /proc/self/fd/7 ] && [ "$(stat -Lc '%t:%T' /proc/self/fd/7)" = a:df ]
    shell="$lib/weston/handheld-shell.so"
fi
cat > "$output/weston.ini" <<CONFIG
[core]
require-input=false
[shell]
client=$base/usr/libexec/weston-desktop-shell
background-color=0xff111a24
panel-position=none
locking=false
animation=none
[input-method]
path=$base/usr/libexec/weston-keyboard
CONFIG
pid=''
client=''
cleanup() {
    [ -z "$client" ] || kill "$client" 2>/dev/null || true
    [ -z "$client" ] || wait "$client" 2>/dev/null || true
    [ -z "$pid" ] || kill "$pid" 2>/dev/null || true
    [ -z "$pid" ] || wait "$pid" 2>/dev/null || true
    rm -rf -- "$XDG_RUNTIME_DIR"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
if [ "$mode" = headless ]; then
    export QT_QUICK_BACKEND=software
    set -- --backend=headless-backend.so --renderer=pixman --width=1024 --height=768
else
    unset QT_QUICK_BACKEND
    export QSG_RHI_BACKEND=opengl QSG_INFO=1 LIBSEAT_BACKEND=seatd SEATD_SOCK=/run/seatd.sock
    if [ "$profile" = windows ]; then
        mapping=$(sed -n '/^readonly CONTROLLER_MAPPING=/p' /usr/local/sbin/r46h-es-de-ui | cut -d "'" -f 2)
        case "$mapping" in 06004e84465200004800000001000000,*) ;; *) exit 1;; esac
        export SDL_GAMECONTROLLERCONFIG="$mapping" SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT=0x5246/0x0048
    fi
    set -- --backend=drm-backend.so --renderer=gl --drm-device=card0 --current-mode --continue-without-input
fi
"$base/usr/bin/weston" "$@" --shell="$shell" --config="$output/weston.ini" \
    --socket="$WAYLAND_DISPLAY" --idle-time=0 --log="$output/weston.log" \
    > "$output/weston-stderr.log" 2>&1 7>&- &
pid=$!
for attempt in $(seq 1 100); do
    [ ! -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ] || break
    kill -0 "$pid"
    sleep 0.1
done
[ -S "$XDG_RUNTIME_DIR/$WAYLAND_DISPLAY" ]
if [ "$profile" = handheld ]; then
    "$base/handheld-client.sh" ui "$output" > "$output/clients.log" 2>&1 &
    client=$!
    exec 7>&-
    wait "$client"
    client=''
else
    "$base/clients.sh" "$mode" "$output"
fi
kill "$pid"
wait "$pid"
pid=''
if [ "$profile" = windows ]; then grep -q '^WAYLAND_CLIENTS_PASS ' "$output/clients.log"; fi
printf 'WAYLAND_SESSION_PASS backend=%s profile=%s physical_acceptance=UNTESTED\n' "$mode" "$profile"
