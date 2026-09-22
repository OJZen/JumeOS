#!/bin/bash
# Package assembly in an isolated SDK; never installs services or changes the host.
set -Eeuo pipefail
[[ -f /.dockerenv && $# == 2 && -d $1 && ! -L $1 ]] || exit 2
case "$1" in /out/*|/run/*) ;; *) exit 2;; esac
code=$(cd -- "$(dirname -- "$0")" && pwd -P)
python3 -B "$code/prepare-peripherals.py" "$2" --check
stage=$1
temporary=$(mktemp -d /out/peripherals-package.XXXXXX)
trap 'rm -rf -- "$temporary"' EXIT
# Exact allowlist: never extract an unverified extra .deb from the cache.
for package in foot_1.21.0-2_arm64.deb libfcft4t64_3.3.1-1_arm64.deb \
    libutf8proc3_2.9.0-1+b2_arm64.deb ncurses-term_6.5+20250216-2_all.deb \
    dmz-cursor-theme_0.4.5.2_all.deb fonts-dejavu-mono_2.37-8_all.deb; do
    dpkg-deb -x "$2/$package" "$temporary"
done
mkdir -p "$stage/usr/bin" "$stage/usr/lib/aarch64-linux-gnu" "$stage/usr/share/"{doc,icons,terminfo}
install -m 755 "$temporary/usr/bin/foot" "$stage/usr/bin/"
install -m 755 "$code/terminal-shell.sh" "$stage/"
install -m 644 "$code/terminal-fonts.conf" "$stage/"
mkdir -p "$stage/usr/share/fonts"
cp -a "$temporary/usr/share/fonts/." "$stage/usr/share/fonts/"
cp -a "$temporary/usr/lib/aarch64-linux-gnu/"{libfcft.so*,libutf8proc.so*} "$stage/usr/lib/aarch64-linux-gnu/"
cp -a "$temporary/usr/share/icons/DMZ-White" "$stage/usr/share/icons/"
cp -a "$temporary/usr/share/terminfo/." "$stage/usr/share/terminfo/"
for package in foot libfcft4t64 libutf8proc3 ncurses-term dmz-cursor-theme fonts-dejavu-mono; do
    cp -a "$temporary/usr/share/doc/$package" "$stage/usr/share/doc/"
done
LD_LIBRARY_PATH="$stage/usr/lib/aarch64-linux-gnu" ldd "$stage/usr/bin/foot" > /out/terminal-linkage.log
! grep -q 'not found' /out/terminal-linkage.log
