#!/bin/bash
# Fixed installed-session hooks; ES-DE is retained but never used for crash recovery.
set -Eeuo pipefail
[[ $# == 1 && $EUID == 0 ]] || exit 2
scope=/run/r46h-wayland-probe
runtime=/run/jume-launcher
release=$(readlink -f /var/lib/jume-launcher/current)
[[ $release =~ ^/var/lib/jume-launcher/releases/[0-9a-f]{64}$ ]] || exit 1
[[ $(stat -c %u:%g:%a "$release") == 0:0:755 && ! -L $release ]] || exit 1
unit=jume-launcher.service
export R46H_SHELL_STATE_DIR=/home/ark/.local/share/r46h-preview
export R46H_DEVICE_CONTROLS=1 R46H_SHARED_PORTS=1 R46H_INSTALLED_SESSION=1
case $1 in
--prepare)
    [[ ! -e $scope && ! -L $scope && ! -e /run/seatd.sock && ! -L /run/seatd.sock ]] || exit 1
    [[ ! -e $runtime/mount-id && ! -e $runtime/scope-created ]] || exit 1
    /usr/bin/python3 "$release/product-install.py" --verify "${release##*/}"
    touch "$runtime/scope-created"
    mkdir -m 755 "$scope"
    mount --bind "$release" "$scope"
    # The mount ID is owned by root, outside all user-writable session state.
    findmnt -rn -M "$scope" -o ID > "$runtime/mount-id"
    /bin/bash "$scope/probe-r46h.sh" --check-installed "${release##*/}" handheld
    /bin/bash "$scope/session-leases.sh" --acquire "$unit" 1 1
    install -d -o ark -g ark -m 700 "$runtime/session"
    ;;
--run)
    inputs=()
    for name in /sys/class/input/event*/device/name; do
        [[ $(cat "$name") != 'R46H Combined Gamepad' ]] || inputs+=("/dev/input/$(basename "$(dirname "$(dirname "$name")")")")
    done
    [[ ${#inputs[@]} == 1 ]] || exit 1
    export R46H_ROUTED_SOURCE=${inputs[0]}
    exec /usr/bin/setsid --wait /usr/bin/openvt -e -c 2 -s -f -- /bin/bash "$scope/session.sh" seat "$runtime/session" handheld
    ;;
--restore)
    # ExecStopPost runs only after systemd has killed every desktop/browser child.
    if [[ -f $runtime/mount-id && ! -L $runtime/mount-id ]]; then
        mount_id=$(cat "$runtime/mount-id")
        [[ $mount_id =~ ^[0-9]+$ && $(findmnt -rn -M "$scope" -o ID) == "$mount_id" ]] || exit 1
        /bin/bash "$scope/session-leases.sh" --restore "$unit" 1 1
        if [[ -e /run/seatd.sock || -L /run/seatd.sock ]]; then
            [[ -S /run/seatd.sock && ! -L /run/seatd.sock && -f $runtime/seatd-socket-identity
               && $(stat -c '%d:%i' /run/seatd.sock) == "$(cat "$runtime/seatd-socket-identity")" ]] || exit 1
            rm -- /run/seatd.sock
        fi
        umount "$scope"
        rmdir "$scope"
        rm -- "$runtime/mount-id"
    elif [[ -f $runtime/scope-created ]]; then
        if mountpoint -q "$scope"; then exit 1; fi
        [[ ! -e $scope ]] || rmdir "$scope"
    fi
    if [[ -f $runtime/scope-created ]]; then
        rm -f -- "$runtime/scope-created" "$runtime/seatd-socket-identity"
        # Fixed task-owned runtime only, never the persistent user state.
        rm -rf -- "$runtime/session"
    fi
    if [[ ${EXIT_CODE:-} == exited && ( ${EXIT_STATUS:-} == 77 || ${EXIT_STATUS:-} == 78 ) ]]; then
        operation=poweroff
        [[ $EXIT_STATUS != 78 ]] || operation=reboot
        sync
        systemctl --no-block "$operation"
    fi
    ;;
*) exit 2 ;;
esac
