import QtQuick

// Shared structure of Sheet, Dialog and QuickPanel (§5): a header (title or custom items), the
// content and a hint footer, separated by dividers. Height follows the content.
Rectangle {
    id: panel
    property string title: ""
    property var hints: []
    property string hintContext: ""
    property bool squareBottom: false
    property real contentPadding: Theme.space24
    property real fontScale: Theme.fontScale
    default property alias content: body.data
    property alias header: headerSlot.data
    readonly property bool hasHeader: title !== "" || headerSlot.children.length > 0
    color: Theme.surface; radius: Theme.radiusPanel
    implicitHeight: column.implicitHeight + 2 * contentPadding
    Shadow {}
    // A sheet rises from the bottom edge: only its top corners are rounded.
    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: panel.radius; color: panel.color; visible: panel.squareBottom }
    Column {
        id: column
        x: panel.contentPadding; y: panel.contentPadding; width: parent.width - 2 * panel.contentPadding
        spacing: Theme.space16
        Item { id: headerSlot; width: parent.width; height: childrenRect.height; visible: children.length > 0 }
        Label {
            width: parent.width; visible: panel.title !== "" && headerSlot.children.length === 0
            role: "headline"; fontScale: panel.fontScale; text: panel.title
        }
        Rectangle { width: parent.width; height: 1; color: Theme.outline; visible: panel.hasHeader }
        Item { id: body; width: parent.width; height: childrenRect.height }
        Rectangle { width: parent.width; height: 1; color: Theme.outline; visible: panel.hints.length > 0 }
        HintBar { width: parent.width; visible: panel.hints.length > 0; actions: panel.hints; context: panel.hintContext; fontScale: panel.fontScale }
    }
}
