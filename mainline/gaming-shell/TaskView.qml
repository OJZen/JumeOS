pragma ComponentBehavior: Bound
import QtQuick
import "controls" as Ui

Rectangle {
    id: root
    objectName: "taskView"
    property var applications
    property int selected: 0
    readonly property var tasks: applications ? applications.tasks : []
    readonly property var currentTask: tasks.length > selected ? tasks[selected] : null
    readonly property bool canAct: currentTask !== null && !currentTask.stopping
    signal dismissed()
    signal activated(string id)
    signal closeRequested(string id)
    color: Ui.Theme.background

    function closeSelected() { if (canAct) closeRequested(currentTask.id) }
    function forceSelected(anchor) {
        if (!canAct) return
        confirm.taskId = currentTask.id
        confirm.present(anchor || forceButton, ["取消", "强制终止"], 0, "未保存内容将丢失")
    }
    function dispatch(action, repeated) {
        if (confirm.visible) { confirm.dispatch(action, repeated); return }
        if (action === "up" || action === "left") selected = Math.max(0, selected - 1)
        else if (action === "down" || action === "right") selected = Math.min(tasks.length - 1, selected + 1)
        else if (!repeated && action === "accept" && canAct) activated(currentTask.id)
        else if (!repeated && action === "erase") closeSelected()
        else if (!repeated && action === "favorite") forceSelected(null)
        else if (!repeated && (action === "back" || action === "quick" || action === "home")) dismissed()
    }
    onTasksChanged: selected = Math.max(0, Math.min(selected, tasks.length - 1))

    Ui.Label { x: 36; y: 25; width: 680; height: 48; role: "title"; text: "后台任务" }
    Ui.Label { x: 36; y: 76; width: 760; height: 28; role: "caption"; text: root.tasks.length ? "选择任务，继续上次的进度" : "运行过的应用会出现在这里" }
    Rectangle {
        x: 856; y: 32; width: 132; height: 44; radius: 22
        color: Ui.Theme.surface; border.color: Ui.Theme.outline
        Ui.Label { anchors.centerIn: parent; role: "caption"; font.bold: true; text: "后台 " + root.tasks.length + " / 4" }
    }

    Rectangle {
        id: featured
        x: 36; y: 130; width: 602; height: 484; radius: 18; clip: true
        visible: root.currentTask !== null
        color: Ui.Theme.surface; border.color: Ui.Theme.outline
        Image {
            anchors.fill: parent; source: root.currentTask ? root.currentTask.preview : ""
            fillMode: Image.PreserveAspectCrop; cache: false; asynchronous: false
        }
        Ui.Icon {
            width: 84; height: 84; anchors.centerIn: parent
            name: root.currentTask ? root.currentTask.icon : "monitor"
            color: Ui.Theme.outline
            visible: !root.currentTask || !root.currentTask.preview
        }
        Rectangle {
            anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
            height: 156
            gradient: Gradient {
                GradientStop { position: 0; color: "#00111a24" }
                GradientStop { position: 0.5; color: "#cc111a24" }
                GradientStop { position: 1; color: "#f5111a24" }
            }
        }
        Rectangle {
            x: 20; y: 20; width: 114; height: 34; radius: 17; color: "#de111a24"
            Rectangle { x: 12; anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8; radius: 4; color: Ui.Theme.accent }
            Ui.Label { x: 28; anchors.verticalCenter: parent.verticalCenter; width: 78; role: "micro"; font.bold: true; text: "当前选择" }
        }
        Ui.Icon { x: 24; y: 415; width: 32; height: 32; name: root.currentTask ? root.currentTask.icon : "monitor"; color: Ui.Theme.accent }
        Ui.Label { x: 68; y: 403; width: 510; height: 42; role: "title"; text: root.currentTask ? root.currentTask.title : "" }
        Ui.Label {
            x: 68; y: 447; width: 510; height: 24; role: "caption"
            text: !root.currentTask ? "" : root.currentTask.stopping ? "正在结束…" : root.currentTask.paused ? "已暂停 · 返回后继续" : root.currentTask.foreground ? "当前应用" : "后台运行中"
        }
        TapHandler { enabled: root.canAct; onTapped: root.activated(root.currentTask.id) }
    }

    Column {
        x: 654; y: 130; width: 334; spacing: 12
        visible: root.tasks.length > 0
        Repeater {
            model: root.tasks
            delegate: Rectangle {
                id: row
                required property var modelData
                required property int index
                width: 334; height: 112; radius: 14
                color: root.selected === index ? Ui.Theme.raised : Ui.Theme.surface
                border.width: root.selected === index ? 2 : 1
                border.color: root.selected === index ? Ui.Theme.accent : Ui.Theme.outline
                Accessible.role: Accessible.Button
                Accessible.name: modelData.title
                Accessible.onPressAction: root.selected = index
                Rectangle {
                    x: 12; y: 12; width: 116; height: 88; radius: 8; clip: true; color: Ui.Theme.background
                    Image { anchors.fill: parent; source: row.modelData.preview; fillMode: Image.PreserveAspectCrop; cache: false; asynchronous: false }
                    Ui.Icon { anchors.centerIn: parent; name: row.modelData.icon; visible: !row.modelData.preview }
                }
                Ui.Label { x: 142; y: 17; width: 174; height: 29; role: "section"; text: row.modelData.title }
                Ui.Label {
                    x: 142; y: 51; width: 174; height: 24; role: "caption"
                    text: row.modelData.stopping ? "正在结束…" : row.modelData.paused ? "已暂停" : row.modelData.foreground ? "当前应用" : "后台运行"
                }
                Rectangle { x: 142; y: 85; width: 18; height: 3; radius: 2; color: root.selected === row.index ? Ui.Theme.accent : Ui.Theme.outline }
                TapHandler { onTapped: root.selected = row.index }
            }
        }
    }

    Rectangle {
        x: 36; y: 130; width: 952; height: 484; radius: 18
        visible: root.tasks.length === 0; color: Ui.Theme.surface; border.color: Ui.Theme.outline
        Ui.Icon { width: 72; height: 72; anchors.horizontalCenter: parent.horizontalCenter; y: 128; name: "monitor"; color: Ui.Theme.muted }
        Ui.Label { width: parent.width; y: 222; role: "title"; horizontalAlignment: Text.AlignHCenter; text: "没有后台任务" }
        Ui.Label { width: parent.width; y: 264; role: "caption"; horizontalAlignment: Text.AlignHCenter; text: "在应用中按 Select + Y，可在这里切换任务" }
    }

    Rectangle {
        x: 36; y: 644; width: 952; height: 72; radius: 16
        color: Ui.Theme.surface; border.color: Ui.Theme.outline
        Ui.Button { x: 14; y: 12; width: 218; text: "A  继续应用"; primary: true; enabled: root.canAct; onClicked: root.activated(root.currentTask.id) }
        Ui.Button { x: 246; y: 12; width: 218; text: "Y  正常关闭"; enabled: root.canAct; onClicked: root.closeSelected() }
        Ui.Button {
            id: forceButton; x: 478; y: 12; width: 218; text: "X  强制结束"
            enabled: root.canAct; onClicked: root.forceSelected(this)
            contentItem: Ui.Label { text: forceButton.text; color: forceButton.enabled ? Ui.Theme.danger : Ui.Theme.muted; font.bold: true; horizontalAlignment: Text.AlignHCenter }
        }
        Ui.Button { x: 710; y: 12; width: 228; text: "B  返回桌面"; onClicked: root.dismissed() }
    }
    Ui.ChoicePopup {
        id: confirm; objectName: "taskKillChoice"; property string taskId: ""
        onActivated: function(index) { close(); if (index === 1 && root.applications) root.applications.forceKill(taskId) }
    }
}
