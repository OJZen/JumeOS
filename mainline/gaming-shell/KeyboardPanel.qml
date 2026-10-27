import QtQuick
import "controls" as Ui
import QtQuick.VirtualKeyboard
import QtQuick.VirtualKeyboard.Settings

InputPanel {
    id: panel
    property bool reducedMotion: Ui.Theme.reducedMotion
    function navigateHorizontal(action) {
        const area = keyboard.keyboardInputArea
        if (!keyboard.navigationModeActive || !area.initialKey || keyboard.languagePopupListActive
                || keyboard.alternativeKeys.active || keyboard.wordCandidateContextMenu.active) return false
        const direction = keyboard.wordCandidateView.effectiveLayoutDirection === Qt.LeftToRight ? 1 : -1
        area.navigateToNextKey((action === "left" ? -1 : 1) * direction, 0, true)
        return true
    }
    // §7.4 keyboard keys outside the key grid: X 大小写, L2 中/英, R2 符号. Shift uses the same
    // Qt 6.8.2 handler as the on-screen shift key; the packaged keyboard check guards it.
    function toggleShift() { InputContext.priv.shiftHandler.toggleShift() }
    function toggleLanguage() { VirtualKeyboardSettings.locale = VirtualKeyboardSettings.locale === "zh_CN" ? "en_GB" : "zh_CN" }
    function toggleSymbols() { keyboard.symbolMode = !keyboard.symbolMode }
    // Same pinned Qt 6.8.2 adapter as the layout cache; checked with the packaged IME.
    Binding { target: panel.keyboard.style; property: "navigationHighlightColor"; value: Ui.Theme.focus }
    Binding { target: panel.keyboard; property: "noAnimations"; value: panel.reducedMotion }
    // Application integration: one panel, no extra EGLFS window.
    Component.onCompleted: {
        // Qt 6.8.2 internal loader: cache keys separately from the moving focus ring.
        // The packaged keyboard check guards this dependency when updating Qt.
        keyboard.keyboardLayoutLoader.layer.enabled = true
        VirtualKeyboardSettings.activeLocales = ["en_GB", "zh_CN"]
        VirtualKeyboardSettings.locale = "en_GB"
    }
}
