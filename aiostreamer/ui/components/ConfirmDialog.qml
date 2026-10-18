import QtQuick
import QtQuick.Controls.Basic
import "../theme"

Popup {
    id: root

    property string title
    property string acceptText: "OK"
    property string rejectText: "Cancel"

    signal accepted()

    parent: Overlay.overlay
    anchors.centerIn: parent
    modal: true
    focus: true
    padding: 48
    closePolicy: Popup.NoAutoClose

    background: Rectangle {
        radius: Theme.radius * 2
        color: Theme.surface
        border.color: Theme.surfaceHigh
        border.width: 2
    }

    Overlay.modal: Rectangle { color: Theme.scrim }

    onOpened: cancelButton.forceActiveFocus()

    contentItem: FocusScope {
        implicitWidth: column.implicitWidth
        implicitHeight: column.implicitHeight
        Keys.onEscapePressed: root.close()
        Keys.onBackPressed: root.close()
        Keys.onPressed: (event) => {
            if (event.key === Qt.Key_Backspace) {
                event.accepted = true
                root.close()
            }
        }

        Column {
            id: column
            spacing: 36
            Text {
                text: root.title
                color: Theme.text
                font.pixelSize: Theme.fontRow
                font.bold: true
                anchors.horizontalCenter: parent.horizontalCenter
            }
            Row {
                spacing: 24
                anchors.horizontalCenter: parent.horizontalCenter
                TvButton {
                    id: acceptButton
                    text: root.acceptText
                    KeyNavigation.right: cancelButton
                    onClicked: {
                        root.close()
                        root.accepted()
                    }
                }
                TvButton {
                    id: cancelButton
                    text: root.rejectText
                    KeyNavigation.left: acceptButton
                    onClicked: root.close()
                }
            }
        }
    }
}
