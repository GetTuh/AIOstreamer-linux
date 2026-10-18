import logging
import os
import re
import tempfile
import threading
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

log = logging.getLogger("aiostreamer.trailer_cache")

CHUNK = 4 * 1024 * 1024
BLOCK = 256 * 1024
KEEP = 4
WAIT = 30
RANGE = re.compile(r"bytes=(\d*)-(\d*)")
CONTENT_RANGE = re.compile(r"bytes \d+-\d+/(\d+)")


class Entry:
    def __init__(self, url, get=None):
        self.url = url
        self.size = 0
        self.total = None
        self.content_type = "application/octet-stream"
        self.done = False
        self.cancelled = False
        self._get = get or requests.get
        self._file = tempfile.TemporaryFile()
        self._cond = threading.Condition()

    def start(self):
        threading.Thread(target=self._download, daemon=True, name="aios-trailer-cache").start()

    def _download(self):
        try:
            while not self.cancelled:
                end = self.size + CHUNK - 1
                with self._get(self.url, headers={"Range": "bytes=%d-%d" % (self.size, end)}, stream=True, timeout=20) as resp:
                    resp.raise_for_status()
                    self.content_type = resp.headers.get("Content-Type", self.content_type)
                    whole = resp.status_code == 200
                    match = CONTENT_RANGE.match(resp.headers.get("Content-Range", ""))
                    with self._cond:
                        if match:
                            self.total = int(match.group(1))
                        elif whole and resp.headers.get("Content-Length"):
                            self.total = int(resp.headers["Content-Length"])
                        self._cond.notify_all()
                    for block in resp.iter_content(BLOCK):
                        if self.cancelled:
                            return
                        os.pwrite(self._file.fileno(), block, self.size)
                        with self._cond:
                            self.size += len(block)
                            self._cond.notify_all()
                if whole or (self.total is not None and self.size >= self.total):
                    break
        except Exception as exc:
            log.info("trailer cache %s", exc)
        finally:
            with self._cond:
                if self.total is None:
                    self.total = self.size
                self.done = True
                self._cond.notify_all()

    def wait_total(self, timeout=WAIT):
        with self._cond:
            self._cond.wait_for(lambda: self.total is not None or self.done, timeout)
            return self.total

    def read(self, offset, length, timeout=WAIT):
        with self._cond:
            if not self._cond.wait_for(lambda: self.size > offset or self.done or self.cancelled, timeout):
                return b""
            length = min(length, self.size - offset)
        if length <= 0:
            return b""
        return os.pread(self._file.fileno(), length, offset)

    def close(self):
        self.cancelled = True
        with self._cond:
            self._cond.notify_all()
        self._file.close()


class TrailerCache:
    def __init__(self, get=None):
        self._get = get
        self._entries = OrderedDict()
        self._lock = threading.Lock()
        self._server = None

    def local_url(self, url):
        if not url:
            return ""
        with self._lock:
            self._ensure_server()
            key = self._key(url)
            if key not in self._entries:
                entry = Entry(url, self._get)
                self._entries[key] = entry
                entry.start()
                while len(self._entries) > KEEP:
                    self._entries.popitem(last=False)[1].close()
            self._entries.move_to_end(key)
            return "http://127.0.0.1:%d/%s" % (self._server.server_address[1], key)

    def entry(self, key):
        with self._lock:
            return self._entries.get(key)

    @staticmethod
    def _key(url):
        return "%x" % (hash(url) & 0xFFFFFFFFFFFF)

    def _ensure_server(self):
        if self._server is not None:
            return
        cache = self

        class Handler(BaseHTTPRequestHandler):
            def do_HEAD(self):
                self._serve(body=False)

            def do_GET(self):
                self._serve(body=True)

            def _serve(self, body):
                entry = cache.entry(self.path.strip("/"))
                total = entry.wait_total() if entry else None
                if not total:
                    self.send_error(404)
                    return
                start, end, partial = 0, total - 1, False
                match = RANGE.match(self.headers.get("Range", ""))
                if match and (match.group(1) or match.group(2)):
                    partial = True
                    if match.group(1):
                        start = int(match.group(1))
                        end = min(int(match.group(2)), total - 1) if match.group(2) else total - 1
                    else:
                        start = max(0, total - int(match.group(2)))
                if start >= total:
                    self.send_response(416)
                    self.send_header("Content-Range", "bytes */%d" % total)
                    self.end_headers()
                    return
                self.send_response(206 if partial else 200)
                self.send_header("Content-Type", entry.content_type)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Length", str(end - start + 1))
                if partial:
                    self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, total))
                self.end_headers()
                if not body:
                    return
                offset = start
                try:
                    while offset <= end:
                        block = entry.read(offset, min(BLOCK, end - offset + 1))
                        if not block:
                            return
                        self.wfile.write(block)
                        offset += len(block)
                except (OSError, ValueError):
                    return

            def log_message(self, *args):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        threading.Thread(target=self._server.serve_forever, daemon=True, name="aios-trailer-server").start()

    def shutdown(self):
        with self._lock:
            for entry in self._entries.values():
                entry.close()
            self._entries.clear()
            if self._server is not None:
                self._server.shutdown()
                self._server.server_close()
                self._server = None
