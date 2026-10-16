import QtQuick
import QtQuick.Controls
import "../theme"
import "../components"

FocusScope {
    id: page

    function submit() {
        error.text = ""
        app.login(serverField.text, userField.text, passwordField.text)
    }

    readonly property var savedAccounts: app.accounts.filter(function (a) { return !a.active })
    readonly property bool quickConnecting: app.quickConnectCode.length > 0

    onQuickConnectingChanged: quickConnecting ? cancelQuick.forceActiveFocus() : focusFirstEmpty()

    function focusFirstEmpty() {
        if (accountRepeater.count > 0 && !app.loggedIn)
            accountRepeater.itemAt(0).forceActiveFocus()
        else if (!serverField.text)
            serverField.forceActiveFocus()
        else if (!userField.text)
            userField.forceActiveFocus()
        else
            passwordField.forceActiveFocus()
    }

    StackView.onActivated: focusFirstEmpty()
    Component.onCompleted: focusFirstEmpty()

    Connections {
        target: app
        function onLoginFailed(message) {
            error.text = message
            passwordField.forceActiveFocus()
            passwordField.selectAll()
        }
    }

    Column {
        anchors.centerIn: parent
        spacing: 24
        width: 640

        Text {
            text: "Jellyfin TV"
            color: Theme.text
            font.pixelSize: Theme.fontHuge
            font.bold: true
            anchors.horizontalCenter: parent.horizontalCenter
        }

        Text {
            text: app.loggedIn ? "Add another account" : (page.savedAccounts.length > 0 ? "Choose an account or sign in" : "Sign in to your server")
            color: Theme.textDim
            font.pixelSize: Theme.fontBody
            anchors.horizontalCenter: parent.horizontalCenter
            bottomPadding: 24
        }

        Column {
            width: parent.width
            spacing: 12
            visible: accountRepeater.count > 0

            Repeater {
                id: accountRepeater
                model: page.savedAccounts
                delegate: TvButton {
                    required property var modelData
                    required property int index
                    width: parent.width
                    icon: "●"
                    text: modelData.username + "  ·  " + modelData.server.replace(/^https?:\/\//, "")
                    KeyNavigation.up: index > 0 ? accountRepeater.itemAt(index - 1) : null
                    KeyNavigation.down: index < accountRepeater.count - 1 ? accountRepeater.itemAt(index + 1) : serverField
                    onClicked: app.switchAccount(modelData.key)
                }
            }

            Item { width: 1; height: 12 }
        }

        TvTextField {
            id: serverField
            width: parent.width
            label: "Server"
            text: app.serverUrl
            placeholderText: "http://server:8096"
            inputMethodHints: Qt.ImhUrlCharactersOnly | Qt.ImhNoAutoUppercase
            KeyNavigation.up: accountRepeater.count > 0 ? accountRepeater.itemAt(accountRepeater.count - 1) : null
            KeyNavigation.down: userField
            onAccepted: userField.forceActiveFocus()
        }

        TvTextField {
            id: userField
            width: parent.width
            label: "Username"
            text: app.settings.username
            inputMethodHints: Qt.ImhNoAutoUppercase | Qt.ImhNoPredictiveText
            KeyNavigation.up: serverField
            KeyNavigation.down: passwordField
            onAccepted: passwordField.forceActiveFocus()
        }

        TvTextField {
            id: passwordField
            width: parent.width
            label: "Password"
            echoMode: TextInput.Password
            KeyNavigation.up: userField
            KeyNavigation.down: signIn
            onAccepted: page.submit()
        }

        TvButton {
            id: signIn
            text: app.busy ? "Signing in…" : "Sign in"
            primary: true
            width: parent.width
            KeyNavigation.up: passwordField
            KeyNavigation.down: quickButton
            onClicked: page.submit()
        }

        TvButton {
            id: quickButton
            text: "Use Quick Connect"
            icon: "⌁"
            width: parent.width
            KeyNavigation.up: signIn
            onClicked: {
                error.text = ""
                app.startQuickConnect(serverField.text)
            }
        }

        Text {
            id: error
            width: parent.width
            color: Theme.danger
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
            visible: text.length > 0
        }
    }

    Rectangle {
        anchors.fill: parent
        visible: page.quickConnecting
        color: Theme.background

        Column {
            anchors.centerIn: parent
            spacing: 28
            width: 900

            Text {
                text: "Quick Connect"
                color: Theme.text
                font.pixelSize: Theme.fontHuge
                font.bold: true
                anchors.horizontalCenter: parent.horizontalCenter
            }

            Text {
                width: parent.width
                text: "On your phone or computer, open Jellyfin, go to Settings → Quick Connect and enter this code:"
                color: Theme.textDim
                font.pixelSize: Theme.fontBody
                wrapMode: Text.WordWrap
                horizontalAlignment: Text.AlignHCenter
            }

            Text {
                text: app.quickConnectCode
                color: Theme.accent
                font.pixelSize: 120
                font.bold: true
                font.letterSpacing: 24
                anchors.horizontalCenter: parent.horizontalCenter
            }

            Row {
                spacing: 16
                anchors.horizontalCenter: parent.horizontalCenter
                Spinner {
                    width: 30
                    height: 30
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: "Waiting for approval…"
                    color: Theme.textDim
                    font.pixelSize: Theme.fontBody
                    anchors.verticalCenter: parent.verticalCenter
                }
            }

            TvButton {
                id: cancelQuick
                text: "Cancel"
                anchors.horizontalCenter: parent.horizontalCenter
                onClicked: app.cancelQuickConnect()
                Keys.onEscapePressed: app.cancelQuickConnect()
                Keys.onBackPressed: app.cancelQuickConnect()
            }
        }
    }
}
