# Application lists and background tasks

Status: **2026-09-26 BASIC SWITCHING ATTENDED PASS / FIXED TASK + TERMINAL DEVICE AUTOMATION PASS**.
The shared Wayland session manages foreground/background application processes.
This is not automatic ROM scanning or a persistent replacement frontend; ES-DE
outside Jume is not managed. Older single-app device evidence does not validate
the new input protocol or multitask lifecycle.

## Configure a list

```sh
mainline/gaming-shell/run.sh --applications /absolute/external/applications.json
```

Without the option, the library holds the built-in Moonlight, optional
[Jume Browser](../gaming-browser/README.md) and 文件管理器 apps; Neo, PortMaster,
USB gamepad, terminal, text editor and file transfer sit behind the home dock's
工具, and settings (with the controller test) behind 设置. They use stable
`builtin.*` favorite IDs and internal routes; see [Tools](TOOLS.md). The explicit
manifest replaces the library's default list and keeps installed built-in apps
after its entries; the old labelled demos remain only in focused QML fixtures. The manifest is
read once at startup: up to 512 entries in a 512 KiB JSON file, owned by the user
or root, regular/non-symlink and not group/world writable. Each entry needs a
unique stable ID, title, absolute executable path and an argument array:

```json
{
  "version": 2,
  "applications": [
    {
      "id": "moonlight",
      "title": "Moonlight",
      "description": "电脑游戏串流",
      "program": "/run/r46h-moonlight-qt-test/qt-client.sh",
      "arguments": []
    }
  ]
}
```

[The example file](applications.example.json) opens Moonlight's own host-selection
UI once its package has been staged. It does not connect to a guessed host. For
one direct stream, configure the client's `stream` arguments after identifying
and pairing the server; the [Moonlight runbook](../gaming-moonlight/QT-CANDIDATE.md)
owns the client and stream parameters. Empty arguments and direct CLI streaming
have different client-exit behavior. The example is shipped, but never activated
implicitly. Keep pairing credentials in the client's private state, not here.

`description` and absolute `directory` are optional. Version 2 adds optional
`system` and `core` (at most 32 characters; the library filters by system, the
options menu shows both) and `supported` (`false` keeps the entry in the library,
disabled as 尚未适配, and refuses launch); version 1 files stay valid and reject
these fields. IDs use lowercase letters,
digits, dots, underscores and hyphens, starting with a letter/digit and at most 64 characters. Titles are at most
64 characters, descriptions 96; unknown fields are rejected. Commands run through
QProcess with separate arguments, without shell concatenation. Use a wrapper for
an application's own runtime or accepted configuration. The desktop removes its
private Qt/SDL library paths, test caches and XDG state overrides from the child;
it retains display/runtime-socket and controller settings. Child standard streams
are closed/discarded; application-specific safe logging belongs in its wrapper.

Home's card row ([JUME-UI §8](../../docs/JUME-UI.md#8-界面)) shows recent entries,
newest first, then favorites, topped up to five with the first available
entries, and ends with 全部游戏. A successful launch records the entry as recent
(up to 32); the options menu removes it. The library is a scrolling grid with
filter tabs (全部, 收藏, 最近, each system, 应用 for entries without one) and
title search. Missing runtime files fail on activation and leave
the desktop visible. Names render as plain text. Application favorites use stable
IDs, so reordering the file does not move a favorite to another application.
Preference schema 5 keeps old demo favorites and migrates versions 1–4 on the next
write; it adds night mode and recent application IDs. Older previews reject schema 5
and preserve it; use their separate state when reverting. Up to 256 application favorites are retained, including IDs whose
entries were temporarily removed from the list.

## Lifecycle and limits

| Physical shortcut | Result |
| --- | --- |
| Select + Y | Background current app and show task cards |
| Select + Start, release before 2 seconds | Background current app and return Home |
| Select + Start, held for 2 seconds | Kill the app that was foreground when the hold began |
| Select + X | Request the current app's normal window close; on the task page, close the selected task. Stage 5 removes it ([JUME-UI §7.8](../../docs/JUME-UI.md#78-从现行映射迁移)) |

Press Select first or simultaneously with the other key. An unrelated face-button
press is never delayed to guess a future shortcut. Select alone delivers its
ordinary press/release on release. Chord keys are consumed; L3+R3 still opens
the existing quick panel. Holding Start+Select shows progress, not an early Home
transition, and never retargets a kill to a newly activated process.

