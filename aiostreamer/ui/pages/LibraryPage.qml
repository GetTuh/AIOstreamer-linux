import QtQuick
import QtQuick.Controls
import "../theme"
import "../components"
import AIOstreamer

FocusScope {
    id: page

    property string catalogType
    property string catalogId
    property var genres: []
    property bool genreRequired: false
    property string title
    readonly property alias libraryModel: library

    signal openItem(var entry)

    readonly property int cellW: Theme.posterWidth + 36
    readonly property int cellH: Theme.posterHeight + Theme.labelHeight + 36

    LibraryModel {
        id: library
        catalogType: page.catalogType
        catalogId: page.catalogId
        genres: page.genres
        genreRequired: page.genreRequired
    }

    Component.onCompleted: {
        library.reload()
        grid.forceActiveFocus()
    }
    StackView.onActivated: if (!sortButton.activeFocus) grid.forceActiveFocus()

    Text {
        id: heading
        x: Theme.margin
        y: 36
        text: page.title
        color: Theme.text
        font.pixelSize: Theme.fontTitle
        font.bold: true
    }

    Text {
        anchors { left: heading.right; leftMargin: 24; baseline: heading.baseline }
        text: page.libraryModel && page.libraryModel.count > 0 ? (grid.currentIndex + 1) + " / " + page.libraryModel.count : ""
        color: Theme.textDim
        font.pixelSize: Theme.fontBody
    }

    TvButton {
        id: sortButton
        anchors { right: parent.right; rightMargin: Theme.margin; verticalCenter: heading.verticalCenter }
        visible: library.genres.length > 0
        icon: "‹›"
        text: "Genre: " + library.genreName
        onClicked: library.stepGenre(1)
        Keys.onRightPressed: library.stepGenre(1)
        Keys.onLeftPressed: library.stepGenre(-1)
        Keys.onDownPressed: grid.forceActiveFocus()
    }

    GridView {
        id: grid
        readonly property int columns: Math.max(1, Math.floor(width / cellWidth))
        anchors { top: heading.bottom; topMargin: 24; bottom: parent.bottom }
        x: Theme.margin - 18
        width: Math.floor((parent.width - 2 * Theme.margin + 36) / page.cellW) * page.cellW
        cellWidth: page.cellW
        cellHeight: page.cellH
        model: page.libraryModel
        focus: true
        clip: true
        cacheBuffer: page.cellH * 2
        keyNavigationEnabled: true
        highlightRangeMode: GridView.ApplyRange
        preferredHighlightBegin: 12
        preferredHighlightEnd: height - page.cellH
        highlightMoveDuration: 200
        boundsBehavior: Flickable.StopAtBounds
        topMargin: 16

        delegate: Item {
            required property int index
            required property var model
            width: grid.cellWidth
            height: grid.cellHeight

            FocusCard {
                anchors.horizontalCenter: parent.horizontalCenter
                y: 12
                title: model.name
                subtitle: model.subtitle
                source: model.image
                progress: model.progress
                played: model.played
                unplayed: model.unplayedCount
                current: parent.GridView.isCurrentItem && grid.activeFocus
                onClicked: {
                    grid.currentIndex = index
                    page.openItem(page.libraryModel.get(index))
                }
            }
        }

        onCountChanged: if (count > 0 && currentIndex < 0) currentIndex = 0

        Keys.onUpPressed: (event) => {
            if (currentIndex < columns && sortButton.visible)
                sortButton.forceActiveFocus()
            else if (currentIndex < columns)
                return
            else
                moveCurrentIndexUp()
        }
        Keys.onReturnPressed: page.openItem(page.libraryModel.get(currentIndex))
        Keys.onEnterPressed: page.openItem(page.libraryModel.get(currentIndex))
    }

    Spinner {
        anchors.centerIn: parent
        visible: page.libraryModel !== null && page.libraryModel.loading && page.libraryModel.count === 0
    }

    Text {
        anchors.centerIn: parent
        visible: page.libraryModel !== null && page.libraryModel.loaded && page.libraryModel.count === 0
        text: "Nothing here yet"
        color: Theme.textDim
        font.pixelSize: Theme.fontRow
    }
}
