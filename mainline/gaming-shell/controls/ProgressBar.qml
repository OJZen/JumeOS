import QtQuick
import QtQuick.Window
import QtQuick.Templates as T

T.ProgressBar {
    id: control
    implicitWidth: 160; implicitHeight: Theme.trackHeight; padding: 0
    background: Rectangle { color: Theme.track; radius: height / 2 }
    contentItem: Item {
        clip: true
        Rectangle {
            width: control.indeterminate ? parent.width * 0.25 : parent.width * control.position
            height: parent.height; radius: height / 2; color: control.enabled ? Theme.accent : Theme.muted
            x: control.indeterminate ? (Theme.reducedMotion ? (parent.width - width) / 2 : (parent.width + width) * control.phase - width) : 0
        }
    }
    property real phase: 0
    NumberAnimation on phase {
        from: 0; to: 1; duration: 900; loops: Animation.Infinite
        running: control.indeterminate && control.visible && control.enabled && !Theme.reducedMotion
            && control.Window.window !== null && control.Window.window.visible
            && control.Window.window.visibility !== Window.Minimized
    }
    onIndeterminateChanged: if (indeterminate) phase = 0.5
}
