import json
import logging
import os
import threading
import time
from pathlib import Path

log = logging.getLogger("aiostreamer.history")

WATCHED_AT = 0.9
RESUME_FROM = 0.02
MIN_RESUME_SECONDS = 60
ITEM_KEYS = ("id", "type", "stremioType", "seriesId", "seriesName", "season", "episode", "name", "poster",
             "background", "logo", "thumbnail", "year", "runtime", "overview")


def slim(item):
    return {k: item[k] for k in ITEM_KEYS if item.get(k) not in (None, "", [])}


class WatchState:
    def __init__(self, path, clock=time.time):
        self.path = Path(path)
        self._clock = clock
        self._lock = threading.RLock()
        self._data = self._load()

    def _load(self):
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            data = {}
        for key in ("progress", "watched", "items", "favorites", "shows"):
            if not isinstance(data.get(key), dict):
                data[key] = {}
        return data

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self._data))
            os.replace(tmp, self.path)
        except OSError as exc:
            log.warning("could not save watch state: %s", exc)

    def _remember(self, item, touch_show=True):
        self._data["items"][item["id"]] = slim(item)
        if touch_show and item.get("type") == "Episode" and item.get("seriesId"):
            show = self._data["shows"].setdefault(item["seriesId"], {})
            show.update({"last": item["id"], "updated": self._clock(),
                         "item": {"id": item["seriesId"], "type": "Series", "stremioType": item.get("stremioType", "series"),
                                  "name": item.get("seriesName", ""), "poster": item.get("poster", ""),
                                  "background": item.get("background", ""), "logo": item.get("logo", "")}})

    def record(self, item, position, duration):
        if not item or not item.get("id"):
            return False
        duration = float(duration or 0) or float(item.get("runtime") or 0)
        position = float(position or 0)
        with self._lock:
            finished = duration > 0 and position / duration >= WATCHED_AT
            resumable = not finished and position >= MIN_RESUME_SECONDS and (not duration or position / duration >= RESUME_FROM)
            self._remember(item, finished or resumable)
            if finished:
                self._data["progress"].pop(item["id"], None)
                self._data["watched"][item["id"]] = self._clock()
            elif resumable:
                self._data["progress"][item["id"]] = {"position": position, "duration": duration, "updated": self._clock()}
                self._data["watched"].pop(item["id"], None)
            self._save()
        return finished

    def set_watched(self, items, watched):
        with self._lock:
            for item in items:
                item_id = item["id"]
                self._data["progress"].pop(item_id, None)
                if watched:
                    self._remember(item)
                    self._data["watched"][item_id] = self._clock()
                else:
                    self._data["watched"].pop(item_id, None)
            self._save()

    def watched(self, item_id):
        return item_id in self._data["watched"]

    def progress(self, item_id):
        entry = self._data["progress"].get(item_id)
        return (entry["position"], entry.get("duration") or 0) if entry else (0.0, 0.0)

    def fraction(self, item_id):
        position, duration = self.progress(item_id)
        return max(0.0, min(1.0, position / duration)) if position and duration else 0.0

    def item(self, item_id):
        return self._data["items"].get(item_id)

    def resume(self, limit=24):
        entries = sorted(self._data["progress"].items(), key=lambda kv: kv[1].get("updated", 0), reverse=True)
        out, shows = [], set()
        for item_id, _entry in entries:
            item = self._data["items"].get(item_id)
            if not item:
                continue
            if item.get("seriesId"):
                if item["seriesId"] in shows:
                    continue
                shows.add(item["seriesId"])
            out.append(dict(item))
            if len(out) >= limit:
                break
        return out

    def recent(self, limit=24):
        seen = {sid: (show.get("updated", 0), show["item"]) for sid, show in self._data["shows"].items() if show.get("item")}
        stamps = dict(self._data["watched"])
        for item_id, entry in self._data["progress"].items():
            stamps[item_id] = max(stamps.get(item_id, 0), entry.get("updated", 0))
        for item_id, stamp in stamps.items():
            item = self._data["items"].get(item_id)
            if item and item.get("type") != "Episode":
                seen[item_id] = (stamp, item)
        ordered = sorted(seen.values(), key=lambda entry: entry[0], reverse=True)
        return [dict(item) for _, item in ordered[:limit]]

    def recent_shows(self, limit=24):
        shows = sorted(self._data["shows"].items(), key=lambda kv: kv[1].get("updated", 0), reverse=True)
        return [(series_id, dict(entry)) for series_id, entry in shows[:limit]]

    def last_episode(self, series_id):
        return (self._data["shows"].get(series_id) or {}).get("last")

    def favorite(self, item_id):
        return item_id in self._data["favorites"]

    def set_favorite(self, item, value):
        with self._lock:
            if value:
                self._data["favorites"][item["id"]] = {"item": slim(item), "added": self._clock()}
            else:
                self._data["favorites"].pop(item["id"], None)
            self._save()

    def favorites(self):
        entries = sorted(self._data["favorites"].values(), key=lambda e: e.get("added", 0), reverse=True)
        return [dict(e["item"]) for e in entries if e.get("item")]
