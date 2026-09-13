#!/bin/bash
set -Eeuo pipefail
umask 077

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
IFS=$' \t\n'
export PATH LC_ALL LANG
unset BASH_ENV CDPATH ENV

readonly PAYLOAD_ID=r46h-v16-boot-promotion-v0.1
readonly TOOL_ID=r46h-v16-boot-promotion-v0.1
readonly RUN_PAYLOAD=/run/r46h-v16-boot-promotion-v0.1
readonly STATE_PARENT=/var/lib/r46h-boot-promotion
readonly STATE_STAGE=/var/lib/r46h-boot-promotion/.v0.16-disable-secondary.stage
readonly STATE_DIR=/var/lib/r46h-boot-promotion/v0.16-disable-secondary
readonly RETAINED_PAYLOAD=/var/lib/r46h-boot-promotion/v0.16-disable-secondary/payload
readonly STATUS_FILE=/var/lib/r46h-boot-promotion/v0.16-disable-secondary/STATUS
readonly STATUS_STAGE=/var/lib/r46h-boot-promotion/v0.16-disable-secondary/.STATUS.stage
readonly LOCK_FILE=/run/r46h-v16-boot-promotion.lock
readonly PRODUCT_KERNEL_DIR=/var/lib/r46h-gaming-product-kernel/v0.15-gaming-product
readonly PRODUCT_IMAGE=/var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/IMAGE
readonly PRODUCT_DTB=/var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/R46H.DTB
readonly PRODUCT_RECEIPT=/var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/RECEIPT
readonly GAMING_RECEIPT=/var/lib/r46h/gaming-mvp-v0.4-installed
readonly RETROARCH_CONFIG=/etc/r46h/retroarch.cfg
readonly STORAGE_AUDIT=/usr/local/sbin/r46h-storage-audit
readonly MODULES_PARENT=/usr/lib/modules
readonly EXPECTED_RUNNING_RELEASE=6.12.99-r46h-mainline-v0.15-gaming-product
readonly EXPECTED_ROOT_PARTUUID=c9f931c9-02
readonly EXPECTED_BOOT_PARTUUID=c9f931c9-01
readonly EXPECTED_ROMS_PARTUUID=c9f931c9-03
readonly EXPECTED_ROOT_UUID=d3130005-46a4-4d56-9001-000000000005
readonly EXPECTED_ROOT_LABEL=R46H_GAMING_V05
readonly EXPECTED_WHOLE_SIZE=62534975488
readonly EXPECTED_BOOT_SIZE=117440512
readonly EXPECTED_ROOT_SIZE=10716877312
readonly EXPECTED_ROMS_SIZE=51683880448
readonly EXPECTED_SECTOR_SIZE=512
readonly EXPECTED_PREFIX_SIZE=16777216
readonly EXPECTED_PREFIX_SHA256=3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3
readonly EXPECTED_BASE_P1_SHA256=042ad4ad08f39f60f1d57e393ab32ae148e2a946ab9996822ae161934f7a0825
readonly EXPECTED_FIRSTBOOT='release=debian13-p2-gaming-v0.5'
readonly EXPECTED_PRODUCT_IMAGE_SIZE=41570816
readonly EXPECTED_PRODUCT_IMAGE_SHA256=956ab3d5a2e53afbfe964ae75850e8591b44c093b9779867b31149b7b591f68f
readonly EXPECTED_PRODUCT_DTB_SIZE=49518
readonly EXPECTED_PRODUCT_DTB_SHA256=4d6d4ebad3b98600b6e9a38df4ca82230335558497a9e15dd0e81ca60e304b61
readonly EXPECTED_PRODUCT_RECEIPT_SHA256=a90b359f2275bdc732b5814bf9d1dc328844532a1e3c2a4d23577068978fffbd
readonly EXPECTED_GAMING_RECEIPT_SHA256=0a0675e82aa35fb22252de2d688fa280275e52634ef9a130c5e415ba2cc04666
readonly EXPECTED_RETROARCH_CONFIG_SHA256=99a45beb148e58e40983773b4f5e26d9fb5d7e1bbbf6a7e714a5c352e43c0dba
readonly EXPECTED_STORAGE_AUDIT_SHA256=08ed33dace8a94a6b129d72896c8e6a657b32d15c74d9ecf48df99a9f49ae95c
readonly PREPARE_CONFIRM=prepare-v0.16-keep-v0.15-active
readonly PREPARE_RECOVERY_CONFIRM=recover-v0.16-versioned-files
readonly ACTIVATE_CONFIRM=activate-v0.16-keep-v0.15-v0.10-v0.8
readonly ACTIVATE_RECOVERY_CONFIRM=recover-v0.16-active-switch
readonly ROLLBACK_CONFIRM=rollback-active-to-v0.15

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

hash_file() {
  sha256sum "$1" | awk '{print $1}'
}

check_file() {
  local path=$1 expected_size=$2 expected_hash=$3 label=$4
  [[ -f "$path" && ! -L "$path" ]] || die "unsafe or missing ${label}"
  [[ "$(stat -c '%h' "$path")" == 1 ]] || die "unexpected link count for ${label}"
  [[ "$(stat -c '%s' "$path")" == "$expected_size" ]] || die "size mismatch for ${label}"
  [[ "$(hash_file "$path")" == "$expected_hash" ]] || die "SHA-256 mismatch for ${label}"
}

require_identity() {
  local path=$1 mode_bits=$2 label=$3
  [[ -f "$path" && ! -L "$path" ]] || die "unsafe or missing ${label}"
  [[ "$(stat -c '%u:%g:%a:%h' "$path")" == "0:0:${mode_bits}:1" ]] || \
    die "identity mismatch for ${label}"
}

