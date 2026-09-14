#include "capture.h"
#include <QCoreApplication>
#include <QProcess>
#include <QLocalSocket>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QElapsedTimer>
#include <QThread>
#include <QDir>
#include <stdexcept>
#include <signal.h>

static void require(bool condition, const char *message) { if (!condition) throw std::runtime_error(message); }
static QJsonObject call(QJsonObject request)
{
    QLocalSocket socket;
    socket.connectToServer(qEnvironmentVariable("XDG_RUNTIME_DIR") + "/r46h-wm.sock");
    require(socket.waitForConnected(1000), "control connection");
    request["version"] = 1;
    socket.write(QJsonDocument(request).toJson(QJsonDocument::Compact) + '\n');
    require(socket.waitForBytesWritten(1000), "control write");
    QByteArray input;
    QElapsedTimer timer; timer.start();
    while (!input.endsWith('\n') && timer.elapsed() < 1500) {
        socket.waitForReadyRead(100); input += socket.readAll();
        require(input.size() < 65536, "control response bound");
    }
    const auto result = QJsonDocument::fromJson(input);
    require(result.isObject(), "control JSON");
    return result.object();
}
static QJsonObject set(const char *operation, const char *key, QJsonValue value)
{
    for (int retry = 0; retry < 2; ++retry) {
        const auto state = call({{"op", "observe"}});
        auto response = call({{"op", operation}, {key, value}, {"session", state.value("session")}, {"sequence", state.value("sequence")}});
        if (response.value("error") == QJsonValue("stale_state")) continue;
        require(response.value("ok").toBool(), "control mutation"); return response;
    }
    throw std::runtime_error("control state kept changing");
}
int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    if (argc == 2 && QByteArray(argv[1]) == "rogue") {
        const auto state = call({{"op", "observe"}});
        const auto response = call({{"op", "panel"}, {"active", true}, {"session", state.value("session")}, {"sequence", state.value("sequence")}});
        return response.value("error") == QJsonValue("wrong_owner") ? 0 : 1;
    }
    if (argc != 3) return 2;
    QProcess ui, game;
    ui.setStandardErrorFile(QDir(argv[2]).filePath("ui.log"));
    game.setStandardErrorFile(QDir(argv[2]).filePath("game.log"));
    auto stop = [](QProcess &p) { if (p.state() != QProcess::NotRunning) { p.terminate(); if (!p.waitForFinished(1000)) { p.kill(); p.waitForFinished(1000); } } };
    try {
        ui.start(QString::fromLocal8Bit(argv[1]), {"ui"}); require(ui.waitForStarted(), "UI start");
        game.start(QString::fromLocal8Bit(argv[1]), {"game"}); require(game.waitForStarted(), "game start");
        require(call({{"op", "hello"}, {"uiPid", qint64(ui.processId())}}).value("ok").toBool(), "UI owner hello");
        set("game", "pid", qint64(game.processId()));
        QElapsedTimer timer; timer.start(); bool ready = false;
        while (timer.elapsed() < 4000) {
            const auto state = call({{"op", "observe"}}); const auto surfaces = state.value("surfaces").toArray();
            int mapped = 0;
            for (const auto &value : surfaces) {
                const auto surface = value.toObject();
                if (surface.value("mapped").toBool() && surface.value("width") == QJsonValue(640) && surface.value("height") == QJsonValue(480)) ++mapped;
            }
            if (mapped == 2) { ready = true; break; }
            QThread::msleep(50);
        }
        if (!ready) qWarning().noquote() << QJsonDocument(call({{"op", "observe"}})).toJson(QJsonDocument::Compact);
        require(ready, "both fullscreen surfaces mapped");
        require(captureOutput(1000, 1).error == QString("wrong_compositor"), "capture must match the expected compositor process");
        auto privateFrame = captureOutput();
        require(privateFrame.image.isNull() && !privateFrame.error.isEmpty(), "initial capture private until explicitly allowed");
        set("privacy", "active", false);
        auto frame = captureOutput(); require(frame.error.isEmpty() && !frame.image.isNull(), "composed game capture");
        require(frame.image.pixelColor(20, 20) == QColor("#168b42") && frame.image.pixelColor(600, 20) == QColor("#168b42"), "game-only pixels");
        frame.image.save(QDir(argv[2]).filePath("game.png"));
        set("overlay", "active", true);
        frame = captureOutput(); require(frame.error.isEmpty(), "clipped overlay capture");
        require(frame.image.pixelColor(20, 20) == QColor("#168b42") && frame.image.pixelColor(600, 20) == QColor("#ffe000")
            && frame.image.pixelColor(600, 300) == QColor("#168b42"), "overlay mask limits the transparent UI surface");
        frame.image.save(QDir(argv[2]).filePath("overlay.png"));
        set("overlay", "active", false);
        QThread::msleep(2600);
        auto expired = captureOutput(); require(expired.image.isNull() && !expired.error.isEmpty(), "capture permission expires without client cleanup");
        set("privacy", "active", false);
        const auto old = set("panel", "active", true);
        frame = captureOutput(); require(frame.error.isEmpty(), "panel capture");
        require(frame.image.pixelColor(20, 20) == QColor("#168b42") && frame.image.pixelColor(600, 20) == QColor("#ffe000")
            && frame.image.pixelColor(600, 300) == QColor("#ffe000"), "panel restores the full UI surface over game");
        frame.image.save(QDir(argv[2]).filePath("panel.png"));
        const auto stale = call({{"op", "panel"}, {"active", false}, {"session", old.value("session")}, {"sequence", old.value("sequence").toInteger() - 1}});
        require(stale.value("error") == QJsonValue("stale_state"), "stale state rejected");
        QProcess rogue; rogue.start(QCoreApplication::applicationFilePath(), {"rogue"}); require(rogue.waitForFinished(3000) && rogue.exitCode() == 0, "other process cannot change policy");
        set("privacy", "active", true);
        frame = captureOutput(); require(frame.image.isNull() && !frame.error.isEmpty(), "private capture refused");
        set("privacy", "active", false); set("panel", "active", false);
        stop(game); QThread::msleep(100);
        frame = captureOutput(); require(frame.error.isEmpty() && frame.image.pixelColor(600, 20) == QColor("#ffe000"), "UI restored after game exit");
        frame.image.save(QDir(argv[2]).filePath("returned.png"));
        stop(ui);
        frame = captureOutput(); require(frame.image.isNull() && !frame.error.isEmpty(), "UI exit revokes capture owner");
        // End the compositor with live surfaces, as a target thermal abort does.
        ui.start(QString::fromLocal8Bit(argv[1]), {"ui"}); require(ui.waitForStarted(), "UI restart");
        game.start(QString::fromLocal8Bit(argv[1]), {"game"}); require(game.waitForStarted(), "game restart");
        timer.restart(); ready = false;
        while (timer.elapsed() < 4000) {
            const auto surfaces = call({{"op", "observe"}}).value("surfaces").toArray();
            if (surfaces.size() == 2 && surfaces[0].toObject().value("mapped").toBool()
                && surfaces[1].toObject().value("mapped").toBool()) { ready = true; break; }
            QThread::msleep(30);
        }
        require(ready, "live surfaces before compositor shutdown");
        const int compositor = qEnvironmentVariableIntValue("R46H_TEST_WESTON_PID");
        require(compositor > 1 && kill(compositor, SIGTERM) == 0, "compositor shutdown");
        require(game.waitForFinished(2000) && ui.waitForFinished(2000), "clients observe compositor shutdown");
        stop(game); stop(ui);
        qInfo("HANDHELD_COMPOSITOR_PASS: fullscreen, real composed pixels, panel stacking, private capture, stale/wrong-owner refusal and game exit");
        return 0;
    } catch (const std::exception &error) {
        qCritical("COMPOSITOR_TEST_FAIL %s; ui=%s game=%s", error.what(), ui.readAllStandardError().constData(), game.readAllStandardError().constData());
        stop(game); stop(ui); return 1;
    }
}
