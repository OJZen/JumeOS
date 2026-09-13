#!/bin/bash
# Pure BOOT-directory transaction helpers for the R46H v0.16 DTB promotion.
# The production wrapper owns device discovery, mounts, health gates and locks.

readonly R46H_V16_DTB_NAME=rk3326-r46h-mainline-v0.16-disable-secondary.dtb
readonly R46H_V16_DTB_SIZE=49522
readonly R46H_V16_DTB_SHA256=7831617d4003cdbb2733433781f80625cb94e7c9d619f2f90990223b8f8d7f81
readonly R46H_V16_BOOT_NAME=boot.ini.v0.16-disable-secondary
readonly R46H_V16_BOOT_SIZE=1449
readonly R46H_V16_BOOT_SHA256=edb33de5fef23b810deec13c05b6958a72eea3dbb74ce2b39b0f80cdb508aba3

readonly R46H_V15_IMAGE_NAME=Image.mainline-v0.15-gaming-product.gz
readonly R46H_V15_IMAGE_SIZE=14925282
readonly R46H_V15_IMAGE_SHA256=9a4f58ed03aab19d5472c5ff41f99383dee90c653dadebcee360f2323dc653bf
readonly R46H_V15_DTB_NAME=rk3326-r46h-mainline-v0.15-gaming-product.dtb
readonly R46H_V15_DTB_SIZE=49518
readonly R46H_V15_DTB_SHA256=4d6d4ebad3b98600b6e9a38df4ca82230335558497a9e15dd0e81ca60e304b61
readonly R46H_V15_BOOT_NAME=boot.ini.v0.15-gaming-product
readonly R46H_V15_BOOT_SIZE=1403
readonly R46H_V15_BOOT_SHA256=f41ab69f17cd22fb22446e390c46325d4e536cf8dee1bd9ab85682297dca1ac8

readonly R46H_V10_IMAGE_NAME=Image.mainline-v0.10-adc-full-range.gz
readonly R46H_V10_IMAGE_SIZE=14921256
readonly R46H_V10_IMAGE_SHA256=736549a919eee0342a2bae961a85b59337ad8de3c901c2e5f193aa15fdead954
readonly R46H_V10_DTB_NAME=rk3326-r46h-mainline-v0.10-adc-full-range.dtb
readonly R46H_V10_DTB_SIZE=49481
readonly R46H_V10_DTB_SHA256=04868feae2678cbee5073f93250dafb0219e560b0f1131526ac89930a8791cee
readonly R46H_V10_BOOT_NAME=boot.ini.v0.10-adc-full-range
readonly R46H_V10_BOOT_SIZE=1408
readonly R46H_V10_BOOT_SHA256=915039bf17dea6aa2ba42701195510c346c70c8c81117151e7d153073fa1ceab

readonly R46H_V08_IMAGE_NAME=Image.mainline-v0.8-bootloader-handoff.gz
readonly R46H_V08_IMAGE_SIZE=14920864
readonly R46H_V08_IMAGE_SHA256=d7c7796c097fbe692412fb63d19c1f97c4b21f55ae2c3b1e8df324a739f166fa
readonly R46H_V08_DTB_NAME=rk3326-r46h-mainline-v0.8-bootloader-handoff.dtb
readonly R46H_V08_DTB_SIZE=49481
readonly R46H_V08_DTB_SHA256=7259bac7bdd063fbaed987a0d5d2bf7066e02beaacc4440849b93d5f048e3dbc
readonly R46H_V08_BOOT_NAME=boot.ini.v0.8-bootloader-handoff
readonly R46H_V08_BOOT_SIZE=1427
readonly R46H_V08_BOOT_SHA256=cead3fbee0d5c42fddcd6f6d83839b82af791e1abf1dd0252d9850fb47dd33fb

