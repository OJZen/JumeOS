#pragma once
#include <QObject>
#include <QProcess>
#include <QTimer>
#include <QVariantList>
#include <QVariantMap>
#include <QHash>

class ToolState final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariantMap info READ info NOTIFY changed)
    Q_PROPERTY(QVariantMap settings READ settings NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(bool dirty READ dirty NOTIFY changed)
    Q_PROPERTY(bool nativeEnabled READ nativeEnabled CONSTANT)
    Q_PROPERTY(bool portsEnabled READ portsEnabled CONSTANT)
    Q_PROPERTY(QString lastGame READ lastGame NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(bool catalogAvailable READ catalogAvailable NOTIFY changed)
    Q_PROPERTY(QVariantMap catalogInfo READ catalogInfo NOTIFY changed)
    Q_PROPERTY(QVariantMap catalogDetail READ catalogDetail NOTIFY changed)
    Q_PROPERTY(double progress READ progress NOTIFY changed)
    Q_PROPERTY(bool cancellable READ cancellable NOTIFY changed)
public:
    explicit ToolState(QString stateDirectory, QString contentRoot, bool target, bool nativeEnabled = false, QObject *parent = nullptr);
    ~ToolState() override;
    QVariantMap info() const { return m_info; }
    QVariantMap settings() const { return m_settings; }
    bool busy() const { return m_process.state() != QProcess::NotRunning; }
    bool dirty() const { return m_dirty; }
    bool nativeEnabled() const { return m_target && m_nativeEnabled; }
    bool portsEnabled() const { return nativeEnabled() && !m_stateDirectory.startsWith("/run/") &&
        (qEnvironmentVariableIsEmpty("WAYLAND_DISPLAY") || qEnvironmentVariable("R46H_SHARED_PORTS") == "1"); }
    QString lastGame() const { return m_lastGame; }
    QString error() const { return m_error; }
    bool catalogAvailable() const { return !m_backendScript.isEmpty(); }
    QVariantMap catalogInfo() const { return m_catalogInfo; }
    QVariantMap catalogDetail() const { return m_catalogDetail; }
    double progress() const { return m_progress; }
    bool cancellable() const { return busy() && m_backend; }
    void configureCatalog(const QString &script, const QString &runtime);
    Q_INVOKABLE bool catalog(const QString &query = {}, int offset = 0, bool installed = false);
    Q_INVOKABLE bool catalogAction(const QString &action, const QString &id = {});
    Q_INVOKABLE void cancel();
    Q_INVOKABLE bool choose(const QString &key, const QVariant &value);
    Q_INVOKABLE bool save();
    Q_INVOKABLE bool inspect(const QString &kind);
    Q_INVOKABLE bool action(const QString &operation, const QString &id);
    Q_INVOKABLE bool requestNative();
    Q_INVOKABLE bool requestPort(const QString &id);
    static QVariantMap defaults();
    static bool validSettings(const QVariantMap &settings);
    static QVariantMap scan(const QString &contentRoot, const QString &stateDirectory, const QString &kind, bool verify);
    static int worker(const QString &operation, const QString &id, const QString &contentRoot, const QString &stateDirectory);
    static int runNative(const QString &stateDirectory, int timeoutSeconds, bool sharedDisplay = false);
    static QByteArray neoConfiguration(const QVariantMap &settings, const QString &gameDirectory, bool sharedDisplay);
    void nativeFinished(const QString &game, int exitCode);
signals:
    void changed();
    void notice(const QString &message);
    void nativeRequested(const QString &game);
    void catalogFinished(const QString &operation);
private:
    bool start(const QString &operation, const QString &id);
    bool fail(const QString &message);
    bool startCatalog(const QString &action, const QStringList &arguments);
    void readOutput();
    QString m_stateDirectory, m_contentRoot, m_error, m_operation, m_id;
    QString m_kind, m_pendingKind, m_resultMessage, m_lastGame;
    QHash<QString, QVariantMap> m_cache;
    QVariantMap m_settings, m_info;
    QProcess m_process;
    QTimer m_deadline;
    QTimer m_cancelDeadline;
    QByteArray m_output;
    QString m_backendScript, m_backendRuntime;
    QVariantMap m_catalogInfo, m_catalogDetail, m_backendResult;
    double m_progress = -1;
    bool m_backend = false;
    bool m_target, m_nativeEnabled, m_dirty = false, m_loadFailed = false, m_timedOut = false;
};
