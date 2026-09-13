#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
MAINLINE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
readonly MAINLINE_DIR
readonly STAGER="$MAINLINE_DIR/scripts/stage-test-to-sd.sh"
readonly TEST_PARENT="$MAINLINE_DIR/out"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

(( EUID == 0 )) || fail "此测试必须在隔离容器中以 root 运行"

mkdir -p -- "$TEST_PARENT"
TEST_DIR=$(mktemp -d "$TEST_PARENT/.stage-test.XXXXXX")
fake_bin=$(mktemp -d /run/r46h-stage-test.XXXXXX)
trap 'rm -rf -- "$TEST_DIR" "$fake_bin"' EXIT

package="$TEST_DIR/package"
boot_mount="$TEST_DIR/boot-mount"
root_mount="$TEST_DIR/root-mount"
release="6.12.99-r46h-mainline-v0.2"

mkdir -p -- \
  "$package/boot" \
  "$package/rootfs/lib/modules/$release/kernel/drivers/test"
printf 'test boot script\n' > "$package/boot/boot.ini.test"
printf 'test arm64 image\n' > "$package/boot/Image.mainline-test"
printf 'test dtb\n' > "$package/boot/rk3326-r46h-mainline-test.dtb"
printf 'kernel/drivers/test/test.ko:\n' > "$package/rootfs/lib/modules/$release/modules.dep"
printf 'test module\n' > "$package/rootfs/lib/modules/$release/kernel/drivers/test/test.ko"
printf 'kernel_release=%s\n' "$release" > "$package/MANIFEST"
(
  cd -- "$package"
  sha256sum \
    MANIFEST \
    boot/boot.ini.test \
    boot/Image.mainline-test \
    boot/rk3326-r46h-mainline-test.dtb \
    "rootfs/lib/modules/$release/modules.dep" \
    "rootfs/lib/modules/$release/kernel/drivers/test/test.ko" \
    > SHA256SUMS
)

cat > "$fake_bin/mountpoint" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
target=""
for arg in "$@"; do
  target=$arg
done
state=stable
[[ ! -f "$IDENTITY_STATE_FILE" ]] || state=$(<"$IDENTITY_STATE_FILE")
[[ ! ( "$state" == boot-missing && "$target" == "$BOOT_TEST_MOUNT" ) ]]
[[ ! ( "$state" == root-missing && "$target" == "$ROOT_TEST_MOUNT" ) ]]
[[ "$target" == "$BOOT_TEST_MOUNT" || "$target" == "$ROOT_TEST_MOUNT" ]]
EOF

cat > "$fake_bin/findmnt" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
target=""
field=""
while (( $# > 0 )); do
  case "$1" in
    -o) field=$2; shift 2 ;;
    --target) target=$2; shift 2 ;;
    *) shift ;;
  esac
done

state=stable
[[ ! -f "$IDENTITY_STATE_FILE" ]] || state=$(<"$IDENTITY_STATE_FILE")

if [[ -n "$NESTED_ROOT_PATH" && ( "$target" == "$NESTED_ROOT_PATH" || "$target" == "$NESTED_ROOT_PATH/"* ) ]]; then
  source='/dev/nested-test1[/bind]'
  majmin=241:1
  fstype=ext4
elif [[ "$target" == "$BOOT_TEST_MOUNT" || "$target" == "$BOOT_TEST_MOUNT/"* ]]; then
  source=$BOOT_TEST_SOURCE
  majmin=$BOOT_TEST_MAJMIN
  fstype=vfat
  if [[ "$state" == boot-changed || "$state" == boot-missing ]]; then
    source=/dev/replacement-test1
    majmin=250:1
  fi
elif [[ "$target" == "$ROOT_TEST_MOUNT" || "$target" == "$ROOT_TEST_MOUNT/"* ]]; then
  source=$ROOT_TEST_SOURCE
  majmin=$ROOT_TEST_MAJMIN
  fstype=ext4
  if [[ "$state" == root-changed || "$state" == root-missing ]]; then
    source=/dev/replacement-test2
    majmin=250:2
  fi
elif [[ "$target" == / ]]; then
  source=$SYSTEM_TEST_SOURCE
  majmin=$SYSTEM_TEST_MAJMIN
  fstype=ext4
else
  exit 1
fi

case "$field" in
  FSTYPE) printf '%s\n' "$fstype" ;;
  SOURCE) printf '%s\n' "$source" ;;
  MAJ:MIN) printf '%s\n' "$majmin" ;;
  SOURCE,MAJ:MIN) printf '%s %s\n' "$source" "$majmin" ;;
  *) exit 1 ;;
