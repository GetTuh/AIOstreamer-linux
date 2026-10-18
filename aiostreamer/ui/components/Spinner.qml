import QtQuick
import "../theme"

Item {
    id: root
    property bool running: visible
    property color color: Theme.accent
    width: 64
    height: 64

    Rectangle {
        anchors.fill: parent
        radius: width / 2
        color: "transparent"
        border.width: Math.max(2, root.width / 10)
        border.color: Theme.surfaceHigh
    }

    Rectangle {
        property real angle: 0
        readonly property real size: Math.max(6, root.width / 4)
        width: size
        height: size
        radius: size / 2
        color: root.color
        x: root.width / 2 - size / 2 + (root.width / 2 - size / 4) * Math.cos(angle * Math.PI / 180)
        y: root.height / 2 - size / 2 + (root.height / 2 - size / 4) * Math.sin(angle * Math.PI / 180)
        NumberAnimation on angle { from: 0; to: 360; duration: 900; loops: Animation.Infinite; running: root.running }
    }
}