readonly R46H_UBOOT_DTB_SIZE=59991
readonly R46H_UBOOT_DTB_SHA256=dd892bbd8dd1e5c51f7b3be2390faab4355e6932aef6a48b030b2591a7b0bf4c
readonly R46H_ACTIVE_BOOT_NAME=boot.ini
readonly R46H_PREPARE_JOURNAL=.r46h-v16-prepare.journal
readonly R46H_ACTIVATE_JOURNAL=.r46h-v16-activate.journal
readonly R46H_ROLLBACK_JOURNAL=.r46h-v16-rollback.journal
readonly R46H_DTB_STAGE=.rk3326-r46h-mainline-v0.16-disable-secondary.dtb.r46h-stage
readonly R46H_BOOT_STAGE=.boot.ini.v0.16-disable-secondary.r46h-stage
readonly R46H_ACTIVE_STAGE=.boot.ini.v0.16-disable-secondary.activate-stage
readonly R46H_BASE_TOP_LEVEL_COUNT=29
readonly R46H_MINIMUM_FREE_BYTES=524288

r46h_tx_fail() {
  printf 'ERROR: %s\n' "$*" >&2
  return 1
}

r46h_tx_hash() {
  sha256sum "$1" | awk '{print $1}'
}

r46h_tx_size() {
  stat -c '%s' "$1" 2>/dev/null || stat -f '%z' "$1"
}

r46h_tx_check_file() {
  local path=$1 expected_size=$2 expected_hash=$3 label=$4 links
  [[ -f "$path" && ! -L "$path" ]] || r46h_tx_fail "unsafe or missing ${label}" || return
  links=$(stat -c '%h' "$path" 2>/dev/null || stat -f '%l' "$path") || \
    r46h_tx_fail "cannot stat ${label}" || return
  [[ "$links" == 1 ]] || r46h_tx_fail "unexpected link count for ${label}" || return
  [[ "$(r46h_tx_size "$path")" == "$expected_size" ]] || \
    r46h_tx_fail "size mismatch for ${label}" || return
  [[ "$(r46h_tx_hash "$path")" == "$expected_hash" ]] || \
    r46h_tx_fail "SHA-256 mismatch for ${label}" || return
}

r46h_tx_check_regular_or_absent() {
  local path=$1 label=$2 links
  [[ -e "$path" || -L "$path" ]] || return 0
  [[ -f "$path" && ! -L "$path" ]] || r46h_tx_fail "unsafe ${label}" || return
  links=$(stat -c '%h' "$path" 2>/dev/null || stat -f '%l' "$path") || \
    r46h_tx_fail "cannot stat ${label}" || return
  [[ "$links" == 1 ]] || r46h_tx_fail "unexpected link count for ${label}" || return
}

r46h_tx_prepare_journal_bytes() {
  printf '%s\n' \
    'format_version=1' \
    'tool_id=r46h-v16-boot-promotion-v0.1' \
    'operation=prepare-versioned-files' \
    'active_boot=v0.15-gaming-product' \
    'target_boot=v0.16-disable-secondary' \
    'state=in-progress'
}

r46h_tx_activate_journal_bytes() {
  printf '%s\n' \
    'format_version=1' \
    'tool_id=r46h-v16-boot-promotion-v0.1' \
    'operation=activate-boot-ini' \
    'fallback_boot=v0.15-gaming-product' \
    'target_boot=v0.16-disable-secondary' \
    'state=in-progress'
}

r46h_tx_rollback_journal_bytes() {
  printf '%s\n' \
    'format_version=1' \
    'tool_id=r46h-v16-boot-promotion-v0.1' \
    'operation=rollback-boot-ini' \
    'active_boot=v0.16-disable-secondary' \
    'target_boot=v0.15-gaming-product' \
    'state=in-progress'
}

r46h_tx_check_journal() {
  local path=$1 operation=$2
  r46h_tx_check_regular_or_absent "$path" "$operation journal" || return
  [[ -f "$path" ]] || r46h_tx_fail "missing ${operation} journal" || return
  case "$operation" in
    prepare)
      cmp -s "$path" <(r46h_tx_prepare_journal_bytes) || \
        r46h_tx_fail 'prepare journal mismatch' || return
      ;;
    activate)
      cmp -s "$path" <(r46h_tx_activate_journal_bytes) || \
        r46h_tx_fail 'activation journal mismatch' || return
      ;;
    rollback)
      cmp -s "$path" <(r46h_tx_rollback_journal_bytes) || \
        r46h_tx_fail 'rollback journal mismatch' || return
      ;;
    *) r46h_tx_fail "unknown journal operation: ${operation}" || return ;;
  esac
}

