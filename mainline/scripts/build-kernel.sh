#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(/usr/bin/dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
MAINLINE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
readonly MAINLINE_DIR
REPO_ROOT="$(cd -- "$MAINLINE_DIR/.." && pwd -P)"
readonly REPO_ROOT
SCRIPT_PATH="$SCRIPT_DIR/$(/usr/bin/basename -- "${BASH_SOURCE[0]}")"
readonly SCRIPT_PATH
SNAPSHOT_HELPER="$SCRIPT_DIR/r46h-source-snapshot.py"
readonly SNAPSHOT_HELPER
readonly BUILD_SCRIPT_RELPATH=mainline/scripts/build-kernel.sh
readonly SNAPSHOT_HELPER_RELPATH=mainline/scripts/r46h-source-snapshot.py
readonly TRUSTED_GIT=/usr/bin/git
readonly TRUSTED_PYTHON=/usr/bin/python3
readonly SNAPSHOT_FD=9

BUILD_ID="v0.19-zram-product"
JOBS=4
ROOT_SPEC="/dev/mmcblk0p2"
REBUILD_BUILDER=0
LOCK_DIR=""
LOCK_OWNED=0
LOCK_DIR_INODE=""
WORK_VOLUME=""
WORK_VOLUME_RUN_TOKEN=""
WORK_VOLUME_REPO_ID=""
SNAPSHOT_TEMP_PATH=""
SNAPSHOT_FD_OPEN=0
SNAPSHOT_INITIAL_IDENTITY=""
SNAPSHOT_STATE=""
BUILDER_IID_DIR=""
BUILDER_IID_DIR_INODE=""
BUILDER_IID_FILE=""
SOURCE_GIT_COMMIT="unknown"
SOURCE_GIT_DIRTY="false"
SOURCE_SNAPSHOT_SHA256=""
DOCKER_CLI=""
DOCKER_CONTEXT=""
DOCKER_EXEC_PATH=""
TRUSTED_USER_HOME=""

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

usage() {
  cat <<'EOF'
在 Debian trixie/arm64 容器中构建并打包 R46H Linux 6.12 测试内核。

用法:
  mainline/scripts/build-kernel.sh [选项]

选项:
  --build-id ID          测试包标识，默认 v0.19-zram-product；必须与内核 LOCALVERSION 一致
  --jobs N               并行编译任务数，默认 4（适合 Docker Desktop 4 GiB）
  --root-spec SPEC       boot.ini.test 的 root=，默认 /dev/mmcblk0p2
  --rebuild-builder      不使用 Docker 层缓存重建 Debian 构建镜像
  -h, --help             显示帮助

Linux 源码、构建树和模块暂存区只写入一次性 Docker volume，退出时删除；
仓库仅保存可审查的源码以及 mainline/out 下的最终测试产物。
EOF
}

require_value() {
  local option=$1
  local value=${2:-}
  [[ -n "$value" ]] || die "$option 需要参数"
}

host_inode_id() {
  if /usr/bin/stat -f '%d:%i' -- "$1" >/dev/null 2>&1; then
    /usr/bin/stat -f '%d:%i' -- "$1"
  else
    /usr/bin/stat -c '%d:%i' -- "$1"
  fi
}

host_recorded_dir_matches() {
  local path=$1
  local expected=$2

  [[ -d "$path" && ! -L "$path" ]] || return 1
  [[ "$(host_inode_id "$path" 2>/dev/null)" == "$expected" ]]
}

volume_list_contains() {
  local expected=$1
  local listed=$2
  local volume

  while IFS= read -r volume; do
    [[ -n "$volume" ]] || continue
    if [[ "$volume" == "$expected" ]]; then
      return 0
    fi
  done <<< "$listed"
  return 1
}

host_file_mode() {
  if /usr/bin/stat -f '%Lp' -- "$1" >/dev/null 2>&1; then
    /usr/bin/stat -f '%Lp' -- "$1"
  else
    /usr/bin/stat -c '%a' -- "$1"
  fi
}

host_file_uid() {
  if /usr/bin/stat -f '%u' -- "$1" >/dev/null 2>&1; then
    /usr/bin/stat -f '%u' -- "$1"
  else
    /usr/bin/stat -c '%u' -- "$1"
  fi
}

