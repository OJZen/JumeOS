#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG

readonly ACTION=${1:-}
readonly IMAGE=/output/${IMAGE_NAME:?}
readonly PAYLOAD=/payload
readonly SOURCE=/source
readonly WORK=/work
readonly EVIDENCE=/evidence
readonly RULE_SOURCE=$SOURCE/mainline/rootfs-debian13-gaming-v06/90-alsa-restore.rules
readonly VENDOR_RULE=/usr/lib/udev/rules.d/90-alsa-restore.rules
readonly OVERRIDE_RULE=/etc/udev/rules.d/90-alsa-restore.rules
readonly OLD_RECEIPT=/var/lib/r46h/gaming-mvp-v0.4-installed
readonly NEW_RECEIPT=/var/lib/r46h/gaming-mvp-v0.5-installed
readonly VOLUME_LINK=/etc/systemd/system/multi-user.target.wants/r46h-volume-keys.service
readonly VOLUME_TARGET=/etc/systemd/system/r46h-volume-keys.service

readonly -a PAYLOAD_FILES=(
  'files/retroarch.cfg|/etc/r46h/retroarch.cfg|0100644|existing'
  'files/r46h-smoke-libretro.so|/usr/local/libexec/r46h-smoke-libretro.so|0100644|existing'
  'files/r46h-input-bridge|/usr/local/libexec/r46h-input-bridge|0100755|existing'
  'files/r46h-gaming-input-ready|/usr/local/libexec/r46h-gaming-input-ready|0100755|existing'
  'files/r46h-volume-keys|/usr/local/libexec/r46h-volume-keys|0100755|new'
  'files/r46h-nes-smoke.nes|/usr/local/share/r46h/r46h-nes-smoke.nes|0100644|existing'
  'files/r46h-game-ui|/usr/local/sbin/r46h-game-ui|0100755|existing'
  'files/r46h-storage-audit|/usr/local/sbin/r46h-storage-audit|0100755|existing'
  'files/r46h-gaming-frontend-condition|/usr/local/libexec/r46h-gaming-frontend-condition|0100755|existing'
  'files/r46h-gaming-frontend.service|/etc/systemd/system/r46h-gaming-frontend.service|0100644|existing'
  'files/r46h-gaming-input.service|/etc/systemd/system/r46h-gaming-input.service|0100644|existing'
  'files/r46h-volume-keys.service|/etc/systemd/system/r46h-volume-keys.service|0100644|new'
  'files/GAMING-PRODUCT.md|/usr/share/doc/r46h-gaming-mvp/GAMING-PRODUCT.md|0100644|existing'
  'files/fstab|/etc/fstab|0100644|existing'
)

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

required_value() {
  local name=$1 value=${!1:-}
  [[ -n "$value" ]] || die "missing environment value: $name"
}

sha256() {
  sha256sum "$1" | awk '{print $1}'
}

expect_sha256() {
  local path=$1 expected=$2 label=$3
  [[ -f "$path" && ! -L "$path" ]] || die "missing regular $label: $path"
  [[ "$(sha256 "$path")" == "$expected" ]] || die "$label digest mismatch"
}

debugfs_output() {
  debugfs -R "$1" "$IMAGE" 2>&1
}

path_is_regular() {
  debugfs_output "stat $1" | grep -Fq 'Type: regular'
}

path_is_directory() {
  debugfs_output "stat $1" | grep -Fq 'Type: directory'
}

path_is_absent() {
  debugfs_output "stat $1" | grep -Fq 'File not found by ext2_lookup'
}

dump_image_file() {
  local image_path=$1 host_path=$2
  rm -f -- "$host_path"
  debugfs -R "dump $image_path $host_path" "$IMAGE" >/dev/null 2>&1 || \
    die "cannot dump image path: $image_path"
  [[ -f "$host_path" && ! -L "$host_path" ]] || die "dump failed: $image_path"
}

