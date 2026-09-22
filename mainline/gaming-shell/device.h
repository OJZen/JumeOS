#pragma once
#include <QObject>
#include <QVariantMap>
#include <QTimer>
#include <QElapsedTimer>
#include <QStorageInfo>
#include <QFileSystemWatcher>

// Linux device adapter. Writes require both the fixed R46H identity and a probe lease.
// The fixture root is constructor-only: the application exposes no arbitrary sysfs path.
class DeviceState final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool target READ target CONSTANT)
    Q_PROPERTY(bool controls READ controls NOTIFY changed)
    Q_PROPERTY(QVariantMap info READ info NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(QVariantList storage READ storage NOTIFY changed)
public:
    explicit DeviceState(QString root = "/", bool allowControls = false, bool fixture = false);
    ~DeviceState() override;
    bool target() const { return m_target; }
    bool controls() const { return m_target && m_controls; }
    QVariantMap info() const { return m_info; }
    QString error() const { return m_error; }
    QVariantList storage() const { return m_storage; }
    QVariantMap diagnostics() const;
    Q_INVOKABLE void refresh();
    Q_INVOKABLE void refreshStorage();
    Q_INVOKABLE bool setBrightness(int percent);
    Q_INVOKABLE bool setDimmed(bool dimmed);
    Q_INVOKABLE bool applyCpu(QString governor, int minimum, int maximum);
    Q_INVOKABLE bool cpuPreset(const QString &name);
    Q_INVOKABLE bool requestPower(const QString &action);
    static QVariantMap snapshot(const QString &root);
    static QVariantMap storageInfo(const QString &label, const QStorageInfo &info, const QString &expectedMount);
signals:
    void changed();
    void warning(const QString &message);
    void powerRequested(int exitCode);
    void volumeChanged(int percent);
private:
    void watchVolume();
    void volumeFileChanged(const QString &name);
    QString path(const QString &relative) const;
    bool fail(const QString &text);
    bool writeValue(const QString &relative, const QString &value);
    bool writeCpu(const QVariantMap &policy, const QString &governor, int minimum, int maximum);
    QString m_root, m_error;
    QVariantMap m_info, m_originalCpu;
    QVariantList m_storage;
    QElapsedTimer m_sampleClock;
    QTimer m_timer;
    QFileSystemWatcher m_volumeWatcher;
    bool m_target = false, m_controls = false, m_warned = false;
    int m_beforeDim = -1;
    qulonglong m_ticks = 0, m_idle = 0;
};
