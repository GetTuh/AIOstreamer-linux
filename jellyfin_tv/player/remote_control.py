import logging

from PySide6.QtCore import QObject, Qt, Slot

log = logging.getLogger("jellyfin_tv.remote")

TICKS = 10_000_000
UI_KEYS = {
    "MoveUp": Qt.Key_Up, "MoveDown": Qt.Key_Down, "MoveLeft": Qt.Key_Left, "MoveRight": Qt.Key_Right,
    "Select": Qt.Key_Return, "Back": Qt.Key_Escape, "PageUp": Qt.Key_PageUp, "PageDown": Qt.Key_PageDown,
}
MPV_KEYS = {
    "MoveUp": "UP", "MoveDown": "DOWN", "MoveLeft": "LEFT", "MoveRight": "RIGHT",
    "Select": "ENTER", "Back": "ESC", "PageUp": "PGUP", "PageDown": "PGDWN",
}


class RemoteControl(QObject):
    def __init__(self, player, ui, parent=None):
        super().__init__(parent)
        self.player = player
        self.ui = ui
        self.enabled = True

    @Slot(dict)
    def handle(self, message):
        kind = message.get("MessageType")
        data = message.get("Data") or {}
        if kind and kind.startswith("SyncPlay"):
            self.ui.syncplay_message(message)
            return
        if not self.enabled:
            return
        try:
            if kind == "Play":
                self._play(data)
            elif kind == "Playstate":
                self._playstate(data)
            elif kind == "GeneralCommand":
                self._general(data.get("Name"), data.get("Arguments") or {})
        except Exception:
            log.exception("remote command %s failed", kind)

    def _play(self, data):
        ids = data.get("ItemIds") or []
        if not ids or data.get("PlayCommand") not in (None, "PlayNow", "PlayInstantMix", "PlayShuffle"):
            return
        self.player.play_now(ids[0], float(data.get("StartPositionTicks") or 0), data.get("MediaSourceId") or "")

    def _playstate(self, data):
        command = data.get("Command")
        if not self.player.active:
            return
        if command == "Pause":
            self.player.set_paused(True)
        elif command == "Unpause":
            self.player.set_paused(False)
        elif command == "PlayPause":
            self.player.set_paused(None)
        elif command == "Stop":
            self.player.stop()
        elif command == "Seek" and data.get("SeekPositionTicks") is not None:
            self.player.seek_to(float(data["SeekPositionTicks"]) / TICKS)
        elif command == "NextTrack":
            self.player.next()
        elif command == "PreviousTrack":
            self.player.seek_to(0)
        elif command == "Rewind":
            self.player.seek_by(-10)
        elif command == "FastForward":
            self.player.seek_by(30)

    def _general(self, name, args):
        playing = self.player.active
        if name in UI_KEYS:
            if playing:
                self.player.command("keypress", MPV_KEYS[name])
            else:
                self.ui.press(UI_KEYS[name])
        elif name == "DisplayMessage":
            text = " — ".join(p for p in (args.get("Header"), args.get("Text")) if p)
            if playing:
                self.player.command("show-text", text, int(args.get("TimeoutMs") or 5000))
            else:
                self.ui.toast(text)
        elif name == "SetAudioStreamIndex":
            self.player.set_audio_index(int(args.get("Index", -1)))
        elif name == "SetSubtitleStreamIndex":
            self.player.set_subtitle_index(int(args.get("Index", -1)))
        elif name in ("VolumeUp", "VolumeDown"):
            self.player.command("add", "volume", 5 if name == "VolumeUp" else -5)
        elif name == "SetVolume" and args.get("Volume") is not None:
            self.player.command("set_property", "volume", int(args["Volume"]))
        elif name in ("Mute", "Unmute"):
            self.player.command("set_property", "mute", name == "Mute")
        elif name == "ToggleMute":
            self.player.command("cycle", "mute")
        elif name == "GoHome" and not playing:
            self.ui.go_home()
        elif name == "GoToSearch" and not playing:
            self.ui.open_search()
        elif name == "GoToSettings" and not playing:
            self.ui.open_settings()
        elif name == "DisplayContent" and args.get("ItemId") and not playing:
            self.ui.open_item(args["ItemId"])
        elif name == "SendString" and args.get("String") and not playing:
            self.ui.type_text(args["String"])
