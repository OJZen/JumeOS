pragma ComponentBehavior: Bound
import QtQuick
import "controls" as Ui

Item {
    id: settings
    objectName: "settingsView"
    required property var store
    required property var metrics
    required property var controller
    property var device: null
    property var network: null
    property var browserVersions: ({})
    readonly property bool hardware: device !== null && device.target
    property var choiceValues: []
    property string choiceKey: ""
    property int category: 0
    property int openedCategory: 0
    property int rowIndex: 0
    property bool sidebar: true
    property bool adjustingValue: false
    property bool navigationActive: true
    property bool tester: false
    // The shell's B-hold progress while the controller test runs (-1 before the ring shows).
    property real testerHold: -1
    // §7.3: L1/R1 return to the row each category had when it was left.
    property var lastRows: ({})
    readonly property real fontScale: store.fontPercent / 100
    readonly property bool choiceOpen: choices.visible
    readonly property bool detailReady: !sidebar && detailLoader.status === Loader.Ready
    // §8: eight categories; the old 12 merge as 显示 = 屏幕 + 字号 + 夜间 + 减少动态效果,
    // 控制器 = 摇杆测试 + 文字输入, 性能 = 浮窗 + 帧与串流 + CPU + 内存, 系统 = 系统信息 + 关于.
    readonly property var categories: ["网络", "显示", "声音", "控制器", "电源", "性能", "存储", "系统"]
    readonly property var categoryIcons: ["wifi", "display", "volume", "gamepad", "battery", "cpu", "storage", "info"]
    readonly property var categoryNotes: ["已连接与附近的 Wi-Fi", "亮度、自动息屏、夜间模式与字号", "音量与声音输出", "摇杆测试与文字输入",
        "变暗、息屏、电池、重启与关机", "性能浮窗、帧与串流、CPU 与内存", "分区与可用空间", "系统状态与关于"]
    readonly property var nightModes: ["off", "on", "auto"]
    readonly property var nightLabels: ["关闭", "开启", "跟随时间"]
    // Two panes from 900 wide (§1); narrower canvases show the categories and the detail in turn.
    readonly property bool twoPane: Ui.Theme.dualPane
    readonly property var row: rows[rowIndex] || null
    readonly property bool sliderRow: !sidebar && detailReady && !!row && valueIsAdjustable(row.key) && canActivate(row.key)
    readonly property string rowAction: !row ? "" : ["motion", "monitor"].indexOf(row.key) >= 0 ? "切换"
        : row.key === "storage" ? "刷新" : row.key === "tester" ? "开始测试" : row.key === "netActive" ? "详情"
        : row.key === "netPoint" ? "连接" : row.key === "netScan" ? "扫描" : choiceRow(row.key) ? "选择" : "打开"
    readonly property var hints: choices.visible ? choices.hints
        : sidebar ? [{button: "A", label: "进入"}, {button: "B", label: "返回"}]
        : tester ? [{button: "B", label: "按住退出", progress: testerHold}]
        : !detailReady ? [{button: "B", label: "返回分类"}]
        : (sliderRow ? [{button: "dpadH", label: "调整"}] : row && canActivate(row.key) ? [{button: "A", label: rowAction}] : [])
            .concat(row && row.key === "netActive" && canActivate("netDisconnect") ? [{button: "X", label: "断开"}] : [])
            .concat(openedCategory === 0 ? [{button: "Y", label: "刷新"}] : [])
            .concat(optionItems().length ? [{button: "Start", label: "选项"}] : [])
            .concat([{button: "B", label: "返回分类"}])
    readonly property var activeNetworks: network !== null && network.available ? network.profiles.filter(function(profile) { return profile.active }) : []
    // Rows carry their section; the detail draws a caption above the first row of each section.
    readonly property var rows: {
        switch (openedCategory) {
        case 0: {
            const result = [{name: "Wi-Fi", key: "wifi", section: ""}]
            activeNetworks.forEach(function(profile) { result.push({name: profile.name, key: "netActive", uuid: profile.id, section: "已连接", icon: "wifi"}) })
            const names = activeNetworks.map(function(profile) { return profile.name })
            const points = network !== null && network.available ? network.accessPoints : []
            points.forEach(function(point, index) {
                if (!point.active && names.indexOf(point.ssid) < 0)
                    result.push({name: point.ssid, key: "netPoint", index: index, security: point.security, section: "附近的网络", icon: "wifi"})
            })
            if (!result.some(function(entry) { return entry.key === "netPoint" })) result.push({name: "扫描附近的网络", key: "netScan", section: "附近的网络", icon: "search"})
            return result
        }
        case 1: return [{name: "亮度", key: "brightness", section: "屏幕", icon: "sun"}, {name: "自动息屏", key: "screenOff", section: "屏幕"},
            {name: "夜间模式", key: "night", section: "外观"}, {name: "界面字号", key: "font", section: "外观"}, {name: "减少动态效果", key: "motion", section: "外观"}]
        case 2: return [{name: "音量", key: "volume", section: "", icon: "volume"}, {name: "声音输出", key: "audioOutput", section: ""}]
        case 3: return [{name: "摇杆测试", key: "tester", detail: "查看按键、摇杆与扳机读数", section: ""},
            {name: "文字输入测试", key: "input", detail: "退出后清空", section: ""}]
        case 4: return [{name: "空闲变暗", key: "dim", section: "节能"}, {name: "立即息屏", key: "screenOffNow", detail: "首个按键仅唤醒", section: "节能"},
            {name: "电池与供电", key: "battery", section: "电池"}, {name: "重启", key: "reboot", section: "系统电源"}, {name: "关机", key: "poweroff", section: "系统电源"}]
        case 5: return [{name: "性能浮窗", key: "monitor", section: "性能浮窗"},
            {name: "帧间隔 P95", key: "p95", section: "帧与串流"}, {name: "串流解码", key: "decode", section: "帧与串流"},
            {name: "网络丢帧", key: "drop", section: "帧与串流"}, {name: "串流排队", key: "queue", section: "帧与串流"},
            {name: "音频接收队列", key: "audioQueue", section: "帧与串流"}, {name: "温控", key: "thermal", section: "帧与串流"},
            {name: "GPU 频率", key: "gpuFrequency", section: "帧与串流"},
            {name: "自动调频", detail: "桌面 816 · 游戏 1008 · 熄屏 600 MHz", key: "cpuAuto", section: "CPU"},
            {name: "频率预设", detail: "手动选择会关闭自动调频", key: "cpuPreset", section: "CPU"}, {name: "调速器", key: "cpuGovernor", section: "CPU"},
            {name: "最低频率", key: "cpuMin", section: "CPU"}, {name: "最高频率", key: "cpuMax", section: "CPU"}, {name: "当前频率", key: "cpuCurrent", section: "CPU"},
            {name: "Swap 使用", key: "swap", section: "内存"}, {name: "zram 内存压缩", key: "zram", section: "内存"},
            {name: "压缩算法", key: "zramAlgorithms", section: "内存"}, {name: "压缩内存占用", key: "zramMemory", section: "内存"},
            {name: "内存压力（10 秒）", key: "pressure", section: "内存"}]
        case 6: return hardware ? [{name: "系统分区", key: "storage0", section: ""}, {name: "游戏分区", key: "storage1", section: ""}, {name: "启动分区", key: "storage2", section: ""}]
            : [{name: "预览文件所在卷", info: "storage", value: "刷新", key: "storage", section: ""}]
        default: return [{name: "当前运行环境", info: "system", value: hardware ? "R46H" : "本机", section: "状态"},
            {name: "系统 CPU", key: "systemCpu", section: "状态"}, {name: "系统内存", key: "memory", section: "状态"},
            {name: "处理器温度", key: "temperature", section: "状态"},
            {name: "启动器", value: Qt.application.displayName, section: "关于"}, {name: "版本", value: Qt.application.version, section: "关于"},
            {name: "项目地址", value: "https://github.com/OJZen/JumeOS", section: "关于"},
            {name: "浏览器 Qt WebEngine", key: "browser", value: browserVersions.webEngine || "", section: "关于"},
            {name: "Chromium 内核", key: "browser", value: browserVersions.chromium || "", section: "关于"},
            {name: "Chromium 安全补丁基线", key: "browser", value: browserVersions.securityPatch || "", section: "关于"}]
        }
    }
    // First row of the 关于 section, for the about scene.
    readonly property int aboutRow: 4
    signal notice(string text)
    signal activity()
    signal screenOffRequested()
    signal editRequested()
    signal wifiPasswordRequested(string name)
    // Readings return "" when there is no value; the row then shows why instead of "—" (§9.5).
    function metric(key, suffix, divisor) {
        if (!hardware || device.info[key] === undefined || device.info[key] < 0) return ""
        return (device.info[key] / (divisor || 1)).toFixed(divisor ? 1 : 0) + (suffix || "")
    }
    function reading(source, key, digits, suffix) {
        const value = source ? source[key] : undefined
        return typeof value === "number" && isFinite(value) && value >= 0 ? value.toFixed(digits) + suffix : ""
    }
    readonly property var readings: ["systemCpu", "memory", "temperature", "thermal", "gpuFrequency", "pressure", "battery", "cpuCurrent", "swap", "zram",
        "zramAlgorithms", "zramMemory", "p95", "decode", "drop", "queue", "audioQueue", "browser"]
    function informational(row) { return !row.key || readings.indexOf(row.key) >= 0 }
    function choiceRow(key) {
        return ["font", "night", "dim", "screenOff"].indexOf(key) >= 0 || (!!key && key.indexOf("cpu") === 0 && key !== "cpuCurrent" && key !== "cpuAuto")
    }
    function canActivate(key) {
        if (!key || readings.indexOf(key) >= 0 || key === "wifi" || key === "audioOutput") return false
        if (key === "tester" || key === "input" || key === "motion" || key === "monitor" || key === "font" || key === "night") return true
        if (key.indexOf("net") === 0) return network !== null && network.available && !network.busy && (key === "netRefresh" || (hardware && device.controls && network.controls && (key !== "netDisconnect" || activeNetworks.length === 1)))
        if (["poweroff", "reboot", "cpuAuto", "cpuPreset", "cpuGovernor", "cpuMin", "cpuMax", "screenOffNow"].indexOf(key) >= 0) return !hardware ? key === "screenOffNow" : device.controls
        if (hardware && key === "volume") return false
        if (hardware && (key === "dim" || key === "screenOff")) return device.controls
        if (hardware && key === "brightness") return device.controls && device.info.brightnessPercent >= 0
        return true
    }
    // Why a row is disabled: no reading, or an action this device or preview cannot take.
    function rowReason(row) {
        if (!row) return ""
        const key = row.key || ""
        if (informational(row)) {
            if (rowValue(row) !== "") return ""
            if (key === "p95") return "游戏运行时显示"
            if (["decode", "drop", "queue", "audioQueue"].indexOf(key) >= 0) return "串流时显示"
            if (key === "browser") return "浏览器未安装或版本未知"
            return hardware ? "暂无读数" : "预览中不可用"
        }
        if (canActivate(key)) return ""
        if (key === "wifi") return "无线开关尚未接入"
        if (key === "audioOutput") return "扬声器 / 耳机切换尚未接入"
        if (key === "volume") return "使用机身音量键调节"
        if (key.indexOf("net") === 0) return network === null || !network.available ? "网络服务不可用" : network.busy ? "正在处理…" : hardware ? "需要设备控制权限" : "预览中不可用"
        return hardware ? "需要设备控制权限" : "预览中不可用"
    }
    function signalText(percent) { return percent >= 70 ? "信号良好" : percent >= 40 ? "信号一般" : percent >= 0 ? "信号较弱" : "" }
    function rowDescription(row) {
        if (row.key === "netActive") return ["已连接", network !== null ? signalText(network.signal) : ""].filter(function(part) { return !!part }).join(" · ")
        if (hardware && row.key && row.key.indexOf("storage") === 0 && row.key !== "storage") {
            const value = device.storage[Number(row.key.slice(-1))]
            return value && value.available ? value.filesystem + " · " + (value.readOnly ? "只读" : "可写") : ""
        }
        return row.info === "storage" ? metrics.storage : row.info === "system" ? metrics.system : row.detail || ""
    }
    function rowValue(row) {
        if (row.key && row.key.indexOf("storage") === 0 && row.key !== "storage") {
            const value = device.storage[Number(row.key.slice(-1))]
            return value && value.available ? (value.availableBytes / 1073741824).toFixed(1) + " / " + (value.totalBytes / 1073741824).toFixed(1) + " GiB 可用" : "未挂载或不可用"
        }
        switch (row.key) {
        case "volume": return hardware ? "" : store.volume + "%"
        case "brightness": return hardware ? metric("brightnessPercent", "%") : store.brightness + "%"
        case "font": return store.fontPercent + "%"
        case "night": return nightLabels[nightModes.indexOf(store.nightMode)] || "关闭"
        case "dim": return store.dimSeconds ? store.dimSeconds + " 秒" : "关闭"
        case "screenOff": return store.screenOffSeconds ? store.screenOffSeconds / 60 + " 分钟" : "关闭"
        case "screenOffNow": return "息屏"
        case "motion": return store.reducedMotion ? "开启" : "关闭"
        case "monitor": return store.monitor ? "开启" : "关闭"
        case "systemCpu": return metric("systemCpu", "%", 1)
        case "netScan": return network !== null && network.busy ? network.status : ""
        case "memory": { const available = metric("MemAvailable", " MiB 可用", 1024), total = metric("MemTotal", " MiB", 1024); return available && total ? available + " / " + total : "" }
        case "temperature": return metric("temperatureC", " °C", 1)
        case "thermal": {
            const cpu = hardware ? device.info.cpuCoolingState : -1, gpu = hardware ? device.info.gpuCoolingState : -1
            return !hardware ? "" : cpu > 0 && gpu > 0 ? "CPU/GPU 限频" : cpu > 0 ? "CPU 限频" : gpu > 0 ? "GPU 限频"
                : cpu === 0 && gpu === 0 ? "未介入" : "状态未知"
        }
        case "gpuFrequency": return metric("gpuFrequencyHz", " MHz", 1000000)
        case "pressure": return metric("memoryPressurePercent", "%", 1)
        case "p95": return metrics.game && metrics.game.active ? reading(metrics.game, "intervalP95Ms", 1, " ms") : ""
        case "decode": return metrics.stream && metrics.stream.active ? reading(metrics.stream, "decodeMs", 1, " ms") : ""
        case "drop": return metrics.stream && metrics.stream.active ? reading(metrics.stream, "networkDropPercent", 1, "%") : ""
        case "queue": return metrics.stream && metrics.stream.active ? reading(metrics.stream, "queueMs", 1, " ms") : ""
        case "audioQueue": return metrics.stream && metrics.stream.active ? reading(metrics.stream, "audioNetworkQueueMs", 0, " ms") : ""
        case "battery": {
            if (!hardware) return ""
            const voltage = metric("voltageUv", " V", 1000000), supply = device.info.online === 1 ? "外部供电" : device.info.online === 0 ? "电池供电" : ""
            return [voltage, supply].filter(function(part) { return !!part }).join(" · ")
        }
        case "poweroff": case "reboot": case "cpuPreset": return canActivate(row.key) ? "确认…" : ""
        case "cpuAuto": return hardware && device.controls ? (device.automaticCpu ? "开启" : "关闭") : ""
        case "cpuGovernor": return hardware ? device.info.cpu.governor || "" : ""
        case "cpuMin": case "cpuMax": case "cpuCurrent": {
            const field = row.key === "cpuMin" ? "scaling_min_freq" : row.key === "cpuMax" ? "scaling_max_freq" : "scaling_cur_freq"
            const value = hardware ? device.info.cpu[field] : -1
            return value > 0 ? (value / 1000).toFixed(0) + " MHz" : ""
        }
        case "swap": { const free = metric("SwapFree", " KiB 可用"), total = metric("SwapTotal", " KiB"); return free && total ? free + " / " + total : "" }
        case "zram": return hardware ? (device.info.zramPresent ? metric("zramSize", " MiB", 1048576) : "未启用") : ""
        case "zramAlgorithms": return hardware ? device.info.zramAlgorithms || "" : ""
        case "zramMemory": return metric("zramMemory", " MiB", 1048576)
        default: return row.value || ""
        }
    }
    // §7.3 Start on the network page: saved networks, forgetting one and the remember switch.
    readonly property string optionTitle: "网络"
    function optionItems() {
        if (sidebar || openedCategory !== 0 || network === null || !network.available) return []
        const reason = canActivate("netProfiles") ? "" : rowReason({key: "netProfiles"})
        const empty = network.profiles.length ? "" : "没有已保存的网络"
        return [{id: "netProfiles", label: "已保存的网络", icon: "wifi", reason: reason || empty},
                {id: "netForget", label: "忘记网络", icon: "x-circle", reason: reason || empty},
                {id: "netRemember", label: network.remember ? "不再记住新网络" : "记住新网络", icon: "save", reason: reason},
                {id: "netRefresh", label: "刷新状态", icon: "restart", reason: canActivate("netRefresh") ? "" : rowReason({key: "netRefresh"})}]
    }
    function runOption(id) {
        if (id === "netRemember") { network.remember = !network.remember; return }
        activateKey(id, id === "netProfiles" ? "已保存的网络" : id === "netForget" ? "忘记网络" : "")
    }
    function enter() {
        sidebar = true; tester = false; adjustingValue = false; rowIndex = 0
        categoryList.positionViewAtIndex(category, ListView.Contain)
    }
    function selectCategory(index) {
        if (adjustingValue && !store.save()) return false
        category = index; tester = false; adjustingValue = false; rowIndex = 0
        categoryList.positionViewAtIndex(category, ListView.Contain)
        activity()
        return true
    }
    // Opens a category's detail at the row it was left on; `row` overrides (e.g. the about section).
    function openCategory(index, viaSection, row) {
        if (!selectCategory(index)) return false
        openedCategory = category; sidebar = false
        rowIndex = Math.min(row !== undefined ? row : lastRows[category] || 0, Math.max(0, rows.length - 1))
        if (category === 6) { metrics.refreshStorage(); if (hardware) device.refreshStorage() }
        activity()
        return true
    }
    function startTester() { if (openCategory(3, false, 0)) { tester = true; activity() } }
    function leaveTester() { tester = false; activity() }
    function detailList() { return detailLoader.item ? detailLoader.item.rowsView : null }
    function choiceAnchor() { const list = detailList(); return list && list.currentItem ? list.currentItem : settings }
    function focusRow(index) {
        if (rowIndex !== index && adjustingValue && !store.save()) return
        if (rowIndex !== index) adjustingValue = false
        rowIndex = index; sidebar = false; activity()
    }
    function rememberRow() {
        if (sidebar) return
        const remembered = lastRows; remembered[openedCategory] = rowIndex; lastRows = remembered
    }
    function returnToCategories() {
        if (!store.save()) return false
        rememberRow()
        sidebar = true; tester = false; adjustingValue = false
        categoryList.positionViewAtIndex(category, ListView.Contain)
        return true
    }
    function valueIsAdjustable(key) { return key === "volume" || key === "brightness" }
    function adjust(direction, repeated) {
        const row = rows[rowIndex]
        if (!row || !canActivate(row.key)) { notice(rowReason(row) || "这项设备功能尚未接入"); return }
        if ((row.key === "motion" || row.key === "monitor") && repeated) return
        if (row.key === "input") { if (!repeated) editRequested(); return }
        if (row.key === "tester") { if (!repeated) startTester(); return }
        if (row.key.indexOf("storage") === 0) { metrics.refreshStorage(); if (hardware) device.refreshStorage(); return }
        if (hardware && row.key === "brightness") {
            if (!device.setBrightness(Math.max(10, Math.min(100, device.info.brightnessPercent + direction * 5)))) notice(device.error)
            return
        }
        store.adjust(row.key, direction * (row.key === "volume" || row.key === "brightness" ? 5 : 1))
    }
    function activate(repeated) {
        if (repeated || !detailReady) return
        const row = rows[rowIndex]
        if (!row || !canActivate(row.key)) { notice(rowReason(row) || "这项设备功能尚未接入"); return }
        activateKey(row.key, row.name, row)
    }
    function activateKey(key, name, row) {
        if (!canActivate(key)) { notice(rowReason({key: key})); return }
        choiceKey = key
        if (key === "netRefresh") { network.refresh(); return }
        if (key === "screenOffNow") { screenOffRequested(); return }
        if (key === "cpuAuto") { if (!device.setAutomaticCpu(!device.automaticCpu)) notice(device.error); return }
        if (key === "netScan") { network.scan(); return }
        if (key === "netPoint") { connectPoint(row.index); return }
        if (key === "netActive") {
            choiceValues = [row.uuid]
            choices.present(choiceAnchor(), ["关闭", "断开连接", "忘记此网络"], 0, name + " · " + rowDescription(row))
        } else if (key === "netProfiles" || key === "netForget") {
            choiceValues = network.profiles.map(function(p){return p.id})
            const labels = network.profiles.map(function(p){return p.name + (p.active ? " · 已连接" : "")})
            choices.present(choiceAnchor(), labels, key === "netForget" ? -1 : network.profiles.findIndex(function(p){return p.active}), name)
        } else if (key === "netDisconnect") {
            choices.present(choiceAnchor(), ["取消", "断开 Wi-Fi"], 0, "断开后远控连接将中断")
        } else if (key === "poweroff" || key === "reboot") {
            choiceValues = ["", key]
            choices.present(choiceAnchor(), ["取消", name], 0, "确认" + name)
        } else if (key.indexOf("cpu") === 0) {
            const cpu = device.info.cpu
            let labels = []; let index = 0
            if (key === "cpuPreset") {
                choiceValues = ["original"]; labels = ["恢复原始"]
                for (const entry of [["schedutil", "balanced", "均衡"], ["performance", "performance", "性能"], ["powersave", "powersave", "省电"]]) {
                    if (cpu.governors.indexOf(entry[0]) >= 0) { choiceValues.push(entry[1]); labels.push(entry[2]) }
                }
            }
            else if (key === "cpuGovernor") { choiceValues = cpu.governors; labels = cpu.governors; index = labels.indexOf(cpu.governor) }
            else { choiceValues = cpu.frequencies; labels = choiceValues.map(function(v) { return (v / 1000).toFixed(0) + " MHz" }); index = choiceValues.indexOf(key === "cpuMin" ? cpu.scaling_min_freq : cpu.scaling_max_freq) }
            choices.present(choiceAnchor(), labels, Math.max(0,index), name)
        } else if (choiceRow(key)) {
            const labels = key === "font" ? Ui.Theme.fontPercents.map(function(value) { return value + "%" }) : key === "night" ? nightLabels
                : key === "dim" ? ["关闭", "30 秒", "60 秒", "120 秒"] : ["关闭", "1 分钟", "3 分钟", "5 分钟", "10 分钟", "15 分钟"]
            const index = key === "font" ? Ui.Theme.fontPercents.indexOf(store.fontPercent) : key === "night" ? nightModes.indexOf(store.nightMode)
                : key === "dim" ? [0, 30, 60, 120].indexOf(store.dimSeconds) : [0, 60, 180, 300, 600, 900].indexOf(store.screenOffSeconds)
            choices.present(choiceAnchor(), labels, index, name)
        } else if (!valueIsAdjustable(key)) adjust(1, false)
    }
    function connectPoint(index) {
        if (!network.selectAccessPoint(index)) { notice("暂不支持此网络的加密方式"); return }
        if (network.selectedNetwork.security === "psk") wifiPasswordRequested(network.selectedNetwork.ssid)
        else network.connectSelected("")
    }
    // Returns false only for B on the category list, which leaves settings.
    function dispatch(action, repeated) {
        if (choices.dispatch(action, repeated)) return true
        if (tester) return true
        if (action === "prevSection" || action === "nextSection") { switchCategory(action === "nextSection" ? 1 : -1); return true }
        if (action === "back") {
            if (repeated) return true
            if (!sidebar) { returnToCategories(); return true }
            return false
        }
        if (!sidebar && !detailReady) {
            if (action === "left") returnToCategories()
            return true
        }
        if (action === "pageUp" || action === "pageDown") { turnPage(action === "pageDown" ? 1 : -1); return true }
        if (sidebar) {
            if (action === "up") selectCategory(Math.max(0, category - 1))
            else if (action === "down") selectCategory(Math.min(categories.length - 1, category + 1))
            else if ((action === "right" || action === "accept") && !repeated) openCategory(category)
        } else if (sliderRow && (action === "left" || action === "right")) {
            // §7.3: ←→ adjust a slider directly; the release saves it.
            adjustingValue = true
            adjust(action === "right" ? 1 : -1, repeated)
        } else if (action === "itemAction") {
            if (!repeated && row && row.key === "netActive") activateKey("netDisconnect", "")
        } else if (action === "pageAction") {
            if (!repeated && openedCategory === 0 && network !== null) { if (canActivate("netScan")) network.scan(); else if (canActivate("netRefresh")) network.refresh() }
        } else {
            if (action === "left") returnToCategories()
            else if (action === "up") focusRow(Math.max(0, rowIndex - 1))
            else if (action === "down") focusRow(Math.min(rows.length - 1, rowIndex + 1))
            else if (action === "accept") activate(repeated)
        }
        return true
    }
    function release(action) {
        if (adjustingValue && (action === "left" || action === "right")) { adjustingValue = false; store.save() }
    }
    // L1/R1: neighbouring category, no wrap; an open detail opens the next one at its last row.
    function switchCategory(direction) {
        const next = Math.max(0, Math.min(categories.length - 1, category + direction))
        if (next === category) return
        if (sidebar) { selectCategory(next); return }
        if (!store.save()) return
        rememberRow()
        openCategory(next, true)
    }
    // L2/R2: one screen of rows.
    function turnPage(direction) {
        const list = sidebar ? categoryList : detailList()
        if (!list) return
        const step = Math.max(1, Math.floor(list.height / (Ui.Theme.listRowHeight + list.spacing)))
        if (sidebar) selectCategory(Math.max(0, Math.min(categories.length - 1, category + direction * step)))
        else focusRow(Math.max(0, Math.min(rows.length - 1, rowIndex + direction * step)))
    }
    // Right stick: scroll the detail without moving the focused row.
    function scroll(velocity) {
        const list = detailList()
        if (tester || sidebar || !list || list.contentHeight <= list.height) return
        list.contentY = Math.max(list.originY, Math.min(list.originY + list.contentHeight - list.height, list.contentY + velocity * Ui.Theme.scrollStep))
    }
    onCategoryChanged: if (!sidebar) openedCategory = category
    // §8 Settings: categories on the left (280), the detail on the right with section captions.
    // While the categories have focus the detail is not built; the right pane names the category.
    Item {
        anchors.fill: parent
        Ui.ListView {
            id: categoryList; objectName: "settingsCategories"
            x: 0; y: Ui.Theme.space8; width: settings.twoPane ? Ui.Theme.settingsSidebarWidth : parent.width; height: parent.height - y
            visible: settings.twoPane || settings.sidebar; currentIndex: settings.category
            model: settings.categories
            delegate: Ui.ListRow {
                required property string modelData; required property int index
                width: categoryList.width; height: Ui.Theme.settingsCategoryHeight; flat: true
                title: modelData; iconName: settings.categoryIcons[index]; fontScale: settings.fontScale
                current: !settings.sidebar && settings.category === index
                selected: settings.category === index; focusOutline: false
                Accessible.role: Accessible.PageTab
                onFocused: settings.selectCategory(index)
                onActivated: settings.openCategory(index)
            }
        }
        Ui.FocusFrame {
            id: focusOutline; objectName: "settingsFocus"
            x: categoryList.x
            y: categoryList.y + (categoryList.currentItem ? categoryList.currentItem.y - categoryList.contentY : 0)
            width: categoryList.width
            height: categoryList.currentItem ? categoryList.currentItem.height : Ui.Theme.settingsCategoryHeight
            visible: settings.sidebar && (!categoryList.currentItem || categoryList.currentItem.y >= categoryList.contentY)
            active: settings.navigationActive && settings.sidebar && !choices.visible
            reducedMotion: settings.store.reducedMotion
        }
        Item {
            id: detailPane
            x: settings.twoPane ? Ui.Theme.settingsSidebarWidth + Ui.Theme.space32 : 0
            width: parent.width - x; height: parent.height
            visible: settings.twoPane || !settings.sidebar
            Column {
                objectName: "settingsPlaceholder"
                y: Ui.Theme.space24; width: parent.width; spacing: Ui.Theme.space4
                visible: settings.sidebar
                Ui.Label { width: parent.width; role: "headline"; fontScale: settings.fontScale; text: settings.categories[settings.category] }
                Ui.Label { width: parent.width; role: "caption"; fontScale: settings.fontScale; color: Ui.Theme.textSecondary; text: settings.categoryNotes[settings.category] }
            }
            Loader {
                id: detailLoader; anchors.fill: parent
                active: !settings.sidebar; visible: status === Loader.Ready
                asynchronous: true; sourceComponent: detailComponent
            }
        }
        Component {
            id: detailComponent
            Item {
                property alias rowsView: settingRows
                Ui.ListView {
                    id: settingRows; objectName: "settingsItems"
                    width: parent.width; height: parent.height
                    visible: !settings.tester
                    model: settings.rows; currentIndex: settings.rowIndex
                    delegate: Item {
                        id: entry
                        required property var modelData; required property int index
                        readonly property bool opensSection: modelData.section !== "" && (index === 0 || settings.rows[index - 1].section !== modelData.section)
                        // The FocusFrame rings the row, not its section caption.
                        readonly property real rowY: caption.visible ? caption.height : (index === 0 ? Ui.Theme.space8 : 0)
                        readonly property real rowHeight: row.height
                        width: settingRows.width; height: rowY + row.height
                        Ui.Label {
                            id: caption; objectName: "settingsSection"
                            x: Ui.Theme.sectionIndent; width: parent.width - x; height: Ui.Theme.lineHeight("caption") + Ui.Theme.space16
                            verticalAlignment: Text.AlignVCenter
                            visible: entry.opensSection; text: entry.modelData.section
                            role: "caption"; fontScale: settings.fontScale; color: Ui.Theme.textSecondary
                        }
                        Ui.ListRow {
                            id: row
                            y: entry.rowY; width: parent.width; fontScale: settings.fontScale
                            title: entry.modelData.name; iconName: entry.modelData.icon || ""
                            description: settings.rowDescription(entry.modelData)
                            value: settings.rowValue(entry.modelData)
                            disabledReason: settings.rowReason(entry.modelData)
                            actionable: settings.canActivate(entry.modelData.key)
                            choice: settings.choiceRow(entry.modelData.key)
                            chevron: ["netActive", "tester", "input"].indexOf(entry.modelData.key) >= 0
                            trailingIcon: entry.modelData.security === "psk" ? "lock" : ""
                            reducedMotion: settings.store.reducedMotion
                            toggleState: entry.modelData.key === "motion" ? Number(settings.store.reducedMotion) : entry.modelData.key === "monitor" ? Number(settings.store.monitor)
                                : entry.modelData.key === "wifi" ? Number(settings.activeNetworks.length > 0) : -1
                            progress: entry.modelData.key === "volume" && !settings.hardware ? settings.store.volume / 100
                                : entry.modelData.key === "brightness" && settings.canActivate("brightness") ? (settings.hardware ? settings.device.info.brightnessPercent : settings.store.brightness) / 100 : -1
                            focusOutline: false; selected: settings.rowIndex === entry.index
                            adjusting: settings.adjustingValue && selected
                            onFocused: settings.focusRow(entry.index)
                            onActivated: if (settings.rowIndex === entry.index) settings.activate(false)
                        }
                    }
                }
                Column {
                    objectName: "controllerTest"
                    y: Ui.Theme.space8; width: parent.width; spacing: Ui.Theme.space16; visible: settings.tester
                    Ui.Label { width: parent.width; text: settings.controller.deviceName || "未检测到手柄"; color: Ui.Theme.text; fontScale: settings.fontScale }
                    Row {
                        spacing: Ui.Theme.space48
                        Repeater {
                            model: 2
                            Column {
                                id: stick
                                required property int index
                                spacing: Ui.Theme.space12
                                Rectangle {
                                    width: 220; height: 220; radius: 110; color: Ui.Theme.surfaceSunken; border.color: Ui.Theme.outline
                                    Rectangle { x: 109; y: 0; width: 1; height: 220; color: Ui.Theme.outline }
                                    Rectangle { x: 0; y: 109; width: 220; height: 1; color: Ui.Theme.outline }
                                    Rectangle {
                                        x: 98 + Number(settings.controller.axes[stick.index * 2]) * 95
                                        y: 98 + Number(settings.controller.axes[stick.index * 2 + 1]) * 95
                                        width: 24; height: 24; radius: 12; color: stick.index === 0 ? Ui.Theme.accent : Ui.Theme.warning
                                    }
                                }
                                Ui.Label {
                                    anchors.horizontalCenter: parent.horizontalCenter; tabular: true; role: "caption"; fontScale: settings.fontScale; color: Ui.Theme.textSecondary
                                    text: (stick.index === 0 ? "左" : "右") + "  X " + Number(settings.controller.axes[stick.index * 2]).toFixed(2) + " / Y " + Number(settings.controller.axes[stick.index * 2 + 1]).toFixed(2)
                                }
                            }
                        }
                    }
                    Ui.Label {
                        width: parent.width; wrapMode: Text.Wrap; color: Ui.Theme.text; role: "caption"; tabular: true; fontScale: settings.fontScale
                        text: "按键  " + (settings.controller.buttons || "无") + "     LT " + Number(settings.controller.axes[4]).toFixed(2) + " / RT " + Number(settings.controller.axes[5]).toFixed(2)
                    }
                }
                Ui.FocusFrame {
                    objectName: "settingsDetailFocus"
                    x: 0
                    y: settingRows.y + (settingRows.currentItem ? settingRows.currentItem.y + settingRows.currentItem.rowY - settingRows.contentY : 0)
                    width: settingRows.width
                    height: settingRows.currentItem ? settingRows.currentItem.rowHeight : Ui.Theme.listRowHeight
                    visible: !settings.tester && (!settingRows.currentItem || settingRows.currentItem.y >= settingRows.contentY)
                    adjusting: settings.adjustingValue
                    active: settings.navigationActive && settings.detailReady && !choices.visible
                    reducedMotion: settings.store.reducedMotion
                }
            }
        }
    }
    Ui.ChoicePopup {
        id: choices; objectName: "settingsChoices"; parent: settings
        onActivated: function(index) {
            let ok = false
            const key = settings.choiceKey; const device = settings.device
            if (key === "netActive") {
                if (index === 0) { close(); return }
                if (index === 1) {
                    if (!settings.canActivate("netDisconnect")) { close(); settings.notice(settings.rowReason({key: "netDisconnect"})); return }
                    settings.choiceKey = "netDisconnect"; present(settings.choiceAnchor(), ["取消", "断开 Wi-Fi"], 0, "断开后远控连接将中断"); return
                }
                settings.choiceKey = "netForgetConfirm"
                present(settings.choiceAnchor(), ["取消", "忘记网络"], 0, "移除配置并断开连接？")
                return
            } else if (key === "netForget") {
                const uuid = settings.choiceValues[index]
                settings.choiceKey = "netForgetConfirm"; settings.choiceValues = [uuid]
                present(settings.choiceAnchor(), ["取消", "忘记网络"], 0, "移除配置并断开连接？")
                return
            } else if (key === "netForgetConfirm") {
                if (index === 0) { close(); return }
                ok = settings.network.forget(settings.choiceValues[0])
            } else if (key === "netProfiles" || key === "netDisconnect") {
                if (key === "netDisconnect" && index === 0) { close(); return }
                ok = key === "netProfiles" ? settings.network.activate(settings.choiceValues[index]) : settings.network.disconnect()
                if (!ok) settings.notice("网络请求尚不可用，请刷新后重试。")
            } else if (key === "poweroff" || key === "reboot") {
                if (index === 0) { close(); return }
                if (!settings.store.save()) return
                ok = device.requestPower(key)
            } else if (key === "cpuPreset") ok = device.cpuPreset(settings.choiceValues[index])
            else if (key.indexOf("cpu") === 0) {
                const cpu = device.info.cpu; const value = settings.choiceValues[index]
                ok = device.applyCpu(key === "cpuGovernor" ? value : cpu.governor,
                    key === "cpuMin" ? value : cpu.scaling_min_freq, key === "cpuMax" ? value : cpu.scaling_max_freq)
            } else ok = settings.store.choose(key, index)
            if (ok) close(); else if (device && device.error) settings.notice(device.error)
        }
        onClosed: settings.activity()
    }
}
