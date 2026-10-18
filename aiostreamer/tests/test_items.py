import unittest

from aiostreamer.tests.helpers import SyncRunner, app
import tempfile

from aiostreamer.api.history import WatchState
from aiostreamer.api.meta import runtime_text
from aiostreamer.models.items import ItemListModel, LibraryModel, match_score, normalize_title, subtitle_for, title_for
from aiostreamer.models.services import services


class FakeLibrary:
    def __init__(self):
        self.history = WatchState(tempfile.mkdtemp(prefix="aios-hist-") + "/s.json")
        self.calls = []
        self.cached = None

    def catalog(self, kind, catalog_id, extra=None, start=0, limit=0):
        self.calls.append((kind, catalog_id, extra, start))
        items = [{"id": "%s%d" % ((extra or {}).get("genre", ""), i), "name": str(i)} for i in range(start, min(start + 50, 75))]
        return items, start + len(items) + (1 if items else 0)

    def peek_catalog(self, kind, catalog_id, extra=None):
        return self.cached


class HelpersTest(unittest.TestCase):
    def test_titles(self):
        ep = {"type": "Episode", "seriesName": "Show", "name": "Pilot", "season": 1, "episode": 1}
        self.assertEqual(title_for(ep), "Show")
        self.assertEqual(subtitle_for(ep), "S1:E1 · Pilot")
        self.assertEqual(subtitle_for({"type": "Series", "year": "2008 – 2013"}), "2008 – 2013")
        self.assertEqual(subtitle_for({"type": "Movie", "year": "1999"}), "1999")

    def test_runtime(self):
        self.assertEqual(runtime_text(49 * 60), "49m")
        self.assertEqual(runtime_text(125 * 60), "2h 5m")
        self.assertEqual(runtime_text(0), "")


class SearchScoreTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_title("Naruto Shippūden!"), "naruto shippuden")

    def test_exact_beats_prefix_beats_contains(self):
        exact = match_score("top gun", "Top Gun")
        prefix = match_score("top gun", "Top Gun: Maverick")
        words = match_score("top gun", "Real Top Gun")
        none = match_score("top gun", "Flower Boy")
        self.assertGreater(exact, prefix)
        self.assertGreater(prefix, words)
        self.assertGreater(words, none)
        self.assertEqual(none, 0.0)

    def test_accents_ignored(self):
        self.assertGreaterEqual(match_score("naruto ship", "Naruto Shippūden"), 2.5)


class ItemListModelTest(unittest.TestCase):
    def tearDown(self):
        services.library = services.runner = None

    def setUp(self):
        app()
        services.library = FakeLibrary()
        self.data = [{"id": "a", "name": "A"}, {"id": "b", "name": "B"}]
        self.model = ItemListModel(SyncRunner(), lambda s, n: (list(self.data), len(self.data)))

    def test_reload_and_get(self):
        self.model.reload()
        self.assertEqual(self.model.count, 2)
        self.assertEqual(self.model.get(1)["itemId"], "b")
        self.assertEqual(self.model.indexOf("b"), 1)
        self.assertEqual(self.model.get(5), {})

    def test_same_ids_refresh_in_place(self):
        self.model.reload()
        resets = []
        changes = []
        self.model.modelReset.connect(lambda: resets.append(1))
        self.model.dataChanged.connect(lambda *a: changes.append(1))
        self.data = [{"id": "a", "name": "A2"}, {"id": "b", "name": "B"}]
        self.model.reload()
        self.assertEqual(resets, [])
        self.assertEqual(changes, [1])
        self.assertEqual(self.model.get(0)["name"], "A2")

    def test_changed_ids_reset(self):
        self.model.reload()
        resets = []
        self.model.modelReset.connect(lambda: resets.append(1))
        self.data = [{"id": "c", "name": "C"}]
        self.model.reload()
        self.assertEqual(resets, [1])

    def test_paging(self):
        items = [{"id": str(i), "name": str(i)} for i in range(25)]
        model = ItemListModel(SyncRunner(), lambda s, n: (items[s:s + n], len(items)), page_size=10)
        model.reload()
        self.assertEqual(model.count, 10)
        self.assertTrue(model.canFetchMore())
        model.fetchMore()
        model.fetchMore()
        self.assertEqual(model.count, 25)
        self.assertFalse(model.canFetchMore())

    def test_episode_context(self):
        model = ItemListModel(SyncRunner(), lambda s, n: ([{"id": "e", "name": "Pilot", "episode": 1, "runtime": 49 * 60}], 1), context="episodes")
        model.reload()
        self.assertEqual(model.get(0)["name"], "1. Pilot")
        self.assertEqual(model.get(0)["subtitle"], "49m")

    def test_user_data_comes_from_history(self):
        self.model.reload()
        history = services.library.history
        history.record({"id": "a", "type": "Movie"}, 600, 3000)
        history.set_watched([{"id": "b"}], True)
        history.set_favorite({"id": "b"}, True)
        self.assertAlmostEqual(self.model.get(0)["progress"], 0.2)
        self.assertTrue(self.model.get(1)["played"])
        self.assertTrue(self.model.get(1)["favorite"])
        self.assertFalse(self.model.get(0)["played"])

    def test_cached_rows_paint_before_fetch(self):
        pending = []

        class Deferred:
            def run(self, fn, on_done=None, on_error=None):
                pending.append((fn, on_done))

        model = ItemListModel(Deferred(), lambda s, n: ([{"id": "fresh"}], 1), peek=lambda: ([{"id": "cached"}], 1))
        model.reload()
        self.assertEqual(model.get(0)["itemId"], "cached")
        self.assertTrue(model.loaded)
        fn, done = pending.pop()
        done(fn())
        self.assertEqual(model.get(0)["itemId"], "fresh")


class LibraryModelTest(unittest.TestCase):
    def setUp(self):
        app()
        services.library = FakeLibrary()
        services.runner = SyncRunner()

    def tearDown(self):
        services.library = services.runner = None

    def test_pages_until_catalog_runs_out(self):
        model = LibraryModel()
        model.catalogType = "movie"
        model.catalogId = "top"
        model.reload()
        self.assertEqual(model.count, 50)
        for _ in range(3):
            model.fetchMore()
        self.assertEqual(model.count, 75)
        self.assertFalse(model.canFetchMore())

    def test_genre_cycle_and_required_genre(self):
        model = LibraryModel()
        model.genres = ["Action", "Drama"]
        self.assertEqual(model.genreName, "All")
        model.stepGenre(1)
        self.assertEqual(model.genre, "Action")
        model.stepGenre(-1)
        model.stepGenre(-1)
        self.assertEqual(model.genre, "Drama")
        required = LibraryModel()
        required.genreRequired = True
        required.genres = ["2026", "2025"]
        self.assertEqual(required.genre, "2026")
        required.stepGenre(1)
        required.stepGenre(1)
        self.assertEqual(required.genre, "2026")
        self.assertEqual(services.library.calls[-1][2], {"genre": "2026"})


if __name__ == "__main__":
    unittest.main()
