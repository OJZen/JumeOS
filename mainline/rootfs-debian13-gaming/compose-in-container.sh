#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG
export DEBIAN_FRONTEND=noninteractive

readonly PAYLOAD=/run/r46h-gaming-payload
readonly EVIDENCE=/usr/share/r46h-build/.gaming-compose-evidence
readonly EMPTY_APT=/run/r46h-gaming-compose-apt
readonly NULL_CONFIG=/run/r46h-gaming-compose-null.cfg
readonly GAMING_RECEIPT=/var/lib/r46h/gaming-mvp-v0.4-installed
readonly ROOTFS_RECEIPT=/usr/share/r46h-build/CONSOLIDATED-RECEIPT
readonly FIRSTBOOT=/usr/libexec/r46h-firstboot
readonly ROOTFS_SMOKE=/usr/local/sbin/r46h-rootfs-smoke

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

for name in ARTIFACT_ID BASE_IMAGE_ID SOURCE_GIT_COMMIT V08_FALLBACK_BUNDLE_SHA256 \
  V08_FALLBACK_MODULE_TREE_SHA256 V10_FALLBACK_BUNDLE_SHA256 \
  V10_FALLBACK_MODULE_TREE_SHA256 KERNEL_RELEASE \
  KERNEL_BUNDLE_SHA256 GAMING_ARCHIVE_SHA256 GAMING_PACKAGE_MANIFEST_SHA256 \
  GAMING_PAYLOAD_SHA256SUMS_SHA256 GAMING_RECEIPT_SHA256 RETROARCH_CONFIG_SHA256 \
  GAME_UI_SHA256 SMOKE_CORE_SHA256 STORAGE_AUDIT_SHA256 \
  KERNEL_SOURCE_COMMIT KERNEL_SOURCE_SNAPSHOT_SHA256 KERNEL_MODULE_TREE_SHA256 \
  KERNEL_IMAGE_SHA256 KERNEL_DTB_SHA256 PRODUCT_KERNEL_DIRECTORY \
  PRODUCT_UBOOT_COMMANDS_SHA256 \
  NES_SMOKE_SHA256 BASE_FIRSTBOOT_SHA256 FINAL_FIRSTBOOT_SHA256 \
  BASE_ROOTFS_SMOKE_SHA256 FINAL_ROOTFS_SMOKE_SHA256 FS_UUID; do
  [[ -n "${!name:-}" ]] || die "missing environment: $name"
done
for name in BASE_IMAGE_ID V08_FALLBACK_BUNDLE_SHA256 V08_FALLBACK_MODULE_TREE_SHA256 \
  V10_FALLBACK_BUNDLE_SHA256 V10_FALLBACK_MODULE_TREE_SHA256 \
  KERNEL_BUNDLE_SHA256 GAMING_ARCHIVE_SHA256 \
  GAMING_PACKAGE_MANIFEST_SHA256 GAMING_PAYLOAD_SHA256SUMS_SHA256 \
  GAMING_RECEIPT_SHA256 GAME_UI_SHA256 SMOKE_CORE_SHA256 STORAGE_AUDIT_SHA256 \
  RETROARCH_CONFIG_SHA256 NES_SMOKE_SHA256 \
  KERNEL_SOURCE_SNAPSHOT_SHA256 KERNEL_MODULE_TREE_SHA256 KERNEL_IMAGE_SHA256 \
  KERNEL_DTB_SHA256 PRODUCT_UBOOT_COMMANDS_SHA256 \
  BASE_FIRSTBOOT_SHA256 FINAL_FIRSTBOOT_SHA256 BASE_ROOTFS_SMOKE_SHA256 \
  FINAL_ROOTFS_SMOKE_SHA256; do
  [[ "${!name}" =~ ^(sha256:)?[0-9a-f]{64}$ ]] || die "invalid hash: $name"
