#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

readonly MAINLINE_DIR=/work/input/mainline
readonly WORK_ROOT=/work
readonly CACHE_DIR=/cache
readonly OUTPUT_ROOT=/output
readonly SOURCE_ARCHIVE=/work/mainline-source.tar
readonly PRIVATE_TARBALL=/work/kernel-source.tar.xz

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

require_env() {
  local name=$1
  [[ -n "${!name:-}" ]] || die "缺少环境变量 $name"
}

manifest_value() {
  local name=$1
  local count
  local value

  count=$(grep -c "^${name}=" "$MAINLINE_DIR/manifest.env" || true)
  [[ "$count" == 1 ]] || die "源码快照 manifest 中 $name 必须恰好出现一次"
  value=$(sed -n "s/^${name}=//p" "$MAINLINE_DIR/manifest.env")
  [[ -n "$value" && "$value" != *$'\n'* ]] || die "源码快照 manifest 中 $name 不能为空"
  printf '%s\n' "$value"
}

receipt_value() {
  local receipt_path=$1
  local name=$2
  local count
  local value

  count=$(grep -c "^${name}=" "$receipt_path" || true)
  [[ "$count" == 1 ]] || return 1
  value=$(sed -n "s/^${name}=//p" "$receipt_path")
  [[ -n "$value" && "$value" != *$'\n'* ]] || return 1
  printf '%s\n' "$value"
}

for name in \
  BUILD_ID BUILDER_IMAGE BUILDER_IMAGE_ID DOCKER_CLIENT_VERSION DOCKER_CONTEXT \
  DOCKER_SERVER_VERSION HOST_GID HOST_UID JOBS \
  KERNEL_LOCALVERSION KERNEL_PATCH_LAST KERNEL_MIRROR_URL KERNEL_SHA256 KERNEL_TARBALL KERNEL_URL \
  KERNEL_VERSION ROOT_SPEC SOURCE_GIT_COMMIT SOURCE_GIT_DIRTY SOURCE_SNAPSHOT_SHA256; do
  require_env "$name"
done

snapshot_kernel_version=$(manifest_value KERNEL_VERSION)
snapshot_kernel_tarball=$(manifest_value KERNEL_TARBALL)
snapshot_kernel_url=$(manifest_value KERNEL_URL)
snapshot_kernel_mirror_url=$(manifest_value KERNEL_MIRROR_URL)
snapshot_kernel_sha256=$(manifest_value KERNEL_SHA256)
snapshot_kernel_localversion=$(manifest_value KERNEL_LOCALVERSION)
snapshot_kernel_patch_last=$(manifest_value KERNEL_PATCH_LAST)
snapshot_builder_image=$(manifest_value BUILDER_IMAGE)
manifest_value BUILD_VOLUME_PREFIX >/dev/null

[[ "$KERNEL_VERSION" == "$snapshot_kernel_version" ]] || die "KERNEL_VERSION 与源码快照 manifest 不一致"
[[ "$KERNEL_TARBALL" == "$snapshot_kernel_tarball" ]] || die "KERNEL_TARBALL 与源码快照 manifest 不一致"
[[ "$KERNEL_URL" == "$snapshot_kernel_url" ]] || die "KERNEL_URL 与源码快照 manifest 不一致"
[[ "$KERNEL_MIRROR_URL" == "$snapshot_kernel_mirror_url" ]] || die "KERNEL_MIRROR_URL 与源码快照 manifest 不一致"
[[ "$KERNEL_SHA256" == "$snapshot_kernel_sha256" ]] || die "KERNEL_SHA256 与源码快照 manifest 不一致"
[[ "$KERNEL_LOCALVERSION" == "$snapshot_kernel_localversion" ]] || die "KERNEL_LOCALVERSION 与源码快照 manifest 不一致"
[[ "$KERNEL_PATCH_LAST" == "$snapshot_kernel_patch_last" ]] || die "KERNEL_PATCH_LAST 与源码快照 manifest 不一致"
[[ "$BUILDER_IMAGE" == "$snapshot_builder_image" ]] || die "BUILDER_IMAGE 与源码快照 manifest 不一致"
unset snapshot_kernel_version snapshot_kernel_tarball snapshot_kernel_url snapshot_kernel_mirror_url \
  snapshot_kernel_sha256 snapshot_kernel_localversion snapshot_kernel_patch_last snapshot_builder_image