esac
EOF

cat > "$fake_bin/lsblk" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
field=""
device=""
while (( $# > 0 )); do
  case "$1" in
    -o) field=$2; shift 2 ;;
    --) device=$2; shift 2 ;;
    -*) shift ;;
    *) device=$1; shift ;;
  esac
done

if [[ "$device" == "$BOOT_TEST_SOURCE" ]]; then
  type=part
  parent=$BOOT_TEST_DISK
elif [[ "$device" == "$ROOT_TEST_SOURCE" ]]; then
  type=part
  parent=$ROOT_TEST_DISK
elif [[ "$device" == "$SYSTEM_TEST_SOURCE" ]]; then
  type=part
  parent=$SYSTEM_TEST_DISK
elif [[ "$device" == "$BOOT_TEST_DISK" || "$device" == "$ROOT_TEST_DISK" ]]; then
  type=disk
  parent=""
elif [[ "$device" == "$SYSTEM_TEST_DISK" ]]; then
  type=disk
  parent=""
else
  exit 1
fi

case "$field" in
  TYPE) printf '%s\n' "$type" ;;
  PKNAME) [[ -n "$parent" ]] && printf '%s\n' "$parent" ;;
  MAJ:MIN)
    if [[ "$device" == "$BOOT_TEST_SOURCE" ]]; then
      printf '%s\n' "$BOOT_TEST_MAJMIN"
    elif [[ "$device" == "$ROOT_TEST_SOURCE" ]]; then
      printf '%s\n' "$ROOT_TEST_MAJMIN"
    elif [[ "$device" == "$SYSTEM_TEST_SOURCE" ]]; then
      printf '%s\n' "$SYSTEM_TEST_MAJMIN"
    else
      exit 1
    fi
    ;;
  RM)
    [[ "$type" == disk ]] || exit 1
    if [[ "$device" == "$SYSTEM_TEST_DISK" ]]; then
      printf '0\n'
    else
      printf '%s\n' "$TARGET_TEST_RM"
    fi
    ;;
  TRAN)
    [[ "$type" == disk ]] || exit 1
    if [[ "$device" == "$SYSTEM_TEST_DISK" ]]; then
      printf 'nvme\n'
    else
      printf '%s\n' "$TARGET_TEST_TRAN"
    fi
    ;;
  *) exit 1 ;;
esac
EOF

cat > "$fake_bin/df" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
mode=${1:-}
target=""
for arg in "$@"; do
  target=$arg
done

case "$mode:$target" in
  -Pk:"$BOOT_TEST_MOUNT") available=$BOOT_AVAILABLE_KIB ;;
  -Pk:"$ROOT_TEST_MOUNT") available=$ROOT_AVAILABLE_KIB ;;
  -Pi:"$ROOT_TEST_MOUNT") available=$ROOT_AVAILABLE_INODES ;;
  *) exit 1 ;;
esac

printf 'Filesystem Total Used Available Use%% Mounted-on\n'
printf 'testfs 999999 0 %s 0%% %s\n' "$available" "$target"
EOF

cat > "$fake_bin/cp" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
paths=()
for arg in "$@"; do
  case "$arg" in
    --|-*) ;;
    *) paths+=("$arg") ;;
  esac
