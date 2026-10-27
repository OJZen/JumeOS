import QtQuick
import QtQuick.Templates as T

T.TextField {
    id: control
    property real fontScale: Theme.fontScale
    // The keyboard's field shows no ring: focus lives on the keys (§8).
    property bool focusRing: true
    implicitWidth: 280; implicitHeight: Theme.fieldHeight
    leftPadding: Theme.space24; rightPadding: Theme.space24; topPadding: Theme.space12; bottomPadding: Theme.space12
    color: Theme.text; placeholderTextColor: Theme.textTertiary
    selectionColor: Theme.accent; selectedTextColor: Theme.accentText
    font.pixelSize: Math.round(Theme.type.body.size * fontScale)
    font.family: Theme.fontFamily
    verticalAlignment: TextInput.AlignVCenter
    selectByMouse: true
    background: Rectangle { color: Theme.surfaceSunken; radius: Theme.radiusRow; border.width: 2; border.color: control.activeFocus && control.focusRing ? Theme.focus : "transparent" }
}
