pragma ComponentBehavior: Bound
import QtQuick
import "../controls" as Ui

Item {
    id: gallery
    width: 1024; height: 768
    required property var tableModel
    property real fontScale: 1
    property bool reducedMotion: false
    property bool night: false
    // "controls" exercises the shared controls; "foundations" mirrors Foundations.png;
    // "buttons", "rows" and "cards" mirror the sections of Components.png.
    property string page: "controls"
    property int presses: 0
    component Sample: Text {
        property string type: "body"
        color: Ui.Theme.text; font.family: Ui.Theme.fontFamily; textFormat: Text.PlainText
        font.pixelSize: Ui.Theme.fontSize(type); font.weight: Ui.Theme.type[type].weight
        lineHeightMode: Text.FixedHeight; lineHeight: Ui.Theme.lineHeight(type)
    }
    function visitLast() { list.currentIndex = 1999; table.positionViewAtRow(1999, TableView.AlignBottom) }
    Binding { target: Ui.Theme; property: "fontScale"; value: gallery.fontScale }
    Binding { target: Ui.Theme; property: "reducedMotion"; value: gallery.reducedMotion }
    Binding { target: Ui.Theme; property: "night"; value: gallery.night }
    Rectangle { anchors.fill: parent; color: Ui.Theme.ground }
    Item {
        anchors.fill: parent; visible: gallery.page === "controls"
        Ui.Label { x: 36; y: 30; text: "基础控件"; role: "title" }
        Ui.Tabs { x: 36; y: 88; model: ["常用", "列表", "表格"]; onActivated: function(index) { currentIndex = index } }
        Ui.Button { objectName: "galleryButton"; x: 36; y: 162; text: "确认"; primary: true; onClicked: gallery.presses++ }
        Ui.Button { x: 160; y: 162; text: "不可用"; enabled: false }
        Ui.Switch { objectName: "gallerySwitch"; x: 310; y: 168; Accessible.name: "测试开关" }
        Ui.Label { x: 390; y: 174; text: "状态标签"; role: "caption" }
        Ui.TextField { objectName: "galleryField"; x: 36; y: 238; width: 468; placeholderText: "输入测试文字"; maximumLength: 128 }
        Ui.Slider { objectName: "gallerySlider"; x: 36; y: 324; width: 468; value: 0.5; Accessible.name: "测试数值" }
        Ui.ProgressBar { objectName: "galleryProgress"; x: 36; y: 388; width: 468; value: Math.min(1, gallery.presses / 5) }
        Ui.Button { id: choice; objectName: "galleryChoice"; x: 36; y: 424; width: 468; text: "画质选项"; onClicked: choices.present(choice, ["流畅", "标准", "高清"], 1, "画质") }
        Ui.ListView {
            id: list; objectName: "galleryList"; x: 36; y: 508; width: 468; height: 216; model: 2000
            delegate: Ui.Button { required property int index; objectName: "galleryListRow"; width: list.width - 12; text: "列表项目 " + (index + 1); selected: list.currentIndex === index; onClicked: list.currentIndex = index }
        }
        Row {
            x: 540; y: 42; spacing: Ui.Theme.labelGap
            Repeater {
                model: ["monitor", "gamepad", "cartridge", "ports", "usb", "settings", "wifi", "cpu", "memory", "save"]
                Ui.Icon { required property string modelData; name: modelData; color: Ui.Theme.accent }
            }
        }
        Ui.Label { x: 540; y: 166; text: "表格 · 按需创建单元格"; role: "caption" }
        Ui.TableView { id: table; objectName: "galleryTable"; x: 540; y: 210; width: 448; height: 514; model: gallery.tableModel }
        Ui.ChoicePopup { id: choices; objectName: "galleryChoices"; parent: gallery; onActivated: function(index) { choice.text = options[index]; close() } }
    }
    Item {
        id: foundations; objectName: "galleryFoundations"
        anchors.fill: parent; visible: gallery.page === "foundations"
        // Stacked blocks; every Grid sizes columns to its widest entry, so nothing elides at 130%.
        Column {
            x: Ui.Theme.margin; y: Ui.Theme.space16; spacing: Ui.Theme.space12
            Sample { type: "title"; text: gallery.night ? "夜间模式 · 同名令牌换值" : "浅色 · 默认" }
            Row {
                objectName: "foundationColors"; spacing: Ui.Theme.space16
                Repeater {
                    model: [["ground", "surface", "surfaceSunken", "outline", "text", "textSecondary"],
                        ["textTertiary", "focus", "accent", "accentSoft", "accentInk", "glyph"],
                        ["glyphSoft", "danger", "warning", "scrim", "track", "switchOff"]]
                    Grid {
                        id: tokenColumn
                        required property var modelData
                        columns: 3; columnSpacing: Ui.Theme.space8; rowSpacing: 2; verticalItemAlignment: Grid.AlignVCenter
                        Repeater {
                            model: tokenColumn.modelData.length * 3
                            Loader {
                                id: cell
                                required property int index
                                readonly property string token: tokenColumn.modelData[Math.floor(index / 3)]
                                sourceComponent: index % 3 === 0 ? swatch : index % 3 === 1 ? tokenName : tokenValue
                                Component { id: swatch; Rectangle { width: 28; height: 28; radius: Ui.Theme.radiusBadge; color: Ui.Theme[cell.token]; border.width: 1; border.color: Ui.Theme.outline } }
                                Component { id: tokenName; Sample { type: "micro"; text: cell.token } }
                                Component { id: tokenValue; Sample { type: "micro"; color: Ui.Theme.textSecondary; text: Ui.Theme[cell.token].toString().toUpperCase() } }
                            }
                        }
                    }
                }
            }
            // Spacing scale, corner radii and the focus geometry (4 px stroke, ground gap, radius + 7).
            Row {
                objectName: "foundationShapes"; spacing: Ui.Theme.space24
                Row {
                    anchors.bottom: parent.bottom; spacing: Ui.Theme.space8
                    Repeater {
                        model: [Ui.Theme.space4, Ui.Theme.space8, Ui.Theme.space12, Ui.Theme.space16, Ui.Theme.space24, Ui.Theme.space32, Ui.Theme.space40, Ui.Theme.space48]
                        Rectangle { required property int modelData; anchors.bottom: parent.bottom; width: modelData; height: modelData; color: Ui.Theme.accent }
                    }
                }
                Row {
                    anchors.bottom: parent.bottom; spacing: Ui.Theme.space8
                    Repeater {
                        model: [Ui.Theme.radiusBadge, Ui.Theme.radiusKey, Ui.Theme.radiusRow, Ui.Theme.radiusGridCard, Ui.Theme.radiusCard, Ui.Theme.radiusPanel]
                        Rectangle { required property int modelData; width: 56; height: 56; radius: modelData; color: Ui.Theme.surfaceSunken }
                    }
                }
                Rectangle { anchors.verticalCenter: focusSample.verticalCenter; width: 56; height: 56; radius: Ui.Theme.radiusCard; color: Ui.Theme.cardColor(1) }
                Rectangle {
                    id: focusSample
                    width: 56 + 2 * (Ui.Theme.focusWidth + Ui.Theme.focusGap); height: width
                    radius: Ui.Theme.radiusCard + Ui.Theme.focusRadiusExtra; color: Ui.Theme.ground
                    border.width: Ui.Theme.focusWidth; border.color: Ui.Theme.focus
                    Rectangle { anchors.centerIn: parent; width: 56; height: 56; radius: Ui.Theme.radiusCard; color: Ui.Theme.cardColor(0) }
                }
            }
            // Type ramp: role and metrics, then a sample at that role.
            Grid {
                objectName: "foundationRamp"
                columns: 2; columnSpacing: Ui.Theme.space24; verticalItemAlignment: Grid.AlignVCenter
                Repeater {
                    id: rampCells
                    readonly property var entries: [["display", "Metal Slug · 主页焦点标题"], ["title", "游戏库 · 页面标题"], ["headline", "快捷面板 · 浮层标题"],
                        ["body", "减少动态效果 · 列表项"], ["label", "5 分钟 · 数值、提示栏"], ["caption", "Neo Geo · 上次游玩 昨天"], ["micro", "已暂停 · 可读下限"]]
                    model: entries.length * 2
                    Sample {
                        required property int index
                        readonly property var entry: rampCells.entries[Math.floor(index / 2)]
                        type: index % 2 === 0 ? "micro" : entry[0]
                        color: index % 2 === 0 ? Ui.Theme.textTertiary : Ui.Theme.text
                        text: index % 2 === 0 ? entry[0] + " " + Ui.Theme.type[entry[0]].size + "/" + Ui.Theme.type[entry[0]].line : entry[1]
                    }
                }
            }
        }
    }
    Column {
        objectName: "componentButtons"; visible: gallery.page === "buttons"
        x: Ui.Theme.margin; y: Ui.Theme.space16; spacing: Ui.Theme.space24
        Sample { type: "title"; text: "按钮 · 开关 · 滑块 · 标签" }
        Grid {
            columns: 5; columnSpacing: Ui.Theme.space24; rowSpacing: Ui.Theme.space24; verticalItemAlignment: Grid.AlignVCenter
            Item { width: 1; height: 1 } // Positioners skip empty items; this keeps the corner cell.
            Repeater { model: ["默认", "聚焦", "按下", "禁用"]; Sample { required property string modelData; type: "micro"; color: Ui.Theme.textSecondary; text: modelData } }
            Repeater {
                model: 15
                Loader {
                    id: cell
                    required property int index
                    readonly property var spec: [["主要", "primary", "开始游戏"], ["次要", "secondary", "重新扫描"], ["危险", "danger", "结束游戏"]][Math.floor(index / 5)]
                    readonly property int column: index % 5
                    sourceComponent: column === 0 ? rowLabel : variantButton
                    Component { id: rowLabel; Sample { type: "micro"; text: cell.spec[0] } }
                    Component {
                        id: variantButton
                        Ui.Button {
                            text: cell.spec[2]; variant: cell.spec[1]
                            selected: cell.column === 2 || cell.column === 3; down: cell.column === 3 ? true : undefined; enabled: cell.column !== 4
                        }
                    }
                }
            }
        }
        Row {
            spacing: Ui.Theme.space32
            Ui.Switch { Accessible.name: "关" }
            Ui.Switch { checked: true; Accessible.name: "开" }
            Ui.Switch { checked: true; selected: true; Accessible.name: "聚焦" }
            Ui.Switch { enabled: false; Accessible.name: "禁用" }
        }
        Row {
            spacing: Ui.Theme.space32
            Ui.Slider { width: 360; value: 0.55; Accessible.name: "普通" }
            Ui.Slider { width: 360; value: 0.7; adjusting: true; Accessible.name: "调整中" }
        }
        Row {
            spacing: Ui.Theme.space32
            Ui.ProgressBar { width: 360; value: 0.6; anchors.verticalCenter: parent.verticalCenter }
            Ui.ProgressBar { width: 360; indeterminate: true; anchors.verticalCenter: parent.verticalCenter }
        }
        Ui.Tabs { model: ["全部", "收藏", "最近"]; currentIndex: 0 }
        Ui.Tabs { model: ["全部", "收藏", "最近"]; currentIndex: 1; navigationActive: true }
    }
    Row {
        objectName: "componentRows"; visible: gallery.page === "rows"
        x: Ui.Theme.margin; y: Ui.Theme.space16; spacing: Ui.Theme.space32
        Column {
            width: 520; spacing: Ui.Theme.space8
            Sample { type: "title"; text: "列表行 · 72 / 96" }
            Ui.ListRow { width: parent.width; title: "基本行 · 进入下一级"; chevron: true }
            Ui.ListRow { width: parent.width; title: "选择行"; value: "跟随时间"; choice: true }
            Ui.ListRow { width: parent.width; title: "开关行"; toggleState: 1 }
            Ui.ListRow { width: parent.width; title: "说明行 · 聚焦"; description: "第二行写结果或影响，不超过一行"; chevron: true; selected: true }
            Ui.ListRow { width: parent.width; title: "滑块行"; value: "55%"; progress: 0.55; selected: true; focusOutline: false }
            Ui.ListRow { width: parent.width; title: "只读行"; value: "Linux 6.12"; actionable: false }
            Ui.ListRow { width: parent.width; title: "禁用行"; disabledReason: "需要先连接 Wi-Fi" }
        }
        Column {
            spacing: Ui.Theme.space16
            Sample { type: "title"; text: "按键徽标" }
            Flow {
                width: 360; spacing: Ui.Theme.space8
                Repeater { model: ["A", "B", "X", "Y", "L1", "R2", "Start", "Select", "dpad", "R3"]; Ui.GlyphBadge { required property string modelData; button: modelData } }
            }
            Row {
                spacing: Ui.Theme.space4
                Ui.GlyphBadge { button: "Select" }
                Sample { type: "micro"; color: Ui.Theme.textTertiary; text: "+"; anchors.verticalCenter: parent.verticalCenter }
                Ui.GlyphBadge { button: "Start" }
                Item { width: Ui.Theme.space16; height: 1 }
                Ui.GlyphBadge { button: "X"; progress: 0.6 }
            }
            Flow {
                width: 360; spacing: Ui.Theme.space8
                Repeater { model: ["A", "B", "X", "Y", "L1", "R2", "Start", "Select"]; Ui.GlyphBadge { required property string modelData; button: modelData; soft: true; size: Ui.Theme.glyphInlineSize } }
            }
            Row {
                spacing: Ui.Theme.space8
                Repeater { model: ["X", "B", "Y", "R2", "L2", "Start"]; Ui.GlyphBadge { required property string modelData; button: modelData; size: Ui.Theme.glyphKeySize } }
            }
            Ui.HintBar { width: 360; actions: [{button: "A", label: "开始"}, {button: "B", label: "返回"}, {button: "X", label: "收藏"}] }
        }
    }
    Column {
        objectName: "componentCards"; visible: gallery.page === "cards"
        x: Ui.Theme.margin; y: Ui.Theme.space16; spacing: Ui.Theme.space12
        Sample { type: "headline"; text: "卡片 · 入口 · 系统反馈" }
        Row {
            spacing: Ui.Theme.space32
            Repeater {
                model: [{title: "1944", color: 4}, {title: "GTA III", color: 1, badge: "已暂停", icon: "pause", selected: true},
                        {title: "Moonlight", color: 2, app: "streaming", favorite: true}, {title: "Stardew", available: false, badge: "尚未适配"}]
                Column {
                    id: gridCard
                    required property var modelData
                    spacing: Ui.Theme.space8
                    Ui.GameCard {
                        width: Ui.Theme.gridCard; height: width; title: gridCard.modelData.title
                        cardColor: Ui.Theme.cardColor(gridCard.modelData.color || 0); badge: gridCard.modelData.badge || ""
                        badgeIcon: gridCard.modelData.icon || ""; iconName: gridCard.modelData.app || ""; favorite: !!gridCard.modelData.favorite
                        selected: !!gridCard.modelData.selected; available: gridCard.modelData.available !== false
                    }
                    Sample {
                        type: "label"; text: gridCard.modelData.title
                        color: gridCard.modelData.available === false ? Ui.Theme.textTertiary : gridCard.modelData.selected ? Ui.Theme.accentInk : Ui.Theme.text
                    }
                }
            }
        }
        Row {
            spacing: Ui.Theme.space32
            Row {
                spacing: Ui.Theme.dockGap
                Ui.DockTile { iconName: "folder"; label: "文件" }
                Ui.DockTile { iconName: "settings"; label: "设置"; selected: true }
                Ui.DockTile { iconName: "power"; label: "电源"; available: false }
            }
            Ui.HoldConfirm { progress: 0.4; detail: "GTA III · 未存档进度会丢失" }
        }
        Row {
            spacing: Ui.Theme.space32
            Ui.Hud { shown: true; value: 0.55; iconName: "volume" }
            Ui.Hud { shown: true; value: 0.7; iconName: "sun" }
        }
        Row {
            spacing: Ui.Theme.space32
            Ui.Toast { text: "已加入收藏"; maximumWidth: 456 }
            Ui.Toast { text: "设置未能保存，已保留修改"; error: true; maximumWidth: 456 }
        }
    }
}
