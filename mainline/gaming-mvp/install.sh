#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG

readonly PAYLOAD_ID=r46h-gaming-mvp-v0.6
readonly EXPECTED_RUNNING_RELEASE=6.12.99-r46h-mainline-v0.15-gaming-product
readonly EXPECTED_ROOT_PARTUUID=c9f931c9-02
readonly PAYLOAD_DIR=/run/r46h-gaming-mvp-v0.6
readonly RECEIPT=/var/lib/r46h/gaming-mvp-v0.6-installed
readonly PREVIOUS_RECEIPT=/var/lib/r46h/gaming-mvp-v0.5-installed
readonly ROLLBACK_STATE=/var/lib/r46h/gaming-mvp-v0.6-rollback
readonly RUNNER=/usr/local/sbin/r46h-game-ui
readonly CONDITION=/usr/local/libexec/r46h-gaming-frontend-condition
readonly PRODUCT_DOC=/usr/share/doc/r46h-gaming-mvp/GAMING-PRODUCT.md
readonly FSTAB=/etc/fstab
readonly FSTAB_SHA256=390d3e67cfaa42aa2781b06c0bb167cae961034d22563584c58ae57e0d5cada5
readonly EXT4_ERRORS=/sys/fs/ext4/mmcblk0p2/errors_count
readonly PREVIOUS_RECEIPT_SHA256=5cdfa424a28858a91e0344f0544e962c5aa0258bb3a7ea41db76df16c77da5d1
readonly PREVIOUS_RUNNER_SHA256=3db31b4c205f98377a56822320f2c63dabce685387becdcb4824fec092ce3133
readonly PREVIOUS_CONDITION_SHA256=888a44d822030430924b012c81069c117c842e17a5173711d6a85e7d351b6031
readonly PREVIOUS_PRODUCT_DOC_SHA256=fdf2be72c5c12c57e48a3082a51ecc8b6da09188a627ceece698b0d481d7d3db

runner_stage=/usr/local/sbin/.r46h-game-ui.v0.6.$$
condition_stage=/usr/local/libexec/.r46h-gaming-frontend-condition.v0.6.$$
document_stage=/usr/share/doc/r46h-gaming-mvp/.GAMING-PRODUCT.v0.6.$$
receipt_stage=/var/lib/r46h/.gaming-mvp-v0.6-installed.$$
state_stage=/var/lib/r46h/.gaming-mvp-v0.6-rollback.$$
rollback_needed=0
staging_started=0
state_stage_created=0

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

hash_file() {
  sha256sum "$1" | awk '{print $1}'
}

require_identity() {
  local path=$1
  local metadata=$2
  local digest=$3

  [[ -f "$path" && ! -L "$path" ]] || die "unsafe or missing file: $path"
  [[ "$(stat -c '%u:%g:%a:%h' "$path")" == "$metadata" ]] || \
    die "unexpected metadata: $path"
  [[ "$(hash_file "$path")" == "$digest" ]] || die "unexpected content: $path"
}

