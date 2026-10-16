import QtQuick
import "../theme"

Rectangle {
    id: root

    property string text
    property string icon
    property bool primary: false
    property bool busy: false
    property bool dimmed: false

    signal clicked()

    function activate() {
        if (visible && enabled)
            clicked()
    }

    activeFocusOnTab: true
    implicitWidth: Math.max(160, label.implicitWidth + 64 + (busy ? 40 : 0))
    implicitHeight: 64
    radius: height / 2
    color: activeFocus ? (dimmed ? Theme.textDim : Theme.focus) : (primary && !dimmed ? Theme.accent : Theme.surfaceHigh)
    scale: activeFocus ? 1.06 : 1.0

    Behavior on scale { NumberAnimation { duration: Theme.animMs } }
    Behavior on color { ColorAnimation { duration: Theme.animMs } }

    Spinner {
        id: busySpinner
        visible: root.busy
        width: 26
        height: 26
        color: root.activeFocus ? Theme.focusText : Theme.accent
        anchors { verticalCenter: parent.verticalCenter; right: label.left; rightMargin: 14 }
    }

    Text {
        id: label
        anchors.centerIn: parent
        anchors.horizontalCenterOffset: root.busy ? 20 : 0
        text: (root.icon && !root.busy ? root.icon + "  " : "") + root.text
        color: root.activeFocus ? Theme.focusText : (root.dimmed ? Theme.textDim : Theme.text)
        font.pixelSize: Theme.fontButton
        font.bold: true
    }

    Keys.onReturnPressed: root.activate()
    Keys.onEnterPressed: root.activate()
    Keys.onSpacePressed: root.activate()

    MouseArea {
        anchors.fill: parent
        onClicked: {
            root.forceActiveFocus()
            root.activate()
        }
    }
}
