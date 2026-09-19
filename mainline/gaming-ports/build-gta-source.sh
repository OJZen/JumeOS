#!/bin/bash
# Build source-bound ARM64 re3/reVC candidates; no game assets are included.
set -Eeuo pipefail
[[ $# == 2 && -d $1 && ! -L $1 && ! -e $2 ]] || {
  echo 'Usage: build-gta-source.sh INPUT_CACHE NEW_OUTPUT_DIRECTORY' >&2; exit 2;
}
base=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd -P)
inputs=$(CDPATH= cd -- "$1" && pwd -P)
output=$2
case "$inputs" in "$base/mainline/out/"*) ;; *) echo 'Input cache must be under mainline/out.' >&2; exit 2;; esac
case "$output" in "$base/mainline/out/"*) ;; *) echo 'Output must be under mainline/out.' >&2; exit 2;; esac
native=${R46H_PORT_NATIVE_CACHE:-"$base/mainline/out/.cache/r46h-ports-native"}
profile=${R46H_GTA_IMMEDIATE_PROFILE:-0}
ring=${R46H_GTA_IMMEDIATE_RING:-1}
frame_profile=${R46H_GTA_FRAME_PROFILE:-0}
swap_nowait=${R46H_GTA_SWAP_NOWAIT:-0}
simple_cutscene_shadows=${R46H_GTA_SIMPLE_CUTSCENE_SHADOWS:-1}
[[ $profile == 0 || $profile == 1 ]] || { echo 'R46H_GTA_IMMEDIATE_PROFILE must be 0 or 1.' >&2; exit 2; }
[[ $ring == 0 || $ring == 1 ]] || { echo 'R46H_GTA_IMMEDIATE_RING must be 0 or 1.' >&2; exit 2; }
[[ $frame_profile == 0 || $frame_profile == 1 ]] || { echo 'R46H_GTA_FRAME_PROFILE must be 0 or 1.' >&2; exit 2; }
[[ $swap_nowait == 0 || $swap_nowait == 1 ]] || { echo 'R46H_GTA_SWAP_NOWAIT must be 0 or 1.' >&2; exit 2; }
[[ $simple_cutscene_shadows == 0 || $simple_cutscene_shadows == 1 ]] || { echo 'R46H_GTA_SIMPLE_CUTSCENE_SHADOWS must be 0 or 1.' >&2; exit 2; }
(( profile + ring <= 1 )) || { echo 'Immediate profiling and ring upload are separate candidates.' >&2; exit 2; }
PYTHONDONTWRITEBYTECODE=1 python3 -B "$base/mainline/gaming-ports/prepare-gta-source.py" "$inputs" --check
PYTHONDONTWRITEBYTECODE=1 python3 -B "$base/mainline/gaming-ports/prepare-native.py" "$native" --check
mkdir -p "$output"
docker run --rm --network none --entrypoint /bin/bash \
  -v "$inputs:/inputs:ro" -v "$native:/native:ro" -v "$output:/out" \
  -v "$base/mainline/gaming-ports/librw-context-fallback.patch:/librw-context-fallback.patch:ro" \
  -v "$base/mainline/gaming-ports/librw-immediate-profile.patch:/librw-immediate-profile.patch:ro" \
  -v "$base/mainline/gaming-ports/librw-immediate-ring.patch:/librw-immediate-ring.patch:ro" \
  -v "$base/mainline/gaming-ports/revc-frame-profile.patch:/revc-frame-profile.patch:ro" \
  -v "$base/mainline/gaming-ports/revc-simple-cutscene-shadows.patch:/revc-simple-cutscene-shadows.patch:ro" \
  -v "$base/mainline/gaming-ports/librw-swap-nowait.patch:/librw-swap-nowait.patch:ro" \
  -v "$base/mainline/gaming-ports/r46h-gta-runtime.patch:/r46h-gta-runtime.patch:ro" \
  -e R46H_GTA_IMMEDIATE_PROFILE="$profile" -e R46H_GTA_IMMEDIATE_RING="$ring" \
  -e R46H_GTA_FRAME_PROFILE="$frame_profile" \
  -e R46H_GTA_SWAP_NOWAIT="$swap_nowait" \
  -e R46H_GTA_SIMPLE_CUTSCENE_SHADOWS="$simple_cutscene_shadows" \
  cgutman/moonlight-packaging@sha256:f25a3e2ad90b85d1a4358e2d612ed311165cddd62aa194455a5dbed844d66d69 -c '
