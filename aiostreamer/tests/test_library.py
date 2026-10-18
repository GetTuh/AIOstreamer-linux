import tempfile
import unittest

from aiostreamer.api import meta as m
from aiostreamer.api.history import WatchState
from aiostreamer.api.library import Library

SHOW = {
    "id": "tt0903747", "type": "series", "name": "Breaking Bad", "poster": "https://img/p", "background": "https://img/b",
    "logo": "https://img/l", "releaseInfo": "2008–2013", "imdbRating": "9.5", "runtime": "49 min",
    "genres": ["Crime", "Drama"], "description": "Chemistry.",
    "trailers": [{"source": "VFkjBy2b50Q", "type": "Trailer"}, {"source": "clip1234567", "type": "Clip"}],
    "trailerStreams": [{"ytId": "VFkjBy2b50Q"}],
    "videos": [
        {"id": "tt0903747:2:1", "season": 2, "episode": 1, "name": "Seven Thirty-Seven", "released": "2009-03-08T00:00:00Z"},
        {"id": "tt0903747:1:2", "season": 1, "episode": 2, "name": "Cat's in the Bag", "released": "2008-01-27T00:00:00Z"},
        {"id": "tt0903747:0:1", "season": 0, "episode": 1, "name": "Special", "released": "2009-01-01T00:00:00Z"},
        {"id": "tt0903747:1:1", "season": 1, "number": 1, "title": "Pilot", "released": "2008-01-20T00:00:00Z", "thumbnail": "https://img/t"},
        {"id": "tt0903747:2:2", "season": 2, "episode": 2, "name": "Future", "released": "2999-01-01T00:00:00Z"},
    ],
}


def history():
    return WatchState(tempfile.mkdtemp(prefix="aios-hist-") + "/state.json")


class MetaTest(unittest.TestCase):
    def test_from_meta(self):
        item = m.from_meta(SHOW)
        self.assertEqual(item["type"], "Series")
        self.assertEqual(item["year"], "2008 – 2013")
        self.assertEqual(item["runtime"], 49 * 60)
        self.assertEqual(item["rating"], "9.5")
        self.assertEqual(item["trailers"], ["VFkjBy2b50Q"])
        self.assertEqual(m.from_meta({"id": "tt1", "type": "movie", "imdbRating": "bad"})["rating"], "")
        self.assertEqual(m.from_meta({"id": "k1", "type": "anime"})["type"], "Series")
        self.assertEqual(m.from_meta({"id": "c1", "type": "tv", "videos": [{"id": "x", "season": 1}]})["type"], "Series")
        self.assertEqual(m.from_meta({"id": "c1", "type": "tv"})["type"], "Movie")

    def test_episodes_ordered_with_series_art(self):
        episodes = m.episodes(SHOW)
        self.assertEqual([e["id"] for e in episodes], ["tt0903747:0:1", "tt0903747:1:1", "tt0903747:1:2", "tt0903747:2:1", "tt0903747:2:2"])
        pilot = episodes[1]
        self.assertEqual((pilot["name"], pilot["episode"], pilot["seriesId"], pilot["seriesName"]), ("Pilot", 1, "tt0903747", "Breaking Bad"))
        self.assertEqual(pilot["logo"], "https://img/l")
        self.assertEqual(pilot["runtime"], 49 * 60)
        self.assertEqual(m.seasons(episodes), [1, 2, 0])
        self.assertEqual(m.episode_label(pilot), "S1:E1")
        self.assertFalse(m.released(episodes[-1]))

    def test_runtime_parsing(self):
        self.assertEqual(m.runtime_seconds("142 min"), 142 * 60)
        self.assertEqual(m.runtime_seconds("2h 22min"), 142 * 60)
        self.assertEqual(m.runtime_seconds("1h"), 3600)
        self.assertEqual(m.runtime_seconds("90"), 90 * 60)
        self.assertEqual(m.runtime_seconds("N/A"), 0)
        self.assertEqual(m.runtime_text(142 * 60), "2h 22m")

    def test_catalogs(self):
        self.assertEqual(m.catalog_title({"type": "movie", "name": "Popular"}), "Popular Movies")
        self.assertEqual(m.catalog_title({"type": "series", "name": "Trending Shows"}), "Trending Shows")
        self.assertEqual(m.catalog_title({"type": "anime", "name": "Airing"}), "Airing Anime")
        year = {"type": "movie", "id": "year", "extra": [{"name": "genre", "isRequired": True, "options": ["2026", "2025"]}]}
        self.assertTrue(m.browsable(year))
        self.assertEqual(m.home_extra(year), {"genre": "2026"})
        self.assertFalse(m.browsable({"extra": [{"name": "search", "isRequired": True}]}))
        self.assertFalse(m.browsable({"extra": [{"name": "lastVideosIds", "isRequired": True}]}))
        self.assertTrue(m.searchable({"extra": [{"name": "search"}]}))
        self.assertTrue(m.searchable({"extraSupported": ["search"]}))