verify_payload() {
  local payload_complete
  [[ -d "$PAYLOAD" && ! -L "$PAYLOAD" ]] || die 'missing extracted gaming payload'
  expect_sha256 "$PAYLOAD/PACKAGES.tsv" "$GAMING_PACKAGE_MANIFEST_SHA256" \
    'gaming package manifest'
  expect_sha256 "$PAYLOAD/SHA256SUMS" "$GAMING_PAYLOAD_SHA256SUMS_SHA256" \
    'gaming payload checksum manifest'
  payload_complete=$(<"$PAYLOAD/PAYLOAD.COMPLETE")
  [[ "$payload_complete" == "sha256sums_sha256=$GAMING_PAYLOAD_SHA256SUMS_SHA256" ]] || \
    die 'gaming payload completion marker mismatch'
  grep -Fqx '"payload_id":"r46h-gaming-mvp-v0.5"' \
    <(tr ',' '\n' < "$PAYLOAD/PAYLOAD-INFO.json") || die 'gaming payload identity mismatch'
  grep -Fqx "\"source_git_commit\":\"$GAMING_SOURCE_COMMIT\"" \
    <(tr ',' '\n' < "$PAYLOAD/PAYLOAD-INFO.json") || die 'gaming payload source mismatch'
  (cd "$PAYLOAD" && sha256sum -c SHA256SUMS) > "$EVIDENCE/GAMING-PAYLOAD-VERIFY.txt"
  grep -Fq ': FAILED' "$EVIDENCE/GAMING-PAYLOAD-VERIFY.txt" && \
    die 'gaming payload checksum verification failed'
  expect_sha256 "$RULE_SOURCE" "$ALSA_OVERRIDE_RULE_SHA256" 'ALSA override rule'

  install -D -m 0755 "$PAYLOAD/files/r46h-volume-keys" \
    /usr/local/libexec/r46h-volume-keys
  install -D -m 0644 "$PAYLOAD/files/r46h-volume-keys.service" \
    /etc/systemd/system/r46h-volume-keys.service
  systemd-analyze verify --man=no r46h-volume-keys.service \
    > "$EVIDENCE/SYSTEMD-VERIFY.txt" 2>&1 || {
      cat "$EVIDENCE/SYSTEMD-VERIFY.txt" >&2
      die 'volume service unit verification failed'
    }
  printf 'R46H_V06_SYSTEMD_VERIFY_RESULT=pass\n' >> "$EVIDENCE/SYSTEMD-VERIFY.txt"
}

