#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
MAINLINE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
readonly MAINLINE_DIR
readonly PACKAGER="$MAINLINE_DIR/scripts/package-test-build.sh"
readonly CONTAINER_BUILDER="$MAINLINE_DIR/scripts/build-in-container.sh"
readonly TEST_PARENT="$MAINLINE_DIR/out"
export SOURCE_DATE_EPOCH=1785369600

for tool in cc dtc fdtget file modinfo sha256sum; do
  command -v "$tool" >/dev/null 2>&1 || {
    printf 'FAIL: 测试必须在 R46H builder 容器运行，缺少 %s\n' "$tool" >&2
    exit 1
  }
done

mkdir -p -- "$TEST_PARENT"
TEST_DIR=$(mktemp -d "$TEST_PARENT/.package-test.XXXXXX")
trap 'rm -rf -- "$TEST_DIR"' EXIT

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_file() {
  [[ -f "$1" ]] || fail "缺少文件: $1"
}

assert_contains() {
  local path=$1
  local expected=$2
  grep -Fq -- "$expected" "$path" || fail "$path 不含: $expected"
}

expect_failure() {
  if "$@" >/dev/null 2>&1; then
    fail "命令应失败但成功: $*"
  fi
}

expect_failure_contains() {
  local expected=$1
  local failure_log
  shift
  failure_log=$(mktemp "$TEST_DIR/.expected-failure.XXXXXX")
  if "$@" >"$failure_log" 2>&1; then
    fail "命令应失败但成功: $*"
  fi
  assert_contains "$failure_log" "$expected"
}

# build-in-container.sh is normally entered only after the host has verified a
# Git snapshot. Exercise its preflight directly here so newly required Docker
# provenance cannot silently become optional or disappear from BUILD-INFO.
builder_preflight_env=(
  BUILD_ID=fixture
  BUILDER_IMAGE=arkos4clone/r46h-kernel-builder:fixture
  BUILDER_IMAGE_ID=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
)
expect_failure_contains '缺少环境变量 DOCKER_CLIENT_VERSION' \
  env -i PATH=/usr/bin:/bin LC_ALL=C LANG=C \
  "${builder_preflight_env[@]}" "$CONTAINER_BUILDER"
expect_failure_contains '缺少环境变量 DOCKER_CONTEXT' \
  env -i PATH=/usr/bin:/bin LC_ALL=C LANG=C \
  "${builder_preflight_env[@]}" DOCKER_CLIENT_VERSION=29.6.1 "$CONTAINER_BUILDER"
expect_failure_contains '缺少环境变量 DOCKER_SERVER_VERSION' \
  env -i PATH=/usr/bin:/bin LC_ALL=C LANG=C \
  "${builder_preflight_env[@]}" DOCKER_CLIENT_VERSION=29.6.1 \
  DOCKER_CONTEXT=desktop-linux "$CONTAINER_BUILDER"
assert_contains "$CONTAINER_BUILDER" "printf 'docker_context=%s\\n'"
assert_contains "$CONTAINER_BUILDER" "printf 'docker_client_version=%s\\n'"
assert_contains "$CONTAINER_BUILDER" "printf 'docker_server_version=%s\\n'"

image="$TEST_DIR/Image"
dtb="$TEST_DIR/rk3326-r46h.dtb"
modules="$TEST_DIR/modules"
output="$TEST_DIR/out"
publication_receipt="$TEST_DIR/publication.receipt"
release="6.12.99-r46h-mainline-v0.2"
source_commit="0123456789abcdef0123456789abcdef01234567"
source_snapshot_sha256="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
vermagic="$release SMP preempt mod_unload aarch64"

dd if=/dev/zero of="$image" bs=1048576 count=8 2>/dev/null
printf '\x00\x00\x08\x00\x00\x00\x00\x00' | dd of="$image" bs=1 seek=8 conv=notrunc 2>/dev/null
printf '\x00\x00\x80\x00\x00\x00\x00\x00' | dd of="$image" bs=1 seek=16 conv=notrunc 2>/dev/null
printf '\x41\x52\x4d\x64' | dd of="$image" bs=1 seek=56 conv=notrunc 2>/dev/null
printf 'Linux version %s (package-test@builder) #1 SMP\0' "$release" | \
  dd of="$image" bs=1 seek=1024 conv=notrunc 2>/dev/null
