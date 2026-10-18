import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "../theme"
import "../components"
import JellyfinTV

FocusScope {
    id: page

    property string itemId
    readonly property alias d: details
    property bool focusedOnce: false

    signal openItem(var entry)
    signal openSources(var model)

    property real chrome: trailerControls.open ? 0 : 1
    Behavior on chrome { NumberAnimation { duration: 450; easing.type: Easing.InOutQuad } }

    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_T && hero.supported) {
            event.accepted = true
            trailerControls.enter(Window.activeFocusItem)
        }
    }

    DetailsModel {
        id: details
        itemId: page.itemId
        onUserDataChanged: (changedId) => app.notifyChanged(changedId)
        onPlayRequested: (seconds, sourceId) => app.playSource(page.itemId, seconds, sourceId)
    }

    Component.onCompleted: page.forceActiveFocus()
    StackView.onActivated: focusButtons()

    function primaryButton() {
        if (resumeButton.visible)
            return resumeButton
        if (playButton.visible)
            return playButton
        return watchedButton
    }

    function focusButtons() {
        if (!details.loaded) {
            page.forceActiveFocus()
            return
        }
        var current = buttonRow.children
        for (var i = 0; i < current.length; i++) {
            if (current[i].activeFocus && current[i].visible)
                return
        }
        primaryButton().forceActiveFocus()
    }

    Connections {
        target: details
        function onChanged() {
            if (!details.loaded)
                return
            if (!page.focusedOnce) {
                page.focusedOnce = true
                page.primaryButton().forceActiveFocus()
            } else if (resumeButton.activeFocus && !resumeButton.visible) {
                page.primaryButton().forceActiveFocus()
            }
        }
    }

    Connections {
        target: app
        function onItemChanged(changedId) {
            if (changedId === page.itemId)
                details.reload()
        }
    }

    Image {
        anchors.fill: parent
        source: details.backdrop
        sourceSize.width: Math.round(width * Screen.devicePixelRatio)
        fillMode: Image.PreserveAspectCrop
        asynchronous: true
        opacity: status === Image.Ready ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 300 } }
    }

    HeroTrailer {
        id: hero
        anchors.fill: parent
        itemId: page.itemId
        itemType: details.itemType
        active: details.loaded && page.StackView.status === StackView.Active && !app.playback.active
    }

    Rectangle {
        anchors.fill: parent
        opacity: page.chrome
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: "#f20f1218" }
            GradientStop { position: 0.5; color: "#c00f1218" }
            GradientStop { position: 1.0; color: "#200f1218" }
        }
    }

    Rectangle {
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        opacity: page.chrome
        height: parent.height * 0.55
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#000f1218" }
            GradientStop { position: 1.0; color: "#f80f1218" }
        }
    }

    Spinner {
        anchors.centerIn: parent
        visible: details.loading && !details.loaded
    }

    Text {
        anchors.centerIn: parent
        visible: details.error.length > 0 && !details.loaded
        text: details.error
        color: Theme.danger
        font.pixelSize: Theme.fontBody
    }

    Column {
        id: info
        opacity: page.chrome
        visible: details.loaded
        x: Theme.margin
        y: Math.max(64, (parent.height - height) / 2)
        width: Math.min(parent.width * 0.55, 1000)
        spacing: 18

        Image {
            id: logo
            source: details.logo
            visible: status === Image.Ready
            width: Math.min(520, parent.width)
            height: 150
            sourceSize.width: Math.round(520 * Screen.devicePixelRatio)
            fillMode: Image.PreserveAspectFit
            horizontalAlignment: Image.AlignLeft
            verticalAlignment: Image.AlignBottom
            asynchronous: true
        }

        Text {
            visible: !logo.visible
            width: parent.width
            text: details.itemType === "Episode" ? details.seriesName : details.name
            color: Theme.text
            font.pixelSize: Theme.fontHuge
            font.bold: true
            wrapMode: Text.WordWrap
            maximumLineCount: 2
            elide: Text.ElideRight
        }

        Text {
            visible: details.itemType === "Episode"
            width: parent.width
            text: details.episodeLabel + "  " + details.name
            color: Theme.text
            font.pixelSize: Theme.fontRow
            font.bold: true
            elide: Text.ElideRight
        }

        Text {
            width: parent.width
            text: {
                var parts = [details.year, details.runtime]
                if (details.communityRating)
                    parts.push("★ " + details.communityRating)
                parts.push(details.genres)
                if (details.played)
                    parts.push("Watched")
                return parts.filter(function (p) { return p && p.length > 0 }).join("   ·   ")
            }
            color: Theme.textDim
            font.pixelSize: Theme.fontBody
            elide: Text.ElideRight
        }

        Item {
            width: parent.width
            height: 8
            visible: details.progress > 0 && !details.played
            Rectangle {
                width: 420
                height: 8
                radius: 4
                color: "#40ffffff"
                Rectangle {
                    width: parent.width * details.progress
                    height: parent.height
                    radius: 4
                    color: Theme.accent
                }
            }
        }

        Row {
            id: buttonRow
            spacing: 18
            height: 76
            topPadding: 6

            TvButton {
                id: resumeButton
                visible: details.playable && details.resumeSeconds > 0
                primary: true
                icon: "▶"
                text: "Resume " + details.resumeText
                KeyNavigation.right: playButton
                busy: details.sourcesLoading
                dimmed: details.sourcesLoading
                onClicked: details.play(details.resumeSeconds)
            }

            TvButton {
                id: playButton
                visible: details.playable
                primary: !resumeButton.visible
                icon: resumeButton.visible ? "↺" : "▶"
                text: resumeButton.visible ? "From beginning" : "Play"
                KeyNavigation.left: resumeButton.visible ? resumeButton : null
                KeyNavigation.right: versionButton.visible ? versionButton : watchedButton
                busy: details.sourcesLoading && !resumeButton.visible
                dimmed: details.sourcesLoading
                onClicked: details.play(0)
            }

            TvButton {
                id: versionButton
                visible: details.playable && (details.sourceCount > 1 || details.sourcesLoading)
                icon: "☰"
                text: details.sourcesLoading ? "Versions…" : "Version (" + details.sourceCount + ")"
                KeyNavigation.left: playButton
                KeyNavigation.right: watchedButton
                onClicked: page.openSources(details)
            }

            TvButton {
                id: watchedButton
                icon: details.played ? "✓" : "○"
                text: details.played ? "Watched" : "Mark watched"
                KeyNavigation.left: versionButton.visible ? versionButton : (playButton.visible ? playButton : null)
                KeyNavigation.right: favoriteButton
                onClicked: details.togglePlayed()
            }

            TvButton {
                id: favoriteButton
                icon: details.favorite ? "♥" : "♡"
                text: details.favorite ? "Favorite" : "Add favorite"
                KeyNavigation.left: watchedButton
                KeyNavigation.right: trailerButton.visible ? trailerButton : (seriesButton.visible ? seriesButton : null)
                onClicked: details.toggleFavorite()
            }

            TvButton {
                id: trailerButton
                visible: hero.supported
                dimmed: hero.status !== "ready"
                busy: hero.status === "loading"
                icon: "▶"
                text: hero.status === "none" ? "No trailer" : "Trailer"
                KeyNavigation.left: favoriteButton
                KeyNavigation.right: seriesButton.visible ? seriesButton : null
                onClicked: trailerControls.enter(trailerButton)
            }

            TvButton {
                id: seriesButton
                visible: details.itemType === "Episode" && details.seriesId.length > 0
                icon: "▤"
                text: "Series"
                KeyNavigation.left: trailerButton.visible ? trailerButton : favoriteButton
                onClicked: page.openItem({ itemId: details.seriesId, itemType: "Series", name: details.seriesName })
            }
        }

        Row {
            visible: details.playable && (details.sourcesLoading || details.selectedSourceLabel.length > 0)
            width: parent.width
            height: 28
            spacing: 12

            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width
                text: details.sourcesLoading
                      ? "Fetching versions from your sources…"
                      : (details.sourceCount > 1 ? details.sourceCount + " versions  ·  " : "") + details.selectedSourceLabel
                color: details.sourcesLoading ? Theme.accent : Theme.textDim
                font.pixelSize: Theme.fontSmall
                elide: Text.ElideRight
            }
        }


        Text {
            width: parent.width
            text: details.overview
            color: Theme.textDim
            font.pixelSize: Theme.fontBody
            lineHeight: 1.2
            wrapMode: Text.WordWrap
            maximumLineCount: 6
            elide: Text.ElideRight
        }
    }

    TrailerControls {
        id: trailerControls
        anchors.fill: parent
        hero: hero
    }
}
