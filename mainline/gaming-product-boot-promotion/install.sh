#!/bin/bash
set -Eeuo pipefail
umask 077

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG

readonly PAYLOAD_ID=r46h-v15-boot-promotion-v0.1
readonly TOOL_ID=r46h-v15-boot-promotion-v0.1
readonly RUN_PAYLOAD=/run/r46h-v15-boot-promotion-v0.1
readonly STATE_PARENT=/var/lib/r46h-boot-promotion
readonly STATE_DIR=/var/lib/r46h-boot-promotion/v0.15-gaming-product
readonly RETAINED_PAYLOAD=/var/lib/r46h-boot-promotion/v0.15-gaming-product/payload
readonly STATUS_FILE=/var/lib/r46h-boot-promotion/v0.15-gaming-product/STATUS
readonly LOCK_FILE=/run/r46h-v15-boot-promotion.lock
readonly PRODUCT_KERNEL_DIR=/var/lib/r46h-gaming-product-kernel/v0.15-gaming-product
readonly PRODUCT_IMAGE=/var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/IMAGE
readonly PRODUCT_DTB=/var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/R46H.DTB
readonly PRODUCT_COMMANDS=/var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/UBOOT-CMDS.txt
readonly PRODUCT_RECEIPT=/var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/RECEIPT
readonly MODULES_PARENT=/usr/lib/modules
readonly EXPECTED_RUNNING_RELEASE=6.12.99-r46h-mainline-v0.15-gaming-product
readonly FALLBACK_RUNNING_RELEASE=6.12.99-r46h-mainline-v0.10-adc-full-range
readonly SECONDARY_FALLBACK_RUNNING_RELEASE=6.12.99-r46h-mainline-v0.8-bootloader-handoff
readonly EXPECTED_ROOT_PARTUUID=c9f931c9-02
readonly EXPECTED_BOOT_PARTUUID=c9f931c9-01
readonly EXPECTED_ROMS_PARTUUID=c9f931c9-03
readonly EXPECTED_WHOLE_SIZE=62534975488
readonly EXPECTED_BOOT_SIZE=117440512
readonly EXPECTED_ROOT_SIZE=10716877312
readonly EXPECTED_ROMS_SIZE=51683880448
readonly EXPECTED_SECTOR_SIZE=512
readonly EXPECTED_PREFIX_SIZE=16777216
readonly EXPECTED_PREFIX_SHA256=3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3
readonly EXPECTED_BASE_P1_SHA256=f50597d459a51bab509aae959267f77ade068d566751acb6cff888b012d3b4ed
readonly EXPECTED_FIRSTBOOT='release=debian13-p2-gaming-v0.3'
readonly EXPECTED_PRODUCT_IMAGE_SIZE=41570816
readonly EXPECTED_PRODUCT_IMAGE_SHA256=956ab3d5a2e53afbfe964ae75850e8591b44c093b9779867b31149b7b591f68f
readonly EXPECTED_PRODUCT_DTB_SIZE=49518
readonly EXPECTED_PRODUCT_DTB_SHA256=4d6d4ebad3b98600b6e9a38df4ca82230335558497a9e15dd0e81ca60e304b61
readonly EXPECTED_PRODUCT_COMMANDS_SIZE=981
readonly EXPECTED_PRODUCT_COMMANDS_SHA256=51bf7caf6e9a08f01e1007a0010841e539300d8776851630e9d7d2829589d717
readonly EXPECTED_PRODUCT_RECEIPT_SHA256=a90b359f2275bdc732b5814bf9d1dc328844532a1e3c2a4d23577068978fffbd
readonly PREPARE_CONFIRM=prepare-v0.15-keep-v0.10-active
readonly PREPARE_RECOVERY_CONFIRM=recover-v0.15-versioned-files
readonly ACTIVATE_CONFIRM=activate-v0.15-keep-v0.10-v0.8-fallback
readonly ACTIVATE_RECOVERY_CONFIRM=recover-v0.15-active-switch
readonly ROLLBACK_CONFIRM=rollback-active-to-v0.10

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

hash_file() {
  sha256sum "$1" | awk '{print $1}'
}

size_file() {
  stat -c '%s' "$1"
}

check_file() {
  local path=$1 expected_size=$2 expected_hash=$3 label=$4
  [[ -f "$path" && ! -L "$path" ]] || die "unsafe or missing ${label}"
  [[ "$(stat -c '%h' "$path")" == 1 ]] || die "unexpected link count for ${label}"
  [[ "$(size_file "$path")" == "$expected_size" ]] || die "size mismatch for ${label}"
  [[ "$(hash_file "$path")" == "$expected_hash" ]] || die "SHA-256 mismatch for ${label}"
}

