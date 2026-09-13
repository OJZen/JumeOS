#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

readonly ROOTFS_TAR=/input/rootfs.tar
readonly V08_FALLBACK_BUNDLE=/input/r46h-mainline-test-v0.8-bootloader-handoff.tar.gz
readonly V10_FALLBACK_BUNDLE=/input/r46h-mainline-test-v0.10-adc-full-range.tar.gz
readonly KERNEL_BUNDLE=/input/r46h-mainline-test-v0.15-gaming-product.tar.gz
readonly ROOTFS=/work/rootfs
readonly V08_FALLBACK_STAGE=/work/kernel-v08
readonly V10_FALLBACK_STAGE=/work/kernel-v10
readonly KERNEL_STAGE=/work/kernel-v15
readonly PRIVATE_V08_FALLBACK_BUNDLE=/work/v08-fallback-kernel-bundle.tar.gz
readonly PRIVATE_V10_FALLBACK_BUNDLE=/work/v10-fallback-kernel-bundle.tar.gz
readonly PRIVATE_KERNEL_BUNDLE=/work/kernel-bundle.tar.gz
readonly V08_FALLBACK_DIRECTORY=r46h-mainline-test-v0.8-bootloader-handoff
readonly V10_FALLBACK_DIRECTORY=r46h-mainline-test-v0.10-adc-full-range
readonly KERNEL_DIRECTORY=r46h-mainline-test-v0.15-gaming-product
readonly V08_FALLBACK_RELEASE=6.12.99-r46h-mainline-v0.8-bootloader-handoff
readonly V10_FALLBACK_RELEASE=6.12.99-r46h-mainline-v0.10-adc-full-range
readonly COMPOSE_EVIDENCE_REL=usr/share/r46h-build/.gaming-compose-evidence
readonly PRODUCT_UBOOT_SOURCE=/source/mainline/rootfs-debian13-gaming/UBOOT-CMDS.product

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

for name in IMAGE_NAME PARTITION_SIZE FS_BLOCK_SIZE FS_BLOCK_COUNT FS_TAIL_SIZE FS_UUID FS_LABEL \
  KERNEL_RELEASE V08_FALLBACK_BUNDLE_SHA256 V08_FALLBACK_MODULE_TREE_SHA256 \
  V10_FALLBACK_BUNDLE_SHA256 V10_FALLBACK_MODULE_TREE_SHA256 \
  KERNEL_BUNDLE_SHA256 SOURCE_DATE_EPOCH ARTIFACT_ID \
  KERNEL_SOURCE_COMMIT KERNEL_SOURCE_SNAPSHOT_SHA256 KERNEL_MODULE_TREE_SHA256 \
  KERNEL_IMAGE_SIZE KERNEL_IMAGE_SHA256 KERNEL_DTB_SIZE KERNEL_DTB_SHA256 \
  PRODUCT_KERNEL_DIRECTORY PRODUCT_UBOOT_COMMANDS_SHA256 \
  GAMING_RECEIPT_SHA256 RETROARCH_CONFIG_SHA256 NES_SMOKE_SHA256 \
  GAME_UI_SHA256 SMOKE_CORE_SHA256 STORAGE_AUDIT_SHA256 \
  FINAL_FIRSTBOOT_SHA256 FINAL_ROOTFS_SMOKE_SHA256; do
  [[ -n "${!name:-}" ]] || die "missing environment: $name"
done
[[ "$PARTITION_SIZE" =~ ^[1-9][0-9]*$ ]] || die 'invalid partition size'
[[ "$FS_BLOCK_SIZE" == 4096 && "$FS_BLOCK_COUNT" =~ ^[1-9][0-9]*$ ]] || \
  die 'invalid ext4 geometry'
[[ "$FS_TAIL_SIZE" == 512 ]] || die 'invalid ext4 tail size'
(( FS_BLOCK_SIZE * FS_BLOCK_COUNT + FS_TAIL_SIZE == PARTITION_SIZE )) || \
  die 'ext4 geometry does not cover p2 exactly'
[[ "$KERNEL_BUNDLE_SHA256" =~ ^[0-9a-f]{64}$ ]] || die 'invalid kernel bundle hash'
[[ "$SOURCE_DATE_EPOCH" =~ ^[1-9][0-9]*$ ]] || die 'invalid source epoch'
[[ "$KERNEL_RELEASE" == 6.12.99-r46h-mainline-v0.15-gaming-product ]] || \
  die 'unexpected product kernel release'
