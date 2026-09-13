#!/usr/bin/env bash
set -Eeuo pipefail

# Directory-backed integration test. No /dev/disk path is passed through to
# the container and no host mount is modified.

readonly IMAGE=arkos4clone/r46h-kernel-builder:trixie-arm64

if [[ "${1:-}" != --inside ]]; then
  repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)
  exec docker run --rm --entrypoint /bin/bash \
    -v "${repo}:/repo" \
    "$IMAGE" /repo/mainline/tests/test-new-card-v08-seed.sh --inside
fi

readonly REPO=/repo
readonly CACHE=$REPO/mainline/out/.cache
readonly SEED=$REPO/mainline/scripts/seed-v08-baseline-on-debian13-new-card.sh
readonly RUNBOOK=$REPO/mainline/deploy/NEW-CARD-V08-SEED.md
readonly SOURCE=$REPO/mainline/out/r46h-easyroms-v0.8-bootloader-handoff
readonly SOURCE_LIST_SHA=fd5f744b75de5849702718493bc87286f41e54acd4be904d657a28858dadbcf8
readonly PREFIX_SHA=97ede10075b3257c638a04b3044c9dda2d8dd9adc6f6fee3be7b004a31fb135e
readonly PRIOR_AUDIT_STATUS_SHA=ce59319faafe2a84ee8efe7640ab0bfffa471510a41889fb3f517597964963e2
readonly PRIOR_AUDIT_STATUS='{"format_version":1,"state":"AUDIT_COMPLETE","safe_to_boot":true,"device":"/dev/disk12","card_state":"ejected","prefix_sha256":"97ede10075b3257c638a04b3044c9dda2d8dd9adc6f6fee3be7b004a31fb135e","p1_sha256":"0132f9a4748408a493983111cfe5c0f2de44574095a236fd13be539e9b39a4bc","p1_matches_write_image":false,"p2_sha256":"6a4254a8e66c110405cf068317da5922bb5ddfe2a02535d1a381fe1303876c96","p3_head_sha256":"92e70ad6a4008df0e7acf276b6602aaf1a86abaae3e1550838ed9b06b658ab6e","boot_volume_uuid":"575BC58C-96FA-3E4F-958B-7A30D5210C3D","easyroms_volume_uuid":"E1F5295C-4B12-A54A-ACB7-317194240001"}'
readonly PAYLOAD=r46h-v0.8-bootloader-handoff

fail() {
  printf 'TEST FAILURE: %s\n' "$*" >&2
  exit 1
}

[[ -x "$SEED" && -d "$SOURCE/payload" && -f "$SOURCE/STAGE-SOURCES.sha256" ]] ||
  fail 'seed script or canonical v0.8 source is missing'
[[ "$(sha256sum "$SOURCE/STAGE-SOURCES.sha256" | awk '{print $1}')" == "$SOURCE_LIST_SHA" ]] ||
  fail 'canonical source-list fixture changed'
required_production_pins=(
  'readonly WHOLE_SIZE=31719424000'
  'readonly PREFIX_SHA256=97ede10075b3257c638a04b3044c9dda2d8dd9adc6f6fee3be7b004a31fb135e'
  'readonly BOOT_OFFSET=16777216'
  'readonly BOOT_SIZE=117440512'
  'readonly BOOT_UUID=575BC58C-96FA-3E4F-958B-7A30D5210C3D'
  'readonly ROOT_OFFSET=134217728'
  'readonly ROOT_SIZE=10716877312'
  'readonly ROOT_PARTUUID=c9f931c9-02'
  'readonly EASYROMS_OFFSET=10851095040'
  'readonly EASYROMS_SIZE=20868328960'
  'readonly EASYROMS_UUID=E1F5295C-4B12-A54A-ACB7-317194240001'
  'readonly SOURCE_ENTRY_COUNT=11'
  'readonly DEFAULT_RECEIPT_PARENT=/private/tmp'
  'readonly PRIOR_AUDIT_STATUS_SHA256=ce59319faafe2a84ee8efe7640ab0bfffa471510a41889fb3f517597964963e2'
  'readonly PRIOR_AUDIT_P2_SHA256=6a4254a8e66c110405cf068317da5922bb5ddfe2a02535d1a381fe1303876c96'
)
for production_pin in "${required_production_pins[@]}"; do
  grep -Fqx "$production_pin" "$SEED" || fail "missing production identity pin: $production_pin"