The selected task gets a large last-visible screenshot; a four-row queue keeps
every task's thumbnail, icon, title and running/paused state visible. D-pad
selects; A resumes and B or Select returns. X is decided on release: a tap requests
normal close, while holding it shows a HoldConfirm after 600 ms and force-quits the
selected task at 2 s; releasing earlier cancels. Start lists the task's actions.
Y is unassigned. The hint bar replaces the former footer buttons. Opening
an existing app ID resumes the same process; it does not launch a duplicate. Ctrl+Tab / Meta+D are
local launcher keyboard equivalents, not global keyboard hooks in other apps.

At most four task records/input endpoints are retained. The target rejects a new
launch below 128 MiB MemAvailable or when that value cannot be read; it does not
kill unsaved work to free memory.
Games and arbitrary manifest programs pause as process groups in the background;
Files, Text, Transfer, Browser and Terminal keep running. This preserves file
operations/network transfers. Pausing does not release RAM, and this admission
guard is not per-app OOM containment. Existing experimental session/worker wall
time limits still apply. Long pauses and memory pressure need target acceptance.

The desktop saves pending preferences before launch. Each task owns its QProcess,
process group, input slot and thumbnail. Returning requires neutral controls;
Wayland keyboard/pointer focus follows only the foreground window. Each task's
gamepad is separate (products 0x0049–0x004c); background tasks do not receive the
foreground pad stream. Ordinary external input devices remain client-owned.

**Normal close is Wayland `xdg_toplevel.close`, not SIGTERM.** The application may
show an unsaved-file dialog, defer or refuse. There is no timed escalation. A
missing window is reported explicitly. Forced termination uses SIGKILL on the
owned process group and can lose unsaved work. It never targets a guessed PID.
The legacy quick-panel End action and whole-preview shutdown retain their
explicit TERM/1.5-second cleanup path; shutdown includes background tasks.

