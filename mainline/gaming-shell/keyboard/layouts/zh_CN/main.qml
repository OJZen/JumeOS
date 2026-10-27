import QtQuick
import QtQuick.VirtualKeyboard

// §8 keyboard, 拼音: the Latin grid with Qt's pinyin input method and its candidate list.
KeyboardLayout {
    function createInputMethod() {
        return Qt.createQmlObject('import QtQuick; import QtQuick.VirtualKeyboard.Plugins; PinyinInputMethod {}', parent, "pinyin.qml")
    }
    sharedLayouts: ["symbols"]
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
        Key { key: Qt.Key_Period; text: "。"; alternativeKeys: "。." }
        EnterKey { weight: 200 }
    }
}