[[ "$KERNEL_SOURCE_COMMIT" =~ ^[0-9a-f]{40}$ ]] || die 'invalid product kernel source commit'
[[ "$KERNEL_IMAGE_SIZE" =~ ^[1-9][0-9]*$ && "$KERNEL_DTB_SIZE" =~ ^[1-9][0-9]*$ ]] || \
  die 'invalid product kernel file size'
[[ "$PRODUCT_KERNEL_DIRECTORY" == \
  /var/lib/r46h-gaming-product-kernel/v0.15-gaming-product ]] || \
  die 'unexpected product kernel directory'
for name in KERNEL_SOURCE_SNAPSHOT_SHA256 KERNEL_MODULE_TREE_SHA256 KERNEL_IMAGE_SHA256 \
  KERNEL_DTB_SHA256 PRODUCT_UBOOT_COMMANDS_SHA256 RETROARCH_CONFIG_SHA256 \
  V08_FALLBACK_BUNDLE_SHA256 V08_FALLBACK_MODULE_TREE_SHA256 \
  V10_FALLBACK_BUNDLE_SHA256 V10_FALLBACK_MODULE_TREE_SHA256 \
  GAME_UI_SHA256 SMOKE_CORE_SHA256 STORAGE_AUDIT_SHA256; do
  [[ "${!name}" =~ ^[0-9a-f]{64}$ ]] || die "invalid hash: $name"
done
[[ -f "$ROOTFS_TAR" && ! -L "$ROOTFS_TAR" ]] || die 'rootfs export is missing'
[[ -f "$V08_FALLBACK_BUNDLE" && ! -L "$V08_FALLBACK_BUNDLE" ]] || \
  die 'v0.8 fallback kernel bundle is missing'
[[ -f "$V10_FALLBACK_BUNDLE" && ! -L "$V10_FALLBACK_BUNDLE" ]] || \
  die 'v0.10 fallback kernel bundle is missing'
[[ -f "$KERNEL_BUNDLE" && ! -L "$KERNEL_BUNDLE" ]] || die 'kernel bundle is missing'
[[ -f "$PRODUCT_UBOOT_SOURCE" && ! -L "$PRODUCT_UBOOT_SOURCE" ]] || \
  die 'product U-Boot commands are missing'
[[ ! -e "/output/$IMAGE_NAME" ]] || die 'output image already exists'

rm -rf -- "$ROOTFS" "$V08_FALLBACK_STAGE" "$V10_FALLBACK_STAGE" "$KERNEL_STAGE"
install -d -m 0755 "$ROOTFS" "$V08_FALLBACK_STAGE" "$V10_FALLBACK_STAGE" "$KERNEL_STAGE"
rm -f -- "$PRIVATE_V08_FALLBACK_BUNDLE"
cp -- "$V08_FALLBACK_BUNDLE" "$PRIVATE_V08_FALLBACK_BUNDLE"
chmod 0400 "$PRIVATE_V08_FALLBACK_BUNDLE"
printf '%s  %s\n' "$V08_FALLBACK_BUNDLE_SHA256" "$PRIVATE_V08_FALLBACK_BUNDLE" | \
  sha256sum -c -
rm -f -- "$PRIVATE_V10_FALLBACK_BUNDLE"
cp -- "$V10_FALLBACK_BUNDLE" "$PRIVATE_V10_FALLBACK_BUNDLE"
chmod 0400 "$PRIVATE_V10_FALLBACK_BUNDLE"
printf '%s  %s\n' "$V10_FALLBACK_BUNDLE_SHA256" "$PRIVATE_V10_FALLBACK_BUNDLE" | \
  sha256sum -c -
rm -f -- "$PRIVATE_KERNEL_BUNDLE"
cp -- "$KERNEL_BUNDLE" "$PRIVATE_KERNEL_BUNDLE"
chmod 0400 "$PRIVATE_KERNEL_BUNDLE"
printf '%s  %s\n' "$KERNEL_BUNDLE_SHA256" "$PRIVATE_KERNEL_BUNDLE" | sha256sum -c -

tar --numeric-owner -xf "$ROOTFS_TAR" -C "$ROOTFS"
tar --numeric-owner -xzf "$PRIVATE_V08_FALLBACK_BUNDLE" -C "$V08_FALLBACK_STAGE"
tar --numeric-owner -xzf "$PRIVATE_V10_FALLBACK_BUNDLE" -C "$V10_FALLBACK_STAGE"
tar --numeric-owner -xzf "$PRIVATE_KERNEL_BUNDLE" -C "$KERNEL_STAGE"
if [[ -e "$ROOTFS/.dockerenv" || -L "$ROOTFS/.dockerenv" ]]; then
  [[ -f "$ROOTFS/.dockerenv" && ! -L "$ROOTFS/.dockerenv" ]] || \
    die 'unsafe Docker runtime marker in rootfs export'
  rm -f -- "$ROOTFS/.dockerenv"