cleanup() {
  local status=$?
  local restore_status=0

  trap - EXIT INT TERM HUP
  set +e
  if (( staging_started == 1 )); then
    rm -f -- "$runner_stage" "$condition_stage" "$document_stage" "$receipt_stage"
  fi
  if (( status != 0 && rollback_needed == 1 )); then
    install -o root -g root -m 0755 "$ROLLBACK_STATE/r46h-game-ui" "$RUNNER" || restore_status=1
    install -o root -g root -m 0755 \
      "$ROLLBACK_STATE/r46h-gaming-frontend-condition" "$CONDITION" || restore_status=1
    install -o root -g root -m 0644 "$ROLLBACK_STATE/GAMING-PRODUCT.md" \
      "$PRODUCT_DOC" || restore_status=1
    rm -f -- "$RECEIPT" || restore_status=1
    sync || restore_status=1
    if (( restore_status == 0 )); then
      printf 'R46H_GAMING_V06_ROLLBACK result=pass state=%s\n' "$ROLLBACK_STATE" >&2
    else
      printf 'R46H_GAMING_V06_ROLLBACK result=fail state=%s\n' "$ROLLBACK_STATE" >&2
      status=1
    fi
  fi
  if (( state_stage_created == 1 )) && [[ -d "$state_stage" && ! -L "$state_stage" ]]; then
    rm -f -- "$state_stage"/GAMING-PRODUCT.md \
      "$state_stage"/gaming-mvp-v0.5-installed "$state_stage"/r46h-game-ui \
      "$state_stage"/r46h-gaming-frontend-condition "$state_stage"/ROLLBACK-INFO \
      "$state_stage"/SHA256SUMS
    rmdir -- "$state_stage" 2>/dev/null || true
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

(( EUID == 0 )) || die 'root is required'
[[ "${BASH_SOURCE[0]}" == "$PAYLOAD_DIR/install.sh" ]] || die "extract payload at $PAYLOAD_DIR"
[[ -d "$PAYLOAD_DIR" && ! -L "$PAYLOAD_DIR" ]] || die 'unsafe payload directory'
[[ "$(stat -c '%u:%a' "$PAYLOAD_DIR")" == 0:700 ]] || die 'unsafe payload ownership'
[[ "$(uname -r)" == "$EXPECTED_RUNNING_RELEASE" ]] || die 'install from the exact v0.15 product boot'
[[ "$(findmnt -rn -o PARTUUID /)" == "$EXPECTED_ROOT_PARTUUID" ]] || die 'unexpected root partition'
[[ "$(findmnt -rn -o FSTYPE /)" == ext4 ]] || die 'root is not ext4'
[[ "$(findmnt -rn -o OPTIONS /)" == *rw* ]] || die 'root is not writable'
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem already reports errors'
[[ -z "$(systemctl --failed --no-legend --plain)" ]] || die 'systemd has failed units'
[[ "$(df -B1 --output=avail / | tail -n 1 | tr -d ' ')" -ge 1073741824 ]] || \
  die 'less than 1 GiB is free on root'

cd "$PAYLOAD_DIR"
sha256sum -c SHA256SUMS
[[ "$(<PAYLOAD.COMPLETE)" == "sha256sums_sha256=$(hash_file SHA256SUMS)" ]] || \
  die 'payload completion marker mismatch'
[[ "$(hash_file files/fstab)" == "$FSTAB_SHA256" ]] || die 'payload fstab mismatch'
[[ "$(hash_file "$FSTAB")" == "$FSTAB_SHA256" ]] || die 'target fstab mismatch'
roms_options=$(findmnt -rn -o OPTIONS /roms 2>/dev/null || true)
[[ -z "$roms_options" || ",$roms_options," == *,ro,* ]] || die 'mounted /roms is writable'

if [[ -e "$RECEIPT" || -L "$RECEIPT" ]]; then
  [[ -f "$RECEIPT" && ! -L "$RECEIPT" ]] || die 'unsafe gaming receipt'
  [[ "$(stat -c '%u:%g:%a:%h' "$RECEIPT")" == 0:0:600:1 ]] || \
    die 'unexpected gaming receipt metadata'
  grep -Fqx "payload_id=$PAYLOAD_ID" "$RECEIPT" || die 'conflicting gaming receipt'
  grep -Fqx "target_release=$EXPECTED_RUNNING_RELEASE" "$RECEIPT" || \
    die 'gaming receipt release mismatch'
  grep -Fqx "package_manifest_sha256=$(hash_file PACKAGES.tsv)" "$RECEIPT" || \
    die 'gaming receipt package manifest mismatch'
  grep -Fqx "payload_sha256sums_sha256=$(hash_file SHA256SUMS)" "$RECEIPT" || \
    die 'gaming receipt payload manifest mismatch'
  cmp -s files/r46h-game-ui "$RUNNER" || die 'installed v0.6 runner mismatch'
  cmp -s files/r46h-gaming-frontend-condition "$CONDITION" || \
    die 'installed v0.6 condition mismatch'
  cmp -s files/GAMING-PRODUCT.md "$PRODUCT_DOC" || die 'installed v0.6 document mismatch'
  [[ -d "$ROLLBACK_STATE" && ! -L "$ROLLBACK_STATE" ]] || die 'rollback state is missing'
  [[ "$(stat -c '%u:%g:%a' "$ROLLBACK_STATE")" == 0:0:700 ]] || \
    die 'rollback state metadata mismatch'
  (cd "$ROLLBACK_STATE" && sha256sum -c SHA256SUMS) || die 'rollback state checksum mismatch'
  printf 'PASS: gaming product v0.6 renderer upgrade is already installed.\n'
  exit 0
fi

require_identity "$PREVIOUS_RECEIPT" 0:0:600:1 "$PREVIOUS_RECEIPT_SHA256"
grep -Fqx 'payload_id=r46h-gaming-mvp-v0.5' "$PREVIOUS_RECEIPT" || \
  die 'unexpected v0.5 receipt identity'
grep -Fqx "target_release=$EXPECTED_RUNNING_RELEASE" "$PREVIOUS_RECEIPT" || \
  die 'v0.5 receipt release mismatch'
require_identity "$RUNNER" 0:0:755:1 "$PREVIOUS_RUNNER_SHA256"
require_identity "$CONDITION" 0:0:755:1 "$PREVIOUS_CONDITION_SHA256"
require_identity "$PRODUCT_DOC" 0:0:644:1 "$PREVIOUS_PRODUCT_DOC_SHA256"

while IFS=$'\t' read -r package version; do
  [[ -n "$package" && -n "$version" ]] || die 'invalid package version manifest'
  [[ "$(dpkg-query -W -f='${db:Status-Abbrev}\t${Version}' "$package")" == $'ii \t'"$version" ]] || \
    die "installed package mismatch: $package"
done < PACKAGES.tsv

if systemctl is-active --quiet r46h-gaming-frontend.service; then
  die 'gaming frontend must be inactive before install'
fi
[[ -z "$(/usr/bin/pgrep -x retroarch || true)" ]] || die 'RetroArch is still running'
for path in "$runner_stage" "$condition_stage" "$document_stage" "$receipt_stage" \
  "$state_stage" "$ROLLBACK_STATE"; do
  [[ ! -e "$path" && ! -L "$path" ]] || die "staging or rollback path already exists: $path"
done

staging_started=1
install -o root -g root -m 0755 files/r46h-game-ui "$runner_stage"
install -o root -g root -m 0755 files/r46h-gaming-frontend-condition "$condition_stage"
install -o root -g root -m 0644 files/GAMING-PRODUCT.md "$document_stage"
package_manifest_sha256=$(hash_file PACKAGES.tsv)
payload_sha256sums_sha256=$(hash_file SHA256SUMS)
printf 'payload_id=%s\ntarget_release=%s\npackage_manifest_sha256=%s\npayload_sha256sums_sha256=%s\n' \
  "$PAYLOAD_ID" "$EXPECTED_RUNNING_RELEASE" "$package_manifest_sha256" \
  "$payload_sha256sums_sha256" > "$receipt_stage"
chmod 0600 "$receipt_stage"
cmp -s files/r46h-game-ui "$runner_stage" || die 'staged runner mismatch'
cmp -s files/r46h-gaming-frontend-condition "$condition_stage" || die 'staged condition mismatch'
cmp -s files/GAMING-PRODUCT.md "$document_stage" || die 'staged document mismatch'

mkdir -m 0700 "$state_stage"
state_stage_created=1
install -o root -g root -m 0755 "$RUNNER" "$state_stage/r46h-game-ui"
install -o root -g root -m 0755 "$CONDITION" \
  "$state_stage/r46h-gaming-frontend-condition"
install -o root -g root -m 0644 "$PRODUCT_DOC" "$state_stage/GAMING-PRODUCT.md"
install -o root -g root -m 0600 "$PREVIOUS_RECEIPT" \
  "$state_stage/gaming-mvp-v0.5-installed"
printf 'upgrade_id=%s\nprevious_receipt_sha256=%s\n' \
  "$PAYLOAD_ID" "$PREVIOUS_RECEIPT_SHA256" > "$state_stage/ROLLBACK-INFO"
chmod 0600 "$state_stage/ROLLBACK-INFO"
(
  cd "$state_stage"
  sha256sum GAMING-PRODUCT.md gaming-mvp-v0.5-installed r46h-game-ui \
    r46h-gaming-frontend-condition ROLLBACK-INFO > SHA256SUMS
)
chmod 0600 "$state_stage/SHA256SUMS"
sync
mv -- "$state_stage" "$ROLLBACK_STATE"
state_stage_created=0
sync

rollback_needed=1
mv -f -- "$document_stage" "$PRODUCT_DOC"
mv -f -- "$runner_stage" "$RUNNER"
mv -f -- "$condition_stage" "$CONDITION"
mv -f -- "$receipt_stage" "$RECEIPT"
sync

cmp -s files/r46h-game-ui "$RUNNER" || die 'installed v0.6 runner mismatch'
cmp -s files/r46h-gaming-frontend-condition "$CONDITION" || \
  die 'installed v0.6 condition mismatch'
cmp -s files/GAMING-PRODUCT.md "$PRODUCT_DOC" || die 'installed v0.6 document mismatch'
[[ "$(stat -c '%u:%g:%a:%h' "$RUNNER")" == 0:0:755:1 ]] || die 'installed runner metadata mismatch'
[[ "$(stat -c '%u:%g:%a:%h' "$CONDITION")" == 0:0:755:1 ]] || \
  die 'installed condition metadata mismatch'
[[ "$(stat -c '%u:%g:%a:%h' "$PRODUCT_DOC")" == 0:0:644:1 ]] || \
  die 'installed document metadata mismatch'
[[ "$(stat -c '%u:%g:%a:%h' "$RECEIPT")" == 0:0:600:1 ]] || \
  die 'installed receipt metadata mismatch'
"$CONDITION" || die 'installed frontend condition failed'
[[ "$(cat "$EXT4_ERRORS")" == 0 ]] || die 'root filesystem reported an error during install'
rollback_needed=0

printf 'PASS: gaming product v0.6 renderer upgrade installed.\n'
printf 'ROLLBACK_STATE=%s\n' "$ROLLBACK_STATE"
printf 'NEXT=start-r46h-gaming-frontend-service-and-run-focused-smoke\n'
