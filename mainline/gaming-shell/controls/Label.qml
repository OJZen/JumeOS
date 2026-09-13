import QtQuick

Text {
    property real fontScale: Theme.fontScale
    property string role: "body"
    color: role === "caption" ? Theme.muted : Theme.text
    font.pixelSize: (role === "title" ? Theme.titleSize : role === "section" ? Theme.sectionSize : role === "caption" ? Theme.captionSize : role === "micro" ? Theme.microSize : Theme.bodySize) * fontScale
    font.bold: role === "title" || role === "section"
    textFormat: Text.PlainText
    verticalAlignment: Text.AlignVCenter
    elide: Text.ElideRight
}
