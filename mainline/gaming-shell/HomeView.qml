pragma ComponentBehavior: Bound
import QtQuick
import "controls" as Ui

// §8 home: the 最近与收藏 card row (256, gap 24, the next card peeking at the right edge, ending in
// 全部游戏), an info line for the focused card and the six-entry dock. The shell owns the state:
// `index` is the row position (entries.length is 全部游戏), `dockFocused`/`dockIndex` the dock.
Item {
    id: home
    required property var shell
    required property var entries
    property int index: 0
    property bool dockFocused: false
    property int dockIndex: 0
    property bool active: true
    property real fontScale: Ui.Theme.fontScale
    property bool reducedMotion: Ui.Theme.reducedMotion
    readonly property var game: !dockFocused && index < entries.length ? shell.games[entries[index]] : null
    signal cardActivated(int position)
    signal dockActivated(int position)
    ListView {
        id: row; objectName: "homeCards"
        // The focus ring and the 1.04 lift need room around the cards.
        x: 0; y: Ui.Theme.homeRowTop - Ui.Theme.space16; width: home.width; height: Ui.Theme.homeCardSize + 2 * Ui.Theme.space16
        orientation: ListView.Horizontal; spacing: Ui.Theme.space24; clip: true; interactive: false
        model: home.entries.length + 1
        currentIndex: home.index
        // The row scrolls only when the focused card would leave the content margins.
        leftMargin: Ui.Theme.margin; rightMargin: Ui.Theme.margin
        highlightRangeMode: ListView.ApplyRange
        preferredHighlightBegin: Ui.Theme.margin; preferredHighlightEnd: width - Ui.Theme.margin
        highlightMoveDuration: home.reducedMotion ? 0 : Ui.Theme.focusDuration * 2
        delegate: Item {
            id: slot
            required property int index
            readonly property bool all: index === home.entries.length
            readonly property var game: all ? null : home.shell.games[home.entries[index]]
            width: Ui.Theme.homeCardSize; height: row.height
            Ui.GameCard {
                objectName: slot.all ? "homeAllCard" : "homeCard"
                y: Ui.Theme.space16; width: Ui.Theme.homeCardSize; height: width
                title: slot.all ? "全部游戏" : slot.game.title
                subtitle: slot.all ? home.shell.games.length + " 项" : ""
                plain: slot.all || !!(slot.game && slot.game.plain)
                cardColor: slot.all ? Ui.Theme.accent : home.shell.entryColor(home.entries[slot.index])
                iconName: slot.all ? "grid" : (slot.game.icon || "")
                badge: slot.all ? "" : home.shell.entryBadge(slot.game)
                badgeIcon: badge === "已暂停" ? "pause" : ""
                available: slot.all || !slot.game.reason
                favorite: !slot.all && home.shell.entryFavorite(home.entries[slot.index])
                selected: home.active && !home.dockFocused && home.index === slot.index
                fontScale: home.fontScale; reducedMotion: home.reducedMotion
                onFocused: { home.dockFocused = false; home.index = slot.index }
                onActivated: home.cardActivated(slot.index)
            }
        }
    }
    Column {
        objectName: "homeInfo"
        x: Ui.Theme.margin; y: Ui.Theme.homeRowTop + Ui.Theme.homeCardSize + Ui.Theme.space32
        width: Ui.Theme.contentWidth; spacing: Ui.Theme.space4
        visible: home.game !== null
        Ui.Label { objectName: "homeTitle"; width: parent.width; role: "display"; fontScale: home.fontScale; text: home.game ? home.game.title : "" }
        Ui.Label { objectName: "homeCaption"; width: parent.width; role: "caption"; fontScale: home.fontScale; color: Ui.Theme.textSecondary; text: home.game ? home.shell.entryCaption(home.game) : "" }
    }
    Row {
        id: dock; objectName: "homeDock"
        anchors.horizontalCenter: parent.horizontalCenter; y: Ui.Theme.dockTop
        spacing: Ui.Theme.dockGap
        Repeater {
            model: home.shell.dockItems
            Ui.DockTile {
                required property var modelData
                required property int index
                objectName: "dock-" + modelData.id
                width: Ui.Theme.dockTileSize
                iconName: modelData.icon; label: modelData.label
                selected: home.active && home.dockFocused && home.dockIndex === index
                fontScale: home.fontScale; reducedMotion: home.reducedMotion
                onFocused: { home.dockFocused = true; home.dockIndex = index }
                onActivated: home.dockActivated(index)
            }
        }
    }
}
