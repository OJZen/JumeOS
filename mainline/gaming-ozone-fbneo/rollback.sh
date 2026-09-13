#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG
umask 077

readonly FEATURE_ID=r46h-gaming-ozone-fbneo-v0.1
readonly EXPECTED_RELEASE=6.12.99-r46h-mainline-v0.15-gaming-product
readonly EXPECTED_ROOT_PARTUUID=c9f931c9-02
readonly EXPECTED_ROOT_UUID=d3130007-46a4-4d56-9001-000000000007
readonly CONFIG=/etc/r46h/retroarch.cfg
readonly RUNNER=/usr/local/sbin/r46h-game-ui
readonly VOLUME_HELPER=/usr/local/libexec/r46h-volume-keys
readonly VOLUME_UNIT=/etc/systemd/system/r46h-volume-keys.service
readonly CORE_OPTIONS_DIR='/home/ark/.config/retroarch/config/FinalBurn Neo (neogeo subset)'
readonly CORE_OPTIONS="$CORE_OPTIONS_DIR/FinalBurn Neo (neogeo subset).opt"
readonly VOLUME_STATE_DIR=/var/lib/r46h-volume
readonly VOLUME_STATE=$VOLUME_STATE_DIR/level
readonly CORE=/usr/local/libexec/fbneo_neogeo_libretro.so
readonly PLAYLIST='/home/ark/.local/share/retroarch/playlists/SNK - Neo Geo.lpl'
readonly LICENSE_DIR=/usr/share/doc/r46h-gaming-ozone-fbneo
readonly LICENSE=$LICENSE_DIR/FBNEO-LICENSE.txt
readonly RECEIPT=/var/lib/r46h/gaming-ozone-fbneo-v0.1-installed
readonly STATE_PARENT=/var/lib/r46h-gaming-ozone-fbneo
readonly STATE_DIR=$STATE_PARENT/v0.1
readonly ROLLBACK=/usr/local/sbin/r46h-gaming-ozone-fbneo-rollback
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count
readonly BASE_CONFIG_SHA256=99a45beb148e58e40983773b4f5e26d9fb5d7e1bbbf6a7e714a5c352e43c0dba
readonly CONFIG_SHA256=0694b9f41220983bdf9d60789b97b2fe115f68474f22f4869a2764513bcf1835
readonly BASE_RUNNER_SHA256=27d2f987545a3ab20610806923372b41530d41e5e3fc0384614211088d71135c
readonly RUNNER_SHA256=b0a44a7184cef97e2b9597f0d84adacb66617073f9422ef719d98e3465cc77c8
readonly BASE_VOLUME_HELPER_SHA256=a66f7ee5fa38dec5964a7d7fa5f72940250952ba3858cbac57626d2f84ff5ec2
readonly VOLUME_HELPER_SHA256=41bb1c0b9d034c13c881e9a186edc6a748adf6b3e00784ff69a57d0b53af6d6c
readonly BASE_VOLUME_UNIT_SHA256=f654a838d58d859ee0ccfa75ab87fdab75c5bd465891418bc526d1c61abb8c89
readonly VOLUME_UNIT_SHA256=8920a66c77caff09db45c6ac6ca347ceead8d7106bc7b2195cb073a0ce6a9a8c
readonly CORE_OPTIONS_SHA256=4e67299bc6c37cd1ebdfca4e6a42110d5071c62d00e714b952b906ca1fa68976
readonly CORE_SHA256=8bb17a551f3eeeb384ab00a5c5375d30eb63807afe5b6c1ba1d3f78220732bdb
readonly PLAYLIST_SHA256=5c67fab51b033e0d8e95d9acf16175566ef9905224831259f1c5b33d01b819d4
readonly LICENSE_SHA256=bb2369f1b75f42242968a78191b47ee90f85682224d3ad1ef63044e244b3e202
readonly SOURCE_COMMIT=26f11fa9e43227a04953e20e8c7e4bf322cd53cb
readonly CORE_INFO_SHA256=2ba4587c30b2c1a81f76325cce4a04305f72869bf5280d6a3c3c7d7cea51142c
readonly MSLUG_ROM_SHA256=3ebe7ca4166f956a65ae98d86f9172f8b5d4462efa13723a5ea72fcf59adcbf8
readonly NEOGEO_BIOS_SHA256=d2d8ab5d5fc5ce41978e40c8db2984d8dd0a37e60c712e20961b80fdbb4c9936

