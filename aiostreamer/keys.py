import json

from PySide6.QtCore import Property, QEvent, QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication, QKeyEvent

from aiostreamer.models.settings import cache_dir

CAPTURE_MS = 6000

APP_ACTIONS = [
    ("up", "Up", ["UP"], (Qt.Key_Up, "")),
    ("down", "Down", ["DOWN"], (Qt.Key_Down, "")),
    ("left", "Left", ["LEFT"], (Qt.Key_Left, "")),
    ("right", "Right", ["RIGHT"], (Qt.Key_Right, "")),
    ("select", "Select / OK", ["ENTER", "KP_ENTER", "SPACE"], (Qt.Key_Return, "\r")),
    ("back", "Back", ["ESC", "BS", "GO_BACK"], (Qt.Key_Escape, "")),
    ("trailer", "Play trailer", ["t"], (Qt.Key_T, "t")),
    ("play", "Pause trailer", ["PLAYPAUSE"], (Qt.Key_MediaTogglePlayPause, "")),
    ("keys", "Show keys", ["F1", "?"], (Qt.Key_F1, "")),
]

PLAYER_ACTIONS = [
    ("play_pause", "Play / pause", ["ENTER", "KP_ENTER", "SPACE", "p", "PLAYPAUSE"]),
    ("seek_back", "Back 10 s", ["LEFT", "REWIND"]),
    ("seek_forward", "Forward 10 s", ["RIGHT", "FORWARD"]),
    ("menu", "Playback menu", ["UP", "MENU"]),
    ("show_ui", "Show controls", ["DOWN"]),
    ("stop", "Stop", ["ESC", "BS", "GO_BACK", "MBTN_BACK", "q"]),
    ("fullscreen", "Fullscreen", ["f"]),
    ("mute", "Mute", ["m", "MUTE"]),
    ("volume_up", "Volume up", ["0", "VOLUME_UP"]),
    ("volume_down", "Volume down", ["9", "VOLUME_DOWN"]),
    ("subtitles", "Next subtitle", ["j"]),
    ("audio", "Next audio track", ["SHARP"]),
    ("keys", "Show keys", ["F1", "?"]),
]

DEFAULTS = {"app." + a[0]: a[2] for a in APP_ACTIONS}
DEFAULTS.update({"player." + a[0]: a[2] for a in PLAYER_ACTIONS})
LABELS = {"app." + a[0]: a[1] for a in APP_ACTIONS}
LABELS.update({"player." + a[0]: a[1] for a in PLAYER_ACTIONS})
APP_KEYS = {a[0]: a[3] for a in APP_ACTIONS}
TEXT_EDIT_KEYS = {"BS", "DEL", "LEFT", "RIGHT", "UP", "DOWN", "HOME", "END", "ENTER", "KP_ENTER", "SPACE", "TAB"}