done
(( ${#paths[@]} == 2 )) || exit 97
source_file=${paths[0]}
target_file=${paths[1]}

if [[ "$source_file" == "$PACKAGE_TEST_MODULE_ROOT/"* && "${FAIL_MODULE_COPY:-0}" == 1 ]]; then
  printf 'partial module\n' > "$target_file"
  exit 23
fi

if [[ "$source_file" == "$PACKAGE_TEST_MODULE_ROOT/"* && \
      "${REPLACE_MODULE_STAGE_ON_COPY:-0}" == 1 ]]; then
  relative_path=${source_file#"$PACKAGE_TEST_MODULE_ROOT"/}
  stage_dir=${target_file%"/$relative_path"}
  rm -rf -- "$stage_dir"
  mkdir -p -- "$stage_dir"
  printf 'foreign replacement stage\n' > "$stage_dir/foreign-marker"
  exit 23
fi

/bin/cp "$@"
if [[ "$source_file" == "$PACKAGE_TEST_MODULE_ROOT/"* && "${FAIL_MODULE_VERIFY:-0}" == 1 ]]; then
  printf 'corrupt after copy\n' >> "$target_file"
fi
if [[ "$source_file" == "$PACKAGE_TEST_MODULE_ROOT/"* && \
      "${LOSE_IDENTITY_AT:-0}" == root-after-module-copy ]]; then
  printf 'root-missing\n' > "$IDENTITY_STATE_FILE"
fi
EOF

cat > "$fake_bin/install" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
counter=0
if [[ -f "$INSTALL_COUNTER_FILE" ]]; then
  counter=$(<"$INSTALL_COUNTER_FILE")
fi
counter=$((counter + 1))
printf '%s\n' "$counter" > "$INSTALL_COUNTER_FILE"

if [[ "${FAIL_BOOT_INSTALL_AT:-0}" == "$counter" ]]; then
  destination=""
  for arg in "$@"; do
    destination=$arg
  done
  printf 'partial boot payload\n' > "$destination"
  exit 28
fi
/usr/bin/install "$@"
if [[ "${LOSE_IDENTITY_AT:-0}" == boot-after-temp-write ]]; then
  printf 'boot-changed\n' > "$IDENTITY_STATE_FILE"
fi
EOF

cat > "$fake_bin/mv" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
paths=()
for arg in "$@"; do
  case "$arg" in
    --|-*) ;;
    *) paths+=("$arg") ;;
  esac
done
(( ${#paths[@]} == 2 )) || exit 97
target_dir=${paths[1]}

if [[ "$target_dir" == "$BOOT_TEST_MOUNT/"* ]]; then
  case "${RACE_BOOT_DEST:-0}" in
    0) ;;
    regular) printf 'foreign boot file\n' > "$target_dir" ;;
    directory)
      mkdir -p -- "$target_dir"
      printf 'foreign boot directory\n' > "$target_dir/foreign-marker"
      ;;
    symlink)
      mkdir -p -- "$BOOT_RACE_ESCAPE"
      printf 'foreign boot symlink target\n' > "$BOOT_RACE_ESCAPE/foreign-marker"
      ln -s -- "$BOOT_RACE_ESCAPE" "$target_dir"
      ;;
    *) exit 98 ;;
  esac
else
  case "${RACE_MODULE_DEST:-0}" in
    0) ;;
    directory)
      mkdir -p -- "$target_dir"
      printf 'foreign directory\n' > "$target_dir/foreign-marker"
      ;;
    symlink)
      mkdir -p -- "$MODULE_RACE_ESCAPE"
      printf 'foreign symlink target\n' > "$MODULE_RACE_ESCAPE/foreign-marker"
      ln -s -- "$MODULE_RACE_ESCAPE" "$target_dir"
      ;;
    *) exit 99 ;;
  esac
fi

exec /bin/mv "$@"
EOF

cat > "$fake_bin/diff" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "${FAIL_MODULE_VERIFY:-0}" == 1 ]]; then
  exit 1
fi
exec /usr/bin/diff "$@"
EOF

cat > "$fake_bin/sync" <<'EOF'
#!/usr/bin/env bash
set -Eeuo pipefail
if [[ "${FAIL_SYNC:-0}" == 1 ]]; then
  exit 5
fi
exec /usr/bin/sync "$@"
EOF

chmod 0755 -- \
  "$fake_bin/mountpoint" \
  "$fake_bin/findmnt" \
  "$fake_bin/lsblk" \
  "$fake_bin/df" \
  "$fake_bin/cp" \
  "$fake_bin/install" \
  "$fake_bin/mv" \
  "$fake_bin/diff" \
  "$fake_bin/sync"
chmod 0700 -- "$fake_bin"

reset_targets() {
  rm -rf -- "$boot_mount" "$root_mount"
  rm -rf -- "$TEST_DIR/module-race-escape" "$TEST_DIR/boot-race-escape" "$TEST_DIR/hostile-tmp"
  mkdir -p -- "$boot_mount" "$root_mount/etc"
  printf 'vendor boot script\n' > "$boot_mount/boot.ini"
  printf 'NAME=TestRoot\n' > "$root_mount/etc/os-release"

  TEST_BOOT_SOURCE=/dev/r46h-test1
  TEST_ROOT_SOURCE=/dev/r46h-test2
  TEST_SYSTEM_SOURCE=/dev/system-test2
  TEST_BOOT_DISK=/dev/r46h-test
  TEST_ROOT_DISK=/dev/r46h-test
  TEST_SYSTEM_DISK=/dev/system-test
  TEST_BOOT_MAJMIN=240:1
  TEST_ROOT_MAJMIN=240:2
  TEST_SYSTEM_MAJMIN=259:2
  TEST_TARGET_RM=1
  TEST_TARGET_TRAN=usb
  TEST_RACE_BOOT_DEST=0
  TEST_LOSE_IDENTITY_AT=0
  TEST_NESTED_ROOT_PATH=""
  TEST_HOSTILE_TMPDIR="$TEST_DIR/hostile-tmp"
  TEST_REPLACE_MODULE_STAGE=0
}

