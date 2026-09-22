#pragma once
#include <QObject>
#include <QDBusConnection>
#include <QDBusObjectPath>
#include <QMap>
#include <QVariantMap>
#include <QTimer>
#include <functional>

using DiskInterfaces = QMap<QString, QVariantMap>;
using DiskObjects = QMap<QDBusObjectPath, DiskInterfaces>;
Q_DECLARE_METATYPE(DiskInterfaces)
Q_DECLARE_METATYPE(DiskObjects)

class Storage final : public QObject {
    Q_OBJECT
  public:
    explicit Storage(QDBusConnection connection = QDBusConnection(QString()), QObject *parent = nullptr);
    QVariantList devices;
    bool busy = false;
    QString error;
    static QVariantList usbDevices(const DiskObjects &objects);
    void refresh();
    void mount(const QVariantMap &expected, bool unmount);
  signals:
    void changed();
    void mounted(const QString &path);

  private:
    void fetch(std::function<void(const DiskObjects &)> done);
    QDBusConnection bus;
    QTimer timer;
};
