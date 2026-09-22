#pragma once
#include <QObject>
#include <QProcess>
#include <QTimer>
#include <QVariantList>
#include <QElapsedTimer>

// Local manifest and compiled-in foreground adapters. No command arrives over IPC.
class Applications final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariantList items READ items CONSTANT)
    Q_PROPERTY(bool hasManifest READ hasManifest CONSTANT)
    Q_PROPERTY(bool running READ running NOTIFY changed)
    Q_PROPERTY(QString activeId READ activeId NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(int exitCode READ exitCode NOTIFY changed)
public:
    explicit Applications(QObject *parent = nullptr);
    ~Applications() override;
    bool load(const QString &path);
    QVariantList items() const { return m_items; }
    bool hasManifest() const { return m_hasManifest; }
    bool running() const { return m_process.state() != QProcess::NotRunning || m_group != 0; }
    QString activeId() const { return m_activeId; }
    QString error() const { return m_error; }
    int exitCode() const { return m_exitCode; }
    qint64 processId() const { return m_process.processId(); }
    void setRoutedInput(bool enabled) { m_routedInput = enabled; }
    // Compiled-in adapters only; requests over QML/IPC never supply commands.
    bool launchPrepared(const QString &id, const QString &program, const QStringList &arguments,
                        const QString &directory, QProcessEnvironment environment, bool captureOutput = false);
    Q_INVOKABLE bool launch(int index);
    Q_INVOKABLE void stop();
signals:
    void browserRequested();
    void terminalRequested();
    void filesRequested(bool editor);
    void transferRequested();
    void changed();
    void started();
    void finished();
    void outputReady(const QByteArray &data);
private:
    struct Entry { QString id, program, directory; QStringList arguments; };
    bool fail(const QString &message);
    void signalGroup(int signal);
    void advanceStop();
    QList<Entry> m_entries;
    QVariantList m_items;
    QProcess m_process;
    QTimer m_stopTimer;
    QElapsedTimer m_stopClock;
    qint64 m_group = 0;
    bool m_finishPending = false;
    QString m_activeId, m_error;
    int m_exitCode = 0;
    bool m_stopping = false;
    bool m_routedInput = false;
    bool m_hasManifest = false;
};