run_stage() {
  local boot_available=$1
  local root_available=$2
  local root_inodes=$3
  local fail_module_copy=$4
  local fail_boot_install_at=$5
  local fail_module_verify=$6
  local fail_sync=$7
  local race_module_dest=${8:-0}

  rm -f -- "$TEST_DIR/install-counter"
  printf 'stable\n' > "$TEST_DIR/identity-state"

  env \
    PATH="$fake_bin:/usr/bin:/bin" \
    R46H_STAGE_TEST_MODE=1 \
    R46H_STAGE_TEST_BIN="$fake_bin" \
    BOOT_TEST_MOUNT="$boot_mount" \
    ROOT_TEST_MOUNT="$root_mount" \
    BOOT_TEST_SOURCE="$TEST_BOOT_SOURCE" \
    ROOT_TEST_SOURCE="$TEST_ROOT_SOURCE" \
    SYSTEM_TEST_SOURCE="$TEST_SYSTEM_SOURCE" \
    BOOT_TEST_DISK="$TEST_BOOT_DISK" \
    ROOT_TEST_DISK="$TEST_ROOT_DISK" \
    SYSTEM_TEST_DISK="$TEST_SYSTEM_DISK" \
    BOOT_TEST_MAJMIN="$TEST_BOOT_MAJMIN" \
    ROOT_TEST_MAJMIN="$TEST_ROOT_MAJMIN" \
    SYSTEM_TEST_MAJMIN="$TEST_SYSTEM_MAJMIN" \
    TARGET_TEST_RM="$TEST_TARGET_RM" \
    TARGET_TEST_TRAN="$TEST_TARGET_TRAN" \
    BOOT_AVAILABLE_KIB="$boot_available" \
    ROOT_AVAILABLE_KIB="$root_available" \
    ROOT_AVAILABLE_INODES="$root_inodes" \
    FAIL_MODULE_COPY="$fail_module_copy" \
    FAIL_BOOT_INSTALL_AT="$fail_boot_install_at" \
    FAIL_MODULE_VERIFY="$fail_module_verify" \
    FAIL_SYNC="$fail_sync" \
    RACE_MODULE_DEST="$race_module_dest" \
    MODULE_RACE_ESCAPE="$TEST_DIR/module-race-escape" \
    RACE_BOOT_DEST="$TEST_RACE_BOOT_DEST" \
    BOOT_RACE_ESCAPE="$TEST_DIR/boot-race-escape" \
    LOSE_IDENTITY_AT="$TEST_LOSE_IDENTITY_AT" \
    IDENTITY_STATE_FILE="$TEST_DIR/identity-state" \
    NESTED_ROOT_PATH="$TEST_NESTED_ROOT_PATH" \
    TMPDIR="$TEST_HOSTILE_TMPDIR" \
    REPLACE_MODULE_STAGE_ON_COPY="$TEST_REPLACE_MODULE_STAGE" \
    PACKAGE_TEST_MODULE_ROOT="$package/rootfs/lib/modules/$release" \
    INSTALL_COUNTER_FILE="$TEST_DIR/install-counter" \
    "$STAGER" \
      --package-dir "$package" \
      --boot-mount "$boot_mount" \
      --root-mount "$root_mount"
}

expect_failure() {
  local label=$1
  local expected_error=$2
  local error_log="$TEST_DIR/failure.stderr"
  local output_log="$TEST_DIR/failure.stdout"
  shift 2
  if run_stage "$@" >"$output_log" 2>"$error_log"; then
    fail "$label 应失败但成功"
  fi
  grep -Fq -- "$expected_error" "$error_log" || fail "$label 未报告预期错误: $expected_error"
}

