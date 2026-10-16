import QtQuick
import QtMultimedia

Item {
    id: root

    property string videoUrl
    property string audioUrl
    property bool muxed: false
    property bool muted: true
    readonly property bool separateAudio: !muxed && !muted && audioUrl !== ""
    property bool started: false
    readonly property bool showing: video.playbackState !== MediaPlayer.StoppedState && started
    readonly property bool paused: video.playbackState === MediaPlayer.PausedState

    signal ended()

    readonly property string inhibitKey: root.toString()
    readonly property bool playing: video.playing
    onPlayingChanged: app.inhibitor.hold(inhibitKey, playing)
    Component.onDestruction: app.inhibitor.hold(inhibitKey, false)

    function ready(player) {
        return player.mediaStatus === MediaPlayer.LoadedMedia || player.mediaStatus === MediaPlayer.BufferedMedia
    }

    function syncAudio() {
        if (separateAudio && video.playing && ready(audio) && !audio.playing) {
            audio.position = video.position
            audio.play()
        }
    }

    function maybeStart() {
        if (video.playbackState === MediaPlayer.StoppedState && ready(video) && (!separateAudio || ready(audio)))
            video.play()
        syncAudio()
    }

    function restart() {
        audio.stop()
        video.position = 0
        video.play()
        syncAudio()
    }

    function seek(ms) {
        video.position = Math.max(0, Math.min(video.duration - 500, video.position + ms))
        if (audio.playing)
            audio.position = video.position
    }

    function togglePause() {
        if (video.playing) {
            video.pause()
            audio.pause()
        } else {
            video.play()
            if (separateAudio && ready(audio)) {
                audio.position = video.position
                audio.play()
            }
        }
    }

    onVideoUrlChanged: {
        started = false
        video.stop()
        audio.stop()
    }

    MediaPlayer {
        id: video
        source: root.videoUrl
        videoOutput: output
        audioOutput: AudioOutput { muted: root.muted || !root.muxed; volume: 0.7 }
        onMediaStatusChanged: {
            if (mediaStatus === MediaPlayer.EndOfMedia) {
                audio.stop()
                root.ended()
            } else {
                root.maybeStart()
            }
        }
        onPlayingChanged: root.syncAudio()
        onPositionChanged: if (position > 250) root.started = true
        onErrorOccurred: app.trailers.failed()
    }

    MediaPlayer {
        id: audio
        source: root.separateAudio ? root.audioUrl : ""
        audioOutput: AudioOutput { volume: 0.7 }
        onMediaStatusChanged: root.maybeStart()
    }

    VideoOutput {
        id: output
        anchors.fill: parent
        fillMode: VideoOutput.PreserveAspectCrop
    }
}
