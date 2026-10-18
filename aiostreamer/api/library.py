import logging
import re
import threading

from aiostreamer.api import meta as m

log = logging.getLogger("aiostreamer.library")

TT_EPISODE_RE = re.compile(r"^(tt\d+):(\d+):(\d+)$")
NEXT_UP_SHOWS = 16
CATALOG_PAGES = 6


def stremio_kind(item):
    return item.get("stremioType") or ("series" if item.get("type") in ("Series", "Episode") else "movie")


def regular(episodes):
    return [e for e in episodes if e.get("season") not in (0, None)] or list(episodes)


class Library:
    def __init__(self, session):
        self.session = session
        self._known = {}
        self._lock = threading.Lock()

    @property
    def client(self):
        return self.session.client

    @property
    def history(self):
        return self.session.history

    def _note(self, items):
        with self._lock:
            for item in items:
                self._known[item["id"]] = {k: item.get(k) for k in ("type", "stremioType", "seriesId")}
        return items

    def _previews(self, metas):
        seen, out = set(), []
        for meta in metas:
            if meta.get("id") in seen:
                continue
            seen.add(meta["id"])
            out.append(m.from_meta(meta))
        return self._note(out)

    def known(self, item_id):
        with self._lock:
            hit = dict(self._known.get(item_id) or {})
        if not hit and self.history is not None:
            stored = self.history.item(item_id)
            if stored:
                hit = {k: stored.get(k) for k in ("type", "stremioType", "seriesId")}
        if not hit:
            match = TT_EPISODE_RE.match(item_id or "")
            if match:
                hit = {"type": "Episode", "stremioType": "series", "seriesId": match.group(1)}
        return hit

    def catalogs(self):
        manifest = self.client.manifest()
        return [c for c in manifest.get("catalogs") or [] if c.get("id") and c.get("type")]

    def home_catalogs(self):
        rows = []
        for catalog in self.catalogs():
            if not m.browsable(catalog):
                continue
            rows.append({
                "key": "catalog:%s:%s" % (catalog["type"], catalog["id"]),
                "title": m.catalog_title(catalog),
                "type": catalog["type"],
                "id": catalog["id"],
                "extra": m.home_extra(catalog),
                "genres": (m.catalog_extra(catalog, "genre") or {}).get("options") or [],
                "genreRequired": bool((m.catalog_extra(catalog, "genre") or {}).get("isRequired")),
            })
        return rows

    def peek_catalog(self, kind, catalog_id, extra=None):
        metas = self.client.peek_catalog(kind, catalog_id, extra)
        return None if metas is None else self._previews(metas)

    def catalog(self, kind, catalog_id, extra=None, start=0, limit=0):
        items, seen = [], set()
        skip = start
        for _ in range(CATALOG_PAGES):
            page_extra = dict(extra or {})
            if skip:
                page_extra["skip"] = skip
            metas = self.client.catalog(kind, catalog_id, page_extra or None)
            fresh = [x for x in metas if x.get("id") not in seen]
            if not fresh:
                return self._previews(items), start + len(items)
            seen.update(x["id"] for x in fresh)
            items.extend(fresh)
            skip += len(metas)
            if not limit or len(items) >= limit:
                break
        return self._previews(items), start + len(items) + 1

    def search(self, term, kind):
        types = ("movie",) if kind == "Movie" else ("series", "anime")
        found = []
        for catalog in self.catalogs():
            if catalog["type"] not in types or not m.searchable(catalog):
                continue
            try:
                found.extend(self.client.catalog(catalog["type"], catalog["id"], {"search": term}))
            except Exception as exc:
                log.info("search in %s failed: %s", catalog["id"], exc)
        return self._previews(found)

    def series(self, series_id, stremio_type="series", fresh=False):
        meta = self.client.meta(stremio_type or "series", series_id, fresh)
        show = m.from_meta(meta)
        self._note([show])
        return show, self._note(m.episodes(meta))

    def item(self, item_id, kind="", series_id=""):
        info = self.known(item_id)
        kind = kind or info.get("type") or ""
        series_id = series_id or info.get("seriesId") or ""
        if kind == "Episode" or series_id:
            show, episodes = self.series(series_id, info.get("stremioType") or "series")
            for episode in episodes:
                if episode["id"] == item_id:
                    return episode
            raise LookupError("Episode not found")
        stremio_type = info.get("stremioType") or ("series" if kind == "Series" else "movie")
        meta = self.client.meta(stremio_type, item_id)
        item = m.from_meta(meta)
        self._note([item])
        if item["type"] == "Series":
            self._note(m.episodes(meta))
        return item

    def peek_item(self, item_id):
        info = self.known(item_id)
        if info.get("type") == "Episode":
            meta = self.client.peek_meta(info.get("stremioType") or "series", info.get("seriesId") or "")
            if meta:
                return next((e for e in m.episodes(meta) if e["id"] == item_id), None)
            return None
        stremio_type = info.get("stremioType") or ("series" if info.get("type") == "Series" else "movie")
        meta = self.client.peek_meta(stremio_type, item_id)
        return m.from_meta(meta) if meta else None

    def resume(self, limit=24):
        return self._note(self.history.resume(limit)) if self.history else []

    def favorites(self):
        return self._note(self.history.favorites()) if self.history else []

    def _after_last(self, series_id, episodes):
        history = self.history
        ordered = regular(episodes)
        last = history.last_episode(series_id)
        index = next((i for i, e in enumerate(ordered) if e["id"] == last), -1)
        if index < 0:
            return None
        for episode in ordered[index + 1:]:
            if not history.watched(episode["id"]):
                return episode if m.released(episode) else None
        return None

    def next_up(self, limit=24):
        history = self.history
        if history is None:
            return []
        out = []
        for series_id, entry in history.recent_shows(NEXT_UP_SHOWS):
            last = entry.get("last")
            if not last or history.progress(last)[0]:
                continue
            kind = (entry.get("item") or {}).get("stremioType") or "series"
            try:
                _show, episodes = self.series(series_id, kind)
            except Exception as exc:
                log.info("next up for %s: %s", series_id, exc)
                continue
            episode = self._after_last(series_id, episodes)
            if episode and not history.progress(episode["id"])[0]:
                out.append(episode)
            if len(out) >= limit:
                break
        return out

    def series_next_up(self, series_id, stremio_type="series"):
        _show, episodes = self.series(series_id, stremio_type)
        history = self.history
        ordered = regular(episodes)
        if not ordered:
            return None
        started = [e for e in ordered if history.progress(e["id"])[0]]
        last = history.last_episode(series_id)
        if started:
            started.sort(key=lambda e: e["id"] == last, reverse=True)
            return started[0]
        following = self._after_last(series_id, episodes)
        if following:
            return following
        for episode in ordered:
            if not history.watched(episode["id"]) and m.released(episode):
                return episode
        return ordered[0]

    def next_episode(self, item):
        if item.get("type") != "Episode" or not item.get("seriesId"):
            return None
        _show, episodes = self.series(item["seriesId"], stremio_kind(item))
        ordered = regular(episodes) if item.get("season") not in (0, None) else episodes
        for index, episode in enumerate(ordered):
            if episode["id"] == item["id"]:
                if index + 1 < len(ordered) and m.released(ordered[index + 1]):
                    return ordered[index + 1]
                return None
        return None

    def streams(self, item, fresh=False):
        return self.client.streams(stremio_kind(item), item["id"], fresh)

    def subtitles(self, item, stream=None):
        hints = (stream or {}).get("behaviorHints") or {}
        extra = {"filename": hints.get("filename"), "videoSize": hints.get("videoSize"), "videoHash": hints.get("videoHash")}
        try:
            found = self.client.subtitles(stremio_kind(item), item["id"], extra)
        except Exception as exc:
            log.info("subtitles: %s", exc)
            found = []
        found += [s for s in (stream or {}).get("subtitles") or [] if s.get("url")]
        return found

    def trailers(self, item_id):
        item = self.peek_item(item_id) or self.item(item_id)
        return {
            "remote": ["https://www.youtube.com/watch?v=%s" % t for t in item.get("trailers") or []],
            "title": item.get("name") or "",
            "year": (item.get("year") or "")[:4],
        }

    def set_watched(self, item, watched):
        if item.get("type") == "Series":
            _show, episodes = self.series(item["id"], stremio_kind(item))
            targets = [e for e in episodes if m.released(e)]
        else:
            targets = [item]
        self.history.set_watched(targets, watched)
        return watched

    def set_favorite(self, item, favorite):
        self.history.set_favorite(item, favorite)
        return favorite
