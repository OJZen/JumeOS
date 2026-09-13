// Own the accepted merged evdev device and expose one game-only uinput endpoint.
#include "input-route.h"
#include <linux/input.h>
#include <linux/uinput.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <unistd.h>
#include <algorithm>
#include <chrono>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <string>

using namespace Route;
constexpr unsigned Keys[] = {BTN_SOUTH, BTN_EAST, BTN_NORTH, BTN_WEST, BTN_TL, BTN_TR,
    BTN_TL2, BTN_TR2, BTN_SELECT, BTN_START, BTN_DPAD_UP, BTN_DPAD_DOWN, BTN_DPAD_LEFT,
    BTN_DPAD_RIGHT, BTN_TRIGGER_HAPPY3, BTN_TRIGGER_HAPPY4, BTN_TRIGGER_HAPPY5};
constexpr unsigned Axes[] = {ABS_X, ABS_Y, ABS_RX, ABS_RY};
static volatile sig_atomic_t stopping = 0;
static void stop(int) { stopping = 1; }
static int64_t nowMs() { return std::chrono::duration_cast<std::chrono::milliseconds>(
    std::chrono::steady_clock::now().time_since_epoch()).count(); }
static void require(bool condition, const char *message) { if (!condition) throw std::runtime_error(message); }
template<size_t N> static bool bit(const unsigned char (&bits)[N], unsigned key) { return bits[key / 8] & (1U << (key % 8)); }

