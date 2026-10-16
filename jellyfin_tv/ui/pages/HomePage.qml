import QtQuick
import QtQuick.Controls
import "../theme"
import "../components"

FocusScope {
    id: page

    property var rowIndexes: ({})
    signal openItem(var entry)
    signal openSearch()
    signal openSettings()
    signal openSyncPlay()
    signal requestQuit()

    StackView.onActivated: {
        if (!rows.activeFocus && !header.activeFocus)
            rows.forceActiveFocus()
        else
            page.forceActiveFocus()
    }

    Component.onCompleted: rows.forceActiveFocus()

    function visibleRow(from, step) {
        for (var i = from; i >= 0 && i < rows.count; i += step) {
            var item = rows.itemAtIndex(i)
            if (!item || item.count > 0)
                return i
        }
        return -1
    }

    FocusScope {
        id: header
        x: Theme.margin
        y: 36
        width: parent.width - 2 * Theme.margin
        height: 72

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: "Home"
            color: Theme.text
            font.pixelSize: Theme.fontTitle
            font.bold: true
        }

        Row {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 20

            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: app.userName
                color: Theme.textDim
                font.pixelSize: Theme.fontBody
            }

            TvButton {
                id: searchButton
                focus: true
                icon: "⌕"
                text: "Search"
                KeyNavigation.right: syncButton
                onClicked: page.openSearch()
                Keys.onDownPressed: rows.forceActiveFocus()
            }

            TvButton {
                id: syncButton
                icon: "⇄"
                text: app.syncplay.active ? app.syncplay.groupName : "SyncPlay"
                primary: app.syncplay.active
                KeyNavigation.left: searchButton
                KeyNavigation.right: settingsButton
                onClicked: page.openSyncPlay()
                Keys.onDownPressed: rows.forceActiveFocus()
            }

            TvButton {
                id: settingsButton
                icon: "⚙"
                text: "Settings"
                KeyNavigation.left: syncButton
                onClicked: page.openSettings()
                Keys.onDownPressed: rows.forceActiveFocus()
            }
        }
    }

    ListView {
        id: rows
        anchors { top: header.bottom; topMargin: 24; left: parent.left; right: parent.right; bottom: parent.bottom }
        model: app.home
        focus: true
        clip: true
        spacing: 36
        cacheBuffer: 4000
        keyNavigationEnabled: false
        highlightRangeMode: ListView.ApplyRange
        preferredHighlightBegin: 0
        preferredHighlightEnd: height * 0.45
        highlightMoveDuration: 260
        highlightMoveVelocity: -1
        boundsBehavior: Flickable.StopAtBounds
        bottomMargin: 120

        delegate: MediaRow {
            id: row
            required property int index
            required property var model
            readonly property string rowKey: model.rowKey

            width: rows.width
            title: model.title
            rowModel: model.rowModel
            landscape: rowModel.imageKind === "thumb"
            visible: row.count > 0
            height: visible ? implicitHeight : 0
            implicitHeight: 48 + 16 + (landscape ? Theme.thumbHeight : Theme.posterHeight) + Theme.labelHeight + 20
            focus: ListView.isCurrentItem
            onActivated: (i) => page.openItem(row.rowModel.get(i))
            onCurrentIndexChanged: page.rowIndexes[row.rowKey] = currentIndex
            onCountChanged: {
                var saved = page.rowIndexes[row.rowKey]
                if (saved !== undefined && saved < count && currentIndex !== saved)
                    currentIndex = saved
                if (count > 0 && rows.currentItem && rows.currentItem.count === 0) {
                    var next = page.visibleRow(rows.currentIndex, 1)
                    if (next >= 0)
                        rows.currentIndex = next
                }
            }
        }

        Keys.onDownPressed: (event) => {
            var next = page.visibleRow(currentIndex + 1, 1)
            if (next >= 0)
                currentIndex = next
        }
        Keys.onUpPressed: (event) => {
            var prev = page.visibleRow(currentIndex - 1, -1)
            if (prev >= 0)
                currentIndex = prev
            else
                searchButton.forceActiveFocus()
        }
    }

    Text {
        anchors.centerIn: parent
        visible: rows.count === 0
        text: "Loading…"
        color: Theme.textDim
        font.pixelSize: Theme.fontRow
    }
}
