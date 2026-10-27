#pragma once
#include <QObject>
#include <QElapsedTimer>
#include <QSet>
#include <QTimer>
#include <QVariantList>
#include <SDL.h>

// Page-layer controller input (docs/JUME-UI.md §7.3–7.5). Presses emit `action`
// immediately; Select ("quick") is decided on release and swallows chords.
// Only directions repeat: after 380 ms every 90 ms; with `fastRepeat` (lists) a
// direction held for 2 s speeds up to 50 ms. B repeats only with `backRepeat` (the
// keyboard's backspace), so Files and Browser keep a single B press; other keys never.
class ControllerInput final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString deviceName READ deviceName NOTIFY stateChanged)
    Q_PROPERTY(QVariantList axes READ axes NOTIFY stateChanged)
    Q_PROPERTY(QString buttons READ buttons NOTIFY stateChanged)
    Q_PROPERTY(bool fastRepeat READ fastRepeat WRITE setFastRepeat NOTIFY fastRepeatChanged)
    Q_PROPERTY(bool backRepeat READ backRepeat WRITE setBackRepeat NOTIFY backRepeatChanged)
public:
    static constexpr int RepeatDelay = 380, RepeatInterval = 90, FastAfter = 2000, FastInterval = 50;
    explicit ControllerInput(QObject *parent = nullptr, bool routed = false);
    ~ControllerInput() override;
    void poll();
    void suppressUntilNeutral();
    void routedState(quint32 keys, const qint32 axes[4]);
    // Left stick: 55% of full scale engages the primary axis, below 35% releases it.
    static QString stickDirection(Sint16 x, Sint16 y, const QString &current = {});
    QString deviceName() const { return m_deviceName; }
    QVariantList axes() const { return m_axes; }
    QString buttons() const { return m_buttons; }
    bool fastRepeat() const { return m_fastRepeat; }
    void setFastRepeat(bool value) { if (m_fastRepeat != value) { m_fastRepeat = value; emit fastRepeatChanged(); } }
    bool backRepeat() const { return m_backRepeat; }
    void setBackRepeat(bool value) { if (m_backRepeat != value) { m_backRepeat = value; emit backRepeatChanged(); } }
    Q_INVOKABLE void keyboardAction(const QString &name);
signals:
    void action(const QString &name, bool repeated);
    void released(const QString &name);
    // Input ownership changed while keys were held: pending holds and taps end without acting.
    void cancelled();
    // Right stick, signed and scaled 0..1 beyond its dead zone; views scroll without moving focus.
    void scrolled(double velocity);
    void stateChanged();
    void fastRepeatChanged();
    void backRepeatChanged();
private:
    void openFirst();
    void press(const QString &name);
    void release(const QString &name);
    void update(const QSet<QString> &down, double scrollY, bool neutral);
    SDL_GameController *m_controller = nullptr;
    QTimer m_timer;
    QElapsedTimer m_heldClock;
    QSet<QString> m_down, m_swallowed, m_buttonsDown;
    QString m_held, m_direction;
    qint64 m_nextRepeat = 0;
    bool m_triggers[2]{};
    QString m_deviceName, m_buttons;
    QVariantList m_axes = {0., 0., 0., 0., 0., 0.};
    bool m_initialized = false, m_waitForNeutral = false, m_routed = false, m_fastRepeat = false, m_backRepeat = false, m_selectChord = false;
    quint32 m_routedKeys = 0;
};
