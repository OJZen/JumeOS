#include "control.h"
#include "preferences.h"
#include "device.h"
#include "telemetry.h"
#include "handheld.h"
#include "../gaming-wayland/input-route.h"
#include <cmath>
#include <QBuffer>
#include <QCryptographicHash>
#include <QDir>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QCoreApplication>
#include <QQuickItem>
#include <QQuickView>
#include <QRegularExpression>
#include <QSysInfo>
#include <QTimer>
#include <QUuid>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>
#include <poll.h>

namespace { bool sameUser(qintptr descriptor); }

int runControlCall(const QString &directory) {
    // SSH supplies a fixed command; never interpret its original command as arguments.
    if (qgetenv("SSH_ORIGINAL_COMMAND") != "r46h-control") return 2;
    alarm(15);
    QFile input, output; input.open(stdin, QIODevice::ReadOnly); output.open(stdout, QIODevice::WriteOnly);
    const auto request = input.readLine(4097);
    const auto document = QJsonDocument::fromJson(request);
    const auto id = document.object().value("id").toString();
    auto fail = [&](const char *reason) {
        output.write(QJsonDocument(QJsonObject{{"version",1},{"id",id},{"ok",false},{"error",QString::fromLatin1(reason)}}).toJson(QJsonDocument::Compact)+'\n');
        output.flush(); return 1;
    };
    if (request.size() > 4096 || !request.endsWith('\n') || !document.isObject()) return fail("invalid_request");
    if (!QDir::isAbsolutePath(directory) || directory != QDir::cleanPath(directory)) return fail("invalid_directory");
    struct stat st{}; const auto parent = QFile::encodeName(directory);
    if (::lstat(parent.constData(), &st) || !S_ISDIR(st.st_mode) || st.st_uid != geteuid() || (st.st_mode & 0777) != 0700)
        return fail("ui_unavailable");
    const auto path = directory + "/control.sock"; const auto encoded = QFile::encodeName(path);
    if (::lstat(encoded.constData(), &st) || !S_ISSOCK(st.st_mode) || st.st_uid != geteuid() || (st.st_mode & 0777) != 0600)
        return fail("ui_unavailable");
    QLocalSocket socket; socket.connectToServer(path);
    if (!socket.waitForConnected(3000)) return fail("ui_unavailable");
    if (!sameUser(socket.socketDescriptor())) return fail("wrong_peer");
    socket.write(request);
    if (socket.bytesToWrite() && !socket.waitForBytesWritten(3000)) return fail("request_delivery_unknown");
    QByteArray response; QElapsedTimer clock; clock.start();
    while (clock.elapsed() < 5000) {
        // SSH stdin normally ends after one request. Its output pipe closes on
        // transport loss; drop our local connection so an active input lease cancels.
        pollfd downstream{STDOUT_FILENO, 0, 0};
        if (::poll(&downstream, 1, 0) < 0 || (downstream.revents & (POLLERR | POLLHUP | POLLNVAL))) return 1;
        response += socket.readAll();
        if (response.size() > 16 * 1024 * 1024) return fail("response_too_large");
        if (response.endsWith('\n')) break;
        if (socket.state() == QLocalSocket::UnconnectedState) break;
        socket.waitForReadyRead(qMin(50, qMax(1, 5000-int(clock.elapsed()))));
    }
    if (response.size() > 16 * 1024 * 1024) return fail("response_too_large");
    const auto result = QJsonDocument::fromJson(response);
    if (!result.isObject() || result.object().value("id").toString() != id || result.object().value("version") != QJsonValue(1))
        return fail("response_unavailable_observe_before_retry");
    if (output.write(response) != response.size() || !output.flush()) return 1;
    alarm(0); return 0;
}

