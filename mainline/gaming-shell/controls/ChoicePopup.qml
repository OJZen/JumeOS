pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Templates as T
import "." as Ui

T.Popup {
    id: popup
    property string title: ""
    property var options: []
    property int currentIndex: 0
    property int pendingIndex: 0
    property point origin: Qt.point(0, 0)
    property real anchorTop: 0
    property real popupWidth: 430
    readonly property bool above: parent && origin.y + height > parent.height && anchorTop >= height + 6
    readonly property var hints: [["↑↓", "选择"], ["A / ↵", "确认"], ["B / Esc", "取消"]]
    signal activated(int index)
    popupType: T.Popup.Item
    modal: true; focus: true; dim: false; padding: 0; margins: 0
    closePolicy: T.Popup.CloseOnEscape | T.Popup.CloseOnPressOutside
    width: Math.min(parent ? parent.width : 0, popupWidth)
    height: Math.min(parent ? parent.height : 0, Theme.fieldHeight + Math.min(5, options.length) * (Theme.rowHeight + Theme.gap) + Theme.gap)
    x: Math.max(0, Math.min(parent ? parent.width - width : 0, origin.x - width))
    y: above ? anchorTop - height - 6 : Math.max(0, Math.min(parent ? parent.height - height : 0, origin.y))
    transformOrigin: above ? Item.BottomRight : Item.TopRight
    enter: Transition {
        Motion { property: "opacity"; from: 0; to: 1; duration: Theme.reducedMotion ? 0 : Theme.popupDuration }
        Motion { property: "scale"; from: Theme.reducedMotion ? 1 : 0.98; to: 1; duration: Theme.reducedMotion ? 0 : Theme.popupDuration }
    }
    // Close immediately so native focus and controller routing resume together.
    function select(index) {
        pendingIndex = Math.max(0, Math.min(options.length - 1, index))
        list.currentIndex = pendingIndex
        list.positionViewAtIndex(pendingIndex, ListView.Contain)
    }
    function present(anchor, values, index, label) {
        if (!anchor || !parent || !values.length) return
        options = values; currentIndex = index; title = label
        origin = anchor.mapToItem(parent, anchor.width, anchor.height + 6)
        anchorTop = anchor.mapToItem(parent, 0, 0).y
        open(); contentItem.forceActiveFocus()
        // Showing the model resets ListView.currentIndex; select after it exists.
        select(index)
    }
    function dispatch(action, repeated) {
        if (!visible) return false
        if (action === "up") select(pendingIndex - 1)
        else if (action === "down") select(pendingIndex + 1)
        else if (action === "back" || action === "quick") close()
        else if (action === "accept" && !repeated) activated(pendingIndex)
        return true
    }
    background: Rectangle { radius: Theme.radius; color: Theme.background; border.color: Theme.outline; border.width: 1 }
    contentItem: FocusScope {
        focus: true
        Keys.onPressed: function(event) {
            // Keep native keys and controller taps on the same pending selection.
            const action = ({[Qt.Key_Up]: "up", [Qt.Key_Backtab]: "up", [Qt.Key_Down]: "down", [Qt.Key_Tab]: "down",
                [Qt.Key_Return]: "accept", [Qt.Key_Enter]: "accept", [Qt.Key_Space]: "accept",
                [Qt.Key_Escape]: "back", [Qt.Key_Backspace]: "back", [Qt.Key_Q]: "quick"})[event.key]
            event.accepted = true
            if (action) popup.dispatch(action, event.isAutoRepeat)
        }
        Keys.onReleased: function(event) { event.accepted = true }
        Label { x: Theme.padding; y: 12; width: parent.width - 40; height: 32; text: popup.title; font.bold: true }
        Ui.ListView {
            id: list; objectName: "choiceList"; x: 8; y: Theme.fieldHeight; width: parent.width - 16; height: parent.height - y - Theme.gap
            model: popup.visible ? popup.options : []
            delegate: Button {
                required property string modelData; required property int index
                width: list.rowWidth; height: Theme.rowHeight; text: modelData
                selected: popup.pendingIndex === index; focusOutline: false; focusPolicy: Qt.NoFocus
                onClicked: { popup.select(index); popup.activated(index) }
                contentItem: Label { text: parent.text; rightPadding: 26 }
                Icon { name: "check"; color: Theme.accent; visible: parent.index === popup.currentIndex; anchors.right: parent.right; anchors.rightMargin: 14; anchors.verticalCenter: parent.verticalCenter }
            }
        }
        Item {
            x: list.x; y: list.y; width: list.width; height: list.height; clip: true
            FocusFrame {
                objectName: "choiceFocus"
                y: list.currentItem ? list.currentItem.y - list.contentY : 0
                width: list.rowWidth; height: Theme.rowHeight; active: popup.visible
            }
        }
    }
}