r46h_tx_flush() {
  sync || r46h_tx_fail 'sync failed' || return
  if [[ "${R46H_TRANSACTION_TEST_MODE:-0}" != 1 ]]; then
    [[ -n "${R46H_BOOT_DEVICE:-}" ]] || r46h_tx_fail 'BOOT device is not set' || return
    blockdev --flushbufs "$R46H_BOOT_DEVICE" || r46h_tx_fail 'BOOT flush failed' || return
    sync || r46h_tx_fail 'post-flush sync failed' || return
  fi
}

r46h_tx_is_base_name() {
  case "$1" in
    .Spotlight-V100|.fseventsd|.console|Image|Image.mainline-v0.10-adc-full-range.gz|\
    Image.mainline-v0.15-gaming-product.gz|Image.mainline-v0.8-bootloader-handoff.gz|\
    'System Volume Information'|USE_DTB_SELECT_TO_SELECT_DEVICE|arkos4clone-uboot.dtb|\
    boot.ini|boot.ini.v0.10-adc-full-range|boot.ini.v0.15-gaming-product|\
    boot.ini.v0.8-bootloader-handoff|boot.ini.vendor|boot.log|clone_log.txt|\
    consoles|dtb_selector_linux32|dtb_selector_macos|dtb_selector_win32.exe|\
    error.log|firstboot.sh|logo.bmp|rk3326-r46h-linux.dtb|\
    rk3326-r46h-mainline-v0.10-adc-full-range.dtb|\
    rk3326-r46h-mainline-v0.15-gaming-product.dtb|\
    rk3326-r46h-mainline-v0.8-bootloader-handoff.dtb|uInitrd) return 0 ;;
    *) return 1 ;;
  esac
}

r46h_tx_is_target_name() {
  case "$1" in
    "$R46H_V16_DTB_NAME"|"$R46H_V16_BOOT_NAME") return 0 ;;
    *) return 1 ;;
  esac
}

r46h_tx_is_transient_name() {
  case "$1" in
    "$R46H_PREPARE_JOURNAL"|"$R46H_ACTIVATE_JOURNAL"|"$R46H_ROLLBACK_JOURNAL"|\
    "$R46H_DTB_STAGE"|"$R46H_BOOT_STAGE"|"$R46H_ACTIVE_STAGE") return 0 ;;
    *) return 1 ;;
  esac
}

r46h_tx_verify_base_types() {
  local boot=$1 name
  for name in consoles 'System Volume Information' .Spotlight-V100 .fseventsd; do
    [[ -d "$boot/$name" && ! -L "$boot/$name" ]] || \
      r46h_tx_fail "required BOOT directory is unsafe: ${name}" || return
  done
  for name in \
    USE_DTB_SELECT_TO_SELECT_DEVICE boot.ini uInitrd clone_log.txt \
    rk3326-r46h-linux.dtb Image firstboot.sh logo.bmp boot.log .console \
    boot.ini.vendor arkos4clone-uboot.dtb dtb_selector_macos \
    dtb_selector_linux32 dtb_selector_win32.exe error.log \
    "$R46H_V08_BOOT_NAME" "$R46H_V08_IMAGE_NAME" "$R46H_V08_DTB_NAME" \
    "$R46H_V10_BOOT_NAME" "$R46H_V10_IMAGE_NAME" "$R46H_V10_DTB_NAME" \
    "$R46H_V15_BOOT_NAME" "$R46H_V15_IMAGE_NAME" "$R46H_V15_DTB_NAME"; do
    [[ -f "$boot/$name" && ! -L "$boot/$name" ]] || \
      r46h_tx_fail "required BOOT file is unsafe: ${name}" || return
  done
}

