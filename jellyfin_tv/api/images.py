import logging
import os
import threading
import time
from pathlib import Path

import requests
from PySide6.QtCore import QRunnable, QSize, Qt, QThreadPool
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickAsyncImageProvider, QQuickImageResponse, QQuickTextureFactory

log = logging.getLogger("jellyfin_tv.images")

PROVIDER_ID = "jf"
WIDTHS = {"poster": 360, "thumb": 560, "backdrop": 1920, "logo": 800}
CACHE_LIMIT_BYTES = 600 * 1024 * 1024


def _source(item_id, image_type, tag, width, index=None):
    if not item_id or not tag:
        return ""
    kind = image_type if index is None else "%s.%s" % (image_type, index)
    return "image://%s/%s/%s/%d/%s" % (PROVIDER_ID, item_id, kind, width, tag)


def _primary(item, width):
    tags = item.get("ImageTags") or {}
    if tags.get("Primary"):
        return _source(item["Id"], "Primary", tags["Primary"], width)
    return ""


def _series_primary(item, width):
    if item.get("SeriesPrimaryImageTag"):
        return _source(item.get("SeriesId"), "Primary", item["SeriesPrimaryImageTag"], width)
    return ""


def _thumb(item, width):
    tags = item.get("ImageTags") or {}
    if tags.get("Thumb"):
        return _source(item["Id"], "Thumb", tags["Thumb"], width)
    if item.get("ParentThumbImageTag"):
        return _source(item.get("ParentThumbItemId"), "Thumb", item["ParentThumbImageTag"], width)
    return ""


def _backdrop(item, width):
    tags = item.get("BackdropImageTags") or []
    if tags:
        return _source(item["Id"], "Backdrop", tags[0], width, 0)
    parent_tags = item.get("ParentBackdropImageTags") or []
    if parent_tags:
        return _source(item.get("ParentBackdropItemId"), "Backdrop", parent_tags[0], width, 0)
    return ""


def _logo(item, width):
    tags = item.get("ImageTags") or {}
    if tags.get("Logo"):
        return _source(item["Id"], "Logo", tags["Logo"], width)
    if item.get("ParentLogoImageTag"):
        return _source(item.get("ParentLogoItemId"), "Logo", item["ParentLogoImageTag"], width)
    if item.get("Type") == "Episode" and item.get("SeriesId"):
        return _source(item["SeriesId"], "Logo", "series", width)
    return ""


def image_source(item, kind):
    width = WIDTHS[kind]
    if kind == "poster":
        chain = (_primary, _series_primary, _thumb)
        if item.get("Type") == "Episode":
            chain = (_series_primary, _primary)
    elif kind == "thumb":
        chain = (_thumb, _backdrop, _primary)
        if item.get("Type") == "Episode":
            chain = (_primary, _thumb, _backdrop)
    elif kind == "backdrop":
        chain = (_backdrop, _thumb)
    else:
        chain = (_logo,)
    for fn in chain:
        src = fn(item, width)
        if src:
            return src
    return ""


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
    def __init__(self, session, cache_root):
        super().__init__()
        self.session = session
        self.cache = Path(cache_root) / "images"
        self.cache.mkdir(parents=True, exist_ok=True)
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(4)
        self._http = threading.local()
        self._pending = {}
        self._lock = threading.Lock()
        threading.Thread(target=self.prune, name="jftv-image-prune", daemon=True).start()

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
            self._http.session = sess
        return sess

    def load(self, image_id, size):
        item_id, kind, width, tag = image_id.split("/", 3)
        image_type, _, index = kind.partition(".")
        path = self.cache / ("%s_%s_%s_%s.img" % (item_id, kind, width, tag))
        if not path.exists():
            self._download(item_id, image_type, index, width, tag, path)
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

    def _download(self, item_id, image_type, index, width, tag, path):
        handler = "Items/%s/Images/%s%s" % (item_id, image_type, "/" + index if index else "")
        url = self.session.url(handler, maxWidth=width, quality=90, tag=tag)
        resp = self._requests().get(url, headers={"Authorization": self.session.auth_header()}, timeout=20)
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
