import QtQuick
import QtQuick.Templates as T

T.ScrollBar {
    id: control
    minimumSize: 0.08
    padding: 2
    implicitWidth: 8; implicitHeight: 8
    policy: T.ScrollBar.AsNeeded
    contentItem: Rectangle { implicitWidth: 4; implicitHeight: 4; radius: 2; color: control.pressed ? Theme.accent : Theme.muted; opacity: control.size < 1 ? (control.active ? 0.9 : 0.4) : 0 }
}
