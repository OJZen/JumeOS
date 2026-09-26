// Dedicated solid-color surfaces for real composition checks, not a product screen.
#include <QGuiApplication>
#include <QQuickView>
#include <QQmlComponent>
#include <QQuickItem>
#include <QTimer>
#include <QFile>
#include <QSaveFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <SDL.h>
#include <chrono>
#include <array>

class TestView final:public QQuickView {
public:
    QString closeGate;int closeRequests=0;
protected:
    bool event(QEvent *event) override {
        if(event->type()==QEvent::Close&&!closeGate.isEmpty()) {
            ++closeRequests;QFile file(closeGate+".requests");if(file.open(QIODevice::WriteOnly))file.write(QByteArray::number(closeRequests));
            if(!QFile::exists(closeGate)){event->ignore();return true;}
        }
        return QQuickView::event(event);
    }
};

int main(int argc, char **argv)
{
    if (argc != 2 && argc != 3 && argc != 4) return 2;
    QGuiApplication app(argc, argv);
    if (argc == 4 && QByteArray(argv[1]) == "--compare-frames") {
        const QImage left = QImage(QString::fromLocal8Bit(argv[2])).convertToFormat(QImage::Format_ARGB32);
        const QImage right = QImage(QString::fromLocal8Bit(argv[3])).convertToFormat(QImage::Format_ARGB32);
        return !left.isNull() && !right.isNull() && left == right ? 0 : 4;
    }
    if (argc == 4) return 2;
    if (argc == 3 && QByteArray(argv[1]) == "--check-panel") {
        const QImage frame(QString::fromLocal8Bit(argv[2]));
        if (frame.isNull() || frame.width() != 640 || frame.height() != 480) return 4;
        const auto game = frame.pixelColor(20, 20), panel = frame.pixelColor(400, 100);
        return game.alpha() == 255 && game.green() > game.red() * 2 && game.green() > game.blue()
            && panel.alpha() == 255 && panel != game ? 0 : 4;
    }
    TestView view;view.closeGate=qEnvironmentVariable("R46H_TEST_CLOSE_GATE");
    if (QByteArray(argv[1])=="ui" && qEnvironmentVariableIntValue("R46H_TEST_PASS_THROUGH")==1)
        QTimer::singleShot(200, &view, [&] { view.setFlag(Qt::WindowTransparentForInput); });
    view.setColor(Qt::transparent);
    view.setResizeMode(QQuickView::SizeRootObjectToView);
    QQmlComponent component(view.engine());
    const bool server = QByteArray(argv[1]) == "server";
    const QByteArray qml = QByteArray("import QtQuick\nItem { id: root; property int frameTick: 0; property bool animate: false; property bool serverMode: false; property bool inputA: false; property real axisX: 0; property real axisY: 0; width: 640; height: 480; Rectangle { anchors.right: parent.right; height: parent.height; width: ")
        + (QByteArray(argv[1]) == "ui" ? "200; color: '#ffe000'" : "parent.width; color: root.serverMode && root.inputA ? '#204ddb' : '#168b42'")
        + " } Rectangle { visible: root.animate; width: 2; height: 2; x: root.frameTick; color: '#123456' } Text { visible: root.serverMode; x: 40; y: 40; color: 'white'; font.pixelSize: 24; text: 'Sunshine input loopback' } Rectangle { visible: root.serverMode; x: 300 + root.axisX * 180; y: 340 + root.axisY * 70; width: 40; height: 40; radius: 6; color: 'white' } }";
    QByteArray scene=qml;
    if(QByteArray(argv[1])=="ui")scene.insert(scene.lastIndexOf('}'),"Rectangle { x: 250; y: 12; width: 140; height: 35; color: '#e030aa' } ");
    component.setData(scene, QUrl());
    auto *item = qobject_cast<QQuickItem *>(component.create());
    if (!item) return 2;
    item->setProperty("serverMode", server);
    view.setContent(QUrl(), &component, item);
    view.resize(640, 480); view.show();
    SDL_GameController *controller = nullptr;
    std::array<int,SDL_CONTROLLER_BUTTON_MAX> presses{};
    QTimer timer;
    QTimer paintTimer; paintTimer.setTimerType(Qt::PreciseTimer);
    QObject::connect(&paintTimer, &QTimer::timeout, item, [item] { item->setProperty("frameTick", 1 - item->property("frameTick").toInt()); });
    qint64 renderedFrames = 0;
    QObject::connect(&view, &QQuickWindow::frameSwapped, &app, [&] { ++renderedFrames; });
    int frameRate = 0;
    if (argc == 3) {
        if (SDL_InitSubSystem(SDL_INIT_GAMECONTROLLER)) return 3;
        QObject::connect(&timer, &QTimer::timeout, &app, [&] {
            QFile rateFile(QString::fromLocal8Bit(argv[2]) + ".fps");
            if (rateFile.open(QIODevice::ReadOnly)) {
                bool valid = false; const int rate = rateFile.read(8).trimmed().toInt(&valid);
                if (valid && (rate == 0 || rate == 15 || rate == 60) && rate != frameRate) {
                    frameRate = rate; item->setProperty("animate", rate != 0);
                    if (rate) paintTimer.start(1000 / rate); else paintTimer.stop();
                }
            }
            QFile exitFile(QString::fromLocal8Bit(argv[2]) + ".exit");
            if (exitFile.open(QIODevice::ReadOnly)) {
                bool ok = false; const int code = exitFile.read(16).trimmed().toInt(&ok);
                if (ok && code >= 0 && code <= 255) { app.exit(code); return; }
            }
            SDL_Event event; while (SDL_PollEvent(&event)) {
                if(event.type==SDL_CONTROLLERBUTTONDOWN&&controller&&event.cbutton.button<presses.size()
                    &&event.cbutton.which==SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(controller)))++presses[event.cbutton.button];
            }
            const auto sampledAt = std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
            QJsonObject state{{"controllers", SDL_NumJoysticks()}, {"pid", QCoreApplication::applicationPid()},
                {"renderedFrames", renderedFrames}, {"sampledAtMs", qint64(sampledAt)}, {"requestedFps", frameRate}};
            if (controller && !SDL_GameControllerGetAttached(controller)) { SDL_GameControllerClose(controller); controller = nullptr; }
            if (!controller) for (int i = 0; i < SDL_NumJoysticks(); ++i) {
                const auto selected=qEnvironmentVariable("SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT").section('/',1).toUInt(nullptr,16);
                if (SDL_JoystickGetDeviceVendor(i) != (server ? 0x045e : 0x5246) || SDL_JoystickGetDeviceProduct(i) != (server ? 0x02ea : selected?selected:0x0049)) continue;
                char guid[33]; SDL_JoystickGetGUIDString(SDL_JoystickGetDeviceGUID(i), guid, sizeof(guid));
                state["guid"] = QString::fromLatin1(guid);
                controller = SDL_GameControllerOpen(i); break;
            }
            if (controller) {
                char guid[33]; SDL_JoystickGetGUIDString(SDL_JoystickGetGUID(SDL_GameControllerGetJoystick(controller)), guid, sizeof(guid));
                state["guid"] = QString::fromLatin1(guid);
                QJsonArray buttons, axes;
                for (int i = 0; i < SDL_CONTROLLER_BUTTON_MAX; ++i) buttons.append(int(SDL_GameControllerGetButton(controller, SDL_GameControllerButton(i))));
                for (int i = 0; i < SDL_CONTROLLER_AXIS_MAX; ++i) axes.append(int(SDL_GameControllerGetAxis(controller, SDL_GameControllerAxis(i))));
                QJsonArray edges;for(int value:presses)edges.append(value);
                state["buttons"] = buttons; state["axes"] = axes;state["presses"]=edges;
            }
            if (server) {
                item->setProperty("inputA", controller && SDL_GameControllerGetButton(controller, SDL_CONTROLLER_BUTTON_A));
                item->setProperty("axisX", controller ? SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_LEFTX) / 32767. : 0);
                item->setProperty("axisY", controller ? SDL_GameControllerGetAxis(controller, SDL_CONTROLLER_AXIS_LEFTY) / 32767. : 0);
            }
            QSaveFile file(QString::fromLocal8Bit(argv[2]));
            if (file.open(QIODevice::WriteOnly)) { file.write(QJsonDocument(state).toJson(QJsonDocument::Compact)); file.commit(); }
        });
        timer.start(30);
    }
    const int result = app.exec();
    if (controller) SDL_GameControllerClose(controller);
    if (argc == 3) SDL_QuitSubSystem(SDL_INIT_GAMECONTROLLER);
    return result;
}