verify_base() {
  local entry relative destination mode state
  [[ "$(stat -c %s "$IMAGE")" == "$IMAGE_SIZE" ]] || die 'base image size mismatch'
  [[ "$(sha256 "$IMAGE")" == "$BASE_IMAGE_SHA256" ]] || die 'base image digest mismatch'
  dumpe2fs -h "$IMAGE" > "$WORK/base-dumpe2fs.txt" 2>&1
  grep -Fq "Filesystem UUID:          $BASE_FS_UUID" "$WORK/base-dumpe2fs.txt" || \
    die 'base filesystem UUID mismatch'
  grep -Fq "Filesystem volume name:   $BASE_FS_LABEL" "$WORK/base-dumpe2fs.txt" || \
    die 'base filesystem label mismatch'

  for entry in "${PAYLOAD_FILES[@]}"; do
    IFS='|' read -r relative destination mode state <<< "$entry"
    if [[ "$state" == existing ]]; then
      path_is_regular "$destination" || die "base path is not regular: $destination"
    else
      path_is_absent "$destination" || die "new path already exists in base: $destination"
    fi
  done
  path_is_regular "$OLD_RECEIPT" || die 'base v0.4 gaming receipt is absent'
  path_is_absent "$NEW_RECEIPT" || die 'base already has the v0.5 gaming receipt'
  path_is_absent "$OVERRIDE_RULE" || die 'base already has an ALSA override rule'
  path_is_absent "$VOLUME_LINK" || die 'base already has the volume enable link'
  path_is_absent /var/lib/r46h/firstboot-complete || die 'base contains target firstboot state'
  path_is_absent /home/ark/.ssh/authorized_keys || die 'base contains personal SSH authorization'
  for destination in \
    /etc /etc/r46h /etc/systemd/system /etc/systemd/system/multi-user.target.wants \
    /etc/udev/rules.d /usr/libexec /usr/local/libexec /usr/local/sbin \
    /usr/local/share/r46h /usr/share/doc/r46h-gaming-mvp /usr/share/r46h-build \
    /var/lib/r46h; do
    path_is_directory "$destination" || die "base directory is absent: $destination"
  done

  dump_image_file "$VENDOR_RULE" "$WORK/vendor-rule"
  dump_image_file /usr/libexec/r46h-firstboot "$WORK/r46h-firstboot.v05"
  dump_image_file /usr/local/sbin/r46h-rootfs-smoke "$WORK/r46h-rootfs-smoke.v05"
  dump_image_file /usr/share/r46h-build/CONSOLIDATED-RECEIPT "$WORK/receipt.v05"
  dump_image_file "$OLD_RECEIPT" "$WORK/gaming-receipt.v04"
  expect_sha256 "$WORK/vendor-rule" "$ALSA_VENDOR_RULE_SHA256" 'vendor ALSA rule'
  expect_sha256 "$WORK/r46h-firstboot.v05" "$BASE_FIRSTBOOT_SHA256" 'base firstboot tool'
  expect_sha256 "$WORK/r46h-rootfs-smoke.v05" "$BASE_ROOTFS_SMOKE_SHA256" \
    'base rootfs smoke tool'
  expect_sha256 "$WORK/receipt.v05" "$BASE_CONSOLIDATED_RECEIPT_SHA256" \
    'base consolidated receipt'
  expect_sha256 "$WORK/gaming-receipt.v04" "$BASE_GAMING_RECEIPT_SHA256" \
    'base gaming receipt'
}

