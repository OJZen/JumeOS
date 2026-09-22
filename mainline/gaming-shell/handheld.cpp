#include "handheld.h"
#include "input.h"
#include "applications.h"
#include "../gaming-wayland/input-route.h"
#include <QDir>
#include <QFileInfo>
#include <QFile>
#include <QQuickView>
#include <QQuickItem>
#include <QJsonDocument>
#include <QCoreApplication>
#include <QGuiApplication>
#include <algorithm>
#include <cmath>
#include <sys/stat.h>
#include <unistd.h>
#ifdef Q_OS_LINUX
#include <sys/socket.h>
#include <fcntl.h>
#include <wayland-client.h>
#include "../gaming-wayland/capture.h"
#endif

HandheldSession::HandheldSession(QQuickView *view, ControllerInput *input, Applications *applications)
    : m_view(view), m_input(input), m_applications(applications) {
    m_router.setStandardInputFile(QProcess::nullDevice());
    m_router.setStandardOutputFile(QProcess::nullDevice());
    m_router.setProcessChannelMode(QProcess::ForwardedErrorChannel);
    connect(&m_router, &QProcess::errorOccurred, this, [this] { fail(QStringLiteral("输入路由未能启动。")); });
    connect(&m_router, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
            [this] { fail(QStringLiteral("输入路由已结束，正在恢复桌面。")); });
    m_deadline.setSingleShot(true); m_deadline.setInterval(1500);
    connect(&m_deadline, &QTimer::timeout, this, [this] {
        if (m_request.value("op") == QJsonValue("observe")) frameSampleFailed();
        else fail(QStringLiteral("桌面合成器响应超时。"));
    });
    m_inputDeadline.setSingleShot(true); m_inputDeadline.setInterval(2000);
    connect(&m_inputDeadline, &QTimer::timeout, this, [this] { fail(QStringLiteral("输入归属切换超时。")); });
    connect(&m_policy, &QLocalSocket::connected, this, [this] {
#ifdef Q_OS_LINUX
        ucred peer{}; socklen_t length = sizeof(peer);
        if (getsockopt(int(m_policy.socketDescriptor()), SOL_SOCKET, SO_PEERCRED, &peer, &length)
            || peer.uid != geteuid() || peer.pid != m_compositorPid) { fail(QStringLiteral("显示连接与桌面策略不属于同一合成器。")); return; }
#endif
        m_policy.write(QJsonDocument(m_request).toJson(QJsonDocument::Compact) + '\n');
    });
    connect(&m_policy, &QLocalSocket::readyRead, this, &HandheldSession::readPolicy);
    connect(&m_policy, &QLocalSocket::errorOccurred, this, [this] {
        if (m_pending && m_response.isEmpty()) {
            if (m_request.value("op") == QJsonValue("observe")) frameSampleFailed();
            else fail(QStringLiteral("无法连接桌面合成器。"));
        }
    });
    connect(m_applications, &Applications::started, this, &HandheldSession::sceneChanged);
    connect(m_applications, &Applications::finished, this, &HandheldSession::sceneChanged);
    m_captureDeadline.setSingleShot(true); m_captureDeadline.setInterval(2000);
    connect(&m_captureDeadline, &QTimer::timeout, this, [this] { cancelCapture("capture_failed"); });
    m_frameTimer.setInterval(1000);
    connect(&m_frameTimer, &QTimer::timeout, this, [this] {
        if (m_capturePhase == Idle) { m_frameSampleDue = true; requestPolicy(); }
    });
    connect(m_view, &QWindow::visibilityChanged, this, [this] { updateFrameSampling(); });
}
HandheldSession::~HandheldSession() {
    disconnect(m_syncConnection); disconnect(m_frameConnection);
#ifdef Q_OS_LINUX
    if (m_fence) wl_callback_destroy(m_fence);
#endif
    if (m_captureThread) { m_captureThread->wait(); delete m_captureThread; }
    m_failed = true; m_deadline.stop(); m_inputDeadline.stop(); m_notifier.reset();
    m_router.disconnect(this);
    if (m_control >= 0) ::close(m_control);
    if (m_router.state() != QProcess::NotRunning) {
        m_router.terminate();
        if (!m_router.waitForFinished(1500)) { m_router.kill(); m_router.waitForFinished(1500); }
    }
}
void HandheldSession::fail(const QString &message) {
    if (m_failed) return;
    m_failed = true; m_ready = false; m_deadline.stop(); m_inputDeadline.stop(); m_frameTimer.stop(); m_notifier.reset();
    m_frameMetrics = {{"active", false}}; emit frameMetricsChanged();
    if (m_control >= 0) { ::close(m_control); m_control = -1; }
    m_input->suppressUntilNeutral(); m_applications->stop();
    if (m_capturePhase != Idle) {
        m_captureDeadline.stop(); m_capturePhase = Idle; m_captureImage = {};
        emit captureFinished({}, "capture_failed");
    }
    if (m_remoteSequence) { m_remoteSequence = 0; emit gameInputFinished("cancelled"); }
    emit changed(); emit failed(message);
}
bool HandheldSession::start(const QString &router, const QString &device, QString *error, int uinputFd) {
#ifndef Q_OS_LINUX
    Q_UNUSED(router); Q_UNUSED(device); Q_UNUSED(uinputFd); *error = QStringLiteral("共享桌面输入仅用于 Linux Wayland。"); return false;
#else
    auto *native = qGuiApp->nativeInterface<QNativeInterface::QWaylandApplication>();
    ucred compositor{}; socklen_t length = sizeof(compositor);
    if (!native || !native->display() || getsockopt(wl_display_get_fd(native->display()), SOL_SOCKET, SO_PEERCRED, &compositor, &length)
        || compositor.uid != geteuid() || compositor.pid <= 1) { *error = QStringLiteral("Wayland 显示归属无效。"); return false; }
    m_compositorPid = compositor.pid;
    const auto directory = qEnvironmentVariable("XDG_RUNTIME_DIR");
    m_socketPath = directory + "/r46h-wm.sock";
    auto safe = [](const QString &path, bool folder, mode_t mode) {
        struct stat st{};
        return ::lstat(QFile::encodeName(path).constData(), &st) == 0 && st.st_uid == geteuid()
            && (folder ? S_ISDIR(st.st_mode) : S_ISSOCK(st.st_mode)) && (st.st_mode & 0777) == mode;
    };
    struct stat st{};
    if (!QDir::isAbsolutePath(directory) || !safe(directory, true, 0700) || !safe(m_socketPath, false, 0600)
        || !QDir::isAbsolutePath(router) || ::lstat(QFile::encodeName(router).constData(), &st) || !S_ISREG(st.st_mode)
        || (st.st_uid != geteuid() && st.st_uid != 0) || (st.st_mode & 0022) || !QFileInfo(router).isExecutable()
        || !QDir::isAbsolutePath(device)) { *error = QStringLiteral("共享桌面运行路径或权限不正确。"); return false; }
    int channel[2];
    if (::socketpair(AF_UNIX, SOCK_SEQPACKET | SOCK_CLOEXEC, 0, channel)) { *error = QStringLiteral("无法创建输入通道。"); return false; }
    m_control = channel[0]; const int child = channel[1];
    m_router.setChildProcessModifier([child, uinputFd] {
        if (::fcntl(child, F_SETFD, 0) < 0 || (uinputFd >= 0 && ::fcntl(uinputFd, F_SETFD, 0) < 0)) ::_exit(127);
    });
    QStringList arguments{device, QString::number(child), "120"};
    if (uinputFd >= 0) arguments.append(QString::number(uinputFd));
    m_router.start(router, arguments);
    // Startup is bounded before showing the UI. All steady-state IO is asynchronous.
    const bool started = m_router.waitForStarted(1500); ::close(child);
    if (uinputFd >= 0) ::close(uinputFd);
    if (!started) { *error = QStringLiteral("无法启动输入路由。"); return false; }
    m_notifier = std::make_unique<QSocketNotifier>(m_control, QSocketNotifier::Read, this);
    connect(m_notifier.get(), &QSocketNotifier::activated, this, &HandheldSession::readInput);
    m_inputDeadline.start(); requestPolicy(); return true;
#endif
}
void HandheldSession::readInput() {
#ifdef Q_OS_LINUX
    for (int count = 0; count < 256 && !m_failed; ++count) {
        Route::Packet packet{};
        const auto size = ::recv(m_control, &packet, sizeof(packet), MSG_DONTWAIT | MSG_TRUNC);
        if (size < 0 && errno == EINTR) continue;
        if (size < 0 && errno == EAGAIN) return;
        if (size != sizeof(packet) || packet.version != Route::Version || packet.reserved || packet.mode > Route::Game
            || packet.flags & ~(Route::WaitingNeutral | Route::WaitingOwner | Route::InjectionCancelled) || packet.sequence > m_inputSequence) {
            fail(QStringLiteral("输入通道状态无效。")); return;
        }
        if ((packet.type == Route::InjectDone || packet.type == Route::InjectDenied) && packet.sequence == m_remoteSequence) {
            m_remoteSequence = 0;
            emit gameInputFinished(packet.type == Route::InjectDenied ? "unavailable" : packet.flags & Route::InjectionCancelled ? "cancelled" : "completed");
        } else if (packet.type == Route::Ready && !m_routerReady) {
            m_routerReady = true; m_inputDeadline.stop(); synchronize();
        } else if (packet.type == Route::State) {
            // Old reports can be queued while an ownership change is awaiting its ack.
            if (packet.sequence == m_inputSequence && packet.mode == Route::Ui && m_inputRequested < 0)
                m_input->routedState(packet.keys, packet.axes);
        } else if (packet.type == Route::Ack && packet.sequence == m_modeSequence && int(packet.mode) == m_inputRequested) {
            m_inputMode = m_inputRequested; m_inputRequested = -1; m_inputDeadline.stop(); synchronize();
        } else if (packet.type == Route::Panel) {
            auto *root = m_view->rootObject();
            // The router is already neutral and paused; policy then grants the next owner.
            m_inputMode = -1; m_input->suppressUntilNeutral();
            if (m_applications->running()) root->setProperty("quickOpen", !root->property("quickOpen").toBool());
            else QMetaObject::invokeMethod(root, "dispatch", Q_ARG(QVariant, QString("quick")), Q_ARG(QVariant, false));
            synchronize();
        } else { fail(QStringLiteral("输入通道消息顺序无效。")); return; }
    }
#endif
}
void HandheldSession::selectInput(bool ui) {
#ifdef Q_OS_LINUX
    const int mode = ui ? Route::Ui : Route::Game;
    if (!m_routerReady || m_inputRequested >= 0 || m_inputMode == mode || m_failed) return;
    Route::Packet packet; packet.type = Route::Mode; packet.mode = mode; packet.sequence = ++m_inputSequence;
    m_modeSequence = packet.sequence; // A later cancellation may advance the channel before this mode ack arrives.
    if (::send(m_control, &packet, sizeof(packet), MSG_NOSIGNAL | MSG_DONTWAIT) != sizeof(packet)) {
        fail(QStringLiteral("无法切换输入归属。")); return;
    }
    m_input->suppressUntilNeutral();
    const qint32 neutral[4]{}; m_input->routedState(0, neutral);
    m_inputRequested = mode; m_inputDeadline.start();
#else
    Q_UNUSED(ui);
#endif
}
void HandheldSession::synchronize() {
    if (m_failed) return;
    requestPolicy();
}
void HandheldSession::sceneChanged() {
    // A visible telemetry/volume overlay is not an input surface. USB pointer
    // events must reach the foreground app until the quick panel explicitly opens.
    m_view->setFlag(Qt::WindowTransparentForInput, m_applications->running()
        && !m_view->rootObject()->property("quickOpen").toBool());
    // A low-priority sample must never delay an input/privacy transition.
    if (m_pending && m_request.value("op") == QJsonValue("observe")) {
        m_pending = false; m_deadline.stop(); m_policy.abort();
    }
    updateFrameSampling();
    ++m_sceneEpoch;
    cancelGameInput();
    if (m_capturePhase != Idle) cancelCapture(m_view->rootObject()->property("sensitiveVisible").toBool() ? "sensitive_entry" : "capture_failed");
    synchronize();
}
void HandheldSession::updateFrameSampling() {
    const auto *root = m_view->rootObject();
    const qint64 game = !m_failed && root && m_view->isVisible() && m_view->visibility() != QWindow::Minimized
        ? m_applications->processId() : 0;
    if (game == m_frameGame && m_frameTimer.isActive() == (game > 1)) return;
    m_frameGame = game; m_previousFrames = {}; m_frameSampleDue = game > 1;
    m_frameMetrics = {{"active", game > 1}, {"submissions", -1}, {"intervalMedianMs", -1}, {"intervalP95Ms", -1},
        {"intervalMaxMs", -1}, {"lastFrameAgeMs", -1}, {"outputRefreshHz", -1}};
    if (game > 1) m_frameTimer.start(); else m_frameTimer.stop();
    emit frameMetricsChanged();
}
void HandheldSession::frameSampleFailed() {
    m_pending = false; m_deadline.stop(); m_policy.abort();
    m_frameGame = 0; updateFrameSampling(); // Retry on the next timer tick, not in a tight loop.
}
void HandheldSession::readFrameMetrics() {
    if (!m_frameTimer.isActive() || m_state.value("gamePid").toInteger() != m_frameGame) return;
    const auto value = m_state.value("frameStats").toObject();
    for (const auto *key : {"surfaceId", "bufferCommits", "sampledAtMs", "intervalMedianMs", "intervalP95Ms", "intervalMaxMs", "lastFrameAgeMs", "outputRefreshHz"}) {
        const double number = value.value(key).toDouble(-2);
        const bool integer = QStringList{"surfaceId", "bufferCommits", "sampledAtMs"}.contains(key);
        if (!value.value(key).isDouble() || !std::isfinite(number) || number < (integer ? 0 : -1) || number > 1e15 || (integer && number != std::floor(number))) {
            m_previousFrames = {};
            for (auto it = m_frameMetrics.begin(); it != m_frameMetrics.end(); ++it) if (it.key() != "active") it.value() = -1;
            emit frameMetricsChanged(); return;
        }
    }
    const auto elapsed = value.value("sampledAtMs").toInteger() - m_previousFrames.value("sampledAtMs").toInteger();
    const auto frames = value.value("bufferCommits").toInteger() - m_previousFrames.value("bufferCommits").toInteger();
    m_frameMetrics["submissions"] = !m_previousFrames.isEmpty() && value.value("surfaceId") == m_previousFrames.value("surfaceId")
        && elapsed > 0 && frames >= 0 ? frames * 1000. / elapsed : -1;
    for (const auto *key : {"intervalMedianMs", "intervalP95Ms", "intervalMaxMs", "lastFrameAgeMs", "outputRefreshHz"}) m_frameMetrics[key] = value.value(key);
    m_previousFrames = value; emit frameMetricsChanged();
}
bool HandheldSession::gameInputAvailable() const {
    const auto *root = m_view->rootObject();
    return !m_failed && m_ready && m_routerReady && !m_remoteSequence && m_inputRequested < 0 && m_inputMode == Route::Game
        && m_applications->processId() > 1 && root && !root->property("quickOpen").toBool()
        && !root->property("panelVisible").toBool() && !root->property("sensitiveVisible").toBool();
}
bool HandheldSession::injectGame(quint32 keys, const qint32 axes[4], int milliseconds, quint64 expectedSequence, const QString &application) {
#ifdef Q_OS_LINUX
    if (!gameInputAvailable() || expectedSequence != m_inputSequence || application != m_applications->activeId()
        || milliseconds < 10 || milliseconds > 1000 || keys & ~0xffffU || (keys & Route::Chord) == Route::Chord
        || m_inputSequence >= 9007199254740991ULL) return false;
    for (int i = 0; i < 4; ++i) if (axes[i] < -32767 || axes[i] > 32767) return false;
    Route::Packet packet; packet.type = Route::Inject; packet.mode = Route::Game;
    packet.flags = milliseconds; packet.keys = keys; std::copy(axes, axes + 4, packet.axes);
    packet.sequence = ++m_inputSequence; m_remoteSequence = packet.sequence;
    if (::send(m_control, &packet, sizeof(packet), MSG_NOSIGNAL | MSG_DONTWAIT) != sizeof(packet)) {
        fail(QStringLiteral("无法提交短时游戏输入。")); return false;
    }
    return true;
#else
    Q_UNUSED(keys); Q_UNUSED(axes); Q_UNUSED(milliseconds); Q_UNUSED(expectedSequence); Q_UNUSED(application);
    return false;
#endif
}
void HandheldSession::cancelGameInput() {
#ifdef Q_OS_LINUX
    if (!m_remoteSequence || m_failed) return;
    Route::Packet packet; packet.type = Route::CancelInject; packet.mode = Route::Game; packet.sequence = ++m_inputSequence;
    if (::send(m_control, &packet, sizeof(packet), MSG_NOSIGNAL | MSG_DONTWAIT) != sizeof(packet)) fail(QStringLiteral("无法释放远程游戏输入。"));
#endif
}
void HandheldSession::requestPolicy() {
    if (m_pending || m_failed) return;
    auto *root = m_view->rootObject();
    if (!root) return;
    const qint64 game = m_applications->processId();
    const bool panel = game && root->property("quickOpen").toBool();
    const bool volume = game && root->property("volumeVisible").toBool();
    const bool overlay = game && (root->property("panelVisible").toBool() || root->property("monitorVisible").toBool() || volume);
    const bool privacy = m_capturePhase != Permit && m_capturePhase != Reading;
    QJsonObject request{{"version", 1}};
    if (m_state.isEmpty()) request["op"] = "hello";
    else if (m_state.value("privacy").toBool() != privacy) { request["op"] = "privacy"; request["active"] = privacy; }
    else if (m_state.value("gamePid").toInteger() != game) { request["op"] = "game"; request["pid"] = game; }
    else if (m_state.value("panel").toBool() != panel) { request["op"] = "panel"; request["active"] = panel; }
    else if (m_state.value("overlay").toBool() != overlay || m_state.value("volume").toBool() != volume) {
        request["op"] = "overlay"; request["active"] = overlay; request["volume"] = volume;
    }
    else if (m_frameSampleDue && m_ready && m_capturePhase == Idle) { request["op"] = "observe"; m_frameSampleDue = false; }
    else {
        if (m_capturePhase == Permit) readCapture();
        if (m_capturePhase == Closing && !m_captureThread) finishCapture();
        selectInput(!game || panel);
        const bool ready = m_routerReady && m_inputRequested < 0;
        if (m_ready != ready) { m_ready = ready; emit changed(); }
        return;
    }
    if (!m_state.isEmpty() && request.value("op") != QJsonValue("observe")) { request["session"] = m_state.value("session"); request["sequence"] = m_state.value("sequence"); }
    m_request = request; m_response.clear(); m_pending = true;
    if (m_ready && request.value("op") != QJsonValue("privacy") && request.value("op") != QJsonValue("observe")) { m_ready = false; emit changed(); }
    m_policy.abort(); m_policy.connectToServer(m_socketPath); m_deadline.start();
}
void HandheldSession::readPolicy() {
    if (!m_pending || m_failed) return;
    m_response += m_policy.readAll();
    if (m_response.size() > 65536) { fail(QStringLiteral("合成器响应超出限制。")); return; }
    if (!m_response.endsWith('\n')) return;
    const auto document = QJsonDocument::fromJson(m_response);
    const auto response = document.object();
    m_pending = false; m_deadline.stop(); m_policy.abort();
    if (!document.isObject()) { fail(QStringLiteral("合成器响应无效。")); return; }
    if (response.value("error") == QJsonValue("stale_state") && ++m_retries <= 4) {
        // A new/removed surface changes the generation. Re-claim our own UI to refresh it.
        m_state = {}; requestPolicy(); return;
    }
    if (!response.value("ok").toBool() || response.value("session").toString().isEmpty()
        || response.value("uiPid").toInteger() != QCoreApplication::applicationPid() || !response.value("privacy").isBool()) {
        // Protocol metadata only: never log page contents, URLs or full replies.
        qWarning("HANDHELD_POLICY_REJECT op=%s error=%s retries=%d ok=%d session_present=%d ui_matches=%d privacy_boolean=%d",
            qPrintable(m_request.value("op").toString()), qPrintable(response.value("error").toString().left(64)), m_retries,
            response.value("ok").toBool(), !response.value("session").toString().isEmpty(),
            response.value("uiPid").toInteger() == QCoreApplication::applicationPid(), response.value("privacy").isBool());
        fail(QStringLiteral("合成器归属或隐私状态无效。")); return;
    }
    if (m_request.value("op") != QJsonValue("hello")) m_retries = 0;
    m_state = response;
    if (m_request.value("op") == QJsonValue("observe")) readFrameMetrics();
    requestPolicy();
}

