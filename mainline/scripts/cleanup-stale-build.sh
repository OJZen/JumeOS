#!/usr/bin/env bash
set -Eeuo pipefail
export PATH=/usr/bin:/bin:/usr/sbin:/sbin

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly SCRIPT_DIR
MAINLINE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
readonly MAINLINE_DIR
REPO_ROOT="$(cd -- "$MAINLINE_DIR/.." && pwd -P)"
readonly REPO_ROOT
DOCKER_CLI=""
DOCKER_CONTEXT=""
DOCKER_EXEC_PATH=""
TRUSTED_USER_HOME=""

# shellcheck disable=SC1091
source "$MAINLINE_DIR/manifest.env"

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
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

require_fixed_executable() {
  local path=$1
  local owner_policy=$2
  local mode owner mode_value

  [[ -f "$path" && ! -L "$path" && -x "$path" ]] || die "不可信的固定可执行文件: $path"
  mode=$(host_file_mode "$path")
  owner=$(host_file_uid "$path")
  [[ "$mode" =~ ^[0-7]{3,4}$ && "$owner" =~ ^[0-9]+$ ]] ||
    die "无法核对固定可执行文件身份: $path"
  mode_value=$((8#$mode))
  (( (mode_value & 0022) == 0 )) || die "固定可执行文件可被组或其他用户写入: $path"
  case "$owner_policy" in
    root) [[ "$owner" == 0 ]] || die "固定可执行文件不是 root 所有: $path" ;;
    root-or-user)
      [[ "$owner" == 0 || "$owner" == "$(/usr/bin/id -u)" ]] ||
        die "固定可执行文件所有者不在信任边界内: $path"
      ;;
    *) die "内部错误：未知可执行文件所有者策略" ;;
  esac
}

