import QtQuick
import QtQuick.Templates as T

T.Slider {
    id: control
    implicitWidth: 180; implicitHeight: Theme.hitHeight
    leftPadding: Theme.labelGap; rightPadding: Theme.labelGap
    background: Rectangle {
        x: control.leftPadding; y: (control.height - height) / 2
        width: control.availableWidth; height: Theme.trackHeight; radius: 2; color: Theme.track
        Rectangle { width: control.position * parent.width; height: Theme.trackHeight; radius: 2; color: control.enabled ? Theme.accent : Theme.muted }
    }
    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: (control.height - height) / 2; width: Theme.thumbSize; height: width; radius: width / 2
        color: control.enabled ? Theme.accent : Theme.muted
        border.color: Theme.text; border.width: control.visualFocus ? 2 : 0
    }
}
