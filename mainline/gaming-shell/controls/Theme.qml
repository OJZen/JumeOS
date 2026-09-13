pragma Singleton
import QtQuick

QtObject {
    property real fontScale: 1
    property bool reducedMotion: false
    readonly property color background: "#111a24"
    readonly property color surface: "#1c2934"
    readonly property color raised: "#243b43"
    readonly property color accent: "#99efdb"
    readonly property color accentText: "#173a35"
    readonly property color text: "#f1f6fa"
    readonly property color muted: "#afc1cc"
    readonly property color outline: "#40535f"
    readonly property color track: "#435765"
    readonly property color warning: "#f5d68a"
    readonly property color danger: "#f0b991"
    readonly property int smallGap: 4
    readonly property int gap: 8
    readonly property int labelGap: 12
    readonly property int padding: 20
    readonly property int radius: 12
    readonly property int pageMargin: 36
    readonly property int contentWidth: 952
    readonly property int rowHeight: 60
    readonly property int descriptionRowHeight: 84
    readonly property int buttonHeight: 48
    readonly property int fieldHeight: 56
    readonly property int hitHeight: 48
    readonly property int sidebarWidth: 256
    readonly property int columnGap: 32
    readonly property int detailX: sidebarWidth + columnGap
    readonly property int detailWidth: contentWidth - detailX
    readonly property int toolTop: 100
    readonly property int toolHeight: 576
    readonly property int contentY: 84
    readonly property int titleSize: 26
    readonly property int sectionSize: 20
    readonly property int bodySize: 18
    readonly property int captionSize: 14
    readonly property int microSize: 12
    readonly property int iconSize: 24
    readonly property int headerIconSize: 32
    readonly property int switchWidth: 56
    readonly property int switchHeight: 32
    readonly property int thumbSize: 24
    readonly property int trackHeight: 4
    readonly property int scrollGutter: 8
    readonly property int focusDuration: 90
    readonly property int controlDuration: 100
    readonly property int pageDuration: 140
    readonly property int popupDuration: 150
    readonly property var curve: [0.23, 1, 0.32, 1, 1, 1]
}
