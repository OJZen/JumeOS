import QtQuick

// §5 toast at the bottom center. The owner clears ordinary notices after toastDwell; errors use the
// error colors and stay until the next action. Only a success carries the check mark and only an
// error the alert; a trailing period is dropped.
Rectangle {
    id: toast
    property string text: ""
    property bool error: false
    property bool success: false
    readonly property bool marked: error || success
    readonly property real iconRoom: marked ? Theme.iconSize + Theme.space12 : 0
    property real maximumWidth: Theme.contentWidth
    property real fontScale: Theme.fontScale
    readonly property real textWidth: Math.min(message.implicitWidth, maximumWidth - 2 * Theme.space24 - iconRoom)
    width: textWidth + 2 * Theme.space24 + iconRoom
    height: Math.max(Theme.minTarget, message.height + 2 * Theme.space12)
    radius: Theme.radiusRow
    visible: text !== ""
    color: error ? Theme.errorToast : Theme.glyph
    Accessible.role: Accessible.AlertMessage
    Accessible.name: text
    Icon {
        x: Theme.space24; anchors.verticalCenter: parent.verticalCenter; visible: toast.marked
        name: toast.error ? "alert" : "check"; color: toast.error ? Theme.errorToastText : Theme.glyphText
    }
    Label {
        id: message
        x: Theme.space24 + toast.iconRoom; anchors.verticalCenter: parent.verticalCenter
        width: toast.textWidth; wrapMode: Text.Wrap; elide: Text.ElideNone
        role: "label"; fontScale: toast.fontScale; text: toast.text.replace(/[。.]+$/, "")
        color: toast.error ? Theme.errorToastText : Theme.glyphText
    }
}