r46h_tx_verify_top_level() {
  local boot=$1 entry name base_count=0
  while IFS= read -r entry; do
    name=${entry##*/}
    if r46h_tx_is_base_name "$name"; then
      base_count=$((base_count + 1))
    elif r46h_tx_is_target_name "$name" || r46h_tx_is_transient_name "$name"; then
      :
    else
      r46h_tx_fail "unexpected BOOT top-level entry: ${name}" || return
    fi
  done < <(find "$boot" -mindepth 1 -maxdepth 1 -print | LC_ALL=C sort)
  [[ "$base_count" == "$R46H_BASE_TOP_LEVEL_COUNT" ]] || \
    r46h_tx_fail "BOOT base member count mismatch: ${base_count}" || return
  r46h_tx_verify_base_types "$boot"
}

r46h_tx_verify_anchors() {
  local boot=$1 active_allowed=$2 active_hash active_size
  r46h_tx_check_file "$boot/$R46H_V08_BOOT_NAME" "$R46H_V08_BOOT_SIZE" \
    "$R46H_V08_BOOT_SHA256" 'v0.8 fallback boot script' || return
  r46h_tx_check_file "$boot/$R46H_V08_IMAGE_NAME" "$R46H_V08_IMAGE_SIZE" \
    "$R46H_V08_IMAGE_SHA256" 'v0.8 fallback Image' || return
  r46h_tx_check_file "$boot/$R46H_V08_DTB_NAME" "$R46H_V08_DTB_SIZE" \
    "$R46H_V08_DTB_SHA256" 'v0.8 fallback DTB' || return
  r46h_tx_check_file "$boot/$R46H_V10_BOOT_NAME" "$R46H_V10_BOOT_SIZE" \
    "$R46H_V10_BOOT_SHA256" 'v0.10 fallback boot script' || return
  r46h_tx_check_file "$boot/$R46H_V10_IMAGE_NAME" "$R46H_V10_IMAGE_SIZE" \
    "$R46H_V10_IMAGE_SHA256" 'v0.10 fallback Image' || return
  r46h_tx_check_file "$boot/$R46H_V10_DTB_NAME" "$R46H_V10_DTB_SIZE" \
    "$R46H_V10_DTB_SHA256" 'v0.10 fallback DTB' || return
  r46h_tx_check_file "$boot/$R46H_V15_BOOT_NAME" "$R46H_V15_BOOT_SIZE" \
    "$R46H_V15_BOOT_SHA256" 'v0.15 fallback boot script' || return
  r46h_tx_check_file "$boot/$R46H_V15_IMAGE_NAME" "$R46H_V15_IMAGE_SIZE" \
    "$R46H_V15_IMAGE_SHA256" 'v0.15 product Image' || return
  r46h_tx_check_file "$boot/$R46H_V15_DTB_NAME" "$R46H_V15_DTB_SIZE" \
    "$R46H_V15_DTB_SHA256" 'v0.15 fallback DTB' || return
  r46h_tx_check_file "$boot/arkos4clone-uboot.dtb" "$R46H_UBOOT_DTB_SIZE" \
    "$R46H_UBOOT_DTB_SHA256" 'root U-Boot DTB' || return
  r46h_tx_check_file "$boot/consoles/r46h/arkos4clone-uboot.dtb" \
    "$R46H_UBOOT_DTB_SIZE" "$R46H_UBOOT_DTB_SHA256" 'R46H U-Boot DTB' || return
  r46h_tx_check_regular_or_absent "$boot/$R46H_ACTIVE_BOOT_NAME" 'active boot script' || return
  active_size=$(r46h_tx_size "$boot/$R46H_ACTIVE_BOOT_NAME") || return
  active_hash=$(r46h_tx_hash "$boot/$R46H_ACTIVE_BOOT_NAME") || return
  case "$active_hash:$active_size:$active_allowed" in
    "$R46H_V15_BOOT_SHA256:$R46H_V15_BOOT_SIZE:v15"|\
    "$R46H_V15_BOOT_SHA256:$R46H_V15_BOOT_SIZE:either"|\
    "$R46H_V16_BOOT_SHA256:$R46H_V16_BOOT_SIZE:v16"|\
    "$R46H_V16_BOOT_SHA256:$R46H_V16_BOOT_SIZE:either") ;;
    *) r46h_tx_fail 'active boot.ini is not an allowed exact state' || return ;;
  esac
}

