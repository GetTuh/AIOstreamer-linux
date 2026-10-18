import json
import logging
import tempfile
import threading
import time
import unittest
from unittest import mock

import requests

from aiostreamer.tests.helpers import FakeSettings
from aiostreamer.api import session as session_module
from aiostreamer.api.aio import AioClient, AioError, USER_AGENT, manifest_uuid, normalize_manifest_url, resolve_manifest, supports
from aiostreamer.api.cache import JsonCache
from aiostreamer.api.session import LoginError, Session, account_key, display_name

BASE = "https://aio.example/stremio/0f1e2d3c-1111-2222-3333-444455556666/ENC"
MANIFEST = BASE + "/manifest.json"


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Resp:
    def __init__(self, data, status=200):
        self.data = data
        self.status_code = status

    def json(self):
        if isinstance(self.data, Exception):
            raise self.data
        return self.data


class FakeHttp:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, timeout=None, headers=None, auth=None):
        self.calls.append(url)
        self.headers = headers
        self.auth = auth
        for key, value in self.routes.items():
            if key in url:
                if isinstance(value, Exception):
                    raise value
                return value if isinstance(value, Resp) else Resp(value)
        return Resp({}, 404)


def client(routes, clock=None):
    http = FakeHttp(routes)
    cache = JsonCache(tempfile.mkdtemp(prefix="aios-cache-"), clock=clock or Clock())
    return AioClient(MANIFEST, cache, http=http), http


class ManifestUrlTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_manifest_url(MANIFEST), MANIFEST)
        self.assertEqual(normalize_manifest_url(" stremio://aio.example/stremio/u/p/manifest.json "), "https://aio.example/stremio/u/p/manifest.json")
        self.assertEqual(normalize_manifest_url("aio.example/stremio/u/p/"), "https://aio.example/stremio/u/p/manifest.json")
        self.assertEqual(normalize_manifest_url("http://a/stremio/u/p/manifest.json?variant=2"), "http://a/stremio/u/p/manifest.json?variant=2")
        self.assertEqual(normalize_manifest_url("https://v3-cinemeta.strem.io/manifest.json"), "https://v3-cinemeta.strem.io/manifest.json")
        with self.assertRaises(AioError):
            normalize_manifest_url("https://")
        with self.assertRaises(AioError):
            normalize_manifest_url("https://aio.example")

    def test_supports_and_prefix(self):
        manifest = {"types": ["movie"], "idPrefixes": ["tt"], "resources": [
            "catalog", {"name": "meta", "types": ["library"], "idPrefixes": ["aiostreams::library"]}]}
        self.assertTrue(supports(manifest, "catalog", "movie", "tt1"))
        self.assertFalse(supports(manifest, "catalog", "movie", "kitsu:1"))
        self.assertTrue(supports(manifest, "meta", "library", "aiostreams::library.x"))
        self.assertFalse(supports(manifest, "meta", "movie", "tt1"))
        client = AioClient("https://c.example/manifest.json", None, prefix="cinemeta:")
        self.assertEqual(client.key(client.url("meta", "movie", "tt1")), "cinemeta:/meta/movie/tt1.json")

    def test_uuid_and_names(self):
        self.assertEqual(manifest_uuid(MANIFEST), "0f1e2d3c-1111-2222-3333-444455556666")
        self.assertEqual(display_name("", MANIFEST), "0f1e2d3c")
        self.assertEqual(display_name("living-room", MANIFEST), "living-room")
        self.assertEqual(account_key(MANIFEST), account_key(MANIFEST.replace("ENC", "OTHERENC")))

    def test_user_agent_asks_for_stream_data(self):
        self.assertTrue(USER_AGENT.startswith("AIO"))


