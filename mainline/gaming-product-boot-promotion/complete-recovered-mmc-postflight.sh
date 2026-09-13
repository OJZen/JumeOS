#!/bin/bash
set -Eeuo pipefail
umask 077

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG

readonly COMPLETION_TOOL_ID=r46h-v15-recovered-mmc-postflight-v0.1
readonly CONFIRM_TOKEN=complete-v0.15-recovered-mmc-open
readonly STATE_DIR=/var/lib/r46h-boot-promotion/v0.15-gaming-product
readonly RETAINED_PAYLOAD=/var/lib/r46h-boot-promotion/v0.15-gaming-product/payload
readonly STATUS_FILE=/var/lib/r46h-boot-promotion/v0.15-gaming-product/STATUS
readonly BACKUP_DIR=/var/lib/r46h-boot-promotion/v0.15-gaming-product/legacy-kernel-inventory-backup
readonly LOCK_FILE=/run/r46h-v15-boot-promotion.lock
readonly EXPECTED_RUNNING_RELEASE=6.12.99-r46h-mainline-v0.15-gaming-product
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
readonly EXPECTED_ACTIVATED_P1_SHA256=e6ca320b5413a6fe224a8a9a89c3d4199d395237d3fc413ef93da50131e481c9
readonly EXPECTED_PAYLOAD_SUMS_SHA256=3e7cb49ca8da715f26618e71cb0afcf3bc641e0afadc902ca30eefc9601bb33f
readonly EXPECTED_STORAGE_HELPER_SHA256=c0e3cb1b69e5b4773f999c62e448cf44a645fe824bc4b8732eef33d8acbf842c
readonly EXPECTED_FIRSTBOOT='release=debian13-p2-gaming-v0.3'
readonly PRODUCT_KERNEL_DIR=/var/lib/r46h-gaming-product-kernel/v0.15-gaming-product
readonly PRODUCT_IMAGE=/var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/IMAGE
readonly PRODUCT_DTB=/var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/R46H.DTB
readonly PRODUCT_COMMANDS=/var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/UBOOT-CMDS.txt
readonly PRODUCT_RECEIPT=/var/lib/r46h-gaming-product-kernel/v0.15-gaming-product/RECEIPT
readonly EXPECTED_PRODUCT_IMAGE_SIZE=41570816
readonly EXPECTED_PRODUCT_IMAGE_SHA256=956ab3d5a2e53afbfe964ae75850e8591b44c093b9779867b31149b7b591f68f
readonly EXPECTED_PRODUCT_DTB_SIZE=49518
readonly EXPECTED_PRODUCT_DTB_SHA256=4d6d4ebad3b98600b6e9a38df4ca82230335558497a9e15dd0e81ca60e304b61
readonly EXPECTED_PRODUCT_COMMANDS_SIZE=981
readonly EXPECTED_PRODUCT_COMMANDS_SHA256=51bf7caf6e9a08f01e1007a0010841e539300d8776851630e9d7d2829589d717
readonly EXPECTED_PRODUCT_RECEIPT_SHA256=a90b359f2275bdc732b5814bf9d1dc328844532a1e3c2a4d23577068978fffbd
readonly EXPECTED_BACKUP_RECEIPT_SHA256=620d3cee882fc8c1d107a8dd42ef11ead09e317de3228b34c05259b4bb4a8012
readonly EXPECTED_BACKUP_RESULT_SHA256=02a00d3521e1b4b7fe4a0ab995f8265541242d0b7f8cd84aed6a240637c7bbe4
readonly EXPECTED_ORIGINAL_IMAGE_SHA256=ae08557630a4bae7e8df5fa39c0651b1ef4380233989aca4450827c3018ea65f
readonly EXPECTED_FIXED_IMAGE_SHA256=eda795942083d198d7223dcf3f65e19c05c4c7bfc754935e4f84d3a0cc15bbfd
readonly EXPECTED_LEGACY_IMAGE_SIZE=13096968

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
readonly SCRIPT_DIR

