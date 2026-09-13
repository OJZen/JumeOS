import QtQuick
import QtQuick.Templates as T

T.Button {
    id: control
    property bool selected: false
    property bool focusOutline: true
    property bool primary: false
    property string iconName: ""
    property bool reducedMotion: Theme.reducedMotion
    property real fontScale: Theme.fontScale
    implicitWidth: Math.max(100, implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: Theme.buttonHeight
    leftPadding: Theme.padding + (iconName ? Theme.iconSize + Theme.labelGap : 0); rightPadding: Theme.padding; topPadding: 8; bottomPadding: 8
    focusPolicy: Qt.StrongFocus
    scale: down ? 0.98 : 1
    Behavior on scale { Motion { duration: control.down || control.reducedMotion ? 0 : Theme.controlDuration } }
    contentItem: Label { text: control.text; fontScale: control.fontScale; font.bold: true; horizontalAlignment: Text.AlignHCenter; color: !control.enabled ? Theme.muted : control.primary ? Theme.accentText : Theme.text }
    Icon { x: Theme.padding; anchors.verticalCenter: parent.verticalCenter; name: control.iconName; visible: control.iconName !== ""; color: control.primary && control.enabled ? Theme.accentText : Theme.muted }
    background: Rectangle { radius: Theme.radius; color: control.primary && control.enabled ? Theme.accent : control.down || control.selected ? Theme.raised : Theme.surface; border.width: 2; border.color: control.focusOutline && control.enabled && (control.selected || control.visualFocus) ? Theme.accent : "transparent" }
}
