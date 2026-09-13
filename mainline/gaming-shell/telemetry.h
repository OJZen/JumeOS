#pragma once
#include <QObject>
#include <QElapsedTimer>
#include <QTimer>
#include <QVariantList>
#include <atomic>
#include <QVariantMap>

// Process metrics plus optional compositor-provided game buffer submissions.
// Neither counter measures LCD presentation or GPU render time.
class Telemetry final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool active READ active WRITE setActive NOTIFY changed)
    Q_PROPERTY(double cpu READ cpu NOTIFY changed)
    Q_PROPERTY(double memoryMiB READ memoryMiB NOTIFY changed)
    Q_PROPERTY(double submissions READ submissions NOTIFY changed)
    Q_PROPERTY(QVariantList history READ history NOTIFY changed)
    Q_PROPERTY(QString system READ system CONSTANT)
    Q_PROPERTY(QString storage READ storage NOTIFY changed)
    Q_PROPERTY(QVariantMap game READ game NOTIFY changed)
    Q_PROPERTY(QVariantMap stream READ stream NOTIFY changed)
public:
    explicit Telemetry(QString stateDirectory, QObject *parent = nullptr);
    bool active() const { return m_active.load(); }
    void setActive(bool value);
    double cpu() const { return m_cpu; }
    double memoryMiB() const { return m_memoryMiB; }
    double submissions() const { return m_submissions; }
    QVariantList history() const { return m_history; }
    QString system() const;
    QString storage() const { return m_storage; }
    QVariantMap game() const { return m_game; }
    void setGame(const QVariantMap &value) { if (m_game != value) { m_game = value; emit changed(); } }
    QVariantMap stream() const { return m_stream; }
    void setStream(const QVariantMap &value) { if (m_stream != value) { m_stream = value; emit changed(); } }
    void frameSubmitted() { if (m_active.load()) ++m_frames; }
    Q_INVOKABLE void refreshStorage();
signals:
    void changed();
private:
    void sample();
    QString m_directory, m_storage;
    QTimer m_timer;
    QElapsedTimer m_clock;
    std::atomic<bool> m_active{false};
    std::atomic<unsigned> m_frames{0};
    double m_cpu = -1, m_memoryMiB = -1, m_submissions = -1, m_previousCpu = -1;
    QVariantList m_history;
    QVariantMap m_game;
    QVariantMap m_stream;
};
