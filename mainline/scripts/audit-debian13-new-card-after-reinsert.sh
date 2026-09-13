#!/bin/bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(/usr/bin/dirname "$0")" && pwd -P)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../.." && pwd -P)

WHOLE_SIZE=31719424000
PREFIX_SIZE=16777216
PREFIX_SHA256=97ede10075b3257c638a04b3044c9dda2d8dd9adc6f6fee3be7b004a31fb135e
BOOT_OFFSET=16777216
BOOT_SIZE=117440512
BOOT_IMAGE_SHA256=b701da77349d3514c65fcfe992434a648ca8678b661c47cb4d6bd997e103f017
BOOT_UUID=575BC58C-96FA-3E4F-958B-7A30D5210C3D
ROOT_OFFSET=134217728
ROOT_SIZE=10716877312
ROOT_SHA256=6a4254a8e66c110405cf068317da5922bb5ddfe2a02535d1a381fe1303876c96
EASYROMS_OFFSET=10851095040
EASYROMS_SIZE=20868328960
EASYROMS_SHA256=-
EASYROMS_HEAD_SIZE=16777216
EASYROMS_HEAD_SHA256=-
EASYROMS_UUID=E1F5295C-4B12-A54A-ACB7-317194240001
EASYROMS_POLICY=blank
EXPECTED_P3_SECTORS=40758455
AUDIT_LEVEL=
RAW_BYTES_READ=21869962240
PRIOR_WRITE_STATUS_SHA256=-
PRIOR_WRITE_LOG_SHA256=-
P3_BUILD_STATUS_SHA256=-
P3_RAW_VERIFY_SHA256=-
EASYROMS_QUICK_IMMUTABLE_SHA256=-
readonly TOOL="$REPO_ROOT/mainline/out/r46h-card-agent/bin/r46h-card-layout-provision"
readonly TOOL_SUM="$REPO_ROOT/mainline/out/r46h-card-agent/bin/r46h-card-layout-provision.sha256"
readonly TOOL_SOURCE="$REPO_ROOT/mainline/tools/r46h-card-agent/Sources/R46HCardLayoutProvision/main.c"
readonly TOOL_SOURCE_RECEIPT_PATH=../../../tools/r46h-card-agent/Sources/R46HCardLayoutProvision/main.c
readonly PROBE="$REPO_ROOT/mainline/scripts/probe-debian13-new-card-snapshots.sh"
readonly ROOT_RECEIPT_PARENT=/private/tmp

DEVICE=
CONFIRM_DEVICE=
LAYOUT=compact-31719424000
ASSET_MANIFEST_SHA256=
PRIOR_WRITE_RECEIPT_DIR=
EXPECTED_PRIOR_WRITE_STATUS_SHA256=
EXPECTED_PRIOR_WRITE_LOG_SHA256=