frontend_was_active=0
frontend_restarts_before=""
frontend_stable_polls=0
volume_was_active=0
volume_restarts_before=""
config_stage=""
runner_stage=""
volume_helper_stage=""
volume_unit_stage=""

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

hash_file() {
  sha256sum "$1" | awk '{print $1}'
}

remove_volume_state() {
  local level
  local members

  [[ -d "$VOLUME_STATE_DIR" && ! -L "$VOLUME_STATE_DIR" ]] || \
    die 'volume state directory is unsafe'
  [[ "$(stat -c '%u:%g:%a' "$VOLUME_STATE_DIR")" == 1000:1000:700 ]] || \
    die 'volume state directory identity is unsafe'
  members=$(find "$VOLUME_STATE_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
  [[ "$members" == level ]] || die 'unexpected volume state member set'
  [[ -f "$VOLUME_STATE" && ! -L "$VOLUME_STATE" ]] || die 'volume state is unsafe'
  [[ "$(stat -c '%u:%g:%a:%h' "$VOLUME_STATE")" == 1000:1000:600:1 ]] || \
    die 'volume state identity is unsafe'
  level=$(<"$VOLUME_STATE")
  [[ "$level" =~ ^[0-9]+$ ]] && (( level <= 201 )) || die 'volume state value is unsafe'
  rm -f -- "$VOLUME_STATE"
  rmdir -- "$VOLUME_STATE_DIR"
}

[[ $# == 0 ]] || die 'this rollback accepts no arguments'
(( EUID == 0 )) || die 'root is required'
[[ "${BASH_SOURCE[0]}" == "$ROLLBACK" ]] || die 'run the installed rollback helper'
[[ "$(uname -r)" == "$EXPECTED_RELEASE" ]] || die 'unexpected running kernel'
[[ "$(findmnt -rn -o PARTUUID /)" == "$EXPECTED_ROOT_PARTUUID" ]] || \
  die 'unexpected root partition'
[[ "$(findmnt -rn -o UUID /)" == "$EXPECTED_ROOT_UUID" ]] || die 'unexpected p2 UUID'
[[ "$(findmnt -rn -o FSTYPE /)" == ext4 ]] || die 'root is not ext4'
[[ ",$(findmnt -rn -o OPTIONS /)," == *,rw,* ]] || die 'root is not writable'
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem already reports errors'
[[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd has failed units'

[[ -f "$RECEIPT" && ! -L "$RECEIPT" ]] || die 'feature receipt is missing'
[[ "$(stat -c '%u:%g:%a:%h' "$RECEIPT")" == 0:0:600:1 ]] || \
  die 'feature receipt identity is unsafe'
[[ "$(wc -l < "$RECEIPT" | tr -d '[:space:]')" == 19 ]] || \
  die 'feature receipt line count mismatch'
grep -Fqx "feature_id=$FEATURE_ID" "$RECEIPT" || die 'feature receipt mismatch'
grep -Fqx "base_config_sha256=$BASE_CONFIG_SHA256" "$RECEIPT" || \
  die 'base config receipt mismatch'
grep -Fqx "config_sha256=$CONFIG_SHA256" "$RECEIPT" || die 'config receipt mismatch'
grep -Fqx "base_runner_sha256=$BASE_RUNNER_SHA256" "$RECEIPT" || \
  die 'base runner receipt mismatch'
grep -Fqx "runner_sha256=$RUNNER_SHA256" "$RECEIPT" || die 'runner receipt mismatch'
grep -Fqx "base_volume_helper_sha256=$BASE_VOLUME_HELPER_SHA256" "$RECEIPT" || \
  die 'base volume helper receipt mismatch'
grep -Fqx "volume_helper_sha256=$VOLUME_HELPER_SHA256" "$RECEIPT" || \
  die 'volume helper receipt mismatch'
grep -Fqx "base_volume_unit_sha256=$BASE_VOLUME_UNIT_SHA256" "$RECEIPT" || \
  die 'base volume unit receipt mismatch'
grep -Fqx "volume_unit_sha256=$VOLUME_UNIT_SHA256" "$RECEIPT" || \
  die 'volume unit receipt mismatch'
grep -Fqx "core_options_sha256=$CORE_OPTIONS_SHA256" "$RECEIPT" || \
  die 'core options receipt mismatch'
grep -Fqx "core_sha256=$CORE_SHA256" "$RECEIPT" || die 'core receipt mismatch'
grep -Fqx "playlist_sha256=$PLAYLIST_SHA256" "$RECEIPT" || die 'playlist receipt mismatch'
grep -Fqx "license_sha256=$LICENSE_SHA256" "$RECEIPT" || die 'license receipt mismatch'
grep -Fqx "source_commit=$SOURCE_COMMIT" "$RECEIPT" || die 'source receipt mismatch'
grep -Fqx "core_info_sha256=$CORE_INFO_SHA256" "$RECEIPT" || \
  die 'core-info receipt mismatch'
grep -Fqx "mslug_rom_sha256=$MSLUG_ROM_SHA256" "$RECEIPT" || \
  die 'ROM receipt mismatch'
grep -Fqx "neogeo_bios_sha256=$NEOGEO_BIOS_SHA256" "$RECEIPT" || \
  die 'BIOS receipt mismatch'
grep -Eq '^rollback_sha256=[0-9a-f]{64}$' "$RECEIPT" || die 'rollback receipt mismatch'
grep -Eq '^installer_sha256=[0-9a-f]{64}$' "$RECEIPT" || die 'installer receipt mismatch'

[[ -d "$STATE_PARENT" && ! -L "$STATE_PARENT" ]] || die 'rollback state parent is missing'
[[ "$(stat -c '%u:%g:%a' "$STATE_PARENT")" == 0:0:700 ]] || \
  die 'rollback state parent identity is unsafe'
[[ -d "$STATE_DIR" && ! -L "$STATE_DIR" ]] || die 'rollback state is missing'
[[ "$(stat -c '%u:%g:%a' "$STATE_DIR")" == 0:0:700 ]] || \
  die 'rollback state identity is unsafe'
state_members=$(find "$STATE_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
[[ "$state_members" == $'base-r46h-game-ui\nbase-r46h-volume-keys\nbase-r46h-volume-keys.service\nbase-retroarch.cfg\nrollback.sh' ]] || \
  die 'unexpected rollback state member set'
for path in "$STATE_DIR/base-retroarch.cfg" "$STATE_DIR/base-r46h-game-ui" \
  "$STATE_DIR/base-r46h-volume-keys" "$STATE_DIR/base-r46h-volume-keys.service" \
  "$STATE_DIR/rollback.sh" "$ROLLBACK"; do
  [[ -f "$path" && ! -L "$path" ]] || die "unsafe rollback member: $path"
  [[ "$(stat -c '%h' "$path")" == 1 ]] || die "hard-linked rollback member: $path"
done
[[ "$(stat -c '%u:%g:%a' "$STATE_DIR/base-retroarch.cfg")" == 0:0:400 ]] || \
  die 'base config state identity is unsafe'
[[ "$(stat -c '%u:%g:%a' "$STATE_DIR/base-r46h-game-ui")" == 0:0:500 ]] || \
  die 'base runner state identity is unsafe'
[[ "$(stat -c '%u:%g:%a' "$STATE_DIR/base-r46h-volume-keys")" == 0:0:500 ]] || \
  die 'base volume helper state identity is unsafe'
[[ "$(stat -c '%u:%g:%a' "$STATE_DIR/base-r46h-volume-keys.service")" == \
   0:0:400 ]] || die 'base volume unit state identity is unsafe'
[[ "$(stat -c '%u:%g:%a' "$STATE_DIR/rollback.sh")" == 0:0:500 ]] || \
  die 'rollback source state identity is unsafe'
[[ "$(stat -c '%u:%g:%a' "$ROLLBACK")" == 0:0:700 ]] || \
  die 'installed rollback identity is unsafe'
[[ "$(hash_file "$STATE_DIR/base-retroarch.cfg")" == "$BASE_CONFIG_SHA256" ]] || \
  die 'base config state mismatch'
[[ "$(hash_file "$STATE_DIR/base-r46h-game-ui")" == "$BASE_RUNNER_SHA256" ]] || \
  die 'base runner state mismatch'
[[ "$(hash_file "$STATE_DIR/base-r46h-volume-keys")" == \
   "$BASE_VOLUME_HELPER_SHA256" ]] || die 'base volume helper state mismatch'
[[ "$(hash_file "$STATE_DIR/base-r46h-volume-keys.service")" == \
   "$BASE_VOLUME_UNIT_SHA256" ]] || die 'base volume unit state mismatch'
rollback_sha256=$(hash_file "$STATE_DIR/rollback.sh")
grep -Fqx "rollback_sha256=$rollback_sha256" "$RECEIPT" || \
  die 'rollback state receipt mismatch'
cmp -s "$STATE_DIR/rollback.sh" "$ROLLBACK" || die 'installed rollback mismatch'

[[ -f "$CONFIG" && ! -L "$CONFIG" ]] || die 'RetroArch config is missing'
[[ -f "$RUNNER" && ! -L "$RUNNER" ]] || die 'frontend runner is missing'
[[ -f "$VOLUME_HELPER" && ! -L "$VOLUME_HELPER" ]] || die 'volume helper is missing'
[[ -f "$VOLUME_UNIT" && ! -L "$VOLUME_UNIT" ]] || die 'volume unit is missing'
current_config_sha256=$(hash_file "$CONFIG")
current_runner_sha256=$(hash_file "$RUNNER")
current_volume_helper_sha256=$(hash_file "$VOLUME_HELPER")
current_volume_unit_sha256=$(hash_file "$VOLUME_UNIT")
[[ "$current_config_sha256" == "$CONFIG_SHA256" ||
   "$current_config_sha256" == "$BASE_CONFIG_SHA256" ]] || die 'RetroArch config mismatch'
[[ "$current_runner_sha256" == "$RUNNER_SHA256" ||
   "$current_runner_sha256" == "$BASE_RUNNER_SHA256" ]] || die 'frontend runner mismatch'
[[ "$current_volume_helper_sha256" == "$VOLUME_HELPER_SHA256" ||
   "$current_volume_helper_sha256" == "$BASE_VOLUME_HELPER_SHA256" ]] || \
  die 'volume helper mismatch'
[[ "$current_volume_unit_sha256" == "$VOLUME_UNIT_SHA256" ||
   "$current_volume_unit_sha256" == "$BASE_VOLUME_UNIT_SHA256" ]] || \
  die 'volume unit mismatch'
if [[ -e "$CORE_OPTIONS_DIR" || -L "$CORE_OPTIONS_DIR" ]]; then
  [[ -d "$CORE_OPTIONS_DIR" && ! -L "$CORE_OPTIONS_DIR" ]] || \
    die 'core options directory is unsafe'
  [[ "$(stat -c '%u:%g:%a' "$CORE_OPTIONS_DIR")" == 1000:1000:700 ]] || \
    die 'core options directory identity is unsafe'
  core_options_members=$(find "$CORE_OPTIONS_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
  [[ -z "$core_options_members" || \
     "$core_options_members" == 'FinalBurn Neo (neogeo subset).opt' ]] || \
      die 'unexpected core options member set'
fi
if [[ -e "$CORE_OPTIONS" || -L "$CORE_OPTIONS" ]]; then
  [[ -f "$CORE_OPTIONS" && ! -L "$CORE_OPTIONS" ]] || die 'core options path is unsafe'
  [[ "$(stat -c '%u:%g:%a:%h' "$CORE_OPTIONS")" == 1000:1000:600:1 ]] || \
    die 'core options identity is unsafe'
  [[ "$(hash_file "$CORE_OPTIONS")" == "$CORE_OPTIONS_SHA256" ]] || \
    die 'core options mismatch'
fi
if [[ -e "$VOLUME_STATE_DIR" || -L "$VOLUME_STATE_DIR" ]]; then
  [[ -d "$VOLUME_STATE_DIR" && ! -L "$VOLUME_STATE_DIR" ]] || \
    die 'volume state directory is unsafe'
  [[ "$(stat -c '%u:%g:%a' "$VOLUME_STATE_DIR")" == 1000:1000:700 ]] || \
    die 'volume state directory identity is unsafe'
  volume_state_members=$(find "$VOLUME_STATE_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
  [[ "$volume_state_members" == level ]] || die 'unexpected volume state member set'
  [[ -f "$VOLUME_STATE" && ! -L "$VOLUME_STATE" ]] || die 'volume state is unsafe'
  [[ "$(stat -c '%u:%g:%a:%h' "$VOLUME_STATE")" == 1000:1000:600:1 ]] || \
    die 'volume state identity is unsafe'
  volume_level=$(<"$VOLUME_STATE")
  [[ "$volume_level" =~ ^[0-9]+$ ]] && (( volume_level <= 201 )) || \
    die 'volume state value is unsafe'
fi
if [[ -e "$CORE" || -L "$CORE" ]]; then
  [[ -f "$CORE" && ! -L "$CORE" ]] || die 'FBNeo core path is unsafe'
  [[ "$(stat -c '%u:%g:%a:%h' "$CORE")" == 0:0:644:1 ]] || \
    die 'FBNeo core identity is unsafe'
  [[ "$(hash_file "$CORE")" == "$CORE_SHA256" ]] || die 'FBNeo core mismatch'
fi
if [[ -e "$PLAYLIST" || -L "$PLAYLIST" ]]; then
  [[ -f "$PLAYLIST" && ! -L "$PLAYLIST" ]] || die 'Neo Geo playlist path is unsafe'
  [[ "$(stat -c '%u:%g:%a:%h' "$PLAYLIST")" == 1000:1000:600:1 ]] || \
    die 'Neo Geo playlist identity is unsafe'
  [[ "$(hash_file "$PLAYLIST")" == "$PLAYLIST_SHA256" ]] || die 'Neo Geo playlist mismatch'
fi
if [[ -e "$LICENSE" || -L "$LICENSE" ]]; then
  [[ -f "$LICENSE" && ! -L "$LICENSE" ]] || die 'FBNeo license path is unsafe'
  [[ "$(stat -c '%u:%g:%a:%h' "$LICENSE")" == 0:0:644:1 ]] || \
    die 'FBNeo license identity is unsafe'
  [[ "$(hash_file "$LICENSE")" == "$LICENSE_SHA256" ]] || die 'FBNeo license mismatch'
fi

frontend_state=$(systemctl is-active r46h-gaming-frontend.service || true)
case $frontend_state in
  active) frontend_was_active=1 ;;
  inactive) ;;
  *) die "unexpected frontend state: $frontend_state" ;;
esac
frontend_restarts_before=$(systemctl show -p NRestarts --value r46h-gaming-frontend.service)
[[ "$frontend_restarts_before" =~ ^[0-9]+$ ]] || die 'cannot read frontend restart count'
volume_service_state=$(systemctl is-active r46h-volume-keys.service || true)
case $volume_service_state in
  active) volume_was_active=1 ;;
  inactive) ;;
  *) die "unexpected volume service state: $volume_service_state" ;;
esac
volume_restarts_before=$(systemctl show -p NRestarts --value r46h-volume-keys.service)
[[ "$volume_restarts_before" =~ ^[0-9]+$ ]] || die 'cannot read volume restart count'
systemctl stop r46h-gaming-frontend.service
[[ "$(systemctl is-active r46h-gaming-frontend.service || true)" == inactive ]] || \
  die 'frontend did not stop'
[[ -z "$(pgrep -x retroarch || true)" ]] || die 'RetroArch survived frontend stop'
systemctl stop r46h-volume-keys.service
[[ "$(systemctl is-active r46h-volume-keys.service || true)" == inactive ]] || \
  die 'volume service did not stop'

trap 'rm -f -- "$config_stage" "$runner_stage" "$volume_helper_stage" "$volume_unit_stage"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
if [[ "$current_config_sha256" == "$CONFIG_SHA256" ]]; then
  config_stage=/etc/r46h/.retroarch.cfg.ozone-fbneo-rollback.$$
  install -o root -g root -m 0644 "$STATE_DIR/base-retroarch.cfg" "$config_stage"
  mv -f -- "$config_stage" "$CONFIG"
  config_stage=""
fi
if [[ "$current_runner_sha256" == "$RUNNER_SHA256" ]]; then
  runner_stage=/usr/local/sbin/.r46h-game-ui.ozone-fbneo-rollback.$$
  install -o root -g root -m 0755 "$STATE_DIR/base-r46h-game-ui" "$runner_stage"
  mv -f -- "$runner_stage" "$RUNNER"
  runner_stage=""
fi
if [[ "$current_volume_helper_sha256" == "$VOLUME_HELPER_SHA256" ]]; then
  volume_helper_stage=/usr/local/libexec/.r46h-volume-keys.ozone-fbneo-rollback.$$
  install -o root -g root -m 0755 "$STATE_DIR/base-r46h-volume-keys" \
    "$volume_helper_stage"
  mv -f -- "$volume_helper_stage" "$VOLUME_HELPER"
  volume_helper_stage=""
fi
if [[ "$current_volume_unit_sha256" == "$VOLUME_UNIT_SHA256" ]]; then
  volume_unit_stage=/etc/systemd/system/.r46h-volume-keys.service.ozone-fbneo-rollback.$$
  install -o root -g root -m 0644 "$STATE_DIR/base-r46h-volume-keys.service" \
    "$volume_unit_stage"
  mv -f -- "$volume_unit_stage" "$VOLUME_UNIT"
  volume_unit_stage=""
fi
systemctl daemon-reload
[[ "$(hash_file "$CONFIG")" == "$BASE_CONFIG_SHA256" ]] || die 'base config restore failed'
[[ "$(hash_file "$RUNNER")" == "$BASE_RUNNER_SHA256" ]] || die 'base runner restore failed'
[[ "$(hash_file "$VOLUME_HELPER")" == "$BASE_VOLUME_HELPER_SHA256" ]] || \
  die 'base volume helper restore failed'
[[ "$(hash_file "$VOLUME_UNIT")" == "$BASE_VOLUME_UNIT_SHA256" ]] || \
  die 'base volume unit restore failed'

if [[ -f "$CORE_OPTIONS" ]]; then
  rm -f -- "$CORE_OPTIONS"
fi
rmdir -- "$CORE_OPTIONS_DIR" 2>/dev/null || true
if [[ -f "$CORE" ]]; then
  rm -f -- "$CORE"
fi
if [[ -f "$PLAYLIST" ]]; then
  rm -f -- "$PLAYLIST"
fi
if [[ -f "$LICENSE" ]]; then
  rm -f -- "$LICENSE"
fi
rmdir -- "$LICENSE_DIR" 2>/dev/null || true
if [[ -e "$VOLUME_STATE_DIR" || -L "$VOLUME_STATE_DIR" ]]; then
  remove_volume_state
fi
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem reported an error during rollback'
sync

if (( volume_was_active == 1 )); then
  systemctl start r46h-volume-keys.service
  for ((poll=0; poll<50; poll++)); do
    [[ "$(systemctl is-active r46h-volume-keys.service || true)" == active ]] && break
    sleep 0.1
  done
  [[ "$(systemctl is-active r46h-volume-keys.service || true)" == active ]] || \
    die 'accepted volume service did not become active'
fi
if (( frontend_was_active == 1 )); then
  systemctl start r46h-gaming-frontend.service
  for ((poll=0; poll<50; poll++)); do
    if [[ "$(systemctl is-active r46h-gaming-frontend.service || true)" == active ]] && \
       [[ "$(pgrep -u 1000 -x retroarch | wc -l | tr -d '[:space:]')" == 1 ]]; then
      ((frontend_stable_polls+=1))
      (( frontend_stable_polls >= 20 )) && break
    else
      frontend_stable_polls=0
    fi
    sleep 0.1
  done
  (( frontend_stable_polls >= 20 )) || die 'accepted frontend did not remain healthy'
fi
[[ "$(systemctl show -p NRestarts --value r46h-gaming-frontend.service)" == \
   "$frontend_restarts_before" ]] || die 'frontend restart count changed during rollback'
[[ "$(systemctl show -p NRestarts --value r46h-volume-keys.service)" == \
   "$volume_restarts_before" ]] || die 'volume restart count changed during rollback'
[[ -z "$(systemctl --failed --no-legend --plain)" ]] || \
  die 'systemd has failed units after rollback'

rm -f -- "$RECEIPT"
rm -f -- "$STATE_DIR/base-retroarch.cfg" "$STATE_DIR/base-r46h-game-ui" \
  "$STATE_DIR/base-r46h-volume-keys" "$STATE_DIR/base-r46h-volume-keys.service" \
  "$STATE_DIR/rollback.sh"
rmdir -- "$STATE_DIR"
rmdir -- "$STATE_PARENT" 2>/dev/null || true
sync
rm -f -- "$ROLLBACK"
sync
trap - EXIT INT TERM HUP
printf 'PASS: R46H Ozone/FBNeo v0.1 rolled back to exact p2 v0.7 frontend.\n'
