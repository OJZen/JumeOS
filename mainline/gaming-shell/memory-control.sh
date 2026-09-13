#!/bin/bash
# Operator/agent CLI for the first memory experiment; no fstab or startup changes.
set -Eeuo pipefail
export LC_ALL=C
readonly state=/var/lib/r46h-memory
readonly swapfile=$state/swapfile
readonly zram=/dev/zram0
die() { echo "MEMORY_ERROR $*" >&2;exit 1; }
[[ $# -ge 1 ]] || die 'Use --check | --disk MiB | --disk-off | --zram MiB lz4|zstd | --zram-off'
[[ $(findmnt -rn -o UUID /) == d3130017-46a4-4d56-9001-000000000017 ]] || die identity
[[ $(cat /sys/class/block/mmcblk0/device/cid) == fe343253440000002000002d57019567 && $(cat /sys/class/block/mmcblk0/size) == 122138624 ]] || die identity
kernel=$(uname -r)
[[ $kernel == 6.12.99-r46h-mainline-v0.15-gaming-product || $kernel == 6.12.99-r46h-mainline-v0.18-zram-candidate ]] || die kernel
if [[ $1 == --check && $# == 1 ]]; then
    cat /proc/swaps
    awk '/^(MemTotal|MemAvailable|SwapTotal|SwapFree):/{print}' /proc/meminfo
    [[ ! -e /sys/block/zram0/mm_stat ]] || cat /sys/block/zram0/mm_stat
    exit 0
fi
[[ $EUID == 0 ]] || die root-required
[[ $(cat /sys/class/power_supply/rk817-charger/online) == 1 ]] || die external-power-required
busy=0
pgrep -u 1000 -f '(^|/)(retroarch|moonlight(-qt)?)([[:space:]]|$)' >/dev/null || busy=$?
[[ $busy == 1 ]] || die game-active-or-process-check-failed
[[ $(findmnt -rn -T /var/lib -o FSTYPE) == ext4 && $(findmnt -rn -T /var/lib -o UUID) == d3130017-46a4-4d56-9001-000000000017 ]] || die storage
if [[ ! -e $state && ! -L $state ]]; then
    install -d -o root -g root -m 700 "$state"
    (umask 077;printf 'r46h-memory-v1\n' > "$state/owner")
fi
[[ -d $state && ! -L $state && $(stat -c %u:%g:%a "$state") == 0:0:700 ]] || die state-directory
[[ -f $state/owner && ! -L $state/owner && $(cat "$state/owner") == r46h-memory-v1 ]] || die unknown-owner
umask 077
exec 9>"$state/lock"
flock -n 9 || die busy

active_used() { awk -v name="$1" '$1==name{print $4;found=1} END{if(!found)print -1}' /proc/swaps; }
size_bytes() {
    [[ $1 =~ ^[1-9][0-9]{1,3}$ ]] || return 1
    local ram
    ram=$(awk '/^MemTotal:/{print $2}' /proc/meminfo)
    [[ $ram =~ ^[0-9]+$ ]] || return 1
    (( $1 >= 64 && $1 <= 2048 && $1 * 1024 <= ram * 2 )) || return 1
    printf '%s\n' "$(( $1 * 1048576 ))"
}
can_disable() {
    local used=$1 available total reserve
    [[ $used =~ ^[0-9]+$ ]] || return 1
    available=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
    total=$(awk '/^MemTotal:/{print $2}' /proc/meminfo)
    [[ $available =~ ^[0-9]+$ && $total =~ ^[0-9]+$ ]] || return 1
    reserve=$((total/8));((reserve>=131072)) || reserve=131072
    (( available >= used + reserve ))
}
owned_file() {
    [[ -f $swapfile && ! -L $swapfile && $(stat -c %u:%g:%a:%h "$swapfile") == 0:0:600:1 ]] || return 1
    [[ -f $state/disk-owner && ! -L $state/disk-owner && $(cat "$state/disk-owner") == "$(stat -c %d:%i:%s "$swapfile")" ]]
}
case $1 in
--disk)
    [[ $# == 2 ]] || die arguments
    bytes=$(size_bytes "$2") || die size-range
    if [[ -e $swapfile || -L $swapfile ]]; then
        owned_file || die swapfile-identity
        [[ $(stat -c %s "$swapfile") == "$bytes" ]] || die 'disable the owned swap file before resizing'
        [[ $(active_used "$swapfile") == -1 ]] || { echo 'MEMORY_OK disk-already-active';exit 0; }
    else
        free=$(df -B1 --output=avail "$state" | tail -n 1 | tr -d ' ')
        [[ $free =~ ^[0-9]+$ ]] && (( free >= bytes + 536870912 )) || die disk-reserve
        temporary=$(mktemp "$state/.swap.XXXXXX")
        trap 'rm -f -- "${temporary:-}"' EXIT
        chmod 600 "$temporary"
        fallocate -l "$bytes" "$temporary"
        mkswap "$temporary" >/dev/null
        mv -T -- "$temporary" "$swapfile"
        stat -c %d:%i:%s "$swapfile" > "$state/disk-owner"
        trap - EXIT
    fi
    [[ $(blkid -p -s TYPE -o value "$swapfile") == swap ]] || die swap-signature
    swapon -p 10 "$swapfile"
    ;;
--disk-off)
    [[ $# == 1 ]] || die arguments
    [[ -e $swapfile || -L $swapfile ]] || { echo 'MEMORY_OK disk-absent';exit 0; }
    owned_file || die swapfile-identity
    used=$(active_used "$swapfile")
    if [[ $used != -1 ]]; then can_disable "$used" || die memory-reserve;swapoff "$swapfile";fi
    [[ $(active_used "$swapfile") == -1 ]] || die still-active
    rm -- "$swapfile"
    rm -- "$state/disk-owner"
    ;;
--zram)
    [[ $# == 3 && ( $3 == lz4 || $3 == zstd ) ]] || die arguments
    [[ $kernel == 6.12.99-r46h-mainline-v0.18-zram-candidate ]] || die zram-kernel-required
    bytes=$(size_bytes "$2") || die size-range
    [[ -e /sys/block/zram0/disksize ]] || modprobe zram num_devices=1
    [[ -b $zram && $(active_used "$zram") == -1 && $(cat /sys/block/zram0/disksize) == 0 ]] || die 'zram must be inactive and uninitialized'
    algorithms=" $(tr -d '[]' < /sys/block/zram0/comp_algorithm) "
    [[ $algorithms == *" $3 "* ]] || die algorithm
    printf '%s %s\n' "$(cat /proc/sys/kernel/random/boot_id)" "$(stat -Lc %d:%i /sys/block/zram0)" > "$state/zram-owner"
    printf '%s\n' "$3" > /sys/block/zram0/comp_algorithm
    printf '%s\n' "$bytes" > /sys/block/zram0/disksize
    [[ $(cat /sys/block/zram0/disksize) == "$bytes" ]] || die zram-readback
    mkswap "$zram" >/dev/null
    swapon -p 100 "$zram"
    ;;
--zram-off)
    [[ $# == 1 && -f $state/zram-owner && ! -L $state/zram-owner ]] || die zram-ownership
    [[ $(cat "$state/zram-owner") == "$(cat /proc/sys/kernel/random/boot_id) $(stat -Lc %d:%i /sys/block/zram0)" ]] || die zram-generation
    used=$(active_used "$zram")
    if [[ $used != -1 ]]; then can_disable "$used" || die memory-reserve;swapoff "$zram";fi
    [[ $(active_used "$zram") == -1 ]] || die still-active
    printf '1\n' > /sys/block/zram0/reset
    [[ $(cat /sys/block/zram0/disksize) == 0 ]] || die zram-reset
    rm -- "$state/zram-owner"
    ;;
*) die arguments ;;
esac
echo 'MEMORY_OK session-only; verify /proc/swaps and retain the receipt'
