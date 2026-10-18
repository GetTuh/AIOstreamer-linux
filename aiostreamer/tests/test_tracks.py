import unittest

from aiostreamer.player.tracks import canonical, choose_audio, choose_subtitle, preferred

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

    def test_old_original_setting_is_ignored(self):
        self.assertEqual(preferred("original,eng"), ["eng"])

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