done
# The dollar expression is intentionally a literal source-code guard.
# shellcheck disable=SC2016
if grep -Fq 'diskutil mount "$root_partition"' "$SEED"; then
  fail 'production seed contains a root-partition mount path'
fi
grep -Fq "'Owners:[[:space:]]+Disabled$'" "$SEED" ||
  fail 'production seed does not handle a proven macOS noowners receipt volume'
# The dollar expression is intentionally a literal source-code guard.
# shellcheck disable=SC2016
grep -Fq '"$EUID" -eq 0' "$SEED" ||
  fail 'production seed does not require root for noowners identity normalization'
# The dollar expressions are intentionally literal source-code guards.
# shellcheck disable=SC2016
grep -Fq '"$uid" == 99 && "$gid" == 99' "$SEED" ||
  fail 'production seed does not accept the macOS root _unknown identity pair'
# shellcheck disable=SC2016
grep -Fq 'volume_source=$(/bin/df -P "$path"' "$SEED" ||
  fail 'production seed does not resolve a noowners path to its volume device'
# shellcheck disable=SC2016
grep -Fq 'diskutil info "$volume_source"' "$SEED" ||
  fail 'production seed does not query noowners status through a device node'
# shellcheck disable=SC2016
if grep -Fq 'diskutil info "$path"' "$SEED"; then
  fail 'production seed passes a filesystem path directly to diskutil info'
fi
# The system sticky directory is the root-private trust boundary. External
# noowners paths remain valid only as pinned evidence inputs.
# shellcheck disable=SC2016
grep -Fq 'root_receipt_parent_identity_is_safe "$receipt_parent" "$DEFAULT_RECEIPT_PARENT"' "$SEED" ||
  fail 'production seed does not require the fixed root receipt parent'
# shellcheck disable=SC2016
grep -Fq '! -L "$receipt_parent" && -k "$receipt_parent"' "$SEED" ||
  fail 'production seed does not require a non-symlink sticky receipt parent'
# shellcheck disable=SC2016
grep -Fq '"$uid" == 0 && "$gid" == 0' "$SEED" ||
  fail 'production seed does not require root ownership of the sticky parent'
# shellcheck disable=SC2016
if grep -Fq '/bin/mkdir -p "$receipt_parent"' "$SEED" ||
   grep -Fq '/bin/chmod 700 "$receipt_parent"' "$SEED"; then
  fail 'production outer process creates or changes the root receipt parent'
fi

# Exercise the production whole-disk identity helper with the two macOS
# representations that are relevant to this workflow. Apple Silicon internal
# storage omits the Virtual line; disk images and ambiguous identities must
# remain fail-closed.
eval "$(sed -n '/^whole_disk_info_is_physical() {$/,/^}$/p' "$SEED")"
explicit_physical_info=$'   Virtual:                   No\n'
apple_fabric_info=$'   Protocol:                  Apple Fabric\n   Device Location:           Internal\n   Removable Media:           Fixed\n   Solid State:               Yes\n'
virtual_info=$'   Protocol:                  Disk Image\n   Device Location:           External\n   Removable Media:           Fixed\n   Virtual:                   Yes\n'
virtual_apple_fabric_info=$'   Protocol:                  Apple Fabric\n   Device Location:           Internal\n   Removable Media:           Fixed\n   Solid State:               Yes\n   Virtual:                   Yes\n'
external_apple_fabric_info=$'   Protocol:                  Apple Fabric\n   Device Location:           External\n   Removable Media:           Fixed\n   Solid State:               Yes\n'
removable_apple_fabric_info=$'   Protocol:                  Apple Fabric\n   Device Location:           Internal\n   Removable Media:           Removable\n   Solid State:               Yes\n'
other_protocol_info=$'   Protocol:                  PCI-Express\n   Device Location:           Internal\n   Removable Media:           Fixed\n   Solid State:               Yes\n'
ambiguous_internal_info=$'   Protocol:                  Apple Fabric\n   Device Location:           Internal\n   Removable Media:           Fixed\n'
whole_disk_info_is_physical "$explicit_physical_info" ||
  fail 'production helper rejected an explicit physical whole disk'
whole_disk_info_is_physical "$apple_fabric_info" ||
  fail 'production helper rejected an Apple Silicon internal physical store'
