pragma ComponentBehavior: Bound
import QtQuick as Q
import QtQuick.Templates as T
import QtQml.Models

Q.TableView {
    id: table
    clip: true; reuseItems: true
    columnSpacing: 1; rowSpacing: 1
    boundsBehavior: Q.Flickable.StopAtBounds
    editTriggers: Q.TableView.NoEditTriggers
    selectionModel: ItemSelectionModel { model: table.model }
    delegate: Q.Rectangle {
        objectName: "tableCell"
        required property var model
        required property bool current
        required property bool selected
        implicitWidth: 180; implicitHeight: Theme.rowHeight
        color: selected ? Theme.raised : Theme.surface
        border.color: current ? Theme.accent : "transparent"; border.width: 2
        Label { x: Theme.padding; width: parent.width - 2 * Theme.padding; height: parent.height; text: parent.model.display === undefined ? "" : String(parent.model.display) }
    }
    T.ScrollBar.vertical: ScrollBar {}
    T.ScrollBar.horizontal: ScrollBar {}
}
