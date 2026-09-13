#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG

readonly WORKFLOW_ID=r46h-rom-workflow-v0.1
readonly EXPECTED_RELEASE=6.12.99-r46h-mainline-v0.10-adc-full-range
readonly EXPECTED_ROOT_PARTUUID=c9f931c9-02
readonly BASE_RECEIPT=/var/lib/r46h/gaming-mvp-v0.3-installed
readonly BASE_RECEIPT_SHA256=08e0c35e924666b5fb946fadadad95218ed6d49d3e3eca3a8cee3f85d98700b4
readonly BASE_CONFIG_SHA256=bdb46922d746cb9acb4207a3c86431a51e66b46ca1fdd7264640cb749a307019
readonly CONFIG_SHA256=621fdf049cd05e6aa02c62b5c42ed37a768ce9342af14c4563cfd4466d80d078
readonly PAYLOAD_DIR=/run/r46h-rom-workflow-v0.1
readonly PUBLIC_KEY="$PAYLOAD_DIR/id_rsa.pub"
readonly CONFIG="$PAYLOAD_DIR/retroarch.cfg"
readonly RECEIPT=/var/lib/r46h/rom-workflow-v0.1-installed
readonly AUTHORIZED_KEYS=/home/ark/.ssh/authorized_keys
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

usage() {
  printf 'usage: sudo %s --installer-sha256 HEX --public-key-sha256 HEX\n' "$0"
}

require_root_directory() {
  local path=$1
  [[ -d "$path" && ! -L "$path" ]] || die "unsafe root directory: $path"
  [[ "$(stat -c '%u:%g' "$path")" == 0:0 ]] || die "unsafe root directory owner: $path"
  [[ -z "$(find "$path" -maxdepth 0 -perm /022 -print -quit)" ]] || \
    die "root directory is group/world writable: $path"
}

reject_link_if_present() {
  local path=$1
  [[ ! -L "$path" ]] || die "symbolic-link directory is forbidden: $path"
}

