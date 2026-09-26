#pragma once
#include <QObject>
#include <QProcess>
#include <QTimer>
#include <QVariantList>
#include <QElapsedTimer>
#include <QImage>
#include <QHash>

// Local manifest and compiled-in foreground adapters. No command arrives over IPC.
class Applications final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariantList items READ items CONSTANT)
    Q_PROPERTY(bool hasManifest READ hasManifest CONSTANT)
    Q_PROPERTY(bool running READ running NOTIFY changed)
    Q_PROPERTY(QString activeId READ activeId NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(int exitCode READ exitCode NOTIFY changed)
    Q_PROPERTY(QVariantList tasks READ tasks NOTIFY changed)
    Q_PROPERTY(bool hasTasks READ hasTasks NOTIFY changed)
public:
    explicit Applications(QObject *parent = nullptr);
    ~Applications() override;
    bool load(const QString &path);
    QVariantList items() const { return m_items; }
    bool hasManifest() const { return m_hasManifest; }
    bool running() const { return m_active != nullptr; }
    bool hasTasks() const { return !m_tasks.isEmpty(); }
    QString activeId() const;
    QString error() const { return m_error; }
    int exitCode() const { return m_exitCode; }
    qint64 processId() const;
    int inputSlot() const;
    QVariantList tasks() const;
    QImage thumbnail(const QString &id) const;
    void setThumbnail(const QString &id, qint64 pid, const QImage &image);
    void setRoutedInput(bool enabled) { m_routedInput = enabled; }
    // Compiled-in adapters only; requests over QML/IPC never supply commands.
    bool launchPrepared(const QString &id, const QString &program, const QStringList &arguments,
                        const QString &directory, QProcessEnvironment environment, bool captureOutput = false);
    Q_INVOKABLE bool launch(int index);
    Q_INVOKABLE void stop();
    Q_INVOKABLE void stopAll();
    Q_INVOKABLE bool activate(const QString &id);
    Q_INVOKABLE void background();
    Q_INVOKABLE void forceKill(const QString &id = QString());
    Q_INVOKABLE void requestClose(const QString &id = QString());
    bool contains(const QString &id) const;
signals:
    void browserRequested();
    void terminalRequested();
    void filesRequested(bool editor);
    void transferRequested();
    void changed();
    void started();
    void finished();
    void outputReady(const QByteArray &data);
    void taskFinished(const QString &id, int code, bool failed);
    void closeRequested(qint64 pid);
    void notice(const QString &message);
    void backgroundRequested(bool tasks);
private:
    struct Entry { QString id, program, directory; QStringList arguments; };
    bool fail(const QString &message);
    struct Task;
    void signalGroup(Task *task, int signal);
    void suspend(Task *task, bool paused);
    void complete(Task *task);
    void advanceStop();
    QList<Entry> m_entries;
    QVariantList m_items;
    QList<Task *> m_tasks;
    Task *m_active = nullptr;
    QTimer m_stopTimer;
    QString m_error;
    int m_exitCode = 0;
    bool m_routedInput = false;
    bool m_hasManifest = false;
};
