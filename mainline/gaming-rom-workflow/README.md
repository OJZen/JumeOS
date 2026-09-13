# R46H ROM-over-Wi-Fi workflow v0.1

> **Historical/frozen contract:** this installer and its accepted result belong
> to the v0.10-era product. They do not describe the current card or current
> RetroArch configuration and do not authorize another install. Read
> [Project Context](../../docs/PROJECT-CONTEXT.md) and the
> [R46H ledger](../board/r46h/EXPERIMENT-STATUS.md) before reusing only the
> independently validated uploader path.

This is the bounded follow-up to the accepted gaming MVP v0.3. It does not
touch BOOT, EASYROMS or the media layout. It adds one operator-selected Mac SSH
public key for the unprivileged `ark` account, creates `/roms/{nes,gb,gba,nds}`
owned by that account, and provisions `ark`-writable RetroArch state
directories. It also carries explicit history and playlist path settings; the
live Debian 1.20 result below records that those settings are not sufficient
when the primary config itself remains below `/etc/r46h`.

The target installer accepts the public key only as a root-owned, single-link
regular file in its fixed `/run/r46h-rom-workflow-v0.1` staging directory. The
operator must provide the exact installer and public-key SHA-256 values. An
existing different `authorized_keys`, a modified RetroArch config, a mismatched
v0.3 receipt, ext4 errors or failed units all stop the transaction before any
change. The public key is host-specific evidence and is never committed.

## One-command Mac uploader

After installation, use [`upload-rom.py`](upload-rom.py) to copy one
operator-owned ROM as `ark`, never as root. Supply the current R46H IPv4
address and the private key matching the already installed public key:

```sh
./mainline/gaming-rom-workflow/upload-rom.py \
  --host R46H_IP \
  --identity OPERATOR_PRIVATE_KEY \
  "/path/to/Game Name.nes"
```

The optional `--port` defaults to 22. The extension selects only one installed
directory: `.nes -> /roms/nes`, `.gb/.gbc -> /roms/gb`, `.gba -> /roms/gba`
or `.nds -> /roms/nds`. Other extensions, hidden/control-character names,
non-literal or non-canonical IPv4 input, an unsafe private-key file and ROMs
larger than 4 GiB fail locally before network access.

The uploader scans only the ED25519 host key and accepts it only when its
fingerprint equals the independently CH340-verified value below. It writes that
single key to a mode-`0600` dedicated temporary `known_hosts` below the ignored
external cache, requires strict host-key checking and public-key-only batch
authentication, and removes the temporary directory at exit. No password,
credential content or private key is written into the repository or target.

On exact v0.10, the unprivileged remote preflight requires `ark` identity,
the exact owned ROM directory, zero ext4 errors, no failed units, and absence
of both the final path and this run's random hidden upload path. After `scp`,
the Mac rehashes the local file and the target independently checks size and
SHA-256. Publication uses a same-directory hard link, which fails atomically if
the final name appears; it never overwrites an existing ROM. A failed transfer
or publish removes only this run's hidden candidate, and a failed post-link
check rolls back only the just-created final link. Compare the remote digest
marker before accepting the final PASS.

RGUI begins at `/roms`, so `Load Content` can open the copied file with a native
Debian libretro core. This version does not scrape metadata, download artwork,
build playlists or claim arbitrary-ROM compatibility. Launching a ROM may add
it to the separately accepted user-owned History, but the uploader does not
edit that playlist directly.

## Mac uploader host result (2026-08-22)

The executable uploader passes the same 14 focused tests on macOS and in the
pinned, offline ARM64 Linux environment. They cover its extension mapping,
canonical IPv4 guard, private-key and non-symlink file identity, shell-safe
argument transport for spaces/quotes, strict pinned-key SSH options, local
rehash, remote no-clobber hard-link publication, bounded rollback and
argument/help guards. This is host evidence only: no board was powered on and
no additional ROM was transferred for this packaging change. The already
accepted manual transfer below remains the physical proof of the underlying
SSH, target directory, rehash and RGUI-readable path.

## Accepted result (2026-08-16)

Clean commit `aacf581` was installed on the accepted persistent v0.10 system.
The installer SHA-256 was
`d6585eedb1c0db21796b6ef505d052c1ed44c18b431de7097c1db79ad434be4e`;
the installed configuration SHA-256 was
`621fdf049cd05e6aa02c62b5c42ed37a768ce9342af14c4563cfd4466d80d078`.
It published root receipt `/var/lib/r46h/rom-workflow-v0.1-installed` with
SHA-256 `d33a1e23c83e2bbcfbb05180aabad4428d99809096f1ca589ddf1be308d2ff27`.

The R46H host key was independently observed over CH340 with ED25519
fingerprint `SHA256:6C7YclGZi6qYujswYZD7yKb2SaWNsGA2bxeN3xTGjps`. Public-key authentication as
unprivileged `ark` then succeeded with strict host-key checking. The original
24,592-byte deterministic NES smoke ROM was copied to a hidden upload name,
rehash-verified as
`f4e911f38aade8353853127e5e45b91aef1333061bdf865ec1775236e72abb0c`,
and renamed to `/roms/nes/r46h-nes-smoke.nes` with `ark:ark`, mode `0644` and
one link. RGUI remained active, ext4 `errors_count` remained zero, and systemd
reported no failed units. This proves the bounded authenticated transfer and
RGUI-readable directory workflow; it is not a new arbitrary-ROM compatibility
claim.

A fresh start/stop after installation proved that Debian RetroArch 1.20 still
derived `content_*_history.lpl` from `/etc/r46h`, despite the explicit absolute
path entries. The resulting write warnings remain harmless, and service/process
cleanup plus mixer restoration passed, but history persistence is **not**
claimed as fixed by v0.1. The separately isolated and rollback-safe v0.2
directory-key candidate is documented in
[`../gaming-history-fix/README.md`](../gaming-history-fix/README.md); apply it
only after the v0.14 input candidate has returned to exact v0.10 and been
removed.