require_directory() {
  local path=$1 mode_bits=$2 label=$3
  [[ -d "$path" && ! -L "$path" ]] || die "unsafe or missing ${label}"
  [[ "$(stat -c '%u:%g:%a' "$path")" == "0:0:${mode_bits}" ]] || \
    die "identity mismatch for ${label}"
}

validate_payload() {
  local payload=$1 members expected
  [[ -d "$payload" && ! -L "$payload" ]] || die 'unsafe payload directory'
  members=$(cd "$payload" && find . -mindepth 1 -maxdepth 2 -print | \
    sed 's#^\./##' | LC_ALL=C sort)
  expected=$'PAYLOAD-INFO.json\nPAYLOAD.COMPLETE\nSHA256SUMS\nfallback-modules.sh\nfiles\nfiles/boot.ini.v0.16-disable-secondary\nfiles/rk3326-r46h-mainline-v0.16-disable-secondary.dtb\ninstall.sh\nstorage-health.sh\ntransaction.sh'
  [[ "$members" == "$expected" ]] || die 'unexpected payload member set'
  [[ -z "$(find "$payload" -xdev -type l -print -quit)" ]] || \
    die 'payload contains a symbolic link'
  [[ -z "$(find "$payload" -xdev ! -type d ! -type f -print -quit)" ]] || \
    die 'payload contains a special file'
  [[ -z "$(find "$payload" -xdev -type f ! -links 1 -print -quit)" ]] || \
    die 'payload contains a hard-linked file'
  (cd "$payload" && sha256sum -c SHA256SUMS) || \
    die 'payload checksum verification failed'
  [[ "$(<"$payload/PAYLOAD.COMPLETE")" == \
    "sha256sums_sha256=$(hash_file "$payload/SHA256SUMS")" ]] || \
    die 'payload completion marker mismatch'
}

verify_payload_identity() {
  local payload=$1 name
  require_directory "$payload" 700 'payload directory'
  require_directory "$payload/files" 700 'payload files directory'
  require_identity "$payload/install.sh" 500 'installer'
  for name in \
    PAYLOAD-INFO.json PAYLOAD.COMPLETE SHA256SUMS fallback-modules.sh \
    storage-health.sh transaction.sh \
    files/boot.ini.v0.16-disable-secondary \
    files/rk3326-r46h-mainline-v0.16-disable-secondary.dtb; do
    require_identity "$payload/$name" 400 "payload member $name"
  done
}

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly SCRIPT_DIR
validate_payload "$SCRIPT_DIR"

if [[ $# == 1 && $1 == --check-payload ]]; then
  printf 'PASS: exact %s payload structure and checksums validated.\n' "$PAYLOAD_ID"
  exit 0
fi

(( EUID == 0 )) || die 'root is required'
case "$SCRIPT_DIR" in
  "$RUN_PAYLOAD"|"$RETAINED_PAYLOAD") ;;
  *) die "run from $RUN_PAYLOAD or $RETAINED_PAYLOAD" ;;
esac
verify_payload_identity "$SCRIPT_DIR"
[[ -z "${R46H_TRANSACTION_TEST_MODE+x}" && -z "${R46H_TRANSACTION_FAULT+x}" ]] || \
  die 'transaction test environment is forbidden in the target wrapper'
# shellcheck source=transaction.sh
source "$SCRIPT_DIR/transaction.sh"
# shellcheck source=fallback-modules.sh
source "$SCRIPT_DIR/fallback-modules.sh"
# shellcheck source=storage-health.sh
source "$SCRIPT_DIR/storage-health.sh"

mode=
case "$#:$*" in
  '1:--preflight') mode=preflight ;;
  '1:--postflight') mode=postflight ;;
  "3:--prepare --confirm $PREPARE_CONFIRM") mode=prepare ;;
  "3:--recover-prepare --confirm $PREPARE_RECOVERY_CONFIRM") mode=recover-prepare ;;
  "3:--activate --confirm $ACTIVATE_CONFIRM") mode=activate ;;
  "3:--recover-activate --confirm $ACTIVATE_RECOVERY_CONFIRM") mode=recover-activate ;;
  "3:--rollback --confirm $ROLLBACK_CONFIRM") mode=rollback ;;
  *)
    die "usage: install.sh --preflight | --postflight | --prepare --confirm $PREPARE_CONFIRM | --recover-prepare --confirm $PREPARE_RECOVERY_CONFIRM | --activate --confirm $ACTIVATE_CONFIRM | --recover-activate --confirm $ACTIVATE_RECOVERY_CONFIRM | --rollback --confirm $ROLLBACK_CONFIRM"
    ;;
esac

exec 9>"$LOCK_FILE"
flock -n 9 || die 'another v0.16 BOOT promotion process holds the lock'

WORK_DIR=
BOOT_MOUNT=
SOURCE_DIR=
BOOT_MOUNTED=0
BOOT_DEVICE=
R46H_BOOT_DEVICE=
ROOT_DEVICE=
ROMS_DEVICE=
WHOLE_DEVICE=
STATUS_STATE=absent
STATUS_P1_SHA256=
STATUS_ACTIVE_SHA256=
STATUS_STAGE_PRESENT=0
BOOT_STATE=
P1_SHA256=

