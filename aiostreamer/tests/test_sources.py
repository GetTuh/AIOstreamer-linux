import unittest

from aiostreamer.tests.helpers import FakeSettings
from aiostreamer.models import sources
from aiostreamer.models.services import services


def stream(sid, res, size=0, group="", filename="", visual=(), audio=(), channels=(), service=None, folder=0):
    data = {"id": sid, "type": "debrid", "size": size, "parsedFile": {
        "resolution": res, "encode": "HEVC", "visualTags": list(visual), "audioTags": list(audio),
        "audioChannels": list(channels), "languages": ["English"]}}
    if service:
        data["service"] = service
    if folder:
        data["folderSize"] = folder
    return {"url": "https://x/" + sid, "name": "AIO\n" + res, "behaviorHints": {"bingeGroup": group, "filename": filename or sid + ".mkv"},
            "streamData": data}


class SourcesTest(unittest.TestCase):
    def setUp(self):
        self.settings = FakeSettings()
        services.settings = self.settings

    def tearDown(self):
        services.settings = None

    def test_describe_uses_parsed_data(self):
        info = sources.describe(stream("a", "2160p", 23_400_000_000, visual=["DV", "HDR10", "IMAX"], audio=["Atmos", "TrueHD"],
                                       channels=["7.1"], service={"id": "torbox", "cached": True}))
        self.assertEqual(info["resolution"], "4K")
        self.assertEqual(info["hdr"], "DV HDR10")
        self.assertEqual(info["codec"], "HEVC")
        self.assertEqual(info["audio"], "Atmos TrueHD 7.1")
        self.assertEqual(info["size"], "23.4 GB")
        self.assertEqual(info["service"], "TB ⚡")
        self.assertEqual(info["title"], "a.mkv")
        self.assertEqual(info["name"], "AIO 2160p")
        self.assertEqual(sources.describe(stream("b", "1080p"))["hdr"], "SDR")

    def test_season_pack_size(self):
        packed = sources.describe(stream("p", "1080p", 2_950_000_000, folder=5_900_000_000))
        self.assertEqual((packed["size"], packed["pack"]), ("2.95 GB", "Pack 5.90 GB"))
        self.assertEqual(sources.describe(stream("p", "1080p", 2_950_000_000, folder=3_000_000_000))["pack"], "")
        hinted = {"url": "u", "behaviorHints": {"filename": "a.mkv", "videoSize": 242704598, "folderSize": 40057706460}}
        self.assertEqual(sources.describe(hinted)["pack"], "Pack 40.1 GB")
        described = {"url": "u", "behaviorHints": {"filename": "b.mkv", "videoSize": 828719564},
                     "description": "Naruto\n❖ 829 MB / 1.02 TB · 4.77 Mbps"}
        self.assertEqual(sources.describe(described)["pack"], "Pack 1.02 TB")
        self.assertIn("Pack 1.02 TB", sources.short_label(described))

    def test_fallbacks_without_stream_data(self):
        bare = {"url": "https://x", "name": "Fake 720p", "behaviorHints": {"videoSize": 900_000_000}}
        self.assertEqual(sources.resolution(bare), 720)
        self.assertEqual(sources.size_bytes(bare), 900_000_000)
        self.assertEqual(sources.stream_id(bare), "https://x")
        self.assertEqual(sources.resolution({"name": "Something 4K"}), 2160)

    def test_guesses_from_text_without_stream_data(self):
        remux = {"url": "https://x/playback/token1", "name": "4K ⚡", "description": "☁ The Matrix\n⛉ [DL] Library",
                 "behaviorHints": {"filename": "The.Matrix.1999.PROPER.2160p.BluRay.REMUX.HEVC.DTS-HD.MA.TrueHD.7.1.Atmos-FGT.mkv",
                                   "bingeGroup": "com.aiostreams.viren070|2160p|BluRay REMUX|FGT", "videoSize": 65_700_000_000}}
        self.assertEqual(sources.short_label(remux), "4K · Remux · SDR · HEVC · Atmos TrueHD 7.1 · 65.7 GB · DL ⚡")
        web = {"url": "https://x/2", "name": "1080p", "description": "[RD] cached",
               "behaviorHints": {"filename": "Show.S01E01.1080p.WEB-DL.DDP5.1.HDR10+.DV.H.264-GRP.mkv"}}
        info = sources.describe(web)
        self.assertEqual((info["quality"], info["hdr"], info["codec"], info["audio"], info["service"]),
                         ("WEB-DL", "DV HDR10+", "H.264", "DD+ 5.1", "RD"))
        self.assertEqual(sources.describe({"name": "x", "behaviorHints": {"filename": "a.DVDRip.AC3.mkv"}})["audio"], "DD")
        again = dict(remux, url="https://x/playback/token2")
        self.assertEqual(sources.stream_id(remux), sources.stream_id(again))
        self.assertEqual(sources.find([again], sources.stream_id(remux)), again)

    def test_default_is_first_in_aiostreams_order(self):
        streams = [stream("a", "2160p"), stream("b", "1080p")]
        self.assertEqual(sources.pick(streams, {"id": "m"})["url"], "https://x/a")
        self.assertIsNone(sources.pick([], {"id": "m"}))

    def test_caps_skip_but_fall_back(self):
        streams = [stream("remux", "2160p", 70_000_000_000), stream("web", "2160p", 14_000_000_000), stream("hd", "1080p", 4_000_000_000)]
        self.settings.values["max_bitrate"] = 40
        self.assertEqual(sources.stream_id(sources.pick(streams, {"id": "m", "runtime": 7200})), "web")
        self.settings.values["max_resolution"] = 1080
        self.assertEqual(sources.stream_id(sources.pick(streams, {"id": "m", "runtime": 7200})), "hd")
        self.settings.values["max_resolution"] = 720
        self.assertEqual(sources.stream_id(sources.pick(streams, {"id": "m", "runtime": 7200})), "remux")

    def test_remembered_file_then_group_for_series(self):
        e1 = {"id": "s:1:1", "seriesId": "s"}
        first = [stream("a1", "2160p", group="g4k", filename="S01E01.2160p.mkv"), stream("b1", "1080p", group="ghd", filename="S01E01.1080p.mkv")]
        sources.remember(e1, first[1])
        self.assertEqual(sources.stream_id(sources.pick(first, e1)), "b1")
        second = [stream("a2", "2160p", group="g4k"), stream("b2", "1080p", group="ghd")]
        for _ in range(3):
            self.assertEqual(sources.stream_id(sources.pick(second, {"id": "s:1:2", "seriesId": "s"})), "b2")
        self.assertEqual(sources.stream_id(sources.pick(second, {"id": "other"})), "a2")

    def test_format_size(self):
        self.assertEqual(sources.format_size(4_530_000_000), "4.53 GB")
        self.assertEqual(sources.format_size(120_000_000_000), "120 GB")
        self.assertEqual(sources.format_size(47_200_000), "47 MB")
        self.assertEqual(sources.format_size(0), "")


if __name__ == "__main__":
    unittest.main()
