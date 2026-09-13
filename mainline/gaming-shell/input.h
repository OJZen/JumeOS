#pragma once
#include <QObject>
#include <QElapsedTimer>
#include <QTimer>
#include <QVariantList>
#include <SDL.h>

class ControllerInput final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString deviceName READ deviceName NOTIFY stateChanged)
    Q_PROPERTY(QVariantList axes READ axes NOTIFY stateChanged)
    Q_PROPERTY(QString buttons READ buttons NOTIFY stateChanged)
public:
    explicit ControllerInput(QObject *parent = nullptr, bool routed = false);
    ~ControllerInput() override;
    void poll();
    void suppressUntilNeutral();
    void routedState(quint32 keys, const qint32 axes[4]);
    static QString axisAction(Sint16 x, Sint16 y);
    QString deviceName() const { return m_deviceName; }
    QVariantList axes() const { return m_axes; }
    QString buttons() const { return m_buttons; }
    Q_INVOKABLE void keyboardAction(const QString &name);
signals:
    void action(const QString &name, bool repeated);
    void stateChanged();
private:
    void openFirst();
    void updateHeld(const QString &held, bool neutral);
    SDL_GameController *m_controller = nullptr;
    QTimer m_timer;
    QElapsedTimer m_repeatClock;
    QString m_held;
    QString m_deviceName, m_buttons;
    QVariantList m_axes = {0., 0., 0., 0., 0., 0.};
    bool m_repeating = false, m_initialized = false;
    bool m_waitForNeutral = false;
    bool m_routed = false;
    quint32 m_routedKeys = 0;
};
