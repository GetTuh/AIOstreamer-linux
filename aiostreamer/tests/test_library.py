import tempfile
import unittest

from aiostreamer.api import meta as m
from aiostreamer.api.history import WatchState
from aiostreamer.api.aio import AioError
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
        self.assertEqual(m.catalog_title({"type": "series", "name": "TVDB Trending"}), "TVDB Trending Shows")
        self.assertEqual(m.catalog_title({"type": "anime", "name": "MAL Top Anime"}), "MAL Top Anime")
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

    def test_recent_shows_series_once_with_movies_newest_first(self):
        clock = [0]
        state = WatchState(tempfile.mkdtemp(prefix="aios-hist-") + "/s.json", clock=lambda: clock[0])
        steps = [({"id": "s:1:1", "type": "Episode", "seriesId": "s", "seriesName": "Show"}, 2900),
                 ({"id": "tt9", "type": "Movie", "name": "Film"}, 2900),
                 ({"id": "tt8", "type": "Movie", "name": "Half"}, 600),
                 ({"id": "s:1:2", "type": "Episode", "seriesId": "s", "seriesName": "Show"}, 600)]
        for i, (item, position) in enumerate(steps):
            clock[0] = i
            state.record(item, position, 3000)
        clock[0] = 9
        state.record({"id": "tt7", "type": "Movie"}, 10, 3000)
        recent = state.recent()
        self.assertEqual([(i["id"], i["type"]) for i in recent], [("s", "Series"), ("tt8", "Movie"), ("tt9", "Movie")])
        self.assertEqual(recent[0]["name"], "Show")

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
    def __init__(self, manifest=None):
        self.meta_calls = 0
        self.pages = {}
        self.cache = None
        self._manifest = manifest

    def meta(self, kind, item_id, fresh=False):
        self.meta_calls += 1
        if item_id != SHOW["id"]:
            return {"id": item_id, "type": kind, "name": "Movie " + item_id}
        return SHOW

    def peek_meta(self, kind, item_id):
        return None

    def manifest(self):
        if self._manifest is not None:
            return self._manifest
        return {"resources": [{"name": "meta", "types": ["movie", "series"], "idPrefixes": ["tt"]}], "catalogs": [
            {"type": "movie", "id": "top", "name": "Popular", "extra": [{"name": "search"}, {"name": "skip"}]},
            {"type": "series", "id": "top", "name": "Popular", "extra": [{"name": "search"}]},
            {"type": "series", "id": "cal", "name": "Calendar", "extra": [{"name": "calendarVideosIds", "isRequired": True}]},
        ]}

    def peek_manifest(self):
        return self.manifest()

    def peek_catalog(self, kind, catalog_id, extra=None):
        return None

    def catalog(self, kind, catalog_id, extra=None):
        extra = extra or {}
        if "search" in extra:
            return [{"id": "%s-%s" % (kind, extra["search"]), "type": kind, "name": extra["search"]}]
        skip = int(extra.get("skip") or 0)
        return [{"id": "tt%d" % i, "type": kind, "name": str(i)} for i in range(skip, min(skip + 50, 120))]


class FakeSession:
    def __init__(self, client=None):
        self.client = client or FakeClient()
        self.history = history()


LIBRARY_ONLY = {
    "types": ["movie", "series", "library"],
    "resources": [
        {"name": "stream", "types": ["movie", "series", "library"], "idPrefixes": ["tt", "aiostreams::library"]},
        {"name": "catalog", "types": ["library"]},
        {"name": "meta", "types": ["library"], "idPrefixes": ["aiostreams::library"]},
    ],
    "catalogs": [{"type": "library", "id": "lib", "name": "Library", "extra": [{"name": "search"}, {"name": "skip"}]}],
}


AIO_TMDB = {
    "types": ["movie", "series", "library"],
    "resources": [
        {"name": "catalog", "types": ["library", "movie", "series"]},
        {"name": "meta", "types": ["library", "movie", "series"], "idPrefixes": ["aiostreams::library", "tmdb:"]},
    ],
    "catalogs": [
        {"type": "library", "id": "ae72eb9.lib", "name": "Library", "extra": [{"name": "search"}]},
        {"type": "movie", "id": "925e3b0.tmdb.top", "name": "Populaire", "extra": [{"name": "skip"}]},
        {"type": "movie", "id": "925e3b0.tmdb.language", "name": "Langue", "extra": [{"name": "genre", "options": ["fr"]}]},
        {"type": "movie", "id": "925e3b0.tmdb.search", "name": "Search", "extra": [{"name": "search", "isRequired": True}]},
    ],
}

