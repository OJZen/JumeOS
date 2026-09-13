# R46H RetroArch history-directory fix v0.2

Status: **PHYSICAL PASS / INSTALLED ON EXACT v0.10**

This is a separate p2-only update for the accepted gaming MVP v0.3 and ROM
workflow v0.1. It changes only `/etc/r46h/retroarch.cfg`; it does not touch
BOOT, kernels, ROMs, SSH keys or the accepted v0.14 input artifacts.

Debian RetroArch 1.20 accepts both individual `content_*_path` keys and
directory keys, but its history initialization derives the standard `.lpl`
names from the directory settings. An isolated AArch64 run using the accepted
v0.3 package reproduced the target warning with the v0.1 config:

```text
[INFO] [Playlist]: Loading history file: "/etc/r46h/content_history.lpl".
[ERROR] Failed to write to playlist file: "/etc/r46h/content_history.lpl".
```

Adding the five directory settings in this candidate changed the same binary's
runtime path and produced the file successfully:

```text
[INFO] [Playlist]: Loading history file: "/home/ark/.local/share/retroarch/content_history.lpl".
[INFO] [Playlist]: Written to playlist file: "/home/ark/.local/share/retroarch/content_history.lpl".
```

The exact video setting is `content_video_directory`; the other four use
`content_{favorites,history,image_history,music_history}_directory`.

The first physical preflight rejected generation
`build-892f649-1724089c04e6`: its batch command tried to expand `*` after the
payload directory became root-only, and its installer assumed the RetroArch
state root was already owned by `ark`. The real accepted v0.10 state root is
`root:root 0755`. Both checks stopped before config, receipt, helper or state
publication; the base config SHA-256 remained exact. Do not use archive
SHA-256 `1724089c04e60fff9fac31c12df8889adbcc0b6575a95374637d31882f6a671a`.

Clean correction commit `878a33e9e5b37a8e8f20ef0317b2b6a363612698` produced
deterministic generation `build-878a33e-ea4d53659c25`. Its 4,223-byte archive
SHA-256 is
`ea4d53659c25389efbc1c692da43aaf99699f5c5f42aee6b150799d0c4c7ea62`.
Two independent `git archive --format=tar` plus `gzip -n` runs were byte-equal;
extraction matched all three committed files. After exact root/mode
normalization, an AArch64 target-Linux container passed the complete payload
gate and stopped at the expected non-target kernel check. That container result
alone was host evidence; the separate R46H result is recorded below.

## Target transaction

Stage exactly `install.sh`, `rollback.sh` and `retroarch.cfg` as root-owned mode
`0600` files in root-owned mode `0700` tmpfs directory
`/run/r46h-gaming-history-v0.2`. Run the installer only after the v0.14 input
candidate has returned to exact v0.10 and both candidate removers have passed.
The bridge installer and remover intentionally pin the old config hash.

Before transfer, record all three SHA-256 values. Then run:

```bash
sudo /bin/bash /run/r46h-gaming-history-v0.2/install.sh \
  --installer-sha256 INSTALLER_SHA256
```

The installer pins exact v0.10, p2, both accepted gaming receipts, the old
config hash, clean ext4/systemd health and exact payload metadata. The accepted
target currently has the RetroArch state root as `root:root 0755`, while the
frontend itself runs RetroArch as `ark`. The transaction therefore pins that
exact base identity and normalizes only
`/home/ark/.local/share/retroarch` to `ark:ark 0700` before atomically
publishing the candidate config. It retains the old config plus an installed
rollback helper. Any install-time failure restores both the old config and the
base state-directory identity. It leaves the frontend stopped.

## Physical acceptance

Start the frontend and launch `/roms/nes/r46h-nes-smoke.nes` once with Nestopia.
After the ROM is visible, stop the service from serial while it remains
running. The accepted config has no controller hotkey for returning to RGUI.
Then require:

```bash
sudo test ! -e /etc/r46h/content_history.lpl
sudo test -f /home/ark/.local/share/retroarch/content_history.lpl
sudo test "$(stat -c '%u:%g:%a' /home/ark/.local/share/retroarch)" = 1000:1000:700
sudo stat -c '%u:%g:%a:%h %s' \
  /home/ark/.local/share/retroarch/content_history.lpl
sudo grep -F '/roms/nes/r46h-nes-smoke.nes' \
  /home/ark/.local/share/retroarch/content_history.lpl
sudo test "$(cat /sys/fs/ext4/mmcblk0p2/errors_count)" = 0
sudo test -z "$(systemctl --failed --no-legend --plain)"
```

Machine PASS requires the state root to be `ark:ark 0700`, the history file to
be `ark:ark` with one regular link, the exact ROM entry, no history file below
`/etc/r46h`, zero ext4 errors and no failed unit.
Start the frontend once more and have the operator open the smoke ROM from
RGUI's History entry. After that ROM is visibly running, stop the service from
serial again. This proves history persistence for the exact smoke path, not
arbitrary playlist scraping or metadata.

## Physical result: 2026-08-18

After exact v0.10 fallback and removal of both v0.14 candidate states, the
corrected installer emitted its PASS marker and left the frontend stopped. The
seven-line receipt and executable rollback helper were present. The state root
was `1000:1000:700`; `content_history.lpl` was a regular one-link
`1000:1000:600` file and contained `/roms/nes/r46h-nes-smoke.nes` exactly once.
The installed config SHA-256 was
`697aa82bb42689cd841f16a8ce1ae9c6ac2bdc56ccd1b811136f8f5884e600e9`.

The operator reopened the same ROM from RGUI History after first running it
from ordinary RGUI. Serial logs independently showed Nestopia loading the exact
path and writing the user playlist. Both frontend stops left no RetroArch process;
ext4 errors and failed units remained zero. The corrected config, receipt and
rollback helper remain installed, and the board reached a controlled poweroff.

If target behavior fails, stop the frontend and run the retained exact helper:

```bash
sudo /usr/local/sbin/r46h-gaming-history-rollback
```

The rollback accepts either the candidate config or an already restored base
config, avoiding a second replacement if restoration has already completed.
It restores the byte-exact v0.1 config and the original `root:root 0755` state
root, then removes only its own receipt, state and helper.
