import QtQuick

Item {
    id: root

    property string itemId
    property string itemType
    property bool active: false
    property bool expanded: false
    property bool cached: false

    readonly property bool supported: itemType === "Movie" || itemType === "Series"
    readonly property bool allowed: Qt.application.state === Qt.ApplicationActive || Qt.platform.pluginName === "offscreen"
    readonly property bool wanted: active && allowed && itemId !== "" && supported
    readonly property string status: itemId !== "" && app.trailers.currentId === itemId ? app.trailers.status : ""
    readonly property bool available: status === "ready" && player.status === Loader.Ready
    readonly property bool showing: available && player.item.showing
    readonly property bool paused: available && player.item.paused

    signal ended()

    function watch() { if (supported) app.trailers.watch(itemId, itemType) }
    function restart() { if (available) player.item.restart() }
    function seek(ms) { if (available) player.item.seek(ms) }
    function togglePause() { if (available) player.item.togglePause() }

    function source(url) {
        return url !== "" && cached ? app.trailers.cached(url) : url
    }

    opacity: showing ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 900; easing.type: Easing.InOutQuad } }

    onWantedChanged: wanted ? app.trailers.request(itemId, itemType) : app.trailers.release(itemId)
    onExpandedChanged: {
        if (!expanded)
            return
        cached = true
        restart()
    }
    Component.onDestruction: app.trailers.release(itemId)

    Loader {
        id: player
        anchors.fill: parent
        source: "TrailerPlayer.qml"
    }

    Connections {
        target: player.item
        function onEnded() { root.ended() }
    }

    Binding { target: player.item; property: "videoUrl"; value: root.available ? root.source(app.trailers.videoUrl) : ""; when: player.status === Loader.Ready }
    Binding { target: player.item; property: "audioUrl"; value: root.available ? root.source(app.trailers.audioUrl) : ""; when: player.status === Loader.Ready }
    Binding { target: player.item; property: "muxed"; value: app.trailers.muxed; when: player.status === Loader.Ready }
    Binding { target: player.item; property: "muted"; value: !root.expanded && app.trailers.muted; when: player.status === Loader.Ready }
}
