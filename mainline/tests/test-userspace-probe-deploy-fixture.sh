#!/usr/bin/env bash
set -Eeuo pipefail

readonly IMAGE=arkos4clone/r46h-kernel-builder:trixie-arm64

if [[ "${1:-}" != --inside ]]; then
  repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
  exec docker run --rm --entrypoint /bin/bash \
    -v "${repo}:/repo" \
    "$IMAGE" /repo/mainline/tests/test-userspace-probe-deploy-fixture.sh --inside
fi

readonly REPO=/repo
readonly MAINLINE=$REPO/mainline
readonly CACHE=$MAINLINE/out/.cache
readonly PACKAGER=$MAINLINE/scripts/package-userspace-probe-bundle.py
readonly PROBE_SOURCE=$MAINLINE/userspace-probe/run-on-target.sh
readonly PROFILE=$MAINLINE/deploy/profiles/hl-r46h-v22-g92-v1.json
readonly BASELINE=$MAINLINE/deploy/baselines/v0.8-bootloader-handoff.json
readonly STAGE_TEMPLATE=$MAINLINE/deploy/templates/stage-easyroms-macos.sh.in
readonly CURRENT_DEPLOY=$MAINLINE/out/r46h-easyroms-v0.8-bootloader-handoff/payload
# Exact historical inputs are kept as one documented, ignored test fixture.
readonly LEGACY_FIXTURE=$MAINLINE/out/test-fixtures/legacy-v08-deploy
readonly LEGACY_FIXTURE_SUMS=$MAINLINE/tests/fixtures/legacy-v08-deploy.sha256
readonly BOOT_RECEIPT=$LEGACY_FIXTURE/boot
readonly RAW_RECEIPT=$LEGACY_FIXTURE/raw
readonly PAYLOAD_NAME=r46h-debian13-mesa-probe-v0.2
readonly IMAGE_NAME=r46h-userspace-probe-debian13-mesa-v0.2.squashfs

fail() {
  printf 'TEST FAILURE: %s\n' "$*" >&2
  exit 1
}

for required in \
  "$PACKAGER" "$PROBE_SOURCE" "$PROFILE" "$BASELINE" "$STAGE_TEMPLATE" \
  "$LEGACY_FIXTURE_SUMS" \
  "$CURRENT_DEPLOY/.r46h-stage-owner" "$CURRENT_DEPLOY/DEPLOY-MANIFEST" \
  "$CURRENT_DEPLOY/STAGE-COMPLETE" \
  "$CURRENT_DEPLOY/r46h-mainline-test-v0.8-bootloader-handoff.tar.gz" \
  "$CURRENT_DEPLOY/boot.ini.v0.8-bootloader-handoff" \
  "$CURRENT_DEPLOY/Image.mainline-v0.8-bootloader-handoff.gz" \
  "$CURRENT_DEPLOY/rk3326-r46h-mainline-v0.8-bootloader-handoff.dtb" \
  "$BOOT_RECEIPT/boot.ini.test" "$BOOT_RECEIPT/Image.mainline-test.gz" \
  "$BOOT_RECEIPT/rk3326-r46h-mainline-test.dtb" \
  "$BOOT_RECEIPT/arkos4clone-uboot.dtb" \
  "$BOOT_RECEIPT/consoles/r46h/arkos4clone-uboot.dtb" \
  "$RAW_RECEIPT/prefix-before.bin" "$RAW_RECEIPT/fdisk-before.txt"; do
  [[ -f "$required" && ! -L "$required" ]] || fail "missing fixture: $required"
done

(
  cd -- "$LEGACY_FIXTURE"
  sha256sum -c "$LEGACY_FIXTURE_SUMS"
) >/dev/null || fail "legacy deployment fixture checksum mismatch"

mkdir -p "$CACHE"
bundle_root=$(mktemp -d "$CACHE/.r46h-probe-bundle-test.XXXXXX")
stage_root=$(mktemp -d "$CACHE/.r46h-stage-test.probe.XXXXXX")
target_root=$(mktemp -d "$CACHE/.r46h-probe-target-test.XXXXXX")
readonly bundle_root stage_root target_root
chmod 0700 "$bundle_root" "$stage_root" "$target_root"

