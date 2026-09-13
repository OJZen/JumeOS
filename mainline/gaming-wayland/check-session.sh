#!/bin/bash
# Reuse the retained runtime; an optional clean source commit freezes a candidate.
set -Eeuo pipefail
trap 'printf "HANDHELD_SESSION_FAILED line=%s status=%s\n" "$LINENO" "$?" >&2' ERR
[[ -f /.dockerenv && -d /wayland && -d /out ]] || exit 2
[[ $# == 0 || ( $# == 1 && $1 =~ ^[0-9a-f]{40}$ ) ]] || exit 2
[[ $(sha256sum /wayland-runtime.tar.gz | cut -d ' ' -f 1) == 355a2913ed11eaab8300f4de13de88b82b2e7413c59a776f5e5d5a0e8faecf50 ]]
stage=$(mktemp -d /run/r46h-handheld-package.XXXXXX)
trap 'rm -rf -- "$stage"; rm -f /out/r46h-handheld-desktop-arm64.tar.gz.incoming' EXIT
chmod 755 "$stage"
tar -xzf /wayland-runtime.tar.gz -C "$stage"
install -m 755 /out/linux-build/r46h-shell "$stage/usr/bin/"
install -m 755 /out/input-router "$stage/usr/bin/"
install -m 755 /out/handheld-shell.so "$stage/usr/lib/aarch64-linux-gnu/weston/"
install -m 755 /wayland/session.sh /wayland/session-leases.sh /wayland/clients.sh /wayland/handheld-client.sh /wayland/probe-r46h.sh /src/shell-client.sh /src/remote-session.sh /src/device-lease.sh "$stage/"
bash /project/mainline/gaming-ports/install-runtime.sh "$stage"
QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software timeout 45 python3 -B /project/mainline/tests/test-portmaster-ui.py \
  --binary "$stage/usr/bin/r46h-shell" --runtime "$stage/usr/share/r46h/portmaster" \
  --packaged --ipc-root /run --evidence /project/mainline/out/packaged-catalog
strip --strip-unneeded "$stage/usr/bin/r46h-shell" "$stage/usr/bin/input-router" "$stage/usr/lib/aarch64-linux-gnu/weston/handheld-shell.so"
find "$stage" -type d -exec chmod a+rx,go-w {} +
find "$stage" -type f -exec chmod a+r,go-w {} +
mknod /dev/uinput c 10 223
timeout 45 python3 -B /wayland/test-session.py "$stage"
# Retain the original two-window profile as a working display fallback.
windows=$(mktemp -d /run/r46h-windows.XXXXXX)
if ! timeout 20 "$stage/session.sh" headless "$windows" > /out/session/windows-check.log 2>&1; then
    cp "$windows/clients.log" /out/session/windows-clients.log
    rm -rf -- "$windows"
    exit 1
fi
rm -rf -- "$windows"
if [[ -n ${R46H_CLIENT_SHA:-} ]]; then
    [[ $R46H_CLIENT_SHA =~ ^[0-9a-f]{64}$ && $(sha256sum /moonlight-qt | cut -d ' ' -f 1) == "$R46H_CLIENT_SHA" ]]
    install -m 755 /moonlight-qt "$stage/usr/bin/moonlight-qt"
    printf '%s\n' "$R46H_CLIENT_SHA" > "$stage/MOONLIGHT_SHA256"
    chmod 644 "$stage/MOONLIGHT_SHA256"
    # Check the actual private client runtime without starting any network session.
    R46H_SHELL_STATE_DIR="$stage/client-check" QT_QPA_PLATFORM=offscreen "$stage/shell-client.sh" --check-state
    install -d -m 700 "$stage/client-check/runtime"
    XDG_CONFIG_HOME="$stage/client-check/config" XDG_DATA_HOME="$stage/client-check/data" XDG_CACHE_HOME="$stage/client-check/cache" \
      XDG_RUNTIME_DIR="$stage/client-check/runtime" LANG=C.UTF-8 \
      QT_QPA_PLATFORM=offscreen QT_QUICK_BACKEND=software LD_LIBRARY_PATH="$stage/usr/lib/aarch64-linux-gnu:$stage/usr/lib/aarch64-linux-gnu/libproxy" \
      "$stage/usr/bin/moonlight-qt" --help > /out/moonlight-help.log 2>&1
    rm -rf -- "$stage/client-check"
    timeout 45 python3 -B /wayland/test-session.py "$stage" --stream-ui
fi
if [[ $# == 1 ]]; then
    [[ ! -e /out/r46h-handheld-desktop-arm64.tar.gz && ! -e /out/receipt.json ]]
    python3 -B - "$stage" "$1" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
manifest = ''.join(f'{digest(f)}  {f.relative_to(root)}\n' for f in sorted(root.rglob('*'))
                   if f.is_file() and not f.is_symlink() and f != root / 'SHA256SUMS')
(root / 'SHA256SUMS').write_text(manifest)
record = {'revision': 49, 'status': 'SHARED_GTA_OVERLAY_HOST_PASS_R46H_UNTESTED',
          'source_commit': sys.argv[2], 'base_runtime_sha256': digest(pathlib.Path('/wayland-runtime.tar.gz')),
          'manifest_sha256': digest(root / 'SHA256SUMS'),
          'binaries': {str(f.relative_to(root)): digest(f) for f in [root / 'usr/bin/r46h-shell', root / 'usr/bin/input-router',
                       root / 'usr/lib/r46h-ports/re3', root / 'usr/lib/r46h-ports/reVC',
                       root / 'usr/lib/aarch64-linux-gnu/weston/handheld-shell.so']},
          'moonlight_sha256': (root / 'MOONLIGHT_SHA256').read_text().strip() if (root / 'MOONLIGHT_SHA256').exists() else None,
          'boundary': 'Headless diagnostic and optional management UI; shared stream uses a fake transport. No R46H DRM/input/audio, target cgroup/seatd or actual Moonlight stream acceptance.'}
pathlib.Path('/out/receipt.json.incoming').write_text(json.dumps(record, indent=2) + '\n')
PY
    tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -C "$stage" -cf - . | gzip -n > /out/r46h-handheld-desktop-arm64.tar.gz.incoming
    mv /out/r46h-handheld-desktop-arm64.tar.gz.incoming /out/r46h-handheld-desktop-arm64.tar.gz
    mv /out/receipt.json.incoming /out/receipt.json
fi