cleanup() {
  local status=$? can_remove_work=1 mount_target
  trap - EXIT INT TERM HUP
  set +e
  if (( BOOT_MOUNTED == 1 )); then
    if umount "$BOOT_MOUNT"; then
      BOOT_MOUNTED=0
    else
      can_remove_work=0
      printf 'HARD WARNING: private BOOT unmount failed; retaining work directory and do not reboot or power off\n' >&2
    fi
  fi
  if [[ -n "$WORK_DIR" ]]; then
    case "$WORK_DIR" in
      /run/r46h-v16-boot-promotion.*)
        while IFS= read -r mount_target; do
          case "$mount_target" in
            "$WORK_DIR"|"$WORK_DIR"/*) can_remove_work=0 ;;
          esac
        done < <(findmnt -rn -o TARGET)
        if (( can_remove_work == 1 )); then
          rm -rf -- "$WORK_DIR"
        else
          printf 'HARD WARNING: work directory contains a mount; cleanup was refused: %s\n' \
            "$WORK_DIR" >&2
        fi
        ;;
      *) printf 'WARNING: refusing unexpected work cleanup path: %s\n' "$WORK_DIR" >&2 ;;
    esac
  fi
  rm -f "$LOCK_FILE"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

begin_write() {
  trap '' INT TERM HUP
}

verify_product() {
  local root_uuid root_label
  require_identity /var/lib/r46h/firstboot-complete 600 'firstboot completion marker'
  [[ "$(< /var/lib/r46h/firstboot-complete)" == "$EXPECTED_FIRSTBOOT" ]] || \
    die 'firstboot completion marker mismatch'
  root_uuid=$(findmnt -rn -o UUID /)
  root_label=$(findmnt -rn -o LABEL /)
  [[ "$root_uuid" == "$EXPECTED_ROOT_UUID" ]] || die 'unexpected root UUID'
  [[ "$root_label" == "$EXPECTED_ROOT_LABEL" ]] || die 'unexpected root label'
  require_directory "$PRODUCT_KERNEL_DIR" 700 'product kernel directory'
  check_file "$PRODUCT_IMAGE" "$EXPECTED_PRODUCT_IMAGE_SIZE" \
    "$EXPECTED_PRODUCT_IMAGE_SHA256" 'product Image'
  check_file "$PRODUCT_DTB" "$EXPECTED_PRODUCT_DTB_SIZE" \
    "$EXPECTED_PRODUCT_DTB_SHA256" 'v0.15 fallback DTB'
  require_identity "$PRODUCT_RECEIPT" 400 'product kernel receipt'
  [[ "$(hash_file "$PRODUCT_RECEIPT")" == "$EXPECTED_PRODUCT_RECEIPT_SHA256" ]] || \
    die 'product kernel receipt mismatch'
  require_identity "$GAMING_RECEIPT" 600 'gaming receipt'
  [[ "$(hash_file "$GAMING_RECEIPT")" == "$EXPECTED_GAMING_RECEIPT_SHA256" ]] || \
    die 'gaming receipt mismatch'
  require_identity "$RETROARCH_CONFIG" 644 'RetroArch config'
  [[ "$(hash_file "$RETROARCH_CONFIG")" == "$EXPECTED_RETROARCH_CONFIG_SHA256" ]] || \
    die 'RetroArch config mismatch'
  require_identity "$STORAGE_AUDIT" 755 'storage audit'
  [[ "$(hash_file "$STORAGE_AUDIT")" == "$EXPECTED_STORAGE_AUDIT_SHA256" ]] || \
    die 'storage audit mismatch'
}

verify_runtime_health() {
  local ext4_errors kernel_log storage_state
  [[ "$(uname -r)" == "$EXPECTED_RUNNING_RELEASE" ]] || die 'unexpected running kernel'
  [[ "$(findmnt -rn -o PARTUUID /)" == "$EXPECTED_ROOT_PARTUUID" ]] || \
    die 'unexpected root PARTUUID'
  [[ "$(findmnt -rn -o FSTYPE /)" == ext4 ]] || die 'root is not ext4'
  [[ ",$(findmnt -rn -o OPTIONS /)," == *,rw,* ]] || die 'root is not writable'
  ext4_errors=/sys/fs/ext4/$(basename "$ROOT_DEVICE")/errors_count
  [[ -f "$ext4_errors" && "$(<"$ext4_errors")" == 0 ]] || \
    die 'root ext4 error counter is nonzero or unavailable'
  [[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd has failed units'
  [[ "$(systemctl is-active r46h-gaming-frontend.service || true)" == inactive ]] || \
    die 'stop the gaming frontend before BOOT promotion'
  [[ -z "$(pgrep -x retroarch || true)" ]] || die 'RetroArch is still running'
  [[ -z "$(find /run -maxdepth 1 -type d -name 'r46h-game-ui.*' -print -quit)" ]] || \
    die 'a game session directory remains'
  [[ -z "$(findmnt -rn -S "$BOOT_DEVICE")" ]] || die 'BOOT became mounted'
  [[ -z "$(findmnt -rn -S "$ROMS_DEVICE")" ]] || die 'ROMS became mounted'
  kernel_log=$(dmesg --color=never)
  ! printf '%s\n' "$kernel_log" | grep -Eqi \
    'Timeout waiting for hardware cmd interrupt|card stuck being busy|EXT4-fs (error|warning)|Buffer I/O error|I/O error, dev mmcblk0|mmc1: (error|timeout)' || \
    die 'runtime contains an unaccepted storage fault marker'
  storage_state=$(printf '%s\n' "$kernel_log" | r46h_storage_health_from_log) || \
    die 'current boot contains an unaccepted storage fault marker'
  case "$storage_state" in clean|recovered-known-open) ;;
    *) die 'unsupported storage-health state' ;;
  esac
}

verify_module_fallbacks() {
  r46h_mod_verify_tree "$MODULES_PARENT" installed || \
    die 'v0.10 fallback module tree verification failed'
  r46h_mod_verify_existing_fallbacks "$MODULES_PARENT" || \
    die 'v0.8/v0.15 module fallback verification failed'
}

partition_parent() {
  lsblk -ndo PKNAME "$1"
}

verify_partition_geometry() {
  local device=$1 start=$2 sectors=$3 name
  name=${device##*/}
  [[ "$(<"/sys/class/block/$name/start")" == "$start" ]] || \
    die "partition start mismatch: ${name}"
  [[ "$(<"/sys/class/block/$name/size")" == "$sectors" ]] || \
    die "partition size mismatch: ${name}"
}

