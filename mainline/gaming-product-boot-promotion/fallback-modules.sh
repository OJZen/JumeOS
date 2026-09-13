#!/bin/bash

# Sourced by install.sh after the root-owned payload has been verified.

readonly R46H_V10_RELEASE=6.12.99-r46h-mainline-v0.10-adc-full-range
readonly R46H_V10_PACKAGE_NAME=r46h-mainline-test-v0.10-adc-full-range
readonly R46H_V10_BUNDLE_NAME=r46h-mainline-test-v0.10-adc-full-range.tar.gz
readonly R46H_V10_BUNDLE_SIZE=33258814
readonly R46H_V10_BUNDLE_SHA256=c4350520f7ad33ecf7b50f67c42985e2ce26c1c38d050ad50601c3538cebc780
readonly R46H_V10_MODULE_TREE_SHA256=a70796c050de93c4c212180addf54a17efe7732d355db2b52d0bfcab6c56cc16
readonly R46H_V10_MODULE_COUNT=1276
readonly R46H_V10_MODULE_FILE_COUNT=1290
readonly R46H_V10_MODULE_DIR_COUNT=395
readonly R46H_V10_EXTRACTION_BYTES=113447508
readonly R46H_V10_EXTRACTION_INODES=1695
readonly R46H_V10_STAGE_NAME=.v10-fallback-modules.stage
readonly R46H_V10_RECEIPT_NAME=V10-FALLBACK-MODULES
readonly R46H_V10_RECEIPT_STAGE_NAME=.V10-FALLBACK-MODULES.stage
readonly R46H_V08_RELEASE=6.12.99-r46h-mainline-v0.8-bootloader-handoff
readonly R46H_V08_MODULE_TREE_SHA256=2ec532a3d3c6833538bd4ffd284122afa30bea0945e832f57be481527986f210
readonly R46H_V15_RELEASE=6.12.99-r46h-mainline-v0.15-gaming-product
readonly R46H_V15_MODULE_TREE_SHA256=bd53fad3997ced39a15c69dbd70525106e891e5529dcef73bbbcfb699aafc291

r46h_mod_fail() {
  printf 'ERROR: %s\n' "$*" >&2
  return 1
}

r46h_mod_hash_file() {
  sha256sum "$1" | awk '{print $1}'
}

r46h_mod_check_bundle() {
  local bundle=$1
  [[ -f "$bundle" && ! -L "$bundle" ]] || r46h_mod_fail 'unsafe or missing v0.10 module bundle' || return
  [[ "$(stat -c '%h' "$bundle")" == 1 ]] || r46h_mod_fail 'unexpected v0.10 module bundle link count' || return
  [[ "$(stat -c '%s' "$bundle")" == "$R46H_V10_BUNDLE_SIZE" ]] || \
    r46h_mod_fail 'v0.10 module bundle size mismatch' || return
  [[ "$(r46h_mod_hash_file "$bundle")" == "$R46H_V10_BUNDLE_SHA256" ]] || \
    r46h_mod_fail 'v0.10 module bundle SHA-256 mismatch' || return
}

r46h_mod_tree_hash() {
  local tree=$1 release=$2 relative digest
  (
    cd "$tree" || exit 1
    find . -xdev -type f -print | LC_ALL=C sort |
      while IFS= read -r relative; do
        digest=$(sha256sum "$relative" | awk '{print $1}') || exit 1
        printf '%s  rootfs/lib/modules/%s/%s\n' \
          "$digest" "$release" "${relative#./}"
      done
  ) | sha256sum | awk '{print $1}'
}

