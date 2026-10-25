import QtQuick
import QtQuick.Shapes

// §5 hold confirmation: a centered card with an 88 ring, the seconds left and one consequence line.
// It appears only after holdDelay of the hold and disappears as soon as the button is released.
Rectangle {
    id: hold
    property real progress: 0
    property int duration: 2000
    property string title: "继续按住以强制结束"
    property string detail: ""
    property real fontScale: Theme.fontScale
    readonly property real elapsed: Math.max(0, Math.min(1, progress)) * duration
    visible: elapsed >= Theme.holdDelay && progress < 1
    width: Math.max(320, content.implicitWidth + 2 * Theme.space32)
    height: content.implicitHeight + 2 * Theme.space32
    radius: Theme.radiusCard; color: Theme.surface
    Accessible.role: Accessible.ProgressBar
    Accessible.name: title
    Shadow {}
    Column {
        id: content
        anchors.centerIn: parent; spacing: Theme.space12
        Item {
            anchors.horizontalCenter: parent.horizontalCenter
            width: Theme.holdRingSize; height: width
            Shape {
                anchors.fill: parent
                preferredRendererType: Shape.CurveRenderer
                ShapePath {
                    strokeColor: Theme.track; strokeWidth: 6; fillColor: "transparent"
                    PathAngleArc { centerX: Theme.holdRingSize / 2; centerY: centerX; radiusX: centerX - 3; radiusY: radiusX; startAngle: 0; sweepAngle: 360 }
                }
                ShapePath {
                    strokeColor: Theme.danger; strokeWidth: 6; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                    PathAngleArc { centerX: Theme.holdRingSize / 2; centerY: centerX; radiusX: centerX - 3; radiusY: radiusX; startAngle: -90; sweepAngle: 360 * Math.max(0, Math.min(1, hold.progress)) }
                }
            }
            Label {
                objectName: "holdSeconds"; anchors.centerIn: parent; role: "headline"; tabular: true; fontScale: hold.fontScale; elide: Text.ElideNone
                text: ((hold.duration - hold.elapsed) / 1000).toFixed(1)
            }
        }
        Label { anchors.horizontalCenter: parent.horizontalCenter; role: "body"; font.weight: Font.Bold; fontScale: hold.fontScale; text: hold.title; elide: Text.ElideNone }
        Label { anchors.horizontalCenter: parent.horizontalCenter; role: "caption"; fontScale: hold.fontScale; text: hold.detail; visible: text !== ""; elide: Text.ElideNone }
    }
}
