#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
MAINLINE_DIR=$(cd "$SCRIPT_DIR/.." && pwd -P)
REPO_ROOT=$(cd "$MAINLINE_DIR/.." && pwd -P)
OUTPUT_ROOT=$MAINLINE_DIR/out
CACHE_ROOT=$OUTPUT_ROOT/.cache
LIVE_SOURCE_DIR=$MAINLINE_DIR/rootfs-debian13
LIVE_PACKAGER=$SCRIPT_DIR/package-debian13-rootfs.py
LIVE_PLAN_GENERATOR=$SCRIPT_DIR/generate-debian13-write-plan.py
LIVE_PROBE_SOURCE=$MAINLINE_DIR/userspace-probe/r46h-gles2-fbo-probe.c
LIVE_CARD_PROFILE=$MAINLINE_DIR/deploy/profiles/hl-r46h-v22-g92-v1.json
KERNEL_BUNDLE=$OUTPUT_ROOT/r46h-mainline-test-v0.8-bootloader-handoff.tar.gz

readonly ARTIFACT_ID=debian13-p2-mvp-v0.1
readonly OUTPUT_NAME=r46h-debian13-p2-mvp-v0.1
readonly OUTPUT_DIR=$OUTPUT_ROOT/$OUTPUT_NAME
readonly IMAGE_NAME=r46h-debian13-p2-mvp-v0.1.ext4
readonly RUNTIME_IMAGE=arkos4clone/r46h-debian13-p2-mvp:v0.1
readonly BASE_IMAGE='debian:trixie-slim@sha256:020c0d20b9880058cbe785a9db107156c3c75c2ac944a6aa7ab59f2add76a7bd'
readonly APT_SNAPSHOT=20260713T000000Z
readonly SOURCE_DATE_EPOCH=1786060800
readonly PARTITION_SIZE=10716877312
readonly FS_BLOCK_SIZE=4096
readonly FS_BLOCK_COUNT=2616425
readonly FS_TAIL_SIZE=512
readonly FS_UUID=d3130001-46a4-4d56-9001-000000000001
readonly FS_LABEL=R46H_DEB13
readonly KERNEL_RELEASE=6.12.99-r46h-mainline-v0.8-bootloader-handoff
readonly KERNEL_BUNDLE_SHA256=8c7282a07bdec52b753a8af27d15c6bbc8b71b34d017c3d78a2273fba6cfd09e

INPUT_PATHS=(
  mainline/rootfs-debian13
  mainline/userspace-probe/r46h-gles2-fbo-probe.c
  mainline/scripts/build-debian13-rootfs.sh
  mainline/scripts/package-debian13-rootfs.py
  mainline/scripts/generate-debian13-write-plan.py
  mainline/tests/test-debian13-rootfs.py
  mainline/deploy/profiles/hl-r46h-v22-g92-v1.json
)
readonly INPUT_PATHS

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

for command in awk docker git shasum file mktemp python3 sed tar find sort stat; do
  command -v "$command" >/dev/null 2>&1 || die "missing command: $command"
done

[[ -d "$LIVE_SOURCE_DIR" && ! -L "$LIVE_SOURCE_DIR" ]] || die 'invalid Debian 13 source directory'
for input in "$LIVE_PACKAGER" "$LIVE_PLAN_GENERATOR" "$LIVE_PROBE_SOURCE" "$LIVE_CARD_PROFILE" "$KERNEL_BUNDLE"; do
  [[ -f "$input" && ! -L "$input" ]] || die "invalid build input: $input"
done
[[ ! -e "$OUTPUT_DIR" && ! -L "$OUTPUT_DIR" ]] || die "output already exists: $OUTPUT_DIR"
(( FS_BLOCK_SIZE * FS_BLOCK_COUNT + FS_TAIL_SIZE == PARTITION_SIZE )) || die 'invalid fixed p2 geometry'

