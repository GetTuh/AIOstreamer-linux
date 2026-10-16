from PySide6.QtCore import Property, QObject, Signal, Slot

from jellyfin_tv.api.images import image_source
from jellyfin_tv.models.items import TICKS, episode_label, progress_for, subtitle_for
from jellyfin_tv.models.services import services
from jellyfin_tv.models.sources import describe, preferred_source_id, remember_source, sort_sources


def format_duration(ticks):
    seconds = int((ticks or 0) / TICKS)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%d:%02d" % (minutes, secs)


def format_runtime(ticks):
    minutes = int((ticks or 0) / TICKS / 60)
    if not minutes:
        return ""
    hours, mins = divmod(minutes, 60)
    return "%dh %dm" % (hours, mins) if hours else "%dm" % mins


class DetailsModel(QObject):
    changed = Signal()
    playRequested = Signal(float, str)

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

    @Slot()
    def reload(self):
        if not self._id:
            return
        self._generation += 1
        generation = self._generation
        item_id = self._id
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
        self._sources_loading = bool(value)
        self.changed.emit()
        self.reload()
        self._load_sources()

    def _loaded(self, item):
        self._item = item or {}
        self._loading = False
        self._error = ""
        if not self.playable:
            self._sources_loading = False
            self._pending_play = None
        self._rank()
        self.changed.emit()

    def _load_sources(self):
        item_id = self._id
        if not item_id:
            return
        services.runner.run(
            lambda: services.library.sources(item_id),
            lambda sources: item_id == self._id and self._sources_loaded(sources),
            lambda _e: item_id == self._id and self._sources_loaded([]))

    def _rank(self):
        original = self._item.get("OriginalLanguage") or ""
        self._sources = sort_sources(self._sources, original)
        self._selected = preferred_source_id(self._id, self._sources, original)

    def _sources_loaded(self, sources):
        self._sources_loading = False
        self._sources = list(sources)
        self._rank()
        pending, self._pending_play = self._pending_play, None
        self.changed.emit()
        if pending is not None:
            self.playRequested.emit(pending, self._selected)

    @Slot(float)
    def play(self, start_ticks):
        if self._sources_loading:
            self._pending_play = start_ticks
            self.changed.emit()
            return
        self.playRequested.emit(start_ticks, self._selected)

    @Property(bool, notify=changed)
    def playPending(self):
        return self._pending_play is not None

    @Property(bool, notify=changed)
    def sourcesLoading(self):
        return self._sources_loading

    def _failed(self, exc):
        self._loading = False
        self._error = str(exc) or "Could not load item"
        self.changed.emit()

    @property
    def item(self):
        return self._item

    def _get(self, key, default=None):
        return self._item.get(key, default)

    def _user(self, key, default=None):
        return (self._item.get("UserData") or {}).get(key, default)

    @Property(bool, notify=changed)
    def loading(self):
        return self._loading

    @Property(bool, notify=changed)
    def loaded(self):
        return bool(self._item)

    @Property(str, notify=changed)
    def error(self):
        return self._error

    def _get_id(self):
        return self._id

    itemId = Property(str, _get_id, _set_id, notify=changed)

    @Property(str, notify=changed)
    def itemType(self):
        return self._get("Type", "")

    @Property(str, notify=changed)
    def name(self):
        return self._get("Name", "")

    @Property(str, notify=changed)
    def seriesName(self):
        return self._get("SeriesName", "")

    @Property(str, notify=changed)
    def episodeLabel(self):
        return episode_label(self._item) if self._get("Type") == "Episode" else ""

    @Property(str, notify=changed)
    def overview(self):
        return self._get("Overview", "") or ""

    @Property(str, notify=changed)
    def tagline(self):
        taglines = self._get("Taglines") or []
        return taglines[0] if taglines else ""

    @Property(str, notify=changed)
    def year(self):
        return subtitle_for(self._item) if self._get("Type") == "Series" else str(self._get("ProductionYear") or "")

    @Property(str, notify=changed)
    def runtime(self):
        return format_runtime(self._get("RunTimeTicks"))

    @Property(str, notify=changed)
    def officialRating(self):
        return self._get("OfficialRating", "") or ""

    @Property(str, notify=changed)
    def communityRating(self):
        rating = self._get("CommunityRating")
        return "%.1f" % rating if rating else ""

    @Property(str, notify=changed)
    def genres(self):
        return " · ".join((self._get("Genres") or [])[:3])

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
    def resumeTicks(self):
        return float(self._user("PlaybackPositionTicks") or 0)

    @Property(str, notify=changed)
    def resumeText(self):
        return format_duration(self._user("PlaybackPositionTicks"))

    @Property(float, notify=changed)
    def progress(self):
        return progress_for(self._item)

    @Property(bool, notify=changed)
    def played(self):
        return bool(self._user("Played"))

    @Property(bool, notify=changed)
    def playable(self):
        return self._get("Type") in ("Movie", "Episode", "Video", "MusicVideo") and not self._get("IsFolder")

    @Property(int, notify=changed)
    def sourceCount(self):
        return len(self._sources)

    @Property(str, notify=changed)
    def seriesId(self):
        return self._get("SeriesId", "") or ""

    @Property(bool, notify=changed)
    def favorite(self):
        return bool(self._user("IsFavorite"))

    def _update_user(self, data):
        if data and self._item:
            user = dict(self._item.get("UserData") or {})
            user.update({k: v for k, v in data.items() if k in ("Played", "IsFavorite", "PlaybackPositionTicks", "PlayedPercentage", "UnplayedItemCount")})
            self._item["UserData"] = user
            self.changed.emit()
            self.userDataChanged.emit(self._id)

    userDataChanged = Signal(str)

    @Slot()
    def togglePlayed(self):
        item_id, value = self._id, not self.played
        services.runner.run(lambda: services.library.set_played(item_id, value), self._update_user, lambda _e: None)

    @Slot()
    def toggleFavorite(self):
        item_id, value = self._id, not self.favorite
        services.runner.run(lambda: services.library.set_favorite(item_id, value), self._update_user, lambda _e: None)

    @Property("QVariantList", notify=changed)
    def sources(self):
        out = []
        for source in self._sources:
            info = describe(source)
            info["selected"] = source.get("Id") == self._selected
            out.append(info)
        return out

    @Property(str, notify=changed)
    def selectedSourceId(self):
        return self._selected

    @Property(str, notify=changed)
    def selectedSourceLabel(self):
        for source in self._sources:
            if source.get("Id") == self._selected:
                info = describe(source)
                return " · ".join(p for p in (info["resolution"], info["hdr"], info["codec"], info["audio"], info["size"]) if p)
        return ""

    @Slot(str)
    def selectSource(self, source_id):
        if source_id and source_id != self._selected:
            self._selected = source_id
            remember_source(self._id, source_id)
            self.changed.emit()
