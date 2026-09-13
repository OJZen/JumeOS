#!/bin/bash
# Run from a clean source snapshot; all cache/build/evidence paths stay external.
set -Eeuo pipefail
trap 'printf "HANDHELD_BUILD_FAILED line=%s status=%s\n" "$LINENO" "$?" >&2' ERR
source_dir=$(cd -- "$(dirname -- "$0")" && pwd -P)
repo=$(git -C "$source_dir" rev-parse --show-toplevel)
[[ $# == 2 || $# == 4 ]] || { echo 'Usage: build-handheld.sh EXISTING_MAINLINE_CACHE NEW_CANDIDATE_OUTPUT [MOONLIGHT_BINARY SHA256]' >&2; exit 2; }
client_bindings=()
if [[ $# == 4 ]]; then
    [[ $3 == /* && $4 =~ ^[0-9a-f]{64}$ && $(shasum -a 256 "$3" | cut -d ' ' -f 1) == "$4" ]]
    client_bindings=(-v "$3:/moonlight-qt:ro" -e "R46H_CLIENT_SHA=$4")
fi
cache=$(cd -- "$1" && pwd -P)
mkdir -p "$2"
output=$(cd -- "$2" && pwd -P)
case "$cache:$output" in /Volumes/*:/Volumes/*) ;; *) echo 'Use the external workspace.' >&2; exit 2;; esac
[[ -z $(git -C "$repo" status --porcelain) && -z $(ls -A "$output") ]]
commit=$(git -C "$repo" rev-parse HEAD)
image=cgutman/moonlight-packaging@sha256:f25a3e2ad90b85d1a4358e2d612ed311165cddd62aa194455a5dbed844d66d69
portmaster=${R46H_PORTMASTER_BUNDLE:-$cache/r46h-portmaster/portmaster-backend.tar.gz}
native=${R46H_PORT_NATIVE_CACHE:-$cache/r46h-ports-native}
[[ -f $portmaster && $(shasum -a 256 "$portmaster" | cut -d ' ' -f 1) == "$(cat "$(dirname "$portmaster")/runtime.sha256")" ]]
python3 -B "$repo/mainline/gaming-ports/prepare-native.py" "$native" --check
# Retained font/client plugins are test inputs; the candidate itself uses the hashed runtime.
mkdir -p "$output/share/fonts/truetype/droid" "$output/qt-wayland"
cp "$cache/r46h-compositor-20260910/share/fonts/truetype/droid/DroidSansFallbackFull.ttf" "$output/share/fonts/truetype/droid/"
cp -R "$cache/r46h-compositor-20260910/qt-wayland/." "$output/qt-wayland/"
docker run --rm --init --network none --memory 1536m --cpus 3 --pids-limit 256 --cap-add SYS_PTRACE \
  --entrypoint /bin/bash --device-cgroup-rule 'c 10:223 rwm' --device-cgroup-rule 'c 13:* rwm' \
  -v "$source_dir:/wayland:ro" -v "$source_dir:/gaming-wayland:ro" \
  -v "$repo/mainline/gaming-shell:/src:ro" -v "$repo/mainline/gaming-shell:/project/mainline/gaming-shell:ro" \
  -v "$repo/mainline/gaming-remote-screen:/project/mainline/gaming-remote-screen:ro" \
  -v "$repo/mainline/gaming-ports:/project/mainline/gaming-ports:ro" -v "$repo/mainline/tests:/project/mainline/tests:ro" \
  -v "$portmaster:/portmaster-backend.tar.gz:ro" -v "$native:/native-debs:ro" \
  -v "$cache/r46h-compositor-20260910/ssh-debs:/ssh-debs:ro" \
  -v "$output:/out" -v "$output/desktop:/project/mainline/out" \
  -v "$cache/r46h-shell/linux-build:/out/linux-build" \
  -v "$cache/r46h-ports-backend-20260910/game-debs:/debs:ro" -v "$cache/r46h-wayland/deb-cache:/wayland-debs:ro" \
  -v "$cache/r46h-wayland/r46h-wayland-preview-arm64.tar.gz:/wayland-runtime.tar.gz:ro" \
  "${client_bindings[@]}" \
  "$image" -c 'set -Eeuo pipefail
    timeout 240 bash /wayland/check-desktop.sh > /out/desktop-check.log 2>&1
    rm /dev/uinput
    timeout 120 bash /wayland/check-session.sh "$1" > /out/session-check.log 2>&1
    rm /dev/uinput
    ln -s /out/r46h-handheld-desktop-arm64.tar.gz /candidate.tar.gz
    timeout 170 bash /wayland/check-remote.sh > /out/remote-check.log 2>&1' -- "$commit"
[[ -z $(git -C "$repo" status --porcelain) && $(git -C "$repo" rev-parse HEAD) == "$commit" ]]
git -C "$repo" archive --format=tar.gz --output="$output/r46h-source.tar.gz" "$commit" AGENTS.md docs mainline
python3 -B - "$output" "$image" <<'PY'
import hashlib, json, pathlib, sys
out = pathlib.Path(sys.argv[1]); path = out / 'receipt.json'; record = json.loads(path.read_text())
def entry(p): return {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
record.update(sdk=sys.argv[2], artifacts={name: entry(out / name) for name in ['r46h-source.tar.gz', 'r46h-handheld-desktop-arm64.tar.gz']},
              evidence={str(p.relative_to(out)): entry(p) for p in [out / 'desktop-check.log', out / 'session-check.log',
                        out / 'desktop/result.json', out / 'session/result.json', out / 'session/windows-check.log']})
for name in ('desktop/shared-stream-result.json', 'desktop/frame-metrics.json', 'desktop/game-frame-hud.png', 'desktop/stream-stats-panel.png', 'session/power-exits.json',
             'stream-session/result.json', 'moonlight-help.log'):
    if (out / name).exists(): record['evidence'][name] = entry(out / name)
for directory in ('remote', 'desktop/packaged-catalog'):
    for p in sorted((out / directory).rglob('*')):
        if p.is_file(): record['evidence'][str(p.relative_to(out))] = entry(p)
record['evidence']['remote-check.log'] = entry(out / 'remote-check.log')
temporary = path.with_suffix('.json.incoming'); temporary.write_text(json.dumps(record, indent=2) + '\n'); temporary.replace(path)
print(json.dumps(record, indent=2))
PY
