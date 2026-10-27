pragma ComponentBehavior: Bound
import QtQuick
import "controls" as Ui

// §8 tasks: a carousel with the focused card (512×384) centered and its neighbours (420×315)
// showing at the sides; the title and state sit below, the count beside the page title.
Rectangle {
    id: root
    objectName: "taskView"
    property var applications
    property int selected: 0
    // X: a tap closes normally, a 2 s hold force-quits (the shell tracks the hold; §7.4, §7.7).
    property real holdProgress: -1
    property real fontScale: Ui.Theme.fontScale
    property bool reducedMotion: Ui.Theme.reducedMotion
    // Status for the shared top bar, and the stable card color of an application ID.
    property int wifiSignal: -1
    property int batteryPercent: -1
    property bool charging: false
    property string clock: ""
    property var colorFor: function(id) { return Ui.Theme.cardColor(0) }
    property var entryFor: function(id) { return null }
    readonly property var tasks: applications ? applications.tasks : []
    readonly property var currentTask: tasks.length > selected ? tasks[selected] : null
    readonly property bool canAct: currentTask !== null && !currentTask.stopping
    readonly property var hints: canAct
        ? [{button: "A", label: "切换"}, {button: "B", label: "返回"}, {button: "X", label: "关闭", progress: holdProgress}, {button: "Start", label: "选项"}]
        : [{button: "B", label: "返回"}]
    signal dismissed()
    signal activated(string id)
    signal closeRequested(string id)
    signal notice(string text)
    color: Ui.Theme.ground

    function closeSelected() { if (canAct) closeRequested(currentTask.id) }
    function forceSelected() { if (canAct && applications) applications.forceKill(currentTask.id) }
    function optionItems() {
        if (!currentTask) return []
        const reason = canAct ? "" : "正在结束"
        return [{id: "switch", label: "切换过去", button: "A", reason: reason}, {id: "close", label: "关闭", button: "X", reason: reason},
                {id: "force", label: "强制结束", button: "X", hold: true, reason: reason}]
    }
    // Force quit is immediate and irreversible (§7.7): only the X hold runs it, so the row points there.
    function runOption(id) {
        if (id === "switch" && canAct) activated(currentTask.id)
        else if (id === "close") closeSelected()
        else if (id === "force") notice("按住 X 2 秒强制结束")
    }
    function stateText(task) {
        return !task ? "" : task.stopping ? "正在结束…" : task.paused ? "已暂停" : task.foreground ? "当前应用" : "运行中"
    }
    function dispatch(action, repeated) {
        if (action === "up" || action === "left") selected = Math.max(0, selected - 1)
        else if (action === "down" || action === "right") selected = Math.min(tasks.length - 1, selected + 1)
        else if (!repeated && action === "accept" && canAct) activated(currentTask.id)
        else if (!repeated && (action === "back" || action === "quick" || action === "home")) dismissed()
    }
    onTasksChanged: selected = Math.max(0, Math.min(selected, tasks.length - 1))

    Ui.TopBar {
        x: Ui.Theme.margin; width: Ui.Theme.contentWidth; fontScale: root.fontScale
        title: "任务"; badge: root.tasks.length + " / 4"
        wifiSignal: root.wifiSignal; batteryPercent: root.batteryPercent; charging: root.charging; clock: root.clock
    }
    Repeater {
        model: root.tasks
        delegate: Item {
            id: card
            required property var modelData
            required property int index
            readonly property int offset: index - root.selected
            readonly property bool focused: offset === 0
            readonly property real cardWidth: focused ? Ui.Theme.taskCardWidth : Ui.Theme.taskSideWidth
            readonly property real centerX: Ui.Theme.canvasWidth / 2 + Math.sign(offset) * ((Ui.Theme.taskCardWidth + Ui.Theme.taskSideWidth) / 2 + Ui.Theme.space32)
                + Math.sign(offset) * Math.max(0, Math.abs(offset) - 1) * (Ui.Theme.taskSideWidth + Ui.Theme.space32)
            objectName: "taskCard"
            visible: Math.abs(offset) <= 2
            width: cardWidth; height: cardWidth * 3 / 4
            x: centerX - width / 2; y: Ui.Theme.taskCardTop + (Ui.Theme.taskCardWidth * 3 / 4 - height) / 2
            z: focused ? 1 : 0
            Behavior on x { enabled: !root.reducedMotion; Ui.Motion { duration: Ui.Theme.focusDuration * 2 } }
            Behavior on width { enabled: !root.reducedMotion; Ui.Motion { duration: Ui.Theme.focusDuration * 2 } }
            Accessible.role: Accessible.Button
            Accessible.name: card.modelData.title + "，" + root.stateText(card.modelData)
            Accessible.onPressAction: root.selected = card.index
            Ui.GameCard {
                anchors.fill: parent; title: card.modelData.title; showTitle: false
                readonly property var entry: root.entryFor(card.modelData.id)
                cardColor: root.colorFor(card.modelData.id); iconName: card.modelData.preview ? "" : (card.modelData.icon || "")
                plain: !card.modelData.preview && !!entry && !!entry.plain
                selected: card.focused; fontScale: root.fontScale; reducedMotion: root.reducedMotion
                // A captured frame covers the fallback art.
                Image {
                    anchors.fill: parent; source: card.modelData.preview; visible: source.toString() !== ""
                    fillMode: Image.PreserveAspectCrop; cache: false; asynchronous: false
                    layer.enabled: visible
                }
                onFocused: root.selected = card.index
                onActivated: if (card.focused && root.canAct) root.activated(card.modelData.id)
            }
        }
    }
    Column {
        objectName: "taskCaption"
        x: (Ui.Theme.canvasWidth - Ui.Theme.taskCardWidth) / 2; y: Ui.Theme.taskCardTop + Ui.Theme.taskCardWidth * 3 / 4 + Ui.Theme.space24
        width: Ui.Theme.taskCardWidth; spacing: Ui.Theme.space4
        visible: root.currentTask !== null
        Ui.Label { objectName: "taskTitle"; width: parent.width; role: "title"; fontScale: root.fontScale; text: root.currentTask ? root.currentTask.title : "" }
        Ui.Label { objectName: "taskState"; width: parent.width; role: "caption"; fontScale: root.fontScale; color: Ui.Theme.textSecondary; text: root.stateText(root.currentTask) }
    }
    Column {
        anchors.centerIn: parent; spacing: Ui.Theme.space12; visible: root.tasks.length === 0
        Ui.Icon { anchors.horizontalCenter: parent.horizontalCenter; width: 64; height: 64; name: "tasks"; color: Ui.Theme.textTertiary }
        Ui.Label { anchors.horizontalCenter: parent.horizontalCenter; role: "title"; fontScale: root.fontScale; text: "没有后台任务" }
        Ui.Label { anchors.horizontalCenter: parent.horizontalCenter; role: "caption"; fontScale: root.fontScale; text: "在应用中按 Select + Y，可在这里切换任务" }
    }
    Item {
        x: Ui.Theme.margin; y: Ui.Theme.canvasHeight - Ui.Theme.hintBarHeight; width: Ui.Theme.contentWidth; height: Ui.Theme.hintBarHeight
        Rectangle { width: parent.width; height: 1; color: Ui.Theme.outline }
        Ui.HintBar { objectName: "taskHints"; anchors.verticalCenter: parent.verticalCenter; width: parent.width; actions: root.hints; fontScale: root.fontScale }
    }
}
