// Test-only screenshot of the dedicated Xvfb display; never the user's desktop.
#include <QGuiApplication>
#include <QScreen>
#include <QPixmap>
#include <QFileInfo>

int main(int argc, char **argv)
{
    if ((argc != 2 && argc != 3) || !QFileInfo::exists("/.dockerenv"))
        return 2;
    qputenv("QT_QPA_PLATFORM", "xcb");
    QGuiApplication app(argc, argv);
    auto *screen = app.primaryScreen();
    if (!screen || screen->size().width() > 2048 || screen->size().height() > 2048)
        return 2;
    const auto frame = screen->grabWindow(0);
    if (frame.isNull() || !frame.save(QString::fromLocal8Bit(argv[1]), "PNG")) return 1;
    if (argc == 3) {
        const auto pixel = frame.toImage().pixelColor(frame.width()/2, frame.height()/2);
        const auto expected = QByteArray(argv[2]);
        if (expected == "green") return pixel.green() > pixel.red()*2 && pixel.green() > pixel.blue()*1.4 ? 0 : 4;
        if (expected == "blue") return pixel.blue() > pixel.green()*2 && pixel.blue() > pixel.red()*2 ? 0 : 4;
        return 2;
    }
    return 0;
}
