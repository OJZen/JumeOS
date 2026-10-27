import QtQuick
import "controls" as Ui
import QtQuick.VirtualKeyboard
import QtQuick.VirtualKeyboard.Settings
import QtQuick.VirtualKeyboard.Styles

// §8 keyboard: Qt's input engine (pinyin, candidates, shift) with Jume layouts and key panels.
// Keys are 64 high, r12, on a 20-column grid; special keys carry their controller badge
// (⇧ X, ⌫ B, 空格 Y, 123 R2, 中/英 L2, 完成 Start). The focus ring is the navigation highlight.
// One key always has the focus: the last one used (q at first), restored after a layout reload,
// a touch or text typed on a USB keyboard or over IPC.
InputPanel {
    id: panel
    property bool reducedMotion: Ui.Theme.reducedMotion
    property string lastKey: "q"
    signal keyFocused(string text)
    readonly property Item focusedKey: keyboard.keyboardInputArea.initialKey
    onFocusedKeyChanged: {
        if (focusedKey) { if (focusedKey.text) keyFocused(focusedKey.text) }
        else Qt.callLater(focusKey, lastKey)
    }
    function findKey(item, text) {
        if (!item) return null
        if (typeof item.displayText === "string" && typeof item.weight === "number" && item.visible && item.enabled
                && (item.text === text || item.displayText === text)) return item
        for (let i = 0; i < item.children.length; ++i) {
            const key = findKey(item.children[i], text)
            if (key) return key
        }
        return null
    }
    function focusKey(text) {
        const area = keyboard.keyboardInputArea, layout = keyboard.keyboardLayoutLoader.item
        if (area.initialKey || !layout) return
        const key = findKey(layout, text) || findKey(layout, "q") || findKey(layout, "1")
        if (!key) return
        keyboard.navigationModeActive = true
        area.navigationCursor = key.mapToItem(area, key.width / 2, key.height / 2)
        area.initialKey = key
    }
    Connections {
        target: panel.keyboard.keyboardLayoutLoader
        function onLoaded() { Qt.callLater(panel.focusKey, panel.lastKey) }
    }
    function navigateHorizontal(action) {
        const area = keyboard.keyboardInputArea
        if (!keyboard.navigationModeActive || !area.initialKey || keyboard.languagePopupListActive
                || keyboard.alternativeKeys.active || keyboard.wordCandidateContextMenu.active) return false
        const direction = keyboard.wordCandidateView.effectiveLayoutDirection === Qt.LeftToRight ? 1 : -1
        area.navigateToNextKey((action === "left" ? -1 : 1) * direction, 0, true)
        return true
    }
    // Up/Down go to the nearest key of the neighbouring row, so the half-key offset of the second
    // row lands on a letter (q ↓ a) instead of falling through to the row below. No wrap; Up from
    // the top row reaches the pinyin candidates when there are any (Qt's own move).
    function visibleKeys(item, list) {
        if (!item || !item.visible) return list
        if (item.hasOwnProperty("keyPanelDelegate") && item.keyPanelDelegate) list.push(item)
        for (let i = 0; i < item.children.length; ++i) visibleKeys(item.children[i], list)
        return list
    }
    function navigateVertical(action) {
        const area = keyboard.keyboardInputArea, layout = keyboard.keyboardLayoutLoader.item
        if (!keyboard.navigationModeActive || !area.initialKey || !layout || keyboard.languagePopupListActive
                || keyboard.alternativeKeys.active || keyboard.wordCandidateContextMenu.active) return false
        const down = action === "down"
        const from = area.initialKey.mapToItem(area, area.initialKey.width / 2, area.initialKey.height / 2)
        let best = null, row = 0, distance = 0
        for (const key of visibleKeys(layout, [])) {
            const at = key.mapToItem(area, key.width / 2, key.height / 2)
            if (down ? at.y <= from.y + 1 : at.y >= from.y - 1) continue
            const nearerRow = !best || (down ? at.y < row - 1 : at.y > row + 1)
            if (nearerRow || (Math.abs(at.y - row) <= 1 && Math.abs(at.x - from.x) < distance)) {
                best = key; row = at.y; distance = Math.abs(at.x - from.x)
            }
        }
        if (!best) return down || keyboard.wordCandidateView.count === 0
        area.navigationCursor = best.mapToItem(area, best.width / 2, best.height / 2)
        area.initialKey = best
        return true
    }
    // §7.4 keyboard keys outside the key grid: X 大小写, L2 中/英, R2 符号. Shift uses the same
    // Qt 6.8.2 handler as the on-screen shift key; the packaged keyboard check guards it.
    function toggleShift() { InputContext.priv.shiftHandler.toggleShift() }
    function toggleLanguage() { VirtualKeyboardSettings.locale = VirtualKeyboardSettings.locale === "zh_CN" ? "en_GB" : "zh_CN" }
    function toggleSymbols() { keyboard.symbolMode = !keyboard.symbolMode }
    // Same pinned Qt 6.8.2 adapter as the layout cache; checked with the packaged IME.
    Binding { target: panel.keyboard.style; property: "navigationHighlightColor"; value: Ui.Theme.focus }
    Binding { target: panel.keyboard; property: "noAnimations"; value: panel.reducedMotion }

    // A key face: background, centered caption or icon, and the controller badge in the corner.
    component Face: Rectangle {
        id: face
        property string caption: ""
        property string iconName: ""
        property string badge: ""
        property bool special: false
        property bool primary: false
        property bool pressed: false
        property bool active: false
        // The focused key: accentSoft with accentInk bold text, inside the navigation ring.
        property bool focused: false
        readonly property bool soft: !primary && (active || focused)
        anchors.fill: parent; anchors.margins: Ui.Theme.space4
        radius: Ui.Theme.radiusKey
        color: primary ? Ui.Theme.accent : soft ? Ui.Theme.accentSoft : special ? Ui.Theme.surfaceSunken : Ui.Theme.ground
        scale: pressed && !panel.reducedMotion ? Ui.Theme.pressScale : 1
        Row {
            anchors.centerIn: parent; spacing: Ui.Theme.space8
            Ui.Icon {
                anchors.verticalCenter: parent.verticalCenter; visible: face.iconName !== ""; name: face.iconName
                color: face.primary ? Ui.Theme.accentText : face.soft ? Ui.Theme.accentInk : Ui.Theme.text
            }
            Ui.Label {
                anchors.verticalCenter: parent.verticalCenter; visible: face.caption !== ""; text: face.caption; elide: Text.ElideNone
                role: face.special ? "label" : "body"
                color: face.primary ? Ui.Theme.accentText : face.soft ? Ui.Theme.accentInk : face.special ? Ui.Theme.textSecondary : Ui.Theme.text
                font.weight: face.primary || face.focused ? Font.Bold : Ui.Theme.type.body.weight
            }
            Ui.GlyphBadge {
                anchors.verticalCenter: parent.verticalCenter; visible: face.badge !== ""; button: face.badge || "A"
                size: Ui.Theme.glyphKeySize; soft: face.primary
            }
        }
    }
    Component {
        id: keyFace
        KeyPanel { Face { caption: control.displayText; pressed: control.pressed; focused: control === panel.focusedKey } }
    }
    Component {
        id: shiftFace
        KeyPanel { Face { iconName: "shift"; badge: "X"; special: true; active: InputContext.shiftActive; pressed: control.pressed; focused: control === panel.focusedKey } }
    }
    Component {
        id: backspaceFace
        KeyPanel { Face { iconName: "backspace"; badge: "B"; special: true; pressed: control.pressed; focused: control === panel.focusedKey } }
    }
    Component {
        id: spaceFace
        KeyPanel { Face { caption: "空格"; badge: "Y"; pressed: control.pressed; focused: control === panel.focusedKey } }
    }
    Component {
        id: symbolFace
        KeyPanel { Face { caption: control.displayText; badge: "R2"; special: true; pressed: control.pressed; focused: control === panel.focusedKey } }
    }
    Component {
        id: languageFace
        KeyPanel { Face { caption: "中/英"; badge: "L2"; special: true; active: VirtualKeyboardSettings.locale === "zh_CN"; pressed: control.pressed; focused: control === panel.focusedKey } }
    }
    Component {
        id: enterFace
        KeyPanel { Face { caption: "完成"; badge: "Start"; primary: true; pressed: control.pressed; focused: control === panel.focusedKey } }
    }
    Component {
        id: background
        Rectangle { color: Ui.Theme.surface }
    }
    Component {
        id: focusRing
        Rectangle {
            color: "transparent"; radius: Ui.Theme.radiusKey + Ui.Theme.focusGap
            border.width: Ui.Theme.focusWidth / 2 + 1; border.color: Ui.Theme.focus
        }
    }
    Component {
        id: candidate
        SelectionListItem {
            id: item
            width: candidateLabel.implicitWidth + 2 * Ui.Theme.space24
            Ui.Label {
                // `display` is the candidate model's role, provided to the delegate's context.
                id: candidateLabel; anchors.centerIn: parent; text: display; elide: Text.ElideNone
                color: item.ListView.isCurrentItem ? Ui.Theme.accentInk : Ui.Theme.text
                font.weight: item.ListView.isCurrentItem ? Font.Bold : Ui.Theme.type.body.weight
            }
        }
    }
    Component {
        id: candidateBackground
        Rectangle { color: Ui.Theme.surface }
    }
    // Application integration: one panel, no extra EGLFS window.
    Component.onCompleted: {
        // Jume layouts: the §8 grid for en_GB and pinyin, symbols shared through fallback.
        VirtualKeyboardSettings.layoutPath = Qt.resolvedUrl("keyboard/layouts")
        const style = keyboard.style
        style.keyboardDesignWidth = Ui.Theme.canvasWidth
        style.keyboardDesignHeight = 4 * (Ui.Theme.keyHeight + 2 * Ui.Theme.space4) + 2 * Ui.Theme.space4
        style.keyboardRelativeLeftMargin = (Ui.Theme.margin - Ui.Theme.space4) / Ui.Theme.canvasWidth
        style.keyboardRelativeRightMargin = (Ui.Theme.margin - Ui.Theme.space4) / Ui.Theme.canvasWidth
        style.keyboardRelativeTopMargin = Ui.Theme.space4 / style.keyboardDesignHeight
        style.keyboardRelativeBottomMargin = Ui.Theme.space4 / style.keyboardDesignHeight
        style.keyboardBackground = background
        style.keyPanel = keyFace
        style.shiftKeyPanel = shiftFace
        style.backspaceKeyPanel = backspaceFace
        style.spaceKeyPanel = spaceFace
        style.symbolKeyPanel = symbolFace
        style.languageKeyPanel = languageFace
        style.enterKeyPanel = enterFace
        style.navigationHighlight = focusRing
        style.selectionListHeight = Ui.Theme.minTarget
        style.selectionListDelegate = candidate
        style.selectionListBackground = candidateBackground
        // Qt 6.8.2 internal loader: cache keys separately from the moving focus ring.
        // The packaged keyboard check guards this dependency when updating Qt.
        keyboard.keyboardLayoutLoader.layer.enabled = true
        VirtualKeyboardSettings.activeLocales = ["en_GB", "zh_CN"]
        VirtualKeyboardSettings.locale = "en_GB"
        Qt.callLater(focusKey, lastKey)
    }
}