printf '%s\0' "$vermagic" | dd of="$image" bs=1 seek=2048 conv=notrunc 2>/dev/null

dt_source="$TEST_DIR/rk3326-r46h.dts"
cat > "$dt_source" <<'EOF'
/dts-v1/;
/ {
    compatible = "rockchip,rk3326-r46h-linux", "rockchip,rk3326";
    model = "R46H package test fixture";
    #address-cells = <2>;
    #size-cells = <2>;
    chosen { stdout-path = "serial2:115200n8"; };
};
EOF
dtc -q -I dts -O dtb -p 512 -o "$dtb" "$dt_source"

mkdir -p -- \
  "$modules/lib/modules/$release/kernel/drivers/gpu/drm/panfrost" \
  "$modules/lib/modules/$release/kernel/drivers/gpu/drm/scheduler" \
  "$modules/lib/modules/$release/kernel/drivers/gpu/drm"
module_source="$TEST_DIR/panfrost-test.c"
cat > "$module_source" <<EOF
__attribute__((used, section(".modinfo")))
static const char vermagic[] = "vermagic=$vermagic";
int package_test_module;
EOF
base_module="$modules/lib/modules/$release/kernel/drivers/gpu/drm/panfrost/panfrost.ko"
cc -c -o "$base_module" "$module_source"
gzip -n -c -- "$base_module" > "$modules/lib/modules/$release/kernel/drivers/gpu/drm/scheduler/gpu_sched.ko.gz"
xz -c -- "$base_module" > "$modules/lib/modules/$release/kernel/drivers/gpu/drm/drm.ko.xz"
zstd -q -c -- "$base_module" > "$modules/lib/modules/$release/kernel/drivers/gpu/drm/drm_gpuvm.ko.zst"
cat > "$modules/lib/modules/$release/modules.dep" <<'EOF'
kernel/drivers/gpu/drm/drm.ko.xz:
kernel/drivers/gpu/drm/drm_gpuvm.ko.zst:
kernel/drivers/gpu/drm/panfrost/panfrost.ko: kernel/drivers/gpu/drm/scheduler/gpu_sched.ko.gz
kernel/drivers/gpu/drm/scheduler/gpu_sched.ko.gz:
EOF

"$PACKAGER" \
  --image "$image" \
  --dtb "$dtb" \
  --modules-dir "$modules" \
  --build-id smoke \
  --source-git-commit "$source_commit" \
  --source-snapshot-sha256 "$source_snapshot_sha256" \
  --publication-receipt "$publication_receipt" \
  --output-dir "$output" >/dev/null

package="$output/r46h-mainline-test-smoke"
archive="$output/r46h-mainline-test-smoke.tar.gz"
assert_file "$package/boot/Image.mainline-test"
assert_file "$package/boot/rk3326-r46h-mainline-test.dtb"
assert_file "$package/boot/boot.ini.test"
assert_file "$package/rootfs/lib/modules/$release/modules.dep"
assert_file "$package/MANIFEST"
assert_file "$package/SHA256SUMS"
assert_file "$archive"
assert_file "$publication_receipt"
assert_contains "$publication_receipt" 'format_version=1'
assert_contains "$publication_receipt" "package_dir_inode=$(stat -c '%d:%i' -- "$package")"
assert_contains "$publication_receipt" "package_tar_inode=$(stat -c '%d:%i' -- "$archive")"
[[ ! -e "$package/rootfs/lib/modules/$release/build" ]] || fail "不应打包主机构建路径链接"
assert_contains "$package/boot/boot.ini.test" 'console=ttyS2,115200n8 earlycon'
assert_contains "$package/boot/boot.ini.test" 'Image.mainline-test'
assert_contains "$package/boot/boot.ini.test" "booti \${loadaddr} - \${dtb_loadaddr}"
assert_contains "$package/MANIFEST" "kernel_release=$release"
assert_contains "$package/MANIFEST" 'dtb_compatible=rockchip,rk3326-r46h-linux'
assert_contains "$package/MANIFEST" "source_git_commit=$source_commit"
assert_contains "$package/MANIFEST" "source_snapshot_sha256=$source_snapshot_sha256"
assert_contains "$package/MANIFEST" 'format_version=2'

