pragma ComponentBehavior: Bound
import QtQuick

// §8 power menu: a centered dialog naming the background apps, then 息屏, 重启 and 关机 with 息屏
// focused. 重启 and 关机 ask once more (§7.7) with 取消 focused and what will be ended. A row
// without a reason runs; B steps back or closes, Select closes. The shell performs `chosen(id)`.
Item {
    id: menu
    property bool open: false
    property int index: 0
    property string confirming: ""
    property var apps: []
    property var reasons: ({})
    property real fontScale: Theme.fontScale
    property bool reducedMotion: Theme.reducedMotion
    readonly property var labels: ({screenOff: "息屏", reboot: "重启", poweroff: "关机"})
    readonly property var rows: confirming ? [{id: "cancel", label: "取消", icon: "x-circle"}, {id: confirming, label: labels[confirming], icon: confirming === "reboot" ? "restart" : "power"}]
        : [{id: "screenOff", label: "息屏", icon: "screen-off"}, {id: "reboot", label: "重启", icon: "restart"}, {id: "poweroff", label: "关机", icon: "power"}]
    readonly property string appsText: apps.length ? "后台有 " + apps.length + " 个应用：" + apps.join("、") : "没有后台应用"
    signal chosen(string id)
    visible: open || dialog.opacity > 0
    function present(backgroundApps) { apps = backgroundApps; confirming = ""; index = 0; open = true }
    function close() { open = false; confirming = "" }
    function dispatch(action, repeated) {
        if (!open) return false
        if (action === "up") index = Math.max(0, index - 1)
        else if (action === "down") index = Math.min(rows.length - 1, index + 1)
        else if (repeated) return true
        else if (action === "back") {
            if (!confirming) { close(); return true }
            const was = confirming
            confirming = ""; index = was === "reboot" ? 1 : 2
        }
        else if (action === "quick") close()
        else if (action === "accept") activate(index)
        return true
    }
    function activate(position) {
        const row = rows[position]
        if (!row || reasons[row.id]) return
        if (row.id === "cancel") { close(); return }
        if (!confirming && row.id !== "screenOff") { confirming = row.id; index = 0; return }
        close(); chosen(row.id)
    }
    Rectangle {
        anchors.fill: parent; color: Theme.scrim
        opacity: menu.open ? 1 : 0; visible: opacity > 0
        Behavior on opacity { Motion { duration: menu.reducedMotion ? Theme.reducedFadeDuration : menu.open ? Theme.dialogEnterDuration : Theme.dialogExitDuration } }
        MouseArea { anchors.fill: parent; enabled: menu.open; onClicked: menu.close() }
    }
    Dialog {
        id: dialog; objectName: "powerMenu"
        anchors.centerIn: parent; fontScale: menu.fontScale
        opacity: menu.open ? 1 : 0; scale: menu.open || menu.reducedMotion ? 1 : Theme.dialogStartScale
        Behavior on opacity { Motion { curve: menu.open ? "emphasized" : "exit"; duration: menu.reducedMotion ? Theme.reducedFadeDuration : menu.open ? Theme.dialogEnterDuration : Theme.dialogExitDuration } }
        Behavior on scale { enabled: !menu.reducedMotion; Motion { curve: "emphasized"; duration: Theme.dialogEnterDuration } }
        hints: [{button: "A", label: "确定"}, {button: "B", label: menu.confirming ? "返回" : "取消"}]
        header: Row {
            width: parent ? parent.width : 0; spacing: Theme.space16
            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: Theme.minTarget; height: width; radius: width / 2; color: Theme.surfaceSunken
                Icon { anchors.centerIn: parent; name: menu.confirming === "reboot" ? "restart" : "power"; color: Theme.text }
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter; spacing: Theme.space4
                width: parent.width - Theme.minTarget - Theme.space16
                Label { objectName: "powerTitle"; width: parent.width; role: "headline"; fontScale: menu.fontScale; text: menu.confirming ? "确认" + menu.labels[menu.confirming] + "？" : "电源" }
                Label {
                    objectName: "powerApps"; width: parent.width; role: "caption"; fontScale: menu.fontScale; color: Theme.textSecondary
                    wrapMode: Text.Wrap; elide: Text.ElideNone
                    text: menu.confirming && menu.apps.length ? "会结束 " + menu.apps.length + " 个后台应用：" + menu.apps.join("、") : menu.appsText
                }
            }
        }
        Column {
            width: parent.width
            Repeater {
                model: menu.rows
                ListRow {
                    required property var modelData
                    required property int index
                    objectName: "power-" + modelData.id
                    width: parent.width; fontScale: menu.fontScale; reducedMotion: menu.reducedMotion
                    title: modelData.label; iconName: modelData.icon; disabledReason: menu.reasons[modelData.id] || ""
                    selected: menu.index === index; current: selected
                    onFocused: menu.index = index
                    onActivated: menu.activate(index)
                }
            }
        }
    }
}
