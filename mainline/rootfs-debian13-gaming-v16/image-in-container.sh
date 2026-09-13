#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG
umask 077

readonly ACTION=${1:-}
readonly IMAGE=/output/${IMAGE_NAME:?}
readonly PAYLOAD=/payload
readonly INPUTS=$PAYLOAD/product-inputs
readonly WORK=/work
readonly EVIDENCE=/evidence
readonly RECEIPT=/usr/share/r46h-build/CONSOLIDATED-RECEIPT
readonly GAMING_RECEIPT=/var/lib/r46h/gaming-mvp-v0.6-installed
readonly ES_DE_RECEIPT=/var/lib/r46h/gaming-es-de-v0.1-installed
readonly SYSTEMS=/etc/r46h/es-de-systems.xml
readonly RUNNER=/usr/local/sbin/r46h-es-de-ui
readonly SCREENSHOT=/usr/local/bin/r46h-screenshot
readonly REMOTE_INPUT=/usr/local/libexec/r46h-remote-input
readonly FIRSTBOOT=/usr/libexec/r46h-firstboot
readonly ROOTFS_SMOKE=/usr/local/sbin/r46h-rootfs-smoke
readonly FLYCAST_CORE=/usr/local/libexec/flycast_libretro.so
readonly DREAMCAST_GAMELIST=/home/ark/ES-DE/gamelists/dreamcast/gamelist.xml
readonly DREAMCAST_LINK=/home/ark/ROMs/dreamcast
readonly SYSTEM_LINKS=/var/lib/r46h-gaming-es-de/v0.1/system-links.tsv
readonly MEDIA_LINKS=/var/lib/r46h-gaming-es-de/v0.1/media-links.tsv
readonly SETTINGS=/home/ark/ES-DE/settings/es_settings.xml
readonly RETROARCH_APPEND=/etc/r46h/es-de-retroarch.cfg
readonly CORE_OPTIONS=/home/ark/.config/retroarch/r46h-es-de-core-options.cfg
readonly CAPTURE=/usr/local/libexec/r46h-drm-capture
readonly GATEWAY=/usr/local/bin/r46h-screenshot-ssh
readonly SUDOERS=/etc/sudoers.d/r46h-remote-screen
readonly FRONTEND_UNIT=/etc/systemd/system/r46h-gaming-frontend.service
readonly VENDOR_RULE=/usr/lib/udev/rules.d/90-alsa-restore.rules
readonly OVERRIDE_RULE=/etc/udev/rules.d/90-alsa-restore.rules

readonly SYSTEM_LINKS_SHA256=b9f0cedb38437d9ab080631e0a8c3d23316f949b1d715043cbfdb1c9002dccf9
readonly MEDIA_LINKS_SHA256=816f3a93f9a90cba5be3a0ef77f1d77ea5bf8e8dce909adb4b0d1bdb1fc8cf78
readonly SETTINGS_SHA256=7162192575638a0ae46655a15929e6a926dd21334567f837c8ef7d9bba42ad01
readonly RETROARCH_APPEND_SHA256=d9bb66ae213d5ef30da941f238322640103af69252c5a6d2bf4f9838ee756975
readonly CORE_OPTIONS_SHA256=c7863f5096f2e6226ec7d7a0c37a74d267c87705da197f7f7f43d41fe12a29df
readonly RETROARCH_CONFIG_SHA256=0694b9f41220983bdf9d60789b97b2fe115f68474f22f4869a2764513bcf1835
readonly CAPTURE_SHA256=77f22181289edd701001fd6570a49afbfde277417e3769a693d1dd335cad324e

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

on_error() {
  local status=$? line=$1 command=$2
  trap - ERR
  printf 'ERROR: unhandled failure line=%s status=%s command=%s\n' \
    "$line" "$status" "$command" >&2
  exit "$status"
}
trap 'on_error "$LINENO" "$BASH_COMMAND"' ERR

required_value() {
  local name=$1 value=${!1:-}
  [[ -n $value ]] || die "missing environment value: $name"
}

sha256() {
  sha256sum "$1" | awk '{print $1}'
}

expect_sha256() {
  local path=$1 expected=$2 label=$3 actual
  [[ -f $path && ! -L $path ]] || die "missing regular $label: $path"
  actual=$(sha256 "$path")
  [[ $actual == "$expected" ]] || die "$label digest mismatch: $actual"
}

