import QtQuick
import QtQuick.VirtualKeyboard

// §8 keyboard, Latin letters on the 20-column grid: ten keys, nine offset by half a key,
// ⇧ + seven + ⌫, then 123 · 中/英 · 空格 · . · 完成. The style draws the corner badges.
KeyboardLayout {
    keyWeight: 100
    KeyboardRow {
        Repeater {
            model: ["q", "w", "e", "r", "t", "y", "u", "i", "o", "p"]
            Key { required property string modelData; key: modelData.toUpperCase().charCodeAt(0); text: modelData }
        }
    }
    KeyboardRow {
        FillerKey { weight: 50 }
        Repeater {
            model: ["a", "s", "d", "f", "g", "h", "j", "k", "l"]
            Key { required property string modelData; key: modelData.toUpperCase().charCodeAt(0); text: modelData }
        }
        FillerKey { weight: 50 }
    }
    KeyboardRow {
        ShiftKey { weight: 150 }
        Repeater {
            model: ["z", "x", "c", "v", "b", "n", "m"]
            Key { required property string modelData; key: modelData.toUpperCase().charCodeAt(0); text: modelData }
        }
        BackspaceKey { weight: 150 }
    }
    KeyboardRow {
        SymbolModeKey { weight: 150; displayText: "123" }
        ChangeLanguageKey { weight: 150 }
        SpaceKey { weight: 400 }
        Key { key: Qt.Key_Period; text: "." }
        EnterKey { weight: 200 }
    }
}
