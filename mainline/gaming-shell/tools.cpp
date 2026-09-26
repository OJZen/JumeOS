#include "tools.h"
#include "device.h"
#include "usbgamepad.h"
#include <QCoreApplication>
#include <QCryptographicHash>
#include <QDateTime>
#include <QDirIterator>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSaveFile>
#include <QRegularExpression>
#include <QStandardPaths>
#include <QUuid>
#include <cmath>
#include <cerrno>
#include <cstdio>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <unistd.h>

namespace {
struct Port { QString id, title, directory, save; QStringList required; };
const QList<Port> ports {
    {"stardew", QStringLiteral("星露谷物语"), "stardewvalley1615", "savedata", {"SVLoader.exe", "dlls/StardewPatches.dll", "gamedata/Stardew Valley.exe", "gamedata/Content"}},
    {"gta3", "GTA III", "gta3", "userfiles", {"re3", "data", "models"}},
    {"gtavc", "GTA Vice City", "gtavc", "userfiles", {"reVC", "data", "models"}},
    {"gtasa", QStringLiteral("GTA 圣安地列斯"), "gtasa_zh", "savegames", {"gtasa", "libGTASA.so", "assets"}}
};
const QStringList saSaves {"GTASAsf*.b", "gta_sa.set", "CINFO.BIN"};
const QString core = "/usr/local/libexec/fbneo_neogeo_libretro.so";
const QString romHash = "3ebe7ca4166f956a65ae98d86f9172f8b5d4462efa13723a5ea72fcf59adcbf8";
const QString biosHash = "d2d8ab5d5fc5ce41978e40c8db2984d8dd0a37e60c712e20961b80fdbb4c9936";
const QString coreHash = "8bb17a551f3eeeb384ab00a5c5375d30eb63807afe5b6c1ba1d3f78220732bdb";

QString pythonProgram() {
    const QFileInfo bundled(QCoreApplication::applicationDirPath() + "/python3.13");
    if (!bundled.exists() && !bundled.isSymLink())
        return QFileInfo::exists(QCoreApplication::applicationDirPath() + "/../share/r46h/ports/manager.py") ? QString() : QStandardPaths::findExecutable("python3");
    if (!bundled.isFile() || bundled.isSymLink() || !bundled.isExecutable()
        || (bundled.ownerId() != 0 && bundled.ownerId() != geteuid())
        || bundled.permissions().testFlag(QFile::WriteGroup) || bundled.permissions().testFlag(QFile::WriteOther)) return {};
    return bundled.absoluteFilePath();
}

bool privateDirectory(const QString &path) {
    if (!QDir::isAbsolutePath(path)) return false;
    const auto bytes = QFile::encodeName(path); struct stat st{};
    if (::lstat(bytes, &st) != 0) { if (::mkdir(bytes, 0700) != 0) return false; if (::lstat(bytes, &st) != 0) return false; }
    return S_ISDIR(st.st_mode) && st.st_uid == geteuid() && (st.st_mode & 077) == 0;
}
bool privateFile(const QString &path, bool absent = false) {
    struct stat st{};
    if (::lstat(QFile::encodeName(path), &st) != 0) return absent && errno == ENOENT;
    return S_ISREG(st.st_mode) && st.st_uid == geteuid() && (st.st_mode & 077) == 0;
}
bool ownedTools(const QString &state) {
    const QFileInfo parent(state);
    return QDir::isAbsolutePath(state) && !parent.isSymLink() && QDir().mkpath(state)
        && QFileInfo(state).ownerId() == geteuid() && privateDirectory(state + "/tools");
}
bool writeJson(const QString &path, const QJsonObject &object) {
    if (!privateFile(path, true)) return false;
    QSaveFile file(path); const auto bytes = QJsonDocument(object).toJson();
    if (!file.open(QIODevice::WriteOnly)) return false;
    file.setPermissions(QFile::ReadOwner | QFile::WriteOwner);
    return file.write(bytes) == bytes.size() && file.commit();
}
QJsonObject readJson(const QString &path) {
    if (!privateFile(path)) return {};
    QFile file(path); if (!file.open(QIODevice::ReadOnly) || file.size() > 32768) return {};
    return QJsonDocument::fromJson(file.readAll()).object();
}
bool contained(const QString &root, const QString &path) {
    const QString base = QFileInfo(root).canonicalFilePath(), actual = QFileInfo(path).canonicalFilePath();
    return !base.isEmpty() && !actual.isEmpty() && actual.startsWith(base + "/") && !QFileInfo(path).isSymLink();
}
QString hash(const QString &path) {
    QFile file(path); if (!file.open(QIODevice::ReadOnly)) return {};
    QCryptographicHash digest(QCryptographicHash::Sha256);
    return digest.addData(&file) ? QString::fromLatin1(digest.result().toHex()) : QString();
}
bool matches(const QString &path, qint64 size, const QString &digest) {
    const QFileInfo file(path);
    return file.isFile() && !file.isSymLink() && file.size() == size && hash(path) == digest;
}
int saveCount(const QString &root) {
    if (!QFileInfo(root).isDir() || QFileInfo(root).isSymLink()) return 0;
    QDirIterator it(root, QDir::Files | QDir::NoSymLinks, QDirIterator::Subdirectories); int count = 0;
    while (it.hasNext() && count < 2048) { it.next(); if (it.fileName() != "r46h-copy-receipt.json" && it.fileName() != ".gitkeep") ++count; }
    return count;
}
QVariantMap toolError(const QString &message) { return {{"ok", false}, {"message", message}}; }
QVariantMap copySaves(const QString &content, const QString &state, const QString &id, bool backup) {
    if (!ownedTools(state)) return toolError(QStringLiteral("存档目录不可写，原文件未改动。"));
    const Port *port = nullptr; for (const auto &p : ports) if (p.id == id) port = &p;
    if (!port && id != "mslug") return toolError(QStringLiteral("未找到这个游戏。"));
    const QString tools = state + "/tools", managed = tools + "/ports", game = managed + "/" + id;
    if (!privateDirectory(managed) || !privateDirectory(game)) return toolError(QStringLiteral("游戏存档目录权限不正确。"));
    QString source;
    if (backup) source = game + "/saves";
    else if (port) source = content + "/ports/" + port->directory + "/" + port->save;
    else return toolError(QStringLiteral("Neo 只备份本工具管理的存档。"));
    QString parent = game, destination = game + "/saves";
    bool initializedStardew = false;
    if (!backup && id == "stardew" && (QFileInfo(destination).exists() || QFileInfo(destination).isSymLink())) {
        if (!privateDirectory(destination)) return toolError(QStringLiteral("已有存档，未覆盖。请先备份并检查。"));
        const auto entries = QDir(destination).entryInfoList(QDir::AllEntries | QDir::NoDotAndDotDot | QDir::Hidden | QDir::System);
        if (entries.size() > 1 || (entries.size() == 1 && (entries.first().fileName() != "startup_preferences" || !privateFile(entries.first().filePath()))))
            return toolError(QStringLiteral("已有存档，未覆盖。请先备份并检查。"));
        source += "/Saves"; parent = destination; destination += "/Saves"; initializedStardew = true;
    }
    QStringList paths;
    if (QFileInfo(source).isSymLink()) return toolError(QStringLiteral("存档包含不安全的链接，未导入。"));
    if (!backup && QFileInfo(source).exists() && !contained(content, source)) return toolError(QStringLiteral("原存档路径不在资源目录内。"));
    QDirIterator it(source, QDir::Files | QDir::Dirs | QDir::Hidden | QDir::System | QDir::NoDotAndDotDot, QDirIterator::Subdirectories);
    qint64 bytes = 0;
    while (it.hasNext()) {
        const QString path = it.next(); const auto info = it.fileInfo();
        if (info.isSymLink()) return toolError(QStringLiteral("存档包含链接，未改动任何已有存档。"));
        if (!info.isFile()) continue;
        if (info.fileName() == "r46h-copy-receipt.json" || info.fileName() == ".gitkeep") continue;
        paths.append(path); bytes += info.size();
        if (paths.size() > 2048 || bytes > 64 * 1024 * 1024) return toolError(QStringLiteral("存档超过本次导入上限，原文件已保留。"));
    }
    // This original SA package also stores saves directly beside the executable.
    if (!backup && id == "gtasa") {
        const QString base = content + "/ports/gtasa_zh";
        for (const auto &name : QDir(base).entryList(saSaves, QDir::Files)) {
            const QString path = base + "/" + name;
            if (!contained(content, path)) return toolError(QStringLiteral("原存档路径不安全。"));
            paths.append(path); bytes += QFileInfo(path).size();
        }
    }
    if (paths.isEmpty()) return toolError(QStringLiteral("没有找到可复制的存档。"));
    if (paths.size() > 2048 || bytes > 64 * 1024 * 1024) return toolError(QStringLiteral("存档超过导入上限。"));
    if (backup) {
        parent = tools + "/backups";
        if (!privateDirectory(parent)) return toolError(QStringLiteral("备份目录不可用。"));
        destination = parent + "/" + id + "-" + QDateTime::currentDateTimeUtc().toString("yyyyMMddTHHmmsszzz") + "-" + QUuid::createUuid().toString(QUuid::Id128).left(8);
    }
    if (QFileInfo(destination).exists() || QFileInfo(destination).isSymLink()) return toolError(QStringLiteral("已有存档，未覆盖。请先备份并检查。"));
    const QString incoming = parent + "/.incoming-" + QUuid::createUuid().toString(QUuid::Id128);
    if (!privateDirectory(incoming)) return toolError(QStringLiteral("无法创建存档副本。"));
    QJsonArray entries; bool ok = true;
    for (const auto &path : paths) {
        QString name = QDir(source).relativeFilePath(path);
        if (name.startsWith("../")) name = QFileInfo(path).fileName();
        const auto before = QFileInfo(path); const auto modified = before.lastModified(); const auto size = before.size();
        const QString target = incoming + "/" + name;
        if (!QDir().mkpath(QFileInfo(target).absolutePath()) || !QFile::copy(path, target)) { ok = false; break; }
        QFile(target).setPermissions(QFile::ReadOwner | QFile::WriteOwner);
        const auto digest = hash(target);
        if (digest.isEmpty() || digest != hash(path) || QFileInfo(path).size() != size || QFileInfo(path).lastModified() != modified) { ok = false; break; }
        entries.append(QJsonObject{{"name", name}, {"bytes", size}, {"sha256", digest}});
    }
    const QJsonObject receipt{{"version", 1}, {"game", id}, {"files", entries}};
    if (ok && !initializedStardew) ok = writeJson(incoming + "/r46h-copy-receipt.json", receipt);
    if (ok) ok = QDir().rename(incoming, destination);
    if (!ok) { QDir(incoming).removeRecursively(); return toolError(QStringLiteral("复制未完成，原存档和已有存档均已保留。")); }
    if (initializedStardew && !writeJson(parent + "/r46h-copy-receipt.json", receipt))
        return toolError(QStringLiteral("原存档已导入，但收据未写入。请先检查，不要重复导入。"));
    return {{"ok", true}, {"message", backup ? QStringLiteral("存档已备份") : QStringLiteral("原存档已导入副本")}, {"files", paths.size()}};
}
}

