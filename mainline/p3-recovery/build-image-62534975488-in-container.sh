#!/bin/bash
set -Eeuo pipefail
umask 077

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG

readonly IMAGE=/work/easyroms-p3-62534975488-v1.img
readonly SOURCE=/work/source
readonly MOUNT=/mnt/r46h-p3-fast-card
readonly IMAGE_SIZE=51683880448
readonly VOLUME_GUID=62534975-4880-4A4A-ACB7-625349754881
readonly VOLUME_SERIAL=0x62534975
readonly PAYLOADS=(
  r46h-v0.8-bootloader-handoff
  r46h-v0.9-adc-joystick-fix
  r46h-v0.10-adc-full-range
)

loop_device=
mounted=0
cleanup() {
  local status=$?
  trap - EXIT INT TERM HUP
  trap '' INT TERM HUP
  set +e
  if [[ "$mounted" -eq 1 ]]; then
    cd /
    /bin/umount "$MOUNT" >/dev/null 2>&1
  fi
  if [[ -n "$loop_device" ]]; then
    /sbin/losetup -d "$loop_device" >/dev/null 2>&1
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

[[ -f "$IMAGE" && ! -L "$IMAGE" && "$(stat -c '%s' "$IMAGE")" == "$IMAGE_SIZE" ]]
[[ -d "$SOURCE" && ! -L "$SOURCE" ]]
for payload in "${PAYLOADS[@]}"; do
  [[ -d "$SOURCE/$payload" && ! -L "$SOURCE/$payload" ]]
done
[[ "$(find "$SOURCE" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)" == \
  $'r46h-v0.10-adc-full-range\nr46h-v0.8-bootloader-handoff\nr46h-v0.9-adc-joystick-fix' ]]

mkfs.exfat -q -L EASYROMS -U "$VOLUME_GUID" -s 512 -c 32K -b 1M "$IMAGE"
tune.exfat -I "$VOLUME_SERIAL" "$IMAGE"
install -d -m 0700 "$MOUNT"
loop_device=$(losetup --find --show "$IMAGE")
[[ "$loop_device" =~ ^/dev/loop[0-9]+$ ]]
mount -t exfat -o rw,nosuid,nodev,noexec "$loop_device" "$MOUNT"
mounted=1
for payload in "${PAYLOADS[@]}"; do
  mkdir "$MOUNT/$payload"
  while IFS= read -r -d '' source; do
    name=${source##*/}
    [[ "$name" =~ ^[A-Za-z0-9._+-]+$ ]]
    cp --reflink=never --sparse=never --no-preserve=mode,ownership,timestamps,xattr \
      "$source" "$MOUNT/$payload/$name"
  done < <(find "$SOURCE/$payload" -mindepth 1 -maxdepth 1 -type f -print0 | sort -z)
done
sync -f "$MOUNT"
cd /
umount "$MOUNT"
mounted=0
fsck.exfat -n -v "$loop_device"
losetup -d "$loop_device"
loop_device=
sync -f "$IMAGE"
echo "R46H_P3_CONTAINER_BUILD result=pass image_size=$IMAGE_SIZE volume_guid=$VOLUME_GUID"
