#include "browserinput.h"
#include <QGuiApplication>
#include <QQuickView>
#include <QQmlContext>
#include <QQmlEngine>
#include <QQuickItem>
#include <QCommandLineParser>
#include <QDir>
#include <QFileInfo>
#include <QLockFile>
#include <QFontDatabase>
#include <QJsonDocument>
#include <QJsonObject>
#include <cstdio>
#include <QtWebEngineQuick/qtwebenginequickglobal.h>
#include <QtWebEngineCore/qtwebenginecoreglobal.h>
#include <unistd.h>
#include <sys/stat.h>

int main(int argc, char **argv)
{
    const QJsonObject engineVersions{{"webEngine", qWebEngineVersion()},
        {"chromium", qWebEngineChromiumVersion()}, {"securityPatch", qWebEngineChromiumSecurityPatchVersion()}};
    // Packaging reads the linked engine, without a display, profile or renderer.
    if (argc == 2 && QByteArray(argv[1]) == "--engine-versions") {
        const auto json = QJsonDocument(engineVersions).toJson();
        return std::fwrite(json.constData(), 1, json.size(), stdout) == size_t(json.size()) ? 0 : 1;
    }
    umask(0077);
    // Security is not a performance knob. Do not inherit debug/sandbox overrides.
    qunsetenv("QTWEBENGINE_DISABLE_SANDBOX");
    qunsetenv("QTWEBENGINE_REMOTE_DEBUGGING");
    // Chromium's desktop tile budget is too large for the R46H's shared 1 GiB RAM.
    // This bounds compositor tiles, not total GPU/renderer memory or JS heaps.
    qputenv("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-extensions --force-gpu-mem-available-mb=128");
    qputenv("QT_IM_MODULE", "qtvirtualkeyboard");
    qputenv("QT_VIRTUALKEYBOARD_DESKTOP_DISABLE", "1");
    QCoreApplication::setAttribute(Qt::AA_DisableShaderDiskCache);
    QQuickWindow::setGraphicsApi(QSGRendererInterface::OpenGL);
    QtWebEngineQuick::initialize();
    QGuiApplication app(argc, argv);
    app.setApplicationName("Jume Browser"); app.setApplicationVersion(JUME_BROWSER_VERSION);
    QCommandLineParser options; options.addHelpOption(); options.addVersionOption();
    options.addOptions({{"state-dir", "Private, persistent browser state (0700).", "path"},
        {"pointer-speed", "Full-stick cursor speed, 240..1400 pixels/sec.", "speed", "850"},
        {"scroll-speed", "Full-stick scroll speed, 200..1800 pixels/sec.", "speed", "1000"},
        {"windowed", "Host preview instead of fullscreen."},
        {"self-test", "Offline, disposable renderer smoke check; never reads a real profile."}});
    options.process(app);
    if (!options.positionalArguments().isEmpty() || geteuid() == 0) {
        qCritical("Jume Browser requires an unprivileged user and supported options only."); return 2;
    }
    const auto state = options.value("state-dir");
    if (!QDir::isAbsolutePath(state) || QDir::cleanPath(state) != state || state == "/") return 2;
    for (QString path = state; path != "/"; path = QFileInfo(path).absolutePath()) {
        if (QFileInfo(path).isSymLink()) return 2;
    }
    const QFileInfo info(state);
    if (!info.isDir() || info.ownerId() != geteuid()
        || (info.permissions() & (QFile::ReadGroup | QFile::WriteGroup | QFile::ExeGroup | QFile::ReadOther | QFile::WriteOther | QFile::ExeOther))) {
        qCritical("Create an owned, private state directory first."); return 2;
    }
    QLockFile lock(state + "/browser.lock");
    if (!lock.tryLock()) { qCritical("Browser profile already in use."); return 2; }
    for (const auto *child : {"profile", "cache", "config", "data"})
        if (QFileInfo(state + "/" + child).isSymLink()) return 2;
    qputenv("XDG_CONFIG_HOME", QFile::encodeName(state + "/config"));
    qputenv("XDG_CACHE_HOME", QFile::encodeName(state + "/cache"));
    qputenv("XDG_DATA_HOME", QFile::encodeName(state + "/data"));
    bool pointerOk = false, scrollOk = false;
    const double pointer = options.value("pointer-speed").toDouble(&pointerOk), scroll = options.value("scroll-speed").toDouble(&scrollOk);
    if (!pointerOk || !scrollOk || !(pointer >= 240 && pointer <= 1400 && scroll >= 200 && scroll <= 1800)) return 2;
    QFontDatabase::addApplicationFont(QCoreApplication::applicationDirPath() + "/../share/fonts/truetype/droid/DroidSansFallbackFull.ttf");
    ControllerInput controller;
    QQuickView view;
    BrowserInput input(&view, &controller); input.setSpeeds(pointer, scroll);
    input.selfTest = options.isSet("self-test");
    view.setTitle("Jume Browser"); view.setResizeMode(QQuickView::SizeRootObjectToView);
    view.rootContext()->setContextProperty("pad", &input);
    view.setInitialProperties({{"statePath", state}, {"selfTest", options.isSet("self-test")},
        {"versionText", "Jume Browser " + app.applicationVersion()
            + "\nQt WebEngine " + engineVersions["webEngine"].toString()
            + "\nChromium " + engineVersions["chromium"].toString()
            + "\nChromium 安全补丁基线 " + engineVersions["securityPatch"].toString()}});
    QObject::connect(view.engine(), &QQmlEngine::quit, &app, [&] {
        if (options.isSet("self-test")) {
            const auto pid = view.rootObject()->property("testRendererPid").toLongLong();
            QFile status(QString("/proc/%1/status").arg(pid));
            if (!status.open(QIODevice::ReadOnly)) { app.exit(6); return; }
            const auto data = status.readAll();
            if (!data.contains("NoNewPrivs:\t1") || !data.contains("Seccomp:\t2")) { qCritical("BROWSER_SANDBOX_FAILED"); app.exit(6); return; }
            qInfo("BROWSER_SANDBOX_OK");
            view.grabWindow().save(state + "/smoke.png");
        }
        app.quit();
    });
    QObject::connect(view.engine(), &QQmlEngine::exit, &app, &QCoreApplication::exit);
    view.setSource(QUrl("qrc:/browser/Browser.qml"));
    if (view.status() != QQuickView::Ready) return 1;
    view.resize(1024, 768);
    if (options.isSet("windowed")) view.show(); else view.showFullScreen();
    // This software cursor belongs to this window only; no global host pointer warping.
    QGuiApplication::setOverrideCursor(Qt::BlankCursor);
    if (options.isSet("self-test")) QTimer::singleShot(60000, &app, [&] {
        qCritical("BROWSER_SMOKE_TIMEOUT step=%d", view.rootObject()->property("testStep").toInt());
        view.grabWindow().save(state + "/timeout.png");
        QCoreApplication::exit(3);
    });
    return app.exec();
}
