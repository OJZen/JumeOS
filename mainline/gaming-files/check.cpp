#include "operations.h"
#include "preview.h"
#include "storage.h"
#include "window.h"
#include "appearance.h"
#include "transfer.h"
#include <QtTest>
#include <QtWidgets>
#include <QPdfWriter>
#include <QPdfDocument>
#include <QMediaPlayer>
#include <QMediaDevices>
#include <QAudioOutput>
#include <QAudioDevice>
#include <QAudioBufferOutput>
#include <QAudioBuffer>
#include <QVideoSink>
#include <QVideoFrame>
#include <QDBusMetaType>
#include <archive.h>
#include <archive_entry.h>
#include <QtEndian>
#include <sys/stat.h>
#include <sys/resource.h>

class DiskFixture : public QObject {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "org.freedesktop.DBus.ObjectManager")
  public:
    DiskObjects objects;
  public slots:
    DiskObjects GetManagedObjects() {
        return objects;
    }
};
class MountFixture : public QObject {
    Q_OBJECT
    Q_CLASSINFO("D-Bus Interface", "org.freedesktop.UDisks2.Filesystem")
  public:
    int calls = 0;
    QVariantMap options;
    QString directory;
  public slots:
    QString Mount(const QVariantMap &value) {
        ++calls;
        options = value;
        return directory;
    }
    void Unmount(const QVariantMap &value) {
        ++calls;
        options = value;
    }
};
class Check : public QObject {
    Q_OBJECT
    QTemporaryDir trashRoot;
    static void put(const QString &p, const QByteArray &data) {
        QFile f(p);
        QVERIFY(f.open(QIODevice::WriteOnly));
        QCOMPARE(f.write(data), data.size());
    }
    static QByteArray get(const QString &p) {
        QFile f(p);
        if (!f.open(QIODevice::ReadOnly))
            return {};
        return f.readAll();
    }
    static void zip(const QString &p, const QByteArray &body) {
        archive *a = archive_write_new();
        archive_write_set_format_zip(a);
        QCOMPARE(archive_write_open_filename(a, QFile::encodeName(p)), ARCHIVE_OK);
        archive_entry *e = archive_entry_new();
        archive_entry_set_pathname(e, "word/document.xml");
        archive_entry_set_filetype(e, AE_IFREG);
        archive_entry_set_perm(e, 0600);
        archive_entry_set_size(e, body.size());
        QCOMPARE(archive_write_header(a, e), ARCHIVE_OK);
        QCOMPARE(archive_write_data(a, body.constData(), body.size()), body.size());
        archive_entry_free(e);
        archive_write_close(a);
        archive_write_free(a);
    }
    static DiskObjects disks() {
        const QString b = "/org/freedesktop/UDisks2/block_devices/sda1", d = "/org/freedesktop/UDisks2/drives/usb";
        return {
            {QDBusObjectPath(d), {{"org.freedesktop.UDisks2.Drive", {{"ConnectionBus", "usb"}, {"Removable", true}}}}},
            {QDBusObjectPath(b),
             {{"org.freedesktop.UDisks2.Block",
               {{"Drive", QVariant::fromValue(QDBusObjectPath(d))},
                {"Device", QByteArray("/dev/sda1\0", 10)},
                {"HintSystem", false},
                {"HintIgnore", false},
                {"Configuration", QVariantList{}},
                {"IdUsage", "filesystem"},
                {"IdType", "vfat"},
                {"IdUUID", "abcd"},
                {"Size", qulonglong(1048576)}}},
              {"org.freedesktop.UDisks2.Filesystem", {{"MountPoints", QVariant::fromValue(QList<QByteArray>())}}}}}};
    }
  private slots:
    void transferQrAndLifecycle() {
        const QString url = "http://192.0.2.1:8080/#synthetic-test-not-a-real-session";
        QTemporaryDir dir;
        const auto image = transferQr(url);
        QVERIFY(!image.isNull());
        QVERIFY(image.width() <= 224);
        QVERIFY(image.save(dir.filePath("qr.png")));
        QProcess decoder;
        decoder.start("zbarimg", {"--quiet", "--raw", dir.filePath("qr.png")});
        QVERIFY(decoder.waitForFinished(3000));
        QCOMPARE(decoder.exitCode(), 0);
        QCOMPARE(QString::fromUtf8(decoder.readAllStandardOutput()).trimmed(), url);
        TransferWindow window(dir.path());
        window.show();
        window.refresh.stop();
        window.probe.kill();
        window.probe.waitForFinished(1000);
        window.connected = false;
        window.start->setEnabled(false);
        window.controllerAction("accept");
        QCOMPARE(window.server.state(), QProcess::NotRunning);
        const auto helper = dir.filePath("fixture.py");
        put(helper,
            QByteArray("import json,sys\nprint(json.dumps({'state':'ready','url':'http://192.0.2.1:8080','link':'") +
                url.toUtf8() + "','code':'12345678'}),flush=True)\nsys.stdin.readline()\n");
        window.helper = helper;
        window.connected = true;
        window.start->setEnabled(true);
        window.start->click();
        QTRY_VERIFY(!window.shareLink.isEmpty());
        QVERIFY(!window.qr->pixmap().isNull());
        QCOMPARE(window.size(), QSize(640, 480));
        const auto captures = qEnvironmentVariable("JUME_FILES_CAPTURE_DIR");
        if (!captures.isEmpty())
            QVERIFY(window.grab().save(captures + "/transfer-device.png"));
        window.close();
        QTRY_COMPARE(window.server.state(), QProcess::NotRunning);
        QTRY_VERIFY(!window.isVisible());
        QVERIFY(window.shareLink.isEmpty());
        QVERIFY(window.address->text().isEmpty());
    }
    void cleanupTestCase() {
        struct rusage usage {};
        QVERIFY(getrusage(RUSAGE_SELF, &usage) == 0);
        qInfo() << "FILES_HOST_PEAK_RSS_KIB" << usage.ru_maxrss;
    }
    void initTestCase() {
        QVERIFY(trashRoot.isValid());
        qputenv("XDG_DATA_HOME", QFile::encodeName(trashRoot.path()));
        filesAppearance();
        const auto file = qEnvironmentVariable("JUME_FILES_FONT");
        if (!file.isEmpty())
            QVERIFY(QFontDatabase::addApplicationFont(file) >= 0);
    }
    void operations() {
        QTemporaryDir dir;
        QVERIFY(dir.isValid());
        std::atomic_bool cancel = false;
        for (const auto &bad : {"", ".", "..", "a/b", "line\nfeed"})
            QVERIFY(!Files::validName(bad));
        QVERIFY(Files::makeDirectory(dir.path(), "source").isEmpty());
        const auto src = dir.filePath("source");
        put(src + "/one", "hello");
        QVERIFY(!Files::makeDirectory(dir.path(), "source").isEmpty());
        QVERIFY(QFile::link(dir.path(), src + "/link"));
        QVERIFY(Files::transfer(src, dir.filePath("copy"), false, cancel).isEmpty());
        QCOMPARE(get(dir.filePath("copy/one")), QByteArray("hello"));
        QVERIFY(QFileInfo(dir.filePath("copy/link")).isSymLink());
        QVERIFY(!Files::transfer(src, src + "/inside", false, cancel).isEmpty());
        QVERIFY(!Files::transfer(src, dir.filePath("copy"), false, cancel).isEmpty());
        QVERIFY(Files::rename(src, "renamed").isEmpty());
        QVERIFY(!QDir(src).exists());
        cancel = true;
        QVERIFY(!Files::transfer(dir.filePath("copy"), dir.filePath("cancelled"), false, cancel).isEmpty());
        QVERIFY(!QDir(dir.filePath("cancelled")).exists());
        cancel = false;
        QVERIFY(Files::remove(dir.filePath("copy"), true, cancel).isEmpty());
        QVERIFY(QFileInfo(dir.filePath("renamed/one")).exists());
        for (const auto &p : {QString("/"), QDir::homePath(), QString("/roms")}) {
            QVERIFY(Files::protectedPath(p));
            QVERIFY(!Files::remove(p, true, cancel).isEmpty());
        }
        QVERIFY(Files::transfer(dir.filePath("renamed/one"), dir.filePath("moved"), true, cancel).isEmpty());
        QCOMPARE(get(dir.filePath("moved")), QByteArray("hello"));
        QString trashed;
        QVERIFY(QFile::moveToTrash(dir.filePath("moved"), &trashed));
        QVERIFY(!QFileInfo::exists(dir.filePath("moved")));
        QString error;
        QCOMPARE(Files::trashDestination(trashed, &error), dir.filePath("moved"));
        QVERIFY(error.isEmpty());
        put(dir.filePath("moved"), "collision");
        QVERIFY(!Files::restoreTrash(trashed, cancel).isEmpty());
        QCOMPARE(get(trashed), QByteArray("hello"));
        QVERIFY(QFile::remove(dir.filePath("moved")));
        QVERIFY(Files::restoreTrash(trashed, cancel).isEmpty());
        QCOMPARE(get(dir.filePath("moved")), QByteArray("hello"));
        QVERIFY(!QFileInfo::exists(trashed));
        QVERIFY(Files::remove(dir.filePath("moved"), false, cancel).isEmpty());
        QVERIFY(!QFileInfo::exists(dir.filePath("moved")));
    }
    void textSafety() {
        QTemporaryDir dir;
        const auto p = dir.filePath("text.txt");
        const QByteArray original = "\xef\xbb\xbfhello\r\nworld\r\n";
        put(p, original);
        Files::TextDocument text;
        QVERIFY(text.load(p).isEmpty());
        QCOMPARE(text.text, QString("hello\nworld\n"));
        QVERIFY(text.save(p, "changed\n").isEmpty());
        QCOMPARE(get(p), QByteArray("\xef\xbb\xbf"
                                    "changed\r\n"));
        put(p, "external");
        QVERIFY(!text.save(p, "bad").isEmpty());
        QCOMPARE(get(p), QByteArray("external"));
        QVERIFY(text.save(dir.filePath("new.txt"), "kept").isEmpty());
        const auto saved = get(dir.filePath("new.txt"));
        QVERIFY(QFile::rename(dir.filePath("new.txt"), dir.filePath("old-inode.txt")));
        put(dir.filePath("new.txt"), saved);
        QVERIFY(!text.save(dir.filePath("new.txt"), "same bytes different file").isEmpty());
        QCOMPARE(get(dir.filePath("new.txt")), saved);
        QVERIFY(!text.save(dir.filePath("nul.txt"), QString(QChar(0))).isEmpty());
        QVERIFY(!QFileInfo::exists(dir.filePath("nul.txt")));
        QVERIFY(!text.save(p, "overwrite").isEmpty());
        QVERIFY(QFile::link(p, dir.filePath("link")));
        QVERIFY(!text.load(dir.filePath("link")).isEmpty());
        QVERIFY(!text.save(dir.filePath("link"), "bad").isEmpty());
        for (const auto &data : QList<QByteArray>{QByteArray("a\0b", 3), QByteArray("\xff"), QByteArray("a\r\nb\n"),
                                                  QByteArray(Files::TextLimit + 1, 'x'), QByteArray(20001, '\n')}) {
            put(p, data);
            QVERIFY(!text.load(p).isEmpty());
            QCOMPARE(get(p), data);
        }
    }
    void zipSafetyAndRoundtrip() {
        QTemporaryDir dir;
        std::atomic_bool cancel = false;
        QVERIFY(QDir().mkpath(dir.filePath("source/nested")));
        put(dir.filePath("source/nested/中文.txt"), "payload");
        const auto archive = dir.filePath("sample.zip"), target = dir.filePath("expanded");
        QVERIFY2(Files::packZip({dir.filePath("source")}, archive, cancel).isEmpty(), "pack");
        auto error = Files::unpackZip(archive, target, cancel);
        QVERIFY2(error.isEmpty(), qPrintable(error));
        QCOMPARE(get(target + "/source/nested/中文.txt"), QByteArray("payload"));
        QVERIFY(!Files::unpackZip(archive, target, cancel).isEmpty());
        QVERIFY(!Files::packZip({dir.filePath("source")}, archive, cancel).isEmpty());
        QVERIFY(!Files::packZip({dir.filePath("source")}, dir.filePath("source/self.zip"), cancel).isEmpty());
        cancel = true;
        QVERIFY(!Files::unpackZip(archive, dir.filePath("cancelled"), cancel).isEmpty());
        cancel = false;
        QVERIFY(!Files::unpackZip(archive, dir.filePath("cancelled"), cancel, [&](const QString &, qint64 n, qint64) {
                     if (n > 0)
                         cancel = true;
                 }).isEmpty());
        QVERIFY(!QFileInfo::exists(dir.filePath("cancelled")));
        cancel = false;
        // Stored ZIP fixtures make corruption and hostile entry paths explicit.
        auto fixture = [&](const QStringList &names, bool link = false) {
            auto *a = archive_write_new();
            archive_write_set_format_zip(a);
            archive_write_set_options(a, "zip:compression=store");
            QCOMPARE(archive_write_open_filename(a, QFile::encodeName(archive)), ARCHIVE_OK);
            for (const auto &name : names) {
                auto *entry = archive_entry_new();
                archive_entry_set_pathname_utf8(entry, name.toUtf8());
                archive_entry_set_filetype(entry, link ? AE_IFLNK : AE_IFREG);
                archive_entry_set_perm(entry, 0600);
                archive_entry_set_size(entry, link ? 0 : 7);
                if (link)
                    archive_entry_set_symlink(entry, "../outside");
                QCOMPARE(archive_write_header(a, entry), ARCHIVE_OK);
                if (!link)
                    QCOMPARE(archive_write_data(a, "payload", 7), 7);
                archive_entry_free(entry);
            }
            archive_write_close(a);
            archive_write_free(a);
        };
        for (const auto &name : {QString("../outside"), dir.filePath("outside"), QString("a/../../outside"),
                                 QString("..\\outside"), QString("C:/outside")}) {
            fixture({name});
            QVERIFY(!Files::unpackZip(archive, dir.filePath("bad"), cancel).isEmpty());
            QVERIFY(!QFileInfo::exists(dir.filePath("bad")));
            QVERIFY(!QFileInfo::exists(dir.filePath("outside")));
        }
        fixture({"link"}, true);
        QVERIFY(!Files::unpackZip(archive, dir.filePath("bad"), cancel).isEmpty());
        fixture({"duplicate", "duplicate"});
        QVERIFY(!Files::unpackZip(archive, dir.filePath("bad"), cancel).isEmpty());
        fixture({"good"});
        auto bytes = get(archive);
        const int payload = bytes.indexOf("payload");
        QVERIFY(payload >= 0);
        bytes[payload] = 'X';
        put(archive, bytes);
        QVERIFY(!Files::unpackZip(archive, dir.filePath("bad"), cancel).isEmpty());
        fixture({"good"});
        bytes = get(archive);
        bytes.chop(10);
        put(archive, bytes);
        QVERIFY(!Files::unpackZip(archive, dir.filePath("bad"), cancel).isEmpty());
        fixture({"good"});
        bytes = get(archive);
        auto end = bytes.lastIndexOf(QByteArray("PK\5\6", 4));
        QVERIFY(end >= 0);
        qToLittleEndian<quint16>(50001, bytes.data() + end + 10);
        put(archive, bytes);
        QVERIFY(!Files::unpackZip(archive, dir.filePath("bad"), cancel).isEmpty());
        QVERIFY(QDir(dir.path())
                    .entryList({".jume-*"}, QDir::Dirs | QDir::Files | QDir::Hidden | QDir::NoDotAndDotDot)
                    .isEmpty());
    }
    void clipboardAndResponsiveWork() {
        QTemporaryDir dir;
        QVERIFY(QDir().mkpath(dir.filePath("destination")));
        put(dir.filePath("a.txt"), "alpha");
        put(dir.filePath("b.txt"), "beta");
        FileWindow window(dir.path(), dir.path(), {});
        window.show();
        QTRY_COMPARE(window.folder, dir.path());
        QTRY_COMPARE(window.sorted.rowCount(window.table->rootIndex()), 3);
        auto *selection = window.table->selectionModel();
        for (const auto &name : {"a.txt", "b.txt"})
            selection->select(window.fileIndex(dir.filePath(name)),
                              QItemSelectionModel::Select | QItemSelectionModel::Rows);
        window.clipboardSelection(false);
        QCOMPARE(window.clipboard.size(), 2);
        QVERIFY(window.clipboardPanel->isVisible());
        window.navigate(dir.filePath("destination"));
        QTRY_COMPARE(window.folder, dir.filePath("destination"));
        window.paste();
        QTRY_VERIFY(!window.worker.isRunning());
        QCOMPARE(get(dir.filePath("destination/a.txt")), QByteArray("alpha"));
        QCOMPARE(get(dir.filePath("destination/b.txt")), QByteArray("beta"));
        QVERIFY(window.worker.result().isEmpty());
        QCOMPARE(window.clipboard.size(), 2); // Copy can be pasted again.
        window.navigate(dir.path());
        QTRY_COMPARE(window.folder, dir.path());
        selection->select(window.fileIndex(dir.filePath("a.txt")),
                          QItemSelectionModel::ClearAndSelect | QItemSelectionModel::Rows);
        window.clipboardSelection(true);
        QVERIFY(QDir().mkdir(dir.filePath("moved")));
        window.navigate(dir.filePath("moved"));
        QTRY_COMPARE(window.folder, dir.filePath("moved"));
        window.paste();
        QTRY_VERIFY(!window.worker.isRunning());
        QTRY_VERIFY(window.clipboard.isEmpty());
        QVERIFY(!QFileInfo::exists(dir.filePath("a.txt")));
        QCOMPARE(get(dir.filePath("moved/a.txt")), QByteArray("alpha"));
        // The same real worker path with a deliberately slow I/O fixture, no GUI sleep.
        int ticks = 0;
        QTimer heartbeat;
        heartbeat.setInterval(10);
        connect(&heartbeat, &QTimer::timeout, this, [&] { ++ticks; });
        heartbeat.start();
        window.run("后台响应检查", [](std::atomic_bool &cancel, const Files::Progress &progress) {
            for (int i = 0; i < 100; ++i) {
                if (cancel)
                    return QString("已取消");
                progress("fixture.bin", i, 100);
                QThread::msleep(5);
            }
            return QString();
        });
        window.navigate(dir.path());
        QTRY_COMPARE(window.folder, dir.path());
        QTest::qWait(100);
        QVERIFY(ticks >= 3);
        QVERIFY(window.worker.isRunning());
        QVERIFY(!QApplication::activeModalWidget());
        const auto capture = qEnvironmentVariable("JUME_FILES_CAPTURE_DIR");
        if (!capture.isEmpty())
            QVERIFY(window.grab().save(capture + "/files-task.png"));
        window.findChild<QPushButton *>("cancelTask")->click();
        QTRY_VERIFY(!window.worker.isRunning());
        QCOMPARE(window.worker.result(), QString("已取消"));
        selection->select(window.fileIndex(dir.filePath("b.txt")),
                          QItemSelectionModel::ClearAndSelect | QItemSelectionModel::Rows);
        QTimer::singleShot(20, [] {
            auto *dialog = qobject_cast<QInputDialog *>(QApplication::activeModalWidget());
            if (dialog) {
                dialog->setTextValue("ui.zip");
                dialog->accept();
            }
        });
        window.findChild<QAction *>("压缩为 ZIP…")->trigger();
        QTRY_VERIFY(!window.worker.isRunning());
        QVERIFY2(window.worker.result().isEmpty(), qPrintable(window.worker.result()));
        QVERIFY(QFileInfo::exists(dir.filePath("ui.zip")));
        QTRY_VERIFY(window.fileIndex(dir.filePath("ui.zip")).isValid());
        selection->select(window.fileIndex(dir.filePath("ui.zip")),
                          QItemSelectionModel::ClearAndSelect | QItemSelectionModel::Rows);
        QTimer::singleShot(20, [] {
            auto *dialog = qobject_cast<QInputDialog *>(QApplication::activeModalWidget());
            if (dialog) {
                dialog->setTextValue("ui-unpacked");
                dialog->accept();
            }
        });
        window.findChild<QAction *>("解压 ZIP…")->trigger();
        QTRY_VERIFY(!window.worker.isRunning());
        QVERIFY2(window.worker.result().isEmpty(), qPrintable(window.worker.result()));
        QCOMPARE(get(dir.filePath("ui-unpacked/b.txt")), QByteArray("beta"));
        heartbeat.stop();
        QTest::qWait(100);
        QVERIFY(!window.taskTimer.isActive());
        window.close();
    }
    void crossVolumeCut() {
        if (!QDir("/dev/shm").exists())
            QSKIP("Linux second filesystem fixture unavailable");
        QTemporaryDir dir, other("/dev/shm/jume-files-XXXXXX");
        QVERIFY(other.isValid());
        struct stat a {
        }, b{};
        QVERIFY(!stat(QFile::encodeName(dir.path()), &a));
        QVERIFY(!stat(QFile::encodeName(other.path()), &b));
        if (a.st_dev == b.st_dev)
            QSKIP("Need separate filesystems");
        const auto source = dir.filePath("source.txt"), destination = other.filePath("moved.txt");
        put(source, "recoverable");
        std::atomic_bool cancel = false;
        const auto error = Files::transfer(source, destination, true, cancel);
        QVERIFY2(error.isEmpty(), qPrintable(error));
        QVERIFY(!QFileInfo::exists(source));
        QCOMPARE(get(destination), QByteArray("recoverable"));
    }
    void largeDirectoryAndNavigation() {
        QTemporaryDir dir;
        QVERIFY(QDir().mkdir(dir.filePath("other")));
        for (int i = 0; i < 3000; ++i)
            put(dir.filePath(QString("item-%1.txt").arg(i, 4, 10, QChar('0'))), "row");
        FileWindow window(dir.path(), dir.path(), {});
        window.show();
        int ticks = 0;
        QTimer heartbeat;
        heartbeat.setInterval(10);
        connect(&heartbeat, &QTimer::timeout, this, [&] { ++ticks; });
        heartbeat.start();
        QTRY_COMPARE(window.folder, dir.path());
        QTRY_COMPARE_WITH_TIMEOUT(window.sorted.rowCount(window.table->rootIndex()), 3001, 5000);
        QVERIFY(window.list->findChildren<QWidget *>().size() < 20);
        QVERIFY(ticks > 0);
        for (int i = 0; i < 30; ++i) {
            window.navigate(dir.filePath("other"));
            window.navigate(dir.path());
        }
        window.navigate(dir.filePath("other"));
        QTRY_COMPARE(window.folder, dir.filePath("other"));
        QVERIFY(window.pendingFolder.isEmpty());
        window.navigate(dir.path());
        QTRY_COMPARE(window.folder, dir.path());
        window.list->setFocus();
        window.list->setCurrentIndex(window.fileIndex(dir.filePath("item-0000.txt")));
        window.controllerAction("quick");
        window.controllerAction("down");
        window.controllerAction("accept");
        QCOMPARE(window.selectedPaths().size(), 2);
        window.controllerAction("quick");
        QVERIFY(!window.multiSelect);
        window.location->setFocus();
        window.location->selectAll();
        QTest::keyClick(window.location, Qt::Key_C, Qt::ControlModifier);
        QVERIFY(window.clipboard.isEmpty()); // Native text shortcuts stay native.
        heartbeat.stop();
        qInfo() << "FILES_RESPONSIVENESS rows=3001 heartbeat_ticks=" << ticks
                << " row_widgets=" << window.list->findChildren<QWidget *>().size();
    }
    void sortingCompactLayoutAndPreferences() {
        QTemporaryDir dir;
        const auto data = dir.filePath("data");
        QVERIFY(QDir().mkpath(data + "/z-dir"));
        put(data + "/file2.txt", "22");
        put(data + "/file10.txt", "123456789");
        put(data + "/alpha.png", "12345");
        int stamp = 1000;
        for (const auto &name : {"file10.txt", "file2.txt", "alpha.png"}) {
            QFile file(data + '/' + name);
            QVERIFY(file.open(QIODevice::ReadWrite));
            QVERIFY(file.setFileTime(QDateTime::fromSecsSinceEpoch(stamp++), QFileDevice::FileModificationTime));
        }
        FileWindow window(dir.path(), data, {});
        window.show();
        QTRY_COMPARE(window.folder, data);
        QTRY_COMPARE(window.sorted.rowCount(window.table->rootIndex()), 4);
        QVERIFY(window.sidebar->isHidden());
        QVERIFY(window.list->width() > 600);
        QVERIFY(window.list->height() > 380);
        auto names = [&] {
            QStringList names;
            for (int row = 0; row < window.sorted.rowCount(window.table->rootIndex()); ++row)
                names << window.sorted.index(row, 0, window.table->rootIndex()).data().toString();
            return names;
        };
        QCOMPARE(names(), QStringList({"z-dir", "alpha.png", "file2.txt", "file10.txt"}));
        window.list->setCurrentIndex(window.fileIndex(data + "/file2.txt"));
        window.findChild<QAction *>("sortDescending")->trigger();
        QCOMPARE(names(), QStringList({"z-dir", "file10.txt", "file2.txt", "alpha.png"}));
        QCOMPARE(window.selectedPaths(), QStringList({data + "/file2.txt"}));
        window.findChild<QAction *>("sort-1")->trigger();
        QCOMPARE(names(), QStringList({"z-dir", "file10.txt", "alpha.png", "file2.txt"}));
        window.findChild<QAction *>("sortDescending")->trigger();
        QCOMPARE(names(), QStringList({"z-dir", "file2.txt", "alpha.png", "file10.txt"}));
        window.findChild<QAction *>("sort-2")->trigger();
        QCOMPARE(names(), QStringList({"z-dir", "alpha.png", "file2.txt", "file10.txt"}));
        window.findChild<QAction *>("sort-3")->trigger();
        QCOMPARE(names(), QStringList({"z-dir", "file10.txt", "file2.txt", "alpha.png"}));
        window.findChild<QAction *>("foldersFirst")->trigger();
        QCOMPARE(names(), QStringList({"file10.txt", "file2.txt", "alpha.png", "z-dir"}));
        window.findChild<QAction *>("showPlaces")->trigger();
        QVERIFY(!window.sidebar->isHidden());
        const auto capture = qEnvironmentVariable("JUME_FILES_CAPTURE_DIR");
        bool menuFits = false;
        QTimer::singleShot(30, [&] {
            menuFits = window.menu->height() <= window.height() && window.menu->width() <= window.width() &&
                       window.rect().contains(window.mapFromGlobal(window.menu->geometry().bottomRight()));
            if (!capture.isEmpty())
                window.menu->grab().save(capture + "/files-menu.png");
            window.menu->close();
        });
        window.showActions();
        QVERIFY(menuFits);
        QTRY_VERIFY(!window.preferencesWrite.isRunning() && !window.pendingPreferences);
        window.close();
        FileWindow restored(dir.path(), data, {});
        QCOMPARE(restored.sorted.sortColumn(), 3);
        QCOMPARE(restored.sorted.sortOrder(), Qt::AscendingOrder);
        QVERIFY(!restored.sorted.foldersFirst);
        QVERIFY(!restored.sidebar->isHidden());
    }
    void officeSafety() {
        QTemporaryDir dir;
        const auto p = dir.filePath("test.docx");
        QString error;
        zip(p, "<document><p><t>Hello</t></p><p><t>World</t></p></document>");
        QCOMPARE(Files::officeText(p, &error), QString("Hello\nWorld\n"));
        QVERIFY(error.isEmpty());
        zip(p, "<!DOCTYPE d [<!ENTITY e SYSTEM 'file:///etc/passwd'>]><d>&e;</d>");
        error.clear();
        QVERIFY(Files::officeText(p, &error).isEmpty());
        QVERIFY(!error.isEmpty());
        zip(p, QByteArray(Files::TextLimit + 1, 'x'));
        error.clear();
        QVERIFY(Files::officeText(p, &error).isEmpty());
        QVERIFY(!error.isEmpty());
    }
    void usbPolicyAndCalls() {
        qDBusRegisterMetaType<DiskInterfaces>();
        qDBusRegisterMetaType<DiskObjects>();
        qDBusRegisterMetaType<QList<QByteArray>>();
        auto objects = disks();
        QCOMPARE(Storage::usbDevices(objects).size(), 1);
        const auto d = QDBusObjectPath("/org/freedesktop/UDisks2/drives/usb"),
                   b = QDBusObjectPath("/org/freedesktop/UDisks2/block_devices/sda1");
        objects[d]["org.freedesktop.UDisks2.Drive"]["ConnectionBus"] = "mmc";
        QVERIFY(Storage::usbDevices(objects).isEmpty());
        objects = disks();
        objects[b]["org.freedesktop.UDisks2.Block"]["HintSystem"] = true;
        QVERIFY(Storage::usbDevices(objects).isEmpty());
        auto bus = QDBusConnection::sessionBus();
        if (!bus.isConnected())
            QSKIP("Run under dbus-run-session for real message serialization");
        DiskFixture fixture;
        fixture.objects = disks();
        MountFixture mount;
        QTemporaryDir directory;
        mount.directory = directory.path();
        QVERIFY(bus.registerService("org.freedesktop.UDisks2"));
        QVERIFY(bus.registerObject("/org/freedesktop/UDisks2", &fixture, QDBusConnection::ExportAllSlots));
        QVERIFY(bus.registerObject(b.path(), &mount, QDBusConnection::ExportAllSlots));
        {
            Storage storage(bus);
            QTRY_VERIFY(!storage.busy);
            QCOMPARE(storage.devices.size(), 1);
            const auto expected = storage.devices.first().toMap();
            QSignalSpy ready(&storage, &Storage::mounted);
            storage.mount(expected, false);
            QTRY_COMPARE(ready.size(), 1);
            QCOMPARE(mount.calls, 1);
            QCOMPARE(mount.options.value("options").toString(), QString("nosuid,nodev,noexec"));
            QVERIFY(mount.options.value("auth.no_user_interaction").toBool());
            fixture.objects[b]["org.freedesktop.UDisks2.Filesystem"]["MountPoints"] =
                QVariant::fromValue(QList<QByteArray>{QFile::encodeName(directory.path()) + '\0'});
            storage.refresh();
            QTRY_VERIFY(!storage.busy);
            const auto mounted = storage.devices.first().toMap();
            storage.mount(mounted, true);
            QTRY_VERIFY(!storage.busy);
            QCOMPARE(mount.calls, 2);
            QVERIFY(!mount.options.contains("force"));
            fixture.objects = disks();
            fixture.objects[b]["org.freedesktop.UDisks2.Block"]["IdUUID"] = "replaced";
            storage.mount(expected, false);
            QTRY_VERIFY(!storage.busy);
            QCOMPARE(mount.calls, 2);
            QVERIFY(!storage.error.isEmpty());
        }
        bus.unregisterObject("/org/freedesktop/UDisks2", QDBusConnection::UnregisterTree);
        bus.unregisterService("org.freedesktop.UDisks2");
    }
    void previewsAndUnsavedClose() {
        QTemporaryDir dir;
        const auto p = dir.filePath("text.txt");
        put(p, "hello");
        Preview text(p, true);
        text.show();
        auto *editor = text.findChild<QPlainTextEdit *>("textEditor");
        QVERIFY(editor);
        QTRY_COMPARE(editor->toPlainText(), QString("hello"));
        QVERIFY(!editor->isReadOnly());
        editor->insertPlainText("changed");
        QVERIFY(editor->document()->isModified());
        QTimer::singleShot(20, [] {
            auto *box = qobject_cast<QMessageBox *>(QApplication::activeModalWidget());
            if (box)
                box->done(QMessageBox::Cancel);
        });
        text.reject();
        QVERIFY(text.isVisible());
        QCOMPARE(get(p), QByteArray("hello"));
        QTimer::singleShot(20, [] {
            auto *box = qobject_cast<QMessageBox *>(QApplication::activeModalWidget());
            if (box)
                box->done(QMessageBox::Discard);
        });
        text.reject();
        QVERIFY(!text.isVisible());
        Preview saving(p, true);
        saving.show();
        auto *saveEditor = saving.findChild<QPlainTextEdit *>("textEditor");
        QTRY_VERIFY(!saveEditor->isReadOnly());
        saveEditor->setPlainText("saved asynchronously");
        saveEditor->document()->setModified(true);
        QTimer::singleShot(20, [] {
            auto *box = qobject_cast<QMessageBox *>(QApplication::activeModalWidget());
            if (box)
                box->done(QMessageBox::Save);
        });
        saving.reject();
        QTRY_VERIFY(!saving.isVisible());
        QCOMPARE(get(p), QByteArray("saved asynchronously"));
        QImage image(320, 200, QImage::Format_RGB32);
        image.fill(Qt::red);
        QVERIFY(image.save(dir.filePath("image.png")));
        Preview picture(dir.filePath("image.png"));
        picture.show();
        auto *imageLabel = qobject_cast<QLabel *>(picture.findChild<QScrollArea *>()->widget());
        QVERIFY(imageLabel);
        QTRY_VERIFY(!imageLabel->pixmap().isNull());
        {
            QPdfWriter writer(dir.filePath("paper.pdf"));
            writer.setResolution(72);
            QPainter painter(&writer);
            painter.setFont(QFont("sans-serif", 22));
            painter.drawText(40, 80, "Jume PDF fixture");
        }
        Preview pdf(dir.filePath("paper.pdf"));
        pdf.show();
        auto *doc = pdf.findChild<QPdfDocument *>();
        QVERIFY(doc);
        QTRY_COMPARE(doc->pageCount(), 1);
        const auto rendered = doc->render(0, QSize(595, 842));
        QVERIFY(!rendered.isNull());
        int ink = 0;
        for (int y = 0; y < rendered.height(); ++y)
            for (int x = 0; x < rendered.width(); ++x)
                if (qAlpha(rendered.pixel(x, y)) > 128 && qGray(rendered.pixel(x, y)) < 100)
                    ++ink;
        QVERIFY(ink > 100);
        QTest::qWait(150); // Allow the view's async page request to compose before capture.
        const auto capture = qEnvironmentVariable("JUME_FILES_CAPTURE_DIR");
        if (!capture.isEmpty())
            QVERIFY(pdf.grab().save(capture + "/pdf.png"));
    }
    void fileViewsAndMedia() {
        QTemporaryDir dir;
        put(dir.filePath("notes.txt"), "Jume file manager fixture\n");
        QDir().mkdir(dir.filePath("Documents"));
        FileWindow window(dir.path(), dir.path(), {{"测试文档", dir.filePath("Documents")}});
        window.show();
        auto *table = window.findChild<QTreeView *>();
        QVERIFY(table);
        QTRY_VERIFY(table->model()->rowCount(table->rootIndex()) >= 2);
        const auto captures = qEnvironmentVariable("JUME_FILES_CAPTURE_DIR");
        if (!captures.isEmpty())
            QVERIFY(window.grab().save(captures + "/files-list.png"));
        window.controllerAction("erase");
        QVERIFY(table->isVisible());
        if (!captures.isEmpty())
            QVERIFY(window.grab().save(captures + "/files-table.png"));
        window.close();
        if (QStandardPaths::findExecutable("ffmpeg").isEmpty())
            QSKIP("ffmpeg fixture generator unavailable");
        const auto clip = dir.filePath("clip.mp4");
        QCOMPARE(QProcess::execute("ffmpeg", {"-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x120:r=10",
                                              "-t", "0.5", "-an", "-c:v", "mpeg4", clip}),
                 0);
        Preview movie(clip);
        auto *player = movie.findChild<QMediaPlayer *>();
        QVERIFY(player);
        QVideoSink sink;
        player->setVideoSink(&sink);
        player->setAudioOutput(nullptr);
        QSignalSpy frames(&sink, &QVideoSink::videoFrameChanged);
        player->play();
        QTRY_VERIFY_WITH_TIMEOUT(!frames.isEmpty(), 5000);
        QVERIFY(qvariant_cast<QVideoFrame>(frames.first().first()).isValid());
        player->stop();
        const auto sound = dir.filePath("sound.wav");
        QCOMPARE(QProcess::execute("ffmpeg",
                                   {"-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", sound}),
                 0);
        if (qEnvironmentVariableIsSet("JUME_FILES_AUDIO_TEST"))
            QTRY_VERIFY_WITH_TIMEOUT(!QMediaDevices::audioOutputs().isEmpty(), 3000);
        Preview audio(sound);
        auto *soundPlayer = audio.findChild<QMediaPlayer *>();
        QVERIFY(soundPlayer);
        QAudioBufferOutput buffers;
        QSignalSpy pcm(&buffers, &QAudioBufferOutput::audioBufferReceived);
        soundPlayer->setAudioBufferOutput(&buffers);
        if (qEnvironmentVariableIsSet("JUME_FILES_AUDIO_TEST")) {
            QVERIFY(!soundPlayer->audioOutput()->device().isNull());
            qInfo() << "AUDIO_FIXTURE_DEVICE" << soundPlayer->audioOutput()->device().description()
                    << soundPlayer->audioOutput()->volume() << soundPlayer->audioOutput()->isMuted();
        }
        if (!qEnvironmentVariableIsSet("JUME_FILES_AUDIO_TEST"))
            soundPlayer->setAudioOutput(nullptr);
        soundPlayer->play();
        QTRY_VERIFY_WITH_TIMEOUT(soundPlayer->duration() > 0, 5000);
        QVERIFY(soundPlayer->hasAudio());
        if (qEnvironmentVariableIsSet("JUME_FILES_AUDIO_TEST"))
            QTRY_COMPARE_WITH_TIMEOUT(soundPlayer->mediaStatus(), QMediaPlayer::EndOfMedia, 5000);
        if (qEnvironmentVariableIsSet("JUME_FILES_AUDIO_TEST")) {
            int peak = 0;
            for (const auto &row : pcm) {
                const auto buffer = qvariant_cast<QAudioBuffer>(row.first());
                if (buffer.format().sampleFormat() == QAudioFormat::Int16)
                    for (int i = 0; i < buffer.sampleCount(); ++i)
                        peak = qMax(peak, qAbs(int(buffer.constData<qint16>()[i])));
            }
            qInfo() << "DECODED_PCM_PEAK" << peak;
            QVERIFY(peak > 500);
        }
        soundPlayer->stop();
    }
};
QTEST_MAIN(Check)
#include "check.moc"
