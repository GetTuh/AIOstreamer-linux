import json
import unittest
from unittest import mock

from jellyfin_tv.tests.helpers import FakeSettings
from jellyfin_tv.api import session as session_mod
from jellyfin_tv.api.images import image_source
from jellyfin_tv.api.session import Session, normalize_server, same_origin


class SessionHelpersTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_server(" serv.local:3020/ "), "http://serv.local:3020")
        self.assertEqual(normalize_server("https://x.y"), "https://x.y")

    def test_same_origin(self):
        self.assertTrue(same_origin("https://host/a", "https://host:443/b"))
        self.assertTrue(same_origin("http://host:3020/a", "http://HOST:3020"))
        self.assertFalse(same_origin("http://host:3020/a", "http://host:3021"))
        self.assertFalse(same_origin("https://cdn.example/a", "http://host"))

    def test_url_and_header(self):
        s = Session(FakeSettings())
        s.server = "http://h"
        s.token = "T"
        self.assertEqual(s.url("/Items/1", maxWidth=300, tag=None), "http://h/Items/1?maxWidth=300")
        self.assertIn('Token="T"', s.auth_header())
        self.assertIn('DeviceId="test-device"', s.auth_header())


class TokenStoreTest(unittest.TestCase):
    def test_falls_back_to_private_file(self):
        s = Session(FakeSettings())
        with mock.patch.object(session_mod.keyring, "set_password", side_effect=RuntimeError("no backend")), \
                mock.patch.object(session_mod.keyring, "get_password", side_effect=RuntimeError("no backend")), \
                mock.patch.object(session_mod.keyring, "delete_password", side_effect=RuntimeError("no backend")):
            s._write_stored(json.dumps({"token": "x"}))
            path = s._fallback_path()
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(s._read_stored())["token"], "x")
            s._clear_stored()
            self.assertFalse(path.exists())


class MemoryStore:
    def __init__(self, raw=None):
        self.raw = raw

    def install(self, session):
        session._read_stored = lambda: self.raw
        session._write_stored = lambda raw: setattr(self, "raw", raw)
        session._clear_stored = lambda: setattr(self, "raw", None)
        session._restore_account = lambda data: session._fake_activate(data)
        session._activate = lambda server, user_id, token, username: session._fake_activate(
            {"server": server, "user_id": user_id, "token": token, "username": username})
        session._teardown = lambda: setattr(session, "client", None)

        def fake_activate(data):
            session.client = object()
            session.server, session.user_id = data["server"], data["user_id"]
            session.token, session.username = data["token"], data.get("username", "")
            return True
        session._fake_activate = fake_activate


class AccountsTest(unittest.TestCase):
    def session(self, store):
        s = Session(FakeSettings())
        store.install(s)
        return s

    def login_as(self, s, server, user_id, name):
        s._switch_to(server, {"AccessToken": "tok-" + user_id, "User": {"Id": user_id, "Name": name}})

    def test_migrates_single_account_format(self):
        store = MemoryStore(json.dumps({"server": "http://a", "user_id": "u1", "token": "t", "username": "ann"}))
        s = self.session(store)
        self.assertTrue(s.restore())
        self.assertEqual(s.username, "ann")
        self.assertEqual([(a["username"], a["active"]) for a in s.accounts()], [("ann", True)])

    def test_multiple_accounts_switch_and_sign_out(self):
        store = MemoryStore()
        s = self.session(store)
        self.login_as(s, "http://a", "u1", "ann")
        self.login_as(s, "http://b", "u2", "bob")
        self.login_as(s, "http://b", "u2", "bob")
        accounts = s.accounts()
        self.assertEqual([(a["username"], a["active"]) for a in accounts], [("ann", False), ("bob", True)])
        for _ in range(3):
            s.switch(accounts[0]["key"])
            self.assertEqual(s.username, "ann")
            s.switch(accounts[1]["key"])
        self.assertEqual(json.loads(store.raw)["active"], accounts[1]["key"])
        s.logout()
        self.assertFalse(s.logged_in)
        self.assertEqual([a["username"] for a in self.session(store).accounts()], ["ann"])
        self.assertFalse(self.session(store).restore())
        s2 = self.session(store)
        s2.switch(accounts[0]["key"])
        s2.logout()
        self.assertIsNone(store.raw)

    def test_quick_connect_header_has_no_token(self):
        s = Session(FakeSettings())
        s.token = "T"
        self.assertNotIn("Token=", s.auth_header(False))


class ImageSourceTest(unittest.TestCase):
    def test_movie(self):
        item = {"Id": "m", "Type": "Movie", "ImageTags": {"Primary": "p", "Thumb": "t", "Logo": "l"}, "BackdropImageTags": ["b"]}
        self.assertEqual(image_source(item, "poster"), "image://jf/m/Primary/360/p")
        self.assertEqual(image_source(item, "thumb"), "image://jf/m/Thumb/560/t")
        self.assertEqual(image_source(item, "backdrop"), "image://jf/m/Backdrop.0/1920/b")
        self.assertEqual(image_source(item, "logo"), "image://jf/m/Logo/800/l")

    def test_episode(self):
        item = {"Id": "e", "Type": "Episode", "ImageTags": {"Primary": "ep"}, "SeriesId": "s", "SeriesPrimaryImageTag": "sp",
                "ParentBackdropItemId": "s", "ParentBackdropImageTags": ["sb"]}
        self.assertEqual(image_source(item, "thumb"), "image://jf/e/Primary/560/ep")
        self.assertEqual(image_source(item, "poster"), "image://jf/s/Primary/360/sp")
        self.assertEqual(image_source(item, "backdrop"), "image://jf/s/Backdrop.0/1920/sb")
        self.assertEqual(image_source(item, "logo"), "image://jf/s/Logo/800/series")

    def test_missing(self):
        self.assertEqual(image_source({"Id": "x", "Type": "Movie"}, "poster"), "")


if __name__ == "__main__":
    unittest.main()
