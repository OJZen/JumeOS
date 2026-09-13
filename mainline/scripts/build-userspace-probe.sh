#!/usr/bin/env bash
# The preserved code below the deliberate freeze gate is unreachable by design.
# shellcheck disable=SC2317
set -Eeuo pipefail
umask 022

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
MAINLINE_DIR=$(cd "$SCRIPT_DIR/.." && pwd -P)
REPO_ROOT=$(cd "$MAINLINE_DIR/.." && pwd -P)
OUTPUT_ROOT=$MAINLINE_DIR/out
CACHE_ROOT=$OUTPUT_ROOT/.cache
LIVE_SOURCE_DIR=$MAINLINE_DIR/userspace-probe
LIVE_PACKAGER=$SCRIPT_DIR/package-userspace-probe-bundle.py
LIVE_CARD_PROFILE=$MAINLINE_DIR/deploy/profiles/hl-r46h-v22-g92-v1.json
LIVE_CURRENT_BASELINE=$MAINLINE_DIR/deploy/baselines/v0.8-bootloader-handoff.json
LIVE_STAGE_TEMPLATE=$MAINLINE_DIR/deploy/templates/stage-easyroms-macos.sh.in

readonly PROBE_ID=debian13-mesa-v0.2
readonly RUNTIME_IMAGE=arkos4clone/r46h-userspace-probe:$PROBE_ID
readonly TOOL_IMAGE=arkos4clone/r46h-squashfs-builder:trixie-arm64
readonly OUTPUT_NAME=r46h-easyroms-debian13-mesa-probe-v0.2
readonly OUTPUT_DIR=$OUTPUT_ROOT/$OUTPUT_NAME
readonly SQUASHFS_NAME=r46h-userspace-probe-$PROBE_ID.squashfs
readonly SOURCE_DATE_EPOCH=1785974400

INPUT_PATHS=(
  mainline/userspace-probe
  mainline/scripts/build-userspace-probe.sh
  mainline/scripts/package-userspace-probe-bundle.py
  mainline/deploy/templates/stage-easyroms-macos.sh.in
  mainline/deploy/baselines/v0.8-bootloader-handoff.json
  mainline/deploy/profiles/hl-r46h-v22-g92-v1.json
)
readonly INPUT_PATHS

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

die "userspace probe v0.2 build is frozen after the raw exFAT verification failure; see mainline/deploy/EXFAT-FSKIT-POSTMORTEM.md"

for command in docker git shasum file mktemp python3 sed tar; do
  command -v "$command" >/dev/null 2>&1 || die "缺少命令: $command"
done

[[ -d "$LIVE_SOURCE_DIR" && ! -L "$LIVE_SOURCE_DIR" ]] || die "userspace probe 源目录无效"
for input in "$LIVE_PACKAGER" "$LIVE_CARD_PROFILE" "$LIVE_CURRENT_BASELINE" "$LIVE_STAGE_TEMPLATE"; do
  [[ -f "$input" && ! -L "$input" ]] || die "构建输入无效: $input"
done
[[ ! -e "$OUTPUT_DIR" && ! -L "$OUTPUT_DIR" ]] || die "输出目录已存在: $OUTPUT_DIR"

source_commit=$(GIT_NO_REPLACE_OBJECTS=1 git -C "$REPO_ROOT" rev-parse --verify 'HEAD^{commit}')
[[ "$source_commit" =~ ^[0-9a-f]{40}$ ]] || die "源码提交 ID 非法"
assert_repository_binding() {
  local current_commit dirty

  current_commit=$(GIT_NO_REPLACE_OBJECTS=1 git -C "$REPO_ROOT" rev-parse --verify 'HEAD^{commit}') ||
    die "无法复核源码提交"
  [[ "$current_commit" == "$source_commit" ]] || die "构建期间 HEAD 已变化"
  dirty=$(git -C "$REPO_ROOT" status --porcelain --untracked-files=all -- "${INPUT_PATHS[@]}") ||
    die "无法复核源码工作区"
  [[ -z "$dirty" ]] || die "canonical 探针要求所有构建输入来自 clean Git HEAD"
}
assert_repository_binding

mkdir -p "$CACHE_ROOT"
work_dir=$(mktemp -d "$CACHE_ROOT/.r46h-userspace-probe.XXXXXX")
probe_input=$work_dir/probe-input
source_snapshot=$work_dir/source-snapshot
source_archive=$work_dir/source.tar
mkdir -m 0700 "$probe_input" "$source_snapshot"
container_id=""

cleanup() {
  local status=$?

  trap - EXIT
  if [[ -n "$container_id" ]]; then
    docker rm -f "$container_id" >/dev/null 2>&1 || true
  fi
  if [[ -d "$work_dir" && "$work_dir" == "$CACHE_ROOT"/.r46h-userspace-probe.* ]]; then
    rm -rf -- "$work_dir"
  fi
  exit "$status"
}
trap cleanup EXIT

