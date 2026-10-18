import QtQuick
import QtQuick.Controls.Basic
import "../theme"

TextField {
    id: root

    property string label

    implicitWidth: 640
    implicitHeight: 72
    leftPadding: 24
    rightPadding: 24
    topPadding: label ? 30 : 0
    color: Theme.text
    placeholderTextColor: Theme.textDim
    selectionColor: Theme.accent
    font.pixelSize: Theme.fontBody
    verticalAlignment: TextInput.AlignVCenter
    inputMethodHints: Qt.ImhNoPredictiveText

    background: Rectangle {
        radius: Theme.radius
        color: Theme.surface
        border.width: root.activeFocus ? 4 : 1
        border.color: root.activeFocus ? Theme.focus : Theme.surfaceHigh

        Text {
            visible: root.label.length > 0
            x: 24
            y: 8
            text: root.label
            color: root.activeFocus ? Theme.text : Theme.textDim
            font.pixelSize: Theme.fontSmall - 2
        }
    }
}
