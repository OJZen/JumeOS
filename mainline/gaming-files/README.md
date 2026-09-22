# Jume Files and Text

**2026-09-22: ARM64 host checks and transient R46H launch/privacy/exit smoke pass.
File operations, previews, USB and physical UX remain target acceptance gates.**

[Jume Transfer](TRANSFER.md) is a separate optional launcher entry for temporary
Wi-Fi-only QR/HTTP uploads and downloads, sharing this runtime and visual style.

## Scope / design

One optional Qt 6 application supplies the file manager and a separate editor
entry. Qt's asynchronous QFileSystemModel, native item views, text editor,
QImageReader, Qt PDF and Qt Multimedia provide the underlying implementations.
Native Widgets are used for their established file selection, editing, PDF and
video behavior; no terminal commands, HTML engine or custom codec is involved.
The native interface follows Jume's dark palette, with cached line icons and
consistent focus/press states. One compact icon/path bar replaces the title and
command rows; the places sidebar is collapsible and starts hidden. The file
viewport takes the remaining space. Icons retain accessible names/tooltips.
Y, the menu button, Shift+F10 and right-click share a window-bounded context menu;
copy/cut/paste stay at its root, secondary actions use submenus. Selection never
starts a preview: Open is explicit.

| Feature | Behavior |
| --- | --- |
| Browse/sort/hidden files/list/details/places | Asynchronous directory model; explicit previews; partitions and XDG places |
| Sorting | Natural name, size, extension/type or modification time; ascending/descending, optional folders-first; persisted across launches |
| New folder/text, rename, multi-select copy/move, trash/restore, permanent delete, properties | Visible clipboard, cancellable background work; refuse roots/self-copy/overwrite |
| ZIP extraction / creation | New destination only; stream bounded data; publish only after success |
| USB discovery/mount/unmount | Async UDisks2, removable USB allowlist, fresh identity checks, no force-unmount |
| Text editor | UTF-8/BOM, LF/CRLF, undo/redo/find, Save/Save As, external-change check and unsaved-close prompt |
| Images/PDF/audio/video/office text | Scaled images, PDF page/zoom, play/pause/seek; DOCX/ODT text only |
| Layout/integration | Standard user directories, private per-app state, no automatic legacy migration, capture privacy |

Files run with the desktop user's permissions. Read-only `/roms` remains
read-only. No partition formatting, system remount, recursive ownership changes,
automatic USB execution or arbitrary helper commands. Trash failure never means
permanent deletion. Overwrite conflicts fail rather than merging trees.
Same-filesystem cut uses a native move; cross-filesystem cut copies first and
moves the source to native trash only after successful writes. If trash fails,
both copies remain with an explicit error. Concurrent edits are not locked out;
recover the original from trash if necessary. Cancelling a directory copy
retains completed entries and removes the unfinished file;
permanent deletion cannot undo already deleted entries. Busy/unplugged volumes
report errors; this is not a transactional filesystem or backup tool.

One mutating task runs at a time. Its inline panel shows the current file's
bytes/progress (not a guessed whole-tree percentage), cancellation and details;
directory browsing stays available. Progress snapshots are sampled at 10 Hz,
without flooding the UI event queue. Directory checks, mount-space queries,
properties and file operations run on workers. Rapid navigation keeps only the
latest pending destination; unchanged storage lists keep focus and scroll.
Editor commits and coalesced view-preference writes also run off the GUI thread;
normal close waits for their result without blocking the event loop.
Native item views use fixed row heights and batched list layout, not one widget
per file. High-frequency actions have no animation, blur or full-page repaint loop.

