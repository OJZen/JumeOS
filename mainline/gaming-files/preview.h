#pragma once
#include "operations.h"
#include <QDialog>
class QPlainTextEdit;
class QCloseEvent;

class Preview final : public QDialog {
    Q_OBJECT
  public:
    explicit Preview(QString path, bool edit = false, QWidget *parent = nullptr);
    ~Preview() override;
    bool confirmClose();
    void reject() override;

  protected:
    void closeEvent(QCloseEvent *event) override;

  private:
    bool save(bool saveAs = false);
    Files::TextDocument document;
    QPlainTextEdit *editor = nullptr;
    bool editable = false, loading = false, saving = false, closeAfterSave = false;
};
