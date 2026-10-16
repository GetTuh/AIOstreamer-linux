import os
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
_tmp = tempfile.mkdtemp(prefix="jftv-test-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(_tmp, "config")
os.environ["XDG_CACHE_HOME"] = os.path.join(_tmp, "cache")

from PySide6.QtGui import QGuiApplication

_app = QGuiApplication.instance() or QGuiApplication([])


def app():
    return _app


class SyncRunner:
    def run(self, fn, on_done=None, on_error=None):
        try:
            result = fn()
        except Exception as exc:
            if on_error:
                on_error(exc)
            return
        if on_done:
            on_done(result)


class FakeSignal:
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        self.slots.append(slot)

    def emit(self, *args):
        for slot in self.slots:
            slot(*args)


class FakeSettings:
    def __init__(self, **values):
        self.changed = FakeSignal()
        from pathlib import Path
        self.values = {
            "audio_language": "",
            "subtitle_language": "eng,en",
            "subtitle_mode": "auto",
            "mpv_extra": "",
            "max_resolution": 0,
            "prefer_hdr": True,
            "max_bitrate": 0,
            "player_ui": "overlay",
            "audio_output": "auto",
            "remote_control": False,
            "skip_segments": "ask",
            "trailer_previews": "muted",
            "gamepad": True,
            "autoplay_next": True,
            "upnext_seconds": 10,
        }
        self.values.update(values)
        self.sources = {}
        self.mpv_conf_path = Path(_tmp) / "missing-mpv.conf"
        self.device_id = "test-device"
        self.device_name = "test"

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value
        self.changed.emit()

    def get_source(self, item_id):
        return self.sources.get(item_id, "")

    def set_source(self, item_id, source_id):
        self.sources[item_id] = source_id
