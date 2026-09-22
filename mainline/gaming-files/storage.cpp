#include "storage.h"
#include <QDBusMetaType>
#include <QDBusArgument>
#include <QDBusPendingCallWatcher>
#include <QDBusPendingReply>
#include <QDir>

namespace {
const QString service = "org.freedesktop.UDisks2", base = "/org/freedesktop/UDisks2";
const QString block = service + ".Block", drive = service + ".Drive", filesystem = service + ".Filesystem";
} // namespace
Storage::Storage(QDBusConnection connection, QObject *parent)
    : QObject(parent),
      bus(connection.isConnected()
              ? connection
              : QDBusConnection::connectToBus("unix:path=/run/dbus/system_bus_socket", "jume-files-storage")) {
    qDBusRegisterMetaType<DiskInterfaces>();
    qDBusRegisterMetaType<DiskObjects>();
    qDBusRegisterMetaType<QList<QByteArray>>();
    connect(&timer, &QTimer::timeout, this, &Storage::refresh);
    timer.start(3000);
    refresh();
}
QVariantList Storage::usbDevices(const DiskObjects &objects) {
    QVariantList result;
    for (auto i = objects.begin(); i != objects.end(); ++i) {
        if (!i.key().path().startsWith(base + "/block_devices/") || !i.value().contains(filesystem))
            continue;
        const auto b = i.value().value(block);
        const auto drivePath = qvariant_cast<QDBusObjectPath>(b.value("Drive"));
        const auto d = objects.value(drivePath).value(drive);
        // Only USB removable filesystems. Internal/system/fstab and encrypted/RAID
        // stacks are not offered as mount targets by this UI or the polkit rule.
        if (d.value("ConnectionBus").toString() != "usb" || !d.value("Removable").toBool() ||
            b.value("HintSystem", true).toBool() || b.value("HintIgnore", true).toBool() ||
            b.value("IdUsage").toString() != "filesystem")
            continue;
        if (!b.contains("Configuration"))
            continue;
        const auto configuration = b.value("Configuration");
        if (configuration.metaType() == QMetaType::fromType<QDBusArgument>()) {
            const auto array = configuration.value<QDBusArgument>();
            array.beginArray();
            const bool empty = array.atEnd();
            array.endArray();
            if (!empty)
                continue;
        } else if (!configuration.toList().isEmpty())
            continue; // Never invoke fstab-specific mounting.
        const auto device = b.value("Device").toByteArray();
        if (!device.startsWith("/dev/") || device.startsWith("/dev/mmc"))
            continue;
        const auto mounts = qdbus_cast<QList<QByteArray>>(i.value().value(filesystem).value("MountPoints"));
        QString mounted;
        if (!mounts.isEmpty())
            mounted = QString::fromUtf8(mounts.first().constData());
        if (!mounted.isEmpty() && !QDir::isAbsolutePath(mounted))
            continue;
        result.append(QVariantMap{{"id", i.key().path()},
                                  {"drive", drivePath.path()},
                                  {"device", device},
                                  {"uuid", b.value("IdUUID")},
                                  {"size", b.value("Size")},
                                  {"label", b.value("IdLabel")},
                                  {"detected", d.value("TimeDetected")},
                                  {"type", b.value("IdType")},
                                  {"mount", mounted},
                                  {"readOnly", b.value("ReadOnly")}});
    }
    return result;
}
void Storage::fetch(std::function<void(const DiskObjects &)> done) {
    auto message =
        QDBusMessage::createMethodCall(service, base, "org.freedesktop.DBus.ObjectManager", "GetManagedObjects");
    auto *watcher = new QDBusPendingCallWatcher(bus.asyncCall(message, 5000), this);
    connect(watcher, &QDBusPendingCallWatcher::finished, this, [this, watcher, done] {
        QDBusPendingReply<DiskObjects> reply = *watcher;
        watcher->deleteLater();
        if (reply.isError()) {
            error = "UDisks2 不可用或请求失败：" + reply.error().message();
            busy = false;
            devices.clear();
            emit changed();
            return;
        }
        done(reply.value());
    });
}
void Storage::refresh() {
    if (busy)
        return;
    busy = true;
    fetch([this](const DiskObjects &objects) {
        devices = usbDevices(objects);
        busy = false;
        error.clear();
        emit changed();
    });
}
void Storage::mount(const QVariantMap &expected, bool unmount) {
    if (busy)
        return;
    busy = true;
    error.clear();
    emit changed();
    fetch([this, expected, unmount](const DiskObjects &objects) {
        QVariantMap current;
        for (const auto &v : usbDevices(objects))
            if (v.toMap().value("id") == expected.value("id"))
                current = v.toMap();
        for (const auto *key : {"id", "drive", "device", "uuid", "size", "type", "mount", "detected"}) {
            if (current.isEmpty() || current.value(key) != expected.value(key)) {
                error = "设备身份/挂载状态已变化，请刷新后重试。";
                busy = false;
                emit changed();
                return;
            }
        }
        if (unmount == current.value("mount").toString().isEmpty()) {
            error = "设备挂载状态不符合请求。";
            busy = false;
            emit changed();
            return;
        }
        auto request = QDBusMessage::createMethodCall(service, current.value("id").toString(), filesystem,
                                                      unmount ? "Unmount" : "Mount");
        QVariantMap options{{"auth.no_user_interaction", true}};
        if (!unmount)
            options["options"] = "nosuid,nodev,noexec";
        request << options;
        auto *watcher = new QDBusPendingCallWatcher(bus.asyncCall(request, 30000), this);
        connect(watcher, &QDBusPendingCallWatcher::finished, this, [this, watcher, unmount] {
            const QDBusMessage reply = watcher->reply();
            watcher->deleteLater();
            busy = false;
            if (reply.type() == QDBusMessage::ErrorMessage)
                error = "存储请求失败/超时；请刷新确认状态：" + reply.errorMessage();
            else if (!unmount && !reply.arguments().isEmpty()) {
                const auto path = reply.arguments().first().toString();
                if (QDir::isAbsolutePath(path) && QDir(path).exists())
                    emit mounted(path);
            }
            emit changed(); // Show the error before the next periodic refresh.
        });
    });
}
