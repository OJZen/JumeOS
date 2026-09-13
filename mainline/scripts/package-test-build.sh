#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
MAINLINE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
readonly MAINLINE_DIR
REPO_ROOT="$(cd -- "$MAINLINE_DIR/.." && pwd -P)"
readonly REPO_ROOT
readonly DEFAULT_OUTPUT_DIR="$MAINLINE_DIR/out"
readonly DEFAULT_DTB_COMPATIBLE="rockchip,rk3326-r46h-linux"
readonly KERNEL_BASELINE="6.12.99"

IMAGE=""
DTB=""
MODULES_DIR=""
INITRAMFS=""
OUTPUT_DIR="$DEFAULT_OUTPUT_DIR"
BUILD_ID=""
KERNEL_RELEASE=""
ROOT_SPEC="/dev/mmcblk0p2"
CONSOLE_SPEC="ttyS2,115200n8"
DTB_COMPATIBLE="$DEFAULT_DTB_COMPATIBLE"
SOURCE_GIT_COMMIT="unknown"
SOURCE_SNAPSHOT_SHA256="unknown"
PUBLICATION_RECEIPT=""

TMP_DIR=""
TMP_DIR_INODE=""
RECEIPT_TMP=""
RECEIPT_TMP_INODE=""
PUBLISHED_DIR=""
PUBLISHED_DIR_INODE=""
PUBLISHED_TAR=""
PUBLISHED_TAR_INODE=""
OWNED_DIR_PATH=""
OWNED_DIR_INODE=""
OWNED_TAR_PATH=""
OWNED_TAR_INODE=""
OWNED_RECEIPT_PATH=""
OWNED_RECEIPT_INODE=""
SUCCESS=0

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
为 R46H 生成不会覆盖正式启动文件的主线内核测试包。

用法:
  mainline/scripts/package-test-build.sh \
    --image PATH \
    --dtb PATH \
    --modules-dir PATH \
    --build-id ID \
    [--initramfs PATH] \
    [--kernel-release RELEASE] \
    [--root-spec SPEC] \
    [--console SPEC] \
    [--dtb-compatible STRING] \
    [--source-git-commit COMMIT] \
    [--source-snapshot-sha256 SHA256] \
    [--publication-receipt PATH] \
    [--output-dir PATH]

必需参数:
  --image PATH          arm64 未压缩内核 Image
  --dtb PATH            R46H DTB
  --modules-dir PATH    make modules_install 的 INSTALL_MOD_PATH
  --build-id ID         产物标识，只允许字母、数字、点、下划线和连字符

可选参数:
  --initramfs PATH      原始 initramfs；booti 会使用 address:size 形式
  --kernel-release REL  modules-dir 中有多个 release 时必须指定
  --root-spec SPEC      内核 root= 参数，默认 /dev/mmcblk0p2
  --console SPEC        串口 console= 参数，默认 ttyS2,115200n8
  --dtb-compatible STR  期望的板级 compatible
  --source-git-commit C 实际构建快照对应的 40 位 Git commit，或 unknown
  --source-snapshot-sha256 H  实际构建输入归档 SHA256，或 unknown
  --publication-receipt P  把已验证的发布 inode 收据原子写入不存在的 PATH
  --output-dir PATH     默认 mainline/out

输出:
  <output-dir>/r46h-mainline-test-<build-id>/
  <output-dir>/r46h-mainline-test-<build-id>.tar.gz

脚本拒绝空路径、根目录、仓库根目录、错误架构 Image、错误 DTB、空模块树及
已有同名产物。它不会写入任何 TF 卡。
EOF
}

