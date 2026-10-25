import QtQuick
import QtQuick.Templates as T

// §5 Button: primary (accent), secondary (surfaceSunken) or danger, which turns solid only while
// focused. Pressing scales to 0.97 and deepens the fill; reduced motion keeps only the color change.
T.Button {
    id: control
    property string variant: primary ? "primary" : "secondary"
    property bool primary: false
    property bool selected: false
    property bool focusOutline: true
    property string iconName: ""
    property bool reducedMotion: Theme.reducedMotion
    property real fontScale: Theme.fontScale
    readonly property bool focused: enabled && (selected || visualFocus)
    readonly property color fill: !enabled ? Theme.surfaceSunken
        : variant === "primary" ? Theme.accent : variant === "danger" && focused ? Theme.danger : Theme.surfaceSunken
    readonly property color ink: !enabled ? Theme.disabledText
        : variant === "primary" ? Theme.accentText : variant === "danger" ? (focused ? Theme.dangerText : Theme.danger) : Theme.text
    implicitWidth: Math.max(2 * implicitHeight, implicitContentWidth + leftPadding + rightPadding)
    implicitHeight: Theme.buttonHeight
    leftPadding: Theme.buttonPadding + (iconName ? Theme.iconSize + Theme.space12 : 0); rightPadding: Theme.buttonPadding
    topPadding: 0; bottomPadding: 0
    focusPolicy: Qt.StrongFocus
    scale: down && !reducedMotion ? Theme.pressScale : 1
    Behavior on scale { Motion { duration: control.reducedMotion ? 0 : Theme.pressDuration } }
    contentItem: Label { text: control.text; fontScale: control.fontScale; color: control.ink; horizontalAlignment: Text.AlignHCenter }
    Icon { x: Theme.buttonPadding; anchors.verticalCenter: parent.verticalCenter; name: control.iconName; visible: control.iconName !== ""; color: control.ink }
    background: Rectangle {
        radius: Theme.radiusRow
        color: control.down ? Theme.pressed(control.fill) : control.fill
        // Focus ring: 4 px stroke outside a gap that shows the container color.
        Rectangle {
            anchors.fill: parent; anchors.margins: -(Theme.focusGap + Theme.focusWidth)
            radius: Theme.radiusRow + Theme.focusRadiusExtra; color: "transparent"
            border.width: Theme.focusWidth; border.color: Theme.focus
            visible: control.focusOutline && control.focused
        }
    }
}
