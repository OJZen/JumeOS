import QtQuick as Q
import QtQuick.Templates as T

Q.ListView {
    clip: true
    readonly property real rowWidth: width - Theme.scrollGutter
    spacing: Theme.gap
    boundsBehavior: Q.Flickable.StopAtBounds
    reuseItems: true
    highlightMoveDuration: 0
    onCurrentIndexChanged: if (currentIndex >= 0) positionViewAtIndex(currentIndex, Q.ListView.Contain)
    T.ScrollBar.vertical: ScrollBar {}
}