module_manifest_check="$TEST_DIR/module-tree.sha256s"
(
  cd -- "$package"
  find "rootfs/lib/modules/$release" -type f -print | LC_ALL=C sort |
    while IFS= read -r module_payload; do
      sha256sum -- "$module_payload"
    done
) > "$module_manifest_check"
expected_module_tree_sha256=$(sha256sum "$module_manifest_check" | awk '{print $1}')
assert_contains "$package/MANIFEST" "module_tree_sha256=$expected_module_tree_sha256"

if command -v sha256sum >/dev/null 2>&1; then
  (cd -- "$package" && sha256sum -c SHA256SUMS >/dev/null)
else
  (cd -- "$package" && shasum -a 256 -c SHA256SUMS >/dev/null)
fi
tar -tzf "$archive" | grep -F "$release/kernel/drivers/gpu/drm/panfrost/panfrost.ko" >/dev/null || fail "tar 缺少模块"
tar -tzf "$archive" | grep -F "$release/kernel/drivers/gpu/drm/scheduler/gpu_sched.ko.gz" >/dev/null || fail "tar 缺少 gzip 模块"
tar -tzf "$archive" | grep -F "$release/kernel/drivers/gpu/drm/drm.ko.xz" >/dev/null || fail "tar 缺少 xz 模块"
tar -tzf "$archive" | grep -F "$release/kernel/drivers/gpu/drm/drm_gpuvm.ko.zst" >/dev/null || fail "tar 缺少 zstd 模块"

actual_payload_count=$(find "$package" -type f ! -path "$package/SHA256SUMS" | wc -l | tr -d '[:space:]')
checksum_count=$(wc -l < "$package/SHA256SUMS" | tr -d '[:space:]')
[[ "$actual_payload_count" == "$checksum_count" ]] || fail "SHA256SUMS 未覆盖精确普通文件集"
[[ -z "$(find "$package" -mindepth 1 \( -type l -o \( ! -type d ! -type f \) \) -print -quit)" ]] || \
  fail "测试包含链接或特殊文件"

repro_output="$TEST_DIR/repro-out"
find "$modules" -exec touch -d '@1700000000' -- {} +
touch -d '@1700000000' -- "$image" "$dtb"
(
  umask 077
  "$PACKAGER" \
    --image "$image" \
    --dtb "$dtb" \
    --modules-dir "$modules" \
    --build-id smoke \
    --source-git-commit "$source_commit" \
    --source-snapshot-sha256 "$source_snapshot_sha256" \
    --output-dir "$repro_output" >/dev/null
)
cmp -s "$archive" "$repro_output/r46h-mainline-test-smoke.tar.gz" || fail "固定 SOURCE_DATE_EPOCH 后 tar 不可复现"

initramfs="$TEST_DIR/initramfs.img"
printf 'fake initramfs for packaging test\n' > "$initramfs"
"$PACKAGER" \
  --image "$image" \
  --dtb "$dtb" \
  --modules-dir "$modules" \
  --initramfs "$initramfs" \
  --build-id smoke-initramfs \
  --output-dir "$output" >/dev/null
initramfs_package="$output/r46h-mainline-test-smoke-initramfs"
assert_file "$initramfs_package/boot/initramfs.mainline-test"
assert_contains "$initramfs_package/boot/boot.ini.test" "setenv initrd_size \${filesize}"
assert_contains "$initramfs_package/boot/boot.ini.test" "booti \${loadaddr} \${initrd_loadaddr}:\${initrd_size} \${dtb_loadaddr}"
assert_contains "$initramfs_package/MANIFEST" 'initramfs=raw-address-size'

