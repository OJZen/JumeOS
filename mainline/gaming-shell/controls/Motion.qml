import QtQuick

NumberAnimation {
    // standard, emphasized (entry) or exit; reduced motion makes every transition immediate.
    property string curve: "standard"
    duration: Theme.reducedMotion ? 0 : Theme.focusDuration
    easing.type: Easing.BezierSpline
    easing.bezierCurve: Theme.curves[curve] || Theme.curves.standard
}