cleanup() {
  local status=$?
  trap - EXIT

  if [[ -n "$TMP_DIR" && -n "$TMP_DIR_INODE" && "$TMP_DIR" == "$OUTPUT_DIR"/.r46h-package.* ]] &&
     recorded_inode_matches "$TMP_DIR" "$TMP_DIR_INODE" dir; then
    rm -rf -- "$TMP_DIR"
  fi
  if [[ -n "$RECEIPT_TMP" && -n "$RECEIPT_TMP_INODE" ]] &&
     recorded_inode_matches "$RECEIPT_TMP" "$RECEIPT_TMP_INODE" file; then
    rm -f -- "$RECEIPT_TMP"
  fi

  if (( SUCCESS == 0 )); then
    if [[ -n "$OWNED_DIR_PATH" && -n "$OWNED_DIR_INODE" &&
          "$OWNED_DIR_PATH" == "$OUTPUT_DIR"/r46h-mainline-test-* ]] &&
       recorded_inode_matches "$OWNED_DIR_PATH" "$OWNED_DIR_INODE" dir; then
      rm -rf -- "$OWNED_DIR_PATH"
    fi
    if [[ -n "$OWNED_TAR_PATH" && -n "$OWNED_TAR_INODE" &&
          "$OWNED_TAR_PATH" == "$OUTPUT_DIR"/r46h-mainline-test-*.tar.gz ]] &&
       recorded_inode_matches "$OWNED_TAR_PATH" "$OWNED_TAR_INODE" file; then
      rm -f -- "$OWNED_TAR_PATH"
    fi
    if [[ -n "$OWNED_RECEIPT_PATH" && -n "$OWNED_RECEIPT_INODE" ]] &&
       recorded_inode_matches "$OWNED_RECEIPT_PATH" "$OWNED_RECEIPT_INODE" file; then
      rm -f -- "$OWNED_RECEIPT_PATH"
    fi
  fi

  # Bash 3.2 can report status 0 to EXIT after an unbound-variable abort.
  # A package is successful only after both final paths have been published.
  if (( SUCCESS == 0 && status == 0 )); then
    status=1
  fi

  exit "$status"
}
trap cleanup EXIT

inode_id() {
  stat -c '%d:%i' -- "$1"
}

recorded_inode_matches() {
  local path=$1
  local expected=$2
  local kind=$3

  [[ ! -L "$path" ]] || return 1
  case "$kind" in
    dir) [[ -d "$path" ]] || return 1 ;;
    file) [[ -f "$path" ]] || return 1 ;;
    *) return 1 ;;
  esac
  [[ "$(inode_id "$path" 2>/dev/null)" == "$expected" ]]
}

publish_no_clobber() {
  local source_path=$1
  local target_path=$2
  local expected_inode=$3
  local kind=$4

  mv -T --no-clobber -- "$source_path" "$target_path" ||
    die "无法无覆盖发布产物: $target_path"
  [[ ! -e "$source_path" && ! -L "$source_path" ]] ||
    die "发布后临时源仍存在: $source_path"
  recorded_inode_matches "$target_path" "$expected_inode" "$kind" ||
    die "发布目标不是本次临时对象: $target_path"
}

require_value() {
  local option=$1
  local value=${2:-}
  [[ -n "$value" ]] || die "$option 需要参数"
}

while (( $# > 0 )); do
  case "$1" in
    --image)
      require_value "$1" "${2:-}"
      IMAGE=$2
      shift 2
      ;;
    --dtb)
      require_value "$1" "${2:-}"
      DTB=$2
      shift 2
      ;;
    --modules-dir)
      require_value "$1" "${2:-}"
      MODULES_DIR=$2
      shift 2
      ;;
    --initramfs)
      require_value "$1" "${2:-}"
      INITRAMFS=$2
      shift 2
      ;;
    --output-dir)
      require_value "$1" "${2:-}"
      OUTPUT_DIR=$2
      shift 2
      ;;
    --build-id)
      require_value "$1" "${2:-}"
      BUILD_ID=$2
      shift 2
      ;;
    --kernel-release)
      require_value "$1" "${2:-}"
      KERNEL_RELEASE=$2
      shift 2
      ;;
    --root-spec)
      require_value "$1" "${2:-}"
      ROOT_SPEC=$2
      shift 2
      ;;
    --console)
      require_value "$1" "${2:-}"
      CONSOLE_SPEC=$2
      shift 2
      ;;
    --dtb-compatible)
      require_value "$1" "${2:-}"
      DTB_COMPATIBLE=$2
      shift 2
      ;;
    --source-git-commit)
      require_value "$1" "${2:-}"
      SOURCE_GIT_COMMIT=$2
      shift 2
      ;;
    --source-snapshot-sha256)
      require_value "$1" "${2:-}"
      SOURCE_SNAPSHOT_SHA256=$2
      shift 2
      ;;
    --publication-receipt)
      require_value "$1" "${2:-}"
      PUBLICATION_RECEIPT=$2
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

