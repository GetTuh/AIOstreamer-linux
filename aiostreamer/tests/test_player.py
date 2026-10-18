import unittest
from pathlib import Path

from aiostreamer.tests.helpers import FakeSettings, SyncRunner, app
from aiostreamer.player.mpv_runner import DEFAULT_OPTIONS, build_options, parse_overrides
import tempfile

from aiostreamer.api.history import WatchState
from aiostreamer.models.services import services
from aiostreamer.player.playback import PlaybackController, media_title, more_subtitles, pick_subtitles, proxy_headers, up_next_at, wants_external


class MpvOptionsTest(unittest.TestCase):
    def test_defaults(self):
        options = build_options(FakeSettings(), "Title", 0)
        for key, value in DEFAULT_OPTIONS.items():
            self.assertEqual(options[key], value)
        self.assertEqual(options["vo"], "gpu-next")
        self.assertEqual(options["gpu-api"], "vulkan")
        self.assertEqual(options["hwdec"], "auto-safe")
        self.assertEqual(options["target-colorspace-hint"], "yes")
        self.assertEqual(options["fullscreen"], "yes")
        self.assertEqual(options["slang"], "eng,en")
        self.assertEqual(options["subs-fallback"], "no")
        self.assertNotIn("start", options)
        self.assertNotIn("include", options)

    def test_start_and_overrides_win(self):
        settings = FakeSettings(mpv_extra="vo=null\n# comment\n--fullscreen=no\nmute")
        options = build_options(settings, "T", 1811.5)
        self.assertEqual(options["start"], "1811.500")
        self.assertEqual(options["vo"], "null")
        self.assertEqual(options["fullscreen"], "no")
        self.assertEqual(options["mute"], "yes")

    def test_user_conf_included_after_defaults(self):
        settings = FakeSettings()
        settings.mpv_conf_path.write_text("vo=x11\n")
        try:
            keys = list(build_options(settings, "T").keys())
            self.assertGreater(keys.index("include"), keys.index("vo"))
        finally:
            settings.mpv_conf_path.unlink()

    def test_subtitles_off(self):
        self.assertEqual(build_options(FakeSettings(subtitle_mode="off"), "T")["sid"], "no")

    def test_uosc_loaded_and_themed(self):
        from aiostreamer.player import mpv_runner
        options = build_options(FakeSettings(), "T", theme={"accent": "#ff8800"})
        scripts = options["scripts"].split(":")
        self.assertTrue(scripts[0].endswith("remote.lua"))
        self.assertEqual(options["osc"], "no")
        for path in scripts:
            self.assertTrue(Path(path).exists(), path)
        self.assertTrue((Path(options["osd-fonts-dir"]) / "uosc_icons.otf").exists())
        self.assertIn("uosc-color=[foreground=ff8800,", options["script-opts"])
        self.assertIn("uosc-controls=[", options["script-opts"])
        self.assertEqual(mpv_runner._hex("#3daee9"), "3daee9")

    def test_native_player_ui(self):
        options = build_options(FakeSettings(player_ui="native"), "T")
        self.assertEqual(options["osc"], "yes")
        self.assertNotIn("uosc", options["scripts"])
        self.assertNotIn("osd-bar", options)
        self.assertNotIn("osd-fonts-dir", options)
        self.assertTrue(options["script-opts"].startswith("aios-overlay=no,"))
        self.assertTrue(options["scripts"].split(":")[0].endswith("remote.lua"))

    def test_user_uosc_wins(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as home:
            (Path(home) / "scripts" / "uosc").mkdir(parents=True)
            os.environ["MPV_HOME"] = home
            try:
                options = build_options(FakeSettings(), "T")
            finally:
                del os.environ["MPV_HOME"]
        self.assertNotIn("uosc", options["scripts"].replace("aios", ""))
        self.assertNotIn("osd-fonts-dir", options)

    def test_audio_output_modes(self):
        self.assertNotIn("audio-spdif", build_options(FakeSettings(), "T"))
        self.assertEqual(build_options(FakeSettings(audio_output="stereo"), "T")["audio-channels"], "stereo")
        options = build_options(FakeSettings(audio_output="passthrough"), "T")
        self.assertEqual(options["audio-spdif"], "ac3,eac3,dts,dts-hd,truehd")
        self.assertEqual(build_options(FakeSettings(audio_output="passthrough", mpv_extra="audio-spdif=ac3"), "T")["audio-spdif"], "ac3")

    def test_parse_overrides(self):
        self.assertEqual(parse_overrides("a=1\n\n b = 2 \nc"), {"a": "1", "b": "2", "c": "yes"})


def stream(item_id, res, group):
    name = "Show.S01E0%s.%s.WEB-DL.mkv" % (item_id[-1], res)
    return {"url": "https://cdn/%s/%s" % (item_id, res), "name": res,
            "behaviorHints": {"filename": name, "bingeGroup": group, "videoSize": 2_000_000_000},
            "streamData": {"id": "%s-%s" % (res, item_id), "type": "debrid", "parsedFile": {"resolution": res}}}


class FakePlayer:
    def __init__(self):
        self.calls = []
        self.tracks = []
        self.subs = []

    def show_up_next(self, series, title, seconds, autoplay, accent=""):
        self.calls.append(("show", title, seconds, autoplay))

    def hide_up_next(self):
        self.calls.append(("hide",))

    def set_versions(self, versions):
        self.versions = versions

    def command(self, *args):
        self.calls.append(("command",) + args)

    def get(self, name, default=None):
        return self.tracks if name == "track-list" else default

    def add_subtitle(self, url, title="", lang=""):
        self.subs.append((url, lang))

    def load_next(self, url, title, start, alang=None):
        self.calls.append(("load", url, title, start))
        self.alang = alang

    def quit(self):
        self.calls.append(("quit",))

    def kinds(self):
        return [c[0] for c in self.calls if c[0] != "command"]


class FakeLibrary:
    EPISODES = ["e1", "e2", "e3"]

    def __init__(self):
        self.subtitle_calls = 0

    def item(self, item_id):
        number = self.EPISODES.index(item_id) + 1
        return {"id": item_id, "type": "Episode", "stremioType": "series", "seriesId": "show", "seriesName": "Show",
                "season": 1, "episode": number, "name": "Ep %d" % number, "runtime": 1000}

    def streams(self, item, fresh=False):
        return [stream(item["id"], "2160p", "aio|2160p|A"), stream(item["id"], "1080p", "aio|1080p|B")]

    def next_episode(self, item):
        index = self.EPISODES.index(item["id"]) + 1
        return self.item(self.EPISODES[index]) if index < len(self.EPISODES) else None

    def subtitles(self, item, stream=None, fresh=False):
        self.subtitle_calls += 1
        self.fresh_calls = getattr(self, "fresh_calls", 0) + bool(fresh)
        return [{"url": "https://subs/%d" % i, "lang": lang} for i, lang in enumerate(["eng", "eng", "eng", "ger", "pob"])]


class FakeSession:
    def __init__(self):
        self.history = WatchState(tempfile.mkdtemp(prefix="aios-hist-") + "/state.json")


class HelpersTest(unittest.TestCase):
    def test_media_title(self):
        self.assertEqual(media_title({"type": "Episode", "seriesName": "BB", "season": 2, "episode": 1, "name": "737"}), "BB - S02E01 - 737")
        self.assertEqual(media_title({"type": "Movie", "name": "Top Gun", "year": "1986"}), "Top Gun (1986)")
        self.assertEqual(media_title({"type": "Movie", "name": "Dune"}), "Dune")

    def test_proxy_headers(self):
        self.assertEqual(proxy_headers({}), "")
        hinted = {"behaviorHints": {"proxyHeaders": {"request": {"Referer": "https://a", "X-A": "b,c"}}}}
        self.assertEqual(proxy_headers(hinted), "Referer: https://a,X-A: b\\,c")

    def test_pick_subtitles_caps_per_language(self):
        subs = [{"url": "u%d" % i, "lang": lang} for i, lang in enumerate(["eng", "en", "eng", "ger", "fre", "eng"])]
        picked = pick_subtitles(subs, ["eng", "ger"])
        self.assertEqual([s["url"] for s in picked], ["u0", "u1", "u3"])

    def test_more_subtitles_prefers_languages_and_skips_known(self):
        subs = [{"url": "u%d" % i, "lang": lang} for i, lang in enumerate(["ger", "eng", "fre", "en", "eng", "ger"])]
        subs.append({"url": "u1", "lang": "eng"})
        picked = more_subtitles(subs, ["eng", "ger"], {"u4"})
        self.assertEqual([s["url"] for s in picked], ["u1", "u3", "u0", "u5", "u2"])
        self.assertEqual(len(more_subtitles(subs, ["eng"], set(), limit=2)), 2)

    def test_wants_external(self):
        internal = [{"type": "sub", "lang": "eng", "id": 1}]
        self.assertFalse(wants_external([], ["eng"], "off", None))
        self.assertFalse(wants_external([], [], "auto", None))
        self.assertFalse(wants_external([], ["eng"], "auto", "eng"))
        self.assertTrue(wants_external([], ["eng"], "always", "eng"))
        self.assertTrue(wants_external([], ["eng"], "auto", "jpn"))
        self.assertFalse(wants_external(internal, ["eng"], "auto", "jpn"))


class UpNextTest(unittest.TestCase):
    def setUp(self):
        app()
        self.settings = FakeSettings(autoplay_next=True, upnext_seconds=10)
        services.settings = self.settings
        self.session = FakeSession()
        self.library = FakeLibrary()
        self.controller = PlaybackController(SyncRunner(), self.session, self.library, self.settings)
        self.advanced = []
        self.controller.playbackAdvanced.connect(self.advanced.append)
        self.player = FakePlayer()
        self.state = self.start("e1")

    def tearDown(self):
        services.settings = None

    def start(self, item_id):
        state = self.controller._resolve(item_id, 0, None)
        state["player"] = self.player
        state["playing"] = True
        self.controller._active = state
        self.controller._launched(state)
        return state

    def test_first_version_in_aiostreams_order_by_default(self):
        self.assertEqual(self.state["url"], "https://cdn/e1/2160p")

    def test_default_pick_is_not_sticky(self):
        self.settings.values["max_resolution"] = 1080
        self.assertEqual(self.controller._resolve("e2", 0, None)["url"], "https://cdn/e2/1080p")

    def test_resolution_cap_skips_to_first_fitting(self):
        self.settings.values["max_resolution"] = 1080
        state = self.controller._resolve("e3", 0, None)
        self.assertEqual(state["url"], "https://cdn/e3/1080p")

    def test_switch_version_keeps_position_and_follows_into_next_episode(self):
        self.controller._on_position(612.5)
        self.controller._on_file_loaded()
        self.assertEqual([v["id"] for v in self.player.versions], ["2160p-e1", "1080p-e1"])
        self.assertTrue(self.player.versions[0]["active"])
        for _ in range(3):
            self.controller._on_message(["aios-version", "1080p-e1"])
        loads = [c for c in self.player.calls if c[0] == "load"]
        self.assertEqual(len(loads), 1)
        self.assertEqual(loads[0][1], "https://cdn/e1/1080p")
        self.assertEqual(loads[0][3], 612.5)
        self.assertEqual(self.controller._active["item_id"], "e1")
        self.controller._on_end_file("stop")
        self.assertNotIn("quit", self.player.kinds())
        self.controller._on_file_loaded()
        self.assertTrue(self.player.versions[1]["active"])
        self.controller._active["playing"] = True
        self.controller._on_position(980)
        self.controller._on_end_file("eof")
        self.assertEqual(self.player.calls[-1][1], "https://cdn/e2/1080p")

    def test_progress_recorded_and_finished_marks_watched(self):
        history = self.session.history
        self.controller._on_position(300)
        self.controller._tick()
        self.assertEqual(history.progress("e1")[0], 300)
        self.controller._on_paused(True)
        self.controller._on_position(420)
        self.controller._on_paused(False)
        self.controller._on_paused(True)
        self.assertEqual(history.progress("e1")[0], 420)
        self.controller._on_position(980)
        self.controller._on_end_file("eof")
        self.assertTrue(history.watched("e1"))
        self.assertEqual(history.progress("e1"), (0.0, 0.0))
        self.assertEqual(self.controller._active["item_id"], "e2")

    def test_addon_subtitles_only_when_no_internal_match(self):
        self.player.tracks = [{"type": "audio", "id": 1, "lang": "jpn", "selected": True}]
        self.controller._on_file_loaded()
        self.assertEqual(self.player.subs, [("https://subs/0", "eng"), ("https://subs/1", "eng")])
        self.player.subs = []
        self.player.tracks.append({"type": "sub", "id": 1, "lang": "eng"})
        self.controller._on_file_loaded()
        self.assertEqual(self.player.subs, [])
        self.assertEqual(self.library.subtitle_calls, 1)

    def test_get_more_subtitles_adds_unseen_fresh(self):
        self.player.tracks = [{"type": "audio", "id": 1, "lang": "jpn", "selected": True}]
        self.controller._on_file_loaded()
        self.player.subs = []
        self.controller._on_message(["aios-more-subs"])
        self.assertEqual(sorted(u for u, _ in self.player.subs), ["https://subs/2", "https://subs/3", "https://subs/4"])
        self.assertEqual(self.library.fresh_calls, 1)
        texts = [c for c in self.player.calls if c[:2] == ("command", "show-text")]
        self.assertIn("Added 3 subtitles", texts[-1][2])
        self.player.subs = []
        self.controller._on_message(["aios-more-subs"])
        self.assertEqual(self.player.subs, [])
        self.assertIn("No more subtitles", [c for c in self.player.calls if c[:2] == ("command", "show-text")][-1][2])

    def test_play_now_replaces_current_item_in_same_player(self):
        self.controller.play_now("e3", 120.0, "")
        loads = [c for c in self.player.calls if c[0] == "load"]
        self.assertEqual(len(loads), 1)
        self.assertEqual(loads[0][3], 120.0)
        self.assertEqual(self.controller._active["item_id"], "e3")
        self.assertEqual(self.advanced, ["e1"])

    def test_skip_script_options(self):
        options = build_options(FakeSettings(skip_segments="auto"), "T", theme={"accent": "#ff8800"})
        self.assertIn("skip.lua", options["scripts"])
        self.assertIn("aios-skip=auto,aios-accent=ff8800", options["script-opts"])
        self.assertIn("aios-skip=ask", build_options(FakeSettings(player_ui="native"), "T")["script-opts"])

    def test_trigger_point(self):
        self.assertEqual(up_next_at(1000, None, 10), 970)
        self.assertEqual(up_next_at(1000, None, 30), 965)
        self.assertEqual(up_next_at(1000, 900, 10), 900)
        self.assertEqual(up_next_at(1000, 995, 10), 970)
        self.assertIsNone(up_next_at(0, None, 10))

    def test_shows_once_near_end_and_plays_now(self):
        self.controller._on_position(960)
        self.assertEqual(self.player.calls, [])
        self.controller._on_position(971)
        self.controller._on_position(975)
        self.assertEqual(self.player.calls, [("show", "S1:E2 · Ep 2", 10, True)])
        self.controller._on_message(["aios-upnext-play"])
        self.assertEqual(self.player.kinds(), ["show", "load"])
        self.assertEqual(self.player.calls[-1][1], "https://cdn/e2/2160p")
        self.assertEqual(self.controller._active["item_id"], "e2")
        self.assertEqual(self.advanced, ["e1"])
        self.controller._on_end_file("stop")
        self.assertNotIn("quit", self.player.kinds())
        self.controller._on_file_loaded()
        self.controller._on_end_file("stop")
        self.assertEqual(self.player.kinds()[-1], "quit")

    def test_next_episode_resumes_from_history(self):
        self.session.history.record(self.library.item("e2"), 333, 1000)
        self.controller._on_position(980)
        self.controller._on_end_file("eof")
        self.assertEqual(self.player.calls[-1][3], 333)

    def test_dismissed_then_eof_returns_to_app(self):
        self.controller._on_position(980)
        self.controller._on_message(["aios-upnext-dismiss"])
        self.controller._on_position(990)
        self.controller._on_end_file("eof")
        self.assertEqual(self.player.kinds(), ["show", "quit"])

    def test_eof_autoplays_without_interaction(self):
        self.controller._on_position(980)
        self.controller._on_end_file("eof")
        self.assertEqual(self.player.kinds(), ["show", "load"])
        self.assertFalse(self.controller._switching)

    def test_eof_without_autoplay_returns_to_app(self):
        self.settings.values["autoplay_next"] = False
        self.controller._on_position(980)
        self.controller._on_end_file("eof")
        self.assertEqual(self.player.calls[0], ("show", "S1:E2 · Ep 2", 10, False))
        self.assertEqual(self.player.kinds(), ["show", "quit"])

    def test_seeking_back_hides_and_rearms(self):
        for _ in range(3):
            self.controller._on_position(975)
            self.controller._on_position(500)
        self.assertEqual(self.player.kinds(), ["show", "hide"] * 3)
        self.assertEqual(self.controller._active["item_id"], "e1")

    def test_chain_continues_and_last_episode_has_no_up_next(self):
        for expected in ("e2", "e3"):
            self.controller._on_position(980)
            self.controller._on_end_file("eof")
            self.controller._on_file_loaded()
            active = self.controller._active
            self.assertEqual(active["item_id"], expected)
            active["playing"] = True
        self.controller._on_position(990)
        self.controller._on_end_file("eof")
        self.assertEqual(self.player.kinds(), ["show", "load", "show", "load", "quit"])
        self.assertEqual(self.advanced, ["e1", "e2"])
        for item_id in ("e1", "e2"):
            self.assertTrue(self.session.history.watched(item_id))


if __name__ == "__main__":
    unittest.main()