validate_payload() {
  local payload=$1 members expected
  [[ -d "$payload" && ! -L "$payload" ]] || die 'unsafe payload directory'
  members=$(cd "$payload" && find . -mindepth 1 -maxdepth 2 -print | \
    sed 's#^\./##' | LC_ALL=C sort)
  expected=$'PAYLOAD-INFO.json\nPAYLOAD.COMPLETE\nSHA256SUMS\nfallback-modules.sh\nfiles\nfiles/Image.mainline-v0.15-gaming-product.gz\nfiles/boot.ini.v0.15-gaming-product\nfiles/r46h-mainline-test-v0.10-adc-full-range.tar.gz\nfiles/rk3326-r46h-mainline-v0.15-gaming-product.dtb\ninstall.sh\nstorage-health.sh\ntransaction.sh'
  [[ "$members" == "$expected" ]] || die 'unexpected payload member set'
  [[ -z "$(find "$payload" -xdev -type l -print -quit)" ]] || die 'payload contains a symbolic link'
  [[ -z "$(find "$payload" -xdev ! -type d ! -type f -print -quit)" ]] || die 'payload contains a special file'
  [[ -z "$(find "$payload" -xdev -type f ! -links 1 -print -quit)" ]] || die 'payload contains a hard-linked file'
  (cd "$payload" && sha256sum -c SHA256SUMS) || die 'payload checksum verification failed'
  [[ "$(<"$payload/PAYLOAD.COMPLETE")" == \
    "sha256sums_sha256=$(hash_file "$payload/SHA256SUMS")" ]] || \
    die 'payload completion marker mismatch'
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
  *) die "run from $RUN_PAYLOAD or the retained rollback payload" ;;
esac
[[ "$(stat -c '%u:%g:%a' "$SCRIPT_DIR")" == 0:0:700 ]] || \
  die 'payload directory must be root-owned mode 0700'
[[ -f "$SCRIPT_DIR/transaction.sh" && ! -L "$SCRIPT_DIR/transaction.sh" ]] || \
  die 'unsafe transaction helper'
[[ -f "$SCRIPT_DIR/fallback-modules.sh" && ! -L "$SCRIPT_DIR/fallback-modules.sh" ]] || \
  die 'unsafe fallback module helper'
[[ -f "$SCRIPT_DIR/storage-health.sh" && ! -L "$SCRIPT_DIR/storage-health.sh" ]] || \
  die 'unsafe storage health helper'
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
flock -n 9 || die 'another BOOT promotion process holds the lock'

WORK_DIR=
BOOT_MOUNT=
SOURCE_DIR=
BOOT_MOUNTED=0
BOOT_DEVICE=
R46H_BOOT_DEVICE=
ROOT_DEVICE=
ROMS_DEVICE=
WHOLE_DEVICE=
BOOT_STATE=
ACTIVE_BOOT_SHA256=
P1_SHA256=
PREFIX_SHA256=
STATUS_STATE=
STATUS_P1_SHA256=
STATUS_ACTIVE_SHA256=
MODULE_STATE=

cleanup() {
  local status=$?
  trap - EXIT INT TERM HUP
  set +e
  if (( BOOT_MOUNTED == 1 )); then
    umount "$BOOT_MOUNT"
    BOOT_MOUNTED=0
  fi
  if [[ -n "$WORK_DIR" ]]; then
    case "$WORK_DIR" in
      /run/r46h-v15-boot-promotion.*)
        rm -rf -- "$WORK_DIR"
        ;;
      *)
        printf 'WARNING: refusing unexpected work cleanup path: %s\n' "$WORK_DIR" >&2
        ;;
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

require_identity() {
  local path=$1 mode_bits=$2 label=$3
  [[ -f "$path" && ! -L "$path" ]] || die "unsafe or missing ${label}"
  [[ "$(stat -c '%u:%g:%a:%h' "$path")" == "0:0:${mode_bits}:1" ]] || \
    die "identity mismatch for ${label}"
}

