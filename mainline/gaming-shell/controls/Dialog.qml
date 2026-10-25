import QtQuick

// §5 dialog: centered, at most 560 wide, r28.
Panel {
    width: Math.min(Theme.dialogMaxWidth, parent ? parent.width - 2 * Theme.margin : Theme.dialogMaxWidth)
}
