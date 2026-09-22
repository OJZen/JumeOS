import QtQuick
import QtQuick.Window
import QtQuick.Shapes
import QtWebEngine
import "controls" as Ui

Rectangle {
    id: root
    width: 1024; height: 768; color: Ui.Theme.background
    required property string statePath
    required property string versionText
    property bool selfTest: false
    property var tabs: []
    property int selected: 0
    readonly property var current: tabs.length ? tabs[selected] : null
    property string notice: ""
    property bool menuOpen: false
    property bool aboutOpen: false
    readonly property bool editing: Qt.inputMethod.visible
    function tell(text) { notice = text; noticeTimer.restart() }
    function addTab(url) {
        if (tabs.length >= 3) { tell("最多打开 3 个标签页，请先关闭一个"); return null }
        const page = pageComponent.createObject(pages, {url: url || "about:blank"})
        if (!page) { tell("无法创建网页"); return null }
        tabs = tabs.concat([page]); selected = tabs.length - 1
        return page
    }
    function closeTab() {
        const old = current
        const remaining = tabs.slice(); remaining.splice(selected, 1)
        selected = Math.max(0, selected - 1); tabs = remaining
        old.destroy()
        if (!tabs.length) addTab()
    }
    function focusAddress() {
        menuOpen = false; address.text = current.url.toString() === "about:blank" ? "" : current.url.toString()
        address.forceActiveFocus(); address.selectAll(); Qt.inputMethod.show()
    }
    Shortcut { sequence: "Ctrl+L"; onActivated: root.focusAddress() }
    Shortcut { sequence: "Ctrl+T"; onActivated: root.addTab() }
    Shortcut { sequence: "Ctrl+W"; onActivated: root.closeTab() }
    Shortcut { sequence: "Alt+Left"; enabled: !!root.current; onActivated: root.current.goBack() }
    Shortcut { sequence: "Alt+Right"; enabled: !!root.current; onActivated: root.current.goForward() }
    Shortcut { sequence: "Ctrl+R"; enabled: !!root.current; onActivated: root.current.reload() }
    Shortcut { sequence: "F5"; enabled: !!root.current; onActivated: root.current.reload() }
    function navigate() {
        const url = pad.address(address.text)
        if (!url.toString()) { tell("请输入网址或搜索内容；不允许本地文件和外部协议"); return }
        current.url = url; current.forceActiveFocus(); Qt.inputMethod.hide()
    }
    function command(name) {
        if (aboutOpen) { if (name === "back") aboutOpen = false; return }
        if (editing) {
            if (name === "dismiss") { Qt.inputMethod.hide(); current.forceActiveFocus() }
            else if (name === "submit") {
                if (address.activeFocus) navigate()
                else {
                    Qt.inputMethod.commit(); Qt.inputMethod.hide(); current.forceActiveFocus()
                    Qt.callLater(function() { pad.key("accept") })
                }
            } else if ((name === "left" || name === "right") && keyboard.item && keyboard.item.navigateHorizontal(name)) return
            else pad.key(name)
            return
        }
        if (name === "back") current.goBack()
        else if (name === "forward") current.goForward()
        else if (name === "reload") current.reload()
        else if (name === "address") focusAddress()
        else if (name === "keyboard") Qt.inputMethod.show()
        else if (name === "previousTab") selected = (selected + tabs.length - 1) % tabs.length
        else if (name === "nextTab") selected = (selected + 1) % tabs.length
    }
    onSelectedChanged: { Qt.inputMethod.hide(); if (current) current.forceActiveFocus() }
    Binding { target: pad; property: "keyboard"; value: root.editing }
    Connections { target: pad; function onAction(name) { root.command(name) } }
    Timer { id: noticeTimer; interval: 6000; onTriggered: root.notice = "" }
    WebEngineProfile {
        id: profile
        storageName: "JumeBrowser"
        offTheRecord: root.selfTest
        persistentStoragePath: root.statePath + "/profile"
        cachePath: root.statePath + "/cache"
        httpCacheMaximumSize: 32 * 1024 * 1024
        // Downloads stay unaccepted until a safe destination/confirmation UI exists.
        onDownloadRequested: function(download) { download.cancel(); root.tell("此预览版尚未开放下载") }
    }
    Component {
        id: pageComponent
        WebEngineView {
            id: page
            anchors.fill: parent
            profile: profile
            visible: root.current === page
            lifecycleState: visible || recommendedState === WebEngineView.LifecycleState.Active ? WebEngineView.LifecycleState.Active : WebEngineView.LifecycleState.Frozen
            settings.fullScreenSupportEnabled: false // Keep the trusted address bar visible.
            settings.localContentCanAccessFileUrls: false
            settings.localContentCanAccessRemoteUrls: false
            settings.javascriptCanAccessClipboard: false
            settings.playbackRequiresUserGesture: true
            onNavigationRequested: function(request) {
                if (root.selfTest && request.url.toString().startsWith("data:text/html")) return
                if (!pad.allowedUrl(request.url)) { request.reject(); root.tell("已阻止不支持的地址协议") }
            }
            onCertificateError: function(error) { error.rejectCertificate(); root.tell("证书无效，连接已阻止") }
            onPermissionRequested: function(permission) { permission.deny(); root.tell("此预览版不开放网站设备权限") }
            onFileDialogRequested: function(request) { request.accepted = true; request.dialogReject(); root.tell("此预览版不开放本地文件上传") }
            onNewWindowRequested: function(request) {
                if (!request.userInitiated || !pad.allowedUrl(request.requestedUrl)) return
                const target = root.addTab()
                if (target) target.acceptAsNewWindow(request)
            }
            onWindowCloseRequested: { if (root.current === page) root.closeTab() }
            onRenderProcessTerminated: root.tell("网页进程已退出，按 X 重新加载")
            onLoadingChanged: function(info) {
                if (root.selfTest) console.log("BROWSER_TEST_LOAD", info.status, info.errorCode, info.errorString)
                if (info.status === WebEngineView.LoadFailedStatus) root.tell("页面加载失败，请检查网络后按 X 重试")
            }
        }
    }
    // Chrome-like tab strip and omnibox, with handheld-sized controls.
    Row {
        x: 8; y: 4; spacing: 8
        Repeater {
            model: root.tabs
            Ui.Button {
                required property var modelData
                required property int index
                width: 236; height: 48; selected: index === root.selected
                text: modelData.title || "新标签页"
                onClicked: root.selected = index
            }
        }
        Ui.Button { width: 48; implicitWidth: 48; text: "+"; Accessible.name: "新标签页"; enabled: root.tabs.length < 3; onClicked: root.addTab() }
        Ui.Button { width: 48; implicitWidth: 48; text: "×"; Accessible.name: "关闭当前标签页"; onClicked: root.closeTab() }
    }
    Row {
        id: toolbar
        x: 8; y: 60; spacing: 8
        Ui.Button { width: 64; implicitWidth: 64; text: "‹"; Accessible.name: "返回"; enabled: root.current && root.current.canGoBack; onClicked: root.current.goBack() }
        Ui.Button { width: 64; implicitWidth: 64; text: "›"; Accessible.name: "前进"; enabled: root.current && root.current.canGoForward; onClicked: root.current.goForward() }
        Ui.Button { width: 80; implicitWidth: 80; text: root.current && root.current.loading ? "停止" : "刷新"; onClicked: root.current.loading ? root.current.stop() : root.current.reload() }
        Ui.TextField {
            id: address; width: root.width - 344; height: 48
            placeholderText: "搜索或输入网址"; maximumLength: 8192
            inputMethodHints: Qt.ImhUrlCharactersOnly | Qt.ImhNoPredictiveText
            Accessible.name: "地址栏"
            onAccepted: root.navigate()
        }
        Ui.Button { width: 80; implicitWidth: 80; text: "菜单"; onClicked: root.menuOpen = !root.menuOpen }
    }
    Binding { target: address; property: "text"; when: !address.activeFocus; value: root.current && root.current.url.toString() !== "about:blank" ? root.current.url.toString() : "" }
    Rectangle { x: 0; y: 116; height: 3; width: root.current ? root.width * root.current.loadProgress / 100 : 0; color: Ui.Theme.accent; visible: root.current && root.current.loading }
    Item { id: pages; x: 0; y: 120; width: root.width; height: root.height - y - hints.height - (root.editing && keyboard.item ? keyboard.height : 0) }
    Rectangle {
        anchors.fill: pages; color: Ui.Theme.background
        visible: root.current && root.current.url.toString() === "about:blank"
        Column {
            anchors.centerIn: parent; spacing: 20; width: 640
            Ui.Label { width: parent.width; text: "Jume Browser"; role: "title"; horizontalAlignment: Text.AlignHCenter }
            Ui.Label { width: parent.width; text: "Start 输入网址 · 右摇杆移动光标 · B 点击"; horizontalAlignment: Text.AlignHCenter }
            Ui.Button { anchors.horizontalCenter: parent.horizontalCenter; width: 300; text: "搜索或输入网址"; onClicked: root.focusAddress() }
            Ui.Label { width: parent.width; text: root.versionText + "\n开发预览 · 请勿用于敏感账户"; role: "caption"; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap }
        }
    }
    Rectangle {
        id: hints; x: 0; y: root.height - height; width: root.width; height: 32; color: Ui.Theme.surface
        Ui.Label { anchors.centerIn: parent; role: "caption"; text: root.editing ? "方向键选字   B 输入   X 退格   Y 收起   Start 确认" : "左杆滚动   右杆光标   B 点击   Y 返回   A 前进   X 刷新   L1/R1 标签   Start 地址   Select 键盘" }
    }
    Loader {
        id: keyboard; x: 0; y: hints.y - height; width: root.width
        source: "KeyboardPanel.qml"; visible: root.editing
        onStatusChanged: if (status === Loader.Error) root.tell("软键盘不可用，请检查运行时组件")
    }
    Rectangle {
        x: root.width - width - 8; y: 116; width: 340; height: menu.height + 24
        radius: Ui.Theme.radius; color: Ui.Theme.surface; border.color: Ui.Theme.outline; visible: root.menuOpen
        Column {
            id: menu; x: 12; y: 12; spacing: 8; width: parent.width - 24
            Ui.Button { width: parent.width; text: "新标签页"; onClicked: { root.addTab(); root.menuOpen = false } }
            Ui.Button { width: parent.width; text: "缩小网页"; enabled: root.current && root.current.zoomFactor > .5; onClicked: root.current.zoomFactor = Math.max(.5, root.current.zoomFactor - .1) }
            Ui.Button { width: parent.width; text: "放大网页"; enabled: root.current && root.current.zoomFactor < 2; onClicked: root.current.zoomFactor = Math.min(2, root.current.zoomFactor + .1) }
            Ui.Button { width: parent.width; text: "图形加速诊断"; onClicked: { root.current.url = "chrome://gpu"; root.menuOpen = false } }
            Ui.Button { width: parent.width; text: "关于 Jume Browser"; onClicked: { root.aboutOpen = true; root.menuOpen = false } }
            Ui.Button { width: parent.width; text: "退出浏览器"; onClicked: Qt.quit() }
        }
    }
    Rectangle {
        x: 24; y: 128; width: root.width - 48; height: 56; radius: Ui.Theme.radius
        color: Ui.Theme.surface; border.color: Ui.Theme.warning; visible: root.notice !== ""
        Ui.Label { anchors.fill: parent; anchors.margins: 12; text: root.notice; wrapMode: Text.Wrap }
    }
    Rectangle {
        id: about; anchors.fill: parent; visible: root.aboutOpen; z: 20; color: Ui.Theme.background
        MouseArea { anchors.fill: parent } // Do not click through to the page.
        Column {
            anchors.centerIn: parent; width: parent.width - 72; spacing: 20
            Ui.Label { text: "关于 Jume Browser"; role: "title" }
            Ui.Label { width: parent.width; text: root.versionText; wrapMode: Text.Wrap }
            Ui.Label { width: parent.width; text: "https://github.com/OJZen/JumeOS"; wrapMode: Text.Wrap }
            Ui.Label { width: parent.width; text: "开发预览 · 安全补丁版本不等于完整 Chromium 功能版本"; role: "caption"; wrapMode: Text.Wrap }
            Ui.Button { text: "返回（Y）"; onClicked: root.aboutOpen = false }
        }
    }
    Shape {
        x: pad ? pad.position.x : 0; y: pad ? pad.position.y : 0; width: 24; height: 32
        visible: !root.editing && pad && pad.controllerPointer; enabled: false; z: 100
        preferredRendererType: Shape.GeometryRenderer
        ShapePath { strokeColor: "#111a24"; strokeWidth: 2; fillColor: "white"; PathSvg { path: "M1 1L1 26L8 20L14 31L19 28L13 18L23 17Z" } }
    }
    // No network or real profile is used by this smoke check.
    property int testStep: 0
    property double testRendererPid: 0
    Timer {
        interval: 200; repeat: true; running: root.selfTest
        onTriggered: {
            if (root.testStep === 0 && root.current) {
                root.testStep = 1
                root.current.loadHtml("<html><title>Jume offline check</title><body style='margin:0;height:3000px'><button id='b' style='position:absolute;left:450px;top:200px;width:124px;height:100px' onclick='this.textContent=42'>Test</button><input id='text' style='position:absolute;left:450px;top:320px'></body></html>", "https://jume.invalid/")
            } else if (root.testStep === 1 && !root.current.loading) {
                root.testStep = 2
                root.current.runJavaScript("document.title", function(value) {
                    // Initial about:blank can finish after loadHtml was queued.
                    // Wait for the fixture document, bounded by the C++ watchdog.
                    if (value !== "Jume offline check") { root.testStep = 1; return }
                    root.testRendererPid = root.current.renderProcessPid
                    pad.smokeInput(1)
                    root.testStep = 3
                })
            } else if (root.testStep === 3) {
                root.testStep = 4
                root.current.runJavaScript("document.getElementById('b').textContent", function(value) {
                    // Title readiness precedes Chromium's first hit-test frame.
                    if (value !== "42") { pad.smokeInput(1); root.testStep = 3; return }
                    pad.smokeInput(2); root.testStep = 5
                })
            } else if (root.testStep === 5) {
                root.testStep = 6
                root.current.runJavaScript("window.scrollY", function(value) {
                    if (!(value > 0)) { root.testStep = 5; return }
                    pad.smokeInput(3); root.testStep = 7
                })
            } else if (root.testStep === 7) {
                root.testStep = 8
                if (!root.editing || !keyboard.item || keyboard.height <= 0) { root.testStep = 7; return }
                address.text = ""; pad.smokeInput(4)
            } else if (root.testStep === 8) {
                if (!address.text.length) return
                Qt.inputMethod.hide(); root.current.forceActiveFocus()
                root.current.runJavaScript("document.getElementById('text').focus()")
                root.testStep = 9
            } else if (root.testStep === 9) {
                Qt.inputMethod.show(); root.testStep = 10
            } else if (root.testStep === 10) {
                if (!root.editing) return
                pad.smokeInput(4); root.testStep = 11
            } else if (root.testStep === 11) {
                root.testStep = 12
                root.current.runJavaScript("document.getElementById('text').value", function(value) {
                    if (!value.length) { root.testStep = 11; return }
                    Qt.inputMethod.hide(); root.current.forceActiveFocus(); root.testStep = 13
                })
            } else if (root.testStep === 13) {
                const tab = root.addTab(); root.closeTab()
                if (!tab || root.tabs.length !== 1 || !pad.allowedUrl("chrome://gpu") || pad.allowedUrl("file:///etc/passwd")) { Qt.exit(5); return }
                root.testStep = 17
                root.current.runJavaScript("JSON.stringify((function(){const c=document.createElement('canvas'); c.width=c.height=16; const g=c.getContext('webgl2')||c.getContext('webgl'); if(!g)return {available:false}; const e=g.getExtension('WEBGL_debug_renderer_info'); g.clearColor(0,0,1,1); g.clear(g.COLOR_BUFFER_BIT); const p=new Uint8Array(4); g.readPixels(0,0,1,1,g.RGBA,g.UNSIGNED_BYTE,p); return {available:true,renderer:g.getParameter(e?e.UNMASKED_RENDERER_WEBGL:g.RENDERER),vendor:g.getParameter(e?e.UNMASKED_VENDOR_WEBGL:g.VENDOR),version:g.getParameter(g.VERSION),pixel:Array.from(p),error:g.getError()};})())", function(value) {
                    console.log("BROWSER_WEBGL_RESULT", value); root.testStep = 14
                })
            } else if (root.testStep === 14) {
                root.aboutOpen = true; root.testStep = 15
            } else if (root.testStep === 15) {
                if (!about.visible || !root.versionText.includes("Qt WebEngine 6.10.2") || !root.versionText.includes("Chromium 134.0.6998.208") || !root.versionText.includes("144.0.7559.96")) { Qt.exit(13); return }
                root.command("reload"); if (!root.aboutOpen) { Qt.exit(14); return }
                root.command("back"); if (root.aboutOpen) { Qt.exit(15); return }
                root.aboutOpen = true; root.testStep = 16
            } else if (root.testStep === 16) {
                console.log("BROWSER_SMOKE_OK renderer,click,scroll,address-IME,page-IME,tabs,scheme-policy,about-version"); Qt.quit()
            }
        }
    }
    Component.onCompleted: root.addTab()
}
