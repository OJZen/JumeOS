#!/bin/bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG
umask 077

readonly ACTION=${1:-}
readonly IMAGE=/output/${IMAGE_NAME:?}
readonly INPUTS=/payload/product-inputs
readonly SCRATCH=/work/rootfs-work.ext4
readonly EVIDENCE=/evidence
readonly ROOT=/mnt/root
readonly SOURCE=/mnt/source
readonly FINAL=/mnt/final
readonly RECEIPT=/usr/share/r46h-build/CONSOLIDATED-RECEIPT
readonly GAMING_RECEIPT=/var/lib/r46h/gaming-mvp-v0.6-installed
readonly POLICY_RECEIPT=/var/lib/r46h/network-policy-v0.18-installed
readonly RULE=/etc/polkit-1/rules.d/49-r46h-network.rules

base_loop=
scratch_loop=
final_loop=
root_mounted=false
source_mounted=false
final_mounted=false
proc_mounted=false
sys_mounted=false
dev_mounted=false
run_mounted=false
tmp_mounted=false

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
sha256() { sha256sum "$1" | awk '{print $1}'; }

cleanup() {
  set +e
  $tmp_mounted && umount "$FINAL/tmp"
  $run_mounted && umount "$FINAL/run"
  $dev_mounted && umount -R "$ROOT/dev"
  $sys_mounted && umount "$ROOT/sys"
  $proc_mounted && umount "$ROOT/proc"
  $final_mounted && umount "$FINAL"
  $source_mounted && umount "$SOURCE"
  $root_mounted && umount "$ROOT"
  [[ -z $final_loop ]] || losetup -d "$final_loop"
  [[ -z $base_loop ]] || losetup -d "$base_loop"
  [[ -z $scratch_loop ]] || losetup -d "$scratch_loop"
  rm -f -- "$SCRATCH"
}
trap cleanup EXIT INT TERM

for name in IMAGE_NAME IMAGE_SIZE FS_TAIL_SIZE BASE_IMAGE_SHA256 BASE_FS_UUID BASE_FS_LABEL \
  FS_UUID FS_LABEL SOURCE_DATE_EPOCH ARTIFACT_ID SOURCE_GIT_COMMIT SOURCE_GIT_TREE \
  SOURCE_MANIFEST_SHA256 BASE_CONSOLIDATED_RECEIPT_SHA256 BASE_GAMING_RECEIPT_SHA256 \
  FINAL_FIRSTBOOT_SHA256 FINAL_ROOTFS_SMOKE_SHA256 ES_DE_RECEIPT_SHA256 \
  ES_DE_RUNNER_SHA256 ES_DE_SYSTEMS_SHA256 SCREENSHOT_SHA256 REMOTE_INPUT_SHA256 \
  NETWORK_RULE_SHA256 POLKIT_PACKAGE_MANIFEST_SHA256 ALSA_VENDOR_RULE_SHA256 \
  ALSA_OVERRIDE_RULE_SHA256; do
  [[ -n ${!name:-} ]] || die "missing environment value: $name"
done
[[ $ACTION == apply || $ACTION == verify ]] || die 'action must be apply or verify'
[[ $IMAGE_SIZE == 10716877312 && $FS_TAIL_SIZE == 512 ]] || die 'unexpected p2 geometry'
[[ $ARTIFACT_ID == debian13-p2-gaming-v0.18 ]] || die 'unexpected artifact identity'
[[ $FS_UUID == d3130018-46a4-4d56-9001-000000000018 ]] || die 'unexpected filesystem UUID'

expect_hash() {
  local path=$1 expected=$2 label=$3
  [[ -f $path && ! -L $path ]] || die "missing regular $label: $path"
  [[ $(sha256 "$path") == "$expected" ]] || die "$label digest mismatch"
}

