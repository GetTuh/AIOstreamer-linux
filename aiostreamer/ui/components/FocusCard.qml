import QtQuick
import QtQuick.Window
import "../theme"

Item {
    id: root

    property string title
    property string subtitle
    property string source
    property real progress: 0
    property bool played: false
    property int unplayed: 0
    property bool landscape: false
    property bool current: false

    signal clicked()

    width: landscape ? Theme.thumbWidth : Theme.posterWidth
    height: frame.height + Theme.labelHeight
    z: current ? 2 : 1

    Rectangle {
        id: frame
        width: parent.width
        height: root.landscape ? Theme.thumbHeight : Theme.posterHeight
        color: Theme.surface
        radius: Theme.radius
        scale: root.current ? Theme.focusScale : 1.0
        transformOrigin: Item.Center
        antialiasing: true

        Behavior on scale { NumberAnimation { duration: Theme.animMs; easing.type: Easing.OutCubic } }

        Text {
            anchors.centerIn: parent
            width: parent.width - 24
            visible: art.status !== Image.Ready
            text: root.title
            color: Theme.textDim
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            maximumLineCount: 3
            elide: Text.ElideRight
        }

        Image {
            id: art
            anchors.fill: parent
            anchors.margins: 0
            source: root.source
            sourceSize.width: Math.round(width * Screen.devicePixelRatio)
            fillMode: Image.PreserveAspectCrop
            asynchronous: true
            cache: true
            smooth: true
            opacity: status === Image.Ready ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: 180 } }
        }

        Rectangle {
            visible: root.progress > 0 && !root.played
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom; margins: 8 }
            height: 6
            radius: 3
            color: "#80000000"
            Rectangle {
                width: parent.width * root.progress
                height: parent.height
                radius: 3
                color: Theme.accent
            }
        }

        Rectangle {
            visible: root.played || root.unplayed > 0
            anchors { top: parent.top; right: parent.right; margins: 8 }
            height: 30
            width: Math.max(30, badgeText.implicitWidth + 14)
            radius: 15
            color: Theme.accent
            Text {
                id: badgeText
                anchors.centerIn: parent
                text: root.played ? "✓" : root.unplayed
                color: "white"
                font.pixelSize: 16
                font.bold: true
            }
        }

        Rectangle {
            anchors.fill: parent
            anchors.margins: -5
            radius: Theme.radius + 4
            color: "transparent"
            border.color: Theme.focus
            border.width: 4
            visible: root.current
        }
    }

    Column {
        anchors { top: frame.bottom; topMargin: 14; left: parent.left; right: parent.right }
        spacing: 2
        Text {
            width: parent.width
            text: root.title
            color: root.current ? Theme.text : Theme.textDim
            font.pixelSize: Theme.fontBody
            font.bold: root.current
            elide: Text.ElideRight
        }
        Text {
            width: parent.width
            text: root.subtitle
            visible: text.length > 0
            color: Theme.textDim
            font.pixelSize: Theme.fontSmall
            elide: Text.ElideRight
        }
    }

    MouseArea {
        anchors.fill: frame
        onClicked: root.clicked()
    }
}
