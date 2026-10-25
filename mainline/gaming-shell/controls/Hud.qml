import QtQuick

// §5 HUD: a 280×56 capsule at the top center for volume or brightness. It never takes focus and
// also shows in games; the owner keeps `shown` true for hudDwell after each change, then it fades.
Rectangle {
    id: hud
    property bool shown: false
    property real value: 0
    property string iconName: "volume"
    property string valueText: Math.round(value * 100) + "%"
    property real fontScale: Theme.fontScale
    width: Theme.hudWidth; height: Theme.hudHeight; radius: height / 2
    color: Theme.surface; border.width: 1; border.color: Theme.outline
    opacity: shown ? 1 : 0
    visible: shown || opacity > 0
    Behavior on opacity { Motion { duration: hud.shown ? Theme.hudEnterDuration : Theme.hudExitDuration } }
    Shadow {}
    Icon { x: Theme.space24; anchors.verticalCenter: parent.verticalCenter; name: hud.iconName; color: Theme.text }
    ProgressBar {
        objectName: "hudProgress"
        x: Theme.space24 + Theme.iconSize + Theme.space16; anchors.verticalCenter: parent.verticalCenter
        width: hudLabel.x - x - Theme.space16; value: hud.value; Accessible.ignored: true
    }
    Label {
        id: hudLabel; objectName: "hudLabel"
        anchors.right: parent.right; anchors.rightMargin: Theme.space24; anchors.verticalCenter: parent.verticalCenter
        width: Math.max(implicitWidth, 64 * hud.fontScale); horizontalAlignment: Text.AlignRight
        role: "label"; tabular: true; fontScale: hud.fontScale; text: hud.valueText; elide: Text.ElideNone
    }
}
