#!/bin/bash
# Mount only the identified original Mono image, and release only our recorded mount.
set -Eeuo pipefail
[[ $# == 2 && ( $1 == --acquire || $1 == --release ) && $2 =~ ^r46h-(shell|wayland)-probe-[0-9]+\.service$ && $EUID == 0 ]] || exit 2
scope=/run/r46h-shell-probe
[[ $2 != r46h-wayland-probe-* ]] || scope=/run/r46h-wayland-probe
target=$scope/mono
record=/run/r46h-port-runtime
source_file=/roms/tools/PortMaster/libs/mono-6.12.0.122-aarch64.squashfs
owner_unit=$2
expected=107c61190ac1f8a60cd8a9ef94e7ae4e3f379bd9fca6efdadcb91e55fca55f83
if [[ $1 == --release ]]; then
  [[ -e $record || -L $record ]] || exit 0
  [[ ! -L $record && $(stat -c '%u:%a' "$record") == 0:700 && -f $record/mount-id && ! -L $record/mount-id ]] || exit 1
  [[ $(stat -c '%u:%a' "$record/mount-id") == 0:600 && -f $record/owner-unit && ! -L $record/owner-unit ]] || exit 1
  [[ $(stat -c '%u:%a' "$record/owner-unit") == 0:600 && $(cat "$record/owner-unit") == "$owner_unit" ]] || exit 1
  mount_id=$(cat "$record/mount-id")
  [[ $mount_id =~ ^[0-9]+$ && $(findmnt -rn -M "$target" -o ID) == "$mount_id" ]] || exit 1
  umount "$target" || exit 1
  rm -- "$record/mount-id" "$record/owner-unit"
  rmdir "$record" "$target"
  exit 0
fi
[[ $(uname -r) == 6.12.99-r46h-mainline-v0.15-gaming-product ]] || exit 1
[[ $(findmnt -rn -o UUID /) == d3130017-46a4-4d56-9001-000000000017 ]] || exit 1
[[ $(cat /sys/class/block/mmcblk0/device/cid) == fe343253440000002000002d57019567 ]] || exit 1
[[ $(cat /sys/class/block/mmcblk0/size) == 122138624 && ,$(findmnt -rn -o OPTIONS /roms), == *,ro,* ]] || exit 1
[[ -d $scope && ! -L $scope && $(stat -c '%u:%a' "$scope") == 0:755 ]] || exit 1
[[ ! -e $record && ! -L $record && ! -e $target && ! -L $target ]] || exit 1
[[ -f $source_file && ! -L $source_file && $(stat -c %s "$source_file") == 262057984 ]] || exit 1
[[ $(readlink -f "$source_file") == "$source_file" && $(sha256sum "$source_file" | cut -d ' ' -f 1) == "$expected" ]] || exit 1
umask 077
mkdir -m 700 "$record"
mounted=0
created_target=0
cleanup() {
  result=$?
  trap - EXIT
  if (( result != 0 )); then
    if (( mounted )); then umount "$target" || exit 1; fi
    rm -f -- "$record/mount-id" "$record/owner-unit"
    rmdir "$record"
    (( ! created_target )) || rmdir "$target"
  fi
  exit "$result"
}
trap cleanup EXIT
printf '%s\n' "$owner_unit" > "$record/owner-unit"
mkdir -m 755 "$target"
created_target=1
mount -t squashfs -o loop,ro,nodev,nosuid "$source_file" "$target"
mounted=1
findmnt -rn -M "$target" -o ID > "$record/mount-id"
[[ ,$(findmnt -rn -M "$target" -o OPTIONS), == *,ro,* && -x $target/bin/mono ]] || exit 1
