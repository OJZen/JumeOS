import QtQuick

Item {
    id: header
    property string title: ""
    property string subtitle: ""
    property string iconName: ""
    property bool error: false
    property bool busy: false
    property bool backVisible: false
    property string actionText: ""
    property real progress: -1
    signal backRequested()
    signal actionRequested()
    implicitHeight: Theme.contentY
    Icon { width: Theme.headerIconSize; height: width; y: 8; name: header.iconName; color: Theme.accent; visible: header.iconName !== "" }
    Label {
        x: header.iconName ? Theme.headerIconSize + Theme.labelGap : 0
        width: parent.width - x - (header.backVisible ? back.width + Theme.padding : 0) - (action.visible ? action.width + Theme.gap : 0); height: Theme.buttonHeight
        text: header.title; role: "title"
    }
    Button { id: back; anchors.right: parent.right; text: "返回"; iconName: "chevron-left"; visible: header.backVisible; onClicked: header.backRequested() }
    Button { id: action; anchors.right: header.backVisible ? back.left : parent.right; anchors.rightMargin: header.backVisible ? Theme.gap : 0; text: header.actionText; visible: text !== ""; enabled: !header.busy; onClicked: header.actionRequested() }
    Label { y: Theme.buttonHeight + Theme.smallGap; width: parent.width; text: header.subtitle; role: "caption"; color: header.error ? Theme.danger : Theme.muted }
    ProgressBar { anchors.bottom: parent.bottom; anchors.bottomMargin: Theme.smallGap; width: parent.width; visible: header.busy; indeterminate: header.progress < 0; value: Math.max(0, header.progress) }
}
