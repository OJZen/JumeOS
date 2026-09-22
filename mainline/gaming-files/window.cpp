#include "window.h"
#include "preview.h"
#include "appearance.h"
#include <QtWidgets>
#include <QtConcurrent>
#include <QStorageInfo>

FileSort::FileSort() : collator(QLocale(QLocale::English)) {
    collator.setNumericMode(true);
    collator.setCaseSensitivity(Qt::CaseInsensitive);
}
bool FileSort::lessThan(const QModelIndex &left, const QModelIndex &right) const {
    const auto *files = qobject_cast<const QFileSystemModel *>(sourceModel());
    const auto a = files->fileInfo(left), b = files->fileInfo(right);
    if (foldersFirst && a.isDir() != b.isDir())
        return sortOrder() == Qt::AscendingOrder ? a.isDir() : !a.isDir();
    const auto nameOrder = [&] {
        const int order = collator.compare(a.fileName(), b.fileName());
        return order == 0 ? a.fileName() < b.fileName() : order < 0;
    };
    switch (left.column()) {
    case 1: {
        const auto as = a.isDir() ? 0 : a.size(), bs = b.isDir() ? 0 : b.size();
        if (as != bs)
            return as < bs;
        break;
    }
    case 2: {
        const int order = collator.compare(a.isDir() ? QString() : a.suffix(), b.isDir() ? QString() : b.suffix());
        if (order)
            return order < 0;
        break;
    }
    case 3:
        if (a.lastModified() != b.lastModified())
            return a.lastModified() < b.lastModified();
        break;
    }
    return nameOrder();
}

QVariant FileModel::data(const QModelIndex &index, int role) const {
    if (role == Qt::DecorationRole && index.column() == 0)
        return filesIcon(isDir(index));
    if (role == Qt::FontRole && index.column() > 0) {
        auto font = qApp->font();
        font.setPixelSize(13);
        return font;
    }
    if (role == Qt::DisplayRole && index.column() == 1) {
        const auto bytes = fileInfo(index).size();
        return isDir(index)   ? QString()
               : bytes < 1024 ? QString::number(bytes) + " B"
                              : QLocale().formattedDataSize(bytes, 1);
    }
    if (role == Qt::DisplayRole && index.column() == 3)
        return fileInfo(index).lastModified().toString("yy-MM-dd HH:mm");
    return QFileSystemModel::data(index, role);
}
QVariant FileModel::headerData(int section, Qt::Orientation orientation, int role) const {
    if (role == Qt::DisplayRole && orientation == Qt::Horizontal && section >= 0 && section < 4)
        return QStringList{"名称", "大小", "类型", "修改时间"}[section];
    return QFileSystemModel::headerData(section, orientation, role);
}

