pragma ComponentBehavior: Bound
import QtQuick
import "controls" as Ui

Rectangle {
    id: panel
    required property var metrics
    property var device: null
    readonly property bool hardware: device !== null && device.target
    property real fontScale: Ui.Theme.fontScale
    property bool compact: false
    readonly property bool game: metrics.game && metrics.game.active === true
    readonly property bool streaming: metrics.stream && metrics.stream.active === true
    width: compact || hardware || game || streaming ? 360 : 510; height: (hardware ? 150 : 128) + (streaming ? 102 : game ? 54 : 0); radius: 16
    color: "#ee12242e"; border.color: "#446271"
    layer.enabled: true
    function number(value, suffix) { return typeof value !== "number" || !isFinite(value) || value < 0 ? "—" : value.toFixed(1) + suffix }
    function frequency(value) { return value > 0 ? (value / 1000).toFixed(0) : "—" }
    function frequencyHz(value) { return value > 0 ? (value / 1000000).toFixed(0) : "—" }
    readonly property string thermalStatus: !hardware ? "" : device.info.cpuCoolingState > 0 && device.info.gpuCoolingState > 0 ? "CPU/GPU 温控限频"
        : device.info.cpuCoolingState > 0 ? "CPU 温控限频" : device.info.gpuCoolingState > 0 ? "GPU 温控限频"
        : device.info.cpuCoolingState === 0 && device.info.gpuCoolingState === 0 ? "温控未介入" : "温控状态未知"
    Ui.Label { x: 18; y: 14; text: panel.streaming ? "性能 · 串流与桌面" : panel.game ? "性能 · 游戏与桌面" : panel.hardware ? "性能 · 系统与界面" : "性能 · 当前预览进程"; color: Ui.Theme.accent; font.bold: true; font.pixelSize: 15 * panel.fontScale }
    Ui.Label {
        x: 18; y: 42; color: "#eef5fa"; font.pixelSize: 14 * panel.fontScale; lineHeight: 1.3
        text: "CPU  " + panel.number(panel.hardware ? panel.device.info.systemCpu : panel.metrics.cpu, "%")
    }
    Ui.Label { x: 170; y: 42; color: "#eef5fa"; font.pixelSize: 14 * panel.fontScale; text: panel.hardware ? "桌面  " + panel.number(panel.metrics.cpu, "%") : "RSS  " + panel.number(panel.metrics.memoryMiB, " MiB") }
    Ui.Label { objectName: "hudMemory"; x: 18; y: 69; color: "#eef5fa"; font.pixelSize: 14 * panel.fontScale; text: panel.hardware ? "可用内存  " + panel.number(panel.device.info.MemAvailable / 1024, "") + " / " + panel.number(panel.device.info.MemTotal / 1024, " MiB") : "界面更新  " + panel.number(panel.metrics.submissions, " 次/秒") }
    Ui.Label { objectName: "hudTemperature"; x: 18; y: 95; visible: panel.hardware; color: Ui.Theme.text; font.pixelSize: 12 * panel.fontScale; text: "芯片  " + panel.number(panel.hardware ? panel.device.info.socTemperatureC : -1, " °C") }
    Ui.Label { x: 170; y: 95; visible: panel.hardware; color: Ui.Theme.text; font.pixelSize: 12 * panel.fontScale; text: panel.hardware ? "CPU  " + panel.frequency(panel.device.info.cpu.scaling_cur_freq) + " / " + panel.frequency(panel.device.info.cpu.scaling_max_freq) + " MHz" : "" }
    Ui.Label { x: 350; y: 18; visible: !panel.compact && !panel.hardware && !panel.game && !panel.streaming; text: "CPU · 最近 60 次"; color: "#a1b4c1"; font.pixelSize: 11 * panel.fontScale }
    Row {
        x: 350; y: 46; width: 142; height: 40; spacing: 0.4
        visible: !panel.compact && !panel.hardware && !panel.game && !panel.streaming
        Repeater {
            model: panel.metrics.history
            Rectangle {
                required property real modelData
                width: 2; height: Math.max(1, Math.min(100, modelData) / 100 * 40)
                y: 40 - height; color: modelData < 0 ? "#45616d" : Ui.Theme.accent
            }
        }
    }
    Ui.Label {
        objectName: "hudGpuFrequency"; x: 18; y: panel.hardware ? 123 : 104; text: panel.hardware ? "GPU " + panel.frequencyHz(panel.device.info.gpuFrequencyHz) + " MHz · " + panel.thermalStatus + " · 界面 " + panel.number(panel.metrics.submissions, " 次/秒") : "按需刷新 · 界面更新不是游戏 FPS"; color: "#a1b4c1"; font.pixelSize: 11 * panel.fontScale
    }
    Ui.Label { objectName: "gameFrameRate"; x: 18; y: panel.hardware ? 150 : 130; visible: panel.game || panel.streaming; color: Ui.Theme.accent; font.pixelSize: 15 * panel.fontScale; text: panel.streaming ? "串流渲染  " + panel.number(panel.metrics.stream.renderedFps, " FPS") : "游戏提交  " + panel.number(panel.metrics.game.submissions, " FPS") }
    Ui.Label { objectName: "gameFrameIntervals"; x: 18; y: panel.hardware ? 177 : 157; visible: panel.game || panel.streaming; color: Ui.Theme.text; font.pixelSize: 12 * panel.fontScale; text: panel.streaming ? "解码  " + panel.number(panel.metrics.stream.decodeMs, " ms") + "  ·  RTT " + panel.number(panel.metrics.stream.rttMs, " ms") : "间隔  " + panel.number(panel.metrics.game.intervalMedianMs, " ms") + "  ·  P95 " + panel.number(panel.metrics.game.intervalP95Ms, " ms") }
    Ui.Label { x: 18; y: panel.hardware ? 202 : 182; visible: panel.streaming; color: Ui.Theme.text; font.pixelSize: 12 * panel.fontScale; text: "网络丢帧  " + panel.number(panel.metrics.stream.networkDropPercent, "%") + "  ·  排队 " + panel.number(panel.metrics.stream.queueMs, " ms") }
    Ui.Label { x: 18; y: panel.hardware ? 227 : 207; visible: panel.streaming; color: Ui.Theme.text; font.pixelSize: 12 * panel.fontScale; text: "音频接收队列  " + panel.number(panel.metrics.stream.audioNetworkQueueMs, " ms") }
}