expect_failure "$PACKAGER" --image "$image" --dtb "$dtb" --modules-dir "$modules" --build-id root-output --output-dir /
expect_failure "$PACKAGER" --image "$image" --dtb "$dtb" --modules-dir "$modules" --build-id smoke --output-dir "$output"
expect_failure "$PACKAGER" --image "$image" --dtb "$dtb" --modules-dir "$modules" --build-id bad-commit --source-git-commit not-a-commit --output-dir "$output"
expect_failure "$PACKAGER" --image "$image" --dtb "$dtb" --modules-dir "$modules" --build-id bad-snapshot --source-snapshot-sha256 not-a-sha256 --output-dir "$output"

bad_image="$TEST_DIR/bad-Image"
dd if=/dev/zero of="$bad_image" bs=1048576 count=1 2>/dev/null
expect_failure "$PACKAGER" --image "$bad_image" --dtb "$dtb" --modules-dir "$modules" --build-id bad-image --output-dir "$output"

short_declared_image="$TEST_DIR/short-declared-Image"
cp -- "$image" "$short_declared_image"
printf x >> "$short_declared_image"
expect_failure "$PACKAGER" --image "$short_declared_image" --dtb "$dtb" --modules-dir "$modules" --build-id short-declared-image --output-dir "$output"

missing_vermagic_image="$TEST_DIR/missing-vermagic-Image"
cp -- "$image" "$missing_vermagic_image"
printf X | dd of="$missing_vermagic_image" bs=1 seek=2048 conv=notrunc 2>/dev/null
expect_failure "$PACKAGER" --image "$missing_vermagic_image" --dtb "$dtb" --modules-dir "$modules" --build-id missing-image-vermagic --output-dir "$output"

wrong_banner_image="$TEST_DIR/wrong-banner-Image"
cp -- "$image" "$wrong_banner_image"
printf X | dd of="$wrong_banner_image" bs=1 seek=1024 conv=notrunc 2>/dev/null
expect_failure "$PACKAGER" --image "$wrong_banner_image" --dtb "$dtb" --modules-dir "$modules" --build-id wrong-image-banner --output-dir "$output"

oversized_declared_image="$TEST_DIR/oversized-declared-Image"
cp -- "$image" "$oversized_declared_image"
printf '\x01\x00\x80\x01\x00\x00\x00\x00' | \
  dd of="$oversized_declared_image" bs=1 seek=16 conv=notrunc 2>/dev/null
expect_failure "$PACKAGER" --image "$oversized_declared_image" --dtb "$dtb" --modules-dir "$modules" --build-id oversized-declared-image --output-dir "$output"

bad_dtb="$TEST_DIR/bad.dtb"
bad_dt_source="$TEST_DIR/bad.dts"
cat > "$bad_dt_source" <<'EOF'
/dts-v1/;
/ { compatible = "rockchip,not-r46h-compatible"; model = "wrong fixture"; };
EOF
dtc -q -I dts -O dtb -p 512 -o "$bad_dtb" "$bad_dt_source"
expect_failure "$PACKAGER" --image "$image" --dtb "$bad_dtb" --modules-dir "$modules" --build-id bad-dtb --output-dir "$output"

malformed_dtb="$TEST_DIR/malformed.dtb"
dd if=/dev/zero of="$malformed_dtb" bs=512 count=1 2>/dev/null
printf '\xd0\x0d\xfe\xed' | dd of="$malformed_dtb" bs=1 seek=0 conv=notrunc 2>/dev/null
expect_failure "$PACKAGER" --image "$image" --dtb "$malformed_dtb" --modules-dir "$modules" --build-id malformed-dtb --output-dir "$output"

empty_modules="$TEST_DIR/empty-modules"
mkdir -p -- "$empty_modules/lib/modules/$release"
expect_failure "$PACKAGER" --image "$image" --dtb "$dtb" --modules-dir "$empty_modules" --build-id empty-modules --output-dir "$output"