if whole_disk_info_is_physical "$virtual_info"; then
  fail 'production helper accepted a virtual disk image'
fi
if whole_disk_info_is_physical "$virtual_apple_fabric_info"; then
  fail 'production helper accepted an explicitly virtual Apple Fabric disk'
fi
if whole_disk_info_is_physical "$external_apple_fabric_info"; then
  fail 'production helper accepted an external Apple Fabric identity'
fi
if whole_disk_info_is_physical "$removable_apple_fabric_info"; then
  fail 'production helper accepted a removable Apple Fabric identity'
fi
if whole_disk_info_is_physical "$other_protocol_info"; then
  fail 'production helper accepted an unknown internal storage protocol'
fi
if whole_disk_info_is_physical "$ambiguous_internal_info"; then
  fail 'production helper accepted an incomplete Apple Fabric identity'
fi
# shellcheck disable=SC2016
grep -Fq '/usr/bin/sudo -n -u "#$expected_uid" -- /bin/cat -- "$source"' "$SEED" ||
  fail 'production root worker does not use a dropped-uid source reader'
if grep -Fq 'chown -R' "$SEED" || grep -Fq 'change_owner -R' "$SEED"; then
  fail 'production seed recursively hands off a live root receipt tree'
fi
# shellcheck disable=SC2016
grep -Fq 'change_owner "$expected_uid:$expected_gid" "$receipt_dir"' "$SEED" ||
  fail 'production seed does not hand off the receipt directory last'
# shellcheck disable=SC2016
grep -Fq '`/private/tmp`' "$RUNBOOK" ||
  fail 'seed runbook does not document the system sticky receipt parent'
grep -Fq 'cannot prove a root-only trust' "$RUNBOOK" ||
  fail 'seed runbook does not explain the noowners trust-boundary constraint'

mkdir -p "$CACHE"
test_parent=$(mktemp -d "$CACHE/.r46h-v08-seed-test.XXXXXX")
readonly test_parent
chmod 0700 "$test_parent"

