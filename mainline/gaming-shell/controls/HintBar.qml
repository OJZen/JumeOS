pragma ComponentBehavior: Bound
import QtQuick

// §7.6 hint bar, built from the page's declared actions instead of hand-written rows.
// An action is {button, label[, leading][, progress]}; older ["A / ↵", "确定"] pairs are mapped.
// A B X Y Start sit at the right edge in that order from the right; directions, Select and shoulder
// keys lead on the left after the optional context text. At most five actions are shown.
Item {
    id: bar
    property var actions: []
    property string context: ""
    property real fontScale: Theme.fontScale
    property bool soft: false
    readonly property var trailingOrder: ["Start", "Y", "X", "B", "A"]
    readonly property var legacyKeys: ({"A / ↵": ["A"], "Enter": ["A"], "A / B": ["A"], "B / Esc": ["B"], "Esc": ["B"], "← / B": ["B"],
        "START": ["Start"], "Select / Q": ["Select"], "L1 / R1": ["L1", "R1"], "↑↓": ["dpadV"], "←→": ["dpadH"], "方向": ["dpad"], "方向 / A B": ["dpad"]})
    readonly property var entries: {
        const list = []
        for (let i = 0; i < actions.length && list.length < 5; ++i) {
            const action = actions[i]
            const key = Array.isArray(action) ? action[0] : action.button
            const buttons = legacyKeys[key] || String(key).split("+")
            const leading = action.leading !== undefined ? action.leading
                : ["dpad", "dpadH", "dpadV", "Select", "L1", "R1", "L2", "R2"].indexOf(buttons[0]) >= 0
            list.push({buttons: buttons, label: Array.isArray(action) ? action[1] : action.label, leading: leading,
                       progress: action.progress === undefined ? -1 : action.progress, index: i})
        }
        return list
    }
    readonly property var leadingEntries: entries.filter(function(entry) { return entry.leading })
    readonly property var trailingEntries: entries.filter(function(entry) { return !entry.leading }).sort(function(a, b) {
        return (bar.trailingOrder.indexOf(a.buttons[0]) - bar.trailingOrder.indexOf(b.buttons[0])) || (a.index - b.index)
    })
    readonly property bool overflow: leadingRow.width + trailingRow.width + Theme.space24 > width
    implicitHeight: Theme.glyphBarSize
    component HintEntry: Row {
        id: hint
        required property var modelData
        spacing: Theme.space8
        Repeater {
            model: hint.modelData.buttons
            GlyphBadge {
                required property string modelData
                required property int index
                anchors.verticalCenter: parent.verticalCenter
                button: modelData; soft: bar.soft; progress: index === 0 ? hint.modelData.progress : -1
            }
        }
        Label {
            objectName: "hintLabel"; anchors.verticalCenter: parent.verticalCenter
            role: "label"; fontScale: bar.fontScale; text: hint.modelData.label; color: Theme.text; elide: Text.ElideNone
        }
    }
    Row {
        id: leadingRow
        anchors.left: parent.left; anchors.verticalCenter: parent.verticalCenter; spacing: Theme.space24
        Label { anchors.verticalCenter: parent.verticalCenter; visible: bar.context !== ""; role: "label"; fontScale: bar.fontScale; color: Theme.textSecondary; tabular: true; text: bar.context; elide: Text.ElideNone }
        Repeater { model: bar.leadingEntries; HintEntry {} }
    }
    Row {
        id: trailingRow
        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: Theme.space24
        Repeater { model: bar.trailingEntries; HintEntry {} }
    }
}
