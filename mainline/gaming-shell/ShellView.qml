pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Window
import QtQuick.Templates as T
import "controls" as Ui

Item {
    id: root
    required property var store
    required property var metrics
    required property var controller
    property var applications: null
    property var streaming: null
    property var device: null
    property var network: null
    property var tools: null
    property bool sharedDisplay: false
    property bool sharedReady: true
    property bool browserAvailable: false
    property var browserVersions: ({})
    signal browserRequested()
    property bool terminalAvailable: false
    signal terminalRequested()
    property bool filesAvailable: false
    signal filesRequested(bool editor)
    signal transferRequested()
    signal backgroundRequested(bool tasks)
    property bool tasksVisible: false
    property int taskHoldPercent: 0
    readonly property int taskCount: applications ? applications.tasks.length : 0
    readonly property int taskPreviewCount: applications ? applications.tasks.filter(function(task){return !!task.preview}).length : 0
    function closeSelectedTask() { if(tasksVisible && taskPage.item)taskPage.item.closeSelected() }
    function showTasksOrDesktop(tasks) {
        quickOpen=false;gameExitChoice.close();tasksVisible=tasks
        if(!tasks) { if(editing)closeEditor();showScene("home") }
        root.forceActiveFocus()
    }
    readonly property bool gameOverlay: sharedDisplay && externalSession
    readonly property bool panelVisible: quickOpen || quickPanel.x < 1024
    readonly property bool monitorVisible: store.monitor
    property bool volumeVisible: false
    property int volumePercent: 0
    property string toolRoute: ""
    readonly property bool toolOpen: toolRoute !== ""
    readonly property bool toolBusy: tools !== null && tools.busy
    readonly property bool toolSaveError: tools !== null && tools.dirty && tools.error.length > 0
    readonly property int toolIndex: toolView.item ? toolView.item.selected : 0
    readonly property int toolRow: toolView.item ? toolView.item.row : 0
    readonly property bool toolDetailReady: toolView.item !== null && toolView.item.detailReady
    readonly property bool hardware: device !== null && device.target
    property bool streamingOpen: false
    readonly property bool streamingBusy: streaming !== null && streaming.busy
    property bool testInputCapture: false
    readonly property bool testInputVisible: editing && testInputCapture && editPurpose === "test"
    readonly property bool portCatalogOpen: toolView.item !== null && toolView.item.catalogOpen
    readonly property int portCatalogTotal: tools ? Number(tools.catalogInfo.total || 0) : 0
    readonly property bool remoteTextAllowed: editing && !quickOpen && !choicesOpen && !dimmed && !screenOff && !externalSession && (editPurpose === "portSearch" || testInputVisible)
    readonly property int portCatalogIndex: toolView.item ? toolView.item.catalogIndex : 0
    readonly property bool portCatalogSidebar: !toolView.item || toolView.item.catalogSidebar
    readonly property bool sensitiveVisible: tasksVisible || (externalSession && ["builtin.browser", "builtin.terminal", "builtin.files", "builtin.text", "builtin.transfer"].includes(activeApplication)) || (editing && !testInputVisible) || (streaming !== null && streaming.pin.length > 0)
    property string editPurpose: "test"
    property string editLabel: "文字输入测试"
    readonly property bool externalSession: applications !== null && applications.running
    readonly property bool customApplications: applications !== null && applications.hasManifest
    readonly property string activeApplication: applications ? applications.activeId : ""
    readonly property bool applicationError: applications !== null && applications.error.length > 0
    readonly property int applicationExitCode: applications ? applications.exitCode : 0
    readonly property string selectedApplication: (applications || tools) && games[selected] ? (games[selected].id || "") : ""
    readonly property bool selectedFavorite: games[selected] ? ((applications || tools) ? store.applicationFavorites.indexOf(games[selected].id) >= 0 : store.favorites.indexOf(selected) >= 0) : false
    property bool keyboardEnabled: false
    readonly property bool keyboardReady: virtualKeyboard.status === Loader.Ready
    readonly property var inputMethod: Qt.inputMethod
    property bool editing: false
    property bool dimmed: false
    property bool screenOff: false
    readonly property bool idleEligible: (!hardware || device.controls) && !session && !externalSession && !streamingBusy && !editing && !testingController && !choicesOpen
    readonly property string powerScene: screenOff ? "off" : externalSession ? "game" : "desktop"
    property bool windowVisible: true
    readonly property real fontScale: store.fontPercent / 100
    readonly property bool motionReduced: store.reducedMotion
    readonly property bool choicesOpen: gameExitChoice.visible || settingsView.choiceOpen || (streamingView.item !== null && streamingView.item.choiceOpen) || (toolView.item !== null && toolView.item.choiceOpen)
    Binding { target: Ui.Theme; property: "fontScale"; value: root.fontScale }
    Binding { target: Ui.Theme; property: "reducedMotion"; value: root.motionReduced }
    Binding { target: root.Window.window; property: "color"; value: root.gameOverlay ? "transparent" : Ui.Theme.background; when: root.Window.window !== null }
    // Native popup items live in the window overlay, outside the scaled canvas.
    Binding { target: root.T.Overlay.overlay; property: "scale"; value: canvas.scale; when: root.T.Overlay.overlay !== null }
    Binding { target: root.T.Overlay.overlay; property: "transformOrigin"; value: Item.TopLeft; when: root.T.Overlay.overlay !== null }
    property alias settingsCategory: settingsView.category
    property alias settingsSidebar: settingsView.sidebar
    property alias settingsAdjusting: settingsView.adjustingValue
    readonly property bool settingsDetailReady: settingsView.detailReady
    property alias testingController: settingsView.tester
    width: 1024; height: 768; focus: true
    property int page: 0
    property int selected: 0
    property alias settingsIndex: settingsView.rowIndex
    property bool tabsFocused: false
    property bool quickOpen: false
    property int quickIndex: 0
    property bool session: false
    property int sessionMoves: 0
    property real avatarX: 480
    property real avatarY: 350
    property string notice: ""
    property var now: new Date()
    readonly property string clockText: Qt.formatTime(now, "hh:mm")
    // "auto" follows local time: night from 19:00 until 07:00.
    readonly property int clockMinutes: now.getHours() * 60 + now.getMinutes()
    readonly property bool nightActive: store.nightMode === "on" || (store.nightMode === "auto" && (clockMinutes >= 19 * 60 || clockMinutes < 7 * 60))
    function applyTheme() {
        themeFade.stop()
        if (Ui.Theme.night === nightActive || motionReduced || !windowVisible || !visible) {
            themeSnapshot.visible = false; themeSnapshot.sourceItem = null
            Ui.Theme.night = nightActive; return
        }
        // Capture one frame of the old palette; scheduledUpdateCompleted switches and fades it out.
        themeSnapshot.opacity = 1; themeSnapshot.sourceItem = canvas; themeSnapshot.visible = true
        themeSnapshot.scheduleUpdate()
    }
    onNightActiveChanged: applyTheme()
    function boundedPercent(value) {
        const number = Number(value)
        return Number.isFinite(number) && number >= 0 && number <= 100 ? Math.round(number) : -1
    }
    readonly property int batteryPercent: hardware ? boundedPercent(device.info.capacity) : -1
    readonly property int liveWifiSignal: network !== null ? boundedPercent(network.signal) : -1
    readonly property int wifiSignal: hardware ? (liveWifiSignal >= 0 ? liveWifiSignal : boundedPercent(device.info.wifiSignal)) : -1
    readonly property string batteryState: hardware ? String(device.info.batteryStatus || "").toLowerCase() : ""
    readonly property var controlHints: quickOpen
        ? [["↑↓", "选择"], [quickIndex < 2 ? "←→" : "A / ↵", quickIndex < 2 ? "调整" : quickIndex < 4 ? "切换" : "确定"], ["B / Esc", "关闭面板"]]
        : toolOpen && toolView.item ? toolView.item.hints
        : streamingOpen ? streamingView.hints
        : testingController ? [["方向 / A B", "测试输入"], ["Select / Q", "返回设置"]]
        : session ? [["方向", "移动"], ["B / Esc", "结束演示"], ["Select / Q", "快捷面板"]]
        : tabsFocused ? [["←→", "切换页面"], ["A / ↵", "进入"], ["Select / Q", "快捷面板"]]
        : page === 2 ? (settingsView.choiceOpen ? settingsView.hints : settingsView.hints.concat([["L1 / R1", "切页"], ["Select / Q", "快捷面板"]]))
        : games.length === 0 ? [["L1 / R1", "切页"], ["Select / Q", "快捷面板"]]
        : [["A / ↵", customApplications ? "启动" : tools ? "打开" : streaming && selected === 0 ? "主机管理" : "打开演示"], ["B / Esc", page === 0 ? "顶部导航" : "主页"], ["X", "收藏"], ["L1 / R1", "切页"], ["Select / Q", "快捷面板"]]
    readonly property var games: customApplications ? applications.items.concat(builtinGames.filter(function(entry) {
        return (["files", "text", "transfer"].includes(entry.route) && root.filesAvailable) || (entry.route === "terminal" && root.terminalAvailable)
    })) : tools ? builtinGames : demoGames
    readonly property var builtinGames: [
        {id: "builtin.moonlight", title: "Moonlight", detail: "电脑游戏串流", palette: 2, route: "streaming", icon: "monitor"},
        {id: "builtin.neo", title: "Neo 模拟器", detail: "Neo Geo 游戏与配置", palette: 0, route: "neo", icon: "cartridge"},
        {id: "builtin.ports", title: "PortMaster", detail: "移植游戏与存档", palette: 1, route: "ports", icon: "ports"},
        {id: "builtin.usb", title: "USB 手柄", detail: "手柄映射与配置", palette: 4, route: "usb", icon: "usb"},
        {id: "builtin.controller", title: "摇杆测试", detail: "查看按键与摇杆", palette: 3, route: "controller", icon: "gamepad"},
        {id: "builtin.settings", title: "设置", detail: "设备与界面", palette: 1, route: "settings", icon: "settings"},
        {id: "builtin.browser", title: "Jume Browser", detail: browserAvailable ? "Chromium 掌机浏览器 · 开发预览" : "浏览器运行时尚未安装", palette: 2, route: "browser", icon: "monitor"},
        {id: "builtin.terminal", title: "终端", detail: terminalAvailable ? "Bash · 请连接 USB 键盘" : "终端运行时尚未安装", palette: 4, route: "terminal", icon: "terminal"},
        {id: "builtin.files", title: "文件管理器", detail: filesAvailable ? "分区 · U 盘 · 文件预览" : "文件运行时尚未安装", palette: 4, route: "files", icon: "folder"},
        {id: "builtin.text", title: "文本编辑器", detail: filesAvailable ? "UTF-8 · 原子保存 · USB 键盘" : "文件运行时尚未安装", palette: 1, route: "text", icon: "document"},
        {id: "builtin.transfer", title: "文件传输", detail: filesAvailable ? "Wi-Fi · 扫码上传与下载" : "文件运行时尚未安装", palette: 1, route: "transfer", icon: "folder"}
    ]
    function openTool(kind) {
        if (!tools || !["neo", "ports", "usb"].includes(kind) || !tools.save()) return
        streamingOpen = false; session = false; toolRoute = kind; clearNotice(); tools.inspect(kind)
    }
    function closeTool() { if (tools && !tools.save()) return false; toolRoute = ""; clearNotice(); root.forceActiveFocus(); return true }
    readonly property var demoGames: [
        {title: "Moonlight", detail: "电脑游戏串流", palette: 2},
        {title: "像素远征", detail: "街机 · 示例游戏", palette: 0},
        {title: "夜航", detail: "Game Gear · 示例游戏", palette: 1},
        {title: "方块花园", detail: "Game Boy · 示例游戏", palette: 4},
        {title: "星际快线", detail: "街机 · 示例游戏", palette: 3},
        {title: "海岛来信", detail: "掌机 · 示例游戏", palette: 1}
    ]
    function showScene(name) {
        toolRoute = ""
        if (["neo", "ports", "usb"].includes(name)) {
            if (tools && !customApplications) {
                const entry = games.findIndex(function(game) { return game.route === name })
                if (entry >= 0) { page = entry < 3 ? 0 : 1; selected = entry }
            }
            openTool(name); return
        }
        streamingOpen = name === "streaming"
        if (streamingOpen && streaming) streaming.refresh()
        page = name === "library" ? 1 : (["settings", "about", "controller", "power", "input"].indexOf(name) >= 0 ? 2 : 0)
        session = name === "session"
        quickOpen = name === "quick"
        if (page === 2) settingsView.enter()
        if (name === "about") settingsView.openCategory(11)
        if (name === "performance" && !store.monitor) store.adjust("monitor", 1)
        if (name === "controller") settingsView.openCategory(2)
        if (name === "power") settingsView.openCategory(7)
        if (name === "input") { settingsView.openCategory(8); openEditor() }
    }
    function changePage(value) {
        if (externalSession || choicesOpen) return
        if (tools && !tools.save()) return
        toolRoute = ""
        if (page === 2 && !store.save()) return
        clearNotice()
        page = Math.max(0, Math.min(2, value)); selected = 0; tabsFocused = false
        settingsView.enter()
        root.forceActiveFocus()
    }
    function notify(text) { notice = text; noticeTimer.restart() }
    function clearNotice() { notice = ""; noticeTimer.stop() }
    function leaveQuick() {
        if (!store.save()) return false
        quickOpen = false; return true
    }
    function activity() {
        const wasDimmed = dimmed || screenOff
        if (screenOff) {
            if (hardware && device.controls && !device.setScreenOff(false)) { notify(device.error); return true }
            screenOff = false
        }
        if (wasDimmed && hardware && device.controls && !device.setDimmed(false)) { notify(device.error); return true }
        dimmed = false
        if (store.dimSeconds > 0 && idleEligible) idleTimer.restart()
        else idleTimer.stop()
        if (store.screenOffSeconds > 0 && idleEligible) offTimer.restart()
        else offTimer.stop()
        return wasDimmed
    }
    function blankScreen() {
        if (!idleEligible || screenOff) return false
        if (hardware && !device.setScreenOff(true)) { notify(device.error); return false }
        screenOff = true; dimmed = false
        return true
    }
    onPowerSceneChanged: if (hardware && device.controls && !device.setPowerScene(powerScene)) notify(device.error)
    Component.onCompleted: {
        Ui.Theme.night = nightActive
        if (hardware && device.controls && !device.setPowerScene(powerScene)) notify(device.error)
    }
    function openEditor() { openTextEditor("文字输入测试", "", "test") }
    function openTextEditor(label, value, purpose) {
        editPurpose = purpose || "test"; editLabel = label || "文字输入测试"
        editing = true; inputField.text = value || ""; inputField.forceActiveFocus()
        inputMethod.show()
    }
    function remoteText(value) {
        if (!remoteTextAllowed || typeof value !== "string" || value.length > Math.min(80, inputField.maximumLength) || /[\x00-\x1f\x7f]/.test(value)) return false
        inputMethod.reset(); inputField.text = value; inputField.cursorPosition = value.length
        return true
    }
    function finishEditor() {
        inputMethod.commit()
        const value = inputField.text; const purpose = editPurpose
        if (purpose === "portSearch") {
            if (!toolView.item || !toolView.item.search(value)) return
        } else if (purpose === "wifiPassword") {
            if (!network || !network.connectSelected(value)) return
        } else if (purpose !== "test" && streaming) {
            if (purpose === "add" ? !streaming.addHost(value) : !streaming.edit(purpose, value)) return
        }
        closeEditor()
    }
    function closeEditor() {
        inputMethod.hide(); editing = false; inputField.text = ""; root.forceActiveFocus()
    }
    Connections {
        target: root.device
        function onVolumeChanged(percent) {
            root.volumePercent = percent
            root.volumeVisible = true
            volumeTimer.restart()
            root.activity()
        }
    }
    Connections {
        target: root.inputMethod
        function onVisibleChanged() {
            if (root.keyboardEnabled && root.editing && !root.inputMethod.visible) {
                // Finish the key callback before unloading its keyboard component.
                Qt.callLater(function() {
                    if (root.editing && !root.inputMethod.visible) root.closeEditor()
                })
            }
        }
    }
    function adjustSetting(index, direction, repeated) {
        if (index >= 2 && repeated) return
        if (hardware && index < 2) {
            if (index === 0) { notify("请使用机身音量键"); return }
            if (!device.setBrightness(Math.max(10,Math.min(100,device.info.brightnessPercent + direction * 5)))) notify(device.error)
            return
        }
        store.adjust(["volume", "brightness", "motion", "monitor"][index], index < 2 ? direction * 5 : 1)
    }
    function activateSelected() {
        if (!sharedReady) return
        if (!games[selected]) return
        if (tools && games[selected].route) {
            const route = games[selected].route
            if (["files", "text", "transfer"].includes(route)) {
                if (!filesAvailable) { notify("请先安装 Jume Files 运行时"); return }
                if (route === "transfer") transferRequested()
                else filesRequested(route === "text")
                return
            }
            if (route === "terminal") {
                if (!terminalAvailable) { notify("请先安装终端运行时"); return }
                terminalRequested(); return
            }
            if (route === "browser") {
                if (!browserAvailable) { notify("请先安装 Jume Browser 预览运行时"); return }
                browserRequested(); return
            }
            if (["neo", "ports", "usb"].includes(route)) openTool(route)
            else showScene(route)
            return
        }
        if (streaming && !customApplications && selected === 0) { streamingOpen = true; streaming.refresh(); clearNotice(); return }
        if (customApplications) { if (store.save()) { clearNotice(); applications.launch(selected) }; return }
        session = true; tabsFocused = false; sessionMoves = 0; avatarX = 480; avatarY = 350
        notify(selected === 0 ? "串流演示 · 尚未连接电脑" : "交互演示 · 未启动模拟器")
    }
    function dispatch(action, repeated) {
        if (screenOff) { activity(); return }
        if(tasksVisible && taskPage.item) { if (!activity()) taskPage.item.dispatch(action,repeated);return }
        if (repeated && ["accept", "back", "quick", "favorite", "home"].indexOf(action) >= 0) return
        if (externalSession && (!sharedDisplay || (!quickOpen && action !== "quick"))) return
        if (activity()) return
        if (gameExitChoice.visible) { gameExitChoice.dispatch(action, repeated); return }
        if (editing) {
            if (action === "back" || action === "quick") closeEditor()
            else if (action === "submit") finishEditor()
            else if (action === "erase") controller.keyboardAction("erase")
            else if ((action === "left" || action === "right") && virtualKeyboard.item && virtualKeyboard.item.navigateHorizontal(action)) return
            else if (keyboardEnabled) controller.keyboardAction(action)
            return
        }
        if (quickOpen) {
            root.forceActiveFocus()
            if (action === "back" || action === "quick") leaveQuick()
            else if (action === "up") quickIndex = Math.max(0, quickIndex - 1)
            else if (action === "down") quickIndex = Math.min(5, quickIndex + 1)
            else if (action === "left" || action === "right") {
                if (quickIndex < 4) adjustSetting(quickIndex, action === "left" ? -1 : 1, repeated)
            } else if (action === "accept") {
                if (quickIndex < 4) adjustSetting(quickIndex, 1)
                else if (quickIndex === 4) leaveQuick()
                else if (gameOverlay) gameExitChoice.present(quickPanel, ["取消", "结束游戏"], 0, "结束当前游戏？")
                else if (leaveQuick()) { session = false; changePage(0) }
            }
            return
        }
        if (toolOpen && toolView.item && toolView.item.choiceOpen) { toolView.item.dispatch(action, repeated); return }
        if (streamingOpen) { streamingView.dispatch(action, repeated); return }
        if (settingsView.choiceOpen) { settingsView.dispatch(action, repeated); return }
        root.forceActiveFocus()
        if (action === "quick") {
            if (testingController) {
                settingsView.enter()
                return
            }
            quickIndex = 0; quickOpen = true
            return
        }
        if (toolOpen) {
            if (action === "home") { if (closeTool()) changePage(0) }
            else if (toolView.item && !toolView.item.dispatch(action, repeated)) closeTool()
            return
        }
        if (action === "home") {
            if (!store.save()) return
            session = false; changePage(0); return
        }
        if (session) {
            if (action === "back") session = false
            else if (["left", "right", "up", "down"].indexOf(action) >= 0) {
                avatarX = Math.max(60, Math.min(924, avatarX + (action === "right" ? 18 : action === "left" ? -18 : 0)))
                avatarY = Math.max(200, Math.min(600, avatarY + (action === "down" ? 18 : action === "up" ? -18 : 0)))
                sessionMoves++
            }
            return
        }
        if (page === 2 && settingsView.tester) return
        if (action === "previousTab" || action === "nextTab") { changePage(page + (action === "nextTab" ? 1 : -1)); return }
        if (action === "back") {
            if (page === 2 && !store.save()) return
            if (page === 2 && settingsView.dispatch(action, repeated)) return
            if (page !== 0) changePage(0); else tabsFocused = !tabsFocused
            return
        }
        if (tabsFocused) {
            if (action === "left" || action === "right") {
                changePage(page + (action === "right" ? 1 : -1)); tabsFocused = page !== 2
            } else if (action === "down" || action === "accept") tabsFocused = false
            return
        }
        if (page === 2) {
            settingsView.dispatch(action, repeated)
        } else {
            const columns = 3
            const count = page === 0 ? Math.min(3, games.length) : games.length
            if (count === 0) { if (action === "up") tabsFocused = true; return }
            if (action === "left") selected = Math.max(0, selected - 1)
            else if (action === "right") selected = Math.min(count - 1, selected + 1)
            else if (action === "up") { if (selected < columns) tabsFocused = true; else selected -= columns }
            else if (action === "down") selected = Math.min(count - 1, selected + columns)
            else if (action === "accept") activateSelected()
            else if (action === "favorite") {
                if (applications || tools) {
                    if (!store.toggleApplicationFavorite(games[selected].id)) { notify("收藏数量已达上限"); return }
                } else store.toggleFavorite(selected)
                store.save()
            }
        }
    }
    Keys.onPressed: function(event) {
        if (screenOff) { activity(); event.accepted = true; return }
        if (editing) return
        if (event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)) return
        const actions = ({[Qt.Key_Left]: "left", [Qt.Key_Right]: "right", [Qt.Key_Up]: "up", [Qt.Key_Down]: "down",
            [Qt.Key_Return]: "accept", [Qt.Key_Enter]: "accept", [Qt.Key_Escape]: "back", [Qt.Key_Backspace]: "back",
            [Qt.Key_Q]: "quick", [Qt.Key_X]: "favorite", [Qt.Key_Home]: "home", [Qt.Key_BracketLeft]: "previousTab", [Qt.Key_BracketRight]: "nextTab"})
        const action = actions[event.key]
        if (action) { dispatch(action, event.isAutoRepeat); event.accepted = true }
    }
    onSessionChanged: { activity(); clearNotice() }
    onEditingChanged: { activity(); clearNotice() }
    onExternalSessionChanged: {
        activity()
        if (!externalSession && sharedDisplay) { gameExitChoice.close(); quickOpen = false }
    }
    onStreamingBusyChanged: activity()
    onTestingControllerChanged: activity()
    onChoicesOpenChanged: activity()
    Connections {
        target: root.applications
        function onChanged() { if (root.applications.error) root.notify(root.applications.error) }
    }
    Binding { target: root.metrics; property: "active"; value: root.windowVisible && root.visible && root.store.monitor && !root.dimmed && !root.screenOff }
    Timer {
        id: idleTimer; objectName: "idleTimer"
        interval: Math.max(1, root.store.dimSeconds) * 1000
        running: root.store.dimSeconds > 0 && root.idleEligible && !root.dimmed && !root.screenOff
        onTriggered: {
            if (root.hardware && root.device.controls && !root.device.setDimmed(true)) { root.notify(root.device.error); return }
            root.dimmed = true
        }
    }
    Timer {
        id: offTimer; objectName: "offTimer"
        interval: Math.max(1, root.store.screenOffSeconds) * 1000
        running: root.store.screenOffSeconds > 0 && root.idleEligible && !root.screenOff
        onTriggered: root.blankScreen()
    }
    TapHandler { onPressedChanged: if (pressed) root.activity() }
    Timer { interval: 60000; running: !root.screenOff; repeat: true; onTriggered: root.now = new Date() }
    onScreenOffChanged: if (!screenOff) now = new Date()
    Timer { id: noticeTimer; interval: Ui.Theme.toastDwell; onTriggered: root.notice = "" }
    Timer { id: volumeTimer; interval: Ui.Theme.hudDwell; onTriggered: root.volumeVisible = false }
    Shortcut { sequence: "Ctrl+Tab"; onActivated: if (root.screenOff) root.activity(); else root.backgroundRequested(true) }
    Shortcut { sequence: "Meta+D"; onActivated: if (root.screenOff) root.activity(); else root.backgroundRequested(false) }
    Item {
        id: canvas
        width: 1024; height: 768; anchors.centerIn: parent
        scale: Math.min(root.width / width, root.height / height)
        Loader {
            id: taskPage; anchors.fill: parent; z: 100; active: root.tasksVisible
            sourceComponent: TaskView {
                applications: root.applications
                onDismissed: root.tasksVisible=false
                onActivated: function(id) { if(root.applications.activate(id))root.tasksVisible=false }
                onCloseRequested: function(id) { root.tasksVisible=false;root.applications.requestClose(id) }
            }
        }
        Ui.HoldConfirm {
            objectName: "taskHold"; z: 101; anchors.centerIn: parent
            progress: root.taskHoldPercent / 100; duration: 2000
            title: "继续按住以强制结束"; detail: "未保存的进度会丢失"; fontScale: root.fontScale
        }
        Item {
            anchors.fill: parent; visible: !root.editing
            Item {
            anchors.fill: parent; visible: !root.gameOverlay
            Ui.TopBar {
                x: Ui.Theme.margin; width: Ui.Theme.contentWidth; fontScale: root.fontScale
                statusVisible: !root.store.monitor; note: root.hardware ? "" : "本地界面预览"
                wifiSignal: root.wifiSignal; batteryPercent: root.batteryPercent
                charging: root.batteryState === "charging" || root.batteryState === "full"
                nightIcon: Ui.Theme.night; clock: root.clockText
            }
            Ui.Tabs {
                x: Ui.Theme.margin; y: 100; visible: !root.session && !root.streamingOpen && !root.toolOpen
                model: ["主页", "游戏库", "设置"]; currentIndex: root.page
                navigationActive: root.tabsFocused && !root.quickOpen
                onActivated: function(index) { root.changePage(index) }
            }
            }
            Ui.Page {
                id: pageContent; objectName: "pageContent"
                anchors.fill: parent; enabled: !root.externalSession; visible: !root.gameOverlay
                route: root.toolOpen ? root.toolRoute : root.streamingOpen ? "streaming" : String(root.page)
                reducedMotion: root.motionReduced
            Item {
                x: Ui.Theme.margin; y: 173; width: Ui.Theme.contentWidth; height: 500; visible: !root.toolOpen && !root.streamingOpen && !root.session && root.page < 2
                Ui.Label { text: root.page === 0 ? ((root.applications || root.tools) ? "应用与游戏" : "继续游玩") : "游戏库"; color: Ui.Theme.text; role: "title" }
                Ui.Label { y: 48; text: (root.applications || root.tools) ? (root.page === 0 ? "常用入口" : "全部") + " · " + (root.page === 0 ? Math.min(3, root.games.length) : root.games.length) + " 项" : root.page === 0 ? "最近使用 · 3 个演示入口" : "全部 6 项 · 示例内容"; font.pixelSize: 14 * root.fontScale; color: Ui.Theme.textSecondary }
                Ui.Label { anchors.centerIn: parent; visible: root.games.length === 0; text: "暂无应用"; color: Ui.Theme.textSecondary; font.pixelSize: 22 * root.fontScale }
                GridView {
                    id: gameGrid; objectName: "gameGrid"
                    x: -12; y: 79; width: parent.width + 24; height: 421; clip: true
                    cellWidth: width / 3; cellHeight: root.page === 0 ? 350 : 198
                    model: root.page === 0 ? Math.min(3, root.games.length) : root.games.length
                    currentIndex: root.selected
                    boundsBehavior: Flickable.StopAtBounds
                    onCurrentIndexChanged: if (currentIndex >= 0) positionViewAtIndex(currentIndex, GridView.Contain)
                    delegate: Item {
                        id: tile; required property int index
                        width: gameGrid.cellWidth; height: gameGrid.cellHeight
                        Ui.GameCard {
                            x: 12; y: 12
                            width: parent.width - 23; height: root.page === 0 ? 330 : 178
                            title: root.games[tile.index].title; subtitle: root.games[tile.index].detail
                            cardColor: Ui.Theme.cardColor(root.games[tile.index].palette !== undefined ? root.games[tile.index].palette : tile.index)
                            iconName: root.games[tile.index].icon || ""; showTitle: true
                            selected: root.selected === tile.index && !root.tabsFocused && !root.quickOpen
                            favorite: (root.applications || root.tools) ? root.store.applicationFavorites.indexOf(root.games[tile.index].id) >= 0 : root.store.favorites.indexOf(tile.index) >= 0
                            reducedMotion: root.store.reducedMotion; fontScale: root.fontScale
                            onFocused: { root.selected = tile.index; root.tabsFocused = false; root.forceActiveFocus() }
                            onActivated: { root.selected = tile.index; root.activateSelected() }
                        }
                    }
                }
            }
            Loader {
                id: toolView; objectName: "toolView"; x: Ui.Theme.margin; y: Ui.Theme.toolTop; width: Ui.Theme.contentWidth; height: Ui.Theme.toolHeight
                active: root.toolOpen && root.tools !== null; visible: active
                sourceComponent: ToolPage {
                    tools: root.tools; kind: root.toolRoute
                    navigationActive: root.windowVisible && !root.quickOpen && !root.dimmed
                    onBackRequested: root.closeTool()
                    onSearchRequested: function(value) { root.openTextEditor("搜索游戏", value, "portSearch") }
                }
            }
            SettingsView {
                id: settingsView; x: Ui.Theme.margin; y: 178; width: Ui.Theme.contentWidth; height: 493
                navigationActive: root.windowVisible && !root.quickOpen && !root.tabsFocused && !root.editing && !root.dimmed
                visible: !root.toolOpen && !root.streamingOpen && !root.session && root.page === 2
                store: root.store; metrics: root.metrics; controller: root.controller; device: root.device; network: root.network
                browserVersions: root.browserVersions
                onNotice: function(text) { root.notify(text) }
                onActivity: { root.activity(); root.forceActiveFocus() }
                onScreenOffRequested: root.blankScreen()
                onEditRequested: root.openEditor()
                onWifiPasswordRequested: function(name) { root.openTextEditor("Wi-Fi 密码 · " + name, "", "wifiPassword") }
            }
            Item {
                anchors.fill: parent; visible: !root.toolOpen && !root.streamingOpen && root.session
                Ui.Label { x: Ui.Theme.margin; y: 115; text: root.games[root.selected] ? root.games[root.selected].title : ""; textFormat: Text.PlainText; color: Ui.Theme.text; font.pixelSize: 34 * root.fontScale; font.bold: true }
                Ui.Label { x: Ui.Theme.margin; y: 163; text: "交互演示 · 方向键移动方块，Q 呼出快捷面板"; color: Ui.Theme.textSecondary; font.pixelSize: 16 }
                Rectangle {
                    x: Ui.Theme.margin; y: 219; width: Ui.Theme.contentWidth; height: 426; radius: 24; color: Ui.Theme.surface; border.color: Ui.Theme.outline
                    Repeater {
                        model: 8
                        Rectangle { required property int index; x: 38 + index * 116; y: 0; width: 1; height: 426; color: Ui.Theme.outline }
                    }
                    Rectangle { x: 0; y: 213; width: parent.width; height: 1; color: Ui.Theme.outline }
                    Ui.Label { x: 28; y: 25; text: "PREVIEW SESSION"; color: Ui.Theme.textTertiary; font.pixelSize: 12 * root.fontScale; font.letterSpacing: 3 }
                    Ui.Label { x: 28; y: 360; text: "未运行游戏或串流"; color: Ui.Theme.textSecondary; font.pixelSize: 16 }
                }
                Rectangle { x: root.avatarX; y: root.avatarY; width: 38; height: 38; radius: 10; color: Ui.Theme.accent }
            }
            Loader {
                id: streamingView; x: Ui.Theme.margin; y: Ui.Theme.toolTop; width: Ui.Theme.contentWidth; height: Ui.Theme.toolHeight
                visible: root.streamingOpen && root.streaming !== null
                active: root.streaming !== null
                readonly property var hints: item ? item.hints : []
                function dispatch(action, repeated) { if (item) item.dispatch(action, repeated) }
                sourceComponent: StreamingView {
                    manager: root.streaming; store: root.store
                    navigationActive: root.windowVisible && !root.quickOpen && !root.editing && !root.dimmed
                    onEditRequested: function(key, label, value) { root.openTextEditor(label, value, key) }
                    onBackRequested: { root.streamingOpen = false; root.clearNotice(); root.forceActiveFocus() }
                }
            }
            }
            Rectangle {
                anchors.fill: parent; color: Ui.Theme.scrim; opacity: root.quickOpen ? 1 : 0; visible: opacity > 0
                Behavior on opacity { Ui.Motion {} }
                MouseArea { anchors.fill: parent; enabled: root.quickOpen; onClicked: root.leaveQuick() }
            }
            Ui.QuickPanel {
                id: quickPanel
                objectName: "quickPanel"
                x: root.quickOpen ? Ui.Theme.canvasWidth - Ui.Theme.quickPanelInset - width : Ui.Theme.canvasWidth + Ui.Theme.shadowSpread
                title: "快捷设置"; fontScale: root.fontScale
                enabled: root.quickOpen
                visible: root.quickOpen || x < Ui.Theme.canvasWidth
                Behavior on x { Ui.Motion { curve: "emphasized"; duration: Ui.Theme.reducedMotion ? 0 : Ui.Theme.sheetEnterDuration } }
                Column {
                    width: parent.width; spacing: Ui.Theme.space8
                    Repeater {
                        model: 6
                        Ui.ListRow {
                            required property int index
                            readonly property int brightness: root.hardware ? root.device.info.brightnessPercent : root.store.brightness
                            width: parent.width; fontScale: root.fontScale
                            reducedMotion: root.store.reducedMotion
                            actionable: !root.hardware || index >= 2 || (index === 1 && root.device.controls)
                            toggleState: index === 2 ? Number(root.store.reducedMotion) : index === 3 ? Number(root.store.monitor) : -1
                            title: ["音量", "亮度", "减少动态效果", "性能浮窗", root.gameOverlay ? "继续游戏" : root.session ? "继续演示" : "关闭面板", root.gameOverlay ? "结束游戏" : "返回主页"][index]
                            value: index === 0 ? (root.hardware ? "机身音量键" : root.store.volume + "%") : index === 1 ? (brightness < 0 ? "—" : brightness + "%") : ""
                            progress: index === 0 && !root.hardware ? root.store.volume / 100 : index === 1 && brightness >= 0 ? brightness / 100 : -1
                            chevron: index >= 4
                            selected: root.quickOpen && root.quickIndex === index
                            onFocused: { root.quickIndex = index; root.forceActiveFocus() }
                            onActivated: { root.quickIndex = index; root.dispatch("accept", false) }
                        }
                    }
                }
            }
        }
        Item {
            x: Ui.Theme.margin; y: Ui.Theme.canvasHeight - Ui.Theme.hintBarHeight; width: Ui.Theme.contentWidth; height: Ui.Theme.hintBarHeight
            visible: !root.editing && (!root.gameOverlay || root.quickOpen)
            Rectangle { width: parent.width; height: 1; color: Ui.Theme.outline }
            Ui.HintBar { objectName: "footerHints"; anchors.verticalCenter: parent.verticalCenter; width: parent.width; actions: root.controlHints; fontScale: root.fontScale }
        }
        Item {
            anchors.fill: parent; visible: root.editing
            MouseArea { anchors.fill: parent }
            Ui.Label { x: Ui.Theme.margin; y: 70; width: root.store.monitor ? performancePanel.x - x - Ui.Theme.padding : Ui.Theme.contentWidth; text: root.editLabel; color: Ui.Theme.text; role: "title" }
            Ui.Label { x: Ui.Theme.margin; y: 123; width: inputField.width; wrapMode: Text.Wrap; text: root.testInputVisible ? "自动化输入测试允许截图，请勿填写密码" : root.editPurpose === "test" ? "退出后清空输入内容" : root.editPurpose === "wifiPassword" ? "完成后连接 · B 取消" : "完成后保存 · B 取消"; color: Ui.Theme.textSecondary; font.pixelSize: 16 * root.fontScale }
            Ui.TextField {
                id: inputField; objectName: "inputField"; x: Ui.Theme.margin; y: 183; width: Ui.Theme.contentWidth - doneButton.width - Ui.Theme.padding; height: 64
                fontScale: root.fontScale; maximumLength: root.editPurpose === "wifiPassword" ? 64 : root.editPurpose === "portSearch" ? 80 : 128
                echoMode: root.editPurpose === "wifiPassword" ? TextInput.Password : TextInput.Normal
                inputMethodHints: Qt.ImhNoPredictiveText | Qt.ImhSensitiveData | (root.editPurpose === "wifiPassword" ? Qt.ImhHiddenText | Qt.ImhLatinOnly | Qt.ImhNoAutoUppercase : 0)
                Accessible.name: root.editLabel
                Keys.onEscapePressed: root.closeEditor()
                Keys.onReturnPressed: root.finishEditor()
            }
            Ui.Button { id: doneButton; x: Ui.Theme.margin + Ui.Theme.contentWidth - width; y: 183; width: 152; height: 64; text: "完成"; primary: true; focusPolicy: Qt.NoFocus; Accessible.name: "完成输入"; onClicked: root.finishEditor() }
            Ui.Label { x: Ui.Theme.margin; y: 270; visible: virtualKeyboard.status === Loader.Error; text: "虚拟键盘模块不可用；仍可使用实体键盘。"; color: Ui.Theme.danger; font.pixelSize: 17 }
            Ui.HintBar { x: Ui.Theme.margin; y: 267; width: inputField.width; visible: virtualKeyboard.status !== Loader.Error; fontScale: root.fontScale; actions: root.keyboardEnabled ? [["方向", "选择按键"], ["A", "输入"], ["Y", "退格"], ["START", "确认"], ["B", "取消"]] : [["键盘", "输入文字"], ["Enter", "确认"], ["Esc", "取消"]] }
            Loader {
                id: virtualKeyboard; objectName: "virtualKeyboard"
                active: root.keyboardEnabled && root.editing
                source: "KeyboardPanel.qml"
                width: parent.width; height: item ? (item as Item).implicitHeight : 0
                anchors.bottom: parent.bottom
            }
            Binding { target: virtualKeyboard.item; property: "reducedMotion"; value: root.store.reducedMotion; when: virtualKeyboard.status === Loader.Ready }
        }
        PerformancePanel {
            id: performancePanel
            objectName: "performancePanel"
            x: root.quickOpen ? Ui.Theme.margin : Ui.Theme.canvasWidth - Ui.Theme.margin - width; y: root.quickOpen ? 168 : 20
            metrics: root.metrics; device: root.device; fontScale: root.fontScale; compact: root.editing || root.quickOpen
            visible: root.store.monitor
        }
        Ui.ChoicePopup {
            id: gameExitChoice; objectName: "gameExitChoice"; parent: root.T.Overlay.overlay
            onActivated: function(index) { close(); if (index === 1 && root.gameOverlay) root.applications.stop() }
            onClosed: root.forceActiveFocus()
        }
        Rectangle {
            anchors.fill: parent; visible: root.dimmed; color: root.hardware && root.device.controls ? "transparent" : Ui.Theme.scrim
            Rectangle {
                anchors.centerIn: parent; visible: !root.hardware || !root.device.controls
                width: dimNotice.implicitWidth + 2 * Ui.Theme.space24; height: Ui.Theme.minTarget; radius: height / 2; color: Ui.Theme.surface
                Ui.Label { id: dimNotice; anchors.centerIn: parent; text: "界面已变暗 · 按键或点击恢复"; color: Ui.Theme.text; font.pixelSize: 21 }
            }
            MouseArea { anchors.fill: parent; onPressed: root.activity() }
        }
        Rectangle {
            anchors.fill: parent; z: 200; visible: root.screenOff
            color: root.hardware && root.device.controls ? "transparent" : Ui.Theme.blackout
            Accessible.role: Accessible.Pane
            Accessible.name: "屏幕已关闭，按任意键唤醒"
            MouseArea { anchors.fill: parent; onPressed: root.activity() }
        }
        Ui.Toast {
            objectName: "notice"
            x: root.quickOpen ? Ui.Theme.margin : (parent.width - width) / 2
            y: root.editing ? 310 : root.quickOpen ? Math.max(340, performancePanel.visible ? performancePanel.y + performancePanel.height + Ui.Theme.space12 : 340)
                : Ui.Theme.canvasHeight - Ui.Theme.hintBarHeight - height - Ui.Theme.space16
            maximumWidth: root.quickOpen ? 530 : Ui.Theme.contentWidth
            text: root.store.error || root.notice; error: root.store.error !== ""; fontScale: root.fontScale
        }
        Ui.Hud {
            id: volumeHud; objectName: "volumeHud"
            // Top center; a performance overlay in the top-right corner pushes it just far enough left.
            readonly property bool crowded: performancePanel.visible && performancePanel.y < y + height
            x: crowded ? Math.min((parent.width - width) / 2, performancePanel.x - Ui.Theme.space16 - width) : (parent.width - width) / 2
            y: Ui.Theme.space24
            shown: root.volumeVisible; value: root.volumePercent / 100; fontScale: root.fontScale
            iconName: root.volumePercent === 0 ? "volume-muted" : "volume"
            Accessible.role: Accessible.Indicator
            Accessible.name: root.volumePercent === 0 ? "静音" : "音量 " + root.volumePercent + "%"
        }
    }
    // A sibling of the canvas, so the one-frame capture never contains itself.
    ShaderEffectSource {
        id: themeSnapshot; objectName: "themeFade"
        anchors.centerIn: parent; width: canvas.width; height: canvas.height; scale: canvas.scale
        live: false; visible: false; sourceItem: null
        onScheduledUpdateCompleted: { Ui.Theme.night = root.nightActive; themeFade.restart() }
        Ui.Motion {
            id: themeFade; target: themeSnapshot; property: "opacity"; from: 1; to: 0; duration: Ui.Theme.themeDuration
            onFinished: { themeSnapshot.visible = false; themeSnapshot.sourceItem = null }
        }
    }
}
