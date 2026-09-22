# Jume file layout

Applications and user documents are different data. New application state is
private and grouped under the launcher-selected state root; user documents are
ordinary, user-owned files. Do not place caches beside ROMs or user documents.

| Purpose | Location / owner |
| --- | --- |
| Installed runtime | Versioned root-owned bundle; no application writes here |
| Launcher root | Explicit `--state-dir`; accepted legacy device path remains `/home/ark/.local/share/r46h-preview` |
| New Files/Text preferences | `<state>/apps/files/view.json`; private `config/`, `cache/` and session locks alongside it |
| File Transfer | Private state `<state>/apps/transfer/`; default shared files in XDG Downloads / `Jume Transfer`; credentials stay in memory |
| Browser profile/cache | Existing `<state>/browser/`; no profile migration or deletion |
| Game saves/tool settings | Existing `<state>/tools/`; keep emulator-specific layouts unchanged |
| Documents/downloads/media | XDG user directories in the user's home; never inside a runtime bundle |
| Games | `/roms` (accepted read-only content); no automatic remount or content relocation |
| USB mounts | Returned by UDisks2; never assume `/dev/sdX` or invent a mount path |
| Trash | Qt's native XDG trash, per filesystem when supported |
| ZIP staging | Private `.jume-unpack-*` / `.jume-zip-*` siblings of the chosen destination; removed on normal cancel/error, published on success |
| Session sockets | Private `$XDG_RUNTIME_DIR`; Files' private audio bridge is removed on app exit |
| Build/test artifacts | External `mainline/out/.cache/`; never installed as user data |

Files/Text use the system's XDG directory mapping even though the launcher's
private Qt environment has its own configuration directory. Missing standard
directories may be created on explicit navigation; old custom directories are
not moved. A future launcher namespace migration needs source/destination
inventory, conflict refusal, verified copies and a rollback; it is not a rename
performed at startup. Existing browser downloads remain disabled until their
own confirmed-save UI is implemented.