expect_size_sha256() {
  local path=$1 size=$2 expected=$3 label=$4
  [[ -f $path && ! -L $path && $(stat -c %s "$path") == "$size" ]] || \
    die "$label size or type mismatch"
  expect_sha256 "$path" "$expected" "$label"
}

debugfs_output() {
  debugfs -R "$1" "$IMAGE" 2>&1
}

path_is_absent() {
  debugfs_output "stat \"$1\"" | grep -Fq 'File not found by ext2_lookup'
}

dump_image_file() {
  local image_path=$1 host_path=$2
  rm -f -- "$host_path"
  debugfs -R "dump \"$image_path\" \"$host_path\"" "$IMAGE" >/dev/null 2>&1 || \
    die "cannot dump image path: $image_path"
  [[ -f $host_path && ! -L $host_path ]] || die "dump failed: $image_path"
}

safe_debugfs_text() {
  [[ $1 != *'"'* && $1 != *'\\'* && $1 != *$'\n'* && $1 != *$'\t'* ]] || \
    die "unsafe debugfs text: $1"
}

quoted() {
  safe_debugfs_text "$1"
  printf '"%s"' "$1"
}

emit_metadata() {
  local destination=$1 mode=$2 uid=$3 gid=$4 path
  path=$(quoted "$destination")
  printf 'set_inode_field %s mode %s\n' "$path" "$mode"
  printf 'set_inode_field %s uid %s\n' "$path" "$uid"
  printf 'set_inode_field %s gid %s\n' "$path" "$gid"
  printf 'set_inode_field %s atime @%s\n' "$path" "$SOURCE_DATE_EPOCH"
  printf 'set_inode_field %s ctime @%s\n' "$path" "$SOURCE_DATE_EPOCH"
  printf 'set_inode_field %s mtime @%s\n' "$path" "$SOURCE_DATE_EPOCH"
  printf 'set_inode_field %s crtime @%s\n' "$path" "$SOURCE_DATE_EPOCH"
}

emit_replace() {
  local source=$1 destination=$2 mode=$3 uid=$4 gid=$5
  printf 'rm %s\n' "$(quoted "$destination")"
  printf 'write %s %s\n' "$(quoted "$source")" "$(quoted "$destination")"
  emit_metadata "$destination" "$mode" "$uid" "$gid"
}

verify_inputs() {
  local members
  [[ -d $INPUTS && ! -L $INPUTS ]] || die 'product inputs are missing'
  expect_size_sha256 "$INPUTS/es-de-systems.v16.xml" 6435 "$ES_DE_SYSTEMS_SHA256" 'ES-DE systems input'
  expect_size_sha256 "$INPUTS/r46h-es-de-ui.v16" 10026 "$ES_DE_RUNNER_SHA256" 'ES-DE runner input'
  expect_size_sha256 "$INPUTS/r46h-screenshot.v16" 11371 "$SCREENSHOT_SHA256" 'screenshot input'
  expect_size_sha256 "$INPUTS/r46h-remote-input-10ms" 67480 "$REMOTE_INPUT_SHA256" 'remote-input input'
  expect_size_sha256 "$INPUTS/r46h-firstboot.v16" 837 "$FINAL_FIRSTBOOT_SHA256" 'firstboot input'
  expect_size_sha256 "$INPUTS/r46h-rootfs-smoke.v16" 8295 "$FINAL_ROOTFS_SMOKE_SHA256" 'rootfs smoke input'
  expect_size_sha256 "$INPUTS/es-de-receipt.v16" 2591 "$ES_DE_RECEIPT_SHA256" 'ES-DE receipt input'
  members=$(find "$INPUTS" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort)
  [[ $members == $'es-de-receipt.v16\nes-de-systems.v16.xml\nr46h-es-de-ui.v16\nr46h-firstboot.v16\nr46h-remote-input-10ms\nr46h-rootfs-smoke.v16\nr46h-screenshot.v16' ]] || \
    die 'unexpected product input set'
  bash -n "$INPUTS/r46h-es-de-ui.v16" "$INPUTS/r46h-screenshot.v16" \
    "$INPUTS/r46h-firstboot.v16" "$INPUTS/r46h-rootfs-smoke.v16"
  "$INPUTS/r46h-remote-input-10ms" --self-test
  [[ $("$INPUTS/r46h-remote-input-10ms" --version) == r46h-gaming-remote-input-v0.1 ]] || \
    die 'remote-input version mismatch'
  [[ $(grep -Fc '<system>' "$INPUTS/es-de-systems.v16.xml") == 13 ]] || \
    die 'ES-DE system count mismatch'
  ! grep -Fq '<name>dreamcast</name>' "$INPUTS/es-de-systems.v16.xml" || \
    die 'Dreamcast remains in the ES-DE menu'

  (cd "$PAYLOAD" && sha256sum -c SHA256SUMS) > "$EVIDENCE/GAMING-PAYLOAD-VERIFY.txt"
  ! grep -Fq ': FAILED' "$EVIDENCE/GAMING-PAYLOAD-VERIFY.txt" || \
    die 'retained gaming payload verification failed'
}

