pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Shapes

Item {
    id: icon
    property string name: "chevron-right"
    property color color: Theme.textSecondary
    property url source: ""
    // Closed shapes (the favorite star) can be drawn solid in the icon color.
    property bool filled: false
    // Original 24-unit line drawings, 2 px round strokes (§4); one geometry path, no font or bitmap dependency.
    readonly property var paths: ({
        "plus": "M5 12H19 M12 5V19",
        "check": "M4 12L9 17L20 6",
        "chevron-right": "M9 5L16 12L9 19",
        "chevron-left": "M15 5L8 12L15 19",
        "chevron-down": "M5 9L12 16L19 9",
        "monitor": "M4 3H20Q22 3 22 5V15Q22 17 20 17H4Q2 17 2 15V5Q2 3 4 3Z M12 17V21 M7 21H17",
        "streaming": "M4 3H20Q22 3 22 5V15Q22 17 20 17H4Q2 17 2 15V5Q2 3 4 3Z M12 17V21 M7 21H17 M10 7L15 10L10 13Z",
        "terminal": "M3 4H21V20H3Z M6 8L10 12L6 16 M13 16H18",
        "folder": "M3 6Q3 4 5 4H9L11 6H19Q21 6 21 8V18Q21 20 19 20H5Q3 20 3 18Z",
        "document": "M4 2H14L20 8V22H4Z M14 2V8H20 M8 12H16 M8 16H16",
        "gamepad": "M7 7H17Q20 7 21 11L22 17Q22 21 19 19L15 16H9L5 19Q2 21 2 17L3 11Q4 7 7 7Z M7 10V14 M5 12H9 M16 11H16.1 M19 13H19.1",
        "cartridge": "M6 2H18V5H21V22H3V5H6Z M7 8H17V15H7Z M8 19V22 M12 19V22 M16 19V22",
        "ports": "M4 8L12 3L20 8V18L12 22L4 18Z M4 8L12 13L20 8 M12 13V22 M8 5.5L16 10.5",
        "usb": "M12 22V3 M9 6L12 3L15 6 M12 16L6 12V8 M12 13L18 9V6 M4 5H8V8H4Z M16 3H20V6H16Z",
        "settings": "M21.77 9.86L21.77 14.14L19.18 14.49L18.84 15.32L20.42 17.39L17.39 20.42L15.32 18.84L14.49 19.18L14.14 21.77L9.86 21.77L9.51 19.18L8.68 18.84L6.61 20.42L3.58 17.39L5.16 15.32L4.82 14.49L2.23 14.14L2.23 9.86L4.82 9.51L5.16 8.68L3.58 6.61L6.61 3.58L8.68 5.16L9.51 4.82L9.86 2.23L14.14 2.23L14.49 4.82L15.32 5.16L17.39 3.58L20.42 6.61L18.84 8.68L19.18 9.51Z M12 9A3 3 0 1 0 12 15A3 3 0 1 0 12 9",
        "grid": "M6 4H8Q10 4 10 6V8Q10 10 8 10H6Q4 10 4 8V6Q4 4 6 4Z M16 4H18Q20 4 20 6V8Q20 10 18 10H16Q14 10 14 8V6Q14 4 16 4Z M6 14H8Q10 14 10 16V18Q10 20 8 20H6Q4 20 4 18V16Q4 14 6 14Z M16 14H18Q20 14 20 16V18Q20 20 18 20H16Q14 20 14 18V16Q14 14 16 14Z",
        "briefcase": "M5 8H19Q21 8 21 10V18Q21 20 19 20H5Q3 20 3 18V10Q3 8 5 8Z M9 8V6Q9 4 11 4H13Q15 4 15 6V8 M3 13H21 M11 13V15H13V13",
        "power": "M12 3V12 M6.34 6.34A8 8 0 1 0 17.66 6.34",
        "home": "M3 11L12 3L21 11 M5 9.5V20H10V14H14V20H19V9.5",
        "tasks": "M9 3H19Q21 3 21 5V15 M5 7H15Q17 7 17 9V19Q17 21 15 21H5Q3 21 3 19V9Q3 7 5 7Z",
        "search": "M11 4A7 7 0 1 0 11 18A7 7 0 1 0 11 4 M16 16L21 21",
        "moon": "M20 14.5A8 8 0 1 1 9.5 4A6.5 6.5 0 0 0 20 14.5Z",
        "gauge": "M4 17A8 8 0 1 1 20 17 M12 14L16 9",
        "star": "M12 2.9L14.41 9.08L21.04 9.46L15.9 13.67L17.58 20.09L12 16.5L6.42 20.09L8.1 13.67L2.96 9.46L9.59 9.08Z",
        "pause": "M9 6V18 M15 6V18",
        "sun": "M12 8A4 4 0 1 0 12 16A4 4 0 1 0 12 8 M18.5 12L21 12 M16.6 16.6L18.36 18.36 M12 18.5L12 21 M7.4 16.6L5.64 18.36 M5.5 12L3 12 M7.4 7.4L5.64 5.64 M12 5.5L12 3 M16.6 7.4L18.36 5.64",
        "lock": "M6 11H18V20H6Z M8.5 11V8A3.5 3.5 0 0 1 15.5 8V11",
        "x-circle": "M12 3A9 9 0 1 0 12 21A9 9 0 1 0 12 3 M9 9L15 15 M15 9L9 15",
        "alert": "M12 3A9 9 0 1 0 12 21A9 9 0 1 0 12 3 M12 7.5V13 M12 16.5H12.1",
        "screen-off": "M4 3H20Q22 3 22 5V15Q22 17 20 17H4Q2 17 2 15V5Q2 3 4 3Z M12 17V21 M7 21H17 M3 2L21 18",
        "restart": "M4 12A8 8 0 1 0 6.34 6.34 M4 3V8H9",
        "globe": "M12 3A9 9 0 1 0 12 21A9 9 0 1 0 12 3 M3 12H21 M12 3Q16 7.5 16 12Q16 16.5 12 21Q8 16.5 8 12Q8 7.5 12 3",
        "dpad": "M9 3H15V9H21V15H15V21H9V15H3V9H9Z",
        "arrows-h": "M8 8L4 12L8 16 M16 8L20 12L16 16",
        "arrows-v": "M8 8L12 4L16 8 M8 16L12 20L16 16",
        "wifi": "M2 8.5Q12 0 22 8.5 M5.5 12.5Q12 7 18.5 12.5 M9 16.5Q12 14 15 16.5 M12 20H12.1",
        "volume": "M3 9H7L12 5V19L7 15H3Z M16 8Q20 12 16 16 M19 5Q25 12 19 19",
        "volume-muted": "M3 9H7L12 5V19L7 15H3Z M16 9L22 15 M22 9L16 15",
        "display": "M4 4H20V17H4Z M8 21H16 M12 17V21 M8 8H16V13H8Z",
        "storage": "M4 3H20V21H4Z M4 15H20 M8 18H8.1 M12 18H12.1",
        "info": "M12 2A10 10 0 1 0 12 22A10 10 0 1 0 12 2 M12 10V17 M12 6H12.1",
        "battery": "M4 7H17Q19 7 19 9V15Q19 17 17 17H4Q2 17 2 15V9Q2 7 4 7Z M22 10.5V13.5",
        "battery-charging": "M4 7H17Q19 7 19 9V15Q19 17 17 17H4Q2 17 2 15V9Q2 7 4 7Z M22 10.5V13.5 M11 9L8.5 12.5H12L9.5 16",
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
            strokeColor: icon.color; strokeWidth: 2; fillColor: icon.filled ? icon.color : "transparent"
            capStyle: ShapePath.RoundCap; joinStyle: ShapePath.RoundJoin
            PathSvg { path: icon.paths[icon.name] || "" }
        }
    }
    Image { anchors.fill: parent; visible: source.toString() !== ""; source: icon.source; sourceSize.width: width; sourceSize.height: height; fillMode: Image.PreserveAspectFit }
}
