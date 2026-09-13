#include "network.h"
#include <QDBusArgument>
#include <QDBusObjectPath>
#include <QDBusVariant>
#include <QDBusVirtualObject>
#include <QFile>
#include <QStandardPaths>
#include <QTemporaryDir>
#include <QtTest>

namespace {
const QString service="org.freedesktop.NetworkManager";
const QString manager="/org/freedesktop/NetworkManager";
const QString apPath=manager+"/AccessPoint/1";
const QString activePath=manager+"/ActiveConnection/1";
const QByteArray scanLine="/org/freedesktop/NetworkManager/AccessPoint/1:AA\\:BB\\:CC\\:DD\\:EE\\:FF:Studio\\:5G:80:WPA2:wlan0:*\n";

class FakeNetwork final : public QDBusVirtualObject {
public:
    QString mode="success";
    uint state=1;
    int additions=0;
    NetworkSettings settings;
    QVariantMap options;
    QString introspect(const QString &) const override { return {}; }
    bool handleMessage(const QDBusMessage &message,const QDBusConnection &bus) override {
        if(message.member()=="GetAll"&&message.path()==apPath){
            const QVariantMap ap{{"Mode",uint(2)},{"Flags",uint(mode=="open"?0:1)},{"WpaFlags",uint(0)},{"RsnFlags",uint(mode=="open"?0:0x100)},
                {"Ssid",mode=="changed"?QByteArray("Changed"):QByteArray("Studio:5G")},{"HwAddress","AA:BB:CC:DD:EE:FF"}};
            return bus.send(message.createReply(QList<QVariant>{ap}));
        }
        if(message.member()=="GetDeviceByIpIface")
            return bus.send(message.createReply({QVariant::fromValue(QDBusObjectPath(manager+"/Devices/1"))}));
        if(message.member()=="AddAndActivateConnection2"){
            ++additions;settings=qdbus_cast<NetworkSettings>(message.arguments()[0]);options=qdbus_cast<QVariantMap>(message.arguments()[3]);
            if(mode=="denied")return bus.send(message.createErrorReply(service+".PermissionDenied","fixture denial"));
            state=mode=="failed"?4:mode=="pending"?1:2;
            return bus.send(message.createReply({QVariant::fromValue(QDBusObjectPath(manager+"/Settings/1")),
                QVariant::fromValue(QDBusObjectPath(activePath)),QVariantMap()}));
        }
        if(message.member()=="Get"&&message.path()==activePath)
            return bus.send(message.createReply({QVariant::fromValue(QDBusVariant(state))}));
        return bus.send(message.createErrorReply("org.freedesktop.DBus.Error.UnknownMethod","fixture method"));
    }
};
}

