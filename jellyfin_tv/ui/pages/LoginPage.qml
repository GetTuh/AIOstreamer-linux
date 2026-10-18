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
    readonly property bool pastedManifest: serverField.text.indexOf("manifest.json") >= 0 || serverField.text.indexOf("stremio://") === 0

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
            if (page.pastedManifest) {
                serverField.forceActiveFocus()
            } else {
                passwordField.forceActiveFocus()
                passwordField.selectAll()
            }
        }
    }

    Column {
        anchors.centerIn: parent
        spacing: 24
        width: 760

        Text {
            text: "Jellyfin TV"
            color: Theme.text
            font.pixelSize: Theme.fontHuge
            font.bold: true
            anchors.horizontalCenter: parent.horizontalCenter
        }

        Text {
            text: app.loggedIn ? "Add another AIOStreams configuration" : (page.savedAccounts.length > 0 ? "Choose a configuration or sign in" : "Sign in to your AIOStreams configuration")
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
            label: "AIOStreams address"
            text: app.serverUrl
            placeholderText: "https://aiostreams.example.com"
            inputMethodHints: Qt.ImhUrlCharactersOnly | Qt.ImhNoAutoUppercase
            KeyNavigation.up: accountRepeater.count > 0 ? accountRepeater.itemAt(accountRepeater.count - 1) : null
            KeyNavigation.down: page.pastedManifest ? signIn : userField
            onAccepted: page.pastedManifest ? page.submit() : userField.forceActiveFocus()
        }

        TvTextField {
            id: userField
            visible: !page.pastedManifest
            width: parent.width
            label: "UUID or alias"
            text: app.settings.username
            inputMethodHints: Qt.ImhNoAutoUppercase | Qt.ImhNoPredictiveText
            KeyNavigation.up: serverField
            KeyNavigation.down: passwordField
            onAccepted: passwordField.forceActiveFocus()
        }

        TvTextField {
            id: passwordField
            visible: !page.pastedManifest
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
            KeyNavigation.up: page.pastedManifest ? serverField : passwordField
            onClicked: page.submit()
        }

        Text {
            width: parent.width
            text: "The UUID and password are the ones you set on your instance's configure page. "
                  + "You can also paste your full manifest URL into the address field."
            color: Theme.textDim
            font.pixelSize: Theme.fontSmall
            wrapMode: Text.WordWrap
            horizontalAlignment: Text.AlignHCenter
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
}