usage() {
  /bin/cat <<'EOF'
usage: mainline/scripts/audit-debian13-new-card-after-reinsert.sh \
  --device /dev/diskN --confirm-device /dev/diskN
  [--layout fast-card-62534975488 --asset-manifest-sha256 HASH]
  [--audit-level full|quick]
  [--prior-write-receipt-dir DIR --prior-write-status-sha256 HASH
   --prior-write-log-sha256 HASH]

This post-reinsert audit never opens the card for writing and never repairs a
filesystem. One C process keeps a whole-disk claim and one read-only raw file
descriptor across raw hashing, offline snapshot checks, final rehashing, and
eject. Unmounting can flush metadata previously dirtied by macOS automount.

The fast-card layout defaults to full. Its explicit quick level still hashes
all boot-critical bytes, but replaces two complete p3 reads with a pinned
immutable exFAT proof: boot regions, the original FAT entries, original root
entries, and every payload directory/data cluster must remain byte-exact.
The complete 256 MiB metadata window is also read twice consistently and its
offline filesystem permits only known macOS automount metadata additions.
Quick requires the prior full-write/readback receipt and exact p3 allocation
proof; its receipt never claims full p3 media coverage.
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
    --audit-level)
      (($# >= 2)) || { usage >&2; exit 64; }
      AUDIT_LEVEL=$2
      shift 2
      ;;
    --prior-write-receipt-dir)
      (($# >= 2)) || { usage >&2; exit 64; }
      PRIOR_WRITE_RECEIPT_DIR=$2
      shift 2
      ;;
    --prior-write-status-sha256)
      (($# >= 2)) || { usage >&2; exit 64; }
      EXPECTED_PRIOR_WRITE_STATUS_SHA256=$2
      shift 2
      ;;
    --prior-write-log-sha256)
      (($# >= 2)) || { usage >&2; exit 64; }
      EXPECTED_PRIOR_WRITE_LOG_SHA256=$2
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
[[ "$DEVICE" != /dev/disk6 ]] || {
  echo "ERROR: refusing known 1 TB workspace disk" >&2
  exit 64
}

case "$LAYOUT" in
  compact-31719424000)
    [[ -z "$ASSET_MANIFEST_SHA256" ]] || { echo "ERROR: compact audit does not use an asset manifest" >&2; exit 64; }
    [[ -z "$AUDIT_LEVEL" || "$AUDIT_LEVEL" == quick ]] || { echo "ERROR: compact layout only supports its head-bound quick audit" >&2; exit 64; }
    AUDIT_LEVEL=compact-head
    ;;
  fast-card-62534975488)
    [[ -n "$AUDIT_LEVEL" ]] || AUDIT_LEVEL=full
    [[ "$AUDIT_LEVEL" == full || "$AUDIT_LEVEL" == quick ]] || { echo "ERROR: fast-card audit level must be full or quick" >&2; exit 64; }
    [[ "$ASSET_MANIFEST_SHA256" =~ ^[0-9a-f]{64}$ ]] || { echo "ERROR: fast-card audit requires a pinned asset manifest" >&2; exit 64; }
    ASSET_DIR="$REPO_ROOT/mainline/out/r46h-fast-card-62534975488-v1"
    manifest="$ASSET_DIR/ASSET-MANIFEST"
    [[ -f "$manifest" && ! -L "$manifest" ]] || { echo "ERROR: missing fast-card asset manifest" >&2; exit 66; }
    actual_manifest=$(/usr/bin/shasum -a 256 "$manifest")
    actual_manifest=${actual_manifest%% *}
    [[ "$actual_manifest" == "$ASSET_MANIFEST_SHA256" ]] || { echo "ERROR: fast-card asset manifest mismatch" >&2; exit 65; }
    WHOLE_SIZE=62534975488
    PREFIX_SHA256=3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3
    BOOT_IMAGE_SHA256=88c6d614984791b891e63068ea687dabe28eb80c905a2aa9c6dd34409b24f86d
    ROOT_SHA256=dba5ff14364aa32b2d5930a055182a7f49c2bea0e2a0eb8cc76d1097b37c4c3e
    EASYROMS_SIZE=51683880448
    EASYROMS_HEAD_SIZE=268435456
    EASYROMS_HEAD_SHA256=d7923cfdb8b9b287a1946548699a9933234c50e89b51ac95f584f7f6ac90340e
    EASYROMS_QUICK_IMMUTABLE_SHA256=1b761a61e89c46c49ab78c1634c25d22112c26f990c13daedf73791ca47aba7a
    full_easyroms_sha=$(/usr/bin/awk '$1 == "easyroms_sha256" { print $2 }' "$manifest")
    EASYROMS_UUID=75495362-8048-4A4A-ACB7-625349754881
    EASYROMS_POLICY=three-payloads
    EXPECTED_P3_SECTORS=100945079
    [[ "$full_easyroms_sha" =~ ^[0-9a-f]{64}$ ]] || { echo "ERROR: malformed fast-card p3 binding" >&2; exit 65; }
    if [[ "$AUDIT_LEVEL" == full ]]; then
      [[ -z "$PRIOR_WRITE_RECEIPT_DIR$EXPECTED_PRIOR_WRITE_STATUS_SHA256$EXPECTED_PRIOR_WRITE_LOG_SHA256" ]] || {
        echo "ERROR: prior-write proof is accepted only by quick audit" >&2
        exit 64
      }
      EASYROMS_SHA256=$full_easyroms_sha
      RAW_BYTES_READ=125992697856
    else
      EASYROMS_SHA256=-
      RAW_BYTES_READ=12199690592
    fi
    ;;
  *) echo "ERROR: unsupported audit layout: $LAYOUT" >&2; exit 64 ;;
esac

require_regular_user_file() {
  local path
  local expected_mode
  local identity
  path=$1
  expected_mode=$2
  [[ -f "$path" && ! -L "$path" ]] || return 1
  identity=$(/usr/bin/stat -f '%u:%Lp:%l' "$path") || return 1
  [[ "$identity" == "$(/usr/bin/id -u):$expected_mode:1" ]]
}

fast_p3_immutable_sha256() {
  local image
  image=$1
  {
    /bin/dd if="$image" bs=512 count=24 2>/dev/null
    /bin/dd if="$image" bs=16 skip=65536 count=1115 2>/dev/null
    /bin/dd if="$image" bs=512 skip=16896 count=1 2>/dev/null
    /bin/dd if="$image" bs=32768 skip=265 count=4449 2>/dev/null
  } | /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}'
}

path_owner_mode() {
  /usr/bin/stat -f '%u:%g:%Lp' "$1"
}

whole_disk_info_is_physical() {
  local whole_info
  whole_info=$1
  if /usr/bin/grep -Eq 'Virtual:[[:space:]]+No$' <<<"$whole_info"; then
    return 0
  fi
  ! /usr/bin/grep -Eq 'Virtual:[[:space:]]+' <<<"$whole_info" || return 1
  /usr/bin/grep -Eq 'Device Location:[[:space:]]+Internal$' <<<"$whole_info" || return 1
  /usr/bin/grep -Eq 'Removable Media:[[:space:]]+Fixed$' <<<"$whole_info" || return 1
  /usr/bin/grep -Eq 'Protocol:[[:space:]]+Apple Fabric$' <<<"$whole_info" || return 1
  /usr/bin/grep -Eq 'Solid State:[[:space:]]+Yes$' <<<"$whole_info"
}

physical_whole_for_source() {
  local source source_info source_device source_whole physical_store physical_count
  local store_info candidate whole_info whole_device
  source=$1
  [[ "$source" =~ ^/dev/disk[0-9]+(s[0-9]+)?$ ]] || return 1
  source_info=$(/usr/sbin/diskutil info "$source" 2>/dev/null) || return 1
  source_device=$(/usr/bin/sed -n 's/^[[:space:]]*Device Identifier:[[:space:]]*//p' <<<"$source_info")
  source_whole=$(/usr/bin/sed -n 's/^[[:space:]]*Part of Whole:[[:space:]]*//p' <<<"$source_info")
  [[ -n "$source_device" ]] || return 1
  physical_store=$(/usr/bin/sed -n 's/^[[:space:]]*APFS Physical Store:[[:space:]]*//p' <<<"$source_info")
  physical_count=$(/usr/bin/sed -n 's/^[[:space:]]*APFS Physical Store:[[:space:]]*//p' <<<"$source_info" |
    /usr/bin/awk 'NF {count++} END {print count+0}')
  (( physical_count <= 1 )) || return 1
  if [[ "$physical_count" -eq 1 ]]; then
    [[ "$physical_store" =~ ^disk[0-9]+s[0-9]+$ ]] || return 1
    store_info=$(/usr/sbin/diskutil info "/dev/${physical_store}" 2>/dev/null) || return 1
    candidate=$(/usr/bin/sed -n 's/^[[:space:]]*Part of Whole:[[:space:]]*//p' <<<"$store_info")
  else
    candidate=$source_whole
    [[ -n "$candidate" ]] || candidate=$source_device
  fi
  [[ "$candidate" =~ ^disk[0-9]+$ ]] || return 1
  whole_info=$(/usr/sbin/diskutil info "/dev/${candidate}" 2>/dev/null) || return 1
  whole_device=$(/usr/bin/sed -n 's/^[[:space:]]*Device Identifier:[[:space:]]*//p' <<<"$whole_info")
  [[ "$whole_device" == "$candidate" ]] || return 1
  /usr/bin/grep -Eq 'Whole:[[:space:]]+Yes$' <<<"$whole_info" || return 1
  whole_disk_info_is_physical "$whole_info" || return 1
  /usr/bin/printf '%s' "$candidate"
}

root_receipt_parent_is_safe() {
  local receipt_parent device resolved identity uid gid mode extra
  local source source_info physical
  receipt_parent=$1
  device=$2
  [[ "$receipt_parent" == "$ROOT_RECEIPT_PARENT" && -d "$receipt_parent" &&
     ! -L "$receipt_parent" && -k "$receipt_parent" ]] || return 1
  resolved=$(cd -- "$receipt_parent" && /bin/pwd -P) || return 1
  [[ "$resolved" == "$ROOT_RECEIPT_PARENT" ]] || return 1
  identity=$(path_owner_mode "$receipt_parent") || return 1
  IFS=: read -r uid gid mode extra <<<"$identity"
  [[ -z "${extra:-}" && "$uid" == 0 && "$gid" == 0 &&
     ( "$mode" == 777 || "$mode" == 1777 ) ]] || return 1
  source=$(/bin/df -P "$receipt_parent" | /usr/bin/awk 'END {print $1}') || return 1
  [[ "$source" =~ ^/dev/disk[0-9]+(s[0-9]+)?$ ]] || return 1
  source_info=$(/usr/sbin/diskutil info "$source" 2>/dev/null) || return 1
  /usr/bin/grep -Eq 'Owners:[[:space:]]+Enabled$' <<<"$source_info" || return 1
  physical=$(physical_whole_for_source "$source") || return 1
  [[ "$physical" != "${device#/dev/}" ]]
}

validate_fast_quick_proof() {
  local p3_artifact
  local build_status
  local raw_verify
  local manifest_status_sha
  local actual_status_sha
  local actual_raw_sha
  local status_raw_sha
  local expected_receipt_parent
  local receipt_parent_actual
  local receipt_actual
  local receipt_name
  local receipt_identity
  local actual_write_status_sha
  local actual_write_log_sha
  local actual_head_sha
  local actual_immutable_sha
  local status_after_sha
  local raw_after_sha
  local manifest_after_sha
  local write_status_after_sha
  local write_log_after_sha
  local prior_device
  local required_marker

  [[ "$EXPECTED_PRIOR_WRITE_STATUS_SHA256" =~ ^[0-9a-f]{64}$ &&
     "$EXPECTED_PRIOR_WRITE_LOG_SHA256" =~ ^[0-9a-f]{64}$ ]] || {
    echo "ERROR: quick audit requires pinned prior-write status and log SHA-256 values" >&2
    exit 64
  }

  p3_artifact="$REPO_ROOT/mainline/out/r46h-p3-recovery-images/r46h-easyroms-p3-62534975488-v1"
  build_status="$p3_artifact/BUILD-STATUS.json"
  raw_verify="$p3_artifact/RAW-VERIFY.json"
  require_regular_user_file "$build_status" 600 || { echo "ERROR: unsafe p3 build status" >&2; exit 65; }
  require_regular_user_file "$raw_verify" 600 || { echo "ERROR: unsafe p3 raw verification" >&2; exit 65; }
  require_regular_user_file "$ASSET_DIR/03-easyroms-p3.img" 600 || { echo "ERROR: unsafe fast-card p3 source image" >&2; exit 65; }
  manifest_status_sha=$(/usr/bin/awk '$1 == "p3_build_status_sha256" { print $2 }' "$manifest")
  actual_status_sha=$(/usr/bin/shasum -a 256 "$build_status")
  actual_status_sha=${actual_status_sha%% *}
  actual_raw_sha=$(/usr/bin/shasum -a 256 "$raw_verify")
  actual_raw_sha=${actual_raw_sha%% *}
  status_raw_sha=$(/usr/bin/plutil -extract raw_verification_sha256 raw -o - "$build_status")
  [[ "$manifest_status_sha" == 05f706354bf46c9ad5237815f40d0b9155b8b103b6ab8ad9e3cfc1a81fe3ef08 &&
     "$actual_status_sha" == "$manifest_status_sha" &&
     "$status_raw_sha" == 560de14babd243bbb981dca5b5a697660c895200be5f633a67d33d66ee398915 &&
     "$actual_raw_sha" == "$status_raw_sha" ]] || {
    echo "ERROR: quick audit p3 allocation proof mismatch" >&2
    exit 65
  }
  [[ "$(/usr/bin/plutil -extract state raw -o - "$build_status")" == BUILD_COMPLETE &&
     "$(/usr/bin/plutil -extract image_sha256 raw -o - "$build_status")" == "$full_easyroms_sha" &&
     "$(/usr/bin/plutil -extract image_size raw -o - "$build_status")" == "$EASYROMS_SIZE" &&
     "$(/usr/bin/plutil -extract allocation_bitmap_exact raw -o - "$build_status")" == true &&
     "$(/usr/bin/plutil -extract raw_verification_twice_passed raw -o - "$build_status")" == true &&
     "$(/usr/bin/plutil -extract post_normalize_fsck_read_only_passed raw -o - "$build_status")" == true ]] || {
    echo "ERROR: quick audit p3 build evidence is incomplete" >&2
    exit 65
  }
  [[ "$(/usr/bin/plutil -extract allocation_bitmap_exact raw -o - "$raw_verify")" == true &&
     "$(/usr/bin/plutil -extract allocated_cluster_count raw -o - "$raw_verify")" == 4458 &&
     "$(/usr/bin/plutil -extract claimed_cluster_count raw -o - "$raw_verify")" == 4458 &&
     "$(/usr/bin/plutil -extract overlapping_clusters raw -o - "$raw_verify")" == 0 &&
     "$(/usr/bin/plutil -extract deleted_entries raw -o - "$raw_verify")" == 0 &&
     "$(/usr/bin/plutil -extract cluster_heap_offset_sectors raw -o - "$raw_verify")" == 16384 &&
     "$(/usr/bin/plutil -extract cluster_size raw -o - "$raw_verify")" == 32768 &&
     "$(/usr/bin/plutil -extract sector_size raw -o - "$raw_verify")" == 512 ]] || {
    echo "ERROR: quick audit p3 allocation facts are inconsistent" >&2
    exit 65
  }
  [[ $((16384 * 512 + (4459 - 1) * 32768)) -le "$EASYROMS_HEAD_SIZE" ]] || {
    echo "ERROR: quick audit window does not cover every allocated p3 cluster" >&2
    exit 65
  }
  actual_head_sha=$(
    /bin/dd if="$ASSET_DIR/03-easyroms-p3.img" bs=1048576 count=256 2>/dev/null |
      /usr/bin/shasum -a 256
  )
  actual_head_sha=${actual_head_sha%% *}
  [[ "$actual_head_sha" == "$EASYROMS_HEAD_SHA256" ]] || {
    echo "ERROR: fast-card p3 allocated-window SHA-256 mismatch" >&2
    exit 65
  }
  actual_immutable_sha=$(fast_p3_immutable_sha256 "$ASSET_DIR/03-easyroms-p3.img")
  [[ "$actual_immutable_sha" == "$EASYROMS_QUICK_IMMUTABLE_SHA256" ]] || {
    echo "ERROR: fast-card p3 immutable proof SHA-256 mismatch" >&2
    exit 65
  }

  expected_receipt_parent="$REPO_ROOT/mainline/out/r46h-fast-card-layout-receipts"
  [[ -d "$expected_receipt_parent" && ! -L "$expected_receipt_parent" &&
     -d "$PRIOR_WRITE_RECEIPT_DIR" && ! -L "$PRIOR_WRITE_RECEIPT_DIR" ]] || {
    echo "ERROR: missing or unsafe prior-write receipt" >&2
    exit 65
  }
  receipt_parent_actual=$(cd -- "$(/usr/bin/dirname "$PRIOR_WRITE_RECEIPT_DIR")" && /bin/pwd -P)
  receipt_actual=$(cd -- "$PRIOR_WRITE_RECEIPT_DIR" && /bin/pwd -P)
  receipt_name=$(/usr/bin/basename "$PRIOR_WRITE_RECEIPT_DIR")
  receipt_identity=$(/usr/bin/stat -f '%u:%Lp' "$PRIOR_WRITE_RECEIPT_DIR")
  [[ "$receipt_parent_actual" == "$expected_receipt_parent" &&
     "$receipt_actual" == "$expected_receipt_parent/$receipt_name" &&
     "$receipt_name" == .r46h-new-card-layout.* &&
     "$receipt_identity" == "$(/usr/bin/id -u):700" ]] || {
    echo "ERROR: prior-write receipt identity mismatch" >&2
    exit 65
  }
  require_regular_user_file "$PRIOR_WRITE_RECEIPT_DIR/WRITE-STATUS.json" 600 || { echo "ERROR: unsafe prior-write status" >&2; exit 65; }
  require_regular_user_file "$PRIOR_WRITE_RECEIPT_DIR/layout-provision.log" 600 || { echo "ERROR: unsafe prior-write log" >&2; exit 65; }
  require_regular_user_file "$PRIOR_WRITE_RECEIPT_DIR/EJECTED" 600 || { echo "ERROR: unsafe prior-write eject marker" >&2; exit 65; }
  [[ ! -s "$PRIOR_WRITE_RECEIPT_DIR/EJECTED" ]] || { echo "ERROR: malformed prior-write eject marker" >&2; exit 65; }
  actual_write_status_sha=$(/usr/bin/shasum -a 256 "$PRIOR_WRITE_RECEIPT_DIR/WRITE-STATUS.json")
  actual_write_status_sha=${actual_write_status_sha%% *}
  actual_write_log_sha=$(/usr/bin/shasum -a 256 "$PRIOR_WRITE_RECEIPT_DIR/layout-provision.log")
  actual_write_log_sha=${actual_write_log_sha%% *}
  [[ "$actual_write_status_sha" == "$EXPECTED_PRIOR_WRITE_STATUS_SHA256" &&
     "$actual_write_log_sha" == "$EXPECTED_PRIOR_WRITE_LOG_SHA256" ]] || {
    echo "ERROR: prior-write receipt SHA-256 mismatch" >&2
    exit 65
  }
  prior_device=$(/usr/bin/plutil -extract device raw -o - "$PRIOR_WRITE_RECEIPT_DIR/WRITE-STATUS.json")
  [[ "$(/usr/bin/plutil -extract format_version raw -o - "$PRIOR_WRITE_RECEIPT_DIR/WRITE-STATUS.json")" == 1 &&
     "$(/usr/bin/plutil -extract state raw -o - "$PRIOR_WRITE_RECEIPT_DIR/WRITE-STATUS.json")" == MEDIA_WRITE_COMPLETE &&
     "$(/usr/bin/plutil -extract safe_to_boot raw -o - "$PRIOR_WRITE_RECEIPT_DIR/WRITE-STATUS.json")" == false &&
     "$prior_device" =~ ^/dev/disk[1-9][0-9]*$ &&
     "$(/usr/bin/plutil -extract next raw -o - "$PRIOR_WRITE_RECEIPT_DIR/WRITE-STATUS.json")" == reinsert-and-audit ]] || {
    echo "ERROR: prior-write status content mismatch" >&2
    exit 65
  }
  for required_marker in \
    "R46H_LAYOUT readback=prefix sha256=$PREFIX_SHA256" \
    "R46H_LAYOUT readback=boot sha256=$BOOT_IMAGE_SHA256" \
    "R46H_LAYOUT readback=root sha256=$ROOT_SHA256" \
    "R46H_LAYOUT readback=easyroms-metadata sha256=$full_easyroms_sha" \
    "R46H_MEDIA_AUDIT stage=ejected device=$prior_device" \
    "R46H_LAYOUT result=pass state=MEDIA_WRITE_COMPLETE safe_to_boot=no card_state=ejected next=reinsert-and-audit"
  do
    [[ "$(/usr/bin/grep -Fxc "$required_marker" "$PRIOR_WRITE_RECEIPT_DIR/layout-provision.log" || true)" == 1 ]] || {
      echo "ERROR: prior-write receipt is missing a full-readback marker" >&2
      exit 65
    }
  done
  manifest_after_sha=$(/usr/bin/shasum -a 256 "$manifest")
  manifest_after_sha=${manifest_after_sha%% *}
  status_after_sha=$(/usr/bin/shasum -a 256 "$build_status")
  status_after_sha=${status_after_sha%% *}
  raw_after_sha=$(/usr/bin/shasum -a 256 "$raw_verify")
  raw_after_sha=${raw_after_sha%% *}
  write_status_after_sha=$(/usr/bin/shasum -a 256 "$PRIOR_WRITE_RECEIPT_DIR/WRITE-STATUS.json")
  write_status_after_sha=${write_status_after_sha%% *}
  write_log_after_sha=$(/usr/bin/shasum -a 256 "$PRIOR_WRITE_RECEIPT_DIR/layout-provision.log")
  write_log_after_sha=${write_log_after_sha%% *}
  [[ "$manifest_after_sha" == "$actual_manifest" &&
     "$status_after_sha" == "$actual_status_sha" &&
     "$raw_after_sha" == "$actual_raw_sha" &&
     "$write_status_after_sha" == "$actual_write_status_sha" &&
     "$write_log_after_sha" == "$actual_write_log_sha" ]] || {
    echo "ERROR: quick audit evidence changed during validation" >&2
    exit 65
  }
  PRIOR_WRITE_STATUS_SHA256=$actual_write_status_sha
  PRIOR_WRITE_LOG_SHA256=$actual_write_log_sha
  P3_BUILD_STATUS_SHA256=$actual_status_sha
  P3_RAW_VERIFY_SHA256=$actual_raw_sha
}

if [[ "$AUDIT_LEVEL" == quick ]]; then
  validate_fast_quick_proof
elif [[ -n "$PRIOR_WRITE_RECEIPT_DIR$EXPECTED_PRIOR_WRITE_STATUS_SHA256$EXPECTED_PRIOR_WRITE_LOG_SHA256" ]]; then
  echo "ERROR: prior-write proof options require fast-card quick audit" >&2
  exit 64
fi

[[ -f "$TOOL" && ! -L "$TOOL" && -f "$TOOL_SUM" && ! -L "$TOOL_SUM" &&
   -f "$TOOL_SOURCE" && ! -L "$TOOL_SOURCE" ]] || {
  echo "ERROR: build the pinned layout provision tool first" >&2
  exit 66
}
tool_sum_lines=$(/usr/bin/awk '$2 == "r46h-card-layout-provision" { print $1 }' "$TOOL_SUM")
tool_source_sum_lines=$(/usr/bin/awk -v path="$TOOL_SOURCE_RECEIPT_PATH" '$2 == path { print $1 }' "$TOOL_SUM")
[[ "$tool_sum_lines" =~ ^[0-9a-f]{64}$ ]] || {
  echo "ERROR: layout audit tool receipt is malformed" >&2
  exit 65
}
expected_tool=$tool_sum_lines
actual_tool=$(/usr/bin/shasum -a 256 "$TOOL")
actual_tool=${actual_tool%% *}
actual_tool_source=$(/usr/bin/shasum -a 256 "$TOOL_SOURCE")
actual_tool_source=${actual_tool_source%% *}
[[ "$tool_source_sum_lines" =~ ^[0-9a-f]{64}$ &&
   "$actual_tool" == "$expected_tool" && "$actual_tool_source" == "$tool_source_sum_lines" ]] || {
  echo "ERROR: layout audit tool SHA-256 mismatch" >&2
  exit 65
}
tool_size=$(/usr/bin/stat -f '%z' "$TOOL")
[[ "$tool_size" =~ ^[1-9][0-9]*$ && "$tool_size" -le 16777216 ]] || {
  echo "ERROR: unsafe layout audit tool size" >&2
  exit 65
}

[[ -f "$PROBE" && ! -L "$PROBE" ]] || {
  echo "ERROR: filesystem snapshot probe is missing" >&2
  exit 66
}
probe_size=$(/usr/bin/stat -f '%z' "$PROBE")
probe_sha=$(/usr/bin/shasum -a 256 "$PROBE")
probe_sha=${probe_sha%% *}
[[ "$probe_size" =~ ^[1-9][0-9]*$ && "$probe_size" -le 1048576 && "$probe_sha" =~ ^[0-9a-f]{64}$ ]] || {
  echo "ERROR: filesystem snapshot probe identity is unsafe" >&2
  exit 65
}

root_receipt_parent_is_safe "$ROOT_RECEIPT_PARENT" "$DEVICE" || {
  echo "ERROR: root receipt parent is unsafe or resides on the target card" >&2
  exit 65
}
expected_uid=$(/usr/bin/id -u)
expected_gid=$(/usr/bin/id -g)
[[ "$expected_uid" =~ ^[1-9][0-9]*$ && "$expected_gid" =~ ^[0-9]+$ ]] || {
  echo "ERROR: invoking user identity is unsafe" >&2
  exit 65
}

echo "R46H Debian 13 new-card post-reinsert audit"
echo "target=$DEVICE exact_size=$WHOLE_SIZE audit_level=$AUDIT_LEVEL expected_raw_bytes=$RAW_BYTES_READ"
echo "One administrator authorization is used for one claimed-media read audit, root-private receipt, and eject."

# The root worker is data here; its variables expand only in the privileged shell.
# shellcheck disable=SC2016
ROOT_AUDIT='
set -euo pipefail

[[ "$#" -eq 36 ]]
device=$1
raw_device=$2
expected_identifier=$3
whole_size=$4
prefix_size=$5
prefix_sha=$6
boot_offset=$7
boot_size=$8
boot_image_sha=$9
root_offset=${10}
root_size=${11}
root_sha=${12}
easyroms_offset=${13}
easyroms_size=${14}
easyroms_sha=${15}
easyroms_head_size=${16}
easyroms_policy=${17}
tool=${18}
tool_sha=${19}
tool_size=${20}
probe=${21}
probe_sha=${22}
probe_size=${23}
boot_uuid=${24}
easyroms_uuid=${25}
expected_uid=${26}
expected_gid=${27}
expected_p3_sectors=${28}
audit_level=${29}
easyroms_head_sha=${30}
raw_bytes_read=${31}
prior_write_status_sha=${32}
prior_write_log_sha=${33}
p3_build_status_sha=${34}
p3_raw_verify_sha=${35}
quick_immutable_sha=${36}

[[ "${SUDO_UID:-}" == "$expected_uid" && "${SUDO_GID:-}" == "$expected_gid" &&
   "$expected_uid" =~ ^[1-9][0-9]*$ && "$expected_gid" =~ ^[0-9]+$ ]]
[[ "$device" == "/dev/$expected_identifier" && "$raw_device" == "/dev/r$expected_identifier" ]]
[[ "$expected_p3_sectors" =~ ^[1-9][0-9]*$ ]]
[[ "$audit_level" == full || "$audit_level" == quick || "$audit_level" == compact-head ]]
[[ "$easyroms_head_sha" =~ ^[0-9a-f]{64}$ ||
   ( "$audit_level" == compact-head && "$easyroms_head_sha" == - ) ]]
if [[ "$audit_level" == quick ]]; then
  [[ "$quick_immutable_sha" =~ ^[0-9a-f]{64}$ ]]
else
  [[ "$quick_immutable_sha" == - ]]
fi
[[ "$raw_bytes_read" =~ ^[1-9][0-9]*$ ]]
if [[ "$audit_level" == quick ]]; then
  [[ "$prior_write_status_sha" =~ ^[0-9a-f]{64}$ && "$prior_write_log_sha" =~ ^[0-9a-f]{64}$ &&
     "$p3_build_status_sha" =~ ^[0-9a-f]{64}$ && "$p3_raw_verify_sha" =~ ^[0-9a-f]{64}$ ]]
else
  [[ "$prior_write_status_sha" == - && "$prior_write_log_sha" == - &&
     "$p3_build_status_sha" == - && "$p3_raw_verify_sha" == - ]]
fi
umask 077

path_owner_mode() {
  /usr/bin/stat -f "%u:%g:%Lp" "$1"
}

path_identity() {
  /usr/bin/stat -f "%d:%i:%u" "$1"
}

path_nlink() {
  /usr/bin/stat -f "%l" "$1"
}

change_owner() {
  if [[ -x /usr/sbin/chown ]]; then
    /usr/sbin/chown "$@"
  else
    /bin/chown "$@"
  fi
}

whole_disk_info_is_physical() {
  local whole_info
  whole_info=$1
  if /usr/bin/grep -Eq "Virtual:[[:space:]]+No$" <<<"$whole_info"; then
    return 0
  fi
  ! /usr/bin/grep -Eq "Virtual:[[:space:]]+" <<<"$whole_info" || return 1
  /usr/bin/grep -Eq "Device Location:[[:space:]]+Internal$" <<<"$whole_info" || return 1
  /usr/bin/grep -Eq "Removable Media:[[:space:]]+Fixed$" <<<"$whole_info" || return 1
  /usr/bin/grep -Eq "Protocol:[[:space:]]+Apple Fabric$" <<<"$whole_info" || return 1
  /usr/bin/grep -Eq "Solid State:[[:space:]]+Yes$" <<<"$whole_info"
}

physical_whole_for_source() {
  local source source_info source_device source_whole physical_store physical_count
  local store_info candidate whole_info whole_device
  source=$1
  [[ "$source" =~ ^/dev/disk[0-9]+(s[0-9]+)?$ ]] || return 1
  source_info=$(/usr/sbin/diskutil info "$source" 2>/dev/null) || return 1
  source_device=$(/usr/bin/sed -n "s/^[[:space:]]*Device Identifier:[[:space:]]*//p" <<<"$source_info")
  source_whole=$(/usr/bin/sed -n "s/^[[:space:]]*Part of Whole:[[:space:]]*//p" <<<"$source_info")
  [[ -n "$source_device" ]] || return 1
  physical_store=$(/usr/bin/sed -n "s/^[[:space:]]*APFS Physical Store:[[:space:]]*//p" <<<"$source_info")
  physical_count=$(/usr/bin/printf "%s\n" "$physical_store" |
    /usr/bin/awk "NF {count++} END {print count+0}")
  (( physical_count <= 1 )) || return 1
  if [[ "$physical_count" -eq 1 ]]; then
    [[ "$physical_store" =~ ^disk[0-9]+s[0-9]+$ ]] || return 1
    store_info=$(/usr/sbin/diskutil info "/dev/${physical_store}" 2>/dev/null) || return 1
    candidate=$(/usr/bin/sed -n "s/^[[:space:]]*Part of Whole:[[:space:]]*//p" <<<"$store_info")
  else
    candidate=$source_whole
    [[ -n "$candidate" ]] || candidate=$source_device
  fi
  [[ "$candidate" =~ ^disk[0-9]+$ ]] || return 1
  whole_info=$(/usr/sbin/diskutil info "/dev/${candidate}" 2>/dev/null) || return 1
  whole_device=$(/usr/bin/sed -n "s/^[[:space:]]*Device Identifier:[[:space:]]*//p" <<<"$whole_info")
  [[ "$whole_device" == "$candidate" ]] || return 1
  /usr/bin/grep -Eq "Whole:[[:space:]]+Yes$" <<<"$whole_info" || return 1
  whole_disk_info_is_physical "$whole_info" || return 1
  /usr/bin/printf "%s" "$candidate"
}

root_receipt_parent_is_safe() {
  local resolved identity uid gid mode extra source source_info physical
  [[ "$receipt_parent" == /private/tmp && -d "$receipt_parent" &&
     ! -L "$receipt_parent" && -k "$receipt_parent" ]] || return 1
  resolved=$(cd -- "$receipt_parent" && /bin/pwd -P) || return 1
  [[ "$resolved" == /private/tmp ]] || return 1
  identity=$(path_owner_mode "$receipt_parent") || return 1
  IFS=: read -r uid gid mode extra <<<"$identity"
  [[ -z "${extra:-}" && "$uid" == 0 && "$gid" == 0 &&
     ( "$mode" == 777 || "$mode" == 1777 ) ]] || return 1
  source=$(/bin/df -P "$receipt_parent" | /usr/bin/awk "END {print \$1}") || return 1
  [[ "$source" =~ ^/dev/disk[0-9]+(s[0-9]+)?$ ]] || return 1
  source_info=$(/usr/sbin/diskutil info "$source" 2>/dev/null) || return 1
  /usr/bin/grep -Eq "Owners:[[:space:]]+Enabled$" <<<"$source_info" || return 1
  physical=$(physical_whole_for_source "$source") || return 1
  [[ "$physical" != "$expected_identifier" ]]
}

receipt_parent=/private/tmp
receipt_dir=
receipt_identity=
stage_dir=

provisional_cleanup() {
  local status=$?
  trap - EXIT INT TERM HUP
  trap "" INT TERM HUP
  set +e
  if [[ -n "$stage_dir" && "$stage_dir" == /private/tmp/r46h-card-audit-root.* &&
     -d "$stage_dir" && ! -L "$stage_dir" && "$(path_owner_mode "$stage_dir")" == 0:0:700 ]]; then
    /bin/rm -rf -- "$stage_dir"
  fi
  if [[ -n "$receipt_dir" && "$receipt_dir" == "$receipt_parent/.r46h-new-card-postwrite."* &&
     -d "$receipt_dir" && ! -L "$receipt_dir" && "$(path_owner_mode "$receipt_dir")" == 0:0:700 ]]; then
    /bin/rm -rf -- "$receipt_dir"
  fi
  exit "$status"
}
trap provisional_cleanup EXIT
trap "exit 130" INT
trap "exit 143" TERM
trap "exit 129" HUP

root_receipt_parent_is_safe
receipt_dir=$(/usr/bin/mktemp -d "$receipt_parent/.r46h-new-card-postwrite.XXXXXX")
/bin/chmod 700 "$receipt_dir"
[[ -d "$receipt_dir" && ! -L "$receipt_dir" && "$(path_owner_mode "$receipt_dir")" == 0:0:700 ]]
receipt_identity=$(path_identity "$receipt_dir")

status_file="$receipt_dir/AUDIT-STATUS.json"
stage_dir=$(/usr/bin/mktemp -d /private/tmp/r46h-card-audit-root.XXXXXX)
/bin/chmod 0700 "$stage_dir"
staged_tool="$stage_dir/r46h-card-layout-provision"
staged_probe="$stage_dir/filesystem-snapshot-probe.sh"
boot_snapshot="$stage_dir/boot-snapshot.img"
easyroms_snapshot="$stage_dir/easyroms-snapshot.img"
probe_result="$stage_dir/PROBE-COMPLETE"
worker_pid=
worker_result=127
pending_signal=
audit_complete=0

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

signal_status() {
  case "$1" in
    INT) echo 130 ;;
    TERM) echo 143 ;;
    HUP) echo 129 ;;
    *) echo 125 ;;
  esac
}

