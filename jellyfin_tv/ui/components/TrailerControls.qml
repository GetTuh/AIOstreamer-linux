import QtQuick
import "../theme"

FocusScope {
    id: root

    property Item hero
    property Item returnFocus
    readonly property bool open: hero !== null && hero.expanded

    visible: open

    function enter(from) {
        if (!hero || !hero.supported || open)
            return
        returnFocus = from
        hero.watch()
        hero.expanded = true
        if (hero.status === "none")
            closeTimer.restart()
        forceActiveFocus()
        hint.opacity = 1
        hintTimer.restart()
    }

    function exit() {
        if (!open)
            return
        hero.expanded = false
        if (returnFocus && returnFocus.visible)
            returnFocus.forceActiveFocus()
    }

    Connections {
        target: root.hero
        function onEnded() { root.exit() }
        function onStatusChanged() { if (root.open && root.hero.status === "none") closeTimer.restart() }
    }

    Keys.onPressed: (event) => {
        switch (event.key) {
        case Qt.Key_Left:
            hero.seek(-10000)
            break
        case Qt.Key_Right:
            hero.seek(10000)
            break
        case Qt.Key_Return:
        case Qt.Key_Enter:
        case Qt.Key_Space:
        case Qt.Key_MediaTogglePlayPause:
            hero.togglePause()
            break
        case Qt.Key_Escape:
        case Qt.Key_Back:
        case Qt.Key_Backspace:
        case Qt.Key_T:
        case Qt.Key_Up:
        case Qt.Key_Down:
            exit()
            break
        default:
            return
        }
        event.accepted = true
        hint.opacity = 1
        hintTimer.restart()
    }

    Timer {
        id: closeTimer
        interval: 1800
        onTriggered: root.exit()
    }

    Timer {
        id: hintTimer
        interval: 3000
        onTriggered: hint.opacity = 0
    }

    Rectangle {
        anchors.centerIn: parent
        width: loading.implicitWidth + 96
        height: loading.implicitHeight + 72
        radius: 24
        color: Theme.scrim
        visible: loading.visible
    }

    Column {
        id: loading
        anchors.centerIn: parent
        spacing: 28
        visible: root.hero !== null && !root.hero.showing
        Spinner {
            anchors.horizontalCenter: parent.horizontalCenter
            visible: root.hero !== null && root.hero.status !== "none"
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.hero !== null && root.hero.status === "none" ? "No trailer found" : "Loading trailer…"
            color: Theme.text
            font.pixelSize: Theme.fontRow
        }
    }

    Rectangle {
        anchors.centerIn: parent
        width: 140
        height: 140
        radius: 70
        color: Theme.scrim
        visible: root.hero !== null && root.hero.paused
        Text {
            anchors.centerIn: parent
            text: "❚❚"
            color: Theme.text
            font.pixelSize: 52
        }
    }

    Rectangle {
        id: hint
        anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 56 }
        width: hintText.implicitWidth + 56
        height: 60
        radius: 30
        color: Theme.scrim
        Behavior on opacity { NumberAnimation { duration: 400 } }
        Text {
            id: hintText
            anchors.centerIn: parent
            text: "◀ ▶  Seek     ·     OK  Pause     ·     Back  Close"
            color: Theme.text
            font.pixelSize: Theme.fontBody
        }
    }
}
