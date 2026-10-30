import QtQuick
import "../gaming-shell/controls" as Ui

// Rendered once for early boot; no Qt process is needed on the device.
Rectangle {
    width: 1024; height: 768; color: Ui.Theme.ground
    Rectangle {
        x: 448; y: 232; width: 128; height: 128; radius: Ui.Theme.radiusPanel
        color: Ui.Theme.accent
        Text {
            anchors.centerIn: parent; text: "J"; color: Ui.Theme.accentText
            font.family: Ui.Theme.fontFamily; font.pixelSize: 84; font.weight: Font.Bold
        }
    }
    Text {
        anchors.horizontalCenter: parent.horizontalCenter; y: 384
        text: "Jume"; color: Ui.Theme.text
        font.family: Ui.Theme.fontFamily; font.pixelSize: 48; font.weight: Font.Bold
    }
    Ui.Label {
        anchors.horizontalCenter: parent.horizontalCenter; y: 510
        text: "正在准备桌面，请稍候"; role: "body"; color: Ui.Theme.textSecondary
    }
}
