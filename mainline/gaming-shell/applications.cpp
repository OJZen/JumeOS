#include "applications.h"
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QGuiApplication>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QSet>
#include <sys/stat.h>
#include <unistd.h>
#include <signal.h>
#include <QThread>

Applications::Applications(QObject *parent) : QObject(parent) {
    m_process.setStandardInputFile(QProcess::nullDevice());
    m_process.setStandardOutputFile(QProcess::nullDevice());
    m_process.setStandardErrorFile(QProcess::nullDevice());
    connect(&m_process, &QProcess::readyReadStandardOutput, this, [this] {
        const auto data = m_process.readAllStandardOutput();
        if (data.size() <= 8192) emit outputReady(data);
    });
    QProcess::UnixProcessParameters parameters;
    parameters.flags = QProcess::UnixProcessFlag::CreateNewSession;
    m_process.setUnixProcessParameters(parameters);
    m_stopTimer.setInterval(50);
    connect(&m_stopTimer, &QTimer::timeout, this, &Applications::advanceStop);
    connect(&m_process, &QProcess::stateChanged, this, &Applications::changed);
    connect(&m_process, &QProcess::started, this, [this] {
        m_group = m_process.processId();
        if (m_stopping) signalGroup(SIGTERM);
        emit started();
    });
    connect(&m_process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
        if (error == QProcess::FailedToStart) { m_stopTimer.stop(); fail(QStringLiteral("无法启动应用，请检查运行文件。")); emit finished(); }
    });
    connect(&m_process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
            [this](int code, QProcess::ExitStatus status) {
        m_exitCode = code;
        m_error = !m_stopping && (code != 0 || status == QProcess::CrashExit) ? QStringLiteral("应用异常结束，已返回桌面。") : QString();
        m_finishPending = true;
        // A launcher can exit before its ordinary children. Keep foreground ownership until they are gone.
        signalGroup(SIGTERM);
        if (!m_stopTimer.isActive()) { m_stopClock.start(); m_stopTimer.start(); }
        advanceStop();
    });
}
Applications::~Applications() {
    m_process.disconnect(this); m_stopTimer.stop();
    if (running()) {
        if (m_process.state() == QProcess::Starting) m_process.waitForStarted(1500);
        if (!m_group && m_process.state() == QProcess::Running) m_group = m_process.processId();
        signalGroup(SIGTERM);
        if (m_process.state() == QProcess::Running) m_process.terminate();
        else if (running()) m_process.kill();
        if (!m_process.waitForFinished(1500)) { m_process.kill(); m_process.waitForFinished(1500); }
        QElapsedTimer grace; grace.start();
        while (m_group && ::kill(-pid_t(m_group), 0) == 0 && grace.elapsed() < 1500) QThread::msleep(10);
        signalGroup(SIGKILL);
    }
}
bool Applications::fail(const QString &message) { m_error = message; m_exitCode = -1; emit changed(); return false; }
bool Applications::load(const QString &path) {
    if (running() || !QDir::isAbsolutePath(path)) return fail(QStringLiteral("应用列表路径无效。"));
    struct stat info{};
    if (::lstat(QFile::encodeName(path).constData(), &info) != 0 || !S_ISREG(info.st_mode) ||
        (info.st_uid != geteuid() && info.st_uid != 0) || (info.st_mode & 0022) || info.st_size > 524288)
        return fail(QStringLiteral("应用列表不可读或权限不安全。"));
    QFile file(path);
    if (!file.open(QIODevice::ReadOnly)) return fail(QStringLiteral("无法读取应用列表。"));
    const auto document = QJsonDocument::fromJson(file.readAll());
    const auto object = document.object();
    if (!document.isObject() || object.value("version") != QJsonValue(1) || !object.value("applications").isArray() ||
        object.size() != 2 || object.value("applications").toArray().size() > 512)
        return fail(QStringLiteral("应用列表格式不正确。"));
    QList<Entry> entries; QVariantList items; QSet<QString> ids;
    const QStringList colors{"#3159a2", "#9c573e", "#386c72", "#667948", "#805779", "#397d91"};
    const auto validText = [](const QJsonValue &value, int maximum, bool allowEmpty = false) {
        return value.isString() && (allowEmpty || !value.toString().isEmpty()) && value.toString().size() <= maximum &&
            !value.toString().contains(QRegularExpression("[\\x00-\\x1f\\x7f]"));
    };
    for (const auto &value : object.value("applications").toArray()) {
        const auto item = value.toObject();
        const auto id = item.value("id").toString();
        bool valid = value.isObject() && QRegularExpression("^[a-z0-9][a-z0-9._-]{0,63}$").match(id).hasMatch() && !ids.contains(id)
            && validText(item.value("title"), 64) && validText(item.value("program"), 4096)
            && QDir::isAbsolutePath(item.value("program").toString()) && item.value("arguments").isArray()
            && item.value("arguments").toArray().size() <= 64;
        for (auto it = item.begin(); it != item.end(); ++it)
            if (!QStringList{"id", "title", "description", "program", "arguments", "directory"}.contains(it.key())) valid = false;
        if (item.contains("description") && !validText(item.value("description"), 96, true)) valid = false;
        if (item.contains("directory") && (!validText(item.value("directory"), 4096) || !QDir::isAbsolutePath(item.value("directory").toString()))) valid = false;
        Entry entry{id, item.value("program").toString(), item.value("directory").toString(), {}};
        for (const auto &argument : item.value("arguments").toArray()) {
            if (!argument.isString() || argument.toString().size() > 4096 || argument.toString().contains(QChar(0))) valid = false;
            entry.arguments.append(argument.toString());
        }
        if (!valid) return fail(QStringLiteral("应用列表第 %1 项无效或标识重复。").arg(entries.size() + 1));
        ids.insert(id); entries.append(entry);
        items.append(QVariantMap{{"id", id}, {"title", item.value("title").toString()},
            {"detail", item.value("description").toString(QStringLiteral("应用"))},
            {"color", colors[items.size() % colors.size()]}});
    }
    m_entries = entries; m_items = items; m_hasManifest = true; m_error.clear(); return true;
}
bool Applications::launch(int index) {
    if (running()) return false;
    if (index < 0 || index >= m_entries.size()) return fail(QStringLiteral("未找到此应用。"));
    const auto &entry = m_entries[index];
    auto environment = QProcessEnvironment::systemEnvironment();
    // Do not inject the shell's private Qt/SDL runtime into another application.
    for (const auto *name : {"LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "QT_PLUGIN_PATH", "QML_IMPORT_PATH", "QML2_IMPORT_PATH", "QT_IM_MODULE", "R46H_VIRTUAL_KEYBOARD",
                            "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "R46H_SHELL_LOG", "QML_DISABLE_DISK_CACHE",
                            "QT_DISABLE_SHADER_DISK_CACHE", "QT_SHADER_CACHE_PATH", "QSG_INFO", "QSG_RENDER_TIMING"})
        environment.remove(QString::fromLatin1(name));
    return launchPrepared(entry.id, entry.program, entry.arguments, entry.directory, environment);
}
bool Applications::launchPrepared(const QString &id, const QString &path, const QStringList &arguments,
                                  const QString &directory, QProcessEnvironment environment, bool captureOutput) {
    if (running()) return false;
    m_activeId = id;
    const auto platform = QGuiApplication::platformName();
    if (platform != "cocoa" && platform != "xcb" && platform != "offscreen" && !platform.startsWith("wayland"))
        return fail(QStringLiteral("当前显示模式暂不支持启动外部应用。"));
    const QFileInfo program(path);
    if (!program.isAbsolute() || !program.isFile() || !program.isExecutable() || (!directory.isEmpty() && !QFileInfo(directory).isDir()))
        return fail(QStringLiteral("运行文件或工作目录不可用。"));
    environment.remove("R46H_DEVICE_CONTROLS"); // The temporary settings lease belongs to the desktop.
    if (m_routedInput) {
        // Input ownership is enforced by the broker, including when a game lacks keyboard focus.
        environment.insert("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1");
        // GUID observed from the actual uinput endpoint, not copied from the physical bridge.
        environment.insert("SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT", "0x5246/0x0049");
        environment.remove("SDL_GAMECONTROLLER_IGNORE_DEVICES");
        environment.insert("SDL_GAMECONTROLLERCONFIG", "06001d11465200004900000001000000,R46H Routed Gamepad,a:b1,b:b0,x:b2,y:b3,back:b8,start:b9,leftshoulder:b4,rightshoulder:b5,lefttrigger:b6,righttrigger:b7,leftstick:b14,rightstick:b15,leftx:a0,lefty:a1,rightx:a2,righty:a3,dpup:b10,dpdown:b11,dpleft:b12,dpright:b13,platform:Linux,");
    }
    m_process.setProcessEnvironment(environment);
    m_process.setStandardOutputFile(captureOutput ? QString() : QProcess::nullDevice());
    m_process.setWorkingDirectory(directory.isEmpty() ? program.absolutePath() : directory);
    m_stopTimer.stop(); m_finishPending = false; m_error.clear(); m_exitCode = 0; m_stopping = false;
    emit changed();
    m_process.start(path, arguments); return true;
}
void Applications::stop() {
    if (!running()) return;
    m_stopping = true;
    signalGroup(SIGTERM);
    if (!m_stopTimer.isActive()) m_stopClock.start();
    m_stopTimer.start();
}
void Applications::signalGroup(int signal) {
    // The PGID is the QProcess child created by setsid(), never an externally supplied PID.
    // ponytail: covers ordinary children; the target session cgroup owns detached descendants.
    if (m_group > 1) (void)::kill(-pid_t(m_group), signal);
}
void Applications::advanceStop() {
    if (m_group && ::kill(-pid_t(m_group), 0) < 0 && errno == ESRCH) m_group = 0;
    if (m_stopClock.isValid() && m_stopClock.elapsed() >= 1500) {
        signalGroup(SIGKILL);
        if (m_process.state() != QProcess::NotRunning) m_process.kill();
    }
    if (!m_group && m_process.state() == QProcess::NotRunning && m_finishPending) {
        m_stopTimer.stop(); m_finishPending = false; emit changed(); emit finished();
    }
}
