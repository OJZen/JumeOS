#pragma once
#include <QObject>
#include <QJsonObject>
#include <QNetworkAccessManager>
#include <QPointer>
#include <QProcess>
#include <QTimer>
#include <QVariantList>
class QNetworkReply;

class Streaming final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariantList hosts READ hosts NOTIFY changed)
    Q_PROPERTY(int selected READ selected NOTIFY changed)
    Q_PROPERTY(QVariantMap current READ current NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(QString status READ status NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(QString pin READ pin NOTIFY changed)
    Q_PROPERTY(bool clientReady READ clientReady NOTIFY changed)
    Q_PROPERTY(QStringList applications READ applications NOTIFY changed)
public:
    explicit Streaming(QString stateDirectory, QObject *parent = nullptr);
    ~Streaming() override;
    void configureClient(QString path, QString hash);
    QVariantList hosts() const;
    QVariantMap current() const;
    int selected() const { return m_selected; }
    QString error() const { return m_error; }
    QString status() const { return m_status; }
    bool busy() const { return m_pair.state() != QProcess::NotRunning || m_apps.state() != QProcess::NotRunning; }
    QString pin() const { return m_pin; }
    bool clientReady() const { return !m_client.isEmpty(); }
    QStringList applications() const { return m_applicationNames; }
    static QString validAddress(const QString &address);
    static QStringList streamArguments(const QJsonObject &host);
    Q_INVOKABLE bool addHost(const QString &address);
    Q_INVOKABLE bool edit(const QString &key, const QString &value);
    Q_INVOKABLE bool removeSelected();
    Q_INVOKABLE void select(int index);
    Q_INVOKABLE bool adjustPreset(int direction);
    Q_INVOKABLE void toggleOverlay();
    Q_INVOKABLE void refresh();
    Q_INVOKABLE void pair();
    Q_INVOKABLE void cancelPair();
    Q_INVOKABLE void refreshApplications();
    Q_INVOKABLE bool chooseApplication(int index);
    static bool parseApplications(const QByteArray &output, QStringList *names);
    Q_INVOKABLE bool requestStream();
    int runPending(int timeoutSeconds);
    void streamFinished(int exitCode);
    QVariantMap statistics() const { return m_statistics; }
    void setStatisticsActive(bool active);
    void ingestStatistics(const QByteArray &data);
signals:
    void changed();
    void launchRequested();
    void applicationsReady();
    void statisticsChanged();
private:
    bool save();
    bool fail(const QString &message);
    bool checkClient();
    QProcessEnvironment clientEnvironment(bool pairing) const;
    bool writeJson(const QString &name, const QJsonObject &data);
    QString m_directory, m_client, m_hash, m_error, m_status, m_pin, m_pairId;
    QList<QJsonObject> m_hosts;
    QHash<QString, QString> m_online;
    int m_selected = 0;
    bool m_loadFailed = false, m_pairCancelled = false, m_pairTimedOut = false;
    QNetworkAccessManager m_network;
    QPointer<QNetworkReply> m_reply;
    QProcess m_pair;
    QTimer m_pairTimer;
    QProcess m_apps;
    QTimer m_appsTimer;
    QByteArray m_appsOutput;
    QStringList m_applicationNames;
    bool m_appsCancelled = false, m_appsTimedOut = false, m_appsOverflow = false;
    QVariantMap m_statistics{{"active", false}, {"available", false}};
    QByteArray m_statisticsPending;
    QTimer m_statisticsExpiry;
};
