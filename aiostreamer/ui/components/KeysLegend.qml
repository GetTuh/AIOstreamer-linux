import QtQuick
import QtQuick.Controls.Basic
import "../theme"

Popup {
    id: root

    signal customize()

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

    onOpened: customizeButton.forceActiveFocus()

    contentItem: FocusScope {
        implicitWidth: column.implicitWidth
        implicitHeight: column.implicitHeight
        Keys.onPressed: (event) => {
            if ([Qt.Key_Escape, Qt.Key_Back, Qt.Key_Backspace, Qt.Key_F1].indexOf(event.key) >= 0) {
                event.accepted = true
                root.close()
            }
        }

        Column {
            id: column
            spacing: 32

            Text {
                text: "Keys"
                color: Theme.text
                font.pixelSize: Theme.fontRow
                font.bold: true
            }

            Row {
                spacing: 72
                Repeater {
                    model: [{ context: "app", title: "Browsing" }, { context: "player", title: "Player" }]
                    delegate: Column {
                        required property var modelData
                        spacing: 10
                        Text {
                            text: modelData.title
                            color: Theme.accent
                            font.pixelSize: Theme.fontBody
                            font.bold: true
                        }
                        Repeater {
                            model: app.keys.actions.filter((a) => a.context === modelData.context)
                            delegate: Row {
                                required property var modelData
                                spacing: 24
                                Text {
                                    width: 260
                                    text: modelData.label
                                    color: Theme.textDim
                                    font.pixelSize: Theme.fontSmall
                                }
                                Text {
                                    width: 380
                                    text: modelData.keys
                                    color: Theme.text
                                    font.pixelSize: Theme.fontSmall
                                    font.bold: true
                                    wrapMode: Text.WordWrap
                                }
                            }
                        }
                    }
                }
            }

            Text {
                text: "Other mpv keys keep working in the player."
                color: Theme.textDim
                font.pixelSize: Theme.fontSmall
            }

            Row {
                spacing: 24
                TvButton {
                    id: customizeButton
                    text: "Change keys"
                    KeyNavigation.right: closeButton
                    onClicked: {
                        root.close()
                        root.customize()
                    }
                }
                TvButton {
                    id: closeButton
                    text: "Close"
                    KeyNavigation.left: customizeButton
                    onClicked: root.close()
                }
            }
        }
    }
}