r46h_tx_target_count() {
  local boot=$1 count=0
  [[ ! -e "$boot/$R46H_V16_DTB_NAME" && ! -L "$boot/$R46H_V16_DTB_NAME" ]] || {
    r46h_tx_check_file "$boot/$R46H_V16_DTB_NAME" "$R46H_V16_DTB_SIZE" \
      "$R46H_V16_DTB_SHA256" 'v0.16 DTB' || return
    count=$((count + 1))
  }
  [[ ! -e "$boot/$R46H_V16_BOOT_NAME" && ! -L "$boot/$R46H_V16_BOOT_NAME" ]] || {
    r46h_tx_check_file "$boot/$R46H_V16_BOOT_NAME" "$R46H_V16_BOOT_SIZE" \
      "$R46H_V16_BOOT_SHA256" 'v0.16 versioned boot script' || return
    count=$((count + 1))
  }
  printf '%s\n' "$count"
}

r46h_tx_detect_state() {
  local boot=$1 target_count prepare=0 activate=0 rollback=0 active_hash active_size name
  r46h_tx_verify_top_level "$boot" || return
  for name in "$R46H_DTB_STAGE" "$R46H_BOOT_STAGE" "$R46H_ACTIVE_STAGE"; do
    r46h_tx_check_regular_or_absent "$boot/$name" "$name" || return
  done
  if [[ -e "$boot/$R46H_PREPARE_JOURNAL" || -L "$boot/$R46H_PREPARE_JOURNAL" ]]; then
    r46h_tx_check_journal "$boot/$R46H_PREPARE_JOURNAL" prepare || return
    prepare=1
  fi
  if [[ -e "$boot/$R46H_ACTIVATE_JOURNAL" || -L "$boot/$R46H_ACTIVATE_JOURNAL" ]]; then
    r46h_tx_check_journal "$boot/$R46H_ACTIVATE_JOURNAL" activate || return
    activate=1
  fi
  if [[ -e "$boot/$R46H_ROLLBACK_JOURNAL" || -L "$boot/$R46H_ROLLBACK_JOURNAL" ]]; then
    r46h_tx_check_journal "$boot/$R46H_ROLLBACK_JOURNAL" rollback || return
    rollback=1
  fi
  (( prepare + activate + rollback <= 1 )) || r46h_tx_fail 'multiple BOOT journals are present' || return
  target_count=$(r46h_tx_target_count "$boot") || return
  active_size=$(r46h_tx_size "$boot/$R46H_ACTIVE_BOOT_NAME") || return
  active_hash=$(r46h_tx_hash "$boot/$R46H_ACTIVE_BOOT_NAME") || return

  if (( prepare == 1 )); then
    r46h_tx_verify_anchors "$boot" v15 || return
    [[ ! -e "$boot/$R46H_ACTIVE_STAGE" && ! -L "$boot/$R46H_ACTIVE_STAGE" ]] || \
      r46h_tx_fail 'activation stage exists during preparation' || return
    printf 'prepare-partial\n'
    return
  fi
  if (( activate == 1 )); then
    [[ "$target_count" == 2 ]] || r46h_tx_fail 'activation journal lacks complete target files' || return
    r46h_tx_verify_anchors "$boot" either || return
    case "$active_hash:$active_size" in
      "$R46H_V15_BOOT_SHA256:$R46H_V15_BOOT_SIZE") printf 'activate-partial-v15\n' ;;
      "$R46H_V16_BOOT_SHA256:$R46H_V16_BOOT_SIZE") printf 'activate-partial-v16\n' ;;
      *) r46h_tx_fail 'activation journal has an unknown active boot.ini' || return ;;
    esac
    return
  fi
  if (( rollback == 1 )); then
    [[ "$target_count" == 2 ]] || r46h_tx_fail 'rollback journal lacks complete target files' || return
    r46h_tx_verify_anchors "$boot" either || return
    case "$active_hash:$active_size" in
      "$R46H_V15_BOOT_SHA256:$R46H_V15_BOOT_SIZE") printf 'rollback-partial-v15\n' ;;
      "$R46H_V16_BOOT_SHA256:$R46H_V16_BOOT_SIZE") printf 'rollback-partial-v16\n' ;;
      *) r46h_tx_fail 'rollback journal has an unknown active boot.ini' || return ;;
    esac
    return
  fi
  for name in "$R46H_DTB_STAGE" "$R46H_BOOT_STAGE" "$R46H_ACTIVE_STAGE"; do
    [[ ! -e "$boot/$name" && ! -L "$boot/$name" ]] || \
      r46h_tx_fail "orphan BOOT stage without journal: ${name}" || return
  done
  case "$target_count:$active_hash:$active_size" in
    "0:$R46H_V15_BOOT_SHA256:$R46H_V15_BOOT_SIZE")
      r46h_tx_verify_anchors "$boot" v15 || return
      printf 'base\n'
      ;;
    "2:$R46H_V15_BOOT_SHA256:$R46H_V15_BOOT_SIZE")
      r46h_tx_verify_anchors "$boot" v15 || return
      printf 'prepared\n'
      ;;
    "2:$R46H_V16_BOOT_SHA256:$R46H_V16_BOOT_SIZE")
      r46h_tx_verify_anchors "$boot" v16 || return
      printf 'activated\n'
      ;;
    *) r46h_tx_fail 'BOOT state is not base, prepared, activated or recoverable' || return ;;
  esac
}