fi
[[ ! -e "$ROOTFS/.dockerenv" && ! -L "$ROOTFS/.dockerenv" ]] || \
  die 'Docker runtime marker remains in hardware rootfs'

mapfile -t v08_fallback_top_entries < <(
  find "$V08_FALLBACK_STAGE" -mindepth 1 -maxdepth 1 -printf '%f\n'
)
[[ "${#v08_fallback_top_entries[@]}" == 1 && \
   "${v08_fallback_top_entries[0]}" == "$V08_FALLBACK_DIRECTORY" ]] || \
  die 'v0.8 fallback kernel bundle has an unexpected top-level layout'
V08_FALLBACK_ROOT=$V08_FALLBACK_STAGE/$V08_FALLBACK_DIRECTORY
[[ -d "$V08_FALLBACK_ROOT" && ! -L "$V08_FALLBACK_ROOT" ]] || \
  die 'v0.8 fallback kernel bundle root is unsafe'
(
  cd "$V08_FALLBACK_ROOT"
  sha256sum -c SHA256SUMS
) > /output/V08-KERNEL-BUNDLE-VERIFY.txt
grep -Fqx "kernel_release=$V08_FALLBACK_RELEASE" "$V08_FALLBACK_ROOT/MANIFEST" || \
  die 'v0.8 fallback kernel release mismatch'
grep -Fqx 'module_count=1276' "$V08_FALLBACK_ROOT/MANIFEST" || \
  die 'v0.8 fallback kernel module count mismatch'
grep -Fqx "module_tree_sha256=$V08_FALLBACK_MODULE_TREE_SHA256" \
  "$V08_FALLBACK_ROOT/MANIFEST" || die 'v0.8 fallback module tree mismatch'

mapfile -t v10_fallback_top_entries < <(
  find "$V10_FALLBACK_STAGE" -mindepth 1 -maxdepth 1 -printf '%f\n'
)
[[ "${#v10_fallback_top_entries[@]}" == 1 && \
   "${v10_fallback_top_entries[0]}" == "$V10_FALLBACK_DIRECTORY" ]] || \
  die 'v0.10 fallback kernel bundle has an unexpected top-level layout'
V10_FALLBACK_ROOT=$V10_FALLBACK_STAGE/$V10_FALLBACK_DIRECTORY
[[ -d "$V10_FALLBACK_ROOT" && ! -L "$V10_FALLBACK_ROOT" ]] || \
  die 'v0.10 fallback kernel bundle root is unsafe'
(
  cd "$V10_FALLBACK_ROOT"
  sha256sum -c SHA256SUMS
) > /output/V10-KERNEL-BUNDLE-VERIFY.txt
grep -Fqx "kernel_release=$V10_FALLBACK_RELEASE" "$V10_FALLBACK_ROOT/MANIFEST" || \
  die 'v0.10 fallback kernel release mismatch'
grep -Fqx 'module_count=1276' "$V10_FALLBACK_ROOT/MANIFEST" || \
  die 'v0.10 fallback kernel module count mismatch'
grep -Fqx "module_tree_sha256=$V10_FALLBACK_MODULE_TREE_SHA256" \
  "$V10_FALLBACK_ROOT/MANIFEST" || die 'v0.10 fallback module tree mismatch'

mapfile -t kernel_top_entries < <(find "$KERNEL_STAGE" -mindepth 1 -maxdepth 1 -printf '%f\n')
[[ "${#kernel_top_entries[@]}" == 1 && "${kernel_top_entries[0]}" == "$KERNEL_DIRECTORY" ]] || \
  die 'kernel bundle has an unexpected top-level layout'
KERNEL_ROOT=$KERNEL_STAGE/$KERNEL_DIRECTORY
[[ -d "$KERNEL_ROOT" && ! -L "$KERNEL_ROOT" ]] || die 'kernel bundle root is unsafe'
(
  cd "$KERNEL_ROOT"
  sha256sum -c SHA256SUMS
) > /output/KERNEL-BUNDLE-VERIFY.txt
grep -Fqx "kernel_release=$KERNEL_RELEASE" "$KERNEL_ROOT/MANIFEST" || \
  die 'kernel release mismatch'