[[ -n "$IMAGE" ]] || die "缺少 --image"
[[ -n "$DTB" ]] || die "缺少 --dtb"
[[ -n "$MODULES_DIR" ]] || die "缺少 --modules-dir"
[[ -n "$BUILD_ID" ]] || die "缺少 --build-id"

[[ "$BUILD_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "非法 --build-id: $BUILD_ID"
[[ "$ROOT_SPEC" =~ ^[A-Za-z0-9_./:=+-]+$ ]] || die "非法 --root-spec: $ROOT_SPEC"
[[ "$CONSOLE_SPEC" =~ ^[A-Za-z0-9_,.-]+$ ]] || die "非法 --console: $CONSOLE_SPEC"
[[ "$DTB_COMPATIBLE" =~ ^[A-Za-z0-9,._+-]+$ ]] || die "非法 --dtb-compatible: $DTB_COMPATIBLE"
[[ "$SOURCE_GIT_COMMIT" == unknown || "$SOURCE_GIT_COMMIT" =~ ^[0-9a-f]{40}$ ]] || die "非法 --source-git-commit: $SOURCE_GIT_COMMIT"
[[ "$SOURCE_SNAPSHOT_SHA256" == unknown || "$SOURCE_SNAPSHOT_SHA256" =~ ^[0-9a-f]{64}$ ]] || \
  die "非法 --source-snapshot-sha256: $SOURCE_SNAPSHOT_SHA256"

for tool in fdtget file gzip modinfo mv sha256sum stat strings xz zstd; do
  command -v "$tool" >/dev/null 2>&1 || die "缺少严格产物校验工具: $tool"
done
mv --version 2>/dev/null | grep -Fq 'GNU coreutils' || die "发布产物需要 GNU mv"

canonical_existing_file() {
  local label=$1
  local path=$2
  local parent

  [[ -n "${path//[[:space:]]/}" ]] || die "$label 不能为空"
  [[ "$path" != "/" ]] || die "$label 不能是根目录"
  [[ -f "$path" && ! -L "$path" ]] || die "$label 必须是普通文件且不能是符号链接: $path"
  [[ -r "$path" ]] || die "$label 不可读: $path"
  parent=$(cd -- "$(dirname -- "$path")" && pwd -P)
  printf '%s/%s\n' "$parent" "$(basename -- "$path")"
}

canonical_existing_dir() {
  local label=$1
  local path=$2

  [[ -n "${path//[[:space:]]/}" ]] || die "$label 不能为空"
  [[ "$path" != "/" ]] || die "$label 不能是根目录"
  [[ -d "$path" && ! -L "$path" ]] || die "$label 必须是目录且不能是符号链接: $path"
  (cd -- "$path" && pwd -P)
}

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

IMAGE=$(canonical_existing_file "Image" "$IMAGE")
DTB=$(canonical_existing_file "DTB" "$DTB")
MODULES_DIR=$(canonical_existing_dir "modules-dir" "$MODULES_DIR")
if [[ -n "$INITRAMFS" ]]; then
  INITRAMFS=$(canonical_existing_file "initramfs" "$INITRAMFS")
fi

[[ "$OUTPUT_DIR" != "/" ]] || die "output-dir 不能是根目录"
[[ -n "${OUTPUT_DIR//[[:space:]]/}" ]] || die "output-dir 不能为空"
mkdir -p -- "$OUTPUT_DIR"
OUTPUT_DIR=$(cd -- "$OUTPUT_DIR" && pwd -P)
[[ "$OUTPUT_DIR" != "/" ]] || die "output-dir 不能是根目录"
[[ "$OUTPUT_DIR" != "$REPO_ROOT" ]] || die "output-dir 不能是仓库根目录"
[[ -w "$OUTPUT_DIR" ]] || die "output-dir 不可写: $OUTPUT_DIR"
if [[ -n "$PUBLICATION_RECEIPT" ]]; then
  receipt_basename=$(basename -- "$PUBLICATION_RECEIPT")
  [[ "$receipt_basename" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] ||
    die "publication-receipt 文件名非法: $receipt_basename"
  receipt_parent=$(cd -- "$(dirname -- "$PUBLICATION_RECEIPT")" && pwd -P) ||
    die "publication-receipt 父目录不存在"
  [[ -w "$receipt_parent" ]] || die "publication-receipt 父目录不可写: $receipt_parent"
  PUBLICATION_RECEIPT="$receipt_parent/$receipt_basename"
  [[ ! -e "$PUBLICATION_RECEIPT" && ! -L "$PUBLICATION_RECEIPT" ]] ||
    die "publication-receipt 已存在，拒绝覆盖: $PUBLICATION_RECEIPT"
fi

modules_base="$MODULES_DIR/lib/modules"
[[ -d "$modules_base" && ! -L "$MODULES_DIR/lib" && ! -L "$modules_base" ]] || \
  die "modules-dir 缺少真实目录 lib/modules: $MODULES_DIR"

if [[ -z "$KERNEL_RELEASE" ]]; then
  releases=()
  while IFS= read -r release_dir; do
    releases+=("$release_dir")
  done < <(find "$modules_base" -mindepth 1 -maxdepth 1 -type d -print | LC_ALL=C sort)
  (( ${#releases[@]} == 1 )) || die "lib/modules 下必须恰好有一个 release，或显式指定 --kernel-release"
  KERNEL_RELEASE=$(basename -- "${releases[0]}")
fi
[[ "$KERNEL_RELEASE" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]*$ ]] || die "非法 kernel release: $KERNEL_RELEASE"
[[ "$KERNEL_RELEASE" == "$KERNEL_BASELINE" || "$KERNEL_RELEASE" == "$KERNEL_BASELINE"-* ]] || die "kernel release 必须基于固定版本 $KERNEL_BASELINE，实际为 $KERNEL_RELEASE"
source_module_release_dir="$modules_base/$KERNEL_RELEASE"
[[ -d "$source_module_release_dir" && ! -L "$source_module_release_dir" ]] || \
  die "模块 release 目录不存在或是符号链接: $source_module_release_dir"

package_name="r46h-mainline-test-$BUILD_ID"
package_dir="$OUTPUT_DIR/$package_name"
package_tar="$OUTPUT_DIR/$package_name.tar.gz"
[[ ! -e "$package_dir" ]] || die "产物目录已存在，拒绝覆盖: $package_dir"
[[ ! -L "$package_dir" ]] || die "产物目录路径已有符号链接，拒绝覆盖: $package_dir"
[[ ! -e "$package_tar" ]] || die "产物压缩包已存在，拒绝覆盖: $package_tar"
[[ ! -L "$package_tar" ]] || die "产物压缩包路径已有符号链接，拒绝覆盖: $package_tar"

# Copy every input once, then validate and package only that private snapshot.
# This prevents a standalone caller from changing a previously checked source
# file between validation and archive creation.
TMP_DIR=$(mktemp -d "$OUTPUT_DIR/.r46h-package.XXXXXX")
TMP_DIR_INODE=$(inode_id "$TMP_DIR")
[[ -n "$TMP_DIR_INODE" ]] || die "无法记录打包临时目录 inode"
stage="$TMP_DIR/$package_name"
mkdir -p -- "$stage/boot" "$stage/rootfs/lib/modules"
install -m 0644 -- "$IMAGE" "$stage/boot/Image.mainline-test"
install -m 0644 -- "$DTB" "$stage/boot/rk3326-r46h-mainline-test.dtb"
cp -a -- "$source_module_release_dir" "$stage/rootfs/lib/modules/"
if [[ -n "$INITRAMFS" ]]; then
  install -m 0644 -- "$INITRAMFS" "$stage/boot/initramfs.mainline-test"
fi

IMAGE="$stage/boot/Image.mainline-test"
DTB="$stage/boot/rk3326-r46h-mainline-test.dtb"
module_release_dir="$stage/rootfs/lib/modules/$KERNEL_RELEASE"
if [[ -n "$INITRAMFS" ]]; then
  INITRAMFS="$stage/boot/initramfs.mainline-test"
fi

while IFS= read -r -d '' stage_entry; do
  stage_relative=${stage_entry#"$stage"/}
  valid_payload_path "$stage_relative" || die "staging 含非法路径名: $stage_relative"
  if [[ -L "$stage_entry" || ( ! -d "$stage_entry" && ! -f "$stage_entry" ) ]]; then
    die "staging 含符号链接或特殊文件: $stage_relative"
  fi
done < <(find "$stage" -mindepth 1 -print0)

image_size=$(wc -c < "$IMAGE" | tr -d '[:space:]')
(( image_size >= 8388608 )) || die "Image 小于 8 MiB，疑似错误产物"
image_magic=$(dd if="$IMAGE" bs=1 skip=56 count=4 2>/dev/null | od -An -tx1 | tr -d '[:space:]')
[[ "$image_magic" == "41524d64" ]] || die "Image 不是 arm64 Linux Image（header magic 不匹配）"
image_declared_size=$(od -An -t u8 -j 16 -N 8 "$IMAGE" | tr -d '[:space:]')
[[ "$image_declared_size" =~ ^[0-9]+$ ]] || die "Image header size 非法"
(( image_declared_size >= 8388608 )) || die "Image header size 小于 8 MiB"
(( image_declared_size >= image_size )) || die "Image header size 小于 Image 文件大小"
(( image_declared_size <= image_size + 16777216 )) || die "Image header size 与文件大小不合理"
image_type=$(file -b -- "$IMAGE")
[[ "$image_type" == *"Linux kernel ARM64 boot executable Image"* ]] || \
  die "file 无法确认 arm64 Linux Image: $image_type"

dtb_size=$(wc -c < "$DTB" | tr -d '[:space:]')
(( dtb_size >= 256 )) || die "DTB 小于 256 字节，疑似错误产物"
dtb_magic=$(dd if="$DTB" bs=1 count=4 2>/dev/null | od -An -tx1 | tr -d '[:space:]')
[[ "$dtb_magic" == "d00dfeed" ]] || die "DTB magic 不匹配"
dtb_compatibles=$(fdtget -t s "$DTB" / compatible 2>/dev/null) || die "fdtget 无法读取 DTB compatible"
case " $dtb_compatibles " in
  *" $DTB_COMPATIBLE "*) ;;
  *) die "DTB compatible 不含 $DTB_COMPATIBLE" ;;
esac

[[ -f "$module_release_dir/modules.dep" && ! -L "$module_release_dir/modules.dep" && \
   -s "$module_release_dir/modules.dep" ]] || die "模块树缺少非空普通文件 modules.dep"

module_paths="$TMP_DIR/module-files.paths"
while IFS= read -r module_file; do
  module_relative=${module_file#"$module_release_dir"/}
  valid_payload_path "$module_relative" || die "模块路径非法: $module_relative"
  printf '%s\n' "$module_relative"
done < <(
  find "$module_release_dir" -type f \
    \( -name '*.ko' -o -name '*.ko.gz' -o -name '*.ko.xz' -o -name '*.ko.zst' \) \
    -print | LC_ALL=C sort
) > "$module_paths"
[[ -s "$module_paths" ]] || die "模块树中没有内核模块"

module_count=0
expected_vermagic=""
while IFS= read -r module_relative; do
  module_file="$module_release_dir/$module_relative"
  inspect_module="$module_file"
  case "$module_relative" in
    *.ko) ;;
    *.ko.gz)
      inspect_dir=$(mktemp -d "$TMP_DIR/module-check.XXXXXX")
      inspect_module="$inspect_dir/module.ko"
      gzip -cd -- "$module_file" > "$inspect_module" || die "无法解压模块: $module_relative"
      ;;
    *.ko.xz)
      inspect_dir=$(mktemp -d "$TMP_DIR/module-check.XXXXXX")
      inspect_module="$inspect_dir/module.ko"
      xz -cd -- "$module_file" > "$inspect_module" || die "无法解压模块: $module_relative"
      ;;
    *.ko.zst)
      inspect_dir=$(mktemp -d "$TMP_DIR/module-check.XXXXXX")
      inspect_module="$inspect_dir/module.ko"
      zstd -q -d -c -- "$module_file" > "$inspect_module" || die "无法解压模块: $module_relative"
      ;;
    *) die "无法识别模块压缩格式: $module_relative" ;;
  esac
  [[ -s "$inspect_module" && -f "$inspect_module" && ! -L "$inspect_module" ]] || \
    die "解压后的模块不是非空普通文件: $module_relative"
  module_type=$(file -b -- "$inspect_module")
  [[ "$module_type" == *"ELF 64-bit LSB relocatable, ARM aarch64"* ]] || \
    die "不是 arm64 ELF 内核模块: $module_relative ($module_type)"
  module_vermagic=$(modinfo -F vermagic "$inspect_module" 2>/dev/null) || \
    die "modinfo 无法读取模块: $module_relative"
  [[ -n "$module_vermagic" && "$module_vermagic" != *$'\n'* ]] || \
    die "模块 vermagic 不是唯一非空值: $module_relative"
  [[ "${module_vermagic%% *}" == "$KERNEL_RELEASE" ]] || \
    die "模块 vermagic 与 kernel release 不一致: $module_relative"
  if [[ -z "$expected_vermagic" ]]; then
    expected_vermagic=$module_vermagic
  else
    [[ "$module_vermagic" == "$expected_vermagic" ]] || \
      die "模块完整 vermagic 不一致: $module_relative"
  fi
  (( module_count += 1 ))
