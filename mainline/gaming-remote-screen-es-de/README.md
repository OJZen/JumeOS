# R46H ES-DE screenshot compatibility v0.1

Status: **HISTORICAL PAYLOAD HOST + TARGET PASS / CURRENT REBUILD BLOCKED**

The accepted installed payload predates the anchored process-guard source now
used by p2 v0.16+. The standalone builder copies that newer source, but
`install.sh` and `rollback.sh` still pin the old helper hash. Consequently the
current rebuild cannot pass installation, and
`test-r46h-gaming-remote-screen-es-de.py` has two failing contract checks.
Reconcile a versioned standalone payload only if it is needed again; do not
loosen its guards. The consolidated successor is owned by
[p2 v0.17](../rootfs-debian13-gaming-v17/README.md).

This p2-only overlay keeps the accepted remote-screen v0.1 SSH gateway, key,
sudo policy and export protocol. It changes only the DRM capture binary and its
unprivileged guard so one frame can be captured from either Ozone/RetroArch or
ES-DE. ES-DE uses linear ARGB8888 scanout; the RGB byte layout is identical to
the already accepted linear XRGB8888 path, so alpha is ignored.

Historical build/test entry points (the mismatch above must be resolved before
rebuilding for deployment):

```sh
mainline/gaming-remote-screen-es-de/build-payload.sh
R46H_TEST_TMPDIR=mainline/out/.cache/r46h-tests \
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/tests/test-r46h-gaming-remote-screen-es-de.py
```

The historical install contract stages six payload files under
`/run/r46h-remote-screen-es-de-v0.1`: root-owned mode 0600 inside a root-owned
mode 0700 directory, followed by the installer with its exact SHA-256.
The transaction does not restart the frontend
and preserves byte-exact v0.1 capture/helper files in its rollback state.

Acceptance requires a strict-key `fetch-screen.py` capture of the ES-DE system
view, exact host PNG validation/removal, unchanged frontend PID/restart count,
zero ext4/failed-unit errors and read-only `/roms`. Run
`sudo /usr/local/sbin/r46h-remote-screen-es-de-rollback` before rolling ES-DE
back to Ozone.

On 2026-09-03 the current card again passed install after the ES-DE profile
updates. Strict-key system and game-list captures passed exact host validation
and removal without changing the frontend PID or restart count; zero errors and
read-only `/roms` remained unchanged. A settled post-reboot system capture also
passed. Only operator LCD comparison remains.