struct Router {
    int source = -1, output = -1, control;
    bool grabbed = false, created = false, syncing = false;
    input_absinfo calibration[4]{};
    Sample input, center, game, ui;
    Policy policy;
    uint64_t commandSequence = 0;
    uint64_t remoteSequence = 0;
    int64_t remoteUntil = 0;
    Sample remote;
    explicit Router(int fd, int chordMs) : control(fd), policy(chordMs) {}
    ~Router() {
        if (created) { try { writeGame(center); } catch (...) {} ioctl(output, UI_DEV_DESTROY); }
        if (grabbed) ioctl(source, EVIOCGRAB, 0);
        if (output >= 0) close(output);
        if (source >= 0) close(source);
    }
    void sendPacket(Packet packet) {
        if (packet.type != InjectDone && packet.type != InjectDenied) packet.sequence = commandSequence;
        packet.mode = policy.mode;
        packet.flags |= (policy.waiting ? WaitingNeutral : 0U) | (policy.ownerPending ? WaitingOwner : 0U);
        ssize_t n;
        do { n = send(control, &packet, sizeof(packet), MSG_NOSIGNAL | MSG_DONTWAIT); } while (n < 0 && errno == EINTR);
        require(n == sizeof(packet), "controller disconnected or stopped consuming reports");
    }
    Packet uiPacket(const Sample &sample) {
        Packet packet; packet.type = State; packet.keys = sample.keys;
        for (int i = 0; i < 4; ++i) {
            const int64_t delta = int64_t(sample.axes[i]) - center.axes[i];
            const int64_t range = delta < 0 ? int64_t(center.axes[i]) - calibration[i].minimum : int64_t(calibration[i].maximum) - center.axes[i];
            packet.axes[i] = int32_t(std::clamp(delta * 32767 / std::max<int64_t>(1, range), int64_t(-32767), int64_t(32767)));
        }
        return packet;
    }
    void writeGame(const Sample &sample) {
        input_event events[22]{}; unsigned count = 0;
        for (unsigned i = 0; i < 17; ++i) if ((game.keys ^ sample.keys) & (1U << i))
            events[count++] = {{}, EV_KEY, uint16_t(Keys[i]), int32_t(bool(sample.keys & (1U << i)))};
        for (unsigned i = 0; i < 4; ++i) if (sample.axes[i] != game.axes[i])
            events[count++] = {{}, EV_ABS, uint16_t(Axes[i]), sample.axes[i]};
        if (!count) return;
        events[count++] = {{}, EV_SYN, SYN_REPORT, 0};
        const auto *bytes = reinterpret_cast<const char *>(events);
        size_t left = count * sizeof(input_event);
        while (left) {
            const auto n = write(output, bytes, left);
            if (n < 0 && errno == EINTR) continue;
            require(n > 0, "uinput write failed"); bytes += n; left -= size_t(n);
        }
        game = sample;
    }
    void neutralize() {
        writeGame(center);
        ui = center; sendPacket(uiPacket(center));
    }
    void readState() {
        unsigned char bits[(KEY_MAX + 8) / 8]{};
        require(ioctl(source, EVIOCGKEY(sizeof(bits)), bits) >= 0, "cannot resynchronize keys");
        input.keys = 0;
        for (unsigned i = 0; i < 17; ++i) if (bit(bits, Keys[i])) input.keys |= 1U << i;
        for (unsigned i = 0; i < 4; ++i) {
            input_absinfo value{};
            require(ioctl(source, EVIOCGABS(Axes[i]), &value) >= 0, "cannot resynchronize axis");
            require(value.minimum == calibration[i].minimum && value.maximum == calibration[i].maximum, "axis calibration changed");
            input.axes[i] = value.value;
        }
    }
    bool neutral() const {
        if (input.keys) return false;
        for (unsigned i = 0; i < 4; ++i) {
            // Match the shell's 0.3 neutral gate while preserving full raw game ranges.
            const int64_t half = (int64_t(calibration[i].maximum) - calibration[i].minimum) / 2;
            if (std::abs(int64_t(input.axes[i]) - center.axes[i]) > std::max<int64_t>(calibration[i].flat, half * 3 / 10)) return false;
        }
        return true;
    }
    void tick() {
        if (remoteUntil && (nowMs() >= remoteUntil || !neutral())) endRemote(!neutral());
        policy.update(input, neutral(), nowMs(), [&](const Sample &sample) {
            if (policy.mode == Game) writeGame(remoteUntil ? remote : sample);
            else if (sample != ui) { ui = sample; sendPacket(uiPacket(sample)); }
        }, [&] {
            neutralize(); Packet packet; packet.type = Panel; sendPacket(packet);
        });
    }
    void endRemote(bool cancelled) {
        if (!remoteUntil) return;
        remoteUntil = 0; writeGame(center);
        Packet done; done.type = InjectDone; done.sequence = remoteSequence;
        done.flags = cancelled ? InjectionCancelled : 0U; sendPacket(done);
    }
    void openDevice(const char *path, int inheritedOutput = -1) {
        int type = 0; socklen_t length = sizeof(type);
        require(getsockopt(control, SOL_SOCKET, SO_TYPE, &type, &length) == 0 && type == SOCK_SEQPACKET, "inherited seqpacket channel required");
        ucred peer{}; length = sizeof(peer);
        require(getsockopt(control, SOL_SOCKET, SO_PEERCRED, &peer, &length) == 0 && peer.uid == geteuid() && peer.pid == getppid(), "controller must be the parent with the same uid");
        require(fcntl(control, F_SETFD, FD_CLOEXEC) == 0, "cannot seal control fd");
        source = open(path, O_RDONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
        struct stat metadata{}; char name[128]{}; input_id id{};
        require(source >= 0 && fstat(source, &metadata) == 0 && S_ISCHR(metadata.st_mode), "evdev character device required");
        require(ioctl(source, EVIOCGNAME(sizeof(name)), name) >= 0 && std::string(name) == "R46H Combined Gamepad", "wrong input name");
        require(ioctl(source, EVIOCGID, &id) == 0 && id.bustype == BUS_VIRTUAL && id.vendor == 0x5246 && id.product == 0x0048 && id.version == 1, "wrong input identity");
        unsigned char keys[(KEY_MAX + 8) / 8]{};
        require(ioctl(source, EVIOCGBIT(EV_KEY, sizeof(keys)), keys) >= 0, "cannot inspect input capabilities");
        for (auto key : Keys) require(bit(keys, key), "missing required key");
        for (unsigned i = 0; i < 4; ++i) {
            require(ioctl(source, EVIOCGABS(Axes[i]), &calibration[i]) == 0, "missing required axis");
            auto &a = calibration[i];
            require(a.maximum > a.minimum && a.flat >= 0 && int64_t(a.flat) * 2 < int64_t(a.maximum) - a.minimum, "invalid axis calibration");
            center.axes[i] = int32_t((int64_t(a.minimum) + a.maximum) / 2);
        }
        output = inheritedOutput >= 0 ? inheritedOutput : open("/dev/uinput", O_WRONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
        require(output >= 0, "cannot open uinput");
        struct stat device{};
        const int flags = fcntl(output, F_GETFL);
        require(output != control && fstat(output, &device) == 0 && S_ISCHR(device.st_mode)
            && major(device.st_rdev) == 10 && minor(device.st_rdev) == 223 && flags >= 0 && (flags & O_ACCMODE) != O_RDONLY,
            "invalid inherited uinput handle");
        require(fcntl(output, F_SETFD, FD_CLOEXEC) == 0 && fcntl(output, F_SETFL, flags | O_NONBLOCK) == 0, "cannot seal uinput handle");
        require(ioctl(output, UI_SET_EVBIT, EV_KEY) == 0 && ioctl(output, UI_SET_EVBIT, EV_ABS) == 0, "cannot configure uinput");
        for (auto key : Keys) require(ioctl(output, UI_SET_KEYBIT, key) == 0, "cannot configure key");
        for (unsigned i = 0; i < 4; ++i) {
            require(ioctl(output, UI_SET_ABSBIT, Axes[i]) == 0, "cannot configure axis");
            uinput_abs_setup axis{}; axis.code = Axes[i]; axis.absinfo = calibration[i]; axis.absinfo.value = center.axes[i];
            require(ioctl(output, UI_ABS_SETUP, &axis) == 0, "cannot copy axis calibration");
        }
        uinput_setup setup{}; setup.id = {BUS_VIRTUAL, 0x5246, 0x0049, 1};
        std::strcpy(setup.name, "R46H Routed Gamepad");
        require(ioctl(output, UI_DEV_SETUP, &setup) == 0 && ioctl(output, UI_DEV_CREATE) == 0, "cannot create routed gamepad");
        created = true; game = ui = center;
        require(ioctl(source, EVIOCGRAB, 1) == 0, "combined controller is already grabbed"); grabbed = true;
        readState();
        Packet ready; ready.type = Ready;
        require(ioctl(output, UI_GET_SYSNAME(sizeof(ready.device)), ready.device) >= 0, "cannot identify routed gamepad");
        sendPacket(ready);
    }
    void command() {
        Packet packet{};
        const auto n = recv(control, &packet, sizeof(packet), MSG_DONTWAIT | MSG_TRUNC);
        if (n < 0 && (errno == EINTR || errno == EAGAIN)) return;
        require(n == sizeof(packet), "invalid or disconnected control channel");
        require(packet.version == Version && (packet.type == Mode || packet.type == Inject || packet.type == CancelInject)
            && packet.mode <= Game && packet.sequence == commandSequence + 1
            && commandSequence < UINT64_MAX, "invalid or stale input ownership command");
        Packet expected; expected.type = packet.type; expected.mode = packet.mode; expected.sequence = packet.sequence;
        if (packet.type == Inject) { expected.keys = packet.keys; expected.flags = packet.flags; std::copy(std::begin(packet.axes), std::end(packet.axes), expected.axes); }
        require(!std::memcmp(&expected, &packet, sizeof(packet)), "unexpected control payload");
        ++commandSequence;
        if (packet.type == CancelInject) { endRemote(true); tick(); return; }
        if (packet.type == Inject) {
            readState();
            bool valid = packet.mode == Game && policy.mode == Game && !policy.waiting && !policy.ownerPending && !syncing && !remoteUntil && neutral()
                && packet.flags >= 10 && packet.flags <= 1000 && !(packet.keys & ~0xffffU) && (packet.keys & Chord) != Chord;
            for (auto axis : packet.axes) valid &= axis >= -32767 && axis <= 32767;
            if (!valid) { Packet denied; denied.type = InjectDenied; denied.sequence = commandSequence; sendPacket(denied); return; }
            remote = center; remote.keys = packet.keys;
            for (unsigned i = 0; i < 4; ++i) {
                const int64_t range = packet.axes[i] < 0 ? int64_t(center.axes[i]) - calibration[i].minimum : int64_t(calibration[i].maximum) - center.axes[i];
                remote.axes[i] += int64_t(packet.axes[i]) * range / 32767;
            }
            remoteSequence = commandSequence; remoteUntil = nowMs() + packet.flags;
            writeGame(remote); return;
        }
        endRemote(true); policy.setMode(packet.mode); neutralize();
        // Discard the previous owner's backlog before reading current held controls.
        input_event old{};
        bool drained = false;
        for (int count = 0; count < 4096; ++count) {
            const auto n = read(source, &old, sizeof(old));
            if (n < 0 && errno == EINTR) continue;
            if (n < 0 && errno == EAGAIN) { drained = true; break; }
            require(n == sizeof(old), "cannot discard old input owner backlog");
        }
        require(drained, "input backlog exceeded ownership transition bound");
        syncing = false;
        readState(); tick();
        Packet ack; ack.type = Ack; sendPacket(ack);
    }
    void run() {
        while (!stopping) {
            int timeout = policy.deadline ? int(std::clamp<int64_t>(policy.deadline - nowMs(), 0, 100)) : 100;
            if (remoteUntil) timeout = std::min(timeout, int(std::clamp<int64_t>(remoteUntil - nowMs(), 0, 100)));
            pollfd fds[]{{source, POLLIN, 0}, {control, POLLIN, 0}};
            const int result = poll(fds, 2, timeout);
            if (result < 0 && errno == EINTR) continue;
            require(result >= 0 && !(fds[0].revents & (POLLHUP | POLLERR | POLLNVAL)), "input device disconnected");
            require(!(fds[1].revents & (POLLHUP | POLLERR | POLLNVAL)), "controller disconnected");
            if (fds[1].revents & POLLIN) command();
            for (int batch = 0; batch < 512 && (fds[0].revents & POLLIN); ++batch) {
                input_event event{}; const auto n = read(source, &event, sizeof(event));
                if (n < 0 && errno == EINTR) continue;
                if (n < 0 && errno == EAGAIN) break;
                require(n == sizeof(event), "invalid or disconnected input stream");
                if (event.type == EV_SYN && event.code == SYN_DROPPED) {
                    endRemote(true);
                    syncing = true;
                    const bool ownerPending = policy.ownerPending;
                    policy.setMode(policy.mode); policy.ownerPending = ownerPending;
                    neutralize(); continue;
                }
                if (syncing) {
                    if (event.type == EV_SYN && event.code == SYN_REPORT) { readState(); syncing = false; tick(); }
                    continue;
                }
                if (event.type == EV_KEY) for (unsigned i = 0; i < 17; ++i) if (event.code == Keys[i]) {
                    if (event.value) input.keys |= 1U << i; else input.keys &= ~(1U << i);
                }
                if (event.type == EV_ABS) for (unsigned i = 0; i < 4; ++i) if (event.code == Axes[i])
                    input.axes[i] = std::clamp(event.value, calibration[i].minimum, calibration[i].maximum);
                if (event.type == EV_SYN && event.code == SYN_REPORT) tick();
            }
            if (!syncing) tick();
        }
    }
};

int main(int argc, char **argv) {
    if (argc != 4 && argc != 5) { std::fprintf(stderr, "Usage: input-router EVENT_NODE CONTROL_FD CHORD_MS [UINPUT_FD]\n"); return 2; }
    try {
        auto number = [](const char *text) { char *end = nullptr; errno = 0; long n = std::strtol(text, &end, 10);
            require(!errno && end != text && !*end && n >= 0 && n <= 65535, "invalid numeric argument"); return int(n); };
        const int fd = number(argv[2]), chordMs = number(argv[3]);
        require(fd > 2 && chordMs >= 40 && chordMs <= 300, "invalid fd or chord interval");
        signal(SIGTERM, stop); signal(SIGINT, stop);
        const int inheritedOutput = argc == 5 ? number(argv[4]) : -1;
        require(inheritedOutput == -1 || inheritedOutput > 2, "invalid inherited uinput fd");
        Router router(fd, chordMs); router.openDevice(argv[1], inheritedOutput); router.run();
    } catch (const std::exception &error) { std::fprintf(stderr, "INPUT_ROUTER_ERROR: %s\n", error.what()); return 1; }
    return 0;
}
