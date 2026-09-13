#!/usr/bin/env bash
set -Eeuo pipefail

# Exercise the generated deployment scripts against directory-backed card and
# target fixtures.  Test mode is deliberately container-only; no block device
# is passed through to the container and no host mount is modified.

readonly IMAGE=arkos4clone/r46h-kernel-builder:trixie-arm64

if [[ "${1:-}" != --inside ]]; then
  repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
  exec docker run --rm --entrypoint /bin/bash \
    -v "${repo}:/repo" \
    "$IMAGE" /repo/mainline/tests/test-easyroms-deploy-fixture.sh --inside
fi

readonly REPO=/repo
readonly MAINLINE=${REPO}/mainline
readonly CACHE=${MAINLINE}/out/.cache
readonly GENERATOR=${MAINLINE}/scripts/generate-easyroms-bundle.py
readonly PACKAGE_V02=${MAINLINE}/out/r46h-mainline-test-v0.2.tar.gz
readonly PACKAGE_V07=${MAINLINE}/out/r46h-mainline-test-v0.7-host-timers.tar.gz
readonly PACKAGE_V08=${MAINLINE}/out/r46h-mainline-test-v0.8-bootloader-handoff.tar.gz
readonly CARD_PROFILE=${MAINLINE}/deploy/profiles/hl-r46h-v22-g92-v1.json
readonly BASELINE_V07=${MAINLINE}/deploy/baselines/v0.7-host-timers.json
readonly DEPLOY_V07=${MAINLINE}/out/r46h-easyroms-v0.7-host-timers/payload
# Exact historical inputs are kept as one documented, ignored test fixture.
readonly LEGACY_FIXTURE=${MAINLINE}/out/test-fixtures/legacy-v08-deploy
readonly LEGACY_FIXTURE_SUMS=${MAINLINE}/tests/fixtures/legacy-v08-deploy.sha256
readonly BOOT_RECEIPT=${LEGACY_FIXTURE}/boot
readonly RAW_RECEIPT=${LEGACY_FIXTURE}/raw
readonly FALLBACK_RELEASE=6.12.99-r46h-mainline-v0.2
readonly CURRENT_ID=v0.7-host-timers
readonly NEW_ID=v0.8-bootloader-handoff
readonly OLD_RELEASE=6.12.99-r46h-mainline-v0.7-host-timers
readonly NEW_RELEASE=6.12.99-r46h-mainline-v0.8-bootloader-handoff
readonly CURRENT_BASELINE=$BASELINE_V07
readonly CURRENT_DEPLOY=$DEPLOY_V07
readonly CURRENT_OWNER=$DEPLOY_V07/.r46h-stage-owner
readonly CURRENT_PACKAGE=$PACKAGE_V07
readonly NEW_PACKAGE=$PACKAGE_V08
readonly DEPLOY_PURPOSE=mainline-panel-bootloader-handoff-test

fail() {
  printf 'TEST FAILURE: %s\n' "$*" >&2
  exit 1
}

required=(
  "$GENERATOR"
  "$PACKAGE_V02"
  "$CURRENT_PACKAGE"
  "$NEW_PACKAGE"
  "$CARD_PROFILE"
  "$CURRENT_BASELINE"
  "$CURRENT_DEPLOY/DEPLOY-MANIFEST"
  "$CURRENT_DEPLOY/STAGE-COMPLETE"
  "$LEGACY_FIXTURE_SUMS"
  "$CURRENT_DEPLOY/Image.mainline-${CURRENT_ID}.gz"
  "$CURRENT_DEPLOY/boot.ini.${CURRENT_ID}"
  "$CURRENT_DEPLOY/rk3326-r46h-mainline-${CURRENT_ID}.dtb"
  "$CURRENT_OWNER"
  "$BOOT_RECEIPT/Image.mainline-test.gz"
  "$BOOT_RECEIPT/boot.ini.test"
  "$BOOT_RECEIPT/rk3326-r46h-mainline-test.dtb"
  "$BOOT_RECEIPT/arkos4clone-uboot.dtb"
  "$BOOT_RECEIPT/consoles/r46h/arkos4clone-uboot.dtb"
  "$RAW_RECEIPT/prefix-before.bin"
  "$RAW_RECEIPT/fdisk-before.txt"
)
for fixture in "${required[@]}"; do
  [[ -f "$fixture" && ! -L "$fixture" ]] ||
    fail "required audited ${CURRENT_ID} -> ${NEW_ID} deployment fixture is missing: ${fixture}"
done

