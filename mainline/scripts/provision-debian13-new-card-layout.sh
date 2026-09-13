#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$('/usr/bin/dirname' "$0")" && pwd -P)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd -P)

WHOLE_SIZE=31719424000
CURRENT_P1_OFFSET=16777216
CURRENT_P1_SIZE=31373393920
CURRENT_P1_CONTENT=Linux
PREFIX_SIZE=16777216
BOOT_OFFSET=16777216
BOOT_SIZE=117440512
ROOT_OFFSET=134217728
ROOT_SIZE=10716877312
EASYROMS_OFFSET=10851095040
EASYROMS_SIZE=20868328960
EASYROMS_DATA_SIZE=4358144
EASYROMS_ZERO_SIZE=16777216
EXPECTED_P3_SECTORS=40758455

ASSET_DIR="$REPO_ROOT/mainline/out/r46h-debian13-new-card-31719424000-v0.1"
PREFIX="$ASSET_DIR/prefix-g92-new-card.bin"
PREFIX_SHA256=97ede10075b3257c638a04b3044c9dda2d8dd9adc6f6fee3be7b004a31fb135e
BOOT="$ASSET_DIR/boot-p1-v0.8.img"
BOOT_SHA256=b701da77349d3514c65fcfe992434a648ca8678b661c47cb4d6bd997e103f017
ROOT="$REPO_ROOT/mainline/out/r46h-debian13-p2-mvp-v0.1/r46h-debian13-p2-mvp-v0.1.ext4"
ROOT_SHA256=6a4254a8e66c110405cf068317da5922bb5ddfe2a02535d1a381fe1303876c96
EASYROMS="$ASSET_DIR/easyroms-p3.sparse.exfat"
EASYROMS_DATA_SHA256=9e3e27c0859ba273e44a6709a3b62d8f4968dc12e061df019f137202672cf6bb
readonly TOOL="$REPO_ROOT/mainline/out/r46h-card-agent/bin/r46h-card-layout-provision"
readonly TOOL_SUM="$REPO_ROOT/mainline/out/r46h-card-agent/bin/r46h-card-layout-provision.sha256"
readonly TOOL_SOURCE="$REPO_ROOT/mainline/tools/r46h-card-agent/Sources/R46HCardLayoutProvision/main.c"
readonly TOOL_SOURCE_RECEIPT_PATH=../../../tools/r46h-card-agent/Sources/R46HCardLayoutProvision/main.c
RECEIPT_PARENT="$REPO_ROOT/mainline/out/r46h-new-card-layout-receipts"

DEVICE=
CONFIRM_DEVICE=
LAYOUT=compact-31719424000
ASSET_MANIFEST_SHA256=
TARGET_BEFORE_LAYOUT=

usage() {
  /bin/cat <<'EOF'
usage: mainline/scripts/provision-debian13-new-card-layout.sh \
  --device /dev/diskN --confirm-device /dev/diskN
  [--layout fast-card-62534975488 --asset-manifest-sha256 HASH \
   --target-before-layout factory-exfat-16m|factory-fat32-1m]

This erases the selected card and writes the R46H g92 prefix, v0.8 BOOT,
Debian 13 root, and blank EASYROMS metadata. Every byte of BOOT and root is
read back before the result is ejected; it remains safe_to_boot=no until a
separate post-reinsert identity audit passes.
EOF
}

