import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "../theme"
import "../components"
import JellyfinTV

FocusScope {
    id: page

    property string itemId
    property bool focusedOnce: false
    property bool episodeTargeted: false

    signal openItem(var entry)

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
    }

    SeriesModel {
        id: series
        seriesId: page.itemId
    }

    Component.onCompleted: page.forceActiveFocus()
    StackView.onActivated: {
        if (!episodesRow.activeFocus && !tabs.activeFocus)
            primaryButton().forceActiveFocus()
    }

    function primaryButton() {
        return playButton.visible ? playButton : watchedButton
    }

    Connections {
        target: details
        function onChanged() {
            if (details.loaded && !page.focusedOnce) {
                page.focusedOnce = true
                page.primaryButton().forceActiveFocus()
            }
        }
    }

    Connections {
        target: app
        function onItemChanged(changedId) {
            series.refresh()
            if (changedId === page.itemId)
                details.reload()
        }
    }

    Connections {
        target: series.episodes
        function onCountChanged() {
            if (series.episodes.count === 0)
                return
            var target = page.episodeTargeted ? -1 : series.episodes.indexOf(series.targetEpisodeId)
            if (target >= 0) {
                page.episodeTargeted = true
                episodesRow.currentIndex = target
            } else if (episodesRow.currentIndex < 0 || episodesRow.currentIndex >= series.episodes.count) {
                episodesRow.currentIndex = 0
            }
        }
    }

    Connections {
        target: series
        function onSeasonChanged() {
            if (tabs.currentIndex !== series.seasonIndex)
                tabs.currentIndex = series.seasonIndex
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
            GradientStop { position: 0.5; color: "#b00f1218" }
            GradientStop { position: 1.0; color: "#200f1218" }
        }
    }

    Rectangle {
        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
        opacity: page.chrome
        height: parent.height * 0.6
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#000f1218" }
            GradientStop { position: 0.35; color: "#e00f1218" }
            GradientStop { position: 1.0; color: "#ff0f1218" }
        }
    }

    Spinner {
        anchors.centerIn: parent
        visible: details.loading && !details.loaded
    }

    Column {
        id: info
        opacity: page.chrome
        visible: details.loaded
        x: Theme.margin
        y: 48
        width: Math.min(parent.width * 0.55, 1000)
        spacing: 14

        Image {
            id: logo
            source: details.logo
            visible: status === Image.Ready
            width: Math.min(460, parent.width)
            height: 120
            sourceSize.width: Math.round(460 * Screen.devicePixelRatio)
            fillMode: Image.PreserveAspectFit
            horizontalAlignment: Image.AlignLeft
            verticalAlignment: Image.AlignBottom
            asynchronous: true
        }

        Text {
            visible: !logo.visible
            width: parent.width
            text: details.name
            color: Theme.text
            font.pixelSize: Theme.fontHuge
            font.bold: true
            elide: Text.ElideRight
        }

        Text {
            width: parent.width
            text: {
                var parts = [details.year, details.officialRating]
                if (details.communityRating)
                    parts.push("★ " + details.communityRating)
                parts.push(details.genres)
                if (series.seasons.count > 0)
                    parts.push(series.seasons.count + (series.seasons.count === 1 ? " season" : " seasons"))
                return parts.filter(function (p) { return p && p.length > 0 }).join("   ·   ")
            }
            color: Theme.textDim
            font.pixelSize: Theme.fontBody
            elide: Text.ElideRight
        }

        Text {
            width: parent.width
            text: details.overview
            color: Theme.textDim
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
            maximumLineCount: 3
            elide: Text.ElideRight
        }

        Row {
            spacing: 18
            height: 76
            topPadding: 6

            TvButton {
                id: playButton
                visible: series.nextUpId.length > 0
                primary: true
                icon: "▶"
                text: (series.nextUpResumeSeconds > 0 ? "Resume " : "Play ") + series.nextUpLabel + (series.nextUpResumeText ? "  " + series.nextUpResumeText : "")
                KeyNavigation.right: watchedButton
                KeyNavigation.down: tabs
                onClicked: app.play(series.nextUpId, series.nextUpResumeSeconds)
            }

            TvButton {
                id: watchedButton
                icon: details.played ? "✓" : "○"
                text: details.played ? "Watched" : "Mark watched"
                KeyNavigation.left: playButton.visible ? playButton : null
                KeyNavigation.right: favoriteButton
                KeyNavigation.down: tabs
                onClicked: details.togglePlayed()
            }

            TvButton {
                id: favoriteButton
                icon: details.favorite ? "♥" : "♡"
                text: details.favorite ? "Favorite" : "Add favorite"
                KeyNavigation.left: watchedButton
                KeyNavigation.right: trailerButton.visible ? trailerButton : null
                KeyNavigation.down: tabs
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
                KeyNavigation.down: tabs
                onClicked: trailerControls.enter(trailerButton)
            }
        }
    }

    ListView {
        id: tabs
        opacity: page.chrome
        anchors { left: parent.left; right: parent.right; bottom: episodesRow.top; bottomMargin: 18 }
        height: 56
        orientation: ListView.Horizontal
        leftMargin: Theme.margin
        rightMargin: Theme.margin
        spacing: 14
        model: series.seasons
        keyNavigationEnabled: true
        highlightRangeMode: ListView.ApplyRange
        preferredHighlightBegin: Theme.margin
        preferredHighlightEnd: width - Theme.margin - 220
        highlightMoveDuration: 180
        boundsBehavior: Flickable.StopAtBounds
        onCurrentIndexChanged: if (currentIndex >= 0) series.seasonIndex = currentIndex

        delegate: Rectangle {
            id: tab
            required property int index
            required property var model
            readonly property bool selected: index === series.seasonIndex
            readonly property bool current: ListView.isCurrentItem && tabs.activeFocus

            height: 52
            width: tabText.implicitWidth + 48
            radius: height / 2
            color: current ? Theme.focus : (selected ? Theme.surfaceHigh : "transparent")
            border.width: selected && !current ? 2 : 0
            border.color: Theme.accent

            Text {
                id: tabText
                anchors.centerIn: parent
                text: tab.model.name + (tab.model.played ? "  ✓" : "")
                color: tab.current ? Theme.focusText : (tab.selected ? Theme.text : Theme.textDim)
                font.pixelSize: Theme.fontBody
                font.bold: tab.selected || tab.current
            }

            MouseArea {
                anchors.fill: parent
                onClicked: {
                    tabs.currentIndex = tab.index
                    tabs.forceActiveFocus()
                }
            }
        }

        Keys.onUpPressed: page.primaryButton().forceActiveFocus()
        Keys.onDownPressed: episodesRow.forceActiveFocus()
        Keys.onReturnPressed: episodesRow.forceActiveFocus()
        Keys.onEnterPressed: episodesRow.forceActiveFocus()
    }

    MediaRow {
        id: episodesRow
        opacity: page.chrome
        anchors { left: parent.left; right: parent.right; bottom: episodeOverview.top; bottomMargin: 4 }
        title: {
            var s = series.seasons.get(series.seasonIndex)
            return s && s.name ? s.name + "  ·  " + series.episodes.count + " episodes" : ""
        }
        rowModel: series.episodes
        landscape: true
        Keys.onUpPressed: tabs.forceActiveFocus()
        onActivated: (i) => page.openItem(series.episodes.get(i))
    }

    Text {
        id: episodeOverview
        opacity: page.chrome
        anchors { left: parent.left; leftMargin: Theme.margin; right: parent.right; rightMargin: Theme.margin; bottom: parent.bottom; bottomMargin: 28 }
        height: 64
        text: episodesRow.activeFocus && episodesRow.currentItem ? episodesRow.currentItem.overview : ""
        color: Theme.textDim
        font.pixelSize: Theme.fontSmall
        wrapMode: Text.WordWrap
        maximumLineCount: 2
        elide: Text.ElideRight
    }

    Spinner {
        anchors.centerIn: episodesRow
        visible: series.episodes.loading && series.episodes.count === 0
    }

    TrailerControls {
        id: trailerControls
        anchors.fill: parent
        hero: hero
    }
}