namespace {
constexpr int RequestLimit = 4096;
const QStringList Actions = {"left", "right", "up", "down", "accept", "back", "quick", "favorite", "home", "previousTab", "nextTab", "erase", "submit"};
bool sameUser(qintptr descriptor) {
#ifdef Q_OS_LINUX
    struct ucred peer{};
    socklen_t size = sizeof(peer);
    return getsockopt(int(descriptor), SOL_SOCKET, SO_PEERCRED, &peer, &size) == 0 && peer.uid == geteuid();
#elif defined(Q_OS_MACOS)
    uid_t uid; gid_t gid;
    return getpeereid(int(descriptor), &uid, &gid) == 0 && uid == geteuid();
#else
    return false;
#endif
}
}
ControlServer::ControlServer(QQuickView *view, Preferences *preferences, DeviceState *device, Telemetry *telemetry, HandheldSession *handheld)
    : m_view(view), m_preferences(preferences), m_device(device), m_telemetry(telemetry), m_handheld(handheld), m_session(QUuid::createUuid().toString(QUuid::WithoutBraces)) {
    m_clock.start();
    connect(&m_server, &QLocalServer::newConnection, this, &ControlServer::accept);
    if (m_handheld) connect(m_handheld, &HandheldSession::captureFinished, this, [this](const QImage &image, const QString &error) {
        if (!m_captureClient) return;
        auto response = observe(false); auto capture = response.value("capture").toObject();
        if (m_view->rootObject()->property("sensitiveVisible").toBool()) capture["status"] = "sensitive_entry";
        else if (!error.isEmpty()) capture["status"] = error;
        else encodeImage(capture, image);
        response["capture"] = capture; response["ok"] = true; response["id"] = m_captureRequest;
        reply(m_captureClient, response); m_captureClient.clear();
    });
    if (m_handheld) connect(m_handheld, &HandheldSession::gameInputFinished, this, [this](const QString &status) {
        if (!m_gameClient) return;
        auto *socket = m_gameClient.data(); m_gameClient.clear();
        socket->setProperty("gameInputStatus", status);
        observeAndReply(socket, socket->property("requestId").toString(), socket->property("screenshot").toBool());
    });
}
ControlServer::~ControlServer() {
    if (m_handheld) m_handheld->cancelGameInput();
    m_server.disconnect(this);
    if (m_client) { m_client->disconnect(this); m_client->abort(); }
    m_server.close();
}
bool ControlServer::start(const QString &directory, QString *error) {
    auto fail = [&](const char *reason) { *error = QString::fromLatin1(reason); return false; };
    if (!QDir::isAbsolutePath(directory) || directory != QDir::cleanPath(directory)) return fail("invalid_directory");
    const auto path = QFile::encodeName(directory);
    if (::mkdir(path.constData(), 0700) != 0 && errno != EEXIST) return fail("directory_unavailable");
    struct stat metadata{};
    if (::lstat(path.constData(), &metadata) != 0 || !S_ISDIR(metadata.st_mode) ||
        metadata.st_uid != geteuid() || (metadata.st_mode & 0777) != 0700) return fail("directory_not_private");
    const auto socketPath = directory + "/control.sock";
    const auto encoded = QFile::encodeName(socketPath);
    if (encoded.size() >= 100) return fail("socket_path_too_long");
    if (::lstat(encoded.constData(), &metadata) == 0 || errno != ENOENT) return fail("socket_path_exists");
    QFile binary(QCoreApplication::applicationFilePath());
    if (!binary.open(QIODevice::ReadOnly)) return fail("binary_identity_unavailable");
    QCryptographicHash hash(QCryptographicHash::Sha256);
    if (!hash.addData(&binary)) return fail("binary_identity_unavailable");
    m_binary = QString::fromLatin1(hash.result().toHex());
    // The 0700 parent protects creation; set the final mode before accepting peers.
    m_server.setMaxPendingConnections(1);
    if (!m_server.listen(socketPath)) return fail("listen_failed");
    if (::chmod(encoded.constData(), 0600) != 0) { m_server.close(); return fail("socket_not_private"); }
    if (::lstat(encoded.constData(), &metadata) != 0 || !S_ISSOCK(metadata.st_mode) ||
        metadata.st_uid != geteuid() || (metadata.st_mode & 0777) != 0600) {
        m_server.close(); return fail("socket_not_private");
    }
    return true;
}
void ControlServer::accept() {
    while (m_server.hasPendingConnections()) {
        auto *socket = m_server.nextPendingConnection();
        if (m_client || !sameUser(socket->socketDescriptor())) { socket->abort(); socket->deleteLater(); continue; }
        m_client = socket;
        socket->setReadBufferSize(RequestLimit + 1);
        connect(socket, &QLocalSocket::disconnected, this, [this, socket] {
            if (m_gameClient == socket) { m_gameClient.clear(); m_handheld->cancelGameInput(); }
            if (m_client == socket) m_client.clear();
            socket->deleteLater();
        });
        connect(socket, &QLocalSocket::readyRead, this, [this, socket] { receive(socket); });
        QTimer::singleShot(3000, socket, [socket] { socket->abort(); });
        receive(socket);
    }
}
void ControlServer::reply(QLocalSocket *socket, QJsonObject response) {
    if (socket->state() != QLocalSocket::ConnectedState) return;
    response["version"] = 1;
    if (socket->property("gameInputStatus").isValid()) {
        response["input_status"] = socket->property("gameInputStatus").toString(); response["input_backend"] = "routed-uinput";
    }
    socket->write(QJsonDocument(response).toJson(QJsonDocument::Compact) + '\n');
    socket->disconnectFromServer();
}
void ControlServer::receive(QLocalSocket *socket) {
    if (socket->property("handled").toBool()) return;
    if (socket->bytesAvailable() > RequestLimit) {
        socket->setProperty("handled", true); reply(socket, {{"ok", false}, {"error", "request_too_large"}}); return;
    }
    if (!socket->canReadLine()) return;
    socket->setProperty("handled", true);
    const auto bytes = socket->readAll();
    const auto document = QJsonDocument::fromJson(bytes);
    const auto request = document.object();
    const auto id = request.value("id").toString();
    auto fail = [&](const char *reason) { reply(socket, {{"id", id}, {"ok", false}, {"error", QString::fromLatin1(reason)}}); };
    if (!document.isObject() || !QRegularExpression("^[A-Za-z0-9_-]{1,64}$").match(id).hasMatch() ||
        request.value("version") != QJsonValue(1) || !request.value("screenshot").isBool()) { fail("invalid_request"); return; }
    const auto op = request.value("op").toString();
    QStringList fields {"version", "id", "op", "screenshot"};
    if (op == "tap" || op == "text") fields.append({"session", "sequence", "binary_sha256", op == "tap" ? "action" : "text"});
    if (op == "game-input") fields.append({"session", "sequence", "binary_sha256", "application", "input_sequence", "buttons", "axes", "duration_ms"});
    for (auto it = request.begin(); it != request.end(); ++it) if (!fields.contains(it.key())) { fail("unknown_field"); return; }
    if (op != "observe" && op != "tap" && op != "text" && op != "game-input") { fail("unsupported_operation"); return; }
    if (!m_view->rootObject()) { fail("ui_unavailable"); return; }
    if (op == "tap" || op == "text" || op == "game-input") {
        if (request.value("session").toString() != m_session) { fail("stale_session"); return; }
        if (request.value("binary_sha256").toString() != m_binary) { fail("wrong_binary"); return; }
        if (!request.value("sequence").isDouble() || request.value("sequence").toDouble() != double(m_sequence)) { fail("stale_sequence"); return; }
        const auto action = request.value("action").toString();
        const auto text = request.value("text").toString();
        if (op == "tap" && !Actions.contains(action)) { fail("unsupported_action"); return; }
        if (op == "text") {
            if (!request.value("text").isString() || text.size() > 80 || QRegularExpression("[\\x00-\\x1f\\x7f]").match(text).hasMatch()) { fail("invalid_text"); return; }
            if (!m_view->rootObject()->property("remoteTextAllowed").toBool()) { fail("field_unavailable"); return; }
        }
        if (m_sequence >= 9007199254740991LL) { fail("sequence_exhausted"); return; }
        if (op == "game-input") {
            Route::Packet input;
            const auto buttons = request.value("buttons").toArray(), axes = request.value("axes").toArray();
            const double duration = request.value("duration_ms").toDouble(-1), sequence = request.value("input_sequence").toDouble(-1);
            bool valid = request.value("buttons").isArray() && buttons.size() <= 16 && request.value("axes").isArray() && axes.size() == 4
                && std::isfinite(duration) && duration >= 10 && duration <= 1000 && duration == std::floor(duration)
                && std::isfinite(sequence) && sequence >= 1 && sequence <= 9007199254740991. && sequence == std::floor(sequence)
                && request.value("application").isString() && request.value("application").toString().size() <= 64;
            for (const auto &button : buttons) {
                int index = -1;
                for (int i = 0; i < 16; ++i) if (button == QJsonValue(QString::fromLatin1(Route::ButtonNames[i]))) index = i;
                if (index < 0 || input.keys & (1U << index)) valid = false;
                else input.keys |= 1U << index;
            }
            for (int i = 0; i < axes.size(); ++i) {
                const double value = axes[i].toDouble(2);
                if (i >= 4 || !std::isfinite(value) || value < -1 || value > 1) valid = false;
                else input.axes[i] = qRound(value * 32767);
            }
            if (!valid) { fail("invalid_game_input"); return; }
            if (!m_handheld || !m_handheld->gameInputAvailable()) { fail("game_input_unavailable"); return; }
            ++m_sequence; m_gameClient = socket;
            socket->setProperty("requestId", id); socket->setProperty("screenshot", request.value("screenshot").toBool());
            if (!m_handheld->injectGame(input.keys, input.axes, int(duration), quint64(sequence), request.value("application").toString())) {
                m_gameClient.clear(); fail("game_input_unavailable");
            }
            return;
        }
        ++m_sequence;
        if (op == "text") {
            QVariant applied;
            if (!QMetaObject::invokeMethod(m_view->rootObject(), "remoteText", Q_RETURN_ARG(QVariant, applied), Q_ARG(QVariant, text)) || !applied.toBool()) { fail("dispatch_failed"); return; }
        } else if (!QMetaObject::invokeMethod(m_view->rootObject(), "dispatch", Q_ARG(QVariant, action), Q_ARG(QVariant, false))) { fail("dispatch_failed"); return; }
    }
    const bool screenshot = request.value("screenshot").toBool();
    // Short bounded settling for the existing <=200 ms transitions. Never blocks input.
    QTimer::singleShot(screenshot && !m_handheld ? 250 : 0, socket, [this, socket, id, screenshot] {
        observeAndReply(socket, id, screenshot);
    });
}
void ControlServer::observeAndReply(QLocalSocket *socket, const QString &id, bool screenshot) {
    if (socket->state() != QLocalSocket::ConnectedState) return;
    if (screenshot && m_handheld) {
        m_captureClient = socket; m_captureRequest = id;
        if (m_handheld->requestCapture()) return;
        m_captureClient.clear();
        auto response = observe(false); auto capture = response.value("capture").toObject();
        capture["status"] = "capture_failed"; response["capture"] = capture;
        response["id"] = id; response["ok"] = true; reply(socket, response); return;
    }
    auto response = observe(screenshot); response["id"] = id; response["ok"] = true; reply(socket, response);
}
QJsonObject ControlServer::observe(bool screenshot) {
    const auto *root = m_view->rootObject();
    QJsonObject state;
    for (const auto *name : {"sharedDisplay", "sharedReady", "keyboardReady", "gameOverlay", "panelVisible", "monitorVisible", "page", "selected", "settingsCategory", "settingsIndex", "settingsSidebar", "settingsAdjusting",
                            "remoteTextAllowed", "portCatalogTotal", "portCatalogOpen", "portCatalogIndex", "portCatalogSidebar", "toolRoute", "toolOpen", "toolBusy", "toolIndex", "toolRow", "toolSaveError", "tabsFocused", "quickOpen", "quickIndex", "session", "sessionMoves", "testingController", "editing", "dimmed", "choicesOpen", "externalSession", "activeApplication", "applicationError", "applicationExitCode", "selectedApplication", "selectedFavorite", "streamingOpen", "streamingBusy", "sensitiveVisible", "testInputCapture", "testInputVisible"})
        state[QString::fromLatin1(name)] = QJsonValue::fromVariant(root->property(name));
    state["monitor"] = m_preferences->monitor(); state["reducedMotion"] = m_preferences->reducedMotion();
    state["gameInputAvailable"] = m_handheld && m_handheld->gameInputAvailable();
    state["inputSequence"] = m_handheld ? qint64(m_handheld->inputSequence()) : 0;
    state["fontPercent"] = m_preferences->fontPercent(); state["volume"] = m_preferences->volume();
    state["brightness"] = m_preferences->brightness(); state["dirty"] = m_preferences->dirty();
    state["save_error"] = !m_preferences->error().isEmpty();
    state["device"] = QJsonObject::fromVariantMap(m_device->diagnostics());
    state["telemetry"] = QJsonObject{{"active",m_telemetry->active()},{"processCpu",m_telemetry->cpu()},
        {"residentMiB",m_telemetry->memoryMiB()},{"uiSubmissions",m_telemetry->submissions()}, {"game", QJsonObject::fromVariantMap(m_telemetry->game())},
        {"stream", QJsonObject::fromVariantMap(m_telemetry->stream())}};
    QJsonObject capture{{"source", m_handheld ? "weston-output" : "qt-window"}, {"status", "not_requested"}};
    if (screenshot) {
        if (root->property("sensitiveVisible").toBool()) capture["status"] = "sensitive_entry";
        else if (!m_view->isVisible() || !m_view->isExposed()) capture["status"] = "window_unavailable";
        else if (double(m_view->width()) * m_view->height() * m_view->devicePixelRatio() * m_view->devicePixelRatio() > 4194304)
            capture["status"] = "size_limit";
        else {
            encodeImage(capture, m_view->grabWindow());
        }
    }
    capture["monotonic_ms"] = m_clock.elapsed();
    return {{"application", "r46h-shell"}, {"session", m_session}, {"sequence", m_sequence}, {"binary_sha256", m_binary},
            {"kernel", QSysInfo::kernelType() + " " + QSysInfo::kernelVersion()}, {"input_backend", "qml-action"},
            {"capture", capture}, {"state", state}, {"actions", QJsonArray::fromStringList(Actions)},
            {"operations", m_handheld ? QJsonArray{"observe", "tap", "text", "game-input"} : QJsonArray{"observe", "tap", "text"}}, {"measurement", "diagnostic-not-performance"}};
}
void ControlServer::encodeImage(QJsonObject &capture, const QImage &frame) {
    QByteArray png; QBuffer buffer(&png); buffer.open(QIODevice::WriteOnly);
    if (frame.isNull() || qint64(frame.width()) * frame.height() > 4194304 || !frame.save(&buffer, "PNG") || png.size() > 8 * 1024 * 1024) { capture["status"] = "capture_failed"; return; }
    capture["status"] = "ok"; capture["width"] = frame.width(); capture["height"] = frame.height();
    capture["logical_width"] = m_handheld ? frame.width() : m_view->width();
    capture["logical_height"] = m_handheld ? frame.height() : m_view->height();
    capture["scale"] = m_handheld ? 1 : m_view->devicePixelRatio(); capture["orientation"] = 0;
    capture["bytes"] = qint64(png.size()); capture["sha256"] = QString::fromLatin1(QCryptographicHash::hash(png, QCryptographicHash::Sha256).toHex());
    capture["png_base64"] = QString::fromLatin1(png.toBase64());
}