bool HandheldSession::requestCapture() {
    if (m_capturePhase != Idle || m_failed) return false;
    const auto *root = m_view->rootObject();
    if (!m_ready || !root) { emit captureFinished({}, "window_unavailable"); return true; }
    if (root->property("sensitiveVisible").toBool()) { emit captureFinished({}, "sensitive_entry"); return true; }
    m_captureEpoch = m_sceneEpoch; ++m_captureId;
    m_captureImage = {}; m_captureError.clear(); m_frameSynced = false;
    m_capturePhase = Frame; m_captureDeadline.start();
    if (qEnvironmentVariable("R46H_SHELL_LOG") == "1") qInfo("HANDHELD_CAPTURE_BEGIN id=%llu", static_cast<unsigned long long>(m_captureId));
    // A hidden UI contributes no pixels; the acknowledged policy must agree.
    if (m_state.value("gamePid").toInteger() && !m_state.value("panel").toBool() && !m_state.value("overlay").toBool()) {
        fenceCapture(); return true;
    }
    const auto token = m_captureId;
    m_syncConnection = connect(m_view, &QQuickWindow::afterSynchronizing, this, [this, token] {
        if (token == m_captureId && m_capturePhase == Frame) m_frameSynced = true;
    }, Qt::QueuedConnection);
    m_frameConnection = connect(m_view, &QQuickWindow::frameSwapped, this, [this, token] {
        if (token == m_captureId && m_capturePhase == Frame && m_frameSynced) fenceCapture();
    }, Qt::QueuedConnection);
    m_view->update(); return true;
}
void HandheldSession::fenceCapture() {
    disconnect(m_syncConnection); disconnect(m_frameConnection);
    if (m_captureEpoch != m_sceneEpoch || m_view->rootObject()->property("sensitiveVisible").toBool()) { cancelCapture("sensitive_entry"); return; }
#ifdef Q_OS_LINUX
    auto *native = qGuiApp->nativeInterface<QNativeInterface::QWaylandApplication>();
    if (!native || !native->display()) { cancelCapture("capture_failed"); return; }
    m_capturePhase = Fence;
    if (qEnvironmentVariable("R46H_SHELL_LOG") == "1") qInfo("HANDHELD_CAPTURE_FENCE id=%llu", static_cast<unsigned long long>(m_captureId));
    // Sync the SAME connection that submitted Qt's public surface, without blocking Qt.
    m_fence = wl_display_sync(native->display());
    if (!m_fence) { cancelCapture("capture_failed"); return; }
    static const wl_callback_listener listener{[](void *data, wl_callback *callback, uint32_t) {
        auto *self = static_cast<HandheldSession *>(data);
        self->m_fence = nullptr; wl_callback_destroy(callback);
        if (self->m_capturePhase == Fence) { self->m_capturePhase = Permit; self->requestPolicy(); }
    }};
    wl_callback_add_listener(m_fence, &listener, this);
    if (wl_display_flush(native->display()) < 0 && errno != EAGAIN) cancelCapture("capture_failed");
#else
    cancelCapture("capture_failed");
#endif
}
void HandheldSession::readCapture() {
#ifdef Q_OS_LINUX
    if (m_captureEpoch != m_sceneEpoch || m_captureThread) { cancelCapture("capture_failed"); return; }
    m_capturePhase = Reading;
    m_captureThread = QThread::create([this] {
        const auto result = captureOutput(1200, m_compositorPid);
        QMetaObject::invokeMethod(this, [this, result] {
            m_captureThread->wait(); delete m_captureThread; m_captureThread = nullptr;
            if (m_capturePhase == Idle || m_failed) return;
            if (m_captureEpoch != m_sceneEpoch || m_view->rootObject()->property("sensitiveVisible").toBool()) m_captureError = "sensitive_entry";
            else if (!result.error.isEmpty() && m_captureError.isEmpty()) m_captureError = "capture_failed";
            if (m_captureError.isEmpty()) m_captureImage = result.image;
            m_capturePhase = Closing; requestPolicy();
        }, Qt::QueuedConnection);
    });
    m_captureThread->start();
#else
    cancelCapture("capture_failed");
#endif
}
void HandheldSession::cancelCapture(const QString &error) {
    if (m_capturePhase == Idle) return;
    disconnect(m_syncConnection); disconnect(m_frameConnection);
#ifdef Q_OS_LINUX
    if (m_fence) { wl_callback_destroy(m_fence); m_fence = nullptr; }
#endif
    m_captureImage = {}; m_captureError = error; m_capturePhase = Closing;
    requestPolicy();
}
void HandheldSession::finishCapture() {
    m_captureDeadline.stop();
    const auto image = m_captureImage; const auto error = m_captureError;
    m_capturePhase = Idle; m_captureImage = {};
    emit captureFinished(image, error);
}
