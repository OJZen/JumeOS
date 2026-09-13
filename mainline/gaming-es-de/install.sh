#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG
umask 077

readonly FEATURE_ID=r46h-gaming-es-de-v0.1
readonly EXPECTED_RELEASE=6.12.99-r46h-mainline-v0.15-gaming-product
readonly EXPECTED_ROOT_PARTUUID=c9f931c9-02
readonly EXPECTED_ROOT_UUID=d3130007-46a4-4d56-9001-000000000007
readonly PAYLOAD_DIR=/run/r46h-gaming-es-de-v0.1
readonly RUNTIME_ARCHIVE=$PAYLOAD_DIR/r46h-es-de-runtime-v3.4.1.tar.gz
readonly RUNTIME_ARCHIVE_SHA256=d5de91eb79fa229336d3f0f9c5e0e0d34b0096950cc67928914603209003aa70
readonly RUNTIME_ARCHIVE_SIZE=81738580
readonly ES_DE_SHA256=9c6e50433b9bca5ac1c01030bc4d7b143f05c2cd27c52e6f5f765b0acf01be98
readonly ES_DE_VERSION='ES-DE 3.4.1 (r51)'
readonly SETTINGS_SHA256=2946f7cde318ba23ca5bb3f07bee09dcef8892b254ef621e49c74bb4b60c69c1
readonly SYSTEMS_SHA256=1f451723d4ce1062157eb0e041ff4c098c5adea98c61e87ddf3cb784dfe630f0
readonly RETROARCH_APPEND_SHA256=2e13e4d33ca23e67d7b52ce6c9c85045b39e3f2ff76bbd6d68c8ca2295ddcb7f
readonly SYSTEM_LINKS_SHA256=bd5e496ab9bb54f0b9d45b461262b70fd5758d763ea4ff4fb9d06c26c936d73d
readonly MEDIA_LINKS_SHA256=9358e316d0b5436108c4a460a6654c5437341e4c85b86dcc2d5ae32abfbb9a9f
readonly THEME_SHA256=2816222c88822a900a01bb966c54e27cfe32d7837edf0062d0edaeb70641736b
readonly RUNNER_SHA256=5b9edd8705d26ac2b58285baee9d2025354a0343936b5360313e664edd5bafa1
readonly UNIT_SHA256=df3b6bdc3ba9b3ee65d18b9575c302cfa3aaff4fcc67fe6d12e825565c2ba05c
readonly ROLLBACK_SHA256=ac58bbc0429b78481a5853431dd1b0bf82b2b1237fc412977beca09ad7487068
readonly OZONE_RECEIPT_SHA256=8acac2c8b8e4295c0235ad1fc7e396e341dcc4b1ba771a053355a98cf8fb73ec
readonly ACCEPTED_CONFIG_SHA256=0694b9f41220983bdf9d60789b97b2fe115f68474f22f4869a2764513bcf1835
readonly ACCEPTED_RUNNER_SHA256=b0a44a7184cef97e2b9597f0d84adacb66617073f9422ef719d98e3465cc77c8
readonly FBNEO_CORE_SHA256=8bb17a551f3eeeb384ab00a5c5375d30eb63807afe5b6c1ba1d3f78220732bdb
readonly FBNEO_OPTIONS_SHA256=4e67299bc6c37cd1ebdfca4e6a42110d5071c62d00e714b952b906ca1fa68976
readonly CJK_FONT_SHA256=acb6440a713d880a13a21b468ba7cd43f5a2b2934972e51be791c880730777b8
readonly PREVIOUS_UNIT_SHA256=2fec9c8cb0be8ee724c5e9d44d78971ab83e57a4d5cbba9d3931d457262ff9ed