verify_hotfixed_product() {
  require_identity /var/lib/r46h/firstboot-complete 600 'firstboot completion marker'
  [[ "$(< /var/lib/r46h/firstboot-complete)" == "$EXPECTED_FIRSTBOOT" ]] || \
    die 'firstboot completion marker mismatch'
  [[ -d "$PRODUCT_KERNEL_DIR" && ! -L "$PRODUCT_KERNEL_DIR" ]] || \
    die 'product kernel staging is unsafe'
  [[ "$(stat -c '%u:%g:%a' "$PRODUCT_KERNEL_DIR")" == 0:0:700 ]] || \
    die 'product kernel staging identity mismatch'
  require_identity "$PRODUCT_IMAGE" 400 'product Image'
  require_identity "$PRODUCT_DTB" 400 'product DTB'
  require_identity "$PRODUCT_COMMANDS" 400 'product one-shot commands'
  require_identity "$PRODUCT_RECEIPT" 400 'product kernel receipt'
  check_file "$PRODUCT_IMAGE" "$EXPECTED_PRODUCT_IMAGE_SIZE" \
    "$EXPECTED_PRODUCT_IMAGE_SHA256" 'product Image'
  check_file "$PRODUCT_DTB" "$EXPECTED_PRODUCT_DTB_SIZE" \
    "$EXPECTED_PRODUCT_DTB_SHA256" 'product DTB'
  check_file "$PRODUCT_COMMANDS" "$EXPECTED_PRODUCT_COMMANDS_SIZE" \
    "$EXPECTED_PRODUCT_COMMANDS_SHA256" 'product one-shot commands'
  [[ "$(hash_file "$PRODUCT_RECEIPT")" == "$EXPECTED_PRODUCT_RECEIPT_SHA256" ]] || \
    die 'product kernel receipt mismatch'

  require_identity /usr/local/sbin/r46h-storage-audit 755 'hotfixed storage audit'
  require_identity /usr/local/libexec/r46h-smoke-libretro.so 644 'hotfixed smoke core'
  require_identity /usr/local/sbin/r46h-game-ui 755 'hotfixed game runner'
  [[ "$(hash_file /usr/local/sbin/r46h-storage-audit)" == \
    08ed33dace8a94a6b129d72896c8e6a657b32d15c74d9ecf48df99a9f49ae95c ]] || \
    die 'hotfixed storage audit mismatch'
  [[ "$(hash_file /usr/local/libexec/r46h-smoke-libretro.so)" == \
    a6618fec16ab91fcfbc76497416c4542d1973862affb82f633ee70d600739085 ]] || \
    die 'hotfixed smoke core mismatch'
  [[ "$(hash_file /usr/local/sbin/r46h-game-ui)" == \
    867664284d932cd23757b40d7108ed878d3ab8d16f5655956543444619e75ff3 ]] || \
    die 'hotfixed game runner mismatch'
  local receipt
  for receipt in \
    /var/lib/r46h-product-hotfixes/storage-audit-tab-v1/RECEIPT \
    /var/lib/r46h-product-hotfixes/smoke-core-analog-v1/RECEIPT \
    /var/lib/r46h-product-hotfixes/game-ui-volume-v1/RECEIPT; do
    require_identity "$receipt" 600 "hotfix receipt ${receipt}"
  done
  [[ "$(hash_file /var/lib/r46h-product-hotfixes/storage-audit-tab-v1/RECEIPT)" == \
    d7f3b7cf5dda67e7799eabc13d385b880eaf3738a1bfa5fd5bcdd353e533450e ]] || \
    die 'storage-audit hotfix receipt mismatch'
  [[ "$(hash_file /var/lib/r46h-product-hotfixes/smoke-core-analog-v1/RECEIPT)" == \
    a28477802e06bcbe5628ea2721c75bf3acd2601aa9cba7800f618348a4e47928 ]] || \
    die 'smoke-core hotfix receipt mismatch'
  [[ "$(hash_file /var/lib/r46h-product-hotfixes/game-ui-volume-v1/RECEIPT)" == \
    7d1d6c86296dafc9a7f199476be4164eb505ce0d38291950ca4e46c5e611a17b ]] || \
    die 'game-runner hotfix receipt mismatch'
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
  [[ "$ROOT_DEVICE" == "$root_alias" ]] || die 'root source does not match the fixed PARTUUID'
  BOOT_DEVICE=$boot_alias
  R46H_BOOT_DEVICE=$BOOT_DEVICE
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
}

ensure_public_partitions_unmounted() {
  [[ -z "$(findmnt -rn -S "$BOOT_DEVICE")" ]] || die 'BOOT is already mounted'
  [[ -z "$(findmnt -rn -S "$ROMS_DEVICE")" ]] || die 'ROMS is already mounted'
}