class ClientTest(unittest.TestCase):
    def test_urls(self):
        c, _ = client({})
        self.assertEqual(c.url("meta", "series", "tt1:1:2"), BASE + "/meta/series/tt1:1:2.json")
        self.assertEqual(c.url("catalog", "movie", "top", {"genre": "Sci-Fi & Fantasy", "skip": 50}),
                         BASE + "/catalog/movie/top/genre=Sci-Fi%20%26%20Fantasy&skip=50.json")
        c2 = AioClient(MANIFEST + "?variant=2", c.cache, http=FakeHttp({}))
        self.assertEqual(c2.url("stream", "movie", "tt1"), BASE + "/stream/movie/tt1.json?variant=2")
        self.assertEqual(c2.url("manifest"), MANIFEST + "?variant=2")

    def test_catalog_cached_until_ttl_then_refetched(self):
        clock = Clock()
        c, http = client({"/catalog/": {"metas": [{"id": "tt1", "type": "movie"}, {"id": "aiostreamserror.x"}]}}, clock)
        for _ in range(4):
            self.assertEqual([m["id"] for m in c.catalog("movie", "top")], ["tt1"])
        self.assertEqual(len(http.calls), 1)
        clock.now += 31 * 60
        c.catalog("movie", "top")
        self.assertEqual(len(http.calls), 2)

    def test_disk_cache_survives_new_client(self):
        c, http = client({"/meta/": {"meta": {"id": "tt1", "type": "movie", "name": "A"}}})
        c.meta("movie", "tt1")
        again = AioClient(MANIFEST, JsonCache(c.cache.root, clock=c.cache._clock), http=http)
        self.assertEqual(again.peek_meta("movie", "tt1")["name"], "A")
        again.meta("movie", "tt1")
        self.assertEqual(len(http.calls), 1)

    def test_new_encrypted_password_keeps_cache(self):
        c, http = client({"/meta/": {"meta": {"id": "tt1", "type": "movie", "name": "A"}}})
        c.meta("movie", "tt1")
        again = AioClient(MANIFEST.replace("ENC", "NEWENC"), c.cache, http=http)
        again.meta("movie", "tt1")
        self.assertEqual(len(http.calls), 1)

    def test_stale_served_when_offline(self):
        clock = Clock()
        c, http = client({"/catalog/": {"metas": [{"id": "tt1"}]}}, clock)
        c.catalog("movie", "top")
        http.routes["/catalog/"] = requests.ConnectionError("down")
        clock.now += 10 * 3600
        self.assertEqual([m["id"] for m in c.catalog("movie", "top")], ["tt1"])
        with self.assertRaises(AioError):
            c.catalog("series", "top")

    def test_streams_keep_only_playable(self):
        c, _ = client({"/stream/": {"streams": [
            {"url": "https://a", "streamData": {"type": "debrid"}},
            {"name": "error", "streamData": {"type": "error"}},
            {"name": "stats", "streamData": {"type": "statistic"}, "url": "https://stats"},
            {"infoHash": "abc", "streamData": {"type": "p2p"}},
            {"url": "https://plain"},
        ]}})
        self.assertEqual([s["url"] for s in c.streams("movie", "tt1")], ["https://a", "https://plain"])

    def test_error_meta_raises(self):
        c, _ = client({"/meta/": {"meta": {"id": "aiostreamserror.1", "description": "Nope"}}})
        with self.assertRaises(AioError) as ctx:
            c.meta("movie", "tt1")
        self.assertIn("Nope", str(ctx.exception))

    def test_rate_limit_message(self):
        c, _ = client({"/meta/": Resp({}, 429)})
        with self.assertRaises(AioError) as ctx:
            c.meta("movie", "tt1")
        self.assertIn("rate limiting", str(ctx.exception))

    def test_manifest_fresh_skips_cache(self):
        c, http = client({"manifest.json": {"resources": ["catalog"], "catalogs": []}})
        c.manifest()
        c.manifest()
        c.manifest(fresh=True)
        self.assertEqual(len(http.calls), 2)


class CacheTest(unittest.TestCase):
    def test_concurrent_requests_share_one_fetch(self):
        cache = JsonCache(tempfile.mkdtemp(prefix="aios-cache-"))
        calls = []
        gate = threading.Event()

        def fetch():
            calls.append(1)
            gate.wait(2)
            return {"v": 1}

        results = []
        threads = [threading.Thread(target=lambda: results.append(cache.get("k", 60, fetch))) for _ in range(5)]
        for t in threads:
            t.start()
        time.sleep(0.1)
        gate.set()
        for t in threads:
            t.join(2)
        self.assertEqual(len(calls), 1)
        self.assertEqual(results, [{"v": 1}] * 5)

    def test_memory_bounded_and_clear(self):
        cache = JsonCache(tempfile.mkdtemp(prefix="aios-cache-"), memory_items=3)
        for i in range(10):
            cache.put("k%d" % i, i)
        self.assertEqual(len(cache._memory), 3)
        self.assertEqual(cache.peek("k0")[1], 0)
        cache.clear()
        self.assertIsNone(cache.peek("k5"))

    def test_prune_removes_old_files(self):
        clock = Clock()
        cache = JsonCache(tempfile.mkdtemp(prefix="aios-cache-"), clock=clock)
        cache.put("a", 1)
        clock.now = time.time() + 40 * 24 * 3600
        cache.prune()
        self.assertEqual(list(cache.root.iterdir()), [])


