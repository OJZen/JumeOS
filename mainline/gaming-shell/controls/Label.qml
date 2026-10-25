import QtQuick

// Plain text in one §3 role: display, title, headline, body, label, caption or micro.
// "section" and "value" are accepted for older call sites (headline and label).
Text {
    property real fontScale: Theme.fontScale
    property string role: "body"
    // Times, battery and percentages use tabular figures.
    property bool tabular: false
    readonly property string resolvedRole: role === "section" ? "headline" : role === "value" ? "label" : Theme.type[role] ? role : "body"
    color: role === "caption" ? Theme.textSecondary : Theme.text
    font.family: Theme.fontFamily
    font.pixelSize: Math.round(Theme.type[resolvedRole].size * fontScale)
    font.weight: Theme.type[resolvedRole].weight
    font.features: tabular ? ({"tnum": 1}) : ({})
    textFormat: Text.PlainText
    verticalAlignment: Text.AlignVCenter
    elide: Text.ElideRight
}