verify_runtime_health() {
  local running ext4_errors storage_state
  running=$(uname -r)
  if [[ "$mode" == rollback || "$mode" == preflight ]]; then
    case "$running" in
      "$EXPECTED_RUNNING_RELEASE"|"$FALLBACK_RUNNING_RELEASE"|"$SECONDARY_FALLBACK_RUNNING_RELEASE") ;;
      *) die 'read-only preflight or rollback requires exact v0.15, v0.10 or v0.8' ;;
    esac
  else
    [[ "$running" == "$EXPECTED_RUNNING_RELEASE" ]] || \
      die 'promotion requires the exact accepted v0.15 one-shot or ordinary boot'
  fi
  [[ "$(findmnt -rn -o PARTUUID /)" == "$EXPECTED_ROOT_PARTUUID" ]] || \
    die 'unexpected root PARTUUID'
  [[ "$(findmnt -rn -o FSTYPE /)" == ext4 ]] || die 'root is not ext4'
  [[ ",$(findmnt -rn -o OPTIONS /)," == *,rw,* ]] || die 'root is not writable'
  ext4_errors=/sys/fs/ext4/${ROOT_DEVICE##*/}/errors_count
  [[ -f "$ext4_errors" && "$(<"$ext4_errors")" == 0 ]] || \
    die 'root ext4 error counter is nonzero or unavailable'
  [[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd has failed units'
  [[ "$(systemctl is-active r46h-gaming-frontend.service || true)" == inactive ]] || \
    die 'stop the gaming frontend before BOOT work'
  [[ -z "$(pgrep -x retroarch || true)" ]] || die 'RetroArch is still running'
  [[ -z "$(find /run -maxdepth 1 -type d -name 'r46h-game-ui.*' -print -quit)" ]] || \
    die 'a game session directory remains'
  if ! storage_state=$(r46h_storage_health_current); then
    die 'current boot contains an unaccepted storage fault marker'
  fi
  if [[ "$storage_state" == recovered-known-open ]]; then
    printf 'WARNING: current boot recovered the known one-shot MMC initialization error; the intermittent MMC item remains open.\n' >&2
  fi
  verify_hotfixed_product
  r46h_mod_verify_existing_fallbacks "$MODULES_PARENT" || \
    die 'existing v0.8 fallback or v0.15 target module tree is not exact'
}

create_work() {
  WORK_DIR=$(mktemp -d /run/r46h-v15-boot-promotion.XXXXXX)
  chmod 0700 "$WORK_DIR"
  BOOT_MOUNT=$WORK_DIR/boot
  SOURCE_DIR=$WORK_DIR/source
  mkdir "$BOOT_MOUNT" "$SOURCE_DIR"
}

mount_boot() {
  local policy=$1 options
  (( BOOT_MOUNTED == 0 )) || die 'BOOT is already privately mounted'
  options="$policy,nosuid,nodev,noexec,umask=0077"
  mount -t vfat -o "$options" "$BOOT_DEVICE" "$BOOT_MOUNT"
  BOOT_MOUNTED=1
  [[ "$(findmnt -rn -T "$BOOT_MOUNT" -o SOURCE)" == "$BOOT_DEVICE" ]] || \
    die 'private BOOT mount source mismatch'
  [[ "$(findmnt -rn -T "$BOOT_MOUNT" -o FSTYPE)" == vfat ]] || \
    die 'private BOOT mount filesystem mismatch'
  [[ ",$(findmnt -rn -T "$BOOT_MOUNT" -o OPTIONS)," == *,$policy,* ]] || \
    die 'private BOOT mount policy mismatch'
}

unmount_boot() {
  (( BOOT_MOUNTED == 1 )) || die 'BOOT is not privately mounted'
  sync
  umount "$BOOT_MOUNT"
  BOOT_MOUNTED=0
  blockdev --flushbufs "$BOOT_DEVICE"
  sync
  ensure_public_partitions_unmounted
}

hash_unmounted_media() {
  ensure_public_partitions_unmounted
  (( EXPECTED_PREFIX_SIZE % 1048576 == 0 )) || die 'prefix size is not MiB-aligned'
  PREFIX_SHA256=$(dd if="$WHOLE_DEVICE" bs=1048576 \
    count=$((EXPECTED_PREFIX_SIZE / 1048576)) iflag=fullblock status=none | \
    sha256sum | awk '{print $1}')
  [[ "$PREFIX_SHA256" == "$EXPECTED_PREFIX_SHA256" ]] || die 'g92 prefix and MBR SHA-256 mismatch'
  P1_SHA256=$(sha256sum "$BOOT_DEVICE" | awk '{print $1}')
}

inspect_boot() {
  mount_boot ro
  BOOT_STATE=$(r46h_tx_detect_state "$BOOT_MOUNT") || die 'BOOT state verification failed'
  ACTIVE_BOOT_SHA256=$(hash_file "$BOOT_MOUNT/$R46H_ACTIVE_BOOT_NAME")
  unmount_boot
}

prepare_sources() {
  check_file "$PRODUCT_IMAGE" "$EXPECTED_PRODUCT_IMAGE_SIZE" \
    "$EXPECTED_PRODUCT_IMAGE_SHA256" 'product Image before compression'
  install -o root -g root -m 0400 "$SCRIPT_DIR/files/$R46H_V15_IMAGE_NAME" \
    "$SOURCE_DIR/$R46H_V15_IMAGE_NAME"
  install -o root -g root -m 0400 "$SCRIPT_DIR/files/$R46H_V15_DTB_NAME" \
    "$SOURCE_DIR/$R46H_V15_DTB_NAME"
  install -o root -g root -m 0400 "$SCRIPT_DIR/files/$R46H_V15_BOOT_NAME" \
    "$SOURCE_DIR/$R46H_V15_BOOT_NAME"
  r46h_tx_verify_sources "$SOURCE_DIR" || die 'prepared v0.15 BOOT sources failed verification'
}

stage_retained_payload() {
  local stage=$STATE_DIR/.payload.stage
  if [[ -e "$RETAINED_PAYLOAD" || -L "$RETAINED_PAYLOAD" ]]; then
    validate_payload "$RETAINED_PAYLOAD"
    [[ "$(stat -c '%u:%g:%a' "$RETAINED_PAYLOAD")" == 0:0:700 ]] || \
      die 'retained payload identity mismatch'
    [[ "$(hash_file "$RETAINED_PAYLOAD/SHA256SUMS")" == \
      "$(hash_file "$SCRIPT_DIR/SHA256SUMS")" ]] || \
      die 'retained payload differs from the active payload'
    return
  fi
  if [[ -e "$STATE_PARENT" || -L "$STATE_PARENT" ]]; then
    [[ -d "$STATE_PARENT" && ! -L "$STATE_PARENT" && \
      "$(stat -c '%u:%g:%a' "$STATE_PARENT")" == 0:0:700 ]] || \
      die 'promotion state parent is unsafe'
  else
    install -d -o root -g root -m 0700 "$STATE_PARENT"
  fi
  if [[ -e "$STATE_DIR" || -L "$STATE_DIR" ]]; then
    [[ -d "$STATE_DIR" && ! -L "$STATE_DIR" && \
      "$(stat -c '%u:%g:%a' "$STATE_DIR")" == 0:0:700 ]] || \
      die 'promotion state directory is unsafe'
  else
    install -d -o root -g root -m 0700 "$STATE_DIR"
  fi
  if [[ -e "$stage" || -L "$stage" ]]; then
    [[ -d "$stage" && ! -L "$stage" && \
      "$(stat -c '%u:%g:%a' "$stage")" == 0:0:700 ]] || \
      die 'retained payload stage is unsafe'
    local entry relative
    while IFS= read -r entry; do
      relative=${entry#"$stage"/}
      case "$relative" in
        files)
          [[ -d "$entry" && ! -L "$entry" && \
            "$(stat -c '%u:%g:%a' "$entry")" == 0:0:700 ]] || \
            die 'retained payload files stage is unsafe'
          ;;
        files/Image.mainline-v0.15-gaming-product.gz|\
        files/boot.ini.v0.15-gaming-product|\
        files/r46h-mainline-test-v0.10-adc-full-range.tar.gz|\
        files/rk3326-r46h-mainline-v0.15-gaming-product.dtb|\
        install.sh|transaction.sh|fallback-modules.sh|storage-health.sh|PAYLOAD-INFO.json|PAYLOAD.COMPLETE|SHA256SUMS)
          [[ -f "$entry" && ! -L "$entry" && "$(stat -c '%u:%g:%h' "$entry")" == 0:0:1 ]] || \
            die 'retained payload file stage is unsafe'
          ;;
        *) die "retained payload stage has an unexpected entry: ${relative}" ;;
      esac
      [[ ! -L "$entry" ]] || die 'retained payload stage contains a symbolic link'
    done < <(find "$stage" -mindepth 1 -maxdepth 2 -print | LC_ALL=C sort)
    rm -f "$stage/install.sh" "$stage/transaction.sh" "$stage/fallback-modules.sh" \
      "$stage/storage-health.sh" \
      "$stage/PAYLOAD-INFO.json" \
      "$stage/PAYLOAD.COMPLETE" "$stage/SHA256SUMS" \
      "$stage/files/$R46H_V15_IMAGE_NAME" "$stage/files/$R46H_V15_DTB_NAME" \
      "$stage/files/$R46H_V15_BOOT_NAME" "$stage/files/$R46H_V10_BUNDLE_NAME"
    rmdir "$stage/files" 2>/dev/null || true
    rmdir "$stage" || die 'cannot clear interrupted retained payload stage'
    sync
  fi
  install -d -o root -g root -m 0700 "$stage" "$stage/files"
  install -o root -g root -m 0500 "$SCRIPT_DIR/install.sh" "$stage/install.sh"
  install -o root -g root -m 0400 "$SCRIPT_DIR/transaction.sh" "$stage/transaction.sh"
  install -o root -g root -m 0400 "$SCRIPT_DIR/fallback-modules.sh" \
    "$stage/fallback-modules.sh"
  install -o root -g root -m 0400 "$SCRIPT_DIR/storage-health.sh" \
    "$stage/storage-health.sh"
  install -o root -g root -m 0400 "$SCRIPT_DIR/PAYLOAD-INFO.json" "$stage/PAYLOAD-INFO.json"
  install -o root -g root -m 0400 "$SCRIPT_DIR/PAYLOAD.COMPLETE" "$stage/PAYLOAD.COMPLETE"
  install -o root -g root -m 0400 "$SCRIPT_DIR/SHA256SUMS" "$stage/SHA256SUMS"
  install -o root -g root -m 0400 "$SCRIPT_DIR/files/$R46H_V15_IMAGE_NAME" \
    "$stage/files/$R46H_V15_IMAGE_NAME"
  install -o root -g root -m 0400 "$SCRIPT_DIR/files/$R46H_V15_DTB_NAME" \
    "$stage/files/$R46H_V15_DTB_NAME"
  install -o root -g root -m 0400 "$SCRIPT_DIR/files/$R46H_V15_BOOT_NAME" \
    "$stage/files/$R46H_V15_BOOT_NAME"
  install -o root -g root -m 0400 "$SCRIPT_DIR/files/$R46H_V10_BUNDLE_NAME" \
    "$stage/files/$R46H_V10_BUNDLE_NAME"
  validate_payload "$stage"
  sync
  [[ ! -e "$RETAINED_PAYLOAD" && ! -L "$RETAINED_PAYLOAD" ]] || \
    die 'retained payload destination appeared concurrently'
  mv -T -- "$stage" "$RETAINED_PAYLOAD"
  sync
  validate_payload "$RETAINED_PAYLOAD"
}