done < "$module_paths"

dep_paths="$TMP_DIR/modules.dep.paths"
: > "$dep_paths"
while IFS= read -r dep_line || [[ -n "$dep_line" ]]; do
  [[ "$dep_line" == *:* ]] || die "modules.dep 条目缺少冒号: $dep_line"
  dep_module=${dep_line%%:*}
  dep_dependencies=${dep_line#*:}
  [[ -n "$dep_module" ]] || die "modules.dep 含空模块路径"
  valid_payload_path "$dep_module" || die "modules.dep 含非法模块路径: $dep_module"
  printf '%s\n' "$dep_module" >> "$dep_paths"
  dep_dependency_list=()
  read -r -a dep_dependency_list <<< "$dep_dependencies"
  for dep_dependency in "${dep_dependency_list[@]}"; do
    valid_payload_path "$dep_dependency" || die "modules.dep 含非法依赖路径: $dep_dependency"
    grep -Fxq -- "$dep_dependency" "$module_paths" || \
      die "modules.dep 依赖不属于模块集合: $dep_dependency"
  done
done < "$module_release_dir/modules.dep"
LC_ALL=C sort "$dep_paths" -o "$dep_paths"
cmp -s -- "$module_paths" "$dep_paths" ||
  die "modules.dep 左侧集合与实际模块路径不完全一致"

image_strings="$TMP_DIR/Image.strings"
strings -a "$IMAGE" > "$image_strings"
grep -Fq -- "Linux version $KERNEL_RELEASE " "$image_strings" ||
  die "Image 内核版本 banner 与 modules release 不一致: $KERNEL_RELEASE"
grep -Fqx -- "$expected_vermagic" "$image_strings" ||
  die "Image 不含模块完整 vermagic: $expected_vermagic"

if [[ -n "$INITRAMFS" ]]; then
  [[ -s "$INITRAMFS" ]] || die "initramfs 为空"
fi

initramfs_mode="absent"
boot_initramfs_lines="booti \${loadaddr} - \${dtb_loadaddr}"
if [[ -n "$INITRAMFS" ]]; then
  initramfs_mode="raw-address-size"
  boot_initramfs_lines="load mmc 1:1 \${initrd_loadaddr} initramfs.mainline-test
setenv initrd_size \${filesize}
load mmc 1:1 \${dtb_loadaddr} rk3326-r46h-mainline-test.dtb
booti \${loadaddr} \${initrd_loadaddr}:\${initrd_size} \${dtb_loadaddr}"
fi

{
  printf '%s\n' \
    'odroidgoa-uboot-config' \
    '' \
    '# R46H mainline bring-up only. Keep this file as boot.ini.test while staging.' \
    '# No quiet/splash: the first boot must remain observable over 3.3 V UART.' \
    "setenv bootargs \"root=$ROOT_SPEC rootwait rw fsck.repair=yes net.ifnames=0 console=$CONSOLE_SPEC earlycon loglevel=7 ignore_loglevel plymouth.enable=0 clk_ignore_unused pd_ignore_unused\"" \
    '' \
    'setenv loadaddr "0x02000000"' \
    'setenv initrd_loadaddr "0x0a000000"' \
    'setenv dtb_loadaddr "0x01f00000"' \
    '' \
    "load mmc 1:1 \${loadaddr} Image.mainline-test"
  if [[ -n "$INITRAMFS" ]]; then
    printf '%s\n' "$boot_initramfs_lines"
  else
    printf '%s\n' \
      "load mmc 1:1 \${dtb_loadaddr} rk3326-r46h-mainline-test.dtb" \
      "$boot_initramfs_lines"
  fi
} > "$stage/boot/boot.ini.test"

archive_epoch=${SOURCE_DATE_EPOCH:-$(date +%s)}
[[ "$archive_epoch" =~ ^[0-9]+$ ]] || die "SOURCE_DATE_EPOCH 必须是非负整数"
if created_utc=$(date -u -d "@$archive_epoch" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null); then
  :
elif created_utc=$(date -u -r "$archive_epoch" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null); then
  :
else
  die "无法把 SOURCE_DATE_EPOCH 转换为 UTC 时间"
fi

module_tree_manifest="$TMP_DIR/MODULES-SHA256SUMS"
(
  cd -- "$stage"
  find "rootfs/lib/modules/$KERNEL_RELEASE" -type f -print | LC_ALL=C sort |
    while IFS= read -r module_payload; do
      sha256sum -- "$module_payload"
    done
) > "$module_tree_manifest"
module_tree_sha256=$(sha256sum "$module_tree_manifest" | awk '{print $1}')
[[ "$module_tree_sha256" =~ ^[0-9a-f]{64}$ ]] || die "无法计算模块树摘要"

cat > "$stage/MANIFEST" <<EOF
format_version=2
target=r46h
soc=rk3326
purpose=mainline-bring-up-test-only
build_id=$BUILD_ID
kernel_release=$KERNEL_RELEASE
kernel_baseline=$KERNEL_BASELINE
dtb_compatible=$DTB_COMPATIBLE
root_spec=$ROOT_SPEC
console=$CONSOLE_SPEC
initramfs=$initramfs_mode
module_count=$module_count
module_tree_sha256=$module_tree_sha256
source_git_commit=$SOURCE_GIT_COMMIT
source_snapshot_sha256=$SOURCE_SNAPSHOT_SHA256
created_utc=$created_utc
image_file=boot/Image.mainline-test
dtb_file=boot/rk3326-r46h-mainline-test.dtb
boot_script=boot/boot.ini.test
modules_path=rootfs/lib/modules/$KERNEL_RELEASE
EOF

sha256_file() {
  local path=$1
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum -- "$path"
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 -- "$path"
  else
    die "需要 sha256sum 或 shasum"
  fi
}

(
  cd -- "$stage"
  find . -mindepth 1 -type f ! -path './SHA256SUMS' -print |
    sed 's#^\./##' | LC_ALL=C sort | while IFS= read -r payload; do
    sha256_file "$payload"
  done
) > "$stage/SHA256SUMS"

expected_checksum_count=$(find "$stage" -type f ! -path "$stage/SHA256SUMS" | wc -l | tr -d '[:space:]')
actual_checksum_count=$(wc -l < "$stage/SHA256SUMS" | tr -d '[:space:]')
[[ "$actual_checksum_count" == "$expected_checksum_count" ]] || die "SHA256SUMS 未绑定精确文件集"
(cd -- "$stage" && sha256sum --strict -c SHA256SUMS >/dev/null) || die "staging SHA256 自校验失败"

archive_tar_tmp="$TMP_DIR/$package_name.tar"
if tar --help 2>&1 | grep -- '--sort' >/dev/null; then
  tar \
    --sort=name \
    --mtime="@$archive_epoch" \
    --owner=0 --group=0 --numeric-owner \
    --format=gnu \
    -cf "$archive_tar_tmp" -C "$TMP_DIR" "$package_name"
else
  # bsdtar lacks GNU's deterministic metadata switches. Avoid AppleDouble
  # entries; the canonical builder always takes the GNU tar branch above.
  COPYFILE_DISABLE=1 tar -cf "$archive_tar_tmp" -C "$TMP_DIR" "$package_name"
fi
gzip -n -9 -- "$archive_tar_tmp"
[[ -s "$TMP_DIR/$package_name.tar.gz" ]] || die "测试包归档生成失败"

archive_tmp="$TMP_DIR/$package_name.tar.gz"
archive_tmp_inode=$(inode_id "$archive_tmp")
stage_inode=$(inode_id "$stage")
[[ -n "$archive_tmp_inode" && -n "$stage_inode" ]] || die "无法记录待发布产物 inode"

OWNED_TAR_PATH="$package_tar"
OWNED_TAR_INODE="$archive_tmp_inode"
publish_no_clobber "$archive_tmp" "$package_tar" "$archive_tmp_inode" file
PUBLISHED_TAR="$package_tar"
PUBLISHED_TAR_INODE="$archive_tmp_inode"
OWNED_DIR_PATH="$package_dir"
OWNED_DIR_INODE="$stage_inode"
publish_no_clobber "$stage" "$package_dir" "$stage_inode" dir
PUBLISHED_DIR="$package_dir"
PUBLISHED_DIR_INODE="$stage_inode"

if [[ -n "$PUBLICATION_RECEIPT" ]]; then
  RECEIPT_TMP=$(mktemp "$receipt_parent/.r46h-publication-receipt.XXXXXX")
  RECEIPT_TMP_INODE=$(inode_id "$RECEIPT_TMP")
  [[ -n "$RECEIPT_TMP_INODE" ]] || die "无法记录发布收据临时 inode"
  {
    printf 'format_version=1\n'
    printf 'package_dir_inode=%s\n' "$PUBLISHED_DIR_INODE"
    printf 'package_tar_inode=%s\n' "$PUBLISHED_TAR_INODE"
  } > "$RECEIPT_TMP"
  chmod 0600 -- "$RECEIPT_TMP"
  OWNED_RECEIPT_PATH="$PUBLICATION_RECEIPT"
  OWNED_RECEIPT_INODE="$RECEIPT_TMP_INODE"
  publish_no_clobber "$RECEIPT_TMP" "$PUBLICATION_RECEIPT" "$RECEIPT_TMP_INODE" file
fi

SUCCESS=1
printf 'staging: %s\n' "$PUBLISHED_DIR"
printf 'archive: %s\n' "$PUBLISHED_TAR"
printf 'kernel release: %s\n' "$KERNEL_RELEASE"
printf 'next: verify SHA256SUMS, then use stage-test-to-sd.sh on a spare TF card\n'