r46h_tx_verify_sources() {
  local source=$1
  r46h_tx_check_file "$source/$R46H_V16_DTB_NAME" "$R46H_V16_DTB_SIZE" \
    "$R46H_V16_DTB_SHA256" 'source v0.16 DTB' || return
  r46h_tx_check_file "$source/$R46H_V16_BOOT_NAME" "$R46H_V16_BOOT_SIZE" \
    "$R46H_V16_BOOT_SHA256" 'source v0.16 boot script' || return
}

r46h_tx_fault() {
  [[ "${R46H_TRANSACTION_TEST_MODE:-0}" == 1 && \
     "${R46H_TRANSACTION_FAULT:-}" == "$1" ]] || return 0
  r46h_tx_fail "injected transaction fault at $1"
}

r46h_tx_publish() {
  local boot=$1 source=$2 final_name=$3 stage_name=$4 size=$5 hash=$6 label=$7
  if [[ -e "$boot/$final_name" || -L "$boot/$final_name" ]]; then
    r46h_tx_check_file "$boot/$final_name" "$size" "$hash" "$label"
    return
  fi
  r46h_tx_check_regular_or_absent "$boot/$stage_name" "${label} stage" || return
  rm -f "$boot/$stage_name" || r46h_tx_fail "cannot clear ${label} stage" || return
  cp "$source/$final_name" "$boot/$stage_name" || r46h_tx_fail "cannot stage ${label}" || return
  r46h_tx_check_file "$boot/$stage_name" "$size" "$hash" "staged ${label}" || return
  r46h_tx_flush || return
  [[ ! -e "$boot/$final_name" && ! -L "$boot/$final_name" ]] || \
    r46h_tx_fail "${label} destination appeared concurrently" || return
  mv "$boot/$stage_name" "$boot/$final_name" || r46h_tx_fail "cannot publish ${label}" || return
  r46h_tx_flush || return
  r46h_tx_check_file "$boot/$final_name" "$size" "$hash" "$label"
}