Double-click a ZIP or choose Menu → ZIP → Extract; enter the new folder name.
Select files/folders and choose Create ZIP to archive them without changing the
originals. Both operations use existing [libarchive](https://github.com/libarchive/libarchive),
256 KiB streaming buffers and private sibling staging. Cancel/error removes
staging; success publishes the new destination without overwriting. Store and
Deflate are supported; creation uses fast Deflate level 1. Encrypted, split,
link/special-file, absolute/traversing/backslash paths, duplicate-file entries,
oversized metadata and CRC/structure errors are refused. Limits: 50,000 entries,
64 path components, 16 MiB central directory and 16 GiB expanded data. Large
ZIP64 central-directory offsets are not supported. A forced kill/power loss can
leave a hidden `.jume-unpack-*` / `.jume-zip-*` partial; inspect before removal.

Home trash has a sidebar entry; removable-volume trash remains on that volume
(show hidden files to browse its `files` directory). Restore reads native
`.trashinfo`, requires the original parent, and never overwrites a new file.
Editing checks both the original inode/device and bytes before atomic replacement;
it does not lock other programs out of concurrent writes. Save As refuses existing
targets. Symlink files are not previewed/edited implicitly.

Text is limited to 2 MiB, 20,000 newlines and 65,536 characters per line. Images
allow up to 64 MiB compressed / 100 million declared pixels, decode at up to
1024×768 with a 64 MiB Qt allocation limit. GIF previews show a still frame.
PDF allows up to 64 MiB; complex documents can still use substantial memory.
DOCX/ODT containers allow 32 MiB, 4,096 entries and 2 MiB XML body; DTDs are refused.
DOC/XLS/PPT and full Office layout are not promised; unsupported files get an
explicit message. Editing/naming uses a USB keyboard; controller navigation
reuses the existing launcher input adapter.

Media includes common MP3/WAV/FLAC/OGG/AAC and MP4/MKV/WebM containers, subject to
the bundled FFmpeg codec support. Playback is explicit and local-only; no network
protocols, autoplay or external helper execution. Hardware video decoding is
**not validated**. Qt uses a private foreground PulseAudio→ALSA bridge because
the accepted desktop has no global Pulse service. Its private UNIX socket and
server die with the app; it does not configure a hardware mixer or replace the
system audio service.

Keyboard: Enter opens, Alt+Up goes up, Ctrl+Shift+N creates a folder, Ctrl+N a
text file, F2 renames, Ctrl+C/X/V copies/cuts/pastes, Delete trashes,
Shift+Delete asks for permanent deletion, Alt+Enter shows properties and Ctrl+H
toggles hidden files. Editor uses Ctrl+S/Shift+Ctrl+S/F/Z/Y. Mouse supports
Ctrl/Shift multi-select, double-click and context menus. File shortcuts do not
intercept text-field copy/paste. R46H Switch-layout labels are B confirm, A back,
Y action menu, X view switch and L1/R1 places (reveals the sidebar); A closes the
sidebar when it owns focus, otherwise goes up. Close is also in the menu.
Select toggles multi-select mode
(directions move focus, B toggles a row); Start cancels the current task. Confirm activates a selected
place (moving selection alone never mounts). Physical input still needs acceptance.

## Build / integration

```sh
mainline/gaming-files/build.sh
```

The pinned ARM64 SDK builds/tests/packages under external
`mainline/out/.cache/jume-files/`. It requires the retained, hash-pinned Qt base
archive named in `package.py`. Dependencies are fetched inside the disposable
container, then network is disconnected for build/test. The runtime preserves
the target libc/C++/GPU ABI; it does not carry a replacement GPU driver.
`receipt.json`, `runtime.sha256` and the archive's `SHA256SUMS` identify outputs.
This dirty-source candidate is not a reproducible release claim.

The shared-desktop builder includes this optional archive (or
`R46H_FILES_RUNTIME`) only after checking its sibling `runtime.sha256`; launch
requires the shared Wayland session and ordinary `ark` user. New entries are
Files, Text and Transfer. No persistent desktop/image promotion is performed here.

USB additionally needs Debian **udisks2** and its filesystem helpers on the
device; **not installed by this app bundle**. Review the target package transaction
before installing it, then seal `storage/49-jume-removable.rules` root-owned
0644 and run `storage/storage-policy.sh --check`, followed by `--install`.
The helper checks the exact accepted board/card/rootfs identity and refuses a
different existing rule. `--remove` removes only its byte-identical rule.
The rule grants `ark` ordinary removable USB mounts, not system/fstab mounts,
formatting or unmounting other users' disks. See upstream
[Filesystem API](https://storaged.org/doc/udisks2-api/latest/gdbus-org.freedesktop.UDisks2.Filesystem.html)
and [polkit actions](https://storaged.org/doc/udisks2-api/latest/udisks-polkit-actions.html).

## Evidence / next physical batch

ARM64 `files-check` covers operations/trash/restore, text and Office
safety, real D-Bus serialization with a fake UDisks service, native file views,
image/PDF and decoded video, hostile ZIP/roundtrip/cancellation, multi-file
clipboard, actual cross-filesystem cut, sorting/menu bounds/preferences, a
full-width compact layout, 3,001-entry browsing and GUI heartbeat
during a slow worker. These are responsiveness checks, **not a 60 FPS R46H claim**.
`check-runtime.sh` verifies manifest hashes, repeats
tests as an unprivileged user with packaged libraries, measures nonzero PCM from
the private audio server and bounds a real app startup. Launcher entry and
sensitive-capture checks also pass, including a custom application list.
Evidence: `mainline/out/.cache/jume-files/RESULTS.md` and adjacent logs/images.

Next single R46H batch: guarded distro dependency/policy setup; a disposable
USB folder through mount/copy/edit/hash/trash/restore/unmount; refusal of busy
unmount; controlled hot-unplug during a disposable copy; readonly `/roms`;
keyboard/mouse/controller and LCD readability; representative A/V and PDF,
memory/health checks, exit/relaunch and policy rollback. No personal documents
belong in captured evidence. Real USB, speaker output and sustained hardware
performance remain **open**, not inferred from host tests.

Current legacy saves/configuration and accepted device images are not migrated
by this implementation. See [storage layout](../../docs/FILESYSTEM-LAYOUT.md).
