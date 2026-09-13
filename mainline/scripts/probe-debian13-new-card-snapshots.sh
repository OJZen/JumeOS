#!/bin/bash
set -euo pipefail

export PATH=/usr/bin:/bin:/usr/sbin:/sbin
export LC_ALL=C
export LANG=C

[[ "$#" -eq 9 ]]
expected_identifier=$1
boot_image=$2
easyroms_image=$3
expected_easyroms_size=$4
easyroms_policy=$5
expected_boot_uuid=$6
expected_easyroms_uuid=$7
receipt_dir=$8
result_path=$9

[[ "$expected_identifier" =~ ^disk[1-9][0-9]*$ ]]
[[ "$expected_boot_uuid" =~ ^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$ ]]
[[ "$expected_easyroms_uuid" =~ ^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$ ]]
[[ "$expected_easyroms_size" =~ ^[1-9][0-9]*$ ]]
[[ "$easyroms_policy" == blank || "$easyroms_policy" == three-payloads ]]

stage_dir=$(/usr/bin/dirname "$result_path")
[[ "$stage_dir" == /private/tmp/r46h-card-audit-root.* ]]
[[ "$(/usr/bin/stat -f "%u:%Lp" "$stage_dir")" == 0:700 ]]
[[ "$(/usr/bin/stat -f "%u:%Lp:%l:%z" "$boot_image")" == 0:600:1:117440512 ]]
[[ "$(/usr/bin/stat -f "%u:%Lp:%l:%z" "$easyroms_image")" == 0:600:1:$expected_easyroms_size ]]
[[ -d "$receipt_dir" && ! -L "$receipt_dir" ]]
[[ ! -e "$result_path" ]]

boot_mount="$stage_dir/boot-mount"
easyroms_mount="$stage_dir/easyroms-mount"
/bin/mkdir -m 0700 "$boot_mount" "$easyroms_mount"
boot_device=
easyroms_device=
probe_complete=0

cleanup() {
  local status=$?
  local cleanup_failed
  cleanup_failed=0
  trap - EXIT
  trap "" INT TERM HUP
  set +e
  if [[ -z "$boot_device" ]]; then
    boot_device=$(attached_device_from_plist "$stage_dir/boot-attach.plist" 2>/dev/null || true)
  fi
  if [[ -z "$easyroms_device" ]]; then
    easyroms_device=$(attached_device_from_plist "$stage_dir/easyroms-attach.plist" 2>/dev/null || true)
  fi
  /sbin/umount "$boot_mount" >/dev/null 2>&1 || true
  /sbin/umount "$easyroms_mount" >/dev/null 2>&1 || true
  if [[ -n "$boot_device" ]]; then
    /usr/bin/hdiutil detach "$boot_device" >/dev/null 2>&1 || cleanup_failed=1
  fi
  if [[ -n "$easyroms_device" ]]; then
    /usr/bin/hdiutil detach "$easyroms_device" >/dev/null 2>&1 || cleanup_failed=1
  fi
  /bin/rmdir "$boot_mount" "$easyroms_mount" >/dev/null 2>&1 || cleanup_failed=1
  if [[ "$probe_complete" -ne 1 ]]; then
    /bin/rm -f -- "$result_path" "$result_path.tmp" 2>/dev/null || true
  fi
  if [[ "$status" -eq 0 && "$cleanup_failed" -ne 0 ]]; then
    status=74
  fi
  exit "$status"
}
trap cleanup EXIT
trap "exit 130" INT
trap "exit 143" TERM
trap "exit 129" HUP

plist_value() {
  /usr/bin/plutil -extract "$2" raw -o - "$1"
}

attached_device_from_plist() {
  local plist
  local candidate
  plist=$1
  [[ -f "$plist" && ! -L "$plist" ]] || return 1
  candidate=$(plist_value "$plist" system-entities.0.dev-entry)
  [[ "$candidate" =~ ^/dev/disk[1-9][0-9]*$ ]]
  [[ "$candidate" != "/dev/$expected_identifier" ]]
  printf "%s\n" "$candidate"
}