assert_no_payload() {
  [[ ! -e "$boot_mount/boot.ini.test" ]] || fail "失败后残留 boot.ini.test"
  [[ ! -e "$boot_mount/Image.mainline-test" ]] || fail "失败后残留 Image.mainline-test"
  [[ ! -e "$boot_mount/rk3326-r46h-mainline-test.dtb" ]] || fail "失败后残留测试 DTB"
  [[ ! -e "$root_mount/lib/modules/$release" ]] || fail "失败后残留 modules"
  [[ ! -e "$root_mount/lib" && ! -L "$root_mount/lib" ]] || fail "失败后残留本次创建的 lib 父目录"
  [[ -z "$(find "$boot_mount" -name '.r46h-boot-stage.*' -print -quit)" ]] || fail "失败后残留 BOOT 暂存文件"
  [[ -z "$(find "$root_mount" -name '.r46h-modules-stage.*' -print -quit)" ]] || fail "失败后残留 modules 暂存目录"
  grep -Fxq 'vendor boot script' "$boot_mount/boot.ini" || fail "正式 boot.ini 被修改"
}

reset_targets
boot_block_bytes=$(stat -f -c '%S' -- "$boot_mount")
boot_allocated_bytes=0
for payload in \
  "$package/boot/boot.ini.test" \
  "$package/boot/Image.mainline-test" \
  "$package/boot/rk3326-r46h-mainline-test.dtb"; do
  payload_bytes=$(wc -c < "$payload" | tr -d '[:space:]')
  boot_allocated_bytes=$((
    boot_allocated_bytes +
    ((payload_bytes + boot_block_bytes - 1) / boot_block_bytes) * boot_block_bytes
  ))
done
boot_required_kib=$(((boot_allocated_bytes + 4096 * 1024 + 1023) / 1024))

root_block_bytes=$(stat -f -c '%S' -- "$root_mount")
module_allocated_bytes=0
for payload in \
  "$package/rootfs/lib/modules/$release/modules.dep" \
  "$package/rootfs/lib/modules/$release/kernel/drivers/test/test.ko"; do
  payload_bytes=$(wc -c < "$payload" | tr -d '[:space:]')
  module_allocated_bytes=$((
    module_allocated_bytes +
    ((payload_bytes + root_block_bytes - 1) / root_block_bytes) * root_block_bytes
  ))
done
module_dir_count=$(find "$package/rootfs/lib/modules/$release" -type d -print | wc -l | tr -d '[:space:]')
root_required_kib=$(((
  module_allocated_bytes + module_dir_count * root_block_bytes + 8192 * 1024 + 1023
) / 1024))
root_required_inodes=$((module_dir_count + 2 + 16))

# 设备身份必须在任何写入前 fail closed。
reset_targets
TEST_ROOT_DISK=/dev/other-test
expect_failure "BOOT/root 不同设备" "BOOT/root 不在同一张块设备上" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0
assert_no_payload

reset_targets
TEST_BOOT_DISK=$TEST_SYSTEM_DISK
TEST_ROOT_DISK=$TEST_SYSTEM_DISK
expect_failure "目标为当前系统盘" "目标分区位于当前 / 所在系统盘" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0
assert_no_payload

reset_targets
TEST_ROOT_SOURCE='/dev/system-test2[/bind-root]'
expect_failure "bind mount" "拒绝 bind mount" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0
assert_no_payload

reset_targets
TEST_TARGET_RM=0
TEST_TARGET_TRAN=sata
expect_failure "非可移除内部盘" "目标设备既不可移除也不是受支持的外接介质" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0
assert_no_payload

reset_targets
mkdir -p -- "$root_mount/lib"
printf 'nested mount sentinel\n' > "$root_mount/lib/sentinel"
TEST_NESTED_ROOT_PATH="$root_mount/lib"
expect_failure "rootfs nested mount" "rootfs 解析路径跨越嵌套挂载或 bind mount" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0
grep -Fxq 'nested mount sentinel' "$root_mount/lib/sentinel" || fail "nested mount 预检修改了目标"
[[ ! -e "$boot_mount/boot.ini.test" ]] || fail "nested mount 预检后写入了 BOOT"

# 清单必须精确、唯一、安全地描述全部普通文件。
reset_targets
printf 'unlisted\n' > "$package/rootfs/lib/modules/$release/unlisted.ko"
expect_failure "清单外文件" "SHA256SUMS 与 payload 普通文件集合不一致" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0
rm -f -- "$package/rootfs/lib/modules/$release/unlisted.ko"
assert_no_payload

