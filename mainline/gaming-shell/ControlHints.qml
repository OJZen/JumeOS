pragma ComponentBehavior: Bound
import QtQuick
import "controls" as Ui

Row {
    id: hints
    required property var actions
    property real fontScale: Ui.Theme.fontScale
    property bool gamepad: false
    function keyLabel(value) {
        return gamepad ? ({"A / ↵": "A", "B / Esc": "B", "Select / Q": "Select"}[value] || value) : value
    }
    spacing: 22
    Repeater {
        model: hints.actions
        Row {
            required property var modelData
            spacing: 8
            Rectangle {
                width: key.implicitWidth + 14; height: 28; radius: 7
                color: "#253641"; border.color: Ui.Theme.outline
                Ui.Label { id: key; anchors.centerIn: parent; text: hints.keyLabel(parent.parent.modelData[0]); color: "#e0eee9"; font.pixelSize: 12 * hints.fontScale; font.bold: true }
            }
            Ui.Label { objectName: "hintLabel"; anchors.verticalCenter: parent.verticalCenter; text: parent.modelData[1]; color: Ui.Theme.muted; font.pixelSize: 13 * hints.fontScale }
        }
    }
}
