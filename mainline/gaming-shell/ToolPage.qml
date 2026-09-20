pragma ComponentBehavior: Bound
import QtQuick
import "controls" as Ui

Item {
    id: view
    required property var tools
    required property string kind
    property bool restoredSelection: false
    onEntriesChanged: {
        if (kind === "ports" && entries.length && !restoredSelection) {
            const previous = entries.findIndex(function(entry) { return entry.id === tools.lastGame })
            if (previous >= 0) selected = previous
            restoredSelection = true
        }
    }
    property int selected: 0
    property string openedId: ""
    property int row: 0
    property bool sidebar: kind !== "usb"
    property bool navigationActive: true
    property bool catalogOpen: false
    readonly property int catalogIndex: catalogPage.item ? catalogPage.item.selected : 0
    readonly property bool catalogSidebar: !catalogPage.item || catalogPage.item.sidebar
    readonly property bool choiceOpen: choices.visible || (catalogPage.item !== null && catalogPage.item.choiceOpen)
    readonly property var facts: tools.info.kind === kind ? tools.info : ({})
    readonly property var entries: kind === "ports" ? facts.ports || [] : [{id: "mslug", title: "合金弹头", status: facts.status || "等待资源检查"}]
    readonly property var current: entries.find(function(entry) { return entry.id === openedId }) || ({})
    readonly property bool detailReady: (kind === "usb" || !sidebar) && detailLoader.status === Loader.Ready
    readonly property string heading: kind === "neo" ? "Neo 模拟器管理" : kind === "ports" ? "PortMaster 管理" : "USB 手柄配置"
    readonly property var localHints: choices.visible ? choices.hints : sidebar
        ? [["↑↓", "选择游戏"], ["A / ↵", "进入"], ["B / Esc", "返回"]]
        : !detailReady ? [["← / B", "返回游戏列表"]]
        : [["↑↓", "选择项目"]].concat(rows[row] && rows[row].enabled && !tools.busy ? [["A / ↵", "操作"]] : []).concat([[kind === "usb" ? "B / Esc" : "← / B", kind === "usb" ? "返回" : "游戏列表"]])
    readonly property var hints: catalogOpen && catalogPage.item ? catalogPage.item.hints : localHints.concat(kind === "ports" && tools.catalogAvailable && !choices.visible ? [["X", "游戏目录"]] : [])
    signal backRequested()
    signal searchRequested(string value)
    function search(value) { return catalogPage.item && catalogPage.item.search(value) }
    function openCatalog() { if (!tools.busy && tools.catalogAvailable) catalogOpen = true }
    function detailList() { return detailLoader.item ? detailLoader.item.rowsView : null }
    function openSelected() {
        if (!entries[selected]) return
        openedId = entries[selected].id; row = 0; sidebar = false
    }
    function returnToList() { sidebar = true; row = 0 }
    readonly property var rows: {
        if (kind === "neo") return [
            {title: "开始游戏", key: "play", value: tools.nativeEnabled ? "启动" : "暂不可用", enabled: tools.nativeEnabled && !!facts.neoVerified},
            {title: "检查资源", key: "verify", value: "校验", enabled: true},
            {title: "整数缩放", key: "neoIntegerScale", toggle: true, enabled: true},
            {title: "平滑显示", key: "neoSmooth", toggle: true, enabled: true},
            {title: "存档文件", value: String(facts.saveFiles || 0) + " 个", enabled: false},
            {title: "备份存档", key: "backup", value: "备份", enabled: (facts.saveFiles || 0) > 0}
        ]
        if (kind === "ports") return [
            {title: "开始游戏", key: "playPort", value: current.id === "gtasa" ? "适配中" : "", enabled: tools.portsEnabled && !!current.dataPresent && current.id !== "gtasa"},
            {title: "资源", value: current.dataPresent ? "已找到" : "缺少文件", enabled: false},
            {title: "运行库", value: current.runtimeStatus || "待检查", enabled: false},
            {title: "原存档", value: String(current.originalSaves || 0) + " 个", enabled: false},
            {title: "导入原存档", key: "import", value: "建立副本", enabled: (current.originalSaves || 0) > 0 && !(current.managedSaves > 0)},
            {title: "管理的存档", value: String(current.managedSaves || 0) + " 个", enabled: false},
            {title: "备份存档", key: "backup", value: "备份", enabled: (current.managedSaves || 0) > 0},
            {title: "刷新资源", key: "refresh", value: "检查", enabled: true}
        ]
        return [
            {title: "USB 手柄模式", key: "usbEnabled", toggle: true, enabled: false},
            {title: "交换 A / B", key: "usbSwapAB", toggle: true, enabled: true},
            {title: "交换 X / Y", key: "usbSwapXY", toggle: true, enabled: true},
            {title: "反转右摇杆 Y", key: "usbInvertRightY", toggle: true, enabled: true},
            {title: "摇杆死区", key: "usbDeadzone", value: String(tools.settings.usbDeadzone) + "%", choice: true, enabled: true},
            {title: "导出测试配置", key: "export", value: "导出", enabled: true},
            {title: "检查连接能力", key: "refresh", value: "检查", enabled: true}
        ]
    }
    function activate() {
        if (!detailReady || tools.busy || !rows[row] || !rows[row].enabled) return
        const entry = rows[row]
        if (entry.toggle) tools.choose(entry.key, !tools.settings[entry.key])
        else if (entry.key === "usbDeadzone") choices.present(detailList().currentItem, ["0%", "5%", "10%", "15%", "20%", "25%", "30%"], tools.settings.usbDeadzone / 5, "摇杆死区")
        else if (entry.key === "play") tools.requestNative()
        else if (entry.key === "playPort") tools.requestPort(current.id)
        else if (entry.key === "verify") tools.action("verify", "neo")
        else if (entry.key === "refresh") tools.inspect(kind)
        else tools.action(entry.key, entry.key === "export" ? "usb" : current.id)
    }
    function dispatch(action, repeated) {
        if (catalogOpen && catalogPage.item) return catalogPage.item.dispatch(action, repeated)
        if (kind === "ports" && action === "favorite" && !repeated) { openCatalog(); return true }
        if (choices.dispatch(action, repeated)) return true
        if (action === "back" || (!sidebar && action === "left")) {
            if (sidebar || kind === "usb") return false
            returnToList(); return true
        }
        if (tools.busy) return true
        if (!sidebar && !detailReady) return true
        if (sidebar) {
            if (action === "up") selected = Math.max(0, selected - 1)
            else if (action === "down") selected = Math.min(entries.length - 1, selected + 1)
            else if ((action === "accept" || action === "right") && entries.length) openSelected()
        } else {
            if (action === "up") row = Math.max(0, row - 1)
            else if (action === "down") row = Math.min(rows.length - 1, row + 1)
            else if (action === "accept" && !repeated) activate()
        }
        return true
    }
    onKindChanged: { catalogOpen = false; selected = 0; openedId = ""; row = 0; sidebar = kind !== "usb" }
    Item {
        anchors.fill: parent; visible: !view.catalogOpen
        Ui.PageHeader {
            width: parent.width
            title: view.sidebar || view.kind === "usb" ? view.heading : view.current.title || view.heading
            actionText: view.sidebar && view.kind === "ports" && view.tools.catalogAvailable ? "游戏目录" : ""
            onActionRequested: view.openCatalog()
            iconName: view.kind === "neo" ? "cartridge" : view.kind === "ports" ? "ports" : "usb"
            backVisible: true
            onBackRequested: if (!view.sidebar && view.kind !== "usb") view.returnToList(); else view.backRequested()
            subtitle: view.tools.error || (view.tools.busy ? "正在处理…" : view.sidebar ? "选择游戏" : view.kind === "usb" ? view.facts.status || "USB 输出尚未启用" : view.current.status || "")
            error: !!view.tools.error
            busy: view.tools.busy
        }
        Ui.ListView {
            id: games; objectName: "toolGames"
            y: Ui.Theme.contentY; width: Ui.Theme.sidebarWidth * 2; height: parent.height - y
            visible: view.sidebar && view.kind !== "usb"; model: view.entries; currentIndex: view.selected
            delegate: SettingRow {
                required property var modelData; required property int index
                width: games.rowWidth; title: modelData.title
                iconName: view.kind === "neo" ? "cartridge" : modelData.id === "stardew" ? "leaf" : "car"
                selected: view.selected === index; focusOutline: false
                onFocused: view.selected = index
                onActivated: { view.selected = index; view.openSelected() }
            }
        }
        Ui.FocusFrame {
            x: 0
            y: games.y + (games.currentItem ? games.currentItem.y - games.contentY : 0)
            width: games.rowWidth
            height: games.currentItem ? games.currentItem.height : Ui.Theme.rowHeight
            active: view.navigationActive && view.sidebar && !choices.visible && !view.tools.busy
            visible: view.sidebar && view.entries.length > 0
        }
        Loader {
            id: detailLoader; anchors.fill: parent
            active: view.kind === "usb" || !view.sidebar
            visible: status === Loader.Ready; asynchronous: true
            sourceComponent: detailComponent
        }
        Component {
            id: detailComponent
            Item {
                property alias rowsView: details
                Ui.ListView {
                    id: details; objectName: "toolRows"
                    y: Ui.Theme.contentY; width: parent.width; height: parent.height - y
                    model: view.rows; currentIndex: view.row
                    delegate: SettingRow {
                        required property var modelData; required property int index
                        width: details.rowWidth; title: modelData.title; value: modelData.value || ""
                        selected: view.row === index; focusOutline: false
                        actionable: !!modelData.enabled && !view.tools.busy
                        choice: !!modelData.choice
                        toggleState: modelData.toggle ? Number(!!view.tools.settings[modelData.key]) : -1
                        onFocused: view.row = index
                        onActivated: { view.row = index; view.activate() }
                    }
                }
                Ui.FocusFrame {
                    x: 0
                    y: details.y + (details.currentItem ? details.currentItem.y - details.contentY : 0)
                    width: details.rowWidth
                    height: details.currentItem ? details.currentItem.height : Ui.Theme.rowHeight
                    active: view.navigationActive && view.detailReady && !choices.visible && !view.tools.busy
                }
            }
        }
    }
    Ui.ChoicePopup {
        id: choices; parent: view; objectName: "toolChoices"
        onActivated: function(index) { if (view.tools.choose("usbDeadzone", index * 5)) close() }
    }
    Loader {
        id: catalogPage; anchors.fill: parent; active: view.catalogOpen; visible: active
        sourceComponent: PortCatalog {
            tools: view.tools; navigationActive: view.navigationActive
            onBackRequested: view.catalogOpen = false
            onSearchRequested: function(value) { view.searchRequested(value) }
        }
    }

}