done
[[ "$SOURCE_GIT_COMMIT" =~ ^[0-9a-f]{40}$ ]] || die 'invalid source commit'
[[ "$KERNEL_SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || die 'invalid kernel source commit'
[[ "$KERNEL_RELEASE" == 6.12.99-r46h-mainline-v0.15-gaming-product ]] || \
  die 'unexpected kernel release'
[[ "$ARTIFACT_ID" == debian13-p2-gaming-v0.5 ]] || die 'unexpected artifact identity'
[[ "$FS_UUID" == d3130005-46a4-4d56-9001-000000000005 ]] || die 'unexpected filesystem UUID'
[[ "$PRODUCT_KERNEL_DIRECTORY" == \
  /var/lib/r46h-gaming-product-kernel/v0.15-gaming-product ]] || \
  die 'unexpected product kernel directory'

[[ -d "$PAYLOAD" && ! -L "$PAYLOAD" ]] || die 'gaming payload is unavailable'
payload_members=$(find "$PAYLOAD" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)
[[ "$payload_members" == $'PACKAGES.tsv\nPAYLOAD-INFO.json\nPAYLOAD.COMPLETE\nSHA256SUMS\ndebs\nfiles\ninstall.sh' ]] || \
  die 'unexpected gaming payload member set'
[[ "$(sha256sum "$PAYLOAD/PACKAGES.tsv" | awk '{print $1}')" == \
  "$GAMING_PACKAGE_MANIFEST_SHA256" ]] || die 'gaming package manifest mismatch'
[[ "$(sha256sum "$PAYLOAD/SHA256SUMS" | awk '{print $1}')" == \
  "$GAMING_PAYLOAD_SHA256SUMS_SHA256" ]] || die 'gaming payload manifest mismatch'
[[ "$(<"$PAYLOAD/PAYLOAD.COMPLETE")" == \
  "sha256sums_sha256=$GAMING_PAYLOAD_SHA256SUMS_SHA256" ]] || \
  die 'gaming payload completion marker mismatch'
[[ "$(sha256sum "$PAYLOAD/files/retroarch.cfg" | awk '{print $1}')" == \
  "$RETROARCH_CONFIG_SHA256" ]] || die 'RetroArch product config mismatch'
[[ "$(sha256sum "$PAYLOAD/files/r46h-game-ui" | awk '{print $1}')" == \
  "$GAME_UI_SHA256" ]] || die 'accepted game UI hotfix mismatch'
[[ "$(sha256sum "$PAYLOAD/files/r46h-smoke-libretro.so" | awk '{print $1}')" == \
  "$SMOKE_CORE_SHA256" ]] || die 'accepted smoke core hotfix mismatch'
[[ "$(sha256sum "$PAYLOAD/files/r46h-storage-audit" | awk '{print $1}')" == \
  "$STORAGE_AUDIT_SHA256" ]] || die 'accepted storage audit hotfix mismatch'
(
  cd "$PAYLOAD"
  sha256sum -c SHA256SUMS
) > /run/r46h-gaming-payload-verify.txt

mapfile -d '' debs < <(find "$PAYLOAD/debs" -maxdepth 1 -type f -name '*.deb' -print0 | sort -z)
(( ${#debs[@]} >= 20 )) || die 'gaming payload Debian package set is incomplete'
rm -rf -- "$EMPTY_APT"
install -d -m 0700 "$EMPTY_APT" "$EMPTY_APT/sources.list.d"
: > "$EMPTY_APT/sources.list"
[[ ! -e /usr/sbin/policy-rc.d && ! -L /usr/sbin/policy-rc.d ]] || \
  die 'unexpected pre-existing policy-rc.d'
printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
chmod 0755 /usr/sbin/policy-rc.d
apt-get \
  -o "Dir::Etc::sourcelist=$EMPTY_APT/sources.list" \
  -o "Dir::Etc::sourceparts=$EMPTY_APT/sources.list.d" \
  install -y --no-install-recommends "${debs[@]}"
rm -f -- /usr/sbin/policy-rc.d
rm -rf -- "$EMPTY_APT"

while IFS=$'\t' read -r package version; do
  [[ -n "$package" && -n "$version" ]] || die 'invalid gaming package manifest row'
  [[ "$(dpkg-query -W -f='${db:Status-Abbrev}\t${Version}' "$package")" == $'ii \t'"$version" ]] || \
    die "installed package mismatch: $package"
done < "$PAYLOAD/PACKAGES.tsv"

install -d -o root -g root -m 0755 /etc/r46h /usr/local/libexec \
  /usr/local/share/r46h /var/lib/r46h /usr/share/doc/r46h-gaming-mvp \
  /usr/share/r46h-build
install -o root -g root -m 0644 "$PAYLOAD/files/r46h-smoke-libretro.so" \
  /usr/local/libexec/r46h-smoke-libretro.so
install -o root -g root -m 0644 "$PAYLOAD/files/r46h-nes-smoke.nes" \
  /usr/local/share/r46h/r46h-nes-smoke.nes
install -o root -g root -m 0755 "$PAYLOAD/files/r46h-game-ui" \
  /usr/local/sbin/r46h-game-ui
install -o root -g root -m 0755 "$PAYLOAD/files/r46h-input-bridge" \
  /usr/local/libexec/r46h-input-bridge
install -o root -g root -m 0755 "$PAYLOAD/files/r46h-gaming-input-ready" \
  /usr/local/libexec/r46h-gaming-input-ready
install -o root -g root -m 0755 "$PAYLOAD/files/r46h-storage-audit" \
  /usr/local/sbin/r46h-storage-audit
install -o root -g root -m 0755 "$PAYLOAD/files/r46h-gaming-frontend-condition" \
  /usr/local/libexec/r46h-gaming-frontend-condition
install -o root -g root -m 0644 "$PAYLOAD/files/r46h-gaming-input.service" \
  /etc/systemd/system/r46h-gaming-input.service
install -o root -g root -m 0644 "$PAYLOAD/files/r46h-gaming-frontend.service" \
  /etc/systemd/system/r46h-gaming-frontend.service
install -o root -g root -m 0644 "$PAYLOAD/files/GAMING-PRODUCT.md" \
  /usr/share/doc/r46h-gaming-mvp/GAMING-PRODUCT.md
install -o root -g root -m 0644 "$PAYLOAD/PACKAGES.tsv" \
  /usr/share/r46h-build/GAMING-PACKAGES.tsv

install -d -o root -g root -m 0755 /roms
for directory in nes gb gba nds; do
  install -d -o ark -g ark -m 0755 "/roms/$directory"
done
install -o ark -g ark -m 0644 "$PAYLOAD/files/r46h-nes-smoke.nes" \
  /roms/nes/r46h-nes-smoke.nes
install -d -o ark -g ark -m 0700 \
  /home/ark/.local /home/ark/.local/share /home/ark/.local/share/retroarch \
  /home/ark/.local/share/retroarch/playlists \
  /home/ark/.local/share/retroarch/saves \
  /home/ark/.local/share/retroarch/states
install -o root -g root -m 0644 "$PAYLOAD/files/retroarch.cfg" /etc/r46h/retroarch.cfg

systemctl enable r46h-gaming-input.service
systemctl enable r46h-gaming-frontend.service
[[ "$(systemctl is-enabled r46h-gaming-input.service)" == enabled ]] || \
  die 'gaming input was not enabled'
[[ "$(systemctl is-enabled r46h-gaming-frontend.service)" == enabled ]] || \
  die 'gaming frontend was not enabled'

update-alternatives --set regulatory.db /lib/firmware/regulatory.db-upstream
[[ "$(readlink -f /lib/firmware/regulatory.db)" == \
  /usr/lib/firmware/regulatory.db-upstream ]] || die 'upstream regulatory database is not selected'
[[ "$(readlink -f /lib/firmware/regulatory.db.p7s)" == \
  /usr/lib/firmware/regulatory.db.p7s-upstream ]] || die 'upstream regulatory signature is not selected'

[[ "$(sha256sum "$FIRSTBOOT" | awk '{print $1}')" == "$BASE_FIRSTBOOT_SHA256" ]] || \
  die 'base firstboot helper mismatch'
firstboot_stage=/usr/libexec/.r46h-firstboot.gaming-v0.5
sed 's/debian13-p2-mvp-v0\.1/debian13-p2-gaming-v0.5/g' "$FIRSTBOOT" > "$firstboot_stage"
[[ "$(sha256sum "$firstboot_stage" | awk '{print $1}')" == "$FINAL_FIRSTBOOT_SHA256" ]] || \
  die 'composed firstboot helper mismatch'
install -o root -g root -m 0755 "$firstboot_stage" "$FIRSTBOOT"
rm -f -- "$firstboot_stage"

[[ "$(sha256sum "$ROOTFS_SMOKE" | awk '{print $1}')" == "$BASE_ROOTFS_SMOKE_SHA256" ]] || \
  die 'base rootfs smoke helper mismatch'
smoke_stage=/usr/local/sbin/.r46h-rootfs-smoke.gaming-v0.5
sed \
  -e 's/6\.12\.99-r46h-mainline-v0\.8-bootloader-handoff/6.12.99-r46h-mainline-v0.15-gaming-product/g' \
  -e 's/d3130001-46a4-4d56-9001-000000000001/d3130005-46a4-4d56-9001-000000000005/g' \
  -e 's/debian13-p2-mvp-v0\.1/debian13-p2-gaming-v0.5/g' \
  "$ROOTFS_SMOKE" > "$smoke_stage"
[[ "$(sha256sum "$smoke_stage" | awk '{print $1}')" == "$FINAL_ROOTFS_SMOKE_SHA256" ]] || \
  die 'composed rootfs smoke helper mismatch'
install -o root -g root -m 0755 "$smoke_stage" "$ROOTFS_SMOKE"
rm -f -- "$smoke_stage"

receipt_stage=/var/lib/r46h/.gaming-mvp-v0.4-installed.compose
printf 'payload_id=r46h-gaming-mvp-v0.4\ntarget_release=%s\npackage_manifest_sha256=%s\npayload_sha256sums_sha256=%s\n' \
  "$KERNEL_RELEASE" "$GAMING_PACKAGE_MANIFEST_SHA256" \
  "$GAMING_PAYLOAD_SHA256SUMS_SHA256" > "$receipt_stage"
chmod 0600 "$receipt_stage"
[[ "$(sha256sum "$receipt_stage" | awk '{print $1}')" == "$GAMING_RECEIPT_SHA256" ]] || \
  die 'generated gaming receipt mismatch'
mv -f -- "$receipt_stage" "$GAMING_RECEIPT"

rootfs_receipt_stage=/usr/share/r46h-build/.CONSOLIDATED-RECEIPT
cat > "$rootfs_receipt_stage" <<EOF
artifact_id=$ARTIFACT_ID
source_git_commit=$SOURCE_GIT_COMMIT
build_inputs_git_dirty=false
base_image_id=$BASE_IMAGE_ID
v08_fallback_release=6.12.99-r46h-mainline-v0.8-bootloader-handoff
v08_fallback_bundle_sha256=$V08_FALLBACK_BUNDLE_SHA256
v08_fallback_module_tree_sha256=$V08_FALLBACK_MODULE_TREE_SHA256
v10_fallback_release=6.12.99-r46h-mainline-v0.10-adc-full-range
v10_fallback_bundle_sha256=$V10_FALLBACK_BUNDLE_SHA256
v10_fallback_module_tree_sha256=$V10_FALLBACK_MODULE_TREE_SHA256
kernel_release=$KERNEL_RELEASE
kernel_bundle_sha256=$KERNEL_BUNDLE_SHA256
kernel_source_commit=$KERNEL_SOURCE_COMMIT
kernel_source_snapshot_sha256=$KERNEL_SOURCE_SNAPSHOT_SHA256
kernel_module_tree_sha256=$KERNEL_MODULE_TREE_SHA256
kernel_image_sha256=$KERNEL_IMAGE_SHA256
kernel_dtb_sha256=$KERNEL_DTB_SHA256
product_kernel_directory=$PRODUCT_KERNEL_DIRECTORY
product_uboot_commands_sha256=$PRODUCT_UBOOT_COMMANDS_SHA256
product_kernel_boot_mode=p2-one-shot-no-saveenv
gaming_payload_id=r46h-gaming-mvp-v0.4
gaming_archive_sha256=$GAMING_ARCHIVE_SHA256
gaming_package_manifest_sha256=$GAMING_PACKAGE_MANIFEST_SHA256
gaming_payload_sha256sums_sha256=$GAMING_PAYLOAD_SHA256SUMS_SHA256
game_ui_sha256=$GAME_UI_SHA256
smoke_core_sha256=$SMOKE_CORE_SHA256
storage_audit_sha256=$STORAGE_AUDIT_SHA256
retroarch_config_sha256=$RETROARCH_CONFIG_SHA256
nes_smoke_sha256=$NES_SMOKE_SHA256
regdb_alternative=/usr/lib/firmware/regulatory.db-upstream
personal_authorized_keys=absent
diagnostic_input_bridge=absent
product_input_bridge=r46h-gaming-input-bridge-v0.5
EOF
install -o root -g root -m 0444 "$rootfs_receipt_stage" "$ROOTFS_RECEIPT"
rm -f -- "$rootfs_receipt_stage"

[[ "$(sha256sum /roms/nes/r46h-nes-smoke.nes | awk '{print $1}')" == "$NES_SMOKE_SHA256" ]] || \
  die 'installed NES smoke ROM mismatch'
[[ "$(sha256sum /etc/r46h/retroarch.cfg | awk '{print $1}')" == \
  "$RETROARCH_CONFIG_SHA256" ]] || die 'installed RetroArch product config mismatch'
[[ "$(sha256sum /usr/local/sbin/r46h-game-ui | awk '{print $1}')" == \
  "$GAME_UI_SHA256" ]] || die 'installed game UI hotfix mismatch'
[[ "$(sha256sum /usr/local/libexec/r46h-smoke-libretro.so | awk '{print $1}')" == \
  "$SMOKE_CORE_SHA256" ]] || die 'installed smoke core hotfix mismatch'
[[ "$(sha256sum /usr/local/sbin/r46h-storage-audit | awk '{print $1}')" == \
  "$STORAGE_AUDIT_SHA256" ]] || die 'installed storage audit hotfix mismatch'
[[ "$(/usr/local/libexec/r46h-input-bridge --version)" == \
  r46h-gaming-input-bridge-v0.5 ]] || die 'product input bridge version mismatch'
grep -Fqx 'input_enable_hotkey_btn = "8"' /etc/r46h/retroarch.cfg || \
  die 'Select hotkey binding is missing'
grep -Fqx 'input_menu_toggle_btn = "2"' /etc/r46h/retroarch.cfg || \
  die 'Select+X RGUI binding is missing'
[[ "$(stat -c '%u:%g:%a:%h' /roms/nes/r46h-nes-smoke.nes)" == 1000:1000:644:1 ]] || \
  die 'installed NES smoke ROM identity mismatch'
[[ "$(stat -c '%u:%g:%a' /home/ark/.local/share/retroarch)" == 1000:1000:700 ]] || \
  die 'RetroArch state root identity mismatch'
[[ ! -e /home/ark/.ssh/authorized_keys && ! -L /home/ark/.ssh/authorized_keys ]] || \
  die 'personal authorized_keys leaked into consolidated image'
for forbidden in \
  /var/lib/r46h/rom-workflow-v0.1-installed \
  /var/lib/r46h/gaming-history-v0.2-installed \
  /usr/local/sbin/r46h-gaming-history-rollback \
  /usr/local/libexec/r46h-gaming-input-bridge \
  /etc/systemd/system/r46h-gaming-input-bridge.service; do
  [[ ! -e "$forbidden" && ! -L "$forbidden" ]] || die "forbidden preinstalled state: $forbidden"
done

rm -rf -- "$EVIDENCE"
install -d -o root -g root -m 0700 "$EVIDENCE"
install -o root -g root -m 0600 /run/r46h-gaming-payload-verify.txt \
  "$EVIDENCE/GAMING-PAYLOAD-VERIFY.txt"
rm -f -- /run/r46h-gaming-payload-verify.txt
systemd-analyze verify /etc/systemd/system/r46h-gaming-input.service \
  /etc/systemd/system/r46h-gaming-frontend.service \
  > "$EVIDENCE/GAMING-SYSTEMD-VERIFY.txt" 2>&1
retroarch --features > "$EVIDENCE/RETROARCH-FEATURES.txt"
for feature in \
  'KMS             - Video context driver: yes' \
  'OpenGLES        - Video driver: yes' \
  'EGL             - Video context driver: yes' \
  'ALSA            - Audio driver: yes' \
  'UDEV            - UDEV/EVDEV input driver: yes'; do
  grep -Fq "$feature" "$EVIDENCE/RETROARCH-FEATURES.txt" || die "missing RetroArch feature: $feature"
done
file /usr/local/libexec/r46h-smoke-libretro.so > "$EVIDENCE/SMOKE-CORE-FILE.txt"
grep -Eq 'ELF 64-bit.*ARM aarch64' "$EVIDENCE/SMOKE-CORE-FILE.txt" || \
  die 'smoke core is not AArch64'
ldd /usr/bin/retroarch > "$EVIDENCE/RETROARCH-LDD.txt"
! grep -Eiq 'not found|libMali' "$EVIDENCE/RETROARCH-LDD.txt" || \
  die 'RetroArch dependency validation failed'
printf '%s\n' 'video_driver = "null"' 'audio_driver = "null"' \
  'input_driver = "null"' > "$NULL_CONFIG"
set +e
timeout -s TERM -k 1 3 retroarch --verbose --config "$NULL_CONFIG" \
  -L /usr/local/libexec/r46h-smoke-libretro.so \
  > "$EVIDENCE/SMOKE-CORE-LOAD.txt" 2>&1
smoke_status=$?
timeout -s TERM -k 1 3 retroarch --verbose --config "$NULL_CONFIG" \
  -L /usr/lib/aarch64-linux-gnu/libretro/nestopia_libretro.so \
  /roms/nes/r46h-nes-smoke.nes > "$EVIDENCE/NESTOPIA-ROM-LOAD.txt" 2>&1
nestopia_status=$?
set -e
rm -f -- "$NULL_CONFIG"
[[ "$smoke_status" == 124 ]] || die "smoke core load returned $smoke_status"
[[ "$nestopia_status" == 124 ]] || die "Nestopia ROM load returned $nestopia_status"
grep -Fq 'R46H Hardware Smoke' "$EVIDENCE/SMOKE-CORE-LOAD.txt" || die 'smoke core did not load'
grep -Fq 'Nestopia' "$EVIDENCE/NESTOPIA-ROM-LOAD.txt" || die 'Nestopia did not load'
! grep -Fq '[ERROR] [Content]' "$EVIDENCE/NESTOPIA-ROM-LOAD.txt" || die 'Nestopia rejected smoke ROM'

apt-get clean
rm -rf -- /var/lib/apt/lists/* /var/cache/apt/archives/*.deb
for log in /var/log/alternatives.log /var/log/apt/eipp.log.xz /var/log/apt/history.log \
  /var/log/apt/term.log /var/log/dpkg.log; do
  if [[ -e "$log" && ! -L "$log" ]]; then
    : > "$log"
  fi
done
rm -f -- /var/lib/r46h/firstboot-complete

printf 'R46H_GAMING_COMPOSE result=pass artifact=%s kernel=%s gaming=r46h-gaming-mvp-v0.4 retroarch_config=%s credentials=absent diagnostic_input_bridge=absent product_input_bridge=v0.5\n' \
  "$ARTIFACT_ID" "$KERNEL_RELEASE" "$RETROARCH_CONFIG_SHA256"
