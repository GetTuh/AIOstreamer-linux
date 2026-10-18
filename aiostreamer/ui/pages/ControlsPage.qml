import QtQuick
import QtQuick.Controls
import "../theme"
import "../components"

FocusScope {
    id: page
    objectName: "controlsPage"

    Component.onCompleted: list.forceActiveFocus()
    StackView.onActivated: list.forceActiveFocus()
    Component.onDestruction: app.keys.cancelCapture()

    Text {
        id: heading
        x: Theme.margin
        y: 36
        text: "Keys and remote buttons"
        color: Theme.text
        font.pixelSize: Theme.fontTitle
        font.bold: true
    }

    Text {
        id: help
        x: Theme.margin
        anchors { top: heading.bottom; topMargin: 12 }
        width: page.width - 2 * Theme.margin
        text: app.keys.capturing
              ? "Press the key or remote button to add…"
              : "OK adds a key to an action (a key used elsewhere moves here). Right, then OK resets a changed action."
        color: app.keys.capturing ? Theme.accent : Theme.textDim
        font.pixelSize: Theme.fontBody
        font.bold: app.keys.capturing.length > 0
        wrapMode: Text.WordWrap
    }

    ListView {
        id: list
        objectName: "keysList"
        anchors { top: help.bottom; topMargin: 28; bottom: resetAll.top; bottomMargin: 24; left: parent.left; right: parent.right }
        leftMargin: Theme.margin
        rightMargin: Theme.margin
        clip: true
        spacing: 10
        model: app.keys.actions
        keyNavigationEnabled: true
        highlightMoveDuration: 120
        preferredHighlightBegin: 120
        preferredHighlightEnd: height - 120
        highlightRangeMode: ListView.ApplyRange

        property bool onReset: false
        property int savedIndex: 0
        onCurrentIndexChanged: onReset = false
        onModelChanged: currentIndex = Math.min(savedIndex, count - 1)

        section.property: "context"
        section.delegate: Text {
            required property string section
            topPadding: 18
            bottomPadding: 6
            text: section === "app" ? "Browsing" : "Player"
            color: Theme.textDim
            font.pixelSize: Theme.fontRow
            font.bold: true
        }

        delegate: Rectangle {
            id: row
            required property var modelData
            required property int index
            readonly property bool current: ListView.isCurrentItem && list.activeFocus
            readonly property bool capturing: app.keys.capturing === modelData.action
            width: Math.min(1100, list.width - 2 * Theme.margin)
            height: 72
            radius: Theme.radius
            color: current && !list.onReset ? Theme.focus : Theme.surface

            Text {
                anchors { left: parent.left; leftMargin: 28; verticalCenter: parent.verticalCenter }
                text: row.modelData.label
                color: row.current && !list.onReset ? Theme.focusText : Theme.text
                font.pixelSize: Theme.fontBody
                font.bold: true
            }

            Row {
                anchors { right: parent.right; rightMargin: 20; verticalCenter: parent.verticalCenter }
                spacing: 20
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    width: Math.min(implicitWidth, 560)
                    elide: Text.ElideRight
                    text: row.capturing ? "Press a key…" : row.modelData.keys
                    color: row.current && !list.onReset ? Theme.focusText : Theme.accent
                    font.pixelSize: Theme.fontBody
                    font.bold: true
                }
                Rectangle {
                    visible: row.modelData.custom
                    anchors.verticalCenter: parent.verticalCenter
                    width: resetLabel.implicitWidth + 36
                    height: 48
                    radius: 24
                    color: row.current && list.onReset ? Theme.focus : Theme.surfaceHigh
                    Text {
                        id: resetLabel
                        anchors.centerIn: parent
                        text: "Reset"
                        color: row.current && list.onReset ? Theme.focusText : Theme.text
                        font.pixelSize: Theme.fontSmall
                        font.bold: true
                    }
                    MouseArea {
                        anchors.fill: parent
                        onClicked: {
                            list.savedIndex = row.index
                            app.keys.reset(row.modelData.action)
                        }
                    }
                }
            }

            MouseArea {
                anchors.fill: parent
                z: -1
                onClicked: {
                    list.currentIndex = row.index
                    list.savedIndex = row.index
                    list.forceActiveFocus()
                    app.keys.capture(row.modelData.action)
                }
            }
        }

        function activate() {
            savedIndex = currentIndex
            var entry = model[currentIndex]
            if (onReset && entry.custom) {
                app.keys.reset(entry.action)
                onReset = false
            } else {
                app.keys.capture(entry.action)
            }
        }

        Keys.onReturnPressed: activate()
        Keys.onEnterPressed: activate()
        Keys.onRightPressed: if (model[currentIndex].custom) onReset = true
        Keys.onLeftPressed: onReset = false
        Keys.onDownPressed: (event) => {
            if (currentIndex === count - 1)
                resetAll.forceActiveFocus()
            else
                event.accepted = false
        }
    }

    TvButton {
        id: resetAll
        x: Theme.margin
        anchors { bottom: parent.bottom; bottomMargin: 36 }
        icon: "↺"
        text: "Reset all keys"
        KeyNavigation.up: list
        onClicked: {
            list.savedIndex = 0
            app.keys.reset("")
        }
    }
}
