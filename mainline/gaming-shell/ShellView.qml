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
    readonly property bool choicesOpen: gameExitChoice.visible || optionsMenu.open || settingsView.choiceOpen || (streamingView.item !== null && streamingView.item.choiceOpen) || (toolView.item !== null && toolView.item.choiceOpen)
    Binding { target: Ui.Theme; property: "fontScale"; value: root.fontScale }
    // §7.5: held directions speed up after 2 s in lists, never in grids or on the keyboard.
    Binding {
        target: root.controller; property: "fastRepeat"; when: root.controller !== null
        value: !root.editing && (root.quickOpen || root.choicesOpen || root.toolOpen || root.streamingOpen || root.page === 2)
    }
    // B repeats only as the keyboard's backspace (§7.5); pages take one B per press.
    Binding { target: root.controller; property: "backRepeat"; when: root.controller !== null; value: root.editing }
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
    // §7.4 quick panel: sliders adjust with ←→, other rows act with A; its own footer replaces the page's.
    readonly property var quickHints: (quickIndex >= 2 ? [{button: "A", label: quickIndex < 4 ? "切换" : "确定"}]
            : !hardware || (quickIndex === 1 && device.controls) ? [{button: "dpadH", label: "调整"}] : [])
        .concat([{button: "B", label: gameOverlay ? "返回游戏" : "关闭"}])
    readonly property string activateLabel: customApplications ? "启动" : tools ? "打开" : streaming && selected === 0 ? "主机管理" : "打开演示"
    // §7.6: the hint bar comes from declared actions; Select appears only on the home page, B never
    // there, and plain up/down moves are not hinted.
    readonly property var pageExit: page === 0 ? [{button: "Select", label: "快捷面板"}] : [{button: "B", label: "主页"}]
    readonly property var controlHints: toolOpen && toolView.item ? toolView.item.hints
        : streamingOpen ? streamingView.hints
        : session ? [{button: "dpad", label: "移动"}, {button: "B", label: "结束演示"}]
        : page === 2 ? settingsView.hints
        : tabsFocused ? [{button: "dpadH", label: "切换页面"}, {button: "A", label: "进入"}].concat(pageExit)
        : games.length === 0 ? pageExit
        : [{button: "A", label: activateLabel}, {button: "X", label: selectedFavorite ? "取消收藏" : "收藏"}, {button: "Start", label: "选项"}].concat(pageExit)
    readonly property string controlContext: !toolOpen && !streamingOpen && !session && page === 1 ? games.length + " 项" : ""
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
    // §7.5 page-layer holds: the task page's X (2 s force-quit) and the controller test's B (1 s exit).
    // Another key, a release before the end or an input-owner change cancels; a task X released
    // before the ring appears is a tap and closes normally.
    property string holdAction: ""
    property int holdDuration: 0
    property real holdProgress: 0
    property double holdStarted: 0
    readonly property real holdElapsed: holdProgress * holdDuration
    readonly property real holdRing: holdElapsed >= Ui.Theme.holdDelay ? holdProgress : -1
    function beginHold(action, duration) {
        holdAction = action; holdDuration = duration; holdStarted = Date.now(); holdProgress = 0; holdTimer.restart()
    }
    function cancelHold() { holdTimer.stop(); holdAction = ""; holdProgress = 0 }
    function finishHold() {
        const action = holdAction
        cancelHold()
        if (action === "taskForce" && tasksVisible && taskPage.item) taskPage.item.forceSelected()
        else if (action === "testerExit") settingsView.returnToCategories()
    }
    Timer {
        id: holdTimer; interval: 16; repeat: true
        onTriggered: {
            root.holdProgress = Math.min(1, (Date.now() - root.holdStarted) / root.holdDuration)
            if (root.holdProgress >= 1) root.finishHold()
        }
    }
    onTasksVisibleChanged: cancelHold()
    function release(action) {
        if (holdAction === "taskForce" && action === "itemAction") {
            const tap = Date.now() - holdStarted < Ui.Theme.holdDelay
            cancelHold()
            if (tap && tasksVisible && taskPage.item) taskPage.item.closeSelected()
        } else if (holdAction === "testerExit" && action === "back") cancelHold()
        else if (!editing && !toolOpen && !streamingOpen && !quickOpen && page === 2) settingsView.release(action)
    }
    // Right stick: scrolls the settings detail or long text without moving focus.
    function scroll(velocity) {
        if (screenOff || dimmed || tasksVisible || quickOpen || editing || choicesOpen || externalSession) return
        if (toolOpen && toolView.item) toolView.item.scroll(velocity)
        else if (!streamingOpen && !session && page === 2) settingsView.scroll(velocity)
    }
    // §7.3 Start: every action of the focused card, task or tool page, unavailable ones with a reason.
    property var optionsOwner: null
    function cardOptions() {
        const game = games[selected]
        if (!game) return []
        const items = [{id: "start", label: activateLabel, button: "A"}, {id: "favorite", label: selectedFavorite ? "取消收藏" : "收藏", button: "X"}]
        if (game.route) return items
        return items.concat([{id: "controls", label: "按键与画面", reason: "每游戏设置尚未接入"}, {id: "saves", label: "存档管理", reason: "每游戏设置尚未接入"}])
    }
    function openOptions() {
        let owner = null, title = "", items = []
        if (tasksVisible && taskPage.item) {
            owner = taskPage.item; items = owner.optionItems(); title = owner.currentTask ? owner.currentTask.title : ""
        } else if (toolOpen && toolView.item) {
            owner = toolView.item; items = owner.optionItems(); title = owner.optionTitle
        } else if (!streamingOpen && !session && page < 2 && !tabsFocused && games[selected]) {
            owner = root; items = cardOptions(); title = games[selected].title
        }
        if (owner && optionsMenu.present(title, items)) optionsOwner = owner
    }
    function runOption(id) {
        if (id === "start") activateSelected()
        else if (id === "favorite") toggleFavorite()
    }
    function toggleFavorite() {
        if (!games[selected]) return
        if (applications || tools) {
            if (!store.toggleApplicationFavorite(games[selected].id)) { notify("收藏数量已达上限"); return }
        } else store.toggleFavorite(selected)
        store.save()
    }
    // The keyboard's B erases and keeps erasing while held, stopping at empty; only a separate
    // press on an empty field closes the editor (§7.5). Repeats never close it.
    function editorDispatch(action, repeated) {
        const keyboard = virtualKeyboard.item
        if (action === "quick") { if (!repeated) closeEditor() }
        else if (action === "options") { if (!repeated) finishEditor() }
        else if (action === "back") {
            if (inputField.text.length > 0) controller.keyboardAction("erase")
            else if (!repeated) closeEditor()
        } else if (action === "pageAction") controller.keyboardAction("space")
        else if (action === "itemAction") { if (keyboard) keyboard.toggleShift() }
        else if (action === "prevSection" || action === "nextSection")
            inputField.cursorPosition = Math.max(0, Math.min(inputField.text.length, inputField.cursorPosition + (action === "nextSection" ? 1 : -1)))
        else if (action === "pageUp") { if (keyboard && !repeated) keyboard.toggleLanguage() }
        else if (action === "pageDown") { if (keyboard && !repeated) keyboard.toggleSymbols() }
        else if ((action === "left" || action === "right") && keyboard && keyboard.navigateHorizontal(action)) return
        else if (keyboardEnabled && ["up", "down", "left", "right", "accept"].indexOf(action) >= 0) controller.keyboardAction(action)
    }
    function dispatch(action, repeated) {
        if (screenOff) { activity(); return }
        if (holdAction !== "" && !repeated) cancelHold()
        if (repeated && ["accept", "quick", "home", "itemAction", "pageAction", "options", "prevSection", "nextSection"].indexOf(action) >= 0) return
        if (tasksVisible && taskPage.item) {
            if (activity()) return
            if (optionsMenu.open) optionsMenu.dispatch(action, repeated)
            else if (action === "itemAction") { if (taskPage.item.canAct) beginHold("taskForce", Ui.Theme.forceHoldDuration) }
            else if (action === "options") openOptions()
            else taskPage.item.dispatch(action, repeated)
            return
        }
        if (externalSession && (!sharedDisplay || (!quickOpen && action !== "quick"))) return
        if (activity()) return
        if (gameExitChoice.visible) { gameExitChoice.dispatch(action, repeated); return }
        if (optionsMenu.open) { optionsMenu.dispatch(action, repeated); return }
        if (editing) { editorDispatch(action, repeated); return }
        if (repeated && action === "back") return
        if (quickOpen) {
            root.forceActiveFocus()
            if (action === "back" || action === "quick") leaveQuick()
            else if (action === "up") quickIndex = Math.max(0, quickIndex - 1)
            else if (action === "down") quickIndex = Math.min(5, quickIndex + 1)
            else if (action === "left" || action === "right") {
                if (quickIndex < 2) adjustSetting(quickIndex, action === "left" ? -1 : 1, repeated)
            } else if (action === "accept") {
                if (quickIndex < 2) return
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
        if (action === "quick") { quickIndex = 0; quickOpen = true; return }
        if (action === "options") { openOptions(); return }
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
        if (page === 2) {
            // Controller test: every key but Select is test input; holding B for 1 s leaves.
            if (settingsView.tester) { if (action === "back") beginHold("testerExit", Ui.Theme.exitHoldDuration); return }
            if (!settingsView.dispatch(action, repeated) && store.save()) changePage(0)
            return
        }
        // Home B does nothing (§7.4); the library returns home.
        if (action === "back") { if (page === 1) changePage(0); return }
        if (tabsFocused) {
            if (action === "left" || action === "right") {
                changePage(page + (action === "right" ? 1 : -1)); tabsFocused = page !== 2
            } else if (action === "down" || action === "accept") tabsFocused = false
            return
        }
        const columns = 3
        const count = page === 0 ? Math.min(3, games.length) : games.length
        if (count === 0) { if (action === "up") tabsFocused = true; return }
        if (action === "left") selected = Math.max(0, selected - 1)
        else if (action === "right") selected = Math.min(count - 1, selected + 1)
        else if (action === "up") { if (selected < columns) tabsFocused = true; else selected -= columns }
        else if (action === "down") selected = Math.min(count - 1, selected + columns)
        else if (action === "accept") activateSelected()
        else if (action === "itemAction") toggleFavorite()
        // Library pages hold two full rows.
        else if (page === 1 && (action === "pageUp" || action === "pageDown"))
            selected = Math.max(0, Math.min(count - 1, selected + (action === "pageDown" ? 2 : -2) * columns))
    }
    // §7.8 desktop preview keys; Select (Q) decides on release like the controller.
    readonly property var previewKeys: ({[Qt.Key_Left]: "left", [Qt.Key_Right]: "right", [Qt.Key_Up]: "up", [Qt.Key_Down]: "down",
        [Qt.Key_Return]: "accept", [Qt.Key_Enter]: "accept", [Qt.Key_Escape]: "back", [Qt.Key_X]: "itemAction", [Qt.Key_Y]: "pageAction",
        [Qt.Key_M]: "options", [Qt.Key_Q]: "quick", [Qt.Key_BracketLeft]: "prevSection", [Qt.Key_BracketRight]: "nextSection",
        [Qt.Key_PageUp]: "pageUp", [Qt.Key_PageDown]: "pageDown"})
    Keys.onPressed: function(event) {
        if (screenOff) { activity(); event.accepted = true; return }
        if (editing) return
        if (event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)) return
        const action = previewKeys[event.key]
        if (!action) return
        event.accepted = true
        if (action !== "quick") dispatch(action, event.isAutoRepeat)
    }
    Keys.onReleased: function(event) {
        if (editing || event.isAutoRepeat || (event.modifiers & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier))) return
        const action = previewKeys[event.key]
        if (!action) return
        event.accepted = true
        if (action === "quick") dispatch(action, false); else release(action)
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
                applications: root.applications; fontScale: root.fontScale
                holdProgress: root.holdAction === "taskForce" ? root.holdRing : -1
                onDismissed: root.tasksVisible=false
                onActivated: function(id) { if(root.applications.activate(id))root.tasksVisible=false }
                onCloseRequested: function(id) { root.tasksVisible=false;root.applications.requestClose(id) }
                onNotice: function(text) { root.notify(text) }
            }
        }
        // Router Select+X holds (stage 5 replaces them) and the task page's X hold share one card.
        Ui.HoldConfirm {
            objectName: "taskHold"; z: 101; anchors.centerIn: parent
            progress: Math.max(root.taskHoldPercent / 100, root.holdAction === "taskForce" ? root.holdProgress : 0)
            duration: Ui.Theme.forceHoldDuration
            title: "继续按住以强制结束"; detail: "未保存的进度会丢失"; fontScale: root.fontScale
        }
        Ui.OptionsSheet {
            id: optionsMenu; objectName: "optionsMenu"; anchors.fill: parent; z: 102
            fontScale: root.fontScale; reducedMotion: root.store.reducedMotion
            onChosen: function(id) {
                const owner = root.optionsOwner
                root.optionsOwner = null
                if (owner) owner.runOption(id)
            }
            onOpenChanged: if (!open) root.forceActiveFocus()
        }
        Item {
            anchors.fill: parent; visible: !root.editing
            Item {
            anchors.fill: parent; visible: !root.gameOverlay
            Ui.TopBar {
                x: Ui.Theme.margin; width: Ui.Theme.contentWidth; fontScale: root.fontScale
                note: root.hardware ? "" : "本地界面预览"
                wifiSignal: root.wifiSignal; batteryPercent: root.batteryPercent
                charging: root.batteryState === "charging" || root.batteryState === "full"
                clock: root.clockText
            }
            Ui.Tabs {
                x: Ui.Theme.margin; y: 100; visible: !root.session && !root.streamingOpen && !root.toolOpen
                model: ["主页", "游戏库", "设置"]; currentIndex: root.page; shoulderHints: false
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
                Column {
                    id: homeHeading; spacing: Ui.Theme.space4
                    Ui.Label { text: root.page === 0 ? ((root.applications || root.tools) ? "应用与游戏" : "继续游玩") : "游戏库"; color: Ui.Theme.text; role: "title" }
                    Ui.Label { text: (root.applications || root.tools) ? (root.page === 0 ? "常用入口" : "全部") + " · " + (root.page === 0 ? Math.min(3, root.games.length) : root.games.length) + " 项" : root.page === 0 ? "最近使用 · 3 个演示入口" : "全部 6 项 · 示例内容"; role: "caption"; color: Ui.Theme.textSecondary }
                }
                Ui.Label { anchors.centerIn: parent; visible: root.games.length === 0; text: "暂无应用"; color: Ui.Theme.textSecondary; role: "label" }
                GridView {
                    id: gameGrid; objectName: "gameGrid"
                    // Cards start below the heading; larger fonts push them down instead of overlapping.
                    x: -12; y: Math.max(79, homeHeading.height); width: parent.width + 24; height: 421; clip: true
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
                testerHold: root.holdAction === "testerExit" ? root.holdRing : -1
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
                Ui.Label { id: sessionTitle; x: Ui.Theme.margin; y: 115; text: root.games[root.selected] ? root.games[root.selected].title : ""; textFormat: Text.PlainText; color: Ui.Theme.text; role: "display" }
                Ui.Label { x: Ui.Theme.margin; y: sessionTitle.y + sessionTitle.height; text: "交互演示 · 方向键移动方块，Q 呼出快捷面板"; role: "caption" }
                Rectangle {
                    x: Ui.Theme.margin; y: 219; width: Ui.Theme.contentWidth; height: 426; radius: 24; color: Ui.Theme.surface; border.color: Ui.Theme.outline
                    Repeater {
                        model: 8
                        Rectangle { required property int index; x: 38 + index * 116; y: 0; width: 1; height: 426; color: Ui.Theme.outline }
                    }
                    Rectangle { x: 0; y: 213; width: parent.width; height: 1; color: Ui.Theme.outline }
                    Ui.Label { x: 28; y: 25; text: "PREVIEW SESSION"; color: Ui.Theme.textTertiary; role: "micro"; font.letterSpacing: 3 }
                    Ui.Label { x: 28; y: 360; text: "未运行游戏或串流"; role: "caption" }
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
                title: "快捷设置"; fontScale: root.fontScale; hints: root.quickHints
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
            visible: !root.editing && !root.gameOverlay && !root.quickOpen
            Rectangle { width: parent.width; height: 1; color: Ui.Theme.outline }
            Ui.HintBar { objectName: "footerHints"; anchors.verticalCenter: parent.verticalCenter; width: parent.width; actions: root.controlHints; context: root.controlContext; fontScale: root.fontScale }
        }
        Item {
            anchors.fill: parent; visible: root.editing
            MouseArea { anchors.fill: parent }
            Ui.Label { x: Ui.Theme.margin; y: 70; width: Ui.Theme.contentWidth; text: root.editLabel; color: Ui.Theme.text; role: "title" }
            Ui.Label { x: Ui.Theme.margin; y: 123; width: inputField.width; wrapMode: Text.Wrap; text: root.testInputVisible ? "自动化输入测试允许截图，请勿填写密码" : root.editPurpose === "test" ? "退出后清空输入内容" : root.editPurpose === "wifiPassword" ? "完成后连接 · Select 取消" : "完成后保存 · Select 取消"; role: "caption" }
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
            Ui.Label { x: Ui.Theme.margin; y: 270; visible: virtualKeyboard.status === Loader.Error; text: "虚拟键盘模块不可用；仍可使用实体键盘。"; color: Ui.Theme.danger; role: "caption" }
            Ui.HintBar { x: Ui.Theme.margin; y: 267; width: inputField.width; visible: virtualKeyboard.status !== Loader.Error; fontScale: root.fontScale; actions: root.keyboardEnabled
                    ? [{button: "A", label: "输入"}, {button: "B", label: "退格"}, {button: "X", label: "大小写"}, {button: "Y", label: "空格"}, {button: "Start", label: "完成"}]
                    : [{button: "A", label: "完成"}, {button: "B", label: "取消"}] }
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
            x: Ui.Theme.canvasWidth - Ui.Theme.perfPanelRight - width
            y: root.gameOverlay ? Ui.Theme.perfPanelTop : Ui.Theme.perfPanelDesktopTop
            metrics: root.metrics; device: root.device; fontScale: root.fontScale
            // The quick panel covers the same corner; it owns the screen while open.
            visible: root.store.monitor && !empty && !root.quickOpen
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
                Ui.Label { id: dimNotice; anchors.centerIn: parent; text: "界面已变暗 · 按键或点击恢复"; color: Ui.Theme.text; role: "label" }
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
            objectName: "notice"; z: 103 // Above the task page and the options sheet.
            x: root.quickOpen ? Ui.Theme.margin : (parent.width - width) / 2
            y: root.editing ? 310 : root.quickOpen ? 340 : Ui.Theme.canvasHeight - Ui.Theme.hintBarHeight - height - Ui.Theme.space16
            maximumWidth: root.quickOpen ? 530 : Ui.Theme.contentWidth
            text: root.store.error || root.notice; error: root.store.error !== ""; fontScale: root.fontScale
        }
        Ui.Hud {
            id: volumeHud; objectName: "volumeHud"
            // Top center. In game it stays inside the compositor region, and below the performance
            // overlay (right-aligned with it) when both are up; on the desktop the overlay starts lower.
            readonly property bool belowPanel: root.gameOverlay && performancePanel.visible
            x: belowPanel ? performancePanel.x + performancePanel.width - width
                : Math.max((parent.width - width) / 2, root.gameOverlay ? Ui.Theme.gameOverlayVolumeLeft : 0)
            y: belowPanel ? performancePanel.y + performancePanel.height + Ui.Theme.space16 : Ui.Theme.space24
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
