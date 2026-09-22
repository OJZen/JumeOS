#pragma once
#include <QString>
#include <QByteArray>
#include <atomic>
#include <functional>
#include <QStringList>

namespace Files {
constexpr qint64 TextLimit = 2 * 1024 * 1024;
bool validName(const QString &name);
bool protectedPath(const QString &path);
QString makeDirectory(const QString &parent, const QString &name);
QString rename(const QString &path, const QString &name);
// Empty result = success. Cancellation never removes the original of a copy/move.
using Progress = std::function<void(const QString &item, qint64 done, qint64 total)>;
QString transfer(const QString &source, const QString &destination, bool move, std::atomic_bool &cancel,
                 const Progress &progress = {});
QString unpackZip(const QString &source, const QString &destination, std::atomic_bool &cancel,
                  const Progress &progress = {});
QString packZip(const QStringList &sources, const QString &destination, std::atomic_bool &cancel,
                const Progress &progress = {});
QString remove(const QString &path, bool permanent, std::atomic_bool &cancel);
QString officeText(const QString &path, QString *error);
QString properties(const QString &path);
QString trashDestination(const QString &path, QString *error);
QString restoreTrash(const QString &path, std::atomic_bool &cancel);

class TextDocument {
  public:
    QString path, text;
    QString load(const QString &file);
    QString save(const QString &file, const QString &value);

  private:
    QByteArray original;
    quint64 deviceId = 0, inode = 0;
    bool bom = false, crlf = false;
};
} // namespace Files
