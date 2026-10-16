import unittest

from jellyfin_tv.tests.helpers import FakeSettings
from jellyfin_tv.models import sources
from jellyfin_tv.models.services import services

AIO_NAME = (
    "1080P‍‍\xa0\xa0‍⚡\n\xa0\xa0〈Web‍-‍dl〉\n"
    "✎  The Great Dictator (1940) \n▣  AVC ♬ DD+  ♯ 2.0\n◈ 4.53 GB · 4.81 ᴹᵇᵖˢ"
)


def source(sid, name="", height=None, width=None, codec=None, vrange=None, size=None, audio=None, channels=2):
    streams = []
    if height or width or codec or vrange:
        streams.append({"Type": "Video", "Height": height, "Width": width, "Codec": codec, "VideoRangeType": vrange})
    if audio:
        streams.append({"Type": "Audio", "Codec": audio, "Channels": channels})
    return {"Id": sid, "Name": name, "Size": size, "MediaStreams": streams}


class SourcesTest(unittest.TestCase):
    def setUp(self):
        services.settings = FakeSettings()

    def tearDown(self):
        services.settings = None

    def test_named_resolution_wins_over_stream_dimensions(self):
        s = source("a", AIO_NAME, height=960, width=1280)
        self.assertEqual(sources.resolution(s), 1080)

    def test_stream_resolution_when_name_has_none(self):
        self.assertEqual(sources.resolution(source("a", "Movie", height=2160, width=3840)), 2160)
        self.assertEqual(sources.resolution(source("b", "Movie", height=800, width=1920)), 1080)

    def test_release_text_is_cleaned(self):
        text = sources.release_text({"Name": AIO_NAME})
        self.assertNotIn("‍", text)
        self.assertNotIn("✎", text)
        self.assertIn("〈Web-dl〉", text)
        self.assertIn("4.53 GB", text)

    def test_size_from_name_is_decimal(self):
        self.assertEqual(sources.size_bytes({"Name": AIO_NAME}), 4530000000)
        self.assertEqual(sources.size_bytes({"Size": 4_529_123_456, "Name": AIO_NAME}), 4_529_123_456)
        self.assertEqual(sources.size_bytes({"Size": 123, "Name": AIO_NAME}), 4530000000)

    def test_pack_size_is_not_the_file_size(self):
        pack = {"Name": "1080P\n〈Bluray〉\n▣ HEVC\n◈ 2.95 / 5.9 GB · 2.64 ᴹᵇᵖˢ"}
        self.assertEqual(sources.size_bytes(pack), 2_950_000_000)
        self.assertEqual(sources.pack_bytes(pack), 5_900_000_000)
        self.assertEqual(sources.describe(pack)["size"], "2.95 GB of 5.90 GB")
        mb = {"Name": "❖ 47.2 MB / 601 MB · 2.16 ᴹᵇᵖˢ"}
        self.assertEqual(sources.size_bytes(mb), 47_200_000)
        self.assertEqual(sources.describe(mb)["size"], "47 MB of 601 MB")
        self.assertEqual(sources.pack_bytes({"Name": "◈ 11 GB · 9.43 ᴹᵇᵖˢ"}), 0)

    def test_garbage_size_and_bitrate_fields_fall_back_to_label(self):
        bogus = {"Size": 582, "Bitrate": 38, "RunTimeTicks": 1209600000, "Name": "◈ 395 MB · 17.6 ᴹᵇᵖˢ⇄ 1❦ · 225d"}
        self.assertEqual(sources.size_bytes(bogus), 395_000_000)
        self.assertEqual(sources.bitrate(bogus), 17_600_000)
        self.assertEqual(sources.describe(bogus)["size"], "395 MB")
        mismatch = {"Size": 111_000_000_000, "Name": "◈ 2.11 / 111 GB · 11.8 ᴹᵇᵖˢ"}
        self.assertEqual(sources.size_bytes(mismatch), 2_110_000_000)
        self.assertEqual(sources.describe(mismatch)["size"], "2.11 GB of 111 GB")

    def test_precise_field_wins_over_rounded_label(self):
        dune = {"Size": 11023536484, "Bitrate": 9426877, "Name": "◈ 11 GB · 9.43 ᴹᵇᵖˢ"}
        self.assertEqual(sources.size_bytes(dune), 11023536484)
        self.assertEqual(sources.bitrate(dune), 9426877)

    def test_hdr_detection(self):
        self.assertEqual(sources.hdr_type(source("a", "x", vrange="DOVIWithHDR10")), "DOVIWithHDR10")
        self.assertEqual(sources.hdr_type(source("a", "Movie 2160p DV HDR10")), "DOVI")
        self.assertEqual(sources.hdr_type(source("a", "Movie 2160p HDR10+")), "HDR10Plus")
        self.assertEqual(sources.describe(source("a", "Movie 2160p HDR10+"))["hdr"], "HDR10+")

    def test_ranking_prefers_resolution_then_hdr_then_size(self):
        small_av1 = source("small", "1080p", codec="av1", size=400_000_000)
        big_h264 = source("big", "1080p", codec="h264", size=4_000_000_000)
        uhd = source("uhd", "2160p", codec="hevc", size=1_000_000_000)
        uhd_dv = source("uhd-dv", "2160p DV", codec="hevc", size=900_000_000)
        ordered = [s["Id"] for s in sources.sort_sources([small_av1, big_h264, uhd, uhd_dv])]
        self.assertEqual(ordered, ["uhd-dv", "uhd", "big", "small"])

    def test_max_resolution_cap(self):
        services.settings = FakeSettings(max_resolution=1080)
        ordered = [s["Id"] for s in sources.sort_sources([source("uhd", "2160p"), source("hd", "1080p")])]
        self.assertEqual(ordered, ["hd", "uhd"])

    def test_prefer_hdr_off(self):
        services.settings = FakeSettings(prefer_hdr=False)
        ordered = [s["Id"] for s in sources.sort_sources([source("dv", "2160p DV"), source("sdr", "2160p")])]
        self.assertEqual(ordered, ["sdr", "dv"])

    def test_bitrate_from_field_or_size_and_runtime(self):
        self.assertEqual(sources.bitrate({"Bitrate": 5_000_000}), 5_000_000)
        self.assertEqual(sources.bitrate({"Size": 10_000_000_000, "RunTimeTicks": 8000 * 10_000_000}), 10_000_000)
        self.assertEqual(sources.bitrate({"Name": "x"}), 0)

    def test_max_bitrate_demotes_remux(self):
        services.settings = FakeSettings(max_bitrate=40)
        remux = dict(source("remux", "2160p DV", size=92_800_000_000), Bitrate=79_600_000)
        web = dict(source("web", "2160p HDR", size=7_440_000_000), Bitrate=6_390_000)
        tiny = dict(source("tiny", "2160p HDR", size=2_300_000_000), Bitrate=1_970_000)
        hd = dict(source("hd", "1080p", size=5_800_000_000), Bitrate=4_960_000)
        ordered = [s["Id"] for s in sources.sort_sources([remux, hd, tiny, web])]
        self.assertEqual(ordered, ["web", "tiny", "hd", "remux"])

    def test_max_bitrate_prefers_smallest_when_all_exceed(self):
        services.settings = FakeSettings(max_bitrate=20)
        a = dict(source("a", "2160p", size=96_000_000_000), Bitrate=75_000_000)
        b = dict(source("b", "2160p", size=75_000_000_000), Bitrate=59_000_000)
        unknown = source("unknown", "720p")
        ordered = [s["Id"] for s in sources.sort_sources([a, b, unknown])]
        self.assertEqual(ordered, ["unknown", "b", "a"])

    def test_original_audio_demotes_dub_only_versions(self):
        dub = dict(source("dub", "2160p"), MediaStreams=[{"Type": "Audio", "Language": "fre"}])
        multi = dict(source("multi", "1080p"), MediaStreams=[{"Type": "Audio", "Language": "fre"}, {"Type": "Audio", "Language": "eng"}])
        unknown = dict(source("unknown", "720p"), MediaStreams=[{"Type": "Audio", "Language": "und"}])
        services.settings = FakeSettings(audio_language="original")
        self.assertEqual([s["Id"] for s in sources.sort_sources([dub, multi, unknown], "en")], ["multi", "unknown", "dub"])
        self.assertEqual([s["Id"] for s in sources.sort_sources([dub, multi, unknown], "")], ["dub", "multi", "unknown"])
        services.settings = FakeSettings(audio_language="eng,en")
        self.assertEqual([s["Id"] for s in sources.sort_sources([dub, multi, unknown], "en")], ["dub", "multi", "unknown"])

    def test_remembered_source(self):
        items = [source("a", "2160p"), source("b", "720p")]
        self.assertEqual(sources.preferred_source_id("item", items), "a")
        sources.remember_source("item", "b")
        self.assertEqual(sources.preferred_source_id("item", items), "b")
        self.assertEqual(sources.preferred_source_id("item", [source("a", "2160p")]), "a")

    def test_pick_source(self):
        items = [source("a", "720p"), source("b", "2160p")]
        self.assertEqual(sources.pick_source(items)["Id"], "b")
        self.assertEqual(sources.pick_source(items, "a")["Id"], "a")
        self.assertIsNone(sources.pick_source([]))


if __name__ == "__main__":
    unittest.main()