# shellcheck disable=SC2153
[[ "$BUILD_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "非法 BUILD_ID"
[[ "$HOST_UID" =~ ^[0-9]+$ && "$HOST_GID" =~ ^[0-9]+$ ]] || die "非法宿主 UID/GID"
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || die "非法 JOBS"
[[ "$KERNEL_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "非法 KERNEL_VERSION"
[[ "$KERNEL_TARBALL" == "linux-$KERNEL_VERSION.tar.xz" ]] || die "内核压缩包名称与版本不一致"
[[ "$KERNEL_URL" == */"$KERNEL_TARBALL" ]] || die "官方内核 URL 与压缩包名称不一致"
[[ "$KERNEL_MIRROR_URL" == */"$KERNEL_TARBALL" ]] || die "镜像 URL 与压缩包名称不一致"
[[ "$KERNEL_SHA256" =~ ^[0-9a-f]{64}$ ]] || die "非法 KERNEL_SHA256"
[[ "$KERNEL_LOCALVERSION" =~ ^-[A-Za-z0-9._-]+$ ]] || die "非法 KERNEL_LOCALVERSION"
[[ "$KERNEL_PATCH_LAST" =~ ^[0-9]{4}$ && "$KERNEL_PATCH_LAST" != 0000 ]] || \
  die "非法 KERNEL_PATCH_LAST"
[[ "$KERNEL_LOCALVERSION" == "-r46h-mainline-$BUILD_ID" ]] || \
  die "BUILD_ID 与 KERNEL_LOCALVERSION 不一致: $BUILD_ID / $KERNEL_LOCALVERSION"
[[ "$ROOT_SPEC" =~ ^[A-Za-z0-9_./:=+-]+$ ]] || die "非法 ROOT_SPEC"
[[ "$BUILDER_IMAGE_ID" =~ ^sha256:[0-9a-f]{64}$ ]] || die "非法 BUILDER_IMAGE_ID"
[[ "$DOCKER_CONTEXT" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || die "非法 DOCKER_CONTEXT"
[[ "$DOCKER_CLIENT_VERSION" =~ ^[0-9][A-Za-z0-9.+_-]{0,63}$ ]] || \
  die "非法 DOCKER_CLIENT_VERSION"
[[ "$DOCKER_SERVER_VERSION" =~ ^[0-9][A-Za-z0-9.+_-]{0,63}$ ]] || \
  die "非法 DOCKER_SERVER_VERSION"
[[ "$SOURCE_GIT_COMMIT" =~ ^[0-9a-f]{40}$ ]] || die "非法 SOURCE_GIT_COMMIT"
[[ "$SOURCE_GIT_DIRTY" == false ]] || die "构建输入必须来自 clean Git 快照"
[[ "$SOURCE_SNAPSHOT_SHA256" =~ ^[0-9a-f]{64}$ ]] || die "非法 SOURCE_SNAPSHOT_SHA256"
[[ -f "$SOURCE_ARCHIVE" ]] || die "缺少只读源码快照"
printf '%s  %s\n' "$SOURCE_SNAPSHOT_SHA256" "$SOURCE_ARCHIVE" | sha256sum -c - >/dev/null || \
  die "源码快照 SHA256 校验失败"
archive_git_commit=$(git get-tar-commit-id < "$SOURCE_ARCHIVE") || die "无法读取源码快照 Git commit"
[[ "$archive_git_commit" == "$SOURCE_GIT_COMMIT" ]] || die "源码快照 Git commit 与传入来源提交不一致"
[[ -x "$MAINLINE_DIR/scripts/build-in-container.sh" ]] || die "源码快照解压不完整"

bash -n "$MAINLINE_DIR"/config/*.sh "$MAINLINE_DIR"/scripts/*.sh "$MAINLINE_DIR"/tests/*.sh
shellcheck "$MAINLINE_DIR"/config/*.sh "$MAINLINE_DIR"/scripts/*.sh "$MAINLINE_DIR"/tests/*.sh

readonly SOURCE_PARENT="$WORK_ROOT/source"
readonly SOURCE_DIR="$SOURCE_PARENT/linux-$KERNEL_VERSION"
readonly BUILD_DIR="$WORK_ROOT/build-$KERNEL_VERSION"
readonly MODULE_STAGE="$WORK_ROOT/modules-$KERNEL_VERSION"
readonly TARBALL_PATH="$CACHE_DIR/$KERNEL_TARBALL"
readonly BUILD_META_NAME="r46h-mainline-build-$BUILD_ID"
readonly BUILD_META_DIR="$OUTPUT_ROOT/$BUILD_META_NAME"
readonly PACKAGE_DIR="$OUTPUT_ROOT/r46h-mainline-test-$BUILD_ID"
readonly PACKAGE_TAR="$PACKAGE_DIR.tar.gz"
BUILD_META_TMP=""
BUILD_META_TMP_INODE=""
BUILD_META_DIR_INODE=""
PACKAGE_DIR_INODE=""
PACKAGE_TAR_INODE=""
PACKAGE_RECEIPT_DIR=""
PACKAGE_RECEIPT_DIR_INODE=""
PACKAGE_RECEIPT=""
download_tmp=""
published_package=0
download_url_used=cache

[[ ! -e "$BUILD_META_DIR" && ! -L "$BUILD_META_DIR" ]] || die "构建元数据产物已存在: $BUILD_META_NAME"
[[ ! -e "$PACKAGE_DIR" && ! -L "$PACKAGE_DIR" && ! -e "$PACKAGE_TAR" && ! -L "$PACKAGE_TAR" ]] ||
  die "测试包产物已存在: $BUILD_ID"

mv --version 2>/dev/null | grep -Fq 'GNU coreutils' || die "发布产物需要 GNU mv"

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

remove_recorded() {
  local path=$1
  local expected=$2
  local kind=$3

  recorded_inode_matches "$path" "$expected" "$kind" || return 0
  case "$kind" in
    dir) rm -rf -- "$path" ;;
    file) rm -f -- "$path" ;;
  esac
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

chown_recorded() {
  local path=$1
  local expected=$2
  local kind=$3

  recorded_inode_matches "$path" "$expected" "$kind" || return 1
  if [[ "$kind" == dir ]]; then
    chown -R "$HOST_UID:$HOST_GID" -- "$path"
  else
    chown "$HOST_UID:$HOST_GID" -- "$path"
  fi
}

cleanup() {
  local status=$?
  local receipt_dir_inode=""
  local receipt_tar_inode=""
  trap - EXIT
  if (( status != 0 )) && [[ -n "$BUILD_META_TMP" && -n "$BUILD_META_TMP_INODE" ]]; then
    remove_recorded "$BUILD_META_TMP" "$BUILD_META_TMP_INODE" dir
  fi
  if (( status != 0 )) &&
     [[ -n "$BUILD_META_DIR_INODE" && "$BUILD_META_DIR" == "$OUTPUT_ROOT"/r46h-mainline-build-* ]]; then
    remove_recorded "$BUILD_META_DIR" "$BUILD_META_DIR_INODE" dir
  fi
  if (( status != 0 && published_package == 1 )); then
    if [[ -n "$PACKAGE_DIR_INODE" && "$PACKAGE_DIR" == "$OUTPUT_ROOT"/r46h-mainline-test-* ]]; then
      remove_recorded "$PACKAGE_DIR" "$PACKAGE_DIR_INODE" dir
    fi
    if [[ -n "$PACKAGE_TAR_INODE" && "$PACKAGE_TAR" == "$OUTPUT_ROOT"/r46h-mainline-test-*.tar.gz ]]; then
      remove_recorded "$PACKAGE_TAR" "$PACKAGE_TAR_INODE" file
    fi
  fi
  if (( status != 0 && published_package == 0 )) &&
     [[ -n "$PACKAGE_RECEIPT_DIR" && -n "$PACKAGE_RECEIPT_DIR_INODE" && -n "$PACKAGE_RECEIPT" ]] &&
     recorded_inode_matches "$PACKAGE_RECEIPT_DIR" "$PACKAGE_RECEIPT_DIR_INODE" dir &&
     [[ -f "$PACKAGE_RECEIPT" && ! -L "$PACKAGE_RECEIPT" ]]; then
    receipt_dir_inode=$(receipt_value "$PACKAGE_RECEIPT" package_dir_inode 2>/dev/null || true)
    receipt_tar_inode=$(receipt_value "$PACKAGE_RECEIPT" package_tar_inode 2>/dev/null || true)
    if [[ "$receipt_dir_inode" =~ ^[0-9]+:[0-9]+$ ]]; then
      remove_recorded "$PACKAGE_DIR" "$receipt_dir_inode" dir
    fi
    if [[ "$receipt_tar_inode" =~ ^[0-9]+:[0-9]+$ ]]; then
      remove_recorded "$PACKAGE_TAR" "$receipt_tar_inode" file
    fi
  fi
  if [[ -n "$download_tmp" && -f "$download_tmp" && "$download_tmp" == "$CACHE_DIR"/*.download ]]; then
    rm -f -- "$download_tmp"
  fi
  exit "$status"
}
trap cleanup EXIT

mkdir -p -- "$CACHE_DIR" "$SOURCE_PARENT"
BUILD_META_TMP=$(mktemp -d "$OUTPUT_ROOT/.$BUILD_META_NAME.tmp.XXXXXX")
BUILD_META_TMP_INODE=$(inode_id "$BUILD_META_TMP")
[[ -n "$BUILD_META_TMP_INODE" ]] || die "无法记录构建元数据临时目录 inode"
PACKAGE_RECEIPT_DIR=$(mktemp -d "$WORK_ROOT/package-receipt.XXXXXX")
PACKAGE_RECEIPT_DIR_INODE=$(inode_id "$PACKAGE_RECEIPT_DIR")
[[ -n "$PACKAGE_RECEIPT_DIR_INODE" ]] || die "无法记录私有发布收据目录 inode"
chmod 0700 -- "$PACKAGE_RECEIPT_DIR"
PACKAGE_RECEIPT="$PACKAGE_RECEIPT_DIR/receipt"

verify_tarball() {
  printf '%s  %s\n' "$KERNEL_SHA256" "$TARBALL_PATH" | sha256sum -c - >/dev/null 2>&1
}

if [[ ! -f "$TARBALL_PATH" ]] || ! verify_tarball; then
  download_tmp="$TARBALL_PATH.download"
  rm -f -- "$download_tmp"
  download_url_used=$KERNEL_MIRROR_URL
  if ! curl --fail --location --retry 3 --retry-all-errors \
       --output "$download_tmp" "$KERNEL_MIRROR_URL"; then
    rm -f -- "$download_tmp"
    download_url_used=$KERNEL_URL
    curl --fail --location --retry 3 --retry-all-errors \
      --output "$download_tmp" "$KERNEL_URL"
  fi
  printf '%s  %s\n' "$KERNEL_SHA256" "$download_tmp" | sha256sum -c -
  mv -- "$download_tmp" "$TARBALL_PATH"
fi
verify_tarball || die "内核压缩包 SHA256 校验失败"

# The host cache is a writable bind mount. Copy it once into the private build
# volume, verify that private inode, and extract only that copy so a host-side
# path replacement cannot change the bytes after verification.
rm -f -- "$PRIVATE_TARBALL"
cp -- "$TARBALL_PATH" "$PRIVATE_TARBALL"
chmod 0400 -- "$PRIVATE_TARBALL"
printf '%s  %s\n' "$KERNEL_SHA256" "$PRIVATE_TARBALL" | sha256sum -c - >/dev/null ||
  die "私有内核压缩包 SHA256 校验失败"

# Source/build paths are exact, version-derived locations in a dedicated Docker volume.
rm -rf -- "$SOURCE_DIR" "$BUILD_DIR" "$MODULE_STAGE"
tar -xJf "$PRIVATE_TARBALL" -C "$SOURCE_PARENT"
[[ -f "$SOURCE_DIR/Makefile" ]] || die "内核源码解压失败"

shopt -s nullglob
patches=("$MAINLINE_DIR"/patches/*.patch)
(( ${#patches[@]} > 0 )) || die "没有找到 R46H 内核补丁"
expected_patch=1
selected_patch_last=""
for patch_file in "${patches[@]}"; do
  patch_name=$(basename -- "$patch_file")
  [[ "$patch_name" =~ ^([0-9]{4})-[A-Za-z0-9][A-Za-z0-9._-]*\.patch$ ]] || \
    die "内核补丁名称非法: $patch_name"
  patch_number=${BASH_REMATCH[1]}
  expected_patch_number=$(printf '%04d' "$expected_patch")
  [[ "$patch_number" == "$expected_patch_number" ]] || \
    die "内核补丁序列不连续: $patch_name（期望 $expected_patch_number）"
  expected_patch=$((expected_patch + 1))
  [[ "$patch_number" > "$KERNEL_PATCH_LAST" ]] && continue
  printf 'Applying %s\n' "$(basename -- "$patch_file")"
  patch --directory "$SOURCE_DIR" --strip=1 --forward < "$patch_file"
  selected_patch_last=$patch_number
done
[[ "$selected_patch_last" == "$KERNEL_PATCH_LAST" ]] || \
  die "没有应用 manifest 指定的末尾补丁: $KERNEL_PATCH_LAST"
cmp -s \
  "$SOURCE_DIR/arch/arm64/boot/dts/rockchip/rk3326-r46h.dts" \
  "$MAINLINE_DIR/board/r46h/rk3326-r46h.dts" || die "补丁中的 R46H DTS 与可审查源码不一致"
cmp -s \
  "$SOURCE_DIR/drivers/gpu/drm/panel/panel-r46h.c" \
  "$MAINLINE_DIR/board/r46h/panel-r46h.c" || die "补丁中的 R46H panel 源码与可审查源码不一致"

make -C "$SOURCE_DIR" O="$BUILD_DIR" ARCH=arm64 defconfig
"$SOURCE_DIR/scripts/kconfig/merge_config.sh" \
  -m -O "$BUILD_DIR" \
  "$BUILD_DIR/.config" \
  "$MAINLINE_DIR/config/r46h.fragment"
make -C "$SOURCE_DIR" O="$BUILD_DIR" ARCH=arm64 olddefconfig
"$MAINLINE_DIR/config/validate-config.sh" "$BUILD_DIR/.config"
make -C "$SOURCE_DIR" O="$BUILD_DIR" ARCH=arm64 syncconfig

kernel_release=$(make -s -C "$SOURCE_DIR" O="$BUILD_DIR" ARCH=arm64 kernelrelease)
expected_release="$KERNEL_VERSION$KERNEL_LOCALVERSION"
[[ "$kernel_release" == "$expected_release" ]] || die "kernel release 不一致: $kernel_release（期望 $expected_release）"

make -C "$SOURCE_DIR" O="$BUILD_DIR" ARCH=arm64 -j"$JOBS" Image dtbs modules
make -C "$SOURCE_DIR" O="$BUILD_DIR" ARCH=arm64 \
  modules_install INSTALL_MOD_PATH="$MODULE_STAGE" INSTALL_MOD_STRIP=1
depmod -b "$MODULE_STAGE" "$kernel_release"

# modules_install normally leaves host-only build/source symlinks. They are not
# runtime payload and the strict packager rejects every link and special file.
rm -f -- \
  "$MODULE_STAGE/lib/modules/$kernel_release/build" \
  "$MODULE_STAGE/lib/modules/$kernel_release/source"

image="$BUILD_DIR/arch/arm64/boot/Image"
dtb="$BUILD_DIR/arch/arm64/boot/dts/rockchip/rk3326-r46h.dtb"
[[ -s "$image" && -s "$dtb" ]] || die "Image 或 R46H DTB 未生成"
[[ "$(dd if="$image" bs=1 skip=56 count=4 2>/dev/null)" == ARMd ]] || die "Image arm64 magic 错误"
fdtget -t s "$dtb" / compatible | tr ' ' '\n' | grep -Fxq 'rockchip,rk3326-r46h-linux' || die "DTB compatible 错误"

install -m 0644 -- "$image" "$BUILD_META_TMP/Image"
install -m 0644 -- "$dtb" "$BUILD_META_TMP/rk3326-r46h.dtb"
install -m 0644 -- "$BUILD_DIR/.config" "$BUILD_META_TMP/config-$kernel_release"
install -m 0644 -- "$BUILD_DIR/System.map" "$BUILD_META_TMP/System.map-$kernel_release"
install -m 0644 -- "$BUILD_DIR/Module.symvers" "$BUILD_META_TMP/Module.symvers-$kernel_release"

(
  cd -- "$WORK_ROOT/input"
  find mainline -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum
) > "$BUILD_META_TMP/SOURCE-SHA256SUMS"
source_file_manifest_sha256=$(sha256sum "$BUILD_META_TMP/SOURCE-SHA256SUMS" | awk '{print $1}')

"$MAINLINE_DIR/scripts/package-test-build.sh" \
  --image "$image" \
  --dtb "$dtb" \
  --modules-dir "$MODULE_STAGE" \
  --kernel-release "$kernel_release" \
  --root-spec "$ROOT_SPEC" \
  --source-git-commit "$SOURCE_GIT_COMMIT" \
  --source-snapshot-sha256 "$SOURCE_SNAPSHOT_SHA256" \
  --publication-receipt "$PACKAGE_RECEIPT" \
  --build-id "$BUILD_ID" \
  --output-dir "$OUTPUT_ROOT"

# The packager marks success only after both GNU mv publications have been
# inode-verified, then atomically writes their original inode IDs into a receipt
# under this container's private /work directory. Never trust a fresh stat as
# ownership evidence for paths exposed through the host output mount.
recorded_inode_matches "$PACKAGE_RECEIPT_DIR" "$PACKAGE_RECEIPT_DIR_INODE" dir ||
  die "私有发布收据目录被替换"
[[ -f "$PACKAGE_RECEIPT" && ! -L "$PACKAGE_RECEIPT" ]] || die "packager 未生成合法发布收据"
[[ "$(receipt_value "$PACKAGE_RECEIPT" format_version)" == 1 ]] || die "发布收据版本不支持"
PACKAGE_DIR_INODE=$(receipt_value "$PACKAGE_RECEIPT" package_dir_inode) || die "发布收据缺少目录 inode"
PACKAGE_TAR_INODE=$(receipt_value "$PACKAGE_RECEIPT" package_tar_inode) || die "发布收据缺少 tar inode"
[[ "$PACKAGE_DIR_INODE" =~ ^[0-9]+:[0-9]+$ ]] || die "发布收据目录 inode 非法"
[[ "$PACKAGE_TAR_INODE" =~ ^[0-9]+:[0-9]+$ ]] || die "发布收据 tar inode 非法"
recorded_inode_matches "$PACKAGE_DIR" "$PACKAGE_DIR_INODE" dir || die "测试包目录发布不完整"
recorded_inode_matches "$PACKAGE_TAR" "$PACKAGE_TAR_INODE" file || die "测试包 tar 发布不完整"
published_package=1

package_tar_sha256=$(sha256sum "$PACKAGE_TAR" | awk '{print $1}')
package_verify_tmp=$(mktemp -d "$WORK_ROOT/package-verify.XXXXXX")
tar_top_levels=$(tar -tzf "$PACKAGE_TAR" | sed 's#/.*##' | LC_ALL=C sort -u)
[[ "$tar_top_levels" == "$(basename -- "$PACKAGE_DIR")" ]] || die "最终 tar 顶层必须恰好是测试包目录"
tar -xzf "$PACKAGE_TAR" -C "$package_verify_tmp"
package_from_tar="$package_verify_tmp/$(basename -- "$PACKAGE_DIR")"
[[ -d "$package_from_tar" && ! -L "$package_from_tar" ]] || die "最终 tar 缺少测试包顶层目录"
diff -qr --no-dereference "$package_from_tar" "$PACKAGE_DIR" >/dev/null ||
  die "最终 tar 内容与发布目录不一致"
(cd -- "$package_from_tar" && sha256sum --strict -c SHA256SUMS >/dev/null) ||
  die "最终 tar 内 SHA256SUMS 校验失败"
tar_actual_paths="$package_verify_tmp/tar-actual.paths"
tar_checksum_paths="$package_verify_tmp/tar-checksum.paths"
(
  cd -- "$package_from_tar"
  find . -mindepth 1 -type f ! -path './SHA256SUMS' -print |
    sed 's#^\./##' | LC_ALL=C sort
) > "$tar_actual_paths"
sed -n 's/^[0-9a-f]\{64\}  //p' "$package_from_tar/SHA256SUMS" | LC_ALL=C sort > "$tar_checksum_paths"
cmp -s -- "$tar_actual_paths" "$tar_checksum_paths" || die "最终 tar 的 SHA256SUMS 未绑定精确文件集"
[[ "$(receipt_value "$package_from_tar/MANIFEST" kernel_release)" == "$kernel_release" ]] ||
  die "最终 tar MANIFEST 的 kernel_release 与本次构建不一致"
[[ "$(receipt_value "$package_from_tar/MANIFEST" source_git_commit)" == "$SOURCE_GIT_COMMIT" ]] ||
  die "最终 tar MANIFEST 的 source_git_commit 与本次构建不一致"
[[ "$(receipt_value "$package_from_tar/MANIFEST" source_snapshot_sha256)" == "$SOURCE_SNAPSHOT_SHA256" ]] ||
  die "最终 tar MANIFEST 的 source_snapshot_sha256 与本次构建不一致"
package_manifest_sha256=$(sha256sum "$package_from_tar/MANIFEST" | awk '{print $1}')
package_payload_manifest_sha256=$(sha256sum "$package_from_tar/SHA256SUMS" | awk '{print $1}')
module_tree_field_count=$(grep -c '^module_tree_sha256=' "$package_from_tar/MANIFEST" || true)
[[ "$module_tree_field_count" == 1 ]] || die "最终 tar MANIFEST 的 module_tree_sha256 字段不唯一"
manifest_module_tree_sha256=$(sed -n 's/^module_tree_sha256=//p' "$package_from_tar/MANIFEST")
[[ "$manifest_module_tree_sha256" =~ ^[0-9a-f]{64}$ ]] || die "测试包缺少合法 module_tree_sha256"
tar_module_tree_manifest="$package_verify_tmp/MODULES-SHA256SUMS"
(
  cd -- "$package_from_tar"
  find "rootfs/lib/modules/$kernel_release" -type f -print | LC_ALL=C sort |
    while IFS= read -r module_payload; do
      sha256sum -- "$module_payload"
    done
) > "$tar_module_tree_manifest"
module_tree_sha256=$(sha256sum "$tar_module_tree_manifest" | awk '{print $1}')
[[ "$module_tree_sha256" == "$manifest_module_tree_sha256" ]] ||
  die "最终 tar 的模块树摘要与 MANIFEST 不一致"
[[ "$(sha256sum "$PACKAGE_DIR/MANIFEST" | awk '{print $1}')" == "$package_manifest_sha256" ]] ||
  die "发布目录 MANIFEST 与最终 tar 不一致"
[[ "$(sha256sum "$PACKAGE_DIR/SHA256SUMS" | awk '{print $1}')" == "$package_payload_manifest_sha256" ]] ||
  die "发布目录 SHA256SUMS 与最终 tar 不一致"

{
  printf 'kernel_release=%s\n' "$kernel_release"
  printf 'kernel_url=%s\n' "$KERNEL_URL"
  printf 'kernel_mirror_url=%s\n' "$KERNEL_MIRROR_URL"
  printf 'kernel_download_used=%s\n' "$download_url_used"
  printf 'kernel_sha256=%s\n' "$KERNEL_SHA256"
  printf 'builder_image=%s\n' "$BUILDER_IMAGE"
  printf 'builder_image_id=%s\n' "$BUILDER_IMAGE_ID"
  printf 'docker_context=%s\n' "$DOCKER_CONTEXT"
  printf 'docker_client_version=%s\n' "$DOCKER_CLIENT_VERSION"
  printf 'docker_server_version=%s\n' "$DOCKER_SERVER_VERSION"
  printf 'compiler=%s\n' "$(gcc -dumpfullversion -dumpversion)"
  printf 'binutils=%s\n' "$(ld --version | sed -n '1p')"
  printf 'source_git_commit=%s\n' "$SOURCE_GIT_COMMIT"
  printf 'source_git_dirty=%s\n' "$SOURCE_GIT_DIRTY"
  printf 'source_snapshot_sha256=%s\n' "$SOURCE_SNAPSHOT_SHA256"
  printf 'source_file_manifest_sha256=%s\n' "$source_file_manifest_sha256"
  printf 'module_tree_sha256=%s\n' "$module_tree_sha256"
  printf 'package_manifest_sha256=%s\n' "$package_manifest_sha256"
  printf 'package_payload_manifest_sha256=%s\n' "$package_payload_manifest_sha256"
  printf 'package_tar_sha256=%s\n' "$package_tar_sha256"
  printf 'built_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} > "$BUILD_META_TMP/BUILD-INFO"

(
  cd -- "$BUILD_META_TMP"
  sha256sum -- BUILD-INFO Image Module.symvers-* SOURCE-SHA256SUMS System.map-* config-* rk3326-r46h.dtb > SHA256SUMS
)

BUILD_META_DIR_INODE="$BUILD_META_TMP_INODE"
publish_no_clobber "$BUILD_META_TMP" "$BUILD_META_DIR" "$BUILD_META_TMP_INODE" dir
if ! chown_recorded "$BUILD_META_DIR" "$BUILD_META_DIR_INODE" dir ||
   ! chown_recorded "$PACKAGE_DIR" "$PACKAGE_DIR_INODE" dir ||
   ! chown_recorded "$PACKAGE_TAR" "$PACKAGE_TAR_INODE" file; then
  printf 'warning: 无法把输出所有者改为宿主 UID/GID；产物本身已完成\n' >&2
fi
recorded_inode_matches "$BUILD_META_DIR" "$BUILD_META_DIR_INODE" dir || die "构建元数据目录在发布后被替换"
recorded_inode_matches "$PACKAGE_DIR" "$PACKAGE_DIR_INODE" dir || die "测试包目录在发布后被替换"
recorded_inode_matches "$PACKAGE_TAR" "$PACKAGE_TAR_INODE" file || die "测试包 tar 在发布后被替换"
[[ "$(sha256sum "$PACKAGE_TAR" | awk '{print $1}')" == "$package_tar_sha256" ]] || \
  die "测试包在发布期间发生变化"
[[ "$(sha256sum "$PACKAGE_DIR/MANIFEST" | awk '{print $1}')" == "$package_manifest_sha256" ]] || \
  die "测试包 MANIFEST 在发布期间发生变化"
[[ "$(sha256sum "$PACKAGE_DIR/SHA256SUMS" | awk '{print $1}')" == "$package_payload_manifest_sha256" ]] || \
  die "测试包 SHA256SUMS 在发布期间发生变化"
diff -qr --no-dereference "$package_from_tar" "$PACKAGE_DIR" >/dev/null ||
  die "发布目录在最终复核时与 tar 不一致"
(cd -- "$BUILD_META_DIR" && sha256sum --strict -c SHA256SUMS >/dev/null) || die "构建元数据发布后自校验失败"
published_package=0

printf 'Build metadata: %s\n' "$BUILD_META_DIR"
printf 'Test archive: %s\n' "$PACKAGE_TAR"
