#include "stickcalibration.h"
#include "fonts.h"
#include <QtTest>
#include <QTemporaryDir>
#include <QFile>
#include <QQuickView>
#include <QQuickItem>
#include <QSignalSpy>

class CalibrationChecks : public QObject {
    Q_OBJECT
    const std::array<qint32, 4> center{{500, -700, 1000, -500}};
    const std::array<qint32, 4> low{{-23000, -26000, -21000, -24500}};
    const std::array<qint32, 4> high{{29000, 24000, 27000, 22000}};
    void centered(StickCalibration &calibration) {
        calibration.observe(center.data());
        for (int i = 0; i < 30; ++i) calibration.sampleCenter();
    }
    void review(StickCalibration &calibration) {
        QVERIFY(calibration.begin()); centered(calibration); QVERIFY(calibration.advance());
        calibration.observe(low.data()); calibration.observe(high.data()); QVERIFY(calibration.advance());
        QCOMPARE(calibration.phase(), 3);
    }
private slots:
    void asymmetricRangesAndClamping() {
        Stick::Axis axis{-23000, 500, 29000}; QVERIFY(axis.valid());
        QCOMPARE(axis.apply(-23000), -32767); QCOMPARE(axis.apply(500), 0); QCOMPARE(axis.apply(29000), 32767);
        QCOMPARE(axis.apply(-32767), -32767); QCOMPARE(axis.apply(32767), 32767);
        int previous = -32767;
        for (int x = -32767; x <= 32767; ++x) { const int value = axis.apply(x); QVERIFY(value >= previous); previous = value; }
        QVERIFY(!(Stick::Axis{-2000, 0, 2000}).valid());
        QVERIFY(!(Stick::Axis{-32767, 9000, 32767}).valid());
        QCOMPARE(Stick::native(-32767, 0, 1023), 0); QCOMPARE(Stick::native(0, 0, 1023), 511);
        QCOMPARE(Stick::native(32767, 0, 1023), 1023);
    }
    void unstableAndIncompleteCaptureNeverSaves() {
        QTemporaryDir dir; StickCalibration calibration; calibration.load(dir.path()); calibration.setAvailable(true);
        QSignalSpy requests(&calibration, &StickCalibration::configurationRequested);
        QVERIFY(calibration.begin()); QVERIFY(!calibration.advance());
        for (int n = 0; n < 30; ++n) { const qint32 raw[]{n % 2 ? 5000 : -5000, 0, 0, 0}; calibration.observe(raw); calibration.sampleCenter(); }
        QVERIFY(!calibration.canAdvance());
        centered(calibration); QVERIFY(calibration.advance());
        calibration.observe(low.data()); QVERIFY(!calibration.advance());
        QCOMPARE(requests.size(), 0); QVERIFY(!QFile::exists(dir.filePath("stick-calibration.json")));
        calibration.cancel(); QCOMPARE(calibration.phase(), 0);
    }
    void capturePersistsAppliesAndResets() {
        QTemporaryDir dir; StickCalibration calibration; calibration.load(dir.path()); calibration.setAvailable(true);
        QSignalSpy requests(&calibration, &StickCalibration::configurationRequested);
        review(calibration);
        QCOMPARE(calibration.previewAxes()[0].toDouble(), 1.); QVERIFY(!calibration.advance());
        calibration.observe(center.data()); QVERIFY(calibration.advance());
        QVERIFY(calibration.busy()); QVERIFY(calibration.configured()); QCOMPARE(requests.size(), 1);
        calibration.applied(true); QVERIFY(!calibration.busy()); QVERIFY(!calibration.needsApply());
        StickCalibration restored; restored.load(dir.path()); QVERIFY(restored.configured());
        restored.observe(low.data()); QCOMPARE(restored.previewAxes()[0].toDouble(), -1.);
        restored.setAvailable(true); QVERIFY(restored.confirmReset()); QVERIFY(restored.advance());
        QVERIFY(!restored.configured()); restored.applied(true);
        StickCalibration defaults; defaults.load(dir.path()); QVERIFY(!defaults.configured());
    }
    void cancelDisconnectAndSaveErrorPreserveProfile() {
        QTemporaryDir dir; StickCalibration calibration; calibration.load(dir.path()); calibration.setAvailable(true);
        review(calibration); calibration.observe(center.data()); QVERIFY(calibration.advance()); calibration.applied(true);
        QFile saved(dir.filePath("stick-calibration.json")); QVERIFY(saved.open(QIODevice::ReadOnly)); const auto before = saved.readAll(); saved.close();
        review(calibration); calibration.setAvailable(false); QVERIFY(!calibration.active()); QVERIFY(!calibration.advance());
        QVERIFY(saved.open(QIODevice::ReadOnly)); QCOMPARE(saved.readAll(), before); saved.close();
        StickCalibration failed; failed.load(dir.filePath("missing/parent")); failed.setAvailable(true);
        QSignalSpy requests(&failed, &StickCalibration::configurationRequested);
        review(failed); failed.observe(center.data()); QVERIFY(!failed.advance()); QCOMPARE(requests.size(), 0); QVERIFY(!failed.configured());
        QVERIFY(saved.open(QIODevice::ReadOnly)); QCOMPARE(saved.readAll(), before);
    }
    void malformedFileIsKeptUntilExplicitReset() {
        QTemporaryDir dir; QFile file(dir.filePath("stick-calibration.json")); QVERIFY(file.open(QIODevice::WriteOnly)); file.write("broken"); file.close();
        StickCalibration calibration; calibration.load(dir.path()); QVERIFY(!calibration.error().isEmpty()); QVERIFY(!calibration.configured());
        QVERIFY(file.open(QIODevice::ReadOnly)); QCOMPARE(file.readAll(), QByteArray("broken")); file.close();
        calibration.setAvailable(true); QVERIFY(calibration.confirmReset()); QVERIFY(calibration.advance());
        StickCalibration restored; restored.load(dir.path()); QVERIFY(restored.error().isEmpty()); QVERIFY(!restored.configured());
    }
    void calibrationPageFitsLargeText() {
        QTest::failOnWarning(QRegularExpression(".*(TypeError|ReferenceError|Binding loop|Unable to assign).*"));
        registerInterfaceFonts();
        QTemporaryDir dir; StickCalibration calibration; calibration.load(dir.path()); calibration.setAvailable(true);
        QQuickView view; view.setResizeMode(QQuickView::SizeRootObjectToView);
        view.setInitialProperties({{"calibration", QVariant::fromValue(&calibration)}, {"fontScale", 1.3}});
        view.setSource(QUrl::fromLocalFile(QStringLiteral(SHELL_SOURCE_DIR "/StickCalibrationView.qml")));
        QVERIFY2(view.status() == QQuickView::Ready, qPrintable(view.errors().isEmpty() ? QString() : view.errors().first().toString()));
        view.resize(944, 592); view.show(); QVERIFY(QTest::qWaitForWindowExposed(&view));
        QVERIFY(calibration.begin()); centered(calibration); QVERIFY(calibration.advance());
        calibration.observe(low.data()); calibration.observe(high.data()); QTest::qWait(100);
        auto *status = view.rootObject()->findChild<QQuickItem *>("calibrationStatus"); QVERIFY(status);
        QVERIFY(status->mapToItem(view.rootObject(), QPointF(0, status->height())).y() <= view.height());
        const auto captures = qEnvironmentVariable("R46H_UI_CAPTURE_DIR");
        if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + "/calibration-range-130.png"));
        QVERIFY(calibration.advance()); calibration.observe(center.data()); QTest::qWait(100);
        if (!captures.isEmpty()) QVERIFY(view.grabWindow().save(captures + "/calibration-review-130.png"));
    }
};
QTEST_MAIN(CalibrationChecks)
#include "calibration-check.moc"
