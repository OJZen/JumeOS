import QtQuick as Q
import QtQuick.Templates as T

// Rows take the full list width; the scrollbar overlays the margin to the right
// of the list (scrollGap from the rows), so it never narrows the layout.
Q.ListView {
    id: list
    property real scrollGap: Theme.space12
    clip: true
    spacing: Theme.gap
    boundsBehavior: Q.Flickable.StopAtBounds
    reuseItems: true
    highlightMoveDuration: 0
    onCurrentIndexChanged: if (currentIndex >= 0) positionViewAtIndex(currentIndex, Q.ListView.Contain)
    T.ScrollBar.vertical: ScrollBar {
        // A sibling now, so it follows the list's visibility explicitly.
        parent: list.parent; visible: list.visible
        anchors.top: list.top; anchors.bottom: list.bottom
        anchors.left: list.right; anchors.leftMargin: list.scrollGap
    }
}
