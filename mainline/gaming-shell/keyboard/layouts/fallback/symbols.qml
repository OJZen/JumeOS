import QtQuick
import QtQuick.VirtualKeyboard

// §8 keyboard, digits and symbols (R2 or 123); the bottom row matches the letters.
KeyboardLayout {
    keyWeight: 100
    KeyboardRow {
        Repeater {
            model: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]
            Key { required property string modelData; text: modelData }
        }
    }
    KeyboardRow {
        Repeater {
            model: ["-", "/", ":", ";", "(", ")", "$", "&", "@", "\""]
            Key { required property string modelData; text: modelData }
        }
    }
    KeyboardRow {
        Repeater {
            model: ["_", "#", "%", "+", "=", "*", "?", "!", "'", ","]
            Key { required property string modelData; text: modelData }
        }
    }
    KeyboardRow {
        SymbolModeKey { weight: 150; displayText: "ABC" }
        ChangeLanguageKey { weight: 150 }
        SpaceKey { weight: 400 }
        Key { key: Qt.Key_Period; text: "." }
        EnterKey { weight: 200 }
    }
}