r46h_tx_prepare() {
  local boot=$1 source=$2 recovery=${3:-0} state available_kib required_bytes required_kib
  r46h_tx_verify_sources "$source" || return
  state=$(r46h_tx_detect_state "$boot") || return
  if [[ "$state" == prepared ]]; then
    [[ "$recovery" == 0 ]] || r46h_tx_fail 'prepare recovery requested after completion' || return
    return 0
  fi
  if [[ "$recovery" == 1 ]]; then
    [[ "$state" == prepare-partial ]] || \
      r46h_tx_fail 'prepare recovery requires exact partial state' || return
  else
    [[ "$state" == base ]] || r46h_tx_fail 'normal prepare requires exact base state' || return
    (umask 077; set -o noclobber; r46h_tx_prepare_journal_bytes > "$boot/$R46H_PREPARE_JOURNAL") || \
      r46h_tx_fail 'cannot publish prepare journal' || return
    r46h_tx_flush || return
  fi

  available_kib=$(df -Pk "$boot" | awk 'END {print $4}') || return
  [[ "$available_kib" =~ ^[0-9]+$ ]] || r46h_tx_fail 'cannot read BOOT free space' || return
  required_bytes=$R46H_MINIMUM_FREE_BYTES
  [[ -e "$boot/$R46H_V16_DTB_NAME" || -L "$boot/$R46H_V16_DTB_NAME" ]] || \
    required_bytes=$((required_bytes + R46H_V16_DTB_SIZE))
  [[ -e "$boot/$R46H_V16_BOOT_NAME" || -L "$boot/$R46H_V16_BOOT_NAME" ]] || \
    required_bytes=$((required_bytes + R46H_V16_BOOT_SIZE))
  required_kib=$(((required_bytes + 1023) / 1024))
  (( available_kib >= required_kib )) || r46h_tx_fail 'BOOT free space is below the safe projection' || return

  r46h_tx_publish "$boot" "$source" "$R46H_V16_DTB_NAME" "$R46H_DTB_STAGE" \
    "$R46H_V16_DTB_SIZE" "$R46H_V16_DTB_SHA256" 'v0.16 DTB' || return
  r46h_tx_fault after-dtb || return
  r46h_tx_publish "$boot" "$source" "$R46H_V16_BOOT_NAME" "$R46H_BOOT_STAGE" \
    "$R46H_V16_BOOT_SIZE" "$R46H_V16_BOOT_SHA256" 'v0.16 versioned boot script' || return
  r46h_tx_fault after-boot || return
  r46h_tx_verify_anchors "$boot" v15 || return
  [[ "$(r46h_tx_target_count "$boot")" == 2 ]] || r46h_tx_fail 'target publication is incomplete' || return
  rm "$boot/$R46H_PREPARE_JOURNAL" || r46h_tx_fail 'cannot remove prepare journal' || return
  r46h_tx_flush || return
  [[ "$(r46h_tx_detect_state "$boot")" == prepared ]] || \
    r46h_tx_fail 'prepared BOOT verification failed' || return
}

