// A single-output fullscreen policy over the retained Weston 14 compositor.
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <libweston/libweston.h>
#include <libweston/desktop.h>
#include <QByteArray>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QList>
#include <QStringList>
#include <QUuid>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <unistd.h>
#include <cerrno>
#include <cmath>
#include <chrono>
#include <array>
#include <algorithm>

struct Shell;
struct Watch { wl_listener listener; Shell *shell; };
struct SeatWatch { wl_listener caps, destroy; Shell *shell; };
struct View {
    weston_desktop_surface *desktop;
    weston_view *view;
    pid_t pid;
    bool mapped = false;
    quint64 id = 0, bufferCommits = 0;
    qint64 lastBufferNs = 0;
    std::array<qint64, 120> intervals{};
    size_t intervalCount = 0, intervalNext = 0;
};
struct Request {
    Shell *shell;
    int fd;
    pid_t pid;
    QByteArray input;
    wl_event_source *source = nullptr, *timer = nullptr;
};
struct Shell {
    weston_compositor *compositor;
    weston_desktop *desktop = nullptr;
    weston_layer hidden, game, ui;
    Watch destroy, output, capture, seatCreated;
    QList<SeatWatch *> seats;
    QList<View *> views;
    QList<Request *> requests;
    int listener = -1;
    wl_event_source *source = nullptr;
    QByteArray socketPath;
    dev_t socketDevice = 0;
    ino_t socketInode = 0;
    pid_t uiPid = 0, controlPid = 0, gamePid = 0;
    bool panel = false, overlay = false, volume = false, privacy = true, destroying = false;
    int64_t captureUntil = 0;
    qint64 sequence = 0;
    quint64 nextViewId = 1;
    QString session = QUuid::createUuid().toString(QUuid::WithoutBraces);
};

static weston_output *firstOutput(Shell *shell)
{
    if (wl_list_empty(&shell->compositor->output_list)) return nullptr;
    return wl_container_of(shell->compositor->output_list.next, static_cast<weston_output *>(nullptr), link);
}

static bool descendant(pid_t pid, pid_t ancestor)
{
    // Trusted launcher supplies the foreground parent; its normal children may own the surface.
    for (int depth = 0; ancestor > 1 && pid > 1 && depth < 16; ++depth) {
        if (pid == ancestor) return true;
        QFile file(QString("/proc/%1/stat").arg(pid));
        if (!file.open(QIODevice::ReadOnly)) break;
        const auto line = file.read(4096);
        const auto fields = line.mid(line.lastIndexOf(')') + 2).split(' ');
        if (fields.size() < 2) break;
        bool ok = false; const int parent = fields[1].toInt(&ok);
        if (!ok || parent == pid) break;
        pid = parent;
    }
    return false;
}

static bool gameClient(Shell *shell, pid_t pid) { return descendant(pid, shell->gamePid); }

static void arrange(Shell *shell)
{
    auto *output = firstOutput(shell);
    if (!output) return;
    View *focus = nullptr;
    bool hasGame = false;
    for (auto *item : shell->views) hasGame |= item->mapped && gameClient(shell, item->pid);
    for (auto *item : shell->views) {
        if (!item->mapped) continue;
        const bool isUi = shell->uiPid && item->pid == shell->uiPid;
        const bool isGame = gameClient(shell, item->pid);
        auto *layer = isUi && (!hasGame || shell->panel || shell->overlay) ? &shell->ui : isGame ? &shell->game : &shell->hidden;
        weston_view_move_to_layer(item->view, &layer->view_list);
        weston_desktop_surface_propagate_layer(item->desktop);
        weston_view_set_output(item->view, output);
        weston_view_set_position(item->view, output->pos);
        if (isUi && hasGame && shell->overlay && !shell->panel
            && (shell->compositor->capabilities & WESTON_CAP_VIEW_CLIP_MASK)) {
            // Include the top-center volume capsule only while it is visible.
            // Otherwise retain the accepted narrow performance-HUD blend region.
            const int left = shell->volume ? 396 : 624;
            weston_view_set_mask(item->view, output->width * left / 1024, output->height * 16 / 768,
                (output->width * (992 - left) + 1023) / 1024, (output->height * 260 + 767) / 768);
        } else if (isUi) weston_view_set_mask_infinite(item->view);
        weston_view_update_transform(item->view);
        const bool active = isUi ? (!hasGame || shell->panel) : isGame && !shell->panel;
        weston_desktop_surface_set_activated(item->desktop, active);
        if (active) focus = item;
    }
    if (focus) {
        weston_seat *seat;
        wl_list_for_each(seat, &shell->compositor->seat_list, link)
            weston_view_activate_input(focus->view, seat, WESTON_ACTIVATE_FLAG_NONE);
    }
    weston_compositor_schedule_repaint(shell->compositor);
}

