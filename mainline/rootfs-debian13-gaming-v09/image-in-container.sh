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
readonly SOURCE=/source
readonly WORK=/work
readonly EVIDENCE=/evidence
readonly DIRECT=$WORK/direct-files.tsv
readonly LINKS=$WORK/direct-links.tsv
readonly RECEIPT=/usr/share/r46h-build/CONSOLIDATED-RECEIPT
readonly GAMING_RECEIPT=/var/lib/r46h/gaming-mvp-v0.6-installed
readonly ES_DE_RECEIPT=/var/lib/r46h/gaming-es-de-v0.1-installed
readonly ES_DE_STATE=/var/lib/r46h-gaming-es-de/v0.1
readonly SYSTEMS=/etc/r46h/es-de-systems.xml
readonly RUNNER=/usr/local/sbin/r46h-es-de-ui
readonly SCREENSHOT=/usr/local/bin/r46h-screenshot
readonly FIRSTBOOT=/usr/libexec/r46h-firstboot
readonly ROOTFS_SMOKE=/usr/local/sbin/r46h-rootfs-smoke
readonly FULL_CORE=/usr/local/libexec/fbneo_libretro.so
readonly ARCADE_LINK=/home/ark/ROMs/arcade

readonly BASE_SYSTEMS_SOURCE=$SOURCE/mainline/gaming-es-de/es_systems.xml
readonly SYSTEM_FRAGMENT_SOURCE=$SOURCE/mainline/gaming-fbneo-full/es-system.arcade.xml
readonly BASE_LINKS_SOURCE=$SOURCE/mainline/gaming-es-de/system-links.tsv
readonly LINK_FRAGMENT_SOURCE=$SOURCE/mainline/gaming-fbneo-full/system-link.arcade.tsv
readonly RUNNER_SOURCE=$SOURCE/mainline/gaming-es-de/r46h-es-de-ui
readonly SCREENSHOT_SOURCE=$SOURCE/mainline/gaming-remote-screen/r46h-screenshot
readonly PRODUCT_DOC_SOURCE=$SOURCE/mainline/rootfs-debian13-gaming-v09/PRODUCT.md

readonly BASE_SYSTEMS_SOURCE_SHA256=1f451723d4ce1062157eb0e041ff4c098c5adea98c61e87ddf3cb784dfe630f0
readonly SYSTEM_FRAGMENT_SHA256=1fbe3e50aaca9c84b2bd2f0a66b41f170c5adcbde8580c8215b60b8c3fbc4711
readonly BASE_LINKS_SOURCE_SHA256=bd5e496ab9bb54f0b9d45b461262b70fd5758d763ea4ff4fb9d06c26c936d73d
readonly LINK_FRAGMENT_SHA256=058d05441005abd21fced96259c949f469bba10f8bb455d6eb21bcfc05d31e6f
readonly RUNNER_SOURCE_SHA256=5b9edd8705d26ac2b58285baee9d2025354a0343936b5360313e664edd5bafa1
readonly SCREENSHOT_SOURCE_SHA256=ce5b38185a92c5043b7ffd4d0a4248d91bc2a189812ed61b2ee68379469d3d04
readonly PRODUCT_DOC_SHA256=6ef4fe926d9569dd4b058f699e74eb589a856d9ecd880664825dc8507a2a54d7
readonly RETROARCH_CONFIG_SHA256=0694b9f41220983bdf9d60789b97b2fe115f68474f22f4869a2764513bcf1835
readonly FBNEO_SUBSET_SHA256=8bb17a551f3eeeb384ab00a5c5375d30eb63807afe5b6c1ba1d3f78220732bdb
readonly FRONTEND_UNIT_SHA256=df3b6bdc3ba9b3ee65d18b9575c302cfa3aaff4fcc67fe6d12e825565c2ba05c
readonly ALSA_VENDOR_RULE_SHA256=78db137bced7b3e9ea57659d098f49ee8636e665bb856af929164cbf80b67880
readonly ALSA_OVERRIDE_RULE_SHA256=e17f53c8923c96e30d5d925f9d525235f2e2da8d084591e33993c2a05f0cb0e0

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
  local path=$1 expected=$2 label=$3
  [[ -f $path && ! -L $path ]] || die "missing regular $label: $path"
  [[ $(sha256 "$path") == "$expected" ]] || die "$label digest mismatch"
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

