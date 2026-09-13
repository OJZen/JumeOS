#!/bin/bash
set -Eeuo pipefail

export LC_ALL=C
readonly PREFIX=/stage/opt/r46h/es-de
readonly LIB_DIR=$PREFIX/lib/aarch64-linux-gnu
readonly BASE_SONAMES=/tmp/base-sonames
readonly SOURCE_DATE_EPOCH=${SOURCE_DATE_EPOCH:?}
readonly ARTIFACT=/artifact/r46h-es-de-runtime-v3.4.1.tar.gz

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

[[ -x $PREFIX/bin/es-de && -x $PREFIX/bin/es-pdf-convert ]] || \
  die 'ES-DE install tree is incomplete'
[[ -s $BASE_SONAMES ]] || die 'base SONAME inventory is missing'

rm -rf "$PREFIX/share/applications" "$PREFIX/share/icons" "$PREFIX/share/man" \
  "$PREFIX/share/metainfo" "$PREFIX/share/pixmaps"
install -d -m 0755 "$LIB_DIR" "$PREFIX/share/r46h/licenses"

dependency_list=/tmp/runtime-dependencies.tsv
package_list=/tmp/runtime-packages.txt
ldd_output=/tmp/runtime-ldd.txt
: > "$dependency_list"
: > "$package_list"
ldd "$PREFIX/bin/es-de" "$PREFIX/bin/es-pdf-convert" > "$ldd_output"
! grep -Fq 'not found' "$ldd_output" || die 'runtime has unresolved shared libraries'

while IFS=$'\t' read -r soname library; do
  [[ -n $soname && $library == /* && -f $library ]] || \
    die "invalid ldd entry: $soname $library"
  if grep -Fqx "$soname" "$BASE_SONAMES"; then
    continue
  fi
  resolved=$(readlink -f -- "$library")
  [[ $resolved == /usr/lib/* || $resolved == /lib/* ]] || \
    die "dependency escaped system library roots: $resolved"
  owner=$(dpkg-query -S "$resolved" 2>/dev/null | sed -n '1{s/: \/.*$//;p;q;}')
  [[ -n $owner ]] || die "cannot identify package for $resolved"
  install -m 0644 "$resolved" "$LIB_DIR/$soname"
  printf '%s\t%s\t%s\n' "$soname" "$resolved" "$owner" >> "$dependency_list"
  printf '%s\n' "${owner%%:*}" >> "$package_list"
done < <(
  awk '$2 == "=>" && $3 ~ /^\// { print $1 "\t" $3 }' "$ldd_output" |
    LC_ALL=C sort -u
)

LC_ALL=C sort -u -o "$dependency_list" "$dependency_list"
LC_ALL=C sort -u -o "$package_list" "$package_list"
install -m 0644 "$dependency_list" "$PREFIX/share/r46h/RUNTIME-LIBRARIES.tsv"

while IFS= read -r package; do
  copyright=/usr/share/doc/$package/copyright
  [[ -f $copyright ]] || die "copyright file is missing for $package"
  install -m 0644 "$copyright" "$PREFIX/share/r46h/licenses/$package.copyright"
done < "$package_list"

cat > "$PREFIX/share/r46h/BUILD-INFO" <<EOF
source=ES-DE-v3.4.1
commit=5db4e2a32bd5852cc7a3dbeb298d85de86a536d7
tree=fc0bb596d66ddcc26548edb6a31c075da68e5cd6
renderer=opengles2
deinit_on_launch=on
application_updater=off
video_hw_decoding=off
source_date_epoch=$SOURCE_DATE_EPOCH
EOF
chmod 0644 "$PREFIX/share/r46h/BUILD-INFO"

version_output=$(LD_LIBRARY_PATH="$LIB_DIR" "$PREFIX/bin/es-de" --version)
[[ $version_output == 'ES-DE 3.4.1 (r51)' ]] || \
  die "unexpected ES-DE version output: $version_output"
printf '%s\n' "$version_output" > "$PREFIX/share/r46h/VERSION"
chmod 0644 "$PREFIX/share/r46h/VERSION"

mkdir -p /artifact
find /stage -xdev -exec touch -h -d "@$SOURCE_DATE_EPOCH" {} +
tar --sort=name --format=posix --mtime="@$SOURCE_DATE_EPOCH" --clamp-mtime \
  --owner=0 --group=0 --numeric-owner \
  --pax-option=delete=atime,delete=ctime \
  -C /stage -cf - opt | gzip -n -9 > "$ARTIFACT"
test -s "$ARTIFACT"
