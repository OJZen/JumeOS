#include "preferences.h"
#include <QDir>
#include <QFile>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QSaveFile>
#include <QRegularExpression>
#include <QSet>
#include <cerrno>
#include <cmath>
#include <sys/stat.h>

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
        && QList<QJsonValue>{1, 2, 3}.contains(data.value("version"))
        && validInteger(data.value("volume"), 0, 100)
        && validInteger(data.value("brightness"), 10, 100)
        && data.value("reducedMotion").isBool() && data.value("favorites").isArray();
    if (data.value("version") == QJsonValue(2) || data.value("version") == QJsonValue(3)) {
        valid = valid && data.value("monitor").isBool()
            && validInteger(data.value("fontPercent"), 100, 120)
            && data.value("fontPercent").toInt() % 10 == 0
            && validInteger(data.value("dimSeconds"), 0, 120)
            && QList<int>{0, 30, 60, 120}.contains(data.value("dimSeconds").toInt());
    }
    QSet<int> seen;
    for (const auto &value : data.value("favorites").toArray()) {
        if (!validInteger(value, 0, 5) || seen.contains(value.toInt())) valid = false;
        seen.insert(value.toInt());
    }
    if (data.value("version") == QJsonValue(3)) {
        const auto values = data.value("applicationFavorites"); QSet<QString> applicationIds;
        valid = valid && values.isArray() && values.toArray().size() <= 256;
        for (const auto &value : values.toArray()) {
            const auto id = value.toString();
            if (!value.isString() || !QRegularExpression("^[a-z0-9][a-z0-9._-]{0,63}$").match(id).hasMatch() || applicationIds.contains(id)) valid = false;
            applicationIds.insert(id);
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
    if (data.value("version") == QJsonValue(3))
        m_applicationFavorites = data.value("applicationFavorites").toArray().toVariantList();
    if (data.value("version") == QJsonValue(2) || data.value("version") == QJsonValue(3)) {
        m_monitor = data.value("monitor").toBool();
        m_fontPercent = data.value("fontPercent").toInt();
        m_dimSeconds = data.value("dimSeconds").toInt();
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
    else if (name == "font") m_fontPercent = qBound(100, m_fontPercent + (step < 0 ? -10 : 10), 120);
    else if (name == "dim") {
        const QList<int> choices{0, 30, 60, 120};
        m_dimSeconds = choices[qBound(0, choices.indexOf(m_dimSeconds) + (step < 0 ? -1 : 1), 3)];
    }
    else return;
    m_dirty = true;
    emit changed();
}

bool Preferences::isFavorite(int index) const { return m_favorites.contains(index); }

bool Preferences::choose(const QString &name, int index) {
    const QList<int> values = name == "font" ? QList<int>{100, 110, 120}
        : name == "dim" ? QList<int>{0, 30, 60, 120} : QList<int>{};
    if (index < 0 || index >= values.size()) return false;
    if (name == "font") m_fontPercent = values[index]; else m_dimSeconds = values[index];
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
    if (!QRegularExpression("^[a-z0-9][a-z0-9._-]{0,63}$").match(id).hasMatch()) return false;
    if (!m_applicationFavorites.contains(id) && m_applicationFavorites.size() >= 256) return false;
    if (!m_applicationFavorites.removeOne(id)) m_applicationFavorites.append(id);
    m_dirty = true; emit changed(); return true;
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
        {"version", 3}, {"volume", m_volume}, {"brightness", m_brightness},
        {"monitor", m_monitor}, {"fontPercent", m_fontPercent}, {"dimSeconds", m_dimSeconds},
        {"reducedMotion", m_reducedMotion}, {"favorites", QJsonArray::fromVariantList(m_favorites)},
        {"applicationFavorites", QJsonArray::fromVariantList(m_applicationFavorites)}
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
