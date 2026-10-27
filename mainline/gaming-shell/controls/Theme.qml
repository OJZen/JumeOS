pragma Singleton
import QtQuick

// Jume UI v1 tokens (docs/JUME-UI.md §1–6). One application owner binds
// fontScale, reducedMotion, night and canvasWidth; pages only read tokens.
QtObject {
    property real fontScale: 1
    property bool reducedMotion: false
    property bool night: false
    property real canvasWidth: 1024
    readonly property int canvasHeight: 768
    readonly property var fontPercents: [90, 100, 115, 130]
    readonly property string fontFamily: "Noto Sans SC"

    // §2 colors: same token, light or night value.
    readonly property color ground: night ? "#0F1316" : "#F2F4F5"
    readonly property color surface: night ? "#1A2024" : "#FFFFFF"
    readonly property color surfaceSunken: night ? "#252C31" : "#E8ECEE"
    readonly property color outline: night ? "#343D44" : "#D9DEE2"
    readonly property color text: night ? "#EDF1F3" : "#14181B"
    readonly property color textSecondary: night ? "#A7B2B9" : "#48535B"
    readonly property color textTertiary: night ? "#8D989F" : "#5F6B73"
    readonly property color focus: night ? "#45D3BF" : "#009482"
    readonly property color accent: night ? "#45D3BF" : "#00756A"
    readonly property color accentText: night ? "#062A25" : "#FFFFFF"
    readonly property color accentSoft: night ? "#143833" : "#DDF2EE"
    readonly property color accentInk: night ? "#7FE3D4" : "#005A51"
    readonly property color glyph: night ? "#E3E8EB" : "#2A3136"
    readonly property color glyphText: night ? "#14181B" : "#FFFFFF"
    readonly property color glyphSoft: night ? "#343D44" : "#DDE2E6"
    readonly property color glyphSoftText: night ? "#EDF1F3" : "#14181B"
    readonly property color danger: night ? "#FF8A7A" : "#B3261E"
    readonly property color warning: night ? "#F2C46D" : "#9A5B00"
    readonly property color scrim: night ? Qt.rgba(0, 0, 0, 0.60) : Qt.rgba(20 / 255, 24 / 255, 27 / 255, 0.48)
    // §5 component colors; the spec gives one value, so night reuses it where legible.
    readonly property color track: glyphSoft
    readonly property color switchOff: night ? "#4A555C" : "#C9D0D5"
    // Light in both modes; on/off is carried by the track color alone.
    readonly property color switchThumb: "#FFFFFF"
    readonly property color disabledText: "#8E99A1"
    readonly property color errorToast: "#FBE9E7"
    readonly property color errorToastText: "#8E1D17"
    readonly property color cardText: "#FFFFFF"
    readonly property color cardStripe: alpha(cardText, 0.07)
    // Controller pointer keeps a dark outline and light fill on any page.
    readonly property color pointer: "#FFFFFF"
    readonly property color pointerOutline: "#14181B"
    // Preview-only simulation of a switched-off panel.
    readonly property color blackout: "#000000"
    // Fallback card colors keep their value in both modes (sampled from the v1 references).
    readonly property var cardPalette: ["#C65A3A", "#3D6E9E", "#2F55A4", "#A24D7C", "#6B7F3A"]
    function cardColor(index) { return cardPalette[Math.abs(index) % cardPalette.length] }
    // Solid danger buttons; night keeps the dark text that the light danger value needs.
    readonly property color dangerText: night ? "#14181B" : "#FFFFFF"
    // Badges on fixed-color cards (状态胶囊、收藏星标) look the same in both modes.
    readonly property color cardInk: "#14181B"
    readonly property color cardFavorite: "#F2C46D"
    // Translucent variants derive from tokens; pages never spell out a color.
    function alpha(color, opacity) { return Qt.rgba(color.r, color.g, color.b, opacity) }
    // Press feedback deepens light surfaces and lightens night ones.
    function pressed(color) { return night ? Qt.lighter(color, 1.15) : Qt.darker(color, 1.08) }

    // §3 type ramp: size / line height / weight before fontScale.
    readonly property var type: ({
        display: {size: 36, line: 44, weight: Font.Bold},
        title: {size: 30, line: 38, weight: Font.Bold},
        headline: {size: 26, line: 34, weight: Font.Bold},
        body: {size: 24, line: 32, weight: Font.Medium},
        label: {size: 22, line: 30, weight: Font.Medium},
        caption: {size: 20, line: 26, weight: Font.Normal},
        micro: {size: 18, line: 24, weight: Font.Medium}
    })
    readonly property int glyphMinSize: 16
    readonly property int glyphMaxSize: 19
    function fontSize(role) { return Math.round((type[role] || type.body).size * fontScale) }
    function lineHeight(role) { return Math.round((type[role] || type.body).line * fontScale) }

    // §4 spacing, layout, corners, depth and focus.
    readonly property int space4: 4
    readonly property int space8: 8
    readonly property int space12: 12
    readonly property int space16: 16
    readonly property int space24: 24
    readonly property int space32: 32
    readonly property int space40: 40
    readonly property int space48: 48
    readonly property int topBarHeight: 72
    readonly property int hintBarHeight: 64
    readonly property int margin: Math.max(40, Math.floor(canvasWidth * 0.04))
    readonly property int contentWidth: canvasWidth - 2 * margin
    readonly property int contentHeight: canvasHeight - topBarHeight - hintBarHeight
    readonly property bool dualPane: canvasWidth >= 900
    readonly property int gridCard: 212
    readonly property int gridGap: 32
    readonly property int gridColumns: Math.max(1, Math.floor((contentWidth + gridGap) / (gridCard + gridGap)))
    readonly property int gridCellWidth: Math.floor(Math.min(gridCard * 1.12, (contentWidth - (gridColumns - 1) * gridGap) / gridColumns))
    readonly property int radiusBadge: 8
    readonly property int radiusKey: 12
    readonly property int radiusRow: 16
    readonly property int radiusGridCard: 20
    readonly property int radiusCard: 24
    readonly property int radiusPanel: 28
    readonly property int listRowHeight: 72
    readonly property int listRowTallHeight: 96
    readonly property int minTarget: 56
    readonly property int sectionIndent: 24
    readonly property int focusWidth: 4
    readonly property int focusGap: 4
    readonly property int focusRadiusExtra: 7
    readonly property real cardFocusScale: 1.04
    readonly property real dockFocusScale: 1.06
    readonly property real pressScale: 0.97
    readonly property real settleScale: 1.03
    readonly property int edgeBounce: 6
    readonly property var iconSizes: [24, 28, 40, 64]

    // §5 component geometry.
    readonly property int buttonHeight: 56
    readonly property int buttonPadding: 28
    readonly property int switchWidth: 64
    readonly property int switchHeight: 36
    readonly property int thumbSize: 28
    readonly property int thumbAdjustingSize: 36
    readonly property int trackHeight: 8
    readonly property int iconSize: 24
    readonly property real sliderStep: 0.05
    readonly property int thumbRing: 3
    readonly property int tabHeight: 48
    readonly property int glyphBarSize: 34
    readonly property int glyphInlineSize: 30
    readonly property int glyphKeySize: 26
    readonly property int homeCardSize: 256
    readonly property int cardBadgeHeight: 32
    readonly property int stripeWidth: 14
    readonly property int dockTileSize: 88
    readonly property int dockIconSize: 40
    readonly property int dockGap: 48
    readonly property int hudWidth: 280
    readonly property int hudHeight: 56
    readonly property int dialogMaxWidth: 560
    readonly property int quickPanelWidth: 392
    readonly property int quickPanelInset: 24
    readonly property int holdRingSize: 88
    readonly property int perfPanelInset: 24
    readonly property int perfPanelWidth: 360
    readonly property int perfPanelRadius: 20
    readonly property real perfPanelOpacity: 0.92
    readonly property int shadowSpread: 24

    // §6 motion (ms) and curves; reducedMotion is applied by Motion and callers.
    readonly property int pressDuration: 80
    readonly property int focusDuration: 120
    readonly property int settleDuration: 260
    readonly property int pageEnterDuration: 220
    readonly property int pageExitDuration: 160
    readonly property int pageShift: 48
    readonly property int pageExitShift: 24
    readonly property int reducedFadeDuration: 100
    readonly property int sheetEnterDuration: 240
    readonly property int sheetExitDuration: 180
    readonly property int dialogEnterDuration: 200
    readonly property int dialogExitDuration: 140
    readonly property real dialogStartScale: 0.96
    readonly property int hudEnterDuration: 180
    readonly property int hudExitDuration: 140
    readonly property int hudDwell: 1800
    readonly property int toastDwell: 2400
    readonly property int holdDelay: 600
    readonly property int themeDuration: 200
    readonly property var curves: ({
        standard: [0.25, 1, 0.5, 1, 1, 1],
        emphasized: [0.2, 0.9, 0.1, 1, 1, 1],
        exit: [0.4, 0, 1, 1, 1, 1]
    })

    // Pre-v1 page metrics still read by pages that §8 replaces; remove with them.
    readonly property color background: ground
    readonly property color raised: surfaceSunken
    readonly property color muted: textSecondary
    readonly property int gap: 8
    readonly property int labelGap: 12
    readonly property int padding: 20
    readonly property int radius: 12
    readonly property int rowHeight: 60
    readonly property int fieldHeight: 56
    readonly property int sidebarWidth: 256
    readonly property int columnGap: 32
    readonly property int detailX: sidebarWidth + columnGap
    readonly property int toolTop: 100
    readonly property int toolHeight: 576
    readonly property int contentY: 96
    readonly property int headerIconSize: 32
    readonly property int popupDuration: sheetEnterDuration
}
