# R46H guarded remote screen

Status: **V0.16 ANCHORED GUARD DEVICE PASS**

This p2-only successor to the accepted Ozone/FBNeo update captures one current
1024x768 frame, transfers it through one forced-command SSH key, verifies the
PNG on the host, then removes only that exact target export. It does not change
BOOT, kernel, packages, p3, ROMs, RetroArch configuration, the Ozone launcher,
renderer, audio, volume or input.

## Why this implementation

The first target experiment used RetroArch's guarded stdin `SCREENSHOT`
command. Both ordinary and GPU screenshot settings returned the same valid but
all-black PNG on the accepted Ozone `gl`/KMS menu. Each candidate rolled back
exactly, so that path is rejected rather than retained as dead configuration.

A bounded target probe then read the active DRM framebuffer and produced a
correct Ozone menu PNG. The product path therefore uses a small pinned AArch64
helper instead of modifying RetroArch:

```text
strict public-key SSH
  -> fixed unprivileged gateway/helper
  -> no-argument sudo rule for one root-owned capture binary
  -> active CRTC + linear XR24/AR24 framebuffer read
  -> privileges dropped permanently to ark
  -> private PNG export
  -> size, SHA-256, PNG structure and CRC verification
  -> exact target export removal
```

The helper queries the active CRTC and framebuffer with libdrm. It first tries
DMA-BUF export and falls back to the target-proven dumb-buffer map. Access is
limited to one 1024x768 linear XRGB8888 or ARGB8888 frame. Alpha is ignored;
both formats have the same little-endian RGB byte layout. The
[DRM GETFB2 UAPI](https://docs.kernel.org/6.18/gpu/drm-uapi.html) restricts
framebuffer handle disclosure to DRM master or `CAP_SYS_ADMIN`, so a tiny
privileged reader is necessary on this stack; PNG compression and output happen
only after it clears supplementary groups, switches permanently to `ark`, and
enables `PR_SET_NO_NEW_PRIVS`.

## Security and rollback boundary

- The sudoers entry authorizes only the exact root-owned binary with no
  arguments. The binary independently requires the fixed `ark` sudo identity,
  its own safe inode and one empty mode-0600 `ark` stdout file.
- RetroArch's unauthenticated network-command listener stays disabled. No new
  service, socket or recording loop is added.
- The SSH key is restricted to capture, exact name/size/hash-bound read, or
  exact removal. PTY, forwarding, password fallback and host-key updates are
  disabled.
- At most eight complete pending exports are accepted. Successful host fetch
  publishes locally before deleting the exact remote file.
- Install and rollback bind to the exact accepted p2 v0.7 UUID, gaming and
  Ozone receipts, config/launcher hashes and zero-error target health. Neither
  operation stops or restarts the frontend.

## Build and host checks

Run from the repository root:

```sh
mainline/gaming-remote-screen/build-drm-capture.sh build

R46H_TEST_TMPDIR=mainline/out/.cache/r46h-tests \
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/tests/test-r46h-gaming-remote-screen.py

bash -n mainline/gaming-remote-screen/build-drm-capture.sh \
  mainline/gaming-remote-screen/install.sh \
  mainline/gaming-remote-screen/rollback.sh \
  mainline/gaming-remote-screen/r46h-screenshot \
  mainline/gaming-remote-screen/r46h-screenshot-ssh
```

The builder is offline, pins the exact AArch64 image and output SHA-256, uses
PIE/RELRO/stack/FORTIFY hardening and accepts only the loader, libc and zlib
runtime dependencies. The artifact is written below ignored
`mainline/out/r46h-gaming-remote-screen-v0.2/`. The accepted Ozone installation
remains v0.1; the [ES-DE overlay](../gaming-remote-screen-es-de/README.md)
updates only the capture binary and unprivileged guard with byte-exact rollback.

## Current target evidence

On 2026-09-01/02 the KMS-only payload and ES-DE ARGB8888 overlay installed
without restarting the frontend. Exact host-validated Ozone menu and Metal Slug
PNGs matched the LCD; strict host-key SSH later captured ES-DE. Exact removal,
idempotence, listener audit and zero-error health passed. Representative accepted
markers are:

```text
R46H_SCREENSHOT result=pass name=r46h-screen-20260901T034832Z-3689.png bytes=49501 sha256=2a5bf01b6588445d6291a764386604727b73037c3cca0748dc056fca9dd6c12b
R46H_SCREENSHOT result=pass name=r46h-screen-20260901T042425Z-4029.png bytes=189855 sha256=b33025cc696b7985db0d82ee5de67af3bce5c636bafa186d00df88f1d6048ccc
```

The consolidated p2 v0.15 helper still captures ES-DE alone, but its process
guard rejects the normal ES-DE-plus-RetroArch topology. `pgrep -x retroarch`
also misses PPSSPP after it renames `comm` to `Main`. The tracked successor now
uses anchored full command lines, retains `/proc/PID/exe` checks and allows at
most one ES-DE plus one RetroArch. The exact candidate passed ES-DE-only, FBNeo
and PPSSPP captures and removal. Exact p2 v0.16 then passed ES-DE-only, normal
ES-DE-plus-Game Gear and PPSSPP (`comm=Main`) captures on 2026-09-05. The
PPSSPP check used the temporary exclusive-systems candidate later packaged by
p2 v0.17. Its persistent p2 media proof passed; device proof remains open.

## Pair and install

Keep the dedicated client key below ignored output:

```sh
client=mainline/out/.cache/r46h-remote-screen/client
install -d -m 0700 "$client"
ssh-keygen -q -t ed25519 -N '' -C r46h-remote-screen-v0.1 \
  -f "$client/id_ed25519"
chmod 0600 "$client/id_ed25519" "$client/id_ed25519.pub"
```

From trusted serial, obtain the current target ED25519 host fingerprint.
Rediscover the current IPv4 address, scan only that address, compare the
fingerprint, and publish one exact `known_hosts` line only after it matches.
Store it at `mainline/out/.cache/r46h-es-de/ssh/known_hosts`. Never reuse a
historical address blindly or disable strict checking.

The base v0.1 install/key transaction is already accepted on the current card;
do not combine its historical installer with the v0.2 capture output. Apply the
[ES-DE compatibility overlay](../gaming-remote-screen-es-de/README.md) to the
accepted v0.1 state. A future consolidated p2 should install the successor
directly instead of replaying both transactions.

## Fetch one frame

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -B \
  mainline/gaming-remote-screen/fetch-screen.py \
  --host CURRENT_IPV4 \
  --identity mainline/out/.cache/r46h-remote-screen/client/id_ed25519 \
  --known-hosts mainline/out/.cache/r46h-es-de/ssh/known_hosts
```

The verified PNG lands below `mainline/out/r46h-screenshots/`.
`REMOTE_CLEANUP=pass` proves its exact target export was removed. A cleanup
warning retains the valid local PNG and the bounded remote export for retry.
The [Qt control tool](../../docs/REMOTE-CONTROL.md) reuses an explicit RGB/RGBA
validation profile with bounded dimensions and PNG filters 0–4. This does not
relax this DRM fetcher's fixed 1024×768 RGB/filter-0 default or prove composed output.

## First product acceptance

1. Fetch the visible Ozone menu and compare it with the LCD. **Passed.**
2. Launch Metal Slug, fetch one gameplay frame and compare it. **Passed.**
3. Confirm no UDP listener on 55355, no unexpected listener, zero frontend
   restarts, zero ext4/failed-unit errors and read-only `/roms`.
4. Return to Ozone. Screenshots do not prove audio, controls, pacing, charging
   or power behavior.

## Rollback

Roll back the remote-input overlay first when it is installed.

```sh
sudo /usr/local/sbin/r46h-remote-screen-es-de-rollback
sudo /usr/local/sbin/r46h-remote-screen-rollback
```

Run the first command only while the ES-DE overlay is installed. It restores
the byte-exact v0.1 capture/helper without restarting the frontend. The base
rollback then removes the exact capture/SSH/sudo files, receipt and only its key
line; it retains non-empty target exports for explicit cleanup.
