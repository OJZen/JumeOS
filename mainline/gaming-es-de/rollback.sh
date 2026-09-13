#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG
umask 077

readonly EXPECTED_RELEASE=6.12.99-r46h-mainline-v0.15-gaming-product
readonly EXPECTED_ROOT_PARTUUID=c9f931c9-02
readonly EXPECTED_ROOT_UUID=d3130007-46a4-4d56-9001-000000000007
readonly ES_DE_SHA256=9c6e50433b9bca5ac1c01030bc4d7b143f05c2cd27c52e6f5f765b0acf01be98
readonly SYSTEMS_SHA256=1f451723d4ce1062157eb0e041ff4c098c5adea98c61e87ddf3cb784dfe630f0
readonly RETROARCH_APPEND_SHA256=2e13e4d33ca23e67d7b52ce6c9c85045b39e3f2ff76bbd6d68c8ca2295ddcb7f
readonly SYSTEM_LINKS_SHA256=bd5e496ab9bb54f0b9d45b461262b70fd5758d763ea4ff4fb9d06c26c936d73d
readonly MEDIA_LINKS_SHA256=9358e316d0b5436108c4a460a6654c5437341e4c85b86dcc2d5ae32abfbb9a9f
readonly RUNNER_SHA256=5b9edd8705d26ac2b58285baee9d2025354a0343936b5360313e664edd5bafa1
readonly UNIT_SHA256=df3b6bdc3ba9b3ee65d18b9575c302cfa3aaff4fcc67fe6d12e825565c2ba05c
readonly PREVIOUS_UNIT_SHA256=2fec9c8cb0be8ee724c5e9d44d78971ab83e57a4d5cbba9d3931d457262ff9ed
readonly OZONE_RECEIPT_SHA256=8acac2c8b8e4295c0235ad1fc7e396e341dcc4b1ba771a053355a98cf8fb73ec
readonly ACCEPTED_CONFIG_SHA256=0694b9f41220983bdf9d60789b97b2fe115f68474f22f4869a2764513bcf1835
readonly ACCEPTED_RUNNER_SHA256=b0a44a7184cef97e2b9597f0d84adacb66617073f9422ef719d98e3465cc77c8
readonly CJK_FONT_SHA256=acb6440a713d880a13a21b468ba7cd43f5a2b2934972e51be791c880730777b8

readonly OZONE_RECEIPT=/var/lib/r46h/gaming-ozone-fbneo-v0.1-installed
readonly ACCEPTED_CONFIG=/etc/r46h/retroarch.cfg
readonly ACCEPTED_RUNNER=/usr/local/sbin/r46h-game-ui
readonly CJK_FONT=/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf
readonly CJK_ALIAS=/usr/share/libretro/assets/pkg/chinese-fallback-font.ttf
readonly CJK_ALIAS_TARGET=../../../fonts/truetype/droid/DroidSansFallbackFull.ttf
readonly RUNTIME=/opt/r46h/es-de
readonly ES_DE=$RUNTIME/bin/es-de
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

manifest_stage=""

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

cleanup_stage() {
  local status=$?
  trap - EXIT
  rm -f -- "$manifest_stage"
  exit "$status"
}
trap cleanup_stage EXIT

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
  local manifest=$1 base=$2 destination source target
  while IFS=$'\t' read -r destination source; do
    [[ -n $destination && ${destination:0:1} != '#' ]] || continue
    safe_relative "$destination" || die "unsafe state link destination: $destination"
    target=$base/$destination
    [[ ! -e $target && ! -L $target ]] && continue
    [[ -L $target && $(readlink -- "$target") == "$source" ]] || \
      die "installed link changed: $target"
    rm -f -- "$target"
  done < "$manifest"
}

