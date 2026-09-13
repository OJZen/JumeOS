#pragma once
#include <QByteArray>
#include <QVariantList>
#include <QVariantMap>

// Offline HID profile/packet preparation. This never opens or binds a USB device.
namespace UsbGamepad {
QByteArray descriptor();
// Axes: LX/LY/RX/RY in [-1,1], LT/RT in [0,1]; directions: U/R/D/L bits 1/2/4/8.
QByteArray report(const QVariantList &axes, quint16 buttons, quint8 directions, const QVariantMap &settings);
}