class WatchStateTest(unittest.TestCase):
    def test_thresholds(self):
        state = history()
        movie = {"id": "tt1", "type": "Movie", "name": "A", "runtime": 6000}
        state.record(movie, 30, 6000)
        self.assertEqual(state.progress("tt1"), (0.0, 0.0))
        state.record(movie, 1200, 6000)
        self.assertAlmostEqual(state.fraction("tt1"), 0.2)
        self.assertFalse(state.watched("tt1"))
        self.assertTrue(state.record(movie, 5500, 6000))
        self.assertTrue(state.watched("tt1"))
        self.assertEqual(state.resume(), [])
        state.record(movie, 30, 6000)
        self.assertTrue(state.watched("tt1"))
        state.record(movie, 600, 6000)
        self.assertFalse(state.watched("tt1"))

    def test_resume_one_per_show_newest_first(self):
        clock = [0]
        state = WatchState(tempfile.mkdtemp(prefix="aios-hist-") + "/s.json", clock=lambda: clock[0])
        for i, item_id in enumerate(["s:1:1", "tt9", "s:1:2"]):
            clock[0] = i
            state.record({"id": item_id, "type": "Episode" if item_id.startswith("s") else "Movie", "seriesId": "s" if item_id.startswith("s") else None}, 600, 3000)
        self.assertEqual([i["id"] for i in state.resume()], ["s:1:2", "tt9"])

    def test_persisted_and_favorites(self):
        path = tempfile.mkdtemp(prefix="aios-hist-") + "/s.json"
        state = WatchState(path)
        state.set_favorite({"id": "tt1", "type": "Movie", "name": "A", "overview": "x" * 10, "extra": "dropped"}, True)
        state.set_watched([{"id": "tt2", "type": "Movie"}], True)
        again = WatchState(path)
        self.assertTrue(again.favorite("tt1"))
        self.assertNotIn("extra", again.favorites()[0])
        self.assertTrue(again.watched("tt2"))
        again.set_watched([{"id": "tt2"}], False)
        self.assertFalse(again.watched("tt2"))

    def test_corrupt_file_starts_empty(self):
        path = tempfile.mkdtemp(prefix="aios-hist-") + "/s.json"
        with open(path, "w") as out:
            out.write("{not json")
        self.assertEqual(WatchState(path).resume(), [])


class FakeClient:
    def __init__(self):
        self.meta_calls = 0
        self.pages = {}

    def meta(self, kind, item_id, fresh=False):
        self.meta_calls += 1
        if item_id != SHOW["id"]:
            return {"id": item_id, "type": kind, "name": "Movie " + item_id}
        return SHOW

    def peek_meta(self, kind, item_id):
        return None

    def manifest(self):
        return {"catalogs": [
            {"type": "movie", "id": "top", "name": "Popular", "extra": [{"name": "search"}, {"name": "skip"}]},
            {"type": "series", "id": "top", "name": "Popular", "extra": [{"name": "search"}]},
            {"type": "series", "id": "cal", "name": "Calendar", "extra": [{"name": "calendarVideosIds", "isRequired": True}]},
        ]}

    def catalog(self, kind, catalog_id, extra=None):
        extra = extra or {}
        if "search" in extra:
            return [{"id": "%s-%s" % (kind, extra["search"]), "type": kind, "name": extra["search"]}]
        skip = int(extra.get("skip") or 0)
        return [{"id": "tt%d" % i, "type": kind, "name": str(i)} for i in range(skip, min(skip + 50, 120))]


