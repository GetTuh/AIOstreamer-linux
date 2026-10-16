import QtQuick
import QtQuick.Controls
import "../theme"
import "../components"

FocusScope {
    id: page

    readonly property var sp: app.syncplay

    function focusFirst() {
        if (page.sp.active)
            leaveButton.forceActiveFocus()
        else if (groupRepeater.count > 0)
            groupRepeater.itemAt(0).forceActiveFocus()
        else
            createButton.forceActiveFocus()
    }

    Component.onCompleted: {
        page.sp.refresh()
        focusFirst()
    }
    StackView.onActivated: focusFirst()

    Connections {
        target: page.sp
        function onChanged() { page.sp.refresh(); page.focusFirst() }
        function onGroupsChanged() { if (!createButton.activeFocus && !refreshButton.activeFocus) page.focusFirst() }
    }

    Column {
        x: Theme.margin
        y: 36
        width: Math.min(parent.width - 2 * Theme.margin, 1100)
        spacing: 22

        Text {
            text: "SyncPlay"
            color: Theme.text
            font.pixelSize: Theme.fontTitle
            font.bold: true
        }

        Text {
            width: parent.width
            text: page.sp.active
                  ? "Watching together in " + page.sp.groupName + (page.sp.groupState ? "  ·  " + page.sp.groupState : "")
                  : "Watch in sync with others on this server. Join a group or create one, then play something."
            color: Theme.textDim
            font.pixelSize: Theme.fontBody
            wrapMode: Text.WordWrap
        }

        Text {
            visible: page.sp.active
            text: "In the group: " + page.sp.participants.join(", ")
            color: Theme.text
            font.pixelSize: Theme.fontBody
        }

        TvButton {
            id: leaveButton
            visible: page.sp.active
            icon: "⏏"
            text: "Leave group"
            onClicked: page.sp.leave()
        }

        Text {
            visible: !page.sp.active
            topPadding: 12
            text: groupRepeater.count > 0 ? "Groups" : "No groups yet"
            color: Theme.textDim
            font.pixelSize: Theme.fontRow
            font.bold: true
        }

        Repeater {
            id: groupRepeater
            model: page.sp.active ? [] : page.sp.groups
            delegate: TvButton {
                required property var modelData
                required property int index
                width: parent.width
                icon: "▶"
                text: modelData.name + "  ·  " + modelData.participants + (modelData.participants === 1 ? " person" : " people")
                KeyNavigation.up: index > 0 ? groupRepeater.itemAt(index - 1) : null
                KeyNavigation.down: index < groupRepeater.count - 1 ? groupRepeater.itemAt(index + 1) : createButton
                onClicked: page.sp.join(modelData.id)
            }
        }

        Row {
            visible: !page.sp.active
            spacing: 18
            TvButton {
                id: createButton
                icon: "+"
                text: "Create group"
                primary: groupRepeater.count === 0
                KeyNavigation.up: groupRepeater.count > 0 ? groupRepeater.itemAt(groupRepeater.count - 1) : null
                KeyNavigation.right: refreshButton
                onClicked: page.sp.create("")
            }
            TvButton {
                id: refreshButton
                icon: "↻"
                text: "Refresh"
                KeyNavigation.left: createButton
                KeyNavigation.up: createButton.KeyNavigation.up
                onClicked: page.sp.refresh()
            }
        }
    }
}