discover_devices() {
  local root_source boot_alias root_alias roms_alias parent
  root_source=$(findmnt -rn -o SOURCE /)
  ROOT_DEVICE=$(readlink -f "$root_source")
  boot_alias=$(readlink -f "/dev/disk/by-partuuid/$EXPECTED_BOOT_PARTUUID")
  root_alias=$(readlink -f "/dev/disk/by-partuuid/$EXPECTED_ROOT_PARTUUID")
  roms_alias=$(readlink -f "/dev/disk/by-partuuid/$EXPECTED_ROMS_PARTUUID")
  [[ -b "$ROOT_DEVICE" && -b "$boot_alias" && -b "$root_alias" && -b "$roms_alias" ]] || \
    die 'required partition aliases are not block devices'
  [[ "$ROOT_DEVICE" == "$root_alias" ]] || die 'root source does not match fixed PARTUUID'
  BOOT_DEVICE=$boot_alias
  ROOT_DEVICE=$root_alias
  ROMS_DEVICE=$roms_alias
  parent=$(partition_parent "$ROOT_DEVICE")
  [[ -n "$parent" && "$(partition_parent "$BOOT_DEVICE")" == "$parent" && \
    "$(partition_parent "$ROMS_DEVICE")" == "$parent" ]] || \
    die 'partition parents do not identify one card'
  WHOLE_DEVICE=/dev/$parent
  [[ -b "$WHOLE_DEVICE" ]] || die 'whole-card device is missing'
  [[ "$(blockdev --getsize64 "$WHOLE_DEVICE")" == "$EXPECTED_WHOLE_SIZE" ]] || \
    die 'whole-card size mismatch'
  [[ "$(blockdev --getss "$WHOLE_DEVICE")" == "$EXPECTED_SECTOR_SIZE" ]] || \
    die 'logical sector size mismatch'
  [[ "$(blockdev --getsize64 "$BOOT_DEVICE")" == "$EXPECTED_BOOT_SIZE" ]] || \
    die 'BOOT partition size mismatch'
  [[ "$(blockdev --getsize64 "$ROOT_DEVICE")" == "$EXPECTED_ROOT_SIZE" ]] || \
    die 'root partition size mismatch'
  [[ "$(blockdev --getsize64 "$ROMS_DEVICE")" == "$EXPECTED_ROMS_SIZE" ]] || \
    die 'ROMS partition size mismatch'
  verify_partition_geometry "$BOOT_DEVICE" 32768 229376
  verify_partition_geometry "$ROOT_DEVICE" 262144 20931401
  verify_partition_geometry "$ROMS_DEVICE" 21193545 100945079
  [[ "$(blkid -s TYPE -o value "$BOOT_DEVICE")" == vfat ]] || die 'BOOT is not vfat'
  [[ "$(blkid -s TYPE -o value "$ROOT_DEVICE")" == ext4 ]] || die 'root is not ext4'
  [[ -z "$(findmnt -rn -S "$BOOT_DEVICE")" ]] || die 'BOOT is already mounted'
  [[ -z "$(findmnt -rn -S "$ROMS_DEVICE")" ]] || die 'ROMS is already mounted'
  R46H_BOOT_DEVICE=$BOOT_DEVICE
}

hash_prefix() {
  dd if="$WHOLE_DEVICE" bs=1048576 count=16 status=none | sha256sum | awk '{print $1}'
}

hash_p1() {
  [[ -z "$(findmnt -rn -S "$BOOT_DEVICE")" ]] || die 'cannot hash mounted BOOT partition'
  sha256sum "$BOOT_DEVICE" | awk '{print $1}'
}

check_fat_readonly() {
  [[ -z "$(findmnt -rn -S "$BOOT_DEVICE")" ]] || die 'cannot audit mounted BOOT partition'
  fsck.fat -n -v "$BOOT_DEVICE" >/dev/null || die 'read-only FAT check failed'
}

ensure_work_dir() {
  if [[ -z "$WORK_DIR" ]]; then
    WORK_DIR=$(mktemp -d /run/r46h-v16-boot-promotion.XXXXXX)
    chmod 0700 "$WORK_DIR"
    BOOT_MOUNT=$WORK_DIR/boot
    SOURCE_DIR=$WORK_DIR/source
    mkdir "$BOOT_MOUNT" "$SOURCE_DIR"
    chmod 0700 "$BOOT_MOUNT" "$SOURCE_DIR"
  fi
}

