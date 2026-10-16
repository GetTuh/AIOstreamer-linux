import unittest

from PySide6.QtCore import Qt

from jellyfin_tv.tests.helpers import app
from jellyfin_tv.api.remote_socket import SUPPORTED_COMMANDS, capabilities, socket_url
from jellyfin_tv.player.remote_control import RemoteControl


class FakePlayer:
    def __init__(self, active=True):
        self.active = active
        self.calls = []

    def __getattr__(self, name):
        return lambda *args: self.calls.append((name,) + args)


class FakeUi:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *args: self.calls.append((name,) + args)


def message(kind, **data):
    return {"MessageType": kind, "Data": data}


class RemoteControlTest(unittest.TestCase):
    def setUp(self):
        app()
        self.player = FakePlayer()
        self.ui = FakeUi()
        self.remote = RemoteControl(self.player, self.ui)

    def test_play_now_uses_first_item_and_start(self):
        self.remote.handle(message("Play", ItemIds=["a", "b"], PlayCommand="PlayNow", StartPositionTicks=600 * 10_000_000))
        self.assertEqual(self.player.calls, [("play_now", "a", 6_000_000_000.0, "")])
        self.remote.handle(message("Play", ItemIds=["c"], PlayCommand="PlayLast"))
        self.assertEqual(len(self.player.calls), 1)

    def test_playstate(self):
        for command in ("Pause", "Unpause", "PlayPause", "Stop", "NextTrack", "Rewind", "FastForward"):
            self.remote.handle(message("Playstate", Command=command))
        self.remote.handle(message("Playstate", Command="Seek", SeekPositionTicks=1234 * 10_000_000))
        self.assertEqual(self.player.calls, [
            ("set_paused", True), ("set_paused", False), ("set_paused", None), ("stop",), ("next",),
            ("seek_by", -10), ("seek_by", 30), ("seek_to", 1234.0)])

    def test_playstate_ignored_when_idle(self):
        self.player.active = False
        self.remote.handle(message("Playstate", Command="Pause"))
        self.assertEqual(self.player.calls, [])

    def test_navigation_goes_to_mpv_while_playing_and_ui_otherwise(self):
        self.remote.handle(message("GeneralCommand", Name="MoveUp"))
        self.assertEqual(self.player.calls, [("command", "keypress", "UP")])
        self.player.active = False
        for name in ("MoveDown", "Select", "Back", "GoHome", "GoToSearch"):
            self.remote.handle(message("GeneralCommand", Name=name))
        self.remote.handle(message("GeneralCommand", Name="DisplayContent", Arguments={"ItemId": "x"}))
        self.remote.handle(message("GeneralCommand", Name="SendString", Arguments={"String": "dune"}))
        self.assertEqual(self.ui.calls, [
            ("press", Qt.Key_Down), ("press", Qt.Key_Return), ("press", Qt.Key_Escape), ("go_home",),
            ("open_search",), ("open_item", "x"), ("type_text", "dune")])

    def test_messages_tracks_and_volume(self):
        self.remote.handle(message("GeneralCommand", Name="DisplayMessage", Arguments={"Header": "Hi", "Text": "there"}))
        self.remote.handle(message("GeneralCommand", Name="SetAudioStreamIndex", Arguments={"Index": "2"}))
        self.remote.handle(message("GeneralCommand", Name="SetSubtitleStreamIndex", Arguments={"Index": "-1"}))
        self.remote.handle(message("GeneralCommand", Name="SetVolume", Arguments={"Volume": "40"}))
        self.assertEqual(self.player.calls, [
            ("command", "show-text", "Hi — there", 5000), ("set_audio_index", 2), ("set_subtitle_index", -1),
            ("command", "set_property", "volume", 40)])
        self.player.active = False
        self.remote.handle(message("GeneralCommand", Name="DisplayMessage", Arguments={"Text": "idle"}))
        self.assertEqual(self.ui.calls, [("toast", "idle")])

    def test_bad_message_does_not_raise(self):
        self.remote.handle(message("Playstate", Command="Seek", SeekPositionTicks="nope"))
        self.remote.handle({"MessageType": "Play"})

    def test_socket_url_and_capabilities(self):
        self.assertEqual(socket_url("http://h:3020", "T", "D"), "ws://h:3020/socket?api_key=T&deviceId=D")
        self.assertTrue(socket_url("https://h", "T", "D").startswith("wss://h/socket"))
        self.assertTrue(capabilities(True)["SupportsMediaControl"])
        self.assertIn("SetAudioStreamIndex", SUPPORTED_COMMANDS)
        self.assertEqual(capabilities(False)["SupportedCommands"], [])


if __name__ == "__main__":
    unittest.main()
