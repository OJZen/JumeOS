#!/usr/bin/env bash
set -Eeuo pipefail
PATH=/usr/bin:/bin:/usr/sbin:/sbin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG
umask 077

readonly PROBE_ID=debian13-mesa-v0.2
readonly PAYLOAD_NAME=r46h-debian13-mesa-probe-v0.2
readonly EXPECTED_KERNEL=6.12.99-r46h-mainline-v0.8-bootloader-handoff
readonly EXPECTED_CARD_PROFILE_SHA256=1c4f0d7116294085d59d5e60e08480c7ac715eddb4d839d0cbdaab605de8beb1
readonly EXPECTED_G92_PREFIX_SHA256=91a1f0d5f84e9589843ebf1eb0889669a5da64632fd258ef872f890b446a998b
readonly IMAGE_NAME=r46h-userspace-probe-debian13-mesa-v0.2.squashfs
readonly EXPECTED_IMAGE_SHA256=@IMAGE_SHA256@
readonly TIMEOUT_SECONDS=30
readonly SESSION_TIMEOUT_SECONDS=45

die() {
  printf 'R46H_MESA_RUNTIME result=fail reason=%s\n' "$*" >&2
  exit 1
}

hash_file() {
  sha256sum -- "$1" | awk '{print $1}'
}

file_value() {
  local file=$1 key=$2 count value
  count=$(grep -c "^${key}=" "$file" 2>/dev/null || true)
  [[ "$count" -eq 1 ]] || die "receipt-key-count:${key}"
  value=$(sed -n "s/^${key}=//p" "$file")
  [[ -n "$value" && "$value" != *$'\n'* ]] || die "receipt-value-invalid:${key}"
  printf '%s' "$value"
}

usage() {
  cat <<'EOF'
usage: bootstrap-target.sh \
  --external-receipt /run/r46h-deploy/TARGET-TRUST-RECEIPT \
  --external-receipt-sha256 <literal-hash-printed-by-the-Mac-stager>
EOF
}