status_value() {
  local key=$1 count value
  count=$(grep -c "^${key}=" "$STATUS_FILE" 2>/dev/null || true)
  [[ "$count" == 1 ]] || die "status key ${key} must appear exactly once"
  value=$(sed -n "s/^${key}=//p" "$STATUS_FILE")
  [[ "$value" != *$'\n'* ]] || die "status key ${key} is multiline"
  printf '%s' "$value"
}

read_status() {
  if [[ ! -e "$STATUS_FILE" && ! -L "$STATUS_FILE" ]]; then
    STATUS_STATE=absent
    STATUS_P1_SHA256=
    STATUS_ACTIVE_SHA256=
    return
  fi
  require_identity "$STATUS_FILE" 600 'promotion status'
  [[ "$(awk 'END {print NR}' "$STATUS_FILE")" == 13 ]] || die 'promotion status field count mismatch'
  [[ "$(status_value format_version)" == 1 ]] || die 'promotion status format mismatch'
  [[ "$(status_value tool_id)" == "$TOOL_ID" ]] || die 'promotion status tool mismatch'
  STATUS_STATE=$(status_value state)
  case "$STATUS_STATE" in
    prepare-intent|prepared|activate-intent|activated|rollback-intent|rollback-complete|complete) ;;
    *) die 'promotion status state is unknown' ;;
  esac
  [[ "$(status_value baseline_p1_sha256)" == "$EXPECTED_BASE_P1_SHA256" ]] || \
    die 'promotion status baseline mismatch'
  STATUS_P1_SHA256=$(status_value p1_sha256)
  [[ "$STATUS_P1_SHA256" =~ ^[0-9a-f]{64}$ ]] || die 'promotion status p1 digest is malformed'
  [[ "$(status_value prefix_sha256)" == "$EXPECTED_PREFIX_SHA256" ]] || \
    die 'promotion status prefix mismatch'
  STATUS_ACTIVE_SHA256=$(status_value active_boot_sha256)
  case "$STATUS_STATE:$STATUS_ACTIVE_SHA256" in
    "prepare-intent:$R46H_V10_BOOT_SHA256"|"prepared:$R46H_V10_BOOT_SHA256"|\
    "activate-intent:$R46H_V10_BOOT_SHA256"|"activated:$R46H_V15_BOOT_SHA256"|\
    "rollback-intent:$R46H_V10_BOOT_SHA256"|"rollback-intent:$R46H_V15_BOOT_SHA256"|\
    "rollback-complete:$R46H_V10_BOOT_SHA256"|"complete:$R46H_V15_BOOT_SHA256") ;;
    *) die 'promotion status active boot digest is inconsistent with its state' ;;
  esac
  [[ "$(status_value target_boot_sha256)" == "$R46H_V15_BOOT_SHA256" ]] || \
    die 'promotion status target boot mismatch'
  [[ "$(status_value fallback_module_tree_sha256)" == "$R46H_V10_MODULE_TREE_SHA256" ]] || \
    die 'promotion status fallback module tree mismatch'
  [[ "$(status_value secondary_fallback_module_tree_sha256)" == "$R46H_V08_MODULE_TREE_SHA256" ]] || \
    die 'promotion status secondary fallback module tree mismatch'
  [[ "$(status_value target_module_tree_sha256)" == "$R46H_V15_MODULE_TREE_SHA256" ]] || \
    die 'promotion status target module tree mismatch'
  [[ "$(status_value payload_sha256s_sha256)" == "$(hash_file "$SCRIPT_DIR/SHA256SUMS")" ]] || \
    die 'promotion status payload mismatch'
  [[ "$(status_value saveenv_used)" == false ]] || die 'promotion status saveenv boundary mismatch'
}

