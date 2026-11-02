#include "stickcalibration.h"
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QSaveFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <cmath>

StickCalibration::StickCalibration(QObject *parent) : QObject(parent) {
    m_timer.setInterval(20);
    connect(&m_timer, &QTimer::timeout, this, &StickCalibration::sampleCenter);
}
void StickCalibration::setError(const QString &text) { m_error = text; emit changed(); }
void StickCalibration::load(const QString &directory) {
    m_path = QDir(directory).filePath("stick-calibration.json");
    QFile file(m_path); const QFileInfo info(file);
    if (!info.exists() && !info.isSymLink()) return;
    bool valid = info.isFile() && !info.isSymLink() && info.size() <= 4096 && file.open(QIODevice::ReadOnly);
    const auto document = valid ? QJsonDocument::fromJson(file.read(4097)) : QJsonDocument();
    const auto object = document.object(); const auto axes = object.value("axes").toArray();
    valid = valid && document.isObject() && object.size() == 3 && object.value("version") == QJsonValue(1)
        && object.value("enabled").isBool() && object.value("axes").isArray() && axes.size() == 4;
    Stick::Profile profile;
    for (int i = 0; valid && i < 4; ++i) {
        const auto values = axes[i].toArray(); valid = axes[i].isArray() && values.size() == 3;
        for (const auto &value : values) {
            const auto number = value.toDouble(1e9);
            valid = valid && value.isDouble() && std::isfinite(number) && std::floor(number) == number
                && number >= -Stick::Full && number <= Stick::Full;
        }
        if (valid) profile[i] = {values[0].toInt(), values[1].toInt(), values[2].toInt()};
    }
    if (!valid || !Stick::valid(profile)) { setError(QStringLiteral("校准文件异常，原文件已保留；可重新校准或恢复默认。")); return; }
    m_saved = profile; m_configured = object.value("enabled").toBool(); emit changed();
}
void StickCalibration::setAvailable(bool value) {
    if (m_available == value) return;
    m_available = value;
    if (!value) { cancel(); m_busy = false; }
    emit changed();
}
void StickCalibration::observe(const qint32 axes[4]) {
    for (int i = 0; i < 4; ++i) if (axes[i] < -Stick::Full || axes[i] > Stick::Full) return;
    std::copy(axes, axes + 4, m_raw.begin());
    if (m_phase == 2) for (int i = 0; i < 4; ++i) {
        m_draft[i].minimum = std::min(m_draft[i].minimum, axes[i]);
        m_draft[i].maximum = std::max(m_draft[i].maximum, axes[i]);
    }
    if (active()) emit changed();
}
void StickCalibration::sampleCenter() {
    if (m_phase != 1 || !m_available) return;
    m_centers.append(m_raw);
    if (m_centers.size() > 30) m_centers.removeFirst();
    emit changed();
}
bool StickCalibration::canAdvance() const {
    if (!m_available || m_busy) return false;
    if (m_phase == 1) {
        if (m_centers.size() != 30) return false;
        for (int i = 0; i < 4; ++i) {
            int low = Stick::Full, high = -Stick::Full;
            for (const auto &sample : m_centers) { low = std::min(low, sample[i]); high = std::max(high, sample[i]); }
            if (low < -Stick::MinimumTravel || high > Stick::MinimumTravel || high - low > 1024) return false;
        }
        return true;
    }
    if (m_phase == 2) return Stick::valid(m_draft);
    if (m_phase == 3) {
        for (int i = 0; i < 4; ++i) if (std::abs(m_draft[i].apply(m_raw[i])) >= 4096) return false;
        return true;
    }
    return m_phase == 4;
}
QVariantList StickCalibration::rawAxes() const {
    QVariantList out; for (auto value : m_raw) out.append(double(value) / Stick::Full); return out;
}
QVariantList StickCalibration::previewAxes() const {
    QVariantList out;
    for (int i = 0; i < 4; ++i) {
        const auto value = m_phase == 3 ? m_draft[i].apply(m_raw[i]) : m_configured ? m_saved[i].apply(m_raw[i]) : m_raw[i];
        out.append(double(value) / Stick::Full);
    }
    return out;
}
QVariantList StickCalibration::ranges() const {
    QVariantList out;
    for (const auto &axis : m_draft) out.append(QVariantMap{{"minimum", double(axis.minimum) / Stick::Full},
        {"center", double(axis.center) / Stick::Full}, {"maximum", double(axis.maximum) / Stick::Full}, {"complete", axis.valid()}});
    return out;
}
bool StickCalibration::begin() {
    if (!m_available || m_busy) return false;
    m_phase = 1; m_centers.clear(); m_error.clear(); m_timer.start(); emit changed(); return true;
}
void StickCalibration::cancel() {
    m_phase = 0; m_centers.clear(); m_timer.stop(); emit changed();
}
bool StickCalibration::confirmReset() {
    if (!m_available || m_busy) return false;
    m_phase = 4; m_error.clear(); m_timer.stop(); emit changed(); return true;
}
bool StickCalibration::advance() {
    if (!canAdvance()) {
        setError(m_phase == 2 ? QStringLiteral("请将两个摇杆向四个方向推满，再沿边缘转动。") : QStringLiteral("请松开两个摇杆并保持稳定。"));
        return false;
    }
    m_error.clear();
    if (m_phase == 1) {
        for (int i = 0; i < 4; ++i) {
            qint64 sum = 0; for (const auto &sample : m_centers) sum += sample[i];
            const auto center = qint32(sum / m_centers.size()); m_draft[i] = {center, center, center};
        }
        m_timer.stop(); m_phase = 2;
    } else if (m_phase == 2) m_phase = 3;
    else return save(m_phase != 4, m_phase == 4 ? Stick::Profile{} : m_draft);
    emit changed(); return true;
}
bool StickCalibration::save(bool enabled, const Stick::Profile &profile) {
    if (m_path.isEmpty() || QFileInfo(m_path).isSymLink() || !Stick::valid(profile)) {
        setError(QStringLiteral("无法保存校准，原设置未更改。")); return false;
    }
    QJsonArray axes; for (const auto &axis : profile) axes.append(QJsonArray{axis.minimum, axis.center, axis.maximum});
    const auto data = QJsonDocument(QJsonObject{{"version", 1}, {"enabled", enabled}, {"axes", axes}}).toJson();
    QSaveFile file(m_path); file.setDirectWriteFallback(false);
    if (!file.open(QIODevice::WriteOnly) || !file.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner)
        || file.write(data) != data.size() || !file.commit()) {
        setError(QStringLiteral("无法保存校准，原设置未更改；可重试。")); return false;
    }
    m_saved = profile; m_configured = enabled; m_needsApply = m_busy = true; cancel();
    emit configurationRequested(); return true;
}
void StickCalibration::applied(bool accepted) {
    const bool requested = m_busy;
    m_busy = false;
    if (accepted) { m_needsApply = false; if (requested) emit notice(m_configured ? QStringLiteral("摇杆校准已应用") : QStringLiteral("摇杆已恢复默认")); }
    else setError(QStringLiteral("校准已保存，暂未生效；回到桌面后可重试。"));
    emit changed();
}
