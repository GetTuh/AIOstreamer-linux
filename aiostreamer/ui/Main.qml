import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "theme"
import "components"
import "pages"

ApplicationWindow {
    id: window

    width: 1920
    height: 1080
    visible: true
    visibility: startWindowed ? Window.Windowed : Window.FullScreen
    title: "AIOstreamer"
    color: Theme.background

    readonly property color accent: Theme.accent
    onAccentChanged: app.setAccent(accent)
    Component.onCompleted: app.setAccent(accent)

    function goBack() {
        if (app.playback.busy)
            return
        if (stack.depth > 1)
            stack.pop()
        else if (app.loggedIn)
            quitDialog.open()
    }

    function openItem(entry) {
        if (!entry || !entry.itemId)
            return
        if (entry.itemType === "Catalog") {
            var c = entry.catalog || {}
            stack.push(libraryComponent, {
                catalogType: c.type || "",
                catalogId: c.id || "",
                genres: c.genres || [],
                genreRequired: !!c.genreRequired,
                title: c.title || entry.name
            })
            return
        }
        if (entry.itemType === "Series") {
            stack.push(showComponent, { itemId: entry.itemId })
            return
        }
        stack.push(detailsComponent, { itemId: entry.itemId })
    }

    function openSearch() {
        stack.push(searchComponent)
    }

    function openSettings() {
        stack.push(settingsComponent)
    }

    function showRoot() {
        if (!app.ready)
            return
        stack.replace(null, app.loggedIn ? homeComponent : loginComponent)
    }

    Loader {
        active: app.kirigami
        source: "KirigamiTheme.qml"
    }

    Connections {
        target: app
        function onSessionChanged() { window.showRoot() }
        function onMessage(text) { toast.show(text) }
    }

    StackView {
        id: stack
        objectName: "stack"
        anchors.fill: parent
        focus: true
        initialItem: splashComponent

        pushEnter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 160 } }
        pushExit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 160 } }
        popEnter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 160 } }
        popExit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 160 } }
        replaceEnter: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 200 } }
        replaceExit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: 200 } }

        Keys.onPressed: (event) => {
            if (event.key === Qt.Key_Escape || event.key === Qt.Key_Back || event.key === Qt.Key_Backspace) {
                event.accepted = true
                window.goBack()
            }
        }
    }

    Component {
        id: splashComponent
        FocusScope {
            Text {
                anchors.centerIn: parent
                text: "AIOstreamer"
                color: Theme.text
                font.pixelSize: Theme.fontHuge
                font.bold: true
            }
            Spinner {
                anchors.horizontalCenter: parent.horizontalCenter
                anchors.top: parent.verticalCenter
                anchors.topMargin: 80
            }
        }
    }

    Component {
        id: loginComponent
        LoginPage {}
    }

    Component {
        id: homeComponent
        HomePage {
            onOpenItem: (entry) => window.openItem(entry)
            onOpenSearch: window.openSearch()
            onOpenSettings: window.openSettings()
        }
    }

    Component {
        id: libraryComponent
        LibraryPage {
            onOpenItem: (entry) => window.openItem(entry)
        }
    }

    Component {
        id: detailsComponent
        DetailsPage {
            onOpenItem: (entry) => window.openItem(entry)
            onOpenSources: (model) => stack.push(sourcesComponent, { details: model })
        }
    }

    Component {
        id: showComponent
        ShowPage {
            onOpenItem: (entry) => window.openItem(entry)
        }
    }

    Component {
        id: sourcesComponent
        SourcePickerPage {}
    }

    Component {
        id: searchComponent
        SearchPage {
            onOpenItem: (entry) => window.openItem(entry)
        }
    }

    Component {
        id: settingsComponent
        SettingsPage {
            onAddAccount: stack.push(loginComponent)
        }
    }

    Rectangle {
        anchors.fill: parent
        visible: app.playback.busy
        color: Theme.scrim
        z: 50

        Column {
            anchors.centerIn: parent
            spacing: 32
            Spinner { anchors.horizontalCenter: parent.horizontalCenter }
            Text {
                text: "Starting playback…"
                color: Theme.text
                font.pixelSize: Theme.fontRow
            }
        }

        MouseArea { anchors.fill: parent }
    }

    ConfirmDialog {
        id: quitDialog
        title: "Quit AIOstreamer?"
        acceptText: "Quit"
        rejectText: "Cancel"
        onAccepted: app.quit()
        onClosed: stack.currentItem && stack.currentItem.forceActiveFocus()
    }

    Toast { id: toast }
}