prepare_generated_files() {
  cp -- "$WORK/r46h-firstboot.v05" "$WORK/r46h-firstboot.v06"
  sed -i 's/debian13-p2-gaming-v0\.5/debian13-p2-gaming-v0.6/g' \
    "$WORK/r46h-firstboot.v06"
  expect_sha256 "$WORK/r46h-firstboot.v06" "$FINAL_FIRSTBOOT_SHA256" \
    'v0.6 firstboot tool'

  cp -- "$WORK/r46h-rootfs-smoke.v05" "$WORK/r46h-rootfs-smoke.v06"
  sed -i \
    -e "s/$BASE_FS_UUID/$FS_UUID/g" \
    -e 's/debian13-p2-gaming-v0\.5/debian13-p2-gaming-v0.6/g' \
    "$WORK/r46h-rootfs-smoke.v06"
  expect_sha256 "$WORK/r46h-rootfs-smoke.v06" "$FINAL_ROOTFS_SMOKE_SHA256" \
    'v0.6 rootfs smoke tool'

  printf '%s\n' \
    'payload_id=r46h-gaming-mvp-v0.5' \
    "target_release=$KERNEL_RELEASE" \
    "package_manifest_sha256=$GAMING_PACKAGE_MANIFEST_SHA256" \
    "payload_sha256sums_sha256=$GAMING_PAYLOAD_SHA256SUMS_SHA256" \
    > "$WORK/gaming-mvp-v0.5-installed"
  chmod 0600 "$WORK/gaming-mvp-v0.5-installed"

  local game_ui smoke_core storage_audit retroarch nes_smoke volume_helper volume_unit fstab
  game_ui=$(sha256 "$PAYLOAD/files/r46h-game-ui")
  smoke_core=$(sha256 "$PAYLOAD/files/r46h-smoke-libretro.so")
  storage_audit=$(sha256 "$PAYLOAD/files/r46h-storage-audit")
  retroarch=$(sha256 "$PAYLOAD/files/retroarch.cfg")
  nes_smoke=$(sha256 "$PAYLOAD/files/r46h-nes-smoke.nes")
  volume_helper=$(sha256 "$PAYLOAD/files/r46h-volume-keys")
  volume_unit=$(sha256 "$PAYLOAD/files/r46h-volume-keys.service")
  fstab=$(sha256 "$PAYLOAD/files/fstab")
  cat > "$WORK/CONSOLIDATED-RECEIPT" <<EOF
artifact_id=$ARTIFACT_ID
source_git_commit=$SOURCE_GIT_COMMIT
source_git_tree=$SOURCE_GIT_TREE
source_manifest_sha256=$SOURCE_MANIFEST_SHA256
build_inputs_git_dirty=false
successor_base_artifact_id=debian13-p2-gaming-v0.5
successor_base_image_sha256=$BASE_IMAGE_SHA256
successor_method=offline-debugfs-bounded-overlay
base_image_id=$BASE_CONTAINER_ID
v08_fallback_release=6.12.99-r46h-mainline-v0.8-bootloader-handoff
v08_fallback_bundle_sha256=8c7282a07bdec52b753a8af27d15c6bbc8b71b34d017c3d78a2273fba6cfd09e
v08_fallback_module_tree_sha256=2ec532a3d3c6833538bd4ffd284122afa30bea0945e832f57be481527986f210
v10_fallback_release=6.12.99-r46h-mainline-v0.10-adc-full-range
v10_fallback_bundle_sha256=c4350520f7ad33ecf7b50f67c42985e2ce26c1c38d050ad50601c3538cebc780
v10_fallback_module_tree_sha256=a70796c050de93c4c212180addf54a17efe7732d355db2b52d0bfcab6c56cc16
kernel_release=$KERNEL_RELEASE
kernel_bundle_sha256=748d81cc0e8b9bf353430db1f4ee358bf09dee1d32db85a855961368b58d3fad
kernel_source_commit=6e36b43ce1048a5924d3b64dde1c038d2ac87e4e
kernel_source_snapshot_sha256=d86166716fc156d5e6e7b9a6aaa98f512aded75c4c156680aab353a1b43de997
kernel_module_tree_sha256=bd53fad3997ced39a15c69dbd70525106e891e5529dcef73bbbcfb699aafc291
kernel_image_sha256=956ab3d5a2e53afbfe964ae75850e8591b44c093b9779867b31149b7b591f68f
kernel_dtb_sha256=4d6d4ebad3b98600b6e9a38df4ca82230335558497a9e15dd0e81ca60e304b61
product_kernel_directory=/var/lib/r46h-gaming-product-kernel/v0.15-gaming-product
product_uboot_commands_sha256=51bf7caf6e9a08f01e1007a0010841e539300d8776851630e9d7d2829589d717
product_kernel_boot_mode=p2-one-shot-no-saveenv
gaming_payload_id=r46h-gaming-mvp-v0.5
gaming_source_commit=$GAMING_SOURCE_COMMIT
gaming_archive_sha256=$GAMING_ARCHIVE_SHA256
gaming_package_manifest_sha256=$GAMING_PACKAGE_MANIFEST_SHA256
gaming_payload_sha256sums_sha256=$GAMING_PAYLOAD_SHA256SUMS_SHA256
game_ui_sha256=$game_ui
smoke_core_sha256=$smoke_core
storage_audit_sha256=$storage_audit
retroarch_config_sha256=$retroarch
nes_smoke_sha256=$nes_smoke
volume_helper_sha256=$volume_helper
volume_unit_sha256=$volume_unit
fstab_sha256=$fstab
alsa_vendor_rule_sha256=$ALSA_VENDOR_RULE_SHA256
alsa_override_rule_sha256=$ALSA_OVERRIDE_RULE_SHA256
alsa_override_upstream_commit=f90124c73edd050b24961197a4abcf17e53b41a8
filesystem_uuid=$FS_UUID
filesystem_label=$FS_LABEL
regdb_alternative=/usr/lib/firmware/regulatory.db-upstream
personal_authorized_keys=absent
diagnostic_input_bridge=absent
product_input_bridge=r46h-gaming-input-bridge-v0.5
EOF
  chmod 0644 "$WORK/CONSOLIDATED-RECEIPT"
}

