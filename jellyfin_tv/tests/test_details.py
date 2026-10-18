import unittest

from jellyfin_tv.tests.helpers import FakeSettings, app
from jellyfin_tv.models.details import DetailsModel
from jellyfin_tv.models.services import services


class ManualRunner:
    def __init__(self):
        self.calls = []

    def run(self, fn, on_done=None, on_error=None):
        self.calls.append((fn, on_done))

    def flush(self):
        while self.calls:
            fn, on_done = self.calls.pop(0)
            on_done(fn())


def stream(sid, res, size):
    return {"url": "https://x/" + sid, "behaviorHints": {"filename": sid + ".mkv"}, "streamData": {"id": sid, "size": size, "parsedFile": {"resolution": res}}}


class FakeLibrary:
    history = None

    def __init__(self):
        self.stream_calls = []

    def known(self, item_id):
        return {"type": "Movie", "stremioType": "movie"} if item_id != "unknown" else {}

    def peek_item(self, item_id):
        return None

    def item(self, item_id):
        return {"id": item_id, "type": "Movie", "stremioType": "movie", "runtime": 7200}

    def streams(self, item, fresh=False):
        self.stream_calls.append((item["id"], fresh))
        return [stream("remux", "2160p", 72_000_000_000), stream("web", "2160p", 9_000_000_000)]


class DetailsPlayTest(unittest.TestCase):
    def setUp(self):
        app()
        self.runner = ManualRunner()
        services.runner = self.runner
        services.library = FakeLibrary()
        services.settings = FakeSettings(max_bitrate=40)
        self.model = DetailsModel()
        self.played = []
        self.model.playRequested.connect(lambda seconds, sid: self.played.append((seconds, sid)))
        self.model.itemId = "movie"
        fn, on_done = self.runner.calls.pop(0)
        on_done(fn())

    def tearDown(self):
        services.runner = services.library = services.settings = None

    def test_play_waits_for_sources(self):
        self.assertTrue(self.model.sourcesLoading)
        self.model.play(0)
        self.model.play(5.0)
        self.assertTrue(self.model.playPending)
        self.assertEqual(self.played, [])
        self.runner.flush()
        self.assertFalse(self.model.playPending)
        self.assertEqual(self.played, [(5.0, "web")])

    def test_play_after_sources_is_immediate(self):
        self.runner.flush()
        self.model.play(0)
        self.model.play(0)
        self.assertEqual(self.played, [(0.0, "web"), (0.0, "web")])

    def test_sources_start_before_item_when_type_known(self):
        self.runner.calls.clear()
        model = DetailsModel()
        model.itemId = "movie2"
        self.assertTrue(model.sourcesLoading)
        self.assertEqual(len(self.runner.calls), 2)
        self.runner.calls.clear()

    def test_unknown_type_waits_for_item(self):
        self.runner.calls.clear()
        model = DetailsModel()
        model.itemId = "unknown"
        self.assertFalse(model.sourcesLoading)
        self.assertEqual(len(self.runner.calls), 1)
        self.runner.flush()
        self.assertEqual(model.sourceCount, 2)
        self.assertEqual(services.library.stream_calls[-1], ("unknown", False))

    def test_refresh_sources_bypasses_cache(self):
        self.runner.flush()
        self.model.refreshSources()
        self.runner.flush()
        self.assertEqual(services.library.stream_calls[-1], ("movie", True))

    def test_select_source_is_remembered(self):
        self.runner.flush()
        self.model.selectSource("remux")
        self.assertEqual(self.model.selectedSourceId, "remux")
        other = DetailsModel()
        other.itemId = "movie"
        self.runner.flush()
        self.assertEqual(other.selectedSourceId, "remux")

    def test_non_playable_item_stops_loading(self):
        services.library.known = lambda item_id: {"type": "Series"}
        services.library.item = lambda item_id: {"id": item_id, "type": "Series"}
        services.library.series = lambda series_id, kind: ({}, [])
        self.runner.calls.clear()
        model = DetailsModel()
        model.itemId = "series"
        self.assertFalse(model.sourcesLoading)
        self.runner.flush()
        self.assertFalse(model.sourcesLoading)
        self.assertFalse(model.playable)
        self.runner.calls.clear()

    def test_changing_item_drops_pending_play(self):
        self.model.play(0)
        self.model.itemId = "other"
        self.runner.flush()
        self.runner.flush()
        self.assertEqual(self.played, [])


if __name__ == "__main__":
    unittest.main()