class ResolveTest(unittest.TestCase):
    def test_resolves_manifest_from_uuid_and_password(self):
        http = FakeHttp({"/api/v1/user": {"success": True, "data": {"userData": {"uuid": "real-uuid"}, "encryptedPassword": "E"}}})
        self.assertEqual(resolve_manifest("aio.example/", "alias", "pw", http), "https://aio.example/stremio/real-uuid/E/manifest.json")
        self.assertEqual(http.auth, ("alias", "pw"))

    def test_wrong_password(self):
        http = FakeHttp({"/api/v1/user": Resp({"success": False, "error": {"code": "USER_INVALID_DETAILS"}}, 401)})
        with self.assertRaises(AioError) as ctx:
            resolve_manifest("https://aio.example", "u", "bad", http)
        self.assertEqual(str(ctx.exception), "Wrong UUID or password")

    def test_not_an_instance(self):
        http = FakeHttp({"/api/v1/user": Resp(ValueError("html"))})
        with self.assertRaises(AioError):
            resolve_manifest("https://example.org", "u", "p", http)


class NoKeyring:
    def get_password(self, *a):
        raise RuntimeError("no keyring")

    set_password = delete_password = get_password


class SessionTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(session_module, "keyring", NoKeyring())
        patcher.start()
        self.addCleanup(patcher.stop)
        logging.getLogger("aiostreamer.session").setLevel(logging.ERROR)
        Session._fallback_path().unlink(missing_ok=True)
        self.http = FakeHttp({"manifest.json": {"resources": ["catalog"], "catalogs": []}})
        self.resolved = []

        def resolver(instance, user, password):
            self.resolved.append((instance, user, password))
            return MANIFEST

        def factory(manifest, key):
            return AioClient(manifest, JsonCache(tempfile.mkdtemp(prefix="aios-cache-")), http=self.http)

        self.settings = FakeSettings()
        self.session = Session(self.settings, resolver=resolver, client_factory=factory)

    def test_login_with_uuid_and_password(self):
        self.session.login("https://aio.example", "0f1e2d3c-1111-2222-3333-444455556666", "pw")
        self.assertTrue(self.session.logged_in)
        self.assertEqual(self.session.username, "0f1e2d3c")
        self.assertEqual(self.settings.get("username"), "0f1e2d3c-1111-2222-3333-444455556666")
        self.assertEqual(self.session.server, "https://aio.example")
        stored = json.loads(Session._fallback_path().read_text())
        self.assertEqual(stored["accounts"][0]["manifest"], MANIFEST)
        self.assertEqual(Session._fallback_path().stat().st_mode & 0o777, 0o600)

    def test_login_with_pasted_manifest_skips_resolver(self):
        self.session.login(MANIFEST, "", "")
        self.assertEqual(self.resolved, [])
        self.assertTrue(self.session.logged_in)

    def test_login_needs_user(self):
        with self.assertRaises(LoginError):
            self.session.login("https://aio.example", "", "")

    def test_bad_manifest_rejected(self):
        self.http.routes["manifest.json"] = Resp({}, 404)
        with self.assertRaises(LoginError):
            self.session.login(MANIFEST, "", "")
        self.assertFalse(self.session.logged_in)

    def test_restore_switch_logout(self):
        self.session.login(MANIFEST, "", "")
        other = MANIFEST.replace("0f1e2d3c", "99999999")
        self.session.login(other, "kids", "")
        accounts = self.session.accounts()
        self.assertEqual([a["active"] for a in accounts], [False, True])
        restored = Session(self.settings, client_factory=self.session._client_factory)
        self.assertTrue(restored.restore())
        self.assertEqual(restored.username, "kids")
        restored.switch(accounts[0]["key"])
        self.assertEqual(restored.username, "0f1e2d3c")
        restored.logout()
        self.assertFalse(restored.logged_in)
        self.assertEqual(len(restored.accounts()), 1)

    def test_restore_works_offline_from_cached_manifest(self):
        self.session.login(MANIFEST, "", "")
        cache_root = self.session.client.cache.root
        self.http.routes["manifest.json"] = requests.ConnectionError("down")

        def factory(manifest, key):
            clock = Clock()
            clock.now = time.time() + 7 * 3600
            return AioClient(manifest, JsonCache(cache_root, clock=clock), http=self.http)

        restored = Session(self.settings, client_factory=factory)
        self.assertTrue(restored.restore())


if __name__ == "__main__":
    unittest.main()