replace_line() {
  local file=$1 old=$2 new=$3 stage=$1.stage
  awk -v old="$old" -v new="$new" '
    $0 == old { print new; replaced += 1; next }
    { print }
    END { if (replaced != 1) exit 1 }
  ' "$file" > "$stage" || die "receipt replacement mismatch: $old"
  mv -f -- "$stage" "$file"
}

verify_inputs() {
  local package version architecture filename digest count=0
  [[ -d $INPUTS && ! -L $INPUTS ]] || die 'product inputs are missing'
  expect_hash "$INPUTS/POLKIT-PACKAGES.tsv" "$POLKIT_PACKAGE_MANIFEST_SHA256" 'package manifest'
  expect_hash "$INPUTS/49-r46h-network.rules" "$NETWORK_RULE_SHA256" 'network rule'
  expect_hash "$INPUTS/r46h-es-de-ui.v18" "$ES_DE_RUNNER_SHA256" 'ES-DE runner'
  expect_hash "$INPUTS/r46h-screenshot.v18" "$SCREENSHOT_SHA256" 'screenshot helper'
  expect_hash "$INPUTS/r46h-firstboot.v18" "$FINAL_FIRSTBOOT_SHA256" 'firstboot helper'
  expect_hash "$INPUTS/r46h-rootfs-smoke.v18" "$FINAL_ROOTFS_SMOKE_SHA256" 'rootfs smoke helper'
  expect_hash "$INPUTS/es-de-receipt.v18" "$ES_DE_RECEIPT_SHA256" 'ES-DE receipt'
  while IFS=$'\t' read -r package version architecture filename digest; do
    [[ -n $package && -n $version && -n $architecture && -n $filename && $digest =~ ^[0-9a-f]{64}$ ]] || \
      die 'invalid package manifest row'
    expect_hash "$INPUTS/$filename" "$digest" "package $package"
    [[ $(dpkg-deb -f "$INPUTS/$filename" Package) == "$package" ]] || die "package name mismatch: $filename"
    [[ $(dpkg-deb -f "$INPUTS/$filename" Version) == "$version" ]] || die "package version mismatch: $filename"
    [[ $(dpkg-deb -f "$INPUTS/$filename" Architecture) == "$architecture" ]] || die "package architecture mismatch: $filename"
    count=$((count + 1))
  done < "$INPUTS/POLKIT-PACKAGES.tsv"
  [[ $count == 6 ]] || die 'unexpected package count'
  [[ $(find "$INPUTS" -mindepth 1 -maxdepth 1 -type f | wc -l | tr -d ' ') == 13 ]] || \
    die 'unexpected product input count'
  bash -n "$INPUTS/r46h-es-de-ui.v18" "$INPUTS/r46h-screenshot.v18" \
    "$INPUTS/r46h-firstboot.v18" "$INPUTS/r46h-rootfs-smoke.v18"
  grep -Fqx '    if (subject.user == "ark" && allowed.indexOf(action.id) >= 0)' \
    "$INPUTS/49-r46h-network.rules" || die 'network rule subject mismatch'
}

verify_base() {
  local dumped=/work/base-receipt
  [[ $(stat -c %s "$IMAGE") == "$IMAGE_SIZE" ]] || die 'base image size mismatch'
  [[ $(sha256 "$IMAGE") == "$BASE_IMAGE_SHA256" ]] || die 'base image digest mismatch'
  dumpe2fs -h "$IMAGE" >/work/base-dumpe2fs.txt 2>&1
  grep -Fq "Filesystem UUID:          $BASE_FS_UUID" /work/base-dumpe2fs.txt || die 'base UUID mismatch'
  grep -Fq "Filesystem volume name:   $BASE_FS_LABEL" /work/base-dumpe2fs.txt || die 'base label mismatch'
  debugfs -R "dump -p $RECEIPT $dumped" "$IMAGE" >/dev/null 2>&1
  expect_hash "$dumped" "$BASE_CONSOLIDATED_RECEIPT_SHA256" 'base consolidated receipt'
}

