import logging
import threading
import urllib.parse

import requests

from jellyfin_tv import __version__

log = logging.getLogger("jellyfin_tv.aio")

USER_AGENT = "AIOStreamsTV/%s (Linux)" % __version__
TIMEOUT = (10, 60)
PARALLEL = 4
TTL = {
    "manifest": 6 * 3600,
    "catalog": 30 * 60,
    "search": 60 * 60,
    "meta": 24 * 3600,
    "meta_airing": 6 * 3600,
    "stream": 15 * 60,
    "subtitles": 6 * 3600,
}
ERROR_PREFIX = "aiostreamserror"
PLAYABLE_TYPES = ("http", "debrid", "usenet", "live", "")


class AioError(Exception):
    pass


def normalize_manifest_url(text):
    text = (text or "").strip()
    if text.startswith("stremio://"):
        text = "https://" + text[len("stremio://"):]
    if text and "://" not in text:
        text = "https://" + text
    parts = urllib.parse.urlsplit(text)
    path = parts.path.rstrip("/")
    if path.endswith("/manifest.json"):
        path = path[:-len("/manifest.json")]
    if not parts.netloc or not path:
        raise AioError("Not a manifest URL")
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path + "/manifest.json", parts.query, ""))


def instance_origin(manifest_url):
    parts = urllib.parse.urlsplit(manifest_url)
    return "%s://%s" % (parts.scheme, parts.netloc)


def manifest_uuid(manifest_url):
    segments = urllib.parse.urlsplit(manifest_url).path.strip("/").split("/")
    if len(segments) >= 3 and segments[0] == "stremio":
        return segments[1]
    return ""


def encode_extra(extra):
    pairs = [(k, v) for k, v in (extra or {}).items() if v not in (None, "")]
    return "&".join("%s=%s" % (k, urllib.parse.quote(str(v), safe="")) for k, v in pairs)


def resolve_manifest(instance, user, password, http=None):
    origin = (instance or "").strip().rstrip("/")
    if origin and "://" not in origin:
        origin = "https://" + origin
    http = http or requests
    try:
        resp = http.get(origin + "/api/v1/user", auth=(user, password or ""),
                        headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        log.info("resolve %s: %s", origin, exc)
        raise AioError("Instance not reachable")
    try:
        body = resp.json()
    except ValueError:
        raise AioError("That address is not an AIOStreams instance")
    if not body.get("success"):
        error = body.get("error") or {}
        if error.get("code") in ("USER_INVALID_DETAILS", "USER_NOT_FOUND"):
            raise AioError("Wrong UUID or password")
        raise AioError(error.get("message") or "Sign-in failed")
    data = body.get("data") or {}
    uuid = (data.get("userData") or {}).get("uuid") or user
    encrypted = data.get("encryptedPassword")
    if not encrypted:
        raise AioError("Sign-in failed")
    return "%s/stremio/%s/%s/manifest.json" % (origin, uuid, encrypted)


def is_playable(stream):
    if not stream.get("url"):
        return False
    kind = (stream.get("streamData") or {}).get("type", "")
    return kind in PLAYABLE_TYPES


class AioClient:
    def __init__(self, manifest_url, cache, http=None, parallel=PARALLEL):
        self.manifest_url = normalize_manifest_url(manifest_url)
        parts = urllib.parse.urlsplit(self.manifest_url)
        self.base = urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path[:-len("/manifest.json")], "", ""))
        self.query = "?" + parts.query if parts.query else ""
        self.cache = cache
        self._http = http
        self._local = threading.local()
        self._gate = threading.Semaphore(parallel)

    def _session(self):
        if self._http is not None:
            return self._http
        sess = getattr(self._local, "session", None)
        if sess is None:
            sess = requests.Session()
            sess.headers["User-Agent"] = USER_AGENT
            self._local.session = sess
        return sess

    def url(self, resource, kind=None, item_id=None, extra=None):
        if resource == "manifest":
            return self.base + "/manifest.json" + self.query
        path = "%s/%s/%s" % (resource, kind, urllib.parse.quote(item_id, safe=":"))
        encoded = encode_extra(extra)
        if encoded:
            path += "/" + encoded
        return "%s/%s.json%s" % (self.base, path, self.query)

    def _get(self, url):
        with self._gate:
            try:
                resp = self._session().get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
            except requests.RequestException as exc:
                raise AioError("AIOStreams not reachable: %s" % exc.__class__.__name__)
        if resp.status_code == 429:
            raise AioError("AIOStreams is rate limiting requests, try again shortly")
        if resp.status_code >= 400:
            raise AioError("AIOStreams answered %d" % resp.status_code)
        try:
            return resp.json()
        except ValueError:
            raise AioError("AIOStreams sent an invalid response")

    def key(self, url):
        return url[len(self.base):] if url.startswith(self.base) else url

    def _peek(self, url):
        return self.cache.peek(self.key(url))

    def _cached(self, url, ttl, fresh=False):
        if fresh:
            self.cache.drop(self.key(url))
        return self.cache.get(self.key(url), ttl, lambda: self._get(url))

    def manifest(self, fresh=False):
        data = self._cached(self.url("manifest"), TTL["manifest"], fresh)
        if not isinstance(data, dict) or "resources" not in data:
            self.cache.drop(self.key(self.url("manifest")))
            raise AioError("Not an AIOStreams manifest")
        return data

    def peek_manifest(self):
        hit = self._peek(self.url("manifest"))
        return hit[1] if hit else None

    def catalog(self, kind, catalog_id, extra=None):
        ttl = TTL["search"] if extra and extra.get("search") else TTL["catalog"]
        data = self._cached(self.url("catalog", kind, catalog_id, extra), ttl)
        return [m for m in (data or {}).get("metas") or [] if m.get("id") and not str(m["id"]).startswith(ERROR_PREFIX)]

    def peek_catalog(self, kind, catalog_id, extra=None):
        hit = self._peek(self.url("catalog", kind, catalog_id, extra))
        if not hit:
            return None
        return [m for m in (hit[1] or {}).get("metas") or [] if m.get("id") and not str(m["id"]).startswith(ERROR_PREFIX)]

    def meta(self, kind, item_id, fresh=False):
        url = self.url("meta", kind, item_id)
        hit = self._peek(url)
        airing = hit and ((hit[1] or {}).get("meta") or {}).get("behaviorHints", {}).get("hasScheduledVideos")
        data = self._cached(url, TTL["meta_airing" if airing else "meta"], fresh)
        meta = (data or {}).get("meta")
        if not meta or str(meta.get("id", "")).startswith(ERROR_PREFIX):
            raise AioError(((meta or {}).get("description")) or "Nothing found for this title")
        return meta

    def peek_meta(self, kind, item_id):
        hit = self._peek(self.url("meta", kind, item_id))
        meta = (hit[1] or {}).get("meta") if hit else None
        return meta if meta and not str(meta.get("id", "")).startswith(ERROR_PREFIX) else None

    def streams(self, kind, video_id, fresh=False):
        data = self._cached(self.url("stream", kind, video_id), TTL["stream"], fresh)
        streams = (data or {}).get("streams") or []
        errors = [s for s in streams if (s.get("streamData") or {}).get("type") == "error"]
        for error in errors:
            log.info("stream error: %s %s", error.get("name"), error.get("description"))
        return [s for s in streams if is_playable(s)]

    def subtitles(self, kind, video_id, extra=None):
        data = self._cached(self.url("subtitles", kind, video_id, extra), TTL["subtitles"])
        return [s for s in (data or {}).get("subtitles") or [] if s.get("url") and s.get("lang")]