attach_image() {
  local image
  local label
  local plist
  local attached_device
  image=$1
  label=$2
  plist="$stage_dir/${label}-attach.plist"
  /usr/bin/hdiutil attach \
    -readonly -nomount -noverify -noautofsck -plist \
    -imagekey diskimage-class=CRawDiskImage \
    "$image" > "$plist"
  attached_device=$(attached_device_from_plist "$plist")
  case "$label" in
    boot) boot_device=$attached_device ;;
    easyroms) easyroms_device=$attached_device ;;
    *) return 64 ;;
  esac
  /bin/cp -p "$plist" "$receipt_dir/${label}-attach.plist"
}

require_image_mount() {
  local plist
  local device
  local mount_point
  local expected_size
  local expected_name
  local expected_uuid
  plist=$1
  device=$2
  mount_point=$3
  expected_size=$4
  expected_name=$5
  expected_uuid=$6
  [[ "$(plist_value "$plist" DeviceIdentifier)" == "${device#/dev/}" ]]
  [[ "$(plist_value "$plist" ParentWholeDisk)" == "${device#/dev/}" ]]
  [[ "$(plist_value "$plist" WholeDisk)" == true ]]
  [[ "$(plist_value "$plist" BusProtocol)" == "Disk Image" ]]
  [[ "$(plist_value "$plist" VirtualOrPhysical)" == Virtual ]]
  [[ "$(plist_value "$plist" Size)" == "$expected_size" ]]
  [[ "$(plist_value "$plist" MountPoint)" == "$mount_point" ]]
  [[ "$(plist_value "$plist" VolumeName)" == "$expected_name" ]]
  [[ "$(plist_value "$plist" VolumeUUID)" == "$expected_uuid" ]]
  [[ "$(plist_value "$plist" Writable)" == false ]]
  [[ "$(plist_value "$plist" WritableMedia)" == false ]]
  [[ "$(plist_value "$plist" WritableVolume)" == false ]]
  /sbin/mount > "$receipt_dir/mounts.txt"
  /usr/bin/grep -F "$device on $mount_point (" "$receipt_dir/mounts.txt" >/dev/null
  /usr/bin/grep -F "$device on $mount_point (" "$receipt_dir/mounts.txt" |
    /usr/bin/grep -F "read-only" >/dev/null
}

require_anchor() {
  local mount_point
  local relative
  local expected_size
  local expected_hash
  local path
  local actual_size
  local actual_hash
  mount_point=$1
  relative=$2
  expected_size=$3
  expected_hash=$4
  path="$mount_point/$relative"
  [[ -f "$path" && ! -L "$path" ]]
  actual_size=$(/usr/bin/stat -f "%z" "$path")
  [[ "$actual_size" == "$expected_size" ]]
  actual_hash=$(/usr/bin/shasum -a 256 "$path")
  actual_hash=${actual_hash%% *}
  [[ "$actual_hash" == "$expected_hash" ]]
  printf "%s  %s\n" "$actual_hash" "$relative" >> "$receipt_dir/BOOT-ANCHORS.sha256"
}

: > "$receipt_dir/BOOT-ANCHORS.sha256"
: > "$receipt_dir/EASYROMS-ROOT.txt"

attach_image "$boot_image" boot
/sbin/fsck_msdos -n "/dev/r${boot_device#/dev/}" > "$receipt_dir/fsck-msdos.txt" 2>&1
/sbin/mount -t msdos -o rdonly,noowners,nobrowse "$boot_device" "$boot_mount"
/usr/sbin/diskutil info -plist "$boot_mount" > "$receipt_dir/boot-snapshot-mounted.plist"
require_image_mount \
  "$receipt_dir/boot-snapshot-mounted.plist" "$boot_device" "$boot_mount" \
  117440512 BOOT "$expected_boot_uuid"
