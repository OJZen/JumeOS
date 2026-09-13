#!/usr/bin/env bash
set -Eeuo pipefail

readonly SYSTEM_PATH=/usr/sbin:/usr/bin:/sbin:/bin
if [[ "${R46H_STAGE_TEST_MODE:-0}" == "1" ]]; then
  [[ -f /.dockerenv ]] || {
    printf 'error: R46H_STAGE_TEST_MODE 仅允许在隔离容器中使用\n' >&2
    exit 1
  }
  test_bin=${R46H_STAGE_TEST_BIN:-}
  [[ -d "$test_bin" && ! -L "$test_bin" ]] || {
    printf 'error: 测试工具目录非法\n' >&2
    exit 1
  }
  test_bin=$(cd -- "$test_bin" && pwd -P)
  [[ "$test_bin" == /run/r46h-stage-test.* ]] || {
    printf 'error: 测试工具目录必须位于 /run/r46h-stage-test.*\n' >&2
    exit 1
  }
  run_owner=$(/usr/bin/stat -c '%u' -- /run)
  run_mode=$(/usr/bin/stat -c '%a' -- /run)
  test_bin_owner=$(/usr/bin/stat -c '%u' -- "$test_bin")
  test_bin_mode=$(/usr/bin/stat -c '%a' -- "$test_bin")
  [[ "$run_owner" == "0" && "$run_mode" =~ ^[0-7]{3,4}$ ]] || {
    printf 'error: /run 不是可信的 root-owned 目录\n' >&2
    exit 1
  }
  (( (8#$run_mode & 8#022) == 0 )) || {
    printf 'error: /run 可被非 root 用户写入\n' >&2
    exit 1
  }
  [[ "$test_bin_owner" == "0" && "$test_bin_mode" == "700" ]] || {
    printf 'error: 测试工具目录必须为 root-owned 0700\n' >&2
    exit 1
  }
  PATH="$test_bin:$SYSTEM_PATH"
else
  PATH=$SYSTEM_PATH
fi
export PATH
unset R46H_STAGE_TEST_MODE R46H_STAGE_TEST_BIN
unset CDPATH
unset -f findmnt mountpoint lsblk stat find sort uniq head comm sha256sum shasum \
  sed awk df wc tr readlink mktemp install cp chmod chown mv sync rm rmdir mkdir 2>/dev/null || true
umask 022

PACKAGE_DIR=""
BOOT_MOUNT=""
ROOT_MOUNT=""
SUCCESS=0
CREATED_MODULES=0
CREATED_MODULE_STAGE=0
CREATED_BOOT=()
CREATED_BOOT_IDS=()
CREATED_BOOT_TEMPS=()
CREATED_BOOT_TEMP_IDS=()
CREATED_BOOT_TEMP_HASHES=()
CREATED_ROOT_DIRS=()
MODULE_STAGE_DIR=""
MODULE_DEST=""
MODULE_STAGE_ID=""
VERIFY_TMP=""
VERIFY_TMP_ID=""
kernel_release=""
boot_source=""
root_source=""
boot_majmin=""
root_majmin=""
readonly BOOT_SAFETY_KIB=4096
readonly ROOT_SAFETY_KIB=8192
readonly ROOT_SAFETY_INODES=16

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

cleanup() {
  local status=$?
  local name
  local index
  local destination_id
  local cleanup_hash
  local boot_cleanup_safe=0
  local root_cleanup_safe=0
  trap - EXIT

  if (( SUCCESS == 0 && (${#CREATED_BOOT[@]} > 0 || ${#CREATED_BOOT_TEMPS[@]} > 0) )); then
    if declare -F mount_identity_is_current >/dev/null && \
       mount_identity_is_current "$BOOT_MOUNT" "$boot_source" "$boot_majmin"; then
      boot_cleanup_safe=1
      for ((index=0; index<${#CREATED_BOOT_TEMPS[@]}; index++)); do
        name=${CREATED_BOOT_TEMPS[index]}
        if [[ "$name" == "$BOOT_MOUNT/"* && -f "$name" && ! -L "$name" ]] && \
           path_mount_identity_is_current "$name" "$boot_source" "$boot_majmin"; then
          destination_id=$(stat -c '%d:%i' -- "$name" 2>/dev/null || true)
          cleanup_hash=""
          if declare -F hash_file >/dev/null; then
            cleanup_hash=$(hash_file "$name" 2>/dev/null || true)
          fi
          if [[ "$destination_id" == "${CREATED_BOOT_TEMP_IDS[index]}" || \
                ( -n "${CREATED_BOOT_TEMP_HASHES[index]}" && \
                  "$cleanup_hash" == "${CREATED_BOOT_TEMP_HASHES[index]}" ) ]]; then
            rm -f -- "$name"
          fi
        fi
      done
      for ((index=0; index<${#CREATED_BOOT[@]}; index++)); do
        name="$BOOT_MOUNT/${CREATED_BOOT[index]}"
        if [[ -f "$name" && ! -L "$name" ]] && \
           path_mount_identity_is_current "$name" "$boot_source" "$boot_majmin"; then
          destination_id=$(stat -c '%d:%i' -- "$name" 2>/dev/null || true)
          if [[ "$destination_id" == "${CREATED_BOOT_IDS[index]}" ]]; then
            rm -f -- "$name"
          fi
        fi
      done
    else
      printf 'warning: BOOT 挂载身份已变化，拒绝自动清理；请人工检查 %s 下的 .r46h-boot-stage.* 和本次测试文件。\n' \
        "$BOOT_MOUNT" >&2
    fi
  fi

  if (( SUCCESS == 0 && \
        (CREATED_MODULES == 1 || CREATED_MODULE_STAGE == 1 || \
         ${#CREATED_ROOT_DIRS[@]} > 0) )); then
    if declare -F mount_identity_is_current >/dev/null && \
       mount_identity_is_current "$ROOT_MOUNT" "$root_source" "$root_majmin"; then
      root_cleanup_safe=1
    else
      printf 'warning: root 挂载身份已变化，拒绝自动清理；请人工检查 %s 和 %s。\n' \
        "${MODULE_STAGE_DIR:-未创建暂存目录}" "${MODULE_DEST:-未创建目标目录}" >&2
    fi
  fi

  if (( root_cleanup_safe == 1 )); then
    if (( CREATED_MODULES == 1 )) && [[ -n "$MODULE_DEST" ]] && \
       [[ "$MODULE_DEST" == "$ROOT_MOUNT/"* ]] && \
       [[ -d "$MODULE_DEST" && ! -L "$MODULE_DEST" ]] && \
       path_mount_identity_is_current "$MODULE_DEST" "$root_source" "$root_majmin"; then
      destination_id=$(stat -c '%d:%i' -- "$MODULE_DEST" 2>/dev/null || true)
      if [[ -n "$MODULE_STAGE_ID" && "$destination_id" == "$MODULE_STAGE_ID" ]]; then
        rm -rf -- "$MODULE_DEST"
      fi
    fi
    if (( CREATED_MODULE_STAGE == 1 )) && [[ -n "$MODULE_STAGE_DIR" ]] && \
       [[ "$MODULE_STAGE_DIR" == "$ROOT_MOUNT/"* ]] && \
       [[ -d "$MODULE_STAGE_DIR" && ! -L "$MODULE_STAGE_DIR" ]] && \
       path_mount_identity_is_current "$MODULE_STAGE_DIR" "$root_source" "$root_majmin"; then
      destination_id=$(stat -c '%d:%i' -- "$MODULE_STAGE_DIR" 2>/dev/null || true)
      if [[ -n "$MODULE_STAGE_ID" && "$destination_id" == "$MODULE_STAGE_ID" ]]; then
        rm -rf -- "$MODULE_STAGE_DIR"
      fi
    elif (( CREATED_MODULE_STAGE == 1 )) && [[ -n "$MODULE_DEST" ]] && \
         [[ "$MODULE_DEST" == "$ROOT_MOUNT/"* ]] && \
         [[ -d "$MODULE_DEST" && ! -L "$MODULE_DEST" ]] && \
         path_mount_identity_is_current "$MODULE_DEST" "$root_source" "$root_majmin"; then
      destination_id=$(stat -c '%d:%i' -- "$MODULE_DEST" 2>/dev/null || true)
      if [[ -n "$MODULE_STAGE_ID" && "$destination_id" == "$MODULE_STAGE_ID" ]]; then
        rm -rf -- "$MODULE_DEST"
      fi
    fi
    for ((index=${#CREATED_ROOT_DIRS[@]} - 1; index >= 0; index--)); do
      name=${CREATED_ROOT_DIRS[index]}
      if [[ "$name" == "$ROOT_MOUNT/"* && -d "$name" && ! -L "$name" ]] && \
         path_mount_identity_is_current "$name" "$root_source" "$root_majmin"; then
        rmdir -- "$name" 2>/dev/null || true
      fi
    done
  fi

  if (( boot_cleanup_safe == 1 || root_cleanup_safe == 1 )); then
    sync || true
  fi

  if [[ -n "$VERIFY_TMP" && "$VERIFY_TMP" == /run/r46h-stage-verify.* && \
        -d "$VERIFY_TMP" && ! -L "$VERIFY_TMP" ]]; then
    destination_id=$(stat -c '%d:%i' -- "$VERIFY_TMP" 2>/dev/null || true)
    if [[ -n "$VERIFY_TMP_ID" && "$destination_id" == "$VERIFY_TMP_ID" ]]; then
      rm -rf -- "$VERIFY_TMP"
    fi
  fi

  if (( SUCCESS == 0 && status == 0 )); then
    status=1
  fi
  exit "$status"
}
trap cleanup EXIT

usage() {
  cat <<'EOF'
把已校验的 R46H 主线测试包旁路安装到已挂载的备用 TF 卡。

用法:
  sudo mainline/scripts/stage-test-to-sd.sh \
    --package-dir PATH \
    --boot-mount PATH \
    --root-mount PATH

安全约束:
  - boot/root 必须是同一张可移除/外接块设备上的两个不同分区；
  - 拒绝当前系统盘、bind mount、非直接块设备挂载；
  - BOOT 必须是 FAT/vfat，root 必须是 ext4；
  - BOOT 必须已有 boot.ini，root 必须已有 etc/os-release；
  - 复制前核对 BOOT/rootfs 可用空间及 rootfs inode；
  - 不修改 boot.ini，不覆盖任何现有测试文件或同版本 modules；
  - SHA256SUMS 必须精确覆盖全部普通文件，并拒绝链接/特殊文件；
  - 离线 rootfs 的绝对 /lib 链接按该 rootfs 内路径解析，绝不跟随到主机；
  - 逐文件复制并复验摘要；挂载身份稳定时失败自动回滚；
  - 若写入中掉盘或换盘则停止自动清理，打印需要人工检查的精确位置。

安装后仍使用原内核启动。真正启用及回退步骤见对应功能 runbook 和 docs/DEVELOPMENT.md。
EOF
}

require_value() {
  local option=$1
  local value=${2:-}
  [[ -n "$value" ]] || die "$option 需要参数"
}

while (( $# > 0 )); do
  case "$1" in
    --package-dir)
      require_value "$1" "${2:-}"
      PACKAGE_DIR=$2
      shift 2
      ;;
    --boot-mount)
      require_value "$1" "${2:-}"
      BOOT_MOUNT=$2
      shift 2
      ;;
    --root-mount)
      require_value "$1" "${2:-}"
      ROOT_MOUNT=$2
      shift 2
      ;;
    -h|--help)
      usage
      SUCCESS=1
      exit 0
      ;;
    *)
      die "未知参数: $1"
      ;;
  esac
done

(( EUID == 0 )) || die "请用 sudo 运行，以便保留 modules 权限"
command -v findmnt >/dev/null 2>&1 || die "缺少 findmnt（util-linux）"
command -v mountpoint >/dev/null 2>&1 || die "缺少 mountpoint（util-linux）"
command -v lsblk >/dev/null 2>&1 || die "缺少 lsblk（util-linux）"

canonical_dir() {
  local label=$1
  local path=$2

  [[ -n "${path//[[:space:]]/}" ]] || die "$label 不能为空"
  [[ "$path" != "/" ]] || die "$label 不能是根目录"
  [[ -d "$path" && ! -L "$path" ]] || die "$label 必须是目录且不能是符号链接: $path"
  (cd -- "$path" && pwd -P)
}

PACKAGE_DIR=$(canonical_dir "package-dir" "$PACKAGE_DIR")
BOOT_MOUNT=$(canonical_dir "boot-mount" "$BOOT_MOUNT")
ROOT_MOUNT=$(canonical_dir "root-mount" "$ROOT_MOUNT")
[[ "$BOOT_MOUNT" != "$ROOT_MOUNT" ]] || die "boot-mount 和 root-mount 不能相同"
mountpoint -q -- "$BOOT_MOUNT" || die "boot-mount 不是真实挂载点: $BOOT_MOUNT"
mountpoint -q -- "$ROOT_MOUNT" || die "root-mount 不是真实挂载点: $ROOT_MOUNT"

findmnt_value() {
  local field=$1
  local target=$2
  local value

  value=$(findmnt -e -n -r -o "$field" --target "$target") || die "无法读取挂载信息: $target"
  [[ -n "$value" && "$value" != *$'\n'* ]] || die "挂载信息不唯一: $target ($field)"
  printf '%s\n' "$value"
}

path_mount_identity_is_current() {
  local path=$1
  local expected_source=$2
  local expected_majmin=$3
  local identity
  local actual_source
  local actual_majmin
  local extra

  [[ -n "$expected_source" && -n "$expected_majmin" ]] || return 1
  identity=$(findmnt -e -n -r -o SOURCE,MAJ:MIN --target "$path" 2>/dev/null) || return 1
  read -r actual_source actual_majmin extra <<< "$identity"
  [[ -n "$actual_source" && -n "$actual_majmin" && -z "${extra:-}" ]] || return 1
  [[ "$actual_source" == "$expected_source" && "$actual_majmin" == "$expected_majmin" ]]
}

mount_identity_is_current() {
  local mount_path=$1
  local expected_source=$2
  local expected_majmin=$3

  mountpoint -q -- "$mount_path" 2>/dev/null || return 1
  path_mount_identity_is_current "$mount_path" "$expected_source" "$expected_majmin"
}

require_mount_identity() {
  local label=$1
  local mount_path=$2
  local expected_source=$3
  local expected_majmin=$4

  mount_identity_is_current "$mount_path" "$expected_source" "$expected_majmin" || \
    die "$label 挂载身份在写入前发生变化，拒绝继续"
}

assert_resolved_rootfs_mounts() {
  local relative=$1
  local current=$ROOT_MOUNT
  local component
  local -a components

  require_mount_identity "root" "$ROOT_MOUNT" "$root_source" "$root_majmin"
  IFS='/' read -r -a components <<< "$relative"
  for component in "${components[@]}"; do
    current="$current/$component"
    if [[ -e "$current" || -L "$current" ]]; then
      path_mount_identity_is_current "$current" "$root_source" "$root_majmin" || \
        die "rootfs 解析路径跨越嵌套挂载或 bind mount: $current"
    else
      break
    fi
  done
}

block_value() {
  local device=$1
  local field=$2
  local value

  value=$(lsblk -d -n -p -r -o "$field" -- "$device") || return 1
  [[ -n "$value" && "$value" != *$'\n'* ]] || return 1
  printf '%s\n' "$value"
}

top_backing_disk() {
  local device=$1
  local type
  local parent
  local depth=0

  while (( depth < 16 )); do
    type=$(block_value "$device" TYPE) || return 1
    if [[ "$type" == "disk" ]]; then
      printf '%s\n' "$device"
      return 0
    fi
    parent=$(block_value "$device" PKNAME) || return 1
    [[ "$parent" == /dev/* ]] || parent="/dev/$parent"
    [[ "$parent" != "$device" ]] || return 1
    device=$parent
    depth=$((depth + 1))
  done
  return 1
}

validate_direct_partition_source() {
  local label=$1
  local source=$2
  local type

  [[ "$source" == /dev/* && "$source" != *'['* && "$source" != *']'* ]] || \
    die "$label 不是直接块设备挂载（拒绝 bind mount）: $source"
  type=$(block_value "$source" TYPE) || die "$label 不是可验证的块设备: $source"
  [[ "$type" == "part" ]] || die "$label 必须直接挂载块设备分区，实际类型为 $type"
}

boot_fstype=$(findmnt_value FSTYPE "$BOOT_MOUNT")
root_fstype=$(findmnt_value FSTYPE "$ROOT_MOUNT")
case "$boot_fstype" in
  vfat|fat|msdos) ;;
  *) die "BOOT 文件系统必须是 FAT/vfat，实际为 $boot_fstype" ;;
esac
[[ "$root_fstype" == "ext4" ]] || die "root 文件系统必须是 ext4，实际为 $root_fstype"

boot_source=$(findmnt_value SOURCE "$BOOT_MOUNT")
root_source=$(findmnt_value SOURCE "$ROOT_MOUNT")
system_root_source=$(findmnt_value SOURCE /)
boot_majmin=$(findmnt_value MAJ:MIN "$BOOT_MOUNT")
root_majmin=$(findmnt_value MAJ:MIN "$ROOT_MOUNT")
system_root_majmin=$(findmnt_value MAJ:MIN /)
[[ "$boot_majmin" =~ ^[0-9]+:[0-9]+$ && "$root_majmin" =~ ^[0-9]+:[0-9]+$ && \
   "$system_root_majmin" =~ ^[0-9]+:[0-9]+$ ]] || die "挂载设备 MAJ:MIN 信息非法"
[[ "$boot_majmin" != "$root_majmin" ]] || die "BOOT/root 不能是同一个分区或 bind mount"

validate_direct_partition_source "BOOT" "$boot_source"
validate_direct_partition_source "root" "$root_source"
[[ "$system_root_source" == /dev/* && "$system_root_source" != *'['* ]] || \
  die "无法安全识别当前 / 的块设备来源: $system_root_source"
boot_source_majmin=$(block_value "$boot_source" MAJ:MIN) || die "无法读取 BOOT 块设备编号"
root_source_majmin=$(block_value "$root_source" MAJ:MIN) || die "无法读取 root 块设备编号"
system_source_majmin=$(block_value "$system_root_source" MAJ:MIN) || die "无法读取当前 / 块设备编号"
[[ "$boot_source_majmin" == "$boot_majmin" && "$root_source_majmin" == "$root_majmin" ]] || \
  die "挂载来源与块设备编号不一致（疑似 bind mount）"
[[ "$system_source_majmin" == "$system_root_majmin" ]] || \
  die "当前 / 的挂载来源与块设备编号不一致"

boot_disk=$(top_backing_disk "$boot_source") || die "无法解析 BOOT 的 backing device: $boot_source"
root_disk=$(top_backing_disk "$root_source") || die "无法解析 root 的 backing device: $root_source"
system_root_disk=$(top_backing_disk "$system_root_source") || \
  die "无法解析当前 / 的 backing device: $system_root_source"
[[ "$boot_disk" == "$root_disk" ]] || \
  die "BOOT/root 不在同一张块设备上: $boot_disk != $root_disk"
[[ "$boot_disk" != "$system_root_disk" && "$boot_majmin" != "$system_root_majmin" && \
   "$root_majmin" != "$system_root_majmin" ]] || \
  die "目标分区位于当前 / 所在系统盘，拒绝写入: $boot_disk"

target_rm=$(block_value "$boot_disk" RM) || die "无法读取目标设备 removable 属性: $boot_disk"
target_transport=$(block_value "$boot_disk" TRAN 2>/dev/null || true)
case "$target_transport" in
  usb|mmc|sd) target_is_external=1 ;;
  *) target_is_external=0 ;;
esac
[[ "$target_rm" == "1" || "$target_is_external" == "1" ]] || \
  die "目标设备既不可移除也不是受支持的外接介质: $boot_disk (RM=$target_rm TRAN=${target_transport:-unknown})"

[[ -f "$BOOT_MOUNT/boot.ini" ]] || die "BOOT 中没有现有 boot.ini，拒绝把它当作可启动基卡"
[[ -f "$ROOT_MOUNT/etc/os-release" ]] || die "root 中没有 etc/os-release，拒绝把它当作 rootfs"
[[ -f "$PACKAGE_DIR/MANIFEST" && -f "$PACKAGE_DIR/SHA256SUMS" ]] || die "测试包缺少 MANIFEST 或 SHA256SUMS"
[[ -f "$PACKAGE_DIR/boot/boot.ini.test" ]] || die "测试包缺少 boot.ini.test"
[[ -f "$PACKAGE_DIR/boot/Image.mainline-test" ]] || die "测试包缺少 Image.mainline-test"
[[ -f "$PACKAGE_DIR/boot/rk3326-r46h-mainline-test.dtb" ]] || die "测试包缺少 R46H DTB"

valid_payload_path() {
  local path=$1
  local component
  local -a components

  [[ "$path" =~ ^[A-Za-z0-9._+@/-]+$ && "$path" != /* && "$path" != */ && \
     "$path" != *//* ]] || return 1
  IFS='/' read -r -a components <<< "$path"
  for component in "${components[@]}"; do
    [[ -n "$component" && "$component" != "." && "$component" != ".." ]] || return 1
  done
}

verification_parent=/run
[[ -d "$verification_parent" && ! -L "$verification_parent" ]] || die "缺少可信的 root-owned /run 临时目录"
verification_parent_owner=$(stat -c '%u' -- "$verification_parent") || die "无法读取 /run 所有者"
verification_parent_mode=$(stat -c '%a' -- "$verification_parent") || die "无法读取 /run 权限"
[[ "$verification_parent_owner" == "0" && "$verification_parent_mode" =~ ^[0-7]{3,4}$ ]] || \
  die "/run 不是可信的 root-owned 目录"
(( (8#$verification_parent_mode & 8#022) == 0 )) || die "/run 可被非 root 用户写入，拒绝使用"
VERIFY_TMP=$(mktemp -d "$verification_parent/r46h-stage-verify.XXXXXX") || die "无法创建校验临时目录"
verify_tmp_owner=$(stat -c '%u' -- "$VERIFY_TMP") || die "无法读取校验临时目录所有者"
verify_tmp_mode=$(stat -c '%a' -- "$VERIFY_TMP") || die "无法读取校验临时目录权限"
VERIFY_TMP_ID=$(stat -c '%d:%i' -- "$VERIFY_TMP") || die "无法记录校验临时目录身份"
[[ "$verify_tmp_owner" == "0" && "$verify_tmp_mode" == "700" && \
   "$VERIFY_TMP_ID" =~ ^[0-9]+:[0-9]+$ && ! -L "$VERIFY_TMP" ]] || \
  die "校验临时目录不是 root-owned 0700 目录"
expected_table="$VERIFY_TMP/expected.tsv"
expected_paths="$VERIFY_TMP/expected.paths"
actual_paths="$VERIFY_TMP/actual.paths"
sorted_expected_paths="$VERIFY_TMP/expected.sorted"

while IFS= read -r line || [[ -n "$line" ]]; do
  (( ${#line} >= 67 )) || die "SHA256SUMS 含格式错误的短行"
  checksum=${line:0:64}
  separator=${line:64:2}
  payload_path=${line:66}
  [[ "$checksum" =~ ^[0-9A-Fa-f]{64}$ && "$separator" == "  " ]] || \
    die "SHA256SUMS 行格式非法（仅接受 sha256sum 文本格式）"
  valid_payload_path "$payload_path" || die "SHA256SUMS 含非法路径: $payload_path"
  printf '%s\t%s\n' "${checksum,,}" "$payload_path" >> "$expected_table"
  printf '%s\n' "$payload_path" >> "$expected_paths"
done < "$PACKAGE_DIR/SHA256SUMS"
[[ -s "$expected_paths" ]] || die "SHA256SUMS 为空"

LC_ALL=C sort -- "$expected_paths" > "$sorted_expected_paths"
duplicate_path=$(LC_ALL=C uniq -d -- "$sorted_expected_paths" | head -n 1)
[[ -z "$duplicate_path" ]] || die "SHA256SUMS 含重复路径: $duplicate_path"

while IFS= read -r -d '' entry; do
  relative_entry=${entry#"$PACKAGE_DIR"/}
  valid_payload_path "$relative_entry" || die "测试包含非法路径名: $relative_entry"
  if [[ -L "$entry" || ( ! -f "$entry" && ! -d "$entry" ) ]]; then
    die "测试包含符号链接或特殊文件: $relative_entry"
  fi
done < <(find "$PACKAGE_DIR" -mindepth 1 -print0)

find "$PACKAGE_DIR" -type f ! -path "$PACKAGE_DIR/SHA256SUMS" -printf '%P\n' | \
  LC_ALL=C sort > "$actual_paths"
payload_mismatch=$(LC_ALL=C comm -3 -- "$sorted_expected_paths" "$actual_paths" | head -n 1)
[[ -z "$payload_mismatch" ]] || \
  die "SHA256SUMS 与 payload 普通文件集合不一致: ${payload_mismatch//$'\t'/}"

verify_checksums() {
  if command -v sha256sum >/dev/null 2>&1; then
    (cd -- "$PACKAGE_DIR" && sha256sum --quiet --strict -c SHA256SUMS)
  elif command -v shasum >/dev/null 2>&1; then
    (cd -- "$PACKAGE_DIR" && shasum -a 256 -c SHA256SUMS)
  else
    die "需要 sha256sum 或 shasum"
  fi
}
verify_checksums || die "SHA256 校验失败"

kernel_release=$(sed -n 's/^kernel_release=//p' "$PACKAGE_DIR/MANIFEST")
[[ "$kernel_release" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]*$ ]] || die "MANIFEST 中 kernel_release 非法"
[[ -d "$PACKAGE_DIR/rootfs/lib/modules/$kernel_release" ]] || die "测试包 modules 路径与 MANIFEST 不一致"

expected_hash_for() {
  local path=$1
  local expected

  expected=$(awk -F '\t' -v wanted="$path" '$2 == wanted { print $1; exit }' "$expected_table")
  [[ "$expected" =~ ^[0-9a-f]{64}$ ]] || die "SHA256SUMS 未覆盖必需文件: $path"
  printf '%s\n' "$expected"
}

hash_file() {
  local path=$1

  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -- "$path" | awk '{ print $1 }'
  else
    shasum -a 256 -- "$path" | awk '{ print $1 }'
  fi
}

resolve_rootfs_path() {
  local requested=${1#/}
  local resolved=""
  local component
  local candidate
  local link_target
  local link_count=0
  local -a pending
  local -a link_components

  IFS='/' read -r -a pending <<< "$requested"
  while (( ${#pending[@]} > 0 )); do
    component=${pending[0]}
    pending=("${pending[@]:1}")
    case "$component" in
      ""|.) continue ;;
      ..)
        [[ -n "$resolved" ]] || die "rootfs 路径试图越过根目录: $requested"
        if [[ "$resolved" == */* ]]; then
          resolved=${resolved%/*}
        else
          resolved=""
        fi
        continue
        ;;
    esac

    candidate="$ROOT_MOUNT/${resolved:+$resolved/}$component"
    if [[ -L "$candidate" ]]; then
      link_count=$((link_count + 1))
      (( link_count <= 40 )) || die "rootfs 路径符号链接层级过深: $requested"
      link_target=$(readlink -- "$candidate") || die "无法读取 rootfs 符号链接: $candidate"
      [[ -n "$link_target" ]] || die "rootfs 含空符号链接: $candidate"
      if [[ "$link_target" == /* ]]; then
        resolved=""
        link_target=${link_target#/}
      fi
      IFS='/' read -r -a link_components <<< "$link_target"
      pending=("${link_components[@]}" "${pending[@]}")
      continue
    fi
    if [[ -e "$candidate" && ! -d "$candidate" ]]; then
      die "rootfs 目标路径组件不是目录: $candidate"
    fi
    resolved="${resolved:+$resolved/}$component"
  done

  [[ -n "$resolved" ]] || die "rootfs 目标路径解析为空: $requested"
  printf '%s\n' "$resolved"
}

ensure_rootfs_directory() {
  local relative=$1
  local current=$ROOT_MOUNT
  local parent
  local component
  local -a components

  assert_resolved_rootfs_mounts "$relative"
  IFS='/' read -r -a components <<< "$relative"
  for component in "${components[@]}"; do
    parent=$current
    current="$current/$component"
    if [[ -L "$current" ]]; then
      die "rootfs 目标路径在写入前变为符号链接: $current"
    elif [[ -e "$current" ]]; then
      [[ -d "$current" ]] || die "rootfs 目标路径组件不是目录: $current"
    else
      require_mount_identity "root" "$ROOT_MOUNT" "$root_source" "$root_majmin"
      path_mount_identity_is_current "$parent" "$root_source" "$root_majmin" || \
        die "rootfs 目录父路径跨越嵌套挂载: $parent"
      mkdir -- "$current" || die "无法创建 rootfs 目录: $current"
      if [[ ! -d "$current" || -L "$current" ]] || \
         ! path_mount_identity_is_current "$current" "$root_source" "$root_majmin"; then
        die "创建的 rootfs 目录不安全: $current"
      fi
      CREATED_ROOT_DIRS+=("$current")
    fi
  done
}

boot_payload=(
  boot.ini.test
  Image.mainline-test
  rk3326-r46h-mainline-test.dtb
)
if [[ -f "$PACKAGE_DIR/boot/initramfs.mainline-test" ]]; then
  boot_payload+=(initramfs.mainline-test)
fi

for name in "${boot_payload[@]}"; do
  [[ ! -e "$BOOT_MOUNT/$name" && ! -L "$BOOT_MOUNT/$name" ]] || \
    die "BOOT 已有测试文件，拒绝覆盖: $name"
  expected_hash_for "boot/$name" >/dev/null
done

modules_target_relative=$(resolve_rootfs_path /lib/modules)
assert_resolved_rootfs_mounts "$modules_target_relative"
MODULES_DEST_PARENT="$ROOT_MOUNT/$modules_target_relative"
MODULE_DEST="$MODULES_DEST_PARENT/$kernel_release"
[[ "$MODULES_DEST_PARENT" == "$ROOT_MOUNT/"* ]] || die "rootfs modules 目标越界"
[[ ! -e "$MODULE_DEST" && ! -L "$MODULE_DEST" ]] || \
  die "rootfs 已有同版本 modules，拒绝覆盖: $kernel_release"

module_prefix="rootfs/lib/modules/$kernel_release/"
module_relative_paths="$VERIFY_TMP/module-relative.paths"
awk -F '\t' -v prefix="$module_prefix" \
  'index($2, prefix) == 1 { print substr($2, length(prefix) + 1) }' \
  "$expected_table" | LC_ALL=C sort > "$module_relative_paths"
[[ -s "$module_relative_paths" ]] || die "modules 中没有普通文件"

available_kib() {
  local path=$1
  local value

  value=$(LC_ALL=C df -Pk -- "$path" | awk 'END { print $4 }')
  [[ "$value" =~ ^[0-9]+$ ]] || die "无法读取可用空间: $path"
  printf '%s\n' "$value"
}

available_inodes() {
  local path=$1
  local value

  value=$(LC_ALL=C df -Pi -- "$path" | awk 'END { print $4 }')
  [[ "$value" =~ ^[0-9]+$ ]] || die "无法读取可用 inode: $path"
  printf '%s\n' "$value"
}

filesystem_block_bytes() {
  local path=$1
  local value

  value=$(LC_ALL=C stat -f -c '%S' -- "$path")
  [[ "$value" =~ ^[1-9][0-9]*$ ]] || die "无法读取文件系统块大小: $path"
  printf '%s\n' "$value"
}

boot_block_bytes=$(filesystem_block_bytes "$BOOT_MOUNT")
boot_allocated_bytes=0
for name in "${boot_payload[@]}"; do
  file_bytes=$(wc -c < "$PACKAGE_DIR/boot/$name" | tr -d '[:space:]')
  [[ "$file_bytes" =~ ^[0-9]+$ ]] || die "无法读取测试文件大小: $name"
  file_allocated_bytes=$((((file_bytes + boot_block_bytes - 1) / boot_block_bytes) * boot_block_bytes))
  boot_allocated_bytes=$((boot_allocated_bytes + file_allocated_bytes))
done
boot_required_bytes=$((boot_allocated_bytes + BOOT_SAFETY_KIB * 1024))
boot_required_kib=$(((boot_required_bytes + 1023) / 1024))
boot_available_kib=$(available_kib "$BOOT_MOUNT")
(( boot_available_kib >= boot_required_kib )) || \
  die "BOOT 空间不足：需要至少 ${boot_required_kib} KiB（含 ${BOOT_SAFETY_KIB} KiB 余量），可用 ${boot_available_kib} KiB"

module_source="$PACKAGE_DIR/rootfs/lib/modules/$kernel_release"

root_block_bytes=$(filesystem_block_bytes "$ROOT_MOUNT")
module_file_count=0
module_file_allocated_bytes=0
module_directories="$VERIFY_TMP/module-directories"
printf '.\n' > "$module_directories"
while IFS= read -r relative_path; do
  valid_payload_path "$relative_path" || die "modules 路径表在消费前校验失败: $relative_path"
  module_file="$module_source/$relative_path"
  [[ -f "$module_file" && ! -L "$module_file" ]] || die "module 不是普通文件: $relative_path"
  file_bytes=$(wc -c < "$module_file" | tr -d '[:space:]')
  [[ "$file_bytes" =~ ^[0-9]+$ ]] || die "无法读取 module 文件大小"
  file_allocated_bytes=$((((file_bytes + root_block_bytes - 1) / root_block_bytes) * root_block_bytes))
  module_file_allocated_bytes=$((module_file_allocated_bytes + file_allocated_bytes))
  module_file_count=$((module_file_count + 1))
  parent_path=${relative_path%/*}
  if [[ "$parent_path" != "$relative_path" ]]; then
    while [[ "$parent_path" != "." ]]; do
      printf '%s\n' "$parent_path" >> "$module_directories"
      if [[ "$parent_path" == */* ]]; then
        parent_path=${parent_path%/*}
      else
        parent_path="."
      fi
    done
  fi
done < "$module_relative_paths"
(( module_file_count > 0 )) || die "modules 中没有普通文件"

LC_ALL=C sort -u -o "$module_directories" "$module_directories"
module_dir_count=$(wc -l < "$module_directories" | tr -d '[:space:]')
[[ "$module_dir_count" =~ ^[1-9][0-9]*$ ]] || die "无法统计 modules 目录"
module_payload_bytes=$((module_file_allocated_bytes + module_dir_count * root_block_bytes))
root_required_bytes=$((module_payload_bytes + ROOT_SAFETY_KIB * 1024))
root_required_kib=$(((root_required_bytes + 1023) / 1024))
root_available_kib=$(available_kib "$ROOT_MOUNT")
(( root_available_kib >= root_required_kib )) || \
  die "rootfs 空间不足：需要至少 ${root_required_kib} KiB（含 ${ROOT_SAFETY_KIB} KiB 余量），可用 ${root_available_kib} KiB"

module_entries=$((module_file_count + module_dir_count))
root_required_inodes=$((module_entries + ROOT_SAFETY_INODES))
root_available_inodes=$(available_inodes "$ROOT_MOUNT")
(( root_available_inodes >= root_required_inodes )) || \
  die "rootfs inode 不足：需要至少 ${root_required_inodes} 个，可用 ${root_available_inodes} 个"

printf '预检通过：BOOT 需要 %s KiB/可用 %s KiB；rootfs 需要 %s KiB、%s inode/可用 %s KiB、%s inode。\n' \
  "$boot_required_kib" "$boot_available_kib" \
  "$root_required_kib" "$root_required_inodes" \
  "$root_available_kib" "$root_available_inodes"

for name in "${boot_payload[@]}"; do
  require_mount_identity "BOOT" "$BOOT_MOUNT" "$boot_source" "$boot_majmin"
  source_file="$PACKAGE_DIR/boot/$name"
  [[ -f "$source_file" && ! -L "$source_file" ]] || die "BOOT 源文件在复制前发生变化: $name"
  [[ ! -e "$BOOT_MOUNT/$name" && ! -L "$BOOT_MOUNT/$name" ]] || \
    die "BOOT 目标在写入前已存在，拒绝覆盖: $name"
  expected_hash=$(expected_hash_for "boot/$name")
  boot_temp=$(mktemp "$BOOT_MOUNT/.r46h-boot-stage.${name}.XXXXXX") || \
    die "无法创建 BOOT 暂存文件: $name"
  [[ -f "$boot_temp" && ! -L "$boot_temp" ]] || die "BOOT 暂存文件不安全: $boot_temp"
  boot_temp_id=$(stat -c '%d:%i' -- "$boot_temp") || die "无法记录 BOOT 暂存文件身份: $name"
  [[ "$boot_temp_id" =~ ^[0-9]+:[0-9]+$ ]] || die "BOOT 暂存文件身份非法: $name"
  CREATED_BOOT_TEMPS+=("$boot_temp")
  CREATED_BOOT_TEMP_IDS+=("$boot_temp_id")
  CREATED_BOOT_TEMP_HASHES+=("$expected_hash")
  boot_temp_index=$((${#CREATED_BOOT_TEMP_IDS[@]} - 1))
  install -m 0644 -- "$source_file" "$boot_temp" || die "BOOT 写入失败: $name"
  [[ -f "$boot_temp" && ! -L "$boot_temp" ]] || die "BOOT 暂存文件在写入后不安全: $name"
  boot_temp_id=$(stat -c '%d:%i' -- "$boot_temp") || die "无法复验 BOOT 暂存文件身份: $name"
  CREATED_BOOT_TEMP_IDS[boot_temp_index]=$boot_temp_id
  require_mount_identity "BOOT" "$BOOT_MOUNT" "$boot_source" "$boot_majmin"
  path_mount_identity_is_current "$boot_temp" "$boot_source" "$boot_majmin" || \
    die "BOOT 暂存文件跨越了记录的文件系统: $name"
  actual_hash=$(hash_file "$boot_temp") || die "无法校验 BOOT 暂存文件: $name"
  [[ "$actual_hash" == "$expected_hash" ]] || die "BOOT 写入后摘要不匹配: $name"
  require_mount_identity "BOOT" "$BOOT_MOUNT" "$boot_source" "$boot_majmin"
  mv -T --no-clobber -- "$boot_temp" "$BOOT_MOUNT/$name" || die "无法原子发布 BOOT 文件: $name"
  if [[ -e "$boot_temp" || -L "$boot_temp" ]]; then
    if [[ -f "$boot_temp" && ! -L "$boot_temp" ]] && \
       path_mount_identity_is_current "$boot_temp" "$boot_source" "$boot_majmin"; then
      remaining_hash=$(hash_file "$boot_temp" 2>/dev/null || true)
      if [[ "$remaining_hash" == "$expected_hash" ]]; then
        boot_temp_id=$(stat -c '%d:%i' -- "$boot_temp" 2>/dev/null || true)
        if [[ "$boot_temp_id" =~ ^[0-9]+:[0-9]+$ ]]; then
          CREATED_BOOT_TEMP_IDS[boot_temp_index]=$boot_temp_id
        fi
      fi
    fi
    die "BOOT 目标在原子发布时已存在，拒绝覆盖或跟随: $name"
  fi
  [[ -f "$BOOT_MOUNT/$name" && ! -L "$BOOT_MOUNT/$name" ]] || \
    die "原子发布后的 BOOT 目标不安全: $name"
  published_boot_id=$(stat -c '%d:%i' -- "$BOOT_MOUNT/$name") || die "无法记录已发布 BOOT 文件身份: $name"
  [[ "$published_boot_id" =~ ^[0-9]+:[0-9]+$ ]] || die "已发布 BOOT 文件身份非法: $name"
  CREATED_BOOT+=("$name")
  CREATED_BOOT_IDS+=("$published_boot_id")
  actual_hash=$(hash_file "$BOOT_MOUNT/$name") || die "无法校验已发布 BOOT 文件: $name"
  [[ "$actual_hash" == "$expected_hash" ]] || die "BOOT 发布后摘要不匹配: $name"
done

require_mount_identity "root" "$ROOT_MOUNT" "$root_source" "$root_majmin"
resolved_before_write=$(resolve_rootfs_path /lib/modules)
[[ "$resolved_before_write" == "$modules_target_relative" ]] || \
  die "rootfs /lib/modules 在预检后发生变化"
assert_resolved_rootfs_mounts "$resolved_before_write"
ensure_rootfs_directory "$modules_target_relative"
[[ -d "$MODULES_DEST_PARENT" && ! -L "$MODULES_DEST_PARENT" ]] || \
  die "rootfs modules 父目录不安全"
assert_resolved_rootfs_mounts "$modules_target_relative"
MODULE_STAGE_DIR=$(mktemp -d "$MODULES_DEST_PARENT/.r46h-modules-stage.XXXXXX") || \
  die "无法创建 modules 暂存目录"
CREATED_MODULE_STAGE=1
MODULE_STAGE_ID=$(stat -c '%d:%i' -- "$MODULE_STAGE_DIR") || die "无法记录 modules 暂存目录身份"
[[ "$MODULE_STAGE_ID" =~ ^[0-9]+:[0-9]+$ ]] || die "modules 暂存目录身份非法"

while IFS= read -r relative_path; do
  valid_payload_path "$relative_path" || die "modules 路径表在复制前校验失败: $relative_path"
  require_mount_identity "root" "$ROOT_MOUNT" "$root_source" "$root_majmin"
  path_mount_identity_is_current "$MODULE_STAGE_DIR" "$root_source" "$root_majmin" || \
    die "modules 暂存目录不再位于记录的 root 文件系统"
  source_file="$module_source/$relative_path"
  target_file="$MODULE_STAGE_DIR/$relative_path"
  [[ -f "$source_file" && ! -L "$source_file" ]] || die "module 源文件在复制前发生变化: $relative_path"
  mkdir -p -- "${target_file%/*}" || die "无法创建 module 子目录: $relative_path"
  cp -p -- "$source_file" "$target_file" || die "modules 复制失败: $relative_path"
  [[ -f "$target_file" && ! -L "$target_file" ]] || die "module 目标不是普通文件: $relative_path"
  expected_hash=$(expected_hash_for "$module_prefix$relative_path")
  actual_hash=$(hash_file "$target_file") || die "无法校验已写入 module: $relative_path"
  [[ "$actual_hash" == "$expected_hash" ]] || die "modules 写入后摘要不匹配: $relative_path"
done < "$module_relative_paths"

require_mount_identity "root" "$ROOT_MOUNT" "$root_source" "$root_majmin"
path_mount_identity_is_current "$MODULE_STAGE_DIR" "$root_source" "$root_majmin" || \
  die "modules 暂存目录在发布前跨越了文件系统"
chmod 0755 -- "$MODULE_STAGE_DIR" || die "无法设置 modules 顶层目录权限"
chown -R 0:0 -- "$MODULE_STAGE_DIR" || die "无法设置 modules 所有者"
require_mount_identity "root" "$ROOT_MOUNT" "$root_source" "$root_majmin"
path_mount_identity_is_current "$MODULES_DEST_PARENT" "$root_source" "$root_majmin" || \
  die "modules 发布父目录跨越了文件系统"
[[ ! -e "$MODULE_DEST" && ! -L "$MODULE_DEST" ]] || \
  die "modules 目标在发布前已存在，拒绝覆盖"
mv -T --no-clobber -- "$MODULE_STAGE_DIR" "$MODULE_DEST" || die "无法原子安装 modules"
[[ ! -e "$MODULE_STAGE_DIR" && ! -L "$MODULE_STAGE_DIR" ]] || \
  die "modules 目标在原子安装时已存在，拒绝嵌套或覆盖"
[[ -d "$MODULE_DEST" && ! -L "$MODULE_DEST" ]] || die "原子安装后的 modules 目标不安全"
installed_directory_id=$(stat -c '%d:%i' -- "$MODULE_DEST") || die "无法确认已安装 modules 身份"
[[ "$installed_directory_id" == "$MODULE_STAGE_ID" ]] || die "已安装 modules 不是本次暂存目录"
CREATED_MODULES=1
CREATED_MODULE_STAGE=0
sync || die "写入后 sync 失败"

for ((boot_index=0; boot_index<${#boot_payload[@]}; boot_index++)); do
  name=${boot_payload[boot_index]}
  require_mount_identity "BOOT" "$BOOT_MOUNT" "$boot_source" "$boot_majmin"
  path_mount_identity_is_current "$BOOT_MOUNT/$name" "$boot_source" "$boot_majmin" || \
    die "BOOT 最终目标跨越了记录的文件系统: $name"
  final_boot_id=$(stat -c '%d:%i' -- "$BOOT_MOUNT/$name" 2>/dev/null || true)
  [[ "$final_boot_id" == "${CREATED_BOOT_IDS[boot_index]}" ]] || die "BOOT 最终目标已被替换: $name"
  expected_hash=$(expected_hash_for "boot/$name")
  actual_hash=$(hash_file "$BOOT_MOUNT/$name") || die "无法最终校验 BOOT 文件: $name"
  [[ "$actual_hash" == "$expected_hash" ]] || die "BOOT 最终校验失败: $name"
done

installed_module_paths="$VERIFY_TMP/installed-module.paths"
find "$MODULE_DEST" -type f -printf '%P\n' | LC_ALL=C sort > "$installed_module_paths"
module_set_mismatch=$(LC_ALL=C comm -3 -- "$module_relative_paths" "$installed_module_paths" | head -n 1)
[[ -z "$module_set_mismatch" ]] || die "modules 最终文件集合不一致: ${module_set_mismatch//$'\t'/}"
while IFS= read -r relative_path; do
  valid_payload_path "$relative_path" || die "modules 路径表在最终校验前失败: $relative_path"
  require_mount_identity "root" "$ROOT_MOUNT" "$root_source" "$root_majmin"
  path_mount_identity_is_current "$MODULE_DEST" "$root_source" "$root_majmin" || \
    die "modules 最终目标跨越了记录的 root 文件系统"
  target_file="$MODULE_DEST/$relative_path"
  [[ -f "$target_file" && ! -L "$target_file" ]] || die "module 最终目标不是普通文件: $relative_path"
  expected_hash=$(expected_hash_for "$module_prefix$relative_path")
  actual_hash=$(hash_file "$target_file") || die "无法最终校验 module: $relative_path"
  [[ "$actual_hash" == "$expected_hash" ]] || die "modules 最终校验失败: $relative_path"
done < "$module_relative_paths"

SUCCESS=1
printf '旁路安装完成；现有 %s/boot.ini 未修改。\n' "$BOOT_MOUNT"
printf '不要直接拔卡。先卸载两个分区，再按 docs/DEVELOPMENT.md 的串口验收流程启动。\n'
