import QtQuick
import QtQuick.Templates as T
import "controls" as Ui

T.ItemDelegate {
    id: row
    required property string title
    property string description: ""
    property string iconName: ""
    property string value: ""
    property real progress: -1
    property int toggleState: -1
    property bool choice: false
    property bool selected: false
    property bool focusOutline: true
    property bool actionable: true
    property bool reducedMotion: Ui.Theme.reducedMotion
    property real fontScale: Ui.Theme.fontScale
    signal activated()
    signal focused()
    implicitHeight: description || progress >= 0 ? Ui.Theme.descriptionRowHeight : Ui.Theme.rowHeight; padding: 0; focusPolicy: Qt.NoFocus
    enabled: actionable
    Accessible.role: actionable ? Accessible.Button : Accessible.StaticText
    Accessible.ignored: toggleState >= 0
    Accessible.name: title + "，" + value + (description ? "，" + description : "")
    onPressedChanged: if (pressed) focused()
    onClicked: { focused(); activated() }
    background: Rectangle {
        radius: Ui.Theme.radius; color: row.selected || row.down ? Ui.Theme.raised : Ui.Theme.surface
        border.color: row.selected && row.focusOutline ? Ui.Theme.accent : "transparent"; border.width: 2
    }
    contentItem: Item {
        Ui.Icon { x: Ui.Theme.padding; anchors.verticalCenter: parent.verticalCenter; name: row.iconName; visible: row.iconName !== ""; color: row.selected ? Ui.Theme.accent : Ui.Theme.muted }
        Column {
            x: Ui.Theme.padding + (row.iconName ? Ui.Theme.iconSize + Ui.Theme.labelGap : 0)
            width: Math.max(0, trailing.x - x - Ui.Theme.labelGap); spacing: Ui.Theme.smallGap
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: row.progress >= 0 ? -5 : 0
            layer.enabled: true
            Ui.Label { width: parent.width; text: row.title; color: row.actionable ? Ui.Theme.text : Ui.Theme.muted; fontScale: row.fontScale; font.bold: row.actionable }
            Ui.Label { width: parent.width; visible: row.description !== ""; text: row.description; role: "caption"; fontScale: row.fontScale; wrapMode: Text.Wrap; maximumLineCount: 2 }
        }
        Item {
            id: trailing
            anchors.right: parent.right; anchors.rightMargin: Ui.Theme.padding
            width: row.toggleState >= 0 ? Ui.Theme.switchWidth : Math.min(parent.width * 0.55, valueLabel.implicitWidth + (row.choice ? Ui.Theme.iconSize + Ui.Theme.gap : 0)); height: parent.height
            Ui.Label {
                id: valueLabel; objectName: "settingValue"; width: parent.width - (row.choice ? Ui.Theme.iconSize + Ui.Theme.gap : 0)
                anchors.verticalCenter: parent.verticalCenter; anchors.verticalCenterOffset: row.progress >= 0 ? -5 : 0
                visible: row.toggleState < 0; text: row.value; color: row.actionable && row.selected ? Ui.Theme.accent : Ui.Theme.muted
                fontScale: row.fontScale; horizontalAlignment: Text.AlignRight
            }
            Ui.Icon { anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; visible: row.choice; name: "chevron-down" }
        }
        Ui.ProgressBar {
            visible: row.progress >= 0; x: Ui.Theme.padding; anchors.bottom: parent.bottom; anchors.bottomMargin: Ui.Theme.labelGap
            width: parent.width - 2 * Ui.Theme.padding; value: Math.max(0, Math.min(1, row.progress))
        }
        Ui.Switch {
            objectName: "settingSwitch"
            anchors.right: parent.right; anchors.rightMargin: Ui.Theme.padding; anchors.verticalCenter: parent.verticalCenter
            focusPolicy: Qt.NoFocus; visible: row.toggleState >= 0; checked: row.toggleState === 1
            reducedMotion: row.reducedMotion
            Accessible.name: row.title
            onPressedChanged: if (pressed) row.focused()
            onToggled: {
                row.focused(); row.activated()
                checked = Qt.binding(function() { return row.toggleState === 1 })
            }
        }
    }
}
