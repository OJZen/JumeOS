# Application lists and foreground launch

Status: **HOST FEATURE / DEVICE HANDOFF UNTESTED**. The shell can load an explicit
application/game list and run its foreground commands. This is not automatic ROM
scanning, an installed replacement frontend or a global game overlay.

## Configure a list

```sh
mainline/gaming-shell/run.sh --applications /absolute/external/applications.json
```

Without the option, the built-in Moonlight, Neo, PortMaster, USB gamepad, controller
test, settings and optional [Jume Browser](../gaming-browser/README.md) entries are shown. Their tools use stable `builtin.*` favorite
IDs and internal routes; see [Tools](TOOLS.md). The explicit manifest replaces
that default list; the old labelled demos remain only in focused QML fixtures. The manifest is
read once at startup: up to 512 entries in a 512 KiB JSON file, owned by the user
or root, regular/non-symlink and not group/world writable. Each entry needs a
unique stable ID, title, absolute executable path and an argument array:

```json
{
  "version": 1,
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

`description` and absolute `directory` are optional. IDs use lowercase letters,
digits, dots, underscores and hyphens, starting with a letter/digit and at most 64 characters. Titles are at most
64 characters, descriptions 96; unknown fields are rejected. Commands run through
QProcess with separate arguments, without shell concatenation. Use a wrapper for
an application's own runtime or accepted configuration. The desktop removes its
private Qt/SDL library paths, test caches and XDG state overrides from the child;
it retains display/runtime-socket and controller settings. Child standard streams
are closed/discarded; application-specific safe logging belongs in its wrapper.

Home shows the first three configured entries. The library uses a virtualized,
scrolling three-column grid. Missing runtime files fail on activation and leave
the desktop visible. Names render as plain text. Application favorites use stable
IDs, so reordering the file does not move a favorite to another application.
Preference schema 3 keeps old demo favorites and migrates versions 1/2 on the next
write. Older previews reject schema 3 and preserve it; use their separate state
when reverting. Up to 256 application favorites are retained, including IDs whose
entries were temporarily removed from the list.

## Lifecycle and limits

The desktop saves pending preferences before launch, blocks its own actions while
the child runs, and hides after the process starts. Normal exit, failure and crash
restore the same selected entry. Returning requires the controller to become
neutral before it can act on the desktop; keyboard/window focus is restored.
Preview dimming is paused during the external session. Closing the preview first
requests termination, then forces the owned process group after 1.5 seconds.

Each launch uses [Qt's new-session flag](https://doc.qt.io/qt-6.8/qprocess.html#UnixProcessFlag-enum)
and retains that child process-group ID. If the main process exits first, ordinary
children receive termination and the same grace period; the desktop stays busy
until the group is gone. Tests include a child that ignores TERM. Detached services
and abrupt death of the desktop itself still require the outer device cgroup
deadline/cleanup. This class does not replace that supervisor.

The opt-in [handheld Wayland session](../gaming-wayland/HANDHELD.md) keeps a
transparent UI above the game and routes L3 + R3 to its quick panel. Ending a game
uses a confirmation that defaults to Cancel; router failure stops the game and
returns a nonzero preview exit status for outer recovery.

The same foreground manager now accepts prepared commands from compiled-in
adapters. This method is not QML-invokable and is not an IPC operation. Shared
Moonlight management uses it to run the existing validated stream worker while
retaining the desktop and built-in cards. Only an explicit manifest replaces the
cards, including an intentionally empty manifest. The worker keeps this package's
runtime and private pairing state; manifest applications retain their existing
environment isolation. The newer Neo adapter uses the same manager with its
target-validated native worker. All paths use the same process-group cleanup and routed pad.
Routed sessions enable [SDL background controller events](https://wiki.libsdl.org/SDL2/SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS):
the broker owns input delivery even when a game has no Wayland keyboard focus.
Its neutral handoff still prevents input leaking into a game behind the panel.

Launch is enabled on Cocoa, X11, Wayland and the host-test offscreen backend.
EGLFS/linuxfb launch is refused because hiding the shell does not establish DRM
handoff. Even on Wayland, the child's renderer/configuration must match the
shared display. Existing RetroArch KMS settings and the standalone Moonlight
probe cannot be blindly used under the compositor. R46H display ownership,
actual game controls and full descendant cleanup remain device integration gates.

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
