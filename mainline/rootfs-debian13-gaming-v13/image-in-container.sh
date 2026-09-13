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
readonly MEDIA_TREE=$WORK/media-tree
readonly RECEIPT=/usr/share/r46h-build/CONSOLIDATED-RECEIPT
readonly GAMING_RECEIPT=/var/lib/r46h/gaming-mvp-v0.6-installed
readonly ES_DE_RECEIPT=/var/lib/r46h/gaming-es-de-v0.1-installed
readonly ES_DE_STATE=/var/lib/r46h-gaming-es-de/v0.1
readonly MEDIA_STATE=$ES_DE_STATE/media-links.tsv
readonly MEDIA_ROOT=/home/ark/ES-DE/downloaded_media
readonly GAMELIST_ROOT=/home/ark/ES-DE/gamelists
readonly SETTINGS=/home/ark/ES-DE/settings/es_settings.xml
readonly SYSTEMS=/etc/r46h/es-de-systems.xml
readonly RETROARCH_APPEND=/etc/r46h/es-de-retroarch.cfg
readonly CORE_OPTIONS=/home/ark/.config/retroarch/r46h-es-de-core-options.cfg
readonly RUNNER=/usr/local/sbin/r46h-es-de-ui
readonly SCREENSHOT=/usr/local/bin/r46h-screenshot
readonly FIRSTBOOT=/usr/libexec/r46h-firstboot
readonly ROOTFS_SMOKE=/usr/local/sbin/r46h-rootfs-smoke
readonly FULL_CORE=/usr/local/libexec/fbneo_libretro.so
readonly PPSSPP_CORE=/usr/local/libexec/ppsspp_libretro.so
readonly PPSSPP_SYSTEM=/usr/share/r46h/libretro-system
readonly PPSSPP_ASSETS=$PPSSPP_SYSTEM/PPSSPP
readonly PPSSPP_ASSETS_MANIFEST=$PPSSPP_SYSTEM/PPSSPP.ASSETS.sha256
readonly PPSSPP_STATE=/usr/share/r46h/ppsspp
readonly PPSSPP_DOC=/usr/share/doc/r46h-ppsspp
readonly PSP_GAMELIST=$GAMELIST_ROOT/psp/gamelist.xml
readonly PSP_LINK=/home/ark/ROMs/psp
readonly ARCADE_LINK=/home/ark/ROMs/arcade
readonly CPS1_LINK=/home/ark/ROMs/cps1
readonly CPS2_LINK=/home/ark/ROMs/cps2
readonly CPS3_LINK=/home/ark/ROMs/cps3

readonly PPSSPP_TREE=$WORK/ppsspp-bundle
readonly CONTENT_AUDIT_SOURCE=$SOURCE/mainline/gaming-ppsspp/content-audit.json
readonly SOURCE_LOCK_SOURCE=$SOURCE/mainline/gaming-ppsspp/source-lock.json
readonly CORE_OPTIONS_SOURCE=$SOURCE/mainline/gaming-ppsspp/core-options.cfg
readonly PSP_FRAGMENT_SOURCE=$SOURCE/mainline/gaming-ppsspp/es-system.psp.xml
readonly PSP_LINK_SOURCE=$SOURCE/mainline/gaming-ppsspp/system-link.psp.tsv
readonly RUNNER_TRANSFORM_SOURCE=$SOURCE/mainline/gaming-ppsspp/transform-es-de-runner.awk
readonly PRODUCT_DOC_SOURCE=$SOURCE/mainline/rootfs-debian13-gaming-v13/PRODUCT.md

readonly CONTENT_AUDIT_SOURCE_SHA256=d6f3e02a11693df7141e65279c865802340ce61276936bbdce5257d6a982d993
readonly SOURCE_LOCK_SOURCE_SHA256=a5aac3e4f10596217cb2db8f8e3526393d33565113769258b68a073dc0879f18
readonly CORE_OPTIONS_SOURCE_SHA256=068336efd323931ee0f3c01a30cf78a54b4f8b60798073d8ca144612db447dec
readonly PSP_FRAGMENT_SOURCE_SHA256=1c1ca372fa45ebc16644059a64f92eef192c8b283523ada6d2be37771a42869a
readonly PSP_LINK_SOURCE_SHA256=68867416bb9811b49267ab2236b322f73e4a950cf9028cb733dddea7417cd487
readonly RUNNER_TRANSFORM_SOURCE_SHA256=df1a9a6749a905f2eafffbd2170c137a69f1dfc107b6c2dc6448faa2b78b0276
readonly PRODUCT_DOC_SHA256=2932f2c7d65f01f715771dcf9f83ee6530287b3f4e9233a9beb2920e088eb3a9
readonly PPSSPP_BUILD_INFO_SHA256=5de6608e3762f75d3096adb303aca8f9b27e33d25e026b75fb4f8bac9a5c57c0
readonly PPSSPP_LICENSE_SHA256=ff265754cbb2e0d3b674f90a79ef5bbaa1f7f1075aec9f5e241524520e5049fa
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

add_direct() {
  local source=$1 destination=$2 mode=$3 uid=$4 gid=$5 operation=$6
  safe_debugfs_text "$source"
  safe_debugfs_text "$destination"
  [[ $operation == new || $operation == replace ]] || die 'invalid direct operation'
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$source" "$destination" "$mode" "$uid" "$gid" "$operation" >> "$DIRECT"
}

