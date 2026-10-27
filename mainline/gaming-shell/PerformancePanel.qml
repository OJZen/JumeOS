pragma ComponentBehavior: Bound
import QtQuick
import "controls" as Ui

// §5 performance overlay: top left, at most three rows of tabular figures, never focused.
// A reading without data is left out entirely (no "—"); the detailed figures (P95, decode,
// queue, audio queue, thermal state) belong to 设置 › 性能. Readings keep non-breaking spaces,
// so a row that outgrows 360 at a large font size wraps only between "·" items.
Rectangle {
    id: panel
    required property var metrics
    property var device: null
    readonly property bool hardware: device !== null && device.target
    property real fontScale: Ui.Theme.fontScale
    readonly property bool game: metrics.game && metrics.game.active === true
    readonly property bool streaming: metrics.stream && metrics.stream.active === true
    readonly property var info: hardware ? device.info : ({})
    function valid(value) { return typeof value === "number" && isFinite(value) && value >= 0 }
    readonly property string space: "\u00a0"
    function fixed(value, digits, suffix) { return valid(value) ? value.toFixed(digits) + suffix.replace(/ /g, space) : "" }
    function join(parts) { return parts.filter(function(part) { return part !== "" }).join(space + "· ") }
    function prefixed(prefix, value) { return value === "" ? "" : prefix + space + value }
    readonly property string rate: streaming
        ? join([prefixed("串流", fixed(metrics.stream.renderedFps, 0, " FPS")), prefixed("RTT", fixed(metrics.stream.rttMs, 0, " ms"))])
        : game ? join([fixed(metrics.game.submissions, 0, " FPS"), fixed(metrics.game.intervalMedianMs, 1, " ms")])
        : prefixed("界面", fixed(metrics.submissions, 0, " 次/秒"))
    readonly property string load: {
        const clock = info.cpu && info.cpu.scaling_cur_freq > 0 ? fixed(info.cpu.scaling_cur_freq / 1000000, 2, " GHz") : ""
        const usage = fixed(hardware ? info.systemCpu : metrics.cpu, 0, "%")
        const gpu = info.gpuFrequencyHz > 0 ? fixed(info.gpuFrequencyHz / 1000000, 0, " MHz") : ""
        return join([prefixed("CPU", clock), clock === "" ? prefixed("CPU", usage) : usage, prefixed("GPU", gpu)])
    }
    readonly property string health: {
        const memory = valid(info.MemTotal) && valid(info.MemAvailable) && info.MemTotal > 0
            ? ["内存", ((info.MemTotal - info.MemAvailable) / 1024).toFixed(0), "/", (info.MemTotal / 1024).toFixed(0), "MB"].join(space) : ""
        return join([fixed(info.socTemperatureC, 0, " °C"), memory])
    }
    readonly property bool empty: rate === "" && load === "" && health === ""
    readonly property real textWidth: Ui.Theme.perfPanelWidth - 2 * Ui.Theme.space16
    width: Math.min(Ui.Theme.perfPanelWidth, rows.implicitWidth + 2 * Ui.Theme.space16)
    height: rows.implicitHeight + 2 * Ui.Theme.space12
    radius: Ui.Theme.perfPanelRadius
    color: Ui.Theme.alpha(Ui.Theme.surface, Ui.Theme.perfPanelOpacity)
    border.width: 1; border.color: Ui.Theme.outline
    component Reading: Ui.Label {
        visible: text !== ""; width: Math.min(implicitWidth, panel.textWidth)
        wrapMode: Text.WordWrap; elide: Text.ElideNone; tabular: true; fontScale: panel.fontScale
        lineHeightMode: Text.FixedHeight; lineHeight: Math.round(Ui.Theme.type[role].line * panel.fontScale)
    }
    Column {
        id: rows
        x: Ui.Theme.space16; y: Ui.Theme.space12
        Reading { objectName: "performanceRate"; role: "label"; font.weight: Font.Bold; color: Ui.Theme.accent; text: panel.rate }
        Reading { objectName: "performanceLoad"; role: "micro"; color: Ui.Theme.textSecondary; text: panel.load }
        Reading { objectName: "performanceHealth"; role: "micro"; color: Ui.Theme.textSecondary; text: panel.health }
    }
}
