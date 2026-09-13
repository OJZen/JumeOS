#include "input.h"
#include <cstdlib>
#include <QGuiApplication>
#include <QKeyEvent>

static QString buttonAction(SDL_GameControllerButton button) {
    switch (button) {
    case SDL_CONTROLLER_BUTTON_A: return "accept";
    case SDL_CONTROLLER_BUTTON_B: return "back";
    case SDL_CONTROLLER_BUTTON_X: return "favorite";
    case SDL_CONTROLLER_BUTTON_Y: return "erase";
    case SDL_CONTROLLER_BUTTON_START: return "submit";
    case SDL_CONTROLLER_BUTTON_BACK:
    case SDL_CONTROLLER_BUTTON_GUIDE: return "quick";
    case SDL_CONTROLLER_BUTTON_LEFTSHOULDER: return "previousTab";
    case SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: return "nextTab";
    default: return {};
    }
}
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
QString ControllerInput::axisAction(Sint16 x, Sint16 y) {
    constexpr int deadzone = 18000;
    if (std::abs(int(x)) < deadzone && std::abs(int(y)) < deadzone) return {};
    if (std::abs(int(x)) > std::abs(int(y))) return x < 0 ? "left" : "right";
    return y < 0 ? "up" : "down";
}
void ControllerInput::suppressUntilNeutral() {
    m_waitForNeutral = true; m_held.clear(); m_repeating = false;
}
void ControllerInput::keyboardAction(const QString &name) {
    auto *focus = QGuiApplication::focusObject();
    if (!focus) return;
    const int key = name == "left" ? Qt::Key_Left : name == "right" ? Qt::Key_Right
        : name == "up" ? Qt::Key_Up : name == "down" ? Qt::Key_Down
        : name == "accept" ? Qt::Key_Return : name == "erase" ? Qt::Key_Backspace : 0;
    if (!key) return;
    // Qt Virtual Keyboard's own focus-object filter owns arrow navigation.
    QKeyEvent press(QEvent::KeyPress, key, Qt::NoModifier), release(QEvent::KeyRelease, key, Qt::NoModifier);
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
            SDL_GameControllerClose(m_controller); m_controller = nullptr; m_held.clear();
            openFirst();
        }
        if (event.type == SDL_CONTROLLERDEVICEADDED) openFirst();
        if (event.type == SDL_CONTROLLERBUTTONDOWN && m_controller &&
            event.cbutton.which == SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(m_controller))) {
            const auto name = buttonAction(SDL_GameControllerButton(event.cbutton.button));
            if (!name.isEmpty() && !m_waitForNeutral) emit action(name, false);
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
    QString held;
    if (m_controller) {
        if (SDL_GameControllerGetButton(m_controller, SDL_CONTROLLER_BUTTON_DPAD_LEFT)) held = "left";
        else if (SDL_GameControllerGetButton(m_controller, SDL_CONTROLLER_BUTTON_DPAD_RIGHT)) held = "right";
        else if (SDL_GameControllerGetButton(m_controller, SDL_CONTROLLER_BUTTON_DPAD_UP)) held = "up";
        else if (SDL_GameControllerGetButton(m_controller, SDL_CONTROLLER_BUTTON_DPAD_DOWN)) held = "down";
        else held = axisAction(SDL_GameControllerGetAxis(m_controller, SDL_CONTROLLER_AXIS_LEFTX),
                               SDL_GameControllerGetAxis(m_controller, SDL_CONTROLLER_AXIS_LEFTY));
    }
    bool neutral = buttons.isEmpty();
    for (const auto &value : axes) neutral = neutral && std::abs(value.toDouble()) < 0.3;
    updateHeld(held, neutral);
    m_timer.setInterval(m_controller ? 16 : 250);
}
void ControllerInput::updateHeld(const QString &held, bool neutral) {
    if (m_waitForNeutral) { if (neutral) m_waitForNeutral = false; return; }
    if (held != m_held) {
        m_held = held; m_repeating = false; m_repeatClock.restart();
        if (!held.isEmpty()) emit action(held, false);
    } else if (!held.isEmpty() && m_repeatClock.elapsed() >= (m_repeating ? 100 : 400)) {
        m_repeating = true; m_repeatClock.restart(); emit action(held, true);
    }
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
    QVariantList axes;
    for (int i = 0; i < 4; ++i) axes.append(double(rawAxes[i]) / 32767.);
    axes.append((keys & (1U << 6)) ? 1. : 0.); axes.append((keys & (1U << 7)) ? 1. : 0.);
    QStringList buttons;
    const auto pressed = keys & ~m_routedKeys;
    m_routedKeys = keys;
    for (unsigned i = 0; i < 17; ++i) if ((keys & (1U << i)) && mapping[i] != SDL_CONTROLLER_BUTTON_INVALID)
        buttons.append(QString::fromLatin1(SDL_GameControllerGetStringForButton(mapping[i])));
    const auto text = buttons.join(" · ");
    if (m_deviceName.isEmpty() || m_axes != axes || m_buttons != text) {
        m_deviceName = QStringLiteral("R46H Routed Gamepad"); m_axes = axes; m_buttons = text; emit stateChanged();
    }
    if (!m_waitForNeutral) for (unsigned i = 0; i < 17; ++i) if (pressed & (1U << i)) {
        const auto actionName = buttonAction(mapping[i]);
        if (!actionName.isEmpty()) emit action(actionName, false);
    }
    const auto held = keys & (1U << 12) ? QString("left") : keys & (1U << 13) ? QString("right")
        : keys & (1U << 10) ? QString("up") : keys & (1U << 11) ? QString("down")
        : axisAction(Sint16(rawAxes[0]), Sint16(rawAxes[1]));
    bool neutral = !keys;
    for (int i = 0; i < 4; ++i) neutral &= std::abs(rawAxes[i]) < 9830;
    updateHeld(held, neutral);
}
