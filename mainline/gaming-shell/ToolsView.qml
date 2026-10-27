pragma ComponentBehavior: Bound
import QtQuick
import "controls" as Ui

// Dock 工具: the Jume tools as list rows; an unavailable tool stays focusable with its reason.
Item {
    id: toolsView
    required property var items
    property int index: 0
    property bool ringVisible: true
    property real fontScale: Ui.Theme.fontScale
    property bool reducedMotion: Ui.Theme.reducedMotion
    signal activated(int position)
    Ui.ListView {
        // Rows draw their own focus ring, so the list keeps a ring's width of room on every side.
        readonly property int ring: Ui.Theme.focusGap + Ui.Theme.focusWidth
        id: list; objectName: "toolsList"
        x: -ring; width: parent.width + 2 * ring; height: parent.height
        topMargin: ring; bottomMargin: ring
        spacing: Ui.Theme.space8; model: toolsView.items; currentIndex: toolsView.index
        delegate: Ui.ListRow {
            required property var modelData
            required property int index
            x: list.ring; width: list.width - 2 * list.ring; fontScale: toolsView.fontScale; reducedMotion: toolsView.reducedMotion
            title: modelData.title; description: modelData.reason ? "" : modelData.detail
            iconName: modelData.icon; disabledReason: modelData.reason || ""; chevron: true
            selected: toolsView.index === index; focusOutline: toolsView.ringVisible
            onFocused: toolsView.index = index
            onActivated: toolsView.activated(index)
        }
    }
}
