import QtQuick
import QtQuick.Templates as T

T.Switch {
    id: control
    property bool reducedMotion: Theme.reducedMotion
    implicitWidth: Theme.switchWidth; implicitHeight: Theme.hitHeight; padding: 0
    focusPolicy: Qt.StrongFocus
    indicator: Rectangle {
        x: (control.width - width) / 2; y: (control.height - height) / 2
        width: Theme.switchWidth; height: Theme.switchHeight; radius: height / 2
        color: control.checked ? Theme.accent : Theme.track
        opacity: control.enabled ? 1 : 0.5
        border.width: control.visualFocus ? 2 : 0; border.color: Theme.text
        Rectangle {
            x: Theme.smallGap + control.visualPosition * (parent.width - width - 2 * Theme.smallGap); y: Theme.smallGap; width: Theme.thumbSize; height: width; radius: width / 2
            color: control.checked ? Theme.accentText : Theme.text
            Behavior on x { enabled: !control.down && !control.reducedMotion; Motion {} }
        }
    }
}
