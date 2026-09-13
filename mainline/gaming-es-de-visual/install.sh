#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG
umask 077

readonly FEATURE_ID=r46h-gaming-es-de-visual-v0.1
readonly EXPECTED_RELEASE=6.12.99-r46h-mainline-v0.15-gaming-product
readonly EXPECTED_ROOT_PARTUUID=c9f931c9-02
readonly EXPECTED_ROOT_UUID=d3130007-46a4-4d56-9001-000000000007
readonly PAYLOAD_DIR=/run/r46h-gaming-es-de-visual-v0.1
readonly THEME=/opt/r46h/es-de/share/es-de/themes/linear-es-de/theme.xml
readonly SETTINGS=/home/ark/ES-DE/settings/es_settings.xml
readonly ES_DE=/opt/r46h/es-de/bin/es-de
readonly ES_DE_RECEIPT=/var/lib/r46h/gaming-es-de-v0.1-installed
readonly ROLLBACK=/usr/local/sbin/r46h-es-de-visual-rollback
readonly RECEIPT=/var/lib/r46h/gaming-es-de-visual-v0.1-installed
readonly STATE_PARENT=/var/lib/r46h-gaming-es-de-visual
readonly STATE_DIR=$STATE_PARENT/v0.1
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count
readonly OLD_THEME_SHA256=b3ee1b1283b71ace6bd8bcb91d7c67a937c4008ca422269af32ccec82840e7eb
readonly NEW_THEME_SHA256=2816222c88822a900a01bb966c54e27cfe32d7837edf0062d0edaeb70641736b
readonly ES_DE_SHA256=9c6e50433b9bca5ac1c01030bc4d7b143f05c2cd27c52e6f5f765b0acf01be98
readonly ROLLBACK_SHA256=1d35f453a81f803a34f760dc8a073d69dab02a03d7e282578c15bd76729f3516

state_stage=""
settings_stage=""
rollback_stage=""
receipt_stage=""
transaction_active=0

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

hash_is() {
  local path=$1 expected=$2
  [[ -f $path && ! -L $path && $(sha256sum "$path" | awk '{print $1}') == "$expected" ]]
}

require_file() {
  local path=$1 expected=$2 identity=$3
  hash_is "$path" "$expected" || die "file identity mismatch: $path"
  [[ $(stat -c '%u:%g:%a:%h' "$path") == "$identity" ]] || die "unsafe file metadata: $path"
}