static void seatRemoved(wl_listener *listener, void *)
{
    auto *watch = wl_container_of(listener, static_cast<SeatWatch *>(nullptr), destroy);
    wl_list_remove(&watch->caps.link); wl_list_remove(&watch->destroy.link);
    watch->shell->seats.removeOne(watch); delete watch;
}
static void seatCapabilities(wl_listener *listener, void *)
{
    auto *watch = wl_container_of(listener, static_cast<SeatWatch *>(nullptr), caps);
    // A keyboard first connected after the UI mapped has no previous focus.
    arrange(watch->shell);
}
static void watchSeat(Shell *shell, weston_seat *seat)
{
    auto *watch = new SeatWatch{}; watch->shell = shell;
    watch->caps.notify = seatCapabilities; watch->destroy.notify = seatRemoved;
    wl_signal_add(&seat->updated_caps_signal, &watch->caps);
    wl_signal_add(&seat->destroy_signal, &watch->destroy);
    shell->seats.append(watch); arrange(shell);
}
static void seatCreated(wl_listener *listener, void *data)
{ watchSeat(reinterpret_cast<Watch *>(listener)->shell, static_cast<weston_seat *>(data)); }

static void sizeSurface(Shell *shell, weston_desktop_surface *surface)
{
    auto *output = firstOutput(shell);
    weston_desktop_surface_set_fullscreen(surface, true);
    if (output) weston_desktop_surface_set_size(surface, output->width, output->height);
}
static void added(weston_desktop_surface *surface, void *data)
{
    auto *shell = static_cast<Shell *>(data);
    if (shell->views.size() >= 64) { weston_desktop_surface_close(surface); return; }
    auto *view = weston_desktop_surface_create_view(surface);
    if (!view) return;
    auto *item = new View{surface, view, weston_desktop_surface_get_pid(surface)};
    item->id = shell->nextViewId++;
    weston_desktop_surface_set_user_data(surface, item);
    shell->views.append(item);
    sizeSurface(shell, surface);
}
static void removed(weston_desktop_surface *surface, void *data)
{
    auto *shell = static_cast<Shell *>(data);
    auto *item = static_cast<View *>(weston_desktop_surface_get_user_data(surface));
    if (!item) return;
    weston_desktop_surface_set_user_data(surface, nullptr);
    shell->views.removeOne(item);
    if (item->pid == shell->uiPid) { shell->privacy = true; shell->captureUntil = 0; }
    weston_desktop_surface_unlink_view(item->view);
    weston_view_destroy(item->view);
    delete item;
    ++shell->sequence;
    if (!shell->destroying) arrange(shell);
}
static void committed(weston_desktop_surface *desktop, struct weston_coord_surface, void *data)
{
    auto *shell = static_cast<Shell *>(data);
    auto *item = static_cast<View *>(weston_desktop_surface_get_user_data(desktop));
    auto *surface = weston_desktop_surface_get_surface(desktop);
    if (!item) return;
    if (surface->width == 0 || surface->height == 0) {
        if (item->mapped) { item->mapped = false; weston_view_move_to_layer(item->view, &shell->hidden.view_list); ++shell->sequence; arrange(shell); }
        return;
    }
    // Desktop callbacks run before Weston clears pending.status. Count only
    // new buffer submissions, not focus/geometry commits or compositor repaints.
    if (surface->pending.status & WESTON_SURFACE_DIRTY_BUFFER) {
        const qint64 now = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
        if (item->lastBufferNs && now > item->lastBufferNs) {
            item->intervals[item->intervalNext] = now - item->lastBufferNs;
            item->intervalNext = (item->intervalNext + 1) % item->intervals.size();
            item->intervalCount = std::min(item->intervalCount + 1, item->intervals.size());
        }
        item->lastBufferNs = now; ++item->bufferCommits;
    }
    if (!item->mapped) {
        weston_surface_map(surface);
        item->mapped = true; ++shell->sequence; arrange(shell);
    }
}
static void fullscreen(weston_desktop_surface *surface, bool, weston_output *, void *data)
{ sizeSurface(static_cast<Shell *>(data), surface); }
static void maximized(weston_desktop_surface *surface, bool, void *data)
{ sizeSurface(static_cast<Shell *>(data), surface); }
static void outputChanged(wl_listener *listener, void *)
{
    auto *shell = reinterpret_cast<Watch *>(listener)->shell;
    for (auto *item : shell->views) sizeSurface(shell, item->desktop);
    arrange(shell);
}
static void captureAllowed(wl_listener *listener, weston_output_capture_attempt *attempt)
{
    auto *shell = reinterpret_cast<Watch *>(listener)->shell;
    pid_t pid; wl_client_get_credentials(attempt->who->client, &pid, nullptr, nullptr);
    const auto now = std::chrono::steady_clock::now().time_since_epoch();
    if (!shell->privacy && std::chrono::duration_cast<std::chrono::milliseconds>(now).count() <= shell->captureUntil
        && shell->uiPid && (pid == shell->uiPid || pid == shell->controlPid)) attempt->authorized = true;
    else attempt->denied = true;
}

