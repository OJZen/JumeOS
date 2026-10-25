import QtQuick

// Level-2 elevation (§4): one prerendered nine-slice shadow under a raised card or panel; never a live blur.
BorderImage {
    property Item target: parent
    anchors.fill: target; anchors.margins: -Theme.shadowSpread
    source: "elevation.png"
    border { left: 40; top: 40; right: 40; bottom: 40 }
    z: -1
}