set -Eeuo pipefail
work=/out/.build
mkdir "$work"
trap '\''rm -rf -- "$work"; rm -f /out/re3.incoming /out/reVC.incoming /out/SHA256SUMS.incoming /out/BUILD-INFO.incoming'\'' EXIT
tar -xzf /inputs/re3-ead2747.tar.gz -C "$work"
tar -xzf /inputs/revc-b9f0b23.tar.gz -C "$work"
tar -xzf /inputs/librw-81c9426.tar.gz -C "$work"
re3="$work/re3-ead2747eadbbdbf0e134eea6679364153dd6c4b8"
revc="$work/re3-b9f0b23466ab4db76615cc2c761df9013a838184"
librw="$work/librw-81c9426cdde73717b04ae4dfc0f6c255f74a3a8a"
for source in "$re3" "$revc"; do
  patch --batch --forward -d "$source" -p1 < /r46h-gta-runtime.patch
  mkdir -p "$source/vendor"
  rm -rf "$source/vendor/librw"
  cp -a "$librw" "$source/vendor/librw"
  patch --batch --forward -d "$source/vendor/librw" -p1 < /librw-context-fallback.patch
  if [[ ${R46H_GTA_IMMEDIATE_PROFILE:-0} == 1 ]]; then
    patch --batch --forward -d "$source/vendor/librw" -p1 < /librw-immediate-profile.patch
  fi
  if [[ ${R46H_GTA_IMMEDIATE_RING:-0} == 1 ]]; then
    patch --batch --forward -d "$source/vendor/librw" -p1 < /librw-immediate-ring.patch
  fi
  if [[ ${R46H_GTA_SWAP_NOWAIT:-0} == 1 ]]; then
    patch --batch --forward -d "$source/vendor/librw" -p1 < /librw-swap-nowait.patch
  fi
done
if [[ ${R46H_GTA_FRAME_PROFILE:-0} == 1 ]]; then
  patch --batch --forward -d "$revc" -p1 < /revc-frame-profile.patch
fi
if [[ ${R46H_GTA_SIMPLE_CUTSCENE_SHADOWS:-0} == 1 ]]; then
  patch --batch --forward -d "$revc" -p1 < /revc-simple-cutscene-shadows.patch
fi
sysroot="$work/sysroot"
mkdir -p "$sysroot"
for package in /native/libopenal1.deb /native/libmpg123.deb /inputs/libopenal-dev_1%3a1.24.2-1_arm64.deb /inputs/libmpg123-dev_1.32.10-1+deb13u1_arm64.deb; do
  dpkg-deb -x "$package" "$sysroot"
done
common=(-DLIBRW_PLATFORM=GL3 -DLIBRW_GL3_GFXLIB=SDL2 -DLIBRW_FORCE_GLES=ON -DCMAKE_BUILD_TYPE=Release
  -DCMAKE_C_FLAGS=-DMASTER -DCMAKE_CXX_FLAGS=-DMASTER
  -DOPENAL_INCLUDE_DIR="$sysroot/usr/include" -DOPENAL_LIBRARY="$sysroot/usr/lib/aarch64-linux-gnu/libopenal.so"
  -Dmpg123_INCLUDE_DIR="$sysroot/usr/include/aarch64-linux-gnu" -Dmpg123_LIBRARIES="$sysroot/usr/lib/aarch64-linux-gnu/libmpg123.so")