add_direct() {
  local source=$1 destination=$2 mode=$3 uid=$4 gid=$5 operation=$6
  safe_debugfs_text "$source"
  safe_debugfs_text "$destination"
  [[ $operation == new || $operation == replace ]] || die 'invalid direct operation'
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$source" "$destination" "$mode" "$uid" "$gid" "$operation" >> "$DIRECT"
}

verify_inputs() {
  local members
  [[ -d $INPUTS && ! -L $INPUTS ]] || die 'product inputs are missing'
  expect_size_sha256 "$INPUTS/fbneo-full-libretro.so" 79683320 \
    "$FBNEO_FULL_CORE_SHA256" 'full FBNeo core'
  expect_size_sha256 "$INPUTS/r46h-firstboot.v08" 835 \
    "$BASE_FIRSTBOOT_SHA256" 'v0.8 firstboot input'
  expect_size_sha256 "$INPUTS/r46h-rootfs-smoke.v08" 8294 \
    "$BASE_ROOTFS_SMOKE_SHA256" 'v0.8 smoke input'
  members=$(find "$INPUTS" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort)
  [[ $members == $'fbneo-full-libretro.so\nr46h-firstboot.v08\nr46h-rootfs-smoke.v08' ]] || \
    die 'unexpected product input set'

  expect_sha256 "$BASE_SYSTEMS_SOURCE" "$BASE_SYSTEMS_SOURCE_SHA256" \
    'base ES-DE systems source'
  expect_sha256 "$SYSTEM_FRAGMENT_SOURCE" "$SYSTEM_FRAGMENT_SHA256" \
    'Arcade system fragment'
  expect_sha256 "$BASE_LINKS_SOURCE" "$BASE_LINKS_SOURCE_SHA256" \
    'base system links source'
  expect_sha256 "$LINK_FRAGMENT_SOURCE" "$LINK_FRAGMENT_SHA256" \
    'Arcade link fragment'
  expect_sha256 "$RUNNER_SOURCE" "$RUNNER_SOURCE_SHA256" 'ES-DE runner source'
  expect_sha256 "$SCREENSHOT_SOURCE" "$SCREENSHOT_SOURCE_SHA256" 'screenshot source'
  expect_sha256 "$PRODUCT_DOC_SOURCE" "$PRODUCT_DOC_SHA256" 'product document source'

  (cd "$PAYLOAD" && sha256sum -c SHA256SUMS) > "$EVIDENCE/GAMING-PAYLOAD-VERIFY.txt"
  if grep -Fq ': FAILED' "$EVIDENCE/GAMING-PAYLOAD-VERIFY.txt"; then
    die 'retained gaming payload verification failed'
  fi
}