QT_NAMES = {
    Qt.Key_Up: "UP", Qt.Key_Down: "DOWN", Qt.Key_Left: "LEFT", Qt.Key_Right: "RIGHT",
    Qt.Key_Return: "ENTER", Qt.Key_Enter: "KP_ENTER", Qt.Key_Escape: "ESC", Qt.Key_Backspace: "BS",
    Qt.Key_Tab: "TAB", Qt.Key_Space: "SPACE", Qt.Key_Delete: "DEL", Qt.Key_Insert: "INS",
    Qt.Key_Home: "HOME", Qt.Key_End: "END", Qt.Key_PageUp: "PGUP", Qt.Key_PageDown: "PGDWN",
    Qt.Key_Menu: "MENU", Qt.Key_Back: "GO_BACK", Qt.Key_Forward: "GO_FORWARD",
    Qt.Key_MediaPlay: "PLAY", Qt.Key_MediaPause: "PAUSE", Qt.Key_MediaTogglePlayPause: "PLAYPAUSE",
    Qt.Key_MediaStop: "STOP", Qt.Key_MediaNext: "NEXT", Qt.Key_MediaPrevious: "PREV",
    Qt.Key_AudioForward: "FORWARD", Qt.Key_AudioRewind: "REWIND", Qt.Key_MediaRecord: "RECORD",
    Qt.Key_VolumeUp: "VOLUME_UP", Qt.Key_VolumeDown: "VOLUME_DOWN", Qt.Key_VolumeMute: "MUTE",
    Qt.Key_HomePage: "HOMEPAGE", Qt.Key_Favorites: "FAVORITES", Qt.Key_Search: "SEARCH",
    Qt.Key_Sleep: "SLEEP", Qt.Key_ChannelUp: "CHANNEL_UP", Qt.Key_ChannelDown: "CHANNEL_DOWN",
    Qt.Key_Print: "PRINT",
}
MODIFIER_KEYS = {Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr, Qt.Key_Super_L, Qt.Key_Super_R, Qt.Key_CapsLock, Qt.Key_NumLock}
DISPLAY = {
    "UP": "↑", "DOWN": "↓", "LEFT": "←", "RIGHT": "→", "ENTER": "Enter", "KP_ENTER": "Keypad Enter",
    "ESC": "Esc", "BS": "Backspace", "SPACE": "Space", "TAB": "Tab", "DEL": "Delete", "INS": "Insert",
    "PGUP": "Page Up", "PGDWN": "Page Down", "GO_BACK": "Remote Back", "GO_FORWARD": "Remote Forward",
    "MBTN_BACK": "Mouse Back", "MENU": "Menu", "PLAYPAUSE": "Play/Pause", "PLAY": "Play", "PAUSE": "Pause",
    "REWIND": "Rewind", "FORWARD": "Fast forward", "VOLUME_UP": "Volume +", "VOLUME_DOWN": "Volume −",
    "MUTE": "Mute key", "SHARP": "#", "CHANNEL_UP": "Channel +", "CHANNEL_DOWN": "Channel −",
}


def key_name(key, modifiers=Qt.NoModifier, text=""):
    if key in MODIFIER_KEYS or key in (0, Qt.Key_unknown):
        return None
    mods = []
    if modifiers & Qt.ControlModifier:
        mods.append("Ctrl")
    if modifiers & Qt.AltModifier:
        mods.append("Alt")
    if modifiers & Qt.MetaModifier:
        mods.append("Meta")
    if modifiers & Qt.KeypadModifier and Qt.Key_0 <= key <= Qt.Key_9:
        base = "KP%d" % (key - Qt.Key_0)
    elif key in QT_NAMES:
        base = QT_NAMES[key]
    elif Qt.Key_F1 <= key <= Qt.Key_F35:
        base = "F%d" % (key - Qt.Key_F1 + 1)
    elif text and text.isprintable() and not mods:
        return "SHARP" if text == "#" else text
    elif 0x20 < key < 0x7f:
        base = chr(key).lower()
        if modifiers & Qt.ShiftModifier:
            base = base.upper()
        return "+".join(mods + [base])
    else:
        return None
    if modifiers & Qt.ShiftModifier:
        mods.append("Shift")
    return "+".join(mods + [base])


def display(name):
    parts = name.split("+")
    last = parts[-1]
    if len(last) == 1 and last.isalpha():
        last = ("Shift+" + last) if last.isupper() else last.upper()
    elif last.startswith("KP") and last[2:].isdigit():
        last = "Keypad " + last[2:]
    else:
        last = DISPLAY.get(last, last)
    return "+".join(parts[:-1] + [last])


def load(raw):
    try:
        custom = json.loads(raw or "{}")
    except ValueError:
        return {}
    if not isinstance(custom, dict):
        return {}
    return {k: [str(n) for n in v] for k, v in custom.items() if k in DEFAULTS and isinstance(v, list)}


def bindings(raw):
    custom = load(raw)
    return {action: list(custom.get(action, keys)) for action, keys in DEFAULTS.items()}


def bind(raw, action, name):
    custom = load(raw)
    current = bindings(raw)
    context = action.split(".")[0] + "."
    for other, keys in current.items():
        if other != action and other.startswith(context) and name in keys:
            custom[other] = [k for k in keys if k != name]
    if name not in current[action]:
        custom[action] = current[action] + [name]
    return json.dumps(_trim(custom), sort_keys=True)


def reset(raw, action=None):
    custom = {} if action is None else {k: v for k, v in load(raw).items() if k != action}
    return json.dumps(_trim(custom), sort_keys=True)


