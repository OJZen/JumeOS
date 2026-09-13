import QtQuick

Item {
    id: page
    property string route: ""
    property bool reducedMotion: Theme.reducedMotion
    property real reveal: 1
    property bool ready: false
    opacity: 0.65 + 0.35 * reveal
    transform: Translate { y: 8 * (1 - page.reveal) }
    function enter() {
        if (reducedMotion) { animation.stop(); reveal = 1; return }
        if (!animation.running) reveal = 0
        animation.restart()
    }
    onRouteChanged: if (ready && visible) enter()
    onReducedMotionChanged: if (reducedMotion) { animation.stop(); reveal = 1 }
    Component.onCompleted: ready = true
    Motion { id: animation; objectName: "pageRevealAnimation"; target: page; property: "reveal"; to: 1; duration: Theme.pageDuration }
}