r46h_tx_activate() {
  local boot=$1 recovery=${2:-0} state
  state=$(r46h_tx_detect_state "$boot") || return
  if [[ "$state" == activated ]]; then
    [[ "$recovery" == 0 ]] || r46h_tx_fail 'activation recovery requested after completion' || return
    return 0
  fi
  if [[ "$recovery" == 1 ]]; then
    case "$state" in activate-partial-v15|activate-partial-v16) ;;
      *) r46h_tx_fail 'activation recovery requires exact partial state' || return ;;
    esac
  else
    [[ "$state" == prepared ]] || r46h_tx_fail 'normal activation requires prepared state' || return
    (umask 077; set -o noclobber; r46h_tx_activate_journal_bytes > "$boot/$R46H_ACTIVATE_JOURNAL") || \
      r46h_tx_fail 'cannot publish activation journal' || return
    r46h_tx_flush || return
    state=activate-partial-v15
  fi
  r46h_tx_check_regular_or_absent "$boot/$R46H_ACTIVE_STAGE" 'active boot stage' || return
  if [[ "$state" == activate-partial-v15 ]]; then
    rm -f "$boot/$R46H_ACTIVE_STAGE" || r46h_tx_fail 'cannot clear active boot stage' || return
    cp "$boot/$R46H_V16_BOOT_NAME" "$boot/$R46H_ACTIVE_STAGE" || \
      r46h_tx_fail 'cannot stage active v0.16 boot script' || return
    r46h_tx_check_file "$boot/$R46H_ACTIVE_STAGE" "$R46H_V16_BOOT_SIZE" \
      "$R46H_V16_BOOT_SHA256" 'staged active v0.16 boot script' || return
    r46h_tx_flush || return
    r46h_tx_verify_anchors "$boot" v15 || return
    mv -f "$boot/$R46H_ACTIVE_STAGE" "$boot/$R46H_ACTIVE_BOOT_NAME" || \
      r46h_tx_fail 'cannot publish active v0.16 boot script' || return
    r46h_tx_fault after-active || return
    r46h_tx_flush || return
  fi
  r46h_tx_verify_anchors "$boot" v16 || return
  rm -f "$boot/$R46H_ACTIVE_STAGE" || r46h_tx_fail 'cannot clear completed active stage' || return
  rm "$boot/$R46H_ACTIVATE_JOURNAL" || r46h_tx_fail 'cannot remove activation journal' || return
  r46h_tx_flush || return
  [[ "$(r46h_tx_detect_state "$boot")" == activated ]] || \
    r46h_tx_fail 'activated BOOT verification failed' || return
}

r46h_tx_rollback() {
  local boot=$1 state active_hash active_size
  state=$(r46h_tx_detect_state "$boot") || return
  case "$state" in
    base|prepared) return 0 ;;
    activate-partial-v15|activate-partial-v16|rollback-partial-v15|\
    rollback-partial-v16|activated) ;;
    *) r46h_tx_fail 'rollback requires prepared or activated target files' || return ;;
  esac
  active_size=$(r46h_tx_size "$boot/$R46H_ACTIVE_BOOT_NAME") || return
  active_hash=$(r46h_tx_hash "$boot/$R46H_ACTIVE_BOOT_NAME") || return
  if [[ "$active_hash:$active_size" == "$R46H_V16_BOOT_SHA256:$R46H_V16_BOOT_SIZE" ]]; then
    if [[ "$state" == activated ]]; then
      (umask 077; set -o noclobber; r46h_tx_rollback_journal_bytes > "$boot/$R46H_ROLLBACK_JOURNAL") || \
        r46h_tx_fail 'cannot publish rollback journal' || return
      r46h_tx_flush || return
    fi
    rm -f "$boot/$R46H_ACTIVE_STAGE" || r46h_tx_fail 'cannot clear rollback stage' || return
    cp "$boot/$R46H_V15_BOOT_NAME" "$boot/$R46H_ACTIVE_STAGE" || \
      r46h_tx_fail 'cannot stage v0.15 rollback script' || return
    r46h_tx_check_file "$boot/$R46H_ACTIVE_STAGE" "$R46H_V15_BOOT_SIZE" \
      "$R46H_V15_BOOT_SHA256" 'staged v0.15 rollback script' || return
    r46h_tx_flush || return
    r46h_tx_verify_anchors "$boot" v16 || return
    mv -f "$boot/$R46H_ACTIVE_STAGE" "$boot/$R46H_ACTIVE_BOOT_NAME" || \
      r46h_tx_fail 'cannot publish v0.15 rollback script' || return
    r46h_tx_fault after-rollback-active || return
    r46h_tx_flush || return
  else
    r46h_tx_verify_anchors "$boot" v15 || return
  fi
  rm -f "$boot/$R46H_ACTIVE_STAGE" "$boot/$R46H_ACTIVATE_JOURNAL" \
    "$boot/$R46H_ROLLBACK_JOURNAL" || \
    r46h_tx_fail 'cannot clear rollback transaction markers' || return
  r46h_tx_flush || return
  [[ "$(r46h_tx_detect_state "$boot")" == prepared ]] || \
    r46h_tx_fail 'rollback did not restore exact prepared state' || return
}
