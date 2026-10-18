from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from jellyfin_tv.api import meta as m
from jellyfin_tv.models.details import format_duration
from jellyfin_tv.models.items import ItemListModel
from jellyfin_tv.models.services import services


class SeriesModel(QObject):
    changed = Signal()
    seasonChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._series_id = ""
        self._season_index = -1
        self._next_up = None
        self._target_episode = ""
        self._episodes_all = []
        self._seasons = ItemListModel(services.runner, self._fetch_seasons, "poster", 0, "Seasons", self, context="seasons")
        self._episodes = ItemListModel(services.runner, self._fetch_episodes, "thumb", 0, "Episodes", self, context="episodes")
        self._seasons.countChanged.connect(self._on_seasons)
        self._season_timer = QTimer(self)
        self._season_timer.setSingleShot(True)
        self._season_timer.setInterval(220)
        self._season_timer.timeout.connect(self._load_episodes)

    def _kind(self):
        return services.library.known(self._series_id).get("stremioType") or "series"

    def _season_items(self, episodes):
        history = services.library.history
        out = []
        for number in m.seasons(episodes):
            members = [e for e in episodes if e.get("season") == number]
            aired = [e for e in members if m.released(e)]
            watched = bool(aired) and history is not None and all(history.watched(e["id"]) for e in aired)
            first = members[0] if members else {}
            out.append({"id": "season:%s" % number, "type": "Season", "season": number, "name": m.season_name(number),
                        "poster": first.get("poster", ""), "played": watched})
        return out

    def _fetch_seasons(self, start, limit):
        _show, episodes = services.library.series(self._series_id, self._kind())
        self._episodes_all = episodes
        items = self._season_items(episodes)
        return items, len(items)

    def _fetch_episodes(self, start, limit):
        season = self._seasons.raw(self._season_index)
        if not season:
            return [], 0
        items = [e for e in self._episodes_all if e.get("season") == season["season"]]
        return items, len(items)

    def _get_series(self):
        return self._series_id

    def _set_series(self, value):
        if value == self._series_id:
            return
        self._series_id = value
        self._season_index = -1
        self.changed.emit()
        self.reload()

    seriesId = Property(str, _get_series, _set_series, notify=changed)

    def _lookup_next(self, callback):
        series_id, kind = self._series_id, self._kind()
        services.runner.run(lambda: services.library.series_next_up(series_id, kind), callback, lambda _e: callback(None))

    @Slot()
    def reload(self):
        if self._series_id:
            self._lookup_next(self._on_next_up)

    @Slot()
    def refresh(self):
        if not self._series_id:
            return
        self._lookup_next(self._on_refreshed_next_up)
        self._seasons.reload()
        if self._season_index >= 0:
            self._episodes.reload()

    def _on_next_up(self, item):
        self._next_up = item
        self.changed.emit()
        self._seasons.reload()

    def _on_refreshed_next_up(self, item):
        self._next_up = item
        self.changed.emit()

    def _on_seasons(self):
        if self._season_index >= 0 or self._seasons.count == 0:
            return
        index = -1
        if self._next_up:
            index = self._seasons.indexOf("season:%s" % self._next_up.get("season"))
            self._target_episode = self._next_up.get("id", "")
        if index < 0:
            for row, season in enumerate(self._seasons.items):
                if season.get("season") not in (0, None):
                    index = row
                    break
        self._set_season(max(index, 0), immediate=True)

    def _get_season(self):
        return self._season_index

    def _set_season(self, value, immediate=False):
        value = int(value)
        if value == self._season_index or value < 0 or value >= self._seasons.count:
            return
        self._season_index = value
        self.seasonChanged.emit()
        if immediate:
            self._season_timer.stop()
            self._load_episodes()
        else:
            self._season_timer.start()

    seasonIndex = Property(int, _get_season, _set_season, notify=seasonChanged)

    def _load_episodes(self):
        self._episodes.clear()
        self._episodes.reload()

    @Property(QObject, constant=True)
    def seasons(self):
        return self._seasons

    @Property(QObject, constant=True)
    def episodes(self):
        return self._episodes

    @Property(str, notify=changed)
    def targetEpisodeId(self):
        return self._target_episode

    @Property(str, notify=changed)
    def nextUpId(self):
        return (self._next_up or {}).get("id", "")

    @Property(str, notify=changed)
    def nextUpLabel(self):
        return m.episode_label(self._next_up) if self._next_up else ""

    @Property(float, notify=changed)
    def nextUpResumeSeconds(self):
        history = services.library.history
        if not self._next_up or history is None:
            return 0.0
        return float(history.progress(self._next_up["id"])[0])

    @Property(str, notify=changed)
    def nextUpResumeText(self):
        return format_duration(self.nextUpResumeSeconds) if self.nextUpResumeSeconds else ""
