#include "transfer.h"
#include <QtWidgets>
#include <qrencode.h>
#include <memory>

QImage transferQr(const QString &url) {
    const auto bytes = url.toUtf8();
    std::unique_ptr<QRcode, decltype(&QRcode_free)> code(QRcode_encodeString8bit(bytes.constData(), 0, QR_ECLEVEL_M),
                                                         QRcode_free);
    if (!code)
        return {};
    const int scale = qMax(1, 224 / (code->width + 8));
    QImage image((code->width + 8) * scale, (code->width + 8) * scale, QImage::Format_RGB32);
    image.fill(Qt::white);
    QPainter painter(&image);
    for (int y = 0; y < code->width; ++y)
        for (int x = 0; x < code->width; ++x)
            if (code->data[y * code->width + x] & 1)
                painter.fillRect((x + 4) * scale, (y + 4) * scale, scale, scale, Qt::black);
    return image;
}

TransferWindow::TransferWindow(QString directory) : root(std::move(directory)) {
    setWindowTitle("Jume Transfer");
    resize(640, 480);
    helper = QCoreApplication::applicationDirPath() + "/../share/jume-files/transfer_server.py";
    auto *layout = new QVBoxLayout(this);
    layout->setContentsMargins(16, 12, 16, 12);
    layout->setSpacing(8);
    auto *header = new QHBoxLayout;
    auto *title = new QLabel("文件传输");
    title->setObjectName("heading");
    header->addWidget(title);
    header->addStretch();
    auto *close = new QPushButton("关闭");
    header->addWidget(close);
    connect(close, &QPushButton::clicked, this, &QWidget::close);
    layout->addLayout(header);
    status = new QLabel("正在检查 Wi-Fi…");
    status->setTextFormat(Qt::PlainText);
    status->setObjectName("transferStatus");
    layout->addWidget(status);
    auto *center = new QHBoxLayout;
    qr = new QLabel("连接 Wi-Fi 后开启共享");
    qr->setObjectName("transferQr");
    qr->setAlignment(Qt::AlignCenter);
    qr->setFixedSize(232, 232);
    center->addWidget(qr);
    auto *instructions = new QVBoxLayout;
    auto *steps = new QLabel("1  其他设备连接同一 Wi-Fi\n2  扫描二维码，或打开下方地址\n3  在网页上传、浏览或下载");
    steps->setWordWrap(true);
    instructions->addWidget(steps);
    pairingCode = new QLabel("连接码：—");
    pairingCode->setObjectName("pairingCode");
    instructions->addWidget(pairingCode);
    start = new QPushButton("开启共享");
    start->setObjectName("startTransfer");
    start->setEnabled(false);
    instructions->addWidget(start);
    copy = new QPushButton("复制授权链接");
    copy->setEnabled(false);
    instructions->addWidget(copy);
    center->addLayout(instructions, 1);
    layout->addLayout(center);
    address = new QLineEdit;
    address->setReadOnly(true);
    address->setAccessibleName("本地传输地址");
    address->setPlaceholderText("仅连接 Wi-Fi 后可用");
    layout->addWidget(address);
    auto *folderRow = new QHBoxLayout;
    folder = new QLabel;
    folder->setTextFormat(Qt::PlainText);
    folder->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Preferred);
    folder->setToolTip(root);
    folderRow->addWidget(folder, 1);
    choose = new QPushButton("选择目录");
    folderRow->addWidget(choose);
    layout->addLayout(folderRow);
    folder->setText("共享：" + QFontMetrics(font()).elidedText(root, Qt::ElideMiddle, 420));
    activity = new QLabel("不会覆盖同名文件。仅共享所选目录，退出应用即停止。");
    activity->setTextFormat(Qt::PlainText);
    activity->setWordWrap(true);
    activity->setObjectName("caption");
    layout->addWidget(activity);
    auto *warning = new QLabel("HTTP 明文 · 仅用于可信 Wi-Fi · 请勿传输敏感文件 · 2 小时自动停止");
    warning->setWordWrap(true);
    warning->setObjectName("caption");
    layout->addWidget(warning);
    auto environment = QProcessEnvironment::systemEnvironment();
    for (const auto *key : {"PYTHONHOME", "PYTHONPATH", "LD_LIBRARY_PATH", "QT_PLUGIN_PATH"})
        environment.remove(key);
    probe.setProcessEnvironment(environment);
    server.setProcessEnvironment(environment);
    probe.setStandardErrorFile(QProcess::nullDevice());
    server.setStandardErrorFile(QProcess::nullDevice());
    connect(&probe, &QProcess::finished, this, [this] {
        const auto data = QJsonDocument::fromJson(probe.readAllStandardOutput()).object();
        connected = data.value("connected").toBool();
        if (server.state() == QProcess::NotRunning && !closing) {
            start->setEnabled(connected);
            status->setText(connected ? "Wi-Fi 已连接 · " + data.value("address").toString()
                                      : "未连接 Wi-Fi，或尚未取得 IPv4 地址");
        }
    });
    connect(&probe, &QProcess::errorOccurred, this, [this] {
        connected = false;
        start->setEnabled(false);
        status->setText("无法检查 Wi-Fi，请检查 Python / NetworkManager。");
    });
    connect(&server, &QProcess::readyReadStandardOutput, this, &TransferWindow::consume);
    connect(&server, &QProcess::finished, this, [this] {
        deadline.stop();
        shareLink.clear();
        address->clear();
        qr->clear();
        qr->setText("共享已停止");
        pairingCode->setText("连接码：—");
        copy->setEnabled(false);
        choose->setEnabled(true);
        start->setText("开启共享");
        start->setEnabled(false);
        status->setText("共享已停止，旧链接与连接码已失效");
        stopping = false;
        if (closing)
            QTimer::singleShot(0, this, &QWidget::close);
        else
            probeWifi();
    });
    connect(&server, &QProcess::errorOccurred, this, [this] {
        if (server.error() == QProcess::FailedToStart) {
            start->setEnabled(connected);
            choose->setEnabled(true);
            status->setText("无法启动传输服务，请检查运行时安装。");
        }
    });
    connect(start, &QPushButton::clicked, this, [this] {
        if (server.state() != QProcess::NotRunning) {
            stop();
            return;
        }
        if (!connected)
            return;
        if (!QDir().mkpath(root)) {
            status->setText("无法创建共享目录，请选择可用位置。");
            return;
        }
        stopping = false;
        pending.clear();
        choose->setEnabled(false);
        start->setEnabled(false);
        status->setText("正在核验 Wi-Fi 并启动临时共享…");
        server.start("/usr/bin/python3", {"-I", "-B", helper, "--root", root});
    });
    connect(copy, &QPushButton::clicked, this, [this] {
        if (!shareLink.isEmpty())
            QApplication::clipboard()->setText(shareLink);
    });
    connect(choose, &QPushButton::clicked, this, [this] {
        const auto selected =
            QFileDialog::getExistingDirectory(this, "选择专用共享目录（不共享整个用户目录）", root,
                                              QFileDialog::ShowDirsOnly | QFileDialog::DontUseNativeDialog);
        if (!selected.isEmpty()) {
            root = selected;
            folder->setText("共享：" + QFontMetrics(font()).elidedText(root, Qt::ElideMiddle, 420));
            folder->setToolTip(root);
        }
    });
    deadline.setSingleShot(true);
    connect(&deadline, &QTimer::timeout, this, [this] {
        if (server.state() != QProcess::NotRunning)
            server.kill();
    });
    refresh.setInterval(2000);
    connect(&refresh, &QTimer::timeout, this, &TransferWindow::probeWifi);
    refresh.start();
    probeWifi();
}
TransferWindow::~TransferWindow() {
    closing = true;
    refresh.stop();
    deadline.stop();
    probe.kill();
    probe.waitForFinished(500);
    if (server.state() != QProcess::NotRunning) {
        server.write("stop\n");
        server.closeWriteChannel();
        if (!server.waitForFinished(1500)) {
            server.kill();
            server.waitForFinished(500);
        }
    }
}
void TransferWindow::probeWifi() {
    if (!closing && server.state() == QProcess::NotRunning && probe.state() == QProcess::NotRunning)
        probe.start("/usr/bin/python3", {"-I", "-B", helper, "--probe"});
}
void TransferWindow::stop() {
    stopping = true;
    shareLink.clear();
    copy->setEnabled(false);
    start->setEnabled(false);
    address->clear();
    qr->clear();
    qr->setText("正在停止…");
    pairingCode->setText("连接码：—");
    status->setText("正在关闭连接并清理未完成上传…");
    server.write("stop\n");
    server.closeWriteChannel();
    deadline.start(5000);
}
void TransferWindow::consume() {
    pending += server.readAllStandardOutput();
    if (pending.size() > 16384) {
        stop();
        pending.clear();
        return;
    }
    while (pending.contains('\n')) {
        const auto end = pending.indexOf('\n');
        const auto data = QJsonDocument::fromJson(pending.left(end)).object();
        pending.remove(0, end + 1);
        const auto state = data.value("state").toString();
        if (stopping)
            continue;
        if (state == "ready") {
            shareLink = data.value("link").toString();
            address->setText(data.value("url").toString());
            pairingCode->setText("连接码：" + data.value("code").toString());
            qr->setPixmap(QPixmap::fromImage(transferQr(shareLink)));
            start->setEnabled(true);
            start->setText("停止共享");
            copy->setEnabled(true);
            status->setText("共享中 · 只允许同一 Wi-Fi 网段连接");
        } else if (state == "error" || state == "stopped") {
            activity->setText(data.value("message").toString());
            shareLink.clear();
            qr->clear();
            address->clear();
            copy->setEnabled(false);
            pairingCode->setText("连接码：—");
        } else if (state == "progress" || state == "complete") {
            const auto label = data.value("direction").toString() == "upload" ? "上传" : "下载";
            activity->setText(state == "complete"
                                  ? QString(label) + "完成"
                                  : QString("%1 · %2 / %3")
                                        .arg(label, QLocale().formattedDataSize(qint64(data.value("done").toDouble())),
                                             QLocale().formattedDataSize(qint64(data.value("total").toDouble()))));
        }
    }
}
void TransferWindow::closeEvent(QCloseEvent *event) {
    if (server.state() != QProcess::NotRunning) {
        closing = true;
        stop();
        event->ignore();
    } else
        event->accept();
}
void TransferWindow::controllerAction(const QString &action) {
    if (QApplication::activeModalWidget()) {
        auto *focus = QApplication::focusWidget();
        if (!focus)
            return;
        const int key = action == "back"     ? Qt::Key_Escape
                        : action == "accept" ? Qt::Key_Return
                        : action == "up"     ? Qt::Key_Up
                        : action == "down"   ? Qt::Key_Down
                                             : 0;
        if (key) {
            QKeyEvent event(QEvent::KeyPress, key, Qt::NoModifier);
            QApplication::sendEvent(focus, &event);
        }
        return;
    }
    if (action == "back")
        close();
    else if (action == "accept")
        start->click();
    else if (action == "favorite" && choose->isEnabled())
        choose->click();
}
