import QtQuick
import "../theme"

FocusScope {
    id: root

    signal typed(string text)
    signal backspace()
    signal cleared()
    signal exitRight()

    readonly property var keys: [
        "a", "b", "c", "d", "e", "f",
        "g", "h", "i", "j", "k", "l",
        "m", "n", "o", "p", "q", "r",
        "s", "t", "u", "v", "w", "x",
        "y", "z", "1", "2", "3", "4",
        "5", "6", "7", "8", "9", "0",
        "space", "⌫", "clear", "-", "'", "."
    ]
    readonly property int keySize: 68

    implicitWidth: grid.width
    implicitHeight: grid.height

    function press(key) {
        if (key === "space")
            typed(" ")
        else if (key === "⌫")
            backspace()
        else if (key === "clear")
            cleared()
        else
            typed(key)
    }

    GridView {
        id: grid
        width: root.keySize * 6
        height: root.keySize * 7
        cellWidth: root.keySize
        cellHeight: root.keySize
        model: root.keys
        focus: true
        interactive: false
        keyNavigationEnabled: true
        currentIndex: 0

        delegate: Item {
            id: cell
            required property int index
            required property string modelData
            readonly property bool current: GridView.isCurrentItem && grid.activeFocus
            width: grid.cellWidth
            height: grid.cellHeight

            Rectangle {
                anchors.fill: parent
                anchors.margins: 4
                radius: Theme.radius
                color: cell.current ? Theme.focus : Theme.surface
                scale: cell.current ? 1.08 : 1
                Behavior on scale { NumberAnimation { duration: 90 } }

                Text {
                    anchors.centerIn: parent
                    text: cell.modelData === "space" ? "␣" : (cell.modelData === "clear" ? "✕" : cell.modelData.toUpperCase())
                    color: cell.current ? Theme.focusText : Theme.text
                    font.pixelSize: Theme.fontBody
                    font.bold: true
                }

                MouseArea {
                    anchors.fill: parent
                    onClicked: {
                        grid.currentIndex = cell.index
                        root.press(cell.modelData)
                    }
                }
            }
        }

        Keys.onReturnPressed: root.press(root.keys[currentIndex])
        Keys.onEnterPressed: root.press(root.keys[currentIndex])
        Keys.onRightPressed: (event) => {
            if (currentIndex % 6 === 5)
                root.exitRight()
            else
                moveCurrentIndexRight()
        }
    }
}
