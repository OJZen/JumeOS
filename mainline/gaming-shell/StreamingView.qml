pragma ComponentBehavior: Bound
import QtQuick
import "controls" as Ui

Item {
    id: view
    required property var manager
    required property var store
    property bool sidebar: true
    property int row: 0
    property bool navigationActive: true
    property string choiceKind: "preset"
    readonly property bool choiceOpen: choices.visible
    readonly property real fontScale: store.fontPercent / 100
    readonly property var host: manager.current
    readonly property var presets: ["640×480 · 60 FPS · 4 Mbps", "640×480 · 30 FPS · 3 Mbps", "1024×768 · 60 FPS · 8 Mbps"]
    readonly property var hints: choices.visible ? choices.hints : manager.busy ? [["B / Esc", "取消"]]
        : sidebar ? [["↑↓", "选择主机"], ["A / ↵", "进入"], ["X", "添加主机"], ["B / Esc", "返回"]]
        : [["↑↓", "选择项目"], ["← / B", "主机列表"], ["A / ↵", row === 3 ? "选择画质" : "确定"]]
    signal editRequested(string key, string label, string value)
    signal backRequested()
    function selectionVisible(list) {
        const item = list.currentItem
        return item && item.y >= list.contentY && item.y + item.height <= list.contentY + list.height + 1
    }
    function addHost() { editRequested("add", "主机 IPv4 地址或名称", "") }
    function chooseApplication() {
        choiceKind = "application"
        const names = manager.applications
        choices.present(detailRows.currentItem, names.concat(["刷新应用列表", "手动输入名称"]), names.indexOf(host.application), "应用")
    }
    function activate() {
        if (!manager.hosts.length) { addHost(); return }
        if (row === 0) editRequested("name", "主机名称", host.name)
        else if (row === 1) editRequested("address", "主机 IPv4 地址或名称", host.address)
        else if (row === 2) chooseApplication()
        else if (row === 3) { choiceKind = "preset"; choices.present(detailRows.currentItem, presets, host.preset, "画质") }
        else if (row === 4) manager.toggleOverlay()
        else if (row === 5) manager.pair()
        else if (row === 6) manager.requestStream()
        else if (row === 7 && manager.removeSelected()) { sidebar = true; row = 0 }
    }
    function dispatch(action, repeated) {
        if (choices.dispatch(action, repeated)) return
        if (manager.busy) { if (action === "back") manager.cancelPair(); return }
        if (action === "favorite" && !repeated) { addHost(); return }
        if (action === "back" || (!sidebar && action === "left")) { if (!sidebar) sidebar = true; else backRequested(); return }
        if (sidebar) {
            if (action === "up") manager.select(manager.selected - 1)
            else if (action === "down") manager.select(manager.selected + 1)
            else if ((action === "accept" || action === "right") && !repeated) {
                if (manager.hosts.length) { sidebar = false; row = 6 } else addHost()
            }
        } else {
            if (action === "up") row = Math.max(0, row - 1)
            else if (action === "down") row = Math.min(7, row + 1)
            else if (action === "accept" && !repeated) activate()
            else if (action === "right" && row === 3 && !repeated) activate()
        }
    }
    Ui.PageHeader {
        width: parent.width; title: "Moonlight 串流"; iconName: "monitor"; backVisible: true
        onBackRequested: view.backRequested()
        subtitle: view.manager.error || view.manager.status || (view.manager.hosts.length ? view.host.status || "" : "添加主机后开始连接")
        error: !!view.manager.error
    }
    Ui.ListView {
        id: hosts; y: Ui.Theme.contentY; width: Ui.Theme.sidebarWidth
        height: parent.height - y - Ui.Theme.buttonHeight - Ui.Theme.gap
        layer.enabled: true
        model: view.manager.hosts; currentIndex: view.manager.selected
        delegate: SettingRow {
            required property var modelData; required property int index
            width: hosts.rowWidth; title: modelData.name; description: modelData.status; iconName: "monitor"
            selected: hosts.currentIndex === index; focusOutline: false
            onFocused: { view.manager.select(index); view.sidebar = true }
            onActivated: { view.manager.select(index); view.sidebar = false; view.row = 6 }
        }
    }
    Ui.Button { id: add; anchors.bottom: parent.bottom; width: hosts.rowWidth; text: "添加主机"; iconName: "plus"; selected: view.sidebar && !view.manager.hosts.length; onClicked: view.addHost() }
    Ui.ListView {
        id: detailRows; objectName: "streamingRows"
        x: Ui.Theme.detailX; y: Ui.Theme.contentY; width: parent.width - x; height: parent.height - y
        layer.enabled: true
        visible: view.manager.hosts.length > 0
        model: 8; currentIndex: view.row
        delegate: SettingRow {
            required property int index
            width: detailRows.rowWidth
            title: ["主机名称", "地址", "应用", "画质", "性能信息", "配对", "开始串流", "从列表移除"][index]
            value: index === 0 ? view.host.name || "" : index === 1 ? view.host.address || "" : index === 2 ? view.host.application || ""
                : index === 3 ? view.presets[view.host.preset || 0] : index === 5 ? (view.host.paired ? "重新配对" : "开始配对") : ""
            choice: index === 2 || index === 3
            toggleState: index === 4 ? Number(!!view.host.overlay) : -1
            selected: !view.sidebar && view.row === index; focusOutline: false
            onFocused: { view.row = index; view.sidebar = false }
            onActivated: view.activate()
        }
    }
    Ui.FocusFrame {
        objectName: "streamingFocus"
        visible: view.sidebar ? !view.manager.hosts.length || view.selectionVisible(hosts) : view.selectionVisible(detailRows)
        x: view.sidebar ? 0 : Ui.Theme.detailX
        y: view.sidebar ? (hosts.currentItem ? hosts.y + hosts.currentItem.y - hosts.contentY : add.y)
            : detailRows.y + (detailRows.currentItem ? detailRows.currentItem.y - detailRows.contentY : 0)
        width: view.sidebar ? hosts.rowWidth : detailRows.rowWidth
        height: view.sidebar ? (hosts.currentItem ? hosts.currentItem.height : add.height) : Ui.Theme.rowHeight
        active: view.navigationActive && !view.manager.busy && !choices.visible
        reducedMotion: view.store.reducedMotion
    }
    Ui.ChoicePopup {
        id: choices; objectName: "streamingChoices"; parent: view; popupWidth: 550
        onActivated: function(index) {
            if (view.choiceKind === "preset") { if (view.manager.adjustPreset(index - view.host.preset)) close(); return }
            const count = view.manager.applications.length
            if (index < count) { if (view.manager.chooseApplication(index)) close() }
            else if (index === count) { close(); view.manager.refreshApplications() }
            else { close(); view.editRequested("application", "Sunshine 应用名称", view.host.application) }
        }
    }
    Connections {
        target: view.manager
        function onApplicationsReady() { if (view.visible && !view.sidebar && view.row === 2) view.chooseApplication() }
    }
    Rectangle {
        anchors.fill: parent; radius: Ui.Theme.radius; color: "#f0111a24"; visible: view.manager.busy
        MouseArea { anchors.fill: parent }
        Ui.Label { anchors.horizontalCenter: parent.horizontalCenter; y: 115; text: view.manager.pin ? "请在 Sunshine 中输入 PIN" : "正在读取应用列表…"; color: Ui.Theme.text; role: "title" }
        Ui.Label { anchors.horizontalCenter: parent.horizontalCenter; y: 175; text: view.manager.pin; color: Ui.Theme.accent; font.pixelSize: 64; font.letterSpacing: 12 }
        Ui.Label { anchors.horizontalCenter: parent.horizontalCenter; y: 290; text: "B 取消"; color: Ui.Theme.muted; role: "body" }
    }
}
