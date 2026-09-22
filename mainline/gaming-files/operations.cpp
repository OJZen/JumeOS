#include "operations.h"
#include <QFile>
#include <QFileInfo>
#include <QDir>
#include <QDirIterator>
#include <QSaveFile>
#include <QTemporaryFile>
#include <QStorageInfo>
#include <QStringDecoder>
#include <QDateTime>
#include <QXmlStreamReader>
#include <QUrl>
#include <archive.h>
#include <archive_entry.h>
#include <sys/stat.h>
#include <unistd.h>

namespace Files {
static bool exists(const QString &p) {
    return QFileInfo::exists(p) || QFileInfo(p).isSymLink();
}
bool validName(const QString &n) {
    if (n.isEmpty() || n == "." || n == ".." || n.toUtf8().size() > 255)
        return false;
    for (auto c : n)
        if (c == '/' || c.unicode() < 32 || c.unicode() == 127)
            return false;
    return true;
}
bool protectedPath(const QString &p) {
    QFileInfo f(p);
    if (!QDir::isAbsolutePath(p) || f.fileName().isEmpty() || p.contains(QChar(0)))
        return true;
    const auto clean = QDir::cleanPath(p);
    if (clean == "/" || clean == QDir::homePath() || clean == "/roms" || clean == "/boot")
        return true;
    if (f.isSymLink())
        return false; // Operations act on the link, never its target.
    return f.isDir() && QStorageInfo(p).rootPath() == f.canonicalFilePath();
}
QString makeDirectory(const QString &parent, const QString &name) {
    if (!validName(name) || !QFileInfo(parent).isDir())
        return "目录名称无效。";
    if (!QDir(parent).mkdir(name))
        return "无法新建目录：名称已存在、只读或权限不足。";
    return {};
}
QString rename(const QString &p, const QString &name) {
    if (protectedPath(p) || !validName(name))
        return "不允许修改根目录，或名称无效。";
    const auto target = QFileInfo(p).dir().filePath(name);
    if (exists(target))
        return "同名文件已存在；未覆盖。";
    return QDir().rename(p, target) ? QString() : QStringLiteral("重命名失败；原文件保留。");
}
static QString copyTree(const QString &src, const QString &dst, std::atomic_bool &cancel, int depth, quint64 &count,
                        const Progress &progress) {
    if (cancel)
        return "已取消；已完成的目录条目保留。";
    if (depth > 64 || ++count > 100000)
        return "目录层级或条目过多；已复制的条目保留。";
    if (exists(dst))
        return "目标已存在；未覆盖：" + dst;
    QFileInfo info(src);
    if (progress)
        progress(src, 0, info.isFile() ? info.size() : 0);
    if (info.isSymLink()) {
        char target[4096];
        const auto size = ::readlink(QFile::encodeName(src), target, sizeof(target));
        if (size < 0 || size == sizeof(target))
            return "无法读取符号链接。";
        return ::symlink(QByteArray(target, int(size)).constData(), QFile::encodeName(dst)) == 0
                   ? QString()
                   : QStringLiteral("无法复制符号链接。");
    }
    if (info.isDir()) {
        if (protectedPath(src) && depth > 0)
            return "不跨越嵌套挂载点。";
        if (!QDir().mkdir(dst))
            return "无法创建目标目录。";
        QDirIterator iterator(src, QDir::AllEntries | QDir::NoDotAndDotDot | QDir::Hidden | QDir::System);
        while (iterator.hasNext()) {
            iterator.next();
            const auto entry = iterator.fileInfo();
            const auto error =
                copyTree(entry.filePath(), QDir(dst).filePath(entry.fileName()), cancel, depth + 1, count, progress);
            if (!error.isEmpty())
                return error;
        }
        return {};
    }
    if (!info.isFile())
        return "仅支持普通文件、目录和符号链接。";
    QFile input(src);
    if (!input.open(QIODevice::ReadOnly))
        return input.errorString();
    struct stat before {
    }, after{};
    if (::fstat(input.handle(), &before))
        return "无法核对源文件。";
    QTemporaryFile output(QFileInfo(dst).dir().filePath(".jume-copy-XXXXXX"));
    if (!output.open())
        return output.errorString();
    while (!input.atEnd()) {
        if (cancel)
            return "已取消；原文件保留。";
        const auto block = input.read(256 * 1024);
        if (block.isEmpty() && input.error() != QFileDevice::NoError)
            return input.errorString();
        if (output.write(block) != block.size())
            return output.errorString();
        if (progress)
            progress(src, input.pos(), before.st_size);
    }
    if (::fstat(input.handle(), &after) || before.st_size != after.st_size ||
        before.st_mtim.tv_sec != after.st_mtim.tv_sec || before.st_mtim.tv_nsec != after.st_mtim.tv_nsec ||
        before.st_ctim.tv_sec != after.st_ctim.tv_sec || before.st_ctim.tv_nsec != after.st_ctim.tv_nsec)
        return "复制时源文件已变化；未发布该副本，请重试。";
    if (!output.flush() || ::fsync(output.handle()))
        return "写入目标失败；源文件保留。";
    if (cancel)
        return "已取消；原文件保留。";
    output.setPermissions(info.permissions());
    output.close();
    if (!output.rename(dst))
        return "无法发布目标文件；可能同名文件已出现，未覆盖。";
    output.setAutoRemove(false);
    return {};
}
QString transfer(const QString &src, const QString &dst, bool move, std::atomic_bool &cancel,
                 const Progress &progress) {
    if (protectedPath(src) || !exists(src) || exists(dst) || !QFileInfo(QFileInfo(dst).absolutePath()).isDir())
        return "源/目标无效、目标已存在或根目录受保护。";
    const auto source = QFileInfo(src).canonicalFilePath(),
               parent = QFileInfo(QFileInfo(dst).absolutePath()).canonicalFilePath();
    if (QFileInfo(src).isDir() && !QFileInfo(src).isSymLink() && (parent == source || parent.startsWith(source + '/')))
        return "不能把目录放进自身。";
    if (cancel)
        return "已取消。";
    if (move) {
        // Cross-volume cut retains the original in native trash, never recursive delete.
        struct stat a {
        }, b{};
        if (::lstat(QFile::encodeName(src), &a) || ::stat(QFile::encodeName(parent), &b))
            return "无法核对分区；原文件保留。";
        if (a.st_dev == b.st_dev)
            return QDir().rename(src, dst) ? QString() : QStringLiteral("移动失败；原文件保留。");
    }
    quint64 count = 0;
    const auto error = copyTree(src, dst, cancel, 0, count, progress);
    if (!error.isEmpty() || !move)
        return error;
    if (cancel)
        return "复制完成后取消，源文件仍保留。";
    return QFile::moveToTrash(src) ? QString()
                                   : QStringLiteral("副本已完成，但源文件无法移入回收站；两份均保留，请核对。");
}
static QString eraseTree(const QString &p, std::atomic_bool &cancel, int depth = 0) {
    if (cancel)
        return "删除已取消；已删除的条目无法恢复。";
    if (protectedPath(p))
        return "根目录或挂载点受保护。";
    if (depth > 64)
        return "目录层级过深；剩余文件保留。";
    QFileInfo f(p);
    if (f.isSymLink() || f.isFile())
        return QFile::remove(p) ? QString() : QStringLiteral("删除失败：") + p;
    if (!f.isDir())
        return "不删除特殊设备文件。";
    QDirIterator iterator(p, QDir::AllEntries | QDir::NoDotAndDotDot | QDir::Hidden | QDir::System);
    while (iterator.hasNext()) {
        const auto error = eraseTree(iterator.next(), cancel, depth + 1);
        if (!error.isEmpty())
            return error;
    }
    return QDir().rmdir(p) ? QString() : QStringLiteral("目录删除失败：") + p;
}
QString remove(const QString &p, bool permanent, std::atomic_bool &cancel) {
    if (cancel)
        return "已取消。";
    if (protectedPath(p))
        return "根目录或挂载点受保护。";
    if (permanent)
        return eraseTree(p, cancel);
    const QFileInfo info(p);
    if (!info.isFile() && !info.isDir() && !info.isSymLink())
        return "不处理特殊设备文件。";
    return QFile::moveToTrash(p) ? QString() : QStringLiteral("此位置无法移入回收站；文件保留。可单独选择永久删除。");
}
QString trashDestination(const QString &p, QString *error) {
    const auto files = QFileInfo(p).dir(), root = QFileInfo(files.path()).dir();
    const bool named =
        root.dirName() == "Trash" || root.dirName() == ".Trash-" + QString::number(geteuid()) ||
        (root.dirName() == QString::number(geteuid()) && QFileInfo(root.path()).dir().dirName() == ".Trash");
    const auto info = root.filePath("info/" + QFileInfo(p).fileName() + ".trashinfo");
    QFile metadata(info);
    if (files.dirName() != "files" || !named || QFileInfo(root.path()).ownerId() != geteuid() ||
        QFileInfo(info).isSymLink() || !QFileInfo(info).isFile() || QFileInfo(info).size() > 16384 ||
        !metadata.open(QIODevice::ReadOnly)) {
        *error = "不是可识别的回收站条目。";
        return {};
    }
    const auto bytes = metadata.read(16385);
    QString destination;
    for (const auto &line : bytes.split('\n'))
        if (line.startsWith("Path=")) {
            if (!destination.isEmpty()) {
                *error = "回收站元数据有歧义。";
                return {};
            }
            destination = QUrl::fromPercentEncoding(line.mid(5));
        }
    if (!QDir::isAbsolutePath(destination)) {
        if (root.dirName() == "Trash" || destination.split('/').contains("..")) {
            *error = "回收站路径无效。";
            return {};
        }
        destination = QDir(QStorageInfo(p).rootPath()).filePath(destination);
    }
    if (destination.isEmpty() || protectedPath(destination) || exists(destination) ||
        !QFileInfo(QFileInfo(destination).absolutePath()).isDir()) {
        *error = "原位置不存在、受保护或已有同名文件；不会覆盖。";
        return {};
    }
    return destination;
}
QString restoreTrash(const QString &p, std::atomic_bool &cancel) {
    QString error;
    const auto destination = trashDestination(p, &error);
    if (!error.isEmpty())
        return error;
    error = transfer(p, destination, true, cancel);
    if (!error.isEmpty())
        return error;
    const auto metadata =
        QFileInfo(QFileInfo(p).dir().path()).dir().filePath("info/" + QFileInfo(p).fileName() + ".trashinfo");
    return QFile::remove(metadata) ? QString() : QStringLiteral("文件已恢复，但旧回收站元数据未清理。");
}
QString TextDocument::load(const QString &file) {
    QFileInfo f(file);
    if (!f.isFile() || f.isSymLink() || f.size() > TextLimit)
        return "仅可编辑不超过 2 MiB 的普通 UTF-8 文件，不跟随符号链接。";
    QFile input(file);
    if (!input.open(QIODevice::ReadOnly))
        return input.errorString();
    const auto bytes = input.read(TextLimit + 1);
    if (bytes.size() > TextLimit || input.error() != QFileDevice::NoError)
        return "文件过大或读取失败。";
    if (bytes.contains('\0'))
        return "这是二进制文件，不作为文本打开。";
    auto content = bytes;
    const bool hasBom = content.startsWith("\xef\xbb\xbf");
    if (hasBom)
        content.remove(0, 3);
    QStringDecoder decoder(QStringDecoder::Utf8);
    const QString decoded = decoder.decode(content);
    if (decoder.hasError())
        return "不是有效 UTF-8；未使用有损解码。请先转换编码。";
    const bool windows = decoded.contains("\r\n");
    const auto normalized = QString(decoded).replace("\r\n", "\n");
    if (normalized.contains('\r') || (windows && QString(decoded).remove("\r\n").contains('\n')))
        return "混合/旧式换行格式暂不编辑；原文件未改动。";
    if (normalized.count('\n') > 20000)
        return "文本行数超过 20,000 行，避免编辑器内存过载。";
    for (const auto &line : normalized.split('\n'))
        if (line.size() > 65536)
            return "单行超过 65,536 字符，避免布局内存过载。";
    struct stat metadata {};
    if (::fstat(input.handle(), &metadata) || !S_ISREG(metadata.st_mode))
        return "文件状态发生变化。";
    deviceId = metadata.st_dev;
    inode = metadata.st_ino;
    path = f.absoluteFilePath();
    text = normalized;
    original = bytes;
    bom = hasBom;
    crlf = windows;
    return {};
}
QString TextDocument::save(const QString &file, const QString &value) {
    if (protectedPath(file) || QFileInfo(file).isSymLink())
        return "不写入根目录或符号链接。";
    if (value.contains(QChar(0)) || value.contains('\r'))
        return "不保存含空字符或混合换行的文本。";
    QByteArray bytes = (crlf ? QString(value).replace("\n", "\r\n") : value).toUtf8();
    if (bom)
        bytes.prepend("\xef\xbb\xbf");
    if (bytes.size() > TextLimit || value.count('\n') > 20000)
        return "文本超过 2 MiB / 20,000 行限制。";
    for (const auto &line : value.split('\n'))
        if (line.size() > 65536)
            return "单行过长。";
    if (file == path) {
        struct stat metadata {};
        if (::lstat(QFile::encodeName(file), &metadata) || quint64(metadata.st_dev) != deviceId ||
            quint64(metadata.st_ino) != inode)
            return "文件/分区已被替换，请另存为。";
        QFile current(file);
        if (!current.open(QIODevice::ReadOnly) || current.read(TextLimit + 1) != original)
            return "文件已被外部修改/移除，请另存为，避免覆盖。";
        QSaveFile output(file);
        output.setDirectWriteFallback(false);
        if (!output.open(QIODevice::WriteOnly) || output.write(bytes) != bytes.size() || !output.commit())
            return "保存失败；原文件与当前编辑内容保留。";
    } else {
        if (exists(file))
            return "目标已存在；未覆盖，请选择新名称。";
        QTemporaryFile output(QFileInfo(file).dir().filePath(".jume-text-XXXXXX"));
        if (!output.open() || output.write(bytes) != bytes.size() || !output.flush() || ::fsync(output.handle()))
            return "保存失败；当前编辑内容保留。";
        output.close();
        if (!output.rename(file))
            return "无法保存到新名称；不会覆盖同名文件。";
        output.setAutoRemove(false);
    }
    struct stat metadata {};
    if (::lstat(QFile::encodeName(file), &metadata))
        return "写入完成但无法核对文件状态，请保留当前内容并核查。";
    deviceId = metadata.st_dev;
    inode = metadata.st_ino;
    path = QFileInfo(file).absoluteFilePath();
    text = value;
    original = bytes;
    return {};
}
QString officeText(const QString &path, QString *error) {
    QFileInfo info(path);
    if (!info.isFile() || info.size() > 32 * 1024 * 1024) {
        *error = "文档超过 32 MiB 限制。";
        return {};
    }
    archive *a = archive_read_new();
    archive_read_support_format_zip(a);
    archive_read_support_filter_none(a);
    QByteArray xml;
    archive_entry *entry = nullptr;
    int entries = 0;
    if (archive_read_open_filename(a, QFile::encodeName(path), 16384) != ARCHIVE_OK)
        *error = "无法打开文档容器。";
    else
        while (archive_read_next_header(a, &entry) == ARCHIVE_OK) {
            if (++entries > 4096) {
                *error = "文档条目过多。";
                break;
            }
            const auto name = QString::fromUtf8(archive_entry_pathname(entry));
            if (name != "word/document.xml" && name != "content.xml") {
                archive_read_data_skip(a);
                continue;
            }
            if (archive_entry_size(entry) > TextLimit) {
                *error = "文档正文过大。";
                break;
            }
            char buffer[16384];
            la_ssize_t read;
            while ((read = archive_read_data(a, buffer, sizeof(buffer))) > 0 && xml.size() <= TextLimit)
                xml.append(buffer, int(read));
            if (read < 0 || xml.size() > TextLimit)
                *error = "正文读取失败或解压后过大。";
            break;
        }
    archive_read_free(a);
    if (!error->isEmpty())
        return {};
    if (xml.isEmpty()) {
        *error = "没有可预览的正文。";
        return {};
    }
    QXmlStreamReader reader(xml);
    reader.setEntityExpansionLimit(1024);
    QString result;
    while (!reader.atEnd()) {
        reader.readNext();
        if (reader.isDTD()) {
            *error = "不加载含 DTD 的文档。";
            return {};
        }
        if (reader.isCharacters())
            result += reader.text();
        if (reader.isEndElement() && (reader.name() == u"p" || reader.name() == u"h"))
            result += '\n';
        if (result.size() > TextLimit) {
            *error = "正文过大。";
            return {};
        }
    }
    if (reader.hasError()) {
        *error = "文档 XML 无效。";
        return {};
    }
    if (result.count('\n') > 20000) {
        *error = "正文行数过多。";
        return {};
    }
    for (const auto &line : result.split('\n'))
        if (line.size() > 65536) {
            *error = "正文单行过长。";
            return {};
        }
    return result;
}
QString properties(const QString &p) {
    QFileInfo f(p);
    QStorageInfo volume(p);
    struct stat metadata {};
    const auto permissions =
        ::lstat(QFile::encodeName(p), &metadata) == 0 ? QString::number(metadata.st_mode & 07777, 8) : QString("未知");
    return QString("名称：%1\n路径：%2\n类型：%3\n大小：%4 "
                   "字节（目录不递归统计）\n修改：%5\n所有者：%6\n权限：%7\n所在分区：%8\n剩余：%9 MiB\n%10")
        .arg(f.fileName(), f.absoluteFilePath(),
             f.isSymLink() ? "符号链接"
             : f.isDir()   ? "目录"
                           : "文件")
        .arg(f.size())
        .arg(f.lastModified().toString(Qt::ISODate), f.owner(), permissions, volume.rootPath())
        .arg(volume.bytesAvailable() / 1024 / 1024)
        .arg(f.isSymLink()         ? "链接目标：" + f.symLinkTarget()
             : volume.isReadOnly() ? "只读分区"
                                   : "可写性受文件权限限制");
}
} // namespace Files
