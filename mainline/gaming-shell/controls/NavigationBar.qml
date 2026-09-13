pragma ComponentBehavior: Bound
import QtQuick

Row {
    id: bar
    required property var model
    property int currentIndex: 0
    property bool navigationActive: true
    signal activated(int index)
    spacing: Theme.gap
    Repeater {
        model: bar.model
        Button {
            required property string modelData
            required property int index
            text: modelData; width: Math.max(108, implicitWidth); height: Theme.buttonHeight
            selected: bar.navigationActive && bar.currentIndex === index
            Accessible.role: Accessible.PageTab
            onClicked: bar.activated(index)
            background: Rectangle { radius: height / 2; color: bar.currentIndex === parent.index ? Theme.raised : "transparent"; border.width: 2; border.color: parent.selected || parent.visualFocus ? Theme.accent : "transparent" }
        }
    }
}