host_file_nlink() {
  if /usr/bin/stat -f '%l' -- "$1" >/dev/null 2>&1; then
    /usr/bin/stat -f '%l' -- "$1"
  else
    /usr/bin/stat -c '%h' -- "$1"
  fi
}

host_file_identity_token() {
  local path=$1
  local token

  token=$(/usr/bin/stat -L -f '%d:%i:%Lp:%l:%u:%z' -- "$path" 2>/dev/null || true)
  if [[ "$token" =~ ^[0-9]+:[0-9]+:[0-7]{3,4}:[0-9]+:[0-9]+:[0-9]+$ ]]; then
    printf '%s\n' "$token"
    return 0
  fi
  token=$(/usr/bin/stat -L -c '%d:%i:%a:%h:%u:%s' -- "$path" 2>/dev/null || true)
  [[ "$token" =~ ^[0-9]+:[0-9]+:[0-7]{3,4}:[0-9]+:[0-9]+:[0-9]+$ ]] || return 1
  printf '%s\n' "$token"
}

require_fixed_executable() {
  local path=$1
  local owner_policy=$2
  local mode
  local mode_value
  local owner

  [[ -f "$path" && ! -L "$path" && -x "$path" ]] || die "不可信的固定可执行文件: $path"
  mode=$(host_file_mode "$path")
  owner=$(host_file_uid "$path")
  [[ "$mode" =~ ^[0-7]{3,4}$ && "$owner" =~ ^[0-9]+$ ]] || \
    die "无法核对固定可执行文件身份: $path"
  mode_value=$((8#$mode))
  (( (mode_value & 0022) == 0 )) || die "固定可执行文件可被组或其他用户写入: $path"
  case "$owner_policy" in
    root) [[ "$owner" == 0 ]] || die "固定可执行文件不是 root 所有: $path" ;;
    root-or-user)
      [[ "$owner" == 0 || "$owner" == "$(/usr/bin/id -u)" ]] || \
        die "固定可执行文件所有者不在信任边界内: $path"
      ;;
    *) die "内部错误：未知可执行文件所有者策略" ;;
  esac
}

safe_git() {
  /usr/bin/env -i \
    PATH=/usr/bin:/bin \
    LC_ALL=C \
    LANG=C \
    GIT_NO_REPLACE_OBJECTS=1 \
    GIT_CONFIG_NOSYSTEM=1 \
    GIT_CONFIG_GLOBAL=/dev/null \
    GIT_ATTR_NOSYSTEM=1 \
    GIT_OPTIONAL_LOCKS=0 \
    "$TRUSTED_GIT" --no-replace-objects \
      -c core.fsmonitor=false \
      -c core.untrackedCache=false \
      -c core.hooksPath=/dev/null \
      -c core.attributesFile=/dev/null \
      -c tar.umask=0002 \
      -C "$REPO_ROOT" "$@"
}

require_bootstrap_head_executable() {
  local relative=$1
  local named_path=$2
  local entry
  local owner
  local mode
  local links

  [[ "$named_path" == "$REPO_ROOT/$relative" ]] || die "来源入口不在固定仓库路径: $relative"
  [[ -f "$named_path" && ! -L "$named_path" ]] || die "来源入口不是普通文件: $relative"
  mode=$(host_file_mode "$named_path")
  owner=$(host_file_uid "$named_path")
  links=$(host_file_nlink "$named_path")
  [[ "$mode" == 755 && "$owner" == "$(/usr/bin/id -u)" && "$links" == 1 ]] || \
    die "来源入口 mode、owner 或 link count 不安全: $relative"
  entry=$(safe_git ls-tree "$BOOTSTRAP_GIT_COMMIT" -- "$relative") || \
    die "无法解析 HEAD 来源入口: $relative"
  [[ "$entry" =~ ^100755\ blob\ [0-9a-f]{40}$'\t'"$relative"$ ]] || \
    die "HEAD 来源入口不是唯一的 100755 blob: $relative"
  safe_git cat-file blob "$BOOTSTRAP_GIT_COMMIT:$relative" | /usr/bin/cmp -s - "$named_path" || \
    die "正在运行的来源入口与 HEAD blob 不一致: $relative"
}

