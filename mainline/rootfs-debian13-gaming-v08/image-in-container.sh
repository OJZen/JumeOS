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
readonly EXPECTED=$WORK/expected
readonly DIRECT=$WORK/direct-files.tsv
readonly LINKS=$WORK/direct-links.tsv
readonly BASE_RECEIPT=/usr/share/r46h-build/CONSOLIDATED-RECEIPT
readonly GAMING_RECEIPT=/var/lib/r46h/gaming-mvp-v0.6-installed
readonly OZONE_RECEIPT=/var/lib/r46h/gaming-ozone-fbneo-v0.1-installed
readonly ES_DE_RECEIPT=/var/lib/r46h/gaming-es-de-v0.1-installed
readonly VENDOR_RULE=/usr/lib/udev/rules.d/90-alsa-restore.rules
readonly OVERRIDE_RULE=/etc/udev/rules.d/90-alsa-restore.rules
readonly FRONTEND_LINK=/etc/systemd/system/multi-user.target.wants/r46h-gaming-frontend.service
readonly FRONTEND_TARGET=/etc/systemd/system/r46h-gaming-frontend.service
readonly VOLUME_LINK=/etc/systemd/system/multi-user.target.wants/r46h-volume-keys.service
readonly VOLUME_TARGET=/etc/systemd/system/r46h-volume-keys.service
readonly CJK_FONT=/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf
readonly CJK_ALIAS=/usr/share/libretro/assets/pkg/chinese-fallback-font.ttf
readonly CJK_ALIAS_TARGET=../../../fonts/truetype/droid/DroidSansFallbackFull.ttf

readonly CONFIG_SOURCE=$SOURCE/mainline/gaming-ozone-fbneo/retroarch.cfg
readonly GAME_UI_SOURCE=$SOURCE/mainline/gaming-ozone-fbneo/r46h-game-ui
readonly VOLUME_HELPER_SOURCE=$SOURCE/mainline/gaming-ozone-fbneo/r46h-volume-keys
readonly VOLUME_UNIT_SOURCE=$SOURCE/mainline/gaming-ozone-fbneo/r46h-volume-keys.service
readonly CORE_OPTIONS_SOURCE="$SOURCE/mainline/gaming-ozone-fbneo/FinalBurn Neo (neogeo subset).opt"
readonly PLAYLIST_SOURCE="$SOURCE/mainline/gaming-ozone-fbneo/SNK - Neo Geo.lpl"
readonly FBNEO_LICENSE_SOURCE=$SOURCE/mainline/gaming-ozone-fbneo/FBNEO-LICENSE.txt
readonly ES_DE_APPEND_SOURCE=$SOURCE/mainline/gaming-es-de/es-de-retroarch.cfg
readonly ES_DE_SETTINGS_SOURCE=$SOURCE/mainline/gaming-es-de/es_settings.xml
readonly ES_DE_SYSTEMS_SOURCE=$SOURCE/mainline/gaming-es-de/es_systems.xml
readonly ES_DE_RUNNER_SOURCE=$SOURCE/mainline/gaming-es-de/r46h-es-de-ui
readonly FRONTEND_UNIT_SOURCE=$SOURCE/mainline/gaming-es-de/r46h-gaming-frontend.service
readonly THEME_SOURCE=$SOURCE/mainline/gaming-es-de/r46h-theme.xml
readonly SYSTEM_LINKS_SOURCE=$SOURCE/mainline/gaming-es-de/system-links.tsv
readonly SCREENSHOT_SOURCE=$SOURCE/mainline/gaming-remote-screen/r46h-screenshot
readonly GATEWAY_SOURCE=$SOURCE/mainline/gaming-remote-input/r46h-screenshot-ssh
readonly SUDOERS_SOURCE=$SOURCE/mainline/gaming-remote-input/r46h-remote-input.sudoers
readonly PRODUCT_DOC_SOURCE=$SOURCE/mainline/rootfs-debian13-gaming-v08/PRODUCT.md

readonly CONFIG_SHA256=0694b9f41220983bdf9d60789b97b2fe115f68474f22f4869a2764513bcf1835
readonly GAME_UI_SHA256=b0a44a7184cef97e2b9597f0d84adacb66617073f9422ef719d98e3465cc77c8
readonly VOLUME_HELPER_SHA256=41bb1c0b9d034c13c881e9a186edc6a748adf6b3e00784ff69a57d0b53af6d6c
readonly VOLUME_UNIT_SHA256=8920a66c77caff09db45c6ac6ca347ceead8d7106bc7b2195cb073a0ce6a9a8c
readonly CORE_OPTIONS_SHA256=4e67299bc6c37cd1ebdfca4e6a42110d5071c62d00e714b952b906ca1fa68976
readonly PLAYLIST_SHA256=5c67fab51b033e0d8e95d9acf16175566ef9905224831259f1c5b33d01b819d4
readonly FBNEO_LICENSE_SHA256=bb2369f1b75f42242968a78191b47ee90f85682224d3ad1ef63044e244b3e202
readonly ES_DE_APPEND_SHA256=2e13e4d33ca23e67d7b52ce6c9c85045b39e3f2ff76bbd6d68c8ca2295ddcb7f
readonly ES_DE_SETTINGS_SHA256=2946f7cde318ba23ca5bb3f07bee09dcef8892b254ef621e49c74bb4b60c69c1
readonly ES_DE_SYSTEMS_SHA256=1f451723d4ce1062157eb0e041ff4c098c5adea98c61e87ddf3cb784dfe630f0
readonly FRONTEND_UNIT_SHA256=df3b6bdc3ba9b3ee65d18b9575c302cfa3aaff4fcc67fe6d12e825565c2ba05c
readonly THEME_SHA256=2816222c88822a900a01bb966c54e27cfe32d7837edf0062d0edaeb70641736b
readonly SYSTEM_LINKS_SHA256=bd5e496ab9bb54f0b9d45b461262b70fd5758d763ea4ff4fb9d06c26c936d73d
readonly GATEWAY_SHA256=1b1ec52cec6d6e670d49789738d1a6c38d7f1b35c50bb24ba86ff1cd6203f9da
readonly SUDOERS_SHA256=2486b57b1312bea2477c4de629c2b5e60641f9016a3d3fb9c5be70e38b15e1fe
readonly OZONE_RECEIPT_SHA256=8acac2c8b8e4295c0235ad1fc7e396e341dcc4b1ba771a053355a98cf8fb73ec
readonly OZONE_INSTALLER_SHA256=ced4dff24bf6f3f017ed54c78d3a636c45f5f0db0a6e1394aba847aa37cbbff1

