#pragma once
#include <QWidget>
#include <QProcess>
#include <QTimer>
#include <QImage>
class QLabel;
class QPushButton;
class QLineEdit;
QImage transferQr(const QString &url);
class TransferWindow final : public QWidget {
    Q_OBJECT
    friend class Check;

  public:
    explicit TransferWindow(QString directory);
    ~TransferWindow() override;
    void controllerAction(const QString &action);

  protected:
    void closeEvent(QCloseEvent *event) override;

  private:
    void probeWifi();
    void stop();
    void consume();
    QString root, helper, shareLink;
    QByteArray pending;
    QProcess probe, server;
    QTimer refresh, deadline;
    QLabel *status, *qr, *folder, *pairingCode, *activity;
    QLineEdit *address;
    QPushButton *start, *choose, *copy;
    bool connected = false, closing = false, stopping = false;
};
