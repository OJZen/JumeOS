#include "input.h"
#include "handheld.h"
#include "preferences.h"
#include "telemetry.h"
#include "control.h"
#include "applications.h"
#include "streaming.h"
#include "device.h"
#include "network.h"
#include "tools.h"
#include <memory>
#include <QCommandLineParser>
#include <QDir>
#include <QFileInfo>
#include <QFile>
#include <QQuickItem>
#include <QGuiApplication>
#include <QQuickView>
#include <QTimer>
#include <QFontDatabase>
#include <QPointer>
#include <QMutex>
#include <QMutexLocker>
#include <QSurfaceFormat>
#include <algorithm>
#include <fcntl.h>

class ShellWindow final : public QQuickView {
public:
    using QQuickView::QQuickView;
    Preferences *preferences = nullptr;
    ToolState *tools = nullptr;
    Applications *applications = nullptr;
    bool closeAfterApplication = false;
protected:
    bool event(QEvent *event) override {
        if (event->type() == QEvent::Close && preferences && !preferences->save()) {
            event->ignore();
            return true;
        }
        if (event->type() == QEvent::Close && tools && !tools->save()) { event->ignore(); return true; }
        if (event->type() == QEvent::Close && applications && applications->running()) {
            closeAfterApplication = true; applications->stop(); event->ignore(); return true;
        }
        return QQuickView::event(event);
    }
};
int main(int argc, char **argv) {
    // Seal a supervisor-delegated handle before Qt can start any helper processes.
    int uinputFd = -1;
    for (int i = 1; i < argc; ++i) if (QByteArray(argv[i]) == "--uinput-fd" || QByteArray(argv[i]).startsWith("--uinput-fd=")) {
        bool ok = false;
        const bool separate = QByteArray(argv[i]) == "--uinput-fd";
        if (uinputFd >= 0 || (separate && i + 1 == argc)) return 2;
        uinputFd = (separate ? QByteArray(argv[++i]) : QByteArray(argv[i]).mid(12)).toInt(&ok);
        if (!ok || uinputFd < 3 || uinputFd > 1024 || fcntl(uinputFd, F_SETFD, FD_CLOEXEC) < 0) return 2;
    }
    for (int i = 1; i < argc; ++i) if (QByteArray(argv[i]) == "--control-call") {
        QCoreApplication relay(argc, argv); QCommandLineParser options;
        options.addOptions({{"control-call", "One restricted SSH UI request."}, {"state-dir", "Wrapper state directory.", "path"},
                            {"control-dir", "Private local endpoint.", "path"}});
        options.process(relay); return runControlCall(options.value("control-dir"));
    }
    for (int i = 1; i < argc; ++i) if (QByteArray(argv[i]) == "--stream-worker") {
        QCoreApplication worker(argc, argv); QCommandLineParser options;
        options.addOptions({{"stream-worker", "Run one validated stream request."}, {"attended", "Operator-present stream ceiling: 35 minutes."}, {"state-dir", "State directory.", "path"},
                            {"moonlight-client", "Client binary.", "path"}, {"moonlight-sha256", "Client SHA-256.", "hash"}});
        options.process(worker);
        if (!QDir::isAbsolutePath(options.value("state-dir"))) return 2;
        Streaming stream(options.value("state-dir")); stream.configureClient(options.value("moonlight-client"), options.value("moonlight-sha256"));
        return stream.runPending(options.isSet("attended") ? 2100 : 120);
    }
    for (int i = 1; i < argc; ++i) if (QByteArray(argv[i]) == "--tool-worker" || QByteArray(argv[i]) == "--native-worker") {
        QCoreApplication worker(argc, argv); QCommandLineParser options;
        options.addOptions({{"tool-worker", "Bounded tool operation.", "operation"}, {"tool-id", "Tool/game identifier.", "id"},
                            {"content-root", "Read-only content root.", "path", "/roms"}, {"state-dir", "Private state directory.", "path"},
                            {"native-worker", "One validated native request."}, {"shared-native", "Run the validated Neo profile in the shared Wayland session."}, {"attended", "Operator-present runtime limit."}});
        options.process(worker);
        if (options.isSet("native-worker")) return ToolState::runNative(options.value("state-dir"), options.isSet("attended") ? 2100 : 120, options.isSet("shared-native"));
        if (options.isSet("shared-native")) return 2;
        return ToolState::worker(options.value("tool-worker"), options.value("tool-id"), options.value("content-root"), options.value("state-dir"));
    }
    const bool virtualKeyboard = qEnvironmentVariable("R46H_VIRTUAL_KEYBOARD") == "1";
    if (virtualKeyboard) {
        qputenv("QT_IM_MODULE", "qtvirtualkeyboard");
        qputenv("QT_VIRTUALKEYBOARD_DESKTOP_DISABLE", "1");
    }
    qputenv("QML_DISABLE_DISK_CACHE", "1");
    QCoreApplication::setAttribute(Qt::AA_DisableShaderDiskCache);
    QGuiApplication app(argc, argv);
    app.setApplicationName(QStringLiteral(JUME_LAUNCHER_NAME));
    app.setApplicationDisplayName(QStringLiteral(JUME_LAUNCHER_NAME));
    app.setApplicationVersion(QStringLiteral(JUME_LAUNCHER_VERSION));
    const auto bundledFont = QCoreApplication::applicationDirPath() + "/../share/fonts/truetype/droid/DroidSansFallbackFull.ttf";
    if (QFileInfo::exists(bundledFont)) QFontDatabase::addApplicationFont(bundledFont);
    QCommandLineParser parser;
    parser.setApplicationDescription("Jume Launcher preview; hardware controls require a guarded session.");
    parser.addHelpOption();
    parser.addVersionOption();
    parser.addOptions({
        {"state-dir", "Required preview state directory (use external workspace).", "path"},
        {"capture", "Save this preview window as PNG, then exit.", "path"},
        {"scene", "Initial scene: home, library, settings, about, quick, session, performance, controller, power, input, streaming, neo, ports or usb.", "name", "home"},
        {"quit-after", "Exit after the specified seconds (1..3600).", "seconds"},
        {"fullscreen", "Show fullscreen; does not establish a global overlay."},
        {"control-dir", "Opt-in private local UI control directory; no network listener.", "path"},
        {"test-input-capture", "Allow captures only in the labelled disposable input-test page."},
        {"content-root", "Read-only ROM/ports root for tool inspection.", "path", "/roms"},
        {"native-handoff", "Supervisor supports validated native-game display handoff."},
        {"resume-native", "Restore the last native-game tool page."},
        {"portmaster-backend", "Private PortMaster adapter script.", "path"},
        {"portmaster-runtime", "Private PortMaster Python runtime.", "path"},
        {"applications", "Owner-provided foreground application list (JSON).", "path"},
        {"handheld-router", "Opt-in shared Wayland session with this input-router executable.", "path"},
        {"input-device", "Identified merged evdev source for the handheld router.", "path"},
        {"uinput-fd", "Supervisor-delegated uinput handle; passed only to the router.", "fd"},
        {"moonlight-client", "Verified Moonlight Qt binary.", "path"},
        {"moonlight-sha256", "Expected Moonlight Qt SHA-256.", "hash"},
        {"stream-handoff", "Supervisor supports exit/restart display handoff."},
        {"profile-ui", "Run bounded idle/card/HUD/panel/settings/keyboard diagnostics, then exit."}
    });
    parser.process(app);
    const auto state = parser.value("state-dir");
    auto scene = parser.value("scene");
    if (state.isEmpty() || !QDir::isAbsolutePath(state) ||
        !QStringList{"home", "library", "settings", "about", "quick", "session", "performance", "controller", "power", "input", "streaming", "neo", "ports", "usb"}.contains(scene)) {
        qCritical("Use --state-dir with an absolute external path and a valid --scene."); return 2;
    }
    bool durationOk = true;
    const int duration = parser.isSet("quit-after") ? parser.value("quit-after").toInt(&durationOk) : 0;
    if (!durationOk || (parser.isSet("quit-after") && (duration < 1 || duration > 3600))) return 2;
    const bool profile = parser.isSet("profile-ui");
    const bool handheldMode = parser.isSet("handheld-router");
    if ((uinputFd >= 0 && !handheldMode) || handheldMode != parser.isSet("input-device") || (handheldMode && (!QGuiApplication::platformName().startsWith("wayland")
        || parser.isSet("stream-handoff") || parser.isSet("native-handoff") || profile))) {
        qCritical("Handheld routing requires Wayland and cannot share a direct-display handoff."); return 2;
    }
    if (profile && parser.isSet("control-dir")) { qCritical("Control capture and performance profiling are separate runs."); return 2; }
    if (profile) {
        qputenv("QSG_INFO", "1");
        qSetMessagePattern(QStringLiteral("[%{time process}] %{category}: %{message}"));
    }
    qputenv("QT_SHADER_CACHE_PATH", QFile::encodeName(QDir(state).filePath("shader-cache")));
    Preferences preferences(state);
    Telemetry telemetry(state);
    DeviceState device("/",qEnvironmentVariable("R46H_DEVICE_CONTROLS")=="1");
    NetworkState network(device.target(),device.controls());
    ToolState tools(state, parser.value("content-root"), device.target(), parser.isSet("native-handoff") || handheldMode);
    if (parser.isSet("resume-native") && !tools.lastGame().isEmpty()) scene = tools.lastGame() == "mslug" ? "neo" : "ports";
    const QString share = QCoreApplication::applicationDirPath() + "/../share/r46h";
    tools.configureCatalog(parser.isSet("portmaster-backend") ? parser.value("portmaster-backend") : share + "/ports/manager.py",
                           parser.isSet("portmaster-runtime") ? parser.value("portmaster-runtime") : share + "/portmaster");
    ControllerInput controller(nullptr, handheldMode);
    if (parser.isSet("stream-handoff") || parser.isSet("native-handoff")) controller.suppressUntilNeutral();
    Streaming streaming(state);
    streaming.configureClient(parser.value("moonlight-client"), parser.value("moonlight-sha256"));
    Applications applications;
    applications.setRoutedInput(handheldMode);
    if (parser.isSet("applications") && !applications.load(parser.value("applications"))) {
        qCritical("APPLICATION_LIST_FAILURE %s", qPrintable(applications.error())); return 2;
    }
    ShellWindow window;
    if (handheldMode) { auto format = window.format(); format.setAlphaBufferSize(8); window.setFormat(format); }
    window.preferences = &preferences;
    window.tools = &tools;
    window.applications = &applications;
    window.setTitle(app.applicationDisplayName() + QStringLiteral(" · R46H"));
    window.setResizeMode(QQuickView::SizeRootObjectToView);
    window.setInitialProperties({{"store", QVariant::fromValue(&preferences)}, {"metrics", QVariant::fromValue(&telemetry)},
        {"sharedDisplay", handheldMode},
        {"controller", QVariant::fromValue(&controller)}, {"keyboardEnabled", virtualKeyboard},
        {"applications", (handheldMode || parser.isSet("applications")) ? QVariant::fromValue(&applications) : QVariant::fromValue<QObject *>(nullptr)},
        {"streaming", QVariant::fromValue(&streaming)}, {"device", QVariant::fromValue(&device)}, {"network", QVariant::fromValue(&network)}, {"tools", QVariant::fromValue(&tools)}, {"testInputCapture", parser.isSet("test-input-capture")}});
    QObject::connect(&window, &QQuickWindow::frameSwapped, &telemetry, &Telemetry::frameSubmitted, Qt::DirectConnection);
    window.setSource(QUrl("qrc:/qt/qml/R46H/Shell/ShellView.qml"));
    if (window.status() != QQuickView::Ready) return 1;
    const QPointer<QQuickItem> root(window.rootObject());
    int fatalStatus = 0;
    std::unique_ptr<HandheldSession> handheld;
    if (handheldMode) {
        handheld = std::make_unique<HandheldSession>(&window, &controller, &applications);
        QObject::connect(handheld.get(), &HandheldSession::frameMetricsChanged, &telemetry, [&] { telemetry.setGame(handheld->frameMetrics().toVariantMap()); });
        root->setProperty("sharedReady", false);
        QObject::connect(handheld.get(), &HandheldSession::changed, &window, [&] { if (root) root->setProperty("sharedReady", handheld->ready()); });
        QObject::connect(handheld.get(), &HandheldSession::failed, &window, [&](const QString &message) {
            fatalStatus = 1; qCritical("HANDHELD_SESSION_FAILURE %s", qPrintable(message)); window.close();
        });
        QObject::connect(root, SIGNAL(quickOpenChanged()), handheld.get(), SLOT(sceneChanged()));
        QObject::connect(root, SIGNAL(panelVisibleChanged()), handheld.get(), SLOT(sceneChanged()));
        QObject::connect(root, SIGNAL(monitorVisibleChanged()), handheld.get(), SLOT(sceneChanged()));
        QObject::connect(root, SIGNAL(sensitiveVisibleChanged()), handheld.get(), SLOT(sceneChanged()));
        QString error;
        if (!handheld->start(parser.value("handheld-router"), parser.value("input-device"), &error, uinputFd)) {
            qCritical("HANDHELD_START_FAILURE %s", qPrintable(error)); return 2;
        }
    }
    QObject::connect(&tools, &ToolState::notice, &window, [root](const QString &message) { if (root) QMetaObject::invokeMethod(root, "notify", Q_ARG(QVariant, message)); });
    QString sharedNativeGame;
    QObject::connect(&tools, &ToolState::nativeRequested, &app, [&](const QString &game) {
        if (!preferences.save()) return;
        if (!handheldMode) { QCoreApplication::exit(79); return; }
        if (!handheld->ready() || applications.running()) return;
        auto environment = QProcessEnvironment::systemEnvironment();
        environment.insert("QT_QPA_PLATFORM", "wayland");
        environment.remove("R46H_SHELL_LOG");
        if (applications.launchPrepared("native." + game, QCoreApplication::applicationFilePath(),
            {"--native-worker", "--shared-native", "--state-dir", state}, state, environment)) sharedNativeGame = game;
    });
    QObject::connect(&device,&DeviceState::powerRequested,&app,[](int code){QCoreApplication::exit(code);});
    QObject::connect(&device,&DeviceState::warning,&window,[root](const QString &message){if(root)QMetaObject::invokeMethod(root,"notify",Q_ARG(QVariant,message));});
    QObject::connect(&network,&NetworkState::notice,&window,[root](const QString &message){if(root)QMetaObject::invokeMethod(root,"notify",Q_ARG(QVariant,message));});
    QObject::connect(&streaming, &Streaming::changed, &window, [&] {
        if (root && root->property("editing").toBool() && !streaming.error().isEmpty())
            QMetaObject::invokeMethod(root, "notify", Q_ARG(QVariant, streaming.error()));
    });
    bool sharedStreamActive = false;
    QObject::connect(&streaming, &Streaming::statisticsChanged, &telemetry, [&] { telemetry.setStream(streaming.statistics()); });
    QObject::connect(&applications, &Applications::outputReady, &streaming, [&](const QByteArray &data) {
        if (sharedStreamActive) streaming.ingestStatistics(data);
    });
    QObject::connect(&streaming, &Streaming::launchRequested, &window, [&] {
        if (!preferences.save()) return;
        if (handheldMode) {
            if (!handheld->ready() || applications.running()) return;
            auto environment = QProcessEnvironment::systemEnvironment();
            environment.insert("QT_QPA_PLATFORM", "wayland");
            environment.insert("SDL_VIDEODRIVER", "wayland");
            environment.insert("R46H_STREAM_STATS", "1");
            environment.remove("R46H_SHELL_LOG");
            environment.remove("QT_IM_MODULE");
            environment.remove("R46H_VIRTUAL_KEYBOARD");
            environment.remove("QT_QPA_EGLFS_INTEGRATION");
            environment.remove("DRM_FORCE_DIRECT");
            environment.remove("DRM_FORCE_EGL");
            sharedStreamActive = applications.launchPrepared("builtin.moonlight", QCoreApplication::applicationFilePath(),
                {"--stream-worker", "--state-dir", state, "--moonlight-client", parser.value("moonlight-client"),
                 "--moonlight-sha256", parser.value("moonlight-sha256")}, state, environment, true);
            streaming.setStatisticsActive(sharedStreamActive);
            return;
        }
        if (!parser.isSet("stream-handoff")) {
            QMetaObject::invokeMethod(root, "notify", Q_ARG(QVariant, QStringLiteral("请通过串流会话启动桌面。"))); return;
        }
        QCoreApplication::exit(75);
    });
    QObject::connect(&window, &QWindow::visibilityChanged, &window, [root](QWindow::Visibility visibility) {
        // The view can hide after its QML tree has already been destroyed.
        if (root) root->setProperty("windowVisible", visibility != QWindow::Hidden && visibility != QWindow::Minimized);
    });
    window.resize(1024, 768);
    window.setMinimumSize(QSize(640, 480));
    QMetaObject::invokeMethod(window.rootObject(), "showScene", Q_ARG(QVariant, scene));
    QObject::connect(&controller, &ControllerInput::action, &window,
        [&](const QString &action, bool repeat) {
            if (handheldMode ? (!handheld->ready() || (applications.running() && !root->property("quickOpen").toBool()))
                             : (!window.isActive() || applications.running())) return;
            QMetaObject::invokeMethod(window.rootObject(), "dispatch", Q_ARG(QVariant, action), Q_ARG(QVariant, repeat));
        });
    QObject::connect(&applications, &Applications::started, &window, [&] {
        controller.suppressUntilNeutral();
        if (!handheldMode) window.hide();
    });
    QObject::connect(&applications, &Applications::finished, &window, [&] {
        controller.suppressUntilNeutral();
        if (!sharedNativeGame.isEmpty()) {
            const auto game = std::exchange(sharedNativeGame, QString());
            tools.nativeFinished(game, applications.error().isEmpty() ? 0 : applications.exitCode());
        }
        if (sharedStreamActive) {
            sharedStreamActive = false;
            streaming.streamFinished(applications.error().isEmpty() ? 0 : applications.exitCode());
        }
        if (root && handheldMode) root->setProperty("quickOpen", false);
        window.show();
        if (window.closeAfterApplication) { window.closeAfterApplication = false; window.close(); return; }
        window.requestActivate();
        if (root) root->forceActiveFocus();
    });
    std::unique_ptr<ControlServer> control;
    if (parser.isSet("control-dir")) {
        control = std::make_unique<ControlServer>(&window, &preferences, &device, &telemetry, handheld.get());
        QString error;
        if (!control->start(parser.value("control-dir"), &error)) { qCritical("CONTROL_START_FAILURE %s", qPrintable(error)); return 2; }
    }
    if (parser.isSet("fullscreen")) window.showFullScreen(); else window.show();
    if (parser.isSet("capture")) {
        QTimer::singleShot(2200, &window, [&] {
            if (root && root->property("sensitiveVisible").toBool()) { qWarning("SHELL_CAPTURE sensitive content unavailable"); app.exit(2); return; }
            const bool ok = window.grabWindow().save(parser.value("capture"));
            qInfo("SHELL_CAPTURE %s Qt=%s boundary=host-window-only", ok ? "PASS" : "FAIL", qVersion());
            app.exit(ok ? 0 : 1);
        });
    }
    if (duration) QTimer::singleShot(duration * 1000, &window, &QWindow::close);
    QTimer profileTimer;
    int profileTick = 0;
    QMutex profileMutex;
    unsigned profileFrames = 0;
    QList<qint64> frameIntervals;
    qint64 previousFrame = 0;
    QElapsedTimer frameClock;
    QMetaObject::Connection profileConnection;
    QElapsedTimer profileClock;
    const char *profilePhase = nullptr;
    const bool originalMotion = preferences.reducedMotion(), originalMonitor = preferences.monitor();
    auto beginPhase = [&](const char *name) {
        unsigned frames; QList<qint64> intervals;
        {
            QMutexLocker lock(&profileMutex);
            frames = std::exchange(profileFrames, 0); intervals.swap(frameIntervals); previousFrame = 0;
        }
        std::sort(intervals.begin(), intervals.end());
        auto percentile = [&](double p) { return intervals.isEmpty() ? 0. : intervals[qMin(intervals.size() - 1, qsizetype(p * (intervals.size() - 1)))] / 1e6; };
        if (profilePhase)
            qInfo("SHELL_PROFILE_RESULT phase=%s elapsed_ms=%lld submissions=%u intervals=%lld p50_ms=%.2f p95_ms=%.2f max_ms=%.2f boundary=submissions-including-idle-gaps", profilePhase,
                  static_cast<long long>(profileClock.elapsed()), frames, static_cast<long long>(intervals.size()), percentile(.5), percentile(.95), percentile(1));
        profilePhase = name; profileClock.start();
        qInfo("SHELL_PROFILE phase=%s", name);
    };
    auto finishProfile = [&] {
        profileTimer.stop(); beginPhase("complete");
        if (preferences.reducedMotion() != originalMotion) preferences.adjust("motion", 1);
        if (preferences.monitor() != originalMonitor) preferences.adjust("monitor", 1);
        window.close();
    };
    if (profile) {
        frameIntervals.reserve(2048); frameClock.start();
        profileConnection = QObject::connect(&window, &QQuickWindow::frameSwapped, &window, [&] {
            const auto now = frameClock.nsecsElapsed();
            QMutexLocker lock(&profileMutex); ++profileFrames;
            if (previousFrame && frameIntervals.size() < 2048) frameIntervals.append(now - previousFrame);
            previousFrame = now;
        }, Qt::DirectConnection);
        // A 100 ms input cadence includes the idle gaps between 90 ms focus animations.
        if (preferences.reducedMotion()) preferences.adjust("motion", 1);
        if (preferences.monitor()) preferences.adjust("monitor", 1);
        QMetaObject::invokeMethod(window.rootObject(), "showScene", Q_ARG(QVariant, "home"));
        profileTimer.setTimerType(Qt::PreciseTimer);
        profileTimer.setInterval(100);
        QObject::connect(&profileTimer, &QTimer::timeout, &window, [&] {
            if (profileTick == 0) beginPhase("idle");
            if (profileTick == 30) beginPhase("cards");
            if (profileTick == 130) {
                preferences.adjust("monitor", 1);
                beginPhase("cards-hud");
            }
            if (profileTick == 230) {
                preferences.adjust("monitor", 1);
                beginPhase("panel");
            }
            if (profileTick >= 30 && profileTick < 230) root->setProperty("selected", profileTick % 2);
            if (profileTick >= 230 && profileTick < 330) root->setProperty("quickOpen", bool(profileTick % 2));
            if (profileTick == 330) {
                root->setProperty("quickOpen", false);
                QMetaObject::invokeMethod(root, "showScene", Q_ARG(QVariant, QStringLiteral("settings")));
                beginPhase("settings-focus");
            }
            if (profileTick == 430) {
                preferences.adjust("monitor", 1);
                beginPhase("settings-focus-hud");
            }
            if (profileTick >= 330 && profileTick < 530)
                QMetaObject::invokeMethod(root, "dispatch", Q_ARG(QVariant, profileTick % 2 ? QStringLiteral("left") : QStringLiteral("right")), Q_ARG(QVariant, false));
            if (profileTick == 530) {
                preferences.adjust("monitor", 1);
                if (!virtualKeyboard) { finishProfile(); return; }
                beginPhase("keyboard-load");
                QMetaObject::invokeMethod(root, "showScene", Q_ARG(QVariant, QStringLiteral("input")));
            }
            if (profileTick == 560) {
                controller.keyboardAction("down");
                beginPhase("keyboard");
                profileTimer.setInterval(16);
            }
            if (profileTick >= 560) {
                controller.keyboardAction(profileTick % 2 ? "left" : "right");
                if (profileClock.elapsed() >= 10000) {
                    if (!preferences.monitor()) {
                        preferences.adjust("monitor", 1);
                        beginPhase("keyboard-hud");
                    } else { finishProfile(); return; }
                }
            }
            ++profileTick;
        });
        profileTimer.start();
    }
    const int result = app.exec();
    QObject::disconnect(profileConnection);
    return fatalStatus ? fatalStatus : result;
}
