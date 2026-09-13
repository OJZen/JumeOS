#include "usbgamepad.h"
#include <QtMath>
#include <cmath>

QByteArray UsbGamepad::descriptor() {
    // Report 1: 16 buttons, hat + padding, X/Y/Rx/Ry int16, Z/Rz uint8 (14 bytes).
    return QByteArray::fromHex(
        "05010905a101850105091901291015002501750195108102"
        "05010939150025073500463b01651475049501814275049501810365003500460000"
        "0501093009310933093416018026ff7f751095048102"
        "09320935150026ff00750895028102c0");
}
QByteArray UsbGamepad::report(const QVariantList &axes, quint16 buttons, quint8 directions, const QVariantMap &settings) {
    auto swap = [&](int a, int b) { if (((buttons >> a) ^ (buttons >> b)) & 1) buttons ^= (1 << a) | (1 << b); };
    if (settings.value("usbSwapAB").toBool()) swap(0, 1);
    if (settings.value("usbSwapXY").toBool()) swap(2, 3);
    const int x = int(bool(directions & 2)) - int(bool(directions & 8));
    const int y = int(bool(directions & 4)) - int(bool(directions & 1));
    const int hat = x == 0 && y == 0 ? 8 : y < 0 ? (x < 0 ? 7 : x > 0 ? 1 : 0) : y > 0 ? (x < 0 ? 5 : x > 0 ? 3 : 4) : x > 0 ? 2 : 6;
    QByteArray out; out.append(char(1)); out.append(char(buttons & 255)); out.append(char(buttons >> 8)); out.append(char(hat));
    const double deadzone = qBound(0, settings.value("usbDeadzone", 10).toInt(), 30) / 100.;
    for (int i = 0; i < 6; ++i) {
        double v = axes.value(i).toDouble(); if (!std::isfinite(v)) v = 0;
        if (i < 4) {
            v = qBound(-1., v, 1.);
            v = std::abs(v) <= deadzone ? 0 : std::copysign((std::abs(v) - deadzone) / (1. - deadzone), v);
            if (i == 3 && settings.value("usbInvertRightY").toBool()) v = -v;
            const auto value = quint16(qint16(qRound(v * 32767.)));
            out.append(char(value & 255)); out.append(char(value >> 8));
        } else out.append(char(qRound(qBound(0., v, 1.) * 255.)));
    }
    return out;
}