wrong_release="6.13.0-r46h"
wrong_modules="$TEST_DIR/wrong-modules"
mkdir -p -- "$wrong_modules/lib/modules/$wrong_release/kernel"
printf 'kernel/test.ko:\n' > "$wrong_modules/lib/modules/$wrong_release/modules.dep"
printf 'fake module\n' > "$wrong_modules/lib/modules/$wrong_release/kernel/test.ko"
expect_failure "$PACKAGER" --image "$image" --dtb "$dtb" --modules-dir "$wrong_modules" --build-id wrong-baseline --output-dir "$output"

linked_modules="$TEST_DIR/linked-modules"
cp -a -- "$modules" "$linked_modules"
ln -s "$TEST_DIR/fake-build-host" "$linked_modules/lib/modules/$release/build"
expect_failure "$PACKAGER" --image "$image" --dtb "$dtb" --modules-dir "$linked_modules" --build-id linked-modules --output-dir "$output"

special_modules="$TEST_DIR/special-modules"
cp -a -- "$modules" "$special_modules"
mkfifo "$special_modules/lib/modules/$release/kernel/test.fifo"
expect_failure "$PACKAGER" --image "$image" --dtb "$dtb" --modules-dir "$special_modules" --build-id special-modules --output-dir "$output"

bad_module_tree="$TEST_DIR/bad-module-tree"
cp -a -- "$modules" "$bad_module_tree"
printf 'not an ELF module\n' > "$bad_module_tree/lib/modules/$release/kernel/drivers/gpu/drm/panfrost/panfrost.ko"
expect_failure "$PACKAGER" --image "$image" --dtb "$dtb" --modules-dir "$bad_module_tree" --build-id bad-module --output-dir "$output"

wrong_flags_tree="$TEST_DIR/wrong-flags-tree"
cp -a -- "$modules" "$wrong_flags_tree"
wrong_flags_source="$TEST_DIR/wrong-flags.c"
cat > "$wrong_flags_source" <<EOF
__attribute__((used, section(".modinfo")))
static const char vermagic[] = "vermagic=$release SMP mod_unload aarch64";
int package_test_wrong_flags_module;
EOF
cc -c -o "$wrong_flags_tree/lib/modules/$release/kernel/drivers/gpu/drm/panfrost/panfrost.ko" "$wrong_flags_source"
expect_failure "$PACKAGER" --image "$image" --dtb "$dtb" --modules-dir "$wrong_flags_tree" --build-id wrong-flags --output-dir "$output"

same_count_nonmodule="$TEST_DIR/same-count-nonmodule"
cp -a -- "$modules" "$same_count_nonmodule"
printf 'not a module\n' > "$same_count_nonmodule/lib/modules/$release/kernel/not-a-module.bin"
cat > "$same_count_nonmodule/lib/modules/$release/modules.dep" <<'EOF'
kernel/drivers/gpu/drm/drm.ko.xz:
kernel/drivers/gpu/drm/panfrost/panfrost.ko:
kernel/drivers/gpu/drm/scheduler/gpu_sched.ko.gz:
kernel/not-a-module.bin:
EOF
expect_failure "$PACKAGER" --image "$image" --dtb "$dtb" --modules-dir "$same_count_nonmodule" --build-id same-count-nonmodule --output-dir "$output"

missing_dep_entry="$TEST_DIR/missing-dep-entry"
cp -a -- "$modules" "$missing_dep_entry"
cat > "$missing_dep_entry/lib/modules/$release/modules.dep" <<'EOF'
kernel/drivers/gpu/drm/drm.ko.xz:
kernel/drivers/gpu/drm/panfrost/panfrost.ko:
kernel/drivers/gpu/drm/scheduler/gpu_sched.ko.gz:
EOF
expect_failure "$PACKAGER" --image "$image" --dtb "$dtb" --modules-dir "$missing_dep_entry" --build-id missing-dep-entry --output-dir "$output"