(
  cd -- "$LEGACY_FIXTURE"
  sha256sum -c "$LEGACY_FIXTURE_SUMS"
) >/dev/null || fail "legacy deployment fixture checksum mismatch"

mkdir -p -- "$CACHE"
bundle_root=$(mktemp -d "${CACHE}/.r46h-deploy-integration.XXXXXX")
stage_root=$(mktemp -d "${CACHE}/.r46h-stage-test.XXXXXX")
failure_stage_root=$(mktemp -d "${CACHE}/.r46h-stage-test.XXXXXX")
target_root=$(mktemp -d "${CACHE}/.r46h-target-test.XXXXXX")
readonly bundle_root stage_root failure_stage_root target_root
chmod 0700 "$bundle_root" "$stage_root" "$failure_stage_root" "$target_root"

cleanup_path() {
  local path=$1 expected_prefix=$2
  [[ -n "$path" && "$path" == "${CACHE}/${expected_prefix}"* &&
     -d "$path" && ! -L "$path" ]] || {
    printf 'WARNING: refusing unsafe test cleanup: %s\n' "$path" >&2
    return
  }
  rm -rf -- "$path"
}
cleanup() {
  local status=$?
  trap - EXIT INT TERM HUP
  cleanup_path "$target_root" .r46h-target-test.
  cleanup_path "$failure_stage_root" .r46h-stage-test.
  cleanup_path "$stage_root" .r46h-stage-test.
  cleanup_path "$bundle_root" .r46h-deploy-integration.
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

manifest_value() {
  local manifest=$1 key=$2 count value
  count=$(grep -c "^${key}=" "$manifest" 2>/dev/null || true)
  [[ "$count" -eq 1 ]] || fail "manifest key ${key} must appear exactly once"
  value=$(sed -n "s/^${key}=//p" "$manifest")
  [[ "$value" != *$'\n'* ]] || fail "manifest key ${key} is multiline"
  printf '%s' "$value"
}

hash_is() {
  local path=$1 expected=$2 label=$3
  [[ -f "$path" && ! -L "$path" ]] || fail "missing or unsafe ${label}: ${path}"
  [[ "$(sha256sum "$path" | awk '{print $1}')" == "$expected" ]] ||
    fail "${label} SHA-256 mismatch"
}

printf 'TEST: generate %s bundle from the audited %s baseline\n' "$NEW_ID" "$CURRENT_ID"
python3 "$GENERATOR" \
  --package-tar "$NEW_PACKAGE" \
  --card-profile "$CARD_PROFILE" \
  --current-baseline "$CURRENT_BASELINE" \
  --purpose "$DEPLOY_PURPOSE" \
  --source-date-epoch 1785369600 \
  --output-dir "$bundle_root"

readonly bundle=${bundle_root}/r46h-easyroms-${NEW_ID}
readonly generated_payload=${bundle}/payload
readonly generated_manifest=${generated_payload}/DEPLOY-MANIFEST
[[ -d "$bundle" && ! -L "$bundle" ]] || fail 'generator did not publish the bundle'

printf 'TEST: stage generated payload into a p3-only directory fixture\n'
mkdir -p \
  "$stage_root/card/boot/consoles/r46h" \
  "$stage_root/card/easyroms/r46h-${CURRENT_ID}" \
  "$stage_root/raw" \
  "$stage_root/receipts"
printf 'initial\n' > "$stage_root/mount-state"
manifest_value "$generated_manifest" card_profile_sha256 > "$stage_root/card-profile.sha256"
printf '\n' >> "$stage_root/card-profile.sha256"

cp "$CURRENT_DEPLOY/boot.ini.${CURRENT_ID}" "$stage_root/card/boot/boot.ini"
cp "$CURRENT_DEPLOY/boot.ini.${CURRENT_ID}" "$stage_root/card/boot/boot.ini.${CURRENT_ID}"
cp "$CURRENT_DEPLOY/Image.mainline-${CURRENT_ID}.gz" "$stage_root/card/boot/"
cp "$CURRENT_DEPLOY/rk3326-r46h-mainline-${CURRENT_ID}.dtb" "$stage_root/card/boot/"
cp "$BOOT_RECEIPT/boot.ini.test" "$stage_root/card/boot/boot.ini.test"
cp "$BOOT_RECEIPT/boot.ini.test" "$stage_root/card/boot/boot.ini.v0.2-known-good"
cp "$BOOT_RECEIPT/Image.mainline-test.gz" "$stage_root/card/boot/"
cp "$BOOT_RECEIPT/rk3326-r46h-mainline-test.dtb" "$stage_root/card/boot/"
cp "$BOOT_RECEIPT/arkos4clone-uboot.dtb" "$stage_root/card/boot/"
cp "$BOOT_RECEIPT/consoles/r46h/arkos4clone-uboot.dtb" \
  "$stage_root/card/boot/consoles/r46h/"

current_payload="$stage_root/card/easyroms/r46h-${CURRENT_ID}"
cp "$CURRENT_OWNER" "$current_payload/.r46h-stage-owner"
cp "$CURRENT_DEPLOY/DEPLOY-MANIFEST" "$current_payload/"
cp "$CURRENT_PACKAGE" "$current_payload/"
cp "$CURRENT_DEPLOY/STAGE-COMPLETE" "$current_payload/"
cp "$RAW_RECEIPT/prefix-before.bin" "$stage_root/raw/prefix.bin"
cp "$RAW_RECEIPT/fdisk-before.txt" "$stage_root/raw/fdisk.txt"
printf 'directory-backed-boot-partition-fixture\n' > "$stage_root/raw/p1.bin"

cp -a "$stage_root/." "$failure_stage_root/"
printf 'TEST: reject the unsupported stage-resume option before any card write\n'
if R46H_DEPLOY_STAGE_TEST_ROOT="$failure_stage_root" \
   bash "$bundle/stage-on-macos.sh" \
     --device /dev/disk4 \
     --confirm-device /dev/disk4 \
     --receipt-parent "$failure_stage_root/receipts" \
     --resume-work-receipt "$failure_stage_root/missing-work-receipt"; then
  fail 'stage silently accepted its unimplemented resume option'
fi
[[ ! -e "$failure_stage_root/card/easyroms/r46h-${NEW_ID}" ]] ||
  fail 'resume-option rejection happened after a card write'

printf 'TEST: reject a receipt parent located on fake BOOT before any card write\n'
if R46H_DEPLOY_STAGE_TEST_ROOT="$failure_stage_root" \
   bash "$bundle/stage-on-macos.sh" \
     --device /dev/disk4 \
     --confirm-device /dev/disk4 \
     --receipt-parent "$failure_stage_root/card/boot"; then
  fail 'stage accepted a receipt parent on fake BOOT'
fi
[[ ! -e "$failure_stage_root/card/easyroms/r46h-${NEW_ID}" ]] ||
  fail 'receipt-parent rejection happened after a card write'

printf 'TEST: invalidate STAGE-COMPLETE after an injected post-publication failure\n'
if R46H_DEPLOY_STAGE_TEST_ROOT="$failure_stage_root" \
   R46H_DEPLOY_STAGE_TEST_FAIL_AFTER_GATE_MOVE=1 \
   bash "$bundle/stage-on-macos.sh" \
     --device /dev/disk4 \
     --confirm-device /dev/disk4 \
     --receipt-parent "$failure_stage_root/receipts"; then
  fail 'post-gate fault injection unexpectedly succeeded'
fi
[[ ! -e "$failure_stage_root/card/easyroms/r46h-${NEW_ID}/STAGE-COMPLETE" ]] ||
  fail 'cleanup left STAGE-COMPLETE consumable after the injected failure'
[[ -z "$(find "$failure_stage_root/receipts" -name COMPLETE -print -quit)" ]] ||
  fail 'failed stage published a complete receipt'
[[ -z "$(find "$failure_stage_root/receipts" -name TARGET-TRUST-RECEIPT -print -quit)" ]] ||
  fail 'post-gate failure leaked a consumable external trust receipt'
if grep -REn '^completion_secret=[0-9a-f]{64}$' \
  "$failure_stage_root/card" "$failure_stage_root/receipts"; then
  fail 'post-gate failure leaked the completion secret onto the card or external receipt parent'
fi

R46H_DEPLOY_STAGE_TEST_ROOT="$stage_root" \
  bash "$bundle/stage-on-macos.sh" \
    --device /dev/disk4 \
    --confirm-device /dev/disk4 \
    --receipt-parent "$stage_root/receipts"

readonly staged_payload=${stage_root}/card/easyroms/r46h-${NEW_ID}
[[ "$(tr -d '\r\n' < "$stage_root/mount-state")" == ejected ]] ||
  fail 'stage fixture was not ejected'
[[ -f "$staged_payload/STAGE-COMPLETE" ]] || fail 'stage completion gate is missing'
[[ -z "$(find "$stage_root/card/easyroms" -name '._*' -print -quit)" ]] ||
  fail 'AppleDouble residue remains after staging'
receipt_count=$(find "$stage_root/receipts" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d '[:space:]')
[[ "$receipt_count" == 1 ]] || fail 'stage did not publish exactly one receipt directory'
stage_receipt=$(find "$stage_root/receipts" -mindepth 1 -maxdepth 1 -type d -print)
[[ -f "$stage_receipt/COMPLETE" && -f "$stage_receipt/EJECTED" ]] ||
  fail 'stage receipt is incomplete'
grep -qx 'only_written_partition=3' "$stage_receipt/STAGE-RESULT" ||
  fail 'stage receipt does not prove p3-only scope'
readonly trust_receipt=${stage_receipt}/TARGET-TRUST-RECEIPT
trust_receipt_hash=$(awk '{print $1}' "$stage_receipt/TARGET-TRUST-RECEIPT.sha256")
bootstrap_hash=$(manifest_value "$trust_receipt" bootstrap_target_sha256)
readonly trust_receipt_hash bootstrap_hash
hash_is "$trust_receipt" "$trust_receipt_hash" 'external target trust receipt'
hash_is "$staged_payload/bootstrap-target.sh" "$bootstrap_hash" 'externally anchored bootstrap'

printf 'TEST: install modules, rerun idempotently, and recover a missing receipt\n'
mkdir -p \
  "$target_root/boot" \
  "$target_root/roms" \
  "$target_root/lib/modules" \
  "$target_root/run/lock" \
  "$target_root/test-state" \
  "$target_root/v02-extract"

printf 'TEST: count all supported compressed module suffixes on target\n'
compressed_parent="$target_root/compressed-modules"
compressed_release=6.12.99-r46h-mainline-compressed-fixture
mkdir -p "$compressed_parent/$compressed_release"
printf 'ko\n' > "$compressed_parent/$compressed_release/a.ko"
printf 'ko.gz\n' > "$compressed_parent/$compressed_release/b.ko.gz"
printf 'ko.xz\n' > "$compressed_parent/$compressed_release/c.ko.xz"
printf 'ko.zst\n' > "$compressed_parent/$compressed_release/d.ko.zst"
printf 'metadata\n' > "$compressed_parent/$compressed_release/modules.dep"
compressed_manifest="$target_root/compressed-modules.sha256s"
(
  cd "$compressed_parent"
  find "$compressed_release" -type f -print | LC_ALL=C sort |
    while IFS= read -r module_file; do
      printf '%s  rootfs/lib/modules/%s\n' "$(sha256sum "$module_file" | awk '{print $1}')" "$module_file"
    done
) > "$compressed_manifest"
compressed_hash=$(sha256sum "$compressed_manifest" | awk '{print $1}')
# shellcheck source=/dev/null
source "$MAINLINE/deploy/templates/target-common.sh.in"
r46h_verify_module_tree "$compressed_parent" "$compressed_release" "$compressed_hash" 4 5 \
  'compressed fixture'
rm -rf -- "$compressed_parent"
rm -- "$compressed_manifest"

printf 'TEST: accept exFAT root defaults and reject ambiguous private mount options\n'
# shellcheck source=/dev/null
source "$generated_payload/target-common.sh"

assert_private_mount_options() {
  local expected=$1 options=$2 label=$3 common_result=reject
  if r46h_mount_options_secure "$options"; then
    common_result=accept
  fi
  [[ "$common_result" == "$expected" ]] ||
    fail "target-common ${label}: expected ${expected}, got ${common_result}"
}

assert_private_mount_options accept \
  'rw,nosuid,nodev,noexec,noatime,fmask=0077,dmask=0077' \
  'did not accept omitted root uid/gid defaults'
assert_private_mount_options accept \
  'rw,nosuid,nodev,noexec,noatime,uid=0,gid=0,fmask=77,dmask=77' \
  'did not accept explicit root uid/gid'
assert_private_mount_options accept 'rw,uid=0,fmask=0077,dmask=0077' \
  'did not accept an explicit root uid with default gid'
assert_private_mount_options accept 'rw,gid=0,fmask=0077,dmask=0077' \
  'did not accept a default uid with explicit root gid'
assert_private_mount_options reject 'rw,uid=1002,fmask=0077,dmask=0077' \
  'accepted a non-root uid'
assert_private_mount_options reject 'rw,gid=1002,fmask=0077,dmask=0077' \
  'accepted a non-root gid'
assert_private_mount_options reject 'rw,uid=0,uid=1002,fmask=0077,dmask=0077' \
  'accepted mixed duplicate uid values'
assert_private_mount_options reject 'rw,gid=0,gid=1002,fmask=0077,dmask=0077' \
  'accepted mixed duplicate gid values'
assert_private_mount_options reject 'rw,uid=0,uid=0,fmask=0077,dmask=0077' \
  'accepted a duplicate uid option'
assert_private_mount_options reject 'rw,fmask=0077,dmask=0077,ro' \
  'accepted conflicting read/write policies'
assert_private_mount_options reject 'rw,dmask=0077' 'accepted a missing fmask'
assert_private_mount_options reject 'rw,fmask=0077' 'accepted a missing dmask'
assert_private_mount_options reject 'rw,fmask=0000,dmask=0077' 'accepted a weak fmask'
assert_private_mount_options reject 'rw,fmask=0077,dmask=0000' 'accepted a weak dmask'
assert_private_mount_options reject 'rw,fmask=0077,fmask=77,dmask=0077' \
  'accepted duplicate fmask values'

cp -a "$stage_root/card/boot/." "$target_root/boot/"
cp -a "$stage_root/card/easyroms/." "$target_root/roms/"
chown -R 1002:1002 -- "$target_root/roms"
find "$target_root/roms" -type d -exec chmod 0777 {} +
find "$target_root/roms" -type f -exec chmod 0777 {} +
cp "$stage_root/card-profile.sha256" "$target_root/test-state/card-profile.sha256"
printf '%s\n' "$OLD_RELEASE" > "$target_root/test-state/running-release"
printf '%s\n' 'rw,noatime,uid=1002,gid=1002,fmask=0000,dmask=0000' > \
  "$target_root/test-state/roms-mount-options"
printf '%s\n' rw > "$target_root/test-state/tools-mount-state"
printf '%s\n' 0 > "$target_root/test-state/rootfs-errors-count"
: > "$target_root/test-state/rootfs-kernel-log"
tar --no-same-owner -xzf "$PACKAGE_V02" -C "$target_root/v02-extract"
mv \
  "$target_root/v02-extract/r46h-mainline-test-v0.2/rootfs/lib/modules/$FALLBACK_RELEASE" \
  "$target_root/lib/modules/$FALLBACK_RELEASE"
rm -rf -- "$target_root/v02-extract"

readonly target_payload=${target_root}/roms/r46h-${NEW_ID}
mkdir -m 0700 "$target_root/run/r46h-deploy"
readonly trusted_parent=${target_root}/run/r46h-deploy
readonly trusted_bootstrap=${trusted_parent}/bootstrap-target.sh
readonly trusted_receipt=${trusted_parent}/TARGET-TRUST-RECEIPT
cp "$target_payload/bootstrap-target.sh" "$trusted_bootstrap"
chmod 0700 "$trusted_bootstrap"
cp "$trust_receipt" "$trusted_receipt"
chmod 0600 "$trusted_receipt"
hash_is "$trusted_bootstrap" "$bootstrap_hash" 'root-owned bootstrap copy'
hash_is "$trusted_receipt" "$trust_receipt_hash" 'root-owned external receipt copy'

run_bootstrap() {
  local requested_action=$1 receipt=${2:-$trusted_receipt}
  local receipt_hash=${3:-$trust_receipt_hash}
  R46H_DEPLOY_TARGET_TEST_ROOT="$target_root" bash "$trusted_bootstrap" \
    --external-receipt "$receipt" \
    --external-receipt-sha256 "$receipt_hash" \
    --action "$requested_action"
}

assert_public_card_restored() {
  local expected_roms_policy=${1:-rw} expected_tools_policy=${2:-rw}
  grep -qx "${expected_roms_policy},noatime,uid=1002,gid=1002,fmask=0000,dmask=0000" \
    "$target_root/test-state/roms-mount-options" ||
    fail 'bootstrap did not restore the original ArkOS EASYROMS read/write policy'
  grep -qx "$expected_tools_policy" "$target_root/test-state/tools-mount-state" ||
    fail 'bootstrap did not restore the original /opt/system/Tools read/write policy'
  [[ -d "$target_root/roms" && ! -L "$target_root/roms" &&
     "$(stat -c '%u:%g:%a' -- "$target_root/roms")" == 1002:1002:777 ]] ||
    fail 'fake public EASYROMS did not regain its ArkOS-visible ownership and mode'
  [[ "$(stat -c '%u:%g:%a' -- "$target_root/roms/r46h-${NEW_ID}")" == 1002:1002:777 ]] ||
    fail 'fake public payload did not regain its world-writable ArkOS view'
  [[ -z "$(find "$trusted_parent" -maxdepth 1 -type d -name 'r46h-*.trusted.*' -print -quit)" ]] ||
    fail 'trusted payload or private mount residue remains after bootstrap'
}

printf 'TEST: reject every direct /roms script execution before privileged writes\n'
if R46H_DEPLOY_TARGET_TEST_ROOT="$target_root" bash "$target_payload/install-modules.sh"; then
  fail 'direct world-writable installer execution was accepted'
fi
if R46H_DEPLOY_TARGET_TEST_ROOT="$target_root" bash "$target_payload/switch-boot.sh"; then
  fail 'direct world-writable switch execution was accepted'
fi
[[ ! -e "$target_root/lib/modules/$NEW_RELEASE" && ! -e "$target_payload/MODULES-INSTALLED" ]] ||
  fail 'direct /roms rejection happened after a privileged write'
assert_public_card_restored
[[ "$(stat -c '%u:%g:%a' -- "$target_payload/install-modules.sh")" == 1002:1002:777 ]] ||
  fail 'world-writable replacement fixture does not model the ArkOS p3 view'

printf 'TEST: reject a world-writable payload replacement before secure remount\n'
printf '%s\n' '# replacement attack' >> "$target_payload/install-modules.sh"
if run_bootstrap install-modules; then
  fail 'bootstrap accepted a replaced world-writable payload file'
fi
assert_public_card_restored
[[ ! -e "$target_root/lib/modules/$NEW_RELEASE" && ! -e "$target_payload/MODULES-INSTALLED" ]] ||
  fail 'payload replacement rejection happened after a module write'
cp "$generated_payload/install-modules.sh" "$target_payload/install-modules.sh"

printf 'TEST: reject unknown payload entries and preserve initial read-only mount policies\n'
printf '%s\n' 'unknown untrusted entry' > "$target_payload/.UNTRUSTED-ENTRY"
printf '%s\n' 'ro,noatime,uid=1002,gid=1002,fmask=0000,dmask=0000' > \
  "$target_root/test-state/roms-mount-options"
printf '%s\n' ro > "$target_root/test-state/tools-mount-state"
if run_bootstrap install-modules; then
  fail 'bootstrap accepted an unknown world-writable payload entry'
fi
assert_public_card_restored ro ro
[[ ! -e "$target_root/lib/modules/$NEW_RELEASE" && ! -e "$target_payload/MODULES-INSTALLED" ]] ||
  fail 'unknown-entry rejection happened after a module write'
rm -- "$target_payload/.UNTRUSTED-ENTRY"
printf '%s\n' 'rw,noatime,uid=1002,gid=1002,fmask=0000,dmask=0000' > \
  "$target_root/test-state/roms-mount-options"
printf '%s\n' rw > "$target_root/test-state/tools-mount-state"

printf 'TEST: reject an externally supplied receipt with the wrong bootstrap hash\n'
forged_receipt=${trusted_parent}/FORGED-TARGET-TRUST-RECEIPT
sed 's/^bootstrap_target_sha256=.*/bootstrap_target_sha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/' \
  "$trusted_receipt" > "$forged_receipt"
chmod 0600 "$forged_receipt"
forged_receipt_hash=$(sha256sum "$forged_receipt" | awk '{print $1}')
if run_bootstrap install-modules "$forged_receipt" "$forged_receipt_hash"; then
  fail 'bootstrap accepted a wrong externally anchored bootstrap hash'
fi
assert_public_card_restored
rm -- "$forged_receipt"

printf 'TEST: reject a wrong completion secret and an invalidated card gate\n'
forged_receipt=${trusted_parent}/FORGED-TARGET-TRUST-RECEIPT
sed 's/^completion_secret=.*/completion_secret=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/' \
  "$trusted_receipt" > "$forged_receipt"
chmod 0600 "$forged_receipt"
forged_receipt_hash=$(sha256sum "$forged_receipt" | awk '{print $1}')
if run_bootstrap install-modules "$forged_receipt" "$forged_receipt_hash"; then
  fail 'bootstrap accepted the wrong external completion secret'
fi
assert_public_card_restored
rm -- "$forged_receipt"
rm -- "$target_payload/STAGE-COMPLETE"
if run_bootstrap install-modules; then
  fail 'bootstrap accepted an invalidated STAGE-COMPLETE gate'
fi
assert_public_card_restored
cp "$generated_payload/STAGE-COMPLETE" "$target_payload/STAGE-COMPLETE"

: > "$target_root/run/r46h-deploy/deployment.lock"
chmod 0600 "$target_root/run/r46h-deploy/deployment.lock"
exec 8<> "$target_root/run/r46h-deploy/deployment.lock"
flock -n 8
if run_bootstrap install-modules; then
  fail 'installer entered while the global deployment lock was held'
fi
assert_public_card_restored
[[ ! -e "$target_root/lib/modules/$NEW_RELEASE" && ! -e "$target_payload/MODULES-INSTALLED" ]] ||
  fail 'lock rejection happened after an install write'
flock -u 8
exec 8>&-

printf 'TEST: reject a nonzero ext4 rootfs error counter before persistent writes\n'
printf '%s\n' 1 > "$target_root/test-state/rootfs-errors-count"
printf '%s\n' preflight-roms-sentinel > "$target_root/test-state/roms-mount-options"
printf '%s\n' preflight-tools-sentinel > "$target_root/test-state/tools-mount-state"
preflight_log="$target_root/test-state/rootfs-preflight.log"
if run_bootstrap install-modules > "$preflight_log" 2>&1; then
  fail 'installer accepted a damaged ext4 rootfs'
fi
grep -Fq 'rootfs ext4 errors_count is nonzero' "$preflight_log" ||
  fail 'nonzero ext4 error counter was not rejected by the pre-remount bootstrap gate'
grep -qx preflight-roms-sentinel "$target_root/test-state/roms-mount-options" ||
  fail 'bootstrap touched EASYROMS mount policy before rejecting ext4 errors_count'
grep -qx preflight-tools-sentinel "$target_root/test-state/tools-mount-state" ||
  fail 'bootstrap touched Tools mount policy before rejecting ext4 errors_count'
[[ ! -e "$target_root/lib/modules/$NEW_RELEASE" && ! -e "$target_payload/MODULES-INSTALLED" ]] ||
  fail 'rootfs health rejection happened after an install write'
printf '%s\n' 0 > "$target_root/test-state/rootfs-errors-count"
printf '%s\n' 'rw,noatime,uid=1002,gid=1002,fmask=0000,dmask=0000' > \
  "$target_root/test-state/roms-mount-options"
printf '%s\n' rw > "$target_root/test-state/tools-mount-state"

printf 'TEST: reject an ext4 corruption record in the kernel log before persistent writes\n'
printf '%s\n' \
  'EXT4-fs error (device mmcblk0p2): ext4_free_blocks: freeing already freed block' > \
  "$target_root/test-state/rootfs-kernel-log"
printf '%s\n' preflight-roms-sentinel > "$target_root/test-state/roms-mount-options"
printf '%s\n' preflight-tools-sentinel > "$target_root/test-state/tools-mount-state"
if run_bootstrap install-modules > "$preflight_log" 2>&1; then
  fail 'installer accepted an ext4 corruption record in the kernel log'
fi
grep -Fq 'kernel log reports mmcblk0p2 ext4/JBD2 damage' "$preflight_log" ||
  fail 'ext4 corruption record was not rejected by the pre-remount bootstrap gate'
grep -qx preflight-roms-sentinel "$target_root/test-state/roms-mount-options" ||
  fail 'bootstrap touched EASYROMS mount policy before rejecting the ext4 kernel log'
grep -qx preflight-tools-sentinel "$target_root/test-state/tools-mount-state" ||
  fail 'bootstrap touched Tools mount policy before rejecting the ext4 kernel log'
[[ ! -e "$target_root/lib/modules/$NEW_RELEASE" && ! -e "$target_payload/MODULES-INSTALLED" ]] ||
  fail 'rootfs kernel-log rejection happened after an install write'
: > "$target_root/test-state/rootfs-kernel-log"
rm -- "$preflight_log"
printf '%s\n' 'rw,noatime,uid=1002,gid=1002,fmask=0000,dmask=0000' > \
  "$target_root/test-state/roms-mount-options"
printf '%s\n' rw > "$target_root/test-state/tools-mount-state"

printf 'TEST: reject the other action receipt stage without broadening the exact payload set\n'
printf '%s\n' 'interrupted switch receipt' > "$target_payload/.BOOT-SWITCHED.stage"
if run_bootstrap install-modules; then
  fail 'install action accepted the switch action interrupted marker'
fi
assert_public_card_restored
[[ ! -e "$target_root/lib/modules/$NEW_RELEASE" && ! -e "$target_payload/MODULES-INSTALLED" ]] ||
  fail 'wrong-action marker rejection happened after a module write'
rm -- "$target_payload/.BOOT-SWITCHED.stage"

printf 'TEST: recover the authenticated install receipt stage after an interruption\n'
printf '%s\n' 'partial authenticated install receipt stage' > \
  "$target_payload/.MODULES-INSTALLED.stage"
run_bootstrap install-modules
assert_public_card_restored
[[ ! -e "$target_payload/.MODULES-INSTALLED.stage" ]] ||
  fail 'interrupted module receipt stage was not recovered'
[[ -d "$target_root/lib/modules/$NEW_RELEASE" ]] || fail 'new module tree is missing'
[[ -f "$target_payload/MODULES-INSTALLED" ]] || fail 'module receipt is missing'
run_bootstrap install-modules
assert_public_card_restored
rm -- "$target_payload/MODULES-INSTALLED"
run_bootstrap install-modules
assert_public_card_restored
[[ -f "$target_payload/MODULES-INSTALLED" ]] || fail 'module receipt recovery failed'
[[ -z "$(find "$target_root/lib/modules" -maxdepth 1 -name '.r46h-*-modules.*' -print -quit)" ]] ||
  fail 'module staging residue remains'

printf 'TEST: switch through fallback, preserve recovery, and rerun idempotently\n'
fallback_boot_hash=$(manifest_value "$generated_manifest" fallback_boot_sha256)
new_boot_hash=$(manifest_value "$generated_manifest" boot_candidate_sha256)
current_image=$(manifest_value "$generated_manifest" current_image_path)
current_dtb=$(manifest_value "$generated_manifest" current_dtb_path)
current_boot=$(manifest_value "$generated_manifest" current_candidate_path)
readonly fallback_boot_hash new_boot_hash current_image current_dtb current_boot
retired_stage="$target_root/roms/r46h-${CURRENT_ID}/.BOOT-RETIRED-${CURRENT_ID}.stage"
mkdir -- "$retired_stage"
printf 'interrupted copy\n' > "$retired_stage/$current_image"
printf 'status=comp' > "$retired_stage/BACKUP-COMPLETE"
printf '%s\n' 'partial authenticated switch receipt stage' > \
  "$target_payload/.BOOT-SWITCHED.stage"
if R46H_DEPLOY_TARGET_TEST_FAIL_AFTER_NEW_ACTIVE_MOVE=1 run_bootstrap switch-boot; then
  fail 'post-active-boot fault injection unexpectedly succeeded'
fi
assert_public_card_restored
hash_is "$target_root/boot/boot.ini" "$fallback_boot_hash" \
  'fallback restored after post-active-boot failure'
[[ ! -e "$target_root/boot/.boot.ini.r46h-${NEW_ID}.rollback" ]] ||
  fail 'post-active-boot rollback left a BOOT temporary file'
[[ ! -e "$target_payload/BOOT-SWITCHED" ]] ||
  fail 'failed switch published a completion receipt'
[[ ! -e "$target_payload/.BOOT-SWITCHED.stage" ]] ||
  fail 'failed switch left the recovered interrupted receipt marker'

run_bootstrap switch-boot
assert_public_card_restored
[[ ! -e "$target_payload/.BOOT-SWITCHED.stage" ]] ||
  fail 'interrupted switch receipt stage was not recovered'

hash_is "$target_root/boot/boot.ini" "$new_boot_hash" 'active new boot.ini'
hash_is "$target_root/boot/boot.ini.v0.2-known-good" "$fallback_boot_hash" 'known-good fallback'
[[ ! -e "$target_root/boot/$current_image" ]] || fail 'current Image was not retired'
[[ ! -e "$target_root/boot/$current_dtb" ]] || fail 'current DTB was not retired'
[[ ! -e "$target_root/boot/$current_boot" ]] || fail 'current boot candidate was not retired'
[[ -f "$target_root/roms/r46h-${CURRENT_ID}/BOOT-RETIRED-${CURRENT_ID}/BACKUP-COMPLETE" ]] ||
  fail 'retired BOOT backup is missing'
[[ ! -e "$retired_stage" ]] || fail 'interrupted retired staging directory was not recovered'
[[ -f "$target_payload/BOOT-SWITCHED" ]] || fail 'switch receipt is missing'
[[ -s "$target_root/test-state/boot-flush.log" ]] || fail 'BOOT flush path was not exercised'

run_bootstrap switch-boot
assert_public_card_restored
printf '%s\n' "$NEW_RELEASE" > "$target_root/test-state/running-release"
run_bootstrap switch-boot
assert_public_card_restored
hash_is "$target_root/boot/boot.ini" "$new_boot_hash" 'idempotent active new boot.ini'
hash_is "$target_root/boot/boot.ini.v0.2-known-good" "$fallback_boot_hash" \
  'idempotent known-good fallback'
[[ -d "$target_root/roms" && ! -L "$target_root/roms" ]] ||
  fail 'bootstrap did not restore EASYROMS at the stable path'
assert_public_card_restored

printf 'PASS: generated %s deployment completed fake %s -> %s stage/install/switch\n' \
  "$NEW_ID" "$CURRENT_ID" "$NEW_ID"
printf 'PASS: real TF operations: none\n'
