import QtQuick

// §6 page motion: a new route slides in from 48 px to the right while fading in (220 ms, emphasized);
// reduced motion only cross-fades for 100 ms. Input stays live while it runs and retargets.
Item {
    id: page
    property string route: ""
    property bool reducedMotion: Theme.reducedMotion
    property real reveal: 1
    property bool ready: false
    opacity: reveal
    transform: Translate { x: page.reducedMotion ? 0 : Theme.pageShift * (1 - page.reveal) }
    function enter() {
        if (!animation.running) reveal = 0
        animation.restart()
    }
    onRouteChanged: if (ready && visible) enter()
    onReducedMotionChanged: { animation.stop(); reveal = 1 }
    Component.onCompleted: ready = true
    Motion {
        id: animation; objectName: "pageRevealAnimation"; target: page; property: "reveal"; to: 1; curve: "emphasized"
        duration: page.reducedMotion ? Theme.reducedFadeDuration : Theme.pageEnterDuration
    }
}