reset_targets
cp -- "$package/SHA256SUMS" "$TEST_DIR/SHA256SUMS.saved"
head -n 1 "$TEST_DIR/SHA256SUMS.saved" >> "$package/SHA256SUMS"
expect_failure "清单重复路径" "SHA256SUMS 含重复路径" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0
cp -- "$TEST_DIR/SHA256SUMS.saved" "$package/SHA256SUMS"
assert_no_payload

reset_targets
printf '%064d  ../escape\n' 0 >> "$package/SHA256SUMS"
expect_failure "清单越界路径" "SHA256SUMS 含非法路径" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0
cp -- "$TEST_DIR/SHA256SUMS.saved" "$package/SHA256SUMS"
assert_no_payload

reset_targets
ln -s -- modules.dep "$package/rootfs/lib/modules/$release/link.ko"
expect_failure "package 符号链接" "测试包含符号链接或特殊文件" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0
rm -f -- "$package/rootfs/lib/modules/$release/link.ko"
assert_no_payload

reset_targets
mkfifo -- "$package/rootfs/lib/modules/$release/special.fifo"
expect_failure "package 特殊文件" "测试包含符号链接或特殊文件" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0
rm -f -- "$package/rootfs/lib/modules/$release/special.fifo"
assert_no_payload

# 标准布局与 Debian 常见的绝对 /lib -> /usr/lib 都必须安全成功。
reset_targets
run_stage "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0 >/dev/null
cmp -s -- "$package/boot/Image.mainline-test" "$boot_mount/Image.mainline-test" || fail "正常安装未复制 Image"
cmp -s -- \
  "$package/rootfs/lib/modules/$release/kernel/drivers/test/test.ko" \
  "$root_mount/lib/modules/$release/kernel/drivers/test/test.ko" || fail "正常安装未复制 module"
[[ "$(stat -c '%a' -- "$root_mount/lib/modules/$release")" == 755 ]] || fail "modules 顶层目录权限不是 0755"
[[ -z "$(find "$root_mount/lib/modules/$release" -type d ! -perm 0755 -print -quit)" ]] || \
  fail "调用者 umask=077 导致 modules 子目录不可读"
grep -Fxq 'vendor boot script' "$boot_mount/boot.ini" || fail "正常安装修改了正式 boot.ini"

reset_targets
mkdir -p -- "$root_mount/usr/lib"
ln -s -- usr/lib "$root_mount/lib"
run_stage "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0 >/dev/null
cmp -s -- \
  "$package/rootfs/lib/modules/$release/kernel/drivers/test/test.ko" \
  "$root_mount/usr/lib/modules/$release/kernel/drivers/test/test.ko" || \
  fail "相对 /lib 链接未在离线 rootfs 内解析"
[[ "$(readlink -- "$root_mount/lib")" == usr/lib ]] || fail "相对 /lib 链接被修改"

reset_targets
mkdir -p -- "$root_mount/usr/lib"
ln -s -- /usr/lib "$root_mount/lib"
[[ ! -e "/usr/lib/modules/$release" && ! -L "/usr/lib/modules/$release" ]] || \
  fail "绝对 /lib 测试的主机逃逸路径已存在，无法证明隔离"
run_stage "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0 >/dev/null
cmp -s -- \
  "$package/rootfs/lib/modules/$release/kernel/drivers/test/test.ko" \
  "$root_mount/usr/lib/modules/$release/kernel/drivers/test/test.ko" || \
  fail "绝对 /lib 链接未在离线 rootfs 内解析"
[[ ! -e "/usr/lib/modules/$release" && ! -L "/usr/lib/modules/$release" ]] || \
  fail "绝对 /lib 链接导致写入逃逸到主机"
[[ "$(readlink -- "$root_mount/lib")" == /usr/lib ]] || fail "绝对 /lib 链接被修改"
grep -Fxq 'vendor boot script' "$boot_mount/boot.ini" || fail "绝对 /lib 测试修改了正式 boot.ini"

reset_targets
mkdir -p -- "$root_mount/usr/lib"
ln -s -- /usr/lib "$root_mount/lib"
expect_failure "绝对 /lib 失败回滚" "modules 复制失败" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 1 0 0 0
[[ -L "$root_mount/lib" && "$(readlink -- "$root_mount/lib")" == /usr/lib ]] || \
  fail "绝对 /lib 回滚修改了原链接"
[[ ! -e "$root_mount/usr/lib/modules/$release" ]] || fail "绝对 /lib 回滚残留 modules"
[[ ! -e "$boot_mount/boot.ini.test" && ! -e "$boot_mount/Image.mainline-test" && \
   ! -e "$boot_mount/rk3326-r46h-mainline-test.dtb" ]] || fail "绝对 /lib 回滚残留 BOOT payload"