detach_source() {
  umount "$SOURCE"; source_mounted=false
  losetup -d "$base_loop"; base_loop=
}

detach_root() {
  umount "$ROOT"; root_mounted=false
  losetup -d "$scratch_loop"; scratch_loop=
  rm -f -- "$SCRATCH"
}

prepare_receipt() {
  local receipt=$ROOT$RECEIPT
  replace_line "$receipt" 'artifact_id=debian13-p2-gaming-v0.17' "artifact_id=$ARTIFACT_ID"
  replace_line "$receipt" 'source_git_commit=221075dc4f7bf0b7977e52f6764523118f2fd982' "source_git_commit=$SOURCE_GIT_COMMIT"
  replace_line "$receipt" 'source_git_tree=ea3277a669677819c4d473b50788246aedbf0334' "source_git_tree=$SOURCE_GIT_TREE"
  replace_line "$receipt" 'source_manifest_sha256=b7a1ec037f265f46acb551341bf2aa67aa1dc4c4776cad23cb23dcb0757fe257' "source_manifest_sha256=$SOURCE_MANIFEST_SHA256"
  replace_line "$receipt" 'successor_base_artifact_id=debian13-p2-gaming-v0.16' 'successor_base_artifact_id=debian13-p2-gaming-v0.17'
  replace_line "$receipt" 'successor_base_image_sha256=21cdfa3af3b96b6233decdc3ca4f8475c0eba946503045a4e86c21c50b8374c4' "successor_base_image_sha256=$BASE_IMAGE_SHA256"
  replace_line "$receipt" 'base_consolidated_receipt_sha256=38dba41fdec1846b7476e29c045381040749e75a4c341d60e3e068578fcfa88f' "base_consolidated_receipt_sha256=$BASE_CONSOLIDATED_RECEIPT_SHA256"
  replace_line "$receipt" 'successor_method=offline-debugfs-bounded-overlay' 'successor_method=offline-ext4-repack-local-debs'
  replace_line "$receipt" 'es_de_runner_sha256=2809199ce5020edd7a654b9ef8b72b58dca7568603f44769b7ace933a942c94d' "es_de_runner_sha256=$ES_DE_RUNNER_SHA256"
  replace_line "$receipt" 'es_de_receipt_sha256=75adef49bcc3637df08060a5e2ba5a2cc10a5f8c8b7430f8c2bd9e4d2c766356' "es_de_receipt_sha256=$ES_DE_RECEIPT_SHA256"
  replace_line "$receipt" 'screenshot_helper_sha256=ddeaacea8619ab23b37423dd27715d7906727475a10f348a589345b8b890e535' "screenshot_helper_sha256=$SCREENSHOT_SHA256"
  replace_line "$receipt" 'filesystem_uuid=d3130017-46a4-4d56-9001-000000000017' "filesystem_uuid=$FS_UUID"
  replace_line "$receipt" 'filesystem_label=R46H_GAMING_V17' "filesystem_label=$FS_LABEL"
  cat >> "$receipt" <<EOF
network_policy_packages_sha256=$POLKIT_PACKAGE_MANIFEST_SHA256
network_policy_rule_sha256=$NETWORK_RULE_SHA256
network_policy_scope=ark-only-three-actions
polkitd_version=126-2
EOF
}