source_commit=$(GIT_NO_REPLACE_OBJECTS=1 git -C "$REPO_ROOT" rev-parse --verify 'HEAD^{commit}')
[[ "$source_commit" =~ ^[0-9a-f]{40}$ ]] || die 'invalid source commit ID'

assert_repository_binding() {
  local current_commit dirty
  current_commit=$(GIT_NO_REPLACE_OBJECTS=1 git -C "$REPO_ROOT" rev-parse --verify 'HEAD^{commit}') ||
    die 'cannot revalidate source commit'
  [[ "$current_commit" == "$source_commit" ]] || die 'HEAD changed during build'
  dirty=$(git -C "$REPO_ROOT" status --porcelain --untracked-files=all -- "${INPUT_PATHS[@]}") ||
    die 'cannot inspect source worktree'
  [[ -z "$dirty" ]] || die 'canonical rootfs requires all inputs from clean Git HEAD'
}
assert_repository_binding

mkdir -p "$CACHE_ROOT" "$OUTPUT_ROOT"
work_dir=$(mktemp -d "$CACHE_ROOT/.r46h-debian13-rootfs.XXXXXX")
source_archive=$work_dir/source.tar
source_snapshot=$work_dir/source-snapshot
kernel_private=$work_dir/r46h-mainline-test-v0.8-bootloader-handoff.tar.gz
rootfs_tar=$work_dir/rootfs.tar
runtime_iid_file=$work_dir/runtime-image.id
stage_dir=$(mktemp -d "$OUTPUT_ROOT/.$OUTPUT_NAME.tmp.XXXXXX")
mkdir -m 0700 "$source_snapshot"
chmod 0700 "$stage_dir"
container_id=""
work_volume=""
published=0

