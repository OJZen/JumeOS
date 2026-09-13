#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

PATH=/usr/sbin:/usr/bin:/sbin:/bin
LC_ALL=C
LANG=C
export PATH LC_ALL LANG

readonly HOTFIX_ID=debian13-p2-mvp-v0.1-regdb-upstream-v1
readonly EXPECTED_RELEASE=6.12.99-r46h-mainline-v0.8-bootloader-handoff
readonly EXPECTED_MARKER=release=debian13-p2-mvp-v0.1
readonly EXPECTED_ROOT_SOURCE=/dev/mmcblk0p2
readonly EXPECTED_ROOT_PARTUUID=c9f931c9-02
readonly EXPECTED_ROOT_UUID=d3130001-46a4-4d56-9001-000000000001
readonly EXPECTED_REGDB_VERSION=2026.05.30-1~deb13u1
readonly UPSTREAM_DB=/lib/firmware/regulatory.db-upstream
readonly UPSTREAM_SIGNATURE=/lib/firmware/regulatory.db.p7s-upstream
readonly UPSTREAM_DB_SHA256=2fb33ca0074db573e05ef7dd50bb45b63c0ff98b7e852e1105ebad536fae8e6b
readonly UPSTREAM_SIGNATURE_SHA256=c941c08f51c93e46722293b85631604c3740d86c3de0c75f79aef50d2e919179

die() {
  trap - ERR
  printf 'R46H_REGDB_HOTFIX id=%s result=fail reason=%s\n' "$HOTFIX_ID" "$1" >&2
  exit 1
}
trap 'die unexpected-error' ERR

[[ "$#" == 0 ]] || die unexpected-arguments
[[ "$(id -u)" == 0 ]] || die not-root
[[ "$(uname -r)" == "$EXPECTED_RELEASE" ]] || die kernel-mismatch
[[ "$(findmnt -n -o SOURCE /)" == "$EXPECTED_ROOT_SOURCE" ]] || die root-source-mismatch
[[ "$(findmnt -n -o PARTUUID /)" == "$EXPECTED_ROOT_PARTUUID" ]] ||
  die root-partuuid-mismatch
[[ "$(findmnt -n -o UUID /)" == "$EXPECTED_ROOT_UUID" ]] || die root-uuid-mismatch
[[ -f /var/lib/r46h/firstboot-complete && ! -L /var/lib/r46h/firstboot-complete ]] ||
  die firstboot-marker-identity
grep -Fqx "$EXPECTED_MARKER" /var/lib/r46h/firstboot-complete || die release-mismatch
installed_regdb_version=$(dpkg-query -W -f='${Version}' wireless-regdb 2>/dev/null)
[[ "$installed_regdb_version" == "$EXPECTED_REGDB_VERSION" ]] ||
  die wireless-regdb-version-mismatch
[[ -f "$UPSTREAM_DB" && ! -L "$UPSTREAM_DB" ]] || die upstream-database-missing
[[ -f "$UPSTREAM_SIGNATURE" && ! -L "$UPSTREAM_SIGNATURE" ]] ||
  die upstream-signature-missing
printf '%s  %s\n' "$UPSTREAM_DB_SHA256" "$UPSTREAM_DB" |
  sha256sum -c - >/dev/null || die upstream-database-hash-mismatch
printf '%s  %s\n' "$UPSTREAM_SIGNATURE_SHA256" "$UPSTREAM_SIGNATURE" |
  sha256sum -c - >/dev/null || die upstream-signature-hash-mismatch

kernel_config=
if [[ -r /proc/config.gz ]]; then
  kernel_config=/proc/config.gz
  zgrep -Fqx 'CONFIG_CFG80211_REQUIRE_SIGNED_REGDB=y' "$kernel_config" ||
    die signed-regdb-contract-mismatch
  zgrep -Fqx 'CONFIG_CFG80211_USE_KERNEL_REGDB_KEYS=y' "$kernel_config" ||
    die kernel-regdb-key-contract-mismatch
elif [[ -r "/boot/config-$EXPECTED_RELEASE" ]]; then
  kernel_config=/boot/config-$EXPECTED_RELEASE
  grep -Fqx 'CONFIG_CFG80211_REQUIRE_SIGNED_REGDB=y' "$kernel_config" ||
    die signed-regdb-contract-mismatch
  grep -Fqx 'CONFIG_CFG80211_USE_KERNEL_REGDB_KEYS=y' "$kernel_config" ||
    die kernel-regdb-key-contract-mismatch
else
  die kernel-config-unavailable
fi

update-alternatives --set regulatory.db "$UPSTREAM_DB" || die alternatives-update-failed
database_target=$(readlink -f /lib/firmware/regulatory.db)
signature_target=$(readlink -f /lib/firmware/regulatory.db.p7s)
[[ "$database_target" == /usr/lib/firmware/regulatory.db-upstream ]] ||
  die database-link-mismatch
[[ "$signature_target" == /usr/lib/firmware/regulatory.db.p7s-upstream ]] ||
  die signature-link-mismatch

printf 'R46H_REGDB_HOTFIX id=%s result=pass reboot_required=yes config=%s\n' \
  "$HOTFIX_ID" "$kernel_config"
