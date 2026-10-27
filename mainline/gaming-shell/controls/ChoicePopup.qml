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
    readonly property var hints: [{button: "A", label: "确定"}, {button: "B", label: "取消"}]
    signal activated(int index)
    popupType: T.Popup.Item
    modal: true; focus: true; dim: false; padding: 0; margins: 0
    closePolicy: T.Popup.CloseOnEscape | T.Popup.CloseOnPressOutside
    width: Math.min(parent ? parent.width : 0, popupWidth)
    readonly property real headerHeight: Theme.space16 + Theme.lineHeight("headline") + Theme.space16
    height: Math.min(parent ? parent.height : 0, headerHeight + Math.min(5, options.length) * (Theme.listRowHeight + Theme.space8) + Theme.space16)
    x: Math.max(0, Math.min(parent ? parent.width - width : 0, origin.x - width))
    y: above ? anchorTop - height - 6 : Math.max(0, Math.min(parent ? parent.height - height : 0, origin.y))
    transformOrigin: above ? Item.BottomRight : Item.TopRight
    enter: Transition {
        Motion { property: "opacity"; from: 0; to: 1; curve: "emphasized"; duration: Theme.reducedMotion ? 0 : Theme.dialogEnterDuration }
        Motion { property: "scale"; from: Theme.reducedMotion ? 1 : Theme.dialogStartScale; to: 1; curve: "emphasized"; duration: Theme.reducedMotion ? 0 : Theme.dialogEnterDuration }
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
        // §7.4 menus: B and Select cancel, Start closes; nothing below sees the key.
        else if (action === "back" || action === "quick" || action === "options") { if (!repeated) close() }
        else if (action === "accept" && !repeated) activated(pendingIndex)
        return true
    }
    background: Rectangle { radius: Theme.radiusPanel; color: Theme.surface; border.color: Theme.outline; border.width: 1; Shadow {} }
    contentItem: FocusScope {
        focus: true
        Keys.onPressed: function(event) {
            // Keep native keys and controller taps on the same pending selection.
            const action = ({[Qt.Key_Up]: "up", [Qt.Key_Backtab]: "up", [Qt.Key_Down]: "down", [Qt.Key_Tab]: "down",
                [Qt.Key_Return]: "accept", [Qt.Key_Enter]: "accept", [Qt.Key_Space]: "accept",
                [Qt.Key_Escape]: "back", [Qt.Key_Q]: "quick", [Qt.Key_M]: "options"})[event.key]
            event.accepted = true
            if (action) popup.dispatch(action, event.isAutoRepeat)
        }
        Keys.onReleased: function(event) { event.accepted = true }
        Label { x: Theme.space24; y: Theme.space16; width: parent.width - 2 * Theme.space24; height: Theme.lineHeight("headline"); role: "headline"; text: popup.title }
        Ui.ListView {
            id: list; objectName: "choiceList"
            // The 16 px side margin holds the 8 px scrollbar clear of the focus ring.
            scrollGap: Theme.space8
            x: Theme.space16; y: popup.headerHeight; width: parent.width - 2 * Theme.space16; height: parent.height - y - Theme.space16
            model: popup.visible ? popup.options : []
            delegate: T.ItemDelegate {
                id: option
                required property string modelData; required property int index
                readonly property bool pending: popup.pendingIndex === index
                width: list.width; height: Theme.listRowHeight; text: modelData
                padding: 0; focusPolicy: Qt.NoFocus
                onClicked: { popup.select(index); popup.activated(index) }
                background: Rectangle { radius: Theme.radiusRow; color: option.pending ? Theme.accentSoft : option.down ? Theme.pressed(Theme.surface) : "transparent" }
                contentItem: Item {
                    Label {
                        x: Theme.space24; width: parent.width - x - Theme.space24 - Theme.iconSize - Theme.space8; anchors.verticalCenter: parent.verticalCenter
                        text: option.text; color: option.pending ? Theme.accentInk : Theme.text; font.weight: option.pending ? Font.Bold : Theme.type.body.weight
                    }
                    Icon { name: "check"; color: Theme.accent; visible: option.index === popup.currentIndex; anchors.right: parent.right; anchors.rightMargin: Theme.space24; anchors.verticalCenter: parent.verticalCenter }
                }
            }
        }
        // The ring sits outside the row; the clip keeps it with the list while rows scroll.
        Item {
            readonly property real ring: Theme.focusGap + Theme.focusWidth
            x: list.x - ring; y: list.y - ring; width: list.width + 2 * ring; height: list.height + 2 * ring; clip: true
            FocusFrame {
                objectName: "choiceFocus"
                x: parent.ring; y: parent.ring + (list.currentItem ? list.currentItem.y - list.contentY : 0)
                width: list.width; height: list.currentItem ? list.currentItem.height : Theme.listRowHeight; active: popup.visible
            }
        }
    }
}
