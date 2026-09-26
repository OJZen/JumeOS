#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include "capture.h"
#include <QColor>
#include <QCoreApplication>
#include <QDir>
#include <QElapsedTimer>
#include <QTemporaryDir>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>
#include <cassert>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <thread>

// Exercise the real receiver without a compositor or device. The server shares
// our PID so the production SO_PEERCRED check remains enabled.
int main(int argc, char **argv)
{
    QCoreApplication app(argc, argv);
    QTemporaryDir directory("/out/capture-task.XXXXXX"); assert(directory.isValid());
    const auto path = directory.path() + "/policy.sock";
    sockaddr_un address{}; address.sun_family = AF_UNIX;
    const auto encoded = path.toUtf8(); assert(encoded.size() < int(sizeof(address.sun_path)));
    memcpy(address.sun_path, encoded.constData(), size_t(encoded.size() + 1));
    const int listener = socket(AF_UNIX, SOCK_STREAM | SOCK_CLOEXEC, 0); assert(listener >= 0);
    assert(bind(listener, reinterpret_cast<sockaddr *>(&address), sizeof(address)) == 0);
    assert(listen(listener, 1) == 0);
    const auto fdCount = [] { return QDir("/proc/self/fd").entryList(QDir::NoDotAndDotDot | QDir::AllEntries).size(); };
    for (const auto *mode : {"exact", "fragmented", "two-fds", "truncated-fds", "oversized", "slow"}) {
        const int before = fdCount();
        std::thread server([&] {
            const int peer = accept4(listener, nullptr, nullptr, SOCK_CLOEXEC); assert(peer >= 0);
            char request[1024]; assert(recv(peer, request, sizeof(request), 0) > 0);
            QImage image(320, 240, QImage::Format_RGBA8888_Premultiplied); image.fill(QColor(17, 65, 193));
            const int imageFd = memfd_create("capture-test", MFD_CLOEXEC); assert(imageFd >= 0);
            assert(write(imageFd, image.constBits(), size_t(image.sizeInBytes())) == image.sizeInBytes());
            const QByteArray response = !strcmp(mode, "oversized")
                ? "{\"ok\":true,\"width\":2147483647,\"height\":2147483647}\n"
                : "{\"ok\":true,\"width\":320,\"height\":240}\n";
            const bool fragmented = !strcmp(mode, "fragmented"), slow = !strcmp(mode, "slow");
            const int count = !strcmp(mode, "two-fds") ? 2 : !strcmp(mode, "truncated-fds") ? 8 : 1;
            const auto first = fragmented || slow ? response.left(1) : response;
            iovec payload{const_cast<char *>(first.constData()), size_t(first.size())};
            alignas(cmsghdr) char control[CMSG_SPACE(8 * sizeof(int))]{};
            msghdr message{}; message.msg_iov = &payload; message.msg_iovlen = 1;
            message.msg_control = control; message.msg_controllen = CMSG_SPACE(count * sizeof(int));
            auto *header = CMSG_FIRSTHDR(&message); header->cmsg_level = SOL_SOCKET; header->cmsg_type = SCM_RIGHTS;
            header->cmsg_len = CMSG_LEN(count * sizeof(int));
            for (int i = 0; i < count; ++i) memcpy(CMSG_DATA(header) + i * sizeof(int), &imageFd, sizeof(imageFd));
            assert(sendmsg(peer, &message, MSG_NOSIGNAL) == first.size());
            if (fragmented || slow) {
                for (int i = 1; i < response.size(); ++i) {
                    std::this_thread::sleep_for(std::chrono::milliseconds(slow ? 250 : 1));
                    if (send(peer, response.constData() + i, 1, MSG_NOSIGNAL) != 1) break;
                }
            }
            close(imageFd); close(peer);
        });
        QElapsedTimer timer; timer.start();
        const auto result = captureTask(path, getpid(), 42, 1);
        const auto elapsed = timer.elapsed();
        server.join();
        assert(fdCount() == before);
        if (!strcmp(mode, "exact") || !strcmp(mode, "fragmented")) {
            assert(result.error.isEmpty() && result.image.size() == QSize(320, 240));
            // Pixel access after receiver munmap catches a shallow scaled() copy.
            assert(result.image.pixelColor(0, 0) == QColor(17, 65, 193));
            assert(result.image.pixelColor(319, 239) == QColor(17, 65, 193));
        } else {
            assert(result.image.isNull() && !result.error.isEmpty());
            if (!strcmp(mode, "slow")) assert(elapsed >= 1000 && elapsed < 2000);
        }
    }
    close(listener);
    puts("TASK_CAPTURE_CHECK PASS: owned exact-size pixels, fragments, extra/truncated fds, absolute deadline");
}