emit_metadata() {
  local destination=$1 mode=$2
  printf 'set_inode_field %s mode %s\n' "$destination" "$mode"
  printf 'set_inode_field %s uid 0\n' "$destination"
  printf 'set_inode_field %s gid 0\n' "$destination"
  printf 'set_inode_field %s atime @%s\n' "$destination" "$SOURCE_DATE_EPOCH"
  printf 'set_inode_field %s ctime @%s\n' "$destination" "$SOURCE_DATE_EPOCH"
  printf 'set_inode_field %s mtime @%s\n' "$destination" "$SOURCE_DATE_EPOCH"
  printf 'set_inode_field %s crtime @%s\n' "$destination" "$SOURCE_DATE_EPOCH"
}

emit_replace() {
  local source_path=$1 destination=$2 mode=$3
  printf 'rm %s\n' "$destination"
  printf 'write %s %s\n' "$source_path" "$destination"
  emit_metadata "$destination" "$mode"
}

emit_new() {
  local source_path=$1 destination=$2 mode=$3
  printf 'write %s %s\n' "$source_path" "$destination"
  emit_metadata "$destination" "$mode"
}

apply_overlay() {
  local commands=$WORK/debugfs.commands entry relative destination mode state directory
  : > "$commands"
  for entry in "${PAYLOAD_FILES[@]}"; do
    IFS='|' read -r relative destination mode state <<< "$entry"
    if [[ "$state" == existing ]]; then
      emit_replace "$PAYLOAD/$relative" "$destination" "$mode" >> "$commands"
    else
      emit_new "$PAYLOAD/$relative" "$destination" "$mode" >> "$commands"
    fi
  done
  emit_replace "$WORK/r46h-firstboot.v06" /usr/libexec/r46h-firstboot 0100755 \
    >> "$commands"
  emit_replace "$WORK/r46h-rootfs-smoke.v06" /usr/local/sbin/r46h-rootfs-smoke 0100755 \
    >> "$commands"
  emit_replace "$WORK/CONSOLIDATED-RECEIPT" \
    /usr/share/r46h-build/CONSOLIDATED-RECEIPT 0100644 >> "$commands"
  printf 'rm %s\n' "$OLD_RECEIPT" >> "$commands"
  emit_new "$WORK/gaming-mvp-v0.5-installed" "$NEW_RECEIPT" 0100600 >> "$commands"
  emit_new "$RULE_SOURCE" "$OVERRIDE_RULE" 0100644 >> "$commands"
  printf 'symlink %s %s\n' "$VOLUME_LINK" "$VOLUME_TARGET" >> "$commands"
  emit_metadata "$VOLUME_LINK" 0120777 >> "$commands"

  for directory in \
    /etc /etc/r46h /etc/systemd/system /etc/systemd/system/multi-user.target.wants \
    /etc/udev/rules.d /usr/libexec /usr/local/libexec /usr/local/sbin \
    /usr/local/share/r46h /usr/share/doc/r46h-gaming-mvp /usr/share/r46h-build \
    /var/lib/r46h; do
    emit_metadata "$directory" 0040755 >> "$commands"
  done

  E2FSPROGS_FAKE_TIME="$SOURCE_DATE_EPOCH" \
    debugfs -w -f "$commands" "$IMAGE" > "$EVIDENCE/APPLY-DEBUGFS.txt" 2>&1 || {
      cat "$EVIDENCE/APPLY-DEBUGFS.txt" >&2
      die 'debugfs overlay failed'
    }
  if grep -Eq 'File not found|Command not found|Usage:|already exists' \
    "$EVIDENCE/APPLY-DEBUGFS.txt"; then
    cat "$EVIDENCE/APPLY-DEBUGFS.txt" >&2
    die 'debugfs overlay reported a rejected command'
  fi

  E2FSPROGS_FAKE_TIME="$SOURCE_DATE_EPOCH" \
    tune2fs -U "$FS_UUID" -L "$FS_LABEL" "$IMAGE" \
    > "$EVIDENCE/TUNE2FS.txt" 2>&1
  E2FSPROGS_FAKE_TIME="$SOURCE_DATE_EPOCH" \
    e2fsck -f -y "$IMAGE" > "$EVIDENCE/E2FSCK-REPAIR.txt" 2>&1 || {
      status=$?
      (( status == 1 )) || {
        cat "$EVIDENCE/E2FSCK-REPAIR.txt" >&2
        die "writable e2fsck failed with status $status"
      }
    }

  cat > "$WORK/normalize-super.commands" <<EOF
set_super_value mtime @$SOURCE_DATE_EPOCH
set_super_value wtime @$SOURCE_DATE_EPOCH
set_super_value lastcheck @$SOURCE_DATE_EPOCH
set_super_value mkfs_time @$SOURCE_DATE_EPOCH
set_super_value mnt_count 0
set_super_value kbytes_written 0
EOF
  E2FSPROGS_FAKE_TIME="$SOURCE_DATE_EPOCH" \
    debugfs -w -f "$WORK/normalize-super.commands" "$IMAGE" \
    > "$EVIDENCE/NORMALIZE-SUPER.txt" 2>&1
}

