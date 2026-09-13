#pragma once
#include <QElapsedTimer>
#include <QJsonObject>
#include <QLocalServer>
#include <QLocalSocket>
#include <QPointer>

class QQuickView;
class Preferences;
class DeviceState;
class Telemetry;
class HandheldSession;
class QImage;

int runControlCall(const QString &directory);

// Opt-in UI actions and bounded game input; never an arbitrary command endpoint.
class ControlServer final : public QObject {
public:
    ControlServer(QQuickView *view, Preferences *preferences, DeviceState *device, Telemetry *telemetry, HandheldSession *handheld = nullptr);
    ~ControlServer() override;
    bool start(const QString &directory, QString *error);
private:
    void accept();
    void receive(QLocalSocket *socket);
    void reply(QLocalSocket *socket, QJsonObject response);
    QJsonObject observe(bool screenshot);
    void encodeImage(QJsonObject &capture, const QImage &image);
    void observeAndReply(QLocalSocket *socket, const QString &id, bool screenshot);
    QQuickView *m_view;
    Preferences *m_preferences;
    DeviceState *m_device;
    Telemetry *m_telemetry;
    HandheldSession *m_handheld;
    QLocalServer m_server;
    QPointer<QLocalSocket> m_client;
    QPointer<QLocalSocket> m_captureClient;
    QPointer<QLocalSocket> m_gameClient;
    QString m_captureRequest;
    QElapsedTimer m_clock;
    QString m_session, m_binary;
    qint64 m_sequence = 0;
};
