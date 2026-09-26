#pragma once
#include <QImage>
#include <QString>

struct OutputCapture { QImage image; QString error; };
// Call off the GUI thread. The private Weston policy must authorize this process.
OutputCapture captureOutput(int timeoutMs = 1500, qint64 expectedCompositor = 0);
// Private, UI-owner-only readback of the last foreground surface, never the output.
OutputCapture captureTask(const QString &socketPath, qint64 compositor, qint64 pid, quint64 surface);