# sudo 继承的敌对 TMPDIR 必须被忽略。
reset_targets
mkdir -p -- "$TEST_HOSTILE_TMPDIR"
chmod 0777 -- "$TEST_HOSTILE_TMPDIR"
printf 'do not trust me\n' > "$TEST_HOSTILE_TMPDIR/expected.tsv"
run_stage "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0 >/dev/null
grep -Fxq 'do not trust me' "$TEST_HOSTILE_TMPDIR/expected.tsv" || fail "脚本消费或覆盖了敌对 TMPDIR"
[[ -z "$(find "$TEST_HOSTILE_TMPDIR" -name 'r46h-stage-verify.*' -print -quit)" ]] || \
  fail "脚本在敌对 TMPDIR 创建了校验目录"

reset_targets
expect_failure "BOOT 边界" "BOOT 空间不足" \
  "$((boot_required_kib - 1))" "$root_required_kib" "$root_required_inodes" 0 0 0 0
assert_no_payload

reset_targets
expect_failure "rootfs 容量边界" "rootfs 空间不足" \
  "$boot_required_kib" "$((root_required_kib - 1))" "$root_required_inodes" 0 0 0 0
assert_no_payload

reset_targets
expect_failure "rootfs inode 边界" "rootfs inode 不足" \
  "$boot_required_kib" "$root_required_kib" "$((root_required_inodes - 1))" 0 0 0 0
assert_no_payload

# BOOT 目标若在预检后出现，no-replace 发布必须保留外来对象并只清理本次暂存文件。
reset_targets
TEST_RACE_BOOT_DEST=regular
expect_failure "BOOT 普通文件竞态" "BOOT 目标在原子发布时已存在" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0
grep -Fxq 'foreign boot file' "$boot_mount/boot.ini.test" || fail "BOOT 普通文件竞态覆盖或误删了外来文件"
[[ -z "$(find "$boot_mount" -name '.r46h-boot-stage.*' -print -quit)" ]] || fail "BOOT 普通文件竞态残留暂存文件"

reset_targets
TEST_RACE_BOOT_DEST=directory
expect_failure "BOOT 目录竞态" "BOOT 目标在原子发布时已存在" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0
[[ -f "$boot_mount/boot.ini.test/foreign-marker" ]] || fail "BOOT 目录竞态覆盖或误删了外来目录"
[[ -z "$(find "$boot_mount" -name '.r46h-boot-stage.*' -print -quit)" ]] || fail "BOOT 目录竞态残留暂存文件"

reset_targets
TEST_RACE_BOOT_DEST=symlink
expect_failure "BOOT 符号链接竞态" "BOOT 目标在原子发布时已存在" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0
[[ -L "$boot_mount/boot.ini.test" ]] || fail "BOOT 符号链接竞态替换或误删了外来链接"
[[ -f "$TEST_DIR/boot-race-escape/foreign-marker" ]] || fail "BOOT 符号链接竞态误删链接目标"
[[ -z "$(find "$TEST_DIR/boot-race-escape" -mindepth 1 -maxdepth 1 ! -name foreign-marker -print -quit)" ]] || \
  fail "BOOT 符号链接竞态发生写入逃逸"
[[ -z "$(find "$boot_mount" -name '.r46h-boot-stage.*' -print -quit)" ]] || fail "BOOT 符号链接竞态残留暂存文件"

# 写入中挂载身份变化时不得清理新挂载或底层目录，必须留下人工清理线索。
reset_targets
TEST_LOSE_IDENTITY_AT=boot-after-temp-write
expect_failure "BOOT 写入中换盘" "BOOT 挂载身份在写入前发生变化" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0
[[ -n "$(find "$boot_mount" -name '.r46h-boot-stage.*' -print -quit)" ]] || \
  fail "BOOT 换盘后错误清理了身份不明的暂存文件"
[[ ! -e "$boot_mount/boot.ini.test" ]] || fail "BOOT 换盘后发布了正式测试文件"
grep -Fq 'BOOT 挂载身份已变化，拒绝自动清理' "$TEST_DIR/failure.stderr" || \
  fail "BOOT 换盘失败未给出人工清理警告"

reset_targets
TEST_LOSE_IDENTITY_AT=root-after-module-copy
expect_failure "root 写入中掉线" "root 挂载身份在写入前发生变化" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0
[[ -n "$(find "$root_mount" -name '.r46h-modules-stage.*' -print -quit)" ]] || \
  fail "root 掉线后错误清理了身份不明的暂存目录"
