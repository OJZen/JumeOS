pragma ComponentBehavior: Bound
import QtQuick
import "controls" as Ui

Item {
    id: view
    required property var calibration
    property real fontScale: 1
    readonly property int phase: calibration ? calibration.phase : 0
    readonly property var values: calibration ? (phase === 3 ? calibration.previewAxes : calibration.rawAxes) : [0, 0, 0, 0]
    Column {
        width: parent.width; spacing: Ui.Theme.space16
        Ui.Label {
            width: parent.width; role: "headline"; fontScale: view.fontScale
            text: view.phase === 4 ? "恢复默认校准" : ["", "1 / 3 · 记录中点", "2 / 3 · 采集行程", "3 / 3 · 检查并保存"][view.phase] || ""
        }
        Ui.Label {
            width: parent.width; wrapMode: Text.Wrap; fontScale: view.fontScale; color: Ui.Theme.textSecondary
            text: view.phase === 1 ? "松开左右摇杆，保持稳定后按 A 记录中点"
                : view.phase === 2 ? "两个摇杆都向四个方向推满，再沿边缘转动两圈"
                : view.phase === 3 ? "检查上下左右是否达到 ±1.00；松开回中后按 A 保存"
                : "将移除两个摇杆已保存的补偿，恢复默认范围"
        }
        Row {
            width: parent.width; spacing: Ui.Theme.space32; visible: view.phase !== 4
            Repeater {
                model: 2
                Column {
                    id: stick
                    required property int index
                    width: (parent.width - Ui.Theme.space32) / 2; spacing: Ui.Theme.space8
                    Ui.Label {
                        anchors.horizontalCenter: parent.horizontalCenter; role: "label"; fontScale: view.fontScale
                        text: stick.index === 0 ? "左摇杆" : "右摇杆"
                    }
                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 160; height: 160; radius: 80; color: Ui.Theme.surfaceSunken; border.color: Ui.Theme.outline
                        Rectangle { x: 79; width: 1; height: 160; color: Ui.Theme.outline }
                        Rectangle { y: 79; width: 160; height: 1; color: Ui.Theme.outline }
                        Rectangle {
                            x: 70 + Number(view.values[stick.index * 2]) * 68
                            y: 70 + Number(view.values[stick.index * 2 + 1]) * 68
                            width: 20; height: 20; radius: 10; color: Ui.Theme.accent
                        }
                    }
                    Ui.Label {
                        anchors.horizontalCenter: parent.horizontalCenter; role: "caption"; fontScale: view.fontScale; tabular: true
                        text: "X " + Number(view.values[stick.index * 2]).toFixed(2) + "   Y " + Number(view.values[stick.index * 2 + 1]).toFixed(2)
                    }
                    Repeater {
                        model: view.phase === 2 ? 2 : 0
                        Ui.Label {
                            required property int index
                            readonly property var range: view.calibration.ranges[stick.index * 2 + index]
                            anchors.horizontalCenter: stick.horizontalCenter; role: "caption"; fontScale: view.fontScale; tabular: true
                            color: range.complete ? Ui.Theme.accent : Ui.Theme.textSecondary
                            text: (index === 0 ? "X  " : "Y  ") + Number(range.minimum).toFixed(2) + " … " + Number(range.maximum).toFixed(2)
                        }
                    }
                }
            }
        }
        Ui.Label {
            objectName: "calibrationStatus"
            width: parent.width; wrapMode: Text.Wrap; fontScale: view.fontScale; role: "caption"
            color: view.calibration && view.calibration.error ? Ui.Theme.danger : Ui.Theme.textSecondary
            text: !view.calibration ? "" : view.calibration.error || (view.phase === 1
                ? (view.calibration.canAdvance ? "中点稳定，可以继续" : "等待摇杆回中并稳定…")
                : view.phase === 2 ? (view.calibration.canAdvance ? "四根轴的行程已采集，可以检查结果" : "继续采集，完成的轴会变为绿色")
                : view.phase === 3 ? (view.calibration.canAdvance ? "已回中，可以保存" : "请松开摇杆后保存") : "按 B 可取消")
        }
    }
}