WORK_DIR=
BOOT_MOUNT=
BOOT_MOUNTED=0
BOOT_DEVICE=
ROOT_DEVICE=
ROMS_DEVICE=
WHOLE_DEVICE=

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

hash_file() {
  sha256sum "$1" | awk '{print $1}'
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

check_file() {
  local path=$1 expected_size=$2 expected_hash=$3 label=$4
  require_identity "$path" 400 "$label"
  [[ "$(stat -c '%s' "$path")" == "$expected_size" ]] || die "size mismatch for ${label}"
  [[ "$(hash_file "$path")" == "$expected_hash" ]] || die "SHA-256 mismatch for ${label}"
}

r46h_expected_status() {
  local state=$1
  case "$state" in activated|complete) ;;
    *) die 'unsupported expected status state' ;;
  esac
  printf '%s\n' \
    'format_version=1' \
    'tool_id=r46h-v15-boot-promotion-v0.1' \
    "state=$state" \
    "baseline_p1_sha256=$EXPECTED_BASE_P1_SHA256" \
    "p1_sha256=$EXPECTED_ACTIVATED_P1_SHA256" \
    "prefix_sha256=$EXPECTED_PREFIX_SHA256" \
    'active_boot_sha256=f41ab69f17cd22fb22446e390c46325d4e536cf8dee1bd9ab85682297dca1ac8' \
    'target_boot_sha256=f41ab69f17cd22fb22446e390c46325d4e536cf8dee1bd9ab85682297dca1ac8' \
    'fallback_module_tree_sha256=a70796c050de93c4c212180addf54a17efe7732d355db2b52d0bfcab6c56cc16' \
    'secondary_fallback_module_tree_sha256=2ec532a3d3c6833538bd4ffd284122afa30bea0945e832f57be481527986f210' \
    'target_module_tree_sha256=bd53fad3997ced39a15c69dbd70525106e891e5529dcef73bbbcfb699aafc291' \
    "payload_sha256s_sha256=$EXPECTED_PAYLOAD_SUMS_SHA256" \
    'saveenv_used=false'
}

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
      /run/r46h-v15-recovered-postflight.*) rm -rf -- "$WORK_DIR" ;;
      *) printf 'WARNING: refusing unexpected work cleanup path: %s\n' "$WORK_DIR" >&2 ;;
    esac
  fi
  exit "$status"
}

