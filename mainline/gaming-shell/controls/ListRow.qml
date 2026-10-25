import QtQuick
import QtQuick.Templates as T

// §5 list row: one rounded surface per row, 72 high or 96 with a description, slider or reason.
// Variants: basic (chevron), choice (value + chevron, opens a ChoicePopup), switch (toggleState),
// description, slider (progress, ←→ adjusts in the page), read-only value, and disabled
// (disabledReason; still focusable so the reason can be read). `current` is the selected-but-not-
// focused state. Pages draw the moving FocusFrame; focusOutline lets a row draw its own ring.
T.ItemDelegate {
    id: row
    required property string title
    property string description: ""
    property string iconName: ""
    property string value: ""
    property real progress: -1
    property int toggleState: -1
    property bool choice: false
    property bool chevron: false
    property bool selected: false
    property bool current: false
    property bool adjusting: false
    property bool focusOutline: true
    property bool actionable: true
    property string disabledReason: ""
    property bool reducedMotion: Theme.reducedMotion
    property real fontScale: Theme.fontScale
    readonly property bool disabledRow: disabledReason !== ""
    readonly property string detail: disabledRow ? disabledReason : description
    signal activated()
    signal focused()
    implicitHeight: detail || progress >= 0 ? Theme.listRowTallHeight : Theme.listRowHeight
    padding: 0; focusPolicy: Qt.NoFocus
    enabled: actionable && !disabledRow
    Accessible.role: actionable && !disabledRow ? Accessible.Button : Accessible.StaticText
    Accessible.ignored: toggleState >= 0
    Accessible.name: title + "，" + value + (detail ? "，" + detail : "")
    onPressedChanged: if (pressed) focused()
    onClicked: { focused(); activated() }
    background: Rectangle {
        radius: Theme.radiusRow
        color: row.current ? Theme.accentSoft : row.down ? Theme.pressed(Theme.surface) : Theme.surface
        Rectangle {
            anchors.fill: parent; anchors.margins: -(Theme.focusGap + Theme.focusWidth)
            radius: Theme.radiusRow + Theme.focusRadiusExtra; color: "transparent"
            border.width: Theme.focusWidth; border.color: row.adjusting ? Theme.warning : Theme.focus
            visible: row.selected && row.focusOutline
        }
    }
    contentItem: Item {
        // The text block sits above the slider track on slider rows.
        readonly property real textCenter: row.progress >= 0 ? Theme.space16 + Theme.lineHeight("body") / 2 - height / 2 : 0
        Icon {
            id: leadingIcon
            x: Theme.space24; anchors.verticalCenter: parent.verticalCenter; anchors.verticalCenterOffset: parent.textCenter
            name: row.iconName; visible: row.iconName !== ""
            color: row.current ? Theme.accentInk : row.disabledRow ? Theme.disabledText : Theme.text
        }
        Column {
            x: Theme.space24 + (row.iconName ? Theme.iconSize + Theme.space12 : 0)
            width: Math.max(0, trailing.x - x - Theme.space16); spacing: Theme.space4
            anchors.verticalCenter: parent.verticalCenter; anchors.verticalCenterOffset: parent.textCenter
            Label {
                width: parent.width; text: row.title; fontScale: row.fontScale
                color: row.current ? Theme.accentInk : row.disabledRow ? Theme.disabledText : row.actionable ? Theme.text : Theme.textSecondary
                font.weight: row.current ? Font.Bold : Theme.type.body.weight
            }
            Label { width: parent.width; visible: row.detail !== ""; text: row.detail; role: "caption"; fontScale: row.fontScale; wrapMode: Text.Wrap; maximumLineCount: 2 }
        }
        Item {
            id: trailing
            anchors.right: parent.right; anchors.rightMargin: Theme.space24
            anchors.verticalCenter: parent.verticalCenter; anchors.verticalCenterOffset: parent.textCenter
            width: row.toggleState >= 0 ? Theme.switchWidth : Math.min(parent.width * 0.55, valueLabel.implicitWidth + (marker.visible ? Theme.iconSize + Theme.space8 : 0))
            height: parent.height
            Label {
                id: valueLabel; objectName: "settingValue"
                width: parent.width - (marker.visible ? Theme.iconSize + Theme.space8 : 0)
                anchors.verticalCenter: parent.verticalCenter
                visible: row.toggleState < 0; text: row.value; role: "label"; tabular: true; fontScale: row.fontScale
                color: row.actionable && row.selected && row.progress >= 0 ? Theme.accent : Theme.textSecondary
                font.weight: row.actionable && row.selected && row.progress >= 0 ? Font.Bold : Theme.type.label.weight
                horizontalAlignment: Text.AlignRight
            }
            Icon {
                id: marker
                anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter
                visible: row.toggleState < 0 && (row.choice || row.chevron || row.disabledRow)
                name: row.disabledRow ? "lock" : "chevron-right"; color: Theme.textTertiary
            }
        }
        Slider {
            objectName: "settingSlider"
            x: Theme.space24 - Theme.thumbAdjustingSize / 2; width: parent.width - 2 * x
            anchors.bottom: parent.bottom; anchors.bottomMargin: Theme.space8
            visible: row.progress >= 0; from: 0; to: 1; value: Math.max(0, Math.min(1, row.progress))
            adjusting: row.adjusting; enabled: row.actionable; focusPolicy: Qt.NoFocus
            Accessible.ignored: true
            // The row owns pointer and controller input; the track only shows the value.
            MouseArea { anchors.fill: parent; onPressed: row.focused(); onClicked: row.activated() }
        }
        Switch {
            objectName: "settingSwitch"
            anchors.right: parent.right; anchors.rightMargin: Theme.space24; anchors.verticalCenter: parent.verticalCenter
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
