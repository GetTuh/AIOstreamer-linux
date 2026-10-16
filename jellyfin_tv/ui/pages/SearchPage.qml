import QtQuick
import QtQuick.Controls
import "../theme"
import "../components"
import JellyfinTV

FocusScope {
    id: page

    signal openItem(var entry)

    readonly property bool loading: shows.loading || movies.loading
    readonly property bool hasResults: shows.count > 0 || movies.count > 0
    readonly property bool showsFirst: shows.count > 0 && (movies.count === 0 || shows.relevance > movies.relevance || (shows.relevance === movies.relevance && shows.count >= movies.count))
    readonly property Item topRow: showsFirst ? showsRow : moviesRow
    readonly property Item bottomRow: showsFirst ? moviesRow : showsRow
    readonly property Item focusedRow: showsRow.activeFocus ? showsRow : (moviesRow.activeFocus ? moviesRow : null)

    SearchModel {
        id: shows
        itemTypes: "Series"
        term: field.text
    }

    SearchModel {
        id: movies
        itemTypes: "Movie"
        term: field.text
    }

    Component.onCompleted: field.forceActiveFocus()
    StackView.onActivated: {
        if (!page.focusedRow && !keyboard.activeFocus)
            field.forceActiveFocus()
    }

    function firstRow() {
        return topRow.count > 0 ? topRow : (bottomRow.count > 0 ? bottomRow : null)
    }

    function rowBelow(row) {
        return row === topRow && bottomRow.count > 0 ? bottomRow : null
    }

    function rowAbove(row) {
        return row === bottomRow && topRow.count > 0 ? topRow : null
    }

    function focusRow(row) {
        if (!row)
            return
        row.forceActiveFocus()
        var y = row.y - 8
        flick.contentY = Math.max(0, Math.min(y, flick.contentHeight - flick.height))
    }

    OnScreenKeyboard {
        id: keyboard
        anchors { left: parent.left; leftMargin: Theme.margin; top: parent.top; topMargin: 48 }
        onTyped: (t) => field.insert(field.cursorPosition, t)
        onBackspace: {
            if (field.cursorPosition > 0)
                field.remove(field.cursorPosition - 1, field.cursorPosition)
        }
        onCleared: field.clear()
        onExitRight: field.forceActiveFocus()
    }

    TvTextField {
        id: field
        anchors { left: keyboard.right; leftMargin: 48; right: parent.right; rightMargin: Theme.margin; top: parent.top; topMargin: 48 }
        placeholderText: "Search movies and shows"
        inputMethodHints: Qt.ImhNoPredictiveText
        Keys.onDownPressed: page.focusRow(page.firstRow())
        Keys.onLeftPressed: (event) => {
            if (cursorPosition === 0)
                keyboard.forceActiveFocus()
            else
                event.accepted = false
        }
        onAccepted: page.focusRow(page.firstRow())
    }

    Text {
        id: focusInfo
        anchors { left: field.left; right: field.right; top: field.bottom; topMargin: 16 }
        height: 34
        text: {
            var row = page.focusedRow
            if (!row || !row.currentItem)
                return ""
            var c = row.currentItem
            return [c.title, c.itemType === "Series" ? "Series" : "Movie", c.subtitle].filter(function (p) { return p && p.length > 0 }).join("   ·   ")
        }
        color: Theme.text
        font.pixelSize: Theme.fontBody
        font.bold: true
        elide: Text.ElideRight
    }

    Flickable {
        id: flick
        anchors { left: field.left; leftMargin: -24; right: parent.right; top: focusInfo.bottom; topMargin: 8; bottom: parent.bottom }
        contentHeight: column.height + 40
        readonly property int gap: 24
        clip: true
        interactive: false
        Behavior on contentY { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }

        Item {
            id: column
            width: flick.width
            height: (showsRow.visible ? showsRow.height : 0) + (moviesRow.visible ? moviesRow.height : 0) + (showsRow.visible && moviesRow.visible ? flick.gap : 0)

            MediaRow {
                id: showsRow
                x: 24 - Theme.margin
                width: parent.width - x
                visible: count > 0
                y: page.showsFirst || !moviesRow.visible ? 0 : moviesRow.height + flick.gap
                title: "Shows  ·  " + shows.count
                rowModel: shows
                Keys.onUpPressed: page.rowAbove(showsRow) ? page.focusRow(page.rowAbove(showsRow)) : field.forceActiveFocus()
                Keys.onDownPressed: if (page.rowBelow(showsRow)) page.focusRow(page.rowBelow(showsRow))
                Keys.onLeftPressed: keyboard.forceActiveFocus()
                onActivated: (i) => page.openItem(shows.get(i))
            }

            MediaRow {
                id: moviesRow
                x: 24 - Theme.margin
                width: parent.width - x
                visible: count > 0
                y: !page.showsFirst || !showsRow.visible ? 0 : showsRow.height + flick.gap
                title: "Movies  ·  " + movies.count
                rowModel: movies
                Keys.onUpPressed: page.rowAbove(moviesRow) ? page.focusRow(page.rowAbove(moviesRow)) : field.forceActiveFocus()
                Keys.onDownPressed: if (page.rowBelow(moviesRow)) page.focusRow(page.rowBelow(moviesRow))
                Keys.onLeftPressed: keyboard.forceActiveFocus()
                onActivated: (i) => page.openItem(movies.get(i))
            }
        }
    }

    Spinner {
        anchors.centerIn: flick
        visible: page.loading && !page.hasResults
    }

    Text {
        anchors.centerIn: flick
        visible: !page.loading && !page.hasResults && shows.loaded && field.text.length > 1
        text: "No results for “" + field.text + "”"
        color: Theme.textDim
        font.pixelSize: Theme.fontRow
    }

    Text {
        anchors.centerIn: flick
        visible: field.text.length < 2
        text: "Type to search movies and shows"
        color: Theme.textDim
        font.pixelSize: Theme.fontRow
    }
}
