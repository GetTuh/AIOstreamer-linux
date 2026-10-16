import unittest

from jellyfin_tv.tests.helpers import SyncRunner, app
from jellyfin_tv.models.items import (
    ItemListModel, episode_label, match_score, normalize_title, progress_for, runtime_text, subtitle_for, title_for,
)


class HelpersTest(unittest.TestCase):
    def test_episode_label(self):
        self.assertEqual(episode_label({"ParentIndexNumber": 2, "IndexNumber": 5}), "S2:E5")
        self.assertEqual(episode_label({"IndexNumber": 5}), "E5")
        self.assertEqual(episode_label({}), "")

    def test_titles(self):
        ep = {"Type": "Episode", "SeriesName": "Show", "Name": "Pilot", "ParentIndexNumber": 1, "IndexNumber": 1}
        self.assertEqual(title_for(ep), "Show")
        self.assertEqual(subtitle_for(ep), "S1:E1 · Pilot")
        self.assertEqual(subtitle_for({"Type": "Series", "ProductionYear": 2008, "EndDate": "2013-09-29"}), "2008 – 2013")
        self.assertEqual(subtitle_for({"Type": "Series", "ProductionYear": 2020, "Status": "Continuing"}), "2020 –")
        self.assertEqual(subtitle_for({"Type": "Movie", "ProductionYear": 1999}), "1999")

    def test_progress(self):
        self.assertAlmostEqual(progress_for({"RunTimeTicks": 100, "UserData": {"PlaybackPositionTicks": 25}}), 0.25)
        self.assertAlmostEqual(progress_for({"UserData": {"PlayedPercentage": 50}}), 0.5)
        self.assertEqual(progress_for({"UserData": {"Played": True, "PlayedPercentage": 50}}), 0.0)

    def test_runtime(self):
        self.assertEqual(runtime_text(49 * 60 * 10_000_000), "49m")
        self.assertEqual(runtime_text(125 * 60 * 10_000_000), "2h 5m")
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
    def setUp(self):
        app()
        self.data = [{"Id": "a", "Name": "A"}, {"Id": "b", "Name": "B"}]
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
        self.data = [{"Id": "a", "Name": "A2"}, {"Id": "b", "Name": "B"}]
        self.model.reload()
        self.assertEqual(resets, [])
        self.assertEqual(changes, [1])
        self.assertEqual(self.model.get(0)["name"], "A2")

    def test_changed_ids_reset(self):
        self.model.reload()
        resets = []
        self.model.modelReset.connect(lambda: resets.append(1))
        self.data = [{"Id": "c", "Name": "C"}]
        self.model.reload()
        self.assertEqual(resets, [1])

    def test_paging(self):
        items = [{"Id": str(i), "Name": str(i)} for i in range(25)]
        model = ItemListModel(SyncRunner(), lambda s, n: (items[s:s + n], len(items)), page_size=10)
        model.reload()
        self.assertEqual(model.count, 10)
        self.assertTrue(model.canFetchMore())
        model.fetchMore()
        model.fetchMore()
        self.assertEqual(model.count, 25)
        self.assertFalse(model.canFetchMore())

    def test_episode_context(self):
        model = ItemListModel(SyncRunner(), lambda s, n: ([{"Id": "e", "Name": "Pilot", "IndexNumber": 1, "RunTimeTicks": 49 * 60 * 10_000_000}], 1), context="episodes")
        model.reload()
        self.assertEqual(model.get(0)["name"], "1. Pilot")
        self.assertEqual(model.get(0)["subtitle"], "49m")


if __name__ == "__main__":
    unittest.main()
