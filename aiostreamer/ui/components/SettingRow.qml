import QtQuick
import "../theme"

Rectangle {
    id: root

    property string label
    property string hint
    property var options: []
    property var value

    signal picked(var value)

    readonly property int currentIndex: {
        for (var i = 0; i < options.length; i++) {
            if (options[i].value === value)
                return i
        }
        return 0
    }

    function step(delta) {
        if (options.length === 0)
            return
        var next = (currentIndex + delta + options.length) % options.length
        picked(options[next].value)
    }

    activeFocusOnTab: true
    width: parent ? parent.width : 800
    height: hint ? 92 : 72
    radius: Theme.radius
    color: activeFocus ? Theme.focus : Theme.surface

    Column {
        anchors { left: parent.left; leftMargin: 28; verticalCenter: parent.verticalCenter }
        spacing: 4
        Text {
            text: root.label
            color: root.activeFocus ? Theme.focusText : Theme.text
            font.pixelSize: Theme.fontBody
            font.bold: true
        }
        Text {
            visible: root.hint.length > 0
            text: root.hint
            color: root.activeFocus ? Theme.focusText : Theme.textDim
            font.pixelSize: Theme.fontSmall
        }
    }

    Row {
        anchors { right: parent.right; rightMargin: 28; verticalCenter: parent.verticalCenter }
        spacing: 18
        Text {
            text: "‹"
            visible: root.activeFocus
            color: Theme.focusText
            font.pixelSize: Theme.fontRow
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            text: root.options.length > 0 ? root.options[root.currentIndex].text : ""
            color: root.activeFocus ? Theme.focusText : Theme.accent
            font.pixelSize: Theme.fontBody
            font.bold: true
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            text: "›"
            visible: root.activeFocus
            color: Theme.focusText
            font.pixelSize: Theme.fontRow
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    Keys.onLeftPressed: step(-1)
    Keys.onRightPressed: step(1)
    Keys.onReturnPressed: step(1)
    Keys.onEnterPressed: step(1)

    MouseArea {
        anchors.fill: parent
        onClicked: {
            root.forceActiveFocus()
            root.step(1)
        }
    }
}
