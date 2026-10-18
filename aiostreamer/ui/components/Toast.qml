import QtQuick
import "../theme"

Rectangle {
    id: root

    function show(message) {
        label.text = message
        opacity = 1
        hideTimer.restart()
    }

    anchors.horizontalCenter: parent.horizontalCenter
    anchors.bottom: parent.bottom
    anchors.bottomMargin: 64
    width: Math.min(parent.width - 2 * Theme.margin, label.implicitWidth + 64)
    height: label.implicitHeight + 32
    radius: Theme.radius
    color: Theme.surfaceHigh
    border.color: Theme.accent
    border.width: 2
    opacity: 0
    visible: opacity > 0
    z: 100

    Behavior on opacity { NumberAnimation { duration: 200 } }

    Text {
        id: label
        anchors.centerIn: parent
        width: Math.min(implicitWidth, root.parent.width - 2 * Theme.margin - 64)
        color: Theme.text
        font.pixelSize: Theme.fontBody
        wrapMode: Text.WordWrap
    }

    Timer {
        id: hideTimer
        interval: 4000
        onTriggered: root.opacity = 0
    }
}