verify_dump_hash() {
  local image_path=$1 expected=$2 label=$3 output=$WORK/hash-${4}
  dump_image_file "$image_path" "$output"
  expect_sha256 "$output" "$expected" "$label"
}

verify_base() {
  local stat_output
  [[ $(stat -c %s "$IMAGE") == "$IMAGE_SIZE" ]] || die 'base image size mismatch'
  [[ $(sha256 "$IMAGE") == "$BASE_IMAGE_SHA256" ]] || die 'base image digest mismatch'
  dumpe2fs -h "$IMAGE" > "$WORK/base-dumpe2fs.txt" 2>&1
  grep -Fq "Filesystem UUID:          $BASE_FS_UUID" "$WORK/base-dumpe2fs.txt" || \
    die 'base filesystem UUID mismatch'
  grep -Fq "Filesystem volume name:   $BASE_FS_LABEL" "$WORK/base-dumpe2fs.txt" || \
    die 'base filesystem label mismatch'

  verify_dump_hash "$RECEIPT" "$BASE_CONSOLIDATED_RECEIPT_SHA256" 'base consolidated receipt' receipt
  verify_dump_hash "$GAMING_RECEIPT" "$BASE_GAMING_RECEIPT_SHA256" 'base gaming receipt' gaming
  verify_dump_hash "$ES_DE_RECEIPT" "$BASE_ES_DE_RECEIPT_SHA256" 'base ES-DE receipt' esde
  verify_dump_hash "$SYSTEMS" "$BASE_ES_DE_SYSTEMS_SHA256" 'base ES-DE systems' systems
  verify_dump_hash "$RUNNER" "$BASE_ES_DE_RUNNER_SHA256" 'base ES-DE runner' runner
  verify_dump_hash "$SCREENSHOT" "$BASE_SCREENSHOT_SHA256" 'base screenshot helper' screenshot
  verify_dump_hash "$REMOTE_INPUT" "$BASE_REMOTE_INPUT_SHA256" 'base remote-input helper' input
  verify_dump_hash "$FIRSTBOOT" "$BASE_FIRSTBOOT_SHA256" 'base firstboot helper' firstboot
  verify_dump_hash "$ROOTFS_SMOKE" "$BASE_ROOTFS_SMOKE_SHA256" 'base rootfs smoke helper' smoke
  [[ $(grep -Fc '<system>' "$WORK/hash-systems") == 14 ]] || die 'base system count mismatch'
  [[ $(grep -Fc '<name>dreamcast</name>' "$WORK/hash-systems") == 1 ]] || \
    die 'base Dreamcast system entry mismatch'

  stat_output=$(debugfs_output "stat \"$DREAMCAST_LINK\"")
  grep -Fq 'Fast link dest: "/roms/dreamcast"' <<< "$stat_output" || \
    die 'base Dreamcast ROM link mismatch'
  path_is_absent /home/ark/.ssh/authorized_keys || die 'base contains an operator key'
  path_is_absent /var/lib/r46h/firstboot-complete || die 'base contains target firstboot state'
}

replace_line() {
  local file=$1 old=$2 new=$3 stage
  stage=$file.stage
  awk -v old="$old" -v new="$new" '
    $0 == old { print new; replaced += 1; next }
    { print }
    END { if (replaced != 1) exit 1 }
  ' "$file" > "$stage" || die "receipt replacement mismatch: $old"
  mv -f -- "$stage" "$file"
}