cleanup() {
  local status=$? restore_ok=1
  trap - EXIT INT TERM HUP
  set +e
  rm -f -- "$settings_stage" "$rollback_stage" "$receipt_stage"
  if (( transaction_active == 1 )); then
    systemctl stop r46h-gaming-frontend.service >/dev/null 2>&1 || true
    if [[ -d $STATE_DIR && ! -L $STATE_DIR ]]; then
      install -o root -g root -m 0644 "$STATE_DIR/previous-theme.xml" "$THEME" || restore_ok=0
      install -o ark -g ark -m 0600 "$STATE_DIR/previous-settings.xml" "$SETTINGS" || restore_ok=0
    else
      restore_ok=0
    fi
    systemctl start r46h-gaming-frontend.service >/dev/null 2>&1 || restore_ok=0
    if (( restore_ok == 1 )); then
      rm -f -- "$RECEIPT" "$ROLLBACK"
      find "$STATE_DIR" -depth -delete || status=1
      rmdir -- "$STATE_PARENT" 2>/dev/null || status=1
    else
      printf 'ERROR: automatic restore incomplete; keep %s\n' "$STATE_DIR" >&2
      status=1
    fi
  fi
  if [[ -n $state_stage && -d $state_stage && ! -L $state_stage ]]; then
    find "$state_stage" -depth -delete || status=1
  fi
  (( transaction_active == 1 )) || rmdir -- "$STATE_PARENT" 2>/dev/null || true
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

[[ $# == 2 && $1 == --installer-sha256 ]] || die 'usage: install.sh --installer-sha256 HEX'
installer_sha256=$2
[[ $installer_sha256 =~ ^[0-9a-f]{64}$ ]] || die 'invalid installer SHA-256'
(( EUID == 0 )) || die 'root is required'
[[ ${BASH_SOURCE[0]} == "$PAYLOAD_DIR/install.sh" ]] || die 'run the staged installer'
[[ -d $PAYLOAD_DIR && ! -L $PAYLOAD_DIR && $(stat -c '%u:%g:%a' "$PAYLOAD_DIR") == 0:0:700 ]] || \
  die 'unsafe payload directory'
payload_members=$(find "$PAYLOAD_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
[[ $payload_members == $'README.md\nSHA256SUMS\ninstall.sh\nr46h-theme.xml\nrollback.sh' ]] || \
  die 'unexpected payload member set'
while IFS= read -r -d '' path; do
  [[ -f $path && ! -L $path && $(stat -c '%u:%g:%a:%h' "$path") == 0:0:600:1 ]] || \
    die "unsafe payload member: $path"
done < <(find "$PAYLOAD_DIR" -mindepth 1 -maxdepth 1 -print0)
require_file "$PAYLOAD_DIR/install.sh" "$installer_sha256" 0:0:600:1
require_file "$PAYLOAD_DIR/r46h-theme.xml" "$NEW_THEME_SHA256" 0:0:600:1
require_file "$PAYLOAD_DIR/rollback.sh" "$ROLLBACK_SHA256" 0:0:600:1

[[ $(uname -r) == "$EXPECTED_RELEASE" ]] || die 'unexpected running kernel'
[[ $(findmnt -rn -o PARTUUID /) == "$EXPECTED_ROOT_PARTUUID" ]] || die 'unexpected root partition'
[[ $(findmnt -rn -o UUID /) == "$EXPECTED_ROOT_UUID" ]] || die 'unexpected root filesystem'
[[ ,$(findmnt -rn -o OPTIONS /), == *,rw,* ]] || die 'p2 is not writable'
[[ ,$(findmnt -rn -o OPTIONS /roms), == *,ro,* ]] || die '/roms is not read-only'
[[ $(cat "$EXT4_ERRORS") == 0 ]] || die 'p2 already reports ext4 errors'
[[ -z $(systemctl --failed --no-legend --plain) ]] || die 'systemd has failed units'
require_file "$ES_DE" "$ES_DE_SHA256" 0:0:755:1
[[ -f $ES_DE_RECEIPT && ! -L $ES_DE_RECEIPT && $(stat -c '%u:%g:%a:%h' "$ES_DE_RECEIPT") == 0:0:600:1 ]] || \
  die 'ES-DE receipt is unsafe'
grep -Fqx 'feature_id=r46h-gaming-es-de-v0.1' "$ES_DE_RECEIPT" || die 'ES-DE receipt mismatch'
grep -Fqx "es_de_sha256=$ES_DE_SHA256" "$ES_DE_RECEIPT" || die 'ES-DE binary receipt mismatch'
require_file "$THEME" "$OLD_THEME_SHA256" 0:0:644:1
[[ -f $SETTINGS && ! -L $SETTINGS && $(stat -c '%u:%g:%a:%h' "$SETTINGS") == 1000:1000:600:1 ]] || \
  die 'unsafe ES-DE settings'
[[ $(grep -Fxc '<string name="ThemeTransitions" value="builtin-instant" />' "$SETTINGS") == 1 ]] || \
  die 'expected one instant transition setting'
[[ $(grep -Fxc '<string name="ThemeTransitions" value="builtin-slide" />' "$SETTINGS") == 0 ]] || \
  die 'slide transition is already present'
[[ $(grep -Fxc '<string name="ThemeColorScheme" value="" />' "$SETTINGS") == 1 ]] || \
  die 'expected the default color scheme'
[[ $(grep -Fxc '<string name="ThemeColorScheme" value="oled" />' "$SETTINGS") == 0 ]] || \
  die 'OLED color scheme is already present'
[[ $(systemctl is-active r46h-gaming-frontend.service || true) == active ]] || die 'frontend is not active'
[[ $(pgrep -u 1000 -xc es-de) == 1 ]] || die 'expected one ES-DE process'
for path in "$RECEIPT" "$STATE_DIR" "$ROLLBACK"; do
  [[ ! -e $path && ! -L $path ]] || die "overlay path already exists: $path"
done

install -d -o root -g root -m 0700 "$STATE_PARENT"
state_stage=$STATE_PARENT/.v0.1-stage.$$
install -d -o root -g root -m 0700 "$state_stage"
install -o root -g root -m 0400 "$THEME" "$state_stage/previous-theme.xml"
install -o root -g root -m 0400 "$SETTINGS" "$state_stage/previous-settings.xml"
install -o root -g root -m 0400 "$PAYLOAD_DIR/r46h-theme.xml" "$state_stage/visual-theme.xml"
install -o root -g root -m 0500 "$PAYLOAD_DIR/rollback.sh" "$state_stage/rollback.sh"
mv -T -- "$state_stage" "$STATE_DIR"; state_stage=""
transaction_active=1

settings_stage=/home/ark/ES-DE/settings/.es_settings.visual.$$
sed -e 's|<string name="ThemeTransitions" value="builtin-instant" />|<string name="ThemeTransitions" value="builtin-slide" />|' \
  -e 's|<string name="ThemeColorScheme" value="" />|<string name="ThemeColorScheme" value="oled" />|' \
  "$SETTINGS" > "$settings_stage"
[[ $(grep -Fxc '<string name="ThemeTransitions" value="builtin-slide" />' "$settings_stage") == 1 ]] || \
  die 'could not apply slide transition'
[[ $(grep -Fxc '<string name="ThemeColorScheme" value="oled" />' "$settings_stage") == 1 ]] || \
  die 'could not apply OLED color scheme'
chown ark:ark "$settings_stage"
chmod 0600 "$settings_stage"

systemctl stop r46h-gaming-frontend.service
install -o root -g root -m 0644 "$PAYLOAD_DIR/r46h-theme.xml" "$THEME"
mv -f -- "$settings_stage" "$SETTINGS"; settings_stage=""
rollback_stage=/usr/local/sbin/.r46h-es-de-visual-rollback.$$
install -o root -g root -m 0700 "$PAYLOAD_DIR/rollback.sh" "$rollback_stage"
mv -T -- "$rollback_stage" "$ROLLBACK"; rollback_stage=""

previous_settings_sha256=$(sha256sum "$STATE_DIR/previous-settings.xml" | awk '{print $1}')
receipt_stage=/var/lib/r46h/.gaming-es-de-visual-v0.1-installed.$$
printf 'feature_id=%s\nold_theme_sha256=%s\nnew_theme_sha256=%s\nprevious_settings_sha256=%s\nrollback_sha256=%s\ninstaller_sha256=%s\n' \
  "$FEATURE_ID" "$OLD_THEME_SHA256" "$NEW_THEME_SHA256" "$previous_settings_sha256" \
  "$ROLLBACK_SHA256" "$installer_sha256" > "$receipt_stage"
chmod 0600 "$receipt_stage"
mv -T -- "$receipt_stage" "$RECEIPT"; receipt_stage=""

systemctl start r46h-gaming-frontend.service
for ((poll=0; poll<100; poll++)); do
  systemctl is-active --quiet r46h-gaming-frontend.service && pgrep -u 1000 -x es-de >/dev/null && break
  sleep 0.1
done
require_file "$THEME" "$NEW_THEME_SHA256" 0:0:644:1
require_file "$ROLLBACK" "$ROLLBACK_SHA256" 0:0:700:1
[[ $(grep -Fxc '<string name="ThemeTransitions" value="builtin-slide" />' "$SETTINGS") == 1 ]] || \
  die 'slide transition did not persist'
[[ $(grep -Fxc '<string name="ThemeColorScheme" value="oled" />' "$SETTINGS") == 1 ]] || \
  die 'OLED color scheme did not persist'
[[ $(pgrep -u 1000 -xc es-de) == 1 ]] || die 'expected one updated ES-DE process'
[[ $(cat "$EXT4_ERRORS") == 0 && -z $(systemctl --failed --no-legend --plain) ]] || \
  die 'target health changed'
sync

transaction_active=0
trap - EXIT INT TERM HUP
printf 'R46H_ES_DE_VISUAL_INSTALL result=pass theme=linear-oled-optimized transition=slide rollback=%s\n' "$ROLLBACK"
