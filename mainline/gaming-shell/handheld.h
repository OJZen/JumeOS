#pragma once
#include <QObject>
#include <QProcess>
#include <QLocalSocket>
#include <QJsonObject>
#include <QSocketNotifier>
#include <QTimer>
#include <memory>
#include <QImage>
#include <QThread>
struct wl_callback;
class ControllerInput;
class Applications;
class QQuickView;

// Opt-in bridge to the separately supervised Weston policy and input router.
class HandheldSession final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool ready READ ready NOTIFY changed)
public:
    HandheldSession(QQuickView *view, ControllerInput *input, Applications *applications);
    ~HandheldSession() override;
    bool start(const QString &router, const QString &device, QString *error, int uinputFd = -1);
    bool ready() const { return m_ready; }
    bool requestCapture();
    void showDesktop(bool tasks);
    quint64 inputSequence() const { return m_inputSequence; }
    bool gameInputAvailable() const;
    bool injectGame(quint32 keys, const qint32 axes[4], int milliseconds, quint64 expectedSequence, const QString &application);
    void cancelGameInput();
    QJsonObject frameMetrics() const { return m_frameMetrics; }
signals:
    void changed();
    void failed(const QString &message);
    void captureFinished(const QImage &image, const QString &error);
    void gameInputFinished(const QString &status);
    void frameMetricsChanged();
    void systemAction(const QString &action);
    void notice(const QString &message);
public slots:
    void synchronize();
    void sceneChanged();
private:
    void readInput();
    void requestPolicy();
    void readPolicy();
    void fail(const QString &message);
    void selectInput(bool ui);
    void fenceCapture();
    void readCapture();
    void cancelCapture(const QString &error);
    void finishCapture();
    void readThumbnail();
    void updateFrameSampling();
    void readFrameMetrics();
    void frameSampleFailed();
    QQuickView *m_view;
    ControllerInput *m_input;
    Applications *m_applications;
    QProcess m_router;
    std::unique_ptr<QSocketNotifier> m_notifier;
    QLocalSocket m_policy;
    QTimer m_deadline, m_inputDeadline;
    QByteArray m_response;
    QJsonObject m_state, m_request;
    QJsonObject m_frameMetrics, m_previousFrames;
    QTimer m_frameTimer;
    bool m_frameSampleDue = false;
    qint64 m_frameGame = 0;
    QString m_socketPath;
    int m_control = -1;
    quint64 m_inputSequence = 0;
    quint64 m_modeSequence = 0;
    quint64 m_remoteSequence = 0;
    qint64 m_compositorPid = 0;
    int m_inputMode = -1, m_inputRequested = -1, m_retries = 0;
    int m_inputSlot = -1, m_requestedSlot = -1;
    qint64 m_closePid = 0, m_thumbnailPid = 0;
    QString m_thumbnailId;
    QString m_holdId;
    qint64 m_holdPid = 0;
    quint64 m_thumbnailSurface = 0, m_thumbnailGeneration = 0;
    bool m_thumbnailSynced = false, m_thumbnailFrameReady = false;
    QThread *m_thumbnailThread = nullptr;
    bool m_routerReady = false, m_ready = false, m_failed = false, m_pending = false;
    enum CapturePhase { Idle, Frame, Fence, Permit, Reading, Closing };
    CapturePhase m_capturePhase = Idle;
    quint64 m_sceneEpoch = 0, m_captureEpoch = 0, m_captureId = 0;
    bool m_frameSynced = false;
    QTimer m_captureDeadline;
    QMetaObject::Connection m_syncConnection, m_frameConnection;
    wl_callback *m_fence = nullptr;
    QThread *m_captureThread = nullptr;
    QImage m_captureImage;
    QString m_captureError;
};