Screenshots are captured asynchronously before leaving the foreground and scaled
to at most 320×240. They stay in memory, are replaced on the next successful
snapshot and removed when the task ends; no disk cache or live video thumbnails.
The task page ([JUME-UI §8](../../docs/JUME-UI.md#8-界面)) is a carousel: the focused
card 512×384 in the middle, its neighbours 420×315 at the sides, the title and
state (已暂停 / 运行中 / 正在结束…) below and the count beside the 任务 title.
Failed/unmapped captures show the entry's fallback card. The whole task page is private
to the local display, including ordinary app thumbnails. Remote capture requests
cannot join or receive a local snapshot operation. The local image provider does
not accept file paths; existing editor/browser/transfer capture restrictions remain.

Each launch uses [Qt's new-session flag](https://doc.qt.io/qt-6.8/qprocess.html#UnixProcessFlag-enum)
and retains that child process-group ID. If the main process exits first, ordinary
children receive termination and the same grace period; the task keeps its slot
until the group is gone. Tests include a child that ignores TERM. Detached services
and abrupt death of the desktop itself still require the outer device cgroup
deadline/cleanup. This class does not replace that supervisor.

The opt-in [handheld Wayland session](../gaming-wayland/HANDHELD.md) keeps a
transparent UI above the game and routes L3 + R3 to its quick panel: the running
app and its state, the Wi-Fi, 性能浮窗 and 夜间模式 tiles, brightness (volume
stays with the device keys and never takes focus), then 回到主页, 任务切换 and
结束游戏…; the desktop variant leaves out 回到主页 and 结束游戏. Ending a game
uses a confirmation that defaults to Cancel; router failure stops the game and
returns a nonzero preview exit status for outer recovery.

The same task manager accepts prepared commands from compiled-in
adapters. This method is not QML-invokable and is not an IPC operation. Shared
Moonlight management uses it to run the existing validated stream worker while
retaining the desktop and built-in cards. Only an explicit manifest replaces the
cards, including an intentionally empty manifest. The worker keeps this package's
runtime and private pairing state; manifest applications retain their existing
environment isolation. The newer Neo adapter uses the same manager with its
target-validated native worker. All paths use per-task process-group cleanup and a routed pad slot.
Native launch requests are staged per game, so a paused worker cannot consume
another game's request when resumed.
Routed sessions enable [SDL background controller events](https://wiki.libsdl.org/SDL2/SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS):
the broker owns input delivery even when a game has no Wayland keyboard focus.
Its neutral handoff still prevents input leaking into a game behind the panel.

Launch is enabled on Cocoa, X11, Wayland and the host-test offscreen backend.
EGLFS/linuxfb launch is refused because hiding the shell does not establish DRM
handoff. Even on Wayland, the child's renderer/configuration must match the
shared display. Existing RetroArch KMS settings and the standalone Moonlight
probe cannot be blindly used under the compositor. R46H display ownership,
actual game controls and full descendant cleanup remain device integration gates.

## Checks and deployment boundary

`shell-check backgroundTasksAndClose` covers process identity, thumbnail bounds,
resume/pause, four-task limit, cooperative-close signal without termination,
background-task kill isolation, task-page privacy/layout and whole-session cleanup.
`tools-check nativeRequestsRemainIsolatedWhilePaused` guards native launch-request
identity, schema validation and per-game cleanup.
`test-input-policy.cpp` and `test-input-router.py` cover short/long shortcuts and
real kernel per-slot isolation; `test-tasks.py` uses real Qt/Wayland windows that
first refuse, then accept close. It also checks simultaneous apps, local thumbnails,
remote refusal, physical synthetic chords, pause/resume and forced kill.
These run in the pinned ARM64 SDK, not on R46H. Evidence is under
`mainline/out/.cache/jume-tasks/`; physical long-hold timing, retained game/save
state, background transfers/audio and sustained RAM remain hardware gates.

The 2026-09-26 R46H operator accepted Select+Y task cards, bottom-B resume with
working directions and short Select+Start Home using the independent controller.
The operator reported slow task-page entry: the tested candidate waited for local
thumbnail capture before showing the page (capture deadline 2 seconds); exact
on-device latency was not measured. Terminal startup failed with exit 2:
the shared setpriv launch inherited no HOME, so `terminal-shell.sh` aborted at
`cd "$HOME"`. Foot with `/bin/true` succeeded; a diagnostic rerun of the shell
with the current user's passwd HOME also exited 0. The shared session now derives
the effective account environment before launching clients; target retest passed.
Evidence: `mainline/out/.cache/r46h-attended-20260926.3Iyp3b/session.md`.

The correction shows the task page before thumbnail readback. After its first
frame, a worker requests only the last foreground main surface from the paired
compositor; PID/surface identity and a one-shot UI-owner check keep other windows
out. Unrendered/unsupported surfaces keep the icon or previous preview. A generation
check discards late images after resume/switch/close. These are surface thumbnails,
not full-output screenshots: HUDs and separate child surfaces are not included.
The delayed-readback test checks responsive page entry and stale-result cancellation;
the receiver test covers owned pixels, malformed descriptors and bounded time/size.

The corrected paired package passed three transient R46H runs: Terminal's ark
login shell/PTY/home, same-PID resume, relaunch, normal close, long-chord kill,
two-app isolation and restoration. Terminal and the OpenGL controller produced
previews; backgrounding before the first rendered frame correctly kept the icon.
Task-page and terminal remote capture stayed denied. Synthetic target task-entry
state checks were 476–804 ms including chord hold/polling; these do not measure
LCD response. The exact package's host GL test showed the page ready at 89.8 ms
despite an 800 ms image-response delay. Evidence and hashes:
`mainline/out/.cache/r46h-task-fixes-20260926.C35vGm/session.md`.
The follow-up operator accepted noticeably faster Select+Y entry/preview,
bottom-B Terminal resume and Select+X normal exit. Sequential keyboard/mouse
acceptance is recorded in [Peripherals](../gaming-wayland/PERIPHERALS.md).
Only the temporary test-wrapper time limits were extended (30-minute UI,
31-minute cgroup); application binaries were unchanged and the thermal guard
remained active. Evidence: `mainline/out/.cache/r46h-usb-attended-20260926.EGffXZ/session.md`.
Physical long-hold kill timing and actual game/save/background-transfer retention
remain attended gates; ES-DE is unchanged.

Deploy the launcher, compositor, input router, session wrapper and native-port
guards together. Protocol v3 and four independently opened uinput handles are
required; an old single-handle session is not compatible. Do not promote the
candidate to default or rewrite the accepted card simply to test it.

The local agent endpoint reports `externalSession`, `activeApplication`,
`applicationError` and `applicationExitCode`. It does not expose arguments or
accept child commands; the shared session's fixed exit action uses the normal UI.
Ordinary hidden-window captures are unavailable; the shared session can capture
the composed game and panel through its guarded compositor path.
The manifest is an owner-provided allowlist; IPC cannot add commands or paths.

## Focused checks

`applicationManifestAndForegroundLifecycle` in the Qt check covers manifest
validation, foreground ownership, normal/error exit, stop, a TERM-ignoring orphan
and stable favorites. The group cleanup check passes on macOS and isolated Linux.
`test-shell-applications.py --binary ABSOLUTE_SHELL_PATH` exercises the real main
program: nine entries, scrolling, literal arguments, favorite persistence, launch,
parent-action blocking and successful/error return. The packaged ARM64 check also
runs this short flow. No high-frequency loop is needed for this feature.