external_receipt=""
external_receipt_sha256=""
while (( $# > 0 )); do
  case "$1" in
    --external-receipt)
      [[ $# -ge 2 ]] || die "external-receipt-needs-value"
      external_receipt=$2
      shift 2
      ;;
    --external-receipt-sha256)
      [[ $# -ge 2 ]] || die "external-receipt-sha256-needs-value"
      external_receipt_sha256=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *) die "unknown-option:$1" ;;
  esac
done

[[ "$(id -u)" == 0 ]] || die "root-required"
[[ "$external_receipt_sha256" =~ ^[0-9a-f]{64}$ ]] ||
  die "invalid-external-receipt-sha256"

test_root=${R46H_PROBE_TARGET_TEST_ROOT:-}
if [[ -n "$test_root" ]]; then
  [[ -f /.dockerenv ]] || die "target-test-mode-is-container-only"
  [[ -d "$test_root" && ! -L "$test_root" ]] || die "unsafe-target-test-root"
  test_root=$(cd "$test_root" && pwd -P)
  [[ "$test_root" == /run/r46h-probe-target-test.* ||
     "$test_root" == /repo/mainline/out/.cache/.r46h-probe-target-test.* ]] ||
    die "target-test-root-outside-allowlist"
  [[ "$(stat -c '%u:%a' -- "$test_root")" == 0:700 ]] ||
    die "unsafe-target-test-root-mode"
  ROMS_MOUNT=$test_root/roms
  trusted_parent=$test_root/run/r46h-deploy
else
  ROMS_MOUNT=/roms
  trusted_parent=/run/r46h-deploy
fi
readonly test_root ROMS_MOUNT

[[ -d "$trusted_parent" && ! -L "$trusted_parent" ]] || die "missing-trusted-directory"
[[ "$(stat -c '%u:%a' -- "$trusted_parent")" == 0:700 ]] ||
  die "unsafe-trusted-directory-mode"
trusted_parent=$(cd "$trusted_parent" && pwd -P)
readonly trusted_parent
[[ "$external_receipt" == "$trusted_parent/"* ]] || die "receipt-outside-trusted-directory"
[[ -f "$external_receipt" && ! -L "$external_receipt" ]] || die "unsafe-external-receipt"
external_receipt=$(realpath -e -- "$external_receipt")
[[ "$external_receipt" == "$trusted_parent/"* ]] || die "receipt-escaped-trusted-directory"
[[ "$(stat -c '%u:%a' -- "$external_receipt")" == 0:600 ]] ||
  die "unsafe-external-receipt-mode"
[[ "$(hash_file "$external_receipt")" == "$external_receipt_sha256" ]] ||
  die "external-receipt-checksum-mismatch"

expected_receipt_keys=$'format_version\nstatus\ntarget\npayload\nkernel_release\ncard_profile_sha256\nstage_complete_sha256\nbootstrap_target_sha256\nstage_sources_sha256\ncompletion_secret\ncompletion_secret_sha256\ng92_prefix_sha256\nboot_partition_sha256\nonly_written_partition\nroot_partition'
actual_receipt_keys=$(awk -F= 'NF >= 2 {print $1} NF < 2 {print "<malformed>"}' "$external_receipt")
[[ "$actual_receipt_keys" == "$expected_receipt_keys" ]] || die "external-receipt-field-set-mismatch"
[[ "$(file_value "$external_receipt" format_version)" == 1 ]] || die "receipt-version-mismatch"
[[ "$(file_value "$external_receipt" status)" == complete ]] || die "receipt-not-complete"
[[ "$(file_value "$external_receipt" target)" == HL-R46H-V22 ]] || die "receipt-target-mismatch"
[[ "$(file_value "$external_receipt" payload)" == "$PAYLOAD_NAME" ]] || die "receipt-payload-mismatch"
[[ "$(file_value "$external_receipt" kernel_release)" == "$EXPECTED_KERNEL" ]] ||
  die "receipt-kernel-mismatch"
[[ "$(file_value "$external_receipt" card_profile_sha256)" == "$EXPECTED_CARD_PROFILE_SHA256" ]] ||
  die "receipt-card-profile-mismatch"
[[ "$(file_value "$external_receipt" g92_prefix_sha256)" == "$EXPECTED_G92_PREFIX_SHA256" ]] ||
  die "receipt-g92-mismatch"
[[ "$(file_value "$external_receipt" only_written_partition)" == 3 ]] ||
  die "receipt-write-scope-mismatch"
[[ "$(file_value "$external_receipt" root_partition)" == never-mounted ]] ||
  die "receipt-root-proof-mismatch"

stage_complete_sha256=$(file_value "$external_receipt" stage_complete_sha256)
bootstrap_sha256=$(file_value "$external_receipt" bootstrap_target_sha256)
source_list_sha256=$(file_value "$external_receipt" stage_sources_sha256)
completion_secret=$(file_value "$external_receipt" completion_secret)
completion_secret_sha256=$(file_value "$external_receipt" completion_secret_sha256)
boot_partition_sha256=$(file_value "$external_receipt" boot_partition_sha256)
for value in "$stage_complete_sha256" "$bootstrap_sha256" "$source_list_sha256" \
  "$completion_secret" "$completion_secret_sha256" "$boot_partition_sha256"; do
  [[ "$value" =~ ^[0-9a-f]{64}$ ]] || die "receipt-sha256-invalid"
done
actual_completion_secret_sha256=$(printf '%s' "$completion_secret" | sha256sum | awk '{print $1}')
[[ "$actual_completion_secret_sha256" == "$completion_secret_sha256" ]] ||
  die "completion-secret-checksum-mismatch"

self_path=$(realpath -e -- "${BASH_SOURCE[0]}")
[[ "$self_path" == "$trusted_parent/"* && -f "$self_path" && ! -L "$self_path" ]] ||
  die "bootstrap-not-in-trusted-directory"
[[ "$(stat -c '%u:%a' -- "$self_path")" == 0:700 ]] || die "unsafe-bootstrap-mode"
[[ "$(hash_file "$self_path")" == "$bootstrap_sha256" ]] || die "bootstrap-checksum-mismatch"

bundle_dir=$ROMS_MOUNT/$PAYLOAD_NAME
image_path=$bundle_dir/$IMAGE_NAME
complete_path=$bundle_dir/STAGE-COMPLETE
source_list_path=$bundle_dir/STAGE-SOURCES.sha256
commitment_path=$bundle_dir/FINAL-RECEIPT-COMMITMENT
manifest_path=$bundle_dir/DEPLOY-MANIFEST

if [[ -n "$test_root" ]]; then
  release=$EXPECTED_KERNEL
else
  release=$(uname -r)
  [[ "$release" == "$EXPECTED_KERNEL" ]] || die "unexpected-kernel:$release"
  [[ -c /dev/dri/renderD128 ]] || die "missing-render-node"
  [[ -c /dev/dri/card0 ]] || die "missing-display-node"
  [[ -r /sys/fs/ext4/mmcblk0p2/errors_count ]] || die "missing-ext4-errors-count"
  [[ -r /sys/class/block/mmcblk0p3/dev ]] || die "missing-easyroms-device-identity"

  p3_majmin=$(cat /sys/class/block/mmcblk0p3/dev)
  [[ "$p3_majmin" =~ ^[0-9]+:[0-9]+$ ]] || die "invalid-easyroms-device-identity"
  mount_record=$(findmnt -rn -T "$ROMS_MOUNT" -o MAJ:MIN,TARGET,FSTYPE,FSROOT)
  read -r mount_majmin mount_target mount_fstype mount_fsroot mount_extra <<<"$mount_record"
  [[ -n "$mount_majmin" && -z "$mount_extra" && "$mount_majmin" == "$p3_majmin" &&
     "$mount_target" == "$ROMS_MOUNT" && "$mount_fstype" == exfat && "$mount_fsroot" == / ]] ||
    die "unexpected-easyroms-mount"
fi

[[ "$EXPECTED_IMAGE_SHA256" =~ ^[0-9a-f]{64}$ ]] || die "unresolved-image-checksum"
if [[ -n "$test_root" ]]; then
  runtime_dir=$(mktemp -d "$test_root/run/r46h-mesa-probe.XXXXXX")
else
  runtime_dir=$(mktemp -d /run/r46h-mesa-probe.XXXXXX)
fi
before_log=$runtime_dir/dmesg-before.log
after_log=$runtime_dir/dmesg-after.log
delta_log=$runtime_dir/dmesg-delta.log
mount_root=$runtime_dir/root
trusted_root=$runtime_dir/trusted
mkdir -m 0700 "$mount_root"
mkdir -m 0700 "$trusted_root"
post_audit_done=0
probe_started=0
probe_status=not-run
dmesg_ring_wrapped=0
ext4_changed=unknown
fault_detected=unknown
before_bytes=0
ext4_before=unknown
fault_pattern='panfrost.*(fault|error|timeout|reset|hang|warning|bug|oops|panic|drm_sched)'
fault_pattern+='|(warning|bug|oops|panic).*(panfrost|gpu|drm|mmu)'
fault_pattern+='|BUG:|Oops:|kernel panic|Call trace:|cut here'
fault_pattern+='|drm_sched.*(timedout|timeout|hang|fault|error)'
fault_pattern+='|\b(mmu|gpu).*(fault|timeout|hang|reset|error)'
fault_pattern+='|mmc.*(I/O error|error|timeout|CRC|fail(ed|ure)?)'
fault_pattern+='|I/O error.*mmc'
fault_pattern+='|(blk_update_request|end_request|blk_print_req_error).*(error|failure)'
fault_pattern+='|Buffer I/O error'
fault_pattern+='|JBD2.*(error|warning|abort|fail(ed|ure)?)'
fault_pattern+='|EXT4-fs.*(error|warning|abort|fail(ed|ure)?)'
fault_pattern+='|(exFAT-fs|FAT-fs).*(error|warning|warn|corrupt|fail(ed|ure)?)'

capture_post_audit() {
  dmesg > "$after_log" || return 1
  after_bytes=$(wc -c < "$after_log" | tr -d ' ')
  [[ "$after_bytes" =~ ^[0-9]+$ ]] || return 1
  if (( after_bytes < before_bytes )) ||
     ! head -c "$before_bytes" "$after_log" | cmp -s "$before_log" -; then
    dmesg_ring_wrapped=1
    cp "$after_log" "$delta_log" || return 1
  else
    tail -c "+$((before_bytes + 1))" "$after_log" > "$delta_log" || return 1
  fi
  ext4_after=$(cat /sys/fs/ext4/mmcblk0p2/errors_count) || return 1
  [[ "$ext4_after" =~ ^[0-9]+$ ]] || return 1
  if [[ "$ext4_after" == "$ext4_before" ]]; then
    ext4_changed=0
  else
    ext4_changed=1
  fi
  if grep -Eiq "$fault_pattern" "$delta_log"; then
    fault_detected=1
  else
    fault_detected=0
  fi

  printf 'R46H_MESA_RUNTIME ext4_errors_before=%s ext4_errors_after=%s\n' \
    "$ext4_before" "$ext4_after"
  printf 'R46H_MESA_RUNTIME probe_exit_status=%s dmesg_ring_wrapped=%s ext4_changed=%s fault_detected=%s\n' \
    "$probe_status" "$dmesg_ring_wrapped" "$ext4_changed" "$fault_detected"
  if [[ -s "$delta_log" ]]; then
    printf 'R46H_MESA_RUNTIME dmesg_delta_begin\n'
    sed -n '1,160p' "$delta_log"
    printf 'R46H_MESA_RUNTIME dmesg_delta_end\n'
  else
    printf 'R46H_MESA_RUNTIME dmesg_delta=empty\n'
  fi
  if (( fault_detected == 1 )); then
    printf 'R46H_MESA_RUNTIME fault_matches_begin\n'
    grep -Ein "$fault_pattern" "$delta_log" || true
    printf 'R46H_MESA_RUNTIME fault_matches_end\n'
  fi
  post_audit_done=1
}

cleanup() {
  local status=$? unmount_ok=1

  trap - EXIT
  trap '' INT TERM HUP
  set +e
  if (( status != 0 && post_audit_done == 0 )) && [[ -s "$before_log" ]]; then
    if (( probe_started == 1 )); then
      sleep 3
    else
      sleep 1
    fi
    capture_post_audit ||
      printf 'R46H_MESA_RUNTIME post_audit=failed-during-cleanup\n' >&2
  fi
  if mountpoint -q -- "$trusted_root"; then
    umount -- "$trusted_root" || unmount_ok=0
  fi
  if (( unmount_ok == 0 )); then
    printf 'R46H_MESA_RUNTIME cleanup=trusted-tmpfs-still-mounted path=%s\n' \
      "$trusted_root" >&2
    [[ "$status" -ne 0 ]] || status=1
  else
    rm -rf -- "$runtime_dir"
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

if [[ -n "$test_root" ]]; then
  post_audit_done=1
else
  ext4_before=$(cat /sys/fs/ext4/mmcblk0p2/errors_count)
  [[ "$ext4_before" =~ ^[0-9]+$ ]] || die "invalid-ext4-errors-before"
  [[ "$ext4_before" -eq 0 ]] || die "preexisting-ext4-errors:$ext4_before"
  dmesg > "$before_log"
  before_bytes=$(wc -c < "$before_log" | tr -d ' ')
  [[ "$before_bytes" =~ ^[0-9]+$ ]] || die "invalid-dmesg-byte-count"
fi

[[ -d "$bundle_dir" && ! -L "$bundle_dir" ]] || die "missing-staged-payload"
[[ -f "$image_path" && ! -L "$image_path" &&
   -f "$complete_path" && ! -L "$complete_path" &&
   -f "$source_list_path" && ! -L "$source_list_path" &&
   -f "$commitment_path" && ! -L "$commitment_path" &&
   -f "$manifest_path" && ! -L "$manifest_path" ]] ||
  die "missing-bundle-files"

if [[ -z "$test_root" ]]; then
  mem_available_kb=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
  [[ "$mem_available_kb" =~ ^[0-9]+$ && "$mem_available_kb" -ge 393216 ]] ||
    die "insufficient-memory-for-trusted-copy"
  if ! mount -t tmpfs -o mode=0700,nosuid,nodev,noexec,size=128m tmpfs "$trusted_root"; then
    die "cannot-mount-trusted-tmpfs"
  fi
fi

# Freeze the externally anchored source list and every staged payload file into
# bounded root-only RAM. Later validation and execution never reopen p3 files.
trusted_source_list=$trusted_root/STAGE-SOURCES.sha256
trusted_commitment=$trusted_root/FINAL-RECEIPT-COMMITMENT
cp --no-preserve=ownership,mode,timestamps -- "$source_list_path" \
  "$trusted_source_list" || die "cannot-copy-stage-source-list"
cp --no-preserve=ownership,mode,timestamps -- "$commitment_path" \
  "$trusted_commitment" || die "cannot-copy-final-receipt-commitment"
chmod 0400 "$trusted_source_list" "$trusted_commitment"
[[ "$(hash_file "$trusted_source_list")" == "$source_list_sha256" ]] ||
  die "stage-source-list-checksum-mismatch"

listed_names=$trusted_root/.listed-names
expected_entries=$trusted_root/.expected-source-entries
actual_entries=$trusted_root/.actual-source-entries
: > "$listed_names"
source_count=0
previous_name=""
while IFS= read -r line; do
  [[ "$line" =~ ^([0-9a-f]{64})[[:space:]][[:space:]]payload/([A-Za-z0-9._+-]+)$ ]] ||
    die "malformed-stage-source-entry"
  expected_hash=${BASH_REMATCH[1]}
  name=${BASH_REMATCH[2]}
  if [[ -n "$previous_name" ]]; then
    [[ "$name" > "$previous_name" ]] || die "stage-source-list-not-unique-and-sorted"
  fi
  previous_name=$name
  [[ "$name" != STAGE-SOURCES.sha256 && "$name" != FINAL-RECEIPT-COMMITMENT ]] ||
    die "reserved-stage-source-name"
  source_file=$bundle_dir/$name
  [[ -f "$source_file" && ! -L "$source_file" ]] || die "unsafe-stage-source:$name"
  cp --no-preserve=ownership,mode,timestamps -- "$source_file" "$trusted_root/$name" ||
    die "cannot-copy-stage-source:$name"
  chmod 0400 "$trusted_root/$name"
  [[ "$(hash_file "$trusted_root/$name")" == "$expected_hash" ]] ||
    die "stage-source-copy-mismatch:$name"
  printf '%s\n' "$name" >> "$listed_names"
  source_count=$((source_count + 1))
done < "$trusted_source_list"
(( source_count >= 9 )) || die "stage-source-list-too-short"

for required in bootstrap-target.sh DEPLOY-MANIFEST STAGE-COMPLETE \
  .r46h-stage-owner "$IMAGE_NAME"; do
  grep -Fxq -- "$required" "$listed_names" || die "missing-stage-source:$required"
done
{
  cat "$listed_names"
  printf '%s\n' STAGE-SOURCES.sha256 FINAL-RECEIPT-COMMITMENT
} | sort > "$expected_entries"
find "$bundle_dir" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort > "$actual_entries"
cmp -s "$expected_entries" "$actual_entries" || die "staged-payload-entry-set-mismatch"

expected_commitment_keys=$'format_version\nstatus\npurpose\npayload\ncompletion_secret_sha256'
actual_commitment_keys=$(awk -F= 'NF >= 2 {print $1} NF < 2 {print "<malformed>"}' \
  "$trusted_commitment")
[[ "$actual_commitment_keys" == "$expected_commitment_keys" ]] ||
  die "final-receipt-commitment-field-set-mismatch"
[[ "$(file_value "$trusted_commitment" format_version)" == 1 &&
   "$(file_value "$trusted_commitment" status)" == committed &&
   "$(file_value "$trusted_commitment" purpose)" == external-receipt-completion-secret &&
   "$(file_value "$trusted_commitment" payload)" == "$PAYLOAD_NAME" &&
   "$(file_value "$trusted_commitment" completion_secret_sha256)" == "$completion_secret_sha256" ]] ||
  die "final-receipt-commitment-mismatch"

trusted_complete=$trusted_root/STAGE-COMPLETE
trusted_image=$trusted_root/$IMAGE_NAME
trusted_manifest=$trusted_root/DEPLOY-MANIFEST
[[ "$(hash_file "$trusted_root/bootstrap-target.sh")" == "$bootstrap_sha256" ]] ||
  die "trusted-bootstrap-checksum-mismatch"
[[ "$(hash_file "$trusted_complete")" == "$stage_complete_sha256" ]] ||
  die "trusted-stage-complete-checksum-mismatch"
[[ "$(file_value "$trusted_manifest" target)" == HL-R46H-V22 ]] ||
  die "manifest-target-mismatch"
[[ "$(file_value "$trusted_manifest" payload_name)" == "$PAYLOAD_NAME" ]] ||
  die "manifest-payload-mismatch"
[[ "$(file_value "$trusted_manifest" kernel_release)" == "$EXPECTED_KERNEL" ]] ||
  die "manifest-kernel-mismatch"
[[ "$(file_value "$trusted_manifest" card_profile_sha256)" == "$EXPECTED_CARD_PROFILE_SHA256" ]] ||
  die "manifest-card-profile-mismatch"
[[ "$(file_value "$trusted_manifest" stage_complete_sha256)" == "$stage_complete_sha256" ]] ||
  die "manifest-stage-complete-mismatch"
[[ "$(file_value "$trusted_manifest" target_bootstrap_sha256)" == "$bootstrap_sha256" ]] ||
  die "manifest-bootstrap-mismatch"
[[ "$(file_value "$trusted_manifest" probe_id)" == "$PROBE_ID" ]] ||
  die "manifest-probe-mismatch"
[[ "$(file_value "$trusted_manifest" probe_image)" == "$IMAGE_NAME" ]] ||
  die "manifest-image-name-mismatch"
[[ "$(file_value "$trusted_manifest" probe_image_sha256)" == "$EXPECTED_IMAGE_SHA256" ]] ||
  die "manifest-image-checksum-mismatch"
trusted_image_size=$(stat -c '%s' "$trusted_image")
[[ "$trusted_image_size" =~ ^[0-9]+$ &&
   "$trusted_image_size" == "$(file_value "$trusted_manifest" probe_image_size)" ]] ||
  die "manifest-image-size-mismatch"

[[ "$(wc -l < "$trusted_complete" | tr -d ' ')" == 4 ]] || die "invalid-stage-complete"
grep -Fxq 'format_version=1' "$trusted_complete" || die "invalid-stage-complete-version"
grep -Fxq 'status=complete' "$trusted_complete" || die "invalid-stage-complete-status"
grep -Fxq "probe_id=$PROBE_ID" "$trusted_complete" || die "invalid-stage-complete-probe"
grep -Fxq "image_sha256=$EXPECTED_IMAGE_SHA256" "$trusted_complete" ||
  die "invalid-stage-complete-image"

actual_sha=$(hash_file "$trusted_image")
[[ "$actual_sha" == "$EXPECTED_IMAGE_SHA256" ]] || die "image-checksum-mismatch"
if [[ -n "$test_root" ]]; then
  rm -rf -- "$runtime_dir" || die "cannot-remove-test-runtime-directory"
  trap - EXIT INT TERM HUP
  printf 'R46H_MESA_RUNTIME result=trust-pass\n'
  exit 0
fi
render_gid=$(stat -c '%g' /dev/dri/renderD128)
[[ "$render_gid" =~ ^[0-9]+$ && "$render_gid" -le 2147483647 ]] ||
  die "invalid-render-node-gid"

printf 'R46H_MESA_RUNTIME stage=preflight probe=%s kernel=%s image_sha256=%s\n' \
  "$PROBE_ID" "$release" "$actual_sha"
printf 'R46H_MESA_RUNTIME isolation=mount-pid-net-namespace uid=65534 gid=%s exposed_node=renderD128 hidden_nodes=card0,card1 sysfs=readonly probe_timeout=%ss session_timeout=%ss\n' \
  "$render_gid" "$TIMEOUT_SECONDS" "$SESSION_TIMEOUT_SECONDS"

export R46H_PROBE_IMAGE=$trusted_image
export R46H_PROBE_ROOT=$mount_root
export R46H_PROBE_TIMEOUT=$TIMEOUT_SECONDS
export R46H_PROBE_RENDER_GID=$render_gid

# The child shell expands only the four exported, prevalidated values.
probe_started=1
set +e
# shellcheck disable=SC2016
timeout -s TERM -k 5 "$SESSION_TIMEOUT_SECONDS" \
  unshare --mount --pid --fork --net --propagation private /bin/bash -Eeuo pipefail -c '
  mount -t squashfs -o loop,ro,nodev,nosuid "$R46H_PROBE_IMAGE" "$R46H_PROBE_ROOT"
  mount -t tmpfs -o mode=0755,nosuid,nodev,size=2m tmpfs "$R46H_PROBE_ROOT/dev"
  mkdir -m 0755 "$R46H_PROBE_ROOT/dev/dri"
  mkdir -m 1777 "$R46H_PROBE_ROOT/dev/shm"
  for node in null zero random urandom; do
    touch "$R46H_PROBE_ROOT/dev/$node"
    mount --bind "/dev/$node" "$R46H_PROBE_ROOT/dev/$node"
  done
  touch "$R46H_PROBE_ROOT/dev/dri/renderD128"
  mount --bind /dev/dri/renderD128 "$R46H_PROBE_ROOT/dev/dri/renderD128"
  mount -t tmpfs -o mode=1777,nosuid,nodev,noexec,size=8m tmpfs "$R46H_PROBE_ROOT/dev/shm"
  mount -t proc -o nosuid,nodev,noexec proc "$R46H_PROBE_ROOT/proc"
  mount -t tmpfs -o mode=1777,nosuid,nodev,noexec,size=32m tmpfs "$R46H_PROBE_ROOT/tmp"
  mount -t sysfs -o ro,nosuid,nodev,noexec sysfs "$R46H_PROBE_ROOT/sys"

  [[ -c "$R46H_PROBE_ROOT/dev/dri/renderD128" ]]
  [[ ! -e "$R46H_PROBE_ROOT/dev/dri/card0" ]]
  [[ ! -e "$R46H_PROBE_ROOT/dev/dri/card1" ]]
  [[ "$(findmnt -rn -T "$R46H_PROBE_ROOT/sys" -o FSTYPE)" == sysfs ]]
  sysfs_options=$(findmnt -rn -T "$R46H_PROBE_ROOT/sys" -o OPTIONS)
  [[ ",$sysfs_options," == *,ro,* ]]
  [[ ",$sysfs_options," == *,nosuid,* ]]
  [[ ",$sysfs_options," == *,nodev,* ]]
  [[ ",$sysfs_options," == *,noexec,* ]]

  timeout -s TERM -k 2 "$R46H_PROBE_TIMEOUT" \
    chroot "$R46H_PROBE_ROOT" /usr/bin/env -i \
      HOME=/tmp \
      PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
      EGL_PLATFORM=surfaceless \
      GALLIUM_DRIVER=panfrost \
      MESA_LOADER_DRIVER_OVERRIDE=panfrost \
      MESA_SHADER_CACHE_DISABLE=true \
      /usr/bin/setpriv \
        --reuid 65534 \
        --regid "$R46H_PROBE_RENDER_GID" \
        --clear-groups \
        --no-new-privs \
        --bounding-set=-all \
        --inh-caps=-all \
        --ambient-caps=-all \
        --pdeathsig TERM \
        /usr/local/libexec/r46h-gles2-fbo-probe
'
probe_status=$?
set -e

# Give delayed GPU faults a bounded window to reach the kernel log.
sleep 3

capture_post_audit || die "post-audit-failed"
[[ "$ext4_changed" -eq 0 ]] || die "ext4-errors-count-changed"
[[ "$dmesg_ring_wrapped" -eq 0 ]] || die "dmesg-ring-wrapped"
[[ "$fault_detected" -eq 0 ]] || die "new-gpu-or-storage-fault"
[[ "$probe_status" -eq 0 ]] || die "probe-exit-$probe_status"
umount -- "$trusted_root" || die "cannot-unmount-trusted-tmpfs"
! mountpoint -q -- "$trusted_root" || die "trusted-tmpfs-remains-mounted"
rm -rf -- "$runtime_dir" || die "cannot-remove-runtime-directory"
trap - EXIT INT TERM HUP
printf 'R46H_MESA_RUNTIME result=pass\n'