bootstrap_python() {
  /usr/bin/env -i \
    HOME=/var/empty \
    PATH=/usr/bin:/bin \
    LC_ALL=C \
    LANG=C \
    "$TRUSTED_PYTHON" -I -B "$@"
}

safe_python() {
  [[ -n "$TRUSTED_USER_HOME" ]] || die "内部错误：固定用户 home 尚未解析"
  /usr/bin/env -i \
    HOME="$TRUSTED_USER_HOME" \
    PATH=/usr/bin:/bin \
    LC_ALL=C \
    LANG=C \
    "$TRUSTED_PYTHON" -I -B "$@"
}

snapshot_python() {
  require_bootstrap_head_executable "$SNAPSHOT_HELPER_RELPATH" "$SNAPSHOT_HELPER"
  safe_python "$SNAPSHOT_HELPER" "$@"
}

resolve_trusted_docker() {
  local platform
  local link_target
  local link_owner

  platform=$(/usr/bin/uname -s)
  TRUSTED_USER_HOME=$(bootstrap_python -c \
    'import os, pwd; print(pwd.getpwuid(os.geteuid()).pw_dir)') || \
    die "无法解析当前用户的固定 home"
  [[ "$TRUSTED_USER_HOME" == /* && -d "$TRUSTED_USER_HOME" && ! -L "$TRUSTED_USER_HOME" ]] || \
    die "当前用户 home 不在 Docker 信任边界内"

  case "$platform" in
    Darwin)
      [[ -L /usr/local/bin/docker ]] || die "缺少固定 Docker Desktop CLI 链接: /usr/local/bin/docker"
      link_target=$(/usr/bin/readlink /usr/local/bin/docker) || die "无法读取 Docker Desktop CLI 链接"
      [[ "$link_target" == /Applications/Docker.app/Contents/Resources/bin/docker ]] || \
        die "Docker Desktop CLI 链接目标不符合固定信任边界: $link_target"
      link_owner=$(/usr/bin/stat -f '%u' /usr/local/bin/docker)
      [[ "$link_owner" == 0 ]] || die "Docker Desktop CLI 链接不是 root 所有"
      DOCKER_CLI=/Applications/Docker.app/Contents/Resources/bin/docker
      DOCKER_CONTEXT=desktop-linux
      DOCKER_EXEC_PATH=/Applications/Docker.app/Contents/Resources/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
      require_fixed_executable "$DOCKER_CLI" root-or-user
      ;;
    Linux)
      DOCKER_CLI=/usr/bin/docker
      DOCKER_CONTEXT=default
      DOCKER_EXEC_PATH=/usr/bin:/bin:/usr/sbin:/sbin
      require_fixed_executable "$DOCKER_CLI" root
      ;;
    *) die "不支持的 Docker 宿主平台: $platform" ;;
  esac
  readonly DOCKER_CLI DOCKER_CONTEXT DOCKER_EXEC_PATH TRUSTED_USER_HOME
}

docker_cmd() {
  /usr/bin/env -i \
    HOME="$TRUSTED_USER_HOME" \
    PATH="$DOCKER_EXEC_PATH" \
    LC_ALL=C \
    LANG=C \
    DOCKER_CONFIG="$TRUSTED_USER_HOME/.docker" \
    "$DOCKER_CLI" --context "$DOCKER_CONTEXT" "$@"
}

verify_snapshot_fd() {
  snapshot_python verify \
    --fd "$SNAPSHOT_FD" \
    --state "$SNAPSHOT_STATE" \
    --sha256 "$SOURCE_SNAPSHOT_SHA256"
}

parse_snapshot_receipt() {
  local receipt=$1
  local line
  local name
  local value
  local seen='|'
  local field_count=0

  while IFS= read -r line; do
    [[ -n "$line" && "$line" == *=* ]] || die "来源快照 receipt 含非法行"
    name=${line%%=*}
    value=${line#*=}
    [[ -n "$value" && "$seen" != *"|$name|"* ]] || die "来源快照 receipt 字段重复或为空: $name"
    seen="$seen$name|"
    field_count=$((field_count + 1))
    case "$name" in
      format_version) [[ "$value" == 1 ]] || die "来源快照 receipt 版本不支持" ;;
      source_git_commit) SOURCE_GIT_COMMIT=$value ;;
      source_snapshot_sha256) SOURCE_SNAPSHOT_SHA256=$value ;;
      snapshot_state) SNAPSHOT_STATE=$value ;;
      KERNEL_VERSION) KERNEL_VERSION=$value ;;
      KERNEL_TARBALL) KERNEL_TARBALL=$value ;;
      KERNEL_URL) KERNEL_URL=$value ;;
      KERNEL_MIRROR_URL) KERNEL_MIRROR_URL=$value ;;
      KERNEL_SHA256) KERNEL_SHA256=$value ;;
      KERNEL_LOCALVERSION) KERNEL_LOCALVERSION=$value ;;
      KERNEL_PATCH_LAST) KERNEL_PATCH_LAST=$value ;;
      BUILDER_IMAGE) BUILDER_IMAGE=$value ;;
      BUILD_VOLUME_PREFIX) BUILD_VOLUME_PREFIX=$value ;;
      *) die "来源快照 receipt 含未知字段: $name" ;;
    esac
  done <<< "$receipt"
  [[ "$field_count" == 13 ]] || die "来源快照 receipt 字段数错误: $field_count"
  for name in \
    format_version source_git_commit source_snapshot_sha256 snapshot_state \
    KERNEL_VERSION KERNEL_TARBALL KERNEL_URL KERNEL_MIRROR_URL KERNEL_SHA256 \
    KERNEL_LOCALVERSION KERNEL_PATCH_LAST BUILDER_IMAGE BUILD_VOLUME_PREFIX; do
    [[ "$seen" == *"|$name|"* ]] || die "来源快照 receipt 缺少字段: $name"
  done
}

while (( $# > 0 )); do
  case "$1" in
    --build-id)
      require_value "$1" "${2:-}"
      BUILD_ID=$2
      shift 2
      ;;
    --jobs)
      require_value "$1" "${2:-}"
      JOBS=$2
      shift 2
      ;;
    --root-spec)
      require_value "$1" "${2:-}"
      ROOT_SPEC=$2
      shift 2
      ;;
    --rebuild-builder)
      REBUILD_BUILDER=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "未知参数: $1"
      ;;
  esac
done

[[ "$BUILD_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "非法 --build-id: $BUILD_ID"
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || die "--jobs 必须是正整数"
(( JOBS <= 32 )) || die "--jobs 不能大于 32"
[[ "$ROOT_SPEC" =~ ^[A-Za-z0-9_./:=+-]+$ ]] || die "非法 --root-spec: $ROOT_SPEC"

require_fixed_executable "$TRUSTED_GIT" root
require_fixed_executable "$TRUSTED_PYTHON" root
BOOTSTRAP_GIT_COMMIT=$(safe_git rev-parse --verify 'HEAD^{commit}' 2>/dev/null) || \
  die "无法通过固定 Git 解析当前 HEAD"
[[ "$BOOTSTRAP_GIT_COMMIT" =~ ^[0-9a-f]{40}$ ]] || die "当前 HEAD 不是完整 SHA-1 commit ID"
readonly BOOTSTRAP_GIT_COMMIT
require_bootstrap_head_executable "$BUILD_SCRIPT_RELPATH" "$SCRIPT_PATH"
require_bootstrap_head_executable "$SNAPSHOT_HELPER_RELPATH" "$SNAPSHOT_HELPER"
resolve_trusted_docker

/bin/mkdir -p -- "$MAINLINE_DIR/.cache/kernel" "$MAINLINE_DIR/out"
LOCK_DIR="$MAINLINE_DIR/.cache/build.lock"

cleanup() {
  local status=$?
  local volume_cleanup_failed=0
  local cleanup_volume_list=""
  local cleanup_volume_metadata=""
  trap - EXIT INT TERM

  if [[ -n "$WORK_VOLUME" ]]; then
    if ! cleanup_volume_list=$(docker_cmd volume ls --format '{{.Name}}' 2>/dev/null); then
      printf 'warning: 无法列出固定 Docker daemon 的卷，拒绝删除构建锁\n' >&2
      volume_cleanup_failed=1
      (( status != 0 )) || status=1
    elif ! volume_list_contains "$WORK_VOLUME" "$cleanup_volume_list"; then
      : # A successful complete listing proves that the planned volume is absent.
    elif ! cleanup_volume_metadata=$(docker_cmd volume inspect "$WORK_VOLUME" \
      --format '{{ index .Labels "org.arkos4clone.r46h.run-token" }}|{{ index .Labels "org.arkos4clone.r46h.repo" }}|{{ index .Labels "org.arkos4clone.r46h.temporary" }}' \
      2>/dev/null); then
      printf 'warning: 无法复验临时 Docker volume，拒绝删除: %s\n' "$WORK_VOLUME" >&2
      volume_cleanup_failed=1
      (( status != 0 )) || status=1
    elif [[ "$cleanup_volume_metadata" != \
      "$WORK_VOLUME_RUN_TOKEN|$WORK_VOLUME_REPO_ID|true" ]]; then
      printf 'warning: 临时 Docker volume 所有权复验失败，拒绝删除: %s\n' "$WORK_VOLUME" >&2
      volume_cleanup_failed=1
      (( status != 0 )) || status=1
    elif ! docker_cmd volume rm "$WORK_VOLUME" >/dev/null 2>&1; then
      printf 'warning: 无法删除临时 Docker volume: %s\n' "$WORK_VOLUME" >&2
      printf 'warning: 确认旧进程结束后运行 mainline/scripts/cleanup-stale-build.sh\n' >&2
      volume_cleanup_failed=1
      (( status != 0 )) || status=1
    fi
  fi
  if (( SNAPSHOT_FD_OPEN == 1 )); then
    if [[ -n "$SNAPSHOT_TEMP_PATH" ]] && \
       { ! (require_bootstrap_head_executable \
              "$SNAPSHOT_HELPER_RELPATH" "$SNAPSHOT_HELPER") >/dev/null 2>&1 || \
         ! safe_python "$SNAPSHOT_HELPER" unlink-owned \
          --repo-root "$REPO_ROOT" \
          --snapshot-path "$SNAPSHOT_TEMP_PATH" \
          --fd "$SNAPSHOT_FD" \
          --initial-identity "$SNAPSHOT_INITIAL_IDENTITY" >/dev/null 2>&1; }; then
      printf 'warning: 来源快照名称身份不匹配；为避免误删竞争者，不做路径清理\n' >&2
    fi
    exec 9>&-
    SNAPSHOT_FD_OPEN=0
  fi
  if [[ -n "$BUILDER_IID_DIR" && -n "$BUILDER_IID_DIR_INODE" ]] &&
     host_recorded_dir_matches "$BUILDER_IID_DIR" "$BUILDER_IID_DIR_INODE"; then
    /bin/rm -rf -- "$BUILDER_IID_DIR"
  fi
  if (( volume_cleanup_failed == 0 && LOCK_OWNED == 1 )); then
    if [[ -z "$LOCK_DIR_INODE" || "$LOCK_DIR" != "$MAINLINE_DIR/.cache/build.lock" ]] || \
       ! host_recorded_dir_matches "$LOCK_DIR" "$LOCK_DIR_INODE"; then
      printf 'warning: 构建锁目录 identity 已变化，拒绝按路径删除\n' >&2
      (( status != 0 )) || status=1
    else
      /bin/rm -f -- \
        "$LOCK_DIR/pid" "$LOCK_DIR/volume" "$LOCK_DIR/volume-repo" \
        "$LOCK_DIR/volume-token"
      if ! /bin/rmdir -- "$LOCK_DIR"; then
        printf 'warning: 构建锁含未识别内容，拒绝递归清理: %s\n' "$LOCK_DIR" >&2
        (( status != 0 )) || status=1
      fi
    fi
  fi

  exit "$status"
}
trap cleanup EXIT INT TERM

if ! /bin/mkdir -- "$LOCK_DIR" 2>/dev/null; then
  die "已有 R46H 构建在运行，或存在过期锁；确认旧进程已退出后运行 mainline/scripts/cleanup-stale-build.sh"
fi
LOCK_OWNED=1
LOCK_DIR_INODE=$(host_inode_id "$LOCK_DIR")
[[ -n "$LOCK_DIR_INODE" ]] || die "无法记录构建锁目录 inode"
printf '%s\n' "$$" > "$LOCK_DIR/pid"

# The helper unlinks this unique name immediately after proving that it still
# names FD 9. All later consumers share this one anonymous inode and rewind the
# same open file description; cleanup never removes a snapshot by pathname.
SNAPSHOT_TEMP_PATH=$(/usr/bin/mktemp "$MAINLINE_DIR/.cache/r46h-build-input.XXXXXX")
[[ -f "$SNAPSHOT_TEMP_PATH" && ! -L "$SNAPSHOT_TEMP_PATH" ]] || \
  die "mktemp 未生成普通来源快照文件"
SNAPSHOT_INITIAL_IDENTITY=$(host_file_identity_token "$SNAPSHOT_TEMP_PATH") || \
  die "无法记录来源快照 mktemp identity"
[[ "$SNAPSHOT_INITIAL_IDENTITY" == *:600:1:"$(/usr/bin/id -u)":0 ]] || \
  die "来源快照 mktemp identity 不是当前用户的空 mode-0600 文件"
readonly SNAPSHOT_INITIAL_IDENTITY
if ! exec 9<> "$SNAPSHOT_TEMP_PATH"; then
  die "无法打开来源快照 mktemp 文件"
fi
SNAPSHOT_FD_OPEN=1
snapshot_open_fd_identity=$(
  snapshot_python fd-identity --fd "$SNAPSHOT_FD"
) || die "无法读取来源快照 FD identity"
snapshot_open_path_identity=$(host_file_identity_token "$SNAPSHOT_TEMP_PATH") || \
  die "无法复验来源快照路径 identity"
[[ "$snapshot_open_fd_identity" == "$SNAPSHOT_INITIAL_IDENTITY" &&
   "$snapshot_open_path_identity" == "$SNAPSHOT_INITIAL_IDENTITY" ]] || \
  die "来源快照在 mktemp 与 open 之间被替换"
unset snapshot_open_fd_identity snapshot_open_path_identity
snapshot_receipt=$(
  snapshot_python create \
    --repo-root "$REPO_ROOT" \
    --running-script "$SCRIPT_PATH" \
    --snapshot-path "$SNAPSHOT_TEMP_PATH" \
    --fd "$SNAPSHOT_FD" \
    --initial-identity "$SNAPSHOT_INITIAL_IDENTITY"
)
SNAPSHOT_TEMP_PATH=""
parse_snapshot_receipt "$snapshot_receipt"
[[ "$SOURCE_GIT_COMMIT" == "$BOOTSTRAP_GIT_COMMIT" ]] || \
  die "来源 helper 的 HEAD 与入口 bootstrap HEAD 不一致"
[[ "$SOURCE_GIT_COMMIT" =~ ^[0-9a-f]{40}$ ]] || die "来源 commit 非法"
[[ "$SOURCE_SNAPSHOT_SHA256" =~ ^[0-9a-f]{64}$ ]] || die "来源快照 SHA256 非法"
[[ "$SNAPSHOT_STATE" =~ ^[0-9]+(:[0-9]+){8}$ ]] || die "来源快照 FD state 非法"
readonly SOURCE_GIT_COMMIT SOURCE_GIT_DIRTY SOURCE_SNAPSHOT_SHA256 SNAPSHOT_STATE
verify_snapshot_fd

[[ "$KERNEL_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "manifest 中的内核版本非法"
[[ "$KERNEL_TARBALL" == "linux-$KERNEL_VERSION.tar.xz" ]] || die "manifest 中的压缩包名称非法"
[[ "$KERNEL_URL" == */"$KERNEL_TARBALL" ]] || die "manifest 中的官方 URL 非法"
[[ "$KERNEL_MIRROR_URL" == */"$KERNEL_TARBALL" ]] || die "manifest 中的镜像 URL 非法"
[[ "$KERNEL_SHA256" =~ ^[0-9a-f]{64}$ ]] || die "manifest 中的 SHA256 非法"
[[ "$KERNEL_LOCALVERSION" =~ ^-[A-Za-z0-9._-]+$ ]] || die "manifest 中的 LOCALVERSION 非法"
[[ "$KERNEL_PATCH_LAST" =~ ^[0-9]{4}$ && "$KERNEL_PATCH_LAST" != 0000 ]] || \
  die "manifest 中的末尾补丁编号非法"
[[ "$KERNEL_LOCALVERSION" == "-r46h-mainline-$BUILD_ID" ]] || \
  die "--build-id 与 manifest LOCALVERSION 不一致: $BUILD_ID / $KERNEL_LOCALVERSION"
[[ "$BUILDER_IMAGE" =~ ^[A-Za-z0-9][A-Za-z0-9_./:-]*$ ]] || die "manifest 中的 builder image 非法"
[[ "$BUILD_VOLUME_PREFIX" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || die "manifest 中的 Docker volume 前缀非法"

[[ "$(docker_cmd context show)" == "$DOCKER_CONTEXT" ]] || die "Docker context 与固定信任边界不一致"
docker_cmd info >/dev/null 2>&1 || die "固定 Docker daemon 未运行"
DOCKER_CLIENT_VERSION=$(docker_cmd version --format '{{.Client.Version}}') || \
  die "无法读取固定 Docker client version"
DOCKER_SERVER_VERSION=$(docker_cmd version --format '{{.Server.Version}}') || \
  die "无法读取固定 Docker server version"
[[ "$DOCKER_CONTEXT" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$ ]] || die "固定 Docker context 非法"
[[ "$DOCKER_CLIENT_VERSION" =~ ^[0-9][A-Za-z0-9.+_-]{0,63}$ ]] || die "Docker client version 非法"
[[ "$DOCKER_SERVER_VERSION" =~ ^[0-9][A-Za-z0-9.+_-]{0,63}$ ]] || die "Docker server version 非法"
readonly DOCKER_CLIENT_VERSION DOCKER_SERVER_VERSION

docker_build_args=(
  --platform linux/arm64
  --file mainline/Dockerfile
  --tag "$BUILDER_IMAGE"
)
if (( REBUILD_BUILDER == 1 )); then
  docker_build_args+=(--no-cache)
fi
BUILDER_IID_DIR=$(/usr/bin/mktemp -d "$MAINLINE_DIR/.cache/r46h-builder-iid.XXXXXX")
BUILDER_IID_DIR_INODE=$(host_inode_id "$BUILDER_IID_DIR")
[[ -n "$BUILDER_IID_DIR_INODE" ]] || die "无法记录 builder iid 私有目录 inode"
/bin/chmod 0700 "$BUILDER_IID_DIR"
BUILDER_IID_FILE="$BUILDER_IID_DIR/image-id"
[[ ! -e "$BUILDER_IID_FILE" && ! -L "$BUILDER_IID_FILE" ]] || die "builder iid 文件意外存在"
docker_build_args+=(--iidfile "$BUILDER_IID_FILE")
verify_snapshot_fd
docker_cmd build "${docker_build_args[@]}" - <&9
verify_snapshot_fd
host_recorded_dir_matches "$BUILDER_IID_DIR" "$BUILDER_IID_DIR_INODE" ||
  die "builder iid 私有目录在构建期间被替换"
[[ -f "$BUILDER_IID_FILE" && ! -L "$BUILDER_IID_FILE" ]] || die "Docker 未生成合法 builder iid 文件"
builder_image_id=$(/usr/bin/tr -d '[:space:]' < "$BUILDER_IID_FILE")
[[ "$builder_image_id" =~ ^sha256:[0-9a-f]{64}$ ]] || die "Docker 未返回合法的 builder image ID"

volume_run_token="$(/bin/date -u +%Y%m%dT%H%M%SZ)-$$-$RANDOM-$RANDOM"
candidate_volume="$BUILD_VOLUME_PREFIX-$BUILD_ID-$volume_run_token"
repo_id=$(printf '%s' "$REPO_ROOT" | /usr/bin/shasum -a 256 | /usr/bin/awk '{ print substr($1, 1, 16) }')
WORK_VOLUME="$candidate_volume"
WORK_VOLUME_RUN_TOKEN="$volume_run_token"
WORK_VOLUME_REPO_ID="$repo_id"
host_recorded_dir_matches "$LOCK_DIR" "$LOCK_DIR_INODE" || \
  die "构建锁目录在写入 volume 收据前被替换"
printf '%s\n' "$WORK_VOLUME" > "$LOCK_DIR/volume"
printf '%s\n' "$WORK_VOLUME_REPO_ID" > "$LOCK_DIR/volume-repo"
printf '%s\n' "$WORK_VOLUME_RUN_TOKEN" > "$LOCK_DIR/volume-token"
created_volume=$(docker_cmd volume create \
  --label org.arkos4clone.r46h.temporary=true \
  --label org.arkos4clone.r46h.repo="$repo_id" \
  --label org.arkos4clone.r46h.pid="$$" \
  --label org.arkos4clone.r46h.build-id="$BUILD_ID" \
  --label org.arkos4clone.r46h.run-token="$volume_run_token" \
  "$candidate_volume")
[[ "$created_volume" == "$candidate_volume" ]] || die "Docker 返回了意外的临时卷名称"
verified_volume_token=$(docker_cmd volume inspect "$candidate_volume" \
  --format '{{ index .Labels "org.arkos4clone.r46h.run-token" }}')
verified_volume_repo=$(docker_cmd volume inspect "$candidate_volume" \
  --format '{{ index .Labels "org.arkos4clone.r46h.repo" }}')
[[ "$verified_volume_token" == "$volume_run_token" && "$verified_volume_repo" == "$repo_id" ]] || {
  printf 'warning: 未能证明临时 Docker volume 属于本次构建，不会自动删除: %s\n' "$candidate_volume" >&2
  die "Docker volume 所有权标签不一致"
}

verify_snapshot_fd
# The quoted command is evaluated by the container's /bin/bash; its variables
# must not expand in the host shell.
# shellcheck disable=SC2016
docker_cmd run --rm -i \
  --platform linux/arm64 \
  --env BUILD_ID="$BUILD_ID" \
  --env HOST_GID="$(/usr/bin/id -g)" \
  --env HOST_UID="$(/usr/bin/id -u)" \
  --env JOBS="$JOBS" \
  --env BUILDER_IMAGE="$BUILDER_IMAGE" \
  --env BUILDER_IMAGE_ID="$builder_image_id" \
  --env DOCKER_CLIENT_VERSION="$DOCKER_CLIENT_VERSION" \
  --env DOCKER_CONTEXT="$DOCKER_CONTEXT" \
  --env DOCKER_SERVER_VERSION="$DOCKER_SERVER_VERSION" \
  --env KERNEL_LOCALVERSION="$KERNEL_LOCALVERSION" \
  --env KERNEL_PATCH_LAST="$KERNEL_PATCH_LAST" \
  --env KERNEL_MIRROR_URL="$KERNEL_MIRROR_URL" \
  --env KERNEL_SHA256="$KERNEL_SHA256" \
  --env KERNEL_TARBALL="$KERNEL_TARBALL" \
  --env KERNEL_URL="$KERNEL_URL" \
  --env KERNEL_VERSION="$KERNEL_VERSION" \
  --env ROOT_SPEC="$ROOT_SPEC" \
  --env SOURCE_GIT_COMMIT="$SOURCE_GIT_COMMIT" \
  --env SOURCE_GIT_DIRTY="$SOURCE_GIT_DIRTY" \
  --env SOURCE_SNAPSHOT_SHA256="$SOURCE_SNAPSHOT_SHA256" \
  --volume "$WORK_VOLUME:/work" \
  --volume "$MAINLINE_DIR/.cache/kernel:/cache" \
  --volume "$MAINLINE_DIR/out:/output" \
  "$builder_image_id" \
  /bin/bash -c \
  'set -euo pipefail; umask 077; cat > /work/mainline-source.tar; printf "%s  %s\n" "$SOURCE_SNAPSHOT_SHA256" /work/mainline-source.tar | sha256sum -c - >/dev/null; mkdir -p /work/input; tar -xf /work/mainline-source.tar -C /work/input; exec /work/input/mainline/scripts/build-in-container.sh' \
  <&9
verify_snapshot_fd

printf '完成。测试包位于 %s/out/r46h-mainline-test-%s.tar.gz\n' "$MAINLINE_DIR" "$BUILD_ID"