static QJsonObject status(Shell *shell)
{
    QJsonArray views;
    View *measured = nullptr;
    qint64 area = -1;
    for (auto *item : shell->views) {
        const auto role = shell->uiPid && item->pid == shell->uiPid ? "ui" : gameClient(shell, item->pid) ? "game" : "unassigned";
        auto *surface = weston_desktop_surface_get_surface(item->desktop);
        views.append(QJsonObject{{"pid", int(item->pid)}, {"role", role}, {"mapped", item->mapped}, {"width", surface->width}, {"height", surface->height}});
        if (item->mapped && gameClient(shell, item->pid) && !weston_desktop_surface_get_parent(item->desktop)
            && qint64(surface->width) * surface->height >= area) {
            measured = item; area = qint64(surface->width) * surface->height;
        }
    }
    const auto now = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
    QJsonObject frames;
    if (measured) {
        auto sorted = measured->intervals;
        std::sort(sorted.begin(), sorted.begin() + measured->intervalCount);
        const bool recent = measured->lastBufferNs && now - measured->lastBufferNs <= 2000000000LL && measured->intervalCount;
        auto *output = firstOutput(shell);
        frames = {{"surfaceId", qint64(measured->id)}, {"bufferCommits", qint64(measured->bufferCommits)}, {"sampledAtMs", qint64(now / 1000000)},
            {"lastFrameAgeMs", measured->lastBufferNs ? double(now - measured->lastBufferNs) / 1e6 : -1},
            {"intervalMedianMs", recent ? (double(sorted[(measured->intervalCount - 1) / 2]) + double(sorted[measured->intervalCount / 2])) / 2e6 : -1},
            {"intervalP95Ms", recent ? double(sorted[(measured->intervalCount * 95 + 99) / 100 - 1]) / 1e6 : -1},
            {"intervalMaxMs", recent ? double(sorted[measured->intervalCount - 1]) / 1e6 : -1},
            {"outputRefreshHz", output && output->current_mode ? output->current_mode->refresh / 1000. : -1}};
    }
    return {{"version", 1}, {"session", shell->session}, {"sequence", shell->sequence}, {"uiPid", int(shell->uiPid)},
            {"gamePid", int(shell->gamePid)}, {"panel", shell->panel}, {"overlay", shell->overlay}, {"volume", shell->volume}, {"privacy", shell->privacy}, {"surfaces", views}, {"frameStats", frames}};
}
static void finish(Request *request, const QJsonObject &response)
{
    const auto bytes = QJsonDocument(response).toJson(QJsonDocument::Compact) + '\n';
    (void)send(request->fd, bytes.constData(), size_t(bytes.size()), MSG_NOSIGNAL);
    request->shell->requests.removeOne(request);
    if (request->source) wl_event_source_remove(request->source);
    if (request->timer) wl_event_source_remove(request->timer);
    close(request->fd); delete request;
}
static int requestTimeout(void *data)
{ finish(static_cast<Request *>(data), {{"ok", false}, {"error", "timeout"}}); return 0; }
static int receive(int fd, uint32_t, void *data)
{
    auto *request = static_cast<Request *>(data);
    auto *shell = request->shell;
    char buffer[4097]; const auto size = recv(fd, buffer, sizeof(buffer), 0);
    if (size <= 0) {
        if (size < 0 && (errno == EAGAIN || errno == EINTR)) return 0;
        finish(request, {{"ok", false}, {"error", "disconnected"}}); return 0;
    }
    request->input.append(buffer, int(size));
    if (request->input.size() > 4096) { finish(request, {{"ok", false}, {"error", "too_large"}}); return 0; }
    if (!request->input.endsWith('\n')) return 0;
    const auto document = QJsonDocument::fromJson(request->input);
    const auto object = document.object(); const auto operation = object.value("op").toString();
    auto fail = [&](const char *message) { finish(request, {{"ok", false}, {"error", message}}); };
    QStringList fields {"version", "op"};
    if (operation == "hello") fields.append("uiPid");
    if (operation == "overlay") fields.append("volume");
    if (operation != "observe" && operation != "hello") fields.append({"session", "sequence", operation == "game" ? "pid" : "active"});
    if (!document.isObject() || object.value("version") != QJsonValue(1)) { fail("invalid_request"); return 0; }
    for (auto it = object.begin(); it != object.end(); ++it) if (!fields.contains(it.key())) { fail("unknown_field"); return 0; }
    if (!QStringList{"observe", "hello", "game", "panel", "overlay", "privacy"}.contains(operation)) { fail("unknown_operation"); return 0; }
    if (operation != "observe" && shell->sequence >= 9007199254740991LL) { fail("sequence_exhausted"); return 0; }
    if (operation == "hello") {
        if (shell->controlPid && shell->controlPid != request->pid) { fail("owner_exists"); return 0; }
        const double proposed = object.contains("uiPid") ? object.value("uiPid").toDouble(-1) : request->pid;
        if (!std::isfinite(proposed) || proposed < 2 || proposed > 4194304 || proposed != std::floor(proposed)
            || !descendant(pid_t(proposed), request->pid)) { fail("invalid_ui_owner"); return 0; }
        shell->controlPid = request->pid; shell->uiPid = pid_t(proposed); ++shell->sequence; arrange(shell);
    } else if (operation != "observe") {
        if (!shell->uiPid || request->pid != shell->controlPid) { fail("wrong_owner"); return 0; }
        if (object.value("session").toString() != shell->session || !object.value("sequence").isDouble() || object.value("sequence").toDouble() != double(shell->sequence)) { fail("stale_state"); return 0; }
        if (operation == "game") {
            const double value = object.value("pid").toDouble(-1);
            if (!std::isfinite(value) || value < 0 || value > 4194304 || value != std::floor(value)) { fail("invalid_pid"); return 0; }
            struct stat st{};
            if (value && (::stat(qPrintable(QString("/proc/%1").arg(int(value))), &st) || st.st_uid != geteuid())) { fail("wrong_game_owner"); return 0; }
            shell->gamePid = pid_t(value); shell->panel = false;
        } else {
            if (!object.value("active").isBool()) { fail("invalid_state"); return 0; }
            if (operation == "panel") shell->panel = object.value("active").toBool();
            else if (operation == "overlay") {
                if (object.contains("volume") && !object.value("volume").isBool()) { fail("invalid_state"); return 0; }
                shell->overlay = object.value("active").toBool();
                shell->volume = shell->overlay && object.value("volume").toBool();
            }
            else {
                shell->privacy = object.value("active").toBool();
                shell->captureUntil = shell->privacy ? 0 : std::chrono::duration_cast<std::chrono::milliseconds>(
                    std::chrono::steady_clock::now().time_since_epoch()).count() + 2500;
            }
        }
        ++shell->sequence; arrange(shell);
    }
    auto response = status(shell); response["ok"] = true; finish(request, response);
    return 0;
}
static int acceptRequest(int fd, uint32_t, void *data)
{
    auto *shell = static_cast<Shell *>(data);
    int client = accept4(fd, nullptr, nullptr, SOCK_NONBLOCK | SOCK_CLOEXEC);
    if (client < 0) return 0;
    ucred peer{}; socklen_t size = sizeof(peer);
    if (shell->requests.size() >= 4 || getsockopt(client, SOL_SOCKET, SO_PEERCRED, &peer, &size) || peer.uid != geteuid()) { close(client); return 0; }
    auto *request = new Request{shell, client, peer.pid, {}};
    auto *loop = wl_display_get_event_loop(shell->compositor->wl_display);
    request->source = wl_event_loop_add_fd(loop, client, WL_EVENT_READABLE, receive, request);
    request->timer = wl_event_loop_add_timer(loop, requestTimeout, request);
    shell->requests.append(request);
    if (!request->source || !request->timer) { finish(request, {{"ok", false}, {"error", "resource_unavailable"}}); return 0; }
    wl_event_source_timer_update(request->timer, 3000);
    return 0;
}
static void destroy(wl_listener *listener, void *)
{
    auto *shell = reinterpret_cast<Watch *>(listener)->shell;
    wl_list_remove(&shell->destroy.listener.link);
    wl_list_remove(&shell->output.listener.link);
    wl_list_remove(&shell->capture.listener.link);
    wl_list_remove(&shell->seatCreated.listener.link);
    while (!shell->seats.isEmpty()) seatRemoved(&shell->seats.first()->destroy, nullptr);
    while (!shell->requests.isEmpty()) finish(shell->requests.first(), {{"ok", false}, {"error", "shutdown"}});
    if (shell->source) wl_event_source_remove(shell->source);
    if (shell->listener >= 0) close(shell->listener);
    struct stat st{};
    if (!lstat(shell->socketPath.constData(), &st) && st.st_dev == shell->socketDevice && st.st_ino == shell->socketInode) unlink(shell->socketPath.constData());
    shell->destroying = true;
    while (!shell->views.isEmpty()) removed(shell->views.first()->desktop, shell);
    weston_desktop_destroy(shell->desktop);
    weston_layer_fini(&shell->ui); weston_layer_fini(&shell->game); weston_layer_fini(&shell->hidden);
    delete shell;
}