r46h_mod_verify_exact_tree() {
  local modules_parent=$1 release=$2 expected_hash=$3 expected_modules=$4
  local expected_files=$5 expected_dirs=$6 label=$7
  local tree file_count module_count dir_count observed_hash
  tree=$modules_parent/$release
  [[ -d "$tree" && ! -L "$tree" ]] || r46h_mod_fail "unsafe or missing ${label} module tree" || return
  [[ -z "$(find "$tree" -xdev -type l -print -quit)" ]] || r46h_mod_fail "${label} module tree contains a symbolic link" || return
  [[ -z "$(find "$tree" -xdev ! -type d ! -type f -print -quit)" ]] || r46h_mod_fail "${label} module tree contains a special file" || return
  [[ -z "$(find "$tree" -xdev -type f ! -links 1 -print -quit)" ]] || r46h_mod_fail "${label} module tree contains a hard-linked file" || return
  [[ -z "$(find "$tree" -xdev ! -uid 0 -print -quit)" && \
     -z "$(find "$tree" -xdev ! -gid 0 -print -quit)" ]] || \
    r46h_mod_fail "${label} module tree ownership mismatch" || return
  [[ -z "$(find "$tree" -xdev -type d ! -perm 0755 -print -quit)" ]] || \
    r46h_mod_fail "${label} module directory mode mismatch" || return
  [[ -z "$(find "$tree" -xdev -type f ! -perm 0644 -print -quit)" ]] || \
    r46h_mod_fail "${label} module file mode mismatch" || return
  file_count=$(find "$tree" -xdev -type f -print | wc -l | tr -d '[:space:]')
  module_count=$(find "$tree" -xdev -type f -name '*.ko' -print | wc -l | tr -d '[:space:]')
  dir_count=$(find "$tree" -xdev -type d -print | wc -l | tr -d '[:space:]')
  [[ "$file_count" == "$expected_files" && \
     "$module_count" == "$expected_modules" && \
     "$dir_count" == "$expected_dirs" ]] || \
    r46h_mod_fail "${label} module tree count mismatch" || return
  observed_hash=$(r46h_mod_tree_hash "$tree" "$release") || \
    r46h_mod_fail "cannot hash ${label} module tree" || return
  [[ "$observed_hash" == "$expected_hash" ]] || \
    r46h_mod_fail "${label} module tree SHA-256 mismatch" || return
}

r46h_mod_verify_tree() {
  r46h_mod_verify_exact_tree "$1" "$R46H_V10_RELEASE" \
    "$R46H_V10_MODULE_TREE_SHA256" "$R46H_V10_MODULE_COUNT" \
    "$R46H_V10_MODULE_FILE_COUNT" "$R46H_V10_MODULE_DIR_COUNT" "$2 v0.10"
}

r46h_mod_verify_existing_fallbacks() {
  local modules_parent=$1
  r46h_mod_verify_exact_tree "$modules_parent" "$R46H_V08_RELEASE" \
    "$R46H_V08_MODULE_TREE_SHA256" 1276 1290 395 'installed v0.8 fallback' || return
  r46h_mod_verify_exact_tree "$modules_parent" "$R46H_V15_RELEASE" \
    "$R46H_V15_MODULE_TREE_SHA256" 1276 1290 395 'installed v0.15 target' || return
}

r46h_mod_receipt_bytes() {
  printf '%s\n' \
    'format_version=1' \
    'status=complete' \
    "installed_release=$R46H_V10_RELEASE" \
    "payload_bundle_sha256=$R46H_V10_BUNDLE_SHA256" \
    "module_tree_sha256=$R46H_V10_MODULE_TREE_SHA256" \
    "module_count=$R46H_V10_MODULE_COUNT" \
    "module_tree_file_count=$R46H_V10_MODULE_FILE_COUNT"
}

r46h_mod_verify_receipt() {
  local state_dir=$1 receipt
  receipt=$state_dir/$R46H_V10_RECEIPT_NAME
  [[ -f "$receipt" && ! -L "$receipt" ]] || r46h_mod_fail 'unsafe or missing v0.10 module receipt' || return
  [[ "$(stat -c '%u:%g:%a:%h' "$receipt")" == 0:0:600:1 ]] || \
    r46h_mod_fail 'v0.10 module receipt identity mismatch' || return
  cmp -s "$receipt" <(r46h_mod_receipt_bytes) || r46h_mod_fail 'v0.10 module receipt content mismatch' || return
}

r46h_mod_stage_path() {
  printf '%s/%s' "$1" "$R46H_V10_STAGE_NAME"
}

r46h_mod_verify_stage_identity() {
  local stage=$1
  [[ -d "$stage" && ! -L "$stage" ]] || r46h_mod_fail 'v0.10 module stage is unsafe' || return
  [[ "$(stat -c '%u:%g:%a' "$stage")" == 0:0:700 ]] || \
    r46h_mod_fail 'v0.10 module stage identity mismatch' || return
}

r46h_mod_clear_stage() {
  local state_dir=$1 stage target
  stage=$(r46h_mod_stage_path "$state_dir")
  [[ -e "$stage" || -L "$stage" ]] || return 0
  r46h_mod_verify_stage_identity "$stage" || return
  while IFS= read -r target; do
    [[ "$target" != "$stage" && "$target" != "$stage/"* ]] || \
      r46h_mod_fail 'v0.10 module stage contains a nested mount' || return
  done < <(findmnt -rn -o TARGET)
  rm -rf -- "$stage" || r46h_mod_fail 'cannot clear v0.10 module stage' || return
  sync || r46h_mod_fail 'cannot sync v0.10 module stage cleanup' || return
}