verify_hotfixed_product() {
  require_identity /var/lib/r46h/firstboot-complete 600 'firstboot completion marker'
  [[ "$(< /var/lib/r46h/firstboot-complete)" == "$EXPECTED_FIRSTBOOT" ]] || \
    die 'firstboot completion marker mismatch'
  require_directory "$PRODUCT_KERNEL_DIR" 700 'product kernel staging'
  check_file "$PRODUCT_IMAGE" "$EXPECTED_PRODUCT_IMAGE_SIZE" \
    "$EXPECTED_PRODUCT_IMAGE_SHA256" 'product Image'
  check_file "$PRODUCT_DTB" "$EXPECTED_PRODUCT_DTB_SIZE" \
    "$EXPECTED_PRODUCT_DTB_SHA256" 'product DTB'
  check_file "$PRODUCT_COMMANDS" "$EXPECTED_PRODUCT_COMMANDS_SIZE" \
    "$EXPECTED_PRODUCT_COMMANDS_SHA256" 'product one-shot commands'
  require_identity "$PRODUCT_RECEIPT" 400 'product kernel receipt'
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

  require_identity /var/lib/r46h-product-hotfixes/storage-audit-tab-v1/RECEIPT 600 \
    'storage-audit hotfix receipt'
  require_identity /var/lib/r46h-product-hotfixes/smoke-core-analog-v1/RECEIPT 600 \
    'smoke-core hotfix receipt'
  require_identity /var/lib/r46h-product-hotfixes/game-ui-volume-v1/RECEIPT 600 \
    'game-runner hotfix receipt'
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

verify_legacy_backup() {
  local members
  require_directory "$BACKUP_DIR" 700 'legacy kernel inventory backup'
  require_directory "$BACKUP_DIR/original" 700 'original legacy kernel backup directory'
  require_directory "$BACKUP_DIR/arkos4clone_fix" 700 'fixed legacy kernel backup directory'
  members=$(find "$BACKUP_DIR" -mindepth 1 -maxdepth 2 -printf '%P\n' | LC_ALL=C sort)
  [[ "$members" == $'RECEIPT\nRESULT\narkos4clone_fix\narkos4clone_fix/Image\noriginal\noriginal/Image' ]] || \
    die 'legacy kernel inventory backup member set mismatch'
  check_file "$BACKUP_DIR/original/Image" "$EXPECTED_LEGACY_IMAGE_SIZE" \
    "$EXPECTED_ORIGINAL_IMAGE_SHA256" 'original legacy kernel backup'
  check_file "$BACKUP_DIR/arkos4clone_fix/Image" "$EXPECTED_LEGACY_IMAGE_SIZE" \
    "$EXPECTED_FIXED_IMAGE_SHA256" 'fixed legacy kernel backup'
  check_file "$BACKUP_DIR/RECEIPT" 657 "$EXPECTED_BACKUP_RECEIPT_SHA256" \
    'legacy kernel backup receipt'
  check_file "$BACKUP_DIR/RESULT" 801 "$EXPECTED_BACKUP_RESULT_SHA256" \
    'legacy kernel reclaim result'
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
  local ext4_errors storage_state
  [[ "$(uname -r)" == "$EXPECTED_RUNNING_RELEASE" ]] || die 'ordinary boot is not exact v0.15'
  [[ "$(findmnt -rn -o PARTUUID /)" == "$EXPECTED_ROOT_PARTUUID" ]] || \
    die 'unexpected root PARTUUID'
  [[ "$(findmnt -rn -o FSTYPE /)" == ext4 ]] || die 'root is not ext4'
  [[ ",$(findmnt -rn -o OPTIONS /)," == *,rw,* ]] || die 'root is not writable'
  ext4_errors=/sys/fs/ext4/${ROOT_DEVICE##*/}/errors_count
  [[ -f "$ext4_errors" && "$(<"$ext4_errors")" == 0 ]] || \
    die 'root ext4 error counter is nonzero or unavailable'
  [[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd has failed units'
  [[ "$(systemctl is-active r46h-gaming-frontend.service || true)" == inactive ]] || \
    die 'stop the gaming frontend before postflight'
  [[ -z "$(pgrep -x retroarch || true)" ]] || die 'RetroArch is still running'
  [[ -z "$(find /run -maxdepth 1 -type d -name 'r46h-game-ui.*' -print -quit)" ]] || \
    die 'a game session directory remains'
  storage_state=$(r46h_storage_health_current) || \
    die 'current boot contains an unaccepted storage fault marker'
  [[ "$storage_state" == recovered-known-open ]] || \
    die 'use the retained ordinary postflight when MMC initialization is clean'
}

mount_boot_readonly() {
  BOOT_MOUNT=$WORK_DIR/boot
  mkdir "$BOOT_MOUNT"
  mount -t vfat -o ro,nosuid,nodev,noexec,umask=0077 "$BOOT_DEVICE" "$BOOT_MOUNT"
  BOOT_MOUNTED=1
  [[ "$(findmnt -rn -T "$BOOT_MOUNT" -o SOURCE)" == "$BOOT_DEVICE" ]] || \
    die 'private BOOT mount source mismatch'
  [[ "$(findmnt -rn -T "$BOOT_MOUNT" -o FSTYPE)" == vfat ]] || \
    die 'private BOOT mount filesystem mismatch'
  [[ ",$(findmnt -rn -T "$BOOT_MOUNT" -o OPTIONS)," == *,ro,* ]] || \
    die 'private BOOT mount is not read-only'
}

unmount_boot() {
  (( BOOT_MOUNTED == 1 )) || die 'BOOT is not privately mounted'
  umount "$BOOT_MOUNT"
  BOOT_MOUNTED=0
  ensure_public_partitions_unmounted
}

verify_media() {
  local prefix p1 state active
  ensure_public_partitions_unmounted
  prefix=$(dd if="$WHOLE_DEVICE" bs=1048576 \
    count=$((EXPECTED_PREFIX_SIZE / 1048576)) iflag=fullblock status=none | \
    sha256sum | awk '{print $1}')
  [[ "$prefix" == "$EXPECTED_PREFIX_SHA256" ]] || die 'g92 prefix and MBR SHA-256 mismatch'
  p1=$(sha256sum "$BOOT_DEVICE" | awk '{print $1}')
  [[ "$p1" == "$EXPECTED_ACTIVATED_P1_SHA256" ]] || die 'activated p1 SHA-256 mismatch'

  mount_boot_readonly
  state=$(r46h_tx_detect_state "$BOOT_MOUNT") || die 'BOOT state verification failed'
  [[ "$state" == activated ]] || die 'BOOT is not in the exact activated state'
  active=$(hash_file "$BOOT_MOUNT/$R46H_ACTIVE_BOOT_NAME")
  [[ "$active" == "$R46H_V15_BOOT_SHA256" ]] || die 'active BOOT script is not exact v0.15'
  r46h_tx_check_file "$BOOT_MOUNT/Image" "$EXPECTED_LEGACY_IMAGE_SIZE" \
    "$EXPECTED_FIXED_IMAGE_SHA256" 'retained root legacy Image' || \
    die 'retained root legacy Image mismatch'
  [[ ! -e "$BOOT_MOUNT/consoles/kernel/original/Image" && \
    ! -L "$BOOT_MOUNT/consoles/kernel/original/Image" ]] || \
    die 'authorized original inventory path is still present on BOOT'
  [[ ! -e "$BOOT_MOUNT/consoles/kernel/arkos4clone_fix/Image" && \
    ! -L "$BOOT_MOUNT/consoles/kernel/arkos4clone_fix/Image" ]] || \
    die 'authorized fixed inventory path is still present on BOOT'
  unmount_boot
}

publish_complete_status() {
  local stage=$STATE_DIR/.STATUS.recovered-mmc.stage
  require_identity "$STATUS_FILE" 600 'promotion status'
  cmp -s "$STATUS_FILE" <(r46h_expected_status activated) || \
    die 'promotion status is not the exact activated receipt'
  if [[ -e "$stage" || -L "$stage" ]]; then
    [[ -f "$stage" && ! -L "$stage" && \
      "$(stat -c '%u:%g:%a:%h' "$stage")" == 0:0:600:1 && \
      "$(stat -c '%s' "$stage")" -le 4096 ]] || \
      die 'completion status stage is unsafe'
    rm -f -- "$stage"
    sync
  fi
  r46h_expected_status complete > "$stage"
  chown root:root "$stage"
  chmod 0600 "$stage"
  cmp -s "$stage" <(r46h_expected_status complete) || die 'completion status stage mismatch'

  trap '' INT TERM HUP
  sync
  mv -f -- "$stage" "$STATUS_FILE"
  sync
  require_identity "$STATUS_FILE" 600 'completed promotion status'
  cmp -s "$STATUS_FILE" <(r46h_expected_status complete) || \
    die 'completed promotion status verification failed'
}

main() {
  local module_state storage_state
  (( EUID == 0 )) || die 'root is required'
  [[ "$#" == 2 && $1 == --confirm && $2 == "$CONFIRM_TOKEN" ]] || \
    die "usage: complete-recovered-mmc-postflight.sh --confirm $CONFIRM_TOKEN"
  require_directory "$SCRIPT_DIR" 700 'completion staging directory'
  require_identity "$SCRIPT_DIR/complete-recovered-mmc-postflight.sh" 500 \
    'completion script'
  require_identity "$SCRIPT_DIR/storage-health.sh" 400 'storage health helper'
  [[ "$(hash_file "$SCRIPT_DIR/storage-health.sh")" == "$EXPECTED_STORAGE_HELPER_SHA256" ]] || \
    die 'storage health helper SHA-256 mismatch'
  # shellcheck source=storage-health.sh
  source "$SCRIPT_DIR/storage-health.sh"

  exec 9>"$LOCK_FILE"
  [[ "$(stat -c '%u:%g:%a:%h' "$LOCK_FILE")" == 0:0:600:1 ]] || \
    die 'promotion lock identity mismatch'
  flock -n 9 || die 'another BOOT promotion process holds the lock'
  trap cleanup EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP

  require_directory "$STATE_DIR" 700 'promotion state directory'
  require_directory "$RETAINED_PAYLOAD" 700 'retained promotion payload'
  require_identity "$RETAINED_PAYLOAD/install.sh" 500 'retained installer'
  require_identity "$RETAINED_PAYLOAD/transaction.sh" 400 'retained transaction helper'
  require_identity "$RETAINED_PAYLOAD/fallback-modules.sh" 400 \
    'retained fallback module helper'
  require_identity "$RETAINED_PAYLOAD/SHA256SUMS" 400 'retained payload checksums'
  [[ "$(hash_file "$RETAINED_PAYLOAD/SHA256SUMS")" == "$EXPECTED_PAYLOAD_SUMS_SHA256" ]] || \
    die 'retained payload checksum manifest mismatch'
  "$RETAINED_PAYLOAD/install.sh" --check-payload >/dev/null || \
    die 'retained payload self-check failed'
  # shellcheck source=transaction.sh
  source "$RETAINED_PAYLOAD/transaction.sh"
  # shellcheck source=fallback-modules.sh
  source "$RETAINED_PAYLOAD/fallback-modules.sh"

  discover_devices
  R46H_BOOT_DEVICE=$BOOT_DEVICE
  export R46H_BOOT_DEVICE
  ensure_public_partitions_unmounted
  verify_runtime_health
  verify_hotfixed_product
  verify_legacy_backup
  require_identity "$STATUS_FILE" 600 'promotion status'
  [[ "$(awk 'END {print NR}' "$STATUS_FILE")" == 13 ]] || \
    die 'promotion status field count mismatch'
  cmp -s "$STATUS_FILE" <(r46h_expected_status activated) || \
    die 'promotion status does not match the exact activation receipt'

  r46h_mod_verify_existing_fallbacks /usr/lib/modules || \
    die 'existing v0.8 fallback or v0.15 target module tree is not exact'
  module_state=$(r46h_mod_detect_state /usr/lib/modules "$STATE_DIR") || \
    die 'v0.10 fallback module state verification failed'
  [[ "$module_state" == complete ]] || die 'exact v0.10 fallback modules are incomplete'

  WORK_DIR=$(mktemp -d /run/r46h-v15-recovered-postflight.XXXXXX)
  chmod 0700 "$WORK_DIR"
  verify_media
  "$RETAINED_PAYLOAD/install.sh" --check-payload >/dev/null || \
    die 'retained payload changed during postflight'
  storage_state=$(r46h_storage_health_current) || \
    die 'a storage fault appeared during postflight'
  [[ "$storage_state" == recovered-known-open ]] || \
    die 'MMC recovery evidence changed during postflight'
  [[ "$(<"/sys/fs/ext4/${ROOT_DEVICE##*/}/errors_count")" == 0 ]] || \
    die 'root ext4 error counter changed during postflight'
  [[ -z "$(systemctl --failed --no-legend --plain)" ]] || \
    die 'systemd gained a failed unit during postflight'
  cmp -s "$STATUS_FILE" <(r46h_expected_status activated) || \
    die 'promotion status changed during postflight'

  publish_complete_status
  printf 'R46H_V15_BOOT_PROMOTION result=pass mode=recovered-mmc-postflight state=complete p1_sha256=%s active_v0.15=yes v0.10_fallback=kernel+modules-exact v0.8_fallback=kernel+modules-exact mmc_init=recovered-known-open later_storage_faults=none saveenv_used=false\n' \
    "$EXPECTED_ACTIVATED_P1_SHA256"
  printf 'The intermittent cold MMC initialization item remains OPEN. No reboot or poweroff was requested.\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
