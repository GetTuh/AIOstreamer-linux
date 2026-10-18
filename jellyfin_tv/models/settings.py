import os
import socket
import uuid
from pathlib import Path

from PySide6.QtCore import Property, QObject, QSettings, Signal

APP_ID = "jellyfin-tv"


def config_dir():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    path = Path(base) / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    path = Path(base) / APP_ID
    path.mkdir(parents=True, exist_ok=True)
    return path


def _setting(kind, key, notify):
    return Property(kind, lambda self: self.get(key), lambda self, v: self.set(key, kind(v)), notify=notify)


class Settings(QObject):
    changed = Signal()

    DEFAULTS = {
        "server": "",
        "username": "",
        "audio_language": "",
        "subtitle_language": "eng,en",
        "subtitle_mode": "auto",
        "autoplay_next": True,
        "upnext_seconds": 10,
        "mpv_extra": "",
        "max_resolution": 0,
        "max_bitrate": 0,
        "player_ui": "overlay",
        "audio_output": "auto",
        "skip_segments": "ask",
        "trailer_previews": "muted",
        "gamepad": True,
    }

    def __init__(self):
        super().__init__()
        self._store = QSettings(str(config_dir() / "settings.ini"), QSettings.IniFormat)
        if not self._store.value("device_id"):
            self._store.setValue("device_id", uuid.uuid4().hex)

    def get(self, key):
        default = self.DEFAULTS.get(key)
        value = self._store.value(key, default)
        if isinstance(default, bool):
            return value in (True, "true", "1", 1)
        if isinstance(default, int):
            try:
                return int(value)
            except (TypeError, ValueError):
                return default
        return value if value is not None else default

    def set(self, key, value):
        if self.get(key) == value:
            return
        self._store.setValue(key, value)
        self._store.sync()
        self.changed.emit()

    def get_source(self, item_id):
        return self._store.value("sources/%s" % item_id, "") or ""

    def set_source(self, item_id, source_id):
        self._store.setValue("sources/%s" % item_id, source_id)
        self._store.sync()

    @property
    def device_id(self):
        return self._store.value("device_id")

    @property
    def device_name(self):
        return socket.gethostname() or "Linux TV"

    @property
    def mpv_conf_path(self):
        return config_dir() / "mpv.conf"

    server = _setting(str, "server", changed)
    username = _setting(str, "username", changed)
    audioLanguage = _setting(str, "audio_language", changed)
    subtitleLanguage = _setting(str, "subtitle_language", changed)
    subtitleMode = _setting(str, "subtitle_mode", changed)
    mpvExtra = _setting(str, "mpv_extra", changed)
    autoplayNext = _setting(bool, "autoplay_next", changed)
    upNextSeconds = _setting(int, "upnext_seconds", changed)
    maxResolution = _setting(int, "max_resolution", changed)
    maxBitrate = _setting(int, "max_bitrate", changed)
    playerUi = _setting(str, "player_ui", changed)
    audioOutput = _setting(str, "audio_output", changed)
    skipSegments = _setting(str, "skip_segments", changed)
    trailerPreviews = _setting(str, "trailer_previews", changed)
    gamepad = _setting(bool, "gamepad", changed)