r46h_mod_publish_receipt() {
  local state_dir=$1 receipt stage
  receipt=$state_dir/$R46H_V10_RECEIPT_NAME
  stage=$state_dir/$R46H_V10_RECEIPT_STAGE_NAME
  if [[ -e "$stage" || -L "$stage" ]]; then
    [[ -f "$stage" && ! -L "$stage" && \
       "$(stat -c '%u:%g:%a:%h' "$stage")" == 0:0:600:1 && \
       "$(stat -c '%s' "$stage")" -le 4096 ]] || \
      r46h_mod_fail 'interrupted v0.10 module receipt stage is unsafe' || return
    rm -f -- "$stage" || r46h_mod_fail 'cannot clear interrupted v0.10 module receipt stage' || return
    sync || r46h_mod_fail 'cannot sync v0.10 module receipt recovery' || return
  fi
  if [[ -e "$receipt" || -L "$receipt" ]]; then
    r46h_mod_verify_receipt "$state_dir" || return
    return 0
  fi
  (set -o noclobber; r46h_mod_receipt_bytes > "$stage") || \
    r46h_mod_fail 'cannot stage v0.10 module receipt' || return
  chmod 0600 "$stage" || r46h_mod_fail 'cannot protect v0.10 module receipt stage' || return
  sync || r46h_mod_fail 'cannot sync v0.10 module receipt stage' || return
  mv -T -- "$stage" "$receipt" || r46h_mod_fail 'cannot publish v0.10 module receipt' || return
  sync || r46h_mod_fail 'cannot sync v0.10 module receipt' || return
  r46h_mod_verify_receipt "$state_dir" || return
}

r46h_mod_detect_state() {
  local modules_parent=$1 state_dir=$2 tree receipt receipt_stage stage final=0 receipted=0 staged=0
  [[ -d "$modules_parent" && ! -L "$modules_parent" && \
     "$(stat -c '%u:%g:%a' "$modules_parent")" == 0:0:755 ]] || \
    r46h_mod_fail 'module parent identity mismatch' || return
  if [[ -e "$state_dir" || -L "$state_dir" ]]; then
    [[ -d "$state_dir" && ! -L "$state_dir" && \
       "$(stat -c '%u:%g:%a' "$state_dir")" == 0:0:700 ]] || \
      r46h_mod_fail 'promotion state directory is unsafe for module inspection' || return
  fi
  tree=$modules_parent/$R46H_V10_RELEASE
  receipt=$state_dir/$R46H_V10_RECEIPT_NAME
  receipt_stage=$state_dir/$R46H_V10_RECEIPT_STAGE_NAME
  stage=$(r46h_mod_stage_path "$state_dir")
  [[ -e "$tree" || -L "$tree" ]] && final=1
  [[ -e "$receipt" || -L "$receipt" ]] && receipted=1
  [[ -e "$stage" || -L "$stage" ]] && staged=1
  if [[ -e "$receipt_stage" || -L "$receipt_stage" ]]; then
    [[ -f "$receipt_stage" && ! -L "$receipt_stage" && \
       "$(stat -c '%u:%g:%a:%h' "$receipt_stage")" == 0:0:600:1 && \
       "$(stat -c '%s' "$receipt_stage")" -le 4096 ]] || \
      r46h_mod_fail 'interrupted v0.10 module receipt stage is unsafe' || return
  fi
  (( staged == 0 )) || r46h_mod_verify_stage_identity "$stage" || return
  if (( final == 1 )); then
    r46h_mod_verify_tree "$modules_parent" installed || return
  fi
  if (( receipted == 1 )); then
    r46h_mod_verify_receipt "$state_dir" || return
  fi
  (( receipted == 0 || final == 1 )) || r46h_mod_fail 'v0.10 module receipt exists without its tree' || return
  case "$final:$receipted:$staged" in
    0:0:0) printf 'absent\n' ;;
    0:0:1) printf 'stage-partial\n' ;;
    1:0:0) printf 'published-unreceipted\n' ;;
    1:0:1) printf 'published-unreceipted-with-stage\n' ;;
    1:1:0) printf 'complete\n' ;;
    1:1:1) printf 'complete-with-stage\n' ;;
    *) r46h_mod_fail 'unsupported v0.10 module transaction state' || return ;;
  esac
}

r46h_mod_check_capacity() {
  local modules_parent=$1 available_kib available_inodes required_kib required_inodes
  available_kib=$(df -Pk "$modules_parent" | awk 'END {print $4}')
  available_inodes=$(df -Pi "$modules_parent" | awk 'END {print $4}')
  [[ "$available_kib" =~ ^[0-9]+$ && "$available_inodes" =~ ^[0-9]+$ ]] || \
    r46h_mod_fail 'cannot read rootfs capacity for v0.10 modules' || return
  required_kib=$(( (R46H_V10_EXTRACTION_BYTES + 1023) / 1024 + 65536 ))
  required_inodes=$(( R46H_V10_EXTRACTION_INODES + 256 ))
  (( available_kib >= required_kib )) || r46h_mod_fail 'rootfs free space is below the v0.10 extraction projection plus 64 MiB' || return
  (( available_inodes >= required_inodes )) || r46h_mod_fail 'rootfs free inodes are below the v0.10 extraction projection plus 256' || return
}

