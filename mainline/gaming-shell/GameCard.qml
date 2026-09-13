pragma ComponentBehavior: Bound
import QtQuick
import "controls" as Ui

Item {
    id: card
    required property string title
    required property string subtitle
    required property string accent
    required property int artwork
    property bool selected: false
    property bool favorite: false
    property real fontScale: Ui.Theme.fontScale
    property bool reducedMotion: Ui.Theme.reducedMotion
    property bool demonstration: true
    property string iconName: ""
    signal activated()
    signal focused()
    Accessible.role: Accessible.Button
    Accessible.name: title + "，" + subtitle
    Accessible.onPressAction: activated()
    scale: pointer.pressed ? 0.99 : selected ? 1.025 : 1
    Behavior on scale { Ui.Motion { duration: card.reducedMotion || pointer.pressed ? 0 : Ui.Theme.controlDuration } }
    Rectangle {
        anchors.fill: parent; anchors.margins: -5
        radius: 25; color: "transparent"
        border.color: card.selected ? Ui.Theme.accent : "transparent"; border.width: 3
    }
    Rectangle {
        anchors.fill: parent; radius: 20; color: card.accent; clip: true
        layer.enabled: true
        Rectangle {
            x: parent.width * 0.47; y: 12; width: parent.width * 0.46; height: width
            radius: width / 2; color: "#23ffffff"
        }
        // Small procedural cover art; no external assets or decoded full-size posters.
        Item {
            x: card.height < 220 ? card.width - 140 : (card.width - 140) / 2
            y: card.height < 220 ? 12 : 60; width: 140; height: 126
            scale: card.height < 220 ? 0.65 : 1
            Ui.Icon { anchors.centerIn: parent; width: 96; height: width; visible: card.iconName !== ""; name: card.iconName; color: "#ecfff7" }
            Repeater {
                model: card.iconName === "" ? 4 : 0
                Rectangle {
                    required property int index
                    x: 20 + (index % 2) * 45; y: 12 + Math.floor(index / 2) * 45
                    width: 34; height: 34; radius: card.artwork % 2 ? 17 : 7
                    rotation: card.artwork * 15
                    color: index === 0 ? "#ecfff7" : "#88ecfff7"
                }
            }
        }
        Text {
            visible: card.demonstration
            x: 20; y: 18; text: card.artwork === 0 ? "串流入口 · 演示" : "游戏库 · 示例"
            font.pixelSize: 12 * card.fontScale; color: "#e0f2ed"
        }
        Text { anchors.right: parent.right; anchors.rightMargin: 18; y: 17; text: card.favorite ? "★" : ""; color: "white"; font.pixelSize: 20 * card.fontScale }
        Text { x: 20; anchors.bottom: parent.bottom; anchors.bottomMargin: 47; width: parent.width - 40; text: card.title; textFormat: Text.PlainText; color: "white"; font.pixelSize: Ui.Theme.titleSize * card.fontScale; font.bold: true; elide: Text.ElideRight }
        Text { x: 20; anchors.bottom: parent.bottom; anchors.bottomMargin: 23; width: parent.width - 40; text: card.subtitle; textFormat: Text.PlainText; color: "#e0eaf0"; font.pixelSize: Ui.Theme.captionSize * card.fontScale; elide: Text.ElideRight }
    }
    MouseArea { id: pointer; anchors.fill: parent; onClicked: card.activated(); onPressed: card.focused() }
}
