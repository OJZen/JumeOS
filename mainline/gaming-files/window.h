#pragma once
#include <QMainWindow>
#include <QFileSystemModel>
#include <QFutureWatcher>
#include <atomic>
#include <memory>
#include "storage.h"
#include "operations.h"
#include <QMutex>
#include <QSortFilterProxyModel>
#include <QCollator>
class QListWidget;
class QTreeView;
class QListView;
class QLineEdit;
class QStackedWidget;
class QMenu;
class QLabel;
class QProgressBar;
class QFrame;
class QAction;
struct TaskProgress {
    QMutex mutex;
    QString item;
    qint64 done = 0, total = 0;
};
struct FolderInfo {
    QString path, error;
    qint64 available = 0;
    bool readOnly = false, missing = false;
};

class FileModel final : public QFileSystemModel {
  public:
    QVariant data(const QModelIndex &index, int role = Qt::DisplayRole) const override;
    QVariant headerData(int section, Qt::Orientation orientation, int role = Qt::DisplayRole) const override;
};

class FileSort final : public QSortFilterProxyModel {
  public:
    FileSort();
    bool foldersFirst = true;
    void setFoldersFirst(bool value) {
        foldersFirst = value;
        invalidate();
    }

  protected:
    bool lessThan(const QModelIndex &left, const QModelIndex &right) const override;

  private:
    QCollator collator;
};

class FileWindow final : public QMainWindow {
    Q_OBJECT
    friend class Check;

  public:
    FileWindow(QString state, QString start, QMap<QString, QString> userPlaces);
    void controllerAction(const QString &name);

  protected:
    void closeEvent(QCloseEvent *event) override;

  private:
    void navigate(const QString &path);
    void places();
    void open(bool edit = false);
    void details();
    void create(bool folder);
    void rename();
    void remove(bool permanent);
    void paste();
    void clipboardSelection(bool cut);
    void updateActions();
    void zip(bool extract);
    QStringList selectedPaths() const;
    QString selected() const;
    void run(const QString &title, std::function<QString(std::atomic_bool &, const Files::Progress &)> task,
             std::function<void(bool)> finished = {});
    void showError(const QString &text);
    void storeView();
    QModelIndex fileIndex(const QString &path) const;
    void showActions();
    void showActionsAt(QPoint position);
    QString state, folder, pendingFolder;
    QStringList clipboard;
    QMap<QString, QString> userPlaces;
    bool cutting = false, readOnly = false, multiSelect = false, pendingPreferences = false, closing = false;
    FileModel model;
    FileSort sorted;
    Storage storage;
    QListWidget *sidebar;
    QTreeView *table;
    QListView *list;
    QLineEdit *location;
    QStackedWidget *views;
    QMenu *menu;
    QLabel *selectionInfo, *clipboardInfo, *taskInfo, *emptyInfo;
    QFrame *clipboardPanel, *taskPanel;
    QProgressBar *taskBar;
    QAction *copyAction, *cutAction, *pasteAction;
    QTimer taskTimer;
    QFutureWatcher<FolderInfo> navigation;
    QFutureWatcher<QString> preferencesWrite;
    QFutureWatcher<QList<QPair<QString, QString>>> volumes;
    QList<QPair<QString, QString>> mountedPlaces;
    QFutureWatcher<QString> worker;
    std::shared_ptr<std::atomic_bool> cancel;
    std::shared_ptr<TaskProgress> taskProgress;
};
