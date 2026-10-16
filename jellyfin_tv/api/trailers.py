import time

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

VIDEO = "bv*[height<=1080][vcodec^=avc1][protocol^=http]/bv*[height<=1080][protocol^=http]"
AUDIO = "ba[ext=m4a][protocol^=http]/ba[protocol^=http]"
FORMAT = "(%s)+(%s)/b[protocol^=http]" % (VIDEO, AUDIO)
TTL = 3600
MAX_SECONDS = 600


def search_url(title, year=None):
    if not title:
        return ""
    return "ytsearch1:%s official trailer" % " ".join(str(p) for p in (title, year) if p)


def _has(fmt, kind):
    return fmt.get(kind) not in (None, "none")


def streams_from(info):
    if "entries" in info:
        found = [e for e in info.get("entries") or [] if e and (e.get("duration") or 0) <= MAX_SECONDS]
        return streams_from(found[0]) if found else None
    parts = info.get("requested_formats")
    if parts:
        video = next((p for p in parts if _has(p, "vcodec")), None)
        audio = next((p for p in parts if p is not video and _has(p, "acodec")), None)
        if video is None:
            return None
        return {
            "video": video.get("url") or "",
            "audio": audio.get("url") or "" if audio else "",
            "muxed": _has(video, "acodec"),
        }
    if not info.get("url"):
        return None
    return {"video": info["url"], "audio": "", "muxed": _has(info, "acodec")}


def extract(url):
    if yt_dlp is None:
        raise RuntimeError("yt-dlp is not installed")
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True, "format": FORMAT}
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


class TrailerResolver:
    def __init__(self, extract_fn=None, clock=time.monotonic):
        self._extract = extract_fn or extract
        self._clock = clock
        self._cache = {}

    @property
    def available(self):
        return yt_dlp is not None or self._extract is not extract

    def resolve(self, url):
        hit = self._cache.get(url)
        if hit and self._clock() - hit[0] < TTL:
            return hit[1]
        streams = streams_from(self._extract(url) or {})
        self._cache[url] = (self._clock(), streams)
        return streams
