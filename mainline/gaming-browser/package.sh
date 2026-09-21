#!/bin/bash
set -Eeuo pipefail
[[ -f /.dockerenv && -d /out && -d /src ]] || exit 2
export TMPDIR=/out/tmp
cmake -S /src -B /out/build -DCMAKE_BUILD_TYPE=Release
cmake --build /out/build -j 3
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software /out/build/browser-check > /out/input-check.log 2>&1
stage=$(mktemp -d /out/package.XXXXXX)
chmod 755 "$stage"
deps=$(mktemp -d /out/deps.XXXXXX)
trap 'rm -rf -- "$stage" "$deps"; rm -f /out/jume-browser-arm64.tar.gz.incoming' EXIT
tar -xzf /shell-runtime/r46h-shell-preview-arm64.tar.gz -C "$stage" \
    ./usr/lib ./usr/share/fonts ./usr/share/doc ./usr/bin/qt.conf
: > /out/dependencies.sha256
for package in /out/apt/*.deb; do
    name=$(dpkg-deb -f "$package" Package)
    version=$(dpkg-deb -f "$package" Version)
    [[ $version == "$(dpkg-query -W -f='${Version}' "$name" 2>/dev/null)" ]] || continue
    dpkg-deb -x "$package" "$deps"
    sha256sum "$package" >> /out/dependencies.sha256
done
mkdir -p "$stage/usr/share/doc" "$stage/usr/share/qt6"
cp -a "$deps/usr/lib/." "$stage/usr/lib/"
cp -a "$deps/usr/share/qt6/." "$stage/usr/share/qt6/"
cp -a "$deps/usr/share/doc/." "$stage/usr/share/doc/"
# Only runtime objects, not SDK linkage/configuration, belong in this optional bundle.
find "$stage/usr/lib" -type f \( -name '*.a' -o -name '*.prl' -o -name '*.cmake' -o -name '*.pc' \) -delete
install -m 755 /out/build/jume-browser "$stage/usr/bin/"
install -m 755 /src/browser-client.sh "$stage/"
strip --strip-unneeded "$stage/usr/bin/jume-browser"
LD_LIBRARY_PATH="$stage/usr/lib/aarch64-linux-gnu:$stage/usr/lib/aarch64-linux-gnu/libproxy" ldd "$stage/usr/bin/jume-browser" > /out/linkage.txt
if grep -q 'not found' /out/linkage.txt; then cat /out/linkage.txt >&2; exit 1; fi
LD_LIBRARY_PATH="$stage/usr/lib/aarch64-linux-gnu:$stage/usr/lib/aarch64-linux-gnu/libproxy" "$stage/usr/bin/jume-browser" --engine-versions > "$stage/engine-versions.json"
cp "$stage/engine-versions.json" /out/engine-versions.json
# Fail closed if packaging accidentally resolves the SDK's older engine.
python3 -c 'import json; v=json.load(open("/out/engine-versions.json")); assert v == {"webEngine":"6.10.2", "chromium":"134.0.6998.208", "securityPatch":"144.0.7559.96"}, v'
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -C "$stage" -cf - . | gzip -n > /out/jume-browser-arm64.tar.gz.incoming
mv /out/jume-browser-arm64.tar.gz.incoming /out/jume-browser-arm64.tar.gz
sha256sum /out/jume-browser-arm64.tar.gz > /out/runtime.sha256
