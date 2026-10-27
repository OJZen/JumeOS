pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Shapes

// §5 game card. Without a cover it shows the system color with 135° stripes (white 7%, 14 px);
// apps with an icon use the plain color and a centered white icon; unavailable items are sunken
// and carry a reason badge. Home cards (256, r24) show the title on the card, grid cards (212, r20)
// leave it to the label below. Focus lifts the card to 1.04 with a shadow and the focus ring.
Item {
    id: card
    required property string title
    property string subtitle: ""
    property color cardColor: Theme.cardColor(0)
    property string iconName: ""
    property string badge: ""
    property string badgeIcon: ""
    property bool favorite: false
    property bool selected: false
    property bool showTitle: Math.min(width, height) >= Theme.homeCardSize
    property bool available: true
    property bool focusOutline: true
    property bool reducedMotion: Theme.reducedMotion
    property real fontScale: Theme.fontScale
    readonly property real cornerRadius: Math.min(width, height) >= Theme.homeCardSize ? Theme.radiusCard : Theme.radiusGridCard
    readonly property real stripePeriod: 2 * Theme.stripeWidth / Math.SQRT2
    signal activated()
    signal focused()
    Accessible.role: Accessible.Button
    Accessible.name: title + (subtitle ? "，" + subtitle : "") + (badge ? "，" + badge : "")
    Accessible.onPressAction: activated()
    scale: pointer.pressed && !reducedMotion ? Theme.pressScale : selected ? Theme.cardFocusScale : 1
    Behavior on scale { enabled: !card.reducedMotion; Motion { duration: pointer.pressed ? Theme.pressDuration : Theme.focusDuration } }
    Shadow { target: art; visible: card.selected }
    Shape {
        id: art
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeWidth: card.available ? -1 : 1; strokeColor: card.available ? "transparent" : Theme.outline
            fillColor: card.available ? card.cardColor : Theme.surfaceSunken
            fillGradient: card.available && card.iconName === "" ? stripes : null
            PathRectangle { width: art.width; height: art.height; radius: card.cornerRadius }
        }
        LinearGradient {
            id: stripes
            x1: 0; y1: 0; x2: card.stripePeriod; y2: card.stripePeriod
            spread: ShapeGradient.RepeatSpread
            GradientStop { position: 0; color: Qt.tint(card.cardColor, Theme.cardStripe) }
            GradientStop { position: 0.48; color: Qt.tint(card.cardColor, Theme.cardStripe) }
            GradientStop { position: 0.52; color: card.cardColor }
            GradientStop { position: 1; color: card.cardColor }
        }
    }
    Icon {
        anchors.centerIn: parent; anchors.verticalCenterOffset: card.showTitle ? -Theme.space16 : 0
        width: 64; height: 64; visible: card.iconName !== ""; name: card.iconName
        color: card.available ? Theme.cardText : Theme.textTertiary
    }
    // Status capsule: top right on a card, top left as the reason on an unavailable item.
    Rectangle {
        objectName: "cardBadge"
        x: card.available ? parent.width - width - Theme.space16 : Theme.space16; y: Theme.space16
        visible: card.badge !== ""
        width: badgeRow.implicitWidth + 2 * Theme.space12; height: Theme.cardBadgeHeight; radius: height / 2
        color: Theme.cardText
        Row {
            id: badgeRow; anchors.centerIn: parent; spacing: Theme.space4
            Icon { anchors.verticalCenter: parent.verticalCenter; width: 18; height: 18; visible: card.badgeIcon !== ""; name: card.badgeIcon; color: Theme.cardInk }
            Label { anchors.verticalCenter: parent.verticalCenter; role: "micro"; fontScale: card.fontScale; text: card.badge; color: card.available ? Theme.cardInk : Theme.textSecondary; elide: Text.ElideNone }
        }
    }
    Rectangle {
        objectName: "cardFavorite"
        x: parent.width - width - Theme.space16; y: Theme.space16
        visible: card.favorite && card.badge === ""
        width: Theme.cardBadgeHeight; height: width; radius: width / 2
        color: Theme.alpha(Theme.cardInk, 0.35)
        Icon { anchors.centerIn: parent; width: 20; height: 20; name: "star"; filled: true; color: Theme.cardFavorite }
    }
    Column {
        x: Theme.space24; width: parent.width - 2 * Theme.space24
        anchors.bottom: parent.bottom; anchors.bottomMargin: Theme.space24
        visible: card.showTitle; spacing: Theme.space4
        Label { width: parent.width; role: "title"; fontScale: card.fontScale; text: card.title; color: card.available ? Theme.cardText : Theme.textSecondary }
        Label { width: parent.width; role: "caption"; fontScale: card.fontScale; visible: card.subtitle !== ""; text: card.subtitle; color: card.available ? Theme.alpha(Theme.cardText, 0.88) : Theme.textTertiary }
    }
    Rectangle {
        objectName: "cardFocus"
        anchors.fill: parent; anchors.margins: -(Theme.focusGap + Theme.focusWidth)
        radius: card.cornerRadius + Theme.focusRadiusExtra; color: "transparent"
        border.width: Theme.focusWidth; border.color: Theme.focus
        visible: card.selected && card.focusOutline
    }
    MouseArea { id: pointer; anchors.fill: parent; onClicked: card.activated(); onPressed: card.focused() }
}