run_worker() {
  local log_path
  local cancelled_status
  log_path=$1
  shift
  pending_signal=
  worker_result=127
  trap "forward_worker_signal INT" INT
  trap "forward_worker_signal TERM" TERM
  trap "forward_worker_signal HUP" HUP
  "$@" > "$log_path" 2>&1 &
  worker_pid=$!
  if [[ -n "$pending_signal" ]]; then
    /bin/kill "-$pending_signal" "$worker_pid" 2>/dev/null || true
  fi
  wait_for_worker
  if [[ -n "$pending_signal" && "$worker_result" -eq 0 ]]; then
    cancelled_status=$(signal_status "$pending_signal")
    worker_result=$cancelled_status
  fi
  trap - INT TERM HUP
  /bin/cat "$log_path" || true
  return "$worker_result"
}

finalize_receipt_ownership() {
  local current unsafe_entry item name
  root_receipt_parent_is_safe || return 1
  [[ -d "$receipt_dir" && ! -L "$receipt_dir" ]] || return 1
  current=$(path_identity "$receipt_dir") || return 1
  [[ "$current" == "$receipt_identity" && "$(path_owner_mode "$receipt_dir")" == 0:0:700 ]] || return 1
  unsafe_entry=$(/usr/bin/find "$receipt_dir" -mindepth 1 ! -type f -print -quit) || return 1
  [[ -z "$unsafe_entry" ]] || return 1
  shopt -s nullglob dotglob
  for item in "$receipt_dir"/*; do
    name=${item##*/}
    [[ "$name" =~ ^[A-Za-z0-9._+-]+$ && -f "$item" && ! -L "$item" &&
       "$(path_owner_mode "$item")" == 0:0:* && "$(path_nlink "$item")" -eq 1 ]] || {
      shopt -u nullglob dotglob
      return 1
    }
    /bin/chmod 600 "$item" || {
      shopt -u nullglob dotglob
      return 1
    }
  done
  for item in "$receipt_dir"/*; do
    change_owner "$expected_uid:$expected_gid" "$item" || {
      shopt -u nullglob dotglob
      return 1
    }
  done
  shopt -u nullglob dotglob
  # This directory chown is the final filesystem access made by root.
  change_owner "$expected_uid:$expected_gid" "$receipt_dir"
}

cleanup() {
  local status=$?
  local receipt_handoff=0
  trap - EXIT INT TERM HUP
  trap "" INT TERM HUP
  set +e
  if [[ -n "$worker_pid" ]]; then
    wait_for_worker
    if [[ "$status" -eq 0 && "$worker_result" -ne 0 ]]; then
      status=$worker_result
    fi
  fi
  if [[ "$audit_complete" -ne 1 && "$status" -eq 0 ]]; then
    status=1
  fi
  if [[ "$audit_complete" -ne 1 ]]; then
    if [[ -d "$receipt_dir" && ! -L "$receipt_dir" &&
       "$(path_identity "$receipt_dir")" == "$receipt_identity" &&
       "$(path_owner_mode "$receipt_dir")" == 0:0:700 ]]; then
      /bin/rm -f -- \
        "$receipt_dir/AUDIT-COMPLETE" \
        "$receipt_dir/.AUDIT-COMPLETE.tmp" \
        "$receipt_dir/.AUDIT-STATUS.complete.tmp" 2>/dev/null || true
      printf "%s\n" "{\"format_version\":1,\"state\":\"AUDIT_FAILED\",\"safe_to_boot\":false,\"device\":\"$device\",\"audit_level\":\"$audit_level\",\"status\":$status,\"root_stage\":\"$stage_dir\"}" > "$status_file"
    else
      status=74
    fi
  fi
  if finalize_receipt_ownership; then
    receipt_handoff=1
  else
    status=74
  fi
  if [[ "$audit_complete" -ne 1 && -d "$stage_dir" ]]; then
    printf "WARNING: preserved privileged failure stage: %s\n" "$stage_dir" >&2
  fi
  if [[ "$receipt_handoff" -eq 1 ]]; then
    printf "RECEIPT_DIR=%s\n" "$receipt_dir" >&2
  else
    printf "WARNING: receipt handoff failed; the receipt remains root-owned: %s\n" "$receipt_dir" >&2
  fi
  exit "$status"
}
trap cleanup EXIT

/usr/bin/install -o root -g wheel -m 0700 "$tool" "$staged_tool"
/usr/bin/install -o root -g wheel -m 0700 "$probe" "$staged_probe"
[[ "$(/usr/bin/stat -f "%u:%Lp:%l:%z" "$staged_tool")" == "0:700:1:$tool_size" ]]
[[ "$(/usr/bin/stat -f "%u:%Lp:%l:%z" "$staged_probe")" == "0:700:1:$probe_size" ]]
staged_hash=$(/usr/bin/shasum -a 256 "$staged_tool")
staged_hash=${staged_hash%% *}
[[ "$staged_hash" == "$tool_sha" ]]
staged_probe_hash=$(/usr/bin/shasum -a 256 "$staged_probe")
staged_probe_hash=${staged_probe_hash%% *}
[[ "$staged_probe_hash" == "$probe_sha" ]]

plist_value() {
  /usr/bin/plutil -extract "$2" raw -o - "$1"
}

require_whole() {
  local plist
  plist=$1
  [[ "$(plist_value "$plist" DeviceIdentifier)" == "$expected_identifier" ]]
  [[ "$(plist_value "$plist" WholeDisk)" == true ]]
  [[ "$(plist_value "$plist" Content)" == FDisk_partition_scheme ]]
  [[ "$(plist_value "$plist" Size)" == "$whole_size" ]]
  [[ "$(plist_value "$plist" DeviceBlockSize)" == 512 ]]
  [[ "$(plist_value "$plist" BusProtocol)" == USB ]]
  [[ "$(plist_value "$plist" Internal)" == false ]]
  [[ "$(plist_value "$plist" RemovableMedia)" == true ]]
  [[ "$(plist_value "$plist" VirtualOrPhysical)" == Physical ]]
}

require_partition() {
  local plist
  local number
  local offset
  local size
  plist=$1
  number=$2
  offset=$3
  size=$4
  [[ "$(plist_value "$plist" DeviceIdentifier)" == "${expected_identifier}s${number}" ]]
  [[ "$(plist_value "$plist" ParentWholeDisk)" == "$expected_identifier" ]]
  [[ "$(plist_value "$plist" PartitionMapPartitionOffset)" == "$offset" ]]
  [[ "$(plist_value "$plist" Size)" == "$size" ]]
}

printf "%s\n" "{\"format_version\":1,\"state\":\"AUDIT_IN_PROGRESS\",\"safe_to_boot\":false,\"device\":\"$device\",\"audit_level\":\"$audit_level\"}" > "$status_file"

whole_plist="$receipt_dir/device.plist"
p1_plist="$receipt_dir/p1.plist"
p2_plist="$receipt_dir/p2.plist"
p3_plist="$receipt_dir/p3.plist"
/usr/sbin/diskutil info -plist "$device" > "$whole_plist"
/usr/sbin/diskutil info -plist "${device}s1" > "$p1_plist"
/usr/sbin/diskutil info -plist "${device}s2" > "$p2_plist"
/usr/sbin/diskutil info -plist "${device}s3" > "$p3_plist"
require_whole "$whole_plist"
require_partition "$p1_plist" 1 "$boot_offset" "$boot_size"
require_partition "$p2_plist" 2 "$root_offset" "$root_size"
require_partition "$p3_plist" 3 "$easyroms_offset" "$easyroms_size"
[[ ! -e "${device}s4" ]]
[[ "$(plist_value "$p1_plist" VolumeUUID)" == "$boot_uuid" ]]
[[ "$(plist_value "$p1_plist" VolumeName)" == BOOT ]]
[[ "$(plist_value "$p3_plist" VolumeUUID)" == "$easyroms_uuid" ]]
[[ "$(plist_value "$p3_plist" VolumeName)" == EASYROMS ]]

/usr/sbin/fdisk "$device" > "$receipt_dir/fdisk.txt"
/usr/bin/grep -Eq "\[ +32768 - +229376\]" "$receipt_dir/fdisk.txt"
/usr/bin/grep -Eq "\[ +262144 - +20931401\]" "$receipt_dir/fdisk.txt"
/usr/bin/grep -Eq "\[ +21193545 - +${expected_p3_sectors}\]" "$receipt_dir/fdisk.txt"
/usr/sbin/diskutil unmountDisk "$device" > "$receipt_dir/unmount-before.txt"

set +e
run_worker "$receipt_dir/claimed-media-audit.log" \
  "$staged_tool" audit "$raw_device" "$whole_size" \
  "$prefix_size" "$prefix_sha" \
  "$boot_offset" "$boot_size" "$boot_image_sha" \
  "$root_offset" "$root_size" "$root_sha" \
  "$easyroms_offset" "$easyroms_size" "$easyroms_sha" "$easyroms_head_size" "$easyroms_policy" \
  "$staged_probe" "$probe_size" "$probe_sha" \
  "$boot_snapshot" "$easyroms_snapshot" "$expected_identifier" \
  "$boot_uuid" "$easyroms_uuid" "$receipt_dir" "$probe_result" \
  "$easyroms_head_sha" "$audit_level" "$quick_immutable_sha"
audit_status=$?
set -e
if [[ "$audit_status" -ne 0 ]]; then
  exit "$audit_status"
fi

p3_full_verified=false
[[ "$audit_level" == full ]] && p3_full_verified=true
if [[ "$easyroms_head_sha" == - || "$audit_level" == quick ]]; then
  expected_p3_head_pattern="[0-9a-f]{64}"
else
  expected_p3_head_pattern=$easyroms_head_sha
fi
if [[ "$audit_level" == quick ]]; then
  expected_quick_immutable_pattern=$quick_immutable_sha
else
  expected_quick_immutable_pattern=not-verified
fi
audit_pattern="^R46H_MEDIA_AUDIT result=pass device=$raw_device whole_size=$whole_size block_size=512 prefix_sha256=$prefix_sha p1_sha256=[0-9a-f]{64} p1_matches_write_image=(true|false) p2_sha256=$root_sha p3_sha256=($easyroms_sha|not-verified) p3_head_sha256=$expected_p3_head_pattern p3_quick_immutable_sha256=$expected_quick_immutable_pattern boot_uuid=$boot_uuid easyroms_uuid=$easyroms_uuid audit_level=$audit_level p3_full_verified=$p3_full_verified raw_bytes_read=$raw_bytes_read card_state=ejected$"
audit_marker_count=$(/usr/bin/grep -Ec "$audit_pattern" "$receipt_dir/claimed-media-audit.log" || true)
[[ "$audit_marker_count" == 1 ]]
audit_line=$(/usr/bin/grep -E "$audit_pattern" "$receipt_dir/claimed-media-audit.log")
p1_sha=${audit_line#* p1_sha256=}
p1_sha=${p1_sha%% *}
p1_matches=${audit_line#* p1_matches_write_image=}
p1_matches=${p1_matches%% *}
p3_sha=${audit_line#* p3_sha256=}
p3_sha=${p3_sha%% *}
p3_head_sha=${audit_line#* p3_head_sha256=}
p3_head_sha=${p3_head_sha%% *}
quick_immutable_actual=${audit_line#* p3_quick_immutable_sha256=}
quick_immutable_actual=${quick_immutable_actual%% *}
[[ "$p1_sha" =~ ^[0-9a-f]{64}$ ]]
[[ "$p1_matches" == true || "$p1_matches" == false ]]
if [[ "$easyroms_sha" == - ]]; then
  [[ "$p3_sha" == not-verified ]]
else
  [[ "$p3_sha" == "$easyroms_sha" ]]
fi
if [[ "$easyroms_head_sha" == - || "$audit_level" == quick ]]; then
  [[ "$p3_head_sha" =~ ^[0-9a-f]{64}$ ]]
else
  [[ "$p3_head_sha" == "$easyroms_head_sha" ]]
fi
[[ "$quick_immutable_actual" == "$expected_quick_immutable_pattern" ]]
if [[ "$p1_sha" == "$boot_image_sha" ]]; then
  [[ "$p1_matches" == true ]]
else
  [[ "$p1_matches" == false ]]
fi
[[ ! -e "$device" && ! -e "$raw_device" ]]

final_status_tmp="$receipt_dir/.AUDIT-STATUS.complete.tmp"
marker_tmp="$receipt_dir/.AUDIT-COMPLETE.tmp"
p3_allocated_window_verified=false
p3_immutable_payload_verified=false
prior_full_write_verified=false
p3_verified_bytes=$easyroms_head_size
if [[ "$audit_level" == full ]]; then
  p3_allocated_window_verified=true
  p3_immutable_payload_verified=true
  p3_verified_bytes=$easyroms_size
elif [[ "$audit_level" == quick ]]; then
  p3_immutable_payload_verified=true
  p3_verified_bytes=145815472
  prior_full_write_verified=true
fi
printf "%s\n" "{\"format_version\":1,\"state\":\"AUDIT_COMPLETE\",\"safe_to_boot\":true,\"device\":\"$device\",\"card_state\":\"ejected\",\"audit_level\":\"$audit_level\",\"raw_bytes_read\":$raw_bytes_read,\"p3_full_verified\":$p3_full_verified,\"p3_allocated_window_verified\":$p3_allocated_window_verified,\"p3_immutable_payload_verified\":$p3_immutable_payload_verified,\"p3_verified_bytes\":$p3_verified_bytes,\"prior_full_write_verified\":$prior_full_write_verified,\"prior_write_status_sha256\":\"$prior_write_status_sha\",\"prior_write_log_sha256\":\"$prior_write_log_sha\",\"p3_build_status_sha256\":\"$p3_build_status_sha\",\"p3_raw_verify_sha256\":\"$p3_raw_verify_sha\",\"prefix_sha256\":\"$prefix_sha\",\"p1_sha256\":\"$p1_sha\",\"p1_matches_write_image\":$p1_matches,\"p2_sha256\":\"$root_sha\",\"p3_sha256\":\"$p3_sha\",\"p3_head_sha256\":\"$p3_head_sha\",\"p3_quick_immutable_sha256\":\"$quick_immutable_actual\",\"boot_volume_uuid\":\"$boot_uuid\",\"easyroms_volume_uuid\":\"$easyroms_uuid\"}" > "$final_status_tmp"
status_sha=$(/usr/bin/shasum -a 256 "$final_status_tmp")
status_sha=${status_sha%% *}
printf "status_sha256=%s\n" "$status_sha" > "$marker_tmp"

/bin/rm -f -- \
  "$staged_tool" "$staged_probe" "$boot_snapshot" "$easyroms_snapshot" "$probe_result"
/bin/rmdir -- "$stage_dir"
[[ ! -e "$stage_dir" ]]
/bin/mv -f -- "$final_status_tmp" "$status_file"
/bin/sync
/bin/mv -f -- "$marker_tmp" "$receipt_dir/AUDIT-COMPLETE"
audit_complete=1
trap - EXIT
trap "" INT TERM HUP
if ! finalize_receipt_ownership; then
  printf "WARNING: media audit completed, but receipt handoff failed; receipt remains root-owned: %s\n" "$receipt_dir" >&2
  exit 74
fi

printf "PASS: one claimed medium passed raw, offline filesystem, anchor, and eject checks.\n"
printf "SAFE_TO_BOOT=yes\nBOOT_VOLUME_UUID=%s\nEASYROMS_VOLUME_UUID=%s\n" "$boot_uuid" "$easyroms_uuid"
printf "P1_MATCHES_WRITE_IMAGE=%s\nP2_SHA256=%s\nCARD_STATE=ejected\n" "$p1_matches" "$root_sha"
printf "AUDIT_LEVEL=%s\nRAW_BYTES_READ=%s\nP3_FULL_VERIFIED=%s\n" "$audit_level" "$raw_bytes_read" "$p3_full_verified"
printf "P3_ALLOCATED_WINDOW_VERIFIED=%s\nP3_IMMUTABLE_PAYLOAD_VERIFIED=%s\n" "$p3_allocated_window_verified" "$p3_immutable_payload_verified"
printf "PRIOR_FULL_WRITE_VERIFIED=%s\n" "$prior_full_write_verified"
printf "RECEIPT_DIR=%s\n" "$receipt_dir"
'

raw_device="/dev/r${DEVICE#/dev/}"
identifier=${DEVICE#/dev/}
exec /usr/bin/sudo -- /bin/bash -c "$ROOT_AUDIT" r46h-new-card-postwrite-audit-root \
  "$DEVICE" "$raw_device" "$identifier" "$WHOLE_SIZE" \
  "$PREFIX_SIZE" "$PREFIX_SHA256" "$BOOT_OFFSET" "$BOOT_SIZE" "$BOOT_IMAGE_SHA256" \
  "$ROOT_OFFSET" "$ROOT_SIZE" "$ROOT_SHA256" \
  "$EASYROMS_OFFSET" "$EASYROMS_SIZE" "$EASYROMS_SHA256" "$EASYROMS_HEAD_SIZE" \
  "$EASYROMS_POLICY" \
  "$TOOL" "$expected_tool" "$tool_size" "$PROBE" "$probe_sha" "$probe_size" \
  "$BOOT_UUID" "$EASYROMS_UUID" \
  "$expected_uid" "$expected_gid" "$EXPECTED_P3_SECTORS" \
  "$AUDIT_LEVEL" "$EASYROMS_HEAD_SHA256" "$RAW_BYTES_READ" \
  "$PRIOR_WRITE_STATUS_SHA256" "$PRIOR_WRITE_LOG_SHA256" \
  "$P3_BUILD_STATUS_SHA256" "$P3_RAW_VERIFY_SHA256" \
  "$EASYROMS_QUICK_IMMUTABLE_SHA256"