[[ ! -e "$root_mount/lib/modules/$release" ]] || fail "root 掉线后发布了 modules"
[[ ! -e "$boot_mount/boot.ini.test" && ! -e "$boot_mount/Image.mainline-test" && \
   ! -e "$boot_mount/rk3326-r46h-mainline-test.dtb" ]] || fail "root 掉线后未回滚稳定 BOOT"
grep -Fq 'root 挂载身份已变化，拒绝自动清理' "$TEST_DIR/failure.stderr" || \
  fail "root 掉线失败未给出人工清理警告"

reset_targets
expect_failure "modules 部分复制失败" "modules 复制失败" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 1 0 0 0
assert_no_payload

reset_targets
TEST_REPLACE_MODULE_STAGE=1
expect_failure "modules 暂存目录被替换" "modules 复制失败" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0
replacement_stage=$(find "$root_mount" -type d -name '.r46h-modules-stage.*' -print -quit)
[[ -n "$replacement_stage" && -f "$replacement_stage/foreign-marker" ]] || \
  fail "暂存目录被替换后误删了非本次目录"
[[ ! -e "$root_mount/lib/modules/$release" ]] || fail "暂存目录被替换后发布了 modules"
[[ ! -e "$boot_mount/boot.ini.test" && ! -e "$boot_mount/Image.mainline-test" && \
   ! -e "$boot_mount/rk3326-r46h-mainline-test.dtb" ]] || fail "暂存目录被替换后未回滚 BOOT"

reset_targets
expect_failure "modules 目标目录竞态" "modules 目标在原子安装时已存在" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0 directory
race_destination="$root_mount/lib/modules/$release"
[[ -f "$race_destination/foreign-marker" ]] || fail "目录竞态误删了非本次目标"
[[ ! -e "$race_destination/modules.dep" ]] || fail "目录竞态把暂存目录嵌套进已有目标"
[[ -z "$(find "$root_mount" -name '.r46h-modules-stage.*' -print -quit)" ]] || \
  fail "目录竞态失败后残留 modules 暂存目录"
[[ ! -e "$boot_mount/boot.ini.test" && ! -e "$boot_mount/Image.mainline-test" && \
   ! -e "$boot_mount/rk3326-r46h-mainline-test.dtb" ]] || fail "目录竞态失败后残留 BOOT payload"
grep -Fxq 'vendor boot script' "$boot_mount/boot.ini" || fail "目录竞态修改了正式 boot.ini"

reset_targets
expect_failure "modules 目标符号链接竞态" "modules 目标在原子安装时已存在" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 0 symlink
race_destination="$root_mount/lib/modules/$release"
[[ -L "$race_destination" ]] || fail "符号链接竞态误删或替换了非本次目标"
[[ "$(readlink -- "$race_destination")" == "$TEST_DIR/module-race-escape" ]] || \
  fail "符号链接竞态修改了目标"
[[ -f "$TEST_DIR/module-race-escape/foreign-marker" ]] || fail "符号链接竞态误删了链接目标"
[[ -z "$(find "$TEST_DIR/module-race-escape" -mindepth 1 -maxdepth 1 ! -name foreign-marker -print -quit)" ]] || \
  fail "符号链接竞态写入逃逸路径"
[[ -z "$(find "$root_mount" -name '.r46h-modules-stage.*' -print -quit)" ]] || \
  fail "符号链接竞态失败后残留 modules 暂存目录"
[[ ! -e "$boot_mount/boot.ini.test" && ! -e "$boot_mount/Image.mainline-test" && \
   ! -e "$boot_mount/rk3326-r46h-mainline-test.dtb" ]] || fail "符号链接竞态失败后残留 BOOT payload"
grep -Fxq 'vendor boot script' "$boot_mount/boot.ini" || fail "符号链接竞态修改了正式 boot.ini"

reset_targets
expect_failure "BOOT 第二个文件写入失败" "BOOT 写入失败: Image.mainline-test" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 2 0 0
assert_no_payload

reset_targets
expect_failure "modules 写后校验失败" "modules 写入后摘要不匹配" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 1 0
assert_no_payload

reset_targets
expect_failure "sync 失败" "写入后 sync 失败" \
  "$boot_required_kib" "$root_required_kib" "$root_required_inodes" 0 0 0 1
assert_no_payload

printf 'PASS: stage-test-to-sd\n'
