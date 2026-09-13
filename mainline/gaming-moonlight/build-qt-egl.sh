#!/bin/bash
# Build v4, or opt-in v5 statistics, from retained v2 with EGL preference.
set -Eeuo pipefail
[[ $# == 0 || $# == 1 && $1 == --stats ]] || exit 2
revision=4
[[ $# == 0 ]] || revision=5
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd -P)
out=$repo/mainline/out/.cache/r46h-moonlight-qt/revision-v$revision
[[ ! -e $out/moonlight-qt-v$revision ]] || { echo "Refusing to overwrite retained client." >&2; exit 1; }
source_tar=$repo/mainline/out/.cache/r46h-moonlight-qt/revision-v2/moonlight-qt-r46h-v2-source.tar.gz
expected=b1e730153f610ef7d5406db0d989a7c5dec00119785a173720a3c3ebeda9a295
[[ $(shasum -a 256 "$source_tar" | cut -d ' ' -f 1) == "$expected" ]]
git -C "$repo" diff --quiet && git -C "$repo" diff --cached --quiet || { echo 'Build requires clean committed inputs.' >&2; exit 1; }
git -C "$repo" ls-files --error-unmatch mainline/gaming-moonlight/qt-listapps.patch mainline/tests/test-moonlight-list.py >/dev/null
if [[ $revision == 5 ]]; then
    git -C "$repo" ls-files --error-unmatch mainline/gaming-moonlight/qt-stats.patch mainline/gaming-shell/streamstats.h mainline/tests/test-moonlight-stats.py >/dev/null
fi
mkdir -p "$out"
work=$(mktemp -d "$out/build.XXXXXX")
trap 'rm -rf -- "$work"' EXIT
tar -xzf "$source_tar" -C "$work"
patch --batch --fuzz=0 -d "$work/moonlight-qt" -p1 < "$repo/mainline/gaming-moonlight/qt-listapps.patch"
if [[ $revision == 5 ]]; then
    patch --batch --fuzz=0 -d "$work/moonlight-qt" -p1 < "$repo/mainline/gaming-moonlight/qt-stats.patch"
    cp "$repo/mainline/gaming-shell/streamstats.h" "$work/moonlight-qt/app/streaming/video/"
fi
docker run --rm --network none --entrypoint /bin/bash \
  -v "$work/moonlight-qt:/src:ro" -v "$work:/work" -v "$out:/out" \
  -v "$repo/mainline/tests:/tests:ro" -e TMPDIR=/work -e R46H_CLIENT_REVISION="$revision" \
  cgutman/moonlight-packaging@sha256:f25a3e2ad90b85d1a4358e2d612ed311165cddd62aa194455a5dbed844d66d69 -c '
set -Eeuo pipefail
mkdir /work/output
cd /work/output
qmake6 PREFIX=/usr CONFIG+=vkslow /src/moonlight-qt.pro
make -j4 release
python3 -B /tests/test-moonlight-qt-patch.py /src /out/patch-check
python3 -B /tests/test-moonlight-list.py /src /out/list-check
if [[ $R46H_CLIENT_REVISION == 5 ]]; then python3 -B /tests/test-moonlight-stats.py /src /out/stats-check > /out/stats-check.log; fi
python3 -B - <<"PY"
from pathlib import Path
flags=Path("app/Makefile.Release").read_text()
assert "-DHAVE_EGL" in flags and "-DHAVE_DRM" in flags and "-DVULKAN_IS_SLOW" in flags
assert "-DGL_IS_SLOW" not in flags
Path("/out/renderer-check.log").write_text("EGL_PREFERENCE_BUILD_PASS: HAVE_EGL/HAVE_DRM; VULKAN_IS_SLOW only; no GL_IS_SLOW\n")
PY
install -m 755 app/moonlight /out/moonlight-qt-v$R46H_CLIENT_REVISION.incoming
strip --strip-unneeded /out/moonlight-qt-v$R46H_CLIENT_REVISION.incoming
mkdir -p /work/runtime /work/private
chmod 700 /work/runtime /work/private
set +e
QT_QPA_PLATFORM=offscreen XDG_RUNTIME_DIR=/work/runtime XDG_CONFIG_HOME=/work/private \
  timeout 15 /out/moonlight-qt-v$R46H_CLIENT_REVISION.incoming pair 127.0.0.2 --pin 0000 >/dev/null 2>&1
result=$?
set -e
[[ $result == 1 ]]
printf "UNREACHABLE_PAIR_EXIT=1\n" > /out/cli-check.log
mv /out/moonlight-qt-v$R46H_CLIENT_REVISION.incoming /out/moonlight-qt-v$R46H_CLIENT_REVISION
sha256sum /out/moonlight-qt-v$R46H_CLIENT_REVISION
'
python3 -B - "$repo" "$out" "$expected" "$revision" <<'PY'
from pathlib import Path
import hashlib,json,sys,subprocess
repo,out=map(Path,sys.argv[1:3]); revision=int(sys.argv[4])
def entry(path):return {'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
report={'revision':revision,'status':'EGL_LIST_STATS_HOST_PASS_R46H_UNTESTED' if revision==5 else 'EGL_LIST_FIX_HOST_PASS_R46H_UNTESTED',
 'source_commit':subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
 'list_patch':entry(repo/'mainline/gaming-moonlight/qt-listapps.patch'),
 'source_v2_sha256':sys.argv[3],
 'builder':'cgutman/moonlight-packaging@sha256:f25a3e2ad90b85d1a4358e2d612ed311165cddd62aa194455a5dbed844d66d69',
 'configuration':'CONFIG+=vkslow; fresh pinned-certificate CLI application query',
 'artifacts':{p.name:entry(p) for p in [out/f'moonlight-qt-v{revision}',out/'renderer-check.log',out/'cli-check.log']},
 'recipe':entry(repo/'mainline/gaming-moonlight/build-qt-egl.sh'),
 'boundary':'Compiled renderer preference and existing SPS/quit/CLI checks only; v4 device list/renderer/A-V retest pending. V3 fallback retained; no audio or decoder policy change.'}
if revision==5:
 report['stats_patch']=entry(repo/'mainline/gaming-moonlight/qt-stats.patch')
 report['stats_protocol']=entry(repo/'mainline/gaming-shell/streamstats.h')
 report['artifacts']['stats-check.log']=entry(out/'stats-check.log')
 report['artifacts']['stats-check/result.json']=entry(out/'stats-check/result.json')
 report['boundary']='Native formatter/protocol, pipe safety and existing build/CLI checks only. No actual stream statistics, Hantro, audio-output or R46H acceptance; v3/v4 retained.'
(out/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
PY