resolve_trusted_docker() {
  local platform link_target link_owner

  platform=$(/usr/bin/uname -s)
  TRUSTED_USER_HOME=$(
    /usr/bin/env -i HOME=/var/empty PATH=/usr/bin:/bin LC_ALL=C LANG=C \
      /usr/bin/python3 -I -B -c 'import os, pwd; print(pwd.getpwuid(os.geteuid()).pw_dir)'
  ) || die "无法解析当前用户的固定 home"
  [[ "$TRUSTED_USER_HOME" == /* && -d "$TRUSTED_USER_HOME" && ! -L "$TRUSTED_USER_HOME" ]] ||
    die "当前用户 home 不在 Docker 信任边界内"

  case "$platform" in
    Darwin)
      [[ -L /usr/local/bin/docker ]] || die "缺少固定 Docker Desktop CLI 链接: /usr/local/bin/docker"
      link_target=$(/usr/bin/readlink /usr/local/bin/docker) || die "无法读取 Docker Desktop CLI 链接"
      [[ "$link_target" == /Applications/Docker.app/Contents/Resources/bin/docker ]] ||
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

resolve_trusted_docker
[[ "$(docker_cmd context show)" == "$DOCKER_CONTEXT" ]] || die "Docker context 与固定信任边界不一致"
docker_cmd info >/dev/null 2>&1 || die "固定 Docker daemon 未运行"

lock_dir="$MAINLINE_DIR/.cache/build.lock"
[[ -d "$lock_dir" && ! -L "$lock_dir" ]] || die "没有待恢复的构建锁"
lock_dir_inode=$(host_inode_id "$lock_dir")
[[ -n "$lock_dir_inode" ]] || die "无法记录构建锁目录 inode"
[[ -f "$lock_dir/pid" && ! -L "$lock_dir/pid" ]] || die "构建锁缺少 PID，拒绝自动清理"

read -r lock_pid < "$lock_dir/pid"
[[ "$lock_pid" =~ ^[1-9][0-9]*$ ]] || die "构建锁 PID 非法"
if kill -0 "$lock_pid" 2>/dev/null; then
  die "PID $lock_pid 仍存在，拒绝清理可能正在运行的构建"
fi

repo_id=$(printf '%s' "$REPO_ROOT" | shasum -a 256 | awk '{ print substr($1, 1, 16) }')
lock_volume=""
lock_volume_repo=""
lock_volume_token=""
volume_receipt_files=0
for receipt_name in volume volume-repo volume-token; do
  if [[ -e "$lock_dir/$receipt_name" || -L "$lock_dir/$receipt_name" ]]; then
    volume_receipt_files=$((volume_receipt_files + 1))
  fi
done
if (( volume_receipt_files != 0 )); then
  (( volume_receipt_files == 3 )) || die "构建锁的 volume 收据不完整，拒绝自动清理"
  [[ -f "$lock_dir/volume" && ! -L "$lock_dir/volume" &&
     -f "$lock_dir/volume-repo" && ! -L "$lock_dir/volume-repo" &&
     -f "$lock_dir/volume-token" && ! -L "$lock_dir/volume-token" ]] ||
    die "构建锁的 volume 收据文件类型非法"
  read -r lock_volume < "$lock_dir/volume"
  read -r lock_volume_repo < "$lock_dir/volume-repo"
  read -r lock_volume_token < "$lock_dir/volume-token"
  [[ "$lock_volume" == "$BUILD_VOLUME_PREFIX"-* &&
     "$lock_volume" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] ||
    die "构建锁内 volume 名非法"
  [[ "$lock_volume_repo" == "$repo_id" ]] || die "构建锁内 volume repo 标识不匹配"
  [[ "$lock_volume_token" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] ||
    die "构建锁内 volume token 非法"
fi

host_recorded_dir_matches "$lock_dir" "$lock_dir_inode" ||
  die "构建锁目录在 Docker 卷枚举前已变化，拒绝继续"
all_volumes=$(docker_cmd volume ls --format '{{.Name}}') ||
  die "无法完整列出固定 Docker daemon 的卷；保留构建锁"
while IFS= read -r volume; do
  [[ -n "$volume" ]] || continue
  [[ "$volume" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] ||
    die "Docker 返回非法卷名，拒绝继续: $volume"
  [[ "$volume" == "$BUILD_VOLUME_PREFIX"-* ]] || continue
  volume_metadata=$(docker_cmd volume inspect "$volume" \
    --format '{{ index .Labels "org.arkos4clone.r46h.repo" }}|{{ index .Labels "org.arkos4clone.r46h.temporary" }}|{{ index .Labels "org.arkos4clone.r46h.run-token" }}') ||
    die "无法复验临时卷标签: $volume"
  IFS='|' read -r volume_repo volume_temporary volume_token <<< "$volume_metadata"
  if [[ "$volume_repo" != "$repo_id" || "$volume_temporary" != true ]]; then
    [[ -z "$lock_volume" || "$volume" != "$lock_volume" ]] ||
      die "锁内卷存在但标签越界，拒绝删除构建锁: $volume"
    continue
  fi
  if [[ -n "$lock_volume" && "$volume" == "$lock_volume" ]]; then
    [[ "$volume_token" == "$lock_volume_token" ]] ||
      die "锁内卷 run-token 不匹配，拒绝删除构建锁: $volume"
  fi
  host_recorded_dir_matches "$lock_dir" "$lock_dir_inode" ||
    die "构建锁目录在 Docker 卷删除前已变化，拒绝继续"
  docker_cmd volume rm "$volume" >/dev/null
  printf 'removed stale volume: %s\n' "$volume"
done <<< "$all_volumes"

unexpected=$(find "$lock_dir" -mindepth 1 -maxdepth 1 \
  ! -name pid ! -name volume ! -name volume-repo ! -name volume-token -print -quit)
[[ -z "$unexpected" ]] || die "构建锁含未知文件，拒绝清理: $unexpected"
host_recorded_dir_matches "$lock_dir" "$lock_dir_inode" ||
  die "构建锁目录 identity 已变化，拒绝按路径删除"
rm -f -- "$lock_dir/pid" "$lock_dir/volume" "$lock_dir/volume-repo" "$lock_dir/volume-token"
rmdir -- "$lock_dir"
printf 'stale R46H build state cleaned\n'
