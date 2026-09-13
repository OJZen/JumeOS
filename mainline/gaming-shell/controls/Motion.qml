import QtQuick

NumberAnimation {
    duration: Theme.reducedMotion ? 0 : Theme.controlDuration
    easing.type: Easing.BezierSpline
    easing.bezierCurve: Theme.curve
}
