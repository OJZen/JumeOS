#!/bin/bash
# Internal, temporary sysfs lease. systemd runs restore even if the GUI/probe dies.
set -Eeuo pipefail
[[ ( $# == 2 && ( $1 == --acquire || $1 == --restore ) && $2 =~ ^r46h-(shell|wayland)-probe-[0-9]+\.service$ || $# == 1 && $1 == --restore ) && $EUID == 0 ]] || exit 2
readonly unit=${2:-}
readonly lease=/run/r46h-device-lease
readonly control=/run/r46h-cpu-control
readonly base=$(cd -- "$(dirname -- "$0")" && pwd -P)
readonly cpu=/sys/devices/system/cpu/cpufreq/policy0
readonly light=/sys/class/backlight/backlight/brightness
readonly -a nodes=("$light" "$cpu/scaling_min_freq" "$cpu/scaling_max_freq" "$cpu/scaling_governor")
root_uuid=$(findmnt -rn -o UUID /)
[[ $(uname -r) == 6.12.99-r46h-mainline-v0.15-gaming-product
   && ( $root_uuid == d3130017-46a4-4d56-9001-000000000017 || $root_uuid == d3130018-46a4-4d56-9001-000000000018 ) ]]
[[ $(cat /sys/class/block/mmcblk0/device/cid) == fe343253440000002000002d57019567 && $(cat /sys/class/block/mmcblk0/size) == 122138624 ]]

restore() {
    [[ -e $lease ]] || return 0
    [[ -d $lease && ! -L $lease && $(stat -c %u:%g:%a "$lease") == 0:0:700 ]] || return 1
    # An unsuccessful second acquire must not restore another session's lease.
    [[ -z $unit || -f $lease/unit && ! -L $lease/unit && $(cat "$lease/unit") == "$unit" ]] || return 1
    [[ -f $lease/ready && ! -L $lease/ready ]] || return 1
    [[ $(cat "$lease/boot") == "$(cat /proc/sys/kernel/random/boot_id)" ]] || return 1
    if [[ -e $lease/helper.unit ]]; then
        [[ -f $lease/helper.unit && ! -L $lease/helper.unit ]] || return 1
        local helper_unit
        helper_unit=$(cat "$lease/helper.unit")
        [[ $helper_unit =~ ^r46h-(shell|wayland)-probe-[0-9]+-cpu\.service$ ]] || return 1
        systemctl stop "$helper_unit" || [[ $(systemctl show -p LoadState --value "$helper_unit") == not-found ]] || return 1
        if [[ -e $control || -L $control ]]; then
            [[ -d $control && ! -L $control ]] || return 1
            local control_meta
            control_meta=$(stat -c %u:%g:%a "$control")
            [[ $control_meta == "0:$(id -g ark):750" || $control_meta == 0:0:750 ]] || return 1
            if [[ -e $control/control.sock || -L $control/control.sock ]]; then
                [[ -S $control/control.sock && ! -L $control/control.sock && $(stat -c %u:%g:%a "$control/control.sock") == "0:$(id -g ark):660" ]] || return 1
                rm -- "$control/control.sock" || return 1
            fi
            rmdir -- "$control" || return 1
        fi
    fi
    local i meta value status=0 current minimum maximum attempt
    local -a values=() metadata=()
    for i in 0 1 2 3; do
        [[ -f $lease/$i.value && ! -L $lease/$i.value && -f $lease/$i.mode && ! -L $lease/$i.mode ]] || return 1
        value=$(cat "$lease/$i.value");meta=$(cat "$lease/$i.mode")
        [[ $meta =~ ^0:[0-9]+:[0-7]{3,4}$ && $value =~ ^[a-z0-9_]+$ ]] || return 1
        values+=("$value");metadata+=("$meta")
        [[ -f ${nodes[$i]} && ! -L ${nodes[$i]} ]] || return 1
    done
    [[ ${values[0]} =~ ^[0-9]+$ && ${values[1]} =~ ^[0-9]+$ && ${values[2]} =~ ^[0-9]+$ ]] || return 1
    minimum=${values[1]};maximum=${values[2]};current=$(cat "$cpu/scaling_min_freq")
    [[ $current =~ ^[0-9]+$ && $minimum -le $maximum ]] || return 1
    if (( maximum < current )); then
        printf '%s\n' "$minimum" > "${nodes[1]}" || status=1
        printf '%s\n' "$maximum" > "${nodes[2]}" || status=1
    else
        printf '%s\n' "$maximum" > "${nodes[2]}" || status=1
        printf '%s\n' "$minimum" > "${nodes[1]}" || status=1
    fi
    printf '%s\n' "${values[3]}" > "${nodes[3]}" || status=1
    printf '%s\n' "${values[0]}" > "${nodes[0]}" || status=1
    for i in 0 1 2 3; do
        IFS=: read -r owner group mode <<< "${metadata[$i]}"
        chown "$owner:$group" "${nodes[$i]}" || status=1
        chmod "$mode" "${nodes[$i]}" || status=1
        # CPUFreq QoS applies bounds from deferred work, not necessarily before the write returns.
        for attempt in {1..10}; do
            [[ $(cat "${nodes[$i]}") == "${values[$i]}" ]] && break
            sleep .01
        done
        [[ $(cat "${nodes[$i]}") == "${values[$i]}" && $(stat -c %u:%g:%a "${nodes[$i]}") == "${metadata[$i]}" ]] || status=1
    done
    if (( status == 0 )); then rm -rf -- "$lease"; fi
    printf 'DEVICE_LEASE_RESTORE status=%s\n' "$status"
    return "$status"
}
if [[ $1 == --restore ]]; then restore; exit; fi

[[ ! -e $lease && ! -L $lease && ! -e $control && ! -L $control && $(id -u ark) == 1000 ]]
[[ -f $base/cpu-control.py && ! -L $base/cpu-control.py && $(stat -c %u:%a "$base/cpu-control.py") == 0:755 ]]
[[ $(find /sys/devices/system/cpu/cpufreq -mindepth 1 -maxdepth 1 -name 'policy*' | wc -l) == 1 ]]
umask 077
mkdir -m 700 "$lease"
complete=0
cleanup() {
    result=$?
    trap - EXIT
    if (( result != 0 )); then
        if (( complete )); then restore || true; else rm -rf -- "$lease"; fi
    fi
    exit "$result"
}
trap cleanup EXIT
cat /proc/sys/kernel/random/boot_id > "$lease/boot"
printf '%s\n' "$unit" > "$lease/unit"
for i in 0 1 2 3; do
    [[ -f ${nodes[$i]} && ! -L ${nodes[$i]} && $(stat -c %u "${nodes[$i]}") == 0 ]]
    stat -c %u:%g:%a "${nodes[$i]}" > "$lease/$i.mode"
    cat "${nodes[$i]}" > "$lease/$i.value"
    [[ $(cat "$lease/$i.value") =~ ^[a-z0-9_]+$ ]]
done
touch "$lease/ready";complete=1
chown 1000:$(id -g ark) "$light";chmod 0600 "$light"
for node in "${nodes[@]:1}"; do chown root:root "$node";chmod 0644 "$node";done
helper_unit="${unit%.service}-cpu.service"
printf '%s\n' "$helper_unit" > "$lease/helper.unit"
mkdir -m 750 "$control";chown root:ark "$control"
systemd-run --quiet --collect --unit="$helper_unit" -p RuntimeMaxSec=7200 -p TimeoutStopSec=2 -- /usr/bin/python3 "$base/cpu-control.py" "$unit"
for attempt in {1..50}; do
    [[ ! -S $control/control.sock ]] || break
    sleep .02
done
[[ -S $control/control.sock && $(stat -c %u:%g:%a "$control/control.sock") == "0:$(id -g ark):660" ]]
printf 'DEVICE_LEASE_READY backlight=ark cpu=root helper=ready lifetime=transient-unit\n'