class NetworkCheck final : public QObject {
    Q_OBJECT
private slots:
    void scanAndPasswordContracts() {
        QCOMPARE(NetworkState::parseSignal(" :89\n*:61\n :42\n"),61);
        QCOMPARE(NetworkState::parseSignal(" :89\n :42\n"),-1);
        QCOMPARE(NetworkState::parseSignal("*:101\n"),-1);
        QCOMPARE(NetworkState::parseSignal("*:61\n*:42\n"),-1);
        QVariantList aps;
        QVERIFY(NetworkState::parseAccessPoints(scanLine,&aps));QCOMPARE(aps.size(),1);
        QCOMPARE(aps[0].toMap().value("ssid").toString(),QString("Studio:5G"));
        QCOMPARE(aps[0].toMap().value("bssid").toString(),QString("AA:BB:CC:DD:EE:FF"));
        const auto weaker=QByteArray(scanLine).replace("AccessPoint/1","AccessPoint/2").replace(":80:",":40:");
        QVERIFY(NetworkState::parseAccessPoints(weaker+scanLine,&aps));QCOMPARE(aps.size(),1);
        QCOMPARE(aps[0].toMap().value("signal").toInt(),80);
        for(const auto &bad:{scanLine+scanLine,QByteArray(scanLine).replace(":80:",":101:"),QByteArray(scanLine).replace("Studio", "bad\r"),QByteArray("\xff")})
            QVERIFY(!NetworkState::parseAccessPoints(bad,&aps));
        for(const auto &valid:{QString("test1234"),QString(64,'A'),QString("abc defgh")})QVERIFY(NetworkState::validPassword(valid));
        for(const auto &bad:{QString("short"),QString(65,'A'),QString(64,'Z'),QString("test1234\n"),QStringLiteral("测试密码12345678")})QVERIFY(!NetworkState::validPassword(bad));
    }
    void privateBusConnectionLifecycle() {
        const auto daemon=QStandardPaths::findExecutable("dbus-daemon");
        if(daemon.isEmpty())QSKIP("No local bus daemon; the ARM64 builder runs this isolated bus check");
        QTemporaryDir files;QVERIFY(files.isValid());
        QTemporaryDir sockets("/run/r46h-network-check.XXXXXX");
        if(!sockets.isValid())QSKIP("Requires the isolated Linux builder's /run socket filesystem");
        QProcess bus;
        bus.start(daemon,{"--session","--nofork","--print-address=1","--address=unix:path="+sockets.filePath("bus")});
        QVERIFY(bus.waitForStarted());QVERIFY(bus.waitForReadyRead());const auto address=QString::fromUtf8(bus.readLine()).trimmed();
        auto server=QDBusConnection::connectToBus(address,"network-check-server");
        auto client=QDBusConnection::connectToBus(address,"network-check-client");
        QVERIFY(server.isConnected()&&client.isConnected());QVERIFY(server.registerService(service));
        FakeNetwork fixture;QVERIFY(server.registerVirtualObject(manager,&fixture,QDBusConnection::SubPath));
        QFile program(files.filePath("nmcli"));QVERIFY(program.open(QIODevice::WriteOnly));
        program.write("#!/bin/sh\ncase \"$*\" in *\"device wifi list\"*) cat \"$0.scan\";; *) printf '%s\\n' '11111111-2222-4333-8444-555555555555:wifi:Saved:wlan0';; esac\n");program.close();
        QVERIFY(program.setPermissions(QFile::ReadOwner|QFile::WriteOwner|QFile::ExeOwner));
        QFile scan(program.fileName()+".scan");QVERIFY(scan.open(QIODevice::WriteOnly));scan.write(scanLine);scan.close();
        {
            NetworkState network(true,true,program.fileName(),client);QTRY_VERIFY(!network.busy());
            QVERIFY(network.scan());QTRY_VERIFY(!network.busy());QVERIFY(network.selectAccessPoint(0));
            QVERIFY(!network.connectSelected("bad\npassword"));QCOMPARE(fixture.additions,0);
            QSignalSpy notices(&network,&NetworkState::notice);
            QVERIFY(network.connectSelected("fixture-password"));QTRY_VERIFY(!network.busy());QCOMPARE(fixture.additions,1);
            QVERIFY(notices.last()[0].toString().contains(QStringLiteral("已连接")));
            // Only this local fixture receives the secret; no argv or file carries it.
            QVERIFY(fixture.settings["802-11-wireless-security"]["psk"]==QString("fixture-password"));
            QCOMPARE(fixture.settings["802-11-wireless"]["ssid"].toByteArray(),QByteArray("Studio:5G"));
            QCOMPARE(fixture.options.value("persist").toString(),QString("volatile"));
            QVERIFY(!fixture.settings["connection"]["autoconnect"].toBool());
            network.setRemember(true);fixture.mode="failed";
            QVERIFY(network.connectSelected("fixture-password"));QTRY_VERIFY(!network.busy());
            QCOMPARE(fixture.options.value("persist").toString(),QString("disk"));
            QVERIFY(!notices.last()[0].toString().contains(QStringLiteral("已连接")));
            fixture.mode="denied";QVERIFY(network.connectSelected("fixture-password"));QTRY_VERIFY(!network.busy());
            QVERIFY(notices.last()[0].toString().contains(QStringLiteral("拒绝")));
            const int previous=fixture.additions;fixture.mode="changed";
            QVERIFY(network.connectSelected("fixture-password"));QTRY_VERIFY(!network.busy());QCOMPARE(fixture.additions,previous);
            QVERIFY(notices.last()[0].toString().contains(QStringLiteral("变化")));
            fixture.mode="pending";QVERIFY(network.connectSelected("fixture-password"));
            QTRY_COMPARE(fixture.additions,previous+1);QTest::qWait(100);QVERIFY(network.busy());
            auto signal=QDBusMessage::createSignal(activePath,service+".Connection.Active","StateChanged");signal.setArguments({uint(2),uint(0)});
            QVERIFY(server.send(signal));QTRY_VERIFY(!network.busy());
            QVERIFY(notices.last()[0].toString().contains(QStringLiteral("已连接")));
            auto *deadline=network.findChild<QTimer *>("networkConnectionDeadline");QVERIFY(deadline);deadline->setInterval(200);
            QVERIFY(network.connectSelected("fixture-password"));QTRY_VERIFY(!network.busy());
            QVERIFY(notices.last()[0].toString().contains(QStringLiteral("超时")));
            deadline->setInterval(40000);fixture.mode="open";
            QVERIFY(scan.open(QIODevice::WriteOnly|QIODevice::Truncate));scan.write(QByteArray(scanLine).replace("WPA2","--"));scan.close();
            QVERIFY(network.scan());QTRY_VERIFY(!network.busy());QVERIFY(network.selectAccessPoint(0));
            QVERIFY(network.connectSelected(""));QTRY_VERIFY(!network.busy());
            QVERIFY(!fixture.settings.contains("802-11-wireless-security"));
            QVERIFY(notices.last()[0].toString().contains(QStringLiteral("已连接")));
        }
        server.unregisterService(service);QDBusConnection::disconnectFromBus("network-check-client");QDBusConnection::disconnectFromBus("network-check-server");
        bus.terminate();QVERIFY(bus.waitForFinished(2000));
    }
};
QTEST_GUILESS_MAIN(NetworkCheck)
#include "network-check.moc"
