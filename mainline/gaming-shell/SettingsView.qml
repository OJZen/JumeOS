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
    clip: true
    property int category: 0
    property int openedCategory: 0
    property int rowIndex: 0
    property bool sidebar: true
    property bool adjustingValue: false
    property bool navigationActive: true
    property bool tester: false
    readonly property real fontScale: store.fontPercent / 100
    readonly property bool choiceOpen: choices.visible
    readonly property bool detailReady: !sidebar && detailLoader.status === Loader.Ready
    readonly property var categories: ["常用", "网络与 Wi-Fi", "摇杆测试", "声音", "屏幕", "存储", "系统信息", "电量与电源", "字体与输入", "CPU 频率", "内存与 Swap", "关于"]
    readonly property var categoryIcons: ["settings", "wifi", "gamepad", "volume", "display", "storage", "info", "battery", "keyboard", "cpu", "memory", "info"]
    readonly property var hints: choices.visible ? choices.hints : sidebar ? [["↑↓", "选择分类"], ["A / ↵", "进入"], ["B / Esc", "主页"]]
        : !detailReady ? [["← / B", "返回分类"]]
        : adjustingValue ? [["↑↓", "增减数值"], ["A / B", "完成调整"], ["←", "返回分类"]]
        : [["↑↓", "选择项目"], ["← / B", "返回分类"]].concat(rows[rowIndex] && canActivate(rows[rowIndex].key)
            ? [["A / ↵", valueIsAdjustable(rows[rowIndex].key) ? "调整" : ["motion", "monitor", "netRemember"].indexOf(rows[rowIndex].key) >= 0 ? "切换" : rows[rowIndex].key === "storage" ? "刷新" : "打开"]] : [])
    readonly property var rows: {
        const volume = {name: "音量", detail: "", key: "volume"}
        const brightness = {name: "屏幕亮度", detail: "", key: "brightness"}
        const motion = {name: "减少动态效果", detail: "", key: "motion"}
        switch (openedCategory) {
        case 0: return [volume, brightness, motion, {name: "性能浮窗", detail: "", key: "monitor"}]
        case 1: return [{name: "添加 Wi-Fi", detail: "切换网络可能中断远控", key: "netScan"}, {name: "已保存的 Wi-Fi", key: "netProfiles"},
            {name: "记住新网络", detail: "保存密码，供下次自动连接", key: "netRemember"}, {name: "断开当前 Wi-Fi", key: "netDisconnect"},
            {name: "忘记网络", key: "netForget"}, {name: "刷新网络状态", key: "netRefresh"}]
        case 2: return []
        case 3: return [volume, {name: "声音输出", detail: "扬声器 / 耳机", value: "未接入"}]
        case 4: return [brightness, motion, {name: "预览分辨率", detail: "", value: "1024 × 768"}]
        case 5: return hardware ? [{name: "系统分区", key: "storage0"}, {name: "游戏分区", key: "storage1"}, {name: "启动分区", key: "storage2"}]
            : [{name: "预览文件所在卷", detail: "", info: "storage", value: "刷新", key: "storage"}]
        case 6: return [{name: "当前运行环境", detail: "", info: "system", value: "本机"}, {name: "系统 CPU", detail: "", key: "systemCpu"}, {name: "系统内存", detail: "", key: "memory"}, {name: "处理器温度", detail: "", key: "temperature"}, {name: "GPU 频率", detail: "", key: "gpuFrequency"}, {name: "内存压力（10 秒）", detail: "", key: "pressure"}]
        case 7: return [{name: "空闲变暗", detail: "", key: "dim"}, {name: "电池与供电", detail: "", key: "battery"}, {name: "关机", detail: "", key: "poweroff"}, {name: "重启", detail: "", key: "reboot"}]
        case 8: return [{name: "界面字体大小", detail: "", key: "font"}, {name: "文字输入测试", detail: "退出后清空", value: "打开", key: "input"}]
        case 9: return [{name: "频率预设", detail: "本次测试会话生效", key: "cpuPreset"}, {name: "调速器", detail: "", key: "cpuGovernor"}, {name: "最低频率", detail: "", key: "cpuMin"}, {name: "最高频率", detail: "", key: "cpuMax"}, {name: "当前频率", detail: "", key: "cpuCurrent"}]
        case 10: return [{name: "Swap 使用", detail: "", key: "swap"}, {name: "zram 内存压缩", detail: "", key: "zram"}, {name: "压缩算法", detail: "", key: "zramAlgorithms"}, {name: "压缩内存占用", detail: "", key: "zramMemory"}]
        default: return [{name: "启动器", value: Qt.application.displayName}, {name: "版本", value: Qt.application.version},
            {name: "项目地址", value: "https://github.com/OJZen/JumeOS"},
            {name: "浏览器 Qt WebEngine", value: browserVersions.webEngine || "未安装 / 版本未知"},
            {name: "Chromium 内核", value: browserVersions.chromium || "—"},
            {name: "Chromium 安全补丁基线", value: browserVersions.securityPatch || "—"}]
        }
    }
    signal notice(string text)
    signal activity()
    signal editRequested()
    signal wifiPasswordRequested(string name)
    function metric(key, suffix, divisor) {
        if (!hardware || device.info[key] === undefined || device.info[key] < 0) return "—"
        return (device.info[key] / (divisor || 1)).toFixed(divisor ? 1 : 0) + (suffix || "")
    }
    function canActivate(key) {
        if (!key || ["systemCpu", "memory", "temperature", "gpuFrequency", "pressure", "battery", "cpuCurrent", "swap", "zram", "zramAlgorithms", "zramMemory"].indexOf(key) >= 0) return false
        if (key.indexOf("net") === 0) return network !== null && network.available && !network.busy && (key === "netRefresh" || (hardware && device.controls && network.controls && (key !== "netDisconnect" || network.profiles.filter(function(p){return p.active}).length === 1)))
        if (["poweroff", "reboot", "cpuPreset", "cpuGovernor", "cpuMin", "cpuMax"].indexOf(key) >= 0) return hardware && device.controls
        if (hardware && key === "volume") return false
        if (hardware && key === "dim") return device.controls
        if (hardware && key === "brightness") return device.controls && device.info.brightnessPercent >= 0
        return true
    }
    function rowValue(row) {
        if (row.key && row.key.indexOf("storage") === 0 && row.key !== "storage") {
            const value = device.storage[Number(row.key.slice(-1))]
            return value && value.available ? (value.availableBytes / 1073741824).toFixed(1) + " / " + (value.totalBytes / 1073741824).toFixed(1) + " GiB 可用" : "未挂载或不可用"
        }
        switch (row.key) {
        case "volume": return hardware ? "机身音量键" : store.volume + "%"
        case "brightness": return hardware ? metric("brightnessPercent", "%") : store.brightness + "%"
        case "font": return store.fontPercent + "%"
        case "dim": return store.dimSeconds ? store.dimSeconds + " 秒" : "关闭"
        case "motion": return store.reducedMotion ? "开启" : "关闭"
        case "monitor": return store.monitor ? "开启" : "关闭"
        case "systemCpu": return metric("systemCpu", "%", 1)
        case "netScan": return network !== null && network.available ? (network.busy ? network.status : "扫描附近网络") : "不可用"
        case "netProfiles": return network !== null && network.available ? network.profiles.length + " 个配置" : "不可用"
        case "netRemember": return ""
        case "netForget": return "选择…"
        case "netDisconnect": return canActivate(row.key) ? "确认…" : "—"
        case "netRefresh": return network !== null && network.busy ? "处理中…" : "刷新"
        case "memory": return metric("MemAvailable", " MiB 可用", 1024) + " / " + metric("MemTotal", " MiB", 1024)
        case "temperature": return metric("temperatureC", " °C", 1)
        case "gpuFrequency": return metric("gpuFrequencyHz", " MHz", 1000000)
        case "pressure": return metric("memoryPressurePercent", "%", 1)
        case "battery": return hardware ? metric("voltageUv", " V", 1000000) + " · " + (device.info.online === 1 ? "外部供电" : device.info.online === 0 ? "电池供电" : "供电未知") : "—"
        case "poweroff": case "reboot": return hardware && device.controls ? "确认…" : "不可用"
        case "cpuPreset": return hardware && device.controls ? "选择…" : "不可用"
        case "cpuGovernor": return hardware ? device.info.cpu.governor || "—" : "—"
        case "cpuMin": case "cpuMax": case "cpuCurrent": {
            const field = row.key === "cpuMin" ? "scaling_min_freq" : row.key === "cpuMax" ? "scaling_max_freq" : "scaling_cur_freq"
            const value = hardware ? device.info.cpu[field] : -1
            return value > 0 ? (value / 1000).toFixed(0) + " MHz" : "—"
        }
        case "swap": return metric("SwapFree", " KiB 可用") + " / " + metric("SwapTotal", " KiB")
        case "zram": return hardware ? (device.info.zramPresent ? metric("zramSize", " MiB", 1048576) : "未启用") : "—"
        case "zramAlgorithms": return hardware ? device.info.zramAlgorithms || "—" : "—"
        case "zramMemory": return metric("zramMemory", " MiB", 1048576)
        default: return row.value
        }
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
    function openCategory(index) {
        if (!selectCategory(index)) return false
        openedCategory = category; sidebar = false; tester = category === 2
        if (category === 5) { metrics.refreshStorage(); if (hardware) device.refreshStorage() }
        activity()
        return true
    }
    function detailList() { return detailLoader.item ? detailLoader.item.rowsView : null }
    function choiceAnchor() { const list = detailList(); return list && list.currentItem ? list.currentItem : settings }
    function focusRow(index) {
        if (rowIndex !== index && adjustingValue && !store.save()) return
        if (rowIndex !== index) adjustingValue = false
        rowIndex = index; sidebar = false; activity()
    }
    function returnToCategories() {
        if (!store.save()) return false
        sidebar = true; tester = false; adjustingValue = false
        categoryList.positionViewAtIndex(category, ListView.Contain)
        return true
    }
    function valueIsAdjustable(key) { return key === "volume" || key === "brightness" }
    function adjust(direction, repeated) {
        const row = rows[rowIndex]
        if (!row || !canActivate(row.key)) { notice("这项设备功能尚未接入"); return }
        if ((row.key === "motion" || row.key === "monitor") && repeated) return
        if (row.key === "netRemember") { if (!repeated) network.remember = !network.remember; return }
        if (row.key === "input") { if (!repeated) editRequested(); return }
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
        if (!row || !canActivate(row.key)) { notice("这项设备功能尚未接入"); return }
        choiceKey = row.key
        if (row.key === "netRefresh") { network.refresh(); return }
        if (row.key === "netScan") {
            if (network.accessPoints.length) showNetworks(); else network.scan()
        } else if (row.key === "netProfiles" || row.key === "netForget") {
            if (!network.profiles.length) { notice("没有可用的已保存 Wi-Fi 配置"); return }
            choiceValues = network.profiles.map(function(p){return p.id})
            const labels = network.profiles.map(function(p){return p.name + (p.active ? " · 已连接" : "")})
            choices.present(choiceAnchor(), labels, row.key === "netForget" ? -1 : network.profiles.findIndex(function(p){return p.active}), row.name)
        } else if (row.key === "netDisconnect") {
            choices.present(choiceAnchor(), ["取消", "断开 Wi-Fi"], 0, "断开后远控连接将中断")
        } else if (row.key === "poweroff" || row.key === "reboot") {
            choiceValues = ["", row.key]
            choices.present(choiceAnchor(), ["取消", row.name], 0, "确认" + row.name)
        } else if (row.key.indexOf("cpu") === 0) {
            const cpu = device.info.cpu
            let labels = []; let index = 0
            if (row.key === "cpuPreset") {
                choiceValues = ["original"]; labels = ["恢复原始"]
                for (const entry of [["schedutil", "balanced", "均衡"], ["performance", "performance", "性能"], ["powersave", "powersave", "省电"]]) {
                    if (cpu.governors.indexOf(entry[0]) >= 0) { choiceValues.push(entry[1]); labels.push(entry[2]) }
                }
            }
            else if (row.key === "cpuGovernor") { choiceValues = cpu.governors; labels = cpu.governors; index = labels.indexOf(cpu.governor) }
            else { choiceValues = cpu.frequencies; labels = choiceValues.map(function(v) { return (v / 1000).toFixed(0) + " MHz" }); index = choiceValues.indexOf(row.key === "cpuMin" ? cpu.scaling_min_freq : cpu.scaling_max_freq) }
            choices.present(choiceAnchor(), labels, Math.max(0,index), row.name)
        } else if (row.key === "font" || row.key === "dim") {
            const labels = row.key === "font" ? ["100%", "110%", "120%"] : ["关闭", "30 秒", "60 秒", "120 秒"]
            const index = row.key === "font" ? (store.fontPercent - 100) / 10 : [0, 30, 60, 120].indexOf(store.dimSeconds)
            choices.present(choiceAnchor(), labels, index, row.name)
        } else if (row && valueIsAdjustable(row.key)) {
            if (adjustingValue && !store.save()) return
            adjustingValue = !adjustingValue
        } else adjust(1, false)
    }
    function showNetworks() {
        if (!network.accessPoints.length) { notice("未发现可连接的 Wi-Fi，请稍后重试。"); return }
        choiceKey = "netScan"
        const labels = network.accessPoints.map(function(ap) { return ap.ssid + " · " + ap.signal + "% · " + (ap.security === "open" ? "开放" : ap.security === "psk" ? "WPA/WPA2" : "暂不支持") })
        choices.present(choiceAnchor(), labels.concat(["重新扫描"]), -1, "附近 Wi-Fi")
    }
    Connections {
        target: settings.network
        function onScanReady() { if (settings.visible && settings.category === 1 && !settings.sidebar && settings.choiceKey === "netScan") settings.showNetworks() }
    }
    function dispatch(action, repeated) {
        if (choices.dispatch(action, repeated)) return true
        if (tester) return true
        if (!sidebar && !detailReady) {
            if (action === "back" || action === "left") returnToCategories()
            return true
        }
        if (!sidebar && action === "left") { returnToCategories(); return true }
        if (action === "back") {
            if (adjustingValue) { if (store.save()) adjustingValue = false; return true }
            if (!sidebar) { returnToCategories(); return true }
            return false
        }
        if (sidebar) {
            if (action === "up") selectCategory(Math.max(0, category - 1))
            else if (action === "down") selectCategory(Math.min(categories.length - 1, category + 1))
            else if ((action === "right" || action === "accept") && !repeated) openCategory(category)
        } else if (adjustingValue) {
            if (action === "up" || action === "down") adjust(action === "up" ? 1 : -1, repeated)
            else if (action === "accept") activate(repeated)
        } else {
            if (action === "up") { if (rowIndex === 0) returnToCategories(); else rowIndex-- }
            else if (action === "down") rowIndex = Math.min(rows.length - 1, rowIndex + 1)
            else if (action === "accept") activate(repeated)
        }
        return true
    }
    onCategoryChanged: if (!sidebar) openedCategory = category
    Item {
        anchors.fill: parent
        Ui.PageHeader {
            width: parent.width
            title: settings.sidebar ? "设置" : settings.categories[settings.category]
            subtitle: settings.sidebar ? "选择分类" : "设置"
            iconName: settings.sidebar ? "settings" : settings.categoryIcons[settings.category]
            backVisible: !settings.sidebar
            onBackRequested: settings.returnToCategories()
        }
        Ui.ListView {
            id: categoryList; objectName: "settingsCategories"
            y: Ui.Theme.contentY; width: Ui.Theme.sidebarWidth * 2; height: parent.height - y
            layer.enabled: true
            visible: settings.sidebar; currentIndex: settings.category
            model: settings.categories
            delegate: SettingRow {
                required property string modelData; required property int index
                width: categoryList.rowWidth; title: modelData; iconName: settings.categoryIcons[index]
                selected: settings.category === index; focusOutline: false
                Accessible.role: Accessible.PageTab
                onFocused: settings.selectCategory(index)
                onActivated: settings.openCategory(index)
            }
        }
        Ui.FocusFrame {
            id: focusOutline; objectName: "settingsFocus"
            x: 0
            y: categoryList.y + (categoryList.currentItem ? categoryList.currentItem.y - categoryList.contentY : 0)
            width: categoryList.rowWidth
            height: categoryList.currentItem ? categoryList.currentItem.height : Ui.Theme.rowHeight
            visible: settings.sidebar && (!categoryList.currentItem || categoryList.currentItem.y >= categoryList.contentY)
            active: settings.navigationActive && settings.sidebar && !choices.visible
            reducedMotion: settings.store.reducedMotion
        }
        Loader {
            id: detailLoader; anchors.fill: parent
            active: !settings.sidebar; visible: status === Loader.Ready
            asynchronous: true; sourceComponent: detailComponent
        }
        Component {
            id: detailComponent
            Item {
                property alias rowsView: settingRows
                Ui.ListView {
                    id: settingRows; objectName: "settingsItems"
                    y: Ui.Theme.contentY; width: parent.width; height: parent.height - y
                    visible: settings.category !== 2
                    model: settings.rows; currentIndex: settings.rowIndex
                    delegate: SettingRow {
                        required property var modelData; required property int index
                        width: settingRows.rowWidth; fontScale: settings.fontScale
                        title: modelData.name
                        description: {
                            if (settings.hardware && modelData.key && modelData.key.indexOf("storage") === 0) {
                                const value = settings.device.storage[Number(modelData.key.slice(-1))]
                                return value && value.available ? value.filesystem + " · " + (value.readOnly ? "只读" : "可写") : ""
                            }
                            return modelData.info === "storage" ? settings.metrics.storage : modelData.info === "system" ? settings.metrics.system : modelData.detail || ""
                        }
                        value: settings.adjustingValue && selected ? "↑  " + settings.rowValue(modelData) + "  ↓" : settings.rowValue(modelData)
                        actionable: settings.canActivate(modelData.key)
                        choice: modelData.key === "font" || modelData.key === "dim" || ["netProfiles", "netScan", "netForget"].indexOf(modelData.key) >= 0 || (!!modelData.key && modelData.key.indexOf("cpu") === 0 && modelData.key !== "cpuCurrent")
                        reducedMotion: settings.store.reducedMotion
                        toggleState: modelData.key === "motion" ? Number(settings.store.reducedMotion) : modelData.key === "monitor" ? Number(settings.store.monitor) : modelData.key === "netRemember" ? Number(settings.network && settings.network.remember) : -1
                        progress: modelData.key === "volume" && !settings.hardware ? settings.store.volume / 100 : modelData.key === "brightness" ? (settings.hardware ? settings.device.info.brightnessPercent : settings.store.brightness) / 100 : -1
                        focusOutline: false; selected: settings.rowIndex === index
                        onFocused: settings.focusRow(index)
                        onActivated: if (settings.rowIndex === index) settings.activate(false)
                    }
                }
                Item {
                    y: Ui.Theme.contentY; width: parent.width; height: parent.height - y; visible: settings.category === 2
                    Ui.Label { width: parent.width; elide: Text.ElideRight; text: settings.controller.deviceName || "未检测到手柄"; color: "#cfdee8"; fontScale: settings.fontScale }
                    Row {
                        y: 55; spacing: 72
                        Repeater {
                            model: 2
                            Rectangle {
                                required property int index
                                width: 220; height: 220; radius: 110; color: "#1d3442"; border.color: "#43616e"
                                Rectangle { x: 109; y: 0; width: 1; height: 220; color: "#45616d" }
                                Rectangle { x: 0; y: 109; width: 220; height: 1; color: "#45616d" }
                                Rectangle {
                                    x: 98 + Number(settings.controller.axes[parent.index * 2]) * 95
                                    y: 98 + Number(settings.controller.axes[parent.index * 2 + 1]) * 95
                                    width: 24; height: 24; radius: 12; color: parent.index === 0 ? Ui.Theme.accent : "#cbb8f5"
                                }
                                Ui.Label { anchors.horizontalCenter: parent.horizontalCenter; y: 233; text: (parent.index === 0 ? "左" : "右") + "  X " + Number(settings.controller.axes[parent.index * 2]).toFixed(2) + " / Y " + Number(settings.controller.axes[parent.index * 2 + 1]).toFixed(2); color: "#b4c8d4"; role: "caption" }
                            }
                        }
                    }
                    Ui.Label { y: 323; width: parent.width; elide: Text.ElideRight; text: "按键  " + (settings.controller.buttons || "—") + "     LT " + Number(settings.controller.axes[4]).toFixed(2) + " / RT " + Number(settings.controller.axes[5]).toFixed(2); color: "#cfdee8"; role: "caption" }
                    MouseArea { anchors.fill: parent; onClicked: { settings.tester = true; settings.activity() } }
                }
                Ui.FocusFrame {
                    objectName: "settingsDetailFocus"
                    x: 0
                    y: settingRows.y + (settingRows.currentItem ? settingRows.currentItem.y - settingRows.contentY : 0)
                    width: settingRows.rowWidth
                    height: settingRows.currentItem ? settingRows.currentItem.height : Ui.Theme.rowHeight
                    visible: settings.category !== 2 && (!settingRows.currentItem || settingRows.currentItem.y >= settingRows.contentY)
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
            if (key === "netScan") {
                if (index === settings.network.accessPoints.length) { close(); settings.network.scan(); return }
                if (!settings.network.selectAccessPoint(index)) return
                close()
                if (settings.network.selectedNetwork.security === "psk") settings.wifiPasswordRequested(settings.network.selectedNetwork.ssid)
                else settings.network.connectSelected("")
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