AIOMETADATA = {
    "types": ["movie", "series", "anime.movie", "anime.series", "anime"],
    "idPrefixes": ["tmdb:", "tt", "mal:", "kitsu:"],
    "resources": ["catalog", "meta"],
    "catalogs": [
        {"type": "movie", "id": "tmdb.top", "name": "TMDB Popular", "extra": [{"name": "skip"}]},
        {"type": "anime", "id": "mal.top_anime", "name": "MAL Top Anime", "extra": [{"name": "skip"}]},
        {"type": "movie", "id": "search.movie", "name": "Movies Search", "extra": [{"name": "search", "isRequired": True}]},
        {"type": "anime.series", "id": "search.anime_series", "name": "Anime Series Search", "extra": [{"name": "search", "isRequired": True}]},
    ],
}


class Recording(FakeClient):
    def __init__(self, manifest):
        super().__init__(manifest)
        self.searched = []

    def catalog(self, kind, catalog_id, extra=None):
        if extra and "search" in extra:
            self.searched.append(catalog_id)
            return [{"id": "%s:%s" % (catalog_id, extra["search"]), "type": "movie" if "movie" in kind else "series", "name": extra["search"]}]
        return super().catalog(kind, catalog_id, extra)


class MetadataAddonTest(unittest.TestCase):
    def setUp(self):
        self.own = Recording(AIO_TMDB)
        self.meta = Recording(AIOMETADATA)
        session = FakeSession(self.own)
        session.metadata = self.meta
        self.lib = Library(session, lambda cache: self.fail("cinemeta used"))

    def test_catalogs_lead_and_replace_duplicates(self):
        rows = [(c["type"], c["id"]) for c in self.lib.home_catalogs()]
        self.assertEqual(rows, [("movie", "tmdb.top"), ("anime", "mal.top_anime"), ("library", "ae72eb9.lib"),
                                ("movie", "925e3b0.tmdb.language")])
        self.lib.catalog("movie", "tmdb.top", None, 0, 10)
        self.assertEqual(self.lib._catalog_client("movie", "tmdb.top"), self.meta)
        self.assertEqual(m.catalog_title({"type": "anime.series", "name": "Search"}), "Search Anime Series")

    def test_meta_from_addon_when_supported(self):
        self.lib.item("tmdb:1", "Movie")
        self.lib.item("kitsu:12", "Series")
        self.assertEqual((self.meta.meta_calls, self.own.meta_calls), (2, 0))
        self.lib.item("aiostreams::library.x", "Movie")
        self.assertEqual(self.own.meta_calls, 1)

    def test_search_prefers_addon(self):
        movies = self.lib.search("dune", "Movie")
        self.assertEqual([i["id"] for i in movies], ["search.movie:dune"])
        self.assertEqual(self.own.searched, ["ae72eb9.lib"])
        shows = self.lib.search("naruto", "Series")
        self.assertEqual(shows[0]["id"], "search.anime_series:naruto")
        self.assertEqual(m.kind_for("anime.series"), "Series")
        self.assertEqual(m.kind_for("anime.movie"), "Movie")

    def test_without_addon_manifest_falls_back_to_aio(self):
        self.meta._manifest = None
        self.meta.manifest = lambda: (_ for _ in ()).throw(AioError("down"))
        self.lib.item("tmdb:1", "Movie")
        self.assertEqual(self.own.meta_calls, 1)


