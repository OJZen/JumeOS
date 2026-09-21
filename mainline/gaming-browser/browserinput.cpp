#include "browserinput.h"
#include <QGuiApplication>
#include <QMouseEvent>
#include <QWheelEvent>
#include <QUrlQuery>
#include <algorithm>
#include <cmath>

BrowserInput::BrowserInput(QQuickWindow *window, ControllerInput *controller)
    : m_window(window), m_controller(controller)
{
    connect(controller, &ControllerInput::action, this, [this](const QString &name, bool) {
        if (m_window->isActive() && !m_waitNeutral && m_keyboard
            && QStringList{"left", "right", "up", "down"}.contains(name)) emit action(name);
    });
    connect(&m_timer, &QTimer::timeout, this, [this] {
        sample(m_controller->axes(), m_controller->buttons().split(" · ", Qt::SkipEmptyParts),
               m_clock.restart() / 1000., m_window->isActive());
    });
    connect(window, &QWindow::activeChanged, this, [this] {
        if (!m_window->isActive()) sample({}, {}, 0, false);
    });
    m_clock.start(); m_timer.start(16);
}

double BrowserInput::speed(double value)
{
    if (!std::isfinite(value)) return 0;
    // Hardware drift and precision near the center: 18% dead zone, quadratic ramp.
    const double magnitude = std::clamp((std::abs(value) - .18) / .82, 0., 1.);
    return std::copysign(magnitude * magnitude, value);
}

void BrowserInput::mouse(QEvent::Type type, bool down)
{
    m_down = down;
    QMouseEvent event(type, m_position, m_window->mapToGlobal(m_position),
        type == QEvent::MouseMove ? Qt::NoButton : Qt::LeftButton,
        down ? Qt::LeftButton : Qt::NoButton, Qt::NoModifier);
    QGuiApplication::sendEvent(m_window, &event);
}

void BrowserInput::setKeyboard(bool value)
{
    if (value == m_keyboard) return;
    if (m_down) mouse(QEvent::MouseButtonRelease, false);
    m_keyboard = value; m_scroll = {}; m_waitNeutral = true;
    emit keyboardChanged();
}

void BrowserInput::sample(const QVariantList &axes, const QStringList &buttons, double seconds, bool active)
{
    if (!active) {
        if (m_down) {
            // Cancel a held click when the quick panel takes focus; releasing on
            // the original link/button would otherwise activate it behind the panel.
            const auto saved = m_position; m_position = {-100, -100};
            mouse(QEvent::MouseButtonRelease, false); m_position = saved;
        }
        m_waitNeutral = true; m_buttons.clear(); m_scroll = {}; return;
    }
    bool neutral = buttons.isEmpty();
    for (const auto &axis : axes) neutral &= std::abs(axis.toDouble()) <= .18;
    if (m_waitNeutral) {
        m_buttons = buttons;
        if (neutral) m_waitNeutral = false;
        return;
    }
    const auto pressed = [&](const char *name) { return buttons.contains(name) && !m_buttons.contains(name); };
    const bool b = buttons.contains("b"); // SDL mapping supplied by the foreground manager: physical South=B.
    if (!m_keyboard) {
        const double dt = std::isfinite(seconds) ? std::clamp(seconds, 0., .05) : 0;
        auto axis = [&](int index) { return speed(axes.value(index).toDouble()); };
        const QPointF old = m_position;
        m_position = {std::clamp(m_position.x() + axis(2) * m_pointerSpeed * dt, 0., double(std::max(0, m_window->width() - 1))),
                      std::clamp(m_position.y() + axis(3) * m_pointerSpeed * dt, 0., double(std::max(0, m_window->height() - 1)))};
        if (old != m_position) { mouse(QEvent::MouseMove, m_down); emit moved(); }
        if (b != m_down) mouse(b ? QEvent::MouseButtonPress : QEvent::MouseButtonRelease, b);
        m_scroll += QPointF(-axis(0), -axis(1)) * (m_scrollSpeed * dt);
        const QPoint pixels(int(m_scroll.x()), int(m_scroll.y()));
        if (!pixels.isNull()) {
            m_scroll -= pixels;
            // Native wheel delivery: scrolls nested frames/elements under the cursor too.
            QWheelEvent event(m_position, m_window->mapToGlobal(m_position), pixels, pixels * 3,
                              m_down ? Qt::LeftButton : Qt::NoButton, Qt::NoModifier, Qt::NoScrollPhase, false);
            QGuiApplication::sendEvent(m_window, &event);
        }
    } else if (pressed("b")) emit action("accept");
    if (pressed("y")) emit action(m_keyboard ? "dismiss" : "back");
    if (pressed("a") && !m_keyboard) emit action("forward");
    if (pressed("x")) emit action(m_keyboard ? "erase" : "reload");
    if (pressed("start")) emit action(m_keyboard ? "submit" : "address");
    if (pressed("back")) emit action(m_keyboard ? "dismiss" : "keyboard");
    if (!m_keyboard && pressed("leftshoulder")) emit action("previousTab");
    if (!m_keyboard && pressed("rightshoulder")) emit action("nextTab");
    m_buttons = buttons;
}

bool BrowserInput::allowed(const QUrl &url)
{
    if (!url.isValid() || !url.userInfo().isEmpty()) return false;
    if (url.scheme() == "https" || url.scheme() == "http") return !url.host().isEmpty();
    return url == QUrl("about:blank") || url == QUrl("chrome://gpu") || url == QUrl("chrome://gpu/")
        || url == QUrl("chrome://version") || url == QUrl("chrome://version/")
        || url == QUrl("chrome://media-internals") || url == QUrl("chrome://media-internals/");
}

QUrl BrowserInput::address(const QString &text) const
{
    const auto value = text.trimmed();
    if (value.isEmpty() || value.size() > 8192) return {};
    QUrl url(value);
    // Never turn an explicit unsupported scheme into a file or executable handler.
    if (!url.scheme().isEmpty()) return allowed(url) ? url : QUrl();
    if (!value.contains(' ') && (value.contains('.') || value == "localhost")) {
        url = QUrl("https://" + value); return allowed(url) ? url : QUrl();
    }
    url = QUrl("https://duckduckgo.com/");
    QUrlQuery query; query.addQueryItem("q", value); url.setQuery(query); return url;
}

void BrowserInput::smokeInput(int phase)
{
    if (!selfTest) return;
    const QVariantList zero{0.,0.,0.,0.};
    sample(zero, {}, .016, true);
    if (phase == 1 || phase == 3) sample(zero, {phase == 1 ? "b" : "start"}, .016, true);
    if (phase == 2) for (int i = 0; i < 5; ++i) sample({0.,1.,0.,0.}, {}, .05, true);
    if (phase == 4) { key("down"); sample(zero, {"b"}, .016, true); }
    sample(zero, {}, .016, true);
}