cmake -S "$re3" -B "$work/build-re3" "${common[@]}" -DRE3_SNES_PAD=ON > /out/re3-configure.log.incoming 2>&1
cmake --build "$work/build-re3" -j 4 > /out/re3-build.log.incoming 2>&1
cmake -S "$revc" -B "$work/build-revc" "${common[@]}" -DREVC_SNES_PAD=ON > /out/revc-configure.log.incoming 2>&1
cmake --build "$work/build-revc" -j 4 > /out/revc-build.log.incoming 2>&1
install -m 0755 "$work/build-re3/src/re3" /out/re3.incoming
install -m 0755 "$work/build-revc/src/reVC" /out/reVC.incoming
for binary in /out/re3.incoming /out/reVC.incoming; do
  strings_file="$work/$(basename "$binary").strings"
  strings "$binary" > "$strings_file"
  if grep -Fq "Show Timebars" "$strings_file" || grep -Fq "Debug Render" "$strings_file"; then
    echo "Release GTA binary retained development instrumentation: $binary" >&2
    exit 1
  fi
done
strip --strip-unneeded /out/re3.incoming /out/reVC.incoming
mv /out/re3-configure.log.incoming /out/re3-configure.log
mv /out/re3-build.log.incoming /out/re3-build.log
mv /out/revc-configure.log.incoming /out/revc-configure.log
mv /out/revc-build.log.incoming /out/revc-build.log
mv /out/re3.incoming /out/re3
mv /out/reVC.incoming /out/reVC
printf '\''re3_source=ead2747eadbbdbf0e134eea6679364153dd6c4b8\nrevc_source=b9f0b23466ab4db76615cc2c761df9013a838184\nlibrw_source=81c9426cdde73717b04ae4dfc0f6c255f74a3a8a\nbuild_profile=MASTER_RELEASE\npatch_sha256=%s\nruntime_patch_sha256=%s\n'\'' "$(sha256sum /librw-context-fallback.patch | cut -d '\'' '\'' -f 1)" "$(sha256sum /r46h-gta-runtime.patch | cut -d '\'' '\'' -f 1)" > /out/BUILD-INFO.incoming
if [[ ${R46H_GTA_IMMEDIATE_PROFILE:-0} == 1 ]]; then
  printf '\''immediate_profile_patch_sha256=%s\n'\'' "$(sha256sum /librw-immediate-profile.patch | cut -d '\'' '\'' -f 1)" >> /out/BUILD-INFO.incoming
fi
if [[ ${R46H_GTA_IMMEDIATE_RING:-0} == 1 ]]; then
  printf '\''immediate_ring_patch_sha256=%s\n'\'' "$(sha256sum /librw-immediate-ring.patch | cut -d '\'' '\'' -f 1)" >> /out/BUILD-INFO.incoming
fi
if [[ ${R46H_GTA_FRAME_PROFILE:-0} == 1 ]]; then
  printf '\''revc_frame_profile_patch_sha256=%s\n'\'' "$(sha256sum /revc-frame-profile.patch | cut -d '\'' '\'' -f 1)" >> /out/BUILD-INFO.incoming
fi
if [[ ${R46H_GTA_SWAP_NOWAIT:-0} == 1 ]]; then
  printf '\''swap_nowait_patch_sha256=%s\n'\'' "$(sha256sum /librw-swap-nowait.patch | cut -d '\'' '\'' -f 1)" >> /out/BUILD-INFO.incoming
fi
if [[ ${R46H_GTA_SIMPLE_CUTSCENE_SHADOWS:-0} == 1 ]]; then
  printf '\''simple_cutscene_shadows_patch_sha256=%s\n'\'' "$(sha256sum /revc-simple-cutscene-shadows.patch | cut -d '\'' '\'' -f 1)" >> /out/BUILD-INFO.incoming
fi
(cd /out && sha256sum re3 reVC > SHA256SUMS.incoming)
mv /out/BUILD-INFO.incoming /out/BUILD-INFO
mv /out/SHA256SUMS.incoming /out/SHA256SUMS
'
