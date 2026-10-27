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
    readonly property bool remoteTextAllowed: editing && !quickOpen && !choicesOpen && !dimmed && !screenOff && !externalSession && (editPurpose === "portSearch" || editPurpose === "librarySearch" || testInputVisible)
    readonly property int portCatalogIndex: toolView.item ? toolView.item.catalogIndex : 0
    readonly property bool portCatalogSidebar: !toolView.item || toolView.item.catalogSidebar
    readonly property bool sensitiveVisible: tasksVisible || (externalSession && ["builtin.browser", "builtin.terminal", "builtin.files", "builtin.text", "builtin.transfer"].includes(activeApplication)) || (editing && !testInputVisible) || (streaming !== null && streaming.pin.length > 0)
    property string editPurpose: "test"
    property string keyboardLastKey: "q"
    property string editLabel: "文字输入测试"
    readonly property bool externalSession: applications !== null && applications.running
    readonly property bool customApplications: applications !== null && applications.hasManifest
    readonly property string activeApplication: applications ? applications.activeId : ""
    readonly property bool applicationError: applications !== null && applications.error.length > 0
    readonly property int applicationExitCode: applications ? applications.exitCode : 0
    readonly property string selectedApplication: (applications || tools) && games[selected] ? (games[selected].id || "") : ""
    readonly property bool selectedFavorite: entryFavorite(selected)
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
    // §4 one focus ring on screen: any sheet, dialog or panel hides the page's ring (cards stay lifted).
    readonly property bool overlayOpen: quickOpen || editing || choicesOpen
    readonly property bool choicesOpen: gameExitChoice.visible || optionsMenu.open || powerMenu.open || settingsView.choiceOpen || (streamingView.item !== null && streamingView.item.choiceOpen) || (toolView.item !== null && toolView.item.choiceOpen)
    Binding { target: Ui.Theme; property: "fontScale"; value: root.fontScale }
    // §7.5: held directions speed up after 2 s in lists, never in grids or on the keyboard.
    Binding {
        target: root.controller; property: "fastRepeat"; when: root.controller !== null
        value: !root.editing && (root.quickOpen || root.choicesOpen || root.toolOpen || root.streamingOpen || root.page >= 2)
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
    // Pages: 0 home, 1 library, 2 settings, 3 tools. `selected` is the focused entry of `games`
    // (-1 on the 全部游戏 card or the dock); the home row, library grid and tools list keep their own position.
    property int page: 0
    property int selected: 0
    property alias settingsIndex: settingsView.rowIndex
    property int homeIndex: 0
    property bool dockFocused: false
    property int dockIndex: 0
    property int libraryFilter: 0
    property int libraryIndex: 0
    property var libraryPositions: ({})
    property string libraryQuery: ""
    property int toolsIndex: 0
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
    // §8 quick panel: tiles take A, sliders ←→; its own footer replaces the page's.
    readonly property var quickHints: (quickId === "brightness" || quickId === "volume" ? [{button: "dpadH", label: "调整"}]
            : [{button: "A", label: quickId === "wifi" ? "打开" : quickId === "monitor" || quickId === "night" ? "切换" : "确定"}])
        .concat([{button: "B", label: gameOverlay ? "返回游戏" : "关闭"}])
    // Focus order; 回到主页 and 结束游戏 only over a game, volume only where the panel can set it.
    readonly property var quickOrder: ["wifi", "monitor", "night", "brightness", "volume", "home", "tasks", "end"]
    readonly property string quickId: quickOrder[quickIndex] || ""
    property int quickTile: 1
    property bool quickAdjusting: false
    readonly property string activeTitle: {
        const task = applications ? applications.tasks.find(function(entry) { return entry.foreground }) : null
        const game = games.find(function(entry) { return entry.id === activeApplication })
        return task ? task.title : game ? game.title : activeApplication
    }
    function quickAvailable(id) {
        if (id === "volume") return !hardware
        if (id === "brightness") return !hardware || (device.controls && device.info.brightnessPercent >= 0)
        if (id === "home" || id === "end") return gameOverlay
        return true
    }
    function quickRow(id) { const index = quickOrder.indexOf(id); return index < 3 ? 0 : index - 2 }
    function quickTileOn(id) {
        return id === "wifi" ? wifiSignal >= 0 || (network !== null && network.profiles.some(function(profile) { return profile.active }))
            : id === "monitor" ? store.monitor : nightActive
    }
    function quickLevel(id) { return id === "volume" ? (hardware ? -1 : store.volume) : hardware ? device.info.brightnessPercent : store.brightness }
    function openQuick() { quickTile = 1; quickIndex = quickAvailable("brightness") ? 3 : 1; quickAdjusting = false; quickOpen = true }
    function quickMove(step) {
        for (let row = quickRow(quickId) + step; row >= 0 && row <= 5; row += step) {
            const id = row === 0 ? quickOrder[quickTile] : quickOrder[row + 2]
            if (quickAvailable(id)) { quickIndex = quickOrder.indexOf(id); return }
        }
    }
    function quickActivate(id) {
        quickIndex = quickOrder.indexOf(id); root.forceActiveFocus()
        if (id === "monitor") store.adjust("monitor", 1)
        else if (id === "night") store.choose("night", nightActive ? 0 : 1)
        else if (id === "wifi") {
            if (gameOverlay) notify("请回到桌面，在设置 › 网络中管理 Wi-Fi")
            else if (leaveQuick()) { session = false; changePage(2); settingsView.openCategory(0) }
        } else if (id === "home") { if (leaveQuick()) backgroundRequested(false) }
        else if (id === "tasks") { if (leaveQuick()) backgroundRequested(true) }
        else if (id === "end") gameExitChoice.present(quickPanel, ["取消", "结束游戏"], 0, "结束当前游戏？")
    }
    readonly property var focusedEntry: page < 2 && !dockFocused ? games[selected] || null : null
    readonly property var focusedTask: focusedEntry ? entryTask(focusedEntry) : null
    readonly property string activateLabel: focusedTask ? "继续" : focusedEntry && focusedEntry.route ? "打开" : "开始"
    // §7.6: the hint bar comes from declared actions; Select appears only on the home page, B never
    // there, and plain up/down moves are not hinted.
    readonly property var pageExit: page === 0 ? [{button: "Select", label: "快捷面板"}] : [{button: "B", label: "返回"}]
    readonly property var cardHints: !focusedEntry ? [{button: "A", label: "打开"}]
        : (focusedEntry.reason ? [] : [{button: "A", label: activateLabel}])
            .concat([{button: "X", label: selectedFavorite ? "取消收藏" : "收藏"}, {button: "Start", label: "选项"}])
    readonly property var controlHints: toolOpen && toolView.item ? toolView.item.hints
        : streamingOpen ? streamingView.hints
        : session ? [{button: "dpad", label: "移动"}, {button: "B", label: "结束演示"}]
        : page === 2 ? settingsView.hints
        : page === 3 ? (builtinTools[toolsIndex] && !builtinTools[toolsIndex].reason ? [{button: "A", label: "打开"}] : []).concat(pageExit)
        : page === 1 ? (libraryEntries.length ? cardHints : []).concat([{button: "Y", label: "搜索"}]).concat(pageExit)
        : cardHints.concat(pageExit)
    readonly property string controlContext: toolOpen || streamingOpen || session || page !== 1 ? ""
        : (libraryQuery ? "“" + libraryQuery + "” · " : "") + libraryEntries.length + " 项"
    readonly property string pageTitle: toolOpen ? (portCatalogOpen ? "PortMaster 目录" : ({neo: "Neo 模拟器", ports: "PortMaster", usb: "USB 手柄"})[toolRoute] || "")
        : streamingOpen ? "串流" : session ? "" : ["", "游戏库", "设置", "工具"][page]
    // §8 entries: manifest items plus installed built-in apps, the built-in apps alone, or the
    // labelled demos. Tools sit behind the dock's 工具 and settings behind 设置.
    readonly property var games: customApplications
        ? applications.items.map(function(item) { return Object.assign({}, item, {reason: item.supported === false ? "尚未适配" : ""}) })
            .concat(builtinApps.filter(function(entry) { return entry.route === "streaming" ? root.streaming !== null : !entry.reason }))
        : tools ? builtinApps : demoGames
    readonly property var builtinApps: [
        {id: "builtin.moonlight", title: "Moonlight", detail: "电脑游戏串流", palette: 2, route: "streaming", icon: "streaming"},
        {id: "builtin.browser", title: "Jume Browser", detail: "网页浏览",
            palette: 2, route: "browser", icon: "globe", plain: true, reason: browserAvailable ? "" : "尚未安装"},
        {id: "builtin.files", title: "文件管理器", detail: "浏览和管理文件",
            tint: Ui.Theme.focus, route: "files", icon: "folder", plain: true, reason: filesAvailable ? "" : "尚未安装"}
    ]
    readonly property var builtinTools: [
        {id: "builtin.neo", title: "Neo 模拟器", detail: "Neo Geo 游戏", route: "neo", icon: "cartridge"},
        {id: "builtin.ports", title: "PortMaster", detail: "移植游戏", route: "ports", icon: "ports"},
        {id: "builtin.usb", title: "USB 手柄", detail: "把掌机当作电脑手柄", route: "usb", icon: "usb"},
        {id: "builtin.terminal", title: "终端", detail: "需要连接 USB 键盘", route: "terminal", icon: "terminal"},
        {id: "builtin.text", title: "文本编辑器", detail: "", route: "text", icon: "document"},
        {id: "builtin.transfer", title: "文件传输", detail: "用手机扫码传文件", route: "transfer", icon: "folder"}
    ].map(function(entry) {
        entry.reason = ["neo", "ports", "usb"].includes(entry.route) ? (tools ? "" : "工具服务未启动")
            : entry.route === "terminal" ? (terminalAvailable ? "" : "尚未安装") : (filesAvailable ? "" : "尚未安装")
        return entry
    })
    readonly property var dockItems: [
        {id: "library", label: "游戏库", icon: "grid"}, {id: "streaming", label: "串流", icon: "streaming"},
        {id: "files", label: "文件", icon: "folder"}, {id: "tools", label: "工具", icon: "briefcase"},
        {id: "settings", label: "设置", icon: "settings"}, {id: "power", label: "电源", icon: "power"}
    ]
    // Home row: recent entries, newest first, then favorites, topped up to five with the first
    // available entries so a new device still shows a row.
    readonly property var homeEntries: {
        const result = []
        const add = function(index) { if (index >= 0 && result.indexOf(index) < 0 && result.length < 12) result.push(index) }
        store.recentApplications.forEach(function(recent) { add(games.findIndex(function(game) { return game.id === recent.id })) })
        games.forEach(function(game, index) { if (entryFavorite(index)) add(index) })
        games.forEach(function(game, index) { if (!game.reason && result.length < 5) add(index) })
        return result
    }
    readonly property var libraryFilters: {
        const systems = []
        games.forEach(function(game) { if (game.system && systems.indexOf(game.system) < 0) systems.push(game.system) })
        return ["全部", "收藏", "最近"].concat(systems).concat(games.some(function(game) { return !game.system }) ? ["应用"] : [])
    }
    readonly property var libraryEntries: {
        const filter = libraryFilters[Math.min(libraryFilter, libraryFilters.length - 1)]
        const query = libraryQuery.toLowerCase()
        const matches = function(game, index) {
            return (!query || game.title.toLowerCase().indexOf(query) >= 0)
                && (filter === "全部" || filter === "最近" || (filter === "收藏" && entryFavorite(index)) || (filter === "应用" && !game.system) || game.system === filter)
        }
        if (filter === "最近") return store.recentApplications.map(function(recent) { return games.findIndex(function(game) { return game.id === recent.id }) })
            .filter(function(index) { return index >= 0 && matches(games[index], index) })
        const result = []
        games.forEach(function(game, index) { if (matches(game, index)) result.push(index) })
        return result
    }
    function entryFavorite(index) {
        const game = games[index]
        if (!game) return false
        return (applications || tools) ? store.applicationFavorites.indexOf(game.id) >= 0 : store.favorites.indexOf(index) >= 0
    }
    function entryTask(game) {
        if (!applications || !game || !game.id) return null
        return applications.tasks.find(function(task) { return task.id === game.id }) || null
    }
    function entryBadge(game) {
        const task = entryTask(game)
        return !task ? "" : task.paused ? "已暂停" : "运行中"
    }
    // Stable color per entry: an explicit tint or palette slot, else a hash of the ID.
    function entryColor(index) {
        const game = games[index]
        if (!game) return Ui.Theme.cardColor(0)
        if (game.tint) return game.tint
        if (game.palette !== undefined) return Ui.Theme.cardColor(game.palette)
        return hashColor(game.id || game.title)
    }
    function hashColor(key) {
        let hash = 0
        for (let i = 0; i < key.length; ++i) hash = (hash * 131 + key.charCodeAt(i)) % 2147483647
        return Ui.Theme.cardColor(hash)
    }
    // Task cards outside the library (e.g. built-in tools) still get their stable color.
    function entryColorById(id) {
        const index = games.findIndex(function(game) { return game.id === id })
        return index >= 0 ? entryColor(index) : hashColor(id || "")
    }
    function entryCaption(game) {
        const task = entryTask(game)
        const recent = store.recentApplications.find(function(entry) { return entry.id === game.id })
        if (task) return task.paused ? "已暂停 · 从上次的位置继续" : "运行中 · 在后台继续"
        return [game.system || game.detail, recent ? "上次游玩 " + playedText(recent.playedAt) : ""].filter(function(part) { return !!part }).join(" · ")
    }
    function playedText(seconds) {
        const day = function(date) { return Math.floor(new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime() / 86400000) }
        const days = day(now) - day(new Date(seconds * 1000))
        return days <= 0 ? "今天" : days === 1 ? "昨天" : days < 30 ? days + " 天前" : Qt.formatDate(new Date(seconds * 1000), "M月d日")
    }
    // The row and grid positions follow `selected`, so tests and remote state can set either.
    function syncSelected() {
        selected = page === 1 ? (libraryEntries[libraryIndex] !== undefined ? libraryEntries[libraryIndex] : -1)
            : page === 0 && !dockFocused && homeIndex < homeEntries.length ? homeEntries[homeIndex] : -1
    }
    onSelectedChanged: {
        if (page === 0 && homeEntries.indexOf(selected) >= 0) { homeIndex = homeEntries.indexOf(selected); dockFocused = false }
        else if (page === 1 && libraryEntries.indexOf(selected) >= 0) libraryIndex = libraryEntries.indexOf(selected)
    }
    onHomeEntriesChanged: if (page === 0 && !dockFocused) {
        const kept = homeEntries.indexOf(selected)
        homeIndex = kept >= 0 ? kept : Math.min(homeIndex, homeEntries.length)
        syncSelected()
    }
    onLibraryEntriesChanged: if (page === 1) { libraryIndex = Math.max(0, Math.min(libraryIndex, libraryEntries.length - 1)); syncSelected() }
    function switchLibraryFilter(index) {
        if (index < 0 || index >= libraryFilters.length || index === libraryFilter) return
        const positions = Object.assign({}, libraryPositions)
        positions[libraryFilters[libraryFilter]] = libraryIndex
        libraryPositions = positions
        libraryFilter = index
        libraryIndex = Math.min(positions[libraryFilters[index]] || 0, Math.max(0, libraryEntries.length - 1))
        syncSelected()
    }
    function openDock(index) {
        const id = dockItems[index].id
        if (id === "library" || id === "settings" || id === "tools") { changePage(["", "library", "settings", "tools"].indexOf(id)); return }
        if (id === "power") { openPowerMenu(); return }
        if (id === "files") {
            if (!filesAvailable) notify("文件管理器尚未安装")
            else { recordLaunch("builtin.files"); filesRequested(false) }
            return
        }
        if (streaming) { showScene("streaming"); return }
        const moonlight = games.findIndex(function(game) { return game.route === "streaming" || game.id === "moonlight" || game.title === "Moonlight" })
        if (moonlight < 0) { notify("串流尚未配置"); return }
        selected = moonlight; activateSelected()
    }
    // §8 power menu: names the background apps; restart and power-off ask once more.
    function openPowerMenu() {
        powerMenu.present(applications ? applications.tasks.map(function(task) { return task.title }) : [])
    }
    function powerChosen(id) {
        if (id === "screenOff") { blankScreen(); return }
        if (!store.save()) return
        if (!device.requestPower(id)) notify(device.error)
    }
    function openToolEntry(index) {
        const entry = builtinTools[index]
        if (!entry) return
        if (entry.reason) { notify(entry.reason); return }
        if (["neo", "ports", "usb"].includes(entry.route)) { openTool(entry.route); return }
        recordLaunch(entry.id)
        if (entry.route === "terminal") terminalRequested()
        else if (entry.route === "transfer") transferRequested()
        else filesRequested(true)
    }
    function recordLaunch(id) { if (id && store.recordRecent(id)) store.save() }
    function openTool(kind) {
        if (!tools || !["neo", "ports", "usb"].includes(kind) || !tools.save()) return
        streamingOpen = false; session = false; toolRoute = kind; clearNotice(); tools.inspect(kind)
    }
    function closeTool() { if (tools && !tools.save()) return false; toolRoute = ""; clearNotice(); root.forceActiveFocus(); return true }
    readonly property var demoGames: [
        {title: "Moonlight", detail: "电脑游戏串流", palette: 2, icon: "streaming", route: "streaming"},
        {title: "像素远征", detail: "示例游戏", system: "街机", palette: 0},
        {title: "夜航", detail: "示例游戏", system: "Game Gear", palette: 1},
        {title: "方块花园", detail: "示例游戏", system: "Game Boy", palette: 4},
        {title: "星际快线", detail: "示例游戏", system: "街机", palette: 3},
        {title: "海岛来信", detail: "示例游戏", system: "掌机", palette: 1}
    ]
    function showScene(name) {
        toolRoute = ""
        if (["neo", "ports", "usb"].includes(name)) {
            page = 3; toolsIndex = Math.max(0, builtinTools.findIndex(function(entry) { return entry.route === name }))
            openTool(name); return
        }
        streamingOpen = name === "streaming"
        if (streamingOpen && streaming) streaming.refresh()
        page = name === "library" ? 1 : name === "tools" ? 3 : (["settings", "about", "controller", "power", "input"].indexOf(name) >= 0 ? 2 : 0)
        syncSelected()
        session = name === "session"
        if (name === "quick") openQuick(); else quickOpen = false
        if (page === 2) settingsView.enter()
        if (name === "about") settingsView.openCategory(7, false, settingsView.aboutRow)
        if (name === "performance" && !store.monitor) store.adjust("monitor", 1)
        if (name === "controller") settingsView.startTester()
        if (name === "power") settingsView.openCategory(4)
        if (name === "input") { settingsView.openCategory(3, false, 1); openEditor() }
    }
    function changePage(value) {
        if (externalSession || choicesOpen) return
        if (tools && !tools.save()) return
        toolRoute = ""
        if (page === 2 && !store.save()) return
        clearNotice()
        page = Math.max(0, Math.min(3, value)); syncSelected()
        settingsView.enter()
        root.forceActiveFocus()
    }
    // Notices are information unless `success` (the only kind with a check mark); no trailing period.
    property bool noticeSuccess: false
    function notify(text, success) { notice = String(text).replace(/[。.]+$/, ""); noticeSuccess = !!success; noticeTimer.restart() }
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
        } else if (purpose === "librarySearch") {
            libraryQuery = value.trim(); libraryIndex = 0; syncSelected()
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
        if (games[selected].reason === "尚未适配") { notify("尚未适配，无法启动"); return }
        if (games[selected].route === "streaming" && streaming) { showScene("streaming"); clearNotice(); return }
        if (tools && games[selected].route) {
            const route = games[selected].route
            if (["files", "text", "transfer"].includes(route)) {
                if (!filesAvailable) { notify("文件管理器尚未安装"); return }
                recordLaunch(games[selected].id)
                if (route === "transfer") transferRequested()
                else filesRequested(route === "text")
                return
            }
            if (route === "terminal") {
                if (!terminalAvailable) { notify("终端尚未安装"); return }
                terminalRequested(); return
            }
            if (route === "browser") {
                if (!browserAvailable) { notify("Jume Browser 尚未安装"); return }
                recordLaunch(games[selected].id); browserRequested(); return
            }
            if (["neo", "ports", "usb"].includes(route)) openTool(route)
            else showScene(route)
            return
        }
        if (customApplications) {
            const id = games[selected].id
            if (store.save()) { clearNotice(); if (applications.launch(selected)) recordLaunch(id) }
            return
        }
        session = true; sessionMoves = 0; avatarX = 480; avatarY = 350
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
        else if (action === "testerExit") settingsView.leaveTester()
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
        if (quickOpen && (action === "left" || action === "right")) { quickAdjusting = false; return }
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
    // §8 GameOptions: start, favorite (X), per-game controls and saves (disabled until G2 lands)
    // and removal from 最近; built-in apps skip the per-game rows.
    function cardOptions() {
        const game = games[selected]
        if (!game) return []
        const items = [{id: "start", label: focusedTask ? "继续" : game.route ? "打开" : "开始游戏", icon: "play", reason: game.reason || ""},
                       {id: "favorite", label: selectedFavorite ? "取消收藏" : "收藏", icon: "star", button: "X"}]
        if (!game.route) items.push({id: "controls", label: "按键与画面", icon: "gamepad", reason: "暂不支持"},
                                    {id: "saves", label: "存档管理", icon: "save", reason: "暂不支持"})
        if (store.recentApplications.some(function(recent) { return recent.id === game.id }))
            items.push({id: "forget", label: "从“最近”中移除", icon: "history-off"})
        return items
    }
    function openOptions() {
        let owner = null, title = "", items = [], header = null
        if (tasksVisible && taskPage.item) {
            owner = taskPage.item; items = owner.optionItems(); title = owner.currentTask ? owner.currentTask.title : ""
        } else if (toolOpen && toolView.item) {
            owner = toolView.item; items = owner.optionItems(); title = owner.optionTitle
        } else if (!streamingOpen && !session && page === 2 && settingsView.optionItems().length) {
            owner = settingsView; items = owner.optionItems(); title = owner.optionTitle
        } else if (!streamingOpen && !session && page < 2 && focusedEntry) {
            owner = root; items = cardOptions(); title = focusedEntry.title
            header = {subtitle: [focusedEntry.system || focusedEntry.detail, focusedEntry.core].filter(function(part) { return !!part }).join(" · "),
                      color: entryColor(selected), icon: focusedEntry.icon || "", plain: !!focusedEntry.plain}
        }
        if (owner && optionsMenu.present(title, items, header)) optionsOwner = owner
    }
    function runOption(id) {
        if (id === "start") activateSelected()
        else if (id === "favorite") toggleFavorite()
        else if (id === "forget" && games[selected] && store.removeRecent(games[selected].id)) store.save()
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
        else if (keyboard && keyboard.candidateAction(action)) return
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
        else if ((action === "up" || action === "down") && keyboard && keyboard.navigateVertical(action)) return
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
        if (powerMenu.open) { powerMenu.dispatch(action, repeated); return }
        if (editing) { editorDispatch(action, repeated); return }
        if (repeated && action === "back") return
        if (quickOpen) {
            root.forceActiveFocus()
            if (action === "back" || action === "quick") leaveQuick()
            else if (action === "up" || action === "down") quickMove(action === "down" ? 1 : -1)
            else if (action === "left" || action === "right") {
                const step = action === "right" ? 1 : -1
                if (quickRow(quickId) === 0) { quickTile = Math.max(0, Math.min(2, quickTile + step)); quickIndex = quickTile }
                else if (quickId === "brightness" || quickId === "volume") { quickAdjusting = true; adjustSetting(quickId === "volume" ? 0 : 1, step, repeated) }
            } else if (action === "accept" && !repeated && quickId !== "brightness" && quickId !== "volume") quickActivate(quickId)
            return
        }
        if (toolOpen && toolView.item && toolView.item.choiceOpen) { toolView.item.dispatch(action, repeated); return }
        if (streamingOpen) { streamingView.dispatch(action, repeated); return }
        if (settingsView.choiceOpen) { settingsView.dispatch(action, repeated); return }
        root.forceActiveFocus()
        if (action === "quick") { openQuick(); return }
        if (action === "options") { openOptions(); return }
        if (toolOpen) {
            if (action === "home") { if (closeTool()) { dockFocused = false; homeIndex = 0; changePage(0) } }
            else if (toolView.item && !toolView.item.dispatch(action, repeated)) closeTool()
            return
        }
        // Back home (Select+Start): the focus returns to the most recent card.
        if (action === "home") {
            if (!store.save()) return
            session = false; dockFocused = false; homeIndex = 0; changePage(0); return
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
        if (page === 3) {
            if (action === "back") changePage(0)
            else if (action === "up") toolsIndex = Math.max(0, toolsIndex - 1)
            else if (action === "down") toolsIndex = Math.min(builtinTools.length - 1, toolsIndex + 1)
            else if (action === "pageUp" || action === "pageDown") toolsIndex = action === "pageUp" ? 0 : builtinTools.length - 1
            else if (action === "accept") openToolEntry(toolsIndex)
            return
        }
        if (page === 1) { libraryDispatch(action); return }
        // Home (§7.4): the card row and the dock; B does nothing.
        if (dockFocused) {
            if (action === "left") dockIndex = Math.max(0, dockIndex - 1)
            else if (action === "right") dockIndex = Math.min(dockItems.length - 1, dockIndex + 1)
            else if (action === "up") { dockFocused = false; syncSelected() }
            else if (action === "accept") openDock(dockIndex)
            return
        }
        if (action === "left" || action === "right") {
            homeIndex = Math.max(0, Math.min(homeEntries.length, homeIndex + (action === "right" ? 1 : -1))); syncSelected()
        } else if (action === "down") { dockFocused = true; syncSelected() }
        else if (action === "accept") { if (homeIndex === homeEntries.length) changePage(1); else activateSelected() }
        else if (action === "itemAction" && focusedEntry) toggleFavorite()
    }
    // Library grid (§7.4): no wrap at the edges; L1/R1 filters, L2/R2 a screen of two rows, Y search.
    function libraryDispatch(action) {
        const columns = Ui.Theme.gridColumns, count = libraryEntries.length
        if (action === "back") { if (libraryQuery) { libraryQuery = ""; libraryIndex = 0; syncSelected() } else changePage(0); return }
        if (action === "prevSection" || action === "nextSection") { switchLibraryFilter(libraryFilter + (action === "nextSection" ? 1 : -1)); return }
        if (action === "pageAction") { openTextEditor("搜索游戏", libraryQuery, "librarySearch"); return }
        if (count === 0) return
        let index = libraryIndex
        if (action === "left") { if (index % columns > 0) index-- }
        else if (action === "right") { if (index % columns < columns - 1 && index < count - 1) index++ }
        else if (action === "up") { if (index >= columns) index -= columns }
        else if (action === "down") { if (Math.floor(index / columns) < Math.floor((count - 1) / columns)) index = Math.min(count - 1, index + columns) }
        else if (action === "pageUp" || action === "pageDown") index = Math.max(0, Math.min(count - 1, index + (action === "pageDown" ? 2 : -2) * columns))
        else if (action === "accept") { activateSelected(); return }
        else if (action === "itemAction") { toggleFavorite(); return }
        libraryIndex = index; syncSelected()
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
                applications: root.applications; fontScale: root.fontScale; reducedMotion: root.motionReduced
                holdProgress: root.holdAction === "taskForce" ? root.holdRing : -1
                wifiSignal: root.wifiSignal; batteryPercent: root.batteryPercent; clock: root.clockText
                charging: root.batteryState === "charging" || root.batteryState === "full"
                colorFor: function(id) { return root.entryColorById(id) }
                entryFor: function(id) { return root.games.find(function(game) { return game.id === id }) || null }
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
        Ui.PowerMenu {
            id: powerMenu; objectName: "powerMenuLayer"; anchors.fill: parent; z: 102
            fontScale: root.fontScale; reducedMotion: root.store.reducedMotion
            readonly property string deviceReason: !root.hardware ? "预览中不可用" : !root.device.controls ? "暂不可用" : ""
            reasons: ({reboot: deviceReason, poweroff: deviceReason})
            onChosen: function(id) { root.powerChosen(id) }
            onOpenChanged: if (!open) root.forceActiveFocus()
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
            anchors.fill: parent
            Item {
            anchors.fill: parent; visible: !root.gameOverlay
            Ui.TopBar {
                objectName: "topBar"
                x: Ui.Theme.margin; width: Ui.Theme.contentWidth; fontScale: root.fontScale
                title: root.pageTitle; note: root.hardware ? "" : "本地界面预览"
                wifiSignal: root.wifiSignal; batteryPercent: root.batteryPercent
                charging: root.batteryState === "charging" || root.batteryState === "full"
                clock: root.clockText
            }
            }
            Ui.Page {
                id: pageContent; objectName: "pageContent"
                anchors.fill: parent; enabled: !root.externalSession; visible: !root.gameOverlay
                route: root.toolOpen ? root.toolRoute : root.streamingOpen ? "streaming" : String(root.page)
                reducedMotion: root.motionReduced
            HomeView {
                id: homeView; objectName: "homeView"
                anchors.fill: parent; visible: !root.toolOpen && !root.streamingOpen && !root.session && root.page === 0
                shell: root; entries: root.homeEntries; index: root.homeIndex; dockFocused: root.dockFocused; dockIndex: root.dockIndex
                ringVisible: !root.overlayOpen; fontScale: root.fontScale; reducedMotion: root.motionReduced
                onIndexChanged: if (root.homeIndex !== index) { root.homeIndex = index; root.syncSelected() }
                onDockFocusedChanged: if (root.dockFocused !== dockFocused) { root.dockFocused = dockFocused; root.syncSelected() }
                onDockIndexChanged: root.dockIndex = dockIndex
                onCardActivated: function(position) { root.forceActiveFocus(); root.dispatch("accept", false) }
                onDockActivated: function(position) { root.forceActiveFocus(); root.openDock(position) }
            }
            LibraryView {
                id: libraryView; objectName: "libraryView"
                anchors.fill: parent; visible: !root.toolOpen && !root.streamingOpen && !root.session && root.page === 1
                shell: root; entries: root.libraryEntries; filters: root.libraryFilters; filter: root.libraryFilter; index: root.libraryIndex
                ringVisible: !root.overlayOpen; fontScale: root.fontScale; reducedMotion: root.motionReduced
                onIndexChanged: if (root.libraryIndex !== index) { root.libraryIndex = index; root.syncSelected() }
                onCardActivated: function(position) { root.forceActiveFocus(); root.activateSelected() }
                onFilterActivated: function(position) { root.forceActiveFocus(); root.switchLibraryFilter(position) }
            }
            ToolsView {
                id: toolsView; objectName: "toolsView"
                x: Ui.Theme.margin; y: Ui.Theme.pageTop; width: Ui.Theme.contentWidth; height: Ui.Theme.pageHeight
                visible: !root.toolOpen && !root.streamingOpen && !root.session && root.page === 3
                items: root.builtinTools; index: root.toolsIndex
                ringVisible: !root.overlayOpen; fontScale: root.fontScale; reducedMotion: root.motionReduced
                onIndexChanged: root.toolsIndex = index
                onActivated: function(position) { root.forceActiveFocus(); root.openToolEntry(position) }
            }
            Loader {
                id: toolView; objectName: "toolView"; x: Ui.Theme.margin; y: Ui.Theme.pageTop; width: Ui.Theme.contentWidth; height: Ui.Theme.pageHeight
                active: root.toolOpen && root.tools !== null; visible: active
                sourceComponent: ToolPage {
                    tools: root.tools; kind: root.toolRoute
                    navigationActive: root.windowVisible && !root.overlayOpen && !root.dimmed
                    onBackRequested: root.closeTool()
                    onSearchRequested: function(value) { root.openTextEditor("搜索游戏", value, "portSearch") }
                }
            }
            SettingsView {
                id: settingsView; x: Ui.Theme.margin; y: Ui.Theme.pageTop; width: Ui.Theme.contentWidth; height: Ui.Theme.pageHeight
                testerHold: root.holdAction === "testerExit" ? root.holdRing : -1
                navigationActive: root.windowVisible && !root.overlayOpen && !root.dimmed
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
                Ui.Label { x: Ui.Theme.margin; y: sessionTitle.y + sessionTitle.height; text: "交互演示 · 方向键移动方块，Select 快捷面板"; role: "caption" }
                Rectangle {
                    x: Ui.Theme.margin; y: 219; width: Ui.Theme.contentWidth; height: 426; radius: 24; color: Ui.Theme.surface; border.color: Ui.Theme.outline
                    Repeater {
                        model: 8
                        Rectangle { required property int index; x: 38 + index * 116; y: 0; width: 1; height: 426; color: Ui.Theme.outline }
                    }
                    Rectangle { x: 0; y: 213; width: parent.width; height: 1; color: Ui.Theme.outline }
                    Ui.Label { x: 28; y: 360; text: "未运行游戏或串流"; role: "caption" }
                }
                Rectangle { x: root.avatarX; y: root.avatarY; width: 38; height: 38; radius: 10; color: Ui.Theme.accent }
            }
            Loader {
                id: streamingView; x: Ui.Theme.margin; y: Ui.Theme.pageTop; width: Ui.Theme.contentWidth; height: Ui.Theme.pageHeight
                visible: root.streamingOpen && root.streaming !== null
                active: root.streaming !== null
                readonly property var hints: item ? item.hints : []
                function dispatch(action, repeated) { if (item) item.dispatch(action, repeated) }
                sourceComponent: StreamingView {
                    manager: root.streaming; store: root.store
                    navigationActive: root.windowVisible && !root.overlayOpen && !root.dimmed
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
                fontScale: root.fontScale; hints: root.quickHints
                enabled: root.quickOpen
                visible: root.quickOpen || x < Ui.Theme.canvasWidth
                Behavior on x { Ui.Motion { curve: "emphasized"; duration: Ui.Theme.reducedMotion ? 0 : Ui.Theme.sheetEnterDuration } }
                header: Item {
                    id: quickHeader
                    // A long title or large font moves battery and time below the title instead of cutting it.
                    readonly property bool stacked: quickTitle.implicitWidth + quickChip.width + quickStatus.implicitWidth + 2 * Ui.Theme.space12 > width
                    width: parent ? parent.width : 0
                    height: stacked ? quickTitle.implicitHeight + Ui.Theme.space4 + quickStatus.implicitHeight : Math.max(quickTitle.implicitHeight, quickStatus.implicitHeight)
                    Ui.Label {
                        id: quickTitle; objectName: "quickTitle"; y: quickHeader.stacked ? 0 : (quickHeader.height - height) / 2
                        width: Math.min(implicitWidth, parent.width - quickChip.width - Ui.Theme.space12)
                        role: "headline"; fontScale: root.fontScale; text: root.gameOverlay ? root.activeTitle : "Jume"
                    }
                    Rectangle {
                        id: quickChip
                        x: quickTitle.width + Ui.Theme.space12; anchors.verticalCenter: quickTitle.verticalCenter
                        width: chipLabel.implicitWidth + 2 * Ui.Theme.space12; height: chipLabel.implicitHeight + Ui.Theme.space4; radius: height / 2
                        color: Ui.Theme.accentSoft
                        Ui.Label { id: chipLabel; anchors.centerIn: parent; role: "micro"; fontScale: root.fontScale; color: Ui.Theme.accentInk; elide: Text.ElideNone; text: root.gameOverlay ? "运行中" : "桌面" }
                    }
                    Ui.Label {
                        id: quickStatus
                        x: quickHeader.stacked ? 0 : parent.width - width; y: quickHeader.stacked ? quickTitle.height + Ui.Theme.space4 : (quickHeader.height - height) / 2
                        role: "label"; tabular: true; fontScale: root.fontScale; elide: Text.ElideNone
                        text: (root.batteryPercent >= 0 ? root.batteryPercent + "%  " : "") + root.clockText
                    }
                }
                QuickPanelView {
                    width: parent.width; shell: root; current: root.quickOpen ? root.quickId : ""; fontScale: root.fontScale
                }
            }
        }
        Item {
            x: Ui.Theme.margin; y: Ui.Theme.canvasHeight - Ui.Theme.hintBarHeight; width: Ui.Theme.contentWidth; height: Ui.Theme.hintBarHeight
            visible: !root.editing && !root.gameOverlay && !root.quickOpen
            Rectangle { width: parent.width; height: 1; color: Ui.Theme.outline }
            Ui.HintBar { objectName: "footerHints"; anchors.verticalCenter: parent.verticalCenter; width: parent.width; actions: root.controlHints; context: root.controlContext; fontScale: root.fontScale }
        }
        // §8 keyboard sheet over the current page: the title, a 64-high field without a ring
        // (focus lives on the keys), Qt's keyboard and the sheet's own hint bar.
        Item {
            anchors.fill: parent; visible: root.editing
            Rectangle { anchors.fill: parent; color: Ui.Theme.scrim }
            MouseArea { anchors.fill: parent }
            Rectangle {
                id: editorSheet; objectName: "editorSheet"
                y: parent.height - height; width: parent.width; height: editorColumn.y + editorColumn.height + Ui.Theme.space16 + Ui.Theme.hintBarHeight
                radius: Ui.Theme.radiusPanel; color: Ui.Theme.surface
                Ui.Shadow {}
                Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: parent.radius; color: parent.color }
                Column {
                    id: editorColumn
                    y: Ui.Theme.space32; width: parent.width; spacing: Ui.Theme.space16
                    Ui.Label { x: Ui.Theme.margin; width: Ui.Theme.contentWidth; text: root.editLabel; color: Ui.Theme.text; role: "headline"; fontScale: root.fontScale }
                    Ui.Label {
                        x: Ui.Theme.margin; width: Ui.Theme.contentWidth; wrapMode: Text.Wrap; role: "caption"; fontScale: root.fontScale
                        visible: text !== ""
                        text: root.testInputVisible ? "自动化输入测试允许截图，请勿填写密码" : root.editPurpose === "wifiPassword" ? "完成后连接" : ""
                    }
                    Item {
                        x: Ui.Theme.margin; width: Ui.Theme.contentWidth; height: Ui.Theme.editorFieldHeight
                        Ui.TextField {
                            id: inputField; objectName: "inputField"
                            width: parent.width - (doneButton.visible ? doneButton.width + Ui.Theme.space16 : 0); height: parent.height
                            focusRing: false; leftPadding: searchIcon.visible ? Ui.Theme.space24 + Ui.Theme.iconSize + Ui.Theme.space12 : Ui.Theme.space24
                            fontScale: root.fontScale; maximumLength: root.editPurpose === "wifiPassword" ? 64 : root.editPurpose === "portSearch" ? 80 : 128
                            echoMode: root.editPurpose === "wifiPassword" ? TextInput.Password : TextInput.Normal
                            inputMethodHints: Qt.ImhNoPredictiveText | Qt.ImhSensitiveData | (root.editPurpose === "wifiPassword" ? Qt.ImhHiddenText | Qt.ImhLatinOnly | Qt.ImhNoAutoUppercase : 0)
                            Accessible.name: root.editLabel
                            Keys.onEscapePressed: root.closeEditor()
                            Keys.onReturnPressed: root.finishEditor()
                            Ui.Icon {
                                id: searchIcon; x: Ui.Theme.space24; anchors.verticalCenter: parent.verticalCenter
                                visible: root.editPurpose === "librarySearch" || root.editPurpose === "portSearch"; name: "search"
                            }
                        }
                        // Without the on-screen keyboard (a USB keyboard or the desktop preview) a button finishes.
                        Ui.Button {
                            id: doneButton; anchors.right: parent.right; width: 152; height: parent.height; visible: !root.keyboardEnabled
                            text: "完成"; primary: true; focusPolicy: Qt.NoFocus; Accessible.name: "完成输入"; onClicked: root.finishEditor()
                        }
                    }
                    Ui.Label { x: Ui.Theme.margin; visible: virtualKeyboard.status === Loader.Error; text: "虚拟键盘模块不可用；仍可使用实体键盘。"; color: Ui.Theme.danger; role: "caption"; fontScale: root.fontScale }
                    Loader {
                        id: virtualKeyboard; objectName: "virtualKeyboard"
                        active: root.keyboardEnabled && root.editing
                        source: "KeyboardPanel.qml"
                        width: parent.width; height: item ? (item as Item).implicitHeight : 0
                    }
                }
                Item {
                    x: Ui.Theme.margin; y: parent.height - Ui.Theme.hintBarHeight; width: Ui.Theme.contentWidth; height: Ui.Theme.hintBarHeight
                    Rectangle { width: parent.width; height: 1; color: Ui.Theme.outline }
                    Ui.HintBar {
                        objectName: "editorHints"; anchors.verticalCenter: parent.verticalCenter; width: parent.width; fontScale: root.fontScale
                        readonly property bool composing: !!virtualKeyboard.item && !!virtualKeyboard.item.composing
                        actions: root.keyboardEnabled && composing
                            ? [{button: "L1+R1", label: "翻页"}, {button: "Y", label: "上屏"}, {button: "A", label: "输入"}]
                            : root.keyboardEnabled
                            ? [{button: "L1+R1", label: "移动光标"}, {button: "Select", label: "取消", leading: false}, {button: "A", label: "输入"}]
                            : [{button: "A", label: "完成"}, {button: "B", label: "取消"}]
                    }
                }
            }
            Binding { target: virtualKeyboard.item; property: "reducedMotion"; value: root.store.reducedMotion; when: virtualKeyboard.status === Loader.Ready }
            // The keyboard reopens on the key last used.
            Binding { target: virtualKeyboard.item; property: "lastKey"; value: root.keyboardLastKey; when: virtualKeyboard.status === Loader.Ready }
            Connections {
                target: virtualKeyboard.status === Loader.Ready ? virtualKeyboard.item : null
                function onKeyFocused(text) { root.keyboardLastKey = text }
            }
        }
        PerformancePanel {
            id: performancePanel
            objectName: "performancePanel"
            x: Ui.Theme.canvasWidth - Ui.Theme.perfPanelRight - width
            y: root.gameOverlay ? Ui.Theme.perfPanelTop : Ui.Theme.perfPanelDesktopTop
            metrics: root.metrics; device: root.device; fontScale: root.fontScale; detail: root.store.monitorDetail
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
            // Above an open sheet or dialog, 16 px clear of it; otherwise above the hint bar.
            readonly property real coverTop: root.editing ? editorSheet.y : optionsMenu.open ? optionsMenu.coverTop : powerMenu.open ? powerMenu.coverTop : -1
            y: coverTop >= 0 ? coverTop - height - Ui.Theme.space16 : root.quickOpen ? 340 : Ui.Theme.canvasHeight - Ui.Theme.hintBarHeight - height - Ui.Theme.space16
            maximumWidth: root.quickOpen ? 530 : Ui.Theme.contentWidth
            text: root.store.error || root.notice; error: root.store.error !== ""; success: !error && root.noticeSuccess; fontScale: root.fontScale
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
