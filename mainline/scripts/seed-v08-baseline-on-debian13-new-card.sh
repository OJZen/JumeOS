#!/bin/bash
set -euo pipefail

PATH=/usr/bin:/bin:/usr/sbin:/sbin
LC_ALL=C
LANG=C
COPYFILE_DISABLE=1
export PATH LC_ALL LANG COPYFILE_DISABLE
umask 077

SCRIPT_DIR=$(cd -- "$(/usr/bin/dirname "$0")" && /bin/pwd -P)
REPO_ROOT=$(cd -- "$SCRIPT_DIR/../.." && /bin/pwd -P)
SCRIPT_PATH="$SCRIPT_DIR/$(/usr/bin/basename "$0")"

readonly WHOLE_SIZE=31719424000
readonly SECTOR_SIZE=512
readonly PREFIX_SIZE=16777216
readonly PREFIX_SHA256=97ede10075b3257c638a04b3044c9dda2d8dd9adc6f6fee3be7b004a31fb135e
readonly BOOT_OFFSET=16777216
readonly BOOT_SIZE=117440512
readonly BOOT_UUID=575BC58C-96FA-3E4F-958B-7A30D5210C3D
readonly ROOT_OFFSET=134217728
readonly ROOT_SIZE=10716877312
readonly ROOT_PARTUUID=c9f931c9-02
readonly ROOT_SECTOR_COUNT=20931401
readonly ROOT_SAMPLE_SECTOR_COUNT=8192
readonly EASYROMS_OFFSET=10851095040
readonly EASYROMS_SIZE=20868328960
readonly EASYROMS_UUID=E1F5295C-4B12-A54A-ACB7-317194240001

readonly PAYLOAD_NAME=r46h-v0.8-bootloader-handoff
readonly SOURCE_BUNDLE_DEFAULT="$REPO_ROOT/mainline/out/r46h-easyroms-v0.8-bootloader-handoff"
readonly SOURCE_LIST_SHA256=fd5f744b75de5849702718493bc87286f41e54acd4be904d657a28858dadbcf8
readonly SOURCE_ENTRY_COUNT=11
readonly STAGE_COMPLETE_SHA256=7de695c19cd6a475143d9e78271877e1adce358584d9ac81e7b1b3276141d2e9
readonly DEFAULT_RECEIPT_PARENT=/private/tmp
readonly PRIOR_AUDIT_STATUS_SHA256=ce59319faafe2a84ee8efe7640ab0bfffa471510a41889fb3f517597964963e2
readonly PRIOR_AUDIT_P2_SHA256=6a4254a8e66c110405cf068317da5922bb5ddfe2a02535d1a381fe1303876c96
readonly PRIOR_AUDIT_STATUS_CONTENT='{"format_version":1,"state":"AUDIT_COMPLETE","safe_to_boot":true,"device":"/dev/disk12","card_state":"ejected","prefix_sha256":"97ede10075b3257c638a04b3044c9dda2d8dd9adc6f6fee3be7b004a31fb135e","p1_sha256":"0132f9a4748408a493983111cfe5c0f2de44574095a236fd13be539e9b39a4bc","p1_matches_write_image":false,"p2_sha256":"6a4254a8e66c110405cf068317da5922bb5ddfe2a02535d1a381fe1303876c96","p3_head_sha256":"92e70ad6a4008df0e7acf276b6602aaf1a86abaae3e1550838ed9b06b658ab6e","boot_volume_uuid":"575BC58C-96FA-3E4F-958B-7A30D5210C3D","easyroms_volume_uuid":"E1F5295C-4B12-A54A-ACB7-317194240001"}'

