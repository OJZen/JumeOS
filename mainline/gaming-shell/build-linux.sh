#!/bin/sh
# Uses the already verified Qt dependency bundle and pinned ARM64 toolchain.
set -eu
source_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
workspace=$(CDPATH= cd -- "$source_dir/../.." && pwd -P)
output="$workspace/mainline/out/.cache/r46h-shell"
baseline="$workspace/mainline/out/.cache/r46h-moonlight-qt/moonlight-qt-candidate.tar.gz"
expected=3e69df3e147c2106aa9f74988bfc0339326ade62793d4ca5c412d3f150178ae8
[ -f "$baseline" ] || { echo 'Prepare the documented Moonlight Qt baseline bundle first.' >&2; exit 1; }
[ "$(shasum -a 256 "$baseline" | cut -d ' ' -f 1)" = "$expected" ]
mkdir -p "$output/tmp" "$output/evidence"
keyboard="$output/keyboard/qtvirtualkeyboard-runtime-arm64.tar.gz"
[ -f "$keyboard" ] && [ -f "$output/keyboard/runtime.sha256" ] || { echo 'Run build-keyboard.sh first.' >&2; exit 1; }
[ "$(shasum -a 256 "$keyboard" | cut -d ' ' -f 1)" = "$(cat "$output/keyboard/runtime.sha256")" ]
portmaster=${R46H_PORTMASTER_BUNDLE:-"$workspace/mainline/out/.cache/r46h-portmaster/portmaster-backend.tar.gz"}
[ -f "$portmaster" ] && [ -f "$(dirname "$portmaster")/runtime.sha256" ] || { echo 'Run gaming-ports/prepare-backend.py first.' >&2; exit 1; }
[ "$(shasum -a 256 "$portmaster" | cut -d ' ' -f 1)" = "$(cat "$(dirname "$portmaster")/runtime.sha256")" ]
native=${R46H_PORT_NATIVE_CACHE:-"$workspace/mainline/out/.cache/r46h-ports-native"}
python3 -B "$workspace/mainline/gaming-ports/prepare-native.py" "$native" --check
gta=${R46H_GTA_SOURCE_OUTPUT:-"$workspace/mainline/out/.cache/r46h-gta-source-r52-20260914"}
[ -f "$gta/BUILD-INFO" ] && [ -f "$gta/SHA256SUMS" ] || { echo 'Run gaming-ports/build-gta-source.sh first.' >&2; exit 1; }
(cd "$gta" && shasum -a 256 -c SHA256SUMS)
docker run --rm --network none --entrypoint /bin/bash \
  -v "$source_dir:/src:ro" -v "$output:/out" -v "$baseline:/qt-baseline.tar.gz:ro" \
  -v "$workspace/mainline/gaming-wayland:/gaming-wayland:ro" \
  -v "$workspace/mainline/gaming-shell:/project/mainline/gaming-shell:ro" \
  -v "$workspace/mainline/gaming-remote-screen:/project/mainline/gaming-remote-screen:ro" \
  -v "$workspace/mainline/gaming-ports:/project/mainline/gaming-ports:ro" -v "$portmaster:/portmaster-backend.tar.gz:ro" \
  -v "$native:/native-debs:ro" -v "$gta:/gta-source:ro" \
  -v "$workspace/mainline/tests:/project/mainline/tests:ro" \
  -v "$output/control-tests:/project/mainline/out/.cache" \
  -e TMPDIR=/out/tmp -e LANG=C.UTF-8 -e QML_DISABLE_DISK_CACHE=1 -e QT_DISABLE_SHADER_DISK_CACHE=1 \
  cgutman/moonlight-packaging@sha256:f25a3e2ad90b85d1a4358e2d612ed311165cddd62aa194455a5dbed844d66d69 -c '
