from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from jellyfin_tv.models.details import format_duration
from jellyfin_tv.models.items import ItemListModel, episode_label
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
        self._seasons = ItemListModel(services.runner, self._fetch_seasons, "poster", 0, "Seasons", self, context="seasons")
        self._episodes = ItemListModel(services.runner, self._fetch_episodes, "thumb", 0, "Episodes", self, context="episodes")
        self._seasons.countChanged.connect(self._on_seasons)
        self._season_timer = QTimer(self)
        self._season_timer.setSingleShot(True)
        self._season_timer.setInterval(220)
        self._season_timer.timeout.connect(self._load_episodes)

    def _fetch_seasons(self, start, limit):
        items = services.library.seasons(self._series_id)
        return items, len(items)

    def _fetch_episodes(self, start, limit):
        season = self._seasons.raw(self._season_index)
        if not season:
            return [], 0
        items = services.library.episodes(self._series_id, season["Id"])
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

    @Slot()
    def reload(self):
        if not self._series_id:
            return
        series_id = self._series_id
        services.runner.run(lambda: services.library.series_next_up(series_id), self._on_next_up, lambda _e: self._on_next_up(None))

    @Slot()
    def refresh(self):
        if not self._series_id:
            return
        series_id = self._series_id
        services.runner.run(lambda: services.library.series_next_up(series_id), self._on_refreshed_next_up, lambda _e: None)
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
            index = self._seasons.indexOf(self._next_up.get("SeasonId") or "")
            self._target_episode = self._next_up.get("Id", "")
        if index < 0:
            for row, season in enumerate(self._seasons.items):
                if season.get("IndexNumber") not in (0, None):
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
        return (self._next_up or {}).get("Id", "")

    @Property(str, notify=changed)
    def nextUpLabel(self):
        return episode_label(self._next_up) if self._next_up else ""

    @Property(float, notify=changed)
    def nextUpResumeTicks(self):
        return float(((self._next_up or {}).get("UserData") or {}).get("PlaybackPositionTicks") or 0)

    @Property(str, notify=changed)
    def nextUpResumeText(self):
        return format_duration(self.nextUpResumeTicks) if self.nextUpResumeTicks else ""