readonly OZONE_RECEIPT=/var/lib/r46h/gaming-ozone-fbneo-v0.1-installed
readonly ACCEPTED_CONFIG=/etc/r46h/retroarch.cfg
readonly ACCEPTED_RUNNER=/usr/local/sbin/r46h-game-ui
readonly FBNEO_CORE=/usr/local/libexec/fbneo_neogeo_libretro.so
readonly FBNEO_OPTIONS='/home/ark/.config/retroarch/config/FinalBurn Neo (neogeo subset)/FinalBurn Neo (neogeo subset).opt'
readonly ES_CORE_OPTIONS=/home/ark/.config/retroarch/r46h-es-de-core-options.cfg
readonly CJK_FONT=/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf
readonly CJK_ALIAS=/usr/share/libretro/assets/pkg/chinese-fallback-font.ttf
readonly CJK_ALIAS_TARGET=../../../fonts/truetype/droid/DroidSansFallbackFull.ttf
readonly RUNTIME=/opt/r46h/es-de
readonly THEME_RELATIVE=share/es-de/themes/linear-es-de/theme.xml
readonly SETTINGS=/home/ark/ES-DE/settings/es_settings.xml
readonly SYSTEMS=/etc/r46h/es-de-systems.xml
readonly SYSTEMS_LINK=/home/ark/ES-DE/custom_systems/es_systems.xml
readonly RETROARCH_APPEND=/etc/r46h/es-de-retroarch.cfg
readonly RUNNER=/usr/local/sbin/r46h-es-de-ui
readonly UNIT=/etc/systemd/system/r46h-gaming-frontend.service
readonly ROLLBACK=/usr/local/sbin/r46h-es-de-rollback
readonly STATE_PARENT=/var/lib/r46h-gaming-es-de
readonly STATE_DIR=$STATE_PARENT/v0.1
readonly RECEIPT=/var/lib/r46h/gaming-es-de-v0.1-installed
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count

runtime_stage=""
state_stage=""
receipt_stage=""
frontend_was_active=0
transaction_active=0
runtime_published=0
state_published=0
settings_seeded=no
core_options_seeded=no
cjk_alias_installed=0

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  printf 'usage: sudo /bin/bash %s --installer-sha256 HEX\n' "$PAYLOAD_DIR/install.sh"
}

hash_is() {
  local path=$1 expected=$2
  [[ -f $path && ! -L $path ]] &&
    [[ $(sha256sum "$path" | awk '{print $1}') == "$expected" ]]
}