mount_boot() {
  local access=$1
  ensure_work_dir
  (( BOOT_MOUNTED == 0 )) || die 'BOOT is already mounted privately'
  mount -t vfat -o "$access,nosuid,nodev,noexec,umask=0077" "$BOOT_DEVICE" "$BOOT_MOUNT"
  BOOT_MOUNTED=1
  [[ "$(findmnt -rn -T "$BOOT_MOUNT" -o SOURCE)" == "$BOOT_DEVICE" ]] || \
    die 'private BOOT mount source mismatch'
  [[ "$(findmnt -rn -T "$BOOT_MOUNT" -o FSTYPE)" == vfat ]] || \
    die 'private BOOT mount filesystem mismatch'
  [[ ",$(findmnt -rn -T "$BOOT_MOUNT" -o OPTIONS)," == *,"$access",* ]] || \
    die 'private BOOT mount access mismatch'
}

unmount_boot() {
  (( BOOT_MOUNTED == 1 )) || return 0
  umount "$BOOT_MOUNT"
  BOOT_MOUNTED=0
}

inspect_boot() {
  mount_boot ro
  BOOT_STATE=$(r46h_tx_detect_state "$BOOT_MOUNT") || die 'cannot classify BOOT state'
  unmount_boot
}

prepare_sources() {
  ensure_work_dir
  rm -f -- "$SOURCE_DIR/$R46H_V16_DTB_NAME" "$SOURCE_DIR/$R46H_V16_BOOT_NAME"
  install -o root -g root -m 0400 "$SCRIPT_DIR/files/$R46H_V16_DTB_NAME" \
    "$SOURCE_DIR/$R46H_V16_DTB_NAME"
  install -o root -g root -m 0400 "$SCRIPT_DIR/files/$R46H_V16_BOOT_NAME" \
    "$SOURCE_DIR/$R46H_V16_BOOT_NAME"
  r46h_tx_verify_sources "$SOURCE_DIR" || die 'prepared v0.16 BOOT sources failed verification'
}

payload_manifest_hash() {
  local payload=$SCRIPT_DIR
  if [[ -e "$RETAINED_PAYLOAD" || -L "$RETAINED_PAYLOAD" ]]; then
    payload=$RETAINED_PAYLOAD
  fi
  hash_file "$payload/SHA256SUMS"
}

status_bytes() {
  local state=$1 p1=$2 active=$3
  printf '%s\n' \
    'format_version=1' \
    "tool_id=$TOOL_ID" \
    "state=$state" \
    "baseline_p1_sha256=$EXPECTED_BASE_P1_SHA256" \
    "p1_sha256=$p1" \
    "prefix_sha256=$EXPECTED_PREFIX_SHA256" \
    "active_boot_sha256=$active" \
    "target_boot_sha256=$R46H_V16_BOOT_SHA256" \
    "candidate_dtb_sha256=$R46H_V16_DTB_SHA256" \
    "fallback_v0.15_boot_sha256=$R46H_V15_BOOT_SHA256" \
    "payload_sha256s_sha256=$(payload_manifest_hash)" \
    'second_card_slot=unavailable' \
    'saveenv_used=false'
}

status_value() {
  local key=$1 count value
  count=$(grep -c "^${key}=" "$STATUS_FILE" || true)
  [[ "$count" == 1 ]] || die "status key count mismatch: ${key}"
  value=$(sed -n "s/^${key}=//p" "$STATUS_FILE")
  printf '%s\n' "$value"
}

load_status() {
  local expected_active
  STATUS_STATE=absent
  STATUS_P1_SHA256=
  STATUS_ACTIVE_SHA256=
  STATUS_STAGE_PRESENT=0
  if [[ ! -e "$STATE_DIR" && ! -L "$STATE_DIR" ]]; then
    if [[ -e "$STATE_PARENT" || -L "$STATE_PARENT" ]]; then
      require_directory "$STATE_PARENT" 700 'promotion state parent'
    fi
    if [[ -e "$STATE_STAGE" || -L "$STATE_STAGE" ]]; then
      require_directory "$STATE_STAGE" 700 'interrupted v0.16 state stage'
      STATUS_STATE=retention-partial
    fi
    return
  fi
  require_directory "$STATE_PARENT" 700 'promotion state parent'
  require_directory "$STATE_DIR" 700 'v0.16 promotion state directory'
  verify_payload_identity "$RETAINED_PAYLOAD"
  validate_payload "$RETAINED_PAYLOAD"
  require_identity "$STATUS_FILE" 600 'v0.16 promotion status'
  if [[ -e "$STATUS_STAGE" || -L "$STATUS_STAGE" ]]; then
    require_identity "$STATUS_STAGE" 600 'interrupted status stage'
    [[ "$(stat -c '%s' "$STATUS_STAGE")" -le 4096 ]] || \
      die 'interrupted status stage is oversized'
    STATUS_STAGE_PRESENT=1
  fi
  STATUS_STATE=$(status_value state)
  STATUS_P1_SHA256=$(status_value p1_sha256)
  STATUS_ACTIVE_SHA256=$(status_value active_boot_sha256)
  [[ "$STATUS_P1_SHA256" =~ ^[0-9a-f]{64}$ ]] || die 'malformed status p1 SHA-256'
  case "$STATUS_STATE" in
    prepare-intent|prepared|activate-intent|rollback-complete)
      expected_active=$R46H_V15_BOOT_SHA256
      ;;
    activated|complete)
      expected_active=$R46H_V16_BOOT_SHA256
      ;;
    rollback-intent)
      case "$STATUS_ACTIVE_SHA256" in
        "$R46H_V15_BOOT_SHA256"|"$R46H_V16_BOOT_SHA256") expected_active=$STATUS_ACTIVE_SHA256 ;;
        *) die 'rollback status has an unknown active boot hash' ;;
      esac
      ;;
    *) die 'unsupported v0.16 promotion status state' ;;
  esac
  [[ "$STATUS_ACTIVE_SHA256" == "$expected_active" ]] || die 'status active boot mismatch'
  cmp -s "$STATUS_FILE" <(status_bytes "$STATUS_STATE" "$STATUS_P1_SHA256" \
    "$STATUS_ACTIVE_SHA256") || die 'v0.16 promotion status content mismatch'
}

