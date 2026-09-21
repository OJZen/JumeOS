#include "browserinput.h"
#include <QtTest>
#include <QSignalSpy>
#include <QMouseEvent>
#include <limits>

class Window : public QQuickWindow {
public:
    int presses = 0, releases = 0, moves = 0, wheels = 0;
    QPointF releasePosition;
    bool event(QEvent *e) override {
        if (e->type() == QEvent::MouseButtonPress) ++presses;
        if (e->type() == QEvent::MouseButtonRelease) { ++releases; releasePosition = static_cast<QMouseEvent *>(e)->position(); }
        if (e->type() == QEvent::MouseMove) ++moves;
        if (e->type() == QEvent::Wheel) ++wheels;
        return QQuickWindow::event(e);
    }
};
class Check : public QObject {
    Q_OBJECT
private slots:
    void controls() {
        Window window; window.resize(1024, 768);
        ControllerInput controller(nullptr, true); BrowserInput input(&window, &controller);
        QSignalSpy actions(&input, &BrowserInput::action);
        const QVariantList zero{0.,0.,0.,0.};
        input.sample(zero, {"b"}, .016, true); QCOMPARE(window.presses, 0);
        input.sample(zero, {}, .016, true);
        input.sample(zero, {"b"}, .016, true); QCOMPARE(window.presses, 1);
        input.sample(zero, {"b"}, .016, true); QCOMPARE(window.presses, 1);
        input.sample({0.,0.,1.,1.}, {"b"}, 30., true);
        QVERIFY(input.position().x() <= 512 + 850 * .05); QCOMPARE(window.moves, 1);
        input.sample(zero, {}, .016, false); QCOMPARE(window.releases, 1);
        QVERIFY(window.releasePosition.x() < 0); // Focus loss cancels, not a click behind the panel.
        input.sample(zero, {"a"}, .016, true); QCOMPARE(actions.size(), 0);
        input.sample(zero, {}, .016, true);
        for (const auto &pair : QList<QPair<QString,QString>>{{"a","forward"},{"y","back"},{"x","reload"},{"start","address"},{"back","keyboard"},{"leftshoulder","previousTab"},{"rightshoulder","nextTab"}}) {
            input.sample(zero, {pair.first}, .016, true);
            QCOMPARE(actions.takeFirst().at(0).toString(), pair.second);
            input.sample(zero, {pair.first}, .016, true); QVERIFY(actions.empty());
            input.sample(zero, {}, .016, true);
        }
        input.sample({1.,1.,0.,0.}, {}, .016, true); QCOMPARE(window.wheels, 1);
        const auto point = input.position();
        input.sample({.17,-.17,.17,-.17}, {}, .016, true); QCOMPARE(input.position(), point); QCOMPARE(window.wheels, 1);
        input.setKeyboard(true); input.sample(zero, {}, .016, true);
        input.sample(zero, {"b"}, .016, true); QCOMPARE(actions.takeFirst().at(0).toString(), "accept"); QCOMPARE(window.presses, 1);
        input.sample(zero, {"x"}, .016, true); QCOMPARE(actions.takeFirst().at(0).toString(), "erase");
        input.sample(zero, {"y"}, .016, true); QCOMPARE(actions.takeFirst().at(0).toString(), "dismiss");
        input.sample(zero, {"a"}, .016, true); QVERIFY(actions.empty());
        QCOMPARE(BrowserInput::speed(std::numeric_limits<double>::quiet_NaN()), 0.);
        QCOMPARE(BrowserInput::speed(-1.), -1.);
        QCOMPARE(BrowserInput::speed(99.), 1.);
    }
    void addresses() {
        Window window; ControllerInput controller(nullptr, true); BrowserInput input(&window, &controller);
        QCOMPARE(input.address(" example.com "), QUrl("https://example.com"));
        QCOMPARE(input.address("https://example.com/path"), QUrl("https://example.com/path"));
        QCOMPARE(input.address("hello world").host(), "duckduckgo.com");
        for (const auto *url : {"file:///etc/passwd", "javascript:alert(1)", "data:text/html,test", "mailto:x@y.com", "https://user:pass@example.com", "chrome://settings", "https:///"}) QVERIFY2(!BrowserInput::allowed(QUrl(url)), url);
        for (const auto *url : {"http://localhost:8000/", "https://example.com", "chrome://gpu", "chrome://gpu/", "about:blank"}) QVERIFY2(BrowserInput::allowed(QUrl(url)), url);
        QVERIFY(input.address("file:///etc/passwd").isEmpty());
        QVERIFY(input.address(" ").isEmpty());
    }
};
QTEST_MAIN(Check)
#include "check.moc"
