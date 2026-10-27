#include "input.h"
#include <cstdlib>
#include <cmath>
#include <QGuiApplication>
#include <QKeyEvent>

static QString buttonAction(SDL_GameControllerButton button) {
    switch (button) {
    case SDL_CONTROLLER_BUTTON_A: return "accept";
    case SDL_CONTROLLER_BUTTON_B: return "back";
    case SDL_CONTROLLER_BUTTON_X: return "itemAction";
    case SDL_CONTROLLER_BUTTON_Y: return "pageAction";
    case SDL_CONTROLLER_BUTTON_START: return "options";
    case SDL_CONTROLLER_BUTTON_BACK:
    case SDL_CONTROLLER_BUTTON_GUIDE: return "quick";
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: return "prevSection";
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: return "nextSection";
    default: return {};
    }
}
static bool direction(const QString &name) { return name == "up" || name == "down" || name == "left" || name == "right"; }
ControllerInput::ControllerInput(QObject *parent, bool routed) : QObject(parent), m_routed(routed) {
    connect(&m_timer, &QTimer::timeout, this, &ControllerInput::poll);
    if (m_routed) { m_timer.start(16); return; }
    // This opens a controller for this process only; it never grabs system input.
    SDL_SetHint(SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, "1");
    m_initialized = SDL_InitSubSystem(SDL_INIT_GAMECONTROLLER) == 0;
    if (!m_initialized) { qWarning("SDL controller unavailable: %s", SDL_GetError()); return; }
    openFirst();
    m_timer.start(m_controller ? 16 : 250);
}
ControllerInput::~ControllerInput() {
    if (m_controller) SDL_GameControllerClose(m_controller);
    if (m_initialized) SDL_QuitSubSystem(SDL_INIT_GAMECONTROLLER);
}
void ControllerInput::openFirst() {
    if (m_controller) return;
    for (int i = 0; i < SDL_NumJoysticks(); ++i) {
        if (SDL_IsGameController(i) && (m_controller = SDL_GameControllerOpen(i))) break;
    }
}
QString ControllerInput::stickDirection(Sint16 x, Sint16 y, const QString &current) {
    constexpr int engage = 18022, keep = 11469; // 55% and 35% of 32767
    const int ax = std::abs(int(x)), ay = std::abs(int(y));
    if (direction(current)) {
        const bool horizontal = current == "left" || current == "right";
        const int value = horizontal ? x : y, other = horizontal ? ay : ax;
        const bool sameSign = (current == "left" || current == "up") == (value < 0);
        if (sameSign && std::abs(value) >= keep && !(other >= engage && other > std::abs(value))) return current;
    }
    if (ax < engage && ay < engage) return {};
    if (ax > ay) return x < 0 ? "left" : "right";
    return y < 0 ? "up" : "down";
}
void ControllerInput::suppressUntilNeutral() {
    const bool holding = !m_down.isEmpty();
    m_down.clear(); m_swallowed.clear(); m_held.clear(); m_selectChord = false;
    m_waitForNeutral = true;
    if (holding) emit cancelled();
}
void ControllerInput::press(const QString &name) {
    if (name.isEmpty() || m_waitForNeutral || m_down.contains(name)) return;
    m_down.insert(name);
    if (name == "quick") { m_selectChord = false; return; }
    // Select + another key belongs to the system layer; the page sees neither (§7.2).
    if (m_down.contains("quick")) { m_selectChord = true; m_swallowed.insert(name); return; }
    emit action(name, false);
    if (direction(name) || (name == "back" && m_backRepeat)) { m_held = name; m_heldClock.restart(); m_nextRepeat = RepeatDelay; }
}
void ControllerInput::release(const QString &name) {
    if (!m_down.remove(name)) return;
    if (name == m_held) m_held.clear();
    if (name == "quick") { if (!m_selectChord) emit action(name, false); m_selectChord = false; return; }
    if (!m_swallowed.remove(name)) emit released(name);
}
void ControllerInput::update(const QSet<QString> &down, double scrollY, bool neutral) {
    // Releases before presses, so a changed direction never overlaps the old one.
    auto ended = m_down; ended.subtract(down);
    for (const auto &name : std::as_const(ended)) release(name);
    for (const auto &name : {"accept", "back", "itemAction", "pageAction", "options", "quick", "prevSection", "nextSection",
                             "pageUp", "pageDown", "up", "down", "left", "right"})
        if (down.contains(name)) press(name);
    if (m_waitForNeutral) { if (neutral) m_waitForNeutral = false; return; }
    if (!m_held.isEmpty()) {
        const auto elapsed = m_heldClock.elapsed();
        if (elapsed >= m_nextRepeat) {
            const bool fast = m_fastRepeat && direction(m_held) && elapsed >= FastAfter;
            m_nextRepeat += fast ? FastInterval : RepeatInterval;
            if (m_nextRepeat <= elapsed) m_nextRepeat = elapsed + (fast ? FastInterval : RepeatInterval);
            emit action(m_held, true);
        }
    }
    constexpr double scrollDeadzone = 0.2;
    if (std::abs(scrollY) >= scrollDeadzone)
        emit scrolled(std::copysign((std::abs(scrollY) - scrollDeadzone) / (1 - scrollDeadzone), scrollY));
}
void ControllerInput::keyboardAction(const QString &name) {
    auto *focus = QGuiApplication::focusObject();
    if (!focus) return;
    const int key = name == "left" ? Qt::Key_Left : name == "right" ? Qt::Key_Right
        : name == "up" ? Qt::Key_Up : name == "down" ? Qt::Key_Down : name == "accept" ? Qt::Key_Return
        : name == "erase" ? Qt::Key_Backspace : name == "space" ? Qt::Key_Space : 0;
    if (!key) return;
    const auto text = key == Qt::Key_Space ? QStringLiteral(" ") : QString();
    // Qt Virtual Keyboard's own focus-object filter owns arrow navigation.
    QKeyEvent press(QEvent::KeyPress, key, Qt::NoModifier, text), release(QEvent::KeyRelease, key, Qt::NoModifier, text);
    QGuiApplication::sendEvent(focus, &press);
    QGuiApplication::sendEvent(focus, &release);
}
void ControllerInput::poll() {
    if (m_routed) {
        const qint32 axes[]{qRound(m_axes[0].toDouble() * 32767), qRound(m_axes[1].toDouble() * 32767),
                            qRound(m_axes[2].toDouble() * 32767), qRound(m_axes[3].toDouble() * 32767)};
        routedState(m_routedKeys, axes); return;
    }
    if (!m_initialized) return;
    SDL_Event event;
    while (SDL_PollEvent(&event)) {
        if (event.type == SDL_CONTROLLERDEVICEREMOVED && m_controller &&
            event.cdevice.which == SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(m_controller))) {
            SDL_GameControllerClose(m_controller); m_controller = nullptr; m_buttonsDown.clear();
            openFirst();
        }
        if (event.type == SDL_CONTROLLERDEVICEADDED) openFirst();
        // Button events keep taps that start and end between two polls.
        if ((event.type == SDL_CONTROLLERBUTTONDOWN || event.type == SDL_CONTROLLERBUTTONUP) && m_controller &&
            event.cbutton.which == SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(m_controller))) {
            const auto name = buttonAction(SDL_GameControllerButton(event.cbutton.button));
            if (name.isEmpty()) continue;
            if (event.type == SDL_CONTROLLERBUTTONDOWN) { m_buttonsDown.insert(name); press(name); }
            else { m_buttonsDown.remove(name); release(name); }
        }
    }
    QVariantList axes = {0., 0., 0., 0., 0., 0.};
    QStringList buttons;
    QString deviceName;
    if (m_controller) {
        deviceName = QString::fromUtf8(SDL_GameControllerName(m_controller));
        for (int axis = 0; axis < SDL_CONTROLLER_AXIS_MAX; ++axis) {
            const auto value = SDL_GameControllerGetAxis(m_controller, SDL_GameControllerAxis(axis));
            axes[axis] = double(value) / (value < 0 ? 32768. : 32767.);
        }
        for (int button = 0; button < SDL_CONTROLLER_BUTTON_MAX; ++button)
            if (SDL_GameControllerGetButton(m_controller, SDL_GameControllerButton(button)))
                buttons.append(QString::fromUtf8(SDL_GameControllerGetStringForButton(SDL_GameControllerButton(button))));
    }
    const auto pressed = buttons.join(" · ");
    if (axes != m_axes || pressed != m_buttons || deviceName != m_deviceName) {
        m_axes = axes; m_buttons = pressed; m_deviceName = deviceName; emit stateChanged();
    }
    auto down = m_buttonsDown;
    if (m_controller) {
        const auto held = [&](SDL_GameControllerButton button) { return SDL_GameControllerGetButton(m_controller, button) != 0; };
        m_direction = held(SDL_CONTROLLER_BUTTON_DPAD_LEFT) ? "left" : held(SDL_CONTROLLER_BUTTON_DPAD_RIGHT) ? "right"
            : held(SDL_CONTROLLER_BUTTON_DPAD_UP) ? "up" : held(SDL_CONTROLLER_BUTTON_DPAD_DOWN) ? "down"
            : stickDirection(SDL_GameControllerGetAxis(m_controller, SDL_CONTROLLER_AXIS_LEFTX),
                             SDL_GameControllerGetAxis(m_controller, SDL_CONTROLLER_AXIS_LEFTY), m_direction);
        // Analog L2/R2 page above 50% travel and release below 35%.
        for (int i = 0; i < 2; ++i) {
            const double travel = axes[4 + i].toDouble();
            m_triggers[i] = travel >= 0.5 || (m_triggers[i] && travel >= 0.35);
        }
    } else { m_direction.clear(); m_triggers[0] = m_triggers[1] = false; }
    if (!m_direction.isEmpty()) down.insert(m_direction);
    if (m_triggers[0]) down.insert("pageUp");
    if (m_triggers[1]) down.insert("pageDown");
    bool neutral = buttons.isEmpty();
    for (const auto &value : axes) neutral = neutral && std::abs(value.toDouble()) < 0.3;
    update(down, axes[3].toDouble(), neutral);
    m_timer.setInterval(m_controller ? 16 : 250);
}
void ControllerInput::routedState(quint32 keys, const qint32 rawAxes[4]) {
    if (!m_routed || (keys & ~0x1ffffU)) return;
    for (int i = 0; i < 4; ++i) if (rawAxes[i] < -32767 || rawAxes[i] > 32767) return;
    // Preserve the accepted R46H physical layout: East=A and South=B.
    constexpr SDL_GameControllerButton mapping[]{SDL_CONTROLLER_BUTTON_B, SDL_CONTROLLER_BUTTON_A,
        SDL_CONTROLLER_BUTTON_X, SDL_CONTROLLER_BUTTON_Y, SDL_CONTROLLER_BUTTON_LEFTSHOULDER,
        SDL_CONTROLLER_BUTTON_RIGHTSHOULDER, SDL_CONTROLLER_BUTTON_INVALID, SDL_CONTROLLER_BUTTON_INVALID,
        SDL_CONTROLLER_BUTTON_BACK, SDL_CONTROLLER_BUTTON_START, SDL_CONTROLLER_BUTTON_DPAD_UP,
        SDL_CONTROLLER_BUTTON_DPAD_DOWN, SDL_CONTROLLER_BUTTON_DPAD_LEFT, SDL_CONTROLLER_BUTTON_DPAD_RIGHT,
        SDL_CONTROLLER_BUTTON_LEFTSTICK, SDL_CONTROLLER_BUTTON_RIGHTSTICK, SDL_CONTROLLER_BUTTON_INVALID};
    // Router bits 0-9: B A X Y L1 R1 L2 R2 Select Start (L2/R2 are digital here).
    static const char *const names[]{"back", "accept", "itemAction", "pageAction", "prevSection", "nextSection",
        "pageUp", "pageDown", "quick", "options"};
    QVariantList axes;
    for (int i = 0; i < 4; ++i) axes.append(double(rawAxes[i]) / 32767.);
    axes.append((keys & (1U << 6)) ? 1. : 0.); axes.append((keys & (1U << 7)) ? 1. : 0.);
    QStringList buttons;
    m_routedKeys = keys;
    for (unsigned i = 0; i < 17; ++i) if ((keys & (1U << i)) && mapping[i] != SDL_CONTROLLER_BUTTON_INVALID)
        buttons.append(QString::fromLatin1(SDL_GameControllerGetStringForButton(mapping[i])));
    const auto text = buttons.join(" · ");
    if (m_deviceName.isEmpty() || m_axes != axes || m_buttons != text) {
        m_deviceName = QStringLiteral("R46H Routed Gamepad"); m_axes = axes; m_buttons = text; emit stateChanged();
    }
    QSet<QString> down;
    for (unsigned i = 0; i < 10; ++i) if (keys & (1U << i)) down.insert(QString::fromLatin1(names[i]));
    m_direction = keys & (1U << 12) ? QString("left") : keys & (1U << 13) ? QString("right")
        : keys & (1U << 10) ? QString("up") : keys & (1U << 11) ? QString("down")
        : stickDirection(Sint16(rawAxes[0]), Sint16(rawAxes[1]), m_direction);
    if (!m_direction.isEmpty()) down.insert(m_direction);
    bool neutral = !keys;
    for (int i = 0; i < 4; ++i) neutral &= std::abs(rawAxes[i]) < 9830;
    update(down, double(rawAxes[3]) / 32767., neutral);
}