FileWindow::FileWindow(QString privateState, QString start, QMap<QString, QString> directories)
    : state(std::move(privateState)), userPlaces(std::move(directories)) {
    setWindowTitle("Jume Files");
    resize(640, 480);
    auto *body = new QWidget;
    auto *layout = new QVBoxLayout(body);
    setCentralWidget(body);
    layout->setContentsMargins(12, 10, 12, 4);
    layout->setSpacing(8);
    auto *pathRow = new QHBoxLayout;
    auto *navigationBar = new QToolBar;
    navigationBar->setMovable(false);
    navigationBar->setIconSize(QSize(22, 22));
    pathRow->addWidget(navigationBar);
    auto *placesAction = navigationBar->addAction(filesActionIcon("places"), "位置 / 分区");
    placesAction->setObjectName("showPlaces");
    placesAction->setCheckable(true);
    navigationBar
        ->addAction(filesActionIcon("up"), "上级目录", this, [this] { navigate(QFileInfo(folder).absolutePath()); })
        ->setShortcut(QKeySequence("Alt+Up"));
    location = new QLineEdit;
    location->setObjectName("location");
    location->setAccessibleName("目录路径");
    location->setMinimumWidth(0);
    pathRow->addWidget(location, 1);
    auto *viewBar = new QToolBar;
    viewBar->setMovable(false);
    viewBar->setIconSize(QSize(22, 22));
    pathRow->addWidget(viewBar);
    auto *toggle = viewBar->addAction(filesActionIcon("view"), "列表 / 表格");
    toggle->setObjectName("detailsView");
    toggle->setCheckable(true);
    viewBar->addAction(filesActionIcon("menu"), "文件菜单（Y / Shift+F10）", this, &FileWindow::showActions);
    viewBar->addAction(filesActionIcon("close"), "关闭", this, &QWidget::close);
    layout->addLayout(pathRow);
    connect(location, &QLineEdit::returnPressed, this, [this] { navigate(location->text()); });
    menu = new QMenu(this);
    auto *split = new QSplitter;
    split->setChildrenCollapsible(false);
    layout->addWidget(split, 1);
    sidebar = new QListWidget;
    sidebar->setObjectName("places");
    sidebar->setAccessibleName("位置与分区");
    sidebar->setMinimumWidth(125);
    sidebar->hide();
    connect(placesAction, &QAction::triggered, this, [this, placesAction] {
        sidebar->setVisible(placesAction->isChecked());
        storeView();
    });
    split->addWidget(sidebar);
    split->setHandleWidth(8);
    views = new QStackedWidget;
    table = new QTreeView;
    list = new QListView;
    auto *content = new QWidget;
    auto *overlay = new QStackedLayout(content);
    overlay->setStackingMode(QStackedLayout::StackAll);
    overlay->addWidget(views);
    split->addWidget(content);
    split->setStretchFactor(1, 1);
    split->setSizes({150, 458});
    table->setObjectName("fileTable");
    list->setObjectName("fileList");
    model.setReadOnly(true);
    model.setOption(QFileSystemModel::DontUseCustomDirectoryIcons, true);
    model.setFilter(QDir::AllEntries | QDir::NoDotAndDotDot | QDir::System);
    model.setRootPath("/");
    sorted.setSourceModel(&model);
    table->setModel(&sorted);
    table->setRootIsDecorated(false);
    table->setItemsExpandable(false);
    table->setUniformRowHeights(true);
    table->setSortingEnabled(true);
    table->sortByColumn(0, Qt::AscendingOrder);
    table->setSelectionBehavior(QAbstractItemView::SelectRows);
    table->header()->setStretchLastSection(false);
    table->header()->setSectionResizeMode(0, QHeaderView::Stretch);
    table->setColumnWidth(1, 72);
    table->setColumnHidden(2, true);
    table->setColumnWidth(3, 128);
    list->setModel(&sorted);
    list->setUniformItemSizes(true);
    list->setLayoutMode(QListView::Batched);
    list->setBatchSize(128);
    list->setSelectionModel(table->selectionModel());
    views->addWidget(list);
    views->addWidget(table);
    for (auto *view : {static_cast<QAbstractItemView *>(table), static_cast<QAbstractItemView *>(list)}) {
        view->setSelectionMode(QAbstractItemView::ExtendedSelection);
        view->setIconSize(QSize(24, 24));
        view->setTextElideMode(Qt::ElideMiddle);
        view->setHorizontalScrollBarPolicy(Qt::ScrollBarAlwaysOff);
        view->setContextMenuPolicy(Qt::CustomContextMenu);
        connect(view, &QAbstractItemView::activated, this, [this] { open(); });
        connect(view, &QWidget::customContextMenuRequested, this, [this, view](const QPoint &point) {
            const auto index = view->indexAt(point);
            if (index.isValid() && !view->selectionModel()->isSelected(index))
                view->setCurrentIndex(index);
            showActionsAt(view->viewport()->mapToGlobal(point));
        });
    }
    emptyInfo = new QLabel("正在读取目录…");
    emptyInfo->setAlignment(Qt::AlignCenter);
    emptyInfo->setAttribute(Qt::WA_TransparentForMouseEvents);
    emptyInfo->setObjectName("caption");
    overlay->addWidget(emptyInfo);
    overlay->setCurrentWidget(emptyInfo);
    connect(toggle, &QAction::triggered, this, [this, toggle] {
        views->setCurrentIndex(toggle->isChecked() ? 1 : 0);
        views->currentWidget()->setFocus();
        storeView();
    });
    auto action = [this](const QString &name, const QKeySequence &key, auto callback) {
        auto *a = menu->addAction(name, this, callback);
        a->setObjectName(name);
        a->setShortcut(key);
        a->setShortcutContext(Qt::WidgetWithChildrenShortcut);
        views->addAction(a);
        return a;
    };
    action("打开/预览", {}, [this] { open(); });
    action("作为文本编辑", QKeySequence("Ctrl+E"), [this] { open(true); });
    action("新建目录", QKeySequence("Ctrl+Shift+N"), [this] { create(true); });
    action("新建文本", QKeySequence::New, [this] { create(false); });
    action("重命名", QKeySequence(Qt::Key_F2), [this] { rename(); });
    copyAction = action("复制", QKeySequence::Copy, [this] { clipboardSelection(false); });
    cutAction = action("剪切", QKeySequence::Cut, [this] { clipboardSelection(true); });
    pasteAction = action("粘贴", QKeySequence::Paste, [this] { paste(); });
    menu->addSeparator();
    action("解压 ZIP…", {}, [this] { zip(true); });
    action("压缩为 ZIP…", {}, [this] { zip(false); });
    menu->addSeparator();
    action("移入回收站", QKeySequence::Delete, [this] { remove(false); });
    action("从回收站恢复…", {}, [this] {
        const auto path = selected();
        run("恢复文件",
            [path](std::atomic_bool &flag, const Files::Progress &) { return Files::restoreTrash(path, flag); });
    });
    action("永久删除…", QKeySequence("Shift+Delete"), [this] { remove(true); });
    action("属性", QKeySequence("Alt+Return"), [this] { details(); });
    menu->addSeparator();
    auto *hidden = action("显示隐藏文件", QKeySequence("Ctrl+H"), [this] {
        model.setFilter(model.filter() ^ QDir::Hidden);
        storeView();
    });
    hidden->setCheckable(true);
    action("刷新存储", QKeySequence::Refresh, [this] {
        storage.refresh();
        places();
        navigate(folder);
    });
    action("安全卸载选中的 U 盘", {}, [this] {
        const auto data =
            sidebar->currentItem() ? sidebar->currentItem()->data(Qt::UserRole + 1).toMap() : QVariantMap();
        if (data.value("mount").toString().isEmpty() || worker.isRunning())
            return;
        navigate(QDir::homePath());
        storage.mount(data, true);
    });
    // Keep the root menu inside a 480 px screen; native submenus keep key navigation.
    for (auto *a : menu->actions())
        if (a->isSeparator())
            menu->removeAction(a);
    const QList<QPair<QString, QStringList>> groups{
        {"新建", {"新建目录", "新建文本"}},
        {"ZIP", {"解压 ZIP…", "压缩为 ZIP…"}},
        {"回收站与删除", {"移入回收站", "从回收站恢复…", "永久删除…"}},
        {"显示与存储", {"显示隐藏文件", "刷新存储", "安全卸载选中的 U 盘"}}};
    for (const auto &group : groups) {
        auto *submenu = menu->addMenu(group.first);
        for (const auto &name : group.second) {
            auto *a = menu->findChild<QAction *>(name);
            menu->removeAction(a);
            submenu->addAction(a);
        }
    }
    for (auto *a : {pasteAction, cutAction, copyAction}) {
        menu->removeAction(a);
        menu->insertAction(menu->actions().first(), a);
    }
    auto *sortMenu = menu->addMenu("排序");
    auto *sortGroup = new QActionGroup(this);
    const QStringList sortNames{"名称", "大小", "类型", "修改时间"};
    for (int column = 0; column < 4; ++column) {
        auto *a = sortMenu->addAction(sortNames[column]);
        a->setObjectName("sort-" + QString::number(column));
        a->setCheckable(true);
        a->setActionGroup(sortGroup);
        a->setChecked(column == 0);
        connect(a, &QAction::triggered, this, [this, column] { table->sortByColumn(column, sorted.sortOrder()); });
    }
    sortMenu->addSeparator();
    auto *order = sortMenu->addAction("降序");
    order->setObjectName("sortDescending");
    order->setCheckable(true);
    connect(order, &QAction::triggered, this, [this, order] {
        table->sortByColumn(sorted.sortColumn(), order->isChecked() ? Qt::DescendingOrder : Qt::AscendingOrder);
    });
    auto *folders = sortMenu->addAction("文件夹优先");
    folders->setObjectName("foldersFirst");
    folders->setCheckable(true);
    folders->setChecked(true);
    connect(folders, &QAction::triggered, this, [this, folders] {
        sorted.setFoldersFirst(folders->isChecked());
        updateActions();
        storeView();
    });
    menu->addAction("关闭文件管理器", this, &QWidget::close);
    auto *contextShortcut = new QShortcut(QKeySequence("Shift+F10"), views);
    contextShortcut->setContext(Qt::WidgetWithChildrenShortcut);
    connect(contextShortcut, &QShortcut::activated, this, &FileWindow::showActions);
    auto *pathShortcut = new QShortcut(QKeySequence("Ctrl+L"), this);
    connect(pathShortcut, &QShortcut::activated, this, [this] {
        location->setFocus();
        location->selectAll();
    });
    clipboardPanel = new QFrame;
    clipboardPanel->setObjectName("clipboardPanel");
    auto *clipLayout = new QHBoxLayout(clipboardPanel);
    clipLayout->setContentsMargins(10, 3, 6, 3);
    clipboardInfo = new QLabel;
    clipboardInfo->setTextFormat(Qt::PlainText);
    clipLayout->addWidget(clipboardInfo, 1);
    auto *clear = new QPushButton("清除");
    clipLayout->addWidget(clear);
    layout->addWidget(clipboardPanel);
    clipboardPanel->hide();
    connect(clear, &QPushButton::clicked, this, [this] {
        clipboard.clear();
        updateActions();
    });
    taskPanel = new QFrame;
    taskPanel->setObjectName("taskPanel");
    auto *taskLayout = new QVBoxLayout(taskPanel);
    taskLayout->setContentsMargins(10, 6, 6, 8);
    taskLayout->setSpacing(5);
    auto *taskRow = new QHBoxLayout;
    taskInfo = new QLabel;
    taskInfo->setTextFormat(Qt::PlainText);
    taskInfo->setMinimumWidth(0);
    taskInfo->setSizePolicy(QSizePolicy::Ignored, QSizePolicy::Preferred);
    taskRow->addWidget(taskInfo, 1);
    auto *detailsButton = new QPushButton("详情");
    taskRow->addWidget(detailsButton);
    connect(detailsButton, &QPushButton::clicked, this, [this] { showError(taskInfo->toolTip()); });
    auto *cancelButton = new QPushButton("取消 / 收起");
    cancelButton->setObjectName("cancelTask");
    taskRow->addWidget(cancelButton);
    taskLayout->addLayout(taskRow);
    taskBar = new QProgressBar;
    taskBar->setTextVisible(false);
    taskBar->setRange(0, 100);
    taskLayout->addWidget(taskBar);
    layout->addWidget(taskPanel);
    taskPanel->hide();
    connect(cancelButton, &QPushButton::clicked, this, [this] {
        if (worker.isRunning()) {
            *cancel = true;
            taskInfo->setText("正在取消，请稍候…");
        } else
            taskPanel->hide();
    });
    selectionInfo = new QLabel;
    selectionInfo->setObjectName("selectionInfo");
    statusBar()->addPermanentWidget(selectionInfo);
    statusBar()->setSizeGripEnabled(false);
    statusBar()->showMessage("Y 菜单 · B 打开 · Select 多选");
    connect(menu, &QMenu::aboutToShow, this, &FileWindow::updateActions);
    connect(table->selectionModel(), &QItemSelectionModel::selectionChanged, this, &FileWindow::updateActions);
    connect(table->selectionModel(), &QItemSelectionModel::currentChanged, this, &FileWindow::updateActions);
    connect(&model, &QFileSystemModel::directoryLoaded, this, &FileWindow::updateActions);
    connect(&model, &QAbstractItemModel::rowsInserted, this, &FileWindow::updateActions);
    connect(&model, &QAbstractItemModel::rowsRemoved, this, &FileWindow::updateActions);
    connect(sidebar, &QListWidget::itemActivated, this, [this](QListWidgetItem *item) {
        const auto path = item->data(Qt::UserRole).toString();
        const auto device = item->data(Qt::UserRole + 1).toMap();
        if (!device.isEmpty() && path.isEmpty()) {
            storage.mount(device, false);
            return;
        }
        navigate(path);
    });
    connect(sidebar, &QListWidget::itemClicked, sidebar, &QListWidget::itemActivated);
    connect(&storage, &Storage::changed, this, [this] {
        places();
        if (!storage.error.isEmpty())
            statusBar()->showMessage(storage.error, 6000);
    });
    connect(&storage, &Storage::mounted, this, [this](const QString &path) {
        navigate(path);
        storage.refresh();
    });
    connect(&volumes, &QFutureWatcherBase::finished, this, [this] {
        mountedPlaces = volumes.result();
        places();
    });
    connect(&preferencesWrite, &QFutureWatcherBase::finished, this, [this] {
        if (!preferencesWrite.result().isEmpty())
            statusBar()->showMessage(preferencesWrite.result(), 5000);
        if (pendingPreferences)
            storeView();
        else if (closing)
            close();
    });
    connect(&navigation, &QFutureWatcherBase::finished, this, [this] {
        const auto result = navigation.result();
        if (!pendingFolder.isEmpty()) {
            const auto path = pendingFolder;
            pendingFolder.clear();
            navigate(path);
            return;
        }
        views->setEnabled(true);
        if (!result.error.isEmpty()) {
            location->setText(folder);
            updateActions();
            if (result.missing && !worker.isRunning() && userPlaces.values().contains(result.path)) {
                QMessageBox ask(QMessageBox::Question, "创建标准目录", result.path,
                                QMessageBox::Yes | QMessageBox::Cancel, this);
                ask.setTextFormat(Qt::PlainText);
                ask.setDefaultButton(QMessageBox::Cancel);
                if (ask.exec() == QMessageBox::Yes)
                    run(
                        "创建标准目录",
                        [path = result.path](std::atomic_bool &, const Files::Progress &) {
                            return QDir().mkpath(path) ? QString() : QString("创建目录失败。");
                        },
                        [this, path = result.path](bool ok) {
                            if (ok)
                                navigate(path);
                        });
            } else
                showError(result.error);
            return;
        }
        folder = result.path;
        readOnly = result.readOnly;
        location->setText(folder);
        model.setRootPath(folder);
        const auto index = fileIndex(folder);
        table->setRootIndex(index);
        list->setRootIndex(index);
        table->selectionModel()->clear();
        location->setToolTip(
            QString("%1 · 剩余 %2").arg(readOnly ? "只读" : "可写", QLocale().formattedDataSize(result.available)));
        views->currentWidget()->setFocus();
        updateActions();
    });
    taskTimer.setInterval(100);
    connect(&taskTimer, &QTimer::timeout, this, [this] {
        if (!taskProgress || !worker.isRunning() || *cancel)
            return;
        QMutexLocker lock(&taskProgress->mutex);
        const auto text =
            QFileInfo(taskProgress->item).fileName() + " · " + QLocale().formattedDataSize(taskProgress->done) +
            (taskProgress->total > 0 ? " / " + QLocale().formattedDataSize(taskProgress->total) : QString());
        taskInfo->setText(taskInfo->fontMetrics().elidedText(text, Qt::ElideMiddle, taskInfo->width()));
        taskInfo->setToolTip(taskProgress->item);
        taskBar->setValue(
            taskProgress->total > 0 ? int(qMin<qint64>(100, taskProgress->done * 100 / taskProgress->total)) : 0);
    });
    QFile preferences(state + "/view.json");
    if (preferences.open(QIODevice::ReadOnly)) {
        const auto data = QJsonDocument::fromJson(preferences.read(4096)).object();
        toggle->setChecked(data.value("details").toBool());
        views->setCurrentIndex(toggle->isChecked() ? 1 : 0);
        if (data.value("hidden").toBool()) {
            hidden->setChecked(true);
            model.setFilter(model.filter() | QDir::Hidden);
        }
        const int column = qBound(0, data.value("sortColumn").toInt(), 3);
        const auto direction = data.value("descending").toBool() ? Qt::DescendingOrder : Qt::AscendingOrder;
        sorted.setFoldersFirst(data.value("foldersFirst").toBool(true));
        folders->setChecked(sorted.foldersFirst);
        table->sortByColumn(column, direction);
        sortGroup->actions()[column]->setChecked(true);
        order->setChecked(direction == Qt::DescendingOrder);
        sidebar->setVisible(data.value("sidebar").toBool(false));
        placesAction->setChecked(!sidebar->isHidden());
    }
    connect(table->header(), &QHeaderView::sortIndicatorChanged, this,
            [this, sortGroup, order](int column, Qt::SortOrder direction) {
                if (column >= 0 && column < 4)
                    sortGroup->actions()[column]->setChecked(true);
                order->setChecked(direction == Qt::DescendingOrder);
                updateActions();
                storeView();
            });
    places();
    navigate(start);
    updateActions();
}
void FileWindow::showError(const QString &text) {
    if (text.isEmpty())
        return;
    QMessageBox box(QMessageBox::Warning, "Jume Files", text, QMessageBox::Ok, this);
    box.setTextFormat(Qt::PlainText);
    box.exec();
}
void FileWindow::storeView() {
    if (preferencesWrite.isRunning()) {
        pendingPreferences = true;
        return;
    }
    pendingPreferences = false;
    const auto bytes = QJsonDocument(QJsonObject{{"details", views->currentIndex() == 1},
                                                 {"hidden", bool(model.filter() & QDir::Hidden)},
                                                 {"sidebar", !sidebar->isHidden()},
                                                 {"sortColumn", sorted.sortColumn()},
                                                 {"descending", sorted.sortOrder() == Qt::DescendingOrder},
                                                 {"foldersFirst", sorted.foldersFirst}})
                           .toJson();
    preferencesWrite.setFuture(QtConcurrent::run([path = state + "/view.json", bytes] {
        QSaveFile file(path);
        if (!file.open(QIODevice::WriteOnly) || file.write(bytes) != bytes.size() || !file.commit())
            return QString("视图偏好未能保存");
        return QString();
    }));
}
void FileWindow::places() {
    if (!volumes.isRunning() && sender() != &volumes)
        volumes.setFuture(QtConcurrent::run([] {
            QList<QPair<QString, QString>> result;
            for (const auto &volume : QStorageInfo::mountedVolumes())
                if (volume.isValid() && volume.isReady() && QFileInfo(volume.rootPath()).isDir() &&
                    volume.rootPath() != "/" && volume.rootPath() != "/roms" && volume.device().startsWith("/dev/"))
                    result.append({volume.displayName() + (volume.isReadOnly() ? " [只读]" : ""), volume.rootPath()});
            return result;
        }));
    QList<QPair<QString, QVariantMap>> entries;
    auto add = [&](const QString &name, const QString &path, QVariantMap device = {}) {
        device["path"] = path;
        entries.append({name, device});
    };
    add("个人目录", QDir::homePath());
    for (auto i = userPlaces.begin(); i != userPlaces.end(); ++i)
        if (!i.value().isEmpty())
            add(i.key(), i.value());
    add("游戏分区", "/roms");
    add("系统文件", "/");
    for (const auto &volume : mountedPlaces) {
        bool usb = false;
        for (const auto &v : storage.devices)
            if (v.toMap().value("mount").toString() == volume.second)
                usb = true;
        if (!usb)
            add(volume.first, volume.second);
    }
    for (const auto &v : storage.devices) {
        const auto d = v.toMap();
        add("USB · " +
                (d.value("label").toString().isEmpty() ? d.value("type").toString() : d.value("label").toString()) +
                (d.value("mount").toString().isEmpty() ? " [挂载]" : ""),
            d.value("mount").toString(), d);
    }
    bool equal = entries.size() == sidebar->count();
    for (int i = 0; equal && i < entries.size(); ++i)
        equal = sidebar->item(i)->text() == entries[i].first &&
                sidebar->item(i)->data(Qt::UserRole + 2).toMap() == entries[i].second;
    if (equal)
        return;
    const auto current = sidebar->currentItem();
    const auto selection = current ? current->data(Qt::UserRole + 2).toMap() : QVariantMap();
    const auto scroll = sidebar->verticalScrollBar()->value();
    sidebar->clear();
    for (const auto &entry : entries) {
        auto d = entry.second;
        const auto path = d.take("path").toString();
        auto *item = new QListWidgetItem(entry.first, sidebar);
        item->setData(Qt::UserRole, path);
        item->setData(Qt::UserRole + 1, d);
        item->setData(Qt::UserRole + 2, entry.second);
        item->setToolTip(path);
        if (entry.second == selection)
            sidebar->setCurrentItem(item);
    }
    sidebar->verticalScrollBar()->setValue(scroll);
}
void FileWindow::navigate(const QString &path) {
    if (navigation.isRunning()) {
        pendingFolder = path;
        return;
    }
    if (path.isEmpty())
        return;
    views->setEnabled(false);
    emptyInfo->setText("正在读取目录…");
    emptyInfo->show();
    navigation.setFuture(QtConcurrent::run([path] {
        FolderInfo result;
        result.path = path;
        QFileInfo info(path);
        if (!QDir::isAbsolutePath(path) || !info.isDir() || !info.isReadable()) {
            result.missing = !info.exists();
            result.error = "目录不存在或不可读；可先在上级目录新建。";
            return result;
        }
        result.path = info.canonicalFilePath();
        QStorageInfo disk(result.path);
        result.available = disk.bytesAvailable();
        result.readOnly = disk.isReadOnly() || !info.isWritable();
        return result;
    }));
}
QStringList FileWindow::selectedPaths() const {
    QStringList result;
    for (const auto &i : table->selectionModel()->selectedIndexes())
        if (i.column() == 0 && i.parent() == table->rootIndex())
            result << model.filePath(sorted.mapToSource(i));
    return result;
}
QString FileWindow::selected() const {
    const auto paths = selectedPaths();
    return paths.size() == 1 ? paths.first() : QString();
}
void FileWindow::updateActions() {
    const auto paths = selectedPaths();
    const bool any = !paths.isEmpty(), one = paths.size() == 1, busy = worker.isRunning(),
               ready = !navigation.isRunning() && !folder.isEmpty();
    copyAction->setEnabled(any && !busy && ready);
    cutAction->setEnabled(any && !busy && ready && !readOnly);
    pasteAction->setEnabled(!clipboard.isEmpty() && !busy && ready && !readOnly);
    for (auto *action : menu->findChildren<QAction *>()) {
        const auto name = action->text();
        if (QStringList{"新建目录", "新建文本", "压缩为 ZIP…", "移入回收站", "永久删除…", "从回收站恢复…", "重命名"}
                .contains(name))
            action->setEnabled(ready && !busy && !readOnly && (name.startsWith("新建") || any));
        if (QStringList{"重命名", "作为文本编辑", "属性", "打开/预览", "从回收站恢复…"}.contains(name))
            action->setEnabled(ready && one && !busy && (name != "重命名" || !readOnly));
        if (name == "解压 ZIP…")
            action->setEnabled(ready && one && !busy && !readOnly &&
                               paths.first().endsWith(".zip", Qt::CaseInsensitive));
        if (name == "安全卸载选中的 U 盘")
            action->setEnabled(
                !busy && sidebar->currentItem() &&
                !sidebar->currentItem()->data(Qt::UserRole + 1).toMap().value("mount").toString().isEmpty());
    }
    clipboardPanel->setVisible(!clipboard.isEmpty());
    clipboardInfo->setText(
        QString("%1 %2 项 · 到目标目录后粘贴").arg(cutting ? "待移动" : "待复制").arg(clipboard.size()));
    const auto count = sorted.rowCount(table->rootIndex());
    selectionInfo->setText(QString("%1 项%2%3 · %4 %5")
                               .arg(count)
                               .arg(any ? QString(" · 已选 %1 项").arg(paths.size()) : QString())
                               .arg(readOnly ? " · 只读" : "")
                               .arg(QStringList{"名称", "大小", "类型", "修改"}.value(sorted.sortColumn()))
                               .arg(sorted.sortOrder() == Qt::AscendingOrder ? "↑" : "↓"));
    emptyInfo->setText(navigation.isRunning() ? "正在读取目录…" : "此目录为空");
    emptyInfo->setVisible(navigation.isRunning() || count == 0);
}
void FileWindow::open(bool edit) {
    const auto path = selected();
    if (path.isEmpty())
        return;
    if (model.isDir(model.index(path))) {
        navigate(path);
        return;
    }
    if (worker.isRunning())
        return;
    if (!edit && path.endsWith(".zip", Qt::CaseInsensitive)) {
        zip(true);
        return;
    }
    Preview preview(path, edit, this);
    preview.exec();
}
void FileWindow::details() {
    const auto path = selected();
    if (path.isEmpty())
        return;
    auto *watcher = new QFutureWatcher<QString>(this);
    connect(watcher, &QFutureWatcherBase::finished, this, [this, watcher] {
        const auto text = watcher->result();
        watcher->deleteLater();
        QMessageBox box(QMessageBox::Information, "属性", text, QMessageBox::Ok, this);
        box.setTextFormat(Qt::PlainText);
        box.exec();
    });
    watcher->setFuture(QtConcurrent::run([path] { return Files::properties(path); }));
}
void FileWindow::create(bool directory) {
    if (worker.isRunning())
        return;
    if (!directory) {
        Preview editor({}, true, this);
        editor.setProperty("saveDirectory", folder);
        editor.exec();
        return;
    }
    bool ok = false;
    const auto name = QInputDialog::getText(this, "新建目录", "名称", QLineEdit::Normal, {}, &ok);
    if (ok) {
        const auto parent = folder;
        run("新建目录",
            [parent, name](std::atomic_bool &, const Files::Progress &) { return Files::makeDirectory(parent, name); });
    }
}
void FileWindow::rename() {
    const auto path = selected();
    if (path.isEmpty())
        return;
    bool ok = false;
    const auto name =
        QInputDialog::getText(this, "重命名", "新名称", QLineEdit::Normal, QFileInfo(path).fileName(), &ok);
    if (ok)
        run("重命名", [path, name](std::atomic_bool &, const Files::Progress &) { return Files::rename(path, name); });
}
void FileWindow::run(const QString &title, std::function<QString(std::atomic_bool &, const Files::Progress &)> task,
                     std::function<void(bool)> finished) {
    if (worker.isRunning())
        return;
    cancel = std::make_shared<std::atomic_bool>(false);
    taskProgress = std::make_shared<TaskProgress>();
    taskProgress->item = title;
    taskInfo->setText(title + "…");
    taskBar->setValue(0);
    taskPanel->show();
    taskTimer.start();
    connect(
        &worker, &QFutureWatcherBase::finished, this,
        [this, title, finished] {
            taskTimer.stop();
            const auto error = worker.result();
            taskBar->setValue(error.isEmpty() ? 100 : 0);
            const auto text = error.isEmpty() ? title + "完成" : error;
            taskInfo->setText(taskInfo->fontMetrics().elidedText(text, Qt::ElideMiddle, taskInfo->width()));
            taskInfo->setToolTip(text);
            if (finished)
                finished(error.isEmpty());
            updateActions();
        },
        Qt::SingleShotConnection);
    worker.setFuture(QtConcurrent::run([task, flag = cancel, snapshot = taskProgress] {
        return task(*flag, [snapshot](const QString &item, qint64 done, qint64 total) {
            QMutexLocker lock(&snapshot->mutex);
            snapshot->item = item;
            snapshot->done = done;
            snapshot->total = total;
        });
    }));
    updateActions();
}
void FileWindow::clipboardSelection(bool cut) {
    const auto paths = selectedPaths();
    if (paths.isEmpty())
        return;
    clipboard = paths;
    cutting = cut;
    updateActions();
}
void FileWindow::paste() {
    if (clipboard.isEmpty() || worker.isRunning())
        return;
    const auto sources = clipboard;
    const auto destination = folder;
    const bool move = cutting;
    auto remaining = std::make_shared<QStringList>(sources);
    run(
        move ? "移动" : "复制",
        [sources, destination, move, remaining](std::atomic_bool &flag, const Files::Progress &progress) {
            for (const auto &source : sources) {
                const auto error = Files::transfer(source, QDir(destination).filePath(QFileInfo(source).fileName()),
                                                   move, flag, progress);
                if (!error.isEmpty())
                    return error + "\n已完成条目保留；剩余条目未操作。";
                remaining->removeFirst();
            }
            return QString();
        },
        [this, sources, move, remaining](bool) {
            if (move && clipboard == sources)
                clipboard = *remaining;
        });
}
void FileWindow::zip(bool extract) {
    const auto sources = selectedPaths();
    if (sources.isEmpty() || worker.isRunning())
        return;
    bool ok = false;
    auto suggested = extract               ? QFileInfo(sources.first()).completeBaseName()
                     : sources.size() == 1 ? QFileInfo(sources.first()).fileName() + ".zip"
                                           : QString("Archive.zip");
    const auto name =
        QInputDialog::getText(this, extract ? "解压到新目录" : "压缩为 ZIP",
                              extract ? "当前目录内的新文件夹名称（不覆盖）" : "当前目录内的 ZIP 文件名（不覆盖）",
                              QLineEdit::Normal, suggested, &ok);
    if (!ok)
        return;
    if (!Files::validName(name)) {
        showError("名称无效。");
        return;
    }
    const auto destination =
        QDir(folder).filePath(!extract && !name.endsWith(".zip", Qt::CaseInsensitive) ? name + ".zip" : name);
    run(extract ? "解压 ZIP" : "压缩 ZIP",
        [sources, destination, extract](std::atomic_bool &flag, const Files::Progress &progress) {
            return extract ? Files::unpackZip(sources.first(), destination, flag, progress)
                           : Files::packZip(sources, destination, flag, progress);
        });
}
void FileWindow::remove(bool permanent) {
    const auto paths = selectedPaths();
    if (paths.isEmpty() || worker.isRunning())
        return;
    QMessageBox box(QMessageBox::Warning, permanent ? "永久删除，无法恢复" : "移入回收站",
                    QString("%1 项\n").arg(paths.size()) + paths.mid(0, 4).join('\n'),
                    QMessageBox::Yes | QMessageBox::Cancel, this);
    box.setTextFormat(Qt::PlainText);
    box.setDefaultButton(QMessageBox::Cancel);
    if (box.exec() == QMessageBox::Yes)
        run(permanent ? "删除" : "移入回收站",
            [paths, permanent](std::atomic_bool &flag, const Files::Progress &progress) {
                for (const auto &path : paths) {
                    progress(path, 0, 0);
                    const auto error = Files::remove(path, permanent, flag);
                    if (!error.isEmpty())
                        return error;
                }
                return QString();
            });
}
void FileWindow::closeEvent(QCloseEvent *event) {
    if (worker.isRunning()) {
        event->ignore();
        statusBar()->showMessage("请先完成或取消当前文件任务，再关闭。", 5000);
    } else if (preferencesWrite.isRunning() || pendingPreferences) {
        closing = true;
        event->ignore();
    } else
        event->accept();
}
void FileWindow::controllerAction(const QString &name) {
    if (QApplication::activeModalWidget() || QApplication::activePopupWidget()) {
        auto *focus = QApplication::focusWidget();
        if (!focus)
            return;
        const int key = name == "accept"  ? Qt::Key_Return
                        : name == "back"  ? Qt::Key_Escape
                        : name == "up"    ? Qt::Key_Up
                        : name == "down"  ? Qt::Key_Down
                        : name == "left"  ? Qt::Key_Left
                        : name == "right" ? Qt::Key_Right
                                          : 0;
        if (key) {
            QKeyEvent event(QEvent::KeyPress, key, Qt::NoModifier);
            QApplication::sendEvent(focus, &event);
        }
        return;
    }
    if (name == "accept") {
        if (sidebar->hasFocus() && sidebar->currentItem())
            sidebar->itemActivated(sidebar->currentItem());
        else if (multiSelect) {
            auto *selection = table->selectionModel();
            selection->select(selection->currentIndex(), QItemSelectionModel::Toggle | QItemSelectionModel::Rows);
        } else
            open();
    } else if (name == "back") {
        if (sidebar->hasFocus()) {
            sidebar->hide();
            findChild<QAction *>("showPlaces")->setChecked(false);
            views->currentWidget()->setFocus();
            storeView();
        } else
            navigate(QFileInfo(folder).absolutePath());
    } else if (name == "favorite") {
        showActions();
    } else if (name == "erase") {
        views->setCurrentIndex(1 - views->currentIndex());
        findChild<QAction *>("detailsView")->setChecked(views->currentIndex() == 1);
        storeView();
    } else if (name == "quick") {
        multiSelect = !multiSelect;
        statusBar()->showMessage(multiSelect ? "多选：方向移动焦点 · B 勾选 · Select 结束"
                                             : "Y 菜单 · B 打开 · Select 多选");
    } else if (name == "submit" && worker.isRunning()) {
        *cancel = true;
        taskInfo->setText("正在取消，请稍候…");
    } else if (name == "previousTab" || name == "nextTab") {
        sidebar->show();
        findChild<QAction *>("showPlaces")->setChecked(true);
        sidebar->setCurrentRow(qBound(0, sidebar->currentRow() + (name == "nextTab" ? 1 : -1), sidebar->count() - 1));
        sidebar->setFocus();
    } else {
        auto *focus = QApplication::focusWidget();
        if (!focus)
            return;
        const int key = name == "up"      ? Qt::Key_Up
                        : name == "down"  ? Qt::Key_Down
                        : name == "left"  ? Qt::Key_Left
                        : name == "right" ? Qt::Key_Right
                                          : 0;
        if (key) {
            QKeyEvent press(QEvent::KeyPress, key,
                            multiSelect && views->isAncestorOf(focus) ? Qt::ControlModifier : Qt::NoModifier);
            QApplication::sendEvent(focus, &press);
        }
    }
}
QModelIndex FileWindow::fileIndex(const QString &path) const {
    return sorted.mapFromSource(model.index(path));
}
void FileWindow::showActions() {
    updateActions();
    auto *view = qobject_cast<QAbstractItemView *>(views->currentWidget());
    const auto rect = view->visualRect(view->currentIndex());
    showActionsAt(rect.isValid() ? view->viewport()->mapToGlobal(rect.bottomLeft())
                                 : mapToGlobal(QPoint(width() - 48, 44)));
}
void FileWindow::showActionsAt(QPoint position) {
    updateActions();
    const auto corner = mapToGlobal(QPoint(0, 0));
    const auto size = menu->sizeHint();
    position.setX(qBound(corner.x(), position.x(), corner.x() + qMax(0, width() - size.width())));
    position.setY(qBound(corner.y(), position.y(), corner.y() + qMax(0, height() - size.height())));
    menu->exec(position);
}