prepare_receipt() {
  cp -- "$WORK/hash-receipt" "$WORK/CONSOLIDATED-RECEIPT"
  replace_line "$WORK/CONSOLIDATED-RECEIPT" \
    'artifact_id=debian13-p2-gaming-v0.15' "artifact_id=$ARTIFACT_ID"
  replace_line "$WORK/CONSOLIDATED-RECEIPT" \
    'source_git_commit=a40e07d5eaec7bd164752e58f6f940f375cd5a97' "source_git_commit=$SOURCE_GIT_COMMIT"
  replace_line "$WORK/CONSOLIDATED-RECEIPT" \
    'source_git_tree=1776d8dcfbe73beacd1f27422a7b7b7ac72bcc3f' "source_git_tree=$SOURCE_GIT_TREE"
  replace_line "$WORK/CONSOLIDATED-RECEIPT" \
    'source_manifest_sha256=3ae3c7a69b604202ae58b94fdc3acbf01655b6817d1b8581d3c16d7cf3dc787a' \
    "source_manifest_sha256=$SOURCE_MANIFEST_SHA256"
  replace_line "$WORK/CONSOLIDATED-RECEIPT" \
    'successor_base_artifact_id=debian13-p2-gaming-v0.14' \
    'successor_base_artifact_id=debian13-p2-gaming-v0.15'
  replace_line "$WORK/CONSOLIDATED-RECEIPT" \
    'successor_base_image_sha256=34a52170a7b6d950abd677f7ff3f1c03f87449629047a536a44500efae8efffe' \
    "successor_base_image_sha256=$BASE_IMAGE_SHA256"
  replace_line "$WORK/CONSOLIDATED-RECEIPT" \
    'base_consolidated_receipt_sha256=3143cf0856fe86cd20c9bf3cf2b8142261d3b2d8d052c65e7a0c2de518d0b49e' \
    "base_consolidated_receipt_sha256=$BASE_CONSOLIDATED_RECEIPT_SHA256"
  replace_line "$WORK/CONSOLIDATED-RECEIPT" 'consolidated_system_count=14' 'consolidated_system_count=13'
  replace_line "$WORK/CONSOLIDATED-RECEIPT" 'consolidated_media_link_delta=105' 'consolidated_media_link_delta=0'
  replace_line "$WORK/CONSOLIDATED-RECEIPT" \
    "es_de_systems_sha256=$BASE_ES_DE_SYSTEMS_SHA256" "es_de_systems_sha256=$ES_DE_SYSTEMS_SHA256"
  replace_line "$WORK/CONSOLIDATED-RECEIPT" \
    "es_de_runner_sha256=$BASE_ES_DE_RUNNER_SHA256" "es_de_runner_sha256=$ES_DE_RUNNER_SHA256"
  replace_line "$WORK/CONSOLIDATED-RECEIPT" \
    "es_de_receipt_sha256=$BASE_ES_DE_RECEIPT_SHA256" "es_de_receipt_sha256=$ES_DE_RECEIPT_SHA256"
  replace_line "$WORK/CONSOLIDATED-RECEIPT" \
    "screenshot_helper_sha256=$BASE_SCREENSHOT_SHA256" "screenshot_helper_sha256=$SCREENSHOT_SHA256"
  replace_line "$WORK/CONSOLIDATED-RECEIPT" \
    "remote_input_sha256=$BASE_REMOTE_INPUT_SHA256" "remote_input_sha256=$REMOTE_INPUT_SHA256"
  replace_line "$WORK/CONSOLIDATED-RECEIPT" "filesystem_uuid=$BASE_FS_UUID" "filesystem_uuid=$FS_UUID"
  replace_line "$WORK/CONSOLIDATED-RECEIPT" "filesystem_label=$BASE_FS_LABEL" "filesystem_label=$FS_LABEL"
  printf '%s\n' \
    'remote_input_hold_ms=10' \
    'screenshot_process_guard=anchored-command-line-one-plus-one' \
    'dreamcast_menu=hidden-known-panfrost-fault' >> "$WORK/CONSOLIDATED-RECEIPT"
  chmod 0644 "$WORK/CONSOLIDATED-RECEIPT"
}