QVariantMap ToolState::defaults() { return {{"neoIntegerScale", false}, {"neoSmooth", false}, {"usbSwapAB", false}, {"usbSwapXY", false}, {"usbInvertRightY", false}, {"usbDeadzone", 10}}; }
bool ToolState::validSettings(const QVariantMap &settings) {
    const auto expected = defaults(); if (settings.size() != expected.size()) return false;
    for (auto it = expected.begin(); it != expected.end(); ++it) {
        const auto v = settings.value(it.key());
        if (it.key() == "usbDeadzone") {
            bool ok = false; const double n = v.toDouble(&ok);
            if (!ok || (v.metaType().id() == QMetaType::QString || v.metaType().id() == QMetaType::Bool) || !std::isfinite(n) || n != std::floor(n) || n < 0 || n > 30 || int(n) % 5) return false;
        } else if (v.metaType().id() != QMetaType::Bool) return false;
    }
    return true;
}
ToolState::ToolState(QString state, QString content, bool target, bool nativeEnabled, QObject *parent)
    : QObject(parent), m_stateDirectory(std::move(state)), m_contentRoot(QDir::cleanPath(content)), m_settings(defaults()), m_target(target), m_nativeEnabled(nativeEnabled) {
    const QString path = m_stateDirectory + "/tools/settings.json";
    struct stat st{};
    if (::lstat(QFile::encodeName(path), &st) == 0) {
        const auto object = readJson(path); const auto values = object.value("settings").toObject().toVariantMap();
        if (object.size() != 2 || object.value("version") != QJsonValue(1) || !validSettings(values)) { m_loadFailed = true; m_error = QStringLiteral("工具配置无法读取，原文件已保留。"); }
        else m_settings = values;
    } else if (errno != ENOENT && errno != ENOTDIR) { m_loadFailed = true; m_error = QStringLiteral("工具配置不可读，原文件已保留。"); }
    const auto nativeResult = readJson(m_stateDirectory + "/tools/native-result.json");
    if (nativeResult.value("version") == QJsonValue(1) && QStringList{"mslug", "gta3", "gtavc", "stardew"}.contains(nativeResult.value("game").toString())) {
        m_lastGame = nativeResult.value("game").toString();
        m_resultMessage = nativeResult.value("exit").toInt(-1) == 0 ? QStringLiteral("游戏已结束") : QStringLiteral("游戏未正常结束，可检查后重试。");
    }
    m_process.setStandardInputFile(QProcess::nullDevice()); m_process.setStandardErrorFile(QProcess::nullDevice());
    m_deadline.setSingleShot(true); m_deadline.setInterval(20000);
    connect(&m_deadline, &QTimer::timeout, this, [this] { m_timedOut = true; m_process.kill(); });
    connect(&m_process, &QProcess::stateChanged, this, &ToolState::changed);
    m_cancelDeadline.setSingleShot(true); m_cancelDeadline.setInterval(15000);
    connect(&m_cancelDeadline, &QTimer::timeout, &m_process, &QProcess::kill);
    connect(&m_process, &QProcess::readyReadStandardOutput, this, &ToolState::readOutput);
    connect(&m_process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError e) { if (e == QProcess::FailedToStart) { m_deadline.stop(); fail(QStringLiteral("无法启动工具检查。")); } });
    connect(&m_process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this, [this](int code, QProcess::ExitStatus status) {
        m_deadline.stop(); m_cancelDeadline.stop(); readOutput();
        const bool backend = m_backend; const QString completed = m_operation;
        const auto object = backend ? QJsonObject::fromVariantMap(m_backendResult) : QJsonDocument::fromJson(m_output).object();
        if (m_timedOut || status != QProcess::NormalExit || m_output.size() > 65536 || !object.value("ok").isBool()) fail(QStringLiteral("工具操作未完成，请刷新检查结果。"));
        else if (code != 0 || !object.value("ok").toBool()) fail(object.value("message").toString(QStringLiteral("操作未完成，原数据已保留。")));
        else {
            if (!m_loadFailed) m_error.clear();
            if (backend) {
                if (completed == "catalog") m_catalogInfo = object.toVariantMap();
                else if (completed == "refresh") emit notice(QStringLiteral("目录已刷新"));
                else if (completed == "details") m_catalogDetail = object.toVariantMap();
                else emit notice(completed == "uninstall" ? QStringLiteral("已卸载，存档已保留") : completed == "rollback" ? QStringLiteral("已回退到上一版本") : QStringLiteral("安装完成，游戏启动仍需适配"));
            } else if (m_operation == "scan" || m_operation == "verify") {
                const QString kind = object.value("kind").toString(); m_cache[kind] = object.toVariantMap();
                if (kind == m_kind) m_info = m_cache[kind];
            } else { emit notice(object.value("message").toString()); m_pendingKind = m_kind; }
            emit changed();
        }
        m_output.clear();
        if (!m_pendingKind.isEmpty()) { const auto kind = m_pendingKind; m_pendingKind.clear(); inspect(kind); }
        if (backend) emit catalogFinished(completed);
    });
}
ToolState::~ToolState() { m_process.disconnect(this); m_deadline.stop(); m_cancelDeadline.stop(); if (busy()) { m_process.kill(); m_process.waitForFinished(1500); } }
bool ToolState::fail(const QString &message) { m_error = message; emit changed(); emit notice(message); return false; }
bool ToolState::choose(const QString &key, const QVariant &value) {
    if (busy()) return false;
    if (m_loadFailed || !m_settings.contains(key)) return fail(QStringLiteral("工具配置不可修改，请保留原文件后检查。"));
    auto next = m_settings; next[key] = value;
    if (!validSettings(next)) return false;
    m_settings = next; m_dirty = true; emit changed(); return save();
}
bool ToolState::save() {
    if (busy() && (m_operation == "import" || m_operation == "backup" || m_operation == "export" || m_operation == "install" || m_operation == "uninstall" || m_operation == "rollback")) return fail(QStringLiteral("正在保存文件，请稍候再离开。"));
    if (!m_dirty) return true;
    if (m_loadFailed || !ownedTools(m_stateDirectory) || !writeJson(m_stateDirectory + "/tools/settings.json", {{"version", 1}, {"settings", QJsonObject::fromVariantMap(m_settings)}})) return fail(QStringLiteral("配置未保存，当前修改保留，可重试。"));
    m_dirty = false; m_error.clear(); emit changed(); return true;
}
bool ToolState::start(const QString &operation, const QString &id) {
    if (busy() || !save()) return false;
    if (m_loadFailed && operation != "scan" && operation != "verify") return fail(QStringLiteral("工具配置不可读，未执行写入。"));
    m_backend = false; m_operation = operation; m_id = id; m_timedOut = false; m_output.clear(); if (!m_loadFailed) m_error.clear();
    m_process.setProcessEnvironment(QProcessEnvironment::systemEnvironment());
    m_process.start(QCoreApplication::applicationFilePath(), {"--tool-worker", operation, "--tool-id", id, "--content-root", m_contentRoot, "--state-dir", m_stateDirectory});
    m_deadline.start(20000); emit changed(); return true;
}
bool ToolState::inspect(const QString &kind) {
    if (!QStringList{"neo", "ports", "usb"}.contains(kind)) return false;
    if ((kind == "neo" || kind == "ports") && !m_resultMessage.isEmpty()) { emit notice(m_resultMessage); m_resultMessage.clear(); }
    m_kind = kind; m_info = m_cache.value(kind, {{"kind", kind}}); emit changed();
    if (busy()) { m_pendingKind = kind; return true; }
    return start("scan", kind);
}
bool ToolState::action(const QString &operation, const QString &id) {
    if (operation == "verify") return id == "neo" && start(operation, id);
    if (operation == "export") return id == "usb" && start(operation, id);
    if (operation != "import" && operation != "backup") return false;
    bool known = id == "mslug"; for (const auto &port : ports) known |= port.id == id;
    return known && start(operation, id);
}
void ToolState::configureCatalog(const QString &script, const QString &runtime) {
    if (busy()) return;
    m_backendScript.clear(); m_backendRuntime.clear();
    for (const auto &path : {script, runtime + "/SOURCE.json", runtime + "/python/harbourmaster/harbour.py"}) {
        const QFileInfo file(path);
        if (!file.isAbsolute() || !file.isFile() || file.isSymLink() || (file.ownerId() != 0 && file.ownerId() != geteuid())
            || file.permissions().testFlag(QFile::WriteGroup) || file.permissions().testFlag(QFile::WriteOther)) { emit changed(); return; }
    }
    m_backendScript = script; m_backendRuntime = runtime; emit changed();
}
void ToolState::readOutput() {
    m_output += m_process.readAllStandardOutput();
    if (m_backend) {
        int end;
        while ((end = m_output.indexOf('\n')) >= 0 && end <= 65536) {
            const auto object = QJsonDocument::fromJson(m_output.left(end)).object(); m_output.remove(0, end + 1);
            if (object.value("event") == QJsonValue("result")) m_backendResult = object.toVariantMap();
            else if (object.value("event") == QJsonValue("progress")) {
                const double value = object.value("progress").toDouble(-1);
                if (std::isfinite(value)) { m_progress = qBound(-1., value, 1.); emit changed(); }
            }
        }
    }
    if (m_output.size() > 65536) { m_timedOut = true; m_process.kill(); }
}
bool ToolState::startCatalog(const QString &operation, const QStringList &arguments) {
    if (busy() || !save()) return false;
    if (!catalogAvailable()) return fail(QStringLiteral("PortMaster 后端尚未准备。"));
    m_backend = true; m_operation = operation; m_output.clear(); m_backendResult.clear(); m_progress = -1;
    m_timedOut = false; m_error.clear();
    auto environment = QProcessEnvironment::systemEnvironment();
    for (const auto *key : {"LD_LIBRARY_PATH", "PYTHONPATH", "PYTHONHOME"}) environment.remove(key);
    m_process.setProcessEnvironment(environment);
    QStringList args {"-I", "-B", m_backendScript, "--runtime", m_backendRuntime, "--state", m_stateDirectory, operation};
    args.append(arguments);
    const auto python = pythonProgram();
    if (python.isEmpty()) return fail(QStringLiteral("未找到 Python 运行环境。"));
    m_process.start(python, args);
    m_deadline.start(operation == "install" ? 900000 : 90000);
    emit changed(); return true;
}
bool ToolState::catalog(const QString &query, int offset, bool installed) {
    if (query.size() > 80 || offset < 0 || offset > 20000) return false;
    QStringList args {"--query=" + query, "--offset=" + QString::number(offset)};
    if (installed) args.append("--installed");
    return startCatalog("catalog", args);
}
bool ToolState::catalogAction(const QString &operation, const QString &id) {
    if (!QStringList{"refresh", "details", "install", "uninstall", "rollback"}.contains(operation)) return false;
    if (operation != "refresh" && (id.size() > 120 || id.contains('/') || id.contains('\\') || !id.endsWith(".zip"))) return false;
    return startCatalog(operation, operation == "refresh" ? QStringList() : QStringList{"--id", id});
}
void ToolState::cancel() {
    if (!cancellable()) return;
    m_process.terminate(); m_cancelDeadline.start();
}
QVariantMap ToolState::scan(const QString &content, const QString &state, const QString &kind, bool verify) {
    QVariantMap result{{"ok", true}, {"kind", kind}};
    if (kind == "neo") {
        const QString rom = content + "/neogeo/mslug.zip", bios = content + "/neogeo/neogeo.zip";
        const bool romPresent = contained(content, rom), biosPresent = contained(content, bios), corePresent = QFileInfo(core).isFile() && !QFileInfo(core).isSymLink();
        result["romPresent"] = romPresent; result["biosPresent"] = biosPresent; result["corePresent"] = corePresent;
        result["neoVerified"] = verify && romPresent && biosPresent && matches(rom, 13165412, romHash) && matches(bios, 1760976, biosHash) && matches(core, 9007520, coreHash);
        result["saveFiles"] = saveCount(state + "/tools/ports/mslug/saves");
        result["status"] = result.value("neoVerified").toBool() ? QStringLiteral("资源校验通过") : verify ? QStringLiteral("资源校验未通过，请核对游戏、BIOS 和核心。") : romPresent && biosPresent && corePresent ? QStringLiteral("资源已找到，待校验") : QStringLiteral("需要准备游戏、BIOS 或核心");
    } else if (kind == "ports") {
        QVariantList list;
        for (const auto &port : ports) {
            const QString base = content + "/ports/" + port.directory; bool ready = QFileInfo(base).isDir() && !QFileInfo(base).isSymLink();
            for (const auto &relative : port.required) ready &= contained(content, base + "/" + relative);
            const bool runtime = port.id != "stardew" || contained(content, content + "/tools/PortMaster/libs/mono-6.12.0.122-aarch64.squashfs");
            list.append(QVariantMap{{"id", port.id}, {"title", port.title}, {"dataPresent", ready}, {"runtimePresent", runtime},
                {"runtimeStatus", port.id == "stardew" ? (runtime ? QStringLiteral("Mono 已找到 · 待适配") : QStringLiteral("缺少 Mono")) : QStringLiteral("系统依赖待核对")},
                {"originalSaves", saveCount(base + "/" + port.save) + (port.id == "gtasa" ? QDir(base).entryList(saSaves, QDir::Files | QDir::NoSymLinks).size() : 0)},
                {"managedSaves", saveCount(state + "/tools/ports/" + port.id + "/saves")},
                {"status", !ready ? QStringLiteral("缺少资源") : !runtime ? QStringLiteral("缺少运行库") : QStringLiteral("资源已找到，启动适配中")}});
        }
        result["ports"] = list;
    } else if (kind == "usb") {
        result["udcCount"] = QDir("/sys/class/udc").entryList(QDir::Dirs | QDir::NoDotAndDotDot).size();
        result["enabled"] = false; result["status"] = QStringLiteral("配置可保存，USB 输出尚未启用");
    } else return toolError(QStringLiteral("未知工具。"));
    return result;
}
int ToolState::worker(const QString &operation, const QString &id, const QString &content, const QString &state) {
    QVariantMap result;
    if (!QDir::isAbsolutePath(content) || !QDir::isAbsolutePath(state)) result = toolError(QStringLiteral("工具路径无效。"));
    else if (operation == "scan" || operation == "verify") result = scan(content, state, id, operation == "verify");
    else if (operation == "import" || operation == "backup") result = copySaves(content, state, id, operation == "backup");
    else if (operation == "export" && id == "usb") {
        const QString settingsPath = state + "/tools/settings.json";
        const auto object = readJson(settingsPath); struct stat st{};
        const bool absent = ::lstat(QFile::encodeName(settingsPath), &st) != 0 && (errno == ENOENT || errno == ENOTDIR);
        const auto settings = absent ? defaults() : object.value("settings").toObject().toVariantMap();
        if ((!absent && (object.size() != 2 || object.value("version") != QJsonValue(1))) || !validSettings(settings) || !ownedTools(state)) result = toolError(QStringLiteral("无法导出配置。"));
        else {
            const QString path = state + "/tools/usb-profile.json"; QVariantMap usb;
            for (const auto &key : {"usbSwapAB", "usbSwapXY", "usbInvertRightY", "usbDeadzone"}) usb[key] = settings.value(key);
            const bool ok = writeJson(path, {{"version", 1}, {"settings", QJsonObject::fromVariantMap(usb)}, {"reportLength", 14},
                {"descriptorHex", QString::fromLatin1(UsbGamepad::descriptor().toHex())}, {"neutralReportHex", QString::fromLatin1(UsbGamepad::report({}, 0, 0, settings).toHex())}, {"usbEnabled", false}});
            result = ok ? QVariantMap{{"ok", true}, {"message", QStringLiteral("测试配置已导出")}} : toolError(QStringLiteral("配置导出失败，原文件已保留。"));
        }
    } else result = toolError(QStringLiteral("不支持这个操作。"));
    const auto data = QJsonDocument(QJsonObject::fromVariantMap(result)).toJson(QJsonDocument::Compact);
    std::fwrite(data.constData(), 1, size_t(data.size()), stdout); std::fputc('\n', stdout);
    return result.value("ok").toBool() ? 0 : 1;
}
bool ToolState::requestNative() {
    if (!nativeEnabled() || m_contentRoot != "/roms" || busy() || !m_info.value("neoVerified").toBool()) return fail(QStringLiteral("请先校验资源，并使用 Neo 游戏会话启动。"));
    if (!save() || !ownedTools(m_stateDirectory) || !writeJson(m_stateDirectory + "/tools/native-request.json", {{"version", 1}, {"game", "mslug"}, {"settings", QJsonObject::fromVariantMap(m_settings)}})) return fail(QStringLiteral("无法保存启动请求。"));
    emit nativeRequested("mslug"); return true;
}
bool ToolState::requestPort(const QString &id) {
    if (!portsEnabled() || m_contentRoot != "/roms" || busy() || !QStringList{"gta3", "gtavc", "stardew"}.contains(id))
        return fail(QStringLiteral("请使用带持久数据目录的游戏会话。"));
    if (!save() || !ownedTools(m_stateDirectory) || !writeJson(m_stateDirectory + "/tools/native-request.json", {{"version", 1}, {"game", id}, {"settings", QJsonObject::fromVariantMap(m_settings)}}))
        return fail(QStringLiteral("无法保存启动请求。"));
    emit nativeRequested(id); return true;
}
bool ToolState::stageNativeRequest(const QString &game) {
    if(!QStringList{"mslug","gta3","gtavc","stardew"}.contains(game)||!ownedTools(m_stateDirectory))return false;
    const auto source=m_stateDirectory+"/tools/native-request.json";
    const auto value=readJson(source);
    if(value.size()!=3 || value.value("version")!=QJsonValue(1) || value.value("game").toString()!=game
        || !validSettings(value.value("settings").toObject().toVariantMap()))return false;
    const auto destination=m_stateDirectory+"/tools/native-request-"+game+".json";
    return writeJson(destination,value)&&QFile::remove(source);
}
void ToolState::nativeFinished(const QString &game, int exitCode) {
    if (!QStringList{"mslug", "gta3", "gtavc", "stardew"}.contains(game) || !ownedTools(m_stateDirectory)
        || !writeJson(m_stateDirectory + "/tools/native-result.json", {{"version", 1}, {"game", game}, {"exit", exitCode}})) {
        fail(QStringLiteral("无法保存游戏结束状态。")); return;
    }
    m_lastGame = game;
    const auto pending=m_stateDirectory+"/tools/native-request-"+game+".json";
    if(privateFile(pending,true))QFile::remove(pending);
    emit changed();
    emit notice(exitCode == 0 ? QStringLiteral("游戏已结束") : QStringLiteral("游戏未正常结束，可检查后重试。"));
    if (game == "mslug" && m_kind == "neo") start("verify", "neo");
    else if (game != "mslug" && m_kind == "ports") start("scan", "ports");
}
QByteArray ToolState::neoConfiguration(const QVariantMap &settings, const QString &game, bool shared) {
    if (!validSettings(settings) || !QDir::isAbsolutePath(game) || game.contains(QRegularExpression("[\"\\\\\\r\\n]"))) return {};
    QString options = QString("video_scale_integer = \"%1\"\nvideo_smooth = \"%2\"\n")
        .arg(settings.value("neoIntegerScale").toBool() ? "true" : "false", settings.value("neoSmooth").toBool() ? "true" : "false");
    options += "libretro_directory = \"/usr/local/libexec\"\nlibretro_info_path = \"/usr/share/libretro/info\"\n"
        "global_core_options = \"true\"\ngame_specific_options = \"false\"\nauto_overrides_enable = \"false\"\nauto_remaps_enable = \"false\"\n"
        "history_list_enable = \"false\"\ncontent_runtime_log = \"false\"\ncontent_runtime_log_aggregate = \"false\"\n"
        "config_save_on_exit = \"false\"\nremap_save_on_exit = \"false\"\nquit_press_twice = \"false\"\n";
    options += "core_options_path = \"" + game + "/core-options.cfg\"\nsavefile_directory = \"" + game + "/saves/battery\"\n"
        "savestate_directory = \"" + game + "/saves/states\"\nscreenshot_directory = \"" + game + "/screenshots\"\n";
    if (!shared) return (options + "input_exit_emulator_btn = \"9\"\n").toUtf8();
    options += "video_context_driver = \"wayland\"\ninput_driver = \"wayland\"\ninput_joypad_driver = \"sdl2\"\n"
        "input_autodetect_enable = \"false\"\ninput_player1_joypad_index = \"0\"\ninput_enable_hotkey_btn = \"4\"\n"
        "input_menu_toggle_btn = \"2\"\ninput_exit_emulator_btn = \"6\"\n";
    const QMap<QString, int> buttons{{"a", 0}, {"b", 1}, {"x", 2}, {"y", 3}, {"select", 4}, {"start", 6},
        {"l3", 7}, {"r3", 8}, {"l", 9}, {"r", 10}, {"up", 11}, {"down", 12}, {"left", 13}, {"right", 14}};
    for (auto it = buttons.begin(); it != buttons.end(); ++it) options += "input_player1_" + it.key() + "_btn = \"" + QString::number(it.value()) + "\"\n";
    options += "input_player1_l2_btn = \"nul\"\ninput_player1_r2_btn = \"nul\"\ninput_player1_l2_axis = \"+4\"\ninput_player1_r2_axis = \"+5\"\n";
    return options.toUtf8();
}
int ToolState::runNative(const QString &state, int timeoutSeconds, bool sharedDisplay, const QString &expectedGame) {
    // Both render paths require the fixed device and the corresponding outer supervisor.
    DeviceState device("/", false);
    if (!device.target() || geteuid() != 1000 || timeoutSeconds < 1 || timeoutSeconds > 2100 || state.contains('"') || state.contains('\\') || state.contains('\n') || state.contains('\r')) return 2;
    QFile cgroup("/proc/self/cgroup"); struct statvfs mount{};
    if (!cgroup.open(QIODevice::ReadOnly) || ::statvfs("/roms", &mount) || !(mount.f_flag & ST_RDONLY)
        || !QRegularExpression(sharedDisplay ? "/r46h-wayland-probe-[0-9]+\\.service(?:\\n|$)" : "/r46h-shell-probe-[0-9]+\\.service(?:\\n|$)")
            .match(QString::fromUtf8(cgroup.read(4096))).hasMatch()) return 2;
    if (sharedDisplay ? (qEnvironmentVariableIsEmpty("WAYLAND_DISPLAY") || !QStringList{"0x5246/0x0049","0x5246/0x004a","0x5246/0x004b","0x5246/0x004c"}.contains(qEnvironmentVariable("SDL_GAMECONTROLLER_IGNORE_DEVICES_EXCEPT")))
                      : !qEnvironmentVariableIsEmpty("WAYLAND_DISPLAY")) return 2;
    if (!ownedTools(state)) return 2;
    if(!expectedGame.isEmpty()&&(!sharedDisplay||!QStringList{"mslug","gta3","gtavc","stardew"}.contains(expectedGame)))return 2;
    const QString requestPath = state + "/tools/native-request"+(expectedGame.isEmpty()?QString():"-"+expectedGame)+".json";
    const auto request = readJson(requestPath); const auto settings = request.value("settings").toObject().toVariantMap();
    if(!expectedGame.isEmpty()&&request.value("game").toString()!=expectedGame)return 2;
    if (request.size() != 3 || request.value("version") != QJsonValue(1) || !QStringList{"mslug", "gta3", "gtavc", "stardew"}.contains(request.value("game").toString()) || !validSettings(settings)) return 2;
    const auto id = request.value("game").toString();
    if (id != "mslug") {
        if (state.startsWith("/run/") || (sharedDisplay && qEnvironmentVariable("R46H_SHARED_PORTS") != "1")) return 2;
        const QString base = QCoreApplication::applicationDirPath() + "/..";
        const QString script = QDir::cleanPath(base + "/share/r46h/ports/local_port.py");
        const auto scriptInfo = QFileInfo(script);
        if (!scriptInfo.isFile() || scriptInfo.isSymLink() || scriptInfo.ownerId() != 0 || scriptInfo.permissions().testFlag(QFile::WriteGroup) || scriptInfo.permissions().testFlag(QFile::WriteOther)) return 2;
        const QString gameDirectory = state + "/tools/ports/" + id;
        if (!privateDirectory(state + "/tools/ports") || !privateDirectory(gameDirectory) || !privateFile(gameDirectory + "/launcher.log", true) || !QFile::remove(requestPath)) return 2;
        QProcess child; auto environment = QProcessEnvironment::systemEnvironment();
        for (const auto *key : {"LD_LIBRARY_PATH", "LD_PRELOAD", "QT_PLUGIN_PATH", "QML_IMPORT_PATH", "QT_IM_MODULE", "QSG_INFO", "QSG_RENDER_TIMING"}) environment.remove(key);
        child.setProcessEnvironment(environment); child.setStandardInputFile(QProcess::nullDevice());
        child.setProcessChannelMode(QProcess::MergedChannels);
        QByteArray launcherLog;
        auto drain = [&] { const auto data = child.readAll(); if (launcherLog.size() < 65536) launcherLog += data.left(65536 - launcherLog.size()); };
        connect(&child, &QProcess::readyRead, &child, drain);
        QStringList arguments{"-I", "-B", script, id, "--device-run", "--content-root", "/roms", "--state", state + "/tools/ports/" + id, "--seconds", QString::number(timeoutSeconds)};
        if (sharedDisplay) arguments << "--shared-display";
        const auto python = pythonProgram();
        if (python.isEmpty() || QFileInfo(python).ownerId() != 0) return 2;
        child.start(python, arguments);
        int result = 1;
        if (child.waitForStarted(5000)) {
            if (child.waitForFinished((timeoutSeconds + 10) * 1000)) result = child.exitStatus() == QProcess::NormalExit ? child.exitCode() : 1;
            else { child.terminate(); if (!child.waitForFinished(3000)) { child.kill(); child.waitForFinished(2000); } result = 124; }
        }
        drain();
        QSaveFile output(gameDirectory + "/launcher.log");
        if (output.open(QIODevice::WriteOnly)) { output.setPermissions(QFile::ReadOwner | QFile::WriteOwner); output.write(launcherLog); output.commit(); }
        if (!writeJson(state + "/tools/native-result.json", {{"version", 1}, {"game", id}, {"exit", result}})) return 2;
        return result == 2 ? 1 : result;
    }
    if (!scan("/roms", state, "neo", true).value("neoVerified").toBool()) return 2;
    const QString config = "/etc/r46h/retroarch.cfg", metadata = "/usr/share/libretro/info/fbneo_neogeo_libretro.info";
    for (const auto &path : {config, metadata, QString("/usr/bin/retroarch")}) {
        const auto info = QFileInfo(path);
        if (!info.isFile() || info.isSymLink() || info.ownerId() != 0 || info.permissions().testFlag(QFile::WriteGroup) || info.permissions().testFlag(QFile::WriteOther)) return 2;
    }
    const QString portsPath = state + "/tools/ports", game = portsPath + "/mslug";
    if (!privateDirectory(portsPath) || !privateDirectory(game) || !privateDirectory(game + "/saves") || !privateDirectory(game + "/saves/battery") || !privateDirectory(game + "/saves/states") || !privateDirectory(game + "/screenshots")) return 2;
    if (!privateFile(game + "/retroarch.cfg", true) || !privateFile(game + "/runtime.log", true)) return 2;
    const QString optionsPath = game + "/core-options.cfg";
    if (!privateFile(optionsPath, true)) return 2;
    if (!QFileInfo::exists(optionsPath)) {
        const QString original = "/home/ark/.config/retroarch/config/FinalBurn Neo (neogeo subset)/FinalBurn Neo (neogeo subset).opt";
        QFile source(original); QSaveFile copy(optionsPath);
        if (!privateFile(original) || !source.open(QIODevice::ReadOnly) || source.size() > 32768 || !copy.open(QIODevice::WriteOnly)) return 2;
        copy.setPermissions(QFile::ReadOwner | QFile::WriteOwner);
        const auto bytes = source.readAll();
        if (copy.write(bytes) != bytes.size() || !copy.commit()) return 2;
    }
    QSaveFile append(game + "/retroarch.cfg");
    const QByteArray options = neoConfiguration(settings, game, sharedDisplay);
    if (!append.open(QIODevice::WriteOnly)) return 2;
    append.setPermissions(QFile::ReadOwner | QFile::WriteOwner);
    if (append.write(options) != options.size() || !append.commit() || !QFile::remove(requestPath)) return 2;
    QProcess process; auto environment = QProcessEnvironment::systemEnvironment();
    for (const auto *key : {"LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH", "QT_PLUGIN_PATH", "QML_IMPORT_PATH", "QT_IM_MODULE", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "QSG_INFO", "QSG_RENDER_TIMING"}) environment.remove(key);
    environment.insert("SDL_NO_SIGNAL_HANDLERS", "1");
    if (sharedDisplay) environment.insert("SDL_VIDEODRIVER", "wayland");
    process.setProcessEnvironment(environment); process.setWorkingDirectory(game);
    process.setStandardInputFile(QProcess::nullDevice()); process.setProcessChannelMode(QProcess::MergedChannels);
    QByteArray log;
    auto drain = [&] { const auto bytes = process.readAll(); if (log.size() < 65536) log += bytes.left(65536 - log.size()); };
    connect(&process, &QProcess::readyRead, &process, drain);
    process.start("/usr/bin/retroarch", {"-c", config, "--appendconfig", game + "/retroarch.cfg", "-L", core, "/roms/neogeo/mslug.zip"});
    int result = 1;
    if (process.waitForStarted(5000)) {
        if (process.waitForFinished(timeoutSeconds * 1000)) result = process.exitStatus() == QProcess::NormalExit ? process.exitCode() : 1;
        else { process.terminate(); if (!process.waitForFinished(3000)) { process.kill(); process.waitForFinished(2000); } result = 124; }
    }
    drain();
    if (!writeJson(state + "/tools/native-result.json", {{"version", 1}, {"game", "mslug"}, {"exit", result}})) return 2;
    QSaveFile output(game + "/runtime.log");
    if (output.open(QIODevice::WriteOnly)) { output.setPermissions(QFile::ReadOwner | QFile::WriteOwner); output.write(log); output.commit(); }
    return result == 2 ? 1 : result;
}