class FakeSession:
    def __init__(self):
        self.client = FakeClient()
        self.history = history()


class LibraryTest(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()
        self.lib = Library(self.session)
        self.episodes = {e["id"]: e for e in m.episodes(SHOW)}

    def watch(self, *ids):
        for item_id in ids:
            self.session.history.record(self.episodes[item_id], 2900, 2940)

    def test_episode_lookup_without_context(self):
        item = self.lib.item("tt0903747:1:2")
        self.assertEqual(item["type"], "Episode")
        self.assertEqual(item["name"], "Cat's in the Bag")
        self.assertEqual(self.lib.known("tt0903747:2:1")["seriesId"], "tt0903747")

    def test_next_up_follows_last_watched_and_skips_watched(self):
        self.watch("tt0903747:1:1")
        self.assertEqual([e["id"] for e in self.lib.next_up()], ["tt0903747:1:2"])
        self.watch("tt0903747:2:1")
        self.assertEqual(self.lib.next_up(), [])
        self.assertEqual(self.lib.series_next_up("tt0903747")["id"], "tt0903747:1:2")

    def test_barely_started_episode_does_not_move_next_up(self):
        self.watch("tt0903747:1:1")
        self.session.history.record(self.episodes["tt0903747:1:2"], 5, 2940)
        self.assertEqual([e["id"] for e in self.lib.next_up()], ["tt0903747:1:2"])

    def test_next_up_hides_show_with_episode_in_progress(self):
        self.watch("tt0903747:1:1")
        self.session.history.record(self.episodes["tt0903747:1:2"], 600, 2940)
        self.assertEqual(self.lib.next_up(), [])
        self.assertEqual(self.lib.series_next_up("tt0903747")["id"], "tt0903747:1:2")
        self.assertEqual([i["id"] for i in self.lib.resume()], ["tt0903747:1:2"])

    def test_series_next_up_starts_at_pilot(self):
        self.assertEqual(self.lib.series_next_up("tt0903747")["id"], "tt0903747:1:1")

    def test_next_episode_skips_specials_and_unaired(self):
        self.assertEqual(self.lib.next_episode(self.episodes["tt0903747:1:2"])["id"], "tt0903747:2:1")
        self.assertIsNone(self.lib.next_episode(self.episodes["tt0903747:2:1"]))
        self.assertIsNone(self.lib.next_episode({"id": "tt1", "type": "Movie"}))

    def test_mark_series_watched_marks_aired_episodes(self):
        self.lib.set_watched({"id": "tt0903747", "type": "Series", "stremioType": "series"}, True)
        history = self.session.history
        self.assertTrue(history.watched("tt0903747:1:1"))
        self.assertFalse(history.watched("tt0903747:2:2"))

    def test_catalog_paging_and_dedupe(self):
        items, total = self.lib.catalog("movie", "top", None, 0, 50)
        self.assertEqual(len(items), 50)
        self.assertEqual(total, 51)
        items, total = self.lib.catalog("movie", "top", None, 100, 50)
        self.assertEqual(len(items), 20)
        items, total = self.lib.catalog("movie", "top", None, 120, 50)
        self.assertEqual((items, total), ([], 120))
        items, _ = self.lib.catalog("movie", "top", None, 0, 120)
        self.assertEqual(len(items), 120)

    def test_home_catalogs_skip_required_extras(self):
        rows = self.lib.home_catalogs()
        self.assertEqual([r["title"] for r in rows], ["Popular Movies", "Popular Shows"])

    def test_search_uses_searchable_catalogs_of_type(self):
        self.assertEqual([i["id"] for i in self.lib.search("dune", "Movie")], ["movie-dune"])
        self.assertEqual([i["id"] for i in self.lib.search("dune", "Series")], ["series-dune"])
        self.assertEqual(self.lib.known("series-dune")["type"], "Series")


if __name__ == "__main__":
    unittest.main()
