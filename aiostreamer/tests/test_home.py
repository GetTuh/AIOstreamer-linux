import unittest

from aiostreamer.tests.helpers import SyncRunner, app

from aiostreamer.models.home import HomeModel, is_library


def catalog(kind, catalog_id, title):
    return {"key": "catalog:%s:%s" % (kind, catalog_id), "title": title, "type": kind, "id": catalog_id,
            "extra": {}, "genres": [], "genreRequired": False}


class FakeLibrary:
    def __init__(self, catalogs):
        self.catalogs = catalogs

    def home_catalogs(self, cached=False):
        return self.catalogs

    def catalog(self, *args):
        return [], 0

    def peek_catalog(self, *args):
        return None

    def resume(self, limit):
        return []

    next_up = recent = resume

    def favorites(self):
        return []


class HomeTest(unittest.TestCase):
    def setUp(self):
        app()

    def test_library_catalogs_go_last_and_recent_follows_my_list(self):
        catalogs = [catalog("library", "lib", "Debrid-Link Library"), catalog("movie", "top", "Popular Movies"),
                    catalog("series", "dl-library", "Series"), catalog("series", "top", "Popular Series")]
        home = HomeModel(SyncRunner(), FakeLibrary(catalogs))
        home._on_catalogs(catalogs)
        self.assertEqual([k for k, _ in home._rows], [
            "catalog:movie:top", "catalog:series:top", "catalogs", "catalog:library:lib", "catalog:series:dl-library"])
        home.load()
        keys = [k for k, _ in home._rows]
        self.assertEqual(keys[:4], ["resume", "nextup", "favorites", "recent"])
        self.assertEqual(keys[-2:], ["catalog:library:lib", "catalog:series:dl-library"])
        self.assertEqual(home._rows[3][1].title, "Recently Watched")

    def test_is_library(self):
        self.assertTrue(is_library(catalog("library", "x", "Mine")))
        self.assertFalse(is_library(catalog("movie", "top", "Popular Movies")))


if __name__ == "__main__":
    unittest.main()