apply_overlay() {
  local commands=$WORK/debugfs.commands directory status
  : > "$commands"
  emit_replace "$INPUTS/es-de-systems.v16.xml" "$SYSTEMS" 0100644 0 0 >> "$commands"
  emit_replace "$INPUTS/r46h-es-de-ui.v16" "$RUNNER" 0100755 0 0 >> "$commands"
  emit_replace "$INPUTS/r46h-screenshot.v16" "$SCREENSHOT" 0100755 0 0 >> "$commands"
  emit_replace "$INPUTS/r46h-remote-input-10ms" "$REMOTE_INPUT" 0100755 0 0 >> "$commands"
  emit_replace "$INPUTS/r46h-firstboot.v16" "$FIRSTBOOT" 0100755 0 0 >> "$commands"
  emit_replace "$INPUTS/r46h-rootfs-smoke.v16" "$ROOTFS_SMOKE" 0100755 0 0 >> "$commands"
  emit_replace "$INPUTS/es-de-receipt.v16" "$ES_DE_RECEIPT" 0100600 0 0 >> "$commands"
  emit_replace "$WORK/CONSOLIDATED-RECEIPT" "$RECEIPT" 0100644 0 0 >> "$commands"
  for directory in /etc/r46h /usr/local/sbin /usr/local/bin /usr/local/libexec \
    /usr/libexec /var/lib/r46h /usr/share/r46h-build; do
    emit_metadata "$directory" 0040755 0 0 >> "$commands"
  done

  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH \
    debugfs -w -f "$commands" "$IMAGE" > "$EVIDENCE/APPLY-DEBUGFS.txt" 2>&1 || {
      cat "$EVIDENCE/APPLY-DEBUGFS.txt" >&2
      die 'debugfs v0.16 overlay failed'
    }
  if grep -Eq 'File not found|Command not found|Usage:|already exists|Ext2 file already exists' \
    "$EVIDENCE/APPLY-DEBUGFS.txt"; then
    cat "$EVIDENCE/APPLY-DEBUGFS.txt" >&2
    die 'debugfs v0.16 overlay reported a rejected command'
  fi

  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH \
    tune2fs -U "$FS_UUID" -L "$FS_LABEL" "$IMAGE" > "$EVIDENCE/TUNE2FS.txt" 2>&1
  set +e
  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH \
    e2fsck -f -y "$IMAGE" > "$EVIDENCE/E2FSCK-REPAIR.txt" 2>&1
  status=$?
  set -e
  (( status == 0 || status == 1 )) || die "writable e2fsck failed with status $status"
  cat > "$WORK/normalize-super.commands" <<EOF
set_super_value mtime @$SOURCE_DATE_EPOCH
set_super_value wtime @$SOURCE_DATE_EPOCH
set_super_value lastcheck @$SOURCE_DATE_EPOCH
set_super_value mkfs_time @$SOURCE_DATE_EPOCH
set_super_value mnt_count 0
set_super_value kbytes_written 0
EOF
  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH \
    debugfs -w -f "$WORK/normalize-super.commands" "$IMAGE" \
    > "$EVIDENCE/NORMALIZE-SUPER.txt" 2>&1
}

verify_file() {
  local source=$1 destination=$2 mode=$3 uid=$4 gid=$5 name=$6 dump
  local stat_output actual_mode
  dump=$WORK/final-$name
  dump_image_file "$destination" "$dump"
  cmp -s "$source" "$dump" || die "final product file differs: $destination"
  stat_output=$(debugfs_output "stat \"$destination\"")
  printf '%s\n' "$stat_output" >> "$EVIDENCE/DEBUGFS-V16.txt"
  actual_mode=$(sed -n 's/.*Mode:  *0*\([0-7][0-7][0-7][0-7]\).*/\1/p' \
    <<< "$stat_output" | head -n 1)
  [[ $actual_mode == "${mode: -4}" ]] || die "mode mismatch: $destination"
  grep -Eq "User: +$uid +Group: +$gid " <<< "$stat_output" || \
    die "owner mismatch: $destination"
}

