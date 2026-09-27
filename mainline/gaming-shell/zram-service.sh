#!/bin/bash
# Opt-in installation only. Does not replace a kernel, edit boot files or enable swap now.
set -Eeuo pipefail
[[ $EUID == 0 && $# == 1 && ( $1 == --check || $1 == --install || $1 == --remove ) ]] || exit 2
base=$(cd -- "$(dirname -- "$0")" && pwd -P)
helper=/usr/local/sbin/r46h-memory-control
unit=/etc/systemd/system/r46h-zram.service
kernel=6.12.99-r46h-mainline-v0.19-zram-product
matching_target() {
    local source=$1 target=$2
    [[ ! -L $target ]] || return 1
    [[ ! -e $target ]] || { [[ -f $target ]] && cmp -s "$source" "$target"; }
}
for name in memory-control.sh r46h-zram.service; do
    [[ -f $base/$name && ! -L $base/$name ]] || exit 2
    case $(stat -c %u:%g:%a "$base/$name") in 0:0:644|0:0:755|0:0:444) ;; *) exit 2;; esac
done
# Reuse the memory controller's exact board/card/rootfs/kernel identity guard.
bash "$base/memory-control.sh" --check >/dev/null
matching_target "$base/memory-control.sh" "$helper" && matching_target "$base/r46h-zram.service" "$unit" || {
    echo 'Existing zram integration differs; retained.' >&2; exit 2;
}
if [[ $1 == --remove ]]; then
    [[ -e $helper || -e $unit ]] || exit 0
    active=$(systemctl show -p ActiveState --value r46h-zram.service)
    [[ $active == inactive || $active == failed ]] || { echo 'Stop the inactive-swap service before removal.' >&2; exit 2; }
    awk '$1=="/dev/zram0"{found=1} END{exit found?1:0}' /proc/swaps || {
        echo 'Use the guarded --zram-off before removing the service.' >&2; exit 2;
    }
    systemctl disable r46h-zram.service
    [[ ! -f $unit ]] || rm -- "$unit"
    [[ ! -f $helper ]] || rm -- "$helper"
    systemctl daemon-reload
    echo 'ZRAM_SERVICE_REMOVED no_kernel_or_boot_change'
    exit
fi
[[ -d /lib/modules/$kernel ]] && modinfo -k "$kernel" zram >/dev/null || {
    echo 'Install the verified v0.19 module closure first.' >&2; exit 2;
}
[[ $1 != --check ]] || { echo 'ZRAM_SERVICE_CHECK_PASS installation-only; boot and pressure proof still required'; exit; }
install -o root -g root -m 755 "$base/memory-control.sh" "$helper"
install -o root -g root -m 644 "$base/r46h-zram.service" "$unit"
systemctl daemon-reload
systemctl enable r46h-zram.service
echo 'ZRAM_SERVICE_INSTALLED exact-kernel next-boot only; current swap and boot selection unchanged'
