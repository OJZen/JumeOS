#!/usr/bin/env bash
set -Eeuo pipefail
umask 022

readonly ROOTFS_TAR=/input/rootfs.tar
readonly KERNEL_BUNDLE=/input/r46h-mainline-test-v0.8-bootloader-handoff.tar.gz
readonly ROOTFS=/work/rootfs
readonly KERNEL_STAGE=/work/kernel
readonly PRIVATE_KERNEL_BUNDLE=/work/kernel-bundle.tar.gz
readonly KERNEL_DIRECTORY=r46h-mainline-test-v0.8-bootloader-handoff

die() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

for name in IMAGE_NAME PARTITION_SIZE FS_BLOCK_SIZE FS_BLOCK_COUNT FS_TAIL_SIZE FS_UUID FS_LABEL \
  KERNEL_RELEASE KERNEL_BUNDLE_SHA256 SOURCE_DATE_EPOCH; do
  [[ -n "${!name:-}" ]] || die "missing environment: $name"
done

[[ "$PARTITION_SIZE" =~ ^[1-9][0-9]*$ ]] || die 'invalid PARTITION_SIZE'
[[ "$FS_BLOCK_SIZE" == 4096 && "$FS_BLOCK_COUNT" =~ ^[1-9][0-9]*$ ]] || die 'invalid ext4 geometry'
[[ "$FS_TAIL_SIZE" == 512 ]] || die 'invalid ext4 tail size'
(( FS_BLOCK_SIZE * FS_BLOCK_COUNT + FS_TAIL_SIZE == PARTITION_SIZE )) || die 'ext4 geometry does not cover p2 exactly'
[[ "$KERNEL_BUNDLE_SHA256" =~ ^[0-9a-f]{64}$ ]] || die 'invalid kernel bundle hash'
[[ -f "$ROOTFS_TAR" && -f "$KERNEL_BUNDLE" ]] || die 'missing build inputs'
[[ ! -e "/output/$IMAGE_NAME" ]] || die 'output image already exists'

rm -rf -- "$ROOTFS" "$KERNEL_STAGE"
mkdir -m 0755 "$ROOTFS" "$KERNEL_STAGE"
rm -f -- "$PRIVATE_KERNEL_BUNDLE"
cp -- "$KERNEL_BUNDLE" "$PRIVATE_KERNEL_BUNDLE"
chmod 0400 "$PRIVATE_KERNEL_BUNDLE"
printf '%s  %s\n' "$KERNEL_BUNDLE_SHA256" "$PRIVATE_KERNEL_BUNDLE" | sha256sum -c -

tar --numeric-owner -xf "$ROOTFS_TAR" -C "$ROOTFS"
tar --numeric-owner -xzf "$PRIVATE_KERNEL_BUNDLE" -C "$KERNEL_STAGE"
if [[ -e "$ROOTFS/.dockerenv" || -L "$ROOTFS/.dockerenv" ]]; then
  [[ -f "$ROOTFS/.dockerenv" && ! -L "$ROOTFS/.dockerenv" ]] ||
    die 'unsafe Docker runtime marker in rootfs export'
  rm -f -- "$ROOTFS/.dockerenv"
fi
[[ ! -e "$ROOTFS/.dockerenv" && ! -L "$ROOTFS/.dockerenv" ]] ||
  die 'Docker runtime marker remains in hardware rootfs'
mapfile -t kernel_top_entries < <(find "$KERNEL_STAGE" -mindepth 1 -maxdepth 1 -printf '%f\n')
[[ "${#kernel_top_entries[@]}" == 1 && "${kernel_top_entries[0]}" == "$KERNEL_DIRECTORY" ]] ||
  die 'kernel bundle has an unexpected top-level layout'
KERNEL_ROOT=$KERNEL_STAGE/$KERNEL_DIRECTORY
[[ -d "$KERNEL_ROOT" && ! -L "$KERNEL_ROOT" ]] || die 'kernel bundle root is unsafe'
(cd "$KERNEL_ROOT" && sha256sum -c SHA256SUMS >/output/KERNEL-BUNDLE-VERIFY.txt)

grep -Fqx "kernel_release=$KERNEL_RELEASE" "$KERNEL_ROOT/MANIFEST" || die 'kernel release mismatch'
rm -rf -- "$ROOTFS/lib/modules/$KERNEL_RELEASE"
install -d -m 0755 "$ROOTFS/lib/modules"
cp -a -- "$KERNEL_ROOT/rootfs/lib/modules/$KERNEL_RELEASE" "$ROOTFS/lib/modules/"

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

cmp -s "$ROOTFS/etc/hostname" "$ROOTFS/usr/share/r46h-build/rootfs-config/hostname" ||
  die 'hostname was not restored after Docker export'
cmp -s "$ROOTFS/etc/hosts" "$ROOTFS/usr/share/r46h-build/rootfs-config/hosts" ||
  die 'hosts file was not restored after Docker export'
[[ "$(readlink "$ROOTFS/etc/resolv.conf")" == /run/NetworkManager/resolv.conf ]] ||
  die 'resolver symlink was not restored after Docker export'
[[ "$(readlink "$ROOTFS/etc/localtime")" == /usr/share/zoneinfo/Asia/Shanghai ]] ||
  die 'timezone symlink mismatch'
grep -Fqx 'Asia/Shanghai' "$ROOTFS/etc/timezone" || die 'timezone identity mismatch'
grep -Fqx 'LANG=C.UTF-8' "$ROOTFS/etc/locale.conf" || die 'locale identity mismatch'
[[ "$(readlink "$ROOTFS/etc/systemd/system/systemd-firstboot.service")" == /dev/null ]] ||
  die 'interactive vendor firstboot service is not masked'

