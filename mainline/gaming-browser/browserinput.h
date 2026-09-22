#pragma once
#include "input.h"
#include <QQuickWindow>
#include <QElapsedTimer>
#include <QUrl>

class BrowserInput final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QPointF position READ position NOTIFY moved)
    Q_PROPERTY(bool keyboard READ keyboard WRITE setKeyboard NOTIFY keyboardChanged)
    Q_PROPERTY(bool controllerPointer READ controllerPointer NOTIFY pointerModeChanged)
public:
    explicit BrowserInput(QQuickWindow *window, ControllerInput *controller);
    ~BrowserInput() override;
    QPointF position() const { return m_position; }
    bool keyboard() const { return m_keyboard; }
    bool controllerPointer() const { return m_controllerPointer; }
    void setKeyboard(bool value);
    // The same bounded, calibrated sample path is exercised without a device.
    void sample(const QVariantList &axes, const QStringList &buttons, double seconds, bool active);
    static double speed(double value);
    static bool allowed(const QUrl &url);
    Q_INVOKABLE QUrl address(const QString &text) const;
    Q_INVOKABLE bool allowedUrl(const QUrl &url) const { return allowed(url); }
    Q_INVOKABLE void key(const QString &action) { m_controller->keyboardAction(action); }
    void setSpeeds(double pointer, double scroll) { m_pointerSpeed = pointer; m_scrollSpeed = scroll; }
    bool selfTest = false;
    Q_INVOKABLE void smokeInput(int phase);
signals:
    void moved();
    void keyboardChanged();
    void pointerModeChanged();
    void action(const QString &name);
private:
    bool eventFilter(QObject *object, QEvent *event) override;
    void useControllerPointer(bool enabled);
    void mouse(QEvent::Type type, bool down);
    QQuickWindow *m_window;
    ControllerInput *m_controller;
    QTimer m_timer;
    QElapsedTimer m_clock;
    QPointF m_position{512, 384}, m_scroll;
    QStringList m_buttons;
    bool m_keyboard = false, m_down = false, m_waitNeutral = true;
    bool m_controllerPointer = true, m_sending = false;
    double m_pointerSpeed = 850, m_scrollSpeed = 1000;
};
