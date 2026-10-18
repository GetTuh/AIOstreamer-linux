import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Basic as Basic
import "../theme"
import "../components"

FocusScope {
    id: page

    signal addAccount()

    readonly property var audioLanguages: [languages[0],
        { value: "original", text: "Original" },
        { value: "original,eng,en", text: "Original, else English" }].concat(languages.slice(1))
    readonly property var languages: [
        { value: "", text: "Auto" },
        { value: "eng,en", text: "English" },
        { value: "ger,deu,de", text: "German" },
        { value: "fre,fra,fr", text: "French" },
        { value: "spa,es", text: "Spanish" },
        { value: "ita,it", text: "Italian" },
        { value: "por,pt", text: "Portuguese" },
        { value: "dut,nld,nl", text: "Dutch" },
        { value: "pol,pl", text: "Polish" },
        { value: "swe,sv", text: "Swedish" },
        { value: "nor,nob,no", text: "Norwegian" },
        { value: "dan,da", text: "Danish" },
        { value: "fin,fi", text: "Finnish" },
        { value: "rus,ru", text: "Russian" },
        { value: "ukr,uk", text: "Ukrainian" },
        { value: "tur,tr", text: "Turkish" },
        { value: "ara,ar", text: "Arabic" },
        { value: "hin,hi", text: "Hindi" },
        { value: "jpn,ja", text: "Japanese" },
        { value: "kor,ko", text: "Korean" },
        { value: "chi,zho,zh", text: "Chinese" }
    ]
    readonly property var onOff: [{ value: true, text: "On" }, { value: false, text: "Off" }]

    Component.onCompleted: first.forceActiveFocus()
    StackView.onActivated: if (!flick.activeFocus) first.forceActiveFocus()

    function ensureVisible(item) {
        var y = item.mapToItem(column, 0, 0).y
        if (y < flick.contentY + 20)
            flick.contentY = Math.max(0, y - 20)
        else if (y + item.height > flick.contentY + flick.height - 20)
            flick.contentY = Math.min(column.height - flick.height + 40, y + item.height - flick.height + 20)
    }

    Text {
        id: heading
        x: Theme.margin
        y: 36
        text: "Settings"
        color: Theme.text
        font.pixelSize: Theme.fontTitle
        font.bold: true
    }

    Flickable {
        id: flick
        anchors { top: heading.bottom; topMargin: 28; bottom: parent.bottom; left: parent.left; right: parent.right }
        contentHeight: column.height + 60
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        Behavior on contentY { NumberAnimation { duration: 160 } }

        Column {
            id: column
            x: Theme.margin
            width: Math.min(1100, page.width - 2 * Theme.margin)
            spacing: 14

            Text {
                text: "Playback"
                color: Theme.textDim
                font.pixelSize: Theme.fontRow
                font.bold: true
            }

            SettingRow {
                id: first
                label: "Audio language"
                hint: "Picks this audio track when a version has several. Original follows the title's country"
                options: page.audioLanguages
                value: app.settings.audioLanguage
                onPicked: (v) => app.settings.audioLanguage = v
                KeyNavigation.down: subLang
                onActiveFocusChanged: if (activeFocus) page.ensureVisible(this)
            }

            SettingRow {
                id: subLang
                label: "Subtitle language"
                options: page.languages
                value: app.settings.subtitleLanguage
                onPicked: (v) => app.settings.subtitleLanguage = v
                KeyNavigation.down: subMode
                onActiveFocusChanged: if (activeFocus) page.ensureVisible(this)
            }

            SettingRow {
                id: subMode
                label: "Subtitles"
                hint: "Auto shows subtitles when the audio is in another language"
                options: [{ value: "auto", text: "Auto" }, { value: "always", text: "Always" }, { value: "off", text: "Off" }]
                value: app.settings.subtitleMode
                onPicked: (v) => app.settings.subtitleMode = v
                KeyNavigation.down: autoplay
                onActiveFocusChanged: if (activeFocus) page.ensureVisible(this)
            }

            SettingRow {
                id: autoplay
                label: "Autoplay next episode"
                options: page.onOff
                value: app.settings.autoplayNext
                onPicked: (v) => app.settings.autoplayNext = v
                KeyNavigation.down: audioOutput
                onActiveFocusChanged: if (activeFocus) page.ensureVisible(this)
            }

            SettingRow {
                id: audioOutput
                label: "Audio output"
                hint: "Passthrough sends Dolby/DTS/TrueHD untouched to a receiver or soundbar"
                options: [{ value: "auto", text: "Auto" }, { value: "stereo", text: "Stereo" }, { value: "passthrough", text: "Passthrough" }]
                value: app.settings.audioOutput
                onPicked: (v) => app.settings.audioOutput = v
                KeyNavigation.down: skipSegments
                onActiveFocusChanged: if (activeFocus) page.ensureVisible(this)
            }

            SettingRow {
                id: skipSegments
                label: "Skip intros and recaps"
                hint: "Uses chapters named Intro/Opening/Recap"
                options: [{ value: "ask", text: "Show button" }, { value: "auto", text: "Automatically" }, { value: "off", text: "Off" }]
                value: app.settings.skipSegments
                onPicked: (v) => app.settings.skipSegments = v
                KeyNavigation.down: countdown
                onActiveFocusChanged: if (activeFocus) page.ensureVisible(this)
            }

            SettingRow {
                id: countdown
                label: "Up Next countdown"
                options: [5, 10, 15, 20, 30].map(function (s) { return { value: s, text: s + " s" } })
                value: app.settings.upNextSeconds
                onPicked: (v) => app.settings.upNextSeconds = v
                KeyNavigation.down: maxRes
                onActiveFocusChanged: if (activeFocus) page.ensureVisible(this)
            }

            Text {
                topPadding: 20
                text: "Versions"
                color: Theme.textDim
                font.pixelSize: Theme.fontRow
                font.bold: true
            }

            SettingRow {
                id: maxRes
                label: "Maximum resolution"
                hint: "Your AIOStreams sort order is kept; versions above these limits are skipped by default"
                options: [{ value: 0, text: "Unlimited" }, { value: 2160, text: "4K" }, { value: 1080, text: "1080p" }, { value: 720, text: "720p" }]
                value: app.settings.maxResolution
                onPicked: (v) => app.settings.maxResolution = v
                KeyNavigation.down: maxBitrate
                onActiveFocusChanged: if (activeFocus) page.ensureVisible(this)
            }

            SettingRow {
                id: maxBitrate
                label: "Maximum bitrate"
                hint: "Estimated from size and runtime"
                options: [{ value: 0, text: "Unlimited" }, { value: 80, text: "80 Mbps" }, { value: 40, text: "40 Mbps" }, { value: 20, text: "20 Mbps" }, { value: 10, text: "10 Mbps" }]
                value: app.settings.maxBitrate
                onPicked: (v) => app.settings.maxBitrate = v
                KeyNavigation.down: playerUi
                onActiveFocusChanged: if (activeFocus) page.ensureVisible(this)
            }

            Text {
                topPadding: 20
                text: "mpv"
                color: Theme.textDim
                font.pixelSize: Theme.fontRow
                font.bold: true
            }

            SettingRow {
                id: playerUi
                label: "Player controls"
                hint: "Overlay is built for remotes; Native uses mpv's own controls and keys"
                options: [{ value: "overlay", text: "Overlay" }, { value: "native", text: "Native mpv" }]
                value: app.settings.playerUi
                onPicked: (v) => app.settings.playerUi = v
                KeyNavigation.down: mpvExtra
                onActiveFocusChanged: if (activeFocus) page.ensureVisible(this)
            }

            Basic.TextArea {
                id: mpvExtra
                width: parent.width
                height: 180
                text: app.settings.mpvExtra
                placeholderText: "Extra mpv options, one key=value per line"
                color: Theme.text
                placeholderTextColor: Theme.textDim
                font.pixelSize: Theme.fontBody
                font.family: "monospace"
                padding: 20
                wrapMode: TextEdit.NoWrap
                background: Rectangle {
                    radius: Theme.radius
                    color: Theme.surface
                    border.width: mpvExtra.activeFocus ? 4 : 1
                    border.color: mpvExtra.activeFocus ? Theme.focus : Theme.surfaceHigh
                }
                onActiveFocusChanged: {
                    if (activeFocus)
                        page.ensureVisible(this)
                    else
                        app.settings.mpvExtra = text
                }
                Keys.onUpPressed: (event) => {
                    if (cursorRectangle.y < 10)
                        playerUi.forceActiveFocus()
                    else
                        event.accepted = false
                }
                Keys.onDownPressed: (event) => {
                    if (cursorRectangle.y + cursorRectangle.height > contentHeight - 10)
                        trailerPreviews.forceActiveFocus()
                    else
                        event.accepted = false
                }
                Keys.onEscapePressed: (event) => {
                    app.settings.mpvExtra = text
                    event.accepted = false
                }
            }

            Text {
                width: parent.width
                text: "Defaults: vo=gpu-next, gpu-api=vulkan, hwdec=auto-safe, target-colorspace-hint=yes, fullscreen=yes. "
                      + "A file at ~/.config/aiostreamer/mpv.conf is also loaded after the defaults."
                color: Theme.textDim
                font.pixelSize: Theme.fontSmall
                wrapMode: Text.WordWrap
            }

            SettingRow {
                id: trailerPreviews
                label: "Trailer previews"
                hint: "Plays the trailer in the background of a movie or show page"
                options: [{ value: "muted", text: "Muted" }, { value: "sound", text: "With sound" }, { value: "off", text: "Off" }]
                value: app.settings.trailerPreviews
                onPicked: (v) => app.settings.trailerPreviews = v
                KeyNavigation.up: mpvExtra
                KeyNavigation.down: gamepadRow
                onActiveFocusChanged: if (activeFocus) page.ensureVisible(this)
            }

            SettingRow {
                id: gamepadRow
                label: "Gamepad"
                hint: "A select, B back, Y trailer, X play/pause, Start menu, bumpers page up/down"
                options: page.onOff
                value: app.settings.gamepad
                onPicked: (v) => app.settings.gamepad = v
                KeyNavigation.up: trailerPreviews
                KeyNavigation.down: accountList.count > 0 ? accountList.itemAt(0) : addAccountButton
                onActiveFocusChanged: if (activeFocus) page.ensureVisible(this)
            }

            Text {
                topPadding: 20
                text: "Accounts"
                color: Theme.textDim
                font.pixelSize: Theme.fontRow
                font.bold: true
            }

            Repeater {
                id: accountList
                model: app.accounts
                delegate: TvButton {
                    required property var modelData
                    required property int index
                    width: Math.min(column.width, 900)
                    icon: modelData.active ? "✓" : "●"
                    primary: modelData.active
                    text: modelData.username + "  ·  " + modelData.server.replace(/^https?:\/\//, "")
                    KeyNavigation.up: index > 0 ? accountList.itemAt(index - 1) : gamepadRow
                    KeyNavigation.down: index < accountList.count - 1 ? accountList.itemAt(index + 1) : addAccountButton
                    onClicked: if (!modelData.active) app.switchAccount(modelData.key)
                    onActiveFocusChanged: if (activeFocus) page.ensureVisible(this)
                }
            }

            Row {
                spacing: 18
                TvButton {
                    id: addAccountButton
                    icon: "+"
                    text: "Add account"
                    KeyNavigation.up: accountList.count > 0 ? accountList.itemAt(accountList.count - 1) : gamepadRow
                    KeyNavigation.right: clearCache
                    onClicked: page.addAccount()
                    onActiveFocusChanged: if (activeFocus) page.ensureVisible(this)
                }
                TvButton {
                    id: clearCache
                    icon: "↻"
                    text: "Clear cache"
                    KeyNavigation.up: addAccountButton.KeyNavigation.up
                    KeyNavigation.left: addAccountButton
                    KeyNavigation.right: signOut
                    onClicked: app.clearCache()
                    onActiveFocusChanged: if (activeFocus) page.ensureVisible(this)
                }
                TvButton {
                    id: signOut
                    text: "Sign out of " + app.userName
                    KeyNavigation.up: addAccountButton.KeyNavigation.up
                    KeyNavigation.left: clearCache
                    onClicked: app.logout()
                    onActiveFocusChanged: if (activeFocus) page.ensureVisible(this)
                }
            }
        }
    }
}