cleanup() {
  local status=$?
  trap - EXIT
  trap '' INT TERM HUP
  if [[ -n "$container_id" ]]; then
    docker --context "$docker_context" rm -f "$container_id" >/dev/null 2>&1 || true
  fi
  if [[ -n "$work_volume" ]]; then
    docker --context "$docker_context" volume rm -f "$work_volume" >/dev/null 2>&1 || true
  fi
  if (( published == 0 )) && [[ -d "$stage_dir" && "$stage_dir" == "$OUTPUT_ROOT"/.$OUTPUT_NAME.tmp.* ]]; then
    rm -rf -- "$stage_dir"
  fi
  if [[ -d "$work_dir" && "$work_dir" == "$CACHE_ROOT"/.r46h-debian13-rootfs.* ]]; then
    rm -rf -- "$work_dir"
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

printf '%s  %s\n' "$KERNEL_BUNDLE_SHA256" "$KERNEL_BUNDLE" | shasum -a 256 -c -
cp -- "$KERNEL_BUNDLE" "$kernel_private"
chmod 0400 "$kernel_private"
printf '%s  %s\n' "$KERNEL_BUNDLE_SHA256" "$kernel_private" | shasum -a 256 -c -

GIT_NO_REPLACE_OBJECTS=1 git -C "$REPO_ROOT" archive \
  --format=tar --output="$source_archive" "$source_commit" -- "${INPUT_PATHS[@]}"
[[ -f "$source_archive" && ! -L "$source_archive" ]] || die 'cannot create source archive'
tar -xf "$source_archive" -C "$source_snapshot"
if find "$source_snapshot" -type l -print -quit | grep -q .; then
  die 'source snapshot contains a symbolic link'
fi
source_archive_sha256=$(shasum -a 256 "$source_archive" | awk '{print $1}')
[[ "$source_archive_sha256" =~ ^[0-9a-f]{64}$ ]] || die 'invalid source archive hash'

SNAPSHOT_MAINLINE=$source_snapshot/mainline
SOURCE_DIR=$SNAPSHOT_MAINLINE/rootfs-debian13
PACKAGER=$SNAPSHOT_MAINLINE/scripts/package-debian13-rootfs.py
PLAN_GENERATOR=$SNAPSHOT_MAINLINE/scripts/generate-debian13-write-plan.py
CARD_PROFILE=$SNAPSHOT_MAINLINE/deploy/profiles/hl-r46h-v22-g92-v1.json
for input in "$SOURCE_DIR/Dockerfile" "$SOURCE_DIR/build-ext4-in-container.sh" \
  "$PACKAGER" "$PLAN_GENERATOR" "$CARD_PROFILE"; do
  [[ -f "$input" && ! -L "$input" ]] || die "snapshot input missing: $input"
done
from_counts=$(awk -v base="$BASE_IMAGE" '
  $1 == "FROM" { total += 1; if ($2 == base) pinned += 1 }
  END { print total + 0, pinned + 0 }
' "$SOURCE_DIR/Dockerfile")
[[ "$from_counts" == "2 2" ]] ||
  die 'snapshot Dockerfile base image does not match the pinned identity'
[[ "$(grep -Fc "$APT_SNAPSHOT" "$SOURCE_DIR/apt/debian.sources")" == 2 ]] ||
  die 'snapshot APT sources do not match the pinned timestamp'
PYTHONDONTWRITEBYTECODE=1 python3 "$SNAPSHOT_MAINLINE/tests/test-debian13-rootfs.py"

(
  cd "$source_snapshot"
  find \
    mainline/rootfs-debian13 \
    mainline/userspace-probe/r46h-gles2-fbo-probe.c \
    mainline/scripts/build-debian13-rootfs.sh \
    mainline/scripts/package-debian13-rootfs.py \
    mainline/scripts/generate-debian13-write-plan.py \
    mainline/tests/test-debian13-rootfs.py \
    mainline/deploy/profiles/hl-r46h-v22-g92-v1.json \
    -type f -print | LC_ALL=C sort | while IFS= read -r file_path; do
      shasum -a 256 "$file_path"
    done
) > "$stage_dir/SOURCE-SHA256SUMS"

docker_context=$(docker context show)
[[ "$docker_context" =~ ^[A-Za-z0-9._-]+$ ]] || die 'invalid Docker context'
docker_client=$(docker --context "$docker_context" version --format '{{.Client.Version}}')
docker_server=$(docker --context "$docker_context" version --format '{{.Server.Version}}')
[[ "$docker_client" =~ ^[0-9A-Za-z._+-]+$ && "$docker_server" =~ ^[0-9A-Za-z._+-]+$ ]] ||
  die 'invalid Docker version'

printf 'Building Debian 13 arm64 rootfs container from snapshot %s...\n' "$APT_SNAPSHOT"
docker --context "$docker_context" build \
  --platform linux/arm64 \
  --file "$SOURCE_DIR/Dockerfile" \
  --tag "$RUNTIME_IMAGE" \
  --iidfile "$runtime_iid_file" \
  "$SNAPSHOT_MAINLINE"
[[ -f "$runtime_iid_file" && ! -L "$runtime_iid_file" ]] || die 'Docker did not publish an image ID'
runtime_image_id=$(<"$runtime_iid_file")
[[ "$runtime_image_id" =~ ^sha256:[0-9a-f]{64}$ ]] || die 'invalid runtime image ID'
[[ "$(docker --context "$docker_context" image inspect "$runtime_image_id" --format '{{.Id}}')" == "$runtime_image_id" ]] ||
  die 'Docker image ID cannot be resolved exactly'

container_id=$(docker --context "$docker_context" create --platform linux/arm64 "$runtime_image_id")
[[ "$container_id" =~ ^[0-9a-f]{64}$ ]] || die 'cannot create rootfs export container'
docker --context "$docker_context" export --output "$rootfs_tar" "$container_id"
docker --context "$docker_context" rm "$container_id" >/dev/null
container_id=""
[[ -f "$rootfs_tar" && ! -L "$rootfs_tar" ]] || die 'rootfs export failed'

work_volume="arkos4clone-r46h-debian13-${source_commit:0:12}-$$"
docker --context "$docker_context" volume create "$work_volume" >/dev/null

printf 'Creating exact-size journaled ext4 p2 image...\n'
docker --context "$docker_context" run --rm --platform linux/arm64 \
  --network none \
  --volume "$work_dir:/input:ro" \
  --volume "$work_volume:/work" \
  --volume "$stage_dir:/output" \
  --env IMAGE_NAME="$IMAGE_NAME" \
  --env PARTITION_SIZE="$PARTITION_SIZE" \
  --env FS_BLOCK_SIZE="$FS_BLOCK_SIZE" \
  --env FS_BLOCK_COUNT="$FS_BLOCK_COUNT" \
  --env FS_TAIL_SIZE="$FS_TAIL_SIZE" \
  --env FS_UUID="$FS_UUID" \
  --env FS_LABEL="$FS_LABEL" \
  --env KERNEL_RELEASE="$KERNEL_RELEASE" \
  --env KERNEL_BUNDLE_SHA256="$KERNEL_BUNDLE_SHA256" \
  --env SOURCE_DATE_EPOCH="$SOURCE_DATE_EPOCH" \
  "$runtime_image_id" \
  /usr/local/libexec/r46h-build-ext4-in-container

image_path=$stage_dir/$IMAGE_NAME
[[ -f "$image_path" && ! -L "$image_path" ]] || die 'ext4 image was not generated'
[[ "$(stat -f '%z' "$image_path" 2>/dev/null || stat -c '%s' "$image_path")" == "$PARTITION_SIZE" ]] ||
  die 'ext4 image length does not match p2'
printf 'Hashing the complete 10.7 GB image...\n'
image_sha256=$(shasum -a 256 "$image_path" | awk '{print $1}')
[[ "$image_sha256" =~ ^[0-9a-f]{64}$ ]] || die 'invalid ext4 image hash'
[[ "$(<"$stage_dir/EXT4-VERIFIED.sha256")" == "$image_sha256  $IMAGE_NAME" ]] ||
  die 'host image hash does not match the post-verification container hash'
printf '%s  %s\n' "$KERNEL_BUNDLE_SHA256" "$(basename "$KERNEL_BUNDLE")" > "$stage_dir/KERNEL-BUNDLE.sha256"

cat > "$stage_dir/BUILD-INFO" <<EOF
artifact_id=$ARTIFACT_ID
distribution=Debian GNU/Linux 13 (trixie)
architecture=arm64
image_name=$IMAGE_NAME
image_size=$PARTITION_SIZE
image_sha256=$image_sha256
filesystem=ext4
filesystem_block_size=$FS_BLOCK_SIZE
filesystem_block_count=$FS_BLOCK_COUNT
filesystem_tail_zero_bytes=$FS_TAIL_SIZE
filesystem_uuid=$FS_UUID
filesystem_label=$FS_LABEL
root_partuuid=c9f931c9-02
kernel_release=$KERNEL_RELEASE
kernel_bundle_sha256=$KERNEL_BUNDLE_SHA256
base_image=$BASE_IMAGE
runtime_image_id=$runtime_image_id
apt_snapshot=$APT_SNAPSHOT
source_git_commit=$source_commit
build_inputs_git_dirty=false
source_snapshot_method=git-archive-exact-commit
source_archive_sha256=$source_archive_sha256
source_date_epoch=$SOURCE_DATE_EPOCH
docker_context=$docker_context
docker_client_version=$docker_client
docker_server_version=$docker_server
EOF

assert_repository_binding
[[ ! -e "$OUTPUT_DIR" && ! -L "$OUTPUT_DIR" ]] || die 'output appeared during build'
python3 "$PACKAGER" \
  --stage-dir "$stage_dir" \
  --output-root "$OUTPUT_ROOT" \
  --repo-root "$REPO_ROOT" \
  --card-profile "$CARD_PROFILE"
published=1

printf 'PASS: Debian 13 p2 MVP artifact published.\n'
printf 'OUTPUT_DIR=%s\n' "$OUTPUT_DIR"
printf 'IMAGE_SHA256=%s\n' "$image_sha256"
