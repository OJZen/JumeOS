#include "window.h"
#include "preview.h"
#include "input.h"
#include "appearance.h"
#include "transfer.h"
#include <QApplication>
#include <QCommandLineParser>
#include <QDir>
#include <QFileInfo>
#include <QLockFile>
#include <QImageReader>
#include <QStandardPaths>
#include <QFontDatabase>
#include <QThreadPool>
#include <unistd.h>

int main(int argc, char **argv) {
    // Local files only. Media containers must not start network protocol readers.
    qputenv("QT_FFMPEG_PROTOCOL_WHITELIST", "file,pipe");
    qputenv("SDL_NO_SIGNAL_HANDLERS", "1");
    QApplication app(argc, argv);
    app.setApplicationName("JumeFiles");
    app.setApplicationVersion("0.1.0-dev");
    app.setStyle("Fusion");
    QFontDatabase::addApplicationFont(QCoreApplication::applicationDirPath() +
                                      "/../share/fonts/truetype/droid/DroidSansFallbackFull.ttf");
    QImageReader::setAllocationLimit(64);
    QThreadPool::globalInstance()->setMaxThreadCount(2); // Bound overlapping decode/copy work on the 1 GiB target.
    filesAppearance();
    QCommandLineParser args;
    args.addHelpOption();
    args.addOptions({{"state-dir", "Private application state directory", "path"},
                     {"directory", "Initial directory", "path", QDir::homePath()},
                     {"editor", "Start a blank text editor"},
                     {"transfer", "Start temporary Wi-Fi file sharing"},
                     {"windowed", "Host preview"}});
    args.process(app);
    if (geteuid() == 0)
        return 2;
    const auto state = args.value("state-dir");
    if (!QDir::isAbsolutePath(state) || QDir::cleanPath(state) != state || state == "/")
        return 2;
    for (QString p = state; p != "/"; p = QFileInfo(p).absolutePath())
        if (QFileInfo(p).isSymLink())
            return 2;
    if (!QDir().mkpath(state) || QFileInfo(state).ownerId() != geteuid())
        return 2;
    QFile::setPermissions(state, QFileDevice::ReadOwner | QFileDevice::WriteOwner | QFileDevice::ExeOwner);
    QMap<QString, QString> directories;
    for (const auto &p :
         QList<QPair<QString, QStandardPaths::StandardLocation>>{{"文档", QStandardPaths::DocumentsLocation},
                                                                 {"下载", QStandardPaths::DownloadLocation},
                                                                 {"图片", QStandardPaths::PicturesLocation},
                                                                 {"音乐", QStandardPaths::MusicLocation},
                                                                 {"视频", QStandardPaths::MoviesLocation}})
        directories[p.first] = QStandardPaths::writableLocation(p.second);
    directories["回收站"] = QStandardPaths::writableLocation(QStandardPaths::GenericDataLocation) + "/Trash/files";
    // Keep GenericDataLocation global: QFile's XDG trash must not become app cache.
    for (const auto &p : QList<QPair<const char *, QString>>{{"XDG_CONFIG_HOME", state + "/config"},
                                                             {"XDG_CACHE_HOME", state + "/cache"}}) {
        if (QFileInfo(p.second).isSymLink() || !QDir().mkpath(p.second))
            return 2;
        qputenv(p.first, QFile::encodeName(p.second));
    }
    QLockFile lock(state + (args.isSet("transfer") ? "/transfer.lock"
                            : args.isSet("editor") ? "/editor.lock"
                                                   : "/files.lock"));
    if (!lock.tryLock(0))
        return 3;
    if (args.isSet("transfer")) {
        TransferWindow transfer(directories.value("下载", QDir::homePath() + "/Downloads") + "/Jume Transfer");
        ControllerInput controller;
        QObject::connect(&controller, &ControllerInput::action, &transfer, [&](const QString &action, bool) {
            if (app.applicationState() == Qt::ApplicationActive)
                transfer.controllerAction(action);
        });
        if (args.isSet("windowed"))
            transfer.show();
        else
            transfer.showFullScreen();
        return app.exec();
    }
    if (args.isSet("editor")) {
        Preview editor({}, true);
        editor.setProperty("saveDirectory", directories.value("文档"));
        if (args.isSet("windowed"))
            editor.show();
        else
            editor.showFullScreen();
        return app.exec();
    }
    FileWindow window(state, args.value("directory"), directories);
    ControllerInput controller;
    QObject::connect(&controller, &ControllerInput::action, &window, [&](const QString &name, bool) {
        if (app.applicationState() == Qt::ApplicationActive)
            window.controllerAction(name);
    });
    if (args.isSet("windowed"))
        window.show();
    else
        window.showFullScreen();
    return app.exec();
}