class FallbackTest(unittest.TestCase):
    def setUp(self):
        self.own = FakeClient(LIBRARY_ONLY)
        self.cinemeta = FakeClient()
        self.lib = Library(FakeSession(self.own), lambda cache: self.cinemeta)

    def test_cinemeta_fills_missing_catalogs(self):
        rows = [(c["type"], c["id"]) for c in self.lib.home_catalogs()]
        self.assertEqual(rows, [("movie", "top"), ("series", "top"), ("library", "lib")])
        self.assertEqual(self.lib.catalog("movie", "top", None, 0, 10)[0][0]["id"], "tt0")

    def test_cinemeta_serves_tt_meta(self):
        show, episodes = self.lib.series(SHOW["id"])
        self.assertEqual((self.own.meta_calls, self.cinemeta.meta_calls), (0, 1))
        self.assertEqual(len(episodes), 5)
        self.lib.item("aiostreams::library.x")
        self.assertEqual((self.own.meta_calls, self.cinemeta.meta_calls), (1, 1))

    def test_search_adds_typed_unmatched_library_items(self):
        own = {
            "lib-show": {"id": "lib-show", "type": "library", "name": "Naruto (2002)",
                         "videos": [{"id": "lib-show:0", "season": 1, "episode": 1}]},
            "lib-movie": {"id": "lib-movie", "type": "library", "name": "Hope (2026)",
                          "videos": [{"id": "lib-movie:0", "season": 0, "episode": 0}],
                          "behaviorHints": {"defaultVideoId": "lib-movie:0"}},
            "lib-dup": {"id": "lib-dup", "type": "library", "name": "Naruto Shippūden (2007)"},
        }
        kinds = []

        def catalog(kind, catalog_id, extra=None):
            if kind == "library":
                return [dict(own[k], videos=None) for k in own]
            return [{"id": "tt1", "type": kind, "name": "Naruto Shippuden", "releaseInfo": "2007-2017"}]

        def meta(kind, item_id, fresh=False):
            kinds.append(kind)
            return own[item_id]

        self.own.catalog = catalog
        self.cinemeta.catalog = catalog
        self.own.meta = meta
        self.assertEqual([i["id"] for i in self.lib.search("naruto", "Series")], ["tt1", "lib-show"])
        self.assertEqual([i["id"] for i in self.lib.search("naruto", "Movie")], ["tt1", "lib-movie"])
        self.assertEqual(set(kinds), {"library"})
        self.assertEqual(self.lib.known("lib-show")["type"], "Series")

    def test_no_fallback_when_covered(self):
        lib = Library(FakeSession(), lambda cache: self.fail("fallback used"))
        self.assertEqual(len(lib.home_catalogs()), 2)
        lib.series(SHOW["id"])


class CountryTest(unittest.TestCase):
    def test_country_from_meta_series_or_cinemeta_search(self):
        class Cinemeta(FakeClient):
            searches = []

            def meta(self, kind, item_id, fresh=False):
                return {"id": item_id, "type": kind, "name": "x", "country": {"tt1": "Japan", "tt2": "France"}.get(item_id, "")}

            def catalog(self, kind, catalog_id, extra=None):
                self.searches.append((kind, extra["search"]))
                return [{"id": "tt9", "releaseInfo": "1999"}, {"id": "tt1", "releaseInfo": "2007-2017"}]

        cinemeta = Cinemeta()
        lib = Library(FakeSession(FakeClient(LIBRARY_ONLY)), lambda cache: cinemeta)
        self.assertEqual(lib.country({"id": "tt5", "country": "Italy"}), "Italy")
        self.assertEqual(lib.country({"id": "tt2", "type": "Movie"}), "France")
        self.assertEqual(lib.country({"id": "tt1:1:1", "type": "Episode", "seriesId": "tt1"}), "Japan")
        episode = {"id": "aiostreams::library.n:0", "type": "Episode", "seriesId": "aiostreams::library.n",
                   "seriesName": "Naruto Shippūden (2007)", "stremioType": "library"}
        self.assertEqual(lib.country(episode), "Japan")
        self.assertEqual(cinemeta.searches, [("series", "Naruto Shippūden")])
        self.assertEqual(m.from_video(m.from_meta({"id": "tt1", "type": "series", "country": "Japan"}), {"id": "tt1:1:1"})["country"], "Japan")


class DefaultVideoTest(unittest.TestCase):
    def test_library_movie_plays_default_video(self):
        meta = {"id": "aiostreams::library.m", "type": "library", "name": "Movie",
                "videos": [{"id": "aiostreams::library.m:0", "season": 0, "episode": 0}],
                "behaviorHints": {"defaultVideoId": "aiostreams::library.m:0"}}
        item = m.from_meta(meta)
        self.assertEqual((item["type"], item["videoId"]), ("Movie", "aiostreams::library.m:0"))
        calls = []

        class Client:
            def streams(self, kind, video_id, fresh=False):
                calls.append((kind, video_id))
                return []

        Library(type("S", (), {"client": Client(), "history": None})()).streams(item)
        self.assertEqual(calls, [("library", "aiostreams::library.m:0")])
        series = dict(meta, behaviorHints={}, videos=[{"id": "s:0", "season": 1, "episode": 1}])
        self.assertEqual(m.from_meta(series)["type"], "Series")
        self.assertNotIn("videoId", m.from_meta(series))
        self.assertTrue(m.direct_type("anime"))
        self.assertFalse(m.direct_type("library"))


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