set -Eeuo pipefail
cmake -S /src -B /out/linux-build -DCMAKE_BUILD_TYPE=Release
cmake --build /out/linux-build -j 4
mkdir -p /out/runtime
chmod 700 /out/runtime
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software XDG_RUNTIME_DIR=/out/runtime /out/linux-build/shell-check
/out/linux-build/network-check
/out/linux-build/tools-check
(
permission_dir=$(mktemp -d /out/permission-check.XXXXXX)
trap '\''rm -rf -- "$permission_dir"'\'' EXIT
chown nobody:nogroup "$permission_dir"
runuser -u nobody -- env TMPDIR="$permission_dir" XDG_RUNTIME_DIR="$permission_dir" \
  QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software \
  /out/linux-build/shell-check unreadableDirectoryKeepsExistingPreferences
)
stage=$(mktemp -d /out/package.XXXXXX)
trap '\''rm -rf -- "$stage"; rm -f /out/r46h-shell-preview-arm64.tar.gz.incoming'\'' EXIT
tar -xzf /qt-baseline.tar.gz -C "$stage"
tar -xzf /out/keyboard/qtvirtualkeyboard-runtime-arm64.tar.gz -C "$stage"
rm "$stage/qt-client.sh" "$stage/usr/bin/moonlight-qt"
install -m 755 /out/linux-build/r46h-shell "$stage/usr/bin/r46h-shell"
strip --strip-unneeded "$stage/usr/bin/r46h-shell"
install -m 755 /src/shell-client.sh /src/probe-r46h.sh /src/desktop-session.sh /src/remote-session.sh /src/device-lease.sh /src/memory-control.sh "$stage/"
install -m 644 /src/applications.example.json "$stage/"
bash /project/mainline/gaming-ports/install-runtime.sh "$stage"
lib=usr/lib/aarch64-linux-gnu
# Virtual Keyboard imports this QML module; the SDK previously hid its absence.
mkdir -p "$stage/$lib/qt6/qml/Qt/labs" "$stage/usr/share/doc/qml6-module-qt-labs-folderlistmodel"
cp -a /$lib/qt6/qml/Qt/labs/folderlistmodel "$stage/$lib/qt6/qml/Qt/labs/"
cp -a /$lib/libQt6LabsFolderListModel.so.6* "$stage/$lib/"
cp /usr/share/doc/qml6-module-qt-labs-folderlistmodel/copyright "$stage/usr/share/doc/qml6-module-qt-labs-folderlistmodel/"
cat > "$stage/usr/bin/qt.conf" <<EOF
[Paths]
Prefix=..
Libraries=lib/aarch64-linux-gnu
Plugins=lib/aarch64-linux-gnu/qt6/plugins
QmlImports=lib/aarch64-linux-gnu/qt6/qml
EOF
sha256sum "$stage/usr/bin/r46h-shell" | awk '\''{print $1}'\'' > /out/evidence/linux-binary.sha256
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software XDG_RUNTIME_DIR=/out/runtime "$stage/shell-client.sh" --help
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software XDG_RUNTIME_DIR=/out/runtime \
  LD_LIBRARY_PATH="$stage/usr/lib/aarch64-linux-gnu:$stage/usr/lib/aarch64-linux-gnu/libproxy" \
  python3 -B /project/mainline/tests/test-shell-control.py --binary "$stage/usr/bin/r46h-shell" \
  --ipc-root /run --cycles 3 --evidence /project/mainline/out/.cache/arm64-control
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software XDG_RUNTIME_DIR=/out/runtime \
  LD_LIBRARY_PATH="$stage/usr/lib/aarch64-linux-gnu:$stage/usr/lib/aarch64-linux-gnu/libproxy" \
  python3 -B /project/mainline/tests/test-shell-applications.py --binary "$stage/usr/bin/r46h-shell" \
  --ipc-root /run --evidence /project/mainline/out/.cache/arm64-applications
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software XDG_RUNTIME_DIR=/out/runtime \
  LD_LIBRARY_PATH="$stage/usr/lib/aarch64-linux-gnu:$stage/usr/lib/aarch64-linux-gnu/libproxy" \
  python3 -B /project/mainline/tests/test-shell-handoff.py --binary "$stage/usr/bin/r46h-shell" \
  --ipc-root /run --evidence /project/mainline/out/.cache/arm64-handoff
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software XDG_RUNTIME_DIR=/out/runtime \
  LD_LIBRARY_PATH="$stage/usr/lib/aarch64-linux-gnu:$stage/usr/lib/aarch64-linux-gnu/libproxy" \
  python3 -B /project/mainline/tests/test-shell-tools.py --binary "$stage/usr/bin/r46h-shell" \
  --ipc-root /run --evidence /project/mainline/out/.cache/arm64-tools
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software XDG_RUNTIME_DIR=/out/runtime \
  LD_LIBRARY_PATH="$stage/usr/lib/aarch64-linux-gnu:$stage/usr/lib/aarch64-linux-gnu/libproxy" \
  python3 -B /project/mainline/tests/test-portmaster-ui.py --binary "$stage/usr/bin/r46h-shell" \
  --runtime "$stage/usr/share/r46h/portmaster" --packaged --ipc-root /run --evidence /project/mainline/out/.cache/arm64-portmaster
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software XDG_RUNTIME_DIR=/out/runtime "$stage/shell-client.sh" --scene quick --capture /out/evidence/arm64-package.png
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software XDG_RUNTIME_DIR=/out/runtime R46H_VIRTUAL_KEYBOARD=1 "$stage/shell-client.sh" --scene input --test-input-capture --capture /out/evidence/arm64-keyboard.png
# Run beside qt.conf so missing QML imports cannot fall back to the build SDK.
install -m 755 /out/linux-build/shell-check "$stage/usr/bin/shell-check"
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software XDG_RUNTIME_DIR=/out/runtime \
  R46H_VIRTUAL_KEYBOARD=1 R46H_UI_CAPTURE_DIR=/out/evidence QT_IM_MODULE=qtvirtualkeyboard QT_VIRTUALKEYBOARD_DESKTOP_DISABLE=1 \
  XDG_CONFIG_HOME="$stage/state/config" XDG_DATA_HOME="$stage/state/data" XDG_CACHE_HOME="$stage/state/cache" \
  LD_LIBRARY_PATH="$stage/usr/lib/aarch64-linux-gnu:$stage/usr/lib/aarch64-linux-gnu/libproxy" \
  QT_PLUGIN_PATH="$stage/usr/lib/aarch64-linux-gnu/qt6/plugins" QML_IMPORT_PATH="$stage/usr/lib/aarch64-linux-gnu/qt6/qml" \
  "$stage/usr/bin/shell-check" virtualKeyboardInput
rm "$stage/usr/bin/shell-check"
rm -rf -- "$stage/state"
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -C "$stage" -cf - . | gzip -n > /out/r46h-shell-preview-arm64.tar.gz.incoming
mv /out/r46h-shell-preview-arm64.tar.gz.incoming /out/r46h-shell-preview-arm64.tar.gz
sha256sum /out/r46h-shell-preview-arm64.tar.gz
'
