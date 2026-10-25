import QtQuick

// §5 quick panel shell: 392 wide, 24 from the top-right corner; height follows its content.
Panel {
    width: Theme.quickPanelWidth
    x: parent ? parent.width - width - Theme.quickPanelInset : 0
    y: Theme.quickPanelInset
}
