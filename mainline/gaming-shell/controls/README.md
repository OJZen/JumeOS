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

Use `TopBar` and `HintBar` on every page; the hint bar is generated from the page's
declared actions. The top bar carries the page title and B returns, so pages draw
no title, breadcrumb or back button; a tool page puts its status in a `PageHeader`
line followed by the smallest required `Ui.ListView`. Delegates take the list's
full `width`; the scrollbar overlays the margin 12 px right of the rows. Give
`FocusFrame` the focused delegate's actual position, height and radius; do not
multiply a hard-coded row stride. Only that frame moves.
The shell owns outer navigation. Category or game lists must not instantiate
their detail page while focus moves: A/right activates one asynchronous `Loader`,
and left/B deactivates it and returns to the preserved list selection. USB's
single list is the deliberate one-level variant. Do not debounce directional
input; cancellation belongs to the detail loader, not focus movement.

```qml
Ui.PageHeader { width: parent.width; subtitle: tools.error || status; error: !!tools.error }
Ui.ListView {
    id: rows
    y: Ui.Theme.pageStatusHeight; width: parent.width; height: parent.height - y
    model: options
    delegate: Ui.ListRow {
        required property var modelData
        width: rows.width; title: modelData.title
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

| Component | Contract (JUME-UI §5) |
| --- | --- |
| `Button` | Native `clicked`; `variant` primary / secondary / danger (solid only while focused), `selected` focus, 56 high, r16, press 0.97 + deeper fill |
| `Switch` | Native `checked`/`toggled`; 64×36 track, light 28 thumb, state shown by the track; `selected` draws the ring |
| `Slider` | Native value/step (5%); 8 track, 28 thumb with a 3 px ring; `adjusting` turns warning and grows the thumb to 36 |
| `ProgressBar` | 8 high bounded value; indeterminate motion needs a visible item in a shown window; reduced motion shows a fixed segment |
| `ScrollBar` | Native attached scrollbar with a visible position indicator, overlaid in the right margin 12 px from the rows (`ListView.scrollGap`); no idle animation |
| `Label` | `role` display / title / headline / body / label / caption / micro (`section`, `value` map to headline, label); `tabular` figures |
| `TextField` | Native editing/selection/IME; caller owns maximum length, validation and sensitive-input policy |
| `Icon` | Named 24-unit, 2 px round-stroke icons from `Icon.qml`; `source` accepts custom images without recoloring |
| `ListView` / `TableView` | Qt virtualized/reused delegates and the shared scrollbar; caller supplies model and delegate |
| `ListRow` | 72 or 96 high surface; basic (`chevron`), choice (`value` + `choice`), switch (`toggleState`), `description`, slider (`progress`, `adjusting`), read-only, disabled (`disabledReason`, still focusable); `current` = accentSoft; `flat` rows (category lists) have no surface until current; `trailingIcon` marks e.g. a protected network |
| `FocusFrame` | The one moving ring: target rect + `radius`; 4 px stroke outside a 4 px gap, radius + 7; `adjusting`, `lift`, `bounce(dx, dy)`; settles once after it stops |
| `Tabs` | 48-high capsules between soft L1/R1 badges; current = `text` fill; `navigationActive` rings the current tab |
| `GameCard` | Fallback = card color + 135° 7% stripes (14 px); `iconName` apps (`plain` puts the icon in the card color on the surface), `badge`/`badgeIcon`, `favorite`, `available`; title on 256 cards only, 72 thumbnails show only the art; focus lifts 1.04 with shadow and ring |
| `DockTile` | 88×88 surface r28 with 40 icon and caption; focus 1.06, ring, bold label |
| `GlyphBadge` | A/B/X/Y circles, shoulders r8 squares, Start/Select capsules, d-pad drawings; 34 / 30 / 26; `soft` for content; `progress` hold ring |
| `HintBar` | Built from `actions` ({button, label[, progress]}; `button` from `knownButtons` or two joined by `+`): A B X Y Start fixed at the right, directions/Select/shoulders lead after `context`; at most five; an unknown button is warned about and not drawn (shell-check fails on the warning); `overflow` reports a cramped bar |
| `TopBar` | 72 high; Jume mark or `title`; night, Wi-Fi (`statusWifi.level`), battery and clock on one centerline |
| `Panel` → `Sheet` / `Dialog` / `QuickPanel` | Surface r28 with header, content and hint footer split by dividers; sheet squares its bottom, dialog ≤ 560, quick panel 392 at 24 from the corner |
| `Hud` / `Toast` / `HoldConfirm` | 280×56 top HUD that fades after `hudDwell`; bottom toast (owner clears after `toastDwell`, errors stay); centered hold card shown only after 600 ms |
| `Shadow` | Level-2 elevation from the prerendered nine-slice `elevation.png` (magick: blurred r24 rect, 16% alpha, +4 px); never a live blur |
| `PageHeader` / `Page` | Page status line (caption, danger on error) with a busy progress bar; `Page` slides a new route in from 48 px (100 ms fade with reduced motion) |
| `ChoicePopup` | Native modal `Popup.Item` dialog with pending/current indexes, confirmation and cancellation (B or Select), Start closes; stays in the existing window |
| `OptionsSheet` | Start menu of the focused item or page: `present(title, items, header)` with {id, label[, icon][, button][, hold][, reason]} rows, shortcut glyphs on the right ("按住" before a hold), disabled rows keep their reason; the optional header {subtitle, color, icon, plain} adds a 72 thumbnail; A runs, Start/B/Select close, `chosen(id)` |

`ListRow` composes these primitives for settings, host details and the quick panel.
Read-only rows remain legible but have no native activation; disabled rows keep
their reason visible and stay reachable by controller focus. All row clicks,
including native and accessibility activation, synchronize the logical selection
before emitting `activated`; pointer press still gives early feedback.
Avoid QML property names that start with `on` and a capital letter: QML reads them
as signal handlers, so such a token never binds (`themeTokenContrast` rejects them).

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
success; a failed save retains the pending choice for retry. B, Select or an
outside click cancels an uncommitted choice and restores previous focus. Cancellation after a
failed write does not discard feature-owned dirty data; its save guard remains.
Switch bindings are similarly restored by `ListRow` after native toggling.

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
switches directly with reduced motion. After the focus ring stops it settles once
(1 → 1.03 → 1, 260 ms); held keys keep restarting the wait, so repeats never pulse it.
`bounce(dx, dy)` gives the 6 px edge push. Cards lift with the focus duration and
press scales take 80 ms; reduced motion keeps the end states without the travel. No bounce, animated full-page layout, blur, shadow stack or new
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

The gallery's `foundations` page mirrors `Foundations.png` and its `buttons`,
`rows` and `cards` pages mirror `Components.png`; captures cover light and night at
100% and 130%, and the check asserts that blocks and labels never overlap, leave
the page or truncate. `sharedComponentStates` checks button variants, ring
geometry and settle, hint ordering, the hold threshold, HUD fade and toast dwell. The check also covers pointer/keyboard activation, disabled state, font sizes,
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
