#include "preview.h"
#include <QtWidgets>
#include <QtConcurrent>
#include <QPdfDocument>
#include <QPdfView>
#include <QPdfPageNavigator>
#include <QMediaPlayer>
#include <QAudioOutput>
#include <QVideoWidget>
#include <QImageReader>
#include <QMimeDatabase>

static void message(QWidget *parent, const QString &text) {
    QMessageBox box(QMessageBox::Warning, "Jume", text, QMessageBox::Ok, parent);
    box.setTextFormat(Qt::PlainText);
    box.exec();
}
Preview::~Preview() {
    // Qt 6.8 PDF emits statusChanged from document destruction. Detach while
    // QPdfView's private state is still alive, before QWidget deletes children.
    if (auto *view = findChild<QPdfView *>())
        view->setDocument(nullptr);
}
Preview::Preview(QString path, bool edit, QWidget *parent) : QDialog(parent) {
    setWindowTitle(path.isEmpty() ? "Jume Text — 新建" : QFileInfo(path).fileName());
    resize(640, 480);
    auto *layout = new QVBoxLayout(this);
    auto *bar = new QToolBar;
    layout->addWidget(bar);
    bar->addAction("关闭", this, &QDialog::close);
    auto *title = new QLabel(path.isEmpty() ? "新建文本" : QFileInfo(path).fileName());
    title->setObjectName("previewTitle");
    title->setTextFormat(Qt::PlainText);
    title->setWordWrap(true);
    layout->addWidget(title);
    const auto suffix = QFileInfo(path).suffix().toLower();
    const QStringList images{"png", "jpg", "jpeg", "bmp", "gif", "webp"},
        media{"mp3", "wav", "flac", "ogg", "opus", "aac", "m4a", "mp4", "mkv", "webm", "mov", "avi"};
    const auto mime = path.isEmpty() ? QString("text/plain")
                                     : QMimeDatabase().mimeTypeForFile(path, QMimeDatabase::MatchExtension).name();
    const bool office = QStringList{"docx", "odt"}.contains(suffix);
    if (!path.isEmpty() && (!QFileInfo(path).isFile() || QFileInfo(path).isSymLink())) {
        layout->addWidget(new QLabel("仅预览普通文件；请显式打开链接目标。"));
        return;
    }
    if (edit || office || mime.startsWith("text/") ||
        QStringList{"json", "xml", "yaml", "yml", "md", "log", "ini", "conf", "sh"}.contains(suffix)) {
        editor = new QPlainTextEdit;
        editor->setObjectName("textEditor");
        editor->setLineWrapMode(QPlainTextEdit::NoWrap);
        editor->setReadOnly(true);
        layout->addWidget(editor, 1);
        auto *find = bar->addAction("查找");
        find->setShortcut(QKeySequence::Find);
        connect(find, &QAction::triggered, this, [this] {
            bool ok = false;
            const auto word = QInputDialog::getText(this, "查找", "文字", QLineEdit::Normal, {}, &ok);
            if (ok && !word.isEmpty() && !editor->find(word)) {
                editor->moveCursor(QTextCursor::Start);
                editor->find(word);
            }
        });
        if (!office) {
            connect(editor->document(), &QTextDocument::modificationChanged, title, [this, title](bool changed) {
                title->setText((document.path.isEmpty() ? QString("新建文本") : QFileInfo(document.path).fileName()) +
                               (changed ? " · 未保存" : ""));
            });
            editable = edit;
            auto *toggle = bar->addAction("编辑");
            toggle->setEnabled(false);
            connect(toggle, &QAction::triggered, this, [this, toggle] {
                editable = true;
                editor->setReadOnly(false);
                toggle->setEnabled(false);
            });
            auto *saveAction = bar->addAction("保存", this, [this] { save(); });
            saveAction->setShortcut(QKeySequence::Save);
            bar->addAction("另存为", this, [this] { save(true); })->setShortcut(QKeySequence::SaveAs);
            if (path.isEmpty()) {
                editor->setReadOnly(!edit);
                toggle->setEnabled(!edit);
                return;
            }
            loading = true;
            auto *watcher = new QFutureWatcher<QPair<Files::TextDocument, QString>>(this);
            connect(watcher, &QFutureWatcherBase::finished, this, [this, watcher, toggle] {
                auto result = watcher->result();
                watcher->deleteLater();
                loading = false;
                if (!result.second.isEmpty()) {
                    message(this, result.second);
                    return;
                }
                document = result.first;
                editor->setPlainText(document.text);
                editor->document()->setModified(false);
                editor->setReadOnly(!editable);
                toggle->setEnabled(!editable);
            });
            watcher->setFuture(QtConcurrent::run([path] {
                Files::TextDocument doc;
                auto error = doc.load(path);
                return qMakePair(doc, error);
            }));
        } else {
            title->setText(title->text() + " · 仅正文，不含原排版");
            auto *watcher = new QFutureWatcher<QPair<QString, QString>>(this);
            connect(watcher, &QFutureWatcherBase::finished, this, [this, watcher] {
                auto r = watcher->result();
                watcher->deleteLater();
                editor->setPlainText(r.second.isEmpty() ? r.first : r.second);
            });
            watcher->setFuture(QtConcurrent::run([path] {
                QString error;
                const auto text = Files::officeText(path, &error);
                return qMakePair(text, error);
            }));
        }
    } else if (images.contains(suffix)) {
        auto *scroll = new QScrollArea;
        scroll->setWidgetResizable(true);
        auto *label = new QLabel("正在读取图片…");
        label->setAlignment(Qt::AlignCenter);
        scroll->setWidget(label);
        layout->addWidget(scroll, 1);
        auto *watcher = new QFutureWatcher<QPair<QImage, QString>>(this);
        connect(watcher, &QFutureWatcherBase::finished, this, [watcher, label] {
            auto r = watcher->result();
            watcher->deleteLater();
            if (r.first.isNull())
                label->setText(r.second);
            else
                label->setPixmap(QPixmap::fromImage(r.first));
        });
        watcher->setFuture(QtConcurrent::run([path] {
            if (QFileInfo(path).size() > 64 * 1024 * 1024)
                return qMakePair(QImage(), QString("图片超过 64 MiB 限制。"));
            QImageReader reader(path);
            reader.setAutoTransform(true);
            const auto size = reader.size();
            if (!size.isValid() || qint64(size.width()) * size.height() > 100000000)
                return qMakePair(QImage(), QString("图片尺寸无效或过大。"));
            reader.setScaledSize(size.scaled(1024, 768, Qt::KeepAspectRatio));
            auto image = reader.read();
            return qMakePair(image, reader.errorString());
        }));
    } else if (suffix == "pdf") {
        if (QFileInfo(path).size() > 64 * 1024 * 1024) {
            layout->addWidget(new QLabel("PDF 超过 64 MiB 限制。"));
            return;
        }
        auto *view = new QPdfView;
        auto *pdf = new QPdfDocument(view);
        view->setDocument(pdf);
        view->setZoomMode(QPdfView::ZoomMode::FitInView);
        layout->addWidget(view, 1);
        auto *page = new QSpinBox;
        page->setMinimum(1);
        page->setPrefix("页 ");
        bar->addWidget(page);
        bar->addAction("放大", view, [view] {
            view->setZoomMode(QPdfView::ZoomMode::Custom);
            view->setZoomFactor(qMin(4., view->zoomFactor() * 1.25));
        });
        bar->addAction("缩小", view, [view] {
            view->setZoomMode(QPdfView::ZoomMode::Custom);
            view->setZoomFactor(qMax(.1, view->zoomFactor() / 1.25));
        });
        bar->addAction("适合窗口", view, [view] { view->setZoomMode(QPdfView::ZoomMode::FitInView); });
        connect(pdf, &QPdfDocument::pageCountChanged, page, [page](int count) { page->setMaximum(qMax(1, count)); });
        connect(page, &QSpinBox::valueChanged, view,
                [view](int n) { view->pageNavigator()->jump(n - 1, QPointF(), 0); });
        connect(pdf, &QPdfDocument::statusChanged, title, [pdf, title] {
            if (pdf->status() == QPdfDocument::Status::Error)
                title->setText("PDF 无法打开；加密/损坏文件不支持预览。");
        });
        pdf->load(path);
    } else if (media.contains(suffix)) {
        auto *video = new QVideoWidget;
        auto *player = new QMediaPlayer(this);
        auto *audio = new QAudioOutput(this);
        audio->setVolume(.7);
        player->setAudioOutput(audio);
        player->setVideoOutput(video);
        layout->addWidget(video, 1);
        auto *play = bar->addAction("播放/暂停");
        connect(play, &QAction::triggered, this, [player] {
            if (player->playbackState() == QMediaPlayer::PlayingState)
                player->pause();
            else
                player->play();
        });
        auto *seek = new QSlider(Qt::Horizontal);
        seek->setRange(0, 1000);
        layout->addWidget(seek);
        connect(player, &QMediaPlayer::positionChanged, seek, [player, seek](qint64 position) {
            if (!seek->isSliderDown() && player->duration() > 0)
                seek->setValue(int(position * 1000 / player->duration()));
        });
        connect(seek, &QSlider::sliderReleased, player,
                [player, seek] { player->setPosition(player->duration() * seek->value() / 1000); });
        connect(player, &QMediaPlayer::errorOccurred, title,
                [title](QMediaPlayer::Error, const QString &text) { title->setText("播放失败：" + text); });
        connect(this, &QDialog::finished, player, &QMediaPlayer::stop);
        player->setSource(QUrl::fromLocalFile(path)); // No automatic playback or network URL handling.
    } else {
        auto *info = new QPlainTextEdit(Files::properties(path) + "\n此格式暂不预览；不会自动执行文件或调用外部程序。");
        info->setReadOnly(true);
        layout->addWidget(info, 1);
    }
}
bool Preview::save(bool saveAs) {
    if (!editor || editor->isReadOnly() || loading || saving)
        return false;
    QString path = document.path;
    if (saveAs || path.isEmpty()) {
        auto directory = property("saveDirectory").toString();
        if (directory.isEmpty())
            directory = QDir::homePath() + "/Documents";
        if (path.isEmpty() && !QDir().mkpath(directory)) {
            message(this, "无法创建默认文档目录，请通过文件管理器选择可写目录。");
            return false;
        }
        path = QFileDialog::getSaveFileName(this, "另存为（不覆盖同名文件）",
                                            path.isEmpty() ? directory + "/untitled.txt" : path, {}, nullptr,
                                            QFileDialog::DontUseNativeDialog | QFileDialog::DontConfirmOverwrite);
    }
    if (path.isEmpty())
        return false;
    saving = true;
    editor->setReadOnly(true);
    findChild<QLabel *>("previewTitle")->setText("正在保存…");
    auto *watcher = new QFutureWatcher<QPair<Files::TextDocument, QString>>(this);
    connect(watcher, &QFutureWatcherBase::finished, this, [this, watcher] {
        const auto result = watcher->result();
        watcher->deleteLater();
        saving = false;
        editor->setReadOnly(false);
        if (!result.second.isEmpty()) {
            closeAfterSave = false;
            findChild<QLabel *>("previewTitle")->setText("保存失败 · 内容仍在编辑器中");
            message(this, result.second);
            return;
        }
        document = result.first;
        editor->document()->setModified(false);
        setWindowTitle(QFileInfo(document.path).fileName());
        findChild<QLabel *>("previewTitle")->setText(QFileInfo(document.path).fileName());
        if (closeAfterSave) {
            closeAfterSave = false;
            accept();
        }
    });
    watcher->setFuture(QtConcurrent::run([doc = document, path, text = editor->toPlainText()]() mutable {
        auto error = doc.save(path, text);
        return qMakePair(doc, error);
    }));
    return true;
}
bool Preview::confirmClose() {
    if (saving)
        return false;
    if (!editor || !editor->document()->isModified())
        return true;
    QMessageBox ask(QMessageBox::Question, "未保存的内容", "保存修改后关闭？",
                    QMessageBox::Save | QMessageBox::Discard | QMessageBox::Cancel, this);
    ask.setDefaultButton(QMessageBox::Cancel);
    const auto choice = ask.exec();
    if (choice == QMessageBox::Save) {
        closeAfterSave = true;
        if (!save())
            closeAfterSave = false;
        return false;
    }
    return choice == QMessageBox::Discard;
}
void Preview::closeEvent(QCloseEvent *event) {
    if (confirmClose())
        event->accept();
    else
        event->ignore();
}
void Preview::reject() {
    if (confirmClose())
        QDialog::reject();
}
