#!/bin/bash
# Install/remove only the narrow policy, after exact target identity. UDisks2
# itself is a distro system dependency, not a daemon shipped in the app archive.
set -Eeuo pipefail
[[ $EUID == 0 && $# == 1 && ( $1 == --check || $1 == --install || $1 == --remove ) ]] || exit 2
[[ $(uname -r) == 6.12.99-r46h-mainline-v0.15-gaming-product
   && $(cat /sys/class/block/mmcblk0/device/cid) == fe343253440000002000002d57019567
   && $(cat /sys/class/block/mmcblk0/size) == 122138624
   && $(findmnt -rn -o UUID /) == d3130018-46a4-4d56-9001-000000000018 ]] || exit 2
[[ $(id -u ark) == 1000 && -f /usr/share/polkit-1/actions/org.freedesktop.UDisks2.policy ]] || { echo 'Install the reviewed Debian udisks2 system dependency first.' >&2; exit 2; }
target=/etc/polkit-1/rules.d/49-jume-removable.rules
source=$(cd -- "$(dirname -- "$0")" && pwd -P)/49-jume-removable.rules
[[ ! -L $target && -f $source && ! -L $source ]]
[[ $(stat -c %u:%a "$source") == 0:644 || $(stat -c %u:%a "$source") == 0:444 ]] || { echo 'Seal the reviewed policy as root-owned first.' >&2;exit 2; }
if [[ $1 == --check ]]; then echo 'FILES_STORAGE_TARGET_OK';exit;fi
if [[ -e $target ]]; then cmp -s "$source" "$target" || { echo 'Existing policy differs; retained.' >&2;exit 2; };fi
if [[ $1 == --remove ]]; then [[ ! -f $target ]] || rm -- "$target";exit;fi
install -o root -g root -m 644 "$source" "$target"
echo 'FILES_USB_POLICY_INSTALLED no_system_mount_or_format_grant'
