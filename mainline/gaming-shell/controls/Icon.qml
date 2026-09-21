pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Shapes

Item {
    id: icon
    property string name: "chevron-right"
    property color color: Theme.muted
    property url source: ""
    // Original 24-unit line drawings; one geometry path, no font or bitmap dependency.
    readonly property var paths: ({
        "plus": "M5 12H19 M12 5V19",
        "check": "M4 12L9 17L20 6",
        "chevron-right": "M9 5L16 12L9 19",
        "chevron-left": "M15 5L8 12L15 19",
        "chevron-down": "M5 9L12 16L19 9",
        "monitor": "M4 3H20Q22 3 22 5V15Q22 17 20 17H4Q2 17 2 15V5Q2 3 4 3Z M12 17V21 M7 21H17",
        "gamepad": "M7 7H17Q20 7 21 11L22 17Q22 21 19 19L15 16H9L5 19Q2 21 2 17L3 11Q4 7 7 7Z M7 10V14 M5 12H9 M16 11H16.1 M19 13H19.1",
        "cartridge": "M6 2H18V5H21V22H3V5H6Z M7 8H17V15H7Z M8 19V22 M12 19V22 M16 19V22",
        "ports": "M4 8L12 3L20 8V18L12 22L4 18Z M4 8L12 13L20 8 M12 13V22 M8 5.5L16 10.5",
        "usb": "M12 22V3 M9 6L12 3L15 6 M12 16L6 12V8 M12 13L18 9V6 M4 5H8V8H4Z M16 3H20V6H16Z",
        "settings": "M4 6H20 M4 12H20 M4 18H20 M8 3V9 M16 9V15 M10 15V21",
        "wifi": "M2 8Q12 -1 22 8 M5 12Q12 5 19 12 M8 16Q12 12 16 16 M12 20H12.1",
        "volume": "M3 9H7L12 5V19L7 15H3Z M16 8Q20 12 16 16 M19 5Q25 12 19 19",
        "display": "M4 4H20V17H4Z M8 21H16 M12 17V21 M8 8H16V13H8Z",
        "storage": "M4 3H20V21H4Z M4 15H20 M8 18H8.1 M12 18H12.1",
        "info": "M12 2A10 10 0 1 0 12 22A10 10 0 1 0 12 2 M12 10V17 M12 6H12.1",
        "battery": "M2 3H19V21H2Z M19 8H22V16H19 M5 6H10V18H5Z",
        "keyboard": "M2 5H22V19H2Z M5 9H6 M9 9H10 M13 9H14 M17 9H19 M5 12H6 M9 12H10 M13 12H14 M17 12H19 M7 16H17",
        "cpu": "M6 6H18V18H6Z M9 9H15V15H9Z M9 2V6 M15 2V6 M9 18V22 M15 18V22 M2 9H6 M2 15H6 M18 9H22 M18 15H22",
        "memory": "M2 6H22V18H2Z M5 9H9V14H5Z M13 9H19V14H13Z M5 18V21 M9 18V21 M15 18V21 M19 18V21",
        "leaf": "M20 3Q2 2 3 15Q4 22 11 20Q22 19 20 3Z M3 22L16 8",
        "car": "M4 10L7 4H17L20 10 M2 10H22V18H2Z M5 18V21 M19 18V21 M5 13H7 M17 13H19",
        "play": "M7 3L21 12L7 21Z",
        "save": "M3 3H17L21 7V21H3Z M7 3V9H16V3 M7 21V14H17V21"
    })
    readonly property bool known: !!paths[name]
    implicitWidth: Theme.iconSize; implicitHeight: Theme.iconSize
    Accessible.ignored: true
    Shape {
        width: 24; height: 24; anchors.centerIn: parent
        scale: Math.min(icon.width, icon.height) / 24
        visible: icon.source.toString() === "" && icon.known
        preferredRendererType: Shape.GeometryRenderer
        ShapePath {
            strokeColor: icon.color; strokeWidth: 1.7; fillColor: "transparent"
            capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
            PathSvg { path: icon.paths[icon.name] || "" }
        }
    }
    Image { anchors.fill: parent; visible: source.toString() !== ""; source: icon.source; sourceSize.width: width; sourceSize.height: height; fillMode: Image.PreserveAspectFit }
}
