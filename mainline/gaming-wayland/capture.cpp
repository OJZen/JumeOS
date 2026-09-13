#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "capture.h"
#include "weston-output-capture-client-protocol.h"
#include <QElapsedTimer>
#include <wayland-client.h>
#include <drm_fourcc.h>
#include <sys/mman.h>
#include <poll.h>
#include <unistd.h>
#include <cstring>
#include <sys/socket.h>

namespace {
struct State {
    wl_display *display = nullptr;
    wl_registry *registry = nullptr;
    wl_output *output = nullptr;
    wl_shm *shm = nullptr;
    weston_capture_v1 *factory = nullptr;
    weston_capture_source_v1 *source = nullptr;
    wl_buffer *buffer = nullptr;
    wl_callback *sync = nullptr;
    uint32_t format = 0;
    int width = 0, height = 0;
    bool syncDone = false, done = false;
    QString error;
};
void outputGeometry(void *, wl_output *, int32_t, int32_t, int32_t, int32_t, int32_t, const char *, const char *, int32_t) {}
void outputMode(void *, wl_output *, uint32_t, int32_t, int32_t, int32_t) {}
void outputDone(void *, wl_output *) {}
void outputScale(void *, wl_output *, int32_t) {}
void outputName(void *, wl_output *, const char *) {}
const wl_output_listener outputListener = {outputGeometry, outputMode, outputDone, outputScale, outputName, outputName};
void shmFormat(void *, wl_shm *, uint32_t) {}
const wl_shm_listener shmListener = {shmFormat};
void global(void *data, wl_registry *registry, uint32_t name, const char *interface, uint32_t version)
{
    auto &state = *static_cast<State *>(data);
    if (!strcmp(interface, "wl_output") && !state.output) { state.output = static_cast<wl_output *>(wl_registry_bind(registry, name, &wl_output_interface, qMin(version, 2u))); wl_output_add_listener(state.output, &outputListener, &state); }
    else if (!strcmp(interface, "wl_shm")) { state.shm = static_cast<wl_shm *>(wl_registry_bind(registry, name, &wl_shm_interface, 1)); wl_shm_add_listener(state.shm, &shmListener, &state); }
    else if (!strcmp(interface, "weston_capture_v1")) state.factory = static_cast<weston_capture_v1 *>(wl_registry_bind(registry, name, &weston_capture_v1_interface, 1));
}
void removed(void *, wl_registry *, uint32_t) {}
const wl_registry_listener registryListener = {global, removed};
void syncDone(void *data, wl_callback *callback, uint32_t)
{ auto &s = *static_cast<State *>(data); s.syncDone = true; s.sync = nullptr; wl_callback_destroy(callback); }
const wl_callback_listener syncListener = {syncDone};
void format(void *data, weston_capture_source_v1 *, uint32_t value) { static_cast<State *>(data)->format = value; }
void size(void *data, weston_capture_source_v1 *, int32_t width, int32_t height) { auto &s = *static_cast<State *>(data); s.width = width; s.height = height; }
void complete(void *data, weston_capture_source_v1 *) { static_cast<State *>(data)->done = true; }
void retry(void *data, weston_capture_source_v1 *) { auto &s = *static_cast<State *>(data); s.error = "capture_resized"; s.done = true; }
void failed(void *data, weston_capture_source_v1 *, const char *message) { auto &s = *static_cast<State *>(data); s.error = QString::fromUtf8(message).left(160); s.done = true; }
const weston_capture_source_v1_listener sourceListener = {format, size, complete, retry, failed};

bool dispatch(State &state, const bool &ready, QElapsedTimer &clock, int timeout)
{
    while (!ready && clock.elapsed() < timeout) {
        if (wl_display_dispatch_pending(state.display) < 0) return false;
        if (ready) return true;
        if (wl_display_prepare_read(state.display) != 0) continue;
        wl_display_flush(state.display);
        pollfd fd{wl_display_get_fd(state.display), POLLIN, 0};
        const int status = poll(&fd, 1, qMax(1, timeout - int(clock.elapsed())));
        if (status > 0 && (fd.revents & POLLIN)) {
            if (wl_display_read_events(state.display) < 0) return false;
        } else {
            wl_display_cancel_read(state.display);
            if (status == 0 || status < 0 || (fd.revents & (POLLERR | POLLHUP))) return false;
        }
    }
    return ready;
}
bool roundtrip(State &state, QElapsedTimer &clock, int timeout)
{
    state.syncDone = false;
    state.sync = wl_display_sync(state.display);
    wl_callback_add_listener(state.sync, &syncListener, &state);
    return dispatch(state, state.syncDone, clock, timeout);
}
}

