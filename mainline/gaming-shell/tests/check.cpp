#include "input.h"
#include "preferences.h"
#include "fonts.h"
#include "telemetry.h"
#include "applications.h"
#include "streaming.h"
#include "device.h"
#include "network.h"
#include "tools.h"
#include <QCryptographicHash>
#include <QJsonArray>
#include <QFile>
#include <QSaveFile>
#include "taskimages.h"
#include <QFontDatabase>
#include <QFontInfo>
#include <QFontMetrics>
#include <QJsonDocument>
#include <QJsonObject>
#include <QInputMethod>
#include <QQuickItem>
#include <QQuickView>
#include <QPointer>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQmlProperty>
#include <QSignalSpy>
#include <QStandardItemModel>
#include <QAccessible>
#include <QStyleHints>
#include <QTemporaryDir>
#include <QDirIterator>
#include <QMap>
#include <cmath>
#include <memory>
#include <tuple>
#include <algorithm>
#include <QRegularExpression>
#include <QtTest>
#include <sys/stat.h>
#include <unistd.h>
#include <signal.h>

// The Theme singleton of an engine, resolved through the same directory import as ShellView.
static QObject *shellTheme(QQmlEngine *engine, QScopedPointer<QObject> &holder) {
    QQmlComponent probe(engine);
    probe.setData("import QtQuick\nimport \"controls\" as Ui\nQtObject { property QtObject theme: Ui.Theme }",
        QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ThemeProbe.qml")));
    holder.reset(probe.create());
    if (!holder) qWarning("%s", qPrintable(probe.errorString()));
    return holder ? holder->property("theme").value<QObject *>() : nullptr;
}
static double contrast(const QColor &first, const QColor &second) {
    const auto luminance = [](const QColor &color) {
        const auto channel = [](double value) { return value <= 0.03928 ? value / 12.92 : std::pow((value + 0.055) / 1.055, 2.4); };
        return 0.2126 * channel(color.redF()) + 0.7152 * channel(color.greenF()) + 0.0722 * channel(color.blueF());
    };
    const auto a = luminance(first), b = luminance(second);
    return (qMax(a, b) + 0.05) / (qMin(a, b) + 0.05);
}

// The §8 reference library: a version 2 manifest (an unsupported entry included), recent entries
// relative to ReferenceClock and one favorite. Returns the manifest path.
static const QDateTime ReferenceClock(QDate(2026, 10, 27), QTime(16, 39));
static QString referenceLibrary(const QString &directory, Preferences &state) {
    QJsonArray entries;
    for (const auto &[id, title, system] : {std::tuple{"native.mslug", "Metal Slug", "Neo Geo"}, {"native.1944", "1944", "Neo Geo"},
             {"native.gta3", "GTA III", "Ports"}, {"native.gtavc", "Vice City", "Ports"}, {"native.stardew", "Stardew Valley", "Ports"}}) {
        QJsonObject entry{{"id", id}, {"title", title}, {"system", system}, {"program", "/bin/sleep"}, {"arguments", QJsonArray{"60"}}};
        if (QString(system) == "Neo Geo") entry["core"] = "FBNeo";
        if (QString(id) == "native.stardew") entry["supported"] = false;
        entries.append(entry);
    }
    const auto path = directory + "/applications.json";
    QFile file(path);
    if (!file.open(QIODevice::WriteOnly)) return {};
    file.write(QJsonDocument(QJsonObject{{"version", 2}, {"applications", entries}}).toJson()); file.close();
    QFile::setPermissions(path, QFileDevice::ReadOwner | QFileDevice::WriteOwner);
    for (const auto &[id, days] : {std::pair{"native.gtavc", 5}, {"builtin.moonlight", 3}, {"native.gta3", 2}, {"native.mslug", 1}})
        state.recordRecent(id, ReferenceClock.addDays(-days).toSecsSinceEpoch());
    state.toggleApplicationFavorite("native.mslug"); state.save();
    return path;
}

// First item named `name` in the visual tree below `root` (Repeater delegates included).
static QQuickItem *findItem(QQuickItem *root, const QString &name) {
    QList<QQuickItem *> pending{root};
    while (!pending.isEmpty()) {
        auto *item = pending.takeFirst();
        if (item->objectName() == name) return item;
        pending.append(item->childItems());
    }
    return nullptr;
}

// §3 and §9: visible text is never below micro (18 px × font scale); glyph-badge letters are the
// one exception. Returns "size px "text"" for each offender.
// Hold captures land past the 600 ms ring delay and before the 1 s exit (capture() adds 150 ms).
static constexpr int HoldCaptureMs = 650;
static QStringList smallText(QQuickItem *root, qreal fontScale) {
    QStringList result;
    QList<QQuickItem *> pending{root};
    while (!pending.isEmpty()) {
        auto *item = pending.takeLast();
        if (!item->isVisible() || item->opacity() <= 0 || item->objectName() == "glyphLetter") continue;
        pending.append(item->childItems());
        if (!item->inherits("QQuickText") && !item->inherits("QQuickTextInput") && !item->inherits("QQuickTextEdit")) continue;
        const auto text = item->property("text").toString();
        const auto font = item->property("font").value<QFont>();
        const int size = font.pixelSize() > 0 ? font.pixelSize() : QFontInfo(font).pixelSize();
        if (!text.trimmed().isEmpty() && size + 0.5 < 18 * fontScale) result << QString("%1 px \"%2\"").arg(size).arg(text.left(24));
    }
    return result;
}

class ShellCheck final : public QObject {
    Q_OBJECT
private slots:
    void initTestCase() {
        QGuiApplication::setApplicationDisplayName(QStringLiteral(JUME_LAUNCHER_NAME));
        QCoreApplication::setApplicationVersion(QStringLiteral(JUME_LAUNCHER_VERSION));
        QGuiApplication::styleHints()->setTabFocusBehavior(Qt::TabFocusAllControls);
        // Noto Sans SC when R46H_UI_FONT_DIR or the packaged copy exists; captures record which one ran.
        qInfo("INTERFACE_FONT %s", registerInterfaceFonts() ? "noto-sans-sc" : "fallback");
    }
    void init() {
        // §7.6: a hint naming an unknown button is a page bug; HintBar reports it instead of drawing it.
        QTest::failOnWarning(QRegularExpression(QStringLiteral("HintBar: unknown button")));
    }
    void preferencesRoundtripAndFailure() {
        QTemporaryDir directory;
        QVERIFY(directory.isValid());
        {
            Preferences state(directory.path());
            state.adjust("volume", 200); QCOMPARE(state.volume(), 100);
            state.adjust("brightness", -200); QCOMPARE(state.brightness(), 10);
            state.adjust("motion", 1);
            state.toggleFavorite(2); state.toggleFavorite(999);
            QVERIFY(!state.monitorDetail()); QVERIFY(state.choose("monitorDetail", 1)); QVERIFY(!state.choose("monitorDetail", 2));
            QVERIFY(state.save()); QVERIFY(!state.dirty());
        }
        Preferences reloaded(directory.path());
        QCOMPARE(reloaded.volume(), 100); QCOMPARE(reloaded.brightness(), 10); QVERIFY(reloaded.monitorDetail());
        QVERIFY(reloaded.reducedMotion()); QVERIFY(reloaded.isFavorite(2));
        reloaded.toggleFavorite(2); QVERIFY(!reloaded.isFavorite(2));
        const auto blockedPath = directory.filePath("blocked");
        QFile blocked(blockedPath); QVERIFY(blocked.open(QIODevice::WriteOnly)); blocked.write("keep"); blocked.close();
        Preferences failed(blockedPath);
        failed.adjust("volume", -5);
        QVERIFY(!failed.save()); QVERIFY(failed.dirty()); QCOMPARE(failed.volume(), 50);
        QVERIFY(!failed.error().isEmpty());
        QVERIFY(blocked.open(QIODevice::ReadOnly)); QCOMPARE(blocked.readAll(), QByteArray("keep")); blocked.close();
        QVERIFY(blocked.remove()); QVERIFY(failed.save()); QVERIFY(!failed.dirty());
        QFile corrupt(directory.filePath("preview.json")); QVERIFY(corrupt.open(QIODevice::WriteOnly)); corrupt.write("broken"); corrupt.close();
        Preferences invalid(directory.path()); QVERIFY(!invalid.error().isEmpty());
        invalid.adjust("volume", 5); QVERIFY(!invalid.save());
        QVERIFY(corrupt.open(QIODevice::ReadOnly)); QCOMPARE(corrupt.readAll(), QByteArray("broken"));
    }
    void unreadableDirectoryKeepsExistingPreferences() {
        if (geteuid() == 0) QSKIP("Permission denial must be checked as an unprivileged user");
        QTemporaryDir directory; QVERIFY(directory.isValid());
        Preferences initial(directory.path()); initial.adjust("volume", 30); initial.toggleFavorite(2);
        QVERIFY(initial.save());
        QFile file(directory.filePath("preview.json")); QVERIFY(file.open(QIODevice::ReadOnly));
        const auto original = file.readAll(); file.close();
        const auto path = QFile::encodeName(directory.path());
        QVERIFY(::chmod(path.constData(), 0000) == 0);
        Preferences denied(directory.path());
        // Restore access before assertions or cleanup, including when the regression fails.
        QVERIFY(::chmod(path.constData(), 0700) == 0);
        QVERIFY(!denied.error().isEmpty()); denied.adjust("brightness", 5);
        QVERIFY(!denied.save()); QVERIFY(denied.dirty());
        QVERIFY(file.open(QIODevice::ReadOnly)); QCOMPARE(file.readAll(), original); file.close();
        Preferences recovered(directory.path());
        QVERIFY(recovered.error().isEmpty()); QCOMPARE(recovered.volume(), 85); QVERIFY(recovered.isFavorite(2));
    }
    void keyboardNavigationAndModalIsolation() {
        QTemporaryDir directory;
        Preferences state(directory.path());
        Telemetry metrics(directory.path());
        ControllerInput controller;
        QQuickView view;
        view.setInitialProperties({{"store", QVariant::fromValue(&state)}, {"metrics", QVariant::fromValue(&metrics)}, {"controller", QVariant::fromValue(&controller)}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));
        QCOMPARE(view.status(), QQuickView::Ready);
        view.resize(1024, 768); view.show();
        QVERIFY(QTest::qWaitForWindowExposed(&view));
        auto *root = view.rootObject(); QVERIFY(root);
        view.requestActivate(); QVERIFY(QTest::qWaitForWindowActive(&view));
        root->forceActiveFocus();
        QTest::qWait(300);
        QSignalSpy idleFrames(&view, &QQuickWindow::frameSwapped);
        QTest::qWait(600);
        QVERIFY2(idleFrames.size() <= 3, "Static shell must not repaint continuously");
        QVERIFY2(root->hasActiveFocus(), qPrintable(QString("Unexpected focus: %1").arg(view.activeFocusItem() ? view.activeFocusItem()->metaObject()->className() : "none")));
        auto key = [&](Qt::Key key) { QTest::keyClick(&view, key); QCoreApplication::processEvents(); };
        key(Qt::Key_Right); QCOMPARE(root->property("selected").toInt(), 1);
        key(Qt::Key_X); QVERIFY(state.isFavorite(1));
        // Start (M) lists the card's actions, X included; the menu owns the keys until it closes.
        auto *options = root->findChild<QObject *>("optionsMenu"); QVERIFY(options);
        key(Qt::Key_M); QVERIFY(options->property("open").toBool());
        key(Qt::Key_Down); key(Qt::Key_Return); QVERIFY(!options->property("open").toBool()); QVERIFY(!state.isFavorite(1));
        key(Qt::Key_M); key(Qt::Key_M); QVERIFY(!options->property("open").toBool());
        key(Qt::Key_X); QVERIFY(state.isFavorite(1));
        key(Qt::Key_Escape); QCOMPARE(root->property("page").toInt(), 0); QVERIFY(!root->property("dockFocused").toBool()); // Home B does nothing.
        key(Qt::Key_Return); QVERIFY(root->property("session").toBool());
        key(Qt::Key_Right); QCOMPARE(root->property("sessionMoves").toInt(), 1);
        key(Qt::Key_Q); QVERIFY(root->property("quickOpen").toBool());
        // The quick panel opens on brightness; ←→ adjust it, Down reaches the volume row.
        key(Qt::Key_Right); QCOMPARE(state.brightness(), 75); QCOMPARE(root->property("sessionMoves").toInt(), 1);
        key(Qt::Key_Down); key(Qt::Key_Left); QCOMPARE(state.volume(), 50);
        key(Qt::Key_Escape); QVERIFY(!root->property("quickOpen").toBool());
        QVERIFY(root->property("session").toBool()); QVERIFY(!state.dirty());
        key(Qt::Key_Left); QCOMPARE(root->property("sessionMoves").toInt(), 2);
        key(Qt::Key_Escape); QVERIFY(!root->property("session").toBool()); QCOMPARE(root->property("selected").toInt(), 1);
        QVERIFY(root->property("notice").toString().isEmpty());
        key(Qt::Key_BracketRight); QCOMPARE(root->property("page").toInt(), 0); // L1/R1 have no home role.
        // §8 home: Down reaches the dock; its first tile opens the library.
        key(Qt::Key_Down); QVERIFY(root->property("dockFocused").toBool()); QCOMPARE(root->property("selected").toInt(), -1);
        key(Qt::Key_Return); QCOMPARE(root->property("page").toInt(), 1); QCOMPARE(root->property("selected").toInt(), 0);
        // Library: four columns without wrap, L2/R2 move two rows, L1/R1 filter and return to the filter's last place.
        key(Qt::Key_Right); key(Qt::Key_Down); QCOMPARE(root->property("selected").toInt(), 5);
        key(Qt::Key_Down); QCOMPARE(root->property("selected").toInt(), 5);
        key(Qt::Key_PageUp); QCOMPARE(root->property("selected").toInt(), 0);
        key(Qt::Key_PageDown); QCOMPARE(root->property("selected").toInt(), 5);
        key(Qt::Key_Up); QCOMPARE(root->property("selected").toInt(), 1);
        key(Qt::Key_Left); key(Qt::Key_Left); QCOMPARE(root->property("selected").toInt(), 0);
        key(Qt::Key_Right); key(Qt::Key_Right); key(Qt::Key_Right); key(Qt::Key_Right); QCOMPARE(root->property("selected").toInt(), 3);
        key(Qt::Key_BracketRight); QCOMPARE(root->property("libraryFilter").toInt(), 1); QCOMPARE(root->property("selected").toInt(), 1); // 收藏
        key(Qt::Key_BracketLeft); key(Qt::Key_BracketLeft); QCOMPARE(root->property("libraryFilter").toInt(), 0);
        QCOMPARE(root->property("selected").toInt(), 3);
        key(Qt::Key_Escape); QCOMPARE(root->property("page").toInt(), 0); QVERIFY(root->property("dockFocused").toBool());
        for (int i = 0; i < 6; ++i) key(Qt::Key_Right);
        QCOMPARE(root->property("dockIndex").toInt(), 5);
        key(Qt::Key_Left); key(Qt::Key_Return); QCOMPARE(root->property("page").toInt(), 2);
        QVERIFY(root->property("settingsSidebar").toBool());
        key(Qt::Key_Down); key(Qt::Key_Right); QTRY_VERIFY(root->property("settingsDetailReady").toBool()); // 显示
        key(Qt::Key_Right); QCOMPARE(state.brightness(), 80); QVERIFY(!state.dirty()); // ←→ adjust; the release saves.
        key(Qt::Key_Escape); key(Qt::Key_Escape); QCOMPARE(root->property("page").toInt(), 0); QVERIFY(!state.dirty());
        view.resize(640, 480); QTest::qWait(40);
        QVERIFY(!view.grabWindow().isNull());
    }
    void failedSaveKeepsSettingsAndPanel() {
        QTemporaryDir directory;
        const auto path = directory.filePath("not-a-directory");
        QFile file(path); QVERIFY(file.open(QIODevice::WriteOnly)); file.close();
        Preferences state(path);
        Telemetry metrics(directory.path());
        ControllerInput controller;
        QQuickView view;
        view.setInitialProperties({{"store", QVariant::fromValue(&state)}, {"metrics", QVariant::fromValue(&metrics)}, {"controller", QVariant::fromValue(&controller)}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));
        QCOMPARE(view.status(), QQuickView::Ready);
        auto *root = view.rootObject();
        auto action = [&](const QString &value, bool repeat = false) {
            QVERIFY(QMetaObject::invokeMethod(root, "dispatch", Q_ARG(QVariant, value), Q_ARG(QVariant, repeat)));
        };
        auto release = [&](const QString &value) { QVERIFY(QMetaObject::invokeMethod(root, "release", Q_ARG(QVariant, value))); };
        action("down"); for (int i = 0; i < 4; ++i) action("right");
        action("accept"); action("down"); action("right"); QTRY_VERIFY(root->property("settingsDetailReady").toBool()); // 显示
        action("right"); QVERIFY(root->property("settingsAdjusting").toBool()); QCOMPARE(state.brightness(), 75);
        release("right"); QVERIFY(!root->property("settingsAdjusting").toBool()); QVERIFY(state.dirty()); // The save on release failed.
        action("back");
        QVERIFY(!root->property("settingsSidebar").toBool()); QCOMPARE(root->property("page").toInt(), 2); QVERIFY(state.dirty());
        action("quick"); action("back"); QVERIFY(root->property("quickOpen").toBool());
        QVERIFY(file.remove()); action("back"); QVERIFY(!root->property("quickOpen").toBool());
        root->setProperty("settingsIndex", 4); // 减少动态效果
        action("accept"); QVERIFY(state.reducedMotion());
        action("accept", true); QVERIFY(state.reducedMotion());
        action("home"); action("accept", true); QVERIFY(!root->property("session").toBool());
    }
    void settingsFocusAndValueEditing() {
        QTemporaryDir directory;
        Preferences state(directory.path()); Telemetry metrics(directory.path()); ControllerInput controller;
        QQuickView view;
        view.setColor(QColor("#111a24"));
        view.setInitialProperties({{"store", QVariant::fromValue(&state)}, {"metrics", QVariant::fromValue(&metrics)}, {"controller", QVariant::fromValue(&controller)}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));
        QCOMPARE(view.status(), QQuickView::Ready); view.resize(1024, 768); view.show();
        QVERIFY(QTest::qWaitForWindowExposed(&view));
        auto *root = view.rootObject();
        auto action = [&](const QString &value, bool repeat = false) {
            QVERIFY(QMetaObject::invokeMethod(root, "dispatch", Q_ARG(QVariant, value), Q_ARG(QVariant, repeat)));
        };
        const auto captures = qEnvironmentVariable("R46H_UI_CAPTURE_DIR");
        auto capture = [&](const QString &name) {
            if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + "/" + name + ".png"));
        };
        QVERIFY(QMetaObject::invokeMethod(root, "showScene", Q_ARG(QVariant, QString("settings"))));
        QTest::qWait(200);
        auto *outline = root->findChild<QQuickItem *>("settingsFocus"); QVERIFY(outline);
        QVERIFY(root->property("settingsSidebar").toBool()); QCOMPARE(outline->x(), 0.);
        auto *settings = root->findChild<QObject *>("settingsView"); QVERIFY(settings);
        const auto settingsCategories = settings->property("categories").toList();
        // §8: eight categories; 常用 is gone.
        QCOMPARE(settings->property("categories").toStringList(), QStringList({"网络", "显示", "声音", "控制器", "电源", "性能", "存储", "系统"}));
        QVERIFY(!root->findChild<QQuickItem *>("settingsItems"));
        for (int i = 0; i < 8; ++i) action("down");
        QCOMPARE(root->property("settingsCategory").toInt(), 7);
        QCOMPARE(settings->property("openedCategory").toInt(), 0);
        QVERIFY(!root->findChild<QQuickItem *>("settingsItems")); // Moving through categories builds no detail.
        // Resting 300 ms previews the category's rows from data at hand; the focus stays on the category.
        QTest::qWait(200); QVERIFY(!root->findChild<QQuickItem *>("settingsItems"));
        QTRY_VERIFY_WITH_TIMEOUT(root->findChild<QQuickItem *>("settingsItems"), 1000);
        QVERIFY(root->property("settingsSidebar").toBool()); QVERIFY(!root->property("settingsDetailReady").toBool());
        QCOMPARE(settings->property("rows").toList().size(), 12);
        QVERIFY(!root->findChild<QQuickItem *>("settingsDetailFocus")->isVisible());
        for (int i = 0; i < 8; ++i) action("up");
        capture("settings-primary");
        action("right"); QVERIFY(!root->property("settingsSidebar").toBool());
        action("left"); // Leaving during asynchronous creation cancels the detail page.
        QVERIFY(root->property("settingsSidebar").toBool());
        QVERIFY(!root->property("settingsDetailReady").toBool()); // Back as an unfocusable preview.
        auto *categories = root->findChild<QQuickItem *>("settingsCategories"); QVERIFY(categories);
        auto row = [](QQuickItem *list) { return qobject_cast<QQuickItem *>(list->property("currentItem").value<QObject *>()); };
        QTRY_COMPARE(outline->x(), 0.); QTRY_COMPARE(outline->width(), row(categories)->width());
        action("down"); action("right"); // 显示: the brightness slider leads.
        QTRY_VERIFY(root->property("settingsDetailReady").toBool());
        auto *rows = root->findChild<QQuickItem *>("settingsItems"); QVERIFY(rows);
        auto *detailOutline = root->findChild<QQuickItem *>("settingsDetailFocus"); QVERIFY(detailOutline);
        QTRY_COMPARE(detailOutline->x(), 0.);
        QTRY_COMPARE(detailOutline->width(), row(rows)->width());
        capture("settings-secondary");
        action("down"); QCOMPARE(root->property("settingsIndex").toInt(), 1);
        QTRY_COMPARE(detailOutline->y(), row(rows)->mapToItem(detailOutline->parentItem(), QPointF()).y());
        QCOMPARE(detailOutline->height(), row(rows)->height());
        action("up"); action("accept"); QVERIFY(!root->property("settingsAdjusting").toBool()); QCOMPARE(state.brightness(), 70); // A does not adjust.
        action("right"); QVERIFY(root->property("settingsAdjusting").toBool()); QCOMPARE(state.brightness(), 75);
        action("left"); action("left", true); QCOMPARE(state.brightness(), 65);
        QTest::qWait(150); capture("settings-adjusting");
        QVERIFY(QMetaObject::invokeMethod(root, "release", Q_ARG(QVariant, QString("left"))));
        QVERIFY(!root->property("settingsAdjusting").toBool()); QVERIFY(!state.dirty());
        Preferences saved(directory.path()); QCOMPARE(saved.brightness(), 65);
        // L1/R1 change category without wrapping and return to the row each one was left on.
        action("down"); QCOMPARE(root->property("settingsIndex").toInt(), 1);
        action("nextSection"); QCOMPARE(root->property("settingsCategory").toInt(), 2); QVERIFY(!root->property("settingsSidebar").toBool());
        QCOMPARE(root->property("settingsIndex").toInt(), 0);
        action("prevSection"); QCOMPARE(root->property("settingsCategory").toInt(), 1); QCOMPARE(root->property("settingsIndex").toInt(), 1);
        action("prevSection"); action("prevSection"); QCOMPARE(root->property("settingsCategory").toInt(), 0);
        action("back"); QVERIFY(root->property("settingsSidebar").toBool());
        // Accessibility preference keeps logical navigation but skips spatial motion.
        state.adjust("motion", 1); action("right");
        QTRY_VERIFY(root->property("settingsDetailReady").toBool());
        rows = root->findChild<QQuickItem *>("settingsItems"); QVERIFY(rows);
        detailOutline = root->findChild<QQuickItem *>("settingsDetailFocus"); QVERIFY(detailOutline);
        QCOMPARE(detailOutline->x(), 0.); QCOMPARE(detailOutline->width(), row(rows)->width());
        action("quick"); QTRY_COMPARE(detailOutline->opacity(), 0.);
        action("back"); QTRY_COMPARE(detailOutline->opacity(), 1.);
        action("back");
        for (int i = 0; i < 7; ++i) action("down");
        QCOMPARE(root->property("settingsCategory").toInt(), 7);
        QVERIFY(outline->y() >= 0 && outline->y() + outline->height() <= settings->property("height").toReal());
        QTRY_VERIFY(root->findChild<QQuickItem *>("settingsItems")); QTest::qWait(1500); // Settled: the preview list's scrollbar has faded out.
        QSignalSpy idle(&view, &QQuickWindow::frameSwapped); QTest::qWait(500);
        QVERIFY2(idle.size() <= 3, qPrintable(QString("Settled settings repainted %1 times").arg(idle.size())));
    }
    void settingsCategoriesAndReasons() {
        QTemporaryDir directory;
        Preferences state(directory.path()); Telemetry metrics(directory.path()); ControllerInput controller;
        QQuickView view;
        view.setInitialProperties({{"store", QVariant::fromValue(&state)}, {"metrics", QVariant::fromValue(&metrics)}, {"controller", QVariant::fromValue(&controller)}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));
        QCOMPARE(view.status(), QQuickView::Ready); view.resize(1024, 768); view.show(); QVERIFY(QTest::qWaitForWindowExposed(&view));
        auto *root = view.rootObject(); auto *settings = root->findChild<QObject *>("settingsView"); QVERIFY(settings);
        auto action = [&](const char *name) { QVERIFY(QMetaObject::invokeMethod(root, "dispatch", Q_ARG(QVariant, QString(name)), Q_ARG(QVariant, false))); };
        auto call = [&](const char *name, const QVariant &row) { QVariant value; QMetaObject::invokeMethod(settings, name, Q_RETURN_ARG(QVariant, value), Q_ARG(QVariant, row)); return value.toString(); };
        // §8: the old categories merge into eight; every row shows a value or why it has none, never "—".
        const QList<QStringList> expected{{"wifi", "netScan"}, {"brightness", "screenOff", "night", "font", "motion"}, {"volume", "audioOutput"},
            {"tester", "input"}, {"dim", "screenOffNow", "battery", "reboot", "poweroff"},
            {"monitor", "monitorDetail", "cpuAuto", "cpuPreset", "cpuGovernor", "cpuMin", "cpuMax", "cpuCurrent", "swap", "zram", "zramAlgorithms", "zramMemory", "pressure"},
            {"storage"}, {"", "systemCpu", "memory", "temperature", "thermal", "gpuFrequency", "", "", "", "browser", "browser", "browser"}};
        QVERIFY(QMetaObject::invokeMethod(root, "showScene", Q_ARG(QVariant, QString("settings"))));
        for (int category = 0; category < 8; ++category) {
            root->setProperty("settingsCategory", category); action("right"); QTRY_VERIFY(root->property("settingsDetailReady").toBool());
            QStringList keys; const auto rows = settings->property("rows").toList();
            for (const auto &row : rows) {
                keys << row.toMap().value("key").toString();
                const auto value = call("rowValue", row), reason = call("rowReason", row);
                QVERIFY2(!value.contains(QStringLiteral("—")), qPrintable(row.toMap().value("name").toString()));
                QVERIFY2(!value.isEmpty() || !reason.isEmpty() || row.toMap().value("key") == "monitor" || call("canActivate", row.toMap().value("key")) == "true",
                         qPrintable(row.toMap().value("name").toString()));
            }
            QCOMPARE(keys, expected[category]);
            action("back");
        }
        // Preview reasons: device rows say so; frame and stream details wait for a game or stream.
        auto reasonOf = [&](const char *key) { return call("rowReason", QVariantMap{{"key", key}}); };
        QCOMPARE(reasonOf("cpuPreset"), QStringLiteral("预览中不可用"));
        // Governor and frequency limits without a reading are disabled as such.
        for (const char *key : {"cpuGovernor", "cpuMin", "cpuMax"}) QCOMPARE(reasonOf(key), QStringLiteral("暂无读数"));
        QCOMPARE(reasonOf("audioOutput"), QStringLiteral("暂不支持"));
        // 控制器: A on 摇杆测试 starts the test; the B hold returns to the row.
        root->setProperty("settingsCategory", 3); action("right"); QTRY_VERIFY(root->property("settingsDetailReady").toBool());
        action("accept"); QVERIFY(root->property("testingController").toBool());
        // Two panes: the categories stay visible beside the detail, the current one marked.
        auto *categories = root->findChild<QQuickItem *>("settingsCategories"); QVERIFY(categories && categories->isVisible());
        QCOMPARE(categories->width(), 280.);
        // 130%: category names and detail titles keep their full text.
        QVERIFY(QMetaObject::invokeMethod(root, "showScene", Q_ARG(QVariant, QString("settings"))));
        QVERIFY(state.choose("font", 3)); root->setProperty("settingsCategory", 5); action("right"); QTRY_VERIFY(root->property("settingsDetailReady").toBool());
        QTest::qWait(100);
        QList<QQuickItem *> pending{qobject_cast<QQuickItem *>(settings)};
        while (!pending.isEmpty()) {
            auto *item = pending.takeLast(); pending.append(item->childItems());
            if (!item->isVisible() || !item->inherits("QQuickText") || item->objectName() == "settingValue") continue;
            if (item->mapToItem(root, QPointF(0, item->height())).y() > 704) continue; // Scrolled below the view.
            QVERIFY2(!item->property("truncated").toBool(), qPrintable(item->property("text").toString()));
        }
    }
    void navigationGuidanceAndHudLayout() {
        QTemporaryDir directory;
        Preferences state(directory.path()); Telemetry metrics(directory.path()); ControllerInput controller;
        QQuickView view; view.setColor(QColor("#111a24"));
        view.setInitialProperties({{"store", QVariant::fromValue(&state)}, {"metrics", QVariant::fromValue(&metrics)}, {"controller", QVariant::fromValue(&controller)}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));
        QCOMPARE(view.status(), QQuickView::Ready); view.resize(1024, 768); view.show();
        QVERIFY(QTest::qWaitForWindowExposed(&view));
        auto *root = view.rootObject();
        auto action = [&](const QString &value) {
            QVERIFY(QMetaObject::invokeMethod(root, "dispatch", Q_ARG(QVariant, value), Q_ARG(QVariant, false)));
        };
        auto *footer = root->findChild<QQuickItem *>("footerHints"); QVERIFY(footer);
        auto labels = [&](QQuickItem *from = nullptr) {
            QStringList result;
            QList<QQuickItem *> pending{from ? from : footer};
            while (!pending.isEmpty()) {
                auto *item = pending.takeLast();
                if (item->objectName() == "hintLabel") result << item->property("text").toString();
                pending.append(item->childItems());
            }
            return result;
        };
        auto *hud = root->findChild<QQuickItem *>("performancePanel"); QVERIFY(hud);
        const auto captures = qEnvironmentVariable("R46H_UI_CAPTURE_DIR");
        for (int scale : {100, 130}) {
            if (scale == 130) { state.adjust("font", 1); state.adjust("font", 1); }
            for (const auto &scene : {"home", "library", "settings", "about", "power", "controller", "quick", "input"}) {
                action("home");
                QVERIFY(QMetaObject::invokeMethod(root, "showScene", Q_ARG(QVariant, QString(scene))));
                QTest::qWait(200);
                if (footer->isVisible()) QVERIFY2(footer->width() <= 952, qPrintable(QString("Footer overflow: %1 at %2%").arg(scene).arg(scale)));
                const auto small = smallText(view.contentItem(), scale / 100.);
                QVERIFY2(small.isEmpty(), qPrintable(QString("%1 at %2%: %3").arg(scene).arg(scale).arg(small.join(", "))));
                if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + QString("/%1-%2.png").arg(scene).arg(scale)));
                if (root->property("editing").toBool()) QVERIFY(QMetaObject::invokeMethod(root, "closeEditor"));
                if (root->property("quickOpen").toBool()) action("back");
            }
        }
        QVERIFY(QMetaObject::invokeMethod(root, "showScene", Q_ARG(QVariant, QStringLiteral("about"))));
        // 系统 › 关于 (rows 6–11); an unknown browser version is a disabled row with its reason, not "—".
        QCOMPARE(root->property("settingsCategory").toInt(), 7); QCOMPARE(root->property("settingsIndex").toInt(), 6);
        QCOMPARE(root->findChild<QObject *>("brandName")->property("text").toString(), QStringLiteral("Jume"));
        auto *settingsObject = root->findChild<QObject *>("settingsView");
        const auto about = settingsObject->property("rows").toList().mid(6);
        QCOMPARE(about.size(), 6);
        QCOMPARE(about[0].toMap().value("value").toString(), QStringLiteral(JUME_LAUNCHER_NAME));
        QCOMPARE(about[1].toMap().value("value").toString(), QStringLiteral(JUME_LAUNCHER_VERSION));
        QCOMPARE(about[2].toMap().value("value").toString(), QStringLiteral("https://github.com/OJZen/JumeOS"));
        QCOMPARE(about[3].toMap().value("value").toString(), QString());
        QVariant browserReason; QVERIFY(QMetaObject::invokeMethod(settingsObject, "rowReason", Q_RETURN_ARG(QVariant, browserReason), Q_ARG(QVariant, about[3])));
        QCOMPARE(browserReason.toString(), QStringLiteral("未安装"));
        root->setProperty("browserVersions", QVariantMap{{"webEngine", "6.10.2"}, {"chromium", "134.0.6998.208"}, {"securityPatch", "144.0.7559.96"}});
        const auto versions = settingsObject->property("rows").toList().mid(6);
        QCOMPARE(versions[3].toMap().value("value").toString(), QStringLiteral("6.10.2"));
        QCOMPARE(versions[4].toMap().value("value").toString(), QStringLiteral("134.0.6998.208"));
        QCOMPARE(versions[5].toMap().value("value").toString(), QStringLiteral("144.0.7559.96"));
        // §7.6: Select only on the home page, never B there; no L1/R1 or plain up/down hints.
        action("home"); QVERIFY(labels().contains("收藏")); QVERIFY(labels().contains("快捷面板"));
        QVERIFY(!labels().contains("主页")); QVERIFY(!labels().contains("返回")); QVERIFY(!labels().contains("切页"));
        action("down"); QTest::qWait(200); // The dock: open, and the quick panel.
        QVERIFY(labels().contains("打开")); QVERIFY(labels().contains("快捷面板")); QVERIFY(!labels().contains("收藏"));
        action("accept"); QTest::qWait(200);
        QCOMPARE(root->property("page").toInt(), 1); QVERIFY(labels().contains("返回")); QVERIFY(labels().contains("搜索")); QVERIFY(!labels().contains("快捷面板"));
        QCOMPARE(footer->property("context").toString(), QStringLiteral("6 项"));
        action("back"); for (int i = 0; i < 4; ++i) action("right");
        action("accept"); QTest::qWait(200); QCOMPARE(root->property("page").toInt(), 2);
        QVERIFY(!labels().contains("收藏")); QVERIFY(labels().contains("进入")); QVERIFY(!labels().contains("快捷面板"));
        state.adjust("monitor", 1); QTest::qWait(200);
        auto *outline = root->findChild<QQuickItem *>("settingsFocus"); QVERIFY(outline);
        QVERIFY(!hud->mapRectToItem(root, hud->boundingRect()).intersects(outline->mapRectToItem(root, outline->boundingRect())));
        if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + "/settings-hud-120.png"));
        action("right"); QTest::qWait(200); // 网络 in the preview: the Wi-Fi switch is disabled with its reason.
        QVERIFY(!labels().contains("打开")); QVERIFY(!labels().contains("调整"));
        action("accept"); QVERIFY(QStringList({"暂不支持", "暂不可用"}).contains(root->property("notice").toString())); // Plain reasons.
        action("left"); root->setProperty("settingsCategory", 1); action("right");
        QTRY_VERIFY(root->property("settingsDetailReady").toBool()); QTest::qWait(200);
        QVERIFY(labels().contains("调整")); QVERIFY(footer->width() <= 952); // Sliders: ←→ 调整.
        action("right"); QVERIFY(QMetaObject::invokeMethod(root, "release", Q_ARG(QVariant, QString("right"))));
        action("quick"); QTest::qWait(200);
        auto *quickPanel = root->findChild<QQuickItem *>("quickPanel"); QVERIFY(quickPanel);
        QVERIFY(!footer->isVisible()); // §7.6 item 4: the panel's own footer replaces the page's.
        QVERIFY(labels(quickPanel).contains("调整")); QVERIFY(labels(quickPanel).contains("关闭")); QVERIFY(!labels(quickPanel).contains("收藏"));
        QVERIFY(!hud->isVisible()); // The performance overlay steps aside for the quick panel.
        if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + "/quick-hud-120.png"));
        // The 夜间模式 tile toggles with a pointer as well; desktop panels leave out 回到主页 and 结束游戏.
        QVERIFY(!findItem(quickPanel, "quickAction-home")->isVisible()); QVERIFY(!findItem(quickPanel, "quickAction-end")->isVisible());
        auto *nightTile = findItem(quickPanel, "quickTile-night"); QVERIFY(nightTile);
        const auto center = nightTile->mapToItem(root, QPointF(nightTile->width() / 2, nightTile->height() / 2)).toPoint();
        QTest::mouseClick(&view, Qt::LeftButton, Qt::NoModifier, center);
        QCOMPARE(state.nightMode(), QString("on")); QCOMPARE(root->property("quickId").toString(), QString("night"));
        QTest::qWait(250);
        if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + "/quick-switches-120.png"));
        QTest::mouseClick(&view, Qt::LeftButton, Qt::NoModifier, center);
        QCOMPARE(state.nightMode(), QString("off"));
        action("back");
        action("home"); QTest::qWait(200);
        auto *pageContent = root->findChild<QQuickItem *>("pageContent"); QVERIFY(pageContent);
        auto *pageAnimation = root->findChild<QObject *>("pageRevealAnimation"); QVERIFY(pageAnimation);
        root->setProperty("dockIndex", 0); action("down"); action("accept"); QTest::qWait(40); // Dock 游戏库.
        const auto current = pageContent->property("reveal").toReal(); QVERIFY(current > 0 && current < 1);
        action("back"); QCOMPARE(root->property("page").toInt(), 0); // A route change mid-reveal retargets.
        QVERIFY(pageContent->property("reveal").toReal() >= current);
        for (int i = 0; i < 4; ++i) action("right");
        action("accept"); QCOMPARE(root->property("page").toInt(), 2); QVERIFY(root->property("settingsSidebar").toBool());
        state.adjust("motion", 1);
        QVERIFY(!pageAnimation->property("running").toBool()); QCOMPARE(pageContent->property("reveal").toReal(), 1.);
        root->setProperty("settingsCategory", 1); action("right"); QTRY_VERIFY(root->property("settingsDetailReady").toBool()); // 显示
        QPointer<QQuickItem> settingsSwitch;
        QList<QQuickItem *> controls{root};
        while (!controls.isEmpty()) {
            auto *item = controls.takeLast(); controls.append(item->childItems());
            if (item->objectName() != "settingSwitch" || !item->isVisible()) continue;
            const auto *accessible = QAccessible::queryAccessibleInterface(item);
            if (accessible && accessible->text(QAccessible::Name) == QStringLiteral("减少动态效果")) settingsSwitch = item;
        }
        QVERIFY(settingsSwitch);
        const auto settingCenter = settingsSwitch->mapToItem(root, QPointF(settingsSwitch->width() / 2, settingsSwitch->height() / 2)).toPoint();
        QTest::mouseClick(&view, Qt::LeftButton, Qt::NoModifier, settingCenter);
        QTest::qWait(150);
        QVERIFY2(settingsSwitch, "Changing a value must preserve the live control and its animation");
        QVERIFY(!state.reducedMotion()); QVERIFY(!settingsSwitch->property("checked").toBool());
        action("left"); QVERIFY(root->property("settingsSidebar").toBool()); QVERIFY(!state.dirty());
    }
    void virtualControllerEvents() {
        // §7.5: 55% of full scale engages the stick's primary axis; it releases below 35%.
        QCOMPARE(ControllerInput::stickDirection(8000, -9000), QString());
        QCOMPARE(ControllerInput::stickDirection(17000, 0), QString());
        QCOMPARE(ControllerInput::stickDirection(18100, 0), QString("right"));
        QCOMPARE(ControllerInput::stickDirection(12000, 0, "right"), QString("right"));
        QCOMPARE(ControllerInput::stickDirection(11000, 0, "right"), QString());
        QCOMPARE(ControllerInput::stickDirection(-32768, 0), QString("left"));
        QCOMPARE(ControllerInput::stickDirection(0, -32768), QString("up"));
        QCOMPARE(ControllerInput::stickDirection(0, 32767), QString("down"));
        QCOMPARE(ControllerInput::stickDirection(30000, 31000), QString("down"));
        ControllerInput input;
        const int device = SDL_JoystickAttachVirtual(SDL_JOYSTICK_TYPE_GAMECONTROLLER, SDL_CONTROLLER_AXIS_MAX, SDL_CONTROLLER_BUTTON_MAX, 0);
        QVERIFY2(device >= 0, SDL_GetError());
        SDL_Joystick *joystick = SDL_JoystickOpen(device); QVERIFY(joystick);
        QSignalSpy actions(&input, &ControllerInput::action), releases(&input, &ControllerInput::released);
        QSignalSpy scrolls(&input, &ControllerInput::scrolled);
        input.poll();
        QVERIFY(SDL_JoystickSetVirtualAxis(joystick, SDL_CONTROLLER_AXIS_LEFTX, -32768) == 0);
        input.poll(); QVERIFY(!actions.isEmpty()); QCOMPARE(actions.last().at(0).toString(), QString("left"));
        QVERIFY(!input.deviceName().isEmpty()); QCOMPARE(input.axes()[0].toDouble(), -1.);
        actions.clear(); QTest::qWait(430); QCOMPARE(actions.size(), 1); QVERIFY(actions.last().at(1).toBool()); // 380 ms, then 90 ms.
        SDL_JoystickSetVirtualAxis(joystick, SDL_CONTROLLER_AXIS_LEFTX, 0); input.poll();
        QCOMPARE(releases.last().at(0).toString(), QString("left"));
        actions.clear(); QTest::qWait(160); QVERIFY(actions.isEmpty());
        // Lists speed up to 50 ms after 2 s; grids stay at 90 ms.
        auto heldRate = [&](bool list) {
            input.setFastRepeat(list);
            SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_DPAD_DOWN, 1); input.poll();
            QTest::qWait(2100); actions.clear(); QTest::qWait(400);
            const auto count = actions.size();
            SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_DPAD_DOWN, 0); input.poll();
            return count;
        };
        const auto fast = heldRate(true), steady = heldRate(false);
        QVERIFY2(fast >= 6 && steady <= 5, qPrintable(QString("list %1, grid %2 repeats in 400 ms").arg(fast).arg(steady)));
        input.setFastRepeat(false);
        input.suppressUntilNeutral(); actions.clear();
        SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_A, 1); input.poll();
        QVERIFY(actions.isEmpty());
        SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_A, 0); input.poll();
        SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_A, 1); input.poll();
        QVERIFY(!actions.isEmpty()); QCOMPARE(actions.last().at(0).toString(), QString("accept"));
        SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_A, 0); input.poll();
        QCOMPARE(releases.last().at(0).toString(), QString("accept"));
        // §7.3 page actions, each with its release.
        for (const auto &button : {qMakePair(SDL_CONTROLLER_BUTTON_B, QString("back")), qMakePair(SDL_CONTROLLER_BUTTON_X, QString("itemAction")),
                 qMakePair(SDL_CONTROLLER_BUTTON_Y, QString("pageAction")), qMakePair(SDL_CONTROLLER_BUTTON_START, QString("options")),
                 qMakePair(SDL_CONTROLLER_BUTTON_LEFTSHOULDER, QString("prevSection")), qMakePair(SDL_CONTROLLER_BUTTON_RIGHTSHOULDER, QString("nextSection"))}) {
            actions.clear(); releases.clear(); SDL_JoystickSetVirtualButton(joystick, button.first, 1); input.poll();
            QCOMPARE(actions.size(), 1); QCOMPARE(actions.first().at(0).toString(), button.second);
            SDL_JoystickSetVirtualButton(joystick, button.first, 0); input.poll();
            QCOMPARE(releases.size(), 1); QCOMPARE(releases.first().at(0).toString(), button.second);
        }
        // Analog L2/R2 page past half travel.
        for (const auto &trigger : {qMakePair(SDL_CONTROLLER_AXIS_TRIGGERLEFT, QString("pageUp")), qMakePair(SDL_CONTROLLER_AXIS_TRIGGERRIGHT, QString("pageDown"))}) {
            actions.clear(); releases.clear(); SDL_JoystickSetVirtualAxis(joystick, trigger.first, 32767); input.poll();
            QCOMPARE(actions.size(), 1); QCOMPARE(actions.first().at(0).toString(), trigger.second);
            SDL_JoystickSetVirtualAxis(joystick, trigger.first, -32768); input.poll();
            QCOMPARE(releases.size(), 1); QCOMPARE(releases.first().at(0).toString(), trigger.second);
            SDL_JoystickSetVirtualAxis(joystick, trigger.first, 0); input.poll();
        }
        // Select decides on release; with another key it is a chord and neither reaches the page.
        actions.clear(); releases.clear();
        SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_BACK, 1); input.poll(); QVERIFY(actions.isEmpty());
        SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_BACK, 0); input.poll();
        QCOMPARE(actions.size(), 1); QCOMPARE(actions.first().at(0).toString(), QString("quick"));
        actions.clear();
        SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_BACK, 1); input.poll();
        SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_A, 1); input.poll();
        SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_A, 0); input.poll();
        SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_BACK, 0); input.poll();
        QVERIFY(actions.isEmpty()); QVERIFY(releases.isEmpty());
        // Right stick scrolls, faster the further it is pushed.
        SDL_JoystickSetVirtualAxis(joystick, SDL_CONTROLLER_AXIS_RIGHTY, 32767); input.poll();
        QVERIFY(!scrolls.isEmpty()); QVERIFY(qAbs(scrolls.last().at(0).toDouble() - 1.) < 0.01);
        SDL_JoystickSetVirtualAxis(joystick, SDL_CONTROLLER_AXIS_RIGHTY, -19661); input.poll();
        QVERIFY(qAbs(scrolls.last().at(0).toDouble() + 0.5) < 0.01);
        SDL_JoystickSetVirtualAxis(joystick, SDL_CONTROLLER_AXIS_RIGHTY, 0); scrolls.clear(); input.poll(); QVERIFY(scrolls.isEmpty());
        SDL_JoystickClose(joystick); QVERIFY(SDL_JoystickDetachVirtual(device) == 0); input.poll();
        QVERIFY(input.deviceName().isEmpty()); QVERIFY(input.buttons().isEmpty()); QCOMPARE(input.axes()[0].toDouble(), 0.);
    }
    void routedControllerEvents() {
        ControllerInput input(nullptr, true);
        QSignalSpy actions(&input, &ControllerInput::action), releases(&input, &ControllerInput::released);
        QSignalSpy cancels(&input, &ControllerInput::cancelled), scrolls(&input, &ControllerInput::scrolled);
        qint32 axes[4]{};
        input.routedState(0, axes);
        QCOMPARE(input.deviceName(), QString("R46H Routed Gamepad"));
        for (const auto &item : {qMakePair(1, QString("accept")), qMakePair(0, QString("back")), qMakePair(2, QString("itemAction")),
             qMakePair(3, QString("pageAction")), qMakePair(9, QString("options")), qMakePair(4, QString("prevSection")),
             qMakePair(5, QString("nextSection")), qMakePair(6, QString("pageUp")), qMakePair(7, QString("pageDown"))}) {
            actions.clear(); releases.clear(); input.routedState(1U << item.first, axes);
            QCOMPARE(actions.size(), 1); QCOMPARE(actions.first().at(0).toString(), item.second);
            input.routedState(0, axes);
            QCOMPARE(releases.size(), 1); QCOMPARE(releases.first().at(0).toString(), item.second);
        }
        // The router delivers a lone Select as a press and release; Select + X stays with the system layer.
        actions.clear(); input.routedState(1U << 8, axes); QVERIFY(actions.isEmpty());
        input.routedState(0, axes); QCOMPARE(actions.size(), 1); QCOMPARE(actions.first().at(0).toString(), QString("quick"));
        actions.clear(); releases.clear();
        input.routedState(1U << 8, axes); input.routedState(1U << 8 | 1U << 2, axes); input.routedState(0, axes);
        QVERIFY(actions.isEmpty()); QVERIFY(releases.isEmpty());
        // B repeats only as the keyboard's backspace; Files and Browser keep one B per press.
        actions.clear(); input.routedState(1U << 0, axes); QTest::qWait(430); QCOMPARE(actions.size(), 1);
        input.routedState(0, axes); input.setBackRepeat(true); actions.clear();
        input.routedState(1U << 0, axes); QTest::qWait(430); QVERIFY(actions.size() >= 2); QVERIFY(actions.last().at(1).toBool());
        input.routedState(0, axes); input.setBackRepeat(false);
        // Only directions and the keyboard's B repeat (§7.5): a held R2 pages once.
        actions.clear(); input.routedState(1U << 7, axes); QTest::qWait(430); QCOMPARE(actions.size(), 1);
        input.routedState(0, axes);
        actions.clear(); axes[0] = -32767; input.routedState(0, axes);
        QCOMPARE(actions.last().at(0).toString(), QString("left"));
        QCOMPARE(input.axes()[0].toDouble(), -1.);
        QTest::qWait(430); QVERIFY(actions.last().at(1).toBool());
        releases.clear(); axes[0] = -12000; input.routedState(0, axes); QVERIFY(releases.isEmpty()); // 37% keeps the direction.
        axes[0] = -11000; input.routedState(0, axes); QCOMPARE(releases.size(), 1);
        axes[0] = -32767; input.routedState(0, axes);
        input.suppressUntilNeutral(); actions.clear(); QCOMPARE(cancels.size(), 1); // A held key ends any page hold.
        input.routedState(1U << 1, axes); QTest::qWait(120); QVERIFY(actions.isEmpty());
        axes[0] = 0; input.routedState(0, axes); input.routedState(1U << 1, axes);
        QCOMPARE(actions.size(), 1); QCOMPARE(actions.first().at(0).toString(), QString("accept"));
        input.routedState(0, axes); actions.clear();
        input.routedState(1U << 6 | 1U << 7, axes);
        QCOMPARE(input.axes()[4].toDouble(), 1.); QCOMPARE(input.axes()[5].toDouble(), 1.);
        QCOMPARE(actions.size(), 2);
        input.routedState(0, axes); axes[3] = 32767; scrolls.clear(); input.routedState(0, axes);
        QCOMPARE(scrolls.size(), 1); QVERIFY(qAbs(scrolls.first().at(0).toDouble() - 1.) < 0.01);
        axes[3] = 0; input.routedState(0, axes); actions.clear(); axes[0] = 40000;
        input.routedState(1U << 1, axes); QVERIFY(actions.isEmpty()); // Reject invalid IPC values.
        QCOMPARE(input.axes()[0].toDouble(), 0.);
    }
    void virtualControllerHandover() {
        ControllerInput input;
        if (SDL_NumJoysticks() != 0) QSKIP("Requires an isolated virtual-controller session");
        const int first = SDL_JoystickAttachVirtual(SDL_JOYSTICK_TYPE_GAMECONTROLLER, SDL_CONTROLLER_AXIS_MAX, SDL_CONTROLLER_BUTTON_MAX, 0);
        QVERIFY(first >= 0); input.poll();
        const int second = SDL_JoystickAttachVirtual(SDL_JOYSTICK_TYPE_GAMECONTROLLER, SDL_CONTROLLER_AXIS_MAX, SDL_CONTROLLER_BUTTON_MAX, 0);
        QVERIFY(second >= 0);
        SDL_Joystick *backup = SDL_JoystickOpen(second); QVERIFY(backup); input.poll();
        const auto backupId = SDL_JoystickInstanceID(backup);
        QSignalSpy actions(&input, &ControllerInput::action);
        QVERIFY(SDL_JoystickDetachVirtual(first) == 0); input.poll();
        QCOMPARE(SDL_NumJoysticks(), 1); QCOMPARE(SDL_JoystickGetDeviceInstanceID(0), backupId);
        QVERIFY(!input.deviceName().isEmpty());
        QVERIFY(SDL_JoystickSetVirtualButton(backup, SDL_CONTROLLER_BUTTON_A, 1) == 0); input.poll();
        QCOMPARE(actions.size(), 1); QCOMPARE(actions.last().at(0).toString(), QString("accept"));
        SDL_JoystickClose(backup); QVERIFY(SDL_JoystickDetachVirtual(0) == 0); input.poll();
        QVERIFY(input.deviceName().isEmpty());
    }
    void telemetryAndPreferenceMigration() {
        QTemporaryDir directory;
        QFile file(directory.filePath("preview.json")); QVERIFY(file.open(QIODevice::WriteOnly));
        file.write(R"({"version":1,"volume":42,"brightness":70,"favorites":[2],"reducedMotion":false,"fontPercent":999})"); file.close();
        Preferences state(directory.path()); QVERIFY(state.error().isEmpty());
        QCOMPARE(state.volume(), 42); QVERIFY(state.isFavorite(2));
        QCOMPARE(state.fontPercent(), 100); QCOMPARE(state.dimSeconds(), 0); QCOMPARE(state.screenOffSeconds(), 300); QVERIFY(!state.monitor());
        state.adjust("font", 1); state.adjust("font", 1); state.adjust("font", 1);
        QCOMPARE(state.fontPercent(), 130);
        for (int i = 0; i < 4; ++i) state.adjust("dim", 1);
        QCOMPARE(state.dimSeconds(), 120); state.adjust("monitor", 1); QVERIFY(state.save());
        Preferences loaded(directory.path()); QCOMPARE(loaded.fontPercent(), 130); QVERIFY(loaded.monitor());
        QCOMPARE(loaded.dimSeconds(), 120); QCOMPARE(loaded.volume(), 42);
        QVERIFY(loaded.choose("screenOff", 1)); QCOMPARE(loaded.screenOffSeconds(), 60);
        // A malformed v2 field must not turn into an apparently valid default.
        QVERIFY(file.open(QIODevice::ReadOnly)); auto data = QJsonDocument::fromJson(file.readAll()).object(); file.close();
        data["dimSeconds"] = 31;
        QVERIFY(file.open(QIODevice::WriteOnly)); file.write(QJsonDocument(data).toJson()); file.close();
        Preferences invalid(directory.path()); QVERIFY(!invalid.error().isEmpty());
        invalid.adjust("font", 1); QVERIFY(!invalid.save());
        Telemetry metrics(directory.path()); QVERIFY(!metrics.active()); QVERIFY(!metrics.storage().isEmpty());
        metrics.setActive(true); QVERIFY(metrics.memoryMiB() > 0); QVERIFY(metrics.cpu() < 0);
        metrics.frameSubmitted(); metrics.frameSubmitted(); metrics.frameSubmitted();
        QTRY_VERIFY_WITH_TIMEOUT(metrics.cpu() >= 0, 1800);
        QVERIFY(metrics.submissions() > 0 && metrics.submissions() < 10); QCOMPARE(metrics.history().size(), 1);
        metrics.setActive(false); QVERIFY(metrics.history().isEmpty()); QVERIFY(metrics.cpu() < 0);
        QSignalSpy changes(&metrics, &Telemetry::changed);
        metrics.frameSubmitted(); QTest::qWait(1100); QVERIFY(changes.isEmpty());
        metrics.setActive(true); QVERIFY(metrics.history().isEmpty()); QVERIFY(metrics.submissions() < 0);
    }
    void preferenceSchemaV5() {
        QTemporaryDir directory; QVERIFY(directory.isValid());
        QFile file(directory.filePath("preview.json"));
        auto write = [&](const QJsonObject &data) {
            QVERIFY(file.open(QIODevice::WriteOnly | QIODevice::Truncate)); file.write(QJsonDocument(data).toJson()); file.close();
        };
        const QJsonObject v4{{"version", 4}, {"volume", 40}, {"brightness", 70}, {"reducedMotion", false}, {"favorites", QJsonArray{}},
            {"monitor", false}, {"fontPercent", 110}, {"dimSeconds", 0}, {"applicationFavorites", QJsonArray{"game-a"}}, {"screenOffSeconds", 300}};
        // Schema 4 sizes keep their rank in the v1 steps: 100/110/120 become 100/115/130.
        for (const auto &size : {qMakePair(100, 100), qMakePair(110, 115), qMakePair(120, 130)}) {
            auto data = v4; data["fontPercent"] = size.first; write(data);
            Preferences migrated(directory.path()); QVERIFY(migrated.error().isEmpty());
            QCOMPARE(migrated.fontPercent(), size.second); QCOMPARE(migrated.nightMode(), QString("off"));
            QVERIFY(migrated.recentApplications().isEmpty()); QVERIFY(migrated.applicationFavorites().contains("game-a"));
        }
        Preferences state(directory.path());
        QVERIFY(state.choose("night", 2)); QCOMPARE(state.nightMode(), QString("auto"));
        QVERIFY(state.recordRecent("game-a", 1000)); QVERIFY(state.recordRecent("game-b", 2000)); QVERIFY(state.recordRecent("game-a", 3000));
        QVERIFY(!state.recordRecent("../bad")); QCOMPARE(state.recentApplications().size(), 2);
        QCOMPARE(state.recentApplications().first().toMap().value("id").toString(), QString("game-a"));
        state.adjust("font", -1); QCOMPARE(state.fontPercent(), 115);
        for (int i = 0; i < 4; ++i) state.adjust("font", -1);
        QCOMPARE(state.fontPercent(), 90); QVERIFY(state.save());
        QVERIFY(file.open(QIODevice::ReadOnly)); const auto saved = QJsonDocument::fromJson(file.readAll()).object(); file.close();
        QCOMPARE(saved.value("version").toInt(), 5); QCOMPARE(saved.value("nightMode").toString(), QString("auto"));
        QCOMPARE(saved.value("fontPercent").toInt(), 90);
        QCOMPARE(saved.value("recentApplications").toArray().first().toObject().value("playedAt").toInt(), 3000);
        Preferences loaded(directory.path()); QVERIFY(loaded.error().isEmpty());
        QCOMPARE(loaded.fontPercent(), 90); QCOMPARE(loaded.nightMode(), QString("auto"));
        QCOMPARE(loaded.recentApplications(), state.recentApplications());
        QVERIFY(loaded.removeRecent("game-b")); QVERIFY(!loaded.removeRecent("game-b")); QCOMPARE(loaded.recentApplications().size(), 1);
        for (int i = 0; i < 40; ++i) QVERIFY(loaded.recordRecent(QString("game-%1").arg(i), i));
        QCOMPARE(loaded.recentApplications().size(), 32);
        QCOMPARE(loaded.recentApplications().first().toMap().value("id").toString(), QString("game-39"));
        // Invalid v5 values are refused and the original file is not overwritten.
        for (const auto &field : {qMakePair(QString("fontPercent"), QJsonValue(110)), qMakePair(QString("nightMode"), QJsonValue("dusk")),
                 qMakePair(QString("recentApplications"), QJsonValue(QJsonArray{QJsonObject{{"id", "game-a"}, {"playedAt", -1}}}))}) {
            auto data = saved; data[field.first] = field.second; write(data);
            QVERIFY(file.open(QIODevice::ReadOnly)); const auto original = file.readAll(); file.close();
            Preferences invalid(directory.path()); QVERIFY2(!invalid.error().isEmpty(), qPrintable(field.first));
            invalid.adjust("font", 1); QVERIFY(!invalid.save());
            QVERIFY(file.open(QIODevice::ReadOnly)); QCOMPARE(file.readAll(), original); file.close();
        }
    }
    void themeTokensAndNightMode() {
        QTemporaryDir directory;
        Preferences state(directory.path()); Telemetry metrics(directory.path()); ControllerInput controller;
        QQuickView view;
        view.setInitialProperties({{"store", QVariant::fromValue(&state)}, {"metrics", QVariant::fromValue(&metrics)}, {"controller", QVariant::fromValue(&controller)}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));
        QCOMPARE(view.status(), QQuickView::Ready); view.resize(1024, 768); view.show();
        QVERIFY(QTest::qWaitForWindowExposed(&view)); auto *root = view.rootObject();
        QScopedPointer<QObject> holder; auto *theme = shellTheme(view.engine(), holder); QVERIFY(theme);
        auto color = [&](const char *name) { return theme->property(name).value<QColor>(); };
        auto call = [&](const char *method, const QVariant &argument) {
            QVariant result; QMetaObject::invokeMethod(theme, method, Q_RETURN_ARG(QVariant, result), Q_ARG(QVariant, argument)); return result.toInt();
        };
        QVERIFY(!theme->property("night").toBool());
        QCOMPARE(color("ground"), QColor("#F2F4F5")); QCOMPARE(color("surface"), QColor("#FFFFFF"));
        QCOMPARE(color("focus"), QColor("#009482")); QCOMPARE(color("accent"), QColor("#00756A"));
        QCOMPARE(color("textSecondary"), QColor("#48535B")); QCOMPARE(color("danger"), QColor("#B3261E"));
        QVERIFY(qAbs(color("scrim").alphaF() - 0.48) < 0.01); QCOMPARE(view.color(), QColor("#F2F4F5"));
        QCOMPARE(call("fontSize", "display"), 36); QCOMPARE(call("lineHeight", "display"), 44); QCOMPARE(call("fontSize", "micro"), 18);
        QVERIFY(state.choose("font", 3)); QCOMPARE(call("fontSize", "title"), 39);
        QVERIFY(state.choose("font", 0)); QCOMPARE(call("fontSize", "title"), 27);
        QVERIFY(state.choose("font", 1));
        // §1 layout rules for other aspect ratios; R46H itself is 1024 wide.
        struct Layout { int width, margin, content, columns, cell; bool dual; };
        for (const auto &layout : {Layout{1024, 40, 944, 4, 212, true}, Layout{1152, 46, 1060, 4, 237, true},
                 Layout{1365, 54, 1257, 5, 225, true}, Layout{768, 40, 688, 2, 237, false}}) {
            theme->setProperty("canvasWidth", layout.width);
            QCOMPARE(theme->property("margin").toInt(), layout.margin); QCOMPARE(theme->property("contentWidth").toInt(), layout.content);
            QCOMPARE(theme->property("gridColumns").toInt(), layout.columns); QCOMPARE(theme->property("gridCellWidth").toInt(), layout.cell);
            QCOMPARE(theme->property("dualPane").toBool(), layout.dual);
        }
        theme->setProperty("canvasWidth", 1024); QCOMPARE(theme->property("contentHeight").toInt(), 632);
        // Switching palettes cross-fades a one-frame snapshot, then leaves nothing animating.
        auto *fade = root->findChild<QQuickItem *>("themeFade"); QVERIFY(fade); QVERIFY(!fade->isVisible());
        QSignalSpy fadeShown(fade, &QQuickItem::visibleChanged);
        QVERIFY(state.choose("night", 1));
        QTRY_VERIFY(theme->property("night").toBool()); QVERIFY(fade->isVisible());
        const auto captures = qEnvironmentVariable("R46H_UI_CAPTURE_DIR");
        if (!captures.isEmpty()) { QTest::qWait(60); QVERIFY(view.grabWindow().save(captures + "/theme-crossfade.png")); }
        QCOMPARE(color("ground"), QColor("#0F1316")); QCOMPARE(color("accentText"), QColor("#062A25"));
        QTRY_VERIFY_WITH_TIMEOUT(!fade->isVisible(), 1000); QCOMPARE(fadeShown.size(), 2);
        QTRY_COMPARE(view.color(), QColor("#0F1316"));
        QTest::qWait(200); QSignalSpy idle(&view, &QQuickWindow::frameSwapped); QTest::qWait(500);
        QVERIFY2(idle.size() <= 3, qPrintable(QString("Night theme repainted %1 times while idle").arg(idle.size())));
        // Reduced motion switches directly; "auto" follows the clock (19:00-07:00).
        state.adjust("motion", 1); fadeShown.clear();
        QVERIFY(state.choose("night", 0)); QVERIFY(!theme->property("night").toBool());
        QVERIFY(state.choose("night", 2));
        for (const auto &sample : {qMakePair(QTime(22, 18), true), qMakePair(QTime(16, 39), false), qMakePair(QTime(6, 59), true), qMakePair(QTime(7, 0), false), qMakePair(QTime(19, 0), true)}) {
            root->setProperty("now", QDateTime(QDate(2026, 10, 25), sample.first));
            QCOMPARE(theme->property("night").toBool(), sample.second);
        }
        QCOMPARE(fadeShown.size(), 0);
        if (QFontDatabase::families().contains(QStringLiteral("Noto Sans SC"))) {
            const auto font = root->findChild<QObject *>("brandName")->property("font").value<QFont>();
            QCOMPARE(QFontInfo(font).family(), QStringLiteral("Noto Sans SC"));
        }
    }
    void interfaceFontWeights() {
        // Packages set R46H_REQUIRE_UI_FONTS=1; host checks without the cache copy skip.
        const bool required = qEnvironmentVariable("R46H_REQUIRE_UI_FONTS") == "1";
        if (!required && !QFontDatabase::families().contains(QStringLiteral("Noto Sans SC"))) QSKIP("Noto Sans SC is not installed for this run");
        QVERIFY(QFontDatabase::families().contains(QStringLiteral("Noto Sans SC")));
        for (const auto &weight : {qMakePair(QFont::Normal, QStringLiteral("Regular")), qMakePair(QFont::Medium, QStringLiteral("Medium")), qMakePair(QFont::Bold, QStringLiteral("Bold"))}) {
            QFont font(QStringLiteral("Noto Sans SC")); font.setPixelSize(24); font.setWeight(weight.first);
            const QFontInfo info(font);
            QCOMPARE(info.family(), QStringLiteral("Noto Sans SC")); QCOMPARE(info.styleName(), weight.second);
            QVERIFY(QFontMetrics(font).inFont(QChar(0x6E38))); // 游
        }
    }
    void qmlColorsComeFromTheme() {
        // Colors are Theme tokens; the browser bundles these controls, so it is checked when present.
        const QRegularExpression literal(QStringLiteral(R"re("#[0-9A-Fa-f]{3,8}"|\bQt\.(rgba|hsla|hsva)\s*\(|"(white|black|red|green|blue|gray|grey|yellow)")re"));
        QStringList roots{QStringLiteral(SHELL_SOURCE_DIR)};
        if (QFileInfo::exists(QStringLiteral(SHELL_SOURCE_DIR "/../gaming-browser"))) roots << QStringLiteral(SHELL_SOURCE_DIR "/../gaming-browser");
        int files = 0; QStringList offenders;
        for (const auto &root : roots) {
            QDirIterator entries(root, {QStringLiteral("*.qml")}, QDir::Files, QDirIterator::Subdirectories);
            while (entries.hasNext()) {
                const auto path = entries.next();
                if (path.endsWith(QStringLiteral("/controls/Theme.qml"))) continue;
                QFile file(path); QVERIFY(file.open(QIODevice::ReadOnly)); ++files;
                const auto lines = QString::fromUtf8(file.readAll()).split(u'\n');
                for (int i = 0; i < lines.size(); ++i)
                    if (lines[i].contains(literal)) offenders << QDir(root).relativeFilePath(path) + ":" + QString::number(i + 1);
            }
        }
        QVERIFY(files >= 20);
        QVERIFY2(offenders.isEmpty(), qPrintable("Hard-coded QML colors: " + offenders.join(", ")));
    }
    void themeTokenContrast() {
        QQmlEngine engine; QScopedPointer<QObject> holder; auto *theme = shellTheme(&engine, holder); QVERIFY(theme);
        auto color = [&](const char *name) { const auto value = theme->property(name).value<QColor>(); if (!value.isValid()) qWarning("Invalid token %s", name); return value; };
        // QML reads "on" + capital as a signal handler, so such a token silently never binds.
        for (int i = 0; i < theme->metaObject()->propertyCount(); ++i)
            QVERIFY2(!QRegularExpression("^on[A-Z]").match(QString::fromLatin1(theme->metaObject()->property(i).name())).hasMatch(), theme->metaObject()->property(i).name());
        const QList<QPair<const char *, const char *>> text{{"text", "ground"}, {"text", "surface"}, {"text", "surfaceSunken"},
            {"textSecondary", "ground"}, {"textSecondary", "surface"}, {"textSecondary", "surfaceSunken"}, {"textTertiary", "ground"},
            {"textTertiary", "surface"}, {"accentText", "accent"}, {"accentInk", "accentSoft"}, {"glyphText", "glyph"},
            {"glyphSoftText", "glyphSoft"}, {"danger", "surface"}, {"warning", "surface"}, {"accent", "surface"}, {"errorToastText", "errorToast"},
            {"dangerText", "danger"}, {"cardInk", "cardText"}};
        for (const bool night : {false, true}) {
            theme->setProperty("night", night);
            // §2: text at least 4.5:1 and focus at least 3:1 against the surfaces they sit on.
            for (const auto &pair : text) QVERIFY2(contrast(color(pair.first), color(pair.second)) >= 4.5,
                qPrintable(QString("%1 on %2 (%3)").arg(pair.first, pair.second, night ? "night" : "light")));
            QVERIFY(contrast(color("focus"), color("ground")) >= 3); QVERIFY(contrast(color("focus"), color("surface")) >= 3);
            // Card titles are large bold text on fixed card colors (3:1 large-text threshold).
            for (const auto &card : theme->property("cardPalette").toList())
                QVERIFY2(contrast(color("cardText"), QColor(card.toString())) >= 3, qPrintable(card.toString()));
        }
    }
    void homeLibraryAndOptions() {
        QTemporaryDir directory;
        Preferences state(directory.filePath("state")); Telemetry metrics(directory.path()); ControllerInput controller;
        Applications applications; QVERIFY(applications.load(referenceLibrary(directory.path(), state)));
        Streaming streaming(directory.filePath("streaming")); QQuickView view;
        view.setInitialProperties({{"store", QVariant::fromValue(&state)}, {"metrics", QVariant::fromValue(&metrics)}, {"controller", QVariant::fromValue(&controller)},
            {"applications", QVariant::fromValue(&applications)}, {"streaming", QVariant::fromValue(&streaming)}, {"browserAvailable", true}, {"filesAvailable", true}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));
        QCOMPARE(view.status(), QQuickView::Ready); view.resize(1024, 768); view.show(); QVERIFY(QTest::qWaitForWindowExposed(&view));
        auto *root = view.rootObject(); root->setProperty("now", ReferenceClock);
        auto action = [&](const char *name) { QVERIFY(QMetaObject::invokeMethod(root, "dispatch", Q_ARG(QVariant, QString(name)), Q_ARG(QVariant, false))); };
        auto app = [&] { return root->property("selectedApplication").toString(); };
        auto hints = [&] {
            QStringList result; QList<QQuickItem *> pending{root->findChild<QQuickItem *>("footerHints")};
            while (!pending.isEmpty()) { auto *item = pending.takeLast(); if (item->objectName() == "hintLabel") result << item->property("text").toString(); pending.append(item->childItems()); }
            return result;
        };
        auto text = [&](const char *name) { auto *item = findItem(root, name); return item ? item->property("text").toString() : QString(); };
        // §8 home: newest recent first, then favorites; the 全部游戏 card ends the row.
        QCOMPARE(app(), QString("native.mslug")); QCOMPARE(text("homeTitle"), QString("Metal Slug"));
        QCOMPARE(text("homeCaption"), QStringLiteral("Neo Geo · 上次游玩 昨天"));
        QVERIFY(hints().contains("取消收藏")); QVERIFY(hints().contains("开始")); QVERIFY(hints().contains("快捷面板"));
        action("down"); QVERIFY(root->property("dockFocused").toBool()); QVERIFY(hints().contains("打开"));
        action("up"); QCOMPARE(app(), QString("native.mslug"));
        action("right"); QCOMPARE(app(), QString("native.gta3"));
        action("right"); action("right"); QCOMPARE(app(), QString("native.gtavc"));
        action("right"); QCOMPARE(app(), QString("native.1944")); // Topped up to five with the first available entry.
        action("right"); QCOMPARE(root->property("selected").toInt(), -1); QVERIFY(findItem(root, "homeAllCard"));
        action("right"); QCOMPARE(root->property("selected").toInt(), -1); // No wrap.
        action("accept"); QCOMPARE(root->property("page").toInt(), 1);
        // Library: filters 全部/收藏/最近/systems/应用 without wrap; each filter keeps its place.
        QCOMPARE(root->property("libraryFilters").toStringList(), QStringList({"全部", "收藏", "最近", "Neo Geo", "Ports", "应用"}));
        auto *footer = root->findChild<QQuickItem *>("footerHints");
        QCOMPARE(footer->property("context").toString(), QStringLiteral("8 项")); QVERIFY(hints().contains("搜索"));
        action("prevSection"); QCOMPARE(root->property("libraryFilter").toInt(), 0);
        action("down"); QCOMPARE(app(), QString("native.stardew")); // Four columns.
        QVERIFY(!hints().contains("开始")); QVERIFY(hints().contains("选项"));
        action("accept"); QCOMPARE(root->property("notice").toString(), QStringLiteral("尚未适配，无法启动")); QVERIFY(!applications.running());
        action("right"); QCOMPARE(root->property("selected").toInt(), 5);
        for (int i = 0; i < 6; ++i) action("nextSection");
        QCOMPARE(root->property("libraryFilter").toInt(), 5); QCOMPARE(footer->property("context").toString(), QStringLiteral("3 项"));
        for (int i = 0; i < 3; ++i) action("prevSection");
        QCOMPARE(root->property("libraryFilter").toInt(), 2); QCOMPARE(app(), QString("native.mslug")); // 最近, newest first.
        action("prevSection"); action("prevSection"); QCOMPARE(root->property("selected").toInt(), 5);
        // Y searches by title; B clears the query before leaving.
        action("pageAction"); QVERIFY(root->property("editing").toBool()); QCOMPARE(root->property("editPurpose").toString(), QString("librarySearch"));
        QVERIFY(QMetaObject::invokeMethod(root, "remoteText", Q_ARG(QVariant, QString("gta")))); action("options");
        QCOMPARE(footer->property("context").toString(), QStringLiteral("“gta” · 1 项")); QCOMPARE(app(), QString("native.gta3"));
        action("back"); QCOMPARE(root->property("page").toInt(), 1); QCOMPARE(footer->property("context").toString(), QStringLiteral("8 项"));
        // GameOptions: start, favorite (X), per-game rows disabled with a reason, removal from 最近.
        root->setProperty("selected", 0); action("options");
        auto *options = root->findChild<QObject *>("optionsMenu");
        const auto rows = options->property("items").toList();
        QStringList ids; for (const auto &row : rows) ids << row.toMap().value("id").toString();
        QCOMPARE(ids, QStringList({"start", "favorite", "controls", "saves", "forget"}));
        QCOMPARE(rows[1].toMap().value("button").toString(), QString("X"));
        QCOMPARE(rows[2].toMap().value("reason").toString(), QStringLiteral("暂不支持"));
        QCOMPARE(text("optionsSubtitle"), QStringLiteral("Neo Geo · FBNeo"));
        for (int i = 0; i < 4; ++i) action("down");
        action("accept"); QVERIFY(!options->property("open").toBool());
        QCOMPARE(state.recentApplications().first().toMap().value("id").toString(), QString("native.gta3"));
        // Launching records the entry as most recent; a paused task shows its badge and continues.
        root->setProperty("selected", 1); action("accept"); QTRY_VERIFY(applications.running());
        QCOMPARE(state.recentApplications().first().toMap().value("id").toString(), QString("native.1944"));
        applications.background(); QTRY_VERIFY(!applications.running()); action("home");
        QCOMPARE(app(), QString("native.1944")); QCOMPARE(text("homeCaption"), QStringLiteral("已暂停 · 从上次的位置继续"));
        QVERIFY(hints().contains("继续"));
        // 130%: titles and captions keep their full text.
        QVERIFY(state.choose("font", 3)); QTest::qWait(100);
        for (const auto *name : {"homeTitle", "homeCaption"}) QVERIFY2(!findItem(root, name)->property("truncated").toBool(), name);
        action("down"); action("accept"); QTest::qWait(100);
        // §8 library at every font size: two full rows (art and title) above the hint bar.
        for (const int font : {1, 2, 3}) {
            QVERIFY(state.choose("font", font)); QTest::qWait(100);
            QList<QQuickItem *> pending{root}; int titles = 0;
            while (!pending.isEmpty()) {
                auto *item = pending.takeLast(); pending.append(item->childItems());
                if (item->objectName() != "libraryTitle" || !item->isVisible()) continue;
                const auto box = item->mapRectToScene(item->boundingRect());
                if (box.top() > 704) continue;
                ++titles; QVERIFY2(box.bottom() <= 704, qPrintable(QString("%1 at font %2").arg(item->property("text").toString()).arg(font)));
                QVERIFY2(!item->property("truncated").toBool(), qPrintable(item->property("text").toString()));
            }
            QVERIFY2(titles >= 8, qPrintable(QString("%1 full titles at font %2").arg(titles).arg(font)));
        }
        applications.stopAll(); QTRY_VERIFY_WITH_TIMEOUT(!applications.hasTasks(), 4000);
    }
    void themedPagesLightAndNight() {
        QTemporaryDir directory;
        auto put = [&](const QString &name, const QByteArray &text) {
            QFile file(directory.filePath(name)); QDir().mkpath(QFileInfo(file).absolutePath());
            QVERIFY(file.open(QIODevice::WriteOnly)); QCOMPARE(file.write(text), text.size());
        };
        put("proc/net/wireless", "Inter-| sta-|   Quality        |   Discarded packets               | Missed | WE\n face | tus | link level noise |  nwid  crypt   frag  retry   misc | beacon | 22\n wlan0: 0000   55.  -55.  -256        0      0      0      0      0        0\n");
        put("sys/class/power_supply/rk817-battery/capacity", "82"); put("sys/class/power_supply/rk817-battery/status", "Discharging");
        put("sys/class/power_supply/rk817-charger/online", "0");
        // Fixture backlight at 70% with controls, so 显示 shows its slider.
        put("sys/class/backlight/backlight/brightness", "111"); put("sys/class/backlight/backlight/actual_brightness", "111");
        put("sys/class/backlight/backlight/max_brightness", "159");
        DeviceState device(directory.path(), true, true);
        Preferences state(directory.filePath("state")); Telemetry metrics(directory.path()); ControllerInput controller;
        Applications applications; QVERIFY(applications.load(referenceLibrary(directory.path(), state)));
        Streaming streaming(directory.filePath("streaming"));
        QQuickView view;
        view.setInitialProperties({{"store", QVariant::fromValue(&state)}, {"metrics", QVariant::fromValue(&metrics)}, {"controller", QVariant::fromValue(&controller)},
            {"device", QVariant::fromValue(&device)}, {"applications", QVariant::fromValue(&applications)}, {"streaming", QVariant::fromValue(&streaming)},
            {"browserAvailable", true}, {"filesAvailable", true}});
        view.engine()->addImageProvider("tasks", new TaskImages(&applications));
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));
        QCOMPARE(view.status(), QQuickView::Ready); view.resize(1024, 768); view.show(); QVERIFY(QTest::qWaitForWindowExposed(&view));
        auto *root = view.rootObject(); root->setProperty("now", ReferenceClock);
        const auto fixedClock = ReferenceClock;
        auto action = [&](const char *name) { QVERIFY(QMetaObject::invokeMethod(root, "dispatch", Q_ARG(QVariant, QString(name)), Q_ARG(QVariant, false))); };
        auto scene = [&](const char *name) { action("home"); QVERIFY(QMetaObject::invokeMethod(root, "showScene", Q_ARG(QVariant, QString(name)))); };
        const auto environment = QProcessEnvironment::systemEnvironment();
        QVERIFY(applications.launchPrepared("native.gta3", "/bin/sleep", {"60"}, directory.path(), environment));
        QTRY_VERIFY(applications.processId() > 1); applications.background();
        QTRY_VERIFY(applications.tasks().value(0).toMap().value("paused").toBool());
        const auto captures = qEnvironmentVariable("R46H_UI_CAPTURE_DIR");
        auto release = [&](const char *name) { QVERIFY(QMetaObject::invokeMethod(root, "release", Q_ARG(QVariant, QString(name)))); };
        state.adjust("motion", 1); // Captures show settled pages, not transitions.
        // Light and night at 100% and 130%: every page keeps 18 px text and its own hint footer.
        QString mode;
        auto capture = [&](const QString &name) {
            QTest::qWait(150);
            const auto small = smallText(view.contentItem(), state.fontPercent() / 100.);
            QVERIFY2(small.isEmpty(), qPrintable(name + ": " + small.join(", ")));
            if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + "/" + name + "-" + mode + ".png"));
        };
        for (const int percent : {100, 130}) {
            QVERIFY(state.choose("font", percent == 100 ? 1 : 3));
            for (const bool night : {false, true}) {
                QVERIFY(state.choose("night", night ? 1 : 0));
                mode = QString("%1-%2").arg(night ? "night" : "light").arg(percent);
                QCOMPARE(view.color(), QColor(night ? "#0F1316" : "#F2F4F5"));
                // HomeNight: 22:18, 41% and the paused GTA III focused.
                root->setProperty("now", night ? fixedClock.addSecs(5 * 3600 + 39 * 60) : fixedClock);
                put("sys/class/power_supply/rk817-battery/capacity", night ? "41" : "82"); device.refresh();
                scene("home"); QCOMPARE(root->property("selectedApplication").toString(), QString("native.mslug"));
                if (night) { action("right"); QCOMPARE(root->property("selectedApplication").toString(), QString("native.gta3")); }
                capture("home"); if (night) action("left");
                action("options"); QTest::qWait(300); capture("options"); action("back");
                QVERIFY(QMetaObject::invokeMethod(root, "notify", Q_ARG(QVariant, QStringLiteral("已加入收藏")), Q_ARG(QVariant, true))); capture("notice");
                QVERIFY(QMetaObject::invokeMethod(root, "clearNotice"));
                action("down"); capture("home-dock"); action("up");
                QVERIFY(QMetaObject::invokeMethod(root, "openPowerMenu")); QTest::qWait(250); capture("power-menu"); action("back");
                scene("library"); root->setProperty("selected", 1); QCOMPARE(root->property("selectedApplication").toString(), QString("native.1944")); capture("library");
                scene("tools"); capture("tools");
                scene("settings"); capture("settings");
                root->setProperty("settingsCategory", 1); action("right"); QTRY_VERIFY(root->property("settingsDetailReady").toBool()); capture("settings-display");
                for (const auto &[index, name] : {std::pair{2, "sound"}, {3, "controls"}, {4, "power"}, {5, "performance"}, {6, "storage"}, {7, "system"}}) {
                    action("back"); root->setProperty("settingsCategory", index); action("right");
                    QTRY_VERIFY(root->property("settingsDetailReady").toBool()); capture(QString("settings-") + name);
                }
                scene("controller"); QTRY_VERIFY(root->property("settingsDetailReady").toBool()); capture("controller");
                action("back"); QTest::qWait(HoldCaptureMs); capture("controller-hold"); release("back");
                QVERIFY(root->property("testingController").toBool());
                scene("quick"); capture("quick");
                action("back"); state.adjust("monitor", 1);
                scene("session"); capture("session-hud"); state.adjust("monitor", 1);
                scene("input"); capture("input"); QVERIFY(QMetaObject::invokeMethod(root, "closeEditor"));
                root->setProperty("dimmed", true); capture("dimmed"); root->setProperty("dimmed", false);
            }
        }
        for (const auto *id : {"builtin.files", "builtin.text"}) {
            QVERIFY(applications.launchPrepared(id, "/bin/sleep", {"30"}, directory.path(), environment));
            QTRY_VERIFY(applications.processId() > 1); applications.background();
        }
        for (const int percent : {100, 130}) {
            QVERIFY(state.choose("font", percent == 100 ? 1 : 3));
            for (const bool night : {false, true}) {
                QVERIFY(state.choose("night", night ? 1 : 0));
                mode = QString("%1-%2").arg(night ? "night" : "light").arg(percent);
                QVERIFY(QMetaObject::invokeMethod(root, "showTasksOrDesktop", Q_ARG(QVariant, true)));
                // §8 carousel at the first, middle and last task: the focused card 512×384 centered, the
                // previous one showing at the left edge and the next at the right, both 420×315 and centered.
                auto *taskView = findItem(root, "taskView"); QVERIFY(taskView);
                const auto onScreen = [&] {
                    QMap<int, QRectF> visible; QList<QQuickItem *> pending{taskView};
                    while (!pending.isEmpty()) {
                        auto *item = pending.takeLast(); pending.append(item->childItems());
                        const QRectF box(item->position(), item->size());
                        if (item->objectName() == "taskCard" && box.right() > 0 && box.left() < 1024) visible[item->property("index").toInt()] = box;
                    }
                    return visible;
                };
                for (int focus = 0; focus < 3; ++focus) {
                    taskView->setProperty("selected", focus); const auto cards = onScreen();
                    QCOMPARE(cards.value(focus), QRectF(256, 104, 512, 384));
                    QCOMPARE(cards.contains(focus - 1), focus > 0);
                    if (focus > 0) QCOMPARE(cards.value(focus - 1), QRectF(-196, 138.5, 420, 315));
                    QCOMPARE(cards.contains(focus + 1), focus < 2);
                    if (focus < 2) QCOMPARE(cards.value(focus + 1), QRectF(800, 138.5, 420, 315));
                }
                taskView->setProperty("selected", 1); capture("tasks");
                QCOMPARE(findItem(root, "topBarBadge")->isVisible(), true);
                // X held past 600 ms shows the HoldConfirm; releasing before 2 s cancels the force-quit.
                action("itemAction"); QTest::qWait(HoldCaptureMs); capture("tasks-hold"); release("itemAction");
                QCOMPARE(applications.tasks().size(), 3);
                action("back");
            }
        }
        applications.stopAll(); QTRY_VERIFY_WITH_TIMEOUT(!applications.hasTasks(), 4000);
    }
    void settingsInputMonitorAndIdle() {
        QTemporaryDir directory;
        Preferences state(directory.path()); Telemetry metrics(directory.path()); ControllerInput controller;
        QQuickView view;
        view.setInitialProperties({{"store", QVariant::fromValue(&state)}, {"metrics", QVariant::fromValue(&metrics)}, {"controller", QVariant::fromValue(&controller)}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));
        QCOMPARE(view.status(), QQuickView::Ready); view.resize(1024, 768); view.show();
        QVERIFY(QTest::qWaitForWindowExposed(&view)); auto *root = view.rootObject(); root->forceActiveFocus();
        auto action = [&](const QString &value, bool repeat = false) {
            QVERIFY(QMetaObject::invokeMethod(root, "dispatch", Q_ARG(QVariant, value), Q_ARG(QVariant, repeat)));
        };
        action("quick"); action("up"); action("accept"); // The 性能浮窗 tile.
        QVERIFY(state.monitor()); QVERIFY(metrics.active()); action("accept", true); QVERIFY(state.monitor());
        action("accept"); QVERIFY(!metrics.active()); action("back");
        action("down"); for (int i = 0; i < 4; ++i) action("right");
        action("accept");
        QVERIFY(root->property("settingsSidebar").toBool());
        // 显示 › 界面字号, then 控制器 › 文字输入测试.
        action("down"); QCOMPARE(root->property("settingsCategory").toInt(), 1);
        action("right"); QTRY_VERIFY(root->property("settingsDetailReady").toBool());
        for (int i = 0; i < 3; ++i) action("down");
        action("accept"); action("down"); action("accept"); QCOMPARE(state.fontPercent(), 115);
        action("back"); action("down"); action("down"); QCOMPARE(root->property("settingsCategory").toInt(), 3);
        action("right"); QTRY_VERIFY(root->property("settingsDetailReady").toBool());
        action("down"); action("accept"); QVERIFY(root->property("editing").toBool());
        auto *editorFocus = view.activeFocusItem(); state.adjust("monitor", 1);
        auto *hud = root->findChild<QQuickItem *>("performancePanel"); QVERIFY(hud);
        QTRY_VERIFY(hud->isVisible()); // Hidden until the first sample: no placeholder rows.
        // Desktop: top right, below the top bar, clear of the keyboard sheet's field.
        QCOMPARE(hud->x() + hud->width(), 992.); QCOMPARE(hud->y(), 80.); QVERIFY(hud->width() <= 360);
        auto *inputBox = root->findChild<QQuickItem *>("inputField"); QVERIFY(inputBox);
        QVERIFY(!hud->mapRectToScene(hud->boundingRect()).intersects(inputBox->mapRectToScene(inputBox->boundingRect())));
        QCOMPARE(view.activeFocusItem(), editorFocus); // The overlay never takes focus.
        state.adjust("monitor", 1); QVERIFY(!hud->isVisible());
        for (auto key : {Qt::Key_Q, Qt::Key_X, Qt::Key_BracketLeft, Qt::Key_BracketRight}) QTest::keyClick(&view, key);
        QTest::keyClick(&view, Qt::Key_Backspace);
        auto *field = root->findChild<QQuickItem *>("inputField"); QVERIFY(field);
        QCOMPARE(field->property("text").toString(), QString("qx["));
        QVERIFY(!root->property("quickOpen").toBool()); QVERIFY(state.favorites().isEmpty());
        QTest::keyClick(&view, Qt::Key_Escape); QVERIFY(!root->property("editing").toBool());
        QVERIFY(field->property("text").toString().isEmpty());
        action("home"); state.adjust("dim", 1);
        auto *timer = root->findChild<QObject *>("idleTimer"); QVERIFY(timer); timer->setProperty("interval", 40);
        auto *offTimer = root->findChild<QObject *>("offTimer"); QVERIFY(offTimer); offTimer->setProperty("interval", 400);
        QTRY_VERIFY_WITH_TIMEOUT(root->property("dimmed").toBool(), 1000);
        action("accept"); QVERIFY(!root->property("dimmed").toBool()); QVERIFY(!root->property("session").toBool());
        action("accept"); QVERIFY(root->property("session").toBool());
        QTest::qWait(100); QVERIFY(!root->property("dimmed").toBool());
        action("home"); state.adjust("dim", -1); QTest::qWait(100); QVERIFY(!root->property("dimmed").toBool());
        offTimer->setProperty("interval", 40);
        QTRY_VERIFY_WITH_TIMEOUT(root->property("screenOff").toBool(), 1000);
        action("accept"); QVERIFY(!root->property("screenOff").toBool()); QVERIFY(!root->property("session").toBool());
        QVERIFY(state.choose("screenOff",0));
        // Controller test (§7.4): every key but Select is test input; only a 1 s B hold leaves.
        auto release = [&](const QString &value) { QVERIFY(QMetaObject::invokeMethod(root, "release", Q_ARG(QVariant, value))); };
        QVERIFY(QMetaObject::invokeMethod(root, "showScene", Q_ARG(QVariant, QString("controller"))));
        QVERIFY(root->property("testingController").toBool());
        for (const auto *key : {"back", "nextSection", "right", "left", "options", "pageAction", "itemAction", "pageDown"}) { action(key); release(key); }
        QCOMPARE(root->property("page").toInt(), 2); QVERIFY(root->property("testingController").toBool());
        QVERIFY(!root->property("choicesOpen").toBool());
        auto *footer = root->findChild<QQuickItem *>("footerHints"); QVERIFY(footer);
        const auto exitHint = [&] {
            const auto hints = footer->property("actions").toList();
            return hints.size() == 1 ? hints.first().toMap() : QVariantMap();
        };
        QCOMPARE(exitHint().value("label").toString(), QStringLiteral("按住退出"));
        action("back"); QTest::qWait(300); QCOMPARE(exitHint().value("progress").toReal(), -1.); // No ring before 600 ms.
        QTRY_VERIFY(exitHint().value("progress").toReal() > 0.6);
        release("back"); QVERIFY(root->property("testingController").toBool()); QCOMPARE(root->property("holdAction").toString(), QString());
        action("back"); QTRY_VERIFY_WITH_TIMEOUT(!root->property("testingController").toBool(), 1500);
        release("back"); QCOMPARE(root->property("page").toInt(), 2); // Back on 控制器, at the 摇杆测试 row.
        QVERIFY(!root->property("settingsSidebar").toBool()); QCOMPARE(root->property("settingsCategory").toInt(), 3); QCOMPARE(root->property("settingsIndex").toInt(), 0);
        QVERIFY(QMetaObject::invokeMethod(root, "showScene", Q_ARG(QVariant, QString("controller"))));
        action("quick"); QVERIFY(root->property("quickOpen").toBool()); QVERIFY(root->property("testingController").toBool());
    }
    void applicationManifestAndForegroundLifecycle() {
        QTemporaryDir directory; QVERIFY(directory.isValid());
        QFile manifest(directory.filePath("applications.json"));
        auto write = [&](const QJsonArray &items, int version = 1) {
            QVERIFY(manifest.open(QIODevice::WriteOnly | QIODevice::Truncate));
            manifest.write(QJsonDocument(QJsonObject{{"version", version}, {"applications", items}}).toJson()); manifest.close();
        };
        const QJsonObject sleeper{{"id", "game-a"}, {"title", "测试应用"}, {"program", "/bin/sleep"}, {"arguments", QJsonArray{"0.1"}}};
        write({sleeper}); Applications apps; QVERIFY(!apps.hasManifest()); QVERIFY(apps.load(manifest.fileName())); QVERIFY(apps.hasManifest()); QCOMPARE(apps.items().size(), 1);
        QSignalSpy ended(&apps, &Applications::finished);
        QVERIFY(apps.launch(0)); QVERIFY(!apps.launch(0));
        QTRY_COMPARE(ended.size(), 1); QVERIFY(!apps.running()); QVERIFY(apps.error().isEmpty()); QCOMPARE(apps.exitCode(), 0);
        // Version 2 adds optional system, core and supported; version 1 still rejects them.
        QJsonObject described = sleeper; described["system"] = "Neo Geo"; described["core"] = "FBNeo";
        write({described}); QVERIFY(!apps.load(manifest.fileName()));
        write({described}, 2); QVERIFY(apps.load(manifest.fileName()));
        QCOMPARE(apps.items()[0].toMap().value("system").toString(), QString("Neo Geo"));
        QCOMPARE(apps.items()[0].toMap().value("core").toString(), QString("FBNeo"));
        QVERIFY(apps.items()[0].toMap().value("supported").toBool());
        described["supported"] = false; write({described}, 2); QVERIFY(apps.load(manifest.fileName()));
        QVERIFY(!apps.launch(0)); QVERIFY(!apps.running()); QVERIFY(apps.error().contains(QStringLiteral("尚未适配")));
        for (const auto &bad : {QJsonValue("no"), QJsonValue(1)}) { described["supported"] = bad; write({described}, 2); QVERIFY(!apps.load(manifest.fileName())); }
        described.remove("supported"); described["system"] = QString(33, 'x'); write({described}, 2); QVERIFY(!apps.load(manifest.fileName()));
        write({sleeper}, 3); QVERIFY(!apps.load(manifest.fileName()));
        write({sleeper, sleeper}); QVERIFY(!apps.load(manifest.fileName())); QCOMPARE(apps.items().size(), 1);
        QJsonObject failed{{"id", "failure"}, {"title", "失败恢复"}, {"program", "/bin/sh"}, {"arguments", QJsonArray{"-c", "exit 7"}}};
        write({failed}); QVERIFY(apps.load(manifest.fileName())); QVERIFY(apps.launch(0));
        QTRY_COMPARE(ended.size(), 2); QVERIFY(!apps.error().isEmpty()); QCOMPARE(apps.exitCode(), 7);
        failed["program"] = directory.filePath("missing"); write({failed}); QVERIFY(apps.load(manifest.fileName()));
        QVERIFY(!apps.launch(0)); QVERIFY(!apps.running()); QCOMPARE(apps.exitCode(), -1);
        QJsonObject longRun = sleeper; longRun["arguments"] = QJsonArray{"5"}; write({longRun}); QVERIFY(apps.load(manifest.fileName()));
        QVERIFY(apps.launch(0)); apps.stop(); QTRY_COMPARE_WITH_TIMEOUT(ended.size(), 3, 3000); QVERIFY(apps.error().isEmpty());
        const auto childFile = directory.filePath("child.pid");
        QJsonObject orphan{{"id", "child-cleanup"}, {"title", "子进程清理"}, {"program", "/bin/sh"},
            {"arguments", QJsonArray{"-c", "trap '' TERM; sleep 30 & echo $! > \"$1\"; exit 7", "r46h-test", childFile}}};
        write({orphan}); QVERIFY(apps.load(manifest.fileName())); QVERIFY(apps.launch(0));
        QTRY_VERIFY(QFileInfo::exists(childFile));
        QFile childRecord(childFile); QVERIFY(childRecord.open(QIODevice::ReadOnly));
        const auto child = childRecord.readAll().trimmed().toLongLong(); QVERIFY(child > 1);
        QVERIFY(apps.running()); QVERIFY(!apps.launch(0));
        QTRY_COMPARE_WITH_TIMEOUT(ended.size(), 4, 3500);
        QVERIFY(!apps.running()); QCOMPARE(apps.exitCode(), 7);
        QVERIFY(::kill(pid_t(child), 0) < 0 && errno == ESRCH);
        auto environment = QProcessEnvironment::systemEnvironment();
        environment.insert("R46H_DEVICE_CONTROLS", "1");
        QVERIFY(apps.launchPrepared("lease-isolation", "/bin/sh", {"-c", "test -z \"${R46H_DEVICE_CONTROLS+x}\""}, directory.path(), environment));
        QTRY_COMPARE(ended.size(), 5); QCOMPARE(apps.exitCode(), 0);
        Preferences state(directory.path()); state.toggleFavorite(2); QVERIFY(state.toggleApplicationFavorite("game-a"));
        QVERIFY(!state.toggleApplicationFavorite("../bad")); QVERIFY(state.save());
        Preferences loaded(directory.path()); QVERIFY(loaded.isFavorite(2)); QVERIFY(loaded.applicationFavorites().contains("game-a"));
        QVERIFY(loaded.toggleApplicationFavorite("game-a")); QVERIFY(loaded.save());
        Preferences removed(directory.path()); QVERIFY(removed.applicationFavorites().isEmpty()); QVERIFY(removed.isFavorite(2));
    }
    void backgroundTasksAndClose() {
        QTemporaryDir directory;Applications apps;
        const auto env=QProcessEnvironment::systemEnvironment();
        auto launch=[&](const QString &id){return apps.launchPrepared(id,"/bin/sleep",{"30"},directory.path(),env);};
        QVERIFY(launch("builtin.files"));QTRY_VERIFY(apps.processId()>1);const auto first=apps.processId();
        QImage image(640,480,QImage::Format_RGB32);image.fill(Qt::green);
        apps.setThumbnail("builtin.files",first+1,image);QVERIFY(apps.thumbnail("builtin.files").isNull());
        apps.setThumbnail("builtin.files",first,image);QCOMPARE(apps.thumbnail("builtin.files").size(),QSize(320,240));
        apps.background();QVERIFY(!apps.running());QVERIFY(apps.hasTasks());
        image.fill(Qt::blue);apps.setThumbnail("builtin.files",first,image);
        QCOMPARE(apps.thumbnail("builtin.files").pixelColor(0,0),QColor(Qt::blue));
        apps.setThumbnail("builtin.files",first+1,QImage());
        QCOMPARE(apps.thumbnail("builtin.files").pixelColor(0,0),QColor(Qt::blue));
        QVERIFY(launch("builtin.text"));QTRY_VERIFY(apps.processId()>1);QCOMPARE(apps.inputSlot(),1);
        apps.background();QVERIFY(apps.activate("builtin.files"));QCOMPARE(apps.processId(),first);QCOMPARE(apps.inputSlot(),0);
        QSignalSpy close(&apps,&Applications::closeRequested);apps.requestClose();QCOMPARE(close.size(),1);
        QTest::qWait(150);QCOMPARE(apps.processId(),first);QVERIFY(::kill(pid_t(first),0)==0); // No TERM escalation on cooperative close.
        QVERIFY(launch("native.gta3"));QTRY_VERIFY(apps.processId()>1);const auto game=apps.processId();apps.background();
#ifdef Q_OS_LINUX
        QFile status(QString("/proc/%1/status").arg(game));QVERIFY(status.open(QIODevice::ReadOnly));
        QTRY_VERIFY(([&]{status.seek(0);return status.readAll().contains("State:\tT");})());
#else
        Q_UNUSED(game);
#endif
        QVERIFY(apps.activate("builtin.files"));
        QVERIFY(launch("builtin.transfer"));QTRY_VERIFY(apps.processId()>1);
        QVERIFY(!launch("fifth"));QCOMPARE(apps.tasks().size(),4);
        apps.forceKill("builtin.text");QTRY_COMPARE(apps.tasks().size(),3);QCOMPARE(apps.activeId(),QString("builtin.transfer"));
        Preferences state(directory.path());Telemetry metrics(directory.path());ControllerInput controller;QQuickView view;
        view.setResizeMode(QQuickView::SizeRootObjectToView);
        view.engine()->addImageProvider("tasks",new TaskImages(&apps));
        view.setInitialProperties({{"store",QVariant::fromValue(&state)},{"metrics",QVariant::fromValue(&metrics)},
            {"controller",QVariant::fromValue(&controller)},{"applications",QVariant::fromValue(&apps)}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));QCOMPARE(view.status(),QQuickView::Ready);
        apps.background();auto *root=view.rootObject();QVERIFY(QMetaObject::invokeMethod(root,"showTasksOrDesktop",Q_ARG(QVariant,true)));
        view.resize(640,480);view.show();QVERIFY(QTest::qWaitForWindowExposed(&view));
        QVERIFY(root->property("tasksVisible").toBool());QVERIFY(root->property("sensitiveVisible").toBool());
        const auto captures=qEnvironmentVariable("R46H_UI_CAPTURE_DIR");
        if(!captures.isEmpty()){QTest::qWait(100);QVERIFY(view.grabWindow().save(captures+"/tasks.png"));}
        auto action=[&](const QString &name){QVERIFY(QMetaObject::invokeMethod(root,"dispatch",Q_ARG(QVariant,name),Q_ARG(QVariant,false)));};
        auto *tasks=root->findChild<QObject *>("taskView");QVERIFY(tasks);
        action("down");QCOMPARE(tasks->property("selected").toInt(),1);
        if(!captures.isEmpty())QVERIFY(view.grabWindow().save(captures+"/tasks-selected.png"));
        action("up");QCOMPARE(tasks->property("selected").toInt(),0);
        auto release=[&](const QString &name){QVERIFY(QMetaObject::invokeMethod(root,"release",Q_ARG(QVariant,name)));};
        auto *hold=root->findChild<QQuickItem *>("taskHold");QVERIFY(hold);
        // X held: HoldConfirm after 600 ms; releasing before 2 s cancels without closing (§7.5, §7.7).
        action("itemAction");QTest::qWait(300);QVERIFY(!hold->isVisible());
        QTRY_VERIFY(hold->isVisible());release("itemAction");QVERIFY(!hold->isVisible());
        QCOMPARE(apps.tasks().size(),3);QVERIFY(root->property("tasksVisible").toBool());
        // Start lists the task's actions; force-quit there only names the X hold.
        auto *options=root->findChild<QObject *>("optionsMenu");QVERIFY(options);
        action("options");QVERIFY(options->property("open").toBool());
        if(!captures.isEmpty()){QTest::qWait(300);QVERIFY(view.grabWindow().save(captures+"/tasks-options.png"));}
        // A notice while the menu is open sits 16 px above the sheet, clear of it.
        {
            QVERIFY(QMetaObject::invokeMethod(root,"notify",Q_ARG(QVariant,QStringLiteral("暂不支持")),Q_ARG(QVariant,false)));
            auto *toast=root->findChild<QQuickItem *>("notice");QTRY_VERIFY(toast->isVisible());
            auto *menu=qobject_cast<QQuickItem *>(options);
            QCOMPARE(toast->parentItem(),menu->parentItem()); // Canvas units, before the window's scale.
            QTRY_COMPARE(toast->y()+toast->height()+16,options->property("coverTop").toReal());
            QVERIFY(QMetaObject::invokeMethod(root,"clearNotice"));
        }
        action("back");QVERIFY(!options->property("open").toBool());QVERIFY(root->property("tasksVisible").toBool());
        // The force row carries a soft "按住 X" badge; choosing it only points at the hold.
        action("options");action("down");action("down");
        auto *force=findItem(qobject_cast<QQuickItem *>(options),"option-force");QVERIFY(force);
        auto *forceHold=findItem(force,"optionHold");QVERIFY(forceHold&&forceHold->isVisible());
        QCOMPARE(forceHold->property("text").toString(),QStringLiteral("按住"));
        action("accept");QVERIFY(!options->property("open").toBool());QCOMPARE(apps.tasks().size(),3);
        QCOMPARE(root->findChild<QObject *>("notice")->property("text").toString(),QStringLiteral("按住 X 2 秒强制结束"));
        action("itemAction");QTRY_COMPARE_WITH_TIMEOUT(apps.tasks().size(),2,3500);release("itemAction");
        QVERIFY(!apps.contains("builtin.files"));
        // A tap closes normally and leaves the task page.
        QSignalSpy closing(&apps,&Applications::closeRequested);
        action("itemAction");release("itemAction");QCOMPARE(closing.size(),1);QVERIFY(!root->property("tasksVisible").toBool());
        apps.stopAll();QTRY_VERIFY_WITH_TIMEOUT(!apps.hasTasks(),4000);QVERIFY(apps.thumbnail("builtin.files").isNull());
    }
    void browserEntryAndPrivacy() {
        QTemporaryDir directory;
        Preferences state(directory.path()); Telemetry metrics(directory.path()); ControllerInput controller;
        ToolState tools(directory.path(), directory.path(), false); Applications applications; QQuickView view;
        view.setInitialProperties({{"store", QVariant::fromValue(&state)}, {"metrics", QVariant::fromValue(&metrics)},
            {"controller", QVariant::fromValue(&controller)}, {"tools", QVariant::fromValue(&tools)}, {"applications", QVariant::fromValue(&applications)}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));
        QCOMPARE(view.status(), QQuickView::Ready);
        auto *root = view.rootObject(); QSignalSpy request(root, SIGNAL(browserRequested()));
        root->setProperty("selected", 1); // The library's apps: Moonlight, Jume Browser, 文件管理器.
        QVERIFY(QMetaObject::invokeMethod(root, "activateSelected")); QCOMPARE(request.size(), 0);
        root->setProperty("browserAvailable", true);
        QVERIFY(QMetaObject::invokeMethod(root, "activateSelected")); QCOMPARE(request.size(), 1);
        QVERIFY(!root->property("sensitiveVisible").toBool());
        QVERIFY(applications.launchPrepared("builtin.browser", "/bin/sleep", {"2"}, directory.path(), QProcessEnvironment::systemEnvironment()));
        QTRY_VERIFY(root->property("sensitiveVisible").toBool());
        applications.stop(); QTRY_VERIFY(!applications.running());
        QVERIFY(!root->property("sensitiveVisible").toBool());
    }
    void terminalEntryKeyboardMouseAndPrivacy() {
        QTemporaryDir directory;
        Preferences state(directory.path()); Telemetry metrics(directory.path()); ControllerInput controller;
        ToolState tools(directory.path(),directory.path(),false); Applications applications; QQuickView view;
        view.setInitialProperties({{"store",QVariant::fromValue(&state)},{"metrics",QVariant::fromValue(&metrics)},
            {"controller",QVariant::fromValue(&controller)},{"tools",QVariant::fromValue(&tools)},{"applications",QVariant::fromValue(&applications)}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));
        QCOMPARE(view.status(),QQuickView::Ready); view.show(); QVERIFY(QTest::qWaitForWindowExposed(&view));
        auto *root=view.rootObject(); QSignalSpy request(root,SIGNAL(terminalRequested()));
        // Keys go to the shell item itself: this check must not depend on the host granting window activation.
        auto key=[&](Qt::Key code,Qt::KeyboardModifiers modifiers=Qt::NoModifier){
            QKeyEvent press(QEvent::KeyPress,code,modifiers),release(QEvent::KeyRelease,code,modifiers);
            QCoreApplication::sendEvent(root,&press);QCoreApplication::sendEvent(root,&release);
        };
        for(const auto code:{Qt::Key_Down,Qt::Key_Right,Qt::Key_Right,Qt::Key_Right,Qt::Key_Return}) key(code); // Dock 工具.
        QCOMPARE(root->property("page").toInt(),3);
        for(int i=0;i<3;++i) key(Qt::Key_Down);
        QCOMPARE(root->property("toolsIndex").toInt(),3); key(Qt::Key_Return); QCOMPARE(request.size(),0);
        root->setProperty("terminalAvailable",true); key(Qt::Key_Return); QCOMPARE(request.size(),1);
        key(Qt::Key_Q,Qt::ControlModifier); QVERIFY(!root->property("quickOpen").toBool());
        key(Qt::Key_Q); QVERIFY(root->property("quickOpen").toBool()); key(Qt::Key_Escape); // Q is Select, decided on release.
        QQuickItem *card=nullptr; QList<QQuickItem *> pending{root};
        while(!pending.isEmpty()) {
            auto *item=pending.takeLast(); pending.append(item->childItems());
            if(item->property("title").toString()==QStringLiteral("终端"))card=item;
        }
        QVERIFY(card); QTest::qWait(150);
        QTest::mouseClick(&view,Qt::LeftButton,Qt::NoModifier,card->mapToScene(card->boundingRect().center()).toPoint());
        QCOMPARE(request.size(),2);
        QVERIFY(applications.launchPrepared("builtin.terminal","/bin/sleep",{"10"},directory.path(),QProcessEnvironment::systemEnvironment()));
        QTRY_VERIFY(root->property("sensitiveVisible").toBool());
        applications.stop(); QTRY_VERIFY(!applications.running()); QVERIFY(!root->property("sensitiveVisible").toBool());
    }
    void filesEntriesAndPrivacy() {
        QTemporaryDir directory;
        Preferences state(directory.path()); Telemetry metrics(directory.path()); ControllerInput controller;
        ToolState tools(directory.path(),directory.path(),false); Applications applications; QQuickView view;
        view.setInitialProperties({{"store",QVariant::fromValue(&state)},{"metrics",QVariant::fromValue(&metrics)},
            {"controller",QVariant::fromValue(&controller)},{"tools",QVariant::fromValue(&tools)},{"applications",QVariant::fromValue(&applications)}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));
        QCOMPARE(view.status(),QQuickView::Ready);
        auto *root=view.rootObject();QSignalSpy request(root,SIGNAL(filesRequested(bool)));
        // 文件管理器 is a library app; the editor and transfer are tools (dock 工具, rows 4 and 5).
        root->setProperty("selected",2);QVERIFY(QMetaObject::invokeMethod(root,"activateSelected"));QCOMPARE(request.size(),0);
        root->setProperty("filesAvailable",true);
        for(int i=0;i<2;++i) {
            if(i) QVERIFY(QMetaObject::invokeMethod(root,"openToolEntry",Q_ARG(QVariant,4)));
            else { root->setProperty("selected",2);QVERIFY(QMetaObject::invokeMethod(root,"activateSelected")); }
            QCOMPARE(request.size(),i+1);QCOMPARE(request.last().first().toBool(),bool(i));
            QVERIFY(applications.launchPrepared(i?"builtin.text":"builtin.files","/bin/sleep",{"10"},directory.path(),QProcessEnvironment::systemEnvironment()));
            QTRY_VERIFY(root->property("sensitiveVisible").toBool());
            root->setProperty("quickOpen",true);QVERIFY(root->property("sensitiveVisible").toBool());root->setProperty("quickOpen",false);
            applications.stop();QTRY_VERIFY(!applications.running());QVERIFY(!root->property("sensitiveVisible").toBool());
        }
        QSignalSpy transferRequest(root,SIGNAL(transferRequested()));
        QVERIFY(QMetaObject::invokeMethod(root,"openToolEntry",Q_ARG(QVariant,5)));QCOMPARE(transferRequest.size(),1);
        QVERIFY(applications.launchPrepared("builtin.transfer","/bin/sleep",{"10"},directory.path(),QProcessEnvironment::systemEnvironment()));
        QTRY_VERIFY(root->property("sensitiveVisible").toBool());applications.stop();QTRY_VERIFY(!applications.running());
        QFile manifest(directory.filePath("applications.json"));QVERIFY(manifest.open(QIODevice::WriteOnly));
        manifest.write(R"({"version":1,"applications":[{"id":"fixture","title":"Fixture","program":"/bin/true","arguments":[]}]})");manifest.close();
        QVERIFY(applications.load(manifest.fileName()));
        // Manifest properties are deliberately CONSTANT: production loads before QML.
        QQuickView custom;custom.setInitialProperties({{"store",QVariant::fromValue(&state)},{"metrics",QVariant::fromValue(&metrics)},
            {"controller",QVariant::fromValue(&controller)},{"tools",QVariant::fromValue(&tools)},{"applications",QVariant::fromValue(&applications)},{"filesAvailable",true}});
        custom.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));QCOMPARE(custom.status(),QQuickView::Ready);
        root=custom.rootObject();QSignalSpy customRequest(root,SIGNAL(filesRequested(bool)));QVERIFY(root->property("customApplications").toBool());
        root->setProperty("selected",1);QVERIFY(QMetaObject::invokeMethod(root,"activateSelected"));QCOMPARE(customRequest.size(),1);QVERIFY(!customRequest.last().first().toBool());
        QVERIFY(QMetaObject::invokeMethod(root,"openToolEntry",Q_ARG(QVariant,4)));QCOMPARE(customRequest.size(),2);QVERIFY(customRequest.last().first().toBool());
        QSignalSpy customTransfer(root,SIGNAL(transferRequested()));QVERIFY(QMetaObject::invokeMethod(root,"openToolEntry",Q_ARG(QVariant,5)));QCOMPARE(customTransfer.size(),1);
    }
    void streamingStatistics() {
        QTemporaryDir directory; Streaming stream(directory.path());
        const QByteArray report = R"(R46H_STATS {"version":1,"receivedFps":60,"decodedFps":59,"renderedFps":58.5,"networkDropPercent":0.1,"pacingDropPercent":0.2,"decodeMs":2,"queueMs":4,"renderCallMs":3,"rttMs":8,"hostProcessingMs":5,"audioNetworkQueueMs":10})" + QByteArray("\n");
        stream.ingestStatistics(report); QVERIFY(!stream.statistics().value("active").toBool());
        stream.setStatisticsActive(true); stream.ingestStatistics(report.left(17));
        QVERIFY(!stream.statistics().value("available").toBool());
        stream.ingestStatistics(report.mid(17));
        QVERIFY(stream.statistics().value("available").toBool());
        QCOMPARE(stream.statistics().value("renderedFps").toDouble(), 58.5);
        const auto previous = stream.statistics();
        auto invalid = report; invalid.replace("\"rttMs\":8", "\"rttMs\":\"private-fixture\"");
        stream.ingestStatistics(invalid); QCOMPARE(stream.statistics(), previous);
        invalid = report; invalid.replace("\"version\":1", "\"version\":1,\"address\":\"private-fixture\"");
        stream.ingestStatistics(invalid); QCOMPARE(stream.statistics(), previous);
        stream.ingestStatistics(QByteArray(9000, 'x')); stream.ingestStatistics(report);
        QCOMPARE(stream.statistics(), previous);
        QTRY_VERIFY_WITH_TIMEOUT(!stream.statistics().value("available").toBool(), 3000);
        QVERIFY(!stream.statistics().contains("renderedFps"));
        stream.ingestStatistics(report); QVERIFY(stream.statistics().value("available").toBool());
        stream.setStatisticsActive(false); QVERIFY(!stream.statistics().value("active").toBool());
        stream.ingestStatistics(report); QVERIFY(!stream.statistics().value("available").toBool());
    }
    void streamingProfilesAndWorker() {
        QTemporaryDir directory; QVERIFY(directory.isValid());
        Streaming manager(directory.path());
        QVERIFY(Streaming::validAddress("http://host/").isEmpty());
        QVERIFY(Streaming::validAddress("-host").isEmpty());
        QVERIFY(manager.addHost("127.0.0.1")); QCOMPARE(manager.hosts().size(), 1);
        QVERIFY(manager.edit("name", "客厅电脑")); QVERIFY(manager.edit("application", "Desktop"));
        manager.adjustPreset(2); manager.toggleOverlay();
        Streaming restored(directory.path()); QCOMPARE(restored.current().value("name").toString(), QString("客厅电脑"));
        QCOMPARE(restored.current().value("preset").toInt(), 2); QVERIFY(!restored.current().value("overlay").toBool());
        auto arguments = Streaming::streamArguments(QJsonObject::fromVariantMap(restored.current()));
        // The public view has a transient status field; persisted requests do not.
        QFile hosts(directory.filePath("streaming/hosts.json")); QVERIFY(hosts.open(QIODevice::ReadOnly));
        const auto host = QJsonDocument::fromJson(hosts.readAll()).object().value("hosts").toArray().first().toObject(); hosts.close();
        arguments = Streaming::streamArguments(host);
        QVERIFY(arguments.contains("1024x768")); QVERIFY(arguments.contains("8000")); QVERIFY(!arguments.contains("--performance-overlay"));
        auto malformed = host; malformed["address"] = " 127.0.0.1 "; QVERIFY(Streaming::streamArguments(malformed).isEmpty());
        QFile fake(directory.filePath("client")); QVERIFY(fake.open(QIODevice::WriteOnly));
        fake.write("#!/bin/sh\nif [ \"$1\" = pair ]; then exit 0; fi\nprintf 'FPS 60\\nExecuting request: http://fixture/?rikey=fixture-secret\\n'\nexit 0\n"); fake.close();
        QVERIFY(fake.setPermissions(QFile::ReadOwner | QFile::WriteOwner | QFile::ExeOwner));
        QVERIFY(fake.open(QIODevice::ReadOnly)); const auto hash = QCryptographicHash::hash(fake.readAll(), QCryptographicHash::Sha256).toHex(); fake.close();
        restored.configureClient(fake.fileName(), QString::fromLatin1(hash)); restored.pair();
        QCOMPARE(restored.pin().size(), 4); QTRY_VERIFY(!restored.busy()); QVERIFY(restored.pin().isEmpty());
        QVERIFY(restored.current().value("paired").toBool());
        QSignalSpy requested(&restored, &Streaming::launchRequested); QVERIFY(restored.requestStream()); QCOMPARE(requested.size(), 1);
        QCOMPARE(restored.runPending(2), 0); QVERIFY(!QFile::exists(directory.filePath("streaming/request.json")));
        QFile log(directory.filePath("streaming/stream.log")); QVERIFY(log.open(QIODevice::ReadOnly)); const auto text = log.readAll();
        QVERIFY(text.contains("FPS 60")); QVERIFY(!text.contains("fixture-secret"));
        restored.streamFinished(7); QVERIFY(restored.status().contains(QStringLiteral("未正常结束")));
        restored.streamFinished(0); QCOMPARE(restored.status(), QStringLiteral("串流已结束"));
        Streaming afterStop(directory.path()); QCOMPARE(afterStop.status(), QStringLiteral("串流已结束"));
        // Refuse a replaced state path and retain the visible host on failed deletion.
        const auto original = hosts.fileName() + ".original";
        QVERIFY(hosts.rename(original)); QVERIFY(QFile::link(original, directory.filePath("streaming/hosts.json")));
        QVERIFY(!restored.removeSelected()); QCOMPARE(restored.hosts().size(), 1);
        Streaming unsafe(directory.path()); QVERIFY(!unsafe.error().isEmpty()); QVERIFY(!unsafe.addHost("example.test"));
        QVERIFY(QFile::remove(directory.filePath("streaming/hosts.json"))); QVERIFY(QFile::rename(original, directory.filePath("streaming/hosts.json")));
        QVERIFY(restored.removeSelected()); QVERIFY(restored.hosts().isEmpty());
    }
    void streamingNavigation() {
        QTemporaryDir directory; Preferences state(directory.path()); Telemetry metrics(directory.path());
        ControllerInput controller; Streaming manager(directory.path());
        QQuickView view; view.setColor(QColor("#111a24"));
        view.setInitialProperties({{"store", QVariant::fromValue(&state)}, {"metrics", QVariant::fromValue(&metrics)},
            {"controller", QVariant::fromValue(&controller)}, {"streaming", QVariant::fromValue(&manager)}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml"))); QCOMPARE(view.status(), QQuickView::Ready);
        view.resize(1024, 768); view.show(); QVERIFY(QTest::qWaitForWindowExposed(&view));
        auto *root = view.rootObject();
        auto action = [&](const char *name) { QVERIFY(QMetaObject::invokeMethod(root, "dispatch", Q_ARG(QVariant, QString(name)), Q_ARG(QVariant, false))); };
        action("accept"); QVERIFY(root->property("streamingOpen").toBool());
        action("accept"); QVERIFY(root->property("editing").toBool()); QVERIFY(root->property("sensitiveVisible").toBool());
        auto *field = root->findChild<QQuickItem *>("inputField"); QVERIFY(field);
        field->setProperty("text", "127.0.0.1"); QVERIFY(QMetaObject::invokeMethod(root, "finishEditor"));
        QVERIFY(!root->property("editing").toBool()); QCOMPARE(manager.hosts().size(), 1);
        QVERIFY(state.choose("font", 3));
        action("accept"); // Enter details at Start, then move to the overlay switch.
        root->setProperty("quickIndex", 3); root->setProperty("quickOpen", true);
        action("down"); QCOMPARE(root->property("quickId").toString(), QString("volume"));
        action("back"); QVERIFY(!root->property("quickOpen").toBool()); QVERIFY(root->property("streamingOpen").toBool());
        const auto captures = qEnvironmentVariable("R46H_UI_CAPTURE_DIR");
        QTest::qWait(200);
        if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + "/streaming-130.png"));
        action("up"); action("up"); action("accept"); QVERIFY(!manager.current().value("overlay").toBool());
        action("up"); action("accept"); QVERIFY(root->property("choicesOpen").toBool());
        QTest::qWait(200);
        if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + "/streaming-choices-130.png"));
        action("down"); QCOMPARE(manager.current().value("preset").toInt(), 0);
        action("accept"); QCOMPARE(manager.current().value("preset").toInt(), 1);
        action("up"); action("accept"); QVERIFY(root->property("choicesOpen").toBool());
        action("down"); action("accept"); QVERIFY(root->property("editing").toBool()); // Manual fallback remains available.
        field->setProperty("text", "Desktop"); QVERIFY(QMetaObject::invokeMethod(root, "finishEditor"));
        QCOMPARE(manager.current().value("application").toString(), QString("Desktop"));
        action("left"); action("back"); QVERIFY(!root->property("streamingOpen").toBool());
        QFile pairingClient(directory.filePath("pair-client")); QVERIFY(pairingClient.open(QIODevice::WriteOnly));
        pairingClient.write("#!/bin/sh\nexec sleep 1\n"); pairingClient.close();
        QVERIFY(pairingClient.setPermissions(QFile::ReadOwner|QFile::WriteOwner|QFile::ExeOwner));
        QVERIFY(pairingClient.open(QIODevice::ReadOnly));
        const auto hash=QCryptographicHash::hash(pairingClient.readAll(),QCryptographicHash::Sha256).toHex(); pairingClient.close();
        manager.configureClient(pairingClient.fileName(),QString::fromLatin1(hash));
        root->setProperty("testInputCapture",true); QVERIFY(QMetaObject::invokeMethod(root,"openEditor"));
        QVERIFY(root->property("testInputVisible").toBool()); QVERIFY(!root->property("sensitiveVisible").toBool());
        manager.pair(); QVERIFY(root->property("sensitiveVisible").toBool());
        manager.cancelPair(); QTRY_VERIFY(!manager.busy());
        QVERIFY(!root->property("sensitiveVisible").toBool()); QVERIFY(QMetaObject::invokeMethod(root,"closeEditor"));
    }
    void streamingApplicationListAndFallback() {
        QStringList names;
        QVERIFY(Streaming::parseApplications("Desktop\nGame; literal\n",&names)); QCOMPARE(names.size(),2);
        for(const auto &bad:{QByteArray("Duplicate\nDuplicate\n"),QByteArray("bad\rname\n"),QByteArray(129,'a'),QByteArray("\xff")})
            QVERIFY(!Streaming::parseApplications(bad,&names));
        QCOMPARE(names.size(),2); // Malformed data does not replace the previous result.
        QTemporaryDir directory; Preferences state(directory.path()); Telemetry metrics(directory.path()); ControllerInput controller;
        QFile client(directory.filePath("list-client")); QVERIFY(client.open(QIODevice::WriteOnly));
        client.write("#!/bin/sh\n[ \"$1\" = list ] && [ \"$2\" = 127.0.0.1 ] || exit 7\n[ ! -f \"$0.slow\" ] || exec sleep 5\nprintf 'Desktop\\nGame; literal\\n'\nprintf 'private-fixture-stderr\\n' >&2\n");client.close();
        QVERIFY(client.setPermissions(QFile::ReadOwner|QFile::WriteOwner|QFile::ExeOwner));
        QVERIFY(client.open(QIODevice::ReadOnly));const auto hash=QCryptographicHash::hash(client.readAll(),QCryptographicHash::Sha256).toHex();client.close();
        Streaming manager(directory.path());QVERIFY(manager.addHost("127.0.0.1"));manager.configureClient(client.fileName(),QString::fromLatin1(hash));
        QSignalSpy ready(&manager,&Streaming::applicationsReady);manager.refreshApplications();
        QTRY_COMPARE(ready.size(),1);QVERIFY(!manager.busy());QCOMPARE(manager.applications(),names);
        QVERIFY(manager.chooseApplication(1));QCOMPARE(manager.current().value("application").toString(),names[1]);QVERIFY(!manager.chooseApplication(2));
        QQuickView view;view.setInitialProperties({{"store",QVariant::fromValue(&state)},{"metrics",QVariant::fromValue(&metrics)},
            {"controller",QVariant::fromValue(&controller)},{"streaming",QVariant::fromValue(&manager)}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));QCOMPARE(view.status(),QQuickView::Ready);
        view.resize(1024,768);view.show();QVERIFY(QTest::qWaitForWindowExposed(&view));auto *root=view.rootObject();
        auto tap=[&](const char *key){QVERIFY(QMetaObject::invokeMethod(root,"dispatch",Q_ARG(QVariant,QString(key)),Q_ARG(QVariant,false)));};
        tap("accept");tap("accept");for(int i=0;i<4;++i)tap("up");tap("accept");QVERIFY(root->property("choicesOpen").toBool());
        const auto captures=qEnvironmentVariable("R46H_UI_CAPTURE_DIR");QTest::qWait(200);
        auto *popup=root->findChild<QObject *>("streamingChoices");QVERIFY(popup);
        auto *content=qobject_cast<QQuickItem *>(popup->property("contentItem").value<QObject *>());QVERIFY(content);
        auto *list=content->findChild<QQuickItem *>("choiceList");QVERIFY(list);
        QCOMPARE(list->property("currentIndex").toInt(),1);
        auto *outline=content->findChild<QQuickItem *>("choiceFocus");QVERIFY(outline);
        auto *choiceRow=qobject_cast<QQuickItem *>(list->property("currentItem").value<QObject *>());QVERIFY(choiceRow);
        QTRY_COMPARE(outline->mapToScene(QPointF()).y(), choiceRow->mapToScene(QPointF()).y());
        QCOMPARE(outline->height(), choiceRow->height());
        if(!captures.isEmpty())QVERIFY(view.grabWindow().save(captures+"/streaming-applications.png"));
        tap("up");tap("accept");QCOMPARE(manager.current().value("application").toString(),QString("Desktop"));
        tap("accept");for(int i=0;i<3;++i)tap("down");tap("accept");QVERIFY(root->property("editing").toBool());tap("quick"); // Select cancels input.
        QFile slow(client.fileName()+".slow");QVERIFY(slow.open(QIODevice::WriteOnly));slow.close();
        manager.refreshApplications();QVERIFY(manager.busy());const auto oldAddress=manager.current().value("address");
        QVERIFY(!manager.edit("address","127.0.0.2"));QCOMPARE(manager.current().value("address"),oldAddress);
        tap("back");QTRY_VERIFY(!manager.busy());QCOMPARE(manager.applications(),names);
        QVERIFY(manager.edit("address","127.0.0.2"));QVERIFY(manager.applications().isEmpty());
        manager.refreshApplications();QTRY_VERIFY(!manager.busy());QVERIFY(!manager.error().isEmpty());QVERIFY(manager.applications().isEmpty());
    }
    void standardControlsAndChoices() {
        QStandardItemModel table(2000, 3);
        for (int row = 0; row < table.rowCount(); ++row)
            for (int column = 0; column < table.columnCount(); ++column)
                table.setData(table.index(row, column), QString("%1 · %2").arg(row + 1).arg(column + 1));
        QQuickView gallery;
        gallery.setInitialProperties({{"tableModel", QVariant::fromValue(&table)}});
        gallery.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/tests/ControlsGallery.qml")));
        QCOMPARE(gallery.status(), QQuickView::Ready); gallery.resize(1024, 768); gallery.show();
        QVERIFY(QTest::qWaitForWindowExposed(&gallery));
        auto *sample = gallery.rootObject();
        auto *toggle = sample->findChild<QQuickItem *>("gallerySwitch"); QVERIFY(toggle);
        QTest::mouseClick(&gallery, Qt::LeftButton, Qt::NoModifier, QPoint(80, 184));
        QCOMPARE(sample->property("presses").toInt(), 1);
        QTest::mouseClick(&gallery, Qt::LeftButton, Qt::NoModifier, QPoint(200, 184));
        QCOMPARE(sample->property("presses").toInt(), 1); // Disabled native button cannot activate.
        QTest::mouseClick(&gallery, Qt::LeftButton, Qt::NoModifier, QPoint(330, 188));
        QVERIFY(toggle->property("checked").toBool());
        QTest::keyClick(&gallery, Qt::Key_Space); QVERIFY(!toggle->property("checked").toBool());
        auto *field = sample->findChild<QQuickItem *>("galleryField"); QVERIFY(field);
        field->forceActiveFocus();
        for (auto key : {Qt::Key_T, Qt::Key_E, Qt::Key_S, Qt::Key_T}) QTest::keyClick(&gallery, key);
        QCOMPARE(field->property("text").toString(), QString("test"));
        auto *button = sample->findChild<QQuickItem *>("galleryButton"); QVERIFY(button); button->forceActiveFocus();
        const auto captures = qEnvironmentVariable("R46H_UI_CAPTURE_DIR");
        for (const bool night : {false, true}) {
            sample->setProperty("night", night);
            for (int percent : {100, 130}) {
                sample->setProperty("fontScale", percent / 100.);
                for (const auto *page : {"controls", "foundations", "buttons", "rows", "cards"}) {
                    sample->setProperty("page", QString::fromLatin1(page)); QTest::qWait(200);
                    const auto small = smallText(gallery.contentItem(), percent / 100.);
                    QVERIFY2(small.isEmpty(), qPrintable(QString("%1 at %2%: %3").arg(QLatin1String(page)).arg(percent).arg(small.join(", "))));
                    if (!captures.isEmpty()) QVERIFY(gallery.grabWindow().save(captures + QString("/%1-%2-%3.png")
                        .arg(QLatin1String(page), night ? "night" : "light").arg(percent)));
                }
            }
        }
        // Showcase pages: blocks stay apart and inside the margins; no text is cut or overlaps another.
        const QList<QPair<const char *, QStringList>> pages{{"foundations", {"foundationColors", "foundationShapes", "foundationRamp"}},
            {"buttons", {"componentButtons"}}, {"rows", {"componentRows"}}, {"cards", {"componentCards"}}};
        for (const auto &page : pages) {
            sample->setProperty("page", QString::fromLatin1(page.first));
            for (const qreal scale : {1.0, 1.3}) {
                sample->setProperty("fontScale", scale); QTest::qWait(100);
                const auto where = QString("%1 at %2%").arg(QLatin1String(page.first)).arg(scale * 100);
                QList<QRectF> blocks; QList<QQuickItem *> pending;
                for (const auto &name : page.second) {
                    auto *block = sample->findChild<QQuickItem *>(name); QVERIFY(block); pending << block;
                    const auto rect = block->mapRectToScene(QRectF(0, 0, block->width(), block->height()));
                    QVERIFY2(rect.left() >= 40 && rect.right() <= 1024 - 40 && rect.bottom() <= 768, qPrintable(QString("%1 outside the page at %2,%3 %4×%5: %6").arg(name).arg(rect.x()).arg(rect.y()).arg(rect.width()).arg(rect.height()).arg(where)));
                    for (const auto &other : blocks) QVERIFY2(!rect.intersects(other), qPrintable(name + " overlaps: " + where));
                    blocks << rect;
                }
                QList<QRectF> texts;
                while (!pending.isEmpty()) {
                    auto *item = pending.takeLast(); pending.append(item->childItems());
                    if (!item->isVisible() || !item->inherits("QQuickText") || item->property("text").toString().isEmpty()) continue;
                    const auto text = item->property("text").toString();
                    QVERIFY2(!item->property("truncated").toBool(), qPrintable(text + " truncated: " + where));
                    QVERIFY2(item->width() + 0.5 >= item->implicitWidth() || item->property("wrapMode").toInt() != 0, qPrintable(text + " clipped: " + where));
                    const auto rect = item->mapRectToScene(QRectF(0, 0, qMin(item->width(), item->implicitWidth()), item->height())).adjusted(0.5, 0.5, -0.5, -0.5);
                    QVERIFY2(rect.right() <= 1024 && rect.bottom() <= 768, qPrintable(text + " leaves the page: " + where));
                    for (const auto &other : texts) QVERIFY2(!rect.intersects(other), qPrintable(text + " overlaps text: " + where));
                    texts << rect;
                }
            }
        }
        sample->setProperty("night", false); sample->setProperty("fontScale", 1.); sample->setProperty("page", "controls"); QTest::qWait(100);
        QVERIFY(QMetaObject::invokeMethod(sample, "visitLast")); QTest::qWait(200);
        int cells = 0, rows = 0;
        QList<QQuickItem *> pending{sample};
        while (!pending.isEmpty()) {
            auto *item = pending.takeLast(); pending.append(item->childItems());
            if (item->objectName() == "tableCell") ++cells;
            if (item->objectName() == "galleryListRow") ++rows;
        }
        qInfo("VIRTUALIZED_VIEWS rows=2000 attached_cells=%d attached_list_rows=%d", cells, rows);
        QVERIFY(cells > 0 && cells < 100);
        QVERIFY(rows > 0 && rows < 30); // Inspect visual ownership, not QObject creation context.
        QSignalSpy idle(&gallery, &QQuickWindow::frameSwapped); QTest::qWait(500);
        QVERIFY2(idle.size() <= 3, "Settled standard controls must not repaint continuously");

        QTemporaryDir directory;
        Preferences state(directory.path()); Telemetry metrics(directory.path()); ControllerInput controller;
        QQuickView view; view.setColor(QColor("#111a24"));
        view.setInitialProperties({{"store", QVariant::fromValue(&state)}, {"metrics", QVariant::fromValue(&metrics)}, {"controller", QVariant::fromValue(&controller)}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));
        QCOMPARE(view.status(), QQuickView::Ready); view.resize(1024, 768); view.show();
        QVERIFY(QTest::qWaitForWindowExposed(&view)); auto *root = view.rootObject();
        auto action = [&](const char *value) { QVERIFY(QMetaObject::invokeMethod(root, "dispatch", Q_ARG(QVariant, QString(value)), Q_ARG(QVariant, false))); };
        QVERIFY(QMetaObject::invokeMethod(root, "showScene", Q_ARG(QVariant, QString("power"))));
        QTRY_VERIFY(root->property("settingsDetailReady").toBool());
        action("accept"); QVERIFY(root->property("choicesOpen").toBool());
        action("down"); action("nextSection"); action("pageDown"); action("home");
        QCOMPARE(root->property("page").toInt(), 2); QCOMPARE(state.dimSeconds(), 0);
        action("back"); QVERIFY(!root->property("choicesOpen").toBool()); QCOMPARE(state.dimSeconds(), 0);
        action("accept"); action("down"); action("accept"); QCOMPARE(state.dimSeconds(), 30);
        QVERIFY(!root->property("choicesOpen").toBool());
        // Failure keeps the choice and dirty value; canceling cannot discard the failed save.
        QVERIFY(QDir().mkdir(directory.filePath("preview-block")));
        QVERIFY(QFile::rename(directory.filePath("preview.json"), directory.filePath("saved.json")));
        QVERIFY(QDir().rename(directory.filePath("preview-block"), directory.filePath("preview.json")));
        action("accept"); action("down"); action("accept");
        QVERIFY(root->property("choicesOpen").toBool()); QVERIFY(state.dirty()); QCOMPARE(state.dimSeconds(), 60);
        action("back"); action("left"); QVERIFY(!root->property("settingsSidebar").toBool());
        QVERIFY(QDir().rmdir(directory.filePath("preview.json")));
        action("left"); QVERIFY(root->property("settingsSidebar").toBool());
        Preferences saved(directory.path()); QCOMPARE(saved.dimSeconds(), 60);
        QVERIFY(!state.choose("font", 4)); QVERIFY(!state.choose("night", 3)); QVERIFY(!state.choose("unknown", 0));
        action("right"); QTRY_VERIFY(root->property("settingsDetailReady").toBool()); action("accept"); QTest::qWait(200);
        if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + "/settings-choices.png"));
        action("back");
    }
    void sharedComponentStates() {
        QQuickView view; view.resize(1024, 768);
        QQmlComponent fixture(view.engine());
        fixture.setData(R"(import QtQuick
            import "controls" as Ui
            Item {
                width: 1024; height: 768
                property alias danger: danger
                property alias frame: frame
                property alias hints: hints
                property alias hold: hold
                property alias hud: hud
                Ui.Button { id: danger; x: 40; y: 40; text: "结束游戏"; variant: "danger" }
                Ui.Button { id: disabled; objectName: "disabledButton"; x: 300; y: 40; text: "不可用"; enabled: false }
                Rectangle { id: target; objectName: "target"; x: 40; y: 140; width: 400; height: 72; radius: Ui.Theme.radiusRow }
                Ui.FocusFrame { id: frame; x: target.x; y: target.y; width: target.width; height: target.height }
                Ui.HintBar { id: hints; x: 40; y: 680; width: 944
                    actions: [{button: "A", label: "开始"}, {button: "Start", label: "选项"}, {button: "dpadH", label: "调整"}, {button: "B", label: "返回"}, {button: "X", label: "收藏"}, {button: "Y", label: "搜索"}] }
                Ui.HoldConfirm { id: hold; anchors.centerIn: parent }
                Ui.Hud { id: hud; anchors.horizontalCenter: parent.horizontalCenter; y: 24 }
                Text { x: 600; y: 300; text: "太小"; font.pixelSize: 16 }
                Ui.GlyphBadge { x: 700; y: 300; button: "A"; size: Ui.Theme.glyphKeySize }
                Ui.GameCard { objectName: "favoriteCard"; x: 760; y: 300; width: 212; height: 212; title: "1944"; favorite: true }
                Ui.HintBar { objectName: "badHints"; x: 40; y: 620; width: 400; actions: [{button: "Home", label: "主页"}, {button: "A", label: "开始"}] }
            })", QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ComponentFixture.qml")));
        QTest::ignoreMessage(QtWarningMsg, QRegularExpression(QStringLiteral("HintBar: unknown button \"Home\"")));
        QScopedPointer<QObject> object(fixture.create()); QVERIFY2(object, qPrintable(fixture.errorString()));
        auto *root = qobject_cast<QQuickItem *>(object.data()); root->setParentItem(view.contentItem());
        view.show(); QVERIFY(QTest::qWaitForWindowExposed(&view));
        QScopedPointer<QObject> holder; auto *theme = shellTheme(view.engine(), holder); QVERIFY(theme);
        auto color = [&](const char *name) { return theme->property(name).value<QColor>(); };
        // Danger buttons are quiet until focused, then solid; disabled text uses the disabled token.
        auto *danger = root->property("danger").value<QQuickItem *>(); QVERIFY(danger);
        QCOMPARE(danger->property("fill").value<QColor>(), color("surfaceSunken")); QCOMPARE(danger->property("ink").value<QColor>(), color("danger"));
        danger->setProperty("selected", true);
        QCOMPARE(danger->property("fill").value<QColor>(), QColor("#B3261E")); QCOMPARE(danger->property("ink").value<QColor>(), QColor("#FFFFFF"));
        QCOMPARE(danger->height(), 56.);
        QCOMPARE(root->findChild<QObject *>("disabledButton")->property("ink").value<QColor>(), color("disabledText"));
        // Focus ring: 4 px stroke outside a 4 px gap, radius = element radius + 7; adjusting turns it warning.
        auto *frame = root->property("frame").value<QQuickItem *>(); auto *ring = frame->findChild<QQuickItem *>("focusRing"); QVERIFY(ring);
        const auto target = root->findChild<QQuickItem *>("target")->mapRectToScene(QRectF(0, 0, 400, 72));
        QCOMPARE(ring->mapRectToScene(ring->boundingRect()), target.adjusted(-8, -8, 8, 8));
        QCOMPARE(ring->property("radius").toReal(), 16. + 7.); QCOMPARE(ring->property("border").value<QObject *>()->property("width").toInt(), 4);
        frame->setProperty("adjusting", true);
        QCOMPARE(ring->property("border").value<QObject *>()->property("color").value<QColor>(), color("warning"));
        // The ring settles once after a move, then nothing animates.
        auto *settle = frame->findChild<QObject *>("focusSettle"); QVERIFY(settle);
        frame->setProperty("y", 260.); QTRY_VERIFY(settle->property("running").toBool()); QTRY_VERIFY(!settle->property("running").toBool());
        QCOMPARE(frame->property("settle").toReal(), 1.);
        QTest::qWait(100); QSignalSpy idle(&view, &QQuickWindow::frameSwapped); QTest::qWait(500);
        QVERIFY2(idle.size() <= 3, qPrintable(QString("Settled components repainted %1 times").arg(idle.size())));
        // Hint bar: five actions at most; directions lead, then Start Y X B A towards the right edge.
        auto *hints = root->property("hints").value<QQuickItem *>(); QVERIFY(!hints->property("overflow").toBool());
        QMap<qreal, QString> order; QList<QQuickItem *> pending{hints};
        while (!pending.isEmpty()) {
            auto *item = pending.takeLast(); pending.append(item->childItems());
            if (item->objectName() == "hintLabel" && item->isVisible()) order.insert(item->mapToScene(QPointF()).x(), item->property("text").toString());
        }
        QCOMPARE(QStringList(order.values()), QStringList({"调整", "选项", "收藏", "返回", "开始"}));
        QCOMPARE(root->findChild<QObject *>("badHints")->property("entries").toList().size(), 1); // Unknown buttons are not drawn.
        // The text-size guard flags raw 16 px text but not the 16 px letter inside a key glyph.
        QCOMPARE(smallText(root, 1.), QStringList({QStringLiteral("16 px \"太小\"")}));
        // Favorites are a solid star in cardFavorite on the card's dark disc.
        auto *star = root->findChild<QQuickItem *>("favoriteCard")->findChild<QQuickItem *>("cardFavorite"); QVERIFY(star && star->isVisible());
        auto *starIcon = star->childItems().value(0); QVERIFY(starIcon);
        QVERIFY(starIcon->property("filled").toBool()); QCOMPARE(starIcon->property("color").value<QColor>(), color("cardFavorite"));
        // Hold confirmation appears only after 600 ms of a 2 s hold and leaves on release.
        auto *hold = root->property("hold").value<QQuickItem *>();
        hold->setProperty("progress", 0.25); QVERIFY(!hold->isVisible());
        hold->setProperty("progress", 0.31); QVERIFY(hold->isVisible());
        QCOMPARE(hold->findChild<QObject *>("holdSeconds")->property("text").toString(), QStringLiteral("1.4"));
        hold->setProperty("progress", 0.); QVERIFY(!hold->isVisible());
        // HUD fades in on show and out on hide without taking focus.
        auto *hud = root->property("hud").value<QQuickItem *>(); QVERIFY(!hud->isVisible());
        hud->setProperty("shown", true); QVERIFY(hud->isVisible()); QTRY_COMPARE(hud->opacity(), 1.);
        QCOMPARE(hud->size(), QSizeF(280, 56)); QVERIFY(!hud->hasActiveFocus());
        hud->setProperty("shown", false); QVERIFY(hud->isVisible()); QTRY_VERIFY(!hud->isVisible());
        // Toasts: notices leave after toastDwell, errors stay until the failure is resolved.
        QTemporaryDir directory; const auto blocked = directory.filePath("blocked");
        QFile file(blocked); QVERIFY(file.open(QIODevice::WriteOnly)); file.close();
        Preferences state(blocked); Telemetry metrics(directory.path()); ControllerInput controller; QQuickView shell;
        shell.setInitialProperties({{"store", QVariant::fromValue(&state)}, {"metrics", QVariant::fromValue(&metrics)}, {"controller", QVariant::fromValue(&controller)}});
        shell.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml"))); QCOMPARE(shell.status(), QQuickView::Ready);
        auto *shellRoot = shell.rootObject(); auto *toast = shellRoot->findChild<QQuickItem *>("notice"); QVERIFY(toast);
        // Only a success carries the check mark; information has no icon and no trailing period.
        QVERIFY(QMetaObject::invokeMethod(shellRoot, "notify", Q_ARG(QVariant, QStringLiteral("暂不支持。")), Q_ARG(QVariant, false)));
        QCOMPARE(shellRoot->property("notice").toString(), QStringLiteral("暂不支持")); QVERIFY(!toast->property("marked").toBool());
        QVERIFY(QMetaObject::invokeMethod(shellRoot, "notify", Q_ARG(QVariant, QStringLiteral("已加入收藏")), Q_ARG(QVariant, true))); QVERIFY(toast->isVisible());
        QVERIFY(toast->property("marked").toBool());
        QVERIFY(!toast->property("error").toBool()); QTest::qWait(2200); QVERIFY(toast->isVisible());
        QTRY_VERIFY_WITH_TIMEOUT(!toast->isVisible(), 600);
        state.adjust("volume", 5); QVERIFY(!state.save());
        QTRY_VERIFY(toast->isVisible()); QVERIFY(toast->property("error").toBool()); QTest::qWait(2600); QVERIFY(toast->isVisible());
        QVERIFY(file.remove()); QVERIFY(state.save()); QTRY_VERIFY(!toast->isVisible());
    }
    void nativeRowActivationUsesItsOwnTarget() {
        QTemporaryDir directory;
        Preferences state(directory.path()); Telemetry metrics(directory.path()); ControllerInput controller;
        Streaming manager(directory.path()); QQuickView view;
        view.setInitialProperties({{"store", QVariant::fromValue(&state)}, {"metrics", QVariant::fromValue(&metrics)},
            {"controller", QVariant::fromValue(&controller)}, {"streaming", QVariant::fromValue(&manager)}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));
        QCOMPARE(view.status(), QQuickView::Ready); view.resize(1024,768); view.show();
        QVERIFY(QTest::qWaitForWindowExposed(&view)); auto *root=view.rootObject(); root->forceActiveFocus();
        auto tap=[&](const char *a){QVERIFY(QMetaObject::invokeMethod(root,"dispatch",Q_ARG(QVariant,QString(a)),Q_ARG(QVariant,false)));};
        auto row=[&](const QString &title) -> QQuickItem * {
            QList<QQuickItem *> pending{root};
            while(!pending.isEmpty()) {
                auto *item=pending.takeLast(); pending.append(item->childItems());
                if(item->isVisible() && item->property("title").toString()==title)return item;
            }
            return nullptr;
        };
        QVERIFY(manager.addHost("127.0.0.1")); tap("accept"); tap("accept"); tap("down"); // logical row = Remove
        QTest::qWait(100);
        auto *pair=row(QStringLiteral("配对")); QVERIFY(pair);
        auto *accessible=QAccessible::queryAccessibleInterface(pair); QVERIFY(accessible && accessible->actionInterface());
        accessible->actionInterface()->doAction(QAccessibleActionInterface::pressAction());
        QCOMPARE(manager.hosts().size(),1); QVERIFY(!manager.error().isEmpty()); // Pair fails without a configured client, not removal.
        auto *name=row(QStringLiteral("主机名称")); QVERIFY(name);
        QVERIFY(QMetaObject::invokeMethod(name,"click"));
        QVERIFY(root->property("editing").toBool()); QCOMPARE(root->property("editPurpose").toString(),QString("name"));
        QVERIFY(QMetaObject::invokeMethod(root,"closeEditor"));
        tap("left");tap("back");
        QVERIFY(QMetaObject::invokeMethod(root,"showScene",Q_ARG(QVariant,QString("settings"))));
        tap("down"); tap("right"); QTRY_VERIFY(root->property("settingsDetailReady").toBool()); tap("down"); // 显示 › 自动息屏
        auto *brightness=row(QStringLiteral("亮度")); QVERIFY(brightness);
        QVERIFY(QMetaObject::invokeMethod(brightness,"click"));
        QCOMPARE(root->property("settingsIndex").toInt(),0); QVERIFY(!root->property("settingsAdjusting").toBool()); // Clicking focuses the slider row.
        const auto before=state.brightness(); tap("right"); QVERIFY(root->property("settingsAdjusting").toBool()); QCOMPARE(state.brightness(),before+5);
    }
    void choiceKeyboardFocusStaysModal() {
        QTemporaryDir directory;
        Preferences state(directory.path()); Telemetry metrics(directory.path()); ControllerInput controller;
        Streaming manager(directory.path()); QQuickView view;
        view.setResizeMode(QQuickView::SizeRootObjectToView);
        view.setInitialProperties({{"store", QVariant::fromValue(&state)}, {"metrics", QVariant::fromValue(&metrics)},
            {"controller", QVariant::fromValue(&controller)}, {"streaming", QVariant::fromValue(&manager)}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));
        QCOMPARE(view.status(), QQuickView::Ready); view.resize(1024,768); view.show();
        QVERIFY(QTest::qWaitForWindowExposed(&view)); auto *root=view.rootObject(); root->forceActiveFocus();
        auto tap=[&](const char *a){QVERIFY(QMetaObject::invokeMethod(root,"dispatch",Q_ARG(QVariant,QString(a)),Q_ARG(QVariant,false)));};
        QVERIFY(manager.addHost("127.0.0.1"));tap("accept");tap("accept");tap("up");tap("up");tap("up");
        const int windows=QGuiApplication::topLevelWindows().size();
        tap("accept"); QVERIFY(root->property("choicesOpen").toBool()); QTest::qWait(200);
        QTest::keyClick(&view,Qt::Key_Tab); QTest::keyClick(&view,Qt::Key_Space);
        QVERIFY2(!root->property("editing").toBool(),"Tab/Space must not activate background Add Host");
        QTRY_VERIFY(!root->property("choicesOpen").toBool());
        QCOMPARE(manager.current().value("preset").toInt(),1);
        QTRY_VERIFY(root->hasActiveFocus());
        tap("accept");QTest::qWait(200);
        auto *popup=root->findChild<QObject *>("streamingChoices"); QVERIFY(popup);
        auto *content=qobject_cast<QQuickItem *>(popup->property("contentItem").value<QObject *>()); QVERIFY(content);
        for(const QSize size : {QSize(768,576),QSize(1280,720)}) {
            view.resize(size);QTest::qWait(200);
            const auto rect=content->mapRectToScene(content->boundingRect());
            const auto scale=qMin(size.width()/1024.,size.height()/768.);
            QVERIFY(qAbs(rect.width()-550*scale)<1);
            QVERIFY(rect.left()>=0 && rect.top()>=0 && rect.right()<=size.width()+1 && rect.bottom()<=size.height()+1);
        }
        view.resize(1024,768);QTest::qWait(200);
        for(int i=0;i<8;++i)QTest::keyClick(&view,Qt::Key_Tab);
        QTest::keyClick(&view,Qt::Key_BracketRight); QVERIFY(root->property("choicesOpen").toBool());
        QCOMPARE(QGuiApplication::topLevelWindows().size(),windows); // Popup must remain in the EGLFS-compatible window.
        QTest::keyClick(&view,Qt::Key_Escape);QTRY_VERIFY(!root->property("choicesOpen").toBool());
        QCOMPARE(manager.current().value("preset").toInt(),1);
        tap("accept");QTest::qWait(200);
        QTest::mouseClick(&view,Qt::LeftButton,Qt::NoModifier,QPoint(90,600)); // Add Host is outside the popup.
        QTRY_VERIFY(!root->property("choicesOpen").toBool()); QVERIFY(!root->property("editing").toBool());
        // Failed confirmation retains modal ownership and the selected value for retry.
        QVERIFY(QFile::rename(directory.filePath("streaming/hosts.json"),directory.filePath("streaming/saved.json")));
        QVERIFY(QDir().mkdir(directory.filePath("streaming/hosts.json")));
        tap("accept");QTest::qWait(200);QTest::keyClick(&view,Qt::Key_Down);QTest::keyClick(&view,Qt::Key_Return);
        QVERIFY(root->property("choicesOpen").toBool()); QVERIFY(!manager.error().isEmpty());
        QTest::keyClick(&view,Qt::Key_Backtab);QVERIFY(!root->property("editing").toBool());
        QVERIFY(QDir().rmdir(directory.filePath("streaming/hosts.json")));
        QTest::keyClick(&view,Qt::Key_Return);QTRY_VERIFY(!root->property("choicesOpen").toBool());
        QCOMPARE(manager.current().value("preset").toInt(),1);QVERIFY(manager.error().isEmpty());
        QTRY_VERIFY(root->hasActiveFocus());
    }
    void progressAnimationFollowsWindowVisibility() {
        QQuickView view;
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/controls/ProgressBar.qml")));
        QCOMPARE(view.status(),QQuickView::Ready);view.resize(200,40);
        auto *progress=view.rootObject();progress->setProperty("indeterminate",true);
        QSignalSpy changes(progress,SIGNAL(phaseChanged()));
        view.show();QTRY_VERIFY(changes.size()>0);
        view.hide();QTest::qWait(50);changes.clear();QTest::qWait(150);QCOMPARE(changes.size(),0);
        view.showNormal();QTRY_VERIFY(changes.size()>0);
        view.showMinimized();QTest::qWait(50);changes.clear();QTest::qWait(150);QCOMPARE(changes.size(),0);
        view.showNormal();QTRY_VERIFY(changes.size()>0);
        progress->setVisible(false);QTest::qWait(50);changes.clear();QTest::qWait(100);QCOMPARE(changes.size(),0);
    }
    void volumeHudAndAtomicUpdates() {
        QTemporaryDir directory; QVERIFY(directory.isValid());
        const auto stateDir=directory.filePath("var/lib/r46h-volume"), level=stateDir+"/level";
        QVERIFY(QDir().mkpath(stateDir));
        auto save=[&](const QByteArray &value) {
            QSaveFile file(level); QVERIFY(file.open(QIODevice::WriteOnly));
            QCOMPARE(file.write(value),value.size()); QVERIFY(file.commit());
        };
        save("169\n");
        DeviceState device(directory.path(),false,true); QSignalSpy changes(&device,&DeviceState::volumeChanged);
        DeviceState untrusted(directory.path()); QSignalSpy ignored(&untrusted,&DeviceState::volumeChanged);
        Preferences state(directory.path()); Telemetry metrics(directory.path()); ControllerInput controller;
        QQuickView view; view.setResizeMode(QQuickView::SizeRootObjectToView);
        view.setInitialProperties({{"store",QVariant::fromValue(&state)},{"metrics",QVariant::fromValue(&metrics)},
            {"controller",QVariant::fromValue(&controller)},{"device",QVariant::fromValue(&device)}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));
        QCOMPARE(view.status(),QQuickView::Ready); view.resize(640,480); view.show();
        QVERIFY(QTest::qWaitForWindowExposed(&view)); auto *root=view.rootObject();
        QSignalSpy visibility(root,SIGNAL(volumeVisibleChanged()));
        auto *hud=root->findChild<QQuickItem *>("volumeHud"); QVERIFY(hud);
        QVERIFY(!hud->isVisible()); QVERIFY(changes.isEmpty());
        QVERIFY(QMetaObject::invokeMethod(root,"openEditor"));
        auto *focus=view.activeFocusItem(); QVERIFY(focus);
        save("201\n"); QTRY_VERIFY(!changes.isEmpty());
        QCOMPARE(changes.last().at(0).toInt(),100); QCOMPARE(device.info().value("volumeSaved").toInt(),100);
        QVERIFY(hud->isVisible()); QCOMPARE(view.activeFocusItem(),focus); QVERIFY(!root->property("quickOpen").toBool());
        const auto bounds=hud->mapRectToScene(hud->boundingRect());
        QCOMPARE(bounds.center().x(),320.); QCOMPARE(bounds.top(),15.); QCOMPARE(bounds.size(),QSizeF(280*0.625,56*0.625));
        const auto captures=qEnvironmentVariable("R46H_UI_CAPTURE_DIR");
        QVERIFY(QMetaObject::invokeMethod(root,"closeEditor"));
        for(int scale:{100,130}) {
            if(scale==130){state.adjust("font",1);state.adjust("font",1);}
            save("201\n"); QTest::qWait(100);
            auto *label=hud->findChild<QQuickItem *>("hudLabel"); QVERIFY(label);
            QVERIFY(label->property("contentWidth").toReal()<=label->width());
            QVERIFY(!label->property("truncated").toBool());
            state.adjust("monitor",1); QTest::qWait(100);
            auto *performance=root->findChild<QQuickItem *>("performancePanel"); QVERIFY(performance);
            QTRY_VERIFY(performance->isVisible()); // Shown once the first sample exists.
            QVERIFY(!hud->mapRectToScene(hud->boundingRect()).intersects(performance->mapRectToScene(performance->boundingRect())));
            if(!captures.isEmpty())QVERIFY(view.grabWindow().save(captures+QString("/volume-%1.png").arg(scale)));
            state.adjust("monitor",1);
        }
        // Waiting for the overlay sample may outlast the dwell; count toggles from a fresh show.
        QTRY_VERIFY_WITH_TIMEOUT(!hud->isVisible(),2500); visibility.clear(); save("201\n"); QTRY_VERIFY(hud->isVisible());
        QTest::qWait(1000); changes.clear(); save("201\n"); // Repeat at the limit must renew the timeout.
        QTRY_VERIFY(!changes.isEmpty()); QTest::qWait(1000); QVERIFY(hud->isVisible());
        QCOMPARE(visibility.size(),1); // Timer renewal must not toggle compositor visibility.
        QTRY_VERIFY_WITH_TIMEOUT(!hud->isVisible(),1500);
        changes.clear(); save("0\n"); QTRY_VERIFY(!changes.isEmpty());
        QCOMPARE(changes.last().at(0).toInt(),0); QCOMPARE(root->property("volumePercent").toInt(),0);
        QTest::qWait(50); changes.clear(); save("202\n"); QTest::qWait(100); QVERIFY(changes.isEmpty());
        save("invalid\n"); QTest::qWait(100); QVERIFY(changes.isEmpty());
        QVERIFY(QFile::remove(level)); QTest::qWait(100); QVERIFY(changes.isEmpty());
        save("85\n"); QTRY_VERIFY(!changes.isEmpty()); QCOMPARE(changes.last().at(0).toInt(),42);
        // Service temporary files are not volume events, and unverified hosts never watch.
        QTest::qWait(100); changes.clear();
        QFile temporary(stateDir+"/.level.temporary"); QVERIFY(temporary.open(QIODevice::WriteOnly)); temporary.close();
        QTest::qWait(100); QVERIFY(changes.isEmpty()); QVERIFY(ignored.isEmpty());
        QTRY_VERIFY_WITH_TIMEOUT(!hud->isVisible(),2200);
    }
    void performanceOverlayInGameRegion() {
        // §5: in game the compositor shows the shell only inside x 624–992, y 16–276, widened to
        // x 396 while the volume Hud is up (gaming-wayland/handheld-shell.cpp). Both must fit.
        QTemporaryDir directory;
        Preferences state(directory.path()); ControllerInput controller;
        QQuickView view;
        QQmlComponent fixtures(view.engine());
        // A game reporting frames, so the overlay's first row and its 详细 row have data.
        fixtures.setData(R"(import QtQuick
QtObject {
    readonly property QtObject telemetry: QtObject {
        property bool active: false; property real cpu: 30; property real submissions: 12; property real memoryMiB: 180
        property var game: ({active: true, submissions: 60, intervalMedianMs: 16.7, intervalP95Ms: 18.2})
        property var stream: ({}); property var history: []; property string system: "fixture"; property string storage: ""
        function refreshStorage() {}
    }
    readonly property QtObject game: QtObject {
        property bool running: true; property bool hasManifest: false; property var items: []
        property var tasks: [{id: "native.gta3", title: "GTA III", icon: "gamepad", foreground: true, paused: false, stopping: false, preview: ""}]
        property string activeId: "native.gta3"; property string error: ""; property int exitCode: 0
        signal changed()
        function stop() {}
    }
    readonly property QtObject device: QtObject {
        property bool target: true; property bool controls: true; property string error: ""
        property var info: ({cpu: {scaling_cur_freq: 1296000}, systemCpu: 45, gpuFrequencyHz: 480000000,
            socTemperatureC: 55, MemTotal: 1048576, MemAvailable: 786432, capacity: 82, brightnessPercent: 70})
        signal volumeChanged(int percent)
        function setPowerScene(scene) { return true }
        function setDimmed(value) { return true }
        function setScreenOff(value) { return true }
        function setBrightness(value) { info = Object.assign({}, info, {brightnessPercent: value}); return true }
    }
})", QUrl());
        std::unique_ptr<QObject> fixture(fixtures.create()); QVERIFY2(fixture, qPrintable(fixtures.errorString()));
        auto *game = fixture->property("game").value<QObject *>(), *device = fixture->property("device").value<QObject *>();
        auto *telemetry = fixture->property("telemetry").value<QObject *>();
        view.setInitialProperties({{"store", QVariant::fromValue(&state)}, {"metrics", QVariant::fromValue(telemetry)},
            {"controller", QVariant::fromValue(&controller)}, {"applications", QVariant::fromValue(game)},
            {"device", QVariant::fromValue(device)}, {"sharedDisplay", true}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));
        QCOMPARE(view.status(), QQuickView::Ready); view.resize(1024, 768); view.show();
        QVERIFY(QTest::qWaitForWindowExposed(&view));
        auto *root = view.rootObject(); QVERIFY(root->property("gameOverlay").toBool());
        auto *panel = root->findChild<QQuickItem *>("performancePanel"); QVERIFY(panel);
        auto *hud = root->findChild<QQuickItem *>("volumeHud"); QVERIFY(hud);
        const QRectF region(624, 16, 368, 260), volumeRegion(396, 16, 596, 260);
        const auto captures = qEnvironmentVariable("R46H_UI_CAPTURE_DIR");
        state.adjust("monitor", 1);
        for (int font : {1, 3}) {
            QVERIFY(state.choose("font", font)); QTRY_VERIFY(panel->isVisible());
            root->setProperty("volumePercent", 40); root->setProperty("volumeVisible", true); QTest::qWait(250);
            const auto box = panel->mapRectToScene(panel->boundingRect()), volume = hud->mapRectToScene(hud->boundingRect());
            const auto where = QString("%1% panel %2,%3 %4x%5").arg(font == 3 ? 130 : 100).arg(box.x()).arg(box.y()).arg(box.width()).arg(box.height());
            QVERIFY2(region.contains(box), qPrintable(where));
            QCOMPARE(box.right(), 992.); QCOMPARE(box.top(), 24.); QVERIFY(box.width() <= 360); QVERIFY2(box.height() <= 252, qPrintable(where));
            QVERIFY2(volumeRegion.contains(volume) && !volume.intersects(box), qPrintable(where));
            auto *load = panel->findChild<QQuickItem *>("performanceLoad"); QVERIFY(load);
            // At 130% the CPU row wraps only between "·" items: four rows, nothing cut.
            QCOMPARE(load->property("lineCount").toInt(), font == 3 ? 2 : 1); QVERIFY(!load->property("truncated").toBool());
            const auto row = [&](const char *name) { return findItem(panel, name)->property("text").toString().replace(QChar(0xa0), ' '); };
            QCOMPARE(row("performanceRate"), QStringLiteral("60 FPS · 16.7 ms")); // The game's frame rate leads.
            if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + QString("/overlay-game-%1.png").arg(font == 3 ? 130 : 100)));
            // 详细 adds the game's P95 as a fourth reading and still fits the region at 130%.
            QVERIFY(state.choose("monitorDetail", 1)); QTest::qWait(100);
            const auto detailed = panel->mapRectToScene(panel->boundingRect());
            QCOMPARE(row("performanceDetail"), QStringLiteral("P95 18.2 ms"));
            QVERIFY2(region.contains(detailed) && detailed.height() <= 252, qPrintable(QString("detail %1").arg(detailed.height())));
            if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + QString("/overlay-game-detail-%1.png").arg(font == 3 ? 130 : 100)));
            QVERIFY(state.choose("monitorDetail", 0));
            root->setProperty("volumeVisible", false);
        }
        // §8 quick panel over a game: the app and its state, tiles, brightness (volume stays with the
        // device keys and never takes focus), 回到主页, 任务切换 and 结束游戏.
        state.adjust("monitor", 1);
        auto action = [&](const char *name) { QVERIFY(QMetaObject::invokeMethod(root, "dispatch", Q_ARG(QVariant, QString(name)), Q_ARG(QVariant, false))); };
        action("quick"); QVERIFY(root->property("quickOpen").toBool()); QCOMPARE(root->property("quickId").toString(), QString("brightness"));
        QCOMPARE(findItem(root, "quickTitle")->property("text").toString(), QString("GTA III"));
        action("down"); QCOMPARE(root->property("quickId").toString(), QString("home")); // The device volume row is read-only.
        action("up"); action("up"); QCOMPARE(root->property("quickId").toString(), QString("monitor"));
        action("right"); action("right"); QCOMPARE(root->property("quickId").toString(), QString("night"));
        action("down"); action("right"); QCOMPARE(root->property("quickId").toString(), QString("brightness"));
        QCOMPARE(device->property("info").toMap().value("brightnessPercent").toInt(), 75);
        for (int i = 0; i < 4; ++i) action("down");
        QCOMPARE(root->property("quickId").toString(), QString("end"));
        action("accept"); QVERIFY(root->property("choicesOpen").toBool()); action("back"); // 结束游戏 asks first; 取消 is the default.
        for (const int percent : {100, 130}) {
            QVERIFY(state.choose("font", percent == 100 ? 1 : 3));
            for (const bool night : {false, true}) {
                QVERIFY(state.choose("night", night ? 1 : 0)); root->setProperty("quickIndex", 1); QTest::qWait(300);
                const auto small = smallText(view.contentItem(), percent / 100.); QVERIFY2(small.isEmpty(), qPrintable(small.join(", ")));
                if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + QString("/quick-game-%1-%2.png").arg(night ? "night" : "light").arg(percent)));
            }
            // Key combinations show on every action row or on none, never wrapped; all fit at 100%.
            auto keysShown = [&](const char *id) { return findItem(findItem(root, id), "quickActionKeys")->isVisible(); };
            QCOMPARE(keysShown("quickAction-home"), keysShown("quickAction-tasks"));
            if (percent == 100) QVERIFY(keysShown("quickAction-home"));
        }
        action("back"); QVERIFY(!root->property("quickOpen").toBool());
        // On the desktop the overlay drops below the top bar and the Hud returns to the center.
        root->setProperty("sharedDisplay", false);
        QCOMPARE(panel->y(), 80.); QCOMPARE(panel->x() + panel->width(), 992.);
        view.setSource(QUrl()); // Release the shell before its fixtures go.
    }
    void deviceSettingsReadbackAndGuards() {
        QTemporaryDir directory;
        auto put=[&](const QString &name,const QByteArray &text){QFile file(directory.filePath(name));QDir().mkpath(QFileInfo(file).absolutePath());QVERIFY(file.open(QIODevice::WriteOnly));QCOMPARE(file.write(text),text.size());};
        auto get=[&](const QString &name){QFile file(directory.filePath(name));if(!file.open(QIODevice::ReadOnly))return QByteArray();return file.readAll().trimmed();};
        const QString cpu="sys/devices/system/cpu/cpufreq/policy0/";
        put(cpu+"scaling_governor","schedutil");put(cpu+"scaling_available_governors","schedutil performance ondemand");
        put(cpu+"scaling_available_frequencies","600000 816000 1008000 1200000 1296000");
        for(const auto &name:{"scaling_min_freq","cpuinfo_min_freq"})put(cpu+name,"600000");
        for(const auto &name:{"scaling_max_freq","cpuinfo_max_freq","scaling_cur_freq"})put(cpu+name,"1296000");
        put("proc/meminfo","MemTotal: 1048576 kB\nMemAvailable: 786432 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\n");
        put("proc/stat","cpu 100 0 50 800 50 0 0 0 0 0\n");
        put("proc/net/wireless","Inter-| sta-|   Quality        |   Discarded packets               | Missed | WE\n face | tus | link level noise |  nwid  crypt   frag  retry   misc | beacon | 22\n wlan0: 0000   55.  -55.  -256        0      0      0      0      0        0\n");
        put("sys/class/backlight/backlight/brightness","80");put("sys/class/backlight/backlight/actual_brightness","80");put("sys/class/backlight/backlight/max_brightness","159");
        put("sys/class/power_supply/rk817-battery/voltage_avg","3800000");put("sys/class/power_supply/rk817-battery/voltage_min_design","3300000");
        put("sys/class/power_supply/rk817-battery/status","Charging");put("sys/class/power_supply/rk817-battery/capacity","86");put("sys/class/power_supply/rk817-charger/online","1");
        put("sys/class/thermal/thermal_zone0/temp","55000");put("sys/class/thermal/thermal_zone0/trip_point_0_type","critical");put("sys/class/thermal/thermal_zone0/trip_point_0_temp","95000");
        put("sys/class/thermal/thermal_zone0/type","soc-thermal");
        put("sys/class/thermal/cooling_device0/type","cpufreq-cpu0");put("sys/class/thermal/cooling_device0/cur_state","0");
        put("sys/class/thermal/cooling_device1/type","devfreq-ff400000.gpu");put("sys/class/thermal/cooling_device1/cur_state","0");
        put("sys/class/devfreq/ff400000.gpu/cur_freq","480000000");
        DeviceState untrusted(directory.path(),true);QVERIFY(!untrusted.target());QVERIFY(!untrusted.setBrightness(70));
        QCOMPARE(untrusted.diagnostics(),QVariantMap({{"target",false},{"controls",false}}));QVERIFY(untrusted.storage().isEmpty());
        DeviceState device(directory.path(),true,true);QVERIFY(device.target());QVERIFY(device.controls());
        QCOMPARE(device.info().value("MemAvailable").toInt(),786432);
        QCOMPARE(device.info().value("capacity").toInt(),86);QCOMPARE(device.info().value("wifiSignal").toInt(),79);
        put("proc/stat","cpu 120 0 60 865 55 0 0 0 0 0\n");device.refresh();QCOMPARE(device.info().value("systemCpu").toDouble(),30.);
        const auto diagnostic=device.diagnostics();QCOMPARE(diagnostic.value("systemCpu").toDouble(),30.);
        QVERIFY(diagnostic.value("sampleAgeMs").toInt()>=0);QVERIFY(!diagnostic.contains("batteryStatus"));QVERIFY(!diagnostic.contains("cpu"));
        QStorageInfo localStorage(directory.path());QVERIFY(localStorage.isValid());
        const auto volume=DeviceState::storageInfo("fixture",localStorage,localStorage.rootPath());QVERIFY(volume.value("available").toBool());
        QCOMPARE(volume.value("totalBytes").toLongLong(),localStorage.bytesTotal());QVERIFY(!volume.contains("device"));QVERIFY(!volume.contains("rootPath"));
        const auto absent=DeviceState::storageInfo("fixture",localStorage,directory.path()+"/not-mounted");QVERIFY(!absent.value("available").toBool());QCOMPARE(absent.value("availableBytes").toLongLong(),-1);
        QVERIFY(device.setBrightness(100));QCOMPARE(get("sys/class/backlight/backlight/brightness"),QByteArray("159"));
        QVERIFY(!device.setBrightness(0));QCOMPARE(get("sys/class/backlight/backlight/brightness"),QByteArray("159"));
        QVERIFY(device.setDimmed(true));QCOMPARE(get("sys/class/backlight/backlight/brightness"),QByteArray("39"));
        QVERIFY(device.setDimmed(false));QCOMPARE(get("sys/class/backlight/backlight/brightness"),QByteArray("159"));
        QVERIFY(device.automaticCpu());
        QVERIFY(device.setPowerScene("desktop"));QCOMPARE(get(cpu+"scaling_max_freq"),QByteArray("816000"));
        QVERIFY(device.setPowerScene("game"));QCOMPARE(get(cpu+"scaling_max_freq"),QByteArray("1008000"));
        QVERIFY(device.setPowerScene("off"));QCOMPARE(get(cpu+"scaling_max_freq"),QByteArray("600000"));
        QVERIFY(device.setScreenOff(true));QCOMPARE(get("sys/class/backlight/backlight/brightness"),QByteArray("0"));
        QVERIFY(!device.setBrightness(70));
        QVERIFY(device.setScreenOff(false));QCOMPARE(get("sys/class/backlight/backlight/brightness"),QByteArray("159"));
        QVERIFY(device.setDimmed(true));QVERIFY(device.setScreenOff(true));
        QVERIFY(device.setScreenOff(false));QCOMPARE(get("sys/class/backlight/backlight/brightness"),QByteArray("159"));
        put("sys/class/power_supply/rk817-charger/online","0");
        QVERIFY(device.setPowerScene("desktop"));QCOMPARE(get(cpu+"scaling_max_freq"),QByteArray("816000"));
        QVERIFY(!device.applyCpu("performance",600000,1008000));
        put("sys/class/power_supply/rk817-battery/voltage_avg","3200000");
        QVERIFY(!device.setPowerScene("game"));QCOMPARE(get(cpu+"scaling_max_freq"),QByteArray("816000"));
        put("sys/class/power_supply/rk817-battery/voltage_avg","3800000");
        put("sys/class/power_supply/rk817-charger/online","1");
        QVERIFY(device.setAutomaticCpu(false));QVERIFY(!device.automaticCpu());
        QVERIFY(device.setAutomaticCpu(true));QVERIFY(device.automaticCpu());
        QVERIFY(device.applyCpu("performance",816000,1200000));QCOMPARE(get(cpu+"scaling_governor"),QByteArray("performance"));
        QVERIFY(!device.automaticCpu());
        QVERIFY(!device.applyCpu("powersave",600000,1296000));QVERIFY(!device.applyCpu("schedutil",1200000,816000));
        QVERIFY(!device.applyCpu("schedutil",500000,1296000));QVERIFY(!device.applyCpu("schedutil",600000,1500000));
        QVERIFY(device.cpuPreset("original"));QCOMPARE(get(cpu+"scaling_governor"),QByteArray("schedutil"));
        QSignalSpy warning(&device,&DeviceState::warning);put("sys/class/power_supply/rk817-battery/voltage_avg","3200000");device.refresh();QCOMPARE(warning.size(),1);
        QVERIFY(!device.applyCpu("performance",600000,1296000));device.refresh();QCOMPARE(warning.size(),1);
        put("sys/class/power_supply/rk817-battery/voltage_avg","3800000");put("sys/class/thermal/thermal_zone0/temp","92000");
        QVERIFY(!device.cpuPreset("performance"));
        put("sys/class/thermal/thermal_zone0/temp","55000");
        QSignalSpy power(&device,&DeviceState::powerRequested);QVERIFY(device.requestPower("poweroff"));QCOMPARE(power.at(0).at(0).toInt(),77);
        QVERIFY(!device.requestPower("suspend"));QCOMPARE(power.size(),1);
        Preferences state(directory.path()+"/state");Telemetry metrics(directory.path());ControllerInput controller;QQuickView view;
        view.setInitialProperties({{"store",QVariant::fromValue(&state)},{"metrics",QVariant::fromValue(&metrics)},{"controller",QVariant::fromValue(&controller)},{"device",QVariant::fromValue(&device)}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));QCOMPARE(view.status(),QQuickView::Ready);view.resize(1024,768);view.show();QVERIFY(QTest::qWaitForWindowExposed(&view));
        auto *root=view.rootObject();auto tap=[&](const char *key){QVERIFY(QMetaObject::invokeMethod(root,"dispatch",Q_ARG(QVariant,QString(key)),Q_ARG(QVariant,false)));};
        QCOMPARE(root->findChild<QObject *>("statusWifi")->property("level").toInt(),79);
        QCOMPARE(root->findChild<QObject *>("statusBattery")->property("text").toString(),QStringLiteral("86%"));
        auto *clock=root->findChild<QQuickItem *>("statusClock");auto *wifiIcon=root->findChild<QQuickItem *>("statusWifiIcon");auto *batteryIcon=root->findChild<QQuickItem *>("statusBatteryIcon");
        QVERIFY(clock&&wifiIcon&&batteryIcon);QCOMPARE(wifiIcon->size(),QSizeF(24,24));QCOMPARE(batteryIcon->size(),wifiIcon->size());
        QCOMPARE(batteryIcon->property("name").toString(),QStringLiteral("battery-charging"));
        const auto centerY=[](QQuickItem *item){return item->mapToScene(QPointF(0,item->height()/2)).y();};
        QVERIFY(qAbs(centerY(clock)-centerY(wifiIcon))<=1);QVERIFY(qAbs(centerY(clock)-centerY(batteryIcon))<=1); // One centerline, within rounding.
        if(!qEnvironmentVariable("R46H_UI_CAPTURE_DIR").isEmpty())QVERIFY(view.grabWindow().save(qEnvironmentVariable("R46H_UI_CAPTURE_DIR")+"/device-status.png"));
        QVERIFY(QMetaObject::invokeMethod(root,"showScene",Q_ARG(QVariant,QString("power"))));QTRY_VERIFY(root->property("settingsDetailReady").toBool());
        for(int i=0;i<4;++i)tap("down");tap("accept");
        QVERIFY(root->property("choicesOpen").toBool());tap("accept");QCOMPARE(power.size(),1); // Default is cancel.
        tap("accept");tap("down");tap("accept");QCOMPARE(power.size(),2); // Confirmation emits only a test signal.
        // §8 power menu: 息屏 focused; 重启/关机 ask again with 取消 focused; B steps back.
        tap("home");QVERIFY(QMetaObject::invokeMethod(root,"openPowerMenu"));
        auto *powerLayer=root->findChild<QObject *>("powerMenuLayer");QVERIFY(powerLayer&&powerLayer->property("open").toBool());
        QCOMPARE(powerLayer->property("index").toInt(),0);QVERIFY(root->property("choicesOpen").toBool());
        QCOMPARE(findItem(root,"powerApps")->property("text").toString(),QStringLiteral("没有后台应用"));
        tap("down");tap("accept");QCOMPARE(powerLayer->property("confirming").toString(),QString("reboot"));QCOMPARE(powerLayer->property("index").toInt(),0);
        tap("back");QCOMPARE(powerLayer->property("confirming").toString(),QString());QCOMPARE(powerLayer->property("index").toInt(),1);
        tap("down");tap("accept");tap("accept");QVERIFY(!powerLayer->property("open").toBool());QCOMPARE(power.size(),2); // 取消
        QVERIFY(QMetaObject::invokeMethod(root,"openPowerMenu"));tap("down");tap("down");tap("accept");tap("down");tap("accept");QCOMPARE(power.size(),3);
        QVERIFY(QMetaObject::invokeMethod(root,"openPowerMenu"));tap("quick");QVERIFY(!powerLayer->property("open").toBool());
        QVERIFY(QMetaObject::invokeMethod(root,"openPowerMenu"));tap("accept");QVERIFY(root->property("screenOff").toBool());
        tap("accept");QVERIFY(!root->property("screenOff").toBool());
        QVERIFY(QMetaObject::invokeMethod(root,"showScene",Q_ARG(QVariant,QString("power"))));QTRY_VERIFY(root->property("settingsDetailReady").toBool());
        root->setProperty("settingsIndex",1);tap("accept");QVERIFY(root->property("screenOff").toBool()); // 立即息屏
        QCOMPARE(get("sys/class/backlight/backlight/brightness"),QByteArray("0"));
        tap("accept");QVERIFY(!root->property("screenOff").toBool());
        QCOMPARE(get("sys/class/backlight/backlight/brightness"),QByteArray("159"));
        root->setProperty("settingsCategory",5);root->setProperty("settingsIndex",3);tap("accept");tap("down");tap("down");tap("accept"); // 性能 › 频率预设
        QCOMPARE(get(cpu+"scaling_governor"),QByteArray("performance"));
        const auto captures=qEnvironmentVariable("R46H_UI_CAPTURE_DIR");QTest::qWait(200);
        if(!captures.isEmpty())QVERIFY(view.grabWindow().save(captures+"/device-cpu.png"));
        QVERIFY(device.cpuPreset("original"));
        QCOMPARE(device.info().value("socTemperatureC").toDouble(),55.);
        QVERIFY(state.choose("font",3));state.adjust("monitor",1);root->setProperty("testInputCapture",true);
        QVERIFY(QMetaObject::invokeMethod(root,"openEditor"));
        auto *hud=root->findChild<QQuickItem *>("performancePanel");QVERIFY(hud);
        QCOMPARE(hud->x()+hud->width(),992.);QCOMPARE(hud->y(),80.);QVERIFY(hud->width()<=360);
        const auto row=[&](const char *name){auto *label=hud->findChild<QQuickItem *>(name);return label&&label->isVisible()?label->property("text").toString().replace(QChar(0xa0),' '):QString();};
        const auto rate=row("performanceRate");QVERIFY(rate.isEmpty()||(rate.startsWith(QStringLiteral("界面 "))&&rate.endsWith(QStringLiteral(" 次/秒")))); // Shown once measured.
        QVERIFY(row("performanceLoad").startsWith(QStringLiteral("CPU 1.30 GHz")));QVERIFY(row("performanceLoad").endsWith(QStringLiteral("GPU 480 MHz")));
        QCOMPARE(row("performanceHealth"),QStringLiteral("55 °C · 内存 256 / 1024 MB"));
        for(const auto *name:{"performanceRate","performanceLoad","performanceHealth"}){
            auto *label=hud->findChild<QQuickItem *>(name);QVERIFY(label);
            QVERIFY(!label->property("text").toString().contains(QStringLiteral("—")));
            QVERIFY2(!label->property("truncated").toBool(),qPrintable(QString("%1 %2 > %3").arg(label->property("text").toString()).arg(label->implicitWidth()).arg(label->width())));}
        const auto thermal=[&]{QVariant value;const QVariantMap row{{"key","thermal"}}; // Empty when the call fails.
            QMetaObject::invokeMethod(root->findChild<QObject *>("settingsView"),"rowValue",Q_RETURN_ARG(QVariant,value),Q_ARG(QVariant,row));return value.toString();};
        QCOMPARE(thermal(),QStringLiteral("未介入"));
        put("sys/class/thermal/cooling_device0/cur_state","1");device.refresh();
        QCOMPARE(thermal(),QStringLiteral("CPU 限频"));
        put("sys/class/thermal/cooling_device0/cur_state","0");device.refresh();
        QTest::qWait(200);if(!captures.isEmpty())QVERIFY(view.grabWindow().save(captures+"/device-hud-input.png"));
        QVERIFY(QMetaObject::invokeMethod(root,"closeEditor"));
        // A late write failure restores the already-written limits and disables unsafe continuation.
        QVERIFY(QFile::rename(directory.filePath(cpu+"scaling_governor"),directory.filePath(cpu+"saved-governor")));
        QVERIFY(QFile::link(directory.filePath(cpu+"saved-governor"),directory.filePath(cpu+"scaling_governor")));
        QVERIFY(!device.applyCpu("performance",816000,1200000));
        QCOMPARE(get(cpu+"scaling_min_freq"),QByteArray("600000"));QCOMPARE(get(cpu+"scaling_max_freq"),QByteArray("1296000"));
        QVERIFY(!device.controls());
    }
    void savedNetworkProfilesAndLiteralArguments() {
        const QByteArray id="11111111-2222-4333-8444-555555555555";
        QVariantList profiles;
        QVERIFY(NetworkState::parse(id+":wifi:Studio\\:5G:wlan0\n",&profiles));
        QCOMPARE(profiles.size(),1);QCOMPARE(profiles[0].toMap().value("name").toString(),QString("Studio:5G"));
        QVERIFY(profiles[0].toMap().value("active").toBool());
        QVERIFY(!NetworkState::parse("bad:record",&profiles));QCOMPARE(profiles.size(),1);
        QVERIFY(!NetworkState::parse(id+":wifi:name:wlan0\n"+id+":wifi:duplicate:\n",&profiles));
        QTemporaryDir directory;
        QFile program(directory.filePath("nmcli-fixture"));QVERIFY(program.open(QIODevice::WriteOnly));
        program.write("#!/bin/sh\ncase \"$*\" in *\"connection show\") printf '%s\\n' '11111111-2222-4333-8444-555555555555:wifi:Studio\\:5G:wlan0';; *) printf '%s\\n' \"$@\" > \"$0.args\";; esac\n");
        program.close();QVERIFY(program.setPermissions(QFile::ReadOwner|QFile::WriteOwner|QFile::ExeOwner));
        NetworkState network(true,true,program.fileName());QTRY_VERIFY(!network.busy());QCOMPARE(network.profiles().size(),1);
        QVERIFY(!network.activate("not-a-known-uuid;touch bad"));QVERIFY(!QFileInfo::exists(program.fileName()+".args"));
        QVERIFY(network.activate(QString::fromLatin1(id)));QTRY_VERIFY(!network.busy());
        QFile trace(program.fileName()+".args");QVERIFY(trace.open(QIODevice::ReadOnly));const auto data=trace.readAll();
        QVERIFY(data.endsWith("connection\nup\nuuid\n"+id+"\n"));
        QVERIFY(!data.contains("password"));
        NetworkState readonly(true,false,program.fileName());QTRY_VERIFY(!readonly.busy());QVERIFY(!readonly.activate(QString::fromLatin1(id)));QVERIFY(!readonly.disconnect());
        QVERIFY(network.disconnect());QTRY_VERIFY(!network.busy());
    }
    void wifiChooserPasswordPrivacyAndForget() {
        QTemporaryDir directory;Preferences state(directory.path());Telemetry metrics(directory.path());ControllerInput controller;
        DeviceState device(directory.path(),true,true);
        // An nmcli stand-in: the SettingsNight networks, Jume-5G connected.
        QFile program(directory.filePath("nmcli-fixture"));QVERIFY(program.open(QIODevice::WriteOnly));
        program.write("#!/bin/sh\ncase \"$*\" in *\"device wifi list\"*) cat \"$0.scan\";; *\"connection delete\"*) printf '%s\\n' \"$@\" > \"$0.deleted\";; *) printf '%s\\n' '11111111-2222-4333-8444-555555555555:wifi:Jume-5G:wlan0';; esac\n");program.close();
        QVERIFY(program.setPermissions(QFile::ReadOwner|QFile::WriteOwner|QFile::ExeOwner));
        QFile scan(program.fileName()+".scan");QVERIFY(scan.open(QIODevice::WriteOnly));
        scan.write("/org/freedesktop/NetworkManager/AccessPoint/1:AA\\:BB\\:CC\\:DD\\:EE\\:01:Jume-5G:82:WPA2:wlan0:*\n"
                   "/org/freedesktop/NetworkManager/AccessPoint/2:AA\\:BB\\:CC\\:DD\\:EE\\:02:Home-2.4G:61:WPA2:wlan0:\n"
                   "/org/freedesktop/NetworkManager/AccessPoint/3:AA\\:BB\\:CC\\:DD\\:EE\\:03:Studio:34:WPA2:wlan0:\n");scan.close();
        NetworkState network(true,true,program.fileName());QTRY_VERIFY(!network.busy());
        QQuickView view;view.setInitialProperties({{"store",QVariant::fromValue(&state)},{"metrics",QVariant::fromValue(&metrics)},
            {"controller",QVariant::fromValue(&controller)},{"device",QVariant::fromValue(&device)},{"network",QVariant::fromValue(&network)}, {"testInputCapture",true}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));QCOMPARE(view.status(),QQuickView::Ready);
        view.resize(1024,768);view.show();QVERIFY(QTest::qWaitForWindowExposed(&view));auto *root=view.rootObject();
        auto tap=[&](const char *key){QVERIFY(QMetaObject::invokeMethod(root,"dispatch",Q_ARG(QVariant,QString(key)),Q_ARG(QVariant,false)));};
        auto *settings=root->findChild<QObject *>("settingsView");QVERIFY(settings);
        auto keys=[&]{QStringList result;for(const auto &row:settings->property("rows").toList())result<<row.toMap().value("key").toString()+":"+row.toMap().value("name").toString();return result;};
        auto reason=[&](int index){QVariant value;QMetaObject::invokeMethod(settings,"rowReason",Q_RETURN_ARG(QVariant,value),Q_ARG(QVariant,settings->property("rows").toList()[index]));return value.toString();};
        // §8 网络: the Wi-Fi switch (disabled with its reason), 已连接 and 附近的网络; Y scans.
        QVERIFY(QMetaObject::invokeMethod(root,"showScene",Q_ARG(QVariant,QString("settings"))));tap("right");
        QTRY_VERIFY(root->property("settingsDetailReady").toBool());
        QCOMPARE(keys(),QStringList({"wifi:Wi-Fi","netActive:Jume-5G","netScan:扫描附近的网络"}));
        QCOMPARE(reason(0),QStringLiteral("暂不支持"));
        tap("pageAction");QTRY_VERIFY(network.accessPoints().size()==3);QTRY_VERIFY(!network.busy());
        QCOMPARE(keys(),QStringList({"wifi:Wi-Fi","netActive:Jume-5G","netPoint:Home-2.4G","netPoint:Studio"}));
        tap("down");QCOMPARE(root->property("settingsIndex").toInt(),1);
        const auto captures=qEnvironmentVariable("R46H_UI_CAPTURE_DIR");
        for(const int percent:{100,130}){
            QVERIFY(state.choose("font",percent==100?1:3));
            for(const bool night:{false,true}){
                QVERIFY(state.choose("night",night?1:0));QTest::qWait(250);
                if(!captures.isEmpty())QVERIFY(view.grabWindow().save(captures+QString("/settings-network-%1-%2.png").arg(night?"night":"light").arg(percent)));
            }
        }
        // X disconnects the connected network after a confirmation whose default is 取消.
        tap("itemAction");QVERIFY(root->property("choicesOpen").toBool());tap("accept");QVERIFY(!root->property("choicesOpen").toBool());
        // A shows its details: close, disconnect or forget (confirmed, 取消 first).
        tap("accept");QVERIFY(root->property("choicesOpen").toBool());tap("down");tap("down");tap("accept");
        QVERIFY(root->property("choicesOpen").toBool());tap("accept");QVERIFY(!QFileInfo::exists(program.fileName()+".deleted"));
        // Start: saved networks, forget, remember new networks and refresh.
        tap("options");auto *options=root->findChild<QObject *>("optionsMenu");QVERIFY(options->property("open").toBool());
        QStringList ids;for(const auto &item:options->property("items").toList())ids<<item.toMap().value("id").toString();
        QCOMPARE(ids,QStringList({"netProfiles","netForget","netRemember","netRefresh"}));
        tap("down");tap("down");tap("accept");QVERIFY(network.remember());
        // A nearby protected network asks for its password in a private editor.
        tap("down");tap("accept");QVERIFY(root->property("editing").toBool());QVERIFY(root->property("sensitiveVisible").toBool());
        QVERIFY(!root->property("testInputVisible").toBool());
        auto *field=root->findChild<QQuickItem *>("inputField");QVERIFY(field);
        QCOMPARE(field->property("echoMode").toInt(),2); // TextInput.Password.
        QCOMPARE(field->property("maximumLength").toInt(),64);
        QVERIFY(field->property("inputMethodHints").toInt()&Qt::ImhHiddenText);
        QVERIFY(field->property("inputMethodHints").toInt()&Qt::ImhNoAutoUppercase);
        field->setProperty("text","fixture-password");QVERIFY(QMetaObject::invokeMethod(root,"finishEditor"));
        QVERIFY(root->property("editing").toBool()); // No fixture bus; refusal keeps the edit available.
        tap("back");QCOMPARE(field->property("text").toString(),QString("fixture-passwor")); // B erases on the keyboard.
        tap("quick");QVERIFY(!root->property("editing").toBool());QVERIFY(field->property("text").toString().isEmpty());
        // Forget through the connected row: 忘记此网络, then confirm.
        tap("up");tap("accept");tap("down");tap("down");tap("accept");tap("down");tap("accept");QTRY_VERIFY(!network.busy());
        QFile deleted(program.fileName()+".deleted");QVERIFY(deleted.open(QIODevice::ReadOnly));
        QVERIFY(deleted.readAll().endsWith("connection\ndelete\nuuid\n11111111-2222-4333-8444-555555555555\n"));
    }
    void virtualKeyboardInput() {
        if (qEnvironmentVariable("R46H_VIRTUAL_KEYBOARD") != "1") QSKIP("Run with the isolated Linux virtual keyboard runtime");
        QTemporaryDir directory;
        Preferences state(directory.path()); Telemetry metrics(directory.path()); ControllerInput controller;
        QQuickView view; view.setColor(QColor("#111a24"));
        view.setInitialProperties({{"store", QVariant::fromValue(&state)}, {"metrics", QVariant::fromValue(&metrics)},
            {"controller", QVariant::fromValue(&controller)}, {"keyboardEnabled", true}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));
        QCOMPARE(view.status(), QQuickView::Ready); view.resize(1024, 768); view.show();
        QVERIFY(QTest::qWaitForWindowExposed(&view)); view.requestActivate();
        auto *root = view.rootObject(); QVERIFY(QMetaObject::invokeMethod(root, "openEditor"));
        auto *loader = root->findChild<QObject *>("virtualKeyboard"); QVERIFY(loader);
        QTRY_COMPARE(loader->property("status").toInt(), 1);
        auto *keyLayout = root->findChild<QQuickItem *>("keyboardLayoutLoader"); QVERIFY(keyLayout);
        QVERIFY(QQmlProperty(keyLayout, "layer.enabled").read().toBool());
        auto *keyboard = root->findChild<QQuickItem *>("keyboard"); QVERIFY(keyboard);
        QCOMPARE(QQmlProperty(keyboard, "style.navigationHighlightColor").read().value<QColor>(), QColor("#009482"));
        state.adjust("motion", 1); QVERIFY(keyboard->property("noAnimations").toBool());
        state.adjust("motion", 1); QVERIFY(!keyboard->property("noAnimations").toBool());
        auto *field = root->findChild<QQuickItem *>("inputField"); QVERIFY(field);
        QTRY_VERIFY(field->hasActiveFocus()); QTest::qWait(200);
        // §8 Jume layouts: the 20-column grid with badged special keys, light and night, 100% and 130%.
        QCOMPARE(QQmlProperty(keyboard, "style.keyboardDesignWidth").read().toReal(), 1024.);
        field->setProperty("text", QStringLiteral("metal")); state.adjust("motion", 1); // Settled captures, no theme fade.
        const auto keyboardCaptures = qEnvironmentVariable("R46H_UI_CAPTURE_DIR");
        for (const int percent : {100, 130}) {
            QVERIFY(state.choose("font", percent == 100 ? 1 : 3));
            for (const bool night : {false, true}) {
                QVERIFY(state.choose("night", night ? 1 : 0)); QTest::qWait(300);
                if (!keyboardCaptures.isEmpty())
                    QVERIFY(view.grabWindow().save(keyboardCaptures + QString("/keyboard-%1-%2.png").arg(night ? "night" : "light").arg(percent)));
            }
        }
        QVERIFY(state.choose("font", 1)); QVERIFY(state.choose("night", 0)); state.adjust("motion", 1); field->setProperty("text", QString());
        // One key always has the focus: q at first, kept when text arrives over IPC or from a USB keyboard.
        auto *inputArea = root->findChild<QQuickItem *>("keyboardInputArea"); QVERIFY(inputArea);
        const auto focusedText = [&] { auto *key = inputArea->property("initialKey").value<QObject *>(); return key ? key->property("text").toString() : QString(); };
        QTRY_COMPARE(focusedText(), QString("q"));
        root->setProperty("testInputCapture", true);
        const auto keyboardState = [&] {
            return QString("editing=%1 visible=%2 navigation=%3 focused=%4 text=%5").arg(root->property("editing").toBool())
                .arg(QGuiApplication::inputMethod()->isVisible()).arg(keyboard->property("navigationModeActive").toBool())
                .arg(focusedText(), field->property("text").toString());
        };
        QVERIFY(QMetaObject::invokeMethod(root, "remoteText", Q_ARG(QVariant, QString("ipc")))); QTest::qWait(100);
        QVERIFY2(focusedText() == "q" && root->property("editing").toBool(), qPrintable(keyboardState()));
        QTest::keyClick(&view, Qt::Key_Z); QTest::qWait(100);
        QVERIFY2(focusedText() == "q" && root->property("editing").toBool(), qPrintable(keyboardState()));
        field->setProperty("text", QString());
        // The same focus-object events sent by SDL must navigate Qt's own keys.
        // Down goes to the nearest key of the offset row (q ↓ a); A types it through Qt's own key
        // (capitalized at the start of an empty field).
        QVERIFY(QMetaObject::invokeMethod(root, "dispatch", Q_ARG(QVariant, QString("down")), Q_ARG(QVariant, false)));
        QVERIFY2(focusedText() == "a", qPrintable(keyboardState()));
        controller.keyboardAction("accept");
        QTRY_VERIFY2(field->property("text").toString().toLower() == "a", qPrintable(keyboardState()));
        QVERIFY(root->property("editing").toBool());
        const auto before = field->property("text").toString();
        controller.keyboardAction("right"); controller.keyboardAction("accept");
        QTRY_VERIFY(field->property("text").toString() != before);
        auto *area=root->findChild<QQuickItem *>("keyboardInputArea"); QVERIFY(area);
        auto focusedKey=[&]{return qobject_cast<QQuickItem *>(area->property("initialKey").value<QObject *>());};
        for (const auto &direction : {QString("left"),QString("right")}) {
            auto *key=focusedKey(); QVERIFY(key); const auto point=key->mapToItem(area,QPointF());
            auto x=point.x(); bool wrapped=false;
            for(int n=0;n<32&&!wrapped;++n) {
                QVERIFY(QMetaObject::invokeMethod(root,"dispatch",Q_ARG(QVariant,direction),Q_ARG(QVariant,false)));
                key=focusedKey(); QVERIFY(key); const auto next=key->mapToItem(area,QPointF());
                QCOMPARE(next.y(),point.y());
                wrapped=direction=="left"?next.x()>x:next.x()<x; x=next.x();
            }
            QVERIFY(wrapped);
        }
        auto dispatch=[&](const char *name,bool repeated=false){QVERIFY(QMetaObject::invokeMethod(root,"dispatch",Q_ARG(QVariant,QString(name)),Q_ARG(QVariant,repeated)));};
        field->setProperty("text",QStringLiteral("ab中")); field->setProperty("cursorPosition",3);
        dispatch("back"); QCOMPARE(field->property("text").toString(),QString("ab")); // §7.4: B erases.
        dispatch("pageAction"); QCOMPARE(field->property("text").toString(),QString("ab ")); // Y space.
        dispatch("prevSection"); QCOMPARE(field->property("cursorPosition").toInt(),2); // L1/R1 cursor.
        dispatch("nextSection"); QCOMPARE(field->property("cursorPosition").toInt(),3);
        // Holding B erases to empty and stops; only a separate press on the empty field closes.
        dispatch("back"); for(int i=0;i<4;++i) dispatch("back",true);
        QVERIFY(field->property("text").toString().isEmpty()); QVERIFY(root->property("editing").toBool());
        QQmlComponent ime(view.engine());
        ime.setData(R"(import QtQuick
            import QtQuick.VirtualKeyboard
            import QtQuick.VirtualKeyboard.Settings
            QtObject {
                property bool chineseAvailable: VirtualKeyboardSettings.availableLocales.indexOf("zh_CN") >= 0
                property int candidates: InputContext.inputEngine.wordCandidateListModel.count
                property bool shift: InputContext.shiftActive
                property string locale: VirtualKeyboardSettings.locale
                function chinese() { VirtualKeyboardSettings.locale = "zh_CN" }
                function typePinyin() {
                    InputContext.inputEngine.virtualKeyClick(Qt.Key_N, "n", Qt.NoModifier)
                    InputContext.inputEngine.virtualKeyClick(Qt.Key_I, "i", Qt.NoModifier)
                }
                function commitFirst() { InputContext.inputEngine.wordCandidateListModel.selectItem(0) }
            })", QUrl());
        QScopedPointer<QObject> inputMethod(ime.create()); QVERIFY2(inputMethod, qPrintable(ime.errorString()));
        QVERIFY(inputMethod->property("chineseAvailable").toBool());
        // X shift, L2 中/英 and R2 symbols act on the keyboard without moving the key focus.
        const bool shifted = inputMethod->property("shift").toBool();
        dispatch("itemAction"); QTRY_COMPARE(inputMethod->property("shift").toBool(), !shifted);
        dispatch("itemAction"); QTRY_COMPARE(inputMethod->property("shift").toBool(), shifted);
        dispatch("pageUp"); QCOMPARE(inputMethod->property("locale").toString(), QString("zh_CN"));
        dispatch("pageUp"); QCOMPARE(inputMethod->property("locale").toString(), QString("en_GB"));
        dispatch("pageDown"); QVERIFY(keyboard->property("symbolMode").toBool());
        dispatch("pageDown"); QVERIFY(!keyboard->property("symbolMode").toBool());
        field->setProperty("text", ""); QVERIFY(QMetaObject::invokeMethod(inputMethod.data(), "chinese"));
        QTest::qWait(100); QVERIFY(QMetaObject::invokeMethod(inputMethod.data(), "typePinyin"));
        QTRY_VERIFY(inputMethod->property("candidates").toInt() > 0);
        // Composing pinyin with the candidate bar, light and night, 100% and 130%.
        state.adjust("motion", 1);
        for (const int percent : {100, 130}) {
            QVERIFY(state.choose("font", percent == 100 ? 1 : 3));
            for (const bool night : {false, true}) {
                QVERIFY(state.choose("night", night ? 1 : 0)); QTest::qWait(300);
                QVERIFY(inputMethod->property("candidates").toInt() > 0);
                if (!keyboardCaptures.isEmpty())
                    QVERIFY(view.grabWindow().save(keyboardCaptures + QString("/keyboard-pinyin-%1-%2.png").arg(night ? "night" : "light").arg(percent)));
            }
        }
        QVERIFY(state.choose("font", 1)); QVERIFY(state.choose("night", 0)); state.adjust("motion", 1);
        // Composing: the hints page and commit. Up from the top row enters the candidate bar (no key
        // keeps the focus), → picks the second candidate, A commits it and the focus returns to a key.
        auto *panel = qvariant_cast<QObject *>(root->findChild<QObject *>("virtualKeyboard")->property("item")); QVERIFY(panel);
        auto *hints = root->findChild<QObject *>("editorHints"); QVERIFY(hints);
        QTRY_VERIFY(hints->property("composing").toBool());
        auto *candidateView = keyboard->findChild<QQuickItem *>("wordCandidateView"); QVERIFY(candidateView);
        QVariant second; QVERIFY(QMetaObject::invokeMethod(panel, "candidateText", Q_RETURN_ARG(QVariant, second), Q_ARG(QVariant, 1)));
        QVERIFY(!second.toString().isEmpty());
        for (int i = 0; i < 4 && !panel->property("candidateFocus").toBool(); ++i) dispatch("up");
        QVERIFY2(panel->property("candidateFocus").toBool(), qPrintable(keyboardState()));
        QVERIFY(!inputArea->property("initialKey").value<QObject *>());
        QCOMPARE(candidateView->property("currentIndex").toInt(), 0);
        dispatch("left"); QCOMPARE(candidateView->property("currentIndex").toInt(), 0); // No wrap.
        dispatch("right"); QCOMPARE(candidateView->property("currentIndex").toInt(), 1);
        dispatch("accept");
        QTRY_COMPARE(field->property("text").toString(), second.toString());
        QTRY_VERIFY(!panel->property("candidateFocus").toBool());
        QTRY_VERIFY(!focusedText().isEmpty());
        QVERIFY(!hints->property("composing").toBool());
        // Y commits the default candidate; B in the bar returns to the keys without committing.
        QVERIFY(QMetaObject::invokeMethod(inputMethod.data(), "typePinyin"));
        QTRY_VERIFY(hints->property("composing").toBool());
        for (int i = 0; i < 4 && !panel->property("candidateFocus").toBool(); ++i) dispatch("up");
        QVERIFY(panel->property("candidateFocus").toBool());
        dispatch("back"); QVERIFY(!panel->property("candidateFocus").toBool()); QVERIFY(!focusedText().isEmpty());
        QVERIFY(hints->property("composing").toBool());
        QVariant first; QVERIFY(QMetaObject::invokeMethod(panel, "candidateText", Q_RETURN_ARG(QVariant, first), Q_ARG(QVariant, 0)));
        dispatch("pageAction");
        QTRY_COMPARE(field->property("text").toString(), second.toString() + first.toString());
        QVERIFY(field->property("text").toString().front().unicode() > 127);
        state.adjust("font", 1); state.adjust("font", 1); state.adjust("monitor", 1);
        QTest::qWait(200);
        const auto captures = qEnvironmentVariable("R46H_UI_CAPTURE_DIR");
        if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + "/arm64-keyboard-pinyin-130.png"));
        // §8 has no hide key: Select cancels the entry and closes the keyboard.
        dispatch("quick"); QTRY_VERIFY(!root->property("editing").toBool());
        // Reopening returns to the key used last.
        const auto lastKey = root->property("keyboardLastKey").toString(); QVERIFY(!lastKey.isEmpty());
        QVERIFY(!QGuiApplication::inputMethod()->isVisible());
        QVERIFY(field->property("text").toString().isEmpty());
        QTRY_COMPARE(loader->property("status").toInt(), 0);
        QVERIFY(root->hasActiveFocus());
        // Reopening must not inherit a stale deferred close or a disabled input context.
        QVERIFY(QMetaObject::invokeMethod(root, "openEditor"));
        QTRY_COMPARE(loader->property("status").toInt(), 1);
        QTRY_VERIFY(QGuiApplication::inputMethod()->isVisible());
        QTRY_VERIFY(field->hasActiveFocus());
        auto *reopenedLayout = root->findChild<QQuickItem *>("keyboardLayoutLoader"); QVERIFY(reopenedLayout);
        QTRY_COMPARE(reopenedLayout->property("status").toInt(), 1);
        QTest::qWait(200); // Match initial entry: finish keyboard layout/observer registration.
        auto *reopenedArea = root->findChild<QQuickItem *>("keyboardInputArea"); QVERIFY(reopenedArea);
        QTRY_VERIFY(reopenedArea->property("initialKey").value<QObject *>());
        QCOMPARE(reopenedArea->property("initialKey").value<QObject *>()->property("text").toString(), lastKey);
        for (int i = 0; i < 3; ++i) dispatch("up"); // The top row holds letters only.
        controller.keyboardAction("accept");
        QTRY_VERIFY(!field->property("text").toString().isEmpty());
        dispatch("options"); // Start: 完成.
        QVERIFY(!root->property("editing").toBool()); QVERIFY(field->property("text").toString().isEmpty());
        QVERIFY(QMetaObject::invokeMethod(root, "openEditor")); QTRY_COMPARE(loader->property("status").toInt(), 1);
        dispatch("back"); QVERIFY(!root->property("editing").toBool()); // B on an empty field closes.
    }
};
QTEST_MAIN(ShellCheck)
#include "check.moc"