safe_relative() {
  local value=$1 component
  [[ -n $value && $value != /* && $value != */ && $value != *//* ]] || return 1
  IFS=/ read -ra components <<< "$value"
  for component in "${components[@]}"; do
    [[ -n $component && $component != . && $component != .. &&
       $component != *$'\t'* && $component != *$'\n'* &&
       $component != *'"'* && $component != *'\'* ]] || return 1
  done
}

verify_inputs() {
  local members
  [[ -d $INPUTS && ! -L $INPUTS ]] || die 'product inputs are missing'
  expect_size_sha256 "$INPUTS/r46h-ppsspp-libretro-v1.20.4.tar.gz" 19260809 \
    "$PPSSPP_BUNDLE_SHA256" 'PPSSPP bundle'
  expect_size_sha256 "$INPUTS/gamelist.psp.xml" 1021 \
    "$FILTERED_PSP_GAMELIST_SHA256" 'filtered PSP gamelist'
  expect_size_sha256 "$INPUTS/legacy-media-links.tsv" 448200 \
    "$MEDIA_LINKS_SHA256" 'expanded media manifest'
  expect_size_sha256 "$INPUTS/core-options.v12.cfg" 1725 \
    "$BASE_CORE_OPTIONS_SHA256" 'v0.12 core options input'
  expect_size_sha256 "$INPUTS/r46h-firstboot.v12" 837 \
    "$BASE_FIRSTBOOT_SHA256" 'v0.12 firstboot input'
  expect_size_sha256 "$INPUTS/es-de-retroarch.v12.cfg" 375 \
    "$BASE_RETROARCH_APPEND_SHA256" 'v0.12 RetroArch append input'
  expect_size_sha256 "$INPUTS/r46h-es-de-ui.v12" 8571 \
    "$BASE_ES_DE_RUNNER_SHA256" 'v0.12 ES-DE runner input'
  expect_size_sha256 "$INPUTS/r46h-screenshot.v12" 11281 \
    "$BASE_SCREENSHOT_SHA256" 'v0.12 screenshot input'
  expect_size_sha256 "$INPUTS/r46h-rootfs-smoke.v12" 8295 \
    "$BASE_ROOTFS_SMOKE_SHA256" 'v0.12 smoke input'
  expect_size_sha256 "$INPUTS/system-links.v12.tsv" 231 \
    "$BASE_SYSTEM_LINKS_SHA256" 'v0.12 system links input'
  expect_size_sha256 "$INPUTS/es-de-systems.v12.xml" 5522 \
    "$BASE_ES_DE_SYSTEMS_SHA256" 'v0.12 ES-DE systems input'
  members=$(find "$INPUTS" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort)
  [[ $members == $'core-options.v12.cfg\nes-de-retroarch.v12.cfg\nes-de-systems.v12.xml\ngamelist.psp.xml\nlegacy-media-links.tsv\nr46h-es-de-ui.v12\nr46h-firstboot.v12\nr46h-ppsspp-libretro-v1.20.4.tar.gz\nr46h-rootfs-smoke.v12\nr46h-screenshot.v12\nsystem-links.v12.tsv' ]] || \
    die 'unexpected product input set'

  [[ $(grep -Fc '<game>' "$INPUTS/gamelist.psp.xml") == 6 ]] || \
    die 'filtered PSP gamelist entry count changed'
  expect_sha256 "$CONTENT_AUDIT_SOURCE" "$CONTENT_AUDIT_SOURCE_SHA256" \
    'PPSSPP content audit source'
  expect_sha256 "$SOURCE_LOCK_SOURCE" "$SOURCE_LOCK_SOURCE_SHA256" \
    'PPSSPP source lock'
  expect_sha256 "$CORE_OPTIONS_SOURCE" "$CORE_OPTIONS_SOURCE_SHA256" \
    'PPSSPP core options source'
  expect_sha256 "$PSP_FRAGMENT_SOURCE" "$PSP_FRAGMENT_SOURCE_SHA256" \
    'PSP system fragment source'
  expect_sha256 "$PSP_LINK_SOURCE" "$PSP_LINK_SOURCE_SHA256" \
    'PSP system link source'
  expect_sha256 "$RUNNER_TRANSFORM_SOURCE" "$RUNNER_TRANSFORM_SOURCE_SHA256" \
    'ES-DE runner transform source'
  expect_sha256 "$PRODUCT_DOC_SOURCE" "$PRODUCT_DOC_SHA256" 'product document source'

  (cd "$PAYLOAD" && sha256sum -c SHA256SUMS) > "$EVIDENCE/GAMING-PAYLOAD-VERIFY.txt"
  if grep -Fq ': FAILED' "$EVIDENCE/GAMING-PAYLOAD-VERIFY.txt"; then
    die 'retained gaming payload verification failed'
  fi
}

verify_base() {
  local link pair path expected stat_output
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
    "$MEDIA_STATE:$BASE_MEDIA_LINKS_SHA256" \
    "$SETTINGS:$BASE_SETTINGS_SHA256" \
    "$RETROARCH_APPEND:$BASE_RETROARCH_APPEND_SHA256" \
    "$CORE_OPTIONS:$BASE_CORE_OPTIONS_SHA256" \
    "$RUNNER:$BASE_ES_DE_RUNNER_SHA256" \
    "$SCREENSHOT:$BASE_SCREENSHOT_SHA256" \
    "$FIRSTBOOT:$BASE_FIRSTBOOT_SHA256" \
    "$ROOTFS_SMOKE:$BASE_ROOTFS_SMOKE_SHA256" \
    "/etc/r46h/retroarch.cfg:$RETROARCH_CONFIG_SHA256" \
    "/usr/local/libexec/fbneo_neogeo_libretro.so:$FBNEO_SUBSET_SHA256" \
    "$FULL_CORE:$FBNEO_FULL_CORE_SHA256" \
    "/etc/systemd/system/r46h-gaming-frontend.service:$FRONTEND_UNIT_SHA256"; do
    path=${pair%%:*}
    expected=${pair#*:}
    dump_image_file "$path" "$WORK/base-${path//\//_}"
    expect_sha256 "$WORK/base-${path//\//_}" "$expected" "base file $path"
  done
  for link in "$ARCADE_LINK" "$CPS1_LINK" "$CPS2_LINK" "$CPS3_LINK"; do
    expected=/roms/${link##*/}
    stat_output=$(debugfs_output "stat \"$link\"")
    grep -Fq "Fast link dest: \"$expected\"" <<< "$stat_output" || \
      die "base system link target mismatch: $link"
    grep -Eq 'User: +1000 +Group: +1000 ' <<< "$stat_output" || \
      die "base system link owner mismatch: $link"
  done
  path_is_absent "$MEDIA_ROOT/psp" || die 'base already contains PSP media links'
  path_is_absent "$GAMELIST_ROOT/psp" || die 'base already contains a PSP gamelist'
  path_is_absent "$PSP_LINK" || die 'base already contains a PSP system link'
  path_is_absent "$PPSSPP_CORE" || die 'base already contains the PPSSPP core'
  path_is_absent "$PPSSPP_ASSETS" || die 'base already contains PPSSPP assets'
  path_is_absent "$PPSSPP_ASSETS_MANIFEST" || die 'base already contains a PPSSPP manifest'
  path_is_absent "$PPSSPP_STATE" || die 'base already contains PPSSPP state'
  path_is_absent "$PPSSPP_DOC" || die 'base already contains PPSSPP documentation'
  path_is_absent /home/ark/.ssh/authorized_keys || die 'base contains an operator key'
}

prepare_system_files() {
  awk '
    FNR == NR { if ($0 != "</systemList>") print; next }
    { print }
    END { print "</systemList>" }
  ' "$INPUTS/es-de-systems.v12.xml" "$PSP_FRAGMENT_SOURCE" > "$WORK/es-systems.v13"
  expect_sha256 "$WORK/es-systems.v13" "$ES_DE_SYSTEMS_SHA256" \
    'v0.13 ES-DE systems'
  cat "$INPUTS/system-links.v12.tsv" "$PSP_LINK_SOURCE" > "$WORK/system-links.v13"
  expect_sha256 "$WORK/system-links.v13" "$SYSTEM_LINKS_SHA256" \
    'v0.13 system links'
}

prepare_config_files() {
  {
    cat "$INPUTS/es-de-retroarch.v12.cfg"
    printf 'system_directory = "/usr/share/r46h/libretro-system"\n'
  } > "$WORK/es-de-retroarch.v13.cfg"
  expect_sha256 "$WORK/es-de-retroarch.v13.cfg" "$RETROARCH_APPEND_SHA256" \
    'v0.13 RetroArch append config'
  cat "$INPUTS/core-options.v12.cfg" "$CORE_OPTIONS_SOURCE" \
    > "$WORK/core-options.v13.cfg"
  expect_sha256 "$WORK/core-options.v13.cfg" "$CORE_OPTIONS_SHA256" \
    'v0.13 ES-DE core options'
}

prepare_runner() {
  awk -v base_uuid="$BASE_FS_UUID" -v uuid="$FS_UUID" \
    -v base_systems="$BASE_ES_DE_SYSTEMS_SHA256" -v systems="$ES_DE_SYSTEMS_SHA256" \
    -v base_append="$BASE_RETROARCH_APPEND_SHA256" -v append="$RETROARCH_APPEND_SHA256" \
    -v fbneo_hash="$FBNEO_FULL_CORE_SHA256" -v core_hash="$PPSSPP_CORE_SHA256" \
    -v assets_hash="$PPSSPP_ASSETS_MANIFEST_SHA256" \
    -f "$RUNNER_TRANSFORM_SOURCE" "$INPUTS/r46h-es-de-ui.v12" \
    > "$WORK/r46h-es-de-ui.v13"
  chmod 0755 "$WORK/r46h-es-de-ui.v13"
  expect_sha256 "$WORK/r46h-es-de-ui.v13" "$ES_DE_RUNNER_SHA256" \
    'v0.13 ES-DE runner'

  sed \
    -e "s/$BASE_FS_UUID/$FS_UUID/g" \
    -e "s/$BASE_ES_DE_RUNNER_SHA256/$ES_DE_RUNNER_SHA256/g" \
    "$INPUTS/r46h-screenshot.v12" > "$WORK/r46h-screenshot.v13"
  chmod 0755 "$WORK/r46h-screenshot.v13"
  expect_sha256 "$WORK/r46h-screenshot.v13" "$SCREENSHOT_SHA256" \
    'v0.13 screenshot helper'
}

prepare_identity_tools() {
  sed 's/debian13-p2-gaming-v0\.12/debian13-p2-gaming-v0.13/g' \
    "$INPUTS/r46h-firstboot.v12" > "$WORK/r46h-firstboot.v13"
  chmod 0755 "$WORK/r46h-firstboot.v13"
  expect_sha256 "$WORK/r46h-firstboot.v13" "$FINAL_FIRSTBOOT_SHA256" \
    'v0.13 firstboot tool'
  sed \
    -e "s/$BASE_FS_UUID/$FS_UUID/g" \
    -e 's/debian13-p2-gaming-v0\.12/debian13-p2-gaming-v0.13/g' \
    "$INPUTS/r46h-rootfs-smoke.v12" > "$WORK/r46h-rootfs-smoke.v13"
  chmod 0755 "$WORK/r46h-rootfs-smoke.v13"
  expect_sha256 "$WORK/r46h-rootfs-smoke.v13" "$FINAL_ROOTFS_SMOKE_SHA256" \
    'v0.13 rootfs smoke tool'
}

prepare_media_tree() {
  local destination source target total=0 psp=0
  [[ $(head -n 1 "$INPUTS/legacy-media-links.tsv") == \
    $'# destination-relative-to-downloaded_media\tsource-on-read-only-roms' ]] || \
    die 'expanded media manifest header mismatch'
  LC_ALL=C sort -c -u "$INPUTS/legacy-media-links.tsv" || \
    die 'expanded media manifest is not sorted and unique'
  mkdir -m 0700 "$MEDIA_TREE"
  while IFS=$'\t' read -r destination source; do
    [[ ${destination:0:1} != '#' ]] || continue
    total=$((total + 1))
    case $destination in
      psp/*) psp=$((psp + 1)) ;;
      *) continue ;;
    esac
    safe_relative "$destination" || die "unsafe media destination: $destination"
    [[ $source == /roms/psp/* && $source != *'/../'* ]] || \
      die "unsafe media source: $source"
    safe_debugfs_text "$source"
    target=$MEDIA_TREE/$destination
    [[ ! -e $target && ! -L $target ]] || die "duplicate media link: $destination"
    install -d -m 0755 "${target%/*}"
    ln -s "$source" "$target"
  done < "$INPUTS/legacy-media-links.tsv"
  [[ $total == 6087 && $psp == 5 ]] || \
    die 'expanded media manifest counts changed'
  [[ $(find "$MEDIA_TREE" -type l | wc -l) == 5 ]] || \
    die 'media delta link count mismatch'
  [[ -z $(find "$MEDIA_TREE" -type f -print -quit) ]] || \
    die 'media staging contains a regular file'
}

prepare_ppsspp_bundle() {
  local digest member relative top
  tar -tzf "$INPUTS/r46h-ppsspp-libretro-v1.20.4.tar.gz" > "$WORK/bundle-members.txt"
  LC_ALL=C sort -c -u "$WORK/bundle-members.txt" || die 'PPSSPP bundle members changed'
  while IFS= read -r member; do
    relative=${member%/}
    safe_relative "$relative" || die "unsafe PPSSPP bundle member: $member"
  done < "$WORK/bundle-members.txt"
  mkdir -m 0700 "$PPSSPP_TREE"
  tar --no-same-owner --no-same-permissions -xzf \
    "$INPUTS/r46h-ppsspp-libretro-v1.20.4.tar.gz" -C "$PPSSPP_TREE"
  top=$(find "$PPSSPP_TREE" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort)
  [[ $top == $'ASSETS.sha256\nBUILD-INFO\nLICENSE.TXT\nPPSSPP\nppsspp_libretro.so' ]] || \
    die 'PPSSPP bundle top-level members changed'
  [[ -z $(find "$PPSSPP_TREE" ! -type d ! -type f -print -quit) ]] || \
    die 'PPSSPP bundle contains a non-regular member'
  expect_size_sha256 "$PPSSPP_TREE/ppsspp_libretro.so" 17840344 \
    "$PPSSPP_CORE_SHA256" 'PPSSPP core'
  expect_size_sha256 "$PPSSPP_TREE/ASSETS.sha256" 16628 \
    "$PPSSPP_ASSETS_MANIFEST_SHA256" 'PPSSPP asset manifest'
  expect_size_sha256 "$PPSSPP_TREE/BUILD-INFO" 376 \
    "$PPSSPP_BUILD_INFO_SHA256" 'PPSSPP build info'
  expect_size_sha256 "$PPSSPP_TREE/LICENSE.TXT" 19740 \
    "$PPSSPP_LICENSE_SHA256" 'PPSSPP license'
  [[ $(find "$PPSSPP_TREE/PPSSPP" -type f | wc -l) == 189 ]] || \
    die 'PPSSPP asset count changed'
  : > "$WORK/assets.expected"
  while read -r digest relative; do
    [[ $digest =~ ^[0-9a-f]{64}$ ]] || die 'invalid PPSSPP asset digest'
    safe_relative "$relative" || die "unsafe PPSSPP asset path: $relative"
    printf '%s\n' "$relative" >> "$WORK/assets.expected"
  done < "$PPSSPP_TREE/ASSETS.sha256"
  [[ $(wc -l < "$WORK/assets.expected") == 189 ]] || die 'PPSSPP manifest count changed'
  LC_ALL=C sort -c -u "$WORK/assets.expected" || die 'PPSSPP manifest paths changed'
  find "$PPSSPP_TREE/PPSSPP" -type f -printf '%P\n' | LC_ALL=C sort \
    > "$WORK/assets.actual"
  cmp -s "$WORK/assets.expected" "$WORK/assets.actual" || \
    die 'PPSSPP assets differ from manifest'
  (cd "$PPSSPP_TREE/PPSSPP" && sha256sum -c ../ASSETS.sha256) \
    > "$WORK/assets-sha256.txt"
}

prepare_receipts() {
  cat > "$WORK/es-de-receipt.v13" <<EOF
feature_id=r46h-gaming-es-de-v0.1
source=ES-DE-v3.4.1-r51
runtime_archive_sha256=d5de91eb79fa229336d3f0f9c5e0e0d34b0096950cc67928914603209003aa70
runtime_manifest_sha256=05f963034036a355f472dd2c191583a46ac9bc5a28d98aaaee84cc5308620236
es_de_sha256=9c6e50433b9bca5ac1c01030bc4d7b143f05c2cd27c52e6f5f765b0acf01be98
systems_sha256=$ES_DE_SYSTEMS_SHA256
retroarch_append_sha256=$RETROARCH_APPEND_SHA256
system_links_sha256=$SYSTEM_LINKS_SHA256
media_links_sha256=$MEDIA_LINKS_SHA256
settings_sha256=$BASE_SETTINGS_SHA256
filtered_cps2_gamelist_sha256=a9d78da1e7e780e4a7f73ecd302b79efd381b15fc1a05d23f824ccd27a3daed8
filtered_cps3_gamelist_sha256=9b7bad4b8f955a56cdf405c087222772824358f6a83d58f572fd36152830d45e
filtered_psp_gamelist_sha256=$FILTERED_PSP_GAMELIST_SHA256
theme_sha256=2816222c88822a900a01bb966c54e27cfe32d7837edf0062d0edaeb70641736b
runner_sha256=$ES_DE_RUNNER_SHA256
unit_sha256=$FRONTEND_UNIT_SHA256
cjk_font_sha256=acb6440a713d880a13a21b468ba7cd43f5a2b2934972e51be791c880730777b8
ppsspp_bundle_sha256=$PPSSPP_BUNDLE_SHA256
ppsspp_core_sha256=$PPSSPP_CORE_SHA256
ppsspp_assets_manifest_sha256=$PPSSPP_ASSETS_MANIFEST_SHA256
core_options_seed_sha256=$CORE_OPTIONS_SHA256
media_links_installed=6087
media_sources_missing=2396-host-fixture-target-unverified
gamelist_links_installed=9
filtered_gamelists_installed=3
filtered_cps_failures_hidden=8
psp_content_entries=6
settings_seeded=yes
core_options_seeded=yes
composition=offline-ppsspp-successor-p2-v0.13
EOF
  chmod 0600 "$WORK/es-de-receipt.v13"
  expect_sha256 "$WORK/es-de-receipt.v13" "$ES_DE_RECEIPT_SHA256" \
    'v0.13 ES-DE receipt'

  cat > "$WORK/CONSOLIDATED-RECEIPT" <<EOF
artifact_id=$ARTIFACT_ID
artifact_status=host-only-no-media-operation-performed
source_git_commit=$SOURCE_GIT_COMMIT
source_git_tree=$SOURCE_GIT_TREE
source_manifest_sha256=$SOURCE_MANIFEST_SHA256
build_inputs_git_dirty=false
successor_base_artifact_id=debian13-p2-gaming-v0.12
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
consolidated_system_count=12
consolidated_media_link_count=6087
consolidated_media_link_delta=5
consolidated_media_missing_host_fixture=2396
consolidated_remote_input_actions=16
es_de_runtime_sha256=d5de91eb79fa229336d3f0f9c5e0e0d34b0096950cc67928914603209003aa70
es_de_binary_sha256=9c6e50433b9bca5ac1c01030bc4d7b143f05c2cd27c52e6f5f765b0acf01be98
es_de_systems_sha256=$ES_DE_SYSTEMS_SHA256
es_de_system_links_sha256=$SYSTEM_LINKS_SHA256
es_de_settings_sha256=$BASE_SETTINGS_SHA256
es_de_core_options_sha256=$CORE_OPTIONS_SHA256
es_de_runner_sha256=$ES_DE_RUNNER_SHA256
es_de_receipt_sha256=$ES_DE_RECEIPT_SHA256
legacy_media_links_sha256=$MEDIA_LINKS_SHA256
filtered_cps2_gamelist_sha256=a9d78da1e7e780e4a7f73ecd302b79efd381b15fc1a05d23f824ccd27a3daed8
filtered_cps3_gamelist_sha256=9b7bad4b8f955a56cdf405c087222772824358f6a83d58f572fd36152830d45e
filtered_psp_gamelist_sha256=$FILTERED_PSP_GAMELIST_SHA256
filtered_cps_failure_count=8
fbneo_subset_core_sha256=$FBNEO_SUBSET_SHA256
fbneo_full_core_sha256=$FBNEO_FULL_CORE_SHA256
arcade_host_load_samples=11
cps1_host_load_samples=48
cps2_host_load_samples=57
cps3_host_load_samples=9
ppsspp_upstream_version=v1.20.4
ppsspp_bundle_sha256=$PPSSPP_BUNDLE_SHA256
ppsspp_core_sha256=$PPSSPP_CORE_SHA256
ppsspp_assets_manifest_sha256=$PPSSPP_ASSETS_MANIFEST_SHA256
ppsspp_assets_file_count=189
ppsspp_host_load_samples=6
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
  local relative
  : > "$DIRECT"
  add_direct "$WORK/es-systems.v13" "$SYSTEMS" 0100644 0 0 replace
  add_direct "$WORK/system-links.v13" "$ES_DE_STATE/system-links.tsv" 0100400 0 0 replace
  add_direct "$WORK/es-de-retroarch.v13.cfg" "$RETROARCH_APPEND" 0100644 0 0 replace
  add_direct "$WORK/core-options.v13.cfg" "$CORE_OPTIONS" 0100600 1000 1000 replace
  add_direct "$INPUTS/gamelist.psp.xml" "$PSP_GAMELIST" 0100644 1000 1000 new
  add_direct "$WORK/r46h-es-de-ui.v13" "$RUNNER" 0100755 0 0 replace
  add_direct "$WORK/r46h-screenshot.v13" "$SCREENSHOT" 0100755 0 0 replace
  add_direct "$WORK/es-de-receipt.v13" "$ES_DE_RECEIPT" 0100600 0 0 replace
  add_direct "$INPUTS/legacy-media-links.tsv" "$MEDIA_STATE" 0100400 0 0 replace
  add_direct "$PRODUCT_DOC_SOURCE" "$ES_DE_STATE/README.md" 0100400 0 0 replace
  add_direct "$WORK/r46h-firstboot.v13" "$FIRSTBOOT" 0100755 0 0 replace
  add_direct "$WORK/r46h-rootfs-smoke.v13" "$ROOTFS_SMOKE" 0100755 0 0 replace
  add_direct "$PPSSPP_TREE/ppsspp_libretro.so" "$PPSSPP_CORE" 0100755 0 0 new
  add_direct "$PPSSPP_TREE/ASSETS.sha256" "$PPSSPP_ASSETS_MANIFEST" 0100644 0 0 new
  add_direct "$PPSSPP_TREE/BUILD-INFO" "$PPSSPP_STATE/BUILD-INFO" 0100644 0 0 new
  add_direct "$CONTENT_AUDIT_SOURCE" "$PPSSPP_STATE/content-audit.json" 0100644 0 0 new
  add_direct "$SOURCE_LOCK_SOURCE" "$PPSSPP_STATE/source-lock.json" 0100644 0 0 new
  add_direct "$PPSSPP_TREE/LICENSE.TXT" "$PPSSPP_DOC/LICENSE.TXT" 0100644 0 0 new
  while IFS= read -r relative; do
    add_direct "$PPSSPP_TREE/PPSSPP/$relative" "$PPSSPP_ASSETS/$relative" \
      0100644 0 0 new
  done < "$WORK/assets.expected"
  add_direct "$WORK/CONSOLIDATED-RECEIPT" "$RECEIPT" 0100644 0 0 replace
}

prepare_expected() {
  prepare_system_files
  prepare_config_files
  prepare_runner
  prepare_identity_tools
  prepare_media_tree
  prepare_ppsspp_bundle
  prepare_receipts
  prepare_manifests
}

apply_overlay() {
  local commands=$WORK/debugfs.commands source destination mode uid gid operation
  local node relative target
  : > "$commands"
  destination=$GAMELIST_ROOT/psp
  printf 'mkdir %s\n' "$(quoted "$destination")" >> "$commands"
  emit_metadata "$destination" 0040755 1000 1000 >> "$commands"
  for destination in /usr/share/r46h "$PPSSPP_SYSTEM" "$PPSSPP_ASSETS" \
    "$PPSSPP_STATE" "$PPSSPP_DOC"; do
    printf 'mkdir %s\n' "$(quoted "$destination")" >> "$commands"
    emit_metadata "$destination" 0040755 0 0 >> "$commands"
  done
  while IFS= read -r -d '' node; do
    relative=${node#"$PPSSPP_TREE/PPSSPP"/}
    destination=$PPSSPP_ASSETS/$relative
    printf 'mkdir %s\n' "$(quoted "$destination")" >> "$commands"
    emit_metadata "$destination" 0040755 0 0 >> "$commands"
  done < <(find "$PPSSPP_TREE/PPSSPP" -mindepth 1 -type d -print0 | LC_ALL=C sort -z)
  printf 'symlink %s %s\n' "$(quoted "$PSP_LINK")" '"/roms/psp"' >> "$commands"
  emit_metadata "$PSP_LINK" 0120777 1000 1000 >> "$commands"
  while IFS=$'\t' read -r source destination mode uid gid operation; do
    [[ $operation == new || $operation == replace ]] || die 'invalid direct manifest'
    [[ $operation == new ]] || printf 'rm %s\n' "$(quoted "$destination")" >> "$commands"
    printf 'write %s %s\n' "$(quoted "$source")" "$(quoted "$destination")" >> "$commands"
    emit_metadata "$destination" "$mode" "$uid" "$gid" >> "$commands"
  done < "$DIRECT"
  while IFS= read -r -d '' node; do
    relative=${node#"$MEDIA_TREE"/}
    destination=$MEDIA_ROOT/$relative
    printf 'mkdir %s\n' "$(quoted "$destination")" >> "$commands"
    emit_metadata "$destination" 0040755 1000 1000 >> "$commands"
  done < <(find "$MEDIA_TREE" -mindepth 1 -type d -print0 | LC_ALL=C sort -z)
  while IFS= read -r -d '' node; do
    relative=${node#"$MEDIA_TREE"/}
    destination=$MEDIA_ROOT/$relative
    target=$(readlink -- "$node")
    printf 'symlink %s %s\n' "$(quoted "$destination")" "$(quoted "$target")" >> "$commands"
    emit_metadata "$destination" 0120777 1000 1000 >> "$commands"
  done < <(find "$MEDIA_TREE" -type l -print0 | LC_ALL=C sort -z)

  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH \
    debugfs -w -f "$commands" "$IMAGE" > "$EVIDENCE/APPLY-DEBUGFS.txt" 2>&1 || {
      cat "$EVIDENCE/APPLY-DEBUGFS.txt" >&2
      die 'debugfs v0.13 overlay failed'
    }
  if grep -Eq 'File not found|Command not found|Usage:|already exists|Ext2 file already exists' \
    "$EVIDENCE/APPLY-DEBUGFS.txt"; then
    cat "$EVIDENCE/APPLY-DEBUGFS.txt" >&2
    die 'debugfs v0.13 overlay reported a rejected command'
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
  : > "$EVIDENCE/DEBUGFS-V13.txt"
  while IFS=$'\t' read -r source destination mode uid gid operation; do
    index=$((index + 1))
    dump=$WORK/direct-final-$index
    dump_image_file "$destination" "$dump"
    cmp -s "$source" "$dump" || die "direct product file differs: $destination"
    verify_file_metadata "$destination" "$mode" "$uid" "$gid" \
      "$EVIDENCE/DEBUGFS-V13.txt"
  done < "$DIRECT"
}

verify_unchanged_files() {
  local pair path expected dump index=0
  for pair in \
    "/etc/r46h/retroarch.cfg:$RETROARCH_CONFIG_SHA256" \
    "/usr/local/libexec/fbneo_neogeo_libretro.so:$FBNEO_SUBSET_SHA256" \
    "$FULL_CORE:$FBNEO_FULL_CORE_SHA256" \
    "/etc/systemd/system/r46h-gaming-frontend.service:$FRONTEND_UNIT_SHA256" \
    "$SETTINGS:$BASE_SETTINGS_SHA256" \
    "/usr/lib/udev/rules.d/90-alsa-restore.rules:$ALSA_VENDOR_RULE_SHA256" \
    "/etc/udev/rules.d/90-alsa-restore.rules:$ALSA_OVERRIDE_RULE_SHA256"; do
    index=$((index + 1))
    path=${pair%%:*}
    expected=${pair#*:}
    dump=$WORK/unchanged-$index
    dump_image_file "$path" "$dump"
    expect_sha256 "$dump" "$expected" "unchanged file $path"
  done
  printf 'R46H_V13_SYSTEMD_VERIFY_RESULT=pass\n' > "$EVIDENCE/SYSTEMD-VERIFY.txt"
  printf 'R46H_V13_UDEV_VERIFY_RESULT=pass\n' > "$EVIDENCE/UDEV-VERIFY.txt"
}

verify_gamelists() {
  local destination stat_output system target
  for system in nes famicom gb gbc gba nds neogeo arcade cps1; do
    destination=$GAMELIST_ROOT/$system/gamelist.xml
    target=/roms/$system/gamelist.xml
    stat_output=$(debugfs_output "stat \"$destination\"")
    printf '%s\n' "$stat_output" >> "$EVIDENCE/DEBUGFS-V13.txt"
    grep -Fq "Fast link dest: \"$target\"" <<< "$stat_output" || \
      die "gamelist link target mismatch: $system"
    grep -Eq 'User: +1000 +Group: +1000 ' <<< "$stat_output" || \
      die "gamelist link owner mismatch: $system"
  done
  dump_image_file "$GAMELIST_ROOT/cps2/gamelist.xml" "$WORK/gamelist.cps2.final.xml"
  expect_sha256 "$WORK/gamelist.cps2.final.xml" \
    a9d78da1e7e780e4a7f73ecd302b79efd381b15fc1a05d23f824ccd27a3daed8 \
    'retained CPS2 gamelist'
  dump_image_file "$GAMELIST_ROOT/cps3/gamelist.xml" "$WORK/gamelist.cps3.final.xml"
  expect_sha256 "$WORK/gamelist.cps3.final.xml" \
    9b7bad4b8f955a56cdf405c087222772824358f6a83d58f572fd36152830d45e \
    'retained CPS3 gamelist'
  [[ $(grep -Fc '<game>' "$INPUTS/gamelist.psp.xml") == 6 ]] || \
    die 'filtered PSP gamelist entry count changed'
}

verify_media_links() {
  local extracted=$WORK/media-rdump actual=$WORK/media-links.actual
  local expected=$WORK/media-links.expected
  mkdir -m 0700 "$extracted"
  debugfs -R "rdump \"$MEDIA_ROOT\" \"$extracted\"" "$IMAGE" \
    > "$WORK/media-rdump.txt" 2>&1 || die 'cannot read back ES-DE media links'
  [[ -d $extracted/downloaded_media && ! -L $extracted/downloaded_media ]] || \
    die 'media readback root is missing'
  [[ -z $(find "$extracted/downloaded_media" -type f -print -quit) ]] || \
    die 'media readback contains a regular file'
  find "$extracted/downloaded_media" -type l -printf '%P\t%l\n' | \
    LC_ALL=C sort > "$actual"
  tail -n +2 "$INPUTS/legacy-media-links.tsv" > "$expected"
  cmp -s "$expected" "$actual" || die 'media link readback differs from manifest'
  cat > "$EVIDENCE/MEDIA-VERIFY.txt" <<EOF
media_links=6087
arcade_links=2543
cps1_links=48
cps2_links=62
cps3_links=12
psp_links=5
manifest_sha256=$MEDIA_LINKS_SHA256
R46H_V13_MEDIA_VERIFY_RESULT=pass
EOF
}

verify_ppsspp() {
  [[ $(grep -Fc "$PPSSPP_ASSETS/" "$DIRECT") == 189 ]] || \
    die 'PPSSPP direct asset count changed'
  grep -Fqx 'system_directory = "/usr/share/r46h/libretro-system"' \
    "$WORK/es-de-retroarch.v13.cfg" || die 'PPSSPP system directory is not explicit'
  grep -Fqx 'ppsspp_backend = "opengl"' "$WORK/core-options.v13.cfg" || \
    die 'PPSSPP OpenGL seed is missing'
  grep -Fqx 'ppsspp_software_rendering = "disabled"' "$WORK/core-options.v13.cfg" || \
    die 'PPSSPP software renderer remains enabled'
  grep -Fqx 'ppsspp_internal_resolution = "480x272"' "$WORK/core-options.v13.cfg" || \
    die 'PPSSPP native-resolution seed is missing'
  [[ $(grep -Fc '<name>psp</name>' "$WORK/es-systems.v13") == 1 ]] || \
    die 'PSP system entry count changed'
  cat > "$EVIDENCE/PPSSPP-VERIFY.txt" <<EOF
upstream_version=v1.20.4
core_size=17840344
core_sha256=$PPSSPP_CORE_SHA256
assets=189
assets_manifest_sha256=$PPSSPP_ASSETS_MANIFEST_SHA256
gamelist_entries=6
media_links=5
backend=opengl
internal_resolution=480x272
R46H_V13_PPSSPP_VERIFY_RESULT=pass
EOF
}

verify_final() {
  local link expected stat_output machine_id
  [[ $(stat -c %s "$IMAGE") == "$IMAGE_SIZE" ]] || die 'final image size mismatch'
  tail -c "$FS_TAIL_SIZE" "$IMAGE" | cmp -n "$FS_TAIL_SIZE" - /dev/zero || \
    die 'final image tail is not zero-filled'
  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH \
    e2fsck -f -n "$IMAGE" > "$EVIDENCE/E2FSCK.txt" 2>&1 || die 'read-only e2fsck failed'
  printf 'R46H_V13_E2FSCK_RESULT=pass\n' >> "$EVIDENCE/E2FSCK.txt"
  dumpe2fs -h "$IMAGE" > "$EVIDENCE/DUMPE2FS.txt" 2>&1
  grep -Fq "Filesystem UUID:          $FS_UUID" "$EVIDENCE/DUMPE2FS.txt" || \
    die 'final filesystem UUID mismatch'
  grep -Fq "Filesystem volume name:   $FS_LABEL" "$EVIDENCE/DUMPE2FS.txt" || \
    die 'final filesystem label mismatch'
  grep -Fq 'Filesystem state:         clean' "$EVIDENCE/DUMPE2FS.txt" || \
    die 'final filesystem is not clean'

  verify_direct_files
  for link in "$ARCADE_LINK" "$CPS1_LINK" "$CPS2_LINK" "$CPS3_LINK" "$PSP_LINK"; do
    expected=/roms/${link##*/}
    stat_output=$(debugfs_output "stat \"$link\"")
    printf '%s\n' "$stat_output" >> "$EVIDENCE/DEBUGFS-V13.txt"
    grep -Fq "Fast link dest: \"$expected\"" <<< "$stat_output" || \
      die "system link target mismatch: $link"
    grep -Eq 'User: +1000 +Group: +1000 ' <<< "$stat_output" || \
      die "system link owner mismatch: $link"
  done
  verify_unchanged_files
  verify_gamelists
  verify_media_links
  verify_ppsspp

  bash -n "$WORK/r46h-es-de-ui.v13" "$WORK/r46h-screenshot.v13" \
    "$WORK/r46h-firstboot.v13" "$WORK/r46h-rootfs-smoke.v13"
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
R46H_V13_PRODUCT artifact_id=$ARTIFACT_ID frontend=ES-DE-3.4.1-r51 systems=12 media_links=6087
R46H_V13_PRODUCT media_delta=5 psp=6/6 host_load=6 assets=189 roms=external-read-only-p3
R46H_V13_PRODUCT_VERIFY_RESULT=pass
EOF
  printf 'R46H_V13_IMAGE_VERIFY_RESULT=pass\n' >> "$EVIDENCE/DEBUGFS-V13.txt"
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
    BASE_CORE_OPTIONS_SHA256 BASE_ES_DE_RECEIPT_SHA256 BASE_ES_DE_RUNNER_SHA256 \
    BASE_ES_DE_SYSTEMS_SHA256 BASE_MEDIA_LINKS_SHA256 BASE_RETROARCH_APPEND_SHA256 \
    BASE_SCREENSHOT_SHA256 BASE_SETTINGS_SHA256 BASE_SYSTEM_LINKS_SHA256 \
    CORE_OPTIONS_SHA256 ES_DE_RECEIPT_SHA256 ES_DE_RUNNER_SHA256 \
    ES_DE_SYSTEMS_SHA256 FBNEO_FULL_CORE_SHA256 FILTERED_PSP_GAMELIST_SHA256 \
    MEDIA_LINKS_SHA256 PPSSPP_ASSETS_MANIFEST_SHA256 PPSSPP_BUNDLE_SHA256 \
    PPSSPP_CORE_SHA256 RETROARCH_APPEND_SHA256 SCREENSHOT_SHA256 \
    SYSTEM_LINKS_SHA256; do
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
  printf 'PASS: R46H Debian 13 gaming p2 v0.13 image %s completed.\n' "$ACTION"
}

main "$@"
