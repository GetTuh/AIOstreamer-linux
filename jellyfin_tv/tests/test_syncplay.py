import unittest

from jellyfin_tv.tests.helpers import app
from jellyfin_tv.player import syncplay as sp


class FakePlayer:
    def __init__(self):
        self.active = True
        self.observer = None
        self.calls = []
        self.pos = 10.0

    def play_now(self, *args):
        self.calls.append(("play_now",) + args)

    def set_paused(self, value):
        self.calls.append(("paused", value))

    def seek_to(self, seconds):
        self.calls.append(("seek", round(seconds, 2)))

    def stop(self):
        self.calls.append(("stop",))

    def position(self):
        return self.pos


class Recorder:
    def __init__(self):
        self.posts = []


class FakeSession:
    server = "http://s"
    username = "me"

    def auth_header(self):
        return "x"


class SyncPlayTest(unittest.TestCase):
    def setUp(self):
        app()
        self.player = FakePlayer()
        self.sync = sp.SyncPlay(FakeSession(), self.player, None)
        self.posts = []
        self.sync._post = lambda path, body=None: self.posts.append((path, body or {}))
        self.sync.sync_time = lambda: None
        self.now = 1_000_000.0
        self.sync.clock = lambda: self.now
        self.scheduled = []
        self.sync._at = lambda when, action: self.scheduled.append((when, action))
        self.sync.handle({"MessageType": "SyncPlayGroupUpdate", "Data": {"Type": "GroupJoined", "Data": {"GroupId": "g", "GroupName": "Movie night", "Participants": ["me"]}}})

    def command(self, name, when_ms, position_s):
        self.sync.handle({"MessageType": "SyncPlayCommand", "Data": {"Command": name, "When": sp.format_time(when_ms), "PositionTicks": int(position_s * sp.TICKS)}})

    def test_time_helpers(self):
        self.assertEqual(sp.parse_time("2026-10-15T10:35:12.9514537Z"), sp.parse_time("2026-10-15T10:35:12.951453Z"))
        self.assertAlmostEqual(sp.parse_time(sp.format_time(1_792_000_000_123.0)), 1_792_000_000_123.0, places=0)
        self.assertEqual(sp.offset_from([(100, 5), (900, 400), (110, 6), (105, 4)]), 105)

    def test_join_attaches_observer(self):
        self.assertTrue(self.sync.active)
        self.assertEqual(self.sync.groupName, "Movie night")
        self.assertIs(self.player.observer, self.sync)
        self.sync.handle({"MessageType": "SyncPlayGroupUpdate", "Data": {"Type": "UserJoined", "Data": "friend"}})
        self.assertEqual(self.sync.participants, ["friend", "me"])

    def test_queue_loads_paused_and_reports(self):
        queue = {"Reason": "NewPlaylist", "PlayingItemIndex": 0, "StartPositionTicks": 50 * sp.TICKS,
                 "Playlist": [{"ItemId": "movie", "PlaylistItemId": "p1"}]}
        for _ in range(3):
            self.sync.handle({"MessageType": "SyncPlayGroupUpdate", "Data": {"Type": "PlayQueue", "Data": dict(queue, Reason="Queue")}})
        self.assertEqual(self.player.calls[0], ("play_now", "movie", 50.0 * sp.TICKS, "", True))
        self.assertEqual(len([c for c in self.player.calls if c[0] == "play_now"]), 1)
        self.assertEqual(self.posts[0][0], "Buffering")
        self.sync.on_loaded({})
        self.assertEqual(self.posts[-1][0], "Ready")
        self.assertEqual(self.posts[-1][1]["PlaylistItemId"], "p1")

    def test_unpause_on_time_and_late(self):
        self.command("Unpause", self.now * 1000 + 500, 30)
        self.assertEqual(self.player.calls, [("seek", 30.0)])
        when, action = self.scheduled[-1]
        action()
        self.assertEqual(self.player.calls[-1], ("paused", False))
        self.player.calls.clear()
        self.command("Unpause", self.now * 1000 - 2000, 30)
        self.assertEqual(self.player.calls, [("seek", 32.0)])

    def test_pause_and_seek_commands(self):
        self.command("Pause", self.now * 1000, 42)
        self.scheduled[-1][1]()
        self.assertEqual(self.player.calls, [("paused", True), ("seek", 42.0)])
        self.sync.on_pause({}, True)
        self.sync.on_restart({"position": 42.0})
        self.assertEqual(self.posts, [])
        self.command("Seek", self.now * 1000, 90)
        self.sync.on_restart({"position": 90.0})
        self.assertEqual(self.posts[-1][0], "Ready")

    def test_local_actions_become_requests(self):
        self.sync.on_restart({"position": 120.0})
        self.assertEqual(self.posts[-1], ("Seek", {"PositionTicks": 120 * sp.TICKS}))
        self.sync.on_pause({}, True)
        self.assertEqual(self.posts[-1][0], "Pause")
        self.sync.on_pause({}, False)
        self.assertEqual(self.player.calls[-1], ("paused", True))
        self.assertEqual(self.posts[-1][0], "Unpause")
        self.sync.on_pause({}, True)
        self.assertEqual(self.posts[-1][0], "Unpause")

    def test_leave_detaches(self):
        self.sync.handle({"MessageType": "SyncPlayGroupUpdate", "Data": {"Type": "GroupLeft"}})
        self.assertFalse(self.sync.active)
        self.assertIsNone(self.player.observer)
        self.command("Pause", self.now * 1000, 1)
        self.assertEqual(self.player.calls, [])


if __name__ == "__main__":
    unittest.main()
