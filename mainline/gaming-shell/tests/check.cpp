#include "input.h"
#include "preferences.h"
#include "telemetry.h"
#include "applications.h"
#include "streaming.h"
#include "device.h"
#include "network.h"
#include <QCryptographicHash>
#include <QJsonArray>
#include <QFile>
#include <QFontDatabase>
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
#include <QtTest>
#include <sys/stat.h>
#include <unistd.h>
#include <signal.h>

class ShellCheck final : public QObject {
    Q_OBJECT
private slots:
    void initTestCase() {
        QGuiApplication::styleHints()->setTabFocusBehavior(Qt::TabFocusAllControls);
        const auto font = QCoreApplication::applicationDirPath() + "/../share/fonts/truetype/droid/DroidSansFallbackFull.ttf";
        if (QFileInfo::exists(font)) QVERIFY(QFontDatabase::addApplicationFont(font) >= 0);
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
            QVERIFY(state.save()); QVERIFY(!state.dirty());
        }
        Preferences reloaded(directory.path());
        QCOMPARE(reloaded.volume(), 100); QCOMPARE(reloaded.brightness(), 10);
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
        key(Qt::Key_Return); QVERIFY(root->property("session").toBool());
        key(Qt::Key_Right); QCOMPARE(root->property("sessionMoves").toInt(), 1);
        key(Qt::Key_Q); QVERIFY(root->property("quickOpen").toBool());
        key(Qt::Key_Right); QCOMPARE(state.volume(), 60); QCOMPARE(root->property("sessionMoves").toInt(), 1);
        key(Qt::Key_Down); key(Qt::Key_Left); QCOMPARE(state.brightness(), 65);
        key(Qt::Key_Escape); QVERIFY(!root->property("quickOpen").toBool());
        QVERIFY(root->property("session").toBool()); QVERIFY(!state.dirty());
        key(Qt::Key_Left); QCOMPARE(root->property("sessionMoves").toInt(), 2);
        key(Qt::Key_Escape); QVERIFY(!root->property("session").toBool()); QCOMPARE(root->property("selected").toInt(), 1);
        QVERIFY(root->property("notice").toString().isEmpty());
        key(Qt::Key_BracketRight); QCOMPARE(root->property("page").toInt(), 1);
        key(Qt::Key_Down); QCOMPARE(root->property("selected").toInt(), 3);
        key(Qt::Key_Up); QCOMPARE(root->property("selected").toInt(), 0);
        key(Qt::Key_Up); QVERIFY(root->property("tabsFocused").toBool());
        key(Qt::Key_Right); QCOMPARE(root->property("page").toInt(), 2);
        QVERIFY(root->property("settingsSidebar").toBool()); QVERIFY(!root->property("tabsFocused").toBool());
        key(Qt::Key_Right); key(Qt::Key_Return); key(Qt::Key_Up); key(Qt::Key_Return); QCOMPARE(state.volume(), 65);
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
        action("nextTab"); action("nextTab"); action("right"); action("accept"); action("up"); action("left");
        QVERIFY(!root->property("settingsSidebar").toBool()); QVERIFY(root->property("settingsAdjusting").toBool());
        action("back");
        QCOMPARE(root->property("page").toInt(), 2); QVERIFY(state.dirty());
        action("quick"); action("back"); QVERIFY(root->property("quickOpen").toBool());
        QVERIFY(file.remove()); action("back"); QVERIFY(!root->property("quickOpen").toBool());
        action("accept"); // Finish the value editor after saving becomes possible.
        root->setProperty("settingsIndex", 2);
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
        capture("settings-primary");
        action("right"); QVERIFY(!root->property("settingsSidebar").toBool()); QCOMPARE(state.volume(), 55);
        auto *animation = root->findChild<QObject *>("settingsFocusMoveX"); QVERIFY(animation);
        QVERIFY(animation->property("running").toBool());
        QTest::qWait(40); capture("settings-transition");
        action("left"); // A new input retargets the in-flight visual transition.
        QVERIFY(root->property("settingsSidebar").toBool());
        auto *categories = root->findChild<QQuickItem *>("settingsCategories"); QVERIFY(categories);
        auto *rows = root->findChild<QQuickItem *>("settingsItems"); QVERIFY(rows);
        auto row = [](QQuickItem *list) { return qobject_cast<QQuickItem *>(list->property("currentItem").value<QObject *>()); };
        QTRY_COMPARE(outline->x(), 0.); QTRY_COMPARE(outline->width(), row(categories)->width());
        action("right");
        QTRY_COMPARE(outline->x(), rows->mapToItem(outline->parentItem(), QPointF()).x());
        QTRY_COMPARE(outline->width(), row(rows)->width());
        capture("settings-secondary");
        action("down"); QCOMPARE(root->property("settingsIndex").toInt(), 1);
        QTRY_COMPARE(outline->y(), row(rows)->mapToItem(outline->parentItem(), QPointF()).y());
        QCOMPARE(outline->height(), row(rows)->height());
        action("up"); action("accept"); QVERIFY(root->property("settingsAdjusting").toBool());
        action("up"); QCOMPARE(state.volume(), 60);
        action("down"); action("down"); QCOMPARE(state.volume(), 50);
        QTest::qWait(150); capture("settings-adjusting");
        action("left"); QVERIFY(root->property("settingsSidebar").toBool());
        QVERIFY(!root->property("settingsAdjusting").toBool()); QCOMPARE(state.volume(), 50);
        Preferences saved(directory.path()); QCOMPARE(saved.volume(), 50);
        action("right"); action("previousTab"); action("nextTab");
        QVERIFY(root->property("settingsSidebar").toBool());
        action("right");
        QTest::mouseClick(&view, Qt::LeftButton, Qt::NoModifier, QPoint(330, 121));
        QVERIFY(root->property("settingsSidebar").toBool());
        // Accessibility preference keeps logical navigation but skips spatial motion.
        state.adjust("motion", 1); action("right");
        QCOMPARE(outline->x(), rows->mapToItem(outline->parentItem(), QPointF()).x()); QCOMPARE(outline->width(), row(rows)->width());
        QVERIFY(!animation->property("running").toBool());
        action("quick"); QCOMPARE(outline->opacity(), 0.);
        action("back"); QCOMPARE(outline->opacity(), 1.);
        action("left");
        for (int i = 0; i < 11; ++i) action("down");
        QCOMPARE(root->property("settingsCategory").toInt(), 11);
        QVERIFY(outline->y() >= 0 && outline->y() + outline->height() <= 493);
        QTest::qWait(300);
        QSignalSpy idle(&view, &QQuickWindow::frameSwapped); QTest::qWait(500);
        QVERIFY2(idle.size() <= 3, "Settled settings must not repaint continuously");
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
        auto labels = [&] {
            QStringList result;
            QList<QQuickItem *> pending{footer};
            while (!pending.isEmpty()) {
                auto *item = pending.takeLast();
                if (item->objectName() == "hintLabel") result << item->property("text").toString();
                pending.append(item->childItems());
            }
            return result;
        };
        auto *hud = root->findChild<QQuickItem *>("performancePanel"); QVERIFY(hud);
        const auto captures = qEnvironmentVariable("R46H_UI_CAPTURE_DIR");
        for (int scale : {100, 120}) {
            if (scale == 120) { state.adjust("font", 1); state.adjust("font", 1); }
            for (const auto &scene : {"home", "library", "settings", "power", "controller", "quick", "input"}) {
                action("home");
                QVERIFY(QMetaObject::invokeMethod(root, "showScene", Q_ARG(QVariant, QString(scene))));
                QTest::qWait(200);
                if (footer->isVisible()) QVERIFY2(footer->width() <= 952, qPrintable(QString("Footer overflow: %1 at %2%").arg(scene).arg(scale)));
                if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + QString("/%1-%2.png").arg(scene).arg(scale)));
                if (root->property("editing").toBool()) QVERIFY(QMetaObject::invokeMethod(root, "closeEditor"));
                if (root->property("quickOpen").toBool()) action("back");
            }
        }
        action("home"); QVERIFY(labels().contains("收藏"));
        action("nextTab"); action("nextTab"); QTest::qWait(200);
        QVERIFY(!labels().contains("收藏")); QVERIFY(labels().contains("选择分类"));
        state.adjust("monitor", 1); QTest::qWait(200);
        auto *outline = root->findChild<QQuickItem *>("settingsFocus"); QVERIFY(outline);
        QVERIFY(!hud->mapRectToItem(root, hud->boundingRect()).intersects(outline->mapRectToItem(root, outline->boundingRect())));
        if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + "/settings-hud-120.png"));
        action("down"); action("right"); QTest::qWait(200);
        QVERIFY(!labels().contains("打开")); QVERIFY(!labels().contains("调整"));
        action("accept"); QVERIFY(root->property("notice").toString().contains("尚未接入"));
        action("left"); root->setProperty("settingsCategory", 0); action("right"); action("accept"); QTest::qWait(200);
        QVERIFY(labels().contains("增减数值")); QVERIFY(footer->width() <= 952);
        action("quick"); QTest::qWait(200);
        QVERIFY(labels().contains("关闭面板")); QVERIFY(!labels().contains("收藏"));
        QVERIFY(hud->x() + hud->width() < 590); // The active quick panel remains unobstructed.
        if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + "/quick-hud-120.png"));
        // Use the actual switch, including its native pointer toggle and state binding.
        QQuickItem *motionSwitch = nullptr;
        auto *quickPanel = root->findChild<QQuickItem *>("quickPanel"); QVERIFY(quickPanel);
        QList<QQuickItem *> controls{quickPanel};
        while (!controls.isEmpty()) {
            auto *item = controls.takeLast(); controls.append(item->childItems());
            if (item->objectName() != "settingSwitch") continue;
            const auto point = item->mapToItem(root, QPointF());
            const auto *accessible = QAccessible::queryAccessibleInterface(item);
            if (item->isVisible() && point.x() > 590 && accessible && accessible->text(QAccessible::Name) == QStringLiteral("减少动态效果")) motionSwitch = item;
        }
        QVERIFY(motionSwitch);
        const auto center = motionSwitch->mapToItem(root, QPointF(motionSwitch->width() / 2, motionSwitch->height() / 2)).toPoint();
        QTest::mouseClick(&view, Qt::LeftButton, Qt::NoModifier, center);
        QVERIFY(state.reducedMotion()); QVERIFY(motionSwitch->property("checked").toBool());
        QTest::qWait(150);
        if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + "/quick-switches-120.png"));
        QTest::mouseClick(&view, Qt::LeftButton, Qt::NoModifier, center);
        QVERIFY(!state.reducedMotion()); QVERIFY(!motionSwitch->property("checked").toBool());
        action("back");
        action("home"); QTest::qWait(200);
        auto *pageContent = root->findChild<QQuickItem *>("pageContent"); QVERIFY(pageContent);
        auto *pageAnimation = root->findChild<QObject *>("pageRevealAnimation"); QVERIFY(pageAnimation);
        action("nextTab"); QTest::qWait(40);
        const auto current = pageContent->property("reveal").toReal(); QVERIFY(current > 0 && current < 1);
        action("nextTab"); QCOMPARE(root->property("page").toInt(), 2);
        QVERIFY(root->property("settingsSidebar").toBool());
        QVERIFY(pageContent->property("reveal").toReal() >= current);
        state.adjust("motion", 1);
        QVERIFY(!pageAnimation->property("running").toBool()); QCOMPARE(pageContent->property("reveal").toReal(), 1.);
        root->setProperty("settingsCategory", 0); QTest::qWait(200);
        QPointer<QQuickItem> settingsSwitch;
        controls = {root};
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
        QCOMPARE(ControllerInput::axisAction(8000, -9000), QString());
        QCOMPARE(ControllerInput::axisAction(-32768, 0), QString("left"));
        QCOMPARE(ControllerInput::axisAction(32767, 0), QString("right"));
        QCOMPARE(ControllerInput::axisAction(0, -32768), QString("up"));
        QCOMPARE(ControllerInput::axisAction(0, 32767), QString("down"));
        ControllerInput input;
        const int device = SDL_JoystickAttachVirtual(SDL_JOYSTICK_TYPE_GAMECONTROLLER, SDL_CONTROLLER_AXIS_MAX, SDL_CONTROLLER_BUTTON_MAX, 0);
        QVERIFY2(device >= 0, SDL_GetError());
        SDL_Joystick *joystick = SDL_JoystickOpen(device); QVERIFY(joystick);
        QSignalSpy actions(&input, &ControllerInput::action);
        input.poll();
        QVERIFY(SDL_JoystickSetVirtualAxis(joystick, SDL_CONTROLLER_AXIS_LEFTX, -32768) == 0);
        input.poll(); QVERIFY(!actions.isEmpty()); QCOMPARE(actions.last().at(0).toString(), QString("left"));
        QVERIFY(!input.deviceName().isEmpty()); QCOMPARE(input.axes()[0].toDouble(), -1.);
        actions.clear(); QTest::qWait(430); QVERIFY(!actions.isEmpty()); QVERIFY(actions.last().at(1).toBool());
        SDL_JoystickSetVirtualAxis(joystick, SDL_CONTROLLER_AXIS_LEFTX, 0); input.poll();
        actions.clear(); QTest::qWait(160); QVERIFY(actions.isEmpty());
        input.suppressUntilNeutral();
        SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_A, 1); input.poll();
        QVERIFY(actions.isEmpty());
        SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_A, 0); input.poll();
        SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_A, 1); input.poll();
        QVERIFY(!actions.isEmpty()); QCOMPARE(actions.last().at(0).toString(), QString("accept"));
        SDL_JoystickSetVirtualButton(joystick, SDL_CONTROLLER_BUTTON_A, 0); input.poll();
        for (const auto &button : {qMakePair(SDL_CONTROLLER_BUTTON_Y,QString("erase")), qMakePair(SDL_CONTROLLER_BUTTON_START,QString("submit"))}) {
            actions.clear(); SDL_JoystickSetVirtualButton(joystick,button.first,1); input.poll();
            QCOMPARE(actions.size(),1); QCOMPARE(actions.first().at(0).toString(),button.second);
            SDL_JoystickSetVirtualButton(joystick,button.first,0); input.poll();
        }
        SDL_JoystickClose(joystick); QVERIFY(SDL_JoystickDetachVirtual(device) == 0); input.poll();
        QVERIFY(input.deviceName().isEmpty()); QVERIFY(input.buttons().isEmpty()); QCOMPARE(input.axes()[0].toDouble(), 0.);
    }
    void routedControllerEvents() {
        ControllerInput input(nullptr, true);
        QSignalSpy actions(&input, &ControllerInput::action);
        qint32 axes[4]{};
        input.routedState(0, axes);
        QCOMPARE(input.deviceName(), QString("R46H Routed Gamepad"));
        for (const auto &item : {qMakePair(1, QString("accept")), qMakePair(0, QString("back")),
             qMakePair(2, QString("favorite")), qMakePair(3, QString("erase")), qMakePair(9, QString("submit"))}) {
            actions.clear(); input.routedState(1U << item.first, axes);
            QCOMPARE(actions.size(), 1); QCOMPARE(actions.first().at(0).toString(), item.second);
            input.routedState(0, axes);
        }
        actions.clear(); axes[0] = -32767; input.routedState(0, axes);
        QCOMPARE(actions.last().at(0).toString(), QString("left"));
        QCOMPARE(input.axes()[0].toDouble(), -1.);
        QTest::qWait(430); QVERIFY(actions.last().at(1).toBool());
        input.suppressUntilNeutral(); actions.clear();
        input.routedState(1U << 1, axes); QTest::qWait(120); QVERIFY(actions.isEmpty());
        axes[0] = 0; input.routedState(0, axes); input.routedState(1U << 1, axes);
        QCOMPARE(actions.size(), 1); QCOMPARE(actions.first().at(0).toString(), QString("accept"));
        input.routedState(0, axes); actions.clear();
        input.routedState(1U << 6 | 1U << 7, axes);
        QCOMPARE(input.axes()[4].toDouble(), 1.); QCOMPARE(input.axes()[5].toDouble(), 1.);
        QVERIFY(actions.isEmpty());
        input.routedState(0, axes); actions.clear(); axes[0] = 40000;
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
        QCOMPARE(state.fontPercent(), 100); QCOMPARE(state.dimSeconds(), 0); QVERIFY(!state.monitor());
        state.adjust("font", 1); state.adjust("font", 1); state.adjust("font", 1);
        QCOMPARE(state.fontPercent(), 120);
        for (int i = 0; i < 4; ++i) state.adjust("dim", 1);
        QCOMPARE(state.dimSeconds(), 120); state.adjust("monitor", 1); QVERIFY(state.save());
        Preferences loaded(directory.path()); QCOMPARE(loaded.fontPercent(), 120); QVERIFY(loaded.monitor());
        QCOMPARE(loaded.dimSeconds(), 120); QCOMPARE(loaded.volume(), 42);
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
        action("quick"); action("down"); action("down"); action("down"); action("accept");
        QVERIFY(state.monitor()); QVERIFY(metrics.active()); action("accept", true); QVERIFY(state.monitor());
        action("accept"); QVERIFY(!metrics.active()); action("back");
        action("nextTab"); action("nextTab"); action("up");
        QVERIFY(root->property("settingsSidebar").toBool());
        for (int i = 0; i < 9; ++i) action("down");
        QCOMPARE(root->property("settingsCategory").toInt(), 9);
        action("right"); action("accept"); action("down"); action("accept"); QCOMPARE(state.fontPercent(), 110);
        action("down"); action("accept"); QVERIFY(root->property("editing").toBool());
        state.adjust("monitor", 1);
        auto *hud = root->findChild<QQuickItem *>("performancePanel"); QVERIFY(hud);
        QVERIFY(hud->isVisible()); QVERIFY(hud->property("compact").toBool());
        QVERIFY(hud->y() + hud->height() < 183); // Above the input field, away from keys.
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
        QTRY_VERIFY_WITH_TIMEOUT(root->property("dimmed").toBool(), 1000);
        action("accept"); QVERIFY(!root->property("dimmed").toBool()); QVERIFY(!root->property("session").toBool());
        action("accept"); QVERIFY(root->property("session").toBool());
        QTest::qWait(100); QVERIFY(!root->property("dimmed").toBool());
        action("home"); state.adjust("dim", -1); QTest::qWait(100); QVERIFY(!root->property("dimmed").toBool());
        action("nextTab"); action("nextTab"); root->setProperty("settingsCategory", 3); root->setProperty("testingController", true);
        action("back"); action("nextTab"); action("right"); action("left"); QCOMPARE(root->property("page").toInt(), 2);
        QVERIFY(root->property("testingController").toBool());
        action("quick");
        QCOMPARE(root->property("page").toInt(), 2); QVERIFY(!root->property("testingController").toBool());
        QVERIFY(root->property("settingsSidebar").toBool()); QVERIFY(!root->property("quickOpen").toBool());
        action("quick"); QVERIFY(root->property("quickOpen").toBool());
    }
    void applicationManifestAndForegroundLifecycle() {
        QTemporaryDir directory; QVERIFY(directory.isValid());
        QFile manifest(directory.filePath("applications.json"));
        auto write = [&](const QJsonArray &items) {
            QVERIFY(manifest.open(QIODevice::WriteOnly | QIODevice::Truncate));
            manifest.write(QJsonDocument(QJsonObject{{"version", 1}, {"applications", items}}).toJson()); manifest.close();
        };
        const QJsonObject sleeper{{"id", "game-a"}, {"title", "测试应用"}, {"program", "/bin/sleep"}, {"arguments", QJsonArray{"0.1"}}};
        write({sleeper}); Applications apps; QVERIFY(!apps.hasManifest()); QVERIFY(apps.load(manifest.fileName())); QVERIFY(apps.hasManifest()); QCOMPARE(apps.items().size(), 1);
        QSignalSpy ended(&apps, &Applications::finished);
        QVERIFY(apps.launch(0)); QVERIFY(!apps.launch(0));
        QTRY_COMPARE(ended.size(), 1); QVERIFY(!apps.running()); QVERIFY(apps.error().isEmpty()); QCOMPARE(apps.exitCode(), 0);
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
        QVERIFY(state.choose("font", 2));
        action("accept"); // Enter details at Start, then move to the overlay switch.
        root->setProperty("quickIndex", 0); root->setProperty("quickOpen", true);
        action("down"); QCOMPARE(root->property("quickIndex").toInt(), 1);
        action("back"); QVERIFY(!root->property("quickOpen").toBool()); QVERIFY(root->property("streamingOpen").toBool());
        const auto captures = qEnvironmentVariable("R46H_UI_CAPTURE_DIR");
        QTest::qWait(200);
        if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + "/streaming-120.png"));
        action("up"); action("up"); action("accept"); QVERIFY(!manager.current().value("overlay").toBool());
        action("up"); action("accept"); QVERIFY(root->property("choicesOpen").toBool());
        QTest::qWait(200);
        if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + "/streaming-choices-120.png"));
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
        QTRY_COMPARE(outline->y(), qobject_cast<QQuickItem *>(list->property("currentItem").value<QObject *>())->y() - list->property("contentY").toReal());
        if(!captures.isEmpty())QVERIFY(view.grabWindow().save(captures+"/streaming-applications.png"));
        tap("up");tap("accept");QCOMPARE(manager.current().value("application").toString(),QString("Desktop"));
        tap("accept");for(int i=0;i<3;++i)tap("down");tap("accept");QVERIFY(root->property("editing").toBool());tap("back");
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
        for (int percent : {100, 120}) {
            sample->setProperty("fontScale", percent / 100.); QTest::qWait(200);
            if (!captures.isEmpty()) QVERIFY(gallery.grabWindow().save(captures + QString("/controls-%1.png").arg(percent)));
        }
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
        action("right"); action("accept"); QVERIFY(root->property("choicesOpen").toBool());
        action("down"); action("nextTab"); action("home");
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
        QVERIFY(!state.choose("font", 3)); QVERIFY(!state.choose("unknown", 0));
        action("right"); action("accept"); QTest::qWait(200);
        if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + "/settings-choices.png"));
        action("back");
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
        auto *brightness=row(QStringLiteral("屏幕亮度")); QVERIFY(brightness);
        QVERIFY(QMetaObject::invokeMethod(brightness,"click"));
        QCOMPARE(root->property("settingsIndex").toInt(),1); QVERIFY(root->property("settingsAdjusting").toBool());
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
        QVERIFY(device.applyCpu("performance",816000,1200000));QCOMPARE(get(cpu+"scaling_governor"),QByteArray("performance"));
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
        QCOMPARE(root->findChild<QObject *>("statusWifi")->property("text").toString(),QStringLiteral("79%"));
        QCOMPARE(root->findChild<QObject *>("statusBattery")->property("text").toString(),QStringLiteral("86% · 充电"));
        if(!qEnvironmentVariable("R46H_UI_CAPTURE_DIR").isEmpty())QVERIFY(view.grabWindow().save(qEnvironmentVariable("R46H_UI_CAPTURE_DIR")+"/device-status.png"));
        QVERIFY(QMetaObject::invokeMethod(root,"showScene",Q_ARG(QVariant,QString("power"))));tap("right");tap("down");tap("down");tap("accept");
        QVERIFY(root->property("choicesOpen").toBool());tap("accept");QCOMPARE(power.size(),1); // Default is cancel.
        tap("accept");tap("down");tap("accept");QCOMPARE(power.size(),2); // Confirmation emits only a test signal.
        root->setProperty("settingsCategory",10);root->setProperty("settingsIndex",0);tap("accept");tap("down");tap("down");tap("accept");
        QCOMPARE(get(cpu+"scaling_governor"),QByteArray("performance"));
        const auto captures=qEnvironmentVariable("R46H_UI_CAPTURE_DIR");QTest::qWait(200);
        if(!captures.isEmpty())QVERIFY(view.grabWindow().save(captures+"/device-cpu.png"));
        QVERIFY(device.cpuPreset("original"));
        QCOMPARE(device.info().value("socTemperatureC").toDouble(),55.);
        QVERIFY(state.choose("font",2));state.adjust("monitor",1);root->setProperty("testInputCapture",true);
        QVERIFY(QMetaObject::invokeMethod(root,"openEditor"));
        auto *hud=root->findChild<QQuickItem *>("performancePanel");QVERIFY(hud);
        QCOMPARE(hud->height(),150.);QVERIFY(hud->y()+hud->height()<183);
        QVERIFY(hud->findChild<QObject *>("hudMemory")->property("text").toString().contains("768.0 / 1024.0"));
        QVERIFY(hud->findChild<QObject *>("hudTemperature")->property("text").toString().contains("55.0"));
        QVERIFY(hud->property("thermalStatus").toString().contains(QStringLiteral("未介入")));
        put("sys/class/thermal/cooling_device0/cur_state","1");device.refresh();
        QVERIFY(hud->property("thermalStatus").toString().contains(QStringLiteral("CPU 温控限频")));
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
        QFile program(directory.filePath("nmcli-fixture"));QVERIFY(program.open(QIODevice::WriteOnly));
        program.write("#!/bin/sh\ncase \"$*\" in *\"device wifi list\"*) cat \"$0.scan\";; *\"connection delete\"*) printf '%s\\n' \"$@\" > \"$0.deleted\";; *) printf '%s\\n' '11111111-2222-4333-8444-555555555555:wifi:Saved:wlan0';; esac\n");program.close();
        QVERIFY(program.setPermissions(QFile::ReadOwner|QFile::WriteOwner|QFile::ExeOwner));
        QFile scan(program.fileName()+".scan");QVERIFY(scan.open(QIODevice::WriteOnly));
        scan.write("/org/freedesktop/NetworkManager/AccessPoint/1:AA\\:BB\\:CC\\:DD\\:EE\\:FF:Studio\\:5G:80:WPA2:wlan0:*\n");scan.close();
        NetworkState network(true,true,program.fileName());QTRY_VERIFY(!network.busy());
        QQuickView view;view.setInitialProperties({{"store",QVariant::fromValue(&state)},{"metrics",QVariant::fromValue(&metrics)},
            {"controller",QVariant::fromValue(&controller)},{"device",QVariant::fromValue(&device)},{"network",QVariant::fromValue(&network)}, {"testInputCapture",true}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/ShellView.qml")));QCOMPARE(view.status(),QQuickView::Ready);
        view.resize(1024,768);view.show();QVERIFY(QTest::qWaitForWindowExposed(&view));auto *root=view.rootObject();
        auto tap=[&](const char *key){QVERIFY(QMetaObject::invokeMethod(root,"dispatch",Q_ARG(QVariant,QString(key)),Q_ARG(QVariant,false)));};
        QVERIFY(QMetaObject::invokeMethod(root,"showScene",Q_ARG(QVariant,QString("settings"))));tap("down");tap("right");tap("accept");
        QTRY_VERIFY(root->property("choicesOpen").toBool());QCOMPARE(network.accessPoints().size(),1);
        const auto captures=qEnvironmentVariable("R46H_UI_CAPTURE_DIR");QTest::qWait(200);
        if(!captures.isEmpty())QVERIFY(view.grabWindow().save(captures+"/wifi-chooser.png"));
        tap("accept");QVERIFY(root->property("editing").toBool());QVERIFY(root->property("sensitiveVisible").toBool());
        QVERIFY(!root->property("testInputVisible").toBool());
        auto *field=root->findChild<QQuickItem *>("inputField");QVERIFY(field);
        QCOMPARE(field->property("echoMode").toInt(),2); // TextInput.Password.
        QCOMPARE(field->property("maximumLength").toInt(),64);
        QVERIFY(field->property("inputMethodHints").toInt()&Qt::ImhHiddenText);
        QVERIFY(field->property("inputMethodHints").toInt()&Qt::ImhNoAutoUppercase);
        field->setProperty("text","fixture-password");QVERIFY(QMetaObject::invokeMethod(root,"finishEditor"));
        QVERIFY(root->property("editing").toBool()); // No fixture bus; refusal keeps the edit available.
        tap("back");QVERIFY(!root->property("editing").toBool());QVERIFY(field->property("text").toString().isEmpty());
        tap("down");tap("down");tap("accept");QVERIFY(network.remember());
        tap("down");tap("down");tap("accept");tap("accept");QVERIFY(root->property("choicesOpen").toBool());
        tap("accept");QVERIFY(!QFileInfo::exists(program.fileName()+".deleted")); // Cancel is the default.
        tap("accept");tap("accept");tap("down");tap("accept");QTRY_VERIFY(!network.busy());
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
        QCOMPARE(QQmlProperty(keyboard, "style.navigationHighlightColor").read().value<QColor>(), QColor("#99efdb"));
        state.adjust("motion", 1); QVERIFY(keyboard->property("noAnimations").toBool());
        state.adjust("motion", 1); QVERIFY(!keyboard->property("noAnimations").toBool());
        auto *field = root->findChild<QQuickItem *>("inputField"); QVERIFY(field);
        QTRY_VERIFY(field->hasActiveFocus()); QTest::qWait(200);
        // The same focus-object events sent by SDL must navigate Qt's own keys.
        controller.keyboardAction("down"); controller.keyboardAction("accept");
        QTRY_VERIFY(!field->property("text").toString().isEmpty());
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
        field->setProperty("text",QStringLiteral("ab中")); field->setProperty("cursorPosition",3);
        QVERIFY(QMetaObject::invokeMethod(root,"dispatch",Q_ARG(QVariant,QString("erase")),Q_ARG(QVariant,false)));
        QCOMPARE(field->property("text").toString(),QString("ab"));
        QQmlComponent ime(view.engine());
        ime.setData(R"(import QtQuick
            import QtQuick.VirtualKeyboard
            import QtQuick.VirtualKeyboard.Settings
            QtObject {
                property bool chineseAvailable: VirtualKeyboardSettings.availableLocales.indexOf("zh_CN") >= 0
                property int candidates: InputContext.inputEngine.wordCandidateListModel.count
                function chinese() { VirtualKeyboardSettings.locale = "zh_CN" }
                function typePinyin() {
                    InputContext.inputEngine.virtualKeyClick(Qt.Key_N, "n", Qt.NoModifier)
                    InputContext.inputEngine.virtualKeyClick(Qt.Key_I, "i", Qt.NoModifier)
                }
                function commitFirst() { InputContext.inputEngine.wordCandidateListModel.selectItem(0) }
            })", QUrl());
        QScopedPointer<QObject> inputMethod(ime.create()); QVERIFY2(inputMethod, qPrintable(ime.errorString()));
        QVERIFY(inputMethod->property("chineseAvailable").toBool());
        field->setProperty("text", ""); QVERIFY(QMetaObject::invokeMethod(inputMethod.data(), "chinese"));
        QTest::qWait(100); QVERIFY(QMetaObject::invokeMethod(inputMethod.data(), "typePinyin"));
        QTRY_VERIFY(inputMethod->property("candidates").toInt() > 0);
        QVERIFY(QMetaObject::invokeMethod(inputMethod.data(), "commitFirst"));
        QTRY_VERIFY(!field->property("text").toString().isEmpty());
        QVERIFY(field->property("text").toString().front().unicode() > 127);
        state.adjust("font", 1); state.adjust("font", 1); state.adjust("monitor", 1);
        QTest::qWait(200);
        const auto captures = qEnvironmentVariable("R46H_UI_CAPTURE_DIR");
        if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + "/arm64-keyboard-pinyin-120.png"));
        QObject *hideKey = nullptr;
        for (auto *item : root->findChildren<QObject *>()) {
            if (QByteArray(item->metaObject()->className()).startsWith("HideKeyboardKey")) { hideKey = item; break; }
        }
        QVERIFY(hideKey); QVERIFY(QMetaObject::invokeMethod(hideKey, "clicked"));
        QTRY_VERIFY(!root->property("editing").toBool());
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
        controller.keyboardAction("down"); controller.keyboardAction("accept");
        QTRY_VERIFY(!field->property("text").toString().isEmpty());
        QVERIFY(QMetaObject::invokeMethod(root, "dispatch", Q_ARG(QVariant, QString("submit")), Q_ARG(QVariant, false)));
        QVERIFY(!root->property("editing").toBool()); QVERIFY(field->property("text").toString().isEmpty());
    }
};
QTEST_MAIN(ShellCheck)
#include "check.moc"
