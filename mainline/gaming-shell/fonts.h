#pragma once
#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QFont>
#include <QFontDatabase>
#include <QGuiApplication>

// Jume UI v1 uses Noto Sans SC Regular/Medium/Bold (interface-fonts.py installs them);
// Droid Sans Fallback stays registered for glyphs outside the Simplified Chinese subset.
// R46H_UI_FONT_DIR lets host previews and checks use the verified cache copy.
inline bool registerInterfaceFonts() {
    const auto shared = QCoreApplication::applicationDirPath() + "/../share/fonts/";
    if (QFileInfo::exists(shared + "truetype/droid/DroidSansFallbackFull.ttf"))
        QFontDatabase::addApplicationFont(shared + "truetype/droid/DroidSansFallbackFull.ttf");
    QStringList directories{shared + "opentype/noto"};
    if (qEnvironmentVariableIsSet("R46H_UI_FONT_DIR")) directories.prepend(qEnvironmentVariable("R46H_UI_FONT_DIR"));
    for (const auto &directory : directories) {
        int loaded = 0;
        for (const auto *weight : {"Regular", "Medium", "Bold"}) {
            const auto path = QDir(directory).filePath(QStringLiteral("NotoSansSC-%1.otf").arg(QLatin1String(weight)));
            if (QFileInfo::exists(path) && QFontDatabase::addApplicationFont(path) >= 0) ++loaded;
        }
        if (loaded) { QGuiApplication::setFont(QFont(QStringLiteral("Noto Sans SC"))); return loaded == 3; }
    }
    return false;
}