[[ $# == 4 ]] || { usage >&2; exit 2; }
installer_sha256=
public_key_sha256=
while (( $# > 0 )); do
  case $1 in
    --installer-sha256) installer_sha256=$2 ;;
    --public-key-sha256) public_key_sha256=$2 ;;
    *) usage >&2; exit 2 ;;
  esac
  shift 2
done
[[ "$installer_sha256" =~ ^[0-9a-f]{64}$ ]] || die 'invalid installer SHA-256'
[[ "$public_key_sha256" =~ ^[0-9a-f]{64}$ ]] || die 'invalid public-key SHA-256'

(( EUID == 0 )) || die 'root is required'
[[ "${BASH_SOURCE[0]}" == "$PAYLOAD_DIR/install.sh" ]] || die "stage payload at $PAYLOAD_DIR"
[[ -d "$PAYLOAD_DIR" && ! -L "$PAYLOAD_DIR" ]] || die 'unsafe payload directory'
[[ "$(stat -c '%u:%a:%h' "$PAYLOAD_DIR")" == 0:700:2 ]] || die 'unsafe payload identity'
payload_members=$(find "$PAYLOAD_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
[[ "$payload_members" == $'id_rsa.pub\ninstall.sh\nretroarch.cfg' ]] || die 'unexpected payload member set'
for path in "${BASH_SOURCE[0]}" "$PUBLIC_KEY" "$CONFIG"; do
  [[ -f "$path" && ! -L "$path" ]] || die "unsafe payload member: $path"
  [[ "$(stat -c '%u:%a:%h' "$path")" == 0:600:1 ]] || die "unsafe payload member identity: $path"
done
[[ "$(sha256sum "${BASH_SOURCE[0]}" | awk '{print $1}')" == "$installer_sha256" ]] || die 'installer SHA-256 mismatch'
[[ "$(sha256sum "$PUBLIC_KEY" | awk '{print $1}')" == "$public_key_sha256" ]] || die 'public-key SHA-256 mismatch'
[[ "$(sha256sum "$CONFIG" | awk '{print $1}')" == "$CONFIG_SHA256" ]] || die 'RetroArch config SHA-256 mismatch'

[[ "$(uname -r)" == "$EXPECTED_RELEASE" ]] || die 'unexpected running kernel'
[[ "$(findmnt -rn -o PARTUUID /)" == "$EXPECTED_ROOT_PARTUUID" ]] || die 'unexpected root partition'
[[ "$(findmnt -rn -o FSTYPE /)" == ext4 ]] || die 'root is not ext4'
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem already reports errors'
[[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd has failed units'
[[ -f "$BASE_RECEIPT" && ! -L "$BASE_RECEIPT" ]] || die 'gaming v0.3 receipt is missing'
[[ "$(stat -c '%u:%a:%h' "$BASE_RECEIPT")" == 0:600:1 ]] || die 'unsafe gaming receipt'
[[ "$(sha256sum "$BASE_RECEIPT" | awk '{print $1}')" == "$BASE_RECEIPT_SHA256" ]] || die 'gaming receipt mismatch'
[[ "$(id -u ark):$(id -g ark)" == 1000:1000 ]] || die 'unexpected ark identity'
require_root_directory /etc/r46h
require_root_directory /var/lib/r46h
[[ -d /home/ark && ! -L /home/ark ]] || die 'unsafe ark home directory'
[[ "$(stat -c '%u:%g' /home/ark)" == 1000:1000 ]] || die 'unexpected ark home owner'

key_fields=$(awk 'NR == 1 && NF == 3 && $1 == "ssh-rsa" { print NF } END { if (NR != 1) exit 1 }' "$PUBLIC_KEY")
[[ "$key_fields" == 3 ]] || die 'public key is not one RSA key'
key_fingerprint=$(ssh-keygen -lf "$PUBLIC_KEY" -E sha256 | awk 'NF >= 4 && $1 == 3072 && $2 ~ /^SHA256:/ && $4 == "(RSA)" { print $2 }')
[[ "$key_fingerprint" =~ ^SHA256:[A-Za-z0-9+/]+$ ]] || die 'unexpected public-key fingerprint'

current_config_sha256=$(sha256sum /etc/r46h/retroarch.cfg | awk '{print $1}')
[[ "$current_config_sha256" == "$BASE_CONFIG_SHA256" || "$current_config_sha256" == "$CONFIG_SHA256" ]] || \
  die 'installed RetroArch config was modified'
if [[ -e "$AUTHORIZED_KEYS" || -L "$AUTHORIZED_KEYS" ]]; then
  [[ -f "$AUTHORIZED_KEYS" && ! -L "$AUTHORIZED_KEYS" ]] || die 'unsafe authorized_keys'
  [[ "$(stat -c '%u:%g:%a:%h' "$AUTHORIZED_KEYS")" == 1000:1000:600:1 ]] || die 'unsafe authorized_keys identity'
  cmp -s "$PUBLIC_KEY" "$AUTHORIZED_KEYS" || die 'authorized_keys already contains different data'
fi
[[ ! -e "$RECEIPT" && ! -L "$RECEIPT" ]] || die 'workflow receipt already exists'

systemctl stop r46h-gaming-frontend.service
[[ "$(systemctl is-active r46h-gaming-frontend.service || true)" == inactive ]] || die 'frontend did not stop'
[[ -z "$(pgrep -x retroarch || true)" ]] || die 'RetroArch process survived service stop'

for directory in /home/ark/.ssh /home/ark/.local /home/ark/.local/share /home/ark/.local/share/retroarch; do
  reject_link_if_present "$directory"
done
install -d -o ark -g ark -m 0700 /home/ark/.ssh
if [[ ! -e "$AUTHORIZED_KEYS" ]]; then
  install -o ark -g ark -m 0600 "$PUBLIC_KEY" "$AUTHORIZED_KEYS"
fi
install -d -o root -g root -m 0755 /roms
for directory in nes gb gba nds; do
  install -d -o ark -g ark -m 0755 "/roms/$directory"
done
install -d -o ark -g ark -m 0700 \
  /home/ark/.local/share/retroarch/playlists \
  /home/ark/.local/share/retroarch/saves \
  /home/ark/.local/share/retroarch/states

config_stage=/etc/r46h/.retroarch.cfg.$$
receipt_stage=/var/lib/r46h/.rom-workflow-v0.1-installed.$$
trap 'rm -f -- "$config_stage" "$receipt_stage"' EXIT
install -o root -g root -m 0644 "$CONFIG" "$config_stage"
mv -f "$config_stage" /etc/r46h/retroarch.cfg
printf 'workflow_id=%s\nbase_receipt_sha256=%s\nconfig_sha256=%s\npublic_key_sha256=%s\npublic_key_fingerprint=%s\ninstaller_sha256=%s\n' \
  "$WORKFLOW_ID" "$BASE_RECEIPT_SHA256" "$CONFIG_SHA256" "$public_key_sha256" \
  "$key_fingerprint" "$installer_sha256" > "$receipt_stage"
chmod 0600 "$receipt_stage"
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem reported an error during install'
sync
ln "$receipt_stage" "$RECEIPT"
rm -f "$receipt_stage"
sync
trap - EXIT

printf 'PASS: R46H ROM-over-Wi-Fi workflow installed.\n'
printf 'PUBLIC_KEY_FINGERPRINT=%s\n' "$key_fingerprint"
printf 'NEXT=systemctl-start-then-scp-one-rom-as-ark\n'
