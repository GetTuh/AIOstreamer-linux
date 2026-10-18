import QtQuick
import "../theme"

FocusScope {
    id: root

    property var rowModel
    property string title
    property bool landscape: false
    property alias currentIndex: list.currentIndex
    property alias count: list.count
    readonly property Item currentItem: list.currentItem

    signal activated(int index)

    height: header.height + 16 + list.height

    Text {
        id: header
        x: Theme.margin
        text: root.title
        color: root.activeFocus ? Theme.text : Theme.textDim
        font.pixelSize: Theme.fontRow
        font.bold: true
    }

    ListView {
        id: list
        anchors { top: header.bottom; topMargin: 16; left: parent.left; right: parent.right }
        height: (root.landscape ? Theme.thumbHeight : Theme.posterHeight) + Theme.labelHeight + 20
        orientation: ListView.Horizontal
        model: root.rowModel
        focus: true
        spacing: 28
        leftMargin: Theme.margin
        rightMargin: Theme.margin
        cacheBuffer: 1200
        boundsBehavior: Flickable.StopAtBounds
        highlightRangeMode: ListView.ApplyRange
        preferredHighlightBegin: Theme.margin
        preferredHighlightEnd: width - Theme.margin - (root.landscape ? Theme.thumbWidth : Theme.posterWidth) * 2
        highlightMoveDuration: 220
        highlightMoveVelocity: -1
        keyNavigationEnabled: true
        topMargin: 12

        delegate: FocusCard {
            required property int index
            required property var model

            readonly property string overview: model.overview
            readonly property string itemType: model.itemType
            title: model.name
            subtitle: model.subtitle
            source: model.image
            progress: model.progress
            played: model.played
            unplayed: model.unplayedCount
            landscape: root.landscape
            current: ListView.isCurrentItem && list.activeFocus
            onClicked: {
                list.currentIndex = index
                list.forceActiveFocus()
                root.activated(index)
            }
        }

        onCountChanged: if (count > 0 && currentIndex < 0) currentIndex = 0

        Keys.onReturnPressed: root.activated(currentIndex)
        Keys.onEnterPressed: root.activated(currentIndex)
    }
}