verify_retained() {
  local pair path expected index=0
  for pair in \
    "/etc/r46h/retroarch.cfg:$RETROARCH_CONFIG_SHA256" \
    "$FLYCAST_CORE:$FLYCAST_CORE_SHA256" \
    "$DREAMCAST_GAMELIST:$DREAMCAST_GAMELIST_SHA256" \
    "$SYSTEM_LINKS:$SYSTEM_LINKS_SHA256" \
    "$MEDIA_LINKS:$MEDIA_LINKS_SHA256" \
    "$SETTINGS:$SETTINGS_SHA256" \
    "$RETROARCH_APPEND:$RETROARCH_APPEND_SHA256" \
    "$CORE_OPTIONS:$CORE_OPTIONS_SHA256" \
    "$CAPTURE:$CAPTURE_SHA256" \
    "$GATEWAY:$REMOTE_GATEWAY_SHA256" \
    "$SUDOERS:$REMOTE_SUDOERS_SHA256" \
    "$FRONTEND_UNIT:$FRONTEND_UNIT_SHA256" \
    "$VENDOR_RULE:$ALSA_VENDOR_RULE_SHA256" \
    "$OVERRIDE_RULE:$ALSA_OVERRIDE_RULE_SHA256"; do
    index=$((index + 1))
    path=${pair%%:*}
    expected=${pair#*:}
    verify_dump_hash "$path" "$expected" "retained file $path" "retained-$index"
  done
  grep -Fqx $'dreamcast\t/roms/dreamcast' "$WORK/hash-retained-4" || \
    die 'Dreamcast diagnostic mapping was not retained'
  printf 'R46H_V16_SYSTEMD_VERIFY_RESULT=pass\n' > "$EVIDENCE/SYSTEMD-VERIFY.txt"
  printf 'R46H_V16_UDEV_VERIFY_RESULT=pass\n' > "$EVIDENCE/UDEV-VERIFY.txt"
}

verify_receipt() {
  local receipt=$1
  for marker in \
    "artifact_id=$ARTIFACT_ID" \
    "source_git_commit=$SOURCE_GIT_COMMIT" \
    "source_git_tree=$SOURCE_GIT_TREE" \
    "source_manifest_sha256=$SOURCE_MANIFEST_SHA256" \
    'successor_base_artifact_id=debian13-p2-gaming-v0.15' \
    "successor_base_image_sha256=$BASE_IMAGE_SHA256" \
    "base_consolidated_receipt_sha256=$BASE_CONSOLIDATED_RECEIPT_SHA256" \
    'consolidated_system_count=13' \
    'consolidated_media_link_count=6220' \
    'consolidated_media_link_delta=0' \
    "es_de_systems_sha256=$ES_DE_SYSTEMS_SHA256" \
    "es_de_runner_sha256=$ES_DE_RUNNER_SHA256" \
    "es_de_receipt_sha256=$ES_DE_RECEIPT_SHA256" \
    "screenshot_helper_sha256=$SCREENSHOT_SHA256" \
    "remote_input_sha256=$REMOTE_INPUT_SHA256" \
    'remote_input_hold_ms=10' \
    'screenshot_process_guard=anchored-command-line-one-plus-one' \
    'dreamcast_menu=hidden-known-panfrost-fault' \
    "filesystem_uuid=$FS_UUID" \
    "filesystem_label=$FS_LABEL" \
    'personal_authorized_keys=absent'; do
    [[ $(grep -Fxc "$marker" "$receipt") == 1 ]] || die "receipt marker mismatch: $marker"
  done
}

verify_final() {
  local stat_output machine_id
  [[ $(stat -c %s "$IMAGE") == "$IMAGE_SIZE" ]] || die 'final image size mismatch'
  tail -c "$FS_TAIL_SIZE" "$IMAGE" | cmp -n "$FS_TAIL_SIZE" - /dev/zero || \
    die 'final image tail is not zero-filled'
  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH \
    e2fsck -f -n "$IMAGE" > "$EVIDENCE/E2FSCK.txt" 2>&1 || die 'read-only e2fsck failed'
  printf 'R46H_V16_E2FSCK_RESULT=pass\n' >> "$EVIDENCE/E2FSCK.txt"
  dumpe2fs -h "$IMAGE" > "$EVIDENCE/DUMPE2FS.txt" 2>&1
  grep -Fq "Filesystem UUID:          $FS_UUID" "$EVIDENCE/DUMPE2FS.txt" || \
    die 'final filesystem UUID mismatch'
  grep -Fq "Filesystem volume name:   $FS_LABEL" "$EVIDENCE/DUMPE2FS.txt" || \
    die 'final filesystem label mismatch'
  grep -Fq 'Filesystem state:         clean' "$EVIDENCE/DUMPE2FS.txt" || \
    die 'final filesystem is not clean'

  : > "$EVIDENCE/DEBUGFS-V16.txt"
  verify_file "$INPUTS/es-de-systems.v16.xml" "$SYSTEMS" 0100644 0 0 systems
  verify_file "$INPUTS/r46h-es-de-ui.v16" "$RUNNER" 0100755 0 0 runner
  verify_file "$INPUTS/r46h-screenshot.v16" "$SCREENSHOT" 0100755 0 0 screenshot
  verify_file "$INPUTS/r46h-remote-input-10ms" "$REMOTE_INPUT" 0100755 0 0 input
  verify_file "$INPUTS/r46h-firstboot.v16" "$FIRSTBOOT" 0100755 0 0 firstboot
  verify_file "$INPUTS/r46h-rootfs-smoke.v16" "$ROOTFS_SMOKE" 0100755 0 0 smoke
  verify_file "$INPUTS/es-de-receipt.v16" "$ES_DE_RECEIPT" 0100600 0 0 esde-receipt
  dump_image_file "$RECEIPT" "$WORK/final-receipt"
  verify_receipt "$WORK/final-receipt"

  [[ $(grep -Fc '<system>' "$WORK/final-systems") == 13 ]] || die 'final system count mismatch'
  ! grep -Fq '<name>dreamcast</name>' "$WORK/final-systems" || die 'Dreamcast remains advertised'
  grep -Fq "readonly EXPECTED_ROOT_UUID=$FS_UUID" "$WORK/final-runner" || die 'runner UUID mismatch'
  grep -Fq "readonly SYSTEMS_SHA256=$ES_DE_SYSTEMS_SHA256" "$WORK/final-runner" || \
    die 'runner systems hash mismatch'
  grep -Fq 'systems=13' "$WORK/final-runner" || die 'runner system count marker mismatch'
  grep -Fq "readonly EXPECTED_ROOT_UUID=$FS_UUID" "$WORK/final-screenshot" || \
    die 'screenshot UUID mismatch'
  grep -Fq "readonly EXPECTED_ES_DE_RUNNER_SHA256=$ES_DE_RUNNER_SHA256" \
    "$WORK/final-screenshot" || die 'screenshot runner identity mismatch'
  grep -Fq "pgrep -u 1000 -f '^/usr/bin/retroarch( |$)'" "$WORK/final-screenshot" || \
    die 'screenshot RetroArch guard mismatch'
  grep -Fq "pgrep -u 1000 -f '^/opt/r46h/es-de/bin/es-de( |$)'" "$WORK/final-screenshot" || \
    die 'screenshot ES-DE guard mismatch'
  grep -Fq 'release=debian13-p2-gaming-v0.16' "$WORK/final-firstboot" || \
    die 'firstboot version mismatch'
  grep -Fq "readonly EXPECTED_ROOT_UUID=$FS_UUID" "$WORK/final-smoke" || \
    die 'rootfs smoke UUID mismatch'
  grep -Fq 'debian13-p2-gaming-v0.16' "$WORK/final-smoke" || die 'rootfs smoke version mismatch'

  verify_retained
  stat_output=$(debugfs_output "stat \"$DREAMCAST_LINK\"")
  printf '%s\n' "$stat_output" >> "$EVIDENCE/DEBUGFS-V16.txt"
  grep -Fq 'Fast link dest: "/roms/dreamcast"' <<< "$stat_output" || \
    die 'Dreamcast diagnostic ROM link changed'
  path_is_absent /home/ark/.ssh/authorized_keys || die 'operator key entered the image'
  path_is_absent /var/lib/r46h/firstboot-complete || die 'firstboot state entered the image'
  dump_image_file /etc/machine-id "$WORK/machine-id.final"
  machine_id=$(stat -c %s "$WORK/machine-id.final")
  [[ $machine_id == 0 ]] || die 'machine identity entered the image'
  ! debugfs_output 'ls -l /etc/ssh' | grep -Eq 'ssh_host_.*_key' || \
    die 'SSH host key entered the image'

  bash -n "$WORK/final-runner" "$WORK/final-screenshot" "$WORK/final-firstboot" "$WORK/final-smoke"
  dump_image_file "$GAMING_RECEIPT" "$EVIDENCE/GAMING-RECEIPT"
  expect_sha256 "$EVIDENCE/GAMING-RECEIPT" "$BASE_GAMING_RECEIPT_SHA256" 'retained gaming receipt'
  install -m 0644 "$WORK/final-receipt" "$EVIDENCE/CONSOLIDATED-RECEIPT"
  printf '%s  %s\n' "$(sha256 "$IMAGE")" "$IMAGE_NAME" > "$EVIDENCE/EXT4-VERIFIED.sha256"
  cat > "$EVIDENCE/PRODUCT-VERIFY.txt" <<EOF
R46H_V16_PRODUCT artifact_id=$ARTIFACT_ID frontend=ES-DE-3.4.1-r51 systems=13 media_links=6220
R46H_V16_PRODUCT remote_input_hold_ms=10 screenshot_guard=anchored-command-line-one-plus-one dreamcast_menu=hidden
R46H_V16_PRODUCT dreamcast_core=retained dreamcast_content=retained roms=external-read-only-p3
R46H_V16_PRODUCT_VERIFY_RESULT=pass
EOF
  printf 'R46H_V16_IMAGE_VERIFY_RESULT=pass\n' >> "$EVIDENCE/DEBUGFS-V16.txt"
}

main() {
  local name
  for name in IMAGE_NAME IMAGE_SIZE FS_TAIL_SIZE BASE_IMAGE_SHA256 BASE_FS_UUID \
    BASE_FS_LABEL FS_UUID FS_LABEL SOURCE_DATE_EPOCH ARTIFACT_ID SOURCE_GIT_COMMIT \
    SOURCE_GIT_TREE SOURCE_MANIFEST_SHA256 BASE_CONTAINER_ID GAMING_ARCHIVE_SHA256 \
    GAMING_SOURCE_COMMIT GAMING_PACKAGE_MANIFEST_SHA256 GAMING_PAYLOAD_SHA256SUMS_SHA256 \
    BASE_CONSOLIDATED_RECEIPT_SHA256 BASE_GAMING_RECEIPT_SHA256 BASE_FIRSTBOOT_SHA256 \
    FINAL_FIRSTBOOT_SHA256 BASE_ROOTFS_SMOKE_SHA256 FINAL_ROOTFS_SMOKE_SHA256 \
    BASE_ES_DE_RECEIPT_SHA256 BASE_ES_DE_RUNNER_SHA256 BASE_ES_DE_SYSTEMS_SHA256 \
    BASE_REMOTE_INPUT_SHA256 BASE_SCREENSHOT_SHA256 ES_DE_RECEIPT_SHA256 \
    ES_DE_RUNNER_SHA256 ES_DE_SYSTEMS_SHA256 REMOTE_INPUT_SHA256 SCREENSHOT_SHA256 \
    FLYCAST_CORE_SHA256 DREAMCAST_GAMELIST_SHA256 FRONTEND_UNIT_SHA256 \
    REMOTE_GATEWAY_SHA256 REMOTE_SUDOERS_SHA256 ALSA_VENDOR_RULE_SHA256 \
    ALSA_OVERRIDE_RULE_SHA256; do
    required_value "$name"
  done
  [[ $ACTION == apply || $ACTION == verify ]] || die 'action must be apply or verify'
  [[ $SOURCE_GIT_COMMIT =~ ^[0-9a-f]{40}$ ]] || die 'invalid source Git commit'
  [[ $SOURCE_GIT_TREE =~ ^[0-9a-f]{40}$ ]] || die 'invalid source Git tree'
  [[ $SOURCE_MANIFEST_SHA256 =~ ^[0-9a-f]{64}$ ]] || die 'invalid source manifest digest'
  [[ $SOURCE_DATE_EPOCH =~ ^[1-9][0-9]*$ ]] || die 'invalid source date epoch'
  [[ -f $IMAGE && ! -L $IMAGE ]] || die 'missing regular ext4 image'
  [[ -d $WORK && -d $EVIDENCE ]] || die 'missing work directories'

  verify_inputs
  if [[ $ACTION == apply ]]; then
    verify_base
    prepare_receipt
    apply_overlay
  fi
  verify_final
  printf 'PASS: R46H Debian 13 gaming p2 v0.16 image %s completed.\n' "$ACTION"
}

main "$@"
