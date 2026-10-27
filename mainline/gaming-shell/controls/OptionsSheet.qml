pragma ComponentBehavior: Bound
import QtQuick

// §7.3 Start options menu: a bottom sheet listing every action of the focused item or page,
// including the X and Y shortcuts (soft glyphs on the right; "按住" before a hold shortcut).
// Unavailable rows stay focusable and give their reason. A runs a row; Start, B or Select closes;
// the page below sees nothing. Items are {id, label[, icon][, button][, hold][, reason]}; the optional
// header adds a 72 thumbnail and a subtitle (§8 GameOptions: system · core).
Item {
    id: menu
    property string title: ""
    property var header: null
    property var items: []
    property int index: 0
    property bool open: false
    // The sheet's top edge, for placing a toast above it.
    readonly property real coverTop: sheet.y
    property real fontScale: Theme.fontScale
    property bool reducedMotion: Theme.reducedMotion
    signal chosen(string id)
    visible: open || sheet.y < height
    function present(heading, entries, details) {
        if (!entries.length) return false
        title = heading; items = entries; header = details || null
        index = Math.max(0, entries.findIndex(function(entry) { return !entry.reason }))
        open = true
        return true
    }
    function close() { open = false }
    function dispatch(action, repeated) {
        if (!open) return false
        if (action === "up") index = Math.max(0, index - 1)
        else if (action === "down") index = Math.min(items.length - 1, index + 1)
        else if (repeated) return true
        else if (action === "options" || action === "back" || action === "quick") close()
        else if (action === "accept" && items[index] && !items[index].reason) {
            const id = items[index].id
            close(); chosen(id)
        }
        return true
    }
    Rectangle {
        anchors.fill: parent; color: Theme.scrim
        opacity: menu.open ? 1 : 0; visible: opacity > 0
        Behavior on opacity { Motion { duration: menu.reducedMotion ? Theme.reducedFadeDuration : menu.open ? Theme.sheetEnterDuration : Theme.sheetExitDuration } }
        MouseArea { anchors.fill: parent; enabled: menu.open; onClicked: menu.close() }
    }
    Sheet {
        id: sheet; objectName: "optionsSheet"
        y: menu.open ? menu.height - height : menu.height + Theme.shadowSpread
        Behavior on y {
            Motion {
                curve: menu.open ? "emphasized" : "exit"
                duration: menu.reducedMotion ? 0 : menu.open ? Theme.sheetEnterDuration : Theme.sheetExitDuration
            }
        }
        x: Theme.margin; width: menu.width - 2 * Theme.margin
        fontScale: menu.fontScale
        hints: [{button: "A", label: "确定"}, {button: "B", label: "关闭"}]
        header: Row {
            width: parent ? parent.width : 0; spacing: Theme.space24
            GameCard {
                objectName: "optionsThumbnail"; anchors.verticalCenter: parent.verticalCenter
                visible: !!menu.header && menu.header.color !== undefined
                width: Theme.optionsThumbnail; height: width; title: menu.title; showTitle: false
                cardColor: menu.header && menu.header.color ? menu.header.color : Theme.accent
                iconName: menu.header ? menu.header.icon || "" : ""; plain: !!menu.header && !!menu.header.plain
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter; spacing: Theme.space4
                width: parent.width - (x > 0 ? Theme.optionsThumbnail + Theme.space24 : 0)
                Label { objectName: "optionsTitle"; width: parent.width; role: "headline"; fontScale: menu.fontScale; text: menu.title }
                Label {
                    objectName: "optionsSubtitle"; width: parent.width; role: "caption"; fontScale: menu.fontScale; color: Theme.textSecondary
                    visible: text !== ""; text: menu.header && menu.header.subtitle ? menu.header.subtitle : ""
                }
            }
        }
        Column {
            width: parent.width; spacing: 0
            Repeater {
                model: menu.items
                ListRow {
                    id: option
                    required property var modelData
                    required property int index
                    objectName: "option-" + modelData.id
                    width: parent.width; fontScale: menu.fontScale; reducedMotion: menu.reducedMotion
                    title: modelData.label; disabledReason: modelData.reason || ""; iconName: modelData.icon || ""
                    selected: menu.index === index; current: selected
                    onFocused: menu.index = index
                    onActivated: menu.dispatch("accept", false)
                    Row {
                        anchors.right: parent.right; anchors.rightMargin: Theme.space24; anchors.verticalCenter: parent.verticalCenter
                        spacing: Theme.space8; visible: !!option.modelData.button
                        Label {
                            objectName: "optionHold"; anchors.verticalCenter: parent.verticalCenter; visible: !!option.modelData.hold
                            text: "按住"; role: "micro"; color: Theme.textSecondary; fontScale: menu.fontScale
                        }
                        GlyphBadge { button: option.modelData.button || "A"; soft: true; size: Theme.glyphInlineSize }
                    }
                }
            }
        }
    }
}
