import json
import re
import unittest
from pathlib import Path

from aiostreamer.tests.helpers import FakeSettings, app
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QGuiApplication, QKeyEvent

from aiostreamer import keys
from aiostreamer.player.mpv_runner import build_options


class FakeWindow(QObject):
    def __init__(self):
        super().__init__()
        self.received = []
        self.focus = None

    def activeFocusItem(self):
        return self.focus

    def event(self, event):
        if event.type() == QEvent.KeyPress:
            self.received.append(event.key())
        return True


class FakeTextInput(QObject):
    def inherits(self, name):
        return name == "QQuickTextInput"


def send(window, key, modifiers=Qt.NoModifier, text=""):
    for kind in (QEvent.KeyPress, QEvent.KeyRelease):
        QGuiApplication.sendEvent(window, QKeyEvent(kind, key, modifiers, text))


class KeyNameTest(unittest.TestCase):
    def test_names_follow_mpv(self):
        self.assertEqual(keys.key_name(Qt.Key_Return), "ENTER")
        self.assertEqual(keys.key_name(Qt.Key_Back), "GO_BACK")
        self.assertEqual(keys.key_name(Qt.Key_F1), "F1")
        self.assertEqual(keys.key_name(Qt.Key_A, Qt.NoModifier, "a"), "a")
        self.assertEqual(keys.key_name(Qt.Key_A, Qt.ShiftModifier, "A"), "A")
        self.assertEqual(keys.key_name(Qt.Key_A, Qt.ControlModifier, "\x01"), "Ctrl+a")
        self.assertEqual(keys.key_name(Qt.Key_Up, Qt.ShiftModifier), "Shift+UP")
        self.assertEqual(keys.key_name(Qt.Key_NumberSign, Qt.ShiftModifier, "#"), "SHARP")
        self.assertEqual(keys.key_name(Qt.Key_5, Qt.KeypadModifier, "5"), "KP5")
        self.assertIsNone(keys.key_name(Qt.Key_Shift, Qt.ShiftModifier))

    def test_display(self):
        self.assertEqual(keys.display("a"), "A")
        self.assertEqual(keys.display("A"), "Shift+A")
        self.assertEqual(keys.display("GO_BACK"), "Remote Back")
        self.assertEqual(keys.display("Ctrl+LEFT"), "Ctrl+←")


class BindingTest(unittest.TestCase):
    def test_bind_moves_key_within_context_only(self):
        raw = keys.bind("", "app.back", "h")
        raw = keys.bind(raw, "app.trailer", "BS")
        current = keys.bindings(raw)
        self.assertEqual(current["app.back"], ["ESC", "GO_BACK", "h"])
        self.assertEqual(current["app.trailer"], ["t", "BS"])
        self.assertIn("BS", current["player.stop"])

    def test_reset_and_garbage(self):
        raw = keys.bind("", "player.stop", "x")
        self.assertEqual(keys.reset(raw, "player.stop"), "{}")
        self.assertEqual(keys.reset(keys.bind(raw, "app.up", "w")), "{}")
        self.assertEqual(keys.bindings("not json"), keys.bindings(""))
        self.assertEqual(keys.load('{"app.up": ["w"], "bogus": ["x"]}'), {"app.up": ["w"]})

    def test_player_keys_reach_mpv(self):
        raw = keys.bind("", "player.seek_forward", "l")
        opts = build_options(FakeSettings(keys=raw), "T")["script-opts"]
        path = re.search(r"aios-keys=([^,]+)", opts).group(1)
        data = json.loads(Path(path).read_text())
        self.assertEqual(data["bindings"]["seek_forward"], ["RIGHT", "FORWARD", "l"])
        self.assertEqual(data["custom"], ["seek_forward"])
        self.assertIn({"title": "Forward 10 s", "hint": "→, Fast forward, L"}, data["legend"])


class KeyMapTest(unittest.TestCase):
    def setUp(self):
        app()
        self.settings = FakeSettings()
        self.map = keys.KeyMap(self.settings)
        self.window = FakeWindow()
        self.map.attach(self.window)

    def test_defaults_pass_through_and_extra_keys_remap(self):
        send(self.window, Qt.Key_Return, text="\r")
        send(self.window, Qt.Key_Space, text=" ")
        send(self.window, Qt.Key_Question, Qt.ShiftModifier, "?")
        self.assertEqual(self.window.received, [Qt.Key_Return, Qt.Key_Return, Qt.Key_F1])

    def test_capture_binds_next_key(self):
        self.map.capture("app.back")
        self.assertEqual(self.map.capturing, "app.back")
        send(self.window, Qt.Key_H, text="h")
        self.assertEqual(self.window.received, [])
        self.assertEqual(self.map.capturing, "")
        send(self.window, Qt.Key_H, text="h")
        self.assertEqual(self.window.received, [Qt.Key_Escape])
        self.assertTrue([a for a in self.map.actions if a["action"] == "app.back"][0]["custom"])

    def test_text_fields_keep_typing(self):
        self.settings.set("keys", keys.bind("", "app.back", "h"))
        self.map = keys.KeyMap(self.settings)
        self.map.attach(self.window)
        self.window.focus = FakeTextInput()
        send(self.window, Qt.Key_H, text="h")
        send(self.window, Qt.Key_Back)
        self.assertEqual(self.window.received, [Qt.Key_H, Qt.Key_Escape])

    def test_synthetic_presses_are_not_remapped(self):
        self.settings.set("keys", keys.bind("", "app.back", "ENTER"))
        self.map = keys.KeyMap(self.settings)
        self.map.attach(self.window)
        self.map.press(Qt.Key_Return, "\r")
        send(self.window, Qt.Key_Return, text="\r")
        self.assertEqual(self.window.received, [Qt.Key_Return, Qt.Key_Escape])


if __name__ == "__main__":
    unittest.main()
