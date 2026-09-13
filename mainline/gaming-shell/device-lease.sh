#!/bin/bash
# Internal, temporary sysfs lease. systemd runs restore even if the GUI/probe dies.
set -Eeuo pipefail
[[ ( $# == 2 && ( $1 == --acquire || $1 == --restore ) && $2 =~ ^r46h-(shell|wayland)-probe-[0-9]+\.service$ || $# == 1 && $1 == --restore ) && $EUID == 0 ]] || exit 2
readonly unit=${2:-}
readonly lease=/run/r46h-device-lease
readonly cpu=/sys/devices/system/cpu/cpufreq/policy0
readonly light=/sys/class/backlight/backlight/brightness
readonly -a nodes=("$light" "$cpu/scaling_min_freq" "$cpu/scaling_max_freq" "$cpu/scaling_governor")
[[ $(uname -r) == 6.12.99-r46h-mainline-v0.15-gaming-product && $(findmnt -rn -o UUID /) == d3130017-46a4-4d56-9001-000000000017 ]]
[[ $(cat /sys/class/block/mmcblk0/device/cid) == fe343253440000002000002d57019567 && $(cat /sys/class/block/mmcblk0/size) == 122138624 ]]

restore() {
    [[ -e $lease ]] || return 0
    [[ -d $lease && ! -L $lease && $(stat -c %u:%g:%a "$lease") == 0:0:700 ]] || return 1
    # An unsuccessful second acquire must not restore another session's lease.
    [[ -z $unit || -f $lease/unit && ! -L $lease/unit && $(cat "$lease/unit") == "$unit" ]] || return 1
    [[ -f $lease/ready && ! -L $lease/ready ]] || return 1
    [[ $(cat "$lease/boot") == "$(cat /proc/sys/kernel/random/boot_id)" ]] || return 1
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

[[ ! -e $lease && ! -L $lease && $(id -u ark) == 1000 ]]
[[ $(cat /sys/class/power_supply/rk817-charger/online) == 1 ]]
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
for node in "${nodes[@]}"; do chown 1000:1000 "$node";chmod 0600 "$node";done
printf 'DEVICE_LEASE_READY nodes=4 lifetime=transient-unit\n'
