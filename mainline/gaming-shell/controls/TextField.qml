import QtQuick
import QtQuick.Templates as T

T.TextField {
    id: control
    property real fontScale: Theme.fontScale
    implicitWidth: 280; implicitHeight: Theme.fieldHeight
    leftPadding: Theme.padding; rightPadding: Theme.padding; topPadding: 12; bottomPadding: 12
    color: Theme.text; placeholderTextColor: Theme.muted
    selectionColor: Theme.accent; selectedTextColor: Theme.accentText
    font.pixelSize: Theme.bodySize * fontScale
    verticalAlignment: TextInput.AlignVCenter
    selectByMouse: true
    background: Rectangle { color: Theme.raised; radius: Theme.radius; border.width: 2; border.color: control.activeFocus ? Theme.accent : Theme.outline }
}