while (($#)); do
  case "$1" in
    --device)
      (($# >= 2)) || { usage >&2; exit 64; }
      DEVICE=$2
      shift 2
      ;;
    --confirm-device)
      (($# >= 2)) || { usage >&2; exit 64; }
      CONFIRM_DEVICE=$2
      shift 2
      ;;
    --layout)
      (($# >= 2)) || { usage >&2; exit 64; }
      LAYOUT=$2
      shift 2
      ;;
    --asset-manifest-sha256)
      (($# >= 2)) || { usage >&2; exit 64; }
      ASSET_MANIFEST_SHA256=$2
      shift 2
      ;;
    --target-before-layout)
      (($# >= 2)) || { usage >&2; exit 64; }
      TARGET_BEFORE_LAYOUT=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 64
      ;;
  esac
done

[[ "$DEVICE" =~ ^/dev/disk[1-9][0-9]*$ && "$DEVICE" == "$CONFIRM_DEVICE" ]] || {
  echo "ERROR: device confirmation mismatch" >&2
  exit 64
}
[[ "$DEVICE" != /dev/disk6 ]] || { echo "ERROR: refusing known 1 TB workspace disk" >&2; exit 64; }

case "$LAYOUT" in
  compact-31719424000)
    [[ -z "$ASSET_MANIFEST_SHA256" ]] || { echo "ERROR: compact layout does not use an asset manifest" >&2; exit 64; }
    [[ -z "$TARGET_BEFORE_LAYOUT" ]] || { echo "ERROR: compact layout does not use a target-before layout" >&2; exit 64; }
    ;;
  fast-card-62534975488)
    [[ "$ASSET_MANIFEST_SHA256" =~ ^[0-9a-f]{64}$ ]] || { echo "ERROR: fast-card layout requires a pinned asset manifest" >&2; exit 64; }
    WHOLE_SIZE=62534975488
    case "$TARGET_BEFORE_LAYOUT" in
      factory-exfat-16m)
        CURRENT_P1_OFFSET=16777216
        CURRENT_P1_SIZE=62518198272
        CURRENT_P1_CONTENT=Windows_NTFS
        ;;
      factory-fat32-1m)
        CURRENT_P1_OFFSET=1048576
        CURRENT_P1_SIZE=62533926912
        CURRENT_P1_CONTENT=Windows_FAT_32
        ;;
      *)
        echo "ERROR: fast-card layout requires an exact target-before layout" >&2
        exit 64
        ;;
    esac
    EASYROMS_SIZE=51683880448
    EASYROMS_DATA_SIZE=$EASYROMS_SIZE
    EASYROMS_ZERO_SIZE=0
    EXPECTED_P3_SECTORS=100945079
    ASSET_DIR="$REPO_ROOT/mainline/out/r46h-fast-card-62534975488-v1"
    PREFIX="$ASSET_DIR/00-prefix-g92-mbr.bin"
    PREFIX_SHA256=3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3
    BOOT="$ASSET_DIR/01-boot-p1.img"
    BOOT_SHA256=88c6d614984791b891e63068ea687dabe28eb80c905a2aa9c6dd34409b24f86d
    ROOT="$ASSET_DIR/02-debian13-root-p2.img"
    ROOT_SHA256=dba5ff14364aa32b2d5930a055182a7f49c2bea0e2a0eb8cc76d1097b37c4c3e
    EASYROMS="$ASSET_DIR/03-easyroms-p3.img"
    RECEIPT_PARENT="$REPO_ROOT/mainline/out/r46h-fast-card-layout-receipts"
    manifest="$ASSET_DIR/ASSET-MANIFEST"
    [[ -f "$manifest" && ! -L "$manifest" ]] || { echo "ERROR: missing fast-card asset manifest" >&2; exit 66; }
    actual_manifest=$(/usr/bin/shasum -a 256 "$manifest")
    actual_manifest=${actual_manifest%% *}
    [[ "$actual_manifest" == "$ASSET_MANIFEST_SHA256" ]] || { echo "ERROR: fast-card asset manifest SHA-256 mismatch" >&2; exit 65; }
    EASYROMS_DATA_SHA256=$(/usr/bin/awk '$1 == "easyroms_sha256" { print $2 }' "$manifest")
    [[ "$EASYROMS_DATA_SHA256" =~ ^[0-9a-f]{64}$ &&
       "$(/usr/bin/grep -Ec '^easyroms_sha256 [0-9a-f]{64}$' "$manifest")" == 1 ]] || { echo "ERROR: malformed fast-card asset manifest" >&2; exit 65; }
    ;;
  *)
    echo "ERROR: unsupported layout: $LAYOUT" >&2
    exit 64
    ;;
esac

require_source() {
  local path=$1 expected_size=$2 expected_hash=$3 label=$4 actual_size actual_hash
  [[ -f "$path" && ! -L "$path" ]] || { echo "ERROR: missing $label" >&2; exit 66; }
  actual_size=$(/usr/bin/stat -f '%z' "$path")
  [[ "$actual_size" == "$expected_size" ]] || { echo "ERROR: $label size mismatch" >&2; exit 65; }
  actual_hash=$(/usr/bin/shasum -a 256 "$path")
  actual_hash=${actual_hash%% *}
  [[ "$actual_hash" == "$expected_hash" ]] || { echo "ERROR: $label SHA-256 mismatch" >&2; exit 65; }
}

require_source "$PREFIX" "$PREFIX_SIZE" "$PREFIX_SHA256" "g92 prefix"
require_source "$BOOT" "$BOOT_SIZE" "$BOOT_SHA256" "v0.8 BOOT image"
require_source "$ROOT" "$ROOT_SIZE" "$ROOT_SHA256" "Debian 13 root image"
[[ -f "$EASYROMS" && ! -L "$EASYROMS" ]] || { echo "ERROR: missing EASYROMS image" >&2; exit 66; }
[[ "$(/usr/bin/stat -f '%z' "$EASYROMS")" == "$EASYROMS_SIZE" ]] || {
  echo "ERROR: EASYROMS logical size mismatch" >&2
  exit 65
}
if [[ "$EASYROMS_DATA_SIZE" == "$EASYROMS_SIZE" ]]; then
  easyroms_data_hash=$(/usr/bin/shasum -a 256 "$EASYROMS")
  easyroms_data_hash=${easyroms_data_hash%% *}
else
  easyroms_data_hash=$(/bin/dd if="$EASYROMS" bs="$EASYROMS_DATA_SIZE" count=1 2>/dev/null | /usr/bin/shasum -a 256)
  easyroms_data_hash=${easyroms_data_hash%% *}
fi
[[ "$easyroms_data_hash" == "$EASYROMS_DATA_SHA256" ]] || {
  echo "ERROR: EASYROMS metadata SHA-256 mismatch" >&2
  exit 65
}

[[ -f "$TOOL" && ! -L "$TOOL" && -f "$TOOL_SUM" && ! -L "$TOOL_SUM" &&
   -f "$TOOL_SOURCE" && ! -L "$TOOL_SOURCE" ]] || {
  echo "ERROR: build the pinned layout provision tool first" >&2
  exit 66
}
expected_tool=$(/usr/bin/awk '$2 == "r46h-card-layout-provision" { print $1 }' "$TOOL_SUM")
expected_tool_source=$(/usr/bin/awk -v path="$TOOL_SOURCE_RECEIPT_PATH" '$2 == path { print $1 }' "$TOOL_SUM")
actual_tool=$(/usr/bin/shasum -a 256 "$TOOL")
actual_tool=${actual_tool%% *}
actual_tool_source=$(/usr/bin/shasum -a 256 "$TOOL_SOURCE")
actual_tool_source=${actual_tool_source%% *}
[[ "$expected_tool" =~ ^[0-9a-f]{64}$ && "$actual_tool" == "$expected_tool" &&
   "$expected_tool_source" =~ ^[0-9a-f]{64}$ && "$actual_tool_source" == "$expected_tool_source" ]] || {
  echo "ERROR: layout provision tool SHA-256 mismatch" >&2
  exit 65
}
tool_size=$(/usr/bin/stat -f '%z' "$TOOL")
[[ "$tool_size" =~ ^[1-9][0-9]*$ && "$tool_size" -le 16777216 ]] || {
  echo "ERROR: unsafe layout provision tool size" >&2
  exit 65
}

/bin/mkdir -p "$RECEIPT_PARENT"
/bin/chmod 0700 "$RECEIPT_PARENT"
receipt_dir=$(/usr/bin/mktemp -d "$RECEIPT_PARENT/.r46h-new-card-layout.XXXXXX")
/bin/chmod 0700 "$receipt_dir"

echo "R46H new-card layout provisioning"
echo "target=$DEVICE layout=$LAYOUT exact_size=$WHOLE_SIZE"
echo "This permanently replaces the current partition table and data on that card."
echo "The 1 TB /dev/disk6 workspace disk is explicitly rejected."
echo "One administrator authorization starts the fixed supervised worker."

# The root worker is data here; its variables expand only in the privileged shell.
# shellcheck disable=SC2016
ROOT_BOOTSTRAP='
set -euo pipefail

[[ "$#" -eq 30 ]]
device=$1
raw_device=$2
expected_identifier=$3
whole_size=$4
current_p1_offset=$5
current_p1_size=$6
current_p1_content=$7
expected_p3_sectors=$8
tool=$9
tool_sha=${10}
tool_size=${11}
expected_uid=${12}
prefix=${13}
prefix_size=${14}
prefix_sha=${15}
boot=${16}
boot_offset=${17}
boot_size=${18}
boot_sha=${19}
root=${20}
root_offset=${21}
root_size=${22}
root_sha=${23}
easyroms=${24}
easyroms_offset=${25}
easyroms_size=${26}
easyroms_data_size=${27}
easyroms_data_sha=${28}
easyroms_zero_size=${29}
receipt_dir=${30}

[[ "${SUDO_UID:-}" == "$expected_uid" && "$expected_uid" =~ ^[1-9][0-9]*$ ]]
[[ "$device" == "/dev/$expected_identifier" && "$raw_device" == "/dev/r$expected_identifier" ]]
receipt_identity=$(/usr/bin/stat -f "%u:%g:%Lp" "$receipt_dir")
IFS=: read -r receipt_uid receipt_gid receipt_mode <<< "$receipt_identity"
[[ "$receipt_uid" == "$expected_uid" && "$receipt_gid" =~ ^[0-9]+$ && "$receipt_mode" == 700 ]]
umask 077

stage_dir=$(/usr/bin/mktemp -d /private/tmp/r46h-card-layout-root.XXXXXX)
staged_tool="$stage_dir/r46h-card-layout-provision"
worker_pid=
worker_result=127
pending_signal=

forward_worker_signal() {
  local signal_name
  signal_name=$1
  pending_signal=$signal_name
  if [[ -n "$worker_pid" ]]; then
    /bin/kill "-$signal_name" "$worker_pid" 2>/dev/null || true
  fi
}

wait_for_worker() {
  local observed_status
  local current_status
  observed_status=127
  while /bin/kill -0 "$worker_pid" 2>/dev/null; do
    wait "$worker_pid"
    current_status=$?
    if [[ "$current_status" -ne 127 ]]; then
      observed_status=$current_status
    fi
  done
  wait "$worker_pid" 2>/dev/null
  current_status=$?
  if [[ "$current_status" -ne 127 ]]; then
    observed_status=$current_status
  fi
  worker_result=$observed_status
  worker_pid=
}

cleanup() {
  local status=$?
  trap - EXIT
  trap "" INT TERM HUP
  set +e
  if [[ -n "$worker_pid" ]]; then
    wait_for_worker
    if [[ "$status" -eq 0 && "$worker_result" -ne 0 ]]; then
      status=$worker_result
    fi
  fi
  /bin/rm -f -- "$staged_tool" 2>/dev/null || true
  /bin/rmdir -- "$stage_dir" 2>/dev/null || true
  if ! /usr/sbin/chown -R "$expected_uid:$receipt_gid" "$receipt_dir"; then
    status=74
  fi
  exit "$status"
}
trap cleanup EXIT

/usr/bin/install -o root -g wheel -m 0700 "$tool" "$staged_tool"
[[ "$(/usr/bin/stat -f "%u:%Lp:%z" "$staged_tool")" == "0:700:$tool_size" ]]
staged_hash=$(/usr/bin/shasum -a 256 "$staged_tool")
staged_hash=${staged_hash%% *}
[[ "$staged_hash" == "$tool_sha" ]]

whole_plist="$receipt_dir/device-before.plist"
p1_plist="$receipt_dir/partition-before.plist"
/usr/sbin/diskutil info -plist "$device" > "$whole_plist"
/usr/sbin/diskutil info -plist "${device}s1" > "$p1_plist"

plist_value() {
  /usr/bin/plutil -extract "$2" raw -o - "$1"
}

[[ "$(plist_value "$whole_plist" DeviceIdentifier)" == "$expected_identifier" ]]
[[ "$(plist_value "$whole_plist" WholeDisk)" == true ]]
[[ "$(plist_value "$whole_plist" Content)" == FDisk_partition_scheme ]]
[[ "$(plist_value "$whole_plist" Size)" == "$whole_size" ]]
[[ "$(plist_value "$whole_plist" DeviceBlockSize)" == 512 ]]
[[ "$(plist_value "$whole_plist" BusProtocol)" == USB ]]
[[ "$(plist_value "$whole_plist" Internal)" == false ]]
[[ "$(plist_value "$whole_plist" RemovableMedia)" == true ]]
[[ "$(plist_value "$whole_plist" VirtualOrPhysical)" == Physical ]]

[[ "$(plist_value "$p1_plist" DeviceIdentifier)" == "${expected_identifier}s1" ]]
[[ "$(plist_value "$p1_plist" ParentWholeDisk)" == "$expected_identifier" ]]
[[ "$(plist_value "$p1_plist" PartitionMapPartitionOffset)" == "$current_p1_offset" ]]
[[ "$(plist_value "$p1_plist" Size)" == "$current_p1_size" ]]
[[ "$(plist_value "$p1_plist" Content)" == "$current_p1_content" ]]
[[ ! -e "${device}s2" && ! -e "${device}s3" && ! -e "${device}s4" ]]

/usr/sbin/diskutil unmountDisk "$device" > "$receipt_dir/unmount-before.txt"
/usr/sbin/fdisk "$device" > "$receipt_dir/fdisk-before.txt"
prefix_before_copy="$receipt_dir/.prefix-before.tmp"
/bin/dd if="$raw_device" of="$prefix_before_copy" bs=1048576 count=16 \
  2> "$receipt_dir/prefix-before-read.txt"
[[ "$(/usr/bin/stat -f "%z" "$prefix_before_copy")" == "$prefix_size" ]]
target_prefix_before=$(/usr/bin/shasum -a 256 "$prefix_before_copy")
target_prefix_before=${target_prefix_before%% *}
[[ "$target_prefix_before" =~ ^[0-9a-f]{64}$ ]]
printf "%s  prefix-before\n" "$target_prefix_before" > "$receipt_dir/prefix-before.sha256"
/bin/rm -f -- "$prefix_before_copy"
[[ ! -e "$prefix_before_copy" ]]

status_file="$receipt_dir/WRITE-STATUS.json"
printf "%s\n" "{\"format_version\":1,\"state\":\"PROVISION_IN_PROGRESS\",\"safe_to_boot\":false,\"device\":\"$device\"}" > "$status_file"
/bin/sync

trap "forward_worker_signal INT" INT
trap "forward_worker_signal TERM" TERM
trap "forward_worker_signal HUP" HUP
set +e
"$staged_tool" \
  "$raw_device" "$whole_size" \
  "$prefix" "$prefix_size" "$prefix_sha" \
  "$boot" "$boot_offset" "$boot_size" "$boot_sha" \
  "$root" "$root_offset" "$root_size" "$root_sha" \
  "$easyroms" "$easyroms_offset" "$easyroms_size" \
  "$easyroms_data_size" "$easyroms_data_sha" "$easyroms_zero_size" \
  "$target_prefix_before" \
  > "$receipt_dir/layout-provision.log" 2>&1 &
worker_pid=$!
if [[ -n "$pending_signal" ]]; then
  /bin/kill "-$pending_signal" "$worker_pid" 2>/dev/null || true
fi
wait_for_worker
worker_status=$worker_result
set -e
/bin/cat "$receipt_dir/layout-provision.log" || true
if [[ "$worker_status" -ne 0 ]]; then
  printf "%s\n" "{\"format_version\":1,\"state\":\"PROVISION_FAILED\",\"safe_to_boot\":false,\"device\":\"$device\",\"worker_status\":$worker_status}" > "$status_file"
  /bin/sync
  exit "$worker_status"
fi
worker_marker="R46H_LAYOUT result=pass state=MEDIA_WRITE_COMPLETE safe_to_boot=no card_state=ejected next=reinsert-and-audit"
worker_marker_count=$(/usr/bin/grep -Fxc "$worker_marker" "$receipt_dir/layout-provision.log" || true)
[[ "$worker_marker_count" == 1 ]]
[[ ! -e "$device" && ! -e "$raw_device" ]]

printf "%s\n" "{\"format_version\":1,\"state\":\"MEDIA_WRITE_COMPLETE\",\"safe_to_boot\":false,\"device\":\"$device\",\"next\":\"reinsert-and-audit\"}" > "$status_file"
/bin/sync
/usr/bin/touch "$receipt_dir/EJECTED"
/bin/sync
/bin/rm -f -- "$staged_tool"
/bin/rmdir -- "$stage_dir"
/usr/sbin/chown -R "$expected_uid:$receipt_gid" "$receipt_dir"
trap - EXIT INT TERM HUP
printf "PASS: new R46H media written and fully read back; post-reinsert audit is still required.\n"
printf "SAFE_TO_BOOT=no\nRECEIPT_DIR=%s\n" "$receipt_dir"
'

raw_device="/dev/r${DEVICE#/dev/}"
identifier=${DEVICE#/dev/}
exec /usr/bin/sudo -- /bin/bash -c "$ROOT_BOOTSTRAP" r46h-new-card-layout-root \
  "$DEVICE" "$raw_device" "$identifier" "$WHOLE_SIZE" "$CURRENT_P1_OFFSET" "$CURRENT_P1_SIZE" \
  "$CURRENT_P1_CONTENT" "$EXPECTED_P3_SECTORS" \
  "$TOOL" "$expected_tool" "$tool_size" "$(/usr/bin/id -u)" \
  "$PREFIX" "$PREFIX_SIZE" "$PREFIX_SHA256" \
  "$BOOT" "$BOOT_OFFSET" "$BOOT_SIZE" "$BOOT_SHA256" \
  "$ROOT" "$ROOT_OFFSET" "$ROOT_SIZE" "$ROOT_SHA256" \
  "$EASYROMS" "$EASYROMS_OFFSET" "$EASYROMS_SIZE" \
  "$EASYROMS_DATA_SIZE" "$EASYROMS_DATA_SHA256" "$EASYROMS_ZERO_SIZE" \
  "$receipt_dir"
