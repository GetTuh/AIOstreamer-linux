import unittest
from pathlib import Path

from jellyfin_tv.tests.helpers import FakeSettings, SyncRunner, app
from jellyfin_tv.player.mpv_runner import DEFAULT_OPTIONS, build_options, parse_overrides
from jellyfin_tv.player.playback import PlaybackController, media_title, up_next_at
from jellyfin_tv.player.reporter import PlaybackReporter


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
        from jellyfin_tv.player import mpv_runner
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
        self.assertTrue(options["script-opts"].startswith("jftv-overlay=no,"))
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
        self.assertNotIn("uosc", options["scripts"].replace("jftv", ""))
        self.assertNotIn("osd-fonts-dir", options)

    def test_audio_output_modes(self):
        self.assertNotIn("audio-spdif", build_options(FakeSettings(), "T"))
        self.assertEqual(build_options(FakeSettings(audio_output="stereo"), "T")["audio-channels"], "stereo")
        options = build_options(FakeSettings(audio_output="passthrough"), "T")
        self.assertEqual(options["audio-spdif"], "ac3,eac3,dts,dts-hd,truehd")
        self.assertEqual(build_options(FakeSettings(audio_output="passthrough", mpv_extra="audio-spdif=ac3"), "T")["audio-spdif"], "ac3")

    def test_parse_overrides(self):
        self.assertEqual(parse_overrides("a=1\n\n b = 2 \nc"), {"a": "1", "b": "2", "c": "yes"})


class FakeSession:
    server = "http://serv.local:3020"
    token = "TOKEN"
    client = None

    def url(self, path, **params):
        from jellyfin_tv.api.session import Session
        return Session.url(self, path, **params)


class StreamUrlTest(unittest.TestCase):
    def setUp(self):
        app()
        self.controller = PlaybackController(SyncRunner(), FakeSession(), None, FakeSettings())

    def test_server_stream(self):
        url, method = self.controller._stream_url("item", {"Id": "src", "Protocol": "File", "Path": "/remux/x", "SupportsDirectStream": True}, "psid")
        self.assertTrue(url.startswith("http://serv.local:3020/Videos/item/stream?"))
        self.assertIn("MediaSourceId=src", url)
        self.assertIn("ApiKey=TOKEN", url)
        self.assertIn("static=true", url)
        self.assertEqual(method, "DirectPlay")

    def test_foreign_http_path_gets_no_token(self):
        url, _ = self.controller._stream_url("item", {"Id": "s", "Protocol": "Http", "Path": "https://cdn.example/v.mkv"}, "p")
        self.assertEqual(url, "https://cdn.example/v.mkv")

    def test_same_origin_subtitle_gets_token_once(self):
        subs = self.controller._external_subtitles({"MediaStreams": [
            {"Type": "Subtitle", "IsExternal": True, "DeliveryUrl": "/Videos/x/Subtitles/4/0/Stream.vtt", "Language": "eng"},
            {"Type": "Subtitle", "IsExternal": True, "DeliveryUrl": "/Videos/x/Subtitles/5/0/Stream.vtt?ApiKey=abc"},
            {"Type": "Subtitle", "IsExternal": True, "DeliveryUrl": "https://other.host/s.srt"},
            {"Type": "Subtitle", "IsExternal": False},
        ]})
        self.assertEqual(len(subs), 3)
        self.assertTrue(subs[0]["url"].endswith("Stream.vtt?ApiKey=TOKEN"))
        self.assertEqual(subs[0]["lang"], "eng")
        self.assertEqual(subs[1]["url"].lower().count("apikey="), 1)
        self.assertEqual(subs[2]["url"], "https://other.host/s.srt")

    def test_media_title(self):
        self.assertEqual(media_title({"Type": "Episode", "SeriesName": "BB", "ParentIndexNumber": 2, "IndexNumber": 1, "Name": "737"}), "BB - S02E01 - 737")
        self.assertEqual(media_title({"Type": "Movie", "Name": "Top Gun", "ProductionYear": 1986}), "Top Gun (1986)")


class FakeClient:
    def __init__(self):
        self.calls = []

    def post(self, path, json=None, params=None):
        self.calls.append(({"Sessions/Playing": "playing", "Sessions/Playing/Progress": "progress",
                            "Sessions/Playing/Stopped": "stop"}[path], json))


