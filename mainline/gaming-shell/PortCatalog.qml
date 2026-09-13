pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Templates as T
import "controls" as Ui

Item {
    id: view
    required property var tools
    property bool navigationActive: true
    property bool sidebar: true
    property int selected: 0
    property int row: 0
    property int offset: 0
    property string query: ""
    property bool installedOnly: false
    property string requestedId: ""
    property string pendingAction: ""
    property bool reloadDetail: false
    readonly property var entries: tools.catalogInfo.ports || []
    readonly property var detail: tools.catalogDetail.id === requestedId ? tools.catalogDetail : ({})
    readonly property bool choiceOpen: choices.visible || readme.visible
    readonly property var hints: readme.visible ? [["↑↓", "滚动"], ["B", "返回"]] : choices.visible ? choices.hints : tools.busy ? [["B", "取消"]]
        : sidebar ? [["↑↓", "游戏"], ["A", "详情"], ["X", "搜索"], ["Y", installedOnly ? "全部" : "已安装"], ["START", "刷新"], ["L1 / R1", "翻页"], ["B", "返回"]]
        : [["↑↓", "项目"], ["A", "操作"], ["← / B", "游戏列表"]]
    readonly property var rows: [
        {title: detail.installed ? (detail.updateAvailable ? "更新游戏" : "重新安装") : "安装游戏", key: "install", enabled: !!detail.compatible, value: detail.bytes ? (detail.bytes / 1048576).toFixed(1) + " MiB" : ""},
        {title: "回退上一版本", key: "rollback", enabled: !!detail.rollbackAvailable, value: ""},
        {title: "卸载游戏", key: "uninstall", enabled: !!detail.installed, value: "保留存档"},
        {title: "运行库", enabled: false, value: (detail.runtime || []).join(" · ") || "无需额外运行库"},
        {title: "安装说明", key: "instructions", enabled: !!detail.instructions, value: "查看"}
    ]
    signal backRequested()
    signal searchRequested(string value)
    function load() { return tools.catalog(query, offset, installedOnly) }
    function search(value) { query = value; offset = 0; selected = 0; sidebar = true; return load() }
    function filter() { installedOnly = !installedOnly; offset = 0; selected = 0; sidebar = true; load() }
    function openDetail() {
        if (!entries[selected]) return
        requestedId = entries[selected].id; row = 0; sidebar = false
        tools.catalogAction("details", requestedId)
    }
    function back() { if (tools.busy) tools.cancel(); else backRequested() }
    function activate() {
        const entry = rows[row]
        if (!entry || !entry.enabled || tools.busy || !detail.id) return
        if (entry.key === "instructions") { readme.open(); return }
        pendingAction = entry.key
        choices.present(details.currentItem, ["取消", entry.key === "uninstall" ? "卸载" : entry.key === "rollback" ? "回退" : "安装"], 0,
                        entry.key === "uninstall" ? "卸载游戏，存档保留" : entry.key === "rollback" ? "恢复上一版本" : "安装到管理目录")
    }
    function dispatch(action, repeated) {
        if (readme.visible) {
            if (action === "back" || action === "quick") readme.close()
            else if (action === "up" || action === "down") prose.contentY = Math.max(0, Math.min(prose.contentHeight - prose.height, prose.contentY + (action === "down" ? 60 : -60)))
            return true
        }
        if (choices.dispatch(action, repeated)) return true
        if (tools.busy) { if (action === "back") tools.cancel(); return true }
        if (action === "back" || (!sidebar && action === "left")) { if (sidebar) backRequested(); else sidebar = true; return true }
        if (sidebar) {
            if (action === "favorite" && !repeated) searchRequested(query)
            else if (action === "erase" && !repeated) filter()
            else if (action === "submit" && !repeated) tools.catalogAction("refresh")
            else if (action === "up") selected = Math.max(0, selected - 1)
            else if (action === "down") selected = Math.min(entries.length - 1, selected + 1)
            else if (action === "accept" || action === "right") openDetail()
            else if (action === "previousTab" || action === "nextTab") {
                const next = Math.max(0, offset + (action === "nextTab" ? 50 : -50))
                if (next !== offset && next < Number(tools.catalogInfo.total || 0)) { offset = next; selected = 0; load() }
            }
        } else {
            if (action === "up") row = Math.max(0, row - 1)
            else if (action === "down") row = Math.min(rows.length - 1, row + 1)
            else if (action === "accept" && !repeated) activate()
        }
        return true
    }
    Component.onCompleted: load()
    Ui.PageHeader {
        width: parent.width; title: "PortMaster 目录"; iconName: "ports"; backVisible: true
        actionText: view.installedOnly ? "全部游戏" : "已安装"; onActionRequested: view.filter(); onBackRequested: view.back()
        subtitle: view.tools.error || (view.tools.busy ? "正在处理…" : (view.query ? view.query + " · " : "") + String(view.tools.catalogInfo.total || 0) + " 项")
        error: !!view.tools.error; busy: view.tools.busy; progress: view.tools.progress
    }
    Ui.ListView {
        id: games; objectName: "catalogGames"; y: Ui.Theme.contentY; width: Ui.Theme.sidebarWidth; height: parent.height - y
        model: view.entries; currentIndex: view.selected
        delegate: SettingRow {
            required property var modelData; required property int index
            width: games.rowWidth; title: modelData.title; description: modelData.installed ? "已安装" : ""
            selected: view.selected === index; focusOutline: false
            onFocused: { view.selected = index; view.sidebar = true }
            onActivated: { view.selected = index; view.openDetail() }
        }
    }
    Item {
        id: info; x: Ui.Theme.detailX; y: Ui.Theme.contentY; width: parent.width - x; height: parent.height - y
        visible: !!view.detail.id
        Column {
            id: introduction; width: parent.width; spacing: Ui.Theme.gap
            Ui.Label { width: parent.width; role: "section"; wrapMode: Text.Wrap; maximumLineCount: 2; text: view.detail.title || "" }
            Ui.Label { width: parent.width; role: "caption"; wrapMode: Text.Wrap; maximumLineCount: 2; text: view.detail.description || ""; visible: text !== "" }
        }
        Ui.ListView {
            id: details; objectName: "catalogRows"; y: introduction.height + Ui.Theme.padding; width: parent.width; height: parent.height - y - status.implicitHeight - Ui.Theme.gap
            currentIndex: view.row; model: view.rows
            delegate: SettingRow {
                required property var modelData; required property int index
                width: details.rowWidth; title: modelData.title; value: modelData.value
                selected: !view.sidebar && view.row === index; focusOutline: false; actionable: modelData.enabled && !view.tools.busy
                onFocused: { view.sidebar = false; view.row = index }
                onActivated: view.activate()
            }
        }
        Ui.Label { id: status; anchors.bottom: parent.bottom; width: parent.width; role: "caption"; text: !view.detail.compatible ? "尚未确认此游戏的运行条件" : view.detail.installed ? "启动适配尚未完成" : view.detail.readyToRun ? "包含游戏数据" : "需要自行提供原版游戏数据" }
    }
    Ui.Label { x: Ui.Theme.detailX; y: Ui.Theme.contentY; width: parent.width - x; visible: !view.detail.id; role: "caption"; text: view.entries.length ? "选择游戏查看详情" : "START 刷新目录 · X 搜索游戏" }
    Item {
        y: Ui.Theme.contentY; width: parent.width; height: parent.height - y; clip: true
        Ui.FocusFrame {
            x: view.sidebar ? 0 : Ui.Theme.detailX
            y: view.sidebar ? (games.currentItem ? games.currentItem.y - games.contentY : 0) : details.y + (details.currentItem ? details.currentItem.y - details.contentY : 0)
            width: view.sidebar ? games.rowWidth : details.rowWidth
            height: view.sidebar && games.currentItem ? games.currentItem.height : Ui.Theme.rowHeight
            active: view.navigationActive && !view.tools.busy && !view.choiceOpen
            visible: view.sidebar ? view.entries.length > 0 : !!view.detail.id
        }
    }
    Ui.ChoicePopup {
        id: choices; parent: view
        onActivated: function(index) { close(); if (index === 1) view.tools.catalogAction(view.pendingAction, view.requestedId) }
    }
    T.Popup {
        id: readme; parent: view; popupType: T.Popup.Item; modal: true; focus: true
        width: Math.min(760, view.width); height: view.height; x: (view.width - width) / 2
        enter: Transition { Ui.Motion { property: "opacity"; from: 0; to: 1; duration: Ui.Theme.reducedMotion ? 0 : Ui.Theme.popupDuration } }
        padding: Ui.Theme.padding; closePolicy: T.Popup.CloseOnEscape | T.Popup.CloseOnPressOutside
        background: Rectangle { radius: Ui.Theme.radius; color: Ui.Theme.background; border.color: Ui.Theme.outline }
        onOpened: { prose.contentY = 0; contentItem.forceActiveFocus() }
        contentItem: FocusScope {
            Keys.onPressed: function(event) {
                event.accepted = true
                if (event.key === Qt.Key_Escape || event.key === Qt.Key_Backspace) readme.close()
                else if (event.key === Qt.Key_Up || event.key === Qt.Key_Down) view.dispatch(event.key === Qt.Key_Up ? "up" : "down", event.isAutoRepeat)
            }
            Ui.PageHeader { width: parent.width; title: "安装说明"; backVisible: true; onBackRequested: readme.close() }
            Flickable {
                id: prose; y: Ui.Theme.contentY; width: parent.width; height: parent.height - y; clip: true
                contentWidth: width; contentHeight: text.implicitHeight; boundsBehavior: Flickable.StopAtBounds
                Ui.Label { id: text; width: parent.width - Ui.Theme.scrollGutter; wrapMode: Text.Wrap; text: view.detail.instructions || "" }
                T.ScrollBar.vertical: Ui.ScrollBar {}
            }
        }
    }
    Connections {
        target: view.tools
        function onCatalogFinished(operation) {
            if (["install", "uninstall", "rollback"].includes(operation)) { view.reloadDetail = true; view.load() }
            else if (operation === "catalog" && view.reloadDetail) {
                view.reloadDetail = false
                if (view.entries.some(function(entry) { return entry.id === view.requestedId })) view.tools.catalogAction("details", view.requestedId)
                else { view.sidebar = true; view.selected = 0; view.requestedId = "" }
            } else if (operation === "refresh") { view.offset = 0; view.selected = 0; view.load() }
        }
    }
}