test -x "$ROOTFS/usr/local/sbin/r46h-rootfs-smoke" || die 'rootfs smoke tool missing'
test -x "$ROOTFS/usr/local/libexec/r46h-gles2-fbo-probe" || die 'GPU probe missing'
test -f "$ROOTFS/lib/firmware/rtlwifi/rtl8188eufw.bin" || die 'RTL8188EU firmware missing'
test -f "$ROOTFS/usr/lib/aarch64-linux-gnu/dri/panfrost_dri.so" || die 'Panfrost DRI missing'
test -f "$ROOTFS/lib/modules/$KERNEL_RELEASE/modules.dep" || die 'module dependency file missing'
test "$(stat -c %a "$ROOTFS/usr/bin/sudo")" == 4755 || die 'sudo lost setuid mode'
# dpkg-query, not Bash, expands this field.
# shellcheck disable=SC2016
for package in libnss-systemd libpam-systemd linux-sysctl-defaults netbase systemd-timesyncd; do
  chroot "$ROOTFS" dpkg-query -W -f='${db:Status-Abbrev}' "$package" | grep -Fqx 'ii ' ||
    die "required base package missing: $package"
done
! find "$ROOTFS" -xdev -iname 'libMali*' -print -quit | grep -q . || die 'forbidden libMali found'

# dpkg-query, not Bash, expands these fields.
# shellcheck disable=SC2016
chroot "$ROOTFS" dpkg-query -W '-f=${binary:Package}\t${Version}\n' | LC_ALL=C sort > /output/PACKAGES.tsv
cp -- "$ROOTFS/usr/share/r46h-build/APT-INRELEASE-SHA256SUMS" /output/APT-INRELEASE-SHA256SUMS
cp -- "$ROOTFS/usr/share/r46h-build/SSHD-EFFECTIVE.txt" /output/SSHD-EFFECTIVE.txt
file "$ROOTFS/usr/local/libexec/r46h-gles2-fbo-probe" > /output/PROBE-FILE.txt
chroot "$ROOTFS" ldd /usr/local/libexec/r46h-gles2-fbo-probe > /output/PROBE-LDD.txt
grep -Eq 'ELF 64-bit.*ARM aarch64' /output/PROBE-FILE.txt || die 'GPU probe is not AArch64'
! grep -Eiq 'not found|libMali' /output/PROBE-LDD.txt || die 'GPU probe dependency failure'

systemd-analyze --root="$ROOTFS" verify --man=no \
  r46h-firstboot.service r46h-wifi-mac.service serial-getty@ttyS2.service \
  ssh.service NetworkManager.service > /output/SYSTEMD-VERIFY.txt 2>&1 || {
    cat /output/SYSTEMD-VERIFY.txt >&2
    die 'systemd unit verification failed'
  }
printf 'R46H_SYSTEMD_VERIFY_RESULT=pass\n' >> /output/SYSTEMD-VERIFY.txt

(cd "$ROOTFS" && find . -xdev -type f -print0 | LC_ALL=C sort -z | xargs -0 sha256sum) \
  > /output/ROOTFS-FILES.sha256
(cd "$ROOTFS" && find . -xdev -printf '%m\t%U\t%G\t%y\t%p\t%l\n' | LC_ALL=C sort) \
  > /output/ROOTFS-TREE.tsv

image="/output/$IMAGE_NAME"
truncate -s "$PARTITION_SIZE" "$image"
E2FSPROGS_FAKE_TIME="$SOURCE_DATE_EPOCH" mke2fs -q -F -t ext4 -b "$FS_BLOCK_SIZE" \
  -L "$FS_LABEL" -U "$FS_UUID" -m 1 \
  -E lazy_itable_init=0,lazy_journal_init=0 \
  -d "$ROOTFS" "$image" "$FS_BLOCK_COUNT"
truncate -s "$PARTITION_SIZE" "$image"
[[ "$(stat -c %s "$image")" == "$PARTITION_SIZE" ]] || die 'image size mismatch'
tail -c "$FS_TAIL_SIZE" "$image" | cmp -n "$FS_TAIL_SIZE" - /dev/zero || die 'nonzero p2 tail'

e2fsck -f -n "$image" > /output/E2FSCK.txt 2>&1 || {
  cat /output/E2FSCK.txt >&2
  die 'offline ext4 verification failed'
}
printf 'R46H_E2FSCK_RESULT=pass\n' >> /output/E2FSCK.txt
dumpe2fs -h "$image" > /output/DUMPE2FS.txt 2>&1
grep -Fq "Filesystem UUID:          $FS_UUID" /output/DUMPE2FS.txt || die 'filesystem UUID mismatch'
grep -Fq "Filesystem volume name:   $FS_LABEL" /output/DUMPE2FS.txt || die 'filesystem label mismatch'
grep -Fq "Block count:              $FS_BLOCK_COUNT" /output/DUMPE2FS.txt || die 'filesystem block count mismatch'
debugfs -R 'stat /usr/local/sbin/r46h-rootfs-smoke' "$image" > /output/DEBUGFS-SMOKE.txt 2>&1
grep -Fq 'Type: regular' /output/DEBUGFS-SMOKE.txt || die 'smoke tool absent from ext4 image'
verified_image_sha=$(sha256sum "$image" | awk '{print $1}')
[[ "$verified_image_sha" =~ ^[0-9a-f]{64}$ ]] || die 'invalid verified image hash'
printf '%s  %s\n' "$verified_image_sha" "$IMAGE_NAME" > /output/EXT4-VERIFIED.sha256

printf 'PASS: Debian 13 ext4 image and offline verification completed.\n'
