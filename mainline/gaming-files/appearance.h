#pragma once
#include <QApplication>
#include <QPainter>
#include <QPainterPath>
#include <QPalette>

// Native Widgets counterpart of gaming-shell/controls/Theme.qml, at 640×480.
// No blur, animated layout, per-row widgets or continuous idle animation.
inline void filesAppearance() {
    qApp->setStyle("Fusion");
    auto font = qApp->font();
    font.setPixelSize(16);
    qApp->setFont(font);
    QPalette p;
    p.setColor(QPalette::Window, QColor("#111a24"));
    p.setColor(QPalette::WindowText, QColor("#f1f6fa"));
    p.setColor(QPalette::Base, QColor("#1c2934"));
    p.setColor(QPalette::AlternateBase, QColor("#1c2934"));
    p.setColor(QPalette::Text, QColor("#f1f6fa"));
    p.setColor(QPalette::Button, QColor("#243b43"));
    p.setColor(QPalette::ButtonText, QColor("#f1f6fa"));
    p.setColor(QPalette::Highlight, QColor("#99efdb"));
    p.setColor(QPalette::HighlightedText, QColor("#173a35"));
    p.setColor(QPalette::ToolTipBase, QColor("#243b43"));
    p.setColor(QPalette::ToolTipText, QColor("#f1f6fa"));
    p.setColor(QPalette::PlaceholderText, QColor("#afc1cc"));
    for (auto role : {QPalette::Text, QPalette::WindowText, QPalette::ButtonText})
        p.setColor(QPalette::Disabled, role, QColor("#80939e"));
    qApp->setPalette(p);
    qApp->setEffectEnabled(Qt::UI_AnimateMenu, false);
    qApp->setEffectEnabled(Qt::UI_FadeMenu, false);
    qApp->setStyleSheet(QStringLiteral(R"(
        QToolBar { border: 0; spacing: 4px; background: transparent; }
        QToolButton, QPushButton { background: #243b43; border: 1px solid transparent; border-radius: 7px; padding: 5px 9px; min-height: 22px; }
        QToolButton:hover, QPushButton:hover { border-color: #40535f; }
        QToolButton:pressed, QPushButton:pressed, QToolButton:checked { background: #99efdb; color: #173a35; }
        QToolButton:focus, QPushButton:focus, QLineEdit:focus, QPlainTextEdit:focus { border: 1px solid #99efdb; }
        QToolButton:disabled, QPushButton:disabled { background: #1c2934; color: #80939e; }
        QLineEdit, QPlainTextEdit, QSpinBox { border: 1px solid #40535f; border-radius: 7px; padding: 6px; selection-background-color: #99efdb; selection-color: #173a35; }
        QAbstractItemView { border: 1px solid #243b43; border-radius: 9px; outline: 0; padding: 4px; }
        QAbstractItemView::item { min-height: 32px; padding: 2px 5px; border: 1px solid transparent; border-radius: 5px; }
        QAbstractItemView::item:hover { background: #243b43; }
        QAbstractItemView::item:selected { background: #99efdb; color: #173a35; }
        QAbstractItemView::item:focus { border-color: #99efdb; }
        QHeaderView::section { background: #1c2934; color: #afc1cc; border: 0; padding: 8px 5px; font-size: 13px; }
        QMenu { background: #1c2934; border: 1px solid #40535f; padding: 5px; }
        QMenu::item { padding: 7px 20px; border-radius: 4px; }
        QMenu::item:selected { background: #99efdb; color: #173a35; }
        QMenu::item:disabled { color: #80939e; }
        QMenu::separator { height: 1px; background: #40535f; margin: 4px 8px; }
        QScrollBar:vertical { width: 8px; background: transparent; margin: 0; }
        QScrollBar:horizontal { height: 8px; background: transparent; margin: 0; }
        QScrollBar::handle { background: #435765; border-radius: 4px; min-height: 20px; min-width: 20px; }
        QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
        QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
        QProgressBar { background: #435765; border: 0; border-radius: 2px; max-height: 4px; }
        QProgressBar::chunk { background: #99efdb; }
        QLabel#heading { font-size: 20px; font-weight: 600; }
        QLabel#caption, QLabel#selectionInfo, QStatusBar { color: #afc1cc; font-size: 13px; }
        QFrame#taskPanel, QFrame#clipboardPanel { background: #1c2934; border-radius: 8px; }
        QStatusBar::item { border: 0; }
        QSplitter::handle { background: transparent; }
    )"));
}

inline QIcon filesIcon(bool folder) {
    static const auto icons = [] {
        QList<QIcon> icons;
        for (bool isFolder : {false, true}) {
            QPixmap pixmap(24, 24);
            pixmap.fill(Qt::transparent);
            QPainter p(&pixmap);
            p.setRenderHint(QPainter::Antialiasing);
            p.setPen(QPen(QColor("#afc1cc"), 1.5, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
            QPainterPath path;
            if (isFolder) {
                path.moveTo(3, 7);
                path.lineTo(10, 7);
                path.lineTo(12, 9);
                path.lineTo(21, 9);
                path.lineTo(21, 20);
                path.lineTo(3, 20);
                path.closeSubpath();
            } else {
                path.moveTo(6, 3);
                path.lineTo(14, 3);
                path.lineTo(19, 8);
                path.lineTo(19, 21);
                path.lineTo(6, 21);
                path.closeSubpath();
                path.moveTo(14, 3);
                path.lineTo(14, 8);
                path.lineTo(19, 8);
                path.moveTo(9, 12);
                path.lineTo(16, 12);
                path.moveTo(9, 16);
                path.lineTo(16, 16);
            }
            p.drawPath(path);
            p.end();
            QIcon icon(pixmap);
            QPainter recolor(&pixmap);
            recolor.setCompositionMode(QPainter::CompositionMode_SourceIn);
            recolor.fillRect(pixmap.rect(), QColor("#173a35"));
            recolor.end();
            icon.addPixmap(pixmap, QIcon::Selected);
            icons << icon;
        }
        return icons;
    }();
    return icons[folder ? 1 : 0];
}

inline QIcon filesActionIcon(const QString &kind) {
    static QMap<QString, QIcon> cache;
    if (cache.contains(kind))
        return cache.value(kind);
    QPixmap pixmap(24, 24);
    pixmap.fill(Qt::transparent);
    QPainter p(&pixmap);
    p.setRenderHint(QPainter::Antialiasing);
    p.setPen(QPen(QColor("#afc1cc"), 1.6, Qt::SolidLine, Qt::RoundCap, Qt::RoundJoin));
    if (kind == "places") {
        p.drawRoundedRect(QRectF(3, 4, 18, 16), 2, 2);
        p.drawLine(9, 4, 9, 20);
    } else if (kind == "up") {
        p.drawLine(12, 20, 12, 4);
        p.drawLine(12, 4, 5, 11);
        p.drawLine(12, 4, 19, 11);
    } else if (kind == "view") {
        p.drawRoundedRect(QRectF(3, 4, 18, 16), 2, 2);
        p.drawLine(3, 10, 21, 10);
        p.drawLine(3, 15, 21, 15);
        p.drawLine(14, 4, 14, 20);
    } else if (kind == "close") {
        p.drawLine(6, 6, 18, 18);
        p.drawLine(18, 6, 6, 18);
    } else {
        p.setBrush(QColor("#afc1cc"));
        for (int x : {5, 12, 19})
            p.drawEllipse(QPoint(x, 12), 1, 1);
    }
    p.end();
    QIcon icon(pixmap);
    QPainter selected(&pixmap);
    selected.setCompositionMode(QPainter::CompositionMode_SourceIn);
    selected.fillRect(pixmap.rect(), QColor("#173a35"));
    selected.end();
    icon.addPixmap(pixmap, QIcon::Active, QIcon::On);
    icon.addPixmap(pixmap, QIcon::Normal, QIcon::On);
    cache[kind] = icon;
    return icon;
}
