import os
import re
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

import requests

from jellyfin_tv.api import trailer_cache
from jellyfin_tv.api.trailer_cache import TrailerCache

DATA = os.urandom(300_000)


class Upstream:
    def __init__(self, ranges=True):
        self.requests = []
        upstream = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                upstream.requests.append(self.headers.get("Range"))
                match = re.match(r"bytes=(\d+)-(\d*)", self.headers.get("Range") or "")
                if ranges and match:
                    start = int(match.group(1))
                    end = min(int(match.group(2) or len(DATA) - 1), len(DATA) - 1)
                    self.send_response(206)
                    self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, len(DATA)))
                    body = DATA[start:end + 1]
                else:
                    self.send_response(200)
                    body = DATA
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d/video?sig=1" % self.server.server_address[1]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class TrailerCacheTest(unittest.TestCase):
    def setUp(self):
        self.upstream = Upstream()
        self.cache = TrailerCache()
        chunk = mock.patch.object(trailer_cache, "CHUNK", 64 * 1024)
        chunk.start()
        self.addCleanup(chunk.stop)

    def tearDown(self):
        self.cache.shutdown()
        self.upstream.close()

    def get(self, url, rng=None):
        return requests.get(url, headers={"Range": rng} if rng else {}, timeout=10)

    def test_serves_whole_file_downloaded_in_chunks(self):
        resp = self.get(self.cache.local_url(self.upstream.url))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, DATA)
        self.assertEqual(resp.headers["Content-Type"], "video/mp4")
        self.assertEqual(self.upstream.requests[:2], ["bytes=0-65535", "bytes=65536-131071"])

    def test_range_requests_like_a_seek(self):
        url = self.cache.local_url(self.upstream.url)
        for rng, expected in (("bytes=1000-1999", DATA[1000:2000]), ("bytes=250000-", DATA[250000:]), ("bytes=-500", DATA[-500:])):
            resp = self.get(url, rng)
            self.assertEqual(resp.status_code, 206)
            self.assertEqual(resp.content, expected)
        self.assertEqual(self.get(url, "bytes=999999-").status_code, 416)

    def test_seeks_do_not_refetch_from_upstream(self):
        url = self.cache.local_url(self.upstream.url)
        self.get(url)
        fetched = len(self.upstream.requests)
        for _ in range(3):
            self.assertEqual(self.get(url, "bytes=100-199").content, DATA[100:200])
        self.assertEqual(len(self.upstream.requests), fetched)

    def test_same_url_reuses_one_download(self):
        first = self.cache.local_url(self.upstream.url)
        self.assertEqual(self.cache.local_url(self.upstream.url), first)
        self.get(first)
        self.assertEqual(self.upstream.requests.count("bytes=0-65535"), 1)

    def test_upstream_without_range_support(self):
        plain = Upstream(ranges=False)
        self.addCleanup(plain.close)
        url = self.cache.local_url(plain.url)
        self.assertEqual(self.get(url, "bytes=10-19").content, DATA[10:20])
        self.assertEqual(len(plain.requests), 1)

    def test_old_entries_are_evicted(self):
        urls = [self.upstream.url + "&n=%d" % i for i in range(trailer_cache.KEEP + 2)]
        locals_ = [self.cache.local_url(u) for u in urls]
        self.assertEqual(self.get(locals_[0]).status_code, 404)
        self.assertEqual(self.get(locals_[-1]).content, DATA)

    def test_unknown_path_is_404(self):
        self.cache.local_url(self.upstream.url)
        port = self.cache._server.server_address[1]
        self.assertEqual(self.get("http://127.0.0.1:%d/nope" % port).status_code, 404)


if __name__ == "__main__":
    unittest.main()
