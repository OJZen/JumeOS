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
readonly PAYLOAD_DIR=/run/r46h-gaming-ozone-fbneo-v0.1
readonly CONFIG_SOURCE=$PAYLOAD_DIR/retroarch.cfg
readonly RUNNER_SOURCE=$PAYLOAD_DIR/r46h-game-ui
readonly VOLUME_HELPER_SOURCE=$PAYLOAD_DIR/r46h-volume-keys
readonly VOLUME_UNIT_SOURCE=$PAYLOAD_DIR/r46h-volume-keys.service
readonly CORE_OPTIONS_SOURCE="$PAYLOAD_DIR/FinalBurn Neo (neogeo subset).opt"
readonly CORE_SOURCE=$PAYLOAD_DIR/fbneo_neogeo_libretro.so
readonly PLAYLIST_SOURCE="$PAYLOAD_DIR/SNK - Neo Geo.lpl"
readonly LICENSE_SOURCE=$PAYLOAD_DIR/FBNEO-LICENSE.txt
readonly ROLLBACK_SOURCE=$PAYLOAD_DIR/rollback.sh
readonly CONFIG=/etc/r46h/retroarch.cfg
readonly RUNNER=/usr/local/sbin/r46h-game-ui
readonly VOLUME_HELPER=/usr/local/libexec/r46h-volume-keys
readonly VOLUME_UNIT=/etc/systemd/system/r46h-volume-keys.service
readonly CORE_OPTIONS_DIR='/home/ark/.config/retroarch/config/FinalBurn Neo (neogeo subset)'
readonly CORE_OPTIONS="$CORE_OPTIONS_DIR/FinalBurn Neo (neogeo subset).opt"
readonly VOLUME_STATE_DIR=/var/lib/r46h-volume
readonly VOLUME_STATE=$VOLUME_STATE_DIR/level
readonly CORE=/usr/local/libexec/fbneo_neogeo_libretro.so
readonly PLAYLIST_DIR=/home/ark/.local/share/retroarch/playlists
readonly PLAYLIST="$PLAYLIST_DIR/SNK - Neo Geo.lpl"
readonly LICENSE_DIR=/usr/share/doc/r46h-gaming-ozone-fbneo
readonly LICENSE=$LICENSE_DIR/FBNEO-LICENSE.txt
readonly ROLLBACK=/usr/local/sbin/r46h-gaming-ozone-fbneo-rollback
readonly BASE_RECEIPT=/var/lib/r46h/gaming-mvp-v0.6-installed
readonly RECEIPT=/var/lib/r46h/gaming-ozone-fbneo-v0.1-installed
readonly STATE_PARENT=/var/lib/r46h-gaming-ozone-fbneo
readonly STATE_DIR=$STATE_PARENT/v0.1
readonly REMOTE_SCREEN_RECEIPT=/var/lib/r46h/remote-screen-v0.1-installed
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count
readonly CORE_INFO=/usr/share/libretro/info/fbneo_neogeo_libretro.info
readonly OZONE_ASSETS=/usr/share/libretro/assets/ozone
readonly OZONE_ICON="$OZONE_ASSETS/png/icons/SNK - Neo Geo.png"
readonly OZONE_CONTENT_ICON="$OZONE_ASSETS/png/icons/SNK - Neo Geo-content.png"
readonly MSLUG_ROM=/roms/neogeo/mslug.zip
readonly NEOGEO_BIOS=/roms/neogeo/neogeo.zip
readonly BASE_RECEIPT_SHA256=82721e16a9b9a7c7927d0ca4d228dd3d850e3a39dca245177ec1f016b3b8d314
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
readonly ROLLBACK_SHA256=1a21775caad50f89bb93c8f4462de742cf0dbfdbcaaef457ad464664032dd64d
readonly SOURCE_COMMIT=26f11fa9e43227a04953e20e8c7e4bf322cd53cb
readonly CORE_INFO_SHA256=2ba4587c30b2c1a81f76325cce4a04305f72869bf5280d6a3c3c7d7cea51142c
readonly MSLUG_ROM_SHA256=3ebe7ca4166f956a65ae98d86f9172f8b5d4462efa13723a5ea72fcf59adcbf8
readonly NEOGEO_BIOS_SHA256=d2d8ab5d5fc5ce41978e40c8db2984d8dd0a37e60c712e20961b80fdbb4c9936

config_stage=""
runner_stage=""
volume_helper_stage=""
volume_unit_stage=""
core_options_stage=""
core_stage=""
playlist_stage=""
license_stage=""
receipt_stage=""
state_stage=""
state_parent_created=0
state_published=0
config_replaced=0
runner_replaced=0
volume_helper_replaced=0
volume_unit_replaced=0
core_options_installed=0
core_options_dir_created=0
volume_state_created=0
core_installed=0
playlist_installed=0
license_installed=0
license_dir_created=0
frontend_was_active=0
frontend_restarts_before=""
volume_was_active=0
volume_restarts_before=""
transaction_active=0

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

hash_file() {
  sha256sum "$1" | awk '{print $1}'
}

usage() {
  printf 'usage: sudo /bin/bash %s --installer-sha256 HEX\n' "$PAYLOAD_DIR/install.sh"
}

