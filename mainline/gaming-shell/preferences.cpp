#include "preferences.h"
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSaveFile>
#include <QDateTime>
#include <QRegularExpression>
#include <QSet>
#include <cerrno>
#include <cmath>
#include <sys/stat.h>

namespace {
const QList<int> FontPercents{90, 100, 115, 130};
const QStringList NightModes{QStringLiteral("off"), QStringLiteral("on"), QStringLiteral("auto")};
constexpr int RecentLimit = 32;
bool validId(const QString &id) { return QRegularExpression("^[a-z0-9][a-z0-9._-]{0,63}$").match(id).hasMatch(); }
}

Preferences::Preferences(QString directory, QObject *parent)
    : QObject(parent), m_directory(std::move(directory)) {
    QFile file(QDir(m_directory).filePath("preview.json"));
    struct stat metadata;
    if (::lstat(QFile::encodeName(file.fileName()).constData(), &metadata) != 0) {
        // QFile::exists() also returns false when traversal is denied.
        if (errno == ENOENT || errno == ENOTDIR) return;
        m_loadFailed = true;
        setError(QStringLiteral("无法读取预览设置；原文件已保留。"));
        return;
    }
    if (!file.open(QIODevice::ReadOnly) || file.size() > 32768) {
        m_loadFailed = true;
        setError(QStringLiteral("无法读取预览设置；原文件已保留。"));
        return;
    }
    QJsonParseError parse;
    const auto document = QJsonDocument::fromJson(file.readAll(), &parse);
    const auto data = document.object();
    const auto validInteger = [](const QJsonValue &value, int low, int high) {
        const double number = value.toDouble(-1);
        return value.isDouble() && std::isfinite(number) && std::floor(number) == number
            && number >= low && number <= high;
    };
    bool valid = parse.error == QJsonParseError::NoError && document.isObject()
        && QList<QJsonValue>{1, 2, 3, 4, 5}.contains(data.value("version"))
        && validInteger(data.value("volume"), 0, 100)
        && validInteger(data.value("brightness"), 10, 100)
        && data.value("reducedMotion").isBool() && data.value("favorites").isArray();
    const int version = data.value("version").toInt();
    if (version >= 2) {
        // Schemas 2-4 stored 100/110/120; migration keeps each rank as 100/115/130.
        const QList<int> fonts = version >= 5 ? FontPercents : QList<int>{100, 110, 120};
        valid = valid && data.value("monitor").isBool()
            && validInteger(data.value("fontPercent"), 90, 130)
            && fonts.contains(data.value("fontPercent").toInt())
            && validInteger(data.value("dimSeconds"), 0, 120)
            && QList<int>{0, 30, 60, 120}.contains(data.value("dimSeconds").toInt());
    }
    QSet<int> seen;
    for (const auto &value : data.value("favorites").toArray()) {
        if (!validInteger(value, 0, 5) || seen.contains(value.toInt())) valid = false;
        seen.insert(value.toInt());
    }
    if (version >= 3) {
        const auto values = data.value("applicationFavorites"); QSet<QString> applicationIds;
        valid = valid && values.isArray() && values.toArray().size() <= 256;
        for (const auto &value : values.toArray()) {
            const auto id = value.toString();
            if (!value.isString() || !validId(id) || applicationIds.contains(id)) valid = false;
            applicationIds.insert(id);
        }
    }
    if (version >= 4)
        valid = valid && validInteger(data.value("screenOffSeconds"), 0, 900)
            && QList<int>{0, 60, 180, 300, 600, 900}.contains(data.value("screenOffSeconds").toInt());
    if (version >= 5) {
        valid = valid && NightModes.contains(data.value("nightMode").toString())
            && (!data.contains("monitorDetail") || data.value("monitorDetail").isBool());
        const auto values = data.value("recentApplications"); QSet<QString> recentIds;
        valid = valid && values.isArray() && values.toArray().size() <= RecentLimit;
        for (const auto &value : values.toArray()) {
            const auto entry = value.toObject(); const auto id = entry.value("id").toString();
            if (!value.isObject() || entry.size() != 2 || !entry.value("id").isString() || !validId(id) || recentIds.contains(id)
                || !validInteger(entry.value("playedAt"), 0, 2147483647)) valid = false;
            recentIds.insert(id);
        }
    }
    if (!valid) {
        m_loadFailed = true;
        setError(QStringLiteral("预览设置格式异常；请保留原文件，移开后再重试。"));
        return;
    }
    m_volume = data.value("volume").toInt();
    m_brightness = data.value("brightness").toInt();
    m_reducedMotion = data.value("reducedMotion").toBool();
    m_favorites = data.value("favorites").toArray().toVariantList();
    if (version >= 3)
        m_applicationFavorites = data.value("applicationFavorites").toArray().toVariantList();
    if (version >= 2) {
        m_monitor = data.value("monitor").toBool();
        const int font = data.value("fontPercent").toInt();
        m_fontPercent = version >= 5 ? font : FontPercents[QList<int>{100, 110, 120}.indexOf(font) + 1];
        m_dimSeconds = data.value("dimSeconds").toInt();
    }
    if (version >= 4) m_screenOffSeconds = data.value("screenOffSeconds").toInt();
    if (version >= 5) {
        m_nightMode = data.value("nightMode").toString();
        m_monitorDetail = data.value("monitorDetail").toBool();
        for (const auto &value : data.value("recentApplications").toArray()) {
            const auto entry = value.toObject();
            m_recentApplications.append(QVariantMap{{"id", entry.value("id").toString()}, {"playedAt", entry.value("playedAt").toInteger()}});
        }
    }
}