write_status() {
  local state=$1 p1=$2 active=$3 stage=$STATE_DIR/.STATUS.stage
  stage_retained_payload
  if [[ -e "$stage" || -L "$stage" ]]; then
    [[ -f "$stage" && ! -L "$stage" && "$(stat -c '%u:%g:%a:%h' "$stage")" == 0:0:600:1 && \
      "$(stat -c '%s' "$stage")" -le 4096 ]] || die 'promotion status stage is unsafe'
    rm -f "$stage"
    sync
  fi
  printf '%s\n' \
    'format_version=1' \
    "tool_id=$TOOL_ID" \
    "state=$state" \
    "baseline_p1_sha256=$EXPECTED_BASE_P1_SHA256" \
    "p1_sha256=$p1" \
    "prefix_sha256=$EXPECTED_PREFIX_SHA256" \
    "active_boot_sha256=$active" \
    "target_boot_sha256=$R46H_V15_BOOT_SHA256" \
    "fallback_module_tree_sha256=$R46H_V10_MODULE_TREE_SHA256" \
    "secondary_fallback_module_tree_sha256=$R46H_V08_MODULE_TREE_SHA256" \
    "target_module_tree_sha256=$R46H_V15_MODULE_TREE_SHA256" \
    "payload_sha256s_sha256=$(hash_file "$SCRIPT_DIR/SHA256SUMS")" \
    'saveenv_used=false' > "$stage"
  chmod 0600 "$stage"
  sync
  mv -f "$stage" "$STATUS_FILE"
  sync
  read_status
  [[ "$STATUS_STATE" == "$state" && "$STATUS_P1_SHA256" == "$p1" ]] || \
    die 'published promotion status verification failed'
}

verify_completed_status_matches_media() {
  read_status
  case "$STATUS_STATE" in prepared|activated|rollback-complete|complete) ;;
    *) die 'promotion status is not a completed media state' ;;
  esac
  [[ "$STATUS_P1_SHA256" == "$P1_SHA256" ]] || die 'p1 digest differs from promotion status'
  MODULE_STATE=$(r46h_mod_detect_state "$MODULES_PARENT" "$STATE_DIR") || \
    die 'cannot verify v0.10 fallback module state'
  [[ "$MODULE_STATE" == complete ]] || die 'completed promotion state lacks exact v0.10 fallback modules'
}

