#pragma once
#include <QObject>
#include <QVariantList>

// Preview state only. No device or host settings are read or changed.
class Preferences final : public QObject {
    Q_OBJECT
    Q_PROPERTY(int volume READ volume NOTIFY changed)
    Q_PROPERTY(int brightness READ brightness NOTIFY changed)
    Q_PROPERTY(bool reducedMotion READ reducedMotion NOTIFY changed)
    Q_PROPERTY(bool monitor READ monitor NOTIFY changed)
    Q_PROPERTY(int fontPercent READ fontPercent NOTIFY changed)
    Q_PROPERTY(int dimSeconds READ dimSeconds NOTIFY changed)
    Q_PROPERTY(QVariantList favorites READ favorites NOTIFY changed)
    Q_PROPERTY(QVariantList applicationFavorites READ applicationFavorites NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY errorChanged)
    Q_PROPERTY(bool dirty READ dirty NOTIFY changed)
public:
    explicit Preferences(QString directory, QObject *parent = nullptr);
    int volume() const { return m_volume; }
    int brightness() const { return m_brightness; }
    bool reducedMotion() const { return m_reducedMotion; }
    bool monitor() const { return m_monitor; }
    int fontPercent() const { return m_fontPercent; }
    int dimSeconds() const { return m_dimSeconds; }
    QVariantList favorites() const { return m_favorites; }
    QVariantList applicationFavorites() const { return m_applicationFavorites; }
    QString error() const { return m_error; }
    bool dirty() const { return m_dirty; }
    Q_INVOKABLE void adjust(const QString &name, int step);
    Q_INVOKABLE bool choose(const QString &name, int index);
    Q_INVOKABLE void toggleFavorite(int index);
    Q_INVOKABLE bool toggleApplicationFavorite(const QString &id);
    Q_INVOKABLE bool save();
    Q_INVOKABLE bool isFavorite(int index) const;
signals:
    void changed();
    void errorChanged();
private:
    void setError(const QString &message);
    QString m_directory, m_error;
    int m_volume = 55, m_brightness = 70;
    int m_fontPercent = 100, m_dimSeconds = 0;
    bool m_monitor = false;
    bool m_reducedMotion = false, m_dirty = false, m_loadFailed = false;
    QVariantList m_favorites;
    QVariantList m_applicationFavorites;
};
