pragma ComponentBehavior: Bound
import QtQuick
import "controls" as Ui

// §8 library: filter tabs (L1/R1, never focused) over a grid of 212 cards with 22 titles below;
// columns follow Theme.gridColumns and two full rows fit at 100%. Unavailable entries keep their
// place, disabled with the reason on the card. The shell owns the filter, position and query.
Item {
    id: library
    required property var shell
    required property var entries
    property var filters: []
    property int filter: 0
    property int index: 0
    // Off while an overlay owns the focus: the card stays lifted without its ring (§4).
    property bool ringVisible: true
    property real fontScale: Ui.Theme.fontScale
    property bool reducedMotion: Ui.Theme.reducedMotion
    signal cardActivated(int position)
    signal filterActivated(int position)
    Ui.Tabs {
        objectName: "libraryTabs"
        x: Ui.Theme.margin; y: Ui.Theme.libraryTabsTop
        model: library.filters; currentIndex: library.filter; fontScale: library.fontScale
        onActivated: function(position) { library.filterActivated(position) }
    }
    GridView {
        id: grid; objectName: "libraryGrid"
        // Cells carry 16 px of room for the focus ring and lift; cards land on the content margin.
        x: Ui.Theme.margin - Ui.Theme.space16; y: Ui.Theme.libraryGridTop - Ui.Theme.space16
        width: Ui.Theme.gridColumns * cellWidth; height: Ui.Theme.canvasHeight - Ui.Theme.hintBarHeight - y
        cellWidth: Ui.Theme.gridCellWidth + Ui.Theme.gridGap
        // Two full rows at every font size: 16 between rows, a title line that follows the font size,
        // and art that shrinks (to 200 at most) only when two rows would still not fit.
        readonly property real titleHeight: Math.round(Ui.Theme.type.label.line * library.fontScale)
        readonly property real cardSize: Math.max(Ui.Theme.libraryCardMin, Math.min(Ui.Theme.gridCellWidth,
            (Ui.Theme.canvasHeight - Ui.Theme.hintBarHeight - Ui.Theme.libraryGridTop + Ui.Theme.space16) / 2 - Ui.Theme.space8 - titleHeight - Ui.Theme.space16))
        cellHeight: cardSize + Ui.Theme.space8 + titleHeight + Ui.Theme.space16
        clip: true; interactive: false
        model: library.entries.length; currentIndex: library.index
        highlightRangeMode: GridView.ApplyRange
        preferredHighlightBegin: 0; preferredHighlightEnd: height
        highlightMoveDuration: library.reducedMotion ? 0 : Ui.Theme.focusDuration * 2
        onCurrentIndexChanged: if (currentIndex >= 0) positionViewAtIndex(currentIndex, GridView.Contain)
        delegate: Item {
            id: cell
            required property int index
            readonly property int entry: library.entries[index]
            readonly property var game: library.shell.games[entry]
            readonly property bool current: library.index === index
            width: grid.cellWidth; height: grid.cellHeight
            Ui.GameCard {
                objectName: "libraryCard"
                x: Ui.Theme.space16; y: Ui.Theme.space16; width: grid.cardSize; height: width
                title: cell.game.title; showTitle: false
                plain: !!cell.game.plain; cardColor: library.shell.entryColor(cell.entry)
                iconName: cell.game.icon || ""
                badge: cell.game.reason || library.shell.entryBadge(cell.game)
                badgeIcon: badge === "已暂停" ? "pause" : ""
                available: !cell.game.reason
                favorite: library.shell.entryFavorite(cell.entry)
                selected: cell.current; focusOutline: library.ringVisible
                fontScale: library.fontScale; reducedMotion: library.reducedMotion
                onFocused: library.index = cell.index
                onActivated: library.cardActivated(cell.index)
            }
            Ui.Label {
                objectName: "libraryTitle"
                x: Ui.Theme.space16; y: Ui.Theme.space16 + grid.cardSize + Ui.Theme.space8; width: grid.cardSize; height: grid.titleHeight
                role: "label"; fontScale: library.fontScale; text: cell.game.title
                // One line; a long title may shrink, never below micro (§3).
                fontSizeMode: Text.HorizontalFit; minimumPixelSize: Math.round(Ui.Theme.type.micro.size * library.fontScale)
                color: cell.game.reason ? Ui.Theme.disabledText : cell.current ? Ui.Theme.accent : Ui.Theme.text
                font.weight: cell.current ? Font.Bold : Ui.Theme.type.label.weight
            }
        }
    }
    Ui.Label {
        anchors.centerIn: grid; visible: library.entries.length === 0
        role: "label"; fontScale: library.fontScale; color: Ui.Theme.textSecondary
        text: library.shell.libraryQuery ? "没有符合“" + library.shell.libraryQuery + "”的项目" : "这里还没有项目"
    }
}
