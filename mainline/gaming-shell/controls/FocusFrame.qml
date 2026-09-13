import QtQuick

Rectangle {
    id: frame
    property bool active: true
    property bool adjusting: false
    property bool reducedMotion: Theme.reducedMotion
    // Only this empty outline moves; content geometry and cached text stay fixed.
    property string animationName: "focusMoveX"
    radius: Theme.radius; color: "transparent"; border.width: 2
    border.color: adjusting ? Theme.warning : Theme.accent
    opacity: active ? 1 : 0
    Behavior on x { enabled: frame.visible && !frame.reducedMotion; Motion { objectName: frame.animationName; duration: Theme.focusDuration } }
    Behavior on y { enabled: frame.visible && !frame.reducedMotion; Motion { duration: Theme.focusDuration } }
    Behavior on width { enabled: frame.visible && !frame.reducedMotion; Motion { duration: Theme.focusDuration } }
    Behavior on height { enabled: frame.visible && !frame.reducedMotion; Motion { duration: Theme.focusDuration } }
    Behavior on opacity { Motion { duration: frame.reducedMotion ? 0 : Theme.controlDuration } }
}