require_anchor "$boot_mount" boot.ini 1427 cead3fbee0d5c42fddcd6f6d83839b82af791e1abf1dd0252d9850fb47dd33fb
require_anchor "$boot_mount" boot.ini.v0.8-bootloader-handoff 1427 cead3fbee0d5c42fddcd6f6d83839b82af791e1abf1dd0252d9850fb47dd33fb
require_anchor "$boot_mount" Image.mainline-v0.8-bootloader-handoff.gz 14920864 d7c7796c097fbe692412fb63d19c1f97c4b21f55ae2c3b1e8df324a739f166fa
require_anchor "$boot_mount" rk3326-r46h-mainline-v0.8-bootloader-handoff.dtb 49481 7259bac7bdd063fbaed987a0d5d2bf7066e02beaacc4440849b93d5f048e3dbc
require_anchor "$boot_mount" arkos4clone-uboot.dtb 59991 dd892bbd8dd1e5c51f7b3be2390faab4355e6932aef6a48b030b2591a7b0bf4c
require_anchor "$boot_mount" consoles/r46h/arkos4clone-uboot.dtb 59991 dd892bbd8dd1e5c51f7b3be2390faab4355e6932aef6a48b030b2591a7b0bf4c
[[ ! -e "$boot_mount/boot.ini.v0.4-dsi396" ]]
[[ ! -e "$boot_mount/Image.mainline-v0.4-dsi396.gz" ]]
[[ ! -e "$boot_mount/rk3326-r46h-mainline-v0.4-dsi396.dtb" ]]
/sbin/umount "$boot_mount"
/usr/bin/hdiutil detach "$boot_device" > "$receipt_dir/boot-detach.txt"
boot_device=
/bin/rm -f -- "$stage_dir/boot-attach.plist"

attach_image "$easyroms_image" easyroms
/sbin/fsck_exfat -n "/dev/r${easyroms_device#/dev/}" > "$receipt_dir/fsck-exfat.txt" 2>&1
/sbin/mount -t exfat -o rdonly,noowners,nobrowse "$easyroms_device" "$easyroms_mount"
/usr/sbin/diskutil info -plist "$easyroms_mount" > "$receipt_dir/easyroms-snapshot-mounted.plist"
require_image_mount \
  "$receipt_dir/easyroms-snapshot-mounted.plist" "$easyroms_device" "$easyroms_mount" \
  "$expected_easyroms_size" EASYROMS "$expected_easyroms_uuid"
easyroms_find="$receipt_dir/.easyroms-root.nul"
/usr/bin/find "$easyroms_mount" -mindepth 1 -maxdepth 1 -print0 > "$easyroms_find"
while IFS= read -r -d "" entry; do
  name=$(/usr/bin/basename "$entry")
  case "$name" in
    .Spotlight-V100|.fseventsd|.Trashes|.TemporaryItems)
      [[ -d "$entry" && ! -L "$entry" ]] || {
        echo "ERROR: unexpected EASYROMS metadata entry type: $name" >&2
        exit 65
      }
      ;;
    r46h-v0.8-bootloader-handoff|r46h-v0.9-adc-joystick-fix|r46h-v0.10-adc-full-range)
      [[ "$easyroms_policy" == three-payloads && -d "$entry" && ! -L "$entry" ]] || {
        echo "ERROR: unexpected EASYROMS payload entry: $name" >&2
        exit 65
      }
      ;;
    *) echo "ERROR: unexpected EASYROMS root entry: $name" >&2; exit 65 ;;
  esac
  printf "%s\n" "$name" >> "$receipt_dir/EASYROMS-ROOT.txt"
done < "$easyroms_find"
if [[ "$easyroms_policy" == three-payloads ]]; then
  for payload in r46h-v0.8-bootloader-handoff r46h-v0.9-adc-joystick-fix r46h-v0.10-adc-full-range; do
    /usr/bin/grep -Fqx "$payload" "$receipt_dir/EASYROMS-ROOT.txt"
  done
else
  if /usr/bin/grep -Eq '^r46h-v0\.(8|9|10)' "$receipt_dir/EASYROMS-ROOT.txt"; then
    echo "ERROR: unexpected EASYROMS payload in blank-policy snapshot" >&2
    exit 65
  fi
fi
/bin/rm -f -- "$easyroms_find"
[[ ! -e "$easyroms_find" ]]
/sbin/umount "$easyroms_mount"
/usr/bin/hdiutil detach "$easyroms_device" > "$receipt_dir/easyroms-detach.txt"
easyroms_device=
/bin/rm -f -- "$stage_dir/easyroms-attach.plist"

/bin/rmdir "$boot_mount" "$easyroms_mount"
printf "R46H_FILESYSTEM_PROBE result=pass boot_uuid=%s easyroms_uuid=%s\n" \
  "$expected_boot_uuid" "$expected_easyroms_uuid" > "$result_path.tmp"
/bin/mv -f -- "$result_path.tmp" "$result_path"
probe_complete=1
trap - EXIT INT TERM HUP
printf "R46H_FILESYSTEM_PROBE result=pass boot_uuid=%s easyroms_uuid=%s\n" \
  "$expected_boot_uuid" "$expected_easyroms_uuid"