OutputCapture captureOutput(int timeoutMs, qint64 expectedCompositor)
{
    OutputCapture result;
    State state;
    QElapsedTimer clock; clock.start();
    void *pixels = MAP_FAILED;
    int fd = -1;
    size_t bytes = 0;
    auto fail = [&](const char *error) { result.error = error; };
    do {
        if (timeoutMs < 1 || timeoutMs > 2500) { fail("invalid_deadline"); break; }
        state.display = wl_display_connect(nullptr);
        if (!state.display) { fail("display_unavailable"); break; }
        if (expectedCompositor) {
            ucred peer{}; socklen_t length = sizeof(peer);
            if (getsockopt(wl_display_get_fd(state.display), SOL_SOCKET, SO_PEERCRED, &peer, &length)
                || peer.uid != geteuid() || peer.pid != expectedCompositor) { fail("wrong_compositor"); break; }
        }
        state.registry = wl_display_get_registry(state.display);
        wl_registry_add_listener(state.registry, &registryListener, &state);
        if (!roundtrip(state, clock, timeoutMs) || !state.output || !state.shm || !state.factory) { fail("capture_protocol_unavailable"); break; }
        state.source = weston_capture_v1_create(state.factory, state.output, WESTON_CAPTURE_V1_SOURCE_FRAMEBUFFER);
        weston_capture_source_v1_add_listener(state.source, &sourceListener, &state);
        if (!roundtrip(state, clock, timeoutMs) || state.width < 1 || state.height < 1 || qint64(state.width) * state.height > 4194304) { fail("capture_dimensions_unavailable"); break; }
        if (state.format != DRM_FORMAT_XRGB8888 && state.format != DRM_FORMAT_ARGB8888) { fail("capture_format_unsupported"); break; }
        bytes = size_t(state.width) * size_t(state.height) * 4;
        fd = memfd_create("r46h-output", MFD_CLOEXEC);
        if (fd < 0 || ftruncate(fd, off_t(bytes)) != 0) { fail("capture_storage_failed"); break; }
        pixels = mmap(nullptr, bytes, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        if (pixels == MAP_FAILED) { fail("capture_mapping_failed"); break; }
        auto *pool = wl_shm_create_pool(state.shm, fd, int32_t(bytes));
        const auto shmFormat = state.format == DRM_FORMAT_XRGB8888 ? WL_SHM_FORMAT_XRGB8888 : WL_SHM_FORMAT_ARGB8888;
        state.buffer = wl_shm_pool_create_buffer(pool, 0, state.width, state.height, state.width * 4, shmFormat);
        wl_shm_pool_destroy(pool);
        weston_capture_source_v1_capture(state.source, state.buffer);
        if (!dispatch(state, state.done, clock, timeoutMs)) { fail("capture_deadline"); break; }
        if (!state.error.isEmpty()) { result.error = state.error; break; }
        result.image = QImage(static_cast<const uchar *>(pixels), state.width, state.height, state.width * 4,
                              state.format == DRM_FORMAT_XRGB8888 ? QImage::Format_RGB32 : QImage::Format_ARGB32_Premultiplied).copy();
        if (result.image.isNull()) fail("capture_copy_failed");
    } while (false);
    if (state.sync) wl_callback_destroy(state.sync);
    if (state.source) weston_capture_source_v1_destroy(state.source);
    if (state.buffer) wl_buffer_destroy(state.buffer);
    if (state.factory) weston_capture_v1_destroy(state.factory);
    if (state.output) wl_output_destroy(state.output);
    if (state.shm) wl_shm_destroy(state.shm);
    if (state.registry) wl_registry_destroy(state.registry);
    if (state.display) wl_display_disconnect(state.display);
    if (pixels != MAP_FAILED) munmap(pixels, bytes);
    if (fd >= 0) close(fd);
    return result;
}