write_status() {
  local state=$1 p1=$2 active=$3
  require_directory "$STATE_DIR" 700 'v0.16 promotion state directory'
  if [[ -e "$STATUS_STAGE" || -L "$STATUS_STAGE" ]]; then
    require_identity "$STATUS_STAGE" 600 'interrupted status stage'
    [[ "$(stat -c '%s' "$STATUS_STAGE")" -le 4096 ]] || \
      die 'interrupted status stage is oversized'
    rm -f -- "$STATUS_STAGE"
    sync
  fi
  (set -o noclobber; status_bytes "$state" "$p1" "$active" > "$STATUS_STAGE") || \
    die 'cannot stage v0.16 promotion status'
  chmod 0600 "$STATUS_STAGE"
  sync
  mv -T -- "$STATUS_STAGE" "$STATUS_FILE"
  sync
  load_status
  [[ "$STATUS_STATE:$STATUS_P1_SHA256:$STATUS_ACTIVE_SHA256" == "$state:$p1:$active" ]] || \
    die 'published v0.16 promotion status mismatch'
}

retain_payload_with_intent() {
  local stage_payload=$STATE_STAGE/payload
  [[ "$SCRIPT_DIR" == "$RUN_PAYLOAD" ]] || die 'initial retention must use the authenticated run payload'
  [[ ! -e "$STATE_DIR" && ! -L "$STATE_DIR" ]] || die 'v0.16 state already exists'
  if [[ -e "$STATE_PARENT" || -L "$STATE_PARENT" ]]; then
    require_directory "$STATE_PARENT" 700 'promotion state parent'
  else
    install -d -o root -g root -m 0700 "$STATE_PARENT"
    sync
  fi
  if [[ -e "$STATE_STAGE" || -L "$STATE_STAGE" ]]; then
    require_directory "$STATE_STAGE" 700 'interrupted v0.16 state stage'
    local mount_target
    while IFS= read -r mount_target; do
      case "$mount_target" in
        "$STATE_STAGE"|"$STATE_STAGE"/*)
          die 'interrupted state stage contains a mountpoint'
          ;;
      esac
    done < <(findmnt -rn -o TARGET)
    rm -rf -- "$STATE_STAGE"
  fi
  install -d -o root -g root -m 0700 "$STATE_STAGE" "$stage_payload"
  cp -a "$SCRIPT_DIR/." "$stage_payload/"
  chown -R root:root "$stage_payload"
  find "$stage_payload" -xdev -type d -exec chmod 0700 {} +
  find "$stage_payload" -xdev -type f -exec chmod 0400 {} +
  chmod 0500 "$stage_payload/install.sh"
  validate_payload "$stage_payload"
  status_bytes prepare-intent "$EXPECTED_BASE_P1_SHA256" "$R46H_V15_BOOT_SHA256" \
    > "$STATE_STAGE/STATUS"
  chown root:root "$STATE_STAGE/STATUS"
  chmod 0600 "$STATE_STAGE/STATUS"
  sync
  [[ ! -e "$STATE_DIR" && ! -L "$STATE_DIR" ]] || \
    die 'v0.16 state destination appeared concurrently'
  mv -T -- "$STATE_STAGE" "$STATE_DIR"
  sync
  load_status
  [[ "$STATUS_STATE" == prepare-intent ]] || die 'retained state did not publish prepare intent'
}

verify_fixed_prefix() {
  [[ "$(hash_prefix)" == "$EXPECTED_PREFIX_SHA256" ]] || die 'raw prefix SHA-256 mismatch'
}

verify_postwrite_media() {
  local expected_state=$1 expected_status=$2
  verify_fixed_prefix
  check_fat_readonly
  P1_SHA256=$(hash_p1)
  inspect_boot
  [[ "$BOOT_STATE" == "$expected_state" ]] || \
    die "unexpected BOOT state: ${BOOT_STATE}"
  [[ "$expected_status" == any || "$STATUS_STATE" == "$expected_status" ]] || \
    die 'unexpected wrapper status state'
}

perform_preflight() {
  local p1 boot_state storage_state
  load_status
  verify_fixed_prefix
  p1=$(hash_p1)
  check_fat_readonly
  inspect_boot
  boot_state=$BOOT_STATE
  case "$boot_state:$STATUS_STATE" in
    base:absent|base:retention-partial)
      [[ "$SCRIPT_DIR" == "$RUN_PAYLOAD" ]] || \
        die 'initial or retention recovery preflight must use the run payload'
      [[ "$p1" == "$EXPECTED_BASE_P1_SHA256" ]] || die 'initial p1 SHA-256 mismatch'
      ;;
    base:prepare-intent|prepare-partial:prepare-intent|prepared:prepare-intent|\
    prepared:activate-intent|activate-partial-v15:activate-intent|\
    activate-partial-v16:activate-intent|activated:activate-intent|\
    activated:rollback-intent|rollback-partial-v16:rollback-intent|\
    rollback-partial-v15:rollback-intent|prepared:rollback-intent)
      [[ "$SCRIPT_DIR" == "$RETAINED_PAYLOAD" ]] || \
        die 'transaction recovery preflight must use the retained payload'
      ;;
    prepared:prepared|prepared:rollback-complete|activated:activated|activated:complete)
      [[ "$SCRIPT_DIR" == "$RETAINED_PAYLOAD" ]] || \
        die 'completed-state preflight must use the retained payload'
      [[ "$p1" == "$STATUS_P1_SHA256" ]] || die 'p1/status SHA-256 mismatch'
      ;;
    *) die "incompatible BOOT/status preflight state: ${boot_state}/${STATUS_STATE}" ;;
  esac
  storage_state=$(r46h_storage_health_current)
  printf 'R46H_V16_BOOT_PROMOTION result=pass mode=preflight state=%s status=%s status_stage_present=%s p1_sha256=%s prefix_sha256=%s mmc_init=%s write_started=false\n' \
    "$boot_state" "$STATUS_STATE" "$STATUS_STAGE_PRESENT" "$p1" \
    "$EXPECTED_PREFIX_SHA256" "$storage_state"
}

perform_prepare() {
  local recovery=$1 boot_state p1
  load_status
  if [[ "$recovery" == 0 ]]; then
    case "$STATUS_STATE" in absent|retention-partial) ;;
      *) die 'normal prepare requires absent or interrupted-retention state' ;;
    esac
    verify_fixed_prefix
    [[ "$(hash_p1)" == "$EXPECTED_BASE_P1_SHA256" ]] || \
      die 'normal prepare requires exact untouched p1 baseline'
    inspect_boot
    [[ "$BOOT_STATE" == base ]] || die 'normal prepare requires exact base BOOT state'
    begin_write
    retain_payload_with_intent
  else
    [[ "$SCRIPT_DIR" == "$RETAINED_PAYLOAD" ]] || die 'prepare recovery must use retained payload'
    [[ "$STATUS_STATE" == prepare-intent ]] || die 'prepare recovery requires prepare-intent status'
    begin_write
  fi
  prepare_sources
  mount_boot rw
  boot_state=$(r46h_tx_detect_state "$BOOT_MOUNT") || die 'cannot classify BOOT before prepare'
  case "$boot_state" in
    base) r46h_tx_prepare "$BOOT_MOUNT" "$SOURCE_DIR" 0 || die 'v0.16 BOOT prepare failed' ;;
    prepare-partial) r46h_tx_prepare "$BOOT_MOUNT" "$SOURCE_DIR" 1 || die 'v0.16 BOOT prepare recovery failed' ;;
    prepared) ;;
    *) die "prepare found incompatible BOOT state: ${boot_state}" ;;
  esac
  unmount_boot
  load_status
  verify_postwrite_media prepared any
  p1=$P1_SHA256
  write_status prepared "$p1" "$R46H_V15_BOOT_SHA256"
  printf 'R46H_V16_BOOT_PROMOTION result=pass mode=%s state=prepared active_v0.15=yes v0.16_candidate=inert p1_sha256=%s saveenv_used=false\n' \
    "$([[ "$recovery" == 1 ]] && printf recover-prepare || printf prepare)" "$p1"
}

perform_activate() {
  local recovery=$1 boot_state operation_status rollback_status p1
  [[ "$SCRIPT_DIR" == "$RETAINED_PAYLOAD" ]] || \
    die 'activation must use the checksum-bound retained payload'
  load_status
  if [[ "$recovery" == 0 ]]; then
    case "$STATUS_STATE" in prepared|rollback-complete) ;;
      *) die 'normal activation requires prepared or rollback-complete status' ;;
    esac
    [[ "$(hash_p1)" == "$STATUS_P1_SHA256" ]] || die 'prepared p1/status mismatch'
    inspect_boot
    [[ "$BOOT_STATE" == prepared ]] || die 'normal activation requires prepared BOOT state'
    begin_write
    write_status activate-intent "$STATUS_P1_SHA256" "$R46H_V15_BOOT_SHA256"
  else
    [[ "$SCRIPT_DIR" == "$RETAINED_PAYLOAD" ]] || die 'activation recovery must use retained payload'
    [[ "$STATUS_STATE" == activate-intent ]] || die 'activation recovery requires activate-intent status'
    begin_write
  fi
  mount_boot rw
  boot_state=$(r46h_tx_detect_state "$BOOT_MOUNT") || die 'cannot classify BOOT before activation'
  set +e
  case "$boot_state" in
    prepared) r46h_tx_activate "$BOOT_MOUNT" 0 ; operation_status=$? ;;
    activate-partial-v15|activate-partial-v16)
      r46h_tx_activate "$BOOT_MOUNT" 1
      operation_status=$?
      ;;
    activated) operation_status=0 ;;
    *) operation_status=1 ;;
  esac
  if (( operation_status != 0 )); then
    r46h_tx_rollback "$BOOT_MOUNT"
    rollback_status=$?
    set -e
    unmount_boot
    if (( rollback_status != 0 )); then
      printf 'HARD WARNING: activation and automatic v0.15 rollback both failed; do not reboot or power off\n' >&2
      die 'v0.16 activation left an unresolved BOOT transaction'
    fi
    verify_postwrite_media prepared any
    p1=$P1_SHA256
    write_status rollback-complete "$p1" "$R46H_V15_BOOT_SHA256"
    die 'v0.16 activation failed and exact v0.15 was restored'
  fi
  set -e
  unmount_boot
  verify_postwrite_media activated any
  p1=$P1_SHA256
  write_status activated "$p1" "$R46H_V16_BOOT_SHA256"
  printf 'R46H_V16_BOOT_PROMOTION result=pass mode=%s state=activated active_v0.16=yes v0.15_v0.10_v0.8_fallbacks=exact p1_sha256=%s saveenv_used=false\n' \
    "$([[ "$recovery" == 1 ]] && printf recover-activate || printf activate)" "$p1"
}

perform_rollback() {
  local boot_state active p1
  [[ "$SCRIPT_DIR" == "$RETAINED_PAYLOAD" ]] || die 'rollback must use retained payload'
  load_status
  case "$STATUS_STATE" in activated|complete|activate-intent|rollback-intent) ;;
    *) die 'rollback requires an activated or recoverable status' ;;
  esac
  inspect_boot
  boot_state=$BOOT_STATE
  case "$boot_state" in
    activated|activate-partial-v16|rollback-partial-v16) active=$R46H_V16_BOOT_SHA256 ;;
    prepared|activate-partial-v15|rollback-partial-v15) active=$R46H_V15_BOOT_SHA256 ;;
    *) die "rollback found incompatible BOOT state: ${boot_state}" ;;
  esac
  p1=$(hash_p1)
  begin_write
  write_status rollback-intent "$p1" "$active"
  mount_boot rw
  r46h_tx_rollback "$BOOT_MOUNT" || \
    die 'exact v0.15 rollback failed; do not reboot or power off'
  unmount_boot
  verify_postwrite_media prepared any
  p1=$P1_SHA256
  write_status rollback-complete "$p1" "$R46H_V15_BOOT_SHA256"
  printf 'R46H_V16_BOOT_PROMOTION result=pass mode=rollback state=prepared active_v0.15=yes v0.16_candidate=inert p1_sha256=%s saveenv_used=false\n' "$p1"
}

verify_candidate_boot() {
  local kernel_log storage_state
  [[ "$(tr -d '\0' < /proc/device-tree/mmc@ff370000/status)" == okay ]] || \
    die 'live system MMC status mismatch'
  [[ "$(tr -d '\0' < /proc/device-tree/mmc@ff380000/status)" == disabled ]] || \
    die 'live secondary MMC status mismatch'
  [[ "$(tr -d '\0' < /proc/device-tree/aliases/mmc0)" == /mmc@ff370000 ]] || \
    die 'live mmc0 alias mismatch'
  [[ "$(tr -d '\0' < /proc/device-tree/aliases/mmc1)" == /mmc@ff380000 ]] || \
    die 'live mmc1 alias mismatch'
  kernel_log=$(dmesg --color=never)
  [[ "$(printf '%s\n' "$kernel_log" | grep -Fc 'dwmmc_rockchip ff370000.mmc: DW MMC controller')" == 1 ]] || \
    die 'system MMC controller count mismatch'
  [[ "$(printf '%s\n' "$kernel_log" | grep -Fc 'mmc_host mmc0: Bus speed (slot 0) = 400000Hz')" == 1 ]] || \
    die '400 kHz initialization marker mismatch'
  [[ "$(printf '%s\n' "$kernel_log" | grep -Fc 'mmc_host mmc0: Bus speed (slot 0) = 150000000Hz')" == 1 ]] || \
    die '150 MHz initialization marker mismatch'
  [[ "$(printf '%s\n' "$kernel_log" | grep -Fc ' mmcblk0: p1 p2 p3')" == 1 ]] || \
    die 'partition enumeration marker mismatch'
  [[ "$(printf '%s\n' "$kernel_log" | grep -Fc 'VFS: Mounted root (ext4 filesystem) on device 179:2.')" == 1 ]] || \
    die 'root mount marker mismatch'
  ! printf '%s\n' "$kernel_log" | grep -Eq \
    'ff380000\.mmc|mmc_host mmc1|mmc1:|mmc0: error|Timeout waiting for hardware cmd interrupt|[Cc]ard stuck being busy|EXT4-fs (error|warning)|Buffer I/O error|I/O error, dev mmcblk0' || \
    die 'persistent v0.16 boot contains a forbidden storage marker'
  storage_state=$(printf '%s\n' "$kernel_log" | r46h_storage_health_from_log) || \
    die 'persistent v0.16 storage classifier failed'
  [[ "$storage_state" == clean ]] || die 'persistent v0.16 cold gate requires clean MMC initialization'
}

perform_postflight() {
  local p1 boot_state
  [[ "$SCRIPT_DIR" == "$RETAINED_PAYLOAD" ]] || die 'postflight must use retained payload'
  load_status
  [[ "$STATUS_STATE" == activated ]] || die 'postflight requires activated status'
  verify_candidate_boot
  [[ "$(hash_p1)" == "$STATUS_P1_SHA256" ]] || die 'activated p1/status mismatch'
  verify_fixed_prefix
  check_fat_readonly
  inspect_boot
  boot_state=$BOOT_STATE
  [[ "$boot_state" == activated ]] || die 'postflight BOOT state is not activated'
  verify_module_fallbacks
  "$STORAGE_AUDIT"
  p1=$STATUS_P1_SHA256
  verify_runtime_health
  begin_write
  write_status complete "$p1" "$R46H_V16_BOOT_SHA256"
  printf 'R46H_V16_BOOT_PROMOTION result=pass mode=postflight state=complete active_v0.16=yes mmc_init=clean second_card_slot=unavailable p1_sha256=%s saveenv_used=false\n' "$p1"
}

discover_devices
verify_product
verify_runtime_health
verify_module_fallbacks
case "$mode" in
  preflight) perform_preflight ;;
  prepare) perform_prepare 0 ;;
  recover-prepare) perform_prepare 1 ;;
  activate) perform_activate 0 ;;
  recover-activate) perform_activate 1 ;;
  rollback) perform_rollback ;;
  postflight) perform_postflight ;;
esac