extern "C" __attribute__((visibility("default"))) int wet_shell_init(weston_compositor *compositor, int *, char *[])
{
    const QByteArray directory = qgetenv("XDG_RUNTIME_DIR"); struct stat st{};
    if (directory.isEmpty() || lstat(directory.constData(), &st) || !S_ISDIR(st.st_mode) || st.st_uid != geteuid() || (st.st_mode & 0777) != 0700) { weston_log("R46H shell: private runtime directory check failed\n"); return -1; }
    const QByteArray path = directory + "/r46h-wm.sock";
    sockaddr_un address{}; address.sun_family = AF_UNIX;
    if (path.size() >= int(sizeof(address.sun_path)) || !lstat(path.constData(), &st) || errno != ENOENT) return -1;
    memcpy(address.sun_path, path.constData(), size_t(path.size() + 1));
    int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
    if (fd < 0) { weston_log("R46H shell: socket creation failed\n"); return -1; }
    if (bind(fd, reinterpret_cast<sockaddr *>(&address), sizeof(address))) { close(fd); return -1; }
    if (chmod(path.constData(), 0600) || listen(fd, 4)) { close(fd); unlink(path.constData()); return -1; }
    auto *shell = new Shell{}; shell->compositor = compositor; shell->listener = fd; shell->socketPath = path;
    lstat(path.constData(), &st); shell->socketDevice = st.st_dev; shell->socketInode = st.st_ino;
    weston_layer_init(&shell->hidden, compositor); weston_layer_set_position(&shell->hidden, WESTON_LAYER_POSITION_HIDDEN);
    weston_layer_init(&shell->game, compositor); weston_layer_set_position(&shell->game, WESTON_LAYER_POSITION_FULLSCREEN);
    weston_layer_init(&shell->ui, compositor); weston_layer_set_position(&shell->ui, WESTON_LAYER_POSITION_TOP_UI);
    static const weston_desktop_api api = [] { weston_desktop_api a{}; a.struct_size = sizeof(a); a.surface_added = added; a.surface_removed = removed; a.committed = committed; a.fullscreen_requested = fullscreen; a.maximized_requested = maximized; return a; }();
    shell->desktop = weston_desktop_create(compositor, &api, shell);
    if (!shell->desktop) {
        weston_layer_fini(&shell->ui); weston_layer_fini(&shell->game); weston_layer_fini(&shell->hidden);
        close(fd); unlink(path.constData()); delete shell; return -1;
    }
    shell->destroy.shell = shell; shell->destroy.listener.notify = destroy; wl_signal_add(&compositor->destroy_signal, &shell->destroy.listener);
    shell->output.shell = shell; shell->output.listener.notify = outputChanged; wl_signal_add(&compositor->output_created_signal, &shell->output.listener);
    shell->capture.shell = shell; weston_compositor_add_screenshot_authority(compositor, &shell->capture.listener, captureAllowed);
    shell->seatCreated.shell = shell; shell->seatCreated.listener.notify = seatCreated;
    wl_signal_add(&compositor->seat_created_signal, &shell->seatCreated.listener);
    weston_seat *seat;
    wl_list_for_each(seat, &compositor->seat_list, link) watchSeat(shell, seat);
    shell->source = wl_event_loop_add_fd(wl_display_get_event_loop(compositor->wl_display), fd, WL_EVENT_READABLE, acceptRequest, shell);
    if (!shell->source) { destroy(&shell->destroy.listener, nullptr); return -1; }
    weston_log("R46H handheld shell: fullscreen policy, private control, capture ownership\n");
    return 0;
}
