import unittest

from aiostreamer.player.tracks import canonical, choose_audio, choose_subtitle, country_language, preferred, wants_original

TRACKS = [
    {"type": "audio", "id": 1, "lang": "fre", "default": True},
    {"type": "audio", "id": 2, "lang": "eng"},
    {"type": "sub", "id": 1, "lang": "spa"},
    {"type": "sub", "id": 2, "lang": "eng", "title": "English Signs"},
    {"type": "sub", "id": 3, "lang": "eng", "title": "English SDH"},
    {"type": "sub", "id": 4, "lang": "en", "title": "English"},
]
ENG = preferred("eng,en")


class TracksTest(unittest.TestCase):
    def test_canonical(self):
        self.assertEqual(canonical("en"), "eng")
        self.assertEqual(canonical("deu"), "ger")
        self.assertEqual(preferred("eng,en"), ["eng"])
        self.assertEqual(canonical("und"), "")

    def test_original_without_known_language_is_skipped(self):
        self.assertEqual(preferred("original,eng"), ["eng"])
        self.assertEqual(preferred("original"), [])

    def test_original_language_from_country(self):
        self.assertEqual(country_language("Japan"), "jpn")
        self.assertEqual(country_language("United States, United Kingdom"), "eng")
        self.assertEqual(country_language("Atlantis"), "")
        self.assertTrue(wants_original("original,eng,en"))
        self.assertFalse(wants_original("eng,en"))
        self.assertEqual(preferred("original,eng,en", "jpn"), ["jpn", "eng"])
        dubbed = [
            {"type": "audio", "id": 1, "lang": "fre", "default": True},
            {"type": "audio", "id": 2, "lang": "jpn"},
        ]
        self.assertEqual(choose_audio(dubbed, preferred("original", "jpn")), 2)
        self.assertEqual(choose_audio(dubbed, preferred("original,eng", "kor")), None)

    def test_original_title_hint_when_language_unknown(self):
        tracks = [
            {"type": "audio", "id": 1, "lang": "ita", "default": True, "title": "Italiano"},
            {"type": "audio", "id": 2, "lang": "eng", "title": "English (Original)"},
        ]
        self.assertEqual(choose_audio(tracks, [], original_hint=True), 2)
        self.assertEqual(choose_audio(tracks, []), None)

    def test_audio_language_beats_default_track(self):
        tracks = [
            {"type": "audio", "id": 1, "lang": "fre", "default": True},
            {"type": "audio", "id": 2, "lang": "fre"},
            {"type": "audio", "id": 3, "lang": "eng"},
        ]
        self.assertEqual(choose_audio(tracks, preferred("eng")), 3)

    def test_foreign_audio_gets_full_english(self):
        self.assertEqual(choose_subtitle(TRACKS, ENG, "auto", "fre"), 4)

    def test_matching_audio_gets_forced_only(self):
        self.assertEqual(choose_subtitle(TRACKS, ENG, "auto", "eng"), 2)

    def test_matching_audio_without_forced_disables(self):
        tracks = [t for t in TRACKS if t.get("title") != "English Signs"]
        self.assertEqual(choose_subtitle(tracks, ENG, "auto", "en"), "no")

    def test_always_mode(self):
        self.assertEqual(choose_subtitle(TRACKS, ENG, "always", "eng"), 4)

    def test_off_mode(self):
        self.assertEqual(choose_subtitle(TRACKS, ENG, "off", "fre"), "no")

    def test_never_falls_back_to_other_language(self):
        self.assertEqual(choose_subtitle([{"type": "sub", "id": 1, "lang": "spa"}], ENG, "auto", "jpn"), "no")

    def test_language_from_title(self):
        tracks = [{"type": "sub", "id": 7, "title": "English (Full)"}]
        self.assertEqual(choose_subtitle(tracks, ENG, "auto", "jpn"), 7)

    def test_no_preference_keeps_mpv_choice(self):
        self.assertIsNone(choose_subtitle(TRACKS, [], "auto", "fre"))

    def test_audio(self):
        self.assertEqual(choose_audio(TRACKS, preferred("eng")), 2)
        self.assertIsNone(choose_audio(TRACKS, preferred("jpn")))
        self.assertIsNone(choose_audio(TRACKS, []))


if __name__ == "__main__":
    unittest.main()