class ReporterTest(unittest.TestCase):
    def test_sequence_and_payload(self):
        client = FakeClient()
        reporter = PlaybackReporter(client, "item", "src", "psid")
        reporter.progress(5, False)
        reporter.start(10, False)
        reporter.progress(20.5, True, "Pause")
        reporter.stop(30, completed=True, runtime=3000)
        reporter.flush(5)
        kinds = [c[0] for c in client.calls]
        self.assertEqual(kinds, ["playing", "progress", "stop"])
        self.assertEqual(client.calls[0][1]["PositionTicks"], 100_000_000)
        self.assertEqual(client.calls[1][1]["EventName"], "Pause")
        self.assertTrue(client.calls[1][1]["IsPaused"])
        self.assertEqual(client.calls[2][1]["PositionTicks"], 30_000_000_000)
        self.assertEqual(client.calls[2][1]["MediaSourceId"], "src")
        self.assertEqual(client.calls[2][1]["PlaySessionId"], "psid")

    def test_no_stop_without_start(self):
        client = FakeClient()
        reporter = PlaybackReporter(client, "item", "src", "psid")
        reporter.stop(30)
        self.assertEqual(client.calls, [])


class FakePlayer:
    def __init__(self):
        self.calls = []

    def show_up_next(self, series, title, seconds, autoplay, accent=""):
        self.calls.append(("show", title, seconds, autoplay))

    def hide_up_next(self):
        self.calls.append(("hide",))

    def set_versions(self, versions):
        self.versions = versions

    def set_segments(self, segments):
        self.calls.append(("segments", segments))

    def command(self, *args):
        self.calls.append(("command",) + args)

    def load_next(self, url, title, start, alang=None):
        self.calls.append(("load", url, title, start))
        self.alang = alang

    def quit(self):
        self.calls.append(("quit",))

    def kinds(self):
        return [c[0] for c in self.calls if c[0] not in ("segments", "command")]


class FakeLibrary:
    EPISODES = ["e1", "e2", "e3"]

    def item(self, item_id):
        number = self.EPISODES.index(item_id) + 1
        return {"Id": item_id, "Type": "Episode", "SeriesId": "show", "SeriesName": "Show",
                "ParentIndexNumber": 1, "IndexNumber": number, "OriginalLanguage": "ja", "Name": "Ep %d" % number, "RunTimeTicks": 1000 * 10_000_000}

    def playback_info(self, item_id, source_id=None):
        return {"PlaySessionId": "ps-" + item_id, "MediaSources": [
            {"Id": "src-" + item_id, "Name": "2160p", "Protocol": "File", "SupportsDirectStream": True},
            {"Id": "alt-" + item_id, "Name": "1080p", "Protocol": "File", "SupportsDirectStream": True},
        ]}

    def next_episode(self, series_id, item_id):
        index = self.EPISODES.index(item_id) + 1
        return self.item(self.EPISODES[index]) if index < len(self.EPISODES) else None

    segments_by_item = {}

    def segments(self, item_id):
        return self.segments_by_item.get(item_id, [])


class ReportingSession(FakeSession):
    client = FakeClient()


