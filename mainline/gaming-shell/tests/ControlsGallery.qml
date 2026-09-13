pragma ComponentBehavior: Bound
import QtQuick
import "../controls" as Ui

Item {
    id: gallery
    width: 1024; height: 768
    required property var tableModel
    property real fontScale: 1
    property bool reducedMotion: false
    property int presses: 0
    function visitLast() { list.currentIndex = 1999; table.positionViewAtRow(1999, TableView.AlignBottom) }
    Binding { target: Ui.Theme; property: "fontScale"; value: gallery.fontScale }
    Binding { target: Ui.Theme; property: "reducedMotion"; value: gallery.reducedMotion }
    Rectangle { anchors.fill: parent; color: Ui.Theme.background }
    Ui.Label { x: 36; y: 30; text: "基础控件"; role: "title" }
    Ui.NavigationBar { x: 36; y: 88; model: ["常用", "列表", "表格"]; onActivated: function(index) { currentIndex = index } }
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