compose() {
  local status package version architecture filename digest
  rm -f -- "$SCRATCH"
  truncate -s "$IMAGE_SIZE" "$SCRATCH"
  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH mke2fs -q -F -t ext4 -b 4096 \
    -L R46H_V18_WORK -U d3130018-46a4-4d56-9001-000000000118 -m 1 \
    -E lazy_itable_init=0,lazy_journal_init=0 "$SCRATCH" 2616425
  mkdir -p "$ROOT" "$SOURCE"
  scratch_loop=$(losetup --find --show "$SCRATCH")
  mount "$scratch_loop" "$ROOT"; root_mounted=true
  base_loop=$(losetup --find --show --read-only "$IMAGE")
  mount -o ro,noload "$base_loop" "$SOURCE"; source_mounted=true
  cp -a -- "$SOURCE/." "$ROOT/"
  detach_source

  mount -t proc proc "$ROOT/proc"; proc_mounted=true
  mount -t sysfs sysfs "$ROOT/sys"; sys_mounted=true
  mount --rbind /dev "$ROOT/dev"; dev_mounted=true
  install -d -m 0700 "$ROOT/run/r46h-polkit-debs" "$ROOT/run/r46h-polkit-apt/sources.list.d"
  cp -a "$INPUTS/"*.deb "$ROOT/run/r46h-polkit-debs/"
  : > "$ROOT/run/r46h-polkit-apt/sources.list"
  [[ ! -e $ROOT/usr/sbin/policy-rc.d && ! -L $ROOT/usr/sbin/policy-rc.d ]] || die 'unexpected policy-rc.d'
  printf '#!/bin/sh\nexit 101\n' > "$ROOT/usr/sbin/policy-rc.d"
  chmod 0755 "$ROOT/usr/sbin/policy-rc.d"
  chroot "$ROOT" /bin/sh -ec '
    export DEBIAN_FRONTEND=noninteractive
    apt-get -o Dir::Etc::sourcelist=/run/r46h-polkit-apt/sources.list \
      -o Dir::Etc::sourceparts=/run/r46h-polkit-apt/sources.list.d \
      install -y --no-install-recommends /run/r46h-polkit-debs/*.deb
  '
  rm -f "$ROOT/usr/sbin/policy-rc.d"
  umount -R "$ROOT/dev"; dev_mounted=false
  umount "$ROOT/sys"; sys_mounted=false
  umount "$ROOT/proc"; proc_mounted=false

  install -D -o root -g root -m 0644 "$INPUTS/49-r46h-network.rules" "$ROOT$RULE"
  install -o root -g root -m 0755 "$INPUTS/r46h-es-de-ui.v18" "$ROOT/usr/local/sbin/r46h-es-de-ui"
  install -o root -g root -m 0755 "$INPUTS/r46h-screenshot.v18" "$ROOT/usr/local/bin/r46h-screenshot"
  install -o root -g root -m 0755 "$INPUTS/r46h-firstboot.v18" "$ROOT/usr/libexec/r46h-firstboot"
  install -o root -g root -m 0755 "$INPUTS/r46h-rootfs-smoke.v18" "$ROOT/usr/local/sbin/r46h-rootfs-smoke"
  install -o root -g root -m 0600 "$INPUTS/es-de-receipt.v18" "$ROOT/var/lib/r46h/gaming-es-de-v0.1-installed"
  cat > "$ROOT$POLICY_RECEIPT" <<EOF
package_manifest_sha256=$POLKIT_PACKAGE_MANIFEST_SHA256
rule_sha256=$NETWORK_RULE_SHA256
scope=ark-only-three-actions
EOF
  chmod 0600 "$ROOT$POLICY_RECEIPT"
  prepare_receipt

  chroot "$ROOT" apt-get clean
  rm -rf "$ROOT/var/lib/apt/lists/"* "$ROOT/var/cache/apt/archives/"*.deb \
    "$ROOT/run/r46h-polkit-debs" "$ROOT/run/r46h-polkit-apt"
  rm -f "$ROOT/var/cache/ldconfig/aux-cache" "$ROOT/var/lib/r46h/firstboot-complete"
  for log in alternatives.log apt/eipp.log.xz apt/history.log apt/term.log dpkg.log; do
    [[ ! -e $ROOT/var/log/$log ]] || : > "$ROOT/var/log/$log"
  done
  find "$ROOT" -xdev -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +

  rm -f -- "$IMAGE"
  truncate -s "$IMAGE_SIZE" "$IMAGE"
  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH mke2fs -q -F -t ext4 -b 4096 \
    -L "$FS_LABEL" -U "$FS_UUID" -m 1 -E lazy_itable_init=0,lazy_journal_init=0 \
    -d "$ROOT" "$IMAGE" 2616425
  truncate -s "$IMAGE_SIZE" "$IMAGE"

  mkdir -p "$FINAL"
  final_loop=$(losetup --find --show --read-only "$IMAGE")
  mount -o ro,noload "$final_loop" "$FINAL"; final_mounted=true
  find "$FINAL" -xdev -printf '%i\n' | sort -nu | awk -v epoch="$SOURCE_DATE_EPOCH" \
    '{ print "set_inode_field <" $1 "> ctime @" epoch }' > /work/final-inodes.commands
  umount "$FINAL"; final_mounted=false
  losetup -d "$final_loop"; final_loop=
  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH debugfs -w \
    -R "set_super_value hash_seed $FS_UUID" "$IMAGE" >/work/hash-seed.txt 2>&1
  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH debugfs -w -f /work/final-inodes.commands "$IMAGE" \
    >/work/normalize-inodes.txt 2>&1
  set +e
  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH e2fsck -f -D -y "$IMAGE" >/work/e2fsck-repair.txt 2>&1
  status=$?
  set -e
  (( status == 0 || status == 1 )) || die "writable e2fsck failed: $status"
  cat > /work/normalize-super.commands <<EOF
set_super_value mtime @$SOURCE_DATE_EPOCH
set_super_value wtime @$SOURCE_DATE_EPOCH
set_super_value lastcheck @$SOURCE_DATE_EPOCH
set_super_value mkfs_time @$SOURCE_DATE_EPOCH
set_super_value mnt_count 0
set_super_value kbytes_written 0
EOF
  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH debugfs -w -f /work/normalize-super.commands "$IMAGE" \
    >/work/normalize-super.txt 2>&1
  E2FSPROGS_FAKE_TIME=$SOURCE_DATE_EPOCH tune2fs -U "$FS_UUID" -L "$FS_LABEL" "$IMAGE" \
    >/work/tune2fs.txt 2>&1
  detach_root
}

attach_final() {
  mkdir -p "$FINAL"
  final_loop=$(losetup --find --show --read-only "$IMAGE")
  mount -o ro,noload "$final_loop" "$FINAL"; final_mounted=true
}

detach_final() {
  $tmp_mounted && { umount "$FINAL/tmp"; tmp_mounted=false; }
  $run_mounted && { umount "$FINAL/run"; run_mounted=false; }
  umount "$FINAL"; final_mounted=false
  losetup -d "$final_loop"; final_loop=
}

verify_receipt() {
  local receipt=$1 marker
  for marker in \
    "artifact_id=$ARTIFACT_ID" "source_git_commit=$SOURCE_GIT_COMMIT" \
    "source_git_tree=$SOURCE_GIT_TREE" "source_manifest_sha256=$SOURCE_MANIFEST_SHA256" \
    'successor_base_artifact_id=debian13-p2-gaming-v0.17' \
    "successor_base_image_sha256=$BASE_IMAGE_SHA256" \
    'successor_method=offline-ext4-repack-local-debs' \
    "es_de_runner_sha256=$ES_DE_RUNNER_SHA256" "es_de_receipt_sha256=$ES_DE_RECEIPT_SHA256" \
    "screenshot_helper_sha256=$SCREENSHOT_SHA256" \
    "network_policy_packages_sha256=$POLKIT_PACKAGE_MANIFEST_SHA256" \
    "network_policy_rule_sha256=$NETWORK_RULE_SHA256" 'network_policy_scope=ark-only-three-actions' \
    'polkitd_version=126-2' "filesystem_uuid=$FS_UUID" "filesystem_label=$FS_LABEL" \
    'personal_authorized_keys=absent'; do
    [[ $(grep -Fxc "$marker" "$receipt") == 1 ]] || die "receipt marker mismatch: $marker"
  done
}

verify_final() {
  local package version architecture filename digest actual
  [[ $(stat -c %s "$IMAGE") == "$IMAGE_SIZE" ]] || die 'final image size mismatch'
  tail -c "$FS_TAIL_SIZE" "$IMAGE" | cmp -n "$FS_TAIL_SIZE" - /dev/zero || die 'nonzero p2 tail'
  e2fsck -f -n "$IMAGE" > "$EVIDENCE/E2FSCK.txt" 2>&1 || die 'read-only e2fsck failed'
  printf 'R46H_V18_E2FSCK_RESULT=pass\n' >> "$EVIDENCE/E2FSCK.txt"
  dumpe2fs -h "$IMAGE" > "$EVIDENCE/DUMPE2FS.txt" 2>&1
  grep -Fq "Filesystem UUID:          $FS_UUID" "$EVIDENCE/DUMPE2FS.txt" || die 'final UUID mismatch'
  grep -Fq "Filesystem volume name:   $FS_LABEL" "$EVIDENCE/DUMPE2FS.txt" || die 'final label mismatch'
  grep -Fq 'Filesystem state:         clean' "$EVIDENCE/DUMPE2FS.txt" || die 'filesystem is not clean'
  attach_final

  : > "$EVIDENCE/PACKAGE-VERIFY.txt"
  while IFS=$'\t' read -r package version architecture filename digest; do
    actual=$(chroot "$FINAL" dpkg-query -W '-f=${binary:Package}\t${Version}\t${Architecture}\n' "$package")
    [[ $actual == "$package"$'\t'"$version"$'\t'"$architecture" ]] || die "installed package mismatch: $package"
    printf '%s\n' "$actual" >> "$EVIDENCE/PACKAGE-VERIFY.txt"
  done < "$INPUTS/POLKIT-PACKAGES.tsv"
  grep -Fqx 'polkitd:x:989:989:User for polkitd:/:/usr/sbin/nologin' "$FINAL/etc/passwd" || die 'polkitd user mismatch'
  grep -Fqx 'polkitd:x:989:' "$FINAL/etc/group" || die 'polkitd group mismatch'
  printf 'R46H_V18_PACKAGE_VERIFY_RESULT=pass\n' >> "$EVIDENCE/PACKAGE-VERIFY.txt"

  expect_hash "$FINAL$RULE" "$NETWORK_RULE_SHA256" 'installed network rule'
  expect_hash "$FINAL/usr/local/sbin/r46h-es-de-ui" "$ES_DE_RUNNER_SHA256" 'installed ES-DE runner'
  expect_hash "$FINAL/usr/local/bin/r46h-screenshot" "$SCREENSHOT_SHA256" 'installed screenshot helper'
  expect_hash "$FINAL/usr/libexec/r46h-firstboot" "$FINAL_FIRSTBOOT_SHA256" 'installed firstboot helper'
  expect_hash "$FINAL/usr/local/sbin/r46h-rootfs-smoke" "$FINAL_ROOTFS_SMOKE_SHA256" 'installed rootfs smoke helper'
  expect_hash "$FINAL/var/lib/r46h/gaming-es-de-v0.1-installed" "$ES_DE_RECEIPT_SHA256" 'installed ES-DE receipt'
  expect_hash "$FINAL/etc/r46h/es-de-systems.xml" "$ES_DE_SYSTEMS_SHA256" 'retained ES-DE systems'
  expect_hash "$FINAL/usr/local/libexec/r46h-remote-input" "$REMOTE_INPUT_SHA256" 'retained remote input'
  expect_hash "$FINAL/usr/lib/udev/rules.d/90-alsa-restore.rules" "$ALSA_VENDOR_RULE_SHA256" 'retained vendor udev rule'
  expect_hash "$FINAL/etc/udev/rules.d/90-alsa-restore.rules" "$ALSA_OVERRIDE_RULE_SHA256" 'retained udev override'
  expect_hash "$FINAL$GAMING_RECEIPT" "$BASE_GAMING_RECEIPT_SHA256" 'retained gaming receipt'
  grep -Fqx "package_manifest_sha256=$POLKIT_PACKAGE_MANIFEST_SHA256" "$FINAL$POLICY_RECEIPT" || die 'policy receipt mismatch'
  verify_receipt "$FINAL$RECEIPT"
  [[ ! -e $FINAL/home/ark/.ssh/authorized_keys && ! -L $FINAL/home/ark/.ssh/authorized_keys ]] || die 'operator key entered image'
  [[ ! -e $FINAL/var/lib/r46h/firstboot-complete ]] || die 'firstboot state entered image'
  [[ ! -s $FINAL/etc/machine-id ]] || die 'machine identity entered image'
  [[ $(stat -c %a "$FINAL/usr/bin/sudo") == 4755 ]] || die 'sudo lost setuid mode'
  bash -n "$FINAL/usr/local/sbin/r46h-es-de-ui" "$FINAL/usr/local/bin/r46h-screenshot" \
    "$FINAL/usr/libexec/r46h-firstboot" "$FINAL/usr/local/sbin/r46h-rootfs-smoke"

  mount -t tmpfs tmpfs "$FINAL/run"; run_mounted=true
  mount -t tmpfs tmpfs "$FINAL/tmp"; tmp_mounted=true
  chroot "$FINAL" /bin/sh -c 'cd /; systemd-analyze verify --man=no NetworkManager.service polkit.service r46h-gaming-input.service r46h-gaming-frontend.service' \
    > "$EVIDENCE/SYSTEMD-VERIFY.txt" 2>&1
  printf 'R46H_V18_SYSTEMD_VERIFY_RESULT=pass\n' >> "$EVIDENCE/SYSTEMD-VERIFY.txt"
  chroot "$FINAL" /bin/sh -c 'cd /; udevadm verify /etc/udev/rules.d/90-alsa-restore.rules' \
    > "$EVIDENCE/UDEV-VERIFY.txt" 2>&1
  printf 'R46H_V18_UDEV_VERIFY_RESULT=pass\n' >> "$EVIDENCE/UDEV-VERIFY.txt"
  umount "$FINAL/tmp"; tmp_mounted=false
  umount "$FINAL/run"; run_mounted=false

  cp -- "$FINAL$RECEIPT" "$EVIDENCE/CONSOLIDATED-RECEIPT"
  cp -- "$FINAL$GAMING_RECEIPT" "$EVIDENCE/GAMING-RECEIPT"
  {
    debugfs -R "stat $RULE" "$IMAGE"
    debugfs -R 'stat /usr/lib/systemd/system/polkit.service' "$IMAGE"
    debugfs -R 'stat /usr/local/sbin/r46h-rootfs-smoke' "$IMAGE"
    printf 'R46H_V18_IMAGE_VERIFY_RESULT=pass\n'
  } > "$EVIDENCE/DEBUGFS-V18.txt" 2>&1
  cat > "$EVIDENCE/PRODUCT-VERIFY.txt" <<EOF
R46H_V18_PRODUCT artifact_id=$ARTIFACT_ID base=v0.17 polkitd=126-2 actions=3 subject=ark
R46H_V18_PRODUCT network_rule_sha256=$NETWORK_RULE_SHA256 package_manifest_sha256=$POLKIT_PACKAGE_MANIFEST_SHA256
R46H_V18_PRODUCT_VERIFY_RESULT=pass
EOF
  printf '%s  %s\n' "$(sha256 "$IMAGE")" "$IMAGE_NAME" > "$EVIDENCE/EXT4-VERIFIED.sha256"
  detach_final
}

verify_inputs
if [[ $ACTION == apply ]]; then
  verify_base
  compose
fi
verify_final
printf 'PASS: R46H Debian 13 gaming p2 v0.18 image %s completed.\n' "$ACTION"