void Preferences::setError(const QString &message) {
    if (m_error == message) return;
    m_error = message;
    emit errorChanged();
}

void Preferences::adjust(const QString &name, int step) {
    if (name == "volume") m_volume = qBound(0, m_volume + qBound(-100, step, 100), 100);
    else if (name == "brightness") m_brightness = qBound(10, m_brightness + qBound(-100, step, 100), 100);
    else if (name == "motion") m_reducedMotion = !m_reducedMotion;
    else if (name == "monitor") m_monitor = !m_monitor;
    else if (name == "font") m_fontPercent = FontPercents[qBound(0, int(FontPercents.indexOf(m_fontPercent)) + (step < 0 ? -1 : 1), int(FontPercents.size()) - 1)];
    else if (name == "dim") {
        const QList<int> choices{0, 30, 60, 120};
        m_dimSeconds = choices[qBound(0, choices.indexOf(m_dimSeconds) + (step < 0 ? -1 : 1), 3)];
    }
    else if (name == "screenOff") {
        const QList<int> choices{0, 60, 180, 300, 600, 900};
        m_screenOffSeconds = choices[qBound(0, choices.indexOf(m_screenOffSeconds) + (step < 0 ? -1 : 1), 5)];
    }
    else return;
    m_dirty = true;
    emit changed();
}

bool Preferences::isFavorite(int index) const { return m_favorites.contains(index); }

bool Preferences::choose(const QString &name, int index) {
    if (name == "monitorDetail") {
        if (index < 0 || index > 1) return false;
        m_monitorDetail = index == 1;
        m_dirty = true; emit changed();
        return save();
    }
    if (name == "night") {
        if (index < 0 || index >= NightModes.size()) return false;
        m_nightMode = NightModes[index];
        m_dirty = true; emit changed();
        return save();
    }
    const QList<int> values = name == "font" ? FontPercents
        : name == "dim" ? QList<int>{0, 30, 60, 120}
        : name == "screenOff" ? QList<int>{0, 60, 180, 300, 600, 900} : QList<int>{};
    if (index < 0 || index >= values.size()) return false;
    if (name == "font") m_fontPercent = values[index]; else if (name == "dim") m_dimSeconds = values[index]; else m_screenOffSeconds = values[index];
    m_dirty = true; emit changed();
    return save();
}

void Preferences::toggleFavorite(int index) {
    if (index < 0 || index > 5) return;
    if (!m_favorites.removeOne(index)) m_favorites.append(index);
    m_dirty = true;
    emit changed();
}
bool Preferences::toggleApplicationFavorite(const QString &id) {
    if (!validId(id)) return false;
    if (!m_applicationFavorites.contains(id) && m_applicationFavorites.size() >= 256) return false;
    if (!m_applicationFavorites.removeOne(id)) m_applicationFavorites.append(id);
    m_dirty = true; emit changed(); return true;
}
// Most recent first; launching again moves an entry to the front.
bool Preferences::recordRecent(const QString &id, qint64 playedAt) {
    if (!validId(id)) return false;
    if (playedAt < 0) playedAt = QDateTime::currentSecsSinceEpoch();
    if (playedAt > 2147483647) return false;
    removeRecent(id);
    m_recentApplications.prepend(QVariantMap{{"id", id}, {"playedAt", playedAt}});
    while (m_recentApplications.size() > RecentLimit) m_recentApplications.removeLast();
    m_dirty = true; emit changed(); return true;
}
bool Preferences::removeRecent(const QString &id) {
    for (int i = 0; i < m_recentApplications.size(); ++i) {
        if (m_recentApplications[i].toMap().value("id").toString() != id) continue;
        m_recentApplications.removeAt(i);
        m_dirty = true; emit changed(); return true;
    }
    return false;
}

bool Preferences::save() {
    if (!m_dirty) return true;
    if (m_loadFailed) return false;
    QDir directory(m_directory);
    if (!directory.mkpath(".")) {
        setError(QStringLiteral("无法保存预览设置；当前修改仍保留，可重试。"));
        return false;
    }
    QSaveFile file(directory.filePath("preview.json"));
    const auto bytes = QJsonDocument(QJsonObject{
        {"version", 5}, {"volume", m_volume}, {"brightness", m_brightness},
        {"monitor", m_monitor}, {"monitorDetail", m_monitorDetail}, {"fontPercent", m_fontPercent}, {"dimSeconds", m_dimSeconds}, {"screenOffSeconds", m_screenOffSeconds},
        {"nightMode", m_nightMode}, {"reducedMotion", m_reducedMotion}, {"favorites", QJsonArray::fromVariantList(m_favorites)},
        {"applicationFavorites", QJsonArray::fromVariantList(m_applicationFavorites)},
        {"recentApplications", QJsonArray::fromVariantList(m_recentApplications)}
    }).toJson();
    if (!file.open(QIODevice::WriteOnly) || file.write(bytes) != bytes.size() || !file.commit()) {
        setError(QStringLiteral("无法保存预览设置；当前修改仍保留，可重试。"));
        return false;
    }
    m_dirty = false;
    setError({});
    emit changed();
    return true;
}