verify_base() {
  local pair path expected
  [[ $(stat -c %s "$IMAGE") == "$IMAGE_SIZE" ]] || die 'base image size mismatch'
  [[ $(sha256 "$IMAGE") == "$BASE_IMAGE_SHA256" ]] || die 'base image digest mismatch'
  dumpe2fs -h "$IMAGE" > "$WORK/base-dumpe2fs.txt" 2>&1
  grep -Fq "Filesystem UUID:          $BASE_FS_UUID" "$WORK/base-dumpe2fs.txt" || \
    die 'base filesystem UUID mismatch'
  grep -Fq "Filesystem volume name:   $BASE_FS_LABEL" "$WORK/base-dumpe2fs.txt" || \
    die 'base filesystem label mismatch'

  for pair in \
    "$RECEIPT:$BASE_CONSOLIDATED_RECEIPT_SHA256" \
    "$GAMING_RECEIPT:$BASE_GAMING_RECEIPT_SHA256" \
    "$ES_DE_RECEIPT:$BASE_ES_DE_RECEIPT_SHA256" \
    "$SYSTEMS:$BASE_ES_DE_SYSTEMS_SHA256" \
    "$ES_DE_STATE/system-links.tsv:$BASE_SYSTEM_LINKS_SHA256" \
    "$RUNNER:$BASE_ES_DE_RUNNER_SHA256" \
    "$SCREENSHOT:$BASE_SCREENSHOT_SHA256" \
    "$FIRSTBOOT:$BASE_FIRSTBOOT_SHA256" \
    "$ROOTFS_SMOKE:$BASE_ROOTFS_SMOKE_SHA256" \
    "/etc/r46h/retroarch.cfg:$RETROARCH_CONFIG_SHA256" \
    "/usr/local/libexec/fbneo_neogeo_libretro.so:$FBNEO_SUBSET_SHA256" \
    "/etc/systemd/system/r46h-gaming-frontend.service:$FRONTEND_UNIT_SHA256"; do
    path=${pair%%:*}
    expected=${pair#*:}
    dump_image_file "$path" "$WORK/base-${path//\//_}"
    expect_sha256 "$WORK/base-${path//\//_}" "$expected" "base file $path"
  done
  path_is_absent "$FULL_CORE" || die 'base already contains full FBNeo core'
  path_is_absent "$ARCADE_LINK" || die 'base already exposes Arcade'
  path_is_absent /home/ark/.ssh/authorized_keys || die 'base contains an operator key'
}

prepare_system_files() {
  awk '
    FNR == NR { if ($0 != "</systemList>") print; next }
    { print }
    END { print "</systemList>" }
  ' "$BASE_SYSTEMS_SOURCE" "$SYSTEM_FRAGMENT_SOURCE" > "$WORK/es-systems.v09"
  expect_sha256 "$WORK/es-systems.v09" "$ES_DE_SYSTEMS_SHA256" 'v0.9 ES-DE systems'
  awk '1' "$BASE_LINKS_SOURCE" "$LINK_FRAGMENT_SOURCE" > "$WORK/system-links.v09"
  expect_sha256 "$WORK/system-links.v09" "$SYSTEM_LINKS_SHA256" 'v0.9 system links'
}

prepare_runner() {
  awk -v uuid="$FS_UUID" -v systems="$ES_DE_SYSTEMS_SHA256" \
      -v fullhash="$FBNEO_FULL_CORE_SHA256" '
    {
      if ($0 ~ /fbneo_neogeo_libretro.so; do$/) {
        print "  /usr/local/libexec/fbneo_neogeo_libretro.so \\"
        print "  /usr/local/libexec/fbneo_libretro.so; do"
        next
      }
      gsub("d3130007-46a4-4d56-9001-000000000007", uuid)
      gsub("1f451723d4ce1062157eb0e041ff4c098c5adea98c61e87ddf3cb784dfe630f0", systems)
      gsub("systems=7", "systems=8")
      print
      if ($0 ~ /^readonly FBNEO_CORE_SHA256=/) {
        print "readonly FBNEO_FULL_CORE=/usr/local/libexec/fbneo_libretro.so"
        print "readonly FBNEO_FULL_CORE_SHA256=" fullhash
      }
      if ($0 ~ /FBNEO_CORE:.*FBNEO_CORE_SHA256/) {
        print "  \"$FBNEO_FULL_CORE:$FBNEO_FULL_CORE_SHA256\" \\"
      }
    }
  ' "$RUNNER_SOURCE" > "$WORK/r46h-es-de-ui.v09"
  chmod 0755 "$WORK/r46h-es-de-ui.v09"
  expect_sha256 "$WORK/r46h-es-de-ui.v09" "$ES_DE_RUNNER_SHA256" 'v0.9 ES-DE runner'

  sed \
    -e "s/d3130007-46a4-4d56-9001-000000000007/$FS_UUID/g" \
    -e "s/5b9edd8705d26ac2b58285baee9d2025354a0343936b5360313e664edd5bafa1/$ES_DE_RUNNER_SHA256/g" \
    "$SCREENSHOT_SOURCE" > "$WORK/r46h-screenshot.v09"
  chmod 0755 "$WORK/r46h-screenshot.v09"
  expect_sha256 "$WORK/r46h-screenshot.v09" "$SCREENSHOT_SHA256" 'v0.9 screenshot helper'
}

prepare_identity_tools() {
  sed 's/debian13-p2-gaming-v0\.8/debian13-p2-gaming-v0.9/g' \
    "$INPUTS/r46h-firstboot.v08" > "$WORK/r46h-firstboot.v09"
  chmod 0755 "$WORK/r46h-firstboot.v09"
  expect_sha256 "$WORK/r46h-firstboot.v09" "$FINAL_FIRSTBOOT_SHA256" 'v0.9 firstboot tool'
  sed \
    -e "s/$BASE_FS_UUID/$FS_UUID/g" \
    -e 's/debian13-p2-gaming-v0\.8/debian13-p2-gaming-v0.9/g' \
    "$INPUTS/r46h-rootfs-smoke.v08" > "$WORK/r46h-rootfs-smoke.v09"
  chmod 0755 "$WORK/r46h-rootfs-smoke.v09"
  expect_sha256 "$WORK/r46h-rootfs-smoke.v09" "$FINAL_ROOTFS_SMOKE_SHA256" \
    'v0.9 rootfs smoke tool'
}

prepare_receipts() {
  cat > "$WORK/es-de-receipt.v09" <<EOF
feature_id=r46h-gaming-es-de-v0.1
source=ES-DE-v3.4.1-r51
runtime_archive_sha256=d5de91eb79fa229336d3f0f9c5e0e0d34b0096950cc67928914603209003aa70
runtime_manifest_sha256=05f963034036a355f472dd2c191583a46ac9bc5a28d98aaaee84cc5308620236
es_de_sha256=9c6e50433b9bca5ac1c01030bc4d7b143f05c2cd27c52e6f5f765b0acf01be98
systems_sha256=$ES_DE_SYSTEMS_SHA256
retroarch_append_sha256=2e13e4d33ca23e67d7b52ce6c9c85045b39e3f2ff76bbd6d68c8ca2295ddcb7f
system_links_sha256=$SYSTEM_LINKS_SHA256
media_links_sha256=9358e316d0b5436108c4a460a6654c5437341e4c85b86dcc2d5ae32abfbb9a9f
theme_sha256=2816222c88822a900a01bb966c54e27cfe32d7837edf0062d0edaeb70641736b
runner_sha256=$ES_DE_RUNNER_SHA256
unit_sha256=$FRONTEND_UNIT_SHA256
cjk_font_sha256=acb6440a713d880a13a21b468ba7cd43f5a2b2934972e51be791c880730777b8
media_links_installed=3417
media_sources_missing=not-evaluated-p3-external
settings_seeded=yes
core_options_seeded=yes
composition=offline-consolidated-p2-v0.9
EOF
  chmod 0600 "$WORK/es-de-receipt.v09"
  expect_sha256 "$WORK/es-de-receipt.v09" "$ES_DE_RECEIPT_SHA256" 'v0.9 ES-DE receipt'

  cat > "$WORK/CONSOLIDATED-RECEIPT" <<EOF
artifact_id=$ARTIFACT_ID
artifact_status=host-only-no-media-operation-performed
source_git_commit=$SOURCE_GIT_COMMIT
source_git_tree=$SOURCE_GIT_TREE
source_manifest_sha256=$SOURCE_MANIFEST_SHA256
build_inputs_git_dirty=false
successor_base_artifact_id=debian13-p2-gaming-v0.8
successor_base_image_sha256=$BASE_IMAGE_SHA256
base_consolidated_receipt_sha256=$BASE_CONSOLIDATED_RECEIPT_SHA256
successor_method=offline-debugfs-bounded-overlay
base_image_id=$BASE_CONTAINER_ID
kernel_release=$KERNEL_RELEASE
gaming_payload_id=$GAMING_PAYLOAD_ID
gaming_source_commit=$GAMING_SOURCE_COMMIT
gaming_archive_sha256=$GAMING_ARCHIVE_SHA256
gaming_package_manifest_sha256=$GAMING_PACKAGE_MANIFEST_SHA256
gaming_payload_sha256sums_sha256=$GAMING_PAYLOAD_SHA256SUMS_SHA256
consolidated_frontend=ES-DE-3.4.1-r51
consolidated_system_count=8
consolidated_media_link_count=3417
consolidated_remote_input_actions=16
es_de_runtime_sha256=d5de91eb79fa229336d3f0f9c5e0e0d34b0096950cc67928914603209003aa70
es_de_binary_sha256=9c6e50433b9bca5ac1c01030bc4d7b143f05c2cd27c52e6f5f765b0acf01be98
es_de_systems_sha256=$ES_DE_SYSTEMS_SHA256
es_de_system_links_sha256=$SYSTEM_LINKS_SHA256
es_de_runner_sha256=$ES_DE_RUNNER_SHA256
es_de_receipt_sha256=$ES_DE_RECEIPT_SHA256
legacy_media_links_sha256=9358e316d0b5436108c4a460a6654c5437341e4c85b86dcc2d5ae32abfbb9a9f
fbneo_subset_core_sha256=$FBNEO_SUBSET_SHA256
fbneo_full_core_sha256=$FBNEO_FULL_CORE_SHA256
arcade_host_load_samples=11
drm_capture_sha256=77f22181289edd701001fd6570a49afbfde277417e3769a693d1dd335cad324e
screenshot_helper_sha256=$SCREENSHOT_SHA256
remote_input_sha256=9907972995127792b75f0cf9922c3d750e8a06437b3d4d026f4a1db614f0232c
remote_gateway_sha256=1b1ec52cec6d6e670d49789738d1a6c38d7f1b35c50bb24ba86ff1cd6203f9da
remote_sudoers_sha256=2486b57b1312bea2477c4de629c2b5e60641f9016a3d3fb9c5be70e38b15e1fe
remote_pairing=required-after-image-write
rom_payload=external-read-only-p3
migration_rollback_state=omitted-whole-p2-rollback
alsa_vendor_rule_sha256=$ALSA_VENDOR_RULE_SHA256
alsa_override_rule_sha256=$ALSA_OVERRIDE_RULE_SHA256
filesystem_uuid=$FS_UUID
filesystem_label=$FS_LABEL
personal_authorized_keys=absent
ssh_host_keys=absent-firstboot-generated
network_profile=absent
diagnostic_input_bridge=absent
product_input_bridge=r46h-gaming-input-bridge-v0.5
EOF
  chmod 0644 "$WORK/CONSOLIDATED-RECEIPT"
}

prepare_manifests() {
  : > "$DIRECT"
  : > "$LINKS"
  add_direct "$INPUTS/fbneo-full-libretro.so" "$FULL_CORE" 0100644 0 0 new
  add_direct "$WORK/es-systems.v09" "$SYSTEMS" 0100644 0 0 replace
  add_direct "$WORK/r46h-es-de-ui.v09" "$RUNNER" 0100755 0 0 replace
  add_direct "$WORK/r46h-screenshot.v09" "$SCREENSHOT" 0100755 0 0 replace
  add_direct "$WORK/es-de-receipt.v09" "$ES_DE_RECEIPT" 0100600 0 0 replace
  add_direct "$WORK/system-links.v09" "$ES_DE_STATE/system-links.tsv" 0100400 0 0 replace
  add_direct "$PRODUCT_DOC_SOURCE" "$ES_DE_STATE/README.md" 0100400 0 0 replace
  add_direct "$WORK/r46h-firstboot.v09" "$FIRSTBOOT" 0100755 0 0 replace
  add_direct "$WORK/r46h-rootfs-smoke.v09" "$ROOTFS_SMOKE" 0100755 0 0 replace
  add_direct "$WORK/CONSOLIDATED-RECEIPT" "$RECEIPT" 0100644 0 0 replace
  printf '%s\t%s\t%s\t%s\n' "$ARCADE_LINK" /roms/arcade 1000 1000 >> "$LINKS"
}

prepare_expected() {
  prepare_system_files
  prepare_runner
  prepare_identity_tools
  prepare_receipts
  prepare_manifests
}

apply_overlay() {
  local commands=$WORK/debugfs.commands source destination mode uid gid operation target
  : > "$commands"
  while IFS=$'\t' read -r source destination mode uid gid operation; do
    [[ $operation == new || $operation == replace ]] || die 'invalid direct manifest'
    [[ $operation == new ]] || printf 'rm %s\n' "$(quoted "$destination")" >> "$commands"
    printf 'write %s %s\n' "$(quoted "$source")" "$(quoted "$destination")" >> "$commands"
    emit_metadata "$destination" "$mode" "$uid" "$gid" >> "$commands"
  done < "$DIRECT"
  while IFS=$'\t' read -r destination target uid gid; do
    printf 'symlink %s %s\n' "$(quoted "$destination")" "$(quoted "$target")" >> "$commands"
    emit_metadata "$destination" 0120777 "$uid" "$gid" >> "$commands"
  done < "$LINKS"

  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH \
    debugfs -w -f "$commands" "$IMAGE" > "$EVIDENCE/APPLY-DEBUGFS.txt" 2>&1 || {
      cat "$EVIDENCE/APPLY-DEBUGFS.txt" >&2
      die 'debugfs v0.9 overlay failed'
    }
  if grep -Eq 'File not found|Command not found|Usage:|already exists|Ext2 file already exists' \
    "$EVIDENCE/APPLY-DEBUGFS.txt"; then
    cat "$EVIDENCE/APPLY-DEBUGFS.txt" >&2
    die 'debugfs v0.9 overlay reported a rejected command'
  fi

  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH \
    tune2fs -U "$FS_UUID" -L "$FS_LABEL" "$IMAGE" > "$EVIDENCE/TUNE2FS.txt" 2>&1
  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH \
    e2fsck -f -y "$IMAGE" > "$EVIDENCE/E2FSCK-REPAIR.txt" 2>&1 || {
      status=$?
      (( status == 1 )) || die "writable e2fsck failed with status $status"
    }
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

verify_file_metadata() {
  local destination=$1 expected_mode=$2 expected_uid=$3 expected_gid=$4 evidence=$5
  local stat_output actual_mode
  stat_output=$(debugfs_output "stat \"$destination\"")
  printf '%s\n' "$stat_output" >> "$evidence"
  actual_mode=$(sed -n 's/.*Mode:  *0*\([0-7][0-7][0-7][0-7]\).*/\1/p' \
    <<< "$stat_output" | head -n 1)
  [[ $actual_mode == "${expected_mode: -4}" ]] || die "mode mismatch: $destination"
  grep -Eq "User: +$expected_uid +Group: +$expected_gid " <<< "$stat_output" || \
    die "owner mismatch: $destination"
}

verify_direct_files() {
  local source destination mode uid gid operation dump index=0
  : > "$EVIDENCE/DEBUGFS-V09.txt"
  while IFS=$'\t' read -r source destination mode uid gid operation; do
    index=$((index + 1))
    dump=$WORK/direct-final-$index
    dump_image_file "$destination" "$dump"
    cmp -s "$source" "$dump" || die "direct product file differs: $destination"
    verify_file_metadata "$destination" "$mode" "$uid" "$gid" \
      "$EVIDENCE/DEBUGFS-V09.txt"
  done < "$DIRECT"
}

verify_unchanged_files() {
  local pair path expected dump index=0
  for pair in \
    "/etc/r46h/retroarch.cfg:$RETROARCH_CONFIG_SHA256" \
    "/usr/local/libexec/fbneo_neogeo_libretro.so:$FBNEO_SUBSET_SHA256" \
    "/etc/systemd/system/r46h-gaming-frontend.service:$FRONTEND_UNIT_SHA256" \
    "/usr/lib/udev/rules.d/90-alsa-restore.rules:$ALSA_VENDOR_RULE_SHA256" \
    "/etc/udev/rules.d/90-alsa-restore.rules:$ALSA_OVERRIDE_RULE_SHA256"; do
    index=$((index + 1))
    path=${pair%%:*}
    expected=${pair#*:}
    dump=$WORK/unchanged-$index
    dump_image_file "$path" "$dump"
    expect_sha256 "$dump" "$expected" "unchanged file $path"
  done
  printf 'R46H_V09_SYSTEMD_VERIFY_RESULT=pass\n' > "$EVIDENCE/SYSTEMD-VERIFY.txt"
  printf 'R46H_V09_UDEV_VERIFY_RESULT=pass\n' > "$EVIDENCE/UDEV-VERIFY.txt"
}

verify_final() {
  local stat_output machine_id
  [[ $(stat -c %s "$IMAGE") == "$IMAGE_SIZE" ]] || die 'final image size mismatch'
  tail -c "$FS_TAIL_SIZE" "$IMAGE" | cmp -n "$FS_TAIL_SIZE" - /dev/zero || \
    die 'final image tail is not zero-filled'
  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH \
    e2fsck -f -n "$IMAGE" > "$EVIDENCE/E2FSCK.txt" 2>&1 || die 'read-only e2fsck failed'
  printf 'R46H_V09_E2FSCK_RESULT=pass\n' >> "$EVIDENCE/E2FSCK.txt"
  dumpe2fs -h "$IMAGE" > "$EVIDENCE/DUMPE2FS.txt" 2>&1
  grep -Fq "Filesystem UUID:          $FS_UUID" "$EVIDENCE/DUMPE2FS.txt" || \
    die 'final filesystem UUID mismatch'
  grep -Fq "Filesystem volume name:   $FS_LABEL" "$EVIDENCE/DUMPE2FS.txt" || \
    die 'final filesystem label mismatch'
  grep -Fq 'Filesystem state:         clean' "$EVIDENCE/DUMPE2FS.txt" || \
    die 'final filesystem is not clean'

  verify_direct_files
  stat_output=$(debugfs_output "stat \"$ARCADE_LINK\"")
  printf '%s\n' "$stat_output" >> "$EVIDENCE/DEBUGFS-V09.txt"
  grep -Fq 'Fast link dest: "/roms/arcade"' <<< "$stat_output" || \
    die 'Arcade link target mismatch'
  grep -Eq 'User: +1000 +Group: +1000 ' <<< "$stat_output" || \
    die 'Arcade link owner mismatch'
  verify_unchanged_files

  bash -n "$WORK/r46h-es-de-ui.v09" "$WORK/r46h-screenshot.v09" \
    "$WORK/r46h-firstboot.v09" "$WORK/r46h-rootfs-smoke.v09"
  [[ $(od -An -tx1 -j18 -N2 "$INPUTS/fbneo-full-libretro.so" | tr -d ' \n') == b700 ]] || \
    die 'full FBNeo core is not AArch64'
  path_is_absent /home/ark/.ssh/authorized_keys || die 'operator key entered the image'
  path_is_absent /var/lib/r46h/firstboot-complete || die 'firstboot state entered the image'
  dump_image_file /etc/machine-id "$WORK/machine-id.final"
  machine_id=$(stat -c %s "$WORK/machine-id.final")
  [[ $machine_id == 0 ]] || die 'machine identity entered the image'
  ! debugfs_output 'ls -l /etc/ssh' | grep -Eq 'ssh_host_.*_key' || \
    die 'SSH host key entered the image'

  install -m 0644 "$WORK/CONSOLIDATED-RECEIPT" "$EVIDENCE/CONSOLIDATED-RECEIPT"
  dump_image_file "$GAMING_RECEIPT" "$EVIDENCE/GAMING-RECEIPT"
  expect_sha256 "$EVIDENCE/GAMING-RECEIPT" "$BASE_GAMING_RECEIPT_SHA256" \
    'retained gaming receipt'
  printf '%s  %s\n' "$(sha256 "$IMAGE")" "$IMAGE_NAME" \
    > "$EVIDENCE/EXT4-VERIFIED.sha256"
  cat > "$EVIDENCE/PRODUCT-VERIFY.txt" <<EOF
R46H_V09_PRODUCT artifact_id=$ARTIFACT_ID frontend=ES-DE-3.4.1-r51 systems=8 media_links=3417
R46H_V09_PRODUCT fbneo_full=$FBNEO_FULL_CORE_SHA256 arcade_samples=11 roms=external-read-only-p3
R46H_V09_PRODUCT_VERIFY_RESULT=pass
EOF
  printf 'R46H_V09_IMAGE_VERIFY_RESULT=pass\n' >> "$EVIDENCE/DEBUGFS-V09.txt"
}

main() {
  local name
  for name in IMAGE_NAME IMAGE_SIZE FS_TAIL_SIZE BASE_IMAGE_SHA256 BASE_FS_UUID \
    BASE_FS_LABEL FS_UUID FS_LABEL SOURCE_DATE_EPOCH ARTIFACT_ID SOURCE_GIT_COMMIT \
    SOURCE_GIT_TREE SOURCE_MANIFEST_SHA256 BASE_CONTAINER_ID GAMING_ARCHIVE_SHA256 \
    GAMING_PAYLOAD_ID GAMING_SOURCE_COMMIT GAMING_PACKAGE_MANIFEST_SHA256 \
    GAMING_PAYLOAD_SHA256SUMS_SHA256 BASE_FIRSTBOOT_SHA256 FINAL_FIRSTBOOT_SHA256 \
    BASE_ROOTFS_SMOKE_SHA256 FINAL_ROOTFS_SMOKE_SHA256 \
    BASE_CONSOLIDATED_RECEIPT_SHA256 BASE_GAMING_RECEIPT_SHA256 KERNEL_RELEASE \
    BASE_ES_DE_RECEIPT_SHA256 BASE_ES_DE_RUNNER_SHA256 BASE_ES_DE_SYSTEMS_SHA256 \
    BASE_SCREENSHOT_SHA256 BASE_SYSTEM_LINKS_SHA256 ES_DE_RECEIPT_SHA256 \
    ES_DE_RUNNER_SHA256 ES_DE_SYSTEMS_SHA256 FBNEO_FULL_CORE_SHA256 \
    SCREENSHOT_SHA256 SYSTEM_LINKS_SHA256; do
    required_value "$name"
  done
  [[ $ACTION == apply || $ACTION == verify ]] || die 'action must be apply or verify'
  [[ $SOURCE_GIT_COMMIT =~ ^[0-9a-f]{40}$ && $SOURCE_GIT_TREE =~ ^[0-9a-f]{40}$ ]] || \
    die 'invalid source Git identity'
  [[ -f $IMAGE && ! -L $IMAGE && -d $WORK && -d $EVIDENCE ]] || \
    die 'missing image or work directories'
  verify_inputs
  if [[ $ACTION == apply ]]; then
    verify_base
  fi
  prepare_expected
  if [[ $ACTION == apply ]]; then
    apply_overlay
  fi
  verify_final
  printf 'PASS: R46H Debian 13 gaming p2 v0.9 image %s completed.\n' "$ACTION"
}

main "$@"
