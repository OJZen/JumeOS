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
readonly THEME=/opt/r46h/es-de/share/es-de/themes/linear-es-de/theme.xml
readonly SETTINGS=/home/ark/ES-DE/settings/es_settings.xml
readonly ROLLBACK=/usr/local/sbin/r46h-es-de-visual-rollback
readonly RECEIPT=/var/lib/r46h/gaming-es-de-visual-v0.1-installed
readonly STATE_PARENT=/var/lib/r46h-gaming-es-de-visual
readonly STATE_DIR=$STATE_PARENT/v0.1
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count
readonly OLD_THEME_SHA256=b3ee1b1283b71ace6bd8bcb91d7c67a937c4008ca422269af32ccec82840e7eb
readonly NEW_THEME_SHA256=2816222c88822a900a01bb966c54e27cfe32d7837edf0062d0edaeb70641736b

settings_current=""
settings_stage=""
transaction_active=0

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

hash_is() {
  local path=$1 expected=$2
  [[ -f $path && ! -L $path && $(sha256sum "$path" | awk '{print $1}') == "$expected" ]]
}

cleanup() {
  local status=$? restore_ok=1
  trap - EXIT INT TERM HUP
  set +e
  if (( transaction_active == 1 )); then
    systemctl stop r46h-gaming-frontend.service >/dev/null 2>&1 || true
    install -o root -g root -m 0644 "$STATE_DIR/visual-theme.xml" "$THEME" || restore_ok=0
    install -o ark -g ark -m 0600 "$settings_current" "$SETTINGS" || restore_ok=0
    systemctl start r46h-gaming-frontend.service >/dev/null 2>&1 || restore_ok=0
    (( restore_ok == 1 )) || status=1
  fi
  rm -f -- "$settings_current" "$settings_stage"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

[[ $# == 0 ]] || die 'this rollback accepts no arguments'
(( EUID == 0 )) || die 'root is required'
[[ ${BASH_SOURCE[0]} == "$ROLLBACK" ]] || die 'run the installed rollback helper'
[[ $(uname -r) == "$EXPECTED_RELEASE" ]] || die 'unexpected running kernel'
[[ $(findmnt -rn -o PARTUUID /) == "$EXPECTED_ROOT_PARTUUID" ]] || die 'unexpected root partition'
[[ $(findmnt -rn -o UUID /) == "$EXPECTED_ROOT_UUID" ]] || die 'unexpected root filesystem'
[[ ,$(findmnt -rn -o OPTIONS /), == *,rw,* ]] || die 'p2 is not writable'
[[ ,$(findmnt -rn -o OPTIONS /roms), == *,ro,* ]] || die '/roms is not read-only'
[[ $(cat "$EXT4_ERRORS") == 0 && -z $(systemctl --failed --no-legend --plain) ]] || die 'target is unhealthy'
[[ $(systemctl is-active r46h-gaming-frontend.service || true) == active ]] || die 'frontend is not active'
[[ $(pgrep -u 1000 -xc es-de) == 1 ]] || die 'expected one ES-DE process'
hash_is "$THEME" "$NEW_THEME_SHA256" || die 'visual theme changed'
[[ $(grep -Fxc '<string name="ThemeTransitions" value="builtin-slide" />' "$SETTINGS") == 1 ]] || \
  die 'visual transition changed'
[[ $(grep -Fxc '<string name="ThemeColorScheme" value="oled" />' "$SETTINGS") == 1 ]] || \
  die 'visual color scheme changed'
[[ -d $STATE_DIR && ! -L $STATE_DIR && $(stat -c '%u:%g:%a' "$STATE_DIR") == 0:0:700 ]] || \
  die 'rollback state is unsafe'
state_members=$(find "$STATE_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
[[ $state_members == $'previous-settings.xml\nprevious-theme.xml\nrollback.sh\nvisual-theme.xml' ]] || \
  die 'unexpected rollback state'
hash_is "$STATE_DIR/previous-theme.xml" "$OLD_THEME_SHA256" || die 'previous theme changed'
hash_is "$STATE_DIR/visual-theme.xml" "$NEW_THEME_SHA256" || die 'visual theme state changed'
[[ $(stat -c '%u:%g:%a:%h' "$STATE_DIR/previous-theme.xml") == 0:0:400:1 ]] || die 'unsafe theme state'
[[ -f $STATE_DIR/previous-settings.xml && ! -L $STATE_DIR/previous-settings.xml && \
   $(stat -c '%u:%g:%a:%h' "$STATE_DIR/previous-settings.xml") == 0:0:400:1 ]] || die 'unsafe settings state'
[[ -f $STATE_DIR/rollback.sh && ! -L $STATE_DIR/rollback.sh && \
   $(stat -c '%u:%g:%a:%h' "$STATE_DIR/rollback.sh") == 0:0:500:1 ]] || die 'unsafe rollback state'
[[ -f $RECEIPT && ! -L $RECEIPT && $(stat -c '%u:%g:%a:%h' "$RECEIPT") == 0:0:600:1 ]] || \
  die 'receipt is unsafe'
grep -Fqx 'feature_id=r46h-gaming-es-de-visual-v0.1' "$RECEIPT" || die 'receipt mismatch'
grep -Fqx "new_theme_sha256=$NEW_THEME_SHA256" "$RECEIPT" || die 'theme receipt mismatch'
previous_settings_sha256=$(sha256sum "$STATE_DIR/previous-settings.xml" | awk '{print $1}')
grep -Fqx "previous_settings_sha256=$previous_settings_sha256" "$RECEIPT" || die 'settings state mismatch'
rollback_sha256=$(sha256sum "$ROLLBACK" | awk '{print $1}')
grep -Fqx "rollback_sha256=$rollback_sha256" "$RECEIPT" || die 'rollback receipt mismatch'
cmp -s "$STATE_DIR/rollback.sh" "$ROLLBACK" || die 'rollback helper changed'

settings_stage=/home/ark/ES-DE/settings/.es_settings.visual-rollback.$$
settings_current=/run/.r46h-es-de-visual-current-settings.$$
install -o root -g root -m 0400 "$SETTINGS" "$settings_current"
sed -e 's|<string name="ThemeTransitions" value="builtin-slide" />|<string name="ThemeTransitions" value="builtin-instant" />|' \
  -e 's|<string name="ThemeColorScheme" value="oled" />|<string name="ThemeColorScheme" value="" />|' \
  "$SETTINGS" > "$settings_stage"
[[ $(grep -Fxc '<string name="ThemeTransitions" value="builtin-instant" />' "$settings_stage") == 1 ]] || \
  die 'could not restore transition'
[[ $(grep -Fxc '<string name="ThemeColorScheme" value="" />' "$settings_stage") == 1 ]] || \
  die 'could not restore color scheme'
chown ark:ark "$settings_stage"
chmod 0600 "$settings_stage"

transaction_active=1
systemctl stop r46h-gaming-frontend.service
install -o root -g root -m 0644 "$STATE_DIR/previous-theme.xml" "$THEME"
mv -f -- "$settings_stage" "$SETTINGS"; settings_stage=""
systemctl start r46h-gaming-frontend.service
for ((poll=0; poll<100; poll++)); do
  systemctl is-active --quiet r46h-gaming-frontend.service && pgrep -u 1000 -x es-de >/dev/null && break
  sleep 0.1
done
hash_is "$THEME" "$OLD_THEME_SHA256" || die 'text theme was not restored'
[[ $(pgrep -u 1000 -xc es-de) == 1 ]] || die 'expected one restored ES-DE process'
[[ $(cat "$EXT4_ERRORS") == 0 && -z $(systemctl --failed --no-legend --plain) ]] || die 'target health changed'
transaction_active=0
rm -f -- "$settings_current"; settings_current=""
rm -f -- "$RECEIPT"
find "$STATE_DIR" -depth -delete
rmdir -- "$STATE_PARENT"
rm -f -- "$ROLLBACK"
sync
trap - EXIT INT TERM HUP
printf 'R46H_ES_DE_VISUAL_ROLLBACK result=pass theme=text color=default transition=instant\n'