class UpNextTest(unittest.TestCase):
    def setUp(self):
        app()
        self.settings = FakeSettings(autoplay_next=True, upnext_seconds=10)
        self.controller = PlaybackController(SyncRunner(), ReportingSession(), FakeLibrary(), self.settings)
        self.advanced = []
        self.controller.playbackAdvanced.connect(self.advanced.append)
        self.player = FakePlayer()
        self.state = self.start("e1")

    def start(self, item_id):
        state = self.controller._resolve(item_id, 0, None)
        state["player"] = self.player
        state["playing"] = True
        self.controller._active = state
        self.controller._launched(state)
        return state

    def test_falls_back_to_item_sources_without_playback_info(self):
        self.controller._library.playback_info = lambda item_id, source_id=None: None
        self.controller._library.sources = lambda item_id: [{"Id": "fallback", "Protocol": "File", "SupportsDirectStream": True}]
        state = self.controller._resolve("e2", 0, None)
        self.assertIn("MediaSourceId=fallback", state["url"])
        self.assertNotIn("PlaySessionId", state["url"])

    def test_switch_version_keeps_position_and_remembers(self):
        self.controller._on_position(612.5)
        self.controller._on_file_loaded()
        self.assertEqual([v["id"] for v in self.player.versions], ["src-e1", "alt-e1"])
        self.assertTrue(self.player.versions[0]["active"])
        for _ in range(3):
            self.controller._on_message(["jftv-version", "alt-e1"])
        loads = [c for c in self.player.calls if c[0] == "load"]
        self.assertEqual(len(loads), 1)
        self.assertIn("MediaSourceId=alt-e1", loads[0][1])
        self.assertEqual(loads[0][3], 612.5)
        self.assertEqual(self.controller._active["source"]["Id"], "alt-e1")
        self.assertEqual(self.controller._active["item_id"], "e1")
        self.assertEqual(self.settings.sources["e1"], "alt-e1")
        self.controller._on_end_file("stop")
        self.assertNotIn("quit", self.player.kinds())
        self.controller._on_file_loaded()
        self.assertTrue(self.player.versions[1]["active"])

    def test_stream_index_maps_to_mpv_track(self):
        self.controller._active["source"]["MediaStreams"] = [
            {"Type": "Video", "Index": 0}, {"Type": "Audio", "Index": 1}, {"Type": "Audio", "Index": 2},
            {"Type": "Subtitle", "Index": 3}, {"Type": "Subtitle", "Index": 4, "IsExternal": True}, {"Type": "Subtitle", "Index": 5},
        ]
        self.controller.set_audio_index(2)
        self.controller.set_subtitle_index(5)
        self.controller.set_subtitle_index(4)
        self.controller.set_subtitle_index(-1)
        self.controller.set_audio_index(9)
        commands = [c[1:] for c in self.player.calls if c[0] == "command"]
        self.assertEqual(commands, [("set_property", "aid", 2), ("set_property", "sid", 2), ("set_property", "sid", 3), ("set_property", "sid", "no")])

    def test_play_now_replaces_current_item_in_same_player(self):
        self.controller.play_now("e3", 120 * 10_000_000.0, "")
        loads = [c for c in self.player.calls if c[0] == "load"]
        self.assertEqual(len(loads), 1)
        self.assertEqual(loads[0][3], 120.0)
        self.assertEqual(self.controller._active["item_id"], "e3")
        self.assertEqual(self.advanced, ["e1"])

    def test_segments_sent_after_load_and_outro_drives_up_next(self):
        FakeLibrary.segments_by_item = {"e2": [{"kind": "Intro", "start": 30.0, "end": 90.0}, {"kind": "Outro", "start": 900.0, "end": 1000.0}]}
        try:
            self.controller._on_position(980)
            self.controller._on_end_file("eof")
            self.assertNotIn("segments", self.player.kinds())
            self.controller._on_file_loaded()
            sent = [c[1] for c in self.player.calls if c[0] == "segments"]
            self.assertEqual(sent[-1][0]["kind"], "Intro")
            active = self.controller._active
            self.assertEqual(active["outro"], 900.0)
            active["playing"] = True
            self.controller._on_position(899)
            self.assertEqual(self.player.kinds().count("show"), 1)
            self.controller._on_position(901)
            self.assertEqual(self.player.kinds().count("show"), 2)
        finally:
            FakeLibrary.segments_by_item = {}

    def test_skip_script_options(self):
        options = build_options(FakeSettings(skip_segments="auto"), "T", theme={"accent": "#ff8800"})
        self.assertIn("skip.lua", options["scripts"])
        self.assertIn("jftv-skip=auto,jftv-accent=ff8800", options["script-opts"])
        self.assertIn("jftv-skip=ask", build_options(FakeSettings(player_ui="native"), "T")["script-opts"])

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
        self.controller._on_message(["jftv-upnext-play"])
        self.assertEqual(self.player.kinds(), ["show", "load"])
        self.assertIn("MediaSourceId=src-e2", self.player.calls[1][1])
        self.assertEqual(self.controller._active["item_id"], "e2")
        self.assertEqual(self.advanced, ["e1"])
        self.controller._on_end_file("stop")
        self.assertNotIn("quit", self.player.kinds())
        self.controller._on_file_loaded()
        self.controller._on_end_file("stop")
        self.assertEqual(self.player.kinds()[-1], "quit")

    def test_next_episode_gets_original_audio_language(self):
        self.settings.values["audio_language"] = "original"
        self.controller._on_position(980)
        self.controller._on_end_file("eof")
        self.assertEqual(self.player.alang, "jpn")
        self.assertIn("alang", build_options(self.settings, "T", original="ja"))
        self.assertEqual(build_options(self.settings, "T", original="ja")["alang"], "jpn")
        self.assertNotIn("alang", build_options(self.settings, "T", original=""))

    def test_dismissed_then_eof_returns_to_app(self):
        self.controller._on_position(980)
        self.controller._on_message(["jftv-upnext-dismiss"])
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


if __name__ == "__main__":
    unittest.main()
