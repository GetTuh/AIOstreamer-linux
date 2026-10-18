import base64
import hashlib
import logging
import os
import threading
import time
from pathlib import Path

import requests
from PySide6.QtCore import QRunnable, QSize, Qt, QThreadPool
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickAsyncImageProvider, QQuickImageResponse, QQuickTextureFactory

from aiostreamer.api.aio import USER_AGENT

log = logging.getLogger("aiostreamer.images")

PROVIDER_ID = "img"
CACHE_LIMIT_BYTES = 600 * 1024 * 1024
FAILED_RETRY_S = 600


def encode_url(url):
    return base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")


def decode_url(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)).decode()


def proxied(url, kind="poster"):
    if not url or not url.startswith(("http://", "https://")):
        return ""
    return "image://%s/%s/%s" % (PROVIDER_ID, kind, encode_url(url))


def image_source(item, kind):
    if kind == "poster":
        chain = ("poster", "thumbnail", "background")
    elif kind == "thumb":
        chain = ("thumbnail", "background", "poster") if item.get("type") == "Episode" else ("background", "thumbnail", "poster")
    elif kind == "backdrop":
        chain = ("background", "thumbnail")
    else:
        chain = ("logo",)
    urls = []
    for key in chain:
        url = item.get(key) or ""
        if url.startswith(("http://", "https://")) and url not in urls:
            urls.append(url)
    if not urls:
        return ""
    return "image://%s/%s/%s" % (PROVIDER_ID, kind, "/".join(encode_url(u) for u in urls))


class _Response(QQuickImageResponse):
    def __init__(self):
        super().__init__()
        self._image = QImage()
        self._error = ""

    def textureFactory(self):
        return QQuickTextureFactory.textureFactoryForImage(self._image)

    def errorString(self):
        return self._error

    def deliver(self, image, error=""):
        self._image = image
        self._error = error
        try:
            self.finished.emit()
        except RuntimeError:
            pass


class _Job(QRunnable):
    def __init__(self, provider, image_id, size, response):
        super().__init__()
        self.provider = provider
        self.image_id = image_id
        self.size = QSize(size)
        self.response = response

    def run(self):
        try:
            image = self.provider.load(self.image_id, self.size)
            self.response.deliver(image, "" if not image.isNull() else "no image")
        except Exception as exc:
            log.debug("image %s failed: %s", self.image_id, exc)
            self.response.deliver(QImage(), str(exc))
        finally:
            self.response = None


class ImageProvider(QQuickAsyncImageProvider):
    def __init__(self, cache_root):
        super().__init__()
        self.cache = Path(cache_root) / "images"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(4)
        self._http = threading.local()
        self._pending = {}
        self._failed = {}
        self._lock = threading.Lock()
        threading.Thread(target=self.prune, name="aios-image-prune", daemon=True).start()

    def requestImageResponse(self, image_id, requested_size):
        response = _Response()
        job = _Job(self, image_id, requested_size, response)
        key = id(response)
        with self._lock:
            self._pending[key] = response
        response.destroyed.connect(lambda *_, k=key: self._release(k), Qt.DirectConnection)
        self.pool.start(job)
        return response

    def _release(self, key):
        with self._lock:
            self._pending.pop(key, None)

    def _requests(self):
        sess = getattr(self._http, "session", None)
        if sess is None:
            sess = requests.Session()
            sess.headers["User-Agent"] = USER_AGENT
            self._http.session = sess
        return sess

    def load(self, image_id, size):
        _kind, *encoded = image_id.split("/")
        error = None
        for part in encoded:
            try:
                image = self._load_url(decode_url(part), size)
            except Exception as exc:
                error = exc
                continue
            if not image.isNull():
                return image
        if error is not None:
            raise error
        return QImage()

    def _load_url(self, url, size):
        path = self.cache / (hashlib.sha1(url.encode()).hexdigest() + ".img")
        if not path.exists():
            failed = self._failed.get(url)
            if failed and time.monotonic() - failed < FAILED_RETRY_S:
                return QImage()
            try:
                self._download(url, path)
            except Exception:
                self._failed[url] = time.monotonic()
                raise
        else:
            try:
                os.utime(path)
            except OSError:
                pass
        image = QImage(str(path))
        if image.isNull():
            path.unlink(missing_ok=True)
            return image
        if size.isValid() and size.width() > 0 and size.height() > 0:
            if image.width() > size.width() or image.height() > size.height():
                image = image.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        elif size.isValid() and size.width() > 0 and image.width() > size.width():
            image = image.scaledToWidth(size.width(), Qt.SmoothTransformation)
        elif size.isValid() and size.height() > 0 and image.height() > size.height():
            image = image.scaledToHeight(size.height(), Qt.SmoothTransformation)
        return image

    def _download(self, url, path):
        resp = self._requests().get(url, timeout=20)
        resp.raise_for_status()
        tmp = path.with_suffix(".part%d" % threading.get_ident())
        tmp.write_bytes(resp.content)
        os.replace(tmp, path)

    def prune(self):
        try:
            files = [(p.stat(), p) for p in self.cache.iterdir() if p.is_file()]
        except OSError:
            return
        now = time.time()
        for st, p in files:
            if ".part" in p.name and now - st.st_mtime > 3600:
                p.unlink(missing_ok=True)
        files = [(st, p) for st, p in files if p.exists()]
        total = sum(st.st_size for st, _ in files)
        if total <= CACHE_LIMIT_BYTES:
            return
        for st, p in sorted(files, key=lambda f: f[0].st_mtime):
            p.unlink(missing_ok=True)
            total -= st.st_size
            if total <= CACHE_LIMIT_BYTES * 0.8:
                break
