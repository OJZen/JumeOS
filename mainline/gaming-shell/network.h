#pragma once
#include <QObject>
#include <QProcess>
#include <QTimer>
#include <QVariantList>
#include <QMap>
#include <QDBusConnection>
#include <QDBusMessage>
#include <functional>

using NetworkSettings = QMap<QString, QVariantMap>;
Q_DECLARE_METATYPE(NetworkSettings)

// Reads use nmcli; new Wi-Fi secrets travel only over the local NetworkManager bus.
class NetworkState final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool available READ available CONSTANT)
    Q_PROPERTY(bool controls READ controls CONSTANT)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(QVariantList profiles READ profiles NOTIFY changed)
    Q_PROPERTY(int signal READ signal NOTIFY changed)
    Q_PROPERTY(QString status READ status NOTIFY changed)
    Q_PROPERTY(QVariantList accessPoints READ accessPoints NOTIFY changed)
    Q_PROPERTY(QVariantMap selectedNetwork READ selectedNetwork NOTIFY changed)
    Q_PROPERTY(bool remember READ remember WRITE setRemember NOTIFY changed)
public:
    NetworkState(bool available, bool controls, QString program="/usr/bin/nmcli",
                 QDBusConnection bus=QDBusConnection(QString()));
    ~NetworkState() override;
    bool available() const { return m_available; }
    bool controls() const { return m_controls; }
    bool busy() const { return m_connecting || m_process.state()!=QProcess::NotRunning; }
    QVariantList profiles() const { return m_profiles; }
    int signal() const { return m_signal; }
    QString status() const { return m_status; }
    QVariantList accessPoints() const { return m_accessPoints; }
    QVariantMap selectedNetwork() const { return m_selectedNetwork; }
    bool remember() const { return m_remember; }
    void setRemember(bool remember);
    Q_INVOKABLE bool refresh();
    Q_INVOKABLE bool activate(const QString &uuid);
    Q_INVOKABLE bool disconnect();
    Q_INVOKABLE bool scan();
    Q_INVOKABLE bool selectAccessPoint(int index);
    Q_INVOKABLE bool connectSelected(const QString &password);
    Q_INVOKABLE bool forget(const QString &uuid);
    static bool parse(const QByteArray &data,QVariantList *profiles);
    static int parseSignal(const QByteArray &data);
    static bool parseAccessPoints(const QByteArray &data,QVariantList *accessPoints);
    static bool validPassword(const QString &password);
signals:
    void changed();
    void notice(const QString &text);
    void scanReady();
private slots:
    void activeStateChanged(uint state, uint reason, const QDBusMessage &message);
private:
    bool start(const QString &operation,const QStringList &arguments);
    void finish(int code,QProcess::ExitStatus status);
    bool fail(const QString &text);
    void busCall(const QString &path, const QString &interface, const QString &method,
                 const QVariantList &arguments, std::function<void(const QList<QVariant> &)> done);
    void finishConnection(const QString &message, bool connected=false);
    void handleActiveState(uint state);
    void clearPassword();
    bool refreshSignal();
    bool m_available, m_controls, m_timeout=false, m_overflow=false;
    QString m_program,m_operation,m_status;
    QByteArray m_output;
    QProcess m_process;
    QTimer m_timer;
    QVariantList m_profiles;
    QVariantList m_accessPoints;
    QVariantMap m_selectedNetwork;
    QDBusConnection m_bus;
    QTimer m_connectionTimer;
    QTimer m_signalTimer;
    QByteArray m_password;
    QString m_activePath;
    bool m_connecting=false, m_remember=false;
    int m_signal=-1;
    quint64 m_connectionGeneration=0;
};