[[ $# == 0 ]] || die 'this rollback accepts no arguments'
(( EUID == 0 )) || die 'root is required'
[[ ${BASH_SOURCE[0]} == "$ROLLBACK" ]] || die 'run the installed rollback helper'
[[ $(uname -r) == "$EXPECTED_RELEASE" ]] || die 'unexpected running kernel'
[[ $(findmnt -rn -o PARTUUID /) == "$EXPECTED_ROOT_PARTUUID" ]] || die 'unexpected root partition'
[[ $(findmnt -rn -o UUID /) == "$EXPECTED_ROOT_UUID" ]] || die 'unexpected root filesystem'
[[ ,$(findmnt -rn -o OPTIONS /), == *,rw,* ]] || die 'p2 is not writable'
[[ ,$(findmnt -rn -o OPTIONS /roms), == *,ro,* ]] || die '/roms is not read-only'
[[ $(cat "$EXT4_ERRORS") == 0 ]] || die 'p2 already reports ext4 errors'
[[ -z $(systemctl --failed --no-legend --plain) ]] || die 'systemd has failed units'

hash_is "$OZONE_RECEIPT" "$OZONE_RECEIPT_SHA256" || die 'accepted Ozone receipt changed'
hash_is "$ACCEPTED_CONFIG" "$ACCEPTED_CONFIG_SHA256" || die 'accepted RetroArch config changed'
hash_is "$ACCEPTED_RUNNER" "$ACCEPTED_RUNNER_SHA256" || die 'accepted Ozone runner changed'
hash_is "$ES_DE" "$ES_DE_SHA256" || die 'installed ES-DE executable changed'
hash_is "$SYSTEMS" "$SYSTEMS_SHA256" || die 'installed systems config changed'
hash_is "$RETROARCH_APPEND" "$RETROARCH_APPEND_SHA256" || die 'installed RetroArch append config changed'
hash_is "$RUNNER" "$RUNNER_SHA256" || die 'installed ES-DE launcher changed'
hash_is "$UNIT" "$UNIT_SHA256" || die 'installed frontend unit changed'
hash_is "$CJK_FONT" "$CJK_FONT_SHA256" || die 'RetroArch Chinese font changed'
[[ -L $CJK_ALIAS && $(readlink -- "$CJK_ALIAS") == "$CJK_ALIAS_TARGET" ]] || \
  die 'RetroArch Chinese font alias changed'
hash_is "$STATE_DIR/previous-frontend.service" "$PREVIOUS_UNIT_SHA256" || die 'rollback unit changed'
[[ -f $RECEIPT && ! -L $RECEIPT ]] || die 'ES-DE receipt is missing'
[[ $(stat -c '%u:%g:%a:%h' "$RECEIPT") == 0:0:600:1 ]] || die 'receipt identity is unsafe'
grep -Fqx 'feature_id=r46h-gaming-es-de-v0.1' "$RECEIPT" || die 'receipt identity mismatch'
grep -Fqx "es_de_sha256=$ES_DE_SHA256" "$RECEIPT" || die 'ES-DE receipt mismatch'
grep -Fqx "systems_sha256=$SYSTEMS_SHA256" "$RECEIPT" || die 'systems receipt mismatch'
grep -Fqx "retroarch_append_sha256=$RETROARCH_APPEND_SHA256" "$RECEIPT" || die 'RetroArch receipt mismatch'
grep -Fqx "system_links_sha256=$SYSTEM_LINKS_SHA256" "$RECEIPT" || die 'system links receipt mismatch'
grep -Fqx "media_links_sha256=$MEDIA_LINKS_SHA256" "$RECEIPT" || die 'media links receipt mismatch'
grep -Fqx "runner_sha256=$RUNNER_SHA256" "$RECEIPT" || die 'launcher receipt mismatch'
grep -Fqx "unit_sha256=$UNIT_SHA256" "$RECEIPT" || die 'unit receipt mismatch'
grep -Fqx "cjk_font_sha256=$CJK_FONT_SHA256" "$RECEIPT" || die 'Chinese font receipt mismatch'
rollback_sha256=$(sha256sum "$ROLLBACK" | awk '{print $1}')
grep -Fqx "rollback_sha256=$rollback_sha256" "$RECEIPT" || die 'rollback receipt mismatch'

[[ -d $STATE_DIR && ! -L $STATE_DIR ]] || die 'rollback state is missing'
[[ $(stat -c '%u:%g:%a' "$STATE_DIR") == 0:0:700 ]] || die 'rollback state identity is unsafe'
hash_is "$STATE_DIR/system-links.tsv" "$SYSTEM_LINKS_SHA256" || die 'system link state changed'
hash_is "$STATE_DIR/media-links.tsv" "$MEDIA_LINKS_SHA256" || die 'media link state changed'
state_members=$(find "$STATE_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | LC_ALL=C sort)
[[ $state_members == $'README.md\nmedia-links.tsv\nprevious-frontend.service\nrollback.sh\nruntime.sha256\nsystem-links.tsv' ]] || \
  die 'unexpected rollback state members'
cmp -s "$STATE_DIR/rollback.sh" "$ROLLBACK" || die 'rollback helper differs from state'
runtime_manifest_sha256=$(sha256sum "$STATE_DIR/runtime.sha256" | awk '{print $1}')
grep -Fqx "runtime_manifest_sha256=$runtime_manifest_sha256" "$RECEIPT" || \
  die 'runtime manifest receipt mismatch'
manifest_stage=$STATE_PARENT/.runtime-current.$$
(cd "$RUNTIME" && find . -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum) \
  > "$manifest_stage"
cmp -s "$manifest_stage" "$STATE_DIR/runtime.sha256" || die 'runtime tree changed'
rm -f -- "$manifest_stage"
manifest_stage=""
[[ -L $SYSTEMS_LINK && $(readlink -- "$SYSTEMS_LINK") == "$SYSTEMS" ]] || \
  die 'custom systems link changed'

[[ $(systemctl is-active r46h-gaming-frontend.service || true) == active ]] || \
  die 'ES-DE frontend is not active'
mapfile -t es_pids < <(pgrep -u 1000 -x es-de || true)
(( ${#es_pids[@]} == 1 )) || die 'expected one ES-DE process'
[[ $(readlink "/proc/${es_pids[0]}/exe") == "$ES_DE" ]] || die 'unexpected ES-DE process'

systemctl stop r46h-gaming-frontend.service
[[ $(systemctl is-active r46h-gaming-frontend.service || true) == inactive ]] || die 'ES-DE service did not stop'
[[ -z $(pgrep -u 1000 -x es-de || true) ]] || die 'ES-DE process survived stop'

remove_link_set "$STATE_DIR/media-links.tsv" /home/ark/ES-DE/downloaded_media
remove_link_set "$STATE_DIR/system-links.tsv" /home/ark/ROMs
rm -f -- "$SYSTEMS_LINK"
rm -f -- "$CJK_ALIAS"
install -o root -g root -m 0644 "$STATE_DIR/previous-frontend.service" "$UNIT"
rm -f -- "$SYSTEMS" "$RETROARCH_APPEND" "$RUNNER"
find "$RUNTIME" -depth -delete
rm -f -- "$RECEIPT"
systemctl daemon-reload
systemctl start r46h-gaming-frontend.service

for ((poll=0; poll<100; poll++)); do
  systemctl is-active --quiet r46h-gaming-frontend.service &&
    pgrep -u 1000 -x retroarch >/dev/null && break
  sleep 0.1
done
systemctl is-active --quiet r46h-gaming-frontend.service || die 'accepted frontend did not restart'
mapfile -t retroarch_pids < <(pgrep -u 1000 -x retroarch || true)
(( ${#retroarch_pids[@]} == 1 )) || die 'expected one accepted RetroArch process after rollback'
[[ $(readlink "/proc/${retroarch_pids[0]}/exe") == /usr/bin/retroarch ]] || die 'unexpected rollback frontend process'
hash_is "$UNIT" "$PREVIOUS_UNIT_SHA256" || die 'accepted frontend unit was not restored'
hash_is "$ACCEPTED_CONFIG" "$ACCEPTED_CONFIG_SHA256" || die 'accepted RetroArch config changed during rollback'
hash_is "$ACCEPTED_RUNNER" "$ACCEPTED_RUNNER_SHA256" || die 'accepted Ozone runner changed during rollback'
[[ $(cat "$EXT4_ERRORS") == 0 ]] || die 'p2 reported an ext4 error during rollback'
[[ -z $(systemctl --failed --no-legend --plain) ]] || die 'systemd has failed units after rollback'
sync

find "$STATE_DIR" -depth -delete
rmdir -- "$STATE_PARENT"
rm -f -- "$ROLLBACK"
sync
trap - EXIT
printf 'R46H_ES_DE_ROLLBACK result=pass frontend=ozone appdata=preserved p1=untouched p3=untouched\n'