GIT_NO_REPLACE_OBJECTS=1 git -C "$REPO_ROOT" archive \
  --format=tar --output="$source_archive" "$source_commit" -- "${INPUT_PATHS[@]}"
[[ -f "$source_archive" && ! -L "$source_archive" ]] || die "无法生成 Git 源码归档"
tar -xf "$source_archive" -C "$source_snapshot"
source_archive_sha256=$(shasum -a 256 "$source_archive" | awk '{print $1}')
[[ "$source_archive_sha256" =~ ^[0-9a-f]{64}$ ]] || die "源码归档 SHA-256 非法"

SNAPSHOT_MAINLINE=$source_snapshot/mainline
SOURCE_DIR=$SNAPSHOT_MAINLINE/userspace-probe
PACKAGER=$SNAPSHOT_MAINLINE/scripts/package-userspace-probe-bundle.py
CARD_PROFILE=$SNAPSHOT_MAINLINE/deploy/profiles/hl-r46h-v22-g92-v1.json
CURRENT_BASELINE=$SNAPSHOT_MAINLINE/deploy/baselines/v0.8-bootloader-handoff.json
STAGE_TEMPLATE=$SNAPSHOT_MAINLINE/deploy/templates/stage-easyroms-macos.sh.in
[[ -d "$SOURCE_DIR" && ! -L "$SOURCE_DIR" ]] || die "Git 快照缺少 userspace probe"
for input in "$PACKAGER" "$CARD_PROFILE" "$CURRENT_BASELINE" "$STAGE_TEMPLATE"; do
  [[ -f "$input" && ! -L "$input" ]] || die "Git 快照构建输入无效: $input"
done

docker_context=$(docker context show)
docker_client=$(docker version --format '{{.Client.Version}}')
docker_server=$(docker version --format '{{.Server.Version}}')
[[ "$docker_context" =~ ^[A-Za-z0-9._-]+$ ]] || die "Docker context 非法"
[[ "$docker_client" =~ ^[0-9A-Za-z._+-]+$ ]] || die "Docker client 版本非法"
[[ "$docker_server" =~ ^[0-9A-Za-z._+-]+$ ]] || die "Docker server 版本非法"

printf 'Building Debian 13 Mesa probe runtime...\n'
docker build \
  --platform linux/arm64 \
  --file "$SOURCE_DIR/Dockerfile" \
  --tag "$RUNTIME_IMAGE" \
  "$SOURCE_DIR"

printf 'Building pinned gzip SquashFS tool image...\n'
docker build \
  --platform linux/arm64 \
  --file "$SOURCE_DIR/Squashfs.Dockerfile" \
  --tag "$TOOL_IMAGE" \
  "$SOURCE_DIR"

runtime_image_id=$(docker image inspect "$RUNTIME_IMAGE" --format '{{.Id}}')
tool_image_id=$(docker image inspect "$TOOL_IMAGE" --format '{{.Id}}')
[[ "$runtime_image_id" =~ ^sha256:[0-9a-f]{64}$ ]] || die "runtime image ID 非法"
[[ "$tool_image_id" =~ ^sha256:[0-9a-f]{64}$ ]] || die "tool image ID 非法"

docker run --rm --platform linux/arm64 --entrypoint /usr/bin/dpkg-query "$RUNTIME_IMAGE" \
  -W '-f=${binary:Package}\t${Version}\n' > "$probe_input/PACKAGES.tsv"
LC_ALL=C sort -o "$probe_input/PACKAGES.tsv" "$probe_input/PACKAGES.tsv"

docker run --rm --platform linux/arm64 --entrypoint /usr/bin/ldd "$RUNTIME_IMAGE" \
  /usr/local/libexec/r46h-gles2-fbo-probe > "$probe_input/LDD.txt"
if grep -Eiq 'libMali|not found' "$probe_input/LDD.txt"; then
  die "probe 动态依赖包含 libMali 或缺失库"
fi

docker run --rm --platform linux/arm64 --entrypoint /usr/bin/test "$RUNTIME_IMAGE" \
  -e /usr/lib/aarch64-linux-gnu/dri/panfrost_dri.so ||
  die "Debian 13 runtime 缺少 panfrost_dri.so"
docker run --rm --platform linux/arm64 --entrypoint /usr/bin/test "$RUNTIME_IMAGE" \
  -x /usr/bin/setpriv || die "Debian 13 runtime 缺少 setpriv"

container_id=$(docker create --platform linux/arm64 "$RUNTIME_IMAGE")
[[ "$container_id" =~ ^[0-9a-f]{64}$ ]] || die "无法创建 runtime export 容器"
docker cp "$container_id:/usr/local/libexec/r46h-gles2-fbo-probe" \
  "$work_dir/r46h-gles2-fbo-probe"
docker export --output "$work_dir/rootfs.tar" "$container_id"
docker rm "$container_id" >/dev/null
container_id=""