cleanup_path() {
  local path=$1 prefix=$2
  [[ "$path" == "$CACHE/$prefix"* && -d "$path" && ! -L "$path" ]] || {
    printf 'WARNING: refusing unsafe fixture cleanup: %s\n' "$path" >&2
    return
  }
  rm -rf -- "$path"
}
cleanup() {
  local status=$?
  trap - EXIT INT TERM HUP
  cleanup_path "$target_root" .r46h-probe-target-test.
  cleanup_path "$stage_root" .r46h-stage-test.probe.
  cleanup_path "$bundle_root" .r46h-probe-bundle-test.
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

hash_file() { sha256sum -- "$1" | awk '{print $1}'; }
manifest_value() {
  local file=$1 key=$2 count value
  count=$(grep -c "^${key}=" "$file" 2>/dev/null || true)
  [[ "$count" -eq 1 ]] || fail "key count mismatch: $key"
  value=$(sed -n "s/^${key}=//p" "$file")
  [[ -n "$value" && "$value" != *$'\n'* ]] || fail "invalid value: $key"
  printf '%s' "$value"
}
expect_failure() {
  local marker=$1
  shift
  local output
  if output=$("$@" 2>&1); then
    fail "command unexpectedly succeeded; expected $marker"
  fi
  grep -Fq -- "$marker" <<<"$output" || {
    printf '%s\n' "$output" >&2
    fail "failure did not contain expected marker: $marker"
  }
  [[ "$output" != *'R46H_MESA_RUNTIME result=trust-pass'* ]] ||
    fail "failed trust check emitted a pass marker"
}

printf 'TEST: package the exact probe bootstrap and a small fixture image\n'
input_dir=$bundle_root/input
output_root=$bundle_root/output
mkdir -m 0700 "$input_dir" "$output_root"
printf 'fixture-squashfs-image\n' > "$input_dir/$IMAGE_NAME"
image_sha=$(hash_file "$input_dir/$IMAGE_NAME")
sed "s/@IMAGE_SHA256@/$image_sha/" "$PROBE_SOURCE" > "$input_dir/bootstrap-target.sh"
chmod 0755 "$input_dir/bootstrap-target.sh"
cat > "$input_dir/BUILD-INFO" <<'EOF'
probe_id=debian13-mesa-v0.2
architecture=arm64
kernel_contract=6.12.99-r46h-mainline-v0.8-bootloader-handoff
source_git_commit=0123456789abcdef0123456789abcdef01234567
source_git_dirty=false
source_snapshot_method=git-archive-exact-commit
source_archive_sha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
EOF
for name in LDD.txt PACKAGES.tsv PROBE-FILE.txt SQUASHFS-FILES.txt SQUASHFS-INFO.txt SOURCE-SHA256SUMS; do
  printf 'fixture=%s\n' "$name" > "$input_dir/$name"
done
python3 "$PACKAGER" \
  --input-dir "$input_dir" \
  --output-root "$output_root" \
  --card-profile "$PROFILE" \
  --current-baseline "$BASELINE" \
  --stage-template "$STAGE_TEMPLATE" \
  --source-date-epoch 1785974400

bundle=$output_root/r46h-easyroms-debian13-mesa-probe-v0.2
manifest=$bundle/payload/DEPLOY-MANIFEST
[[ -d "$bundle" && -f "$manifest" ]] || fail "probe bundle was not generated"
packaged_bootstrap=$bundle/payload/bootstrap-target.sh
# These are literal runtime snippets that the fixture searches for in the package.
# shellcheck disable=SC2016
for marker in \
  'mount --bind /dev/dri/renderD128' \
  '[[ ! -e "$R46H_PROBE_ROOT/dev/dri/card0" ]]' \
  '[[ ! -e "$R46H_PROBE_ROOT/dev/dri/card1" ]]' \
  'mount -t sysfs -o ro,nosuid,nodev,noexec sysfs "$R46H_PROBE_ROOT/sys"' \
  '[[ "$(findmnt -rn -T "$R46H_PROBE_ROOT/sys" -o FSTYPE)" == sysfs ]]' \
  'sysfs_options=$(findmnt -rn -T "$R46H_PROBE_ROOT/sys" -o OPTIONS)' \
  '[[ ",$sysfs_options," == *,ro,* ]]'; do
  grep -Fq -- "$marker" "$packaged_bootstrap" ||
    fail "packaged bootstrap is missing runtime isolation marker: $marker"
done
if grep -Fq -- 'mount --bind /dev/dri/card' "$packaged_bootstrap" ||
   grep -Fq -- 'mount --rbind /sys' "$packaged_bootstrap"; then
  fail "packaged bootstrap exposes a forbidden KMS node or writable host sysfs tree"
fi

printf 'TEST: stage the probe bundle through the p3-only directory fixture\n'
mkdir -p \
  "$stage_root/card/boot/consoles/r46h" \
  "$stage_root/card/easyroms/r46h-v0.8-bootloader-handoff" \
  "$stage_root/raw" "$stage_root/receipts"
chmod 0700 "$stage_root/receipts"
printf 'initial\n' > "$stage_root/mount-state"
printf '%s\n' "$(manifest_value "$manifest" card_profile_sha256)" > "$stage_root/card-profile.sha256"

cp "$CURRENT_DEPLOY/boot.ini.v0.8-bootloader-handoff" "$stage_root/card/boot/boot.ini"
cp "$CURRENT_DEPLOY/boot.ini.v0.8-bootloader-handoff" "$stage_root/card/boot/"
cp "$CURRENT_DEPLOY/Image.mainline-v0.8-bootloader-handoff.gz" "$stage_root/card/boot/"
cp "$CURRENT_DEPLOY/rk3326-r46h-mainline-v0.8-bootloader-handoff.dtb" "$stage_root/card/boot/"
cp "$BOOT_RECEIPT/boot.ini.test" "$stage_root/card/boot/boot.ini.test"
cp "$BOOT_RECEIPT/boot.ini.test" "$stage_root/card/boot/boot.ini.v0.2-known-good"
cp "$BOOT_RECEIPT/Image.mainline-test.gz" "$stage_root/card/boot/"
cp "$BOOT_RECEIPT/rk3326-r46h-mainline-test.dtb" "$stage_root/card/boot/"
cp "$BOOT_RECEIPT/arkos4clone-uboot.dtb" "$stage_root/card/boot/"
cp "$BOOT_RECEIPT/consoles/r46h/arkos4clone-uboot.dtb" \
  "$stage_root/card/boot/consoles/r46h/"

current_payload=$stage_root/card/easyroms/r46h-v0.8-bootloader-handoff
for name in .r46h-stage-owner DEPLOY-MANIFEST STAGE-COMPLETE \
  r46h-mainline-test-v0.8-bootloader-handoff.tar.gz; do
  cp "$CURRENT_DEPLOY/$name" "$current_payload/$name"
done
cp "$RAW_RECEIPT/prefix-before.bin" "$stage_root/raw/prefix.bin"
cp "$RAW_RECEIPT/fdisk-before.txt" "$stage_root/raw/fdisk.txt"
printf 'directory-backed-boot-partition-fixture\n' > "$stage_root/raw/p1.bin"

chmod 0755 "$stage_root/receipts"
expect_failure 'receipt parent is on the target card or cannot be proven independent' \
  env R46H_DEPLOY_STAGE_TEST_ROOT="$stage_root" \
  bash "$bundle/stage-on-macos.sh" \
    --device /dev/disk4 \
    --confirm-device /dev/disk4 \
    --receipt-parent "$stage_root/receipts"
chmod 0700 "$stage_root/receipts"

R46H_DEPLOY_STAGE_TEST_ROOT="$stage_root" \
  R46H_DEPLOY_STAGE_TEST_WITHDRAW_SOURCE_AFTER_SNAPSHOT=1 \
  bash "$bundle/stage-on-macos.sh" \
    --device /dev/disk4 \
    --confirm-device /dev/disk4 \
    --receipt-parent "$stage_root/receipts"

staged_payload=$stage_root/card/easyroms/$PAYLOAD_NAME
stage_receipt=$(find "$stage_root/receipts" -mindepth 1 -maxdepth 1 -type d -print)
[[ -d "$staged_payload" && -f "$staged_payload/STAGE-COMPLETE" ]] ||
  fail "probe payload was not staged"
[[ ! -e "$bundle/payload" && ! -e "$bundle/STAGE-SOURCES.sha256" &&
   -d "$stage_root/withdrawn-live-source/payload" ]] ||
  fail "live bundle source was not withdrawn after the private snapshot"
[[ -n "$stage_receipt" && -f "$stage_receipt/TARGET-TRUST-RECEIPT" ]] ||
  fail "post-eject target receipt is missing"
receipt_hash=$(awk '{print $1}' "$stage_receipt/TARGET-TRUST-RECEIPT.sha256")
[[ "$receipt_hash" =~ ^[0-9a-f]{64}$ ]] || fail "invalid target receipt hash"

printf 'TEST: execute valid and negative receipt/commitment trust paths\n'
mkdir -p "$target_root/roms" "$target_root/run/r46h-deploy"
chmod 0700 "$target_root/run/r46h-deploy"
cp -a "$staged_payload" "$target_root/roms/$PAYLOAD_NAME"
trusted_parent=$target_root/run/r46h-deploy
trusted_bootstrap=$trusted_parent/bootstrap-target.sh
trusted_receipt=$trusted_parent/TARGET-TRUST-RECEIPT
install -o root -g root -m 0700 "$staged_payload/bootstrap-target.sh" "$trusted_bootstrap"
install -o root -g root -m 0600 "$stage_receipt/TARGET-TRUST-RECEIPT" "$trusted_receipt"

R46H_PROBE_TARGET_TEST_ROOT="$target_root" \
  bash "$trusted_bootstrap" \
    --external-receipt "$trusted_receipt" \
    --external-receipt-sha256 "$receipt_hash" |
  grep -Fq 'R46H_MESA_RUNTIME result=trust-pass'

bad_hash=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
expect_failure external-receipt-checksum-mismatch \
  env R46H_PROBE_TARGET_TEST_ROOT="$target_root" \
  bash "$trusted_bootstrap" \
    --external-receipt "$trusted_receipt" \
    --external-receipt-sha256 "$bad_hash"

forged_receipt=$trusted_parent/FORGED-TARGET-TRUST-RECEIPT
forged_secret=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
forged_secret_sha=$(printf '%s' "$forged_secret" | sha256sum | awk '{print $1}')
sed \
  -e "s/^completion_secret=.*/completion_secret=${forged_secret}/" \
  -e "s/^completion_secret_sha256=.*/completion_secret_sha256=${forged_secret_sha}/" \
  "$trusted_receipt" > "$forged_receipt"
chmod 0600 "$forged_receipt"
forged_receipt_hash=$(hash_file "$forged_receipt")
expect_failure final-receipt-commitment-mismatch \
  env R46H_PROBE_TARGET_TEST_ROOT="$target_root" \
  bash "$trusted_bootstrap" \
    --external-receipt "$forged_receipt" \
    --external-receipt-sha256 "$forged_receipt_hash"

printf 'tampered\n' >> "$target_root/roms/$PAYLOAD_NAME/FINAL-RECEIPT-COMMITMENT"
expect_failure final-receipt-commitment-field-set-mismatch \
  env R46H_PROBE_TARGET_TEST_ROOT="$target_root" \
  bash "$trusted_bootstrap" \
    --external-receipt "$trusted_receipt" \
    --external-receipt-sha256 "$receipt_hash"

printf 'PASS: probe stager and post-eject target receipt trust fixture completed.\n'
