import QtQuick

// §5 dock tile: an 88×88 surface (r28, 1 px outline) with a 40 px icon and a caption label below.
// Focus lifts the tile to 1.06, draws the ring and bolds the label.
Item {
    id: tile
    property string iconName: ""
    property string label: ""
    property bool selected: false
    property bool available: true
    property bool reducedMotion: Theme.reducedMotion
    property real fontScale: Theme.fontScale
    signal activated()
    signal focused()
    implicitWidth: Math.max(Theme.dockTileSize, caption.implicitWidth)
    implicitHeight: Theme.dockTileSize + Theme.space12 + caption.implicitHeight
    Accessible.role: Accessible.Button
    Accessible.name: label
    Accessible.onPressAction: activated()
    Rectangle {
        id: face
        anchors.horizontalCenter: parent.horizontalCenter
        width: Theme.dockTileSize; height: width; radius: Theme.radiusPanel
        color: pointer.pressed ? Theme.pressed(Theme.surface) : Theme.surface
        border.width: 1; border.color: Theme.outline
        scale: pointer.pressed && !tile.reducedMotion ? Theme.pressScale : tile.selected ? Theme.dockFocusScale : 1
        Behavior on scale { enabled: !tile.reducedMotion; Motion { duration: pointer.pressed ? Theme.pressDuration : Theme.focusDuration } }
        Icon { anchors.centerIn: parent; width: Theme.dockIconSize; height: width; name: tile.iconName; color: tile.available ? Theme.text : Theme.disabledText }
        Rectangle {
            objectName: "dockFocus"
            anchors.fill: parent; anchors.margins: -(Theme.focusGap + Theme.focusWidth)
            radius: Theme.radiusPanel + Theme.focusRadiusExtra; color: "transparent"
            border.width: Theme.focusWidth; border.color: Theme.focus
            visible: tile.selected
        }
    }
    Label {
        id: caption
        anchors.horizontalCenter: parent.horizontalCenter; y: Theme.dockTileSize + Theme.space12
        role: "caption"; fontScale: tile.fontScale; text: tile.label; elide: Text.ElideNone
        color: tile.available ? Theme.text : Theme.disabledText
        font.weight: tile.selected ? Font.Bold : Theme.type.caption.weight
    }
    MouseArea { id: pointer; anchors.fill: parent; onClicked: tile.activated(); onPressed: tile.focused() }
}