duplicate_dep_entry="$TEST_DIR/duplicate-dep-entry"
cp -a -- "$modules" "$duplicate_dep_entry"
cat > "$duplicate_dep_entry/lib/modules/$release/modules.dep" <<'EOF'
kernel/drivers/gpu/drm/drm.ko.xz:
kernel/drivers/gpu/drm/panfrost/panfrost.ko:
kernel/drivers/gpu/drm/panfrost/panfrost.ko:
kernel/drivers/gpu/drm/scheduler/gpu_sched.ko.gz:
EOF
expect_failure "$PACKAGER" --image "$image" --dtb "$dtb" --modules-dir "$duplicate_dep_entry" --build-id duplicate-dep-entry --output-dir "$output"

bad_dependency="$TEST_DIR/bad-dependency"
cp -a -- "$modules" "$bad_dependency"
printf 'not a module\n' > "$bad_dependency/lib/modules/$release/kernel/not-a-module.bin"
cat > "$bad_dependency/lib/modules/$release/modules.dep" <<'EOF'
kernel/drivers/gpu/drm/drm.ko.xz:
kernel/drivers/gpu/drm/drm_gpuvm.ko.zst:
kernel/drivers/gpu/drm/panfrost/panfrost.ko: kernel/not-a-module.bin
kernel/drivers/gpu/drm/scheduler/gpu_sched.ko.gz:
EOF
expect_failure "$PACKAGER" --image "$image" --dtb "$dtb" --modules-dir "$bad_dependency" --build-id bad-dependency --output-dir "$output"

race_output="$TEST_DIR/race-output"
race_bin="$TEST_DIR/race-bin"
mkdir -p -- "$race_output" "$race_bin"
real_mv=$(command -v mv)
cat > "$race_bin/mv" <<EOF
#!/usr/bin/env bash
set -Eeuo pipefail
last_arg=""
for arg in "\$@"; do
  last_arg=\$arg
done
if [[ -n "\${R46H_TEST_RACE_TARGET:-}" && "\$last_arg" == "\$R46H_TEST_RACE_TARGET" ]]; then
  printf 'foreign-race-winner\n' > "\$R46H_TEST_RACE_TARGET"
fi
exec "$real_mv" "\$@"
EOF
chmod 0755 -- "$race_bin/mv"
race_target="$race_output/r46h-mainline-test-race.tar.gz"
expect_failure env \
  PATH="$race_bin:$PATH" \
  R46H_TEST_RACE_TARGET="$race_target" \
  "$PACKAGER" \
  --image "$image" \
  --dtb "$dtb" \
  --modules-dir "$modules" \
  --build-id race \
  --output-dir "$race_output"
[[ "$(< "$race_target")" == foreign-race-winner ]] || fail "发布竞态覆盖或删除了外来 tar"
[[ ! -e "$race_output/r46h-mainline-test-race" ]] || fail "tar 发布竞态失败后不应留下 package 目录"
[[ -z "$(find "$race_output" -maxdepth 1 -name '.r46h-package.*' -print -quit)" ]] ||
  fail "发布竞态失败后残留打包临时目录"

receipt_collision_output="$TEST_DIR/receipt-collision-output"
mkdir -p -- "$receipt_collision_output"
receipt_collision_tar="$receipt_collision_output/r46h-mainline-test-receipt-collision.tar.gz"
expect_failure "$PACKAGER" \
  --image "$image" \
  --dtb "$dtb" \
  --modules-dir "$modules" \
  --build-id receipt-collision \
  --publication-receipt "$receipt_collision_tar" \
  --output-dir "$receipt_collision_output"
[[ ! -e "$receipt_collision_tar" &&
   ! -e "$receipt_collision_output/r46h-mainline-test-receipt-collision" ]] ||
  fail "receipt 发布冲突后没有回滚本次 tar/目录"
[[ -z "$(find "$receipt_collision_output" -maxdepth 1 \
  \( -name '.r46h-package.*' -o -name '.r46h-publication-receipt.*' \) -print -quit)" ]] ||
  fail "receipt 发布冲突后残留临时对象"

printf 'PASS: package-test-build\n'
