#!/bin/sh
# Optional Linux keyboard runtime, built without installing anything on the host.
set -eu
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
workspace=$(CDPATH= cd -- "$source_dir/../.." && pwd -P)
output="$workspace/mainline/out/.cache/r46h-shell"
archive="$output/keyboard/qtvirtualkeyboard-6.8.2.tar.gz"
expected=8d3a0bf1ca732e49ad74cea67e5e702acaaecd7789f067d584236f59b29c2592
mkdir -p "$output/keyboard" "$output/evidence" "$output/tmp"
if [ ! -f "$archive" ]; then
    curl -fL --retry 2 https://codeload.github.com/qt/qtvirtualkeyboard/tar.gz/refs/tags/v6.8.2 -o "$archive.incoming"
    [ "$(shasum -a 256 "$archive.incoming" | cut -d ' ' -f 1)" = "$expected" ]
    mv "$archive.incoming" "$archive"
fi
[ "$(shasum -a 256 "$archive" | cut -d ' ' -f 1)" = "$expected" ]
container=$(docker create --network bridge --entrypoint /bin/sleep -v "$output:/out" \
    cgutman/moonlight-packaging@sha256:f25a3e2ad90b85d1a4358e2d612ed311165cddd62aa194455a5dbed844d66d69 1800)
trap 'docker rm -f "$container" >/dev/null' EXIT HUP INT TERM
docker start "$container" >/dev/null
docker exec "$container" /bin/bash -c '
set -eu
apt-get update
apt-get install -y --no-install-recommends qt6-base-private-dev=6.8.2+dfsg-9+deb13u2 qt6-declarative-private-dev=6.8.2+dfsg-7 fonts-droid-fallback
dpkg-query -W > /out/evidence/keyboard-packages.txt
' > "$output/evidence/keyboard-setup.log" 2>&1
docker network disconnect bridge "$container"
docker network connect none "$container"
docker exec "$container" /bin/bash -c '
set -Eeuo pipefail
mkdir /source /build /runtime
tar -xzf /out/keyboard/qtvirtualkeyboard-6.8.2.tar.gz -C /source
src=/source/qtvirtualkeyboard-6.8.2
args=()
for lang in $(sed -n "s/.*INPUT_lang_\([A-Za-z_]*\).*/\1/p" "$src/src/virtualkeyboard/configure.cmake" | sort -u); do
    case "$lang" in en_GB|zh_CN|ch_CN) ;; *) args+=("-DINPUT_lang_$lang=no");; esac
done
cmake -S "$src" -B /build -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr \
    -DCMAKE_INSTALL_LIBDIR=lib/aarch64-linux-gnu -DQT_BUILD_TESTS=OFF -DQT_BUILD_EXAMPLES=OFF \
    -DFEATURE_vkb_arrow_keynavigation=ON -DFEATURE_vkb_desktop=OFF \
    -DFEATURE_pinyin=ON -DFEATURE_vkb_lang_zh_CN=ON \
    -DINPUT_vkb_hunspell=no -DINPUT_vkb_handwriting=no "${args[@]}"
cmake --build /build -j4
DESTDIR=/install cmake --install /build
cp /build/config.summary /out/evidence/keyboard-features.txt
lib=usr/lib/aarch64-linux-gnu
mkdir -p /runtime/$lib/qt6 /runtime/usr/share/doc/qtvirtualkeyboard /runtime/usr/share/fonts/truetype/droid
cp -a /install/$lib/libQt6VirtualKeyboard*.so* /runtime/$lib/
cp -a /install/$lib/qt6/plugins /install/$lib/qt6/qml /runtime/$lib/qt6/
cp -a "$src/LICENSES" /runtime/usr/share/doc/qtvirtualkeyboard/
cp "$src/src/plugins/pinyin/3rdparty/pinyin/NOTICE" /runtime/usr/share/doc/qtvirtualkeyboard/pinyin-NOTICE
cp /usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf /runtime/usr/share/fonts/truetype/droid/
cp /usr/share/doc/fonts-droid-fallback/copyright /runtime/usr/share/doc/qtvirtualkeyboard/font-copyright
find /runtime -type f -name "*.so*" -exec strip --strip-unneeded {} +
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -C /runtime -cf - . | gzip -n > /out/keyboard/qtvirtualkeyboard-runtime-arm64.tar.gz.incoming
mv /out/keyboard/qtvirtualkeyboard-runtime-arm64.tar.gz.incoming /out/keyboard/qtvirtualkeyboard-runtime-arm64.tar.gz
sha256sum /out/keyboard/qtvirtualkeyboard-runtime-arm64.tar.gz
' > "$output/evidence/keyboard-build.log" 2>&1
shasum -a 256 "$output/keyboard/qtvirtualkeyboard-runtime-arm64.tar.gz" | cut -d ' ' -f 1 > "$output/keyboard/runtime.sha256"
