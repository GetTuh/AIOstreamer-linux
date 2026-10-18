import logging
import time

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from jellyfin_tv.api.trailer_cache import TrailerCache
from jellyfin_tv.api.trailers import TrailerResolver, search_url

log = logging.getLogger("jellyfin_tv.trailers")

DELAY_MS = 800
TRAILER_TYPES = ("Movie", "Series")
ITEM_TTL = 3600


class TrailerPreview(QObject):
    changed = Signal()

    def __init__(self, runner, library, settings, resolver=None, clock=time.monotonic, cache=None, parent=None):
        super().__init__(parent)
        self._runner = runner
        self._library = library
        self._settings = settings
        self._resolver = resolver or TrailerResolver()
        self._clock = clock
        self._cache = cache or TrailerCache()
        self._items = {}
        self._pending = ""
        self._generation = 0
        self._streams = None
        self._status = ""
        self._explicit = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DELAY_MS)
        self._timer.timeout.connect(self._lookup)
        settings.changed.connect(self._settings_changed)

    @property
    def mode(self):
        return self._settings.get("trailer_previews") or "off"

    @Property(str, notify=changed)
    def itemId(self):
        return self._pending if self._streams else ""

    @Property(str, notify=changed)
    def videoUrl(self):
        return self._streams["video"] if self._streams else ""

    @Property(str, notify=changed)
    def audioUrl(self):
        return self._streams["audio"] if self._streams else ""

    @Property(bool, notify=changed)
    def muxed(self):
        return bool(self._streams and self._streams.get("muxed"))

    @Property(bool, notify=changed)
    def muted(self):
        return self.mode != "sound"

    @Property(str, notify=changed)
    def currentId(self):
        return self._pending

    @Property(str, notify=changed)
    def status(self):
        return self._status

    @Slot(str, str)
    def request(self, item_id, item_type):
        if item_id == self._pending:
            return
        self.stop()
        if not item_id or item_type not in TRAILER_TYPES:
            return
        self._pending = item_id
        if self.mode != "off":
            self._set_status("loading")
            self._timer.start()

    @Slot(str, str)
    def watch(self, item_id, item_type):
        if item_id != self._pending:
            self.request(item_id, item_type)
        self._explicit = self._pending == item_id
        if self._pending != item_id or self._status in ("ready", "none"):
            return
        if self._status == "" or self._timer.isActive():
            self._timer.stop()
            self._set_status("loading")
            self._lookup()

    @Slot(str, result=str)
    def cached(self, url):
        if not url.startswith(("http://", "https://")):
            return url
        return self._cache.local_url(url)

    def shutdown(self):
        self.stop()
        self._cache.shutdown()

    @Slot(str)
    def release(self, item_id):
        if item_id and item_id == self._pending:
            self.stop()

    @Slot()
    def stop(self):
        self._timer.stop()
        self._generation += 1
        self._pending = ""
        self._explicit = False
        self._streams = None
        self._set_status("")

    @Slot()
    def failed(self):
        if self._streams is not None:
            self._streams = None
            self._set_status("none")

    def _set_status(self, status):
        self._status = status
        self.changed.emit()

    def _settings_changed(self):
        if self.mode == "off" and not self._explicit:
            pending = self._pending
            self.stop()
            self._pending = pending
            self.changed.emit()
        elif self._streams is not None:
            self.changed.emit()

    def _lookup(self):
        item_id = self._pending
        generation = self._generation
        hit = self._items.get(item_id)
        if hit and self._clock() - hit[0] < ITEM_TTL:
            self._ready(generation, item_id, hit[1])
            return
        self._runner.run(lambda: self._find(item_id), lambda s: self._found(generation, item_id, s),
                         lambda _e: self._ready(generation, item_id, None))

    def _find(self, item_id):
        found = self._library.trailers(item_id)
        if self._resolver.available:
            fallback = search_url(found["title"], found.get("year"))
            for url in found["remote"] + ([fallback] if fallback else []):
                try:
                    streams = self._resolver.resolve(url)
                except Exception as exc:
                    log.info("trailer %s: %s", url, exc)
                    continue
                if streams:
                    return streams
        return None

    def _found(self, generation, item_id, streams):
        self._items[item_id] = (self._clock(), streams)
        self._ready(generation, item_id, streams)

    def _ready(self, generation, item_id, streams):
        if generation != self._generation or item_id != self._pending:
            return
        self._streams = streams or None
        self._set_status("ready" if streams else "none")
