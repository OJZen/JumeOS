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
#include <algorithm>

struct Applications::Task {
    QString id, title, icon;
    QProcess process;
    QElapsedTimer stopClock;
    QImage preview;
    qint64 group = 0;
    int slot = 0, code = 0, revision = 0;
    bool stopping = false, done = false, failed = false, paused = false;
};
Applications::Applications(QObject *parent) : QObject(parent) {
    m_stopTimer.setInterval(50);
    connect(&m_stopTimer, &QTimer::timeout, this, &Applications::advanceStop);
}
Applications::~Applications() {
    m_stopTimer.stop();
    for (auto *task : m_tasks) {
        task->process.disconnect(this);
        if (task->process.state() == QProcess::Starting) task->process.waitForStarted(1500);
        if (!task->group) task->group = task->process.processId();
        signalGroup(task, SIGKILL); task->process.kill(); task->process.waitForFinished(1500);
        delete task;
    }
}
QString Applications::activeId() const { return m_active ? m_active->id : QString(); }
qint64 Applications::processId() const { return m_active ? m_active->process.processId() : 0; }
int Applications::inputSlot() const { return m_active ? m_active->slot : 0; }
bool Applications::contains(const QString &id) const { for (auto *t : m_tasks) if (t->id == id) return true; return false; }
QVariantList Applications::tasks() const {
    QVariantList result;
    for (auto *t : m_tasks) result.append(QVariantMap{{"id",t->id},{"title",t->title},{"icon",t->icon},
        {"foreground",t==m_active},{"paused",t->paused},{"stopping",t->stopping||t->done},
        {"preview",t->preview.isNull()?QString():QString("image://tasks/%1/%2").arg(t->id).arg(t->revision)}});
    return result;
}
QImage Applications::thumbnail(const QString &id) const { for (auto *t:m_tasks) if(t->id==id)return t->preview; return {}; }
void Applications::setThumbnail(const QString &id,qint64 pid,const QImage &image) {
    for(auto *t:m_tasks) if(t->id==id && !t->stopping && !t->done && t->process.processId()==pid && !image.isNull()) {
        t->preview=image.scaled(320,240,Qt::KeepAspectRatio,Qt::SmoothTransformation);++t->revision;emit changed();return;
    }
}
void Applications::suspend(Task *t,bool paused) {
    // Utility jobs keep copying/transferring; games and arbitrary manifests pause.
    if (QStringList{"builtin.files","builtin.text","builtin.transfer","builtin.browser","builtin.terminal"}.contains(t->id)) return;
    if(t->paused==paused)return;
    t->paused=paused;signalGroup(t,paused?SIGSTOP:SIGCONT);
}
void Applications::background() {
    if(!m_active)return;
    suspend(m_active,true);m_active=nullptr;emit changed();
}
bool Applications::activate(const QString &id) {
    for(auto *t:m_tasks) if(t->id==id) {
        if(t->stopping||t->done||m_active==t)return false;
        if(m_active && m_active!=t)suspend(m_active,true);
        m_active=t;suspend(t,false);m_error.clear();m_exitCode=0;emit changed();return true;
    }
    return false;
}
bool Applications::fail(const QString &message) { m_error = message; m_exitCode = -1; emit changed();emit notice(message);return false; }
bool Applications::load(const QString &path) {
    if (hasTasks() || !QDir::isAbsolutePath(path)) return fail(QStringLiteral("应用列表路径无效。"));
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
    if (contains(id)) return activate(id);
    if (m_tasks.size() >= 4) return fail(QStringLiteral("最多保留 4 个应用，请先关闭一个后台任务。"));
    if (m_routedInput) {
        QFile memory("/proc/meminfo");
        if(!memory.open(QIODevice::ReadOnly))return fail(QStringLiteral("无法确认可用内存，请稍后重试。"));
        const auto match=QRegularExpression("(?:^|\\n)MemAvailable:\\s+(\\d+)\\s+kB(?:\\n|$)").match(QString::fromLatin1(memory.readAll()));
        if(!match.hasMatch())return fail(QStringLiteral("无法确认可用内存，请稍后重试。"));
        if(match.captured(1).toLongLong()<128*1024)
            return fail(QStringLiteral("可用内存不足 128 MiB，请先关闭后台应用。"));
    }
    const auto platform = QGuiApplication::platformName();
    if (platform != "cocoa" && platform != "xcb" && platform != "offscreen" && !platform.startsWith("wayland"))
        return fail(QStringLiteral("当前显示模式暂不支持启动外部应用。"));
    const QFileInfo program(path);
    if (!program.isAbsolute() || !program.isFile() || !program.isExecutable() || (!directory.isEmpty() && !QFileInfo(directory).isDir()))
        return fail(QStringLiteral("运行文件或工作目录不可用。"));
    auto *task=new Task;task->id=id;
    const QHash<QString,QStringList> labels{{"builtin.files",{"文件管理器","folder"}},{"builtin.text",{"文本编辑器","document"}},
        {"builtin.transfer",{"文件传输","folder"}},{"builtin.browser",{"Jume Browser","monitor"}},
        {"builtin.terminal",{"终端","terminal"}},{"builtin.moonlight",{"Moonlight","monitor"}},
        {"native.gta3",{"GTA III","gamepad"}},{"native.gtavc",{"GTA: Vice City","gamepad"}},
        {"native.mslug",{"Metal Slug","cartridge"}},{"native.stardew",{"Stardew Valley","gamepad"}}};
    const auto label=labels.value(id,{id,QStringLiteral("gamepad")});task->title=label[0];task->icon=label[1];
    for(const auto &item:m_items)if(item.toMap().value("id")==id)task->title=item.toMap().value("title").toString();
    while(std::any_of(m_tasks.begin(),m_tasks.end(),[&](Task *t){return t->slot==task->slot;}))++task->slot;
    environment.remove("R46H_DEVICE_CONTROLS"); // The temporary settings lease belongs to the desktop.
    if (m_routedInput) {
        // Input ownership is enforced by the broker, including when a game lacks keyboard focus.
        environment.insert("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1");
        // GUID observed from the actual uinput endpoint, not copied from the physical bridge.
        environment.insert("SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT", QString("0x5246/0x%1").arg(0x49+task->slot,4,16,QChar('0')));
        environment.remove("SDL_GAMECONTROLLER_IGNORE_DEVICES");
        environment.insert("SDL_GAMECONTROLLERCONFIG", QString("06001d1146520000%1").arg(0x49+task->slot,2,16,QChar('0'))+
            "00000001000000,R46H Routed Gamepad,a:b1,b:b0,x:b2,y:b3,back:b8,start:b9,leftshoulder:b4,rightshoulder:b5,lefttrigger:b6,righttrigger:b7,leftstick:b14,rightstick:b15,leftx:a0,lefty:a1,rightx:a2,righty:a3,dpup:b10,dpdown:b11,dpleft:b12,dpright:b13,platform:Linux,");
    }
    auto &process=task->process;
    process.setStandardInputFile(QProcess::nullDevice());process.setStandardErrorFile(QProcess::nullDevice());
    process.setStandardOutputFile(captureOutput ? QString() : QProcess::nullDevice());
    process.setProcessEnvironment(environment);process.setWorkingDirectory(directory.isEmpty()?program.absolutePath():directory);
    QProcess::UnixProcessParameters parameters;parameters.flags=QProcess::UnixProcessFlag::CreateNewSession;
    process.setUnixProcessParameters(parameters);
    connect(&process,&QProcess::readyReadStandardOutput,this,[this,task]{const auto data=task->process.readAllStandardOutput();if(task->id=="builtin.moonlight" && data.size()<=8192)emit outputReady(data);});
    connect(&process,&QProcess::started,this,[this,task]{task->group=task->process.processId();if(task->stopping)signalGroup(task,SIGKILL);else if(task->paused)signalGroup(task,SIGSTOP);emit changed();emit started();});
    connect(&process,&QProcess::errorOccurred,this,[this,task](QProcess::ProcessError error){
        if(error==QProcess::FailedToStart){task->done=true;task->failed=true;task->code=-1;complete(task);}
    });
    connect(&process,qOverload<int,QProcess::ExitStatus>(&QProcess::finished),this,[this,task](int code,QProcess::ExitStatus status){
        task->code=code;task->failed=!task->stopping&&(code!=0||status==QProcess::CrashExit);task->done=true;
        signalGroup(task,SIGTERM);task->stopClock.start();m_stopTimer.start();emit changed();
    });
    if(m_active)suspend(m_active,true);
    m_tasks.append(task);m_active=task;m_error.clear();m_exitCode=0;
    emit changed();process.start(path,arguments);return true;
}
void Applications::stop() {
    if(!m_active)return;
    m_active->stopping=true;suspend(m_active,false);signalGroup(m_active,SIGTERM);
    m_active->stopClock.start();m_stopTimer.start();emit changed();
}
void Applications::stopAll() {
    for(auto *t:m_tasks){t->stopping=true;suspend(t,false);signalGroup(t,SIGTERM);t->stopClock.start();}
    m_stopTimer.start();emit changed();
}
void Applications::forceKill(const QString &id) {
    const auto selected=id.isEmpty()?activeId():id;
    for(auto *t:m_tasks)if(t->id==selected){t->stopping=true;signalGroup(t,SIGKILL);t->process.kill();t->stopClock.start();m_stopTimer.start();emit changed();return;}
}
void Applications::requestClose(const QString &id) {
    if(!id.isEmpty()&&id!=activeId()&&!activate(id))return;
    if(m_active && !m_active->stopping)emit closeRequested(processId());
}
void Applications::signalGroup(Task *task,int signal) {
    // The PGID is the QProcess child created by setsid(), never an externally supplied PID.
    // ponytail: covers ordinary children; the target session cgroup owns detached descendants.
    if (task->group > 1) (void)::kill(-pid_t(task->group), signal);
}
void Applications::advanceStop() {
    const auto tasks=m_tasks;bool pending=false;
    for(auto *t:tasks) {
        if(t->group && ::kill(-pid_t(t->group),0)<0 && errno==ESRCH)t->group=0;
        if(t->stopClock.isValid()&&t->stopClock.elapsed()>=1500){signalGroup(t,SIGKILL);if(t->process.state()!=QProcess::NotRunning)t->process.kill();}
        if(t->done&&!t->group&&t->process.state()==QProcess::NotRunning)complete(t);
        else pending|=t->stopClock.isValid();
    }
    if(!pending)m_stopTimer.stop();
}
void Applications::complete(Task *t) {
    const bool foreground=m_active==t;const auto id=t->id;const int code=t->code;const bool failed=t->failed;
    if(foreground){m_active=nullptr;m_exitCode=code;m_error=failed?QStringLiteral("应用异常结束，已返回桌面。"):QString();}
    if(failed)emit notice(QStringLiteral("%1 已异常退出，其他任务已保留。").arg(t->title));
    m_tasks.removeOne(t);t->process.disconnect(this);
    // QProcess can still be emitting finished/errorOccurred; dispose after delivery.
    QTimer::singleShot(0,this,[t]{delete t;});
    emit changed();emit taskFinished(id,code,failed);if(foreground)emit finished();
}
