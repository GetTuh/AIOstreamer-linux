from PySide6.QtCore import Property, QObject, Signal, Slot

from jellyfin_tv.api import meta as m
from jellyfin_tv.api.images import image_source
from jellyfin_tv.models.services import services
from jellyfin_tv.models.sources import describe, find, pick, remember, short_label, stream_id


def format_duration(seconds):
    seconds = int(seconds or 0)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%d:%02d" % (minutes, secs)


class DetailsModel(QObject):
    changed = Signal()
    playRequested = Signal(float, str)
    userDataChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._id = ""
        self._item = {}
        self._loading = False
        self._error = ""
        self._generation = 0
        self._sources = []
        self._selected = ""
        self._sources_loading = False
        self._pending_play = None
        self._series_played = False

    @property
    def _history(self):
        return services.library.history

    @Slot()
    def reload(self):
        if not self._id:
            return
        self._generation += 1
        generation = self._generation
        item_id = self._id
        if not self._item:
            cached = services.library.peek_item(item_id)
            if cached:
                self._item = cached
        self._loading = True
        self.changed.emit()
        services.runner.run(
            lambda: services.library.item(item_id),
            lambda item: generation == self._generation and self._loaded(item),
            lambda exc: generation == self._generation and self._failed(exc))

    def _set_id(self, value):
        if value == self._id:
            return
        self._id = value
        self._item = {}
        self._sources = []
        self._selected = ""
        self._pending_play = None
        self._series_played = False
        info = services.library.known(value) if value else {}
        self._sources_loading = bool(value) and info.get("type") in ("Movie", "Episode")
        self.changed.emit()
        self.reload()
        if self._sources_loading:
            self._load_sources(dict(info, id=value))

    def _loaded(self, item):
        self._item = item or {}
        self._loading = False
        self._error = ""
        if not self.playable:
            self._sources_loading = False
            self._pending_play = None
        elif not self._sources and not self._sources_loading:
            self._sources_loading = True
            self._load_sources(self._item)
        if self._item.get("type") == "Series":
            self._check_series_played()
        self._rank()
        self.changed.emit()

    def _check_series_played(self):
        item = self._item
        history = self._history

        def compute():
            _show, episodes = services.library.series(item["id"], item.get("stremioType") or "series")
            aired = [e for e in episodes if e.get("season") not in (0, None) and m.released(e)]
            return bool(aired) and all(history.watched(e["id"]) for e in aired)

        services.runner.run(compute, self._series_checked, lambda _e: None)

    def _series_checked(self, played):
        self._series_played = played
        self.changed.emit()

    def _load_sources(self, item):
        item_id = item["id"]
        services.runner.run(
            lambda: services.library.streams(item),
            lambda sources: item_id == self._id and self._sources_loaded(sources),
            lambda exc: item_id == self._id and self._sources_failed(exc))

    def _rank(self):
        if not self._sources:
            return
        if not find(self._sources, self._selected):
            chosen = pick(self._sources, self._item or {"id": self._id}, self._item.get("runtime", 0))
            self._selected = stream_id(chosen) if chosen else ""

    def _sources_failed(self, exc):
        self._error = "" if self._item else str(exc)
        self._sources_loaded([])

    def _sources_loaded(self, sources):
        self._sources_loading = False
        self._sources = list(sources)
        self._rank()
        pending, self._pending_play = self._pending_play, None
        self.changed.emit()
        if pending is not None and self._sources:
            self.playRequested.emit(pending, self._selected)

    @Slot()
    def refreshSources(self):
        if not self.playable or self._sources_loading:
            return
        item = self._item
        self._sources_loading = True
        self.changed.emit()
        services.runner.run(
            lambda: services.library.streams(item, fresh=True),
            lambda sources: item.get("id") == self._id and self._sources_loaded(sources),
            lambda exc: item.get("id") == self._id and self._sources_failed(exc))

    @Slot(float)
    def play(self, seconds):
        if self._sources_loading:
            self._pending_play = seconds
            self.changed.emit()
            return
        self.playRequested.emit(seconds, self._selected)

    @Property(bool, notify=changed)
    def playPending(self):
        return self._pending_play is not None

    @Property(bool, notify=changed)
    def sourcesLoading(self):
        return self._sources_loading

    def _failed(self, exc):
        self._loading = False
        if not self._item:
            self._error = str(exc) or "Could not load this title"
        self.changed.emit()

    @property
    def item(self):
        return self._item

    def _get(self, key, default=None):
        value = self._item.get(key)
        return default if value is None else value

    @Property(bool, notify=changed)
    def loading(self):
        return self._loading

    @Property(bool, notify=changed)
    def loaded(self):
        return bool(self._item)

    @Property(str, notify=changed)
    def error(self):
        return self._error

    itemId = Property(str, lambda self: self._id, _set_id, notify=changed)

    @Property(str, notify=changed)
    def itemType(self):
        return self._get("type", "")

    @Property(str, notify=changed)
    def stremioType(self):
        return self._get("stremioType", "")

    @Property(str, notify=changed)
    def name(self):
        return self._get("name", "")

    @Property(str, notify=changed)
    def seriesName(self):
        return self._get("seriesName", "")

    @Property(str, notify=changed)
    def episodeLabel(self):
        return m.episode_label(self._item) if self._get("type") == "Episode" else ""

    @Property(str, notify=changed)
    def overview(self):
        return self._get("overview", "")

    @Property(str, notify=changed)
    def tagline(self):
        return ""

    @Property(str, notify=changed)
    def year(self):
        return self._get("year", "")

    @Property(str, notify=changed)
    def runtime(self):
        return m.runtime_text(self._get("runtime", 0))

    @Property(str, notify=changed)
    def officialRating(self):
        return ""

    @Property(str, notify=changed)
    def communityRating(self):
        return self._get("rating", "")

    @Property(str, notify=changed)
    def genres(self):
        return " · ".join(self._get("genres", [])[:3])

    @Property(str, notify=changed)
    def backdrop(self):
        return image_source(self._item, "backdrop") if self._item else ""

    @Property(str, notify=changed)
    def logo(self):
        return image_source(self._item, "logo") if self._item else ""

    @Property(str, notify=changed)
    def poster(self):
        return image_source(self._item, "poster") if self._item else ""

    @Property(float, notify=changed)
    def resumeSeconds(self):
        return float(self._history.progress(self._id)[0]) if self._history else 0.0

    @Property(str, notify=changed)
    def resumeText(self):
        return format_duration(self.resumeSeconds)

    @Property(float, notify=changed)
    def progress(self):
        return self._history.fraction(self._id) if self._history else 0.0

    @Property(bool, notify=changed)
    def played(self):
        if self._get("type") == "Series":
            return self._series_played
        return bool(self._history and self._history.watched(self._id))

    @Property(bool, notify=changed)
    def playable(self):
        return bool(self._item) and self._get("type") in ("Movie", "Episode")

    @Property(int, notify=changed)
    def sourceCount(self):
        return len(self._sources)

    @Property(str, notify=changed)
    def seriesId(self):
        return self._get("seriesId", "")

    @Property(bool, notify=changed)
    def favorite(self):
        target = self._get("seriesId") or self._id
        return bool(self._history and self._history.favorite(target))

    def _user_updated(self, _value):
        self.changed.emit()
        self.userDataChanged.emit(self._id)

    @Slot()
    def togglePlayed(self):
        if not self._item:
            return
        item, value = dict(self._item), not self.played
        if item.get("type") == "Series":
            self._series_played = value
        services.runner.run(lambda: services.library.set_watched(item, value), self._user_updated, lambda _e: None)

    @Slot()
    def toggleFavorite(self):
        if not self._item:
            return
        item = dict(self._item)
        if item.get("type") == "Episode" and item.get("seriesId"):
            item = {"id": item["seriesId"], "type": "Series", "stremioType": item.get("stremioType"), "name": item.get("seriesName"),
                    "poster": item.get("poster"), "background": item.get("background"), "logo": item.get("logo")}
        value = not self.favorite
        services.runner.run(lambda: services.library.set_favorite(item, value), self._user_updated, lambda _e: None)

    @Property("QVariantList", notify=changed)
    def sources(self):
        out = []
        for source in self._sources:
            info = describe(source)
            info["selected"] = info["id"] == self._selected
            out.append(info)
        return out

    @Property(str, notify=changed)
    def selectedSourceId(self):
        return self._selected

    @Property(str, notify=changed)
    def selectedSourceLabel(self):
        stream = find(self._sources, self._selected)
        return short_label(stream) if stream else ""

    @Slot(str)
    def selectSource(self, source_id):
        stream = find(self._sources, source_id)
        if stream and source_id != self._selected:
            self._selected = source_id
            remember(self._item or {"id": self._id}, stream)
            self.changed.emit()
