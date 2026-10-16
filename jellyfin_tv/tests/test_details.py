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


class FakeLibrary:
    def item(self, item_id):
        return {"Id": item_id, "Type": "Movie"}

    def sources(self, item_id):
        return [
            {"Id": "remux", "Name": "2160p", "Bitrate": 80_000_000},
            {"Id": "web", "Name": "2160p", "Bitrate": 6_000_000},
        ]


class DetailsPlayTest(unittest.TestCase):
    def setUp(self):
        app()
        self.runner = ManualRunner()
        services.runner = self.runner
        services.library = FakeLibrary()
        services.settings = FakeSettings(max_bitrate=40)
        self.model = DetailsModel()
        self.played = []
        self.model.playRequested.connect(lambda ticks, sid: self.played.append((ticks, sid)))
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

    def test_sources_load_from_the_start_and_rerank_when_item_arrives(self):
        services.library.item = lambda item_id: {"Id": item_id, "Type": "Movie", "OriginalLanguage": "ja"}
        services.library.sources = lambda item_id: [
            {"Id": "dub", "Name": "2160p", "MediaStreams": [{"Type": "Audio", "Language": "eng"}]},
            {"Id": "orig", "Name": "1080p", "MediaStreams": [{"Type": "Audio", "Language": "jpn"}]},
        ]
        services.settings = FakeSettings(audio_language="original")
        self.runner.calls.clear()
        model = DetailsModel()
        model.itemId = "anime"
        self.assertTrue(model.sourcesLoading)
        item_call, sources_call = self.runner.calls
        sources_call[1](sources_call[0]())
        self.assertEqual(model.selectedSourceId, "dub")
        item_call[1](item_call[0]())
        self.assertEqual(model.selectedSourceId, "orig")
        self.runner.calls.clear()

    def test_non_playable_item_stops_loading(self):
        services.library.item = lambda item_id: {"Id": item_id, "Type": "Series"}
        self.runner.calls.clear()
        model = DetailsModel()
        model.itemId = "series"
        item_call = self.runner.calls[0]
        item_call[1](item_call[0]())
        self.assertFalse(model.sourcesLoading)
        self.runner.calls.clear()

    def test_changing_item_drops_pending_play(self):
        self.model.play(0)
        self.model.itemId = "other"
        self.runner.flush()
        self.runner.flush()
        self.assertEqual(self.played, [])


if __name__ == "__main__":
    unittest.main()