safe_relative() {
  local path=$1
  [[ -n $path && $path != /* && $path != *$'\t'* && $path != *$'\n'* && $path != *$'\r'* ]] &&
    [[ /$path/ != */../* && /$path/ != */./* ]]
}

remove_link_set() {
  local manifest=$1 base=$2 destination source
  [[ -f $manifest && ! -L $manifest ]] || return 1
  while IFS=$'\t' read -r destination source; do
    [[ -n $destination && ${destination:0:1} != '#' ]] || continue
    safe_relative "$destination" || return 1
    target=$base/$destination
    [[ ! -e $target && ! -L $target ]] && continue
    [[ -L $target && $(readlink -- "$target") == "$source" ]] || return 1
    rm -f -- "$target" || return 1
  done < "$manifest"
}

cleanup() {
  local status=$? cleanup_ok=1
  trap - EXIT INT TERM HUP
  set +e
  trap '' INT TERM HUP
  rm -f -- "$receipt_stage"
  if (( transaction_active == 1 )); then
    systemctl stop r46h-gaming-frontend.service >/dev/null 2>&1 || true
    if [[ -f ${STATE_DIR:-}/media-links.tsv ]]; then
      remove_link_set "$STATE_DIR/media-links.tsv" /home/ark/ES-DE/downloaded_media || cleanup_ok=0
    elif [[ -f ${state_stage:-}/media-links.tsv ]]; then
      remove_link_set "$state_stage/media-links.tsv" /home/ark/ES-DE/downloaded_media || cleanup_ok=0
    fi
    if [[ -f ${STATE_DIR:-}/system-links.tsv ]]; then
      remove_link_set "$STATE_DIR/system-links.tsv" /home/ark/ROMs || cleanup_ok=0
    elif [[ -f ${state_stage:-}/system-links.tsv ]]; then
      remove_link_set "$state_stage/system-links.tsv" /home/ark/ROMs || cleanup_ok=0
    fi
    if [[ -L $SYSTEMS_LINK && $(readlink -- "$SYSTEMS_LINK") == "$SYSTEMS" ]]; then
      rm -f -- "$SYSTEMS_LINK" || cleanup_ok=0
    elif [[ -e $SYSTEMS_LINK || -L $SYSTEMS_LINK ]]; then
      cleanup_ok=0
    fi
    if (( cjk_alias_installed == 1 )); then
      if [[ -L $CJK_ALIAS && $(readlink -- "$CJK_ALIAS") == "$CJK_ALIAS_TARGET" ]]; then
        rm -f -- "$CJK_ALIAS" || cleanup_ok=0
      elif [[ -e $CJK_ALIAS || -L $CJK_ALIAS ]]; then
        cleanup_ok=0
      fi
    fi
    if [[ $core_options_seeded == yes ]]; then
      if hash_is "$ES_CORE_OPTIONS" "$FBNEO_OPTIONS_SHA256" &&
         [[ $(stat -c '%u:%g:%a:%h' "$ES_CORE_OPTIONS") == 1000:1000:600:1 ]]; then
        rm -f -- "$ES_CORE_OPTIONS" || cleanup_ok=0
      elif [[ -e $ES_CORE_OPTIONS || -L $ES_CORE_OPTIONS ]]; then
        cleanup_ok=0
      fi
    fi
    rm -f -- "$RUNNER" "$SYSTEMS" "$RETROARCH_APPEND" "$ROLLBACK" "$RECEIPT"
    if (( runtime_published == 1 )) && [[ -d $RUNTIME && ! -L $RUNTIME ]]; then
      find "$RUNTIME" -depth -delete || cleanup_ok=0
    fi
    previous=${STATE_DIR:-}/previous-frontend.service
    [[ -f $previous ]] || previous=${state_stage:-}/previous-frontend.service
    if [[ -f $previous ]] && hash_is "$previous" "$PREVIOUS_UNIT_SHA256"; then
      install -o root -g root -m 0644 "$previous" "$UNIT" || cleanup_ok=0
      systemctl daemon-reload || cleanup_ok=0
    else
      cleanup_ok=0
    fi
    if (( frontend_was_active == 1 )); then
      systemctl start r46h-gaming-frontend.service >/dev/null 2>&1 || cleanup_ok=0
    fi
  fi
  if [[ -n $runtime_stage && -d $runtime_stage && ! -L $runtime_stage ]]; then
    find "$runtime_stage" -depth -delete || cleanup_ok=0
  fi
  if (( cleanup_ok == 1 )); then
    if (( state_published == 1 )) && [[ -d $STATE_DIR && ! -L $STATE_DIR ]]; then
      find "$STATE_DIR" -depth -delete || cleanup_ok=0
    elif [[ -n $state_stage && -d $state_stage && ! -L $state_stage ]]; then
      find "$state_stage" -depth -delete || cleanup_ok=0
    fi
    rmdir -- "$STATE_PARENT" 2>/dev/null || true
  else
    printf 'ERROR: automatic restore incomplete; keep %s for recovery\n' "$STATE_DIR" >&2
    status=1
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

[[ $# == 2 && $1 == --installer-sha256 ]] || { usage >&2; exit 2; }
installer_sha256=$2
[[ $installer_sha256 =~ ^[0-9a-f]{64}$ ]] || die 'invalid installer SHA-256'
(( EUID == 0 )) || die 'root is required'
[[ ${BASH_SOURCE[0]} == "$PAYLOAD_DIR/install.sh" ]] || die 'run the staged payload installer'
[[ -d $PAYLOAD_DIR && ! -L $PAYLOAD_DIR ]] || die 'unsafe payload directory'
[[ $(stat -c '%u:%g:%a' "$PAYLOAD_DIR") == 0:0:700 ]] || die 'unsafe payload directory identity'
payload_members=$(find "$PAYLOAD_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort)
[[ $payload_members == $'README.md\nSHA256SUMS\nes-de-retroarch.cfg\nes_settings.xml\nes_systems.xml\ninstall.sh\nlegacy-media-links.tsv\nr46h-es-de-runtime-v3.4.1.tar.gz\nr46h-es-de-ui\nr46h-gaming-frontend.service\nr46h-theme.xml\nrollback.sh\nsystem-links.tsv' ]] || \
  die 'unexpected payload member set'
while IFS= read -r -d '' path; do
  [[ -f $path && ! -L $path ]] || die "unsafe payload member: $path"
  [[ $(stat -c '%u:%g:%a:%h' "$path") == 0:0:600:1 ]] || \
    die "unsafe payload member identity: $path"
done < <(find "$PAYLOAD_DIR" -mindepth 1 -maxdepth 1 -print0)
hash_is "$PAYLOAD_DIR/install.sh" "$installer_sha256" || die 'installer SHA-256 mismatch'
[[ $(uname -r) == "$EXPECTED_RELEASE" ]] || die 'unexpected running kernel'
[[ $(findmnt -rn -o PARTUUID /) == "$EXPECTED_ROOT_PARTUUID" ]] || die 'unexpected root partition'
[[ $(findmnt -rn -o UUID /) == "$EXPECTED_ROOT_UUID" ]] || die 'unexpected root filesystem'
[[ ,$(findmnt -rn -o OPTIONS /), == *,rw,* ]] || die 'p2 is not writable'
[[ ,$(findmnt -rn -o OPTIONS /roms), == *,ro,* ]] || die '/roms is not read-only'
[[ $(cat "$EXT4_ERRORS") == 0 ]] || die 'p2 already reports ext4 errors'
[[ -z $(systemctl --failed --no-legend --plain) ]] || die 'systemd has failed units'
[[ $(id -u ark) == 1000 ]] || die 'unexpected ark identity'

for specification in \
  "$RUNTIME_ARCHIVE:$RUNTIME_ARCHIVE_SHA256" \
  "$PAYLOAD_DIR/es_settings.xml:$SETTINGS_SHA256" \
  "$PAYLOAD_DIR/es_systems.xml:$SYSTEMS_SHA256" \
  "$PAYLOAD_DIR/es-de-retroarch.cfg:$RETROARCH_APPEND_SHA256" \
  "$PAYLOAD_DIR/system-links.tsv:$SYSTEM_LINKS_SHA256" \
  "$PAYLOAD_DIR/legacy-media-links.tsv:$MEDIA_LINKS_SHA256" \
  "$PAYLOAD_DIR/r46h-theme.xml:$THEME_SHA256" \
  "$PAYLOAD_DIR/r46h-es-de-ui:$RUNNER_SHA256" \
  "$PAYLOAD_DIR/r46h-gaming-frontend.service:$UNIT_SHA256" \
  "$PAYLOAD_DIR/rollback.sh:$ROLLBACK_SHA256"; do
  path=${specification%%:*}
  digest=${specification#*:}
  hash_is "$path" "$digest" || die "payload identity mismatch: $path"
done
[[ $(stat -c '%s' "$RUNTIME_ARCHIVE") == "$RUNTIME_ARCHIVE_SIZE" ]] || die 'runtime archive size mismatch'
hash_is "$OZONE_RECEIPT" "$OZONE_RECEIPT_SHA256" || die 'accepted Ozone receipt changed'
hash_is "$ACCEPTED_CONFIG" "$ACCEPTED_CONFIG_SHA256" || die 'accepted RetroArch config changed'
hash_is "$ACCEPTED_RUNNER" "$ACCEPTED_RUNNER_SHA256" || die 'accepted Ozone runner changed'
hash_is "$FBNEO_CORE" "$FBNEO_CORE_SHA256" || die 'accepted FBNeo core changed'
hash_is "$FBNEO_OPTIONS" "$FBNEO_OPTIONS_SHA256" || die 'accepted FBNeo options changed'
hash_is "$CJK_FONT" "$CJK_FONT_SHA256" || die 'RetroArch Chinese font changed'
[[ ! -e $CJK_ALIAS && ! -L $CJK_ALIAS ]] || die 'RetroArch Chinese font alias already exists'
hash_is "$UNIT" "$PREVIOUS_UNIT_SHA256" || die 'active frontend unit is not the accepted Ozone unit'
[[ ! -e $RECEIPT && ! -L $RECEIPT ]] || die 'ES-DE receipt already exists'
[[ ! -e $STATE_DIR && ! -L $STATE_DIR ]] || die 'ES-DE state already exists'
[[ ! -e $RUNTIME && ! -L $RUNTIME ]] || die 'ES-DE runtime already exists'
[[ ! -e $RUNNER && ! -L $RUNNER ]] || die 'ES-DE launcher already exists'
[[ ! -e $SYSTEMS && ! -L $SYSTEMS ]] || die 'ES-DE systems config already exists'
[[ ! -e $RETROARCH_APPEND && ! -L $RETROARCH_APPEND ]] || die 'ES-DE RetroArch append config already exists'
[[ ! -e $SYSTEMS_LINK && ! -L $SYSTEMS_LINK ]] || die 'custom systems link already exists'
if [[ -e $ES_CORE_OPTIONS || -L $ES_CORE_OPTIONS ]]; then
  [[ -f $ES_CORE_OPTIONS && ! -L $ES_CORE_OPTIONS ]] || die 'unsafe existing ES-DE core options'
  [[ $(stat -c '%u:%g:%a:%h' "$ES_CORE_OPTIONS") == 1000:1000:600:1 ]] || \
    die 'unsafe existing ES-DE core options metadata'
fi
[[ -d /home/ark/.config/retroarch && ! -L /home/ark/.config/retroarch ]] || \
  die 'accepted RetroArch appdata directory is missing'
for directory in /home/ark/ROMs /home/ark/ES-DE /home/ark/ES-DE/settings \
  /home/ark/ES-DE/custom_systems /home/ark/ES-DE/downloaded_media; do
  if [[ -e $directory || -L $directory ]]; then
    [[ -d $directory && ! -L $directory ]] || die "unsafe existing directory: $directory"
  fi
done
if [[ -d /home/ark/ES-DE/downloaded_media ]]; then
  [[ -z $(find /home/ark/ES-DE/downloaded_media \( -type f -o -type l \) -print -quit) ]] || \
    die 'existing downloaded_media contains files or links'
fi

while IFS=$'\t' read -r system source; do
  [[ -n $system && ${system:0:1} != '#' ]] || continue
  safe_relative "$system" || die "unsafe system name: $system"
  [[ $source == /roms/* && -d $source && ! -L $source ]] || die "missing source system: $source"
  [[ ! -e /home/ark/ROMs/$system && ! -L /home/ark/ROMs/$system ]] || die "ROM link already exists: $system"
done < "$PAYLOAD_DIR/system-links.tsv"

frontend_state=$(systemctl is-active r46h-gaming-frontend.service || true)
[[ $frontend_state == active ]] || die 'accepted frontend must be active before update'
frontend_was_active=1
mapfile -t retroarch_pids < <(pgrep -u 1000 -x retroarch || true)
(( ${#retroarch_pids[@]} == 1 )) || die 'expected one accepted RetroArch frontend process'

install -d -o root -g root -m 0700 "$STATE_PARENT"
state_stage=$STATE_PARENT/.v0.1-stage.$$
install -d -o root -g root -m 0700 "$state_stage"
install -o root -g root -m 0400 "$UNIT" "$state_stage/previous-frontend.service"
install -o root -g root -m 0400 "$PAYLOAD_DIR/system-links.tsv" "$state_stage/system-links.tsv"
install -o root -g root -m 0400 "$PAYLOAD_DIR/legacy-media-links.tsv" "$state_stage/media-links.tsv"
install -o root -g root -m 0500 "$PAYLOAD_DIR/rollback.sh" "$state_stage/rollback.sh"
install -o root -g root -m 0400 "$PAYLOAD_DIR/README.md" "$state_stage/README.md"

install -d -o root -g root -m 0755 /opt/r46h
runtime_stage=/opt/r46h/.es-de-v0.1.$$
install -d -o root -g root -m 0700 "$runtime_stage"
tar -tzf "$RUNTIME_ARCHIVE" | awk '
  BEGIN { ok=1 }
  /^\// { ok=0 }
  /(^|\/)\.\.($|\/)/ { ok=0 }
  $0 != "opt/" && $0 != "opt/r46h/" && $0 !~ /^opt\/r46h\/es-de(\/|$)/ { ok=0 }
  END { exit ok ? 0 : 1 }
' || die 'runtime archive has unsafe members'
tar -tvzf "$RUNTIME_ARCHIVE" | awk '$1 !~ /^[d-]/ { bad=1 } END { exit bad ? 1 : 0 }' || \
  die 'runtime archive contains unsupported member types'
tar -xzf "$RUNTIME_ARCHIVE" -C "$runtime_stage" --no-same-owner
runtime_tree=$runtime_stage/opt/r46h/es-de
[[ -x $runtime_tree/bin/es-de && ! -L $runtime_tree/bin/es-de ]] || die 'runtime executable is missing'
[[ $(sha256sum "$runtime_tree/bin/es-de" | awk '{print $1}') == "$ES_DE_SHA256" ]] || die 'runtime executable mismatch'
[[ -z $(find "$runtime_tree" \( -type l -o -type b -o -type c -o -type p -o -type s \) \
  -print -quit) ]] || die 'runtime tree contains unsupported nodes'
[[ -f $runtime_tree/$THEME_RELATIVE && ! -L $runtime_tree/$THEME_RELATIVE ]] || \
  die 'bundled theme path is missing or unsafe'
install -o root -g root -m 0644 "$PAYLOAD_DIR/r46h-theme.xml" \
  "$runtime_tree/$THEME_RELATIVE"
hash_is "$runtime_tree/$THEME_RELATIVE" "$THEME_SHA256" || die 'R46H theme install failed'
(runtime_version=$(/usr/bin/env HOME=/home/ark \
  LD_LIBRARY_PATH="$runtime_tree/lib/aarch64-linux-gnu:$runtime_tree/lib" \
  "$runtime_tree/bin/es-de" --version) && \
  [[ $runtime_version == "$ES_DE_VERSION" ]]) || die 'runtime cannot execute on the accepted p2'
(cd "$runtime_tree" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum) \
  > "$state_stage/runtime.sha256"
chmod 0400 "$state_stage/runtime.sha256"

transaction_active=1
systemctl stop r46h-gaming-frontend.service
[[ $(systemctl is-active r46h-gaming-frontend.service || true) == inactive ]] || die 'frontend did not stop'
[[ -z $(pgrep -u 1000 -x retroarch || true) ]] || die 'accepted frontend process survived stop'
ln -s "$CJK_ALIAS_TARGET" "$CJK_ALIAS"
cjk_alias_installed=1
if [[ ! -e $ES_CORE_OPTIONS && ! -L $ES_CORE_OPTIONS ]]; then
  install -o ark -g ark -m 0600 "$FBNEO_OPTIONS" "$ES_CORE_OPTIONS"
  core_options_seeded=yes
fi

install -d -o ark -g ark -m 0755 /home/ark/ROMs /home/ark/ES-DE \
  /home/ark/ES-DE/settings /home/ark/ES-DE/custom_systems /home/ark/ES-DE/downloaded_media
if [[ ! -e $SETTINGS && ! -L $SETTINGS ]]; then
  install -o ark -g ark -m 0600 "$PAYLOAD_DIR/es_settings.xml" "$SETTINGS"
  settings_seeded=yes
elif [[ ! -f $SETTINGS || -L $SETTINGS ]]; then
  die 'existing ES-DE settings path is unsafe'
fi
install -o root -g root -m 0644 "$PAYLOAD_DIR/es_systems.xml" "$SYSTEMS"
install -o root -g root -m 0644 "$PAYLOAD_DIR/es-de-retroarch.cfg" "$RETROARCH_APPEND"
ln -s "$SYSTEMS" "$SYSTEMS_LINK"

while IFS=$'\t' read -r system source; do
  [[ -n $system && ${system:0:1} != '#' ]] || continue
  ln -s "$source" "/home/ark/ROMs/$system"
done < "$PAYLOAD_DIR/system-links.tsv"

media_installed=0
media_missing=0
while IFS=$'\t' read -r destination source; do
  [[ -n $destination && ${destination:0:1} != '#' ]] || continue
  safe_relative "$destination" || die "unsafe media destination: $destination"
  [[ $source == /roms/* && /$source/ != */../* ]] || die "unsafe media source: $source"
  if [[ ! -f $source || -L $source ]]; then
    media_missing=$((media_missing + 1))
    continue
  fi
  target=/home/ark/ES-DE/downloaded_media/$destination
  [[ ! -e $target && ! -L $target ]] || die "media destination already exists: $target"
  install -d -o ark -g ark -m 0755 "${target%/*}"
  ln -s "$source" "$target"
  media_installed=$((media_installed + 1))
done < "$PAYLOAD_DIR/legacy-media-links.tsv"

install -o root -g root -m 0755 "$PAYLOAD_DIR/r46h-es-de-ui" "$RUNNER"
install -o root -g root -m 0644 "$PAYLOAD_DIR/r46h-gaming-frontend.service" "$UNIT"
install -o root -g root -m 0700 "$PAYLOAD_DIR/rollback.sh" "$ROLLBACK"
mv -- "$runtime_tree" "$RUNTIME"
runtime_published=1
find "$runtime_stage" -depth -delete
runtime_stage=""
mv -- "$state_stage" "$STATE_DIR"
state_stage=""
state_published=1

runtime_manifest_sha256=$(sha256sum "$STATE_DIR/runtime.sha256" | awk '{print $1}')
receipt_stage=/var/lib/r46h/.gaming-es-de-v0.1-installed.$$
cat > "$receipt_stage" <<EOF
feature_id=$FEATURE_ID
source=ES-DE-v3.4.1-r51
runtime_archive_sha256=$RUNTIME_ARCHIVE_SHA256
runtime_manifest_sha256=$runtime_manifest_sha256
es_de_sha256=$ES_DE_SHA256
systems_sha256=$SYSTEMS_SHA256
retroarch_append_sha256=$RETROARCH_APPEND_SHA256
system_links_sha256=$SYSTEM_LINKS_SHA256
media_links_sha256=$MEDIA_LINKS_SHA256
runner_sha256=$RUNNER_SHA256
unit_sha256=$UNIT_SHA256
rollback_sha256=$ROLLBACK_SHA256
cjk_font_sha256=$CJK_FONT_SHA256
media_links_installed=$media_installed
media_sources_missing=$media_missing
settings_seeded=$settings_seeded
core_options_seeded=$core_options_seeded
EOF
chown root:root "$receipt_stage"
chmod 0600 "$receipt_stage"
mv -- "$receipt_stage" "$RECEIPT"
receipt_stage=""

systemctl daemon-reload
systemctl start r46h-gaming-frontend.service
for ((poll=0; poll<100; poll++)); do
  systemctl is-active --quiet r46h-gaming-frontend.service &&
    pgrep -u 1000 -x es-de >/dev/null && break
  sleep 0.1
done
systemctl is-active --quiet r46h-gaming-frontend.service || die 'ES-DE frontend service is not active'
mapfile -t es_pids < <(pgrep -u 1000 -x es-de || true)
(( ${#es_pids[@]} == 1 )) || die 'expected one ES-DE process'
[[ $(readlink "/proc/${es_pids[0]}/exe") == "$RUNTIME/bin/es-de" ]] || die 'unexpected ES-DE executable'
[[ $(cat "$EXT4_ERRORS") == 0 ]] || die 'p2 reported an ext4 error during update'
[[ -z $(systemctl --failed --no-legend --plain) ]] || die 'systemd has failed units after update'
sync

transaction_active=0
trap - EXIT INT TERM HUP
printf 'R46H_ES_DE_INSTALL result=pass systems=7 media_links=%d media_missing=%d settings_seeded=%s rollback=%s\n' \
  "$media_installed" "$media_missing" "$settings_seeded" "$ROLLBACK"