readonly -a TREE_ROOTS=(
  'opt/r46h'
  'home/ark/.config'
  'home/ark/ROMs'
  'home/ark/ES-DE'
  'home/ark/.cache'
  'var/lib/r46h-gaming-es-de'
  'usr/share/doc/r46h-gaming-ozone-fbneo'
)

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

path_is_regular() {
  debugfs_output "stat \"$1\"" | grep -Fq 'Type: regular'
}

path_is_directory() {
  debugfs_output "stat \"$1\"" | grep -Fq 'Type: directory'
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

add_link() {
  local destination=$1 target=$2 uid=$3 gid=$4
  safe_debugfs_text "$destination"
  safe_debugfs_text "$target"
  printf '%s\t%s\t%s\t%s\n' "$destination" "$target" "$uid" "$gid" >> "$LINKS"
}

safe_relative() {
  local value=$1 component
  [[ -n $value && $value != /* && $value != */ && $value != *//* ]] || return 1
  IFS=/ read -ra components <<< "$value"
  for component in "${components[@]}"; do
    [[ -n $component && $component != . && $component != .. &&
       $component != *$'\t'* && $component != *$'\n'* &&
       $component != *'"'* && $component != *'\\'* ]] || return 1
  done
}

verify_inputs() {
  local members
  [[ -d $INPUTS && ! -L $INPUTS ]] || die 'consolidated product inputs are missing'
  expect_size_sha256 "$INPUTS/es-de-runtime-v3.4.1.tar.gz" 81738580 \
    "$ES_DE_RUNTIME_SHA256" 'ES-DE runtime'
  expect_size_sha256 "$INPUTS/legacy-media-links.tsv" 269434 \
    "$LEGACY_MEDIA_LINKS_SHA256" 'legacy media links'
  expect_size_sha256 "$INPUTS/fbneo-neogeo-libretro.so" 9007520 \
    "$FBNEO_CORE_SHA256" 'FBNeo core'
  expect_size_sha256 "$INPUTS/r46h-drm-capture" 67400 \
    "$DRM_CAPTURE_SHA256" 'DRM capture helper'
  expect_size_sha256 "$INPUTS/r46h-remote-input" 67480 \
    "$REMOTE_INPUT_SHA256" 'remote input helper'
  members=$(find "$INPUTS" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort)
  [[ $members == $'es-de-runtime-v3.4.1.tar.gz\nfbneo-neogeo-libretro.so\nlegacy-media-links.tsv\nr46h-drm-capture\nr46h-remote-input' ]] || \
    die 'unexpected consolidated product input set'

  expect_sha256 "$CONFIG_SOURCE" "$CONFIG_SHA256" 'Ozone config source'
  expect_sha256 "$GAME_UI_SOURCE" "$GAME_UI_SHA256" 'Ozone launcher source'
  expect_sha256 "$VOLUME_HELPER_SOURCE" "$VOLUME_HELPER_SHA256" 'volume helper source'
  expect_sha256 "$VOLUME_UNIT_SOURCE" "$VOLUME_UNIT_SHA256" 'volume unit source'
  expect_sha256 "$CORE_OPTIONS_SOURCE" "$CORE_OPTIONS_SHA256" 'FBNeo options source'
  expect_sha256 "$PLAYLIST_SOURCE" "$PLAYLIST_SHA256" 'FBNeo playlist source'
  expect_sha256 "$FBNEO_LICENSE_SOURCE" "$FBNEO_LICENSE_SHA256" 'FBNeo license source'
  expect_sha256 "$ES_DE_APPEND_SOURCE" "$ES_DE_APPEND_SHA256" 'ES-DE RetroArch source'
  expect_sha256 "$ES_DE_SETTINGS_SOURCE" "$ES_DE_SETTINGS_SHA256" 'ES-DE settings source'
  expect_sha256 "$ES_DE_SYSTEMS_SOURCE" "$ES_DE_SYSTEMS_SHA256" 'ES-DE systems source'
  expect_sha256 "$ES_DE_RUNNER_SOURCE" "$ES_DE_RUNNER_BASE_SHA256" 'ES-DE runner source'
  expect_sha256 "$FRONTEND_UNIT_SOURCE" "$FRONTEND_UNIT_SHA256" 'frontend unit source'
  expect_sha256 "$THEME_SOURCE" "$THEME_SHA256" 'ES-DE theme source'
  expect_sha256 "$SYSTEM_LINKS_SOURCE" "$SYSTEM_LINKS_SHA256" 'system links source'
  expect_sha256 "$SCREENSHOT_SOURCE" "$SCREENSHOT_BASE_SHA256" 'screenshot source'
  expect_sha256 "$GATEWAY_SOURCE" "$GATEWAY_SHA256" 'gateway source'
  expect_sha256 "$SUDOERS_SOURCE" "$SUDOERS_SHA256" 'sudo policy source'

  (cd "$PAYLOAD" && sha256sum -c SHA256SUMS) > "$EVIDENCE/GAMING-PAYLOAD-VERIFY.txt"
  if grep -Fq ': FAILED' "$EVIDENCE/GAMING-PAYLOAD-VERIFY.txt"; then
    die 'retained gaming payload verification failed'
  fi
}

verify_base() {
  local path pair expected
  [[ $(stat -c %s "$IMAGE") == "$IMAGE_SIZE" ]] || die 'base image size mismatch'
  [[ $(sha256 "$IMAGE") == "$BASE_IMAGE_SHA256" ]] || die 'base image digest mismatch'
  dumpe2fs -h "$IMAGE" > "$WORK/base-dumpe2fs.txt" 2>&1
  grep -Fq "Filesystem UUID:          $BASE_FS_UUID" "$WORK/base-dumpe2fs.txt" || \
    die 'base filesystem UUID mismatch'
  grep -Fq "Filesystem volume name:   $BASE_FS_LABEL" "$WORK/base-dumpe2fs.txt" || \
    die 'base filesystem label mismatch'

  for pair in \
    "/etc/r46h/retroarch.cfg:$BASE_CONFIG_SHA256" \
    "/usr/local/sbin/r46h-game-ui:$BASE_RUNNER_SHA256" \
    "/usr/local/libexec/r46h-volume-keys:$BASE_VOLUME_HELPER_SHA256" \
    "/etc/systemd/system/r46h-volume-keys.service:$BASE_VOLUME_UNIT_SHA256" \
    "/etc/systemd/system/r46h-gaming-frontend.service:$BASE_FRONTEND_UNIT_SHA256" \
    "$BASE_RECEIPT:$BASE_CONSOLIDATED_RECEIPT_SHA256" \
    "$GAMING_RECEIPT:$BASE_GAMING_RECEIPT_SHA256" \
    "$CJK_FONT:$CJK_FONT_SHA256"; do
    path=${pair%%:*}
    expected=${pair#*:}
    path_is_regular "$path" || die "base file is missing: $path"
    dump_image_file "$path" "$WORK/base-${path//\//_}"
    expect_sha256 "$WORK/base-${path//\//_}" "$expected" "base file $path"
  done
  dump_image_file /usr/libexec/r46h-firstboot "$WORK/r46h-firstboot.base"
  dump_image_file /usr/local/sbin/r46h-rootfs-smoke "$WORK/r46h-rootfs-smoke.base"
  expect_sha256 "$WORK/r46h-firstboot.base" "$BASE_FIRSTBOOT_SHA256" 'base firstboot tool'
  expect_sha256 "$WORK/r46h-rootfs-smoke.base" "$BASE_ROOTFS_SMOKE_SHA256" \
    'base rootfs smoke tool'

  for path in \
    /opt/r46h /home/ark/.config /home/ark/ROMs /home/ark/ES-DE \
    /home/ark/.cache /var/lib/r46h-gaming-es-de \
    /usr/share/doc/r46h-gaming-ozone-fbneo "$OZONE_RECEIPT" "$ES_DE_RECEIPT" \
    /usr/local/libexec/fbneo_neogeo_libretro.so /usr/local/libexec/r46h-drm-capture \
    /usr/local/libexec/r46h-remote-input /usr/local/bin/r46h-screenshot \
    /usr/local/bin/r46h-screenshot-ssh /etc/sudoers.d/r46h-remote-screen \
    "/home/ark/.local/share/retroarch/playlists/SNK - Neo Geo.lpl" \
    /home/ark/.config/retroarch/r46h-es-de-core-options.cfg \
    /etc/r46h/es-de-systems.xml /etc/r46h/es-de-retroarch.cfg \
    /usr/local/sbin/r46h-es-de-ui \
    "$CJK_ALIAS" /home/ark/.ssh/authorized_keys /var/lib/r46h/firstboot-complete; do
    path_is_absent "$path" || die "base already contains consolidated path: $path"
  done
  debugfs_output "stat \"$FRONTEND_LINK\"" | \
    grep -Fq "Fast link dest: \"$FRONTEND_TARGET\"" || die 'frontend enable link mismatch'
  debugfs_output "stat \"$VOLUME_LINK\"" | \
    grep -Fq "Fast link dest: \"$VOLUME_TARGET\"" || die 'volume enable link mismatch'
}

reconstruct_base_identity() {
  dump_image_file /usr/libexec/r46h-firstboot "$WORK/r46h-firstboot.final-input"
  sed \
    's/debian13-p2-gaming-v0\.8/debian13-p2-gaming-v0.7/g' \
    "$WORK/r46h-firstboot.final-input" > "$WORK/r46h-firstboot.base"
  expect_sha256 "$WORK/r46h-firstboot.base" "$BASE_FIRSTBOOT_SHA256" \
    'reconstructed base firstboot tool'

  dump_image_file /usr/local/sbin/r46h-rootfs-smoke "$WORK/r46h-rootfs-smoke.final-input"
  sed \
    -e "s/$FS_UUID/$BASE_FS_UUID/g" \
    -e 's/debian13-p2-gaming-v0\.8/debian13-p2-gaming-v0.7/g' \
    "$WORK/r46h-rootfs-smoke.final-input" > "$WORK/r46h-rootfs-smoke.base"
  expect_sha256 "$WORK/r46h-rootfs-smoke.base" "$BASE_ROOTFS_SMOKE_SHA256" \
    'reconstructed base rootfs smoke tool'
}

prepare_identity_tools() {
  sed 's/debian13-p2-gaming-v0\.7/debian13-p2-gaming-v0.8/g' \
    "$WORK/r46h-firstboot.base" > "$WORK/r46h-firstboot.v08"
  expect_sha256 "$WORK/r46h-firstboot.v08" "$FINAL_FIRSTBOOT_SHA256" \
    'v0.8 firstboot tool'
  sed \
    -e "s/$BASE_FS_UUID/$FS_UUID/g" \
    -e 's/debian13-p2-gaming-v0\.7/debian13-p2-gaming-v0.8/g' \
    "$WORK/r46h-rootfs-smoke.base" > "$WORK/r46h-rootfs-smoke.v08"
  expect_sha256 "$WORK/r46h-rootfs-smoke.v08" "$FINAL_ROOTFS_SMOKE_SHA256" \
    'v0.8 rootfs smoke tool'
}

prepare_runtime_tree() {
  local archive=$INPUTS/es-de-runtime-v3.4.1.tar.gz runtime
  mkdir -m 0700 "$EXPECTED"
  tar -tzf "$archive" | awk '
    BEGIN { ok=1 }
    /^\// { ok=0 }
    /(^|\/)\.\.($|\/)/ { ok=0 }
    $0 != "opt/" && $0 != "opt/r46h/" && $0 !~ /^opt\/r46h\/es-de(\/|$)/ { ok=0 }
    END { exit ok ? 0 : 1 }
  ' || die 'ES-DE runtime has unsafe members'
  tar -tvzf "$archive" | awk '$1 !~ /^[d-]/ { bad=1 } END { exit bad ? 1 : 0 }' || \
    die 'ES-DE runtime contains unsupported members'
  [[ $(tar -tzf "$archive" | wc -l | tr -d ' ') == 3003 ]] || \
    die 'ES-DE runtime member count mismatch'
  tar -xzf "$archive" -C "$EXPECTED" --no-same-owner
  runtime=$EXPECTED/opt/r46h/es-de
  [[ -x $runtime/bin/es-de && ! -L $runtime/bin/es-de ]] || die 'ES-DE executable missing'
  [[ -z $(find "$runtime" \( -type l -o -type b -o -type c -o -type p -o -type s \) \
    -print -quit) ]] || die 'ES-DE runtime contains unsupported nodes'
  chown -R root:root "$EXPECTED/opt"
  install -o root -g root -m 0644 "$THEME_SOURCE" \
    "$runtime/share/es-de/themes/linear-es-de/theme.xml"
  expect_sha256 "$runtime/bin/es-de" "$ES_DE_BINARY_SHA256" 'ES-DE executable'
  expect_sha256 "$runtime/share/es-de/themes/linear-es-de/theme.xml" "$THEME_SHA256" \
    'installed ES-DE theme'
  grep -Fqx 'ES-DE 3.4.1 (r51)' "$runtime/share/r46h/VERSION" || \
    die 'ES-DE runtime version mismatch'
}

prepare_home_trees() {
  local destination source system target media_count=0 system_count=0
  install -d -o ark -g ark -m 0700 "$EXPECTED/home/ark/.config"
  install -d -o ark -g ark -m 0700 "$EXPECTED/home/ark/.config/retroarch"
  install -d -o ark -g ark -m 0700 "$EXPECTED/home/ark/.config/retroarch/config"
  install -d -o ark -g ark -m 0700 \
    "$EXPECTED/home/ark/.config/retroarch/config/FinalBurn Neo (neogeo subset)"
  install -o ark -g ark -m 0600 "$CORE_OPTIONS_SOURCE" \
    "$EXPECTED/home/ark/.config/retroarch/config/FinalBurn Neo (neogeo subset)/FinalBurn Neo (neogeo subset).opt"
  install -o ark -g ark -m 0600 "$CORE_OPTIONS_SOURCE" \
    "$EXPECTED/home/ark/.config/retroarch/r46h-es-de-core-options.cfg"

  install -d -o ark -g ark -m 0755 "$EXPECTED/home/ark/ROMs" \
    "$EXPECTED/home/ark/ES-DE" \
    "$EXPECTED/home/ark/ES-DE/settings" "$EXPECTED/home/ark/ES-DE/custom_systems" \
    "$EXPECTED/home/ark/ES-DE/downloaded_media"
  install -o ark -g ark -m 0600 "$ES_DE_SETTINGS_SOURCE" \
    "$EXPECTED/home/ark/ES-DE/settings/es_settings.xml"
  ln -s /etc/r46h/es-de-systems.xml \
    "$EXPECTED/home/ark/ES-DE/custom_systems/es_systems.xml"
  chown -h ark:ark "$EXPECTED/home/ark/ES-DE/custom_systems/es_systems.xml"
  while IFS=$'\t' read -r system source; do
    [[ -n $system && ${system:0:1} != '#' ]] || continue
    safe_relative "$system" || die "unsafe system link name: $system"
    [[ $source == /roms/* && $source != *'/../'* ]] || die "unsafe system source: $source"
    target=$EXPECTED/home/ark/ROMs/$system
    [[ ! -e $target && ! -L $target ]] || die "duplicate system link: $system"
    ln -s "$source" "$target"
    chown -h ark:ark "$target"
    system_count=$((system_count + 1))
  done < "$SYSTEM_LINKS_SOURCE"
  [[ $system_count == 7 ]] || die 'system link count mismatch'

  while IFS=$'\t' read -r destination source; do
    [[ -n $destination && ${destination:0:1} != '#' ]] || continue
    safe_relative "$destination" || die "unsafe media destination: $destination"
    [[ $source == /roms/* && $source != *'/../'* ]] || die "unsafe media source: $source"
    target=$EXPECTED/home/ark/ES-DE/downloaded_media/$destination
    [[ ! -e $target && ! -L $target ]] || die "duplicate media link: $destination"
    install -d -o ark -g ark -m 0755 "${target%/*}"
    ln -s "$source" "$target"
    chown -h ark:ark "$target"
    media_count=$((media_count + 1))
  done < "$INPUTS/legacy-media-links.tsv"
  [[ $media_count == 3417 ]] || die 'media link count mismatch'
  find "$EXPECTED/home/ark/ES-DE/downloaded_media" -type d \
    -exec chown ark:ark {} + -exec chmod 0755 {} +

  install -d -o ark -g ark -m 0700 "$EXPECTED/home/ark/.cache" \
    "$EXPECTED/home/ark/.cache/r46h" "$EXPECTED/home/ark/.cache/r46h/screenshots" \
    "$EXPECTED/home/ark/.cache/r46h/screenshots/capture" \
    "$EXPECTED/home/ark/.cache/r46h/screenshots/exports"
}

prepare_state_trees() {
  local runtime=$EXPECTED/opt/r46h/es-de state
  state=$EXPECTED/var/lib/r46h-gaming-es-de/v0.1
  install -d -o root -g root -m 0700 "$EXPECTED/var/lib/r46h-gaming-es-de"
  install -d -o root -g root -m 0700 "$state"
  install -o root -g root -m 0400 "$SYSTEM_LINKS_SOURCE" "$state/system-links.tsv"
  install -o root -g root -m 0400 "$INPUTS/legacy-media-links.tsv" "$state/media-links.tsv"
  install -o root -g root -m 0400 "$PRODUCT_DOC_SOURCE" "$state/README.md"
  (cd "$runtime" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum) \
    > "$state/runtime.sha256"
  chmod 0400 "$state/runtime.sha256"

  install -d -o root -g root -m 0755 \
    "$EXPECTED/usr/share/doc/r46h-gaming-ozone-fbneo"
  install -o root -g root -m 0644 "$FBNEO_LICENSE_SOURCE" \
    "$EXPECTED/usr/share/doc/r46h-gaming-ozone-fbneo/FBNEO-LICENSE.txt"
}

prepare_transformed_scripts() {
  sed "s/$BASE_FS_UUID/$FS_UUID/g" "$ES_DE_RUNNER_SOURCE" > "$WORK/r46h-es-de-ui"
  chmod 0755 "$WORK/r46h-es-de-ui"
  expect_sha256 "$WORK/r46h-es-de-ui" "$ES_DE_RUNNER_SHA256" 'v0.8 ES-DE runner'
  sed \
    -e "s/$BASE_FS_UUID/$FS_UUID/g" \
    -e "s/$ES_DE_RUNNER_BASE_SHA256/$ES_DE_RUNNER_SHA256/g" \
    "$SCREENSHOT_SOURCE" > "$WORK/r46h-screenshot"
  chmod 0755 "$WORK/r46h-screenshot"
  expect_sha256 "$WORK/r46h-screenshot" "$SCREENSHOT_SHA256" 'v0.8 screenshot helper'
}

prepare_component_receipts() {
  local media_count runtime_manifest_sha256 es_de_receipt_sha256
  cat > "$WORK/ozone-receipt" <<EOF
feature_id=r46h-gaming-ozone-fbneo-v0.1
base_config_sha256=99a45beb148e58e40983773b4f5e26d9fb5d7e1bbbf6a7e714a5c352e43c0dba
config_sha256=$CONFIG_SHA256
base_runner_sha256=27d2f987545a3ab20610806923372b41530d41e5e3fc0384614211088d71135c
runner_sha256=$GAME_UI_SHA256
base_volume_helper_sha256=a66f7ee5fa38dec5964a7d7fa5f72940250952ba3858cbac57626d2f84ff5ec2
volume_helper_sha256=$VOLUME_HELPER_SHA256
base_volume_unit_sha256=f654a838d58d859ee0ccfa75ab87fdab75c5bd465891418bc526d1c61abb8c89
volume_unit_sha256=$VOLUME_UNIT_SHA256
core_options_sha256=$CORE_OPTIONS_SHA256
core_sha256=$FBNEO_CORE_SHA256
playlist_sha256=$PLAYLIST_SHA256
license_sha256=$FBNEO_LICENSE_SHA256
source_commit=26f11fa9e43227a04953e20e8c7e4bf322cd53cb
core_info_sha256=2ba4587c30b2c1a81f76325cce4a04305f72869bf5280d6a3c3c7d7cea51142c
mslug_rom_sha256=3ebe7ca4166f956a65ae98d86f9172f8b5d4462efa13723a5ea72fcf59adcbf8
neogeo_bios_sha256=d2d8ab5d5fc5ce41978e40c8db2984d8dd0a37e60c712e20961b80fdbb4c9936
rollback_sha256=1a21775caad50f89bb93c8f4462de742cf0dbfdbcaaef457ad464664032dd64d
installer_sha256=$OZONE_INSTALLER_SHA256
EOF
  chmod 0600 "$WORK/ozone-receipt"
  expect_sha256 "$WORK/ozone-receipt" "$OZONE_RECEIPT_SHA256" 'Ozone receipt'

  runtime_manifest_sha256=$(sha256 \
    "$EXPECTED/var/lib/r46h-gaming-es-de/v0.1/runtime.sha256")
  media_count=$(awk -F '\t' '$1 !~ /^#/ && NF == 2 { count++ } END { print count+0 }' \
    "$INPUTS/legacy-media-links.tsv")
  cat > "$WORK/es-de-receipt" <<EOF
feature_id=r46h-gaming-es-de-v0.1
source=ES-DE-v3.4.1-r51
runtime_archive_sha256=$ES_DE_RUNTIME_SHA256
runtime_manifest_sha256=$runtime_manifest_sha256
es_de_sha256=$ES_DE_BINARY_SHA256
systems_sha256=$ES_DE_SYSTEMS_SHA256
retroarch_append_sha256=$ES_DE_APPEND_SHA256
system_links_sha256=$SYSTEM_LINKS_SHA256
media_links_sha256=$LEGACY_MEDIA_LINKS_SHA256
theme_sha256=$THEME_SHA256
runner_sha256=$ES_DE_RUNNER_SHA256
unit_sha256=$FRONTEND_UNIT_SHA256
cjk_font_sha256=$CJK_FONT_SHA256
media_links_installed=$media_count
media_sources_missing=not-evaluated-p3-external
settings_seeded=yes
core_options_seeded=yes
composition=offline-consolidated-p2-v0.8
EOF
  chmod 0600 "$WORK/es-de-receipt"
  es_de_receipt_sha256=$(sha256 "$WORK/es-de-receipt")

  cat > "$WORK/CONSOLIDATED-RECEIPT" <<EOF
artifact_id=$ARTIFACT_ID
artifact_status=host-only-no-media-operation-performed
source_git_commit=$SOURCE_GIT_COMMIT
source_git_tree=$SOURCE_GIT_TREE
source_manifest_sha256=$SOURCE_MANIFEST_SHA256
build_inputs_git_dirty=false
successor_base_artifact_id=debian13-p2-gaming-v0.7
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
consolidated_system_count=7
consolidated_media_link_count=$media_count
consolidated_remote_input_actions=16
es_de_runtime_sha256=$ES_DE_RUNTIME_SHA256
es_de_binary_sha256=$ES_DE_BINARY_SHA256
es_de_runner_sha256=$ES_DE_RUNNER_SHA256
es_de_receipt_sha256=$es_de_receipt_sha256
legacy_media_links_sha256=$LEGACY_MEDIA_LINKS_SHA256
fbneo_core_sha256=$FBNEO_CORE_SHA256
drm_capture_sha256=$DRM_CAPTURE_SHA256
screenshot_helper_sha256=$SCREENSHOT_SHA256
remote_input_sha256=$REMOTE_INPUT_SHA256
remote_gateway_sha256=$GATEWAY_SHA256
remote_sudoers_sha256=$SUDOERS_SHA256
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

prepare_direct_manifests() {
  : > "$DIRECT"
  : > "$LINKS"
  add_direct "$CONFIG_SOURCE" /etc/r46h/retroarch.cfg 0100644 0 0 replace
  add_direct "$GAME_UI_SOURCE" /usr/local/sbin/r46h-game-ui 0100755 0 0 replace
  add_direct "$VOLUME_HELPER_SOURCE" /usr/local/libexec/r46h-volume-keys 0100755 0 0 replace
  add_direct "$VOLUME_UNIT_SOURCE" /etc/systemd/system/r46h-volume-keys.service 0100644 0 0 replace
  add_direct "$INPUTS/fbneo-neogeo-libretro.so" /usr/local/libexec/fbneo_neogeo_libretro.so 0100644 0 0 new
  add_direct "$PLAYLIST_SOURCE" "/home/ark/.local/share/retroarch/playlists/SNK - Neo Geo.lpl" 0100600 1000 1000 new
  add_direct "$ES_DE_SYSTEMS_SOURCE" /etc/r46h/es-de-systems.xml 0100644 0 0 new
  add_direct "$ES_DE_APPEND_SOURCE" /etc/r46h/es-de-retroarch.cfg 0100644 0 0 new
  add_direct "$WORK/r46h-es-de-ui" /usr/local/sbin/r46h-es-de-ui 0100755 0 0 new
  add_direct "$FRONTEND_UNIT_SOURCE" /etc/systemd/system/r46h-gaming-frontend.service 0100644 0 0 replace
  add_direct "$INPUTS/r46h-drm-capture" /usr/local/libexec/r46h-drm-capture 0100755 0 0 new
  add_direct "$WORK/r46h-screenshot" /usr/local/bin/r46h-screenshot 0100755 0 0 new
  add_direct "$GATEWAY_SOURCE" /usr/local/bin/r46h-screenshot-ssh 0100755 0 0 new
  add_direct "$INPUTS/r46h-remote-input" /usr/local/libexec/r46h-remote-input 0100755 0 0 new
  add_direct "$SUDOERS_SOURCE" /etc/sudoers.d/r46h-remote-screen 0100440 0 0 new
  add_direct "$WORK/ozone-receipt" "$OZONE_RECEIPT" 0100600 0 0 new
  add_direct "$WORK/es-de-receipt" "$ES_DE_RECEIPT" 0100600 0 0 new
  add_direct "$WORK/r46h-firstboot.v08" /usr/libexec/r46h-firstboot 0100755 0 0 replace
  add_direct "$WORK/r46h-rootfs-smoke.v08" /usr/local/sbin/r46h-rootfs-smoke 0100755 0 0 replace
  add_direct "$WORK/CONSOLIDATED-RECEIPT" "$BASE_RECEIPT" 0100644 0 0 replace
  add_link "$CJK_ALIAS" "$CJK_ALIAS_TARGET" 0 0
}

prepare_expected() {
  if [[ $ACTION == apply ]]; then
    :
  else
    reconstruct_base_identity
  fi
  prepare_identity_tools
  prepare_runtime_tree
  prepare_home_trees
  prepare_state_trees
  prepare_transformed_scripts
  prepare_component_receipts
  prepare_direct_manifests
}

emit_tree() {
  local relative=$1 root=$EXPECTED/$relative node destination mode uid gid target
  while IFS= read -r -d '' node; do
    destination=/${node#"$EXPECTED"/}
    printf 'mkdir %s\n' "$(quoted "$destination")"
  done < <(find "$root" -type d -print0 | LC_ALL=C sort -z)
  while IFS= read -r -d '' node; do
    destination=/${node#"$EXPECTED"/}
    if [[ -f $node && ! -L $node ]]; then
      printf 'write %s %s\n' "$(quoted "$node")" "$(quoted "$destination")"
    elif [[ -L $node ]]; then
      target=$(readlink -- "$node")
      printf 'symlink %s %s\n' "$(quoted "$destination")" "$(quoted "$target")"
    fi
  done < <(find "$root" ! -type d -print0 | LC_ALL=C sort -z)
  while IFS= read -r -d '' node; do
    destination=/${node#"$EXPECTED"/}
    mode=$(stat -c %a "$node")
    uid=$(stat -c %u "$node")
    gid=$(stat -c %g "$node")
    [[ $relative == home/ark/* ]] && { uid=1000; gid=1000; }
    if [[ -d $node ]]; then
      mode=0040$mode
    elif [[ -L $node ]]; then
      mode=0120$mode
    else
      mode=0100$mode
    fi
    emit_metadata "$destination" "$mode" "$uid" "$gid"
  done < <(find "$root" ! -type d -print0 | LC_ALL=C sort -z)
  while IFS= read -r -d '' node; do
    destination=/${node#"$EXPECTED"/}
    mode=$(stat -c %a "$node")
    uid=$(stat -c %u "$node")
    gid=$(stat -c %g "$node")
    [[ $relative == home/ark/* ]] && { uid=1000; gid=1000; }
    emit_metadata "$destination" "0040$mode" "$uid" "$gid"
  done < <(find "$root" -type d -print0 | LC_ALL=C sort -zr)
}

apply_overlay() {
  local commands=$WORK/debugfs.commands source destination mode uid gid operation target
  : > "$commands"
  for relative in "${TREE_ROOTS[@]}"; do
    emit_tree "$relative" >> "$commands"
  done
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
  for destination in /etc/r46h /etc/systemd/system /etc/sudoers.d /usr/libexec \
    /usr/local/bin /usr/local/libexec /usr/local/sbin /usr/share/libretro/assets/pkg \
    /usr/share/r46h-build /var/lib/r46h; do
    emit_metadata "$destination" 0040755 0 0 >> "$commands"
  done
  emit_metadata /home/ark/.local/share/retroarch/playlists 0040700 1000 1000 >> "$commands"

  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH \
    debugfs -w -f "$commands" "$IMAGE" > "$EVIDENCE/APPLY-DEBUGFS.txt" 2>&1 || {
      cat "$EVIDENCE/APPLY-DEBUGFS.txt" >&2
      die 'debugfs product overlay failed'
    }
  if grep -Eq 'File not found|Command not found|Usage:|already exists|Ext2 file already exists' \
    "$EVIDENCE/APPLY-DEBUGFS.txt"; then
    cat "$EVIDENCE/APPLY-DEBUGFS.txt" >&2
    die 'debugfs product overlay reported a rejected command'
  fi

  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH \
    tune2fs -U "$FS_UUID" -L "$FS_LABEL" "$IMAGE" > "$EVIDENCE/TUNE2FS.txt" 2>&1
  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH \
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
  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH \
    debugfs -w -f "$WORK/normalize-super.commands" "$IMAGE" \
    > "$EVIDENCE/NORMALIZE-SUPER.txt" 2>&1
}

tree_manifest() {
  local root=$1 output=$2 node relative identity
  : > "$output"
  while IFS= read -r -d '' node; do
    relative=${node#"$root"}
    [[ -n $relative ]] || relative=/
    identity=$(stat -c '%u:%g:%a' "$node")
    if [[ -d $node ]]; then
      printf 'd\t%s\t%s\n' "$relative" "$identity" >> "$output"
    elif [[ -L $node ]]; then
      printf 'l\t%s\t%s\t%s\n' "$relative" "$identity" "$(readlink -- "$node")" >> "$output"
    elif [[ -f $node ]]; then
      printf 'f\t%s\t%s\t%s\n' "$relative" "$identity" "$(sha256 "$node")" >> "$output"
    else
      die "unsupported tree node: $node"
    fi
  done < <(find "$root" -print0 | LC_ALL=C sort -z)
}

verify_tree() {
  local relative=$1 expected=$EXPECTED/$relative dump_parent=$WORK/dump-${relative//\//_}
  local dumped=$dump_parent/${relative##*/}
  mkdir -m 0700 "$dump_parent"
  debugfs -R "rdump \"/$relative\" \"$dump_parent\"" "$IMAGE" \
    > "$WORK/rdump-${relative//\//_}.txt" 2>&1 || die "cannot dump tree: /$relative"
  [[ -d $dumped && ! -L $dumped ]] || die "dumped tree is missing: /$relative"
  tree_manifest "$expected" "$WORK/expected-${relative//\//_}.tsv"
  tree_manifest "$dumped" "$WORK/dumped-${relative//\//_}.tsv"
  cmp -s "$WORK/expected-${relative//\//_}.tsv" "$WORK/dumped-${relative//\//_}.tsv" || \
    die "tree differs from consolidated product: /$relative"
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
  : > "$EVIDENCE/DEBUGFS-V08.txt"
  while IFS=$'\t' read -r source destination mode uid gid operation; do
    index=$((index + 1))
    dump=$WORK/direct-final-$index
    dump_image_file "$destination" "$dump"
    cmp -s "$source" "$dump" || die "direct product file differs: $destination"
    verify_file_metadata "$destination" "$mode" "$uid" "$gid" \
      "$EVIDENCE/DEBUGFS-V08.txt"
  done < "$DIRECT"
}

verify_direct_links() {
  local destination target uid gid stat_output
  while IFS=$'\t' read -r destination target uid gid; do
    stat_output=$(debugfs_output "stat \"$destination\"")
    printf '%s\n' "$stat_output" >> "$EVIDENCE/DEBUGFS-V08.txt"
    grep -Fq "Fast link dest: \"$target\"" <<< "$stat_output" || \
      die "link target mismatch: $destination"
    grep -Eq "User: +$uid +Group: +$gid " <<< "$stat_output" || \
      die "link owner mismatch: $destination"
  done < "$LINKS"
}

verify_product_tools() {
  local runtime=$EXPECTED/opt/r46h/es-de
  install -m 0755 "$GAME_UI_SOURCE" /usr/local/sbin/r46h-game-ui
  install -m 0755 "$VOLUME_HELPER_SOURCE" /usr/local/libexec/r46h-volume-keys
  install -m 0755 "$WORK/r46h-es-de-ui" /usr/local/sbin/r46h-es-de-ui
  install -m 0755 "$GATEWAY_SOURCE" /usr/local/bin/r46h-screenshot-ssh
  install -m 0755 "$WORK/r46h-screenshot" /usr/local/bin/r46h-screenshot
  install -m 0644 "$FRONTEND_UNIT_SOURCE" /etc/systemd/system/r46h-gaming-frontend.service
  install -m 0644 "$VOLUME_UNIT_SOURCE" /etc/systemd/system/r46h-volume-keys.service
  install -m 0755 "$PAYLOAD/files/r46h-gaming-frontend-condition" \
    /usr/local/libexec/r46h-gaming-frontend-condition
  install -m 0755 "$PAYLOAD/files/r46h-input-bridge" \
    /usr/local/libexec/r46h-input-bridge
  install -m 0755 "$PAYLOAD/files/r46h-gaming-input-ready" \
    /usr/local/libexec/r46h-gaming-input-ready
  install -m 0644 "$PAYLOAD/files/r46h-gaming-input.service" \
    /etc/systemd/system/r46h-gaming-input.service
  systemd-analyze verify --man=no r46h-gaming-frontend.service \
    r46h-gaming-input.service r46h-volume-keys.service \
    > "$EVIDENCE/SYSTEMD-VERIFY.txt" 2>&1 || {
      cat "$EVIDENCE/SYSTEMD-VERIFY.txt" >&2
      die 'consolidated service verification failed'
    }
  printf 'R46H_V08_SYSTEMD_VERIFY_RESULT=pass\n' >> "$EVIDENCE/SYSTEMD-VERIFY.txt"
  visudo -cf "$SUDOERS_SOURCE" >/dev/null || die 'remote sudo policy is invalid'
  bash -n "$GAME_UI_SOURCE" "$VOLUME_HELPER_SOURCE" "$WORK/r46h-es-de-ui" \
    "$WORK/r46h-screenshot" "$GATEWAY_SOURCE"
  for binary in "$runtime/bin/es-de" "$INPUTS/fbneo-neogeo-libretro.so" \
    "$INPUTS/r46h-drm-capture" "$INPUTS/r46h-remote-input"; do
    [[ $(od -An -tx1 -j18 -N2 "$binary" | tr -d ' \n') == b700 ]] || \
      die "non-AArch64 product binary: $binary"
  done
}

verify_udev() {
  local root=$WORK/udev-root
  dump_image_file "$VENDOR_RULE" "$WORK/vendor-rule.final"
  dump_image_file "$OVERRIDE_RULE" "$WORK/override-rule.final"
  expect_sha256 "$WORK/vendor-rule.final" "$ALSA_VENDOR_RULE_SHA256" 'vendor ALSA rule'
  expect_sha256 "$WORK/override-rule.final" "$ALSA_OVERRIDE_RULE_SHA256" \
    'override ALSA rule'
  install -d "$root/etc/udev/rules.d" "$root/usr/lib/udev/rules.d"
  install -m 0644 "$WORK/vendor-rule.final" "$root/usr/lib/udev/rules.d/90-alsa-restore.rules"
  install -m 0644 "$WORK/override-rule.final" "$root/etc/udev/rules.d/90-alsa-restore.rules"
  udevadm verify --root="$root" --resolve-names=never > "$EVIDENCE/UDEV-VERIFY.txt" 2>&1 || {
    cat "$EVIDENCE/UDEV-VERIFY.txt" >&2
    die 'ALSA rule precedence verification failed'
  }
  grep -Fq 'Success: 1' "$EVIDENCE/UDEV-VERIFY.txt" || \
    die 'ALSA rule verification success marker missing'
  printf 'R46H_V08_UDEV_VERIFY_RESULT=pass\n' >> "$EVIDENCE/UDEV-VERIFY.txt"
}

verify_final() {
  local relative machine_id
  [[ $(stat -c %s "$IMAGE") == "$IMAGE_SIZE" ]] || die 'final image size mismatch'
  tail -c "$FS_TAIL_SIZE" "$IMAGE" | cmp -n "$FS_TAIL_SIZE" - /dev/zero || \
    die 'final image tail is not zero-filled'
  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH \
    e2fsck -f -n "$IMAGE" > "$EVIDENCE/E2FSCK.txt" 2>&1 || {
      cat "$EVIDENCE/E2FSCK.txt" >&2
      die 'read-only e2fsck failed'
    }
  printf 'R46H_V08_E2FSCK_RESULT=pass\n' >> "$EVIDENCE/E2FSCK.txt"
  dumpe2fs -h "$IMAGE" > "$EVIDENCE/DUMPE2FS.txt" 2>&1
  grep -Fq "Filesystem UUID:          $FS_UUID" "$EVIDENCE/DUMPE2FS.txt" || \
    die 'final filesystem UUID mismatch'
  grep -Fq "Filesystem volume name:   $FS_LABEL" "$EVIDENCE/DUMPE2FS.txt" || \
    die 'final filesystem label mismatch'
  grep -Fq 'Filesystem state:         clean' "$EVIDENCE/DUMPE2FS.txt" || \
    die 'final filesystem is not clean'

  for relative in "${TREE_ROOTS[@]}"; do
    verify_tree "$relative"
  done
  verify_direct_files
  verify_direct_links
  for relative in \
    /home/ark/.config /home/ark/.config/retroarch \
    /home/ark/.config/retroarch/config /home/ark/.cache \
    /home/ark/.cache/r46h /home/ark/.cache/r46h/screenshots; do
    verify_file_metadata "$relative" 0040700 1000 1000 \
      "$EVIDENCE/DEBUGFS-V08.txt"
  done
  for relative in /home/ark/ROMs /home/ark/ES-DE /home/ark/ES-DE/settings \
    /home/ark/ES-DE/custom_systems /home/ark/ES-DE/downloaded_media; do
    verify_file_metadata "$relative" 0040755 1000 1000 \
      "$EVIDENCE/DEBUGFS-V08.txt"
  done
  verify_file_metadata /home/ark/ES-DE/settings/es_settings.xml 0100600 1000 1000 \
    "$EVIDENCE/DEBUGFS-V08.txt"
  verify_file_metadata /home/ark/.config/retroarch/r46h-es-de-core-options.cfg \
    0100600 1000 1000 "$EVIDENCE/DEBUGFS-V08.txt"
  debugfs_output "stat \"$FRONTEND_LINK\"" | \
    grep -Fq "Fast link dest: \"$FRONTEND_TARGET\"" || die 'frontend enable link changed'
  debugfs_output "stat \"$VOLUME_LINK\"" | \
    grep -Fq "Fast link dest: \"$VOLUME_TARGET\"" || die 'volume enable link changed'
  path_is_absent /home/ark/.ssh/authorized_keys || die 'operator SSH key entered the image'
  path_is_absent /var/lib/r46h/firstboot-complete || die 'target firstboot state entered the image'
  path_is_absent /var/lib/r46h-gaming-ozone-fbneo || die 'migration rollback state entered image'
  path_is_absent /var/lib/r46h-remote-screen || die 'remote-screen rollback state entered image'
  path_is_absent /var/lib/r46h-remote-input || die 'remote-input rollback state entered image'
  dump_image_file /etc/machine-id "$WORK/machine-id.final"
  machine_id=$(stat -c %s "$WORK/machine-id.final")
  [[ $machine_id == 0 ]] || die 'machine identity entered the image'
  ! debugfs_output 'ls -l /etc/ssh' | grep -Eq 'ssh_host_.*_key' || \
    die 'SSH host key entered the image'

  verify_product_tools
  verify_udev
  install -m 0644 "$WORK/CONSOLIDATED-RECEIPT" "$EVIDENCE/CONSOLIDATED-RECEIPT"
  dump_image_file "$GAMING_RECEIPT" "$EVIDENCE/GAMING-RECEIPT"
  expect_sha256 "$EVIDENCE/GAMING-RECEIPT" "$BASE_GAMING_RECEIPT_SHA256" \
    'retained gaming receipt'
  printf '%s  %s\n' "$(sha256 "$IMAGE")" "$IMAGE_NAME" \
    > "$EVIDENCE/EXT4-VERIFIED.sha256"
  cat > "$EVIDENCE/PRODUCT-VERIFY.txt" <<EOF
R46H_V08_PRODUCT artifact_id=$ARTIFACT_ID frontend=ES-DE-3.4.1-r51 systems=7 media_links=3417
R46H_V08_PRODUCT remote_screen=paired-key-required remote_input_actions=16 roms=external-read-only-p3
R46H_V08_PRODUCT_VERIFY_RESULT=pass
EOF
  printf 'R46H_V08_IMAGE_VERIFY_RESULT=pass\n' >> "$EVIDENCE/DEBUGFS-V08.txt"
}

main() {
  local name
  for name in IMAGE_NAME IMAGE_SIZE FS_TAIL_SIZE BASE_IMAGE_SHA256 BASE_FS_UUID \
    BASE_FS_LABEL FS_UUID FS_LABEL SOURCE_DATE_EPOCH ARTIFACT_ID SOURCE_GIT_COMMIT \
    SOURCE_GIT_TREE SOURCE_MANIFEST_SHA256 BASE_CONTAINER_ID GAMING_ARCHIVE_SHA256 \
    GAMING_PAYLOAD_ID GAMING_SOURCE_COMMIT GAMING_PACKAGE_MANIFEST_SHA256 \
    GAMING_PAYLOAD_SHA256SUMS_SHA256 ALSA_VENDOR_RULE_SHA256 ALSA_OVERRIDE_RULE_SHA256 \
    BASE_FIRSTBOOT_SHA256 FINAL_FIRSTBOOT_SHA256 BASE_ROOTFS_SMOKE_SHA256 \
    FINAL_ROOTFS_SMOKE_SHA256 BASE_CONSOLIDATED_RECEIPT_SHA256 \
    BASE_GAMING_RECEIPT_SHA256 KERNEL_RELEASE BASE_FRONTEND_UNIT_SHA256 \
    BASE_CONFIG_SHA256 BASE_RUNNER_SHA256 BASE_VOLUME_HELPER_SHA256 \
    BASE_VOLUME_UNIT_SHA256 CJK_FONT_SHA256 DRM_CAPTURE_SHA256 ES_DE_BINARY_SHA256 \
    ES_DE_RUNNER_BASE_SHA256 ES_DE_RUNNER_SHA256 ES_DE_RUNTIME_SHA256 \
    FBNEO_CORE_SHA256 LEGACY_MEDIA_LINKS_SHA256 REMOTE_INPUT_SHA256 \
    SCREENSHOT_BASE_SHA256 SCREENSHOT_SHA256; do
    required_value "$name"
  done
  [[ $ACTION == apply || $ACTION == verify ]] || die 'action must be apply or verify'
  [[ $SOURCE_GIT_COMMIT =~ ^[0-9a-f]{40}$ && $SOURCE_GIT_TREE =~ ^[0-9a-f]{40}$ ]] || \
    die 'invalid source Git identity'
  [[ $SOURCE_DATE_EPOCH =~ ^[1-9][0-9]*$ ]] || die 'invalid source date epoch'
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
  printf 'PASS: R46H Debian 13 gaming p2 v0.8 image %s completed.\n' "$ACTION"
}

main "$@"
