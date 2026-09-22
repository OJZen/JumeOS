#include "operations.h"
#include <QDir>
#include <QDirIterator>
#include <QFile>
#include <QFileInfo>
#include <QTemporaryDir>
#include <QTemporaryFile>
#include <QDateTime>
#include <QtEndian>
#include <archive.h>
#include <archive_entry.h>
#include <memory>
#include <unistd.h>

namespace Files {
namespace {
constexpr qint64 limit = 16LL * 1024 * 1024 * 1024;
constexpr int entryLimit = 50000;
bool occupied(const QString &p) {
    return QFileInfo::exists(p) || QFileInfo(p).isSymLink();
}
bool safeEntry(QString name) {
    if (name.endsWith('/'))
        name.chop(1);
    if (name.isEmpty() || name.contains('\\') || name.contains(':') || name.toUtf8().size() > 4096)
        return false;
    const auto parts = name.split('/');
    if (parts.size() > 64)
        return false;
    for (const auto &part : parts)
        if (!validName(part))
            return false;
    return true;
}
} // namespace
QString unpackZip(const QString &source, const QString &destination, std::atomic_bool &cancel,
                  const Progress &progress) {
    if (cancel)
        return "已取消。";
    QFile input(source);
    const QFileInfo info(source);
    if (!info.isFile() || info.isSymLink() || protectedPath(destination) || occupied(destination) ||
        !input.open(QIODevice::ReadOnly))
        return "ZIP 或目标无效；请选择不存在的新目录。";
    // Stream entries instead of retaining the central-directory tree in RAM.
    // Check the bounded end record first so truncated/no-directory input fails closed.
    input.seek(qMax<qint64>(0, input.size() - 65557));
    const auto tail = input.read(65557);
    int end = tail.size() - 22;
    for (; end >= 0; --end)
        if (tail.mid(end, 4) == QByteArray("PK\5\6", 4) &&
            end + 22 + qFromLittleEndian<quint16>(tail.constData() + end + 20) == tail.size())
            break;
    if (end < 0 || qFromLittleEndian<quint32>(tail.constData() + end + 4) != 0)
        return "ZIP 不完整或为分卷压缩包。";
    const auto expected = qFromLittleEndian<quint16>(tail.constData() + end + 10);
    if (expected > entryLimit || expected != qFromLittleEndian<quint16>(tail.constData() + end + 8))
        return "ZIP 条目超过 50,000 或分卷结构不受支持。";
    // Streaming readers cannot see Unix link modes stored only in the central
    // directory. Bound and validate that metadata before trusting local headers.
    const quint64 directorySize = qFromLittleEndian<quint32>(tail.constData() + end + 12),
                  offset = qFromLittleEndian<quint32>(tail.constData() + end + 16);
    if (directorySize > 16 * 1024 * 1024 || offset + directorySize > quint64(input.size()) || !input.seek(offset))
        return "ZIP 目录过大或不支持此 ZIP64 目录。";
    const auto central = input.read(directorySize);
    qsizetype pos = 0;
    int records = 0;
    while (pos < central.size()) {
        if (cancel)
            return "已取消解压。";
        if (central.size() - pos < 46 || central.mid(pos, 4) != QByteArray("PK\1\2", 4))
            return "ZIP 中央目录损坏。";
        const auto *h = central.constData() + pos;
        const auto nameSize = qFromLittleEndian<quint16>(h + 28);
        const auto length = 46 + nameSize + qFromLittleEndian<quint16>(h + 30) + qFromLittleEndian<quint16>(h + 32);
        const auto type = (qFromLittleEndian<quint32>(h + 38) >> 16) & AE_IFMT;
        const auto method = qFromLittleEndian<quint16>(h + 10);
        if (length > central.size() - pos || ++records > entryLimit || (type && type != AE_IFDIR && type != AE_IFREG) ||
            (qFromLittleEndian<quint16>(h + 8) & 1) || qFromLittleEndian<quint16>(h + 34) ||
            (method != 0 && method != 8))
            return "ZIP 含链接、特殊文件、加密条目或不支持的压缩方法。";
        const auto name = central.mid(pos + 46, nameSize);
        if (name.contains('\0') || !safeEntry(QString::fromUtf8(name)))
            return "ZIP 含不安全路径。";
        pos += length;
    }
    if (records != expected || central.size() != qsizetype(directorySize))
        return "ZIP 中央目录条目不完整。";
    input.close();
    QTemporaryDir stage(QFileInfo(destination).dir().filePath(".jume-unpack-XXXXXX"));
    if (!stage.isValid())
        return "无法创建解压临时目录。";
    std::unique_ptr<archive, decltype(&archive_read_free)> reader(archive_read_new(), archive_read_free);
    archive *a = reader.get();
    archive_read_support_format_zip_streamable(a);
    archive_read_support_filter_none(a);
    if (archive_read_open_filename(a, QFile::encodeName(source), 65536) != ARCHIVE_OK)
        return "无法读取 ZIP。";
    archive_entry *entry = nullptr;
    int count = 0, status;
    qint64 total = 0;
    while ((status = archive_read_next_header(a, &entry)) == ARCHIVE_OK) {
        if (cancel)
            return "已取消解压；未发布任何文件。";
        if (++count > entryLimit)
            return "ZIP 条目过多。";
        const auto name = QString::fromUtf8(archive_entry_pathname_utf8(entry));
        const auto format = QString::fromLatin1(archive_format_name(a));
        if (!format.endsWith("(uncompressed)") && !format.endsWith("(deflation)"))
            return "仅支持 Store / Deflate ZIP。";
        if (!safeEntry(name) || archive_entry_is_encrypted(entry) || archive_entry_symlink(entry) ||
            archive_entry_hardlink(entry))
            return "ZIP 含不安全路径、链接或加密条目；未解压。";
        const auto type = archive_entry_filetype(entry);
        const auto size = archive_entry_size(entry);
        if ((type != AE_IFDIR && type != AE_IFREG) || size < 0 || size > limit - total)
            return "ZIP 含特殊文件或展开大小超过 16 GiB。";
        const auto path = stage.filePath(name);
        if (progress)
            progress(name, 0, size);
        if (type == AE_IFDIR) {
            if (!QDir().mkpath(path))
                return "无法创建 ZIP 目录。";
            continue;
        }
        if (!QDir().mkpath(QFileInfo(path).absolutePath()))
            return "ZIP 路径冲突。";
        QFile output(path);
        if (!output.open(QIODevice::WriteOnly | QIODevice::NewOnly))
            return "ZIP 有重名条目或目标不可写。";
        output.setPermissions(QFileDevice::ReadOwner | QFileDevice::WriteOwner);
        char buffer[256 * 1024];
        la_ssize_t read;
        qint64 bytes = 0;
        while ((read = archive_read_data(a, buffer, sizeof(buffer))) > 0) {
            if (cancel)
                return "已取消解压；未发布任何文件。";
            if (read > limit - total)
                return "ZIP 展开大小超过 16 GiB。";
            if (output.write(buffer, read) != read)
                return "解压写入失败；请检查空间和设备。";
            bytes += read;
            total += read;
            if (progress)
                progress(name, bytes, size);
        }
        if (read < 0)
            return "ZIP 数据损坏或校验失败。";
        if (!output.flush() || ::fsync(output.handle()))
            return "解压写入未完成。";
    }
    if (status != ARCHIVE_EOF || count != expected || archive_read_close(a) != ARCHIVE_OK)
        return "ZIP 结构/条目数量不完整。";
    if (cancel)
        return "已取消解压；未发布任何文件。";
    if (!QDir().rename(stage.path(), destination))
        return "无法发布解压目录；不会覆盖同名目录。";
    stage.setAutoRemove(false);
    return {};
}

QString packZip(const QStringList &sources, const QString &destination, std::atomic_bool &cancel,
                const Progress &progress) {
    if (sources.isEmpty() || occupied(destination) || protectedPath(destination))
        return "ZIP 目标无效或已经存在。";
    const auto parent = QFileInfo(QFileInfo(destination).absolutePath()).canonicalFilePath();
    for (const auto &source : sources) {
        const auto canonical = QFileInfo(source).canonicalFilePath();
        if (protectedPath(source) ||
            (QFileInfo(source).isDir() && (parent == canonical || parent.startsWith(canonical + '/'))))
            return "不能将压缩包放入源目录内部，或压缩根目录。";
    }
    QTemporaryFile output(QFileInfo(destination).dir().filePath(".jume-zip-XXXXXX"));
    if (!output.open())
        return "无法创建 ZIP 临时文件。";
    std::unique_ptr<archive, decltype(&archive_write_free)> writer(archive_write_new(), archive_write_free);
    archive *a = writer.get();
    archive_write_set_format_zip(a);
    archive_write_set_options(a, "zip:compression=deflate,zip:compression-level=1");
    if (archive_write_open_fd(a, output.handle()) != ARCHIVE_OK)
        return "无法打开 ZIP 写入器。";
    int count = 0;
    qint64 total = 0;
    std::function<QString(const QString &, const QString &, int)> add = [&](const QString &path, const QString &name,
                                                                            int depth) -> QString {
        if (cancel)
            return "已取消压缩；源文件保留。";
        if (depth > 64 || ++count > entryLimit || !safeEntry(name))
            return "目录层级、名称或条目数量超限。";
        QFileInfo info(path);
        if (info.isSymLink() || (!info.isFile() && !info.isDir()) || (depth > 0 && protectedPath(path)))
            return "ZIP 不包含链接、特殊文件或嵌套挂载点。";
        const auto size = info.isDir() ? 0 : info.size();
        if (size < 0 || size > limit - total)
            return "压缩源超过 16 GiB。";
        std::unique_ptr<archive_entry, decltype(&archive_entry_free)> entry(archive_entry_new(), archive_entry_free);
        archive_entry_set_pathname_utf8(entry.get(), name.toUtf8());
        archive_entry_set_filetype(entry.get(), info.isDir() ? AE_IFDIR : AE_IFREG);
        archive_entry_set_perm(entry.get(), info.isDir() ? 0700 : 0600);
        archive_entry_set_size(entry.get(), size);
        if (archive_write_header(a, entry.get()) != ARCHIVE_OK)
            return "无法写入 ZIP 条目。";
        if (progress)
            progress(name, 0, size);
        if (info.isDir()) {
            QDirIterator iterator(path, QDir::AllEntries | QDir::NoDotAndDotDot | QDir::Hidden | QDir::System);
            while (iterator.hasNext()) {
                iterator.next();
                const auto error = add(iterator.filePath(), name + '/' + iterator.fileName(), depth + 1);
                if (!error.isEmpty())
                    return error;
            }
        } else {
            QFile input(path);
            if (!input.open(QIODevice::ReadOnly))
                return input.errorString();
            qint64 bytes = 0;
            while (!input.atEnd()) {
                if (cancel)
                    return "已取消压缩；源文件保留。";
                const auto data = input.read(256 * 1024);
                if (data.isEmpty() && input.error() != QFileDevice::NoError)
                    return input.errorString();
                if (data.size() > size - bytes || archive_write_data(a, data.data(), data.size()) != data.size())
                    return "源文件变化或 ZIP 写入失败。";
                bytes += data.size();
                total += data.size();
                if (progress)
                    progress(name, bytes, size);
            }
            if (bytes != size || QFileInfo(path).lastModified() != info.lastModified())
                return "压缩时源文件已变化，请重试。";
        }
        return archive_write_finish_entry(a) == ARCHIVE_OK ? QString() : QStringLiteral("ZIP 条目写入失败。");
    };
    QStringList names;
    for (const auto &source : sources) {
        const auto name = QFileInfo(source).fileName();
        if (names.contains(name))
            return "选中文件存在重名。";
        names << name;
        const auto error = add(source, name, 0);
        if (!error.isEmpty())
            return error;
    }
    if (archive_write_close(a) != ARCHIVE_OK || !output.flush() || ::fsync(output.handle()))
        return "ZIP 写入未完成。";
    if (cancel)
        return "已取消压缩；源文件保留。";
    output.close();
    if (!output.rename(destination))
        return "无法发布 ZIP；未覆盖原文件。";
    output.setAutoRemove(false);
    return {};
}
} // namespace Files