def _trim(custom):
    return {k: v for k, v in custom.items() if v != DEFAULTS[k]}


def app_lookup(raw):
    lookup = {}
    for action, keys in bindings(raw).items():
        if action.startswith("app."):
            for name in keys:
                lookup[name] = action[4:]
    return lookup


def write_player_keys(raw):
    current = bindings(raw)
    custom = load(raw)
    data = {
        "bindings": {a[0]: current["player." + a[0]] for a in PLAYER_ACTIONS},
        "custom": [a[0] for a in PLAYER_ACTIONS if "player." + a[0] in custom],
        "legend": [{"title": a[1], "hint": ", ".join(display(n) for n in current["player." + a[0]])} for a in PLAYER_ACTIONS],
    }
    path = cache_dir() / "player-keys.json"
    path.write_text(json.dumps(data))
    return path


class KeyMap(QObject):
    changed = Signal()
    capturingChanged = Signal()

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._settings = settings
        self._window = None
        self._lookup = app_lookup(settings.get("keys"))
        self._capturing = ""
        self._synthetic = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(CAPTURE_MS)
        self._timer.timeout.connect(self.cancelCapture)

    def attach(self, window):
        self._window = window
        window.installEventFilter(self)

    def _raw(self):
        return self._settings.get("keys")

    def _store(self, raw):
        self._settings.set("keys", raw)
        self._lookup = app_lookup(raw)
        self.changed.emit()

    @Property("QVariantList", notify=changed)
    def actions(self):
        current = bindings(self._raw())
        custom = load(self._raw())
        rows = []
        for context, actions in (("app", APP_ACTIONS), ("player", PLAYER_ACTIONS)):
            for entry in actions:
                action = "%s.%s" % (context, entry[0])
                rows.append({
                    "action": action,
                    "context": context,
                    "label": entry[1],
                    "keys": ", ".join(display(n) for n in current[action]) or "None",
                    "custom": action in custom,
                })
        return rows

    @Property(str, notify=capturingChanged)
    def capturing(self):
        return self._capturing

    @Slot(str)
    def capture(self, action):
        if action in DEFAULTS:
            self._capturing = action
            self._timer.start()
            self.capturingChanged.emit()

    @Slot()
    def cancelCapture(self):
        self._timer.stop()
        if self._capturing:
            self._capturing = ""
            self.capturingChanged.emit()

    @Slot(str)
    def reset(self, action):
        self._store(reset(self._raw(), action or None))

    def assign(self, action, name):
        self._store(bind(self._raw(), action, name))

    def press(self, key, text=""):
        if self._window is None:
            return
        self._synthetic = True
        try:
            for kind in (QEvent.KeyPress, QEvent.KeyRelease):
                QGuiApplication.sendEvent(self._window, QKeyEvent(kind, key, Qt.NoModifier, text))
        finally:
            self._synthetic = False

    def _editing_text(self):
        item = self._window.activeFocusItem() if self._window is not None else None
        return item is not None and (item.inherits("QQuickTextInput") or item.inherits("QQuickTextEdit"))

    def eventFilter(self, obj, event):
        if obj is not self._window or event.type() not in (QEvent.KeyPress, QEvent.KeyRelease) or self._synthetic:
            return False
        name = key_name(event.key(), event.modifiers(), event.text())
        if self._capturing:
            if name and event.type() == QEvent.KeyPress and not event.isAutoRepeat():
                action = self._capturing
                self.cancelCapture()
                self.assign(action, name)
            return name is not None
        if name is None:
            return False
        if self._editing_text() and (name in TEXT_EDIT_KEYS or len(name) == 1):
            return False
        action = self._lookup.get(name)
        if action is None:
            return False
        key, text = APP_KEYS[action]
        if key == event.key() and not (event.modifiers() & ~Qt.KeypadModifier):
            return False
        if event.type() == QEvent.KeyPress:
            self._synthetic = True
            try:
                QGuiApplication.sendEvent(self._window, QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier, text, event.isAutoRepeat()))
                QGuiApplication.sendEvent(self._window, QKeyEvent(QEvent.KeyRelease, key, Qt.NoModifier, text, event.isAutoRepeat()))
            finally:
                self._synthetic = False
        return True
