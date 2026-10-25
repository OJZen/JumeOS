# Shared Qt controls

Use `import "controls" as Ui` from the shell, or the relative path to this
directory from another QML tool. These are QML components over Qt Quick and
Qt Quick Templates, not a new rendering/input framework. The existing shell
CMake target compiles them into its QML resource module; another executable
must include the same QML files and `qmldir`, marking `Theme.qml` as a singleton.
The [Qt customization pattern](https://doc.qt.io/qt-6.8/qtquickcontrols-customize.html)
owns the underlying template APIs. Complex game/library views remain custom.

## Defaults and ownership

`Theme.qml` owns the [Jume UI v1](../../../docs/JUME-UI.md) tokens: the light and
night palette, type ramp, spacing, layout, corner radius, focus geometry and
motion. One application owner binds `Theme.fontScale`, `Theme.reducedMotion`,
`Theme.night` and `Theme.canvasWidth`. Controls have no settings persistence,
device writes or shell commands. State belongs to the calling
feature; pass values in and handle native signals or the documented action.
Labels default to plain text, vertical centering and elision. Use semantic roles,
not page-local pixel sizes. Geometry uses the 1024×768 logical canvas; only text
scales (90/100/115/130%). Do not scale a whole page to implement font size.
Pages keep `Theme.margin` (40 at 1024 wide) on both sides and lay out inside
`Theme.contentWidth` (944).

Colors come only from `Theme.qml`: other QML has no hex value, `Qt.rgba` or named
color. Use `Theme.alpha(token, opacity)` for a translucent variant and
`Theme.cardColor(index)` for fallback card colors; the night palette keeps the
same names. `shell-check qmlColorsComeFromTheme` guards the shell and browser QML;
`themeTokenContrast` keeps text pairs at 4.5:1 or more and focus/card titles at
3:1 or more in both modes.

The interface font is Noto Sans SC Regular/Medium/Bold, the Simplified Chinese
subset of Noto Sans CJK. [`interface-fonts.py`](../interface-fonts.py) pins,
installs and verifies it for packages; `fonts.h` registers it and keeps Droid Sans
Fallback for glyphs outside the subset. Host runs read `R46H_UI_FONT_DIR`, which
`run.sh` points at the verified cache when present.

### Required defaults for new tools

| Property | Default / allowed variant |
| --- | --- |
| Text | display 36/44, title 30/38, headline 26/34, body 24/32, label 22/30, caption 20/26, micro 18/24; `Theme.fontSize(role)` and `lineHeight(role)` apply `fontScale` |
| Color | `ground`, `surface`, `surfaceSunken`, `outline`; `text`, `textSecondary`, `textTertiary`; `focus`, `accent` (+`accentText`/`accentSoft`/`accentInk`); `glyph`/`glyphSoft`; `danger`, `warning`, `scrim` |
| Spacing | `space4` to `space48`; 4 within a group, 8 between rows |
| Page geometry | top bar 72, hint bar 64, `margin` max(40, 4% of width), `contentWidth` × `contentHeight` (944×632); `gridColumns`, `gridCellWidth` and `dualPane` follow `canvasWidth` |
| Rows / targets | list row 72, or 96 with a description or slider; focus targets at least 56 high |
| Button / switch / slider | button 56; switch 64×36 with a light 28 thumb, state shown by the track color; track 8, thumb 28 (36 while adjusting) |
| Corners | badge 8, key 12, row/button 16, grid card 20, card 24, panel/sheet/dock tile 28 |
| Focus | 4 px `focus` stroke, 4 px gap in the container color, radius + 7; cards lift to 1.04 |
| Motion | press 80, focus 120, settle 260, page 220/160, sheet 240/180, dialog 200/140, HUD 180/140, theme 200 ms; `Motion { curve }` selects standard, emphasized or exit |

Pages that the v1 screens replace still read the pre-v1 metric aliases at the end
of `Theme.qml`; new code must not use them.

Set a control's text, value/state and actions first. Do **not** repeat its default
height, font, margin, radius or animation duration in feature QML. Add a shared
variant only for a real layout requirement. The joystick plot, keyboard layout,
compact telemetry and game cover art remain purpose-built; their typography,
colors and interaction feedback still use these tokens where applicable.
Do not hide unavailable actions behind enabled-looking controls, replace switches
with “已开启/已关闭”, or use a progress track for a value with unknown bounds.

Use `PageHeader` on tool pages, followed by the smallest required `Ui.ListView`.
Use the list's `rowWidth` for delegates and the selected delegate's actual
position/height for `FocusFrame`; do not multiply a hard-coded row stride.
The shell owns outer navigation. Category or game lists must not instantiate
their detail page while focus moves: A/right activates one asynchronous `Loader`,
and left/B deactivates it and returns to the preserved list selection. USB's
single list is the deliberate one-level variant. Do not debounce directional
input; cancellation belongs to the detail loader, not focus movement.

```qml
Ui.PageHeader { width: parent.width; title: "工具名称"; iconName: "gamepad" }
Ui.ListView {
    id: rows
    y: Ui.Theme.contentY; width: parent.width; height: parent.height - y
    model: options
    delegate: SettingRow {
        required property var modelData
        width: rows.rowWidth; title: modelData.title
        toggleState: Number(modelData.enabled)
        onActivated: updateOption(modelData.id)
    }
}
```

Icons are decorative companions to readable labels, never the only clue to an
operation. `Icon.qml` contains the original paths; no font glyphs, network fetches
or icon dependency are needed. Reuse a named icon before adding a path. Paths are
static Qt Quick Shapes geometry (already in the runtime); changing selection only
changes its color. Keep source artwork bounded to the displayed size. Game images
may come from a verified local game manifest later; no guessed covers or remote
posters are loaded for the management pages.

| Component | Contract |
| --- | --- |
| `Button` | Native button semantics and `clicked`; `primary`, `selected`, disabled/focus/press feedback |
| `Switch` | Native `checked`/`toggled`; use `Accessible.name` and a nearby `Label` or `SettingRow` |
| `Slider` | Native horizontal value/step/drag/keyboard behavior; `moved` identifies user changes |
| `ProgressBar` | Native bounded value; indeterminate motion requires a visible/enabled item in a shown, non-minimized window; reduced motion shows a fixed segment |
| `ScrollBar` | Native attached scrollbar with a visible position indicator; no idle animation |
| `Label` | `text`, `role: "title" / "section" / "body" / "caption" / "micro"`; use explicit wrapping only where needed |
| `TextField` | Native editing/selection/IME; caller owns maximum length, validation and sensitive-input policy |
| `Icon` | Named navigation/device/game line icons from `Icon.qml`; `source` accepts custom image assets without recoloring |
| `ListView` | Qt virtualized/reused delegates, containment on selection and shared scrollbar; caller supplies its model/delegate |
| `TableView` | Qt's two-axis virtualized table with native selection model; default read-only cells use the model's `display` role; supply a custom delegate for editing |
| `FocusFrame` | Empty outline shared by both sidebars/details; content remains stationary; `active`/`adjusting` select feedback |
| `NavigationBar` | `model`, externally owned `currentIndex`, `activated(index)`; a failed navigation/save can leave selection unchanged |
| `PageHeader` | Shared title/icon/status, optional back/action buttons and determinate or indeterminate bounded-work progress |
| `Page` | A `route` change reveals content; transitions retarget while input stays live, and reduced motion settles immediately |
| `ChoicePopup` | Native modal `Popup.Item` with pending/current indexes, confirmation and cancellation; stays in the existing window |

`SettingRow.qml` composes these primitives for settings, host details and the
quick panel. Its `choice` flag adds a chevron; `toggleState` uses the shared
switch. Read-only rows remain legible but have no native activation. A parent
may still let controller navigation select them to explain unavailability.
All row clicks, including native and accessibility activation, synchronize the
logical selection before emitting `activated`; pointer press still gives early feedback.

## Choices and navigation

Declare one `ChoicePopup` with the page as its `parent`. It flips above the
trigger when space permits and otherwise stays inside that page; long lists
scroll. Data is a string list. Qt's modal popup owns focus and outside clicks;
`popupType: Popup.Item` keeps it compatible with the single EGLFS window.
[Qt popup behavior](https://doc.qt.io/qt-6.8/qml-qtquick-controls-popup.html).

```qml
Ui.Button {
    id: quality
    text: "画质"
    onClicked: choices.present(quality, ["流畅", "标准", "高清"], savedIndex, "画质")
}
Ui.ChoicePopup {
    id: choices
    parent: quality.parent
    onActivated: function(index) {
        if (saveSelection(index)) close()
    }
}
```

The feature implements `saveSelection` and owns `savedIndex`. Highlighting does
not commit. `activated(index)` leaves the popup open until the caller confirms
success; a failed save retains the pending choice for retry. B/outside click
cancels an uncommitted choice and restores previous focus. Cancellation after a
failed write does not discard feature-owned dirty data; its save guard remains.
Switch bindings are similarly restored by `SettingRow` after native toggling.

Route controller actions to `choices.dispatch(action, repeated)` **before**
page/shortcut handling and stop if it returns true. While open, the popup owns
all controller actions, including tab/home shortcuts; it supports Up/Down,
A confirmation and B/Select cancellation. Test `visible` for this routing guard;
Qt's `opened` becomes true only after the entry transition finishes. Native
Up/Down and Tab/Shift+Tab move the same pending selection; Enter/Space confirms
and Escape/Q cancels. Outside clicks dismiss without activating the covered
control. Closing is immediate so focus restoration and controller routing agree.
Keep the shell's explicit page states; no separate router/store is needed.

Popup items move to the window's overlay. A scaled application must apply its
canvas scale to that overlay too; `ShellView.qml` binds scale/origin after the
overlay becomes available. Do not create a second window to implement a menu.

## Motion and performance

Durations and the standard/emphasized/exit curves follow the table above and
[JUME-UI §6](../../../docs/JUME-UI.md#6-动效). Logical selection updates
immediately. A palette change cross-fades one non-live snapshot for 200 ms and
switches directly with reduced motion. No bounce, animated full-page layout, blur, shadow stack or new
per-frame JavaScript loop is added. A focus outline changes its own small
geometry; it does not relayout cached text. Game art, settings content, keyboard
keys and the quick panel retain their existing cache boundaries.

| Before | After | Why |
| --- | --- | --- |
| Moonlight changed per-row borders; settings moved an outline | All tools use `FocusFrame` and shared timings | Consistent feedback without moving row contents |
| Settings/Moonlight/tools used 86/52/60/72 px rows and separate offsets | Shared row variants, header and list defaults | New tools inherit the same spacing and alignment |
| Letter badges and mixed symbols | One named vector icon family | Recognizable tools without decoded posters |
| Presets cycled immediately | A pending choice list commits on confirmation | Choices are visible and cancellation is predictable |
| Inline switches, field and buttons had separate styling | Native template components share one theme | Common spacing, typography, disabled and focus states |

60 FPS means a 16.7 ms frame budget; it is a target, not a result from host
screenshots. Avoid enabling a layer on every primitive: cache only measured
expensive, stable groups. Use the [existing device profiler](../README.md#ui-performance)
for matched R46H checks, including keyboard and HUD workloads. Idle pages should
not repaint continuously. Table/list row creation must follow the viewport.

## Checks and examples

`tests/ControlsGallery.qml` is a developer fixture, not a product menu. It uses
the real controls, a native table model and a 2,000-row list. Run from repo root:

```sh
mkdir -p mainline/out/.cache/r46h-controls-review
R46H_UI_CAPTURE_DIR="$PWD/mainline/out/.cache/r46h-controls-review" \
  mainline/gaming-shell/run.sh --check standardControlsAndChoices streamingNavigation
```

The gallery's `foundations` page mirrors `Foundations.png`; captures cover light
and night at 100% and 130%, and the check asserts that its blocks and labels never
overlap or truncate. The check also covers pointer/keyboard activation, disabled state, font sizes,
viewport-limited delegates, idle repaint, modal isolation, cancellation and
failed-save recovery. The three review regressions also exercise native and
accessibility row activation, Tab/Space isolation, outside clicks, scaled popup
bounds, failed confirmation/retry and hide/minimize/restore animation lifecycle.
Application-list coverage also checks that a nonzero initial selection survives
model creation: selection and the focus outline must name the same row on open.
Shell coverage also checks that rapid category/game selection creates no detail
page, entry loads exactly one detail page, and immediate return cancels creation.
`test-shell-control.py` additionally drives actual popup
navigation and PNG validation through the remote-control protocol. `themedPagesLightAndNight`
captures the current pages in both palettes. New-tool IPC checks cover 100% tool interactions and 130% snapshots of all three
pages, verify modal routing and exercise disposable save import/backup; screenshots do not
prove device motion. The ARM64
builder checks the relocated package and its real Qt keyboard. Device delivery,
LCD pacing and changed-candidate 60 FPS remain a separate physical gate.
