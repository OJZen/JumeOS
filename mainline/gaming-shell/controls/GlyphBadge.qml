import QtQuick
import QtQuick.Shapes

// §5 key badge: A/B/X/Y circles, shoulder keys rounded squares, Start/Select capsules and the d-pad
// as a drawing. Hint bars use glyph (34), content uses glyphSoft (30), keyboard corners 26.
// progress >= 0 draws the hold ring around the badge.
Item {
    id: badge
    property string button: "A"
    property int size: Theme.glyphBarSize
    property bool soft: false
    property real progress: -1
    property color ringColor: Theme.danger
    readonly property string shape: ["A", "B", "X", "Y", "L3", "R3"].indexOf(button) >= 0 ? "circle"
        : ["L1", "R1", "L2", "R2", "dpad", "dpadH", "dpadV"].indexOf(button) >= 0 ? "square" : "capsule"
    readonly property string iconName: ({dpad: "dpad", dpadH: "arrows-h", dpadV: "arrows-v"})[button] || ""
    readonly property color fill: soft ? Theme.glyphSoft : Theme.glyph
    readonly property color ink: soft ? Theme.glyphSoftText : Theme.glyphText
    implicitWidth: shape === "capsule" ? Math.max(size, caption.implicitWidth + size * 0.6) : shape === "square" && !iconName ? Math.round(size * 1.18) : size
    implicitHeight: size
    Accessible.role: Accessible.StaticText
    Accessible.name: button
    Rectangle {
        anchors.fill: parent
        radius: badge.shape === "square" ? Theme.radiusBadge : height / 2
        color: badge.fill
    }
    Text {
        // §3: the only text allowed below micro (16–19 px).
        id: caption; objectName: "glyphLetter"
        anchors.centerIn: parent; visible: badge.iconName === ""
        text: ({R3: "R", L3: "L"})[badge.button] || badge.button
        color: badge.ink; textFormat: Text.PlainText
        font.family: Theme.fontFamily; font.weight: Font.Bold
        font.pixelSize: Math.max(Theme.glyphMinSize, Math.min(Theme.glyphMaxSize, Math.round(badge.size * 0.5)))
    }
    Icon { anchors.centerIn: parent; width: Math.round(badge.size * 0.62); height: width; visible: badge.iconName !== ""; name: badge.iconName; color: badge.ink }
    Shape {
        anchors.fill: parent; anchors.margins: -Theme.space4
        visible: badge.progress >= 0
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: badge.ringColor; strokeWidth: 3; fillColor: "transparent"; capStyle: ShapePath.RoundCap
            PathAngleArc {
                centerX: badge.width / 2 + Theme.space4; centerY: badge.height / 2 + Theme.space4
                radiusX: badge.width / 2 + Theme.space4 - 2; radiusY: badge.height / 2 + Theme.space4 - 2
                startAngle: -90; sweepAngle: 360 * Math.max(0, Math.min(1, badge.progress))
            }
        }
    }
}
