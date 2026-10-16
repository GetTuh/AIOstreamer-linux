import unittest

from jellyfin_tv.tests.helpers import FakeSettings, app
from jellyfin_tv.api.library import Library
from jellyfin_tv.api.trailers import FORMAT, MAX_SECONDS, TTL, TrailerResolver, search_url, streams_from
from jellyfin_tv.models.trailers import TrailerPreview

YT = "https://www.youtube.com/watch?v=abc"
DASH = {
    "requested_formats": [
        {"url": "https://v/video", "vcodec": "avc1.4D401F", "acodec": "none"},
        {"url": "https://v/audio", "vcodec": "none", "acodec": "mp4a.40.2"},
    ]
}


class ManualRunner:
    def __init__(self):
        self.calls = []

    def run(self, fn, on_done=None, on_error=None):
        self.calls.append((fn, on_done, on_error))

    def flush(self):
        while self.calls:
            fn, on_done, on_error = self.calls.pop(0)
            try:
                result = fn()
            except Exception as exc:
                on_error(exc)
                continue
            on_done(result)


class FakeSession:
    server = "http://srv"
    token = "TOKEN"

    def url(self, path, **params):
        return "%s/%s?%s" % (self.server, path, "&".join("%s=%s" % kv for kv in params.items()))


class FakeLibrary:
    def __init__(self, trailers=None):
        self.session = FakeSession()
        self.data = trailers or {}
        self.calls = []

    def trailers(self, item_id):
        self.calls.append(item_id)
        local, remote = self.data.get(item_id, ([], []))
        return {"local": local, "remote": remote, "title": "", "year": None}


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class StreamsTest(unittest.TestCase):
    def test_separate_video_and_audio(self):
        self.assertEqual(streams_from(DASH), {"video": "https://v/video", "audio": "https://v/audio", "muxed": False})

    def test_single_muxed_format(self):
        info = {"url": "https://v/both", "vcodec": "avc1", "acodec": "mp4a"}
        self.assertEqual(streams_from(info), {"video": "https://v/both", "audio": "", "muxed": True})

    def test_search_takes_first_entry_short_enough_to_be_a_trailer(self):
        movie = {"url": "https://v/movie", "vcodec": "avc1", "acodec": "mp4a", "duration": MAX_SECONDS * 10}
        trailer = dict(DASH, duration=150)
        self.assertEqual(streams_from({"entries": [movie, trailer]})["video"], "https://v/video")
        self.assertIsNone(streams_from({"entries": [movie]}))
        self.assertIsNone(streams_from({"entries": []}))

    def test_search_url(self):
        self.assertEqual(search_url("Avatar", 2009), "ytsearch1:Avatar 2009 official trailer")
        self.assertEqual(search_url("Avatar"), "ytsearch1:Avatar official trailer")
        self.assertEqual(search_url(""), "")

    def test_audio_only_is_not_a_trailer(self):
        self.assertIsNone(streams_from({"requested_formats": [{"url": "a", "vcodec": "none", "acodec": "opus"}]}))
        self.assertIsNone(streams_from({}))


class ResolverTest(unittest.TestCase):
    def test_format_merges_any_video_choice_with_audio(self):
        try:
            from yt_dlp import YoutubeDL
        except ImportError:
            self.skipTest("yt-dlp missing")
        formats = [
            {"format_id": "v", "url": "v", "ext": "mp4", "protocol": "https", "vcodec": "avc1", "acodec": "none", "height": 720},
            {"format_id": "a", "url": "a", "ext": "m4a", "protocol": "https", "vcodec": "none", "acodec": "mp4a"},
        ]
        with YoutubeDL({"quiet": True, "format": FORMAT}) as ydl:
            chosen = list(ydl.build_format_selector(FORMAT)({"formats": formats, "has_merged_format": False, "incomplete_formats": False}))
        self.assertEqual(chosen[0]["format_id"], "v+a")

    def test_caches_until_urls_expire(self):
        calls = []
        clock = Clock()
        resolver = TrailerResolver(lambda url: calls.append(url) or DASH, clock)
        for _ in range(3):
            self.assertEqual(resolver.resolve(YT)["video"], "https://v/video")
        self.assertEqual(calls, [YT])
        clock.now = TTL + 1
        resolver.resolve(YT)
        self.assertEqual(calls, [YT, YT])