file "$work_dir/r46h-gles2-fbo-probe" > "$probe_input/PROBE-FILE.txt"
grep -Eq 'ELF 64-bit.*ARM aarch64' "$probe_input/PROBE-FILE.txt" ||
  die "probe 不是 AArch64 ELF"

docker run --rm --platform linux/arm64 \
  --volume "$work_dir:/work" \
  --volume "$probe_input:/output" \
  "$TOOL_IMAGE" \
  /bin/bash -Eeuo pipefail -c '
    mkdir -m 0755 /work/rootfs
    tar -xf /work/rootfs.tar -C /work/rootfs
    for directory in dev proc sys tmp; do
      find "/work/rootfs/$directory" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
    done
    chmod 1777 /work/rootfs/tmp
    mksquashfs /work/rootfs "/output/'"$SQUASHFS_NAME"'" \
      -noappend -all-root -no-xattrs -comp gzip -b 131072 \
      -all-time '"$SOURCE_DATE_EPOCH"' -mkfs-time '"$SOURCE_DATE_EPOCH"'
    unsquashfs -s "/output/'"$SQUASHFS_NAME"'" > /output/SQUASHFS-INFO.txt
    unsquashfs -ll "/output/'"$SQUASHFS_NAME"'" > /output/SQUASHFS-FILES.txt
  '

grep -Fq 'Compression gzip' "$probe_input/SQUASHFS-INFO.txt" ||
  die "SquashFS 不是内核支持的 gzip 压缩"
grep -Fq 'usr/local/libexec/r46h-gles2-fbo-probe' "$probe_input/SQUASHFS-FILES.txt" ||
  die "SquashFS 缺少 probe"
grep -Fq 'usr/lib/aarch64-linux-gnu/dri/panfrost_dri.so' "$probe_input/SQUASHFS-FILES.txt" ||
  die "SquashFS 缺少 Panfrost DRI"

image_sha=$(shasum -a 256 "$probe_input/$SQUASHFS_NAME" | awk '{print $1}')
[[ "$image_sha" =~ ^[0-9a-f]{64}$ ]] || die "SquashFS SHA-256 非法"
sed "s/@IMAGE_SHA256@/$image_sha/" "$SOURCE_DIR/run-on-target.sh" > \
  "$probe_input/bootstrap-target.sh"
chmod 0755 "$probe_input/bootstrap-target.sh"
grep -Fqx "readonly EXPECTED_IMAGE_SHA256=$image_sha" "$probe_input/bootstrap-target.sh" ||
  die "目标脚本没有嵌入 SquashFS SHA-256"
if grep -Fq '@IMAGE_SHA256@' "$probe_input/bootstrap-target.sh"; then
  die "目标脚本仍含未解析的 SquashFS SHA-256 token"
fi

(
  cd "$source_snapshot"
  shasum -a 256 \
    mainline/userspace-probe/Dockerfile \
    mainline/userspace-probe/Squashfs.Dockerfile \
    mainline/userspace-probe/packages.txt \
    mainline/userspace-probe/r46h-gles2-fbo-probe.c \
    mainline/userspace-probe/run-on-target.sh \
    mainline/scripts/build-userspace-probe.sh \
    mainline/scripts/package-userspace-probe-bundle.py \
    mainline/deploy/templates/stage-easyroms-macos.sh.in \
    mainline/deploy/baselines/v0.8-bootloader-handoff.json \
    mainline/deploy/profiles/hl-r46h-v22-g92-v1.json \
    > "$probe_input/SOURCE-SHA256SUMS"
)

cat > "$probe_input/BUILD-INFO" <<EOF
probe_id=$PROBE_ID
distribution=Debian GNU/Linux 13 (trixie)
architecture=arm64
kernel_contract=6.12.99-r46h-mainline-v0.8-bootloader-handoff
base_image=debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd
runtime_image_id=$runtime_image_id
squashfs_tool_image_id=$tool_image_id
squashfs_compression=gzip
squashfs_source_date_epoch=$SOURCE_DATE_EPOCH
squashfs_sha256=$image_sha
source_git_commit=$source_commit
source_git_dirty=false
source_snapshot_method=git-archive-exact-commit
source_archive_sha256=$source_archive_sha256
docker_context=$docker_context
docker_client_version=$docker_client
docker_server_version=$docker_server
EOF

assert_repository_binding
[[ ! -e "$OUTPUT_DIR" && ! -L "$OUTPUT_DIR" ]] || die "发布前输出目录已出现: $OUTPUT_DIR"
python3 "$PACKAGER" \
  --input-dir "$probe_input" \
  --output-root "$OUTPUT_ROOT" \
  --card-profile "$CARD_PROFILE" \
  --current-baseline "$CURRENT_BASELINE" \
  --stage-template "$STAGE_TEMPLATE" \
  --source-date-epoch "$SOURCE_DATE_EPOCH"
