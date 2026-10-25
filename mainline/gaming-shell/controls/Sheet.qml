import QtQuick

// §5 bottom sheet: full width, rises from the bottom edge with only the top corners rounded.
Panel {
    squareBottom: true
    width: parent ? parent.width : implicitWidth
}
