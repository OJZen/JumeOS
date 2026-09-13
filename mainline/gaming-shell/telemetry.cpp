#include "telemetry.h"
#include <QFile>
#include <QStorageInfo>
#include <QSysInfo>
#include <time.h>
#include <unistd.h>
#ifdef Q_OS_MACOS
#include <mach/mach.h>
#endif

static double processCpuSeconds() {
    timespec value{};
    if (clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &value) != 0) return -1;
    return double(value.tv_sec) + double(value.tv_nsec) / 1e9;
}
static double residentMiB() {
#ifdef Q_OS_MACOS
    mach_task_basic_info_data_t info{};
    mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
    if (task_info(mach_task_self(), MACH_TASK_BASIC_INFO, reinterpret_cast<task_info_t>(&info), &count) == KERN_SUCCESS)
        return double(info.resident_size) / (1024 * 1024);
#elif defined(Q_OS_LINUX)
    QFile file("/proc/self/statm");
    if (file.open(QIODevice::ReadOnly)) {
        const auto fields = file.read(256).simplified().split(' ');
        bool ok = false;
        const auto pages = fields.value(1).toULongLong(&ok);
        const auto pageSize = sysconf(_SC_PAGESIZE);
        if (ok && pageSize > 0) return double(pages) * double(pageSize) / (1024 * 1024);
    }
#endif
    return -1;
}
Telemetry::Telemetry(QString stateDirectory, QObject *parent)
    : QObject(parent), m_directory(std::move(stateDirectory)) {
    m_timer.setInterval(1000);
    connect(&m_timer, &QTimer::timeout, this, &Telemetry::sample);
    refreshStorage();
}
void Telemetry::setActive(bool value) {
    if (active() == value) return;
    m_active.store(value);
    m_frames.store(0);
    m_history.clear();
    m_cpu = m_submissions = -1;
    m_memoryMiB = value ? residentMiB() : -1;
    if (value) { m_previousCpu = processCpuSeconds(); m_clock.start(); m_timer.start(); }
    else m_timer.stop();
    emit changed();
}
void Telemetry::sample() {
    const double elapsed = double(m_clock.nsecsElapsed()) / 1e9;
    m_clock.restart();
    const double current = processCpuSeconds();
    m_cpu = elapsed > 0 && current >= 0 && m_previousCpu >= 0 && current >= m_previousCpu
        ? (current - m_previousCpu) / elapsed * 100 : -1;
    m_previousCpu = current;
    m_memoryMiB = residentMiB();
    m_submissions = elapsed > 0 ? double(m_frames.exchange(0)) / elapsed : -1;
    m_history.append(m_cpu);
    if (m_history.size() > 60) m_history.removeFirst();
    emit changed();
}
QString Telemetry::system() const {
    return QSysInfo::prettyProductName() + " · " + QSysInfo::currentCpuArchitecture() + " · Qt " + qVersion();
}
void Telemetry::refreshStorage() {
    QStorageInfo info(m_directory);
    m_storage = info.isValid() && info.isReady()
        ? QStringLiteral("可用 %1 / 共 %2 GiB").arg(double(info.bytesAvailable()) / (1ULL << 30), 0, 'f', 1)
            .arg(double(info.bytesTotal()) / (1ULL << 30), 0, 'f', 1)
        : QStringLiteral("目录尚未创建或存储不可用");
    emit changed();
}
