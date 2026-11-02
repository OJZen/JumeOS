#pragma once
#include "../gaming-wayland/stick-calibration.h"
#include <QObject>
#include <QTimer>
#include <QVariantList>
#include <QList>

class StickCalibration final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool available READ available NOTIFY changed)
    Q_PROPERTY(bool active READ active NOTIFY changed)
    Q_PROPERTY(bool configured READ configured NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(int phase READ phase NOTIFY changed)
    Q_PROPERTY(bool canAdvance READ canAdvance NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(QVariantList rawAxes READ rawAxes NOTIFY changed)
    Q_PROPERTY(QVariantList previewAxes READ previewAxes NOTIFY changed)
    Q_PROPERTY(QVariantList ranges READ ranges NOTIFY changed)
public:
    explicit StickCalibration(QObject *parent = nullptr);
    void load(const QString &stateDirectory);
    void setAvailable(bool value);
    void observe(const qint32 axes[4]);
    void applied(bool accepted);
    bool needsApply() const { return m_needsApply; }
    const Stick::Profile &profile() const { return m_saved; }
    bool available() const { return m_available; }
    bool active() const { return m_phase != 0; }
    bool configured() const { return m_configured; }
    bool busy() const { return m_busy; }
    int phase() const { return m_phase; }
    bool canAdvance() const;
    QString error() const { return m_error; }
    QVariantList rawAxes() const;
    QVariantList previewAxes() const;
    QVariantList ranges() const;
    Q_INVOKABLE bool begin();
    Q_INVOKABLE void cancel();
    Q_INVOKABLE bool advance();
    Q_INVOKABLE bool confirmReset();
    void sampleCenter();
signals:
    void changed();
    void configurationRequested();
    void notice(const QString &text);
private:
    bool save(bool enabled, const Stick::Profile &profile);
    void setError(const QString &text);
    QString m_path, m_error;
    Stick::Profile m_saved{}, m_draft{};
    std::array<qint32, 4> m_raw{};
    QList<std::array<qint32, 4>> m_centers;
    QTimer m_timer;
    bool m_available = false, m_configured = false, m_busy = false, m_needsApply = true;
    int m_phase = 0; // Idle, center, travel, review, reset confirmation.
};
