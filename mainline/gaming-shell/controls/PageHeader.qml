import QtQuick

// Page status below the shared top bar: one caption line (danger for an error) and a progress bar
// while busy. The top bar carries the title and B returns, so pages draw no title or back button.
Item {
    id: header
    property string subtitle: ""
    property bool error: false
    property bool busy: false
    property real progress: -1
    implicitHeight: Theme.pageStatusHeight
    Label {
        objectName: "pageStatus"; width: parent.width; y: Theme.space8
        text: header.subtitle; role: "caption"; color: header.error ? Theme.danger : Theme.textSecondary
    }
    ProgressBar { anchors.bottom: parent.bottom; anchors.bottomMargin: Theme.space4; width: parent.width; visible: header.busy; indeterminate: header.progress < 0; value: Math.max(0, header.progress) }
}