class LibraryTrailersTest(unittest.TestCase):
    def test_reads_local_and_remote(self):
        lib = Library(None)
        responses = {
            "Items/m": {"LocalTrailerCount": 1, "RemoteTrailers": [{"Url": YT}, {"Name": "no url"}]},
            "Items/m/LocalTrailers": [{"Id": "t1"}],
        }
        lib._get = lambda path, params=None: responses[path]
        self.assertEqual(lib.trailers("m"), {"local": ["t1"], "remote": [YT], "title": "", "year": None})

    def test_skips_local_lookup_without_count(self):
        lib = Library(None)
        seen = []
        lib._get = lambda path, params=None: seen.append(path) or {"RemoteTrailers": [], "Name": "Avatar", "ProductionYear": 2009}
        self.assertEqual(lib.trailers("m"), {"local": [], "remote": [], "title": "Avatar", "year": 2009})
        self.assertEqual(seen, ["Items/m"])


class TrailerPreviewTest(unittest.TestCase):
    def setUp(self):
        app()
        self.runner = ManualRunner()
        self.settings = FakeSettings()
        self.resolved = []
        resolver = TrailerResolver(lambda url: self.resolved.append(url) or DASH)
        self.library = FakeLibrary({"movie": ([], [YT]), "show": ([], ["bad", YT]), "local": (["t1"], [YT])})
        self.preview = TrailerPreview(self.runner, self.library, self.settings, resolver=resolver)
        self.emitted = []
        self.preview.changed.connect(lambda: self.emitted.append(self.preview.videoUrl))

    def elapse(self):
        self.preview._timer.stop()
        self.preview._lookup()
        self.runner.flush()

    def test_plays_after_delay_muted(self):
        self.preview.request("movie", "Movie")
        self.assertTrue(self.preview._timer.isActive())
        self.assertEqual(self.preview.videoUrl, "")
        self.elapse()
        self.assertEqual(self.preview.videoUrl, "https://v/video")
        self.assertEqual(self.preview.audioUrl, "https://v/audio")
        self.assertFalse(self.preview.muxed)
        self.assertTrue(self.preview.muted)
        self.assertEqual(self.preview.itemId, "movie")

    def test_sound_setting_unmutes_background(self):
        self.settings.set("trailer_previews", "sound")
        self.preview.request("movie", "Movie")
        self.elapse()
        self.assertFalse(self.preview.muted)

    def test_local_trailer_wins_and_carries_its_own_audio(self):
        self.settings.set("trailer_previews", "sound")
        self.preview.request("local", "Movie")
        self.elapse()
        self.assertIn("Videos/t1/stream", self.preview.videoUrl)
        self.assertIn("ApiKey=TOKEN", self.preview.videoUrl)
        self.assertTrue(self.preview.muxed)
        self.assertEqual(self.preview.audioUrl, "")
        self.assertEqual(self.resolved, [])

    def test_falls_through_failing_remote_urls(self):
        def extract(url):
            self.resolved.append(url)
            if url == "bad":
                raise RuntimeError("unavailable")
            return DASH
        self.preview._resolver = TrailerResolver(extract)
        self.preview.request("show", "Series")
        self.elapse()
        self.assertEqual(self.resolved, ["bad", YT])
        self.assertEqual(self.preview.videoUrl, "https://v/video")

    def test_searches_youtube_when_server_lists_no_trailer(self):
        self.library.trailers = lambda item_id: {"local": [], "remote": [], "title": "Avatar", "year": 2009}
        self.preview.request("avatar", "Movie")
        self.elapse()
        self.assertEqual(self.resolved, ["ytsearch1:Avatar 2009 official trailer"])
        self.assertEqual(self.preview.videoUrl, "https://v/video")

    def test_search_is_last_resort_after_listed_trailers(self):
        self.library.trailers = lambda item_id: {"local": [], "remote": [YT], "title": "Avatar", "year": 2009}
        self.preview.request("avatar", "Movie")
        self.elapse()
        self.assertEqual(self.resolved, [YT])

    def test_episodes_and_off_setting_never_look_up(self):
        self.preview.request("ep", "Episode")
        self.assertFalse(self.preview._timer.isActive())
        self.settings.set("trailer_previews", "off")
        self.preview.request("movie", "Movie")
        self.assertFalse(self.preview._timer.isActive())
        self.assertEqual(self.library.calls, [])

    def test_result_for_a_page_already_left_is_dropped(self):
        self.preview.request("movie", "Movie")
        self.preview._timer.stop()
        self.preview._lookup()
        self.preview.release("movie")
        self.preview.request("show", "Series")
        self.runner.flush()
        self.assertEqual(self.preview.videoUrl, "")
        self.assertEqual(set(self.emitted), {""})
        self.assertEqual(self.preview.status, "loading")

    def test_releasing_another_item_keeps_the_current_one(self):
        self.preview.request("movie", "Movie")
        self.elapse()
        self.preview.release("show")
        self.assertEqual(self.preview.videoUrl, "https://v/video")
        self.preview.release("movie")
        self.assertEqual(self.preview.videoUrl, "")

    def test_moving_back_and_forth_looks_up_each_item_once(self):
        for _ in range(3):
            for item, kind in (("movie", "Movie"), ("show", "Series")):
                self.preview.request(item, kind)
                self.elapse()
                self.assertEqual(self.preview.itemId, item)
        self.assertEqual(self.library.calls, ["movie", "show"])
        self.assertEqual(self.resolved, [YT, "bad"])

    def test_items_without_trailers_are_remembered(self):
        self.preview._resolver = TrailerResolver(lambda url: self.resolved.append(url) or {"entries": []})
        for _ in range(3):
            self.preview.request("none", "Movie")
            self.elapse()
            self.assertEqual(self.preview.videoUrl, "")
            self.preview.release("none")
        self.assertEqual(self.library.calls, ["none"])

    def test_failed_does_not_retry_on_same_item(self):
        self.preview.request("movie", "Movie")
        self.elapse()
        self.preview.failed()
        self.preview.request("movie", "Movie")
        self.assertFalse(self.preview._timer.isActive())
        self.assertEqual(self.preview.videoUrl, "")

    def test_status_follows_lookup(self):
        self.preview.request("movie", "Movie")
        self.assertEqual(self.preview.status, "loading")
        self.elapse()
        self.assertEqual(self.preview.status, "ready")
        self.preview.request("none", "Movie")
        self.elapse()
        self.assertEqual(self.preview.status, "none")
        self.assertEqual(self.preview.currentId, "none")

    def test_lookup_error_reports_none(self):
        def broken(item_id):
            raise RuntimeError("500")
        self.library.trailers = broken
        self.preview.request("movie", "Movie")
        self.elapse()
        self.assertEqual(self.preview.status, "none")

    def test_watch_skips_delay(self):
        self.preview.request("movie", "Movie")
        self.preview.watch("movie", "Movie")
        self.assertFalse(self.preview._timer.isActive())
        self.runner.flush()
        self.assertEqual(self.preview.status, "ready")

    def test_watch_works_with_background_previews_off(self):
        self.settings.set("trailer_previews", "off")
        self.preview.request("movie", "Movie")
        self.assertEqual(self.preview.status, "")
        self.assertEqual(self.library.calls, [])
        self.preview.watch("movie", "Movie")
        self.runner.flush()
        self.assertEqual(self.preview.videoUrl, "https://v/video")

    def test_turning_off_keeps_an_explicitly_opened_trailer(self):
        self.preview.watch("movie", "Movie")
        self.runner.flush()
        self.settings.set("trailer_previews", "off")
        self.assertEqual(self.preview.videoUrl, "https://v/video")

    def test_watch_twice_looks_up_once(self):
        for _ in range(3):
            self.preview.watch("movie", "Movie")
        self.runner.flush()
        self.assertEqual(self.library.calls, ["movie"])

    def test_cached_only_wraps_third_party_urls(self):
        class Cache:
            def local_url(self, url):
                return "http://127.0.0.1:1/x"
        self.preview._cache = Cache()
        self.assertEqual(self.preview.cached("https://v/video"), "http://127.0.0.1:1/x")
        self.assertEqual(self.preview.cached("http://srv/Videos/t1/stream?ApiKey=TOKEN"), "http://srv/Videos/t1/stream?ApiKey=TOKEN")
        self.assertEqual(self.preview.cached(""), "")

    def test_turning_off_stops_playing_trailer(self):
        self.preview.request("movie", "Movie")
        self.elapse()
        self.settings.set("trailer_previews", "off")
        self.assertEqual(self.preview.videoUrl, "")


if __name__ == "__main__":
    unittest.main()
