import QtQuick
import QtQuick.Controls
import "../theme"
import "../components"

FocusScope {
    id: page

    property var details

    property bool placed: false

    function placeSelection() {
        var sources = details.sources
        if (placed || sources.length === 0)
            return
        placed = true
        for (var i = 0; i < sources.length; i++) {
            if (sources[i].selected) {
                list.currentIndex = i
                break
            }
        }
    }

    Connections {
        target: page.details
        function onChanged() { page.placeSelection() }
    }

    Component.onCompleted: {
        placeSelection()
        list.forceActiveFocus()
    }
    StackView.onActivated: list.forceActiveFocus()

    Text {
        id: heading
        x: Theme.margin
        y: 36
        text: "Choose version"
        color: Theme.text
        font.pixelSize: Theme.fontTitle
        font.bold: true
    }

    Text {
        anchors { left: heading.right; leftMargin: 24; baseline: heading.baseline }
        text: !page.details ? "" : page.details.name + (page.details.sourcesLoading ? "" : "   ·   " + list.count + " versions in your AIOStreams order")
        color: Theme.textDim
        font.pixelSize: Theme.fontBody
    }

    ListView {
        id: list
        anchors { top: heading.bottom; topMargin: 28; bottom: parent.bottom; bottomMargin: 36 }
        x: Theme.margin
        width: parent.width - 2 * Theme.margin
        model: page.details ? page.details.sources : []
        spacing: 14
        clip: true
        focus: true
        keyNavigationEnabled: true
        highlightRangeMode: ListView.ApplyRange
        preferredHighlightBegin: 40
        preferredHighlightEnd: height - 160
        highlightMoveDuration: 180
        boundsBehavior: Flickable.StopAtBounds

        delegate: Rectangle {
            id: row
            required property int index
            required property var modelData
            readonly property bool current: ListView.isCurrentItem && list.activeFocus

            width: list.width
            height: 112
            radius: Theme.radius
            color: current ? Theme.focus : Theme.surface
            border.width: modelData.selected && !current ? 2 : 0
            border.color: Theme.accent

            Row {
                id: badges
                x: 24
                y: 18
                spacing: 12
                Repeater {
                    model: [row.modelData.resolution, row.modelData.hdr, row.modelData.codec, row.modelData.audio, row.modelData.size, row.modelData.service, row.modelData.languages].filter(function (p) { return p && p.length > 0 })
                    delegate: Rectangle {
                        required property string modelData
                        height: 36
                        width: badgeText.implicitWidth + 24
                        radius: 6
                        color: row.current ? "#1f000000" : Theme.surfaceHigh
                        Text {
                            id: badgeText
                            anchors.centerIn: parent
                            text: parent.modelData
                            color: row.current ? Theme.focusText : Theme.text
                            font.pixelSize: Theme.fontSmall
                            font.bold: true
                        }
                    }
                }
            }

            Text {
                anchors { left: parent.left; leftMargin: 24; right: check.left; rightMargin: 24; top: badges.bottom; topMargin: 12 }
                text: row.modelData.title || row.modelData.name
                color: row.current ? Theme.focusText : Theme.textDim
                font.pixelSize: Theme.fontSmall
                elide: Text.ElideRight
            }

            Text {
                id: check
                anchors { right: parent.right; rightMargin: 28; verticalCenter: parent.verticalCenter }
                text: row.modelData.selected ? "✓ Selected" : (row.index === 0 ? "Top" : "")
                color: row.current ? Theme.focusText : Theme.accent
                font.pixelSize: Theme.fontBody
                font.bold: true
            }

            MouseArea {
                anchors.fill: parent
                onClicked: {
                    list.currentIndex = row.index
                    page.choose(row.index)
                }
            }
        }

        Keys.onReturnPressed: page.choose(currentIndex)
        Keys.onEnterPressed: page.choose(currentIndex)
    }

    Column {
        anchors.centerIn: parent
        visible: page.details && page.details.sourcesLoading
        spacing: 28
        Spinner { anchors.horizontalCenter: parent.horizontalCenter }
        Text {
            text: "Fetching versions from your sources…"
            color: Theme.textDim
            font.pixelSize: Theme.fontRow
        }
    }

    Text {
        anchors.centerIn: parent
        visible: page.details && !page.details.sourcesLoading && list.count === 0
        text: "No versions found"
        color: Theme.textDim
        font.pixelSize: Theme.fontRow
    }

    function choose(index) {
        var sources = details.sources
        if (index < 0 || index >= sources.length)
            return
        details.selectSource(sources[index].id)
        StackView.view.pop()
    }
}
