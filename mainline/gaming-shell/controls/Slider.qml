import QtQuick
import QtQuick.Templates as T

// §5 Slider: 8 px track, 28 px light thumb with a 3 px ring; while adjusting the fill and ring use
// warning and the thumb grows to 36. Steps are 5%.
T.Slider {
    id: control
    property bool adjusting: false
    readonly property color fillColor: !enabled ? Theme.disabledText : adjusting ? Theme.warning : Theme.accent
    implicitWidth: 180; implicitHeight: Theme.thumbAdjustingSize
    leftPadding: Theme.thumbAdjustingSize / 2; rightPadding: Theme.thumbAdjustingSize / 2
    stepSize: Theme.sliderStep
    background: Item {
        x: control.leftPadding; y: (control.height - height) / 2
        width: control.availableWidth; height: Theme.trackHeight
        Rectangle { anchors.fill: parent; radius: height / 2; color: Theme.track }
        Rectangle { width: control.visualPosition * parent.width; height: parent.height; radius: height / 2; color: control.fillColor }
    }
    handle: Rectangle {
        readonly property int size: control.adjusting ? Theme.thumbAdjustingSize : Theme.thumbSize
        x: control.leftPadding + control.visualPosition * control.availableWidth - width / 2
        y: (control.height - height) / 2; width: size; height: size; radius: size / 2
        color: Theme.switchThumb
        border.width: Theme.thumbRing; border.color: control.fillColor
    }
}
