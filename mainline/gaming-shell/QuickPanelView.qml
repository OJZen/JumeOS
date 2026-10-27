pragma ComponentBehavior: Bound
import QtQuick
import "controls" as Ui

// §8 quick panel content: a header (current app, its state, battery and time), three tiles
// (Wi-Fi, 性能浮窗, 夜间模式), brightness and volume rows, then the actions. The shell owns
// focus (`current` is an id from shell.quickOrder) and every action.
Column {
    id: content
    required property var shell
    property string current: ""
    property real fontScale: Ui.Theme.fontScale
    spacing: Ui.Theme.space12
    component Ring: Rectangle {
        anchors.fill: parent; anchors.margins: -(Ui.Theme.focusGap + Ui.Theme.focusWidth)
        radius: Ui.Theme.radiusRow + Ui.Theme.focusRadiusExtra; color: "transparent"
        border.width: Ui.Theme.focusWidth
    }
    Row {
        width: parent.width; spacing: Ui.Theme.space8
        Repeater {
            model: [{id: "wifi", label: "Wi-Fi", icon: "wifi"}, {id: "monitor", label: "性能浮窗", icon: "gauge"}, {id: "night", label: "夜间模式", icon: "moon"}]
            Rectangle {
                id: tile
                required property var modelData
                readonly property bool on: content.shell.quickTileOn(modelData.id)
                objectName: "quickTile-" + modelData.id
                width: (content.width - 2 * Ui.Theme.space8) / 3; height: tileColumn.implicitHeight + 2 * Ui.Theme.space16
                radius: Ui.Theme.radiusRow; color: on ? Ui.Theme.accentSoft : Ui.Theme.surfaceSunken
                Accessible.role: Accessible.CheckBox; Accessible.name: modelData.label; Accessible.checked: on
                Column {
                    id: tileColumn
                    anchors.centerIn: parent; width: parent.width - 2 * Ui.Theme.space4; spacing: Ui.Theme.space8
                    Ui.Icon { anchors.horizontalCenter: parent.horizontalCenter; name: tile.modelData.icon; color: tile.on ? Ui.Theme.accentInk : Ui.Theme.text }
                    // One line; at large font sizes it may shrink, never below micro (§3).
                    Ui.Label {
                        width: parent.width; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideNone
                        fontSizeMode: Text.HorizontalFit; minimumPixelSize: Ui.Theme.fontSize("micro")
                        role: "label"; fontScale: content.fontScale; text: tile.modelData.label
                        color: tile.on ? Ui.Theme.accentInk : Ui.Theme.text; font.weight: tile.on ? Font.Bold : Ui.Theme.type.label.weight
                    }
                }
                Ring { visible: content.current === tile.modelData.id; border.color: Ui.Theme.focus }
                MouseArea { anchors.fill: parent; onClicked: content.shell.quickActivate(tile.modelData.id) }
            }
        }
    }
    Repeater {
        model: ["brightness", "volume"]
        Rectangle {
            id: level
            required property string modelData
            readonly property int percent: content.shell.quickLevel(modelData)
            readonly property bool adjustable: content.shell.quickAvailable(modelData)
            objectName: "quickLevel-" + modelData
            width: content.width; height: Math.max(Ui.Theme.minTarget, valueLabel.implicitHeight + Ui.Theme.space16)
            radius: Ui.Theme.radiusRow; color: Ui.Theme.surfaceSunken
            Accessible.role: Accessible.Slider; Accessible.name: (modelData === "volume" ? "音量 " : "亮度 ") + (percent >= 0 ? percent + "%" : "")
            Ui.Icon { id: levelIcon; x: Ui.Theme.space16; anchors.verticalCenter: parent.verticalCenter; name: level.modelData === "volume" ? "volume" : "sun"; color: Ui.Theme.text }
            Rectangle {
                x: levelIcon.x + levelIcon.width + Ui.Theme.space16; anchors.verticalCenter: parent.verticalCenter
                width: valueLabel.x - x - Ui.Theme.space16; height: Ui.Theme.trackHeight; radius: height / 2; color: Ui.Theme.track
                visible: level.percent >= 0
                Rectangle {
                    width: parent.width * Math.max(0, level.percent) / 100; height: parent.height; radius: parent.radius
                    color: content.current === level.modelData && content.shell.quickAdjusting ? Ui.Theme.warning : Ui.Theme.accent
                }
            }
            Ui.Label {
                id: valueLabel; objectName: "quickLevelValue"
                anchors.right: parent.right; anchors.rightMargin: Ui.Theme.space16; anchors.verticalCenter: parent.verticalCenter
                role: level.percent >= 0 ? "label" : "caption"; tabular: true; fontScale: content.fontScale; elide: Text.ElideNone
                color: level.percent >= 0 ? Ui.Theme.text : Ui.Theme.textSecondary
                text: level.percent >= 0 ? level.percent + "%" : "使用机身音量键"
            }
            Ring {
                visible: content.current === level.modelData
                border.color: content.shell.quickAdjusting ? Ui.Theme.warning : Ui.Theme.focus
            }
        }
    }
    Rectangle { width: parent.width; height: 1; color: Ui.Theme.outline }
    Column {
        width: parent.width
        Repeater {
            model: [{id: "home", label: "回到主页", icon: "home", keys: ["Select", "Start"]}, {id: "tasks", label: "任务切换", icon: "tasks", keys: ["Select", "Y"]},
                    {id: "end", label: "结束游戏…", icon: "x-circle", keys: []}]
            Item {
                id: action
                required property var modelData
                // At large font sizes the key combination moves below the label instead of cutting it.
                readonly property bool stacked: actionLabel.x + actionLabel.implicitWidth + Ui.Theme.space8 + keys.width + Ui.Theme.space16 > width
                objectName: "quickAction-" + modelData.id
                visible: content.shell.quickAvailable(modelData.id)
                width: content.width; height: !visible ? 0 : stacked ? actionLabel.implicitHeight + keys.height + 3 * Ui.Theme.space8 : Ui.Theme.minTarget
                Accessible.role: Accessible.Button; Accessible.name: modelData.label
                Rectangle { anchors.fill: parent; radius: Ui.Theme.radiusRow; color: content.current === action.modelData.id ? Ui.Theme.accentSoft : "transparent" }
                Ui.Icon { id: actionIcon; x: Ui.Theme.space16; y: actionLabel.y + (actionLabel.height - height) / 2; name: action.modelData.icon; color: action.modelData.id === "end" ? Ui.Theme.danger : Ui.Theme.text }
                Ui.Label {
                    id: actionLabel
                    x: actionIcon.x + actionIcon.width + Ui.Theme.space16; y: action.stacked ? Ui.Theme.space8 : (action.height - height) / 2
                    width: action.stacked ? action.width - x - Ui.Theme.space16 : keys.x - x - Ui.Theme.space8
                    text: action.modelData.label; fontScale: content.fontScale; color: action.modelData.id === "end" ? Ui.Theme.danger : Ui.Theme.text
                }
                Row {
                    id: keys
                    x: action.stacked ? actionLabel.x : action.width - width - Ui.Theme.space16
                    y: action.stacked ? actionLabel.y + actionLabel.height + Ui.Theme.space8 : (action.height - height) / 2; spacing: Ui.Theme.space4
                    Repeater {
                        model: action.modelData.keys
                        Row {
                            id: key
                            required property string modelData
                            required property int index
                            spacing: Ui.Theme.space4
                            Ui.Label { anchors.verticalCenter: parent.verticalCenter; visible: key.index > 0; text: "+"; role: "micro"; color: Ui.Theme.textTertiary; fontScale: content.fontScale }
                            Ui.GlyphBadge { anchors.verticalCenter: parent.verticalCenter; button: key.modelData; soft: true; size: Ui.Theme.glyphInlineSize }
                        }
                    }
                }
                Ring { visible: content.current === action.modelData.id; border.color: Ui.Theme.focus }
                MouseArea { anchors.fill: parent; onClicked: content.shell.quickActivate(action.modelData.id) }
            }
        }
    }
}