r46h_mod_validate_archive_paths() {
  local bundle=$1 entry
  while IFS= read -r entry; do
    [[ -n "$entry" && "$entry" != /* && "$entry" != *$'\n'* && \
       "$entry" != *'/../'* && "$entry" != ../* ]] || \
      r46h_mod_fail 'unsafe v0.10 module archive path' || return
  done < <(tar -tzf "$bundle")
  tar -tvzf "$bundle" | awk \
    'substr($1,1,1)!="-" && substr($1,1,1)!="d" {bad=1} END{exit bad?1:0}' || \
    r46h_mod_fail 'v0.10 module archive contains a link or special file' || return
}

r46h_mod_ensure() {
  local modules_parent=$1 state_dir=$2 bundle=$3 state stage package_dir staged_modules
  [[ -d "$modules_parent" && ! -L "$modules_parent" && \
     "$(stat -c '%u:%g:%a' "$modules_parent")" == 0:0:755 ]] || \
    r46h_mod_fail 'module parent identity mismatch' || return
  [[ -d "$state_dir" && ! -L "$state_dir" && \
     "$(stat -c '%u:%g:%a' "$state_dir")" == 0:0:700 ]] || \
    r46h_mod_fail 'promotion state directory is unsafe for module transaction' || return
  r46h_mod_check_bundle "$bundle" || return
  state=$(r46h_mod_detect_state "$modules_parent" "$state_dir") || return
  case "$state" in
    complete)
      r46h_mod_publish_receipt "$state_dir" || return
      return 0
      ;;
    complete-with-stage)
      r46h_mod_clear_stage "$state_dir" || return
      return 0
      ;;
    published-unreceipted|published-unreceipted-with-stage)
      r46h_mod_clear_stage "$state_dir" || return
      r46h_mod_publish_receipt "$state_dir" || return
      return 0
      ;;
    absent) ;;
    stage-partial)
      r46h_mod_clear_stage "$state_dir" || return
      ;;
    *) r46h_mod_fail 'cannot recover the v0.10 module transaction state' || return ;;
  esac
  r46h_mod_check_capacity "$modules_parent" || return
  r46h_mod_validate_archive_paths "$bundle" || return
  stage=$(r46h_mod_stage_path "$state_dir")
  install -d -o root -g root -m 0700 "$stage" || r46h_mod_fail 'cannot create v0.10 module stage' || return
  tar --no-same-owner -xzf "$bundle" -C "$stage" || r46h_mod_fail 'cannot extract v0.10 module bundle' || return
  package_dir=$stage/$R46H_V10_PACKAGE_NAME
  staged_modules=$package_dir/rootfs/lib/modules/$R46H_V10_RELEASE
  [[ -d "$package_dir" && ! -L "$package_dir" ]] || r46h_mod_fail 'v0.10 package root is unsafe' || return
  [[ -d "$staged_modules" && ! -L "$staged_modules" ]] || r46h_mod_fail 'v0.10 staged module tree is missing' || return
  (cd "$package_dir" && sha256sum -c SHA256SUMS >/dev/null) || \
    r46h_mod_fail 'v0.10 package SHA256SUMS verification failed' || return
  r46h_mod_verify_tree "$package_dir/rootfs/lib/modules" staged || return
  [[ ! -e "$modules_parent/$R46H_V10_RELEASE" && ! -L "$modules_parent/$R46H_V10_RELEASE" ]] || \
    r46h_mod_fail 'v0.10 module tree appeared concurrently' || return
  sync || r46h_mod_fail 'cannot sync staged v0.10 module tree' || return
  mv -T -- "$staged_modules" "$modules_parent/$R46H_V10_RELEASE" || \
    r46h_mod_fail 'cannot atomically publish v0.10 module tree' || return
  sync || r46h_mod_fail 'cannot sync published v0.10 module tree' || return
  r46h_mod_verify_tree "$modules_parent" installed || return
  r46h_mod_clear_stage "$state_dir" || return
  r46h_mod_publish_receipt "$state_dir" || return
  [[ "$(r46h_mod_detect_state "$modules_parent" "$state_dir")" == complete ]] || \
    r46h_mod_fail 'v0.10 module transaction did not reach exact complete state' || return
}