fail() {
  /usr/bin/printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

hash_file() {
  if [[ -x /usr/bin/shasum ]]; then
    /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'
  else
    /usr/bin/sha256sum "$1" | /usr/bin/awk '{print $1}'
  fi
}

file_size() {
  if [[ "$(/usr/bin/uname -s)" == Darwin ]]; then
    /usr/bin/stat -f '%z' "$1"
  else
    /usr/bin/stat -c '%s' "$1"
  fi
}

path_owner_mode() {
  if [[ "$(/usr/bin/uname -s)" == Darwin ]]; then
    /usr/bin/stat -f '%u:%g:%Lp' "$1"
  else
    /usr/bin/stat -c '%u:%g:%a' "$1"
  fi
}

path_identity() {
  if [[ "$(/usr/bin/uname -s)" == Darwin ]]; then
    /usr/bin/stat -f '%d:%i:%u' "$1"
  else
    /usr/bin/stat -c '%d:%i:%u' "$1"
  fi
}

path_nlink() {
  if [[ "$(/usr/bin/uname -s)" == Darwin ]]; then
    /usr/bin/stat -f '%l' "$1"
  else
    /usr/bin/stat -c '%h' "$1"
  fi
}

change_owner() {
  if [[ -x /usr/sbin/chown ]]; then
    /usr/sbin/chown "$@"
  else
    /bin/chown "$@"
  fi
}

path_owner_mode_is_safe() {
  local path=$1 expected_uid=$2 expected_mode=$3 identity uid gid mode extra
  local volume_source volume_info
  identity=$(path_owner_mode "$path") || return 1
  IFS=: read -r uid gid mode extra <<<"$identity"
  [[ -z "${extra:-}" && "$uid" =~ ^[0-9]+$ && "$gid" =~ ^[0-9]+$ &&
     "$mode" == "$expected_mode" ]] || return 1
  [[ "$uid" == "$expected_uid" ]] && return 0
  # A noowners APFS volume is exposed as _unknown (99:99) to root on current macOS.
  [[ "$expected_uid" != 0 && "$EUID" -eq 0 && "$(/usr/bin/uname -s)" == Darwin &&
     ( "$uid" == 0 || ( "$uid" == 99 && "$gid" == 99 ) ) ]] || return 1
  volume_source=$(/bin/df -P "$path" | /usr/bin/awk 'END {print $1}') || return 1
  [[ "$volume_source" =~ ^/dev/disk[0-9]+(s[0-9]+)?$ ]] || return 1
  volume_info=$(/usr/sbin/diskutil info "$volume_source" 2>/dev/null) || return 1
  /usr/bin/grep -Eq 'Owners:[[:space:]]+Disabled$' <<<"$volume_info"
}

source_entry() {
  local source_list=$1 wanted_name=$2 hash path extra found=0
  while read -r hash path extra; do
    [[ -z "${extra:-}" ]] || return 1
    [[ "$hash" =~ ^[0-9a-f]{64}$ && "$path" =~ ^payload/[A-Za-z0-9._+-]+$ ]] || return 1
    if [[ "${path#payload/}" == "$wanted_name" ]]; then
      (( found == 0 )) || return 1
      /usr/bin/printf '%s\n' "$hash"
      found=1
    fi
  done < "$source_list"
  (( found == 1 ))
}

validate_source_bundle() {
  local source_bundle=$1 source_list source_root list_hash
  local hash path extra name previous_path='' count=0 actual_count=0 matched
  local saw_complete=0
  source_list="$source_bundle/STAGE-SOURCES.sha256"
  source_root="$source_bundle/payload"

  [[ -d "$source_bundle" && ! -L "$source_bundle" &&
     -f "$source_list" && ! -L "$source_list" &&
     -d "$source_root" && ! -L "$source_root" ]] ||
    fail "canonical v0.8 source bundle is missing or unsafe"
  list_hash=$(hash_file "$source_list")
  [[ "$list_hash" == "$SOURCE_LIST_SHA256" ]] ||
    fail "canonical v0.8 source-list SHA-256 mismatch"

  while read -r hash path extra; do
    [[ -z "${extra:-}" ]] || fail "malformed canonical source-list entry"
    [[ "$hash" =~ ^[0-9a-f]{64}$ && "$path" =~ ^payload/[A-Za-z0-9._+-]+$ ]] ||
      fail "unsafe canonical source-list entry: ${path:-missing}"
    [[ -z "$previous_path" || "$path" > "$previous_path" ]] ||
      fail "canonical source paths are not unique and sorted"
    previous_path=$path
    name=${path#payload/}
    [[ -f "$source_root/$name" && ! -L "$source_root/$name" ]] ||
      fail "canonical source is missing or unsafe: $name"
    [[ "$(hash_file "$source_root/$name")" == "$hash" ]] ||
      fail "canonical source SHA-256 mismatch: $name"
    [[ "$name" != STAGE-COMPLETE ]] || saw_complete=1
    count=$((count + 1))
  done < "$source_list"
  [[ "$count" -eq "$SOURCE_ENTRY_COUNT" && "$saw_complete" -eq 1 ]] ||
    fail "canonical v0.8 source list has an unexpected file set"
  [[ "$(hash_file "$source_root/STAGE-COMPLETE")" == "$STAGE_COMPLETE_SHA256" ]] ||
    fail "canonical STAGE-COMPLETE identity mismatch"

  shopt -s nullglob dotglob
  for matched in "$source_root"/*; do
    [[ -f "$matched" && ! -L "$matched" ]] ||
      fail "canonical payload contains a non-regular entry"
    name=${matched##*/}
    [[ "$name" =~ ^[A-Za-z0-9._+-]+$ ]] || fail "unsafe canonical payload name: $name"
    source_entry "$source_list" "$name" >/dev/null ||
      fail "canonical payload is not exactly covered by its source list: $name"
    actual_count=$((actual_count + 1))
  done
  shopt -u nullglob dotglob
  [[ "$actual_count" -eq "$SOURCE_ENTRY_COUNT" ]] ||
    fail "canonical payload entry count mismatch"
}

whole_disk_info_is_physical() {
  local whole_info=$1
  # Removable and legacy media report this field explicitly.
  if /usr/bin/grep -Eq 'Virtual:[[:space:]]+No$' <<<"$whole_info"; then
    return 0
  fi
  # Apple Silicon internal storage reports VirtualOrPhysical=Unknown in the
  # plist and omits the human-readable Virtual line. Accept only the exact
  # internal Apple Fabric identity; a disk image, external device or other
  # unresolved virtual topology remains rejected.
  ! /usr/bin/grep -Eq 'Virtual:[[:space:]]+' <<<"$whole_info" || return 1
  /usr/bin/grep -Eq 'Device Location:[[:space:]]+Internal$' <<<"$whole_info" || return 1
  /usr/bin/grep -Eq 'Removable Media:[[:space:]]+Fixed$' <<<"$whole_info" || return 1
  /usr/bin/grep -Eq 'Protocol:[[:space:]]+Apple Fabric$' <<<"$whole_info" || return 1
  /usr/bin/grep -Eq 'Solid State:[[:space:]]+Yes$' <<<"$whole_info"
}

physical_whole_for_source() {
  local source=$1 source_info source_device source_whole physical_store physical_count
  local store_info candidate whole_info whole_device
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

path_is_on_other_physical_disk() {
  local path=$1 device=$2 source physical
  source=$(/bin/df -P "$path" | /usr/bin/awk 'END {print $1}') || return 1
  [[ "$source" == /dev/* ]] || return 1
  physical=$(physical_whole_for_source "$source") || return 1
  [[ "$physical" != "${device#/dev/}" ]]
}

evidence_dir_is_safe() {
  local evidence_dir=$1 device=$2 expected_uid=$3
  [[ -d "$evidence_dir" && ! -L "$evidence_dir" && "$evidence_dir" == /Volumes/* ]] ||
    return 1
  path_owner_mode_is_safe "$evidence_dir" "$expected_uid" 700 || return 1
  path_is_on_other_physical_disk "$evidence_dir" "$device"
}

root_receipt_parent_identity_is_safe() {
  local receipt_parent=$1 expected_path=$2 resolved identity uid gid mode extra
  [[ "$receipt_parent" == "$expected_path" && -d "$receipt_parent" &&
     ! -L "$receipt_parent" && -k "$receipt_parent" ]] || return 1
  resolved=$(cd -- "$receipt_parent" && /bin/pwd -P) || return 1
  [[ "$resolved" == "$expected_path" ]] || return 1
  identity=$(path_owner_mode "$receipt_parent") || return 1
  IFS=: read -r uid gid mode extra <<<"$identity"
  [[ -z "${extra:-}" && "$uid" == 0 && "$gid" == 0 &&
     ( "$mode" == 777 || "$mode" == 1777 ) ]]
}

root_receipt_parent_is_safe() {
  local receipt_parent=$1 device=$2
  root_receipt_parent_identity_is_safe "$receipt_parent" "$DEFAULT_RECEIPT_PARENT" || return 1
  path_is_on_other_physical_disk "$receipt_parent" "$device"
}

validate_prior_audit_files() {
  local audit_dir=$1 expected_uid=$2 status_name=${3:-AUDIT-STATUS.json}
  local complete_name=${4:-AUDIT-COMPLETE}
  local status_file complete_file status_content
  status_file="$audit_dir/$status_name"
  complete_file="$audit_dir/$complete_name"
  [[ -d "$audit_dir" && ! -L "$audit_dir" &&
     -f "$status_file" && ! -L "$status_file" &&
     -f "$complete_file" && ! -L "$complete_file" ]] ||
    fail "prior full-p2 audit receipt is missing or unsafe"
  path_owner_mode_is_safe "$audit_dir" "$expected_uid" 700 ||
    fail "prior audit directory identity mismatch"
  for audit_file in "$status_file" "$complete_file"; do
    path_owner_mode_is_safe "$audit_file" "$expected_uid" 600 ||
      fail "prior audit file ownership or mode mismatch: ${audit_file##*/}"
    [[ "$(path_nlink "$audit_file")" -eq 1 ]] ||
      fail "prior audit file identity mismatch: ${audit_file##*/}"
  done
  [[ "$(hash_file "$status_file")" == "$PRIOR_AUDIT_STATUS_SHA256" ]] ||
    fail "prior full-p2 audit status SHA-256 mismatch"
  status_content=$(< "$status_file")
  [[ "$status_content" == "$PRIOR_AUDIT_STATUS_CONTENT" ]] ||
    fail "prior full-p2 audit status content mismatch"
  [[ "$(< "$complete_file")" == "status_sha256=$PRIOR_AUDIT_STATUS_SHA256" ]] ||
    fail "prior full-p2 audit completion marker mismatch"
}

validate_prior_audit_location() {
  local audit_dir=$1 expected_uid=$2 device=$3 supplied_status_hash=$4 test_root=$5 resolved
  [[ "$supplied_status_hash" == "$PRIOR_AUDIT_STATUS_SHA256" ]] ||
    fail "prior audit status hash does not match the pinned full-p2 audit"
  [[ -d "$audit_dir" && ! -L "$audit_dir" ]] || fail "prior audit directory is unavailable"
  resolved=$(cd -- "$audit_dir" && /bin/pwd -P) || fail "cannot resolve prior audit directory"
  [[ "$resolved" == "$audit_dir" ]] || fail "prior audit directory must be a canonical non-symlink path"
  if [[ -n "$test_root" ]]; then
    [[ "$audit_dir" == "$test_root/prior-audit" ]] || fail "unsafe fixture prior-audit path"
  else
    [[ "$audit_dir" == "$REPO_ROOT/mainline/out/r46h-new-card-postwrite-audits/.r46h-new-card-postwrite."* ]] ||
      fail "prior audit directory is outside the fixed new-card audit namespace"
    evidence_dir_is_safe "$audit_dir" "$device" "$expected_uid" ||
      fail "prior audit directory is unsafe or resides on the target card"
  fi
}

validate_prior_audit_source() {
  local audit_dir=$1 expected_uid=$2 device=$3 supplied_status_hash=$4 test_root=$5
  validate_prior_audit_location "$audit_dir" "$expected_uid" "$device" \
    "$supplied_status_hash" "$test_root"
  validate_prior_audit_files "$audit_dir" "$expected_uid"
}

plist_value() {
  /usr/bin/plutil -extract "$2" raw -o - "$1"
}

seed_worker() {
  local device=$1 receipt_parent=$2 expected_uid=$3 expected_gid=$4
  local source_bundle=$5 expected_script_hash=$6 prior_audit_dir=$7 prior_audit_status_hash=$8
  local test_root=${9:-}
  local raw_device identifier boot_partition boot_raw_partition root_partition root_raw_partition
  local roms_partition roms_mount receipt_dir='' receipt_identity='' work_dir='' snapshot_bundle
  local snapshot_audit receipt_token source_name source_hash source_path source_extra
  local source_list source_root payload_final payload_root_sidecar status_file
  local completed=0 gate_published=0 final_verified=0 ejected=0
  local cleanup_running=0 card_access_started=0

  if [[ -n "$test_root" ]]; then
    [[ -f /.dockerenv && "$EUID" -eq 0 ]] || fail "seed fixture mode is container-root only"
    [[ "$test_root" == /run/r46h-v08-seed-test.* ||
       "$test_root" == /repo/mainline/out/.cache/.r46h-v08-seed-test.* ]] ||
      fail "unsafe seed fixture root"
    [[ -d "$test_root" && ! -L "$test_root" && "$(path_owner_mode "$test_root")" == 0:0:700 ]] ||
      fail "seed fixture root must be root-owned 0700"
  else
    [[ "$(/usr/bin/uname -s)" == Darwin && "$EUID" -eq 0 ]] ||
      fail "production seed worker requires macOS root"
    [[ "${SUDO_UID:-}" == "$expected_uid" && "$expected_uid" =~ ^[1-9][0-9]*$ ]] ||
      fail "invoking user identity mismatch"
    [[ "$(hash_file "$SCRIPT_PATH")" == "$expected_script_hash" ]] ||
      fail "seed worker script SHA-256 changed"
    root_receipt_parent_is_safe "$receipt_parent" "$device" ||
      fail "root receipt parent is unsafe or resides on the target card"
    [[ "$source_bundle" == "$SOURCE_BUNDLE_DEFAULT" && -d "$source_bundle" &&
       ! -L "$source_bundle" && "$(cd -- "$source_bundle" && /bin/pwd -P)" == "$SOURCE_BUNDLE_DEFAULT" ]] ||
      fail "canonical source bundle location mismatch"
    path_is_on_other_physical_disk "$source_bundle" "$device" ||
      fail "canonical source bundle resides on the target card"
  fi

  validate_prior_audit_location "$prior_audit_dir" "$expected_uid" "$device" \
    "$prior_audit_status_hash" "$test_root"
  [[ "$((ROOT_SECTOR_COUNT * SECTOR_SIZE))" -eq "$ROOT_SIZE" &&
     "$ROOT_SAMPLE_SECTOR_COUNT" -gt 0 &&
     "$ROOT_SAMPLE_SECTOR_COUNT" -lt "$ROOT_SECTOR_COUNT" &&
     "$((PREFIX_SIZE % 1048576))" -eq 0 ]] ||
    fail "internal geometry arithmetic mismatch"
  [[ "$device" =~ ^/dev/disk[1-9][0-9]*$ && "$device" != /dev/disk6 ]] ||
    fail "unsafe target device"
  raw_device="/dev/r${device#/dev/}"
  identifier=${device#/dev/}
  boot_partition="${device}s1"
  boot_raw_partition="/dev/r${identifier}s1"
  root_partition="${device}s2"
  root_raw_partition="/dev/r${identifier}s2"
  roms_partition="${device}s3"

  # ShellCheck cannot see this local function's later EXIT-trap invocation.
  # shellcheck disable=SC2317
  provisional_cleanup() {
    local status=$?
    trap - EXIT INT TERM HUP
    trap '' INT TERM HUP
    set +e
    if [[ -n "$receipt_dir" && "$receipt_dir" == "$receipt_parent/.r46h-v08-new-card-seed."* &&
       -d "$receipt_dir" && ! -L "$receipt_dir" && "$(path_owner_mode "$receipt_dir")" == 0:0:700 ]]; then
      /bin/rm -rf -- "$receipt_dir"
      [[ ! -e "$receipt_dir" ]] || status=74
    fi
    exit "$status"
  }
  trap provisional_cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP

  if [[ -n "$test_root" ]]; then
    root_receipt_parent_identity_is_safe "$receipt_parent" "$test_root/receipts" ||
      fail "fixture root receipt parent identity mismatch"
    receipt_dir=$(/usr/bin/mktemp -d "$receipt_parent/.r46h-v08-new-card-seed.XXXXXX") ||
      fail "cannot create seed receipt"
  else
    receipt_token=$(/usr/bin/uuidgen) || fail "cannot generate seed receipt identity"
    [[ "$receipt_token" =~ ^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$ ]] ||
      fail "invalid seed receipt identity"
    receipt_dir="$receipt_parent/.r46h-v08-new-card-seed.$receipt_token"
    /bin/mkdir -m 700 "$receipt_dir" || fail "cannot create seed receipt"
  fi
  [[ -d "$receipt_dir" && ! -L "$receipt_dir" && "$(path_owner_mode "$receipt_dir")" == 0:0:700 ]] ||
    fail "seed receipt is not a root-private directory"
  receipt_identity=$(path_identity "$receipt_dir")
  work_dir="$receipt_dir/.work"
  /bin/mkdir -m 700 "$work_dir"
  snapshot_bundle="$work_dir/source"
  snapshot_audit="$work_dir/prior-audit"
  /bin/mkdir -m 700 "$snapshot_bundle" "$snapshot_bundle/payload" "$snapshot_audit"
  status_file="$receipt_dir/SEED-STATUS.json"

  copy_invoking_user_file() {
    local source=$1 destination=$2
    [[ -f "$source" && ! -L "$source" && ! -e "$destination" ]] ||
      fail "unsafe source snapshot path: $source"
    if [[ -n "$test_root" ]]; then
      ( set -o noclobber; /bin/cat -- "$source" > "$destination" ) ||
        fail "cannot snapshot fixture source: $source"
    else
      # The reader is deliberately unprivileged; the root shell must create
      # the destination inside its inaccessible snapshot directory.
      # shellcheck disable=SC2024
      ( set -o noclobber; /usr/bin/sudo -n -u "#$expected_uid" -- /bin/cat -- "$source" > "$destination" ) ||
        fail "cannot snapshot invoking-user source: $source"
    fi
    /bin/chmod 600 "$destination"
    [[ -f "$destination" && ! -L "$destination" &&
       "$(path_owner_mode "$destination")" == 0:0:600 && "$(path_nlink "$destination")" -eq 1 ]] ||
      fail "unsafe root snapshot destination: $destination"
  }

  finalize_receipt_ownership() {
    local current unsafe_entry item name
    [[ -d "$receipt_dir" && ! -L "$receipt_dir" ]] || return 1
    if [[ -z "$test_root" ]]; then
      root_receipt_parent_is_safe "$receipt_parent" "$device" || return 1
    fi
    current=$(path_identity "$receipt_dir") || return 1
    [[ "$current" == "$receipt_identity" ]] || return 1
    [[ "$(path_owner_mode "$receipt_dir")" == 0:0:700 ]] || return 1
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
    if [[ -n "$test_root" && "${R46H_V08_SEED_TEST_FAIL_RECEIPT_HANDOFF:-0}" == 1 ]]; then
      shopt -u nullglob dotglob
      return 1
    fi
    # Keep the top-level root-owned and inaccessible until every file has
    # been handed off. The directory chown is the final filesystem access.
    for item in "$receipt_dir"/*; do
      change_owner "$expected_uid:$expected_gid" "$item" || {
        shopt -u nullglob dotglob
        return 1
      }
    done
    shopt -u nullglob dotglob
    change_owner "$expected_uid:$expected_gid" "$receipt_dir"
    return $?
  }

  card_identity_matches() {
    if [[ -n "$test_root" ]]; then
      local fixture_identity
      [[ -f "$test_root/card-identity" ]] || {
        /usr/bin/printf 'WARNING: fixture identity file is unavailable: %s\n' "$test_root/card-identity" >&2
        return 1
      }
      fixture_identity=$(/usr/bin/tr -d '\r\n' < "$test_root/card-identity")
      [[ "$fixture_identity" == "whole=$WHOLE_SIZE;prefix=$PREFIX_SHA256;boot=$BOOT_UUID;root=$ROOT_PARTUUID;roms=$EASYROMS_UUID" ]] || {
        /usr/bin/printf 'WARNING: fixture identity mismatch: %s\n' "$fixture_identity" >&2
        return 1
      }
      return 0
    fi
    local whole_plist="$work_dir/identity-whole.plist"
    local p1_plist="$work_dir/identity-p1.plist"
    local p2_plist="$work_dir/identity-p2.plist"
    local p3_plist="$work_dir/identity-p3.plist"
    [[ -b "$device" && -c "$raw_device" && -b "$boot_partition" &&
       -c "$boot_raw_partition" && -b "$root_partition" && -c "$root_raw_partition" &&
       -b "$roms_partition" && ! -e "${device}s4" ]] || return 1
    /usr/sbin/diskutil info -plist "$device" > "$whole_plist" || return 1
    /usr/sbin/diskutil info -plist "$boot_partition" > "$p1_plist" || return 1
    /usr/sbin/diskutil info -plist "$root_partition" > "$p2_plist" || return 1
    /usr/sbin/diskutil info -plist "$roms_partition" > "$p3_plist" || return 1
    [[ "$(plist_value "$whole_plist" DeviceIdentifier)" == "$identifier" &&
       "$(plist_value "$whole_plist" WholeDisk)" == true &&
       "$(plist_value "$whole_plist" Content)" == FDisk_partition_scheme &&
       "$(plist_value "$whole_plist" Size)" == "$WHOLE_SIZE" &&
       "$(plist_value "$whole_plist" DeviceBlockSize)" == "$SECTOR_SIZE" &&
       "$(plist_value "$whole_plist" BusProtocol)" == USB &&
       "$(plist_value "$whole_plist" Internal)" == false &&
       "$(plist_value "$whole_plist" RemovableMedia)" == true &&
       "$(plist_value "$whole_plist" VirtualOrPhysical)" == Physical &&
       "$(plist_value "$whole_plist" Writable)" == true ]] || return 1
    [[ "$(plist_value "$p1_plist" ParentWholeDisk)" == "$identifier" &&
       "$(plist_value "$p1_plist" PartitionMapPartitionOffset)" == "$BOOT_OFFSET" &&
       "$(plist_value "$p1_plist" Size)" == "$BOOT_SIZE" &&
       "$(plist_value "$p1_plist" VolumeUUID)" == "$BOOT_UUID" &&
       "$(plist_value "$p1_plist" VolumeName)" == BOOT ]] || return 1
    [[ "$(plist_value "$p2_plist" ParentWholeDisk)" == "$identifier" &&
       "$(plist_value "$p2_plist" PartitionMapPartitionOffset)" == "$ROOT_OFFSET" &&
       "$(plist_value "$p2_plist" Size)" == "$ROOT_SIZE" ]] || return 1
    [[ "$(plist_value "$p3_plist" ParentWholeDisk)" == "$identifier" &&
       "$(plist_value "$p3_plist" PartitionMapPartitionOffset)" == "$EASYROMS_OFFSET" &&
       "$(plist_value "$p3_plist" Size)" == "$EASYROMS_SIZE" &&
       "$(plist_value "$p3_plist" VolumeUUID)" == "$EASYROMS_UUID" &&
       "$(plist_value "$p3_plist" VolumeName)" == EASYROMS ]]
  }

  set_mount_state() {
    local state=$1
    if [[ -n "$test_root" ]]; then
      /usr/bin/printf '%s\n' "$state" > "$test_root/mount-state"
      return 0
    fi
    case "$state" in
      unmounted) /usr/sbin/diskutil unmountDisk "$device" >/dev/null ;;
      roms) /usr/sbin/diskutil mount "$roms_partition" >/dev/null ;;
      ejected) /usr/sbin/diskutil eject "$device" >/dev/null ;;
      *) return 1 ;;
    esac
  }

  mount_state_is() {
    local expected=$1
    if [[ -n "$test_root" ]]; then
      [[ "$(/usr/bin/tr -d '\r\n' < "$test_root/mount-state")" == "$expected" ]]
      return $?
    fi
    local p1 p2 p3
    p1=$(/usr/sbin/diskutil info "$boot_partition") || return 1
    p2=$(/usr/sbin/diskutil info "$root_partition") || return 1
    p3=$(/usr/sbin/diskutil info "$roms_partition") || return 1
    case "$expected" in
      unmounted)
        /usr/bin/grep -Eq 'Mounted:[[:space:]]+No$' <<<"$p1" &&
        /usr/bin/grep -Eq 'Mounted:[[:space:]]+(No|Not applicable)' <<<"$p2" &&
        /usr/bin/grep -Eq 'Mounted:[[:space:]]+No$' <<<"$p3"
        ;;
      roms)
        /usr/bin/grep -Eq 'Mounted:[[:space:]]+No$' <<<"$p1" &&
        /usr/bin/grep -Eq 'Mounted:[[:space:]]+(No|Not applicable)' <<<"$p2" &&
        /usr/bin/grep -Eq 'Mounted:[[:space:]]+Yes$' <<<"$p3" &&
        /usr/bin/grep -Eq 'Mount Point:[[:space:]]+/Volumes/EASYROMS$' <<<"$p3"
        ;;
      *) return 1 ;;
    esac
  }

  unmount_card() {
    card_identity_matches || fail "card identity changed before unmount"
    /bin/sync || fail "cannot sync before unmount"
    set_mount_state unmounted || fail "cannot unmount the whole card"
    mount_state_is unmounted || fail "card is not fully unmounted"
  }

  mount_roms_only() {
    card_identity_matches || fail "card identity changed before p3 mount"
    set_mount_state roms || fail "cannot mount EASYROMS"
    mount_state_is roms || fail "mount state is not p3-only"
  }

  capture_evidence() {
    local suffix=$1 prefix_hash p1_hash p2_first p2_last
    mount_state_is unmounted || fail "raw evidence requires an unmounted card"
    if [[ -n "$test_root" ]]; then
      hash_file "$test_root/raw/prefix.bin" > "$receipt_dir/prefix-${suffix}.sha256"
      /bin/cp "$test_root/raw/fdisk.txt" "$receipt_dir/fdisk-${suffix}.txt"
      hash_file "$test_root/raw/p1.bin" > "$receipt_dir/p1-${suffix}.sha256"
      hash_file "$test_root/raw/p2-first.bin" > "$receipt_dir/p2-first-${suffix}.sha256"
      hash_file "$test_root/raw/p2-last.bin" > "$receipt_dir/p2-last-${suffix}.sha256"
    else
      prefix_hash=$(/bin/dd if="$raw_device" bs=1048576 count="$((PREFIX_SIZE / 1048576))" \
        2> "$receipt_dir/prefix-${suffix}-read.txt" |
        /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}')
      [[ "$prefix_hash" == "$PREFIX_SHA256" ]] || fail "g92 prefix SHA-256 mismatch"
      /usr/bin/printf '%s\n' "$prefix_hash" > "$receipt_dir/prefix-${suffix}.sha256"
      /usr/sbin/fdisk "$device" > "$receipt_dir/fdisk-${suffix}.txt"
      /usr/bin/grep -Eq '\[ +32768 - +229376\]' "$receipt_dir/fdisk-${suffix}.txt" ||
        fail "BOOT fdisk geometry mismatch"
      /usr/bin/grep -Eq '\[ +262144 - +20931401\]' "$receipt_dir/fdisk-${suffix}.txt" ||
        fail "root fdisk geometry mismatch"
      /usr/bin/grep -Eq '\[ +21193545 - +40758455\]' "$receipt_dir/fdisk-${suffix}.txt" ||
        fail "EASYROMS fdisk geometry mismatch"
      p1_hash=$(/usr/bin/shasum -a 256 "$boot_raw_partition" | /usr/bin/awk '{print $1}')
      /usr/bin/printf '%s\n' "$p1_hash" > "$receipt_dir/p1-${suffix}.sha256"
      p2_first=$(/bin/dd if="$root_raw_partition" bs="$SECTOR_SIZE" count="$ROOT_SAMPLE_SECTOR_COUNT" \
        2> "$receipt_dir/p2-first-${suffix}-read.txt" |
        /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}')
      p2_last=$(/bin/dd if="$root_raw_partition" bs="$SECTOR_SIZE" \
        skip="$((ROOT_SECTOR_COUNT - ROOT_SAMPLE_SECTOR_COUNT))" count="$ROOT_SAMPLE_SECTOR_COUNT" \
        2> "$receipt_dir/p2-last-${suffix}-read.txt" |
        /usr/bin/shasum -a 256 | /usr/bin/awk '{print $1}')
      /usr/bin/printf '%s\n' "$p2_first" > "$receipt_dir/p2-first-${suffix}.sha256"
      /usr/bin/printf '%s\n' "$p2_last" > "$receipt_dir/p2-last-${suffix}.sha256"
    fi
    if [[ "$suffix" != before ]]; then
      /usr/bin/cmp -s "$receipt_dir/prefix-before.sha256" "$receipt_dir/prefix-${suffix}.sha256" ||
        fail "g92 prefix changed"
      /usr/bin/cmp -s "$receipt_dir/fdisk-before.txt" "$receipt_dir/fdisk-${suffix}.txt" ||
        fail "partition table changed"
      /usr/bin/cmp -s "$receipt_dir/p1-before.sha256" "$receipt_dir/p1-${suffix}.sha256" ||
        fail "BOOT partition changed"
      /usr/bin/cmp -s "$receipt_dir/p2-first-before.sha256" "$receipt_dir/p2-first-${suffix}.sha256" ||
        fail "root partition first sample changed"
      /usr/bin/cmp -s "$receipt_dir/p2-last-before.sha256" "$receipt_dir/p2-last-${suffix}.sha256" ||
        fail "root partition last sample changed"
    fi
  }

  target_exists() { [[ -e "$1" || -L "$1" ]]; }
  target_hash() { hash_file "$1"; }

  appledouble_magic() {
    local magic
    [[ -f "$1" && ! -L "$1" ]] || return 1
    magic=$(/usr/bin/od -An -tx1 -N4 "$1" | /usr/bin/tr -d '[:space:]')
    [[ "$magic" == 00051607 ]]
  }

  remove_appledouble() {
    local path=$1 label=$2
    if target_exists "$path"; then
      appledouble_magic "$path" || fail "$label is not a proven AppleDouble file"
      /bin/rm -- "$path" || fail "cannot remove $label"
      ! target_exists "$path" || fail "$label remains after removal"
    fi
  }

  verify_blank_roms_root() {
    local item name unexpected
    shopt -s nullglob dotglob
    for item in "$roms_mount"/*; do
      name=${item##*/}
      case "$name" in
        .Spotlight-V100|.fseventsd)
          [[ -d "$item" && ! -L "$item" ]] || fail "unsafe EASYROMS metadata entry: $name"
          ;;
        .Trashes|.TemporaryItems)
          [[ -d "$item" && ! -L "$item" ]] || fail "unsafe EASYROMS metadata entry: $name"
          unexpected=$(/usr/bin/find "$item" -mindepth 1 -print -quit) ||
            fail "cannot inspect EASYROMS metadata entry: $name"
          [[ -z "$unexpected" ]] || fail "EASYROMS metadata directory is not empty: $name"
          ;;
        *) fail "EASYROMS is not blank: unexpected root entry $name" ;;
      esac
    done
    shopt -u nullglob dotglob
  }

  verify_roms_root_after_seed() {
    local item name unexpected saw_payload=0
    shopt -s nullglob dotglob
    for item in "$roms_mount"/*; do
      name=${item##*/}
      case "$name" in
        .Spotlight-V100|.fseventsd)
          [[ -d "$item" && ! -L "$item" ]] || fail "unsafe EASYROMS metadata entry: $name"
          ;;
        .Trashes|.TemporaryItems)
          [[ -d "$item" && ! -L "$item" ]] || fail "unsafe EASYROMS metadata entry: $name"
          unexpected=$(/usr/bin/find "$item" -mindepth 1 -print -quit) ||
            fail "cannot inspect EASYROMS metadata entry: $name"
          [[ -z "$unexpected" ]] || fail "EASYROMS metadata directory is not empty: $name"
          ;;
        "$PAYLOAD_NAME")
          [[ -d "$item" && ! -L "$item" ]] || fail "unsafe seeded payload directory"
          saw_payload=1
          ;;
        *) fail "unexpected EASYROMS root entry after seed: $name" ;;
      esac
    done
    shopt -u nullglob dotglob
    [[ "$saw_payload" -eq 1 ]] || fail "seeded payload directory is missing"
  }

  verify_payload_exact() {
    local include_complete=$1 item name expected_hash count=0 expected_count
    if [[ "$include_complete" -eq 1 ]]; then expected_count=$SOURCE_ENTRY_COUNT; else expected_count=$((SOURCE_ENTRY_COUNT - 1)); fi
    shopt -s nullglob dotglob
    for item in "$payload_final"/*; do
      [[ -f "$item" && ! -L "$item" ]] || fail "seeded payload contains a non-regular entry"
      name=${item##*/}
      [[ "$name" =~ ^[A-Za-z0-9._+-]+$ ]] || fail "unsafe seeded payload name: $name"
      [[ "$include_complete" -eq 1 || "$name" != STAGE-COMPLETE ]] ||
        fail "STAGE-COMPLETE appeared before the publication gate"
      expected_hash=$(source_entry "$source_list" "$name") ||
        fail "seeded payload contains an extra entry: $name"
      [[ "$(target_hash "$item")" == "$expected_hash" ]] ||
        fail "seeded payload SHA-256 mismatch: $name"
      count=$((count + 1))
    done
    shopt -u nullglob dotglob
    [[ "$count" -eq "$expected_count" ]] || fail "seeded payload file-set mismatch"
  }

  publish_file() {
    local source=$1 destination=$2 expected_hash=$3 label=$4
    local partial destination_sidecar partial_sidecar
    partial="$payload_final/.${label}.partial.$$"
    destination_sidecar="$payload_final/._${label}"
    partial_sidecar="$payload_final/._.${label}.partial.$$"
    mount_state_is roms || fail "$label publication requires a p3-only mount"
    ! target_exists "$destination" || fail "$label already exists"
    ! target_exists "$partial" || fail "$label partial already exists"
    ( set -o noclobber; /bin/cat "$source" > "$partial" ) || fail "cannot copy $label"
    if [[ -n "$test_root" ]]; then
      /usr/bin/printf '\x00\x05\x16\x07fixture-sidecar\n' > "$partial_sidecar"
    fi
    [[ "$(target_hash "$partial")" == "$expected_hash" ]] || fail "$label partial SHA-256 mismatch"
    remove_appledouble "$partial_sidecar" "$label partial AppleDouble"
    /bin/sync || fail "cannot sync $label partial"
    ! target_exists "$destination" || fail "$label appeared before publication"
    /bin/mv -n "$partial" "$destination" || fail "cannot publish $label"
    [[ ! -e "$partial" && "$(target_hash "$destination")" == "$expected_hash" ]] ||
      fail "$label publication verification failed"
    if [[ -n "$test_root" ]]; then
      /usr/bin/printf '\x00\x05\x16\x07fixture-sidecar\n' > "$destination_sidecar"
    fi
    remove_appledouble "$destination_sidecar" "$label AppleDouble"
    /bin/sync || fail "cannot sync published $label"
  }

  # Called only from the EXIT trap cleanup path.
  # shellcheck disable=SC2317
  invalidate_gate() {
    local gate
    [[ "$gate_published" -eq 1 && "$final_verified" -eq 0 ]] || return 0
    card_identity_matches || {
      /usr/bin/printf 'WARNING: card identity changed before gate invalidation\n' >&2
      return 1
    }
    set_mount_state unmounted >/dev/null 2>&1 || {
      /usr/bin/printf 'WARNING: cannot unmount for gate invalidation\n' >&2
      return 1
    }
    mount_state_is unmounted || {
      /usr/bin/printf 'WARNING: gate invalidation unmount was not proven\n' >&2
      return 1
    }
    set_mount_state roms >/dev/null 2>&1 || {
      /usr/bin/printf 'WARNING: cannot mount p3 for gate invalidation\n' >&2
      return 1
    }
    mount_state_is roms || {
      /usr/bin/printf 'WARNING: gate invalidation p3-only mount was not proven\n' >&2
      return 1
    }
    gate="$payload_final/STAGE-COMPLETE"
    if target_exists "$gate"; then
      [[ -f "$gate" && ! -L "$gate" && "$(target_hash "$gate")" == "$STAGE_COMPLETE_SHA256" ]] || {
        /usr/bin/printf 'WARNING: refusing to remove an unproven completion gate\n' >&2
        return 1
      }
      /bin/rm -- "$gate" || {
        /usr/bin/printf 'WARNING: cannot remove the proven completion gate\n' >&2
        return 1
      }
      /bin/sync || {
        /usr/bin/printf 'WARNING: cannot sync completion-gate invalidation\n' >&2
        return 1
      }
    fi
    remove_appledouble "$payload_final/._STAGE-COMPLETE" "gate AppleDouble" || return 1
  }

  # Installed below as an EXIT trap rather than called directly.
  # shellcheck disable=SC2317
  cleanup() {
    local status=$?
    local work_removed=1
    [[ "$cleanup_running" -eq 0 ]] || exit "$status"
    cleanup_running=1
    trap - EXIT INT TERM HUP
    trap '' INT TERM HUP
    set +e
    if [[ "$completed" -ne 1 ]]; then
      invalidate_gate || /usr/bin/printf 'WARNING: could not prove STAGE-COMPLETE invalidation\n' >&2
      if [[ "$card_access_started" -eq 1 ]]; then
        if card_identity_matches; then
          set_mount_state unmounted >/dev/null 2>&1 ||
            /usr/bin/printf 'WARNING: could not leave the failed card unmounted\n' >&2
        else
          /usr/bin/printf 'WARNING: card identity is unavailable; cleanup will not touch the device path\n' >&2
        fi
      fi
      if [[ -n "$status_file" && -d "$receipt_dir" ]]; then
        /usr/bin/printf '%s\n' \
          '{"format_version":1,"state":"SEED_FAILED","safe_to_execute":false}' > "$status_file"
        /usr/bin/touch "$receipt_dir/FAILED"
      fi
      if [[ -n "$work_dir" && -e "$work_dir" ]]; then
        if [[ -d "$receipt_dir" && ! -L "$receipt_dir" &&
           "$(path_identity "$receipt_dir")" == "$receipt_identity" ]]; then
          if [[ -n "$test_root" && "${R46H_V08_SEED_TEST_FAIL_WORK_REMOVAL:-0}" == 1 ]]; then
            work_removed=0
          else
            /bin/rm -rf -- "$work_dir"
            [[ ! -e "$work_dir" ]] || work_removed=0
          fi
        else
          work_removed=0
        fi
      fi
    fi
    if [[ "$work_removed" -eq 1 ]]; then
      finalize_receipt_ownership || status=74
    else
      status=74
      /usr/bin/printf 'WARNING: private source snapshot was not removed; receipt remains root-owned\n' >&2
    fi
    if [[ "$completed" -ne 1 && -n "$receipt_dir" ]]; then
      /usr/bin/printf 'Seed failed closed. Never execute scripts from the partial payload.\n' >&2
      /usr/bin/printf 'RECEIPT_DIR=%s\n' "$receipt_dir" >&2
    elif [[ "$completed" -eq 1 && "$status" -ne 0 ]]; then
      /usr/bin/printf 'WARNING: media seed completed, but receipt handoff failed; audit the root-owned receipt\n' >&2
      /usr/bin/printf 'RECEIPT_DIR=%s\n' "$receipt_dir" >&2
    fi
    exit "$status"
  }
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP

  copy_invoking_user_file "$source_bundle/STAGE-SOURCES.sha256" \
    "$snapshot_bundle/STAGE-SOURCES.sha256"
  [[ "$(hash_file "$snapshot_bundle/STAGE-SOURCES.sha256")" == "$SOURCE_LIST_SHA256" ]] ||
    fail "root snapshot source-list SHA-256 mismatch"
  while read -r source_hash source_path source_extra; do
    [[ -z "${source_extra:-}" && "$source_hash" =~ ^[0-9a-f]{64}$ &&
       "$source_path" =~ ^payload/[A-Za-z0-9._+-]+$ ]] || fail "unsafe source during snapshot"
    source_name=${source_path#payload/}
    copy_invoking_user_file "$source_bundle/payload/$source_name" \
      "$snapshot_bundle/payload/$source_name"
  done < "$snapshot_bundle/STAGE-SOURCES.sha256"
  validate_source_bundle "$snapshot_bundle"
  source_list="$snapshot_bundle/STAGE-SOURCES.sha256"
  source_root="$snapshot_bundle/payload"

  if [[ -n "$test_root" ]]; then
    roms_mount="$test_root/card/easyroms"
  else
    roms_mount=/Volumes/EASYROMS
  fi
  payload_final="$roms_mount/$PAYLOAD_NAME"
  payload_root_sidecar="$roms_mount/._$PAYLOAD_NAME"

  /usr/bin/printf '%s\n' \
    '{"format_version":1,"state":"SEED_IN_PROGRESS","safe_to_execute":false}' > "$status_file"
  /bin/cp "$source_list" "$receipt_dir/CANONICAL-STAGE-SOURCES.sha256"
  copy_invoking_user_file "$prior_audit_dir/AUDIT-STATUS.json" \
    "$snapshot_audit/AUDIT-STATUS.json"
  copy_invoking_user_file "$prior_audit_dir/AUDIT-COMPLETE" \
    "$snapshot_audit/AUDIT-COMPLETE"
  validate_prior_audit_files "$snapshot_audit" 0
  /bin/cp "$snapshot_audit/AUDIT-STATUS.json" "$receipt_dir/PRIOR-AUDIT-STATUS.json"
  /bin/cp "$snapshot_audit/AUDIT-COMPLETE" "$receipt_dir/PRIOR-AUDIT-COMPLETE"
  validate_prior_audit_files "$receipt_dir" 0 \
    PRIOR-AUDIT-STATUS.json PRIOR-AUDIT-COMPLETE
  if [[ -n "$test_root" && "${R46H_V08_SEED_TEST_FAIL_AFTER_AUDIT_FREEZE:-0}" == 1 ]]; then
    fail "injected failure after prior-audit freeze"
  fi
  /usr/bin/printf '%s\n' \
    'format_version=1' \
    'purpose=v0.8-baseline-anchor-seed-only' \
    "payload=$PAYLOAD_NAME" \
    "source_list_sha256=$SOURCE_LIST_SHA256" \
    'source_file_count=11' \
    "prior_full_p2_audit_status_sha256=$PRIOR_AUDIT_STATUS_SHA256" \
    "prior_full_p2_audit_p2_sha256=$PRIOR_AUDIT_P2_SHA256" \
    'prior_full_p2_audit_safe_to_boot=yes' \
    'full_p2_hash_verified_during_seed=no' \
    'target_scripts_must_not_be_executed=yes' \
    'target_trust_receipt_generated=no' \
    'external_completion_secret_generated=no' > "$receipt_dir/SEED-INTENT"

  card_access_started=1
  card_identity_matches || fail "$device is not the audited Debian 13 R46H card"
  unmount_card
  capture_evidence before
  mount_roms_only
  verify_blank_roms_root
  [[ ! -e "$payload_final" && ! -L "$payload_final" ]] || fail "v0.8 payload already exists"
  /bin/mkdir "$payload_final" || fail "cannot create v0.8 seed directory"
  if [[ -n "$test_root" ]]; then
    /usr/bin/printf '\x00\x05\x16\x07fixture-directory-sidecar\n' > "$payload_root_sidecar"
  fi

  while read -r source_hash source_path source_extra; do
    source_name=${source_path#payload/}
    [[ "$source_name" == STAGE-COMPLETE ]] && continue
    publish_file "$source_root/$source_name" "$payload_final/$source_name" "$source_hash" "$source_name"
  done < "$source_list"
  remove_appledouble "$payload_root_sidecar" "payload directory AppleDouble"
  verify_payload_exact 0
  verify_roms_root_after_seed

  unmount_card
  capture_evidence after-body
  mount_roms_only
  verify_payload_exact 0
  verify_roms_root_after_seed

  gate_published=1
  publish_file "$source_root/STAGE-COMPLETE" "$payload_final/STAGE-COMPLETE" \
    "$STAGE_COMPLETE_SHA256" STAGE-COMPLETE
  if [[ -n "$test_root" && "${R46H_V08_SEED_TEST_FAIL_AFTER_GATE:-0}" == 1 ]]; then
    fail "injected failure after STAGE-COMPLETE publication"
  fi
  remove_appledouble "$payload_root_sidecar" "payload directory AppleDouble"
  verify_payload_exact 1
  verify_roms_root_after_seed

  unmount_card
  capture_evidence after-complete
  mount_roms_only
  verify_payload_exact 1
  verify_roms_root_after_seed
  final_verified=1
  unmount_card
  set_mount_state ejected || fail "cannot safely eject card"
  ejected=1

  /usr/bin/printf '%s\n' \
    'format_version=1' \
    'status=complete' \
    'purpose=v0.8-baseline-anchor-seed-only' \
    "device=$device" \
    "payload=$PAYLOAD_NAME" \
    "canonical_source_list_sha256=$SOURCE_LIST_SHA256" \
    'canonical_file_count=11' \
    'only_written_partition=3' \
    'bootloader_prefix=unchanged' \
    'partition_table=unchanged' \
    'boot_partition=unchanged-full-raw-sha256' \
    'root_partition=never-mounted-boundary-samples-unchanged' \
    'full_p2_hash_verified_during_seed=no' \
    "prior_full_p2_audit_status_sha256=$PRIOR_AUDIT_STATUS_SHA256" \
    "prior_full_p2_audit_p2_sha256=$PRIOR_AUDIT_P2_SHA256" \
    'prior_full_p2_audit_safe_to_boot=yes' \
    'target_trust_receipt_generated=no' \
    'external_completion_secret_generated=no' \
    'seeded_target_scripts_authorized=no' \
    'seeded_target_scripts_must_not_be_executed=yes' > "$receipt_dir/SEED-RESULT"
  /usr/bin/printf '%s\n' \
    '{"format_version":1,"state":"SEED_COMPLETE","safe_to_execute":false,"next":"stage-v0.9-bundle"}' > "$status_file"
  /usr/bin/touch "$receipt_dir/EJECTED"
  [[ "$ejected" -eq 1 ]] || fail "eject completion was not recorded"
  /bin/rm -rf -- "$work_dir"
  [[ ! -e "$work_dir" ]] || fail "cannot remove private source snapshot"
  /bin/sync || fail "cannot sync seed receipt"
  /usr/bin/touch "$receipt_dir/COMPLETE"
  /bin/sync || fail "cannot publish seed receipt completion"
  completed=1
  finalize_receipt_ownership || fail "cannot finalize seed receipt ownership"
  trap - EXIT INT TERM HUP

  /usr/bin/printf 'PASS: canonical v0.8 baseline anchors were seeded to blank EASYROMS only.\n'
  /usr/bin/printf 'SAFE_TO_EXECUTE=no\nTARGET_TRUST_RECEIPT_GENERATED=no\nRECEIPT_DIR=%s\n' "$receipt_dir"
}

usage() {
  /bin/cat <<'EOF'
usage: mainline/scripts/seed-v08-baseline-on-debian13-new-card.sh \
  --device /dev/diskN --confirm-device /dev/diskN \
  --prior-audit-dir /absolute/.r46h-new-card-postwrite.RECEIPT \
  --prior-audit-status-sha256 <literal-sha256> \
  [--receipt-parent /private/tmp]

Seeds only the exact canonical v0.8 EASYROMS payload directory onto the
audited 31,719,424,000-byte Debian 13 card. EASYROMS must otherwise be blank.
The embedded scripts are baseline anchors only and MUST NOT be executed.
No TARGET-TRUST-RECEIPT or external completion secret is generated.
EOF
}

if [[ "${1:-}" == --internal-root-worker ]]; then
  [[ "$#" -eq 10 ]] || fail "invalid internal seed-worker argument count"
  seed_worker "$2" "$3" "$4" "$5" "$6" "$7" "$8" "$9" "${10}"
  exit 0
fi

device=
confirm_device=
receipt_parent=$DEFAULT_RECEIPT_PARENT
prior_audit_dir=
prior_audit_status_hash=
while (( $# > 0 )); do
  case "$1" in
    --device) [[ $# -ge 2 ]] || { usage >&2; exit 64; }; device=$2; shift 2 ;;
    --confirm-device) [[ $# -ge 2 ]] || { usage >&2; exit 64; }; confirm_device=$2; shift 2 ;;
    --receipt-parent) [[ $# -ge 2 ]] || { usage >&2; exit 64; }; receipt_parent=$2; shift 2 ;;
    --prior-audit-dir) [[ $# -ge 2 ]] || { usage >&2; exit 64; }; prior_audit_dir=$2; shift 2 ;;
    --prior-audit-status-sha256) [[ $# -ge 2 ]] || { usage >&2; exit 64; }; prior_audit_status_hash=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) /usr/bin/printf 'ERROR: unknown option: %s\n' "$1" >&2; usage >&2; exit 64 ;;
  esac
done

[[ "$device" =~ ^/dev/disk[1-9][0-9]*$ && "$device" == "$confirm_device" &&
   "$device" != /dev/disk6 ]] || fail "device confirmation mismatch or unsafe target"
[[ "$prior_audit_dir" == /* && "$prior_audit_status_hash" =~ ^[0-9a-f]{64}$ ]] ||
  fail "prior full-p2 audit directory and literal status SHA-256 are required"

test_root=${R46H_V08_SEED_TEST_ROOT:-}
source_bundle=$SOURCE_BUNDLE_DEFAULT
if [[ -n "$test_root" ]]; then
  [[ -f /.dockerenv && "$EUID" -eq 0 ]] || fail "seed fixture mode is container-root only"
  source_bundle=${R46H_V08_SEED_TEST_SOURCE_BUNDLE:-$SOURCE_BUNDLE_DEFAULT}
  receipt_parent=$(cd -- "$receipt_parent" && /bin/pwd -P)
  validate_source_bundle "$source_bundle"
  seed_worker "$device" "$receipt_parent" 12345 12345 "$source_bundle" fixture \
    "$prior_audit_dir" "$prior_audit_status_hash" "$test_root"
  exit 0
fi

[[ "$(/usr/bin/uname -s)" == Darwin ]] || fail "production seed requires macOS"
validate_source_bundle "$source_bundle"
expected_uid=$(/usr/bin/id -u)
expected_gid=$(/usr/bin/id -g)
validate_prior_audit_source "$prior_audit_dir" "$expected_uid" "$device" \
  "$prior_audit_status_hash" ''
receipt_parent=$(cd -- "$receipt_parent" && /bin/pwd -P)
root_receipt_parent_identity_is_safe "$receipt_parent" "$DEFAULT_RECEIPT_PARENT" ||
  fail "receipt parent must be the root-owned sticky /private/tmp"
path_is_on_other_physical_disk "$receipt_parent" "$device" ||
  fail "cannot prove that /private/tmp is on a physical disk different from the target card"
script_hash=$(hash_file "$SCRIPT_PATH")
[[ "$script_hash" =~ ^[0-9a-f]{64}$ ]] || fail "cannot hash seed worker script"

/usr/bin/printf 'R46H Debian 13 new-card canonical v0.8 baseline seed\n'
/usr/bin/printf 'target=%s exact_size=%s write_scope=p3-only\n' "$device" "$WHOLE_SIZE"
/usr/bin/printf 'The 11 seeded files are baseline anchors only; target execution is not authorized.\n'
/usr/bin/printf 'One administrator authorization is used for audited reads, fixed p3 writes, and safe eject.\n'
/usr/bin/sudo -v || fail "administrator authorization failed"

# The root process loads this same script, rechecks its exact SHA-256, and
# accepts only this fixed internal argument vector.
/usr/bin/sudo -- /bin/bash "$SCRIPT_PATH" --internal-root-worker \
  "$device" "$receipt_parent" "$expected_uid" "$expected_gid" \
  "$source_bundle" "$script_hash" "$prior_audit_dir" "$prior_audit_status_hash" ''
