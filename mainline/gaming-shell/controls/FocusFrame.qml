import QtQuick

// The one moving focus ring (§4). Give it the focused element's own rect and corner radius: the
// 4 px ring sits outside a gap that shows the container, with radius + 7. Only this outline moves;
// after it stops it settles once (1 → 1.03 → 1), so held keys never pulse.
Item {
    id: frame
    property bool active: true
    property bool adjusting: false
    property bool reducedMotion: Theme.reducedMotion
    property real radius: Theme.radiusRow
    property real lift: 1
    property string animationName: "focusMoveX"
    property real settle: 1
    property real nudgeX: 0
    property real nudgeY: 0
    property bool ready: false
    // Edge feedback: a short 6 px push toward the blocked direction.
    function bounce(dx, dy) {
        if (reducedMotion || !visible) return
        bounceX.to = dx * Theme.edgeBounce; bounceY.to = dy * Theme.edgeBounce; bounceAnimation.restart()
    }
    function moved() { if (ready) { settleAnimation.stop(); settle = 1; settleTimer.restart() } }
    opacity: active ? 1 : 0
    scale: lift * settle
    transform: Translate { x: frame.nudgeX; y: frame.nudgeY }
    onXChanged: moved()
    onYChanged: moved()
    Component.onCompleted: Qt.callLater(function() { frame.ready = true })
    Rectangle {
        objectName: "focusRing"
        anchors.fill: parent; anchors.margins: -(Theme.focusGap + Theme.focusWidth)
        radius: frame.radius + Theme.focusRadiusExtra; color: "transparent"
        border.width: Theme.focusWidth; border.color: frame.adjusting ? Theme.warning : Theme.focus
    }
    Behavior on x { enabled: frame.visible && !frame.reducedMotion; Motion { objectName: frame.animationName; duration: Theme.focusDuration } }
    Behavior on y { enabled: frame.visible && !frame.reducedMotion; Motion { duration: Theme.focusDuration } }
    Behavior on width { enabled: frame.visible && !frame.reducedMotion; Motion { duration: Theme.focusDuration } }
    Behavior on height { enabled: frame.visible && !frame.reducedMotion; Motion { duration: Theme.focusDuration } }
    Behavior on lift { enabled: frame.visible && !frame.reducedMotion; Motion { duration: Theme.focusDuration } }
    Behavior on opacity { Motion { duration: frame.reducedMotion ? 0 : Theme.focusDuration } }
    Timer {
        id: settleTimer; interval: Theme.focusDuration + 40
        onTriggered: if (frame.visible && frame.active && !frame.reducedMotion) settleAnimation.restart()
    }
    SequentialAnimation {
        id: settleAnimation; objectName: "focusSettle"
        Motion { target: frame; property: "settle"; to: Theme.settleScale; duration: Theme.settleDuration / 2 }
        Motion { target: frame; property: "settle"; to: 1; duration: Theme.settleDuration / 2 }
    }
    SequentialAnimation {
        id: bounceAnimation
        ParallelAnimation {
            Motion { id: bounceX; target: frame; property: "nudgeX"; duration: Theme.pressDuration }
            Motion { id: bounceY; target: frame; property: "nudgeY"; duration: Theme.pressDuration }
        }
        ParallelAnimation {
            Motion { target: frame; property: "nudgeX"; to: 0; duration: Theme.focusDuration }
            Motion { target: frame; property: "nudgeY"; to: 0; duration: Theme.focusDuration }
        }
    }
}
