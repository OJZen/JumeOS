#include "tools.h"
#include "usbgamepad.h"
#include <QTest>
#include <QSignalSpy>
#include <QTemporaryDir>
#include <QCommandLineParser>
#include <QThread>
#include <QFile>
#include <QDir>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <limits>
#include <sys/stat.h>
#include <cstdio>

class ToolsCheck : public QObject {
    Q_OBJECT
    static bool put(const QString &path, const QByteArray &bytes) {
        if (!QDir().mkpath(QFileInfo(path).absolutePath())) return false;
        QFile f(path); return f.open(QIODevice::WriteOnly) && f.write(bytes) == bytes.size();
    }
    static QByteArray get(const QString &path) { QFile f(path); return f.open(QIODevice::ReadOnly) ? f.readAll() : QByteArray(); }
private slots:
    void neoConfigurationAndNativeResult() {
        auto settings = ToolState::defaults(); settings["neoSmooth"] = true;
        const auto direct = ToolState::neoConfiguration(settings, "/private/game", false);
        const auto shared = ToolState::neoConfiguration(settings, "/private/game", true);
        QVERIFY(direct.contains("input_exit_emulator_btn = \"9\"")); QVERIFY(!direct.contains("wayland"));
        QVERIFY(shared.contains("video_context_driver = \"wayland\""));
        QVERIFY(shared.contains("input_joypad_driver = \"sdl2\""));
        QVERIFY(shared.contains("input_player1_a_btn = \"0\""));
        QVERIFY(shared.contains("input_player1_start_btn = \"6\""));
        QVERIFY(shared.contains("input_player1_l2_axis = \"+4\""));
        QVERIFY(shared.contains("input_player1_r2_axis = \"+5\""));
        for (const auto &config : {direct, shared}) {
            QVERIFY(config.contains("core_options_path = \"/private/game/core-options.cfg\""));
            QVERIFY(config.contains("history_list_enable = \"false\""));
            QVERIFY(config.contains("quit_press_twice = \"false\""));
            QVERIFY(config.contains("video_smooth = \"true\""));
        }
        for (const auto &path : {QString("relative"), QString("/bad\"path"), QString("/bad\\path"), QString("/bad\npath")})
            QVERIFY(ToolState::neoConfiguration(settings, path, true).isEmpty());
        QTemporaryDir directory; ToolState state(directory.path(), "/roms", false);
        state.nativeFinished("mslug", 7); state.nativeFinished("mslug", 0);
        const auto result = QJsonDocument::fromJson(get(directory.filePath("tools/native-result.json"))).object();
        QCOMPARE(result.value("exit").toInt(-1), 0); QCOMPARE(state.lastGame(), QString("mslug"));
        ToolState restored(directory.path(), "/roms", false); QCOMPARE(restored.lastGame(), QString("mslug"));
    }
    void inspectionSwitchesWithoutStaleResults() {
        QTemporaryDir dir; ToolState state(dir.path(), dir.filePath("roms"), false);
        QVERIFY(state.inspect("neo")); QVERIFY(state.busy());
        QVERIFY(!state.choose("usbSwapAB", true));
        QVERIFY(state.inspect("ports")); QVERIFY(state.inspect("usb"));
        QTRY_VERIFY_WITH_TIMEOUT(!state.busy() && state.info().value("kind").toString() == "usb", 3000);
        QVERIFY(!state.info().value("enabled").toBool());
        QVERIFY(state.inspect("neo"));
        QTRY_VERIFY_WITH_TIMEOUT(!state.busy() && state.info().value("kind").toString() == "neo", 3000);
        QVERIFY(!state.info().value("neoVerified").toBool());
    }
    void profileValidationAndAtomicRetry() {
        QTemporaryDir dir; QVERIFY(dir.isValid());
        ToolState state(dir.path(), dir.filePath("roms"), false);
        QVERIFY(state.choose("usbSwapAB", true)); QVERIFY(!state.dirty());
        ToolState restored(dir.path(), dir.filePath("roms"), false);
        QVERIFY(restored.settings().value("usbSwapAB").toBool());
        QVERIFY(!state.choose("usbDeadzone", true)); QVERIFY(!state.choose("usbDeadzone", "10"));
        QVERIFY(!state.choose("usbDeadzone", 31)); QVERIFY(!state.choose("usbDeadzone", 12));
        QVERIFY(!state.choose("usbDeadzone", std::numeric_limits<double>::quiet_NaN()));
        QVERIFY(!state.choose("usbEnabled", true)); QVERIFY(!state.nativeEnabled());
        const auto path = dir.filePath("tools/settings.json"), other = dir.filePath("original");
        QVERIFY(put(other, "keep")); QVERIFY(QFile::remove(path)); QVERIFY(QFile::link(other, path));
        QVERIFY(!state.choose("neoSmooth", true)); QVERIFY(state.dirty()); QCOMPARE(get(other), QByteArray("keep"));
        QVERIFY(QFile::remove(path)); QVERIFY(state.save()); QVERIFY(!state.dirty());
        QCOMPARE(ToolState(dir.path(), dir.filePath("roms"), false).settings().value("neoSmooth").toBool(), true);
        QVERIFY(put(path, "bad-json"));
        ToolState corrupt(dir.path(), dir.filePath("roms"), false); QVERIFY(!corrupt.error().isEmpty());
        QVERIFY(!corrupt.choose("neoSmooth", false)); QCOMPARE(get(path), QByteArray("bad-json"));
        QCOMPARE(ToolState::worker("export", "usb", dir.filePath("roms"), dir.path()), 1);
    }
    void sourceInventoryAndSaveImport() {
        QTemporaryDir dir; const auto content = dir.filePath("roms"), state = dir.filePath("state");
        const auto game = content + "/ports/stardewvalley1615";
        for (const auto &file : {"SVLoader.exe", "dlls/StardewPatches.dll", "gamedata/Stardew Valley.exe", "gamedata/Content/a.xnb", "savedata/Saves/farm/save"}) QVERIFY(put(game + "/" + file, "original"));
        auto info = ToolState::scan(content, state, "ports", false); auto port = info.value("ports").toList().first().toMap();
        QVERIFY(port.value("dataPresent").toBool()); QVERIFY(!port.value("runtimePresent").toBool());
        QCOMPARE(port.value("originalSaves").toInt(), 1);
        QCOMPARE(ToolState::worker("import", "stardew", content, state), 0);
        const auto copied = state + "/tools/ports/stardew/saves/Saves/farm/save";
        QCOMPARE(get(copied), QByteArray("original")); QCOMPARE(get(game + "/savedata/Saves/farm/save"), QByteArray("original"));
        QVERIFY(put(copied, "new progress"));
        QCOMPARE(ToolState::worker("import", "stardew", content, state), 1); QCOMPARE(get(copied), QByteArray("new progress"));
        QCOMPARE(ToolState::worker("backup", "stardew", content, state), 0);
        const auto backups = QDir(state + "/tools/backups").entryList(QDir::Dirs | QDir::NoDotAndDotDot); QCOMPARE(backups.size(), 1);
        const auto backup = state + "/tools/backups/" + backups.first(); QCOMPARE(get(backup + "/Saves/farm/save"), QByteArray("new progress"));
        const auto receipt = QJsonDocument::fromJson(get(backup + "/r46h-copy-receipt.json")).object(); QCOMPARE(receipt.value("files").toArray().size(), 1);
        QCOMPARE(ToolState::worker("import", "../../escape", content, state), 1);
        QVERIFY(put(content + "/ports/gta3/userfiles/save", "safe"));
        QVERIFY(QFile::link(dir.filePath("original-outside"), content + "/ports/gta3/userfiles/link"));
        QCOMPARE(ToolState::worker("import", "gta3", content, state), 1);
        QVERIFY(!QFileInfo::exists(state + "/tools/ports/gta3/saves"));
        QVERIFY(!ToolState::scan(content, state, "neo", true).value("neoVerified").toBool());
        QCOMPARE(ToolState::runNative(state, 1), 2); // Host preview cannot launch the R46H profile.
    }
    void nativePortRequestIsBoundedToKnownGames() {
        QTemporaryDir dir; ToolState state(dir.path(), "/roms", true, true);
        QSignalSpy requested(&state, &ToolState::nativeRequested);
        QVERIFY(!state.requestPort("gtasa")); QVERIFY(!state.requestPort("../../escape"));
        QVERIFY(state.requestPort("gta3")); QCOMPARE(requested.size(), 1);
        const auto request = QJsonDocument::fromJson(get(dir.filePath("tools/native-request.json"))).object();
        QCOMPARE(request.value("game").toString(), QString("gta3"));
        QCOMPARE(ToolState::runNative(dir.path(), 1), 2); // A host fixture cannot cross the physical guard.
        ToolState transient("/run/r46h-fixture", "/roms", true, true); QVERIFY(!transient.portsEnabled());
        const auto display = qgetenv("WAYLAND_DISPLAY"), capability = qgetenv("R46H_SHARED_PORTS");
        qputenv("WAYLAND_DISPLAY", "fixture"); qunsetenv("R46H_SHARED_PORTS");
        QVERIFY(!state.portsEnabled()); QVERIFY(!state.requestPort("gta3"));
        qputenv("R46H_SHARED_PORTS", "1"); QVERIFY(state.portsEnabled());
        QVERIFY(!transient.portsEnabled()); QVERIFY(state.requestPort("gta3"));
        QCOMPARE(ToolState::runNative(dir.path(), 1, true), 2);
        if (display.isNull()) qunsetenv("WAYLAND_DISPLAY"); else qputenv("WAYLAND_DISPLAY", display);
        if (capability.isNull()) qunsetenv("R46H_SHARED_PORTS"); else qputenv("R46H_SHARED_PORTS", capability);
    }
    void hidDescriptorAndReports() {
        const auto settings = ToolState::defaults();
        QCOMPARE(UsbGamepad::report({}, 0, 0, settings).toHex(), QByteArray("0100000800000000000000000000"));
        auto profile = settings; profile["usbSwapAB"] = true; profile["usbSwapXY"] = true; profile["usbInvertRightY"] = true;
        const auto packet = UsbGamepad::report({-1., 1., .05, 1., 0., 1.}, 5, 3, profile);
        QCOMPARE(packet.size(), 14); QCOMPARE(quint8(packet[1]), quint8(10)); QCOMPARE(quint8(packet[3]), quint8(1));
        QCOMPARE(packet.mid(4, 8).toHex(), QByteArray("0180ff7f00000180")); QCOMPARE(quint8(packet[13]), quint8(255));
        QCOMPARE(quint8(UsbGamepad::report({}, 0, 15, settings)[3]), quint8(8));
        QCOMPARE(UsbGamepad::report({2., -2., std::numeric_limits<double>::quiet_NaN()}, 0, 0, settings).mid(4, 6).toHex(), QByteArray("ff7f01800000"));
        // Parse short HID items and verify input bit length plus Report ID.
        const auto descriptor = UsbGamepad::descriptor(); int size = 0, count = 0, bits = 0, reportId = 0;
        for (int i = 0; i < descriptor.size();) {
            const auto prefix = quint8(descriptor[i++]); QVERIFY(prefix != 0xfe); const int length = (prefix & 3) == 3 ? 4 : prefix & 3;
            QVERIFY(i + length <= descriptor.size()); unsigned value = 0;
            for (int j = 0; j < length; ++j) value |= unsigned(quint8(descriptor[i++])) << (8 * j);
            if ((prefix & 0xfc) == 0x74) size = int(value);
            if ((prefix & 0xfc) == 0x94) count = int(value);
            if ((prefix & 0xfc) == 0x84) reportId = int(value);
            if ((prefix & 0xfc) == 0x80) bits += size * count;
        }
        QCOMPARE(reportId, 1); QCOMPARE(bits, 104);
        QTemporaryDir dir; ToolState state(dir.path(), dir.filePath("roms"), false); QVERIFY(state.choose("usbDeadzone", 15));
        QCOMPARE(ToolState::worker("export", "usb", dir.filePath("roms"), dir.path()), 0);
        const auto exported = QJsonDocument::fromJson(get(dir.filePath("tools/usb-profile.json"))).object();
        QCOMPARE(exported.value("reportLength").toInt(), 14); QVERIFY(!exported.value("usbEnabled").toBool()); QVERIFY(!exported.value("settings").toObject().contains("neoSmooth"));
    }
};
int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    if (app.arguments().size() == 3 && app.arguments()[1] == "--neo-config") {
        const auto config = ToolState::neoConfiguration(ToolState::defaults(), app.arguments()[2], true);
        return config.isEmpty() || std::fwrite(config.constData(), 1, size_t(config.size()), stdout) != size_t(config.size()) ? 2 : 0;
    }
    if (app.arguments().contains("--tool-worker")) {
        QCommandLineParser parser;
        parser.addOptions({{"tool-worker", "Operation", "operation"}, {"tool-id", "Identifier", "id"}, {"content-root", "Root", "path"}, {"state-dir", "State", "path"}});
        parser.process(app); QThread::msleep(150); // Test binary only: exercise an in-flight route switch.
        return ToolState::worker(parser.value("tool-worker"), parser.value("tool-id"), parser.value("content-root"), parser.value("state-dir"));
    }
    ToolsCheck check; return QTest::qExec(&check, argc, argv);
}
#include "tools-check.moc"