verify_final() {
  local entry relative destination mode state dump_name actual_mode stat_output
  [[ "$(stat -c %s "$IMAGE")" == "$IMAGE_SIZE" ]] || die 'final image size mismatch'
  tail -c "$FS_TAIL_SIZE" "$IMAGE" | cmp -n "$FS_TAIL_SIZE" - /dev/zero || \
    die 'final image tail is not zero-filled'
  E2FSPROGS_FAKE_TIME="$SOURCE_DATE_EPOCH" \
    e2fsck -f -n "$IMAGE" > "$EVIDENCE/E2FSCK.txt" 2>&1 || {
      cat "$EVIDENCE/E2FSCK.txt" >&2
      die 'read-only e2fsck failed'
    }
  printf 'R46H_V06_E2FSCK_RESULT=pass\n' >> "$EVIDENCE/E2FSCK.txt"
  dumpe2fs -h "$IMAGE" > "$EVIDENCE/DUMPE2FS.txt" 2>&1
  grep -Fq "Filesystem UUID:          $FS_UUID" "$EVIDENCE/DUMPE2FS.txt" || \
    die 'final filesystem UUID mismatch'
  grep -Fq "Filesystem volume name:   $FS_LABEL" "$EVIDENCE/DUMPE2FS.txt" || \
    die 'final filesystem label mismatch'
  grep -Fq 'Filesystem state:         clean' "$EVIDENCE/DUMPE2FS.txt" || \
    die 'final filesystem is not clean'

  : > "$EVIDENCE/DEBUGFS-V06.txt"
  for entry in "${PAYLOAD_FILES[@]}"; do
    IFS='|' read -r relative destination mode state <<< "$entry"
    dump_name=${destination//\//_}
    dump_image_file "$destination" "$WORK/$dump_name"
    cmp -s "$PAYLOAD/$relative" "$WORK/$dump_name" || \
      die "payload file differs in final image: $destination"
    stat_output=$(debugfs_output "stat $destination")
    printf '%s\n' "$stat_output" >> "$EVIDENCE/DEBUGFS-V06.txt"
    actual_mode=$(sed -n 's/.*Mode:  *0*\([0-7][0-7][0-7][0-7]\).*/\1/p' \
      <<< "$stat_output" | head -n 1)
    [[ "$actual_mode" == "${mode: -4}" ]] || die "mode mismatch: $destination"
    grep -Eq 'User: +0 +Group: +0 ' <<< "$stat_output" || \
      die "owner mismatch: $destination"
  done

  dump_image_file /usr/libexec/r46h-firstboot "$WORK/r46h-firstboot.final"
  dump_image_file /usr/local/sbin/r46h-rootfs-smoke "$WORK/r46h-rootfs-smoke.final"
  dump_image_file /usr/share/r46h-build/CONSOLIDATED-RECEIPT "$WORK/receipt.final"
  dump_image_file "$NEW_RECEIPT" "$WORK/gaming-receipt.final"
  dump_image_file "$VENDOR_RULE" "$WORK/vendor-rule.final"
  dump_image_file "$OVERRIDE_RULE" "$WORK/override-rule.final"
  expect_sha256 "$WORK/r46h-firstboot.final" "$FINAL_FIRSTBOOT_SHA256" \
    'final firstboot tool'
  expect_sha256 "$WORK/r46h-rootfs-smoke.final" "$FINAL_ROOTFS_SMOKE_SHA256" \
    'final rootfs smoke tool'
  cmp -s "$WORK/receipt.final" "$WORK/CONSOLIDATED-RECEIPT" || \
    die 'final consolidated receipt differs'
  cmp -s "$WORK/gaming-receipt.final" "$WORK/gaming-mvp-v0.5-installed" || \
    die 'final gaming receipt differs'
  expect_sha256 "$WORK/vendor-rule.final" "$ALSA_VENDOR_RULE_SHA256" \
    'final vendor ALSA rule'
  expect_sha256 "$WORK/override-rule.final" "$ALSA_OVERRIDE_RULE_SHA256" \
    'final ALSA override rule'
  path_is_absent "$OLD_RECEIPT" || die 'old gaming receipt remains in final image'
  path_is_absent /var/lib/r46h/firstboot-complete || die 'target firstboot state remains'
  path_is_absent /home/ark/.ssh/authorized_keys || die 'personal SSH authorization remains'

  debugfs_output "stat $VOLUME_LINK" >> "$EVIDENCE/DEBUGFS-V06.txt"
  debugfs_output "stat $VOLUME_LINK" | \
    grep -Fq "Fast link dest: \"$VOLUME_TARGET\"" || die 'volume enable link mismatch'
  for marker in \
    "artifact_id=$ARTIFACT_ID" \
    "source_git_commit=$SOURCE_GIT_COMMIT" \
    "successor_base_image_sha256=$BASE_IMAGE_SHA256" \
    'gaming_payload_id=r46h-gaming-mvp-v0.5' \
    "gaming_archive_sha256=$GAMING_ARCHIVE_SHA256" \
    "alsa_vendor_rule_sha256=$ALSA_VENDOR_RULE_SHA256" \
    "alsa_override_rule_sha256=$ALSA_OVERRIDE_RULE_SHA256" \
    'alsa_override_upstream_commit=f90124c73edd050b24961197a4abcf17e53b41a8' \
    "filesystem_uuid=$FS_UUID" \
    "filesystem_label=$FS_LABEL" \
    'personal_authorized_keys=absent' \
    'diagnostic_input_bridge=absent'; do
    grep -Fqx "$marker" "$WORK/receipt.final" || die "receipt marker missing: $marker"
  done

  local udev_root=$WORK/udev-root
  install -d "$udev_root/etc/udev/rules.d" "$udev_root/usr/lib/udev/rules.d"
  install -m 0644 "$WORK/vendor-rule.final" \
    "$udev_root/usr/lib/udev/rules.d/90-alsa-restore.rules"
  install -m 0644 "$WORK/override-rule.final" \
    "$udev_root/etc/udev/rules.d/90-alsa-restore.rules"
  udevadm verify --root="$udev_root" --resolve-names=never \
    > "$EVIDENCE/UDEV-VERIFY.txt" 2>&1 || {
      cat "$EVIDENCE/UDEV-VERIFY.txt" >&2
      die 'ALSA rule precedence verification failed'
    }
  grep -Fq 'Success: 1' "$EVIDENCE/UDEV-VERIFY.txt" || \
    die 'ALSA rule precedence success marker missing'
  printf 'R46H_V06_UDEV_VERIFY_RESULT=pass\n' >> "$EVIDENCE/UDEV-VERIFY.txt"
  printf '%s  %s\n' "$(sha256 "$IMAGE")" "$IMAGE_NAME" \
    > "$EVIDENCE/EXT4-VERIFIED.sha256"
  install -m 0644 "$WORK/receipt.final" "$EVIDENCE/CONSOLIDATED-RECEIPT"
  install -m 0600 "$WORK/gaming-receipt.final" "$EVIDENCE/GAMING-RECEIPT"
  printf 'R46H_V06_IMAGE_VERIFY_RESULT=pass\n' >> "$EVIDENCE/DEBUGFS-V06.txt"
}

main() {
  local name
  for name in IMAGE_NAME IMAGE_SIZE FS_TAIL_SIZE BASE_IMAGE_SHA256 BASE_FS_UUID \
    BASE_FS_LABEL FS_UUID FS_LABEL SOURCE_DATE_EPOCH ARTIFACT_ID SOURCE_GIT_COMMIT \
    SOURCE_GIT_TREE SOURCE_MANIFEST_SHA256 BASE_CONTAINER_ID GAMING_ARCHIVE_SHA256 \
    GAMING_SOURCE_COMMIT GAMING_PACKAGE_MANIFEST_SHA256 \
    GAMING_PAYLOAD_SHA256SUMS_SHA256 ALSA_VENDOR_RULE_SHA256 \
    ALSA_OVERRIDE_RULE_SHA256 BASE_FIRSTBOOT_SHA256 FINAL_FIRSTBOOT_SHA256 \
    BASE_ROOTFS_SMOKE_SHA256 FINAL_ROOTFS_SMOKE_SHA256 \
    BASE_CONSOLIDATED_RECEIPT_SHA256 BASE_GAMING_RECEIPT_SHA256 KERNEL_RELEASE; do
    required_value "$name"
  done
  [[ "$ACTION" == apply || "$ACTION" == verify ]] || die 'action must be apply or verify'
  [[ "$SOURCE_GIT_COMMIT" =~ ^[0-9a-f]{40}$ ]] || die 'invalid source Git commit'
  [[ "$SOURCE_GIT_TREE" =~ ^[0-9a-f]{40}$ ]] || die 'invalid source Git tree'
  [[ "$SOURCE_DATE_EPOCH" =~ ^[1-9][0-9]*$ ]] || die 'invalid source date epoch'
  [[ -f "$IMAGE" && ! -L "$IMAGE" ]] || die 'missing regular ext4 image'
  [[ -d "$WORK" && -d "$EVIDENCE" ]] || die 'missing work directories'

  verify_payload
  if [[ "$ACTION" == apply ]]; then
    verify_base
    prepare_generated_files
    apply_overlay
  else
    dump_image_file /usr/libexec/r46h-firstboot "$WORK/r46h-firstboot.v05"
    sed -i 's/debian13-p2-gaming-v0\.6/debian13-p2-gaming-v0.5/g' \
      "$WORK/r46h-firstboot.v05"
    expect_sha256 "$WORK/r46h-firstboot.v05" "$BASE_FIRSTBOOT_SHA256" \
      'reconstructed base firstboot tool'
    dump_image_file /usr/local/sbin/r46h-rootfs-smoke "$WORK/r46h-rootfs-smoke.v05"
    sed -i \
      -e "s/$FS_UUID/$BASE_FS_UUID/g" \
      -e 's/debian13-p2-gaming-v0\.6/debian13-p2-gaming-v0.5/g' \
      "$WORK/r46h-rootfs-smoke.v05"
    expect_sha256 "$WORK/r46h-rootfs-smoke.v05" "$BASE_ROOTFS_SMOKE_SHA256" \
      'reconstructed base rootfs smoke tool'
    prepare_generated_files
  fi
  verify_final
  printf 'PASS: R46H Debian 13 gaming p2 v0.6 image %s completed.\n' "$ACTION"
}

main "$@"
