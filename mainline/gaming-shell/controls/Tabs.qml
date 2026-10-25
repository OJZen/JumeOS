pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Templates as T

// §5 section tabs: 48-high capsules between soft L1/R1 badges; the current tab is filled with
// `text`. L1/R1 switch sections without moving focus here; navigationActive marks tab focus.
Row {
    id: tabs
    required property var model
    property int currentIndex: 0
    property bool navigationActive: false
    property bool shoulderHints: true
    property real fontScale: Theme.fontScale
    signal activated(int index)
    spacing: Theme.space8
    GlyphBadge { anchors.verticalCenter: parent.verticalCenter; visible: tabs.shoulderHints; button: "L1"; soft: true; size: Theme.glyphInlineSize }
    Repeater {
        model: tabs.model
        T.AbstractButton {
            id: tab
            required property string modelData
            required property int index
            readonly property bool current: tabs.currentIndex === index
            text: modelData
            implicitHeight: Theme.tabHeight
            implicitWidth: label.implicitWidth + 2 * Theme.space24
            focusPolicy: Qt.NoFocus
            Accessible.role: Accessible.PageTab
            onClicked: tabs.activated(index)
            Rectangle {
                anchors.fill: parent; radius: height / 2
                color: tab.current ? Theme.text : tab.down ? Theme.surfaceSunken : "transparent"
                Rectangle {
                    anchors.fill: parent; anchors.margins: -(Theme.focusGap + Theme.focusWidth)
                    radius: height / 2; color: "transparent"
                    border.width: Theme.focusWidth; border.color: Theme.focus
                    visible: tabs.navigationActive && tab.current
                }
            }
            Label {
                id: label; anchors.centerIn: parent; role: "label"; fontScale: tabs.fontScale
                text: tab.text; color: tab.current ? Theme.surface : Theme.textSecondary; elide: Text.ElideNone
            }
        }
    }
    GlyphBadge { anchors.verticalCenter: parent.verticalCenter; visible: tabs.shoulderHints; button: "R1"; soft: true; size: Theme.glyphInlineSize }
}
