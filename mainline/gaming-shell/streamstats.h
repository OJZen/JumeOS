#pragma once
#include <QByteArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <cmath>
#include <iterator>
#ifdef Q_OS_UNIX
#include <fcntl.h>
#include <signal.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

// Numeric-only, bounded protocol shared by the client, worker and desktop.
namespace StreamStats {
inline constexpr const char *keys[] = {"receivedFps", "decodedFps", "renderedFps", "networkDropPercent",
    "pacingDropPercent", "decodeMs", "queueMs", "renderCallMs", "rttMs", "hostProcessingMs", "audioNetworkQueueMs"};
inline QJsonObject parse(const QByteArray &line) {
    if (line.size() > 2048 || !line.startsWith("R46H_STATS ")) return {};
    const auto document = QJsonDocument::fromJson(line.mid(11));
    const auto value = document.object();
    if (!document.isObject() || value.size() != int(std::size(keys)) + 1 || value.value("version") != QJsonValue(1)) return {};
    for (const auto *key : keys) {
        const auto number = value.value(key);
        if (!number.isDouble() || !std::isfinite(number.toDouble()) || number.toDouble() < -1 || number.toDouble() > 1e6) return {};
    }
    return value;
}
inline QByteArray encode(const QJsonObject &value) { return "R46H_STATS " + QJsonDocument(value).toJson(QJsonDocument::Compact) + '\n'; }
inline bool preparePipe() {
#ifdef Q_OS_UNIX
    struct stat info{}; const int flags = fcntl(STDOUT_FILENO, F_GETFL);
    if (flags < 0 || fstat(STDOUT_FILENO, &info) || !S_ISFIFO(info.st_mode) || fcntl(STDOUT_FILENO, F_SETFL, flags | O_NONBLOCK) < 0) return false;
    signal(SIGPIPE, SIG_IGN); // A closed diagnostic consumer must not stop streaming.
    return true;
#else
    return false;
#endif
}
inline void send(const QByteArray &line) {
#ifdef Q_OS_UNIX
    if (line.size() <= 2048) (void)::write(STDOUT_FILENO, line.constData(), size_t(line.size()));
#else
    Q_UNUSED(line);
#endif
}
}
