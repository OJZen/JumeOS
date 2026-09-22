# Jume Transfer

Optional launcher application sharing one explicitly chosen directory over
temporary HTTP. Reuses the Files runtime, its native dark Widgets appearance
and controller adapter; no web engine, cloud account or persistent server.
**2026-09-22: transient R46H Wi-Fi/service and launcher machine checks pass;
phone QR scan, physical controls and persistent promotion remain open.**

## User flow

1. Connect R46H to Wi-Fi and open **File Transfer**. Ethernet alone does not qualify.
2. Check the shared directory (default XDG Downloads / `Jume Transfer`), or choose
   another owned directory. `/roms` may be selected for read-only downloads.
3. Choose Start. The app shows a QR code, IPv4 URL and random eight-digit code.
   Scan to pair directly, or open the URL on another device and enter the code.
4. The responsive web page browses subdirectories, uploads a batch of files,
   shows byte progress/cancellation and offers download links. No remote deletion,
   execution, system-directory browsing or partition changes are exposed.
5. Stop or close the application to revoke all connections and credentials.
   Losing Wi-Fi, changing the active connection/address, replacing the shared
   directory or reaching two hours also stops the session. Reconnection is manual.

Device controls: B starts/stops, A closes, Y opens the directory picker.
Keyboard/mouse use ordinary native controls. The main launcher blocks captures
while this app is active, including when its global panel is open.

## Boundaries

- **HTTP is unencrypted. Use trusted Wi-Fi only; do not transfer sensitive data.**
  Same-network pairing is an access gate, not protection against a network sniffer.
- Binds only the currently activated Wi-Fi IPv4 address, on an OS-chosen port;
  accepts peers in that IPv4 subnet. No `0.0.0.0`, IPv6 listener, public tunnel,
  port forwarding, root daemon or firewall changes. IPv6-only Wi-Fi is not supported.
- `nmcli` reports a connected Wi-Fi device and its active connection/IP. The
  service rechecks every second with bounded subprocess timeouts; stale health
  expires after four seconds. This is a sampled fail-closed gate, not an
  instantaneous kernel link-down notification.
- QR tokens are random, per session and sent in the URL fragment; the page clears
  the fragment before authenticating. Manual-code attempts are rate-limited.
  Authentication uses a session-only server secret in an HttpOnly/SameSite=Strict
  cookie. No credentials enter persistent state, command arguments or HTTP logs.
- Host and Origin checks, no CORS, CSP, no-referrer/no-store and attachment-only
  downloads constrain browser exposure. File names enter the DOM as text, not HTML.
- A shared directory must be owned by the desktop user (or be under `/roms`).
  Entire home/system roots, hidden paths, traversal, symlinks and special files
  are refused. Directory-relative file descriptors pin operations to the chosen
  tree; root identity changes revoke the session.
- Uploads stream in 64 KiB blocks into exclusive `.jume-upload-*` files and publish
  with no-overwrite rename. Existing files are never replaced. Disconnect/normal
  stop removes partial uploads while storage remains writable; storage loss,
  a forced kill or power loss can leave a hidden
  partial requiring inspection. Completed files stay even if acknowledgement is lost.
- Four HTTP handlers / two transfers maximum; each connection has a 15-second
  I/O timeout. Max file upload 8 GiB, page 200 entries (directory scan capped at
  10,000), browser batch 64 files, 16 MiB free-space reserve. Upload queue is serial
  within one browser; no upload resume or automatic retry. Downloads stream and
  support a single explicit-start byte range for clients that resume them.

The server uses a fixed-route subclass of Python's HTTP handler, not a directory
server or CGI. Python's [HTTP server warning](https://docs.python.org/3.13/library/http.server.html#security-considerations)
still applies: this is a bounded trusted-LAN utility, not an Internet-facing service.
QR generation uses [Debian libqrencode 4.1.1-2](https://packages.debian.org/trixie/libqrencode-dev).
System `/usr/bin/python3` and NetworkManager/nmcli are runtime prerequisites.
The v0.18 image lacks system Python. This target received eight reviewed Debian
packages (Python 3.13.5-2+deb13u5, default-version metadata and media-types),
24.3 MB installed, with no existing package upgrades/removals. Image integration
is still open; shipping the Files archive alone does not satisfy this dependency.

## Build and verification

`mainline/gaming-files/build.sh` includes the server/assets/library in the normal optional
Files bundle. Transfer mode skips the private audio server. Launcher state uses
`<state>/apps/transfer/`; shared data is never stored under the application cache.

`test-transfer.py` runs real loopback HTTP with an injected **test-only** link
provider: Ethernet rejection, NM activation, auth/origin/host, ordinary/ranged
downloads, Unicode/empty uploads, no-overwrite, hidden/symlink/traversal refusal,
disconnect cleanup, network/identity changes, expiry, pagination and parent EOF.
Every server fixture also rejects reverse DNS calls: binding a numeric Wi-Fi
address must not stall on router DNS and expire the startup health deadline.
There is no command-line Wi-Fi bypass. Run it as an ordinary Linux user.
Qt checks decode a generated QR with ZBar and exercise native start/stop with a
synthetic helper. Launcher checks cover entry, custom manifest and capture privacy.

The real local-browser fixture passed manual-code login, upload and byte comparison;
a 375 CSS-pixel view had no horizontal overflow. This is not a real phone/Wi-Fi test.
The R46H batch passed a real 16 MiB Wi-Fi upload/download with matching host,
returned-data and device SHA-256 (7.11 s upload, 28.97 s download; one sample,
not a throughput guarantee). Pairing by code/token, no overwrite, interrupted
upload cleanup, old-cookie rejection, parent EOF, readonly ROMs and actual Wi-Fi
loss/reconnect passed. The device's ordinary-user HTTP suite passed all 10 checks.
The native Transfer window mapped and submitted buffers; launch, quick-panel
capture refusal, exit and relaunch passed. Pairing/transfer used the production
helper via private SSH pipes; the native Start button and camera scan were not
automated or captured. Files/Text startup, privacy and exit also passed.

Target startup exposed two repaired issues: an omitted private libproxy search
directory and HTTPServer's unnecessary reverse DNS lookup (8.059 s startup age).
The listener now binds numerically; the four-second stale-link guard is unchanged.
Exact component hashes, bounded health and cleanup belong to
`mainline/out/.cache/r46h-transfer-device-20260922/RESULTS.md`.
Next batch: phone camera QR scan, native B/start/stop and physical readability,
long transfers and removable storage. Do not replay the completed machine checks
unchanged. Keep personal documents and live QR codes out of captured evidence.
