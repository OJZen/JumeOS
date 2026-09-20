# Shared Qt controls

Use `import "controls" as Ui` from the shell, or the relative path to this
directory from another QML tool. These are QML components over Qt Quick and
Qt Quick Templates, not a new rendering/input framework. The existing shell
CMake target compiles them into its QML resource module; another executable
must include the same QML files and `qmldir`, marking `Theme.qml` as a singleton.
The [Qt customization pattern](https://doc.qt.io/qt-6.8/qtquickcontrols-customize.html)
owns the underlying template APIs. Complex game/library views remain custom.

## Defaults and ownership

`Theme.qml` owns the palette, spacing, corner radius, text scale and motion
durations. One application owner binds `Theme.fontScale` and
`Theme.reducedMotion` to its preferences. Controls have no settings persistence,
device writes or shell commands. State belongs to the calling
feature; pass values in and handle native signals or the documented action.
Labels default to plain text, vertical centering and elision. Use semantic roles,
not page-local pixel sizes. Geometry uses the 1024×768 logical canvas; only text
scales from 100–120%. Do not scale a whole page to implement font size. The
compact header status uses caption text, 18 px icon boxes, `smallGap` within each
metric and `labelGap` between metrics, all on one centerline.

### Required defaults for new tools

| Property | Default / allowed variant |
| --- | --- |
| Text | title 26, section 20, body/value/input 18, caption 14, micro 12 px, multiplied by `fontScale` |
| Spacing | 4 within a label group, 8 between rows, 12 between icon/label, 20 inside controls |
| Page geometry | 36 outer margin, tool top 100 / height 576, 952 content width, 256 sidebar, 32 column gap; lists begin at `Theme.contentY` (84) |
| Row | 60 high; 84 when it has a description or progress track; derive focus height from the actual row |
| Button / editor / hit area | 48 / 56 / at least 48 high; width follows content plus padding |
| Switch | 56×32 track, 24 thumb inside a 48-high hit area |
| Track / scrollbar | 4 track; reserve 8 for scrollbars through `ListView.rowWidth` |
| Corners / icons | 12 radius; 24 row icon, 32 page icon; one original 24-unit stroke family |
| Alignment | row contents vertically centered, title left, value right; reserve trailing width before laying out text |
| Motion | focus 90, control 100, page 140, popup 150 ms; `Motion` owns easing, `Theme.reducedMotion` owns the opt-out |

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

Focus movement takes 90 ms, control feedback 100 ms, page reveals 140 ms and
popup entry 150 ms, with one shared ease-out curve. Logical selection updates
immediately. No bounce, animated full-page layout, blur, shadow stack or new
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

The check covers pointer/keyboard activation, disabled state, font sizes,
viewport-limited delegates, idle repaint, modal isolation, cancellation and
failed-save recovery. The three review regressions also exercise native and
accessibility row activation, Tab/Space isolation, outside clicks, scaled popup
bounds, failed confirmation/retry and hide/minimize/restore animation lifecycle.
Application-list coverage also checks that a nonzero initial selection survives
model creation: selection and the focus outline must name the same row on open.
Shell coverage also checks that rapid category/game selection creates no detail
page, entry loads exactly one detail page, and immediate return cancels creation.
`test-shell-control.py` additionally drives actual popup
navigation and PNG validation through the remote-control protocol. New-tool IPC checks cover 100% tool interactions and 120% snapshots of all three
pages, verify modal routing and exercise disposable save import/backup; screenshots do not
prove device motion. The ARM64
builder checks the relocated package and its real Qt keyboard. Device delivery,
LCD pacing and changed-candidate 60 FPS remain a separate physical gate.