grep -Fqx 'module_count=1276' "$KERNEL_ROOT/MANIFEST" || die 'kernel module count mismatch'
grep -Fqx 'build_id=v0.15-gaming-product' "$KERNEL_ROOT/MANIFEST" || \
  die 'product kernel build identity mismatch'
grep -Fqx "source_git_commit=$KERNEL_SOURCE_COMMIT" "$KERNEL_ROOT/MANIFEST" || \
  die 'product kernel source commit mismatch'
grep -Fqx "source_snapshot_sha256=$KERNEL_SOURCE_SNAPSHOT_SHA256" \
  "$KERNEL_ROOT/MANIFEST" || die 'product kernel source snapshot mismatch'
grep -Fqx "module_tree_sha256=$KERNEL_MODULE_TREE_SHA256" "$KERNEL_ROOT/MANIFEST" || \
  die 'product kernel module tree mismatch'
[[ "$(stat -c %s "$KERNEL_ROOT/boot/Image.mainline-test")" == "$KERNEL_IMAGE_SIZE" ]] || \
  die 'product kernel Image size mismatch'
[[ "$(sha256sum "$KERNEL_ROOT/boot/Image.mainline-test" | awk '{print $1}')" == \
  "$KERNEL_IMAGE_SHA256" ]] || die 'product kernel Image hash mismatch'
[[ "$(stat -c %s "$KERNEL_ROOT/boot/rk3326-r46h-mainline-test.dtb")" == \
  "$KERNEL_DTB_SIZE" ]] || die 'product kernel DTB size mismatch'
[[ "$(sha256sum "$KERNEL_ROOT/boot/rk3326-r46h-mainline-test.dtb" | awk '{print $1}')" == \
  "$KERNEL_DTB_SHA256" ]] || die 'product kernel DTB hash mismatch'
[[ "$(sha256sum "$PRODUCT_UBOOT_SOURCE" | awk '{print $1}')" == \
  "$PRODUCT_UBOOT_COMMANDS_SHA256" ]] || die 'product U-Boot command hash mismatch'
rm -rf -- "$ROOTFS/lib/modules/$V08_FALLBACK_RELEASE"
rm -rf -- "$ROOTFS/lib/modules/$V10_FALLBACK_RELEASE"
rm -rf -- "$ROOTFS/lib/modules/$KERNEL_RELEASE"
install -d -m 0755 "$ROOTFS/lib/modules"
cp -a -- "$V08_FALLBACK_ROOT/rootfs/lib/modules/$V08_FALLBACK_RELEASE" \
  "$ROOTFS/lib/modules/"
cp -a -- "$V10_FALLBACK_ROOT/rootfs/lib/modules/$V10_FALLBACK_RELEASE" \
  "$ROOTFS/lib/modules/"
cp -a -- "$KERNEL_ROOT/rootfs/lib/modules/$KERNEL_RELEASE" "$ROOTFS/lib/modules/"
test -f "$ROOTFS/lib/modules/$V08_FALLBACK_RELEASE/modules.dep" || \
  die 'accepted v0.8 fallback modules are missing'
test -f "$ROOTFS/lib/modules/$V10_FALLBACK_RELEASE/modules.dep" || \
  die 'accepted v0.10 fallback modules are missing'
test -f "$ROOTFS/lib/modules/$KERNEL_RELEASE/modules.dep" || \
  die 'v0.15 product module dependency file is missing'