cleanup() {
  local status=$?
  trap - EXIT INT TERM HUP
  [[ "$test_parent" == "$CACHE/.r46h-v08-seed-test."* &&
     -d "$test_parent" && ! -L "$test_parent" ]] ||
    fail "refusing unsafe fixture cleanup: $test_parent"
  rm -rf -- "$test_parent"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

prepare_fixture() {
  local root=$1
  mkdir -p \
    "$root/card/easyroms/.Spotlight-V100" \
    "$root/raw" \
    "$root/receipts"
  chmod 0700 "$root"
  chmod 1777 "$root/receipts"
  mkdir -m 0700 "$root/prior-audit"
  printf '%s\n' "$PRIOR_AUDIT_STATUS" > "$root/prior-audit/AUDIT-STATUS.json"
  printf 'status_sha256=%s\n' "$PRIOR_AUDIT_STATUS_SHA" > "$root/prior-audit/AUDIT-COMPLETE"
  chmod 0600 "$root/prior-audit/AUDIT-STATUS.json" "$root/prior-audit/AUDIT-COMPLETE"
  [[ "$(sha256sum "$root/prior-audit/AUDIT-STATUS.json" | awk '{print $1}')" == "$PRIOR_AUDIT_STATUS_SHA" ]] ||
    fail 'prior audit fixture does not match the pinned status SHA-256'
  printf '%s\n' \
    "whole=31719424000;prefix=$PREFIX_SHA;boot=575BC58C-96FA-3E4F-958B-7A30D5210C3D;root=c9f931c9-02;roms=E1F5295C-4B12-A54A-ACB7-317194240001" \
    > "$root/card-identity"
  printf 'initial\n' > "$root/mount-state"
  printf 'fixture-prefix\n' > "$root/raw/prefix.bin"
  printf 'fixture-fdisk\n' > "$root/raw/fdisk.txt"
  printf 'fixture-p1\n' > "$root/raw/p1.bin"
  printf 'fixture-p2-first\n' > "$root/raw/p2-first.bin"
  printf 'fixture-p2-last\n' > "$root/raw/p2-last.bin"
}

run_seed() {
  local root=$1
  shift
  R46H_V08_SEED_TEST_ROOT="$root" "$@" \
    bash "$SEED" \
      --device /dev/disk12 \
      --confirm-device /dev/disk12 \
      --prior-audit-dir "$root/prior-audit" \
      --prior-audit-status-sha256 "$PRIOR_AUDIT_STATUS_SHA" \
      --receipt-parent "$root/receipts"
}

printf 'TEST: exact canonical 11-file seed, AppleDouble cleanup, and safe eject\n'
success_root="$test_parent/success"
mkdir -m 0700 "$success_root"
prepare_fixture "$success_root"
run_seed "$success_root" env

success_payload="$success_root/card/easyroms/$PAYLOAD"
[[ -d "$success_payload" && ! -L "$success_payload" ]] || fail 'seeded payload is missing'
count=$(find "$success_payload" -mindepth 1 -maxdepth 1 -type f | wc -l | tr -d '[:space:]')
[[ "$count" == 11 ]] || fail 'seeded payload is not the exact canonical 11-file set'
while read -r expected relative extra; do
  [[ -z "${extra:-}" ]] || fail 'malformed canonical source list during verification'
  name=${relative#payload/}
  [[ -f "$success_payload/$name" && ! -L "$success_payload/$name" ]] ||
    fail "missing seeded file: $name"
  [[ "$(sha256sum "$success_payload/$name" | awk '{print $1}')" == "$expected" ]] ||
    fail "seeded hash mismatch: $name"
done < "$SOURCE/STAGE-SOURCES.sha256"
[[ -z "$(find "$success_root/card/easyroms" -name '._*' -print -quit)" ]] ||
  fail 'AppleDouble residue remains after the successful seed'
[[ ! -e "$success_payload/STAGE-SOURCES.sha256" &&
   ! -e "$success_payload/FINAL-RECEIPT-COMMITMENT" ]] ||
  fail 'seed added non-canonical authorization files to the target payload'
[[ "$(tr -d '\r\n' < "$success_root/mount-state")" == ejected ]] ||
  fail 'successful fixture was not safely ejected'

receipt_count=$(find "$success_root/receipts" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d '[:space:]')
[[ "$receipt_count" == 1 ]] || fail 'successful seed did not publish exactly one receipt'
success_receipt=$(find "$success_root/receipts" -mindepth 1 -maxdepth 1 -type d -print)
[[ -f "$success_receipt/COMPLETE" && -f "$success_receipt/EJECTED" ]] ||
  fail 'successful seed receipt is incomplete'
[[ ! -e "$success_receipt/.work" ]] ||
  fail 'successful seed receipt retained the private source snapshot'
[[ "$(stat -c '%u:%g:%a' "$success_receipt")" == 12345:12345:700 ]] ||
  fail 'fixture receipt does not model invoking-user 0700 ownership'
[[ -z "$(find "$success_receipt" -mindepth 1 ! -user 12345 -print -quit)" ]] ||
  fail 'fixture receipt files were not handed off before the top-level directory'
grep -qx 'only_written_partition=3' "$success_receipt/SEED-RESULT" ||
  fail 'receipt does not constrain writes to p3'
grep -qx 'boot_partition=unchanged-full-raw-sha256' "$success_receipt/SEED-RESULT" ||
  fail 'receipt does not prove BOOT preservation'
grep -qx 'root_partition=never-mounted-boundary-samples-unchanged' "$success_receipt/SEED-RESULT" ||
  fail 'receipt does not record the bounded root preservation proof'
grep -qx 'full_p2_hash_verified_during_seed=no' "$success_receipt/SEED-RESULT" ||
  fail 'receipt does not disclose that seed skipped a full p2 hash'
grep -qx "prior_full_p2_audit_status_sha256=$PRIOR_AUDIT_STATUS_SHA" "$success_receipt/SEED-RESULT" ||
  fail 'receipt does not bind the prior full-p2 audit status'
grep -qx 'prior_full_p2_audit_p2_sha256=6a4254a8e66c110405cf068317da5922bb5ddfe2a02535d1a381fe1303876c96' \
  "$success_receipt/SEED-RESULT" || fail 'receipt does not bind the prior full p2 hash'
cmp -s "$success_root/prior-audit/AUDIT-STATUS.json" "$success_receipt/PRIOR-AUDIT-STATUS.json" ||
  fail 'receipt did not preserve the pinned prior audit status'
grep -qx 'seeded_target_scripts_must_not_be_executed=yes' "$success_receipt/SEED-RESULT" ||
  fail 'receipt omits the no-execution boundary'
[[ -z "$(find "$success_receipt" -name 'TARGET-TRUST-RECEIPT*' -print -quit)" ]] ||
  fail 'seed receipt improperly created a target execution authorization'
if grep -REn '^completion_secret=' "$success_receipt"; then
  fail 'seed receipt leaked or generated a completion secret'
fi

printf 'TEST: reject a nonblank p3 before creating the payload\n'
nonblank_root="$test_parent/nonblank"
mkdir -m 0700 "$nonblank_root"
prepare_fixture "$nonblank_root"
printf 'unrelated-data\n' > "$nonblank_root/card/easyroms/unexpected.bin"
if run_seed "$nonblank_root" env; then
  fail 'seed accepted a nonblank EASYROMS partition'
fi
[[ ! -e "$nonblank_root/card/easyroms/$PAYLOAD" ]] ||
  fail 'nonblank-card rejection happened after payload creation'
[[ -z "$(find "$nonblank_root/receipts" -name COMPLETE -print -quit)" ]] ||
  fail 'nonblank-card failure published a complete receipt'
[[ -z "$(find "$nonblank_root/receipts" -name .work -print -quit)" ]] ||
  fail 'nonblank-card failure retained a private source snapshot'

printf 'TEST: invalidate STAGE-COMPLETE after an injected post-gate failure\n'
failure_root="$test_parent/post-gate-failure"
mkdir -m 0700 "$failure_root"
prepare_fixture "$failure_root"
if run_seed "$failure_root" env R46H_V08_SEED_TEST_FAIL_AFTER_GATE=1; then
  fail 'post-gate fault injection unexpectedly succeeded'
fi
failure_payload="$failure_root/card/easyroms/$PAYLOAD"
[[ -d "$failure_payload" && ! -e "$failure_payload/STAGE-COMPLETE" ]] ||
  fail 'failed seed left STAGE-COMPLETE consumable'
[[ -z "$(find "$failure_root/receipts" -name COMPLETE -print -quit)" ]] ||
  fail 'failed seed published a complete receipt'
[[ -z "$(find "$failure_root/receipts" -name 'TARGET-TRUST-RECEIPT*' -print -quit)" ]] ||
  fail 'failed seed created a target execution authorization'
[[ -z "$(find "$failure_root/receipts" -name .work -print -quit)" ]] ||
  fail 'post-gate failure retained a private source snapshot'

printf 'TEST: reject a tampered canonical source before touching the card fixture\n'
tamper_root="$test_parent/tampered-source-card"
tamper_source="$test_parent/tampered-source"
mkdir -m 0700 "$tamper_root"
prepare_fixture "$tamper_root"
cp -a "$SOURCE" "$tamper_source"
printf 'tamper\n' >> "$tamper_source/payload/DEPLOY-MANIFEST"
if R46H_V08_SEED_TEST_SOURCE_BUNDLE="$tamper_source" run_seed "$tamper_root" env; then
  fail 'seed accepted a tampered canonical source'
fi
[[ "$(tr -d '\r\n' < "$tamper_root/mount-state")" == initial ]] ||
  fail 'source rejection happened after a fixture mount transition'
[[ ! -e "$tamper_root/card/easyroms/$PAYLOAD" ]] ||
  fail 'source rejection happened after a card write'

printf 'TEST: reject a tampered prior full-p2 audit before touching the card fixture\n'
audit_tamper_root="$test_parent/tampered-prior-audit-card"
mkdir -m 0700 "$audit_tamper_root"
prepare_fixture "$audit_tamper_root"
printf 'tamper\n' >> "$audit_tamper_root/prior-audit/AUDIT-STATUS.json"
if run_seed "$audit_tamper_root" env; then
  fail 'seed accepted a tampered prior full-p2 audit status'
fi
[[ "$(tr -d '\r\n' < "$audit_tamper_root/mount-state")" == initial ]] ||
  fail 'prior-audit rejection happened after a fixture mount transition'
[[ ! -e "$audit_tamper_root/card/easyroms/$PAYLOAD" ]] ||
  fail 'prior-audit rejection happened after a card write'

printf 'TEST: pre-card cleanup never touches mount state after a frozen-audit failure\n'
audit_freeze_root="$test_parent/frozen-audit-failure-card"
mkdir -m 0700 "$audit_freeze_root"
prepare_fixture "$audit_freeze_root"
if run_seed "$audit_freeze_root" env R46H_V08_SEED_TEST_FAIL_AFTER_AUDIT_FREEZE=1; then
  fail 'post-freeze prior-audit fault injection unexpectedly succeeded'
fi
[[ "$(tr -d '\r\n' < "$audit_freeze_root/mount-state")" == initial ]] ||
  fail 'pre-card cleanup touched mount state after a frozen-audit failure'
[[ ! -e "$audit_freeze_root/card/easyroms/$PAYLOAD" ]] ||
  fail 'post-freeze prior-audit failure happened after a card write'
[[ -z "$(find "$audit_freeze_root/receipts" -name .work -print -quit)" ]] ||
  fail 'post-freeze failure retained a private source snapshot'

printf 'TEST: refuse receipt handoff when private snapshot removal is unproven\n'
work_removal_root="$test_parent/work-removal-failure-card"
mkdir -m 0700 "$work_removal_root"
prepare_fixture "$work_removal_root"
set +e
run_seed "$work_removal_root" env \
  R46H_V08_SEED_TEST_FAIL_AFTER_AUDIT_FREEZE=1 \
  R46H_V08_SEED_TEST_FAIL_WORK_REMOVAL=1
work_removal_status=$?
set -e
[[ "$work_removal_status" -eq 74 ]] ||
  fail "unremoved private snapshot returned $work_removal_status instead of 74"
work_removal_receipt=$(find "$work_removal_root/receipts" -mindepth 1 -maxdepth 1 -type d -print)
[[ -n "$work_removal_receipt" && -d "$work_removal_receipt/.work" ]] ||
  fail 'work-removal fault injection did not preserve the private snapshot'
[[ "$(stat -c '%u:%g:%a' "$work_removal_receipt")" == 0:0:700 ]] ||
  fail 'receipt with an unremoved private snapshot was handed to the invoking user'
[[ "$(tr -d '\r\n' < "$work_removal_root/mount-state")" == initial ]] ||
  fail 'work-removal failure touched mount state'

printf 'TEST: keep a completed receipt root-owned when final handoff fails\n'
handoff_root="$test_parent/receipt-handoff-failure-card"
mkdir -m 0700 "$handoff_root"
prepare_fixture "$handoff_root"
set +e
run_seed "$handoff_root" env R46H_V08_SEED_TEST_FAIL_RECEIPT_HANDOFF=1
handoff_status=$?
set -e
[[ "$handoff_status" -eq 74 ]] ||
  fail "failed receipt handoff returned $handoff_status instead of 74"
handoff_receipt=$(find "$handoff_root/receipts" -mindepth 1 -maxdepth 1 -type d -print)
[[ -n "$handoff_receipt" && -f "$handoff_receipt/COMPLETE" && ! -e "$handoff_receipt/.work" ]] ||
  fail 'handoff failure did not retain a complete receipt without private work data'
[[ "$(stat -c '%u:%g:%a' "$handoff_receipt")" == 0:0:700 ]] ||
  fail 'failed handoff exposed the completed receipt to the invoking user'
[[ "$(tr -d '\r\n' < "$handoff_root/mount-state")" == ejected ]] ||
  fail 'receipt handoff failure changed the already-ejected card state'

printf 'TEST: reject non-root and non-sticky privileged receipt parents before card access\n'
unsafe_parent_root="$test_parent/unsafe-receipt-parent-card"
mkdir -m 0700 "$unsafe_parent_root"
prepare_fixture "$unsafe_parent_root"
chmod 0777 "$unsafe_parent_root/receipts"
if run_seed "$unsafe_parent_root" env; then
  fail 'seed accepted a non-sticky privileged receipt parent'
fi
[[ "$(tr -d '\r\n' < "$unsafe_parent_root/mount-state")" == initial ]] ||
  fail 'non-sticky receipt-parent rejection touched mount state'
chmod 1777 "$unsafe_parent_root/receipts"
chown 99:99 "$unsafe_parent_root/receipts"
if run_seed "$unsafe_parent_root" env; then
  fail 'seed accepted a non-root privileged receipt parent'
fi
[[ "$(tr -d '\r\n' < "$unsafe_parent_root/mount-state")" == initial ]] ||
  fail 'non-root receipt-parent rejection touched mount state'

printf 'PASS: new-card v0.8 baseline seed fixture completed without a physical disk.\n'