validate_user_layout() {
  local directory

  [[ "$(id -u ark):$(id -g ark)" == 1000:1000 ]] || die 'unexpected ark identity'
  [[ -d /home/ark/.config && ! -L /home/ark/.config ]] || \
    die 'unsafe user directory: /home/ark/.config'
  [[ "$(stat -c '%u:%g:%a' /home/ark/.config)" == 0:0:755 ]] || \
    die 'unexpected user directory identity: /home/ark/.config'
  for directory in /home/ark /home/ark/.config/retroarch \
    /home/ark/.local /home/ark/.local/share /home/ark/.local/share/retroarch \
    "$PLAYLIST_DIR"; do
    [[ -d "$directory" && ! -L "$directory" ]] || die "unsafe user directory: $directory"
    [[ "$(stat -c '%u:%g:%a' "$directory")" == 1000:1000:700 ]] || \
      die "unexpected user directory identity: $directory"
  done
}

validate_runtime_inputs() {
  [[ -f "$CORE_INFO" && ! -L "$CORE_INFO" ]] || die 'FBNeo Neo-Geo core info is missing'
  [[ "$(hash_file "$CORE_INFO")" == "$CORE_INFO_SHA256" ]] || die 'core info mismatch'
  [[ -d "$OZONE_ASSETS" && ! -L "$OZONE_ASSETS" ]] || die 'Ozone assets are missing'
  [[ -f "$OZONE_ICON" && ! -L "$OZONE_ICON" ]] || die 'Ozone Neo Geo icon is missing'
  [[ -f "$OZONE_CONTENT_ICON" && ! -L "$OZONE_CONTENT_ICON" ]] || \
    die 'Ozone Neo Geo content icon is missing'
  [[ ",$(findmnt -rn -o OPTIONS /roms)," == *,ro,* ]] || die '/roms is not read-only'
  [[ -f "$MSLUG_ROM" && ! -L "$MSLUG_ROM" ]] || die 'Metal Slug ROM is missing'
  [[ -f "$NEOGEO_BIOS" && ! -L "$NEOGEO_BIOS" ]] || die 'Neo Geo BIOS is missing'
  [[ "$(hash_file "$MSLUG_ROM")" == "$MSLUG_ROM_SHA256" ]] || die 'Metal Slug ROM mismatch'
  [[ "$(hash_file "$NEOGEO_BIOS")" == "$NEOGEO_BIOS_SHA256" ]] || \
    die 'Neo Geo BIOS mismatch'
}

remove_state_directory() {
  local directory=$1

  rm -f -- "$directory/base-r46h-game-ui" "$directory/base-r46h-volume-keys" \
    "$directory/base-r46h-volume-keys.service" "$directory/base-retroarch.cfg" \
    "$directory/rollback.sh"
  rmdir -- "$directory" 2>/dev/null || true
}