perform_prepare() {
  local recovery=$1 transaction_recovery=0 boot_already_prepared=0
  read_status
  if [[ "$recovery" == 0 ]]; then
    [[ "$BOOT_STATE" == base && "$P1_SHA256" == "$EXPECTED_BASE_P1_SHA256" ]] || \
      die 'normal prepare requires the exact untouched p1 baseline'
    [[ "$STATUS_STATE" == absent ]] || die 'normal prepare requires absent promotion state'
    [[ "$MODULE_STATE" == absent ]] || \
      die 'normal prepare requires the product p2 baseline without a v0.10 module transaction'
  else
    [[ "$STATUS_STATE" == prepare-intent ]] || die 'prepare recovery requires prepare-intent status'
    case "$BOOT_STATE" in
      base) transaction_recovery=0 ;;
      prepare-partial) transaction_recovery=1 ;;
      prepared) boot_already_prepared=1 ;;
      *) die 'prepare recovery found an incompatible BOOT state' ;;
    esac
  fi
  stage_retained_payload
  write_status prepare-intent "$P1_SHA256" "$R46H_V10_BOOT_SHA256"
  begin_write
  r46h_mod_ensure "$MODULES_PARENT" "$STATE_DIR" \
    "$SCRIPT_DIR/files/$R46H_V10_BUNDLE_NAME" || \
    die 'v0.10 fallback module transaction failed; use only the documented prepare recovery mode'
  MODULE_STATE=$(r46h_mod_detect_state "$MODULES_PARENT" "$STATE_DIR") || \
    die 'cannot verify installed v0.10 fallback modules'
  [[ "$MODULE_STATE" == complete ]] || die 'v0.10 fallback module transaction is incomplete'
  if (( boot_already_prepared == 1 )); then
    write_status prepared "$P1_SHA256" "$R46H_V10_BOOT_SHA256"
    printf 'R46H_V15_BOOT_PROMOTION result=pass mode=recover-prepare state=prepared write_started=true v0.10_modules=exact\n'
    return
  fi
  prepare_sources
  mount_boot rw
  r46h_tx_prepare "$BOOT_MOUNT" "$SOURCE_DIR" "$transaction_recovery" || \
    die 'versioned v0.15 BOOT preparation failed; use only the documented recovery mode'
  unmount_boot
  hash_unmounted_media
  inspect_boot
  [[ "$BOOT_STATE" == prepared && "$ACTIVE_BOOT_SHA256" == "$R46H_V10_BOOT_SHA256" ]] || \
    die 'post-prepare BOOT state mismatch'
  write_status prepared "$P1_SHA256" "$ACTIVE_BOOT_SHA256"
  printf 'R46H_V15_BOOT_PROMOTION result=pass mode=%s state=prepared write_started=true active_v0.10_unchanged=yes v0.10_modules=exact\n' \
    "$([[ "$recovery" == 1 ]] && printf recover-prepare || printf prepare)"
}

perform_activate() {
  local recovery=$1 transaction_recovery=0 operation_status rollback_status
  read_status
  [[ "$MODULE_STATE" == complete ]] || die 'activation requires exact v0.10 fallback modules and receipt'
  if [[ "$recovery" == 0 ]]; then
    [[ ( "$STATUS_STATE" == prepared || "$STATUS_STATE" == rollback-complete ) && \
      "$STATUS_P1_SHA256" == "$P1_SHA256" ]] || \
      die 'normal activation requires the exact prepared receipt and p1 digest'
    [[ "$BOOT_STATE" == prepared ]] || die 'normal activation requires exact prepared BOOT state'
  else
    [[ "$STATUS_STATE" == activate-intent ]] || die 'activation recovery requires activate-intent status'
    case "$BOOT_STATE" in
      prepared) transaction_recovery=0 ;;
      activate-partial-v10|activate-partial-v15) transaction_recovery=1 ;;
      activated)
        write_status activated "$P1_SHA256" "$R46H_V15_BOOT_SHA256"
        printf 'R46H_V15_BOOT_PROMOTION result=pass mode=recover-activate state=activated write_started=false\n'
        return
        ;;
      *) die 'activation recovery found an incompatible BOOT state' ;;
    esac
  fi
  write_status activate-intent "$P1_SHA256" "$R46H_V10_BOOT_SHA256"
  mount_boot rw
  begin_write
  set +e
  r46h_tx_activate "$BOOT_MOUNT" "$transaction_recovery"
  operation_status=$?
  set -e
  if (( operation_status != 0 )); then
    printf 'WARNING: activation failed; attempting exact v0.10 rollback before unmount\n' >&2
    set +e
    r46h_tx_rollback "$BOOT_MOUNT"
    rollback_status=$?
    set -e
    if (( rollback_status != 0 )); then
      printf 'HARD WARNING: active BOOT rollback proof failed; do not reboot or power off\n' >&2
      die 'activation and rollback both failed'
    fi
    unmount_boot
    hash_unmounted_media
    inspect_boot
    [[ "$BOOT_STATE" == prepared && "$ACTIVE_BOOT_SHA256" == "$R46H_V10_BOOT_SHA256" ]] || \
      die 'automatic rollback did not restore the exact prepared state'
    write_status rollback-complete "$P1_SHA256" "$ACTIVE_BOOT_SHA256"
    die 'activation failed and exact v0.10 was restored; review before retrying'
  fi
  unmount_boot
  hash_unmounted_media
  inspect_boot
  [[ "$BOOT_STATE" == activated && "$ACTIVE_BOOT_SHA256" == "$R46H_V15_BOOT_SHA256" ]] || \
    die 'post-activation BOOT state mismatch'
  write_status activated "$P1_SHA256" "$ACTIVE_BOOT_SHA256"
  printf 'R46H_V15_BOOT_PROMOTION result=pass mode=%s state=activated write_started=true v0.10_fallback=kernel+modules-exact v0.8_fallback=kernel+modules-exact saveenv_used=false\n' \
    "$([[ "$recovery" == 1 ]] && printf recover-activate || printf activate)"
  printf 'No reboot or poweroff was requested.\n'
}