product_kernel_rel=${PRODUCT_KERNEL_DIRECTORY#/}
install -d -o root -g root -m 0700 "$ROOTFS/var/lib/r46h-gaming-product-kernel"
install -d -o root -g root -m 0700 "$ROOTFS/$product_kernel_rel"
install -o root -g root -m 0400 "$KERNEL_ROOT/boot/Image.mainline-test" \
  "$ROOTFS/$product_kernel_rel/IMAGE"
install -o root -g root -m 0400 "$KERNEL_ROOT/boot/rk3326-r46h-mainline-test.dtb" \
  "$ROOTFS/$product_kernel_rel/R46H.DTB"
install -o root -g root -m 0400 "$PRODUCT_UBOOT_SOURCE" \
  "$ROOTFS/$product_kernel_rel/UBOOT-CMDS.txt"
cat > "$ROOTFS/$product_kernel_rel/RECEIPT" <<EOF
kernel_release=$KERNEL_RELEASE
kernel_bundle_sha256=$KERNEL_BUNDLE_SHA256
kernel_source_commit=$KERNEL_SOURCE_COMMIT
kernel_source_snapshot_sha256=$KERNEL_SOURCE_SNAPSHOT_SHA256
kernel_module_tree_sha256=$KERNEL_MODULE_TREE_SHA256
image_size=$KERNEL_IMAGE_SIZE
image_sha256=$KERNEL_IMAGE_SHA256
dtb_size=$KERNEL_DTB_SIZE
dtb_sha256=$KERNEL_DTB_SHA256
uboot_commands_sha256=$PRODUCT_UBOOT_COMMANDS_SHA256
boot_mode=p2-one-shot-no-saveenv
EOF
chmod 0400 "$ROOTFS/$product_kernel_rel/RECEIPT"
(
  cd "$ROOTFS"
  sha256sum \
    "$product_kernel_rel/IMAGE" \
    "$product_kernel_rel/R46H.DTB" \
    "$product_kernel_rel/UBOOT-CMDS.txt"
) > /output/PRODUCT-KERNEL-FILES.sha256

for directory in dev proc sys run tmp; do
  find "$ROOTFS/$directory" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
done
chmod 1777 "$ROOTFS/tmp"
chmod 0755 "$ROOTFS/dev" "$ROOTFS/proc" "$ROOTFS/sys" "$ROOTFS/run"
rm -f -- "$ROOTFS/usr/local/libexec/r46h-build-ext4-in-container"
rm -f -- "$ROOTFS/etc/ssh"/ssh_host_* "$ROOTFS/var/lib/dbus/machine-id"
: > "$ROOTFS/etc/machine-id"
ln -s /etc/machine-id "$ROOTFS/var/lib/dbus/machine-id"
install -m 0644 "$ROOTFS/usr/share/r46h-build/rootfs-config/hostname" "$ROOTFS/etc/hostname"
install -m 0644 "$ROOTFS/usr/share/r46h-build/rootfs-config/hosts" "$ROOTFS/etc/hosts"
rm -f -- "$ROOTFS/etc/resolv.conf"
ln -s /run/NetworkManager/resolv.conf "$ROOTFS/etc/resolv.conf"

cmp -s "$ROOTFS/etc/hostname" "$ROOTFS/usr/share/r46h-build/rootfs-config/hostname" || \
  die 'hostname was not restored after Docker export'
cmp -s "$ROOTFS/etc/hosts" "$ROOTFS/usr/share/r46h-build/rootfs-config/hosts" || \
  die 'hosts file was not restored after Docker export'
[[ "$(readlink "$ROOTFS/etc/resolv.conf")" == /run/NetworkManager/resolv.conf ]] || \
  die 'resolver symlink was not restored after Docker export'
[[ "$(readlink "$ROOTFS/etc/localtime")" == /usr/share/zoneinfo/Asia/Shanghai ]] || \
  die 'timezone symlink mismatch'
[[ "$(readlink "$ROOTFS/etc/systemd/system/systemd-firstboot.service")" == /dev/null ]] || \
  die 'interactive vendor firstboot service is not masked'

test -x "$ROOTFS/usr/local/sbin/r46h-rootfs-smoke" || die 'rootfs smoke tool is missing'
test -x "$ROOTFS/usr/local/sbin/r46h-game-ui" || die 'gaming runner is missing'
test -x "$ROOTFS/usr/local/libexec/r46h-gaming-frontend-condition" || \
  die 'gaming frontend condition is missing'
test -x "$ROOTFS/usr/local/libexec/r46h-input-bridge" || die 'product input bridge is missing'
test -x "$ROOTFS/usr/local/libexec/r46h-gaming-input-ready" || \
  die 'gaming input readiness helper is missing'
test -x "$ROOTFS/usr/local/sbin/r46h-storage-audit" || die 'storage audit is missing'
test -f "$ROOTFS/usr/local/libexec/r46h-smoke-libretro.so" || die 'gaming smoke core is missing'
test -f "$ROOTFS/usr/lib/aarch64-linux-gnu/libretro/nestopia_libretro.so" || \
  die 'Nestopia core is missing'
test -f "$ROOTFS/usr/lib/aarch64-linux-gnu/dri/panfrost_dri.so" || die 'Panfrost DRI is missing'
test "$(stat -c %a "$ROOTFS/usr/bin/sudo")" == 4755 || die 'sudo lost setuid mode'
[[ "$(sha256sum "$ROOTFS/usr/libexec/r46h-firstboot" | awk '{print $1}')" == \
  "$FINAL_FIRSTBOOT_SHA256" ]] || die 'firstboot helper identity mismatch'
[[ "$(sha256sum "$ROOTFS/usr/local/sbin/r46h-rootfs-smoke" | awk '{print $1}')" == \
  "$FINAL_ROOTFS_SMOKE_SHA256" ]] || die 'rootfs smoke helper identity mismatch'
[[ "$(sha256sum "$ROOTFS/etc/r46h/retroarch.cfg" | awk '{print $1}')" == \
  "$RETROARCH_CONFIG_SHA256" ]] || die 'RetroArch product configuration mismatch'
[[ "$(sha256sum "$ROOTFS/usr/local/sbin/r46h-game-ui" | awk '{print $1}')" == \
  "$GAME_UI_SHA256" ]] || die 'accepted game UI hotfix mismatch'
[[ "$(sha256sum "$ROOTFS/usr/local/libexec/r46h-smoke-libretro.so" | awk '{print $1}')" == \
  "$SMOKE_CORE_SHA256" ]] || die 'accepted smoke core hotfix mismatch'
[[ "$(sha256sum "$ROOTFS/usr/local/sbin/r46h-storage-audit" | awk '{print $1}')" == \
  "$STORAGE_AUDIT_SHA256" ]] || die 'accepted storage audit hotfix mismatch'
[[ "$(chroot "$ROOTFS" /usr/local/libexec/r46h-input-bridge --version)" == \
  r46h-gaming-input-bridge-v0.5 ]] || die 'product input bridge version mismatch'
[[ "$(sha256sum "$ROOTFS/var/lib/r46h/gaming-mvp-v0.4-installed" | awk '{print $1}')" == \
  "$GAMING_RECEIPT_SHA256" ]] || die 'gaming receipt mismatch'
[[ "$(stat -c '%u:%g:%a:%h' "$ROOTFS/$product_kernel_rel/IMAGE")" == 0:0:400:1 ]] || \
  die 'product kernel Image identity mismatch'
[[ "$(stat -c '%u:%g:%a:%h' "$ROOTFS/$product_kernel_rel/R46H.DTB")" == 0:0:400:1 ]] || \
  die 'product kernel DTB identity mismatch'
[[ "$(stat -c '%u:%g:%a:%h' "$ROOTFS/$product_kernel_rel/UBOOT-CMDS.txt")" == \
  0:0:400:1 ]] || die 'product U-Boot command identity mismatch'
[[ "$(sha256sum "$ROOTFS/roms/nes/r46h-nes-smoke.nes" | awk '{print $1}')" == \
  "$NES_SMOKE_SHA256" ]] || die 'NES smoke ROM mismatch'
[[ "$(stat -c '%u:%g:%a:%h' "$ROOTFS/roms/nes/r46h-nes-smoke.nes")" == 1000:1000:644:1 ]] || \
  die 'NES smoke ROM identity mismatch'
[[ "$(stat -c '%u:%g:%a' "$ROOTFS/home/ark/.local/share/retroarch")" == 1000:1000:700 ]] || \
  die 'RetroArch state root identity mismatch'
[[ "$(chroot "$ROOTFS" readlink -f /lib/firmware/regulatory.db)" == \
  /usr/lib/firmware/regulatory.db-upstream ]] || die 'regulatory database selection mismatch'
[[ "$(chroot "$ROOTFS" readlink -f /lib/firmware/regulatory.db.p7s)" == \
  /usr/lib/firmware/regulatory.db.p7s-upstream ]] || \
  die 'regulatory signature selection mismatch'
[[ ! -e "$ROOTFS/home/ark/.ssh/authorized_keys" && \
   ! -L "$ROOTFS/home/ark/.ssh/authorized_keys" ]] || die 'personal authorized_keys leaked into image'
for forbidden in \
  var/lib/r46h/rom-workflow-v0.1-installed \
  var/lib/r46h/gaming-history-v0.2-installed \
  usr/local/sbin/r46h-gaming-history-rollback \
  usr/local/libexec/r46h-gaming-input-bridge \
  etc/systemd/system/r46h-gaming-input-bridge.service; do
  [[ ! -e "$ROOTFS/$forbidden" && ! -L "$ROOTFS/$forbidden" ]] || \
    die "forbidden preinstalled state: /$forbidden"
done
grep -Fqx "artifact_id=$ARTIFACT_ID" "$ROOTFS/usr/share/r46h-build/CONSOLIDATED-RECEIPT" || \
  die 'consolidated receipt identity mismatch'
grep -Fqx "kernel_release=$KERNEL_RELEASE" "$ROOTFS/usr/share/r46h-build/CONSOLIDATED-RECEIPT" || \
  die 'consolidated receipt kernel mismatch'
grep -Fqx "v08_fallback_bundle_sha256=$V08_FALLBACK_BUNDLE_SHA256" \
  "$ROOTFS/usr/share/r46h-build/CONSOLIDATED-RECEIPT" || \
  die 'consolidated receipt v0.8 fallback mismatch'
grep -Fqx "v08_fallback_module_tree_sha256=$V08_FALLBACK_MODULE_TREE_SHA256" \
  "$ROOTFS/usr/share/r46h-build/CONSOLIDATED-RECEIPT" || \
  die 'consolidated receipt v0.8 module tree mismatch'
grep -Fqx "v10_fallback_bundle_sha256=$V10_FALLBACK_BUNDLE_SHA256" \
  "$ROOTFS/usr/share/r46h-build/CONSOLIDATED-RECEIPT" || \
  die 'consolidated receipt v0.10 fallback mismatch'
grep -Fqx "v10_fallback_module_tree_sha256=$V10_FALLBACK_MODULE_TREE_SHA256" \
  "$ROOTFS/usr/share/r46h-build/CONSOLIDATED-RECEIPT" || \
  die 'consolidated receipt v0.10 module tree mismatch'
grep -Fqx 'personal_authorized_keys=absent' "$ROOTFS/usr/share/r46h-build/CONSOLIDATED-RECEIPT" || \
  die 'consolidated receipt credential boundary mismatch'
grep -Fqx 'diagnostic_input_bridge=absent' "$ROOTFS/usr/share/r46h-build/CONSOLIDATED-RECEIPT" || \
  die 'consolidated receipt input boundary mismatch'
grep -Fqx 'product_input_bridge=r46h-gaming-input-bridge-v0.5' \
  "$ROOTFS/usr/share/r46h-build/CONSOLIDATED-RECEIPT" || \
  die 'consolidated receipt product input mismatch'
grep -Fqx "product_kernel_directory=$PRODUCT_KERNEL_DIRECTORY" \
  "$ROOTFS/usr/share/r46h-build/CONSOLIDATED-RECEIPT" || \
  die 'consolidated receipt product kernel staging mismatch'

evidence=$ROOTFS/$COMPOSE_EVIDENCE_REL
[[ -d "$evidence" && ! -L "$evidence" ]] || die 'composition evidence is missing'
for name in GAMING-PAYLOAD-VERIFY.txt GAMING-SYSTEMD-VERIFY.txt NESTOPIA-ROM-LOAD.txt \
  RETROARCH-FEATURES.txt RETROARCH-LDD.txt SMOKE-CORE-FILE.txt SMOKE-CORE-LOAD.txt; do
  [[ -f "$evidence/$name" && ! -L "$evidence/$name" ]] || die "composition evidence is missing: $name"
  cp -- "$evidence/$name" "/output/$name"
done
rm -rf -- "$evidence"

# dpkg-query, not Bash, expands these fields.
# shellcheck disable=SC2016
chroot "$ROOTFS" dpkg-query -W '-f=${binary:Package}\t${Version}\n' | LC_ALL=C sort \
  > /output/PACKAGES.tsv
while IFS=$'\t' read -r package version; do
  [[ "$(chroot "$ROOTFS" dpkg-query -W -f='${db:Status-Abbrev}\t${Version}' "$package")" == \
    $'ii \t'"$version" ]] || die "installed gaming package mismatch: $package"
done < "$ROOTFS/usr/share/r46h-build/GAMING-PACKAGES.tsv"
! find "$ROOTFS" -xdev -iname 'libMali*' -print -quit | grep -q . || die 'forbidden libMali found'

systemd-analyze --root="$ROOTFS" verify --man=no \
  r46h-firstboot.service r46h-wifi-mac.service serial-getty@ttyS2.service \
  ssh.service NetworkManager.service r46h-gaming-input.service r46h-gaming-frontend.service \
  > /output/SYSTEMD-VERIFY.txt 2>&1 || {
    cat /output/SYSTEMD-VERIFY.txt >&2
    die 'systemd unit verification failed'
  }
printf 'R46H_SYSTEMD_VERIFY_RESULT=pass\n' >> /output/SYSTEMD-VERIFY.txt
[[ "$(readlink "$ROOTFS/etc/systemd/system/multi-user.target.wants/r46h-gaming-frontend.service")" == \
  /etc/systemd/system/r46h-gaming-frontend.service ]] || die 'gaming frontend enable link mismatch'
[[ "$(readlink "$ROOTFS/etc/systemd/system/multi-user.target.wants/r46h-gaming-input.service")" == \
  /etc/systemd/system/r46h-gaming-input.service ]] || die 'gaming input enable link mismatch'

cp -- "$ROOTFS/usr/share/r46h-build/APT-INRELEASE-SHA256SUMS" \
  /output/APT-INRELEASE-SHA256SUMS
cp -- "$ROOTFS/usr/share/r46h-build/SSHD-EFFECTIVE.txt" /output/SSHD-EFFECTIVE.txt
cp -- "$ROOTFS/usr/share/r46h-build/CONSOLIDATED-RECEIPT" /output/CONSOLIDATED-RECEIPT
cp -- "$ROOTFS/var/lib/r46h/gaming-mvp-v0.4-installed" /output/GAMING-RECEIPT

# Container execution and package installation change directory mtimes. Normalize
# the complete composed tree only after all build-only evidence has been removed.
find "$ROOTFS" -xdev -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
(cd "$ROOTFS" && find . -xdev -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum) \
  > /output/ROOTFS-FILES.sha256
(cd "$ROOTFS" && find . -xdev -printf '%m\t%U\t%G\t%y\t%p\t%l\n' | LC_ALL=C sort) \
  > /output/ROOTFS-TREE.tsv

image=/output/$IMAGE_NAME
truncate -s "$PARTITION_SIZE" "$image"
E2FSPROGS_FAKE_TIME="$SOURCE_DATE_EPOCH" mke2fs -q -F -t ext4 -b "$FS_BLOCK_SIZE" \
  -L "$FS_LABEL" -U "$FS_UUID" -m 1 \
  -E lazy_itable_init=0,lazy_journal_init=0 \
  -d "$ROOTFS" "$image" "$FS_BLOCK_COUNT"
truncate -s "$PARTITION_SIZE" "$image"
[[ "$(stat -c %s "$image")" == "$PARTITION_SIZE" ]] || die 'image size mismatch'
tail -c "$FS_TAIL_SIZE" "$image" | cmp -n "$FS_TAIL_SIZE" - /dev/zero || \
  die 'nonzero p2 tail'

e2fsck -f -n "$image" > /output/E2FSCK.txt 2>&1 || {
  cat /output/E2FSCK.txt >&2
  die 'offline ext4 verification failed'
}
printf 'R46H_E2FSCK_RESULT=pass\n' >> /output/E2FSCK.txt
dumpe2fs -h "$image" > /output/DUMPE2FS.txt 2>&1
grep -Fq "Filesystem UUID:          $FS_UUID" /output/DUMPE2FS.txt || die 'filesystem UUID mismatch'
grep -Fq "Filesystem volume name:   $FS_LABEL" /output/DUMPE2FS.txt || die 'filesystem label mismatch'
grep -Fq "Block count:              $FS_BLOCK_COUNT" /output/DUMPE2FS.txt || die 'filesystem block count mismatch'
{
  debugfs -R 'stat /usr/local/sbin/r46h-rootfs-smoke' "$image"
  debugfs -R 'stat /var/lib/r46h/gaming-mvp-v0.4-installed' "$image"
  debugfs -R 'stat /roms/nes/r46h-nes-smoke.nes' "$image"
  debugfs -R "stat $PRODUCT_KERNEL_DIRECTORY/IMAGE" "$image"
  debugfs -R "stat $PRODUCT_KERNEL_DIRECTORY/R46H.DTB" "$image"
  debugfs -R "stat $PRODUCT_KERNEL_DIRECTORY/UBOOT-CMDS.txt" "$image"
} > /output/DEBUGFS-GAMING.txt 2>&1
[[ "$(grep -Fc 'Type: regular' /output/DEBUGFS-GAMING.txt)" == 6 ]] || \
  die 'debugfs did not prove all gaming image anchors'
verified_image_sha=$(sha256sum "$image" | awk '{print $1}')
[[ "$verified_image_sha" =~ ^[0-9a-f]{64}$ ]] || die 'invalid verified image hash'
printf '%s  %s\n' "$verified_image_sha" "$IMAGE_NAME" > /output/EXT4-VERIFIED.sha256

printf 'PASS: consolidated Debian 13 gaming ext4 image and offline verification completed.\n'