remove_volume_state() {
  local level
  local members

  [[ -e "$VOLUME_STATE_DIR" || -L "$VOLUME_STATE_DIR" ]] || return 0
  [[ -d "$VOLUME_STATE_DIR" && ! -L "$VOLUME_STATE_DIR" ]] || return 1
  [[ "$(stat -c '%u:%g:%a' "$VOLUME_STATE_DIR")" == 1000:1000:700 ]] || return 1
  members=$(find "$VOLUME_STATE_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
  [[ "$members" == level ]] || return 1
  [[ -f "$VOLUME_STATE" && ! -L "$VOLUME_STATE" ]] || return 1
  [[ "$(stat -c '%u:%g:%a:%h' "$VOLUME_STATE")" == 1000:1000:600:1 ]] || return 1
  level=$(<"$VOLUME_STATE")
  [[ "$level" =~ ^[0-9]+$ ]] || return 1
  (( level >= 0 && level <= 201 )) || return 1
  rm -f -- "$VOLUME_STATE" || return 1
  rmdir -- "$VOLUME_STATE_DIR"
}

restore_base() {
  local restore_ok=1

  if (( config_replaced == 1 && state_published == 1 )); then
    install -o root -g root -m 0644 "$STATE_DIR/base-retroarch.cfg" \
      /etc/r46h/.retroarch.cfg.ozone-fbneo-cleanup.$$ &&
      mv -f -- /etc/r46h/.retroarch.cfg.ozone-fbneo-cleanup.$$ "$CONFIG" || restore_ok=0
  fi
  if (( runner_replaced == 1 && state_published == 1 )); then
    install -o root -g root -m 0755 "$STATE_DIR/base-r46h-game-ui" \
      /usr/local/sbin/.r46h-game-ui.ozone-fbneo-cleanup.$$ &&
      mv -f -- /usr/local/sbin/.r46h-game-ui.ozone-fbneo-cleanup.$$ "$RUNNER" || restore_ok=0
  fi
  if (( volume_helper_replaced == 1 && state_published == 1 )); then
    install -o root -g root -m 0755 "$STATE_DIR/base-r46h-volume-keys" \
      /usr/local/libexec/.r46h-volume-keys.ozone-fbneo-cleanup.$$ &&
      mv -f -- /usr/local/libexec/.r46h-volume-keys.ozone-fbneo-cleanup.$$ \
        "$VOLUME_HELPER" || restore_ok=0
  fi
  if (( volume_unit_replaced == 1 && state_published == 1 )); then
    install -o root -g root -m 0644 "$STATE_DIR/base-r46h-volume-keys.service" \
      /etc/systemd/system/.r46h-volume-keys.service.ozone-fbneo-cleanup.$$ &&
      mv -f -- /etc/systemd/system/.r46h-volume-keys.service.ozone-fbneo-cleanup.$$ \
        "$VOLUME_UNIT" || restore_ok=0
  fi
  rm -f -- /etc/r46h/.retroarch.cfg.ozone-fbneo-cleanup.$$ \
    /usr/local/sbin/.r46h-game-ui.ozone-fbneo-cleanup.$$ \
    /usr/local/libexec/.r46h-volume-keys.ozone-fbneo-cleanup.$$ \
    /etc/systemd/system/.r46h-volume-keys.service.ozone-fbneo-cleanup.$$
  if (( core_options_installed == 1 )); then
    rm -f -- "$CORE_OPTIONS" || restore_ok=0
  fi
  if (( core_options_dir_created == 1 )); then
    rmdir -- "$CORE_OPTIONS_DIR" 2>/dev/null || restore_ok=0
  fi
  if (( core_installed == 1 )); then
    rm -f -- "$CORE" || restore_ok=0
  fi
  if (( playlist_installed == 1 )); then
    rm -f -- "$PLAYLIST" || restore_ok=0
  fi
  if (( license_installed == 1 )); then
    rm -f -- "$LICENSE" || restore_ok=0
  fi
  if (( license_dir_created == 1 )); then
    rmdir -- "$LICENSE_DIR" 2>/dev/null || restore_ok=0
  fi
  if (( volume_unit_replaced == 1 )); then
    systemctl daemon-reload || restore_ok=0
  fi
  if (( volume_state_created == 1 )); then
    remove_volume_state || restore_ok=0
  fi
  (( restore_ok == 1 )) || return 1
  [[ "$(hash_file "$CONFIG" 2>/dev/null)" == "$BASE_CONFIG_SHA256" ]] || return 1
  [[ "$(hash_file "$RUNNER" 2>/dev/null)" == "$BASE_RUNNER_SHA256" ]] || return 1
  [[ "$(hash_file "$VOLUME_HELPER" 2>/dev/null)" == "$BASE_VOLUME_HELPER_SHA256" ]] || \
    return 1
  [[ "$(hash_file "$VOLUME_UNIT" 2>/dev/null)" == "$BASE_VOLUME_UNIT_SHA256" ]] || \
    return 1
}

cleanup_install() {
  local status=$?
  local restore_ok=1

  trap - EXIT INT TERM HUP
  set +e
  trap '' INT TERM HUP
  rm -f -- "$config_stage" "$runner_stage" "$volume_helper_stage" \
    "$volume_unit_stage" "$core_options_stage" "$core_stage" "$playlist_stage" \
    "$license_stage" "$receipt_stage"
  if (( transaction_active == 1 )); then
    systemctl stop r46h-gaming-frontend.service >/dev/null 2>&1 || true
    systemctl stop r46h-volume-keys.service >/dev/null 2>&1 || true
    restore_base || restore_ok=0
  fi
  if (( restore_ok == 1 )); then
    rm -f -- "$RECEIPT" "$ROLLBACK"
    if (( state_published == 1 )) && [[ -d "$STATE_DIR" && ! -L "$STATE_DIR" ]]; then
      remove_state_directory "$STATE_DIR"
    elif [[ -n "$state_stage" && -d "$state_stage" && ! -L "$state_stage" ]]; then
      remove_state_directory "$state_stage"
    fi
    if (( state_parent_created == 1 )); then
      rmdir -- "$STATE_PARENT" 2>/dev/null || true
    fi
  else
    printf 'ERROR: automatic restore failed; rollback state retained at %s\n' \
      "$STATE_DIR" >&2
    status=1
  fi
  if (( volume_was_active == 1 && restore_ok == 1 )); then
    systemctl start r46h-volume-keys.service >/dev/null 2>&1 || status=1
  fi
  if (( frontend_was_active == 1 && restore_ok == 1 )); then
    systemctl start r46h-gaming-frontend.service >/dev/null 2>&1 || status=1
  fi
  exit "$status"
}

[[ $# == 2 && $1 == --installer-sha256 ]] || { usage >&2; exit 2; }
installer_sha256=$2
[[ "$installer_sha256" =~ ^[0-9a-f]{64}$ ]] || die 'invalid installer SHA-256'
(( EUID == 0 )) || die 'root is required'
[[ "${BASH_SOURCE[0]}" == "$PAYLOAD_DIR/install.sh" ]] || die "stage payload at $PAYLOAD_DIR"
[[ -d "$PAYLOAD_DIR" && ! -L "$PAYLOAD_DIR" ]] || die 'unsafe payload directory'
[[ "$(stat -c '%u:%g:%a' "$PAYLOAD_DIR")" == 0:0:700 ]] || \
  die 'unsafe payload directory identity'
payload_members=$(find "$PAYLOAD_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
[[ "$payload_members" == $'FBNEO-LICENSE.txt\nFinalBurn Neo (neogeo subset).opt\nSNK - Neo Geo.lpl\nfbneo_neogeo_libretro.so\ninstall.sh\nr46h-game-ui\nr46h-volume-keys\nr46h-volume-keys.service\nretroarch.cfg\nrollback.sh' ]] || \
  die 'unexpected payload member set'
for path in "${BASH_SOURCE[0]}" "$CONFIG_SOURCE" "$RUNNER_SOURCE" \
  "$VOLUME_HELPER_SOURCE" "$VOLUME_UNIT_SOURCE" "$CORE_OPTIONS_SOURCE" "$CORE_SOURCE" \
  "$PLAYLIST_SOURCE" "$LICENSE_SOURCE" "$ROLLBACK_SOURCE"; do
  [[ -f "$path" && ! -L "$path" ]] || die "unsafe payload member: $path"
  [[ "$(stat -c '%u:%g:%a:%h' "$path")" == 0:0:600:1 ]] || \
    die "unsafe payload member identity: $path"
done
[[ "$(hash_file "${BASH_SOURCE[0]}")" == "$installer_sha256" ]] || \
  die 'installer SHA-256 mismatch'
[[ "$(hash_file "$CONFIG_SOURCE")" == "$CONFIG_SHA256" ]] || \
  die 'candidate config SHA-256 mismatch'
[[ "$(hash_file "$RUNNER_SOURCE")" == "$RUNNER_SHA256" ]] || \
  die 'candidate runner SHA-256 mismatch'
[[ "$(hash_file "$VOLUME_HELPER_SOURCE")" == "$VOLUME_HELPER_SHA256" ]] || \
  die 'candidate volume helper SHA-256 mismatch'
[[ "$(hash_file "$VOLUME_UNIT_SOURCE")" == "$VOLUME_UNIT_SHA256" ]] || \
  die 'candidate volume unit SHA-256 mismatch'
[[ "$(hash_file "$CORE_OPTIONS_SOURCE")" == "$CORE_OPTIONS_SHA256" ]] || \
  die 'candidate core options SHA-256 mismatch'
[[ "$(hash_file "$CORE_SOURCE")" == "$CORE_SHA256" ]] || die 'FBNeo core SHA-256 mismatch'
[[ "$(hash_file "$PLAYLIST_SOURCE")" == "$PLAYLIST_SHA256" ]] || \
  die 'Neo Geo playlist SHA-256 mismatch'
[[ "$(hash_file "$LICENSE_SOURCE")" == "$LICENSE_SHA256" ]] || \
  die 'FBNeo license SHA-256 mismatch'
[[ "$(hash_file "$ROLLBACK_SOURCE")" == "$ROLLBACK_SHA256" ]] || \
  die 'rollback SHA-256 mismatch'

[[ "$(uname -r)" == "$EXPECTED_RELEASE" ]] || die 'unexpected running kernel'
[[ "$(findmnt -rn -o PARTUUID /)" == "$EXPECTED_ROOT_PARTUUID" ]] || \
  die 'unexpected root partition'
[[ "$(findmnt -rn -o UUID /)" == "$EXPECTED_ROOT_UUID" ]] || die 'unexpected p2 UUID'
[[ "$(findmnt -rn -o FSTYPE /)" == ext4 ]] || die 'root is not ext4'
[[ ",$(findmnt -rn -o OPTIONS /)," == *,rw,* ]] || die 'root is not writable'
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem already reports errors'
[[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd has failed units'
[[ "$(df -B1 --output=avail / | tail -n 1 | tr -d ' ')" -ge 67108864 ]] || \
  die 'less than 64 MiB is free on p2'
[[ -f "$BASE_RECEIPT" && ! -L "$BASE_RECEIPT" ]] || die 'gaming v0.6 receipt is missing'
[[ "$(stat -c '%u:%g:%a:%h' "$BASE_RECEIPT")" == 0:0:600:1 ]] || \
  die 'gaming v0.6 receipt identity is unsafe'
[[ "$(hash_file "$BASE_RECEIPT")" == "$BASE_RECEIPT_SHA256" ]] || \
  die 'gaming v0.6 receipt mismatch'
[[ -f "$CONFIG" && ! -L "$CONFIG" ]] || die 'RetroArch config is missing'
[[ -f "$RUNNER" && ! -L "$RUNNER" ]] || die 'frontend runner is missing'
[[ -f "$VOLUME_HELPER" && ! -L "$VOLUME_HELPER" ]] || die 'volume helper is missing'
[[ -f "$VOLUME_UNIT" && ! -L "$VOLUME_UNIT" ]] || die 'volume unit is missing'
[[ "$(stat -c '%u:%g:%a:%h' "$CONFIG")" == 0:0:644:1 ]] || \
  die 'RetroArch config identity is unsafe'
[[ "$(stat -c '%u:%g:%a:%h' "$RUNNER")" == 0:0:755:1 ]] || \
  die 'frontend runner identity is unsafe'
[[ "$(stat -c '%u:%g:%a:%h' "$VOLUME_HELPER")" == 0:0:755:1 ]] || \
  die 'volume helper identity is unsafe'
[[ "$(stat -c '%u:%g:%a:%h' "$VOLUME_UNIT")" == 0:0:644:1 ]] || \
  die 'volume unit identity is unsafe'
validate_user_layout
validate_runtime_inputs

if [[ -e "$RECEIPT" || -L "$RECEIPT" ]]; then
  [[ -f "$RECEIPT" && ! -L "$RECEIPT" ]] || die 'installed receipt is unsafe'
  [[ "$(stat -c '%u:%g:%a:%h' "$RECEIPT")" == 0:0:600:1 ]] || \
    die 'installed receipt identity is unsafe'
  [[ "$(wc -l < "$RECEIPT" | tr -d '[:space:]')" == 19 ]] || \
    die 'installed receipt line count mismatch'
  grep -Fqx "feature_id=$FEATURE_ID" "$RECEIPT" || die 'installed receipt mismatch'
  grep -Fqx "installer_sha256=$installer_sha256" "$RECEIPT" || \
    die 'installed receipt came from another installer'
  for pair in \
    "base_config_sha256=$BASE_CONFIG_SHA256" "config_sha256=$CONFIG_SHA256" \
    "base_runner_sha256=$BASE_RUNNER_SHA256" "runner_sha256=$RUNNER_SHA256" \
    "base_volume_helper_sha256=$BASE_VOLUME_HELPER_SHA256" \
    "volume_helper_sha256=$VOLUME_HELPER_SHA256" \
    "base_volume_unit_sha256=$BASE_VOLUME_UNIT_SHA256" \
    "volume_unit_sha256=$VOLUME_UNIT_SHA256" "core_options_sha256=$CORE_OPTIONS_SHA256" \
    "core_sha256=$CORE_SHA256" "playlist_sha256=$PLAYLIST_SHA256" \
    "license_sha256=$LICENSE_SHA256" \
    "source_commit=$SOURCE_COMMIT" "core_info_sha256=$CORE_INFO_SHA256" \
    "mslug_rom_sha256=$MSLUG_ROM_SHA256" "neogeo_bios_sha256=$NEOGEO_BIOS_SHA256" \
    "rollback_sha256=$ROLLBACK_SHA256"; do
    grep -Fqx "$pair" "$RECEIPT" || die "installed receipt mismatch: $pair"
  done
  [[ "$(hash_file "$CONFIG")" == "$CONFIG_SHA256" ]] || die 'installed config mismatch'
  [[ "$(hash_file "$RUNNER")" == "$RUNNER_SHA256" ]] || die 'installed runner mismatch'
  [[ "$(hash_file "$VOLUME_HELPER")" == "$VOLUME_HELPER_SHA256" ]] || \
    die 'installed volume helper mismatch'
  [[ "$(hash_file "$VOLUME_UNIT")" == "$VOLUME_UNIT_SHA256" ]] || \
    die 'installed volume unit mismatch'
  [[ -f "$CORE_OPTIONS" && ! -L "$CORE_OPTIONS" && \
     "$(hash_file "$CORE_OPTIONS")" == "$CORE_OPTIONS_SHA256" ]] || \
    die 'installed core options mismatch'
  [[ "$(stat -c '%u:%g:%a:%h' "$CORE_OPTIONS")" == 1000:1000:600:1 ]] || \
    die 'installed core options identity is unsafe'
  [[ -d "$CORE_OPTIONS_DIR" && ! -L "$CORE_OPTIONS_DIR" ]] || \
    die 'installed core options directory is unsafe'
  [[ "$(stat -c '%u:%g:%a' "$CORE_OPTIONS_DIR")" == 1000:1000:700 ]] || \
    die 'installed core options directory identity is unsafe'
  core_options_members=$(find "$CORE_OPTIONS_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
  [[ "$core_options_members" == 'FinalBurn Neo (neogeo subset).opt' ]] || \
    die 'unexpected installed core options member set'
  [[ -f "$CORE" && ! -L "$CORE" && "$(hash_file "$CORE")" == "$CORE_SHA256" ]] || \
    die 'installed core mismatch'
  [[ -f "$PLAYLIST" && ! -L "$PLAYLIST" && \
     "$(hash_file "$PLAYLIST")" == "$PLAYLIST_SHA256" ]] || \
    die 'installed playlist mismatch'
  [[ "$(stat -c '%u:%g:%a:%h' "$CORE")" == 0:0:644:1 ]] || \
    die 'installed core identity is unsafe'
  [[ "$(stat -c '%u:%g:%a:%h' "$PLAYLIST")" == 1000:1000:600:1 ]] || \
    die 'installed playlist identity is unsafe'
  [[ -f "$LICENSE" && ! -L "$LICENSE" && \
     "$(hash_file "$LICENSE")" == "$LICENSE_SHA256" ]] || \
    die 'installed FBNeo license mismatch'
  [[ "$(stat -c '%u:%g:%a:%h' "$LICENSE")" == 0:0:644:1 ]] || \
    die 'installed FBNeo license identity is unsafe'
  [[ -d "$LICENSE_DIR" && ! -L "$LICENSE_DIR" ]] || \
    die 'installed FBNeo license directory is unsafe'
  [[ "$(stat -c '%u:%g:%a' "$LICENSE_DIR")" == 0:0:755 ]] || \
    die 'installed FBNeo license directory identity is unsafe'
  [[ -d "$VOLUME_STATE_DIR" && ! -L "$VOLUME_STATE_DIR" ]] || \
    die 'volume state directory is missing'
  [[ "$(stat -c '%u:%g:%a' "$VOLUME_STATE_DIR")" == 1000:1000:700 ]] || \
    die 'volume state directory identity is unsafe'
  volume_state_members=$(find "$VOLUME_STATE_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
  [[ "$volume_state_members" == level ]] || die 'unexpected installed volume state member set'
  [[ -f "$VOLUME_STATE" && ! -L "$VOLUME_STATE" ]] || die 'volume state is missing'
  [[ "$(stat -c '%u:%g:%a:%h' "$VOLUME_STATE")" == 1000:1000:600:1 ]] || \
    die 'volume state identity is unsafe'
  volume_level=$(<"$VOLUME_STATE")
  [[ "$volume_level" =~ ^[0-9]+$ ]] && (( volume_level <= 201 )) || \
    die 'volume state value is unsafe'
  [[ -f "$ROLLBACK" && ! -L "$ROLLBACK" && \
     "$(hash_file "$ROLLBACK")" == "$ROLLBACK_SHA256" ]] || \
    die 'installed rollback mismatch'
  [[ "$(stat -c '%u:%g:%a:%h' "$ROLLBACK")" == 0:0:700:1 ]] || \
    die 'installed rollback identity is unsafe'
  [[ -d "$STATE_PARENT" && ! -L "$STATE_PARENT" ]] || \
    die 'rollback state parent is missing'
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
    "$STATE_DIR/rollback.sh"; do
    [[ -f "$path" && ! -L "$path" ]] || die "unsafe rollback state member: $path"
    [[ "$(stat -c '%h' "$path")" == 1 ]] || die "hard-linked rollback state member: $path"
  done
  [[ "$(stat -c '%u:%g:%a' "$STATE_DIR/base-retroarch.cfg")" == 0:0:400 ]] || \
    die 'base config rollback state identity is unsafe'
  [[ "$(stat -c '%u:%g:%a' "$STATE_DIR/base-r46h-game-ui")" == 0:0:500 ]] || \
    die 'base runner rollback state identity is unsafe'
  [[ "$(stat -c '%u:%g:%a' "$STATE_DIR/base-r46h-volume-keys")" == 0:0:500 ]] || \
    die 'base volume helper rollback state identity is unsafe'
  [[ "$(stat -c '%u:%g:%a' "$STATE_DIR/base-r46h-volume-keys.service")" == \
     0:0:400 ]] || die 'base volume unit rollback state identity is unsafe'
  [[ "$(stat -c '%u:%g:%a' "$STATE_DIR/rollback.sh")" == 0:0:500 ]] || \
    die 'rollback helper state identity is unsafe'
  [[ "$(hash_file "$STATE_DIR/base-retroarch.cfg")" == "$BASE_CONFIG_SHA256" ]] || \
    die 'base config rollback state mismatch'
  [[ "$(hash_file "$STATE_DIR/base-r46h-game-ui")" == "$BASE_RUNNER_SHA256" ]] || \
    die 'base runner rollback state mismatch'
  [[ "$(hash_file "$STATE_DIR/base-r46h-volume-keys")" == \
     "$BASE_VOLUME_HELPER_SHA256" ]] || die 'base volume helper rollback state mismatch'
  [[ "$(hash_file "$STATE_DIR/base-r46h-volume-keys.service")" == \
     "$BASE_VOLUME_UNIT_SHA256" ]] || die 'base volume unit rollback state mismatch'
  [[ "$(hash_file "$STATE_DIR/rollback.sh")" == "$ROLLBACK_SHA256" ]] || \
    die 'rollback helper state mismatch'
  cmp -s "$STATE_DIR/rollback.sh" "$ROLLBACK" || die 'installed rollback differs from state'
  printf 'PASS: R46H Ozone/FBNeo v0.1 is already installed.\n'
  exit 0
fi

[[ "$(hash_file "$CONFIG")" == "$BASE_CONFIG_SHA256" ]] || die 'base config mismatch'
[[ "$(hash_file "$RUNNER")" == "$BASE_RUNNER_SHA256" ]] || die 'base runner mismatch'
[[ "$(hash_file "$VOLUME_HELPER")" == "$BASE_VOLUME_HELPER_SHA256" ]] || \
  die 'base volume helper mismatch'
[[ "$(hash_file "$VOLUME_UNIT")" == "$BASE_VOLUME_UNIT_SHA256" ]] || \
  die 'base volume unit mismatch'
[[ ! -e "$REMOTE_SCREEN_RECEIPT" && ! -L "$REMOTE_SCREEN_RECEIPT" ]] || \
  die 'remote-screen candidate must be rolled back before this frontend change'
for path in "$CORE" "$PLAYLIST" "$LICENSE" "$LICENSE_DIR" "$CORE_OPTIONS_DIR" \
  "$VOLUME_STATE_DIR" "$ROLLBACK" "$STATE_DIR"; do
  [[ ! -e "$path" && ! -L "$path" ]] || die "candidate path already exists: $path"
done
frontend_state=$(systemctl is-active r46h-gaming-frontend.service || true)
case $frontend_state in
  active) frontend_was_active=1 ;;
  inactive) ;;
  *) die "unexpected frontend state: $frontend_state" ;;
esac
frontend_restarts_before=$(systemctl show -p NRestarts --value r46h-gaming-frontend.service)
[[ "$frontend_restarts_before" =~ ^[0-9]+$ ]] || die 'cannot read frontend restart count'
volume_state=$(systemctl is-active r46h-volume-keys.service || true)
case $volume_state in
  active) volume_was_active=1 ;;
  inactive) die 'volume service must be active for the guarded update' ;;
  *) die "unexpected volume service state: $volume_state" ;;
esac
volume_restarts_before=$(systemctl show -p NRestarts --value r46h-volume-keys.service)
[[ "$volume_restarts_before" =~ ^[0-9]+$ ]] || die 'cannot read volume restart count'

trap cleanup_install EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
transaction_active=1
systemctl stop r46h-gaming-frontend.service
[[ "$(systemctl is-active r46h-gaming-frontend.service || true)" == inactive ]] || \
  die 'frontend did not stop'
[[ -z "$(pgrep -x retroarch || true)" ]] || die 'RetroArch survived frontend stop'
systemctl stop r46h-volume-keys.service
[[ "$(systemctl is-active r46h-volume-keys.service || true)" == inactive ]] || \
  die 'volume service did not stop'

if [[ -e "$STATE_PARENT" || -L "$STATE_PARENT" ]]; then
  [[ -d "$STATE_PARENT" && ! -L "$STATE_PARENT" ]] || die 'rollback state parent is unsafe'
  [[ "$(stat -c '%u:%g:%a' "$STATE_PARENT")" == 0:0:700 ]] || \
    die 'rollback state parent identity is unsafe'
else
  install -d -o root -g root -m 0700 "$STATE_PARENT"
  state_parent_created=1
fi
state_stage=$STATE_PARENT/.stage-v0.1.$$
[[ ! -e "$state_stage" && ! -L "$state_stage" ]] || die 'rollback state stage exists'
install -d -o root -g root -m 0700 "$state_stage"
install -o root -g root -m 0400 "$CONFIG" "$state_stage/base-retroarch.cfg"
install -o root -g root -m 0500 "$RUNNER" "$state_stage/base-r46h-game-ui"
install -o root -g root -m 0500 "$VOLUME_HELPER" \
  "$state_stage/base-r46h-volume-keys"
install -o root -g root -m 0400 "$VOLUME_UNIT" \
  "$state_stage/base-r46h-volume-keys.service"
install -o root -g root -m 0500 "$ROLLBACK_SOURCE" "$state_stage/rollback.sh"
[[ "$(hash_file "$state_stage/base-retroarch.cfg")" == "$BASE_CONFIG_SHA256" ]] || \
  die 'base config rollback state mismatch'
[[ "$(hash_file "$state_stage/base-r46h-game-ui")" == "$BASE_RUNNER_SHA256" ]] || \
  die 'base runner rollback state mismatch'
[[ "$(hash_file "$state_stage/base-r46h-volume-keys")" == \
   "$BASE_VOLUME_HELPER_SHA256" ]] || die 'base volume helper rollback state mismatch'
[[ "$(hash_file "$state_stage/base-r46h-volume-keys.service")" == \
   "$BASE_VOLUME_UNIT_SHA256" ]] || die 'base volume unit rollback state mismatch'
[[ "$(hash_file "$state_stage/rollback.sh")" == "$ROLLBACK_SHA256" ]] || \
  die 'rollback helper state mismatch'
mv -T --no-clobber -- "$state_stage" "$STATE_DIR"
state_stage=""
state_published=1

install -d -o root -g root -m 0755 "$LICENSE_DIR"
license_dir_created=1
if [[ ! -d "$CORE_OPTIONS_DIR" ]]; then
  install -d -o ark -g ark -m 0700 "$CORE_OPTIONS_DIR"
  core_options_dir_created=1
fi
config_stage=/etc/r46h/.retroarch.cfg.ozone-fbneo.$$
runner_stage=/usr/local/sbin/.r46h-game-ui.ozone-fbneo.$$
volume_helper_stage=/usr/local/libexec/.r46h-volume-keys.ozone-fbneo.$$
volume_unit_stage=/etc/systemd/system/.r46h-volume-keys.service.ozone-fbneo.$$
core_options_stage="$CORE_OPTIONS_DIR/.FinalBurn Neo (neogeo subset).opt.$$"
core_stage=/usr/local/libexec/.fbneo_neogeo_libretro.so.$$
playlist_stage="$PLAYLIST_DIR/.SNK - Neo Geo.lpl.$$"
license_stage=$LICENSE_DIR/.FBNEO-LICENSE.txt.$$
install -o root -g root -m 0644 "$CONFIG_SOURCE" "$config_stage"
install -o root -g root -m 0755 "$RUNNER_SOURCE" "$runner_stage"
install -o root -g root -m 0755 "$VOLUME_HELPER_SOURCE" "$volume_helper_stage"
install -o root -g root -m 0644 "$VOLUME_UNIT_SOURCE" "$volume_unit_stage"
install -o ark -g ark -m 0600 "$CORE_OPTIONS_SOURCE" "$core_options_stage"
install -o root -g root -m 0644 "$CORE_SOURCE" "$core_stage"
install -o ark -g ark -m 0600 "$PLAYLIST_SOURCE" "$playlist_stage"
install -o root -g root -m 0644 "$LICENSE_SOURCE" "$license_stage"
mv -f -- "$config_stage" "$CONFIG"
config_stage=""
config_replaced=1
mv -f -- "$runner_stage" "$RUNNER"
runner_stage=""
runner_replaced=1
mv -f -- "$volume_helper_stage" "$VOLUME_HELPER"
volume_helper_stage=""
volume_helper_replaced=1
mv -f -- "$volume_unit_stage" "$VOLUME_UNIT"
volume_unit_stage=""
volume_unit_replaced=1
systemctl daemon-reload
mv -f -- "$core_options_stage" "$CORE_OPTIONS"
core_options_stage=""
core_options_installed=1
mv -f -- "$core_stage" "$CORE"
core_stage=""
core_installed=1
mv -f -- "$playlist_stage" "$PLAYLIST"
playlist_stage=""
playlist_installed=1
mv -f -- "$license_stage" "$LICENSE"
license_stage=""
license_installed=1
install -o root -g root -m 0700 "$STATE_DIR/rollback.sh" "$ROLLBACK"

[[ "$(hash_file "$CONFIG")" == "$CONFIG_SHA256" ]] || die 'published config mismatch'
[[ "$(hash_file "$RUNNER")" == "$RUNNER_SHA256" ]] || die 'published runner mismatch'
[[ "$(hash_file "$VOLUME_HELPER")" == "$VOLUME_HELPER_SHA256" ]] || \
  die 'published volume helper mismatch'
[[ "$(hash_file "$VOLUME_UNIT")" == "$VOLUME_UNIT_SHA256" ]] || \
  die 'published volume unit mismatch'
[[ "$(hash_file "$CORE_OPTIONS")" == "$CORE_OPTIONS_SHA256" ]] || \
  die 'published core options mismatch'
[[ "$(hash_file "$CORE")" == "$CORE_SHA256" ]] || die 'published core mismatch'
[[ "$(hash_file "$PLAYLIST")" == "$PLAYLIST_SHA256" ]] || die 'published playlist mismatch'
[[ "$(hash_file "$LICENSE")" == "$LICENSE_SHA256" ]] || die 'published FBNeo license mismatch'
[[ "$(stat -c '%u:%g:%a:%h' "$CORE")" == 0:0:644:1 ]] || \
  die 'published core identity is unsafe'
[[ "$(stat -c '%u:%g:%a:%h' "$PLAYLIST")" == 1000:1000:600:1 ]] || \
  die 'published playlist identity is unsafe'
[[ "$(stat -c '%u:%g:%a:%h' "$LICENSE")" == 0:0:644:1 ]] || \
  die 'published FBNeo license identity is unsafe'
[[ "$(stat -c '%u:%g:%a:%h' "$VOLUME_HELPER")" == 0:0:755:1 ]] || \
  die 'published volume helper identity is unsafe'
[[ "$(stat -c '%u:%g:%a:%h' "$VOLUME_UNIT")" == 0:0:644:1 ]] || \
  die 'published volume unit identity is unsafe'
[[ "$(stat -c '%u:%g:%a:%h' "$CORE_OPTIONS")" == 1000:1000:600:1 ]] || \
  die 'published core options identity is unsafe'

receipt_stage=/var/lib/r46h/.gaming-ozone-fbneo-v0.1-installed.$$
printf 'feature_id=%s\nbase_config_sha256=%s\nconfig_sha256=%s\nbase_runner_sha256=%s\nrunner_sha256=%s\nbase_volume_helper_sha256=%s\nvolume_helper_sha256=%s\nbase_volume_unit_sha256=%s\nvolume_unit_sha256=%s\ncore_options_sha256=%s\ncore_sha256=%s\nplaylist_sha256=%s\nlicense_sha256=%s\nsource_commit=%s\ncore_info_sha256=%s\nmslug_rom_sha256=%s\nneogeo_bios_sha256=%s\nrollback_sha256=%s\ninstaller_sha256=%s\n' \
  "$FEATURE_ID" "$BASE_CONFIG_SHA256" "$CONFIG_SHA256" "$BASE_RUNNER_SHA256" \
  "$RUNNER_SHA256" "$BASE_VOLUME_HELPER_SHA256" "$VOLUME_HELPER_SHA256" \
  "$BASE_VOLUME_UNIT_SHA256" "$VOLUME_UNIT_SHA256" "$CORE_OPTIONS_SHA256" \
  "$CORE_SHA256" "$PLAYLIST_SHA256" "$LICENSE_SHA256" "$SOURCE_COMMIT" \
  "$CORE_INFO_SHA256" "$MSLUG_ROM_SHA256" "$NEOGEO_BIOS_SHA256" \
  "$ROLLBACK_SHA256" "$installer_sha256" > "$receipt_stage"
chmod 0600 "$receipt_stage"
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem reported an error during install'
sync
ln -- "$receipt_stage" "$RECEIPT"
rm -f -- "$receipt_stage"
receipt_stage=""
sync

if ! systemctl start r46h-volume-keys.service; then
  [[ -d "$VOLUME_STATE_DIR" && ! -L "$VOLUME_STATE_DIR" ]] && volume_state_created=1
  die 'candidate volume service failed to start'
fi
[[ -d "$VOLUME_STATE_DIR" && ! -L "$VOLUME_STATE_DIR" ]] && volume_state_created=1
for ((poll=0; poll<50; poll++)); do
  [[ "$(systemctl is-active r46h-volume-keys.service || true)" == active ]] && \
    [[ -f "$VOLUME_STATE" && ! -L "$VOLUME_STATE" ]] && break
  sleep 0.1
done
[[ "$(systemctl is-active r46h-volume-keys.service || true)" == active ]] || \
  die 'candidate volume service is not active'
[[ -f "$VOLUME_STATE" && ! -L "$VOLUME_STATE" ]] || die 'candidate volume state is missing'
[[ "$(stat -c '%u:%g:%a:%h' "$VOLUME_STATE")" == 1000:1000:600:1 ]] || \
  die 'candidate volume state identity is unsafe'
volume_level=$(<"$VOLUME_STATE")
[[ "$volume_level" =~ ^[0-9]+$ ]] && (( volume_level <= 201 )) || \
  die 'candidate volume state value is unsafe'

if (( frontend_was_active == 1 )); then
  systemctl start r46h-gaming-frontend.service
  for ((poll=0; poll<50; poll++)); do
    [[ "$(systemctl is-active r46h-gaming-frontend.service || true)" == active ]] && \
      [[ "$(pgrep -u 1000 -x retroarch | wc -l | tr -d '[:space:]')" == 1 ]] && break
    sleep 0.1
  done
  [[ "$(systemctl is-active r46h-gaming-frontend.service || true)" == active ]] || \
    die 'candidate frontend did not become active'
  [[ "$(pgrep -u 1000 -x retroarch | wc -l | tr -d '[:space:]')" == 1 ]] || \
    die 'candidate RetroArch process is unavailable'
fi
[[ "$(systemctl show -p NRestarts --value r46h-gaming-frontend.service)" == \
   "$frontend_restarts_before" ]] || die 'frontend restart count changed during install'
[[ "$(systemctl show -p NRestarts --value r46h-volume-keys.service)" == \
   "$volume_restarts_before" ]] || die 'volume restart count changed during install'
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem reported an error after install'
[[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd has failed units after install'

transaction_active=0
trap - EXIT INT TERM HUP
printf 'PASS: R46H Ozone/FBNeo v0.1 installed; frontend_restored=%s.\n' \
  "$([[ $frontend_was_active == 1 ]] && printf active || printf inactive)"
printf 'NEXT=open-the-SNK-Neo-Geo-playlist-and-launch-Metal-Slug\n'
