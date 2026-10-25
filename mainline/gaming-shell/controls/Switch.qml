import QtQuick
import QtQuick.Templates as T

T.Switch {
    id: control
    property bool reducedMotion: Theme.reducedMotion
    property bool selected: false
    implicitWidth: Theme.switchWidth; implicitHeight: Theme.minTarget; padding: 0
    focusPolicy: Qt.StrongFocus
    indicator: Rectangle {
        x: (control.width - width) / 2; y: (control.height - height) / 2
        width: Theme.switchWidth; height: Theme.switchHeight; radius: height / 2
        color: control.checked ? Theme.accent : Theme.switchOff
        opacity: control.enabled ? 1 : 0.5
        border.width: 0
        Rectangle {
            anchors.fill: parent; anchors.margins: -(Theme.focusGap + Theme.focusWidth); radius: height / 2; color: "transparent"
            border.width: Theme.focusWidth; border.color: Theme.focus; visible: control.enabled && (control.visualFocus || control.selected)
        }
        Rectangle {
            x: Theme.space4 + control.visualPosition * (parent.width - width - 2 * Theme.space4); y: (parent.height - height) / 2; width: Theme.thumbSize; height: width; radius: width / 2
            color: Theme.switchThumb
            Behavior on x { enabled: !control.down && !control.reducedMotion; Motion {} }
        }
    }
}
