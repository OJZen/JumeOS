import QtQuick

// Shared 72-high top bar (§4, §8): the Jume mark and name, or a page title, on the left; night,
// Wi-Fi, battery and time on the right, all on one centerline with tabular figures.
Item {
    id: bar
    property string title: ""
    property bool statusVisible: true
    property int wifiSignal: -1
    property bool wifiKnown: wifiSignal >= 0
    property int batteryPercent: -1
    property bool charging: false
    property bool nightIcon: false
    property string clock: ""
    // Replaces device status when there is none, e.g. "本地界面预览".
    property string note: ""
    property real fontScale: Theme.fontScale
    implicitHeight: Theme.topBarHeight
    Row {
        id: brand
        anchors.verticalCenter: parent.verticalCenter; spacing: Theme.space12
        visible: bar.title === ""
        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: 36; height: 36; radius: Theme.radiusBadge; color: Theme.accent
            Label { anchors.centerIn: parent; text: "J"; role: "headline"; fontScale: 1; color: Theme.accentText; elide: Text.ElideNone }
        }
        Label { objectName: "brandName"; anchors.verticalCenter: parent.verticalCenter; text: "Jume"; role: "headline"; fontScale: bar.fontScale; elide: Text.ElideNone }
    }
    Label {
        objectName: "topBarTitle"; anchors.verticalCenter: parent.verticalCenter
        visible: bar.title !== ""; text: bar.title; role: "title"; fontScale: bar.fontScale; elide: Text.ElideNone
    }
    Row {
        id: status
        anchors.right: parent.right; anchors.verticalCenter: parent.verticalCenter; spacing: Theme.space16
        visible: bar.statusVisible
        Icon { anchors.verticalCenter: parent.verticalCenter; visible: bar.nightIcon; name: "moon"; color: Theme.textSecondary }
        Rectangle {
            anchors.verticalCenter: parent.verticalCenter; visible: bar.note !== ""
            width: noteLabel.implicitWidth + 2 * Theme.space16; height: Theme.glyphInlineSize; radius: height / 2; color: Theme.surfaceSunken
            Label { id: noteLabel; anchors.centerIn: parent; role: "micro"; fontScale: bar.fontScale; text: bar.note; color: Theme.textSecondary; elide: Text.ElideNone }
        }
        Item {
            objectName: "statusWifi"
            readonly property int level: bar.wifiSignal
            anchors.verticalCenter: parent.verticalCenter; visible: bar.note === ""
            width: Theme.iconSize; height: Theme.iconSize
            Accessible.role: Accessible.Indicator
            Accessible.name: bar.wifiKnown ? "Wi-Fi " + bar.wifiSignal + "%" : "Wi-Fi 未连接"
            Icon { objectName: "statusWifiIcon"; anchors.fill: parent; name: "wifi"; color: bar.wifiKnown ? Theme.textSecondary : Theme.disabledText }
        }
        Row {
            anchors.verticalCenter: parent.verticalCenter; spacing: Theme.space8; visible: bar.note === ""
            Icon { objectName: "statusBatteryIcon"; anchors.verticalCenter: parent.verticalCenter; name: bar.charging ? "battery-charging" : "battery"; color: bar.charging ? Theme.accent : Theme.textSecondary }
            Label {
                objectName: "statusBattery"; anchors.verticalCenter: parent.verticalCenter
                role: "label"; tabular: true; fontScale: bar.fontScale; color: Theme.textSecondary; elide: Text.ElideNone
                text: bar.batteryPercent < 0 ? "—" : bar.batteryPercent + "%"
            }
        }
        Label { objectName: "statusClock"; anchors.verticalCenter: parent.verticalCenter; role: "body"; tabular: true; fontScale: bar.fontScale; text: bar.clock; elide: Text.ElideNone }
    }
}