perform_rollback() {
  read_status
  [[ "$MODULE_STATE" == complete ]] || die 'rollback requires exact v0.10 fallback modules and receipt'
  case "$STATUS_STATE" in
    prepared|activate-intent|activated|rollback-intent|rollback-complete|complete) ;;
    *) die 'rollback lacks a recognized promotion status' ;;
  esac
  write_status rollback-intent "$P1_SHA256" "$ACTIVE_BOOT_SHA256"
  mount_boot rw
  begin_write
  r46h_tx_rollback "$BOOT_MOUNT" || die 'exact v0.10 rollback failed; do not reboot or power off'
  unmount_boot
  hash_unmounted_media
  inspect_boot
  [[ "$BOOT_STATE" == prepared && "$ACTIVE_BOOT_SHA256" == "$R46H_V10_BOOT_SHA256" ]] || \
    die 'rollback verification failed; do not reboot or power off'
  write_status rollback-complete "$P1_SHA256" "$ACTIVE_BOOT_SHA256"
  printf 'R46H_V15_BOOT_PROMOTION result=pass mode=rollback state=prepared active_v0.10=yes v0.10_modules=exact v0.15_candidate=inert saveenv_used=false\n'
}

discover_devices
ensure_public_partitions_unmounted
verify_runtime_health
create_work
hash_unmounted_media
inspect_boot
read_status
MODULE_STATE=$(r46h_mod_detect_state "$MODULES_PARENT" "$STATE_DIR") || \
  die 'v0.10 fallback module state verification failed'

case "$mode" in
  preflight)
    case "$BOOT_STATE" in
      base)
        if [[ "$STATUS_STATE" == absent ]]; then
          [[ "$P1_SHA256" == "$EXPECTED_BASE_P1_SHA256" && "$MODULE_STATE" == absent ]] || \
            die 'base BOOT does not match the exact accepted pre-promotion boundary'
        else
          [[ "$STATUS_STATE" == prepare-intent ]] || die 'base BOOT has an unexpected promotion status'
          case "$MODULE_STATE" in
            absent|stage-partial|published-unreceipted|published-unreceipted-with-stage|complete|complete-with-stage) ;;
            *) die 'base BOOT has an unsupported v0.10 module recovery state' ;;
          esac
        fi
        ;;
      prepare-partial)
        [[ "$STATUS_STATE" == prepare-intent ]] || die 'partial prepare lacks matching intent status'
        [[ "$MODULE_STATE" == complete ]] || die 'partial BOOT prepare lacks exact v0.10 fallback modules'
        ;;
      activate-partial-v10|activate-partial-v15)
        [[ "$STATUS_STATE" == activate-intent ]] || die 'partial activation lacks matching intent status'
        [[ "$MODULE_STATE" == complete ]] || die 'partial activation lacks exact v0.10 fallback modules'
        ;;
      prepared)
        case "$STATUS_STATE" in
          prepare-intent|activate-intent|rollback-intent)
            [[ "$MODULE_STATE" == complete ]] || \
              die 'recoverable prepared BOOT lacks exact v0.10 fallback modules'
            ;;
          prepared|rollback-complete) verify_completed_status_matches_media ;;
          *) die 'prepared BOOT has an incompatible promotion status' ;;
        esac
        ;;
      activated)
        case "$STATUS_STATE" in
          activate-intent|rollback-intent)
            [[ "$MODULE_STATE" == complete ]] || \
              die 'recoverable activated BOOT lacks exact v0.10 fallback modules'
            ;;
          activated|complete) verify_completed_status_matches_media ;;
          *) die 'activated BOOT has an incompatible promotion status' ;;
        esac
        ;;
      rollback-partial-v10|rollback-partial-v15)
        [[ "$STATUS_STATE" == rollback-intent ]] || die 'partial rollback lacks matching intent status'
        [[ "$MODULE_STATE" == complete ]] || die 'partial rollback lacks exact v0.10 fallback modules'
        ;;
      *) die 'unsupported BOOT preflight state' ;;
    esac
    printf 'R46H_V15_BOOT_PROMOTION result=pass mode=preflight state=%s status=%s v0.10_modules=%s p1_sha256=%s prefix_sha256=%s write_started=false\n' \
      "$BOOT_STATE" "$STATUS_STATE" "$MODULE_STATE" "$P1_SHA256" "$PREFIX_SHA256"
    ;;
  prepare) perform_prepare 0 ;;
  recover-prepare) perform_prepare 1 ;;
  activate) perform_activate 0 ;;
  recover-activate) perform_activate 1 ;;
  rollback) perform_rollback ;;
  postflight)
    [[ "$BOOT_STATE" == activated && "$ACTIVE_BOOT_SHA256" == "$R46H_V15_BOOT_SHA256" ]] || \
      die 'postflight requires exact active v0.15 BOOT state'
    [[ "$MODULE_STATE" == complete ]] || die 'postflight requires exact v0.10 fallback modules'
    read_status
    [[ "$STATUS_STATE" == activated && "$STATUS_P1_SHA256" == "$P1_SHA256" ]] || \
      die 'postflight requires the exact activation receipt and p1 digest'
    write_status complete "$P1_SHA256" "$ACTIVE_BOOT_SHA256"
    printf 'R46H_V15_BOOT_PROMOTION result=pass mode=postflight state=complete p1_sha256=%s active_v0.15=yes v0.10_fallback=kernel+modules-exact v0.8_fallback=kernel+modules-exact saveenv_used=false\n' \
      "$P1_SHA256"
    ;;
esac
